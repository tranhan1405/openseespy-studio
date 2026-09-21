from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..frp_column import (
    CONCRETE_TYPES,
    REBAR_TYPES,
    FRPColumnBuildResult,
    FRPColumnSpec,
    build_frp_rc_column,
)
from ..project import MATERIAL_DEFAULTS, MaterialData
from ..units import UnitSystem
from .material_test_dialog import MaterialTestDialog


PA_PER_MPA = 1.0e6


def _spin(
    value: float,
    *,
    minimum: float = -1.0e20,
    maximum: float = 1.0e20,
    decimals: int = 8,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(minimum, maximum)
    spin.setValue(float(value))
    return spin


class FRPColumnPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.shape = "Circular"
        self.diameter = 400.0
        self.height_value = 400.0
        self.width_value = 400.0
        self.cover = 35.0
        self.bar_diameter = 16.0
        self.circular_bars = 8
        self.bars_top = 3
        self.bars_bottom = 3
        self.side_bars_each = 2
        self.layers = 2

    def set_spec(self, spec: FRPColumnSpec) -> None:
        self.shape = spec.shape
        self.diameter = spec.diameter
        self.height_value = spec.height
        self.width_value = spec.width
        self.cover = spec.cover
        self.bar_diameter = spec.bar_diameter
        self.circular_bars = spec.circular_bars
        self.bars_top = spec.bars_top
        self.bars_bottom = spec.bars_bottom
        self.side_bars_each = spec.side_bars_each
        self.layers = spec.frp_layers
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#ccd6df"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        box = QRectF(70, 45, max(100, self.width() - 140), max(100, self.height() - 105))
        span = (
            self.diameter
            if self.shape == "Circular"
            else max(self.height_value, self.width_value)
        )
        if span <= 0.0:
            return
        scale = min(box.width(), box.height()) / span * 0.82
        center = box.center()

        painter.setPen(QPen(QColor("#8e44ad"), 5.0))
        painter.setBrush(QColor("#f6f7f8"))
        if self.shape == "Circular":
            d = self.diameter * scale
            outer = QRectF(center.x() - d / 2, center.y() - d / 2, d, d)
            painter.drawEllipse(outer)
            core_d = max(0.0, self.diameter - 2.0 * self.cover) * scale
            painter.setPen(QPen(QColor("#758596"), 1.5, Qt.DashLine))
            painter.drawEllipse(
                QRectF(
                    center.x() - core_d / 2,
                    center.y() - core_d / 2,
                    core_d,
                    core_d,
                )
            )

            radius = max(
                0.0,
                0.5 * self.diameter - self.cover - 0.5 * self.bar_diameter,
            ) * scale
            painter.setBrush(QColor("#17356d"))
            painter.setPen(Qt.NoPen)
            bar_radius = max(3.0, 0.5 * self.bar_diameter * scale)
            for index in range(max(1, self.circular_bars)):
                theta = 2.0 * math.pi * index / max(1, self.circular_bars)
                point = QPointF(
                    center.x() + radius * math.sin(theta),
                    center.y() - radius * math.cos(theta),
                )
                painter.drawEllipse(point, bar_radius, bar_radius)
        else:
            h = self.height_value * scale
            w = self.width_value * scale
            outer = QRectF(center.x() - w / 2, center.y() - h / 2, w, h)
            painter.drawRect(outer)
            inset = self.cover * scale
            painter.setPen(QPen(QColor("#758596"), 1.5, Qt.DashLine))
            painter.drawRect(outer.adjusted(inset, inset, -inset, -inset))

            offset = (self.cover + 0.5 * self.bar_diameter) * scale
            left = outer.left() + offset
            right = outer.right() - offset
            top = outer.top() + offset
            bottom = outer.bottom() - offset
            painter.setBrush(QColor("#17356d"))
            painter.setPen(Qt.NoPen)
            br = max(3.0, 0.5 * self.bar_diameter * scale)

            def row_points(count: int, y: float) -> None:
                if count <= 1:
                    xs = [0.5 * (left + right)]
                else:
                    xs = [
                        left + (right - left) * i / (count - 1)
                        for i in range(count)
                    ]
                for x in xs:
                    painter.drawEllipse(QPointF(x, y), br, br)

            row_points(max(1, self.bars_top), top)
            row_points(max(1, self.bars_bottom), bottom)
            for index in range(1, self.side_bars_each + 1):
                ratio = index / (self.side_bars_each + 1)
                y = bottom + (top - bottom) * ratio
                painter.drawEllipse(QPointF(left, y), br, br)
                painter.drawEllipse(QPointF(right, y), br, br)

        painter.setPen(QColor("#7b2f91"))
        painter.drawText(
            QRectF(12, 10, self.width() - 24, 26),
            Qt.AlignCenter,
            f"External FRP jacket · {self.layers} layer(s)",
        )
        painter.setPen(QColor("#637487"))
        painter.drawText(
            QRectF(12, self.height() - 38, self.width() - 24, 24),
            Qt.AlignCenter,
            "Purple = FRP jacket · dashed = nominal core boundary · blue = rebars",
        )


class FRPColumnWizardDialog(QDialog):
    def __init__(
        self,
        materials: dict[int, MaterialData],
        *,
        section_tag: int,
        section_name: str,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("RC Column + FRP Retrofit Wizard")
        self.setModal(True)
        self.resize(920, 760)
        self.materials = dict(materials)
        self.unit_system = UnitSystem.from_mapping(units)
        self.section_tag = int(section_tag)
        self.section_name = str(section_name).strip() or (
            f"FRP RC Column {section_tag}"
        )

        root = QVBoxLayout(self)
        intro = QLabel(
            "Build an RC Fiber section and its FRP-confined concrete material "
            "together. Circular columns use FRPConfinedConcrete02 JacketC. "
            "Rectangular columns use Ultimate mode, so fcu/ecu must come from "
            "the confinement model adopted in your research."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(intro)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_geometry_tab()
        self._build_material_tab()
        self._build_frp_tab()
        self._build_preview_tab()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.test_button = buttons.addButton(
            "Test FRP Material...",
            QDialogButtonBox.ActionRole,
        )
        self.test_button.clicked.connect(self._test_frp_material)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.shape.currentTextChanged.connect(self._sync_shape)
        self.concrete_source.currentIndexChanged.connect(self._sync_material_sources)
        self.rebar_source.currentIndexChanged.connect(self._sync_material_sources)
        self._connect_preview_updates()
        self._sync_shape()
        self._sync_material_sources()
        self._update_preview()

    def _build_geometry_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)
        form = QFormLayout()

        self.shape = QComboBox()
        self.shape.addItems(["Circular", "Rectangular"])
        form.addRow("Column shape:", self.shape)

        self.geometry_stack = QStackedWidget()

        circle = QWidget()
        circle_form = QFormLayout(circle)
        self.diameter = _spin(400.0, minimum=1.0)
        circle_form.addRow(f"Diameter [{self.unit_system.length}]:", self.diameter)
        self.circular_bars = QSpinBox()
        self.circular_bars.setRange(1, 200)
        self.circular_bars.setValue(8)
        circle_form.addRow("Longitudinal bars:", self.circular_bars)
        self.n_radial = QSpinBox()
        self.n_radial.setRange(1, 200)
        self.n_radial.setValue(12)
        self.n_circum = QSpinBox()
        self.n_circum.setRange(4, 500)
        self.n_circum.setValue(48)
        circle_form.addRow("Radial fibers:", self.n_radial)
        circle_form.addRow("Circumferential fibers:", self.n_circum)
        self.geometry_stack.addWidget(circle)

        rect = QWidget()
        rect_form = QFormLayout(rect)
        self.height = _spin(400.0, minimum=1.0)
        self.width = _spin(400.0, minimum=1.0)
        rect_form.addRow(f"Height [{self.unit_system.length}]:", self.height)
        rect_form.addRow(f"Width [{self.unit_system.length}]:", self.width)
        self.bars_top = QSpinBox()
        self.bars_top.setRange(1, 100)
        self.bars_top.setValue(3)
        self.bars_bottom = QSpinBox()
        self.bars_bottom.setRange(1, 100)
        self.bars_bottom.setValue(3)
        self.side_bars = QSpinBox()
        self.side_bars.setRange(0, 100)
        self.side_bars.setValue(2)
        rect_form.addRow("Top-row bars:", self.bars_top)
        rect_form.addRow("Bottom-row bars:", self.bars_bottom)
        rect_form.addRow("Intermediate bars / side:", self.side_bars)
        self.n_y = QSpinBox()
        self.n_y.setRange(1, 300)
        self.n_y.setValue(24)
        self.n_z = QSpinBox()
        self.n_z.setRange(1, 300)
        self.n_z.setValue(24)
        rect_form.addRow("Fibers along y:", self.n_y)
        rect_form.addRow("Fibers along z:", self.n_z)
        self.geometry_stack.addWidget(rect)

        form.addRow("Geometry:", self.geometry_stack)

        self.cover = _spin(35.0, minimum=0.0)
        self.bar_diameter = _spin(16.0, minimum=0.1)
        self.gj = _spin(1.0e6, minimum=0.0)
        form.addRow(f"Concrete cover [{self.unit_system.length}]:", self.cover)
        form.addRow(f"Bar diameter [{self.unit_system.length}]:", self.bar_diameter)
        form.addRow(
            f"GJ [{self.unit_system.force}·{self.unit_system.length}²]:",
            self.gj,
        )

        root.addLayout(form)
        root.addStretch(1)
        self.tabs.addTab(page, "1 · Geometry")

    def _build_material_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)

        concrete_group = QGroupBox("Original concrete")
        concrete_layout = QVBoxLayout(concrete_group)
        concrete_form = QFormLayout()
        self.concrete_source = QComboBox()
        self.concrete_source.addItem("Create new Concrete02", "__new__")
        for tag in sorted(self.materials):
            material = self.materials[tag]
            if material.material_type in CONCRETE_TYPES:
                self.concrete_source.addItem(
                    f"{tag} - {material.name} ({material.material_type})",
                    tag,
                )
        concrete_form.addRow("Source:", self.concrete_source)
        concrete_layout.addLayout(concrete_form)

        defaults = MATERIAL_DEFAULTS["Concrete02"]
        self.concrete_inputs = QGroupBox("New Concrete02 parameters")
        cform = QFormLayout(self.concrete_inputs)
        self.fc = _spin(self.unit_system.engineering_stress_from_pa(defaults["fpc"]))
        self.epsc0 = _spin(defaults["epsc0"], decimals=10)
        self.fcu = _spin(self.unit_system.engineering_stress_from_pa(defaults["fpcu"]))
        self.epsu = _spin(defaults["epsU"], decimals=10)
        self.lambda_c = _spin(defaults["lambda"], decimals=8)
        self.ft = _spin(self.unit_system.engineering_stress_from_pa(defaults["ft"]))
        self.ets = _spin(self.unit_system.engineering_stress_from_pa(defaults["Ets"]))
        cform.addRow(f"fpc [{self.unit_system.engineering_stress_label}]:", self.fc)
        cform.addRow("epsc0:", self.epsc0)
        cform.addRow(f"fpcu [{self.unit_system.engineering_stress_label}]:", self.fcu)
        cform.addRow("epsU:", self.epsu)
        cform.addRow("lambda:", self.lambda_c)
        cform.addRow(f"ft [{self.unit_system.engineering_stress_label}]:", self.ft)
        cform.addRow(f"Ets [{self.unit_system.engineering_stress_label}]:", self.ets)
        concrete_layout.addWidget(self.concrete_inputs)
        root.addWidget(concrete_group)

        rebar_group = QGroupBox("Longitudinal reinforcement")
        rebar_layout = QVBoxLayout(rebar_group)
        rebar_form = QFormLayout()
        self.rebar_source = QComboBox()
        self.rebar_source.addItem("Create new ReinforcingSteel", "__new__")
        for tag in sorted(self.materials):
            material = self.materials[tag]
            if material.material_type in REBAR_TYPES:
                self.rebar_source.addItem(
                    f"{tag} - {material.name} ({material.material_type})",
                    tag,
                )
        rebar_form.addRow("Source:", self.rebar_source)
        rebar_layout.addLayout(rebar_form)

        steel = MATERIAL_DEFAULTS["ReinforcingSteel"]
        self.rebar_inputs = QGroupBox("New ReinforcingSteel parameters")
        sform = QFormLayout(self.rebar_inputs)
        self.fy = _spin(self.unit_system.engineering_stress_from_pa(steel["fy"]))
        self.fu = _spin(self.unit_system.engineering_stress_from_pa(steel["fu"]))
        self.es = _spin(self.unit_system.engineering_stress_from_pa(steel["Es"]))
        self.esh = _spin(self.unit_system.engineering_stress_from_pa(steel["Esh"]))
        self.eps_sh = _spin(steel["eps_sh"], decimals=10)
        self.eps_ult = _spin(steel["eps_ult"], decimals=10)
        sform.addRow(f"fy [{self.unit_system.engineering_stress_label}]:", self.fy)
        sform.addRow(f"fu [{self.unit_system.engineering_stress_label}]:", self.fu)
        sform.addRow(f"Es [{self.unit_system.engineering_stress_label}]:", self.es)
        sform.addRow(f"Esh [{self.unit_system.engineering_stress_label}]:", self.esh)
        sform.addRow("eps_sh:", self.eps_sh)
        sform.addRow("eps_ult:", self.eps_ult)
        rebar_layout.addWidget(self.rebar_inputs)
        root.addWidget(rebar_group)
        root.addStretch(1)
        self.tabs.addTab(page, "2 · RC Materials")

    def _build_frp_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)
        form = QFormLayout()

        self.frp_family = QComboBox()
        self.frp_family.addItems(["CFRP", "GFRP", "Custom"])
        self.frp_family.setCurrentText("Custom")
        self.layers = QSpinBox()
        self.layers.setRange(1, 100)
        self.layers.setValue(2)
        self.layer_t = _spin(
            self.unit_system.length_from_m(0.000167),
            minimum=1.0e-9,
            decimals=8,
        )
        self.efrp = _spin(
            self.unit_system.engineering_stress_from_pa(72_000.0 * PA_PER_MPA),
            minimum=1.0,
        )
        self.erup = _spin(0.015, minimum=1.0e-8, decimals=10)

        self.scope = QComboBox()
        self.scope.addItem(
            "Entire concrete section (external wrap)",
            "all_concrete",
        )
        self.scope.addItem(
            "Core only (simplified research idealization)",
            "core_only",
        )

        form.addRow("FRP family:", self.frp_family)
        form.addRow("Number of layers:", self.layers)
        form.addRow(
            f"Layer thickness [{self.unit_system.length}]:",
            self.layer_t,
        )
        form.addRow(f"Efrp [{self.unit_system.engineering_stress_label}]:", self.efrp)
        form.addRow("FRP rupture strain:", self.erup)
        form.addRow("Confinement assignment:", self.scope)
        root.addLayout(form)

        self.mode_note = QLabel()
        self.mode_note.setWordWrap(True)
        root.addWidget(self.mode_note)

        self.ultimate_group = QGroupBox(
            "Rectangular section · user-supplied confined ultimate point"
        )
        ultimate = QFormLayout(self.ultimate_group)
        self.ultimate_fcu = _spin(
            self.unit_system.engineering_stress_from_pa(-45.0 * PA_PER_MPA)
        )
        self.ultimate_ecu = _spin(-0.015, decimals=10)
        ultimate.addRow(f"fcu [{self.unit_system.engineering_stress_label}]:", self.ultimate_fcu)
        ultimate.addRow("ecu:", self.ultimate_ecu)
        root.addWidget(self.ultimate_group)

        tension_group = QGroupBox("FRP-confined concrete tension branch")
        tension = QFormLayout(tension_group)
        self.frp_ft = _spin(
            self.unit_system.engineering_stress_from_pa(3.0 * PA_PER_MPA)
        )
        self.frp_ets = _spin(
            self.unit_system.engineering_stress_from_pa(1500.0 * PA_PER_MPA)
        )
        tension.addRow(f"ft [{self.unit_system.engineering_stress_label}]:", self.frp_ft)
        tension.addRow(f"Ets [{self.unit_system.engineering_stress_label}]:", self.frp_ets)
        root.addWidget(tension_group)

        warning = QLabel(
            "CFRP/GFRP here is a descriptive family label only. Efrp, layer "
            "thickness and rupture strain remain explicit inputs; use the "
            "manufacturer/test values for the actual laminate."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "padding: 7px; background: #fff7e0; color: #7a5600;"
        )
        root.addWidget(warning)
        root.addStretch(1)
        self.tabs.addTab(page, "3 · FRP Retrofit")

    def _build_preview_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)
        self.preview = FRPColumnPreview()
        root.addWidget(self.preview, 1)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            "padding: 8px; background: #f5f7f9; color: #526578;"
        )
        root.addWidget(self.summary)
        self.tabs.addTab(page, "4 · Preview")

    def _connect_preview_updates(self) -> None:
        for combo in (
            self.frp_family,
            self.scope,
        ):
            combo.currentIndexChanged.connect(self._update_preview)
        for spin in (
            self.diameter,
            self.height,
            self.width,
            self.cover,
            self.bar_diameter,
            self.circular_bars,
            self.bars_top,
            self.bars_bottom,
            self.side_bars,
            self.n_radial,
            self.n_circum,
            self.n_y,
            self.n_z,
            self.layers,
            self.layer_t,
            self.efrp,
            self.erup,
            self.ultimate_fcu,
            self.ultimate_ecu,
            self.frp_ft,
            self.frp_ets,
            self.gj,
        ):
            spin.valueChanged.connect(self._update_preview)

    def _sync_shape(self, *args) -> None:
        circular = self.shape.currentText() == "Circular"
        self.geometry_stack.setCurrentIndex(0 if circular else 1)
        self.ultimate_group.setVisible(not circular)
        if circular:
            self.mode_note.setText(
                "Circular column: Studio will create FRPConfinedConcrete02 "
                "with JacketC using total jacket thickness, Efrp, rupture "
                "strain and the column radius."
            )
            self.mode_note.setStyleSheet(
                "padding: 7px; background: #eaf6ee; color: #276738;"
            )
        else:
            self.mode_note.setText(
                "Rectangular column: Studio will use Ultimate mode. It does "
                "not invent a rectangular FRP confinement equation; enter "
                "fcu and ecu from the model/calibration adopted in your study."
            )
            self.mode_note.setStyleSheet(
                "padding: 7px; background: #fff7e0; color: #7a5600;"
            )
        self._update_preview()

    def _sync_material_sources(self, *args) -> None:
        self.concrete_inputs.setVisible(
            self.concrete_source.currentData() == "__new__"
        )
        self.rebar_inputs.setVisible(
            self.rebar_source.currentData() == "__new__"
        )
        self._update_preview()

    def _spec(self) -> FRPColumnSpec:
        concrete_source = self.concrete_source.currentData()
        rebar_source = self.rebar_source.currentData()
        return FRPColumnSpec(
            section_tag=self.section_tag,
            section_name=self.section_name,
            shape=self.shape.currentText(),
            diameter=self.diameter.value(),
            height=self.height.value(),
            width=self.width.value(),
            cover=self.cover.value(),
            gj=self.gj.value(),
            concrete_material_tag=(
                None if concrete_source == "__new__" else int(concrete_source)
            ),
            create_concrete02=concrete_source == "__new__",
            concrete02_parameters={
                "fpc": self.unit_system.engineering_stress_to_pa(self.fc.value()),
                "epsc0": self.epsc0.value(),
                "fpcu": self.unit_system.engineering_stress_to_pa(self.fcu.value()),
                "epsU": self.epsu.value(),
                "lambda": self.lambda_c.value(),
                "ft": self.unit_system.engineering_stress_to_pa(self.ft.value()),
                "Ets": self.unit_system.engineering_stress_to_pa(self.ets.value()),
            },
            rebar_material_tag=(
                None if rebar_source == "__new__" else int(rebar_source)
            ),
            create_reinforcing_steel=rebar_source == "__new__",
            reinforcing_steel_parameters={
                "fy": self.unit_system.engineering_stress_to_pa(self.fy.value()),
                "fu": self.unit_system.engineering_stress_to_pa(self.fu.value()),
                "Es": self.unit_system.engineering_stress_to_pa(self.es.value()),
                "Esh": self.unit_system.engineering_stress_to_pa(self.esh.value()),
                "eps_sh": self.eps_sh.value(),
                "eps_ult": self.eps_ult.value(),
            },
            bar_diameter=self.bar_diameter.value(),
            circular_bars=self.circular_bars.value(),
            bars_top=self.bars_top.value(),
            bars_bottom=self.bars_bottom.value(),
            side_bars_each=self.side_bars.value(),
            n_radial=self.n_radial.value(),
            n_circum=self.n_circum.value(),
            n_y=self.n_y.value(),
            n_z=self.n_z.value(),
            frp_family=self.frp_family.currentText(),
            frp_layers=self.layers.value(),
            frp_layer_thickness_m=self.unit_system.length_to_m_value(
                self.layer_t.value()
            ),
            frp_modulus_pa=self.unit_system.engineering_stress_to_pa(self.efrp.value()),
            frp_rupture_strain=self.erup.value(),
            confinement_scope=str(self.scope.currentData()),
            ultimate_fcu_pa=self.unit_system.engineering_stress_to_pa(self.ultimate_fcu.value()),
            ultimate_ecu=self.ultimate_ecu.value(),
            tensile_strength_pa=self.unit_system.engineering_stress_to_pa(self.frp_ft.value()),
            tension_softening_pa=self.unit_system.engineering_stress_to_pa(self.frp_ets.value()),
        )

    def build_result(self) -> FRPColumnBuildResult:
        return build_frp_rc_column(
            self._spec(),
            self.materials,
            self.unit_system.as_mapping(),
        )

    def _update_preview(self, *args) -> None:
        try:
            spec = self._spec()
            self.preview.set_spec(spec)
            total_t = self.layers.value() * self.layer_t.value()
            mode = "JacketC" if spec.shape == "Circular" else "Ultimate"
            concrete = (
                "new Concrete02"
                if spec.create_concrete02
                else f"material {spec.concrete_material_tag}"
            )
            rebar = (
                "new ReinforcingSteel"
                if spec.create_reinforcing_steel
                else f"material {spec.rebar_material_tag}"
            )
            self.summary.setText(
                f"{spec.shape} RC column · concrete: {concrete} · "
                f"rebar: {rebar}\n"
                f"FRP: {spec.frp_family}, {spec.frp_layers} layer(s), "
                f"total t = {total_t:.6g} {self.unit_system.length}, "
                f"Efrp = {self.efrp.value():.6g} "
                f"{self.unit_system.engineering_stress_label}, "
                f"eps_fu = {spec.frp_rupture_strain:.6g}\n"
                f"Constitutive mode: {mode} · assignment: "
                f"{self.scope.currentText()}"
            )
            self.summary.setStyleSheet(
                "padding: 8px; background: #eaf6ee; color: #276738;"
            )
        except (TypeError, ValueError) as exc:
            self.summary.setText(str(exc))
            self.summary.setStyleSheet(
                "padding: 8px; background: #fff0f0; color: #9b2c2c;"
            )

    def _test_frp_material(self) -> None:
        try:
            result = self.build_result()
        except ValueError as exc:
            QMessageBox.warning(self, "FRP RC Column Wizard", str(exc))
            return
        materials = result.combined_materials(self.materials)
        dialog = MaterialTestDialog(
            materials[result.frp_material_tag],
            units=self.unit_system.as_mapping(),
            materials=materials,
            parent=self,
        )
        dialog.exec()

    def _validate_and_accept(self) -> None:
        try:
            self.build_result()
        except ValueError as exc:
            QMessageBox.warning(self, "FRP RC Column Wizard", str(exc))
            return
        self.accept()
