from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..generator import FrameGridSpec
from ..project import ProjectDatabase
from ..units import UnitSystem


class FramePreview(QWidget):
    """Lightweight live preview for the first Frame Wizard tranche."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dimension = "2D"
        self.nx = 3
        self.ny = 2
        self.nz = 3
        self.dx = 5.0
        self.dy = 5.0
        self.dz = 3.5
        self.create_columns = True
        self.create_beams_x = True
        self.create_beams_y = True
        self.setMinimumHeight(250)

    def set_frame(
        self,
        *,
        dimension: str,
        nx: int,
        ny: int,
        nz: int,
        dx: float,
        dy: float,
        dz: float,
        create_columns: bool,
        create_beams_x: bool,
        create_beams_y: bool,
    ) -> None:
        self.dimension = str(dimension)
        self.nx = max(1, int(nx))
        self.ny = max(1, int(ny))
        self.nz = max(1, int(nz))
        self.dx = max(float(dx), 1.0e-9)
        self.dy = max(float(dy), 1.0e-9)
        self.dz = max(float(dz), 1.0e-9)
        self.create_columns = bool(create_columns)
        self.create_beams_x = bool(create_beams_x)
        self.create_beams_y = bool(create_beams_y)
        self.update()

    def _project_3d(self, x: float, y: float, z: float) -> QPointF:
        # Compact engineering-style axonometric projection.
        return QPointF(x + 0.55 * y, z + 0.32 * y)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(24, 20, -24, -28)
        if rect.width() <= 20 or rect.height() <= 20:
            return

        if self.dimension == "2D":
            raw_points = [
                QPointF(i * self.dx, k * self.dz)
                for k in range(self.nz + 1)
                for i in range(self.nx + 1)
            ]
        else:
            raw_points = [
                self._project_3d(i * self.dx, j * self.dy, k * self.dz)
                for k in range(self.nz + 1)
                for j in range(self.ny + 1)
                for i in range(self.nx + 1)
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
                return map_point(QPointF(i * self.dx, k * self.dz))

            if self.create_columns:
                for k in range(self.nz):
                    for i in range(self.nx + 1):
                        painter.drawLine(p(i, k), p(i, k + 1))
            if self.create_beams_x:
                for k in range(1, self.nz + 1):
                    for i in range(self.nx):
                        painter.drawLine(p(i, k), p(i + 1, k))
        else:
            def p(i: int, j: int, k: int) -> QPointF:
                return map_point(
                    self._project_3d(
                        i * self.dx,
                        j * self.dy,
                        k * self.dz,
                    )
                )

            if self.create_columns:
                for k in range(self.nz):
                    for j in range(self.ny + 1):
                        for i in range(self.nx + 1):
                            painter.drawLine(p(i, j, k), p(i, j, k + 1))
            if self.create_beams_x:
                for k in range(1, self.nz + 1):
                    for j in range(self.ny + 1):
                        for i in range(self.nx):
                            painter.drawLine(p(i, j, k), p(i + 1, j, k))
            if self.create_beams_y:
                for k in range(1, self.nz + 1):
                    for j in range(self.ny):
                        for i in range(self.nx + 1):
                            painter.drawLine(p(i, j, k), p(i, j + 1, k))

        node_pen = QPen(self.palette().highlight().color())
        node_pen.setWidthF(4.0)
        node_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(node_pen)
        for point in raw_points:
            painter.drawPoint(map_point(point))

        painter.setPen(self.palette().text().color())
        painter.drawText(
            10,
            self.height() - 8,
            (
                f"{self.dimension} · {self.nx} X bay(s)"
                + (
                    f" × {self.ny} Y bay(s)"
                    if self.dimension == "3D"
                    else ""
                )
                + f" · {self.nz} storey(s)"
            ),
        )


class FrameWizard(QWizard):
    """First 10% slice of FEWIZ's general frame-generation workflow."""

    def __init__(self, project: ProjectDatabase, parent=None):
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)

        self.setWindowTitle("Frame Wizard")
        self.setMinimumSize(720, 620)
        self.setWizardStyle(QWizard.ModernStyle)

        self._build_geometry_page()
        self._sync_dimension()
        self._update_preview()

    @staticmethod
    def _spin(value: int, lo: int = 1, hi: int = 50) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(lo, hi)
        widget.setValue(value)
        return widget

    @staticmethod
    def _double(value: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(4)
        widget.setRange(1.0e-6, 1.0e9)
        widget.setValue(value)
        return widget

    def _build_geometry_page(self) -> None:
        page = QWizardPage()
        page.setTitle("Geometry & Grid")
        page.setSubTitle(
            "Define the regular frame grid. Member formulation, sections, "
            "diaphragms and advanced storey/span editing follow in later "
            "Frame Wizard phases."
        )

        scroll = QScrollArea()
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

        self.x_spacing = self._double(self.units.length_from_m(5.0))
        self.y_spacing = self._double(self.units.length_from_m(5.0))
        self.storey_height = self._double(self.units.length_from_m(3.5))

        form.addRow("Dimension:", self.dimension)
        form.addRow("X bays:", self.x_bays)
        form.addRow(
            f"X bay width [{self.units.length}]:",
            self.x_spacing,
        )
        form.addRow("Y bays:", self.y_bays)
        form.addRow(
            f"Y bay width [{self.units.length}]:",
            self.y_spacing,
        )
        form.addRow("Storeys:", self.storeys)
        form.addRow(
            f"Storey height [{self.units.length}]:",
            self.storey_height,
        )
        layout.addWidget(geometry)

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
        layout.addWidget(support)

        self.preview = FramePreview()
        self.preview.setObjectName("frame-wizard-live-preview")
        layout.addWidget(self.preview)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("padding:8px;")
        layout.addWidget(self.summary)
        layout.addStretch(1)

        outer = QVBoxLayout(page)
        outer.addWidget(scroll)
        self.geometry_scroll = scroll
        self.addPage(page)

        self.dimension.currentIndexChanged.connect(self._sync_dimension)
        for widget in (
            self.x_bays,
            self.y_bays,
            self.storeys,
            self.x_spacing,
            self.y_spacing,
            self.storey_height,
        ):
            widget.valueChanged.connect(self._update_preview)
        for widget in (
            self.create_columns,
            self.create_beams_x,
            self.create_beams_y,
        ):
            widget.toggled.connect(self._update_preview)
        self.base_support.currentIndexChanged.connect(self._update_preview)

    def _sync_dimension(self, *_args) -> None:
        is_3d = self.dimension.currentData() == "3D"
        self.y_bays.setEnabled(is_3d)
        self.y_spacing.setEnabled(is_3d)
        self.create_beams_y.setEnabled(is_3d)
        if not is_3d:
            self.create_beams_y.setChecked(False)
        elif not self.create_beams_y.isChecked():
            self.create_beams_y.setChecked(True)
        self.base_support.setEnabled(not is_3d)
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        dimension = str(self.dimension.currentData() or "2D")
        self.preview.set_frame(
            dimension=dimension,
            nx=self.x_bays.value(),
            ny=self.y_bays.value(),
            nz=self.storeys.value(),
            dx=self.x_spacing.value(),
            dy=self.y_spacing.value(),
            dz=self.storey_height.value(),
            create_columns=self.create_columns.isChecked(),
            create_beams_x=self.create_beams_x.isChecked(),
            create_beams_y=(
                self.create_beams_y.isChecked()
                if dimension == "3D"
                else False
            ),
        )

        nx = self.x_bays.value()
        ny = self.y_bays.value() if dimension == "3D" else 0
        nz = self.storeys.value()
        if dimension == "2D":
            nodes = (nx + 1) * (nz + 1)
            columns = (nx + 1) * nz if self.create_columns.isChecked() else 0
            beams_x = nx * nz if self.create_beams_x.isChecked() else 0
            beams_y = 0
        else:
            nodes = (nx + 1) * (ny + 1) * (nz + 1)
            columns = (
                (nx + 1) * (ny + 1) * nz
                if self.create_columns.isChecked()
                else 0
            )
            beams_x = (
                nx * (ny + 1) * nz
                if self.create_beams_x.isChecked()
                else 0
            )
            beams_y = (
                (nx + 1) * ny * nz
                if self.create_beams_y.isChecked()
                else 0
            )

        self.summary.setText(
            "<b>Live object estimate</b><br>"
            f"Nodes: {nodes} · Columns: {columns} · "
            f"X beams: {beams_x} · Y beams: {beams_y}<br>"
            f"Total frame elements: {columns + beams_x + beams_y}<br>"
            "Phase 1 uses the existing regular Frame Grid backend; "
            "sections/member formulations will be added on the next pages."
        )

    def spec(self) -> FrameGridSpec:
        dimension = str(self.dimension.currentData() or "2D")
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
