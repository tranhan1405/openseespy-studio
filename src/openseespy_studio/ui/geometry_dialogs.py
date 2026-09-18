from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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
    def __init__(
        self,
        tag: int,
        node_i: int = 1,
        node_j: int = 2,
        parent=None,
    ):
        super().__init__("Create Element", parent)
        self.tag = _tag_spin(tag)
        self.node_i = _tag_spin(node_i)
        self.node_j = _tag_spin(node_j)
        self.element_type = QComboBox()
        self.element_type.addItems([
            "elasticBeamColumn",
            "forceBeamColumn",
            "dispBeamColumn",
            "truss",
            "zeroLength",
        ])
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(["frame", "column", "beam-x", "beam-y"])
        self.form.addRow("Tag:", self.tag)
        self.form.addRow("Node I:", self.node_i)
        self.form.addRow("Node J:", self.node_j)
        self.form.addRow("Type:", self.element_type)
        self.form.addRow("Group:", self.group)

    def values(self):
        return (
            self.tag.value(),
            self.node_i.value(),
            self.node_j.value(),
            self.element_type.currentText(),
            self.group.currentText().strip() or "frame",
        )


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
