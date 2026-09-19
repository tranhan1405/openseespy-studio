from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..project import (
    MATERIAL_DEFAULTS,
    MATERIAL_ENGINEERING_DEFAULTS,
    MATERIAL_PARAMETER_ORDER,
    MaterialData,
)


class MaterialDialog(QDialog):
    def __init__(self, material: MaterialData | None = None, *, next_tag: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Material Editor")
        self.setModal(True)
        self.resize(380, 420)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(material.tag if material else next_tag)

        self.name = QLineEdit()
        self.name.setText(material.name if material else f"Material {next_tag}")

        self.material_type = QComboBox()
        self.material_type.addItems(sorted(MATERIAL_PARAMETER_ORDER))
        if material:
            self.material_type.setCurrentText(material.material_type)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.material_type)

        engineering_defaults = MATERIAL_ENGINEERING_DEFAULTS[
            material.material_type if material else self.material_type.currentText()
        ]
        self.poisson_ratio = QDoubleSpinBox()
        self.poisson_ratio.setDecimals(6)
        self.poisson_ratio.setRange(-0.99, 0.499999)
        self.poisson_ratio.setSingleStep(0.01)
        self.poisson_ratio.setValue(
            material.poisson_ratio
            if material is not None
            else engineering_defaults["poisson_ratio"]
        )

        self.density = QDoubleSpinBox()
        self.density.setDecimals(6)
        self.density.setRange(0.0, 1.0e12)
        self.density.setValue(
            material.density
            if material is not None
            else engineering_defaults["density"]
        )

        form.addRow("Poisson ratio ν:", self.poisson_ratio)
        form.addRow("Density ρ [kg/m³]:", self.density)
        root.addLayout(form)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.parameter_widget = QWidget()
        self.parameter_form = QFormLayout(self.parameter_widget)
        scroll.setWidget(self.parameter_widget)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._parameter_spins: dict[str, QDoubleSpinBox] = {}
        self._initial_material = material
        self.material_type.currentTextChanged.connect(self._material_type_changed)
        self._rebuild_parameters(self.material_type.currentText())

    def _material_type_changed(self, material_type: str) -> None:
        self._rebuild_parameters(material_type)
        if self._initial_material is None:
            defaults = MATERIAL_ENGINEERING_DEFAULTS[material_type]
            self.poisson_ratio.setValue(defaults["poisson_ratio"])
            self.density.setValue(defaults["density"])

    def _clear_parameter_form(self) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self._parameter_spins.clear()

    def _rebuild_parameters(self, material_type: str) -> None:
        previous = {
            key: spin.value()
            for key, spin in self._parameter_spins.items()
        }
        self._clear_parameter_form()

        defaults = MATERIAL_DEFAULTS[material_type]
        initial_parameters = (
            self._initial_material.parameters
            if (
                self._initial_material is not None
                and self._initial_material.material_type == material_type
            )
            else {}
        )

        for key in MATERIAL_PARAMETER_ORDER[material_type]:
            spin = QDoubleSpinBox()
            spin.setDecimals(10)
            spin.setRange(-1.0e20, 1.0e20)
            spin.setSingleStep(0.01)
            spin.setValue(
                float(
                    previous.get(
                        key,
                        initial_parameters.get(key, defaults[key]),
                    )
                )
            )
            stress_keys = {
                "E",
                "Fy",
                "E0",
                "fpc",
                "fpcu",
                "ft",
                "Ets",
            }
            label = f"{key} [Pa]:" if key in stress_keys else f"{key}:"
            self.parameter_form.addRow(label, spin)
            self._parameter_spins[key] = spin

    def material_data(self) -> MaterialData:
        material_type = self.material_type.currentText()
        return MaterialData(
            tag=self.tag.value(),
            name=self.name.text().strip() or f"Material {self.tag.value()}",
            material_type=material_type,
            parameters={
                key: self._parameter_spins[key].value()
                for key in MATERIAL_PARAMETER_ORDER[material_type]
            },
            poisson_ratio=self.poisson_ratio.value(),
            density=self.density.value(),
        )
