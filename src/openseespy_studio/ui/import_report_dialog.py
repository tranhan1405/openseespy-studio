from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..importer import OpenSeesImportResult


class ImportReportDialog(QDialog):
    def __init__(self, result: OpenSeesImportResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenSeesPy Import Report")
        self.setModal(True)
        self.resize(900, 520)

        root = QVBoxLayout(self)

        counts = ", ".join(
            f"{name}: {value}"
            for name, value in sorted(result.imported_counts.items())
            if value
        ) or "No supported model objects were recovered."

        summary = QLabel(
            f"<b>{result.source_name}</b><br>"
            f"{counts}<br><br>"
            f"Errors: {result.error_count} &nbsp;&nbsp; "
            f"Warnings: {result.warning_count} &nbsp;&nbsp; "
            f"Unsupported: {result.unsupported_count}"
        )
        summary.setWordWrap(True)
        root.addWidget(summary)

        note = QLabel(
            "Safe import never executes the Python file. Unsupported constructs "
            "remain listed below so you can decide whether the recovered model "
            "is complete enough to bring into Studio."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Severity", "Line", "Construct", "Message"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        root.addWidget(self.table, 1)

        colors = {
            "ERROR": QColor("#b42318"),
            "WARNING": QColor("#a15c00"),
            "UNSUPPORTED": QColor("#5b4b8a"),
        }
        self.table.setRowCount(len(result.issues))
        for row, issue in enumerate(result.issues):
            values = (
                issue.severity,
                str(issue.line or "-"),
                issue.construct,
                issue.message,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setForeground(
                        colors.get(issue.severity, QColor("#3b5b7a"))
                    )
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)

        buttons = QDialogButtonBox()
        self.import_button = buttons.addButton(
            "Import Recovered Model",
            QDialogButtonBox.AcceptRole,
        )
        cancel = buttons.addButton(
            QDialogButtonBox.Cancel,
        )
        self.import_button.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

        recoverable = (
            len(result.project.model.nodes) > 0
            or len(result.project.materials) > 0
            or len(result.project.sections) > 0
        )
        self.import_button.setEnabled(recoverable and result.error_count == 0)
        root.addWidget(buttons)
