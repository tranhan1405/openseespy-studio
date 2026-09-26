from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
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
    validate_frame_grid_spec,
)
from ..project import ProjectDatabase
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
    ) -> None:
        self.dimension = str(dimension)
        self.x_coordinates = list(x_coordinates)
        self.y_coordinates = list(y_coordinates)
        self.z_coordinates = list(z_coordinates)
        self.create_columns = bool(create_columns)
        self.create_beams_x = bool(create_beams_x)
        self.create_beams_y = bool(create_beams_y)
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
        self._sync_dimension()
        self._sync_spacing_mode()
        self._update_preview()

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
        self.addPage(page)

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
        self.base_support.currentIndexChanged.connect(self._update_preview)

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
        self._update_preview()

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
                "Grid coordinates and topology are valid. Finish creates "
                "the frame using the existing Frame Grid backend."
            )
            if finish is not None:
                finish.setEnabled(True)

    def validateCurrentPage(self) -> bool:  # noqa: N802
        try:
            validate_frame_grid_spec(self.spec())
        except (TypeError, ValueError) as exc:
            self.validation_status.setText(
                "<b>Geometry needs attention</b><br>" + str(exc)
            )
            return False
        return True
