from __future__ import annotations

import inspect

import pytest

from openseespy_studio.project import (
    AnalysisSettingsData,
    ProjectDatabase,
    SectionData,
    SolutionResultData,
    SurfaceGeometryData,
)
from openseespy_studio.surface_mesher import (
    delete_surface_geometry,
    managed_surface_result_tags,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    sync_solution_result_surface_scope,
)
from openseespy_studio.ui.main_window import MainWindow, PropertiesPanel
from openseespy_studio.ui.surface_result_dialog import SurfaceResultDialog


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
    project = ProjectDatabase(name="managed-surface-result")
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
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Static",
            "Static",
        )
    )
    return project


def test_managed_surface_result_round_trips_with_geometry_scope():
    project = _project()
    result = SolutionResultData(
        1,
        1,
        "Panel Nxx",
        "ShellForce",
        surface_scope=[1],
        settings={"component": "Nxx"},
    )
    project.add_solution_result(result)

    assert result.element_scope == sorted(
        project.surfaces[1].generated_element_tags
    )
    assert managed_surface_result_tags(project) == {1}

    restored = ProjectDatabase.from_dict(project.to_dict())
    item = restored.solution_results[1]
    assert item.surface_scope == [1]
    assert item.element_scope == sorted(
        restored.surfaces[1].generated_element_tags
    )
    assert item.settings["component"] == "Nxx"


def test_remesh_rebinds_managed_shell_result_scope():
    project = _project(divisions_u=1, divisions_v=1)
    result = SolutionResultData(
        1,
        1,
        "Panel Mxx",
        "ShellForce",
        surface_scope=[1],
        settings={"component": "Mxx"},
    )
    project.add_solution_result(result)
    assert len(result.element_scope) == 1

    project.surfaces[1].divisions_u = 3
    project.surfaces[1].divisions_v = 2
    remesh_surface_geometry(project, 1)

    item = project.solution_results[1]
    assert item.surface_scope == [1]
    assert len(item.element_scope) == 6
    assert item.element_scope == sorted(
        project.surfaces[1].generated_element_tags
    )
    assert sync_solution_result_surface_scope(project, 1) == item.element_scope


def test_direct_fe_shell_result_still_blocks_surface_remesh():
    project = _project()
    element_tag = project.surfaces[1].generated_element_tags[0]
    project.add_solution_result(
        SolutionResultData(
            1,
            1,
            "Direct FE Nxx",
            "ShellForce",
            element_scope=[element_tag],
            settings={"component": "Nxx"},
        )
    )

    with pytest.raises(ValueError, match="result request"):
        remesh_surface_geometry(project, 1)


def test_multi_surface_result_survives_deleting_one_surface():
    project = _project(divisions_u=1, divisions_v=1)
    project.add_surface(
        SurfaceGeometryData(
            2,
            "Panel 2",
            points=rectangle_surface_points((4, 0, 0), 4, 2),
            section_tag=7,
            divisions_u=2,
            divisions_v=1,
            conform_existing_edges=False,
        )
    )
    mesh_surface_geometry(project, 2)

    result = SolutionResultData(
        1,
        1,
        "Two-panel Exx",
        "ShellDeformation",
        surface_scope=[1, 2],
        settings={"component": "Exx"},
    )
    project.add_solution_result(result)
    expected = sorted(
        set(project.surfaces[1].generated_element_tags)
        | set(project.surfaces[2].generated_element_tags)
    )
    assert result.element_scope == expected

    delete_surface_geometry(project, 1)

    item = project.solution_results[1]
    assert item.surface_scope == [2]
    assert item.element_scope == sorted(
        project.surfaces[2].generated_element_tags
    )


def test_unmeshed_managed_result_definition_can_persist_and_rebind():
    project = _project(divisions_u=2, divisions_v=1)
    result = SolutionResultData(
        1,
        1,
        "Panel Qx",
        "ShellForce",
        surface_scope=[1],
        settings={"component": "Qx"},
    )
    project.add_solution_result(result)

    from openseespy_studio.surface_mesher import delete_surface_mesh

    delete_surface_mesh(project, 1)
    assert project.solution_results[1].surface_scope == [1]
    assert project.solution_results[1].element_scope == []

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.solution_results[1].surface_scope == [1]
    assert restored.solution_results[1].element_scope == []

    mesh_surface_geometry(restored, 1)
    assert restored.solution_results[1].element_scope == sorted(
        restored.surfaces[1].generated_element_tags
    )


def test_managed_surface_result_ui_locks_fe_scope_and_exposes_geometry_route():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    manage = inspect.getsource(MainWindow._manage_surface_shell_result)
    select_scope = inspect.getsource(
        MainWindow._select_managed_surface_result_scope
    )
    remove = inspect.getsource(
        MainWindow._remove_managed_surface_shell_result
    )
    payload = inspect.getsource(MainWindow._solution_result_from_payload)
    use_selection = inspect.getsource(
        MainWindow._use_current_selection_for_solution_result
    )
    surface_properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )
    result_panel = inspect.getsource(PropertiesPanel.set_solution_result)
    dialog = inspect.getsource(SurfaceResultDialog)

    assert "Managed Shell Result..." in context
    assert "Select Managed Result FE Scope..." in context
    assert "Remove Managed Shell Result..." in context
    assert "SurfaceResultDialog" in manage
    assert "add_solution_result" in manage
    assert 'set_display_domain("fe")' in select_scope
    assert "remove_solution_result" in remove
    assert "surface_scope=list(current.surface_scope)" in payload
    assert "This result scope is managed by Geometry Surface" in use_selection
    assert "Managed Shell results" in surface_properties
    assert "managed_surface_scope = bool(result.surface_scope)" in result_panel
    assert "result_use_selection.setEnabled(not managed_surface_scope)" in result_panel
    assert "ShellForce" in dialog and "ShellDeformation" in dialog
