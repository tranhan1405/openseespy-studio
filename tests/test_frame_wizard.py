from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from openseespy_studio.project import ProjectDatabase
from openseespy_studio.ui.frame_wizard import FrameWizard
from openseespy_studio.ui.main_window import MainWindow


_APP = QApplication.instance() or QApplication([])


def test_frame_wizard_starts_as_regular_2d_frame_with_live_preview():
    project = ProjectDatabase()
    project.units = {"length": "m", "force": "kN", "time": "s"}
    wizard = FrameWizard(project)
    try:
        assert wizard.dimension.currentData() == "2D"
        assert wizard.x_bays.value() == 3
        assert wizard.storeys.value() == 3
        assert not wizard.y_bays.isEnabled()
        assert not wizard.y_spacing.isEnabled()
        assert not wizard.create_beams_y.isEnabled()
        assert wizard.base_support.isEnabled()
        assert wizard.preview.objectName() == "frame-wizard-live-preview"
        assert "Nodes: 16" in wizard.summary.text()
        assert "Columns: 12" in wizard.summary.text()
        assert "X beams: 9" in wizard.summary.text()

        spec = wizard.spec()
        assert spec.planar_2d
        assert spec.nx == 3
        assert spec.nz == 3
        assert spec.dx == 5.0
        assert spec.dz == 3.5
        assert spec.create_columns
        assert spec.create_beams_x
        assert not spec.create_beams_y
        assert spec.planar_base_support == "Fixed"
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_switches_to_3d_and_updates_counts_and_spec():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.x_bays.setValue(2)
        wizard.y_bays.setValue(2)
        wizard.storeys.setValue(2)
        _APP.processEvents()

        assert wizard.y_bays.isEnabled()
        assert wizard.y_spacing.isEnabled()
        assert wizard.create_beams_y.isEnabled()
        assert not wizard.base_support.isEnabled()
        assert wizard.create_beams_y.isChecked()
        assert "Nodes: 27" in wizard.summary.text()
        assert "Columns: 18" in wizard.summary.text()
        assert "X beams: 12" in wizard.summary.text()
        assert "Y beams: 12" in wizard.summary.text()
        assert "Total frame elements: 42" in wizard.summary.text()

        spec = wizard.spec()
        assert not spec.planar_2d
        assert (spec.nx, spec.ny, spec.nz) == (2, 2, 2)
        assert spec.create_beams_y
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_geometry_page_is_scrollable():
    wizard = FrameWizard(ProjectDatabase())
    try:
        assert wizard.geometry_scroll.widgetResizable()
        assert (
            wizard.geometry_scroll.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert wizard.geometry_scroll.widget() is not None
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_main_window_exposes_frame_wizard_action_and_handler():
    source = inspect.getsource(MainWindow._show_frame_wizard)
    assert "FrameWizard(self.project" in source
    assert "dialog.spec()" in source
    assert "self._generate_frame_grid(spec)" in source

    window = MainWindow()
    try:
        assert "frame_wizard" in window.actions
        assert window.actions["frame_wizard"].text() == "Frame Wizard"
        assert window.actions["frame_wizard"].isEnabled()
    finally:
        window.close()
        window.deleteLater()
        _APP.processEvents()
