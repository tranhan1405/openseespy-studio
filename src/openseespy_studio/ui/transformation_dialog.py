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
        self.resize(410, 330)

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

        self.orientation_mode = QComboBox()
        self.orientation_mode.addItem("Auto (SARE managed)", "auto")
        self.orientation_mode.addItem("Manual vector", "manual")
        initial_mode = (
            transformation.orientation_mode
            if transformation is not None
            else "auto"
        )
        mode_index = self.orientation_mode.findData(initial_mode)
        self.orientation_mode.setCurrentIndex(
            mode_index if mode_index >= 0 else 0
        )
        self.orientation_mode.setToolTip(
            "Auto lets SARE choose a safe common reference direction from "
            "the frame members using this transformation. Choose Manual "
            "only when you need explicit section orientation control."
        )

        vec = transformation.vecxz if transformation else (0.0, 0.0, 1.0)
        self.vx = _float_spin(vec[0])
        self.vy = _float_spin(vec[1])
        self.vz = _float_spin(vec[2])
        for widget in (self.vx, self.vy, self.vz):
            widget.setToolTip(
                "Manual OpenSees vecxz component. Ignored while Orientation "
                "is Auto."
            )

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.transformation_type)
        form.addRow("Orientation:", self.orientation_mode)
        form.addRow("Manual vecxz X:", self.vx)
        form.addRow("Manual vecxz Y:", self.vy)
        form.addRow("Manual vecxz Z:", self.vz)
        root.addLayout(form)

        self.orientation_mode.currentIndexChanged.connect(
            self._sync_orientation_mode
        )
        self._sync_orientation_mode()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _sync_orientation_mode(self) -> None:
        manual = self.orientation_mode.currentData() == "manual"
        for widget in (self.vx, self.vy, self.vz):
            widget.setEnabled(manual)

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
            orientation_mode=str(self.orientation_mode.currentData()),
        )
