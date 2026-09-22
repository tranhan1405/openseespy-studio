from __future__ import annotations

import inspect
import math
from types import SimpleNamespace

import pytest

from openseespy_studio.line_mesher import (
    audit_line_mesh_integrity,
    audit_line_network_connectivity,
    chamfer_lines,
    conform_line_network,
    copy_line_mesh_recipe,
    copy_offset_line_geometry,
    delete_line_geometry,
    delete_line_mesh,
    divide_line_geometry,
    fillet_lines,
    inspect_line_mesh_state,
    line_geometry_intersections,
    line_mesh_coordinates,
    line_mesh_quality,
    merge_collinear_lines,
    mesh_line_geometry,
    remesh_line_batch,
    remesh_line_geometry,
    reverse_line_geometry,
    split_line_geometry_at_point,
    split_line_pair_at_intersection,
    trim_extend_line_to_line,
    trim_extend_lines_to_line,
)
from openseespy_studio.project import (
    LineGeometryData,
    MaterialData,
    PointGeometryData,
    ProjectDatabase,
    SectionData,
    SelectionSetData,
    SurfaceGeometryData,
    TransformationData,
)
from openseespy_studio.surface_mesher import mesh_surface_geometry
from openseespy_studio.ui.line_geometry_dialog import LineGeometryDialog
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog
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

    assert "Edit Line Geometry..." in context
    assert "Configure Line Mesh / FE Recipe..." in context
    assert 'if kind == "line_mesh_recipe"' in context
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
    assert "Inspect Line Network Intersections..." in context
    assert "Conform / Heal Line Network" in context
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
    intersections = inspect.getsource(
        MainWindow._inspect_line_geometry_intersections
    )
    conform = inspect.getsource(
        MainWindow._conform_line_network_ui
    )
    assert "line_mesh_quality" in quality
    assert "reverse_line_geometry" in reverse
    assert "copy_line_mesh_recipe" in copy_recipe
    assert "remesh_line_batch" in batch
    assert "audit_line_network_connectivity" in network
    assert "line_geometry_intersections" in intersections
    assert "conform_line_network" in conform

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
    expected_xyz = list(reversed(before_xyz))
    assert len(after_xyz) == len(expected_xyz)
    for actual, expected in zip(after_xyz, expected_xyz):
        assert actual == pytest.approx(expected)
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


def test_shared_geometry_point_is_connected_even_when_coordinate_reuse_disabled():
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
    first = mesh_line_geometry(project, 1)
    second = mesh_line_geometry(project, 2)

    assert set(first.node_tags) & set(second.node_tags)
    assert audit_line_network_connectivity(project) == []


