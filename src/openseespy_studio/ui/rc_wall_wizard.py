from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..material_library import load_verified_material_library
from ..project import ProjectDatabase
from ..rc_wall import (
    RCWallSpec,
    rc_wall_reinforcement_summary,
    validate_rc_wall_spec,
)
from ..units import UnitSystem


def _double(
    value: float,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 6,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(low, high)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


class RCWallPreview(QWidget):
    """Compact schematic preview of the MEFI wall discretization."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.width_value = 1.0
        self.height_value = 2.0
        self.thickness_value = 0.15
        self.boundary_value = 0.2
        self.rows = 1
        self.fibers = 3
        self.formulation = "MEFI"
        self.reinforcement_mode = "smeared"
        self.boundary_bars = 0
        self.boundary_layer_mode = "front_back"
        self.boundary_cover = 0.0
        self.web_horizontal_mode = "smeared"
        self.web_horizontal_layer_mode = "front_back"
        self.web_vertical_mode = "smeared"
        self.web_vertical_bar_diameter = 0.0
        self.web_vertical_spacing = 0.2
        self.web_vertical_edge_offset = 0.05
        self.web_vertical_layer_mode = "front_back"
        self.detailed_annotations = False
        self.warning_keys: set[str] = set()
        self.setMinimumHeight(190)

    def set_wall(
        self,
        *,
        width: float,
        height: float,
        thickness: float = 0.15,
        boundary: float,
        rows: int,
        fibers: int,
        formulation: str = "MEFI",
        reinforcement_mode: str = "smeared",
        boundary_bars: int = 0,
        boundary_layer_mode: str = "front_back",
        boundary_cover: float = 0.0,
        web_horizontal_mode: str = "smeared",
        web_horizontal_layer_mode: str = "front_back",
        web_vertical_mode: str = "smeared",
        web_vertical_bar_diameter: float = 0.0,
        web_vertical_spacing: float = 0.2,
        web_vertical_edge_offset: float = 0.05,
        web_vertical_layer_mode: str = "front_back",
        detailed_annotations: bool = False,
        warning_keys: set[str] | None = None,
    ) -> None:
        self.width_value = max(float(width), 1.0e-12)
        self.height_value = max(float(height), 1.0e-12)
        self.thickness_value = max(float(thickness), 1.0e-12)
        self.boundary_value = max(float(boundary), 0.0)
        self.rows = max(int(rows), 1)
        self.fibers = max(int(fibers), 3)
        self.formulation = str(formulation)
        self.reinforcement_mode = str(reinforcement_mode)
        self.boundary_bars = max(int(boundary_bars), 0)
        self.boundary_layer_mode = str(boundary_layer_mode)
        self.boundary_cover = max(float(boundary_cover), 0.0)
        self.web_horizontal_mode = str(web_horizontal_mode)
        self.web_horizontal_layer_mode = str(web_horizontal_layer_mode)
        self.web_vertical_mode = str(web_vertical_mode)
        self.web_vertical_bar_diameter = max(
            float(web_vertical_bar_diameter), 0.0
        )
        self.web_vertical_spacing = max(
            float(web_vertical_spacing), 1.0e-12
        )
        self.web_vertical_edge_offset = max(
            float(web_vertical_edge_offset), 0.0
        )
        self.web_vertical_layer_mode = str(web_vertical_layer_mode)
        self.detailed_annotations = bool(detailed_annotations)
        self.warning_keys = set(warning_keys or ())
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 42.0
        available_w = max(float(self.width()) - 2.0 * margin, 20.0)
        available_h = max(float(self.height()) - 2.0 * margin, 20.0)
        scale = min(
            available_w / self.width_value,
            available_h / self.height_value,
        )
        wall_w = self.width_value * scale
        wall_h = self.height_value * scale
        left = (float(self.width()) - wall_w) / 2.0
        top = (float(self.height()) - wall_h) / 2.0

        painter.fillRect(self.rect(), QColor("#f8fafc"))
        painter.fillRect(
            int(left), int(top), int(wall_w), int(wall_h),
            QColor("#ffffff"),
        )

        boundary_px = min(
            wall_w / 2.0,
            self.boundary_value * scale,
        )
        painter.fillRect(
            int(left), int(top), int(boundary_px), int(wall_h),
            QColor("#e7eef7"),
        )
        painter.fillRect(
            int(left + wall_w - boundary_px),
            int(top),
            int(boundary_px),
            int(wall_h),
            QColor("#e7eef7"),
        )

        if "boundary" in self.warning_keys:
            warning_pen = QPen(QColor("#c62828"), 2.4)
            painter.setPen(warning_pen)
            painter.drawRect(
                int(left), int(top), int(boundary_px), int(wall_h)
            )
            painter.drawRect(
                int(left + wall_w - boundary_px),
                int(top),
                int(boundary_px),
                int(wall_h),
            )

        painter.setPen(
            QPen(
                QColor(
                    "#c62828"
                    if "geometry" in self.warning_keys
                    else "#49657f"
                ),
                2.2 if "geometry" in self.warning_keys else 1.2,
            )
        )
        painter.drawRect(
            int(left), int(top), int(wall_w), int(wall_h)
        )

        for row in range(1, self.rows):
            y = top + wall_h * row / self.rows
            painter.drawLine(
                int(left), int(y), int(left + wall_w), int(y)
            )

        if self.formulation in {"MVLEM", "SFI_MVLEM"}:
            center_x = left + 0.5 * wall_w
            center_pen = QPen(QColor("#f28c00"), 2.2)
            center_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(center_pen)
            painter.drawLine(
                int(center_x), int(top), int(center_x), int(top + wall_h)
            )
            painter.setBrush(QColor("#ffffff"))
            node_pen = QPen(QColor("#f28c00"), 1.8)
            painter.setPen(node_pen)
            for row in range(self.rows + 1):
                y = top + wall_h * row / self.rows
                painter.drawEllipse(
                    int(center_x - 3), int(y - 3), 6, 6
                )
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.formulation == "MVLEM_3D":
            panel_pen = QPen(QColor("#f28c00"), 1.7)
            panel_pen.setStyle(Qt.PenStyle.DashDotLine)
            painter.setPen(panel_pen)
            for row in range(self.rows):
                y0 = top + wall_h * row / self.rows
                y1 = top + wall_h * (row + 1) / self.rows
                painter.drawLine(
                    int(left), int(y0), int(left + wall_w), int(y1)
                )

        web_count = max(self.fibers - 2, 1)
        web_width = max(
            self.width_value - 2.0 * self.boundary_value,
            0.0,
        ) / web_count
        cumulative = [self.boundary_value]
        for _index in range(1, web_count):
            cumulative.append(cumulative[-1] + web_width)
        cumulative.append(
            self.width_value - self.boundary_value
        )

        painter.setPen(QPen(QColor("#9aaabd"), 1.0))
        for value in cumulative:
            x = left + value * scale
            painter.drawLine(
                int(x), int(top), int(x), int(top + wall_h)
            )

        if (
            self.reinforcement_mode in {"hybrid", "fully_discrete"}
            and self.boundary_bars
        ):
            # Elevation preview: individual boundary bars are shown explicitly.
            # Front/back bars are separated schematically by line style because
            # the physical model is a 2D MEFI wall.
            cover_px = min(
                max(self.boundary_cover * scale, 0.0),
                max(boundary_px * 0.40, 0.0),
            )
            usable = max(boundary_px - 2.0 * cover_px, 1.0)

            layer_layout = (
                (("front", self.boundary_bars // 2),
                 ("back", self.boundary_bars // 2))
                if self.boundary_layer_mode == "front_back"
                else (("center", self.boundary_bars),)
            )
            for layer_index, (layer_name, layer_count) in enumerate(
                layer_layout
            ):
                preview_bars = min(max(layer_count, 0), 12)
                if preview_bars <= 0:
                    continue
                pen = QPen(
                    QColor("#d64545" if layer_name != "back" else "#9f2f2f"),
                    2.2,
                )
                if layer_name == "back":
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                layer_shift = 2.0 * layer_index
                for bar in range(preview_bars):
                    fraction = (
                        0.5
                        if preview_bars == 1
                        else bar / (preview_bars - 1)
                    )
                    x_left = (
                        left + cover_px + usable * fraction + layer_shift
                    )
                    x_right = (
                        left + wall_w - boundary_px
                        + cover_px + usable * fraction - layer_shift
                    )
                    painter.drawLine(
                        int(x_left), int(top),
                        int(x_left), int(top + wall_h),
                    )
                    painter.drawLine(
                        int(x_right), int(top),
                        int(x_right), int(top + wall_h),
                    )

            if self.web_horizontal_mode == "mesh_aligned":
                # Only internal MEFI node rows are valid perfect-bond locations
                # before embedded/interpolation coupling is implemented.
                pen = QPen(QColor("#2f80c9"), 1.8)
                if self.web_horizontal_layer_mode == "front_back":
                    pen.setStyle(Qt.PenStyle.DashDotLine)
                painter.setPen(pen)
                for row in range(1, self.rows):
                    y = top + wall_h * row / self.rows
                    painter.drawLine(
                        int(left), int(y), int(left + wall_w), int(y)
                    )
            else:
                # Smeared web reinforcement remains a light guide field.
                painter.setPen(QPen(QColor("#9bb7d1"), 1.0))
                web_left = left + boundary_px
                web_right = left + wall_w - boundary_px
                for index in range(1, 6):
                    y = top + wall_h * index / 6.0
                    painter.drawLine(
                        int(web_left), int(y),
                        int(web_right), int(y),
                    )

        if (
            self.reinforcement_mode in {"hybrid", "fully_discrete"}
            and self.web_vertical_mode == "embedded"
        ):
            diameter = self.web_vertical_bar_diameter
            local_left = (
                self.boundary_value
                + self.web_vertical_edge_offset
                + 0.5 * diameter
            )
            local_right = (
                self.width_value
                - self.boundary_value
                - self.web_vertical_edge_offset
                - 0.5 * diameter
            )
            if local_right >= local_left:
                local_span = local_right - local_left
                intervals = (
                    max(
                        1,
                        int(
                            math.ceil(
                                local_span / self.web_vertical_spacing
                            )
                        ),
                    )
                    if local_span > 1.0e-12
                    else 1
                )
                positions = (
                    [local_left]
                    if local_span <= 1.0e-12
                    else [
                        local_left + local_span * index / intervals
                        for index in range(intervals + 1)
                    ]
                )
                layers = (
                    ("front", "back")
                    if self.web_vertical_layer_mode == "front_back"
                    else ("center",)
                )
                for layer_index, layer_name in enumerate(layers):
                    pen = QPen(
                        QColor(
                            "#188977"
                            if layer_name != "back"
                            else "#12685b"
                        ),
                        1.9,
                    )
                    if layer_name == "back":
                        pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    shift = 1.5 * layer_index
                    for value in positions:
                        x = left + value * scale + shift
                        painter.drawLine(
                            int(x), int(top),
                            int(x), int(top + wall_h),
                        )

                if "web_vertical" in self.warning_keys:
                    painter.setPen(QPen(QColor("#c62828"), 2.2))
                    painter.drawRect(
                        int(left + boundary_px),
                        int(top),
                        int(max(wall_w - 2.0 * boundary_px, 1.0)),
                        int(wall_h),
                    )

        painter.setPen(QPen(QColor("#26394c"), 2.2))
        painter.drawLine(
            int(left),
            int(top + wall_h),
            int(left + wall_w),
            int(top + wall_h),
        )

        # Compact engineering-style annotations for the pre-generation view.
        dim_pen = QPen(QColor("#52677b"), 1.0)
        painter.setPen(dim_pen)
        dim_y = top + wall_h + 18.0
        painter.drawLine(
            int(left), int(dim_y), int(left + wall_w), int(dim_y)
        )
        painter.drawLine(
            int(left), int(dim_y - 5.0), int(left), int(dim_y + 5.0)
        )
        painter.drawLine(
            int(left + wall_w), int(dim_y - 5.0),
            int(left + wall_w), int(dim_y + 5.0)
        )
        painter.drawText(
            int(left),
            int(dim_y + 16.0),
            f"W = {self.width_value:g}",
        )

        dim_x = left - 18.0
        painter.drawLine(
            int(dim_x), int(top), int(dim_x), int(top + wall_h)
        )
        painter.drawLine(
            int(dim_x - 5.0), int(top), int(dim_x + 5.0), int(top)
        )
        painter.drawLine(
            int(dim_x - 5.0), int(top + wall_h),
            int(dim_x + 5.0), int(top + wall_h)
        )
        painter.save()
        painter.translate(int(dim_x - 8.0), int(top + wall_h / 2.0))
        painter.rotate(-90.0)
        painter.drawText(0, 0, f"H = {self.height_value:g}")
        painter.restore()

        painter.setPen(QPen(QColor("#40566c"), 1.0))
        painter.drawText(
            int(left + 4.0),
            int(max(top - 10.0, 12.0)),
            (
                f"t = {self.thickness_value:g} · "
                f"B = {self.boundary_value:g} · "
                f"{self.rows} {self.formulation} row(s) · "
                f"{self.fibers} fibers"
            ),
        )

        if self.detailed_annotations:
            # Boundary-width dimensions at the top of the wall.
            boundary_dim_y = max(top - 25.0, 14.0)
            painter.setPen(QPen(QColor("#52677b"), 1.0))
            painter.drawLine(
                int(left), int(boundary_dim_y),
                int(left + boundary_px), int(boundary_dim_y),
            )
            painter.drawLine(
                int(left + wall_w - boundary_px),
                int(boundary_dim_y),
                int(left + wall_w), int(boundary_dim_y),
            )
            painter.drawText(
                int(left + 2.0),
                int(boundary_dim_y - 3.0),
                f"B={self.boundary_value:g}",
            )
            painter.drawText(
                int(left + wall_w - boundary_px + 2.0),
                int(boundary_dim_y - 3.0),
                f"B={self.boundary_value:g}",
            )

            row_height = self.height_value / max(self.rows, 1)
            painter.drawText(
                int(left + wall_w + 8.0),
                int(top + wall_h / 2.0),
                f"Δh≈{row_height:g}",
            )

            if (
                self.reinforcement_mode == "hybrid"
                and self.boundary_bars
            ):
                painter.setPen(QPen(QColor("#d64545"), 1.0))
                painter.drawText(
                    int(left + 5.0),
                    int(top + 16.0),
                    f"cover={self.boundary_cover:g}",
                )
                painter.drawText(
                    int(left + wall_w - boundary_px + 5.0),
                    int(top + 16.0),
                    f"{self.boundary_bars} bars",
                )

        painter.end()


class RCWallWizard(QWizard):
    """Create RC walls with MEFI/RCLMS or OpenSees MVLEM formulations."""

    def __init__(
        self,
        project: ProjectDatabase,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)
        self._applying_preset = False
        self._verified_material_records = {
            record.id: record
            for record in load_verified_material_library()
        }
        self._rw_a20_hidden_parameters: dict[str, dict[str, float]] = {}
        self.setWindowTitle("RC Wall Wizard · MEFI / MVLEM Family")
        self.resize(760, 650)
        self.setOption(
            QWizard.WizardOption.NoBackButtonOnStartPage,
            True,
        )
        self.setButtonText(
            QWizard.WizardButton.FinishButton,
            "Create Wall",
        )

        self._build_geometry_page()
        self._build_concrete_page()
        self._build_reinforcement_page()
        self._build_review_page()

        self.currentIdChanged.connect(self._page_changed)
        self._apply_rw_a20_preset()
        self._sync_wall_formulation()
        self._update_review()

    def _page_changed(self, _page: int) -> None:
        self._update_review()
        page_to_scroll = {
            0: getattr(self, "geometry_scroll", None),
            1: getattr(self, "concrete_scroll", None),
            2: getattr(self, "reinforcement_scroll", None),
            3: getattr(self, "preview_scroll", None),
        }
        scroll = page_to_scroll.get(int(_page))
        if scroll is not None:
            scroll.verticalScrollBar().setValue(0)

    def _stress_display(self, value_pa: float) -> float:
        return self.units.engineering_stress_from_pa(value_pa)

    def _stress_store(self, value: float) -> float:
        return self.units.engineering_stress_to_pa(value)

    def _scrollable_page_body(
        self,
        page: QWizardPage,
        name: str,
    ) -> QWidget:
        """Keep wizard navigation fixed while page content scrolls vertically."""
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(page)
        scroll.setObjectName(f"rc-wall-{name}-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        body = QWidget()
        body.setObjectName(f"rc-wall-{name}-scroll-body")
        scroll.setWidget(body)
        outer.addWidget(scroll)

        setattr(self, f"{name}_scroll", scroll)
        return body

    def _build_geometry_page(self) -> None:
        page = QWizardPage()
        page.setTitle("1 · Geometry & discretization")
        page.setSubTitle(
            "Choose the OpenSees wall formulation first. MEFI/RCLMS uses "
            "two edge-node chains; MVLEM and SFI_MVLEM use a centerline "
            "macro-element stack. MVLEM_3D uses four-node wall panels in "
            "an ndm=3 / ndf=6 project."
        )
        body = self._scrollable_page_body(page, "geometry")
        layout = QVBoxLayout(body)
        form = QFormLayout()

        self.preset = QComboBox()
        self.preset.addItem(
            "RW-A20-P10-S38 · wall-only benchmark preset",
            "rw-a20",
        )
        self.preset.addItem(
            "Custom · exposed inputs override current starter values",
            "custom",
        )
        self.preset.currentIndexChanged.connect(self._preset_changed)
        form.addRow("Preset:", self.preset)

        self.formulation = QComboBox()
        self.formulation.addItem(
            "MEFI / RCLMS · detailed membrane-fiber wall",
            "MEFI",
        )
        self.formulation.addItem(
            "MVLEM · 2D macro-element stack",
            "MVLEM",
        )
        self.formulation.addItem(
            "SFI_MVLEM · 2D shear-flexure interaction stack",
            "SFI_MVLEM",
        )
        self.formulation.addItem(
            "MVLEM_3D · 3D four-node wall-panel stack",
            "MVLEM_3D",
        )
        self.formulation.currentIndexChanged.connect(
            self._wall_formulation_changed
        )
        form.addRow("Wall formulation:", self.formulation)

        self.wall_name = QLineEdit("RC Wall")
        self.replace_geometry = QCheckBox(
            "Replace current model geometry and model-linked data"
        )
        self.replace_geometry.setChecked(True)
        form.addRow("Wall name:", self.wall_name)
        form.addRow("", self.replace_geometry)

        self.width = _double(1220.0, 1.0e-9)
        self.height = _double(2209.8, 1.0e-9)
        self.thickness = _double(152.4, 1.0e-9)
        self.boundary_width = _double(228.6, 1.0e-9)
        self.origin_x = _double(0.0)
        self.origin_y = _double(0.0)
        self.vertical_elements = QSpinBox()
        self.vertical_elements.setRange(1, 1000)
        self.vertical_elements.setValue(7)
        self.macro_fibers = QSpinBox()
        self.macro_fibers.setRange(3, 100)
        self.macro_fibers.setValue(8)

        length = self.units.length
        form.addRow(f"Wall width [{length}]:", self.width)
        form.addRow(f"Wall height [{length}]:", self.height)
        form.addRow(f"Wall thickness [{length}]:", self.thickness)
        form.addRow(f"Boundary width each side [{length}]:", self.boundary_width)
        form.addRow(f"Origin X [{length}]:", self.origin_x)
        form.addRow(f"Origin Y [{length}]:", self.origin_y)
        form.addRow("Vertical wall elements:", self.vertical_elements)
        form.addRow("Macro-fibers per wall element:", self.macro_fibers)
        layout.addLayout(form)

        note = QLabel(
            "Macro-fiber mapping is always Boundary | Web ... Web | Boundary. "
            "The web fiber widths are calculated automatically so the sum of "
            "all widths equals the wall width."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        layout.addWidget(note)
        self.preview = RCWallPreview()
        layout.addWidget(self.preview)
        layout.addStretch(1)

        self.wall_name.textChanged.connect(
            lambda _text: self._update_review()
        )
        self.replace_geometry.toggled.connect(
            lambda _checked: self._update_review()
        )

        for widget in (
            self.width,
            self.height,
            self.thickness,
            self.boundary_width,
            self.origin_x,
            self.origin_y,
            self.vertical_elements,
            self.macro_fibers,
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(
                    lambda _value: self._geometry_changed()
                )

        self.addPage(page)

    def _build_concrete_page(self) -> None:
        page = QWizardPage()
        page.setTitle("2 · Concrete")
        page.setSubTitle(
            "Concrete02 creates the uniaxial laws; OrthotropicRAConcrete "
            "wraps them into plane-stress concrete layers."
        )
        body = self._scrollable_page_body(page, "concrete")
        form = QFormLayout(body)
        stress = self.units.engineering_stress_label

        self.fc_web = _double(47.09, 0.0)
        self.eps_web = _double(-0.00232, -1.0, -1.0e-12, 8)
        self.fc_boundary = _double(53.78, 0.0)
        self.eps_boundary = _double(-0.00397, -1.0, -1.0e-12, 8)
        self.ft = _double(2.13, 0.0)
        self.cracking_strain = _double(0.00008, 1.0e-12, 1.0, 8)
        self.damage1 = _double(0.175, 0.0, 10.0, 6)
        self.damage2 = _double(0.5, 0.0, 10.0, 6)
        self.unconfined_layer = _double(50.8, 1.0e-9)

        form.addRow(f"Web |f'c| [{stress}]:", self.fc_web)
        form.addRow("Web peak compression strain:", self.eps_web)
        form.addRow(f"Boundary |f'cc| [{stress}]:", self.fc_boundary)
        form.addRow("Boundary peak compression strain:", self.eps_boundary)
        form.addRow(f"Concrete tensile strength ft [{stress}]:", self.ft)
        form.addRow("Tension cracking strain ecr:", self.cracking_strain)
        form.addRow("Cyclic damage constant 1:", self.damage1)
        form.addRow("Cyclic damage constant 2:", self.damage2)
        form.addRow(
            f"Boundary unconfined layer [{self.units.length}]:",
            self.unconfined_layer,
        )

        note = QLabel(
            "Boundary confined thickness = wall thickness − unconfined layer. "
            "The wizard creates one web RCLMS concrete layer and two boundary "
            "layers (unconfined + confined). Created materials remain fully "
            "editable after generation."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        form.addRow(note)

        self.reinforcement_info = QLabel()
        self.reinforcement_info.setWordWrap(True)
        self.reinforcement_info.setStyleSheet(
            "padding: 8px; background: #f7f9fb; color: #26394c;"
        )
        form.addRow("Calculated information:", self.reinforcement_info)

        for widget in (
            self.fc_web,
            self.eps_web,
            self.fc_boundary,
            self.eps_boundary,
            self.ft,
            self.cracking_strain,
            self.damage1,
            self.damage2,
            self.unconfined_layer,
        ):
            widget.valueChanged.connect(
                lambda _value: self._mark_custom()
            )

        self.addPage(page)

    def _build_reinforcement_page(self) -> None:
        page = QWizardPage()
        page.setTitle("3 · Reinforcement")
        page.setSubTitle(
            "Steel02 supplies the uniaxial steel laws. "
            "SmearedSteelDoubleLayer converts reinforcement ratios to "
            "the membrane representation used by RCLMS."
        )
        body = self._scrollable_page_body(page, "reinforcement")
        form = QFormLayout(body)
        stress = self.units.engineering_stress_label

        self.steel_E = _double(200000.0, 1.0e-9)
        self.fy_x = _double(469.93, 0.0)
        self.fy_y_web = _double(409.71, 0.0)
        self.fy_y_boundary = _double(429.78, 0.0)

        self.rho_x_web = _double(0.27, 0.0, 100.0, 4)
        self.rho_y_web = _double(0.27, 0.0, 100.0, 4)
        self.rho_x_boundary = _double(0.82, 0.0, 100.0, 4)
        self.rho_y_boundary = _double(3.23, 0.0, 100.0, 4)

        self.reinforcement_mode = QComboBox()
        self.reinforcement_mode.addItem(
            "Smeared · RCLMS only",
            "smeared",
        )
        self.reinforcement_mode.addItem(
            "Hybrid · selected discrete reinforcement",
            "hybrid",
        )
        self.reinforcement_mode.addItem(
            "Fully Discrete · all reinforcement as bars",
            "fully_discrete",
        )
        self.boundary_bar_count = QSpinBox()
        self.boundary_bar_count.setRange(1, 200)
        self.boundary_bar_count.setValue(4)
        self.boundary_bar_diameter = _double(16.0, 1.0e-9)
        self.boundary_layer_mode = QComboBox()
        self.boundary_layer_mode.addItem(
            "Front + Back faces",
            "front_back",
        )
        self.boundary_layer_mode.addItem(
            "Single centerline layer",
            "single",
        )
        self.boundary_cover = _double(30.0, 0.0)

        self.web_horizontal_mode = QComboBox()
        self.web_horizontal_mode.addItem(
            "Smeared in RCLMS",
            "smeared",
        )
        self.web_horizontal_mode.addItem(
            "Discrete · MEFI mesh-aligned rows",
            "mesh_aligned",
        )
        self.web_horizontal_bar_diameter = _double(8.0, 1.0e-9)
        self.web_horizontal_layer_mode = QComboBox()
        self.web_horizontal_layer_mode.addItem(
            "Front + Back faces",
            "front_back",
        )
        self.web_horizontal_layer_mode.addItem(
            "Single centerline layer",
            "single",
        )

        self.web_vertical_mode = QComboBox()
        self.web_vertical_mode.addItem(
            "Smeared in RCLMS",
            "smeared",
        )
        self.web_vertical_mode.addItem(
            "Discrete · Embedded independent bars",
            "embedded",
        )
        self.web_vertical_bar_diameter = _double(6.0, 1.0e-9)
        self.web_vertical_spacing = _double(200.0, 1.0e-9)
        self.web_vertical_edge_offset = _double(50.0, 0.0)
        self.web_vertical_layer_mode = QComboBox()
        self.web_vertical_layer_mode.addItem(
            "Front + Back faces",
            "front_back",
        )
        self.web_vertical_layer_mode.addItem(
            "Single centerline layer",
            "single",
        )
        self.embedded_penalty_factor = _double(
            1.0, 1.0e-6, 1.0e6, 4
        )

        self.boundary_truss_type = QComboBox()
        self.boundary_truss_type.addItem("CorotTruss", "corotTruss")
        self.boundary_truss_type.addItem("Truss", "truss")

        form.addRow(f"Steel modulus Es [{stress}]:", self.steel_E)
        form.addRow(f"Steel X fy [{stress}]:", self.fy_x)
        form.addRow(f"Steel Y web fy [{stress}]:", self.fy_y_web)
        form.addRow(
            f"Steel Y boundary fy [{stress}]:",
            self.fy_y_boundary,
        )
        form.addRow("Web ρx [%]:", self.rho_x_web)
        form.addRow("Web ρy [%]:", self.rho_y_web)
        form.addRow("Boundary ρx [%]:", self.rho_x_boundary)
        form.addRow("Boundary ρy total [%]:", self.rho_y_boundary)
        form.addRow("Reinforcement model:", self.reinforcement_mode)
        form.addRow(
            "Longitudinal bars / boundary zone:",
            self.boundary_bar_count,
        )
        form.addRow(
            f"Boundary bar diameter [{self.units.length}]:",
            self.boundary_bar_diameter,
        )
        form.addRow("Boundary layers:", self.boundary_layer_mode)
        form.addRow(
            f"Boundary clear cover [{self.units.length}]:",
            self.boundary_cover,
        )
        form.addRow(
            "Horizontal web steel:",
            self.web_horizontal_mode,
        )
        form.addRow(
            f"Horizontal bar diameter [{self.units.length}]:",
            self.web_horizontal_bar_diameter,
        )
        form.addRow(
            "Horizontal layers:",
            self.web_horizontal_layer_mode,
        )
        form.addRow(
            "Vertical web steel:",
            self.web_vertical_mode,
        )
        form.addRow(
            f"Vertical bar diameter [{self.units.length}]:",
            self.web_vertical_bar_diameter,
        )
        form.addRow(
            f"Vertical target spacing [{self.units.length}]:",
            self.web_vertical_spacing,
        )
        form.addRow(
            f"Vertical edge offset [{self.units.length}]:",
            self.web_vertical_edge_offset,
        )
        form.addRow(
            "Vertical layers:",
            self.web_vertical_layer_mode,
        )
        form.addRow(
            "Embedded penalty factor:",
            self.embedded_penalty_factor,
        )
        form.addRow(
            "Discrete element formulation:",
            self.boundary_truss_type,
        )

        self.macro_center_ratio = _double(0.4, 0.0, 1.0, 6)
        self.macro_density = _double(0.0, 0.0, 1.0e20, 6)
        self.macro_thick_mod = _double(0.63, 1.0e-9, 1.0e6, 6)
        self.macro_poisson = _double(
            0.25, -0.999999, 0.499999, 6
        )
        self.macro_shear_material = QComboBox()
        self.macro_shear_material.addItem(
            "Select existing uniaxial shear material…",
            None,
        )
        for tag in sorted(self.project.materials):
            material = self.project.materials[tag]
            self.macro_shear_material.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                int(tag),
            )

        self.macro_web_fsam = QComboBox()
        self.macro_boundary_fsam = QComboBox()
        for combo, role in (
            (self.macro_web_fsam, "web"),
            (self.macro_boundary_fsam, "boundary"),
        ):
            combo.addItem(f"Select {role} FSAM nD material…", None)
            for tag in sorted(self.project.nd_materials):
                material = self.project.nd_materials[tag]
                if material.material_type != "FSAM":
                    continue
                combo.addItem(
                    f"{tag} - {material.name} (FSAM)",
                    int(tag),
                )

        form.addRow("Macro CoR ratio c:", self.macro_center_ratio)
        form.addRow("Macro density:", self.macro_density)
        form.addRow("MVLEM_3D ThickMod:", self.macro_thick_mod)
        form.addRow("MVLEM_3D Poisson ν:", self.macro_poisson)
        form.addRow("MVLEM / MVLEM_3D shear material:", self.macro_shear_material)
        form.addRow("SFI_MVLEM web FSAM:", self.macro_web_fsam)
        form.addRow("SFI_MVLEM boundary FSAM:", self.macro_boundary_fsam)

        self.macro_dependency_note = QLabel(
            "MVLEM creates its Concrete02/Steel02 fiber materials from the "
            "wizard values and reuses one existing uniaxial shear material. "
            "SFI_MVLEM reuses existing FSAM nD materials for web/boundary "
            "macro-fibers."
        )
        self.macro_dependency_note.setWordWrap(True)
        self.macro_dependency_note.setStyleSheet(
            "padding: 8px; background: #fff7e0; color: #6e5200;"
        )
        form.addRow(self.macro_dependency_note)

        note = QLabel(
            "Hybrid moves only the selected reinforcement into discrete "
            "bars. Fully Discrete moves all target ρx/ρy into truss bars and "
            "sets the RCLMS smeared steel ratios to zero. In the current "
            "2D MEFI formulation the physical bars still share each boundary "
            "edge node chain (perfect bond); front/back and cover are shown "
            "schematically in the viewport. Horizontal web bars can also be "
            "discretized on existing internal MEFI node rows, with their rho-x "
            "automatically removed from smeared RCLMS steel. Vertical web bars "
            "may use independent steel nodes coupled to the MEFI host through "
            "ASDEmbeddedNodeElement interpolation. Fully Discrete auto-sizes "
            "equivalent FE bar areas from the target reinforcement ratios and "
            "uses segmented horizontal bars so web and boundary rho-x may differ."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        form.addRow(note)

        for widget in (
            self.steel_E,
            self.fy_x,
            self.fy_y_web,
            self.fy_y_boundary,
            self.rho_x_web,
            self.rho_y_web,
            self.rho_x_boundary,
            self.rho_y_boundary,
            self.boundary_bar_count,
            self.boundary_bar_diameter,
            self.boundary_cover,
            self.web_horizontal_bar_diameter,
            self.web_vertical_bar_diameter,
            self.web_vertical_spacing,
            self.web_vertical_edge_offset,
            self.embedded_penalty_factor,
        ):
            widget.valueChanged.connect(
                lambda _value: self._mark_custom()
            )
        self.reinforcement_mode.currentIndexChanged.connect(
            self._reinforcement_mode_changed
        )
        self.boundary_truss_type.currentIndexChanged.connect(
            lambda _index: self._mark_custom()
        )
        self.macro_center_ratio.valueChanged.connect(
            lambda _value: self._mark_custom()
        )
        self.macro_density.valueChanged.connect(
            lambda _value: self._mark_custom()
        )
        self.macro_thick_mod.valueChanged.connect(
            lambda _value: self._mark_custom()
        )
        self.macro_poisson.valueChanged.connect(
            lambda _value: self._mark_custom()
        )
        self.macro_shear_material.currentIndexChanged.connect(
            lambda _index: self._update_review()
        )
        self.macro_web_fsam.currentIndexChanged.connect(
            lambda _index: self._update_review()
        )
        self.macro_boundary_fsam.currentIndexChanged.connect(
            lambda _index: self._update_review()
        )
        self.boundary_layer_mode.currentIndexChanged.connect(
            lambda _index: self._reinforcement_layout_changed()
        )
        self.web_horizontal_mode.currentIndexChanged.connect(
            lambda _index: self._reinforcement_layout_changed()
        )
        self.web_horizontal_layer_mode.currentIndexChanged.connect(
            lambda _index: self._reinforcement_layout_changed()
        )
        self.web_vertical_mode.currentIndexChanged.connect(
            lambda _index: self._reinforcement_layout_changed()
        )
        self.web_vertical_layer_mode.currentIndexChanged.connect(
            lambda _index: self._reinforcement_layout_changed()
        )
        self.boundary_bar_count.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.boundary_bar_diameter.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.boundary_cover.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.web_horizontal_bar_diameter.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.web_vertical_bar_diameter.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.web_vertical_spacing.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.web_vertical_edge_offset.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.rho_y_boundary.valueChanged.connect(
            lambda _value: self._update_reinforcement_info()
        )
        self.rho_y_web.valueChanged.connect(
            lambda _value: self._update_reinforcement_info()
        )
        self.rho_x_web.valueChanged.connect(
            lambda _value: self._update_reinforcement_info()
        )
        self.rho_x_boundary.valueChanged.connect(
            lambda _value: self._update_reinforcement_info()
        )
        self._sync_reinforcement_mode()

        self.addPage(page)

    def _reinforcement_mode_changed(self, *_args) -> None:
        self._mark_custom()
        self._sync_reinforcement_mode()

    def _reinforcement_layout_changed(self) -> None:
        self._mark_custom()
        self._sync_reinforcement_mode()

    def _sync_reinforcement_mode(self) -> None:
        mode = str(self.reinforcement_mode.currentData())
        enabled = mode in {"hybrid", "fully_discrete"}
        fully_discrete = mode == "fully_discrete"

        self.boundary_bar_count.setEnabled(enabled)
        self.boundary_bar_diameter.setEnabled(
            enabled and not fully_discrete
        )
        self.boundary_layer_mode.setEnabled(enabled)
        self.boundary_cover.setEnabled(enabled)
        self.boundary_truss_type.setEnabled(enabled)

        # Sub-mode selectors are meaningful only for Hybrid. Fully Discrete
        # always uses segmented horizontal bars + embedded vertical bars.
        self.web_horizontal_mode.setEnabled(
            enabled and not fully_discrete
        )
        self.web_vertical_mode.setEnabled(
            enabled and not fully_discrete
        )

        horizontal_enabled = (
            enabled
            and (
                fully_discrete
                or self.web_horizontal_mode.currentData() == "mesh_aligned"
            )
        )
        self.web_horizontal_bar_diameter.setEnabled(
            horizontal_enabled and not fully_discrete
        )
        self.web_horizontal_layer_mode.setEnabled(horizontal_enabled)

        vertical_enabled = (
            enabled
            and (
                fully_discrete
                or self.web_vertical_mode.currentData() == "embedded"
            )
        )
        self.web_vertical_bar_diameter.setEnabled(
            vertical_enabled and not fully_discrete
        )
        self.web_vertical_spacing.setEnabled(vertical_enabled)
        self.web_vertical_edge_offset.setEnabled(vertical_enabled)
        self.web_vertical_layer_mode.setEnabled(vertical_enabled)
        self.embedded_penalty_factor.setEnabled(vertical_enabled)

        if fully_discrete:
            horizontal_index = self.web_horizontal_mode.findData(
                "mesh_aligned"
            )
            if horizontal_index >= 0:
                self.web_horizontal_mode.blockSignals(True)
                self.web_horizontal_mode.setCurrentIndex(horizontal_index)
                self.web_horizontal_mode.blockSignals(False)
            vertical_index = self.web_vertical_mode.findData("embedded")
            if vertical_index >= 0:
                self.web_vertical_mode.blockSignals(True)
                self.web_vertical_mode.setCurrentIndex(vertical_index)
                self.web_vertical_mode.blockSignals(False)

        self._update_reinforcement_info()
        self._update_preview()
        self._update_review()

    def _vertical_web_metrics(self) -> dict[str, object]:
        spec = self.data()
        summary = rc_wall_reinforcement_summary(spec)
        positions = tuple(summary["web_vertical_positions"])
        return {
            "positions": positions,
            "bar_count_per_layer": len(positions),
            "layers": (
                2
                if self.web_vertical_layer_mode.currentData() == "front_back"
                else 1
            ),
            "bar_area": float(summary["web_vertical_bar_area"]),
            "equivalent_diameter": float(
                summary["web_vertical_equivalent_diameter"]
            ),
            "actual_spacing": float(
                summary["web_vertical_actual_spacing"]
            ),
            "discrete_rho": float(
                summary["web_vertical_discrete_rho_y"]
            ),
            "remaining_rho": (
                float(spec.rho_y_web)
                - float(summary["web_vertical_discrete_rho_y"])
            ),
            "fits": bool(positions),
        }

    def _update_reinforcement_info(self) -> None:
        if not hasattr(self, "reinforcement_info"):
            return
        mode = str(self.reinforcement_mode.currentData())
        if mode == "fully_discrete":
            spec = self.data()
            summary = rc_wall_reinforcement_summary(spec)
            boundary_layers = (
                2
                if self.boundary_layer_mode.currentData() == "front_back"
                else 1
            )
            vertical_layers = (
                2
                if self.web_vertical_layer_mode.currentData() == "front_back"
                else 1
            )
            self.reinforcement_info.setText(
                "<b>Fully Discrete reinforcement</b><br>"
                "All target reinforcement ratios are carried by truss bars; "
                "RCLMS smeared steel ratios = 0.<br>"
                f"Boundary Y: {self.boundary_bar_count.value()} bars/zone · "
                f"{boundary_layers} layer(s) · "
                f"equiv. Ø{float(summary['boundary_equivalent_diameter']):g} "
                f"{self.units.length} · "
                f"s≈{float(summary['boundary_bar_spacing']):g} "
                f"{self.units.length}<br>"
                f"Web Y: {len(summary['web_vertical_positions'])} "
                f"bars/layer × {vertical_layers} layer(s) · "
                f"equiv. Ø"
                f"{float(summary['web_vertical_equivalent_diameter']):g} "
                f"{self.units.length} · "
                f"s≈{float(summary['web_vertical_actual_spacing']):g} "
                f"{self.units.length}<br>"
                f"Horizontal X: {int(summary['horizontal_line_count'])} "
                f"internal row(s) × "
                f"{int(summary['horizontal_layer_count'])} layer(s)<br>"
                f"Web segment equiv. Ø"
                f"{float(summary['web_horizontal_equivalent_diameter']):g} "
                f"{self.units.length} · "
                f"Boundary segment equiv. Ø"
                f"{float(summary['boundary_horizontal_equivalent_diameter']):g} "
                f"{self.units.length}<br>"
                f"ρ targets represented discretely: "
                f"web X={100.0 * float(spec.rho_x_web):.4g}% · "
                f"web Y={100.0 * float(spec.rho_y_web):.4g}% · "
                f"boundary X={100.0 * float(spec.rho_x_boundary):.4g}% · "
                f"boundary Y={100.0 * float(spec.rho_y_boundary):.4g}%<br>"
                f"Embedded penalty K≈"
                f"{self._stress_display(float(summary['embedded_penalty'])):g} "
                f"{self.units.engineering_stress_label}"
            )
            return

        if mode != "hybrid":
            self.reinforcement_info.setText(
                "All reinforcement is represented by RCLMS smeared ratios."
            )
            return

        count = int(self.boundary_bar_count.value())
        diameter = float(self.boundary_bar_diameter.value())
        cover = float(self.boundary_cover.value())
        boundary = float(self.boundary_width.value())
        thickness = float(self.thickness.value())
        bar_area = math.pi * diameter * diameter / 4.0
        area = count * bar_area
        gross = boundary * thickness
        discrete_ratio = area / gross if gross > 0.0 else 0.0
        total_ratio = float(self.rho_y_boundary.value()) / 100.0
        remaining = total_ratio - discrete_ratio

        layer_mode = str(self.boundary_layer_mode.currentData())
        per_layer = (
            count // 2 if layer_mode == "front_back" else count
        )
        clear_span = max(
            boundary - 2.0 * cover - diameter,
            0.0,
        )
        spacing = (
            clear_span / (per_layer - 1)
            if per_layer > 1
            else 0.0
        )

        warning_parts: list[str] = []
        if remaining < -1.0e-12:
            warning_parts.append(
                "Discrete boundary steel exceeds total boundary rho-y."
            )
        if layer_mode == "front_back" and count % 2:
            warning_parts.append(
                "Front/back layout requires an even total boundary bar count."
            )
        if 2.0 * cover + diameter > boundary + 1.0e-12:
            warning_parts.append(
                "Cover + bar diameter do not fit the boundary-zone width."
            )
        if (
            layer_mode == "front_back"
            and 2.0 * cover + diameter > thickness + 1.0e-12
        ):
            warning_parts.append(
                "Cover + bar diameter do not fit through wall thickness."
            )

        horizontal_text = "Horizontal web steel: smeared"
        if self.web_horizontal_mode.currentData() == "mesh_aligned":
            h_diameter = float(self.web_horizontal_bar_diameter.value())
            h_area = math.pi * h_diameter * h_diameter / 4.0
            h_layers = (
                2
                if self.web_horizontal_layer_mode.currentData()
                == "front_back"
                else 1
            )
            h_lines = max(int(self.vertical_elements.value()) - 1, 0)
            h_rho = (
                h_lines * h_layers * h_area
                / (
                    float(self.height.value())
                    * thickness
                )
                if float(self.height.value()) > 0.0 and thickness > 0.0
                else 0.0
            )
            web_remaining = (
                float(self.rho_x_web.value()) / 100.0 - h_rho
            )
            boundary_x_remaining = (
                float(self.rho_x_boundary.value()) / 100.0 - h_rho
            )
            if web_remaining < -1.0e-12 or boundary_x_remaining < -1.0e-12:
                warning_parts.append(
                    "Discrete horizontal bars exceed available rho-x."
                )
            mesh_spacing = (
                float(self.height.value())
                / max(int(self.vertical_elements.value()), 1)
            )
            horizontal_text = (
                f"Horizontal discrete: {h_lines} internal rows × "
                f"{h_layers} layer(s) × Ø{h_diameter:g}; "
                f"mesh spacing ≈ {mesh_spacing:g} {self.units.length}; "
                f"ρx,discrete = {100.0 * h_rho:.4g}%"
            )

        vertical_text = "Vertical web steel: smeared"
        if self.web_vertical_mode.currentData() == "embedded":
            vertical = self._vertical_web_metrics()
            if not bool(vertical["fits"]):
                warning_parts.append(
                    "No embedded vertical web bar fits between boundary zones."
                )
            if float(vertical["remaining_rho"]) < -1.0e-12:
                warning_parts.append(
                    "Embedded vertical bars exceed available web rho-y."
                )
            concrete_tangent = (
                2.0
                * abs(float(self.fc_web.value()))
                / max(abs(float(self.eps_web.value())), 1.0e-12)
            )
            penalty_display = (
                concrete_tangent
                * float(self.embedded_penalty_factor.value())
            )
            vertical_text = (
                f"Vertical embedded: "
                f"{int(vertical['bar_count_per_layer'])} bars/layer × "
                f"{int(vertical['layers'])} layer(s) × "
                f"Ø{self.web_vertical_bar_diameter.value():g}; "
                f"target ≤ {self.web_vertical_spacing.value():g} "
                f"{self.units.length}; actual ≈ "
                f"{float(vertical['actual_spacing']):g} "
                f"{self.units.length}; ρy,discrete = "
                f"{100.0 * float(vertical['discrete_rho']):.4g}% · "
                f"ρy,smeared remaining = "
                f"{100.0 * max(float(vertical['remaining_rho']), 0.0):.4g}%; "
                f"K≈{penalty_display:g} "
                f"{self.units.engineering_stress_label}"
            )

        warning = "".join(
            f"<br><b style='color:#b42318'>{message}</b>"
            for message in warning_parts
        )
        layer_label = (
            "Front + Back"
            if layer_mode == "front_back"
            else "Single centerline"
        )
        self.reinforcement_info.setText(
            f"<b>Each boundary zone</b><br>"
            f"As,bar = {bar_area:g} {self.units.length}² · "
            f"As,total = {area:g} {self.units.length}² "
            f"({count} × Ø{diameter:g})<br>"
            f"Layers = {layer_label} · bars/layer = {per_layer}<br>"
            f"Clear cover = {cover:g} {self.units.length} · "
            f"center spacing ≈ {spacing:g} {self.units.length}<br>"
            f"ρy,discrete = {100.0 * discrete_ratio:.4g}% · "
            f"ρy,smeared remaining = "
            f"{100.0 * max(remaining, 0.0):.4g}%<br>"
            f"{horizontal_text}<br>"
            f"{vertical_text}"
            + warning
        )

    def _build_review_page(self) -> None:
        page = QWizardPage()
        page.setTitle("4 · Preview & Create Wall")
        page.setSubTitle(
            "Review the exact wall layout and the FEWIZ objects that will be "
            "created before accepting the wizard."
        )
        body = self._scrollable_page_body(page, "preview")
        layout = QVBoxLayout(body)

        preview_row = QHBoxLayout()
        preview_column = QVBoxLayout()
        self.final_preview = RCWallPreview()
        self.final_preview.setMinimumSize(390, 350)
        preview_column.addWidget(self.final_preview, 1)

        self.preview_legend = QLabel(
            "<b>Legend</b> · "
            "<span style='color:#8fa3b5'>■</span> Concrete / web · "
            "<span style='color:#7897b5'>■</span> Boundary zone · "
            "<span style='color:#d64545'>━</span> Boundary bars · "
            "<span style='color:#2f80c9'>━</span> Horizontal web bars · "
            "<span style='color:#188977'>━</span> Embedded vertical bars · "
            "<span style='color:#26394c'>━</span> MEFI mesh"
        )
        self.preview_legend.setWordWrap(True)
        self.preview_legend.setStyleSheet(
            "padding: 7px; background: #f7f9fb; color: #40566c;"
        )
        preview_column.addWidget(self.preview_legend)
        preview_row.addLayout(preview_column, 3)

        summary_column = QVBoxLayout()
        self.preview_geometry_summary = QLabel()
        self.preview_geometry_summary.setWordWrap(True)
        self.preview_geometry_summary.setStyleSheet(
            "padding: 10px; background: #f7f9fb; color: #26394c;"
        )
        summary_column.addWidget(self.preview_geometry_summary)

        self.preview_object_summary = QLabel()
        self.preview_object_summary.setWordWrap(True)
        self.preview_object_summary.setStyleSheet(
            "padding: 10px; background: #eef4fb; color: #26394c;"
        )
        summary_column.addWidget(self.preview_object_summary)

        self.preview_material_summary = QLabel()
        self.preview_material_summary.setWordWrap(True)
        self.preview_material_summary.setStyleSheet(
            "padding: 10px; background: #f7f9fb; color: #26394c;"
        )
        summary_column.addWidget(self.preview_material_summary)

        self.preview_selection_summary = QLabel()
        self.preview_selection_summary.setWordWrap(True)
        self.preview_selection_summary.setStyleSheet(
            "padding: 10px; background: #f7f9fb; color: #26394c;"
        )
        summary_column.addWidget(self.preview_selection_summary)

        self.preview_validation_status = QLabel()
        self.preview_validation_status.setWordWrap(True)
        summary_column.addWidget(self.preview_validation_status)
        summary_column.addStretch(1)
        preview_row.addLayout(summary_column, 2)
        layout.addLayout(preview_row)

        self.review = QLabel()
        self.review.setWordWrap(True)
        self.review.setTextFormat(self.review.textFormat())
        self.review.setStyleSheet(
            "padding: 10px; background: #ffffff; color: #26394c;"
        )
        layout.addWidget(self.review)

        self.preview_note = QLabel(
            "Preview is generated from the current wizard inputs before the "
            "project is modified. Boundary and mesh-aligned horizontal bars "
            "use shared-node perfect bond. Embedded vertical web bars use "
            "independent steel nodes coupled to MEFI host triangles by "
            "ASDEmbeddedNodeElement; front/back separation remains schematic "
            "in this 2D wall model."
        )
        self.preview_note.setWordWrap(True)
        self.preview_note.setStyleSheet(
            "padding: 8px; background: #fff7e0; color: #7a5600;"
        )
        layout.addWidget(self.preview_note)
        self.addPage(page)

    def _mark_custom(self) -> None:
        if self._applying_preset:
            return
        custom_index = self.preset.findData("custom")
        if custom_index >= 0 and self.preset.currentIndex() != custom_index:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(custom_index)
            self.preset.blockSignals(False)
        self._update_review()

    def _geometry_changed(self) -> None:
        self._mark_custom()
        self._update_preview()

    def _wall_formulation_changed(self, *_args) -> None:
        self._sync_wall_formulation()
        self._update_preview()
        self._update_review()

    def _sync_wall_formulation(self) -> None:
        if not hasattr(self, "formulation"):
            return
        formulation = str(self.formulation.currentData())
        is_mefi = formulation == "MEFI"
        is_mvlem = formulation == "MVLEM"
        is_sfi = formulation == "SFI_MVLEM"
        is_3d = formulation == "MVLEM_3D"

        # Detailed discrete-reinforcement controls belong to the MEFI/RCLMS
        # workflow. Macro-element formulations use fiber reinforcement ratios.
        for widget in (
            getattr(self, "reinforcement_mode", None),
            getattr(self, "boundary_bar_count", None),
            getattr(self, "boundary_bar_diameter", None),
            getattr(self, "boundary_layer_mode", None),
            getattr(self, "boundary_cover", None),
            getattr(self, "web_horizontal_mode", None),
            getattr(self, "web_horizontal_bar_diameter", None),
            getattr(self, "web_horizontal_layer_mode", None),
            getattr(self, "web_vertical_mode", None),
            getattr(self, "web_vertical_bar_diameter", None),
            getattr(self, "web_vertical_spacing", None),
            getattr(self, "web_vertical_edge_offset", None),
            getattr(self, "web_vertical_layer_mode", None),
            getattr(self, "embedded_penalty_factor", None),
            getattr(self, "boundary_truss_type", None),
        ):
            if widget is not None:
                widget.setEnabled(is_mefi)

        for widget in (
            getattr(self, "macro_center_ratio", None),
            getattr(self, "macro_density", None),
        ):
            if widget is not None:
                widget.setEnabled(is_mvlem or is_sfi or is_3d)
        if hasattr(self, "macro_thick_mod"):
            self.macro_thick_mod.setEnabled(is_3d)
        if hasattr(self, "macro_poisson"):
            self.macro_poisson.setEnabled(is_3d)
        if hasattr(self, "macro_shear_material"):
            self.macro_shear_material.setEnabled(is_mvlem or is_3d)
        if hasattr(self, "macro_web_fsam"):
            self.macro_web_fsam.setEnabled(is_sfi)
        if hasattr(self, "macro_boundary_fsam"):
            self.macro_boundary_fsam.setEnabled(is_sfi)
        if hasattr(self, "macro_dependency_note"):
            self.macro_dependency_note.setVisible(not is_mefi)

        if hasattr(self, "preview_legend"):
            if is_mefi:
                self.preview_legend.setText(
                    "<b>Legend</b> · "
                    "<span style='color:#8fa3b5'>■</span> Concrete / web · "
                    "<span style='color:#7897b5'>■</span> Boundary zone · "
                    "<span style='color:#d64545'>━</span> Boundary bars · "
                    "<span style='color:#2f80c9'>━</span> Horizontal bars · "
                    "<span style='color:#188977'>━</span> Embedded bars · "
                    "<span style='color:#26394c'>━</span> MEFI mesh"
                )
            elif is_3d:
                self.preview_legend.setText(
                    "<b>Legend</b> · Boundary/Web macro-fibers · "
                    "<span style='color:#f28c00'>━</span> "
                    "MVLEM_3D panel guide · four-node panels"
                )
            else:
                self.preview_legend.setText(
                    "<b>Legend</b> · Boundary/Web macro-fibers · "
                    "<span style='color:#f28c00'>┄</span> "
                    "macro-element centerline + nodes"
                )

        if hasattr(self, "preview_note"):
            if is_mefi:
                self.preview_note.setText(
                    "MEFI/RCLMS preview includes detailed reinforcement. "
                    "Embedded vertical bars use ASDEmbeddedNodeElement; "
                    "front/back separation remains schematic in 2D."
                )
            elif is_sfi:
                self.preview_note.setText(
                    "SFI_MVLEM uses a centerline macro-element stack. "
                    "Boundary and web fibers reference existing FSAM "
                    "nDMaterials; no RCLMS/discrete-bar objects are generated."
                )
            elif is_3d:
                self.preview_note.setText(
                    "MVLEM_3D uses four nodes per wall panel row in a "
                    "3D/6DOF domain. Fiber widths, thicknesses, steel ratios "
                    "and material mapping are shared across the vertical stack."
                )
            else:
                self.preview_note.setText(
                    "MVLEM uses a centerline macro-element stack with "
                    "Concrete02/Steel02 fibers and one existing shear material."
                )

    def _preset_changed(self, *_args) -> None:
        if self.preset.currentData() == "rw-a20":
            self._apply_rw_a20_preset()
        else:
            self._update_preview()
            self._update_review()

    def _update_preview(self) -> None:
        if not hasattr(self, "preview"):
            return

        mode = (
            str(self.reinforcement_mode.currentData())
            if hasattr(self, "reinforcement_mode")
            else "smeared"
        )
        fully_discrete = mode == "fully_discrete"
        vertical_diameter = (
            float(self.web_vertical_bar_diameter.value())
            if hasattr(self, "web_vertical_bar_diameter")
            else 0.0
        )
        if fully_discrete:
            try:
                summary = rc_wall_reinforcement_summary(self.data())
                vertical_diameter = float(
                    summary["web_vertical_equivalent_diameter"]
                )
            except (AttributeError, ValueError, ZeroDivisionError):
                pass

        preview_kwargs = dict(
            width=float(self.width.value()),
            height=float(self.height.value()),
            thickness=float(self.thickness.value()),
            boundary=float(self.boundary_width.value()),
            rows=int(self.vertical_elements.value()),
            fibers=int(self.macro_fibers.value()),
            formulation=str(self.formulation.currentData()),
            reinforcement_mode=mode,
            boundary_bars=(
                int(self.boundary_bar_count.value())
                if hasattr(self, "boundary_bar_count")
                else 0
            ),
            boundary_layer_mode=(
                str(self.boundary_layer_mode.currentData())
                if hasattr(self, "boundary_layer_mode")
                else "front_back"
            ),
            boundary_cover=(
                float(self.boundary_cover.value())
                if hasattr(self, "boundary_cover")
                else 0.0
            ),
            web_horizontal_mode=(
                "mesh_aligned"
                if fully_discrete
                else (
                    str(self.web_horizontal_mode.currentData())
                    if hasattr(self, "web_horizontal_mode")
                    else "smeared"
                )
            ),
            web_horizontal_layer_mode=(
                str(self.web_horizontal_layer_mode.currentData())
                if hasattr(self, "web_horizontal_layer_mode")
                else "front_back"
            ),
            web_vertical_mode=(
                "embedded"
                if fully_discrete
                else (
                    str(self.web_vertical_mode.currentData())
                    if hasattr(self, "web_vertical_mode")
                    else "smeared"
                )
            ),
            web_vertical_bar_diameter=vertical_diameter,
            web_vertical_spacing=(
                float(self.web_vertical_spacing.value())
                if hasattr(self, "web_vertical_spacing")
                else 1.0
            ),
            web_vertical_edge_offset=(
                float(self.web_vertical_edge_offset.value())
                if hasattr(self, "web_vertical_edge_offset")
                else 0.0
            ),
            web_vertical_layer_mode=(
                str(self.web_vertical_layer_mode.currentData())
                if hasattr(self, "web_vertical_layer_mode")
                else "front_back"
            ),
        )
        self.preview.set_wall(**preview_kwargs)
        if hasattr(self, "final_preview"):
            warning_keys = set()
            if hasattr(self, "_preview_validation_items"):
                warning_keys = {
                    key
                    for key, _message in self._preview_validation_items()
                }
            self.final_preview.set_wall(
                **preview_kwargs,
                detailed_annotations=True,
                warning_keys=warning_keys,
            )
        self._update_reinforcement_info()

    def _from_mm(self, value_mm: float) -> float:
        return float(value_mm) * 0.001 / self.units.length_to_m

    def _apply_rw_a20_preset(self) -> None:
        self._applying_preset = True
        self.width.setValue(self._from_mm(1220.0))
        self.height.setValue(self._from_mm(2209.8))
        self.thickness.setValue(self._from_mm(152.4))
        self.boundary_width.setValue(self._from_mm(228.6))
        self.origin_x.setValue(0.0)
        self.origin_y.setValue(0.0)
        self.vertical_elements.setValue(7)
        self.macro_fibers.setValue(8)

        records = self._verified_material_records
        steel_x = records["opensees-mefi-rwa20-steel-x-steel02"]
        steel_y_web = records[
            "opensees-mefi-rwa20-steel-y-web-steel02"
        ]
        steel_y_boundary = records[
            "opensees-mefi-rwa20-steel-y-boundary-steel02"
        ]
        concrete_web = records[
            "opensees-mefi-rwa20-unconfined-concrete02"
        ]
        concrete_boundary = records[
            "opensees-mefi-rwa20-confined-concrete02"
        ]
        self._rw_a20_hidden_parameters = {
            "steel_x": dict(steel_x.parameters_si),
            "steel_y_web": dict(steel_y_web.parameters_si),
            "steel_y_boundary": dict(steel_y_boundary.parameters_si),
            "concrete_web": dict(concrete_web.parameters_si),
            "concrete_boundary": dict(concrete_boundary.parameters_si),
        }

        self.fc_web.setValue(
            self._stress_display(abs(concrete_web.parameters_si["fpc"]))
        )
        self.eps_web.setValue(concrete_web.parameters_si["epsc0"])
        self.fc_boundary.setValue(
            self._stress_display(
                abs(concrete_boundary.parameters_si["fpc"])
            )
        )
        self.eps_boundary.setValue(
            concrete_boundary.parameters_si["epsc0"]
        )
        self.ft.setValue(
            self._stress_display(concrete_web.parameters_si["ft"])
        )
        self.cracking_strain.setValue(0.00008)
        self.damage1.setValue(0.175)
        self.damage2.setValue(0.5)
        self.unconfined_layer.setValue(self._from_mm(50.8))

        self.steel_E.setValue(
            self._stress_display(steel_x.parameters_si["E0"])
        )
        self.fy_x.setValue(
            self._stress_display(steel_x.parameters_si["Fy"])
        )
        self.fy_y_web.setValue(
            self._stress_display(steel_y_web.parameters_si["Fy"])
        )
        self.fy_y_boundary.setValue(
            self._stress_display(steel_y_boundary.parameters_si["Fy"])
        )
        self.rho_x_web.setValue(0.27)
        self.rho_y_web.setValue(0.27)
        self.rho_x_boundary.setValue(0.82)
        self.rho_y_boundary.setValue(3.23)
        smeared_index = self.reinforcement_mode.findData("smeared")
        if smeared_index >= 0:
            self.reinforcement_mode.blockSignals(True)
            self.reinforcement_mode.setCurrentIndex(smeared_index)
            self.reinforcement_mode.blockSignals(False)
        self.boundary_bar_count.setValue(4)
        self.boundary_bar_diameter.setValue(self._from_mm(16.0))
        self.boundary_cover.setValue(self._from_mm(30.0))
        front_back_index = self.boundary_layer_mode.findData("front_back")
        if front_back_index >= 0:
            self.boundary_layer_mode.blockSignals(True)
            self.boundary_layer_mode.setCurrentIndex(front_back_index)
            self.boundary_layer_mode.blockSignals(False)
        smeared_horizontal = self.web_horizontal_mode.findData("smeared")
        if smeared_horizontal >= 0:
            self.web_horizontal_mode.blockSignals(True)
            self.web_horizontal_mode.setCurrentIndex(smeared_horizontal)
            self.web_horizontal_mode.blockSignals(False)
        self.web_horizontal_bar_diameter.setValue(self._from_mm(8.0))
        self.web_vertical_bar_diameter.setValue(self._from_mm(6.0))
        self.web_vertical_spacing.setValue(self._from_mm(200.0))
        self.web_vertical_edge_offset.setValue(self._from_mm(50.0))
        self.embedded_penalty_factor.setValue(1.0)
        smeared_vertical = self.web_vertical_mode.findData("smeared")
        if smeared_vertical >= 0:
            self.web_vertical_mode.blockSignals(True)
            self.web_vertical_mode.setCurrentIndex(smeared_vertical)
            self.web_vertical_mode.blockSignals(False)
        vertical_layers = self.web_vertical_layer_mode.findData(
            "front_back"
        )
        if vertical_layers >= 0:
            self.web_vertical_layer_mode.blockSignals(True)
            self.web_vertical_layer_mode.setCurrentIndex(vertical_layers)
            self.web_vertical_layer_mode.blockSignals(False)
        horizontal_layers = self.web_horizontal_layer_mode.findData(
            "front_back"
        )
        if horizontal_layers >= 0:
            self.web_horizontal_layer_mode.blockSignals(True)
            self.web_horizontal_layer_mode.setCurrentIndex(horizontal_layers)
            self.web_horizontal_layer_mode.blockSignals(False)
        corot_index = self.boundary_truss_type.findData("corotTruss")
        if corot_index >= 0:
            self.boundary_truss_type.blockSignals(True)
            self.boundary_truss_type.setCurrentIndex(corot_index)
            self.boundary_truss_type.blockSignals(False)
        self._sync_reinforcement_mode()
        self._applying_preset = False
        benchmark_index = self.preset.findData("rw-a20")
        if benchmark_index >= 0:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(benchmark_index)
            self.preset.blockSignals(False)
        self._update_preview()
        self._update_review()

    def data(self) -> RCWallSpec:
        thickness = float(self.thickness.value())
        unconfined = float(self.unconfined_layer.value())
        confined = thickness - unconfined
        if confined <= 0.0:
            raise ValueError(
                "Boundary unconfined layer must be smaller than wall thickness."
            )

        fc_web = self._stress_store(self.fc_web.value())
        fc_boundary = self._stress_store(self.fc_boundary.value())
        ft = self._stress_store(self.ft.value())

        reinforcement_mode = str(self.reinforcement_mode.currentData())
        fully_discrete = reinforcement_mode == "fully_discrete"

        return RCWallSpec(
            width=float(self.width.value()),
            height=float(self.height.value()),
            thickness=thickness,
            boundary_width=float(self.boundary_width.value()),
            origin_x=float(self.origin_x.value()),
            origin_y=float(self.origin_y.value()),
            vertical_elements=int(self.vertical_elements.value()),
            macro_fibers=int(self.macro_fibers.value()),
            formulation=str(self.formulation.currentData()),
            macro_center_ratio=float(self.macro_center_ratio.value()),
            macro_density=float(self.macro_density.value()),
            macro_thick_mod=float(self.macro_thick_mod.value()),
            macro_poisson=float(self.macro_poisson.value()),
            macro_shear_material_tag=(
                None
                if self.macro_shear_material.currentData() is None
                else int(self.macro_shear_material.currentData())
            ),
            macro_web_fsam_tag=(
                None
                if self.macro_web_fsam.currentData() is None
                else int(self.macro_web_fsam.currentData())
            ),
            macro_boundary_fsam_tag=(
                None
                if self.macro_boundary_fsam.currentData() is None
                else int(self.macro_boundary_fsam.currentData())
            ),
            steel_E=self._stress_store(self.steel_E.value()),
            steel_fx=self._stress_store(self.fy_x.value()),
            steel_fy_web=self._stress_store(self.fy_y_web.value()),
            steel_fy_boundary=self._stress_store(
                self.fy_y_boundary.value()
            ),
            steel_bx=float(
                self._rw_a20_hidden_parameters.get("steel_x", {}).get(
                    "b", 0.02
                )
            ),
            steel_by_web=float(
                self._rw_a20_hidden_parameters.get("steel_y_web", {}).get(
                    "b", 0.02
                )
            ),
            steel_by_boundary=float(
                self._rw_a20_hidden_parameters.get(
                    "steel_y_boundary", {}
                ).get("b", 0.01)
            ),
            concrete_fc_web=-abs(fc_web),
            concrete_eps_web=float(self.eps_web.value()),
            concrete_fcu_web=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_web", {}
                ).get("fpcu", 0.0)
            ),
            concrete_epsu_web=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_web", {}
                ).get("epsU", -0.037)
            ),
            concrete_fc_boundary=-abs(fc_boundary),
            concrete_eps_boundary=float(self.eps_boundary.value()),
            concrete_fcu_boundary=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_boundary", {}
                ).get("fpcu", -9.42e6)
            ),
            concrete_epsu_boundary=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_boundary", {}
                ).get("epsU", -0.047)
            ),
            concrete_ft=abs(ft),
            concrete_ets_web=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_web", {}
                ).get("Ets", 1.73833e9)
            ),
            concrete_ets_boundary=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_boundary", {}
                ).get("Ets", 1.82712e9)
            ),
            concrete_lambda=float(
                self._rw_a20_hidden_parameters.get(
                    "concrete_web", {}
                ).get("lambda", 0.1)
            ),
            cracking_strain=float(self.cracking_strain.value()),
            damage_cte1=float(self.damage1.value()),
            damage_cte2=float(self.damage2.value()),
            rho_x_web=float(self.rho_x_web.value()) / 100.0,
            rho_y_web=float(self.rho_y_web.value()) / 100.0,
            rho_x_boundary=float(self.rho_x_boundary.value()) / 100.0,
            rho_y_boundary=float(self.rho_y_boundary.value()) / 100.0,
            reinforcement_mode=reinforcement_mode,
            boundary_bar_count=int(self.boundary_bar_count.value()),
            boundary_bar_diameter=float(
                self.boundary_bar_diameter.value()
            ),
            boundary_truss_type=str(
                self.boundary_truss_type.currentData()
            ),
            boundary_layer_mode=str(
                self.boundary_layer_mode.currentData()
            ),
            boundary_cover=float(self.boundary_cover.value()),
            web_horizontal_mode=(
                "mesh_aligned"
                if fully_discrete
                else (
                    str(self.web_horizontal_mode.currentData())
                    if reinforcement_mode == "hybrid"
                    else "smeared"
                )
            ),
            web_horizontal_bar_diameter=float(
                self.web_horizontal_bar_diameter.value()
            ),
            web_horizontal_layer_mode=str(
                self.web_horizontal_layer_mode.currentData()
            ),
            web_vertical_mode=(
                "embedded"
                if fully_discrete
                else (
                    str(self.web_vertical_mode.currentData())
                    if reinforcement_mode == "hybrid"
                    else "smeared"
                )
            ),
            web_vertical_bar_diameter=float(
                self.web_vertical_bar_diameter.value()
            ),
            web_vertical_spacing=float(
                self.web_vertical_spacing.value()
            ),
            web_vertical_edge_offset=float(
                self.web_vertical_edge_offset.value()
            ),
            web_vertical_layer_mode=str(
                self.web_vertical_layer_mode.currentData()
            ),
            embedded_penalty_factor=float(
                self.embedded_penalty_factor.value()
            ),
            boundary_unconfined_thickness=unconfined,
            boundary_confined_thickness=confined,
            name=self.wall_name.text().strip() or "RC Wall",
            replace_geometry=bool(self.replace_geometry.isChecked()),
        )

    def validateCurrentPage(self) -> bool:
        try:
            page = self.currentId()
            if page == 0:
                width = float(self.width.value())
                height = float(self.height.value())
                thickness = float(self.thickness.value())
                boundary = float(self.boundary_width.value())
                if min(width, height, thickness) <= 0.0:
                    raise ValueError(
                        "Wall width, height and thickness must be positive."
                    )
                if not 0.0 < boundary < 0.5 * width:
                    raise ValueError(
                        "Boundary width must be positive and smaller than "
                        "half the wall width."
                    )
                formulation = str(self.formulation.currentData())
                required_domain = (
                    (3, 6) if formulation == "MVLEM_3D" else (2, 3)
                )
                if (
                    not self.replace_geometry.isChecked()
                    and (
                        int(self.project.model.ndm),
                        int(self.project.model.ndf),
                    ) != required_domain
                ):
                    raise ValueError(
                        "Append mode for "
                        f"{formulation} requires ndm={required_domain[0]} / "
                        f"ndf={required_domain[1]}."
                    )
            elif page == 1:
                if self.unconfined_layer.value() >= self.thickness.value():
                    raise ValueError(
                        "Boundary unconfined layer must be smaller than "
                        "the wall thickness."
                    )
                if (
                    self.eps_web.value() >= 0.0
                    or self.eps_boundary.value() >= 0.0
                ):
                    raise ValueError(
                        "Concrete peak compression strains must be negative."
                    )
                if (
                    self.fc_web.value() <= 0.0
                    or self.fc_boundary.value() <= 0.0
                ):
                    raise ValueError(
                        "Concrete compressive strengths must be positive "
                        "magnitudes in the wizard."
                    )
            elif page == 2:
                if min(
                    self.steel_E.value(),
                    self.fy_x.value(),
                    self.fy_y_web.value(),
                    self.fy_y_boundary.value(),
                ) <= 0.0:
                    raise ValueError(
                        "Steel modulus and yield strengths must be positive."
                    )
                for widget, label in (
                    (self.rho_x_web, "Web rho-x"),
                    (self.rho_y_web, "Web rho-y"),
                    (self.rho_x_boundary, "Boundary rho-x"),
                    (self.rho_y_boundary, "Boundary rho-y"),
                ):
                    if not 0.0 <= widget.value() <= 100.0:
                        raise ValueError(
                            f"{label} must be between 0 and 100%."
                        )
                formulation = str(self.formulation.currentData())
                if formulation in {"MVLEM", "MVLEM_3D"}:
                    if self.macro_shear_material.currentData() is None:
                        raise ValueError(
                            f"{formulation} requires an existing uniaxial "
                            "shear material."
                        )
                    if formulation == "MVLEM_3D":
                        if self.macro_thick_mod.value() <= 0.0:
                            raise ValueError(
                                "MVLEM_3D ThickMod must be positive."
                            )
                        if not -1.0 < self.macro_poisson.value() < 0.5:
                            raise ValueError(
                                "MVLEM_3D Poisson ratio must satisfy "
                                "-1 < nu < 0.5."
                            )
                    return True
                if formulation == "SFI_MVLEM":
                    if (
                        self.macro_web_fsam.currentData() is None
                        or self.macro_boundary_fsam.currentData() is None
                    ):
                        raise ValueError(
                            "SFI_MVLEM requires FSAM nD materials for both "
                            "web and boundary macro-fibers."
                        )
                    return True

                reinforcement_mode = str(
                    self.reinforcement_mode.currentData()
                )
                if reinforcement_mode == "fully_discrete":
                    validate_rc_wall_spec(self.data())
                elif formulation == "MEFI" and reinforcement_mode == "hybrid":
                    diameter = float(self.boundary_bar_diameter.value())
                    count = int(self.boundary_bar_count.value())
                    cover = float(self.boundary_cover.value())
                    boundary = float(self.boundary_width.value())
                    thickness = float(self.thickness.value())
                    gross = boundary * thickness
                    discrete_ratio = (
                        count * math.pi * diameter * diameter / 4.0 / gross
                    )
                    total_ratio = (
                        float(self.rho_y_boundary.value()) / 100.0
                    )
                    if discrete_ratio > total_ratio + 1.0e-12:
                        raise ValueError(
                            "Discrete boundary bars exceed total boundary "
                            "rho-y. Reduce bar count/diameter or increase "
                            "boundary rho-y."
                        )
                    if (
                        self.boundary_layer_mode.currentData() == "front_back"
                        and count % 2
                    ):
                        raise ValueError(
                            "Front/back boundary layout requires an even "
                            "total bar count."
                        )
                    if 2.0 * cover + diameter > boundary + 1.0e-12:
                        raise ValueError(
                            "Boundary cover and bar diameter do not fit "
                            "the boundary-zone width."
                        )
                    if (
                        self.boundary_layer_mode.currentData() == "front_back"
                        and 2.0 * cover + diameter > thickness + 1.0e-12
                    ):
                        raise ValueError(
                            "Boundary cover and bar diameter do not fit "
                            "through the wall thickness."
                        )
                    if (
                        self.web_horizontal_mode.currentData()
                        == "mesh_aligned"
                    ):
                        h_d = float(
                            self.web_horizontal_bar_diameter.value()
                        )
                        h_layers = (
                            2
                            if self.web_horizontal_layer_mode.currentData()
                            == "front_back"
                            else 1
                        )
                        h_lines = max(
                            int(self.vertical_elements.value()) - 1,
                            0,
                        )
                        h_rho = (
                            h_lines
                            * h_layers
                            * math.pi
                            * h_d
                            * h_d
                            / 4.0
                            / (
                                float(self.height.value())
                                * thickness
                            )
                        )
                        if h_rho > min(
                            float(self.rho_x_web.value()) / 100.0,
                            float(self.rho_x_boundary.value()) / 100.0,
                        ) + 1.0e-12:
                            raise ValueError(
                                "Discrete horizontal bars exceed available "
                                "rho-x in the web or boundary zone."
                            )
                    if self.web_vertical_mode.currentData() == "embedded":
                        vertical = self._vertical_web_metrics()
                        if not bool(vertical["fits"]):
                            raise ValueError(
                                "No embedded vertical web bar fits between "
                                "the boundary zones. Reduce edge offset/bar "
                                "diameter or increase the web width."
                            )
                        if float(vertical["remaining_rho"]) < -1.0e-12:
                            raise ValueError(
                                "Embedded vertical web bars exceed available "
                                "web rho-y. Increase spacing/reduce diameter "
                                "or increase web rho-y."
                            )
            else:
                self.data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "RC Wall Wizard",
                str(exc),
            )
            return False
        return super().validateCurrentPage()

    def _preview_object_counts(self) -> dict[str, int]:
        rows = max(int(self.vertical_elements.value()), 1)
        formulation = str(self.formulation.currentData())
        if formulation != "MEFI":
            is_3d = formulation == "MVLEM_3D"
            host_nodes = (
                2 * (rows + 1)
                if is_3d
                else rows + 1
            )
            return {
                "nodes": host_nodes,
                "host_nodes": host_nodes,
                "embedded_nodes": 0,
                "horizontal_embedded_nodes": 0,
                "vertical_embedded_nodes": 0,
                "mefi": 0,
                "wall_elements": rows,
                "boundary_rebar": 0,
                "horizontal_rebar": 0,
                "web_horizontal_rebar": 0,
                "boundary_horizontal_rebar": 0,
                "vertical_rebar": 0,
                "embedded_coupling": 0,
                "horizontal_coupling": 0,
                "vertical_coupling": 0,
                "discrete_rebar": 0,
                "elements": rows,
                "structural_elements": rows,
                "uniaxial_materials": (
                    4 if formulation in {"MVLEM", "MVLEM_3D"} else 0
                ),
                "nd_materials": 0,
                "sections": 0,
                "selection_sets": 3,
                "fixed_nodes": 2 if is_3d else 1,
            }

        mode = str(self.reinforcement_mode.currentData())
        discrete_enabled = mode in {"hybrid", "fully_discrete"}
        fully_discrete = mode == "fully_discrete"

        boundary_rebar = 0
        horizontal_rebar = 0
        web_horizontal_rebar = 0
        boundary_horizontal_rebar = 0
        vertical_rebar = 0
        horizontal_embedded_nodes = 0
        vertical_embedded_nodes = 0
        horizontal_coupling = 0
        vertical_coupling = 0

        if discrete_enabled:
            boundary_rebar = (
                rows
                * 2
                * int(self.boundary_bar_count.value())
            )
            horizontal_layers = (
                2
                if self.web_horizontal_layer_mode.currentData()
                == "front_back"
                else 1
            )
            internal_rows = max(rows - 1, 0)

            if fully_discrete:
                web_horizontal_rebar = (
                    internal_rows * horizontal_layers
                )
                boundary_horizontal_rebar = (
                    2 * internal_rows * horizontal_layers
                )
                horizontal_rebar = (
                    web_horizontal_rebar
                    + boundary_horizontal_rebar
                )
                horizontal_embedded_nodes = 2 * internal_rows
                horizontal_coupling = horizontal_embedded_nodes
            elif self.web_horizontal_mode.currentData() == "mesh_aligned":
                web_horizontal_rebar = (
                    internal_rows * horizontal_layers
                )
                horizontal_rebar = web_horizontal_rebar

            vertical_enabled = (
                fully_discrete
                or self.web_vertical_mode.currentData() == "embedded"
            )
            if vertical_enabled:
                vertical = self._vertical_web_metrics()
                bar_lines = (
                    int(vertical["bar_count_per_layer"])
                    * int(vertical["layers"])
                )
                vertical_rebar = bar_lines * rows
                vertical_embedded_nodes = bar_lines * (rows + 1)
                vertical_coupling = vertical_embedded_nodes

        embedded_nodes = (
            horizontal_embedded_nodes + vertical_embedded_nodes
        )
        embedded_coupling = horizontal_coupling + vertical_coupling
        discrete = boundary_rebar + horizontal_rebar + vertical_rebar

        selection_sets = 3
        if discrete:
            selection_sets += 1  # Discrete Reinforcement
        if horizontal_rebar:
            selection_sets += 1  # Horizontal Bars
        if vertical_rebar:
            selection_sets += 1  # Vertical Web Bars
        if embedded_coupling:
            selection_sets += 1  # Embedded Coupling

        return {
            "nodes": 2 * (rows + 1) + embedded_nodes,
            "host_nodes": 2 * (rows + 1),
            "embedded_nodes": embedded_nodes,
            "horizontal_embedded_nodes": horizontal_embedded_nodes,
            "vertical_embedded_nodes": vertical_embedded_nodes,
            "mefi": rows,
            "boundary_rebar": boundary_rebar,
            "horizontal_rebar": horizontal_rebar,
            "web_horizontal_rebar": web_horizontal_rebar,
            "boundary_horizontal_rebar": boundary_horizontal_rebar,
            "vertical_rebar": vertical_rebar,
            "embedded_coupling": embedded_coupling,
            "horizontal_coupling": horizontal_coupling,
            "vertical_coupling": vertical_coupling,
            "discrete_rebar": discrete,
            "elements": rows + discrete + embedded_coupling,
            "structural_elements": rows + discrete,
            "uniaxial_materials": 5,
            "nd_materials": 4,
            "sections": 2,
            "selection_sets": selection_sets,
            "fixed_nodes": 2,
        }

    def _preview_validation_items(
        self,
    ) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        width = float(self.width.value())
        height = float(self.height.value())
        thickness = float(self.thickness.value())
        boundary = float(self.boundary_width.value())
        if min(width, height, thickness) <= 0.0:
            items.append(
                ("geometry", "Wall dimensions must be positive.")
            )
        if not 0.0 < boundary < 0.5 * width:
            items.append((
                "boundary",
                "Boundary width must be positive and smaller than W/2.",
            ))
        if self.unconfined_layer.value() >= thickness:
            items.append((
                "boundary",
                "Boundary unconfined layer must be smaller than thickness.",
            ))
        formulation = str(self.formulation.currentData())
        required_domain = (
            (3, 6) if formulation == "MVLEM_3D" else (2, 3)
        )
        if (
            not self.replace_geometry.isChecked()
            and (
                int(self.project.model.ndm),
                int(self.project.model.ndf),
            ) != required_domain
        ):
            items.append((
                "domain",
                "Append mode for "
                f"{formulation} requires ndm={required_domain[0]} / "
                f"ndf={required_domain[1]}.",
            ))

        if formulation != "MEFI":
            if not 0.0 <= self.macro_center_ratio.value() <= 1.0:
                items.append((
                    "macro",
                    "Macro center-of-rotation ratio must be in [0, 1].",
                ))
            if self.macro_density.value() < 0.0:
                items.append(("macro", "Macro density cannot be negative."))
            if formulation in {"MVLEM", "MVLEM_3D"}:
                if self.macro_shear_material.currentData() is None:
                    items.append((
                        "material",
                        f"{formulation} requires a shear material.",
                    ))
            if formulation == "SFI_MVLEM":
                if (
                    self.macro_web_fsam.currentData() is None
                    or self.macro_boundary_fsam.currentData() is None
                ):
                    items.append((
                        "material",
                        "SFI_MVLEM requires web and boundary FSAM materials.",
                    ))
            if formulation == "MVLEM_3D":
                if self.macro_thick_mod.value() <= 0.0:
                    items.append((
                        "macro",
                        "MVLEM_3D ThickMod must be positive.",
                    ))
                if not -1.0 < self.macro_poisson.value() < 0.5:
                    items.append((
                        "macro",
                        "MVLEM_3D Poisson ratio must satisfy -1 < nu < 0.5.",
                    ))
            return items

        reinforcement_mode = str(
            self.reinforcement_mode.currentData()
        )
        if reinforcement_mode == "fully_discrete":
            try:
                validate_rc_wall_spec(self.data())
            except ValueError as exc:
                message = str(exc)
                lowered = message.lower()
                key = (
                    "boundary"
                    if "boundary" in lowered
                    else "web_vertical"
                    if "vertical" in lowered
                    else "web_rebar"
                    if "horizontal" in lowered
                    else "fully_discrete"
                )
                items.append((key, message))
            return items

        if reinforcement_mode == "hybrid":
            count = int(self.boundary_bar_count.value())
            diameter = float(self.boundary_bar_diameter.value())
            cover = float(self.boundary_cover.value())
            gross = boundary * thickness
            rho = (
                count * math.pi * diameter * diameter / 4.0 / gross
                if gross > 0.0
                else float("inf")
            )
            if rho > float(self.rho_y_boundary.value()) / 100.0 + 1.0e-12:
                items.append((
                    "boundary",
                    "Discrete boundary bars exceed total boundary rho-y.",
                ))
            if (
                self.boundary_layer_mode.currentData() == "front_back"
                and count % 2
            ):
                items.append((
                    "boundary",
                    "Front/back boundary layout needs an even bar count.",
                ))
            if 2.0 * cover + diameter > boundary + 1.0e-12:
                items.append((
                    "boundary",
                    "Boundary cover and bar diameter do not fit the zone.",
                ))
            if (
                self.boundary_layer_mode.currentData() == "front_back"
                and 2.0 * cover + diameter > thickness + 1.0e-12
            ):
                items.append((
                    "boundary",
                    "Front/back cover and bar diameter do not fit thickness.",
                ))

            if self.web_horizontal_mode.currentData() == "mesh_aligned":
                h_diameter = float(
                    self.web_horizontal_bar_diameter.value()
                )
                h_layers = (
                    2
                    if self.web_horizontal_layer_mode.currentData()
                    == "front_back"
                    else 1
                )
                h_lines = max(int(self.vertical_elements.value()) - 1, 0)
                h_rho = (
                    h_lines
                    * h_layers
                    * math.pi
                    * h_diameter
                    * h_diameter
                    / 4.0
                    / (height * thickness)
                    if height > 0.0 and thickness > 0.0
                    else float("inf")
                )
                available = min(
                    float(self.rho_x_web.value()) / 100.0,
                    float(self.rho_x_boundary.value()) / 100.0,
                )
                if h_rho > available + 1.0e-12:
                    items.append((
                        "web_rebar",
                        "Discrete horizontal bars exceed available rho-x.",
                    ))

            if self.web_vertical_mode.currentData() == "embedded":
                vertical = self._vertical_web_metrics()
                if not bool(vertical["fits"]):
                    items.append((
                        "web_vertical",
                        "No embedded vertical web bar fits in the web region.",
                    ))
                if float(vertical["remaining_rho"]) < -1.0e-12:
                    items.append((
                        "web_vertical",
                        "Embedded vertical bars exceed available web rho-y.",
                    ))

        return items

    def _preview_validation_messages(self) -> list[str]:
        return [
            message
            for _key, message in self._preview_validation_items()
        ]

    def _rw_a20_material_status_html(
        self,
        *,
        include_steel_x: bool,
    ) -> str:
        stress = self._stress_store
        checks: list[tuple[str, bool]] = []
        if include_steel_x:
            checks.append((
                "Steel X",
                math.isclose(stress(self.steel_E.value()), 200.0e9, rel_tol=1e-9)
                and math.isclose(stress(self.fy_x.value()), 469.93e6, rel_tol=1e-9),
            ))
        checks.extend([
            (
                "Steel Y web",
                math.isclose(stress(self.steel_E.value()), 200.0e9, rel_tol=1e-9)
                and math.isclose(
                    stress(self.fy_y_web.value()), 409.71e6, rel_tol=1e-9
                ),
            ),
            (
                "Steel Y boundary",
                math.isclose(stress(self.steel_E.value()), 200.0e9, rel_tol=1e-9)
                and math.isclose(
                    stress(self.fy_y_boundary.value()), 429.78e6, rel_tol=1e-9
                ),
            ),
            (
                "Concrete web",
                math.isclose(
                    stress(self.fc_web.value()), 47.09e6, rel_tol=1e-9
                )
                and math.isclose(
                    float(self.eps_web.value()), -0.00232, rel_tol=1e-9
                ),
            ),
            (
                "Concrete boundary",
                math.isclose(
                    stress(self.fc_boundary.value()), 53.78e6, rel_tol=1e-9
                )
                and math.isclose(
                    float(self.eps_boundary.value()), -0.00397, rel_tol=1e-9
                ),
            ),
        ])
        return "<br>".join(
            f"{name}: "
            + (
                "<span style='color:#22763b'>✓ Verified RW-A20</span>"
                if exact
                else "<span style='color:#a15c00'>Modified from verified</span>"
            )
            for name, exact in checks
        )

    def _update_review(self) -> None:
        if not hasattr(self, "review"):
            return
        try:
            self._update_preview()
            width = float(self.width.value())
            height = float(self.height.value())
            thickness = float(self.thickness.value())
            boundary = float(self.boundary_width.value())
            count = int(self.macro_fibers.value())
            rows = int(self.vertical_elements.value())
            web_count = count - 2
            web_width = (width - 2.0 * boundary) / web_count
            mapping = (
                "[B] " + " ".join("[W]" for _ in range(web_count)) + " [B]"
            )
            formulation = str(self.formulation.currentData())
            mode = (
                "Replace current FE model"
                if self.replace_geometry.isChecked()
                else (
                    "Append to current 3D model"
                    if formulation == "MVLEM_3D"
                    else "Append to current 2D model"
                )
            )
            reinforcement_mode = str(
                self.reinforcement_mode.currentData()
            )
            reinforcement_text = (
                "Macro-fiber reinforcement ratios ρy (Boundary/Web)"
                if formulation != "MEFI"
                else "Smeared reinforcement only"
            )
            if formulation == "MEFI" and reinforcement_mode == "fully_discrete":
                spec = self.data()
                summary = rc_wall_reinforcement_summary(spec)
                reinforcement_text = (
                    "<b>Fully Discrete</b> · RCLMS steel ratios = 0<br>"
                    f"Boundary Y: {self.boundary_bar_count.value()} bars/zone · "
                    f"equiv. Ø"
                    f"{float(summary['boundary_equivalent_diameter']):g} "
                    f"{self.units.length}<br>"
                    f"Web Y: {len(summary['web_vertical_positions'])} "
                    f"bars/layer · equiv. Ø"
                    f"{float(summary['web_vertical_equivalent_diameter']):g} "
                    f"{self.units.length} · "
                    f"s≈{float(summary['web_vertical_actual_spacing']):g} "
                    f"{self.units.length}<br>"
                    f"Horizontal: "
                    f"{int(summary['horizontal_line_count'])} row(s) · "
                    f"web equiv. Ø"
                    f"{float(summary['web_horizontal_equivalent_diameter']):g} · "
                    f"boundary equiv. Ø"
                    f"{float(summary['boundary_horizontal_equivalent_diameter']):g} "
                    f"{self.units.length}<br>"
                    "All target ρx/ρy represented by discrete bars."
                )
            elif formulation == "MEFI" and reinforcement_mode == "hybrid":
                diameter = float(self.boundary_bar_diameter.value())
                bars = int(self.boundary_bar_count.value())
                discrete_area = bars * math.pi * diameter * diameter / 4.0
                gross = boundary * thickness
                discrete_rho = (
                    100.0 * discrete_area / gross
                    if gross > 0.0 else 0.0
                )
                remaining = max(
                    0.0,
                    float(self.rho_y_boundary.value()) - discrete_rho,
                )
                layer_label = (
                    "Front + Back"
                    if self.boundary_layer_mode.currentData() == "front_back"
                    else "Single centerline"
                )
                horizontal_label = (
                    "Discrete on MEFI rows"
                    if self.web_horizontal_mode.currentData() == "mesh_aligned"
                    else "Smeared"
                )
                vertical_label = "Smeared"
                if self.web_vertical_mode.currentData() == "embedded":
                    vertical = self._vertical_web_metrics()
                    vertical_label = (
                        f"Embedded · "
                        f"{int(vertical['bar_count_per_layer'])} bars/layer × "
                        f"{int(vertical['layers'])} layer(s) · "
                        f"s≈{float(vertical['actual_spacing']):g} "
                        f"{self.units.length}"
                    )
                reinforcement_text = (
                    f"{bars} × Ø{diameter:g} / boundary · {layer_label}<br>"
                    f"Cover = {self.boundary_cover.value():g} "
                    f"{self.units.length}<br>"
                    f"ρy discrete = {discrete_rho:.3g}% · "
                    f"smeared remaining = {remaining:.3g}%<br>"
                    f"Horizontal web = {horizontal_label}<br>"
                    f"Vertical web = {vertical_label}"
                )

            counts = self._preview_object_counts()
            self.preview_geometry_summary.setText(
                "<b>Wall to create</b><br>"
                f"{self.wall_name.text().strip() or 'RC Wall'}<br>"
                f"W × H × t = {width:g} × {height:g} × {thickness:g} "
                f"{self.units.length}<br>"
                f"Boundary = {boundary:g} {self.units.length} each side<br>"
                f"Origin = ({self.origin_x.value():g}, "
                f"{self.origin_y.value():g}) {self.units.length}<br>"
                f"{formulation} = {rows} vertical element(s) · "
                f"{count} macro-fibers<br>"
                f"Web fiber width = {web_width:g} {self.units.length}<br>"
                f"Mode = {mode}"
            )
            if formulation == "MEFI":
                object_text = (
                    "<b>Objects to be created</b><br>"
                    f"Nodes: {counts['nodes']} "
                    f"({counts['host_nodes']} host + "
                    f"{counts['embedded_nodes']} embedded steel)<br>"
                    f"MEFI elements: {counts['mefi']}<br>"
                    f"Boundary bar elements: {counts['boundary_rebar']}<br>"
                    f"Horizontal bar elements: {counts['horizontal_rebar']} "
                    f"({counts['web_horizontal_rebar']} web + "
                    f"{counts['boundary_horizontal_rebar']} boundary)<br>"
                    f"Vertical web bar elements: {counts['vertical_rebar']}<br>"
                    f"Embedded coupling helpers: "
                    f"{counts['embedded_coupling']}<br>"
                    f"<b>Total elements: {counts['elements']}</b> "
                    f"({counts['structural_elements']} structural)<br>"
                    f"Uniaxial materials: {counts['uniaxial_materials']}<br>"
                    f"nD materials: {counts['nd_materials']}<br>"
                    f"RCLMS sections: {counts['sections']}<br>"
                    f"Selection sets: {counts['selection_sets']}<br>"
                    f"Fixed base nodes: {counts['fixed_nodes']}"
                )
            else:
                dependency_text = (
                    "Existing FSAM references: 2"
                    if formulation == "SFI_MVLEM"
                    else f"New uniaxial fiber materials: "
                    f"{counts['uniaxial_materials']} + existing shear material"
                )
                object_text = (
                    "<b>Objects to be created</b><br>"
                    f"Host nodes: {counts['host_nodes']}<br>"
                    f"{formulation} elements: {counts['wall_elements']}<br>"
                    f"{dependency_text}<br>"
                    f"Selection sets: {counts['selection_sets']}<br>"
                    f"Fixed base nodes: {counts['fixed_nodes']}"
                )
            self.preview_object_summary.setText(object_text)

            if formulation == "MEFI":
                truss_text = (
                    self.boundary_truss_type.currentText()
                    if reinforcement_mode in {"hybrid", "fully_discrete"}
                    else "—"
                )
                material_text = (
                    "<b>Materials & Sections</b><br>"
                    "Uniaxial: Steel02 ×3 · Concrete02 ×2<br>"
                    "nD: OrthotropicRAConcrete ×2 · "
                    "SmearedSteelDoubleLayer ×2"
                    + (
                        " (ratios = 0)"
                        if reinforcement_mode == "fully_discrete"
                        else ""
                    )
                    + "<br>"
                    "Sections: RCLMS Web (1 layer) · "
                    "RCLMS Boundary (2 layers)<br>"
                    f"Discrete reinforcement formulation: {truss_text}<br>"
                    + self._rw_a20_material_status_html(
                        include_steel_x=True
                    )
                    + "<br>"
                    + (
                        "Coupling: ASDEmbeddedNodeElement · "
                        f"penalty factor "
                        f"{self.embedded_penalty_factor.value():g}"
                        if counts["embedded_coupling"]
                        else "Coupling: —"
                    )
                )
            elif formulation == "SFI_MVLEM":
                material_text = (
                    "<b>Materials & Dependencies</b><br>"
                    f"Web FSAM: {self.macro_web_fsam.currentText()}<br>"
                    f"Boundary FSAM: "
                    f"{self.macro_boundary_fsam.currentText()}<br>"
                    "Fiber mapping: Boundary | Web … Web | Boundary"
                )
            else:
                material_text = (
                    "<b>Materials & Dependencies</b><br>"
                    "Generated: Steel02 web/boundary + "
                    "Concrete02 web/boundary<br>"
                    + self._rw_a20_material_status_html(
                        include_steel_x=False
                    )
                    + "<br>"
                    f"Shear: {self.macro_shear_material.currentText()}<br>"
                    f"CoR c = {self.macro_center_ratio.value():g} · "
                    f"density = {self.macro_density.value():g}"
                    + (
                        f"<br>ThickMod = {self.macro_thick_mod.value():g} · "
                        f"ν = {self.macro_poisson.value():g}"
                        if formulation == "MVLEM_3D"
                        else ""
                    )
                )
            self.preview_material_summary.setText(material_text)

            selection_text = f"Base · Top · {formulation}"
            if counts["discrete_rebar"]:
                selection_text += " · Reinforcement"
            if counts["horizontal_rebar"]:
                selection_text += " · Horizontal Bars"
            if counts["vertical_rebar"]:
                selection_text += " · Vertical Web Bars"
            if counts["embedded_coupling"]:
                selection_text += " · Embedded Coupling"
            self.preview_selection_summary.setText(
                "<b>Selections & Boundary Conditions</b><br>"
                f"Named selections: {selection_text}<br>"
                + (
                    "Base nodes: all 6 DOF fixed<br>Top: two top panel nodes"
                    if formulation == "MVLEM_3D"
                    else (
                        "Base node: UX, UY, RZ fixed<br>"
                        "Top: one top centerline node"
                        if formulation in {"MVLEM", "SFI_MVLEM"}
                        else "Base nodes: UX, UY, RZ fixed<br>Top: two top wall nodes"
                    )
                )
            )

            validation_items = self._preview_validation_items()
            messages = [
                message
                for _key, message in validation_items
            ]
            if messages:
                self.preview_validation_status.setStyleSheet(
                    "padding: 9px; background: #fff0ee; color: #b42318; "
                    "font-weight: 600;"
                )
                category_labels = {
                    "geometry": "Geometry",
                    "boundary": "Boundary / reinforcement",
                    "web_rebar": "Web reinforcement",
                    "web_vertical": "Embedded vertical reinforcement",
                    "fully_discrete": "Fully discrete reinforcement",
                    "domain": "Project domain",
                    "macro": "Macro formulation",
                    "material": "Material dependency",
                }
                self.preview_validation_status.setText(
                    "<b>Preview check · needs attention</b><br>"
                    + "<br>".join(
                        f"• <b>{category_labels.get(key, 'Model')}:</b> "
                        f"{message}"
                        for key, message in validation_items
                    )
                )
            else:
                self.preview_validation_status.setStyleSheet(
                    "padding: 9px; background: #eaf7ee; color: #226b3a; "
                    "font-weight: 600;"
                )
                self.preview_validation_status.setText(
                    "✓ Preview check · Ready to create wall"
                )

            finish_button = self.button(
                QWizard.WizardButton.FinishButton
            )
            if finish_button is not None:
                finish_button.setEnabled(not messages)
                finish_button.setToolTip(
                    ""
                    if not messages
                    else "Resolve preview validation issues before creating."
                )

            base_text = (
                "both bottom nodes fixed in all 6 DOF"
                if formulation == "MVLEM_3D"
                else (
                    "bottom centerline node fixed in UX, UY and RZ"
                    if formulation in {"MVLEM", "SFI_MVLEM"}
                    else "both bottom nodes fixed in UX, UY and RZ"
                )
            )
            self.review.setText(
                "<b>Model definition</b><br>"
                f"Mode: {mode}<br>"
                f"Formulation: {formulation}<br>"
                + (
                    f"Vertical MEFI elements: {rows}<br>"
                    if formulation == "MEFI"
                    else f"Vertical {formulation} elements: {rows}<br>"
                )
                f"Macro-fibers: {count} · web fiber width "
                f"{web_width:g} {self.units.length}<br>"
                f"Mapping: <code>{mapping}</code><br>"
                f"Reinforcement: {reinforcement_text}<br>"
                f"Base: {base_text}.<br>"
                f"Named selections: Base · Top · {formulation}"
                + (" · Reinforcement" if counts["discrete_rebar"] else "")
                + (
                    " · Horizontal Bars"
                    if counts["horizontal_rebar"]
                    else ""
                )
                + (
                    " · Vertical Web Bars"
                    if counts["vertical_rebar"]
                    else ""
                )
                + (
                    " · Embedded Coupling"
                    if counts["embedded_coupling"]
                    else ""
                )
            )
        except (AttributeError, ZeroDivisionError, ValueError):
            self.preview_geometry_summary.setText(
                "Complete the previous pages to preview the wall."
            )
            self.preview_object_summary.setText("")
            self.preview_material_summary.setText("")
            self.preview_selection_summary.setText("")
            self.preview_validation_status.setText("")
            finish_button = self.button(
                QWizard.WizardButton.FinishButton
            )
            if finish_button is not None:
                finish_button.setEnabled(False)
            self.review.setText("")
