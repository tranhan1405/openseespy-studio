from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..mass_source import evaluate_mass_source
from ..project import MassSourceData, ProjectDatabase
from ..units import UnitSystem


class MassSourceDialog(QDialog):
    """Define seismic mass from structural self mass and gravity load patterns."""

    def __init__(
        self,
        project: ProjectDatabase,
        source: MassSourceData | None = None,
        *,
        next_tag: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Mass Source")
        self.setModal(True)
        self.resize(720, 610)

        root = QVBoxLayout(self)

        general_group = QGroupBox("Mass source")
        general = QFormLayout(general_group)
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(source.tag if source else int(next_tag))
        self.name = QLineEdit(
            source.name if source else f"Mass Source {next_tag}"
        )
        self.include_self = QCheckBox(
            "Include structural self mass from section/material density"
        )
        self.include_self.setChecked(
            source.include_self_mass if source else True
        )
        self.gravity_axis = QComboBox()
        for axis, label in ((1, "Global X"), (2, "Global Y"), (3, "Global Z")):
            self.gravity_axis.addItem(label, axis)
        gravity_axis = source.gravity_axis if source else 3
        index = self.gravity_axis.findData(gravity_axis)
        if index >= 0:
            self.gravity_axis.setCurrentIndex(index)
        general.addRow("Tag:", self.tag)
        general.addRow("Name:", self.name)
        general.addRow(self.include_self)
        general.addRow("Gravity load axis:", self.gravity_axis)
        root.addWidget(general_group)

        direction_group = QGroupBox("Mass directions")
        direction_layout = QHBoxLayout(direction_group)
        self.direction_checks: dict[int, QCheckBox] = {}
        available = range(1, min(3, int(project.model.ndf)) + 1)
        selected = set(source.directions if source else ())
        if not selected:
            selected = {1} if int(project.model.ndm) <= 2 else {1, 2}
        for dof in available:
            label = ("UX", "UY", "UZ")[dof - 1]
            check = QCheckBox(label)
            check.setChecked(dof in selected)
            self.direction_checks[dof] = check
            direction_layout.addWidget(check)
        direction_layout.addStretch(1)
        root.addWidget(direction_group)

        loads_group = QGroupBox("Load patterns → seismic mass")
        loads_layout = QVBoxLayout(loads_group)
        note = QLabel(
            "Select only gravity/permanent/variable-load patterns that "
            "represent physical weight. Factor is the fraction included in "
            "seismic mass (for example permanent load 1.0; live-load factor "
            "must be chosen from the applicable design code)."
        )
        note.setWordWrap(True)
        loads_layout.addWidget(note)

        self.pattern_table = QTableWidget(0, 4)
        self.pattern_table.setHorizontalHeaderLabels(
            ["Use", "Tag", "Plain load pattern", "Mass factor"]
        )
        self.pattern_table.verticalHeader().setVisible(False)
        self.pattern_table.setAlternatingRowColors(True)
        self.pattern_table.horizontalHeader().setStretchLastSection(True)
        self._populate_patterns(source)
        loads_layout.addWidget(self.pattern_table, 1)
        root.addWidget(loads_group, 1)

        warning = QLabel(
            "Double-count protection: if structural self mass is enabled, "
            "SelfWeight beam loads are not converted again. Elements with an "
            "explicit OpenSees mass/length are also not converted to nodal "
            "self mass."
        )
        warning.setWordWrap(True)
        warning.setObjectName("Muted")
        root.addWidget(warning)

        preview_row = QHBoxLayout()
        preview = QPushButton("Preview Mass")
        preview.clicked.connect(self._preview)
        preview_row.addWidget(preview)
        self.preview_label = QLabel("Preview not calculated.")
        self.preview_label.setWordWrap(True)
        preview_row.addWidget(self.preview_label, 1)
        root.addLayout(preview_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Save Mass Source")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _eligible_patterns(self):
        result = []
        for tag in sorted(self.project.load_patterns):
            pattern = self.project.load_patterns[tag]
            if pattern.pattern_type != "Plain":
                continue
            series = self.project.time_series.get(pattern.time_series_tag)
            if series is None or series.series_type not in {"Linear", "Constant"}:
                continue
            result.append(pattern)
        return result

    def _populate_patterns(
        self,
        source: MassSourceData | None,
    ) -> None:
        factors = dict(source.load_factors) if source else {}
        patterns = self._eligible_patterns()
        self.pattern_table.setRowCount(len(patterns))
        for row, pattern in enumerate(patterns):
            use_item = QTableWidgetItem()
            use_item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
            )
            use_item.setCheckState(
                Qt.Checked if pattern.tag in factors else Qt.Unchecked
            )
            use_item.setData(Qt.UserRole, pattern.tag)
            self.pattern_table.setItem(row, 0, use_item)

            tag_item = QTableWidgetItem(str(pattern.tag))
            tag_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.pattern_table.setItem(row, 1, tag_item)

            name_item = QTableWidgetItem(pattern.name)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.pattern_table.setItem(row, 2, name_item)

            factor = QDoubleSpinBox()
            factor.setDecimals(6)
            factor.setRange(0.0, 1000.0)
            factor.setValue(float(factors.get(pattern.tag, 1.0)))
            factor.setKeyboardTracking(False)
            self.pattern_table.setCellWidget(row, 3, factor)

        self.pattern_table.resizeColumnsToContents()

    def data(self) -> MassSourceData:
        directions = tuple(
            dof
            for dof, check in self.direction_checks.items()
            if check.isChecked()
        )
        factors: dict[int, float] = {}
        for row in range(self.pattern_table.rowCount()):
            item = self.pattern_table.item(row, 0)
            if item is None or item.checkState() != Qt.Checked:
                continue
            tag = int(item.data(Qt.UserRole))
            spin = self.pattern_table.cellWidget(row, 3)
            factor = float(spin.value())
            if factor <= 0.0:
                raise ValueError(
                    f"Selected load pattern {tag} needs a positive mass factor."
                )
            factors[tag] = factor

        return MassSourceData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Mass Source {self.tag.value()}",
            include_self_mass=self.include_self.isChecked(),
            load_factors=factors,
            gravity_axis=int(self.gravity_axis.currentData() or 3),
            directions=directions,
        )

    def _preview(self) -> None:
        try:
            source = self.data()
            summary = evaluate_mass_source(self.project, source)
        except ValueError as exc:
            QMessageBox.warning(self, "Mass Source Preview", str(exc))
            return
        unit = UnitSystem.from_mapping(self.project.units).mass_label
        message = (
            f"Total generated mass = {summary.total_mass:.6g} {unit} · "
            f"self = {summary.self_mass:.6g} {unit} · "
            f"loads = {summary.load_mass:.6g} {unit} · "
            f"active nodes = {summary.active_nodes}"
        )
        extras = []
        if summary.skipped_element_mass_tags:
            extras.append(
                "explicit element mass/length kept on element(s): "
                + ", ".join(map(str, summary.skipped_element_mass_tags))
            )
        if summary.skipped_self_weight_load_tags:
            extras.append(
                "SelfWeight load(s) skipped to avoid double counting: "
                + ", ".join(map(str, summary.skipped_self_weight_load_tags))
            )
        if extras:
            message += "\n" + "\n".join(extras)
        self.preview_label.setText(message)

    def _accept(self) -> None:
        try:
            source = self.data()
            summary = evaluate_mass_source(self.project, source)
        except ValueError as exc:
            QMessageBox.warning(self, "Mass Source", str(exc))
            return
        if summary.total_mass <= 1.0e-15:
            answer = QMessageBox.question(
                self,
                "Mass Source",
                (
                    "This source currently generates zero nodal mass. "
                    "Save it anyway?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.accept()
