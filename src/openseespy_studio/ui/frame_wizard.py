from __future__ import annotations

from dataclasses import replace
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..frame_setup import prepare_frame_grid
from ..generator import (
    FrameGridSpec,
    frame_brace_element_count,
    frame_brace_panel_count,
    frame_brace_panels,
    frame_brace_storeys,
    frame_brace_x_bays,
    frame_brace_x_grid_lines,
    frame_brace_y_bays,
    frame_brace_y_grid_lines,
    frame_diaphragm_count,
    frame_diaphragm_levels,
    frame_floor_levels,
    frame_foundation_count,
    frame_foundation_profile_assignments,
    frame_foundation_profiles,
    frame_grid_coordinates,
    frame_slab_count,
    frame_joint_connection_count,
    frame_load_storeys,
    generate_frame_project,
    validate_frame_grid_spec,
)
from ..project import (
    MEMBRANE_SECTION_TYPES,
    SHELL_SECTION_TYPES,
    ProjectDatabase,
)
from ..units import UnitSystem


class SpacingEditor(QTableWidget):
    """Compact editor for per-bay/per-storey spacing values."""

    def __init__(
        self,
        *,
        prefix: str,
        unit_label: str,
        count: int,
        default_value: float,
        parent=None,
    ):
        super().__init__(0, 1, parent)
        self.prefix = str(prefix)
        self.unit_label = str(unit_label)
        self.default_value = float(default_value)
        self.setHorizontalHeaderLabels([f"Size [{self.unit_label}]"])
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setMinimumHeight(150)
        self.setMaximumHeight(225)
        self.set_count(count)

    def _spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(4)
        spin.setRange(1.0e-6, 1.0e9)
        spin.setValue(float(value))
        return spin

    def set_count(self, count: int) -> None:
        count = max(1, int(count))
        existing = self.values()
        self.setRowCount(count)
        for row in range(count):
            value = (
                existing[row]
                if row < len(existing)
                else self.default_value
            )
            spin = self._spin(value)
            self.setCellWidget(row, 0, spin)
            self.setVerticalHeaderItem(
                row,
                QTableWidgetItem(f"{self.prefix}{row + 1}"),
            )

    def fill(self, value: float) -> None:
        self.default_value = float(value)
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, 0)
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))

    def set_default(self, value: float) -> None:
        self.default_value = float(value)

    def values(self) -> tuple[float, ...]:
        values: list[float] = []
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, 0)
            if isinstance(widget, QDoubleSpinBox):
                values.append(float(widget.value()))
        return tuple(values)

    def connect_value_changed(self, callback) -> None:
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, 0)
            if isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(callback)


