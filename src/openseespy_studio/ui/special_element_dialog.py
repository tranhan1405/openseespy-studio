from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..units import UnitSystem


def _tag_spin(value: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, 2_147_483_647)
    spin.setValue(int(value))
    return spin


def _float_spin(
    value: float,
    *,
    minimum: float = -1.0e30,
    maximum: float = 1.0e30,
    decimals: int = 8,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(minimum, maximum)
    spin.setValue(float(value))
    spin.setKeyboardTracking(False)
    return spin


class _SpecialElementDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(470)
        root = QVBoxLayout(self)
        self.form = QFormLayout()
        root.addLayout(self.form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_note(self, text: str) -> None:
        note = QLabel(text)
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 6px; background: #f3f6f9; color: #526476;"
        )
        self.layout().insertWidget(0, note)


class CatenaryCableDialog(_SpecialElementDialog):
    def __init__(
        self,
        tag: int,
        node_i: int,
        node_j: int,
        *,
        units=None,
        element=None,
        parent=None,
    ):
        super().__init__(
            "Edit Catenary Cable"
            if element is not None
            else "Create Catenary Cable",
            parent,
        )
        self.unit_system = UnitSystem.from_mapping(units)
        p = dict(
            getattr(element, "special_parameters", {})
            if element is not None
            else {}
        )

        self.tag = _tag_spin(
            getattr(element, "tag", tag)
        )
        self.node_i = _tag_spin(
            getattr(element, "i", node_i)
        )
        self.node_j = _tag_spin(
            getattr(element, "j", node_j)
        )
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(["cable", "stay-cable", "hanger", "tendon"])
        self.group.setCurrentText(
            getattr(element, "group", "cable")
        )

        weight_model = (
            float(p.get("weight", 1000.0))
            * self.unit_system.length_to_m
            / self.unit_system.force_to_n
        )
        e_display = self.unit_system.engineering_stress_from_pa(
            float(p.get("E", 2.0e11))
        )
        area_model = (
            float(p.get("A", 1.0e-3))
            / self.unit_system.length_to_m**2
        )
        l0_model = self.unit_system.length_from_m(
            float(p.get("L0", 1.0))
        )
        rho_model = (
            float(p.get("rho", 0.0))
            * self.unit_system.length_to_m
            / self.unit_system.mass_unit_kg
        )
        tol_model = self.unit_system.length_from_m(
            float(p.get("errorTol", 1.0e-8))
        )

        self.weight = _float_spin(weight_model, minimum=0.0)
        self.elastic_modulus = _float_spin(
            e_display, minimum=1.0e-12
        )
        self.area = _float_spin(area_model, minimum=1.0e-16, decimals=12)
        self.unstressed_length = _float_spin(
            l0_model, minimum=1.0e-12, decimals=10
        )
        self.alpha = _float_spin(
            float(p.get("alpha", 0.0)), decimals=12
        )
        self.temperature_change = _float_spin(
            float(p.get("temperature_change", 0.0))
        )
        self.rho = _float_spin(rho_model, minimum=0.0, decimals=12)
        self.error_tol = _float_spin(
            tol_model, minimum=1.0e-15, decimals=14
        )
        self.substeps = QSpinBox()
        self.substeps.setRange(1, 1_000_000)
        self.substeps.setValue(int(p.get("Nsubsteps", 10)))
        self.mass_type = QComboBox()
        self.mass_type.addItem(
            "0 — lumped mass (supported)",
            0,
        )
        index = self.mass_type.findData(int(p.get("massType", 0)))
        if index >= 0:
            self.mass_type.setCurrentIndex(index)

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Group:", self.group)
        self.form.addRow(
            f"Weight / length [{self.unit_system.line_load_label}]:",
            self.weight,
        )
        self.form.addRow(
            f"Elastic modulus [{self.unit_system.engineering_stress_label}]:",
            self.elastic_modulus,
        )
        self.form.addRow(
            f"Area [{self.unit_system.length}²]:",
            self.area,
        )
        self.form.addRow(
            f"Unstressed length L0 [{self.unit_system.length}]:",
            self.unstressed_length,
        )
        self.form.addRow("Thermal expansion α [1/°C]:", self.alpha)
        self.form.addRow("Temperature change ΔT [°C]:", self.temperature_change)
        self.form.addRow(
            f"Mass / length ρ [{self.unit_system.mass_per_length_label}]:",
            self.rho,
        )
        self.form.addRow(
            f"Equilibrium tolerance [{self.unit_system.length}]:",
            self.error_tol,
        )
        self.form.addRow("Substeps:", self.substeps)
        self.form.addRow("Mass formulation:", self.mass_type)
        self._add_note(
            "CatenaryCable is a 3D/3DOF cable formulation with geometric sag. "
            "L0 is the unstressed cable length; no beam Section or "
            "Geometric Transformation is used."
        )

    def values(self):
        if self.node_i.value() == self.node_j.value():
            raise ValueError("Cable end node tags must be different.")
        u = self.unit_system
        params = {
            "weight": (
                self.weight.value()
                * u.force_to_n
                / u.length_to_m
            ),
            "E": u.engineering_stress_to_pa(
                self.elastic_modulus.value()
            ),
            "A": self.area.value() * u.length_to_m**2,
            "L0": u.length_to_m_value(self.unstressed_length.value()),
            "alpha": self.alpha.value(),
            "temperature_change": self.temperature_change.value(),
            "rho": (
                self.rho.value()
                * u.mass_unit_kg
                / u.length_to_m
            ),
            "errorTol": u.length_to_m_value(self.error_tol.value()),
            "Nsubsteps": self.substeps.value(),
            "massType": int(self.mass_type.currentData()),
        }
        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.group.currentText().strip() or "cable",
            params,
        )


