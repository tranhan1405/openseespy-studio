from __future__ import annotations

import csv
import math
from typing import Any

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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

from ..calibration import (
    calibration_available_objectives,
    calibration_best_score_history,
    calibration_objective_label,
    calibration_parameter_keys,
    calibration_parameter_label,
    calibration_pareto_projection,
    calibration_round_best_parameter_series,
)
from ..jobs import JobRecord
from ..response2000 import (
    parse_response2000_chart_text,
    response2000_curve_comparison,
    response2000_series,
    suggest_response2000_columns,
    suggest_response2000_units,
)
from ..units import UnitSystem
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
    cyclic_backbone_curve,
    cyclic_curve_comparison,
    cyclic_hysteresis_curve,
    cyclic_hysteresis_metrics,
    experimental_csv_series,
    parse_experimental_csv_text,
    column_cyclic_cycle_metrics,
    column_cyclic_reversal_metrics,
    fiber_response_element_tags,
    fiber_response_range,
    fiber_response_sections,
    fiber_state_element_tags,
    fiber_state_sections,
    force_displacement_curve,
    moment_curvature_curve,
    section_response_curve,
    pushover_capacity_curve,
    time_history_node_tags,
    time_history_series,
    column_fiber_history_catalog,
    column_interface_moment_rotation_curve,
    column_moment_curvature_curve,
    column_response_summary,
    column_rotation_decomposition,
    column_specimen_research_metrics,
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
        self._overlay_x: list[float] = []
        self._overlay_y: list[float] = []
        self._overlay_label = ""
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

    def set_overlay(
        self,
        x: list[float],
        y: list[float],
        *,
        label: str = "",
    ) -> None:
        self._overlay_x = list(x)
        self._overlay_y = list(y)
        self._overlay_label = str(label)
        self.update()

    def clear_overlay(self) -> None:
        self.set_overlay([], [], label="")

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

        all_x = list(self._x)
        all_y = list(self._y)
        if len(self._overlay_x) >= 2 and len(self._overlay_y) >= 2:
            all_x.extend(self._overlay_x)
            all_y.extend(self._overlay_y)

        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)
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

        if len(self._overlay_x) >= 2 and len(self._overlay_y) >= 2:
            overlay_pen = QPen(QColor("#d35400"), 2)
            overlay_pen.setStyle(Qt.DashLine)
            painter.setPen(overlay_pen)
            previous = point(self._overlay_x[0], self._overlay_y[0])
            for x, y in zip(self._overlay_x[1:], self._overlay_y[1:]):
                current = point(x, y)
                painter.drawLine(previous, current)
                previous = current

            painter.setPen(QColor("#526579"))
            label = self._overlay_label or "Experiment"
            painter.drawText(
                left + 6,
                top + 14,
                f"Solid: OpenSees   Dashed: {label}",
            )

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


