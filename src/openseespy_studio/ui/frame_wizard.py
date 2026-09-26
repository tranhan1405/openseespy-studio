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

        if self.joint_model == "ZeroLength":
            spring_pen = QPen(self.palette().highlight().color())
            spring_pen.setWidthF(1.4)
            painter.setPen(spring_pen)
            if self.dimension == "2D":
                x_indices = list(range(len(self.x_coordinates)))
                if self.joint_scope == "interior":
                    x_indices = list(
                        range(1, len(self.x_coordinates) - 1)
                    )
                for k in range(1, len(self.z_coordinates)):
                    for i in x_indices:
                        point = p(i, k)
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
        self._sync_dimension()
        self._sync_spacing_mode()
        self._sync_member_controls()
        self._sync_joint_controls()
        self._update_preview()
        self._update_member_summary()
        self._update_joint_summary()

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
            "Define explicit beam-to-column rotational connection behaviour. "
            "This phase implements generated zeroLength springs with automatic "
            "node duplication and DOF tying."
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

        self.joint_material = QComboBox()
        self.joint_scope = QComboBox()
        self.joint_scope.addItem("All elevated beam-column joints", "all")
        self.joint_scope.addItem(
            "Interior grid joints only",
            "interior",
        )

        model_box = QGroupBox("Joint model")
        form = QFormLayout(model_box)
        form.addRow("Connection model:", self.joint_model)
        form.addRow("Rotational material:", self.joint_material)
        form.addRow("Apply to:", self.joint_scope)
        layout.addWidget(model_box)

        note = QLabel(
            "zeroLength mode keeps the column/grid node as the retained node, "
            "creates one coincident beam-side node per active beam family, "
            "rewires the beam members, ties every non-spring DOF with equalDOF, "
            "and inserts the rotational spring. For X beams the spring acts "
            "about global Y; for Y beams it acts about global X. "
            "Joint2D, BeamColumnJoint and the Krawinkler panel-zone macro are "
            "reserved for the second half of Task 3 because they require a "
            "dedicated 2D joint-core topology rather than FEWIZ's current "
            "3D/6DOF planar-frame convention."
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
        self.joint_model.currentIndexChanged.connect(
            self._sync_joint_controls
        )
        self.joint_material.currentIndexChanged.connect(
            self._update_joint_summary
        )
        self.joint_scope.currentIndexChanged.connect(
            self._update_joint_summary
        )

        for widget in (
            self.dimension,
            self.x_bays,
            self.y_bays,
            self.storeys,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    self._update_joint_summary
                )
            else:
                widget.valueChanged.connect(self._update_joint_summary)
        for checkbox in (
            self.create_columns,
            self.create_beams_x,
            self.create_beams_y,
        ):
            checkbox.toggled.connect(self._update_joint_summary)

    def _populate_joint_materials(self) -> None:
        previous = self.joint_material.currentData()
        self.joint_material.blockSignals(True)
        self.joint_material.clear()
        self.joint_material.addItem("Select rotational material…", None)
        for tag, material in sorted(self.project.materials.items()):
            self.joint_material.addItem(
                f"{tag} · {material.name} [{material.material_type}]",
                int(tag),
            )
        if previous is not None:
            index = self.joint_material.findData(previous)
            if index >= 0:
                self.joint_material.setCurrentIndex(index)
        self.joint_material.blockSignals(False)

    def _sync_joint_controls(self, *_args) -> None:
        active = self.joint_model.currentData() == "ZeroLength"
        self.joint_material.setEnabled(active)
        self.joint_scope.setEnabled(active)
        self._update_joint_summary()
        self._update_preview()

    def _joint_validation_error(self) -> str:
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            return str(exc)
        if self.joint_model.currentData() == "ZeroLength":
            tag = self.joint_material.currentData()
            if tag is None:
                return "Select a rotational uniaxial material for the joint."
            if int(tag) not in self.project.materials:
                return f"Joint material tag {int(tag)} no longer exists."
        return ""

    def _update_joint_summary(self, *_args) -> None:
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
        else:
            self.joint_summary.setText(
                "<b>Joint generation summary</b><br>"
                "Rigid centerline connectivity; no duplicate joint nodes, "
                "MPC ties or connection elements will be generated."
            )

        if error:
            self.joint_validation_status.setText(
                "<b>Joint definition needs attention</b><br>" + error
            )
        else:
            self.joint_validation_status.setText(
                "<b>Joint definition ready</b><br>"
                "The selected joint topology is consistent with the frame "
                "geometry and member families."
            )

    def apply_to_project(self) -> dict[str, int]:
        """Generate the current Frame Wizard definition into the project."""
        return generate_frame_project(self.project, self.spec())

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
        self._update_preview()

    def _uniform_changed(
        self,
        editor: SpacingEditor,
        value: float,
    ) -> None:
        editor.set_default(value)
        if self.spacing_mode.currentData() == "Uniform":
            editor.fill(value)
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
