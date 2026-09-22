from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ProjectDatabase, SectionData
from openseespy_studio.ui.moment_curvature_dialog import (
    MomentCurvatureDialog,
)


_APP = QApplication.instance() or QApplication([])


def _project(length: str = "mm") -> ProjectDatabase:
    project = ProjectDatabase(
        name="MC dialog",
        model=StructuralModel("MC dialog", ndm=2, ndf=3),
        units={"length": length, "force": "N", "time": "s"},
    )
    project.add_section(
        SectionData(
            3,
            "RC section",
            "Elastic",
            parameters={
                "E": 30.0e9,
                "A": 1.0,
                "Iz": 1.0,
                "Iy": 1.0,
                "G": 12.0e9,
                "J": 1.0,
            },
        )
    )
    return project


def test_dialog_has_scroll_and_research_inputs():
    dialog = MomentCurvatureDialog(_project(), None)
    try:
        assert dialog.scroll.widgetResizable() is True
        assert dialog.scroll.widget() is not None
        assert dialog.section.currentData() == 3
        assert dialog.axis.currentData() == "Mz"
        assert dialog.increments.value() == 100
        assert dialog.max_curvature.suffix() == " 1/mm"
        # 0.02 /m = 0.00002 /mm.
        assert dialog.max_curvature.value() == pytest.approx(2.0e-5)
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_dialog_returns_active_unit_values_for_isolated_builder():
    dialog = MomentCurvatureDialog(_project(), None)
    try:
        dialog.axial_load.setValue(-250000.0)
        dialog.max_curvature.setValue(5.0e-5)
        dialog.increments.setValue(200)

        spec = dialog.spec()

        assert spec.section_tag == 3
        assert spec.axis == "Mz"
        assert spec.axial_load == pytest.approx(-250000.0)
        assert spec.max_curvature == pytest.approx(5.0e-5)
        assert spec.increments == 200
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()



def test_dialog_opens_with_visible_empty_section_state():
    project = ProjectDatabase(
        name="Empty MC",
        model=StructuralModel("Empty MC", ndm=2, ndf=3),
        units={"length": "m", "force": "N", "time": "s"},
    )
    dialog = MomentCurvatureDialog(project, None)
    try:
        assert dialog.section.currentData() is None
        assert "No Sections available" in dialog.section.currentText()
        assert (
            dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
            is False
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()
