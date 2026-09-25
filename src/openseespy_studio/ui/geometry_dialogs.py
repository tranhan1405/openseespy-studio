from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def _coord_spin(value: float = 0.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-1.0e12, 1.0e12)
    spin.setDecimals(6)
    spin.setValue(value)
    return spin


def _tag_spin(value: int = 1) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, 2_147_483_647)
    spin.setValue(value)
    return spin


from ..units import UnitSystem

class _BaseDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.root = QVBoxLayout(self)
        self.form = QFormLayout()
        self.root.addLayout(self.form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.root.addWidget(buttons)


class NodeDialog(_BaseDialog):
    def __init__(self, tag: int, parent=None):
        super().__init__("Create Node", parent)
        self.tag = _tag_spin(tag)
        self.x = _coord_spin()
        self.y = _coord_spin()
        self.z = _coord_spin()
        self.form.addRow("Tag:", self.tag)
        self.form.addRow("X:", self.x)
        self.form.addRow("Y:", self.y)
        self.form.addRow("Z:", self.z)

    def values(self):
        return self.tag.value(), self.x.value(), self.y.value(), self.z.value()


class ElementDialog(_BaseDialog):
    """Create a fully assigned structural frame member."""

    def __init__(
        self,
        tag: int,
        node_i: int = 1,
        node_j: int = 2,
        *,
        sections=None,
        transformations=None,
        new_section_callback=None,
        new_transformation_callback=None,
        ndm: int = 3,
        ndf: int = 6,
        parent=None,
    ):
        super().__init__("Create Frame Member", parent)
        self._sections = dict(sections or {})
        self._transformations = dict(transformations or {})
        self._new_section_callback = new_section_callback
        self._new_transformation_callback = new_transformation_callback
        self._dims = (int(ndm), int(ndf))

        self.tag = _tag_spin(tag)
        self.node_i = _tag_spin(node_i)
        self.node_j = _tag_spin(node_j)

        self.element_type = QComboBox()
        element_types = [
            "elasticBeamColumn",
            "ElasticTimoshenkoBeam",
            "forceBeamColumn",
            "dispBeamColumn",
        ]
        if self._dims == (2, 3):
            element_types.append("dispBeamColumnInt")
        self.element_type.addItems(element_types)

        self.section = QComboBox()
        self.section_new = QPushButton("New Section...")
        self.section_new.setEnabled(callable(self._new_section_callback))
        self.section_new.clicked.connect(self._create_section_dependency)
        self.section_holder = QWidget()
        section_row = QHBoxLayout(self.section_holder)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(4)
        section_row.addWidget(self.section, 1)
        section_row.addWidget(self.section_new)

        self.transformation = QComboBox()
        self.transformation_new = QPushButton("New Transformation...")
        self.transformation_new.setEnabled(
            callable(self._new_transformation_callback)
        )
        self.transformation_new.clicked.connect(
            self._create_transformation_dependency
        )
        self.transformation_holder = QWidget()
        transformation_row = QHBoxLayout(self.transformation_holder)
        transformation_row.setContentsMargins(0, 0, 0, 0)
        transformation_row.setSpacing(4)
        transformation_row.addWidget(self.transformation, 1)
        transformation_row.addWidget(self.transformation_new)

        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(["frame", "column", "beam-x", "beam-y"])

        self.integration_type = QComboBox()
        self.integration_type.addItems(["Lobatto", "Legendre", "Radau"])
        self.integration_points = QSpinBox()
        self.integration_points.setRange(1, 50)
        self.integration_points.setValue(5)

        self.center_rotation = QDoubleSpinBox()
        self.center_rotation.setDecimals(6)
        self.center_rotation.setRange(0.0, 1.0)
        self.center_rotation.setSingleStep(0.05)
        self.center_rotation.setValue(0.4)
        self.center_rotation.setToolTip(
            "dispBeamColumnInt center-of-rotation ratio cRot."
        )

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Formulation:", self.element_type)
        self.form.addRow("Section:", self.section_holder)
        self.form.addRow("Transformation:", self.transformation_holder)
        self.form.addRow("Group:", self.group)
        self.form.addRow("Beam integration:", self.integration_type)
        self.form.addRow("Integration points:", self.integration_points)
        self.form.addRow("Center of rotation cRot:", self.center_rotation)

        self.formulation_note = QLabel()
        self.formulation_note.setWordWrap(True)
        self.formulation_note.setStyleSheet(
            "padding: 6px; background: #f3f6f9; color: #526476;"
        )
        self.root.insertWidget(1, self.formulation_note)

        self._populate_transformations()
        self.element_type.currentTextChanged.connect(
            self._sync_formulation_controls
        )
        self._sync_formulation_controls(self.element_type.currentText())

    def _create_section_dependency(self) -> None:
        if not callable(self._new_section_callback):
            return
        section = self._new_section_callback()
        if section is None:
            return
        self._sections[int(section.tag)] = section
        self._populate_sections(self.element_type.currentText())
        index = self.section.findData(int(section.tag))
        if index >= 0:
            self.section.setCurrentIndex(index)

    def _create_transformation_dependency(self) -> None:
        if not callable(self._new_transformation_callback):
            return
        transformation = self._new_transformation_callback()
        if transformation is None:
            return
        self._transformations[int(transformation.tag)] = transformation
        self._populate_transformations()
        index = self.transformation.findData(int(transformation.tag))
        if index >= 0:
            self.transformation.setCurrentIndex(index)

    def _populate_transformations(self) -> None:
        current = self.transformation.currentData()
        element_type = self.element_type.currentText()
        self.transformation.clear()
        for tag in sorted(self._transformations):
            item = self._transformations[tag]
            if (
                element_type == "dispBeamColumnInt"
                and item.transformation_type != "LinearInt"
            ):
                continue
            if (
                element_type != "dispBeamColumnInt"
                and item.transformation_type == "LinearInt"
            ):
                continue
            self.transformation.addItem(
                f"{tag} - {item.name} ({item.transformation_type})",
                int(tag),
            )
        if current is not None:
            index = self.transformation.findData(int(current))
            if index >= 0:
                self.transformation.setCurrentIndex(index)

    def _populate_sections(self, element_type: str) -> None:
        current = self.section.currentData()
        self.section.clear()
        for tag in sorted(self._sections):
            item = self._sections[tag]
            if (
                element_type
                in {"elasticBeamColumn", "ElasticTimoshenkoBeam"}
                and item.section_type != "Elastic"
            ):
                continue
            if (
                element_type == "dispBeamColumnInt"
                and item.section_type != "FiberInt"
            ):
                continue
            self.section.addItem(
                f"{tag} - {item.name} ({item.section_type})",
                int(tag),
            )
        if current is not None:
            index = self.section.findData(current)
            if index >= 0:
                self.section.setCurrentIndex(index)

    def _sync_formulation_controls(self, element_type: str) -> None:
        nonlinear = element_type in {"forceBeamColumn", "dispBeamColumn"}
        interaction = element_type == "dispBeamColumnInt"
        self.integration_type.setEnabled(nonlinear)
        self.integration_points.setEnabled(nonlinear or interaction)
        self.integration_points.setMinimum(1 if interaction else 2)
        self.center_rotation.setEnabled(interaction)
        self._populate_sections(element_type)
        self._populate_transformations()

        if interaction:
            self.formulation_note.setText(
                "Flexure-shear interaction formulation. Requires a FiberInt "
                "section and LinearInt transformation. Integration points and "
                "cRot are direct dispBeamColumnInt parameters; no separate "
                "beamIntegration tag is used."
            )
        elif element_type == "ElasticTimoshenkoBeam":
            self.formulation_note.setText(
                "Elastic Timoshenko beam with shear deformation. Use an "
                "Elastic section containing E, G and shear areas Avy/Avz "
                "as required by the model dimension."
            )
        elif element_type == "elasticBeamColumn":
            self.formulation_note.setText(
                "Elastic Euler-Bernoulli beam-column. Shear deformation is "
                "not included; use ElasticTimoshenkoBeam when it matters."
            )
        else:
            self.formulation_note.setText(
                "Distributed-plasticity beam-column. Assign a compatible "
                "section and geometric transformation before analysis."
            )

    def values(self):
        section_tag = self.section.currentData()
        transf_tag = self.transformation.currentData()
        if section_tag is None:
            raise ValueError(
                "Select a compatible section before creating the frame member."
            )
        if transf_tag is None:
            raise ValueError(
                "Select a geometric transformation before creating the frame member."
            )
        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.element_type.currentText(),
            int(section_tag),
            int(transf_tag),
            self.group.currentText().strip() or "frame",
            self.integration_type.currentText(),
            self.integration_points.value(),
            self.center_rotation.value(),
        )


