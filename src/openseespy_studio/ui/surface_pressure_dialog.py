from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
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
        new_pattern_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Managed Surface Pressure")
        self.setModal(True)
        self.unit_system = UnitSystem.from_mapping(units)
        self._patterns = dict(patterns)
        self._new_pattern_callback = new_pattern_callback
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
        self._refresh_pattern_choices(pressure.pattern_tag if pressure is not None else None)
        self.pattern_new = QPushButton("New Plain Pattern...")
        self.pattern_new.setEnabled(callable(self._new_pattern_callback))
        self.pattern_new.setToolTip(
            "Define a Plain load pattern now without closing this dialog."
        )
        self.pattern_new.clicked.connect(self._create_pattern_dependency)
        self.pattern_holder = QWidget()
        pattern_row = QHBoxLayout(self.pattern_holder)
        pattern_row.setContentsMargins(0, 0, 0, 0)
        pattern_row.setSpacing(4)
        pattern_row.addWidget(self.pattern, 1)
        pattern_row.addWidget(self.pattern_new)

        self.value = QDoubleSpinBox()
        self.value.setRange(-1.0e18, 1.0e18)
        self.value.setDecimals(8)
        self.value.setSingleStep(1.0)
        self.value.setValue(pressure.pressure if pressure else -1.0)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Plain pattern:", self.pattern_holder)
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

    def _refresh_pattern_choices(self, select_tag=None) -> None:
        current = self.pattern.currentData() if self.pattern.count() else None
        wanted = select_tag if select_tag is not None else current
        self.pattern.clear()
        self.pattern.addItem("Select Plain load pattern...", None)
        for tag in sorted(self._patterns):
            pattern = self._patterns[tag]
            if pattern.pattern_type == "Plain":
                self.pattern.addItem(f"{tag} - {pattern.name}", int(tag))
        if wanted is not None:
            index = self.pattern.findData(int(wanted))
            if index >= 0:
                self.pattern.setCurrentIndex(index)
        elif self.pattern.count() == 2:
            self.pattern.setCurrentIndex(1)

    def _create_pattern_dependency(self) -> None:
        if not callable(self._new_pattern_callback):
            return
        pattern = self._new_pattern_callback()
        if pattern is None:
            return
        self._patterns[int(pattern.tag)] = pattern
        self._refresh_pattern_choices(int(pattern.tag))

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
