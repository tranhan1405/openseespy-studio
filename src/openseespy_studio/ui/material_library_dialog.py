from __future__ import annotations

from typing import Any

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

from ..material_library import (
    MaterialLibraryRecord,
    load_verified_material_library,
    material_from_library_record,
)
from ..project import MATERIAL_PARAMETER_KINDS, MaterialData
from ..units import UnitSystem
from .material_dialog import MaterialEnvelopePreview


class MaterialLibraryDialog(QDialog):
    """Reference-backed engineering material library.

    Official entries are deliberately conservative: only records that pass the
    loader's provenance checks are displayed and can be added to a project.
    """

    def __init__(
        self,
        *,
        next_tag: int,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("SARE Material Library · Verified Sources")
        self.resize(1120, 760)
        self._next_tag = int(next_tag)
        self._units = UnitSystem.from_mapping(units)
        self._records = load_verified_material_library()
        self._record_by_id = {record.id: record for record in self._records}
        self._selected_record: MaterialLibraryRecord | None = None

        root = QVBoxLayout(self)

        title = QLabel("Engineering Data · Verified Material Library")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        policy = QLabel(
            "Official Library policy: no constitutive preset is included "
            "without a traceable source and an identified parameter location. "
            "Journal sources must include a DOI."
        )
        policy.setWordWrap(True)
        policy.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(policy)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search material, grade, standard, model, author or DOI..."
        )
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel(
            "Material family / grade / OpenSees model / parameter set"
        )
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tree.currentItemChanged.connect(self._selection_changed)
        splitter.addWidget(self.tree)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.heading = QLabel("Select a verified parameter set")
        self.heading.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.heading.setWordWrap(True)
        right_layout.addWidget(self.heading)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        right_layout.addWidget(self.summary)

        self.parameter_table = QTableWidget(0, 4)
        self.parameter_table.setHorizontalHeaderLabels([
            "Parameter",
            "Value",
            "Unit",
            "Evidence",
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
        right_layout.addWidget(self.parameter_table, 2)

        lower = QSplitter(Qt.Orientation.Horizontal)
        right_layout.addWidget(lower, 2)

        source_host = QWidget()
        source_layout = QVBoxLayout(source_host)
        source_layout.setContentsMargins(0, 0, 6, 0)
        source_title = QLabel("Reference / evidence")
        source_title.setStyleSheet("font-weight: 700;")
        source_layout.addWidget(source_title)

        self.reference = QLabel()
        self.reference.setWordWrap(True)
        self.reference.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.reference.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        source_layout.addWidget(self.reference, 1)

        source_buttons = QHBoxLayout()
        self.open_doi = QPushButton("Open DOI")
        self.open_doi.clicked.connect(self._open_doi)
        self.open_evidence = QPushButton("Open evidence")
        self.open_evidence.clicked.connect(self._open_evidence)
        source_buttons.addWidget(self.open_doi)
        source_buttons.addWidget(self.open_evidence)
        source_buttons.addStretch(1)
        source_layout.addLayout(source_buttons)
        lower.addWidget(source_host)

        preview_host = QWidget()
        preview_layout = QVBoxLayout(preview_host)
        preview_layout.setContentsMargins(6, 0, 0, 0)
        preview_title = QLabel("Constitutive response guide")
        preview_title.setStyleSheet("font-weight: 700;")
        preview_layout.addWidget(preview_title)
        self.preview = MaterialEnvelopePreview()
        preview_layout.addWidget(self.preview, 1)
        lower.addWidget(preview_host)
        lower.setStretchFactor(0, 3)
        lower.setStretchFactor(1, 2)

        self.scope = QLabel()
        self.scope.setWordWrap(True)
        self.scope.setStyleSheet(
            "padding: 7px; background: #f7f7f7; color: #526578;"
        )
        right_layout.addWidget(self.scope)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([310, 810])

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.add_button = buttons.addButton(
            "Add to Project",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.add_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._populate_tree()
        self._select_first_record()

    def _populate_tree(self) -> None:
        self.tree.clear()
        families: dict[str, QTreeWidgetItem] = {}
        grades: dict[tuple[str, str], QTreeWidgetItem] = {}
        models: dict[tuple[str, str, str], QTreeWidgetItem] = {}
        for record in self._records:
            family_item = families.get(record.family)
            if family_item is None:
                family_item = QTreeWidgetItem([record.family])
                family_item.setExpanded(True)
                self.tree.addTopLevelItem(family_item)
                families[record.family] = family_item

            grade_key = (record.family, record.grade)
            grade_item = grades.get(grade_key)
            if grade_item is None:
                grade_item = QTreeWidgetItem([
                    f"{record.grade} · {record.standard}"
                ])
                grade_item.setExpanded(True)
                family_item.addChild(grade_item)
                grades[grade_key] = grade_item

            model_key = (record.family, record.grade, record.model)
            model_item = models.get(model_key)
            if model_item is None:
                model_item = QTreeWidgetItem([record.model])
                model_item.setExpanded(True)
                grade_item.addChild(model_item)
                models[model_key] = model_item

            item = QTreeWidgetItem([record.preset_name])
            item.setData(0, Qt.ItemDataRole.UserRole, record.id)
            item.setToolTip(
                0,
                f"{record.model} · verified source · DOI {record.doi}",
            )
            model_item.addChild(item)

    def _select_first_record(self) -> None:
        if not self._records:
            return
        target = self._records[0].id
        iterator = self.tree.invisibleRootItem()
        stack = [
            iterator.child(index)
            for index in range(iterator.childCount())
        ]
        while stack:
            item = stack.pop(0)
            if item.data(0, Qt.ItemDataRole.UserRole) == target:
                self.tree.setCurrentItem(item)
                return
            stack.extend(
                item.child(index)
                for index in range(item.childCount())
            )

    def _apply_filter(self, text: str) -> None:
        query = str(text).strip().lower()
        root = self.tree.invisibleRootItem()
        for family_index in range(root.childCount()):
            family = root.child(family_index)
            family_visible = False
            for grade_index in range(family.childCount()):
                grade = family.child(grade_index)
                grade_visible = False
                for model_index in range(grade.childCount()):
                    model = grade.child(model_index)
                    model_visible = False
                    for record_index in range(model.childCount()):
                        item = model.child(record_index)
                        record = self._record_by_id.get(
                            str(
                                item.data(
                                    0,
                                    Qt.ItemDataRole.UserRole,
                                )
                            )
                        )
                        haystack = ""
                        if record is not None:
                            haystack = " ".join([
                                record.family,
                                record.material,
                                record.grade,
                                record.standard,
                                record.model,
                                record.preset_name,
                                str(
                                    record.primary_reference.get(
                                        "authors",
                                        "",
                                    )
                                ),
                                record.doi,
                            ]).lower()
                        visible = not query or query in haystack
                        item.setHidden(not visible)
                        model_visible = model_visible or visible
                    model.setHidden(not model_visible)
                    grade_visible = grade_visible or model_visible
                grade.setHidden(not grade_visible)
                family_visible = family_visible or grade_visible
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
        self.add_button.setEnabled(record is not None)
        self.open_doi.setEnabled(bool(record and record.doi))
        self.open_evidence.setEnabled(
            bool(
                record
                and str(
                    record.parameter_evidence.get("url", "")
                ).strip()
            )
        )
        if record is None:
            return
        self._show_record(record)

    def _parameter_display(
        self,
        model: str,
        key: str,
        value: float,
    ) -> tuple[str, str]:
        kind = MATERIAL_PARAMETER_KINDS.get(model, {}).get(key, "raw")
        if kind == "stress":
            display = self._units.engineering_stress_from_pa(value)
            return f"{display:g}", self._units.engineering_stress_label
        if kind == "length":
            display = self._units.length_from_m(value)
            return f"{display:g}", self._units.length
        return f"{value:g}", "—"

    def _show_record(self, record: MaterialLibraryRecord) -> None:
        self.heading.setText(
            f"{record.grade}  →  {record.model}"
        )
        self.summary.setText(
            f"{record.material} · {record.standard} · "
            f"Verified parameter set: {record.preset_name}"
        )

        rows = list(record.parameters_si.items())
        self.parameter_table.setRowCount(len(rows))
        evidence_location = str(
            record.parameter_evidence.get("location", "")
        )
        for row, (key, value) in enumerate(rows):
            display, unit = self._parameter_display(
                record.model,
                key,
                float(value),
            )
            values = (
                key,
                display,
                unit,
                evidence_location,
            )
            for column, cell in enumerate(values):
                self.parameter_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(cell)),
                )

        ref = record.primary_reference
        evidence = record.parameter_evidence
        self.reference.setText(
            f"Primary peer-reviewed reference\n"
            f"{ref.get('authors', '')} ({ref.get('year', '')})\n"
            f"{ref.get('title', '')}\n"
            f"{ref.get('journal', '')} {ref.get('volume_issue', '')}, "
            f"{ref.get('article', '')}\n"
            f"DOI: {ref.get('doi', '')}\n\n"
            f"Exact parameter evidence\n"
            f"{evidence.get('author', '')} ({evidence.get('year', '')})\n"
            f"{evidence.get('title', '')}\n"
            f"{evidence.get('institution', '')}\n"
            f"{evidence.get('location', '')}\n\n"
            f"{evidence.get('relationship', '')}"
        )

        applicability = "\n".join(
            f"✓ {item}" for item in record.applicability
        )
        limitations = "\n".join(
            f"• {item}" for item in record.limitations
        )
        self.scope.setText(
            "Applicability\n"
            + applicability
            + "\n\nLimitations\n"
            + limitations
        )
        self.preview.set_material(
            record.model,
            dict(record.parameters_si),
        )

    def _open_doi(self) -> None:
        record = self._selected_record
        if record is None or not record.doi:
            return
        QDesktopServices.openUrl(
            QUrl("https://doi.org/" + record.doi)
        )

    def _open_evidence(self) -> None:
        record = self._selected_record
        if record is None:
            return
        url = str(record.parameter_evidence.get("url", "")).strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def material_data(self) -> MaterialData:
        if self._selected_record is None:
            raise ValueError("Select a verified material parameter set.")
        return material_from_library_record(
            self._selected_record,
            tag=self._next_tag,
        )