class TrussDialog(_BaseDialog):
    """Create an axial-only OpenSees Truss element."""

    def __init__(
        self,
        tag: int,
        node_i: int = 1,
        node_j: int = 2,
        *,
        materials=None,
        units=None,
        default_area: float | None = None,
        new_material_callback=None,
        parent=None,
    ):
        super().__init__("Create Truss Element", parent)
        self._materials = dict(materials or {})
        self._new_material_callback = new_material_callback
        self.unit_system = UnitSystem.from_mapping(units)

        self.tag = _tag_spin(tag)
        self.node_i = _tag_spin(node_i)
        self.node_j = _tag_spin(node_j)

        self.area = QDoubleSpinBox()
        self.area.setDecimals(9)
        self.area.setRange(1.0e-12, 1.0e18)
        if default_area is None:
            default_area = 1.0e-3 / (self.unit_system.length_to_m ** 2)
        self.area.setValue(float(default_area))

        self.material = QComboBox()
        self.material_new = QPushButton("New Material...")
        self.material_new.setEnabled(callable(self._new_material_callback))
        self.material_new.clicked.connect(self._create_material_dependency)
        self.material_holder = QWidget()
        material_row = QHBoxLayout(self.material_holder)
        material_row.setContentsMargins(0, 0, 0, 0)
        material_row.setSpacing(4)
        material_row.addWidget(self.material, 1)
        material_row.addWidget(self.material_new)
        self._refresh_material_choices()

        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(["truss", "brace", "tie", "bar"])

        self.rho = QDoubleSpinBox()
        self.rho.setDecimals(9)
        self.rho.setRange(0.0, 1.0e18)
        self.rho.setValue(0.0)

        self.consistent_mass = QCheckBox("Use consistent mass matrix")
        self.do_rayleigh = QCheckBox("Include in Rayleigh damping")

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow(
            f"Area [{self.unit_system.length}²]:",
            self.area,
        )
        self.form.addRow("Uniaxial material:", self.material_holder)
        self.form.addRow("Group:", self.group)
        self.form.addRow(
            f"rho [{self.unit_system.mass_per_length_label}]:",
            self.rho,
        )
        self.form.addRow("Mass:", self.consistent_mass)
        self.form.addRow("Rayleigh:", self.do_rayleigh)

        note = QLabel(
            "Truss is axial-only: it uses area + uniaxial material and "
            "does not require a Section, geometric Transformation, or "
            "beam Integration."
        )
        note.setWordWrap(True)
        self.root.insertWidget(1, note)

    def _refresh_material_choices(self, select_tag: int | None = None) -> None:
        current = self.material.currentData() if self.material.count() else None
        wanted = select_tag if select_tag is not None else current
        self.material.clear()
        self.material.addItem("Select Material...", None)
        for material_tag in sorted(self._materials):
            material = self._materials[material_tag]
            self.material.addItem(
                f"{material_tag} - {material.name} ({material.material_type})",
                int(material_tag),
            )
        if wanted is not None:
            index = self.material.findData(int(wanted))
            if index >= 0:
                self.material.setCurrentIndex(index)
        elif self.material.count() == 2:
            self.material.setCurrentIndex(1)

    def _create_material_dependency(self) -> None:
        if not callable(self._new_material_callback):
            return
        material = self._new_material_callback()
        if material is None:
            return
        self._materials[int(material.tag)] = material
        self._refresh_material_choices(int(material.tag))

    def values(self):
        material_tag = self.material.currentData()
        if material_tag is None:
            raise ValueError(
                "Select a uniaxial material before creating the Truss element."
            )
        if self.node_i.value() == self.node_j.value():
            raise ValueError("Truss end nodes must be different.")
        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.area.value(),
            int(material_tag),
            self.group.currentText().strip() or "truss",
            self.rho.value(),
            self.consistent_mass.isChecked(),
            self.do_rayleigh.isChecked(),
        )