class FramePreview(QWidget):
    """Dimensioned live preview for Frame Wizard geometry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dimension = "2D"
        self.x_coordinates = [0.0, 5.0, 10.0, 15.0]
        self.y_coordinates = [0.0]
        self.z_coordinates = [0.0, 3.5, 7.0, 10.5]
        self.create_columns = True
        self.create_beams_x = True
        self.create_beams_y = False
        self.joint_model = "None"
        self.joint_scope = "all"
        self.joint_panel_width = 0.40
        self.joint_panel_height = 0.50
        self.diaphragm_mode = "None"
        self.diaphragm_levels: tuple[int, ...] = ()
        self.slab_divisions_x = 1
        self.slab_divisions_y = 1
        self.foundation_mode = "Direct"
        self.foundation_base_profiles: tuple[int, ...] = ()
        self.brace_mode = "None"
        self.brace_pattern = "X"
        self.brace_x_bays: tuple[int, ...] = ()
        self.brace_y_bays: tuple[int, ...] = ()
        self.brace_storeys: tuple[int, ...] = ()
        self.brace_plane_mode = "X"
        self.brace_y_plane_scope = "All"
        self.brace_x_plane_scope = "All"
        self.brace_panel_patterns: tuple[
            tuple[str, int, int, int, str], ...
        ] = ()
        self.load_mode = "None"
        self.load_beam_udl = False
        self.load_beam_scope = "Both"
        self.load_storeys: tuple[int, ...] = ()
        self.load_floor_area = False
        self.load_floor_area_direction = "X"
        self.setMinimumHeight(285)

    def set_frame(
        self,
        *,
        dimension: str,
        x_coordinates: list[float],
        y_coordinates: list[float],
        z_coordinates: list[float],
        create_columns: bool,
        create_beams_x: bool,
        create_beams_y: bool,
        joint_model: str = "None",
        joint_scope: str = "all",
        joint_panel_width: float = 0.40,
        joint_panel_height: float = 0.50,
        diaphragm_mode: str = "None",
        diaphragm_levels: tuple[int, ...] = (),
        slab_divisions_x: int = 1,
        slab_divisions_y: int = 1,
        foundation_mode: str = "Direct",
        foundation_base_profiles: tuple[int, ...] = (),
        brace_mode: str = "None",
        brace_pattern: str = "X",
        brace_x_bays: tuple[int, ...] = (),
        brace_y_bays: tuple[int, ...] = (),
        brace_storeys: tuple[int, ...] = (),
        brace_plane_mode: str = "X",
        brace_y_plane_scope: str = "All",
        brace_x_plane_scope: str = "All",
        brace_panel_patterns: tuple[
            tuple[str, int, int, int, str], ...
        ] = (),
        load_mode: str = "None",
        load_beam_udl: bool = False,
        load_beam_scope: str = "Both",
        load_storeys: tuple[int, ...] = (),
        load_floor_area: bool = False,
        load_floor_area_direction: str = "X",
    ) -> None:
        self.dimension = str(dimension)
        self.x_coordinates = list(x_coordinates)
        self.y_coordinates = list(y_coordinates)
        self.z_coordinates = list(z_coordinates)
        self.create_columns = bool(create_columns)
        self.create_beams_x = bool(create_beams_x)
        self.create_beams_y = bool(create_beams_y)
        self.joint_model = str(joint_model)
        self.joint_scope = str(joint_scope)
        self.joint_panel_width = float(joint_panel_width)
        self.joint_panel_height = float(joint_panel_height)
        self.diaphragm_mode = str(diaphragm_mode)
        self.diaphragm_levels = tuple(
            int(level) for level in diaphragm_levels
        )
        self.slab_divisions_x = max(1, int(slab_divisions_x))
        self.slab_divisions_y = max(1, int(slab_divisions_y))
        self.foundation_mode = str(foundation_mode)
        self.foundation_base_profiles = tuple(
            int(value) for value in foundation_base_profiles
        )
        self.brace_mode = str(brace_mode)
        self.brace_pattern = str(brace_pattern)
        self.brace_x_bays = tuple(int(value) for value in brace_x_bays)
        self.brace_y_bays = tuple(int(value) for value in brace_y_bays)
        self.brace_storeys = tuple(int(value) for value in brace_storeys)
        self.brace_plane_mode = str(brace_plane_mode)
        self.brace_y_plane_scope = str(brace_y_plane_scope)
        self.brace_x_plane_scope = str(brace_x_plane_scope)
        self.brace_panel_patterns = tuple(
            (
                str(axis),
                int(plane),
                int(bay),
                int(storey),
                str(pattern),
            )
            for axis, plane, bay, storey, pattern in brace_panel_patterns
        )
        self.load_mode = str(load_mode)
        self.load_beam_udl = bool(load_beam_udl)
        self.load_beam_scope = str(load_beam_scope)
        self.load_storeys = tuple(int(value) for value in load_storeys)
        self.load_floor_area = bool(load_floor_area)
        self.load_floor_area_direction = str(load_floor_area_direction)
        self.update()

    @staticmethod
    def _project_3d(x: float, y: float, z: float) -> QPointF:
        return QPointF(x + 0.55 * y, z + 0.32 * y)

    @staticmethod
    def _intervals(values: list[float]) -> list[float]:
        return [
            float(values[index + 1] - values[index])
            for index in range(len(values) - 1)
        ]

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(62, 20, -38, -58)
        if rect.width() <= 20 or rect.height() <= 20:
            return

        x0 = self.x_coordinates[0]
        y0 = self.y_coordinates[0]
        z0 = self.z_coordinates[0]
        if self.dimension == "2D":
            raw_points = [
                QPointF(x, z)
                for z in self.z_coordinates
                for x in self.x_coordinates
            ]
        else:
            raw_points = [
                self._project_3d(x, y, z)
                for z in self.z_coordinates
                for y in self.y_coordinates
                for x in self.x_coordinates
            ]

        xs = [point.x() for point in raw_points]
        ys = [point.y() for point in raw_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1.0e-9)
        span_y = max(max_y - min_y, 1.0e-9)
        scale = min(rect.width() / span_x, rect.height() / span_y)

        def map_point(point: QPointF) -> QPointF:
            return QPointF(
                rect.left() + (point.x() - min_x) * scale,
                rect.bottom() - (point.y() - min_y) * scale,
            )

        member_pen = QPen(self.palette().text().color())
        member_pen.setWidthF(1.6)
        painter.setPen(member_pen)

        if self.dimension == "2D":
            def p(i: int, k: int) -> QPointF:
                return map_point(
                    QPointF(
                        self.x_coordinates[i],
                        self.z_coordinates[k],
                    )
                )

            if self.create_columns:
                for k in range(len(self.z_coordinates) - 1):
                    for i in range(len(self.x_coordinates)):
                        painter.drawLine(p(i, k), p(i, k + 1))
            if self.create_beams_x:
                for k in range(1, len(self.z_coordinates)):
                    for i in range(len(self.x_coordinates) - 1):
                        painter.drawLine(p(i, k), p(i + 1, k))
        else:
            def p(i: int, j: int, k: int) -> QPointF:
                return map_point(
                    self._project_3d(
                        self.x_coordinates[i],
                        self.y_coordinates[j],
                        self.z_coordinates[k],
                    )
                )

            if self.create_columns:
                for k in range(len(self.z_coordinates) - 1):
                    for j in range(len(self.y_coordinates)):
                        for i in range(len(self.x_coordinates)):
                            painter.drawLine(p(i, j, k), p(i, j, k + 1))
            if self.create_beams_x:
                for k in range(1, len(self.z_coordinates)):
                    for j in range(len(self.y_coordinates)):
                        for i in range(len(self.x_coordinates) - 1):
                            painter.drawLine(p(i, j, k), p(i + 1, j, k))
            if self.create_beams_y:
                for k in range(1, len(self.z_coordinates)):
                    for j in range(len(self.y_coordinates) - 1):
                        for i in range(len(self.x_coordinates)):
                            painter.drawLine(p(i, j, k), p(i, j + 1, k))

        node_pen = QPen(self.palette().highlight().color())
        node_pen.setWidthF(4.0)
        node_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(node_pen)
        for point in raw_points:
            painter.drawPoint(map_point(point))

        if self.joint_model != "None":
            joint_pen = QPen(self.palette().highlight().color())
            joint_pen.setWidthF(1.4)
            painter.setPen(joint_pen)
            if self.dimension == "2D":
                x_indices = list(range(len(self.x_coordinates)))
                if self.joint_scope == "interior":
                    x_indices = list(
                        range(1, len(self.x_coordinates) - 1)
                    )
                for k in range(1, len(self.z_coordinates)):
                    for i in x_indices:
                        point = p(i, k)
                        if self.joint_model == "ZeroLength":
                            painter.drawEllipse(
                                QRectF(
                                    point.x() - 5.0,
                                    point.y() - 5.0,
                                    10.0,
                                    10.0,
                                )
                            )
                            painter.drawLine(
                                QPointF(point.x() - 8.0, point.y()),
                                QPointF(point.x() + 8.0, point.y()),
                            )
                        else:
                            panel_w = max(
                                8.0,
                                self.joint_panel_width * scale,
                            )
                            panel_h = max(
                                8.0,
                                self.joint_panel_height * scale,
                            )
                            painter.setBrush(self.palette().base())
                            painter.drawRect(
                                QRectF(
                                    point.x() - 0.5 * panel_w,
                                    point.y() - 0.5 * panel_h,
                                    panel_w,
                                    panel_h,
                                )
                            )
                            painter.setBrush(Qt.NoBrush)
                            painter.drawLine(
                                QPointF(
                                    point.x() - 0.5 * panel_w,
                                    point.y(),
                                ),
                                QPointF(
                                    point.x() + 0.5 * panel_w,
                                    point.y(),
                                ),
                            )
                            painter.drawLine(
                                QPointF(
                                    point.x(),
                                    point.y() - 0.5 * panel_h,
                                ),
                                QPointF(
                                    point.x(),
                                    point.y() + 0.5 * panel_h,
                                ),
                            )
            elif self.joint_model == "ZeroLength":
                x_indices = list(range(len(self.x_coordinates)))
                y_indices = list(range(len(self.y_coordinates)))
                if self.joint_scope == "interior":
                    x_indices = list(
                        range(1, len(self.x_coordinates) - 1)
                    )
                    y_indices = list(
                        range(1, len(self.y_coordinates) - 1)
                    )
                for k in range(1, len(self.z_coordinates)):
                    for j in y_indices:
                        for i in x_indices:
                            point = p(i, j, k)
                            painter.drawEllipse(
                                QRectF(
                                    point.x() - 5.0,
                                    point.y() - 5.0,
                                    10.0,
                                    10.0,
                                )
                            )

        if (
            self.dimension == "3D"
            and self.diaphragm_mode in {"Rigid", "Shell"}
        ):
            floor_pen = QPen(self.palette().highlight().color())
            floor_pen.setWidthF(
                1.8 if self.diaphragm_mode == "Rigid" else 1.1
            )
            painter.setPen(floor_pen)
            levels = (
                self.diaphragm_levels
                if self.diaphragm_levels
                else tuple(range(1, len(self.z_coordinates)))
            )

            def refined(values: list[float], divisions: int) -> list[float]:
                result = [float(values[0])]
                for left, right in zip(values[:-1], values[1:]):
                    for index in range(1, divisions + 1):
                        ratio = index / divisions
                        result.append(
                            float(left)
                            + ratio * (float(right) - float(left))
                        )
                return result

            x_mesh = refined(
                self.x_coordinates,
                self.slab_divisions_x,
            )
            y_mesh = refined(
                self.y_coordinates,
                self.slab_divisions_y,
            )
            # Preview remains light even for a deliberately fine FE mesh.
            x_step = max(1, int(math.ceil(len(x_mesh) / 80)))
            y_step = max(1, int(math.ceil(len(y_mesh) / 80)))

            for level in levels:
                if level <= 0 or level >= len(self.z_coordinates):
                    continue
                z_value = self.z_coordinates[level]
                corners = [
                    p(0, 0, level),
                    p(len(self.x_coordinates) - 1, 0, level),
                    p(
                        len(self.x_coordinates) - 1,
                        len(self.y_coordinates) - 1,
                        level,
                    ),
                    p(0, len(self.y_coordinates) - 1, level),
                ]
                for index in range(4):
                    painter.drawLine(
                        corners[index],
                        corners[(index + 1) % 4],
                    )

                if self.diaphragm_mode == "Rigid":
                    center = map_point(
                        self._project_3d(
                            0.5 * (
                                self.x_coordinates[0]
                                + self.x_coordinates[-1]
                            ),
                            0.5 * (
                                self.y_coordinates[0]
                                + self.y_coordinates[-1]
                            ),
                            z_value,
                        )
                    )
                    painter.drawEllipse(
                        QRectF(
                            center.x() - 4.0,
                            center.y() - 4.0,
                            8.0,
                            8.0,
                        )
                    )
                else:
                    for x_value in x_mesh[::x_step]:
                        painter.drawLine(
                            map_point(
                                self._project_3d(
                                    x_value,
                                    y_mesh[0],
                                    z_value,
                                )
                            ),
                            map_point(
                                self._project_3d(
                                    x_value,
                                    y_mesh[-1],
                                    z_value,
                                )
                            ),
                        )
                    if x_mesh[-1] not in x_mesh[::x_step]:
                        painter.drawLine(
                            map_point(
                                self._project_3d(
                                    x_mesh[-1],
                                    y_mesh[0],
                                    z_value,
                                )
                            ),
                            map_point(
                                self._project_3d(
                                    x_mesh[-1],
                                    y_mesh[-1],
                                    z_value,
                                )
                            ),
                        )
                    for y_value in y_mesh[::y_step]:
                        painter.drawLine(
                            map_point(
                                self._project_3d(
                                    x_mesh[0],
                                    y_value,
                                    z_value,
                                )
                            ),
                            map_point(
                                self._project_3d(
                                    x_mesh[-1],
                                    y_value,
                                    z_value,
                                )
                            ),
                        )
                    if y_mesh[-1] not in y_mesh[::y_step]:
                        painter.drawLine(
                            map_point(
                                self._project_3d(
                                    x_mesh[0],
                                    y_mesh[-1],
                                    z_value,
                                )
                            ),
                            map_point(
                                self._project_3d(
                                    x_mesh[-1],
                                    y_mesh[-1],
                                    z_value,
                                )
                            ),
                        )

        if self.brace_mode == "Truss":
            brace_pen = QPen(self.palette().highlight().color())
            brace_pen.setWidthF(2.0)
            painter.setPen(brace_pen)

            x_bays = (
                self.brace_x_bays
                if self.brace_x_bays
                else tuple(range(len(self.x_coordinates) - 1))
            )
            y_bays = (
                self.brace_y_bays
                if self.brace_y_bays
                else tuple(range(len(self.y_coordinates) - 1))
            )
            storeys = (
                self.brace_storeys
                if self.brace_storeys
                else tuple(range(1, len(self.z_coordinates)))
            )
            overrides = {
                (axis, plane, bay, storey): pattern
                for axis, plane, bay, storey, pattern
                in self.brace_panel_patterns
            }

            def scoped_lines(
                count: int,
                scope: str,
                minimum: str,
                maximum: str,
            ) -> tuple[int, ...]:
                if scope == minimum:
                    return (0,)
                if scope == maximum:
                    return (count,)
                if scope == "Exterior":
                    return (0,) if count == 0 else (0, count)
                return tuple(range(count + 1))

            if self.dimension == "2D":
                y_lines = (0,)
                x_lines = ()
            else:
                y_lines = scoped_lines(
                    len(self.y_coordinates) - 1,
                    self.brace_y_plane_scope,
                    "YMin",
                    "YMax",
                )
                x_lines = scoped_lines(
                    len(self.x_coordinates) - 1,
                    self.brace_x_plane_scope,
                    "XMin",
                    "XMax",
                )

            def project_xyz(x: float, y: float, z: float) -> QPointF:
                if self.dimension == "2D":
                    return map_point(QPointF(x, z))
                return map_point(self._project_3d(x, y, z))

            def draw_panel(
                axis: str,
                plane: int,
                bay: int,
                storey: int,
                pattern: str,
            ) -> None:
                if pattern == "None":
                    return
                lower = storey - 1
                upper = storey
                if axis == "X":
                    if (
                        plane < 0
                        or plane >= len(self.y_coordinates)
                        or bay < 0
                        or bay + 1 >= len(self.x_coordinates)
                    ):
                        return
                    bl = p(bay, plane, lower)
                    br = p(bay + 1, plane, lower)
                    tl = p(bay, plane, upper)
                    tr = p(bay + 1, plane, upper)
                    mid_upper = project_xyz(
                        0.5 * (
                            self.x_coordinates[bay]
                            + self.x_coordinates[bay + 1]
                        ),
                        self.y_coordinates[plane],
                        self.z_coordinates[upper],
                    )
                    mid_lower = project_xyz(
                        0.5 * (
                            self.x_coordinates[bay]
                            + self.x_coordinates[bay + 1]
                        ),
                        self.y_coordinates[plane],
                        self.z_coordinates[lower],
                    )
                    mid_left = project_xyz(
                        self.x_coordinates[bay],
                        self.y_coordinates[plane],
                        0.5 * (
                            self.z_coordinates[lower]
                            + self.z_coordinates[upper]
                        ),
                    )
                    mid_right = project_xyz(
                        self.x_coordinates[bay + 1],
                        self.y_coordinates[plane],
                        0.5 * (
                            self.z_coordinates[lower]
                            + self.z_coordinates[upper]
                        ),
                    )
                else:
                    if (
                        plane < 0
                        or plane >= len(self.x_coordinates)
                        or bay < 0
                        or bay + 1 >= len(self.y_coordinates)
                    ):
                        return
                    bl = p(plane, bay, lower)
                    br = p(plane, bay + 1, lower)
                    tl = p(plane, bay, upper)
                    tr = p(plane, bay + 1, upper)
                    mid_upper = project_xyz(
                        self.x_coordinates[plane],
                        0.5 * (
                            self.y_coordinates[bay]
                            + self.y_coordinates[bay + 1]
                        ),
                        self.z_coordinates[upper],
                    )
                    mid_lower = project_xyz(
                        self.x_coordinates[plane],
                        0.5 * (
                            self.y_coordinates[bay]
                            + self.y_coordinates[bay + 1]
                        ),
                        self.z_coordinates[lower],
                    )
                    mid_left = project_xyz(
                        self.x_coordinates[plane],
                        self.y_coordinates[bay],
                        0.5 * (
                            self.z_coordinates[lower]
                            + self.z_coordinates[upper]
                        ),
                    )
                    mid_right = project_xyz(
                        self.x_coordinates[plane],
                        self.y_coordinates[bay + 1],
                        0.5 * (
                            self.z_coordinates[lower]
                            + self.z_coordinates[upper]
                        ),
                    )

                if pattern == "DiagonalForward":
                    painter.drawLine(bl, tr)
                elif pattern == "DiagonalBackward":
                    painter.drawLine(br, tl)
                elif pattern == "X":
                    painter.drawLine(bl, tr)
                    painter.drawLine(br, tl)
                elif pattern == "VUpper":
                    painter.drawLine(bl, mid_upper)
                    painter.drawLine(br, mid_upper)
                elif pattern == "VLower":
                    painter.drawLine(tl, mid_lower)
                    painter.drawLine(tr, mid_lower)
                elif pattern == "KLeft":
                    painter.drawLine(mid_left, br)
                    painter.drawLine(mid_left, tr)
                elif pattern == "KRight":
                    painter.drawLine(mid_right, bl)
                    painter.drawLine(mid_right, tl)

            if self.brace_plane_mode in {"X", "Both"}:
                for storey in storeys:
                    if storey <= 0 or storey >= len(self.z_coordinates):
                        continue
                    for plane in y_lines:
                        for bay in x_bays:
                            draw_panel(
                                "X",
                                plane,
                                bay,
                                storey,
                                overrides.get(
                                    ("X", plane, bay, storey),
                                    self.brace_pattern,
                                ),
                            )

            if (
                self.dimension == "3D"
                and self.brace_plane_mode in {"Y", "Both"}
            ):
                for storey in storeys:
                    if storey <= 0 or storey >= len(self.z_coordinates):
                        continue
                    for plane in x_lines:
                        for bay in y_bays:
                            draw_panel(
                                "Y",
                                plane,
                                bay,
                                storey,
                                overrides.get(
                                    ("Y", plane, bay, storey),
                                    self.brace_pattern,
                                ),
                            )

        if self.load_mode == "Static":
            load_pen = QPen(self.palette().highlight().color())
            load_pen.setWidthF(1.4)
            painter.setPen(load_pen)

            # A compact gravity marker communicates automatic self-weight.
            painter.drawText(
                int(rect.left() + 4),
                int(rect.top() + 14),
                "LOAD ↓",
            )

            if self.load_beam_udl or self.load_floor_area:
                selected_storeys = (
                    self.load_storeys
                    if self.load_storeys
                    else tuple(range(1, len(self.z_coordinates)))
                )
                draw_x = (
                    self.load_beam_udl
                    and self.load_beam_scope in {"X", "Both"}
                ) or (
                    self.load_floor_area
                    and self.load_floor_area_direction == "X"
                )
                draw_y = (
                    self.load_beam_udl
                    and self.load_beam_scope in {"Y", "Both"}
                ) or (
                    self.load_floor_area
                    and self.load_floor_area_direction == "Y"
                )

                def arrow_at(point: QPointF) -> None:
                    length = 13.0
                    tip = QPointF(point.x(), point.y() + length)
                    painter.drawLine(point, tip)
                    painter.drawLine(
                        tip,
                        QPointF(tip.x() - 3.5, tip.y() - 4.0),
                    )
                    painter.drawLine(
                        tip,
                        QPointF(tip.x() + 3.5, tip.y() - 4.0),
                    )

                for storey in selected_storeys:
                    if (
                        storey <= 0
                        or storey >= len(self.z_coordinates)
                    ):
                        continue
                    z_value = self.z_coordinates[storey]

                    if draw_x:
                        if self.dimension == "2D":
                            for bay in range(len(self.x_coordinates) - 1):
                                x_mid = 0.5 * (
                                    self.x_coordinates[bay]
                                    + self.x_coordinates[bay + 1]
                                )
                                arrow_at(
                                    map_point(QPointF(x_mid, z_value))
                                )
                        else:
                            for j, y_value in enumerate(self.y_coordinates):
                                del j
                                for bay in range(
                                    len(self.x_coordinates) - 1
                                ):
                                    x_mid = 0.5 * (
                                        self.x_coordinates[bay]
                                        + self.x_coordinates[bay + 1]
                                    )
                                    arrow_at(
                                        map_point(
                                            self._project_3d(
                                                x_mid,
                                                y_value,
                                                z_value,
                                            )
                                        )
                                    )

                    if (
                        self.dimension == "3D"
                        and draw_y
                    ):
                        for i, x_value in enumerate(self.x_coordinates):
                            del i
                            for bay in range(
                                len(self.y_coordinates) - 1
                            ):
                                y_mid = 0.5 * (
                                    self.y_coordinates[bay]
                                    + self.y_coordinates[bay + 1]
                                )
                                arrow_at(
                                    map_point(
                                        self._project_3d(
                                            x_value,
                                            y_mid,
                                            z_value,
                                        )
                                    )
                                )

        if self.foundation_mode == "Springs":
            spring_pen = QPen(self.palette().highlight().color())
            spring_pen.setWidthF(1.5)
            painter.setPen(spring_pen)

            base_points: list[QPointF] = []
            if self.dimension == "2D":
                base_points = [
                    p(i, 0)
                    for i in range(len(self.x_coordinates))
                ]
            else:
                base_points = [
                    p(i, j, 0)
                    for j in range(len(self.y_coordinates))
                    for i in range(len(self.x_coordinates))
                ]

            for base_index, point in enumerate(base_points):
                painter.drawEllipse(
                    QRectF(
                        point.x() - 3.0,
                        point.y() - 3.0,
                        6.0,
                        6.0,
                    )
                )
                painter.drawLine(
                    QPointF(point.x(), point.y() + 3.0),
                    QPointF(point.x(), point.y() + 7.0),
                )
                zig = [
                    QPointF(point.x(), point.y() + 7.0),
                    QPointF(point.x() - 4.0, point.y() + 10.0),
                    QPointF(point.x() + 4.0, point.y() + 13.0),
                    QPointF(point.x() - 4.0, point.y() + 16.0),
                    QPointF(point.x(), point.y() + 19.0),
                ]
                for left, right in zip(zig[:-1], zig[1:]):
                    painter.drawLine(left, right)
                painter.drawLine(
                    QPointF(point.x() - 6.0, point.y() + 19.0),
                    QPointF(point.x() + 6.0, point.y() + 19.0),
                )
                if base_index < len(self.foundation_base_profiles):
                    profile_index = self.foundation_base_profiles[base_index]
                    profile_label = chr(ord("A") + profile_index)
                    painter.drawText(
                        int(point.x() + 7.0),
                        int(point.y() + 16.0),
                        profile_label,
                    )

        painter.setPen(self.palette().text().color())

        # X bay dimensions at the base.
        base_z = self.z_coordinates[0]
        for index, width in enumerate(self._intervals(self.x_coordinates)):
            midpoint = 0.5 * (
                self.x_coordinates[index] + self.x_coordinates[index + 1]
            )
            if self.dimension == "2D":
                point = map_point(QPointF(midpoint, base_z))
            else:
                point = map_point(self._project_3d(midpoint, y0, base_z))
            painter.drawText(
                int(point.x() - 24),
                int(point.y() + 20),
                f"X{index + 1}={width:g}",
            )

        # Storey dimensions along the left edge.
        for index, height in enumerate(self._intervals(self.z_coordinates)):
            midpoint = 0.5 * (
                self.z_coordinates[index] + self.z_coordinates[index + 1]
            )
            if self.dimension == "2D":
                point = map_point(QPointF(x0, midpoint))
            else:
                point = map_point(self._project_3d(x0, y0, midpoint))
            painter.drawText(
                int(point.x() - 58),
                int(point.y() + 4),
                f"H{index + 1}={height:g}",
            )

        if self.dimension == "3D":
            # Y dimensions on the projected base-left edge.
            for index, width in enumerate(self._intervals(self.y_coordinates)):
                midpoint = 0.5 * (
                    self.y_coordinates[index] + self.y_coordinates[index + 1]
                )
                point = map_point(self._project_3d(x0, midpoint, base_z))
                painter.drawText(
                    int(point.x() + 5),
                    int(point.y() - 4),
                    f"Y{index + 1}={width:g}",
                )

        painter.drawText(
            10,
            self.height() - 8,
            (
                f"{self.dimension} · origin "
                f"({x0:g}, {y0:g}, {z0:g}) · "
                f"{len(self.x_coordinates) - 1} X bay(s)"
                + (
                    f" × {len(self.y_coordinates) - 1} Y bay(s)"
                    if self.dimension == "3D"
                    else ""
                )
                + f" · {len(self.z_coordinates) - 1} storey(s)"
            ),
        )


class FrameWizard(QWizard):
    """Task 1: geometry/grid definition for FEWIZ's frame workflow."""

    def __init__(self, project: ProjectDatabase, parent=None):
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)

        self.setWindowTitle("Frame Wizard")
        self.setMinimumSize(780, 680)
        self.setWizardStyle(QWizard.ModernStyle)

        self._build_geometry_page()
        self._build_members_page()
        self._build_joints_page()
        self._build_floors_page()
        self._build_foundation_page()
        self._build_bracing_page()
        self._build_loads_page()
        self._build_mass_page()
        self._build_review_page()
        self.setButtonText(QWizard.FinishButton, "Generate Model")
        self.currentIdChanged.connect(self._review_page_changed)
        self._sync_dimension()
        self._sync_spacing_mode()
        self._sync_member_controls()
        self._sync_joint_controls()
        self._sync_diaphragm_controls()
        self._sync_foundation_controls()
        self._sync_brace_controls()
        self._sync_load_controls()
        self._sync_mass_controls()
        self._update_preview()
        self._update_member_summary()
        self._update_joint_summary()
        self._update_diaphragm_summary()
        self._update_foundation_summary()
        self._update_brace_summary()
        self._update_load_summary()
        self._update_mass_summary()
        self._update_review_page()

    @staticmethod
    def _spin(value: int, lo: int = 1, hi: int = 50) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(lo, hi)
        widget.setValue(value)
        return widget

    @staticmethod
    def _positive(value: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(4)
        widget.setRange(1.0e-6, 1.0e9)
        widget.setValue(value)
        return widget

    @staticmethod
    def _nonnegative(
        value: float = 0.0,
        *,
        decimals: int = 6,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(0.0, 1.0e12)
        widget.setValue(value)
        return widget

    @staticmethod
    def _coordinate(value: float = 0.0) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(4)
        widget.setRange(-1.0e9, 1.0e9)
        widget.setValue(value)
        return widget

    def _build_geometry_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Geometry & Grid")
        page.setSubTitle(
            "Define frame dimensionality, bay/storey layout, origin, member "
            "families and base support. Individual spacings are supported."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-geometry-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        geometry = QGroupBox("Frame layout")
        form = QFormLayout(geometry)

        self.dimension = QComboBox()
        self.dimension.addItem("2D Frame · X-Z", "2D")
        self.dimension.addItem("3D Frame · X-Y-Z", "3D")

        self.x_bays = self._spin(3)
        self.y_bays = self._spin(2)
        self.storeys = self._spin(3)

        self.x_spacing = self._positive(self.units.length_from_m(5.0))
        self.y_spacing = self._positive(self.units.length_from_m(5.0))
        self.storey_height = self._positive(
            self.units.length_from_m(3.5)
        )

        self.spacing_mode = QComboBox()
        self.spacing_mode.addItem("Uniform spacing", "Uniform")
        self.spacing_mode.addItem(
            "Individual bay / storey sizes",
            "Individual",
        )

        form.addRow("Dimension:", self.dimension)
        form.addRow("Spacing definition:", self.spacing_mode)
        form.addRow("X bays:", self.x_bays)
        form.addRow(
            f"Uniform X width [{self.units.length}]:",
            self.x_spacing,
        )
        form.addRow("Y bays:", self.y_bays)
        form.addRow(
            f"Uniform Y width [{self.units.length}]:",
            self.y_spacing,
        )
        form.addRow("Storeys:", self.storeys)
        form.addRow(
            f"Uniform storey height [{self.units.length}]:",
            self.storey_height,
        )
        layout.addWidget(geometry)

        self.x_spacing_editor = SpacingEditor(
            prefix="X",
            unit_label=self.units.length,
            count=self.x_bays.value(),
            default_value=self.x_spacing.value(),
        )
        self.y_spacing_editor = SpacingEditor(
            prefix="Y",
            unit_label=self.units.length,
            count=self.y_bays.value(),
            default_value=self.y_spacing.value(),
        )
        self.z_spacing_editor = SpacingEditor(
            prefix="H",
            unit_label=self.units.length,
            count=self.storeys.value(),
            default_value=self.storey_height.value(),
        )
        self.spacing_tabs = QTabWidget()
        self.spacing_tabs.addTab(self.x_spacing_editor, "X Bay Widths")
        self.spacing_tabs.addTab(self.y_spacing_editor, "Y Bay Widths")
        self.spacing_tabs.addTab(self.z_spacing_editor, "Storey Heights")
        layout.addWidget(self.spacing_tabs)

        origin = QGroupBox("Grid origin")
        origin_form = QFormLayout(origin)
        self.origin_x = self._coordinate()
        self.origin_y = self._coordinate()
        self.origin_z = self._coordinate()
        origin_form.addRow(
            f"X0 [{self.units.length}]:",
            self.origin_x,
        )
        origin_form.addRow(
            f"Y0 [{self.units.length}]:",
            self.origin_y,
        )
        origin_form.addRow(
            f"Z0 [{self.units.length}]:",
            self.origin_z,
        )
        layout.addWidget(origin)

        members = QGroupBox("Members")
        member_layout = QHBoxLayout(members)
        self.create_columns = QCheckBox("Columns")
        self.create_beams_x = QCheckBox("X beams")
        self.create_beams_y = QCheckBox("Y beams")
        for checkbox in (
            self.create_columns,
            self.create_beams_x,
            self.create_beams_y,
        ):
            checkbox.setChecked(True)
            member_layout.addWidget(checkbox)
        member_layout.addStretch(1)
        layout.addWidget(members)

        support = QGroupBox("Base support")
        support_form = QFormLayout(support)
        self.base_support = QComboBox()
        self.base_support.addItem("Fixed", "Fixed")
        self.base_support.addItem("Pinned", "Pinned")
        support_form.addRow("2D base support:", self.base_support)
        self.base_support_note = QLabel(
            "3D Task 1 uses fixed base nodes. More support patterns belong "
            "to the later boundary-condition task."
        )
        self.base_support_note.setWordWrap(True)
        support_form.addRow(self.base_support_note)
        layout.addWidget(support)

        self.preview = FramePreview()
        self.preview.setObjectName("frame-wizard-live-preview")
        layout.addWidget(self.preview)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.summary)

        self.validation_status = QLabel()
        self.validation_status.setWordWrap(True)
        self.validation_status.setObjectName(
            "frame-wizard-validation-status"
        )
        self.validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.geometry_scroll = scroll
        self.geometry_page_id = self.addPage(page)

        self.dimension.currentIndexChanged.connect(self._sync_dimension)
        self.spacing_mode.currentIndexChanged.connect(
            self._sync_spacing_mode
        )
        self.x_bays.valueChanged.connect(
            lambda value: self._resize_spacing_editor(
                self.x_spacing_editor,
                value,
            )
        )
        self.y_bays.valueChanged.connect(
            lambda value: self._resize_spacing_editor(
                self.y_spacing_editor,
                value,
            )
        )
        self.storeys.valueChanged.connect(
            lambda value: self._resize_spacing_editor(
                self.z_spacing_editor,
                value,
            )
        )

        for widget, editor in (
            (self.x_spacing, self.x_spacing_editor),
            (self.y_spacing, self.y_spacing_editor),
            (self.storey_height, self.z_spacing_editor),
        ):
            widget.valueChanged.connect(
                lambda value, target=editor: self._uniform_changed(
                    target,
                    value,
                )
            )

        for editor in (
            self.x_spacing_editor,
            self.y_spacing_editor,
            self.z_spacing_editor,
        ):
            editor.connect_value_changed(self._update_preview)

        for widget in (
            self.origin_x,
            self.origin_y,
            self.origin_z,
        ):
            widget.valueChanged.connect(self._update_preview)
        for widget in (
            self.create_columns,
            self.create_beams_x,
            self.create_beams_y,
        ):
            widget.toggled.connect(self._update_preview)
            widget.toggled.connect(self._update_member_summary)
        self.base_support.currentIndexChanged.connect(self._update_preview)

    def _build_members_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Members & Sections")
        page.setSubTitle(
            "Assign element formulations, section integration, geometric "
            "transformations, plastic-hinge sections and member mass."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-members-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.column_formulation = QComboBox()
        self.beam_formulation = QComboBox()
        for combo in (self.column_formulation, self.beam_formulation):
            combo.addItem("Elastic Beam-Column", "elasticBeamColumn")
            combo.addItem("Force-Based Beam-Column", "forceBeamColumn")
            combo.addItem(
                "Displacement-Based Beam-Column",
                "dispBeamColumn",
            )

        self.column_section = QComboBox()
        self.beam_section = QComboBox()
        self.column_transformation = QComboBox()
        self.beam_transformation = QComboBox()

        self.column_integration = QComboBox()
        self.beam_integration = QComboBox()
        integration_items = (
            ("Lobatto · distributed", "Lobatto"),
            ("Legendre · distributed", "Legendre"),
            ("Radau · distributed", "Radau"),
            ("HingeRadau", "HingeRadau"),
            ("HingeRadauTwo", "HingeRadauTwo"),
            ("HingeMidpoint", "HingeMidpoint"),
            ("HingeEndpoint", "HingeEndpoint"),
            ("Concentrated Plasticity", "ConcentratedPlasticity"),
        )
        for combo in (self.column_integration, self.beam_integration):
            for label, value in integration_items:
                combo.addItem(label, value)

        self.column_integration_points = self._spin(5, 2, 20)
        self.beam_integration_points = self._spin(5, 2, 20)

        self.column_hinge_i_section = QComboBox()
        self.column_hinge_j_section = QComboBox()
        self.column_interior_section = QComboBox()
        self.beam_hinge_i_section = QComboBox()
        self.beam_hinge_j_section = QComboBox()
        self.beam_interior_section = QComboBox()

        default_hinge = self.units.length_from_m(0.30)
        self.column_hinge_i_length = self._nonnegative(default_hinge)
        self.column_hinge_j_length = self._nonnegative(default_hinge)
        self.beam_hinge_i_length = self._nonnegative(default_hinge)
        self.beam_hinge_j_length = self._nonnegative(default_hinge)

        self.column_mass_per_length = self._nonnegative(0.0)
        self.beam_mass_per_length = self._nonnegative(0.0)
        self.column_consistent_mass = QCheckBox(
            "Use consistent mass matrix"
        )
        self.beam_consistent_mass = QCheckBox(
            "Use consistent mass matrix"
        )

        mass_unit = (
            f"{self.units.force}·{self.units.time}²/"
            f"{self.units.length}²"
        )

        column_box = QGroupBox("Columns")
        column_form = QFormLayout(column_box)
        column_form.addRow("Formulation:", self.column_formulation)
        column_form.addRow("Primary section:", self.column_section)
        column_form.addRow(
            "Geometric transformation:",
            self.column_transformation,
        )
        column_form.addRow(
            "Beam integration:",
            self.column_integration,
        )
        column_form.addRow(
            "Integration points:",
            self.column_integration_points,
        )
        column_form.addRow(
            "I-end hinge section:",
            self.column_hinge_i_section,
        )
        column_form.addRow(
            "J-end hinge section:",
            self.column_hinge_j_section,
        )
        column_form.addRow(
            "Interior section:",
            self.column_interior_section,
        )
        column_form.addRow(
            f"I-end hinge length [{self.units.length}]:",
            self.column_hinge_i_length,
        )
        column_form.addRow(
            f"J-end hinge length [{self.units.length}]:",
            self.column_hinge_j_length,
        )
        column_form.addRow(
            f"Mass / length [{mass_unit}]:",
            self.column_mass_per_length,
        )
        column_form.addRow("", self.column_consistent_mass)
        layout.addWidget(column_box)

        beam_box = QGroupBox("Beams")
        beam_form = QFormLayout(beam_box)
        beam_form.addRow("Formulation:", self.beam_formulation)
        beam_form.addRow("Primary section:", self.beam_section)
        beam_form.addRow(
            "Geometric transformation:",
            self.beam_transformation,
        )
        beam_form.addRow("Beam integration:", self.beam_integration)
        beam_form.addRow(
            "Integration points:",
            self.beam_integration_points,
        )
        beam_form.addRow(
            "I-end hinge section:",
            self.beam_hinge_i_section,
        )
        beam_form.addRow(
            "J-end hinge section:",
            self.beam_hinge_j_section,
        )
        beam_form.addRow(
            "Interior section:",
            self.beam_interior_section,
        )
        beam_form.addRow(
            f"I-end hinge length [{self.units.length}]:",
            self.beam_hinge_i_length,
        )
        beam_form.addRow(
            f"J-end hinge length [{self.units.length}]:",
            self.beam_hinge_j_length,
        )
        beam_form.addRow(
            f"Mass / length [{mass_unit}]:",
            self.beam_mass_per_length,
        )
        beam_form.addRow("", self.beam_consistent_mass)
        layout.addWidget(beam_box)

        note = QLabel(
            "Auto geomTransf uses PDelta for columns and Linear for beams. "
            "Distributed integrations use the Primary section. Hinge "
            "integrations use explicit I/J-end and interior sections. "
            "ConcentratedPlasticity does not use hinge lengths. "
            "forceBeamColumn accepts member mass but not a consistent-mass "
            "switch, so FEWIZ disables that option for force-based members."
        )
        note.setWordWrap(True)
        note.setStyleSheet("padding:8px;")
        layout.addWidget(note)

        self.member_summary = QLabel()
        self.member_summary.setWordWrap(True)
        self.member_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.member_summary)

        self.member_validation_status = QLabel()
        self.member_validation_status.setWordWrap(True)
        self.member_validation_status.setObjectName(
            "frame-wizard-member-validation-status"
        )
        self.member_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.member_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.members_scroll = scroll
        self.members_page_id = self.addPage(page)

        self._populate_member_dependencies()

        for combo in (
            self.column_formulation,
            self.beam_formulation,
        ):
            combo.currentIndexChanged.connect(
                self._member_formulation_changed
            )
        for combo in (
            self.column_integration,
            self.beam_integration,
        ):
            combo.currentIndexChanged.connect(
                self._member_integration_changed
            )
        for combo in (
            self.column_section,
            self.beam_section,
            self.column_transformation,
            self.beam_transformation,
            self.column_hinge_i_section,
            self.column_hinge_j_section,
            self.column_interior_section,
            self.beam_hinge_i_section,
            self.beam_hinge_j_section,
            self.beam_interior_section,
        ):
            combo.currentIndexChanged.connect(
                self._update_member_summary
            )
        for spin in (
            self.column_integration_points,
            self.beam_integration_points,
            self.column_hinge_i_length,
            self.column_hinge_j_length,
            self.beam_hinge_i_length,
            self.beam_hinge_j_length,
            self.column_mass_per_length,
            self.beam_mass_per_length,
        ):
            spin.valueChanged.connect(self._update_member_summary)
        for checkbox in (
            self.column_consistent_mass,
            self.beam_consistent_mass,
        ):
            checkbox.toggled.connect(self._update_member_summary)

    def _build_joints_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Beam–Column Joints")
        page.setSubTitle(
            "Define rigid, semi-rigid, RC joint-panel, or panel-zone "
            "behaviour at frame intersections."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-joints-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.joint_model = QComboBox()
        self.joint_model.addItem(
            "Rigid centerline · no explicit joint",
            "None",
        )
        self.joint_model.addItem(
            "Semi-rigid rotational spring · zeroLength",
            "ZeroLength",
        )
        self.joint_model.addItem(
            "Joint2D · panel shear + interface springs",
            "Joint2D",
        )
        self.joint_model.addItem(
            "RC BeamColumnJoint · 13 component materials",
            "BeamColumnJoint",
        )
        self.joint_model.addItem(
            "Krawinkler panel zone · rigid boundary + shear spring",
            "KrawinklerPanelZone",
        )

        self.joint_material = QComboBox()
        self.joint_scope = QComboBox()
        self.joint_scope.addItem("All elevated beam-column joints", "all")
        self.joint_scope.addItem(
            "Interior grid joints only",
            "interior",
        )

        model_box = QGroupBox("Joint model")
        model_form = QFormLayout(model_box)
        model_form.addRow("Connection model:", self.joint_model)
        model_form.addRow("Spring / panel material:", self.joint_material)
        model_form.addRow("Apply to:", self.joint_scope)
        layout.addWidget(model_box)

        self.joint_panel_width = self._positive(
            self.units.length_from_m(0.40)
        )
        self.joint_panel_height = self._positive(
            self.units.length_from_m(0.50)
        )
        panel_group = QGroupBox("Joint-core geometry")
        panel_form = QFormLayout(panel_group)
        panel_form.addRow(
            f"Panel width [{self.units.length}]:",
            self.joint_panel_width,
        )
        panel_form.addRow(
            f"Panel height [{self.units.length}]:",
            self.joint_panel_height,
        )
        panel_hint = QLabel(
            "Macro models use a native 2D/3DOF core. FEWIZ shortens adjacent "
            "beam/column centerlines to four external nodes. Joint2D and "
            "Krawinkler use Left → Top → Right → Bottom; BeamColumnJoint "
            "uses Top → Right → Bottom → Left so opposite chords align with "
            "the global 2D axes."
        )
        panel_hint.setWordWrap(True)
        panel_form.addRow(panel_hint)
        layout.addWidget(panel_group)
        self.joint_panel_group = panel_group

        joint2d_group = QGroupBox("Joint2D interface and panel response")
        joint2d_form = QFormLayout(joint2d_group)
        self.joint_interface_materials: list[QComboBox] = []
        for index in range(4):
            combo = QComboBox()
            self.joint_interface_materials.append(combo)
            joint2d_form.addRow(
                f"Interface Mat{index + 1}:",
                combo,
            )
        self.joint_large_disp = QComboBox()
        self.joint_large_disp.addItem("0 · small deformation", 0)
        self.joint_large_disp.addItem("1 · large deformation", 1)
        self.joint_large_disp.addItem(
            "2 · large deformation + length correction",
            2,
        )
        joint2d_form.addRow("Large displacement:", self.joint_large_disp)
        layout.addWidget(joint2d_group)
        self.joint2d_group = joint2d_group

        bcj_group = QGroupBox("BeamColumnJoint · 13 component materials")
        bcj_form = QFormLayout(bcj_group)
        self.bcj_labels = (
            "N1 bar-slip left",
            "N1 bar-slip right",
            "N1 interface shear",
            "N2 bar-slip bottom",
            "N2 bar-slip top",
            "N2 interface shear",
            "N3 bar-slip left",
            "N3 bar-slip right",
            "N3 interface shear",
            "N4 bar-slip bottom",
            "N4 bar-slip top",
            "N4 interface shear",
            "Shear panel",
        )
        self.bcj_materials: list[QComboBox] = []
        for index, label in enumerate(self.bcj_labels):
            combo = QComboBox()
            self.bcj_materials.append(combo)
            bcj_form.addRow(f"Mat{index + 1} · {label}:", combo)
        self.bcj_height_factor = self._positive(1.0)
        self.bcj_width_factor = self._positive(1.0)
        bcj_form.addRow("Effective height factor:", self.bcj_height_factor)
        bcj_form.addRow("Effective width factor:", self.bcj_width_factor)
        layout.addWidget(bcj_group)
        self.bcj_group = bcj_group

        kraw_group = QGroupBox("Krawinkler stiff panel-boundary members")
        kraw_form = QFormLayout(kraw_group)
        self.kraw_rigid_a = self._nonnegative(0.0)
        self.kraw_rigid_e = self._nonnegative(0.0)
        self.kraw_rigid_i = self._nonnegative(0.0)
        kraw_form.addRow("Rigid-link A:", self.kraw_rigid_a)
        kraw_form.addRow("Rigid-link E:", self.kraw_rigid_e)
        kraw_form.addRow("Rigid-link Iz:", self.kraw_rigid_i)
        kraw_hint = QLabel(
            "Enter deliberately stiff elastic-member properties in the "
            "active project unit system. The selected panel material supplies "
            "the nonlinear rotational/shear spring."
        )
        kraw_hint.setWordWrap(True)
        kraw_form.addRow(kraw_hint)
        layout.addWidget(kraw_group)
        self.kraw_group = kraw_group

        note = QLabel(
            "zeroLength keeps FEWIZ's 3D/6DOF planar convention. Joint2D, "
            "BeamColumnJoint and Krawinkler use a native 2D/3DOF joint-core "
            "model so OpenSees node order, rotational DOF and panel topology "
            "remain consistent."
        )
        note.setWordWrap(True)
        note.setStyleSheet("padding:8px;")
        layout.addWidget(note)

        self.joint_summary = QLabel()
        self.joint_summary.setWordWrap(True)
        self.joint_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.joint_summary)

        self.joint_validation_status = QLabel()
        self.joint_validation_status.setWordWrap(True)
        self.joint_validation_status.setObjectName(
            "frame-wizard-joint-validation-status"
        )
        self.joint_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.joint_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.joints_scroll = scroll
        self.joints_page_id = self.addPage(page)

        self._populate_joint_materials()
        for combo in (
            self.joint_model,
            self.joint_material,
            self.joint_scope,
            self.joint_large_disp,
            *self.joint_interface_materials,
            *self.bcj_materials,
        ):
            combo.currentIndexChanged.connect(
                self._joint_control_changed
            )
        for spin in (
            self.joint_panel_width,
            self.joint_panel_height,
            self.bcj_height_factor,
            self.bcj_width_factor,
            self.kraw_rigid_a,
            self.kraw_rigid_e,
            self.kraw_rigid_i,
        ):
            spin.valueChanged.connect(self._joint_control_changed)

        for widget in (
            self.dimension,
            self.x_bays,
            self.y_bays,
            self.storeys,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    self._joint_control_changed
                )
            else:
                widget.valueChanged.connect(
                    self._joint_control_changed
                )
        for checkbox in (
            self.create_columns,
            self.create_beams_x,
            self.create_beams_y,
        ):
            checkbox.toggled.connect(self._joint_control_changed)

    @staticmethod
    def _set_material_combo_items(
        combo: QComboBox,
        materials,
        *,
        allow_rigid_zero: bool = False,
        allow_none: bool = True,
    ) -> None:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        if allow_rigid_zero:
            combo.addItem("Rigid interface (0)", 0)
        elif allow_none:
            combo.addItem("Select material…", None)
        for tag, material in sorted(materials.items()):
            combo.addItem(
                f"{tag} · {material.name} [{material.material_type}]",
                int(tag),
            )
        if previous is not None:
            index = combo.findData(previous)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _populate_joint_materials(self) -> None:
        self._set_material_combo_items(
            self.joint_material,
            self.project.materials,
        )
        for combo in self.joint_interface_materials:
            self._set_material_combo_items(
                combo,
                self.project.materials,
                allow_rigid_zero=True,
                allow_none=False,
            )
        for combo in self.bcj_materials:
            self._set_material_combo_items(
                combo,
                self.project.materials,
            )

    def _joint_control_changed(self, *_args) -> None:
        self._sync_joint_controls()
        self._update_joint_summary()
        self._update_preview()

    def _sync_joint_controls(self, *_args) -> None:
        model = str(self.joint_model.currentData() or "None")
        active = model != "None"
        macro = model in {
            "Joint2D",
            "BeamColumnJoint",
            "KrawinklerPanelZone",
        }
        self.joint_scope.setEnabled(active)
        self.joint_material.setEnabled(
            model in {
                "ZeroLength",
                "Joint2D",
                "KrawinklerPanelZone",
            }
        )
        self.joint_panel_group.setVisible(macro)
        self.joint2d_group.setVisible(model == "Joint2D")
        self.bcj_group.setVisible(model == "BeamColumnJoint")
        self.kraw_group.setVisible(model == "KrawinklerPanelZone")

    def _joint_material_tags(self) -> set[int]:
        model = str(self.joint_model.currentData() or "None")
        tags: set[int] = set()
        if model in {
            "ZeroLength",
            "Joint2D",
            "KrawinklerPanelZone",
        }:
            value = self.joint_material.currentData()
            if value is not None:
                tags.add(int(value))
        if model == "Joint2D":
            tags.update(
                int(combo.currentData())
                for combo in self.joint_interface_materials
                if combo.currentData() not in {None, 0}
            )
        if model == "BeamColumnJoint":
            tags.update(
                int(combo.currentData())
                for combo in self.bcj_materials
                if combo.currentData() is not None
            )
        return tags

    def _joint_validation_error(self) -> str:
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            return str(exc)
        missing = sorted(
            tag
            for tag in self._joint_material_tags()
            if tag not in self.project.materials
        )
        if missing:
            return (
                "Joint material tag(s) no longer exist: "
                + ", ".join(map(str, missing))
            )
        return ""

    def _update_joint_summary(self, *_args) -> None:
        if not hasattr(self, "joint_summary"):
            return
        self._sync_joint_controls()
        try:
            spec = self.spec()
            count = frame_joint_connection_count(spec)
            error = self._joint_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            count = 0
            error = str(exc)

        if spec.joint_model == "ZeroLength":
            family_text = (
                "X beam springs"
                if spec.planar_2d
                else "X/Y beam-family springs"
            )
            self.joint_summary.setText(
                "<b>Joint generation summary</b><br>"
                f"Explicit springs: {count} · {family_text}<br>"
                f"Duplicate beam-side nodes: {count} · "
                f"equalDOF ties: {count}<br>"
                "Columns remain attached to the original grid nodes."
            )
        elif spec.joint_model in {
            "Joint2D",
            "BeamColumnJoint",
            "KrawinklerPanelZone",
        }:
            self.joint_summary.setText(
                "<b>Joint-core generation summary</b><br>"
                f"Joint cores: {count} · external panel nodes: {4 * count}<br>"
                f"Panel size: {spec.joint_panel_width:g} × "
                f"{spec.joint_panel_height:g} {self.units.length}<br>"
                "Adjacent beam/column members terminate at Left / Top / "
                "Right / Bottom external nodes; export uses native 2D/3DOF."
            )
        else:
            self.joint_summary.setText(
                "<b>Joint generation summary</b><br>"
                "Rigid centerline connectivity; no duplicate joint nodes, "
                "MPC ties or connection elements will be generated."
            )

        finish = self.button(QWizard.FinishButton)
        if error:
            self.joint_validation_status.setText(
                "<b>Joint definition needs attention</b><br>" + error
            )
            if finish is not None and self.currentId() == self.joints_page_id:
                finish.setEnabled(False)
        else:
            self.joint_validation_status.setText(
                "<b>Joint definition ready</b><br>"
                "The selected joint topology, materials and panel geometry "
                "are consistent with the frame definition."
            )
            if finish is not None and self.currentId() == self.joints_page_id:
                finish.setEnabled(True)

    def apply_to_project(self) -> dict[str, int]:
        """Generate the current Frame Wizard definition into the project."""
        return generate_frame_project(self.project, self.spec())

    def _build_floors_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Floors & Diaphragms")
        page.setSubTitle(
            "Choose no floor model, rigid diaphragm constraints, or an "
            "explicit semi-rigid shell slab with a conforming frame mesh."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-floors-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.diaphragm_mode = QComboBox()
        self.diaphragm_mode.addItem(
            "None · frame only",
            "None",
        )
        self.diaphragm_mode.addItem(
            "Rigid diaphragm · centroid master node",
            "Rigid",
        )
        self.diaphragm_mode.addItem(
            "Semi-rigid slab · explicit Shell FE mesh",
            "Shell",
        )

        mode_group = QGroupBox("Floor model")
        mode_form = QFormLayout(mode_group)
        mode_form.addRow("Floor behaviour:", self.diaphragm_mode)
        layout.addWidget(mode_group)

        self.diaphragm_level_table = QTableWidget(0, 2)
        self.diaphragm_level_table.setHorizontalHeaderLabels(
            ["Floor", f"Elevation [{self.units.length}]"]
        )
        self.diaphragm_level_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.diaphragm_level_table.setSelectionMode(
            QAbstractItemView.NoSelection
        )
        self.diaphragm_level_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.diaphragm_level_table.setMinimumHeight(170)
        self.diaphragm_level_table.setMaximumHeight(260)
        floor_group = QGroupBox("Apply floor model to")
        floor_layout = QVBoxLayout(floor_group)
        floor_layout.addWidget(self.diaphragm_level_table)
        layout.addWidget(floor_group)
        self.diaphragm_floor_group = floor_group

        self.diaphragm_floor_mass = self._nonnegative(0.0)
        self.diaphragm_rotational_inertia = self._nonnegative(0.0)
        mass_group = QGroupBox("Rigid diaphragm · optional lumped mass")
        mass_form = QFormLayout(mass_group)
        mass_form.addRow(
            f"Translational mass / floor [{self.units.mass_label}]:",
            self.diaphragm_floor_mass,
        )
        mass_form.addRow(
            "RZ rotational inertia [mass·length²]:",
            self.diaphragm_rotational_inertia,
        )
        mass_hint = QLabel(
            "The centroid master node carries UX/UY mass and optional RZ "
            "inertia. UZ/RX/RY are restrained to avoid free retained-node "
            "modes."
        )
        mass_hint.setWordWrap(True)
        mass_form.addRow(mass_hint)
        layout.addWidget(mass_group)
        self.diaphragm_mass_group = mass_group

        self.slab_section = QComboBox()
        self.slab_formulation = QComboBox()
        for label, value in (
            ("ASDShellQ4 · enhanced quadrilateral", "ASDShellQ4"),
            ("ShellMITC4 · mixed interpolation", "ShellMITC4"),
            ("ShellDKGQ · linear shell", "ShellDKGQ"),
            ("ShellNLDKGQ · nonlinear geometry shell", "ShellNLDKGQ"),
        ):
            self.slab_formulation.addItem(label, value)
        self.slab_divisions_x = QSpinBox()
        self.slab_divisions_y = QSpinBox()
        for spin in (self.slab_divisions_x, self.slab_divisions_y):
            spin.setRange(1, 50)
            spin.setValue(1)
        self.slab_corotational = QCheckBox(
            "ASDShellQ4 corotational formulation"
        )
        self.slab_mass_per_area = self._nonnegative(0.0)

        slab_group = QGroupBox("Semi-rigid explicit slab")
        slab_form = QFormLayout(slab_group)
        slab_form.addRow("Shell section:", self.slab_section)
        slab_form.addRow("Shell formulation:", self.slab_formulation)
        slab_form.addRow("Elements / structural X bay:", self.slab_divisions_x)
        slab_form.addRow("Elements / structural Y bay:", self.slab_divisions_y)
        slab_form.addRow("", self.slab_corotational)
        slab_form.addRow(
            (
                "Additional nodal mass / area "
                f"[{self.units.mass_label}/{self.units.length}²]:"
            ),
            self.slab_mass_per_area,
        )
        slab_hint = QLabel(
            "Shell edges are conforming with the frame. A 1×1 bay mesh uses "
            "the existing beam/column grid nodes directly. Refined meshes "
            "split elasticBeamColumn members along slab grid lines so Shell "
            "and beam nodes are physically shared. Section density remains "
            "available through the Shell section; added mass/area is optional "
            "and is distributed consistently to Shell nodes."
        )
        slab_hint.setWordWrap(True)
        slab_form.addRow(slab_hint)
        layout.addWidget(slab_group)
        self.slab_group = slab_group

        note = QLabel(
            "Rigid and explicit-shell floor models are mutually exclusive. "
            "Explicit slabs currently require 3D rigid-centerline joints. "
            "For nonlinear frame members use one Shell element per structural "
            "bay; refined conforming meshes are enabled for elastic beams."
        )
        note.setWordWrap(True)
        note.setStyleSheet("padding:8px;")
        layout.addWidget(note)

        self.diaphragm_summary = QLabel()
        self.diaphragm_summary.setWordWrap(True)
        self.diaphragm_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.diaphragm_summary)

        self.diaphragm_validation_status = QLabel()
        self.diaphragm_validation_status.setWordWrap(True)
        self.diaphragm_validation_status.setObjectName(
            "frame-wizard-diaphragm-validation-status"
        )
        self.diaphragm_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.diaphragm_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.floors_scroll = scroll
        self.floors_page_id = self.addPage(page)

        self._populate_slab_sections()
        self._refresh_diaphragm_levels()
        for combo in (
            self.diaphragm_mode,
            self.slab_section,
            self.slab_formulation,
        ):
            combo.currentIndexChanged.connect(
                self._diaphragm_control_changed
            )
        self.diaphragm_level_table.itemChanged.connect(
            self._diaphragm_control_changed
        )
        for spin in (
            self.diaphragm_floor_mass,
            self.diaphragm_rotational_inertia,
            self.slab_divisions_x,
            self.slab_divisions_y,
            self.slab_mass_per_area,
        ):
            spin.valueChanged.connect(self._diaphragm_control_changed)
        self.slab_corotational.toggled.connect(
            self._diaphragm_control_changed
        )
        self.storeys.valueChanged.connect(self._refresh_diaphragm_levels)
        self.origin_z.valueChanged.connect(self._refresh_diaphragm_levels)
        self.spacing_mode.currentIndexChanged.connect(
            self._refresh_diaphragm_levels
        )
        self.z_spacing_editor.connect_value_changed(
            self._refresh_diaphragm_levels
        )
        self.dimension.currentIndexChanged.connect(
            self._diaphragm_control_changed
        )
        for checkbox in (
            self.create_beams_x,
            self.create_beams_y,
        ):
            checkbox.toggled.connect(self._diaphragm_control_changed)
        self.beam_formulation.currentIndexChanged.connect(
            self._diaphragm_control_changed
        )
        self.joint_model.currentIndexChanged.connect(
            self._diaphragm_control_changed
        )

    def _populate_slab_sections(self) -> None:
        previous = self.slab_section.currentData()
        self.slab_section.blockSignals(True)
        self.slab_section.clear()
        self.slab_section.addItem("Select Shell section…", None)
        for tag in sorted(self.project.sections):
            section = self.project.sections[tag]
            if section.section_type not in SHELL_SECTION_TYPES:
                continue
            thickness = section.shell_total_thickness()
            thickness_text = (
                f" · h={thickness:g} {self.units.length}"
                if thickness > 0.0
                else ""
            )
            self.slab_section.addItem(
                f"{tag} · {section.name} ({section.section_type})"
                + thickness_text,
                int(tag),
            )
        if previous is not None:
            index = self.slab_section.findData(previous)
            if index >= 0:
                self.slab_section.setCurrentIndex(index)
        elif self.slab_section.count() == 2:
            self.slab_section.setCurrentIndex(1)
        self.slab_section.blockSignals(False)

    def _selected_diaphragm_levels(self) -> tuple[int, ...]:
        levels: list[int] = []
        for row in range(self.diaphragm_level_table.rowCount()):
            item = self.diaphragm_level_table.item(row, 0)
            if (
                item is not None
                and item.checkState() == Qt.Checked
            ):
                level = item.data(Qt.UserRole)
                if level is not None:
                    levels.append(int(level))
        return tuple(levels)

    def _refresh_diaphragm_levels(self, *_args) -> None:
        if not hasattr(self, "diaphragm_level_table"):
            return
        selected = set(self._selected_diaphragm_levels())
        had_rows = self.diaphragm_level_table.rowCount() > 0
        try:
            _, _, z_coordinates = frame_grid_coordinates(self.spec())
        except (TypeError, ValueError):
            z_coordinates = [
                float(self.origin_z.value())
                + index * float(self.storey_height.value())
                for index in range(int(self.storeys.value()) + 1)
            ]

        table = self.diaphragm_level_table
        table.blockSignals(True)
        table.setRowCount(int(self.storeys.value()))
        for row in range(table.rowCount()):
            level = row + 1
            item = QTableWidgetItem(f"Floor {level}")
            item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
            )
            item.setData(Qt.UserRole, level)
            item.setCheckState(
                Qt.Checked
                if (not had_rows or level in selected)
                else Qt.Unchecked
            )
            table.setItem(row, 0, item)

            elevation = (
                z_coordinates[level]
                if level < len(z_coordinates)
                else float(self.origin_z.value())
            )
            elevation_item = QTableWidgetItem(f"{elevation:g}")
            elevation_item.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 1, elevation_item)
        table.blockSignals(False)
        self._update_diaphragm_summary()
        self._update_preview()

    def _diaphragm_control_changed(self, *_args) -> None:
        self._sync_diaphragm_controls()
        self._update_diaphragm_summary()
        self._update_preview()

    def _sync_diaphragm_controls(self, *_args) -> None:
        if not hasattr(self, "diaphragm_mode"):
            return
        mode = str(self.diaphragm_mode.currentData() or "None")
        active = mode != "None"
        self.diaphragm_floor_group.setEnabled(active)
        self.diaphragm_mass_group.setVisible(mode == "Rigid")
        self.slab_group.setVisible(mode == "Shell")
        self.slab_corotational.setEnabled(
            self.slab_formulation.currentData() == "ASDShellQ4"
        )
        if self.slab_formulation.currentData() != "ASDShellQ4":
            self.slab_corotational.setChecked(False)

    def _diaphragm_validation_error(self) -> str:
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            return str(exc)

        mode = str(self.diaphragm_mode.currentData() or "None")
        if mode in {"Rigid", "Shell"} and not self._selected_diaphragm_levels():
            return "Select at least one elevated floor for the floor model."
        if mode == "Shell":
            tag = self.slab_section.currentData()
            if tag is None:
                return "Select a shell-compatible section for the slab."
            section = self.project.sections.get(int(tag))
            if section is None:
                return f"Slab section {int(tag)} no longer exists."
            if section.section_type not in SHELL_SECTION_TYPES:
                return "Selected slab section is not shell-compatible."
        return ""

    def _update_diaphragm_summary(self, *_args) -> None:
        if not hasattr(self, "diaphragm_summary"):
            return
        self._sync_diaphragm_controls()
        try:
            spec = self.spec()
            error = self._diaphragm_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            error = str(exc)

        if spec.diaphragm_mode == "Rigid":
            count = frame_diaphragm_count(spec)
            levels = frame_diaphragm_levels(spec)
            nodes_per_floor = (
                (int(spec.nx) + 1) * (int(spec.ny) + 1)
                if not spec.planar_2d
                else 0
            )
            self.diaphragm_summary.setText(
                "<b>Rigid floor diaphragm summary</b><br>"
                f"Rigid diaphragms: {count} · floors: "
                + ", ".join(map(str, levels))
                + "<br>"
                f"Centroid master nodes: {count} · constrained grid nodes / "
                f"floor: {nodes_per_floor}<br>"
                f"Mass / floor: {spec.diaphragm_floor_mass:g} "
                f"{self.units.mass_label} · RZ inertia: "
                f"{spec.diaphragm_rotational_inertia:g}"
            )
        elif spec.diaphragm_mode == "Shell":
            levels = frame_floor_levels(spec)
            floor_count = frame_slab_count(spec)
            per_floor = (
                int(spec.nx)
                * int(spec.ny)
                * int(spec.slab_divisions_x)
                * int(spec.slab_divisions_y)
            )
            refined_nodes = (
                int(spec.nx) * int(spec.slab_divisions_x) + 1
            ) * (
                int(spec.ny) * int(spec.slab_divisions_y) + 1
            )
            self.diaphragm_summary.setText(
                "<b>Semi-rigid slab summary</b><br>"
                f"Shell floors: {floor_count} · floors: "
                + ", ".join(map(str, levels))
                + "<br>"
                f"Shell elements / floor: {per_floor} · mesh nodes / floor: "
                f"{refined_nodes}<br>"
                f"{spec.slab_element_type} · "
                f"{self.slab_section.currentText()}<br>"
                f"Additional nodal mass/area: {spec.slab_mass_per_area:g} "
                f"{self.units.mass_label}/{self.units.length}²"
            )
        else:
            self.diaphragm_summary.setText(
                "<b>Floor model summary</b><br>"
                "No diaphragm constraints or explicit slab Shell elements "
                "will be generated."
            )

        finish = self.button(QWizard.FinishButton)
        if error:
            self.diaphragm_validation_status.setText(
                "<b>Floor definition needs attention</b><br>" + error
            )
            if finish is not None and self.currentId() == self.floors_page_id:
                finish.setEnabled(False)
        else:
            self.diaphragm_validation_status.setText(
                "<b>Floor definition ready</b><br>"
                "Selected floors and the active rigid/shell floor model are "
                "consistent with the frame definition."
            )
            if finish is not None and self.currentId() == self.floors_page_id:
                finish.setEnabled(True)

    def _build_foundation_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Foundation & Base Springs")
        page.setSubTitle(
            "Use direct support, one uniform spring profile, or assign "
            "equivalent footing / pile-group / soil spring profiles per base."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-foundation-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.foundation_mode = QComboBox()
        self.foundation_mode.addItem(
            "Direct support · use Geometry page base restraint",
            "Direct",
        )
        self.foundation_mode.addItem(
            "Equivalent foundation springs · zeroLength to fixed ground",
            "Springs",
        )
        self.foundation_assignment_mode = QComboBox()
        self.foundation_assignment_mode.addItem(
            "Uniform · Profile A at every base",
            "Uniform",
        )
        self.foundation_assignment_mode.addItem(
            "Per-base · assign A / B / C by column base",
            "PerBase",
        )

        mode_group = QGroupBox("Foundation model")
        mode_form = QFormLayout(mode_group)
        mode_form.addRow("Base model:", self.foundation_mode)
        mode_form.addRow("Assignment:", self.foundation_assignment_mode)
        layout.addWidget(mode_group)

        self.foundation_dof_labels = (
            "UX · global X translation",
            "UY · global Y translation",
            "UZ · global Z translation",
            "RX · rotation about global X",
            "RY · rotation about global Y",
            "RZ · rotation about global Z",
        )
        self.foundation_profile_names = (
            "A · Isolated footing equivalent",
            "B · Pile-group equivalent",
            "C · Custom soil spring group",
        )
        self.foundation_profile_materials: list[list[QComboBox]] = []
        self.foundation_profile_tabs = QTabWidget()
        for profile_name in self.foundation_profile_names:
            tab = QWidget()
            form = QFormLayout(tab)
            materials: list[QComboBox] = []
            for label in self.foundation_dof_labels:
                combo = QComboBox()
                materials.append(combo)
                form.addRow(label + ":", combo)
            hint = QLabel(
                "Positive uniaxial material = flexible/nonlinear spring DOF. "
                "Rigid transfer = equalDOF to the coincident fixed ground "
                "node. The profile name describes the equivalent macro-model; "
                "the actual response comes from the selected project materials."
            )
            hint.setWordWrap(True)
            form.addRow(hint)
            self.foundation_profile_materials.append(materials)
            self.foundation_profile_tabs.addTab(tab, profile_name)

        # Backward-compatible alias used by the first Foundation stage/tests.
        self.foundation_materials = self.foundation_profile_materials[0]

        spring_group = QGroupBox("Equivalent spring profiles")
        spring_layout = QVBoxLayout(spring_group)
        spring_layout.addWidget(self.foundation_profile_tabs)
        layout.addWidget(spring_group)
        self.foundation_spring_group = spring_group

        self.foundation_base_table = QTableWidget(0, 4)
        self.foundation_base_table.setHorizontalHeaderLabels(
            ["Base", "Grid", "Coordinates", "Profile"]
        )
        self.foundation_base_table.horizontalHeader().setStretchLastSection(True)
        self.foundation_base_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.foundation_base_table.setSelectionMode(
            QAbstractItemView.NoSelection
        )
        self.foundation_base_table.setMinimumHeight(180)
        self.foundation_base_table.setMaximumHeight(300)
        assignment_group = QGroupBox("Per-base profile assignment")
        assignment_layout = QVBoxLayout(assignment_group)
        assignment_layout.addWidget(self.foundation_base_table)
        assignment_hint = QLabel(
            "Rows are ordered X-fast, then Y. Profile A/B/C may therefore be "
            "used for edge/interior footings, pile-supported columns, or local "
            "soil zones without duplicating the frame geometry."
        )
        assignment_hint.setWordWrap(True)
        assignment_layout.addWidget(assignment_hint)
        layout.addWidget(assignment_group)
        self.foundation_assignment_group = assignment_group

        note = QLabel(
            "These are equivalent foundation macro-springs, not explicit "
            "footing solids or pile beam elements. FEWIZ creates one fixed "
            "ground node and one zeroLength connection per column base. "
            "Native 2D macro-joint frames retain direct fixed/pinned support."
        )
        note.setWordWrap(True)
        note.setStyleSheet("padding:8px;")
        layout.addWidget(note)

        self.foundation_summary = QLabel()
        self.foundation_summary.setWordWrap(True)
        self.foundation_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.foundation_summary)

        self.foundation_validation_status = QLabel()
        self.foundation_validation_status.setWordWrap(True)
        self.foundation_validation_status.setObjectName(
            "frame-wizard-foundation-validation-status"
        )
        self.foundation_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.foundation_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.foundation_scroll = scroll
        self.foundation_page_id = self.addPage(page)

        self._populate_foundation_materials()
        self._refresh_foundation_base_table()

        self.foundation_mode.currentIndexChanged.connect(
            self._foundation_control_changed
        )
        self.foundation_assignment_mode.currentIndexChanged.connect(
            self._foundation_control_changed
        )
        for materials in self.foundation_profile_materials:
            for combo in materials:
                combo.currentIndexChanged.connect(
                    self._foundation_control_changed
                )

        self.dimension.currentIndexChanged.connect(
            self._foundation_geometry_changed
        )
        self.joint_model.currentIndexChanged.connect(
            self._foundation_control_changed
        )
        self.create_columns.toggled.connect(
            self._foundation_control_changed
        )
        for spin in (self.x_bays, self.y_bays):
            spin.valueChanged.connect(self._foundation_geometry_changed)
        for spin in (
            self.x_spacing,
            self.y_spacing,
            self.origin_x,
            self.origin_y,
        ):
            spin.valueChanged.connect(self._foundation_geometry_changed)
        self.spacing_mode.currentIndexChanged.connect(
            self._foundation_geometry_changed
        )
        self.x_spacing_editor.connect_value_changed(
            self._foundation_geometry_changed
        )
        self.y_spacing_editor.connect_value_changed(
            self._foundation_geometry_changed
        )

    def _populate_foundation_materials(self) -> None:
        for materials in self.foundation_profile_materials:
            for combo in materials:
                previous = combo.currentData()
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("Rigid transfer · no spring", 0)
                for tag, material in sorted(self.project.materials.items()):
                    combo.addItem(
                        f"{tag} · {material.name} [{material.material_type}]",
                        int(tag),
                    )
                if previous is not None:
                    index = combo.findData(previous)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                combo.blockSignals(False)

    def _foundation_active_dofs(self) -> tuple[int, ...]:
        return (
            (1, 3, 5)
            if self.dimension.currentData() == "2D"
            else (1, 2, 3, 4, 5, 6)
        )

    def _foundation_profile_tags(self) -> tuple[tuple[int, ...], ...]:
        if not hasattr(self, "foundation_profile_materials"):
            return ()
        return tuple(
            tuple(int(combo.currentData() or 0) for combo in materials)
            for materials in self.foundation_profile_materials
        )

    def _foundation_base_profile_indices(self) -> tuple[int, ...]:
        if not hasattr(self, "foundation_base_table"):
            return ()
        values: list[int] = []
        for row in range(self.foundation_base_table.rowCount()):
            combo = self.foundation_base_table.cellWidget(row, 3)
            if isinstance(combo, QComboBox):
                values.append(int(combo.currentData() or 0))
        return tuple(values)

    def _foundation_geometry_changed(self, *_args) -> None:
        self._refresh_foundation_base_table()
        self._foundation_control_changed()

    def _refresh_foundation_base_table(self, *_args) -> None:
        if not hasattr(self, "foundation_base_table"):
            return

        old_assignments = self._foundation_base_profile_indices()
        dimension = str(self.dimension.currentData() or "2D")
        try:
            spec = self.spec()
            x_coordinates, y_coordinates, _ = frame_grid_coordinates(spec)
        except (TypeError, ValueError):
            x_coordinates = [
                float(self.origin_x.value())
                + index * float(self.x_spacing.value())
                for index in range(int(self.x_bays.value()) + 1)
            ]
            y_coordinates = (
                [0.0]
                if dimension == "2D"
                else [
                    float(self.origin_y.value())
                    + index * float(self.y_spacing.value())
                    for index in range(int(self.y_bays.value()) + 1)
                ]
            )

        rows: list[tuple[str, str, str]] = []
        if dimension == "2D":
            for i, x in enumerate(x_coordinates):
                rows.append(
                    (
                        f"B{i + 1}",
                        f"X{i + 1}",
                        f"({x:g}, 0)",
                    )
                )
        else:
            number = 1
            for j, y in enumerate(y_coordinates):
                for i, x in enumerate(x_coordinates):
                    rows.append(
                        (
                            f"B{number}",
                            f"X{i + 1} / Y{j + 1}",
                            f"({x:g}, {y:g})",
                        )
                    )
                    number += 1

        table = self.foundation_base_table
        table.setRowCount(len(rows))
        for row, (base_name, grid_name, coordinate_text) in enumerate(rows):
            for column, text_value in enumerate(
                (base_name, grid_name, coordinate_text)
            ):
                item = QTableWidgetItem(text_value)
                item.setFlags(Qt.ItemIsEnabled)
                table.setItem(row, column, item)

            combo = QComboBox()
            for index, profile_name in enumerate(self.foundation_profile_names):
                combo.addItem(profile_name, index)
            previous = (
                old_assignments[row]
                if row < len(old_assignments)
                else 0
            )
            profile_index = combo.findData(previous)
            combo.setCurrentIndex(profile_index if profile_index >= 0 else 0)
            combo.currentIndexChanged.connect(
                self._foundation_control_changed
            )
            table.setCellWidget(row, 3, combo)

        self._sync_foundation_controls()

    def _foundation_control_changed(self, *_args) -> None:
        self._sync_foundation_controls()
        self._update_foundation_summary()
        self._update_preview()

    def _sync_foundation_controls(self, *_args) -> None:
        if not hasattr(self, "foundation_mode"):
            return
        spring_mode = self.foundation_mode.currentData() == "Springs"
        per_base = (
            self.foundation_assignment_mode.currentData() == "PerBase"
        )
        active_dofs = set(self._foundation_active_dofs())

        self.foundation_spring_group.setEnabled(spring_mode)
        self.foundation_assignment_mode.setEnabled(spring_mode)
        self.foundation_assignment_group.setEnabled(spring_mode and per_base)
        for tab_index, materials in enumerate(
            self.foundation_profile_materials
        ):
            self.foundation_profile_tabs.setTabEnabled(
                tab_index,
                spring_mode and (tab_index == 0 or per_base),
            )
            for dof, combo in enumerate(materials, start=1):
                combo.setEnabled(
                    spring_mode
                    and (tab_index == 0 or per_base)
                    and dof in active_dofs
                )

        if spring_mode:
            self.base_support.setEnabled(False)
        else:
            self.base_support.setEnabled(
                self.dimension.currentData() == "2D"
            )

    def _foundation_material_tags(self) -> tuple[int, ...]:
        profiles = self._foundation_profile_tags()
        return profiles[0] if profiles else (0, 0, 0, 0, 0, 0)

    def _foundation_validation_error(self) -> str:
        try:
            spec = self.spec()
            validate_frame_grid_spec(spec)
        except (TypeError, ValueError) as exc:
            return str(exc)

        if self.foundation_mode.currentData() != "Springs":
            return ""

        active = set(self._foundation_active_dofs())
        profiles = frame_foundation_profiles(spec)
        assignments = frame_foundation_profile_assignments(spec)
        used_profiles = sorted(set(assignments))
        missing = sorted({
            int(tag)
            for profile_index in used_profiles
            for dof, tag in enumerate(
                profiles[profile_index],
                start=1,
            )
            if (
                dof in active
                and int(tag) > 0
                and int(tag) not in self.project.materials
            )
        })
        if missing:
            return (
                "Foundation material tag(s) no longer exist: "
                + ", ".join(map(str, missing))
            )
        return ""

    def _update_foundation_summary(self, *_args) -> None:
        if not hasattr(self, "foundation_summary"):
            return
        self._sync_foundation_controls()
        try:
            spec = self.spec()
            count = frame_foundation_count(spec)
            error = self._foundation_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            count = 0
            error = str(exc)

        if spec.foundation_mode == "Springs":
            active = self._foundation_active_dofs()
            names = ("UX", "UY", "UZ", "RX", "RY", "RZ")
            profiles = frame_foundation_profiles(spec)
            assignments = frame_foundation_profile_assignments(spec)
            usage = {
                index: assignments.count(index)
                for index in sorted(set(assignments))
            }
            rows: list[str] = []
            for profile_index, base_count in usage.items():
                profile = profiles[profile_index]
                flexible = [
                    names[dof - 1]
                    for dof in active
                    if int(profile[dof - 1]) > 0
                ]
                rigid = [
                    names[dof - 1]
                    for dof in active
                    if int(profile[dof - 1]) == 0
                ]
                label = chr(ord("A") + profile_index)
                rows.append(
                    f"Profile {label}: {base_count} base(s) · spring "
                    f"{', '.join(flexible) or 'none'} · rigid "
                    f"{', '.join(rigid) or 'none'}"
                )

            self.foundation_summary.setText(
                "<b>Foundation spring summary</b><br>"
                f"Column bases: {count} · zeroLength connections: {count} · "
                f"fixed ground nodes: {count}<br>"
                f"Assignment: {spec.foundation_assignment_mode}<br>"
                + "<br>".join(rows)
            )
        else:
            support = (
                self.base_support.currentText()
                if spec.planar_2d
                else "Fixed"
            )
            self.foundation_summary.setText(
                "<b>Foundation summary</b><br>"
                f"Direct base support: {support}. No ground nodes, "
                "foundation spring connections or foundation MPCs will be "
                "generated."
            )

        finish = self.button(QWizard.FinishButton)
        if error:
            self.foundation_validation_status.setText(
                "<b>Foundation definition needs attention</b><br>" + error
            )
            if (
                finish is not None
                and self.currentId() == self.foundation_page_id
            ):
                finish.setEnabled(False)
        else:
            self.foundation_validation_status.setText(
                "<b>Foundation definition ready</b><br>"
                "Equivalent foundation profiles, per-base assignments and "
                "uniaxial spring materials are consistent with the frame."
            )
            if (
                finish is not None
                and self.currentId() == self.foundation_page_id
            ):
                finish.setEnabled(True)

    def _build_bracing_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Bracing")
        page.setSubTitle(
            "Create axial truss bracing in X-Z, Y-Z or both frame-plane "
            "families, with optional per-panel mixed patterns."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-bracing-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.brace_mode = QComboBox()
        self.brace_mode.addItem("None · moment frame only", "None")
        self.brace_mode.addItem(
            "Truss bracing · explicit axial elements",
            "Truss",
        )

        self.brace_plane_mode = QComboBox()
        self.brace_plane_mode.addItem("X-Z planes", "X")
        self.brace_plane_mode.addItem("Y-Z planes", "Y")
        self.brace_plane_mode.addItem("Both X-Z and Y-Z planes", "Both")

        self.brace_pattern = QComboBox()
        for label, value in (
            ("Single diagonal /", "DiagonalForward"),
            ("Single diagonal \\", "DiagonalBackward"),
            ("X bracing", "X"),
            ("Chevron · meet upper beam midpoint", "VUpper"),
            ("Chevron · meet lower beam midpoint", "VLower"),
            ("K bracing · left-column midpoint", "KLeft"),
            ("K bracing · right-column midpoint", "KRight"),
        ):
            self.brace_pattern.addItem(label, value)
        self.brace_pattern.setCurrentIndex(
            self.brace_pattern.findData("X")
        )

        self.brace_response_preset = QComboBox()
        self.brace_response_preset.addItem(
            "Standard axial brace",
            "Standard",
        )
        self.brace_response_preset.addItem(
            "Nonlinear-ready · use calibrated hysteretic material",
            "NonlinearReady",
        )
        self.brace_response_preset.addItem(
            "BRB-ready · calibrated BRB axial material required",
            "BRBReady",
        )

        self.brace_element_type = QComboBox()
        self.brace_element_type.addItem("Truss · linear geometry", "truss")
        self.brace_element_type.addItem(
            "corotTruss · corotational geometry",
            "corotTruss",
        )
        self.brace_material = QComboBox()
        self.brace_area = self._positive(
            self.units.length_from_m(0.1) ** 2
        )
        self.brace_mass_per_length = self._nonnegative(0.0)
        self.brace_do_rayleigh = QCheckBox(
            "Include brace element in Rayleigh damping"
        )

        model_group = QGroupBox("Brace element")
        model_form = QFormLayout(model_group)
        model_form.addRow("Bracing:", self.brace_mode)
        model_form.addRow("Plane family:", self.brace_plane_mode)
        model_form.addRow("Default pattern:", self.brace_pattern)
        model_form.addRow("Response workflow:", self.brace_response_preset)
        model_form.addRow("Element formulation:", self.brace_element_type)
        model_form.addRow("Uniaxial material:", self.brace_material)
        model_form.addRow(
            f"Area [{self.units.length}²]:",
            self.brace_area,
        )
        model_form.addRow(
            f"Mass / length [{self.units.mass_label}/{self.units.length}]:",
            self.brace_mass_per_length,
        )
        model_form.addRow("", self.brace_do_rayleigh)
        preset_hint = QLabel(
            "Nonlinear-ready / BRB-ready are workflow presets only. FEWIZ "
            "does not invent a BRB constitutive law: select a calibrated "
            "nonlinear uniaxial material from the project. BRB-ready switches "
            "the element to corotTruss and rejects a purely Elastic material."
        )
        preset_hint.setWordWrap(True)
        model_form.addRow(preset_hint)
        layout.addWidget(model_group)
        self.brace_model_group = model_group

        def make_scope_table(headers: list[str]) -> QTableWidget:
            table = QTableWidget(0, 2)
            table.setHorizontalHeaderLabels(headers)
            table.horizontalHeader().setStretchLastSection(True)
            table.setSelectionMode(QAbstractItemView.NoSelection)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setMinimumHeight(140)
            table.setMaximumHeight(220)
            return table

        self.brace_x_table = make_scope_table(["X bay", "Brace"])
        self.brace_y_table = make_scope_table(["Y bay", "Brace"])
        self.brace_storey_table = make_scope_table(["Storey", "Brace"])

        scope_tabs = QTabWidget()
        scope_tabs.addTab(self.brace_x_table, "X Bays")
        scope_tabs.addTab(self.brace_y_table, "Y Bays")
        scope_tabs.addTab(self.brace_storey_table, "Storeys")

        self.brace_y_plane_scope = QComboBox()
        self.brace_y_plane_scope.addItem(
            "All X-Z grid planes",
            "All",
        )
        self.brace_y_plane_scope.addItem(
            "Exterior Y-min / Y-max planes",
            "Exterior",
        )
        self.brace_y_plane_scope.addItem("Y-min plane only", "YMin")
        self.brace_y_plane_scope.addItem("Y-max plane only", "YMax")

        self.brace_x_plane_scope = QComboBox()
        self.brace_x_plane_scope.addItem(
            "All Y-Z grid planes",
            "All",
        )
        self.brace_x_plane_scope.addItem(
            "Exterior X-min / X-max planes",
            "Exterior",
        )
        self.brace_x_plane_scope.addItem("X-min plane only", "XMin")
        self.brace_x_plane_scope.addItem("X-max plane only", "XMax")

        scope_group = QGroupBox("Brace panel scope")
        scope_layout = QVBoxLayout(scope_group)
        scope_layout.addWidget(scope_tabs)
        scope_form = QFormLayout()
        scope_form.addRow("X-Z planes at Y grid lines:", self.brace_y_plane_scope)
        scope_form.addRow("Y-Z planes at X grid lines:", self.brace_x_plane_scope)
        scope_layout.addLayout(scope_form)
        layout.addWidget(scope_group)
        self.brace_scope_group = scope_group

        self.brace_panel_table = QTableWidget(0, 5)
        self.brace_panel_table.setHorizontalHeaderLabels(
            ["Plane", "Grid line", "Bay", "Storey", "Pattern override"]
        )
        self.brace_panel_table.horizontalHeader().setStretchLastSection(True)
        self.brace_panel_table.setSelectionMode(
            QAbstractItemView.NoSelection
        )
        self.brace_panel_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.brace_panel_table.setMinimumHeight(200)
        self.brace_panel_table.setMaximumHeight(330)

        matrix_group = QGroupBox("Per-panel mixed pattern matrix")
        matrix_layout = QVBoxLayout(matrix_group)
        matrix_layout.addWidget(self.brace_panel_table)
        matrix_hint = QLabel(
            "Default uses the pattern selected above. Override any active "
            "panel independently, including Off. Panel keys are regenerated "
            "automatically when bays, storeys or plane scope change."
        )
        matrix_hint.setWordWrap(True)
        matrix_layout.addWidget(matrix_hint)
        layout.addWidget(matrix_group)
        self.brace_matrix_group = matrix_group

        note = QLabel(
            "Diagonal/X patterns use existing grid joints. Chevron layouts "
            "split the matching X- or Y-beam at its midpoint. K-left/right "
            "split the corresponding column. Midpoint patterns require "
            "elasticBeamColumn frame members."
        )
        note.setWordWrap(True)
        note.setStyleSheet("padding:8px;")
        layout.addWidget(note)

        self.brace_summary = QLabel()
        self.brace_summary.setWordWrap(True)
        self.brace_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.brace_summary)

        self.brace_validation_status = QLabel()
        self.brace_validation_status.setWordWrap(True)
        self.brace_validation_status.setObjectName(
            "frame-wizard-brace-validation-status"
        )
        self.brace_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.brace_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.bracing_scroll = scroll
        self.bracing_page_id = self.addPage(page)

        self._populate_brace_materials()
        self._refresh_brace_scope_tables()

        for combo in (
            self.brace_mode,
            self.brace_plane_mode,
            self.brace_pattern,
            self.brace_element_type,
            self.brace_material,
            self.brace_y_plane_scope,
            self.brace_x_plane_scope,
        ):
            combo.currentIndexChanged.connect(self._brace_control_changed)
        self.brace_response_preset.currentIndexChanged.connect(
            self._brace_preset_changed
        )
        for spin in (self.brace_area, self.brace_mass_per_length):
            spin.valueChanged.connect(self._brace_control_changed)
        self.brace_do_rayleigh.toggled.connect(self._brace_control_changed)
        for table in (
            self.brace_x_table,
            self.brace_y_table,
            self.brace_storey_table,
        ):
            table.itemChanged.connect(self._brace_scope_changed)

        for widget in (
            self.dimension,
            self.x_bays,
            self.y_bays,
            self.storeys,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    self._brace_geometry_changed
                )
            else:
                widget.valueChanged.connect(self._brace_geometry_changed)
        self.create_columns.toggled.connect(self._brace_control_changed)
        self.create_beams_x.toggled.connect(self._brace_control_changed)
        self.create_beams_y.toggled.connect(self._brace_control_changed)
        self.joint_model.currentIndexChanged.connect(
            self._brace_control_changed
        )
        self.beam_formulation.currentIndexChanged.connect(
            self._brace_control_changed
        )
        self.column_formulation.currentIndexChanged.connect(
            self._brace_control_changed
        )

    def _populate_brace_materials(self) -> None:
        previous = self.brace_material.currentData()
        self.brace_material.blockSignals(True)
        self.brace_material.clear()
        self.brace_material.addItem("Select material…", None)
        for tag, material in sorted(self.project.materials.items()):
            self.brace_material.addItem(
                f"{tag} · {material.name} [{material.material_type}]",
                int(tag),
            )
        if previous is not None:
            index = self.brace_material.findData(previous)
            if index >= 0:
                self.brace_material.setCurrentIndex(index)
        self.brace_material.blockSignals(False)

    @staticmethod
    def _checked_rows(table: QTableWidget, *, offset: int = 0) -> tuple[int, ...]:
        values: list[int] = []
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item is not None and item.checkState() == Qt.Checked:
                values.append(row + offset)
        return tuple(values)

    def _selected_brace_x_bays(self) -> tuple[int, ...]:
        return (
            self._checked_rows(self.brace_x_table)
            if hasattr(self, "brace_x_table")
            else ()
        )

    def _selected_brace_y_bays(self) -> tuple[int, ...]:
        return (
            self._checked_rows(self.brace_y_table)
            if hasattr(self, "brace_y_table")
            else ()
        )

    def _selected_brace_storeys(self) -> tuple[int, ...]:
        return (
            self._checked_rows(self.brace_storey_table, offset=1)
            if hasattr(self, "brace_storey_table")
            else ()
        )

    def _brace_panel_pattern_overrides(
        self,
    ) -> tuple[tuple[str, int, int, int, str], ...]:
        if not hasattr(self, "brace_panel_table"):
            return ()
        result: list[tuple[str, int, int, int, str]] = []
        for row in range(self.brace_panel_table.rowCount()):
            combo = self.brace_panel_table.cellWidget(row, 4)
            if not isinstance(combo, QComboBox):
                continue
            pattern = str(combo.currentData() or "")
            if not pattern:
                continue
            axis_item = self.brace_panel_table.item(row, 0)
            plane_item = self.brace_panel_table.item(row, 1)
            bay_item = self.brace_panel_table.item(row, 2)
            storey_item = self.brace_panel_table.item(row, 3)
            if None in (axis_item, plane_item, bay_item, storey_item):
                continue
            result.append(
                (
                    str(axis_item.data(Qt.UserRole)),
                    int(plane_item.data(Qt.UserRole)),
                    int(bay_item.data(Qt.UserRole)),
                    int(storey_item.data(Qt.UserRole)),
                    pattern,
                )
            )
        return tuple(result)

    def _brace_candidate_panel_keys(
        self,
    ) -> tuple[tuple[str, int, int, int], ...]:
        if not hasattr(self, "brace_plane_mode"):
            return ()
        mode = str(self.brace_plane_mode.currentData() or "X")
        storeys = self._selected_brace_storeys()
        result: list[tuple[str, int, int, int]] = []

        if mode in {"X", "Both"}:
            ny = 0 if self.dimension.currentData() == "2D" else int(self.y_bays.value())
            scope = str(self.brace_y_plane_scope.currentData() or "All")
            if self.dimension.currentData() == "2D":
                planes = (0,)
            elif scope == "YMin":
                planes = (0,)
            elif scope == "YMax":
                planes = (ny,)
            elif scope == "Exterior":
                planes = (0,) if ny == 0 else (0, ny)
            else:
                planes = tuple(range(ny + 1))
            for storey in storeys:
                for plane in planes:
                    for bay in self._selected_brace_x_bays():
                        result.append(("X", plane, bay, storey))

        if (
            self.dimension.currentData() == "3D"
            and mode in {"Y", "Both"}
        ):
            nx = int(self.x_bays.value())
            scope = str(self.brace_x_plane_scope.currentData() or "All")
            if scope == "XMin":
                planes = (0,)
            elif scope == "XMax":
                planes = (nx,)
            elif scope == "Exterior":
                planes = (0,) if nx == 0 else (0, nx)
            else:
                planes = tuple(range(nx + 1))
            for storey in storeys:
                for plane in planes:
                    for bay in self._selected_brace_y_bays():
                        result.append(("Y", plane, bay, storey))

        return tuple(result)

    def _refresh_brace_panel_table(self) -> None:
        if not hasattr(self, "brace_panel_table"):
            return
        old = {
            (axis, plane, bay, storey): pattern
            for axis, plane, bay, storey, pattern
            in self._brace_panel_pattern_overrides()
        }
        keys = self._brace_candidate_panel_keys()
        table = self.brace_panel_table
        table.setRowCount(len(keys))
        labels = (
            ("Default", ""),
            ("Off", "None"),
            ("Diagonal /", "DiagonalForward"),
            ("Diagonal \\", "DiagonalBackward"),
            ("X", "X"),
            ("Chevron upper", "VUpper"),
            ("Chevron lower", "VLower"),
            ("K left", "KLeft"),
            ("K right", "KRight"),
        )

        for row, (axis, plane, bay, storey) in enumerate(keys):
            plane_item = QTableWidgetItem(
                "X-Z" if axis == "X" else "Y-Z"
            )
            plane_item.setData(Qt.UserRole, axis)
            plane_item.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 0, plane_item)

            grid_value = plane + 1
            grid_item = QTableWidgetItem(
                ("Y" if axis == "X" else "X") + str(grid_value)
            )
            grid_item.setData(Qt.UserRole, plane)
            grid_item.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 1, grid_item)

            bay_item = QTableWidgetItem(
                ("X" if axis == "X" else "Y") + str(bay + 1)
            )
            bay_item.setData(Qt.UserRole, bay)
            bay_item.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 2, bay_item)

            storey_item = QTableWidgetItem(f"S{storey}")
            storey_item.setData(Qt.UserRole, storey)
            storey_item.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 3, storey_item)

            combo = QComboBox()
            for label, value in labels:
                combo.addItem(label, value)
            previous = old.get((axis, plane, bay, storey), "")
            index = combo.findData(previous)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.currentIndexChanged.connect(
                self._brace_control_changed
            )
            table.setCellWidget(row, 4, combo)

    def _refresh_brace_scope_tables(self, *_args) -> None:
        if not hasattr(self, "brace_x_table"):
            return
        old_x = set(self._selected_brace_x_bays())
        old_y = set(self._selected_brace_y_bays())
        old_storeys = set(self._selected_brace_storeys())
        had_x = self.brace_x_table.rowCount() > 0
        had_y = self.brace_y_table.rowCount() > 0
        had_storeys = self.brace_storey_table.rowCount() > 0

        def rebuild(
            table: QTableWidget,
            count: int,
            prefix: str,
            selected: set[int],
            had_rows: bool,
            offset: int = 0,
        ) -> None:
            table.blockSignals(True)
            table.setRowCount(count)
            for row in range(count):
                value = row + offset
                label = QTableWidgetItem(f"{prefix}{value + (0 if offset else 1)}")
                label.setFlags(Qt.ItemIsEnabled)
                table.setItem(row, 0, label)
                check = QTableWidgetItem("Enabled")
                check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                check.setCheckState(
                    Qt.Checked
                    if (not had_rows or value in selected)
                    else Qt.Unchecked
                )
                table.setItem(row, 1, check)
            table.blockSignals(False)

        rebuild(
            self.brace_x_table,
            int(self.x_bays.value()),
            "X",
            old_x,
            had_x,
        )
        rebuild(
            self.brace_y_table,
            int(self.y_bays.value()),
            "Y",
            old_y,
            had_y,
        )
        rebuild(
            self.brace_storey_table,
            int(self.storeys.value()),
            "S",
            old_storeys,
            had_storeys,
            offset=1,
        )
        self._refresh_brace_panel_table()
        self._sync_brace_controls()
        self._update_brace_summary()
        self._update_preview()

    def _brace_geometry_changed(self, *_args) -> None:
        self._refresh_brace_scope_tables()

    def _brace_scope_changed(self, *_args) -> None:
        self._refresh_brace_panel_table()
        self._brace_control_changed()

    def _brace_preset_changed(self, *_args) -> None:
        if not hasattr(self, "brace_response_preset"):
            return
        preset = self.brace_response_preset.currentData()
        if preset in {"NonlinearReady", "BRBReady"}:
            index = self.brace_element_type.findData("corotTruss")
            if index >= 0:
                self.brace_element_type.setCurrentIndex(index)
        self._brace_control_changed()

    def _brace_control_changed(self, *_args) -> None:
        if (
            hasattr(self, "brace_pattern")
            and self.brace_pattern.currentData() == "VLower"
            and hasattr(self, "brace_storey_table")
            and self.brace_storey_table.rowCount() > 0
        ):
            first = self.brace_storey_table.item(0, 1)
            if first is not None and first.checkState() == Qt.Checked:
                self.brace_storey_table.blockSignals(True)
                first.setCheckState(Qt.Unchecked)
                self.brace_storey_table.blockSignals(False)
                self._refresh_brace_panel_table()
        if hasattr(self, "brace_panel_table"):
            # Plane/pattern/scope changes can alter candidate rows.
            expected = len(self._brace_candidate_panel_keys())
            if self.brace_panel_table.rowCount() != expected:
                self._refresh_brace_panel_table()
        self._sync_brace_controls()
        self._update_brace_summary()
        self._update_preview()

    def _sync_brace_controls(self, *_args) -> None:
        if not hasattr(self, "brace_mode"):
            return
        active = self.brace_mode.currentData() == "Truss"
        is_3d = self.dimension.currentData() == "3D"
        plane_mode = str(self.brace_plane_mode.currentData() or "X")

        self.brace_model_group.setEnabled(True)
        for widget in (
            self.brace_plane_mode,
            self.brace_pattern,
            self.brace_response_preset,
            self.brace_element_type,
            self.brace_material,
            self.brace_area,
            self.brace_mass_per_length,
            self.brace_do_rayleigh,
        ):
            widget.setEnabled(active)
        self.brace_plane_mode.setEnabled(active and is_3d)
        if not is_3d and self.brace_plane_mode.currentData() != "X":
            self.brace_plane_mode.blockSignals(True)
            self.brace_plane_mode.setCurrentIndex(
                self.brace_plane_mode.findData("X")
            )
            self.brace_plane_mode.blockSignals(False)
            plane_mode = "X"

        self.brace_scope_group.setEnabled(active)
        self.brace_matrix_group.setEnabled(active)
        self.brace_x_table.setEnabled(active and plane_mode in {"X", "Both"})
        self.brace_y_table.setEnabled(
            active and is_3d and plane_mode in {"Y", "Both"}
        )
        self.brace_y_plane_scope.setEnabled(
            active and is_3d and plane_mode in {"X", "Both"}
        )
        self.brace_x_plane_scope.setEnabled(
            active and is_3d and plane_mode in {"Y", "Both"}
        )

    def _brace_validation_error(self) -> str:
        try:
            spec = self.spec()
            validate_frame_grid_spec(spec)
        except (TypeError, ValueError) as exc:
            return str(exc)

        if spec.brace_mode != "Truss":
            return ""
        if spec.brace_plane_mode in {"X", "Both"} and not self._selected_brace_x_bays():
            return "Select at least one X bay for X-Z bracing."
        if (
            spec.brace_plane_mode in {"Y", "Both"}
            and not spec.planar_2d
            and not self._selected_brace_y_bays()
        ):
            return "Select at least one Y bay for Y-Z bracing."
        if not self._selected_brace_storeys():
            return "Select at least one storey for bracing."

        tag = self.brace_material.currentData()
        if tag is None:
            return "Select a uniaxial material for the brace."
        material = self.project.materials.get(int(tag))
        if material is None:
            return f"Brace material {int(tag)} no longer exists."

        if spec.brace_response_preset in {"NonlinearReady", "BRBReady"}:
            if str(material.material_type) == "Elastic":
                label = (
                    "BRB-ready"
                    if spec.brace_response_preset == "BRBReady"
                    else "Nonlinear-ready"
                )
                return (
                    f"{label} workflow requires a calibrated nonlinear "
                    "uniaxial material; a purely Elastic material is not "
                    "treated as nonlinear brace behavior."
                )
        return ""

    def _update_brace_summary(self, *_args) -> None:
        if not hasattr(self, "brace_summary"):
            return
        self._sync_brace_controls()
        try:
            spec = self.spec()
            panels = frame_brace_panel_count(spec)
            elements = frame_brace_element_count(spec)
            actual_panels = frame_brace_panels(spec)
            error = self._brace_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            panels = 0
            elements = 0
            actual_panels = ()
            error = str(exc)

        if spec.brace_mode == "Truss":
            xz_count = sum(1 for panel in actual_panels if panel[0] == "X")
            yz_count = sum(1 for panel in actual_panels if panel[0] == "Y")
            override_count = len(spec.brace_panel_patterns)
            self.brace_summary.setText(
                "<b>Bracing summary</b><br>"
                f"Planes: {spec.brace_plane_mode} · panels: {panels} "
                f"(X-Z {xz_count}, Y-Z {yz_count}) · "
                f"brace elements: {elements}<br>"
                f"Default pattern: {spec.brace_pattern} · "
                f"panel overrides: {override_count}<br>"
                f"{spec.brace_element_type} · area={spec.brace_area:g} "
                f"{self.units.length}² · material "
                f"{spec.brace_material_tag} · workflow "
                f"{spec.brace_response_preset}"
            )
        else:
            self.brace_summary.setText(
                "<b>Bracing summary</b><br>"
                "No explicit brace elements will be generated."
            )

        finish = self.button(QWizard.FinishButton)
        if error:
            self.brace_validation_status.setText(
                "<b>Bracing definition needs attention</b><br>" + error
            )
            if finish is not None and self.currentId() == self.bracing_page_id:
                finish.setEnabled(False)
        else:
            self.brace_validation_status.setText(
                "<b>Bracing definition ready</b><br>"
                "X-Z/Y-Z plane scope, per-panel patterns and axial brace "
                "material are consistent with the frame."
            )
            if finish is not None and self.currentId() == self.bracing_page_id:
                finish.setEnabled(True)

    def _build_loads_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Loads & Gravity")
        page.setSubTitle(
            "Create one static Plain load pattern after final frame topology "
            "is generated. Add member self-weight, direct beam UDL and/or "
            "one-way floor area gravity distributed by tributary width."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-loads-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.load_mode = QComboBox()
        self.load_mode.addItem("None · no automatic loads", "None")
        self.load_mode.addItem(
            "Static gravity / beam load pattern",
            "Static",
        )

        mode_group = QGroupBox("Automatic load pattern")
        mode_form = QFormLayout(mode_group)
        mode_form.addRow("Load generation:", self.load_mode)
        layout.addWidget(mode_group)

        self.load_self_weight = QCheckBox(
            "Generate automatic self-weight on frame columns and beams"
        )
        self.load_self_weight_density = self._nonnegative(0.0)
        self.load_self_weight_density.setDecimals(3)

        self_weight_group = QGroupBox("Member self-weight")
        self_weight_form = QFormLayout(self_weight_group)
        self_weight_form.addRow("", self.load_self_weight)
        self_weight_form.addRow(
            (
                "Density override "
                f"[{self.units.mass_label}/{self.units.length}³]:"
            ),
            self.load_self_weight_density,
        )
        self_weight_hint = QLabel(
            "Density override 0 uses the material density linked to each "
            "Elastic section. Automatic self-weight currently applies only "
            "to Elastic frame sections with valid geometric transformations."
        )
        self_weight_hint.setWordWrap(True)
        self_weight_form.addRow(self_weight_hint)
        layout.addWidget(self_weight_group)
        self.load_self_weight_group = self_weight_group

        self.load_beam_udl = QCheckBox(
            "Generate uniform distributed load on selected beam families"
        )
        self.load_beam_udl_coordinate = QComboBox()
        self.load_beam_udl_coordinate.addItem("Global X/Y/Z", "global")
        self.load_beam_udl_coordinate.addItem("Beam local x/y/z", "local")
        self.load_beam_scope = QComboBox()
        self.load_beam_scope.addItem("X-direction beams", "X")
        self.load_beam_scope.addItem("Y-direction beams", "Y")
        self.load_beam_scope.addItem("Both X and Y beams", "Both")
        self.load_beam_scope.setCurrentIndex(
            self.load_beam_scope.findData("Both")
        )

        self.load_udl_x = self._coordinate(0.0)
        self.load_udl_y = self._coordinate(0.0)
        self.load_udl_z = self._coordinate(-10.0)

        udl_group = QGroupBox("Beam uniform distributed load")
        udl_form = QFormLayout(udl_group)
        udl_form.addRow("", self.load_beam_udl)
        udl_form.addRow("Coordinate system:", self.load_beam_udl_coordinate)
        udl_form.addRow("Beam family:", self.load_beam_scope)
        udl_form.addRow(
            f"Component X/x [{self.units.force}/{self.units.length}]:",
            self.load_udl_x,
        )
        udl_form.addRow(
            f"Component Y/y [{self.units.force}/{self.units.length}]:",
            self.load_udl_y,
        )
        udl_form.addRow(
            f"Component Z/z [{self.units.force}/{self.units.length}]:",
            self.load_udl_z,
        )
        udl_hint = QLabel(
            "For Global coordinates, the vector is resolved into each beam's "
            "local axes at export. For Local coordinates, x/y/z are the "
            "OpenSees beam local axes."
        )
        udl_hint.setWordWrap(True)
        udl_form.addRow(udl_hint)
        layout.addWidget(udl_group)
        self.load_udl_group = udl_group

        self.load_floor_area = QCheckBox(
            "Distribute a floor area gravity load to one beam direction"
        )
        self.load_floor_area_pressure = self._nonnegative(0.0)
        self.load_floor_area_pressure.setDecimals(4)
        self.load_floor_area_direction = QComboBox()
        self.load_floor_area_direction.addItem(
            "X-direction beams · tributary width in Y",
            "X",
        )
        self.load_floor_area_direction.addItem(
            "Y-direction beams · tributary width in X",
            "Y",
        )

        floor_area_group = QGroupBox("Floor area gravity · tributary method")
        floor_area_form = QFormLayout(floor_area_group)
        floor_area_form.addRow("", self.load_floor_area)
        floor_area_form.addRow(
            (
                "Downward pressure "
                f"[{self.units.force}/{self.units.length}²]:"
            ),
            self.load_floor_area_pressure,
        )
        floor_area_form.addRow(
            "Load carried by:",
            self.load_floor_area_direction,
        )
        floor_area_hint = QLabel(
            "One-way distribution for 3D frames. Edge beams receive half the "
            "adjacent bay width; interior beams receive half of each adjacent "
            "bay. The resulting global-Z line load is applied to the final "
            "beam segments, including Chevron-split members."
        )
        floor_area_hint.setWordWrap(True)
        floor_area_form.addRow(floor_area_hint)
        layout.addWidget(floor_area_group)
        self.load_floor_area_group = floor_area_group

        self.load_storey_table = QTableWidget(0, 2)
        self.load_storey_table.setHorizontalHeaderLabels(
            ["Storey", "Beam / floor load"]
        )
        self.load_storey_table.horizontalHeader().setStretchLastSection(True)
        self.load_storey_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.load_storey_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.load_storey_table.setMinimumHeight(170)
        self.load_storey_table.setMaximumHeight(260)

        scope_group = QGroupBox("Beam / floor load storey scope")
        scope_layout = QVBoxLayout(scope_group)
        scope_layout.addWidget(self.load_storey_table)
        scope_hint = QLabel(
            "Self-weight always follows all generated frame columns/beams. "
            "The storey selection applies to direct beam UDL and floor area "
            "gravity distribution."
        )
        scope_hint.setWordWrap(True)
        scope_layout.addWidget(scope_hint)
        layout.addWidget(scope_group)
        self.load_scope_group = scope_group

        note = QLabel(
            "Loads are generated after shell-mesh refinement, Chevron/K member "
            "splitting, joint processing and foundation generation. Therefore "
            "the load objects target the final FE member tags rather than the "
            "pre-Wizard topology."
        )
        note.setWordWrap(True)
        note.setStyleSheet("padding:8px;")
        layout.addWidget(note)

        self.load_summary = QLabel()
        self.load_summary.setWordWrap(True)
        self.load_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.load_summary)

        self.load_validation_status = QLabel()
        self.load_validation_status.setWordWrap(True)
        self.load_validation_status.setObjectName(
            "frame-wizard-load-validation-status"
        )
        self.load_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.load_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.loads_scroll = scroll
        self.loads_page_id = self.addPage(page)

        self._refresh_load_storeys()

        self.load_mode.currentIndexChanged.connect(
            self._load_control_changed
        )
        self.load_self_weight.toggled.connect(self._load_control_changed)
        self.load_beam_udl.toggled.connect(self._load_control_changed)
        self.load_floor_area.toggled.connect(self._load_control_changed)
        for combo in (
            self.load_beam_udl_coordinate,
            self.load_beam_scope,
            self.load_floor_area_direction,
        ):
            combo.currentIndexChanged.connect(self._load_control_changed)
        for spin in (
            self.load_self_weight_density,
            self.load_udl_x,
            self.load_udl_y,
            self.load_udl_z,
            self.load_floor_area_pressure,
        ):
            spin.valueChanged.connect(self._load_control_changed)
        self.load_storey_table.itemChanged.connect(
            self._load_control_changed
        )

        self.storeys.valueChanged.connect(self._refresh_load_storeys)
        self.dimension.currentIndexChanged.connect(
            self._load_geometry_changed
        )
        self.create_columns.toggled.connect(self._load_control_changed)
        self.create_beams_x.toggled.connect(self._load_control_changed)
        self.create_beams_y.toggled.connect(self._load_control_changed)
        self.joint_model.currentIndexChanged.connect(
            self._load_control_changed
        )
        self.column_section.currentIndexChanged.connect(
            self._load_control_changed
        )
        self.beam_section.currentIndexChanged.connect(
            self._load_control_changed
        )

    def _selected_load_storeys(self) -> tuple[int, ...]:
        if not hasattr(self, "load_storey_table"):
            return ()
        values: list[int] = []
        for row in range(self.load_storey_table.rowCount()):
            item = self.load_storey_table.item(row, 1)
            if item is not None and item.checkState() == Qt.Checked:
                values.append(row + 1)
        return tuple(values)

    def _refresh_load_storeys(self, *_args) -> None:
        if not hasattr(self, "load_storey_table"):
            return
        selected = set(self._selected_load_storeys())
        had_rows = self.load_storey_table.rowCount() > 0
        table = self.load_storey_table
        table.blockSignals(True)
        table.setRowCount(int(self.storeys.value()))
        for row in range(table.rowCount()):
            storey = row + 1
            label = QTableWidgetItem(f"S{storey}")
            label.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 0, label)
            check = QTableWidgetItem("Enabled")
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(
                Qt.Checked
                if (not had_rows or storey in selected)
                else Qt.Unchecked
            )
            table.setItem(row, 1, check)
        table.blockSignals(False)
        self._sync_load_controls()
        self._update_load_summary()
        self._update_preview()

    def _load_geometry_changed(self, *_args) -> None:
        if (
            hasattr(self, "load_floor_area")
            and self.dimension.currentData() == "2D"
            and self.load_floor_area.isChecked()
        ):
            self.load_floor_area.blockSignals(True)
            self.load_floor_area.setChecked(False)
            self.load_floor_area.blockSignals(False)
        if (
            hasattr(self, "load_beam_scope")
            and self.dimension.currentData() == "2D"
            and self.load_beam_scope.currentData() != "X"
        ):
            self.load_beam_scope.blockSignals(True)
            self.load_beam_scope.setCurrentIndex(
                self.load_beam_scope.findData("X")
            )
            self.load_beam_scope.blockSignals(False)
        self._load_control_changed()

    def _load_control_changed(self, *_args) -> None:
        self._sync_load_controls()
        self._update_load_summary()
        if hasattr(self, "mass_source_mode"):
            self._sync_mass_controls()
            self._update_mass_summary()
        self._update_preview()

    def _sync_load_controls(self, *_args) -> None:
        if not hasattr(self, "load_mode"):
            return
        active = self.load_mode.currentData() == "Static"
        self.load_self_weight_group.setEnabled(active)
        self.load_udl_group.setEnabled(active)
        self.load_scope_group.setEnabled(
            active
            and (
                self.load_beam_udl.isChecked()
                or self.load_floor_area.isChecked()
            )
        )
        floor_area_available = (
            active and self.dimension.currentData() == "3D"
        )
        self.load_floor_area_group.setEnabled(floor_area_available)
        self.load_floor_area_pressure.setEnabled(
            floor_area_available and self.load_floor_area.isChecked()
        )
        self.load_floor_area_direction.setEnabled(
            floor_area_available and self.load_floor_area.isChecked()
        )
        self.load_self_weight_density.setEnabled(
            active and self.load_self_weight.isChecked()
        )

        udl_active = active and self.load_beam_udl.isChecked()
        for widget in (
            self.load_beam_udl_coordinate,
            self.load_beam_scope,
            self.load_udl_x,
            self.load_udl_y,
            self.load_udl_z,
        ):
            widget.setEnabled(udl_active)
        self.load_beam_scope.setEnabled(
            udl_active and self.dimension.currentData() == "3D"
        )
        if (
            self.dimension.currentData() == "2D"
            and self.load_beam_scope.currentData() != "X"
        ):
            self.load_beam_scope.blockSignals(True)
            self.load_beam_scope.setCurrentIndex(
                self.load_beam_scope.findData("X")
            )
            self.load_beam_scope.blockSignals(False)

    def _self_weight_section_error(
        self,
        section_tag: int | None,
        label: str,
        density_override: float,
    ) -> str:
        if section_tag is None:
            return f"{label} section is not assigned."
        section = self.project.sections.get(int(section_tag))
        if section is None:
            return f"{label} section {section_tag} does not exist."
        if section.section_type != "Elastic":
            return (
                f"Automatic self-weight requires Elastic {label.lower()} "
                f"section; {section.name} is {section.section_type}."
            )
        if density_override > 0.0:
            return ""
        if section.material_tag is None:
            return (
                f"{label} section {section.tag} has no linked material "
                "density. Enter a density override."
            )
        material = self.project.materials.get(int(section.material_tag))
        if material is None or float(material.density) <= 0.0:
            return (
                f"{label} section {section.tag} needs positive linked material "
                "density or a density override."
            )
        return ""

    def _load_validation_error(self) -> str:
        try:
            spec = self.spec()
            validate_frame_grid_spec(spec)
        except (TypeError, ValueError) as exc:
            return str(exc)

        if spec.load_mode != "Static":
            return ""
        if (
            spec.load_beam_udl or spec.load_floor_area
        ) and not self._selected_load_storeys():
            return "Select at least one storey for beam / floor load."

        if spec.load_self_weight:
            density = float(spec.load_self_weight_density)
            if spec.create_columns:
                error = self._self_weight_section_error(
                    spec.column_section_tag,
                    "Column",
                    density,
                )
                if error:
                    return error
            if spec.create_beams_x or spec.create_beams_y:
                error = self._self_weight_section_error(
                    spec.beam_section_tag,
                    "Beam",
                    density,
                )
                if error:
                    return error
        return ""

    def _update_load_summary(self, *_args) -> None:
        if not hasattr(self, "load_summary"):
            return
        self._sync_load_controls()
        try:
            spec = self.spec()
            error = self._load_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            error = str(exc)

        if spec.load_mode == "Static":
            parts: list[str] = []
            if spec.load_self_weight:
                density_text = (
                    f"override {spec.load_self_weight_density:g}"
                    if spec.load_self_weight_density > 0.0
                    else "linked material density"
                )
                parts.append("Self-weight · " + density_text)
            if spec.load_beam_udl:
                vector = spec.load_beam_udl_vector
                parts.append(
                    "Beam UDL "
                    f"({vector[0]:g}, {vector[1]:g}, {vector[2]:g}) "
                    f"{spec.load_beam_udl_coordinate_system} · "
                    f"{spec.load_beam_scope} beams · storeys "
                    + ", ".join(map(str, frame_load_storeys(spec)))
                )
            if spec.load_floor_area:
                parts.append(
                    "Floor area gravity "
                    f"{spec.load_floor_area_pressure:g} "
                    f"{self.units.force}/{self.units.length}² · "
                    f"to {spec.load_floor_area_direction} beams · storeys "
                    + ", ".join(map(str, frame_load_storeys(spec)))
                )
            self.load_summary.setText(
                "<b>Automatic load summary</b><br>"
                "One Linear time series + one Plain pattern<br>"
                + "<br>".join(parts)
            )
        else:
            self.load_summary.setText(
                "<b>Automatic load summary</b><br>"
                "No automatic load pattern will be generated."
            )

        finish = self.button(QWizard.FinishButton)
        if error:
            self.load_validation_status.setText(
                "<b>Load definition needs attention</b><br>" + error
            )
            if finish is not None and self.currentId() == self.loads_page_id:
                finish.setEnabled(False)
        else:
            self.load_validation_status.setText(
                "<b>Load definition ready</b><br>"
                "Automatic static loads are consistent with the final frame "
                "topology."
            )
            if finish is not None and self.currentId() == self.loads_page_id:
                finish.setEnabled(True)


    def _build_mass_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Mass & Dynamic")
        page.setSubTitle(
            "Create a reproducible seismic Mass Source from structural self "
            "mass and/or the gravity load pattern. This first-stage dynamic "
            "setup prepares the model for modal and earthquake analyses."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-mass-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.mass_source_mode = QComboBox()
        self.mass_source_mode.addItem(
            "None · keep existing element / nodal mass only",
            "None",
        )
        self.mass_source_mode.addItem(
            "Create and apply seismic Mass Source",
            "Source",
        )

        mode_group = QGroupBox("Automatic seismic mass")
        mode_form = QFormLayout(mode_group)
        mode_form.addRow("Mass generation:", self.mass_source_mode)
        layout.addWidget(mode_group)

        self.mass_include_self = QCheckBox(
            "Include structural self mass from section/material density"
        )
        self.mass_include_self.setChecked(True)
        self.mass_include_static = QCheckBox(
            "Convert the Frame Wizard static gravity pattern to mass"
        )
        self.mass_include_static.setChecked(True)
        self.mass_static_factor = self._nonnegative(1.0)
        self.mass_static_factor.setDecimals(4)

        source_group = QGroupBox("Mass source components")
        source_form = QFormLayout(source_group)
        source_form.addRow("", self.mass_include_self)
        source_form.addRow("", self.mass_include_static)
        source_form.addRow(
            "Static-pattern participation factor:",
            self.mass_static_factor,
        )
        source_hint = QLabel(
            "SelfWeight element loads are not counted twice when structural "
            "self mass is enabled. Direct beam UDL and floor-area gravity in "
            "the generated static pattern are converted using |W|/g."
        )
        source_hint.setWordWrap(True)
        source_form.addRow(source_hint)
        layout.addWidget(source_group)
        self.mass_source_group = source_group

        self.mass_gravity_axis = QComboBox()
        self.mass_gravity_axis.addItem("Global X", 1)
        self.mass_gravity_axis.addItem("Global Y", 2)
        self.mass_gravity_axis.addItem("Global Z · typical gravity", 3)
        self.mass_gravity_axis.setCurrentIndex(
            self.mass_gravity_axis.findData(3)
        )

        self.mass_direction_x = QCheckBox("UX")
        self.mass_direction_y = QCheckBox("UY")
        self.mass_direction_z = QCheckBox("UZ")
        self.mass_direction_x.setChecked(True)
        self.mass_direction_y.setChecked(True)

        direction_host = QWidget()
        direction_layout = QHBoxLayout(direction_host)
        direction_layout.setContentsMargins(0, 0, 0, 0)
        direction_layout.addWidget(self.mass_direction_x)
        direction_layout.addWidget(self.mass_direction_y)
        direction_layout.addWidget(self.mass_direction_z)
        direction_layout.addStretch(1)

        direction_group = QGroupBox("Mass directions")
        direction_form = QFormLayout(direction_group)
        direction_form.addRow("Gravity force axis:", self.mass_gravity_axis)
        direction_form.addRow("Assign mass to:", direction_host)
        direction_hint = QLabel(
            "For a 3D building, UX + UY is the normal lateral seismic "
            "choice. For a planar X-Z frame FEWIZ automatically keeps UX "
            "only when switching dimensions."
        )
        direction_hint.setWordWrap(True)
        direction_form.addRow(direction_hint)
        layout.addWidget(direction_group)
        self.mass_direction_group = direction_group

        self.modal_mode = QComboBox()
        self.modal_mode.addItem(
            "None · mass definition only",
            "None",
        )
        self.modal_mode.addItem(
            "Create Modal analysis + mode-shape results",
            "Modal",
        )
        self.modal_num_modes = self._spin(6, 1, 100)
        self.modal_eigen_solver = QComboBox()
        self.modal_eigen_solver.addItem(
            "Band ARPACK · recommended",
            "-genBandArpack",
        )
        self.modal_eigen_solver.addItem(
            "Full General LAPACK",
            "-fullGenLapack",
        )
        self.modal_eigen_solver.addItem(
            "Symmetric Band LAPACK",
            "-symmBandLapack",
        )

        modal_group = QGroupBox("Modal analysis preset")
        modal_form = QFormLayout(modal_group)
        modal_form.addRow("After mass generation:", self.modal_mode)
        modal_form.addRow("Number of modes:", self.modal_num_modes)
        modal_form.addRow("Eigen solver:", self.modal_eigen_solver)
        modal_hint = QLabel(
            "Creates one Modal Analysis object plus Mode Motion and one "
            "Mode Shape result request for each requested mode. The analysis "
            "uses the same FEWIZ Analysis Template backend as manual setup."
        )
        modal_hint.setWordWrap(True)
        modal_form.addRow(modal_hint)
        layout.addWidget(modal_group)
        self.modal_group = modal_group

        compatibility_note = QLabel(
            "Safety rule: automatic Mass Source replaces selected nodal mass. "
            "Therefore FEWIZ blocks it when a nonzero rigid-diaphragm floor "
            "mass or additional slab nodal mass is already defined. Use the "
            "gravity-pattern route instead to avoid silent double/overwritten "
            "mass."
        )
        compatibility_note.setWordWrap(True)
        compatibility_note.setStyleSheet("padding:8px;")
        layout.addWidget(compatibility_note)

        self.mass_summary = QLabel()
        self.mass_summary.setWordWrap(True)
        self.mass_summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.mass_summary)

        self.mass_validation_status = QLabel()
        self.mass_validation_status.setWordWrap(True)
        self.mass_validation_status.setObjectName(
            "frame-wizard-mass-validation-status"
        )
        self.mass_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.mass_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.mass_scroll = scroll
        self.mass_page_id = self.addPage(page)

        self.mass_source_mode.currentIndexChanged.connect(
            self._mass_control_changed
        )
        self.mass_include_self.toggled.connect(self._mass_control_changed)
        self.mass_include_static.toggled.connect(self._mass_control_changed)
        self.mass_static_factor.valueChanged.connect(
            self._mass_control_changed
        )
        self.mass_gravity_axis.currentIndexChanged.connect(
            self._mass_control_changed
        )
        self.modal_mode.currentIndexChanged.connect(
            self._mass_control_changed
        )
        self.modal_num_modes.valueChanged.connect(
            self._mass_control_changed
        )
        self.modal_eigen_solver.currentIndexChanged.connect(
            self._mass_control_changed
        )
        for check in (
            self.mass_direction_x,
            self.mass_direction_y,
            self.mass_direction_z,
        ):
            check.toggled.connect(self._mass_control_changed)

    def _selected_mass_directions(self) -> tuple[int, ...]:
        if not hasattr(self, "mass_direction_x"):
            return ()
        values = []
        for dof, check in (
            (1, self.mass_direction_x),
            (2, self.mass_direction_y),
            (3, self.mass_direction_z),
        ):
            if check.isChecked():
                values.append(dof)
        return tuple(values)

    def _mass_control_changed(self, *_args) -> None:
        self._sync_mass_controls()
        self._update_mass_summary()

    def _sync_mass_controls(self, *_args) -> None:
        if not hasattr(self, "mass_source_mode"):
            return
        active = self.mass_source_mode.currentData() == "Source"
        self.mass_source_group.setEnabled(active)
        self.mass_direction_group.setEnabled(active)
        self.mass_static_factor.setEnabled(
            active and self.mass_include_static.isChecked()
        )

        modal_active = self.modal_mode.currentData() == "Modal"
        self.modal_num_modes.setEnabled(modal_active)
        self.modal_eigen_solver.setEnabled(modal_active)

        if self.dimension.currentData() == "2D":
            self.mass_direction_y.blockSignals(True)
            self.mass_direction_z.blockSignals(True)
            self.mass_direction_y.setChecked(False)
            self.mass_direction_z.setChecked(False)
            self.mass_direction_y.blockSignals(False)
            self.mass_direction_z.blockSignals(False)
            if active and not self.mass_direction_x.isChecked():
                self.mass_direction_x.blockSignals(True)
                self.mass_direction_x.setChecked(True)
                self.mass_direction_x.blockSignals(False)

    def _mass_validation_error(self) -> str:
        try:
            spec = self.spec()
            validate_frame_grid_spec(spec)
        except (TypeError, ValueError) as exc:
            return str(exc)
        return ""

    def _update_mass_summary(self, *_args) -> None:
        if not hasattr(self, "mass_summary"):
            return
        self._sync_mass_controls()
        try:
            spec = self.spec()
            error = self._mass_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            error = str(exc)

        if spec.mass_source_mode == "Source":
            components = []
            if spec.mass_include_self:
                components.append("structural self mass")
            if spec.mass_include_static_loads:
                components.append(
                    "static gravity pattern "
                    f"× {spec.mass_static_load_factor:g}"
                )
            direction_names = {
                1: "UX",
                2: "UY",
                3: "UZ",
            }
            mass_text = (
                "<b>Seismic mass summary</b><br>"
                "Create + apply one Mass Source<br>"
                "Components: "
                + " + ".join(components)
                + "<br>Gravity axis: "
                + direction_names.get(spec.mass_gravity_axis, "?")
                + " · assigned directions: "
                + ", ".join(
                    direction_names[value]
                    for value in spec.mass_directions
                )
            )
        else:
            mass_text = (
                "<b>Seismic mass summary</b><br>"
                "No automatic Mass Source will be created. Existing element "
                "mass and nodal mass are left unchanged."
            )

        if spec.modal_mode == "Modal":
            mass_text += (
                "<br><br><b>Modal preset</b><br>"
                f"{spec.modal_num_modes} mode(s) · "
                f"{spec.modal_eigen_solver}<br>"
                "Creates Modal analysis + Mode Motion + Mode Shape requests."
            )
        else:
            mass_text += (
                "<br><br><b>Modal preset</b><br>"
                "No automatic modal analysis will be created."
            )
        self.mass_summary.setText(mass_text)

        finish = self.button(QWizard.FinishButton)
        if error:
            self.mass_validation_status.setText(
                "<b>Mass definition needs attention</b><br>" + error
            )
            if finish is not None and self.currentId() == self.mass_page_id:
                finish.setEnabled(False)
        else:
            self.mass_validation_status.setText(
                "<b>Mass definition ready</b><br>"
                "Mass Source settings are consistent with the current frame, "
                "floor and gravity-load definitions."
            )
            if finish is not None and self.currentId() == self.mass_page_id:
                finish.setEnabled(True)

    def _build_review_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Preview & Create")
        page.setSubTitle(
            "Review the complete FE model definition before FEWIZ replaces "
            "the active FE domain and generates the frame."
        )

        scroll = QScrollArea()
        scroll.setObjectName("frame-wizard-review-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.review_preview = FramePreview()
        self.review_preview.setObjectName("frame-wizard-final-preview")
        self.review_preview.setMinimumHeight(330)
        layout.addWidget(self.review_preview)

        self.review_geometry = QLabel()
        self.review_geometry.setWordWrap(True)
        geometry_group = QGroupBox("Geometry & topology")
        geometry_layout = QVBoxLayout(geometry_group)
        geometry_layout.addWidget(self.review_geometry)
        layout.addWidget(geometry_group)

        self.review_modeling = QLabel()
        self.review_modeling.setWordWrap(True)
        modeling_group = QGroupBox("Structural modeling")
        modeling_layout = QVBoxLayout(modeling_group)
        modeling_layout.addWidget(self.review_modeling)
        layout.addWidget(modeling_group)

        self.review_loading = QLabel()
        self.review_loading.setWordWrap(True)
        loading_group = QGroupBox("Loads, mass & analysis")
        loading_layout = QVBoxLayout(loading_group)
        loading_layout.addWidget(self.review_loading)
        layout.addWidget(loading_group)

        self.review_build = QLabel()
        self.review_build.setWordWrap(True)
        build_group = QGroupBox("Generation dry-run")
        build_layout = QVBoxLayout(build_group)
        build_layout.addWidget(self.review_build)
        layout.addWidget(build_group)

        self.review_impact = QLabel()
        self.review_impact.setWordWrap(True)
        self.review_impact.setObjectName("frame-wizard-review-impact")
        self.review_impact.setStyleSheet("padding:8px;")
        layout.addWidget(self.review_impact)

        self.review_replace_ack = QCheckBox(
            "I understand that Generate Model will replace the current FE "
            "domain and model-linked objects."
        )
        self.review_replace_ack.setObjectName(
            "frame-wizard-review-replace-ack"
        )
        self.review_replace_ack.toggled.connect(self._update_review_page)
        layout.addWidget(self.review_replace_ack)

        self.review_validation_status = QLabel()
        self.review_validation_status.setWordWrap(True)
        self.review_validation_status.setObjectName(
            "frame-wizard-review-validation-status"
        )
        self.review_validation_status.setStyleSheet("padding:8px;")
        layout.addWidget(self.review_validation_status)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.review_scroll = scroll
        self.review_page_id = self.addPage(page)

    def _review_page_changed(self, page_id: int) -> None:
        if int(page_id) == int(self.review_page_id):
            self._update_review_page()

    def _review_validation_errors(
        self,
        *,
        include_replacement_ack: bool = True,
    ) -> list[str]:
        errors: list[str] = []
        checks = (
            self._member_validation_error,
            self._joint_validation_error,
            self._diaphragm_validation_error,
            self._foundation_validation_error,
            self._brace_validation_error,
            self._load_validation_error,
            self._mass_validation_error,
        )
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
        for check in checks:
            try:
                error = str(check() or "").strip()
            except (TypeError, ValueError) as exc:
                error = str(exc).strip()
            if error and error not in errors:
                errors.append(error)

        if include_replacement_ack:
            replacing = bool(
                self.project.model.nodes or self.project.model.elements
            )
            if (
                replacing
                and hasattr(self, "review_replace_ack")
                and not self.review_replace_ack.isChecked()
            ):
                errors.append(
                    "Confirm replacement of the current FE domain before "
                    "generating the model."
                )
        return errors

    def _review_dry_run(
        self,
        spec: FrameGridSpec,
    ) -> tuple[dict[str, int | float], int]:
        preview_project = ProjectDatabase.from_dict(
            self.project.to_dict()
        )
        preview_spec = replace(spec)
        created_transformations = prepare_frame_grid(
            preview_project,
            preview_spec,
        )
        result = generate_frame_project(
            preview_project,
            preview_spec,
        )
        result = dict(result)
        result["final_nodes"] = len(preview_project.model.nodes)
        result["final_elements"] = len(preview_project.model.elements)
        result["final_constraints"] = len(preview_project.constraints)
        result["final_connections"] = len(preview_project.connections)
        result["final_load_patterns"] = len(preview_project.load_patterns)
        result["final_element_loads"] = len(preview_project.element_loads)
        result["final_mass_sources"] = len(preview_project.mass_sources)
        result["final_analyses"] = len(preview_project.analyses)
        result["final_results"] = len(preview_project.solution_results)
        return result, len(created_transformations)

    def _update_review_page(self, *_args) -> None:
        if not hasattr(self, "review_geometry"):
            return

        spec = self.spec()
        self._update_preview()
        try:
            x_coords, y_coords, z_coords = frame_grid_coordinates(spec)
        except (TypeError, ValueError):
            x_coords = [0.0, 1.0]
            y_coords = [0.0] if spec.planar_2d else [0.0, 1.0]
            z_coords = [0.0, 1.0]

        counts = self._object_counts(spec)
        overall_x = x_coords[-1] - x_coords[0]
        overall_y = (
            y_coords[-1] - y_coords[0]
            if len(y_coords) > 1
            else 0.0
        )
        overall_z = z_coords[-1] - z_coords[0]

        geometry_text = (
            f"<b>{'2D X-Z' if spec.planar_2d else '3D'} frame</b> · "
            f"{spec.nx} X bay(s)"
            + (f" × {spec.ny} Y bay(s)" if not spec.planar_2d else "")
            + f" · {spec.nz} storey(s)<br>"
            f"Envelope: {overall_x:g} × "
            + (
                f"{overall_y:g} × "
                if not spec.planar_2d
                else ""
            )
            + f"{overall_z:g} {self.units.length}<br>"
            f"Base topology: {counts['nodes']} node(s) · "
            f"{counts['columns']} column(s) · "
            f"{counts['beams_x']} X beam(s) · "
            f"{counts['beams_y']} Y beam(s)"
        )
        self.review_geometry.setText(geometry_text)

        joint_count = frame_joint_connection_count(spec)
        floor_levels = frame_floor_levels(spec)
        foundation_count = frame_foundation_count(spec)
        brace_panels = frame_brace_panel_count(spec)
        brace_elements = frame_brace_element_count(spec)

        floor_detail = "None"
        if spec.diaphragm_mode == "Rigid":
            floor_detail = (
                f"Rigid diaphragm · {len(frame_diaphragm_levels(spec))} floor(s)"
            )
        elif spec.diaphragm_mode == "Shell":
            shell_count = (
                len(floor_levels)
                * int(spec.nx)
                * int(spec.ny)
                * int(spec.slab_divisions_x)
                * int(spec.slab_divisions_y)
            )
            floor_detail = (
                f"Shell slab · {len(floor_levels)} floor(s) · "
                f"{shell_count} shell element(s)"
            )

        modeling_text = (
            f"<b>Members:</b> {spec.column_element_type} columns · "
            f"{spec.beam_element_type} beams<br>"
            f"<b>Joints:</b> {spec.joint_model} · "
            f"{joint_count} generated connection(s)<br>"
            f"<b>Floors:</b> {floor_detail}<br>"
            f"<b>Foundation:</b> {spec.foundation_mode}"
            + (
                f" · {foundation_count} spring connection(s)"
                if spec.foundation_mode == "Springs"
                else ""
            )
            + "<br>"
            f"<b>Bracing:</b> "
            + (
                f"{brace_panels} panel(s) · {brace_elements} element(s) · "
                f"{spec.brace_response_preset}"
                if spec.brace_mode == "Truss"
                else "None"
            )
        )
        self.review_modeling.setText(modeling_text)

        load_items: list[str] = []
        if spec.load_mode == "Static":
            if spec.load_self_weight:
                load_items.append("self-weight")
            if spec.load_beam_udl:
                load_items.append("beam UDL")
            if spec.load_floor_area:
                load_items.append(
                    f"floor area → {spec.load_floor_area_direction} beams"
                )
        load_text = ", ".join(load_items) if load_items else "None"

        mass_text = (
            "Automatic Mass Source"
            if spec.mass_source_mode == "Source"
            else "existing member/nodal mass"
        )
        modal_text = (
            f"{spec.modal_num_modes} modes · {spec.modal_eigen_solver}"
            if spec.modal_mode == "Modal"
            else "None"
        )
        self.review_loading.setText(
            f"<b>Static loads:</b> {load_text}<br>"
            f"<b>Mass:</b> {mass_text}<br>"
            f"<b>Modal preset:</b> {modal_text}"
        )

        existing_nodes = len(self.project.model.nodes)
        existing_elements = len(self.project.model.elements)
        replacing = bool(existing_nodes or existing_elements)
        self.review_replace_ack.setVisible(replacing)
        if replacing:
            self.review_impact.setText(
                "<b>Replacement mode</b><br>"
                f"The current FE domain contains {existing_nodes} node(s) and "
                f"{existing_elements} element(s). Generate Model will replace "
                "Sketch/Geometry-linked FE nodes/elements, loads, constraints, "
                "connections, recorders, analyses and result requests. "
                "Material, nDMaterial and section libraries are preserved."
            )
        else:
            self.review_impact.setText(
                "<b>New model</b><br>"
                "The active FE domain is empty. Generate Model will create "
                "this frame as the new FE model."
            )

        definition_errors = self._review_validation_errors(
            include_replacement_ack=False
        )
        if definition_errors:
            self.review_build.setText(
                "<b>Dry-run unavailable</b><br>"
                "Resolve the model-definition issues below before FEWIZ can "
                "simulate the final generation result."
            )
        else:
            try:
                dry_run, transformation_count = self._review_dry_run(spec)
                build_bits = [
                    f"{int(dry_run.get('final_nodes', 0))} node(s)",
                    f"{int(dry_run.get('final_elements', 0))} FE element(s)",
                    f"{int(dry_run.get('final_connections', 0))} connection(s)",
                    f"{int(dry_run.get('final_constraints', 0))} constraint(s)",
                ]
                second_bits = [
                    f"{int(dry_run.get('final_load_patterns', 0))} load pattern(s)",
                    f"{int(dry_run.get('final_element_loads', 0))} element load(s)",
                    f"{int(dry_run.get('final_mass_sources', 0))} mass source(s)",
                    f"{int(dry_run.get('final_analyses', 0))} analysis object(s)",
                    f"{int(dry_run.get('final_results', 0))} result request(s)",
                ]
                self.review_build.setText(
                    "<b>Dry-run passed</b><br>"
                    + " · ".join(build_bits)
                    + "<br>"
                    + " · ".join(second_bits)
                    + (
                        f"<br>{transformation_count} geometric "
                        "transformation(s) will be auto-created."
                        if transformation_count
                        else "<br>No new geometric transformations are needed."
                    )
                )
            except (TypeError, ValueError) as exc:
                definition_errors.append(str(exc))
                self.review_build.setText(
                    "<b>Dry-run failed</b><br>" + str(exc)
                )

        errors = self._review_validation_errors()
        finish = self.button(QWizard.FinishButton)
        if errors:
            self.review_validation_status.setText(
                "<b>Model definition needs attention</b><br>"
                + "<br>".join(
                    f"• {error}"
                    for error in errors[:6]
                )
            )
            if finish is not None and self.currentId() == self.review_page_id:
                finish.setEnabled(False)
        else:
            self.review_validation_status.setText(
                "<b>Ready to generate</b><br>"
                "All Frame Wizard definitions pass the current validation "
                "checks. Review the preview, then choose Generate Model."
            )
            if finish is not None and self.currentId() == self.review_page_id:
                finish.setEnabled(True)

    @staticmethod
    def _section_is_compatible(
        section_type: str,
        element_type: str,
    ) -> bool:
        section_type = str(section_type)
        if section_type in SHELL_SECTION_TYPES | MEMBRANE_SECTION_TYPES:
            return False
        if element_type == "elasticBeamColumn":
            return section_type == "Elastic"
        return section_type in {"Elastic", "Fiber"}

    @staticmethod
    def _hinge_section_is_compatible(section_type: str) -> bool:
        return str(section_type) in {"Elastic", "Fiber"}

    def _populate_section_combo(
        self,
        combo: QComboBox,
        element_type: str,
    ) -> None:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select section…", None)
        for tag in sorted(self.project.sections):
            section = self.project.sections[tag]
            if not self._section_is_compatible(
                section.section_type,
                element_type,
            ):
                continue
            combo.addItem(
                f"{tag} · {section.name} ({section.section_type})",
                int(tag),
            )
        index = combo.findData(previous)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.count() == 2:
            combo.setCurrentIndex(1)
        combo.blockSignals(False)

    def _populate_hinge_section_combo(
        self,
        combo: QComboBox,
    ) -> None:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select section…", None)
        for tag in sorted(self.project.sections):
            section = self.project.sections[tag]
            if not self._hinge_section_is_compatible(
                section.section_type
            ):
                continue
            combo.addItem(
                f"{tag} · {section.name} ({section.section_type})",
                int(tag),
            )
        index = combo.findData(previous)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _populate_member_dependencies(self) -> None:
        self._populate_section_combo(
            self.column_section,
            str(
                self.column_formulation.currentData()
                or "elasticBeamColumn"
            ),
        )
        self._populate_section_combo(
            self.beam_section,
            str(
                self.beam_formulation.currentData()
                or "elasticBeamColumn"
            ),
        )
        for combo in (
            self.column_hinge_i_section,
            self.column_hinge_j_section,
            self.column_interior_section,
            self.beam_hinge_i_section,
            self.beam_hinge_j_section,
            self.beam_interior_section,
        ):
            self._populate_hinge_section_combo(combo)

        for combo, auto_text in (
            (
                self.column_transformation,
                "Auto · PDelta column transformation",
            ),
            (
                self.beam_transformation,
                "Auto · Linear beam transformation",
            ),
        ):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(auto_text, None)
            for tag in sorted(self.project.transformations):
                transformation = self.project.transformations[tag]
                combo.addItem(
                    f"{tag} · {transformation.name} "
                    f"({transformation.transformation_type})",
                    int(tag),
                )
            index = combo.findData(previous)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

        self._sync_hinge_defaults("column")
        self._sync_hinge_defaults("beam")

    def _member_formulation_changed(self, *_args) -> None:
        self._populate_section_combo(
            self.column_section,
            str(
                self.column_formulation.currentData()
                or "elasticBeamColumn"
            ),
        )
        self._populate_section_combo(
            self.beam_section,
            str(
                self.beam_formulation.currentData()
                or "elasticBeamColumn"
            ),
        )
        self._sync_hinge_defaults("column")
        self._sync_hinge_defaults("beam")
        self._sync_member_controls()
        self._update_member_summary()

    def _member_integration_changed(self, *_args) -> None:
        self._sync_hinge_defaults("column")
        self._sync_hinge_defaults("beam")
        self._sync_member_controls()
        self._update_member_summary()

    def _sync_hinge_defaults(self, role: str) -> None:
        main = getattr(self, f"{role}_section")
        main_tag = main.currentData()
        if main_tag is None:
            return
        for suffix in (
            "hinge_i_section",
            "hinge_j_section",
            "interior_section",
        ):
            combo = getattr(self, f"{role}_{suffix}")
            if combo.currentData() is None:
                index = combo.findData(main_tag)
                if index >= 0:
                    combo.setCurrentIndex(index)

    @staticmethod
    def _is_hinge_integration(integration_type: str) -> bool:
        return str(integration_type) in {
            "HingeRadau",
            "HingeRadauTwo",
            "HingeMidpoint",
            "HingeEndpoint",
            "ConcentratedPlasticity",
        }

    def _sync_member_controls(self) -> None:
        columns_on = bool(self.create_columns.isChecked())
        beams_on = bool(
            self.create_beams_x.isChecked()
            or (
                self.dimension.currentData() == "3D"
                and self.create_beams_y.isChecked()
            )
        )
        for widget in (
            self.column_formulation,
            self.column_section,
            self.column_transformation,
            self.column_mass_per_length,
        ):
            widget.setEnabled(columns_on)
        for widget in (
            self.beam_formulation,
            self.beam_section,
            self.beam_transformation,
            self.beam_mass_per_length,
        ):
            widget.setEnabled(beams_on)

        for role, enabled in (
            ("column", columns_on),
            ("beam", beams_on),
        ):
            formulation = str(
                getattr(self, f"{role}_formulation").currentData()
                or "elasticBeamColumn"
            )
            nonlinear = formulation in {
                "forceBeamColumn",
                "dispBeamColumn",
            }
            integration = str(
                getattr(self, f"{role}_integration").currentData()
                or "Lobatto"
            )
            hinge = nonlinear and self._is_hinge_integration(
                integration
            )
            concentrated = integration == "ConcentratedPlasticity"

            getattr(self, f"{role}_integration").setEnabled(
                enabled and nonlinear
            )
            getattr(self, f"{role}_integration_points").setEnabled(
                enabled and nonlinear and not hinge
            )
            for suffix in (
                "hinge_i_section",
                "hinge_j_section",
                "interior_section",
            ):
                getattr(self, f"{role}_{suffix}").setEnabled(
                    enabled and hinge
                )
            getattr(self, f"{role}_hinge_i_length").setEnabled(
                enabled and hinge and not concentrated
            )
            getattr(self, f"{role}_hinge_j_length").setEnabled(
                enabled and hinge and not concentrated
            )

            consistent = getattr(self, f"{role}_consistent_mass")
            consistent.setEnabled(
                enabled and formulation != "forceBeamColumn"
            )
            if formulation == "forceBeamColumn" and consistent.isChecked():
                consistent.blockSignals(True)
                consistent.setChecked(False)
                consistent.blockSignals(False)

    def _member_validation_error(self) -> str:
        columns_on = bool(self.create_columns.isChecked())
        beams_on = bool(
            self.create_beams_x.isChecked()
            or (
                self.dimension.currentData() == "3D"
                and self.create_beams_y.isChecked()
            )
        )
        for role, key, enabled in (
            ("Column", "column", columns_on),
            ("Beam", "beam", beams_on),
        ):
            if not enabled:
                continue
            formulation = str(
                getattr(self, f"{key}_formulation").currentData()
            )
            section_combo = getattr(self, f"{key}_section")
            section_tag = section_combo.currentData()
            if section_tag is None:
                return (
                    f"{role} members require a compatible primary section. "
                    "Create/assign one in the Section library first."
                )
            section = self.project.sections.get(int(section_tag))
            if section is None:
                return f"{role} section {section_tag} no longer exists."
            if not self._section_is_compatible(
                section.section_type,
                formulation,
            ):
                return (
                    f"{role} formulation {formulation} is not compatible "
                    f"with section type {section.section_type}."
                )

            if formulation not in {
                "forceBeamColumn",
                "dispBeamColumn",
            }:
                continue

            integration = str(
                getattr(self, f"{key}_integration").currentData()
            )
            if self._is_hinge_integration(integration):
                for label, suffix in (
                    ("I-end", "hinge_i_section"),
                    ("J-end", "hinge_j_section"),
                    ("interior", "interior_section"),
                ):
                    combo = getattr(self, f"{key}_{suffix}")
                    tag = combo.currentData()
                    if tag is None:
                        return (
                            f"{role} {integration} requires a {label} "
                            "section."
                        )
                    hinge_section = self.project.sections.get(int(tag))
                    if hinge_section is None:
                        return (
                            f"{role} {label} section {tag} no longer exists."
                        )
                    if not self._hinge_section_is_compatible(
                        hinge_section.section_type
                    ):
                        return (
                            f"{role} {label} section must be Elastic or "
                            "Fiber."
                        )
                if integration != "ConcentratedPlasticity":
                    length_i = getattr(
                        self, f"{key}_hinge_i_length"
                    ).value()
                    length_j = getattr(
                        self, f"{key}_hinge_j_length"
                    ).value()
                    if length_i <= 0.0 or length_j <= 0.0:
                        return (
                            f"{role} {integration} requires positive I/J "
                            "hinge lengths."
                        )
        return ""

    def _member_summary_text(self, role: str) -> str:
        formulation = str(
            getattr(self, f"{role}_formulation").currentData()
            or "elasticBeamColumn"
        )
        section = getattr(self, f"{role}_section").currentText()
        transf = getattr(
            self, f"{role}_transformation"
        ).currentText()
        mass = getattr(self, f"{role}_mass_per_length").value()
        consistent = getattr(
            self, f"{role}_consistent_mass"
        ).isChecked()

        detail = f"{formulation} · {section} · {transf}"
        if formulation in {"forceBeamColumn", "dispBeamColumn"}:
            integration = str(
                getattr(self, f"{role}_integration").currentData()
            )
            if self._is_hinge_integration(integration):
                detail += (
                    f" · {integration} · I="
                    f"{getattr(self, f'{role}_hinge_i_section').currentText()}"
                    f" · J="
                    f"{getattr(self, f'{role}_hinge_j_section').currentText()}"
                    f" · interior="
                    f"{getattr(self, f'{role}_interior_section').currentText()}"
                )
                if integration != "ConcentratedPlasticity":
                    detail += (
                        f" · LpI="
                        f"{getattr(self, f'{role}_hinge_i_length').value():g}"
                        f" · LpJ="
                        f"{getattr(self, f'{role}_hinge_j_length').value():g}"
                        f" {self.units.length}"
                    )
            else:
                detail += (
                    f" · {integration} / "
                    f"{getattr(self, f'{role}_integration_points').value()} "
                    "pts"
                )
        detail += f" · mass/L={mass:g}"
        if consistent:
            detail += " · consistent mass"
        elif formulation != "forceBeamColumn":
            detail += " · lumped mass"
        return detail

    def _update_member_summary(self, *_args) -> None:
        if not hasattr(self, "member_summary"):
            return
        self._sync_member_controls()

        self.member_summary.setText(
            "<b>Member assignment review</b><br>"
            "Columns: "
            + self._member_summary_text("column")
            + "<br>Beams: "
            + self._member_summary_text("beam")
        )

        error = self._member_validation_error()
        finish = self.button(QWizard.FinishButton)
        if error:
            self.member_validation_status.setText(
                "<b>Member definition needs attention</b><br>" + error
            )
            if finish is not None and self.currentId() == self.members_page_id:
                finish.setEnabled(False)
        else:
            self.member_validation_status.setText(
                "<b>Member definition ready</b><br>"
                "Formulations, sections, integration, transformations and "
                "mass settings are consistent."
            )
            if finish is not None and self.currentId() == self.members_page_id:
                finish.setEnabled(True)

    def _resize_spacing_editor(
        self,
        editor: SpacingEditor,
        count: int,
    ) -> None:
        editor.set_count(count)
        editor.connect_value_changed(self._update_preview)
        if hasattr(self, "diaphragm_level_table"):
            editor.connect_value_changed(self._refresh_diaphragm_levels)
            self._refresh_diaphragm_levels()
        self._update_preview()

    def _uniform_changed(
        self,
        editor: SpacingEditor,
        value: float,
    ) -> None:
        editor.set_default(value)
        if self.spacing_mode.currentData() == "Uniform":
            editor.fill(value)
        if hasattr(self, "diaphragm_level_table"):
            self._refresh_diaphragm_levels()
        self._update_preview()

    def _sync_dimension(self, *_args) -> None:
        is_3d = self.dimension.currentData() == "3D"
        self.y_bays.setEnabled(is_3d)
        self.y_spacing.setEnabled(
            is_3d and self.spacing_mode.currentData() == "Uniform"
        )
        self.origin_y.setEnabled(is_3d)
        self.create_beams_y.setEnabled(is_3d)
        self.spacing_tabs.setTabEnabled(1, is_3d)
        if not is_3d:
            self.create_beams_y.setChecked(False)
            if self.spacing_tabs.currentIndex() == 1:
                self.spacing_tabs.setCurrentIndex(0)
        elif not self.create_beams_y.isChecked():
            self.create_beams_y.setChecked(True)
        self.base_support.setEnabled(not is_3d)
        self._sync_member_controls()
        if hasattr(self, "joint_model"):
            self._sync_joint_controls()
            self._update_joint_summary()
        if hasattr(self, "diaphragm_mode"):
            self._sync_diaphragm_controls()
            self._update_diaphragm_summary()
        if hasattr(self, "foundation_mode"):
            self._sync_foundation_controls()
            self._update_foundation_summary()
        if hasattr(self, "brace_mode"):
            self._sync_brace_controls()
            self._update_brace_summary()
        if hasattr(self, "load_mode"):
            self._sync_load_controls()
            self._update_load_summary()
        if hasattr(self, "mass_source_mode"):
            self._sync_mass_controls()
            self._update_mass_summary()
        self._update_preview()
        self._update_member_summary()

    def _sync_spacing_mode(self, *_args) -> None:
        individual = self.spacing_mode.currentData() == "Individual"
        self.spacing_tabs.setVisible(individual)
        self.x_spacing.setEnabled(not individual)
        self.storey_height.setEnabled(not individual)
        is_3d = self.dimension.currentData() == "3D"
        self.y_spacing.setEnabled(is_3d and not individual)
        self._update_preview()

    def _individual_spacings(
        self,
    ) -> tuple[
        tuple[float, ...],
        tuple[float, ...],
        tuple[float, ...],
    ]:
        if self.spacing_mode.currentData() != "Individual":
            return (), (), ()
        return (
            self.x_spacing_editor.values(),
            self.y_spacing_editor.values(),
            self.z_spacing_editor.values(),
        )

    def spec(self) -> FrameGridSpec:
        dimension = str(self.dimension.currentData() or "2D")
        x_widths, y_widths, heights = self._individual_spacings()
        return FrameGridSpec(
            nx=int(self.x_bays.value()),
            ny=(
                int(self.y_bays.value())
                if dimension == "3D"
                else 1
            ),
            nz=int(self.storeys.value()),
            dx=float(self.x_spacing.value()),
            dy=float(self.y_spacing.value()),
            dz=float(self.storey_height.value()),
            x_bay_widths=x_widths,
            y_bay_widths=(
                y_widths if dimension == "3D" else ()
            ),
            storey_heights=heights,
            origin_x=float(self.origin_x.value()),
            origin_y=(
                float(self.origin_y.value())
                if dimension == "3D"
                else 0.0
            ),
            origin_z=float(self.origin_z.value()),
            create_columns=bool(self.create_columns.isChecked()),
            create_beams_x=bool(self.create_beams_x.isChecked()),
            create_beams_y=(
                bool(self.create_beams_y.isChecked())
                if dimension == "3D"
                else False
            ),
            column_section_tag=(
                int(self.column_section.currentData())
                if self.column_section.currentData() is not None
                else None
            ),
            beam_section_tag=(
                int(self.beam_section.currentData())
                if self.beam_section.currentData() is not None
                else None
            ),
            column_transf_tag=(
                int(self.column_transformation.currentData())
                if self.column_transformation.currentData() is not None
                else None
            ),
            beam_transf_tag=(
                int(self.beam_transformation.currentData())
                if self.beam_transformation.currentData() is not None
                else None
            ),
            column_element_type=str(
                self.column_formulation.currentData()
                or "elasticBeamColumn"
            ),
            beam_element_type=str(
                self.beam_formulation.currentData()
                or "elasticBeamColumn"
            ),
            column_integration_type=str(
                self.column_integration.currentData() or "Lobatto"
            ),
            beam_integration_type=str(
                self.beam_integration.currentData() or "Lobatto"
            ),
            column_integration_points=int(
                self.column_integration_points.value()
            ),
            beam_integration_points=int(
                self.beam_integration_points.value()
            ),
            column_hinge_i_section_tag=(
                int(self.column_hinge_i_section.currentData())
                if self.column_hinge_i_section.currentData() is not None
                else None
            ),
            column_hinge_j_section_tag=(
                int(self.column_hinge_j_section.currentData())
                if self.column_hinge_j_section.currentData() is not None
                else None
            ),
            column_interior_section_tag=(
                int(self.column_interior_section.currentData())
                if self.column_interior_section.currentData() is not None
                else None
            ),
            beam_hinge_i_section_tag=(
                int(self.beam_hinge_i_section.currentData())
                if self.beam_hinge_i_section.currentData() is not None
                else None
            ),
            beam_hinge_j_section_tag=(
                int(self.beam_hinge_j_section.currentData())
                if self.beam_hinge_j_section.currentData() is not None
                else None
            ),
            beam_interior_section_tag=(
                int(self.beam_interior_section.currentData())
                if self.beam_interior_section.currentData() is not None
                else None
            ),
            column_hinge_i_length=float(
                self.column_hinge_i_length.value()
            ),
            column_hinge_j_length=float(
                self.column_hinge_j_length.value()
            ),
            beam_hinge_i_length=float(
                self.beam_hinge_i_length.value()
            ),
            beam_hinge_j_length=float(
                self.beam_hinge_j_length.value()
            ),
            column_mass_per_length=float(
                self.column_mass_per_length.value()
            ),
            beam_mass_per_length=float(
                self.beam_mass_per_length.value()
            ),
            column_consistent_mass=bool(
                self.column_consistent_mass.isChecked()
                and self.column_formulation.currentData()
                != "forceBeamColumn"
            ),
            beam_consistent_mass=bool(
                self.beam_consistent_mass.isChecked()
                and self.beam_formulation.currentData()
                != "forceBeamColumn"
            ),
            joint_model=str(
                self.joint_model.currentData() or "None"
            ),
            joint_material_tag=(
                int(self.joint_material.currentData())
                if self.joint_material.currentData() is not None
                else None
            ),
            joint_scope=str(
                self.joint_scope.currentData() or "all"
            ),
            joint_panel_width=float(self.joint_panel_width.value()),
            joint_panel_height=float(self.joint_panel_height.value()),
            joint_interface_material_tags=tuple(
                int(combo.currentData() or 0)
                for combo in self.joint_interface_materials
            ),
            joint_large_disp=int(
                self.joint_large_disp.currentData() or 0
            ),
            joint_component_material_tags=tuple(
                (
                    int(combo.currentData())
                    if combo.currentData() is not None
                    else 0
                )
                for combo in self.bcj_materials
            ),
            joint_height_factor=float(self.bcj_height_factor.value()),
            joint_width_factor=float(self.bcj_width_factor.value()),
            joint_rigid_a=float(self.kraw_rigid_a.value()),
            joint_rigid_e=float(self.kraw_rigid_e.value()),
            joint_rigid_i=float(self.kraw_rigid_i.value()),
            diaphragm_mode=str(
                self.diaphragm_mode.currentData() or "None"
            ),
            diaphragm_levels=self._selected_diaphragm_levels(),
            diaphragm_floor_mass=float(
                self.diaphragm_floor_mass.value()
            ),
            diaphragm_rotational_inertia=float(
                self.diaphragm_rotational_inertia.value()
            ),
            slab_section_tag=(
                int(self.slab_section.currentData())
                if self.slab_section.currentData() is not None
                else None
            ),
            slab_element_type=str(
                self.slab_formulation.currentData() or "ASDShellQ4"
            ),
            slab_divisions_x=int(self.slab_divisions_x.value()),
            slab_divisions_y=int(self.slab_divisions_y.value()),
            slab_corotational=bool(self.slab_corotational.isChecked()),
            slab_mass_per_area=float(self.slab_mass_per_area.value()),
            foundation_mode=(
                str(self.foundation_mode.currentData() or "Direct")
                if hasattr(self, "foundation_mode")
                else "Direct"
            ),
            foundation_material_tags=(
                self._foundation_material_tags()
                if hasattr(self, "foundation_materials")
                else (0, 0, 0, 0, 0, 0)
            ),
            foundation_assignment_mode=(
                str(
                    self.foundation_assignment_mode.currentData()
                    or "Uniform"
                )
                if hasattr(self, "foundation_assignment_mode")
                else "Uniform"
            ),
            foundation_profile_material_tags=(
                self._foundation_profile_tags()
                if hasattr(self, "foundation_profile_materials")
                else ()
            ),
            foundation_base_profile_indices=(
                self._foundation_base_profile_indices()
                if hasattr(self, "foundation_base_table")
                else ()
            ),
            brace_mode=(
                str(self.brace_mode.currentData() or "None")
                if hasattr(self, "brace_mode")
                else "None"
            ),
            brace_pattern=(
                str(self.brace_pattern.currentData() or "X")
                if hasattr(self, "brace_pattern")
                else "X"
            ),
            brace_element_type=(
                str(self.brace_element_type.currentData() or "truss")
                if hasattr(self, "brace_element_type")
                else "truss"
            ),
            brace_material_tag=(
                int(self.brace_material.currentData())
                if (
                    hasattr(self, "brace_material")
                    and self.brace_material.currentData() is not None
                )
                else None
            ),
            brace_area=(
                float(self.brace_area.value())
                if hasattr(self, "brace_area")
                else 0.01
            ),
            brace_mass_per_length=(
                float(self.brace_mass_per_length.value())
                if hasattr(self, "brace_mass_per_length")
                else 0.0
            ),
            brace_do_rayleigh=(
                bool(self.brace_do_rayleigh.isChecked())
                if hasattr(self, "brace_do_rayleigh")
                else False
            ),
            brace_x_bays=(
                self._selected_brace_x_bays()
                if hasattr(self, "brace_x_table")
                else ()
            ),
            brace_y_bays=(
                self._selected_brace_y_bays()
                if hasattr(self, "brace_y_table")
                else ()
            ),
            brace_storeys=(
                self._selected_brace_storeys()
                if hasattr(self, "brace_storey_table")
                else ()
            ),
            brace_plane_mode=(
                str(self.brace_plane_mode.currentData() or "X")
                if hasattr(self, "brace_plane_mode")
                else "X"
            ),
            brace_y_plane_scope=(
                str(self.brace_y_plane_scope.currentData() or "All")
                if hasattr(self, "brace_y_plane_scope")
                else "All"
            ),
            brace_x_plane_scope=(
                str(self.brace_x_plane_scope.currentData() or "All")
                if hasattr(self, "brace_x_plane_scope")
                else "All"
            ),
            brace_panel_patterns=(
                self._brace_panel_pattern_overrides()
                if hasattr(self, "brace_panel_table")
                else ()
            ),
            brace_response_preset=(
                str(self.brace_response_preset.currentData() or "Standard")
                if hasattr(self, "brace_response_preset")
                else "Standard"
            ),
            load_mode=(
                str(self.load_mode.currentData() or "None")
                if hasattr(self, "load_mode")
                else "None"
            ),
            load_self_weight=(
                bool(self.load_self_weight.isChecked())
                if hasattr(self, "load_self_weight")
                else False
            ),
            load_self_weight_density=(
                float(self.load_self_weight_density.value())
                if hasattr(self, "load_self_weight_density")
                else 0.0
            ),
            load_beam_udl=(
                bool(self.load_beam_udl.isChecked())
                if hasattr(self, "load_beam_udl")
                else False
            ),
            load_beam_udl_coordinate_system=(
                str(
                    self.load_beam_udl_coordinate.currentData()
                    or "global"
                )
                if hasattr(self, "load_beam_udl_coordinate")
                else "global"
            ),
            load_beam_udl_vector=(
                (
                    float(self.load_udl_x.value()),
                    float(self.load_udl_y.value()),
                    float(self.load_udl_z.value()),
                )
                if hasattr(self, "load_udl_x")
                else (0.0, 0.0, -10.0)
            ),
            load_beam_scope=(
                str(self.load_beam_scope.currentData() or "Both")
                if hasattr(self, "load_beam_scope")
                else "Both"
            ),
            load_storeys=(
                self._selected_load_storeys()
                if hasattr(self, "load_storey_table")
                else ()
            ),
            load_floor_area=(
                bool(self.load_floor_area.isChecked())
                if hasattr(self, "load_floor_area")
                else False
            ),
            load_floor_area_pressure=(
                float(self.load_floor_area_pressure.value())
                if hasattr(self, "load_floor_area_pressure")
                else 0.0
            ),
            load_floor_area_direction=(
                str(self.load_floor_area_direction.currentData() or "X")
                if hasattr(self, "load_floor_area_direction")
                else "X"
            ),
            mass_source_mode=(
                str(self.mass_source_mode.currentData() or "None")
                if hasattr(self, "mass_source_mode")
                else "None"
            ),
            mass_include_self=(
                bool(self.mass_include_self.isChecked())
                if hasattr(self, "mass_include_self")
                else True
            ),
            mass_include_static_loads=(
                bool(self.mass_include_static.isChecked())
                if hasattr(self, "mass_include_static")
                else True
            ),
            mass_static_load_factor=(
                float(self.mass_static_factor.value())
                if hasattr(self, "mass_static_factor")
                else 1.0
            ),
            mass_gravity_axis=(
                int(self.mass_gravity_axis.currentData() or 3)
                if hasattr(self, "mass_gravity_axis")
                else 3
            ),
            mass_directions=(
                self._selected_mass_directions()
                if hasattr(self, "mass_direction_x")
                else ((1,) if dimension == "2D" else (1, 2))
            ),
            modal_mode=(
                str(self.modal_mode.currentData() or "None")
                if hasattr(self, "modal_mode")
                else "None"
            ),
            modal_num_modes=(
                int(self.modal_num_modes.value())
                if hasattr(self, "modal_num_modes")
                else 6
            ),
            modal_eigen_solver=(
                str(
                    self.modal_eigen_solver.currentData()
                    or "-genBandArpack"
                )
                if hasattr(self, "modal_eigen_solver")
                else "-genBandArpack"
            ),
            planar_2d=(dimension == "2D"),
            planar_base_support=str(
                self.base_support.currentData() or "Fixed"
            ),
        )

    @staticmethod
    def _object_counts(
        spec: FrameGridSpec,
    ) -> dict[str, int]:
        nx = int(spec.nx)
        nz = int(spec.nz)
        if spec.planar_2d:
            nodes = (nx + 1) * (nz + 1)
            columns = (nx + 1) * nz if spec.create_columns else 0
            beams_x = nx * nz if spec.create_beams_x else 0
            beams_y = 0
            base_nodes = nx + 1
        else:
            ny = int(spec.ny)
            nodes = (nx + 1) * (ny + 1) * (nz + 1)
            columns = (
                (nx + 1) * (ny + 1) * nz
                if spec.create_columns
                else 0
            )
            beams_x = (
                nx * (ny + 1) * nz
                if spec.create_beams_x
                else 0
            )
            beams_y = (
                (nx + 1) * ny * nz
                if spec.create_beams_y
                else 0
            )
            base_nodes = (nx + 1) * (ny + 1)
        return {
            "nodes": nodes,
            "columns": columns,
            "beams_x": beams_x,
            "beams_y": beams_y,
            "elements": columns + beams_x + beams_y,
            "base_nodes": base_nodes,
        }

    def _update_preview(self, *_args) -> None:
        try:
            spec = self.spec()
            validate_frame_grid_spec(spec)
            x_coords, y_coords, z_coords = frame_grid_coordinates(spec)
            error = ""
        except (TypeError, ValueError) as exc:
            error = str(exc)
            spec = self.spec()
            x_coords = [0.0, 1.0]
            y_coords = [0.0] if spec.planar_2d else [0.0, 1.0]
            z_coords = [0.0, 1.0]

        preview_widgets = [self.preview]
        if hasattr(self, "review_preview"):
            preview_widgets.append(self.review_preview)
        for preview_widget in preview_widgets:
            preview_widget.set_frame(
                dimension="2D" if spec.planar_2d else "3D",
                x_coordinates=x_coords,
                y_coordinates=y_coords,
                z_coordinates=z_coords,
                create_columns=spec.create_columns,
                create_beams_x=spec.create_beams_x,
                create_beams_y=spec.create_beams_y,
                joint_model=spec.joint_model,
                joint_scope=spec.joint_scope,
                joint_panel_width=spec.joint_panel_width,
                joint_panel_height=spec.joint_panel_height,
                diaphragm_mode=spec.diaphragm_mode,
                diaphragm_levels=spec.diaphragm_levels,
                slab_divisions_x=spec.slab_divisions_x,
                slab_divisions_y=spec.slab_divisions_y,
                foundation_mode=spec.foundation_mode,
                foundation_base_profiles=(
                    frame_foundation_profile_assignments(spec)
                ),
                brace_mode=spec.brace_mode,
                brace_pattern=spec.brace_pattern,
                brace_x_bays=spec.brace_x_bays,
                brace_y_bays=spec.brace_y_bays,
                brace_storeys=spec.brace_storeys,
                brace_plane_mode=spec.brace_plane_mode,
                brace_y_plane_scope=spec.brace_y_plane_scope,
                brace_x_plane_scope=spec.brace_x_plane_scope,
                brace_panel_patterns=spec.brace_panel_patterns,
                load_mode=spec.load_mode,
                load_beam_udl=spec.load_beam_udl,
                load_beam_scope=spec.load_beam_scope,
                load_storeys=spec.load_storeys,
                load_floor_area=spec.load_floor_area,
                load_floor_area_direction=spec.load_floor_area_direction,
            )

        counts = self._object_counts(spec)
        total_x = x_coords[-1] - x_coords[0]
        total_y = (
            y_coords[-1] - y_coords[0]
            if len(y_coords) > 1
            else 0.0
        )
        total_h = z_coords[-1] - z_coords[0]
        spacing_text = (
            "Individual"
            if self.spacing_mode.currentData() == "Individual"
            else "Uniform"
        )
        self.summary.setText(
            "<b>Geometry summary</b><br>"
            f"Spacing: {spacing_text} · "
            f"overall X={total_x:g} {self.units.length}"
            + (
                f" · Y={total_y:g} {self.units.length}"
                if not spec.planar_2d
                else ""
            )
            + f" · H={total_h:g} {self.units.length}<br>"
            f"Nodes: {counts['nodes']} · Columns: {counts['columns']} · "
            f"X beams: {counts['beams_x']} · "
            f"Y beams: {counts['beams_y']}<br>"
            f"Total frame elements: {counts['elements']} · "
            f"Base nodes: {counts['base_nodes']}"
        )

        finish = self.button(QWizard.FinishButton)
        if error:
            self.validation_status.setText(
                "<b>Geometry needs attention</b><br>" + error
            )
            if finish is not None:
                finish.setEnabled(False)
        else:
            self.validation_status.setText(
                "<b>Geometry ready</b><br>"
                "Grid coordinates and topology are valid. Continue to "
                "Members & Sections."
            )
            if finish is not None:
                finish.setEnabled(True)

    def validateCurrentPage(self) -> bool:  # noqa: N802
        # Geometry is a prerequisite for every later page. Validate it even
        # when currentId() is -1 (possible before an offscreen wizard is
        # shown), so programmatic callers cannot bypass topology checks.
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            self.validation_status.setText(
                "<b>Geometry needs attention</b><br>" + str(exc)
            )
            return False

        if self.currentId() == self.members_page_id:
            error = self._member_validation_error()
            if error:
                self.member_validation_status.setText(
                    "<b>Member definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.joints_page_id:
            error = self._joint_validation_error()
            if error:
                self.joint_validation_status.setText(
                    "<b>Joint definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.floors_page_id:
            error = self._diaphragm_validation_error()
            if error:
                self.diaphragm_validation_status.setText(
                    "<b>Floor definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.foundation_page_id:
            error = self._foundation_validation_error()
            if error:
                self.foundation_validation_status.setText(
                    "<b>Foundation definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.bracing_page_id:
            error = self._brace_validation_error()
            if error:
                self.brace_validation_status.setText(
                    "<b>Bracing definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.loads_page_id:
            error = self._load_validation_error()
            if error:
                self.load_validation_status.setText(
                    "<b>Load definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.mass_page_id:
            error = self._mass_validation_error()
            if error:
                self.mass_validation_status.setText(
                    "<b>Mass definition needs attention</b><br>" + error
                )
                return False
        if self.currentId() == self.review_page_id:
            errors = self._review_validation_errors()
            if errors:
                self.review_validation_status.setText(
                    "<b>Model definition needs attention</b><br>"
                    + "<br>".join(
                        f"• {error}"
                        for error in errors[:6]
                    )
                )
                finish = self.button(QWizard.FinishButton)
                if finish is not None:
                    finish.setEnabled(False)
                return False
        return True

    def initializePage(self, page_id: int) -> None:  # noqa: N802
        super().initializePage(page_id)
        if page_id == self.members_page_id:
            self._populate_member_dependencies()
            self._sync_member_controls()
            self._update_member_summary()
        elif page_id == self.joints_page_id:
            self._populate_joint_materials()
            self._sync_joint_controls()
            self._update_joint_summary()
        elif page_id == self.floors_page_id:
            self._populate_slab_sections()
            self._refresh_diaphragm_levels()
            self._sync_diaphragm_controls()
            self._update_diaphragm_summary()
        elif page_id == self.foundation_page_id:
            self._populate_foundation_materials()
            self._refresh_foundation_base_table()
            self._sync_foundation_controls()
            self._update_foundation_summary()
        elif page_id == self.bracing_page_id:
            self._populate_brace_materials()
            self._refresh_brace_scope_tables()
            self._refresh_brace_panel_table()
            self._sync_brace_controls()
            self._update_brace_summary()
        elif page_id == self.loads_page_id:
            self._refresh_load_storeys()
            self._sync_load_controls()
            self._update_load_summary()
        elif page_id == self.mass_page_id:
            self._sync_mass_controls()
            self._update_mass_summary()
        elif page_id == self.review_page_id:
            self._update_review_page()
