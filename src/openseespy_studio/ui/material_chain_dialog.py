from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..material_chain import (
    SpringMaterialChainResult,
    SpringMaterialChainSpec,
    build_spring_material_chain,
)
from ..project import MATERIAL_DEFAULTS, MaterialData
from .material_test_dialog import MaterialTestDialog


PA_PER_MPA = 1.0e6


def _spin(
    value: float,
    *,
    decimals: int = 8,
    minimum: float = -1.0e12,
    maximum: float = 1.0e20,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(minimum, maximum)
    spin.setValue(float(value))
    return spin


class MaterialChainDialog(QDialog):
    """Build Steel02 → Fatigue → MinMax for research spring workflows."""

    def __init__(
        self,
        materials: dict[int, MaterialData],
        *,
        units=None,
        target_dof_label: str = "UX",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Research Nonlinear Spring Chain")
        self.setModal(True)
        self.resize(610, 660)
        self.materials = dict(materials)
        self.units = dict(units or {})
        self.target_dof_label = str(target_dof_label)

        root = QVBoxLayout(self)

        intro = QLabel(
            "Build a dependency-safe uniaxial chain and assign the outermost "
            f"material to zeroLength DOF {self.target_dof_label}. "
            "The chain is committed only when the Connection Editor is accepted."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(intro)

        name_form = QFormLayout()
        self.name_prefix = QLineEdit("Research Spring")
        name_form.addRow("Chain name:", self.name_prefix)
        root.addLayout(name_form)

        base_group = QGroupBox("1. Base material")
        base_form = QFormLayout(base_group)
        self.base_source = QComboBox()
        self.base_source.addItem("Create new Steel02", "__new_steel02__")
        for tag in sorted(self.materials):
            material = self.materials[tag]
            self.base_source.addItem(
                f"Use existing {tag} - {material.name} "
                f"({material.material_type})",
                int(tag),
            )
        base_form.addRow("Source:", self.base_source)

        steel = MATERIAL_DEFAULTS["Steel02"]
        self.steel_fy = _spin(steel["Fy"] / PA_PER_MPA, decimals=4)
        self.steel_e0 = _spin(steel["E0"] / PA_PER_MPA, decimals=4)
        self.steel_b = _spin(steel["b"], decimals=8)
        self.steel_r0 = _spin(steel["R0"], decimals=8)
        self.steel_cr1 = _spin(steel["cR1"], decimals=8)
        self.steel_cr2 = _spin(steel["cR2"], decimals=8)

        self.steel_group = QGroupBox("New Steel02 parameters")
        steel_form = QFormLayout(self.steel_group)
        steel_form.addRow("Fy [MPa]:", self.steel_fy)
        steel_form.addRow("E0 [MPa]:", self.steel_e0)
        steel_form.addRow("b:", self.steel_b)
        steel_form.addRow("R0:", self.steel_r0)
        steel_form.addRow("cR1:", self.steel_cr1)
        steel_form.addRow("cR2:", self.steel_cr2)
        base_form.addRow(self.steel_group)
        root.addWidget(base_group)

        fatigue_defaults = MATERIAL_DEFAULTS["Fatigue"]
        self.add_fatigue = QCheckBox("Add Fatigue wrapper")
        self.add_fatigue.setChecked(True)
        self.fatigue_group = QGroupBox("2. Fatigue")
        fatigue_layout = QVBoxLayout(self.fatigue_group)
        fatigue_layout.addWidget(self.add_fatigue)
        fatigue_form = QFormLayout()
        self.fatigue_e0 = _spin(fatigue_defaults["E0"], decimals=8)
        self.fatigue_m = _spin(fatigue_defaults["m"], decimals=8)
        self.fatigue_min = _spin(fatigue_defaults["min"], decimals=8)
        self.fatigue_max = _spin(fatigue_defaults["max"], decimals=8)
        fatigue_form.addRow("E0:", self.fatigue_e0)
        fatigue_form.addRow("m:", self.fatigue_m)
        fatigue_form.addRow("Minimum deformation:", self.fatigue_min)
        fatigue_form.addRow("Maximum deformation:", self.fatigue_max)
        fatigue_layout.addLayout(fatigue_form)
        root.addWidget(self.fatigue_group)

        minmax_defaults = MATERIAL_DEFAULTS["MinMax"]
        self.add_minmax = QCheckBox("Add MinMax outer wrapper")
        self.add_minmax.setChecked(True)
        self.minmax_group = QGroupBox("3. MinMax")
        minmax_layout = QVBoxLayout(self.minmax_group)
        minmax_layout.addWidget(self.add_minmax)
        minmax_form = QFormLayout()
        self.minmax_min = _spin(minmax_defaults["min"], decimals=8)
        self.minmax_max = _spin(minmax_defaults["max"], decimals=8)
        minmax_form.addRow("Minimum deformation:", self.minmax_min)
        minmax_form.addRow("Maximum deformation:", self.minmax_max)
        minmax_layout.addLayout(minmax_form)
        root.addWidget(self.minmax_group)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(
            "padding: 9px; background: #f5f7f9; color: #526578;"
        )
        root.addWidget(self.preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.test_button = buttons.addButton(
            "Test Final Chain...",
            QDialogButtonBox.ActionRole,
        )
        self.test_button.clicked.connect(self._test_chain)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.base_source.currentIndexChanged.connect(self._sync_ui)
        self.add_fatigue.toggled.connect(self._sync_ui)
        self.add_minmax.toggled.connect(self._sync_ui)
        for widget in (
            self.steel_fy,
            self.steel_e0,
            self.steel_b,
            self.steel_r0,
            self.steel_cr1,
            self.steel_cr2,
            self.fatigue_e0,
            self.fatigue_m,
            self.fatigue_min,
            self.fatigue_max,
            self.minmax_min,
            self.minmax_max,
        ):
            widget.valueChanged.connect(self._update_preview)
        self.name_prefix.textChanged.connect(self._update_preview)
        self._sync_ui()

    def _sync_ui(self) -> None:
        self.steel_group.setVisible(
            self.base_source.currentData() == "__new_steel02__"
        )
        fatigue_enabled = self.add_fatigue.isChecked()
        for widget in (
            self.fatigue_e0,
            self.fatigue_m,
            self.fatigue_min,
            self.fatigue_max,
        ):
            widget.setEnabled(fatigue_enabled)

        minmax_enabled = self.add_minmax.isChecked()
        self.minmax_min.setEnabled(minmax_enabled)
        self.minmax_max.setEnabled(minmax_enabled)
        self._update_preview()

    def _spec(self) -> SpringMaterialChainSpec:
        source = self.base_source.currentData()
        create_steel = source == "__new_steel02__"

        if self.add_fatigue.isChecked():
            if self.fatigue_min.value() >= self.fatigue_max.value():
                raise ValueError(
                    "Fatigue minimum deformation must be less than maximum."
                )
        if self.add_minmax.isChecked():
            if self.minmax_min.value() >= self.minmax_max.value():
                raise ValueError(
                    "MinMax minimum deformation must be less than maximum."
                )

        return SpringMaterialChainSpec(
            base_material_tag=None if create_steel else int(source),
            create_steel02=create_steel,
            steel02_parameters={
                "Fy": self.steel_fy.value() * PA_PER_MPA,
                "E0": self.steel_e0.value() * PA_PER_MPA,
                "b": self.steel_b.value(),
                "R0": self.steel_r0.value(),
                "cR1": self.steel_cr1.value(),
                "cR2": self.steel_cr2.value(),
            },
            add_fatigue=self.add_fatigue.isChecked(),
            fatigue_parameters={
                "E0": self.fatigue_e0.value(),
                "m": self.fatigue_m.value(),
                "min": self.fatigue_min.value(),
                "max": self.fatigue_max.value(),
            },
            add_minmax=self.add_minmax.isChecked(),
            minmax_parameters={
                "min": self.minmax_min.value(),
                "max": self.minmax_max.value(),
            },
            name_prefix=self.name_prefix.text().strip() or "Research Spring",
        )

    def chain_result(self) -> SpringMaterialChainResult:
        return build_spring_material_chain(
            self._spec(),
            self.materials,
        )

    def _combined_materials(
        self,
        result: SpringMaterialChainResult,
    ) -> dict[int, MaterialData]:
        materials = dict(self.materials)
        for material in result.materials:
            materials[material.tag] = material
        return materials

    def _update_preview(self, *args) -> None:
        try:
            result = self.chain_result()
        except (TypeError, ValueError) as exc:
            self.preview.setText(str(exc))
            self.preview.setStyleSheet(
                "padding: 9px; background: #fff0f0; color: #8a2f2f;"
            )
            return

        materials = self._combined_materials(result)
        chain: list[str] = []
        tag = result.final_tag
        seen: set[int] = set()
        while tag in materials and tag not in seen:
            seen.add(tag)
            material = materials[tag]
            chain.append(f"{material.material_type} [{material.tag}]")
            if (
                material.material_type in {"Fatigue", "MinMax"}
                and material.base_material_tag is not None
            ):
                tag = material.base_material_tag
            else:
                break
        chain.reverse()

        self.preview.setText(
            "Chain: "
            + "  →  ".join(chain)
            + f"  →  zeroLength {self.target_dof_label}\n"
            + f"Assigned outer material: {result.final_tag}"
        )
        self.preview.setStyleSheet(
            "padding: 9px; background: #eaf6ee; color: #276738;"
        )

    def _test_chain(self) -> None:
        try:
            result = self.chain_result()
        except ValueError as exc:
            QMessageBox.warning(self, "Research Spring Chain", str(exc))
            return

        materials = self._combined_materials(result)
        final_material = materials[result.final_tag]
        dialog = MaterialTestDialog(
            final_material,
            units=self.units,
            materials=materials,
            parent=self,
        )
        dialog.exec()

    def _validate_and_accept(self) -> None:
        try:
            self.chain_result()
        except ValueError as exc:
            QMessageBox.warning(self, "Research Spring Chain", str(exc))
            return
        self.accept()
