from __future__ import annotations

from dataclasses import dataclass, field, fields
import math

from .project import (
    MaterialData,
    NDMaterialData,
    ProjectDatabase,
    SectionData,
    SelectionSetData,
    ShellLayerData,
)


@dataclass(slots=True)
class RCWallSpec:
    """Planar 2D reinforced-concrete wall built with RCLMS + MEFI."""

    # Lengths are in the project length unit. Defaults match SARE's
    # standard metre-based project and the RW-A20 wall geometry.
    width: float = 1.220
    height: float = 2.2098
    thickness: float = 0.1524
    boundary_width: float = 0.2286
    origin_x: float = 0.0
    origin_y: float = 0.0
    vertical_elements: int = 7
    macro_fibers: int = 8

    # Benchmark-inspired constitutive inputs, stored in SI stress units.
    steel_E: float = 200.0e9
    steel_fx: float = 469.93e6
    steel_fy_web: float = 409.71e6
    steel_fy_boundary: float = 429.78e6
    steel_bx: float = 0.02
    steel_by_web: float = 0.02
    steel_by_boundary: float = 0.01

    concrete_fc_web: float = -47.09e6
    concrete_eps_web: float = -0.00232
    concrete_fcu_web: float = 0.0
    concrete_epsu_web: float = -0.037
    concrete_fc_boundary: float = -53.78e6
    concrete_eps_boundary: float = -0.00397
    concrete_fcu_boundary: float = -9.42e6
    concrete_epsu_boundary: float = -0.047
    concrete_ft: float = 2.13e6
    concrete_ets_web: float = 1.73833e9
    concrete_ets_boundary: float = 1.82712e9
    concrete_lambda: float = 0.1
    cracking_strain: float = 8.0e-5
    damage_cte1: float = 0.175
    damage_cte2: float = 0.5

    rho_x_web: float = 0.0027
    rho_y_web: float = 0.0027
    rho_x_boundary: float = 0.0082
    rho_y_boundary: float = 0.0323

    # Hybrid V1 keeps web steel smeared and may move part of the boundary
    # longitudinal steel into discrete perfect-bond truss lines. Because the
    # current MEFI wall has nodes only on its two vertical edges, each edge
    # line represents the total discrete bar area of one boundary zone.
    reinforcement_mode: str = "smeared"
    boundary_bar_count: int = 4
    boundary_bar_diameter: float = 0.016
    boundary_truss_type: str = "corotTruss"
    boundary_layer_mode: str = "front_back"
    boundary_cover: float = 0.030

    # Horizontal web bars can be discretized only on existing MEFI node
    # rows in this shared-node perfect-bond stage. Vertical web bars remain
    # smeared until an embedded/interpolation coupling is available.
    web_horizontal_mode: str = "smeared"
    web_horizontal_bar_diameter: float = 0.008
    web_horizontal_layer_mode: str = "front_back"

    # Embedded vertical web reinforcement is independent of the MEFI node
    # grid. Each steel node is interpolated from a retained triangle using
    # ASDEmbeddedNodeElement. This backend option is intentionally not yet
    # exposed as the default GUI workflow.
    web_vertical_mode: str = "smeared"
    web_vertical_bar_diameter: float = 0.006
    web_vertical_spacing: float = 0.200
    web_vertical_edge_offset: float = 0.050
    web_vertical_layer_mode: str = "front_back"
    embedded_penalty_factor: float = 1.0

    boundary_unconfined_thickness: float = 0.0508
    boundary_confined_thickness: float = 0.1016

    name: str = "RC Wall"
    replace_geometry: bool = True


@dataclass(slots=True)
class RCWallBuildResult:
    node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    material_tags: list[int] = field(default_factory=list)
    nd_material_tags: list[int] = field(default_factory=list)
    section_tags: list[int] = field(default_factory=list)
    web_section_tag: int = 0
    boundary_section_tag: int = 0
    top_node_tags: tuple[int, int] = (0, 0)
    selection_set_names: tuple[str, ...] = ()
    reinforcement_element_tags: list[int] = field(default_factory=list)
    reinforcement_selection_name: str = ""
    boundary_bar_area: float = 0.0
    boundary_bar_spacing: float = 0.0
    boundary_discrete_rho_y: float = 0.0
    boundary_smeared_rho_y: float = 0.0
    web_horizontal_element_tags: list[int] = field(default_factory=list)
    web_horizontal_discrete_rho_x: float = 0.0
    web_vertical_node_tags: list[int] = field(default_factory=list)
    web_vertical_element_tags: list[int] = field(default_factory=list)
    embedded_coupling_element_tags: list[int] = field(default_factory=list)
    web_vertical_selection_name: str = ""
    embedded_coupling_selection_name: str = ""
    web_vertical_positions: tuple[float, ...] = ()
    web_vertical_actual_spacing: float = 0.0
    web_vertical_discrete_rho_y: float = 0.0
    web_smeared_rho_y: float = 0.0
    embedded_penalty: float = 0.0
    web_smeared_rho_x: float = 0.0
    boundary_smeared_rho_x: float = 0.0


