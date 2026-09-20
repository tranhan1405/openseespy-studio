from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.material_dialog import (
    MaterialDialog,
    MaterialEnvelopePreview,
)


_APP = QApplication.instance() or QApplication([])


def _select_material_type(dialog: MaterialDialog, material_type: str) -> None:
    index = dialog.material_type.findData(material_type)
    assert index >= 0
    dialog.material_type.setCurrentIndex(index)
    _APP.processEvents()


def _close(dialog: MaterialDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_wrapper_material_hides_response_diagram():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        # Fatigue is a wrapper around an existing material and does not have
        # an independent response curve of its own.
        _select_material_type(dialog, "Fatigue")

        assert dialog.preview_host.isHidden()
        assert not dialog.material_note.isHidden()
        assert dialog.preview.minimumWidth() <= 260
        assert dialog.preview.minimumHeight() <= 180
    finally:
        _close(dialog)


def test_bond_sp01_shows_compact_stress_slip_diagram():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Bond_SP01")

        assert not dialog.preview_host.isHidden()
        assert "parameter diagram" in dialog.preview_title.text().lower()
        points, note, annotations = dialog.preview._curve()
        assert len(points) == 5
        assert "stress-slip" in note
        assert any(label == "Sy / Fy" for _x, _y, label in annotations)
        assert any(label == "Su / Fu" for _x, _y, label in annotations)
    finally:
        _close(dialog)


def test_concrete02_diagram_contains_compression_and_tension_parameters():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Concrete02")

        assert not dialog.preview_host.isHidden()
        points, note, annotations = dialog.preview._curve()
        assert len(points) > 10
        assert "Concrete02" in note
        labels = {label for _x, _y, label in annotations}
        assert "epsc0 / fpc" in labels
        assert "epsU / fpcu" in labels
        assert "ft" in labels
        assert "Ets" in labels
        assert min(y for _x, y in points) < 0.0
        assert max(y for _x, y in points) > 0.0
    finally:
        _close(dialog)


def test_steel02_diagram_uses_current_material_parameters():
    preview = MaterialEnvelopePreview()
    try:
        preview.set_material(
            "Steel02",
            {
                "Fy": 355.0,
                "E0": 200000.0,
                "b": 0.01,
                "R0": 20.0,
                "cR1": 0.925,
                "cR2": 0.15,
            },
        )
        points, note, annotations = preview._curve()

        assert len(points) == 41
        assert "Menegotto-Pinto" in note
        assert points[0][0] < 0.0 < points[-1][0]
        assert points[0][1] < 0.0 < points[-1][1]
        assert any(label == "Fy / E0" for _x, _y, label in annotations)
    finally:
        preview.close()
        preview.deleteLater()
        _APP.processEvents()


def test_reinforcing_steel_diagram_marks_hardening_and_ultimate_strain():
    preview = MaterialEnvelopePreview()
    try:
        preview.set_material(
            "ReinforcingSteel",
            {
                "fy": 500.0,
                "fu": 650.0,
                "Es": 200000.0,
                "Esh": 5000.0,
                "eps_sh": 0.01,
                "eps_ult": 0.12,
            },
        )
        points, _note, annotations = preview._curve()

        labels = {label for _x, _y, label in annotations}
        assert points[-1][0] == 0.12
        assert "fy" in labels
        assert "eps_sh" in labels
        assert "eps_ult / fu" in labels
    finally:
        preview.close()
        preview.deleteLater()
        _APP.processEvents()
