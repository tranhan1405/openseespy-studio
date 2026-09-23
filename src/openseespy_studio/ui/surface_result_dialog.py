from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..project import AnalysisSettingsData, SolutionResultData


FORCE_COMPONENTS = ("Nxx", "Nyy", "Nxy", "Mxx", "Myy", "Mxy", "Qx", "Qy")
DEFORMATION_COMPONENTS = (
    "Exx", "Eyy", "Gxy", "Kxx", "Kyy", "Kxy", "Gxz", "Gyz"
)


class SurfaceResultDialog(QDialog):
    def __init__(
        self,
        analyses: dict[int, AnalysisSettingsData],
        *,
        surface_tags,
        result: SolutionResultData | None = None,
        next_tag: int = 1,
        new_analysis_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Managed Surface Shell Result")
        self.setModal(True)
        self.surface_tags = sorted({int(tag) for tag in surface_tags})
        self._analyses = dict(analyses)
        self._new_analysis_callback = new_analysis_callback

        root = QVBoxLayout(self)
        info = QLabel(
            "Geometry Surface scope: "
            + ", ".join(f"S{tag}" for tag in self.surface_tags)
            + "\nThe FE Shell element scope is regenerated automatically "
            "after remeshing."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(result.tag if result is not None else int(next_tag))
        self.tag.setEnabled(result is None)

        self.name = QLineEdit(
            result.name
            if result is not None
            else (
                "Surface Shell Force"
                if result is None
                else result.name
            )
        )

        self.analysis = QComboBox()
        self._refresh_analysis_choices(
            result.analysis_tag if result is not None else None
        )
        self.analysis_new = QPushButton("New Analysis...")
        self.analysis_new.setEnabled(callable(self._new_analysis_callback))
        self.analysis_new.setToolTip(
            "Define compatible Analysis Settings now without closing this dialog."
        )
        self.analysis_new.clicked.connect(self._create_analysis_dependency)
        self.analysis_holder = QWidget()
        analysis_row = QHBoxLayout(self.analysis_holder)
        analysis_row.setContentsMargins(0, 0, 0, 0)
        analysis_row.setSpacing(4)
        analysis_row.addWidget(self.analysis, 1)
        analysis_row.addWidget(self.analysis_new)

        self.result_type = QComboBox()
        self.result_type.addItem("Shell Force", "ShellForce")
        self.result_type.addItem("Shell Deformation", "ShellDeformation")
        if result is not None:
            index = self.result_type.findData(result.result_type)
            if index >= 0:
                self.result_type.setCurrentIndex(index)

        self.component = QComboBox()

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Analysis:", self.analysis_holder)
        form.addRow("Result:", self.result_type)
        form.addRow("Component:", self.component)
        root.addLayout(form)

        note = QLabel(
            "Only ShellForce and ShellDeformation are Geometry-managed here. "
            "Direct FE-scoped result requests remain available as the "
            "low-level workflow and intentionally block remeshing."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.result_type.currentIndexChanged.connect(
            self._refresh_components
        )
        self._refresh_components()
        if result is not None:
            component = str(result.settings.get("component", ""))
            index = self.component.findText(component)
            if index >= 0:
                self.component.setCurrentIndex(index)

    def _refresh_analysis_choices(self, select_tag=None) -> None:
        current = self.analysis.currentData() if self.analysis.count() else None
        wanted = select_tag if select_tag is not None else current
        self.analysis.clear()
        self.analysis.addItem("Select Analysis Settings...", None)
        for tag in sorted(self._analyses):
            item = self._analyses[tag]
            if item.analysis_type == "Modal":
                continue
            self.analysis.addItem(
                f"{tag} - {item.name} ({item.analysis_type})",
                int(tag),
            )
        if wanted is not None:
            index = self.analysis.findData(int(wanted))
            if index >= 0:
                self.analysis.setCurrentIndex(index)
        elif self.analysis.count() == 2:
            self.analysis.setCurrentIndex(1)

    def _create_analysis_dependency(self) -> None:
        if not callable(self._new_analysis_callback):
            return
        analysis = self._new_analysis_callback()
        if analysis is None:
            return
        if analysis.analysis_type == "Modal":
            QMessageBox.warning(
                self,
                "Managed Surface Shell Result",
                "Modal Analysis Settings are not compatible with this result.",
            )
            return
        self._analyses[int(analysis.tag)] = analysis
        self._refresh_analysis_choices(int(analysis.tag))

    def _refresh_components(self) -> None:
        current = self.component.currentText()
        result_type = str(self.result_type.currentData())
        options = (
            FORCE_COMPONENTS
            if result_type == "ShellForce"
            else DEFORMATION_COMPONENTS
        )
        self.component.clear()
        self.component.addItems(list(options))
        index = self.component.findText(current)
        if index >= 0:
            self.component.setCurrentIndex(index)
        if not self.name.text().strip() or self.name.text().startswith(
            "Surface Shell "
        ):
            self.name.setText(
                "Surface Shell Force"
                if result_type == "ShellForce"
                else "Surface Shell Deformation"
            )

    def data(self) -> SolutionResultData:
        if self.analysis.currentData() is None:
            raise ValueError(
                "Create a compatible non-modal Analysis Settings object first."
            )
        if not self.surface_tags:
            raise ValueError("Select at least one Geometry Surface.")
        return SolutionResultData(
            tag=self.tag.value(),
            analysis_tag=int(self.analysis.currentData()),
            name=self.name.text().strip(),
            result_type=str(self.result_type.currentData()),
            surface_scope=list(self.surface_tags),
            settings={"component": self.component.currentText()},
        )

    def _accept(self) -> None:
        try:
            self.data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Managed Surface Shell Result",
                str(exc),
            )
            return
        self.accept()
