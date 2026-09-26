from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from .generator import FrameGridSpec
from .project import ProjectDatabase


FRAME_PRESET_SCHEMA_VERSION = 1
FRAME_PRESET_KIND = "fewiz.frame-wizard"


_TUPLE_FIELDS = {
    "x_bay_widths",
    "y_bay_widths",
    "storey_heights",
    "joint_interface_material_tags",
    "joint_component_material_tags",
    "diaphragm_levels",
    "foundation_material_tags",
    "foundation_profile_material_tags",
    "foundation_base_profile_indices",
    "brace_x_bays",
    "brace_y_bays",
    "brace_storeys",
    "brace_panel_patterns",
    "load_beam_udl_vector",
    "load_storeys",
    "mass_directions",
}


def _tuple_tree(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple_tree(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_tuple_tree(item) for item in value)
    return value


def frame_spec_to_preset(
    spec: FrameGridSpec,
    *,
    name: str,
    description: str = "",
    builtin: bool = False,
) -> dict[str, Any]:
    preset_name = str(name).strip()
    if not preset_name:
        raise ValueError("Frame Wizard preset name cannot be empty.")
    return {
        "kind": FRAME_PRESET_KIND,
        "schema_version": FRAME_PRESET_SCHEMA_VERSION,
        "name": preset_name,
        "description": str(description).strip(),
        "builtin": bool(builtin),
        "spec": asdict(spec),
    }


def frame_spec_from_preset(data: dict[str, Any]) -> FrameGridSpec:
    if not isinstance(data, dict):
        raise ValueError("Frame Wizard preset must be an object.")
    if str(data.get("kind", FRAME_PRESET_KIND)) != FRAME_PRESET_KIND:
        raise ValueError("This preset is not a Frame Wizard preset.")
    version = int(data.get("schema_version", FRAME_PRESET_SCHEMA_VERSION))
    if version != FRAME_PRESET_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported Frame Wizard preset schema version "
            f"{version}; expected {FRAME_PRESET_SCHEMA_VERSION}."
        )
    raw = data.get("spec")
    if not isinstance(raw, dict):
        raise ValueError("Frame Wizard preset does not contain a spec object.")

    known = {item.name for item in fields(FrameGridSpec)}
    values = {
        str(key): value
        for key, value in raw.items()
        if str(key) in known
    }
    for key in _TUPLE_FIELDS:
        if key in values:
            values[key] = _tuple_tree(values[key])
    return FrameGridSpec(**values)


