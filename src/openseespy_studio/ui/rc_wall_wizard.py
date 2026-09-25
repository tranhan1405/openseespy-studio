from __future__ import annotations

import math

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..project import ProjectDatabase
from ..rc_wall import RCWallSpec
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
        self.boundary_value = 0.2
        self.rows = 1
        self.fibers = 3
        self.reinforcement_mode = "smeared"
        self.boundary_bars = 0
        self.setMinimumHeight(190)

    def set_wall(
        self,
        *,
        width: float,
        height: float,
        boundary: float,
        rows: int,
        fibers: int,
        reinforcement_mode: str = "smeared",
        boundary_bars: int = 0,
    ) -> None:
        self.width_value = max(float(width), 1.0e-12)
        self.height_value = max(float(height), 1.0e-12)
        self.boundary_value = max(float(boundary), 0.0)
        self.rows = max(int(rows), 1)
        self.fibers = max(int(fibers), 3)
        self.reinforcement_mode = str(reinforcement_mode)
        self.boundary_bars = max(int(boundary_bars), 0)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 18.0
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

        painter.setPen(QPen(QColor("#49657f"), 1.2))
        painter.drawRect(
            int(left), int(top), int(wall_w), int(wall_h)
        )

        for row in range(1, self.rows):
            y = top + wall_h * row / self.rows
            painter.drawLine(
                int(left), int(y), int(left + wall_w), int(y)
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

        if self.reinforcement_mode == "hybrid" and self.boundary_bars:
            # Discrete boundary reinforcement is intentionally shown as
            # explicit red bars. Cap the preview count so very dense layouts
            # remain legible while the numerical input keeps the true count.
            preview_bars = min(self.boundary_bars, 12)
            painter.setPen(QPen(QColor("#d64545"), 2.2))
            inset = max(boundary_px * 0.12, 2.0)
            usable = max(boundary_px - 2.0 * inset, 1.0)
            for bar in range(preview_bars):
                fraction = (
                    0.5
                    if preview_bars == 1
                    else bar / (preview_bars - 1)
                )
                x_left = left + inset + usable * fraction
                x_right = left + wall_w - boundary_px + inset + usable * fraction
                painter.drawLine(
                    int(x_left), int(top),
                    int(x_left), int(top + wall_h),
                )
                painter.drawLine(
                    int(x_right), int(top),
                    int(x_right), int(top + wall_h),
                )

            # Blue guide lines communicate that the web steel remains a
            # smeared RCLMS field rather than individually meshed bars.
            painter.setPen(QPen(QColor("#2f80c9"), 1.0))
            web_left = left + boundary_px
            web_right = left + wall_w - boundary_px
            for index in range(1, 6):
                y = top + wall_h * index / 6.0
                painter.drawLine(
                    int(web_left), int(y),
                    int(web_right), int(y),
                )

        painter.setPen(QPen(QColor("#26394c"), 2.2))
        painter.drawLine(
            int(left),
            int(top + wall_h),
            int(left + wall_w),
            int(top + wall_h),
        )
        painter.end()


class RCWallWizard(QWizard):
    """Create a planar RC wall using OrthotropicRAConcrete/RCLMS/MEFI."""

    def __init__(
        self,
        project: ProjectDatabase,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)
        self._applying_preset = False
        self.setWindowTitle("RC Wall Wizard · MEFI / RCLMS")
        self.resize(760, 650)
        self.setOption(
            QWizard.WizardOption.NoBackButtonOnStartPage,
            True,
        )
        self.setButtonText(
            QWizard.WizardButton.FinishButton,
            "Generate Wall",
        )

        self._build_geometry_page()
        self._build_concrete_page()
        self._build_reinforcement_page()
        self._build_review_page()

        self.currentIdChanged.connect(
            lambda _page: self._update_review()
        )
        self._apply_rw_a20_preset()
        self._update_review()

    def _stress_display(self, value_pa: float) -> float:
        return self.units.engineering_stress_from_pa(value_pa)

    def _stress_store(self, value: float) -> float:
        return self.units.engineering_stress_to_pa(value)

    def _build_geometry_page(self) -> None:
        page = QWizardPage()
        page.setTitle("1 · Geometry & discretization")
        page.setSubTitle(
            "Planar 2D cantilever wall. V1 generates an ndm=2 / ndf=3 "
            "MEFI model. Choose Replace for a standalone wall or Append "
            "to place a wall at a project-space origin."
        )
        layout = QVBoxLayout(page)
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
        form.addRow("MEFI rows over height:", self.vertical_elements)
        form.addRow("Macro-fibers per MEFI element:", self.macro_fibers)
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
        form = QFormLayout(page)
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
        form = QFormLayout(page)
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
            "Hybrid · discrete boundary longitudinal steel",
            "hybrid",
        )
        self.boundary_bar_count = QSpinBox()
        self.boundary_bar_count.setRange(1, 200)
        self.boundary_bar_count.setValue(4)
        self.boundary_bar_diameter = _double(16.0, 1.0e-9)
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
        form.addRow(
            "Discrete element formulation:",
            self.boundary_truss_type,
        )

        note = QLabel(
            "Hybrid V1 moves part of boundary vertical steel from the "
            "smeared RCLMS ratio into discrete Truss/CorotTruss elements. "
            "The discrete bars share the MEFI edge nodes (perfect bond), and "
            "SARE automatically subtracts their area from boundary rho-y to "
            "avoid double-counting. V1 is edge-lumped: one truss line per "
            "boundary represents the total selected bar area."
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
        self.boundary_bar_count.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.boundary_bar_diameter.valueChanged.connect(
            lambda _value: self._update_preview()
        )
        self.rho_y_boundary.valueChanged.connect(
            lambda _value: self._update_reinforcement_info()
        )
        self._sync_reinforcement_mode()

        self.addPage(page)

    def _reinforcement_mode_changed(self, *_args) -> None:
        self._mark_custom()
        self._sync_reinforcement_mode()

    def _sync_reinforcement_mode(self) -> None:
        enabled = (
            str(self.reinforcement_mode.currentData()) == "hybrid"
        )
        self.boundary_bar_count.setEnabled(enabled)
        self.boundary_bar_diameter.setEnabled(enabled)
        self.boundary_truss_type.setEnabled(enabled)
        self._update_reinforcement_info()
        self._update_preview()
        self._update_review()

    def _update_reinforcement_info(self) -> None:
        if not hasattr(self, "reinforcement_info"):
            return
        if self.reinforcement_mode.currentData() != "hybrid":
            self.reinforcement_info.setText(
                "All reinforcement is represented by RCLMS smeared ratios."
            )
            return

        count = int(self.boundary_bar_count.value())
        diameter = float(self.boundary_bar_diameter.value())
        boundary = float(self.boundary_width.value())
        thickness = float(self.thickness.value())
        area = count * math.pi * diameter * diameter / 4.0
        gross = boundary * thickness
        discrete_ratio = area / gross if gross > 0.0 else 0.0
        total_ratio = float(self.rho_y_boundary.value()) / 100.0
        remaining = total_ratio - discrete_ratio

        warning = ""
        if remaining < -1.0e-12:
            warning = (
                "<br><b style='color:#b42318'>Discrete steel exceeds total "
                "boundary rho-y.</b>"
            )
        self.reinforcement_info.setText(
            f"<b>Each boundary zone</b><br>"
            f"As,discrete = {area:g} {self.units.length}² "
            f"({count} × Ø{diameter:g})<br>"
            f"ρy,discrete = {100.0 * discrete_ratio:.4g}%<br>"
            f"ρy,smeared remaining = {100.0 * max(remaining, 0.0):.4g}%"
            + warning
        )

    def _build_review_page(self) -> None:
        page = QWizardPage()
        page.setTitle("4 · Review & generate")
        page.setSubTitle(
            "The generated objects are ordinary SARE objects and can be "
            "edited individually after the wizard closes."
        )
        layout = QVBoxLayout(page)
        self.review = QLabel()
        self.review.setWordWrap(True)
        self.review.setTextFormat(self.review.textFormat())
        self.review.setStyleSheet(
            "padding: 12px; background: #f7f9fb; color: #26394c;"
        )
        layout.addWidget(self.review)
        warning = QLabel(
            "V1 creates the physical wall model only. The RW-A20 preset uses "
            "7 physical-wall MEFI rows; the two loading-transfer rows in the "
            "full OpenSees benchmark are intentionally excluded. Gravity, "
            "pushover, cyclic and time-history analyses remain in SARE's "
            "normal Analysis workflow. In Custom mode, advanced Concrete02/"
            "Steel02 parameters not shown here retain the current starter "
            "values and remain editable as ordinary SARE materials after "
            "generation."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "padding: 8px; background: #fff7e0; color: #7a5600;"
        )
        layout.addWidget(warning)
        layout.addStretch(1)
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

    def _preset_changed(self, *_args) -> None:
        if self.preset.currentData() == "rw-a20":
            self._apply_rw_a20_preset()
        else:
            self._update_preview()
            self._update_review()

    def _update_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        self.preview.set_wall(
            width=float(self.width.value()),
            height=float(self.height.value()),
            boundary=float(self.boundary_width.value()),
            rows=int(self.vertical_elements.value()),
            fibers=int(self.macro_fibers.value()),
            reinforcement_mode=(
                str(self.reinforcement_mode.currentData())
                if hasattr(self, "reinforcement_mode")
                else "smeared"
            ),
            boundary_bars=(
                int(self.boundary_bar_count.value())
                if hasattr(self, "boundary_bar_count")
                else 0
            ),
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

        self.fc_web.setValue(self._stress_display(47.09e6))
        self.eps_web.setValue(-0.00232)
        self.fc_boundary.setValue(self._stress_display(53.78e6))
        self.eps_boundary.setValue(-0.00397)
        self.ft.setValue(self._stress_display(2.13e6))
        self.cracking_strain.setValue(0.00008)
        self.damage1.setValue(0.175)
        self.damage2.setValue(0.5)
        self.unconfined_layer.setValue(self._from_mm(50.8))

        self.steel_E.setValue(self._stress_display(200.0e9))
        self.fy_x.setValue(self._stress_display(469.93e6))
        self.fy_y_web.setValue(self._stress_display(409.71e6))
        self.fy_y_boundary.setValue(self._stress_display(429.78e6))
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

        return RCWallSpec(
            width=float(self.width.value()),
            height=float(self.height.value()),
            thickness=thickness,
            boundary_width=float(self.boundary_width.value()),
            origin_x=float(self.origin_x.value()),
            origin_y=float(self.origin_y.value()),
            vertical_elements=int(self.vertical_elements.value()),
            macro_fibers=int(self.macro_fibers.value()),
            steel_E=self._stress_store(self.steel_E.value()),
            steel_fx=self._stress_store(self.fy_x.value()),
            steel_fy_web=self._stress_store(self.fy_y_web.value()),
            steel_fy_boundary=self._stress_store(
                self.fy_y_boundary.value()
            ),
            concrete_fc_web=-abs(fc_web),
            concrete_eps_web=float(self.eps_web.value()),
            concrete_fc_boundary=-abs(fc_boundary),
            concrete_eps_boundary=float(self.eps_boundary.value()),
            concrete_ft=abs(ft),
            cracking_strain=float(self.cracking_strain.value()),
            damage_cte1=float(self.damage1.value()),
            damage_cte2=float(self.damage2.value()),
            rho_x_web=float(self.rho_x_web.value()) / 100.0,
            rho_y_web=float(self.rho_y_web.value()) / 100.0,
            rho_x_boundary=float(self.rho_x_boundary.value()) / 100.0,
            rho_y_boundary=float(self.rho_y_boundary.value()) / 100.0,
            reinforcement_mode=str(
                self.reinforcement_mode.currentData()
            ),
            boundary_bar_count=int(self.boundary_bar_count.value()),
            boundary_bar_diameter=float(
                self.boundary_bar_diameter.value()
            ),
            boundary_truss_type=str(
                self.boundary_truss_type.currentData()
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
                if (
                    not self.replace_geometry.isChecked()
                    and (
                        int(self.project.model.ndm),
                        int(self.project.model.ndf),
                    ) != (2, 3)
                ):
                    raise ValueError(
                        "Append mode requires the current project domain to "
                        "be ndm=2 / ndf=3."
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
                if self.reinforcement_mode.currentData() == "hybrid":
                    diameter = float(self.boundary_bar_diameter.value())
                    count = int(self.boundary_bar_count.value())
                    gross = (
                        float(self.boundary_width.value())
                        * float(self.thickness.value())
                    )
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

    def _update_review(self) -> None:
        if not hasattr(self, "review"):
            return
        try:
            width = float(self.width.value())
            boundary = float(self.boundary_width.value())
            count = int(self.macro_fibers.value())
            web_count = count - 2
            web_width = (width - 2.0 * boundary) / web_count
            valid = web_width > 0.0
            mapping = (
                "[B] " + " ".join("[W]" for _ in range(web_count)) + " [B]"
            )
            mode = (
                "Replace current FE model"
                if self.replace_geometry.isChecked()
                else "Append to current 2D model"
            )
            reinforcement_mode = str(
                self.reinforcement_mode.currentData()
            )
            reinforcement_text = "Smeared reinforcement only"
            if reinforcement_mode == "hybrid":
                diameter = float(self.boundary_bar_diameter.value())
                bars = int(self.boundary_bar_count.value())
                discrete_area = bars * math.pi * diameter * diameter / 4.0
                gross = (
                    float(self.boundary_width.value())
                    * float(self.thickness.value())
                )
                discrete_rho = (
                    100.0 * discrete_area / gross
                    if gross > 0.0 else 0.0
                )
                remaining = max(
                    0.0,
                    float(self.rho_y_boundary.value()) - discrete_rho,
                )
                reinforcement_text = (
                    f"Hybrid · {bars} × Ø{diameter:g} per boundary zone "
                    f"→ discrete rho-y {discrete_rho:.3g}% + "
                    f"smeared remainder {remaining:.3g}% · "
                    f"{self.boundary_truss_type.currentText()}"
                )

            text = (
                "<b>RC Wall V1 · MEFI / RCLMS</b><br><br>"
                f"Name: {self.wall_name.text().strip() or 'RC Wall'}<br>"
                f"Geometry: {width:g} × {self.height.value():g} × "
                f"{self.thickness.value():g} {self.units.length}<br>"
                f"Origin: ({self.origin_x.value():g}, "
                f"{self.origin_y.value():g}) {self.units.length}<br>"
                f"Vertical MEFI elements: {self.vertical_elements.value()}<br>"
                f"Macro-fibers: {count} · web fiber width "
                f"{web_width:g} {self.units.length}<br>"
                f"Mapping: <code>{mapping}</code><br>"
                f"Mode: {mode}<br>"
                f"Reinforcement: {reinforcement_text}<br><br>"
                "Generate chain:<br>"
                "5 uniaxial materials → 4 nD materials → "
                "2 RCLMS sections → MEFI wall mesh"
                + (
                    " + discrete boundary truss lines"
                    if reinforcement_mode == "hybrid"
                    else ""
                )
                + "<br><br>"
                "Base: both bottom nodes fixed in UX, UY and RZ.<br>"
                "Named selections: Base · Top · MEFI."
            )
            if not valid:
                text += (
                    "<br><br><b>Invalid:</b> boundary widths consume the "
                    "entire wall width."
                )
            self.review.setText(text)
        except (AttributeError, ZeroDivisionError, ValueError):
            self.review.setText("Complete the previous pages to review the wall.")