def _next_tags(store: dict[int, object], count: int) -> list[int]:
    candidate = max(store, default=0) + 1
    tags: list[int] = []
    while len(tags) < int(count):
        if candidate not in store:
            tags.append(candidate)
        candidate += 1
    return tags


def _single_bar_area(diameter: float) -> float:
    value = float(diameter)
    return math.pi * value * value / 4.0


def _boundary_bar_area(spec: RCWallSpec) -> float:
    return _single_bar_area(spec.boundary_bar_diameter)


def _boundary_layer_layout(
    spec: RCWallSpec,
) -> tuple[tuple[str, int], ...]:
    count = int(spec.boundary_bar_count)
    mode = str(spec.boundary_layer_mode).strip().lower()
    if mode == "front_back":
        per_face = count // 2
        return (("front", per_face), ("back", per_face))
    return (("center", count),)


def _boundary_bars_per_layer(spec: RCWallSpec) -> int:
    layout = _boundary_layer_layout(spec)
    return max((count for _layer, count in layout), default=0)


def _boundary_bar_spacing(spec: RCWallSpec) -> float:
    count = _boundary_bars_per_layer(spec)
    if count <= 1:
        return 0.0
    clear_span = (
        float(spec.boundary_width)
        - 2.0 * float(spec.boundary_cover)
        - float(spec.boundary_bar_diameter)
    )
    return max(clear_span, 0.0) / float(count - 1)


def _boundary_discrete_area(spec: RCWallSpec) -> float:
    if str(spec.reinforcement_mode).strip().lower() != "hybrid":
        return 0.0
    return int(spec.boundary_bar_count) * _boundary_bar_area(spec)


def _web_horizontal_layer_layout(
    spec: RCWallSpec,
) -> tuple[str, ...]:
    mode = str(spec.web_horizontal_layer_mode).strip().lower()
    return ("front", "back") if mode == "front_back" else ("center",)


def _web_horizontal_discrete_ratio(spec: RCWallSpec) -> float:
    if (
        str(spec.reinforcement_mode).strip().lower() != "hybrid"
        or str(spec.web_horizontal_mode).strip().lower() != "mesh_aligned"
    ):
        return 0.0
    line_count = max(int(spec.vertical_elements) - 1, 0)
    layer_count = len(_web_horizontal_layer_layout(spec))
    steel_area = (
        line_count
        * layer_count
        * _single_bar_area(spec.web_horizontal_bar_diameter)
    )
    gross = float(spec.height) * float(spec.thickness)
    return steel_area / gross if gross > 0.0 else 0.0


def _web_vertical_layer_names(
    spec: RCWallSpec,
) -> tuple[str, ...]:
    mode = str(spec.web_vertical_layer_mode).strip().lower()
    return ("front", "back") if mode == "front_back" else ("center",)


def _web_vertical_positions(spec: RCWallSpec) -> tuple[float, ...]:
    if str(spec.web_vertical_mode).strip().lower() != "embedded":
        return ()
    diameter = float(spec.web_vertical_bar_diameter)
    left = (
        float(spec.boundary_width)
        + float(spec.web_vertical_edge_offset)
        + 0.5 * diameter
    )
    right = (
        float(spec.width)
        - float(spec.boundary_width)
        - float(spec.web_vertical_edge_offset)
        - 0.5 * diameter
    )
    if right < left:
        return ()
    span = right - left
    if span <= 1.0e-12:
        return (left,)
    intervals = max(
        1,
        int(math.ceil(span / float(spec.web_vertical_spacing))),
    )
    return tuple(
        left + span * index / intervals
        for index in range(intervals + 1)
    )


def _web_vertical_actual_spacing(spec: RCWallSpec) -> float:
    positions = _web_vertical_positions(spec)
    if len(positions) < 2:
        return 0.0
    return float(positions[1] - positions[0])


def _web_vertical_discrete_ratio(spec: RCWallSpec) -> float:
    positions = _web_vertical_positions(spec)
    if not positions:
        return 0.0
    web_width = float(spec.width) - 2.0 * float(spec.boundary_width)
    gross = web_width * float(spec.thickness)
    if gross <= 0.0:
        return 0.0
    steel_area = (
        len(positions)
        * len(_web_vertical_layer_names(spec))
        * _single_bar_area(spec.web_vertical_bar_diameter)
    )
    return steel_area / gross


def _embedded_penalty(spec: RCWallSpec) -> float:
    # Concrete02 initial tangent is approximately 2*fpc/epsc0. Store the
    # penalty in SI Pa, matching SARE material storage. The generator converts
    # it to the active project stress unit before writing OpenSees commands.
    concrete_tangent = (
        2.0
        * abs(float(spec.concrete_fc_web))
        / abs(float(spec.concrete_eps_web))
    )
    return concrete_tangent * float(spec.embedded_penalty_factor)


