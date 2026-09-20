from __future__ import annotations

import csv
import math
from typing import Any

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..jobs import JobRecord
from ..motion import (
    available_modal_modes,
    motion_frame,
    motion_info,
)
from ..postprocess import (
    component_end_resultants,
    convergence_steps,
    convergence_trace,
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
    test_column_fiber_history_catalog,
    test_column_moment_curvature_curve,
    test_column_response_summary,
    test_column_rotation_decomposition,
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
        self._marker_index: int | None = None
        self.setMinimumHeight(140)

    def set_series(self, x: list[float], y: list[float]) -> None:
        self._x = list(x)
        self._y = list(y)
        if (
            self._marker_index is not None
            and self._marker_index >= min(len(self._x), len(self._y))
        ):
            self._marker_index = None
        self.update()

    def set_marker(self, index: int | None) -> None:
        self._marker_index = (
            None if index is None else max(0, int(index))
        )
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

        marker_index = self._marker_index
        if (
            marker_index is not None
            and marker_index < len(self._x)
            and marker_index < len(self._y)
        ):
            marker = point(
                self._x[marker_index],
                self._y[marker_index],
            )
            painter.setPen(QPen(QColor("#c62828"), 2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(marker, 5.0, 5.0)

        painter.setPen(QColor("#526579"))
        painter.drawText(4, top + 8, f"{ymax:.3g}")
        painter.drawText(4, bottom, f"{ymin:.3g}")
        painter.drawText(left, self.height() - 7, f"{xmin:.3g}")
        painter.drawText(right - 35, self.height() - 7, f"{xmax:.3g}")


class ConvergenceOverviewPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._x: list[float] = []
        self._norm: list[float] = []
        self._criterion: float | None = None
        self._cutbacks: list[float] = []
        self._converged: list[float] = []
        self._show_norm = True
        self._show_criterion = True
        self._show_cutbacks = True
        self._show_converged = True
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

    def set_trace(
        self,
        x: list[float],
        norm: list[float],
        *,
        criterion: float | None,
        cutbacks: list[float],
        converged: list[float],
    ) -> None:
        self._x = list(x)
        self._norm = list(norm)
        self._criterion = criterion
        self._cutbacks = list(cutbacks)
        self._converged = list(converged)
        self.update()

    def clear(self) -> None:
        self.set_trace(
            [],
            [],
            criterion=None,
            cutbacks=[],
            converged=[],
        )

    def set_display_options(
        self,
        *,
        norm: bool,
        criterion: bool,
        cutbacks: bool,
        converged: bool,
    ) -> None:
        self._show_norm = bool(norm)
        self._show_criterion = bool(criterion)
        self._show_cutbacks = bool(cutbacks)
        self._show_converged = bool(converged)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        values = [
            abs(float(value))
            for value in self._norm
            if math.isfinite(float(value)) and float(value) != 0.0
        ]
        if (
            self._criterion is not None
            and math.isfinite(float(self._criterion))
            and float(self._criterion) > 0.0
        ):
            values.append(abs(float(self._criterion)))

        if not self._x or not values:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No convergence trace",
            )
            return

        margin_left = 58.0
        margin_right = 18.0
        margin_top = 26.0
        margin_bottom = 30.0
        left = margin_left
        right = max(left + 1.0, self.width() - margin_right)
        top = margin_top
        bottom = max(top + 1.0, self.height() - margin_bottom)

        xmin = 1.0
        xmax = max(max(self._x), 1.0)
        if xmax <= xmin:
            xmax = xmin + 1.0

        log_values = [
            math.log10(max(value, 1.0e-300))
            for value in values
        ]
        log_min = min(log_values)
        log_max = max(log_values)
        if abs(log_max - log_min) < 1.0e-12:
            log_min -= 1.0
            log_max += 1.0
        else:
            pad = 0.08 * (log_max - log_min)
            log_min -= pad
            log_max += pad

        def px(x: float) -> float:
            return left + (x - xmin) / (xmax - xmin) * (right - left)

        def py(value: float) -> float:
            log_value = math.log10(max(abs(value), 1.0e-300))
            return bottom - (
                log_value - log_min
            ) / (log_max - log_min) * (bottom - top)

        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(int(left), int(bottom), int(right), int(bottom))
        painter.drawLine(int(left), int(top), int(left), int(bottom))

        if self._show_cutbacks:
            painter.setPen(QPen(QColor("#e74c3c"), 1, Qt.DashLine))
            for x in self._cutbacks:
                xx = px(float(x))
                painter.drawLine(
                    int(xx),
                    int(top),
                    int(xx),
                    int(bottom),
                )

        if self._show_converged:
            painter.setPen(QPen(QColor("#2ecc71"), 1, Qt.DashLine))
            for x in self._converged:
                xx = px(float(x))
                painter.drawLine(
                    int(xx),
                    int(top),
                    int(xx),
                    int(bottom),
                )

        if self._show_criterion and self._criterion is not None:
            criterion = abs(float(self._criterion))
            if criterion > 0.0 and math.isfinite(criterion):
                yy = py(criterion)
                painter.setPen(QPen(QColor("#00bcd4"), 2))
                painter.drawLine(
                    int(left),
                    int(yy),
                    int(right),
                    int(yy),
                )

        if self._show_norm:
            painter.setPen(QPen(QColor("#d000d0"), 2))
            painter.setBrush(QColor("#d000d0"))
            previous: QPointF | None = None
            for x, value in zip(self._x, self._norm):
                if (
                    not math.isfinite(float(value))
                    or float(value) == 0.0
                ):
                    previous = None
                    continue
                current = QPointF(
                    px(float(x)),
                    py(float(value)),
                )
                if previous is not None:
                    painter.drawLine(previous, current)
                painter.drawEllipse(current, 2.2, 2.2)
                previous = current

        legend = []
        if self._show_norm:
            legend.append(("Convergence", QColor("#d000d0")))
        if self._show_criterion and self._criterion is not None:
            legend.append(("Criterion", QColor("#00bcd4")))
        if self._show_cutbacks:
            legend.append(("Cutback", QColor("#e74c3c")))
        if self._show_converged:
            legend.append(("Converged", QColor("#2ecc71")))
        x_cursor = int(left + 4)
        for label, color in legend:
            painter.setPen(QPen(color, 2))
            painter.drawLine(x_cursor, 12, x_cursor + 18, 12)
            painter.setPen(QColor("#263746"))
            painter.drawText(x_cursor + 23, 16, label)
            x_cursor += 95

        painter.setPen(QColor("#526579"))
        painter.drawText(4, int(top + 8), f"1e{math.ceil(log_max):g}")
        painter.drawText(4, int(bottom), f"1e{math.floor(log_min):g}")
        painter.drawText(int(left), self.height() - 7, "1")
        painter.drawText(
            int(right - 44),
            self.height() - 7,
            f"{int(xmax)}",
        )
        painter.drawText(
            int((left + right) / 2 - 55),
            self.height() - 7,
            "Cumulative iteration",
        )


class AnalysisCoordinatePlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._x: list[float] = []
        self._y: list[float] = []
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

    def set_series(
        self,
        x: list[float],
        y: list[float],
    ) -> None:
        self._x = list(x)
        self._y = list(y)
        self.update()

    def clear(self) -> None:
        self.set_series([], [])

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        if len(self._x) < 2 or len(self._y) < 2:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No analysis-coordinate history",
            )
            return

        left = 58.0
        right = max(left + 1.0, self.width() - 18.0)
        top = 10.0
        bottom = max(top + 1.0, self.height() - 26.0)
        xmin = min(self._x)
        xmax = max(self._x)
        ymin = min(self._y)
        ymax = max(self._y)
        if abs(xmax - xmin) < 1.0e-15:
            xmax = xmin + 1.0
        if abs(ymax - ymin) < 1.0e-15:
            pad = max(abs(ymax), 1.0) * 0.05
            ymin -= pad
            ymax += pad

        def point(x: float, y: float) -> QPointF:
            return QPointF(
                left + (x - xmin) / (xmax - xmin) * (right - left),
                bottom - (y - ymin) / (ymax - ymin) * (bottom - top),
            )

        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(int(left), int(bottom), int(right), int(bottom))
        painter.drawLine(int(left), int(top), int(left), int(bottom))

        painter.setPen(QPen(QColor("#202020"), 2))
        previous = point(self._x[0], self._y[0])
        for x, y in zip(self._x[1:], self._y[1:]):
            current = point(x, y)
            painter.drawLine(previous, current)
            previous = current

        painter.setPen(QColor("#526579"))
        painter.drawText(4, int(top + 8), f"{ymax:.3g}")
        painter.drawText(4, int(bottom), f"{ymin:.3g}")
        painter.drawText(
            int((left + right) / 2 - 55),
            self.height() - 6,
            "Cumulative iteration",
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


class CompactResultTabs(QTabWidget):
    """Tab stack whose hidden pages cannot force a large dock width."""

    def minimumSizeHint(self) -> QSize:
        return QSize(80, 80)

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is None:
            return QSize(320, 240)
        hint = current.sizeHint()
        return QSize(
            min(max(240, hint.width()), 420),
            min(max(180, hint.height()), 520),
        )


class ResultsPanel(QWidget):
    deformation_requested = Signal(float, str, str, bool)
    mode_shape_requested = Signal(int, float, str, str, bool)
    motion_frame_requested = Signal(object, float, bool, float, str)
    clear_overlay_requested = Signal()
    member_force_requested = Signal(str, float)
    node_contour_requested = Signal(str, str)
    hinge_state_requested = Signal()
    element_selected = Signal(int)
    job_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: dict[str, Any] = {}
        self._node_table_cache: dict[str, list[tuple[str, ...]]] = {}
        self._element_table_cache: dict[
            str,
            tuple[list[tuple[int, float, float, float, str]], str],
        ] = {}
        self._node_table_display_key: str | None = None
        self._element_table_display_key: str | None = None
        # Stable source key (normally ("job", job_id)) used to avoid
        # rebuilding every result table when switching views of one Job.
        self._result_cache_key: object | None = None
        self._live_convergence_attempts: list[dict[str, Any]] = []
        self._live_convergence_step = 0
        self._live_convergence_total = 0
        self._live_convergence_test = ""
        self._live_convergence_tolerance: float | None = None
        self._live_cumulative_iteration = 0
        self._live_attempt_iteration = 0
        self._live_trace_x: list[float] = []
        self._live_trace_norm: list[float] = []
        self._live_cutbacks: list[float] = []
        self._live_converged: list[float] = []
        self._live_coordinate_x: list[float] = [0.0]
        self._live_coordinate_y: list[float] = [0.0]
        self._motion_timer = QTimer(self)
        self._motion_timer.timeout.connect(self._advance_motion)
        self._motion_info = None
        self._motion_frame_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 5, 6, 5)
        root.setSpacing(4)

        self.setMinimumSize(0, 0)
        self.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Expanding,
        )

        self.tabs = CompactResultTabs()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()
        self.tabs.setMinimumSize(0, 0)
        self.tabs.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Expanding,
        )
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
        self._build_specimen_tab()
        self._build_history_tab()
        self._build_motion_tab()

        # QTabWidget normally derives its minimum from every hidden page.
        # Results pages contain wide tables, so without relaxing these hints
        # the surrounding QDockWidget behaves as though it were fixed-width.
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if page is not None:
                page.setMinimumSize(0, 0)
                page.setSizePolicy(
                    QSizePolicy.Ignored,
                    QSizePolicy.Expanding,
                )
        for table in self.findChildren(QTableWidget):
            table.setMinimumSize(0, 0)
            table.setSizePolicy(
                QSizePolicy.Ignored,
                QSizePolicy.Expanding,
            )
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)


    def minimumSizeHint(self) -> QSize:
        return QSize(80, 80)

    def sizeHint(self) -> QSize:
        return QSize(360, 300)

    def _select_tab(self, title: str) -> None:
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == str(title):
                self.tabs.setCurrentIndex(index)
                return

    def show_jobs(self) -> None:
        self._select_tab("Jobs")

    def show_solution_result(
        self,
        result_type: str,
        settings: dict[str, Any] | None = None,
    ) -> None:
        options = dict(settings or {})
        kind = str(result_type)

        if kind == "DeformedShape":
            scale = options.get("scale", 10.0)
            try:
                self.deformation_scale.setValue(float(scale))
            except (TypeError, ValueError):
                pass
            display_mode = str(
                options.get("display_mode", "deformed_only")
            )
            index = self.deformation_display.findData(display_mode)
            self.deformation_display.setCurrentIndex(
                index if index >= 0 else 0
            )
            representation = str(
                options.get("representation", "actual_section")
            )
            index = self.deformation_representation.findData(
                representation
            )
            self.deformation_representation.setCurrentIndex(
                index if index >= 0 else 0
            )
            self.deformation_smooth.setChecked(
                bool(options.get("smooth_curvature", True))
            )
            self._select_tab("Deformation")
            return

        if kind in {"NodalDisplacement", "NodalReaction"}:
            quantity = (
                "Reaction"
                if kind == "NodalReaction"
                else "Displacement"
            )
            self.node_quantity.setCurrentText(quantity)
            component = str(
                options.get(
                    "component",
                    "FX" if quantity == "Reaction" else "|U|",
                )
            )
            index = self.node_contour_component.findText(component)
            if index >= 0:
                self.node_contour_component.setCurrentIndex(index)
            self._select_tab("Node Results")
            return

        if kind == "MemberForce":
            component = str(options.get("component", "Mz"))
            index = self.element_quantity.findText(component)
            if index >= 0:
                self.element_quantity.setCurrentIndex(index)
            try:
                self.member_force_scale.setValue(
                    float(options.get("scale", 1.0))
                )
            except (TypeError, ValueError):
                pass
            self._select_tab("Member Forces")
            return

        if kind in {"FiberStress", "FiberStrain"}:
            self.fiber_quantity.setCurrentText(
                "Stress" if kind == "FiberStress" else "Strain"
            )
            element_scope = options.get("_element_scope", [])
            if isinstance(element_scope, (list, tuple)) and element_scope:
                try:
                    element_tag = int(element_scope[0])
                except (TypeError, ValueError):
                    element_tag = None
                if element_tag is not None:
                    index = self.fiber_element.findData(element_tag)
                    if index >= 0:
                        self.fiber_element.setCurrentIndex(index)
            section = options.get("section")
            if section is not None:
                try:
                    section_number = int(section)
                except (TypeError, ValueError):
                    section_number = None
                if section_number is not None:
                    index = self.fiber_section.findData(section_number)
                    if index >= 0:
                        self.fiber_section.setCurrentIndex(index)
            self._select_tab("Fiber Response")
            return

        if kind == "HingeState":
            self._select_tab("Hinge / Yield States")
            return
        if kind == "PushoverCurve":
            self._select_tab("Pushover Curve")
            return
        if kind == "CyclicHysteresis":
            self._select_tab("Cyclic Hysteresis")
            return
        if kind == "SpecimenResponse":
            self._select_tab("Specimen Response")
            return
        if kind == "TimeHistory":
            node = options.get("node")
            if node is not None:
                try:
                    index = self.history_node.findData(int(node))
                except (TypeError, ValueError):
                    index = -1
                if index >= 0:
                    self.history_node.setCurrentIndex(index)
            quantity = str(
                options.get("quantity", "Displacement")
            )
            index = self.history_quantity.findText(quantity)
            if index >= 0:
                self.history_quantity.setCurrentIndex(index)
            dof = options.get("dof")
            if dof is not None:
                try:
                    index = int(dof) - 1
                except (TypeError, ValueError):
                    index = -1
                if 0 <= index < self.history_dof.count():
                    self.history_dof.setCurrentIndex(index)
            self._select_tab("Time History")
            return
        if kind == "ModeShape":
            mode = options.get("mode")
            if mode is not None:
                index = self.mode_combo.findData(int(mode))
                if index >= 0:
                    self.mode_combo.setCurrentIndex(index)
            scale = options.get("scale")
            if scale is not None:
                try:
                    self.mode_scale.setValue(float(scale))
                except (TypeError, ValueError):
                    pass
            display_mode = str(
                options.get("display_mode", "deformed_only")
            )
            index = self.mode_display.findData(display_mode)
            self.mode_display.setCurrentIndex(
                index if index >= 0 else 0
            )
            representation = str(
                options.get("representation", "actual_section")
            )
            index = self.mode_representation.findData(representation)
            self.mode_representation.setCurrentIndex(
                index if index >= 0 else 0
            )
            self.mode_smooth.setChecked(
                bool(options.get("smooth_curvature", True))
            )
            self._select_tab("Mode Shape")
            return
        if kind == "Motion":
            mode = options.get("mode")
            if mode is not None:
                index = self.motion_source.findData(int(mode))
                if index >= 0:
                    self.motion_source.setCurrentIndex(index)
            scale = options.get("scale")
            if scale is not None:
                try:
                    self.motion_scale.setValue(float(scale))
                except (TypeError, ValueError):
                    pass
            if "auto_scale" in options:
                self.motion_auto_scale.setChecked(
                    bool(options.get("auto_scale"))
                )
            self._select_tab("Motion")
            self._emit_current_motion_frame()
            return
        if kind == "Convergence":
            self._select_tab("Convergence")
            return

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
        layout.setSpacing(4)

        controls = QHBoxLayout()

        self.convergence_display_button = QToolButton()
        self.convergence_display_button.setText("Display")
        self.convergence_display_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        display_menu = QMenu(self.convergence_display_button)
        self.convergence_display_actions: dict[str, QAction] = {}
        for key, label, checked in (
            ("norm", "Convergence Norm", True),
            ("criterion", "Criterion", True),
            ("cutbacks", "Cutback Markers", True),
            ("converged", "Substep Converged", True),
            ("coordinate", "Analysis Coordinate", True),
            ("details", "Detailed History", False),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(checked)
            action.toggled.connect(
                self._update_convergence_display_options
            )
            display_menu.addAction(action)
            self.convergence_display_actions[key] = action
        self.convergence_display_button.setMenu(display_menu)
        controls.addWidget(self.convergence_display_button)

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

        self.convergence_plot_splitter = QSplitter(Qt.Vertical)
        self.convergence_plot_splitter.setChildrenCollapsible(True)
        self.convergence_plot_splitter.setMinimumSize(0, 0)

        self.convergence_overview_plot = ConvergenceOverviewPlot()
        self.convergence_plot_splitter.addWidget(
            self.convergence_overview_plot
        )

        self.convergence_coordinate_plot = AnalysisCoordinatePlot()
        self.convergence_plot_splitter.addWidget(
            self.convergence_coordinate_plot
        )
        self.convergence_plot_splitter.setStretchFactor(0, 4)
        self.convergence_plot_splitter.setStretchFactor(1, 1)
        self.convergence_plot_splitter.setSizes([240, 70])
        layout.addWidget(self.convergence_plot_splitter, 1)

        self.convergence_details_widget = QWidget()
        details_layout = QVBoxLayout(self.convergence_details_widget)
        details_layout.setContentsMargins(0, 2, 0, 0)
        details_layout.setSpacing(3)

        self.convergence_info = QLabel(
            "Run a non-modal analysis to inspect solver convergence."
        )
        self.convergence_info.setWordWrap(True)
        details_layout.addWidget(self.convergence_info)

        self.convergence_summary_label = QLabel(
            "Steps: -   Recovered: -   Failed: -   Max iterations: -"
        )
        self.convergence_summary_label.setWordWrap(True)
        details_layout.addWidget(self.convergence_summary_label)

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
        self.convergence_table.setMinimumSize(0, 0)
        details_layout.addWidget(self.convergence_table, 1)

        self.convergence_attempt_info = QLabel(
            "Select a step to inspect primary/fallback attempts."
        )
        self.convergence_attempt_info.setWordWrap(True)
        details_layout.addWidget(self.convergence_attempt_info)

        self.convergence_details_widget.hide()
        layout.addWidget(self.convergence_details_widget, 1)

        self.tabs.addTab(page, "Convergence")
        self._update_convergence_display_options()

    def _update_convergence_display_options(self) -> None:
        actions = getattr(self, "convergence_display_actions", {})
        if not actions:
            return
        self.convergence_overview_plot.set_display_options(
            norm=actions["norm"].isChecked(),
            criterion=actions["criterion"].isChecked(),
            cutbacks=actions["cutbacks"].isChecked(),
            converged=actions["converged"].isChecked(),
        )
        self.convergence_coordinate_plot.setVisible(
            actions["coordinate"].isChecked()
        )
        self.convergence_details_widget.setVisible(
            actions["details"].isChecked()
        )

    def _build_deformation_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Display:"))
        self.deformation_display = QComboBox()
        self.deformation_display.addItem(
            "Deformed",
            "deformed_only",
        )
        self.deformation_display.addItem(
            "Both",
            "both",
        )
        self.deformation_display.addItem(
            "Undeformed",
            "undeformed_only",
        )
        self.deformation_display.setToolTip(
            "Hide the original frame to inspect the deformed shape without "
            "the undeformed model obscuring it."
        )
        row.addWidget(self.deformation_display)

        row.addWidget(QLabel("Scale:"))
        self.deformation_scale = QDoubleSpinBox()
        self.deformation_scale.setRange(0.01, 1.0e6)
        self.deformation_scale.setDecimals(3)
        self.deformation_scale.setValue(10.0)
        row.addWidget(self.deformation_scale)
        self.deformation_show_button = QPushButton("Show")
        clear = QPushButton("Clear")
        self.deformation_show_button.clicked.connect(
            lambda: self.deformation_requested.emit(
                self.deformation_scale.value(),
                str(self.deformation_display.currentData()),
                str(self.deformation_representation.currentData()),
                self.deformation_smooth.isChecked(),
            )
        )
        clear.clicked.connect(self.clear_overlay_requested.emit)
        row.addWidget(self.deformation_show_button)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)

        geometry_row = QHBoxLayout()
        geometry_row.addWidget(QLabel("Representation:"))
        self.deformation_representation = QComboBox()
        self.deformation_representation.addItem(
            "Actual Section",
            "actual_section",
        )
        self.deformation_representation.addItem("Tube", "tube")
        self.deformation_representation.addItem(
            "Centerline",
            "centerline",
        )
        self.deformation_representation.setToolTip(
            "Actual Section sweeps stored section geometry along the deformed "
            "member. Members without display geometry fall back to Tube."
        )
        geometry_row.addWidget(self.deformation_representation)
        self.deformation_smooth = QCheckBox("Smooth member curvature")
        self.deformation_smooth.setChecked(True)
        self.deformation_smooth.setToolTip(
            "Use nodal rotations with cubic beam interpolation instead of "
            "joining displaced end nodes with a straight segment."
        )
        geometry_row.addWidget(self.deformation_smooth)
        geometry_row.addStretch(1)
        layout.addLayout(geometry_row)

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
        self.mode_combo.currentIndexChanged.connect(
            self._update_mode_summary
        )
        row.addWidget(self.mode_combo)

        row.addWidget(QLabel("Display:"))
        self.mode_display = QComboBox()
        self.mode_display.addItem("Deformed", "deformed_only")
        self.mode_display.addItem("Both", "both")
        self.mode_display.addItem("Undeformed", "undeformed_only")
        self.mode_display.setToolTip(
            "Choose whether the undeformed frame remains visible behind "
            "the mode shape."
        )
        row.addWidget(self.mode_display)

        row.addWidget(QLabel("Scale:"))
        self.mode_scale = QDoubleSpinBox()
        self.mode_scale.setRange(0.01, 1.0e6)
        self.mode_scale.setValue(1.0)
        row.addWidget(self.mode_scale)
        self.mode_show_button = QPushButton("Show Mode")
        self.mode_show_button.clicked.connect(self._emit_mode)
        row.addWidget(self.mode_show_button)
        row.addStretch(1)
        layout.addLayout(row)

        geometry_row = QHBoxLayout()
        geometry_row.addWidget(QLabel("Representation:"))
        self.mode_representation = QComboBox()
        self.mode_representation.addItem("Actual Section", "actual_section")
        self.mode_representation.addItem("Tube", "tube")
        self.mode_representation.addItem("Centerline", "centerline")
        geometry_row.addWidget(self.mode_representation)
        self.mode_smooth = QCheckBox("Smooth member curvature")
        self.mode_smooth.setChecked(True)
        geometry_row.addWidget(self.mode_smooth)
        geometry_row.addStretch(1)
        layout.addLayout(geometry_row)

        self.mode_info = QLabel(
            "Run a Modal analysis to populate mode shapes."
        )
        self.mode_info.setWordWrap(True)
        layout.addWidget(self.mode_info)

        self.modal_summary_table = QTableWidget(0, 10)
        self.modal_summary_table.setHorizontalHeaderLabels(
            [
                "Mode",
                "Eigenvalue",
                "Frequency [Hz]",
                "Period [s]",
                "UX mass %",
                "UY mass %",
                "UZ mass %",
                "Cum. UX %",
                "Cum. UY %",
                "Cum. UZ %",
            ]
        )
        self.modal_summary_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.modal_summary_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.modal_summary_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.modal_summary_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.modal_summary_table.setMinimumSize(0, 0)
        layout.addWidget(self.modal_summary_table, 1)

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
            QHeaderView.Interactive
        )
        self.node_table.horizontalHeader().setDefaultSectionSize(78)
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
            QHeaderView.Interactive
        )
        self.element_table.horizontalHeader().setDefaultSectionSize(110)
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
            "Peak |u|: -   +Vpeak: -   -Vpeak: -   "
            "Hysteretic energy: -   Closed cycles: -"
        )
        self.cyclic_metrics.setWordWrap(True)
        layout.addWidget(self.cyclic_metrics)

        self.cyclic_plot = TimeHistoryPlot(
            empty_message="No cyclic hysteresis data"
        )
        layout.addWidget(self.cyclic_plot, 1)

        self.cyclic_reversal_table = QTableWidget(0, 6)
        self.cyclic_reversal_table.setHorizontalHeaderLabels(
            [
                "Reversal",
                "u",
                "V",
                "|Ksec|",
                "Strength / 1st",
                "Ksec / 1st",
            ]
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

    def _build_motion_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source:"))
        self.motion_source = QComboBox()
        self.motion_source.currentIndexChanged.connect(
            self._motion_source_changed
        )
        source_row.addWidget(self.motion_source, 1)

        source_row.addWidget(QLabel("Scale:"))
        self.motion_scale = QDoubleSpinBox()
        self.motion_scale.setRange(0.001, 1.0e6)
        self.motion_scale.setDecimals(3)
        self.motion_scale.setValue(1.0)
        self.motion_scale.valueChanged.connect(
            self._emit_current_motion_frame
        )
        source_row.addWidget(self.motion_scale)

        self.motion_auto_scale = QCheckBox("Auto")
        self.motion_auto_scale.setChecked(True)
        self.motion_auto_scale.toggled.connect(
            self._emit_current_motion_frame
        )
        source_row.addWidget(self.motion_auto_scale)
        layout.addLayout(source_row)

        transport = QHBoxLayout()
        previous = QPushButton("◀")
        previous.setToolTip("Previous motion frame")
        previous.clicked.connect(lambda: self._step_motion(-1))
        transport.addWidget(previous)

        self.motion_play = QPushButton("▶ Play")
        self.motion_play.setCheckable(True)
        self.motion_play.toggled.connect(self._toggle_motion_playback)
        transport.addWidget(self.motion_play)

        clear = QPushButton("Clear")
        clear.clicked.connect(self.stop_motion)
        clear.clicked.connect(self.clear_overlay_requested.emit)
        transport.addWidget(clear)

        next_button = QPushButton("▶")
        next_button.setToolTip("Next motion frame")
        next_button.clicked.connect(lambda: self._step_motion(1))
        transport.addWidget(next_button)

        transport.addWidget(QLabel("Speed:"))
        self.motion_speed = QComboBox()
        for label, speed in (
            ("0.25×", 0.25),
            ("0.5×", 0.5),
            ("1×", 1.0),
            ("2×", 2.0),
            ("4×", 4.0),
        ):
            self.motion_speed.addItem(label, speed)
        self.motion_speed.setCurrentIndex(2)
        self.motion_speed.currentIndexChanged.connect(
            self._update_motion_timer
        )
        transport.addWidget(self.motion_speed)

        self.motion_loop = QCheckBox("Loop")
        self.motion_loop.setChecked(True)
        transport.addWidget(self.motion_loop)
        transport.addStretch(1)
        layout.addLayout(transport)

        slider_row = QHBoxLayout()
        self.motion_slider = QSlider(Qt.Horizontal)
        self.motion_slider.setRange(0, 0)
        self.motion_slider.valueChanged.connect(
            self._motion_slider_changed
        )
        slider_row.addWidget(self.motion_slider, 1)
        self.motion_counter = QLabel("0 / 0")
        slider_row.addWidget(self.motion_counter)
        layout.addLayout(slider_row)

        self.motion_info_label = QLabel(
            "Run or select an analysis result to animate deformation."
        )
        self.motion_info_label.setWordWrap(True)
        layout.addWidget(self.motion_info_label)
        layout.addStretch(1)

        self.tabs.addTab(page, "Motion")

    def _motion_selected_mode(self) -> int | None:
        data = self.motion_source.currentData()
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return None

    def _refresh_motion_controls(self) -> None:
        self._motion_timer.stop()
        self.motion_play.blockSignals(True)
        self.motion_play.setChecked(False)
        self.motion_play.setText("▶ Play")
        self.motion_play.blockSignals(False)

        analysis = (
            self._result.get("analysis", {})
            if isinstance(self._result, dict)
            else {}
        )
        analysis_type = (
            str(analysis.get("type", ""))
            if isinstance(analysis, dict)
            else ""
        )

        previous_mode = self._motion_selected_mode()
        self.motion_source.blockSignals(True)
        self.motion_source.clear()
        if analysis_type == "Modal":
            modes = available_modal_modes(self._result)
            for mode in modes:
                self.motion_source.addItem(f"Mode {mode}", mode)
            if previous_mode is not None:
                index = self.motion_source.findData(previous_mode)
                if index >= 0:
                    self.motion_source.setCurrentIndex(index)
        else:
            self.motion_source.addItem(
                f"{analysis_type or 'Analysis'} deformation",
                None,
            )
        self.motion_source.blockSignals(False)

        self._motion_frame_index = 0
        self._motion_info = motion_info(
            self._result,
            mode=self._motion_selected_mode(),
            scan_reference=False,
        )
        count = int(self._motion_info.frame_count)
        self.motion_slider.blockSignals(True)
        self.motion_slider.setRange(0, max(0, count - 1))
        self.motion_slider.setValue(0)
        self.motion_slider.blockSignals(False)
        self.motion_counter.setText(
            f"{1 if count else 0} / {count}"
        )
        enabled = count > 0
        self.motion_play.setEnabled(enabled)
        self.motion_slider.setEnabled(enabled)
        self.motion_source.setEnabled(
            analysis_type == "Modal"
            and self.motion_source.count() > 1
        )
        self.motion_info_label.setText(
            (
                f"{analysis_type or 'Analysis'} motion available · "
                f"{count} frame(s). Open or play Motion to display it."
                if count > 0
                else "No deformation history or modal vectors are "
                "available for motion playback."
            )
        )
        self._sync_motion_markers(None)

    def _motion_source_changed(self, *_args) -> None:
        self._motion_frame_index = 0
        self._motion_info = motion_info(
            self._result,
            mode=self._motion_selected_mode(),
            scan_reference=False,
        )
        count = int(self._motion_info.frame_count)
        self.motion_slider.blockSignals(True)
        self.motion_slider.setRange(0, max(0, count - 1))
        self.motion_slider.setValue(0)
        self.motion_slider.blockSignals(False)
        self._emit_current_motion_frame()

    def _motion_slider_changed(self, value: int) -> None:
        self._motion_frame_index = int(value)
        self._emit_current_motion_frame()

    def _set_motion_index(self, index: int) -> None:
        if self._motion_info is None:
            return
        count = int(self._motion_info.frame_count)
        if count <= 0:
            return
        target = max(0, min(int(index), count - 1))
        self._motion_frame_index = target
        if self.motion_slider.value() != target:
            self.motion_slider.setValue(target)
        else:
            self._emit_current_motion_frame()

    def _step_motion(self, delta: int) -> None:
        if self._motion_info is None:
            return
        count = int(self._motion_info.frame_count)
        if count <= 0:
            return
        target = self._motion_frame_index + int(delta)
        if target >= count:
            target = 0 if self.motion_loop.isChecked() else count - 1
        elif target < 0:
            target = count - 1 if self.motion_loop.isChecked() else 0
        self._set_motion_index(target)

    def _motion_speed_value(self) -> float:
        try:
            return float(self.motion_speed.currentData())
        except (TypeError, ValueError):
            return 1.0

    def _update_motion_timer(self, *_args) -> None:
        if not self._motion_timer.isActive():
            return
        speed = max(0.01, self._motion_speed_value())
        interval = max(16, int(round(40.0 / speed)))
        if (
            self._motion_info is not None
            and self._motion_info.transient_dt is not None
        ):
            dt = float(self._motion_info.transient_dt)
            if dt > 0.0 and dt / speed > 0.04:
                interval = max(
                    16,
                    int(round(1000.0 * dt / speed)),
                )
            else:
                interval = 40
        self._motion_timer.setInterval(interval)

    def stop_motion(self) -> None:
        self._motion_timer.stop()
        if hasattr(self, "motion_play"):
            self.motion_play.blockSignals(True)
            self.motion_play.setChecked(False)
            self.motion_play.setText("▶ Play")
            self.motion_play.blockSignals(False)
        self._sync_motion_markers(None)

    def _toggle_motion_playback(self, checked: bool) -> None:
        if checked:
            if (
                self._motion_info is None
                or self._motion_info.frame_count <= 0
            ):
                self.motion_play.blockSignals(True)
                self.motion_play.setChecked(False)
                self.motion_play.blockSignals(False)
                return
            self.motion_play.setText("❚❚ Pause")
            speed = max(0.01, self._motion_speed_value())
            interval = max(16, int(round(40.0 / speed)))
            if self._motion_info.transient_dt is not None:
                dt = float(self._motion_info.transient_dt)
                if dt > 0.0 and dt / speed > 0.04:
                    interval = max(
                        16,
                        int(round(1000.0 * dt / speed)),
                    )
                else:
                    interval = 40
            self._motion_timer.setInterval(interval)
            self._motion_timer.start()
        else:
            self._motion_timer.stop()
            self.motion_play.setText("▶ Play")

    def _advance_motion(self) -> None:
        if self._motion_info is None:
            return
        count = int(self._motion_info.frame_count)
        if count <= 0:
            return

        increment = 1
        dt = self._motion_info.transient_dt
        speed = max(0.01, self._motion_speed_value())
        if dt is not None and dt > 0.0:
            desired = 0.04 * speed
            if desired >= dt:
                increment = max(1, int(round(desired / dt)))

        target = self._motion_frame_index + increment
        if target >= count:
            if self.motion_loop.isChecked():
                target %= count
            else:
                target = count - 1
                self.motion_play.setChecked(False)
        self._set_motion_index(target)

    def _sync_motion_markers(self, index: int | None) -> None:
        self.history_plot.set_marker(index)
        self.pushover_plot.set_marker(index)
        self.cyclic_plot.set_marker(index)

    def _emit_current_motion_frame(self, *_args) -> None:
        if not hasattr(self, "motion_info_label"):
            return
        mode = self._motion_selected_mode()
        if (
            self._motion_info is None
            or self._motion_info.reference_magnitude is None
        ):
            self._motion_info = motion_info(
                self._result,
                mode=mode,
                scan_reference=True,
            )
        count = int(self._motion_info.frame_count)
        if count <= 0:
            self.motion_counter.setText("0 / 0")
            self.motion_info_label.setText(
                "No deformation history or modal vectors are available "
                "for motion playback."
            )
            self._sync_motion_markers(None)
            return

        self._motion_frame_index = max(
            0,
            min(self._motion_frame_index, count - 1),
        )
        frame = motion_frame(
            self._result,
            self._motion_frame_index,
            mode=mode,
            info=self._motion_info,
        )
        self.motion_counter.setText(
            f"{frame.index + 1} / {frame.frame_count}"
        )
        self.motion_info_label.setText(frame.label)
        self._sync_motion_markers(
            None if self._motion_info.kind == "Modal" else frame.index
        )
        self.motion_frame_requested.emit(
            frame.vectors,
            float(self.motion_scale.value()),
            bool(self.motion_auto_scale.isChecked()),
            float(self._motion_info.reference_magnitude or 0.0),
            frame.label,
        )

    def _build_specimen_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Response:"))
        self.specimen_quantity = QComboBox()
        self.specimen_quantity.currentIndexChanged.connect(
            self._update_specimen_view
        )
        controls.addWidget(self.specimen_quantity, 1)
        layout.addLayout(controls)

        self.specimen_info = QLabel(
            "Quick 1D Column instrumentation is captured automatically when "
            "a test-column specimen is present."
        )
        self.specimen_info.setWordWrap(True)
        layout.addWidget(self.specimen_info)

        self.specimen_metrics = QLabel(
            "Mmax: -   κmax: -   drift: -   interface rotation: -"
        )
        self.specimen_metrics.setWordWrap(True)
        layout.addWidget(self.specimen_metrics)

        self.specimen_plot = TimeHistoryPlot(
            empty_message="No 1D-column specimen response data"
        )
        layout.addWidget(self.specimen_plot, 1)

        self.specimen_fiber_table = QTableWidget(0, 7)
        self.specimen_fiber_table.setHorizontalHeaderLabels([
            "Source",
            "Fiber",
            "Material",
            "y",
            "z",
            "Response",
            "Latest",
        ])
        self.specimen_fiber_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.specimen_fiber_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.specimen_fiber_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.specimen_fiber_table.setMaximumHeight(150)
        layout.addWidget(self.specimen_fiber_table)

        self.tabs.addTab(page, "Specimen Response")

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
        self.stop_motion()
        self._result = {}
        self._result_cache_key = None
        self._node_table_cache.clear()
        self._element_table_cache.clear()
        self._node_table_display_key = None
        self._element_table_display_key = None
        self.jobs_table.setRowCount(0)
        self.convergence_table.setRowCount(0)
        self._live_convergence_attempts = []
        self._live_convergence_step = 0
        self._live_convergence_total = 0
        self._live_convergence_test = ""
        self._live_convergence_tolerance = None
        self._live_cumulative_iteration = 0
        self._live_attempt_iteration = 0
        self._live_trace_x = []
        self._live_trace_norm = []
        self._live_cutbacks = []
        self._live_converged = []
        self._live_coordinate_x = [0.0]
        self._live_coordinate_y = [0.0]
        self.live_convergence_status.setText("Live monitor idle.")
        self.convergence_overview_plot.clear()
        self.convergence_coordinate_plot.clear()
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
        self.modal_summary_table.setRowCount(0)
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
            "Peak |u|: -   +Vpeak: -   -Vpeak: -   "
            "Hysteretic energy: -   Closed cycles: -"
        )
        self.history_node.clear()
        self.history_label.setText(
            "Run a non-modal analysis to populate time-history data."
        )
        self.history_plot.set_series([], [])

    def _populate_modal_summary(self) -> None:
        modes = (
            self._result.get("modes", {})
            if isinstance(self._result, dict)
            else {}
        )
        if not isinstance(modes, dict):
            modes = {}
        ordered = sorted(modes, key=lambda value: int(value))
        self.modal_summary_table.setRowCount(len(ordered))

        cumulative = [0.0, 0.0, 0.0]
        for row, key in enumerate(ordered):
            mode = modes.get(key, {})
            eigenvalue = float(mode.get("eigenvalue", 0.0) or 0.0)
            frequency = mode.get("frequency_hz")
            period = mode.get("period_s")
            participation = mode.get("participation", {})
            ratios: list[float] = []
            for dof in (1, 2, 3):
                item = (
                    participation.get(str(dof), {})
                    if isinstance(participation, dict)
                    else {}
                )
                ratio = 100.0 * float(
                    item.get("mass_ratio", 0.0) or 0.0
                )
                ratios.append(ratio)
                cumulative[dof - 1] += ratio

            values = [
                str(key),
                f"{eigenvalue:.6g}",
                (
                    f"{float(frequency):.6g}"
                    if frequency is not None
                    else "-"
                ),
                (
                    f"{float(period):.6g}"
                    if period is not None
                    else "-"
                ),
                *(f"{value:.3f}" for value in ratios),
                *(f"{value:.3f}" for value in cumulative),
            ]
            for column, value in enumerate(values):
                self.modal_summary_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _update_mode_summary(self, *_args) -> None:
        mode_number = self.mode_combo.currentData()
        if mode_number is None:
            self.mode_info.setText(
                "Run a Modal analysis to populate mode shapes."
            )
            return
        modes = (
            self._result.get("modes", {})
            if isinstance(self._result, dict)
            else {}
        )
        mode = modes.get(str(int(mode_number)), {})
        eigenvalue = float(mode.get("eigenvalue", 0.0) or 0.0)
        frequency = mode.get("frequency_hz")
        period = mode.get("period_s")
        participation = mode.get("participation", {})

        mass_text: list[str] = []
        for dof, label in ((1, "UX"), (2, "UY"), (3, "UZ")):
            item = (
                participation.get(str(dof), {})
                if isinstance(participation, dict)
                else {}
            )
            ratio = 100.0 * float(
                item.get("mass_ratio", 0.0) or 0.0
            )
            mass_text.append(f"{label}={ratio:.2f}%")

        frequency_text = (
            f"{float(frequency):.6g} Hz"
            if frequency is not None
            else "-"
        )
        period_text = (
            f"{float(period):.6g} s"
            if period is not None
            else "-"
        )
        self.mode_info.setText(
            f"Mode {int(mode_number)} · λ={eigenvalue:.6g} · "
            f"f={frequency_text} · T={period_text} · "
            + " · ".join(mass_text)
        )

    def _emit_mode(self) -> None:
        mode = self.mode_combo.currentData()
        if mode is None:
            return
        self.mode_shape_requested.emit(
            int(mode),
            self.mode_scale.value(),
            str(self.mode_display.currentData()),
            str(self.mode_representation.currentData()),
            self.mode_smooth.isChecked(),
        )

    def _refresh_live_convergence_plots(self) -> None:
        self.convergence_overview_plot.set_trace(
            self._live_trace_x,
            self._live_trace_norm,
            criterion=self._live_convergence_tolerance,
            cutbacks=self._live_cutbacks,
            converged=self._live_converged,
        )
        self.convergence_coordinate_plot.set_series(
            self._live_coordinate_x,
            self._live_coordinate_y,
        )

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
        self._live_convergence_total = int(total)
        self._live_convergence_test = str(test)
        self._live_convergence_tolerance = tolerance
        self._live_cumulative_iteration = 0
        self._live_attempt_iteration = 0
        self._live_trace_x = []
        self._live_trace_norm = []
        self._live_cutbacks = []
        self._live_converged = []
        self._live_coordinate_x = [0.0]
        self._live_coordinate_y = [0.0]
        self.tabs.setCurrentWidget(self.convergence_page)
        self._refresh_live_convergence_plots()
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
        self._live_attempt_iteration = 0
        if test:
            self._live_convergence_test = str(test)
        if tolerance is not None:
            self._live_convergence_tolerance = float(tolerance)
        self._live_convergence_attempts = [
            {"algorithm": str(algorithm), "values": []}
        ]
        self._refresh_live_convergence_plots()
        self.live_convergence_status.setText(
            f"RUNNING · Step {step}/{total} · {algorithm} · "
            f"{self._live_convergence_test or 'test'}"
        )

    def begin_live_convergence_attempt(
        self,
        algorithm: str,
    ) -> None:
        algorithm = str(algorithm)
        self._live_attempt_iteration = 0
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
        local_iteration = int(iteration)
        point = (local_iteration, float(norm))
        if values and int(values[-1][0]) == local_iteration:
            values[-1] = point
            if self._live_trace_norm:
                self._live_trace_norm[-1] = float(norm)
        else:
            values.append(point)
            self._live_cumulative_iteration += 1
            self._live_trace_x.append(
                float(self._live_cumulative_iteration)
            )
            self._live_trace_norm.append(float(norm))
        self._live_attempt_iteration = local_iteration
        self._refresh_live_convergence_plots()

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

    def mark_live_substep_converged(
        self,
        coordinate: float | None = None,
    ) -> None:
        if self._live_cumulative_iteration <= 0:
            return
        marker = float(self._live_cumulative_iteration)
        if not self._live_converged or self._live_converged[-1] != marker:
            self._live_converged.append(marker)
        if coordinate is not None:
            try:
                value = float(coordinate)
            except (TypeError, ValueError):
                value = math.nan
            if math.isfinite(value):
                if (
                    self._live_coordinate_x[-1] != marker
                    or self._live_coordinate_y[-1] != value
                ):
                    self._live_coordinate_x.append(marker)
                    self._live_coordinate_y.append(value)
        self._refresh_live_convergence_plots()

    def update_live_analysis_coordinate(
        self,
        coordinate: float | None,
    ) -> None:
        if coordinate is None or self._live_cumulative_iteration <= 0:
            return
        try:
            value = float(coordinate)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value):
            return
        marker = float(self._live_cumulative_iteration)
        if (
            self._live_coordinate_x[-1] != marker
            or self._live_coordinate_y[-1] != value
        ):
            self._live_coordinate_x.append(marker)
            self._live_coordinate_y.append(value)
            self._refresh_live_convergence_plots()

    def set_live_convergence_message(self, message: str) -> None:
        self.live_convergence_status.setText(str(message))

    def finish_live_convergence(self, status: str) -> None:
        if self._live_convergence_step <= 0:
            return
        final_status = str(status)
        marker = float(self._live_cumulative_iteration)
        if final_status == "CUTBACK" and marker > 0.0:
            if not self._live_cutbacks or self._live_cutbacks[-1] != marker:
                self._live_cutbacks.append(marker)
        elif final_status in {"CONVERGED", "RECOVERED"} and marker > 0.0:
            if not self._live_converged or self._live_converged[-1] != marker:
                self._live_converged.append(marker)
        if (
            final_status == "CONVERGED"
            and len(self._live_convergence_attempts) > 1
        ):
            final_status = "RECOVERED"
        self._refresh_live_convergence_plots()
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

    def set_result(
        self,
        result: dict[str, Any],
        *,
        cache_key: object | None = None,
    ) -> bool:
        """Load result data, skipping an identical already-loaded source.

        A completed Job is immutable for post-processing, so all saved plot
        children of that Job can share the same populated tables/dashboard.
        This avoids rebuilding convergence, node, member, fiber, hinge and
        history widgets on every tree selection.
        """
        if (
            cache_key is not None
            and cache_key == self._result_cache_key
            and self._result
        ):
            return False

        self._result = dict(result or {})
        self._result_cache_key = cache_key
        self._node_table_cache.clear()
        self._element_table_cache.clear()
        self._node_table_display_key = None
        self._element_table_display_key = None
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
        self._populate_modal_summary()
        self._update_mode_summary()

        self._populate_convergence_dashboard()
        self._populate_node_table()
        self._populate_element_table()
        self._populate_fiber_elements()
        self._populate_hinge_table()
        self._populate_history_nodes()
        self._update_pushover_plot()
        self._update_cyclic_plot()
        self._populate_specimen_response()
        self._update_history_plot()
        self._refresh_motion_controls()
        return True

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
            self.convergence_overview_plot.clear()
            self.convergence_coordinate_plot.clear()
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

        trace = convergence_trace(self._result)
        self.convergence_overview_plot.set_trace(
            list(trace.get("iteration", [])),
            list(trace.get("norm", [])),
            criterion=trace.get("criterion"),
            cutbacks=list(trace.get("cutbacks", [])),
            converged=list(trace.get("converged", [])),
        )
        self.convergence_coordinate_plot.set_series(
            list(trace.get("coordinate_iteration", [])),
            list(trace.get("coordinate", [])),
        )
        self.live_convergence_status.setText(
            f"POST-RUN · {analysis_type or 'Analysis'} · "
            f"{summary.get('test') or 'Convergence'} · "
            f"{int(trace.get('total_iterations', 0) or 0)} cumulative iterations"
        )

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
                    "total_iterations",
                    "norm",
                    "recovered",
                    "adaptive",
                    "cutbacks",
                    "nominal_increment",
                    "min_step_size_used",
                    "final_step_size",
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
                        row.get("total_iterations", row.get("iterations")),
                        row.get("norm"),
                        row.get("recovered"),
                        row.get("adaptive"),
                        row.get("cutbacks", 0),
                        row.get("nominal_increment"),
                        row.get("min_step_size_used"),
                        row.get("final_step_size"),
                        row.get("time"),
                        len(attempts),
                        chain,
                    ]
                )
        self.convergence_attempt_info.setText(
            f"Exported {len(rows)} convergence step(s) to {path}"
        )

    def _populate_node_table(self) -> None:
        displacement = self.node_quantity.currentText() == "Displacement"
        display_key = "Displacement" if displacement else "Reaction"
        if self._node_table_display_key == display_key:
            return

        headers = (
            ["Node", "UX", "UY", "UZ", "RX", "RY", "RZ"]
            if displacement
            else ["Node", "FX", "FY", "FZ", "MX", "MY", "MZ"]
        )
        rows = self._node_table_cache.get(display_key)
        if rows is None:
            final = self._result.get("final", {})
            key = "node_displacements" if displacement else "node_reactions"
            data = final.get(key, {}) if isinstance(final, dict) else {}
            if not isinstance(data, dict):
                data = {}
            rows = []
            for tag in sorted(data, key=lambda value: int(value)):
                values = list(data[tag])
                while len(values) < 6:
                    values.append(0.0)
                rows.append(
                    (
                        str(tag),
                        *(f"{float(value):.6g}" for value in values[:6]),
                    )
                )
            self._node_table_cache[display_key] = rows

        self.node_table.setUpdatesEnabled(False)
        try:
            self.node_table.setHorizontalHeaderLabels(headers)
            self.node_table.setRowCount(len(rows))
            for row_index, values in enumerate(rows):
                for column, value in enumerate(values):
                    self.node_table.setItem(
                        row_index,
                        column,
                        QTableWidgetItem(value),
                    )
        finally:
            self.node_table.setUpdatesEnabled(True)
        self._node_table_display_key = display_key

    def _populate_element_table(self) -> None:
        component = self.element_quantity.currentText()
        if self._element_table_display_key == component:
            return

        cached = self._element_table_cache.get(component)
        if cached is None:
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
                        max(
                            abs(float(end_values[0])),
                            abs(float(end_values[1])),
                        ),
                        "end-force fallback",
                    )
                )
                source_counts["end-force fallback"] = (
                    source_counts.get("end-force fallback", 0) + 1
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
                    note += (
                        f" {skipped} element(s) had no usable frame result."
                    )
            else:
                note = (
                    "No local member-force result is available for this job."
                )
            cached = (rows, note)
            self._element_table_cache[component] = cached

        rows, note = cached
        self.element_table.setUpdatesEnabled(False)
        try:
            self.element_table.setRowCount(len(rows))
            for row, (tag, value_i, value_j, maximum, _source) in enumerate(
                rows
            ):
                item = QTableWidgetItem(str(tag))
                item.setData(Qt.UserRole, tag)
                self.element_table.setItem(row, 0, item)
                self.element_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(f"{value_i:.6g}"),
                )
                self.element_table.setItem(
                    row,
                    2,
                    QTableWidgetItem(f"{value_j:.6g}"),
                )
                self.element_table.setItem(
                    row,
                    3,
                    QTableWidgetItem(f"{maximum:.6g}"),
                )
        finally:
            self.element_table.setUpdatesEnabled(True)

        self.element_info.setText(note)
        self._element_table_display_key = component

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

    def _populate_specimen_response(self) -> None:
        previous = self.specimen_quantity.currentData()
        self.specimen_quantity.blockSignals(True)
        self.specimen_quantity.clear()
        self.specimen_quantity.addItem(
            "Moment–curvature · base section",
            "moment_curvature",
        )
        for label, key in (
            ("Drift angle · total", "rotation:total"),
            ("Drift angle · member contribution", "rotation:column"),
            ("Interface rotation", "rotation:interface_rotation"),
            ("Interface lateral-slip drift", "rotation:interface_slip"),
        ):
            self.specimen_quantity.addItem(label, key)

        fibers = test_column_fiber_history_catalog(self._result)
        for item in fibers:
            self.specimen_quantity.addItem(
                f"{item.get('source', '-')} · "
                f"{item.get('label', '-')} · "
                f"{str(item.get('quantity', '')).title()}",
                str(item.get("key", "")),
            )

        if previous is not None:
            index = self.specimen_quantity.findData(previous)
            if index >= 0:
                self.specimen_quantity.setCurrentIndex(index)
        self.specimen_quantity.blockSignals(False)

        self.specimen_fiber_table.setRowCount(len(fibers))
        for row, item in enumerate(fibers):
            material = (
                f"{item.get('material_type', '-')} "
                f"[{item.get('material_tag', '-')}]"
            )
            values = [
                str(item.get("source", "-")),
                str(item.get("label", "-")),
                material,
                f"{float(item.get('y_coord', 0.0)):.6g}",
                f"{float(item.get('z_coord', 0.0)):.6g}",
                str(item.get("quantity", "-")),
                f"{float(item.get('latest', 0.0)):.6g}",
            ]
            for column, value in enumerate(values):
                self.specimen_fiber_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self._update_specimen_view()

    def _update_specimen_view(self, *_args) -> None:
        specimen = self._result.get("specimen", {})
        if not isinstance(specimen, dict) or not specimen:
            self.specimen_info.setText(
                "No Quick 1D Column instrumentation is available in this "
                "result. Create/run a 1D test specimen first."
            )
            self.specimen_metrics.setText(
                "Mmax: -   κmax: -   drift: -   interface rotation: -"
            )
            self.specimen_plot.set_series([], [])
            self.specimen_fiber_table.setRowCount(0)
            return

        summary = test_column_response_summary(self._result)
        interface_name = str(specimen.get("interface_name", "Fixed base"))
        element_tag = specimen.get("element_tag", "-")
        selected = str(
            self.specimen_quantity.currentData() or "moment_curvature"
        )

        max_m = summary.get("max_abs_moment")
        max_k = summary.get("max_abs_curvature")
        max_drift = summary.get("max_abs_total_drift")
        max_interface = summary.get("max_abs_interface_rotation")
        self.specimen_metrics.setText(
            "Mmax: "
            + (f"{float(max_m):.6g}" if max_m is not None else "-")
            + "   κmax: "
            + (f"{float(max_k):.6g}" if max_k is not None else "-")
            + "   max |drift angle|: "
            + (
                f"{float(max_drift):.6g}"
                if max_drift is not None
                else "-"
            )
            + "   max |interface rotation|: "
            + (
                f"{float(max_interface):.6g}"
                if max_interface is not None
                else "-"
            )
        )

        if selected == "moment_curvature":
            x, y, component = test_column_moment_curvature_curve(
                self._result
            )
            self.specimen_info.setText(
                f"Element {element_tag} · base IP · {component or 'M'}–κ · "
                f"base interface: {interface_name}. "
                "The section history and interface history are captured "
                "independently to avoid hiding strain-penetration deformation."
            )
            self.specimen_plot.set_series(x, y)
            return

        if selected.startswith("rotation:"):
            key = selected.split(":", 1)[1]
            decomposition = test_column_rotation_decomposition(
                self._result
            )
            x = decomposition.get("time", [])
            y = decomposition.get(key, [])
            labels = {
                "total": "total top-drift angle",
                "column": "member contribution = total − interface rotation − slip",
                "interface_rotation": "base-interface rotation",
                "interface_slip": "lateral interface slip / column height",
            }
            self.specimen_info.setText(
                f"Element {element_tag} · {labels.get(key, key)} · "
                f"base interface: {interface_name}. "
                "The member contribution is a drift-equivalent kinematic "
                "decomposition, not direct integration of section curvature."
            )
            self.specimen_plot.set_series(list(x), list(y))
            return

        item = next(
            (
                row
                for row in test_column_fiber_history_catalog(self._result)
                if str(row.get("key", "")) == selected
            ),
            None,
        )
        if item is None:
            self.specimen_plot.set_series([], [])
            return
        self.specimen_info.setText(
            f"{item.get('source', '-')} · {item.get('label', '-')} · "
            f"{item.get('material_type', '-')} "
            f"[{item.get('material_tag', '-')}] · "
            f"y={float(item.get('y_coord', 0.0)):.6g}, "
            f"z={float(item.get('z_coord', 0.0)):.6g}. "
            + (
                "For Bond_SP01, the material deformation is slip."
                if str(item.get("quantity", "")) == "slip"
                else ""
            )
        )
        self.specimen_plot.set_series(
            list(item.get("x", [])),
            list(item.get("y", [])),
        )

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
                "Peak |u|: -   +Vpeak: -   -Vpeak: -   "
                "Hysteretic energy: -   Closed cycles: -"
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
            f"+Vpeak: {float(metrics.get('peak_positive_force', 0.0)):.6g}   "
            f"-Vpeak: {float(metrics.get('peak_negative_force', 0.0)):.6g}   "
            f"Hysteretic energy: {energy_text}   "
            f"Closed cycles: {int(metrics.get('closed_cycle_count', 0))}   "
            f"Residual u: "
            f"{float(metrics.get('residual_displacement', 0.0)):.6g}"
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
            strength_ratio = reversal.get("strength_ratio")
            stiffness_ratio = reversal.get("stiffness_ratio")
            strength_ratio_text = (
                f"{float(strength_ratio):.4f}"
                if strength_ratio is not None
                and math.isfinite(float(strength_ratio))
                else "-"
            )
            stiffness_ratio_text = (
                f"{float(stiffness_ratio):.4f}"
                if stiffness_ratio is not None
                and math.isfinite(float(stiffness_ratio))
                else "-"
            )
            values = [
                str(row + 1),
                f"{float(reversal.get('displacement', 0.0)):.6g}",
                f"{float(reversal.get('force', 0.0)):.6g}",
                stiffness_text,
                strength_ratio_text,
                stiffness_ratio_text,
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
