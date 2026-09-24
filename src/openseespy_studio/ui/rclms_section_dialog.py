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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..project import NDMaterialData, SectionData, ShellLayerData
from ..units import UnitSystem


class RCLMSSectionDialog(QDialog):
    """Editor for ReinforcedConcreteLayeredMembraneSection / RCLMS."""

    def __init__(
        self,
        *,
        section: SectionData,
        nd_materials: dict[int, NDMaterialData],
        units=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if section.section_type != "RCLMS":
            raise ValueError("RCLMSSectionDialog requires an RCLMS section.")

        self.setWindowTitle("Edit RCLMS RC Membrane Section")
        self.setModal(True)
        self.resize(650, 500)
        self.unit_system = UnitSystem.from_mapping(units)
        self._nd_materials = dict(nd_materials)
        self._layers = [
            ShellLayerData(layer.material_tag, layer.thickness)
            for layer in section.shell_layers
        ]

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(int(section.tag))
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(section.name)
        form.addRow("Name:", self.name)

        self.steel = QComboBox()
        for tag, material in sorted(self._nd_materials.items()):
            if material.material_type != "SmearedSteelDoubleLayer":
                continue
            self.steel.addItem(
                f"{tag} - {material.name}",
                int(tag),
            )
        if section.nd_material_tag is not None:
            index = self.steel.findData(int(section.nd_material_tag))
            if index >= 0:
                self.steel.setCurrentIndex(index)
        form.addRow("Smeared reinforcement:", self.steel)
        root.addLayout(form)

        input_row = QHBoxLayout()
        self.concrete = QComboBox()
        for tag, material in sorted(self._nd_materials.items()):
            if material.material_type != "OrthotropicRAConcrete":
                continue
            self.concrete.addItem(
                f"{tag} - {material.name}",
                int(tag),
            )
        input_row.addWidget(self.concrete, 1)

        self.thickness = QDoubleSpinBox()
        self.thickness.setDecimals(8)
        self.thickness.setRange(1.0e-12, 1.0e20)
        self.thickness.setValue(
            self._layers[0].thickness
            if self._layers
            else self.unit_system.length_from_m(0.10)
        )
        self.thickness.setSuffix(f" {self.unit_system.length}")
        input_row.addWidget(self.thickness)

        add_layer = QPushButton("Add Concrete Layer")
        add_layer.clicked.connect(self._add_layer)
        input_row.addWidget(add_layer)
        root.addLayout(input_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Layer", "OrthotropicRAConcrete", f"Thickness [{self.unit_system.length}]"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        root.addWidget(self.table, 1)

        remove_layer = QPushButton("Remove Selected Layer")
        remove_layer.clicked.connect(self._remove_layer)
        root.addWidget(remove_layer)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(self.summary)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_table()

    def _add_layer(self) -> None:
        tag = self.concrete.currentData()
        if tag is None:
            QMessageBox.warning(
                self,
                "RCLMS",
                "No OrthotropicRAConcrete material is available.",
            )
            return
        self._layers.append(
            ShellLayerData(
                int(tag),
                float(self.thickness.value()),
            )
        )
        self._refresh_table()

    def _remove_layer(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._layers):
            return
        self._layers.pop(row)
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._layers))
        for row, layer in enumerate(self._layers):
            material = self._nd_materials.get(int(layer.material_tag))
            name = (
                f"{layer.material_tag} - {material.name}"
                if material is not None
                else f"{layer.material_tag} (missing)"
            )
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(
                row,
                2,
                QTableWidgetItem(f"{float(layer.thickness):g}"),
            )
        total = sum(float(layer.thickness) for layer in self._layers)
        self.summary.setText(
            f"Concrete layers: {len(self._layers)} · "
            f"total wall thickness = {total:g} {self.unit_system.length}. "
            "The smeared-steel ratios live in the selected "
            "SmearedSteelDoubleLayer nDMaterial."
        )

    def section_data(self) -> SectionData:
        steel_tag = self.steel.currentData()
        if steel_tag is None:
            raise ValueError(
                "RCLMS requires a SmearedSteelDoubleLayer material."
            )
        if not self._layers:
            raise ValueError("RCLMS requires at least one concrete layer.")
        return SectionData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"RCLMS Section {self.tag.value()}",
            section_type="RCLMS",
            nd_material_tag=int(steel_tag),
            shell_layers=[
                ShellLayerData(
                    int(layer.material_tag),
                    float(layer.thickness),
                )
                for layer in self._layers
            ],
        )

    def _accept(self) -> None:
        try:
            self.section_data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "RCLMS", str(exc))
            return
        self.accept()
