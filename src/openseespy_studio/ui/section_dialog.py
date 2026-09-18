from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..project import (
    FiberData,
    MATERIAL_PARAMETER_ORDER,
    SECTION_DEFAULTS,
    SECTION_PARAMETER_ORDER,
    MaterialData,
    SectionData,
)


def _float_spin(value: float = 0.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(10)
    spin.setRange(-1.0e20, 1.0e20)
    spin.setValue(float(value))
    return spin


class SectionDialog(QDialog):
    def __init__(
        self,
        materials: dict[int, MaterialData],
        section: SectionData | None = None,
        *,
        next_tag: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Section Editor")
        self.setModal(True)
        self.resize(560, 500)
        self.materials = materials
        self._initial_section = section

        root = QVBoxLayout(self)

        header = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(section.tag if section else next_tag)

        self.name = QLineEdit()
        self.name.setText(section.name if section else f"Section {next_tag}")

        self.section_type = QComboBox()
        self.section_type.addItems(["Elastic", "Fiber"])
        if section:
            self.section_type.setCurrentText(section.section_type)

        header.addRow("Tag:", self.tag)
        header.addRow("Name:", self.name)
        header.addRow("Type:", self.section_type)
        root.addLayout(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.elastic_page = QWidget()
        elastic_form = QFormLayout(self.elastic_page)

        self.elastic_material = QComboBox()
        self.elastic_material.addItem("Manual section properties", None)
        for tag in sorted(self.materials):
            material = self.materials[tag]
            self.elastic_material.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                tag,
            )
        if (
            section is not None
            and section.section_type == "Elastic"
            and section.material_tag is not None
        ):
            index = self.elastic_material.findData(section.material_tag)
            if index >= 0:
                self.elastic_material.setCurrentIndex(index)
        elastic_form.addRow("Material:", self.elastic_material)

        self.elastic_spins: dict[str, QDoubleSpinBox] = {}
        for key in SECTION_PARAMETER_ORDER["Elastic"]:
            initial = (
                section.parameters.get(key, SECTION_DEFAULTS["Elastic"][key])
                if section and section.section_type == "Elastic"
                else SECTION_DEFAULTS["Elastic"][key]
            )
            spin = _float_spin(initial)
            elastic_form.addRow(f"{key}:", spin)
            self.elastic_spins[key] = spin

        self.elastic_material.currentIndexChanged.connect(
            self._update_elastic_material_link
        )
        self._update_elastic_material_link()
        self.stack.addWidget(self.elastic_page)

        self.fiber_page = QWidget()
        fiber_root = QVBoxLayout(self.fiber_page)

        gj_form = QFormLayout()
        gj_value = (
            section.parameters.get("GJ", SECTION_DEFAULTS["Fiber"]["GJ"])
            if section and section.section_type == "Fiber"
            else SECTION_DEFAULTS["Fiber"]["GJ"]
        )
        self.gj = _float_spin(gj_value)
        gj_form.addRow("GJ:", self.gj)
        fiber_root.addLayout(gj_form)

        hint = QLabel(
            "Explicit fiber definition: local y, z, area and uniaxial material tag."
        )
        hint.setWordWrap(True)
        fiber_root.addWidget(hint)

        self.fiber_table = QTableWidget(0, 4)
        self.fiber_table.setHorizontalHeaderLabels(["y", "z", "Area", "Material"])
        self.fiber_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        fiber_root.addWidget(self.fiber_table, 1)

        fiber_buttons = QHBoxLayout()
        add_fiber = QPushButton("Add Fiber")
        remove_fiber = QPushButton("Remove Selected")
        add_fiber.clicked.connect(self._add_fiber_row)
        remove_fiber.clicked.connect(self._remove_selected_fibers)
        fiber_buttons.addWidget(add_fiber)
        fiber_buttons.addWidget(remove_fiber)
        fiber_buttons.addStretch(1)
        fiber_root.addLayout(fiber_buttons)

        self.stack.addWidget(self.fiber_page)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.section_type.currentTextChanged.connect(self._sync_page)
        self._sync_page(self.section_type.currentText())

        if section and section.section_type == "Fiber":
            for fiber in section.fibers:
                self._add_fiber_row(fiber)

    def _update_elastic_material_link(self) -> None:
        material_tag = self.elastic_material.currentData()
        linked = material_tag is not None

        self.elastic_spins["E"].setEnabled(not linked)
        self.elastic_spins["G"].setEnabled(not linked)

        if not linked:
            return

        material = self.materials.get(int(material_tag))
        if material is None:
            return

        self.elastic_spins["E"].setValue(material.elastic_modulus())
        self.elastic_spins["G"].setValue(material.shear_modulus())

    def _sync_page(self, section_type: str) -> None:
        self.stack.setCurrentIndex(0 if section_type == "Elastic" else 1)

    def _material_combo(self, selected_tag: int | None = None) -> QComboBox:
        combo = QComboBox()
        for tag in sorted(self.materials):
            material = self.materials[tag]
            combo.addItem(f"{tag} - {material.name}", tag)
        if selected_tag is not None:
            index = combo.findData(selected_tag)
            if index >= 0:
                combo.setCurrentIndex(index)
        return combo

    def _add_fiber_row(self, fiber: FiberData | None = None) -> None:
        row = self.fiber_table.rowCount()
        self.fiber_table.insertRow(row)
        values = (
            (fiber.y, fiber.z, fiber.area)
            if fiber is not None
            else (0.0, 0.0, 1.0e-4)
        )
        for column, value in enumerate(values):
            self.fiber_table.setItem(
                row,
                column,
                QTableWidgetItem(f"{float(value):.10g}"),
            )
        selected_tag = fiber.material_tag if fiber is not None else None
        self.fiber_table.setCellWidget(
            row,
            3,
            self._material_combo(selected_tag),
        )

    def _remove_selected_fibers(self) -> None:
        rows = sorted(
            {index.row() for index in self.fiber_table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self.fiber_table.removeRow(row)

    def _fiber_data(self) -> list[FiberData]:
        fibers: list[FiberData] = []
        for row in range(self.fiber_table.rowCount()):
            combo = self.fiber_table.cellWidget(row, 3)
            if combo is None or combo.currentData() is None:
                raise ValueError(
                    f"Fiber row {row + 1} has no material assigned."
                )
            fibers.append(
                FiberData(
                    y=float(self.fiber_table.item(row, 0).text()),
                    z=float(self.fiber_table.item(row, 1).text()),
                    area=float(self.fiber_table.item(row, 2).text()),
                    material_tag=int(combo.currentData()),
                )
            )
        return fibers

    def _validate_and_accept(self) -> None:
        try:
            section = self.section_data()
            if section.section_type == "Fiber" and not self.materials:
                raise ValueError(
                    "Create at least one material before defining a Fiber section."
                )
        except (ValueError, AttributeError) as exc:
            QMessageBox.warning(self, "Section Editor", str(exc))
            return
        self.accept()

    def section_data(self) -> SectionData:
        section_type = self.section_type.currentText()
        if section_type == "Elastic":
            parameters = {
                key: self.elastic_spins[key].value()
                for key in SECTION_PARAMETER_ORDER["Elastic"]
            }
            fibers: list[FiberData] = []
            material_tag = self.elastic_material.currentData()
        else:
            parameters = {"GJ": self.gj.value()}
            fibers = self._fiber_data()
            material_tag = None

        return SectionData(
            tag=self.tag.value(),
            name=self.name.text().strip() or f"Section {self.tag.value()}",
            section_type=section_type,
            parameters=parameters,
            fibers=fibers,
            material_tag=material_tag,
        )
