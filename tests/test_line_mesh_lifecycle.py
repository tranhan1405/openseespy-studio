from __future__ import annotations

import inspect

import pytest

from openseespy_studio.line_mesher import (
    audit_line_mesh_integrity,
    delete_line_geometry,
    delete_line_mesh,
    inspect_line_mesh_state,
    line_mesh_coordinates,
    mesh_line_geometry,
    remesh_line_geometry,
)
from openseespy_studio.project import (
    LineGeometryData,
    MaterialData,
    PointGeometryData,
    ProjectDatabase,
    SectionData,
    SelectionSetData,
    TransformationData,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport


def _frame_project(*, length: float = 10.0) -> ProjectDatabase:
    project = ProjectDatabase(name="line-lifecycle-frame")
    project.add_section(SectionData(1, "Frame section", "Elastic"))
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "B", (length, 0.0, 0.0)))
    return project


def _truss_project(*, length: float = 6.0) -> ProjectDatabase:
    project = ProjectDatabase(name="line-lifecycle-truss")
    project.add_material(
        MaterialData(
            1,
            "Elastic steel",
            "Elastic",
            parameters={"E": 200.0e9},
        )
    )
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "B", (length, 0.0, 0.0)))
    return project


def test_biased_frame_line_mesh_has_requested_end_ratio_and_ownership():
    project = _frame_project()
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
            1,
            2,
            divisions=5,
            bias=4.0,
            reuse_existing_nodes=False,
            element_family="Frame",
            element_type="dispBeamColumn",
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = mesh_line_geometry(project, 1)
    xs = [project.model.nodes[tag].xyz[0] for tag in result.node_tags]
    lengths = [
        xs[index + 1] - xs[index]
        for index in range(len(xs) - 1)
    ]

    assert len(result.element_tags) == 5
    assert lengths[-1] / lengths[0] == pytest.approx(4.0)
    assert project.lines[1].generated_node_tags == result.node_tags
    assert set(project.lines[1].owned_node_tags) == set(result.node_tags)
    assert result.coordinates == pytest.approx(
        line_mesh_coordinates(5, 4.0)
    )


def test_truss_line_remesh_updates_discretization_and_keeps_recipe():
    project = _truss_project()
    project.add_line(
        LineGeometryData(
            1,
            "Tie",
            1,
            2,
            divisions=2,
            bias=1.0,
            element_family="Truss",
            material_tag=1,
            area=0.003,
            do_rayleigh=True,
        )
    )
    mesh_line_geometry(project, 1)

    project.lines[1].divisions = 4
    project.lines[1].bias = 0.25
    result = remesh_line_geometry(project, 1)

    assert len(result.element_tags) == 4
    assert set(project.model.elements) == set(result.element_tags)
    assert all(
        project.model.elements[tag].element_type == "truss"
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].truss_material_tag == 1
        and project.model.elements[tag].truss_area == pytest.approx(0.003)
        and project.model.elements[tag].truss_do_rayleigh
        for tag in result.element_tags
    )
    xs = [project.model.nodes[tag].xyz[0] for tag in result.node_tags]
    lengths = [
        xs[index + 1] - xs[index]
        for index in range(len(xs) - 1)
    ]
    assert lengths[-1] / lengths[0] == pytest.approx(0.25)


def test_delete_line_mesh_preserves_reused_end_nodes_and_removes_owned_nodes():
    project = _frame_project(length=4.0)
    project.model.add_node(10, 0.0, 0.0, 0.0)
    project.model.add_node(11, 4.0, 0.0, 0.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
            1,
            2,
            divisions=2,
            section_tag=1,
            transformation_tag=1,
            reuse_existing_nodes=True,
        )
    )
    result = mesh_line_geometry(project, 1)
    midpoint = next(
        tag for tag in result.node_tags
        if tag not in {10, 11}
    )

    deleted = delete_line_mesh(project, 1)

    assert set(deleted.kept_node_tags) == set()
    assert midpoint in deleted.removed_node_tags
    assert 10 in project.model.nodes
    assert 11 in project.model.nodes
    assert midpoint not in project.model.nodes
    assert project.lines[1].generated_node_tags == []
    assert project.lines[1].owned_node_tags == []
    assert project.lines[1].generated_element_tags == []


@pytest.mark.parametrize("scope_kind", ["node", "element"])
def test_direct_fe_named_selection_blocks_line_remesh(scope_kind):
    project = _frame_project(length=4.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
            1,
            2,
            divisions=2,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    result = mesh_line_geometry(project, 1)
    if scope_kind == "node":
        selection = SelectionSetData(
            "Direct node scope",
            node_tags={result.node_tags[1]},
        )
    else:
        selection = SelectionSetData(
            "Direct element scope",
            element_tags={result.element_tags[0]},
        )
    project.add_selection_set(selection)
    old_elements = set(result.element_tags)

    project.lines[1].divisions = 5
    with pytest.raises(ValueError, match="named selection"):
        remesh_line_geometry(project, 1)

    assert old_elements <= set(project.model.elements)


def test_line_integrity_detects_foreign_tracked_element_ownership():
    project = _frame_project(length=4.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
            1,
            2,
            divisions=2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    result = mesh_line_geometry(project, 1)
    project.model.elements[result.element_tags[0]].group = "manual"

    state = inspect_line_mesh_state(project, 1)
    report = audit_line_mesh_integrity(project, [1])

    assert state.status == "stale"
    assert result.element_tags[0] in state.foreign_element_tags
    assert report.issue_count >= 1
    with pytest.raises(ValueError, match="ownership is inconsistent"):
        delete_line_mesh(project, 1)


def test_delete_geometry_line_cascades_its_owned_frame_mesh():
    project = _frame_project(length=4.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
            1,
            2,
            divisions=3,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    result = mesh_line_geometry(project, 1)

    deleted = delete_line_geometry(project, 1)

    assert 1 not in project.lines
    assert set(result.element_tags).isdisjoint(project.model.elements)
    assert set(result.node_tags).isdisjoint(project.model.nodes)
    assert set(deleted.removed_element_tags) == set(result.element_tags)


def test_line_mesh_ui_exposes_preview_remesh_delete_audit_and_fe_bridge():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    edit = inspect.getsource(MainWindow._edit_line_geometry)
    preview = inspect.getsource(MainWindow._preview_line_mesh)
    select_fe = inspect.getsource(MainWindow._select_line_generated_fe)
    properties = inspect.getsource(MainWindow._show_line_geometry_properties)
    viewport = inspect.getsource(ModelViewport._render_line_mesh_preview)

    assert "Edit Line / Mesh Settings..." in context
    assert "Preview Line Mesh" in context
    assert "Remesh Line" in context
    assert "Delete Generated Line Mesh" in context
    assert "Select Generated FE" in context
    assert "Audit Line Mesh Integrity" in context
    assert "remesh_line_geometry" in edit
    assert "line_mesh_preview_points" in preview
    assert 'set_display_domain("fe")' in select_fe
    assert "Mesh bias" in properties
    assert 'name="line-mesh-preview"' in viewport
    assert "pickable=False" in viewport
