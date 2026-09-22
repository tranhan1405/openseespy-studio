from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from ..project import SurfacePressureData
from ..units import UnitSystem


class SurfacePressureDialog(QDialog):
    def __init__(
        self,
        patterns,
        *,
        surface_tag: int,
        pressure: SurfacePressureData | None = None,
        next_tag: int = 1,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Managed Surface Pressure")
        self.setModal(True)
        self.unit_system = UnitSystem.from_mapping(units)
        self.surface_tag = int(surface_tag)

        root = QVBoxLayout(self)
        info = QLabel(
            f"Surface {self.surface_tag}\n"
            "Pressure is stored on Geometry and regenerated on all generated "
            "Shell elements after remeshing. Positive follows +Surface normal."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(pressure.tag if pressure else int(next_tag))
        self.tag.setEnabled(pressure is None)
        self.name = QLineEdit(
            pressure.name
            if pressure
            else f"Surface {self.surface_tag} Pressure"
        )
        self.pattern = QComboBox()
        for tag in sorted(patterns):
            pattern = patterns[tag]
            if pattern.pattern_type == "Plain":
                self.pattern.addItem(f"{tag} - {pattern.name}", int(tag))
        if pressure is not None:
            index = self.pattern.findData(pressure.pattern_tag)
            if index >= 0:
                self.pattern.setCurrentIndex(index)

        self.value = QDoubleSpinBox()
        self.value.setRange(-1.0e18, 1.0e18)
        self.value.setDecimals(8)
        self.value.setSingleStep(1.0)
        self.value.setValue(pressure.pressure if pressure else -1.0)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Plain pattern:", self.pattern)
        form.addRow(
            f"Pressure [{self.unit_system.stress_label}]:",
            self.value,
        )
        root.addLayout(form)

        note = QLabel(
            "Flip Surface Normal preserves the physical pressure direction: "
            "SARE reverses the stored pressure sign when it reverses the "
            "Surface winding."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def data(self) -> SurfacePressureData:
        if self.pattern.currentData() is None:
            raise ValueError("Create a Plain load pattern first.")
        return SurfacePressureData(
            tag=self.tag.value(),
            name=(
                self.name.text().strip()
                or f"Surface Pressure {self.tag.value()}"
            ),
            surface_tag=self.surface_tag,
            pattern_tag=int(self.pattern.currentData()),
            pressure=self.value.value(),
            generated_element_load_tags=[],
        )

    def _accept(self) -> None:
        try:
            self.data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Managed Surface Pressure",
                str(exc),
            )
            return
        self.accept()