class ElastomericBearingPlasticityDialog(_SpecialElementDialog):
    def __init__(
        self,
        tag: int,
        node_i: int,
        node_j: int,
        *,
        materials,
        ndm: int,
        units=None,
        element=None,
        parent=None,
    ):
        super().__init__(
            "Edit Elastomeric Bearing Plasticity"
            if element is not None
            else "Create Elastomeric Bearing Plasticity",
            parent,
        )
        self.unit_system = UnitSystem.from_mapping(units)
        self._ndm = int(ndm)
        self._materials = dict(materials or {})
        p = dict(
            getattr(element, "special_parameters", {})
            if element is not None
            else {}
        )

        self.tag = _tag_spin(getattr(element, "tag", tag))
        self.node_i = _tag_spin(getattr(element, "i", node_i))
        self.node_j = _tag_spin(getattr(element, "j", node_j))
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(["bearing", "isolator", "support-bearing"])
        self.group.setCurrentText(
            getattr(element, "group", "bearing")
        )

        k_model = (
            float(p.get("kInit", 1.0e7))
            * self.unit_system.length_to_m
            / self.unit_system.force_to_n
        )
        qd_model = self.unit_system.force_from_n(
            float(p.get("qd", 1.0e3))
        )
        mass_model = (
            float(p.get("mass", 0.0))
            / self.unit_system.mass_unit_kg
        )
        self.k_init = _float_spin(k_model, minimum=1.0e-12)
        self.qd = _float_spin(qd_model, minimum=0.0)
        self.alpha1 = _float_spin(float(p.get("alpha1", 0.02)), minimum=0.0)
        self.alpha2 = _float_spin(float(p.get("alpha2", 0.0)), minimum=0.0)
        self.mu = _float_spin(float(p.get("mu", 2.0)), minimum=1.0e-12)
        self.shear_dist = _float_spin(
            float(p.get("shearDist", 0.5)),
            minimum=0.0,
            maximum=1.0,
        )
        self.do_rayleigh = QCheckBox("Include element in Rayleigh damping")
        self.do_rayleigh.setChecked(bool(p.get("doRayleigh", False)))
        self.mass = _float_spin(mass_model, minimum=0.0)

        self.p_material = self._material_combo(p.get("p_mat_tag"))
        self.mz_material = self._material_combo(p.get("mz_mat_tag"))
        self.t_material = self._material_combo(p.get("t_mat_tag"))
        self.my_material = self._material_combo(p.get("my_mat_tag"))

        orientation = p.get("orientation")
        self.custom_orientation = QCheckBox(
            "Use explicit local x/y orientation"
        )
        self.custom_orientation.setChecked(orientation is not None)
        default_orientation = (
            tuple(float(v) for v in orientation)
            if orientation is not None
            else (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        )
        self.orientation = [
            _float_spin(default_orientation[index], decimals=8)
            for index in range(6)
        ]
        for spin in self.orientation:
            spin.setEnabled(self.custom_orientation.isChecked())
        self.custom_orientation.toggled.connect(
            lambda checked: [
                spin.setEnabled(bool(checked))
                for spin in self.orientation
            ]
        )

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Group:", self.group)
        self.form.addRow(
            f"Initial shear stiffness [{self.unit_system.line_load_label}]:",
            self.k_init,
        )
        self.form.addRow(
            f"Characteristic strength qd [{self.unit_system.force}]:",
            self.qd,
        )
        self.form.addRow("α1:", self.alpha1)
        self.form.addRow("α2:", self.alpha2)
        self.form.addRow("μ:", self.mu)
        self.form.addRow("Axial material (-P):", self.p_material)
        if self._ndm == 3:
            self.form.addRow("Torsion material (-T):", self.t_material)
            self.form.addRow("My material (-My):", self.my_material)
        self.form.addRow("Mz material (-Mz):", self.mz_material)
        self.form.addRow("Shear distance:", self.shear_dist)
        self.form.addRow("", self.do_rayleigh)
        self.form.addRow(
            f"Element mass [{self.unit_system.mass_label}]:",
            self.mass,
        )
        self.form.addRow("", self.custom_orientation)
        labels = (
            "Local x1", "Local x2", "Local x3",
            "Local y1", "Local y2", "Local y3",
        )
        for label, spin in zip(labels, self.orientation):
            self.form.addRow(label + ":", spin)

        self._add_note(
            "This bearing is a two-node isolation element. Coincident end "
            "coordinates are allowed. In 3D, axial, torsion, My and Mz "
            "uniaxial materials are required."
        )

    def _material_combo(self, selected):
        combo = QComboBox()
        combo.addItem("Select Material...", None)
        for tag in sorted(self._materials):
            material = self._materials[tag]
            combo.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                int(tag),
            )
        if selected is not None:
            index = combo.findData(int(selected))
            if index >= 0:
                combo.setCurrentIndex(index)
        return combo

    @staticmethod
    def _require_material(combo: QComboBox, label: str) -> int:
        value = combo.currentData()
        if value is None:
            raise ValueError(f"Select the {label} material.")
        return int(value)

    def values(self):
        if self.node_i.value() == self.node_j.value():
            raise ValueError("Bearing end node tags must be different.")
        u = self.unit_system
        params = {
            "kInit": (
                self.k_init.value()
                * u.force_to_n
                / u.length_to_m
            ),
            "qd": u.force_to_n_value(self.qd.value()),
            "alpha1": self.alpha1.value(),
            "alpha2": self.alpha2.value(),
            "mu": self.mu.value(),
            "p_mat_tag": self._require_material(
                self.p_material, "axial (-P)"
            ),
            "mz_mat_tag": self._require_material(
                self.mz_material, "Mz"
            ),
            "shearDist": self.shear_dist.value(),
            "doRayleigh": self.do_rayleigh.isChecked(),
            "mass": self.mass.value() * u.mass_unit_kg,
        }
        if self._ndm == 3:
            params["t_mat_tag"] = self._require_material(
                self.t_material, "torsion (-T)"
            )
            params["my_mat_tag"] = self._require_material(
                self.my_material, "My"
            )
        if self.custom_orientation.isChecked():
            params["orientation"] = tuple(
                spin.value() for spin in self.orientation
            )
        else:
            params["orientation"] = None

        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.group.currentText().strip() or "bearing",
            params,
        )
