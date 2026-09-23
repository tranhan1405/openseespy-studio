from __future__ import annotations

import inspect
from types import SimpleNamespace

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport


class _ViewportStub:
    def geometry_world_to_screen(self, xyz):
        return float(xyz[0]), float(xyz[1])


def _measure_stub(base_snap):
    point_i = SimpleNamespace(xyz=(0.0, 0.0, 0.0))
    point_j = SimpleNamespace(xyz=(10.0, 0.0, 0.0))
    line = SimpleNamespace(point_i=1, point_j=2)
    return SimpleNamespace(
        _geometry_sketch_snap=lambda payload: dict(base_snap),
        project=SimpleNamespace(
            points={1: point_i, 2: point_j},
            lines={7: line},
        ),
        viewport=_ViewportStub(),
        _measure_first_xyz=None,
        _geometry_point_on_active_sketch_plane=lambda xyz: True,
    )


def test_measure_snap_prefers_nearest_geometry_line_over_free_cursor():
    window = _measure_stub(
        {
            "xyz": (4.0, 3.0, 0.0),
            "kind": "free",
            "label": "Free",
            "point_tag": None,
            "line_tags": (),
        }
    )

    result = MainWindow._geometry_measure_snap(
        window,
        {
            "world": (4.0, 3.0, 0.0),
            "screen": (4.0, 3.0),
        },
    )

    assert result is not None
    assert result["kind"] == "line_nearest"
    assert result["line_tags"] == (7,)
    assert result["xyz"] == (4.0, 0.0, 0.0)


def test_measure_snap_keeps_topology_snap_priority():
    midpoint = {
        "xyz": (5.0, 0.0, 0.0),
        "kind": "midpoint",
        "label": "Midpoint L7",
        "point_tag": None,
        "line_tags": (7,),
    }
    window = _measure_stub(midpoint)

    result = MainWindow._geometry_measure_snap(
        window,
        {
            "world": (5.0, 2.0, 0.0),
            "screen": (5.0, 2.0),
        },
    )

    assert result == midpoint


def test_measure_snap_keeps_closer_grid_over_nearest_line():
    grid = {
        "xyz": (4.0, 4.0, 0.0),
        "kind": "grid",
        "label": "Grid",
        "point_tag": None,
        "line_tags": (),
    }
    window = _measure_stub(grid)

    result = MainWindow._geometry_measure_snap(
        window,
        {
            "world": (4.0, 3.0, 0.0),
            "screen": (4.0, 3.0),
        },
    )

    assert result == grid


def test_measure_tool_has_hover_signal_and_dedicated_interaction_mode():
    source = inspect.getsource(ModelViewport.set_interaction_tool)
    event_source = inspect.getsource(ModelViewport.eventFilter)

    assert '"measure"' in source
    assert "self.measure_moved.emit" in event_source


def test_measure_geometry_uses_shared_snap_engine_and_hover_preview():
    point_source = inspect.getsource(
        MainWindow._measurement_point_from_payload
    )
    hover_source = inspect.getsource(MainWindow._viewport_measure_moved)

    assert "self._geometry_measure_snap(payload)" in point_source
    assert "self._geometry_measure_snap(payload)" in hover_source
    assert "show_measure_snap_preview" in hover_source
