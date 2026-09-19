from __future__ import annotations

import csv
import math
from typing import Any

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
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
from ..postprocess import (
    component_end_resultants,
    convergence_series,
    convergence_steps,
    convergence_summary,
    cyclic_hysteresis_curve,
    cyclic_hysteresis_metrics,
    fiber_response_element_tags,
    fiber_response_range,
    fiber_response_sections,
    fiber_state_element_tags,
    fiber_state_sections,
    pushover_capacity_curve,
    time_history_node_tags,
    time_history_series,
)


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


class LiveConvergencePlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._attempts: list[dict[str, Any]] = []
        self._tolerance: float | None = None
        self._empty_message = "Live convergence monitor idle"
        self.setMinimumHeight(190)

    def set_attempts(
        self,
        attempts: list[dict[str, Any]],
        tolerance: float | None,
    ) -> None:
        self._attempts = [
            {
                "algorithm": str(attempt.get("algorithm", "-")),
                "values": [
                    (int(item[0]), float(item[1]))
                    for item in attempt.get("values", [])
                    if (
                        isinstance(item, (list, tuple))
                        and len(item) >= 2
                        and math.isfinite(float(item[1]))
                    )
                ],
            }
            for attempt in attempts
            if isinstance(attempt, dict)
        ]
        try:
            parsed_tolerance = (
                float(tolerance)
                if tolerance is not None
                else None
            )
        except (TypeError, ValueError):
            parsed_tolerance = None
        self._tolerance = (
            parsed_tolerance
            if parsed_tolerance is not None
            and math.isfinite(parsed_tolerance)
            and parsed_tolerance > 0.0
            else None
        )
        self.update()

    def clear(self) -> None:
        self._attempts = []
        self._tolerance = None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        attempt_values = [
            (
                attempt.get("algorithm", "-"),
                [
                    (iteration, norm)
                    for iteration, norm in attempt.get("values", [])
                    if norm > 0.0 and math.isfinite(norm)
                ],
            )
            for attempt in self._attempts
        ]
        attempt_values = [
            (algorithm, values)
            for algorithm, values in attempt_values
            if values
        ]
        if not attempt_values:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                self._empty_message,
            )
            return

        norms = [
            norm
            for _algorithm, values in attempt_values
            for _iteration, norm in values
        ]
        if self._tolerance is not None:
            norms.append(self._tolerance)

        logs = [math.log10(max(value, 1.0e-300)) for value in norms]
        log_min = min(logs)
        log_max = max(logs)
        if abs(log_max - log_min) < 1.0e-12:
            log_min -= 1.0
            log_max += 1.0
        else:
            pad = 0.12 * (log_max - log_min)
            log_min -= pad
            log_max += pad

        margin_left, margin_right = 62.0, 18.0
        margin_top, margin_bottom = 26.0, 34.0
        left = margin_left
        right = max(left + 1.0, self.width() - margin_right)
        top = margin_top
        bottom = max(top + 1.0, self.height() - margin_bottom)

        total_points = sum(len(values) for _, values in attempt_values)
        gaps = max(0, len(attempt_values) - 1)
        xmax = max(total_points + gaps - 1, 1)

        def point(index: float, norm: float) -> QPointF:
            px = left + index / xmax * (right - left)
            py = bottom - (
                math.log10(max(norm, 1.0e-300)) - log_min
            ) / (log_max - log_min) * (bottom - top)
            return QPointF(px, py)

        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(int(left), int(bottom), int(right), int(bottom))
        painter.drawLine(int(left), int(top), int(left), int(bottom))

        if self._tolerance is not None:
            tol_y = point(0.0, self._tolerance).y()
            painter.setPen(QPen(QColor("#c0392b"), 1, Qt.DashLine))
            painter.drawLine(
                int(left),
                int(tol_y),
                int(right),
                int(tol_y),
            )
            painter.drawText(
                int(left + 4),
                int(max(top + 12, tol_y - 4)),
                f"tol={self._tolerance:.3e}",
            )

        palette = (
            QColor("#2f80ed"),
            QColor("#f2994a"),
            QColor("#9b51e0"),
            QColor("#219653"),
        )
        offset = 0
        for attempt_index, (algorithm, values) in enumerate(attempt_values):
            color = palette[attempt_index % len(palette)]
            painter.setPen(QPen(color, 2))
            previous: QPointF | None = None
            for local_index, (_iteration, norm) in enumerate(values):
                x_index = offset + local_index
                current = point(x_index, norm)
                if previous is not None:
                    painter.drawLine(previous, current)
                painter.setBrush(color)
                painter.drawEllipse(current, 3.0, 3.0)
                previous = current

            first = point(offset, values[0][1])
            painter.setPen(color)
            painter.drawText(
                int(first.x() + 4),
                int(top + 12 + 14 * (attempt_index % 2)),
                algorithm,
            )
            offset += len(values) + 1

        painter.setPen(QColor("#526579"))
        painter.drawText(
            4,
            int(top + 8),
            f"1e{math.ceil(log_max):g}",
        )
        painter.drawText(
            4,
            int(bottom),
            f"1e{math.floor(log_min):g}",
        )
        painter.drawText(
            int(left),
            self.height() - 7,
            "Iterations / fallback attempts →",
        )


