from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.hinge_backbone_dialog import (
    HingeBackboneDialog,
)


_APP = QApplication.instance() or QApplication([])


def _close(dialog: HingeBackboneDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_dialog_keeps_section_to_hinge_steps_separate():
    dialog = HingeBackboneDialog(
        next_tag=12,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        assert dialog.windowTitle() == "Hinge Backbone Builder"
        assert dialog.scroll.widgetResizable() is True
        assert dialog.scroll.widget() is not None
        assert dialog.tag.value() == 12
        assert dialog.source_kind.findData("response_2000") >= 0
        assert dialog.basis.findData("moment_rotation") >= 0
        assert dialog.basis.findData("moment_curvature") >= 0
        assert dialog.hinge_length.isEnabled() is False
        assert "Rotation" in dialog.points.horizontalHeaderItem(2).text()
    finally:
        _close(dialog)


def test_dialog_converts_active_mm_units_to_si_traceable_hinge_material():
    dialog = HingeBackboneDialog(
        next_tag=13,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        dialog.source_kind.setCurrentIndex(
            dialog.source_kind.findData("response_2000")
        )
        dialog.source_note.setText("Response-2000 Column C1")

        dialog.basis.setCurrentIndex(
            dialog.basis.findData("moment_curvature")
        )
        _APP.processEvents()
        assert dialog.hinge_length.isEnabled()
        assert "1/mm" in dialog.points.horizontalHeaderItem(2).text()

        dialog.hinge_length.setValue(300.0)

        moments_nmm = (100.0e6, 150.0e6, 140.0e6)
        curvatures_per_mm = (1.0e-6, 4.0e-6, 12.0e-6)
        for spin, value in zip(dialog._moment_spins, moments_nmm):
            spin.setValue(value)
        for spin, value in zip(
            dialog._deformation_spins,
            curvatures_per_mm,
        ):
            spin.setValue(value)

        material = dialog.material_data()

        assert material.material_type == "Hysteretic"
        assert material.source["response_quantity"] == "moment_rotation"
        calibration = material.source["calibration"]
        assert calibration["source_kind"] == "response_2000"
        assert calibration["source_note"] == "Response-2000 Column C1"
        assert calibration["basis"] == "moment_curvature"
        assert calibration["conversion"] == "theta = kappa * L_eq"
        assert calibration["equivalent_hinge_length_m"] == pytest.approx(0.3)

        assert material.parameters["s1p"] == pytest.approx(100.0e3)
        assert material.parameters["s2p"] == pytest.approx(150.0e3)
        assert material.parameters["s3p"] == pytest.approx(140.0e3)
        assert material.parameters["e1p"] == pytest.approx(0.0003)
        assert material.parameters["e2p"] == pytest.approx(0.0012)
        assert material.parameters["e3p"] == pytest.approx(0.0036)
        assert material.parameters["s1n"] == pytest.approx(-100.0e3)
        assert material.parameters["e3n"] == pytest.approx(-0.0036)
    finally:
        _close(dialog)


def test_dialog_accepts_prefill_from_sare_moment_curvature_result():
    dialog = HingeBackboneDialog(
        next_tag=14,
        units={"length": "m", "force": "kN", "time": "s"},
        prefill={
            "source_kind": "sare_moment_curvature",
            "source_note": "SARE Moment-Curvature · Section 3 · Mz",
            "basis": "moment_curvature",
        },
    )
    try:
        assert dialog.source_kind.currentData() == "sare_moment_curvature"
        assert dialog.source_note.text() == (
            "SARE Moment-Curvature · Section 3 · Mz"
        )
        assert dialog.basis.currentData() == "moment_curvature"
        assert dialog.hinge_length.isEnabled() is True
    finally:
        _close(dialog)



def test_sare_curve_prefills_three_hinge_points_in_active_units():
    dialog = HingeBackboneDialog(
        next_tag=15,
        units={"length": "mm", "force": "N", "time": "s"},
        prefill={
            "source_kind": "sare_moment_curvature",
            "source_note": "SARE Moment-Curvature · Section 8 · Mz",
            "basis": "moment_curvature",
            "curvature": [
                0.0,
                0.5e-6,
                1.0e-6,
                2.0e-6,
                4.0e-6,
                8.0e-6,
                12.0e-6,
            ],
            "moment": [
                0.0,
                40.0e6,
                78.0e6,
                125.0e6,
                150.0e6,
                158.0e6,
                155.0e6,
            ],
        },
    )
    try:
        moments = [spin.value() for spin in dialog._moment_spins]
        curvatures = [
            spin.value() for spin in dialog._deformation_spins
        ]

        assert all(value > 0.0 for value in moments)
        assert 0.0 < curvatures[0] < curvatures[1] < curvatures[2]
        assert curvatures[2] == pytest.approx(12.0e-6)
        assert moments[2] == pytest.approx(155.0e6)
        assert "prefilled" in dialog.point_note.text()
        assert "starting suggestions only" in dialog.point_note.text()
    finally:
        _close(dialog)
