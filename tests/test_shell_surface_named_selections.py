from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    SelectionSetData,
    SurfaceGeometryData,
)
from openseespy_studio.surface_mesher import (
    delete_surface_geometry,
    delete_surface_mesh,
    managed_surface_selection_names,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    sync_selection_set_surface_scope,
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


def _project(*, divisions_u=2, divisions_v=2) -> ProjectDatabase:
    project = ProjectDatabase(name="managed-surface-selection")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_section())
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=rectangle_surface_points((0, 0, 0), 4, 2),
            section_tag=7,
            divisions_u=divisions_u,
            divisions_v=divisions_v,
            conform_existing_edges=False,
        )
    )
    mesh_surface_geometry(project, 1)
    return project


def test_managed_surface_named_selection_round_trips():
    project = _project()
    selection = SelectionSetData(
        "Panel scope",
        surface_tags={1},
        surface_scope_mode="nodes_and_elements",
    )
    project.add_selection_set(selection)

    assert selection.node_tags == set(
        project.surfaces[1].generated_node_tags
    )
    assert selection.element_tags == set(
        project.surfaces[1].generated_element_tags
    )
    assert managed_surface_selection_names(project) == {"Panel scope"}

    restored = ProjectDatabase.from_dict(project.to_dict())
    item = restored.selection_sets["Panel scope"]
    assert item.surface_tags == {1}
    assert item.surface_scope_mode == "nodes_and_elements"
    assert item.node_tags == set(restored.surfaces[1].generated_node_tags)
    assert item.element_tags == set(
        restored.surfaces[1].generated_element_tags
    )


@pytest.mark.parametrize(
    ("mode", "expect_nodes", "expect_elements"),
    [
        ("nodes", True, False),
        ("elements", False, True),
        ("nodes_and_elements", True, True),
    ],
)
def test_surface_named_selection_scope_modes(
    mode,
    expect_nodes,
    expect_elements,
):
    project = _project()
    selection = SelectionSetData(
        "Scope",
        surface_tags={1},
        surface_scope_mode=mode,
    )
    project.add_selection_set(selection)

    assert bool(selection.node_tags) is expect_nodes
    assert bool(selection.element_tags) is expect_elements


def test_remesh_rebinds_managed_named_selection_membership():
    project = _project(divisions_u=1, divisions_v=1)
    selection = SelectionSetData(
        "Panel scope",
        surface_tags={1},
        surface_scope_mode="nodes_and_elements",
    )
    project.add_selection_set(selection)

    project.surfaces[1].divisions_u = 3
    project.surfaces[1].divisions_v = 2
    remesh_surface_geometry(project, 1)

    item = project.selection_sets["Panel scope"]
    assert item.node_tags == set(
        project.surfaces[1].generated_node_tags
    )
    assert item.element_tags == set(
        project.surfaces[1].generated_element_tags
    )
    assert len(item.element_tags) == 6


def test_delete_mesh_keeps_geometry_selection_definition_then_mesh_rebinds():
    project = _project(divisions_u=2, divisions_v=1)
    project.add_selection_set(
        SelectionSetData(
            "Panel shells",
            surface_tags={1},
            surface_scope_mode="elements",
        )
    )

    delete_surface_mesh(project, 1)

    item = project.selection_sets["Panel shells"]
    assert item.surface_tags == {1}
    assert item.node_tags == set()
    assert item.element_tags == set()

    restored = ProjectDatabase.from_dict(project.to_dict())
    mesh_surface_geometry(restored, 1)
    item = restored.selection_sets["Panel shells"]
    assert item.element_tags == set(
        restored.surfaces[1].generated_element_tags
    )


@pytest.mark.parametrize("kind", ["node", "element"])
def test_direct_fe_named_selection_still_blocks_surface_remesh(kind):
    project = _project()
    if kind == "node":
        selection = SelectionSetData(
            "Direct node",
            node_tags={project.surfaces[1].generated_node_tags[0]},
        )
    else:
        selection = SelectionSetData(
            "Direct shell",
            element_tags={project.surfaces[1].generated_element_tags[0]},
        )
    project.add_selection_set(selection)

    with pytest.raises(ValueError, match="named selection"):
        remesh_surface_geometry(project, 1)


def test_multi_surface_managed_selection_survives_deleting_one_source():
    project = _project(divisions_u=1, divisions_v=1)
    project.add_surface(
        SurfaceGeometryData(
            2,
            "Panel 2",
            points=rectangle_surface_points((5, 0, 0), 4, 2),
            section_tag=7,
            divisions_u=2,
            divisions_v=1,
            conform_existing_edges=False,
        )
    )
    mesh_surface_geometry(project, 2)
    project.add_selection_set(
        SelectionSetData(
            "Two panels",
            surface_tags={1, 2},
            surface_scope_mode="elements",
        )
    )

    delete_surface_geometry(project, 1)

    item = project.selection_sets["Two panels"]
    assert item.surface_tags == {2}
    assert item.element_tags == set(
        project.surfaces[2].generated_element_tags
    )

    delete_surface_geometry(project, 2)
    assert "Two panels" not in project.selection_sets


def test_managed_named_selection_ui_and_provenance_guard_are_exposed():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    create = inspect.getsource(MainWindow._create_surface_named_selection)
    edit = inspect.getsource(MainWindow._edit_managed_named_selection)
    update = inspect.getsource(MainWindow._update_named_selection)
    properties = inspect.getsource(
        MainWindow._show_named_selection_properties
    )
    surface_properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )
    refresh_tree = inspect.getsource(MainWindow._refresh_tree)
    prune = inspect.getsource(MainWindow._prune_selection_sets)

    assert "Create Managed Named Selection..." in context
    assert "Edit Surface Scope Mode..." in context
    assert "surface_tags=set(tags)" in create
    assert "surface_scope_mode=mode" in create
    assert "update_selection_set" in edit
    assert "This named selection is managed by Geometry Surface" in update
    assert "Geometry Surface · remesh-safe" in properties
    assert "Managed named selections" in surface_properties
    assert "[Surface:" in refresh_tree
    assert "sync_selection_set_surface_scope" in prune
