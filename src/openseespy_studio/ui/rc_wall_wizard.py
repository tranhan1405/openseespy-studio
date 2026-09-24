from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
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
        self.setWindowTitle("RC Wall Wizard · MEFI / RCLMS")
        self.resize(760, 650)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)

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
            "MEFI model and replaces the current FE geometry."
        )
        layout = QVBoxLayout(page)
        form = QFormLayout()

        self.preset = QComboBox()
        self.preset.addItem(
            "RW-A20-P10-S38 · Tran & Wallace benchmark",
            "rw-a20",
        )
        self.preset.addItem("Custom / keep current values", "custom")
        self.preset.currentIndexChanged.connect(self._preset_changed)
        form.addRow("Preset:", self.preset)

        self.width = _double(1220.0, 1.0e-9)
        self.height = _double(2209.8, 1.0e-9)
        self.thickness = _double(152.4, 1.0e-9)
        self.boundary_width = _double(228.6, 1.0e-9)
        self.vertical_elements = QSpinBox()
        self.vertical_elements.setRange(1, 1000)
        self.vertical_elements.setValue(9)
        self.macro_fibers = QSpinBox()
        self.macro_fibers.setRange(3, 100)
        self.macro_fibers.setValue(8)

        length = self.units.length
        form.addRow(f"Wall width [{length}]:", self.width)
        form.addRow(f"Wall height [{length}]:", self.height)
        form.addRow(f"Wall thickness [{length}]:", self.thickness)
        form.addRow(f"Boundary width each side [{length}]:", self.boundary_width)
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
        layout.addStretch(1)

        for widget in (
            self.width,
            self.height,
            self.thickness,
            self.boundary_width,
            self.vertical_elements,
            self.macro_fibers,
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(
                    lambda _value: self._update_review()
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
        form.addRow("Boundary ρy [%]:", self.rho_y_boundary)

        note = QLabel(
            "Direction 1 is horizontal and direction 2 is vertical; "
            "orientation is generated as 0 rad. Separate vertical steel "
            "materials are created for web and boundary zones."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        form.addRow(note)

        self.addPage(page)

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
            "V1 creates the physical wall model only. Gravity, pushover, "
            "cyclic and time-history analyses remain in SARE's normal "
            "Analysis workflow."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "padding: 8px; background: #fff7e0; color: #7a5600;"
        )
        layout.addWidget(warning)
        layout.addStretch(1)
        self.addPage(page)

    def _preset_changed(self) -> None:
        if self.preset.currentData() == "rw-a20":
            self._apply_rw_a20_preset()

    def _apply_rw_a20_preset(self) -> None:
        self.width.setValue(1220.0)
        self.height.setValue(2209.8)
        self.thickness.setValue(152.4)
        self.boundary_width.setValue(228.6)
        self.vertical_elements.setValue(9)
        self.macro_fibers.setValue(8)

        self.fc_web.setValue(self._stress_display(47.09e6))
        self.eps_web.setValue(-0.00232)
        self.fc_boundary.setValue(self._stress_display(53.78e6))
        self.eps_boundary.setValue(-0.00397)
        self.ft.setValue(self._stress_display(2.13e6))
        self.cracking_strain.setValue(0.00008)
        self.damage1.setValue(0.175)
        self.damage2.setValue(0.5)
        self.unconfined_layer.setValue(50.8)

        self.steel_E.setValue(self._stress_display(200.0e9))
        self.fy_x.setValue(self._stress_display(469.93e6))
        self.fy_y_web.setValue(self._stress_display(409.71e6))
        self.fy_y_boundary.setValue(self._stress_display(429.78e6))
        self.rho_x_web.setValue(0.27)
        self.rho_y_web.setValue(0.27)
        self.rho_x_boundary.setValue(0.82)
        self.rho_y_boundary.setValue(3.23)
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
            boundary_unconfined_thickness=unconfined,
            boundary_confined_thickness=confined,
            name="RC Wall",
            replace_geometry=True,
        )

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
            text = (
                "<b>RC Wall V1 · MEFI / RCLMS</b><br><br>"
                f"Geometry: {width:g} × {self.height.value():g} × "
                f"{self.thickness.value():g} {self.units.length}<br>"
                f"Vertical MEFI elements: {self.vertical_elements.value()}<br>"
                f"Macro-fibers: {count} · web fiber width "
                f"{web_width:g} {self.units.length}<br>"
                f"Mapping: <code>{mapping}</code><br><br>"
                "Generate chain:<br>"
                "5 uniaxial materials → 4 nD materials → "
                "2 RCLMS sections → MEFI wall mesh<br><br>"
                "Base: both bottom nodes fixed in UX, UY and RZ."
            )
            if not valid:
                text += (
                    "<br><br><b>Invalid:</b> boundary widths consume the "
                    "entire wall width."
                )
            self.review.setText(text)
        except (AttributeError, ZeroDivisionError, ValueError):
            self.review.setText("Complete the previous pages to review the wall.")
