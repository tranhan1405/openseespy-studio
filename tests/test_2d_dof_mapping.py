from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.model import (
    classify_fixity,
    dof_is_rotation,
    dof_labels_for_model,
    fixity_presets_for_model,
)
from openseespy_studio.project import LoadPatternData
from openseespy_studio.ui.load_dialogs import PrescribedDisplacementDialog
from openseespy_studio.ui.restraint_dialog import RestraintDialog


_APP = QApplication.instance() or QApplication([])


def test_native_2d_frame_dof_labels_match_opensees_order():
    assert dof_labels_for_model(2, 3) == ("UX", "UY", "RZ")
    assert dof_is_rotation(2, 3, 1) is False
    assert dof_is_rotation(2, 3, 2) is False
    assert dof_is_rotation(2, 3, 3) is True


def test_3d_labels_remain_unchanged():
    assert dof_labels_for_model(3, 6) == (
        "UX", "UY", "UZ", "RX", "RY", "RZ"
    )
    assert dof_labels_for_model(3, 3) == ("UX", "UY", "UZ")


def test_native_2d_frame_fixity_presets_are_dimension_aware():
    presets = fixity_presets_for_model(2, 3)

    assert presets["Fixed"] == (1, 1, 1)
    assert presets["Pinned"] == (1, 1, 0)
    assert presets["Roller X"] == (0, 1, 0)
    assert presets["Roller Y"] == (1, 0, 0)
    assert "Roller Z" not in presets
    assert classify_fixity((1, 1, 1), ndm=2) == "Fixed"
    assert classify_fixity((1, 1, 0), ndm=2) == "Pinned"


def test_restraint_dialog_uses_rz_for_native_2d_frame():
    dialog = RestraintDialog(
        initial=(1, 1, 1),
        ndm=2,
        ndf=3,
    )
    try:
        assert dialog._dof_labels == ("UX", "UY", "RZ")
        assert dialog.fixity() == (1, 1, 1)
        assert dialog.preset.currentText() == "Fixed"
        assert all("Roller Z" not in dialog.preset.itemText(i)
                   for i in range(dialog.preset.count()))
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_prescribed_displacement_dialog_marks_2d_dof3_as_rotation():
    patterns = {
        1: LoadPatternData(
            tag=1,
            name="Ramp",
            pattern_type="Plain",
            time_series_tag=1,
        )
    }
    dialog = PrescribedDisplacementDialog(
        patterns,
        ndm=2,
        ndf=3,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert [dialog.dof.itemText(i) for i in range(dialog.dof.count())] == [
            "UX (DOF 1)",
            "UY (DOF 2)",
            "RZ (DOF 3)",
        ]
        dialog.dof.setCurrentIndex(2)
        assert dialog.value_label.text() == "Value [rad]:"
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()