class ElementFormulationDialog(_BaseDialog):
    def __init__(
        self,
        *,
        element_type: str = "elasticBeamColumn",
        integration_type: str = "Lobatto",
        integration_points: int = 5,
        force_max_iter: int = 10,
        force_tolerance: float = 1.0e-12,
        mass_per_length: float = 0.0,
        consistent_mass: bool = False,
        beam_center_ratio: float = 0.4,
        ndm: int = 3,
        ndf: int = 6,
        units=None,
        parent=None,
    ):
        super().__init__("Element Formulation", parent)
        self.unit_system = UnitSystem.from_mapping(units)
        self._dims = (int(ndm), int(ndf))

        self.element_type = QComboBox()
        element_types = [
            "elasticBeamColumn",
            "ElasticTimoshenkoBeam",
            "forceBeamColumn",
            "dispBeamColumn",
        ]
        if self._dims == (2, 3):
            element_types.append("dispBeamColumnInt")
        self.element_type.addItems(element_types)
        self.element_type.setCurrentText(element_type)

        self.integration_type = QComboBox()
        self.integration_type.addItems(["Lobatto", "Legendre"])
        self.integration_type.setCurrentText(integration_type)

        self.integration_points = QSpinBox()
        self.integration_points.setRange(1, 50)
        self.integration_points.setValue(int(integration_points))

        self.force_max_iter = QSpinBox()
        self.force_max_iter.setRange(1, 10000)
        self.force_max_iter.setValue(int(force_max_iter))

        self.force_tolerance = QDoubleSpinBox()
        self.force_tolerance.setDecimals(14)
        self.force_tolerance.setRange(1.0e-16, 1.0)
        self.force_tolerance.setValue(float(force_tolerance))

        self.mass_per_length = QDoubleSpinBox()
        self.mass_per_length.setDecimals(10)
        self.mass_per_length.setRange(0.0, 1.0e20)
        self.mass_per_length.setValue(float(mass_per_length))

        self.consistent_mass = QCheckBox(
            "Use consistent mass matrix when supported"
        )
        self.consistent_mass.setChecked(bool(consistent_mass))

        self.center_rotation = QDoubleSpinBox()
        self.center_rotation.setDecimals(6)
        self.center_rotation.setRange(0.0, 1.0)
        self.center_rotation.setSingleStep(0.05)
        self.center_rotation.setValue(float(beam_center_ratio))

        self.form.addRow("Type:", self.element_type)
        self.form.addRow("Beam integration:", self.integration_type)
        self.form.addRow("Integration points:", self.integration_points)
        self.form.addRow("Force max iterations:", self.force_max_iter)
        self.form.addRow("Force tolerance:", self.force_tolerance)
        self.form.addRow(
            f"Mass / length [{self.unit_system.mass_per_length_label}]:",
            self.mass_per_length,
        )
        self.form.addRow("", self.consistent_mass)
        self.form.addRow("Center of rotation cRot:", self.center_rotation)

        self.formulation_note = QLabel()
        self.formulation_note.setWordWrap(True)
        self.formulation_note.setStyleSheet(
            "padding: 6px; background: #f3f6f9; color: #526476;"
        )
        self.root.insertWidget(1, self.formulation_note)

        self.element_type.currentTextChanged.connect(self._sync)
        self._sync(self.element_type.currentText())

    def _sync(self, element_type: str) -> None:
        nonlinear = element_type in {"forceBeamColumn", "dispBeamColumn"}
        interaction = element_type == "dispBeamColumnInt"
        force_based = element_type == "forceBeamColumn"
        mass_matrix_supported = element_type in {
            "elasticBeamColumn",
            "ElasticTimoshenkoBeam",
            "dispBeamColumn",
        }

        self.integration_type.setEnabled(nonlinear)
        self.integration_points.setEnabled(nonlinear or interaction)
        self.integration_points.setMinimum(1 if interaction else 2)
        self.force_max_iter.setEnabled(force_based)
        self.force_tolerance.setEnabled(force_based)
        self.consistent_mass.setEnabled(mass_matrix_supported)
        if not mass_matrix_supported:
            self.consistent_mass.setChecked(False)
        self.center_rotation.setEnabled(interaction)

        if interaction:
            self.formulation_note.setText(
                "dispBeamColumnInt is a 2D flexure-shear interaction "
                "formulation. It uses FiberInt + LinearInt, with cRot and "
                "the integration-point count stored directly on the element."
            )
        elif element_type == "ElasticTimoshenkoBeam":
            self.formulation_note.setText(
                "ElasticTimoshenkoBeam includes shear deformation; section "
                "shear properties must be defined in the assigned Elastic "
                "section."
            )
        elif element_type == "forceBeamColumn":
            self.formulation_note.setText(
                "forceBeamColumn uses the selected beam integration rule. "
                "Lobatto is the common distributed-plasticity choice because "
                "it places integration points at the member ends."
            )
        elif element_type == "dispBeamColumn":
            self.formulation_note.setText(
                "dispBeamColumn uses the selected beam integration rule and "
                "supports a consistent mass matrix."
            )
        else:
            self.formulation_note.setText(
                "elasticBeamColumn is the Euler-Bernoulli elastic frame "
                "formulation; shear deformation is neglected."
            )

    def values(self) -> dict[str, object]:
        return {
            "element_type": self.element_type.currentText(),
            "integration_type": self.integration_type.currentText(),
            "integration_points": self.integration_points.value(),
            "force_max_iter": self.force_max_iter.value(),
            "force_tolerance": self.force_tolerance.value(),
            "mass_per_length": self.mass_per_length.value(),
            "consistent_mass": self.consistent_mass.isChecked(),
            "beam_center_ratio": self.center_rotation.value(),
        }


