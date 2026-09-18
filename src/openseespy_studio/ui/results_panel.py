from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..jobs import JobRecord


class TimeHistoryPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._x: list[float] = []
        self._y: list[float] = []
        self.setMinimumHeight(140)

    def set_series(self, x: list[float], y: list[float]) -> None:
        self._x = list(x)
        self._y = list(y)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if len(self._x) < 2 or len(self._y) < 2:
            painter.setPen(QColor("#718195"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No time-history data")
            return

        margin_left, margin_right = 48, 14
        margin_top, margin_bottom = 16, 28
        left = margin_left
        right = max(left + 1, self.width() - margin_right)
        top = margin_top
        bottom = max(top + 1, self.height() - margin_bottom)

        xmin, xmax = min(self._x), max(self._x)
        ymin, ymax = min(self._y), max(self._y)
        if abs(xmax - xmin) < 1.0e-15:
            xmax = xmin + 1.0
        if abs(ymax - ymin) < 1.0e-15:
            pad = max(abs(ymax), 1.0) * 0.05
            ymin -= pad
            ymax += pad

        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(left, bottom, right, bottom)
        painter.drawLine(left, top, left, bottom)

        def point(x: float, y: float) -> QPointF:
            px = left + (x - xmin) / (xmax - xmin) * (right - left)
            py = bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
            return QPointF(px, py)

        painter.setPen(QPen(QColor("#2f80ed"), 2))
        previous = point(self._x[0], self._y[0])
        for x, y in zip(self._x[1:], self._y[1:]):
            current = point(x, y)
            painter.drawLine(previous, current)
            previous = current

        painter.setPen(QColor("#526579"))
        painter.drawText(4, top + 8, f"{ymax:.3g}")
        painter.drawText(4, bottom, f"{ymin:.3g}")
        painter.drawText(left, self.height() - 7, f"{xmin:.3g}")
        painter.drawText(right - 35, self.height() - 7, f"{xmax:.3g}")


class ResultsPanel(QWidget):
    deformation_requested = Signal(float)
    mode_shape_requested = Signal(int, float)
    clear_overlay_requested = Signal()
    job_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: dict[str, Any] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 5, 6, 5)
        root.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)

        self._build_jobs_tab()
        self._build_deformation_tab()
        self._build_mode_tab()
        self._build_node_tab()
        self._build_element_tab()
        self._build_history_tab()

    def _build_jobs_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        self.jobs_table = QTableWidget(0, 7)
        self.jobs_table.setHorizontalHeaderLabels(
            [
                "Job",
                "Analysis",
                "Type",
                "Status",
                "Progress",
                "Elapsed (s)",
                "Message",
            ]
        )
        self.jobs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        self.jobs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.jobs_table.cellClicked.connect(self._job_clicked)
        layout.addWidget(self.jobs_table)
        self.tabs.addTab(page, "Jobs")

    def _build_deformation_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Scale:"))
        self.deformation_scale = QDoubleSpinBox()
        self.deformation_scale.setRange(0.01, 1.0e6)
        self.deformation_scale.setDecimals(3)
        self.deformation_scale.setValue(10.0)
        row.addWidget(self.deformation_scale)
        show = QPushButton("Show Deformed")
        clear = QPushButton("Clear")
        show.clicked.connect(
            lambda: self.deformation_requested.emit(
                self.deformation_scale.value()
            )
        )
        clear.clicked.connect(self.clear_overlay_requested.emit)
        row.addWidget(show)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)
        self.deformation_info = QLabel("Run a non-modal analysis to view deformation.")
        self.deformation_info.setWordWrap(True)
        layout.addWidget(self.deformation_info)
        layout.addStretch(1)
        self.tabs.addTab(page, "Deformation")

    def _build_mode_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        row.addWidget(self.mode_combo)
        row.addWidget(QLabel("Scale:"))
        self.mode_scale = QDoubleSpinBox()
        self.mode_scale.setRange(0.01, 1.0e6)
        self.mode_scale.setValue(1.0)
        row.addWidget(self.mode_scale)
        show = QPushButton("Show Mode")
        show.clicked.connect(self._emit_mode)
        row.addWidget(show)
        row.addStretch(1)
        layout.addLayout(row)
        self.mode_info = QLabel("Run a Modal analysis to populate mode shapes.")
        self.mode_info.setWordWrap(True)
        layout.addWidget(self.mode_info)
        layout.addStretch(1)
        self.tabs.addTab(page, "Mode Shape")

    def _build_node_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Quantity:"))
        self.node_quantity = QComboBox()
        self.node_quantity.addItems(["Displacement", "Reaction"])
        self.node_quantity.currentTextChanged.connect(self._populate_node_table)
        row.addWidget(self.node_quantity)
        row.addStretch(1)
        layout.addLayout(row)

        self.node_table = QTableWidget(0, 7)
        self.node_table.setHorizontalHeaderLabels(
            ["Node", "X", "Y", "Z", "RX", "RY", "RZ"]
        )
        self.node_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.node_table.horizontalHeader().setStretchLastSection(True)
        self.node_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.node_table)
        self.tabs.addTab(page, "Node Results")

    def _build_element_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.element_table = QTableWidget(0, 2)
        self.element_table.setHorizontalHeaderLabels(["Element", "Force vector"])
        self.element_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.element_table.horizontalHeader().setStretchLastSection(True)
        self.element_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.element_table)
        self.tabs.addTab(page, "Element Results")

    def _build_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.history_label = QLabel("Monitor node: -")
        row.addWidget(self.history_label)
        row.addWidget(QLabel("Quantity:"))
        self.history_quantity = QComboBox()
        self.history_quantity.addItems(["Monitor displacement", "Base shear"])
        self.history_quantity.currentTextChanged.connect(
            self._update_history_plot
        )
        row.addWidget(self.history_quantity)
        row.addWidget(QLabel("DOF:"))
        self.history_dof = QComboBox()
        self.history_dof.addItems(["UX", "UY", "UZ", "RX", "RY", "RZ"])
        self.history_dof.currentIndexChanged.connect(self._update_history_plot)
        row.addWidget(self.history_dof)
        row.addStretch(1)
        layout.addLayout(row)
        self.history_plot = TimeHistoryPlot()
        layout.addWidget(self.history_plot, 1)
        self.tabs.addTab(page, "Time History")

    def _job_clicked(self, row: int, column: int) -> None:
        item = self.jobs_table.item(row, 0)
        if item is None:
            return
        job_id = item.data(Qt.UserRole)
        if job_id is not None:
            self.job_selected.emit(int(job_id))

    def clear_all(self) -> None:
        self._result = {}
        self.jobs_table.setRowCount(0)
        self.node_table.setRowCount(0)
        self.element_table.setRowCount(0)
        self.mode_combo.clear()
        self.deformation_info.setText(
            "Run a non-modal analysis to view deformation."
        )
        self.mode_info.setText("Run a Modal analysis to populate mode shapes.")
        self.history_label.setText("Monitor node: -")
        self.history_plot.set_series([], [])

    def _emit_mode(self) -> None:
        mode = self.mode_combo.currentData()
        if mode is None:
            return
        self.mode_shape_requested.emit(int(mode), self.mode_scale.value())

    def add_or_update_job(self, job: JobRecord) -> None:
        row = None
        for index in range(self.jobs_table.rowCount()):
            item = self.jobs_table.item(index, 0)
            if item is not None and item.data(Qt.UserRole) == job.job_id:
                row = index
                break
        if row is None:
            row = self.jobs_table.rowCount()
            self.jobs_table.insertRow(row)

        values = [
            f"Job {job.job_id}",
            job.analysis_name,
            job.analysis_type,
            job.status,
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 0:
                item.setData(Qt.UserRole, job.job_id)
            self.jobs_table.setItem(row, column, item)

        progress = self.jobs_table.cellWidget(row, 4)
        if not isinstance(progress, QProgressBar):
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setTextVisible(True)
            self.jobs_table.setCellWidget(row, 4, progress)
        progress.setValue(int(round(job.progress_percent)))
        progress.setFormat(
            f"{job.progress_current}/{job.progress_total} · %p%"
            if job.progress_total > 0
            else "%p%"
        )

        self.jobs_table.setItem(
            row,
            5,
            QTableWidgetItem(f"{job.elapsed_seconds:.2f}"),
        )
        self.jobs_table.setItem(
            row,
            6,
            QTableWidgetItem(job.message),
        )

    def set_result(self, result: dict[str, Any]) -> None:
        self._result = dict(result or {})
        analysis = self._result.get("analysis", {})
        final = self._result.get("final", {})
        displacements = final.get("node_displacements", {})

        self.deformation_info.setText(
            f"{analysis.get('type', 'Analysis')} · "
            f"{len(displacements)} node displacement result(s)"
            if displacements
            else "No final nodal displacement data in this result."
        )

        self.mode_combo.clear()
        modes = self._result.get("modes", {})
        for key in sorted(modes, key=lambda value: int(value)):
            mode = modes[key]
            eigenvalue = mode.get("eigenvalue", 0.0)
            self.mode_combo.addItem(
                f"Mode {key}  λ={float(eigenvalue):.5g}",
                int(key),
            )
        self.mode_info.setText(
            f"{len(modes)} mode shape(s) available."
            if modes
            else "No mode-shape data in this result."
        )

        self._populate_node_table()
        self._populate_element_table()
        self._update_history_plot()

    def _populate_node_table(self) -> None:
        final = self._result.get("final", {})
        key = (
            "node_displacements"
            if self.node_quantity.currentText() == "Displacement"
            else "node_reactions"
        )
        data = final.get(key, {})
        tags = sorted(data, key=lambda value: int(value))
        self.node_table.setRowCount(len(tags))
        for row, tag in enumerate(tags):
            values = list(data[tag])
            while len(values) < 6:
                values.append(0.0)
            self.node_table.setItem(row, 0, QTableWidgetItem(str(tag)))
            for column, value in enumerate(values[:6], start=1):
                self.node_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(f"{float(value):.6g}"),
                )

    def _populate_element_table(self) -> None:
        final = self._result.get("final", {})
        forces = (
            final.get("element_forces", {})
            if isinstance(final, dict)
            else {}
        )
        tags = sorted(forces, key=lambda value: int(value))
        self.element_table.setRowCount(len(tags))
        for row, tag in enumerate(tags):
            values = forces[tag]
            text = ", ".join(f"{float(value):.6g}" for value in values)
            self.element_table.setItem(row, 0, QTableWidgetItem(str(tag)))
            self.element_table.setItem(row, 1, QTableWidgetItem(text))

    def _update_history_plot(self) -> None:
        history = self._result.get("history", {})
        time = [float(value) for value in history.get("time", [])]
        self.history_label.setText(
            f"Monitor node: {history.get('monitor_node', '-')}"
        )

        if self.history_quantity.currentText() == "Base shear":
            self.history_dof.setEnabled(False)
            values = [
                float(value)
                for value in history.get("base_shear", [])
            ]
        else:
            self.history_dof.setEnabled(True)
            rows = history.get("displacement", [])
            index = self.history_dof.currentIndex()
            values = [
                float(row[index]) if index < len(row) else 0.0
                for row in rows
            ]
        self.history_plot.set_series(time, values)
