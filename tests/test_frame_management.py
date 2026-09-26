from __future__ import annotations

from openseespy_studio.frame_management import (
    frame_regeneration_plan,
    managed_frame_conflicts,
    managed_frame_snapshot,
)
from openseespy_studio.frame_presets import frame_spec_to_preset
from openseespy_studio.frame_setup import prepare_frame_grid
from openseespy_studio.generator import FrameGridSpec, generate_frame_project
from openseespy_studio.project import ProjectDatabase, SectionData


def _project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.add_section(
        SectionData(
            1,
            "Elastic",
            "Elastic",
            parameters={
                "E": 2.0e11,
                "A": 0.03,
                "Iz": 1.0e-4,
                "Iy": 1.0e-4,
                "G": 7.7e10,
                "J": 5.0e-5,
                "Avy": 0.03,
                "Avz": 0.03,
            },
        )
    )
    return project


def _managed_project() -> tuple[ProjectDatabase, FrameGridSpec, dict]:
    project = _project()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=2,
        planar_2d=False,
        column_section_tag=1,
        beam_section_tag=1,
    )
    prepare_frame_grid(project, spec)
    generate_frame_project(project, spec)
    recipe = frame_spec_to_preset(spec, name="Managed")
    recipe["managed_snapshot"] = managed_frame_snapshot(project)
    project.frame_wizard_recipe = recipe
    return project, spec, recipe


def test_managed_snapshot_detects_manual_node_edit_by_domain():
    project, _spec, recipe = _managed_project()
    assert managed_frame_conflicts(project, recipe) == []

    tag = min(project.model.nodes)
    project.model.set_fixity(tag, (0, 0, 0, 0, 0, 0))
    conflicts = managed_frame_conflicts(project, recipe)

    assert [item["domain"] for item in conflicts] == ["nodes"]


def test_regeneration_plan_preserves_all_tags_for_compatible_geometry_edit():
    project, spec, recipe = _managed_project()
    revised = FrameGridSpec(**vars(spec))
    revised.dx = 6.25

    plan = frame_regeneration_plan(project, recipe, revised)

    assert plan["compatible"] is True
    assert plan["all_tags_stable"] is True
    assert plan["conflicts"] == []
    assert plan["domains"]["nodes"]["stable"] is True
    assert plan["domains"]["elements"]["stable"] is True
    assert plan["domains"]["nodes"]["retained"] == len(project.model.nodes)
    assert plan["domains"]["elements"]["retained"] == len(
        project.model.elements
    )


def test_regeneration_plan_rejects_topology_change_for_compatible_update():
    project, spec, recipe = _managed_project()
    revised = FrameGridSpec(**vars(spec))
    revised.nx = 3

    plan = frame_regeneration_plan(project, recipe, revised)

    assert plan["compatible"] is False
    assert plan["all_tags_stable"] is False
    assert plan["domains"]["nodes"]["after"] > plan["domains"]["nodes"]["before"]
    assert plan["domains"]["elements"]["after"] > (
        plan["domains"]["elements"]["before"]
    )


def test_regeneration_plan_rejects_compatible_update_after_manual_edit():
    project, spec, recipe = _managed_project()
    tag = min(project.model.nodes)
    project.model.set_fixity(tag, (0, 0, 0, 0, 0, 0))

    plan = frame_regeneration_plan(project, recipe, spec)

    assert plan["compatible"] is False
    assert plan["all_tags_stable"] is True
    assert any(
        item["domain"] == "nodes"
        for item in plan["conflicts"]
    )
