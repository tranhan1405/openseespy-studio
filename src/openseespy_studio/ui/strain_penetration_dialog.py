from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..project import MATERIAL_DEFAULTS, MaterialData, SectionData
from ..strain_penetration import (
    StrainPenetrationSectionResult,
    build_bond_sp01_strain_penetration_section,
)
from ..units import UnitSystem
from .material_test_dialog import MaterialTestDialog


PA_PER_MPA = 1.0e6


def _spin(
    value: float,
    *,
    minimum: float = -1.0e20,
    maximum: float = 1.0e20,
    decimals: int = 8,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(minimum, maximum)
    spin.setValue(float(value))
    return spin


class StrainPenetrationDialog(QDialog):
    """Build a Bond_SP01 Fiber section for a zeroLengthSection interface."""

    def __init__(
        self,
        sections: dict[int, SectionData],
        materials: dict[int, MaterialData],
        *,
        next_material_tag: int,
        next_section_tag: int,
        units=None,
        initial_section_tag: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Bond_SP01 Strain Penetration Builder")
        self.setModal(True)
        self.resize(650, 610)

        self.sections = dict(sections)
        self.materials = dict(materials)
        self.next_material_tag = int(next_material_tag)
        self.next_section_tag = int(next_section_tag)
        self.unit_system = UnitSystem.from_mapping(units)

        root = QVBoxLayout(self)

        intro = QLabel(
            "OpenSees strain-penetration workflow: clone the RC Fiber section, "
            "replace longitudinal steel fibers/layers with Bond_SP01, and use "
            "the cloned section in a zeroLengthSection at the member-footing "
            "interface. Concrete fibers are retained from the source section."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(intro)

        source_group = QGroupBox("Source RC Fiber section")
        source_form = QFormLayout(source_group)
        self.source_section = QComboBox()
        for tag in sorted(self.sections):
            section = self.sections[tag]
            if section.section_type == "Fiber":
                self.source_section.addItem(
                    f"{tag} - {section.name}",
                    tag,
                )
        if initial_section_tag is not None:
            index = self.source_section.findData(int(initial_section_tag))
            if index >= 0:
                self.source_section.setCurrentIndex(index)
        source_form.addRow("Section:", self.source_section)
        root.addWidget(source_group)

        defaults = MATERIAL_DEFAULTS["Bond_SP01"]
        bond_group = QGroupBox("Bond_SP01 bar stress-slip law")
        bond_form = QFormLayout(bond_group)

        self.fy = _spin(defaults["Fy"] / PA_PER_MPA, minimum=0.001)
        self.sy = _spin(
            self.unit_system.length_from_m(defaults["Sy"]),
            minimum=1.0e-12,
            decimals=10,
        )
        self.fu = _spin(defaults["Fu"] / PA_PER_MPA, minimum=0.001)
        self.su = _spin(
            self.unit_system.length_from_m(defaults["Su"]),
            minimum=1.0e-12,
            decimals=10,
        )
        self.b = _spin(defaults["b"], minimum=1.0e-8, decimals=8)
        self.r = _spin(
            defaults["R"],
            minimum=1.0e-8,
            maximum=1.0,
            decimals=8,
        )

        bond_form.addRow("Fy [MPa]:", self.fy)
        bond_form.addRow(
            f"Yield slip Sy [{self.unit_system.length}]:",
            self.sy,
        )
        bond_form.addRow("Fu [MPa]:", self.fu)
        bond_form.addRow(
            f"Ultimate slip Su [{self.unit_system.length}]:",
            self.su,
        )
        bond_form.addRow("Hardening ratio b:", self.b)
        bond_form.addRow("Pinching factor R:", self.r)
        root.addWidget(bond_group)

        concrete_note = QLabel(
            "Concrete fibers are intentionally retained from the source Fiber "
            "section. The original Bond_SP01 guidance notes that zeroLengthSection "
            "concrete can experience very large interface deformations; review "
            "and calibrate the concrete branch for your specimen instead of "
            "treating this automatic clone as a universal concrete model."
        )
        concrete_note.setWordWrap(True)
        concrete_note.setStyleSheet(
            "padding: 8px; background: #fff7e0; color: #7a5600;"
        )
        root.addWidget(concrete_note)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            "padding: 8px; background: #f5f7f9; color: #526578;"
        )
        root.addWidget(self.summary)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.test_button = buttons.addButton(
            "Test Bond_SP01...",
            QDialogButtonBox.ActionRole,
        )
        self.test_button.clicked.connect(self._test_material)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.source_section.currentIndexChanged.connect(self._update_summary)
        for widget in (self.fy, self.sy, self.fu, self.su, self.b, self.r):
            widget.valueChanged.connect(self._update_summary)
        self._update_summary()

    def bond_material(self) -> MaterialData:
        return MaterialData(
            tag=self.next_material_tag,
            name="Bond_SP01 · strain penetration",
            material_type="Bond_SP01",
            parameters={
                "Fy": self.fy.value() * PA_PER_MPA,
                "Sy": self.unit_system.length_to_m_value(self.sy.value()),
                "Fu": self.fu.value() * PA_PER_MPA,
                "Su": self.unit_system.length_to_m_value(self.su.value()),
                "b": self.b.value(),
                "R": self.r.value(),
            },
            poisson_ratio=0.3,
            density=0.0,
        )

    def build_result(self) -> StrainPenetrationSectionResult:
        source_tag = self.source_section.currentData()
        if source_tag is None:
            raise ValueError("Select a Fiber section.")
        material = self.bond_material()
        materials = dict(self.materials)
        materials[material.tag] = material
        return build_bond_sp01_strain_penetration_section(
            self.sections[int(source_tag)],
            materials,
            bond_material_tag=material.tag,
            section_tag=self.next_section_tag,
        )

    def result_material_and_section(
        self,
    ) -> tuple[MaterialData, SectionData]:
        result = self.build_result()
        return self.bond_material(), result.section

    def _update_summary(self, *args) -> None:
        try:
            result = self.build_result()
            replaced = ", ".join(
                str(tag) for tag in result.replaced_material_tags
            )
            self.summary.setText(
                f"New material tag: {self.next_material_tag} · Bond_SP01\n"
                f"New Fiber section tag: {self.next_section_tag}\n"
                f"Replaced steel/rebar material tag(s): {replaced}\n"
                "Output is intended for a zeroLengthSection interface, not "
                "for the distributed beam-column section."
            )
            self.summary.setStyleSheet(
                "padding: 8px; background: #eaf6ee; color: #276738;"
            )
        except ValueError as exc:
            self.summary.setText(str(exc))
            self.summary.setStyleSheet(
                "padding: 8px; background: #fff0f0; color: #8a2f2f;"
            )

    def _test_material(self) -> None:
        try:
            material = self.bond_material()
        except ValueError as exc:
            QMessageBox.warning(self, "Bond_SP01", str(exc))
            return
        materials = dict(self.materials)
        materials[material.tag] = material
        dialog = MaterialTestDialog(
            material,
            units=self.unit_system.as_mapping(),
            materials=materials,
            parent=self,
        )
        dialog.exec()

    def _validate_and_accept(self) -> None:
        try:
            self.build_result()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Bond_SP01 Strain Penetration",
                str(exc),
            )
            return
        self.accept()
