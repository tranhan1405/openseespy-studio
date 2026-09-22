from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    SurfaceGeometryData,
)
from openseespy_studio.surface_mesher import (
    mesh_surface_geometry,
    rectangle_surface_points,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog
from openseespy_studio.ui.viewport import ModelViewport


def _shell_section() -> SectionData:
    return SectionData(
        7,
        "Surface shell",
        "ElasticMembranePlate",
        parameters={
            "E": 30.0e9,
            "nu": 0.2,
            "h": 0.18,
            "rho": 0.0,
            "EpModifier": 1.0,
        },
    )


def _project() -> ProjectDatabase:
    project = ProjectDatabase(name="surface-geometry")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_shell_section())
    return project


def test_surface_geometry_round_trip_is_independent_of_fe_mesh():
    project = _project()
    surface = SurfaceGeometryData(
        tag=1,
        name="Slab A",
        surface_type="Rectangle",
        points=rectangle_surface_points(
            (0.0, 0.0, 3.0),
            6.0,
            4.0,
            plane="XY",
        ),
        section_tag=7,
        mesh_mode="target_size",
        target_size=0.5,
    )
    project.add_surface(surface)

    assert project.model.nodes == {}
    assert project.model.elements == {}

    restored = ProjectDatabase.from_dict(project.to_dict())

    restored_surface = restored.surfaces[1]
    assert restored_surface.name == "Slab A"
    assert restored_surface.surface_type == "Rectangle"
    for restored_point, source_point in zip(
        restored_surface.points,
        surface.points,
    ):
        assert restored_point == pytest.approx(source_point)
    assert restored_surface.section_tag == 7
    assert restored_surface.mesh_mode == "target_size"
    assert restored_surface.target_size == pytest.approx(0.5)
    assert restored.model.nodes == {}
    assert restored.model.elements == {}


def test_rectangle_surface_points_support_structural_working_planes():
    xy = rectangle_surface_points((1, 2, 3), 4, 5, plane="XY")
    xz = rectangle_surface_points((1, 2, 3), 4, 5, plane="XZ")
    yz = rectangle_surface_points((1, 2, 3), 4, 5, plane="YZ")

    assert xy == (
        (1.0, 2.0, 3.0),
        (5.0, 2.0, 3.0),
        (5.0, 7.0, 3.0),
        (1.0, 7.0, 3.0),
    )
    assert xz == (
        (1.0, 2.0, 3.0),
        (5.0, 2.0, 3.0),
        (5.0, 2.0, 8.0),
        (1.0, 2.0, 8.0),
    )
    assert yz == (
        (1.0, 2.0, 3.0),
        (1.0, 6.0, 3.0),
        (1.0, 6.0, 8.0),
        (1.0, 2.0, 8.0),
    )


def test_surface_geometry_generates_mapped_quad_shell_mesh():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            tag=1,
            name="Panel",
            surface_type="Rectangle",
            points=rectangle_surface_points(
                (0.0, 0.0, 0.0),
                2.0,
                1.0,
            ),
            section_tag=7,
            divisions_u=2,
            divisions_v=1,
        )
    )

    result = mesh_surface_geometry(project, 1)

    assert result.divisions_u == 2
    assert result.divisions_v == 1
    assert len(result.element_tags) == 2
    assert len(project.model.elements) == 2
    assert len(project.model.nodes) == 6
    assert project.surfaces[1].generated_element_tags == result.element_tags
    assert set(project.surfaces[1].generated_node_tags) <= set(
        project.model.nodes
    )
    assert all(
        project.model.elements[tag].group == "surface:1"
        for tag in result.element_tags
    )


def test_adjacent_geometry_surfaces_reuse_conforming_shared_edge_nodes():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            tag=1,
            name="Left",
            points=rectangle_surface_points((0, 0, 0), 1, 1),
            section_tag=7,
            divisions_u=1,
            divisions_v=2,
        )
    )
    project.add_surface(
        SurfaceGeometryData(
            tag=2,
            name="Right",
            points=rectangle_surface_points((1, 0, 0), 1, 1),
            section_tag=7,
            divisions_u=1,
            divisions_v=3,
        )
    )

    mesh_surface_geometry(project, 1)
    right = mesh_surface_geometry(project, 2)

    assert right.divisions_v == 2
    assert right.conformed_v is True
    shared_midpoints = [
        node.tag
        for node in project.model.nodes.values()
        if node.xyz == pytest.approx((1.0, 0.5, 0.0))
    ]
    assert len(shared_midpoints) == 1


def test_surface_geometry_ui_routes_keep_geometry_separate_from_shell_elements():
    dialog_source = inspect.getsource(SurfaceGeometryDialog)
    tree_source = inspect.getsource(MainWindow._refresh_tree)
    context_source = inspect.getsource(MainWindow._show_tree_context_menu)
    create_source = inspect.getsource(MainWindow._create_surface_geometry)
    mesh_source = inspect.getsource(MainWindow._mesh_surface_geometry)

    assert "Rectangle" in dialog_source
    assert "Quad" in dialog_source
    assert "Geometry is stored independently" in dialog_source
    assert "surface_geometry" in tree_source
    assert "New Surface Geometry..." in context_source
    assert "Mesh Surface Geometry..." in context_source
    assert "add_surface" in create_source
    assert "mesh_surface_geometry" in mesh_source


def test_surface_geometry_is_primary_shell_preprocessing_route():
    build_source = inspect.getsource(MainWindow._build_actions_and_ribbon)
    tree_source = inspect.getsource(MainWindow._refresh_tree)
    context_source = inspect.getsource(MainWindow._show_tree_context_menu)
    direct_source = inspect.getsource(MainWindow._create_shell)

    assert '"surface_geometry"' in build_source
    assert '"Surface Geometry..."' in build_source
    assert 'actions["shell_mesh"]' not in build_source
    assert '"shell_input"' in build_source
    assert '"Direct Shell Element..."' in build_source

    assert "Surface Geometry (" in tree_source
    assert "geometry /" not in tree_source

    assert "Legacy:" not in context_source
    assert "New Shell / Surface..." not in context_source
    assert "Mesh Shell Surface..." not in context_source
    assert "New Direct Shell Element..." in context_source
    assert "New Surface Geometry..." in context_source

    pressure_source = inspect.getsource(
        MainWindow._create_shell_pressure
    )
    recorder_source = inspect.getsource(
        MainWindow._recorder_target_creator
    )
    result_source = inspect.getsource(
        MainWindow._prepare_solution_result_prerequisites
    )

    assert "Direct Shell Element" in direct_source
    assert "_create_surface_geometry_and_mesh" in pressure_source
    assert "_create_surface_geometry_and_mesh" in recorder_source
    assert "_create_surface_geometry_and_mesh" in result_source
    assert "Create & Mesh Surface Now..." in pressure_source


def test_unmeshed_surface_geometry_is_rendered_in_viewport():
    draw_source = inspect.getsource(ModelViewport.draw_model)
    render_source = inspect.getsource(ModelViewport._render_model)
    refresh_source = inspect.getsource(MainWindow._refresh_all)
    tree_selection_source = inspect.getsource(
        MainWindow._tree_selection_changed
    )

    assert "surfaces:" in draw_source
    assert "self._surfaces" in draw_source
    assert "surface-geometry-" in render_source
    assert "not self._model.nodes and not self._surfaces" in render_source
    assert "self.project.surfaces" in refresh_source
    assert 'kind == "surface_geometry"' in tree_selection_source
    assert "_show_surface_geometry_properties" in tree_selection_source
