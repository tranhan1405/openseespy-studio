from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from ..project import SurfaceRecorderData


class SurfaceRecorderDialog(QDialog):
    def __init__(
        self,
        *,
        surface_tag: int,
        surface_recorder: SurfaceRecorderData | None = None,
        next_tag: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Managed Surface Shell Recorder")
        self.setModal(True)
        self.surface_tag = int(surface_tag)

        root = QVBoxLayout(self)
        info = QLabel(
            f"Surface {self.surface_tag}\n"
            "Recorder scope is owned by Geometry. SARE regenerates the "
            "underlying Shell recorder target list after remeshing."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(
            surface_recorder.tag
            if surface_recorder is not None
            else int(next_tag)
        )
        self.tag.setEnabled(surface_recorder is None)

        self.name = QLineEdit(
            surface_recorder.name
            if surface_recorder is not None
            else f"Surface {self.surface_tag} Shell Recorder"
        )

        self.response = QComboBox()
        self.response.addItems(["force", "deformation"])
        if surface_recorder is not None:
            self.response.setCurrentText(surface_recorder.response)

        self.gauss_point = QSpinBox()
        self.gauss_point.setRange(1, 4)
        self.gauss_point.setValue(
            surface_recorder.section_number
            if surface_recorder is not None
            else 1
        )

        self.file_name = QLineEdit(
            surface_recorder.file_name
            if surface_recorder is not None
            else f"recorders/surface_{self.surface_tag}_shell.out"
        )
        self.include_time = QCheckBox("Include analysis time/load factor")
        self.include_time.setChecked(
            surface_recorder.include_time
            if surface_recorder is not None
            else True
        )

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Response:", self.response)
        form.addRow("Gauss point:", self.gauss_point)
        form.addRow("Output file:", self.file_name)
        form.addRow("", self.include_time)
        root.addLayout(form)

        note = QLabel(
            "Shell recorder output uses the native OpenSees element recorder "
            "at material/Gauss point 1..4. Direct FE Shell recorders remain "
            "available as the low-level workflow and intentionally block remesh."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def data(self) -> SurfaceRecorderData:
        return SurfaceRecorderData(
            tag=self.tag.value(),
            name=(
                self.name.text().strip()
                or f"Surface Recorder {self.tag.value()}"
            ),
            surface_tag=self.surface_tag,
            response=self.response.currentText(),
            section_number=self.gauss_point.value(),
            file_name=self.file_name.text().strip(),
            include_time=self.include_time.isChecked(),
            generated_recorder_tag=(
                self._source_generated_tag
                if hasattr(self, "_source_generated_tag")
                else None
            ),
        )

    def _accept(self) -> None:
        try:
            self.data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Managed Surface Shell Recorder",
                str(exc),
            )
            return
        self.accept()

    def set_source_generated_tag(self, tag: int | None) -> None:
        self._source_generated_tag = tag
