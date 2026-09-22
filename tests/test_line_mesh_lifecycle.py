from __future__ import annotations

import inspect

import pytest

from openseespy_studio.line_mesher import (
    audit_line_mesh_integrity,
    audit_line_network_connectivity,
    copy_line_mesh_recipe,
    delete_line_geometry,
    delete_line_mesh,
    inspect_line_mesh_state,
    line_mesh_coordinates,
    line_mesh_quality,
    mesh_line_geometry,
    remesh_line_batch,
    remesh_line_geometry,
    reverse_line_geometry,
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
    assert "Mesh Quality..." in context
    assert "Reverse Line Direction" in context
    assert "Copy This Mesh / FE Recipe" in context
    assert "Generate / Remesh" in context
    assert "Audit Line Network Connectivity" in context
    assert "remesh_line_geometry" in edit
    assert "line_mesh_preview_points" in preview
    assert 'set_display_domain("fe")' in select_fe
    assert "Mesh bias" in properties
    assert 'name="line-mesh-preview"' in viewport
    assert "pickable=False" in viewport

    quality = inspect.getsource(MainWindow._show_line_mesh_quality)
    reverse = inspect.getsource(MainWindow._reverse_line_geometry)
    copy_recipe = inspect.getsource(
        MainWindow._copy_line_mesh_recipe_to_selected
    )
    batch = inspect.getsource(MainWindow._remesh_line_geometries)
    network = inspect.getsource(
        MainWindow._audit_line_network_connectivity_ui
    )
    assert "line_mesh_quality" in quality
    assert "reverse_line_geometry" in reverse
    assert "copy_line_mesh_recipe" in copy_recipe
    assert "remesh_line_batch" in batch
    assert "audit_line_network_connectivity" in network

def test_line_mesh_quality_reports_actual_biased_fe_lengths():
    project = _frame_project(length=10.0)
    project.add_line(
        LineGeometryData(
            1,
            "Quality beam",
            1,
            2,
            divisions=5,
            bias=4.0,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    mesh_line_geometry(project, 1)

    quality = line_mesh_quality(project, 1)

    assert quality.element_count == 5
    assert quality.total_length == pytest.approx(10.0)
    assert quality.length_ratio == pytest.approx(4.0)
    assert quality.min_length > 0.0
    assert quality.max_length > quality.min_length
    assert not quality.uniform


def test_reverse_meshed_line_preserves_physical_grading_and_remeshes():
    project = _frame_project(length=10.0)
    project.add_line(
        LineGeometryData(
            1,
            "Reverse beam",
            1,
            2,
            divisions=4,
            bias=8.0,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    before = mesh_line_geometry(project, 1)
    before_xyz = [
        project.model.nodes[tag].xyz
        for tag in before.node_tags
    ]
    result = reverse_line_geometry(project, 1)

    assert result is not None
    assert project.lines[1].point_i == 2
    assert project.lines[1].point_j == 1
    assert project.lines[1].bias == pytest.approx(1.0 / 8.0)
    after_xyz = [
        project.model.nodes[tag].xyz
        for tag in result.node_tags
    ]
    assert after_xyz == pytest.approx(list(reversed(before_xyz)))
    assert len(result.element_tags) == 4
    assert all(
        project.model.elements[tag].group == "line:1"
        for tag in result.element_tags
    )


def test_copy_line_mesh_recipe_can_convert_target_frame_to_truss():
    project = _frame_project(length=8.0)
    project.add_material(
        MaterialData(
            1,
            "Truss steel",
            "Elastic",
            parameters={"E": 200.0e9},
        )
    )
    project.add_point(PointGeometryData(3, "C", (0.0, 2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (8.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Truss source",
            1,
            2,
            divisions=6,
            bias=2.0,
            element_family="Truss",
            material_tag=1,
            area=0.004,
            mass_per_length=12.0,
            do_rayleigh=True,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Frame target",
            3,
            4,
            divisions=2,
            element_family="Frame",
            section_tag=1,
            transformation_tag=1,
        )
    )

    results = copy_line_mesh_recipe(project, 1, [2])
    target = project.lines[2]

    assert results[2] is None
    assert target.name == "Frame target"
    assert (target.point_i, target.point_j) == (3, 4)
    assert target.element_family == "Truss"
    assert target.element_type == "truss"
    assert target.divisions == 6
    assert target.bias == pytest.approx(2.0)
    assert target.material_tag == 1
    assert target.area == pytest.approx(0.004)
    assert target.mass_per_length == pytest.approx(12.0)
    assert target.do_rayleigh

    mesh = mesh_line_geometry(project, 2)
    assert len(mesh.element_tags) == 6
    assert all(
        project.model.elements[tag].element_type == "truss"
        for tag in mesh.element_tags
    )


def test_batch_remesh_rebuilds_shared_endpoint_without_orphan_nodes():
    project = _frame_project(length=4.0)
    project.add_point(PointGeometryData(3, "C", (4.0, 3.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "AB",
            1,
            2,
            divisions=2,
            reuse_existing_nodes=True,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "BC",
            2,
            3,
            divisions=2,
            reuse_existing_nodes=True,
            section_tag=1,
            transformation_tag=1,
        )
    )
    first = mesh_line_geometry(project, 1)
    second = mesh_line_geometry(project, 2)
    shared_before = set(first.node_tags) & set(second.node_tags)
    assert len(shared_before) == 1

    project.lines[1].divisions = 4
    project.lines[2].divisions = 3
    results = remesh_line_batch(project, [1, 2])

    shared_after = (
        set(results[1].node_tags)
        & set(results[2].node_tags)
    )
    assert len(shared_after) == 1
    assert len(results[1].element_tags) == 4
    assert len(results[2].element_tags) == 3
    used_nodes = {
        node_tag
        for element in project.model.elements.values()
        for node_tag in element.node_tags()
    }
    assert set(project.model.nodes) == used_nodes


def test_connectivity_audit_flags_disconnected_geometry_junction():
    project = _frame_project(length=4.0)
    project.add_point(PointGeometryData(3, "C", (4.0, 3.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "AB",
            1,
            2,
            divisions=2,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "BC",
            2,
            3,
            divisions=2,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    mesh_line_geometry(project, 1)
    mesh_line_geometry(project, 2)

    issues = audit_line_network_connectivity(project)

    assert len(issues) == 1
    assert issues[0].kind == "endpoint"
    assert issues[0].line_tags == (1, 2)
    assert issues[0].point == pytest.approx((4.0, 0.0, 0.0))

    remesh_line_batch(project, [1, 2])
    # reuse_existing_nodes=False remains an explicit disconnected recipe.
    assert len(audit_line_network_connectivity(project)) == 1

    project.lines[1].reuse_existing_nodes = True
    project.lines[2].reuse_existing_nodes = True
    remesh_line_batch(project, [1, 2])
    assert audit_line_network_connectivity(project) == []

