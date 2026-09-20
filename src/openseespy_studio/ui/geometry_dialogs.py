from __future__ import annotations

from dataclasses import dataclass

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
        parent=None,
    ):
        super().__init__("Create Frame Member", parent)
        self._sections = dict(sections or {})
        self._transformations = dict(transformations or {})

        self.tag = _tag_spin(tag)
        self.node_i = _tag_spin(node_i)
        self.node_j = _tag_spin(node_j)

        self.element_type = QComboBox()
        self.element_type.addItems([
            "elasticBeamColumn",
            "forceBeamColumn",
            "dispBeamColumn",
        ])

        self.section = QComboBox()
        self.transformation = QComboBox()

        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(["frame", "column", "beam-x", "beam-y"])

        self.integration_type = QComboBox()
        self.integration_type.addItems(["Lobatto", "Legendre", "Radau"])
        self.integration_points = QSpinBox()
        self.integration_points.setRange(2, 50)
        self.integration_points.setValue(5)

        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Formulation:", self.element_type)
        self.form.addRow("Section:", self.section)
        self.form.addRow("Transformation:", self.transformation)
        self.form.addRow("Group:", self.group)
        self.form.addRow("Beam integration:", self.integration_type)
        self.form.addRow("Integration points:", self.integration_points)

        self._populate_transformations()
        self.element_type.currentTextChanged.connect(
            self._sync_formulation_controls
        )
        self._sync_formulation_controls(self.element_type.currentText())

        note = QLabel(
            "Frame creates a solver-ready structural member. "
            "Section and geometric transformation are assigned at creation."
        )
        note.setWordWrap(True)
        self.root.insertWidget(1, note)

    def _populate_transformations(self) -> None:
        self.transformation.clear()
        for tag in sorted(self._transformations):
            item = self._transformations[tag]
            self.transformation.addItem(
                f"{tag} - {item.name} ({item.transformation_type})",
                int(tag),
            )

    def _populate_sections(self, element_type: str) -> None:
        current = self.section.currentData()
        self.section.clear()
        for tag in sorted(self._sections):
            item = self._sections[tag]
            if (
                element_type == "elasticBeamColumn"
                and item.section_type != "Elastic"
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
        self.integration_type.setEnabled(nonlinear)
        self.integration_points.setEnabled(nonlinear)
        self._populate_sections(element_type)

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
        units=None,
        parent=None,
    ):
        super().__init__("Element Formulation", parent)
        self.unit_system = UnitSystem.from_mapping(units)

        self.element_type = QComboBox()
        self.element_type.addItems([
            "elasticBeamColumn",
            "forceBeamColumn",
            "dispBeamColumn",
        ])
        self.element_type.setCurrentText(element_type)

        self.integration_type = QComboBox()
        self.integration_type.addItems(["Lobatto", "Legendre"])
        self.integration_type.setCurrentText(integration_type)

        self.integration_points = QSpinBox()
        self.integration_points.setRange(2, 50)
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
            "Use consistent mass matrix (dispBeamColumn)"
        )
        self.consistent_mass.setChecked(bool(consistent_mass))

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

        note = QLabel(
            "Lobatto places integration points at the member ends and is "
            "the common distributed-plasticity choice for forceBeamColumn."
        )
        note.setWordWrap(True)
        self.root.insertWidget(1, note)

        self.element_type.currentTextChanged.connect(self._sync)
        self._sync(self.element_type.currentText())

    def _sync(self, element_type: str) -> None:
        nonlinear = element_type in {"forceBeamColumn", "dispBeamColumn"}
        force_based = element_type == "forceBeamColumn"
        displacement_based = element_type == "dispBeamColumn"

        self.integration_type.setEnabled(nonlinear)
        self.integration_points.setEnabled(nonlinear)
        self.force_max_iter.setEnabled(force_based)
        self.force_tolerance.setEnabled(force_based)
        self.consistent_mass.setEnabled(displacement_based)

    def values(self) -> dict[str, object]:
        return {
            "element_type": self.element_type.currentText(),
            "integration_type": self.integration_type.currentText(),
            "integration_points": self.integration_points.value(),
            "force_max_iter": self.force_max_iter.value(),
            "force_tolerance": self.force_tolerance.value(),
            "mass_per_length": self.mass_per_length.value(),
            "consistent_mass": self.consistent_mass.isChecked(),
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