class VectorDialog(_BaseDialog):
    def __init__(self, title: str, parent=None, *, copies: bool = False):
        super().__init__(title, parent)
        self.dx = _coord_spin()
        self.dy = _coord_spin()
        self.dz = _coord_spin()
        self.form.addRow("ΔX:", self.dx)
        self.form.addRow("ΔY:", self.dy)
        self.form.addRow("ΔZ:", self.dz)
        self.count = None
        if copies:
            self.count = QSpinBox()
            self.count.setRange(1, 1000)
            self.count.setValue(1)
            self.form.addRow("Number of copies:", self.count)

    def values(self):
        count = self.count.value() if self.count is not None else 1
        return self.dx.value(), self.dy.value(), self.dz.value(), count


class RotateDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Rotate Selection", parent)
        self.axis = QComboBox()
        self.axis.addItems(["Z", "X", "Y"])
        self.angle = _coord_spin()
        self.angle.setRange(-360000.0, 360000.0)
        self.angle.setValue(90.0)
        self.px = _coord_spin()
        self.py = _coord_spin()
        self.pz = _coord_spin()
        self.form.addRow("Axis:", self.axis)
        self.form.addRow("Angle (deg):", self.angle)
        self.form.addRow("Pivot X:", self.px)
        self.form.addRow("Pivot Y:", self.py)
        self.form.addRow("Pivot Z:", self.pz)

    def values(self):
        return (
            self.axis.currentText().lower(),
            self.angle.value(),
            (self.px.value(), self.py.value(), self.pz.value()),
        )


class MirrorDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Mirror Selection", parent)
        self.plane = QComboBox()
        self.plane.addItems(["YZ (X = constant)", "XZ (Y = constant)", "XY (Z = constant)"])
        self.coordinate = _coord_spin()
        self.form.addRow("Mirror plane:", self.plane)
        self.form.addRow("Plane coordinate:", self.coordinate)

    def values(self):
        plane = ("x", "y", "z")[self.plane.currentIndex()]
        return plane, self.coordinate.value()


class SelectByIdDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Select By ID", parent)
        self.entity = QComboBox()
        self.entity.addItems(["Element", "Node"])
        from PySide6.QtWidgets import QLineEdit
        self.ids = QLineEdit()
        self.ids.setPlaceholderText("e.g. 1, 5, 10-20")
        self.form.addRow("Entity:", self.entity)
        self.form.addRow("IDs:", self.ids)

    def values(self):
        return self.entity.currentText().lower(), self.ids.text().strip()
