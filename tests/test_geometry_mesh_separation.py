from __future__ import annotations

import inspect

import pytest

from openseespy_studio.line_mesher import mesh_line_geometry
from openseespy_studio.project import (
    LineGeometryData,
    PointGeometryData,
    ProjectDatabase,
    SectionData,
    SurfaceGeometryData,
    TransformationData,
)
from openseespy_studio.surface_mesher import mesh_surface_geometry
from openseespy_studio.ui.line_geometry_dialog import LineGeometryDialog
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog


def _base_project() -> ProjectDatabase:
    project = ProjectDatabase(name="geometry-mesh-separation")
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "B", (4.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(3, "C", (4.0, 3.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (0.0, 3.0, 0.0)))
    return project


def test_unconfigured_line_is_valid_geometry_but_cannot_mesh():
    project = _base_project()
    line = LineGeometryData(
        1,
        "Geometry only",
        1,
        2,
        mesh_recipe_configured=False,
    )

    project.add_line(line)

    assert project.lines[1].mesh_recipe_configured is False
    assert project.model.nodes == {}
    assert project.model.elements == {}
    with pytest.raises(ValueError, match="no Mesh recipe"):
        mesh_line_geometry(project, 1)


def test_line_can_be_configured_later_then_meshed():
    project = _base_project()
    project.add_section(SectionData(1, "Beam", "Elastic"))
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )
    project.add_line(
        LineGeometryData(
            1,
            "Geometry first",
            1,
            2,
            mesh_recipe_configured=False,
        )
    )

    configured = LineGeometryData.from_dict(
        {
            **project.lines[1].to_dict(),
            "mesh_recipe_configured": True,
            "divisions": 4,
            "section_tag": 1,
            "transformation_tag": 1,
        }
    )
    project.update_line(1, configured)
    result = mesh_line_geometry(project, 1)

    assert len(result.element_tags) == 4
    assert project.lines[1].mesh_recipe_configured is True


def test_unconfigured_surface_is_valid_geometry_but_cannot_mesh():
    project = _base_project()
    surface = SurfaceGeometryData(
        1,
        "Geometry only",
        points=(
            (0.0, 0.0, 0.0),
            (4.0, 0.0, 0.0),
            (4.0, 3.0, 0.0),
            (0.0, 3.0, 0.0),
        ),
        corner_point_tags=(1, 2, 3, 4),
        mesh_recipe_configured=False,
        section_tag=None,
    )

    project.add_surface(surface)

    assert project.surfaces[1].mesh_recipe_configured is False
    assert project.model.nodes == {}
    assert project.model.elements == {}
    with pytest.raises(ValueError, match="no Mesh recipe"):
        mesh_surface_geometry(project, 1)


def test_geometry_mesh_recipe_flag_roundtrips_and_legacy_defaults_true():
    line = LineGeometryData(
        1,
        "L",
        1,
        2,
        mesh_recipe_configured=False,
    )
    surface = SurfaceGeometryData(
        1,
        "S",
        mesh_recipe_configured=False,
        section_tag=None,
    )

    assert LineGeometryData.from_dict(
        line.to_dict()
    ).mesh_recipe_configured is False
    assert SurfaceGeometryData.from_dict(
        surface.to_dict()
    ).mesh_recipe_configured is False

    legacy_line = line.to_dict()
    legacy_line.pop("mesh_recipe_configured")
    legacy_surface = surface.to_dict()
    legacy_surface.pop("mesh_recipe_configured")
    assert LineGeometryData.from_dict(
        legacy_line
    ).mesh_recipe_configured is True
    assert SurfaceGeometryData.from_dict(
        legacy_surface
    ).mesh_recipe_configured is True


def test_create_geometry_workflows_do_not_generate_fe_immediately():
    create_line = inspect.getsource(
        MainWindow._create_line_geometry_from_points
    )
    create_surface = inspect.getsource(
        MainWindow._create_surface_geometry_from_points
    )

    assert 'mode="geometry"' in create_line
    assert "mesh_line_geometry" not in create_line
    assert 'mode="geometry"' in create_surface
    assert "mesh_surface_geometry" not in create_surface


def test_mesh_tree_and_dedicated_configure_workflows_are_exposed():
    refresh_tree = inspect.getsource(MainWindow._refresh_tree)
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    configure_line = inspect.getsource(MainWindow._configure_line_mesh)
    configure_surface = inspect.getsource(MainWindow._configure_surface_mesh)
    line_dialog = inspect.getsource(LineGeometryDialog)
    surface_dialog = inspect.getsource(SurfaceGeometryDialog)

    assert 'QTreeWidgetItem(["Mesh"])' in refresh_tree
    assert '"line_mesh_recipe"' in refresh_tree
    assert '"surface_mesh_recipe"' in refresh_tree
    assert 'if kind == "line_mesh_recipe"' in context
    assert 'if kind == "surface_mesh_recipe"' in context
    assert 'mode="mesh"' in configure_line
    assert 'mode="mesh"' in configure_surface
    assert "Create Geometry" in line_dialog
    assert "Create Geometry" in surface_dialog
    assert "Save Mesh Recipe" in line_dialog
    assert "Save Mesh Recipe" in surface_dialog
