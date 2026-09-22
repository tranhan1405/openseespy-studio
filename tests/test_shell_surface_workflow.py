from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    PointGeometryData,
    ProjectDatabase,
    SectionData,
    SelectionSetData,
    SurfaceGeometryData,
)
from openseespy_studio.shell_quality import (
    shell_element_quality,
    shell_mesh_quality_summary,
)
from openseespy_studio.surface_mesher import (
    delete_surface_mesh,
    flip_surface_orientation,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    surface_unit_normal,
)
from openseespy_studio.ui.main_window import MainWindow


def _shell_section(tag: int = 7) -> SectionData:
    return SectionData(
        tag,
        "Shell",
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
    project = ProjectDatabase(name="surface-shell-workflow")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_shell_section())
    return project


def test_surface_keeps_geometry_point_topology_and_tracks_unmeshed_moves():
    project = _project()
    project.add_point(PointGeometryData(1, "P1", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "P2", (2.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(3, "P3", (2.0, 1.0, 0.0)))
    project.add_point(PointGeometryData(4, "P4", (0.0, 1.0, 0.0)))

    surface = SurfaceGeometryData(
        1,
        "Panel",
        points=(
            (99.0, 99.0, 99.0),
            (98.0, 99.0, 99.0),
            (98.0, 98.0, 99.0),
            (99.0, 98.0, 99.0),
        ),
        section_tag=7,
        corner_point_tags=(1, 2, 3, 4),
    )
    project.add_surface(surface)

    assert project.surfaces[1].points == (
        project.points[1].xyz,
        project.points[2].xyz,
        project.points[3].xyz,
        project.points[4].xyz,
    )

    project.update_point(
        2,
        PointGeometryData(20, "P2 moved", (3.0, 0.0, 0.0)),
    )
    assert project.surfaces[1].corner_point_tags == (1, 20, 3, 4)
    assert project.surfaces[1].points[1] == (3.0, 0.0, 0.0)

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.surfaces[1].corner_point_tags == (1, 20, 3, 4)
    assert restored.surfaces[1].points[1] == (3.0, 0.0, 0.0)

    with pytest.raises(ValueError, match=r"Surface\(s\)"):
        restored.remove_point(20)


def test_meshed_surface_blocks_moving_geometry_corner_point():
    project = _project()
    for tag, xyz in {
        1: (0.0, 0.0, 0.0),
        2: (2.0, 0.0, 0.0),
        3: (2.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
    }.items():
        project.add_point(PointGeometryData(tag, f"P{tag}", xyz))
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=tuple(project.points[tag].xyz for tag in (1, 2, 3, 4)),
            section_tag=7,
            corner_point_tags=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=1,
        )
    )
    mesh_surface_geometry(project, 1)

    with pytest.raises(ValueError, match=r"meshed Surface"):
        project.update_point(
            2,
            PointGeometryData(2, "P2", (3.0, 0.0, 0.0)),
        )


def test_delete_surface_mesh_keeps_geometry_and_shared_fe_nodes():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Left",
            points=rectangle_surface_points((0, 0, 0), 1, 1),
            section_tag=7,
            divisions_u=1,
            divisions_v=2,
        )
    )
    project.add_surface(
        SurfaceGeometryData(
            2,
            "Right",
            points=rectangle_surface_points((1, 0, 0), 1, 1),
            section_tag=7,
            divisions_u=1,
            divisions_v=2,
        )
    )
    left = mesh_surface_geometry(project, 1)
    right = mesh_surface_geometry(project, 2)

    shared = set(left.corner_node_tags) | set(left.created_node_tags)
    shared &= set(
        node
        for tag in right.element_tags
        for node in project.model.elements[tag].node_tags()
    )
    assert shared

    deleted = delete_surface_mesh(project, 1)

    assert 1 in project.surfaces
    assert project.surfaces[1].generated_element_tags == []
    assert all(
        tag not in project.model.elements
        for tag in deleted.removed_element_tags
    )
    assert shared <= set(project.model.nodes)
    assert shared <= set(deleted.kept_node_tags)
    assert all(tag in project.model.elements for tag in right.element_tags)


def test_delete_surface_mesh_refuses_named_selection_dependency():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=rectangle_surface_points((0, 0, 0), 2, 1),
            section_tag=7,
        )
    )
    mesh = mesh_surface_geometry(project, 1)
    project.selection_sets["shell-set"] = SelectionSetData(
        "shell-set",
        element_tags={mesh.element_tags[0]},
    )

    with pytest.raises(ValueError, match=r"named selection"):
        delete_surface_mesh(project, 1)

    assert all(tag in project.model.elements for tag in mesh.element_tags)


