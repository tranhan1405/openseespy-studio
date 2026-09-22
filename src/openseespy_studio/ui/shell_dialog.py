from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
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

from ..model import SHELL_ELEMENT_TYPES
from ..project import SECTION_DEFAULTS, SHELL_SECTION_TYPES, SectionData
from ..units import UnitSystem


def _float_spin(
    value: float,
    *,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 8,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setValue(float(value))
    return spin


class ShellSectionDialog(QDialog):
    """Elastic membrane-plate section for shell elements."""

    def __init__(
        self,
        *,
        next_tag: int | None = None,
        section: SectionData | None = None,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Shell Section" if section is not None
            else "New Shell Section"
        )
        self.setModal(True)
        self.setMinimumWidth(470)
        self.unit_system = UnitSystem.from_mapping(units)

        if section is not None and section.section_type not in SHELL_SECTION_TYPES:
            raise ValueError(
                f"Section {section.tag} is not a shell-compatible section."
            )

        defaults = SECTION_DEFAULTS["ElasticMembranePlate"]
        p = section.parameters if section is not None else defaults

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(
            section.tag if section is not None else int(next_tag or 1)
        )
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            section.name if section is not None
            else f"Shell Section {int(next_tag or 1)}"
        )
        form.addRow("Name:", self.name)

        formulation = QLabel("ElasticMembranePlateSection")
        formulation.setStyleSheet("font-weight: 600;")
        form.addRow("OpenSees section:", formulation)

        self.elastic_modulus = _float_spin(
            self.unit_system.engineering_stress_from_pa(
                float(p.get("E", defaults["E"]))
            ),
            low=1.0e-12,
        )
        self.elastic_modulus.setSingleStep(100.0)
        form.addRow(
            f"E [{self.unit_system.engineering_stress_label}]:",
            self.elastic_modulus,
        )

        self.poisson = _float_spin(
            float(p.get("nu", defaults["nu"])),
            low=-0.999999,
            high=0.499999,
            decimals=6,
        )
        form.addRow("Poisson ratio ν:", self.poisson)

        thickness_value = (
            float(section.parameters["h"])
            if section is not None
            else self.unit_system.length_from_m(0.20)
        )
        self.thickness = _float_spin(
            thickness_value,
            low=1.0e-12,
        )
        form.addRow(
            f"Thickness h [{self.unit_system.length}]:",
            self.thickness,
        )

        self.density = _float_spin(
            float(p.get("rho", defaults["rho"])),
            low=0.0,
        )
        form.addRow("Mass density ρ [model mass/L³]:", self.density)

        self.ep_modifier = _float_spin(
            float(p.get("EpModifier", defaults["EpModifier"])),
            low=1.0e-12,
            decimals=6,
        )
        form.addRow("Out-of-plane E modifier:", self.ep_modifier)

        note = QLabel(
            "Initial shell support uses OpenSees ElasticMembranePlateSection. "
            "It is compatible with ASDShellQ4, ShellMITC4, ShellDKGQ and "
            "ShellNLDKGQ. PlateFiber/LayeredShell will be added as nonlinear "
            "shell-section families without introducing solid elements."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def section_data(self) -> SectionData:
        return SectionData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Shell Section {self.tag.value()}",
            section_type="ElasticMembranePlate",
            parameters={
                "E": self.unit_system.engineering_stress_to_pa(
                    self.elastic_modulus.value()
                ),
                "nu": self.poisson.value(),
                "h": self.thickness.value(),
                "rho": self.density.value(),
                "EpModifier": self.ep_modifier.value(),
            },
        )

    def _accept(self) -> None:
        try:
            self.section_data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Shell Section", str(exc))
            return
        self.accept()


class ShellElementDialog(QDialog):
    """Create one four-node quadrilateral shell element."""

    FORMULATIONS = (
        "ASDShellQ4",
        "ShellMITC4",
        "ShellDKGQ",
        "ShellNLDKGQ",
    )

    def __init__(
        self,
        *,
        tag: int,
        nodes,
        sections,
        initial_nodes=(),
        element=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Shell Element" if element is not None
            else "Create Shell Element"
        )
        self.setModal(True)
        self.setMinimumWidth(500)
        self._nodes = dict(nodes or {})
        self._sections = {
            int(section_tag): section
            for section_tag, section in dict(sections or {}).items()
            if section.section_type in SHELL_SECTION_TYPES
        }

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
                (node_tag for node_tag in fallback if node_tag not in selected),
                None,
            )
            if candidate is None:
                break
            selected.append(candidate)

        self.node_combos: list[QComboBox] = []
        for index, label in enumerate(("Node 1:", "Node 2:", "Node 3:", "Node 4:")):
            combo = QComboBox()
            for node_tag in sorted(self._nodes):
                node = self._nodes[node_tag]
                x, y, z = node.xyz
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
        self.formulation.addItems(list(self.FORMULATIONS))
        if element is not None and element.element_type in SHELL_ELEMENT_TYPES:
            self.formulation.setCurrentText(element.element_type)
        form.addRow("Formulation:", self.formulation)

        self.section = QComboBox()
        for section_tag in sorted(self._sections):
            section = self._sections[section_tag]
            self.section.addItem(
                f"{section_tag} - {section.name} ({section.section_type})",
                int(section_tag),
            )
        if element is not None and element.section_tag is not None:
            wanted = self.section.findData(int(element.section_tag))
            if wanted >= 0:
                self.section.setCurrentIndex(wanted)
        form.addRow("Shell section:", self.section)

        self.corotational = QCheckBox(
            "Corotational kinematics (large displacement/rotation)"
        )
        self.corotational.setChecked(
            bool(getattr(element, "shell_corotational", False))
            if element is not None
            else False
        )
        form.addRow("", self.corotational)

        self.formulation.currentTextChanged.connect(
            self._sync_formulation
        )
        self._sync_formulation()

        note = QLabel(
            "Node ordering must follow the shell boundary consistently "
            "(clockwise or counter-clockwise). Shells require ndm=3, ndf=6. "
            "ASDShellQ4 is the recommended default general-purpose element."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _sync_formulation(self, *_args) -> None:
        self.corotational.setEnabled(
            self.formulation.currentText() == "ASDShellQ4"
        )
        if self.formulation.currentText() != "ASDShellQ4":
            self.corotational.setChecked(False)

    def values(self) -> tuple[int, tuple[int, int, int, int], str, int, bool]:
        node_tags = tuple(
            int(combo.currentData())
            for combo in self.node_combos
            if combo.currentData() is not None
        )
        if len(node_tags) != 4:
            raise ValueError("Shell element requires four node tags.")
        if len(set(node_tags)) != 4:
            raise ValueError("Shell element requires four distinct nodes.")
        section_tag = self.section.currentData()
        if section_tag is None:
            raise ValueError(
                "Shell element requires a shell-compatible Section."
            )
        formulation = self.formulation.currentText()
        if formulation not in SHELL_ELEMENT_TYPES:
            raise ValueError(
                f"Unsupported shell formulation: {formulation}"
            )
        return (
            self.tag.value(),
            node_tags,
            formulation,
            int(section_tag),
            bool(self.corotational.isChecked()),
        )

    def _accept(self) -> None:
        try:
            self.values()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Shell Element", str(exc))
            return
        self.accept()
