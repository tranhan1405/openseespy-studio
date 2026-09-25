from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..project import FrictionModelData
from ..units import UnitSystem


def _tag_spin(value: int) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(1, 2_147_483_647)
    widget.setValue(int(value))
    return widget


def _float_spin(
    value: float,
    *,
    minimum: float = -1.0e30,
    maximum: float = 1.0e30,
    decimals: int = 8,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(minimum, maximum)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


def _combo_by_tag(items, selected=None, *, placeholder="Select..."):
    combo = QComboBox()
    combo.addItem(placeholder, None)
    normalized_items = list(items)
    for tag, label in normalized_items:
        combo.addItem(str(label), int(tag))
    if selected is not None:
        index = combo.findData(int(selected))
        if index >= 0:
            combo.setCurrentIndex(index)
    elif len(normalized_items) == 1:
        combo.setCurrentIndex(1)
    return combo


class _ScrollableDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(590, 720)
        root = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(
            "padding: 7px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(self.note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.form = QFormLayout(host)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class FrictionModelDialog(_ScrollableDialog):
    def __init__(
        self,
        *,
        next_tag: int,
        units=None,
        model: FrictionModelData | None = None,
        parent=None,
    ):
        super().__init__(
            "Edit Friction Model" if model is not None else "New Friction Model",
            parent,
        )
        self.units = UnitSystem.from_mapping(units)
        self.tag = _tag_spin(model.tag if model is not None else next_tag)
        self.name = QLineEdit(
            model.name if model is not None else f"Friction {next_tag}"
        )
        self.kind = QComboBox()
        self.kind.addItem("Coulomb", "Coulomb")
        self.kind.addItem("Velocity dependent", "VelDependent")
        initial_type = model.friction_type if model is not None else "Coulomb"
        index = self.kind.findData(initial_type)
        if index >= 0:
            self.kind.setCurrentIndex(index)

        p = dict(model.parameters if model is not None else {})
        self.mu = _float_spin(float(p.get("mu", 0.05)), minimum=0.0)
        self.mu_slow = _float_spin(
            float(p.get("muSlow", 0.03)), minimum=0.0
        )
        self.mu_fast = _float_spin(
            float(p.get("muFast", 0.08)), minimum=0.0
        )
        rate_si = float(p.get("transRate", 1.0))
        rate_display = (
            rate_si * self.units.time_to_s / self.units.length_to_m
        )
        self.trans_rate = _float_spin(rate_display, minimum=1.0e-15)

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Name:", self.name)
        self.form.addRow("OpenSees frictionModel:", self.kind)
        self.form.addRow("Friction coefficient μ:", self.mu)
        self.form.addRow("Slow-velocity μ:", self.mu_slow)
        self.form.addRow("Fast-velocity μ:", self.mu_fast)
        self.form.addRow(
            f"Transition rate [{self.units.time}/{self.units.length}]:",
            self.trans_rate,
        )
        self.kind.currentIndexChanged.connect(self._sync_type)
        self._sync_type()
        self.note.setText(
            "Friction models are reusable project properties. "
            "TripleFrictionPendulum references three friction-model tags."
        )

    def _sync_type(self, *_args) -> None:
        velocity = self.kind.currentData() == "VelDependent"
        self.mu.setEnabled(not velocity)
        self.mu_slow.setEnabled(velocity)
        self.mu_fast.setEnabled(velocity)
        self.trans_rate.setEnabled(velocity)

    def friction_model(self) -> FrictionModelData:
        kind = str(self.kind.currentData())
        if kind == "Coulomb":
            parameters = {"mu": self.mu.value()}
        else:
            parameters = {
                "muSlow": self.mu_slow.value(),
                "muFast": self.mu_fast.value(),
                "transRate": (
                    self.trans_rate.value()
                    * self.units.length_to_m
                    / self.units.time_to_s
                ),
            }
        return FrictionModelData(
            self.tag.value(),
            self.name.text().strip() or f"Friction {self.tag.value()}",
            kind,
            parameters,
        )


class LeadRubberXDialog(_ScrollableDialog):
    def __init__(
        self,
        *,
        tag: int,
        node_i: int,
        node_j: int,
        units=None,
        element=None,
        parent=None,
    ):
        super().__init__(
            "Edit Lead Rubber Bearing"
            if element is not None
            else "Create Lead Rubber Bearing",
            parent,
        )
        self.units = UnitSystem.from_mapping(units)
        p = dict(
            getattr(element, "special_parameters", {})
            if element is not None else {}
        )
        self.tag = _tag_spin(getattr(element, "tag", tag))
        self.node_i = _tag_spin(getattr(element, "i", node_i))
        self.node_j = _tag_spin(getattr(element, "j", node_j))
        self.group = QLineEdit(getattr(element, "group", "isolation"))

        self.fy = _float_spin(
            self.units.force_from_n(float(p.get("Fy", 1.2e5))),
            minimum=1.0e-15,
        )
        self.alpha = _float_spin(float(p.get("alpha", 0.1)), minimum=0.0)
        self.gr = _float_spin(
            self.units.engineering_stress_from_pa(float(p.get("Gr", 0.8e6))),
            minimum=1.0e-15,
        )
        self.kbulk = _float_spin(
            self.units.engineering_stress_from_pa(
                float(p.get("Kbulk", 2.0e9))
            ),
            minimum=1.0e-15,
        )
        self.d1 = self._length(p.get("D1", 0.10), minimum=0.0)
        self.d2 = self._length(p.get("D2", 0.80), minimum=1.0e-15)
        self.ts = self._length(p.get("ts", 0.003), minimum=1.0e-15)
        self.tr = self._length(p.get("tr", 0.010), minimum=1.0e-15)
        self.layers = QSpinBox()
        self.layers.setRange(1, 100000)
        self.layers.setValue(int(p.get("n", 20)))

        orientation = p.get("orientation")
        self.custom_orientation = QCheckBox("Use explicit local x/y vectors")
        self.custom_orientation.setChecked(orientation is not None)
        values = (
            tuple(float(v) for v in orientation)
            if orientation is not None
            else (0.0, 0.0, 1.0, 1.0, 0.0, 0.0)
        )
        self.orientation = [_float_spin(v) for v in values]

        self.kc = _float_spin(float(p.get("kc", 10.0)), minimum=0.0)
        self.phim = _float_spin(float(p.get("PhiM", 0.5)), minimum=0.0)
        self.ac = _float_spin(float(p.get("ac", 1.0)), minimum=0.0)
        self.sdratio = _float_spin(
            float(p.get("sDratio", 0.5)), minimum=0.0, maximum=1.0
        )
        self.mass = _float_spin(
            float(p.get("mass", 0.0)) / self.units.mass_unit_kg,
            minimum=0.0,
        )
        self.cd = _float_spin(float(p.get("cd", 0.0)), minimum=0.0)
        self.tc = self._length(p.get("tc", 0.0), minimum=0.0)

        self.ql = _float_spin(
            float(p.get("qL", 11200.0))
            * self.units.length_to_m**3
            / self.units.mass_unit_kg,
            minimum=1.0e-15,
        )
        self.cl = _float_spin(
            float(p.get("cL", 130.0))
            * self.units.mass_unit_kg
            / (self.units.force_to_n * self.units.length_to_m),
            minimum=1.0e-15,
        )
        self.ks = _float_spin(
            float(p.get("kS", 50.0))
            * self.units.time_to_s
            / self.units.force_to_n,
            minimum=1.0e-15,
        )
        self.a_s = _float_spin(
            float(p.get("aS", 1.41e-5))
            * self.units.time_to_s
            / self.units.length_to_m**2,
            minimum=1.0e-15,
        )
        self.flags = []
        flag_labels = (
            "tag1 · Cavitation / post-cavitation",
            "tag2 · Buckling-load variation",
            "tag3 · Horizontal-stiffness variation",
            "tag4 · Vertical-stiffness variation",
            "tag5 · Lead-core heating degradation",
        )
        for index, label in enumerate(flag_labels, start=1):
            flag = QCheckBox(label)
            flag.setChecked(bool(int(p.get(f"tag{index}", 0))))
            flag.setToolTip(
                "OpenSees LeadRubberX optional behavior switch "
                f"{index}."
            )
            self.flags.append(flag)

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Group:", self.group)
        self.form.addRow(f"Lead yield force Fy [{self.units.force}]:", self.fy)
        self.form.addRow("Post-yield ratio α:", self.alpha)
        self.form.addRow(
            f"Rubber shear modulus Gr [{self.units.engineering_stress_label}]:",
            self.gr,
        )
        self.form.addRow(
            f"Bulk modulus Kbulk [{self.units.engineering_stress_label}]:",
            self.kbulk,
        )
        self.form.addRow(f"Lead-core diameter D1 [{self.units.length}]:", self.d1)
        self.form.addRow(f"Bearing diameter D2 [{self.units.length}]:", self.d2)
        self.form.addRow(f"Steel shim thickness ts [{self.units.length}]:", self.ts)
        self.form.addRow(f"Rubber-layer thickness tr [{self.units.length}]:", self.tr)
        self.form.addRow("Rubber layers n:", self.layers)
        self.form.addRow("", self.custom_orientation)
        for label, widget in zip(
            ("x1", "x2", "x3", "y1", "y2", "y3"),
            self.orientation,
        ):
            self.form.addRow(f"Local {label}:", widget)
        self.form.addRow("Cavitation parameter kc:", self.kc)
        self.form.addRow("Damage parameter PhiM:", self.phim)
        self.form.addRow("Strength degradation ac:", self.ac)
        self.form.addRow("Shear distance ratio:", self.sdratio)
        self.form.addRow(f"Element mass [{self.units.mass_label}]:", self.mass)
        self.form.addRow("Viscous damping cd:", self.cd)
        self.form.addRow(f"Cover thickness tc [{self.units.length}]:", self.tc)
        self.form.addRow("Lead density/heat qL:", self.ql)
        self.form.addRow("Lead heat cL:", self.cl)
        self.form.addRow("Steel conductivity kS:", self.ks)
        self.form.addRow("Steel diffusivity aS:", self.a_s)
        for flag in self.flags:
            self.form.addRow("", flag)

        self.custom_orientation.toggled.connect(self._sync_orientation)
        self.flags[4].toggled.connect(self._sync_heating_fields)
        self._sync_orientation(self.custom_orientation.isChecked())
        self._sync_heating_fields(self.flags[4].isChecked())
        self.note.setText(
            "LeadRubberX is a 3D/6DOF isolation-bearing element. "
            "Optional behavior switches are named by their physical effect. "
            "Thermal lead/steel properties become editable when lead-core "
            "heating degradation (tag5) is enabled."
        )

    def _length(self, stored, *, minimum=0.0):
        return _float_spin(
            self.units.length_from_m(float(stored)),
            minimum=minimum,
            decimals=10,
        )

    def _sync_orientation(self, checked: bool) -> None:
        for widget in self.orientation:
            widget.setEnabled(bool(checked))

    def _sync_heating_fields(self, checked: bool) -> None:
        for widget in (self.ql, self.cl, self.ks, self.a_s):
            widget.setEnabled(bool(checked))

    def values(self):
        if self.node_i.value() == self.node_j.value():
            raise ValueError("LeadRubberX end-node tags must be different.")
        if self.d1.value() >= self.d2.value():
            raise ValueError(
                "LeadRubberX requires lead-core diameter D1 < bearing diameter D2."
            )
        orientation = None
        if self.custom_orientation.isChecked():
            orientation = tuple(widget.value() for widget in self.orientation)
            x = orientation[:3]
            y = orientation[3:]
            x_norm2 = sum(value * value for value in x)
            y_norm2 = sum(value * value for value in y)
            cross = (
                x[1] * y[2] - x[2] * y[1],
                x[2] * y[0] - x[0] * y[2],
                x[0] * y[1] - x[1] * y[0],
            )
            cross_norm2 = sum(value * value for value in cross)
            if (
                x_norm2 <= 1.0e-24
                or y_norm2 <= 1.0e-24
                or cross_norm2 <= 1.0e-16 * x_norm2 * y_norm2
            ):
                raise ValueError(
                    "LeadRubberX local x/y vectors must be non-zero "
                    "and non-parallel."
                )
        u = self.units
        params = {
            "Fy": u.force_to_n_value(self.fy.value()),
            "alpha": self.alpha.value(),
            "Gr": u.engineering_stress_to_pa(self.gr.value()),
            "Kbulk": u.engineering_stress_to_pa(self.kbulk.value()),
            "D1": u.length_to_m_value(self.d1.value()),
            "D2": u.length_to_m_value(self.d2.value()),
            "ts": u.length_to_m_value(self.ts.value()),
            "tr": u.length_to_m_value(self.tr.value()),
            "n": self.layers.value(),
            "orientation": orientation,
            "kc": self.kc.value(),
            "PhiM": self.phim.value(),
            "ac": self.ac.value(),
            "sDratio": self.sdratio.value(),
            "mass": self.mass.value() * u.mass_unit_kg,
            "cd": self.cd.value(),
            "tc": u.length_to_m_value(self.tc.value()),
            "qL": (
                self.ql.value()
                * u.mass_unit_kg
                / u.length_to_m**3
            ),
            "cL": (
                self.cl.value()
                * u.force_to_n
                * u.length_to_m
                / u.mass_unit_kg
            ),
            "kS": self.ks.value() * u.force_to_n / u.time_to_s,
            "aS": self.a_s.value() * u.length_to_m**2 / u.time_to_s,
        }
        for index, flag in enumerate(self.flags, start=1):
            params[f"tag{index}"] = 1 if flag.isChecked() else 0
        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.group.text().strip() or "isolation",
            params,
        )


class TripleFrictionPendulumDialog(_ScrollableDialog):
    def __init__(
        self,
        *,
        tag: int,
        node_i: int,
        node_j: int,
        materials,
        friction_models,
        units=None,
        element=None,
        parent=None,
    ):
        super().__init__(
            "Edit Triple Friction Pendulum"
            if element is not None
            else "Create Triple Friction Pendulum",
            parent,
        )
        self.units = UnitSystem.from_mapping(units)
        p = dict(
            getattr(element, "special_parameters", {})
            if element is not None else {}
        )
        self.tag = _tag_spin(getattr(element, "tag", tag))
        self.node_i = _tag_spin(getattr(element, "i", node_i))
        self.node_j = _tag_spin(getattr(element, "j", node_j))
        self.group = QLineEdit(getattr(element, "group", "isolation"))

        friction_items = [
            (tag, f"{tag} - {item.name} ({item.friction_type})")
            for tag, item in sorted((friction_models or {}).items())
        ]
        material_items = [
            (tag, f"{tag} - {item.name} ({item.material_type})")
            for tag, item in sorted((materials or {}).items())
        ]
        self.friction = [
            _combo_by_tag(
                friction_items,
                p.get(f"frnTag{index}"),
                placeholder="Select friction model...",
            )
            for index in range(1, 4)
        ]
        keys = ("vertMatTag", "rotZMatTag", "rotXMatTag", "rotYMatTag")
        self.materials = [
            _combo_by_tag(
                material_items,
                p.get(key),
                placeholder="Select uniaxial material...",
            )
            for key in keys
        ]
        self.lengths = {
            key: _float_spin(
                self.units.length_from_m(
                    float(p.get(key, default))
                ),
                minimum=0.0 if key.startswith("d") else 1.0e-15,
                decimals=10,
            )
            for key, default in (
                ("L1", 0.36), ("L2", 1.25), ("L3", 1.25),
                ("d1", 0.10), ("d2", 0.20), ("d3", 0.20),
            )
        }
        self.w = _float_spin(
            self.units.force_from_n(float(p.get("W", 1.0e6))),
            minimum=0.0,
        )
        self.uy = _float_spin(
            self.units.length_from_m(float(p.get("uy", 0.0005))),
            minimum=1.0e-15,
            decimals=10,
        )
        self.kvt = _float_spin(
            float(p.get("kvt", 1000.0))
            * self.units.length_to_m
            / self.units.force_to_n,
            minimum=1.0e-15,
        )
        self.min_fv = _float_spin(
            self.units.force_from_n(float(p.get("minFv", 100.0))),
            minimum=0.0,
        )
        self.tol = _float_spin(
            float(p.get("tol", 1.0e-5)),
            minimum=1.0e-15,
            decimals=12,
        )

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Group:", self.group)
        for index, combo in enumerate(self.friction, start=1):
            self.form.addRow(f"Friction model {index}:", combo)
        for label, combo in zip(
            (
                "Axial material (matP)",
                "Torsional material (matT)",
                "Moment-y material (matMy)",
                "Moment-z material (matMz)",
            ),
            self.materials,
        ):
            self.form.addRow(label + ":", combo)
        for index in range(1, 4):
            self.form.addRow(
                f"Effective pendulum length L{index} [{self.units.length}]:",
                self.lengths[f"L{index}"],
            )
        for index in range(1, 4):
            self.form.addRow(
                f"Sliding capacity Ubar{index} [{self.units.length}]:",
                self.lengths[f"d{index}"],
            )
        self.form.addRow(f"Initial axial force W [{self.units.force}]:", self.w)
        self.form.addRow(f"Sliding onset Uy [{self.units.length}]:", self.uy)
        self.form.addRow(
            f"Vertical tension stiffness Kvt [{self.units.force}/{self.units.length}]:",
            self.kvt,
        )
        self.form.addRow(f"Minimum vertical force [{self.units.force}]:", self.min_fv)
        self.form.addRow("Element tolerance:", self.tol)

        for index in range(1, 4):
            self.lengths[f"L{index}"].setToolTip(
                f"Effective pendulum length L{index} for sliding interface {index}."
            )
            self.lengths[f"d{index}"].setToolTip(
                f"OpenSees Ubar{index}: displacement capacity of sliding "
                f"interface {index}. Stored internally as d{index} for "
                "backward-compatible FEWIZ project files."
            )
        self.kvt.setToolTip(
            "Vertical tension stiffness Kvt. This is stiffness "
            "(force/length), not flexibility."
        )
        self.note.setText(
            "TripleFrictionPendulum is a 3D/6DOF isolation element. "
            "The three d1/d2/d3 storage keys are shown here using the "
            "OpenSees names Ubar1/Ubar2/Ubar3 (sliding displacement "
            "capacities). Material labels follow matP, matT, matMy and matMz."
        )

    @staticmethod
    def _required(combo: QComboBox, label: str) -> int:
        value = combo.currentData()
        if value is None:
            raise ValueError(f"Select {label}.")
        return int(value)

    def values(self):
        if self.node_i.value() == self.node_j.value():
            raise ValueError("TFP end-node tags must be different.")
        u = self.units
        params = {
            f"frnTag{index}": self._required(
                combo, f"friction model {index}"
            )
            for index, combo in enumerate(self.friction, start=1)
        }
        for key, combo, label in zip(
            ("vertMatTag", "rotZMatTag", "rotXMatTag", "rotYMatTag"),
            self.materials,
            ("vertical material", "RotZ material", "RotX material", "RotY material"),
        ):
            params[key] = self._required(combo, label)
        for key, widget in self.lengths.items():
            params[key] = u.length_to_m_value(widget.value())
        params.update({
            "W": u.force_to_n_value(self.w.value()),
            "uy": u.length_to_m_value(self.uy.value()),
            "kvt": self.kvt.value() * u.force_to_n / u.length_to_m,
            "minFv": u.force_to_n_value(self.min_fv.value()),
            "tol": self.tol.value(),
        })
        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.group.text().strip() or "isolation",
            params,
        )


