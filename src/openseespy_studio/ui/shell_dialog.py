from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..model import SHELL_ELEMENT_TYPES
from ..project import (
    ND_MATERIAL_DEFAULTS,
    ND_MATERIAL_PARAMETER_ORDER,
    NDMaterialData,
    nd_material_parameter_kind,
    nd_material_supports_plate_fiber,
    SECTION_DEFAULTS,
    SHELL_SECTION_TYPES,
    SectionData,
    ShellLayerData,
)
from ..shell_mesh import ShellMeshSpec, resolve_shell_mesh_divisions
from ..units import UnitSystem


def _float_spin(
    value: float,
    *,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 8,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setValue(float(value))
    return spin


class NDMaterialDialog(QDialog):
    """Editor for OpenSees nDMaterial definitions supported by SARE."""

    MATERIAL_TYPES = (
        ("Elastic isotropic", "ElasticIsotropic"),
        ("Elastic orthotropic", "ElasticOrthotropic"),
        ("J2 plasticity (von Mises)", "J2Plasticity"),
        ("Drucker-Prager", "DruckerPrager"),
        ("Pressure-independent multi-yield", "PressureIndependMultiYield"),
        ("Pressure-dependent multi-yield", "PressureDependMultiYield"),
        ("ASD concrete 3D", "ASDConcrete3D"),
        ("Orthotropic rotating-angle concrete", "OrthotropicRAConcrete"),
        ("Smeared steel double layer", "SmearedSteelDoubleLayer"),
    )

    PARAMETER_LABELS = {
        "E": "Elastic modulus E",
        "nu": "Poisson ratio ν",
        "rho": "Density ρ",
        "Ex": "Elastic modulus Ex",
        "Ey": "Elastic modulus Ey",
        "Ez": "Elastic modulus Ez",
        "nu_xy": "Poisson ratio νxy",
        "nu_yz": "Poisson ratio νyz",
        "nu_zx": "Poisson ratio νzx",
        "Gxy": "Shear modulus Gxy",
        "Gyz": "Shear modulus Gyz",
        "Gzx": "Shear modulus Gzx",
        "K": "Bulk modulus K",
        "G": "Shear modulus G",
        "sig0": "Initial yield stress σ0",
        "sigInf": "Saturation yield stress σ∞",
        "delta": "Exponential hardening δ",
        "H": "Linear hardening H",
        "sigmaY": "Yield stress σY",
        "rhoBar": "Plastic volume parameter ρbar",
        "Kinf": "Isotropic hardening K∞",
        "Ko": "Initial isotropic hardening K0",
        "delta1": "Isotropic hardening δ1",
        "delta2": "Tension softening δ2",
        "theta": "Hardening mix θ",
        "density": "Mass density",
        "atmPressure": "Atmospheric pressure",
        "nd": "Analysis dimension nd",
        "refShearModul": "Reference shear modulus Gr",
        "refBulkModul": "Reference bulk modulus Br",
        "cohesi": "Cohesion c",
        "peakShearStra": "Peak octahedral shear strain γmax",
        "frictionAng": "Friction angle Φ [deg]",
        "refPress": "Reference pressure p'r",
        "pressDependCoe": "Pressure-dependence coefficient d",
        "noYieldSurf": "Number of yield surfaces",
        "PTAng": "Phase transformation angle ΦPT [deg]",
        "contrac": "Contraction parameter",
        "dilat1": "Dilation parameter 1",
        "dilat2": "Dilation parameter 2",
        "liquefac1": "Liquefaction pressure threshold",
        "liquefac2": "Liquefaction strain parameter 2",
        "liquefac3": "Liquefaction bias parameter 3",
        "e": "Initial void ratio e",
        "cs1": "Critical-state parameter cs1",
        "cs2": "Critical-state parameter cs2",
        "cs3": "Critical-state parameter cs3",
        "pa": "Atmospheric normalization pressure pa",
        "c": "Numerical pressure constant c",
        "fc": "Compressive strength fc",
        "ft": "Tensile strength ft",
        "implex": "Use IMPL-EX (0/1)",
        "Kc": "Triaxial failure-surface coefficient Kc",
        "cdf": "Cross-damage factor cdf",
        "conc": "Referenced uniaxial concrete tag",
        "ecr": "Tension cracking strain ecr",
        "ec": "Compression peak strain ec",
        "DamageCte1": "Cyclic compression damage constant 1",
        "DamageCte2": "Cyclic compression damage constant 2",
        "mat1": "Uniaxial steel tag, direction 1",
        "mat2": "Uniaxial steel tag, direction 2",
        "ratio1": "Reinforcement ratio ρ1",
        "ratio2": "Reinforcement ratio ρ2",
        "orientation": "Layer orientation [rad]",
    }

    def __init__(
        self,
        *,
        next_tag: int,
        material: NDMaterialData | None = None,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit nD Material" if material is not None else "New nD Material"
        )
        self.setModal(True)
        self.setMinimumSize(500, 520)
        self.unit_system = UnitSystem.from_mapping(units)
        self._initial_material = material
        self._parameter_widgets: dict[str, QDoubleSpinBox] = {}

        root = QVBoxLayout(self)

        header = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(
            material.tag if material is not None else int(next_tag)
        )
        header.addRow("Tag:", self.tag)

        initial_type = (
            material.material_type
            if material is not None
            else "ElasticIsotropic"
        )
        self.name = QLineEdit(
            material.name
            if material is not None
            else f"{initial_type} {int(next_tag)}"
        )
        header.addRow("Name:", self.name)

        self.material_type = QComboBox()
        for label, value in self.MATERIAL_TYPES:
            self.material_type.addItem(label, value)
        index = self.material_type.findData(initial_type)
        if index >= 0:
            self.material_type.setCurrentIndex(index)
        header.addRow("OpenSees nDMaterial:", self.material_type)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.parameter_host = QWidget()
        self.parameter_form = QFormLayout(self.parameter_host)
        self.parameter_form.setFieldGrowthPolicy(
            QFormLayout.AllNonFixedFieldsGrow
        )
        scroll.setWidget(self.parameter_host)
        root.addWidget(scroll, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(
            "padding: 7px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(self.note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.material_type.currentIndexChanged.connect(
            self._material_type_changed
        )
        self._rebuild_parameters(
            material.parameters if material is not None else None
        )

    def _parameter_label(self, material_type: str, key: str) -> str:
        if material_type == "DruckerPrager" and key == "rho":
            base = "Frictional strength parameter ρ"
        else:
            base = self.PARAMETER_LABELS.get(key, key)
        kind = nd_material_parameter_kind(material_type, key)
        if kind == "stress":
            return f"{base} [{self.unit_system.engineering_stress_label}]:"
        if kind == "density":
            return (
                f"{base} "
                f"[{self.unit_system.engineering_density_label}]:"
            )
        return base + ":"

    def _display_value(
        self,
        material_type: str,
        key: str,
        value: float,
    ) -> float:
        kind = nd_material_parameter_kind(material_type, key)
        if kind == "stress":
            return self.unit_system.engineering_stress_from_pa(value)
        if kind == "density":
            return self.unit_system.engineering_density_from_kg_per_m3(
                value
            )
        return value

    def _stored_value(
        self,
        material_type: str,
        key: str,
        value: float,
    ) -> float:
        kind = nd_material_parameter_kind(material_type, key)
        if kind == "stress":
            return self.unit_system.engineering_stress_to_pa(value)
        if kind == "density":
            return self.unit_system.engineering_density_to_kg_per_m3(
                value
            )
        return value

    def _clear_parameter_form(self) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self._parameter_widgets.clear()

    def _rebuild_parameters(
        self,
        supplied: dict[str, float] | None = None,
    ) -> None:
        material_type = str(self.material_type.currentData())
        defaults = ND_MATERIAL_DEFAULTS[material_type]
        values = dict(defaults)
        if supplied:
            values.update({
                key: float(value)
                for key, value in supplied.items()
                if key in values
            })

        self._clear_parameter_form()
        for key in ND_MATERIAL_PARAMETER_ORDER[material_type]:
            kind = nd_material_parameter_kind(material_type, key)
            stored = float(values[key])
            shown = self._display_value(material_type, key, stored)
            low = -1.0e20
            high = 1.0e20
            decimals = 8
            if kind in {"stress", "density"}:
                low = 0.0
            if key == "nu":
                low, high, decimals = -0.999999, 0.499999, 6
            elif key in {"nu_xy", "nu_yz", "nu_zx"}:
                low, high, decimals = -0.999999, 0.999999, 6
            elif key in {"delta", "delta1", "delta2"}:
                low, decimals = 0.0, 8
            elif material_type == "DruckerPrager" and key in {
                "rho", "rhoBar", "theta",
            }:
                low, decimals = 0.0, 8
                if key == "theta":
                    high = 1.0
            elif material_type in {
                "PressureIndependMultiYield",
                "PressureDependMultiYield",
            }:
                if key == "nd":
                    low, high, decimals = 2.0, 3.0, 0
                elif key == "noYieldSurf":
                    low, high, decimals = 1.0, 39.0, 0
                elif key in {"frictionAng", "PTAng"}:
                    low, high, decimals = 0.0, 89.999999, 6
                elif key in {
                    "peakShearStra", "pressDependCoe", "contrac",
                    "dilat1", "dilat2", "liquefac2", "liquefac3",
                    "e", "cs1", "cs2", "cs3", "c",
                }:
                    low = 0.0
            elif material_type == "ASDConcrete3D":
                if key == "nu":
                    low, high, decimals = -0.999999, 0.499999, 6
                elif key == "implex":
                    low, high, decimals = 0.0, 1.0, 0
                elif key == "Kc":
                    low, high, decimals = 0.500001, 1.0, 6
                elif key in {"fc", "ft", "cdf"}:
                    low = 0.0
            elif material_type == "OrthotropicRAConcrete":
                if key == "conc":
                    low, high, decimals = 1.0, 2_147_483_647.0, 0
                elif key == "ecr":
                    low = 0.0
                elif key == "ec":
                    high = -1.0e-12
                elif key in {"DamageCte1", "DamageCte2"}:
                    low = 0.0
            elif material_type == "SmearedSteelDoubleLayer":
                if key in {"mat1", "mat2"}:
                    low, high, decimals = 1.0, 2_147_483_647.0, 0
                elif key in {"ratio1", "ratio2"}:
                    low, high = 0.0, 1.0

            widget = _float_spin(
                shown,
                low=low,
                high=high,
                decimals=decimals,
            )
            self._parameter_widgets[key] = widget
            self.parameter_form.addRow(
                self._parameter_label(material_type, key),
                widget,
            )

        if material_type == "ElasticIsotropic":
            text = (
                "Linear isotropic continuum material. Available in OpenSees "
                "including PlateFiber formulation for shell sections."
            )
        elif material_type == "ElasticOrthotropic":
            text = (
                "Linear orthotropic continuum material with independent "
                "directional elastic and shear moduli. OpenSees provides a "
                "PlateFiber formulation, so it can be used by SARE shell "
                "sections."
            )
        elif material_type == "J2Plasticity":
            text = (
                "Von Mises J2 plasticity with saturation plus linear "
                "isotropic hardening. K and G define the elastic response; "
                "σ0, σ∞, δ and H define yielding/hardening. OpenSees "
                "provides a PlateFiber formulation."
            )
        elif material_type == "DruckerPrager":
            text = (
                "Drucker-Prager pressure-sensitive plasticity. OpenSees "
                "documents ThreeDimensional and PlaneStrain formulations "
                "only; it is intentionally not available for PlateFiber "
                "shell sections in SARE."
            )
        elif material_type == "PressureIndependMultiYield":
            text = (
                "Pressure-independent multi-yield soil/clay model using "
                "automatic nested yield surfaces. OpenSees supports nd=2 "
                "(plane strain) or nd=3 (3D). Gravity/static loading is "
                "elastic; elastoplastic response requires updateMaterialStage. "
                "SARE currently supports positive automatic noYieldSurf only, "
                "not explicit custom surface pairs."
            )
        elif material_type == "PressureDependMultiYield":
            text = (
                "Pressure-dependent multi-yield sand/silt model with "
                "contraction, dilation and cyclic-mobility parameters. "
                "OpenSees supports nd=2 (plane strain) or nd=3 (3D). "
                "Gravity/static loading is elastic; elastoplastic response "
                "requires updateMaterialStage. SARE supports the automatic "
                "yield-surface form, including documented critical-state "
                "optional parameters, but not explicit custom surface pairs."
            )
        elif material_type == "ASDConcrete3D":
            text = (
                "3D plastic-damage concrete/masonry continuum model. "
                "This SARE V1 editor uses the robust scalar-strength profile "
                "(E, nu, rho, fc, ft, optional IMPL-EX, Kc and cdf); OpenSees "
                "can auto-generate tension/compression laws from fc and ft. "
                "Custom backbone lists, crack planes, viscosity and automatic "
                "regularization are intentionally left unsupported in V1."
            )
        elif material_type == "OrthotropicRAConcrete":
            text = (
                "Orthotropic rotating-angle plane-stress concrete layer for "
                "RC wall/membrane formulations. 'Referenced uniaxial concrete "
                "tag' must point to an existing concrete uniaxial material "
                "(for example Concrete02 or Concrete06). Cyclic compression "
                "damage constants default to the OpenSees values 0.14 and 0.6."
            )
        else:
            text = (
                "Two orthogonal smeared reinforcement layers for RC membrane "
                "models. mat1/mat2 reference existing uniaxial steel materials; "
                "ratio1/ratio2 are reinforcement ratios and orientation is in "
                "radians. This material is intended for RCLMS/MEFI workflows."
            )
        self.note.setText(text)

    def _material_type_changed(self, *_args) -> None:
        self._rebuild_parameters()

    def material_data(self) -> NDMaterialData:
        material_type = str(self.material_type.currentData())
        parameters = {
            key: self._stored_value(
                material_type,
                key,
                self._parameter_widgets[key].value(),
            )
            for key in ND_MATERIAL_PARAMETER_ORDER[material_type]
        }
        return NDMaterialData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"{material_type} {self.tag.value()}",
            material_type=material_type,
            parameters=parameters,
            source=(
                deepcopy(self._initial_material.source)
                if (
                    self._initial_material is not None
                    and self._initial_material.material_type == material_type
                )
                else {}
            ),
        )

    def _accept(self) -> None:
        try:
            self.material_data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "nD Material", str(exc))
            return
        self.accept()


