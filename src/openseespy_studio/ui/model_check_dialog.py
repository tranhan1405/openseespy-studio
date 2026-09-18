from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..validation import ValidationIssue


class ModelCheckDialog(QDialog):
    def __init__(
        self,
        issues: list[ValidationIssue],
        *,
        allow_run: bool = False,
        select_callback: Callable[[ValidationIssue], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Model Check")
        self.setModal(True)
        self.resize(920, 470)
        self._issues = list(issues)
        self._select_callback = select_callback

        errors = sum(issue.severity == "ERROR" for issue in issues)
        warnings = sum(issue.severity == "WARNING" for issue in issues)

        root = QVBoxLayout(self)
        summary = QLabel(
            f"Model check found {errors} error(s) and {warnings} warning(s)."
        )
        summary.setStyleSheet(
            "font-weight: 700; color: #9b1c1c;"
            if errors
            else "font-weight: 700; color: #8a5a00;"
        )
        root.addWidget(summary)

        if errors:
            note = QLabel(
                "ERROR items must be fixed before OpenSees can run. "
                "Select an issue to locate its entity."
            )
        else:
            note = QLabel(
                "Warnings do not block the solver. Review them before running."
            )
        note.setWordWrap(True)
        root.addWidget(note)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Severity", "Category", "Entity", "Message", "Suggestion"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch
        )
        self.table.itemDoubleClicked.connect(
            lambda _item: self._select_current_issue()
        )
        root.addWidget(self.table, 1)

        self._populate()

        buttons = QDialogButtonBox()
        self.select_button = QPushButton("Select Entity")
        self.select_button.clicked.connect(self._select_current_issue)
        buttons.addButton(
            self.select_button,
            QDialogButtonBox.ActionRole,
        )

        if allow_run and not errors:
            run_button = QPushButton("Run Anyway")
            run_button.setDefault(True)
            run_button.clicked.connect(self.accept)
            buttons.addButton(
                run_button,
                QDialogButtonBox.AcceptRole,
            )

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addButton(
            close_button,
            QDialogButtonBox.RejectRole,
        )
        root.addWidget(buttons)

        if self.table.rowCount():
            self.table.selectRow(0)
        self.table.itemSelectionChanged.connect(
            self._update_select_button
        )
        self._update_select_button()

    def _populate(self) -> None:
        self.table.setRowCount(len(self._issues))
        severity_colors = {
            "ERROR": QColor("#b42318"),
            "WARNING": QColor("#a15c00"),
            "INFO": QColor("#3b5b7a"),
        }
        for row, issue in enumerate(self._issues):
            entity = (
                f"{issue.entity_kind.title()} {issue.entity_tag}"
                if issue.entity_kind and issue.entity_tag is not None
                else "-"
            )
            values = (
                issue.severity,
                issue.category,
                entity,
                issue.message,
                issue.suggestion,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row)
                if column == 0:
                    item.setForeground(
                        severity_colors.get(
                            issue.severity,
                            QColor("#3b5b7a"),
                        )
                    )
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)

    def _current_issue(self) -> ValidationIssue | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._issues):
            return None
        return self._issues[row]

    def _update_select_button(self) -> None:
        issue = self._current_issue()
        self.select_button.setEnabled(
            issue is not None
            and issue.entity_kind in {"node", "element"}
            and issue.entity_tag is not None
            and self._select_callback is not None
        )

    def _select_current_issue(self) -> None:
        issue = self._current_issue()
        if (
            issue is None
            or issue.entity_kind not in {"node", "element"}
            or issue.entity_tag is None
            or self._select_callback is None
        ):
            return
        self._select_callback(issue)
