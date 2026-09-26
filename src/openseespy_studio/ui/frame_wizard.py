from __future__ import annotations

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

from ..generator import (
    FrameGridSpec,
    frame_diaphragm_count,
    frame_diaphragm_levels,
    frame_grid_coordinates,
    frame_joint_connection_count,
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

        if self.dimension == "3D" and self.diaphragm_mode == "Rigid":
            diaphragm_pen = QPen(self.palette().highlight().color())
            diaphragm_pen.setWidthF(1.8)
            painter.setPen(diaphragm_pen)
            levels = (
                self.diaphragm_levels
                if self.diaphragm_levels
                else tuple(range(1, len(self.z_coordinates)))
            )
            for level in levels:
                if level <= 0 or level >= len(self.z_coordinates):
                    continue
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
                        self.z_coordinates[level],
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
        self._sync_dimension()
        self._sync_spacing_mode()
        self._sync_member_controls()
        self._sync_joint_controls()
        self._sync_diaphragm_controls()
        self._update_preview()
        self._update_member_summary()
        self._update_joint_summary()
        self._update_diaphragm_summary()

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
            "Select elevated floors for rigid in-plane diaphragm behaviour "
            "and optional lumped floor mass at a generated centroid master node."
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
            "None · flexible frame floor",
            "None",
        )
        self.diaphragm_mode.addItem(
            "Rigid diaphragm · centroid master node",
            "Rigid",
        )

        mode_group = QGroupBox("Floor diaphragm")
        mode_form = QFormLayout(mode_group)
        mode_form.addRow("Diaphragm mode:", self.diaphragm_mode)
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
        floor_group = QGroupBox("Apply diaphragm to floors")
        floor_layout = QVBoxLayout(floor_group)
        floor_layout.addWidget(self.diaphragm_level_table)
        layout.addWidget(floor_group)
        self.diaphragm_floor_group = floor_group

        self.diaphragm_floor_mass = self._nonnegative(0.0)
        self.diaphragm_rotational_inertia = self._nonnegative(0.0)
        mass_group = QGroupBox("Optional lumped master-node mass")
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
            "The generated master node carries UX/UY mass and optional RZ "
            "rotational inertia. UZ/RX/RY are restrained so the retained node "
            "does not introduce free zero-stiffness modes."
        )
        mass_hint.setWordWrap(True)
        mass_form.addRow(mass_hint)
        layout.addWidget(mass_group)
        self.diaphragm_mass_group = mass_group

        note = QLabel(
            "Rigid diaphragm is available for the standard 3D/6DOF frame "
            "workflow. FEWIZ creates one centroid retained node per selected "
            "floor and one OpenSees rigidDiaphragm(perpDirn=3) constraint. "
            "Semi-rigid shell slabs are reserved for the second half of Task 4."
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

        self._refresh_diaphragm_levels()
        self.diaphragm_mode.currentIndexChanged.connect(
            self._diaphragm_control_changed
        )
        self.diaphragm_level_table.itemChanged.connect(
            self._diaphragm_control_changed
        )
        self.diaphragm_floor_mass.valueChanged.connect(
            self._diaphragm_control_changed
        )
        self.diaphragm_rotational_inertia.valueChanged.connect(
            self._diaphragm_control_changed
        )
        self.storeys.valueChanged.connect(self._refresh_diaphragm_levels)
        self.dimension.currentIndexChanged.connect(
            self._diaphragm_control_changed
        )

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
        active = self.diaphragm_mode.currentData() == "Rigid"
        self.diaphragm_floor_group.setEnabled(active)
        self.diaphragm_mass_group.setEnabled(active)

    def _diaphragm_validation_error(self) -> str:
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            return str(exc)
        if (
            self.diaphragm_mode.currentData() == "Rigid"
            and not self._selected_diaphragm_levels()
        ):
            return "Select at least one elevated floor for the diaphragm."
        return ""

    def _update_diaphragm_summary(self, *_args) -> None:
        if not hasattr(self, "diaphragm_summary"):
            return
        self._sync_diaphragm_controls()
        try:
            spec = self.spec()
            count = frame_diaphragm_count(spec)
            levels = frame_diaphragm_levels(spec)
            error = self._diaphragm_validation_error()
        except (TypeError, ValueError) as exc:
            spec = self.spec()
            count = 0
            levels = ()
            error = str(exc)

        if spec.diaphragm_mode == "Rigid":
            nodes_per_floor = (
                (int(spec.nx) + 1) * (int(spec.ny) + 1)
                if not spec.planar_2d
                else 0
            )
            self.diaphragm_summary.setText(
                "<b>Floor diaphragm summary</b><br>"
                f"Rigid diaphragms: {count} · floors: "
                + ", ".join(map(str, levels))
                + "<br>"
                f"Centroid master nodes: {count} · constrained grid nodes / "
                f"floor: {nodes_per_floor}<br>"
                f"Mass / floor: {spec.diaphragm_floor_mass:g} "
                f"{self.units.mass_label} · RZ inertia: "
                f"{spec.diaphragm_rotational_inertia:g}"
            )
        else:
            self.diaphragm_summary.setText(
                "<b>Floor diaphragm summary</b><br>"
                "No diaphragm constraints or floor master nodes will be "
                "generated."
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
                "Selected floors, retained nodes and optional lumped mass "
                "are consistent with the frame definition."
            )
            if finish is not None and self.currentId() == self.floors_page_id:
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

        self.preview.set_frame(
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
            self._refresh_diaphragm_levels()
            self._sync_diaphragm_controls()
            self._update_diaphragm_summary()
