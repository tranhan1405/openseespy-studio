from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    LoadPatternData,
    ProjectDatabase,
    SectionData,
    SurfaceEdgeLoadData,
    SurfaceGeometryData,
    TimeSeriesData,
)
from openseespy_studio.surface_mesher import (
    flip_surface_orientation,
    managed_surface_edge_load_nodal_tags,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    remove_surface_edge_load,
    surface_edge_consistent_nodal_weights,
    sync_surface_edge_load,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_edge_load_dialog import SurfaceEdgeLoadDialog
from openseespy_studio.ui.viewport import ModelViewport


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
    project = ProjectDatabase(name="managed-edge-line-load")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_section())
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Gravity",
            "Plain",
            time_series_tag=1,
        )
    )
    return project


def _meshed_project(
    *,
    divisions_u=4,
    divisions_v=1,
    bias_u=1.0,
) -> ProjectDatabase:
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Panel",
            points=rectangle_surface_points((0, 0, 0), 10, 2),
            section_tag=7,
            divisions_u=divisions_u,
            divisions_v=divisions_v,
            bias_u=bias_u,
            conform_existing_edges=False,
        )
    )
    mesh_surface_geometry(project, 1)
    return project


def test_surface_edge_line_load_round_trips_with_generated_provenance():
    project = _meshed_project()
    edge_load = SurfaceEdgeLoadData(
        1,
        "Bottom qZ",
        1,
        1,
        1,
        values_per_length=(0, 0, -5, 0, 0, 0),
    )
    project.add_surface_edge_load(edge_load)
    generated = sync_surface_edge_load(project, 1)

    restored = ProjectDatabase.from_dict(project.to_dict())
    item = restored.surface_edge_loads[1]

    assert item.surface_tag == 1
    assert item.edge_index == 1
    assert item.pattern_tag == 1
    assert item.values_per_length[2] == pytest.approx(-5.0)
    assert item.generated_nodal_load_tags == generated
    assert set(generated) == managed_surface_edge_load_nodal_tags(restored)


def test_consistent_edge_load_is_exact_on_biased_nonuniform_mesh():
    project = _meshed_project(divisions_u=5, bias_u=4.0)
    edge_load = SurfaceEdgeLoadData(
        1,
        "Biased qX",
        1,
        1,
        1,
        values_per_length=(3.0, 0, 0, 0, 0, 0),
    )
    project.add_surface_edge_load(edge_load)

    node_tags, weights = surface_edge_consistent_nodal_weights(
        project,
        1,
        1,
    )
    generated = sync_surface_edge_load(project, 1)
    loads = [project.nodal_loads[tag] for tag in generated]

    assert len(node_tags) == 6
    assert len(weights) == 6
    assert sum(weights) == pytest.approx(10.0)
    assert weights[0] != pytest.approx(weights[-1])
    assert sum(load.values[0] for load in loads) == pytest.approx(30.0)


def test_consistent_uniform_edge_load_reproduces_resultant_location():
    project = _meshed_project(divisions_u=5, bias_u=4.0)
    edge_load = SurfaceEdgeLoadData(
        1,
        "Biased qY",
        1,
        1,
        1,
        values_per_length=(0, 2.0, 0, 0, 0, 0),
    )
    project.add_surface_edge_load(edge_load)
    generated = sync_surface_edge_load(project, 1)

    total_y = sum(
        project.nodal_loads[tag].values[1]
        for tag in generated
    )
    moment_z = sum(
        project.model.nodes[
            project.nodal_loads[tag].node_tag
        ].xyz[0]
        * project.nodal_loads[tag].values[1]
        for tag in generated
    )

    assert total_y == pytest.approx(20.0)
    assert moment_z == pytest.approx(100.0)


