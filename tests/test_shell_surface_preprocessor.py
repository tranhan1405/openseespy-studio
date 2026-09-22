from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    SurfaceGeometryData,
)
from openseespy_studio.surface_mesher import (
    audit_surface_conformity,
    mesh_surface_geometry,
    rectangle_surface_points,
    surface_mesh_preview_segments,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog
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
    project = ProjectDatabase(name="surface-preprocessor")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_section())
    return project


def test_surface_mesh_preview_is_non_destructive_and_matches_divisions():
    project = _project()
    surface = SurfaceGeometryData(
        1,
        "Panel",
        points=rectangle_surface_points((0, 0, 0), 2, 1),
        section_tag=7,
        divisions_u=2,
        divisions_v=1,
    )
    project.add_surface(surface)

    nu, nv, segments = surface_mesh_preview_segments(surface)

    assert (nu, nv) == (2, 1)
    assert len(segments) == (nu + 1) * nv + (nv + 1) * nu
    assert project.model.nodes == {}
    assert project.model.elements == {}
    assert surface.generated_node_tags == []
    assert surface.generated_element_tags == []


def test_surface_mesh_preview_resolves_target_size():
    surface = SurfaceGeometryData(
        1,
        "Sized",
        points=rectangle_surface_points((0, 0, 0), 4, 2),
        section_tag=7,
        mesh_mode="target_size",
        target_size=1.1,
    )

    nu, nv, _segments = surface_mesh_preview_segments(surface)

    assert (nu, nv) == (4, 2)


def test_conformity_audit_detects_requested_shared_edge_division_mismatch():
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
            divisions_v=3,
        )
    )

    report = audit_surface_conformity(project, [1, 2])

    assert report.shared_edge_count == 1
    assert report.conforming is False
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "division_mismatch"
    assert {report.issues[0].divisions_a, report.issues[0].divisions_b} == {
        2,
        3,
    }


def test_conformity_audit_accepts_automatic_conforming_shared_mesh():
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
            divisions_v=3,
        )
    )

    mesh_surface_geometry(project, 1)
    right = mesh_surface_geometry(project, 2)
    assert right.conformed_v is True
    assert right.divisions_v == 2

    report = audit_surface_conformity(project, [1, 2])

    assert report.shared_edge_count == 1
    assert report.conforming is True
    assert report.issues == []


def test_conformity_audit_detects_coincident_but_disconnected_fe_edges():
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
                reuse_existing_nodes=False,
                conform_existing_edges=False,
            )
        )

    mesh_surface_geometry(project, 1)
    mesh_surface_geometry(project, 2)
    report = audit_surface_conformity(project, [1, 2])

    assert report.shared_edge_count == 1
    assert report.conforming is False
    assert any(
        issue.issue_type == "disconnected_nodes"
        for issue in report.issues
    )


def test_geometry_surface_is_pickable_and_highlightable():
    render = inspect.getsource(ModelViewport._render_model)
    picker = inspect.getsource(ModelViewport.pick_entity)
    highlight = inspect.getsource(
        ModelViewport._update_highlight_overlays
    )

    assert 'name="surface-geometry"' in render
    assert "pickable=True" in render
    assert "self._cell_picker.AddPickList" in render
    assert '"geometry_surface"' in picker
    assert "_geometry_surface_actor" in picker
    assert "selection-geometry-surfaces" in highlight
    assert "hover-geometry-surface" in highlight


def test_viewport_surface_click_routes_to_tree_geometry_selection():
    click = inspect.getsource(MainWindow._viewport_entity_clicked)
    helper = inspect.getsource(
        MainWindow._select_geometry_surface_from_viewport
    )
    tree = inspect.getsource(MainWindow._refresh_tree)

    assert 'kind == "geometry_surface"' in click
    assert "_select_geometry_surface_from_viewport" in click
    assert 'mode == "replace"' in helper
    assert 'mode == "add"' in helper
    assert 'mode == "toggle"' in helper
    assert "_tree_surface_items" in tree


def test_surface_editor_exposes_live_non_destructive_mesh_preview():
    init_source = inspect.getsource(SurfaceGeometryDialog.__init__)
    preview_source = inspect.getsource(SurfaceGeometryDialog._preview_mesh)
    viewport_source = inspect.getsource(
        ModelViewport.show_surface_mesh_definition_preview
    )

    assert "preview_callback" in init_source
    assert '"Preview Mesh"' in init_source
    assert "self.data()" in preview_source
    assert "_preview_callback(surface)" in preview_source
    assert "surface_mesh_preview_segments" in viewport_source
    assert 'name="surface-mesh-preview"' in viewport_source
    assert "pickable=False" in viewport_source


def test_surface_context_has_batch_section_preview_and_conformity_commands():
    source = inspect.getsource(MainWindow._show_tree_context_menu)
    assign = inspect.getsource(
        MainWindow._assign_shell_section_to_surfaces
    )
    audit = inspect.getsource(MainWindow._audit_surface_conformity)

    assert "Assign Shell Section" in source
    assert "Preview Mesh" in source
    assert "Audit Shared-Edge Conformity" in source
    assert "Audit Mesh Integrity" in source
    assert "_audit_surface_mesh_integrity" in source
    assert "_assign_shell_section_to_surfaces" in source
    assert "_preview_surface_meshes" in source
    assert "_audit_surface_conformity" in source

    assert "surface.section_tag = section_tag" in assign
    assert "element.section_tag = section_tag" in assign
    assert "audit_surface_conformity" in audit
    assert "Surface Conformity Audit" in audit
