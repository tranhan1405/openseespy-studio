from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)


def _float_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-1.0e20, 1.0e20)
    spin.setDecimals(8)
    spin.setValue(float(value))
    return spin


class SolidBrickDialog(QDialog):
    """Direct editor for FEWIZ eight-node OpenSees solid bricks."""

    FORMULATIONS = (
        ("stdBrick (standard integration)", "stdBrick"),
        ("SSPbrick (stabilized single point)", "SSPbrick"),
        ("bbarBrick (mixed volume/pressure)", "bbarBrick"),
    )

    def __init__(
        self,
        *,
        tag: int,
        nodes,
        nd_materials,
        initial_nodes=(),
        element=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit 3D Solid Brick"
            if element is not None
            else "Create 3D Solid Brick"
        )
        self.setModal(True)
        self.setMinimumWidth(560)
        self._nodes = dict(nodes or {})
        self._nd_materials = dict(nd_materials or {})

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
        while len(selected) < 8:
            candidate = next(
                (value for value in fallback if value not in selected),
                None,
            )
            if candidate is None:
                break
            selected.append(candidate)

        self.node_combos = []
        labels = (
            "Node 1 (I):", "Node 2 (J):", "Node 3 (K):", "Node 4 (L):",
            "Node 5 (M):", "Node 6 (N):", "Node 7 (P):", "Node 8 (Q):",
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
                wanted = combo.findData(int(selected[index]))
                if wanted >= 0:
                    combo.setCurrentIndex(wanted)
            self.node_combos.append(combo)
            form.addRow(label, combo)

        self.formulation = QComboBox()
        for label, value in self.FORMULATIONS:
            self.formulation.addItem(label, value)
        if element is not None:
            index = self.formulation.findData(element.element_type)
            if index >= 0:
                self.formulation.setCurrentIndex(index)
        form.addRow("Formulation:", self.formulation)

        self.material = QComboBox()
        for material_tag in sorted(self._nd_materials):
            material = self._nd_materials[material_tag]
            self.material.addItem(
                f"{material_tag} - {material.name} "
                f"({material.material_type})",
                int(material_tag),
            )
        if element is not None and element.solid_material_tag is not None:
            index = self.material.findData(int(element.solid_material_tag))
            if index >= 0:
                self.material.setCurrentIndex(index)
        form.addRow("nD Material:", self.material)

        existing_body = (
            element.solid_body_force
            if element is not None
            else (0.0, 0.0, 0.0)
        )
        self.body_x = _float_spin(existing_body[0])
        self.body_y = _float_spin(existing_body[1])
        self.body_z = _float_spin(existing_body[2])
        form.addRow("Body force b1 (global X):", self.body_x)
        form.addRow("Body force b2 (global Y):", self.body_y)
        form.addRow("Body force b3 (global Z):", self.body_z)

        note = QLabel(
            "Use OpenSees eight-node brick ordering: nodes 1-4 form one "
            "face and nodes 5-8 the opposite face with matching orientation. "
            "FEWIZ checks the center Jacobian and rejects inverted or "
            "degenerate ordering."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, object]:
        nodes = tuple(
            int(combo.currentData())
            for combo in self.node_combos
        )
        if len(set(nodes)) != 8:
            raise ValueError(
                "3D solid element requires eight distinct nodes."
            )
        material_tag = self.material.currentData()
        if material_tag is None:
            raise ValueError("Select an nDMaterial.")
        return {
            "tag": int(self.tag.value()),
            "nodes": nodes,
            "formulation": str(self.formulation.currentData()),
            "material_tag": int(material_tag),
            "body_force": (
                float(self.body_x.value()),
                float(self.body_y.value()),
                float(self.body_z.value()),
            ),
        }

    def _accept(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "3D Solid Brick", str(exc))
            return
        self.accept()