class FiberResponsePlot(QWidget):
    fiber_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._section: dict[str, Any] = {}
        self._quantity = "stress"
        self._screen_fibers: list[
            tuple[float, float, float, dict[str, Any], int]
        ] = []
        self.setMinimumHeight(220)

    def set_response(
        self,
        section: dict[str, Any] | None,
        quantity: str,
    ) -> None:
        self._section = dict(section or {})
        self._quantity = str(quantity).strip().lower()
        self._screen_fibers = []
        self.update()

    @staticmethod
    def _lerp(a: int, b: int, t: float) -> int:
        return int(round(a + (b - a) * max(0.0, min(1.0, t))))

    @classmethod
    def _response_color(
        cls,
        value: float,
        limit: float,
    ) -> QColor:
        if limit <= 1.0e-30:
            return QColor("#d9dee5")
        t = max(-1.0, min(1.0, value / limit))
        neutral = (238, 241, 245)
        if t < 0.0:
            end = (47, 128, 237)
            ratio = -t
        else:
            end = (214, 64, 69)
            ratio = t
        return QColor(
            cls._lerp(neutral[0], end[0], ratio),
            cls._lerp(neutral[1], end[1], ratio),
            cls._lerp(neutral[2], end[2], ratio),
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        fibers = self._section.get("fibers", [])
        if not isinstance(fibers, list) or not fibers:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No fiber response data",
            )
            return

        numeric: list[tuple[int, dict[str, Any], float, float, float]] = []
        values: list[float] = []
        for index, fiber in enumerate(fibers):
            if not isinstance(fiber, dict):
                continue
            try:
                y = float(fiber.get("y", 0.0))
                z = float(fiber.get("z", 0.0))
                area = max(float(fiber.get("area", 0.0)), 0.0)
            except (TypeError, ValueError):
                continue
            raw_value = fiber.get(self._quantity)
            try:
                value = float(raw_value) if raw_value is not None else math.nan
            except (TypeError, ValueError):
                value = math.nan
            numeric.append((index, fiber, y, z, area))
            if math.isfinite(value):
                values.append(value)

        if not numeric:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No valid fiber geometry",
            )
            return

        radii = [
            math.sqrt(area / math.pi) if area > 0.0 else 0.0
            for _, _, _, _, area in numeric
        ]
        ymin = min(item[2] - radius for item, radius in zip(numeric, radii))
        ymax = max(item[2] + radius for item, radius in zip(numeric, radii))
        zmin = min(item[3] - radius for item, radius in zip(numeric, radii))
        zmax = max(item[3] + radius for item, radius in zip(numeric, radii))

        if abs(ymax - ymin) < 1.0e-15:
            ymin -= 0.5
            ymax += 0.5
        if abs(zmax - zmin) < 1.0e-15:
            zmin -= 0.5
            zmax += 0.5

        margin_left, margin_right = 54.0, 24.0
        margin_top, margin_bottom = 24.0, 42.0
        available_w = max(self.width() - margin_left - margin_right, 1.0)
        available_h = max(self.height() - margin_top - margin_bottom, 1.0)
        scale = min(
            available_w / (ymax - ymin),
            available_h / (zmax - zmin),
        )
        drawing_w = (ymax - ymin) * scale
        drawing_h = (zmax - zmin) * scale
        x0 = margin_left + 0.5 * (available_w - drawing_w)
        y0 = margin_top + 0.5 * (available_h - drawing_h)

        limit = max((abs(value) for value in values), default=0.0)
        self._screen_fibers = []

        painter.setPen(QPen(QColor("#9aa9b8"), 1))
        for (index, fiber, y, z, area), physical_radius in zip(
            numeric,
            radii,
        ):
            px = x0 + (y - ymin) * scale
            py = y0 + (zmax - z) * scale
            radius = max(2.0, physical_radius * scale)
            raw_value = fiber.get(self._quantity)
            try:
                value = (
                    float(raw_value)
                    if raw_value is not None
                    else math.nan
                )
            except (TypeError, ValueError):
                value = math.nan
            color = (
                self._response_color(value, limit)
                if math.isfinite(value)
                else QColor("#c8ced6")
            )
            painter.setBrush(color)
            painter.drawEllipse(QPointF(px, py), radius, radius)
            self._screen_fibers.append(
                (px, py, radius, fiber, index)
            )

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor("#526579"))
        painter.drawText(
            6,
            16,
            (
                f"{self._quantity.title()} range: "
                f"{min(values):.4g} to {max(values):.4g}"
                if values
                else f"{self._quantity.title()}: unavailable"
            ),
        )
        painter.drawText(
            int(x0),
            self.height() - 10,
            "y →",
        )
        painter.drawText(
            6,
            int(y0 + 12),
            "z ↑",
        )

    def mousePressEvent(self, event) -> None:
        position = event.position()
        best: tuple[float, dict[str, Any], int] | None = None
        for px, py, radius, fiber, index in self._screen_fibers:
            distance = math.hypot(position.x() - px, position.y() - py)
            threshold = max(radius, 8.0)
            if distance <= threshold and (
                best is None or distance < best[0]
            ):
                best = (distance, fiber, index)
        if best is not None:
            payload = dict(best[1])
            payload["index"] = best[2]
            self.fiber_selected.emit(payload)
        super().mousePressEvent(event)


