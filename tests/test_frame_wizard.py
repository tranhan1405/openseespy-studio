from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from openseespy_studio.generator import (
    FrameGridSpec,
    frame_grid_coordinates,
    generate_frame_grid,
    validate_frame_grid_spec,
)
from openseespy_studio.model import StructuralModel
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
    handler = inspect.getsource(MainWindow._show_frame_wizard)
    actions = inspect.getsource(MainWindow._build_actions)
    assert "FrameWizard(self.project" in handler
    assert "dialog.spec()" in handler
    assert "self._generate_frame_grid(spec)" in handler
    assert '"frame_wizard"' in actions
    assert '"Frame Wizard"' in actions

def _set_spacing(editor, row: int, value: float) -> None:
    widget = editor.cellWidget(row, 0)
    assert widget is not None
    widget.setValue(value)


def test_frame_wizard_individual_spacing_and_origin_flow_to_spec():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.spacing_mode.setCurrentIndex(
            wizard.spacing_mode.findData("Individual")
        )
        wizard.x_bays.setValue(3)
        wizard.y_bays.setValue(2)
        wizard.storeys.setValue(3)

        for row, value in enumerate((4.0, 5.5, 6.0)):
            _set_spacing(wizard.x_spacing_editor, row, value)
        for row, value in enumerate((3.0, 4.5)):
            _set_spacing(wizard.y_spacing_editor, row, value)
        for row, value in enumerate((3.2, 3.4, 3.8)):
            _set_spacing(wizard.z_spacing_editor, row, value)

        wizard.origin_x.setValue(10.0)
        wizard.origin_y.setValue(-2.0)
        wizard.origin_z.setValue(1.5)
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.x_bay_widths == (4.0, 5.5, 6.0)
        assert spec.y_bay_widths == (3.0, 4.5)
        assert spec.storey_heights == (3.2, 3.4, 3.8)
        assert (spec.origin_x, spec.origin_y, spec.origin_z) == (
            10.0,
            -2.0,
            1.5,
        )

        x, y, z = frame_grid_coordinates(spec)
        assert x == [10.0, 14.0, 19.5, 25.5]
        assert y == [-2.0, 1.0, 5.5]
        assert z == pytest.approx([1.5, 4.7, 8.1, 11.9])
        assert "overall X=15.5" in wizard.summary.text()
        assert "Y=7.5" in wizard.summary.text()
        assert "H=10.4" in wizard.summary.text()
        assert "Geometry ready" in wizard.validation_status.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_generate_frame_grid_uses_individual_coordinates_in_2d():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=2,
        dx=5.0,
        dy=6.0,
        dz=3.5,
        x_bay_widths=(4.0, 6.0),
        storey_heights=(3.0, 4.0),
        origin_x=10.0,
        origin_z=2.0,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        planar_base_support="Pinned",
    )
    generate_frame_grid(model, spec)

    coordinates = {
        (node.x, node.y, node.z)
        for node in model.nodes.values()
    }
    assert coordinates == {
        (10.0, 0.0, 2.0),
        (14.0, 0.0, 2.0),
        (20.0, 0.0, 2.0),
        (10.0, 0.0, 5.0),
        (14.0, 0.0, 5.0),
        (20.0, 0.0, 5.0),
        (10.0, 0.0, 9.0),
        (14.0, 0.0, 9.0),
        (20.0, 0.0, 9.0),
    }
    base = [
        node
        for node in model.nodes.values()
        if node.xyz[2] == 2.0
    ]
    assert len(base) == 3
    assert all(node.fixity == (1, 1, 1, 1, 0, 1) for node in base)


def test_generate_frame_grid_uses_individual_coordinates_in_3d():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=2,
        ny=2,
        nz=1,
        x_bay_widths=(4.0, 6.0),
        y_bay_widths=(3.0, 7.0),
        storey_heights=(3.5,),
        origin_x=1.0,
        origin_y=2.0,
        origin_z=-1.0,
    )
    generate_frame_grid(model, spec)

    coordinates = {
        (node.x, node.y, node.z)
        for node in model.nodes.values()
    }
    assert (1.0, 2.0, -1.0) in coordinates
    assert (11.0, 12.0, 2.5) in coordinates
    assert len(model.nodes) == 18
    assert len(model.elements) == 21


def test_frame_grid_validation_rejects_bad_individual_spacing_and_empty_members():
    bad_count = FrameGridSpec(
        nx=3,
        x_bay_widths=(4.0, 5.0),
    )
    try:
        validate_frame_grid_spec(bad_count)
    except ValueError as exc:
        assert "spacing count" in str(exc)
    else:
        raise AssertionError("Expected bad spacing count to fail")

    no_members = FrameGridSpec(
        planar_2d=True,
        create_columns=False,
        create_beams_x=False,
        create_beams_y=False,
    )
    try:
        validate_frame_grid_spec(no_members)
    except ValueError as exc:
        assert "at least one member family" in str(exc)
    else:
        raise AssertionError("Expected empty frame topology to fail")


def test_frame_wizard_validation_blocks_empty_member_topology():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.create_columns.setChecked(False)
        wizard.create_beams_x.setChecked(False)
        wizard.create_beams_y.setChecked(False)
        _APP.processEvents()

        assert not wizard.validateCurrentPage()
        assert "at least one member family" in (
            wizard.validation_status.text()
        )
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()