def _boundary_discrete_ratio(spec: RCWallSpec) -> float:
    gross = float(spec.boundary_width) * float(spec.thickness)
    if gross <= 0.0:
        return 0.0
    return _boundary_discrete_area(spec) / gross


def _boundary_smeared_ratio(spec: RCWallSpec) -> float:
    return float(spec.rho_y_boundary) - _boundary_discrete_ratio(spec)


def _validate(spec: RCWallSpec) -> None:
    numeric_values = {
        item.name: float(getattr(spec, item.name))
        for item in fields(spec)
        if isinstance(getattr(spec, item.name), (int, float))
    }
    non_finite = [
        name for name, value in numeric_values.items()
        if not math.isfinite(value)
    ]
    if non_finite:
        raise ValueError(
            "RC wall inputs must be finite: " + ", ".join(non_finite) + "."
        )

    if spec.width <= 0.0 or spec.height <= 0.0 or spec.thickness <= 0.0:
        raise ValueError("RC wall width, height and thickness must be positive.")
    if not 0.0 < spec.boundary_width < 0.5 * spec.width:
        raise ValueError(
            "Boundary width must be positive and smaller than half the wall width."
        )
    if int(spec.vertical_elements) < 1:
        raise ValueError("RC wall needs at least one vertical MEFI element.")
    if int(spec.macro_fibers) < 3:
        raise ValueError(
            "RC wall needs at least three macro-fibers "
            "(boundary + web + boundary)."
        )
    if abs(
        spec.boundary_unconfined_thickness
        + spec.boundary_confined_thickness
        - spec.thickness
    ) > max(1.0e-9, 1.0e-6 * spec.thickness):
        raise ValueError(
            "Boundary unconfined + confined concrete thickness must equal "
            "the wall thickness."
        )
    if (
        spec.boundary_unconfined_thickness <= 0.0
        or spec.boundary_confined_thickness <= 0.0
    ):
        raise ValueError(
            "Boundary unconfined and confined layer thicknesses must "
            "both be positive."
        )

    for name, value in (
        ("steel_E", spec.steel_E),
        ("steel_fx", spec.steel_fx),
        ("steel_fy_web", spec.steel_fy_web),
        ("steel_fy_boundary", spec.steel_fy_boundary),
    ):
        if float(value) <= 0.0:
            raise ValueError(f"{name} must be positive.")

    for name, value in (
        ("steel_bx", spec.steel_bx),
        ("steel_by_web", spec.steel_by_web),
        ("steel_by_boundary", spec.steel_by_boundary),
        ("concrete_ft", spec.concrete_ft),
        ("concrete_ets_web", spec.concrete_ets_web),
        ("concrete_ets_boundary", spec.concrete_ets_boundary),
        ("damage_cte1", spec.damage_cte1),
        ("damage_cte2", spec.damage_cte2),
    ):
        if float(value) < 0.0:
            raise ValueError(f"{name} cannot be negative.")

    for name, value in (
        ("concrete_fc_web", spec.concrete_fc_web),
        ("concrete_fc_boundary", spec.concrete_fc_boundary),
        ("concrete_eps_web", spec.concrete_eps_web),
        ("concrete_eps_boundary", spec.concrete_eps_boundary),
        ("concrete_epsu_web", spec.concrete_epsu_web),
        ("concrete_epsu_boundary", spec.concrete_epsu_boundary),
    ):
        if float(value) >= 0.0:
            raise ValueError(f"{name} must be negative for compression.")

    for name, value in (
        ("concrete_fcu_web", spec.concrete_fcu_web),
        ("concrete_fcu_boundary", spec.concrete_fcu_boundary),
    ):
        if float(value) > 0.0:
            raise ValueError(f"{name} cannot be positive.")

    if not 0.0 <= float(spec.concrete_lambda) <= 1.0:
        raise ValueError("concrete_lambda must satisfy 0 <= lambda <= 1.")
    if float(spec.cracking_strain) <= 0.0:
        raise ValueError("cracking_strain must be positive.")

    for name, value in (
        ("rho_x_web", spec.rho_x_web),
        ("rho_y_web", spec.rho_y_web),
        ("rho_x_boundary", spec.rho_x_boundary),
        ("rho_y_boundary", spec.rho_y_boundary),
    ):
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{name} must be a reinforcement ratio in [0, 1].")

    reinforcement_mode = str(spec.reinforcement_mode).strip().lower()
    if reinforcement_mode not in {"smeared", "hybrid"}:
        raise ValueError(
            "reinforcement_mode must be 'smeared' or 'hybrid'."
        )
    if str(spec.boundary_truss_type) not in {"truss", "corotTruss"}:
        raise ValueError(
            "boundary_truss_type must be 'truss' or 'corotTruss'."
        )
    if str(spec.boundary_layer_mode).strip().lower() not in {
        "single",
        "front_back",
    }:
        raise ValueError(
            "boundary_layer_mode must be 'single' or 'front_back'."
        )
    if str(spec.web_horizontal_mode).strip().lower() not in {
        "smeared",
        "mesh_aligned",
    }:
        raise ValueError(
            "web_horizontal_mode must be 'smeared' or 'mesh_aligned'."
        )
    if str(spec.web_horizontal_layer_mode).strip().lower() not in {
        "single",
        "front_back",
    }:
        raise ValueError(
            "web_horizontal_layer_mode must be 'single' or 'front_back'."
        )
    if str(spec.web_vertical_mode).strip().lower() not in {
        "smeared",
        "embedded",
    }:
        raise ValueError(
            "web_vertical_mode must be 'smeared' or 'embedded'."
        )
    if str(spec.web_vertical_layer_mode).strip().lower() not in {
        "single",
        "front_back",
    }:
        raise ValueError(
            "web_vertical_layer_mode must be 'single' or 'front_back'."
        )
    if float(spec.embedded_penalty_factor) <= 0.0:
        raise ValueError("embedded_penalty_factor must be positive.")

    if (
        reinforcement_mode != "hybrid"
        and str(spec.web_vertical_mode).strip().lower() == "embedded"
    ):
        raise ValueError(
            "Embedded vertical web reinforcement currently requires "
            "reinforcement_mode='hybrid'."
        )

    if reinforcement_mode == "hybrid":
        if int(spec.boundary_bar_count) < 1:
            raise ValueError(
                "Hybrid reinforcement requires at least one longitudinal "
                "bar per boundary zone."
            )
        if float(spec.boundary_bar_diameter) <= 0.0:
            raise ValueError(
                "Hybrid boundary bar diameter must be positive."
            )
        if float(spec.boundary_cover) < 0.0:
            raise ValueError("Boundary clear cover cannot be negative.")
        if (
            str(spec.boundary_layer_mode).strip().lower() == "front_back"
            and int(spec.boundary_bar_count) % 2
        ):
            raise ValueError(
                "Front/back boundary layout requires an even total bar count "
                "per boundary zone."
            )
        if (
            str(spec.boundary_layer_mode).strip().lower() == "front_back"
            and int(spec.boundary_bar_count) < 2
        ):
            raise ValueError(
                "Front/back boundary layout requires at least two bars "
                "per boundary zone."
            )
        if (
            2.0 * float(spec.boundary_cover)
            + float(spec.boundary_bar_diameter)
            > float(spec.boundary_width) + 1.0e-12
        ):
            raise ValueError(
                "Boundary clear cover and bar diameter do not fit inside "
                "the boundary-zone width."
            )
        if (
            str(spec.boundary_layer_mode).strip().lower() == "front_back"
            and (
                2.0 * float(spec.boundary_cover)
                + float(spec.boundary_bar_diameter)
                > float(spec.thickness) + 1.0e-12
            )
        ):
            raise ValueError(
                "Boundary clear cover and bar diameter do not fit through "
                "the wall thickness for front/back layers."
            )

        discrete_ratio = _boundary_discrete_ratio(spec)
        remaining_ratio = _boundary_smeared_ratio(spec)
        tolerance = max(1.0e-12, 1.0e-9 * float(spec.rho_y_boundary))
        if remaining_ratio < -tolerance:
            raise ValueError(
                "Discrete boundary longitudinal steel exceeds the specified "
                "boundary rho-y. Reduce bar count/diameter or increase rho-y."
            )

        if str(spec.web_vertical_mode).strip().lower() == "embedded":
            if float(spec.web_vertical_bar_diameter) <= 0.0:
                raise ValueError(
                    "Embedded vertical web bar diameter must be positive."
                )
            if float(spec.web_vertical_spacing) <= 0.0:
                raise ValueError(
                    "Embedded vertical web bar spacing must be positive."
                )
            if float(spec.web_vertical_edge_offset) < 0.0:
                raise ValueError(
                    "Embedded vertical web edge offset cannot be negative."
                )
            positions = _web_vertical_positions(spec)
            if not positions:
                raise ValueError(
                    "No embedded vertical web bar fits between the boundary "
                    "zones with the selected edge offset and diameter."
                )
            vertical_ratio = _web_vertical_discrete_ratio(spec)
            tolerance_y = max(
                1.0e-12,
                1.0e-9 * float(spec.rho_y_web),
            )
            if float(spec.rho_y_web) - vertical_ratio < -tolerance_y:
                raise ValueError(
                    "Embedded vertical web steel exceeds the available "
                    "smeared rho-y in the web."
                )

        if str(spec.web_horizontal_mode).strip().lower() == "mesh_aligned":
            if int(spec.vertical_elements) < 2:
                raise ValueError(
                    "Mesh-aligned horizontal bars need at least two vertical "
                    "MEFI elements so an internal shared-node row exists."
                )
            if float(spec.web_horizontal_bar_diameter) <= 0.0:
                raise ValueError(
                    "Horizontal web bar diameter must be positive."
                )
            rho_x_discrete = _web_horizontal_discrete_ratio(spec)
            tolerance_x = max(
                1.0e-12,
                1.0e-9 * min(
                    float(spec.rho_x_web),
                    float(spec.rho_x_boundary),
                ),
            )
            if (
                float(spec.rho_x_web) - rho_x_discrete < -tolerance_x
                or float(spec.rho_x_boundary) - rho_x_discrete
                < -tolerance_x
            ):
                raise ValueError(
                    "Mesh-aligned horizontal discrete steel exceeds the "
                    "available smeared rho-x in the web or boundary zone."
                )


