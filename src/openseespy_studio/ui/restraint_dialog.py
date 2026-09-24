from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from ..model import (
    dof_labels_for_model,
    fixity_presets_for_model,
)


class RestraintDialog(QDialog):
    def __init__(
        self,
        initial=None,
        parent=None,
        *,
        ndm=3,
        ndf=6,
    ):
        super().__init__(parent)
        self.setWindowTitle("Support / Restraint")
        self.setModal(True)
        self.resize(360, 330)

        self.ndm = int(ndm)
        self.ndf = int(ndf)
        self._dof_labels = dof_labels_for_model(self.ndm, self.ndf)
        self._presets = fixity_presets_for_model(self.ndm, self.ndf)
        self._preset_display = {
            name: (
                f"{name} (free U{name[-1]})"
                if name.startswith("Roller ")
                else name
            )
            for name in self._presets
        }

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.preset = QComboBox()
        self._preset_names = [
            self._preset_display[name]
            for name in self._presets
        ] + ["Custom"]
        self.preset.addItems(self._preset_names)
        form.addRow("Preset:", self.preset)
        root.addLayout(form)

        hint = QLabel(
            "Checked DOF = restrained. Labels follow the active OpenSees "
            f"model (ndm={self.ndm}, ndf={self.ndf})."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        group = QGroupBox("Degrees of freedom")
        dof_form = QFormLayout(group)
        self.checks: list[QCheckBox] = []
        for label in self._dof_labels:
            check = QCheckBox("Restrained")
            self.checks.append(check)
            dof_form.addRow(f"{label}:", check)
            check.toggled.connect(self._manual_change)
        root.addWidget(group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._updating = False
        self.preset.currentTextChanged.connect(self._preset_changed)

        if initial is not None:
            values = tuple(int(v) for v in initial)
            matched = next(
                (
                    name
                    for name, fixity in self._presets.items()
                    if values == fixity
                ),
                None,
            )
            if matched is None:
                self.preset.setCurrentText("Custom")
                self._set_checks(values)
            else:
                label = self._preset_display[matched]
                self.preset.setCurrentText(label)
                self._preset_changed(label)
        else:
            self.preset.setCurrentText(
                self._preset_display.get("Fixed", "Custom")
            )
            self._preset_changed(self.preset.currentText())

    def _preset_changed(self, label: str) -> None:
        for name, display in self._preset_display.items():
            if label == display:
                self._set_checks(self._presets[name])
                return

    def _set_checks(self, fixity) -> None:
        values = tuple(int(value) for value in fixity)
        self._updating = True
        try:
            for index, check in enumerate(self.checks):
                value = values[index] if index < len(values) else 0
                check.setChecked(bool(value))
        finally:
            self._updating = False

    def _manual_change(self) -> None:
        if self._updating:
            return
        values = self.fixity()
        matched = next(
            (
                name
                for name, preset in self._presets.items()
                if values == preset
            ),
            None,
        )
        self._updating = True
        try:
            self.preset.setCurrentText(
                self._preset_display[matched]
                if matched is not None
                else "Custom"
            )
        finally:
            self._updating = False

    def fixity(self) -> tuple[int, ...]:
        return tuple(1 if check.isChecked() else 0 for check in self.checks)