def test_remesh_rebinds_edge_load_and_removes_old_equivalent_loads():
    project = _meshed_project(divisions_u=2)
    edge_load = SurfaceEdgeLoadData(
        1,
        "Bottom qY",
        1,
        1,
        1,
        values_per_length=(0, 2.0, 0, 0, 0, 0),
    )
    project.add_surface_edge_load(edge_load)
    old_generated = set(sync_surface_edge_load(project, 1))

    project.surfaces[1].divisions_u = 6
    remesh_surface_geometry(project, 1)
    item = project.surface_edge_loads[1]
    new_generated = set(item.generated_nodal_load_tags)

    assert len(new_generated) == 7
    assert old_generated.isdisjoint(project.nodal_loads)
    assert new_generated <= set(project.nodal_loads)
    assert sum(
        project.nodal_loads[tag].values[1]
        for tag in new_generated
    ) == pytest.approx(20.0)


def test_flip_preserves_physical_loaded_edge_and_total_resultant():
    project = _meshed_project(divisions_u=3, divisions_v=2)
    edge_load = SurfaceEdgeLoadData(
        1,
        "Bottom qZ",
        1,
        1,
        1,
        values_per_length=(0, 0, -4.0, 0, 0, 0),
    )
    project.add_surface_edge_load(edge_load)
    generated_before = sync_surface_edge_load(project, 1)
    xyz_before = {
        tuple(
            project.model.nodes[
                project.nodal_loads[tag].node_tag
            ].xyz
        )
        for tag in generated_before
    }
    total_before = sum(
        project.nodal_loads[tag].values[2]
        for tag in generated_before
    )

    flip_surface_orientation(project, 1)

    item = project.surface_edge_loads[1]
    generated_after = item.generated_nodal_load_tags
    xyz_after = {
        tuple(
            project.model.nodes[
                project.nodal_loads[tag].node_tag
            ].xyz
        )
        for tag in generated_after
    }
    total_after = sum(
        project.nodal_loads[tag].values[2]
        for tag in generated_after
    )

    assert item.edge_index == 4
    assert xyz_after == xyz_before
    assert total_after == pytest.approx(total_before)
    assert total_after == pytest.approx(-40.0)


def test_remove_edge_load_deletes_only_its_generated_nodal_loads():
    project = _meshed_project()
    edge_load = SurfaceEdgeLoadData(
        1,
        "Bottom qZ",
        1,
        1,
        1,
        values_per_length=(0, 0, -5, 0, 0, 0),
    )
    project.add_surface_edge_load(edge_load)
    generated = set(sync_surface_edge_load(project, 1))

    removed = set(remove_surface_edge_load(project, 1))

    assert removed == generated
    assert generated.isdisjoint(project.nodal_loads)
    assert 1 not in project.surface_edge_loads


def test_edge_load_ui_preview_and_generated_nodal_guard_are_exposed():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    manage = inspect.getsource(MainWindow._manage_surface_edge_line_load)
    preview = inspect.getsource(MainWindow._preview_surface_edge_line_load)
    remove = inspect.getsource(MainWindow._remove_surface_edge_line_load)
    edit_nodal = inspect.getsource(MainWindow._edit_nodal_load)
    delete_nodal = inspect.getsource(MainWindow._delete_nodal_load)
    properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )
    viewport = inspect.getsource(
        ModelViewport._render_surface_edge_load_preview
    )
    dialog = inspect.getsource(SurfaceEdgeLoadDialog)

    assert "Managed Edge Line Load..." in context
    assert "Preview Managed Edge Line Load..." in context
    assert "Remove Managed Edge Line Load..." in context
    assert "SurfaceEdgeLoadDialog" in manage
    assert "sync_surface_edge_load" in manage
    assert "replace_surface_edge_load" in manage
    assert "show_surface_edge_load_preview" in preview
    assert "remove_surface_edge_load" in remove
    assert "generated by managed Surface Edge Line Load" in edit_nodal
    assert "generated by managed Surface Edge Line Load" in delete_nodal
    assert "Managed edge line loads" in properties
    assert 'name="surface-edge-load-preview"' in viewport
    assert "pickable=False" in viewport
    assert "qX" in dialog and "mZ" in dialog