def _validate_append_location(
    project: ProjectDatabase,
    spec: RCWallSpec,
) -> None:
    if spec.replace_geometry or not project.model.nodes:
        return

    rows = int(spec.vertical_elements)
    candidate_points = []
    for row in range(rows + 1):
        y = float(spec.origin_y) + float(spec.height) * row / rows
        candidate_points.extend([
            (float(spec.origin_x), y, 0.0),
            (float(spec.origin_x) + float(spec.width), y, 0.0),
        ])

    coordinates = [
        tuple(float(value) for value in node.xyz)
        for node in project.model.nodes.values()
    ]
    span = max(
        float(spec.width),
        float(spec.height),
        1.0,
    )
    tolerance2 = (1.0e-9 * span) ** 2
    for point in candidate_points:
        for existing in coordinates:
            distance2 = sum(
                (point[index] - existing[index]) ** 2
                for index in range(3)
            )
            if distance2 <= tolerance2:
                raise ValueError(
                    "Append wall geometry overlaps an existing model node "
                    f"near ({point[0]:g}, {point[1]:g}). Change Origin X/Y "
                    "or use Replace mode."
                )


def _unique_selection_name(
    project: ProjectDatabase,
    base: str,
) -> str:
    candidate = str(base).strip() or "RC Wall"
    if candidate not in project.selection_sets:
        return candidate
    index = 2
    while f"{candidate} {index}" in project.selection_sets:
        index += 1
    return f"{candidate} {index}"


