from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..model import CONTINUUM_QUAD_ELEMENT_TYPES


def _float_spin(
    value: float,
    *,
    low: float = -1.0e20,
    high: float = 1.0e20,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(8)
    spin.setValue(float(value))
    return spin


class ContinuumQuadDialog(QDialog):
    """Direct editor for the first FEWIZ 2-D continuum quad formulations."""

    FORMULATIONS = (
        ("FourNodeQuad (full integration)", "quad"),
        ("SSPquad (stabilized single point)", "SSPquad"),
        ("bbarQuad (B-bar · plane strain)", "bbarQuad"),
        ("enhancedQuad (enhanced strain)", "enhancedQuad"),
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
            "Edit 2D Continuum Quad"
            if element is not None
            else "Create 2D Continuum Quad"
        )
        self.setModal(True)
        self.setMinimumWidth(520)
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
        while len(selected) < 4:
            candidate = next(
                (value for value in fallback if value not in selected),
                None,
            )
            if candidate is None:
                break
            selected.append(candidate)

        self.node_combos = []
        for index, label in enumerate(
            ("Node I:", "Node J:", "Node K:", "Node L:")
        ):
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
        if (
            element is not None
            and element.element_type in CONTINUUM_QUAD_ELEMENT_TYPES
        ):
            index = self.formulation.findData(element.element_type)
            if index >= 0:
                self.formulation.setCurrentIndex(index)
        form.addRow("Formulation:", self.formulation)

        self.behavior = QComboBox()
        self.behavior.addItems(["PlaneStrain", "PlaneStress"])
        if element is not None:
            self.behavior.setCurrentText(element.continuum_type)
        form.addRow("Material behavior:", self.behavior)

        self.material = QComboBox()
        for material_tag in sorted(self._nd_materials):
            material = self._nd_materials[material_tag]
            self.material.addItem(
                f"{material_tag} - {material.name} "
                f"({material.material_type})",
                int(material_tag),
            )
        existing_material = (
            element.continuum_material_tag
            if element is not None
            else None
        )
        if existing_material is not None:
            index = self.material.findData(int(existing_material))
            if index >= 0:
                self.material.setCurrentIndex(index)
        form.addRow("nD Material:", self.material)

        self.thickness = _float_spin(
            element.continuum_thickness
            if element is not None
            else 1.0,
            low=1.0e-12,
        )
        form.addRow("Thickness:", self.thickness)

        self.pressure = _float_spin(
            element.continuum_pressure
            if element is not None
            else 0.0
        )
        form.addRow("Edge pressure:", self.pressure)

        self.density = _float_spin(
            element.continuum_density
            if element is not None
            else 0.0,
            low=0.0,
        )
        form.addRow("Mass density (rho):", self.density)

        existing_body = (
            element.continuum_body_force
            if element is not None
            else (0.0, 0.0)
        )
        self.body_x = _float_spin(existing_body[0])
        self.body_y = _float_spin(existing_body[1])
        form.addRow("Body force b1 (global X):", self.body_x)
        form.addRow("Body force b2 (global Y):", self.body_y)

        note = QLabel(
            "Nodes must be four distinct corners ordered counter-clockwise "
            "in the global XY plane. FourNodeQuad supports pressure, density "
            "and body force; SSPquad supports body force. bbarQuad is "
            "PlaneStrain-only. bbarQuad/enhancedQuad do not use pressure, "
            "density or body-force inputs."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        self.formulation.currentIndexChanged.connect(self._sync_formulation)
        self._sync_formulation()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _sync_formulation(self, *_args) -> None:
        formulation = str(self.formulation.currentData())
        is_quad = formulation == "quad"
        supports_body_force = formulation in {"quad", "SSPquad"}
        is_bbar = formulation == "bbarQuad"

        self.behavior.setEnabled(not is_bbar)
        if is_bbar:
            self.behavior.setCurrentText("PlaneStrain")

        self.pressure.setEnabled(is_quad)
        self.density.setEnabled(is_quad)
        self.body_x.setEnabled(supports_body_force)
        self.body_y.setEnabled(supports_body_force)

        if not is_quad:
            self.pressure.setValue(0.0)
            self.density.setValue(0.0)
        if not supports_body_force:
            self.body_x.setValue(0.0)
            self.body_y.setValue(0.0)

    def values(self) -> dict[str, object]:
        nodes = tuple(
            int(combo.currentData())
            for combo in self.node_combos
        )
        if len(set(nodes)) != 4:
            raise ValueError(
                "2D continuum element requires four distinct nodes."
            )
        material_tag = self.material.currentData()
        if material_tag is None:
            raise ValueError("Select an nDMaterial.")
        return {
            "tag": int(self.tag.value()),
            "nodes": nodes,
            "formulation": str(self.formulation.currentData()),
            "behavior": self.behavior.currentText(),
            "material_tag": int(material_tag),
            "thickness": float(self.thickness.value()),
            "pressure": float(self.pressure.value()),
            "density": float(self.density.value()),
            "body_force": (
                float(self.body_x.value()),
                float(self.body_y.value()),
            ),
        }

    def _accept(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "2D Continuum Quad", str(exc))
            return
        self.accept()