def test_distinct_coincident_geometry_points_remain_disconnected_when_reuse_disabled():
    project = _frame_project(length=4.0)
    project.add_point(PointGeometryData(3, "B duplicate", (4.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(4, "C", (4.0, 3.0, 0.0)))
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
            "B2C",
            3,
            4,
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

    result = conform_line_network(project, [1, 2], mesh=True)

    assert result.created_point_tags == []
    assert project.lines[1].point_j == project.lines[2].point_i
    assert audit_line_network_connectivity(project) == []

def _crossing_project() -> ProjectDatabase:
    project = _frame_project(length=4.0)
    project.add_point(PointGeometryData(3, "C", (2.0, -2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (2.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Horizontal",
            1,
            2,
            divisions=4,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Vertical",
            3,
            4,
            divisions=4,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    return project


def test_crossing_lines_conform_into_shared_geometry_point_and_fe_node():
    project = _crossing_project()

    intersections = line_geometry_intersections(project, [1, 2])
    assert len(intersections) == 1
    assert intersections[0].kind == "crossing"
    assert intersections[0].point == pytest.approx((2.0, 0.0, 0.0))

    result = conform_line_network(project, [1, 2], mesh=True)

    assert result.intersection_count == 1
    assert result.split_line_tags == [1, 2]
    assert len(result.created_point_tags) == 1
    assert len(result.created_line_tags) == 2
    assert len(result.output_line_tags) == 4
    center_point = result.created_point_tags[0]

    center_lines = [
        line
        for line in project.lines.values()
        if center_point in {line.point_i, line.point_j}
    ]
    assert len(center_lines) == 4

    center_nodes = set()
    for line in center_lines:
        node_tag = (
            line.generated_node_tags[0]
            if line.point_i == center_point
            else line.generated_node_tags[-1]
        )
        center_nodes.add(node_tag)
    assert len(center_nodes) == 1
    assert audit_line_network_connectivity(project) == []


def test_t_junction_conform_reuses_existing_endpoint_geometry_point():
    project = _frame_project(length=4.0)
    project.add_point(PointGeometryData(3, "T", (2.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(4, "Stem", (2.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Through",
            1,
            2,
            divisions=4,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Stem",
            3,
            4,
            divisions=2,
            reuse_existing_nodes=False,
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = conform_line_network(project, [1, 2], mesh=True)

    assert result.intersection_count == 1
    assert result.created_point_tags == []
    assert result.split_line_tags == [1]
    assert len(result.created_line_tags) == 1
    lines_at_t = [
        line
        for line in project.lines.values()
        if 3 in {line.point_i, line.point_j}
    ]
    assert len(lines_at_t) == 3
    shared_nodes = {
        (
            line.generated_node_tags[0]
            if line.point_i == 3
            else line.generated_node_tags[-1]
        )
        for line in lines_at_t
    }
    assert len(shared_nodes) == 1


def test_manual_line_split_preserves_recipe_and_existing_mesh_state():
    project = _frame_project(length=10.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
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

    result = split_line_geometry_at_point(
        project,
        1,
        (4.0, 0.0, 0.0),
        remesh=True,
    )

    assert len(result.line_tags) == 2
    assert len(result.created_line_tags) == 1
    assert len(result.created_point_tags) == 1
    first = project.lines[result.line_tags[0]]
    second = project.lines[result.line_tags[1]]
    assert first.section_tag == second.section_tag == 1
    assert first.transformation_tag == second.transformation_tag == 1
    assert first.element_family == second.element_family == "Frame"
    assert first.divisions + second.divisions == 5
    assert first.bias * second.bias == pytest.approx(4.0)
    assert set(result.mesh_results) == set(result.line_tags)
    shared = (
        set(result.mesh_results[first.tag].node_tags)
        & set(result.mesh_results[second.tag].node_tags)
    )
    assert len(shared) == 1


def test_moving_point_used_by_meshed_line_is_rejected():
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
    mesh_line_geometry(project, 1)

    with pytest.raises(ValueError, match="meshed Line"):
        project.update_point(
            2,
            PointGeometryData(2, "B", (5.0, 0.0, 0.0)),
        )

def test_trim_extend_splits_target_and_shares_topology():
    project = _frame_project(length=3.0)
    project.add_point(PointGeometryData(3, "C", (0.0, 2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (5.0, -2.0, 0.0)))
    project.add_point(PointGeometryData(5, "E", (5.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Subject",
            1,
            2,
            divisions=3,
            section_tag=1,
            transformation_tag=1,
            reuse_existing_nodes=False,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Target",
            4,
            5,
            divisions=4,
            section_tag=1,
            transformation_tag=1,
            reuse_existing_nodes=False,
        )
    )
    mesh_line_geometry(project, 1)
    mesh_line_geometry(project, 2)

    result = trim_extend_line_to_line(
        project,
        1,
        2,
        endpoint="j",
        remesh=True,
    )

    assert result.operation == "extend"
    assert result.endpoint == "j"
    assert result.intersection == pytest.approx((5.0, 0.0, 0.0))
    assert len(result.created_point_tags) == 1
    assert len(result.created_line_tags) == 1
    junction = result.intersection_point_tag
    assert project.lines[1].point_j == junction
    target_segments = [
        line
        for line in project.lines.values()
        if line.tag != 1 and junction in {line.point_i, line.point_j}
    ]
    assert len(target_segments) == 2

    junction_nodes = set()
    for line in [project.lines[1], *target_segments]:
        junction_nodes.add(
            line.generated_node_tags[0]
            if line.point_i == junction
            else line.generated_node_tags[-1]
        )
    assert len(junction_nodes) == 1


def test_split_by_line_creates_shared_topology_on_both_lines():
    project = _frame_project(length=10.0)
    project.add_point(PointGeometryData(3, "C", (5.0, -5.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (5.0, 5.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Horizontal",
            1,
            2,
            divisions=2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Vertical",
            3,
            4,
            divisions=2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    remesh_line_batch(project, [1, 2])

    result = split_line_pair_at_intersection(project, 1, 2, remesh=True)

    assert result.intersection == pytest.approx((5.0, 0.0, 0.0))
    assert len(result.output_line_tags[1]) == 2
    assert len(result.output_line_tags[2]) == 2
    assert len(result.created_line_tags) == 2
    point_tag = result.intersection_point_tag
    assert sum(
        point_tag in {line.point_i, line.point_j}
        for line in project.lines.values()
    ) == 4
    junction_nodes = {
        line.generated_node_tags[0]
        if line.point_i == point_tag
        else line.generated_node_tags[-1]
        for line in project.lines.values()
        if point_tag in {line.point_i, line.point_j}
    }
    assert len(junction_nodes) == 1


def test_batch_trim_splits_one_boundary_for_multiple_subjects():
    project = _frame_project(length=10.0)
    project.add_point(PointGeometryData(3, "A2", (0.0, 2.0, 0.0)))
    project.add_point(PointGeometryData(4, "B2", (10.0, 2.0, 0.0)))
    project.add_point(PointGeometryData(5, "C", (6.0, -1.0, 0.0)))
    project.add_point(PointGeometryData(6, "D", (6.0, 3.0, 0.0)))
    for tag, name, pi, pj in (
        (1, "S1", 1, 2),
        (2, "S2", 3, 4),
        (3, "Boundary", 5, 6),
    ):
        project.add_line(
            LineGeometryData(
                tag,
                name,
                pi,
                pj,
                divisions=2,
                section_tag=1,
                transformation_tag=1,
            )
        )
    remesh_line_batch(project, [1, 2, 3])

    result = trim_extend_lines_to_line(
        project,
        [1, 2],
        3,
        operation="trim",
        remesh=True,
    )

    assert result.operation == "trim"
    assert len(result.target_line_tags) == 3
    assert len(result.created_line_tags) == 2
    assert project.points[project.lines[1].point_j].xyz == pytest.approx(
        (6.0, 0.0, 0.0)
    )
    assert project.points[project.lines[2].point_j].xyz == pytest.approx(
        (6.0, 2.0, 0.0)
    )
    assert set(result.mesh_results) >= {1, 2}


def test_batch_extend_moves_multiple_nearest_endpoints_to_boundary():
    project = _frame_project(length=3.0)
    project.add_point(PointGeometryData(3, "A2", (0.0, 2.0, 0.0)))
    project.add_point(PointGeometryData(4, "B2", (3.0, 2.0, 0.0)))
    project.add_point(PointGeometryData(5, "C", (6.0, -1.0, 0.0)))
    project.add_point(PointGeometryData(6, "D", (6.0, 3.0, 0.0)))
    for tag, name, pi, pj in (
        (1, "S1", 1, 2),
        (2, "S2", 3, 4),
        (3, "Boundary", 5, 6),
    ):
        project.add_line(
            LineGeometryData(
                tag,
                name,
                pi,
                pj,
                section_tag=1,
                transformation_tag=1,
            )
        )

    result = trim_extend_lines_to_line(
        project,
        [1, 2],
        3,
        operation="extend",
        remesh=True,
    )

    assert result.operation == "extend"
    assert project.points[project.lines[1].point_j].xyz == pytest.approx(
        (6.0, 0.0, 0.0)
    )
    assert project.points[project.lines[2].point_j].xyz == pytest.approx(
        (6.0, 2.0, 0.0)
    )
    assert len(result.target_line_tags) == 3


def test_chamfer_replaces_shared_corner_with_straight_connector():
    project = _frame_project(length=5.0)
    project.add_point(PointGeometryData(3, "C", (5.0, 5.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Horizontal",
            1,
            2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Vertical",
            2,
            3,
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = chamfer_lines(project, 1, 2, distance=1.0)

    assert len(result.connector_line_tags) == 1
    connector = project.lines[result.connector_line_tags[0]]
    coords = {
        project.points[connector.point_i].xyz,
        project.points[connector.point_j].xyz,
    }
    assert coords == {(4.0, 0.0, 0.0), (5.0, 1.0, 0.0)}
    assert 2 not in {
        project.lines[1].point_i,
        project.lines[1].point_j,
        project.lines[2].point_i,
        project.lines[2].point_j,
    }


def test_fillet_creates_tangent_polyline_arc_and_trims_source_lines():
    project = _frame_project(length=5.0)
    project.add_point(PointGeometryData(3, "C", (5.0, 5.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Horizontal",
            1,
            2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Vertical",
            2,
            3,
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = fillet_lines(project, 1, 2, radius=1.0, segments=4)

    assert len(result.connector_line_tags) == 4
    first = project.lines[result.connector_line_tags[0]]
    last = project.lines[result.connector_line_tags[-1]]
    assert project.points[first.point_i].xyz == pytest.approx(
        (4.0, 0.0, 0.0)
    )
    assert project.points[last.point_j].xyz == pytest.approx(
        (5.0, 1.0, 0.0)
    )
    center = (4.0, 1.0, 0.0)
    fillet_point_tags = {
        tag
        for line_tag in result.connector_line_tags
        for tag in (
            project.lines[line_tag].point_i,
            project.lines[line_tag].point_j,
        )
    }
    for point_tag in fillet_point_tags:
        xyz = project.points[point_tag].xyz
        distance = math.sqrt(
            sum(
                (xyz[index] - center[index]) ** 2
                for index in range(3)
            )
        )
        assert distance == pytest.approx(1.0)


def test_explicit_trim_never_silently_extends():
    project = _frame_project(length=3.0)
    project.add_point(PointGeometryData(3, "C", (5.0, -2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (5.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Subject",
            1,
            2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Boundary",
            3,
            4,
            section_tag=1,
            transformation_tag=1,
        )
    )

    with pytest.raises(ValueError, match="would EXTEND"):
        trim_extend_line_to_line(
            project,
            1,
            2,
            endpoint="j",
            operation="trim",
        )

    assert project.lines[1].point_j == 2


def test_explicit_extend_never_silently_trims():
    project = _frame_project(length=10.0)
    project.add_point(PointGeometryData(3, "C", (5.0, -2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (5.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Subject",
            1,
            2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Boundary",
            3,
            4,
            section_tag=1,
            transformation_tag=1,
        )
    )

    with pytest.raises(ValueError, match="would TRIM"):
        trim_extend_line_to_line(
            project,
            1,
            2,
            endpoint="j",
            operation="extend",
        )

    assert project.lines[1].point_j == 2


def test_trim_extend_rejects_noop_endpoint_on_boundary():
    project = _frame_project(length=3.0)
    project.add_point(PointGeometryData(3, "C", (3.0, -2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (3.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Subject",
            1,
            2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Boundary",
            3,
            4,
            section_tag=1,
            transformation_tag=1,
        )
    )

    with pytest.raises(ValueError, match="already lies"):
        trim_extend_line_to_line(
            project,
            1,
            2,
            endpoint="j",
            operation="auto",
        )


def test_trim_extend_rejects_wrong_extension_endpoint():
    project = _frame_project(length=3.0)
    project.add_point(PointGeometryData(3, "C", (5.0, -2.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (5.0, 2.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Subject",
            1,
            2,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "Target",
            3,
            4,
            section_tag=1,
            transformation_tag=1,
        )
    )

    with pytest.raises(ValueError, match="beyond Point J"):
        trim_extend_line_to_line(
            project,
            1,
            2,
            endpoint="i",
        )


def test_merge_collinear_lines_preserves_total_divisions_and_mesh():
    project = _frame_project(length=2.0)
    project.add_point(PointGeometryData(3, "C", (5.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(4, "D", (9.0, 0.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "A-B",
            1,
            2,
            divisions=2,
            bias=1.0,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "B-C",
            2,
            3,
            divisions=3,
            bias=1.0,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            3,
            "C-D",
            3,
            4,
            divisions=4,
            bias=1.0,
            section_tag=1,
            transformation_tag=1,
        )
    )
    remesh_line_batch(project, [1, 2, 3])

    result = merge_collinear_lines(
        project,
        [1, 2, 3],
        remesh=True,
    )

    assert result.keeper_line_tag == 1
    assert result.removed_line_tags == [2, 3]
    assert set(project.lines) == {1}
    merged = project.lines[1]
    assert {merged.point_i, merged.point_j} == {1, 4}
    assert merged.divisions == 9
    assert merged.bias == pytest.approx(1.0)
    assert result.mesh_result is not None
    assert len(result.mesh_result.element_tags) == 9


def test_merge_collinear_lines_rejects_biased_recipe():
    project = _frame_project(length=2.0)
    project.add_point(PointGeometryData(3, "C", (4.0, 0.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "A-B",
            1,
            2,
            divisions=2,
            bias=2.0,
            section_tag=1,
            transformation_tag=1,
        )
    )
    project.add_line(
        LineGeometryData(
            2,
            "B-C",
            2,
            3,
            divisions=2,
            bias=2.0,
            section_tag=1,
            transformation_tag=1,
        )
    )

    with pytest.raises(ValueError, match="bias = 1"):
        merge_collinear_lines(project, [1, 2])


def test_divide_geometry_line_into_equal_segments_is_real_topology_division():
    project = _frame_project(length=12.0)
    project.add_line(
        LineGeometryData(
            1,
            "Long beam",
            1,
            2,
            divisions=6,
            bias=1.0,
            section_tag=1,
            transformation_tag=1,
        )
    )
    mesh_line_geometry(project, 1)

    result = divide_line_geometry(
        project,
        1,
        segments=3,
        remesh=True,
    )

    assert len(result.line_tags) == 3
    assert len(result.created_line_tags) == 2
    assert len(result.created_point_tags) == 2
    assert sum(project.lines[tag].divisions for tag in result.line_tags) == 6
    assert set(result.mesh_results) == set(result.line_tags)
    endpoint_sets = [
        {project.lines[tag].point_i, project.lines[tag].point_j}
        for tag in result.line_tags
    ]
    assert endpoint_sets[0] & endpoint_sets[1]
    assert endpoint_sets[1] & endpoint_sets[2]


def test_divide_geometry_line_at_distance_from_i():
    project = _frame_project(length=10.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam",
            1,
            2,
            divisions=5,
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = divide_line_geometry(
        project,
        1,
        distance_from_i=3.0,
        remesh=True,
    )

    assert len(result.line_tags) == 2
    split_point = project.points[result.point_tags[0]]
    assert split_point.xyz == pytest.approx((3.0, 0.0, 0.0))


def test_copy_offset_line_network_preserves_shared_geometry_topology():
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
    remesh_line_batch(project, [1, 2])

    result = copy_offset_line_geometry(
        project,
        [1, 2],
        dx=10.0,
        dy=0.0,
        dz=0.0,
        copies=2,
        mesh=True,
    )

    assert len(result.created_line_tags) == 4
    assert len(result.created_point_tags) == 6
    assert len(result.mesh_results) == 4

    first_copy = result.created_line_tags[:2]
    copy_lines = [project.lines[tag] for tag in first_copy]
    common_points = (
        {copy_lines[0].point_i, copy_lines[0].point_j}
        & {copy_lines[1].point_i, copy_lines[1].point_j}
    )
    assert len(common_points) == 1
    common_point = next(iter(common_points))
    common_nodes = {
        (
            line.generated_node_tags[0]
            if line.point_i == common_point
            else line.generated_node_tags[-1]
        )
        for line in copy_lines
    }
    assert len(common_nodes) == 1


def test_line_intersection_preview_and_preprocessor_actions_are_exposed():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    trim = inspect.getsource(MainWindow._trim_extend_geometry_line)
    merge = inspect.getsource(MainWindow._merge_selected_geometry_lines)
    divide = inspect.getsource(MainWindow._divide_geometry_line)
    copy_offset = inspect.getsource(MainWindow._copy_offset_geometry_lines)
    inspect_intersections = inspect.getsource(
        MainWindow._inspect_line_geometry_intersections
    )
    viewport_show = inspect.getsource(
        ModelViewport.show_line_intersection_preview
    )
    viewport_render = inspect.getsource(
        ModelViewport._render_line_intersection_preview
    )

    assert "Trim / Extend This Line to Other Selected Line..." in context
    assert "Merge" in context and "Collinear Lines" in context
    assert "Divide Geometry Line..." in context
    assert "Copy / Offset Geometry Line..." in context
    assert "Clear Intersection Preview" in context
    assert "trim_extend_line_to_line" in trim
    assert "merge_collinear_lines" in merge
    assert "divide_line_geometry" in divide
    assert "copy_offset_line_geometry" in copy_offset
    assert "show_line_intersection_preview" in inspect_intersections
    assert 'name="line-intersection-preview"' in viewport_render
    assert "pickable=False" in viewport_render
    assert "_line_intersection_preview" in viewport_show

def test_geometry_creation_uses_geometry_only_dialog_modes():
    line_create = inspect.getsource(
        MainWindow._create_line_geometry_from_points
    )
    surface_create = inspect.getsource(
        MainWindow._create_surface_geometry_from_points
    )

    assert 'mode="geometry"' in line_create
    assert 'mode="geometry"' in surface_create
    assert "_mesh_line_geometry" not in line_create
    assert "_configure_line_mesh" not in line_create
    assert "_mesh_surface_geometry" not in surface_create
    assert "_configure_surface_mesh" not in surface_create


def test_geometry_dialogs_hide_mesh_recipe_controls_in_geometry_mode():
    line_init = inspect.getsource(LineGeometryDialog.__init__)
    surface_init = inspect.getsource(SurfaceGeometryDialog.__init__)

    assert "self.mesh_group.setVisible(False)" in line_init
    assert "self.recipe_group.setVisible(False)" in line_init
    assert '"Create Geometry"' in line_init
    assert "self.mesh_group.setVisible(False)" in surface_init
    assert "self.preview_button.setVisible(False)" in surface_init
    assert '"Create Geometry"' in surface_init


def test_surface_mesher_rejects_unconfigured_geometry():
    project = ProjectDatabase(name="geometry-only-surface")
    project.add_surface(
        SurfaceGeometryData(
            tag=1,
            name="Geometry only",
            mesh_recipe_configured=False,
            section_tag=None,
        )
    )

    with pytest.raises(ValueError, match="no Mesh recipe"):
        mesh_surface_geometry(project, 1)


def test_mesh_tree_owns_mesh_lifecycle_commands():
    context = inspect.getsource(MainWindow._show_tree_context_menu)

    assert 'if kind == "mesh_root":' in context
    assert 'if kind == "line_meshes_root":' in context
    assert 'if kind == "surface_meshes_root":' in context
    assert 'if kind == "line_mesh_recipe":' in context
    assert 'if kind == "surface_mesh_recipe":' in context
    assert "Generate All Configured Line Meshes" in context
    assert "Generate All Configured Surface Meshes" in context
    assert "Configure Line Mesh / FE Recipe..." in context
    assert "Configure Surface Mesh / Shell Recipe..." in context


def test_geometry_line_context_has_no_mesh_lifecycle_commands():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    start = context.index('if kind == "line_geometry":')
    end = context.index('if kind == "surfaces_root":', start)
    line_block = context[start:end]

    assert "Edit Line Geometry..." in line_block
    assert "Divide Geometry Line..." in line_block
    assert "Trim / Extend This Line to Other Selected Line..." in line_block
    assert "Generate Line Mesh..." not in line_block
    assert "Remesh Line" not in line_block
    assert "Delete Generated Line Mesh" not in line_block
    assert "Configure Mesh / FE Recipe..." not in line_block
    assert "Mesh Quality..." not in line_block


def test_geometry_surface_context_has_no_mesh_lifecycle_commands():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    start = context.index('if kind == "surface_geometry":')
    end = context.index('if kind == "material":', start)
    surface_block = context[start:end]

    assert "Edit Surface Geometry..." in surface_block
    assert "Copy / Offset Surface..." in surface_block
    assert "Configure Mesh / Shell Recipe..." not in surface_block
    assert "Mesh / Remesh Surface" not in surface_block
    assert "Visualize Mesh Quality" not in surface_block

def test_spaceclaim_style_geometry_sketch_actions_and_working_plane():
    actions = inspect.getsource(MainWindow._build_actions_and_ribbon)
    line_activate = inspect.getsource(
        MainWindow._activate_geometry_line_pick_tool
    )
    surface_activate = inspect.getsource(
        MainWindow._activate_geometry_surface_pick_tool
    )
    viewport_plane = inspect.getsource(
        ModelViewport.geometry_workplane_point
    )

    assert '"Draw Polyline"' in actions
    assert '"Draw Rectangle"' in actions
    assert "Create at least two Geometry Points first" not in line_activate
    assert "Create at least four Geometry Points first" not in surface_activate
    assert "shell-compatible Section" not in surface_activate
    assert 'set_interaction_tool("geometry_sketch")' in line_activate
    assert 'set_interaction_tool("geometry_sketch")' in surface_activate
    assert "_geometry_sketch_plane_offset" in viewport_plane


def test_geometry_polyline_sketch_is_continuous_and_geometry_only():
    click = inspect.getsource(
        MainWindow._handle_geometry_line_sketch_click
    )
    draw = inspect.getsource(
        MainWindow._draw_geometry_line_segment
    )
    refresh = inspect.getsource(MainWindow._refresh_all)
    viewport_draw = inspect.getsource(ModelViewport.draw_model)

    assert "_geometry_line_point_tags = [point_j]" in click
    assert "click next point" in click
    assert "LineGeometryData" in draw
    assert "mesh_recipe_configured=False" in draw
    assert "_mesh_line_geometry" not in draw

    # Interactive sketch commits must not refit/reset the camera between
    # P1 -> P2 -> P3. A camera reset after P1 changes the work-plane mapping
    # and makes later clicks look like preview points without committing Lines.
    assert "reset_camera=False" in click
    assert "reset_camera: bool = True" in refresh
    assert "reset_camera=reset_camera" in refresh
    assert "reset_camera: bool = True" in viewport_draw
    assert "_render_model(reset_camera=bool(reset_camera))" in viewport_draw


def test_geometry_sketch_snaps_endpoint_midpoint_and_intersection():
    snap = inspect.getsource(MainWindow._geometry_sketch_snap)
    materialize = inspect.getsource(
        MainWindow._materialize_geometry_sketch_point
    )
    refresh_tree = inspect.getsource(MainWindow._refresh_tree)

    assert '"endpoint"' in snap
    assert '"midpoint"' in snap
    assert '"intersection"' in snap
    assert "16.0 * 16.0" in snap
    assert "best = min(candidates, key=lambda item: (item[1], item[0]))" in snap
    assert "split_line_geometry_at_point" in materialize

    # Rebuilding the tree during a sketch commit must not emit selection
    # changes that can switch the viewport from Geometry to FE mode.
    assert "previous_signal_state = self.tree.blockSignals(True)" in refresh_tree
    assert "self.tree.blockSignals(previous_signal_state)" in refresh_tree
    assert "selected_state" in refresh_tree
    assert "restore_selection" in refresh_tree


def test_geometry_free_line_first_click_is_transient_until_segment_exists():
    project = ProjectDatabase(name="transient-free-line")

    class SnapAction:
        def isChecked(self):
            return False

    class ViewportStub:
        def __init__(self):
            self.plane = ("xy", 0.0)

        def geometry_sketch_plane(self):
            return self.plane

        def set_geometry_sketch_plane_offset_from_point(self, xyz):
            self.plane = ("xy", float(xyz[2]))

        def show_geometry_sketch_preview(self, *_args, **_kwargs):
            return None

    class StatusStub:
        def setText(self, _text):
            return None

    dummy = SimpleNamespace(
        project=project,
        model=project.model,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        status_message=StatusStub(),
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
    )
    dummy._geometry_sketch_snap = (
        MainWindow._geometry_sketch_snap.__get__(dummy, type(dummy))
    )
    dummy._handle_geometry_line_sketch_click = (
        MainWindow._handle_geometry_line_sketch_click.__get__(
            dummy, type(dummy)
        )
    )

    dummy._handle_geometry_line_sketch_click(
        {
            "kind": None,
            "tag": None,
            "world": (2.5, 1.5, 0.0),
            "screen": (250.0, 150.0),
        }
    )

    assert project.points == {}
    assert project.lines == {}
    assert dummy._geometry_line_point_tags == []
    assert dummy._geometry_line_anchor_snap is not None
    assert dummy._geometry_line_anchor_snap["xyz"] == pytest.approx(
        (2.5, 1.5, 0.0)
    )


def test_geometry_polyline_midpoint_anchor_is_transient_then_splits_on_p2():
    project = ProjectDatabase(name="midpoint-first-anchor")
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "B", (4.0, 0.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Base",
            1,
            2,
            mesh_recipe_configured=False,
        )
    )

    class ViewportStub:
        def __init__(self):
            self.plane = ("xy", 0.0)

        def geometry_sketch_plane(self):
            return self.plane

        def set_geometry_sketch_plane_offset_from_point(self, xyz):
            self.plane = ("xy", float(xyz[2]))

        def show_geometry_sketch_preview(self, *_args, **_kwargs):
            return None

    class StatusStub:
        def setText(self, _text):
            return None

    snaps = iter(
        (
            {
                "xyz": (2.0, 0.0, 0.0),
                "kind": "midpoint",
                "label": "Midpoint L1",
                "point_tag": None,
                "line_tags": (1,),
            },
            {
                "xyz": (2.0, 2.0, 0.0),
                "kind": "free",
                "label": "Free",
                "point_tag": None,
                "line_tags": (),
            },
        )
    )
    dummy = SimpleNamespace(
        project=project,
        model=project.model,
        viewport=ViewportStub(),
        status_message=StatusStub(),
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
    )
    dummy._geometry_sketch_snap = lambda _payload: next(snaps)
    for name in (
        "_geometry_sketch_tolerance",
        "_find_geometry_point_near",
        "_geometry_lines_containing_interior_point",
        "_materialize_geometry_sketch_point",
        "_existing_geometry_line_between",
        "_draw_geometry_line_segment",
        "_handle_geometry_line_sketch_click",
    ):
        setattr(
            dummy,
            name,
            getattr(MainWindow, name).__get__(dummy, type(dummy)),
        )
    dummy._refresh_geometry_sketch_snap_cache = lambda: None
    dummy._refresh_all = lambda *_args, **_kwargs: None
    dummy._record_project_change = lambda *_args, **_kwargs: None

    dummy._handle_geometry_line_sketch_click({})

    # P1 is only a preview anchor; cancel here would leave topology unchanged.
    assert len(project.points) == 2
    assert len(project.lines) == 1
    assert dummy._geometry_line_anchor_snap is not None

    dummy._handle_geometry_line_sketch_click({})

    # Committing P2 atomically materializes/splits the midpoint and creates
    # the new free-line segment.
    assert len(project.points) == 4
    assert len(project.lines) == 3
    assert dummy._geometry_line_anchor_snap is None
    assert dummy._geometry_line_point_tags == [4]
    assert project.points[3].xyz == pytest.approx((2.0, 0.0, 0.0))
    assert project.points[4].xyz == pytest.approx((2.0, 2.0, 0.0))


def test_geometry_free_line_three_clicks_commit_two_lines():
    project = ProjectDatabase(name="three-click-free-line")

    class SnapAction:
        def isChecked(self):
            return False

    class ViewportStub:
        def __init__(self):
            self.plane = ("xy", 0.0)

        def geometry_world_to_screen(self, xyz):
            return (float(xyz[0]) * 100.0, float(xyz[1]) * 100.0)

        def geometry_sketch_plane(self):
            return self.plane

        def set_geometry_sketch_plane_offset_from_point(self, xyz):
            self.plane = ("xy", float(xyz[2]))

        def show_geometry_sketch_preview(self, *_args, **_kwargs):
            return None

    class StatusStub:
        def setText(self, _text):
            return None

    dummy = SimpleNamespace(
        project=project,
        model=project.model,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        status_message=StatusStub(),
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
    )
    for name in (
        "_geometry_sketch_tolerance",
        "_geometry_point_on_active_sketch_plane",
        "_geometry_sketch_snap",
        "_find_geometry_point_near",
        "_geometry_lines_containing_interior_point",
        "_materialize_geometry_sketch_point",
        "_existing_geometry_line_between",
        "_draw_geometry_line_segment",
        "_handle_geometry_line_sketch_click",
    ):
        setattr(
            dummy,
            name,
            getattr(MainWindow, name).__get__(dummy, type(dummy)),
        )

    dummy._refresh_geometry_sketch_snap_cache = lambda: None
    dummy._refresh_all = lambda *_args, **_kwargs: None
    dummy._record_project_change = lambda *_args, **_kwargs: None

    for world, screen in (
        ((0.0, 0.0, 0.0), (100.0, 100.0)),
        ((2.0, 1.0, 0.0), (300.0, 200.0)),
        ((4.0, 3.0, 0.0), (500.0, 400.0)),
    ):
        dummy._handle_geometry_line_sketch_click(
            {
                "kind": None,
                "tag": None,
                "world": world,
                "screen": screen,
            }
        )

    assert len(project.points) == 3
    assert len(project.lines) == 2
    assert dummy._geometry_line_point_tags == [3]
    assert (project.lines[1].point_i, project.lines[1].point_j) == (1, 2)
    assert (project.lines[2].point_i, project.lines[2].point_j) == (2, 3)


def test_geometry_free_line_repeated_second_click_does_not_create_zero_length():
    project = ProjectDatabase(name="free-line-repeat-click")

    class SnapAction:
        def isChecked(self):
            return False

    class ViewportStub:
        def __init__(self):
            self.plane = ("xy", 0.0)

        def geometry_world_to_screen(self, xyz):
            return (float(xyz[0]) * 100.0, float(xyz[1]) * 100.0)

        def geometry_sketch_plane(self):
            return self.plane

        def set_geometry_sketch_plane_offset_from_point(self, xyz):
            self.plane = ("xy", float(xyz[2]))

        def show_geometry_sketch_preview(self, *_args, **_kwargs):
            return None

    class StatusStub:
        def setText(self, _text):
            return None

    dummy = SimpleNamespace(
        project=project,
        model=project.model,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        status_message=StatusStub(),
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
    )
    for name in (
        "_geometry_sketch_tolerance",
        "_geometry_point_on_active_sketch_plane",
        "_geometry_sketch_snap",
        "_find_geometry_point_near",
        "_geometry_lines_containing_interior_point",
        "_materialize_geometry_sketch_point",
        "_existing_geometry_line_between",
        "_draw_geometry_line_segment",
        "_handle_geometry_line_sketch_click",
    ):
        setattr(
            dummy,
            name,
            getattr(MainWindow, name).__get__(dummy, type(dummy)),
        )
    dummy._refresh_geometry_sketch_snap_cache = lambda: None
    dummy._refresh_all = lambda *_args, **_kwargs: None
    dummy._record_project_change = lambda *_args, **_kwargs: None

    first = {
        "kind": None,
        "tag": None,
        "world": (1.0, 1.0, 0.0),
        "screen": (100.0, 100.0),
    }
    dummy._handle_geometry_line_sketch_click(first)
    dummy._handle_geometry_line_sketch_click(first)

    assert dummy.project.points == {}
    assert dummy.project.lines == {}
    assert dummy._geometry_line_anchor_snap is not None

    dummy._handle_geometry_line_sketch_click(
        {
            "kind": None,
            "tag": None,
            "world": (3.0, 2.0, 0.0),
            "screen": (300.0, 200.0),
        }
    )
    assert len(dummy.project.points) == 2
    assert len(dummy.project.lines) == 1


def test_geometry_free_line_can_start_from_existing_endpoint_without_duplicate_point():
    project = ProjectDatabase(name="free-line-existing-endpoint")
    project.add_point(PointGeometryData(1, "Existing", (0.0, 0.0, 0.0)))

    class SnapAction:
        def isChecked(self):
            return True

    class ViewportStub:
        def __init__(self):
            self.plane = ("xy", 0.0)

        def geometry_world_to_screen(self, xyz):
            return (float(xyz[0]) * 100.0, float(xyz[1]) * 100.0)

        def geometry_sketch_plane(self):
            return self.plane

        def set_geometry_sketch_plane_offset_from_point(self, xyz):
            self.plane = ("xy", float(xyz[2]))

        def show_geometry_sketch_preview(self, *_args, **_kwargs):
            return None

    class StatusStub:
        def setText(self, _text):
            return None

    dummy = SimpleNamespace(
        project=project,
        model=project.model,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        status_message=StatusStub(),
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
    )
    for name in (
        "_geometry_sketch_tolerance",
        "_geometry_point_on_active_sketch_plane",
        "_geometry_sketch_snap",
        "_find_geometry_point_near",
        "_geometry_lines_containing_interior_point",
        "_materialize_geometry_sketch_point",
        "_existing_geometry_line_between",
        "_draw_geometry_line_segment",
        "_handle_geometry_line_sketch_click",
    ):
        setattr(
            dummy,
            name,
            getattr(MainWindow, name).__get__(dummy, type(dummy)),
        )
    dummy._refresh_geometry_sketch_snap_cache = lambda: None
    dummy._refresh_all = lambda *_args, **_kwargs: None
    dummy._record_project_change = lambda *_args, **_kwargs: None

    dummy._handle_geometry_line_sketch_click(
        {
            "kind": "geometry_point",
            "tag": 1,
            "world": (0.0, 0.0, 0.0),
            "screen": (0.0, 0.0),
        }
    )
    assert len(project.points) == 1
    assert project.lines == {}

    dummy._handle_geometry_line_sketch_click(
        {
            "kind": None,
            "tag": None,
            "world": (2.0, 1.0, 0.0),
            "screen": (200.0, 100.0),
        }
    )

    assert len(project.points) == 2
    assert len(project.lines) == 1
    assert project.lines[1].point_i == 1
    assert project.lines[1].point_j == 2


def test_geometry_free_line_three_clicks_with_snap_on_still_draw_freely():
    project = ProjectDatabase(name="three-click-free-line-snap-on")

    class SnapAction:
        def isChecked(self):
            return True

    class ViewportStub:
        def __init__(self):
            self.plane = ("xy", 0.0)

        def geometry_world_to_screen(self, xyz):
            return (float(xyz[0]) * 100.0, float(xyz[1]) * 100.0)

        def geometry_sketch_plane(self):
            return self.plane

        def set_geometry_sketch_plane_offset_from_point(self, xyz):
            self.plane = ("xy", float(xyz[2]))

        def show_geometry_sketch_preview(self, *_args, **_kwargs):
            return None

    class StatusStub:
        def setText(self, _text):
            return None

    dummy = SimpleNamespace(
        project=project,
        model=project.model,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        status_message=StatusStub(),
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
    )
    for name in (
        "_geometry_sketch_tolerance",
        "_geometry_point_on_active_sketch_plane",
        "_geometry_sketch_snap",
        "_find_geometry_point_near",
        "_geometry_lines_containing_interior_point",
        "_materialize_geometry_sketch_point",
        "_existing_geometry_line_between",
        "_draw_geometry_line_segment",
        "_handle_geometry_line_sketch_click",
    ):
        setattr(
            dummy,
            name,
            getattr(MainWindow, name).__get__(dummy, type(dummy)),
        )

    dummy._refresh_geometry_sketch_snap_cache = lambda: None
    dummy._refresh_all = lambda *_args, **_kwargs: None
    dummy._record_project_change = lambda *_args, **_kwargs: None

    for world in (
        (0.0, 0.0, 0.0),
        (2.0, 1.0, 0.0),
        (4.0, 3.0, 0.0),
    ):
        screen = (world[0] * 100.0, world[1] * 100.0)
        dummy._handle_geometry_line_sketch_click(
            {
                "kind": None,
                "tag": None,
                "world": world,
                "screen": screen,
            }
        )

    assert len(project.points) == 3
    assert len(project.lines) == 2
    assert dummy._geometry_line_point_tags == [3]
    assert dummy._geometry_line_anchor_snap is None


def test_geometry_snap_off_ignores_even_exact_existing_point_hit():
    project = ProjectDatabase(name="snap-off-exact-hit")
    project.add_point(PointGeometryData(1, "Existing", (0.0, 0.0, 0.0)))

    class SnapAction:
        def isChecked(self):
            return False

    class ViewportStub:
        def geometry_world_to_screen(self, _xyz):
            return (100.0, 100.0)

        def geometry_sketch_plane(self):
            return ("xy", 0.0)

    dummy = SimpleNamespace(
        project=project,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
        _geometry_point_on_active_sketch_plane=lambda _xyz: True,
    )

    snap = MainWindow._geometry_sketch_snap(
        dummy,
        {
            "kind": "geometry_point",
            "tag": 1,
            "world": (0.03, 0.02, 0.0),
            "screen": (100.0, 100.0),
        },
    )

    assert snap is not None
    assert snap["kind"] == "free"
    assert snap["point_tag"] is None
    assert snap["xyz"] == pytest.approx((0.03, 0.02, 0.0))


def test_geometry_free_line_ignores_stale_far_point_picker_hit():
    project = ProjectDatabase(name="free-line-snap")
    project.add_point(PointGeometryData(1, "Anchor", (0.0, 0.0, 0.0)))

    class SnapAction:
        def isChecked(self):
            return True

    class ViewportStub:
        def geometry_world_to_screen(self, _xyz):
            return (100.0, 100.0)

        def geometry_sketch_plane(self):
            return ("xy", 0.0)

    dummy = SimpleNamespace(
        project=project,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        _geometry_line_point_tags=[1],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[],
        _geometry_point_on_active_sketch_plane=lambda _xyz: True,
    )

    snap = MainWindow._geometry_sketch_snap(
        dummy,
        {
            "kind": "geometry_point",
            "tag": 1,
            "world": (2.0, 3.0, 0.0),
            "screen": (300.0, 300.0),
        },
    )

    assert snap is not None
    assert snap["kind"] == "free"
    assert snap["point_tag"] is None
    assert snap["xyz"] == pytest.approx((2.0, 3.0, 0.0))


def test_geometry_free_line_redraw_preserves_exact_camera_state():
    render = inspect.getsource(ModelViewport._render_model)

    assert "preserved_camera = self.plotter.camera_position" in render
    assert "if preserved_camera is not None:" in render
    assert "self.plotter.camera_position = preserved_camera" in render
    geometry_tail = render.split(
        'if self._display_domain == "geometry":', 1
    )[1].split("return", 1)[0]
    assert (
        "self.set_view(self._current_view, render=False)"
        in geometry_tail
    )
    assert "else:" in geometry_tail


def test_geometry_free_line_undo_redo_resets_stale_chain_anchor():
    snapshot = inspect.getsource(MainWindow._apply_project_snapshot)

    assert "sketch_active = self._geometry_sketch_tool_active()" in snapshot
    assert "self._geometry_line_point_tags = []" in snapshot
    assert "self._geometry_line_anchor_snap = None" in snapshot
    assert "reset_camera=not sketch_active" in snapshot
    assert 'set_interaction_tool("geometry_sketch")' in snapshot


def test_geometry_view_change_cannot_leave_sketch_on_edge_on_old_plane():
    view_action = inspect.getsource(MainWindow._set_view_from_ui)
    build = inspect.getsource(MainWindow._build_actions_and_ribbon)
    wire = inspect.getsource(MainWindow._wire_selection)
    viewport_init = inspect.getsource(ModelViewport.__init__)

    assert "self._set_view_from_ui(v)" in build
    assert "view_requested.connect(self._set_view_from_ui)" in wire
    assert "self.view_requested.emit(v)" in viewport_init
    assert 'self.view_requested.emit("iso")' in viewport_init
    assert 'target in {"xy", "xz", "yz"}' in view_action
    assert "_reset_active_geometry_sketch_anchor()" in view_action
    assert "set_geometry_sketch_plane(target, 0.0)" in view_action
    assert 'set_interaction_tool("geometry_sketch")' in view_action


def test_geometry_tree_switch_to_fe_domain_exits_active_sketch():
    tree_change = inspect.getsource(MainWindow._tree_selection_changed)

    assert "not geometry_mode and self._geometry_sketch_tool_active()" in tree_change
    assert "self._activate_select_tool()" in tree_change
    assert '"geometry" if geometry_mode else "fe"' in tree_change


def test_geometry_double_click_finishes_sketch_instead_of_editing_entity():
    event_filter = inspect.getsource(ModelViewport.eventFilter)
    marker = (
        'event.button() == Qt.LeftButton\n'
        '                and self._interaction_tool == "geometry_sketch"'
    )

    assert marker in event_filter
    assert "self._left_press_pos = None" in event_filter
    assert "self.geometry_sketch_finished.emit()" in event_filter


def test_geometry_sketch_tolerance_is_bounded_for_huge_coordinates():
    project = ProjectDatabase(name="huge-coordinate-sketch")
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(
        PointGeometryData(2, "B", (1.0e12, 0.0, 0.0))
    )
    dummy = SimpleNamespace(project=project)

    tolerance = MainWindow._geometry_sketch_tolerance(dummy)

    assert 1.0e-9 <= tolerance <= 1.0e-6


def test_geometry_sketch_rejects_nonfinite_mouse_payloads():
    dummy = SimpleNamespace(
        project=ProjectDatabase(name="invalid-sketch-payload"),
        actions={},
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
    )

    assert MainWindow._geometry_sketch_snap(
        dummy,
        {
            "world": (math.nan, 0.0, 0.0),
            "screen": (10.0, 10.0),
        },
    ) is None
    assert MainWindow._geometry_sketch_snap(
        dummy,
        {
            "world": (0.0, 0.0, 0.0),
            "screen": (math.inf, 10.0),
        },
    ) is None


def test_geometry_snap_prefers_visually_nearest_candidate_over_type_priority():
    project = ProjectDatabase(name="nearest-snap")
    project.add_point(PointGeometryData(1, "Endpoint", (0.15, 0.0, 0.0)))

    class SnapAction:
        def isChecked(self):
            return True

    class ViewportStub:
        def geometry_world_to_screen(self, xyz):
            return (float(xyz[0]) * 100.0, float(xyz[1]) * 100.0)

        def geometry_sketch_plane(self):
            return ("xy", 0.0)

    dummy = SimpleNamespace(
        project=project,
        viewport=ViewportStub(),
        actions={"geometry_snap": SnapAction()},
        _geometry_line_point_tags=[],
        _geometry_line_anchor_snap=None,
        _geometry_surface_point_tags=[],
        _geometry_sketch_intersections=[
            SimpleNamespace(
                point=(0.01, 0.0, 0.0),
                line_tags=(10, 11),
                parameters=(0.5, 0.5),
            )
        ],
    )
    dummy._geometry_point_on_active_sketch_plane = lambda _xyz: True

    snap = MainWindow._geometry_sketch_snap(
        dummy,
        {
            "world": (0.0, 0.0, 0.0),
            "screen": (0.0, 0.0),
        },
    )

    assert snap is not None
    assert snap["kind"] == "intersection"
    assert snap["xyz"] == pytest.approx((0.01, 0.0, 0.0))


def test_geometry_sketch_tool_switch_clears_ghost_mouse_state():
    source = inspect.getsource(ModelViewport.set_interaction_tool)

    for state in (
        "_left_press_pos = None",
        "_right_press_pos = None",
        "_nav_mode = None",
        "_nav_last_pos = None",
        "_last_geometry_sketch_qt_pos = None",
        "_pending_hover_vtk_pos = None",
    ):
        assert state in source


def test_geometry_sketch_plain_middle_mouse_cannot_rotate_workplane_edge_on():
    source = inspect.getsource(ModelViewport._start_navigation)

    assert 'self._interaction_tool == "geometry_sketch"' in source
    assert 'self._nav_mode = "pan"' in source
    assert 'self._nav_mode = "rotate"' in source


def test_geometry_sketch_navigation_invalidates_stale_cursor_preview():
    start = inspect.getsource(ModelViewport._start_navigation)
    wheel = inspect.getsource(ModelViewport._wheel_zoom)
    helper = inspect.getsource(
        ModelViewport._invalidate_geometry_sketch_cursor_preview
    )

    assert "_invalidate_geometry_sketch_cursor_preview" in start
    assert "_invalidate_geometry_sketch_cursor_preview" in wheel
    assert '["cursor"] = None' in helper
    assert '["snap_label"] = None' in helper
    assert "_last_geometry_sketch_qt_pos = None" in helper


def test_geometry_workplane_mapping_rejects_nonfinite_and_out_of_clip_hits():
    source = inspect.getsource(ModelViewport.geometry_workplane_point)

    assert "np.all(np.isfinite(near))" in source
    assert "np.all(np.isfinite(far))" in source
    assert "math.isfinite(denominator)" in source
    assert "not math.isfinite(t)" in source
    assert "t < -1.0e-6" in source
    assert "t > 1.0 + 1.0e-6" in source
    assert "np.all(np.isfinite(point))" in source


def test_geometry_sketch_plane_rejects_nan_inf_offsets_and_points():
    plane = inspect.getsource(ModelViewport.set_geometry_sketch_plane)
    offset = inspect.getsource(
        ModelViewport.set_geometry_sketch_plane_offset_from_point
    )

    assert "math.isfinite(numeric_offset)" in plane
    assert "offset must be finite" in plane
    assert "all(math.isfinite(value) for value in point)" in offset
    assert "coordinates must be finite" in offset


def test_geometry_view_change_validates_name_and_resets_sketch_cursor_state():
    source = inspect.getsource(ModelViewport.set_view)

    assert "normalized = str(view).strip().lower()" in source
    assert "if normalized not in functions:" in source
    assert "Viewport view must be iso, xy, xz, or yz." in source
    assert "_invalidate_geometry_sketch_cursor_preview" in source
    assert "self._current_view = normalized" in source


def test_geometry_redraw_and_domain_switch_reset_stale_sketch_pointer_state():
    draw = inspect.getsource(ModelViewport.draw_model)
    domain = inspect.getsource(ModelViewport.set_display_domain)

    assert "_last_geometry_sketch_qt_pos = None" in draw
    assert "_left_press_pos = None" in domain
    assert "_right_press_pos = None" in domain
    assert "_last_geometry_sketch_qt_pos = None" in domain
    assert 'normalized != "geometry"' in domain
    assert "clear_geometry_sketch_preview" in domain


def test_geometry_rectangle_draw_uses_two_click_geometry_only_surface():
    rectangle = inspect.getsource(
        MainWindow._handle_geometry_rectangle_sketch_click
    )
    corners = inspect.getsource(
        MainWindow._rectangle_corners_from_diagonal
    )

    assert "opposite corner" in rectangle
    assert "SurfaceGeometryData" in rectangle
    assert 'surface_type="Rectangle"' in rectangle
    assert "mesh_recipe_configured=False" in rectangle
    assert "section_tag=None" in rectangle
    assert 'plane == "xy"' in corners
    assert 'plane == "xz"' in corners


def test_geometry_sketch_has_live_preview_and_right_click_finish():
    wire = inspect.getsource(MainWindow._wire_selection)
    moved = inspect.getsource(
        MainWindow._viewport_geometry_sketch_moved
    )
    preview = inspect.getsource(
        ModelViewport.show_geometry_sketch_preview
    )
    event_filter = inspect.getsource(ModelViewport.eventFilter)

    assert "geometry_sketch_moved.connect" in wire
    assert "geometry_sketch_finished.connect" in wire
    assert "show_geometry_sketch_preview" in moved
    assert "_geometry_sketch_preview" in preview
    assert "geometry_sketch_finished.emit()" in event_filter

def test_geometry_ribbon_tab_groups_spaceclaim_style_tools():
    ribbon = inspect.getsource(MainWindow._build_actions_and_ribbon)

    assert 'self.ribbon_tabs.addTab(' in ribbon
    assert 'geometry_page = RibbonPage()' in ribbon
    assert 'geometry_plan_view_button' in ribbon
    assert 'geometry_plan_view_popup.addAction(self.actions["xy"])' in ribbon
    assert '"Orient"' in ribbon
    assert '"Create"' in ribbon
    assert '"Modify"' in ribbon
    assert '"Sketch Aids"' in ribbon
    assert '"Mesh Preview"' in ribbon
    assert 'geometry_surface_button.setText("Rectangle")' in ribbon
    assert (
        'geometry_index = self.ribbon_tabs.addTab(\n'
        '            geometry_page,\n'
        '            "Sketch",\n'
        '        )'
    ) in ribbon
    assert 'geometry_page,\n            "Create"' in ribbon
    assert 'geometry_page,\n            "Modify"' in ribbon
    assert '"geometry_trim_pick"' in ribbon
    assert '"geometry_extend_pick"' in ribbon
    assert '"geometry_split"' in ribbon
    assert '"geometry_join"' in ribbon
    assert '"geometry_split_by_line"' in ribbon
    assert '"geometry_fillet"' in ribbon
    assert '"geometry_chamfer"' in ribbon
    assert '"geometry_trim_multiple"' in ribbon
    assert '"geometry_extend_multiple"' in ribbon
    assert '"geometry_snap"' in ribbon
    assert '"geometry_grid"' in ribbon


def test_geometry_lines_are_pickable_hoverable_and_tree_selectable():
    render = inspect.getsource(ModelViewport._render_model)
    picking = inspect.getsource(ModelViewport.pick_entity)
    highlight = inspect.getsource(
        ModelViewport._update_highlight_overlays
    )
    selection = inspect.getsource(
        MainWindow._select_geometry_line_from_viewport
    )

    assert 'name="line-geometry"' in render
    assert "pickable=True" in render
    assert "_cell_picker.AddPickList" in render
    assert '"geometry_line"' in picking
    assert '"hover-geometry-line"' in highlight
    assert '"selection-geometry-lines"' in highlight
    assert "_tree_line_items" in selection


def test_geometry_trim_and_extend_are_strict_click_side_workflows():
    activate = inspect.getsource(
        MainWindow._activate_geometry_line_target_tool
    )
    trim = inspect.getsource(MainWindow._activate_geometry_trim_tool)
    extend = inspect.getsource(MainWindow._activate_geometry_extend_tool)
    endpoint = inspect.getsource(
        MainWindow._geometry_line_endpoint_from_click
    )
    handle = inspect.getsource(
        MainWindow._handle_geometry_trim_click
    )
    click = inspect.getsource(MainWindow._viewport_entity_clicked)

    assert "click the side of the Geometry Line" in activate
    assert '_activate_geometry_line_target_tool("trim"' in trim
    assert '_activate_geometry_line_target_tool("extend"' in extend
    assert "_world_to_qt" in endpoint
    assert "_geometry_trim_endpoint" in handle
    assert "trim_extend_line_to_line" in handle
    assert "operation=operation" in handle
    assert "geometry_trim_pick" in click
    assert "geometry_extend_pick" in click
    assert "_handle_geometry_trim_click(payload)" in click


def test_geometry_second_cad_batch_is_wired_to_real_operations():
    split = inspect.getsource(
        MainWindow._split_selected_geometry_lines_at_intersection
    )
    fillet = inspect.getsource(
        MainWindow._fillet_selected_geometry_lines
    )
    chamfer = inspect.getsource(
        MainWindow._chamfer_selected_geometry_lines
    )
    batch_activate = inspect.getsource(
        MainWindow._activate_geometry_batch_target_tool
    )
    batch_handle = inspect.getsource(
        MainWindow._handle_geometry_batch_target_click
    )
    click = inspect.getsource(MainWindow._viewport_entity_clicked)

    assert "split_line_pair_at_intersection" in split
    assert "fillet_lines" in fillet
    assert "segments=8" in fillet
    assert "chamfer_lines" in chamfer
    assert "at least two Geometry Lines" in batch_activate
    assert "trim_extend_lines_to_line" in batch_handle
    assert "geometry_trim_multiple" in click
    assert "geometry_extend_multiple" in click


def test_geometry_snap_has_orthogonal_inference_and_toggle():
    snap = inspect.getsource(MainWindow._geometry_sketch_snap)
    toggle = inspect.getsource(MainWindow._toggle_geometry_snap)

    assert 'self.actions.get("geometry_snap")' in snap
    assert '"orthogonal"' in snap
    assert "Orthogonal ·" in snap
    assert '"Horizontal"' in snap
    assert '"Vertical"' in snap
    assert "Geometry snapping" in toggle


def test_geometry_sketch_grid_is_workplane_aware_and_toggleable():
    toggle = inspect.getsource(MainWindow._toggle_geometry_grid)
    setter = inspect.getsource(
        ModelViewport.set_geometry_sketch_grid_visible
    )
    render = inspect.getsource(
        ModelViewport._render_geometry_sketch_grid
    )

    assert "set_geometry_sketch_grid_visible" in toggle
    assert "_geometry_sketch_grid_visible" in setter
    assert '"xy": (0, 1, 2)' in render
    assert '"xz": (0, 2, 1)' in render
    assert '"yz": (1, 2, 0)' in render
    assert 'name="geometry-sketch-grid"' in render


def test_geometry_tools_are_mutually_exclusive():
    line = inspect.getsource(
        MainWindow._activate_geometry_line_pick_tool
    )
    surface = inspect.getsource(
        MainWindow._activate_geometry_surface_pick_tool
    )
    frame = inspect.getsource(MainWindow._activate_frame_pick_tool)

    assert "_leave_geometry_trim_mode" in line
    assert "_leave_geometry_trim_mode" in surface
    assert "_leave_geometry_trim_mode" in frame