def build_rc_wall(
    project: ProjectDatabase,
    spec: RCWallSpec,
) -> RCWallBuildResult:
    """Build a planar cantilever RC wall using the OpenSees MEFI workflow."""

    _validate(spec)

    if spec.replace_geometry:
        project.clear_model_linked_data()
        project.model.clear()
        project.model.ndm = 2
        project.model.ndf = 3
    elif (int(project.model.ndm), int(project.model.ndf)) != (2, 3):
        raise ValueError(
            "Appending an RC Wall Wizard V1 wall requires an ndm=2/ndf=3 model."
        )

    _validate_append_location(project, spec)

    material_tags = _next_tags(project.materials, 5)
    sx, syw, syb, c_web, c_bound = material_tags

    steel_common = {
        "E0": float(spec.steel_E),
        "R0": 20.0,
        "cR1": 0.925,
        "cR2": 0.15,
    }
    project.add_material(
        MaterialData(
            sx,
            f"{spec.name} · Steel X",
            "Steel02",
            parameters={
                **steel_common,
                "Fy": float(spec.steel_fx),
                "b": float(spec.steel_bx),
            },
        )
    )
    project.add_material(
        MaterialData(
            syw,
            f"{spec.name} · Steel Y Web",
            "Steel02",
            parameters={
                **steel_common,
                "Fy": float(spec.steel_fy_web),
                "b": float(spec.steel_by_web),
            },
        )
    )
    project.add_material(
        MaterialData(
            syb,
            f"{spec.name} · Steel Y Boundary",
            "Steel02",
            parameters={
                **steel_common,
                "Fy": float(spec.steel_fy_boundary),
                "b": float(spec.steel_by_boundary),
            },
        )
    )
    project.add_material(
        MaterialData(
            c_web,
            f"{spec.name} · Concrete Web",
            "Concrete02",
            parameters={
                "fpc": float(spec.concrete_fc_web),
                "epsc0": float(spec.concrete_eps_web),
                "fpcu": float(spec.concrete_fcu_web),
                "epsU": float(spec.concrete_epsu_web),
                "lambda": float(spec.concrete_lambda),
                "ft": float(spec.concrete_ft),
                "Ets": float(spec.concrete_ets_web),
            },
        )
    )
    project.add_material(
        MaterialData(
            c_bound,
            f"{spec.name} · Concrete Boundary",
            "Concrete02",
            parameters={
                "fpc": float(spec.concrete_fc_boundary),
                "epsc0": float(spec.concrete_eps_boundary),
                "fpcu": float(spec.concrete_fcu_boundary),
                "epsU": float(spec.concrete_epsu_boundary),
                "lambda": float(spec.concrete_lambda),
                "ft": float(spec.concrete_ft),
                "Ets": float(spec.concrete_ets_boundary),
            },
        )
    )

    nd_tags = _next_tags(project.nd_materials, 4)
    ra_web, ra_boundary, steel_web, steel_boundary = nd_tags
    project.add_nd_material(
        NDMaterialData(
            ra_web,
            f"{spec.name} · RA Concrete Web",
            "OrthotropicRAConcrete",
            parameters={
                "conc": float(c_web),
                "ecr": float(spec.cracking_strain),
                "ec": float(spec.concrete_eps_web),
                "rho": 0.0,
                "DamageCte1": float(spec.damage_cte1),
                "DamageCte2": float(spec.damage_cte2),
            },
        )
    )
    project.add_nd_material(
        NDMaterialData(
            ra_boundary,
            f"{spec.name} · RA Concrete Boundary",
            "OrthotropicRAConcrete",
            parameters={
                "conc": float(c_bound),
                "ecr": float(spec.cracking_strain),
                "ec": float(spec.concrete_eps_boundary),
                "rho": 0.0,
                "DamageCte1": float(spec.damage_cte1),
                "DamageCte2": float(spec.damage_cte2),
            },
        )
    )
    web_horizontal_discrete_rho_x = _web_horizontal_discrete_ratio(spec)
    web_vertical_discrete_rho_y = _web_vertical_discrete_ratio(spec)
    web_smeared_rho_y = max(
        0.0,
        float(spec.rho_y_web) - web_vertical_discrete_rho_y,
    )
    web_smeared_rho_x = max(
        0.0,
        float(spec.rho_x_web) - web_horizontal_discrete_rho_x,
    )
    boundary_smeared_rho_x = max(
        0.0,
        float(spec.rho_x_boundary) - web_horizontal_discrete_rho_x,
    )
    project.add_nd_material(
        NDMaterialData(
            steel_web,
            f"{spec.name} · Smeared Steel Web",
            "SmearedSteelDoubleLayer",
            parameters={
                "mat1": float(sx),
                "mat2": float(syw),
                "ratio1": float(web_smeared_rho_x),
                "ratio2": float(web_smeared_rho_y),
                "orientation": 0.0,
            },
        )
    )
    boundary_smeared_rho_y = max(
        0.0,
        _boundary_smeared_ratio(spec),
    )
    boundary_discrete_rho_y = _boundary_discrete_ratio(spec)
    project.add_nd_material(
        NDMaterialData(
            steel_boundary,
            f"{spec.name} · Smeared Steel Boundary",
            "SmearedSteelDoubleLayer",
            parameters={
                "mat1": float(sx),
                "mat2": float(syb),
                "ratio1": float(boundary_smeared_rho_x),
                "ratio2": float(boundary_smeared_rho_y),
                "orientation": 0.0,
            },
        )
    )

    section_tags = _next_tags(project.sections, 2)
    web_section, boundary_section = section_tags
    project.add_section(
        SectionData(
            web_section,
            f"{spec.name} · RCLMS Web",
            "RCLMS",
            nd_material_tag=steel_web,
            shell_layers=[
                ShellLayerData(ra_web, float(spec.thickness)),
            ],
        )
    )
    project.add_section(
        SectionData(
            boundary_section,
            f"{spec.name} · RCLMS Boundary",
            "RCLMS",
            nd_material_tag=steel_boundary,
            shell_layers=[
                ShellLayerData(
                    ra_web,
                    float(spec.boundary_unconfined_thickness),
                ),
                ShellLayerData(
                    ra_boundary,
                    float(spec.boundary_confined_thickness),
                ),
            ],
        )
    )

    model = project.model
    first_node = model.next_node_tag()
    node_tags: list[int] = []
    rows = int(spec.vertical_elements)
    for row in range(rows + 1):
        y = float(spec.origin_y) + float(spec.height) * row / rows
        left = first_node + 2 * row
        right = left + 1
        model.add_node(left, float(spec.origin_x), y, 0.0)
        model.add_node(
            right,
            float(spec.origin_x) + float(spec.width),
            y,
            0.0,
        )
        node_tags.extend([left, right])

    model.nodes[node_tags[0]].fixity = (1, 1, 1)
    model.nodes[node_tags[1]].fixity = (1, 1, 1)

    n_fib = int(spec.macro_fibers)
    web_count = n_fib - 2
    web_width = (
        float(spec.width) - 2.0 * float(spec.boundary_width)
    ) / web_count
    widths = (
        float(spec.boundary_width),
        *([web_width] * web_count),
        float(spec.boundary_width),
    )
    sec_map = (
        boundary_section,
        *([web_section] * web_count),
        boundary_section,
    )

    first_element = project.next_element_tag()
    element_tags: list[int] = []
    for row in range(rows):
        tag = first_element + row
        while tag in model.elements or tag in project.connections:
            tag += 1
        i = node_tags[2 * row]
        j = node_tags[2 * row + 1]
        l = node_tags[2 * (row + 1)]
        k = node_tags[2 * (row + 1) + 1]
        model.add_element(
            tag,
            i,
            j,
            element_type="MEFI",
            group="rc-wall",
            k=k,
            l=l,
            mefi_widths=widths,
            mefi_section_tags=sec_map,
        )
        element_tags.append(tag)

    reinforcement_element_tags: list[int] = []
    web_horizontal_element_tags: list[int] = []
    web_vertical_node_tags: list[int] = []
    web_vertical_element_tags: list[int] = []
    embedded_coupling_element_tags: list[int] = []
    reinforcement_selection_name = ""
    if str(spec.reinforcement_mode).strip().lower() == "hybrid":
        bar_area = _boundary_bar_area(spec)
        next_rebar_tag = project.next_element_tag()

        # Each longitudinal bar receives its own FE element chain. In the
        # current 2D MEFI formulation all bars in one boundary still share
        # the same host edge nodes, which is mechanically equivalent for
        # in-plane axial response while preserving per-bar identity/results.
        for side in (0, 1):
            side_name = "left" if side == 0 else "right"
            for layer_name, layer_count in _boundary_layer_layout(spec):
                for bar_index in range(layer_count):
                    group = (
                        f"rc-wall-rebar-{side_name}-{layer_name}-"
                        f"b{bar_index + 1:02d}of{layer_count:02d}"
                    )
                    for row in range(rows):
                        while (
                            next_rebar_tag in model.elements
                            or next_rebar_tag in project.connections
                        ):
                            next_rebar_tag += 1
                        i = node_tags[2 * row + side]
                        j = node_tags[2 * (row + 1) + side]
                        model.add_element(
                            next_rebar_tag,
                            i,
                            j,
                            element_type=str(spec.boundary_truss_type),
                            group=group,
                            truss_area=float(bar_area),
                            truss_material_tag=int(syb),
                        )
                        reinforcement_element_tags.append(next_rebar_tag)
                        next_rebar_tag += 1

        # Horizontal web steel is safe to discretize only on internal MEFI
        # rows because these bars can share the existing concrete nodes.
        if str(spec.web_horizontal_mode).strip().lower() == "mesh_aligned":
            web_bar_area = _single_bar_area(
                spec.web_horizontal_bar_diameter
            )
            layers = _web_horizontal_layer_layout(spec)
            for row in range(1, rows):
                i = node_tags[2 * row]
                j = node_tags[2 * row + 1]
                for layer_name in layers:
                    while (
                        next_rebar_tag in model.elements
                        or next_rebar_tag in project.connections
                    ):
                        next_rebar_tag += 1
                    model.add_element(
                        next_rebar_tag,
                        i,
                        j,
                        element_type=str(spec.boundary_truss_type),
                        group=(
                            "rc-wall-rebar-web-horizontal-"
                            f"{layer_name}-r{row:02d}"
                        ),
                        truss_area=float(web_bar_area),
                        truss_material_tag=int(sx),
                    )
                    reinforcement_element_tags.append(next_rebar_tag)
                    web_horizontal_element_tags.append(next_rebar_tag)
                    next_rebar_tag += 1

        if str(spec.web_vertical_mode).strip().lower() == "embedded":
            positions = _web_vertical_positions(spec)
            layers = _web_vertical_layer_names(spec)
            vertical_area = _single_bar_area(
                spec.web_vertical_bar_diameter
            )
            penalty = _embedded_penalty(spec)
            next_node_tag = model.next_node_tag()

            for layer_name in layers:
                for bar_index, local_x in enumerate(positions):
                    chain_nodes: list[int] = []
                    for grid_row in range(rows + 1):
                        node_tag = next_node_tag
                        next_node_tag += 1
                        y = (
                            float(spec.origin_y)
                            + float(spec.height) * grid_row / rows
                        )
                        model.add_node(
                            node_tag,
                            float(spec.origin_x) + float(local_x),
                            y,
                            0.0,
                        )
                        web_vertical_node_tags.append(node_tag)
                        chain_nodes.append(node_tag)

                        # Split each MEFI quad along LL -> UR. Base nodes use
                        # the lower triangle; all other row-boundary nodes use
                        # the upper triangle of the row immediately below.
                        if grid_row == 0:
                            host_row = 0
                            retained = (
                                node_tags[2 * host_row],
                                node_tags[2 * host_row + 1],
                                node_tags[2 * (host_row + 1) + 1],
                            )
                        else:
                            host_row = grid_row - 1
                            retained = (
                                node_tags[2 * host_row],
                                node_tags[2 * (host_row + 1) + 1],
                                node_tags[2 * (host_row + 1)],
                            )

                        while (
                            next_rebar_tag in model.elements
                            or next_rebar_tag in project.connections
                        ):
                            next_rebar_tag += 1
                        model.add_element(
                            next_rebar_tag,
                            node_tag,
                            retained[0],
                            element_type="ASDEmbeddedNodeElement",
                            group=(
                                "rc-wall-embedded-coupling-web-vertical-"
                                f"{layer_name}-b{bar_index + 1:02d}-"
                                f"n{grid_row:02d}"
                            ),
                            k=retained[1],
                            l=retained[2],
                            embedded_penalty=float(penalty),
                            embedded_constrain_rotation=True,
                        )
                        embedded_coupling_element_tags.append(
                            next_rebar_tag
                        )
                        next_rebar_tag += 1

                    for row in range(rows):
                        while (
                            next_rebar_tag in model.elements
                            or next_rebar_tag in project.connections
                        ):
                            next_rebar_tag += 1
                        model.add_element(
                            next_rebar_tag,
                            chain_nodes[row],
                            chain_nodes[row + 1],
                            element_type=str(spec.boundary_truss_type),
                            group=(
                                "rc-wall-rebar-web-vertical-"
                                f"{layer_name}-b{bar_index + 1:02d}"
                            ),
                            truss_area=float(vertical_area),
                            truss_material_tag=int(syw),
                        )
                        reinforcement_element_tags.append(next_rebar_tag)
                        web_vertical_element_tags.append(next_rebar_tag)
                        next_rebar_tag += 1

    selection_set_names = (
        _unique_selection_name(project, f"{spec.name} · Base"),
        _unique_selection_name(project, f"{spec.name} · Top"),
        _unique_selection_name(project, f"{spec.name} · MEFI"),
    )
    project.add_selection_set(
        SelectionSetData(
            selection_set_names[0],
            node_tags={node_tags[0], node_tags[1]},
        )
    )
    project.add_selection_set(
        SelectionSetData(
            selection_set_names[1],
            node_tags={node_tags[-2], node_tags[-1]},
        )
    )
    project.add_selection_set(
        SelectionSetData(
            selection_set_names[2],
            element_tags=set(element_tags),
        )
    )
    if reinforcement_element_tags:
        reinforcement_selection_name = _unique_selection_name(
            project,
            f"{spec.name} · Discrete Reinforcement",
        )
        project.add_selection_set(
            SelectionSetData(
                reinforcement_selection_name,
                node_tags=set(web_vertical_node_tags),
                element_tags=set(reinforcement_element_tags),
            )
        )

    web_vertical_selection_name = ""
    if web_vertical_element_tags:
        web_vertical_selection_name = _unique_selection_name(
            project,
            f"{spec.name} · Vertical Web Bars",
        )
        project.add_selection_set(
            SelectionSetData(
                web_vertical_selection_name,
                node_tags=set(web_vertical_node_tags),
                element_tags=set(web_vertical_element_tags),
            )
        )

    embedded_coupling_selection_name = ""
    if embedded_coupling_element_tags:
        coupling_selection_name = _unique_selection_name(
            project,
            f"{spec.name} · Embedded Coupling",
        )
        embedded_coupling_selection_name = coupling_selection_name
        project.add_selection_set(
            SelectionSetData(
                coupling_selection_name,
                element_tags=set(embedded_coupling_element_tags),
            )
        )

    return RCWallBuildResult(
        node_tags=node_tags,
        element_tags=element_tags,
        material_tags=material_tags,
        nd_material_tags=nd_tags,
        section_tags=section_tags,
        web_section_tag=web_section,
        boundary_section_tag=boundary_section,
        top_node_tags=(node_tags[-2], node_tags[-1]),
        selection_set_names=selection_set_names,
        reinforcement_element_tags=reinforcement_element_tags,
        reinforcement_selection_name=reinforcement_selection_name,
        boundary_bar_area=float(_boundary_bar_area(spec))
        if str(spec.reinforcement_mode).strip().lower() == "hybrid"
        else 0.0,
        boundary_bar_spacing=float(_boundary_bar_spacing(spec))
        if str(spec.reinforcement_mode).strip().lower() == "hybrid"
        else 0.0,
        boundary_discrete_rho_y=float(boundary_discrete_rho_y),
        boundary_smeared_rho_y=float(boundary_smeared_rho_y),
        web_horizontal_element_tags=web_horizontal_element_tags,
        web_horizontal_discrete_rho_x=float(
            web_horizontal_discrete_rho_x
        ),
        web_vertical_node_tags=web_vertical_node_tags,
        web_vertical_element_tags=web_vertical_element_tags,
        embedded_coupling_element_tags=embedded_coupling_element_tags,
        web_vertical_selection_name=web_vertical_selection_name,
        embedded_coupling_selection_name=embedded_coupling_selection_name,
        web_vertical_positions=tuple(_web_vertical_positions(spec)),
        web_vertical_actual_spacing=float(
            _web_vertical_actual_spacing(spec)
        ),
        web_vertical_discrete_rho_y=float(
            web_vertical_discrete_rho_y
        ),
        web_smeared_rho_y=float(web_smeared_rho_y),
        embedded_penalty=float(_embedded_penalty(spec))
        if str(spec.web_vertical_mode).strip().lower() == "embedded"
        else 0.0,
        web_smeared_rho_x=float(web_smeared_rho_x),
        boundary_smeared_rho_x=float(boundary_smeared_rho_x),
    )