class ContactElementDialog(_ScrollableDialog):
    def __init__(
        self,
        *,
        tag: int,
        nodes,
        ndm: int,
        nd_materials,
        transformations,
        units=None,
        element=None,
        next_node_tag: int | None = None,
        parent=None,
    ):
        super().__init__(
            "Edit Contact / Interface Element"
            if element is not None
            else "Create Contact / Interface Element",
            parent,
        )
        self.units = UnitSystem.from_mapping(units)
        self.ndm = int(ndm)
        self.nodes = dict(nodes or {})
        self.nd_materials = dict(nd_materials or {})
        self.transformations = dict(transformations or {})
        self.next_node_tag = int(next_node_tag or 1)
        p = dict(
            getattr(element, "special_parameters", {})
            if element is not None else {}
        )
        self.tag = _tag_spin(getattr(element, "tag", tag))
        self.kind = QComboBox()
        types = (
            ("Zero-length contact 2D", "zeroLengthContact2D"),
            ("Beam-to-node contact 2D", "BeamContact2D"),
        ) if self.ndm == 2 else (
            ("Zero-length contact 3D", "zeroLengthContact3D"),
            ("Beam-to-node contact 3D", "BeamContact3D"),
        )
        for label, value in types:
            self.kind.addItem(label, value)
        initial = (
            getattr(element, "element_type", types[0][1])
            if element is not None else types[0][1]
        )
        index = self.kind.findData(initial)
        if index >= 0:
            self.kind.setCurrentIndex(index)

        self.node_i = QComboBox()
        self.node_j = QComboBox()
        self.node_k = QComboBox()
        self.node_l = QComboBox()
        for combo in (self.node_i, self.node_j, self.node_k, self.node_l):
            self._fill_node_combo(combo)
        if element is not None:
            for combo, selected in (
                (self.node_i, element.i),
                (self.node_j, element.j),
                (self.node_k, element.k),
                (self.node_l, element.l),
            ):
                if selected is not None:
                    found = combo.findData(int(selected))
                    if found >= 0:
                        combo.setCurrentIndex(found)

        self.auto_lambda = QCheckBox(
            "Auto-create free Lagrange node at contact-node coordinates"
        )
        self.auto_lambda.setChecked(element is None)

        self.kn = _float_spin(
            float(p.get("Kn", 1.0e9))
            * self.units.length_to_m
            / self.units.force_to_n,
            minimum=1.0e-15,
        )
        self.kt = _float_spin(
            float(p.get("Kt", 1.0e8))
            * self.units.length_to_m
            / self.units.force_to_n,
            minimum=1.0e-15,
        )
        self.mu = _float_spin(float(p.get("mu", 0.30)), minimum=0.0)
        normal = tuple(p.get("normal", (1.0, 0.0)))
        self.nx = _float_spin(float(normal[0]))
        self.ny = _float_spin(float(normal[1]))
        self.cohesion = _float_spin(
            self.units.force_from_n(float(p.get("cohesion", 0.0))),
            minimum=0.0,
        )
        self.direction = QComboBox()
        self.direction.addItem("1 - X", 1)
        self.direction.addItem("2 - Y", 2)
        self.direction.addItem("3 - Z", 3)
        di = self.direction.findData(int(p.get("dir", 1)))
        if di >= 0:
            self.direction.setCurrentIndex(di)

        nd2 = "ContactMaterial2D"
        nd3 = "ContactMaterial3D"
        self.nd_material = QComboBox()
        self.nd_material.addItem("Select contact material...", None)
        for nd_tag, mat in sorted(self.nd_materials.items()):
            if mat.material_type in {nd2, nd3}:
                self.nd_material.addItem(
                    f"{nd_tag} - {mat.name} ({mat.material_type})",
                    int(nd_tag),
                )
        selected_nd = p.get("nd_material_tag")
        if selected_nd is not None:
            index = self.nd_material.findData(int(selected_nd))
            if index >= 0:
                self.nd_material.setCurrentIndex(index)

        self.width = _float_spin(
            self.units.length_from_m(float(p.get("width", 0.30))),
            minimum=1.0e-15,
        )
        self.radius = _float_spin(
            self.units.length_from_m(float(p.get("radius", 0.15))),
            minimum=1.0e-15,
        )
        self.gtol = _float_spin(
            self.units.length_from_m(float(p.get("gTol", 1.0e-8))),
            minimum=1.0e-15,
            decimals=12,
        )
        self.ftol = _float_spin(
            self.units.force_from_n(float(p.get("fTol", 1.0e-4))),
            minimum=1.0e-15,
            decimals=12,
        )
        self.cflag = QCheckBox(
            "Initially open / no contact assumed (cFlag=1)"
        )
        self.cflag.setChecked(bool(int(p.get("cFlag", 0))))
        self.transformation = _combo_by_tag(
            [
                (
                    tr_tag,
                    f"{tr_tag} - {tr.name} ({tr.transformation_type})",
                )
                for tr_tag, tr in sorted(self.transformations.items())
            ],
            p.get("transf_tag"),
            placeholder="Select transformation...",
        )

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Formulation:", self.kind)
        self.form.addRow("Master / constrained node I:", self.node_i)
        self.form.addRow("Master node J:", self.node_j)
        self.form.addRow("Contact node K:", self.node_k)
        self.form.addRow("Lagrange node L:", self.node_l)
        self.form.addRow("", self.auto_lambda)
        self.form.addRow(
            f"Normal penalty Kn [{self.units.force}/{self.units.length}]:",
            self.kn,
        )
        self.form.addRow(
            f"Tangential penalty Kt [{self.units.force}/{self.units.length}]:",
            self.kt,
        )
        self.form.addRow("Friction coefficient μ:", self.mu)
        self.form.addRow("2D normal Nx:", self.nx)
        self.form.addRow("2D normal Ny:", self.ny)
        self.form.addRow(
            f"3D cohesion [{self.units.force}]:",
            self.cohesion,
        )
        self.form.addRow("3D normal direction:", self.direction)
        self.form.addRow("Contact nD material:", self.nd_material)
        self.form.addRow(f"Beam-contact width [{self.units.length}]:", self.width)
        self.form.addRow(f"Beam-contact radius [{self.units.length}]:", self.radius)
        self.form.addRow(f"Gap tolerance [{self.units.length}]:", self.gtol)
        self.form.addRow(f"Force tolerance [{self.units.force}]:", self.ftol)
        self.form.addRow("", self.cflag)
        self.form.addRow("3D beam transformation:", self.transformation)

        self.kind.currentIndexChanged.connect(self._sync_kind)
        self.auto_lambda.toggled.connect(self._sync_kind)
        self._sync_kind()

    def _fill_node_combo(
        self,
        combo: QComboBox,
        *,
        allowed_ndf: int | None = None,
    ):
        combo.addItem("Select node...", None)
        for tag, node in sorted(self.nodes.items()):
            if allowed_ndf is not None and int(node.ndf) != int(allowed_ndf):
                continue
            combo.addItem(
                f"{tag} · ndf={int(node.ndf)} · "
                f"({node.xyz[0]:g}, {node.xyz[1]:g}, {node.xyz[2]:g})",
                int(tag),
            )

    def _refilter_node_combo(
        self,
        combo: QComboBox,
        *,
        allowed_ndf: int,
    ) -> None:
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        self._fill_node_combo(combo, allowed_ndf=allowed_ndf)
        if selected is not None:
            index = combo.findData(int(selected))
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _refilter_nd_materials(self, kind: str) -> None:
        selected = self.nd_material.currentData()
        expected = (
            "ContactMaterial2D"
            if kind.endswith("2D")
            else "ContactMaterial3D"
        )
        self.nd_material.blockSignals(True)
        self.nd_material.clear()
        self.nd_material.addItem(f"Select {expected}...", None)
        for nd_tag, material in sorted(self.nd_materials.items()):
            if material.material_type != expected:
                continue
            self.nd_material.addItem(
                f"{nd_tag} - {material.name} ({material.material_type})",
                int(nd_tag),
            )
        if selected is not None:
            index = self.nd_material.findData(int(selected))
            if index >= 0:
                self.nd_material.setCurrentIndex(index)
        self.nd_material.blockSignals(False)

    def _sync_kind(self, *_args):
        kind = str(self.kind.currentData())
        beam = kind.startswith("BeamContact")
        is2d = kind.endswith("2D")

        if beam:
            master_ndf = 3 if is2d else 6
            contact_ndf = 2 if is2d else 3
            self._refilter_node_combo(
                self.node_i,
                allowed_ndf=master_ndf,
            )
            self._refilter_node_combo(
                self.node_j,
                allowed_ndf=master_ndf,
            )
            self._refilter_node_combo(
                self.node_k,
                allowed_ndf=contact_ndf,
            )
            self._refilter_node_combo(
                self.node_l,
                allowed_ndf=contact_ndf,
            )
            self._refilter_nd_materials(kind)
            self.note.setText(
                f"{kind} requires master nodes with ndf={master_ndf} and "
                f"contact/Lagrange nodes with ndf={contact_ndf}. "
                "Only compatible nodes and contact nD materials are shown. "
                "Auto Lagrange creates a free node at node K coordinates."
            )
        else:
            contact_ndf = 2 if is2d else 3
            self._refilter_node_combo(
                self.node_i,
                allowed_ndf=contact_ndf,
            )
            self._refilter_node_combo(
                self.node_j,
                allowed_ndf=contact_ndf,
            )
            self._refilter_node_combo(
                self.node_k,
                allowed_ndf=contact_ndf,
            )
            self._refilter_node_combo(
                self.node_l,
                allowed_ndf=contact_ndf,
            )
            self._refilter_nd_materials(kind)
            self.note.setText(
                f"{kind} requires two translational nodes with "
                f"ndf={contact_ndf}. Only compatible nodes are shown. "
                "This contact formulation has a non-symmetric tangent, so "
                "use a non-symmetric equation-system solver."
            )

        self.node_k.setEnabled(beam)
        self.auto_lambda.setEnabled(beam)
        self.node_l.setEnabled(beam and not self.auto_lambda.isChecked())
        for widget in (self.kn, self.kt, self.mu):
            widget.setEnabled(not beam)
        self.nx.setEnabled(not beam and is2d)
        self.ny.setEnabled(not beam and is2d)
        self.cohesion.setEnabled(not beam and not is2d)
        self.direction.setEnabled(not beam and not is2d)
        self.nd_material.setEnabled(beam)
        self.width.setEnabled(beam and is2d)
        self.radius.setEnabled(beam and not is2d)
        self.gtol.setEnabled(beam)
        self.ftol.setEnabled(beam)
        self.cflag.setEnabled(beam)
        self.transformation.setEnabled(beam and not is2d)

    @staticmethod
    def _required(combo: QComboBox, label: str) -> int:
        value = combo.currentData()
        if value is None:
            raise ValueError(f"Select {label}.")
        return int(value)

    def values(self):
        kind = str(self.kind.currentData())
        i = self._required(self.node_i, "node I")
        j = self._required(self.node_j, "node J")
        if i == j:
            raise ValueError("Contact element node tags must be different.")
        u = self.units
        if kind == "zeroLengthContact2D":
            nx = self.nx.value()
            ny = self.ny.value()
            if nx * nx + ny * ny <= 1.0e-24:
                raise ValueError("2D contact normal cannot be zero.")
            params = {
                "Kn": self.kn.value() * u.force_to_n / u.length_to_m,
                "Kt": self.kt.value() * u.force_to_n / u.length_to_m,
                "mu": self.mu.value(),
                "normal": (nx, ny),
            }
            return self.tag.value(), kind, (i, j, None, None), params, False
        if kind == "zeroLengthContact3D":
            params = {
                "Kn": self.kn.value() * u.force_to_n / u.length_to_m,
                "Kt": self.kt.value() * u.force_to_n / u.length_to_m,
                "mu": self.mu.value(),
                "cohesion": u.force_to_n_value(self.cohesion.value()),
                "dir": int(self.direction.currentData()),
            }
            return self.tag.value(), kind, (i, j, None, None), params, False

        k = self._required(self.node_k, "contact node K")
        auto_lambda = self.auto_lambda.isChecked()
        l = (
            self.next_node_tag
            if auto_lambda
            else self._required(self.node_l, "Lagrange node L")
        )
        if len({i, j, k, l}) != 4:
            raise ValueError("BeamContact requires four distinct node tags.")
        nd_tag = self._required(self.nd_material, "contact nD material")
        expected = (
            "ContactMaterial2D" if kind == "BeamContact2D"
            else "ContactMaterial3D"
        )
        material = self.nd_materials.get(nd_tag)
        if material is None or material.material_type != expected:
            raise ValueError(f"{kind} requires {expected}.")
        params = {
            "nd_material_tag": nd_tag,
            "gTol": u.length_to_m_value(self.gtol.value()),
            "fTol": u.force_to_n_value(self.ftol.value()),
            "cFlag": 1 if self.cflag.isChecked() else 0,
        }
        if kind == "BeamContact2D":
            params["width"] = u.length_to_m_value(self.width.value())
        else:
            params["radius"] = u.length_to_m_value(self.radius.value())
            params["transf_tag"] = self._required(
                self.transformation,
                "3D geometric transformation",
            )
        return self.tag.value(), kind, (i, j, k, l), params, auto_lambda
