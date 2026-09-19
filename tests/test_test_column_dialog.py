from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.project import ProjectDatabase, SectionData
from openseespy_studio.ui.test_column_dialog import TestColumnWizard


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_test_column_wizard_cyclic_preset_builds_reference_loading(qapp):
    project = ProjectDatabase()
    project.add_section(
        SectionData(1, "RC column", "Elastic")
    )
    dialog = TestColumnWizard(project)
    try:
        dialog.preset.setCurrentText("Cantilever Cyclic Test")
        qapp.processEvents()

        spec = dialog.data()
        assert spec.axis == 3
        assert spec.lateral_direction == 1
        assert spec.planar is True
        assert spec.base_support == "Fixed"
        assert spec.top_support == "Free"
        assert spec.element_type == "forceBeamColumn"
        assert spec.lateral_reference_load == pytest.approx(1.0)
        assert spec.prescribed_displacement == pytest.approx(0.0)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_test_column_wizard_dynamic_preset_enables_top_mass(qapp):
    dialog = TestColumnWizard(ProjectDatabase())
    try:
        dialog.preset.setCurrentText("Dynamic / Shake-table Column")
        qapp.processEvents()

        spec = dialog.data()
        assert spec.top_mass == pytest.approx(1.0)
        assert spec.top_mass_directions == (1, 2, 3)
        assert spec.axial_load == pytest.approx(0.0)
        assert spec.lateral_reference_load == pytest.approx(0.0)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_test_column_wizard_auto_changes_lateral_axis(qapp):
    dialog = TestColumnWizard(ProjectDatabase())
    try:
        dialog.axis.setCurrentIndex(dialog.axis.findData(1))
        qapp.processEvents()
        assert dialog.lateral.currentData() != 1

        spec = dialog.data()
        assert spec.axis == 1
        assert spec.lateral_direction in {2, 3}
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_test_column_wizard_can_shrink_and_scroll(qapp):
    dialog = TestColumnWizard(ProjectDatabase())
    try:
        dialog.show()
        qapp.processEvents()
        dialog.resize(460, 340)
        qapp.processEvents()

        assert dialog.height() <= 360
        assert dialog.scroll.widgetResizable() is True
        assert dialog.scroll.verticalScrollBar().maximum() > 0
        assert dialog.buttons.isVisible() is True
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
