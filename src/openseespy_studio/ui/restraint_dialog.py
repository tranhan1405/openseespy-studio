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

from ..model import FIXITY_PRESETS


class RestraintDialog(QDialog):
    DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

    def __init__(self, initial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Support / Restraint")
        self.setModal(True)
        self.resize(360, 330)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.preset = QComboBox()
        self._preset_names = [
            "Fixed",
            "Pinned",
            "Roller X (free UX)",
            "Roller Y (free UY)",
            "Roller Z (free UZ)",
            "Custom",
        ]
        self.preset.addItems(self._preset_names)
        form.addRow("Preset:", self.preset)
        root.addLayout(form)

        hint = QLabel(
            "Checked DOF = restrained. Roller axis is the free translation direction."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        group = QGroupBox("Degrees of freedom")
        dof_form = QFormLayout(group)
        self.checks: list[QCheckBox] = []
        for label in self.DOF_LABELS:
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
            matched = None
            for name, fixity in FIXITY_PRESETS.items():
                if values == fixity:
                    matched = name
                    break
            if matched is None:
                self.preset.setCurrentText("Custom")
                self._set_checks(values)
            else:
                label = {
                    "Fixed": "Fixed",
                    "Pinned": "Pinned",
                    "Roller X": "Roller X (free UX)",
                    "Roller Y": "Roller Y (free UY)",
                    "Roller Z": "Roller Z (free UZ)",
                }[matched]
                self.preset.setCurrentText(label)
                self._preset_changed(label)
        else:
            self.preset.setCurrentText("Fixed")
            self._preset_changed("Fixed")

    def _preset_changed(self, label: str) -> None:
        mapping = {
            "Fixed": FIXITY_PRESETS["Fixed"],
            "Pinned": FIXITY_PRESETS["Pinned"],
            "Roller X (free UX)": FIXITY_PRESETS["Roller X"],
            "Roller Y (free UY)": FIXITY_PRESETS["Roller Y"],
            "Roller Z (free UZ)": FIXITY_PRESETS["Roller Z"],
        }
        if label in mapping:
            self._set_checks(mapping[label])

    def _set_checks(self, fixity) -> None:
        self._updating = True
        try:
            for check, value in zip(self.checks, fixity):
                check.setChecked(bool(value))
        finally:
            self._updating = False

    def _manual_change(self) -> None:
        if self._updating:
            return
        values = self.fixity()
        for name, preset in FIXITY_PRESETS.items():
            if values == preset:
                label = {
                    "Fixed": "Fixed",
                    "Pinned": "Pinned",
                    "Roller X": "Roller X (free UX)",
                    "Roller Y": "Roller Y (free UY)",
                    "Roller Z": "Roller Z (free UZ)",
                }[name]
                self._updating = True
                try:
                    self.preset.setCurrentText(label)
                finally:
                    self._updating = False
                return
        self._updating = True
        try:
            self.preset.setCurrentText("Custom")
        finally:
            self._updating = False

    def fixity(self) -> tuple[int, ...]:
        return tuple(1 if check.isChecked() else 0 for check in self.checks)
