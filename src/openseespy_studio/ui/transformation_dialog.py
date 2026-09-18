from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..project import TransformationData


def _float_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(10)
    spin.setRange(-1.0e12, 1.0e12)
    spin.setValue(float(value))
    return spin


class TransformationDialog(QDialog):
    def __init__(
        self,
        transformation: TransformationData | None = None,
        *,
        next_tag: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Geometric Transformation Editor")
        self.setModal(True)
        self.resize(390, 280)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(transformation.tag if transformation else next_tag)

        self.name = QLineEdit()
        self.name.setText(
            transformation.name
            if transformation
            else f"Transformation {next_tag}"
        )

        self.transformation_type = QComboBox()
        self.transformation_type.addItems([
            "Linear",
            "PDelta",
            "Corotational",
        ])
        if transformation:
            self.transformation_type.setCurrentText(
                transformation.transformation_type
            )

        vec = transformation.vecxz if transformation else (0.0, 0.0, 1.0)
        self.vx = _float_spin(vec[0])
        self.vy = _float_spin(vec[1])
        self.vz = _float_spin(vec[2])

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.transformation_type)
        form.addRow("vecxz X:", self.vx)
        form.addRow("vecxz Y:", self.vy)
        form.addRow("vecxz Z:", self.vz)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def transformation_data(self) -> TransformationData:
        return TransformationData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Transformation {self.tag.value()}",
            transformation_type=self.transformation_type.currentText(),
            vecxz=(
                self.vx.value(),
                self.vy.value(),
                self.vz.value(),
            ),
        )
