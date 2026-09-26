from __future__ import annotations

from dataclasses import dataclass
import math

from .beam_loads import (
    resolve_element_load_local_components,
    resolve_element_load_local_end_components,
    resolve_self_weight_local,
)
from .mass_source import apply_mass_source
from .units import UnitSystem
from .model import (
    BEAM_CONTACT_ELEMENT_TYPES,
    BEARING_ELEMENT_TYPES,
    CABLE_ELEMENT_TYPES,
    CONTACT_TWO_NODE_ELEMENT_TYPES,
    CONTINUUM_QUAD_ELEMENT_TYPES,
    EMBEDDED_ELEMENT_TYPES,
    FRICTION_BEARING_ELEMENT_TYPES,
    MASONRY_PANEL_ELEMENT_TYPES,
    SHELL_ELEMENT_TYPES,
    SOLID_ELEMENT_TYPES,
    TRUSS_ELEMENT_TYPES,
    TRUSS_MATERIAL_ELEMENT_TYPES,
    TRUSS_SECTION_ELEMENT_TYPES,
    WALL_MACRO_ELEMENT_TYPES,
    StructuralModel,
)
from .project import ELEMENT_BACKED_CONNECTION_TYPES, MATERIAL_PARAMETER_ORDER, AnalysisSettingsData, ConnectionData, ConstraintData, ElementLoadData, FiberComponentData, LoadPatternData, MassSourceData, MaterialData, FrictionModelData, NDMaterialData, NodalLoadData, PrescribedDisplacementData, RecorderData, SHELL_SECTION_TYPES, MEMBRANE_SECTION_TYPES, SectionData, TimeSeriesData, TransformationData, material_parameter_kind, nd_material_parameter_kind, resolve_transformation_vecxz
from .section_response import automatic_moment_curvature_spec, build_section_response_specs
from .response_spectrum import build_period_grid


@dataclass(slots=True)
class FrameGridSpec:
    nx: int = 4
    ny: int = 3
    nz: int = 3
    dx: float = 5.0
    dy: float = 6.0
    dz: float = 3.5
    x_bay_widths: tuple[float, ...] = ()
    y_bay_widths: tuple[float, ...] = ()
    storey_heights: tuple[float, ...] = ()
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_z: float = 0.0
    start_node_tag: int = 1
    start_element_tag: int = 1
    create_columns: bool = True
    create_beams_x: bool = True
    create_beams_y: bool = True
    column_section_tag: int | None = None
    beam_section_tag: int | None = None
    column_transf_tag: int | None = None
    beam_transf_tag: int | None = None
    column_element_type: str = "elasticBeamColumn"
    beam_element_type: str = "elasticBeamColumn"
    column_integration_type: str = "Lobatto"
    beam_integration_type: str = "Lobatto"
    column_integration_points: int = 5
    beam_integration_points: int = 5
    column_hinge_i_section_tag: int | None = None
    column_hinge_j_section_tag: int | None = None
    column_interior_section_tag: int | None = None
    beam_hinge_i_section_tag: int | None = None
    beam_hinge_j_section_tag: int | None = None
    beam_interior_section_tag: int | None = None
    column_hinge_i_length: float = 0.0
    column_hinge_j_length: float = 0.0
    beam_hinge_i_length: float = 0.0
    beam_hinge_j_length: float = 0.0
    column_mass_per_length: float = 0.0
    beam_mass_per_length: float = 0.0
    column_consistent_mass: bool = False
    beam_consistent_mass: bool = False
    joint_model: str = "None"
    joint_material_tag: int | None = None
    joint_scope: str = "all"
    joint_panel_width: float = 0.40
    joint_panel_height: float = 0.50
    joint_interface_material_tags: tuple[int, ...] = (0, 0, 0, 0)
    joint_large_disp: int = 0
    joint_component_material_tags: tuple[int, ...] = ()
    joint_height_factor: float = 1.0
    joint_width_factor: float = 1.0
    joint_rigid_a: float = 0.0
    joint_rigid_e: float = 0.0
    joint_rigid_i: float = 0.0
    diaphragm_mode: str = "None"
    diaphragm_levels: tuple[int, ...] = ()
    diaphragm_floor_mass: float = 0.0
    diaphragm_rotational_inertia: float = 0.0
    slab_section_tag: int | None = None
    slab_element_type: str = "ASDShellQ4"
    slab_divisions_x: int = 1
    slab_divisions_y: int = 1
    slab_corotational: bool = False
    slab_mass_per_area: float = 0.0
    foundation_mode: str = "Direct"
    foundation_material_tags: tuple[int, ...] = (0, 0, 0, 0, 0, 0)
    foundation_assignment_mode: str = "Uniform"
    foundation_profile_material_tags: tuple[
        tuple[int, ...], ...
    ] = ()
    foundation_base_profile_indices: tuple[int, ...] = ()
    brace_mode: str = "None"
    brace_pattern: str = "X"
    brace_element_type: str = "truss"
    brace_material_tag: int | None = None
    brace_area: float = 0.01
    brace_mass_per_length: float = 0.0
    brace_do_rayleigh: bool = False
    brace_x_bays: tuple[int, ...] = ()
    brace_y_bays: tuple[int, ...] = ()
    brace_storeys: tuple[int, ...] = ()
    brace_plane_mode: str = "X"
    brace_y_plane_scope: str = "All"
    brace_x_plane_scope: str = "All"
    brace_panel_patterns: tuple[
        tuple[str, int, int, int, str], ...
    ] = ()
    brace_response_preset: str = "Standard"
    load_mode: str = "None"
    load_self_weight: bool = False
    load_self_weight_density: float = 0.0
    load_beam_udl: bool = False
    load_beam_udl_coordinate_system: str = "global"
    load_beam_udl_vector: tuple[float, float, float] = (0.0, 0.0, -10.0)
    load_beam_scope: str = "Both"
    load_storeys: tuple[int, ...] = ()
    load_floor_area: bool = False
    load_floor_area_pressure: float = 0.0
    load_floor_area_direction: str = "X"
    mass_source_mode: str = "None"
    mass_include_self: bool = True
    mass_include_static_loads: bool = True
    mass_static_load_factor: float = 1.0
    mass_gravity_axis: int = 3
    mass_directions: tuple[int, ...] = (1, 2)
    planar_2d: bool = False
    planar_base_support: str = "Fixed"


def _frame_axis_coordinates(
    count: int,
    uniform_spacing: float,
    individual_spacings: tuple[float, ...],
    origin: float,
    axis_name: str,
) -> list[float]:
    count = int(count)
    if count < 1:
        raise ValueError(f"{axis_name} needs at least one interval.")
    if not math.isfinite(float(origin)):
        raise ValueError(f"{axis_name} origin must be finite.")

    values = tuple(float(value) for value in individual_spacings)
    if values and len(values) != count:
        raise ValueError(
            f"{axis_name} spacing count is {len(values)} but expected {count}."
        )
    if not values:
        values = (float(uniform_spacing),) * count
    for index, value in enumerate(values, start=1):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                f"{axis_name} spacing {index} must be finite and positive."
            )

    coordinates = [float(origin)]
    for value in values:
        coordinates.append(coordinates[-1] + value)
    return coordinates


def frame_grid_coordinates(
    spec: FrameGridSpec,
) -> tuple[list[float], list[float], list[float]]:
    """Resolve regular or individually-sized grid coordinates."""
    x = _frame_axis_coordinates(
        spec.nx,
        spec.dx,
        spec.x_bay_widths,
        spec.origin_x,
        "X bay",
    )
    if spec.planar_2d:
        y = [float(spec.origin_y)]
    else:
        y = _frame_axis_coordinates(
            spec.ny,
            spec.dy,
            spec.y_bay_widths,
            spec.origin_y,
            "Y bay",
        )
    z = _frame_axis_coordinates(
        spec.nz,
        spec.dz,
        spec.storey_heights,
        spec.origin_z,
        "Storey",
    )
    return x, y, z


def validate_frame_grid_spec(spec: FrameGridSpec) -> None:
    """Validate frame-grid topology and resolve coordinate arrays."""
    if int(spec.start_node_tag) < 1 or int(spec.start_element_tag) < 1:
        raise ValueError("Frame node and element start tags must be positive.")
    if spec.planar_2d and spec.planar_base_support not in {"Fixed", "Pinned"}:
        raise ValueError("2D frame base support must be Fixed or Pinned.")
    if not (
        bool(spec.create_columns)
        or bool(spec.create_beams_x)
        or (not spec.planar_2d and bool(spec.create_beams_y))
    ):
        raise ValueError("Frame grid must create at least one member family.")

    supported_frame_types = {
        "elasticBeamColumn",
        "forceBeamColumn",
        "dispBeamColumn",
    }
    distributed_integrations = {"Lobatto", "Legendre", "Radau"}
    hinge_integrations = {
        "HingeRadau",
        "HingeRadauTwo",
        "HingeMidpoint",
        "HingeEndpoint",
        "ConcentratedPlasticity",
    }
    for (
        role,
        enabled,
        element_type,
        integration_type,
        points,
        hinge_i_section,
        hinge_j_section,
        interior_section,
        hinge_i_length,
        hinge_j_length,
        mass_per_length,
    ) in (
        (
            "Column",
            bool(spec.create_columns),
            str(spec.column_element_type),
            str(spec.column_integration_type),
            int(spec.column_integration_points),
            spec.column_hinge_i_section_tag,
            spec.column_hinge_j_section_tag,
            spec.column_interior_section_tag,
            float(spec.column_hinge_i_length),
            float(spec.column_hinge_j_length),
            float(spec.column_mass_per_length),
        ),
        (
            "Beam",
            bool(spec.create_beams_x)
            or (not spec.planar_2d and bool(spec.create_beams_y)),
            str(spec.beam_element_type),
            str(spec.beam_integration_type),
            int(spec.beam_integration_points),
            spec.beam_hinge_i_section_tag,
            spec.beam_hinge_j_section_tag,
            spec.beam_interior_section_tag,
            float(spec.beam_hinge_i_length),
            float(spec.beam_hinge_j_length),
            float(spec.beam_mass_per_length),
        ),
    ):
        if not enabled:
            continue
        if element_type not in supported_frame_types:
            raise ValueError(
                f"{role} formulation {element_type!r} is not supported by "
                "Frame Wizard."
            )
        if not math.isfinite(mass_per_length) or mass_per_length < 0.0:
            raise ValueError(
                f"{role} mass per length must be finite and non-negative."
            )
        if element_type in {"forceBeamColumn", "dispBeamColumn"}:
            if integration_type in distributed_integrations:
                if points < 2 or points > 20:
                    raise ValueError(
                        f"{role} integration points must be between 2 and 20."
                    )
            elif integration_type in hinge_integrations:
                if (
                    hinge_i_section is None
                    or hinge_j_section is None
                    or interior_section is None
                ):
                    raise ValueError(
                        f"{role} {integration_type} requires I-end, J-end, "
                        "and interior section assignments."
                    )
                if (
                    not math.isfinite(hinge_i_length)
                    or not math.isfinite(hinge_j_length)
                    or hinge_i_length < 0.0
                    or hinge_j_length < 0.0
                ):
                    raise ValueError(
                        f"{role} plastic hinge lengths must be finite and "
                        "non-negative."
                    )
                if (
                    integration_type != "ConcentratedPlasticity"
                    and (hinge_i_length <= 0.0 or hinge_j_length <= 0.0)
                ):
                    raise ValueError(
                        f"{role} {integration_type} requires positive I/J "
                        "plastic hinge lengths."
                    )
            else:
                raise ValueError(
                    f"{role} beam integration {integration_type!r} is not "
                    "supported by Frame Wizard."
                )
    joint_model = str(spec.joint_model or "None")
    supported_joint_models = {
        "None",
        "ZeroLength",
        "Joint2D",
        "BeamColumnJoint",
        "KrawinklerPanelZone",
    }
    if joint_model not in supported_joint_models:
        raise ValueError(
            f"Frame Wizard joint model {joint_model!r} is not supported."
        )
    if str(spec.joint_scope) not in {"all", "interior"}:
        raise ValueError("Frame joint scope must be 'all' or 'interior'.")

    if joint_model != "None":
        if not bool(spec.create_columns):
            raise ValueError(
                "Beam-column joints require columns to be created."
            )
        if not (
            bool(spec.create_beams_x)
            or (not spec.planar_2d and bool(spec.create_beams_y))
        ):
            raise ValueError(
                "Beam-column joints require at least one beam family."
            )

    if joint_model == "ZeroLength":
        if spec.joint_material_tag is None or int(spec.joint_material_tag) <= 0:
            raise ValueError(
                "Semi-rigid beam-column joints require a rotational "
                "uniaxial material."
            )

    macro_joint_models = {
        "Joint2D",
        "BeamColumnJoint",
        "KrawinklerPanelZone",
    }
    if joint_model in macro_joint_models:
        if not spec.planar_2d:
            raise ValueError(
                f"{joint_model} is a planar joint-core model in Frame Wizard; "
                "switch the frame dimension to 2D."
            )
        if not bool(spec.create_beams_x):
            raise ValueError(
                f"{joint_model} requires X-direction beams in the 2D frame."
            )
        width = float(spec.joint_panel_width)
        height = float(spec.joint_panel_height)
        if (
            not math.isfinite(width)
            or not math.isfinite(height)
            or width <= 0.0
            or height <= 0.0
        ):
            raise ValueError(
                "Joint panel width and height must be finite and positive."
            )
        x_coordinates, _, z_coordinates = frame_grid_coordinates(spec)
        min_bay = min(
            x_coordinates[index + 1] - x_coordinates[index]
            for index in range(len(x_coordinates) - 1)
        )
        min_storey = min(
            z_coordinates[index + 1] - z_coordinates[index]
            for index in range(len(z_coordinates) - 1)
        )
        if width >= min_bay:
            raise ValueError(
                "Joint panel width must be smaller than every X bay width."
            )
        if height >= min_storey:
            raise ValueError(
                "Joint panel height must be smaller than every storey height."
            )
        if (
            str(spec.joint_scope) == "interior"
            and int(spec.nx) < 2
        ):
            raise ValueError(
                "Interior joint scope requires at least two X bays."
            )

    if joint_model == "Joint2D":
        if spec.joint_material_tag is None or int(spec.joint_material_tag) <= 0:
            raise ValueError("Joint2D requires a panel rotational material.")
        interface = tuple(int(tag) for tag in spec.joint_interface_material_tags)
        if len(interface) != 4 or any(tag < 0 for tag in interface):
            raise ValueError(
                "Joint2D requires four interface material tags (zero = rigid)."
            )
        if int(spec.joint_large_disp) not in {0, 1, 2}:
            raise ValueError("Joint2D large-displacement flag must be 0, 1, or 2.")

    if joint_model == "BeamColumnJoint":
        components = tuple(
            int(tag) for tag in spec.joint_component_material_tags
        )
        if len(components) != 13 or any(tag <= 0 for tag in components):
            raise ValueError(
                "BeamColumnJoint requires 13 positive component material tags."
            )
        if (
            not math.isfinite(float(spec.joint_height_factor))
            or not math.isfinite(float(spec.joint_width_factor))
            or float(spec.joint_height_factor) <= 0.0
            or float(spec.joint_width_factor) <= 0.0
        ):
            raise ValueError(
                "BeamColumnJoint height/width factors must be positive."
            )

    if joint_model == "KrawinklerPanelZone":
        if spec.joint_material_tag is None or int(spec.joint_material_tag) <= 0:
            raise ValueError(
                "Krawinkler panel-zone requires a panel rotational material."
            )
        for label, value in (
            ("rigid A", spec.joint_rigid_a),
            ("rigid E", spec.joint_rigid_e),
            ("rigid I", spec.joint_rigid_i),
        ):
            numeric = float(value)
            if not math.isfinite(numeric) or numeric <= 0.0:
                raise ValueError(
                    f"Krawinkler panel-zone requires positive {label}."
                )

    diaphragm_mode = str(spec.diaphragm_mode or "None")
    if diaphragm_mode not in {"None", "Rigid", "Shell"}:
        raise ValueError(
            f"Frame Wizard floor mode {diaphragm_mode!r} is not supported."
        )
    if diaphragm_mode in {"Rigid", "Shell"}:
        if spec.planar_2d:
            raise ValueError(
                "Floor diaphragm/slab models require a 3D frame."
            )
        normalized_levels = tuple(
            sorted({int(level) for level in spec.diaphragm_levels})
        )
        if normalized_levels and any(
            level < 1 or level > int(spec.nz)
            for level in normalized_levels
        ):
            raise ValueError(
                "Floor levels must be between 1 and the number of storeys."
            )

    if diaphragm_mode == "Rigid":
        floor_mass = float(spec.diaphragm_floor_mass)
        rotational_inertia = float(spec.diaphragm_rotational_inertia)
        if not math.isfinite(floor_mass) or floor_mass < 0.0:
            raise ValueError(
                "Diaphragm floor mass must be finite and non-negative."
            )
        if (
            not math.isfinite(rotational_inertia)
            or rotational_inertia < 0.0
        ):
            raise ValueError(
                "Diaphragm rotational inertia must be finite and "
                "non-negative."
            )

    if diaphragm_mode == "Shell":
        if str(spec.joint_model or "None") != "None":
            raise ValueError(
                "Explicit shell slabs currently require rigid centerline "
                "beam-column joints so the slab cannot bypass joint springs."
            )
        if not bool(spec.create_beams_x) or not bool(spec.create_beams_y):
            raise ValueError(
                "Explicit shell slabs require both X and Y beam families."
            )
        if spec.slab_section_tag is None or int(spec.slab_section_tag) <= 0:
            raise ValueError(
                "Explicit shell slabs require a shell-compatible section."
            )
        if str(spec.slab_element_type) not in SHELL_ELEMENT_TYPES:
            raise ValueError(
                f"Unsupported slab shell formulation {spec.slab_element_type!r}."
            )
        nx_mesh = int(spec.slab_divisions_x)
        ny_mesh = int(spec.slab_divisions_y)
        if not 1 <= nx_mesh <= 50 or not 1 <= ny_mesh <= 50:
            raise ValueError(
                "Slab mesh divisions per bay must be between 1 and 50."
            )
        selected_floor_count = (
            len(normalized_levels)
            if normalized_levels
            else int(spec.nz)
        )
        shell_count = (
            int(spec.nx)
            * int(spec.ny)
            * nx_mesh
            * ny_mesh
            * selected_floor_count
        )
        if shell_count > 50000:
            raise ValueError(
                "Frame Wizard explicit slab mesh would create "
                f"{shell_count} Shell elements. Reduce X/Y mesh divisions, "
                "bay count, or selected floors; the Wizard limit is 50,000."
            )
        if (
            (nx_mesh > 1 or ny_mesh > 1)
            and str(spec.beam_element_type) != "elasticBeamColumn"
        ):
            raise ValueError(
                "Refined conforming slab meshes currently require "
                "elasticBeamColumn beams. Use 1×1 mesh per bay for nonlinear "
                "beam formulations."
            )
        mass_per_area = float(spec.slab_mass_per_area)
        if not math.isfinite(mass_per_area) or mass_per_area < 0.0:
            raise ValueError(
                "Additional slab mass per area must be finite and non-negative."
            )

    foundation_mode = str(spec.foundation_mode or "Direct")
    if foundation_mode not in {"Direct", "Springs"}:
        raise ValueError(
            f"Frame Wizard foundation mode {foundation_mode!r} is not supported."
        )

    assignment_mode = str(spec.foundation_assignment_mode or "Uniform")
    if assignment_mode not in {"Uniform", "PerBase"}:
        raise ValueError(
            "Foundation assignment mode must be Uniform or PerBase."
        )

    foundation_tags = tuple(
        int(tag) for tag in spec.foundation_material_tags
    )
    if len(foundation_tags) != 6 or any(tag < 0 for tag in foundation_tags):
        raise ValueError(
            "Foundation definition requires six material slots; "
            "zero means rigid transfer."
        )

    profile_tags = tuple(
        tuple(int(tag) for tag in profile)
        for profile in spec.foundation_profile_material_tags
    )
    if profile_tags:
        if len(profile_tags) > 3:
            raise ValueError(
                "Frame Wizard supports up to three equivalent foundation "
                "profiles in this workflow."
            )
        if any(
            len(profile) != 6 or any(tag < 0 for tag in profile)
            for profile in profile_tags
        ):
            raise ValueError(
                "Every foundation profile requires six material slots; "
                "zero means rigid transfer."
            )
    else:
        profile_tags = (foundation_tags,)

    if foundation_mode == "Springs":
        if joint_model in macro_joint_models:
            raise ValueError(
                "Foundation springs currently require the standard 3D/6DOF "
                "Frame Wizard backend; use rigid/pinned support with native "
                "2D macro joints."
            )
        if not bool(spec.create_columns):
            raise ValueError(
                "Foundation springs require columns and base-column nodes."
            )

        base_count = (
            int(spec.nx) + 1
            if spec.planar_2d
            else (int(spec.nx) + 1) * (int(spec.ny) + 1)
        )
        if assignment_mode == "PerBase":
            assignments = tuple(
                int(value) for value in spec.foundation_base_profile_indices
            )
            if len(assignments) != base_count:
                raise ValueError(
                    "Per-base foundation assignment count must match the "
                    f"{base_count} column bases."
                )
            if any(
                index < 0 or index >= len(profile_tags)
                for index in assignments
            ):
                raise ValueError(
                    "Foundation base assignment references an unavailable "
                    "profile."
                )
            used_profile_indices = sorted(set(assignments))
        else:
            used_profile_indices = [0]

        active_dofs = (
            (1, 3, 5)
            if spec.planar_2d
            else (1, 2, 3, 4, 5, 6)
        )
        for profile_index in used_profile_indices:
            profile = profile_tags[profile_index]
            if not any(profile[dof - 1] > 0 for dof in active_dofs):
                label = chr(ord("A") + profile_index)
                raise ValueError(
                    f"Foundation profile {label} requires at least one active "
                    "uniaxial spring material."
                )

    brace_mode = str(spec.brace_mode or "None")
    if brace_mode not in {"None", "Truss"}:
        raise ValueError(
            f"Frame Wizard brace mode {brace_mode!r} is not supported."
        )
    brace_pattern = str(spec.brace_pattern or "X")
    supported_brace_patterns = {
        "DiagonalForward",
        "DiagonalBackward",
        "X",
        "VUpper",
        "VLower",
        "KLeft",
        "KRight",
    }
    if brace_pattern not in supported_brace_patterns:
        raise ValueError(
            f"Frame Wizard brace pattern {brace_pattern!r} is not supported."
        )
    if str(spec.brace_element_type) not in {"truss", "corotTruss"}:
        raise ValueError(
            "Frame Wizard braces currently support truss or corotTruss."
        )

    plane_mode = str(spec.brace_plane_mode or "X")
    if plane_mode not in {"X", "Y", "Both"}:
        raise ValueError(
            "Brace plane mode must be X, Y, or Both."
        )
    if spec.planar_2d and plane_mode != "X":
        raise ValueError(
            "Planar Frame Wizard models support X-Z bracing only."
        )

    response_preset = str(spec.brace_response_preset or "Standard")
    if response_preset not in {"Standard", "NonlinearReady", "BRBReady"}:
        raise ValueError(
            "Brace response preset must be Standard, NonlinearReady, or "
            "BRBReady."
        )

    brace_x_bays = tuple(sorted({int(value) for value in spec.brace_x_bays}))
    if (
        plane_mode in {"X", "Both"}
        and brace_x_bays
        and any(
            value < 0 or value >= int(spec.nx)
            for value in brace_x_bays
        )
    ):
        raise ValueError(
            "Brace X-bay selections must be zero-based indices inside the "
            "frame grid."
        )
    brace_y_bays = tuple(sorted({int(value) for value in spec.brace_y_bays}))
    if (
        not spec.planar_2d
        and plane_mode in {"Y", "Both"}
        and brace_y_bays
        and any(
            value < 0 or value >= int(spec.ny)
            for value in brace_y_bays
        )
    ):
        raise ValueError(
            "Brace Y-bay selections must be zero-based indices inside the "
            "frame grid."
        )
    brace_storeys = tuple(
        sorted({int(value) for value in spec.brace_storeys})
    )
    if brace_storeys and any(
        value < 1 or value > int(spec.nz)
        for value in brace_storeys
    ):
        raise ValueError(
            "Brace storey selections must be between 1 and the number of "
            "storeys."
        )
    if str(spec.brace_y_plane_scope) not in {
        "All",
        "Exterior",
        "YMin",
        "YMax",
    }:
        raise ValueError(
            "Brace Y-plane scope must be All, Exterior, YMin, or YMax."
        )
    if str(spec.brace_x_plane_scope) not in {
        "All",
        "Exterior",
        "XMin",
        "XMax",
    }:
        raise ValueError(
            "Brace X-plane scope must be All, Exterior, XMin, or XMax."
        )

    panel_overrides = tuple(spec.brace_panel_patterns)
    seen_override_keys: set[tuple[str, int, int, int]] = set()
    for raw in panel_overrides:
        if len(raw) != 5:
            raise ValueError(
                "Brace panel override needs axis, plane, bay, storey, pattern."
            )
        axis = str(raw[0])
        plane = int(raw[1])
        bay = int(raw[2])
        storey = int(raw[3])
        pattern = str(raw[4])
        if axis not in {"X", "Y"}:
            raise ValueError("Brace panel override axis must be X or Y.")
        if pattern not in supported_brace_patterns | {"None"}:
            raise ValueError(
                f"Unsupported per-panel brace pattern {pattern!r}."
            )
        key = (axis, plane, bay, storey)
        if key in seen_override_keys:
            raise ValueError(
                "Brace panel overrides cannot contain duplicate panel keys."
            )
        seen_override_keys.add(key)
        if not 1 <= storey <= int(spec.nz):
            raise ValueError(
                "Brace panel override storey is outside the frame."
            )
        if axis == "X":
            if not 0 <= plane <= int(spec.ny):
                raise ValueError(
                    "X-Z brace panel Y-grid line is outside the frame."
                )
            if not 0 <= bay < int(spec.nx):
                raise ValueError(
                    "X-Z brace panel X bay is outside the frame."
                )
        else:
            if not 0 <= plane <= int(spec.nx):
                raise ValueError(
                    "Y-Z brace panel X-grid line is outside the frame."
                )
            if not 0 <= bay < int(spec.ny):
                raise ValueError(
                    "Y-Z brace panel Y bay is outside the frame."
                )

    if brace_mode == "Truss":
        if joint_model in macro_joint_models:
            raise ValueError(
                "Frame Wizard bracing currently requires the standard "
                "3D/6DOF frame backend; native 2D macro-joint cores are not "
                "combined with braces yet."
            )
        if not bool(spec.create_columns):
            raise ValueError(
                "Frame bracing requires columns."
            )
        if plane_mode in {"X", "Both"} and not bool(spec.create_beams_x):
            raise ValueError(
                "X-Z plane bracing requires X-direction beams."
            )
        if plane_mode in {"Y", "Both"} and not bool(spec.create_beams_y):
            raise ValueError(
                "Y-Z plane bracing requires Y-direction beams."
            )
        if (
            spec.brace_material_tag is None
            or int(spec.brace_material_tag) <= 0
        ):
            raise ValueError(
                "Frame bracing requires a positive uniaxial material tag."
            )
        brace_area = float(spec.brace_area)
        if not math.isfinite(brace_area) or brace_area <= 0.0:
            raise ValueError("Brace area must be finite and positive.")
        brace_mass = float(spec.brace_mass_per_length)
        if not math.isfinite(brace_mass) or brace_mass < 0.0:
            raise ValueError(
                "Brace mass per length must be finite and non-negative."
            )

        active_patterns = {
            brace_pattern,
            *(
                str(raw[4])
                for raw in panel_overrides
                if str(raw[4]) != "None"
            ),
        }
        selected_storeys = (
            brace_storeys
            if brace_storeys
            else tuple(range(1, int(spec.nz) + 1))
        )
        if "VLower" in active_patterns and 1 in selected_storeys:
            # This is conservative: per-panel overrides can disable S1, but
            # the default pattern may still target it. UI removes S1 when
            # VLower is selected globally.
            if brace_pattern == "VLower":
                raise ValueError(
                    "Chevron-to-lower-beam bracing cannot use storey 1 because "
                    "Frame Wizard does not create a beam on the base line."
                )
        if active_patterns & {"VUpper", "VLower"} and (
            str(spec.beam_element_type) != "elasticBeamColumn"
        ):
            raise ValueError(
                "Chevron bracing that meets a beam midpoint currently "
                "requires elasticBeamColumn beams."
            )
        if active_patterns & {"KLeft", "KRight"} and (
            str(spec.column_element_type) != "elasticBeamColumn"
        ):
            raise ValueError(
                "K bracing at a column midpoint currently requires "
                "elasticBeamColumn columns."
            )


    load_mode = str(spec.load_mode or "None")
    if load_mode not in {"None", "Static"}:
        raise ValueError(
            f"Frame Wizard load mode {load_mode!r} is not supported."
        )
    load_storeys = tuple(sorted({int(value) for value in spec.load_storeys}))
    if load_storeys and any(
        value < 1 or value > int(spec.nz)
        for value in load_storeys
    ):
        raise ValueError(
            "Frame Wizard load storeys must be between 1 and the number "
            "of storeys."
        )
    if str(spec.load_beam_scope) not in {"X", "Y", "Both"}:
        raise ValueError(
            "Frame Wizard beam load scope must be X, Y, or Both."
        )
    if str(spec.load_beam_udl_coordinate_system).lower() not in {
        "local", "global"
    }:
        raise ValueError(
            "Frame Wizard beam UDL coordinate system must be local or global."
        )
    udl_vector = tuple(float(value) for value in spec.load_beam_udl_vector)
    if len(udl_vector) != 3 or any(
        not math.isfinite(value) for value in udl_vector
    ):
        raise ValueError(
            "Frame Wizard beam UDL vector requires three finite components."
        )
    density_override = float(spec.load_self_weight_density)
    if (
        not math.isfinite(density_override)
        or density_override < 0.0
    ):
        raise ValueError(
            "Frame Wizard self-weight density override must be finite and "
            "non-negative."
        )
    floor_pressure = float(spec.load_floor_area_pressure)
    if not math.isfinite(floor_pressure) or floor_pressure < 0.0:
        raise ValueError(
            "Frame Wizard floor area pressure must be finite and non-negative."
        )
    floor_direction = str(spec.load_floor_area_direction or "X")
    if floor_direction not in {"X", "Y"}:
        raise ValueError(
            "Frame Wizard floor area load direction must be X or Y."
        )
    mass_mode = str(spec.mass_source_mode or "None")
    if mass_mode not in {"None", "Source"}:
        raise ValueError(
            f"Frame Wizard mass source mode {mass_mode!r} is not supported."
        )
    mass_factor = float(spec.mass_static_load_factor)
    if not math.isfinite(mass_factor) or mass_factor < 0.0:
        raise ValueError(
            "Frame Wizard mass-source static load factor must be finite and "
            "non-negative."
        )
    mass_axis = int(spec.mass_gravity_axis)
    if mass_axis not in (1, 2, 3):
        raise ValueError(
            "Frame Wizard mass-source gravity axis must be X, Y, or Z."
        )
    mass_directions = tuple(
        sorted({int(value) for value in spec.mass_directions})
    )
    if mass_directions and any(
        value not in (1, 2, 3) for value in mass_directions
    ):
        raise ValueError(
            "Frame Wizard mass-source directions must be translational DOFs "
            "1, 2, or 3."
        )
    if mass_mode == "Source":
        if not mass_directions:
            raise ValueError(
                "Frame Wizard mass source needs at least one direction."
            )
        if (
            not bool(spec.mass_include_self)
            and not bool(spec.mass_include_static_loads)
        ):
            raise ValueError(
                "Frame Wizard mass source must include structural self mass "
                "and/or the generated static load pattern."
            )
        if bool(spec.mass_include_static_loads):
            if load_mode != "Static":
                raise ValueError(
                    "Frame Wizard mass source cannot convert static loads "
                    "because automatic static load generation is disabled."
                )
            if mass_factor <= 0.0:
                raise ValueError(
                    "Frame Wizard mass-source static load factor must be "
                    "positive when static loads are included."
                )
        if (
            str(spec.diaphragm_mode or "None") == "Rigid"
            and float(spec.diaphragm_floor_mass) > 0.0
        ):
            raise ValueError(
                "Automatic Mass Source replaces selected nodal mass and cannot "
                "be combined with explicit rigid-diaphragm floor mass. Set the "
                "floor mass to zero and derive mass from gravity loads, or "
                "disable the automatic Mass Source."
            )
        if (
            str(spec.diaphragm_mode or "None") == "Shell"
            and float(spec.slab_mass_per_area) > 0.0
        ):
            raise ValueError(
                "Automatic Mass Source replaces selected nodal mass and cannot "
                "be combined with additional slab nodal mass. Set slab mass "
                "per area to zero and derive mass from gravity loads, or "
                "disable the automatic Mass Source."
            )

    if load_mode == "Static":
        if joint_model in macro_joint_models:
            raise ValueError(
                "Frame Wizard automatic loads currently require the standard "
                "3D/6DOF frame backend; native 2D macro-joint cores are not "
                "combined with automatic loads yet."
            )
        if (
            not bool(spec.load_self_weight)
            and not bool(spec.load_beam_udl)
            and not bool(spec.load_floor_area)
        ):
            raise ValueError(
                "Frame Wizard static load mode requires self-weight, beam UDL "
                "and/or floor area load."
            )
        beam_scope = str(spec.load_beam_scope)
        if spec.planar_2d and beam_scope in {"Y", "Both"}:
            if beam_scope == "Y":
                raise ValueError(
                    "Planar Frame Wizard models have no Y-direction beams."
                )
        if bool(spec.load_beam_udl):
            if all(abs(value) <= 1.0e-15 for value in udl_vector):
                raise ValueError(
                    "Frame Wizard beam UDL vector cannot be zero."
                )
            if beam_scope in {"X", "Both"} and not bool(spec.create_beams_x):
                raise ValueError(
                    "X beam UDL requires X-direction beams."
                )
            if (
                not spec.planar_2d
                and beam_scope in {"Y", "Both"}
                and not bool(spec.create_beams_y)
            ):
                raise ValueError(
                    "Y beam UDL requires Y-direction beams."
                )
        if bool(spec.load_floor_area):
            if spec.planar_2d:
                raise ValueError(
                    "Floor area load tributary distribution requires a 3D "
                    "Frame Wizard model."
                )
            if floor_pressure <= 0.0:
                raise ValueError(
                    "Frame Wizard floor area pressure must be positive."
                )
            if floor_direction == "X" and not bool(spec.create_beams_x):
                raise ValueError(
                    "Floor area load to X beams requires X-direction beams."
                )
            if floor_direction == "Y" and not bool(spec.create_beams_y):
                raise ValueError(
                    "Floor area load to Y beams requires Y-direction beams."
                )

    frame_grid_coordinates(spec)


def generate_frame_grid(model: StructuralModel, spec: FrameGridSpec) -> None:
    """Create a regular or individually-spaced frame grid.

    Standard mode creates a 3-D X-Y-Z frame. Planar mode creates an X-Z
    frame while retaining the Studio 3-D / 6-DOF backend and automatically
    restraining all out-of-plane DOFs.
    """
    validate_frame_grid_spec(spec)
    x_coordinates, y_coordinates, z_coordinates = frame_grid_coordinates(spec)
    model.clear()

    if spec.planar_2d:
        if spec.planar_base_support not in {"Fixed", "Pinned"}:
            raise ValueError(
                "2D frame base support must be Fixed or Pinned."
            )
        node_tag = spec.start_node_tag
        node_at_2d: dict[tuple[int, int], int] = {}
        out_of_plane = (0, 1, 0, 1, 0, 1)

        for k in range(spec.nz + 1):
            for i in range(spec.nx + 1):
                model.add_node(
                    node_tag,
                    x_coordinates[i],
                    y_coordinates[0],
                    z_coordinates[k],
                )
                node_at_2d[(i, k)] = node_tag
                model.set_fixity(node_tag, out_of_plane)
                node_tag += 1

        ele_tag = spec.start_element_tag
        if spec.create_columns:
            for k in range(spec.nz):
                for i in range(spec.nx + 1):
                    model.add_element(
                        ele_tag,
                        node_at_2d[(i, k)],
                        node_at_2d[(i, k + 1)],
                        element_type=spec.column_element_type,
                        section_tag=spec.column_section_tag,
                        transf_tag=spec.column_transf_tag,
                        group="column-2d",
                        integration_type=spec.column_integration_type,
                        integration_points=spec.column_integration_points,
                        mass_per_length=spec.column_mass_per_length,
                        consistent_mass=spec.column_consistent_mass,
                        hinge_i_section_tag=spec.column_hinge_i_section_tag,
                        hinge_j_section_tag=spec.column_hinge_j_section_tag,
                        interior_section_tag=spec.column_interior_section_tag,
                        hinge_i_length=spec.column_hinge_i_length,
                        hinge_j_length=spec.column_hinge_j_length,
                    )
                    ele_tag += 1

        if spec.create_beams_x:
            for k in range(1, spec.nz + 1):
                for i in range(spec.nx):
                    model.add_element(
                        ele_tag,
                        node_at_2d[(i, k)],
                        node_at_2d[(i + 1, k)],
                        element_type=spec.beam_element_type,
                        section_tag=spec.beam_section_tag,
                        transf_tag=spec.beam_transf_tag,
                        group="beam-2d",
                        integration_type=spec.beam_integration_type,
                        integration_points=spec.beam_integration_points,
                        mass_per_length=spec.beam_mass_per_length,
                        consistent_mass=spec.beam_consistent_mass,
                        hinge_i_section_tag=spec.beam_hinge_i_section_tag,
                        hinge_j_section_tag=spec.beam_hinge_j_section_tag,
                        interior_section_tag=spec.beam_interior_section_tag,
                        hinge_i_length=spec.beam_hinge_i_length,
                        hinge_j_length=spec.beam_hinge_j_length,
                    )
                    ele_tag += 1

        base_fixity = (
            (1, 1, 1, 1, 1, 1)
            if spec.planar_base_support == "Fixed"
            else (1, 1, 1, 1, 0, 1)
        )
        for i in range(spec.nx + 1):
            model.set_fixity(node_at_2d[(i, 0)], base_fixity)
        return
    node_tag = spec.start_node_tag
    node_at: dict[tuple[int, int, int], int] = {}

    for k in range(spec.nz + 1):
        for j in range(spec.ny + 1):
            for i in range(spec.nx + 1):
                model.add_node(
                    node_tag,
                    x_coordinates[i],
                    y_coordinates[j],
                    z_coordinates[k],
                )
                node_at[(i, j, k)] = node_tag
                node_tag += 1

    ele_tag = spec.start_element_tag

    if spec.create_columns:
        for k in range(spec.nz):
            for j in range(spec.ny + 1):
                for i in range(spec.nx + 1):
                    model.add_element(
                        ele_tag,
                        node_at[(i, j, k)],
                        node_at[(i, j, k + 1)],
                        element_type=spec.column_element_type,
                        section_tag=spec.column_section_tag,
                        transf_tag=spec.column_transf_tag,
                        group="column",
                        integration_type=spec.column_integration_type,
                        integration_points=spec.column_integration_points,
                        mass_per_length=spec.column_mass_per_length,
                        consistent_mass=spec.column_consistent_mass,
                        hinge_i_section_tag=spec.column_hinge_i_section_tag,
                        hinge_j_section_tag=spec.column_hinge_j_section_tag,
                        interior_section_tag=spec.column_interior_section_tag,
                        hinge_i_length=spec.column_hinge_i_length,
                        hinge_j_length=spec.column_hinge_j_length,
                    )
                    ele_tag += 1

    if spec.create_beams_x:
        for k in range(1, spec.nz + 1):
            for j in range(spec.ny + 1):
                for i in range(spec.nx):
                    model.add_element(
                        ele_tag,
                        node_at[(i, j, k)],
                        node_at[(i + 1, j, k)],
                        element_type=spec.beam_element_type,
                        section_tag=spec.beam_section_tag,
                        transf_tag=spec.beam_transf_tag,
                        group="beam-x",
                        integration_type=spec.beam_integration_type,
                        integration_points=spec.beam_integration_points,
                        mass_per_length=spec.beam_mass_per_length,
                        consistent_mass=spec.beam_consistent_mass,
                        hinge_i_section_tag=spec.beam_hinge_i_section_tag,
                        hinge_j_section_tag=spec.beam_hinge_j_section_tag,
                        interior_section_tag=spec.beam_interior_section_tag,
                        hinge_i_length=spec.beam_hinge_i_length,
                        hinge_j_length=spec.beam_hinge_j_length,
                    )
                    ele_tag += 1

    if spec.create_beams_y:
        for k in range(1, spec.nz + 1):
            for j in range(spec.ny):
                for i in range(spec.nx + 1):
                    model.add_element(
                        ele_tag,
                        node_at[(i, j, k)],
                        node_at[(i, j + 1, k)],
                        element_type=spec.beam_element_type,
                        section_tag=spec.beam_section_tag,
                        transf_tag=spec.beam_transf_tag,
                        group="beam-y",
                        integration_type=spec.beam_integration_type,
                        integration_points=spec.beam_integration_points,
                        mass_per_length=spec.beam_mass_per_length,
                        consistent_mass=spec.beam_consistent_mass,
                        hinge_i_section_tag=spec.beam_hinge_i_section_tag,
                        hinge_j_section_tag=spec.beam_hinge_j_section_tag,
                        interior_section_tag=spec.beam_interior_section_tag,
                        hinge_i_length=spec.beam_hinge_i_length,
                        hinge_j_length=spec.beam_hinge_j_length,
                    )
                    ele_tag += 1

    for j in range(spec.ny + 1):
        for i in range(spec.nx + 1):
            model.set_fixity(node_at[(i, j, 0)], (1, 1, 1, 1, 1, 1))


def frame_joint_connection_count(spec: FrameGridSpec) -> int:
    """Return the number of explicit joint connection objects to create."""
    joint_model = str(spec.joint_model or "None")
    if joint_model == "None" or not bool(spec.create_columns):
        return 0

    nx = int(spec.nx)
    nz = int(spec.nz)
    scope = str(spec.joint_scope or "all")

    if joint_model in {
        "Joint2D",
        "BeamColumnJoint",
        "KrawinklerPanelZone",
    }:
        if not spec.planar_2d or not spec.create_beams_x:
            return 0
        x_indices = range(nx + 1)
        if scope == "interior":
            x_indices = range(1, nx)
        return len(tuple(x_indices)) * nz

    if spec.planar_2d:
        x_indices = range(nx + 1)
        if scope == "interior":
            x_indices = range(1, nx)
        joint_nodes = len(tuple(x_indices)) * nz
        return joint_nodes if spec.create_beams_x else 0

    ny = int(spec.ny)
    x_indices = range(nx + 1)
    y_indices = range(ny + 1)
    if scope == "interior":
        x_indices = range(1, nx)
        y_indices = range(1, ny)
    joint_nodes = len(tuple(x_indices)) * len(tuple(y_indices)) * nz
    per_joint = int(bool(spec.create_beams_x)) + int(bool(spec.create_beams_y))
    return joint_nodes * per_joint


def _frame_center_node_tag(
    spec: FrameGridSpec,
    i: int,
    j: int,
    k: int,
) -> int:
    if spec.planar_2d:
        return int(spec.start_node_tag) + k * (int(spec.nx) + 1) + i
    plane = (int(spec.nx) + 1) * (int(spec.ny) + 1)
    return (
        int(spec.start_node_tag)
        + k * plane
        + j * (int(spec.nx) + 1)
        + i
    )


def apply_frame_zero_length_joints(project, spec: FrameGridSpec) -> dict[str, int]:
    """Insert semi-rigid beam-column joints into an already-built frame grid.

    The column/grid node remains the retained joint node.  Each active beam
    family receives a coincident duplicate node. Beam elements are rewired to
    that duplicate, all non-spring DOFs are tied back with equalDOF, and one
    zeroLength rotational spring connects the duplicate to the column node.
    """
    validate_frame_grid_spec(spec)
    if str(spec.joint_model or "None") != "ZeroLength":
        return {
            "joint_nodes": 0,
            "joint_connections": 0,
            "duplicate_nodes": 0,
            "joint_constraints": 0,
        }

    material_tag = int(spec.joint_material_tag)
    if material_tag not in project.materials:
        raise ValueError(
            f"Joint rotational material tag {material_tag} does not exist."
        )

    model = project.model
    next_node_tag = max(model.nodes, default=0) + 1
    next_connection_tag = max(
        max(model.elements, default=0),
        max(project.connections, default=0),
    ) + 1
    next_constraint_tag = max(project.constraints, default=0) + 1
    nx = int(spec.nx)
    ny = 1 if spec.planar_2d else int(spec.ny)
    nz = int(spec.nz)
    scope = str(spec.joint_scope or "all")

    x_indices = list(range(nx + 1))
    y_indices = [0] if spec.planar_2d else list(range(ny + 1))
    if scope == "interior":
        x_indices = list(range(1, nx))
        if not spec.planar_2d:
            y_indices = list(range(1, ny))

    joint_nodes: set[int] = set()
    connection_count = 0
    constraint_count = 0
    duplicate_count = 0

    for k in range(1, nz + 1):
        for j in y_indices:
            for i in x_indices:
                center_tag = _frame_center_node_tag(spec, i, j, k)
                center = model.nodes.get(center_tag)
                if center is None:
                    continue

                axes: list[tuple[str, int]] = []
                if spec.create_beams_x:
                    axes.append(("beam-2d" if spec.planar_2d else "beam-x", 5))
                if not spec.planar_2d and spec.create_beams_y:
                    axes.append(("beam-y", 4))

                created_here = False
                for group, spring_dof in axes:
                    connected = [
                        element
                        for element in model.elements.values()
                        if element.group == group
                        and (element.i == center_tag or element.j == center_tag)
                    ]
                    if not connected:
                        continue

                    duplicate_tag = next_node_tag
                    next_node_tag += 1
                    duplicate = model.add_node(
                        duplicate_tag,
                        center.xyz[0],
                        center.xyz[1],
                        center.xyz[2],
                        ndf=center.ndf,
                    )
                    duplicate.mass = (0.0,) * int(duplicate.ndf)

                    for element in connected:
                        if element.i == center_tag:
                            element.i = duplicate_tag
                        if element.j == center_tag:
                            element.j = duplicate_tag

                    tied_dofs = tuple(
                        dof
                        for dof in range(1, int(center.ndf) + 1)
                        if dof != spring_dof
                    )
                    constraint = ConstraintData(
                        tag=next_constraint_tag,
                        name=(
                            f"Frame joint tie N{center_tag}-{duplicate_tag}"
                        ),
                        constraint_type="equalDOF",
                        retained_node=center_tag,
                        constrained_nodes=[duplicate_tag],
                        dofs=tied_dofs,
                    )
                    project.add_constraint(constraint)
                    next_constraint_tag += 1
                    constraint_count += 1

                    connection = ConnectionData(
                        tag=next_connection_tag,
                        name=(
                            f"Frame joint {group} N{center_tag}"
                        ),
                        connection_type="zeroLength",
                        node_i=center_tag,
                        node_j=duplicate_tag,
                        materials_by_dof={spring_dof: material_tag},
                        generated_constraint_tag=constraint.tag,
                    )
                    project.add_connection(connection)
                    next_connection_tag += 1
                    connection_count += 1
                    duplicate_count += 1
                    created_here = True

                if created_here:
                    joint_nodes.add(center_tag)

    return {
        "joint_nodes": len(joint_nodes),
        "joint_connections": connection_count,
        "duplicate_nodes": duplicate_count,
        "joint_constraints": constraint_count,
    }


def _frame_add_member(
    model: StructuralModel,
    tag: int,
    i_node: int,
    j_node: int,
    *,
    role: str,
    spec: FrameGridSpec,
) -> None:
    is_column = role == "column"
    model.add_element(
        tag,
        i_node,
        j_node,
        element_type=(
            spec.column_element_type if is_column else spec.beam_element_type
        ),
        section_tag=(
            spec.column_section_tag if is_column else spec.beam_section_tag
        ),
        transf_tag=(
            spec.column_transf_tag if is_column else spec.beam_transf_tag
        ),
        group="column-2d" if is_column else "beam-2d",
        integration_type=(
            spec.column_integration_type
            if is_column else spec.beam_integration_type
        ),
        integration_points=(
            spec.column_integration_points
            if is_column else spec.beam_integration_points
        ),
        mass_per_length=(
            spec.column_mass_per_length
            if is_column else spec.beam_mass_per_length
        ),
        consistent_mass=(
            spec.column_consistent_mass
            if is_column else spec.beam_consistent_mass
        ),
        hinge_i_section_tag=(
            spec.column_hinge_i_section_tag
            if is_column else spec.beam_hinge_i_section_tag
        ),
        hinge_j_section_tag=(
            spec.column_hinge_j_section_tag
            if is_column else spec.beam_hinge_j_section_tag
        ),
        interior_section_tag=(
            spec.column_interior_section_tag
            if is_column else spec.beam_interior_section_tag
        ),
        hinge_i_length=(
            spec.column_hinge_i_length
            if is_column else spec.beam_hinge_i_length
        ),
        hinge_j_length=(
            spec.column_hinge_j_length
            if is_column else spec.beam_hinge_j_length
        ),
    )


def _frame_macro_material_tags(spec: FrameGridSpec) -> set[int]:
    model = str(spec.joint_model or "None")
    tags: set[int] = set()
    if model in {"Joint2D", "KrawinklerPanelZone"}:
        if spec.joint_material_tag is not None:
            tags.add(int(spec.joint_material_tag))
    if model == "Joint2D":
        tags.update(
            int(tag)
            for tag in spec.joint_interface_material_tags
            if int(tag) > 0
        )
    if model == "BeamColumnJoint":
        tags.update(int(tag) for tag in spec.joint_component_material_tags)
    return tags


def generate_frame_macro_joint_project(
    project,
    spec: FrameGridSpec,
) -> dict[str, int]:
    """Build a native 2D frame whose selected intersections are joint cores."""
    validate_frame_grid_spec(spec)
    joint_model = str(spec.joint_model)
    if joint_model not in {
        "Joint2D",
        "BeamColumnJoint",
        "KrawinklerPanelZone",
    }:
        raise ValueError("Macro-joint frame generator received a non-macro model.")

    missing_materials = sorted(
        tag
        for tag in _frame_macro_material_tags(spec)
        if tag not in project.materials
    )
    if missing_materials:
        raise ValueError(
            "Joint material tag(s) do not exist: "
            + ", ".join(map(str, missing_materials))
        )

    x_coordinates, _, z_coordinates = frame_grid_coordinates(spec)
    model = project.model
    model.clear()
    model.ndm = 2
    model.ndf = 3

    nx = int(spec.nx)
    nz = int(spec.nz)
    scope = str(spec.joint_scope or "all")
    active_i = set(range(nx + 1))
    if scope == "interior":
        active_i = set(range(1, nx))

    macro_points = {
        (i, k)
        for k in range(1, nz + 1)
        for i in active_i
    }
    node_tag = int(spec.start_node_tag)
    centers: dict[tuple[int, int], int] = {}
    cores: dict[tuple[int, int], dict[str, int]] = {}
    half_width = 0.5 * float(spec.joint_panel_width)
    half_height = 0.5 * float(spec.joint_panel_height)

    for k in range(nz + 1):
        for i in range(nx + 1):
            x = float(x_coordinates[i])
            y = float(z_coordinates[k])
            if (i, k) in macro_points:
                core: dict[str, int] = {}
                for key, px, py in (
                    ("left", x - half_width, y),
                    ("top", x, y + half_height),
                    ("right", x + half_width, y),
                    ("bottom", x, y - half_height),
                ):
                    model.add_node(node_tag, px, py, 0.0, ndf=3)
                    core[key] = node_tag
                    node_tag += 1
                cores[(i, k)] = core
            else:
                model.add_node(node_tag, x, y, 0.0, ndf=3)
                centers[(i, k)] = node_tag
                node_tag += 1

    def vertical_endpoint(i: int, k: int, *, leaving_up: bool) -> int:
        core = cores.get((i, k))
        if core is None:
            return centers[(i, k)]
        return core["top" if leaving_up else "bottom"]

    def horizontal_endpoint(i: int, k: int, *, leaving_right: bool) -> int:
        core = cores.get((i, k))
        if core is None:
            return centers[(i, k)]
        return core["right" if leaving_right else "left"]

    ele_tag = int(spec.start_element_tag)
    if spec.create_columns:
        for k in range(nz):
            for i in range(nx + 1):
                _frame_add_member(
                    model,
                    ele_tag,
                    vertical_endpoint(i, k, leaving_up=True),
                    vertical_endpoint(i, k + 1, leaving_up=False),
                    role="column",
                    spec=spec,
                )
                ele_tag += 1

    if spec.create_beams_x:
        for k in range(1, nz + 1):
            for i in range(nx):
                _frame_add_member(
                    model,
                    ele_tag,
                    horizontal_endpoint(i, k, leaving_right=True),
                    horizontal_endpoint(i + 1, k, leaving_right=False),
                    role="beam",
                    spec=spec,
                )
                ele_tag += 1

    base_fixity = (
        (1, 1, 1)
        if spec.planar_base_support == "Fixed"
        else (1, 1, 0)
    )
    for i in range(nx + 1):
        model.set_fixity(centers[(i, 0)], base_fixity)

    connection_tag = max(model.elements, default=0) + 1
    for i, k in sorted(macro_points, key=lambda item: (item[1], item[0])):
        core = cores[(i, k)]
        external_nodes = [
            core["left"],
            core["top"],
            core["right"],
            core["bottom"],
        ]
        if joint_model == "BeamColumnJoint":
            # OpenSees BeamColumnJoint uses opposite 1↔3 nodes along the
            # vertical chord and 2↔4 along the horizontal chord.
            external_nodes = [
                core["top"],
                core["right"],
                core["bottom"],
                core["left"],
            ]
        parameters: dict[str, object] = {
            "external_nodes": external_nodes,
        }
        if joint_model == "Joint2D":
            parameters.update({
                "panel_material": int(spec.joint_material_tag),
                "interface_materials": [
                    int(tag) for tag in spec.joint_interface_material_tags
                ],
                "large_disp": int(spec.joint_large_disp),
            })
        elif joint_model == "BeamColumnJoint":
            parameters.update({
                "component_materials": [
                    int(tag) for tag in spec.joint_component_material_tags
                ],
                "height_factor": float(spec.joint_height_factor),
                "width_factor": float(spec.joint_width_factor),
            })
        else:
            parameters.update({
                "panel_material": int(spec.joint_material_tag),
                "rigid_A": float(spec.joint_rigid_a),
                "rigid_E": float(spec.joint_rigid_e),
                "rigid_I": float(spec.joint_rigid_i),
            })

        project.add_connection(
            ConnectionData(
                tag=connection_tag,
                name=f"Frame {joint_model} joint X{i + 1}-L{k}",
                connection_type=joint_model,
                node_i=core["left"],
                node_j=core["right"],
                materials_by_dof={},
                parameters=parameters,
            )
        )
        connection_tag += 1

    return {
        "joint_nodes": len(macro_points),
        "joint_connections": len(macro_points),
        "duplicate_nodes": 0,
        "joint_constraints": 0,
        "panel_external_nodes": 4 * len(macro_points),
    }


def frame_floor_levels(spec: FrameGridSpec) -> tuple[int, ...]:
    """Return normalized elevated levels selected for rigid/shell floor action."""
    if str(spec.diaphragm_mode or "None") not in {"Rigid", "Shell"}:
        return ()
    levels = tuple(sorted({int(level) for level in spec.diaphragm_levels}))
    if levels:
        return levels
    return tuple(range(1, int(spec.nz) + 1))


def frame_diaphragm_levels(spec: FrameGridSpec) -> tuple[int, ...]:
    """Return normalized elevated floor levels selected for rigid diaphragm."""
    if str(spec.diaphragm_mode or "None") != "Rigid":
        return ()
    return frame_floor_levels(spec)


def frame_diaphragm_count(spec: FrameGridSpec) -> int:
    """Return the number of rigid floor diaphragms requested."""
    return len(frame_diaphragm_levels(spec))


def frame_slab_count(spec: FrameGridSpec) -> int:
    """Return the number of explicit shell slab floors requested."""
    if str(spec.diaphragm_mode or "None") != "Shell":
        return 0
    return len(frame_floor_levels(spec))


def apply_frame_rigid_diaphragms(
    project,
    spec: FrameGridSpec,
) -> dict[str, int]:
    """Create one centroid retained node and rigidDiaphragm MPC per floor."""
    validate_frame_grid_spec(spec)
    if str(spec.diaphragm_mode or "None") != "Rigid":
        return {
            "diaphragm_constraints": 0,
            "diaphragm_master_nodes": 0,
        }

    model = project.model
    if (int(model.ndm), int(model.ndf)) != (3, 6):
        raise ValueError(
            "Rigid floor diaphragms require the standard 3D/6DOF frame backend."
        )

    x_coordinates, y_coordinates, z_coordinates = frame_grid_coordinates(spec)
    next_node_tag = max(model.nodes, default=0) + 1
    next_constraint_tag = max(project.constraints, default=0) + 1
    floor_mass = float(spec.diaphragm_floor_mass)
    rotational_inertia = float(spec.diaphragm_rotational_inertia)
    levels = frame_diaphragm_levels(spec)

    x_center = 0.5 * (x_coordinates[0] + x_coordinates[-1])
    y_center = 0.5 * (y_coordinates[0] + y_coordinates[-1])

    for level in levels:
        master_tag = next_node_tag
        next_node_tag += 1
        master = model.add_node(
            master_tag,
            x_center,
            y_center,
            z_coordinates[level],
            ndf=6,
        )
        # rigidDiaphragm with perpDirn=3 couples UX, UY and RZ. Restrain
        # unused retained-node DOFs to avoid free zero-stiffness modes.
        model.set_fixity(master_tag, (0, 0, 1, 1, 1, 0))
        master.mass = (
            floor_mass,
            floor_mass,
            0.0,
            0.0,
            0.0,
            rotational_inertia,
        )

        floor_nodes = [
            _frame_center_node_tag(spec, i, j, level)
            for j in range(int(spec.ny) + 1)
            for i in range(int(spec.nx) + 1)
        ]
        project.add_constraint(
            ConstraintData(
                tag=next_constraint_tag,
                name=f"Frame floor {level} rigid diaphragm",
                constraint_type="rigidDiaphragm",
                retained_node=master_tag,
                constrained_nodes=floor_nodes,
                perp_dirn=3,
            )
        )
        next_constraint_tag += 1

    return {
        "diaphragm_constraints": len(levels),
        "diaphragm_master_nodes": len(levels),
    }


def _frame_refined_axis(
    coordinates: list[float],
    divisions_per_bay: int,
) -> list[float]:
    result = [float(coordinates[0])]
    divisions = int(divisions_per_bay)
    for left, right in zip(coordinates[:-1], coordinates[1:]):
        for index in range(1, divisions + 1):
            ratio = index / divisions
            result.append(
                float(left) + ratio * (float(right) - float(left))
            )
    return result


def _frame_coordinate_node_lookup(
    model: StructuralModel,
    *,
    tolerance: float,
) -> dict[tuple[int, int, int], int]:
    lookup: dict[tuple[int, int, int], int] = {}
    for tag, node in sorted(model.nodes.items()):
        key = tuple(
            int(round(float(value) / tolerance))
            for value in node.xyz
        )
        lookup.setdefault(key, int(tag))
    return lookup


def _frame_find_or_create_node(
    model: StructuralModel,
    lookup: dict[tuple[int, int, int], int],
    xyz: tuple[float, float, float],
    *,
    tolerance: float,
) -> tuple[int, bool]:
    key = tuple(
        int(round(float(value) / tolerance))
        for value in xyz
    )
    existing = lookup.get(key)
    if existing is not None:
        node = model.nodes.get(existing)
        if (
            node is not None
            and sum(
                (float(node.xyz[index]) - float(xyz[index])) ** 2
                for index in range(3)
            ) <= tolerance * tolerance
        ):
            return int(existing), False

    tag = model.next_node_tag()
    model.add_node(tag, *xyz, ndf=6)
    lookup[key] = int(tag)
    return int(tag), True


def _frame_clone_member_segment(
    model: StructuralModel,
    source,
    tag: int,
    node_i: int,
    node_j: int,
) -> None:
    model.add_element(
        tag,
        node_i,
        node_j,
        element_type=source.element_type,
        section_tag=source.section_tag,
        transf_tag=source.transf_tag,
        group=source.group,
        integration_type=source.integration_type,
        integration_points=source.integration_points,
        force_max_iter=source.force_max_iter,
        force_tolerance=source.force_tolerance,
        mass_per_length=source.mass_per_length,
        consistent_mass=source.consistent_mass,
        hinge_i_section_tag=source.hinge_i_section_tag,
        hinge_j_section_tag=source.hinge_j_section_tag,
        interior_section_tag=source.interior_section_tag,
        hinge_i_length=source.hinge_i_length,
        hinge_j_length=source.hinge_j_length,
        beam_center_ratio=source.beam_center_ratio,
    )


def apply_frame_shell_slabs(
    project,
    spec: FrameGridSpec,
) -> dict[str, int]:
    """Mesh selected 3D floors with conforming quadrilateral shell elements."""
    validate_frame_grid_spec(spec)
    if str(spec.diaphragm_mode or "None") != "Shell":
        return {
            "slab_floors": 0,
            "slab_elements": 0,
            "slab_nodes_created": 0,
            "slab_beam_segments_added": 0,
            "slab_mass_nodes": 0,
        }

    section_tag = int(spec.slab_section_tag)
    section = project.sections.get(section_tag)
    if section is None:
        raise ValueError(
            f"Slab section tag {section_tag} does not exist in the project."
        )
    if section.section_type not in SHELL_SECTION_TYPES:
        raise ValueError(
            f"Slab section {section_tag} is not shell-compatible."
        )

    model = project.model
    if (int(model.ndm), int(model.ndf)) != (3, 6):
        raise ValueError(
            "Explicit shell slabs require the standard 3D/6DOF frame backend."
        )

    x_base, y_base, z_coordinates = frame_grid_coordinates(spec)
    x_mesh = _frame_refined_axis(x_base, int(spec.slab_divisions_x))
    y_mesh = _frame_refined_axis(y_base, int(spec.slab_divisions_y))
    levels = frame_floor_levels(spec)
    span = max(
        x_mesh[-1] - x_mesh[0],
        y_mesh[-1] - y_mesh[0],
        z_coordinates[-1] - z_coordinates[0],
        1.0,
    )
    tolerance = 1.0e-9 * span
    lookup = _frame_coordinate_node_lookup(
        model,
        tolerance=tolerance,
    )

    floor_grids: dict[int, list[list[int]]] = {}
    created_count = 0
    reused_count = 0
    for level in levels:
        z = float(z_coordinates[level])
        grid: list[list[int]] = []
        for y in y_mesh:
            row: list[int] = []
            for x in x_mesh:
                node_tag, created = _frame_find_or_create_node(
                    model,
                    lookup,
                    (float(x), float(y), z),
                    tolerance=tolerance,
                )
                row.append(node_tag)
                if created:
                    created_count += 1
                else:
                    reused_count += 1
            grid.append(row)
        floor_grids[int(level)] = grid

    # Refined slabs need matching nodes along every beam line. Split only
    # elastic frame beams; validation prevents nonlinear hinge duplication.
    split_count = 0
    if int(spec.slab_divisions_x) > 1 or int(spec.slab_divisions_y) > 1:
        original_beams = [
            element
            for element in list(model.elements.values())
            if element.group in {"beam-x", "beam-y"}
        ]
        next_element_tag = max(model.elements, default=0) + 1
        selected_z = {
            round(float(z_coordinates[level]), 12)
            for level in levels
        }
        for element in original_beams:
            node_i = model.nodes[int(element.i)]
            node_j = model.nodes[int(element.j)]
            if round(float(node_i.xyz[2]), 12) not in selected_z:
                continue
            if abs(float(node_i.xyz[2]) - float(node_j.xyz[2])) > tolerance:
                continue

            divisions = (
                int(spec.slab_divisions_x)
                if element.group == "beam-x"
                else int(spec.slab_divisions_y)
            )
            if divisions <= 1:
                continue

            points: list[int] = []
            for index in range(divisions + 1):
                ratio = index / divisions
                xyz = tuple(
                    float(node_i.xyz[axis])
                    + ratio * (
                        float(node_j.xyz[axis])
                        - float(node_i.xyz[axis])
                    )
                    for axis in range(3)
                )
                tag, _created = _frame_find_or_create_node(
                    model,
                    lookup,
                    xyz,
                    tolerance=tolerance,
                )
                points.append(tag)

            original_tag = int(element.tag)
            model.elements.pop(original_tag)
            _frame_clone_member_segment(
                model,
                element,
                original_tag,
                points[0],
                points[1],
            )
            for left, right in zip(points[1:-1], points[2:]):
                while next_element_tag in model.elements:
                    next_element_tag += 1
                _frame_clone_member_segment(
                    model,
                    element,
                    next_element_tag,
                    left,
                    right,
                )
                next_element_tag += 1
                split_count += 1

    shell_count = 0
    next_element_tag = max(model.elements, default=0) + 1
    mass_per_area = float(spec.slab_mass_per_area)
    mass_added: dict[int, float] = {}

    for level in levels:
        grid = floor_grids[int(level)]
        for j in range(len(y_mesh) - 1):
            for i in range(len(x_mesh) - 1):
                n1 = grid[j][i]
                n2 = grid[j][i + 1]
                n3 = grid[j + 1][i + 1]
                n4 = grid[j + 1][i]
                while next_element_tag in model.elements:
                    next_element_tag += 1
                model.add_element(
                    next_element_tag,
                    n1,
                    n2,
                    element_type=str(spec.slab_element_type),
                    section_tag=section_tag,
                    group=f"slab:L{int(level)}",
                    k=n3,
                    l=n4,
                    shell_corotational=(
                        bool(spec.slab_corotational)
                        if str(spec.slab_element_type) == "ASDShellQ4"
                        else False
                    ),
                )
                shell_count += 1

                if mass_per_area > 0.0:
                    area = (
                        abs(float(x_mesh[i + 1]) - float(x_mesh[i]))
                        * abs(float(y_mesh[j + 1]) - float(y_mesh[j]))
                    )
                    share = 0.25 * mass_per_area * area
                    for node_tag in (n1, n2, n3, n4):
                        mass_added[node_tag] = (
                            mass_added.get(node_tag, 0.0) + share
                        )
                next_element_tag += 1

    for node_tag, added_mass in mass_added.items():
        node = model.nodes[int(node_tag)]
        values = list(node.mass)
        while len(values) < 6:
            values.append(0.0)
        for index in (0, 1, 2):
            values[index] += float(added_mass)
        node.mass = tuple(values[:6])

    return {
        "slab_floors": len(levels),
        "slab_elements": shell_count,
        "slab_nodes_created": created_count,
        "slab_nodes_reused": reused_count,
        "slab_beam_segments_added": split_count,
        "slab_mass_nodes": len(mass_added),
    }


def frame_brace_x_bays(spec: FrameGridSpec) -> tuple[int, ...]:
    values = tuple(sorted({int(value) for value in spec.brace_x_bays}))
    return values if values else tuple(range(int(spec.nx)))


def frame_brace_y_bays(spec: FrameGridSpec) -> tuple[int, ...]:
    values = tuple(sorted({int(value) for value in spec.brace_y_bays}))
    return values if values else tuple(range(int(spec.ny)))


def frame_brace_storeys(spec: FrameGridSpec) -> tuple[int, ...]:
    values = tuple(sorted({int(value) for value in spec.brace_storeys}))
    return values if values else tuple(range(1, int(spec.nz) + 1))


def frame_brace_y_grid_lines(spec: FrameGridSpec) -> tuple[int, ...]:
    if spec.planar_2d:
        return (0,)
    ny = int(spec.ny)
    scope = str(spec.brace_y_plane_scope or "All")
    if scope == "YMin":
        return (0,)
    if scope == "YMax":
        return (ny,)
    if scope == "Exterior":
        return (0,) if ny == 0 else (0, ny)
    return tuple(range(ny + 1))


def frame_brace_x_grid_lines(spec: FrameGridSpec) -> tuple[int, ...]:
    nx = int(spec.nx)
    scope = str(spec.brace_x_plane_scope or "All")
    if scope == "XMin":
        return (0,)
    if scope == "XMax":
        return (nx,)
    if scope == "Exterior":
        return (0,) if nx == 0 else (0, nx)
    return tuple(range(nx + 1))


def frame_brace_panel_pattern_map(
    spec: FrameGridSpec,
) -> dict[tuple[str, int, int, int], str]:
    return {
        (str(axis), int(plane), int(bay), int(storey)): str(pattern)
        for axis, plane, bay, storey, pattern in spec.brace_panel_patterns
    }


def frame_brace_panels(
    spec: FrameGridSpec,
) -> tuple[tuple[str, int, int, int, str], ...]:
    if str(spec.brace_mode or "None") != "Truss":
        return ()
    mode = str(spec.brace_plane_mode or "X")
    overrides = frame_brace_panel_pattern_map(spec)
    panels: list[tuple[str, int, int, int, str]] = []

    if mode in {"X", "Both"}:
        for storey in frame_brace_storeys(spec):
            for plane in frame_brace_y_grid_lines(spec):
                for bay in frame_brace_x_bays(spec):
                    pattern = overrides.get(
                        ("X", plane, bay, storey),
                        str(spec.brace_pattern),
                    )
                    if pattern != "None":
                        panels.append(
                            ("X", plane, bay, storey, pattern)
                        )

    if mode in {"Y", "Both"} and not spec.planar_2d:
        for storey in frame_brace_storeys(spec):
            for plane in frame_brace_x_grid_lines(spec):
                for bay in frame_brace_y_bays(spec):
                    pattern = overrides.get(
                        ("Y", plane, bay, storey),
                        str(spec.brace_pattern),
                    )
                    if pattern != "None":
                        panels.append(
                            ("Y", plane, bay, storey, pattern)
                        )

    return tuple(panels)


def frame_brace_panel_count(spec: FrameGridSpec) -> int:
    return len(frame_brace_panels(spec))


def frame_brace_element_count(spec: FrameGridSpec) -> int:
    count = 0
    for _axis, _plane, _bay, _storey, pattern in frame_brace_panels(spec):
        count += 1 if pattern in {
            "DiagonalForward",
            "DiagonalBackward",
        } else 2
    return count


def _frame_point_on_segment(
    point: tuple[float, float, float],
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    *,
    tolerance: float,
) -> bool:
    ab = tuple(float(b[i]) - float(a[i]) for i in range(3))
    ap = tuple(float(point[i]) - float(a[i]) for i in range(3))
    length2 = sum(value * value for value in ab)
    if length2 <= tolerance * tolerance:
        return False
    ratio = sum(ap[i] * ab[i] for i in range(3)) / length2
    if ratio <= tolerance or ratio >= 1.0 - tolerance:
        return False
    closest = tuple(float(a[i]) + ratio * ab[i] for i in range(3))
    return (
        sum(
            (float(point[i]) - closest[i]) ** 2
            for i in range(3)
        )
        <= tolerance * tolerance
    )


def _frame_insert_member_midpoint_node(
    model: StructuralModel,
    point: tuple[float, float, float],
    *,
    groups: set[str],
    tolerance: float,
) -> tuple[int, int]:
    lookup = _frame_coordinate_node_lookup(model, tolerance=tolerance)
    node_tag, _ = _frame_find_or_create_node(
        model,
        lookup,
        point,
        tolerance=tolerance,
    )

    for element in model.elements.values():
        if element.group not in groups:
            continue
        if node_tag in {int(element.i), int(element.j)}:
            return int(node_tag), 0

    target = None
    for element in list(model.elements.values()):
        if element.group not in groups:
            continue
        node_i = model.nodes[int(element.i)]
        node_j = model.nodes[int(element.j)]
        if _frame_point_on_segment(
            point,
            tuple(node_i.xyz),
            tuple(node_j.xyz),
            tolerance=tolerance,
        ):
            target = element
            break
    if target is None:
        raise ValueError(
            "Brace midpoint could not be inserted on a matching frame member."
        )
    if str(target.element_type) != "elasticBeamColumn":
        raise ValueError(
            "Brace midpoint insertion requires elasticBeamColumn frame members."
        )

    old_tag = int(target.tag)
    old_j = int(target.j)
    model.elements.pop(old_tag)
    _frame_clone_member_segment(
        model,
        target,
        old_tag,
        int(target.i),
        int(node_tag),
    )
    new_tag = max(model.elements, default=0) + 1
    _frame_clone_member_segment(
        model,
        target,
        new_tag,
        int(node_tag),
        old_j,
    )
    return int(node_tag), 1


def apply_frame_bracing(
    project,
    spec: FrameGridSpec,
) -> dict[str, int]:
    """Create selected X-Z / Y-Z truss braces with per-panel patterns."""
    validate_frame_grid_spec(spec)
    if str(spec.brace_mode or "None") != "Truss":
        return {
            "brace_panels": 0,
            "brace_elements": 0,
            "brace_midpoint_nodes": 0,
            "brace_member_splits": 0,
            "brace_xz_panels": 0,
            "brace_yz_panels": 0,
        }

    material_tag = int(spec.brace_material_tag)
    if material_tag not in project.materials:
        raise ValueError(
            f"Brace material tag {material_tag} does not exist."
        )

    model = project.model
    x_coordinates, y_coordinates, z_coordinates = frame_grid_coordinates(spec)
    span = max(
        x_coordinates[-1] - x_coordinates[0],
        (y_coordinates[-1] - y_coordinates[0])
        if len(y_coordinates) > 1 else 0.0,
        z_coordinates[-1] - z_coordinates[0],
        1.0,
    )
    tolerance = 1.0e-9 * span
    next_element_tag = max(model.elements, default=0) + 1
    midpoint_nodes: set[int] = set()
    split_count = 0
    brace_count = 0
    xz_panels = 0
    yz_panels = 0

    def add_brace(
        node_i: int,
        node_j: int,
        *,
        axis: str,
        panel_label: str,
    ) -> None:
        nonlocal next_element_tag, brace_count
        while next_element_tag in model.elements:
            next_element_tag += 1
        model.add_element(
            next_element_tag,
            int(node_i),
            int(node_j),
            element_type=str(spec.brace_element_type),
            group=f"brace-{axis.lower()}:{panel_label}",
            truss_area=float(spec.brace_area),
            truss_material_tag=material_tag,
            mass_per_length=float(spec.brace_mass_per_length),
            truss_do_rayleigh=bool(spec.brace_do_rayleigh),
        )
        next_element_tag += 1
        brace_count += 1

    for axis, plane, bay, storey, pattern in frame_brace_panels(spec):
        lower_k = int(storey) - 1
        upper_k = int(storey)

        if axis == "X":
            left = int(bay)
            right = left + 1
            n_bl = _frame_center_node_tag(spec, left, plane, lower_k)
            n_br = _frame_center_node_tag(spec, right, plane, lower_k)
            n_tl = _frame_center_node_tag(spec, left, plane, upper_k)
            n_tr = _frame_center_node_tag(spec, right, plane, upper_k)
            lower_left_xyz = (
                x_coordinates[left],
                y_coordinates[plane],
                z_coordinates[lower_k],
            )
            lower_right_xyz = (
                x_coordinates[right],
                y_coordinates[plane],
                z_coordinates[lower_k],
            )
            upper_left_xyz = (
                x_coordinates[left],
                y_coordinates[plane],
                z_coordinates[upper_k],
            )
            upper_right_xyz = (
                x_coordinates[right],
                y_coordinates[plane],
                z_coordinates[upper_k],
            )
            beam_groups = {"beam-2d", "beam-x"}
            xz_panels += 1
            label = f"S{storey}:X{bay + 1}:Y{plane + 1}"
        else:
            low = int(bay)
            high = low + 1
            n_bl = _frame_center_node_tag(spec, plane, low, lower_k)
            n_br = _frame_center_node_tag(spec, plane, high, lower_k)
            n_tl = _frame_center_node_tag(spec, plane, low, upper_k)
            n_tr = _frame_center_node_tag(spec, plane, high, upper_k)
            lower_left_xyz = (
                x_coordinates[plane],
                y_coordinates[low],
                z_coordinates[lower_k],
            )
            lower_right_xyz = (
                x_coordinates[plane],
                y_coordinates[high],
                z_coordinates[lower_k],
            )
            upper_left_xyz = (
                x_coordinates[plane],
                y_coordinates[low],
                z_coordinates[upper_k],
            )
            upper_right_xyz = (
                x_coordinates[plane],
                y_coordinates[high],
                z_coordinates[upper_k],
            )
            beam_groups = {"beam-y"}
            yz_panels += 1
            label = f"S{storey}:Y{bay + 1}:X{plane + 1}"

        if pattern == "DiagonalForward":
            add_brace(n_bl, n_tr, axis=axis, panel_label=label)
        elif pattern == "DiagonalBackward":
            add_brace(n_br, n_tl, axis=axis, panel_label=label)
        elif pattern == "X":
            add_brace(n_bl, n_tr, axis=axis, panel_label=label)
            add_brace(n_br, n_tl, axis=axis, panel_label=label)
        elif pattern in {"VUpper", "VLower"}:
            target_xyz = (
                tuple(
                    0.5 * (
                        upper_left_xyz[index]
                        + upper_right_xyz[index]
                    )
                    for index in range(3)
                )
                if pattern == "VUpper"
                else tuple(
                    0.5 * (
                        lower_left_xyz[index]
                        + lower_right_xyz[index]
                    )
                    for index in range(3)
                )
            )
            mid, split = _frame_insert_member_midpoint_node(
                model,
                target_xyz,
                groups=beam_groups,
                tolerance=tolerance,
            )
            midpoint_nodes.add(mid)
            split_count += split
            if pattern == "VUpper":
                add_brace(n_bl, mid, axis=axis, panel_label=label)
                add_brace(n_br, mid, axis=axis, panel_label=label)
            else:
                add_brace(n_tl, mid, axis=axis, panel_label=label)
                add_brace(n_tr, mid, axis=axis, panel_label=label)
        elif pattern in {"KLeft", "KRight"}:
            side_xyz_a = (
                lower_left_xyz if pattern == "KLeft" else lower_right_xyz
            )
            side_xyz_b = (
                upper_left_xyz if pattern == "KLeft" else upper_right_xyz
            )
            point = tuple(
                0.5 * (
                    float(side_xyz_a[index])
                    + float(side_xyz_b[index])
                )
                for index in range(3)
            )
            mid, split = _frame_insert_member_midpoint_node(
                model,
                point,
                groups={"column-2d", "column"},
                tolerance=tolerance,
            )
            midpoint_nodes.add(mid)
            split_count += split
            if pattern == "KLeft":
                add_brace(mid, n_br, axis=axis, panel_label=label)
                add_brace(mid, n_tr, axis=axis, panel_label=label)
            else:
                add_brace(mid, n_bl, axis=axis, panel_label=label)
                add_brace(mid, n_tl, axis=axis, panel_label=label)

    return {
        "brace_panels": frame_brace_panel_count(spec),
        "brace_elements": brace_count,
        "brace_midpoint_nodes": len(midpoint_nodes),
        "brace_member_splits": split_count,
        "brace_xz_panels": xz_panels,
        "brace_yz_panels": yz_panels,
    }


def frame_load_storeys(spec: FrameGridSpec) -> tuple[int, ...]:
    values = tuple(sorted({int(value) for value in spec.load_storeys}))
    return values if values else tuple(range(1, int(spec.nz) + 1))


def _frame_element_storey(
    model: StructuralModel,
    element,
    z_coordinates: list[float],
    *,
    tolerance: float,
) -> int | None:
    node_i = model.nodes.get(int(element.i))
    node_j = model.nodes.get(int(element.j))
    if node_i is None or node_j is None:
        return None
    zi = float(node_i.xyz[2])
    zj = float(node_j.xyz[2])
    if abs(zi - zj) > tolerance:
        return None
    for storey in range(1, len(z_coordinates)):
        if abs(zi - float(z_coordinates[storey])) <= tolerance:
            return storey
    return None


def _frame_self_weight_targets(model: StructuralModel) -> list:
    groups = {
        "column",
        "column-2d",
        "beam-x",
        "beam-y",
        "beam-2d",
    }
    return [
        element
        for element in model.elements.values()
        if element.group in groups
    ]


def _frame_beam_udl_targets(
    model: StructuralModel,
    spec: FrameGridSpec,
) -> list:
    _x, _y, z_coordinates = frame_grid_coordinates(spec)
    span = max(
        z_coordinates[-1] - z_coordinates[0],
        1.0,
    )
    tolerance = 1.0e-9 * span
    selected_storeys = set(frame_load_storeys(spec))
    scope = str(spec.load_beam_scope or "Both")
    groups: set[str] = set()
    if scope in {"X", "Both"}:
        groups.update({"beam-x", "beam-2d"})
    if not spec.planar_2d and scope in {"Y", "Both"}:
        groups.add("beam-y")

    targets = []
    for element in model.elements.values():
        if element.group not in groups:
            continue
        storey = _frame_element_storey(
            model,
            element,
            z_coordinates,
            tolerance=tolerance,
        )
        if storey in selected_storeys:
            targets.append(element)
    return targets


def _frame_tributary_width(
    coordinates: list[float],
    index: int,
) -> float:
    if len(coordinates) < 2:
        return 0.0
    index = int(index)
    if index <= 0:
        return 0.5 * float(coordinates[1] - coordinates[0])
    if index >= len(coordinates) - 1:
        return 0.5 * float(coordinates[-1] - coordinates[-2])
    return 0.5 * float(
        coordinates[index + 1] - coordinates[index - 1]
    )


def _frame_floor_area_load_targets(
    model: StructuralModel,
    spec: FrameGridSpec,
) -> list[tuple[object, float]]:
    if not bool(spec.load_floor_area) or spec.planar_2d:
        return []

    x_coordinates, y_coordinates, z_coordinates = frame_grid_coordinates(spec)
    scale = max(
        x_coordinates[-1] - x_coordinates[0],
        y_coordinates[-1] - y_coordinates[0],
        z_coordinates[-1] - z_coordinates[0],
        1.0,
    )
    tolerance = 1.0e-9 * scale
    selected_storeys = set(frame_load_storeys(spec))
    direction = str(spec.load_floor_area_direction or "X")
    group = "beam-x" if direction == "X" else "beam-y"
    transverse = y_coordinates if direction == "X" else x_coordinates

    targets: list[tuple[object, float]] = []
    for element in model.elements.values():
        if element.group != group:
            continue
        storey = _frame_element_storey(
            model,
            element,
            z_coordinates,
            tolerance=tolerance,
        )
        if storey not in selected_storeys:
            continue
        node_i = model.nodes.get(int(element.i))
        node_j = model.nodes.get(int(element.j))
        if node_i is None or node_j is None:
            continue
        coordinate = (
            0.5 * (float(node_i.xyz[1]) + float(node_j.xyz[1]))
            if direction == "X"
            else 0.5 * (float(node_i.xyz[0]) + float(node_j.xyz[0]))
        )
        grid_index = min(
            range(len(transverse)),
            key=lambda idx: abs(float(transverse[idx]) - coordinate),
        )
        if abs(float(transverse[grid_index]) - coordinate) > tolerance:
            continue
        width = _frame_tributary_width(transverse, grid_index)
        if width > 0.0:
            targets.append((element, width))
    return targets


def _preflight_frame_self_weight(
    project,
    spec: FrameGridSpec,
    targets: list,
) -> None:
    density_override = float(spec.load_self_weight_density)
    for element in targets:
        if element.section_tag is None:
            raise ValueError(
                f"Automatic self-weight: element {element.tag} has no section."
            )
        section = project.sections.get(int(element.section_tag))
        if section is None:
            raise ValueError(
                f"Automatic self-weight: section {element.section_tag} "
                "does not exist."
            )
        if section.section_type != "Elastic":
            raise ValueError(
                "Automatic self-weight currently requires Elastic frame "
                f"sections; element {element.tag} uses {section.section_type}."
            )
        if element.transf_tag is None or int(element.transf_tag) not in (
            project.transformations
        ):
            raise ValueError(
                f"Automatic self-weight: element {element.tag} needs a valid "
                "geometric transformation."
            )
        if density_override <= 0.0:
            if section.material_tag is None:
                raise ValueError(
                    "Automatic self-weight needs a positive density override "
                    f"or section {section.tag} linked to material density."
                )
            material = project.materials.get(int(section.material_tag))
            if material is None or float(material.density) <= 0.0:
                raise ValueError(
                    "Automatic self-weight needs a positive density override "
                    f"or positive linked material density for section "
                    f"{section.tag}."
                )


def apply_frame_static_loads(
    project,
    spec: FrameGridSpec,
) -> dict[str, int]:
    """Create one static Plain pattern for frame self-weight and beam UDL."""
    validate_frame_grid_spec(spec)
    if str(spec.load_mode or "None") != "Static":
        return {
            "load_patterns": 0,
            "load_pattern_tag": 0,
            "self_weight_loads": 0,
            "beam_udl_loads": 0,
            "floor_area_loads": 0,
        }

    model = project.model
    self_weight_targets = (
        _frame_self_weight_targets(model)
        if bool(spec.load_self_weight)
        else []
    )
    udl_targets = (
        _frame_beam_udl_targets(model, spec)
        if bool(spec.load_beam_udl)
        else []
    )
    floor_area_targets = _frame_floor_area_load_targets(model, spec)
    if self_weight_targets:
        _preflight_frame_self_weight(
            project,
            spec,
            self_weight_targets,
        )

    time_series_tag = max(project.time_series, default=0) + 1
    pattern_tag = max(project.load_patterns, default=0) + 1
    project.add_time_series(
        TimeSeriesData(
            tag=time_series_tag,
            name="Frame Wizard static",
            series_type="Linear",
            factor=1.0,
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            tag=pattern_tag,
            name="Frame Wizard gravity / beam / floor area load",
            pattern_type="Plain",
            time_series_tag=time_series_tag,
        )
    )

    next_load_tag = max(project.element_loads, default=0) + 1
    self_weight_count = 0
    for element in sorted(
        self_weight_targets,
        key=lambda item: int(item.tag),
    ):
        project.add_element_load(
            ElementLoadData(
                tag=next_load_tag,
                name=f"Frame self-weight E{element.tag}",
                pattern_tag=pattern_tag,
                element_tag=int(element.tag),
                load_type="SelfWeight",
                gravity=(0.0, 0.0, -9.81),
                density_override=float(spec.load_self_weight_density),
                coordinate_system="global",
            )
        )
        next_load_tag += 1
        self_weight_count += 1

    udl_count = 0
    wx, wy, wz = (
        float(value) for value in spec.load_beam_udl_vector
    )
    for element in sorted(
        udl_targets,
        key=lambda item: int(item.tag),
    ):
        project.add_element_load(
            ElementLoadData(
                tag=next_load_tag,
                name=f"Frame beam UDL E{element.tag}",
                pattern_tag=pattern_tag,
                element_tag=int(element.tag),
                load_type="Uniform",
                wx=wx,
                wy=wy,
                wz=wz,
                coordinate_system=str(
                    spec.load_beam_udl_coordinate_system
                ).lower(),
            )
        )
        next_load_tag += 1
        udl_count += 1

    floor_area_count = 0
    floor_pressure = float(spec.load_floor_area_pressure)
    for element, tributary_width in sorted(
        floor_area_targets,
        key=lambda item: int(item[0].tag),
    ):
        line_load = floor_pressure * float(tributary_width)
        project.add_element_load(
            ElementLoadData(
                tag=next_load_tag,
                name=f"Frame floor area load E{element.tag}",
                pattern_tag=pattern_tag,
                element_tag=int(element.tag),
                load_type="Uniform",
                wx=0.0,
                wy=0.0,
                wz=-line_load,
                coordinate_system="global",
            )
        )
        next_load_tag += 1
        floor_area_count += 1

    return {
        "load_patterns": 1,
        "load_pattern_tag": int(pattern_tag),
        "self_weight_loads": self_weight_count,
        "beam_udl_loads": udl_count,
        "floor_area_loads": floor_area_count,
    }


def apply_frame_mass_source(
    project,
    spec: FrameGridSpec,
    *,
    static_pattern_tag: int | None = None,
) -> dict[str, int | float]:
    """Create and apply one FEWIZ mass source after frame/load generation."""
    validate_frame_grid_spec(spec)
    if str(spec.mass_source_mode or "None") != "Source":
        return {
            "mass_sources": 0,
            "mass_source_tag": 0,
            "mass_nodes": 0,
            "generated_nodal_mass": 0.0,
        }

    load_factors: dict[int, float] = {}
    if bool(spec.mass_include_static_loads):
        if static_pattern_tag is None or int(static_pattern_tag) <= 0:
            raise ValueError(
                "Frame Wizard mass source expected the generated static load "
                "pattern but no valid pattern tag was produced."
            )
        load_factors[int(static_pattern_tag)] = float(
            spec.mass_static_load_factor
        )

    source_tag = max(project.mass_sources, default=0) + 1
    source = MassSourceData(
        tag=source_tag,
        name="Frame Wizard seismic mass",
        include_self_mass=bool(spec.mass_include_self),
        load_factors=load_factors,
        gravity_axis=int(spec.mass_gravity_axis),
        directions=tuple(
            sorted({int(value) for value in spec.mass_directions})
        ),
    )
    project.add_mass_source(source)
    summary = apply_mass_source(project, source)
    return {
        "mass_sources": 1,
        "mass_source_tag": int(source_tag),
        "mass_nodes": int(summary.active_nodes),
        "generated_nodal_mass": float(summary.total_mass),
    }


def frame_foundation_count(spec: FrameGridSpec) -> int:
    """Return the number of base foundation spring connections requested."""
    if str(spec.foundation_mode or "Direct") != "Springs":
        return 0
    if not bool(spec.create_columns):
        return 0
    if spec.planar_2d:
        return int(spec.nx) + 1
    return (int(spec.nx) + 1) * (int(spec.ny) + 1)


def frame_foundation_profiles(
    spec: FrameGridSpec,
) -> tuple[tuple[int, ...], ...]:
    """Return normalized A/B/C equivalent foundation spring profiles."""
    profiles = tuple(
        tuple(int(tag) for tag in profile)
        for profile in spec.foundation_profile_material_tags
    )
    if profiles:
        return profiles
    return (
        tuple(int(tag) for tag in spec.foundation_material_tags),
    )


def frame_foundation_profile_assignments(
    spec: FrameGridSpec,
) -> tuple[int, ...]:
    """Return one normalized profile index per frame base, row-major in X/Y."""
    count = frame_foundation_count(spec)
    if count <= 0:
        return ()
    if str(spec.foundation_assignment_mode or "Uniform") == "PerBase":
        values = tuple(
            int(value) for value in spec.foundation_base_profile_indices
        )
        if values:
            return values
    return (0,) * count


def apply_frame_foundation_springs(
    project,
    spec: FrameGridSpec,
) -> dict[str, int]:
    """Attach frame bases to fixed ground through assigned spring profiles."""
    validate_frame_grid_spec(spec)
    if str(spec.foundation_mode or "Direct") != "Springs":
        return {
            "foundation_connections": 0,
            "foundation_ground_nodes": 0,
            "foundation_constraints": 0,
            "foundation_profiles_used": 0,
        }

    model = project.model
    if (int(model.ndm), int(model.ndf)) != (3, 6):
        raise ValueError(
            "Foundation springs require the standard 3D/6DOF frame backend."
        )

    profiles = frame_foundation_profiles(spec)
    assignments = frame_foundation_profile_assignments(spec)
    active_dofs = (
        (1, 3, 5)
        if spec.planar_2d
        else (1, 2, 3, 4, 5, 6)
    )

    used_profile_indices = sorted(set(assignments))
    missing = sorted({
        int(tag)
        for profile_index in used_profile_indices
        for dof, tag in enumerate(
            profiles[profile_index],
            start=1,
        )
        if (
            dof in active_dofs
            and int(tag) > 0
            and int(tag) not in project.materials
        )
    })
    if missing:
        raise ValueError(
            "Foundation spring material tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )

    if spec.planar_2d:
        base_nodes = [
            _frame_center_node_tag(spec, i, 0, 0)
            for i in range(int(spec.nx) + 1)
        ]
    else:
        base_nodes = [
            _frame_center_node_tag(spec, i, j, 0)
            for j in range(int(spec.ny) + 1)
            for i in range(int(spec.nx) + 1)
        ]

    next_node_tag = max(model.nodes, default=0) + 1
    next_connection_tag = max(
        max(model.elements, default=0),
        max(project.connections, default=0),
    ) + 1
    next_constraint_tag = max(project.constraints, default=0) + 1
    connection_count = 0
    constraint_count = 0

    for base_index, base_tag in enumerate(base_nodes):
        base = model.nodes.get(int(base_tag))
        if base is None:
            continue

        profile_index = int(assignments[base_index])
        material_tags = profiles[profile_index]
        spring_materials = {
            dof: int(material_tags[dof - 1])
            for dof in active_dofs
            if int(material_tags[dof - 1]) > 0
        }
        profile_label = chr(ord("A") + profile_index)

        if spec.planar_2d:
            model.set_fixity(base_tag, (0, 1, 0, 1, 0, 1))
        else:
            model.set_fixity(base_tag, (0, 0, 0, 0, 0, 0))

        ground_tag = next_node_tag
        next_node_tag += 1
        model.add_node(
            ground_tag,
            float(base.xyz[0]),
            float(base.xyz[1]),
            float(base.xyz[2]),
            ndf=6,
        )
        model.set_fixity(ground_tag, (1, 1, 1, 1, 1, 1))

        rigid_dofs = tuple(
            dof for dof in active_dofs
            if dof not in spring_materials
        )
        generated_constraint_tag = None
        if rigid_dofs:
            constraint = ConstraintData(
                tag=next_constraint_tag,
                name=(
                    f"Foundation rigid transfer {profile_label} N{base_tag}"
                ),
                constraint_type="equalDOF",
                retained_node=ground_tag,
                constrained_nodes=[base_tag],
                dofs=rigid_dofs,
            )
            project.add_constraint(constraint)
            generated_constraint_tag = int(constraint.tag)
            next_constraint_tag += 1
            constraint_count += 1

        connection = ConnectionData(
            tag=next_connection_tag,
            name=(
                f"Foundation spring {profile_label} N{base_tag}"
            ),
            connection_type="zeroLength",
            node_i=ground_tag,
            node_j=base_tag,
            materials_by_dof=dict(spring_materials),
            generated_ground_node=ground_tag,
            generated_constraint_tag=generated_constraint_tag,
            parameters={
                "foundation_profile_index": profile_index,
                "foundation_profile_label": profile_label,
            },
        )
        project.add_connection(connection)
        next_connection_tag += 1
        connection_count += 1

    return {
        "foundation_connections": connection_count,
        "foundation_ground_nodes": connection_count,
        "foundation_constraints": constraint_count,
        "foundation_profiles_used": len(used_profile_indices),
    }


def generate_frame_project(project, spec: FrameGridSpec) -> dict[str, int | float]:
    """Replace model-linked project data with one Frame Wizard model."""
    validate_frame_grid_spec(spec)
    project.clear_model_linked_data()
    joint_model = str(spec.joint_model or "None")
    if joint_model in {
        "Joint2D",
        "BeamColumnJoint",
        "KrawinklerPanelZone",
    }:
        return generate_frame_macro_joint_project(project, spec)

    # Standard/zeroLength modes retain FEWIZ's 3D/6DOF frame backend.
    project.model.ndm = 3
    project.model.ndf = 6
    generate_frame_grid(project.model, spec)

    if joint_model == "ZeroLength":
        result = apply_frame_zero_length_joints(project, spec)
    else:
        result = {
            "joint_nodes": 0,
            "joint_connections": 0,
            "duplicate_nodes": 0,
            "joint_constraints": 0,
            "panel_external_nodes": 0,
        }

    floor_mode = str(spec.diaphragm_mode or "None")
    if floor_mode == "Rigid":
        result.update(apply_frame_rigid_diaphragms(project, spec))
    elif floor_mode == "Shell":
        result.update(apply_frame_shell_slabs(project, spec))

    if str(spec.brace_mode or "None") == "Truss":
        result.update(apply_frame_bracing(project, spec))

    if str(spec.foundation_mode or "Direct") == "Springs":
        result.update(apply_frame_foundation_springs(project, spec))

    static_pattern_tag: int | None = None
    if str(spec.load_mode or "None") == "Static":
        load_result = apply_frame_static_loads(project, spec)
        result.update(load_result)
        tag = int(load_result.get("load_pattern_tag", 0))
        static_pattern_tag = tag if tag > 0 else None

    if str(spec.mass_source_mode or "None") == "Source":
        result.update(
            apply_frame_mass_source(
                project,
                spec,
                static_pattern_tag=static_pattern_tag,
            )
        )
    return result


def material_source_comments(material: MaterialData) -> list[str]:
    """Return compact provenance comments for exported sourced materials."""
    source = material.source if isinstance(material.source, dict) else {}
    if not source:
        return []

    reference = source.get("primary_reference", {})
    if not isinstance(reference, dict):
        reference = {}
    evidence = source.get("parameter_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}

    comments = [
        f"# Source status: {source.get('status', 'unknown')}",
    ]
    title = str(reference.get("title", "")).strip()
    if title:
        comments.append("# Source: " + title)
    doi = str(reference.get("doi", "")).strip()
    if doi:
        comments.append("# DOI: " + doi)
    location = str(evidence.get("location", "")).strip()
    if location:
        comments.append("# Parameter evidence: " + location)
    record_id = str(source.get("record_id", "")).strip()
    if record_id:
        comments.append("# SARE library record: " + record_id)
    response_quantity = str(
        source.get("response_quantity", "")
    ).strip()
    if response_quantity:
        comments.append(
            "# Response quantity: " + response_quantity
        )
    source_units = source.get("source_units", {})
    if isinstance(source_units, dict) and source_units:
        unit_text = ", ".join(
            f"{key}={value}"
            for key, value in source_units.items()
        )
        comments.append("# Published units: " + unit_text)
    return comments


def nd_material_source_comments(
    material: NDMaterialData,
) -> list[str]:
    """Return provenance comments for a sourced nD material."""
    source = material.source if isinstance(material.source, dict) else {}
    if not source:
        return []

    reference = source.get("primary_reference", {})
    if not isinstance(reference, dict):
        reference = {}
    evidence = source.get("parameter_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}

    comments = [
        f"# Source status: {source.get('status', 'unknown')}",
    ]
    title = str(reference.get("title", "")).strip()
    if title:
        comments.append("# Source: " + title)
    url = str(reference.get("url", "")).strip()
    if url:
        comments.append("# Source URL: " + url)
    doi = str(reference.get("doi", "")).strip()
    if doi:
        comments.append("# DOI: " + doi)
    location = str(evidence.get("location", "")).strip()
    if location:
        comments.append("# Parameter evidence: " + location)
    record_id = str(source.get("record_id", "")).strip()
    if record_id:
        comments.append("# SARE nD library record: " + record_id)
    compatibility = source.get("compatibility", [])
    if isinstance(compatibility, (list, tuple)) and compatibility:
        comments.append(
            "# Compatible formulations: "
            + ", ".join(str(value) for value in compatibility)
        )
    verification = source.get("verification", {})
    if not isinstance(verification, dict):
        verification = {}
    parameter_status = str(
        verification.get("parameter_status", "")
    ).strip()
    if parameter_status:
        comments.append("# Parameter status: " + parameter_status)
    checked_on = str(verification.get("checked_on", "")).strip()
    if checked_on:
        comments.append("# Source verified on: " + checked_on)
    return comments


def material_to_openseespy(
    material: MaterialData,
    units: dict[str, str] | None = None,
) -> str:
    p = material.parameters
    unit_system = UnitSystem.from_mapping(units)
    stress = unit_system.stress_from_pa

    if material.material_type == "Elastic":
        source = material.source if isinstance(material.source, dict) else {}
        dimensions = source.get("parameter_dimensions", {})
        stiffness_parameter = (
            isinstance(dimensions, dict)
            and str(dimensions.get("E", "")).strip().lower()
            in {"stiffness", "force_per_length", "force/length"}
        )
        if stiffness_parameter:
            # OpenSees MVLEM/MVLEM_3D feed the shear material a relative
            # displacement and read its stress as a force. Its tangent is
            # therefore F/L, not material stress F/L^2.
            elastic_e = (
                float(p["E"])
                * unit_system.length_to_m
                / unit_system.force_to_n
            )
        else:
            elastic_e = stress(p["E"])
        return (
            "ops.uniaxialMaterial('Elastic', "
            f"{material.tag}, {elastic_e:g})"
        )

    if material.material_type == "Steel01":
        return (
            "ops.uniaxialMaterial('Steel01', "
            f"{material.tag}, {stress(p['Fy']):g}, {stress(p['E0']):g}, "
            f"{p['b']:g}, {p['a1']:g}, {p['a2']:g}, {p['a3']:g}, {p['a4']:g})"
        )

    if material.material_type == "Steel02":
        return (
            "ops.uniaxialMaterial('Steel02', "
            f"{material.tag}, {stress(p['Fy']):g}, {stress(p['E0']):g}, "
            f"{p['b']:g}, {p['R0']:g}, {p['cR1']:g}, {p['cR2']:g}, "
            f"{p['a1']:g}, {p['a2']:g}, {p['a3']:g}, {p['a4']:g})"
        )

    if material.material_type == "Hardening":
        return (
            "ops.uniaxialMaterial('Hardening', "
            f"{material.tag}, {stress(p['E']):g}, "
            f"{stress(p['sigmaY']):g}, {stress(p['H_iso']):g}, "
            f"{stress(p['H_kin']):g}, {stress(p['eta']):g})"
        )

    if material.material_type == "ElasticPP":
        return (
            "ops.uniaxialMaterial('ElasticPP', "
            f"{material.tag}, {stress(p['E']):g}, "
            f"{p['epsyP']:g}, {p['epsyN']:g}, {p['eps0']:g})"
        )

    if material.material_type == "ElasticBilin":
        return (
            "ops.uniaxialMaterial('ElasticBilin', "
            f"{material.tag}, {stress(p['EP1']):g}, "
            f"{stress(p['EP2']):g}, {p['epsP2']:g}, "
            f"{stress(p['EN1']):g}, {stress(p['EN2']):g}, "
            f"{p['epsN2']:g})"
        )

    if material.material_type == "ReinforcingSteel":
        return (
            "ops.uniaxialMaterial('ReinforcingSteel', "
            f"{material.tag}, {stress(p['fy']):g}, {stress(p['fu']):g}, "
            f"{stress(p['Es']):g}, {stress(p['Esh']):g}, "
            f"{p['eps_sh']:g}, {p['eps_ult']:g})"
        )

    if material.material_type == "Concrete01":
        return (
            "ops.uniaxialMaterial('Concrete01', "
            f"{material.tag}, {stress(p['fpc']):g}, {p['epsc0']:g}, "
            f"{stress(p['fpcu']):g}, {p['epsU']:g})"
        )

    if material.material_type == "Concrete02":
        return (
            "ops.uniaxialMaterial('Concrete02', "
            f"{material.tag}, {stress(p['fpc']):g}, {p['epsc0']:g}, "
            f"{stress(p['fpcu']):g}, {p['epsU']:g}, {p['lambda']:g}, "
            f"{stress(p['ft']):g}, {stress(p['Ets']):g})"
        )

    if material.material_type == "Concrete04":
        return (
            "ops.uniaxialMaterial('Concrete04', "
            f"{material.tag}, {stress(p['fc']):g}, {p['epsc']:g}, "
            f"{p['epscu']:g}, {stress(p['Ec']):g}, {stress(p['fct']):g}, "
            f"{p['et']:g}, {p['beta']:g})"
        )

    if material.material_type == "ConcreteCM":
        return (
            "ops.uniaxialMaterial('ConcreteCM', "
            f"{material.tag}, {stress(p['fpcc']):g}, {p['epcc']:g}, "
            f"{stress(p['Ec']):g}, {p['rc']:g}, {p['xcrn']:g}, "
            f"{stress(p['ft']):g}, {p['et']:g}, {p['rt']:g}, "
            f"{p['xcrp']:g}, '-GapClose', "
            f"{int(round(p['GapClose']))})"
        )

    if material.material_type == "Masonry":
        return (
            "ops.uniaxialMaterial('Masonry', "
            f"{material.tag}, {stress(p['Fm']):g}, {stress(p['Ft']):g}, "
            f"{p['Um']:g}, {p['Uult']:g}, {p['Ucl']:g}, "
            f"{stress(p['Emo']):g}, {p['L']:g}, {p['A1']:g}, "
            f"{p['A2']:g}, {p['D1']:g}, {p['D2']:g}, "
            f"{p['Ach']:g}, {p['Are']:g}, {p['Ba']:g}, "
            f"{p['Bch']:g}, {p['Gun']:g}, {p['Gplu']:g}, "
            f"{p['Gplr']:g}, {p['Exp1']:g}, {p['Exp2']:g}, "
            f"{int(round(p['IENV']))})"
        )

    if material.material_type == "Hysteretic":
        keys = MATERIAL_PARAMETER_ORDER["Hysteretic"]

        def hysteretic_value(key: str) -> float:
            value = float(p[key])
            kind = material_parameter_kind(material, key)
            if kind == "force":
                return unit_system.force_from_n(value)
            if kind == "moment":
                return unit_system.moment_from_nm(value)
            if kind == "stress":
                return unit_system.stress_from_pa(value)
            if kind == "length":
                return unit_system.length_from_m(value)
            return value

        args = ", ".join(
            f"{hysteretic_value(key):g}"
            for key in keys
        )
        return (
            f"ops.uniaxialMaterial('Hysteretic', {material.tag}, {args})"
        )

    if material.material_type == "RambergOsgoodSteel":
        raise ValueError(
            "RambergOsgoodSteel is reference-only in SARE. Stock "
            "OpenSeesPy 3.8.x reports this material as temporarily removed "
            "from compiled Tcl/Py builds because of known issues and "
            "unreliable results."
        )

    if material.material_type == "HystereticSmooth":
        return (
            "ops.uniaxialMaterial('HystereticSmooth', "
            f"{material.tag}, {p['ka']:g}, {p['kb']:g}, "
            f"{p['fbar']:g}, {p['beta']:g})"
        )

    if material.material_type == "Pinching4":
        keys = MATERIAL_PARAMETER_ORDER["Pinching4"][:-1]

        def pinching_value(key: str) -> float:
            value = float(p[key])
            kind = material_parameter_kind(material, key)
            if kind == "force":
                return unit_system.force_from_n(value)
            if kind == "moment":
                return unit_system.moment_from_nm(value)
            if kind == "stress":
                return unit_system.stress_from_pa(value)
            if kind == "length":
                return unit_system.length_from_m(value)
            return value

        args = ", ".join(
            f"{pinching_value(key):g}"
            for key in keys
        )
        dmg_type = "cycle" if p["dmgType"] < 0.5 else "energy"
        return (
            f"ops.uniaxialMaterial('Pinching4', {material.tag}, "
            f"{args}, {dmg_type!r})"
        )

    if material.material_type == "Bond_SP01":
        sy = unit_system.length_from_m(p["Sy"])
        su = unit_system.length_from_m(p["Su"])
        return (
            "ops.uniaxialMaterial('Bond_SP01', "
            f"{material.tag}, {stress(p['Fy']):g}, {sy:g}, "
            f"{stress(p['Fu']):g}, {su:g}, {p['b']:g}, {p['R']:g})"
        )

    if material.material_type == "ElasticPPGap":
        damage = "damage" if p["damage"] >= 0.5 else "noDamage"
        return (
            "ops.uniaxialMaterial('ElasticPPGap', "
            f"{material.tag}, {p['E']:g}, {p['Fy']:g}, {p['gap']:g}, "
            f"{p['eta']:g}, {damage!r})"
        )

    if material.material_type == "FRPConfinedConcrete":
        if not (
            unit_system.length == "mm"
            and unit_system.force == "N"
        ):
            raise ValueError(
                "FRPConfinedConcrete is unit-sensitive and requires "
                "project units mm - N - s (stress in MPa), matching the "
                "OpenSees material documentation."
            )
        length = unit_system.length_from_m
        return (
            "ops.uniaxialMaterial('FRPConfinedConcrete', "
            f"{material.tag}, "
            f"{stress(p['fpc1']):g}, {stress(p['fpc2']):g}, "
            f"{p['epsc0']:g}, {length(p['D']):g}, {length(p['c']):g}, "
            f"{stress(p['Ej']):g}, {length(p['Sj']):g}, "
            f"{length(p['tj']):g}, {p['eju']:g}, {length(p['S']):g}, "
            f"{stress(p['fyl']):g}, {stress(p['fyh']):g}, "
            f"{length(p['dlong']):g}, {length(p['dtrans']):g}, "
            f"{stress(p['Es']):g}, {p['nu0']:g}, {p['k']:g}, "
            f"{p['useBuck']:g})"
        )

    if material.material_type == "FRPConfinedConcrete02":
        if not (
            unit_system.length == "mm"
            and unit_system.force == "N"
        ):
            raise ValueError(
                "FRPConfinedConcrete02 is unit-sensitive and Studio "
                "currently supports it only with project units mm - N - s "
                "(stress in MPa), matching the OpenSees SI metric convention."
            )
        tfrp = unit_system.length_from_m(p["tfrp"])
        radius = unit_system.length_from_m(p["R"])
        common = (
            f"ops.uniaxialMaterial('FRPConfinedConcrete02', {material.tag}, "
            f"{stress(p['fc0']):g}, {stress(p['Ec']):g}, {p['ec0']:g}, "
        )
        if p["mode"] < 0.5:
            return (
                common
                + f"'-JacketC', {tfrp:g}, {stress(p['Efrp']):g}, "
                + f"{p['erup']:g}, {radius:g}, {stress(p['ft']):g}, "
                + f"{stress(p['Ets']):g}, 1)"
            )
        return (
            common
            + f"'-Ultimate', {stress(p['fcu']):g}, {p['ecu']:g}, "
            + f"{stress(p['ft']):g}, {stress(p['Ets']):g}, 1)"
        )

    if material.material_type == "MinMax":
        return (
            "ops.uniaxialMaterial('MinMax', "
            f"{material.tag}, {material.base_material_tag}, "
            f"'-min', {p['min']:g}, '-max', {p['max']:g})"
        )

    if material.material_type == "Fatigue":
        return (
            "ops.uniaxialMaterial('Fatigue', "
            f"{material.tag}, {material.base_material_tag}, "
            f"'-E0', {p['E0']:g}, '-m', {p['m']:g}, "
            f"'-min', {p['min']:g}, '-max', {p['max']:g})"
        )

    if material.material_type == "Parallel":
        tags = ", ".join(str(tag) for tag in material.material_tags)
        factors = ", ".join(f"{value:g}" for value in material.factors)
        return (
            f"ops.uniaxialMaterial('Parallel', {material.tag}, {tags}, "
            f"'-factors', {factors})"
        )

    if material.material_type == "Series":
        tags = ", ".join(str(tag) for tag in material.material_tags)
        return f"ops.uniaxialMaterial('Series', {material.tag}, {tags})"

    raise ValueError(f"Unsupported material type: {material.material_type}")


def ordered_material_tags(
    materials: dict[int, MaterialData],
) -> list[int]:
    """Topologically order material wrappers after their dependencies."""
    graph: dict[int, list[int]] = {}
    for tag, material in materials.items():
        if material.material_type in {"MinMax", "Fatigue"}:
            deps = (
                []
                if material.base_material_tag is None
                else [material.base_material_tag]
            )
        elif material.material_type in {"Parallel", "Series"}:
            deps = list(material.material_tags)
        else:
            deps = []
        missing = [dependency for dependency in deps if dependency not in materials]
        if missing:
            raise ValueError(
                f"Material {tag} references missing material tag(s): "
                + ", ".join(map(str, missing))
            )
        graph[int(tag)] = deps

    ordered: list[int] = []
    temporary: set[int] = set()
    permanent: set[int] = set()

    def visit(tag: int) -> None:
        if tag in permanent:
            return
        if tag in temporary:
            raise ValueError(
                "Material wrapper references contain a dependency cycle."
            )
        temporary.add(tag)
        for dependency in graph[tag]:
            visit(dependency)
        temporary.remove(tag)
        permanent.add(tag)
        ordered.append(tag)

    for tag in sorted(graph):
        visit(tag)
    return ordered


def nd_material_to_openseespy(
    material: NDMaterialData,
    units: dict[str, str] | None = None,
) -> str:
    unit_system = UnitSystem.from_mapping(units)
    p = material.parameters

    def value(key: str) -> float:
        raw = float(p[key])
        kind = nd_material_parameter_kind(
            material.material_type,
            key,
        )
        if kind == "stress":
            return unit_system.stress_from_pa(raw)
        if kind == "density":
            return unit_system.density_from_kg_per_m3(raw)
        return raw

    if material.material_type == "ElasticIsotropic":
        return (
            "ops.nDMaterial('ElasticIsotropic', "
            f"{material.tag}, {value('E'):g}, {value('nu'):g}, "
            f"{value('rho'):g})"
        )

    if material.material_type == "ElasticOrthotropic":
        keys = (
            "Ex", "Ey", "Ez",
            "nu_xy", "nu_yz", "nu_zx",
            "Gxy", "Gyz", "Gzx",
            "rho",
        )
        args = ", ".join(f"{value(key):g}" for key in keys)
        return (
            "ops.nDMaterial('ElasticOrthotropic', "
            f"{material.tag}, {args})"
        )

    if material.material_type == "J2Plasticity":
        keys = ("K", "G", "sig0", "sigInf", "delta", "H")
        args = ", ".join(f"{value(key):g}" for key in keys)
        return (
            "ops.nDMaterial('J2Plasticity', "
            f"{material.tag}, {args})"
        )

    if material.material_type == "DruckerPrager":
        keys = (
            "K", "G", "sigmaY", "rho", "rhoBar",
            "Kinf", "Ko", "delta1", "delta2", "H",
            "theta", "density", "atmPressure",
        )
        args = ", ".join(f"{value(key):g}" for key in keys)
        return (
            "ops.nDMaterial('DruckerPrager', "
            f"{material.tag}, {args})"
        )

    if material.material_type == "PressureIndependMultiYield":
        keys = (
            "nd", "rho", "refShearModul", "refBulkModul",
            "cohesi", "peakShearStra", "frictionAng", "refPress",
            "pressDependCoe", "noYieldSurf",
        )
        rendered: list[str] = []
        for key in keys:
            number = value(key)
            if key in {"nd", "noYieldSurf"}:
                rendered.append(str(int(round(number))))
            else:
                rendered.append(f"{number:g}")
        return (
            "ops.nDMaterial('PressureIndependMultiYield', "
            f"{material.tag}, {', '.join(rendered)})"
        )

    if material.material_type == "PressureDependMultiYield":
        keys = (
            "nd", "rho", "refShearModul", "refBulkModul",
            "frictionAng", "peakShearStra", "refPress",
            "pressDependCoe", "PTAng", "contrac", "dilat1", "dilat2",
            "liquefac1", "liquefac2", "liquefac3", "noYieldSurf",
            "e", "cs1", "cs2", "cs3", "pa", "c",
        )
        rendered: list[str] = []
        for key in keys:
            number = value(key)
            if key in {"nd", "noYieldSurf"}:
                rendered.append(str(int(round(number))))
            else:
                rendered.append(f"{number:g}")
        return (
            "ops.nDMaterial('PressureDependMultiYield', "
            f"{material.tag}, {', '.join(rendered)})"
        )

    if material.material_type == "ASDConcrete3D":
        args = [
            "'ASDConcrete3D'",
            str(material.tag),
            f"{value('E'):g}",
            f"{value('nu'):g}",
            "'-rho'",
            f"{value('rho'):g}",
            "'-fc'",
            f"{value('fc'):g}",
            "'-ft'",
            f"{value('ft'):g}",
        ]
        if value("implex") >= 0.5:
            args.append("'-implex'")
        args.extend([
            "'-Kc'",
            f"{value('Kc'):g}",
            "'-cdf'",
            f"{value('cdf'):g}",
        ])
        return "ops.nDMaterial(" + ", ".join(args) + ")"

    if material.material_type == "OrthotropicRAConcrete":
        return (
            "ops.nDMaterial('OrthotropicRAConcrete', "
            f"{material.tag}, {int(round(value('conc')))}, "
            f"{value('ecr'):g}, {value('ec'):g}, {value('rho'):g}, "
            "'-damageCte1', "
            f"{value('DamageCte1'):g}, '-damageCte2', "
            f"{value('DamageCte2'):g})"
        )

    if material.material_type == "SmearedSteelDoubleLayer":
        return (
            "ops.nDMaterial('SmearedSteelDoubleLayer', "
            f"{material.tag}, {int(round(value('mat1')))}, "
            f"{int(round(value('mat2')))}, {value('ratio1'):g}, "
            f"{value('ratio2'):g}, {value('orientation'):g})"
        )

    if material.material_type == "FSAM":
        return (
            "ops.nDMaterial('FSAM', "
            f"{material.tag}, {value('rho'):g}, "
            f"{int(round(value('sX')))}, {int(round(value('sY')))}, "
            f"{int(round(value('conc')))}, {value('rouX'):g}, "
            f"{value('rouY'):g}, {value('nu'):g}, "
            f"{value('alfadow'):g})"
        )

    if material.material_type in {
        "ContactMaterial2D",
        "ContactMaterial3D",
    }:
        return (
            f"ops.nDMaterial('{material.material_type}', "
            f"{material.tag}, {value('mu'):g}, {value('G'):g}, "
            f"{value('c'):g}, {value('t'):g})"
        )

    raise ValueError(
        f"Unsupported nDMaterial type: {material.material_type}"
    )


def elastic_section_parameters_in_model_units(
    section: SectionData,
    materials: dict[int, MaterialData] | None = None,
    units: dict[str, str] | None = None,
) -> dict[str, float]:
    p = section.resolved_elastic_parameters(materials)
    result = dict(p)
    unit_system = UnitSystem.from_mapping(units)
    result["E"] = unit_system.stress_from_pa(p["E"])
    result["G"] = unit_system.stress_from_pa(p["G"])
    return result

def fiber_component_to_openseespy(
    component: FiberComponentData,
) -> list[str]:
    p = component.parameters
    mat = component.material_tag
    lines = [f"# {component.name}"]

    if component.component_type == "RectPatch":
        y0 = p["y_center"] - 0.5 * p["width_y"]
        y1 = p["y_center"] + 0.5 * p["width_y"]
        z0 = p["z_center"] - 0.5 * p["depth_z"]
        z1 = p["z_center"] + 0.5 * p["depth_z"]
        lines.append(
            "ops.patch('rect', "
            f"{mat}, {int(p['n_y'])}, {int(p['n_z'])}, "
            f"{y0:g}, {z0:g}, {y1:g}, {z1:g})"
        )
        return lines

    if component.component_type == "CircPatch":
        lines.append(
            "ops.patch('circ', "
            f"{mat}, {int(p['n_circum'])}, {int(p['n_radial'])}, "
            f"{p['y_center']:g}, {p['z_center']:g}, "
            f"{p['r_inner']:g}, {p['r_outer']:g}, "
            f"{p['start_angle']:g}, {p['end_angle']:g})"
        )
        return lines

    if component.component_type == "StraightLayer":
        lines.append(
            "ops.layer('straight', "
            f"{mat}, {int(p['n_bars'])}, {p['bar_area']:g}, "
            f"{p['y_i']:g}, {p['z_i']:g}, "
            f"{p['y_j']:g}, {p['z_j']:g})"
        )
        return lines

    if component.component_type == "CircLayer":
        count = int(p["n_bars"])
        span = p["end_angle"] - p["start_angle"]
        base = (
            "ops.layer('circ', "
            f"{mat}, {count}, {p['bar_area']:g}, "
            f"{p['y_center']:g}, {p['z_center']:g}, "
            f"{p['radius']:g}"
        )
        if abs(span - 360.0) <= 1.0e-9:
            # OpenSeesPy's omitted-angle form creates a full ring without
            # duplicating the first bar at the final angle.
            lines.append(base + ")")
        else:
            lines.append(
                base
                + f", {p['start_angle']:g}, {p['end_angle']:g})"
            )
        return lines

    if component.component_type == "SingleFiber":
        lines.append(
            "ops.fiber("
            f"{p['y']:g}, {p['z']:g}, {p['area']:g}, {mat})"
        )
        return lines

    raise ValueError(
        f"Unsupported fiber component type: {component.component_type}"
    )


def section_to_openseespy(
    section: SectionData,
    materials: dict[int, MaterialData] | None = None,
    units: dict[str, str] | None = None,
    ndm: int = 3,
    nd_materials: dict[int, NDMaterialData] | None = None,
) -> list[str]:
    p = (
        elastic_section_parameters_in_model_units(
            section,
            materials,
            units,
        )
        if section.section_type == "Elastic"
        else section.parameters
    )
    if section.section_type == "Elastic":
        if int(ndm) == 2:
            return [
                "ops.section('Elastic', "
                f"{section.tag}, {p['E']:g}, {p['A']:g}, "
                f"{p['Iz']:g})"
            ]
        return [
            "ops.section('Elastic', "
            f"{section.tag}, {p['E']:g}, {p['A']:g}, "
            f"{p['Iz']:g}, {p['Iy']:g}, {p['G']:g}, {p['J']:g})"
        ]

    if section.section_type == "FiberInt":
        n1 = int(round(p["nStrip1"]))
        n2 = int(round(p["nStrip2"]))
        n3 = int(round(p["nStrip3"]))
        lines = [
            "ops.section('FiberInt', "
            f"{section.tag}, '-NStrip', "
            f"{n1}, {p['thick1']:g}, "
            f"{n2}, {p['thick2']:g}, "
            f"{n3}, {p['thick3']:g})"
        ]
        for fiber in section.fibers:
            lines.append(
                "ops.fiber("
                f"{fiber.y:g}, {fiber.z:g}, {fiber.area:g}, "
                f"{fiber.material_tag})"
            )
        for fiber in section.horizontal_fibers:
            lines.append(
                "ops.Hfiber("
                f"{fiber.y:g}, {fiber.z:g}, {fiber.area:g}, "
                f"{fiber.material_tag})"
            )
        return lines

    if section.section_type == "Fiber":
        lines = [
            f"ops.section('Fiber', {section.tag}, '-GJ', {p['GJ']:g})"
        ]

        # Keep manually entered fibers explicit. Builder primitives remain
        # native OpenSees patch/layer commands instead of being flattened.
        if section.fibers:
            for fiber in section.fibers:
                lines.append(
                    "ops.fiber("
                    f"{fiber.y:g}, {fiber.z:g}, {fiber.area:g}, "
                    f"{fiber.material_tag})"
                )

        for component in section.fiber_components:
            lines.extend(fiber_component_to_openseespy(component))
        return lines

    if section.section_type == "ElasticMembranePlate":
        unit_system = UnitSystem.from_mapping(units)
        elastic_modulus = unit_system.stress_from_pa(
            float(p["E"])
        )
        return [
            "ops.section('ElasticMembranePlateSection', "
            f"{section.tag}, {elastic_modulus:g}, {p['nu']:g}, "
            f"{p['h']:g}, {p['rho']:g}, {p['EpModifier']:g})"
        ]

    if section.section_type == "PlateFiber":
        if (
            section.nd_material_tag is None
            or nd_materials is None
            or section.nd_material_tag not in nd_materials
        ):
            raise ValueError(
                f"PlateFiber section {section.tag} references missing "
                f"nDMaterial {section.nd_material_tag}."
            )
        return [
            "ops.section('PlateFiber', "
            f"{section.tag}, {section.nd_material_tag}, {p['h']:g})"
        ]

    if section.section_type == "LayeredShell":
        if not section.shell_layers:
            raise ValueError(
                f"LayeredShell section {section.tag} has no layers."
            )
        missing = sorted({
            int(layer.material_tag)
            for layer in section.shell_layers
            if (
                nd_materials is None
                or int(layer.material_tag) not in nd_materials
            )
        })
        if missing:
            raise ValueError(
                f"LayeredShell section {section.tag} references missing "
                "nDMaterial tag(s): "
                + ", ".join(map(str, missing))
            )
        layer_args = ", ".join(
            f"{int(layer.material_tag)}, {float(layer.thickness):g}"
            for layer in section.shell_layers
        )
        return [
            "ops.section('LayeredShell', "
            f"{section.tag}, {len(section.shell_layers)}, {layer_args})"
        ]

    if section.section_type == "RCLMS":
        if section.nd_material_tag is None or not section.shell_layers:
            raise ValueError(
                f"RCLMS section {section.tag} needs steel and concrete layers."
            )
        tags = section.shell_nd_material_tags()
        missing = sorted(
            tag
            for tag in tags
            if nd_materials is None or tag not in nd_materials
        )
        if missing:
            raise ValueError(
                f"RCLMS section {section.tag} references missing nDMaterial "
                "tag(s): " + ", ".join(map(str, missing))
            )
        steel = nd_materials[int(section.nd_material_tag)]
        if steel.material_type != "SmearedSteelDoubleLayer":
            raise ValueError(
                f"RCLMS section {section.tag} reinforcing layer must use "
                "SmearedSteelDoubleLayer."
            )
        concrete_tags = [
            int(layer.material_tag) for layer in section.shell_layers
        ]
        if any(
            nd_materials[tag].material_type != "OrthotropicRAConcrete"
            for tag in concrete_tags
        ):
            raise ValueError(
                f"RCLMS section {section.tag} concrete layers must use "
                "OrthotropicRAConcrete."
            )
        concrete_thicknesses = [
            float(layer.thickness) for layer in section.shell_layers
        ]
        conc = ", ".join(str(tag) for tag in concrete_tags)
        thick = ", ".join(f"{value:g}" for value in concrete_thicknesses)
        return [
            "ops.section('RCLMS', "
            f"{section.tag}, 1, {len(concrete_tags)}, "
            f"'-reinfSteel', {section.nd_material_tag}, "
            f"'-conc', {conc}, '-concThick', {thick})"
        ]

    raise ValueError(f"Unsupported section type: {section.section_type}")

def constraint_to_openseespy(
    constraint: ConstraintData,
) -> list[str]:
    lines = [f"# Constraint {constraint.tag}: {constraint.name}"]

    if constraint.constraint_type == "equalDOF":
        dofs = ", ".join(str(dof) for dof in constraint.dofs)
        for constrained in constraint.constrained_nodes:
            lines.append(
                f"ops.equalDOF({constraint.retained_node}, "
                f"{constrained}, {dofs})"
            )
        return lines

    if constraint.constraint_type == "rigidLink":
        for constrained in constraint.constrained_nodes:
            lines.append(
                f"ops.rigidLink('{constraint.link_type}', "
                f"{constraint.retained_node}, {constrained})"
            )
        return lines

    if constraint.constraint_type == "rigidDiaphragm":
        constrained = ", ".join(
            str(tag) for tag in constraint.constrained_nodes
        )
        lines.append(
            f"ops.rigidDiaphragm({constraint.perp_dirn}, "
            f"{constraint.retained_node}, {constrained})"
        )
        return lines

    raise ValueError(
        f"Unsupported constraint type: {constraint.constraint_type}"
    )


BEAM_COLUMN_JOINT_COMPONENT_RESPONSES: frozenset[str] = frozenset({
    "node1BarSlipL",
    "node1BarSlipR",
    "node1InterfaceShear",
    "node2BarSlipB",
    "node2BarSlipT",
    "node2InterfaceShear",
    "node3BarSlipL",
    "node3BarSlipR",
    "node3InterfaceShear",
    "node4BarSlipB",
    "node4BarSlipT",
    "node4InterfaceShear",
    "shearPanel",
})


CONNECTION_HISTORY_RESPONSES: dict[str, tuple[str, ...]] = {
    "semiRigid": ("force", "deformation"),
    "zeroLength": ("force", "deformation"),
    "CoupledZeroLength": ("force",),
    "zeroLengthSection": ("force", "deformation", "stiff"),
    "twoNodeLink": (
        "force",
        "localForce",
        "basicForce",
        "localDisplacement",
        "basicDisplacement",
    ),
    "Joint2D": (
        "force",
        "deformation",
        "centralNode",
        "size",
        "stiffness",
        "defoANDforce",
    ),
    "BeamColumnJoint": (
        "deformation",
        "shearPanel",
        "node1BarSlipL",
        "node1BarSlipR",
        "node1InterfaceShear",
        "node2BarSlipB",
        "node2BarSlipT",
        "node2InterfaceShear",
        "node3BarSlipL",
        "node3BarSlipR",
        "node3InterfaceShear",
        "node4BarSlipB",
        "node4BarSlipT",
        "node4InterfaceShear",
        "internalDisplacement",
        "externalDisplacement",
    ),
    # Source-verified LehighJoint2d::setResponse aliases.
    "LehighJoint2D": (
        "globalForce",
        "localForce",
        "basicForces",
        "Deformation",
    ),
    "KrawinklerPanelZone": ("force", "deformation"),
}


def connection_to_openseespy(
    connection: ConnectionData,
    *,
    ndm: int = 3,
    ndf: int = 6,
    reserved_element_tag_max: int = 0,
    reserved_node_tag_max: int = 0,
) -> str:
    """Generate OpenSeesPy for one SARE connection/joint object."""
    ox = ", ".join(f"{value:g}" for value in connection.orient_x)
    oy = ", ".join(f"{value:g}" for value in connection.orient_y)
    connection_type = connection.connection_type

    if connection_type == "rigid":
        return (
            "ops.rigidLink('beam', "
            f"{connection.node_i}, {connection.node_j})"
        )

    if connection_type == "pinned":
        translational_dofs = tuple(
            range(1, min(max(int(ndm), 1), int(ndf)) + 1)
        )
        dof_text = ", ".join(str(dof) for dof in translational_dofs)
        return (
            f"ops.equalDOF({connection.node_i}, {connection.node_j}, "
            f"{dof_text})"
        )

    if connection_type == "zeroLengthSection":
        return (
            "ops.element('zeroLengthSection', "
            f"{connection.tag}, {connection.node_i}, {connection.node_j}, "
            f"{connection.section_tag}, '-orient', {ox}, {oy}, "
            f"'-doRayleigh', {1 if connection.do_rayleigh else 0})"
        )

    if connection_type == "CoupledZeroLength":
        directions = sorted(connection.materials_by_dof)
        material_tag = int(connection.materials_by_dof[directions[0]])
        command = (
            f"ops.element('CoupledZeroLength', {connection.tag}, "
            f"{connection.node_i}, {connection.node_j}, "
            f"{directions[0]}, {directions[1]}, {material_tag}"
        )
        if connection.do_rayleigh:
            command += ", 1"
        return command + ")"

    if connection_type == "twoNodeLink":
        directions = sorted(connection.materials_by_dof)
        materials = [connection.materials_by_dof[dof] for dof in directions]
        args = [
            f"ops.element('twoNodeLink', {connection.tag}, "
            f"{connection.node_i}, {connection.node_j}, '-mat', "
            + ", ".join(str(tag) for tag in materials)
            + ", '-dir', "
            + ", ".join(str(dof) for dof in directions)
        ]
        if bool(connection.parameters.get("orientation_override", True)):
            args.append(f", '-orient', {ox}, {oy}")
        p_delta = [
            float(value)
            for value in connection.parameters.get("p_delta", ())
        ]
        if p_delta:
            args.append(
                ", '-pDelta', "
                + ", ".join(f"{value:g}" for value in p_delta)
            )
        shear_dist = [
            float(value)
            for value in connection.parameters.get("shear_dist", ())
        ]
        if shear_dist:
            args.append(
                ", '-shearDist', "
                + ", ".join(f"{value:g}" for value in shear_dist)
            )
        if connection.do_rayleigh:
            args.append(", '-doRayleigh'")
        link_mass = float(connection.parameters.get("mass", 0.0))
        if link_mass > 0.0:
            args.append(f", '-mass', {link_mass:g}")
        args.append(")")
        return "".join(args)

    if connection_type == "Joint2D":
        nodes = [
            int(tag)
            for tag in connection.parameters["external_nodes"]
        ]
        interface = [
            int(tag)
            for tag in connection.parameters.get(
                "interface_materials",
                (0, 0, 0, 0),
            )
        ]
        panel_material = int(connection.parameters["panel_material"])
        large_disp = int(connection.parameters.get("large_disp", 0))
        center_var = f"_sare_joint2d_center_{connection.tag}"
        imported_center = connection.parameters.get("imported_center_node_tag")
        center_arg = (
            str(int(imported_center))
            if imported_center is not None
            else center_var
        )
        args = ", ".join(str(tag) for tag in nodes)
        command_args = [
            f"ops.element('Joint2D', {connection.tag}, {args}, {center_arg}"
        ]
        if any(interface):
            command_args.append(
                ", " + ", ".join(str(tag) for tag in interface)
            )
        command_args.append(f", {panel_material}, {large_disp})")
        lines = [
            f"# Joint2D connection {connection.tag}: external nodes are "
            "clockwise/counter-clockwise around the joint.",
        ]
        if imported_center is None:
            lines.append(
                (
                f"{center_var} = max((list(ops.getNodeTags()) or [0]) + "
                f"[{int(reserved_node_tag_max)}]) + 1"
            )
            )
        else:
            lines.append(
                f"# Preserved imported Joint2D center-node tag {center_arg}"
            )
        lines.append("".join(command_args))
        return "\n".join(lines)

    if connection_type == "BeamColumnJoint":
        nodes = [
            int(tag)
            for tag in connection.parameters["external_nodes"]
        ]
        materials = [
            int(tag)
            for tag in connection.parameters["component_materials"]
        ]
        height_factor = float(
            connection.parameters.get("height_factor", 1.0)
        )
        width_factor = float(
            connection.parameters.get("width_factor", 1.0)
        )
        node_text = ", ".join(str(tag) for tag in nodes)
        material_text = ", ".join(str(tag) for tag in materials)
        command = (
            f"ops.element('beamColumnJoint', {connection.tag}, "
            f"{node_text}, {material_text}"
        )
        if (
            abs(height_factor - 1.0) > 1.0e-12
            or abs(width_factor - 1.0) > 1.0e-12
        ):
            command += f", {height_factor:g}, {width_factor:g}"
        return command + ")"

    if connection_type == "LehighJoint2D":
        nodes = [
            int(tag)
            for tag in connection.parameters["external_nodes"]
        ]
        materials = [
            int(tag)
            for tag in connection.parameters["mode_materials"]
        ]
        return (
            f"ops.element('LehighJoint2D', {connection.tag}, "
            + ", ".join(str(tag) for tag in nodes + materials)
            + ")"
        )

    if connection_type == "KrawinklerPanelZone":
        nodes = [
            int(tag)
            for tag in connection.parameters["external_nodes"]
        ]
        left, top, right, bottom = nodes
        panel_material = int(connection.parameters["panel_material"])
        rigid_a = float(connection.parameters["rigid_A"])
        rigid_e = float(connection.parameters["rigid_E"])
        rigid_i = float(connection.parameters["rigid_I"])
        p = f"_sare_pz_{connection.tag}"
        rayleigh = 1 if connection.do_rayleigh else 0
        rotation_dof = 6

        # The macro follows the Gupta-Krawinkler topology used by the
        # OpenSees panel-zone example: eight very-stiff elastic frame
        # segments, translational equalDOF constraints at the duplicated
        # corners, and one zeroLength rotational spring. The public SARE
        # connection tag is the spring tag; internal frame tags stay hidden.
        return "\n".join([
            f"# Krawinkler panel-zone macro {connection.tag}",
            f"{p}_left = ops.nodeCoord({left})",
            f"{p}_top = ops.nodeCoord({top})",
            f"{p}_right = ops.nodeCoord({right})",
            f"{p}_bottom = ops.nodeCoord({bottom})",
            f"{p}_xl = float({p}_left[0])",
            f"{p}_xr = float({p}_right[0])",
            f"{p}_yt = float({p}_top[1])",
            f"{p}_yb = float({p}_bottom[1])",
            (
                f"{p}_nbase = max((list(ops.getNodeTags()) or [0]) + "
                f"[{int(reserved_node_tag_max)}]) + 1"
            ),
            f"{p}_tlh, {p}_tlv = {p}_nbase, {p}_nbase + 1",
            f"{p}_trh, {p}_trv = {p}_nbase + 2, {p}_nbase + 3",
            f"{p}_brv, {p}_brh = {p}_nbase + 4, {p}_nbase + 5",
            f"{p}_blh, {p}_blv = {p}_nbase + 6, {p}_nbase + 7",
            f"ops.node({p}_tlh, {p}_xl, {p}_yt)",
            f"ops.node({p}_tlv, {p}_xl, {p}_yt)",
            f"ops.node({p}_trh, {p}_xr, {p}_yt)",
            f"ops.node({p}_trv, {p}_xr, {p}_yt)",
            f"ops.node({p}_brv, {p}_xr, {p}_yb)",
            f"ops.node({p}_brh, {p}_xr, {p}_yb)",
            f"ops.node({p}_blh, {p}_xl, {p}_yb)",
            f"ops.node({p}_blv, {p}_xl, {p}_yb)",
            f"{p}_tr = max(list(ops.getCrdTransfTags()) or [0]) + 1",
            f"ops.geomTransf('Linear', {p}_tr)",
            (
                f"{p}_ebase = max((list(ops.getEleTags()) or [0]) + "
                f"[{max(connection.tag, int(reserved_element_tag_max))}]) + 1"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 0, "
                f"{p}_tlh, {top}, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 1, "
                f"{top}, {p}_trh, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 2, "
                f"{p}_trv, {right}, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 3, "
                f"{right}, {p}_brv, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 4, "
                f"{p}_brh, {bottom}, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 5, "
                f"{bottom}, {p}_blh, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 6, "
                f"{p}_blv, {left}, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            (
                f"ops.element('elasticBeamColumn', {p}_ebase + 7, "
                f"{left}, {p}_tlv, {rigid_a:g}, {rigid_e:g}, "
                f"{rigid_i:g}, {p}_tr)"
            ),
            f"ops.equalDOF({p}_tlh, {p}_tlv, 1, 2)",
            f"ops.equalDOF({p}_trh, {p}_trv, 1, 2)",
            f"ops.equalDOF({p}_brv, {p}_brh, 1, 2)",
            f"ops.equalDOF({p}_blh, {p}_blv, 1, 2)",
            (
                f"ops.element('zeroLength', {connection.tag}, "
                f"{p}_tlh, {p}_tlv, '-mat', {panel_material}, "
                f"'-dir', {rotation_dof}, '-doRayleigh', {rayleigh})"
            ),
        ])

    directions = sorted(connection.materials_by_dof)
    materials = [connection.materials_by_dof[dof] for dof in directions]
    mat_text = ", ".join(str(tag) for tag in materials)
    dir_text = ", ".join(str(dof) for dof in directions)

    element_line = (
        f"ops.element('"
        f"{'zeroLength' if connection_type == 'semiRigid' else connection_type}"
        f"', {connection.tag}, "
        f"{connection.node_i}, {connection.node_j}, "
        f"'-mat', {mat_text}, '-dir', {dir_text}, "
        f"'-orient', {ox}, {oy}, "
        f"'-doRayleigh', {1 if connection.do_rayleigh else 0})"
    )

    if connection_type == "semiRigid":
        # Semi-rigid means only the explicitly spring-backed mechanisms may
        # deform. Every other nodal DOF remains rigidly compatible.
        #
        # zeroLength uses physical direction 6 for RZ in a 2D/3-DOF model,
        # while the corresponding nodal DOF is 3; translate that one special
        # case before constructing equalDOF.
        if int(ndm) == 2 and int(ndf) == 3:
            direction_to_nodal_dof = {1: 1, 2: 2, 6: 3}
        else:
            direction_to_nodal_dof = {
                direction: direction
                for direction in range(1, min(int(ndf), 6) + 1)
            }
        spring_nodal_dofs = {
            direction_to_nodal_dof[direction]
            for direction in directions
            if direction in direction_to_nodal_dof
        }
        tied_dofs = [
            dof
            for dof in range(1, int(ndf) + 1)
            if dof not in spring_nodal_dofs
        ]
        if tied_dofs:
            dof_text = ", ".join(str(dof) for dof in tied_dofs)
            return "\n".join([
                (
                    f"ops.equalDOF({connection.node_i}, "
                    f"{connection.node_j}, {dof_text})"
                ),
                element_line,
            ])

    return element_line


def time_series_to_openseespy(series: TimeSeriesData) -> str:
    if series.series_type in {"Linear", "Constant"}:
        return (
            f"ops.timeSeries('{series.series_type}', {series.tag}, "
            f"'-factor', {series.factor:g})"
        )
    if series.series_type == "Path":
        values = ", ".join(f"{value:g}" for value in series.values)
        return (
            f"ops.timeSeries('Path', {series.tag}, '-dt', {series.dt:g}, "
            f"'-values', {values}, '-factor', {series.factor:g})"
        )
    raise ValueError(f"Unsupported time series type: {series.series_type}")


def load_pattern_to_openseespy(pattern: LoadPatternData) -> str:
    if pattern.pattern_type == "Plain":
        return f"ops.pattern('Plain', {pattern.tag}, {pattern.time_series_tag})"
    if pattern.pattern_type == "UniformExcitation":
        return (
            f"ops.pattern('UniformExcitation', {pattern.tag}, "
            f"{pattern.direction}, '-accel', {pattern.time_series_tag}, "
            f"'-vel0', {pattern.vel0:g}, '-fact', {pattern.factor:g})"
        )
    raise ValueError(f"Unsupported load pattern type: {pattern.pattern_type}")


def nodal_load_to_openseespy(
    load: NodalLoadData,
    ndf: int = 6,
) -> str:
    values = ", ".join(
        f"{value:g}" for value in load.values[:max(int(ndf), 0)]
    )
    return f"ops.load({load.node_tag}, {values})"


def prescribed_displacement_to_openseespy(
    displacement: PrescribedDisplacementData,
) -> str:
    return (
        f"ops.sp({displacement.node_tag}, {displacement.dof}, "
        f"{displacement.value:g})"
    )


def element_load_to_openseespy(
    load: ElementLoadData,
    model: StructuralModel,
    sections: dict[int, SectionData] | None = None,
    materials: dict[int, MaterialData] | None = None,
    transformations: dict[int, TransformationData] | None = None,
    units: dict[str, str] | None = None,
) -> str:
    transformations = transformations or {}
    if load.load_type == "Uniform":
        wx, wy, wz = resolve_element_load_local_components(
            load,
            model,
            transformations,
        )
    elif load.load_type in {"Triangular", "Trapezoidal"}:
        wxa, wya, wza = resolve_element_load_local_components(
            load,
            model,
            transformations,
        )
        wxb, wyb, wzb = resolve_element_load_local_end_components(
            load,
            model,
            transformations,
        )
        if int(model.ndm) == 2:
            return (
                "ops.eleLoad('-ele', "
                f"{load.element_tag}, '-type', '-beamUniform', "
                f"{wya:g}, {wxa:g}, {load.a_over_l:g}, "
                f"{load.b_over_l:g}, {wyb:g}, {wxb:g})"
            )
        return (
            "ops.eleLoad('-ele', "
            f"{load.element_tag}, '-type', '-beamUniform', "
            f"{wya:g}, {wza:g}, {wxa:g}, {load.a_over_l:g}, "
            f"{load.b_over_l:g}, {wyb:g}, {wzb:g}, {wxb:g})"
        )
    elif load.load_type == "Point":
        px, py, pz = resolve_element_load_local_components(
            load,
            model,
            transformations,
        )
        return (
            "ops.eleLoad('-ele', "
            f"{load.element_tag}, '-type', '-beamPoint', "
            f"{py:g}, {pz:g}, {load.x_over_l:g}, {px:g})"
        )
    elif load.load_type == "SelfWeight":
        wx, wy, wz = resolve_self_weight_local(
            load,
            model,
            sections or {},
            materials or {},
            transformations,
            units,
        )
    else:
        raise ValueError(
            f"Unsupported element load type: {load.load_type}"
        )

    return (
        "ops.eleLoad('-ele', "
        f"{load.element_tag}, '-type', '-beamUniform', "
        f"{wy:g}, {wz:g}, {wx:g})"
    )


def load_pattern_block_to_openseespy(
    pattern: LoadPatternData,
    *,
    nodal_loads: list[NodalLoadData] | None = None,
    prescribed_displacements: list[PrescribedDisplacementData] | None = None,
    element_loads: list[ElementLoadData] | None = None,
    model: StructuralModel,
    sections: dict[int, SectionData] | None = None,
    materials: dict[int, MaterialData] | None = None,
    transformations: dict[int, TransformationData] | None = None,
    units: dict[str, str] | None = None,
    surface_pressure_tags: dict[int, int] | None = None,
) -> list[str]:
    lines = [load_pattern_to_openseespy(pattern)]
    if pattern.pattern_type != "Plain":
        return lines

    for load in sorted(nodal_loads or [], key=lambda item: item.tag):
        lines.append(f"# Nodal load {load.tag}: {load.name}")
        lines.append(nodal_load_to_openseespy(load, model.ndf))
    for displacement in sorted(
        prescribed_displacements or [],
        key=lambda item: item.tag,
    ):
        lines.append(
            "# Prescribed displacement "
            f"{displacement.tag}: {displacement.name}"
        )
        lines.append(
            prescribed_displacement_to_openseespy(displacement)
        )
    for load in sorted(element_loads or [], key=lambda item: item.tag):
        lines.append(f"# Element load {load.tag}: {load.name}")
        if load.load_type == "SurfacePressure":
            element = model.elements.get(int(load.element_tag))
            helper_tag = (surface_pressure_tags or {}).get(int(load.tag))
            if (
                element is None
                or element.element_type not in SHELL_ELEMENT_TYPES
                or len(element.node_tags()) != 4
                or helper_tag is None
            ):
                lines.append(
                    f"# ERROR: SurfacePressure load {load.tag} could not "
                    "create its native SurfaceLoad helper."
                )
                continue
            n1, n2, n3, n4 = element.node_tags()
            lines.append(
                "ops.element('SurfaceLoad', "
                f"{helper_tag}, {n1}, {n2}, {n3}, {n4}, "
                f"{load.pressure:g})"
            )
            lines.append(
                "ops.eleLoad('-ele', "
                f"{helper_tag}, '-type', '-surfaceLoad')"
            )
            continue
        lines.append(
            element_load_to_openseespy(
                load,
                model,
                sections,
                materials,
                transformations,
                units,
            )
        )
    return lines


def recorder_to_openseespy(recorder: RecorderData) -> list[str]:
    """Generate one native OpenSees recorder command."""
    path = recorder.file_name
    lines = [
        f"os.makedirs(os.path.dirname({path!r}) or '.', exist_ok=True)"
    ]
    time_args = ", '-time'" if recorder.include_time else ""
    targets = ", ".join(str(tag) for tag in recorder.target_tags)

    if recorder.recorder_type == "Node":
        dofs = ", ".join(str(dof) for dof in recorder.dofs)
        lines.append(
            "ops.recorder('Node', '-file', "
            f"{path!r}{time_args}, '-node', {targets}, "
            f"'-dof', {dofs}, {recorder.response!r})"
        )
        return lines

    prefix = (
        "ops.recorder('Element', '-file', "
        f"{path!r}{time_args}, '-ele', {targets}"
    )
    if recorder.recorder_type == "Element":
        if recorder.response in BEAM_COLUMN_JOINT_COMPONENT_RESPONSES:
            lines.append(
                prefix
                + f", {recorder.response!r}, 'stressStrain')"
            )
        else:
            lines.append(prefix + f", {recorder.response!r})")
        return lines
    if recorder.recorder_type == "Shell":
        lines.append(
            prefix
            + f", 'material', {recorder.section_number}, "
            + f"{recorder.response!r})"
        )
        return lines
    if recorder.recorder_type == "Section":
        lines.append(
            prefix
            + f", 'section', {recorder.section_number}, "
            + f"{recorder.response!r})"
        )
        return lines

    if recorder.fiber_index is not None:
        fiber_args = (
            f", 'section', {recorder.section_number}, 'fiber', "
            f"{recorder.fiber_index}"
        )
    else:
        fiber_args = (
            f", 'section', {recorder.section_number}, 'fiber', "
            f"{recorder.fiber_y:g}, {recorder.fiber_z:g}"
        )
        if recorder.material_tag is not None:
            fiber_args += f", {recorder.material_tag}"
    lines.append(prefix + fiber_args + f", {recorder.response!r})")
    return lines


def cyclic_displacement_steps(
    targets: list[float] | tuple[float, ...],
    max_increment: float,
    *,
    start: float = 0.0,
) -> list[float]:
    """Expand absolute cyclic displacement targets into exact increments."""
    increment = abs(float(max_increment))
    if increment <= 0.0:
        raise ValueError("Cyclic max displacement increment must be positive.")

    current = float(start)
    steps: list[float] = []
    for raw_target in targets:
        target = float(raw_target)
        delta = target - current
        if abs(delta) <= 1.0e-15:
            current = target
            continue
        count = max(1, int(math.ceil(abs(delta) / increment)))
        branch_increment = delta / count
        steps.extend([branch_increment] * count)
        current = target
    return steps



def _vector_unit(
    values: tuple[float, float, float],
) -> tuple[float, float, float]:
    norm = math.sqrt(sum(float(value) ** 2 for value in values))
    if norm <= 1.0e-14:
        raise ValueError("Cannot normalize a zero vector.")
    return tuple(float(value) / norm for value in values)


def _vector_cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vector_dot(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _critical_section_fibers(
    section: SectionData | None,
    materials: dict[int, MaterialData] | None,
    *,
    coordinate: str,
    material_types: set[str],
    label_prefix: str,
) -> list[dict[str, object]]:
    if section is None or section.section_type != "Fiber":
        return []
    if coordinate not in {"y", "z"}:
        raise ValueError("Critical fiber coordinate must be y or z.")

    candidates = []
    for fiber in section.compiled_fibers():
        material = (materials or {}).get(int(fiber.material_tag))
        if material is None or material.material_type not in material_types:
            continue
        candidates.append(fiber)
    if not candidates:
        return []

    key = (
        (lambda fiber: float(fiber.y))
        if coordinate == "y"
        else (lambda fiber: float(fiber.z))
    )
    selected = [
        ("min", min(candidates, key=key)),
        ("max", max(candidates, key=key)),
    ]
    rows: list[dict[str, object]] = []
    seen: set[tuple[float, float, int]] = set()
    for suffix, fiber in selected:
        identity = (
            round(float(fiber.y), 14),
            round(float(fiber.z), 14),
            int(fiber.material_tag),
        )
        if identity in seen:
            continue
        seen.add(identity)
        material = (materials or {}).get(int(fiber.material_tag))
        rows.append({
            "label": f"{label_prefix}_{suffix}",
            "y": float(fiber.y),
            "z": float(fiber.z),
            "area": float(fiber.area),
            "material_tag": int(fiber.material_tag),
            "material_type": (
                material.material_type if material is not None else "Unknown"
            ),
        })
    return rows


def column_response_spec(
    model: StructuralModel,
    *,
    sections: dict[int, SectionData] | None = None,
    materials: dict[int, MaterialData] | None = None,
    transformations: dict[int, TransformationData] | None = None,
    connections: dict[int, ConnectionData] | None = None,
    active_analysis: AnalysisSettingsData | None = None,
) -> dict[str, object] | None:
    """Infer instrumentation for a Quick 1D Column specimen.

    The builder tags its member elements with group="test-column". This
    helper keeps the instrumentation automatic and does not require a second
    user-facing recorder setup.
    """
    members = sorted(
        (
            element
            for element in model.elements.values()
            if element.group == "test-column"
        ),
        key=lambda element: int(element.tag),
    )
    if not members:
        return None

    base_element = members[0]
    top_element = members[-1]
    base_node = int(base_element.i)
    top_node = int(top_element.j)
    base_xyz = model.nodes[base_node].xyz
    top_xyz = model.nodes[top_node].xyz
    member_vector = tuple(
        float(top_xyz[index]) - float(base_xyz[index])
        for index in range(3)
    )
    local_x = _vector_unit(member_vector)
    height = math.sqrt(sum(value * value for value in member_vector))
    axis = max(range(3), key=lambda index: abs(local_x[index])) + 1

    lateral = (
        int(active_analysis.control_dof)
        if active_analysis is not None
        and int(active_analysis.control_dof) in (1, 2, 3)
        else 1
    )
    if lateral == axis:
        lateral = next(direction for direction in (1, 2, 3) if direction != axis)
    global_lateral = tuple(
        1.0 if index == lateral - 1 else 0.0
        for index in range(3)
    )

    transformation = (
        (transformations or {}).get(int(base_element.transf_tag))
        if base_element.transf_tag is not None
        else None
    )
    vecxz = (
        resolve_transformation_vecxz(model, transformation)
        if transformation is not None
        else ((1.0, 0.0, 0.0) if axis == 3 else (0.0, 0.0, 1.0))
    )
    local_y = _vector_unit(_vector_cross(vecxz, local_x))
    local_z = _vector_unit(_vector_cross(local_x, local_y))
    projection_y = _vector_dot(global_lateral, local_y)
    projection_z = _vector_dot(global_lateral, local_z)

    if abs(projection_y) >= abs(projection_z):
        moment_component = "Mz"
        moment_index = 1
        bending_coordinate = "y"
        component_axis = local_z
    else:
        moment_component = "My"
        moment_index = 2
        bending_coordinate = "z"
        component_axis = local_y

    global_bending_axis = _vector_unit(
        _vector_cross(local_x, global_lateral)
    )
    sign_value = _vector_dot(component_axis, global_bending_axis)
    moment_sign = 1.0 if sign_value >= 0.0 else -1.0

    hinge_integrations = {
        "HingeRadau",
        "HingeRadauTwo",
        "HingeMidpoint",
        "HingeEndpoint",
        "ConcentratedPlasticity",
    }
    base_section_tag = (
        base_element.hinge_i_section_tag
        if base_element.integration_type in hinge_integrations
        and base_element.hinge_i_section_tag is not None
        else base_element.section_tag
    )
    base_section = (
        (sections or {}).get(int(base_section_tag))
        if base_section_tag is not None
        else None
    )

    base_fibers = []
    base_fibers.extend(
        _critical_section_fibers(
            base_section,
            materials,
            coordinate=bending_coordinate,
            material_types={
                "Steel01",
                "Steel02",
                "Hardening",
                "ElasticPP",
                "ElasticBilin",
                "ReinforcingSteel",
            },
            label_prefix="steel",
        )
    )
    base_fibers.extend(
        _critical_section_fibers(
            base_section,
            materials,
            coordinate=bending_coordinate,
            material_types={
                "Concrete01",
                "Concrete02",
                "Concrete04",
                "FRPConfinedConcrete02",
            },
            label_prefix="concrete",
        )
    )

    interface = next(
        (
            connection
            for connection in (connections or {}).values()
            if connection.node_j == base_node
            and connection.generated_ground_node is not None
        ),
        None,
    )
    interface_fibers: list[dict[str, object]] = []
    interface_section_tag: int | None = None
    if interface is not None and interface.connection_type == "zeroLengthSection":
        interface_section_tag = interface.section_tag
        interface_section = (
            (sections or {}).get(int(interface_section_tag))
            if interface_section_tag is not None
            else None
        )
        interface_fibers = _critical_section_fibers(
            interface_section,
            materials,
            coordinate=bending_coordinate,
            material_types={"Bond_SP01"},
            label_prefix="bond",
        )

    return {
        "kind": "test-column",
        "element_tag": int(base_element.tag),
        "base_node": base_node,
        "top_node": top_node,
        "height": float(height),
        "axis": int(axis),
        "lateral_direction": int(lateral),
        "bending_rotation_dof": int(
            ({1, 2, 3} - {axis, lateral}).pop() + 3
        ),
        "section_number": 1,
        "base_section_tag": (
            int(base_section_tag) if base_section_tag is not None else None
        ),
        "moment_component": moment_component,
        "moment_index": int(moment_index),
        "moment_sign": float(moment_sign),
        "bending_coordinate": bending_coordinate,
        "base_fibers": base_fibers,
        "interface_tag": (
            int(interface.tag) if interface is not None else None
        ),
        "interface_type": (
            str(interface.connection_type) if interface is not None else "Fixed base"
        ),
        "interface_name": (
            str(interface.name) if interface is not None else "Fixed base"
        ),
        "interface_section_tag": (
            int(interface_section_tag)
            if interface_section_tag is not None
            else None
        ),
        "ground_node": (
            int(interface.generated_ground_node)
            if interface is not None
            and interface.generated_ground_node is not None
            else None
        ),
        "interface_fibers": interface_fibers,
    }


def moment_curvature_response_spec(
    model: StructuralModel,
    *,
    connections: dict[int, ConnectionData] | None = None,
    active_analysis: AnalysisSettingsData | None = None,
) -> dict[str, object] | None:
    """Backward-compatible alias for the generic section-response detector."""
    return automatic_moment_curvature_spec(
        model,
        connections=connections,
        active_analysis=active_analysis,
    )

def _response_spectrum_sources(
    settings: AnalysisSettingsData,
    load_patterns: dict[int, LoadPatternData] | None,
    time_series: dict[int, TimeSeriesData] | None,
) -> list[dict[str, object]]:
    if settings.analysis_type != "Response Spectrum":
        return []
    expected = (
        1
        if settings.response_spectrum_mode == "Single Component"
        else 2
    )
    pattern_tags = list(settings.deferred_pattern_tags)
    if len(pattern_tags) != expected:
        raise ValueError(
            f"Response Spectrum {settings.response_spectrum_mode} needs "
            f"exactly {expected} UniformExcitation pattern tag(s)."
        )
    components: list[dict[str, object]] = []
    for pattern_tag in pattern_tags:
        pattern = (load_patterns or {}).get(int(pattern_tag))
        if pattern is None:
            raise ValueError(
                f"Response Spectrum references missing load pattern "
                f"{pattern_tag}."
            )
        if pattern.pattern_type != "UniformExcitation":
            raise ValueError(
                f"Response Spectrum pattern {pattern_tag} must be "
                "UniformExcitation."
            )
        series = (time_series or {}).get(int(pattern.time_series_tag))
        if series is None:
            raise ValueError(
                f"Response Spectrum pattern {pattern_tag} references "
                f"missing time series {pattern.time_series_tag}."
            )
        if series.series_type != "Path":
            raise ValueError(
                f"Response Spectrum time series {series.tag} must be Path."
            )
        scale = float(series.factor) * float(pattern.factor)
        components.append({
            "pattern_tag": int(pattern.tag),
            "time_series_tag": int(series.tag),
            "direction": int(pattern.direction),
            "name": str(series.name),
            "dt": float(series.dt),
            "values": [float(value) * scale for value in series.values],
        })
    if len(components) == 2:
        directions = [int(item["direction"]) for item in components]
        if any(direction not in {1, 2, 3} for direction in directions):
            raise ValueError(
                "Bidirectional RotD sources must use translational "
                "UniformExcitation directions 1, 2, or 3."
            )
        if directions[0] == directions[1]:
            raise ValueError(
                "Bidirectional RotD sources must use two distinct "
                "UniformExcitation directions."
            )
    return components


def analysis_to_openseespy(
    settings: AnalysisSettingsData,
    *,
    ndm: int = 3,
    node_tags: list[int] | None = None,
    element_tags: list[int] | None = None,
    frame_element_tags: list[int] | None = None,
    truss_element_tags: list[int] | None = None,
    shell_element_tags: list[int] | None = None,
    frame_history_tags: list[int] | None = None,
    shell_force_history_tags: list[int] | None = None,
    shell_deformation_history_tags: list[int] | None = None,
    masonry_history_tags: list[int] | None = None,
    mefi_crack_specs: dict[int, dict[str, object]] | None = None,
    support_node_tags: list[int] | None = None,
    plain_pattern_tags: list[int] | None = None,
    monitor_node: int | None = None,
    fiber_response_specs: dict[int, dict[str, object]] | None = None,
    specimen_response_spec: dict[str, object] | None = None,
    moment_curvature_spec: dict[str, object] | None = None,
    section_response_specs: list[dict[str, object]] | None = None,
    response_spectrum_components: list[dict[str, object]] | None = None,
    response_spectrum_gravity: float = 9.80665,
    requires_joint2d_handler: bool = False,
    requires_offset_rigid_handler: bool = False,
    krawinkler_panel_zone_tags: list[int] | None = None,
    joint_response_specs: dict[int, dict[str, object]] | None = None,
) -> list[str]:
    ndm = int(ndm)
    translational_dofs = tuple(range(1, max(ndm, 0) + 1))
    node_tags = list(node_tags or [])
    element_tags = list(element_tags or [])
    frame_element_tags = list(frame_element_tags or [])
    truss_element_tags = list(truss_element_tags or [])
    shell_element_tags = list(shell_element_tags or [])
    frame_history_tags = sorted({
        int(tag) for tag in (frame_history_tags or [])
    })
    shell_force_history_tags = sorted({
        int(tag) for tag in (shell_force_history_tags or [])
    })
    shell_deformation_history_tags = sorted({
        int(tag) for tag in (shell_deformation_history_tags or [])
    })
    masonry_history_tags = sorted({
        int(tag) for tag in (masonry_history_tags or [])
    })
    mefi_crack_specs = {
        int(tag): dict(spec)
        for tag, spec in (mefi_crack_specs or {}).items()
    }
    support_node_tags = list(support_node_tags or [])
    plain_pattern_tags = list(plain_pattern_tags or [])
    fiber_response_specs = dict(fiber_response_specs or {})
    specimen_response_spec = dict(specimen_response_spec or {})
    moment_curvature_spec = dict(moment_curvature_spec or {})
    section_response_specs = [
        dict(spec) for spec in (section_response_specs or [])
    ]
    response_spectrum_components = [
        dict(component)
        for component in (response_spectrum_components or [])
    ]
    krawinkler_panel_zone_tags = sorted({
        int(tag) for tag in (krawinkler_panel_zone_tags or [])
    })
    joint_response_specs = {
        int(tag): dict(spec)
        for tag, spec in (joint_response_specs or {}).items()
    }
    joint_response_catalog = {
        str(tag): {
            "connection_type": str(spec.get("connection_type", "")),
            "responses": [
                str(response)
                for response in spec.get("responses", ())
            ],
        }
        for tag, spec in sorted(joint_response_specs.items())
    }
    joint_response_history = {
        key: {
            "connection_type": str(spec.get("connection_type", "")),
            "responses": {
                response: []
                for response in spec.get("responses", ())
            },
        }
        for key, spec in joint_response_catalog.items()
    }
    section_response_catalog = {
        str(spec.get('key', f'response:{index}')): dict(spec)
        for index, spec in enumerate(section_response_specs)
    }
    section_response_history = {
        key: {'force': [], 'deformation': []}
        for key in section_response_catalog
    }
    mefi_panel_history = {
        str(tag): {
            str(int(panel.get("panel", index))): []
            for index, panel in enumerate(
                spec.get("panels", ()),
                start=1,
            )
        }
        for tag, spec in sorted(mefi_crack_specs.items())
    }
    frame_force_history = {
        str(tag): [] for tag in frame_history_tags
    }
    shell_force_history = {
        str(tag): [] for tag in shell_force_history_tags
    }
    shell_deformation_history = {
        str(tag): [] for tag in shell_deformation_history_tags
    }
    masonry_history = {
        str(tag): {
            "shear": [],
            "strut_forces": [],
            "strut_strains": [],
        }
        for tag in masonry_history_tags
    }
    system_command = (
        "ops.system('SparseGeneral', '-piv')"
        if settings.system == "SparseGeneral" and settings.system_pivoting
        else f"ops.system({settings.system!r})"
    )
    cyclic_steps = (
        cyclic_displacement_steps(
            settings.cyclic_targets,
            settings.cyclic_increment,
        )
        if settings.analysis_type == "Cyclic"
        else []
    )
    spectrum_periods = (
        build_period_grid(
            settings.response_spectrum_t1_step,
            settings.response_spectrum_t1_end,
            settings.response_spectrum_t2_step,
            settings.response_spectrum_t2_end,
            settings.response_spectrum_t3_step,
            settings.response_spectrum_t3_end,
        )
        if settings.analysis_type == "Response Spectrum"
        else []
    )
    if settings.analysis_type == "Cyclic":
        total_steps = len(cyclic_steps)
    elif settings.analysis_type == "Response Spectrum":
        total_steps = len(spectrum_periods)
    else:
        total_steps = settings.steps

    # Solver output is a UI transport, not the result database. Bound the
    # number of progress messages for long analyses and disable per-iteration
    # OpenSees printing when the step count is large. Full convergence data
    # are still collected from ops.testNorms() and stored in _studio_results.
    ui_target_updates = 400
    ui_stride = max(
        1,
        (max(int(total_steps), 1) + ui_target_updates - 1)
        // ui_target_updates,
    )
    live_stream_step_limit = 2000
    stream_live_convergence = bool(
        settings.live_convergence
        and int(total_steps) <= live_stream_step_limit
    )
    ui_throttled = bool(
        int(total_steps) > ui_target_updates
        or (
            settings.live_convergence
            and not stream_live_convergence
        )
    )
    if monitor_node is None and (
        settings.analysis_type in {"Pushover", "Cyclic"}
        or (
            settings.analysis_type == "Static"
            and settings.integrator == "DisplacementControl"
        )
    ):
        monitor_node = settings.control_node
    monitor_node = int(monitor_node or (node_tags[0] if node_tags else 1))

    effective_constraints_handler = settings.constraints_handler
    requires_transformation_handler = bool(
        requires_joint2d_handler or requires_offset_rigid_handler
    )
    if (
        requires_transformation_handler
        and effective_constraints_handler != "Transformation"
    ):
        effective_constraints_handler = "Transformation"

    lines = [
        f"# Active analysis {settings.tag}: {settings.name}",
        "def _studio_emit(_event, **_payload):",
        "    _payload['event'] = _event",
        "    print('[STUDIO_EVENT] ' + json.dumps(_payload, separators=(',', ':')), flush=True)",
        "",
        "def _studio_test_state():",
        "    try:",
        "        _iterations = int(ops.testIter())",
        "    except Exception:",
        "        _iterations = -1",
        "    try:",
        "        _all_norms = [float(v) for v in (ops.testNorms() or [])]",
        "        _used = max(0, min(_iterations, len(_all_norms)))",
        "        _norms = _all_norms[:_used]",
        "        _norm = float(_norms[-1]) if _norms else None",
        "    except Exception:",
        "        _norms = []",
        "        _norm = None",
        "    return _iterations, _norm, _norms",
        "",
        "_studio_results = {",
        "    'schema_version': 14,",
        "    'analysis': {",
        f"        'tag': {settings.tag},",
        f"        'name': {settings.name!r},",
        f"        'type': {settings.analysis_type!r},",
        f"        'constraints_handler': {effective_constraints_handler!r},",
        f"        'numberer': {settings.numberer!r},",
        f"        'system': {settings.system!r},",
        f"        'system_pivoting': {settings.system_pivoting!r},",
        f"        'test': {settings.test!r},",
        f"        'tolerance': {settings.tolerance:g},",
        f"        'max_iterations': {settings.max_iterations},",
        f"        'algorithm': {settings.algorithm!r},",
        f"        'algorithm_initial': {settings.algorithm_initial!r},",
        f"        'integrator': {settings.integrator!r},",
        f"        'steps': {settings.steps},",
        f"        'load_increment': {settings.load_increment:g},",
        f"        'control_node': {settings.control_node},",
        f"        'control_dof': {settings.control_dof},",
        f"        'displacement_increment': {settings.displacement_increment:g},",
        f"        'cyclic_targets': {settings.cyclic_targets!r},",
        f"        'cyclic_increment': {settings.cyclic_increment:g},",
        f"        'dt': {settings.dt:g},",
        f"        'gamma': {settings.gamma:g},",
        f"        'beta': {settings.beta:g},",
        f"        'hht_alpha': {settings.hht_alpha:g},",
        f"        'generalized_alpha_m': {settings.generalized_alpha_m:g},",
        f"        'generalized_alpha_f': {settings.generalized_alpha_f:g},",
        f"        'arc_length_s': {settings.arc_length_s:g},",
        f"        'arc_length_alpha': {settings.arc_length_alpha:g},",
        f"        'preload_gravity': {settings.preload_gravity!r},",
        f"        'gravity_steps': {settings.gravity_steps},",
        f"        'gravity_algorithm': {settings.gravity_algorithm!r},",
        f"        'deferred_pattern_tags': {settings.deferred_pattern_tags!r},",
        f"        'num_modes': {settings.num_modes},",
        f"        'recovery': {settings.recovery!r},",
        f"        'planned_steps': {total_steps},",
        f"        'adaptive_step': {settings.adaptive_step!r},",
        f"        'adaptive_cutback_factor': {settings.adaptive_cutback_factor:g},",
        f"        'adaptive_min_factor': {settings.adaptive_min_factor:g},",
        f"        'adaptive_growth_factor': {settings.adaptive_growth_factor:g},",
        f"        'adaptive_easy_iterations': {settings.adaptive_easy_iterations},",
        f"        'adaptive_growth_after': {settings.adaptive_growth_after},",
        f"        'live_convergence': {settings.live_convergence!r},",
        f"        'rayleigh_damping_ratio': {settings.rayleigh_damping_ratio:g},",
        f"        'rayleigh_mode_i': {settings.rayleigh_mode_i},",
        f"        'rayleigh_mode_j': {settings.rayleigh_mode_j},",
        f"        'eigen_solver': {settings.eigen_solver!r},",
        f"        'execution_mode': {settings.execution_mode!r},",
        f"        'num_threads': {settings.num_threads},",
        "    },",
        "    'specimen': " + repr(specimen_response_spec) + ",",
        "    'moment_curvature': " + repr(moment_curvature_spec) + ",",
        "    'section_responses': " + repr(section_response_catalog) + ",",
        "    'mefi_crack_specs': " + repr({
            str(tag): dict(spec)
            for tag, spec in sorted(mefi_crack_specs.items())
        }) + ",",
        "    'masonry_elements': " + repr(masonry_history_tags) + ",",
        "    'final': {},",
        "    'convergence': {",
        f"        'test': {settings.test!r},",
        f"        'tolerance': {settings.tolerance:g},",
        f"        'max_iterations': {settings.max_iterations},",
        f"        'primary_algorithm': {settings.algorithm!r},",
        f"        'adaptive_step': {settings.adaptive_step!r},",
        f"        'cutback_factor': {settings.adaptive_cutback_factor:g},",
        f"        'minimum_factor': {settings.adaptive_min_factor:g},",
        f"        'growth_factor': {settings.adaptive_growth_factor:g},",
        f"        'easy_iterations': {settings.adaptive_easy_iterations},",
        f"        'growth_after': {settings.adaptive_growth_after},",
        "        'steps': [],",
        "    },",
        "    'history': {'time': [], 'monitor_node': "
        f"{monitor_node}, 'control_dof': {settings.control_dof}, "
        "'displacement': [], 'base_shear': [], "
        "'base_reactions': [], 'nodes': {}, "
        "'element_local_forces': " + repr(frame_force_history) + ", "
        "'shell_section_forces': " + repr(shell_force_history) + ", "
        "'shell_section_deformations': " + repr(shell_deformation_history) + ", "
        "'masonry': " + repr(masonry_history) + ", "
        "'moment_curvature': {'force': [], 'deformation': []}, "
        "'section_responses': " + repr(section_response_history) + ", "
        "'mefi_panel_strains': " + repr(mefi_panel_history) + ", "
        "'joints': " + repr(joint_response_history) + ", "
        "'specimen': {"
        "'section_force': [], 'section_deformation': [], "
        "'base_fibers': [], 'interface_force': [], "
        "'interface_deformation': [], 'interface_fibers': []"
        "}}," ,
        "    'modes': {},",
        "}",
        f"_studio_node_tags = {node_tags!r}",
        "_studio_results['history']['nodes'] = {",
        "    str(_studio_node): {",
        "        'disp': [], 'vel': [], 'accel': [], 'reaction': []",
        "    }",
        "    for _studio_node in _studio_node_tags",
        "}",
        f"_studio_element_tags = {element_tags!r}",
        f"_studio_frame_element_tags = {frame_element_tags!r}",
        f"_studio_truss_element_tags = {truss_element_tags!r}",
        f"_studio_shell_element_tags = {shell_element_tags!r}",
        f"_studio_frame_history_tags = {frame_history_tags!r}",
        f"_studio_shell_force_history_tags = {shell_force_history_tags!r}",
        f"_studio_shell_deformation_history_tags = {shell_deformation_history_tags!r}",
        f"_studio_masonry_history_tags = {masonry_history_tags!r}",
        f"_studio_mefi_crack_specs = {mefi_crack_specs!r}",
        f"_studio_support_node_tags = {support_node_tags!r}",
        f"_studio_plain_pattern_tags = {plain_pattern_tags!r}",
        f"_studio_fiber_response_specs = {fiber_response_specs!r}",
        f"_studio_specimen_response_spec = {specimen_response_spec!r}",
        f"_studio_moment_curvature_spec = {moment_curvature_spec!r}",
        f"_studio_section_response_specs = {section_response_catalog!r}",
        f"_studio_joint_response_specs = {joint_response_catalog!r}",
        f"_studio_monitor_node = {monitor_node}",
        (
            "# OpenSees threads: Auto (runtime/default)"
            if settings.execution_mode == "Auto"
            else (
                "ops.setNumThreads(1)"
                if settings.execution_mode == "Single Thread"
                else f"ops.setNumThreads({settings.num_threads})"
            )
        ),
        (
            (
                "# Joint2D requires Transformation/Penalty; SARE uses "
                f"{effective_constraints_handler} for this generated analysis."
            )
            if requires_joint2d_handler
            else (
                "# Offset rigidLink beam requires a general MP handler; "
                f"SARE uses {effective_constraints_handler}."
            )
            if requires_offset_rigid_handler
            else f"# Constraint handler: {effective_constraints_handler}"
        ),
        f"ops.constraints('{effective_constraints_handler}')",
        f"ops.numberer('{settings.numberer}')",
        system_command,
    ]

    if settings.analysis_type == "Response Spectrum":
        expected = (
            1
            if settings.response_spectrum_mode == "Single Component"
            else 2
        )
        if len(response_spectrum_components) != expected:
            raise ValueError(
                f"Response Spectrum {settings.response_spectrum_mode} needs "
                f"{expected} resolved source component(s)."
            )
        source_metadata = [
            {
                key: component.get(key)
                for key in (
                    "pattern_tag",
                    "time_series_tag",
                    "direction",
                    "name",
                    "dt",
                )
            }
            for component in response_spectrum_components
        ]
        lines.extend([
            "",
            "# Response Spectrum generation (linear SDOF sweep)",
            "from openseespy_studio.response_spectrum import compute_response_spectrum as _studio_compute_response_spectrum",
            f"_studio_rs_sources = {response_spectrum_components!r}",
            f"_studio_rs_periods = {spectrum_periods!r}",
            "_studio_results['response_spectrum'] = {",
            f"    'mode': {settings.response_spectrum_mode!r},",
            f"    'damping_ratio': {settings.response_spectrum_damping_ratio:g},",
            f"    'sources': {source_metadata!r},",
            "    'period_s': [],",
        ])
        if settings.response_spectrum_component_x:
            lines.append("    'component_x_sa_g': [],")
        if settings.response_spectrum_component_y:
            lines.append("    'component_y_sa_g': [],")
        if settings.response_spectrum_rotd50:
            lines.append("    'rotd50_sa_g': [],")
        if settings.response_spectrum_rotd100:
            lines.append("    'rotd100_sa_g': [],")
        lines.extend([
            "}",
            (
                f"_studio_emit('start', total={len(spectrum_periods)}, "
                "analysis_type='Response Spectrum', "
                "algorithm='Linear Newmark SDOF')"
            ),
            "for _studio_index, _studio_period in enumerate(_studio_rs_periods, start=1):",
            "    _studio_point = _studio_compute_response_spectrum(",
            "        _studio_rs_sources,",
            "        [_studio_period],",
            f"        {settings.response_spectrum_damping_ratio:g},",
            f"        {float(response_spectrum_gravity):g},",
            f"        include_component_x={settings.response_spectrum_component_x!r},",
            f"        include_component_y={settings.response_spectrum_component_y!r},",
            f"        include_rotd50={settings.response_spectrum_rotd50!r},",
            f"        include_rotd100={settings.response_spectrum_rotd100!r},",
            "    )",
            "    _studio_curve = _studio_results['response_spectrum']",
            "    _studio_curve['period_s'].append(float(_studio_period))",
            "    for _studio_key in ('component_x_sa_g', 'component_y_sa_g', 'rotd50_sa_g', 'rotd100_sa_g'):",
            "        if _studio_key in _studio_curve and _studio_key in _studio_point:",
            "            _studio_curve[_studio_key].append(float(_studio_point[_studio_key][0]))",
            (
                f"    _studio_emit('progress', step=_studio_index, "
                f"total={len(spectrum_periods)}, "
                "percent=100.0 * _studio_index / max(len(_studio_rs_periods), 1), "
                "algorithm='Linear Newmark SDOF', iterations=0, "
                "time=float(_studio_period), monitor=0.0, base_shear=0.0)"
            ),
            "_studio_results['final'] = {",
            "    'response_spectrum_points': len(_studio_rs_periods),",
            "    'period_min_s': min(_studio_rs_periods) if _studio_rs_periods else None,",
            "    'period_max_s': max(_studio_rs_periods) if _studio_rs_periods else None,",
            "}",
        ])
        return lines

    _studio_has_direct_rayleigh = (
        settings.rayleigh_model == "DirectCoefficients"
        and any(
            abs(value) > 0.0
            for value in (
                settings.rayleigh_alpha_m,
                settings.rayleigh_beta_k,
                settings.rayleigh_beta_k_init,
                settings.rayleigh_beta_k_comm,
            )
        )
    )
    if (
        settings.analysis_type == "Transient"
        and (
            settings.rayleigh_damping_ratio > 0.0
            or _studio_has_direct_rayleigh
        )
    ):
        if settings.rayleigh_model == "DirectCoefficients":
            lines.extend([
                "# Rayleigh damping: imported direct coefficients",
                (
                    "ops.rayleigh("
                    f"{settings.rayleigh_alpha_m:g}, "
                    f"{settings.rayleigh_beta_k:g}, "
                    f"{settings.rayleigh_beta_k_init:g}, "
                    f"{settings.rayleigh_beta_k_comm:g})"
                ),
                "",
            ])
        elif settings.rayleigh_model == "SingleModeCommittedStiffness":
            max_mode = settings.rayleigh_mode_i
            lines.extend([
                "# Rayleigh damping: committed-stiffness proportional, calibrated to one mode",
                (
                    f"_studio_damping_eigs = ops.eigen("
                    f"{settings.eigen_solver!r}, {max_mode})"
                ),
                "if not isinstance(_studio_damping_eigs, (list, tuple)):",
                "    _studio_damping_eigs = [_studio_damping_eigs]",
                f"if len(_studio_damping_eigs) < {max_mode}:",
                (
                    "    raise RuntimeError("
                    f"'Rayleigh damping requested mode {max_mode}, but OpenSees '"
                    "f'returned only {len(_studio_damping_eigs)} eigenvalue(s). '"
                    "'Reduce the damping mode number or fix the model mass/stiffness.'"
                    ")"
                ),
                (
                    f"_studio_lambda_i = float(_studio_damping_eigs["
                    f"{settings.rayleigh_mode_i - 1}])"
                ),
                (
                    "if (not math.isfinite(_studio_lambda_i)) or "
                    "_studio_lambda_i <= 0.0:"
                ),
                (
                    "    raise RuntimeError("
                    f"'Rayleigh damping mode {settings.rayleigh_mode_i} returned an '"
                    "f'invalid eigenvalue ({_studio_lambda_i!r}); expected a finite, '"
                    "'positive value. Check constraints, mass, and stiffness.'"
                    ")"
                ),
                "_studio_omega_i = math.sqrt(_studio_lambda_i)",
                f"_studio_zeta = {settings.rayleigh_damping_ratio:g}",
                "_studio_beta_k_comm = 2.0 * _studio_zeta / _studio_omega_i",
                "ops.rayleigh(0.0, 0.0, 0.0, _studio_beta_k_comm)",
                "",
            ])
        else:
            max_mode = max(
                settings.rayleigh_mode_i,
                settings.rayleigh_mode_j,
            )
            lines.extend([
                "# Rayleigh damping from two modal frequencies",
                (
                    f"_studio_damping_eigs = ops.eigen("
                    f"{settings.eigen_solver!r}, {max_mode})"
                ),
                "if not isinstance(_studio_damping_eigs, (list, tuple)):",
                "    _studio_damping_eigs = [_studio_damping_eigs]",
                (
                    f"if len(_studio_damping_eigs) < {max_mode}:"
                ),
                (
                    "    raise RuntimeError("
                    f"'Rayleigh damping requested mode {max_mode}, but OpenSees '"
                    "f'returned only {len(_studio_damping_eigs)} eigenvalue(s). '"
                    "'Reduce the damping mode numbers or fix the model mass/stiffness.'"
                    ")"
                ),
                (
                    f"_studio_lambda_i = float(_studio_damping_eigs["
                    f"{settings.rayleigh_mode_i - 1}])"
                ),
                (
                    f"_studio_lambda_j = float(_studio_damping_eigs["
                    f"{settings.rayleigh_mode_j - 1}])"
                ),
                (
                    "if (not math.isfinite(_studio_lambda_i)) or "
                    "_studio_lambda_i <= 0.0:"
                ),
                (
                    "    raise RuntimeError("
                    f"'Rayleigh damping mode {settings.rayleigh_mode_i} returned an '"
                    "f'invalid eigenvalue ({_studio_lambda_i!r}); expected a finite, '"
                    "'positive value. Check constraints, mass, and stiffness.'"
                    ")"
                ),
                (
                    "if (not math.isfinite(_studio_lambda_j)) or "
                    "_studio_lambda_j <= 0.0:"
                ),
                (
                    "    raise RuntimeError("
                    f"'Rayleigh damping mode {settings.rayleigh_mode_j} returned an '"
                    "f'invalid eigenvalue ({_studio_lambda_j!r}); expected a finite, '"
                    "'positive value. Check constraints, mass, and stiffness.'"
                    ")"
                ),
                "_studio_omega_i = math.sqrt(_studio_lambda_i)",
                "_studio_omega_j = math.sqrt(_studio_lambda_j)",
                (
                    f"_studio_zeta = {settings.rayleigh_damping_ratio:g}"
                ),
                (
                    "_studio_beta_k = "
                    "2.0 * _studio_zeta / "
                    "(_studio_omega_i + _studio_omega_j)"
                ),
                (
                    "_studio_alpha_m = "
                    "_studio_beta_k * _studio_omega_i * _studio_omega_j"
                ),
                "ops.rayleigh(_studio_alpha_m, 0.0, 0.0, _studio_beta_k)",
                "",
            ])

    if (
        settings.analysis_type == "Transient"
        and krawinkler_panel_zone_tags
        and (
            settings.rayleigh_damping_ratio > 0.0
            or _studio_has_direct_rayleigh
        )
    ):
        lines.append(
            "# Exclude Krawinkler rigid panel-boundary members from "
            "Rayleigh damping"
        )
        for panel_tag in krawinkler_panel_zone_tags:
            p = f"_sare_pz_{panel_tag}"
            internal_tags = ", ".join(
                f"{p}_ebase + {index}" for index in range(8)
            )
            lines.append(
                f"ops.region({panel_tag}, '-eleOnly', {internal_tags}, "
                "'-rayleigh', 0.0, 0.0, 0.0, 0.0)"
            )
        lines.append("")

    if settings.analysis_type == "Modal":
        lines.append(
            f"_studio_emit('start', total={settings.num_modes}, "
            f"analysis_type='Modal', algorithm={settings.eigen_solver!r})"
        )
        lines.append(
            f"_studio_eigenvalues = ops.eigen("
            f"{settings.eigen_solver!r}, {settings.num_modes})"
        )
        lines.append("if not isinstance(_studio_eigenvalues, (list, tuple)):")
        lines.append("    _studio_eigenvalues = [_studio_eigenvalues]")
        lines.extend([
            (
                f"if len(_studio_eigenvalues) < {settings.num_modes}:"
            ),
            (
                "    raise RuntimeError("
                f"'Modal analysis requested {settings.num_modes} mode(s), but OpenSees '"
                "f'returned only {len(_studio_eigenvalues)} eigenvalue(s). '"
                "'Reduce the requested mode count or check constraints, mass, and stiffness.'"
                ")"
            ),
            "try:",
            "    _studio_modal_properties = ops.modalProperties('-return')",
            "except Exception as _studio_modal_exc:",
            "    raise RuntimeError(",
            "        'OpenSees modalProperties(-return) failed; accurate modal mass '",
            "        'participation requires the assembled nodal and element mass matrix.'",
            "    ) from _studio_modal_exc",
            "if not isinstance(_studio_modal_properties, dict):",
            "    raise RuntimeError(",
            "        'OpenSees modalProperties(-return) did not return a dictionary.'",
            "    )",
            "_studio_modal_directions = {1: 'MX', 2: 'MY', 3: 'MZ'}",
            f"_studio_modal_directions = {{k: v for k, v in _studio_modal_directions.items() if k in {translational_dofs!r}}}",
            "_studio_total_mass_values = list(_studio_modal_properties.get('totalMass', []))",
            "_studio_total_free_mass_values = list(_studio_modal_properties.get('totalFreeMass', []))",
            f"if len(_studio_total_mass_values) < {len(translational_dofs)}:",
            "    raise RuntimeError('OpenSees modalProperties returned incomplete totalMass data.')",
            f"if len(_studio_total_free_mass_values) < {len(translational_dofs)}:",
            "    raise RuntimeError('OpenSees modalProperties returned incomplete totalFreeMass data.')",
            "_studio_total_lumped_mass = {",
            "    str(_studio_dof): float(_studio_total_mass_values[_studio_dof - 1])",
            "    for _studio_dof in _studio_modal_directions",
            "}",
            "_studio_total_free_mass = {",
            "    str(_studio_dof): float(_studio_total_free_mass_values[_studio_dof - 1])",
            "    for _studio_dof in _studio_modal_directions",
            "}",
            "_studio_results['modal_summary'] = {",
            f"    'eigen_solver': {settings.eigen_solver!r},",
            "    'total_lumped_mass': dict(_studio_total_lumped_mass),",
            "    'total_free_mass': dict(_studio_total_free_mass),",
            "}",
        ])
        lines.append(
            "for _studio_mode, _studio_lambda in "
            "enumerate(_studio_eigenvalues, start=1):"
        )
        lines.extend([
            "    _studio_lambda = float(_studio_lambda)",
            (
                "    if (not math.isfinite(_studio_lambda)) or "
                "_studio_lambda < 0.0:"
            ),
            (
                "        raise RuntimeError("
                "f'Modal mode {_studio_mode} returned an invalid eigenvalue '"
                "f'({_studio_lambda!r}); expected a finite, non-negative value. '"
                "'Check constraints, mass, stiffness, and geometric stability.'"
                ")"
            ),
            "    _studio_omega = math.sqrt(_studio_lambda)",
            (
                "    _studio_frequency = "
                "_studio_omega / (2.0 * math.pi) "
                "if _studio_omega > 0.0 else None"
            ),
            (
                "    _studio_period = "
                "(2.0 * math.pi / _studio_omega) "
                "if _studio_omega > 0.0 else None"
            ),
            "    _studio_vectors = {}",
            "    for _studio_node in _studio_node_tags:",
            "        _studio_vectors[str(_studio_node)] = [",
            "            float(v) for v in",
            "            ops.nodeEigenvector(_studio_node, _studio_mode)",
            "        ]",
            "    _studio_participation = {}",
            "    for _studio_dof, _studio_axis in _studio_modal_directions.items():",
            "        _studio_index = _studio_mode - 1",
            "        _studio_factor_values = list(",
            "            _studio_modal_properties.get(",
            "                f'partiFactor{_studio_axis}', []",
            "            )",
            "        )",
            "        _studio_mass_values = list(",
            "            _studio_modal_properties.get(",
            "                f'partiMass{_studio_axis}', []",
            "            )",
            "        )",
            "        _studio_ratio_values = list(",
            "            _studio_modal_properties.get(",
            "                f'partiMassRatios{_studio_axis}', []",
            "            )",
            "        )",
            "        if (",
            "            len(_studio_factor_values) <= _studio_index",
            "            or len(_studio_mass_values) <= _studio_index",
            "            or len(_studio_ratio_values) <= _studio_index",
            "        ):",
            "            raise RuntimeError(",
            "                f'OpenSees modalProperties returned incomplete participation '",
            "                f'data for mode {_studio_mode}, direction {_studio_axis}.'",
            "            )",
            "        _studio_participation[str(_studio_dof)] = {",
            "            'factor': float(_studio_factor_values[_studio_index]),",
            "            'effective_mass': float(_studio_mass_values[_studio_index]),",
            "            'mass_ratio': float(_studio_ratio_values[_studio_index]) / 100.0,",
            "        }",
            "    _studio_results['modes'][str(_studio_mode)] = {",
            "        'eigenvalue': _studio_lambda,",
            "        'omega_rad_s': float(_studio_omega),",
            "        'frequency_hz': _studio_frequency,",
            "        'period_s': _studio_period,",
            "        'vectors': _studio_vectors,",
            "        'participation': _studio_participation,",
            "    }",
        ])
        lines.append(
            "    _studio_emit('progress', step=_studio_mode, "
            f"total={settings.num_modes}, "
            f"percent=100.0 * _studio_mode / {settings.num_modes}, "
            f"algorithm={settings.eigen_solver!r}, iterations=0, "
            "time=0.0, monitor=0.0, base_shear=0.0, "
            "eigenvalue=_studio_lambda)"
        )
        lines.append(
            "_studio_results['eigenvalues'] = "
            "[float(v) for v in _studio_eigenvalues]"
        )
        lines.append("print('Eigenvalues:', _studio_eigenvalues)")
        return lines

    _studio_print_flag = 1 if stream_live_convergence else 0
    if settings.algorithm != "Linear":
        lines.append(
            f"ops.test('{settings.test}', {settings.tolerance:g}, "
            f"{settings.max_iterations}, {_studio_print_flag})"
        )
    lines.append(f"_studio_primary_algorithm = {settings.algorithm!r}")
    lines.append(
        f"_studio_primary_algorithm_initial = "
        f"{settings.algorithm_initial!r}"
    )
    lines.extend([
        "def _studio_apply_primary_algorithm():",
        "    if (_studio_primary_algorithm == 'ModifiedNewton' "
        "and _studio_primary_algorithm_initial):",
        "        ops.algorithm('ModifiedNewton', '-initial')",
        "    else:",
        "        ops.algorithm(_studio_primary_algorithm)",
        "",
        "_studio_apply_primary_algorithm()",
    ])

    if settings.analysis_type == "Static":
        if settings.integrator == "LoadControl":
            lines.append(
                f"ops.integrator('LoadControl', {settings.load_increment:g})"
            )
        elif settings.integrator == "DisplacementControl":
            lines.append(
                f"ops.integrator('DisplacementControl', {settings.control_node}, "
                f"{settings.control_dof}, {settings.displacement_increment:g})"
            )
        elif settings.integrator == "ArcLength":
            lines.append(
                f"ops.integrator('ArcLength', {settings.arc_length_s:g}, "
                f"{settings.arc_length_alpha:g})"
            )
        else:
            raise ValueError(
                f"Unsupported Static integrator: {settings.integrator}"
            )
        analyze_call = "ops.analyze(1)"
        analysis_kind = "Static"
    elif settings.analysis_type == "Pushover":
        lines.append(
            f"ops.integrator('DisplacementControl', {settings.control_node}, "
            f"{settings.control_dof}, {settings.displacement_increment:g})"
        )
        analyze_call = "ops.analyze(1)"
        analysis_kind = "Static"
    elif settings.analysis_type == "Cyclic":
        if not cyclic_steps:
            raise ValueError(
                "Cyclic protocol produced no displacement increments."
            )
        lines.append(f"_studio_cyclic_increments = {cyclic_steps!r}")
        lines.append(
            f"ops.integrator('DisplacementControl', {settings.control_node}, "
            f"{settings.control_dof}, _studio_cyclic_increments[0])"
        )
        analyze_call = "ops.analyze(1)"
        analysis_kind = "Static"
    elif settings.analysis_type == "Transient":
        if settings.integrator == "Newmark":
            lines.append(
                f"ops.integrator('Newmark', {settings.gamma:g}, "
                f"{settings.beta:g})"
            )
        elif settings.integrator == "HHT":
            lines.append(
                f"ops.integrator('HHT', {settings.hht_alpha:g})"
            )
        elif settings.integrator == "GeneralizedAlpha":
            lines.append(
                f"ops.integrator('GeneralizedAlpha', "
                f"{settings.generalized_alpha_m:g}, "
                f"{settings.generalized_alpha_f:g})"
            )
        else:
            raise ValueError(
                f"Unsupported Transient integrator: {settings.integrator}"
            )
        analyze_call = f"ops.analyze(1, {settings.dt:g})"
        analysis_kind = "Transient"
    else:
        raise ValueError(
            f"Unsupported analysis type: {settings.analysis_type}"
        )

    lines.append(f"ops.analysis('{analysis_kind}')")
    lines.append(
        f"_studio_emit('start', total={total_steps}, "
        f"analysis_type={settings.analysis_type!r}, "
        f"integrator={settings.integrator!r}, "
        f"algorithm=_studio_primary_algorithm, "
        f"test={settings.test!r}, tolerance={settings.tolerance:g}, "
        f"live_convergence={stream_live_convergence!r}, "
        f"live_convergence_requested={settings.live_convergence!r}, "
        f"ui_stride={ui_stride}, ui_throttled={ui_throttled!r}, "
        f"adaptive_step={settings.adaptive_step!r})"
    )
    if settings.adaptive_step:
        if settings.analysis_type == "Static":
            if settings.integrator == "LoadControl":
                adaptive_initial = abs(settings.load_increment)
                nominal_source = f"{settings.load_increment:g}"
            elif settings.integrator == "DisplacementControl":
                adaptive_initial = abs(settings.displacement_increment)
                nominal_source = f"{settings.displacement_increment:g}"
            elif settings.integrator == "ArcLength":
                adaptive_initial = abs(settings.arc_length_s)
                nominal_source = f"{settings.arc_length_s:g}"
            else:
                raise ValueError(
                    f"Unsupported adaptive Static integrator: "
                    f"{settings.integrator}"
                )
            adaptive_analyze_call = "ops.analyze(1)"
        elif settings.analysis_type == "Pushover":
            adaptive_initial = abs(settings.displacement_increment)
            nominal_source = f"{settings.displacement_increment:g}"
            adaptive_analyze_call = "ops.analyze(1)"
        elif settings.analysis_type == "Cyclic":
            adaptive_initial = abs(settings.cyclic_increment)
            nominal_source = "_studio_cyclic_increments[_studio_step]"
            adaptive_analyze_call = "ops.analyze(1)"
        else:
            adaptive_initial = abs(settings.dt)
            nominal_source = f"{settings.dt:g}"
            adaptive_analyze_call = "ops.analyze(1, _studio_trial_size)"

        adaptive_fallbacks = [
            algorithm
            for algorithm in ("NewtonLineSearch", "ModifiedNewton", "Newton")
            if algorithm != settings.algorithm
        ]

        lines.extend([
            f"_studio_adaptive_size = {adaptive_initial:g}",
            "_studio_easy_streak = 0",
            f"_studio_cutback_factor = {settings.adaptive_cutback_factor:g}",
            f"_studio_min_factor = {settings.adaptive_min_factor:g}",
            f"_studio_growth_factor = {settings.adaptive_growth_factor:g}",
            f"_studio_easy_iterations = {settings.adaptive_easy_iterations}",
            f"_studio_growth_after = {settings.adaptive_growth_after}",
        ])
        lines.append(f"for _studio_step in range({total_steps}):")
        lines.append("    _studio_step_no = _studio_step + 1")
        lines.append(f"    _studio_nominal_increment = {nominal_source}")
        lines.append("    _studio_reference_size = abs(_studio_nominal_increment)")
        lines.append(
            "    _studio_remaining_tol = "
            "max(_studio_reference_size, 1.0) * 1.0e-12"
        )
        lines.append("    _studio_remaining = _studio_nominal_increment")
        lines.append(
            "    _studio_min_size = "
            "_studio_reference_size * _studio_min_factor"
        )
        lines.append(
            "    _studio_adaptive_size = min("
            "_studio_reference_size, "
            "max(_studio_min_size, _studio_adaptive_size)"
            ") if _studio_reference_size > 0.0 else 0.0"
        )
        lines.append("    _studio_attempts = []")
        lines.append("    _studio_substeps = []")
        lines.append("    _studio_cutbacks = 0")
        lines.append("    _studio_had_recovery = False")
        lines.append(
            "    if "
            f"{stream_live_convergence!r} or "
            "_studio_step_no == 1 or "
            f"_studio_step_no == {total_steps} or "
            f"_studio_step_no % {ui_stride} == 0:"
        )
        lines.append(
            "        _studio_emit('step_start', step=_studio_step_no, "
            f"total={total_steps}, algorithm=_studio_primary_algorithm, "
            f"test={settings.test!r}, tolerance={settings.tolerance:g}, "
            f"live_convergence={stream_live_convergence!r}, "
            "adaptive_step=True, "
            "increment=_studio_nominal_increment, "
            "step_size=_studio_adaptive_size)"
        )
        lines.append(
            "    while abs(_studio_remaining) > _studio_remaining_tol:"
        )
        lines.append(
            "        _studio_direction = "
            "1.0 if _studio_remaining >= 0.0 else -1.0"
        )
        lines.append(
            "        _studio_trial_size = min("
            "abs(_studio_remaining), _studio_adaptive_size)"
        )
        lines.append(
            "        _studio_trial_increment = "
            "_studio_direction * _studio_trial_size"
        )
        lines.append("        _studio_trial_attempts = []")
        lines.append(
            "        _studio_active_algorithm = _studio_primary_algorithm"
        )
        lines.append("        _studio_apply_primary_algorithm()")

        if settings.analysis_type == "Static":
            if settings.integrator == "LoadControl":
                lines.append(
                    "        ops.integrator('LoadControl', "
                    "_studio_trial_increment)"
                )
            elif settings.integrator == "DisplacementControl":
                lines.append(
                    f"        ops.integrator('DisplacementControl', "
                    f"{settings.control_node}, {settings.control_dof}, "
                    "_studio_trial_increment)"
                )
            elif settings.integrator == "ArcLength":
                lines.append(
                    f"        ops.integrator('ArcLength', "
                    f"_studio_trial_size, {settings.arc_length_alpha:g})"
                )
        elif settings.analysis_type in {"Pushover", "Cyclic"}:
            lines.append(
                f"        ops.integrator('DisplacementControl', "
                f"{settings.control_node}, {settings.control_dof}, "
                "_studio_trial_increment)"
            )

        lines.append(f"        _studio_ok = {adaptive_analyze_call}")
        lines.append(
            "        _studio_iterations, _studio_norm, "
            "_studio_norm_history = _studio_test_state()"
        )
        lines.append(
            "        _studio_trial_attempts.append({"
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'norm': _studio_norm, "
            "'norm_history': list(_studio_norm_history), "
            "'code': int(_studio_ok), "
            "'success': bool(_studio_ok == 0), "
            "'increment': _studio_trial_increment"
            "})"
        )
        lines.append("        if _studio_ok != 0:")
        lines.append(
            "            _studio_emit('convergence_failed', "
            "step=_studio_step_no, "
            f"total={total_steps}, "
            "algorithm=_studio_active_algorithm, "
            "iterations=_studio_iterations, norm=_studio_norm, "
            "code=int(_studio_ok), "
            "increment=_studio_trial_increment)"
        )

        if settings.recovery and settings.algorithm != "Linear":
            lines.append(
                f"            for _studio_alg in {adaptive_fallbacks!r}:"
            )
            lines.append(
                "                _studio_emit('fallback', "
                "step=_studio_step_no, "
                f"total={total_steps}, algorithm=_studio_alg, "
                "increment=_studio_trial_increment)"
            )
            lines.append(
                "                _studio_active_algorithm = _studio_alg"
            )
            lines.append("                ops.algorithm(_studio_alg)")
            lines.append(f"                _studio_ok = {adaptive_analyze_call}")
            lines.append(
                "                _studio_iterations, _studio_norm, "
                "_studio_norm_history = _studio_test_state()"
            )
            lines.append(
                "                _studio_trial_attempts.append({"
                "'algorithm': _studio_alg, "
                "'iterations': _studio_iterations, "
                "'norm': _studio_norm, "
                "'norm_history': list(_studio_norm_history), "
                "'code': int(_studio_ok), "
                "'success': bool(_studio_ok == 0), "
                "'increment': _studio_trial_increment"
                "})"
            )
            lines.append("                if _studio_ok == 0:")
            lines.append(
                "                    _studio_emit('recovered', "
                "step=_studio_step_no, "
                f"total={total_steps}, algorithm=_studio_alg, "
                "iterations=_studio_iterations, norm=_studio_norm, "
                "increment=_studio_trial_increment)"
            )
            lines.append("                    break")

        lines.append("        if _studio_ok != 0:")
        lines.append(
            "            _studio_substeps.append({"
            "'accepted': False, "
            "'increment': _studio_trial_increment, "
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'norm': _studio_norm, "
            "'time': float(ops.getTime()), "
            "'attempts': list(_studio_trial_attempts)"
            "})"
        )
        lines.append(
            "            _studio_attempts.extend(_studio_trial_attempts)"
        )
        lines.append(
            "            _studio_can_cutback = "
            "_studio_trial_size > "
            "_studio_min_size * (1.0 + 1.0e-12)"
        )
        lines.append("            if _studio_can_cutback:")
        lines.append(
            "                _studio_new_size = max("
            "_studio_min_size, "
            "_studio_trial_size * _studio_cutback_factor)"
        )
        lines.append(
            "                _studio_old_size = _studio_trial_size"
        )
        lines.append(
            "                _studio_adaptive_size = _studio_new_size"
        )
        lines.append("                _studio_cutbacks += 1")
        lines.append("                _studio_easy_streak = 0")
        lines.append(
            "                _studio_emit('cutback', "
            "step=_studio_step_no, "
            f"total={total_steps}, "
            "old_size=_studio_old_size, "
            "new_size=_studio_new_size, "
            "remaining=_studio_remaining, "
            "cutbacks=_studio_cutbacks, "
            "algorithm=_studio_primary_algorithm)"
        )
        lines.append(
            "                _studio_apply_primary_algorithm()"
        )
        lines.append("                continue")
        lines.append(
            "            _studio_total_iterations = sum("
            "max(0, int(_a.get('iterations', 0) or 0)) "
            "for _a in _studio_attempts)"
        )
        lines.append(
            "            _studio_results['convergence']['steps'].append({"
            "'step': _studio_step_no, "
            "'status': 'failed', "
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'total_iterations': _studio_total_iterations, "
            "'norm': _studio_norm, "
            "'recovered': False, "
            "'adaptive': True, "
            "'cutbacks': _studio_cutbacks, "
            "'nominal_increment': _studio_nominal_increment, "
            "'time': float(ops.getTime()), "
            "'substeps': list(_studio_substeps), "
            "'attempts': list(_studio_attempts)"
            "})"
        )
        lines.append(
            "            _studio_emit('failed', "
            "step=_studio_step_no, "
            f"total={total_steps}, "
            "algorithm=_studio_active_algorithm, "
            "iterations=_studio_iterations, "
            "norm=_studio_norm, code=int(_studio_ok), "
            "increment=_studio_trial_increment, "
            "cutbacks=_studio_cutbacks)"
        )
        lines.append(
            "            raise RuntimeError("
            "f'Analysis failed at step {_studio_step_no} "
            "after adaptive cutback')"
        )
        lines.append(
            "        _studio_attempts.extend(_studio_trial_attempts)"
        )
        lines.append(
            "        _studio_had_recovery = "
            "_studio_had_recovery or "
            "len(_studio_trial_attempts) > 1"
        )
        lines.append(
            "        _studio_substeps.append({"
            "'accepted': True, "
            "'increment': _studio_trial_increment, "
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'norm': _studio_norm, "
            "'time': float(ops.getTime()), "
            "'attempts': list(_studio_trial_attempts)"
            "})"
        )
        lines.append(
            "        _studio_remaining -= _studio_trial_increment"
        )
        lines.append(
            "        if abs(_studio_remaining) <= _studio_remaining_tol:"
        )
        lines.append("            _studio_remaining = 0.0")
        lines.append(
            "        _studio_easy = ("
            "_studio_ok == 0 "
            "and len(_studio_trial_attempts) == 1 "
            "and _studio_iterations >= 0 "
            "and _studio_iterations <= _studio_easy_iterations"
            ")"
        )
        lines.append(
            "        _studio_easy_streak = "
            "_studio_easy_streak + 1 if _studio_easy else 0"
        )
        lines.append(
            "        if ("
            "_studio_easy_streak >= _studio_growth_after "
            "and _studio_adaptive_size < "
            "_studio_reference_size * (1.0 - 1.0e-12)"
            "):"
        )
        lines.append(
            "            _studio_old_size = _studio_adaptive_size"
        )
        lines.append(
            "            _studio_adaptive_size = min("
            "_studio_reference_size, "
            "_studio_adaptive_size * _studio_growth_factor)"
        )
        lines.append(
            "            if _studio_adaptive_size > "
            "_studio_old_size * (1.0 + 1.0e-12):"
        )
        lines.append(
            "                _studio_emit('grow', "
            "step=_studio_step_no, "
            f"total={total_steps}, "
            "old_size=_studio_old_size, "
            "new_size=_studio_adaptive_size, "
            "algorithm=_studio_primary_algorithm)"
        )
        lines.append("            _studio_easy_streak = 0")
        lines.append("        _studio_apply_primary_algorithm()")
        lines.append("        if _studio_remaining != 0.0:")
        lines.append(
            "            _studio_emit('adaptive_substep', "
            "step=_studio_step_no, "
            f"total={total_steps}, "
            "accepted_increment=_studio_trial_increment, "
            "remaining=_studio_remaining, "
            "next_size=min(abs(_studio_remaining), "
            "_studio_adaptive_size), "
            "time=float(ops.getTime()), "
            "algorithm=_studio_primary_algorithm)"
        )

        lines.append("    _studio_time = float(ops.getTime())")
        lines.append(
            "    _studio_total_iterations = sum("
            "max(0, int(_a.get('iterations', 0) or 0)) "
            "for _a in _studio_attempts)"
        )
        lines.append(
            "    _studio_step_recovered = "
            "bool(_studio_cutbacks > 0 or _studio_had_recovery)"
        )
        lines.append(
            "    _studio_accepted_sizes = ["
            "abs(float(_s.get('increment', 0.0))) "
            "for _s in _studio_substeps "
            "if _s.get('accepted')"
            "]"
        )
        lines.append(
            "    _studio_results['convergence']['steps'].append({"
            "'step': _studio_step_no, "
            "'status': 'recovered' "
            "if _studio_step_recovered else 'converged', "
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'total_iterations': _studio_total_iterations, "
            "'norm': _studio_norm, "
            "'recovered': _studio_step_recovered, "
            "'adaptive': True, "
            "'cutbacks': _studio_cutbacks, "
            "'nominal_increment': _studio_nominal_increment, "
            "'min_step_size_used': "
            "min(_studio_accepted_sizes) "
            "if _studio_accepted_sizes else None, "
            "'final_step_size': _studio_adaptive_size, "
            "'time': _studio_time, "
            "'substeps': list(_studio_substeps), "
            "'attempts': list(_studio_attempts)"
            "})"
        )
        lines.append(
            "    _studio_results['history']['time'].append(_studio_time)"
        )
    else:
        lines.append(f"for _studio_step in range({total_steps}):")
        lines.append("    _studio_step_no = _studio_step + 1")
        lines.append("    _studio_attempts = []")
        lines.append(
            "    if "
            f"{stream_live_convergence!r} or "
            "_studio_step_no == 1 or "
            f"_studio_step_no == {total_steps} or "
            f"_studio_step_no % {ui_stride} == 0:"
        )
        lines.append(
            "        _studio_emit('step_start', step=_studio_step_no, "
            f"total={total_steps}, algorithm=_studio_primary_algorithm, "
            f"test={settings.test!r}, tolerance={settings.tolerance:g}, "
            f"live_convergence={stream_live_convergence!r})"
        )
        if settings.analysis_type == "Cyclic":
            lines.append(
                "    _studio_disp_increment = "
                "_studio_cyclic_increments[_studio_step]"
            )
            lines.append(
                f"    ops.integrator('DisplacementControl', "
                f"{settings.control_node}, {settings.control_dof}, "
                "_studio_disp_increment)"
            )
        lines.append("    _studio_active_algorithm = _studio_primary_algorithm")
        lines.append(f"    _studio_ok = {analyze_call}")
        lines.append(
            "    _studio_iterations, _studio_norm, "
            "_studio_norm_history = _studio_test_state()"
        )
        lines.append(
            "    _studio_attempts.append({"
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'norm': _studio_norm, "
            "'norm_history': list(_studio_norm_history), "
            "'code': int(_studio_ok), "
            "'success': bool(_studio_ok == 0)"
            "})"
        )
        lines.append("    if _studio_ok != 0:")
        lines.append(
            "        _studio_emit('convergence_failed', "
            "step=_studio_step_no, "
            f"total={total_steps}, "
            "algorithm=_studio_active_algorithm, "
            "iterations=_studio_iterations, norm=_studio_norm, "
            "code=int(_studio_ok))"
        )
    
        if settings.recovery and settings.algorithm != "Linear":
            fallbacks = [
                algorithm
                for algorithm in ("NewtonLineSearch", "ModifiedNewton", "Newton")
                if algorithm != settings.algorithm
            ]
            lines.append(f"        for _studio_alg in {fallbacks!r}:")
            lines.append(
                "            _studio_emit('fallback', "
                "step=_studio_step_no, "
                f"total={total_steps}, algorithm=_studio_alg)"
            )
            lines.append("            _studio_active_algorithm = _studio_alg")
            lines.append("            ops.algorithm(_studio_alg)")
            lines.append(f"            _studio_ok = {analyze_call}")
            lines.append(
                "            _studio_iterations, _studio_norm, "
                "_studio_norm_history = _studio_test_state()"
            )
            lines.append(
                "            _studio_attempts.append({"
                "'algorithm': _studio_alg, "
                "'iterations': _studio_iterations, "
                "'norm': _studio_norm, "
                "'norm_history': list(_studio_norm_history), "
                "'code': int(_studio_ok), "
                "'success': bool(_studio_ok == 0)"
                "})"
            )
            lines.append("            if _studio_ok == 0:")
            lines.append("                _studio_active_algorithm = _studio_alg")
            lines.append(
                "                _studio_emit('recovered', "
                "step=_studio_step_no, "
                f"total={total_steps}, algorithm=_studio_alg, "
                "iterations=_studio_iterations, norm=_studio_norm)"
            )
            lines.append("                break")
            lines.append("        _studio_apply_primary_algorithm()")
    
        lines.append("    if _studio_ok != 0:")
        lines.append(
            "        _studio_results['convergence']['steps'].append({"
            "'step': _studio_step_no, "
            "'status': 'failed', "
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'norm': _studio_norm, "
            "'recovered': False, "
            "'time': float(ops.getTime()), "
            "'attempts': list(_studio_attempts)"
            "})"
        )
        lines.append(
            "        _studio_emit('failed', step=_studio_step_no, "
            f"total={total_steps}, "
            "algorithm=_studio_active_algorithm, "
            "iterations=_studio_iterations, norm=_studio_norm, "
            "code=int(_studio_ok))"
        )
        lines.append(
            "        raise RuntimeError("
            "f'Analysis failed at step {_studio_step_no}')"
        )
        lines.append("    _studio_time = float(ops.getTime())")
        lines.append(
            "    _studio_results['convergence']['steps'].append({"
            "'step': _studio_step_no, "
            "'status': 'recovered' if len(_studio_attempts) > 1 else 'converged', "
            "'algorithm': _studio_active_algorithm, "
            "'iterations': _studio_iterations, "
            "'norm': _studio_norm, "
            "'recovered': bool(len(_studio_attempts) > 1), "
            "'time': _studio_time, "
            "'attempts': list(_studio_attempts)"
            "})"
        )
        lines.append(
            "    _studio_results['history']['time'].append(_studio_time)"
        )
    
    if settings.analysis_type == "Transient":
        lines.append("    ops.reactions('-dynamic', '-rayleigh')")
    else:
        lines.append("    ops.reactions()")
    lines.append("    _studio_base_reactions = [0.0] * 6")
    lines.append("    for _studio_support in _studio_support_node_tags:")
    lines.append(
        "        _studio_support_reaction = "
        "[float(v) for v in ops.nodeReaction(_studio_support)]"
    )
    lines.append(
        "        for _studio_dof_index, _studio_value in "
        "enumerate(_studio_support_reaction[:6]):"
    )
    lines.append(
        "            _studio_base_reactions[_studio_dof_index] += "
        "_studio_value"
    )
    lines.append(
        "    _studio_results['history']['base_reactions'].append("
        "_studio_base_reactions)"
    )
    lines.append(
        f"    _studio_base = "
        f"float(_studio_base_reactions[{settings.control_dof - 1}])"
    )
    lines.append(
        "    _studio_results['history']['base_shear'].append(_studio_base)"
    )
    lines.append("    for _studio_node in _studio_node_tags:")
    lines.append(
        "        _studio_disp_row = "
        "[float(v) for v in ops.nodeDisp(_studio_node)]"
    )
    lines.append(
        "        _studio_vel_row = "
        "[float(v) for v in ops.nodeVel(_studio_node)]"
    )
    lines.append(
        "        _studio_accel_row = "
        "[float(v) for v in ops.nodeAccel(_studio_node)]"
    )
    lines.append(
        "        _studio_reaction_row = "
        "[float(v) for v in ops.nodeReaction(_studio_node)]"
    )
    lines.append(
        "        _studio_node_history = "
        "_studio_results['history']['nodes'][str(_studio_node)]"
    )
    lines.append(
        "        _studio_node_history['disp'].append(_studio_disp_row)"
    )
    lines.append(
        "        _studio_node_history['vel'].append(_studio_vel_row)"
    )
    lines.append(
        "        _studio_node_history['accel'].append(_studio_accel_row)"
    )
    lines.append(
        "        _studio_node_history['reaction'].append("
        "_studio_reaction_row)"
    )
    lines.append("    for _studio_element in _studio_frame_history_tags:")
    lines.append("        try:")
    lines.append(
        "            _studio_local = ops.eleResponse("
        "_studio_element, 'localForce') or []"
    )
    lines.append(
        "            _studio_local = [float(v) for v in _studio_local]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_local = []")
    lines.append(
        "        _studio_results['history']['element_local_forces']"
        "[str(_studio_element)].append(_studio_local)"
    )
    lines.append("    for _studio_element in _studio_shell_force_history_tags:")
    lines.append("        _studio_gp_rows = []")
    lines.append("        for _studio_gp in range(1, 5):")
    lines.append("            try:")
    lines.append(
        "                _studio_row = ops.eleResponse("
        "_studio_element, 'material', _studio_gp, 'force') or []"
    )
    lines.append(
        "                _studio_row = [float(v) for v in _studio_row]"
    )
    lines.append("            except Exception:")
    lines.append("                _studio_row = []")
    lines.append("            _studio_gp_rows.append(_studio_row)")
    lines.append(
        "        _studio_valid_rows = ["
        "row for row in _studio_gp_rows if len(row) >= 8]"
    )
    lines.append("        _studio_average = []")
    lines.append("        if _studio_valid_rows:")
    lines.append(
        "            _studio_average = ["
        "sum(row[index] for row in _studio_valid_rows) "
        "/ len(_studio_valid_rows) for index in range(8)]"
    )
    lines.append(
        "        _studio_results['history']['shell_section_forces']"
        "[str(_studio_element)].append(_studio_average)"
    )
    lines.append(
        "    for _studio_element in _studio_shell_deformation_history_tags:"
    )
    lines.append("        _studio_gp_rows = []")
    lines.append("        for _studio_gp in range(1, 5):")
    lines.append("            try:")
    lines.append(
        "                _studio_row = ops.eleResponse("
        "_studio_element, 'material', _studio_gp, 'deformation') or []"
    )
    lines.append(
        "                _studio_row = [float(v) for v in _studio_row]"
    )
    lines.append("            except Exception:")
    lines.append("                _studio_row = []")
    lines.append("            _studio_gp_rows.append(_studio_row)")
    lines.append(
        "        _studio_valid_rows = ["
        "row for row in _studio_gp_rows if len(row) >= 8]"
    )
    lines.append("        _studio_average = []")
    lines.append("        if _studio_valid_rows:")
    lines.append(
        "            _studio_average = ["
        "sum(row[index] for row in _studio_valid_rows) "
        "/ len(_studio_valid_rows) for index in range(8)]"
    )
    lines.append(
        "        _studio_results['history']['shell_section_deformations']"
        "[str(_studio_element)].append(_studio_average)"
    )
    lines.append("    for _studio_element in _studio_masonry_history_tags:")
    lines.append("        _studio_key = str(_studio_element)")
    lines.append(
        "        _studio_masonry = "
        "_studio_results['history']['masonry'][_studio_key]"
    )
    lines.append("        try:")
    lines.append(
        "            _studio_shear = ops.eleResponse("
        "_studio_element, 'Shear') or []"
    )
    lines.append(
        "            _studio_shear = [float(v) for v in _studio_shear[:2]]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_shear = []")
    lines.append("        try:")
    lines.append(
        "            _studio_strut_forces = ops.eleResponse("
        "_studio_element, 'localForce') or []"
    )
    lines.append(
        "            _studio_strut_forces = "
        "[float(v) for v in _studio_strut_forces[:6]]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_strut_forces = []")
    lines.append("        try:")
    lines.append(
        "            _studio_strut_strains = ops.eleResponse("
        "_studio_element, 'deformation') or []"
    )
    lines.append(
        "            _studio_strut_strains = "
        "[float(v) for v in _studio_strut_strains[:6]]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_strut_strains = []")
    lines.append(
        "        _studio_masonry['shear'].append(_studio_shear)"
    )
    lines.append(
        "        _studio_masonry['strut_forces'].append("
        "_studio_strut_forces)"
    )
    lines.append(
        "        _studio_masonry['strut_strains'].append("
        "_studio_strut_strains)"
    )
    lines.append(
        "    for _studio_mefi_tag, _studio_mefi_spec in "
        "_studio_mefi_crack_specs.items():"
    )
    lines.append(
        "        _studio_mefi_key = str(int(_studio_mefi_tag))"
    )
    lines.append(
        "        _studio_mefi_history = "
        "_studio_results['history']['mefi_panel_strains']"
        ".get(_studio_mefi_key, {})"
    )
    lines.append(
        "        for _studio_panel in "
        "_studio_mefi_spec.get('panels', []):"
    )
    lines.append(
        "            _studio_panel_no = int(_studio_panel.get('panel', 0))"
    )
    lines.append(
        "            _studio_panel_key = str(_studio_panel_no)"
    )
    lines.append("            try:")
    lines.append(
        "                _studio_panel_strain = ops.eleResponse("
        "int(_studio_mefi_tag), 'RCPanel', _studio_panel_no, "
        "'panel_strain') or []"
    )
    lines.append(
        "                _studio_panel_strain = "
        "[float(v) for v in _studio_panel_strain[:3]]"
    )
    lines.append("            except Exception:")
    lines.append("                _studio_panel_strain = []")
    lines.append(
        "            if _studio_panel_key in _studio_mefi_history:"
    )
    lines.append(
        "                _studio_mefi_history[_studio_panel_key].append("
        "_studio_panel_strain)"
    )
    lines.append(
        "    _studio_disp = "
        "[float(v) for v in ops.nodeDisp(_studio_monitor_node)]"
    )
    lines.append(
        "    _studio_results['history']['displacement'].append(_studio_disp)"
    )
    lines.append("    if _studio_moment_curvature_spec:")
    lines.append(
        "        _studio_mc_history = "
        "_studio_results['history']['moment_curvature']"
    )
    lines.append(
        "        _studio_mc_element = "
        "int(_studio_moment_curvature_spec.get('element_tag', 0))"
    )
    lines.append("        try:")
    lines.append(
        "            _studio_mc_force = ops.eleResponse("
        "_studio_mc_element, 'section', 'force') or []"
    )
    lines.append(
        "            _studio_mc_force = "
        "[float(v) for v in _studio_mc_force]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_mc_force = []")
    lines.append("        try:")
    lines.append(
        "            _studio_mc_def = ops.eleResponse("
        "_studio_mc_element, 'section', 'deformation') or []"
    )
    lines.append(
        "            _studio_mc_def = [float(v) for v in _studio_mc_def]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_mc_def = []")
    lines.append(
        "        _studio_mc_history['force'].append(_studio_mc_force)"
    )
    lines.append(
        "        _studio_mc_history['deformation'].append(_studio_mc_def)"
    )
    lines.append("    for _studio_sr_key, _studio_sr_spec in _studio_section_response_specs.items():")
    lines.append(
        "        _studio_sr_history = "
        "_studio_results['history']['section_responses'][_studio_sr_key]"
    )
    lines.append(
        "        _studio_sr_element = int(_studio_sr_spec.get('element_tag', 0))"
    )
    lines.append(
        "        _studio_sr_section = int(_studio_sr_spec.get('section_number', 1))"
    )
    lines.append(
        "        _studio_sr_direct = "
        "_studio_sr_spec.get('query_mode') == 'direct'"
    )
    lines.append("        try:")
    lines.append(
        "            _studio_sr_force = (ops.eleResponse("
        "_studio_sr_element, 'section', 'force') if _studio_sr_direct "
        "else ops.eleResponse(_studio_sr_element, 'section', "
        "_studio_sr_section, 'force')) or []"
    )
    lines.append(
        "            _studio_sr_force = [float(v) for v in _studio_sr_force]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_sr_force = []")
    lines.append("        try:")
    lines.append(
        "            _studio_sr_def = (ops.eleResponse("
        "_studio_sr_element, 'section', 'deformation') if _studio_sr_direct "
        "else ops.eleResponse(_studio_sr_element, 'section', "
        "_studio_sr_section, 'deformation')) or []"
    )
    lines.append(
        "            _studio_sr_def = [float(v) for v in _studio_sr_def]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_sr_def = []")
    lines.append(
        "        _studio_sr_history['force'].append(_studio_sr_force)"
    )
    lines.append(
        "        _studio_sr_history['deformation'].append(_studio_sr_def)"
    )
    lines.append(
        "    for _studio_joint_key, _studio_joint_spec in "
        "_studio_joint_response_specs.items():"
    )
    lines.append(
        "        _studio_joint_history = "
        "_studio_results['history']['joints'][_studio_joint_key]"
    )
    lines.append(
        "        _studio_joint_tag = int(_studio_joint_key)"
    )
    lines.append(
        "        for _studio_joint_response in "
        "_studio_joint_spec.get('responses', []):"
    )
    lines.append("            try:")
    lines.append(
        "                if ("
        "_studio_joint_spec.get('connection_type') == 'BeamColumnJoint' "
        "and _studio_joint_response in "
        + repr(sorted(BEAM_COLUMN_JOINT_COMPONENT_RESPONSES))
        + "):"
    )
    lines.append(
        "                    _studio_joint_value = ops.eleResponse("
        "_studio_joint_tag, _studio_joint_response, 'stressStrain')"
    )
    lines.append("                else:")
    lines.append(
        "                    _studio_joint_value = ops.eleResponse("
        "_studio_joint_tag, _studio_joint_response)"
    )
    lines.append(
        "                if isinstance(_studio_joint_value, (list, tuple)):"
    )
    lines.append(
        "                    _studio_joint_row = "
        "[float(v) for v in _studio_joint_value]"
    )
    lines.append("                elif _studio_joint_value is None:")
    lines.append("                    _studio_joint_row = []")
    lines.append("                else:")
    lines.append(
        "                    _studio_joint_row = [float(_studio_joint_value)]"
    )
    lines.append("            except Exception:")
    lines.append("                _studio_joint_row = []")
    lines.append(
        "            _studio_joint_history['responses']"
        "[_studio_joint_response].append(_studio_joint_row)"
    )
    lines.append("    if _studio_specimen_response_spec:")
    lines.append(
        "        _studio_specimen_history = "
        "_studio_results['history']['specimen']"
    )
    lines.append(
        "        _studio_specimen_element = "
        "int(_studio_specimen_response_spec.get('element_tag', 0))"
    )
    lines.append(
        "        _studio_specimen_section = "
        "int(_studio_specimen_response_spec.get('section_number', 1))"
    )
    lines.append("        try:")
    lines.append(
        "            _studio_sec_force = ops.eleResponse("
        "_studio_specimen_element, 'section', "
        "_studio_specimen_section, 'force') or []"
    )
    lines.append(
        "            _studio_sec_force = "
        "[float(v) for v in _studio_sec_force]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_sec_force = []")
    lines.append("        try:")
    lines.append(
        "            _studio_sec_def = ops.eleResponse("
        "_studio_specimen_element, 'section', "
        "_studio_specimen_section, 'deformation') or []"
    )
    lines.append(
        "            _studio_sec_def = [float(v) for v in _studio_sec_def]"
    )
    lines.append("        except Exception:")
    lines.append("            _studio_sec_def = []")
    lines.append(
        "        _studio_specimen_history['section_force'].append("
        "_studio_sec_force)"
    )
    lines.append(
        "        _studio_specimen_history['section_deformation'].append("
        "_studio_sec_def)"
    )
    lines.append("        _studio_base_fiber_rows = []")
    lines.append(
        "        for _studio_fiber in "
        "_studio_specimen_response_spec.get('base_fibers', []):"
    )
    lines.append("            _studio_y = float(_studio_fiber.get('y', 0.0))")
    lines.append("            _studio_z = float(_studio_fiber.get('z', 0.0))")
    lines.append(
        "            _studio_mat = int(_studio_fiber.get('material_tag', 0))"
    )
    lines.append("            try:")
    lines.append(
        "                _studio_ss = ops.eleResponse("
        "_studio_specimen_element, 'section', "
        "_studio_specimen_section, 'fiber', "
        "_studio_y, _studio_z, _studio_mat, 'stressStrain') or []"
    )
    lines.append("                _studio_ss = [float(v) for v in _studio_ss]")
    lines.append("            except Exception:")
    lines.append("                _studio_ss = []")
    lines.append("            _studio_base_fiber_rows.append({")
    lines.append(
        "                **dict(_studio_fiber), "
        "'stress': float(_studio_ss[0]) if len(_studio_ss) >= 1 else None, "
        "'strain': float(_studio_ss[1]) if len(_studio_ss) >= 2 else None"
    )
    lines.append("            })")
    lines.append(
        "        _studio_specimen_history['base_fibers'].append("
        "_studio_base_fiber_rows)"
    )
    lines.append(
        "        _studio_interface_tag = "
        "_studio_specimen_response_spec.get('interface_tag')"
    )
    lines.append("        _studio_interface_force = []")
    lines.append("        _studio_interface_def = []")
    lines.append("        _studio_interface_fiber_rows = []")
    lines.append("        if _studio_interface_tag is not None:")
    lines.append("            _studio_interface_tag = int(_studio_interface_tag)")
    lines.append("            try:")
    lines.append(
        "                _studio_if_force = ops.eleResponse("
        "_studio_interface_tag, 'section', 'force') or []"
    )
    lines.append(
        "                _studio_interface_force = "
        "[float(v) for v in _studio_if_force]"
    )
    lines.append("            except Exception:")
    lines.append("                _studio_interface_force = []")
    lines.append("            try:")
    lines.append(
        "                _studio_if_def = ops.eleResponse("
        "_studio_interface_tag, 'section', 'deformation') or []"
    )
    lines.append(
        "                _studio_interface_def = "
        "[float(v) for v in _studio_if_def]"
    )
    lines.append("            except Exception:")
    lines.append("                _studio_interface_def = []")
    lines.append(
        "            for _studio_fiber in "
        "_studio_specimen_response_spec.get('interface_fibers', []):"
    )
    lines.append(
        "                _studio_y = float(_studio_fiber.get('y', 0.0))"
    )
    lines.append(
        "                _studio_z = float(_studio_fiber.get('z', 0.0))"
    )
    lines.append(
        "                _studio_mat = int(_studio_fiber.get('material_tag', 0))"
    )
    lines.append("                try:")
    lines.append(
        "                    _studio_ss = ops.eleResponse("
        "_studio_interface_tag, 'section', 'fiber', "
        "_studio_y, _studio_z, _studio_mat, 'stressStrain') or []"
    )
    lines.append(
        "                    _studio_ss = [float(v) for v in _studio_ss]"
    )
    lines.append("                except Exception:")
    lines.append("                    _studio_ss = []")
    lines.append("                _studio_interface_fiber_rows.append({")
    lines.append(
        "                    **dict(_studio_fiber), "
        "'stress': float(_studio_ss[0]) if len(_studio_ss) >= 1 else None, "
        "'slip': float(_studio_ss[1]) if len(_studio_ss) >= 2 else None"
    )
    lines.append("                })")
    lines.append(
        "        _studio_specimen_history['interface_force'].append("
        "_studio_interface_force)"
    )
    lines.append(
        "        _studio_specimen_history['interface_deformation'].append("
        "_studio_interface_def)"
    )
    lines.append(
        "        _studio_specimen_history['interface_fibers'].append("
        "_studio_interface_fiber_rows)"
    )
    lines.append(
        f"    _studio_monitor = "
        f"float(_studio_disp[{settings.control_dof - 1}]) "
        f"if len(_studio_disp) >= {settings.control_dof} else 0.0"
    )
    lines.append(
        "    if _studio_step_no == 1 or "
        f"_studio_step_no == {total_steps} or "
        f"_studio_step_no % {ui_stride} == 0:"
    )
    lines.append(
        "        _studio_emit('progress', step=_studio_step_no, "
        f"total={total_steps}, "
        f"percent=100.0 * _studio_step_no / {total_steps}, "
        "algorithm=_studio_active_algorithm, "
        "iterations=_studio_iterations, norm=_studio_norm, "
        "time=_studio_time, monitor=_studio_monitor, "
        "base_shear=_studio_base)"
    )

    if settings.analysis_type == "Transient":
        lines.append("ops.reactions('-dynamic', '-rayleigh')")
    else:
        lines.append("ops.reactions()")
    lines.extend([
        "_studio_final_disp = {}",
        "_studio_final_reaction = {}",
        "for _studio_node in _studio_node_tags:",
        "    _studio_final_disp[str(_studio_node)] = "
        "[float(v) for v in ops.nodeDisp(_studio_node)]",
        "    _studio_final_reaction[str(_studio_node)] = "
        "[float(v) for v in ops.nodeReaction(_studio_node)]",
        "_studio_element_forces = {}",
        "for _studio_element in _studio_element_tags:",
        "    try:",
        "        _studio_element_forces[str(_studio_element)] = "
        "[float(v) for v in ops.eleForce(_studio_element)]",
        "    except Exception:",
        "        _studio_element_forces[str(_studio_element)] = []",
        "_studio_element_axial_forces = {}",
        "for _studio_element in _studio_truss_element_tags:",
        "    try:",
        "        _studio_axial = ops.eleResponse(",
        "            _studio_element, 'axialForce'",
        "        )",
        "        if isinstance(_studio_axial, (list, tuple)):",
        "            _studio_axial = _studio_axial[0] if _studio_axial else None",
        "        _studio_element_axial_forces[str(_studio_element)] = (",
        "            None if _studio_axial is None else float(_studio_axial)",
        "        )",
        "    except Exception:",
        "        _studio_element_axial_forces[str(_studio_element)] = None",
        "_studio_element_local_forces = {}",
        "_studio_element_section_forces = {}",
        "for _studio_element in _studio_frame_element_tags:",
        "    try:",
        "        _studio_local = ops.eleResponse("
        "_studio_element, 'localForce')",
        "        _studio_element_local_forces[str(_studio_element)] = "
        "[float(v) for v in (_studio_local or [])]",
        "    except Exception:",
        "        _studio_element_local_forces[str(_studio_element)] = []",
        "    try:",
        "        _studio_locs = ops.eleResponse("
        "_studio_element, 'integrationPoints') or []",
        "        _studio_wts = ops.eleResponse("
        "_studio_element, 'integrationWeights') or []",
        "        if not isinstance(_studio_locs, (list, tuple)):",
        "            _studio_locs = [_studio_locs]",
        "        if not isinstance(_studio_wts, (list, tuple)):",
        "            _studio_wts = [_studio_wts]",
        "        _studio_sec_forces = []",
        "        for _studio_sec_no in range(1, len(_studio_locs) + 1):",
        "            try:",
        "                _studio_sec = ops.eleResponse("
        "_studio_element, 'section', _studio_sec_no, 'force') or []",
        "                _studio_sec_forces.append("
        "[float(v) for v in _studio_sec])",
        "            except Exception:",
        "                _studio_sec_forces.append([])",
        "        if _studio_locs:",
        "            _studio_element_section_forces[str(_studio_element)] = {",
        "                'locations': [float(v) for v in _studio_locs],",
        "                'weights': [float(v) for v in _studio_wts],",
        "                'forces': _studio_sec_forces,",
        "            }",
        "    except Exception:",
        "        pass",
        "_studio_shell_section_forces = {}",
        "_studio_shell_section_deformations = {}",
        "for _studio_element in _studio_shell_element_tags:",
        "    _studio_gp_forces = []",
        "    _studio_gp_deformations = []",
        "    for _studio_gp in range(1, 5):",
        "        try:",
        "            _studio_force = ops.eleResponse(",
        "                _studio_element, 'material', _studio_gp, 'force'",
        "            ) or []",
        "            _studio_force = [float(v) for v in _studio_force]",
        "        except Exception:",
        "            _studio_force = []",
        "        _studio_gp_forces.append(_studio_force)",
        "        try:",
        "            _studio_deformation = ops.eleResponse(",
        "                _studio_element, 'material', _studio_gp, 'deformation'",
        "            ) or []",
        "            _studio_deformation = [",
        "                float(v) for v in _studio_deformation",
        "            ]",
        "        except Exception:",
        "            _studio_deformation = []",
        "        _studio_gp_deformations.append(_studio_deformation)",
        "    _studio_valid_gp = [",
        "        row for row in _studio_gp_forces if len(row) >= 8",
        "    ]",
        "    _studio_average = []",
        "    if _studio_valid_gp:",
        "        _studio_average = [",
        "            sum(row[index] for row in _studio_valid_gp)",
        "            / len(_studio_valid_gp)",
        "            for index in range(8)",
        "        ]",
        "    _studio_shell_section_forces[str(_studio_element)] = {",
        "        'gauss_points': _studio_gp_forces,",
        "        'average': _studio_average,",
        "        'components': [",
        "            'Nxx', 'Nyy', 'Nxy', 'Mxx', 'Myy', 'Mxy', 'Qx', 'Qy'",
        "        ],",
        "    }",
        "    _studio_valid_def = [",
        "        row for row in _studio_gp_deformations if len(row) >= 8",
        "    ]",
        "    _studio_average_def = []",
        "    if _studio_valid_def:",
        "        _studio_average_def = [",
        "            sum(row[index] for row in _studio_valid_def)",
        "            / len(_studio_valid_def)",
        "            for index in range(8)",
        "        ]",
        "    _studio_shell_section_deformations[str(_studio_element)] = {",
        "        'gauss_points': _studio_gp_deformations,",
        "        'average': _studio_average_def,",
        "        'components': [",
        "            'Exx', 'Eyy', 'Gxy', 'Kxx', 'Kyy', 'Kxy', 'Gxz', 'Gyz'",
        "        ],",
        "    }",
        "_studio_mefi_panel_strains = {}",
        "for _studio_mefi_tag, _studio_mefi_spec in _studio_mefi_crack_specs.items():",
        "    _studio_mefi_key = str(int(_studio_mefi_tag))",
        "    _studio_mefi_panel_strains[_studio_mefi_key] = {}",
        "    for _studio_panel in _studio_mefi_spec.get('panels', []):",
        "        _studio_panel_no = int(_studio_panel.get('panel', 0))",
        "        try:",
        "            _studio_panel_strain = ops.eleResponse(",
        "                int(_studio_mefi_tag), 'RCPanel', _studio_panel_no,",
        "                'panel_strain'",
        "            ) or []",
        "            _studio_panel_strain = [",
        "                float(v) for v in _studio_panel_strain[:3]",
        "            ]",
        "        except Exception:",
        "            _studio_panel_strain = []",
        "        _studio_mefi_panel_strains[_studio_mefi_key][",
        "            str(_studio_panel_no)",
        "        ] = _studio_panel_strain",
        "_studio_element_fiber_responses = {}",
        "for _studio_element_raw, _studio_spec in "
        "_studio_fiber_response_specs.items():",
        "    _studio_element = int(_studio_element_raw)",
        "    _studio_section_tag = int(_studio_spec.get('section_tag', 0))",
        "    _studio_locations = list(_studio_spec.get('locations', []))",
        "    try:",
        "        _studio_actual_locations = ops.eleResponse(",
        "            _studio_element, 'integrationPoints'",
        "        ) or []",
        "        if not isinstance(_studio_actual_locations, (list, tuple)):",
        "            _studio_actual_locations = [_studio_actual_locations]",
        "        if _studio_actual_locations:",
        "            _studio_locations = [float(v) for v in _studio_actual_locations]",
        "    except Exception:",
        "        pass",
        "    _studio_fibers = list(_studio_spec.get('fibers', []))",
        "    _studio_sections = []",
        "    for _studio_sec_no, _studio_location in "
        "enumerate(_studio_locations, start=1):",
        "        _studio_fiber_rows = []",
        "        for _studio_fiber in _studio_fibers:",
        "            _studio_y = float(_studio_fiber.get('y', 0.0))",
        "            _studio_z = float(_studio_fiber.get('z', 0.0))",
        "            _studio_area = float(_studio_fiber.get('area', 0.0))",
        "            _studio_mat = int(_studio_fiber.get('material_tag', 0))",
        "            try:",
        "                _studio_ss = ops.eleResponse(",
        "                    _studio_element, 'section', _studio_sec_no,",
        "                    'fiber', _studio_y, _studio_z, _studio_mat,",
        "                    'stressStrain'",
        "                ) or []",
        "                _studio_ss = [float(v) for v in _studio_ss]",
        "            except Exception:",
        "                _studio_ss = []",
        "            _studio_fiber_rows.append({",
        "                'y': _studio_y, 'z': _studio_z,",
        "                'area': _studio_area, 'material_tag': _studio_mat,",
        "                'stress': (",
        "                    float(_studio_ss[0])",
        "                    if len(_studio_ss) >= 1 else None",
        "                ),",
        "                'strain': (",
        "                    float(_studio_ss[1])",
        "                    if len(_studio_ss) >= 2 else None",
        "                ),",
        "            })",
        "        _studio_sections.append({",
        "            'number': _studio_sec_no,",
        "            'location': float(_studio_location),",
        "            'fibers': _studio_fiber_rows,",
        "        })",
        "    _studio_element_fiber_responses[str(_studio_element)] = {",
        "        'section_tag': _studio_section_tag,",
        "        'sections': _studio_sections,",
        "    }",
        "_studio_masonry_responses = {}",
        "for _studio_element in _studio_masonry_history_tags:",
        "    _studio_key = str(_studio_element)",
        "    try:",
        "        _studio_shear = ops.eleResponse(_studio_element, 'Shear') or []",
        "        _studio_shear = [float(v) for v in _studio_shear[:2]]",
        "    except Exception:",
        "        _studio_shear = []",
        "    try:",
        "        _studio_strut_forces = ops.eleResponse(",
        "            _studio_element, 'localForce'",
        "        ) or []",
        "        _studio_strut_forces = [",
        "            float(v) for v in _studio_strut_forces[:6]",
        "        ]",
        "    except Exception:",
        "        _studio_strut_forces = []",
        "    try:",
        "        _studio_strut_strains = ops.eleResponse(",
        "            _studio_element, 'deformation'",
        "        ) or []",
        "        _studio_strut_strains = [",
        "            float(v) for v in _studio_strut_strains[:6]",
        "        ]",
        "    except Exception:",
        "        _studio_strut_strains = []",
        "    _studio_masonry_responses[_studio_key] = {",
        "        'shear': _studio_shear,",
        "        'strut_forces': _studio_strut_forces,",
        "        'strut_strains': _studio_strut_strains,",
        "    }",
        "_studio_load_factors = {}",
        "for _studio_pattern in _studio_plain_pattern_tags:",
        "    try:",
        "        _studio_load_factors[str(_studio_pattern)] = "
        "float(ops.getLoadFactor(_studio_pattern))",
        "    except Exception:",
        "        pass",
        "_studio_results['final'] = {",
        "    'node_displacements': _studio_final_disp,",
        "    'node_reactions': _studio_final_reaction,",
        "    'element_forces': _studio_element_forces,",
        "    'element_axial_forces': _studio_element_axial_forces,",
        "    'element_local_forces': _studio_element_local_forces,",
        "    'element_section_forces': _studio_element_section_forces,",
        "    'shell_section_forces': _studio_shell_section_forces,",
        "    'shell_section_deformations': _studio_shell_section_deformations,",
        "    'mefi_panel_strains': _studio_mefi_panel_strains,",
        "    'masonry': _studio_masonry_responses,",
        "    'element_fiber_responses': _studio_element_fiber_responses,",
        "    'load_factors': _studio_load_factors,",
        "}",
        "print('Analysis completed:', "
        f"{settings.analysis_type!r}, {total_steps}, 'step(s)')",
    ])
    return lines

def transformation_to_openseespy(
    transformation: TransformationData,
    ndm: int = 3,
    model: StructuralModel | None = None,
) -> str:
    if transformation.transformation_type == "LinearInt":
        if int(ndm) != 2:
            raise ValueError(
                "LinearInt geometric transformation is available only in 2D."
            )
        return f"ops.geomTransf('LinearInt', {transformation.tag})"
    if int(ndm) == 2:
        return (
            f"ops.geomTransf('{transformation.transformation_type}', "
            f"{transformation.tag})"
        )
    effective = (
        resolve_transformation_vecxz(model, transformation)
        if model is not None
        else transformation.vecxz
    )
    x, y, z = effective
    return (
        f"ops.geomTransf('{transformation.transformation_type}', "
        f"{transformation.tag}, {x:g}, {y:g}, {z:g})"
    )



def build_mefi_crack_specs(
    model: StructuralModel,
    *,
    sections: dict[int, SectionData] | None,
    nd_materials: dict[int, NDMaterialData] | None,
) -> dict[int, dict[str, object]]:
    """Describe MEFI RC panels and their concrete cracking thresholds.

    RCLMS exposes panel_strain for each MEFI RCPanel. The concrete
    OrthotropicRAConcrete.ecr parameter is the model tensile cracking strain,
    so SARE retains it per macro-fiber instead of inventing a GUI-only
    threshold.
    """
    section_map = sections or {}
    material_map = nd_materials or {}
    specs: dict[int, dict[str, object]] = {}

    for tag, element in sorted(model.elements.items()):
        if element.element_type != "MEFI":
            continue
        widths = list(element.mefi_widths)
        section_tags = list(element.mefi_section_tags)
        if not widths or len(widths) != len(section_tags):
            continue

        panels: list[dict[str, object]] = []
        for panel_no, (width, section_tag) in enumerate(
            zip(widths, section_tags),
            start=1,
        ):
            threshold_values: list[float] = []
            section = section_map.get(int(section_tag))
            if section is not None and section.section_type == "RCLMS":
                for layer in section.shell_layers:
                    material = material_map.get(int(layer.material_tag))
                    if (
                        material is not None
                        and material.material_type == "OrthotropicRAConcrete"
                    ):
                        ecr = float(material.parameters.get("ecr", 0.0))
                        if ecr > 0.0 and math.isfinite(ecr):
                            threshold_values.append(ecr)

            panels.append({
                "panel": int(panel_no),
                "width": float(width),
                "section_tag": int(section_tag),
                "cracking_strain": (
                    min(threshold_values) if threshold_values else None
                ),
            })

        if panels:
            specs[int(tag)] = {
                "source": "MEFI RCPanel panel_strain",
                "panels": panels,
            }

    return specs


def build_joint_response_specs(
    *,
    connections: dict[int, ConnectionData] | None,
    solution_results: dict[int, object] | None,
    active_analysis: AnalysisSettingsData | None,
) -> dict[int, dict[str, object]]:
    """Return only joint histories explicitly requested for this analysis."""
    if active_analysis is None:
        return {}
    requested: dict[int, set[str]] = {}
    connection_map = connections or {}

    pair_map = {
        "force": "deformation",
        "deformation": "force",
        "basicForce": "basicDisplacement",
        "basicDisplacement": "basicForce",
        "localForce": "localDisplacement",
        "localDisplacement": "localForce",
        "basicForces": "Deformation",
        "Deformation": "basicForces",
    }

    for result in (solution_results or {}).values():
        if str(getattr(result, "result_type", "")) != "JointResponse":
            continue
        if int(getattr(result, "analysis_tag", -1)) != int(active_analysis.tag):
            continue
        scope = list(getattr(result, "element_scope", ()) or ())
        if len(scope) != 1:
            continue
        connection_tag = int(scope[0])
        connection = connection_map.get(connection_tag)
        if connection is None:
            continue
        settings = dict(getattr(result, "settings", {}) or {})
        default_response = (
            "force"
            if connection.connection_type == "CoupledZeroLength"
            else "deformation"
        )
        response = str(settings.get("response", default_response))
        allowed = CONNECTION_HISTORY_RESPONSES.get(
            connection.connection_type,
            (),
        )
        if response not in allowed:
            continue
        response_set = requested.setdefault(connection_tag, set())
        response_set.add(response)

        if str(settings.get("curve_mode", "history")) == "force_deformation":
            paired = pair_map.get(response)
            if paired in allowed:
                response_set.add(str(paired))

    return {
        tag: {
            "connection_type": connection_map[tag].connection_type,
            "responses": [
                response
                for response in CONNECTION_HISTORY_RESPONSES.get(
                    connection_map[tag].connection_type,
                    (),
                )
                if response in responses
            ],
        }
        for tag, responses in sorted(requested.items())
    }


def friction_model_to_openseespy(
    model: FrictionModelData,
    units: dict[str, str] | None = None,
) -> str:
    p = model.parameters
    if model.friction_type == "Coulomb":
        return (
            "ops.frictionModel('Coulomb', "
            f"{model.tag}, {float(p['mu']):g})"
        )
    if model.friction_type == "VelDependent":
        unit_system = UnitSystem.from_mapping(units)
        trans_rate = (
            float(p["transRate"])
            * unit_system.length_to_m
            / unit_system.time_to_s
        )
        return (
            "ops.frictionModel('VelDependent', "
            f"{model.tag}, {float(p['muSlow']):g}, "
            f"{float(p['muFast']):g}, {trans_rate:g})"
        )
    raise ValueError(
        f"Unsupported friction model type: {model.friction_type}"
    )


def to_openseespy(
    model: StructuralModel,
    materials: dict[int, MaterialData] | None = None,
    sections: dict[int, SectionData] | None = None,
    transformations: dict[int, TransformationData] | None = None,
    constraints: dict[int, ConstraintData] | None = None,
    connections: dict[int, ConnectionData] | None = None,
    time_series: dict[int, TimeSeriesData] | None = None,
    load_patterns: dict[int, LoadPatternData] | None = None,
    nodal_loads: dict[int, NodalLoadData] | None = None,
    analyses: dict[int, AnalysisSettingsData] | None = None,
    active_analysis_tag: int | None = None,
    element_loads: dict[int, ElementLoadData] | None = None,
    prescribed_displacements: dict[int, PrescribedDisplacementData] | None = None,
    recorders: dict[int, RecorderData] | None = None,
    units: dict[str, str] | None = None,
    solution_results: dict[int, object] | None = None,
    nd_materials: dict[int, NDMaterialData] | None = None,
    friction_models: dict[int, FrictionModelData] | None = None,
) -> str:
    active_analysis = (
        analyses.get(active_analysis_tag)
        if analyses and active_analysis_tag in analyses
        else None
    )
    deferred_pattern_tags = set(
        active_analysis.deferred_pattern_tags
        if active_analysis is not None
        else []
    )
    other_analysis_driver_tags: set[int] = set()
    if analyses and active_analysis is not None:
        for analysis_tag, analysis in analyses.items():
            if (
                active_analysis_tag is not None
                and int(analysis_tag) == int(active_analysis_tag)
            ):
                continue
            other_analysis_driver_tags.update(
                int(tag) for tag in analysis.deferred_pattern_tags
            )
    scoped_deferred_analysis = bool(
        active_analysis is not None and deferred_pattern_tags
    )

    geometry_reference_errors: list[str] = []

    duplicate_element_tags = sorted(
        set(model.elements) & set((connections or {}).keys())
    )
    if duplicate_element_tags:
        geometry_reference_errors.append(
            "duplicate OpenSees element tag(s) shared by frame/truss and "
            "connection: "
            + ", ".join(map(str, duplicate_element_tags))
        )

    for element in model.elements.values():
        element_nodes = tuple(int(tag) for tag in element.node_tags())
        missing = [
            tag
            for tag in element_nodes
            if tag not in model.nodes
        ]
        if missing:
            geometry_reference_errors.append(
                f"element {element.tag} -> missing node "
                + ", ".join(map(str, sorted(set(missing))))
            )
        elif element.element_type in SHELL_ELEMENT_TYPES:
            if (int(model.ndm), int(model.ndf)) != (3, 6):
                geometry_reference_errors.append(
                    f"shell element {element.tag} -> requires ndm=3, ndf=6"
                )
            points = [
                tuple(float(value) for value in model.nodes[tag].xyz)
                for tag in element_nodes
            ]

            def _triangle_area2(a, b, c):
                ab = tuple(b[i] - a[i] for i in range(3))
                ac = tuple(c[i] - a[i] for i in range(3))
                cross = (
                    ab[1] * ac[2] - ab[2] * ac[1],
                    ab[2] * ac[0] - ab[0] * ac[2],
                    ab[0] * ac[1] - ab[1] * ac[0],
                )
                return math.sqrt(sum(value * value for value in cross))

            area2 = _triangle_area2(points[0], points[1], points[2])
            area2 += _triangle_area2(points[0], points[2], points[3])
            if area2 <= 1.0e-12:
                geometry_reference_errors.append(
                    f"shell element {element.tag} -> zero area"
                )
        else:
            node_i = model.nodes[int(element.i)]
            node_j = model.nodes[int(element.j)]
            length2 = sum(
                (
                    float(node_j.xyz[index])
                    - float(node_i.xyz[index])
                ) ** 2
                for index in range(3)
            )
            if (
                length2 <= 1.0e-24
                and element.element_type not in (
                    BEARING_ELEMENT_TYPES | CONTACT_TWO_NODE_ELEMENT_TYPES
                )
            ):
                geometry_reference_errors.append(
                    f"element {element.tag} -> zero length"
                )

    for connection in (connections or {}).values():
        missing = [
            int(tag)
            for tag in (connection.node_i, connection.node_j)
            if int(tag) not in model.nodes
        ]
        if missing:
            geometry_reference_errors.append(
                f"connection {connection.tag} -> missing node "
                + ", ".join(map(str, sorted(set(missing))))
            )

    valid_element_targets = set(model.elements) | set(
        (connections or {}).keys()
    )
    for recorder in (recorders or {}).values():
        if recorder.recorder_type == "Node":
            missing = sorted(
                int(tag)
                for tag in recorder.target_tags
                if int(tag) not in model.nodes
            )
            if missing:
                geometry_reference_errors.append(
                    f"node recorder {recorder.tag} -> missing node "
                    + ", ".join(map(str, missing))
                )
        else:
            missing = sorted(
                int(tag)
                for tag in recorder.target_tags
                if int(tag) not in valid_element_targets
            )
            if missing:
                geometry_reference_errors.append(
                    f"{recorder.recorder_type.lower()} recorder "
                    f"{recorder.tag} -> missing element "
                    + ", ".join(map(str, missing))
                )

    if geometry_reference_errors:
        raise ValueError(
            "Geometry reference error(s): "
            + "; ".join(sorted(geometry_reference_errors))
            + "."
        )

    material_reference_errors: list[str] = []
    material_catalog = (
        None if materials is None else set(materials)
    )

    for material in (materials or {}).values():
        dependency_tags: list[int] = []
        if material.base_material_tag is not None:
            dependency_tags.append(int(material.base_material_tag))
        dependency_tags.extend(int(tag) for tag in material.material_tags)
        missing = sorted({
            tag for tag in dependency_tags
            if material_catalog is not None and tag not in material_catalog
        })
        if missing:
            material_reference_errors.append(
                f"material {material.tag} -> missing material "
                + ", ".join(map(str, missing))
            )

    nd_material_catalog = set(nd_materials or {})
    for element in model.elements.values():
        if element.element_type in BEAM_CONTACT_ELEMENT_TYPES:
            nd_tag = int(element.special_parameters["nd_material_tag"])
            if nd_tag not in nd_material_catalog:
                material_reference_errors.append(
                    f"{element.element_type} element {element.tag} "
                    f"-> missing nDMaterial {nd_tag}"
                )
            if (
                element.element_type == "BeamContact3D"
                and (
                    transformations is None
                    or int(element.special_parameters["transf_tag"])
                    not in transformations
                )
            ):
                material_reference_errors.append(
                    f"BeamContact3D element {element.tag} -> missing "
                    f"transformation {element.special_parameters['transf_tag']}"
                )

    for section in (sections or {}).values():
        referenced_materials: set[int] = set()
        if section.material_tag is not None:
            referenced_materials.add(int(section.material_tag))
        referenced_materials.update(
            int(tag) for tag in section.fiber_material_tags()
        )
        missing = sorted(
            tag for tag in referenced_materials
            if material_catalog is not None and tag not in material_catalog
        )
        if missing:
            material_reference_errors.append(
                f"section {section.tag} -> missing material "
                + ", ".join(map(str, missing))
            )

    for element in model.elements.values():
        if (
            element.truss_material_tag is not None
            and material_catalog is not None
            and int(element.truss_material_tag) not in material_catalog
        ):
            material_reference_errors.append(
                f"truss element {element.tag} -> missing material "
                f"{element.truss_material_tag}"
            )
        if element.element_type == "elastomericBearingPlasticity":
            referenced = {
                int(value)
                for key in (
                    "p_mat_tag", "t_mat_tag", "my_mat_tag", "mz_mat_tag"
                )
                for value in [element.special_parameters.get(key)]
                if value is not None
            }
            missing = sorted(
                tag for tag in referenced
                if material_catalog is not None and tag not in material_catalog
            )
            if missing:
                material_reference_errors.append(
                    f"bearing element {element.tag} -> missing material "
                    + ", ".join(map(str, missing))
                )
        if element.element_type == "TripleFrictionPendulum":
            referenced = {
                int(element.special_parameters[key])
                for key in (
                    "vertMatTag", "rotZMatTag",
                    "rotXMatTag", "rotYMatTag",
                )
            }
            missing = sorted(
                tag for tag in referenced
                if material_catalog is None or tag not in material_catalog
            )
            if missing:
                material_reference_errors.append(
                    f"TripleFrictionPendulum element {element.tag} "
                    "-> missing material "
                    + ", ".join(map(str, missing))
                )
            friction_catalog = set(friction_models or {})
            missing_friction = sorted(
                int(element.special_parameters[key])
                for key in ("frnTag1", "frnTag2", "frnTag3")
                if int(element.special_parameters[key]) not in friction_catalog
            )
            if missing_friction:
                material_reference_errors.append(
                    f"TripleFrictionPendulum element {element.tag} "
                    "-> missing friction model "
                    + ", ".join(map(str, missing_friction))
                )

    for connection in (connections or {}).values():
        missing = sorted({
            int(tag)
            for tag in connection.materials_by_dof.values()
            if material_catalog is not None
            and int(tag) not in material_catalog
        })
        if missing:
            material_reference_errors.append(
                f"connection {connection.tag} -> missing material "
                + ", ".join(map(str, missing))
            )

    for recorder in (recorders or {}).values():
        if (
            recorder.recorder_type == "Fiber"
            and recorder.material_tag is not None
            and material_catalog is not None
            and int(recorder.material_tag) not in material_catalog
        ):
            material_reference_errors.append(
                f"fiber recorder {recorder.tag} -> missing material "
                f"{recorder.material_tag}"
            )

    if material_reference_errors:
        raise ValueError(
            "Material reference error(s): "
            + "; ".join(sorted(material_reference_errors))
            + "."
        )

    transformation_reference_errors: list[str] = []
    transformation_catalog = (
        None if transformations is None else set(transformations)
    )
    frame_element_types = {
        "elasticBeamColumn",
        "ElasticTimoshenkoBeam",
        "forceBeamColumn",
        "dispBeamColumn",
        "dispBeamColumnInt",
    }
    for element in model.elements.values():
        if element.element_type not in frame_element_types:
            continue
        if transformation_catalog is None:
            continue
        if element.transf_tag is None:
            transformation_reference_errors.append(
                f"element {element.tag} -> no geometric transformation assigned"
            )
        elif int(element.transf_tag) not in transformation_catalog:
            transformation_reference_errors.append(
                f"element {element.tag} -> missing transformation "
                f"{element.transf_tag}"
            )
        elif int(model.ndm) == 3:
            transformation = transformations[int(element.transf_tag)]
            node_i = model.nodes[int(element.i)]
            node_j = model.nodes[int(element.j)]
            delta = tuple(
                float(node_j.xyz[index]) - float(node_i.xyz[index])
                for index in range(3)
            )
            vx, vy, vz = resolve_transformation_vecxz(
                model,
                transformation,
            )
            dx, dy, dz = delta
            cross = (
                vy * dz - vz * dy,
                vz * dx - vx * dz,
                vx * dy - vy * dx,
            )
            vec_norm2 = vx * vx + vy * vy + vz * vz
            length2 = sum(value * value for value in delta)
            cross_norm2 = sum(value * value for value in cross)
            if (
                length2 > 1.0e-24
                and cross_norm2
                <= 1.0e-16 * vec_norm2 * length2
            ):
                transformation_reference_errors.append(
                    f"element {element.tag} -> transformation "
                    f"{element.transf_tag} vecxz parallel to member axis"
                )

    if transformation_reference_errors:
        raise ValueError(
            "Geometric transformation reference error(s): "
            + "; ".join(sorted(transformation_reference_errors))
            + "."
        )

    section_reference_errors: list[str] = []
    section_catalog = None if sections is None else set(sections)
    for element in model.elements.values():
        referenced_sections = {
            int(tag)
            for tag in (
                element.section_tag,
                element.hinge_i_section_tag,
                element.hinge_j_section_tag,
                element.interior_section_tag,
            )
            if tag is not None
        }
        if element.element_type == "MEFI":
            referenced_sections.update(
                int(tag) for tag in element.mefi_section_tags
            )
        missing = sorted(
            tag for tag in referenced_sections
            if section_catalog is not None and tag not in section_catalog
        )
        if missing:
            section_reference_errors.append(
                f"element {element.tag} -> missing section "
                + ", ".join(map(str, missing))
            )

    for connection in (connections or {}).values():
        if (
            connection.connection_type == "zeroLengthSection"
            and (
                section_catalog is not None
                and (
                    connection.section_tag is None
                    or int(connection.section_tag) not in section_catalog
                )
            )
        ):
            section_reference_errors.append(
                f"connection {connection.tag} -> missing section "
                f"{connection.section_tag}"
            )

    if section_reference_errors:
        raise ValueError(
            "Section reference error(s): "
            + "; ".join(sorted(section_reference_errors))
            + "."
        )

    missing_pattern_series = {
        int(pattern.tag): int(pattern.time_series_tag)
        for pattern in (load_patterns or {}).values()
        if int(pattern.time_series_tag) not in (time_series or {})
    }
    if missing_pattern_series:
        details = "; ".join(
            f"pattern {tag} -> time series {series_tag}"
            for tag, series_tag in sorted(missing_pattern_series.items())
        )
        raise ValueError(
            "Load pattern(s) reference missing time series: "
            + details
            + "."
        )

    orphan_load_references: list[str] = []
    for load in (nodal_loads or {}).values():
        pattern = (load_patterns or {}).get(int(load.pattern_tag))
        if int(load.node_tag) not in model.nodes:
            orphan_load_references.append(
                f"nodal load {load.tag} -> missing node {load.node_tag}"
            )
        if pattern is None:
            orphan_load_references.append(
                f"nodal load {load.tag} -> missing pattern {load.pattern_tag}"
            )
        elif pattern.pattern_type != "Plain":
            orphan_load_references.append(
                f"nodal load {load.tag} -> non-Plain pattern {load.pattern_tag}"
            )

    for load in (element_loads or {}).values():
        pattern = (load_patterns or {}).get(int(load.pattern_tag))
        if int(load.element_tag) not in model.elements:
            orphan_load_references.append(
                f"element load {load.tag} -> missing element {load.element_tag}"
            )
        if pattern is None:
            orphan_load_references.append(
                f"element load {load.tag} -> missing pattern {load.pattern_tag}"
            )
        elif pattern.pattern_type != "Plain":
            orphan_load_references.append(
                f"element load {load.tag} -> non-Plain pattern {load.pattern_tag}"
            )

    for displacement in (prescribed_displacements or {}).values():
        pattern = (load_patterns or {}).get(int(displacement.pattern_tag))
        if int(displacement.node_tag) not in model.nodes:
            orphan_load_references.append(
                "prescribed displacement "
                f"{displacement.tag} -> missing node {displacement.node_tag}"
            )
        if pattern is None:
            orphan_load_references.append(
                "prescribed displacement "
                f"{displacement.tag} -> missing pattern "
                f"{displacement.pattern_tag}"
            )
        elif pattern.pattern_type != "Plain":
            orphan_load_references.append(
                "prescribed displacement "
                f"{displacement.tag} -> non-Plain pattern "
                f"{displacement.pattern_tag}"
            )

    if orphan_load_references:
        raise ValueError(
            "Load object reference error(s): "
            + "; ".join(sorted(orphan_load_references))
            + "."
        )

    missing_constraint_nodes: dict[int, list[int]] = {}
    for constraint in (constraints or {}).values():
        missing = sorted({
            int(tag)
            for tag in (
                [constraint.retained_node]
                + list(constraint.constrained_nodes)
            )
            if int(tag) not in model.nodes
        })
        if missing:
            missing_constraint_nodes[int(constraint.tag)] = missing

    if missing_constraint_nodes:
        details = "; ".join(
            f"{tag}: " + ", ".join(map(str, nodes))
            for tag, nodes in sorted(missing_constraint_nodes.items())
        )
        raise ValueError(
            "Constraint(s) reference missing model node tag(s): "
            + details
            + "."
        )

    invalid_rigid_links: list[str] = []
    for constraint in (constraints or {}).values():
        if constraint.constraint_type != "rigidLink":
            continue
        ndm = int(model.ndm)
        ndf = int(model.ndf)
        if constraint.link_type == "bar":
            if ndf < ndm:
                invalid_rigid_links.append(
                    f"{constraint.tag} (bar: ndm={ndm}, ndf={ndf})"
                )
            continue

        valid_beam_signature = (
            ndf == ndm
            or (ndm, ndf) in {(2, 3), (3, 6)}
        )
        if not valid_beam_signature:
            invalid_rigid_links.append(
                f"{constraint.tag} (beam: ndm={ndm}, ndf={ndf})"
            )

    if invalid_rigid_links:
        raise ValueError(
            "Unsupported rigidLink model signature(s): "
            + "; ".join(invalid_rigid_links)
            + ". rigidLink bar requires ndf >= ndm; rigidLink beam "
            "requires ndf == ndm, 2D/3DOF, or 3D/6DOF."
        )

    invalid_equal_dof_dofs = {
        int(constraint.tag): sorted(
            int(dof)
            for dof in constraint.dofs
            if int(dof) > int(model.ndf)
        )
        for constraint in (constraints or {}).values()
        if constraint.constraint_type == "equalDOF"
    }
    invalid_equal_dof_dofs = {
        tag: dofs
        for tag, dofs in invalid_equal_dof_dofs.items()
        if dofs
    }
    if invalid_equal_dof_dofs:
        details = "; ".join(
            f"{tag}: " + ", ".join(map(str, dofs))
            for tag, dofs in sorted(invalid_equal_dof_dofs.items())
        )
        raise ValueError(
            "equalDOF constraint DOF(s) exceed "
            f"model ndf={model.ndf} ({details})."
        )

    rigid_diaphragm_tags = sorted(
        constraint.tag
        for constraint in (constraints or {}).values()
        if constraint.constraint_type == "rigidDiaphragm"
    )
    if rigid_diaphragm_tags and (
        (int(model.ndm), int(model.ndf)) not in {(2, 3), (3, 6)}
    ):
        raise ValueError(
            "rigidDiaphragm constraint(s) "
            + ", ".join(map(str, rigid_diaphragm_tags))
            + f" require a 2D/3DOF or 3D/6DOF model; got "
            f"ndm={model.ndm}, ndf={model.ndf}."
        )

    def constraint_dependent_dofs(
        constraint: ConstraintData,
    ) -> set[int]:
        if constraint.constraint_type == "equalDOF":
            return {
                int(dof)
                for dof in constraint.dofs
                if 1 <= int(dof) <= int(model.ndf)
            }
        if constraint.constraint_type == "rigidLink":
            if constraint.link_type == "beam":
                return set(range(1, int(model.ndf) + 1))
            return set(
                range(
                    1,
                    min(int(model.ndm), int(model.ndf)) + 1,
                )
            )
        if constraint.constraint_type == "rigidDiaphragm":
            if model.ndm == 3 and model.ndf == 6:
                return {
                    1: {2, 3, 4},
                    2: {1, 3, 5},
                    3: {1, 2, 6},
                }.get(int(constraint.perp_dirn), set())
            if model.ndm == 2 and model.ndf == 3:
                return {
                    1: {1},
                    2: {2},
                    3: {1, 2, 3},
                }.get(int(constraint.perp_dirn), set())
        return set()

    dependent_owners: dict[tuple[int, int], list[int]] = {}
    support_mpc_conflicts: list[tuple[int, int, int]] = []
    for constraint in (constraints or {}).values():
        dependent_dofs = constraint_dependent_dofs(constraint)
        for node_tag in constraint.constrained_nodes:
            node_tag = int(node_tag)
            node = model.nodes.get(node_tag)
            for dof in sorted(dependent_dofs):
                dependent_owners.setdefault(
                    (node_tag, int(dof)),
                    [],
                ).append(int(constraint.tag))
                if (
                    node is not None
                    and dof <= len(node.fixity)
                    and bool(node.fixity[dof - 1])
                ):
                    support_mpc_conflicts.append(
                        (node_tag, int(dof), int(constraint.tag))
                    )

    overlapping_mpcs = {
        key: sorted(tags)
        for key, tags in dependent_owners.items()
        if len(set(tags)) > 1
    }
    if overlapping_mpcs:
        details = "; ".join(
            f"node {node_tag} DOF {dof}: "
            + ", ".join(map(str, sorted(set(tags))))
            for (node_tag, dof), tags in sorted(overlapping_mpcs.items())
        )
        raise ValueError(
            "Multiple MPC constraints assign the same dependent DOF(s): "
            + details
            + "."
        )

    if support_mpc_conflicts:
        details = "; ".join(
            f"constraint {tag}: node {node_tag} DOF {dof}"
            for node_tag, dof, tag in sorted(support_mpc_conflicts)
        )
        raise ValueError(
            "MPC dependent DOF(s) are also fixed by supports: "
            + details
            + "."
        )

    def pattern_is_active(pattern_tag: int) -> bool:
        pattern_tag = int(pattern_tag)
        if pattern_tag in deferred_pattern_tags:
            return True
        if scoped_deferred_analysis:
            pattern = (load_patterns or {}).get(pattern_tag)
            return bool(
                active_analysis is not None
                and active_analysis.preload_gravity
                and pattern is not None
                and pattern.pattern_type == "Plain"
                and pattern_tag not in other_analysis_driver_tags
            )
        return pattern_tag in (load_patterns or {})

    active_prescribed_by_dof: dict[tuple[int, int], list[int]] = {}
    for displacement in (prescribed_displacements or {}).values():
        if not pattern_is_active(displacement.pattern_tag):
            continue
        key = (int(displacement.node_tag), int(displacement.dof))
        active_prescribed_by_dof.setdefault(key, []).append(
            int(displacement.tag)
        )

    duplicate_active_prescribed = {
        key: sorted(tags)
        for key, tags in active_prescribed_by_dof.items()
        if len(tags) > 1
    }
    if duplicate_active_prescribed:
        details = "; ".join(
            f"node {node_tag} DOF {dof}: "
            + ", ".join(map(str, tags))
            for (node_tag, dof), tags
            in sorted(duplicate_active_prescribed.items())
        )
        raise ValueError(
            "Multiple active Prescribed Displacement objects target the "
            "same node/DOF: "
            + details
            + "."
        )

    prescribed_mpc_conflicts: list[tuple[int, int, int, list[int]]] = []
    for displacement in (prescribed_displacements or {}).values():
        if not pattern_is_active(displacement.pattern_tag):
            continue
        key = (int(displacement.node_tag), int(displacement.dof))
        owners = sorted(set(dependent_owners.get(key, [])))
        if owners:
            prescribed_mpc_conflicts.append(
                (
                    int(displacement.tag),
                    key[0],
                    key[1],
                    owners,
                )
            )

    if prescribed_mpc_conflicts:
        details = "; ".join(
            f"SP {sp_tag}: node {node_tag} DOF {dof} -> MPC "
            + ", ".join(map(str, owners))
            for sp_tag, node_tag, dof, owners
            in prescribed_mpc_conflicts
        )
        raise ValueError(
            "Active Prescribed Displacement object(s) overlap MPC "
            "dependent DOF(s): "
            + details
            + "."
        )

    def plain_handler_supports_constraint(
        constraint: ConstraintData,
    ) -> bool:
        if constraint.constraint_type in {"equalDOF"}:
            return True
        if constraint.constraint_type == "rigidLink":
            if constraint.link_type == "bar":
                return True
            if int(model.ndf) == int(model.ndm):
                return True
            retained = model.nodes[int(constraint.retained_node)]
            retained_xyz = retained.xyz
            for node_tag in constraint.constrained_nodes:
                constrained = model.nodes[int(node_tag)]
                if any(
                    float(constrained.xyz[i]) != float(retained_xyz[i])
                    for i in range(int(model.ndm))
                ):
                    return False
            return True
        if constraint.constraint_type == "rigidDiaphragm":
            retained = model.nodes[int(constraint.retained_node)]
            retained_xyz = retained.xyz
            for node_tag in constraint.constrained_nodes:
                constrained_xyz = model.nodes[int(node_tag)].xyz
                if model.ndm == 2 and model.ndf == 3:
                    dx = float(constrained_xyz[0]) - float(retained_xyz[0])
                    dy = float(constrained_xyz[1]) - float(retained_xyz[1])
                    if int(constraint.perp_dirn) == 3 and (
                        dx != 0.0 or dy != 0.0
                    ):
                        return False
                elif model.ndm == 3 and model.ndf == 6:
                    dx = float(constrained_xyz[0]) - float(retained_xyz[0])
                    dy = float(constrained_xyz[1]) - float(retained_xyz[1])
                    dz = float(constrained_xyz[2]) - float(retained_xyz[2])
                    coupled_offsets = {
                        1: (dy, dz),
                        2: (dx, dz),
                        3: (dx, dy),
                    }.get(int(constraint.perp_dirn), ())
                    if any(value != 0.0 for value in coupled_offsets):
                        return False
            return True
        return True

    if active_analysis is not None and constraints:
        constrained_by_node: dict[int, list[int]] = {}
        for constraint in constraints.values():
            for node_tag in constraint.constrained_nodes:
                constrained_by_node.setdefault(
                    int(node_tag),
                    [],
                ).append(int(constraint.tag))

        chain_conflicts: list[tuple[int, int, list[int]]] = []
        for constraint in constraints.values():
            retained_node = int(constraint.retained_node)
            upstream = sorted({
                int(tag)
                for tag in constrained_by_node.get(retained_node, [])
                if int(tag) != int(constraint.tag)
            })
            if upstream:
                chain_conflicts.append(
                    (int(constraint.tag), retained_node, upstream)
                )

        if chain_conflicts and active_analysis.constraints_handler in {
            "Transformation",
            "Plain",
        }:
            details = "; ".join(
                f"constraint {tag} retains node {node_tag}, which is "
                "constrained by "
                + ", ".join(map(str, upstream))
                for tag, node_tag, upstream in chain_conflicts
            )
            raise ValueError(
                f"{active_analysis.constraints_handler} constraint handler "
                "does not follow chained MP constraints: "
                + details
                + ". A retained node must not be constrained in another "
                "MP constraint."
            )

        if active_analysis.constraints_handler == "Transformation":
            mpc_objects_by_node: dict[int, list[int]] = {}
            for constraint in constraints.values():
                for node_tag in constraint.constrained_nodes:
                    mpc_objects_by_node.setdefault(
                        int(node_tag),
                        [],
                    ).append(int(constraint.tag))
            multiple_mps = {
                node_tag: sorted(tags)
                for node_tag, tags in mpc_objects_by_node.items()
                if len(tags) > 1
            }
            if multiple_mps:
                details = "; ".join(
                    f"node {node_tag}: "
                    + ", ".join(map(str, tags))
                    for node_tag, tags in sorted(multiple_mps.items())
                )
                raise ValueError(
                    "Transformation constraint handler supports only one "
                    "MP constraint object per constrained node in Studio; "
                    "multiple MP objects found at "
                    + details
                    + ". Merge compatible equalDOF DOFs or use a supported "
                    "single MPC definition."
                )

        if active_analysis.constraints_handler == "Plain":
            unsupported_plain = sorted(
                int(constraint.tag)
                for constraint in constraints.values()
                if not plain_handler_supports_constraint(constraint)
            )
            if unsupported_plain:
                raise ValueError(
                    "Plain constraint handler would ignore non-identity "
                    "MP transformation matrix for constraint(s): "
                    + ", ".join(map(str, unsupported_plain))
                    + ". Use the Transformation constraint handler."
                )

    missing_deferred = sorted(
        deferred_pattern_tags - set((load_patterns or {}).keys())
    )
    if missing_deferred:
        raise ValueError(
            "Analysis references missing driving load pattern tag(s): "
            + ", ".join(map(str, missing_deferred))
        )

    if (
        active_analysis is not None
        and active_analysis.analysis_type != "Modal"
        and not (1 <= int(active_analysis.control_dof) <= int(model.ndf))
    ):
        raise ValueError(
            "Analysis control DOF "
            f"{active_analysis.control_dof} is incompatible with "
            f"model ndf={model.ndf}; choose a DOF from 1 to {model.ndf}."
        )

    uses_control_node = (
        active_analysis is not None
        and (
            active_analysis.analysis_type in {"Pushover", "Cyclic"}
            or (
                active_analysis.analysis_type == "Static"
                and active_analysis.integrator == "DisplacementControl"
            )
        )
    )
    if (
        uses_control_node
        and int(active_analysis.control_node) not in model.nodes
    ):
        raise ValueError(
            f"{active_analysis.analysis_type} control node "
            f"{active_analysis.control_node} does not exist in the model."
        )
    if uses_control_node:
        _control_node = model.nodes[int(active_analysis.control_node)]
        _control_dof = int(active_analysis.control_dof)
        if (
            _control_dof <= len(_control_node.fixity)
            and bool(_control_node.fixity[_control_dof - 1])
        ):
            raise ValueError(
                f"{active_analysis.analysis_type} control node "
                f"{active_analysis.control_node} DOF "
                f"{active_analysis.control_dof} is restrained by a support."
            )

        equal_dof_conflicts = sorted(
            constraint.tag
            for constraint in (constraints or {}).values()
            if (
                constraint.constraint_type == "equalDOF"
                and int(active_analysis.control_node)
                in {int(tag) for tag in constraint.constrained_nodes}
                and int(active_analysis.control_dof)
                in {int(dof) for dof in constraint.dofs}
            )
        )
        if equal_dof_conflicts:
            raise ValueError(
                f"{active_analysis.analysis_type} control node "
                f"{active_analysis.control_node} DOF "
                f"{active_analysis.control_dof} is a constrained/dependent "
                "DOF in equalDOF constraint(s): "
                + ", ".join(map(str, equal_dof_conflicts))
                + ". Use the retained node or another independent DOF."
            )

        rigid_link_conflicts = sorted(
            constraint.tag
            for constraint in (constraints or {}).values()
            if (
                constraint.constraint_type == "rigidLink"
                and int(active_analysis.control_node)
                in {int(tag) for tag in constraint.constrained_nodes}
                and (
                    constraint.link_type == "beam"
                    or int(active_analysis.control_dof)
                    <= min(int(model.ndm), int(model.ndf))
                )
            )
        )
        if rigid_link_conflicts:
            raise ValueError(
                f"{active_analysis.analysis_type} control node "
                f"{active_analysis.control_node} DOF "
                f"{active_analysis.control_dof} is a constrained/dependent "
                "DOF in rigidLink constraint(s): "
                + ", ".join(map(str, rigid_link_conflicts))
                + ". Use the retained node or another independent DOF."
            )

        def rigid_diaphragm_dofs(constraint: ConstraintData) -> set[int]:
            if model.ndm == 3 and model.ndf == 6:
                return {
                    1: {2, 3, 4},
                    2: {1, 3, 5},
                    3: {1, 2, 6},
                }.get(int(constraint.perp_dirn), set())
            if model.ndm == 2 and model.ndf == 3:
                return {
                    1: {1},
                    2: {2},
                    3: {1, 2, 3},
                }.get(int(constraint.perp_dirn), set())
            return set()

        rigid_diaphragm_conflicts = sorted(
            constraint.tag
            for constraint in (constraints or {}).values()
            if (
                constraint.constraint_type == "rigidDiaphragm"
                and int(active_analysis.control_node)
                in {int(tag) for tag in constraint.constrained_nodes}
                and int(active_analysis.control_dof)
                in rigid_diaphragm_dofs(constraint)
            )
        )
        if rigid_diaphragm_conflicts:
            raise ValueError(
                f"{active_analysis.analysis_type} control node "
                f"{active_analysis.control_node} DOF "
                f"{active_analysis.control_dof} is a constrained/dependent "
                "DOF in rigidDiaphragm constraint(s): "
                + ", ".join(map(str, rigid_diaphragm_conflicts))
                + ". Use the retained node or another independent DOF."
            )

    lines: list[str] = [
        "import json",
        "import math",
        "import os",
        "import openseespy.opensees as ops",
        "",
        "ops.wipe()",
        f"ops.model('basic', '-ndm', {model.ndm}, '-ndf', {model.ndf})",
        "",
        "# Consistent model units: "
        + f"{UnitSystem.from_mapping(units).length}, "
        + f"{UnitSystem.from_mapping(units).force}, "
        + f"{UnitSystem.from_mapping(units).time}",
        "# Material stress/modulus inputs are stored in Pa and converted here.",
        "# Material density inputs are stored in kg/m^3.",
        "",
        "# Nodes",
    ]

    current_ndf = int(model.ndf)
    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        node_ndf = int(node.ndf)
        if node_ndf != current_ndf:
            lines.append(
                f"ops.model('basic', '-ndm', {model.ndm}, "
                f"'-ndf', {node_ndf})"
            )
            current_ndf = node_ndf
        coordinates = tuple(node.xyz[:model.ndm])
        coordinate_text = ", ".join(f"{value:g}" for value in coordinates)
        lines.append(f"ops.node({tag}, {coordinate_text})")
    if current_ndf != int(model.ndf):
        lines.append(
            f"ops.model('basic', '-ndm', {model.ndm}, "
            f"'-ndf', {model.ndf})"
        )

    mass_nodes = [
        tag for tag, node in model.nodes.items()
        if any(abs(value) > 0.0 for value in node.mass)
    ]
    if mass_nodes:
        lines.extend(["", "# Nodal masses"])
        for tag in sorted(mass_nodes):
            mass = ", ".join(
                f"{value:g}"
                for value in model.nodes[tag].mass[:int(model.nodes[tag].ndf)]
            )
            lines.append(f"ops.mass({tag}, {mass})")

    lines.extend(["", "# Boundary conditions"])
    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        if any(node.fixity):
            fix = ", ".join(
                str(v) for v in node.fixity[:int(node.ndf)]
            )
            lines.append(f"ops.fix({tag}, {fix})")

    if constraints:
        lines.extend(["", "# Multi-point constraints"])
        for tag in sorted(constraints):
            lines.extend(constraint_to_openseespy(constraints[tag]))

    if materials:
        lines.extend(["", "# Materials"])
        for tag in ordered_material_tags(materials):
            material = materials[tag]
            lines.extend(material_source_comments(material))
            lines.append(material_to_openseespy(material, units))

    if friction_models:
        lines.extend(["", "# Friction models"])
        for tag in sorted(friction_models):
            lines.append(
                friction_model_to_openseespy(
                    friction_models[tag],
                    units,
                )
            )

    if nd_materials:
        lines.extend(["", "# nD Materials"])
        for tag in sorted(nd_materials):
            material = nd_materials[tag]
            lines.extend(nd_material_source_comments(material))
            lines.append(
                nd_material_to_openseespy(
                    material,
                    units,
                )
            )

    if sections:
        lines.extend(["", "# Sections"])
        for tag in sorted(sections):
            lines.extend(
                section_to_openseespy(
                    sections[tag],
                    materials,
                    units,
                    model.ndm,
                    nd_materials,
                )
            )

    if transformations:
        lines.extend(["", "# Geometric transformations"])
        for tag in sorted(transformations):
            lines.append(
                transformation_to_openseespy(
                    transformations[tag],
                    model.ndm,
                    model,
                )
            )

    lines.extend([
        "",
        "# Elements",
    ])
    for tag in sorted(model.elements):
        e = model.elements[tag]

        if e.element_type == "zeroLengthContact2D":
            p = e.special_parameters
            u = UnitSystem.from_mapping(units)
            kn = float(p["Kn"]) * u.length_to_m / u.force_to_n
            kt = float(p["Kt"]) * u.length_to_m / u.force_to_n
            nx, ny = (float(value) for value in p["normal"])
            lines.append(
                "ops.element('zeroLengthContact2D', "
                f"{tag}, {e.i}, {e.j}, {kn:g}, {kt:g}, "
                f"{float(p['mu']):g}, '-normal', {nx:g}, {ny:g})"
            )
            continue

        if e.element_type == "zeroLengthContact3D":
            p = e.special_parameters
            u = UnitSystem.from_mapping(units)
            kn = float(p["Kn"]) * u.length_to_m / u.force_to_n
            kt = float(p["Kt"]) * u.length_to_m / u.force_to_n
            cohesion = u.force_from_n(float(p["cohesion"]))
            lines.append(
                "ops.element('zeroLengthContact3D', "
                f"{tag}, {e.i}, {e.j}, {kn:g}, {kt:g}, "
                f"{float(p['mu']):g}, {cohesion:g}, {int(p['dir'])})"
            )
            continue

        if e.element_type == "BeamContact2D":
            p = e.special_parameters
            u = UnitSystem.from_mapping(units)
            width = u.length_from_m(float(p["width"]))
            gtol = u.length_from_m(float(p["gTol"]))
            ftol = u.force_from_n(float(p["fTol"]))
            lines.append(
                "ops.element('BeamContact2D', "
                f"{tag}, {e.i}, {e.j}, {int(e.k)}, {int(e.l)}, "
                f"{int(p['nd_material_tag'])}, {width:g}, "
                f"{gtol:g}, {ftol:g}, {int(p['cFlag'])})"
            )
            continue

        if e.element_type == "BeamContact3D":
            p = e.special_parameters
            u = UnitSystem.from_mapping(units)
            radius = u.length_from_m(float(p["radius"]))
            gtol = u.length_from_m(float(p["gTol"]))
            ftol = u.force_from_n(float(p["fTol"]))
            lines.append(
                "ops.element('BeamContact3D', "
                f"{tag}, {e.i}, {e.j}, {int(e.k)}, {int(e.l)}, "
                f"{radius:g}, {int(p['transf_tag'])}, "
                f"{int(p['nd_material_tag'])}, {gtol:g}, "
                f"{ftol:g}, {int(p['cFlag'])})"
            )
            continue

        if e.element_type in CABLE_ELEMENT_TYPES:
            p = e.special_parameters
            unit_system = UnitSystem.from_mapping(units)
            weight = (
                float(p["weight"])
                * unit_system.length_to_m
                / unit_system.force_to_n
            )
            elastic_modulus = unit_system.stress_from_pa(float(p["E"]))
            area = float(p["A"]) / (unit_system.length_to_m ** 2)
            unstressed_length = unit_system.length_from_m(float(p["L0"]))
            rho = (
                float(p["rho"])
                * unit_system.length_to_m
                / unit_system.mass_unit_kg
            )
            error_tol = unit_system.length_from_m(float(p["errorTol"]))
            lines.append(
                "ops.element('CatenaryCable', "
                f"{tag}, {e.i}, {e.j}, {weight:g}, "
                f"{elastic_modulus:g}, {area:g}, {unstressed_length:g}, "
                f"{float(p['alpha']):g}, "
                f"{float(p['temperature_change']):g}, {rho:g}, "
                f"{error_tol:g}, {int(p['Nsubsteps'])}, "
                f"{int(p['massType'])})"
            )
            continue

        if e.element_type == "LeadRubberX":
            p = e.special_parameters
            u = UnitSystem.from_mapping(units)
            fy = u.force_from_n(float(p["Fy"]))
            gr = u.stress_from_pa(float(p["Gr"]))
            kbulk = u.stress_from_pa(float(p["Kbulk"]))
            lengths = [
                u.length_from_m(float(p[key]))
                for key in ("D1", "D2", "ts", "tr")
            ]
            args = (
                "ops.element('LeadRubberX', "
                f"{tag}, {e.i}, {e.j}, {fy:g}, "
                f"{float(p['alpha']):g}, {gr:g}, {kbulk:g}, "
                + ", ".join(f"{value:g}" for value in lengths)
                + f", {int(p['n'])}"
            )
            orientation = p.get("orientation")
            if orientation is not None:
                args += ", " + ", ".join(
                    f"{float(value):g}" for value in orientation
                )
            mass = float(p["mass"]) / u.mass_unit_kg
            tc = u.length_from_m(float(p["tc"]))
            ql = (
                float(p["qL"])
                * u.length_to_m**3
                / u.mass_unit_kg
            )
            cl = (
                float(p["cL"])
                * u.mass_unit_kg
                / (u.force_to_n * u.length_to_m)
            )
            ks = (
                float(p["kS"])
                * u.time_to_s
                / u.force_to_n
            )
            a_s = (
                float(p["aS"])
                * u.time_to_s
                / (u.length_to_m**2)
            )
            args += (
                f", {float(p['kc']):g}, {float(p['PhiM']):g}, "
                f"{float(p['ac']):g}, {float(p['sDratio']):g}, "
                f"{mass:g}, {float(p['cd']):g}, {tc:g}, "
                f"{ql:g}, {cl:g}, {ks:g}, {a_s:g}, "
                f"{int(p['tag1'])}, {int(p['tag2'])}, "
                f"{int(p['tag3'])}, {int(p['tag4'])}, "
                f"{int(p['tag5'])})"
            )
            lines.append(args)
            continue

        if e.element_type == "TripleFrictionPendulum":
            p = e.special_parameters
            u = UnitSystem.from_mapping(units)
            lengths = [
                u.length_from_m(float(p[key]))
                for key in ("L1", "L2", "L3", "d1", "d2", "d3")
            ]
            w = u.force_from_n(float(p["W"]))
            uy = u.length_from_m(float(p["uy"]))
            kvt = (
                float(p["kvt"])
                * u.length_to_m
                / u.force_to_n
            )
            min_fv = u.force_from_n(float(p["minFv"]))
            lines.append(
                "ops.element('TripleFrictionPendulum', "
                f"{tag}, {e.i}, {e.j}, "
                f"{int(p['frnTag1'])}, {int(p['frnTag2'])}, "
                f"{int(p['frnTag3'])}, {int(p['vertMatTag'])}, "
                f"{int(p['rotZMatTag'])}, {int(p['rotXMatTag'])}, "
                f"{int(p['rotYMatTag'])}, "
                + ", ".join(f"{value:g}" for value in lengths)
                + f", {w:g}, {uy:g}, {kvt:g}, {min_fv:g}, "
                f"{float(p['tol']):g})"
            )
            continue

        if e.element_type in FRICTION_BEARING_ELEMENT_TYPES:
            p = e.special_parameters
            unit_system = UnitSystem.from_mapping(units)
            k_init = (
                float(p["kInit"])
                * unit_system.length_to_m
                / unit_system.force_to_n
            )
            args = (
                f"ops.element('{e.element_type}', "
                f"{tag}, {e.i}, {e.j}, {int(p['frn_model_tag'])}, "
            )
            if e.element_type == "singleFPBearing":
                args += (
                    f"{unit_system.length_from_m(float(p['Reff'])):g}, "
                )
            args += (
                f"{k_init:g}, '-P', {int(p['p_mat_tag'])}"
            )
            if int(model.ndm) == 3:
                args += (
                    f", '-T', {int(p['t_mat_tag'])}, "
                    f"'-My', {int(p['my_mat_tag'])}"
                )
            args += f", '-Mz', {int(p['mz_mat_tag'])}"
            orientation = p.get("orientation")
            if orientation is not None:
                args += ", '-orient', " + ", ".join(
                    f"{float(value):g}" for value in orientation
                )
            if abs(float(p["shearDist"])) > 1.0e-12:
                args += f", '-shearDist', {float(p['shearDist']):g}"
            if bool(p["doRayleigh"]):
                args += ", '-doRayleigh'"
            if float(p["mass"]) > 0.0:
                mass = float(p["mass"]) / unit_system.mass_unit_kg
                args += f", '-mass', {mass:g}"
            if (
                int(p["maxIter"]) != 20
                or abs(float(p["tol"]) - 1.0e-8) > 1.0e-16
            ):
                args += (
                    f", '-iter', {int(p['maxIter'])}, "
                    f"{float(p['tol']):g}"
                )
            args += ")"
            lines.append(args)
            continue

        if e.element_type == "elastomericBearingPlasticity":
            p = e.special_parameters
            unit_system = UnitSystem.from_mapping(units)
            k_init = (
                float(p["kInit"])
                * unit_system.length_to_m
                / unit_system.force_to_n
            )
            qd = unit_system.force_from_n(float(p["qd"]))
            args = (
                "ops.element('elastomericBearingPlasticity', "
                f"{tag}, {e.i}, {e.j}, {k_init:g}, {qd:g}, "
                f"{float(p['alpha1']):g}, {float(p['alpha2']):g}, "
                f"{float(p['mu']):g}, '-P', {int(p['p_mat_tag'])}"
            )
            if int(model.ndm) == 3:
                args += (
                    f", '-T', {int(p['t_mat_tag'])}, "
                    f"'-My', {int(p['my_mat_tag'])}"
                )
            args += f", '-Mz', {int(p['mz_mat_tag'])}"
            orientation = p.get("orientation")
            if orientation is not None:
                values = tuple(float(value) for value in orientation)
                args += ", '-orient', " + ", ".join(
                    f"{value:g}" for value in values
                )
            if abs(float(p["shearDist"]) - 0.5) > 1.0e-12:
                args += f", '-shearDist', {float(p['shearDist']):g}"
            if bool(p["doRayleigh"]):
                args += ", '-doRayleigh'"
            if float(p["mass"]) > 0.0:
                mass = float(p["mass"]) / unit_system.mass_unit_kg
                args += f", '-mass', {mass:g}"
            args += ")"
            lines.append(args)
            continue

        if e.element_type in EMBEDDED_ELEMENT_TYPES:
            if e.k is None or e.l is None:
                lines.append(
                    f"# ERROR: Embedded element {tag} is missing retained "
                    "triangle nodes; element not generated."
                )
                continue
            args = (
                "ops.element('ASDEmbeddedNodeElement', "
                f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}"
            )
            if e.embedded_constrain_rotation:
                args += ", '-rot'"
            if e.embedded_penalty is not None:
                penalty = UnitSystem.from_mapping(
                    units
                ).stress_from_pa(e.embedded_penalty)
                args += f", '-K', {penalty:g}"
            args += ")"
            lines.append(args)
            continue

        if e.element_type == "MEFI":
            if e.k is None or e.l is None:
                lines.append(
                    f"# ERROR: MEFI element {tag} is missing K/L nodes; "
                    "element not generated."
                )
                continue
            if not e.mefi_widths or (
                len(e.mefi_widths) != len(e.mefi_section_tags)
            ):
                lines.append(
                    f"# ERROR: MEFI element {tag} has invalid macro-fiber "
                    "width/section arrays; element not generated."
                )
                continue
            missing = [
                int(section_tag)
                for section_tag in e.mefi_section_tags
                if (
                    sections is None
                    or int(section_tag) not in sections
                )
            ]
            if missing:
                lines.append(
                    f"# ERROR: MEFI element {tag} references missing "
                    "RCLMS section tag(s): "
                    + ", ".join(map(str, sorted(set(missing))))
                )
                continue
            incompatible = [
                int(section_tag)
                for section_tag in e.mefi_section_tags
                if sections[int(section_tag)].section_type != "RCLMS"
            ]
            if incompatible:
                lines.append(
                    f"# ERROR: MEFI element {tag} requires RCLMS sections; "
                    "element not generated."
                )
                continue
            widths = ", ".join(
                f"{float(value):g}" for value in e.mefi_widths
            )
            sec_tags = ", ".join(
                str(int(value)) for value in e.mefi_section_tags
            )
            lines.append(
                "ops.element('MEFI', "
                f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}, "
                f"{len(e.mefi_widths)}, '-width', {widths}, "
                f"'-sec', {sec_tags})"
            )
            continue

        if e.element_type in WALL_MACRO_ELEMENT_TYPES:
            m = len(e.wall_widths)
            thick = ", ".join(
                f"{float(value):g}" for value in e.wall_thicknesses
            )
            widths = ", ".join(
                f"{float(value):g}" for value in e.wall_widths
            )
            if e.element_type == "SFI_MVLEM":
                missing = [
                    int(mat_tag)
                    for mat_tag in e.wall_nd_material_tags
                    if nd_materials is None or int(mat_tag) not in nd_materials
                ]
                if missing:
                    lines.append(
                        f"# ERROR: SFI_MVLEM element {tag} references "
                        "missing nDMaterial tag(s) "
                        + ", ".join(map(str, sorted(set(missing))))
                        + "; element not generated."
                    )
                    continue
                mats = ", ".join(
                    str(int(value)) for value in e.wall_nd_material_tags
                )
                lines.append(
                    "ops.element('SFI_MVLEM', "
                    f"{tag}, {e.i}, {e.j}, {m}, "
                    f"{e.wall_center_ratio:g}, '-thick', {thick}, "
                    f"'-width', {widths}, '-mat', {mats})"
                )
                continue

            direct_tags = {*e.wall_concrete_tags, *e.wall_steel_tags}
            if e.wall_shear_tag is not None:
                direct_tags.add(int(e.wall_shear_tag))
            missing = [
                int(mat_tag)
                for mat_tag in direct_tags
                if materials is None or int(mat_tag) not in materials
            ]
            if missing:
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} references "
                    "missing uniaxial material tag(s) "
                    + ", ".join(map(str, sorted(set(missing))))
                    + "; element not generated."
                )
                continue
            rhos = ", ".join(f"{float(value):g}" for value in e.wall_rhos)
            concrete = ", ".join(
                str(int(value)) for value in e.wall_concrete_tags
            )
            steel = ", ".join(
                str(int(value)) for value in e.wall_steel_tags
            )
            if e.element_type == "MVLEM":
                lines.append(
                    "ops.element('MVLEM', "
                    f"{tag}, {e.wall_density:g}, {e.i}, {e.j}, "
                    f"{m}, {e.wall_center_ratio:g}, "
                    f"'-thick', {thick}, '-width', {widths}, "
                    f"'-rho', {rhos}, '-matConcrete', {concrete}, "
                    f"'-matSteel', {steel}, '-matShear', "
                    f"{int(e.wall_shear_tag)})"
                )
            else:
                if e.k is None or e.l is None:
                    lines.append(
                        f"# ERROR: MVLEM_3D element {tag} is missing "
                        "K/L nodes; element not generated."
                    )
                    continue
                lines.append(
                    "ops.element('MVLEM_3D', "
                    f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}, {m}, "
                    f"'-thick', {thick}, '-width', {widths}, "
                    f"'-rho', {rhos}, '-matConcrete', {concrete}, "
                    f"'-matSteel', {steel}, '-matShear', "
                    f"{int(e.wall_shear_tag)}, '-CoR', "
                    f"{e.wall_center_ratio:g}, '-ThickMod', "
                    f"{e.wall_thick_mod:g}, '-Poisson', "
                    f"{e.wall_poisson:g}, '-Density', "
                    f"{e.wall_density:g})"
                )
            continue

        if e.element_type in CONTINUUM_QUAD_ELEMENT_TYPES:
            if e.k is None or e.l is None:
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} is missing "
                    "K/L nodes; element not generated."
                )
                continue
            if e.continuum_material_tag is None:
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} has no "
                    "nDMaterial assigned; element not generated."
                )
                continue
            if (
                nd_materials is None
                or int(e.continuum_material_tag) not in nd_materials
            ):
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} references "
                    f"missing nDMaterial {e.continuum_material_tag}; "
                    "element not generated."
                )
                continue
            b1, b2 = e.continuum_body_force
            if e.element_type == "quad":
                args = (
                    "ops.element('quad', "
                    f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}, "
                    f"{e.continuum_thickness:g}, "
                    f"'{e.continuum_type}', "
                    f"{e.continuum_material_tag}"
                )
                if any((
                    abs(float(e.continuum_pressure)) > 0.0,
                    abs(float(e.continuum_density)) > 0.0,
                    abs(float(b1)) > 0.0,
                    abs(float(b2)) > 0.0,
                )):
                    args += (
                        f", {e.continuum_pressure:g}, "
                        f"{e.continuum_density:g}, "
                        f"{b1:g}, {b2:g}"
                    )
                args += ")"
                lines.append(args)
            elif e.element_type == "SSPquad":
                lines.append(
                    "ops.element('SSPquad', "
                    f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}, "
                    f"{e.continuum_material_tag}, "
                    f"'{e.continuum_type}', "
                    f"{e.continuum_thickness:g}, {b1:g}, {b2:g})"
                )
            elif e.element_type == "bbarQuad":
                lines.append(
                    "ops.element('bbarQuad', "
                    f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}, "
                    f"{e.continuum_thickness:g}, "
                    f"{e.continuum_material_tag})"
                )
            else:
                lines.append(
                    "ops.element('enhancedQuad', "
                    f"{tag}, {e.i}, {e.j}, {e.k}, {e.l}, "
                    f"{e.continuum_thickness:g}, "
                    f"'{e.continuum_type}', "
                    f"{e.continuum_material_tag})"
                )
            continue

        if e.element_type in MASONRY_PANEL_ELEMENT_TYPES:
            node_tags = e.node_tags()
            if len(node_tags) != 12:
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} requires "
                    "twelve nodes; element not generated."
                )
                continue
            p = e.special_parameters
            node_args = ", ".join(str(int(value)) for value in node_tags)
            lines.append(
                "ops.element('MasonPan12', "
                f"{tag}, {node_args}, "
                f"{int(p['mat_1'])}, {int(p['mat_2'])}, "
                f"{float(p['thick']):g}, {float(p['w_tot']):g}, "
                f"{float(p['w_1']):g})"
            )
            continue

        if e.element_type in SOLID_ELEMENT_TYPES:
            node_tags = e.node_tags()
            if len(node_tags) != 8:
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} is missing "
                    "brick nodes; element not generated."
                )
                continue
            if e.solid_material_tag is None:
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} has no "
                    "nDMaterial assigned; element not generated."
                )
                continue
            if (
                nd_materials is None
                or int(e.solid_material_tag) not in nd_materials
            ):
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} references "
                    f"missing nDMaterial {e.solid_material_tag}; "
                    "element not generated."
                )
                continue
            nodes = ", ".join(str(int(value)) for value in node_tags)
            b1, b2, b3 = e.solid_body_force
            lines.append(
                f"ops.element('{e.element_type}', {tag}, {nodes}, "
                f"{e.solid_material_tag}, {b1:g}, {b2:g}, {b3:g})"
            )
            continue

        if e.element_type in SHELL_ELEMENT_TYPES:
            if e.section_tag is None:
                lines.append(
                    f"# ERROR: Shell element {tag} has no shell section "
                    "assigned; element not generated."
                )
                continue
            assigned_section = (
                sections.get(e.section_tag)
                if sections is not None
                else None
            )
            if (
                assigned_section is None
                or assigned_section.section_type not in SHELL_SECTION_TYPES
            ):
                lines.append(
                    f"# ERROR: Shell element {tag} requires a "
                    "shell-compatible section; element not generated."
                )
                continue
            if e.k is None or e.l is None:
                lines.append(
                    f"# ERROR: Shell element {tag} is missing K/L nodes; "
                    "element not generated."
                )
                continue
            args = (
                f"ops.element('{e.element_type}', {tag}, "
                f"{e.i}, {e.j}, {e.k}, {e.l}, {e.section_tag}"
            )
            if e.element_type == "ASDShellQ4":
                if e.shell_corotational:
                    args += ", '-corotational'"
                if e.shell_no_eas:
                    args += ", '-noeas'"
                if e.shell_drilling_stab is not None:
                    args += (
                        f", '-drillingStab', "
                        f"{e.shell_drilling_stab:g}"
                    )
                if e.shell_drilling_nl:
                    args += ", '-drillingNL'"
                if e.shell_local_x is not None:
                    x1, x2, x3 = e.shell_local_x
                    args += (
                        f", '-local', {x1:g}, {x2:g}, {x3:g}"
                    )
            args += ")"
            lines.append(args)
            continue

        if e.element_type in TRUSS_ELEMENT_TYPES:
            if e.element_type in TRUSS_SECTION_ELEMENT_TYPES:
                if e.section_tag is None:
                    lines.append(
                        f"# ERROR: {e.element_type} element {tag} has no "
                        "section assigned; element not generated."
                    )
                    continue
                assigned_section = (
                    sections.get(int(e.section_tag))
                    if sections is not None
                    else None
                )
                if assigned_section is None:
                    lines.append(
                        f"# ERROR: {e.element_type} element {tag} references "
                        f"missing section {e.section_tag}; element not generated."
                    )
                    continue
                if assigned_section.section_type in (
                    SHELL_SECTION_TYPES | MEMBRANE_SECTION_TYPES
                ):
                    lines.append(
                        f"# ERROR: {e.element_type} element {tag} cannot use "
                        f"shell section {e.section_tag}; element not generated."
                    )
                    continue
                command = (
                    "TrussSection"
                    if e.element_type == "trussSection"
                    else "corotTrussSection"
                )
                args = (
                    f"ops.element('{command}', "
                    f"{tag}, {e.i}, {e.j}, {int(e.section_tag)}"
                )
            else:
                if e.truss_area <= 0.0:
                    lines.append(
                        f"# ERROR: Truss element {tag} has non-positive area; "
                        "element not generated."
                    )
                    continue
                if e.truss_material_tag is None:
                    lines.append(
                        f"# ERROR: Truss element {tag} has no material assigned; "
                        "element not generated."
                    )
                    continue
                if (
                    materials is None
                    or e.truss_material_tag not in materials
                ):
                    lines.append(
                        f"# ERROR: Truss element {tag} references missing material "
                        f"{e.truss_material_tag}; element not generated."
                    )
                    continue

                command = (
                    "Truss"
                    if e.element_type == "truss"
                    else "corotTruss"
                )
                args = (
                    f"ops.element('{command}', "
                    f"{tag}, {e.i}, {e.j}, {e.truss_area:g}, "
                    f"{e.truss_material_tag}"
                )
            if e.mass_per_length > 0.0:
                args += f", '-rho', {e.mass_per_length:g}"
            if e.consistent_mass:
                args += ", '-cMass', 1"
            if e.truss_do_rayleigh:
                args += ", '-doRayleigh', 1"
            args += ")"
            lines.append(args)
            continue

        transf_tag = e.transf_tag
        if transf_tag is None:
            lines.append(
                f"# ERROR: Element {tag} has no geometric "
                "transformation assigned; element not generated."
            )
            continue
        if not transformations or transf_tag not in transformations:
            lines.append(
                f"# ERROR: Element {tag} references missing geometric "
                f"transformation {transf_tag}; element not generated."
            )
            continue

        if e.section_tag is None:
            lines.append(
                f"# ERROR: Element {tag} has no section assigned; "
                "element not generated."
            )
            continue
        assigned_section = (
            sections.get(e.section_tag)
            if sections is not None
            else None
        )
        if assigned_section is None:
            lines.append(
                f"# ERROR: Element {tag} references missing section "
                f"{e.section_tag}; element not generated."
            )
            continue

        if e.element_type in {"elasticBeamColumn", "ElasticTimoshenkoBeam"}:
            if assigned_section.section_type != "Elastic":
                lines.append(
                    f"# ERROR: {e.element_type} element {tag} requires an "
                    "Elastic section in the current Studio generator; "
                    "element not generated."
                )
                continue
            p = elastic_section_parameters_in_model_units(
                assigned_section,
                materials,
                units,
            )
            if e.element_type == "ElasticTimoshenkoBeam":
                required = (
                    ("E", "G", "A", "Iz", "Avy")
                    if int(model.ndm) == 2
                    else (
                        "E", "G", "A", "J", "Iy", "Iz", "Avy", "Avz"
                    )
                )
                invalid = [
                    key for key in required
                    if float(p.get(key, 0.0)) <= 0.0
                ]
                if invalid:
                    lines.append(
                        f"# ERROR: ElasticTimoshenkoBeam element {tag} "
                        "requires positive Elastic section parameter(s): "
                        + ", ".join(invalid)
                        + "; element not generated."
                    )
                    continue
                if int(model.ndm) == 2:
                    args = (
                        "ops.element('ElasticTimoshenkoBeam', "
                        f"{tag}, {e.i}, {e.j}, {p['E']:g}, {p['G']:g}, "
                        f"{p['A']:g}, {p['Iz']:g}, {p['Avy']:g}, "
                        f"{transf_tag}"
                    )
                else:
                    args = (
                        "ops.element('ElasticTimoshenkoBeam', "
                        f"{tag}, {e.i}, {e.j}, {p['E']:g}, {p['G']:g}, "
                        f"{p['A']:g}, {p['J']:g}, {p['Iy']:g}, "
                        f"{p['Iz']:g}, {p['Avy']:g}, {p['Avz']:g}, "
                        f"{transf_tag}"
                    )
            elif int(model.ndm) == 2:
                args = (
                    "ops.element('elasticBeamColumn', "
                    f"{tag}, {e.i}, {e.j}, {p['A']:g}, {p['E']:g}, "
                    f"{p['Iz']:g}, {transf_tag}"
                )
            else:
                args = (
                    "ops.element('elasticBeamColumn', "
                    f"{tag}, {e.i}, {e.j}, {p['A']:g}, {p['E']:g}, "
                    f"{p['G']:g}, {p['J']:g}, {p['Iy']:g}, {p['Iz']:g}, "
                    f"{transf_tag}"
                )
            if e.mass_per_length > 0.0:
                args += f", '-mass', {e.mass_per_length:g}"
                if e.consistent_mass:
                    args += ", '-cMass'"
            args += ")"
            lines.append(args)
            continue

        if e.element_type == "dispBeamColumnInt":
            if (int(model.ndm), int(model.ndf)) != (2, 3):
                lines.append(
                    f"# ERROR: dispBeamColumnInt element {tag} requires "
                    "ndm=2/ndf=3; element not generated."
                )
                continue
            if assigned_section.section_type != "FiberInt":
                lines.append(
                    f"# ERROR: dispBeamColumnInt element {tag} requires "
                    "a FiberInt section; element not generated."
                )
                continue
            transformation = transformations.get(transf_tag)
            if transformation.transformation_type != "LinearInt":
                lines.append(
                    f"# ERROR: dispBeamColumnInt element {tag} requires "
                    "a LinearInt transformation; element not generated."
                )
                continue
            args = (
                "ops.element('dispBeamColumnInt', "
                f"{tag}, {e.i}, {e.j}, {e.integration_points}, "
                f"{assigned_section.tag}, {transf_tag}, "
                f"{e.beam_center_ratio:g}"
            )
            if e.mass_per_length > 0.0:
                args += f", '-mass', {e.mass_per_length:g}"
            args += ")"
            lines.append(args)
            continue

        if e.element_type in {"forceBeamColumn", "dispBeamColumn"}:
            integration_tag = tag
            distributed_types = {"Lobatto", "Legendre", "Radau"}
            hinge_types = {
                "HingeRadau",
                "HingeRadauTwo",
                "HingeMidpoint",
                "HingeEndpoint",
            }

            if e.integration_type in distributed_types:
                lines.append(
                    "ops.beamIntegration("
                    f"'{e.integration_type}', {integration_tag}, "
                    f"{assigned_section.tag}, {e.integration_points})"
                )
            elif e.integration_type in hinge_types:
                required = (
                    e.hinge_i_section_tag,
                    e.hinge_j_section_tag,
                    e.interior_section_tag,
                )
                if any(section_tag is None for section_tag in required):
                    lines.append(
                        f"# ERROR: {e.integration_type} element {tag} is missing "
                        "hinge/interior section assignments; element not generated."
                    )
                    continue
                missing = [
                    int(section_tag)
                    for section_tag in required
                    if sections is None or int(section_tag) not in sections
                ]
                if missing:
                    lines.append(
                        f"# ERROR: {e.integration_type} element {tag} references "
                        f"missing section tag(s) {missing}; element not generated."
                    )
                    continue
                lines.append(
                    "ops.beamIntegration("
                    f"'{e.integration_type}', {integration_tag}, "
                    f"{e.hinge_i_section_tag}, {e.hinge_i_length:g}, "
                    f"{e.hinge_j_section_tag}, {e.hinge_j_length:g}, "
                    f"{e.interior_section_tag})"
                )
            elif e.integration_type == "ConcentratedPlasticity":
                required = (
                    e.hinge_i_section_tag,
                    e.hinge_j_section_tag,
                    e.interior_section_tag,
                )
                if any(section_tag is None for section_tag in required):
                    lines.append(
                        f"# ERROR: ConcentratedPlasticity element {tag} is missing "
                        "end/interior section assignments; element not generated."
                    )
                    continue
                missing = [
                    int(section_tag)
                    for section_tag in required
                    if sections is None or int(section_tag) not in sections
                ]
                if missing:
                    lines.append(
                        f"# ERROR: ConcentratedPlasticity element {tag} references "
                        f"missing section tag(s) {missing}; element not generated."
                    )
                    continue
                lines.append(
                    "ops.beamIntegration("
                    f"'ConcentratedPlasticity', {integration_tag}, "
                    f"{e.hinge_i_section_tag}, {e.hinge_j_section_tag}, "
                    f"{e.interior_section_tag})"
                )
            else:
                lines.append(
                    f"# ERROR: Beam integration {e.integration_type!r} for "
                    f"element {tag} is not implemented; element not generated."
                )
                continue

            if e.element_type == "forceBeamColumn":
                args = (
                    "ops.element('forceBeamColumn', "
                    f"{tag}, {e.i}, {e.j}, {transf_tag}, "
                    f"{integration_tag}, '-iter', {e.force_max_iter}, "
                    f"{e.force_tolerance:g}"
                )
                if e.mass_per_length > 0.0:
                    args += f", '-mass', {e.mass_per_length:g}"
                args += ")"
                lines.append(args)
            else:
                args = (
                    "ops.element('dispBeamColumn', "
                    f"{tag}, {e.i}, {e.j}, {transf_tag}, "
                    f"{integration_tag}"
                )
                if e.consistent_mass:
                    args += ", '-cMass'"
                if e.mass_per_length > 0.0:
                    args += f", '-mass', {e.mass_per_length:g}"
                args += ")"
                lines.append(args)
            continue

        lines.append(
            f"# ERROR: Element {tag} type {e.element_type!r} is not "
            "implemented by the Studio generator; element not generated."
        )

    connection_values = list((connections or {}).values())
    reserved_connection_element_max = max(
        set(model.elements) | set((connections or {}).keys()),
        default=0,
    )
    explicit_joint_center_tags = {
        int(connection.parameters["imported_center_node_tag"])
        for connection in connection_values
        if (
            connection.connection_type == "Joint2D"
            and connection.parameters.get("imported_center_node_tag") is not None
        )
    }
    reserved_connection_node_max = max(
        set(model.nodes) | explicit_joint_center_tags,
        default=0,
    )
    krawinkler_internal_element_count = 8 * sum(
        1
        for connection in connection_values
        if connection.connection_type == "KrawinklerPanelZone"
    )

    if connections:
        lines.extend(["", "# Connections / springs / links"])
        for tag in sorted(connections):
            lines.append(
                connection_to_openseespy(
                    connections[tag],
                    ndm=model.ndm,
                    ndf=model.ndf,
                    reserved_element_tag_max=reserved_connection_element_max,
                    reserved_node_tag_max=reserved_connection_node_max,
                )
            )

    if time_series:
        lines.extend(["", "# Time series"])
        for tag in sorted(time_series):
            lines.append(time_series_to_openseespy(time_series[tag]))

    nodal_by_pattern: dict[int, list[NodalLoadData]] = {}
    for load in (nodal_loads or {}).values():
        nodal_by_pattern.setdefault(load.pattern_tag, []).append(load)

    element_by_pattern: dict[int, list[ElementLoadData]] = {}
    for load in (element_loads or {}).values():
        element_by_pattern.setdefault(load.pattern_tag, []).append(load)

    reserved_element_tags = set(model.elements)
    reserved_element_tags.update((connections or {}).keys())
    # Krawinkler macros create eight hidden elasticBeamColumn elements each,
    # immediately above the public model/connection element-tag ceiling.
    # Keep later generated SurfaceLoad helper elements above that range.
    next_surface_tag = (
        max(reserved_element_tags, default=0)
        + krawinkler_internal_element_count
        + 1
    )
    surface_pressure_tags: dict[int, int] = {}
    for load in sorted(
        (element_loads or {}).values(),
        key=lambda item: int(item.tag),
    ):
        if load.load_type != "SurfacePressure":
            continue
        while next_surface_tag in reserved_element_tags:
            next_surface_tag += 1
        surface_pressure_tags[int(load.tag)] = next_surface_tag
        reserved_element_tags.add(next_surface_tag)
        next_surface_tag += 1

    displacement_by_pattern: dict[int, list[PrescribedDisplacementData]] = {}
    for displacement in (prescribed_displacements or {}).values():
        displacement_by_pattern.setdefault(
            displacement.pattern_tag,
            [],
        ).append(displacement)

    if (
        active_analysis is not None
        and active_analysis.constraints_handler == "Plain"
    ):
        active_nonzero_prescribed: list[int] = []
        for displacement in (prescribed_displacements or {}).values():
            if displacement.value == 0.0:
                continue
            pattern_tag = int(displacement.pattern_tag)
            if pattern_tag in deferred_pattern_tags:
                is_active = True
            elif scoped_deferred_analysis:
                pattern = (load_patterns or {}).get(pattern_tag)
                is_active = bool(
                    active_analysis.preload_gravity
                    and pattern is not None
                    and pattern.pattern_type == "Plain"
                    and pattern_tag not in other_analysis_driver_tags
                )
            else:
                is_active = pattern_tag in (load_patterns or {})
            if is_active:
                active_nonzero_prescribed.append(int(displacement.tag))

        if active_nonzero_prescribed:
            raise ValueError(
                "Plain constraint handler cannot enforce non-zero "
                "Prescribed Displacement object(s): "
                + ", ".join(map(str, sorted(active_nonzero_prescribed)))
                + ". Use the Transformation constraint handler."
            )

    if (
        active_analysis is not None
        and (
            active_analysis.analysis_type in {"Pushover", "Cyclic"}
            or (
                active_analysis.analysis_type == "Static"
                and active_analysis.integrator == "DisplacementControl"
            )
        )
    ):
        invalid_driver_patterns = sorted(
            tag
            for tag in deferred_pattern_tags
            if displacement_by_pattern.get(tag)
        )
        if invalid_driver_patterns:
            raise ValueError(
                "DisplacementControl driving load pattern(s) cannot contain "
                "Prescribed Displacement objects: "
                + ", ".join(map(str, invalid_driver_patterns))
                + ". Use a force reference-load pattern for "
                "DisplacementControl."
            )

        conflicting_displacements: list[int] = []
        for displacement in (prescribed_displacements or {}).values():
            if (
                int(displacement.node_tag) != int(active_analysis.control_node)
                or int(displacement.dof) != int(active_analysis.control_dof)
            ):
                continue

            pattern_tag = int(displacement.pattern_tag)
            if pattern_tag in deferred_pattern_tags:
                is_active = True
            elif scoped_deferred_analysis:
                pattern = (load_patterns or {}).get(pattern_tag)
                is_active = bool(
                    active_analysis.preload_gravity
                    and pattern is not None
                    and pattern.pattern_type == "Plain"
                    and pattern_tag not in other_analysis_driver_tags
                )
            else:
                is_active = pattern_tag in (load_patterns or {})

            if is_active:
                conflicting_displacements.append(int(displacement.tag))

        if conflicting_displacements:
            raise ValueError(
                f"{active_analysis.analysis_type} control node "
                f"{active_analysis.control_node} DOF "
                f"{active_analysis.control_dof} conflicts with active "
                "Prescribed Displacement object(s): "
                + ", ".join(map(str, sorted(conflicting_displacements)))
                + ". Remove the prescribed displacement or choose a "
                "different control DOF."
            )

    if load_patterns:
        lines.extend(["", "# Load patterns"])
        for tag in sorted(load_patterns):
            if tag in deferred_pattern_tags:
                continue
            pattern = load_patterns[tag]
            if scoped_deferred_analysis:
                # Template-driven analyses own their driver/excitation
                # patterns. Do not leak drivers from other analyses into the
                # active solve, and only activate background Plain patterns
                # when gravity/existing-load preload is explicitly enabled.
                if tag in other_analysis_driver_tags:
                    continue
                if pattern.pattern_type != "Plain":
                    continue
                if not active_analysis.preload_gravity:
                    continue
            lines.extend(
                load_pattern_block_to_openseespy(
                    pattern,
                    nodal_loads=nodal_by_pattern.get(tag, []),
                    prescribed_displacements=displacement_by_pattern.get(
                        tag,
                        [],
                    ),
                    element_loads=element_by_pattern.get(tag, []),
                    model=model,
                    sections=sections,
                    materials=materials,
                    transformations=transformations,
                    units=units,
                    surface_pressure_tags=surface_pressure_tags,
                )
            )

    if recorders:
        valid_recorder_element_tags = set(model.elements) | {
            connection_tag
            for connection_tag, connection in (connections or {}).items()
            if connection.connection_type in ELEMENT_BACKED_CONNECTION_TYPES
        }
        lines.extend(["", "# Recorders"])
        for tag in sorted(recorders):
            recorder = recorders[tag]
            if recorder.recorder_type != "Node":
                invalid_targets = sorted(
                    int(target)
                    for target in recorder.target_tags
                    if int(target) not in valid_recorder_element_tags
                )
                if invalid_targets:
                    raise ValueError(
                        f"Recorder {recorder.tag} targets non-element or "
                        "missing connection/element tag(s): "
                        + ", ".join(map(str, invalid_targets))
                    )
            lines.append(
                f"# Recorder {recorder.tag}: {recorder.name}"
            )
            lines.extend(recorder_to_openseespy(recorder))

    if active_analysis is not None:
        lines.extend(["", "# Analysis settings"])
        active = active_analysis

        preload_plain_tags = sorted(
            tag
            for tag, pattern in (load_patterns or {}).items()
            if (
                pattern.pattern_type == "Plain"
                and tag not in deferred_pattern_tags
                and (
                    not scoped_deferred_analysis
                    or tag not in other_analysis_driver_tags
                )
            )
        )
        if active.preload_gravity and preload_plain_tags:
            gravity_increment = 1.0 / active.gravity_steps
            lines.extend([
                "",
                "# Template sequence: gravity / existing Plain-load preload",
                f"ops.constraints({active.constraints_handler!r})",
                f"ops.numberer({active.numberer!r})",
                (
                    "ops.system('SparseGeneral', '-piv')"
                    if (
                        active.system == "SparseGeneral"
                        and active.system_pivoting
                    )
                    else f"ops.system({active.system!r})"
                ),
                (
                    f"ops.test({active.test!r}, {active.tolerance:g}, "
                    f"{active.max_iterations}, 0)"
                ),
                f"ops.algorithm({(active.algorithm if active.gravity_algorithm == 'Auto' else active.gravity_algorithm)!r})",
                f"ops.integrator('LoadControl', {gravity_increment:g})",
                "ops.analysis('Static')",
                f"_studio_gravity_ok = ops.analyze({active.gravity_steps})",
                "if _studio_gravity_ok != 0:",
                (
                    "    raise RuntimeError("
                    "'Gravity preload failed before the template analysis')"
                ),
                "ops.loadConst('-time', 0.0)",
                "ops.wipeAnalysis()",
            ])

        if (
            deferred_pattern_tags
            and active.analysis_type != "Response Spectrum"
        ):
            lines.extend(["", "# Template driving / excitation patterns"])
            for deferred_tag in sorted(deferred_pattern_tags):
                pattern = (load_patterns or {}).get(deferred_tag)
                if pattern is None:
                    lines.append(
                        f"# ERROR: Deferred load pattern {deferred_tag} "
                        "does not exist."
                    )
                    continue
                lines.extend(
                    load_pattern_block_to_openseespy(
                        pattern,
                        nodal_loads=nodal_by_pattern.get(
                            deferred_tag,
                            [],
                        ),
                        prescribed_displacements=displacement_by_pattern.get(
                            deferred_tag,
                            [],
                        ),
                        element_loads=element_by_pattern.get(
                            deferred_tag,
                            [],
                        ),
                        model=model,
                        sections=sections,
                        materials=materials,
                        transformations=transformations,
                        units=units,
                    )
                )
        monitor_node = (
            active.control_node
            if active.control_node in model.nodes
            else min(model.nodes, default=1)
        )
        result_element_tags = sorted(
            {
                int(tag)
                for tag, element in model.elements.items()
                if element.element_type not in EMBEDDED_ELEMENT_TYPES
            }
            | {
                tag
                for tag, connection in (connections or {}).items()
                if connection.connection_type in ELEMENT_BACKED_CONNECTION_TYPES
            }
        )
        support_node_tags = sorted(
            tag
            for tag, node in model.nodes.items()
            if any(node.fixity)
        )
        fiber_response_specs: dict[int, dict[str, object]] = {}
        for element_tag, element in model.elements.items():
            if element.element_type not in {"forceBeamColumn", "dispBeamColumn"}:
                continue
            if element.section_tag is None or not sections:
                continue
            section = sections.get(element.section_tag)
            if section is None or section.section_type != "Fiber":
                continue
            fibers = section.compiled_fibers()
            if not fibers:
                continue
            count = max(int(element.integration_points), 1)
            locations = (
                [0.5]
                if count == 1
                else [index / (count - 1) for index in range(count)]
            )
            fiber_response_specs[int(element_tag)] = {
                "section_tag": int(section.tag),
                "locations": locations,
                "fibers": [
                    {
                        "y": float(fiber.y),
                        "z": float(fiber.z),
                        "area": float(fiber.area),
                        "material_tag": int(fiber.material_tag),
                    }
                    for fiber in fibers
                ],
            }

        specimen_response_spec = column_response_spec(
            model,
            sections=sections,
            materials=materials,
            transformations=transformations,
            connections=connections,
            active_analysis=active,
        )
        moment_curvature_spec = moment_curvature_response_spec(
            model,
            connections=connections,
            active_analysis=active,
        )
        section_response_specs = build_section_response_specs(
            model,
            connections=connections,
            solution_results=solution_results,
            active_analysis=active,
        )
        joint_response_specs = build_joint_response_specs(
            connections=connections,
            solution_results=solution_results,
            active_analysis=active,
        )
        mefi_crack_specs = build_mefi_crack_specs(
            model,
            sections=sections,
            nd_materials=nd_materials,
        )

        frame_tags = sorted(
            tag
            for tag, element in model.elements.items()
            if element.element_type in {
                "elasticBeamColumn",
                "forceBeamColumn",
                "dispBeamColumn",
            }
        )
        shell_tags = sorted(
            tag
            for tag, element in model.elements.items()
            if element.element_type in SHELL_ELEMENT_TYPES
        )
        frame_history_tags: set[int] = set()
        shell_force_history_tags: set[int] = set()
        shell_deformation_history_tags: set[int] = set()
        masonry_history_tags: set[int] = set()
        masonry_tags = {
            int(tag)
            for tag, element in model.elements.items()
            if element.element_type == "MasonPan12"
        }
        for result_request in (solution_results or {}).values():
            if int(getattr(result_request, "analysis_tag", -1)) != int(active.tag):
                continue
            result_type = str(
                getattr(result_request, "result_type", "")
            )
            scope = {
                int(tag)
                for tag in (
                    getattr(result_request, "element_scope", ()) or ()
                )
            }
            if result_type == "MemberForce":
                candidates = set(frame_tags)
                frame_history_tags.update(
                    (scope & candidates) if scope else candidates
                )
            elif result_type == "ShellForce":
                candidates = set(shell_tags)
                shell_force_history_tags.update(
                    (scope & candidates) if scope else candidates
                )
            elif result_type == "ShellDeformation":
                candidates = set(shell_tags)
                shell_deformation_history_tags.update(
                    (scope & candidates) if scope else candidates
                )
            elif result_type in {
                "MasonryPanelShear",
                "MasonryStrutForce",
                "MasonryStrutStrain",
            }:
                masonry_history_tags.update(
                    (scope & masonry_tags) if scope else masonry_tags
                )

        response_spectrum_components = _response_spectrum_sources(
            active,
            load_patterns,
            time_series,
        )
        response_spectrum_gravity = UnitSystem.from_mapping(
            units
        ).acceleration_from_m_per_s2(9.80665)

        lines.extend(
            analysis_to_openseespy(
                active,
                ndm=model.ndm,
                node_tags=sorted(model.nodes),
                element_tags=result_element_tags,
                frame_element_tags=frame_tags,
                truss_element_tags=sorted(
                    tag
                    for tag, element in model.elements.items()
                    if element.element_type in TRUSS_ELEMENT_TYPES
                ),
                shell_element_tags=shell_tags,
                frame_history_tags=sorted(frame_history_tags),
                shell_force_history_tags=sorted(shell_force_history_tags),
                shell_deformation_history_tags=sorted(
                    shell_deformation_history_tags
                ),
                masonry_history_tags=sorted(masonry_history_tags),
                mefi_crack_specs=mefi_crack_specs,
                support_node_tags=support_node_tags,
                plain_pattern_tags=sorted(
                    tag
                    for tag, pattern in (load_patterns or {}).items()
                    if (
                        pattern.pattern_type == "Plain"
                        and (
                            not scoped_deferred_analysis
                            or tag in deferred_pattern_tags
                            or (
                                active.preload_gravity
                                and tag not in other_analysis_driver_tags
                            )
                        )
                    )
                ),
                monitor_node=monitor_node,
                fiber_response_specs=fiber_response_specs,
                specimen_response_spec=specimen_response_spec,
                moment_curvature_spec=moment_curvature_spec,
                section_response_specs=section_response_specs,
                response_spectrum_components=response_spectrum_components,
                response_spectrum_gravity=response_spectrum_gravity,
                requires_joint2d_handler=any(
                    connection.connection_type == "Joint2D"
                    for connection in (connections or {}).values()
                ),
                requires_offset_rigid_handler=any(
                    (
                        connection.connection_type == "rigid"
                        and connection.node_i in model.nodes
                        and connection.node_j in model.nodes
                        and any(
                            abs(float(a) - float(b)) > 1.0e-12
                            for a, b in zip(
                                model.nodes[connection.node_i].xyz,
                                model.nodes[connection.node_j].xyz,
                            )
                        )
                    )
                    for connection in (connections or {}).values()
                ),
                krawinkler_panel_zone_tags=[
                    int(tag)
                    for tag, connection in (connections or {}).items()
                    if connection.connection_type == "KrawinklerPanelZone"
                ],
                joint_response_specs=joint_response_specs,
            )
        )

    lines.extend(["", "print('Model generated by OpenSeesPy Studio MVP')"])
    return "\n".join(lines) + "\n"