def frame_preset_dependency_issues(
    project: ProjectDatabase,
    spec: FrameGridSpec,
) -> list[str]:
    issues: list[str] = []

    def need_section(tag: int | None, label: str) -> None:
        if tag is None:
            issues.append(f"{label} section is not assigned.")
        elif int(tag) not in project.sections:
            issues.append(
                f"{label} section {int(tag)} does not exist in this project."
            )

    def optional_section(tag: int | None, label: str) -> None:
        if tag is not None and int(tag) not in project.sections:
            issues.append(
                f"{label} section {int(tag)} does not exist in this project."
            )

    def optional_transformation(tag: int | None, label: str) -> None:
        if tag is not None and int(tag) not in project.transformations:
            issues.append(
                f"{label} transformation {int(tag)} does not exist in this project."
            )

    def need_material(tag: int | None, label: str) -> None:
        if tag is None or int(tag) <= 0:
            issues.append(f"{label} material is not assigned.")
        elif int(tag) not in project.materials:
            issues.append(
                f"{label} material {int(tag)} does not exist in this project."
            )

    def optional_material(tag: int, label: str) -> None:
        value = int(tag)
        if value > 0 and value not in project.materials:
            issues.append(
                f"{label} material {value} does not exist in this project."
            )

    if spec.create_columns:
        need_section(spec.column_section_tag, "Column")
    if spec.create_beams_x or (not spec.planar_2d and spec.create_beams_y):
        need_section(spec.beam_section_tag, "Beam")
    optional_transformation(spec.column_transf_tag, "Column")
    optional_transformation(spec.beam_transf_tag, "Beam")

    for tag, label in (
        (spec.column_hinge_i_section_tag, "Column I-end hinge"),
        (spec.column_hinge_j_section_tag, "Column J-end hinge"),
        (spec.column_interior_section_tag, "Column interior"),
        (spec.beam_hinge_i_section_tag, "Beam I-end hinge"),
        (spec.beam_hinge_j_section_tag, "Beam J-end hinge"),
        (spec.beam_interior_section_tag, "Beam interior"),
    ):
        optional_section(tag, label)

    if spec.joint_model in {"ZeroLength", "Joint2D", "KrawinklerPanelZone"}:
        need_material(spec.joint_material_tag, f"{spec.joint_model} joint")
    if spec.joint_model == "Joint2D":
        for index, tag in enumerate(spec.joint_interface_material_tags, start=1):
            optional_material(tag, f"Joint2D interface {index}")
    if spec.joint_model == "BeamColumnJoint":
        for index, tag in enumerate(spec.joint_component_material_tags, start=1):
            need_material(tag, f"BeamColumnJoint component {index}")

    if spec.diaphragm_mode == "Shell":
        if spec.slab_section_tag is None:
            issues.append("Shell slab section is not assigned.")
        elif int(spec.slab_section_tag) not in project.sections:
            issues.append(
                f"Shell slab section {int(spec.slab_section_tag)} does not exist "
                "in this project."
            )

    if spec.foundation_mode == "Springs":
        profiles = (
            spec.foundation_profile_material_tags
            if spec.foundation_profile_material_tags
            else (spec.foundation_material_tags,)
        )
        active_dofs = (1, 3, 5) if spec.planar_2d else (1, 2, 3, 4, 5, 6)
        for profile_index, profile in enumerate(profiles, start=1):
            for dof in active_dofs:
                tag = int(profile[dof - 1]) if len(profile) >= dof else 0
                optional_material(
                    tag,
                    f"Foundation profile {profile_index} DOF {dof}",
                )

    if spec.brace_mode == "Truss":
        need_material(spec.brace_material_tag, "Brace")

    return list(dict.fromkeys(issues))


BUILTIN_FRAME_PRESETS: dict[str, dict[str, Any]] = {
    "2D Moment Frame": frame_spec_to_preset(
        FrameGridSpec(
            nx=3,
            ny=1,
            nz=3,
            dx=5.0,
            dy=5.0,
            dz=3.5,
            create_columns=True,
            create_beams_x=True,
            create_beams_y=False,
            planar_2d=True,
            planar_base_support="Fixed",
        ),
        name="2D Moment Frame",
        description="Regular 3-bay × 3-storey planar moment frame.",
        builtin=True,
    ),
    "3D Moment Frame": frame_spec_to_preset(
        FrameGridSpec(
            nx=3,
            ny=2,
            nz=3,
            dx=5.0,
            dy=5.0,
            dz=3.5,
            create_columns=True,
            create_beams_x=True,
            create_beams_y=True,
            planar_2d=False,
        ),
        name="3D Moment Frame",
        description="Regular 3 × 2 bay, 3-storey space moment frame.",
        builtin=True,
    ),
    "3D Braced Frame": frame_spec_to_preset(
        FrameGridSpec(
            nx=3,
            ny=2,
            nz=3,
            dx=5.0,
            dy=5.0,
            dz=3.5,
            create_columns=True,
            create_beams_x=True,
            create_beams_y=True,
            planar_2d=False,
            brace_mode="Truss",
            brace_pattern="X",
            brace_plane_mode="X",
            brace_y_plane_scope="Exterior",
            brace_x_bays=(0, 2),
            brace_storeys=(1, 2, 3),
        ),
        name="3D Braced Frame",
        description=(
            "Space frame with X-bracing on exterior X-Z planes. "
            "Assign a brace material after loading."
        ),
        builtin=True,
    ),
    "Rigid Diaphragm Frame": frame_spec_to_preset(
        FrameGridSpec(
            nx=3,
            ny=2,
            nz=3,
            dx=5.0,
            dy=5.0,
            dz=3.5,
            create_columns=True,
            create_beams_x=True,
            create_beams_y=True,
            planar_2d=False,
            diaphragm_mode="Rigid",
            diaphragm_levels=(1, 2, 3),
        ),
        name="Rigid Diaphragm Frame",
        description="3D frame with rigid diaphragms on every elevated floor.",
        builtin=True,
    ),
}
