from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    ElementLoadData,
    LoadPatternData,
    ProjectDatabase,
    SectionData,
    SurfaceGeometryData,
    SurfacePressureData,
    TimeSeriesData,
)
from openseespy_studio.surface_mesher import (
    flip_surface_orientation,
    managed_surface_pressure_element_load_tags,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    remove_surface_pressure,
    surface_unit_normal,
    sync_surface_pressure,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_pressure_dialog import SurfacePressureDialog


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
    project = ProjectDatabase(name="managed-surface-pressure")
    project.model.ndm = 3
    project.model.ndf = 6
    project.add_section(_section())
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Pressure",
            "Plain",
            time_series_tag=1,
        )
    )
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
            conform_existing_edges=False,
        )
    )
    mesh_surface_geometry(project, 1)
    return project


def test_managed_surface_pressure_round_trips_with_generated_provenance():
    project = _meshed_project()
    pressure = SurfacePressureData(
        1,
        "Gravity pressure",
        1,
        1,
        -3.5,
    )
    project.add_surface_pressure(pressure)
    generated = sync_surface_pressure(project, 1)

    restored = ProjectDatabase.from_dict(project.to_dict())
    item = restored.surface_pressures[1]

    assert item.surface_tag == 1
    assert item.pattern_tag == 1
    assert item.pressure == pytest.approx(-3.5)
    assert item.generated_element_load_tags == generated
    assert set(generated) == managed_surface_pressure_element_load_tags(
        restored
    )
    assert all(
        restored.element_loads[tag].load_type == "SurfacePressure"
        for tag in generated
    )


def test_managed_pressure_rebinds_to_new_shell_mesh_after_remesh():
    project = _meshed_project(divisions_u=1, divisions_v=1)
    pressure = SurfacePressureData(1, "p", 1, 1, -2.0)
    project.add_surface_pressure(pressure)
    old_generated = sync_surface_pressure(project, 1)
    assert len(old_generated) == 1

    project.surfaces[1].divisions_u = 4
    project.surfaces[1].divisions_v = 2
    remesh_surface_geometry(project, 1)

    item = project.surface_pressures[1]
    new_generated = item.generated_element_load_tags
    assert len(new_generated) == 8
    assert set(project.element_loads) == set(new_generated)
    assert all(
        project.element_loads[tag].pressure == pytest.approx(-2.0)
        for tag in new_generated
    )


def test_direct_fe_surface_pressure_still_blocks_surface_remesh():
    project = _meshed_project()
    element_tag = project.surfaces[1].generated_element_tags[0]
    project.add_element_load(
        ElementLoadData(
            99,
            "Direct FE pressure",
            1,
            element_tag,
            load_type="SurfacePressure",
            pressure=-1.0,
        )
    )

    with pytest.raises(ValueError, match="element load"):
        remesh_surface_geometry(project, 1)


def test_flip_surface_preserves_global_pressure_direction():
    project = _meshed_project(divisions_u=3, divisions_v=2)
    pressure = SurfacePressureData(1, "p", 1, 1, -4.0)
    project.add_surface_pressure(pressure)
    sync_surface_pressure(project, 1)

    normal_before = surface_unit_normal(project.surfaces[1])
    vector_before = tuple(-4.0 * value for value in normal_before)

    flip_surface_orientation(project, 1)

    item = project.surface_pressures[1]
    normal_after = surface_unit_normal(project.surfaces[1])
    vector_after = tuple(item.pressure * value for value in normal_after)

    assert item.pressure == pytest.approx(4.0)
    assert vector_after == pytest.approx(vector_before)
    assert len(item.generated_element_load_tags) == 6
    assert all(
        project.element_loads[tag].pressure == pytest.approx(4.0)
        for tag in item.generated_element_load_tags
    )


def test_remove_managed_pressure_deletes_only_generated_element_loads():
    project = _meshed_project()
    pressure = SurfacePressureData(1, "p", 1, 1, -2.0)
    project.add_surface_pressure(pressure)
    generated = set(sync_surface_pressure(project, 1))

    removed = set(remove_surface_pressure(project, 1))

    assert removed == generated
    assert generated.isdisjoint(project.element_loads)
    assert 1 not in project.surface_pressures


def test_load_pattern_rename_propagates_to_managed_surface_pressure():
    project = _meshed_project()
    pressure = SurfacePressureData(1, "p", 1, 1, -2.0)
    project.add_surface_pressure(pressure)
    sync_surface_pressure(project, 1)

    project.update_load_pattern(
        1,
        LoadPatternData(
            5,
            "Renamed pressure",
            "Plain",
            time_series_tag=1,
        ),
    )

    assert project.surface_pressures[1].pattern_tag == 5
    assert all(
        project.element_loads[tag].pattern_tag == 5
        for tag in project.surface_pressures[1].generated_element_load_tags
    )


def test_managed_pressure_ui_and_generated_element_guard_are_exposed():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    create = inspect.getsource(
        MainWindow._create_surface_pressure_for_surfaces
    )
    preview = inspect.getsource(
        MainWindow._preview_managed_surface_pressure
    )
    remove = inspect.getsource(
        MainWindow._remove_managed_surface_pressure
    )
    edit_element = inspect.getsource(MainWindow._edit_element_load)
    delete_element = inspect.getsource(MainWindow._delete_element_load)
    properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )
    dialog = inspect.getsource(SurfacePressureDialog)

    assert "Managed Surface Pressure..." in context
    assert "Preview Managed Surface Pressure..." in context
    assert "Remove Managed Surface Pressure..." in context
    assert "SurfacePressureDialog" in create
    assert "sync_surface_pressure" in create
    assert "replace_surface_pressure" in create
    assert "show_surface_pressure_preview" in preview
    assert "remove_surface_pressure" in remove
    assert "_managed_surface_pressure_for_element_load" in edit_element
    assert "owner is not None" in edit_element
    assert "_create_surface_pressure_for_surfaces" in edit_element
    assert "_managed_surface_pressure_for_element_load" in delete_element
    assert "owner is not None" in delete_element
    assert "_remove_managed_surface_pressure" in delete_element
    assert "Managed Surface pressures" in properties
    assert "Positive follows +Surface normal" in dialog