def test_remesh_surface_replaces_generated_mesh_atomically():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=rectangle_surface_points((0, 0, 0), 3, 1),
            section_tag=7,
            divisions_u=1,
            divisions_v=1,
        )
    )
    first = mesh_surface_geometry(project, 1)
    assert len(first.element_tags) == 1

    project.surfaces[1].divisions_u = 3
    result = remesh_surface_geometry(project, 1)

    assert len(result.deleted.removed_element_tags) == 1
    assert result.mesh.divisions_u == 3
    assert len(result.mesh.element_tags) == 3
    assert project.surfaces[1].generated_element_tags == result.mesh.element_tags


def test_surface_advanced_asdshell_settings_propagate_to_generated_elements():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Advanced",
            points=rectangle_surface_points((0, 0, 0), 2, 1),
            section_tag=7,
            formulation="ASDShellQ4",
            corotational=True,
            local_x=(1.0, 0.0, 0.0),
            no_eas=True,
            drilling_stab=0.15,
            drilling_nl=True,
            divisions_u=2,
            divisions_v=1,
        )
    )

    result = mesh_surface_geometry(project, 1)

    for tag in result.element_tags:
        element = project.model.elements[tag]
        assert element.shell_corotational is True
        assert element.shell_local_x == (1.0, 0.0, 0.0)
        assert element.shell_no_eas is True
        assert element.shell_drilling_stab == pytest.approx(0.15)
        assert element.shell_drilling_nl is True

    restored = ProjectDatabase.from_dict(project.to_dict())
    surface = restored.surfaces[1]
    assert surface.corotational is True
    assert surface.local_x == (1.0, 0.0, 0.0)
    assert surface.no_eas is True
    assert surface.drilling_stab == pytest.approx(0.15)
    assert surface.drilling_nl is True


def test_non_asdshell_surface_clears_asd_only_settings():
    surface = SurfaceGeometryData(
        1,
        "MITC",
        points=rectangle_surface_points((0, 0, 0), 1, 1),
        section_tag=7,
        formulation="ShellMITC4",
        corotational=True,
        local_x=(1.0, 0.0, 0.0),
        no_eas=True,
        drilling_stab=0.2,
        drilling_nl=True,
    )
    assert surface.corotational is False
    assert surface.local_x is None
    assert surface.no_eas is False
    assert surface.drilling_stab is None
    assert surface.drilling_nl is False


def test_flip_surface_normal_reverses_winding_and_remeshes():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=rectangle_surface_points((0, 0, 0), 2, 1),
            section_tag=7,
            divisions_u=2,
            divisions_v=1,
        )
    )
    first = mesh_surface_geometry(project, 1)
    before = surface_unit_normal(project.surfaces[1])
    assert before[2] > 0.0

    remeshed = flip_surface_orientation(project, 1)

    after = surface_unit_normal(project.surfaces[1])
    assert after[2] < 0.0
    assert after == pytest.approx(tuple(-value for value in before))
    assert remeshed is not None
    assert len(remeshed.element_tags) == len(first.element_tags)


def test_shell_quality_regular_quad_and_distorted_quad_metrics():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Square",
            points=rectangle_surface_points((0, 0, 0), 1, 1),
            section_tag=7,
            divisions_u=1,
            divisions_v=1,
        )
    )
    square = mesh_surface_geometry(project, 1)
    quality = shell_element_quality(project, square.element_tags[0])

    assert quality.area == pytest.approx(1.0)
    assert quality.aspect_ratio == pytest.approx(1.0)
    assert quality.max_skew_deg == pytest.approx(0.0)
    assert quality.warpage_deg == pytest.approx(0.0)

    project.add_surface(
        SurfaceGeometryData(
            2,
            "Warped long",
            points=(
                (2.0, 0.0, 0.0),
                (12.0, 0.0, 0.0),
                (12.0, 1.0, 0.5),
                (2.0, 1.0, 0.0),
            ),
            section_tag=7,
            divisions_u=1,
            divisions_v=1,
        )
    )
    distorted = mesh_surface_geometry(project, 2)
    summary = shell_mesh_quality_summary(
        project,
        distorted.element_tags,
    )

    assert summary.element_count == 1
    assert summary.max_aspect_ratio > 5.0
    assert summary.max_warpage_deg > 0.0
    assert summary.heuristic_status == "Review recommended"


def test_surface_context_exposes_lifecycle_orientation_and_quality_tools():
    source = inspect.getsource(MainWindow._show_tree_context_menu)
    properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )

    assert "Properties / Mesh Quality" in source
    assert "Remesh Surface" in source
    assert "Delete Generated Mesh" in source
    assert "Flip Surface Normal" in source
    assert "_remesh_surface_geometry" in source
    assert "_delete_surface_mesh" in source
    assert "_flip_surface_normal" in source

    assert "Worst aspect ratio" in properties
    assert "Worst skew" in properties
    assert "Worst warpage" in properties
    assert "Corotational" in properties
    assert "Topology" in properties
