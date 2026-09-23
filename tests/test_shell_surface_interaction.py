from __future__ import annotations

import inspect
from inspect import signature

import pytest

from openseespy_studio.project import SurfaceGeometryData
from openseespy_studio.surface_mesher import rectangle_surface_points
from openseespy_studio.ui.load_dialogs import ElementLoadDialog
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport


def test_surface_axes_regular_xy_surface():
    surface = SurfaceGeometryData(
        1,
        "XY",
        points=rectangle_surface_points((0, 0, 0), 4, 2),
        section_tag=None,
    )

    axes = ModelViewport._surface_axes(surface)

    assert axes is not None
    center, local_x, local_y, normal, scale = axes
    assert center == pytest.approx((2.0, 1.0, 0.0))
    assert local_x == pytest.approx((1.0, 0.0, 0.0))
    assert local_y == pytest.approx((0.0, 1.0, 0.0))
    assert normal == pytest.approx((0.0, 0.0, 1.0))
    assert scale > 0.0


def test_surface_axes_projects_user_local_x_to_surface_plane():
    surface = SurfaceGeometryData(
        1,
        "Local X",
        points=rectangle_surface_points((0, 0, 0), 2, 1),
        section_tag=None,
        local_x=(1.0, 0.0, 1.0),
    )

    axes = ModelViewport._surface_axes(surface)

    assert axes is not None
    _center, local_x, _local_y, normal, _scale = axes
    assert local_x == pytest.approx((1.0, 0.0, 0.0))
    assert normal == pytest.approx((0.0, 0.0, 1.0))


def test_geometry_shell_mesh_overlay_is_non_pickable_and_geometry_only():
    setter = inspect.getsource(
        ModelViewport.set_geometry_mesh_overlay_visible
    )
    render = inspect.getsource(ModelViewport._render_model)

    assert "_geometry_mesh_overlay_visible" in setter
    assert 'self._display_domain == "geometry"' in setter
    assert '"geometry-shell-mesh-overlay"' in render
    assert 'style="wireframe"' in render
    assert "pickable=False" in render


def test_tree_surface_selection_drives_orientation_overlay():
    source = inspect.getsource(MainWindow._tree_selection_changed)

    assert "surface_geometry_tags" in source
    assert "show_surface_orientation" in source
    assert "clear_surface_orientation" in source


def test_element_load_dialog_supports_filtered_surface_pressure_mode():
    params = signature(ElementLoadDialog.__init__).parameters

    assert "allowed_load_types" in params

    source = inspect.getsource(ElementLoadDialog.__init__)
    assert '("Shell Surface Pressure (normal)", "SurfacePressure")' in source


def test_surface_pressure_route_expands_surface_to_generated_shell_elements():
    source = inspect.getsource(
        MainWindow._create_surface_pressure_for_surfaces
    )
    helper = inspect.getsource(
        MainWindow._create_shell_pressure_for_elements
    )
    context = inspect.getsource(MainWindow._show_tree_context_menu)

    assert "SurfacePressureData" in source
    assert "sync_surface_pressure" in source
    assert "replace_surface_pressure" in source
    assert 'allowed_load_types={"SurfacePressure"}' in helper
    assert "Managed Surface Pressure..." in context


def test_multi_surface_lifecycle_operations_are_atomic():
    remesh = inspect.getsource(
        MainWindow._remesh_surface_geometries
    )
    delete = inspect.getsource(
        MainWindow._delete_surface_meshes
    )
    flip = inspect.getsource(
        MainWindow._flip_surface_normals
    )

    for source in (remesh, delete, flip):
        assert "before = self.project.to_dict()" in source
        assert "ProjectDatabase.from_dict(before)" in source

    assert "remesh_surface_geometry" in remesh
    assert "delete_surface_mesh" in delete
    assert "flip_surface_orientation" in flip


def test_surface_context_exposes_multi_surface_and_fe_bridge():
    source = inspect.getsource(MainWindow._show_tree_context_menu)

    assert "_selected_surface_geometry_tags" in source
    assert 'if kind == "surface_mesh_recipe"' in source
    assert '"Generate Mesh"' in source
    assert '"Remesh"' in source
    assert 'menu.addAction("Delete Generated Mesh")' in source
    assert '"Flip Surface Normal"' in source
    assert "Flip Normals (" in source
    assert "Select Generated FE" in source
    assert "_select_generated_fe_for_surfaces" in source
    assert "surface_mesh_overlay" in source


def test_generated_fe_bridge_switches_from_geometry_to_fe_domain():
    source = inspect.getsource(
        MainWindow._select_generated_fe_for_surfaces
    )

    assert 'set_display_domain("fe")' in source
    assert "self.selection.set_selection(elements=element_tags)" in source
    assert "generated_element_tags" in source
