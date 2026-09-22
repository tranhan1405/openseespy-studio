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

from ..project import SurfaceEdgeLoadData
from ..units import UnitSystem


def _spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-1.0e18, 1.0e18)
    spin.setDecimals(8)
    spin.setValue(float(value))
    spin.setSingleStep(1.0)
    return spin


class SurfaceEdgeLoadDialog(QDialog):
    COMPONENTS = ("qX", "qY", "qZ", "mX", "mY", "mZ")

    def __init__(
        self,
        patterns,
        *,
        surface_tag: int,
        edge_index: int,
        edge_load: SurfaceEdgeLoadData | None = None,
        next_tag: int = 1,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Managed Surface Edge Line Load")
        self.setModal(True)
        self.unit_system = UnitSystem.from_mapping(units)
        self.surface_tag = int(surface_tag)
        self.edge_index = int(edge_index)

        root = QVBoxLayout(self)
        info = QLabel(
            f"Surface {self.surface_tag} · Edge {self.edge_index}\n"
            "Uniform global line resultants. SARE converts them to "
            "consistent equivalent nodal loads and regenerates them after "
            "remeshing."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(edge_load.tag if edge_load else int(next_tag))
        self.name = QLineEdit(
            edge_load.name
            if edge_load
            else f"S{self.surface_tag} E{self.edge_index} Line Load"
        )
        self.pattern = QComboBox()
        for tag in sorted(patterns):
            pattern = patterns[tag]
            if pattern.pattern_type == "Plain":
                self.pattern.addItem(f"{tag} - {pattern.name}", int(tag))
        if edge_load is not None:
            index = self.pattern.findData(edge_load.pattern_tag)
            if index >= 0:
                self.pattern.setCurrentIndex(index)
        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Plain pattern:", self.pattern)

        values = (
            edge_load.values_per_length
            if edge_load is not None
            else (0.0,) * 6
        )
        self.spins: list[QDoubleSpinBox] = []
        for index, (label, value) in enumerate(
            zip(self.COMPONENTS, values)
        ):
            spin = _spin(value)
            unit = (
                self.unit_system.line_load_label
                if index < 3
                else self.unit_system.force
            )
            form.addRow(f"{label} [{unit}]:", spin)
            self.spins.append(spin)
        root.addLayout(form)

        note = QLabel(
            "qX–qZ are force per unit edge length. "
            "mX–mZ are moment per unit edge length; in a consistent "
            "force-length unit system their displayed unit reduces to force."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def data(self) -> SurfaceEdgeLoadData:
        if self.pattern.currentData() is None:
            raise ValueError("Create a Plain load pattern first.")
        return SurfaceEdgeLoadData(
            tag=self.tag.value(),
            name=(
                self.name.text().strip()
                or f"Surface Edge Load {self.tag.value()}"
            ),
            surface_tag=self.surface_tag,
            edge_index=self.edge_index,
            pattern_tag=int(self.pattern.currentData()),
            values_per_length=tuple(
                spin.value() for spin in self.spins
            ),
            generated_nodal_load_tags=[],
        )

    def _accept(self) -> None:
        try:
            self.data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Managed Surface Edge Line Load",
                str(exc),
            )
            return
        self.accept()
