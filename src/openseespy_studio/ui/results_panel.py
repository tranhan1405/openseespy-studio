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
from ..postprocess import component_end_resultants, pushover_capacity_curve


class TimeHistoryPlot(QWidget):
    def __init__(
        self,
        parent=None,
        *,
        empty_message: str = "No time-history data",
    ):
        super().__init__(parent)
        self._x: list[float] = []
        self._y: list[float] = []
        self._empty_message = str(empty_message)
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
            painter.drawText(self.rect(), Qt.AlignCenter, self._empty_message)
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
    member_force_requested = Signal(str, float)
    node_contour_requested = Signal(str, str)
    element_selected = Signal(int)
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
        self._build_pushover_tab()
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
        self.node_quantity.currentTextChanged.connect(
            self._node_quantity_changed
        )
        row.addWidget(self.node_quantity)

        row.addWidget(QLabel("Contour:"))
        self.node_contour_component = QComboBox()
        row.addWidget(self.node_contour_component)

        show = QPushButton("Show Contour")
        show.clicked.connect(
            lambda: self.node_contour_requested.emit(
                self.node_quantity.currentText(),
                self.node_contour_component.currentText(),
            )
        )
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_overlay_requested.emit)
        row.addWidget(show)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)

        self.node_table = QTableWidget(0, 7)
        self.node_table.setHorizontalHeaderLabels(
            ["Node", "UX", "UY", "UZ", "RX", "RY", "RZ"]
        )
        self.node_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.node_table.horizontalHeader().setStretchLastSection(True)
        self.node_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.node_table)
        self.tabs.addTab(page, "Node Results")
        self._node_quantity_changed(self.node_quantity.currentText())

    def _node_quantity_changed(self, quantity: str) -> None:
        self.node_contour_component.clear()
        if str(quantity) == "Reaction":
            self.node_contour_component.addItems(
                ["|F|", "FX", "FY", "FZ", "|M|", "MX", "MY", "MZ"]
            )
        else:
            self.node_contour_component.addItems(
                ["|U|", "UX", "UY", "UZ", "|R|", "RX", "RY", "RZ"]
            )
        self._populate_node_table()

    def _build_element_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Local component:"))
        self.element_quantity = QComboBox()
        self.element_quantity.addItems(["N", "Vy", "Vz", "T", "My", "Mz"])
        self.element_quantity.currentTextChanged.connect(
            self._populate_element_table
        )
        controls.addWidget(self.element_quantity)

        controls.addWidget(QLabel("Diagram scale:"))
        self.member_force_scale = QDoubleSpinBox()
        self.member_force_scale.setRange(0.01, 1000.0)
        self.member_force_scale.setDecimals(3)
        self.member_force_scale.setValue(1.0)
        controls.addWidget(self.member_force_scale)

        show = QPushButton("Show Diagram")
        show.clicked.connect(
            lambda: self.member_force_requested.emit(
                self.element_quantity.currentText(),
                self.member_force_scale.value(),
            )
        )
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_overlay_requested.emit)
        controls.addWidget(show)
        controls.addWidget(clear)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.element_info = QLabel(
            "Member-force diagrams use equilibrium reconstruction where "
            "available and actual OpenSees section integration-point "
            "resultants for displacement-based nonlinear members."
        )
        self.element_info.setWordWrap(True)
        layout.addWidget(self.element_info)

        self.element_table = QTableWidget(0, 4)
        self.element_table.setHorizontalHeaderLabels(
            ["Element", "I end", "J end", "Max |diagram|"]
        )
        self.element_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.element_table.horizontalHeader().setStretchLastSection(True)
        self.element_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.element_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.element_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.element_table.cellClicked.connect(self._element_clicked)
        layout.addWidget(self.element_table)
        self.tabs.addTab(page, "Member Forces")

    def _build_pushover_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        self.pushover_info = QLabel(
            "Run a Pushover analysis to plot applied base shear versus "
            "control-node displacement."
        )
        self.pushover_info.setWordWrap(True)
        layout.addWidget(self.pushover_info)

        self.pushover_metrics = QLabel(
            "Vpeak: -   u@Vpeak: -   ufinal: -"
        )
        self.pushover_metrics.setWordWrap(True)
        layout.addWidget(self.pushover_metrics)

        self.pushover_plot = TimeHistoryPlot(
            empty_message="No pushover capacity-curve data"
        )
        layout.addWidget(self.pushover_plot, 1)
        self.tabs.addTab(page, "Pushover Curve")

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

    def _element_clicked(self, row: int, column: int) -> None:
        item = self.element_table.item(row, 0)
        if item is None:
            return
        tag = item.data(Qt.UserRole)
        if tag is None:
            try:
                tag = int(item.text())
            except ValueError:
                return
        self.element_selected.emit(int(tag))

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
        self.element_info.setText(
            "Run a non-modal frame analysis to populate local member forces."
        )
        self.mode_combo.clear()
        self.deformation_info.setText(
            "Run a non-modal analysis to view deformation."
        )
        self.mode_info.setText("Run a Modal analysis to populate mode shapes.")
        self.pushover_info.setText(
            "Run a Pushover analysis to plot applied base shear versus "
            "control-node displacement."
        )
        self.pushover_metrics.setText(
            "Vpeak: -   u@Vpeak: -   ufinal: -"
        )
        self.pushover_plot.set_series([], [])
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
        self._update_pushover_plot()
        self._update_history_plot()

    def _populate_node_table(self) -> None:
        final = self._result.get("final", {})
        displacement = self.node_quantity.currentText() == "Displacement"
        key = "node_displacements" if displacement else "node_reactions"
        self.node_table.setHorizontalHeaderLabels(
            (
                ["Node", "UX", "UY", "UZ", "RX", "RY", "RZ"]
                if displacement
                else ["Node", "FX", "FY", "FZ", "MX", "MY", "MZ"]
            )
        )
        data = final.get(key, {})
        if not isinstance(data, dict):
            data = {}
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
            final.get("element_local_forces", {})
            if isinstance(final, dict)
            else {}
        )
        diagrams = (
            final.get("member_force_diagrams", {})
            if isinstance(final, dict)
            else {}
        )
        if not isinstance(forces, dict):
            forces = {}
        if not isinstance(diagrams, dict):
            diagrams = {}

        component = self.element_quantity.currentText()
        rows: list[tuple[int, float, float, float, str]] = []
        skipped = 0
        source_counts: dict[str, int] = {}

        tags = set(forces)
        tags.update(diagrams)
        for raw_tag in sorted(tags, key=lambda value: int(value)):
            tag = int(raw_tag)
            diagram_by_component = diagrams.get(
                str(tag),
                diagrams.get(tag, {}),
            )
            diagram = (
                diagram_by_component.get(component, {})
                if isinstance(diagram_by_component, dict)
                else {}
            )

            if isinstance(diagram, dict):
                values = diagram.get("values", [])
                if isinstance(values, (list, tuple)) and values:
                    numeric = [float(value) for value in values]
                    source = str(
                        diagram.get("source", "member distribution")
                    )
                    rows.append(
                        (
                            tag,
                            numeric[0],
                            numeric[-1],
                            max(abs(value) for value in numeric),
                            source,
                        )
                    )
                    source_counts[source] = (
                        source_counts.get(source, 0) + 1
                    )
                    continue

            raw = forces.get(str(tag), forces.get(tag, []))
            end_values = component_end_resultants(
                raw if isinstance(raw, (list, tuple)) else [],
                component,
            )
            if end_values is None:
                skipped += 1
                continue
            rows.append(
                (
                    tag,
                    float(end_values[0]),
                    float(end_values[1]),
                    max(abs(float(end_values[0])), abs(float(end_values[1]))),
                    "end-force fallback",
                )
            )
            source_counts["end-force fallback"] = (
                source_counts.get("end-force fallback", 0) + 1
            )

        self.element_table.setRowCount(len(rows))
        for row, (tag, value_i, value_j, maximum, _source) in enumerate(rows):
            item = QTableWidgetItem(str(tag))
            item.setData(Qt.UserRole, tag)
            self.element_table.setItem(row, 0, item)
            self.element_table.setItem(
                row, 1, QTableWidgetItem(f"{value_i:.6g}")
            )
            self.element_table.setItem(
                row, 2, QTableWidgetItem(f"{value_j:.6g}")
            )
            self.element_table.setItem(
                row,
                3,
                QTableWidgetItem(f"{maximum:.6g}"),
            )

        if rows:
            details = ", ".join(
                f"{source}: {count}"
                for source, count in sorted(source_counts.items())
            )
            note = (
                f"{component}: {len(rows)} member(s). "
                f"Sources — {details}."
            )
            if skipped:
                note += f" {skipped} element(s) had no usable frame result."
            self.element_info.setText(note)
        else:
            self.element_info.setText(
                "No local member-force result is available for this job."
            )

    def _update_pushover_plot(self) -> None:
        x, y, control_node, control_dof = pushover_capacity_curve(
            self._result
        )
        if not x or not y:
            analysis = self._result.get("analysis", {})
            analysis_type = (
                str(analysis.get("type", ""))
                if isinstance(analysis, dict)
                else ""
            )
            if analysis_type == "Pushover":
                self.pushover_info.setText(
                    "Pushover result is present, but no complete "
                    "control-displacement/base-shear history is available."
                )
            else:
                self.pushover_info.setText(
                    "Run or select a Pushover analysis to view the "
                    "capacity curve."
                )
            self.pushover_metrics.setText(
                "Vpeak: -   u@Vpeak: -   ufinal: -"
            )
            self.pushover_plot.set_series([], [])
            return

        dof_names = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        dof_name = (
            dof_names[control_dof - 1]
            if control_dof in range(1, 7)
            else f"DOF {control_dof}"
        )
        peak_index = max(
            range(len(y)),
            key=lambda index: abs(y[index]),
        )
        self.pushover_info.setText(
            f"Control node {control_node if control_node is not None else '-'} "
            f"· {dof_name} · X = control displacement · "
            "Y = applied base shear (-Σ support reactions)"
        )
        self.pushover_metrics.setText(
            f"Points: {len(x)}   "
            f"Vpeak: {y[peak_index]:.6g}   "
            f"u@Vpeak: {x[peak_index]:.6g}   "
            f"ufinal: {x[-1]:.6g}"
        )
        self.pushover_plot.set_series(x, y)

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
