from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.project import (
    PointGeometryData,
    SectionData,
    TransformationData,
)
from openseespy_studio.ui.line_geometry_dialog import LineGeometryDialog
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog
from openseespy_studio.ui.viewport import ModelViewport


_APP = QApplication.instance() or QApplication([])


def _points():
    return {
        1: PointGeometryData(1, "P1", (0.0, 0.0, 0.0)),
        2: PointGeometryData(2, "P2", (2.0, 0.0, 0.0)),
        3: PointGeometryData(3, "P3", (2.0, 1.0, 0.0)),
        4: PointGeometryData(4, "P4", (0.0, 1.0, 0.0)),
    }


def test_line_dialog_accepts_picked_point_seeds():
    dialog = LineGeometryDialog(
        next_tag=1,
        points=_points(),
        sections={1: SectionData(1, "S", "Elastic")},
        transformations={
            1: TransformationData(1, "T", "Linear")
        },
        materials={},
        initial_point_i=2,
        initial_point_j=4,
    )
    try:
        assert dialog.point_i.currentData() == 2
        assert dialog.point_j.currentData() == 4
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_surface_dialog_uses_picked_corners_as_quad():
    points = _points()
    corners = tuple(points[tag].xyz for tag in (1, 2, 3, 4))
    dialog = SurfaceGeometryDialog(
        next_tag=1,
        sections={},
        initial_points=corners,
    )
    try:
        assert dialog.surface_type.currentText() == "Quad"
        assert tuple(
            tuple(spin.value() for spin in row)
            for row in dialog.quad_spins
        ) == corners
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_viewport_geometry_mode_exposes_geometry_point_picker():
    render_source = inspect.getsource(ModelViewport._render_model)
    pick_source = inspect.getsource(ModelViewport.pick_entity)

    assert "self._geometry_point_tags = sorted(self._points)" in render_source
    assert "self._point_picker.AddPickList" in render_source
    assert '"geometry_point"' in pick_source
    assert 'self._display_domain == "geometry"' in pick_source


def test_main_window_has_line_and_surface_geometry_pick_workflows():
    actions = inspect.getsource(MainWindow._build_actions_and_ribbon)
    click = inspect.getsource(MainWindow._viewport_entity_clicked)
    line_tool = inspect.getsource(
        MainWindow._activate_geometry_line_pick_tool
    )
    surface_tool = inspect.getsource(
        MainWindow._activate_geometry_surface_pick_tool
    )

    assert '"line_geometry_pick"' in actions
    assert '"surface_geometry_pick"' in actions
    assert "_create_line_geometry_from_points" in click
    assert "_create_surface_geometry_from_points" in click
    assert 'kind != "geometry_point"' in click
    assert 'set_display_domain("geometry")' in line_tool
    assert 'set_display_domain("geometry")' in surface_tool


def test_surface_pick_collects_four_distinct_geometry_points():
    source = inspect.getsource(MainWindow._viewport_entity_clicked)

    assert "self._geometry_surface_point_tags.append(point_tag)" in source
    assert "if point_tag in self._geometry_surface_point_tags" in source
    assert "if count < 4" in source
    assert "closed=(count == 4)" in source

def test_geometry_grid_snap_rounds_to_nearest_visible_intersection():
    class StubViewport:
        def _geometry_sketch_grid_spec(self):
            return {
                "spacing": 1.0,
                "start_u": -5.0,
                "end_u": 5.0,
                "start_v": -5.0,
                "end_v": 5.0,
            }

        def geometry_world_to_local(self, xyz):
            return float(xyz[0]), float(xyz[1])

        def geometry_local_to_world(self, u, v):
            return float(u), float(v), 7.0

    snapped = ModelViewport.geometry_sketch_grid_snap(
        StubViewport(),
        (1.86, 3.08, 7.0),
    )

    assert snapped == ((2.0, 3.0, 7.0), 1.0)


def test_geometry_grid_snap_rejects_points_outside_visible_grid():
    class StubViewport:
        def _geometry_sketch_grid_spec(self):
            return {
                "spacing": 1.0,
                "start_u": -2.0,
                "end_u": 2.0,
                "start_v": -2.0,
                "end_v": 2.0,
            }

        def geometry_world_to_local(self, xyz):
            return float(xyz[0]), float(xyz[1])

        def geometry_local_to_world(self, u, v):
            return float(u), float(v), 0.0

    assert ModelViewport.geometry_sketch_grid_snap(
        StubViewport(),
        (3.2, 0.1, 0.0),
    ) is None


def test_main_window_geometry_snap_includes_grid_intersections():
    source = inspect.getsource(MainWindow._geometry_sketch_snap)

    assert '"geometry_sketch_grid_snap"' in source
    assert '"kind": "grid"' in source
    assert "14.0 * 14.0" in source