class CalibrationParetoPlot(QWidget):
    point_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[dict[str, Any]] = []
        self._x_label = "Objective X"
        self._y_label = "Objective Y"
        self._selected_job_id: int | None = None
        self._screen_points: list[tuple[float, float, int | None]] = []
        self.setMinimumHeight(135)

    def set_points(
        self,
        points: list[dict[str, Any]],
        *,
        x_label: str,
        y_label: str,
    ) -> None:
        self._points = [
            dict(point)
            for point in points
            if isinstance(point, dict)
        ]
        self._x_label = str(x_label)
        self._y_label = str(y_label)
        self.update()

    def clear(self) -> None:
        self._points = []
        self._screen_points = []
        self._selected_job_id = None
        self.update()

    def set_selected_job(self, job_id: int | None) -> None:
        self._selected_job_id = (
            None if job_id is None else int(job_id)
        )
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        self._screen_points = []

        if not self._points:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No finite Pareto objective pairs",
            )
            return

        left = 62.0
        right = max(left + 1.0, self.width() - 18.0)
        top = 22.0
        bottom = max(top + 1.0, self.height() - 36.0)
        xs = [float(point["x"]) for point in self._points]
        ys = [float(point["y"]) for point in self._points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if abs(xmax - xmin) < 1.0e-15:
            pad = max(abs(xmax), 1.0) * 0.05
            xmin -= pad
            xmax += pad
        if abs(ymax - ymin) < 1.0e-15:
            pad = max(abs(ymax), 1.0) * 0.05
            ymin -= pad
            ymax += pad

        def map_point(x: float, y: float) -> QPointF:
            px = left + (x - xmin) / (xmax - xmin) * (right - left)
            py = bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
            return QPointF(px, py)

        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(int(left), int(bottom), int(right), int(bottom))
        painter.drawLine(int(left), int(top), int(left), int(bottom))

        projected = sorted(
            (
                point
                for point in self._points
                if bool(point.get("projection_front"))
            ),
            key=lambda point: (float(point["x"]), float(point["y"])),
        )
        if len(projected) >= 2:
            painter.setPen(QPen(QColor("#d35400"), 2))
            previous = map_point(
                float(projected[0]["x"]),
                float(projected[0]["y"]),
            )
            for point in projected[1:]:
                current = map_point(
                    float(point["x"]),
                    float(point["y"]),
                )
                painter.drawLine(previous, current)
                previous = current

        for point in self._points:
            screen = map_point(
                float(point["x"]),
                float(point["y"]),
            )
            job_id_raw = point.get("job_id")
            try:
                job_id = (
                    int(job_id_raw)
                    if job_id_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                job_id = None
            self._screen_points.append(
                (screen.x(), screen.y(), job_id)
            )

            global_front = bool(
                point.get("global_pareto_front")
            )
            projected_front = bool(point.get("projection_front"))
            if global_front:
                painter.setPen(QPen(QColor("#1565c0"), 2))
                painter.setBrush(QColor("#ffffff"))
                radius = 5.0
            elif projected_front:
                painter.setPen(QPen(QColor("#d35400"), 2))
                painter.setBrush(QColor("#ffffff"))
                radius = 4.0
            else:
                painter.setPen(QPen(QColor("#7f8c8d"), 1))
                painter.setBrush(QColor("#bdc3c7"))
                radius = 3.0
            painter.drawEllipse(screen, radius, radius)

            if (
                self._selected_job_id is not None
                and job_id == self._selected_job_id
            ):
                painter.setPen(QPen(QColor("#c62828"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(screen, 8.0, 8.0)

        painter.setPen(QColor("#526579"))
        painter.drawText(4, int(top + 8), f"{ymax:.3g}")
        painter.drawText(4, int(bottom), f"{ymin:.3g}")
        painter.drawText(int(left), self.height() - 7, f"{xmin:.3g}")
        painter.drawText(
            int(right - 40),
            self.height() - 7,
            f"{xmax:.3g}",
        )
        painter.drawText(
            int(left + 8),
            15,
            "Blue ring: global P1 · orange line: selected-axis front",
        )
        painter.drawText(
            int((left + right) / 2 - 80),
            self.height() - 7,
            self._x_label,
        )
        painter.save()
        painter.translate(13, (top + bottom) / 2 + 70)
        painter.rotate(-90)
        painter.drawText(0, 0, self._y_label)
        painter.restore()

    def mousePressEvent(self, event) -> None:
        if not self._screen_points:
            return
        position = event.position()
        best_job: int | None = None
        best_distance = 9.0
        for x, y, job_id in self._screen_points:
            if job_id is None:
                continue
            distance = math.hypot(
                position.x() - x,
                position.y() - y,
            )
            if distance <= best_distance:
                best_distance = distance
                best_job = job_id
        if best_job is not None:
            self.point_selected.emit(best_job)


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
    calibration_case_apply_requested = Signal(object)
    moment_curvature_hinge_requested = Signal(object)

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
        self._calibration_rows: list[dict[str, Any]] = []
        self._cyclic_experiment_dataset: dict[str, Any] = {}
        self._cyclic_experiment_path = ""
        self._project_units = UnitSystem.from_mapping(None).as_mapping()
        self._response2000_dataset: dict[str, Any] = {}
        self._response2000_path = ""
        self._response2000_source_name = ""

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
        self._build_force_displacement_tab()
        self._build_section_response_tab()
        self._build_moment_curvature_tab()
        self._build_pushover_tab()
        self._build_cyclic_tab()
        self._build_specimen_tab()
        self._build_calibration_tab()
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

    def set_units(self, units) -> None:
        self._project_units = UnitSystem.from_mapping(units).as_mapping()
        if hasattr(self, "response2000_curvature_unit"):
            self._update_moment_curvature_plot()

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
        if kind == "ForceDisplacement":
            node_scope = options.get("_node_scope", [])
            default_node = (
                int(node_scope[0])
                if isinstance(node_scope, (list, tuple)) and node_scope
                else None
            )
            displacement_node = options.get(
                "displacement_node",
                default_node,
            )
            if displacement_node is not None:
                try:
                    index = self.force_disp_node.findData(
                        int(displacement_node)
                    )
                except (TypeError, ValueError):
                    index = -1
                if index >= 0:
                    self.force_disp_node.setCurrentIndex(index)

            displacement_dof = options.get("displacement_dof")
            if displacement_dof is not None:
                try:
                    index = int(displacement_dof) - 1
                except (TypeError, ValueError):
                    index = -1
                if 0 <= index < self.force_disp_dof.count():
                    self.force_disp_dof.setCurrentIndex(index)

            source = str(options.get("force_source", "Base shear"))
            index = self.force_disp_force_source.findText(source)
            if index >= 0:
                self.force_disp_force_source.setCurrentIndex(index)

            force_node = options.get("force_node", default_node)
            if force_node is not None:
                try:
                    index = self.force_disp_force_node.findData(
                        int(force_node)
                    )
                except (TypeError, ValueError):
                    index = -1
                if index >= 0:
                    self.force_disp_force_node.setCurrentIndex(index)

            force_dof = options.get("force_dof")
            if force_dof is not None:
                try:
                    index = int(force_dof) - 1
                except (TypeError, ValueError):
                    index = -1
                if 0 <= index < self.force_disp_force_dof.count():
                    self.force_disp_force_dof.setCurrentIndex(index)

            self._update_force_displacement_controls()
            self._select_tab("Force–Displacement")
            return
        if kind == "SectionResponse":
            self._select_section_response(options)
            self._select_tab("Section Response")
            return
        if kind == "MomentCurvature":
            self._select_tab("Moment–Curvature")
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
            ("details", "Detailed History", True),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(checked)
            action.toggled.connect(
                self._update_convergence_display_options
            )
            if key == "details":
                # Detailed history now has its own sub-tab. Keep this legacy
                # action internally for compatibility without duplicating UI.
                action.setVisible(False)
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

        self.convergence_detail_tabs = CompactResultTabs()
        self.convergence_detail_tabs.setDocumentMode(True)
        layout.addWidget(self.convergence_detail_tabs, 1)

        overview_page = QWidget()
        overview_layout = QVBoxLayout(overview_page)
        overview_layout.setContentsMargins(3, 3, 3, 3)
        overview_layout.setSpacing(4)

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
        overview_layout.addWidget(self.convergence_plot_splitter, 1)
        self.convergence_detail_tabs.addTab(overview_page, "Overview")

        self.convergence_details_widget = QWidget()
        details_layout = QVBoxLayout(self.convergence_details_widget)
        details_layout.setContentsMargins(3, 3, 3, 3)
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

        self.convergence_detail_tabs.addTab(
            self.convergence_details_widget,
            "Step Details",
        )

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
        if hasattr(self, "convergence_detail_tabs"):
            self.convergence_detail_tabs.setTabEnabled(
                1,
                actions["details"].isChecked(),
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

        self.modal_mass_coverage = QLabel(
            "Cumulative translational modal mass: -"
        )
        self.modal_mass_coverage.setWordWrap(True)
        self.modal_mass_coverage.setToolTip(
            "90% is used here only as a QA reference threshold. "
            "Check the governing standard and analysis purpose."
        )
        layout.addWidget(self.modal_mass_coverage)

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

    def _build_force_displacement_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Disp. node:"))
        self.force_disp_node = QComboBox()
        self.force_disp_node.currentIndexChanged.connect(
            self._update_force_displacement_plot
        )
        controls.addWidget(self.force_disp_node)

        controls.addWidget(QLabel("DOF:"))
        self.force_disp_dof = QComboBox()
        self.force_disp_dof.addItems(
            ["UX", "UY", "UZ", "RX", "RY", "RZ"]
        )
        self.force_disp_dof.currentIndexChanged.connect(
            self._update_force_displacement_plot
        )
        controls.addWidget(self.force_disp_dof)

        controls.addWidget(QLabel("Force:"))
        self.force_disp_force_source = QComboBox()
        self.force_disp_force_source.addItems(
            ["Base shear", "Node reaction"]
        )
        self.force_disp_force_source.currentTextChanged.connect(
            self._update_force_displacement_controls
        )
        controls.addWidget(self.force_disp_force_source)

        controls.addWidget(QLabel("Force node:"))
        self.force_disp_force_node = QComboBox()
        self.force_disp_force_node.currentIndexChanged.connect(
            self._update_force_displacement_plot
        )
        controls.addWidget(self.force_disp_force_node)

        controls.addWidget(QLabel("DOF:"))
        self.force_disp_force_dof = QComboBox()
        self.force_disp_force_dof.addItems(
            ["FX", "FY", "FZ", "MX", "MY", "MZ"]
        )
        self.force_disp_force_dof.currentIndexChanged.connect(
            self._update_force_displacement_plot
        )
        controls.addWidget(self.force_disp_force_dof)

        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_force_displacement_csv)
        controls.addWidget(export)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.force_disp_info = QLabel(
            "Run a non-modal analysis to plot force versus displacement."
        )
        self.force_disp_info.setWordWrap(True)
        layout.addWidget(self.force_disp_info)

        self.force_disp_metrics = QLabel(
            "Points: -   Peak |F|: -   Peak |u|: -"
        )
        self.force_disp_metrics.setWordWrap(True)
        layout.addWidget(self.force_disp_metrics)

        self.force_disp_plot = TimeHistoryPlot(
            empty_message="No force-displacement data"
        )
        layout.addWidget(self.force_disp_plot, 1)
        self.tabs.addTab(page, "Force–Displacement")
        self._update_force_displacement_controls()

    def _build_section_response_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Section source:"))
        self.section_response_source = QComboBox()
        self.section_response_source.currentIndexChanged.connect(
            self._update_section_response_plot
        )
        controls.addWidget(self.section_response_source, 1)

        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_section_response_csv)
        controls.addWidget(export)
        layout.addLayout(controls)

        self.section_response_info = QLabel(
            "Create a Section Response result request for a "
            "zeroLengthSection or nonlinear beam-column section/IP."
        )
        self.section_response_info.setWordWrap(True)
        layout.addWidget(self.section_response_info)

        self.section_response_metrics = QLabel(
            "Points: -   Peak |Y|: -   Peak |X|: -   Final: -"
        )
        self.section_response_metrics.setWordWrap(True)
        layout.addWidget(self.section_response_metrics)

        self.section_response_plot = TimeHistoryPlot(
            empty_message="No section-response data"
        )
        layout.addWidget(self.section_response_plot, 1)
        self.tabs.addTab(page, "Section Response")

    def _populate_section_response_sources(self) -> None:
        previous = self.section_response_source.currentData()
        self.section_response_source.blockSignals(True)
        self.section_response_source.clear()
        specs = self._result.get("section_responses", {})
        if isinstance(specs, dict):
            for key, raw_spec in specs.items():
                if not isinstance(raw_spec, dict):
                    continue
                spec = dict(raw_spec)
                element_tag = spec.get("element_tag", "-")
                element_kind = str(spec.get("element_kind", "section"))
                section_number = spec.get("section_number", 1)
                pair_label = str(
                    spec.get(
                        "pair_label",
                        spec.get("component", "Section response"),
                    )
                )
                location = (
                    f" · IP {section_number}"
                    if spec.get("query_mode") == "indexed"
                    else ""
                )
                automatic = " · auto" if spec.get("automatic") else ""
                self.section_response_source.addItem(
                    f"{element_kind} {element_tag}{location} · "
                    f"{pair_label}{automatic}",
                    str(key),
                )
        if previous is not None:
            index = self.section_response_source.findData(previous)
            if index >= 0:
                self.section_response_source.setCurrentIndex(index)
        self.section_response_source.blockSignals(False)
        self._update_section_response_plot()

    def _select_section_response(
        self,
        options: dict[str, Any],
    ) -> None:
        element_scope = options.get("_element_scope", [])
        element_tag = None
        if isinstance(element_scope, (list, tuple)) and element_scope:
            try:
                element_tag = int(element_scope[0])
            except (TypeError, ValueError):
                element_tag = None
        try:
            section_number = int(options.get("section", 1))
        except (TypeError, ValueError):
            section_number = 1
        component = str(options.get("component", "Mz"))

        specs = self._result.get("section_responses", {})
        if not isinstance(specs, dict):
            return
        for key, raw_spec in specs.items():
            if not isinstance(raw_spec, dict):
                continue
            try:
                same_element = (
                    element_tag is None
                    or int(raw_spec.get("element_tag")) == element_tag
                )
                same_section = (
                    int(raw_spec.get("section_number", 1))
                    == section_number
                )
            except (TypeError, ValueError):
                continue
            if (
                same_element
                and same_section
                and str(raw_spec.get("component", "")) == component
            ):
                index = self.section_response_source.findData(str(key))
                if index >= 0:
                    self.section_response_source.setCurrentIndex(index)
                return

    def _current_section_response(
        self,
    ) -> tuple[list[float], list[float], dict[str, Any]]:
        key = self.section_response_source.currentData()
        specs = self._result.get("section_responses", {})
        if key is None or not isinstance(specs, dict):
            return [], [], {}
        raw_spec = specs.get(str(key), {})
        if not isinstance(raw_spec, dict):
            return [], [], {}
        spec = dict(raw_spec)
        try:
            return section_response_curve(
                self._result,
                element_tag=int(spec.get("element_tag")),
                section_number=int(spec.get("section_number", 1)),
                component=str(spec.get("component", "")),
            )
        except (TypeError, ValueError):
            return [], [], spec

    def _update_section_response_plot(self) -> None:
        x, y, spec = self._current_section_response()
        if not x or not y:
            if self.section_response_source.count():
                self.section_response_info.setText(
                    "Section response was requested, but no complete "
                    "force/deformation history is available."
                )
            else:
                self.section_response_info.setText(
                    "No Section Response was requested for this analysis. "
                    "Select one section-capable element, insert Section "
                    "Response, then run the analysis."
                )
            self.section_response_metrics.setText(
                "Points: -   Peak |Y|: -   Peak |X|: -   Final: -"
            )
            self.section_response_plot.set_series([], [])
            return

        element_tag = spec.get("element_tag", "-")
        source_kind = spec.get("element_kind", "section")
        section_number = spec.get("section_number", 1)
        location = (
            f" · IP {section_number}"
            if spec.get("query_mode") == "indexed"
            else ""
        )
        x_label = str(spec.get("deformation_label", "Section deformation"))
        y_label = str(spec.get("force_label", "Section force"))
        pair_label = str(spec.get("pair_label", "Section response"))
        self.section_response_info.setText(
            f"{source_kind} element {element_tag}{location} · "
            f"{pair_label} · X = {x_label} · Y = {y_label}"
        )
        self.section_response_metrics.setText(
            f"Points: {len(x)}   Peak |Y|: {max(abs(v) for v in y):.6g}   "
            f"Peak |X|: {max(abs(v) for v in x):.6g}   "
            f"Final: ({x[-1]:.6g}, {y[-1]:.6g})"
        )
        self.section_response_plot.set_series(x, y)

    def _export_section_response_csv(self) -> None:
        x, y, spec = self._current_section_response()
        if not x or not y:
            self.section_response_info.setText(
                "No section-response data is available to export."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Section Response",
            "section_response.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        x_label = str(spec.get("deformation_label", "Section deformation"))
        y_label = str(spec.get("force_label", "Section force"))
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow([
                x_label,
                y_label,
                "Element",
                "Section / IP",
                "Component",
            ])
            for x_value, y_value in zip(x, y):
                writer.writerow([
                    x_value,
                    y_value,
                    spec.get("element_tag", ""),
                    spec.get("section_number", 1),
                    spec.get("component", ""),
                ])
        self.section_response_info.setText(
            f"Exported {len(x)} section-response point(s) to {path}."
        )

    def _build_moment_curvature_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        self.moment_curvature_info = QLabel(
            "Run a recognized zeroLengthSection moment-curvature workflow "
            "to plot section moment versus curvature."
        )
        self.moment_curvature_info.setWordWrap(True)
        layout.addWidget(self.moment_curvature_info)

        self.moment_curvature_metrics = QLabel(
            "Points: -   Peak |M|: -   Peak |κ|: -   Final: -"
        )
        self.moment_curvature_metrics.setWordWrap(True)
        layout.addWidget(self.moment_curvature_metrics)

        row = QHBoxLayout()
        import_response = QPushButton("Import Response-2000...")
        import_response.clicked.connect(self._import_response2000_data)
        row.addWidget(import_response)

        paste_response = QPushButton("Paste Response-2000")
        paste_response.clicked.connect(self._paste_response2000_data)
        row.addWidget(paste_response)

        clear_response = QPushButton("Clear Response-2000")
        clear_response.clicked.connect(self._clear_response2000_data)
        row.addWidget(clear_response)

        send_to_hinge = QPushButton("Send to Hinge Backbone...")
        send_to_hinge.clicked.connect(
            self._send_moment_curvature_to_hinge
        )
        row.addWidget(send_to_hinge)

        row.addStretch(1)
        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_moment_curvature_csv)
        row.addWidget(export)
        layout.addLayout(row)

        self.moment_curvature_detail_tabs = CompactResultTabs()
        self.moment_curvature_detail_tabs.setDocumentMode(True)
        layout.addWidget(self.moment_curvature_detail_tabs, 1)

        curve_page = QWidget()
        curve_layout = QVBoxLayout(curve_page)
        curve_layout.setContentsMargins(3, 3, 3, 3)
        self.moment_curvature_plot = TimeHistoryPlot(
            empty_message="No moment-curvature data"
        )
        curve_layout.addWidget(self.moment_curvature_plot, 1)
        self.moment_curvature_detail_tabs.addTab(curve_page, "Curve")

        validation_page = QWidget()
        validation_layout = QVBoxLayout(validation_page)
        validation_layout.setContentsMargins(3, 3, 3, 3)
        validation_layout.setSpacing(3)

        self.response2000_controls = QWidget()
        response_controls_layout = QVBoxLayout(self.response2000_controls)
        response_controls_layout.setContentsMargins(0, 0, 0, 0)
        response_controls_layout.setSpacing(3)

        x_row = QHBoxLayout()
        x_row.addWidget(QLabel("Response κ:"))
        self.response2000_curvature_column = QComboBox()
        self.response2000_curvature_column.currentIndexChanged.connect(
            self._update_moment_curvature_plot
        )
        x_row.addWidget(self.response2000_curvature_column, 1)

        self.response2000_curvature_unit = QComboBox()
        for label, value in (
            ("Same as SARE", "same"),
            ("rad/km", "rad_per_km"),
            ("1/m", "per_m"),
            ("1/mm", "per_mm"),
            ("1/cm", "per_cm"),
            ("1/in", "per_in"),
            ("1/ft", "per_ft"),
        ):
            self.response2000_curvature_unit.addItem(label, value)
        self.response2000_curvature_unit.currentIndexChanged.connect(
            self._update_moment_curvature_plot
        )
        x_row.addWidget(self.response2000_curvature_unit)

        x_row.addWidget(QLabel("×"))
        self.response2000_curvature_factor = QDoubleSpinBox()
        self.response2000_curvature_factor.setRange(-1.0e12, 1.0e12)
        self.response2000_curvature_factor.setDecimals(8)
        self.response2000_curvature_factor.setValue(1.0)
        self.response2000_curvature_factor.setMaximumWidth(105)
        self.response2000_curvature_factor.valueChanged.connect(
            self._update_moment_curvature_plot
        )
        x_row.addWidget(self.response2000_curvature_factor)
        response_controls_layout.addLayout(x_row)

        y_row = QHBoxLayout()
        y_row.addWidget(QLabel("Response M:"))
        self.response2000_moment_column = QComboBox()
        self.response2000_moment_column.currentIndexChanged.connect(
            self._update_moment_curvature_plot
        )
        y_row.addWidget(self.response2000_moment_column, 1)

        self.response2000_moment_unit = QComboBox()
        for label, value in (
            ("Same as SARE", "same"),
            ("kN·m", "kn_m"),
            ("N·m", "n_m"),
            ("N·mm", "n_mm"),
            ("kN·mm", "kn_mm"),
            ("kip·ft", "kip_ft"),
            ("kip·in", "kip_in"),
            ("kgf·m", "kgf_m"),
            ("kgf·cm", "kgf_cm"),
        ):
            self.response2000_moment_unit.addItem(label, value)
        self.response2000_moment_unit.currentIndexChanged.connect(
            self._update_moment_curvature_plot
        )
        y_row.addWidget(self.response2000_moment_unit)

        y_row.addWidget(QLabel("×"))
        self.response2000_moment_factor = QDoubleSpinBox()
        self.response2000_moment_factor.setRange(-1.0e12, 1.0e12)
        self.response2000_moment_factor.setDecimals(8)
        self.response2000_moment_factor.setValue(1.0)
        self.response2000_moment_factor.setMaximumWidth(105)
        self.response2000_moment_factor.valueChanged.connect(
            self._update_moment_curvature_plot
        )
        y_row.addWidget(self.response2000_moment_factor)
        response_controls_layout.addLayout(y_row)

        self.response2000_info = QLabel(
            "Optional validation overlay: import chart data copied/exported "
            "from Response-2000 Moment-Curvature."
        )
        self.response2000_info.setWordWrap(True)
        response_controls_layout.addWidget(self.response2000_info)

        self.response2000_compare_table = QTableWidget(0, 4)
        self.response2000_compare_table.setHorizontalHeaderLabels(
            ["Validation metric", "SARE/OpenSees", "Response-2000", "Δ [%]"]
        )
        self.response2000_compare_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.response2000_compare_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.response2000_compare_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.response2000_compare_table.setAlternatingRowColors(True)
        self.response2000_compare_table.hide()
        response_controls_layout.addWidget(
            self.response2000_compare_table,
            1,
        )

        validation_layout.addWidget(self.response2000_controls, 1)
        self.moment_curvature_detail_tabs.addTab(
            validation_page,
            "Response-2000",
        )

        self.tabs.addTab(page, "Moment–Curvature")

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
        layout.setSpacing(5)

        # Keep the essential cyclic summary visible regardless of which
        # detail page is active.
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

        self.cyclic_detail_tabs = QTabWidget()
        self.cyclic_detail_tabs.setDocumentMode(True)
        layout.addWidget(self.cyclic_detail_tabs, 1)

        # --------------------------------------------------------------
        # CURVE
        # --------------------------------------------------------------
        curve_page = QWidget()
        curve_layout = QVBoxLayout(curve_page)
        curve_layout.setContentsMargins(4, 4, 4, 4)
        curve_layout.setSpacing(4)

        curve_controls = QHBoxLayout()
        curve_controls.addWidget(QLabel("View:"))
        self.cyclic_compare_view = QComboBox()
        self.cyclic_compare_view.addItem("Hysteresis", "hysteresis")
        self.cyclic_compare_view.addItem("Backbone / envelope", "backbone")
        self.cyclic_compare_view.currentIndexChanged.connect(
            self._update_cyclic_plot
        )
        curve_controls.addWidget(self.cyclic_compare_view)
        curve_controls.addStretch(1)
        curve_layout.addLayout(curve_controls)

        self.cyclic_plot = TimeHistoryPlot(
            empty_message="No cyclic hysteresis data"
        )
        self.cyclic_plot.setMinimumHeight(220)
        curve_layout.addWidget(self.cyclic_plot, 1)

        self.cyclic_detail_tabs.addTab(curve_page, "Curve")

        # --------------------------------------------------------------
        # EXPERIMENT
        # --------------------------------------------------------------
        experiment_page = QWidget()
        experiment_layout = QVBoxLayout(experiment_page)
        experiment_layout.setContentsMargins(4, 4, 4, 4)
        experiment_layout.setSpacing(5)

        experiment_buttons = QHBoxLayout()
        import_experiment = QPushButton("Import Experiment CSV")
        import_experiment.clicked.connect(
            self._import_cyclic_experiment_csv
        )
        experiment_buttons.addWidget(import_experiment)

        clear_experiment = QPushButton("Clear Experiment")
        clear_experiment.clicked.connect(
            self._clear_cyclic_experiment
        )
        experiment_buttons.addWidget(clear_experiment)
        experiment_buttons.addStretch(1)
        experiment_layout.addLayout(experiment_buttons)

        x_row = QHBoxLayout()
        x_row.addWidget(QLabel("Exp X:"))
        self.cyclic_exp_x_column = QComboBox()
        self.cyclic_exp_x_column.currentIndexChanged.connect(
            self._update_cyclic_plot
        )
        x_row.addWidget(self.cyclic_exp_x_column, 1)
        x_row.addWidget(QLabel("×"))
        self.cyclic_exp_x_scale = QDoubleSpinBox()
        self.cyclic_exp_x_scale.setRange(-1.0e9, 1.0e9)
        self.cyclic_exp_x_scale.setDecimals(8)
        self.cyclic_exp_x_scale.setValue(1.0)
        self.cyclic_exp_x_scale.valueChanged.connect(
            self._update_cyclic_plot
        )
        self.cyclic_exp_x_scale.setMaximumWidth(120)
        x_row.addWidget(self.cyclic_exp_x_scale)
        experiment_layout.addLayout(x_row)

        y_row = QHBoxLayout()
        y_row.addWidget(QLabel("Exp Y:"))
        self.cyclic_exp_y_column = QComboBox()
        self.cyclic_exp_y_column.currentIndexChanged.connect(
            self._update_cyclic_plot
        )
        y_row.addWidget(self.cyclic_exp_y_column, 1)
        y_row.addWidget(QLabel("×"))
        self.cyclic_exp_y_scale = QDoubleSpinBox()
        self.cyclic_exp_y_scale.setRange(-1.0e9, 1.0e9)
        self.cyclic_exp_y_scale.setDecimals(8)
        self.cyclic_exp_y_scale.setValue(1.0)
        self.cyclic_exp_y_scale.valueChanged.connect(
            self._update_cyclic_plot
        )
        self.cyclic_exp_y_scale.setMaximumWidth(120)
        y_row.addWidget(self.cyclic_exp_y_scale)
        experiment_layout.addLayout(y_row)

        self.cyclic_experiment_info = QLabel(
            "Optional: import experimental displacement-force CSV for "
            "overlay and descriptive validation metrics."
        )
        self.cyclic_experiment_info.setWordWrap(True)
        experiment_layout.addWidget(self.cyclic_experiment_info)

        self.cyclic_compare_table = QTableWidget(0, 4)
        self.cyclic_compare_table.setHorizontalHeaderLabels(
            ["Comparison metric", "OpenSees", "Experiment", "Δ vs exp [%]"]
        )
        self.cyclic_compare_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.cyclic_compare_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.cyclic_compare_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.cyclic_compare_table.setAlternatingRowColors(True)
        self.cyclic_compare_table.hide()
        experiment_layout.addWidget(self.cyclic_compare_table, 1)

        self.cyclic_detail_tabs.addTab(experiment_page, "Experiment")

        # --------------------------------------------------------------
        # REVERSALS
        # --------------------------------------------------------------
        reversal_page = QWidget()
        reversal_layout = QVBoxLayout(reversal_page)
        reversal_layout.setContentsMargins(4, 4, 4, 4)
        reversal_layout.setSpacing(4)

        research_row = QHBoxLayout()
        self.cyclic_research_info = QLabel(
            "1D-column research metrics appear here when specimen "
            "instrumentation is available."
        )
        self.cyclic_research_info.setWordWrap(True)
        research_row.addWidget(self.cyclic_research_info, 1)

        export_research = QPushButton("Export Research CSV")
        export_research.clicked.connect(
            self._export_cyclic_research_csv
        )
        research_row.addWidget(export_research)
        reversal_layout.addLayout(research_row)

        self.cyclic_reversal_table = QTableWidget(0, 20)
        self.cyclic_reversal_table.setHorizontalHeaderLabels(
            [
                "Rev",
                "u",
                "V",
                "Drift",
                "M",
                "κ",
                "εs",
                "εc",
                "Bond slip",
                "θint",
                "|Ksec|",
                "Strength / 1st",
                "Ksec / 1st",
                "E branch",
                "Cycle",
                "E cycle",
                "Vexp",
                "V err [%]",
                "Kexp",
                "K err [%]",
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
        self.cyclic_reversal_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.cyclic_reversal_table.setAlternatingRowColors(True)
        self.cyclic_reversal_table.verticalHeader().setVisible(False)
        reversal_layout.addWidget(self.cyclic_reversal_table, 1)

        self.cyclic_detail_tabs.addTab(reversal_page, "Reversals")

        # --------------------------------------------------------------
        # CYCLES
        # --------------------------------------------------------------
        cycle_page = QWidget()
        cycle_layout = QVBoxLayout(cycle_page)
        cycle_layout.setContentsMargins(4, 4, 4, 4)

        self.cyclic_cycle_table = QTableWidget(0, 8)
        self.cyclic_cycle_table.setHorizontalHeaderLabels(
            [
                "Cycle",
                "End rev",
                "|u|",
                "Repeat",
                "E loop",
                "E interface",
                "Strength / 1st",
                "Ksec / 1st",
            ]
        )
        self.cyclic_cycle_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.cyclic_cycle_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.cyclic_cycle_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.cyclic_cycle_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.cyclic_cycle_table.setAlternatingRowColors(True)
        self.cyclic_cycle_table.verticalHeader().setVisible(False)
        cycle_layout.addWidget(self.cyclic_cycle_table, 1)

        self.cyclic_detail_tabs.addTab(cycle_page, "Cycles")

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
            ("8×", 8.0),
            ("16×", 16.0),
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
        layout.setSpacing(4)

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

        self.specimen_detail_tabs = CompactResultTabs()
        self.specimen_detail_tabs.setDocumentMode(True)
        layout.addWidget(self.specimen_detail_tabs, 1)

        response_page = QWidget()
        response_layout = QVBoxLayout(response_page)
        response_layout.setContentsMargins(3, 3, 3, 3)
        response_layout.setSpacing(4)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Response:"))
        self.specimen_quantity = QComboBox()
        self.specimen_quantity.currentIndexChanged.connect(
            self._update_specimen_view
        )
        controls.addWidget(self.specimen_quantity, 1)
        import_specimen_experiment = QPushButton("Import Experiment CSV")
        import_specimen_experiment.clicked.connect(
            self._import_cyclic_experiment_csv
        )
        controls.addWidget(import_specimen_experiment)
        response_layout.addLayout(controls)

        experiment_controls = QHBoxLayout()
        experiment_controls.addWidget(QLabel("Exp X:"))
        self.specimen_exp_x_column = QComboBox()
        self.specimen_exp_x_column.currentIndexChanged.connect(
            self._update_specimen_view
        )
        experiment_controls.addWidget(self.specimen_exp_x_column, 1)
        experiment_controls.addWidget(QLabel("×"))
        self.specimen_exp_x_scale = QDoubleSpinBox()
        self.specimen_exp_x_scale.setRange(-1.0e9, 1.0e9)
        self.specimen_exp_x_scale.setDecimals(8)
        self.specimen_exp_x_scale.setValue(1.0)
        self.specimen_exp_x_scale.valueChanged.connect(
            self._update_specimen_view
        )
        experiment_controls.addWidget(self.specimen_exp_x_scale)

        experiment_controls.addWidget(QLabel("Exp Y:"))
        self.specimen_exp_y_column = QComboBox()
        self.specimen_exp_y_column.currentIndexChanged.connect(
            self._update_specimen_view
        )
        experiment_controls.addWidget(self.specimen_exp_y_column, 1)
        experiment_controls.addWidget(QLabel("×"))
        self.specimen_exp_y_scale = QDoubleSpinBox()
        self.specimen_exp_y_scale.setRange(-1.0e9, 1.0e9)
        self.specimen_exp_y_scale.setDecimals(8)
        self.specimen_exp_y_scale.setValue(1.0)
        self.specimen_exp_y_scale.valueChanged.connect(
            self._update_specimen_view
        )
        experiment_controls.addWidget(self.specimen_exp_y_scale)
        response_layout.addLayout(experiment_controls)

        self.specimen_experiment_info = QLabel(
            "Experimental overlay is optional. For M–κ select curvature "
            "as X and moment as Y."
        )
        self.specimen_experiment_info.setWordWrap(True)
        response_layout.addWidget(self.specimen_experiment_info)

        self.specimen_plot = TimeHistoryPlot(
            empty_message="No 1D-column specimen response data"
        )
        response_layout.addWidget(self.specimen_plot, 1)
        self.specimen_detail_tabs.addTab(response_page, "Response")

        research_page = QWidget()
        research_layout = QVBoxLayout(research_page)
        research_layout.setContentsMargins(3, 3, 3, 3)
        self.specimen_research_table = QTableWidget(0, 3)
        self.specimen_research_table.setHorizontalHeaderLabels([
            "Research metric",
            "Value",
            "Interpretation",
        ])
        self.specimen_research_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.specimen_research_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.specimen_research_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        research_layout.addWidget(self.specimen_research_table, 1)
        self.specimen_detail_tabs.addTab(
            research_page,
            "Research Metrics",
        )

        fiber_page = QWidget()
        fiber_layout = QVBoxLayout(fiber_page)
        fiber_layout.setContentsMargins(3, 3, 3, 3)
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
        fiber_layout.addWidget(self.specimen_fiber_table, 1)
        self.specimen_detail_tabs.addTab(fiber_page, "Fiber History")

        self.tabs.addTab(page, "Specimen Response")

    def _build_calibration_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.calibration_info = QLabel(
            "Run a Calibration / Parameter Study to compare batch cases "
            "against experimental cyclic data."
        )
        self.calibration_info.setWordWrap(True)
        layout.addWidget(self.calibration_info)

        controls = QHBoxLayout()
        self.calibration_apply = QPushButton("Apply Selected to Model...")
        self.calibration_apply.setEnabled(False)
        self.calibration_apply.setToolTip(
            "Preview and apply the selected scored calibration case "
            "to the project material parameters"
        )
        self.calibration_apply.clicked.connect(
            self._request_apply_calibration_case
        )
        controls.addWidget(self.calibration_apply)

        export = QPushButton("Export Calibration CSV")
        export.clicked.connect(self._export_calibration_csv)
        controls.addWidget(export)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.calibration_detail_tabs = CompactResultTabs()
        self.calibration_detail_tabs.setDocumentMode(True)
        layout.addWidget(self.calibration_detail_tabs, 1)

        history_page = QWidget()
        history_page_layout = QVBoxLayout(history_page)
        history_page_layout.setContentsMargins(3, 3, 3, 3)

        history_splitter = QSplitter(Qt.Horizontal)

        score_page = QWidget()
        score_layout = QVBoxLayout(score_page)
        score_layout.setContentsMargins(0, 0, 0, 0)
        self.calibration_score_info = QLabel(
            "Best score vs cumulative analyses"
        )
        self.calibration_score_info.setWordWrap(True)
        score_layout.addWidget(self.calibration_score_info)
        self.calibration_score_plot = TimeHistoryPlot(
            empty_message="No scored calibration history"
        )
        self.calibration_score_plot.setMinimumHeight(150)
        score_layout.addWidget(self.calibration_score_plot, 1)
        history_splitter.addWidget(score_page)

        parameter_page = QWidget()
        parameter_layout = QVBoxLayout(parameter_page)
        parameter_layout.setContentsMargins(0, 0, 0, 0)
        parameter_controls = QHBoxLayout()
        parameter_controls.addWidget(QLabel("Round-best parameter:"))
        self.calibration_parameter_combo = QComboBox()
        self.calibration_parameter_combo.currentIndexChanged.connect(
            self._update_calibration_parameter_plot
        )
        parameter_controls.addWidget(
            self.calibration_parameter_combo,
            1,
        )
        parameter_layout.addLayout(parameter_controls)
        self.calibration_parameter_info = QLabel(
            "Select a parameter to inspect its best-case path by round."
        )
        self.calibration_parameter_info.setWordWrap(True)
        parameter_layout.addWidget(self.calibration_parameter_info)
        self.calibration_parameter_plot = TimeHistoryPlot(
            empty_message="Need at least two round-best points"
        )
        self.calibration_parameter_plot.setMinimumHeight(150)
        parameter_layout.addWidget(
            self.calibration_parameter_plot,
            1,
        )
        history_splitter.addWidget(parameter_page)

        history_splitter.setStretchFactor(0, 1)
        history_splitter.setStretchFactor(1, 1)
        history_page_layout.addWidget(history_splitter, 1)
        self.calibration_detail_tabs.addTab(history_page, "History")

        pareto_page = QWidget()
        pareto_layout = QVBoxLayout(pareto_page)
        pareto_layout.setContentsMargins(3, 3, 3, 3)
        pareto_controls = QHBoxLayout()
        pareto_controls.addWidget(QLabel("X:"))
        self.calibration_pareto_x = QComboBox()
        self.calibration_pareto_x.currentIndexChanged.connect(
            self._update_calibration_pareto_plot
        )
        pareto_controls.addWidget(self.calibration_pareto_x, 1)
        pareto_controls.addWidget(QLabel("Y:"))
        self.calibration_pareto_y = QComboBox()
        self.calibration_pareto_y.currentIndexChanged.connect(
            self._update_calibration_pareto_plot
        )
        pareto_controls.addWidget(self.calibration_pareto_y, 1)
        pareto_layout.addLayout(pareto_controls)
        self.calibration_pareto_info = QLabel(
            "Pareto rank uses all active nonzero-weight objectives."
        )
        self.calibration_pareto_info.setWordWrap(True)
        pareto_layout.addWidget(self.calibration_pareto_info)
        self.calibration_pareto_plot = CalibrationParetoPlot()
        self.calibration_pareto_plot.point_selected.connect(
            self._calibration_pareto_job_selected
        )
        pareto_layout.addWidget(self.calibration_pareto_plot, 1)
        self.calibration_detail_tabs.addTab(pareto_page, "Pareto")

        cases_page = QWidget()
        cases_layout = QVBoxLayout(cases_page)
        cases_layout.setContentsMargins(3, 3, 3, 3)

        self.calibration_table = QTableWidget(0, 11)
        self.calibration_table.setHorizontalHeaderLabels(
            [
                "Rank",
                "Job",
                "Round",
                "Score [%]",
                "Peak |V| err [%]",
                "Reversal NRMSE [%]",
                "Cycle energy err [%]",
                "Matched rev.",
                "Parameters",
                "Pareto",
                "Status",
            ]
        )
        self.calibration_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.calibration_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.calibration_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.calibration_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.calibration_table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.calibration_table.cellDoubleClicked.connect(
            self._calibration_row_activated
        )
        self.calibration_table.itemSelectionChanged.connect(
            self._calibration_selection_changed
        )
        cases_layout.addWidget(self.calibration_table, 1)

        note = QLabel(
            "Score is the weighted mean of available absolute percentage "
            "errors. Lower is closer to the imported experiment; no "
            "pass/fail criterion is implied."
        )
        note.setWordWrap(True)
        cases_layout.addWidget(note)
        self.calibration_detail_tabs.addTab(cases_page, "Cases")

        self.tabs.addTab(page, "Calibration")

    def show_calibration(self) -> None:
        self._select_tab("Calibration")

    @staticmethod
    def _calibration_metric_text(value: Any) -> str:
        if value is None:
            return "-"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        if not math.isfinite(number):
            return "-"
        return f"{number:.6g}"

    def set_calibration_results(
        self,
        rows: list[dict[str, Any]],
    ) -> None:
        self._calibration_rows = [
            dict(row)
            for row in rows
            if isinstance(row, dict)
        ]
        self.calibration_table.setRowCount(
            len(self._calibration_rows)
        )
        successful = 0
        for row_index, row in enumerate(self._calibration_rows):
            components = row.get("components", {})
            if not isinstance(components, dict):
                components = {}
            score = row.get("score")
            if score is not None:
                try:
                    if math.isfinite(float(score)):
                        successful += 1
                except (TypeError, ValueError):
                    pass
            parameters = row.get("values", {})
            if isinstance(parameters, dict):
                parameter_text = ", ".join(
                    f"{calibration_parameter_label(str(key))}="
                    f"{float(value):.6g}"
                    for key, value in sorted(parameters.items())
                )
            else:
                parameter_text = "-"
            values = [
                (
                    str(row.get("rank"))
                    if row.get("rank") is not None
                    else "-"
                ),
                (
                    str(row.get("job_id"))
                    if row.get("job_id") is not None
                    else "-"
                ),
                str(int(row.get("round", 1) or 1)),
                self._calibration_metric_text(score),
                self._calibration_metric_text(
                    components.get("peak_force")
                ),
                self._calibration_metric_text(
                    components.get("reversal_nrmse")
                ),
                self._calibration_metric_text(
                    components.get("cycle_energy")
                ),
                str(row.get("matched_reversal_count", 0)),
                parameter_text or "-",
                (
                    f"P{int(row.get('pareto_rank'))}"
                    if row.get("pareto_rank") is not None
                    else "-"
                ),
                str(row.get("status", "-")),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1 and row.get("job_id") is not None:
                    item.setData(
                        Qt.UserRole,
                        int(row["job_id"]),
                    )
                self.calibration_table.setItem(
                    row_index,
                    column,
                    item,
                )

        max_round = max(
            (
                int(row.get("round", 1) or 1)
                for row in self._calibration_rows
            ),
            default=1,
        )
        round_text = (
            f" · {max_round} refinement round(s)"
            if max_round > 1
            else ""
        )
        pareto_front_count = sum(
            1
            for row in self._calibration_rows
            if bool(row.get("pareto_front"))
        )
        pareto_text = (
            f" · {pareto_front_count} global Pareto P1 case(s)"
            if pareto_front_count
            else ""
        )
        self.calibration_info.setText(
            f"{len(self._calibration_rows)} case(s) · "
            f"{successful} scored case(s){round_text}{pareto_text}. "
            "Double-click a row to activate its result; select a scored "
            "row to preview/apply its parameters to the model."
        )
        self.calibration_apply.setEnabled(False)
        self._update_calibration_history()

    def _update_calibration_history(self) -> None:
        history = calibration_best_score_history(
            self._calibration_rows
        )
        x = [
            float(value)
            for value in history.get(
                "cumulative_analyses",
                [],
            )
        ]
        y = [
            float(value)
            for value in history.get("best_score", [])
        ]
        self.calibration_score_plot.set_series(x, y)
        self.calibration_score_plot.clear_overlay()

        if y:
            initial = y[0]
            final = y[-1]
            improvement = (
                (initial - final) / abs(initial) * 100.0
                if abs(initial) > 1.0e-15
                else 0.0
            )
            self.calibration_score_info.setText(
                "Best score vs cumulative analyses · "
                f"initial {initial:.6g}% → best {final:.6g}% · "
                f"relative improvement {improvement:.3g}%"
            )
        else:
            self.calibration_score_info.setText(
                "Best score vs cumulative analyses · "
                "no valid scored case"
            )

        current_key = self.calibration_parameter_combo.currentData()
        self.calibration_parameter_combo.blockSignals(True)
        self.calibration_parameter_combo.clear()
        keys = calibration_parameter_keys(
            self._calibration_rows
        )
        for key in keys:
            self.calibration_parameter_combo.addItem(
                calibration_parameter_label(key),
                key,
            )
        if current_key in keys:
            self.calibration_parameter_combo.setCurrentIndex(
                keys.index(current_key)
            )
        elif keys:
            self.calibration_parameter_combo.setCurrentIndex(0)
        self.calibration_parameter_combo.blockSignals(False)
        self._update_calibration_parameter_plot()
        self._update_calibration_pareto_controls()

    def _update_calibration_pareto_controls(self) -> None:
        objectives = calibration_available_objectives(
            self._calibration_rows
        )
        current_x = self.calibration_pareto_x.currentData()
        current_y = self.calibration_pareto_y.currentData()
        self.calibration_pareto_x.blockSignals(True)
        self.calibration_pareto_y.blockSignals(True)
        self.calibration_pareto_x.clear()
        self.calibration_pareto_y.clear()
        for key in objectives:
            label = calibration_objective_label(key)
            self.calibration_pareto_x.addItem(label, key)
            self.calibration_pareto_y.addItem(label, key)

        if objectives:
            x_key = (
                str(current_x)
                if current_x in objectives
                else (
                    "peak_force"
                    if "peak_force" in objectives
                    else objectives[0]
                )
            )
            y_default = (
                "cycle_energy"
                if "cycle_energy" in objectives
                else (
                    "reversal_nrmse"
                    if "reversal_nrmse" in objectives
                    else objectives[min(1, len(objectives) - 1)]
                )
            )
            y_key = (
                str(current_y)
                if current_y in objectives
                else y_default
            )
            self.calibration_pareto_x.setCurrentIndex(
                objectives.index(x_key)
            )
            self.calibration_pareto_y.setCurrentIndex(
                objectives.index(y_key)
            )
        self.calibration_pareto_x.blockSignals(False)
        self.calibration_pareto_y.blockSignals(False)
        self._update_calibration_pareto_plot()

    def _update_calibration_pareto_plot(
        self,
        *_args,
    ) -> None:
        x_key = self.calibration_pareto_x.currentData()
        y_key = self.calibration_pareto_y.currentData()
        if not x_key or not y_key:
            self.calibration_pareto_plot.clear()
            self.calibration_pareto_info.setText(
                "Pareto plot needs finite objective components."
            )
            return

        points = calibration_pareto_projection(
            self._calibration_rows,
            str(x_key),
            str(y_key),
        )
        self.calibration_pareto_plot.set_points(
            points,
            x_label=calibration_objective_label(str(x_key)),
            y_label=calibration_objective_label(str(y_key)),
        )
        global_front = sum(
            1
            for point in points
            if bool(point.get("global_pareto_front"))
        )
        projection_front = sum(
            1
            for point in points
            if bool(point.get("projection_front"))
        )
        objective_keys: list[str] = []
        for row in self._calibration_rows:
            raw = row.get("pareto_objectives", [])
            if isinstance(raw, list) and raw:
                objective_keys = [str(key) for key in raw]
                break
        objective_text = ", ".join(
            calibration_objective_label(key)
            for key in objective_keys
        ) or "none"
        self.calibration_pareto_info.setText(
            f"{len(points)} finite case(s) · global P1: {global_front} · "
            f"selected-axis front: {projection_front}. "
            f"Global Pareto objectives: {objective_text}."
        )

    def _calibration_pareto_job_selected(self, job_id: int) -> None:
        target = int(job_id)
        for row_index, row in enumerate(self._calibration_rows):
            try:
                row_job = int(row.get("job_id"))
            except (TypeError, ValueError):
                continue
            if row_job != target:
                continue
            self.calibration_table.selectRow(row_index)
            break
        self.job_selected.emit(target)

    def _update_calibration_parameter_plot(
        self,
        *_args,
    ) -> None:
        key = self.calibration_parameter_combo.currentData()
        if not key:
            self.calibration_parameter_plot.set_series([], [])
            self.calibration_parameter_info.setText(
                "No calibration parameter history is available."
            )
            return

        series = calibration_round_best_parameter_series(
            self._calibration_rows,
            str(key),
        )
        rounds = [
            float(value)
            for value in series.get("rounds", [])
        ]
        values = [
            float(value)
            for value in series.get("values", [])
        ]
        case_ids = [
            int(value)
            for value in series.get("case_ids", [])
        ]
        scores = [
            float(value)
            for value in series.get("scores", [])
        ]
        self.calibration_parameter_plot.set_series(
            rounds,
            values,
        )
        self.calibration_parameter_plot.clear_overlay()

        label = calibration_parameter_label(str(key))
        if not values:
            self.calibration_parameter_info.setText(
                f"{label} · no scored round-best history"
            )
            return
        path = " → ".join(
            f"R{int(round_index)} C{case_id}: {value:.6g}"
            for round_index, case_id, value in zip(
                rounds,
                case_ids,
                values,
            )
        )
        score_tail = (
            f" · final round-best score {scores[-1]:.6g}%"
            if scores
            else ""
        )
        self.calibration_parameter_info.setText(
            f"{label} round-best trajectory · {path}{score_tail}"
        )

    def _selected_calibration_row(self) -> dict[str, Any] | None:
        selected = self.calibration_table.selectionModel().selectedRows()
        if not selected:
            return None
        row = int(selected[0].row())
        if row < 0 or row >= len(self._calibration_rows):
            return None
        item = self._calibration_rows[row]
        return dict(item) if isinstance(item, dict) else None

    def _calibration_selection_changed(self) -> None:
        row = self._selected_calibration_row()
        valid = False
        if isinstance(row, dict):
            score = row.get("score")
            values = row.get("values")
            try:
                valid_score = score is not None and math.isfinite(
                    float(score)
                )
            except (TypeError, ValueError):
                valid_score = False
            valid = (
                valid_score
                and str(row.get("status", "")).lower() == "scored"
                and isinstance(values, dict)
                and bool(values)
            )
        self.calibration_apply.setEnabled(valid)
        selected_job = None
        if isinstance(row, dict) and row.get("job_id") is not None:
            try:
                selected_job = int(row.get("job_id"))
            except (TypeError, ValueError):
                selected_job = None
        self.calibration_pareto_plot.set_selected_job(selected_job)

    def _request_apply_calibration_case(self) -> None:
        row = self._selected_calibration_row()
        if row is None:
            self.calibration_info.setText(
                "Select a scored calibration case before applying it."
            )
            return
        score = row.get("score")
        try:
            valid_score = score is not None and math.isfinite(float(score))
        except (TypeError, ValueError):
            valid_score = False
        if (
            not valid_score
            or str(row.get("status", "")).lower() != "scored"
            or not isinstance(row.get("values"), dict)
            or not row.get("values")
        ):
            self.calibration_info.setText(
                "Only a successfully scored calibration case can be applied."
            )
            return
        self.calibration_case_apply_requested.emit(row)

    def _calibration_row_activated(
        self,
        row: int,
        _column: int,
    ) -> None:
        item = self.calibration_table.item(row, 1)
        if item is None:
            return
        job_id = item.data(Qt.UserRole)
        if job_id is not None:
            self.job_selected.emit(int(job_id))

    def _export_calibration_csv(self) -> None:
        if not self._calibration_rows:
            self.calibration_info.setText(
                "No calibration results are available to export."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Calibration Results",
            "calibration_results.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        parameter_keys = sorted(
            {
                str(key)
                for row in self._calibration_rows
                for key in (
                    row.get("values", {}).keys()
                    if isinstance(row.get("values"), dict)
                    else []
                )
            }
        )
        fields = [
            "rank",
            "job_id",
            "case_id",
            "round",
            "round_case",
            "score_percent",
            "peak_force_error_percent",
            "reversal_force_nrmse_percent",
            "cycle_energy_error_percent",
            "max_displacement_error_percent",
            "matched_reversal_count",
            "pareto_rank",
            "pareto_front",
            "pareto_eligible",
            "pareto_objectives",
            "status",
            *parameter_keys,
        ]
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in self._calibration_rows:
                components = row.get("components", {})
                if not isinstance(components, dict):
                    components = {}
                values = row.get("values", {})
                if not isinstance(values, dict):
                    values = {}
                output = {
                    "rank": row.get("rank"),
                    "job_id": row.get("job_id"),
                    "case_id": row.get("case_id"),
                    "round": row.get("round", 1),
                    "round_case": row.get("round_case"),
                    "score_percent": row.get("score"),
                    "peak_force_error_percent": components.get(
                        "peak_force"
                    ),
                    "reversal_force_nrmse_percent": components.get(
                        "reversal_nrmse"
                    ),
                    "cycle_energy_error_percent": components.get(
                        "cycle_energy"
                    ),
                    "max_displacement_error_percent": components.get(
                        "max_displacement"
                    ),
                    "matched_reversal_count": row.get(
                        "matched_reversal_count",
                        0,
                    ),
                    "pareto_rank": row.get("pareto_rank"),
                    "pareto_front": bool(row.get("pareto_front")),
                    "pareto_eligible": bool(row.get("pareto_eligible")),
                    "pareto_objectives": ";".join(
                        str(key)
                        for key in row.get("pareto_objectives", [])
                    ) if isinstance(
                        row.get("pareto_objectives"),
                        list,
                    ) else "",
                    "status": row.get("status"),
                }
                for key in parameter_keys:
                    output[key] = values.get(key)
                writer.writerow(output)
        self.calibration_info.setText(
            f"Exported {len(self._calibration_rows)} calibration case(s) "
            f"to {path}"
        )

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
        self.modal_mass_coverage.setText(
            "Cumulative translational modal mass: -"
        )
        self.force_disp_node.clear()
        self.force_disp_force_node.clear()
        self.force_disp_info.setText(
            "Run a non-modal analysis to plot force versus displacement."
        )
        self.force_disp_metrics.setText(
            "Points: -   Peak |F|: -   Peak |u|: -"
        )
        self.force_disp_plot.set_series([], [])
        self.section_response_source.clear()
        self.section_response_info.setText(
            "Create a Section Response result request for a "
            "zeroLengthSection or nonlinear beam-column section/IP."
        )
        self.section_response_metrics.setText(
            "Points: -   Peak |Y|: -   Peak |X|: -   Final: -"
        )
        self.section_response_plot.set_series([], [])
        self.moment_curvature_info.setText(
            "Run a recognized zeroLengthSection moment-curvature workflow "
            "to plot section moment versus curvature."
        )
        self.moment_curvature_metrics.setText(
            "Points: -   Peak |M|: -   Peak |κ|: -   Final: -"
        )
        self.moment_curvature_plot.set_series([], [])
        self.pushover_info.setText(
            "Run a Pushover analysis to plot applied base shear versus "
            "control-node displacement."
        )
        self.pushover_metrics.setText(
            "Vpeak: -   u@Vpeak: -   ufinal: -"
        )
        self.pushover_plot.set_series([], [])
        self.cyclic_plot.set_series([], [])
        self.cyclic_plot.clear_overlay()
        self.cyclic_reversal_table.setRowCount(0)
        self.cyclic_compare_table.setRowCount(0)
        self.cyclic_compare_table.hide()
        self._cyclic_experiment_dataset = {}
        self._cyclic_experiment_path = ""
        self.cyclic_exp_x_column.clear()
        self.cyclic_exp_y_column.clear()
        self.specimen_exp_x_column.clear()
        self.specimen_exp_y_column.clear()
        self.specimen_exp_x_column.addItem("(none)", -1)
        self.specimen_exp_y_column.addItem("(none)", -1)
        self.specimen_plot.clear_overlay()
        self.specimen_experiment_info.setText(
            "Experimental overlay is optional. For M–κ select curvature "
            "as X and moment as Y."
        )
        self.cyclic_info.setText(
            "Run a Cyclic analysis to plot applied base shear versus "
            "control displacement."
        )
        self.cyclic_metrics.setText(
            "Peak |u|: -   +Vpeak: -   -Vpeak: -   "
            "Hysteretic energy: -   Closed cycles: -"
        )
        self._calibration_rows = []
        self.calibration_table.setRowCount(0)
        self.calibration_apply.setEnabled(False)
        self.calibration_score_plot.set_series([], [])
        self.calibration_parameter_plot.set_series([], [])
        self.calibration_parameter_combo.clear()
        self.calibration_pareto_x.clear()
        self.calibration_pareto_y.clear()
        self.calibration_pareto_plot.clear()
        self.calibration_pareto_info.setText(
            "Pareto rank uses all active nonzero-weight objectives."
        )
        self.calibration_score_info.setText(
            "Best score vs cumulative analyses"
        )
        self.calibration_parameter_info.setText(
            "Select a parameter to inspect its best-case path by round."
        )
        self.calibration_info.setText(
            "Run a Calibration / Parameter Study to compare batch cases "
            "against experimental cyclic data."
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

        active_dofs: set[int] = set()
        for key in ordered:
            participation = modes.get(key, {}).get("participation", {})
            if not isinstance(participation, dict):
                continue
            for raw_dof in participation:
                try:
                    dof = int(raw_dof)
                except (TypeError, ValueError):
                    continue
                if dof in {1, 2, 3}:
                    active_dofs.add(dof)

        cumulative = [0.0, 0.0, 0.0]
        for row, key in enumerate(ordered):
            mode = modes.get(key, {})
            eigenvalue = float(mode.get("eigenvalue", 0.0) or 0.0)
            frequency = mode.get("frequency_hz")
            period = mode.get("period_s")
            participation = mode.get("participation", {})
            ratio_text: list[str] = []
            cumulative_text: list[str] = []
            for dof in (1, 2, 3):
                if dof not in active_dofs:
                    ratio_text.append("-")
                    cumulative_text.append("-")
                    continue
                item = (
                    participation.get(str(dof), {})
                    if isinstance(participation, dict)
                    else {}
                )
                ratio = 100.0 * float(
                    item.get("mass_ratio", 0.0) or 0.0
                )
                cumulative[dof - 1] += ratio
                ratio_text.append(f"{ratio:.3f}")
                cumulative_text.append(f"{cumulative[dof - 1]:.3f}")

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
                *ratio_text,
                *cumulative_text,
            ]
            for column, value in enumerate(values):
                self.modal_summary_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

        if not ordered or not active_dofs:
            self.modal_mass_coverage.setText(
                "Cumulative translational modal mass: -"
            )
            return

        modal_summary = (
            self._result.get("modal_summary", {})
            if isinstance(self._result, dict)
            else {}
        )
        total_free_mass = (
            modal_summary.get("total_free_mass", {})
            if isinstance(modal_summary, dict)
            else {}
        )
        relevant_dofs: list[int] = []
        for dof in sorted(active_dofs):
            if isinstance(total_free_mass, dict) and total_free_mass:
                try:
                    free_mass = float(total_free_mass.get(str(dof), 0.0) or 0.0)
                except (TypeError, ValueError):
                    free_mass = 0.0
                if free_mass <= 0.0:
                    continue
            relevant_dofs.append(dof)

        if not relevant_dofs:
            self.modal_mass_coverage.setText(
                "Cumulative translational modal mass: no positive free mass."
            )
            return

        labels = {1: "UX", 2: "UY", 3: "UZ"}
        coverage = " · ".join(
            f"{labels[dof]}={cumulative[dof - 1]:.2f}%"
            for dof in relevant_dofs
        )
        below_reference = [
            labels[dof]
            for dof in relevant_dofs
            if cumulative[dof - 1] < 90.0 - 1.0e-9
        ]
        if below_reference:
            warning = (
                " · QA warning: below 90% reference in "
                + ", ".join(below_reference)
                + "; consider extracting more modes."
            )
        else:
            warning = " · All shown translational directions ≥ 90% reference."
        self.modal_mass_coverage.setText(
            "Cumulative translational modal mass: "
            + coverage
            + warning
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
            if not isinstance(participation, dict):
                continue
            item = participation.get(str(dof))
            if not isinstance(item, dict) or "mass_ratio" not in item:
                continue
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
        mass_suffix = (
            " · " + " · ".join(mass_text)
            if mass_text
            else ""
        )
        self.mode_info.setText(
            f"Mode {int(mode_number)} · λ={eigenvalue:.6g} · "
            f"f={frequency_text} · T={period_text}"
            + mass_suffix
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
        self._populate_force_displacement_nodes()
        self._update_force_displacement_plot()
        self._populate_section_response_sources()
        self._update_moment_curvature_plot()
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

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_response2000_dataset(
        self,
        dataset: dict[str, Any],
        *,
        path: str = "",
        source_name: str = "",
    ) -> bool:
        headers = dataset.get("headers", [])
        rows = dataset.get("rows", [])
        if (
            not isinstance(headers, (list, tuple))
            or len(headers) < 2
            or not isinstance(rows, (list, tuple))
            or not rows
        ):
            self.response2000_info.setText(
                "No usable two-column numeric chart data was found. "
                "Use Response-2000 > right-click Moment-Curvature chart > "
                "Copy Chart Data / View Data and import or paste the numeric "
                "table."
            )
            self.response2000_controls.show()
            return False

        self._response2000_dataset = dict(dataset)
        self._response2000_path = str(path)
        self._response2000_source_name = (
            str(source_name).strip()
            or (
                str(path).replace("\\", "/").split("/")[-1]
                if path
                else "Response-2000 data"
            )
        )

        self.response2000_curvature_column.blockSignals(True)
        self.response2000_moment_column.blockSignals(True)
        try:
            self.response2000_curvature_column.clear()
            self.response2000_moment_column.clear()
            for index, header in enumerate(headers):
                label = str(header)
                self.response2000_curvature_column.addItem(label, index)
                self.response2000_moment_column.addItem(label, index)

            x_index, y_index = suggest_response2000_columns(headers)
            self.response2000_curvature_column.setCurrentIndex(
                max(0, min(int(x_index), len(headers) - 1))
            )
            self.response2000_moment_column.setCurrentIndex(
                max(0, min(int(y_index), len(headers) - 1))
            )
        finally:
            self.response2000_curvature_column.blockSignals(False)
            self.response2000_moment_column.blockSignals(False)

        curvature_header = str(
            headers[self.response2000_curvature_column.currentIndex()]
        )
        moment_header = str(
            headers[self.response2000_moment_column.currentIndex()]
        )
        x_unit, y_unit = suggest_response2000_units(
            curvature_header,
            moment_header,
        )
        self.response2000_curvature_unit.blockSignals(True)
        self.response2000_moment_unit.blockSignals(True)
        try:
            self._set_combo_data(
                self.response2000_curvature_unit,
                x_unit,
            )
            self._set_combo_data(
                self.response2000_moment_unit,
                y_unit,
            )
        finally:
            self.response2000_curvature_unit.blockSignals(False)
            self.response2000_moment_unit.blockSignals(False)

        self.response2000_curvature_factor.blockSignals(True)
        self.response2000_moment_factor.blockSignals(True)
        try:
            self.response2000_curvature_factor.setValue(1.0)
            self.response2000_moment_factor.setValue(1.0)
        finally:
            self.response2000_curvature_factor.blockSignals(False)
            self.response2000_moment_factor.blockSignals(False)

        self.response2000_controls.show()
        self._update_moment_curvature_plot()
        return True

    def _import_response2000_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Response-2000 Moment-Curvature Data",
            "",
            (
                "Response/chart data (*.txt *.csv *.tsv *.dat);;"
                "All files (*)"
            ),
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as stream:
                dataset = parse_response2000_chart_text(stream.read())
        except (OSError, UnicodeError) as exc:
            self.response2000_info.setText(
                f"Could not read Response-2000 data: {exc}"
            )
            self.response2000_controls.show()
            return

        self._apply_response2000_dataset(dataset, path=path)

    def _paste_response2000_data(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        if not str(text).strip():
            self.response2000_info.setText(
                "Clipboard is empty. In Response-2000, right-click the "
                "Moment-Curvature chart and choose Copy Chart Data first."
            )
            self.response2000_controls.show()
            return
        dataset = parse_response2000_chart_text(text)
        self._apply_response2000_dataset(
            dataset,
            source_name="Response-2000 clipboard",
        )

    def _clear_response2000_data(self) -> None:
        self._response2000_dataset = {}
        self._response2000_path = ""
        self._response2000_source_name = ""
        self.response2000_curvature_column.clear()
        self.response2000_moment_column.clear()
        self.response2000_compare_table.setRowCount(0)
        self.response2000_compare_table.hide()
        self.response2000_controls.hide()
        self.moment_curvature_plot.clear_overlay()
        self._update_moment_curvature_plot()

    def _response2000_series(self) -> tuple[list[float], list[float]]:
        x_column = self.response2000_curvature_column.currentData()
        y_column = self.response2000_moment_column.currentData()
        if x_column is None or y_column is None:
            return [], []
        return response2000_series(
            self._response2000_dataset,
            int(x_column),
            int(y_column),
            curvature_unit=str(
                self.response2000_curvature_unit.currentData() or "same"
            ),
            moment_unit=str(
                self.response2000_moment_unit.currentData() or "same"
            ),
            units=self._project_units,
            curvature_factor=float(
                self.response2000_curvature_factor.value()
            ),
            moment_factor=float(
                self.response2000_moment_factor.value()
            ),
        )

    def _populate_response2000_comparison(
        self,
        simulation_x: list[float],
        simulation_y: list[float],
        response_x: list[float],
        response_y: list[float],
    ) -> dict[str, Any]:
        comparison = response2000_curve_comparison(
            simulation_x,
            simulation_y,
            response_x,
            response_y,
        )
        rows = comparison.get("metrics", [])
        if not isinstance(rows, list) or not rows:
            self.response2000_compare_table.setRowCount(0)
            self.response2000_compare_table.hide()
            return comparison

        def value_text(value: object) -> str:
            if value is None:
                return "-"
            try:
                number = float(value)
            except (TypeError, ValueError):
                return "-"
            if not math.isfinite(number):
                return "-"
            return f"{number:.6g}"

        self.response2000_compare_table.setRowCount(len(rows))
        for row_index, metric in enumerate(rows):
            values = (
                str(metric.get("label", "-")),
                value_text(metric.get("simulation")),
                value_text(metric.get("response2000")),
                value_text(metric.get("difference_percent")),
            )
            for column, value in enumerate(values):
                self.response2000_compare_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(value),
                )
        self.response2000_compare_table.show()
        return comparison

    def _update_moment_curvature_plot(self) -> None:
        x, y, component, element_tag = moment_curvature_curve(self._result)
        if not x or not y:
            spec = self._result.get("moment_curvature", {})
            if isinstance(spec, dict) and spec.get("kind") == "moment-curvature":
                self.moment_curvature_info.setText(
                    "Moment-curvature workflow recognized, but no complete "
                    "zeroLengthSection force/deformation history is available."
                )
            else:
                self.moment_curvature_info.setText(
                    "Run a Static + DisplacementControl zeroLengthSection "
                    "moment-curvature workflow to populate this result."
                )
            self.moment_curvature_metrics.setText(
                "Points: -   Peak |M|: -   Peak |κ|: -   Final: -"
            )
            self.moment_curvature_plot.set_series([], [])
            self.moment_curvature_plot.clear_overlay()
            self.response2000_compare_table.setRowCount(0)
            self.response2000_compare_table.hide()
            return

        component_label = component or "M"
        peak_m = max(abs(value) for value in y)
        peak_k = max(abs(value) for value in x)
        self.moment_curvature_info.setText(
            f"zeroLengthSection element "
            f"{element_tag if element_tag is not None else '-'} "
            f"· X = curvature κ · Y = section moment {component_label}"
        )
        self.moment_curvature_metrics.setText(
            f"Points: {len(x)}   "
            f"Peak |M|: {peak_m:.6g}   "
            f"Peak |κ|: {peak_k:.6g}   "
            f"Final: ({x[-1]:.6g}, {y[-1]:.6g})"
        )
        self.moment_curvature_plot.set_series(x, y)

        response_x, response_y = self._response2000_series()
        if response_x and response_y:
            self.moment_curvature_plot.set_overlay(
                response_x,
                response_y,
                label="Response-2000",
            )
            comparison = self._populate_response2000_comparison(
                x,
                y,
                response_x,
                response_y,
            )
            filename = (
                self._response2000_source_name
                or "Response-2000 data"
            )
            nrmse = comparison.get("moment_nrmse_percent")
            nrmse_text = (
                f"{float(nrmse):.3g}%"
                if nrmse is not None
                else "-"
            )
            unit_system = UnitSystem.from_mapping(self._project_units)
            self.response2000_info.setText(
                f"{filename} · {len(response_x)} valid point(s) · "
                f"converted to SARE units "
                f"[κ: 1/{unit_system.length}, "
                f"M: {unit_system.moment_label}] · "
                f"moment NRMSE over common κ range = {nrmse_text}. "
                "Dashed curve = Response-2000; solid curve = SARE/OpenSees."
            )
            self.response2000_controls.show()
        else:
            self.moment_curvature_plot.clear_overlay()
            self.response2000_compare_table.setRowCount(0)
            self.response2000_compare_table.hide()
            if self._response2000_dataset:
                self.response2000_info.setText(
                    "Choose numeric curvature and moment columns. Check source "
                    "units/signs; the × factors can reverse sign or apply an "
                    "additional scale."
                )
                self.response2000_controls.show()

    def _send_moment_curvature_to_hinge(self) -> None:
        x, y, component, element_tag = moment_curvature_curve(self._result)
        if not x or not y:
            self.moment_curvature_info.setText(
                "No moment-curvature data is available to send."
            )
            return

        spec = self._result.get("moment_curvature", {})
        section_tag = (
            spec.get("section_tag")
            if isinstance(spec, dict)
            else None
        )
        self.moment_curvature_hinge_requested.emit({
            "source_kind": "sare_moment_curvature",
            "source_note": (
                "SARE Moment-Curvature"
                + (
                    f" · Section {section_tag}"
                    if section_tag is not None
                    else ""
                )
                + (
                    f" · {component}"
                    if component
                    else ""
                )
            ),
            "basis": "moment_curvature",
            "section_tag": section_tag,
            "component": component,
            "element_tag": element_tag,
            "curvature": list(x),
            "moment": list(y),
        })

    def _export_moment_curvature_csv(self) -> None:
        x, y, component, element_tag = moment_curvature_curve(self._result)
        if not x or not y:
            self.moment_curvature_info.setText(
                "No moment-curvature data is available to export."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Moment–Curvature",
            "moment_curvature.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow([
                "Curvature",
                f"Moment {component or 'M'}",
                "zeroLengthSection element",
            ])
            for curvature, moment in zip(x, y):
                writer.writerow([
                    curvature,
                    moment,
                    element_tag if element_tag is not None else "",
                ])

        self.moment_curvature_info.setText(
            f"Exported {len(x)} moment-curvature point(s) to {path}."
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
        interface_rotation, interface_moment, _interface_component = (
            column_interface_moment_rotation_curve(self._result)
        )
        if interface_rotation and interface_moment:
            self.specimen_quantity.addItem(
                "Moment–rotation · base interface",
                "interface_moment_rotation",
            )
        for label, key in (
            ("Drift angle · total", "rotation:total"),
            ("Drift angle · member contribution", "rotation:column"),
            ("Interface rotation", "rotation:interface_rotation"),
            ("Interface lateral-slip drift", "rotation:interface_slip"),
        ):
            self.specimen_quantity.addItem(label, key)

        fibers = column_fiber_history_catalog(self._result)
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

        metrics = column_specimen_research_metrics(self._result)
        metric_rows = [
            (
                "Peak +M",
                metrics.get("peak_positive_moment"),
                f"Maximum positive {metrics.get('moment_component', 'M')}",
            ),
            (
                "Peak -M",
                metrics.get("peak_negative_moment"),
                f"Minimum negative {metrics.get('moment_component', 'M')}",
            ),
            (
                "Peak |κ|",
                metrics.get("peak_abs_curvature"),
                "Maximum absolute base-section curvature",
            ),
            (
                "Peak |drift angle|",
                metrics.get("peak_abs_total_drift"),
                "Global top drift angle relative to ground/base",
            ),
            (
                "Peak |member contribution|",
                metrics.get("peak_abs_column_drift"),
                "Drift-equivalent member contribution",
            ),
            (
                "Peak |interface rotation|",
                metrics.get("peak_abs_interface_rotation"),
                "Base-interface rotational contribution",
            ),
            (
                "Interface share @ peak drift [%]",
                metrics.get("interface_share_at_peak_drift_percent"),
                "Kinematic magnitude share; may exceed 100% if contributions oppose",
            ),
            (
                "Peak |steel strain|",
                metrics.get("peak_abs_steel_strain"),
                "Critical base-section reinforcing-steel strain",
            ),
            (
                "Peak |concrete strain|",
                metrics.get("peak_abs_concrete_strain"),
                "Critical base-section concrete strain",
            ),
            (
                "Peak |Bond_SP01 slip|",
                metrics.get("peak_abs_bond_slip"),
                "Critical strain-penetration material slip",
            ),
            (
                "Interface path energy",
                metrics.get("interface_path_energy"),
                "Absolute M–θ path work; descriptive, not a code check",
            ),
        ]
        visible_metric_rows = [
            row for row in metric_rows if row[1] is not None
        ]
        self.specimen_research_table.setRowCount(
            len(visible_metric_rows)
        )
        for row_index, (label, value, interpretation) in enumerate(
            visible_metric_rows
        ):
            self.specimen_research_table.setItem(
                row_index,
                0,
                QTableWidgetItem(str(label)),
            )
            self.specimen_research_table.setItem(
                row_index,
                1,
                QTableWidgetItem(f"{float(value):.6g}"),
            )
            self.specimen_research_table.setItem(
                row_index,
                2,
                QTableWidgetItem(str(interpretation)),
            )

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
            self.specimen_plot.clear_overlay()
            self.specimen_research_table.setRowCount(0)
            self.specimen_fiber_table.setRowCount(0)
            return

        summary = column_response_summary(self._result)
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
            x, y, component = column_moment_curvature_curve(
                self._result
            )
            self.specimen_info.setText(
                f"Element {element_tag} · base IP · {component or 'M'}–κ · "
                f"base interface: {interface_name}. "
                "The section history and interface history are captured "
                "independently to avoid hiding strain-penetration deformation."
            )
            self.specimen_plot.set_series(x, y)
            self._update_specimen_experiment_overlay()
            return

        if selected == "interface_moment_rotation":
            x, y, component = column_interface_moment_rotation_curve(
                self._result
            )
            self.specimen_info.setText(
                f"Base interface · {component or 'M'}–rotation · "
                f"{interface_name}. "
                "For Bond_SP01 zeroLengthSection this isolates the "
                "strain-penetration interface loop from the member M–κ loop."
            )
            self.specimen_plot.set_series(x, y)
            self._update_specimen_experiment_overlay()
            return

        if selected.startswith("rotation:"):
            key = selected.split(":", 1)[1]
            decomposition = column_rotation_decomposition(
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
            self._update_specimen_experiment_overlay()
            return

        item = next(
            (
                row
                for row in column_fiber_history_catalog(self._result)
                if str(row.get("key", "")) == selected
            ),
            None,
        )
        if item is None:
            self.specimen_plot.set_series([], [])
            self.specimen_plot.clear_overlay()
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
        self._update_specimen_experiment_overlay()

    def _update_specimen_experiment_overlay(self) -> None:
        if not self._cyclic_experiment_dataset:
            self.specimen_plot.clear_overlay()
            self.specimen_experiment_info.setText(
                "Experimental overlay is optional. For M–κ select "
                "curvature as X and moment as Y."
            )
            return

        x_column = self.specimen_exp_x_column.currentData()
        y_column = self.specimen_exp_y_column.currentData()
        if x_column is None or y_column is None:
            self.specimen_plot.clear_overlay()
            return
        try:
            x_index = int(x_column)
            y_index = int(y_column)
        except (TypeError, ValueError):
            self.specimen_plot.clear_overlay()
            return
        if x_index < 0 or y_index < 0:
            self.specimen_plot.clear_overlay()
            self.specimen_experiment_info.setText(
                "Experimental file loaded. Select Exp X and Exp Y to "
                "overlay a specimen response such as M–κ."
            )
            return

        x, y = experimental_csv_series(
            self._cyclic_experiment_dataset,
            x_index,
            y_index,
            x_scale=float(self.specimen_exp_x_scale.value()),
            y_scale=float(self.specimen_exp_y_scale.value()),
        )
        if not x or not y:
            self.specimen_plot.clear_overlay()
            self.specimen_experiment_info.setText(
                "Selected experimental X/Y columns contain no paired "
                "numeric data."
            )
            return

        self.specimen_plot.set_overlay(x, y, label="Experiment")
        filename = (
            self._cyclic_experiment_path.replace("\\", "/").split("/")[-1]
            if self._cyclic_experiment_path
            else "experimental data"
        )
        self.specimen_experiment_info.setText(
            f"{filename} · {len(x)} point(s) · "
            f"X={self.specimen_exp_x_column.currentText()} · "
            f"Y={self.specimen_exp_y_column.currentText()}."
        )

    def _populate_force_displacement_nodes(self) -> None:
        tags = time_history_node_tags(self._result)
        history = self._result.get("history", {})
        analysis = self._result.get("analysis", {})
        if not isinstance(history, dict):
            history = {}
        if not isinstance(analysis, dict):
            analysis = {}

        raw_monitor = history.get(
            "monitor_node",
            analysis.get("control_node"),
        )
        try:
            monitor_node = (
                int(raw_monitor)
                if raw_monitor is not None
                else None
            )
        except (TypeError, ValueError):
            monitor_node = None

        for combo in (self.force_disp_node, self.force_disp_force_node):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for tag in tags:
                combo.addItem(str(tag), int(tag))
            preferred = previous if previous is not None else monitor_node
            if preferred is not None:
                index = combo.findData(int(preferred))
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)

        raw_dof = history.get(
            "control_dof",
            analysis.get("control_dof", 1),
        )
        try:
            dof = int(raw_dof)
        except (TypeError, ValueError):
            dof = 1
        if dof not in range(1, 7):
            dof = 1
        self.force_disp_dof.blockSignals(True)
        self.force_disp_force_dof.blockSignals(True)
        self.force_disp_dof.setCurrentIndex(dof - 1)
        self.force_disp_force_dof.setCurrentIndex(dof - 1)
        self.force_disp_dof.blockSignals(False)
        self.force_disp_force_dof.blockSignals(False)

    def _update_force_displacement_controls(self, *_args) -> None:
        reaction = (
            self.force_disp_force_source.currentText()
            == "Node reaction"
        )
        self.force_disp_force_node.setEnabled(reaction)
        self._update_force_displacement_plot()

    def _force_displacement_selection(
        self,
    ) -> tuple[
        list[float],
        list[float],
        int | None,
        int,
        str,
        int | None,
        int,
    ]:
        displacement_data = self.force_disp_node.currentData()
        force_node_data = self.force_disp_force_node.currentData()
        return force_displacement_curve(
            self._result,
            displacement_node=(
                int(displacement_data)
                if displacement_data is not None
                else None
            ),
            displacement_dof=self.force_disp_dof.currentIndex() + 1,
            force_source=self.force_disp_force_source.currentText(),
            force_node=(
                int(force_node_data)
                if force_node_data is not None
                else None
            ),
            force_dof=self.force_disp_force_dof.currentIndex() + 1,
        )

    def _update_force_displacement_plot(self, *_args) -> None:
        (
            x,
            y,
            displacement_node,
            displacement_dof,
            force_source,
            force_node,
            force_dof,
        ) = self._force_displacement_selection()

        if not x or not y:
            self.force_disp_info.setText(
                "No complete force-displacement history is available for "
                "the selected node / force source."
            )
            self.force_disp_metrics.setText(
                "Points: -   Peak |F|: -   Peak |u|: -"
            )
            self.force_disp_plot.set_series([], [])
            return

        disp_labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        force_labels = ("FX", "FY", "FZ", "MX", "MY", "MZ")
        disp_label = disp_labels[displacement_dof - 1]
        force_label = force_labels[force_dof - 1]
        force_text = (
            f"applied base shear {force_label} (-Σ support reactions)"
            if force_source == "Base shear"
            else f"node {force_node} reaction {force_label}"
        )
        self.force_disp_info.setText(
            f"X = node {displacement_node} {disp_label} displacement · "
            f"Y = {force_text}"
        )
        self.force_disp_metrics.setText(
            f"Points: {len(x)}   "
            f"Peak |F|: {max(abs(value) for value in y):.6g}   "
            f"Peak |u|: {max(abs(value) for value in x):.6g}   "
            f"Final: ({x[-1]:.6g}, {y[-1]:.6g})"
        )
        self.force_disp_plot.set_series(x, y)

    def _export_force_displacement_csv(self) -> None:
        (
            x,
            y,
            displacement_node,
            displacement_dof,
            force_source,
            force_node,
            force_dof,
        ) = self._force_displacement_selection()
        if not x or not y:
            self.force_disp_info.setText(
                "No force-displacement data is available to export."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Force–Displacement",
            "force_displacement.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        disp_labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        force_labels = ("FX", "FY", "FZ", "MX", "MY", "MZ")
        force_header = (
            f"Applied base shear {force_labels[force_dof - 1]}"
            if force_source == "Base shear"
            else (
                f"Node {force_node} reaction "
                f"{force_labels[force_dof - 1]}"
            )
        )
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    f"Node {displacement_node} "
                    f"{disp_labels[displacement_dof - 1]} displacement",
                    force_header,
                ]
            )
            writer.writerows(zip(x, y))
        self.force_disp_info.setText(
            f"Exported {len(x)} force-displacement point(s) to {path}"
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

    def _set_cyclic_experiment_dataset(
        self,
        dataset: dict[str, Any],
        *,
        path: str = "",
    ) -> None:
        self._cyclic_experiment_dataset = (
            dict(dataset) if isinstance(dataset, dict) else {}
        )
        self._cyclic_experiment_path = str(path or "")
        headers = self._cyclic_experiment_dataset.get("headers", [])
        if not isinstance(headers, list):
            headers = []

        self.cyclic_exp_x_column.blockSignals(True)
        self.cyclic_exp_y_column.blockSignals(True)
        self.cyclic_exp_x_column.clear()
        self.cyclic_exp_y_column.clear()
        for index, header in enumerate(headers):
            label = str(header)
            self.cyclic_exp_x_column.addItem(label, index)
            self.cyclic_exp_y_column.addItem(label, index)

        def best_column(keywords: tuple[str, ...], fallback: int) -> int:
            for index, header in enumerate(headers):
                normalized = str(header).strip().lower()
                if any(keyword in normalized for keyword in keywords):
                    return index
            return min(max(fallback, 0), max(len(headers) - 1, 0))

        if headers:
            x_index = best_column(
                ("displacement", "disp", "drift", "stroke", "position", "u"),
                0,
            )
            y_index = best_column(
                ("force", "load", "shear", "base shear"),
                1 if len(headers) > 1 else 0,
            )
            self.cyclic_exp_x_column.setCurrentIndex(x_index)
            self.cyclic_exp_y_column.setCurrentIndex(y_index)

        self.cyclic_exp_x_column.blockSignals(False)
        self.cyclic_exp_y_column.blockSignals(False)

        if hasattr(self, "specimen_exp_x_column"):
            self.specimen_exp_x_column.blockSignals(True)
            self.specimen_exp_y_column.blockSignals(True)
            self.specimen_exp_x_column.clear()
            self.specimen_exp_y_column.clear()
            self.specimen_exp_x_column.addItem("(none)", -1)
            self.specimen_exp_y_column.addItem("(none)", -1)
            for index, header in enumerate(headers):
                label = str(header)
                self.specimen_exp_x_column.addItem(label, index)
                self.specimen_exp_y_column.addItem(label, index)

            curvature_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if any(
                        token in str(header).strip().lower()
                        for token in ("curvature", "kappa", "κ")
                    )
                ),
                None,
            )
            moment_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if "moment" in str(header).strip().lower()
                ),
                None,
            )
            if curvature_index is not None:
                self.specimen_exp_x_column.setCurrentIndex(
                    curvature_index + 1
                )
            if moment_index is not None:
                self.specimen_exp_y_column.setCurrentIndex(
                    moment_index + 1
                )
            self.specimen_exp_x_column.blockSignals(False)
            self.specimen_exp_y_column.blockSignals(False)

        self._update_cyclic_plot()
        if hasattr(self, "specimen_plot"):
            self._update_specimen_view()

    def _import_cyclic_experiment_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Experimental Cyclic Data",
            "",
            "CSV/TSV files (*.csv *.txt *.tsv);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as stream:
                dataset = parse_experimental_csv_text(stream.read())
        except (OSError, UnicodeError) as exc:
            message = f"Could not read experimental file: {exc}"
            self.cyclic_experiment_info.setText(message)
            if hasattr(self, "specimen_experiment_info"):
                self.specimen_experiment_info.setText(message)
            return

        headers = dataset.get("headers", [])
        rows = dataset.get("rows", [])
        if not headers or not rows:
            message = (
                "The selected file has no usable numeric experimental data."
            )
            self.cyclic_experiment_info.setText(message)
            if hasattr(self, "specimen_experiment_info"):
                self.specimen_experiment_info.setText(message)
            return

        self._set_cyclic_experiment_dataset(dataset, path=path)

    def _clear_cyclic_experiment(self) -> None:
        self._cyclic_experiment_dataset = {}
        self._cyclic_experiment_path = ""
        self.cyclic_exp_x_column.clear()
        self.cyclic_exp_y_column.clear()
        if hasattr(self, "specimen_exp_x_column"):
            self.specimen_exp_x_column.clear()
            self.specimen_exp_y_column.clear()
            self.specimen_exp_x_column.addItem("(none)", -1)
            self.specimen_exp_y_column.addItem("(none)", -1)
            self.specimen_plot.clear_overlay()
            self.specimen_experiment_info.setText(
                "Experimental overlay is optional. For M–κ select "
                "curvature as X and moment as Y."
            )
        self.cyclic_compare_table.setRowCount(0)
        self.cyclic_compare_table.hide()
        self.cyclic_plot.clear_overlay()
        self.cyclic_experiment_info.setText(
            "Optional: import experimental displacement-force CSV for "
            "overlay and descriptive validation metrics."
        )
        self._update_cyclic_plot()

    def _cyclic_experiment_series(self) -> tuple[list[float], list[float]]:
        x_column = self.cyclic_exp_x_column.currentData()
        y_column = self.cyclic_exp_y_column.currentData()
        if x_column is None or y_column is None:
            return [], []
        return experimental_csv_series(
            self._cyclic_experiment_dataset,
            int(x_column),
            int(y_column),
            x_scale=float(self.cyclic_exp_x_scale.value()),
            y_scale=float(self.cyclic_exp_y_scale.value()),
        )

    def _populate_cyclic_comparison(
        self,
        simulation_x: list[float],
        simulation_y: list[float],
        experiment_x: list[float],
        experiment_y: list[float],
    ) -> dict[str, Any]:
        comparison = cyclic_curve_comparison(
            simulation_x,
            simulation_y,
            experiment_x,
            experiment_y,
        )
        metric_rows = comparison.get("metrics", [])
        if not isinstance(metric_rows, list) or not metric_rows:
            self.cyclic_compare_table.setRowCount(0)
            self.cyclic_compare_table.hide()
            return comparison

        def format_value(value: Any) -> str:
            if value is None:
                return "-"
            try:
                number = float(value)
            except (TypeError, ValueError):
                return "-"
            if not math.isfinite(number):
                return "-"
            return f"{number:.6g}"

        self.cyclic_compare_table.setRowCount(len(metric_rows))
        for row, item in enumerate(metric_rows):
            values = [
                str(item.get("label", "-")),
                format_value(item.get("simulation")),
                format_value(item.get("experiment")),
                format_value(item.get("difference_percent")),
            ]
            for column, value in enumerate(values):
                self.cyclic_compare_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self.cyclic_compare_table.show()
        return comparison

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
            self.cyclic_plot.clear_overlay()
            self.cyclic_compare_table.setRowCount(0)
            self.cyclic_compare_table.hide()
            self.cyclic_reversal_table.setRowCount(0)
            self.cyclic_cycle_table.setRowCount(0)
            self.cyclic_research_info.setText(
                "No cyclic reversal research data is available."
            )
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
        experiment_x, experiment_y = self._cyclic_experiment_series()
        comparison: dict[str, Any] = {}
        view = str(self.cyclic_compare_view.currentData() or "hysteresis")
        if view == "backbone":
            plot_x, plot_y = cyclic_backbone_curve(x, y)
        else:
            plot_x, plot_y = x, y
        self.cyclic_plot.set_series(plot_x, plot_y)

        if experiment_x and experiment_y:
            if view == "backbone":
                overlay_x, overlay_y = cyclic_backbone_curve(
                    experiment_x,
                    experiment_y,
                )
            else:
                overlay_x, overlay_y = experiment_x, experiment_y
            self.cyclic_plot.set_overlay(
                overlay_x,
                overlay_y,
                label="Experiment",
            )
            comparison = self._populate_cyclic_comparison(
                x,
                y,
                experiment_x,
                experiment_y,
            )
            filename = (
                self._cyclic_experiment_path.replace("\\", "/").split("/")[-1]
                if self._cyclic_experiment_path
                else "experimental data"
            )
            matched = int(comparison.get("matched_reversal_count", 0))
            sim_reversals = int(comparison.get("simulation_reversal_count", 0))
            exp_reversals = int(comparison.get("experiment_reversal_count", 0))
            nrmse = comparison.get("reversal_force_nrmse_percent")
            nrmse_text = (
                f"{float(nrmse):.3g}%"
                if nrmse is not None
                else "-"
            )
            self.cyclic_experiment_info.setText(
                f"{filename} · {len(experiment_x)} valid point(s) · "
                f"matched reversals {matched}/{sim_reversals} OpenSees "
                f"and {exp_reversals} experimental · "
                f"reversal-force NRMSE={nrmse_text}. "
                "Δ values are descriptive differences relative to experiment."
            )
        else:
            self.cyclic_plot.clear_overlay()
            self.cyclic_compare_table.setRowCount(0)
            self.cyclic_compare_table.hide()
            if self._cyclic_experiment_dataset:
                self.cyclic_experiment_info.setText(
                    "Choose two numeric experimental columns with usable "
                    "X/Y data. Scale factors may be negative to reverse sign."
                )
            else:
                self.cyclic_experiment_info.setText(
                    "Optional: import experimental displacement-force CSV "
                    "for overlay and descriptive validation metrics."
                )

        specimen_rows = column_cyclic_reversal_metrics(
            self._result
        )
        if specimen_rows:
            reversal_rows = specimen_rows
            self.cyclic_research_info.setText(
                f"{len(specimen_rows)} synchronized reversal(s): "
                "global V–u + drift + base M–κ + critical steel/concrete "
                "strain + Bond_SP01 slip + interface rotation + energy."
            )
        else:
            raw_reversals = metrics.get("reversals", [])
            if not isinstance(raw_reversals, list):
                raw_reversals = []
            reversal_rows = [
                {
                    "reversal": index + 1,
                    "displacement": reversal.get("displacement"),
                    "base_shear": reversal.get("force"),
                    "secant_stiffness": reversal.get(
                        "secant_stiffness"
                    ),
                    "strength_ratio": reversal.get("strength_ratio"),
                    "stiffness_ratio": reversal.get(
                        "stiffness_ratio"
                    ),
                }
                for index, reversal in enumerate(raw_reversals)
                if isinstance(reversal, dict)
            ]
            self.cyclic_research_info.setText(
                "Global reversal metrics are available. Build/run a Quick "
                "1D Column specimen to add M–κ, fiber, Bond_SP01 and "
                "interface-response columns."
            )

        def metric_text(value: Any, decimals: int = 6) -> str:
            if value is None:
                return "-"
            try:
                number = float(value)
            except (TypeError, ValueError):
                return "-"
            if not math.isfinite(number):
                return "-"
            return f"{number:.{decimals}g}"

        self.cyclic_reversal_table.setRowCount(len(reversal_rows))
        for row, reversal in enumerate(reversal_rows):
            cycle = reversal.get("closed_cycle_number")
            values = [
                str(reversal.get("reversal", row + 1)),
                metric_text(reversal.get("displacement")),
                metric_text(reversal.get("base_shear")),
                metric_text(reversal.get("drift_angle")),
                metric_text(reversal.get("moment")),
                metric_text(reversal.get("curvature")),
                metric_text(reversal.get("steel_strain")),
                metric_text(reversal.get("concrete_strain")),
                metric_text(reversal.get("bond_slip")),
                metric_text(reversal.get("interface_rotation")),
                metric_text(reversal.get("secant_stiffness")),
                metric_text(reversal.get("strength_ratio"), 4),
                metric_text(reversal.get("stiffness_ratio"), 4),
                metric_text(reversal.get("branch_energy")),
                str(int(cycle)) if cycle is not None else "-",
                metric_text(reversal.get("closed_cycle_energy")),
            ]
            reversal_number = int(reversal.get("reversal", row + 1))
            match = next(
                (
                    item
                    for item in comparison.get("reversal_matches", [])
                    if int(item.get("simulation_reversal", -1))
                    == reversal_number
                ),
                None,
            )
            if isinstance(match, dict):
                values.extend([
                    metric_text(match.get("experiment_force")),
                    metric_text(match.get("force_error_percent"), 4),
                    metric_text(
                        match.get("experiment_secant_stiffness")
                    ),
                    metric_text(match.get("stiffness_error_percent"), 4),
                ])
            else:
                values.extend(["-", "-", "-", "-"])
            for column, value in enumerate(values):
                self.cyclic_reversal_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

        cycle_rows = column_cyclic_cycle_metrics(self._result)
        self.cyclic_cycle_table.setRowCount(len(cycle_rows))
        for row, cycle in enumerate(cycle_rows):
            values = [
                str(cycle.get("cycle", row + 1)),
                str(cycle.get("end_reversal", "-")),
                metric_text(cycle.get("amplitude")),
                str(cycle.get("repeat_index", "-")),
                metric_text(cycle.get("energy")),
                metric_text(cycle.get("interface_energy")),
                metric_text(cycle.get("strength_ratio"), 4),
                metric_text(cycle.get("stiffness_ratio"), 4),
            ]
            for column, value in enumerate(values):
                self.cyclic_cycle_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _export_cyclic_research_csv(self) -> None:
        reversal_rows = column_cyclic_reversal_metrics(self._result)
        if not reversal_rows:
            self.cyclic_research_info.setText(
                "No synchronized 1D-column cyclic research metrics are "
                "available to export."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Cyclic Research Metrics",
            "column_cyclic_research_metrics.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        fields = [
            "reversal",
            "history_step",
            "time",
            "repeat_index",
            "displacement",
            "base_shear",
            "drift_angle",
            "member_drift",
            "interface_rotation",
            "interface_slip_drift",
            "interface_slip",
            "moment",
            "curvature",
            "steel_strain",
            "concrete_strain",
            "bond_slip",
            "secant_stiffness",
            "strength_ratio",
            "stiffness_ratio",
            "branch_energy",
            "interface_branch_energy",
            "closed_cycle_number",
            "closed_cycle_energy",
            "interface_closed_cycle_energy",
        ]
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in reversal_rows:
                writer.writerow({
                    field: row.get(field)
                    for field in fields
                })

        self.cyclic_research_info.setText(
            f"Exported {len(reversal_rows)} synchronized reversal row(s) "
            f"to {path}"
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
