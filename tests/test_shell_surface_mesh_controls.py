from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    SurfaceGeometryData,
)
from openseespy_studio.shell_mesh import (
    biased_mesh_coordinates,
)
from openseespy_studio.surface_mesher import (
    audit_surface_conformity,
    mesh_surface_geometry,
    rectangle_surface_points,
    surface_mesh_preview_segments,
    surface_preview_divisions,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog
from openseespy_studio.ui.viewport import ModelViewport


def _shell_section(tag: int = 1) -> SectionData:
    return SectionData(
        tag,
        "Shell",
        "ElasticMembranePlate",
        parameters={
            "E": 30.0e9,
            "nu": 0.2,
            "h": 0.15,
            "rho": 0.0,
            "EpModifier": 1.0,
        },
    )


def _project() -> ProjectDatabase:
    project = ProjectDatabase(name="advanced-surface-mesh")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_shell_section())
    return project


def test_biased_mesh_coordinates_match_requested_end_start_ratio():
    coordinates = biased_mesh_coordinates(5, 4.0)
    widths = [
        coordinates[index + 1] - coordinates[index]
        for index in range(5)
    ]

    assert coordinates[0] == pytest.approx(0.0)
    assert coordinates[-1] == pytest.approx(1.0)
    assert all(
        widths[index + 1] > widths[index]
        for index in range(len(widths) - 1)
    )
    assert widths[-1] / widths[0] == pytest.approx(4.0)

    reversed_coordinates = biased_mesh_coordinates(5, 0.25)
    reversed_widths = [
        reversed_coordinates[index + 1] - reversed_coordinates[index]
        for index in range(5)
    ]
    assert reversed_widths[-1] / reversed_widths[0] == pytest.approx(0.25)


def test_surface_edge_seeds_override_global_divisions_and_round_trip():
    surface = SurfaceGeometryData(
        1,
        "Seeded",
        points=rectangle_surface_points((0, 0, 0), 6, 3),
        section_tag=1,
        divisions_u=2,
        divisions_v=2,
        bias_u=3.0,
        bias_v=0.5,
        edge_divisions=(6, 3, 6, 3),
    )

    assert surface_preview_divisions(surface) == (6, 3)
    nu, nv, segments = surface_mesh_preview_segments(surface)
    assert (nu, nv) == (6, 3)
    assert len(segments) == (nu + 1) * nv + (nv + 1) * nu

    restored = SurfaceGeometryData.from_dict(surface.to_dict())
    assert restored.bias_u == pytest.approx(3.0)
    assert restored.bias_v == pytest.approx(0.5)
    assert restored.edge_divisions == (6, 3, 6, 3)


def test_mapped_surface_rejects_incompatible_opposite_edge_seeds():
    with pytest.raises(ValueError, match="opposite edges 1 and 3"):
        SurfaceGeometryData(
            1,
            "Bad seeds",
            points=rectangle_surface_points((0, 0, 0), 2, 1),
            section_tag=1,
            edge_divisions=(4, None, 5, None),
        )


def test_biased_surface_mesh_generates_nonuniform_node_spacing():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Biased",
            points=rectangle_surface_points((0, 0, 0), 10, 1),
            section_tag=1,
            divisions_u=5,
            divisions_v=1,
            bias_u=4.0,
            conform_existing_edges=False,
        )
    )

    result = mesh_surface_geometry(project, 1)
    bottom = result.grid[0]
    xs = [project.model.nodes[tag].xyz[0] for tag in bottom]
    widths = [xs[index + 1] - xs[index] for index in range(5)]

    assert len(result.element_tags) == 5
    assert widths[-1] / widths[0] == pytest.approx(4.0)


def test_adjacent_surface_conforms_to_existing_biased_edge_positions():
    project = _project()
    project.add_surface(
        SurfaceGeometryData(
            1,
            "Left",
            points=rectangle_surface_points((0, 0, 0), 1, 4),
            section_tag=1,
            divisions_u=1,
            divisions_v=4,
            bias_v=5.0,
            conform_existing_edges=True,
        )
    )
    first = mesh_surface_geometry(project, 1)

    project.add_surface(
        SurfaceGeometryData(
            2,
            "Right",
            points=rectangle_surface_points((1, 0, 0), 1, 4),
            section_tag=1,
            divisions_u=1,
            divisions_v=4,
            bias_v=1.0,
            conform_existing_edges=True,
        )
    )
    second = mesh_surface_geometry(project, 2)

    assert first.divisions_v == 4
    assert second.divisions_v == 4
    assert second.conformed_v is True

    report = audit_surface_conformity(project, [1, 2])
    assert report.shared_edge_count == 1
    assert report.conforming is True


def test_surface_editor_exposes_bias_edge_seeds_and_mesh_preview():
    source = inspect.getsource(SurfaceGeometryDialog)

    assert "Bias U (end/start)" in source
    assert "Bias V (end/start)" in source
    assert "Edge seeds:" in source
    assert "self.edge_seed_spins" in source
    assert "bias_u=self.bias_u.value()" in source
    assert "bias_v=self.bias_v.value()" in source


def test_surface_quality_visualization_is_geometry_only_non_pickable():
    source = inspect.getsource(ModelViewport._render_surface_quality_overlay)
    route = inspect.getsource(MainWindow._show_surface_quality_map)

    assert '"surface-quality-overlay"' in source
    assert 'pickable=False' in source
    assert '"aspect_ratio"' in source
    assert '"skew"' in source
    assert '"warpage"' in source
    assert "show_surface_mesh_quality" in route


def test_surface_copy_preserves_recipe_but_clears_generated_fe_provenance():
    source = inspect.getsource(MainWindow._copy_surface_geometries)

    assert "source.to_dict()" in source
    assert '"generated_node_tags": []' in source
    assert '"generated_element_tags": []' in source
    assert "PointGeometryData" in source
    assert "SurfaceGeometryData.from_dict" in source
    assert "mesh recipe and Shell Section preserved" in source


def test_surface_pressure_preview_uses_signed_surface_normal():
    viewport = inspect.getsource(
        ModelViewport._render_surface_pressure_preview
    )
    route = inspect.getsource(MainWindow._preview_surface_pressure)
    context = inspect.getsource(MainWindow._show_tree_context_menu)

    assert "pressure >= 0.0" in viewport
    assert '"(+N)"' in viewport
    assert '"(-N)"' in viewport
    assert "show_surface_pressure_preview" in route
    assert "Preview Pressure Direction..." in context
    assert "Clear Pressure Preview" in context


def test_surface_context_exposes_copy_and_quality_map_tools():
    source = inspect.getsource(MainWindow._show_tree_context_menu)

    assert "Copy / Offset Surface..." in source
    assert "Visualize Mesh Quality" in source
    assert "Aspect Ratio" in source
    assert "Warpage" in source
