from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..project import MaterialData, ProjectDatabase, SectionData
from ..test_column import TestColumnSpec, bending_rotation_dof
from ..units import UnitSystem
from .material_dialog import MaterialDialog
from .section_dialog import SectionDialog


def _double(
    value: float,
    low: float = 0.0,
    high: float = 1.0e20,
    decimals: int = 6,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(low, high)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


class TestColumnWizard(QDialog):
    PRESETS = (
        "Blank Column",
        "Cantilever Cyclic Test",
        "Cantilever Pushover",
        "Axial + Lateral Column",
        "Dynamic / Shake-table Column",
    )

    def __init__(
        self,
        project: ProjectDatabase,
        *,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)
        self._pending_sections: dict[int, SectionData] = {}
        self._pending_materials: dict[int, MaterialData] = {}
        self.setWindowTitle("Quick 1D Column / Test Specimen")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.resize(650, 620)

        root = QVBoxLayout(self)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)

        intro = QLabel(
            "Create a single-line column specimen for experimental validation, "
            "cyclic/pushover studies, section tests, or simple dynamic models."
        )
        intro.setWordWrap(True)
        body_layout.addWidget(intro)

        preset_form = QFormLayout()
        self.preset = QComboBox()
        self.preset.addItems(self.PRESETS)
        preset_form.addRow("Preset:", self.preset)
        body_layout.addLayout(preset_form)

        geometry_group = QGroupBox("Geometry & formulation")
        geometry = QFormLayout(geometry_group)
        self.column_height = _double(3.0, 1.0e-6, 1.0e9)
        self.elements = QSpinBox()
        self.elements.setRange(1, 200)
        self.elements.setValue(1)

        self.axis = QComboBox()
        self.axis.addItem("Global Z · vertical", 3)
        self.axis.addItem("Global X", 1)
        self.axis.addItem("Global Y", 2)

        self.lateral = QComboBox()
        self.lateral.addItem("Global X", 1)
        self.lateral.addItem("Global Y", 2)
        self.lateral.addItem("Global Z", 3)

        self.planar = QCheckBox(
            "Planar test behavior · restrain out-of-plane DOFs automatically"
        )
        self.planar.setChecked(True)

        self.section = QComboBox()
        self._refresh_section_combo()

        self.new_section = QPushButton("New Section...")
        self.new_section.setToolTip(
            "Create a section without leaving the 1D Column wizard"
        )
        self.new_section.clicked.connect(self._create_section)

        section_widget = QWidget()
        section_row = QHBoxLayout(section_widget)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(6)
        section_row.addWidget(self.section, 1)
        section_row.addWidget(self.new_section)

        self.element_type = QComboBox()
        self.element_type.addItems(
            ["forceBeamColumn", "dispBeamColumn", "elasticBeamColumn"]
        )

        self.integration = QComboBox()
        self.integration.addItems(["Lobatto", "Legendre"])
        self.integration_points = QSpinBox()
        self.integration_points.setRange(2, 50)
        self.integration_points.setValue(5)

        self.transformation = QComboBox()
        self.transformation.addItem("Auto · PDelta", ("auto", "PDelta"))
        self.transformation.addItem("Auto · Linear", ("auto", "Linear"))
        self.transformation.addItem(
            "Auto · Corotational",
            ("auto", "Corotational"),
        )
        for tag in sorted(project.transformations):
            item = project.transformations[tag]
            self.transformation.addItem(
                f"{tag} - {item.name} ({item.transformation_type})",
                ("tag", tag),
            )

        geometry.addRow(
            f"Column height [{self.units.length}]:",
            self.column_height,
        )
        geometry.addRow("Number of elements:", self.elements)
        geometry.addRow("Column axis:", self.axis)
        geometry.addRow("Lateral/test direction:", self.lateral)
        geometry.addRow("", self.planar)
        geometry.addRow("Section:", section_widget)
        geometry.addRow("Element formulation:", self.element_type)
        geometry.addRow("Beam integration:", self.integration)
        geometry.addRow("Integration points:", self.integration_points)
        geometry.addRow("Geometric transformation:", self.transformation)
        body_layout.addWidget(geometry_group)

        boundary_group = QGroupBox("Boundary & Base Interface Model")
        boundary_layout = QVBoxLayout(boundary_group)
        boundary = QFormLayout()
        self.base_support = QComboBox()
        self.base_support.addItems(["Fixed", "Pinned", "Free"])
        self.top_support = QComboBox()
        self.top_support.addItems(["Free", "Pinned", "Fixed"])
        boundary.addRow("Nominal base support:", self.base_support)
        boundary.addRow("Top:", self.top_support)

        self.base_interface = QComboBox()
        self.base_interface.addItems([
            "Fixed base",
            "Translational slip spring",
            "Rotational spring",
            "Bond_SP01 strain penetration",
            "Custom zeroLength",
        ])
        boundary.addRow("Base Interface Model:", self.base_interface)
        boundary_layout.addLayout(boundary)

        interface_note = QLabel(
            "The base interface belongs to the specimen, so the same column "
            "can be used for Cyclic, Pushover, and NLTH. Fixed base is the "
            "default. Nonlinear interface DOFs are released at the column "
            "base and connected to a coincident fixed ground node through "
            "zeroLength. For reinforcement strain penetration, Bond_SP01 "
            "belongs in a Fiber zeroLengthSection rather than directly in "
            "a force-deformation zeroLength DOF."
        )
        interface_note.setWordWrap(True)
        interface_note.setObjectName("Muted")
        boundary_layout.addWidget(interface_note)

        self.interface_rows: dict[
            int, tuple[QCheckBox, QComboBox]
        ] = {}
        self.interface_dofs_group = QGroupBox("zeroLength spring DOFs")
        interface_dofs_layout = QVBoxLayout(self.interface_dofs_group)
        for dof, label in (
            (1, "UX"), (2, "UY"), (3, "UZ"),
            (4, "RX"), (5, "RY"), (6, "RZ"),
        ):
            row = QHBoxLayout()
            check = QCheckBox(f"{label} · dir {dof}")
            combo = QComboBox()
            row.addWidget(check)
            row.addWidget(combo, 1)
            interface_dofs_layout.addLayout(row)
            self.interface_rows[dof] = (check, combo)
            check.toggled.connect(
                lambda checked, row_dof=dof: self._sync_interface_row(
                    row_dof,
                    checked,
                )
            )
            combo.currentIndexChanged.connect(self._update_preview)

        material_buttons = QHBoxLayout()
        self.new_interface_material = QPushButton("New Material...")
        self.new_interface_material.clicked.connect(
            self._create_interface_material
        )
        material_buttons.addWidget(self.new_interface_material)
        material_buttons.addStretch(1)
        interface_dofs_layout.addLayout(material_buttons)
        boundary_layout.addWidget(self.interface_dofs_group)

        self.strain_penetration_group = QGroupBox(
            "Bond_SP01 strain penetration · zeroLengthSection"
        )
        strain_form = QFormLayout(self.strain_penetration_group)
        self.strain_bond_material = QComboBox()
        self.strain_bond_material.currentIndexChanged.connect(
            self._update_preview
        )
        strain_form.addRow("Bond_SP01 material:", self.strain_bond_material)

        self.strain_note = QLabel(
            "Studio clones the selected column Fiber section, keeps its "
            "concrete fibers, and replaces steel/rebar fibers with Bond_SP01. "
            "The resulting Fiber section is assigned to a zeroLengthSection. "
            "Lateral shear translation remains restrained; axial deformation "
            "and flexural rotation are carried by the interface section."
        )
        self.strain_note.setWordWrap(True)
        self.strain_note.setStyleSheet(
            "padding: 6px; background: #eef4fb; color: #40566c;"
        )
        strain_form.addRow(self.strain_note)
        boundary_layout.addWidget(self.strain_penetration_group)

        self.interface_rayleigh = QCheckBox(
            "Include base zeroLength in Rayleigh damping"
        )
        self.interface_rayleigh.setChecked(False)
        self.interface_rayleigh.setToolTip(
            "Off by default for nonlinear concentrated springs to avoid "
            "unintended damping forces. Enable only when your formulation "
            "requires it."
        )
        boundary_layout.addWidget(self.interface_rayleigh)

        self.interface_warning = QLabel(
            "Rayleigh contribution is OFF by default for nonlinear base "
            "springs, especially for NLTH."
        )
        self.interface_warning.setWordWrap(True)
        self.interface_warning.setStyleSheet(
            "padding: 6px; background: #fff7e0; color: #7a5600;"
        )
        boundary_layout.addWidget(self.interface_warning)
        body_layout.addWidget(boundary_group)

        loading_group = QGroupBox("Optional test setup")
        loading = QFormLayout(loading_group)

        self.use_axial = QCheckBox("Create constant axial-load pattern")
        self.axial = _double(100.0, 0.0, 1.0e20)
        loading.addRow(self.use_axial)
        loading.addRow(
            f"Compression load [{self.units.force}]:",
            self.axial,
        )

        self.use_lateral = QCheckBox("Create lateral reference-load pattern")
        self.lateral_load = _double(1.0, -1.0e20, 1.0e20)
        loading.addRow(self.use_lateral)
        loading.addRow(
            f"Reference load [{self.units.force}]:",
            self.lateral_load,
        )

        self.use_displacement = QCheckBox(
            "Create direct prescribed displacement (ops.sp)"
        )
        self.displacement = _double(
            0.01,
            -1.0e20,
            1.0e20,
        )
        loading.addRow(self.use_displacement)
        loading.addRow(
            f"Prescribed displacement [{self.units.length}]:",
            self.displacement,
        )

        self.use_mass = QCheckBox("Assign lumped mass at top node")
        self.top_mass = _double(1.0, 0.0, 1.0e20)
        loading.addRow(self.use_mass)
        loading.addRow(
            f"Top mass [{self.units.mass_label}]:",
            self.top_mass,
        )

        mass_dir_widget = QGroupBox("Top-mass directions")
        mass_dir_row = QHBoxLayout(mass_dir_widget)
        self.mass_directions: dict[int, QCheckBox] = {}
        for dof, label in ((1, "UX"), (2, "UY"), (3, "UZ")):
            check = QCheckBox(label)
            check.setChecked(True)
            self.mass_directions[dof] = check
            mass_dir_row.addWidget(check)
        mass_dir_row.addStretch(1)
        loading.addRow("", mass_dir_widget)

        body_layout.addWidget(loading_group)

        options_group = QGroupBox("Creation")
        options = QFormLayout(options_group)
        self.replace_geometry = QCheckBox(
            "Replace current model geometry with this standalone specimen"
        )
        self.replace_geometry.setChecked(True)
        options.addRow(self.replace_geometry)
        body_layout.addWidget(options_group)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setObjectName("Muted")
        body_layout.addWidget(self.preview)

        note = QLabel(
            "Axial, lateral-reference, and prescribed-displacement actions "
            "create separate Plain patterns. The reference load is a load "
            "shape for Pushover/Cyclic; it is not a fixed applied force once "
            "DisplacementControl is used. Direct prescribed displacement is "
            "a separate ops.sp workflow and is normally left off when using "
            "the Cyclic/Pushover templates."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        body_layout.addWidget(note)

        body_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText("Create Specimen")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.preset.currentTextChanged.connect(self._apply_preset)
        self.axis.currentIndexChanged.connect(self._axis_changed)
        self.lateral.currentIndexChanged.connect(self._lateral_changed)
        self.base_interface.currentTextChanged.connect(
            self._sync_base_interface
        )
        self.interface_rayleigh.toggled.connect(self._update_preview)
        self.planar.toggled.connect(self._update_preview)
        self.column_height.valueChanged.connect(self._update_preview)
        self.elements.valueChanged.connect(self._update_preview)
        self.element_type.currentTextChanged.connect(self._sync_formulation)
        for toggle in (
            self.use_axial,
            self.use_lateral,
            self.use_displacement,
            self.use_mass,
        ):
            toggle.toggled.connect(self._sync_optional_controls)
        self._refresh_interface_material_combos()
        self._apply_preset(self.preset.currentText())
        self._sync_formulation()
        self._sync_optional_controls()
        self._sync_base_interface()
        self._update_preview()

    def _combined_materials(self) -> dict[int, MaterialData]:
        materials = dict(self.project.materials)
        materials.update(self._pending_materials)
        return materials

    def _next_material_tag(self) -> int:
        used = set(self.project.materials) | set(self._pending_materials)
        return max(used, default=0) + 1

    def _refresh_interface_material_combos(
        self,
        selected_tag: int | None = None,
    ) -> None:
        materials = self._combined_materials()
        for _dof, (_check, combo) in self.interface_rows.items():
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for tag in sorted(materials):
                material = materials[tag]
                suffix = (
                    " · new"
                    if tag in self._pending_materials
                    else ""
                )
                combo.addItem(
                    f"{tag} - {material.name} "
                    f"({material.material_type}){suffix}",
                    tag,
                )
            wanted = selected_tag if selected_tag is not None else previous
            if wanted is not None:
                combo_index = combo.findData(int(wanted))
                if combo_index >= 0:
                    combo.setCurrentIndex(combo_index)
            combo.blockSignals(False)

        previous_bond = (
            self.strain_bond_material.currentData()
            if hasattr(self, "strain_bond_material")
            else None
        )
        if hasattr(self, "strain_bond_material"):
            self.strain_bond_material.blockSignals(True)
            self.strain_bond_material.clear()
            for tag in sorted(materials):
                material = materials[tag]
                if material.material_type != "Bond_SP01":
                    continue
                suffix = " · new" if tag in self._pending_materials else ""
                self.strain_bond_material.addItem(
                    f"{tag} - {material.name}{suffix}",
                    tag,
                )
            if previous_bond is not None:
                bond_index = self.strain_bond_material.findData(
                    int(previous_bond)
                )
                if bond_index >= 0:
                    self.strain_bond_material.setCurrentIndex(bond_index)
            self.strain_bond_material.blockSignals(False)

    def _preferred_material_tag(
        self,
        material_types: tuple[str, ...],
    ) -> int | None:
        materials = self._combined_materials()
        for tag in sorted(materials):
            if materials[tag].material_type in material_types:
                return tag
        return next(iter(sorted(materials)), None)

    def _create_interface_material(self) -> None:
        materials = self._combined_materials()
        dialog = MaterialDialog(
            next_tag=self._next_material_tag(),
            units=self.project.units,
            materials=materials,
            parent=self,
        )
        if not dialog.exec():
            return
        try:
            material = dialog.material_data()
            if material.tag in self.project.materials:
                raise ValueError(
                    f"Material tag {material.tag} already exists in the project."
                )
            if material.tag in self._pending_materials:
                raise ValueError(
                    f"Material tag {material.tag} is already staged in this wizard."
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Material Editor", str(exc))
            return

        self._pending_materials[material.tag] = material
        self._refresh_interface_material_combos(material.tag)
        if material.material_type == "Bond_SP01":
            bond_index = self.strain_bond_material.findData(material.tag)
            if bond_index >= 0:
                self.strain_bond_material.setCurrentIndex(bond_index)
        self._update_preview()

    def new_materials(self) -> list[MaterialData]:
        return [
            MaterialData.from_dict(self._pending_materials[tag].to_dict())
            for tag in self._pending_materials
        ]

    def _set_interface_single_dof(
        self,
        dof: int,
        preferred_types: tuple[str, ...],
    ) -> None:
        material_tag = self._preferred_material_tag(preferred_types)
        for row_dof, (check, combo) in self.interface_rows.items():
            check.blockSignals(True)
            check.setChecked(row_dof == dof)
            check.blockSignals(False)
            if row_dof == dof and material_tag is not None:
                index = combo.findData(material_tag)
                if index >= 0:
                    combo.setCurrentIndex(index)

    def _sync_interface_row(
        self,
        dof: int,
        checked: bool,
    ) -> None:
        _check, combo = self.interface_rows[int(dof)]
        combo.setEnabled(
            self.base_interface.currentText() != "Fixed base"
            and bool(checked)
        )
        self._update_preview()

    def _sync_base_interface(self, *_args) -> None:
        interface = self.base_interface.currentText()
        active = interface != "Fixed base"
        self.base_support.setEnabled(not active)
        if active:
            self.base_support.setCurrentText("Fixed")

        strain_mode = interface == "Bond_SP01 strain penetration"
        self.interface_dofs_group.setVisible(active and not strain_mode)
        self.strain_penetration_group.setVisible(strain_mode)

        for check, combo in self.interface_rows.values():
            check.setEnabled(active and not strain_mode)
            combo.setEnabled(
                active and not strain_mode and check.isChecked()
            )
        self.new_interface_material.setEnabled(active)
        self.interface_rayleigh.setEnabled(active)
        self.interface_warning.setVisible(active)

        if interface == "Translational slip spring":
            self._set_interface_single_dof(
                int(self.lateral.currentData()),
                ("Pinching4", "Hysteretic", "ElasticPPGap", "Steel02", "Elastic"),
            )
        elif interface == "Rotational spring":
            try:
                dof = bending_rotation_dof(
                    int(self.axis.currentData()),
                    int(self.lateral.currentData()),
                )
            except ValueError:
                dof = 6
            self._set_interface_single_dof(
                dof,
                ("Pinching4", "Hysteretic", "Steel02"),
            )
        elif interface == "Bond_SP01 strain penetration":
            for check, _combo in self.interface_rows.values():
                check.blockSignals(True)
                check.setChecked(False)
                check.blockSignals(False)
        elif interface == "Custom zeroLength":
            if not any(
                check.isChecked()
                for check, _combo in self.interface_rows.values()
            ):
                dof = int(self.lateral.currentData())
                check, _combo = self.interface_rows[dof]
                check.setChecked(True)
        else:
            for check, _combo in self.interface_rows.values():
                check.blockSignals(True)
                check.setChecked(False)
                check.blockSignals(False)

        for check, combo in self.interface_rows.values():
            combo.setEnabled(
                active and not strain_mode and check.isChecked()
            )
        self._update_preview()

    def _lateral_changed(self, *_args) -> None:
        if self.base_interface.currentText() in {
            "Translational slip spring",
            "Rotational spring",
        }:
            self._sync_base_interface()
        else:
            self._update_preview()

    def _refresh_section_combo(
        self,
        selected_tag: int | None = None,
    ) -> None:
        current = (
            selected_tag
            if selected_tag is not None
            else self.section.currentData()
            if hasattr(self, "section")
            else None
        )
        self.section.clear()
        self.section.addItem("Unassigned · assign later", None)

        combined = dict(self.project.sections)
        combined.update(self._pending_sections)
        for tag in sorted(combined):
            item = combined[tag]
            suffix = (
                " · new"
                if tag in self._pending_sections
                else ""
            )
            self.section.addItem(
                f"{tag} - {item.name} ({item.section_type}){suffix}",
                tag,
            )

        if current is not None:
            index = self.section.findData(int(current))
            if index >= 0:
                self.section.setCurrentIndex(index)

    def _next_section_tag(self) -> int:
        used = set(self.project.sections) | set(self._pending_sections)
        return max(used, default=0) + 1

    def _create_section(self) -> None:
        dialog = SectionDialog(
            self._combined_materials(),
            next_tag=self._next_section_tag(),
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        try:
            section = dialog.section_data()
            if section.tag in self.project.sections:
                raise ValueError(
                    f"Section tag {section.tag} already exists in the project."
                )
            if section.tag in self._pending_sections:
                raise ValueError(
                    f"Section tag {section.tag} is already staged in this wizard."
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Section Editor", str(exc))
            return

        pending_materials = (
            dialog.pending_materials()
            if hasattr(dialog, "pending_materials")
            else []
        )
        try:
            for material in pending_materials:
                if material.tag in self.project.materials:
                    raise ValueError(
                        f"Material tag {material.tag} already exists in the project."
                    )
                if material.tag in self._pending_materials:
                    raise ValueError(
                        f"Material tag {material.tag} is already staged "
                        "in this wizard."
                    )
            for material in pending_materials:
                self._pending_materials[material.tag] = material
        except ValueError as exc:
            QMessageBox.warning(self, "Section Editor", str(exc))
            return
        self._refresh_interface_material_combos()

        self._pending_sections[section.tag] = section
        self._refresh_section_combo(section.tag)
        self._update_preview()

    def new_sections(self) -> list[SectionData]:
        return [
            SectionData.from_dict(self._pending_sections[tag].to_dict())
            for tag in sorted(self._pending_sections)
        ]

    def _apply_preset(self, preset: str) -> None:
        self.use_axial.setChecked(False)
        self.use_lateral.setChecked(False)
        self.use_displacement.setChecked(False)
        self.use_mass.setChecked(False)
        self.base_support.setCurrentText("Fixed")
        self.top_support.setCurrentText("Free")
        self.base_interface.setCurrentText("Fixed base")
        self.interface_rayleigh.setChecked(False)
        self.planar.setChecked(True)

        if preset == "Cantilever Cyclic Test":
            self.use_lateral.setChecked(True)
            self.lateral_load.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")
        elif preset == "Cantilever Pushover":
            self.use_lateral.setChecked(True)
            self.lateral_load.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")
        elif preset == "Axial + Lateral Column":
            self.use_axial.setChecked(True)
            self.use_lateral.setChecked(True)
            self.axial.setValue(100.0)
            self.lateral_load.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")
        elif preset == "Dynamic / Shake-table Column":
            self.use_mass.setChecked(True)
            self.top_mass.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")

        self._sync_optional_controls()
        self._update_preview()

    def _axis_changed(self, *_args) -> None:
        axis = int(self.axis.currentData())
        if int(self.lateral.currentData()) == axis:
            for direction in (1, 2, 3):
                if direction != axis:
                    index = self.lateral.findData(direction)
                    if index >= 0:
                        self.lateral.setCurrentIndex(index)
                        break
        if self.base_interface.currentText() == "Rotational spring":
            self._sync_base_interface()
        else:
            self._update_preview()

    def _sync_formulation(self, *_args) -> None:
        nonlinear = self.element_type.currentText() in {
            "forceBeamColumn",
            "dispBeamColumn",
        }
        self.integration.setEnabled(nonlinear)
        self.integration_points.setEnabled(nonlinear)
        self._update_preview()

    def _sync_optional_controls(self, *_args) -> None:
        self.axial.setEnabled(self.use_axial.isChecked())
        self.lateral_load.setEnabled(self.use_lateral.isChecked())
        self.displacement.setEnabled(self.use_displacement.isChecked())
        self.top_mass.setEnabled(self.use_mass.isChecked())
        for check in self.mass_directions.values():
            check.setEnabled(self.use_mass.isChecked())
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        axis = {1: "X", 2: "Y", 3: "Z"}[int(self.axis.currentData())]
        lateral = {1: "X", 2: "Y", 3: "Z"}[
            int(self.lateral.currentData())
        ]
        options = []
        if self.use_axial.isChecked():
            options.append("axial")
        if self.use_lateral.isChecked():
            options.append("lateral reference")
        if self.use_displacement.isChecked():
            options.append("prescribed displacement")
        if self.use_mass.isChecked():
            options.append("top mass")
        section_tag = self.section.currentData()
        section_note = (
            "section unassigned"
            if section_tag is None
            else (
                f"section {int(section_tag)}"
                + (
                    " (new)"
                    if int(section_tag) in self._pending_sections
                    else ""
                )
            )
        )
        interface = self.base_interface.currentText()
        if interface == "Fixed base":
            interface_note = "fixed base"
        elif interface == "Bond_SP01 strain penetration":
            bond_tag = self.strain_bond_material.currentData()
            interface_note = (
                "Bond_SP01 strain penetration · "
                f"zeroLengthSection · Bond material {bond_tag if bond_tag is not None else 'not selected'}"
                + (
                    " · Rayleigh ON"
                    if self.interface_rayleigh.isChecked()
                    else " · Rayleigh OFF"
                )
            )
        else:
            active = [
                f"{('UX','UY','UZ','RX','RY','RZ')[dof - 1]}→"
                f"{combo.currentData()}"
                for dof, (check, combo) in self.interface_rows.items()
                if check.isChecked() and combo.currentData() is not None
            ]
            interface_note = (
                interface
                + (" [" + ", ".join(active) + "]" if active else " [not configured]")
                + (
                    " · Rayleigh ON"
                    if self.interface_rayleigh.isChecked()
                    else " · Rayleigh OFF"
                )
            )
        self.preview.setText(
            f"Preview: 1D {axis}-axis column · {self.column_height.value():g} "
            f"{self.units.length} · {self.elements.value()} element(s) · "
            f"lateral {lateral} · "
            f"{'planar' if self.planar.isChecked() else '3D'} · "
            f"{section_note} · base: {interface_note} · "
            + (", ".join(options) if options else "geometry only")
        )

    def data(self) -> TestColumnSpec:
        axis = int(self.axis.currentData())
        lateral = int(self.lateral.currentData())
        if lateral == axis and (
            self.planar.isChecked()
            or self.use_lateral.isChecked()
            or self.use_displacement.isChecked()
        ):
            raise ValueError(
                "Choose a lateral/test direction different from the column axis."
            )

        transform_data = self.transformation.currentData()
        transform_tag = None
        transform_type = "PDelta"
        if (
            isinstance(transform_data, tuple)
            and len(transform_data) == 2
        ):
            if transform_data[0] == "tag":
                transform_tag = int(transform_data[1])
                transform_type = self.project.transformations[
                    transform_tag
                ].transformation_type
            else:
                transform_type = str(transform_data[1])

        mass_dirs = tuple(
            dof
            for dof, check in self.mass_directions.items()
            if check.isChecked()
        )
        if self.use_mass.isChecked() and not mass_dirs:
            raise ValueError(
                "Select at least one direction for the top mass."
            )

        interface_type = self.base_interface.currentText()
        interface_materials: dict[int, int] = {}
        strain_bond_tag: int | None = None
        if interface_type == "Bond_SP01 strain penetration":
            if self.section.currentData() is None:
                raise ValueError(
                    "Assign a Fiber column section before enabling "
                    "Bond_SP01 strain penetration."
                )
            combined_sections = dict(self.project.sections)
            combined_sections.update(self._pending_sections)
            source_section = combined_sections.get(
                int(self.section.currentData())
            )
            if source_section is None or source_section.section_type != "Fiber":
                raise ValueError(
                    "Bond_SP01 strain penetration requires a Fiber column section."
                )
            if self.strain_bond_material.currentData() is None:
                raise ValueError(
                    "Create/select a Bond_SP01 material for strain penetration."
                )
            strain_bond_tag = int(self.strain_bond_material.currentData())
        elif interface_type != "Fixed base":
            for dof, (check, combo) in self.interface_rows.items():
                if not check.isChecked():
                    continue
                if combo.currentData() is None:
                    raise ValueError(
                        "Select a material for every active base-interface DOF."
                    )
                interface_materials[dof] = int(combo.currentData())
            if not interface_materials:
                raise ValueError(
                    "Activate at least one DOF for the Base Interface Model."
                )

        return TestColumnSpec(
            height=self.column_height.value(),
            num_elements=self.elements.value(),
            axis=axis,
            lateral_direction=lateral,
            planar=self.planar.isChecked(),
            replace_geometry=self.replace_geometry.isChecked(),
            section_tag=(
                int(self.section.currentData())
                if self.section.currentData() is not None
                else None
            ),
            transformation_tag=transform_tag,
            transformation_type=transform_type,
            element_type=self.element_type.currentText(),
            integration_type=self.integration.currentText(),
            integration_points=self.integration_points.value(),
            base_support=(
                "Fixed"
                if interface_type != "Fixed base"
                else self.base_support.currentText()
            ),
            top_support=self.top_support.currentText(),
            base_interface_type=interface_type,
            base_interface_materials=interface_materials,
            base_interface_rayleigh=(
                self.interface_rayleigh.isChecked()
                if interface_type != "Fixed base"
                else False
            ),
            strain_penetration_bond_material_tag=strain_bond_tag,
            top_mass=(
                self.top_mass.value()
                if self.use_mass.isChecked()
                else 0.0
            ),
            top_mass_directions=mass_dirs or (1, 2, 3),
            axial_load=(
                self.axial.value()
                if self.use_axial.isChecked()
                else 0.0
            ),
            lateral_reference_load=(
                self.lateral_load.value()
                if self.use_lateral.isChecked()
                else 0.0
            ),
            prescribed_displacement=(
                self.displacement.value()
                if self.use_displacement.isChecked()
                else 0.0
            ),
            name_prefix=self.preset.currentText(),
        )

    def _accept(self) -> None:
        try:
            self.data()
        except (KeyError, TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Quick 1D Column", str(exc))
            return
        self.accept()
