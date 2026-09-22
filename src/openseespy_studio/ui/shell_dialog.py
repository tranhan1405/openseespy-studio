from __future__ import annotations

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
    NDMaterialData,
    SECTION_DEFAULTS,
    SHELL_SECTION_TYPES,
    SectionData,
    ShellLayerData,
)
from ..shell_mesh import ShellMeshSpec
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
    """Small shell-focused editor for OpenSees nDMaterial definitions."""

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
        self.setMinimumWidth(420)
        self.unit_system = UnitSystem.from_mapping(units)
        defaults = ND_MATERIAL_DEFAULTS["ElasticIsotropic"]
        p = material.parameters if material is not None else defaults

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(
            material.tag if material is not None else int(next_tag)
        )
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            material.name
            if material is not None
            else f"ElasticIsotropic {int(next_tag)}"
        )
        form.addRow("Name:", self.name)

        self.material_type = QComboBox()
        self.material_type.addItem("ElasticIsotropic")
        form.addRow("OpenSees nDMaterial:", self.material_type)

        self.elastic_modulus = _float_spin(
            self.unit_system.engineering_stress_from_pa(
                float(p.get("E", defaults["E"]))
            ),
            low=1.0e-12,
        )
        form.addRow(
            f"E [{self.unit_system.engineering_stress_label}]:",
            self.elastic_modulus,
        )

        self.poisson = _float_spin(
            float(p.get("nu", defaults["nu"])),
            low=-0.999999,
            high=0.499999,
            decimals=6,
        )
        form.addRow("Poisson ratio ν:", self.poisson)

        self.density = _float_spin(
            self.unit_system.engineering_density_from_kg_per_m3(
                float(p.get("rho", defaults["rho"]))
            ),
            low=0.0,
        )
        form.addRow(
            f"Density ρ [{self.unit_system.engineering_density_label}]:",
            self.density,
        )

        note = QLabel(
            "nD materials are stored separately from uniaxial materials. "
            "The first nonlinear-shell family uses ElasticIsotropic; more "
            "constitutive nD models can be added without changing the "
            "uniaxial Material Library."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def material_data(self) -> NDMaterialData:
        return NDMaterialData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"ElasticIsotropic {self.tag.value()}",
            material_type="ElasticIsotropic",
            parameters={
                "E": self.unit_system.engineering_stress_to_pa(
                    self.elastic_modulus.value()
                ),
                "nu": self.poisson.value(),
                "rho": self.unit_system.engineering_density_to_kg_per_m3(
                    self.density.value()
                ),
            },
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
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Shell Element" if element is not None
            else "Create Shell Element"
        )
        self.setModal(True)
        self.setMinimumWidth(500)
        self._nodes = dict(nodes or {})
        self._sections = {
            int(section_tag): section
            for section_tag, section in dict(sections or {}).items()
            if section.section_type in SHELL_SECTION_TYPES
        }

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
        for section_tag in sorted(self._sections):
            section = self._sections[section_tag]
            self.section.addItem(
                f"{section_tag} - {section.name} ({section.section_type})",
                int(section_tag),
            )
        if element is not None and element.section_tag is not None:
            wanted = self.section.findData(int(element.section_tag))
            if wanted >= 0:
                self.section.setCurrentIndex(wanted)
        form.addRow("Shell section:", self.section)

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
            "ASDShellQ4 is the recommended default general-purpose element."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

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
            QMessageBox.warning(self, "Shell Element", str(exc))
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

        self.divisions_u = QSpinBox()
        self.divisions_u.setRange(1, 500)
        self.divisions_u.setValue(4)
        form.addRow("Divisions U:", self.divisions_u)

        self.divisions_v = QSpinBox()
        self.divisions_v.setRange(1, 500)
        self.divisions_v.setValue(4)
        form.addRow("Divisions V:", self.divisions_v)

        self.formulation = QComboBox()
        self.formulation.addItems(list(ShellElementDialog.FORMULATIONS))
        self.formulation.setCurrentText("ASDShellQ4")
        form.addRow("Formulation:", self.formulation)

        self.section = QComboBox()
        for section_tag in sorted(self._sections):
            section = self._sections[section_tag]
            self.section.addItem(
                f"{section_tag} - {section.name} ({section.section_type})",
                section_tag,
            )
        form.addRow("Shell section:", self.section)

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
        self._sync_formulation()

        note = QLabel(
            "Corners must be ordered around the boundary. SARE uses bilinear "
            "interpolation between the four corners, so the same tool works "
            "for flat slabs, walls and moderately warped quadrilateral "
            "surfaces. Existing corner nodes are reused; intermediate mesh "
            "nodes are generated automatically."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        self.preview_info = QLabel()
        self.preview_info.setWordWrap(True)
        root.addWidget(self.preview_info)

        self.divisions_u.valueChanged.connect(self._update_info)
        self.divisions_v.valueChanged.connect(self._update_info)
        self._update_info()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Create Shell Mesh")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

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

    def _update_info(self, *_args) -> None:
        nu = self.divisions_u.value()
        nv = self.divisions_v.value()
        generated_nodes = (nu + 1) * (nv + 1) - 4
        self.preview_info.setText(
            f"Mesh: {nu} × {nv} = {nu * nv} shell elements · "
            f"up to {generated_nodes} generated nodes "
            "(four corners are reused)."
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
        )

    def _accept(self) -> None:
        try:
            self.spec()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Shell Surface Mesh", str(exc))
            return
        self.accept()