class ResultsPanel(QWidget):
    deformation_requested = Signal(float)
    mode_shape_requested = Signal(int, float)
    clear_overlay_requested = Signal()
    member_force_requested = Signal(str, float)
    node_contour_requested = Signal(str, str)
    hinge_state_requested = Signal()
    element_selected = Signal(int)
    job_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: dict[str, Any] = {}
        self._live_convergence_attempts: list[dict[str, Any]] = []
        self._live_convergence_step = 0
        self._live_convergence_total = 0
        self._live_convergence_test = ""
        self._live_convergence_tolerance: float | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 5, 6, 5)
        root.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)

        self._build_jobs_tab()
        self._build_convergence_tab()
        self._build_deformation_tab()
        self._build_mode_tab()
        self._build_node_tab()
        self._build_element_tab()
        self._build_fiber_tab()
        self._build_hinge_tab()
        self._build_pushover_tab()
        self._build_cyclic_tab()
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

    def _build_convergence_tab(self) -> None:
        page = QWidget()
        self.convergence_page = page
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        controls = QHBoxLayout()
        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_convergence_csv)
        controls.addWidget(export)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.live_convergence_status = QLabel(
            "Live monitor idle."
        )
        self.live_convergence_status.setWordWrap(True)
        layout.addWidget(self.live_convergence_status)

        self.live_convergence_plot = LiveConvergencePlot()
        layout.addWidget(self.live_convergence_plot)

        self.convergence_info = QLabel(
            "Run a non-modal analysis to inspect solver convergence."
        )
        self.convergence_info.setWordWrap(True)
        layout.addWidget(self.convergence_info)

        self.convergence_summary_label = QLabel(
            "Steps: -   Recovered: -   Failed: -   Max iterations: -"
        )
        self.convergence_summary_label.setWordWrap(True)
        layout.addWidget(self.convergence_summary_label)

        layout.addWidget(QLabel("Iterations by step"))
        self.convergence_iterations_plot = TimeHistoryPlot(
            empty_message="No convergence iteration data"
        )
        self.convergence_iterations_plot.setMinimumHeight(110)
        layout.addWidget(self.convergence_iterations_plot)

        layout.addWidget(QLabel("Final convergence norm by step"))
        self.convergence_norm_plot = TimeHistoryPlot(
            empty_message="No convergence norm data"
        )
        self.convergence_norm_plot.setMinimumHeight(110)
        layout.addWidget(self.convergence_norm_plot)

        self.convergence_table = QTableWidget(0, 10)
        self.convergence_table.setHorizontalHeaderLabels(
            [
                "Step",
                "Status",
                "Algorithm",
                "Last iter",
                "Total iter",
                "Norm",
                "Attempts",
                "Cutbacks",
                "Min |step|",
                "Time / Load factor",
            ]
        )
        self.convergence_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.convergence_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.convergence_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.convergence_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.convergence_table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.convergence_table.cellClicked.connect(
            self._convergence_row_clicked
        )
        layout.addWidget(self.convergence_table, 1)

        self.convergence_attempt_info = QLabel(
            "Select a step to inspect primary/fallback attempts."
        )
        self.convergence_attempt_info.setWordWrap(True)
        layout.addWidget(self.convergence_attempt_info)

        self.tabs.addTab(page, "Convergence")

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

    def _build_fiber_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Element:"))
        self.fiber_element = QComboBox()
        self.fiber_element.currentIndexChanged.connect(
            self._fiber_element_changed
        )
        controls.addWidget(self.fiber_element)

        controls.addWidget(QLabel("Section/IP:"))
        self.fiber_section = QComboBox()
        self.fiber_section.currentIndexChanged.connect(
            self._update_fiber_view
        )
        controls.addWidget(self.fiber_section)

        controls.addWidget(QLabel("Quantity:"))
        self.fiber_quantity = QComboBox()
        self.fiber_quantity.addItems(["Stress", "Strain"])
        self.fiber_quantity.currentTextChanged.connect(
            self._update_fiber_view
        )
        controls.addWidget(self.fiber_quantity)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.fiber_info = QLabel(
            "Run a nonlinear beam-column model with a FiberSection "
            "to inspect final fiber stress/strain."
        )
        self.fiber_info.setWordWrap(True)
        layout.addWidget(self.fiber_info)

        self.fiber_plot = FiberResponsePlot()
        self.fiber_plot.fiber_selected.connect(
            self._fiber_selected
        )
        layout.addWidget(self.fiber_plot, 1)

        self.fiber_selected_info = QLabel(
            "Click a fiber to inspect material, stress and strain."
        )
        self.fiber_selected_info.setWordWrap(True)
        layout.addWidget(self.fiber_selected_info)

        self.tabs.addTab(page, "Fiber Response")

    def _build_hinge_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        controls = QHBoxLayout()
        show = QPushButton("Show States on Model")
        show.clicked.connect(self.hinge_state_requested.emit)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_overlay_requested.emit)
        controls.addWidget(show)
        controls.addWidget(clear)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.hinge_info = QLabel(
            "Fiber-based diagnostic states: Elastic → Nonlinear/near yield "
            "→ Yielding/softening → Plastic/crushing."
        )
        self.hinge_info.setWordWrap(True)
        layout.addWidget(self.hinge_info)

        self.hinge_table = QTableWidget(0, 6)
        self.hinge_table.setHorizontalHeaderLabels(
            [
                "Element",
                "IP",
                "x",
                "State",
                "Controlling material",
                "Controlling fiber",
            ]
        )
        self.hinge_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.hinge_table.horizontalHeader().setStretchLastSection(True)
        self.hinge_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hinge_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hinge_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hinge_table.cellClicked.connect(self._hinge_row_clicked)
        layout.addWidget(self.hinge_table)

        self.tabs.addTab(page, "Hinge / Yield States")

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

    def _build_cyclic_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        self.cyclic_info = QLabel(
            "Run a Cyclic analysis to plot applied base shear versus "
            "control displacement."
        )
        self.cyclic_info.setWordWrap(True)
        layout.addWidget(self.cyclic_info)

        self.cyclic_metrics = QLabel(
            "Peak |u|: -   Peak |V|: -   Hysteretic energy: -"
        )
        self.cyclic_metrics.setWordWrap(True)
        layout.addWidget(self.cyclic_metrics)

        self.cyclic_plot = TimeHistoryPlot(
            empty_message="No cyclic hysteresis data"
        )
        layout.addWidget(self.cyclic_plot, 1)

        self.cyclic_reversal_table = QTableWidget(0, 4)
        self.cyclic_reversal_table.setHorizontalHeaderLabels(
            ["Reversal", "u", "V", "|Ksec|"]
        )
        self.cyclic_reversal_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.cyclic_reversal_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.cyclic_reversal_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        layout.addWidget(self.cyclic_reversal_table)

        self.tabs.addTab(page, "Cyclic Hysteresis")

    def _build_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        row = QHBoxLayout()
        row.addWidget(QLabel("Node:"))
        self.history_node = QComboBox()
        self.history_node.currentIndexChanged.connect(
            self._update_history_plot
        )
        row.addWidget(self.history_node)

        row.addWidget(QLabel("Quantity:"))
        self.history_quantity = QComboBox()
        self.history_quantity.addItems(
            [
                "Displacement",
                "Velocity",
                "Acceleration",
                "Reaction",
                "Base shear",
            ]
        )
        self.history_quantity.currentTextChanged.connect(
            self._update_history_controls
        )
        row.addWidget(self.history_quantity)

        row.addWidget(QLabel("DOF:"))
        self.history_dof = QComboBox()
        self.history_dof.currentIndexChanged.connect(
            self._update_history_plot
        )
        row.addWidget(self.history_dof)

        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_history_csv)
        row.addWidget(export)
        row.addStretch(1)
        layout.addLayout(row)

        self.history_label = QLabel(
            "Run a non-modal analysis to populate time-history data."
        )
        self.history_label.setWordWrap(True)
        layout.addWidget(self.history_label)

        self.history_plot = TimeHistoryPlot()
        layout.addWidget(self.history_plot, 1)
        self.tabs.addTab(page, "Time History")
        self._update_history_controls()

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
        self.convergence_table.setRowCount(0)
        self._live_convergence_attempts = []
        self._live_convergence_step = 0
        self._live_convergence_total = 0
        self._live_convergence_test = ""
        self._live_convergence_tolerance = None
        self.live_convergence_status.setText("Live monitor idle.")
        self.live_convergence_plot.clear()
        self.convergence_iterations_plot.set_series([], [])
        self.convergence_norm_plot.set_series([], [])
        self.convergence_info.setText(
            "Run a non-modal analysis to inspect solver convergence."
        )
        self.convergence_summary_label.setText(
            "Steps: -   Recovered: -   Failed: -   Max iterations: -"
        )
        self.convergence_attempt_info.setText(
            "Select a step to inspect primary/fallback attempts."
        )
        self.node_table.setRowCount(0)
        self.element_table.setRowCount(0)
        self.element_info.setText(
            "Run a non-modal frame analysis to populate local member forces."
        )
        self.fiber_element.clear()
        self.fiber_section.clear()
        self.fiber_plot.set_response({}, "stress")
        self.fiber_info.setText(
            "Run a nonlinear beam-column model with a FiberSection "
            "to inspect final fiber stress/strain."
        )
        self.fiber_selected_info.setText(
            "Click a fiber to inspect material, stress and strain."
        )
        self.hinge_table.setRowCount(0)
        self.hinge_info.setText(
            "Fiber-based diagnostic states: Elastic → Nonlinear/near yield "
            "→ Yielding/softening → Plastic/crushing."
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
        self.cyclic_plot.set_series([], [])
        self.cyclic_reversal_table.setRowCount(0)
        self.cyclic_info.setText(
            "Run a Cyclic analysis to plot applied base shear versus "
            "control displacement."
        )
        self.cyclic_metrics.setText(
            "Peak |u|: -   Peak |V|: -   Hysteretic energy: -"
        )
        self.history_node.clear()
        self.history_label.setText(
            "Run a non-modal analysis to populate time-history data."
        )
        self.history_plot.set_series([], [])

    def _emit_mode(self) -> None:
        mode = self.mode_combo.currentData()
        if mode is None:
            return
        self.mode_shape_requested.emit(int(mode), self.mode_scale.value())

    def start_live_convergence(
        self,
        *,
        total: int,
        test: str,
        tolerance: float | None,
        algorithm: str,
    ) -> None:
        self._live_convergence_attempts = []
        self._live_convergence_step = 0
        self.tabs.setCurrentWidget(self.convergence_page)
        self._live_convergence_total = int(total)
        self._live_convergence_test = str(test)
        self._live_convergence_tolerance = tolerance
        self.live_convergence_plot.clear()
        self.live_convergence_status.setText(
            f"RUNNING · {self._live_convergence_test or 'Convergence test'} "
            f"· primary {algorithm or '-'}"
        )

    def begin_live_convergence_step(
        self,
        *,
        step: int,
        total: int,
        algorithm: str,
        test: str = "",
        tolerance: float | None = None,
    ) -> None:
        self._live_convergence_step = int(step)
        self._live_convergence_total = int(total)
        if test:
            self._live_convergence_test = str(test)
        if tolerance is not None:
            self._live_convergence_tolerance = float(tolerance)
        self._live_convergence_attempts = [
            {"algorithm": str(algorithm), "values": []}
        ]
        self.live_convergence_plot.set_attempts(
            self._live_convergence_attempts,
            self._live_convergence_tolerance,
        )
        self.live_convergence_status.setText(
            f"RUNNING · Step {step}/{total} · {algorithm} · "
            f"{self._live_convergence_test or 'test'}"
        )

    def begin_live_convergence_attempt(
        self,
        algorithm: str,
    ) -> None:
        algorithm = str(algorithm)
        if (
            self._live_convergence_attempts
            and self._live_convergence_attempts[-1].get("algorithm")
            == algorithm
            and not self._live_convergence_attempts[-1].get("values")
        ):
            return
        self._live_convergence_attempts.append(
            {"algorithm": algorithm, "values": []}
        )
        self.live_convergence_plot.set_attempts(
            self._live_convergence_attempts,
            self._live_convergence_tolerance,
        )
        self.live_convergence_status.setText(
            f"RUNNING · Step {self._live_convergence_step}/"
            f"{self._live_convergence_total} · fallback {algorithm}"
        )

    def append_live_convergence_iteration(
        self,
        *,
        iteration: int,
        norm: float,
        tolerance: float | None = None,
        test: str = "",
        algorithm: str = "",
    ) -> None:
        if tolerance is not None:
            self._live_convergence_tolerance = float(tolerance)
        if test:
            self._live_convergence_test = str(test)
        if not self._live_convergence_attempts:
            self._live_convergence_attempts.append(
                {
                    "algorithm": str(algorithm or "-"),
                    "values": [],
                }
            )
        attempt = self._live_convergence_attempts[-1]
        values = attempt.setdefault("values", [])
        point = (int(iteration), float(norm))
        if values and int(values[-1][0]) == point[0]:
            values[-1] = point
        else:
            values.append(point)
        self.live_convergence_plot.set_attempts(
            self._live_convergence_attempts,
            self._live_convergence_tolerance,
        )
        tol = self._live_convergence_tolerance
        status = (
            "CONVERGED"
            if tol is not None and norm <= tol
            else "ITERATING"
        )
        self.live_convergence_status.setText(
            f"{status} · Step {self._live_convergence_step}/"
            f"{self._live_convergence_total} · "
            f"{attempt.get('algorithm', algorithm or '-')} · "
            f"iter {iteration} · norm={norm:.3e}"
            + (
                f" · tol={tol:.3e}"
                if tol is not None
                else ""
            )
        )

    def set_live_convergence_message(self, message: str) -> None:
        self.live_convergence_status.setText(str(message))

    def finish_live_convergence(self, status: str) -> None:
        if self._live_convergence_step <= 0:
            return
        final_status = str(status)
        if (
            final_status == "CONVERGED"
            and len(self._live_convergence_attempts) > 1
        ):
            final_status = "RECOVERED"
        self.live_convergence_status.setText(
            f"{final_status} · Step {self._live_convergence_step}/"
            f"{self._live_convergence_total}"
        )

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

        self._populate_convergence_dashboard()
        self._populate_node_table()
        self._populate_element_table()
        self._populate_fiber_elements()
        self._populate_hinge_table()
        self._populate_history_nodes()
        self._update_pushover_plot()
        self._update_cyclic_plot()
        self._update_history_plot()

    def _populate_convergence_dashboard(self) -> None:
        rows = convergence_steps(self._result)
        summary = convergence_summary(self._result)
        analysis = self._result.get("analysis", {})
        analysis_type = (
            str(analysis.get("type", ""))
            if isinstance(analysis, dict)
            else ""
        )

        if not rows:
            self.convergence_table.setRowCount(0)
            self.convergence_iterations_plot.set_series([], [])
            self.convergence_norm_plot.set_series([], [])
            self.convergence_info.setText(
                "No iterative convergence history is available for this "
                "result."
                if analysis_type
                else "Run a non-modal analysis to inspect solver convergence."
            )
            self.convergence_summary_label.setText(
                "Steps: -   Recovered: -   Failed: -   Max iterations: -"
            )
            self.convergence_attempt_info.setText(
                "Select a step to inspect primary/fallback attempts."
            )
            return

        tolerance = summary.get("tolerance")
        tolerance_text = (
            f"{float(tolerance):.3e}"
            if tolerance is not None
            else "-"
        )
        configured_max = summary.get("configured_max_iterations")
        adaptive_text = (
            " · adaptive ON "
            f"(cut={summary.get('cutback_factor')}, "
            f"min={summary.get('minimum_factor')}, "
            f"grow={summary.get('growth_factor')})"
            if summary.get("adaptive_step")
            else " · adaptive OFF"
        )
        self.convergence_info.setText(
            f"{analysis_type or 'Analysis'} · "
            f"Test {summary.get('test') or '-'} · "
            f"tol={tolerance_text} · "
            f"configured max iter={configured_max if configured_max is not None else '-'} · "
            f"primary={summary.get('primary_algorithm') or '-'}"
            + adaptive_text
        )

        algorithms = ", ".join(summary.get("algorithms", [])) or "-"
        worst_norm = summary.get("worst_norm")
        worst_step = summary.get("worst_step")
        worst_text = (
            f"{float(worst_norm):.3e} at step {worst_step}"
            if worst_norm is not None
            else "-"
        )
        minimum_step = summary.get("minimum_step_size")
        minimum_step_text = (
            f"{float(minimum_step):.6g}"
            if minimum_step is not None
            else "-"
        )
        self.convergence_summary_label.setText(
            f"Steps: {summary['steps']} · "
            f"Converged: {summary['converged']} · "
            f"Recovered: {summary['recovered']} · "
            f"Failed: {summary['failed']} · "
            f"Attempts: {summary['total_attempts']} · "
            f"Cutbacks: {summary.get('total_cutbacks', 0)} · "
            f"Min |step|: {minimum_step_text} · "
            f"Max iterations used: {summary['max_iterations_used']} · "
            f"Worst norm: {worst_text} · Algorithms: {algorithms}"
        )

        self.convergence_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            attempts = row.get("attempts", [])
            attempt_count = len(attempts) if isinstance(attempts, list) else 0
            norm = row.get("norm")
            norm_text = "-"
            if norm is not None:
                try:
                    norm_text = f"{float(norm):.3e}"
                except (TypeError, ValueError):
                    norm_text = str(norm)
            time_value = row.get("time")
            time_text = "-"
            if time_value is not None:
                try:
                    time_text = f"{float(time_value):.7g}"
                except (TypeError, ValueError):
                    time_text = str(time_value)
            min_step = row.get("min_step_size_used")
            min_step_text = "-"
            if min_step is not None:
                try:
                    min_step_text = f"{float(min_step):.6g}"
                except (TypeError, ValueError):
                    min_step_text = str(min_step)
            values = [
                str(row.get("step", "-")),
                str(row.get("status", "-")),
                str(row.get("algorithm", "-")),
                str(row.get("iterations", "-")),
                str(row.get("total_iterations", row.get("iterations", "-"))),
                norm_text,
                str(attempt_count),
                str(row.get("cutbacks", 0) or 0),
                min_step_text,
                time_text,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, int(row.get("step", 0)))
                self.convergence_table.setItem(
                    row_index,
                    column,
                    item,
                )

        x_iter, y_iter = convergence_series(
            self._result,
            "iterations",
        )
        x_norm, y_norm = convergence_series(
            self._result,
            "norm",
        )
        self.convergence_iterations_plot.set_series(x_iter, y_iter)
        self.convergence_norm_plot.set_series(x_norm, y_norm)

    def _convergence_row_clicked(self, row: int, column: int) -> None:
        item = self.convergence_table.item(row, 0)
        if item is None:
            return
        step = item.data(Qt.UserRole)
        records = convergence_steps(self._result)
        record = next(
            (
                candidate
                for candidate in records
                if int(candidate.get("step", -1)) == int(step)
            ),
            None,
        )
        if not isinstance(record, dict):
            return

        attempts = record.get("attempts", [])
        if isinstance(attempts, list):
            plot_attempts: list[dict[str, Any]] = []
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                history = attempt.get("norm_history", [])
                values = []
                if isinstance(history, (list, tuple)):
                    for iteration, raw_norm in enumerate(history, start=1):
                        try:
                            norm = float(raw_norm)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(norm):
                            values.append((iteration, norm))
                plot_attempts.append({
                    "algorithm": str(attempt.get("algorithm", "-")),
                    "values": values,
                })
            convergence = self._result.get("convergence", {})
            tolerance = (
                convergence.get("tolerance")
                if isinstance(convergence, dict)
                else None
            )
            self.live_convergence_plot.set_attempts(
                plot_attempts,
                tolerance,
            )
            self.live_convergence_status.setText(
                f"POST-RUN · Selected step {step}"
            )
        if not isinstance(attempts, list) or not attempts:
            self.convergence_attempt_info.setText(
                f"Step {step}: no attempt details available."
            )
            return

        labels: list[str] = []
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            success = bool(attempt.get("success"))
            norm = attempt.get("norm")
            norm_text = "-"
            if norm is not None:
                try:
                    norm_text = f"{float(norm):.3e}"
                except (TypeError, ValueError):
                    norm_text = str(norm)
            increment = attempt.get("increment")
            increment_text = ""
            if increment is not None:
                try:
                    increment_text = f", Δ={float(increment):.6g}"
                except (TypeError, ValueError):
                    increment_text = f", Δ={increment}"
            labels.append(
                f"{attempt.get('algorithm', '-')} "
                f"{'✓' if success else '✗'} "
                f"(iter={attempt.get('iterations', '-')}, "
                f"norm={norm_text}, code={attempt.get('code', '-')}"
                f"{increment_text})"
            )
        self.convergence_attempt_info.setText(
            f"Step {step}: " + " → ".join(labels)
        )

    def _export_convergence_csv(self) -> None:
        rows = convergence_steps(self._result)
        if not rows:
            self.convergence_attempt_info.setText(
                "No convergence data is available to export."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Convergence History",
            "convergence_history.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "step",
                    "status",
                    "algorithm",
                    "iterations",
                    "norm",
                    "recovered",
                    "time_or_load_factor",
                    "attempt_count",
                    "attempt_chain",
                ]
            )
            for row in rows:
                attempts = row.get("attempts", [])
                attempts = attempts if isinstance(attempts, list) else []
                chain = " -> ".join(
                    (
                        f"{attempt.get('algorithm', '-')}:"
                        f"{'ok' if attempt.get('success') else 'fail'}:"
                        f"iter={attempt.get('iterations', '-')}:"
                        f"norm={attempt.get('norm', '-')}:"
                        f"code={attempt.get('code', '-')}"
                    )
                    for attempt in attempts
                    if isinstance(attempt, dict)
                )
                writer.writerow(
                    [
                        row.get("step"),
                        row.get("status"),
                        row.get("algorithm"),
                        row.get("iterations"),
                        row.get("norm"),
                        row.get("recovered"),
                        row.get("time"),
                        len(attempts),
                        chain,
                    ]
                )
        self.convergence_attempt_info.setText(
            f"Exported {len(rows)} convergence step(s) to {path}"
        )

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

    def _populate_hinge_table(self) -> None:
        rows: list[tuple[int, dict[str, Any]]] = []
        for tag in fiber_state_element_tags(self._result):
            for section in fiber_state_sections(self._result, tag):
                rows.append((tag, section))

        self.hinge_table.setRowCount(len(rows))
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for row, (tag, section) in enumerate(rows):
            severity = int(section.get("severity", -1))
            if severity in counts:
                counts[severity] += 1
            controlling = section.get("controlling_fiber")
            controlling = controlling if isinstance(controlling, dict) else {}
            values = [
                str(tag),
                str(section.get("number", "-")),
                f"{float(section.get('location', 0.0)):.6g}",
                str(section.get("state", "Unknown")),
                (
                    f"{controlling.get('material_type', '-')} "
                    f"[{controlling.get('material_tag', '-')}]"
                ),
                (
                    f"#{int(controlling.get('fiber_index', -1)) + 1} · "
                    f"strain={controlling.get('strain', '-')}"
                    if controlling
                    else "-"
                ),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, int(tag))
                self.hinge_table.setItem(row, column, item)

        total = len(rows)
        if total:
            self.hinge_info.setText(
                f"{total} integration point(s) · "
                f"Elastic {counts[0]} · Nonlinear/near yield {counts[1]} · "
                f"Yielding/softening {counts[2]} · "
                f"Plastic/crushing {counts[3]}. "
                "States are material-based diagnostics, not code acceptance checks."
            )
        else:
            self.hinge_info.setText(
                "No fiber-state summary is available. Run a nonlinear "
                "FiberSection analysis first."
            )

    def _hinge_row_clicked(self, row: int, column: int) -> None:
        item = self.hinge_table.item(row, 0)
        if item is None:
            return
        tag = item.data(Qt.UserRole)
        if tag is not None:
            self.element_selected.emit(int(tag))

    def _populate_fiber_elements(self) -> None:
        previous = self.fiber_element.currentData()
        tags = fiber_response_element_tags(self._result)
        self.fiber_element.blockSignals(True)
        self.fiber_element.clear()
        for tag in tags:
            self.fiber_element.addItem(str(tag), int(tag))
        if previous is not None:
            index = self.fiber_element.findData(previous)
            if index >= 0:
                self.fiber_element.setCurrentIndex(index)
        self.fiber_element.blockSignals(False)
        self._fiber_element_changed()

    def _fiber_element_changed(self) -> None:
        element_data = self.fiber_element.currentData()
        self.fiber_section.blockSignals(True)
        self.fiber_section.clear()
        if element_data is not None:
            sections = fiber_response_sections(
                self._result,
                int(element_data),
            )
            for index, section in enumerate(sections):
                number = int(section.get("number", index + 1))
                try:
                    location = float(section.get("location", 0.0))
                except (TypeError, ValueError):
                    location = 0.0
                self.fiber_section.addItem(
                    f"IP {number} · x={location:.5g}",
                    index,
                )
        self.fiber_section.blockSignals(False)
        if element_data is not None:
            self.element_selected.emit(int(element_data))
        self._update_fiber_view()

    def _current_fiber_section(self) -> dict[str, Any]:
        element_data = self.fiber_element.currentData()
        section_index = self.fiber_section.currentData()
        if element_data is None or section_index is None:
            return {}
        sections = fiber_response_sections(
            self._result,
            int(element_data),
        )
        index = int(section_index)
        if index < 0 or index >= len(sections):
            return {}
        return sections[index]

    def _update_fiber_view(self) -> None:
        section = self._current_fiber_section()
        quantity = self.fiber_quantity.currentText().lower()
        self.fiber_plot.set_response(section, quantity)
        self.fiber_selected_info.setText(
            "Click a fiber to inspect material, stress and strain."
        )

        if not section:
            self.fiber_info.setText(
                "No fiber response is available for the selected result."
            )
            return

        minimum, maximum = fiber_response_range(section, quantity)
        fibers = section.get("fibers", [])
        valid = sum(
            isinstance(fiber, dict)
            and fiber.get(quantity) is not None
            for fiber in fibers
        )
        element_tag = self.fiber_element.currentData()
        number = section.get("number", "-")
        location = section.get("location", "-")
        range_text = (
            f"{minimum:.6g} … {maximum:.6g}"
            if minimum is not None and maximum is not None
            else "unavailable"
        )
        self.fiber_info.setText(
            f"Element {element_tag} · IP {number} · x={location} · "
            f"{len(fibers)} fiber(s), {valid} response(s) · "
            f"{quantity} range: {range_text}"
        )

    def _fiber_selected(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        def numeric(name: str) -> str:
            raw = payload.get(name)
            if raw is None:
                return "-"
            try:
                return f"{float(raw):.7g}"
            except (TypeError, ValueError):
                return str(raw)

        self.fiber_selected_info.setText(
            f"Fiber #{int(payload.get('index', 0)) + 1} · "
            f"Material {payload.get('material_tag', '-')} · "
            f"y={numeric('y')} · z={numeric('z')} · "
            f"A={numeric('area')} · "
            f"stress={numeric('stress')} · "
            f"strain={numeric('strain')}"
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

    def _populate_history_nodes(self) -> None:
        previous = self.history_node.currentData()
        tags = time_history_node_tags(self._result)
        self.history_node.blockSignals(True)
        self.history_node.clear()
        for tag in tags:
            self.history_node.addItem(str(tag), int(tag))
        if previous is not None:
            index = self.history_node.findData(previous)
            if index >= 0:
                self.history_node.setCurrentIndex(index)
        self.history_node.blockSignals(False)

    def _update_history_controls(self) -> None:
        quantity = self.history_quantity.currentText()
        labels = {
            "Displacement": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
            "Velocity": ["VX", "VY", "VZ", "WX", "WY", "WZ"],
            "Acceleration": ["AX", "AY", "AZ", "AlphaX", "AlphaY", "AlphaZ"],
            "Reaction": ["FX", "FY", "FZ", "MX", "MY", "MZ"],
            "Base shear": ["X", "Y", "Z"],
        }.get(quantity, ["DOF 1"])

        previous_index = max(self.history_dof.currentIndex(), 0)
        self.history_dof.blockSignals(True)
        self.history_dof.clear()
        self.history_dof.addItems(labels)
        self.history_dof.setCurrentIndex(
            min(previous_index, len(labels) - 1)
        )
        self.history_dof.blockSignals(False)
        self.history_node.setEnabled(quantity != "Base shear")
        self._update_history_plot()

    def _history_selection(
        self,
    ) -> tuple[list[float], list[float], str, int | None, int]:
        quantity = self.history_quantity.currentText()
        node_data = self.history_node.currentData()
        node_tag = int(node_data) if node_data is not None else None
        dof = self.history_dof.currentIndex() + 1
        time, values = time_history_series(
            self._result,
            quantity,
            node_tag=node_tag,
            dof=dof,
        )
        return time, values, quantity, node_tag, dof

    def _update_cyclic_plot(self) -> None:
        x, y, control_node, control_dof = cyclic_hysteresis_curve(
            self._result
        )
        if not x or not y:
            analysis = self._result.get("analysis", {})
            analysis_type = (
                str(analysis.get("type", ""))
                if isinstance(analysis, dict)
                else ""
            )
            if analysis_type == "Cyclic":
                self.cyclic_info.setText(
                    "Cyclic result is present, but no complete "
                    "control-displacement/base-shear history is available."
                )
            else:
                self.cyclic_info.setText(
                    "Run or select a Cyclic analysis to view hysteresis."
                )
            self.cyclic_metrics.setText(
                "Peak |u|: -   Peak |V|: -   Hysteretic energy: -"
            )
            self.cyclic_plot.set_series([], [])
            self.cyclic_reversal_table.setRowCount(0)
            return

        metrics = cyclic_hysteresis_metrics(x, y)
        dof_names = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        dof_name = (
            dof_names[control_dof - 1]
            if control_dof in range(1, 7)
            else f"DOF {control_dof}"
        )
        self.cyclic_info.setText(
            f"Control node {control_node if control_node is not None else '-'} "
            f"· {dof_name} · X = control displacement · "
            "Y = applied base shear (-Σ support reactions)"
        )

        energy = metrics.get("dissipated_energy")
        if energy is None:
            energy_text = (
                f"path work={abs(float(metrics.get('signed_work', 0.0))):.6g} "
                "(protocol not closed)"
            )
        else:
            energy_text = f"{float(energy):.6g}"

        self.cyclic_metrics.setText(
            f"Peak |u|: {float(metrics['max_abs_displacement']):.6g}   "
            f"Peak |V|: {float(metrics['max_abs_force']):.6g}   "
            f"Hysteretic energy: {energy_text}"
        )
        self.cyclic_plot.set_series(x, y)

        reversals = metrics.get("reversals", [])
        if not isinstance(reversals, list):
            reversals = []
        self.cyclic_reversal_table.setRowCount(len(reversals))
        for row, reversal in enumerate(reversals, start=0):
            if not isinstance(reversal, dict):
                continue
            stiffness = reversal.get("secant_stiffness")
            stiffness_text = (
                f"{float(stiffness):.6g}"
                if stiffness is not None and math.isfinite(float(stiffness))
                else "-"
            )
            values = [
                str(row + 1),
                f"{float(reversal.get('displacement', 0.0)):.6g}",
                f"{float(reversal.get('force', 0.0)):.6g}",
                stiffness_text,
            ]
            for column, value in enumerate(values):
                self.cyclic_reversal_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _update_history_plot(self) -> None:
        time, values, quantity, node_tag, dof = self._history_selection()
        dof_label = self.history_dof.currentText() or f"DOF {dof}"

        if time and values:
            peak_index = max(
                range(len(values)),
                key=lambda index: abs(values[index]),
            )
            target = (
                "Base"
                if quantity == "Base shear"
                else f"Node {node_tag}"
            )
            note = (
                f"{target} · {quantity} {dof_label} · "
                f"Points: {len(values)} · "
                f"Peak: {values[peak_index]:.6g} at t={time[peak_index]:.6g} · "
                f"Final: {values[-1]:.6g}"
            )
            if quantity == "Base shear":
                note += " · sign = -Σ support reactions"
            elif quantity == "Acceleration":
                note += (
                    " · OpenSees nodal acceleration "
                    "(UniformExcitation response is relative)"
                )
            self.history_label.setText(note)
        else:
            target = (
                "base"
                if quantity == "Base shear"
                else (
                    f"node {node_tag}"
                    if node_tag is not None
                    else "selected node"
                )
            )
            self.history_label.setText(
                f"No {quantity.lower()} history is available for {target} "
                f"at {dof_label}."
            )

        self.history_plot.set_series(time, values)

    def _export_history_csv(self) -> None:
        time, values, quantity, node_tag, dof = self._history_selection()
        if not time or not values:
            self.history_label.setText(
                "No plotted time-history data is available to export."
            )
            return

        dof_label = self.history_dof.currentText() or f"DOF{dof}"
        target = (
            "base"
            if quantity == "Base shear"
            else f"node_{node_tag}"
        )
        safe_quantity = quantity.lower().replace(" ", "_")
        suggested = (
            f"{target}_{safe_quantity}_{dof_label.lower()}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Time History",
            suggested,
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "time",
                    (
                        f"{quantity} {dof_label}"
                        if node_tag is None
                        else f"Node {node_tag} {quantity} {dof_label}"
                    ),
                ]
            )
            writer.writerows(zip(time, values))
        self.history_label.setText(
            f"Exported {len(values)} time-history point(s) to {path}"
        )
