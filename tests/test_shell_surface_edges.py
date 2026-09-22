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
    surface_boundary_edges,
    surface_boundary_node_tags,
    surface_edge_info,
    surface_edge_node_tags,
)
from openseespy_studio.ui.main_window import MainWindow
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
    project = ProjectDatabase(name="surface-edge-tools")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_section())
    return project


def test_surface_edge_nodes_are_ordered_on_biased_seeded_mesh():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Biased",
            points=rectangle_surface_points((0, 0, 0), 10, 2),
            section_tag=7,
            divisions_u=5,
            divisions_v=2,
            bias_u=4.0,
            edge_divisions=(5, 2, 5, 2),
            conform_existing_edges=False,
        )
    )
    mesh_surface_geometry(project, 1)

    node_tags = surface_edge_node_tags(project, 1, 1)
    xs = [project.model.nodes[tag].xyz[0] for tag in node_tags]

    assert len(node_tags) == 6
    assert xs == sorted(xs)
    widths = [xs[index + 1] - xs[index] for index in range(5)]
    assert widths[-1] / widths[0] == pytest.approx(4.0)

    info = surface_edge_info(project, 1, 1)
    assert info.requested_divisions == 5
    assert info.actual_divisions == 5
    assert info.length == pytest.approx(10.0)
    assert info.connectivity_status == "boundary"


def test_surface_edge_info_reports_connected_shared_neighbor():
    project = _project()
    for tag, origin in ((1, (0, 0, 0)), (2, (1, 0, 0))):
        project.add_surface(
            SurfaceGeometryData(
                tag,
                f"S{tag}",
                points=rectangle_surface_points(origin, 1, 1),
                section_tag=7,
                divisions_u=1,
                divisions_v=2,
            )
        )
    mesh_surface_geometry(project, 1)
    mesh_surface_geometry(project, 2)

    left = surface_edge_info(project, 1, 2)

    assert left.neighbor_edges == [(2, 4)]
    assert left.connected_neighbor_edges == [(2, 4)]
    assert left.connectivity_status == "shared"
    assert len(left.live_node_tags) == 3


def test_surface_outer_boundary_excludes_internal_shared_edge_midpoint():
    project = _project()
    for tag, origin in ((1, (0, 0, 0)), (2, (1, 0, 0))):
        project.add_surface(
            SurfaceGeometryData(
                tag,
                f"S{tag}",
                points=rectangle_surface_points(origin, 1, 1),
                section_tag=7,
                divisions_u=1,
                divisions_v=2,
            )
        )
    mesh_surface_geometry(project, 1)
    mesh_surface_geometry(project, 2)

    edges = surface_boundary_edges(project, [1, 2])
    nodes = surface_boundary_node_tags(project, [1, 2])

    assert len(edges) == 6
    internal_midpoint = next(
        node.tag
        for node in project.model.nodes.values()
        if node.xyz == pytest.approx((1.0, 0.5, 0.0))
    )
    assert internal_midpoint not in nodes
    assert all(
        not (
            info.surface_tag == 1 and info.edge_index == 2
            or info.surface_tag == 2 and info.edge_index == 4
        )
        for info in edges
    )


def test_surface_boundary_nodes_require_live_mesh():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Unmeshed",
            points=rectangle_surface_points((0, 0, 0), 1, 1),
            section_tag=7,
        )
    )

    with pytest.raises(ValueError, match="Mesh the following Surface"):
        surface_boundary_node_tags(project, [1])


def test_surface_edge_preview_is_geometry_only_and_non_pickable():
    show = inspect.getsource(ModelViewport.show_surface_edge_preview)
    render = inspect.getsource(ModelViewport._render_surface_edge_preview)
    model_render = inspect.getsource(ModelViewport._render_model)

    assert "_surface_edge_preview_refs" in show
    assert 'name="surface-edge-preview"' in render
    assert 'name="surface-edge-preview-labels"' in render
    assert "pickable=False" in render
    assert "S{surface_tag}:E{edge_index}" in render
    assert "_render_surface_edge_preview()" in model_render


def test_surface_context_exposes_edge_inspection_and_fe_selection_bridge():
    source = inspect.getsource(MainWindow._show_tree_context_menu)
    inspect_edges = inspect.getsource(MainWindow._inspect_surface_edges)
    select_edge = inspect.getsource(MainWindow._select_surface_edge_nodes)
    select_boundary = inspect.getsource(
        MainWindow._select_surface_boundary_nodes
    )

    assert "Inspect / Preview Surface Edges" in source
    assert "Select Edge FE Nodes..." in source
    assert "Preview Outer Boundary" in source
    assert "Select Outer Boundary FE Nodes" in source
    assert "Clear Edge Preview" in source

    assert "surface_edge_info" in inspect_edges
    assert "show_surface_edge_preview" in inspect_edges
    assert "surface_edge_node_tags" in select_edge
    assert 'set_display_domain("fe")' in select_edge
    assert "self.selection.set_selection(nodes=set(node_tags))" in select_edge
    assert "surface_boundary_node_tags" in select_boundary
    assert "surface_boundary_edges" in select_boundary
