from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..project import RecorderData
from .selection import parse_tag_expression


RECORDER_RESPONSES: dict[str, list[str]] = {
    "Node": ["disp", "vel", "accel", "reaction"],
    "Element": ["globalForce", "localForce"],
    "Shell": ["force", "deformation"],
    "Section": ["force", "deformation"],
    "Fiber": ["stressStrain", "stress", "strain"],
}


class RecorderDialog(QDialog):
    def __init__(
        self,
        *,
        next_tag: int | None = None,
        recorder: RecorderData | None = None,
        initial_node_tags: set[int] | None = None,
        initial_element_tags: set[int] | None = None,
        target_creator: Callable[[str], list[int]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Recorder" if recorder is not None else "New Recorder"
        )
        self.setMinimumWidth(470)
        self._recorder = recorder
        self._target_creator = target_creator

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_000_000_000)
        self.tag.setValue(
            recorder.tag if recorder is not None else int(next_tag or 1)
        )
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            recorder.name if recorder is not None else "Recorder"
        )
        form.addRow("Name:", self.name)

        self.recorder_type = QComboBox()
        self.recorder_type.addItems(
            ["Node", "Element", "Shell", "Section", "Fiber"]
        )
        if recorder is not None:
            self.recorder_type.setCurrentText(recorder.recorder_type)
        elif initial_element_tags and not initial_node_tags:
            self.recorder_type.setCurrentText("Element")
        form.addRow("Type:", self.recorder_type)

        if recorder is not None:
            target_text = ", ".join(map(str, recorder.target_tags))
        else:
            node_tags = sorted(initial_node_tags or ())
            element_tags = sorted(initial_element_tags or ())
            target_text = ", ".join(
                map(str, node_tags if node_tags else element_tags)
            )
        self.targets = QLineEdit(target_text)
        self.targets.setPlaceholderText("e.g. 1, 2, 5-10")

        target_row = QHBoxLayout()
        target_row.addWidget(self.targets, 1)
        self.create_target = QPushButton("Create / Link Target...")
        self.create_target.setToolTip(
            "Create or link the prerequisite target required by the "
            "selected recorder type"
        )
        self.create_target.setEnabled(self._target_creator is not None)
        self.create_target.clicked.connect(self._create_or_link_target)
        target_row.addWidget(self.create_target)
        form.addRow("Target tags:", target_row)

        self.response = QComboBox()
        form.addRow("Response:", self.response)

        self.dofs = QLineEdit(
            ", ".join(map(str, recorder.dofs))
            if recorder is not None
            else "1"
        )
        self.dofs.setPlaceholderText("1,2,3")
        form.addRow("DOFs:", self.dofs)

        self.section_number = QSpinBox()
        self.section_number.setRange(1, 1000)
        self.section_number.setValue(
            recorder.section_number if recorder is not None else 1
        )
        form.addRow("Section/IP no.:", self.section_number)

        self.fiber_index = QSpinBox()
        self.fiber_index.setRange(-1, 2_000_000_000)
        self.fiber_index.setSpecialValueText("Coordinates / nearest")
        self.fiber_index.setValue(
            recorder.fiber_index
            if recorder is not None and recorder.fiber_index is not None
            else -1
        )
        form.addRow("Fiber index:", self.fiber_index)

        self.fiber_y = QDoubleSpinBox()
        self.fiber_y.setRange(-1.0e12, 1.0e12)
        self.fiber_y.setDecimals(9)
        self.fiber_y.setValue(
            recorder.fiber_y if recorder is not None else 0.0
        )
        form.addRow("Fiber y:", self.fiber_y)

        self.fiber_z = QDoubleSpinBox()
        self.fiber_z.setRange(-1.0e12, 1.0e12)
        self.fiber_z.setDecimals(9)
        self.fiber_z.setValue(
            recorder.fiber_z if recorder is not None else 0.0
        )
        form.addRow("Fiber z:", self.fiber_z)

        self.material_tag = QSpinBox()
        self.material_tag.setRange(0, 2_000_000_000)
        self.material_tag.setSpecialValueText("Any / nearest")
        self.material_tag.setValue(
            recorder.material_tag
            if recorder is not None and recorder.material_tag is not None
            else 0
        )
        form.addRow("Fiber material:", self.material_tag)

        self.file_name = QLineEdit(
            recorder.file_name
            if recorder is not None
            else f"recorders/recorder_{int(next_tag or 1)}.out"
        )
        form.addRow("Output file:", self.file_name)

        self.include_time = QCheckBox("Include analysis time/load factor")
        self.include_time.setChecked(
            recorder.include_time if recorder is not None else True
        )
        form.addRow("", self.include_time)

        note = QLabel(
            "Node: disp/vel/accel/reaction · Element: global/local force · "
            "Shell: Gauss-point force/deformation (GP 1..4) · "
            "Section: force/deformation · Fiber: stress/strain/stressStrain. "
            "Fiber selection may use an explicit index or nearest y-z coordinates."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.recorder_type.currentTextChanged.connect(
            self._update_type_controls
        )
        self.fiber_index.valueChanged.connect(
            self._update_type_controls
        )
        self._update_type_controls()
        if recorder is not None:
            self.response.setCurrentText(recorder.response)

    def _create_or_link_target(self) -> None:
        if self._target_creator is None:
            return
        recorder_type = self.recorder_type.currentText()
        try:
            tags = [
                int(tag)
                for tag in self._target_creator(recorder_type)
            ]
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Recorder Target", str(exc))
            return
        if tags:
            self.targets.setText(", ".join(map(str, sorted(set(tags)))))

    def _update_type_controls(self) -> None:
        recorder_type = self.recorder_type.currentText()
        current_response = self.response.currentText()
        self.response.clear()
        self.response.addItems(RECORDER_RESPONSES[recorder_type])
        if current_response in RECORDER_RESPONSES[recorder_type]:
            self.response.setCurrentText(current_response)

        is_node = recorder_type == "Node"
        is_section = recorder_type in {"Section", "Fiber"}
        is_shell = recorder_type == "Shell"
        is_fiber = recorder_type == "Fiber"
        self.dofs.setEnabled(is_node)
        self.section_number.setEnabled(is_section or is_shell)
        self.section_number.setMaximum(4 if is_shell else 1000)
        if is_shell and self.section_number.value() > 4:
            self.section_number.setValue(4)
        self.fiber_y.setEnabled(is_fiber)
        self.fiber_z.setEnabled(is_fiber)
        self.material_tag.setEnabled(is_fiber)
        self.fiber_index.setEnabled(is_fiber)
        use_coordinates = (
            is_fiber and self.fiber_index.value() < 0
        )
        self.fiber_y.setEnabled(use_coordinates)
        self.fiber_z.setEnabled(use_coordinates)
        self.material_tag.setEnabled(use_coordinates)

    def _accept(self) -> None:
        try:
            self.data()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Recorder", str(exc))
            return
        self.accept()

    def data(self) -> RecorderData:
        targets = sorted(parse_tag_expression(self.targets.text()))
        dofs = (
            sorted(parse_tag_expression(self.dofs.text()))
            if self.recorder_type.currentText() == "Node"
            else []
        )
        material_tag = self.material_tag.value() or None
        fiber_index = (
            self.fiber_index.value()
            if self.fiber_index.value() >= 0
            else None
        )
        return RecorderData(
            tag=self.tag.value(),
            name=self.name.text().strip(),
            recorder_type=self.recorder_type.currentText(),
            target_tags=targets,
            response=self.response.currentText(),
            dofs=dofs,
            file_name=self.file_name.text().strip(),
            include_time=self.include_time.isChecked(),
            section_number=self.section_number.value(),
            fiber_y=self.fiber_y.value(),
            fiber_z=self.fiber_z.value(),
            material_tag=material_tag,
            fiber_index=fiber_index,
        )
