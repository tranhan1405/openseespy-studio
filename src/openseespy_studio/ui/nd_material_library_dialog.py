from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..nd_material_library import (
    NDMaterialLibraryRecord,
    load_verified_nd_material_library,
    nd_material_from_library_record,
)
from ..project import NDMaterialData, nd_material_parameter_kind
from ..units import UnitSystem


class NDMaterialLibraryDialog(QDialog):
    """Verified OpenSees nD material model/template browser."""

    def __init__(
        self,
        *,
        next_tag: int,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("SARE nD Material Library · Verified Models")
        self.resize(1080, 720)
        self._next_tag = int(next_tag)
        self._units = UnitSystem.from_mapping(units)
        self._records = load_verified_nd_material_library()
        self._record_by_id = {record.id: record for record in self._records}
        self._selected_record: NDMaterialLibraryRecord | None = None

        root = QVBoxLayout(self)

        title = QLabel(
            "Engineering Data · Verified nD Material Library · "
            f"{len(self._records)} model template(s)"
        )
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        policy = QLabel(
            "Model syntax and compatibility are verified against official "
            "OpenSees documentation. Numerical values marked Starter Template "
            "are initialization values and must be replaced/calibrated for "
            "project-specific research or design."
        )
        policy.setWordWrap(True)
        policy.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(policy)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search family, model, behavior, compatibility..."
        )
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Family / OpenSees nDMaterial")
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(
            lambda _item, _column: self._accept_selected()
        )
        splitter.addWidget(self.tree)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.heading = QLabel("Select an nD material model")
        self.heading.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.heading.setWordWrap(True)
        right_layout.addWidget(self.heading)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        right_layout.addWidget(self.summary)

        self.compatibility = QLabel()
        self.compatibility.setWordWrap(True)
        self.compatibility.setStyleSheet(
            "padding: 7px; background: #f4f8fc; color: #31485f;"
        )
        right_layout.addWidget(self.compatibility)

        self.parameter_table = QTableWidget(0, 4)
        self.parameter_table.setHorizontalHeaderLabels([
            "Parameter",
            "Value",
            "Unit",
            "Status",
        ])
        self.parameter_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.parameter_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        header = self.parameter_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.parameter_table, 1)

        self.scope = QLabel()
        self.scope.setWordWrap(True)
        self.scope.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        right_layout.addWidget(self.scope)

        source_row = QHBoxLayout()
        self.source = QLabel()
        self.source.setWordWrap(True)
        self.source.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        source_row.addWidget(self.source, 1)
        self.open_source = QPushButton("Open Official Source")
        self.open_source.clicked.connect(self._open_source)
        source_row.addWidget(self.open_source)
        right_layout.addLayout(source_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([300, 780])

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.add_button = buttons.addButton(
            "Insert into Project",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.add_button.setEnabled(False)
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._populate_tree()
        self._select_first_record()

    def _display_parameter(
        self,
        record: NDMaterialLibraryRecord,
        key: str,
        value: float,
    ) -> tuple[str, str]:
        kind = nd_material_parameter_kind(record.model, key)
        if kind == "stress":
            return (
                f"{self._units.engineering_stress_from_pa(value):g}",
                self._units.engineering_stress_label,
            )
        if kind == "density":
            return (
                f"{self._units.engineering_density_from_kg_per_m3(value):g}",
                self._units.engineering_density_label,
            )
        return f"{value:g}", "-"

    def _populate_tree(self) -> None:
        self.tree.clear()
        families: dict[str, QTreeWidgetItem] = {}
        for record in self._records:
            family = families.get(record.family)
            if family is None:
                family = QTreeWidgetItem([record.family])
                family.setExpanded(True)
                self.tree.addTopLevelItem(family)
                families[record.family] = family
            item = QTreeWidgetItem([
                f"{record.model} · {record.preset_name}"
            ])
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                record.id,
            )
            item.setToolTip(
                0,
                ", ".join(record.compatibility),
            )
            family.addChild(item)

    def _select_first_record(self) -> None:
        if not self._records:
            return
        root = self.tree.invisibleRootItem()
        for family_index in range(root.childCount()):
            family = root.child(family_index)
            if family.childCount():
                self.tree.setCurrentItem(family.child(0))
                return

    def _apply_filter(self, text: str) -> None:
        query = str(text).strip().lower()
        root = self.tree.invisibleRootItem()
        for family_index in range(root.childCount()):
            family = root.child(family_index)
            family_visible = False
            for record_index in range(family.childCount()):
                item = family.child(record_index)
                record = self._record_by_id.get(
                    str(item.data(0, Qt.ItemDataRole.UserRole) or "")
                )
                haystack = ""
                if record is not None:
                    haystack = " ".join([
                        record.family,
                        record.material,
                        record.model,
                        record.preset_name,
                        *record.behavior,
                        *record.compatibility,
                        *record.applicability,
                    ]).lower()
                visible = not query or query in haystack
                item.setHidden(not visible)
                family_visible = family_visible or visible
            family.setHidden(not family_visible)

    def _selection_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        record_id = (
            str(current.data(0, Qt.ItemDataRole.UserRole))
            if current is not None
            and current.data(0, Qt.ItemDataRole.UserRole)
            else ""
        )
        record = self._record_by_id.get(record_id)
        self._selected_record = record
        self.add_button.setEnabled(bool(record and record.is_verified))
        self.open_source.setEnabled(bool(record and record.source_url))

        self.parameter_table.setRowCount(0)
        if record is None:
            self.heading.setText("Select an nD material model")
            self.summary.clear()
            self.compatibility.clear()
            self.scope.clear()
            self.source.clear()
            return

        self.heading.setText(
            f"{record.material} · {record.model}"
        )
        parameter_status = (
            "Starter Template"
            if record.is_starter_template
            else "Verified parameter set"
        )
        self.summary.setText(
            "Behavior: "
            + ", ".join(record.behavior)
            + f" · Parameter status: {parameter_status}"
        )
        self.compatibility.setText(
            "Compatible formulations: "
            + ", ".join(record.compatibility)
        )

        for key in record.verified_parameters:
            row = self.parameter_table.rowCount()
            self.parameter_table.insertRow(row)
            value, unit = self._display_parameter(
                record,
                key,
                record.parameters_si[key],
            )
            for column, text in enumerate((
                key,
                value,
                unit,
                "Starter · model parameter verified",
            )):
                self.parameter_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(text),
                )

        applicability = "\n".join(
            f"• {item}" for item in record.applicability
        )
        limitations = "\n".join(
            f"• {item}" for item in record.limitations
        )
        self.scope.setText(
            "Applicability\n"
            + (applicability or "• -")
            + "\n\nLimitations\n"
            + (limitations or "• -")
        )

        reference = record.primary_reference
        evidence = record.parameter_evidence
        self.source.setText(
            "Official source: "
            + str(reference.get("title", ""))
            + "\nEvidence: "
            + str(evidence.get("location", ""))
        )

    def _open_source(self) -> None:
        record = self._selected_record
        if record is None or not record.source_url:
            return
        QDesktopServices.openUrl(QUrl(record.source_url))

    def _accept_selected(self) -> None:
        if self._selected_record is None:
            return
        if not self._selected_record.is_verified:
            return
        self.accept()

    def material_data(self) -> NDMaterialData:
        if self._selected_record is None:
            raise ValueError("Select an nD material library record.")
        return nd_material_from_library_record(
            self._selected_record,
            tag=self._next_tag,
        )