class ShellSectionDialog(QDialog):
    """Elastic, PlateFiber, or layered shell-section editor."""

    SECTION_TYPES = (
        ("Elastic membrane plate", "ElasticMembranePlate"),
        ("PlateFiber", "PlateFiber"),
        ("LayeredShell", "LayeredShell"),
    )

    def __init__(
        self,
        *,
        next_tag: int | None = None,
        section: SectionData | None = None,
        nd_materials=None,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Shell Section" if section is not None
            else "New Shell Section"
        )
        self.setModal(True)
        self.setMinimumWidth(560)
        self.unit_system = UnitSystem.from_mapping(units)
        self._nd_materials = dict(nd_materials or {})
        self._staged_nd_materials: dict[int, NDMaterialData] = {}
        self._layers: list[ShellLayerData] = [
            ShellLayerData(layer.material_tag, layer.thickness)
            for layer in (section.shell_layers if section is not None else [])
        ]

        if (
            section is not None
            and section.section_type not in SHELL_SECTION_TYPES
        ):
            raise ValueError(
                f"Section {section.tag} is not a shell-compatible section."
            )

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(
            section.tag if section is not None else int(next_tag or 1)
        )
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            section.name if section is not None
            else f"Shell Section {int(next_tag or 1)}"
        )
        form.addRow("Name:", self.name)

        self.section_type = QComboBox()
        for label, value in self.SECTION_TYPES:
            self.section_type.addItem(label, value)
        if section is not None:
            index = self.section_type.findData(section.section_type)
            if index >= 0:
                self.section_type.setCurrentIndex(index)
        form.addRow("Shell section type:", self.section_type)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        # ElasticMembranePlate page.
        elastic_page = QWidget()
        elastic_form = QFormLayout(elastic_page)
        elastic_defaults = SECTION_DEFAULTS["ElasticMembranePlate"]
        elastic_p = (
            section.parameters
            if section is not None
            and section.section_type == "ElasticMembranePlate"
            else elastic_defaults
        )
        self.elastic_modulus = _float_spin(
            self.unit_system.engineering_stress_from_pa(
                float(elastic_p.get("E", elastic_defaults["E"]))
            ),
            low=1.0e-12,
        )
        elastic_form.addRow(
            f"E [{self.unit_system.engineering_stress_label}]:",
            self.elastic_modulus,
        )
        self.poisson = _float_spin(
            float(elastic_p.get("nu", elastic_defaults["nu"])),
            low=-0.999999,
            high=0.499999,
            decimals=6,
        )
        elastic_form.addRow("Poisson ratio ν:", self.poisson)
        elastic_thickness = (
            float(section.parameters["h"])
            if section is not None
            and section.section_type == "ElasticMembranePlate"
            else self.unit_system.length_from_m(0.20)
        )
        self.thickness = _float_spin(elastic_thickness, low=1.0e-12)
        elastic_form.addRow(
            f"Thickness h [{self.unit_system.length}]:",
            self.thickness,
        )
        self.density = _float_spin(
            float(elastic_p.get("rho", elastic_defaults["rho"])),
            low=0.0,
        )
        elastic_form.addRow("Mass density ρ [model mass/L³]:", self.density)
        self.ep_modifier = _float_spin(
            float(
                elastic_p.get(
                    "EpModifier",
                    elastic_defaults["EpModifier"],
                )
            ),
            low=1.0e-12,
            decimals=6,
        )
        elastic_form.addRow(
            "Out-of-plane E modifier:",
            self.ep_modifier,
        )
        self.pages.addWidget(elastic_page)

        # PlateFiber page.
        plate_page = QWidget()
        plate_form = QFormLayout(plate_page)
        plate_row = QHBoxLayout()
        self.plate_material = QComboBox()
        plate_row.addWidget(self.plate_material, 1)
        plate_new = QPushButton("New nD Material...")
        plate_new.clicked.connect(self._new_nd_material)
        plate_row.addWidget(plate_new)
        plate_form.addRow("nD Material:", plate_row)
        plate_thickness = (
            float(section.parameters["h"])
            if section is not None
            and section.section_type == "PlateFiber"
            else self.unit_system.length_from_m(0.20)
        )
        self.plate_thickness = _float_spin(
            plate_thickness,
            low=1.0e-12,
        )
        plate_form.addRow(
            f"Thickness h [{self.unit_system.length}]:",
            self.plate_thickness,
        )
        plate_note = QLabel(
            "PlateFiber integrates the selected nD material through the "
            "shell thickness and enables material-level stress/strain "
            "responses."
        )
        plate_note.setWordWrap(True)
        plate_form.addRow(plate_note)
        self.pages.addWidget(plate_page)

        # LayeredShell page.
        layered_page = QWidget()
        layered_layout = QVBoxLayout(layered_page)
        layer_input = QHBoxLayout()
        self.layer_material = QComboBox()
        layer_input.addWidget(self.layer_material, 1)
        self.layer_thickness = _float_spin(
            self.unit_system.length_from_m(0.05),
            low=1.0e-12,
        )
        self.layer_thickness.setMaximumWidth(130)
        layer_input.addWidget(self.layer_thickness)
        add_layer = QPushButton("Add Layer")
        add_layer.clicked.connect(self._add_layer)
        layer_input.addWidget(add_layer)
        new_layer_material = QPushButton("New nD Material...")
        new_layer_material.clicked.connect(self._new_nd_material)
        layer_input.addWidget(new_layer_material)
        layered_layout.addLayout(layer_input)

        self.layer_table = QTableWidget(0, 3)
        self.layer_table.setHorizontalHeaderLabels(
            ["Layer", "nD Material", f"Thickness [{self.unit_system.length}]"]
        )
        self.layer_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.layer_table.horizontalHeader().setStretchLastSection(True)
        layered_layout.addWidget(self.layer_table, 1)
        remove_layer = QPushButton("Remove Selected Layer")
        remove_layer.clicked.connect(self._remove_layer)
        layered_layout.addWidget(remove_layer)
        self.pages.addWidget(layered_page)

        self.section_type.currentIndexChanged.connect(
            self._sync_section_page
        )
        self._refresh_nd_material_choices()
        if (
            section is not None
            and section.section_type == "PlateFiber"
            and section.nd_material_tag is not None
        ):
            index = self.plate_material.findData(section.nd_material_tag)
            if index >= 0:
                self.plate_material.setCurrentIndex(index)
        self._refresh_layer_table()
        self._sync_section_page()

        note = QLabel(
            "Shell scope in SARE ends at surface elements. "
            "ElasticMembranePlate is the simple elastic option; PlateFiber "
            "and LayeredShell provide the nonlinear-shell foundation without "
            "adding solid/brick elements."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _all_nd_materials(self) -> dict[int, NDMaterialData]:
        result = dict(self._nd_materials)
        result.update(self._staged_nd_materials)
        return result

    def _refresh_nd_material_choices(self) -> None:
        plate_current = self.plate_material.currentData()
        layer_current = self.layer_material.currentData()
        for combo in (self.plate_material, self.layer_material):
            combo.clear()
            for tag, material in sorted(self._all_nd_materials().items()):
                if not nd_material_supports_plate_fiber(
                    material.material_type
                ):
                    continue
                combo.addItem(
                    f"{tag} - {material.name} ({material.material_type})",
                    int(tag),
                )
        for combo, current in (
            (self.plate_material, plate_current),
            (self.layer_material, layer_current),
        ):
            if current is not None:
                index = combo.findData(int(current))
                if index >= 0:
                    combo.setCurrentIndex(index)

    def _next_staged_nd_material_tag(self) -> int:
        return max(
            set(self._nd_materials) | set(self._staged_nd_materials),
            default=0,
        ) + 1

    def _new_nd_material(self) -> None:
        dialog = NDMaterialDialog(
            next_tag=self._next_staged_nd_material_tag(),
            units=self.unit_system.as_mapping(),
            parent=self,
        )
        if not dialog.exec():
            return
        material = dialog.material_data()
        if not nd_material_supports_plate_fiber(material.material_type):
            QMessageBox.warning(
                self,
                "nD Material",
                f"{material.material_type} is not compatible with "
                "PlateFiber shell sections. Create it from the Model "
                "nD Materials workflow for continuum use instead.",
            )
            return
        if material.tag in self._all_nd_materials():
            QMessageBox.warning(
                self,
                "nD Material",
                f"nDMaterial tag {material.tag} already exists.",
            )
            return
        self._staged_nd_materials[material.tag] = material
        self._refresh_nd_material_choices()
        for combo in (self.plate_material, self.layer_material):
            index = combo.findData(material.tag)
            if index >= 0:
                combo.setCurrentIndex(index)

    def staged_nd_materials(self) -> list[NDMaterialData]:
        return [
            self._staged_nd_materials[tag]
            for tag in sorted(self._staged_nd_materials)
        ]

    def _sync_section_page(self, *_args) -> None:
        section_type = str(self.section_type.currentData())
        page_index = {
            "ElasticMembranePlate": 0,
            "PlateFiber": 1,
            "LayeredShell": 2,
        }[section_type]
        self.pages.setCurrentIndex(page_index)

    def _add_layer(self) -> None:
        material_tag = self.layer_material.currentData()
        if material_tag is None:
            QMessageBox.warning(
                self,
                "LayeredShell",
                "Create or choose an nD Material first.",
            )
            return
        self._layers.append(
            ShellLayerData(
                int(material_tag),
                self.layer_thickness.value(),
            )
        )
        self._refresh_layer_table()

    def _remove_layer(self) -> None:
        row = self.layer_table.currentRow()
        if row < 0 or row >= len(self._layers):
            return
        self._layers.pop(row)
        self._refresh_layer_table()

    def _refresh_layer_table(self) -> None:
        self.layer_table.setRowCount(len(self._layers))
        materials = self._all_nd_materials()
        for row, layer in enumerate(self._layers):
            material = materials.get(int(layer.material_tag))
            label = (
                f"{layer.material_tag} - {material.name}"
                if material is not None
                else f"{layer.material_tag} (missing)"
            )
            self.layer_table.setItem(
                row,
                0,
                QTableWidgetItem(str(row + 1)),
            )
            self.layer_table.setItem(row, 1, QTableWidgetItem(label))
            self.layer_table.setItem(
                row,
                2,
                QTableWidgetItem(f"{layer.thickness:g}"),
            )

    def section_data(self) -> SectionData:
        section_type = str(self.section_type.currentData())
        common = {
            "tag": self.tag.value(),
            "name": self.name.text().strip()
            or f"Shell Section {self.tag.value()}",
            "section_type": section_type,
        }
        if section_type == "ElasticMembranePlate":
            return SectionData(
                **common,
                parameters={
                    "E": self.unit_system.engineering_stress_to_pa(
                        self.elastic_modulus.value()
                    ),
                    "nu": self.poisson.value(),
                    "h": self.thickness.value(),
                    "rho": self.density.value(),
                    "EpModifier": self.ep_modifier.value(),
                },
            )
        if section_type == "PlateFiber":
            material_tag = self.plate_material.currentData()
            if material_tag is None:
                raise ValueError(
                    "PlateFiber requires an nD Material. "
                    "Use 'New nD Material...' to define one here."
                )
            return SectionData(
                **common,
                parameters={"h": self.plate_thickness.value()},
                nd_material_tag=int(material_tag),
            )
        return SectionData(
            **common,
            shell_layers=[
                ShellLayerData(layer.material_tag, layer.thickness)
                for layer in self._layers
            ],
        )

    def _accept(self) -> None:
        try:
            section = self.section_data()
            available = self._all_nd_materials()
            missing = sorted(
                tag
                for tag in section.shell_nd_material_tags()
                if tag not in available
            )
            if missing:
                raise ValueError(
                    "Shell section references missing nDMaterial tag(s): "
                    + ", ".join(map(str, missing))
                )
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Shell Section", str(exc))
            return
        self.accept()


class ShellElementDialog(QDialog):
    """Create one four-node quadrilateral shell element."""

    FORMULATIONS = (
        "ASDShellQ4",
        "ShellMITC4",
        "ShellDKGQ",
        "ShellNLDKGQ",
    )

    def __init__(
        self,
        *,
        tag: int,
        nodes,
        sections,
        initial_nodes=(),
        element=None,
        new_section_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Direct Shell Element" if element is not None
            else "Create Direct Shell Element"
        )
        self.setModal(True)
        self.setMinimumWidth(500)
        self._nodes = dict(nodes or {})
        self._sections = {
            int(section_tag): section
            for section_tag, section in dict(sections or {}).items()
            if section.section_type in SHELL_SECTION_TYPES
        }
        self._new_section_callback = new_section_callback

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(element.tag if element is not None else int(tag))
        form.addRow("Tag:", self.tag)

        selected = list(initial_nodes or ())
        if element is not None:
            selected = list(element.node_tags())
        fallback = sorted(self._nodes)
        while len(selected) < 4:
            candidate = next(
                (node_tag for node_tag in fallback if node_tag not in selected),
                None,
            )
            if candidate is None:
                break
            selected.append(candidate)

        self.node_combos: list[QComboBox] = []
        for index, label in enumerate(("Node 1:", "Node 2:", "Node 3:", "Node 4:")):
            combo = QComboBox()
            for node_tag in sorted(self._nodes):
                node = self._nodes[node_tag]
                x, y, z = node.xyz
                combo.addItem(
                    f"{node_tag}  ({x:g}, {y:g}, {z:g})",
                    int(node_tag),
                )
            if index < len(selected):
                wanted = combo.findData(int(selected[index]))
                if wanted >= 0:
                    combo.setCurrentIndex(wanted)
            self.node_combos.append(combo)
            form.addRow(label, combo)

        self.formulation = QComboBox()
        self.formulation.addItems(list(self.FORMULATIONS))
        if element is not None and element.element_type in SHELL_ELEMENT_TYPES:
            self.formulation.setCurrentText(element.element_type)
        form.addRow("Formulation:", self.formulation)

        self.section = QComboBox()
        self.section_new = QPushButton("New Shell Section...")
        self.section_new.setEnabled(callable(self._new_section_callback))
        self.section_new.setToolTip(
            "Define a shell-compatible Section without closing this dialog."
        )
        self.section_new.clicked.connect(self._create_section_dependency)
        section_holder = QWidget()
        section_row = QHBoxLayout(section_holder)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(4)
        section_row.addWidget(self.section, 1)
        section_row.addWidget(self.section_new)
        self._refresh_section_choices(
            int(element.section_tag)
            if element is not None and element.section_tag is not None
            else None
        )
        form.addRow("Shell section:", section_holder)

        self.corotational = QCheckBox(
            "Corotational kinematics (large displacement/rotation)"
        )
        self.corotational.setChecked(
            bool(getattr(element, "shell_corotational", False))
            if element is not None
            else False
        )
        form.addRow("", self.corotational)

        self.no_eas = QCheckBox(
            "Disable enhanced assumed strain (-noeas)"
        )
        self.no_eas.setChecked(
            bool(getattr(element, "shell_no_eas", False))
            if element is not None
            else False
        )
        form.addRow("", self.no_eas)

        self.use_drilling_stab = QCheckBox(
            "Override drilling stabilization (-drillingStab)"
        )
        existing_drilling_stab = (
            getattr(element, "shell_drilling_stab", None)
            if element is not None
            else None
        )
        self.use_drilling_stab.setChecked(
            existing_drilling_stab is not None
        )
        form.addRow("", self.use_drilling_stab)

        self.drilling_stab = _float_spin(
            (
                float(existing_drilling_stab)
                if existing_drilling_stab is not None
                else 0.01
            ),
            low=0.0,
            high=1.0e12,
            decimals=8,
        )
        form.addRow("Drilling stabilization:", self.drilling_stab)
        self.use_drilling_stab.toggled.connect(self._sync_formulation)

        self.drilling_nl = QCheckBox(
            "Nonlinear drilling constraint (-drillingNL)"
        )
        self.drilling_nl.setChecked(
            bool(getattr(element, "shell_drilling_nl", False))
            if element is not None
            else False
        )
        form.addRow("", self.drilling_nl)

        self.use_local_x = QCheckBox("Override ASDShellQ4 local X axis")
        existing_local = (
            getattr(element, "shell_local_x", None)
            if element is not None
            else None
        )
        self.use_local_x.setChecked(existing_local is not None)
        form.addRow("", self.use_local_x)

        local_row = QHBoxLayout()
        self.local_x_spins = [
            _float_spin(
                (
                    float(existing_local[index])
                    if existing_local is not None
                    else (1.0 if index == 0 else 0.0)
                ),
                low=-1.0e12,
                high=1.0e12,
            )
            for index in range(3)
        ]
        for label, spin in zip(("X", "Y", "Z"), self.local_x_spins):
            local_row.addWidget(QLabel(label))
            local_row.addWidget(spin)
        form.addRow("Local X vector:", local_row)
        self.use_local_x.toggled.connect(self._sync_formulation)

        self.formulation.currentTextChanged.connect(
            self._sync_formulation
        )
        self._sync_formulation()

        note = QLabel(
            "Node ordering must follow the shell boundary consistently "
            "(clockwise or counter-clockwise). Shells require ndm=3, ndf=6. "
            "ASDShellQ4 is the recommended default general-purpose element. "
            "This dialog creates one FE element directly; use Surface Geometry "
            "for reusable shapes and mapped meshing."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_section_choices(self, select_tag: int | None = None) -> None:
        current = self.section.currentData() if self.section.count() else None
        wanted = select_tag if select_tag is not None else current
        self.section.clear()
        self.section.addItem("Select Shell Section...", None)
        for section_tag in sorted(self._sections):
            section = self._sections[section_tag]
            self.section.addItem(
                f"{section_tag} - {section.name} ({section.section_type})",
                int(section_tag),
            )
        if wanted is not None:
            index = self.section.findData(int(wanted))
            if index >= 0:
                self.section.setCurrentIndex(index)
        elif self.section.count() == 2:
            self.section.setCurrentIndex(1)

    def _create_section_dependency(self) -> None:
        if not callable(self._new_section_callback):
            return
        section = self._new_section_callback()
        if section is None:
            return
        if section.section_type not in SHELL_SECTION_TYPES:
            QMessageBox.warning(
                self,
                "Shell Section",
                "The newly created Section is not shell-compatible.",
            )
            return
        self._sections[int(section.tag)] = section
        self._refresh_section_choices(int(section.tag))

    def _sync_formulation(self, *_args) -> None:
        is_asd = self.formulation.currentText() == "ASDShellQ4"
        self.corotational.setEnabled(is_asd)
        self.no_eas.setEnabled(is_asd)
        self.use_drilling_stab.setEnabled(is_asd)
        self.drilling_stab.setEnabled(
            is_asd and self.use_drilling_stab.isChecked()
        )
        self.drilling_nl.setEnabled(is_asd)
        self.use_local_x.setEnabled(is_asd)
        for spin in self.local_x_spins:
            spin.setEnabled(is_asd and self.use_local_x.isChecked())
        if not is_asd:
            self.corotational.setChecked(False)
            self.no_eas.setChecked(False)
            self.use_drilling_stab.setChecked(False)
            self.drilling_nl.setChecked(False)
            self.use_local_x.setChecked(False)

    def values(
        self,
    ) -> tuple[
        int,
        tuple[int, int, int, int],
        str,
        int,
        bool,
        tuple[float, float, float] | None,
        bool,
        float | None,
        bool,
    ]:
        node_tags = tuple(
            int(combo.currentData())
            for combo in self.node_combos
            if combo.currentData() is not None
        )
        if len(node_tags) != 4:
            raise ValueError("Shell element requires four node tags.")
        if len(set(node_tags)) != 4:
            raise ValueError("Shell element requires four distinct nodes.")
        section_tag = self.section.currentData()
        if section_tag is None:
            raise ValueError(
                "Shell element requires a shell-compatible Section."
            )
        formulation = self.formulation.currentText()
        if formulation not in SHELL_ELEMENT_TYPES:
            raise ValueError(
                f"Unsupported shell formulation: {formulation}"
            )
        local_x = None
        if formulation == "ASDShellQ4" and self.use_local_x.isChecked():
            local_x = tuple(
                float(spin.value())
                for spin in self.local_x_spins
            )
            if sum(value * value for value in local_x) <= 1.0e-24:
                raise ValueError("Shell local X vector cannot be zero.")
        drilling_stab = None
        if (
            formulation == "ASDShellQ4"
            and self.use_drilling_stab.isChecked()
        ):
            drilling_stab = float(self.drilling_stab.value())
        return (
            self.tag.value(),
            node_tags,
            formulation,
            int(section_tag),
            bool(self.corotational.isChecked()),
            local_x,
            bool(self.no_eas.isChecked()),
            drilling_stab,
            bool(self.drilling_nl.isChecked()),
        )

    def _accept(self) -> None:
        try:
            self.values()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Direct Shell Element", str(exc))
            return
        self.accept()


class ShellMeshDialog(QDialog):
    """Structured Nu x Nv mesh over four ordered corner nodes."""

    def __init__(
        self,
        *,
        nodes,
        sections,
        initial_nodes=(),
        new_section_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Mesh Shell Surface")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._nodes = dict(nodes or {})
        self._sections = {
            int(tag): section
            for tag, section in dict(sections or {}).items()
            if section.section_type in SHELL_SECTION_TYPES
        }
        self._new_section_callback = new_section_callback

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        selected = [
            int(tag)
            for tag in initial_nodes
            if int(tag) in self._nodes
        ]
        for tag in sorted(self._nodes):
            if len(selected) >= 4:
                break
            if tag not in selected:
                selected.append(tag)

        self.corner_combos: list[QComboBox] = []
        labels = (
            "Corner 1 · U0,V0:",
            "Corner 2 · U1,V0:",
            "Corner 3 · U1,V1:",
            "Corner 4 · U0,V1:",
        )
        for index, label in enumerate(labels):
            combo = QComboBox()
            for node_tag in sorted(self._nodes):
                x, y, z = self._nodes[node_tag].xyz
                combo.addItem(
                    f"{node_tag}  ({x:g}, {y:g}, {z:g})",
                    int(node_tag),
                )
            if index < len(selected):
                wanted = combo.findData(selected[index])
                if wanted >= 0:
                    combo.setCurrentIndex(wanted)
            self.corner_combos.append(combo)
            form.addRow(label, combo)

        self.mesh_mode = QComboBox()
        self.mesh_mode.addItem("By divisions (Nu × Nv)", "divisions")
        self.mesh_mode.addItem("By target element size", "target_size")
        form.addRow("Mesh sizing:", self.mesh_mode)

        self.divisions_u = QSpinBox()
        self.divisions_u.setRange(1, 500)
        self.divisions_u.setValue(4)
        form.addRow("Divisions U:", self.divisions_u)

        self.divisions_v = QSpinBox()
        self.divisions_v.setRange(1, 500)
        self.divisions_v.setValue(4)
        form.addRow("Divisions V:", self.divisions_v)

        self.target_size = _float_spin(
            1.0,
            low=1.0e-12,
            high=1.0e12,
            decimals=8,
        )
        form.addRow("Target size [model length]:", self.target_size)

        self.reuse_existing_nodes = QCheckBox(
            "Reuse existing coincident nodes (recommended for adjacent patches)"
        )
        self.reuse_existing_nodes.setChecked(True)
        form.addRow("", self.reuse_existing_nodes)

        self.conform_existing_edges = QCheckBox(
            "Conform divisions to existing shared-edge shell mesh"
        )
        self.conform_existing_edges.setChecked(True)
        form.addRow("", self.conform_existing_edges)

        self.formulation = QComboBox()
        self.formulation.addItems(list(ShellElementDialog.FORMULATIONS))
        self.formulation.setCurrentText("ASDShellQ4")
        form.addRow("Formulation:", self.formulation)

        self.section = QComboBox()
        self.section_new = QPushButton("New Shell Section...")
        self.section_new.setEnabled(callable(self._new_section_callback))
        self.section_new.setToolTip(
            "Define a shell-compatible Section without closing this mesh dialog."
        )
        self.section_new.clicked.connect(self._create_section_dependency)
        section_holder = QWidget()
        section_row = QHBoxLayout(section_holder)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(4)
        section_row.addWidget(self.section, 1)
        section_row.addWidget(self.section_new)
        self._refresh_section_choices()
        form.addRow("Shell section:", section_holder)

        self.corotational = QCheckBox(
            "Corotational kinematics (ASDShellQ4)"
        )
        form.addRow("", self.corotational)

        self.no_eas = QCheckBox(
            "Disable enhanced assumed strain for all mesh elements (-noeas)"
        )
        form.addRow("", self.no_eas)

        self.use_drilling_stab = QCheckBox(
            "Override drilling stabilization for all mesh elements"
        )
        form.addRow("", self.use_drilling_stab)
        self.drilling_stab = _float_spin(
            0.01,
            low=0.0,
            high=1.0e12,
            decimals=8,
        )
        form.addRow("Drilling stabilization:", self.drilling_stab)
        self.use_drilling_stab.toggled.connect(self._sync_formulation)

        self.drilling_nl = QCheckBox(
            "Nonlinear drilling constraint for all mesh elements"
        )
        form.addRow("", self.drilling_nl)

        self.use_local_x = QCheckBox(
            "Override ASDShellQ4 local X axis for all mesh elements"
        )
        form.addRow("", self.use_local_x)

        local_row = QHBoxLayout()
        self.local_x_spins = [
            _float_spin(
                1.0 if index == 0 else 0.0,
                low=-1.0e12,
                high=1.0e12,
            )
            for index in range(3)
        ]
        for label, spin in zip(("X", "Y", "Z"), self.local_x_spins):
            local_row.addWidget(QLabel(label))
            local_row.addWidget(spin)
        form.addRow("Local X vector:", local_row)
        self.use_local_x.toggled.connect(self._sync_formulation)

        self.formulation.currentTextChanged.connect(
            self._sync_formulation
        )
        self.mesh_mode.currentIndexChanged.connect(
            self._sync_mesh_sizing
        )
        self._sync_formulation()
        self._sync_mesh_sizing()

        note = QLabel(
            "Corners must be ordered around the boundary. SARE uses bilinear "
            "interpolation between the four corners, so the same tool works "
            "for flat slabs, walls and moderately warped quadrilateral "
            "surfaces. Existing coincident nodes can be reused automatically "
            "so separately meshed adjacent patches remain connected."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        self.preview_info = QLabel()
        self.preview_info.setWordWrap(True)
        root.addWidget(self.preview_info)

        self.divisions_u.valueChanged.connect(self._update_info)
        self.divisions_v.valueChanged.connect(self._update_info)
        self.target_size.valueChanged.connect(self._update_info)
        self.mesh_mode.currentIndexChanged.connect(self._update_info)
        self.reuse_existing_nodes.toggled.connect(
            self._sync_conformity_options
        )
        self.reuse_existing_nodes.toggled.connect(self._update_info)
        self.conform_existing_edges.toggled.connect(
            self._sync_conformity_options
        )
        self.conform_existing_edges.toggled.connect(self._update_info)
        self._sync_conformity_options()
        for combo in self.corner_combos:
            combo.currentIndexChanged.connect(self._update_info)
        self._update_info()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Create Shell Mesh")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_section_choices(self, select_tag: int | None = None) -> None:
        current = self.section.currentData() if self.section.count() else None
        wanted = select_tag if select_tag is not None else current
        self.section.clear()
        self.section.addItem("Select Shell Section...", None)
        for section_tag in sorted(self._sections):
            section = self._sections[section_tag]
            self.section.addItem(
                f"{section_tag} - {section.name} ({section.section_type})",
                int(section_tag),
            )
        if wanted is not None:
            index = self.section.findData(int(wanted))
            if index >= 0:
                self.section.setCurrentIndex(index)
        elif self.section.count() == 2:
            self.section.setCurrentIndex(1)

    def _create_section_dependency(self) -> None:
        if not callable(self._new_section_callback):
            return
        section = self._new_section_callback()
        if section is None:
            return
        if section.section_type not in SHELL_SECTION_TYPES:
            QMessageBox.warning(
                self,
                "Shell Section",
                "The newly created Section is not shell-compatible.",
            )
            return
        self._sections[int(section.tag)] = section
        self._refresh_section_choices(int(section.tag))

    def _sync_formulation(self, *_args) -> None:
        enabled = self.formulation.currentText() == "ASDShellQ4"
        self.corotational.setEnabled(enabled)
        self.no_eas.setEnabled(enabled)
        self.use_drilling_stab.setEnabled(enabled)
        self.drilling_stab.setEnabled(
            enabled and self.use_drilling_stab.isChecked()
        )
        self.drilling_nl.setEnabled(enabled)
        self.use_local_x.setEnabled(enabled)
        for spin in self.local_x_spins:
            spin.setEnabled(enabled and self.use_local_x.isChecked())
        if not enabled:
            self.corotational.setChecked(False)
            self.no_eas.setChecked(False)
            self.use_drilling_stab.setChecked(False)
            self.drilling_nl.setChecked(False)
            self.use_local_x.setChecked(False)

    def _sync_mesh_sizing(self, *_args) -> None:
        target_mode = self.mesh_mode.currentData() == "target_size"
        self.divisions_u.setEnabled(not target_mode)
        self.divisions_v.setEnabled(not target_mode)
        self.target_size.setEnabled(target_mode)

    def _sync_conformity_options(self, *_args) -> None:
        if self.conform_existing_edges.isChecked():
            self.reuse_existing_nodes.setChecked(True)
        if not self.reuse_existing_nodes.isChecked():
            self.conform_existing_edges.setChecked(False)
        self.conform_existing_edges.setEnabled(
            self.reuse_existing_nodes.isChecked()
        )

    def _update_info(self, *_args) -> None:
        corners = [
            int(combo.currentData())
            for combo in self.corner_combos
            if combo.currentData() is not None
        ]
        if len(corners) != 4 or any(
            tag not in self._nodes for tag in corners
        ):
            self.preview_info.setText("Select four valid corner nodes.")
            return
        p1, p2, p3, p4 = (
            self._nodes[tag].xyz for tag in corners
        )
        target_size = (
            float(self.target_size.value())
            if self.mesh_mode.currentData() == "target_size"
            else None
        )
        try:
            nu, nv = resolve_shell_mesh_divisions(
                p1,
                p2,
                p3,
                p4,
                divisions_u=self.divisions_u.value(),
                divisions_v=self.divisions_v.value(),
                target_size=target_size,
            )
        except ValueError as exc:
            self.preview_info.setText(str(exc))
            return
        generated_nodes = (nu + 1) * (nv + 1) - 4
        reuse_text = (
            "existing coincident nodes will be reused"
            if self.reuse_existing_nodes.isChecked()
            else "new intermediate nodes will always be created"
        )
        conformity_text = (
            "shared edges may override Nu/Nv to preserve conformity"
            if self.conform_existing_edges.isChecked()
            else "shared-edge conformity is disabled"
        )
        self.preview_info.setText(
            f"Requested mesh: {nu} × {nv} = {nu * nv} shell elements · "
            f"up to {generated_nodes} intermediate nodes · {reuse_text} · "
            f"{conformity_text}."
        )

    def spec(self) -> ShellMeshSpec:
        corners = tuple(
            int(combo.currentData())
            for combo in self.corner_combos
            if combo.currentData() is not None
        )
        if len(corners) != 4 or len(set(corners)) != 4:
            raise ValueError(
                "Shell mesh requires four distinct corner nodes."
            )
        section_tag = self.section.currentData()
        if section_tag is None:
            raise ValueError(
                "Shell mesh requires a shell-compatible Section."
            )
        local_x = None
        if (
            self.formulation.currentText() == "ASDShellQ4"
            and self.use_local_x.isChecked()
        ):
            local_x = tuple(
                float(spin.value())
                for spin in self.local_x_spins
            )
            if sum(value * value for value in local_x) <= 1.0e-24:
                raise ValueError("Shell local X vector cannot be zero.")
        return ShellMeshSpec(
            corner_nodes=corners,
            divisions_u=self.divisions_u.value(),
            divisions_v=self.divisions_v.value(),
            target_size=(
                float(self.target_size.value())
                if self.mesh_mode.currentData() == "target_size"
                else None
            ),
            formulation=self.formulation.currentText(),
            section_tag=int(section_tag),
            corotational=self.corotational.isChecked(),
            local_x=local_x,
            no_eas=self.no_eas.isChecked(),
            drilling_stab=(
                float(self.drilling_stab.value())
                if self.use_drilling_stab.isChecked()
                else None
            ),
            drilling_nl=self.drilling_nl.isChecked(),
            reuse_existing_nodes=self.reuse_existing_nodes.isChecked(),
            conform_existing_edges=self.conform_existing_edges.isChecked(),
        )

    def _accept(self) -> None:
        try:
            self.spec()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Shell Surface Mesh", str(exc))
            return
        self.accept()

