from __future__ import annotations

from dataclasses import asdict

from openseespy_studio.frame_presets import (
    BUILTIN_FRAME_PRESETS,
    FRAME_PRESET_KIND,
    frame_preset_dependency_issues,
    frame_spec_from_preset,
    frame_spec_to_preset,
)
from openseespy_studio.generator import FrameGridSpec
from openseespy_studio.project import ProjectDatabase, SectionData


def _project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.add_section(
        SectionData(
            10,
            "Preset elastic frame",
            "Elastic",
            parameters={
                "E": 2.0e11,
                "A": 0.03,
                "Iz": 1.2e-4,
                "Iy": 9.0e-5,
                "G": 7.7e10,
                "J": 6.0e-5,
                "Avy": 0.025,
                "Avz": 0.025,
            },
        )
    )
    return project


def test_frame_preset_round_trip_preserves_complete_spec():
    spec = FrameGridSpec(
        nx=2,
        ny=3,
        nz=4,
        dx=4.5,
        dy=6.5,
        dz=3.2,
        x_bay_widths=(4.0, 5.0),
        y_bay_widths=(5.0, 6.0, 7.0),
        storey_heights=(3.0, 3.1, 3.2, 3.3),
        origin_x=1.0,
        origin_y=-2.0,
        origin_z=0.5,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=10,
        beam_section_tag=10,
        column_element_type="dispBeamColumn",
        beam_element_type="forceBeamColumn",
        column_integration_type="Lobatto",
        beam_integration_type="Radau",
        column_integration_points=7,
        beam_integration_points=6,
        column_mass_per_length=2.5,
        beam_mass_per_length=1.5,
        joint_model="None",
        diaphragm_mode="Rigid",
        diaphragm_levels=(1, 2, 4),
        foundation_mode="Direct",
        brace_mode="None",
        load_mode="Static",
        load_beam_udl=True,
        load_beam_udl_coordinate_system="global",
        load_beam_udl_vector=(1.0, 2.0, -12.0),
        load_beam_scope="Both",
        load_storeys=(2, 4),
        mass_source_mode="Source",
        mass_include_self=True,
        mass_include_static_loads=True,
        mass_static_load_factor=0.75,
        mass_gravity_axis=3,
        mass_directions=(1, 2),
        modal_mode="Modal",
        modal_num_modes=8,
        modal_eigen_solver="-fullGenLapack",
        planar_2d=False,
    )
    preset = frame_spec_to_preset(
        spec,
        name="Round Trip",
        description="Regression preset",
    )
    restored = frame_spec_from_preset(preset)

    assert preset["kind"] == FRAME_PRESET_KIND
    assert preset["name"] == "Round Trip"
    assert asdict(restored) == asdict(spec)


def test_builtin_frame_presets_are_versioned_and_loadable():
    assert {
        "2D Moment Frame",
        "3D Moment Frame",
        "3D Braced Frame",
        "Rigid Diaphragm Frame",
    } <= set(BUILTIN_FRAME_PRESETS)

    for name, data in BUILTIN_FRAME_PRESETS.items():
        assert data["builtin"] is True
        assert data["name"] == name
        spec = frame_spec_from_preset(data)
        assert isinstance(spec, FrameGridSpec)


def test_frame_preset_dependency_check_reports_missing_project_references():
    project = _project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        column_section_tag=999,
        beam_section_tag=None,
        brace_mode="Truss",
        brace_material_tag=88,
    )
    issues = frame_preset_dependency_issues(project, spec)
    text = "\n".join(issues)

    assert "Column section 999" in text
    assert "Beam section is not assigned" in text
    assert "Brace material 88" in text


def test_frame_preset_dependency_check_accepts_resolved_frame_sections():
    project = _project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        column_section_tag=10,
        beam_section_tag=10,
    )
    assert frame_preset_dependency_issues(project, spec) == []
