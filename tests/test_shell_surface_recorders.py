from __future__ import annotations

import inspect

import pytest

from openseespy_studio.generator import to_openseespy
from openseespy_studio.project import (
    ProjectDatabase,
    RecorderData,
    SectionData,
    SurfaceGeometryData,
    SurfaceRecorderData,
)
from openseespy_studio.surface_mesher import (
    delete_surface_mesh,
    managed_surface_recorder_tags,
    mesh_surface_geometry,
    rectangle_surface_points,
    remesh_surface_geometry,
    remove_surface_recorder,
    sync_surface_recorder,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.surface_recorder_dialog import SurfaceRecorderDialog


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
    project = ProjectDatabase(name="managed-surface-recorder")
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


def test_managed_surface_recorder_round_trips_with_generated_provenance():
    project = _project()
    definition = SurfaceRecorderData(
        1,
        "Panel force",
        1,
        response="force",
        section_number=2,
        file_name="recorders/panel_force.out",
    )
    project.add_surface_recorder(definition)
    generated_tag = sync_surface_recorder(project, 1)

    restored = ProjectDatabase.from_dict(project.to_dict())
    item = restored.surface_recorders[1]
    recorder = restored.recorders[generated_tag]

    assert item.surface_tag == 1
    assert item.generated_recorder_tag == generated_tag
    assert recorder.recorder_type == "Shell"
    assert recorder.response == "force"
    assert recorder.section_number == 2
    assert recorder.file_name == "recorders/panel_force.out"
    assert recorder.target_tags == sorted(
        restored.surfaces[1].generated_element_tags
    )
    assert managed_surface_recorder_tags(restored) == {generated_tag}


def test_remesh_rebinds_recorder_targets_and_preserves_output_contract():
    project = _project(divisions_u=1, divisions_v=1)
    definition = SurfaceRecorderData(
        1,
        "Panel deformation",
        1,
        response="deformation",
        section_number=3,
        file_name="recorders/panel_deformation.out",
        include_time=False,
    )
    project.add_surface_recorder(definition)
    sync_surface_recorder(project, 1)

    project.surfaces[1].divisions_u = 3
    project.surfaces[1].divisions_v = 2
    remesh_surface_geometry(project, 1)

    item = project.surface_recorders[1]
    assert item.generated_recorder_tag is not None
    recorder = project.recorders[item.generated_recorder_tag]
    assert len(recorder.target_tags) == 6
    assert recorder.target_tags == sorted(
        project.surfaces[1].generated_element_tags
    )
    assert recorder.response == "deformation"
    assert recorder.section_number == 3
    assert recorder.file_name == "recorders/panel_deformation.out"
    assert recorder.include_time is False


def test_direct_fe_shell_recorder_still_blocks_surface_remesh():
    project = _project()
    element_tag = project.surfaces[1].generated_element_tags[0]
    project.add_recorder(
        RecorderData(
            99,
            "Direct FE recorder",
            "Shell",
            target_tags=[element_tag],
            response="force",
            section_number=1,
            file_name="recorders/direct.out",
        )
    )

    with pytest.raises(ValueError, match="recorder"):
        remesh_surface_geometry(project, 1)


def test_delete_mesh_detaches_managed_recorder_and_rebinds_on_mesh():
    project = _project(divisions_u=2, divisions_v=1)
    definition = SurfaceRecorderData(
        1,
        "Panel force",
        1,
        response="force",
        section_number=1,
    )
    project.add_surface_recorder(definition)
    old_generated = sync_surface_recorder(project, 1)

    delete_surface_mesh(project, 1)

    assert project.surface_recorders[1].generated_recorder_tag is None
    assert old_generated not in project.recorders

    mesh_surface_geometry(project, 1)

    item = project.surface_recorders[1]
    assert item.generated_recorder_tag is not None
    recorder = project.recorders[item.generated_recorder_tag]
    assert recorder.target_tags == sorted(
        project.surfaces[1].generated_element_tags
    )


def test_managed_surface_recorder_generates_native_shell_recorder_script():
    project = _project(divisions_u=2, divisions_v=1)
    definition = SurfaceRecorderData(
        1,
        "Panel deformation",
        1,
        response="deformation",
        section_number=3,
        file_name="recorders/panel_deformation.out",
        include_time=True,
    )
    project.add_surface_recorder(definition)
    generated_tag = sync_surface_recorder(project, 1)
    recorder = project.recorders[generated_tag]

    script = to_openseespy(
        project.model,
        sections=project.sections,
        recorders=project.recorders,
        units=project.units,
    )

    target_text = ", ".join(map(str, recorder.target_tags))
    assert "recorders/panel_deformation.out" in script
    assert f"'-ele', {target_text}, 'material', 3, 'deformation'" in script


def test_remove_managed_surface_recorder_removes_generated_recorder_only():
    project = _project()
    definition = SurfaceRecorderData(1, "Panel force", 1)
    project.add_surface_recorder(definition)
    generated_tag = sync_surface_recorder(project, 1)

    removed = remove_surface_recorder(project, 1)

    assert removed == generated_tag
    assert generated_tag not in project.recorders
    assert 1 not in project.surface_recorders


def test_managed_surface_recorder_ui_and_provenance_guard_are_exposed():
    context = inspect.getsource(MainWindow._show_tree_context_menu)
    manage = inspect.getsource(MainWindow._manage_surface_shell_recorder)
    select_targets = inspect.getsource(
        MainWindow._select_managed_surface_recorder_targets
    )
    remove = inspect.getsource(
        MainWindow._remove_managed_surface_shell_recorder
    )
    edit = inspect.getsource(MainWindow._edit_recorder)
    delete = inspect.getsource(MainWindow._delete_recorder)
    properties = inspect.getsource(
        MainWindow._show_surface_geometry_properties
    )
    recorder_properties = inspect.getsource(
        MainWindow._show_recorder_properties
    )
    dialog = inspect.getsource(SurfaceRecorderDialog)

    assert "Managed Shell Recorder..." in context
    assert "Select Managed Recorder FE Targets..." in context
    assert "Remove Managed Shell Recorder..." in context
    assert "SurfaceRecorderDialog" in manage
    assert "sync_surface_recorder" in manage
    assert "replace_surface_recorder" in manage
    assert 'set_display_domain("fe")' in select_targets
    assert "remove_surface_recorder" in remove
    assert "_managed_surface_recorder_for_recorder" in edit
    assert "owner is not None" in edit
    assert "_manage_surface_shell_recorder" in edit
    assert "_managed_surface_recorder_for_recorder" in delete
    assert "owner is not None" in delete
    assert "_remove_managed_surface_shell_recorder" in delete
    assert "Managed Surface recorders" in properties
    assert "Geometry-owned · remesh-safe" in recorder_properties
    assert "Gauss point" in dialog
