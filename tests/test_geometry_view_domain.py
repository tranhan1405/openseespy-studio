from __future__ import annotations

import inspect

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport


def test_tree_geometry_branch_switches_to_geometry_only_domain():
    source = inspect.getsource(MainWindow._tree_selection_changed)

    assert "geometry_tree_kinds" in source
    for kind in (
        "geometry_root",
        "points_root",
        "lines_root",
        "surfaces_root",
        "point_geometry",
        "line_geometry",
        "surface_geometry",
    ):
        assert f'"{kind}"' in source
    assert "self.viewport.set_display_domain(" in source
    assert '"geometry" if geometry_mode else "fe"' in source


def test_geometry_tree_selection_does_not_select_generated_fe_elements():
    source = inspect.getsource(MainWindow._tree_selection_changed)
    line_branch = source.split(
        'elif kind == "line_geometry":', 1
    )[1].split(
        'elif kind == "surface_geometry":', 1
    )[0]
    surface_branch = source.split(
        'elif kind == "surface_geometry":', 1
    )[1].split(
        'elif kind == "material":', 1
    )[0]

    assert "generated_element_tags" not in line_branch
    assert "generated_element_tags" not in surface_branch
    assert "elements.update" not in line_branch
    assert "elements.update" not in surface_branch


def test_viewport_domains_are_mutually_exclusive():
    setter = inspect.getsource(ModelViewport.set_display_domain)
    render = inspect.getsource(ModelViewport._render_model)

    assert '{"geometry", "fe"}' in setter
    assert 'self._display_domain == "geometry"' in render
    assert 'name="geometry-points"' in render
    assert 'name=f"line-geometry-{line_tag}"' in render
    assert 'name="surface-geometry"' in render
    assert '"surface_tag"' in render

    geometry_branch = render.split(
        'if self._display_domain == "geometry":', 1
    )[1].split(
        'if not self._model.nodes:', 1
    )[0]
    assert "self.plotter.render()" in geometry_branch
    assert "return" in geometry_branch

    fe_branch = render.split(
        'if not self._model.nodes:', 1
    )[1]
    assert 'name="geometry-points"' not in fe_branch
    assert 'line-geometry-' not in fe_branch
    assert 'name="surface-geometry"' not in fe_branch
