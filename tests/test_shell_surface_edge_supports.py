from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    SurfaceEdgeSupportData,
    SurfaceGeometryData,
)
from openseespy_studio.surface_mesher import (
    flip_surface_orientation,
    managed_surface_support_node_tags,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    remove_surface_edge_support,
    sync_surface_edge_support,
)
from openseespy_studio.ui.main_window import MainWindow


def _section(tag: int = 7) -> SectionData:
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
    project = ProjectDatabase(name="managed-edge-support")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_section())
    return project


def _meshed_project(*, divisions_u=2, divisions_v=2) -> ProjectDatabase:
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=rectangle_surface_points((0, 0, 0), 4, 2),
            section_tag=7,
            divisions_u=divisions_u,
            divisions_v=divisions_v,
        )
    )
    mesh_surface_geometry(project, 1)
    return project


def test_surface_edge_support_round_trips_with_geometry_reference():
    project = _meshed_project()
    support = SurfaceEdgeSupportData(
        1,
        "Bottom pinned",
        surface_tag=1,
        edge_index=1,
        fixity=(1, 1, 1, 0, 0, 0),
    )
    project.add_surface_edge_support(support)
    nodes = sync_surface_edge_support(project, 1)

    restored = ProjectDatabase.from_dict(project.to_dict())
    item = restored.surface_edge_supports[1]

    assert item.surface_tag == 1
    assert item.edge_index == 1
    assert item.fixity == (1, 1, 1, 0, 0, 0)
    assert item.generated_node_tags == nodes
    assert all(
        restored.model.nodes[tag].fixity == (1, 1, 1, 0, 0, 0)
        for tag in nodes
    )


def test_managed_edge_support_applies_to_all_ordered_edge_nodes():
    project = _meshed_project(divisions_u=4, divisions_v=1)
    support = SurfaceEdgeSupportData(
        1,
        "Bottom roller",
        1,
        1,
        fixity=(0, 0, 1, 0, 0, 0),
    )
    project.add_surface_edge_support(support)

    nodes = sync_surface_edge_support(project, 1)

    assert len(nodes) == 5
    assert set(nodes) == managed_surface_support_node_tags(project)
    assert all(
        project.model.nodes[tag].fixity[2] == 1
        for tag in nodes
    )


def test_remesh_rebinds_support_and_does_not_keep_old_support_only_nodes():
    project = _meshed_project(divisions_u=2, divisions_v=1)
    support = SurfaceEdgeSupportData(
        1,
        "Bottom fixed",
        1,
        1,
        fixity=(1, 1, 1, 1, 1, 1),
    )
    project.add_surface_edge_support(support)
    old_nodes = set(sync_surface_edge_support(project, 1))

    project.surfaces[1].divisions_u = 4
    remesh_surface_geometry(project, 1)
    new_nodes = set(project.surface_edge_supports[1].generated_node_tags)

    assert len(new_nodes) == 5
    assert new_nodes != old_nodes
    assert all(
        project.model.nodes[tag].fixity == (1, 1, 1, 1, 1, 1)
        for tag in new_nodes
    )
    stale = old_nodes - new_nodes
    assert all(
        tag not in project.model.nodes
        or project.model.nodes[tag].fixity == (0, 0, 0, 0, 0, 0)
        for tag in stale
    )


def test_flip_surface_preserves_physical_supported_edge():
    project = _meshed_project(divisions_u=3, divisions_v=2)
    support = SurfaceEdgeSupportData(
        1,
        "Bottom support",
        1,
        1,
        fixity=(0, 0, 1, 0, 0, 0),
    )
    project.add_surface_edge_support(support)
    before_nodes = sync_surface_edge_support(project, 1)
    before_xyz = {
        tuple(project.model.nodes[tag].xyz)
        for tag in before_nodes
    }

    flip_surface_orientation(project, 1)

    item = project.surface_edge_supports[1]
    after_xyz = {
        tuple(project.model.nodes[tag].xyz)
        for tag in item.generated_node_tags
    }
    assert item.edge_index == 4
    assert after_xyz == before_xyz
    assert all(
        project.model.nodes[tag].fixity[2] == 1
        for tag in item.generated_node_tags
    )


def test_remove_managed_support_releases_only_owned_dofs():
    project = _meshed_project(divisions_u=2, divisions_v=2)
    first = SurfaceEdgeSupportData(
        1,
        "Bottom UZ",
        1,
        1,
        fixity=(0, 0, 1, 0, 0, 0),
    )
    second = SurfaceEdgeSupportData(
        2,
        "Left UX",
        1,
        4,
        fixity=(1, 0, 0, 0, 0, 0),
    )
    project.add_surface_edge_support(first)
    project.add_surface_edge_support(second)
    sync_surface_edge_support(project, 1)
    sync_surface_edge_support(project, 2)
    shared_corner = set(first.generated_node_tags) & set(
        second.generated_node_tags
    )
    assert len(shared_corner) == 1

    remove_surface_edge_support(project, 1)

    corner = project.model.nodes[next(iter(shared_corner))]
    assert corner.fixity[0] == 1
    assert corner.fixity[2] == 0
    assert 1 not in project.surface_edge_supports


def test_surface_support_ui_and_manual_restraint_guard_are_exposed():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    manage = inspect.getsource(MainWindow._manage_surface_edge_support)
    remove = inspect.getsource(MainWindow._remove_surface_edge_support)
    guard = inspect.getsource(
        MainWindow._exclude_managed_surface_support_nodes
    )
    apply_restraint = inspect.getsource(MainWindow._apply_restraint)
    clear_restraint = inspect.getsource(MainWindow._clear_restraint)
    properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )

    assert "Managed Edge Support..." in context
    assert "Remove Managed Edge Support..." in context
    assert "SurfaceEdgeSupportData" in manage
    assert "sync_surface_edge_support" in manage
    assert "remove_surface_edge_support" in remove
    assert "managed_surface_support_node_tags" in guard
    assert "_exclude_managed_surface_support_nodes" in apply_restraint
    assert "_exclude_managed_surface_support_nodes" in clear_restraint
    assert "Managed edge supports" in properties


def test_update_managed_support_releases_old_fixity_dofs():
    from openseespy_studio.surface_mesher import replace_surface_edge_support

    project = _meshed_project(divisions_u=2, divisions_v=1)
    original = SurfaceEdgeSupportData(
        1,
        "Bottom fixed",
        1,
        1,
        fixity=(1, 1, 1, 1, 1, 1),
    )
    project.add_surface_edge_support(original)
    nodes = sync_surface_edge_support(project, 1)
    assert all(
        project.model.nodes[tag].fixity == (1, 1, 1, 1, 1, 1)
        for tag in nodes
    )

    updated = SurfaceEdgeSupportData(
        1,
        "Bottom UZ",
        1,
        1,
        fixity=(0, 0, 1, 0, 0, 0),
        generated_node_tags=list(nodes),
    )
    rebound = replace_surface_edge_support(project, updated)

    assert rebound == nodes
    assert all(
        project.model.nodes[tag].fixity == (0, 0, 1, 0, 0, 0)
        for tag in nodes
    )


def test_support_round_trip_validation_does_not_treat_itself_as_duplicate():
    project = _meshed_project()
    project.add_surface_edge_support(
        SurfaceEdgeSupportData(
            11,
            "Edge support",
            1,
            2,
            fixity=(1, 0, 0, 0, 0, 0),
        )
    )
    sync_surface_edge_support(project, 11)

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert list(restored.surface_edge_supports) == [11]
    assert restored.surface_edge_supports[11].edge_index == 2
