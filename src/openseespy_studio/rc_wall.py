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
    boundary_discrete_rho_y: float = 0.0
    boundary_smeared_rho_y: float = 0.0


def _next_tags(store: dict[int, object], count: int) -> list[int]:
    candidate = max(store, default=0) + 1
    tags: list[int] = []
    while len(tags) < int(count):
        if candidate not in store:
            tags.append(candidate)
        candidate += 1
    return tags


def _boundary_discrete_area(spec: RCWallSpec) -> float:
    if str(spec.reinforcement_mode).strip().lower() != "hybrid":
        return 0.0
    diameter = float(spec.boundary_bar_diameter)
    count = int(spec.boundary_bar_count)
    return count * math.pi * diameter * diameter / 4.0


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
        discrete_ratio = _boundary_discrete_ratio(spec)
        remaining_ratio = _boundary_smeared_ratio(spec)
        tolerance = max(1.0e-12, 1.0e-9 * float(spec.rho_y_boundary))
        if remaining_ratio < -tolerance:
            raise ValueError(
                "Discrete boundary longitudinal steel exceeds the specified "
                "boundary rho-y. Reduce bar count/diameter or increase rho-y."
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
    project.add_nd_material(
        NDMaterialData(
            steel_web,
            f"{spec.name} · Smeared Steel Web",
            "SmearedSteelDoubleLayer",
            parameters={
                "mat1": float(sx),
                "mat2": float(syw),
                "ratio1": float(spec.rho_x_web),
                "ratio2": float(spec.rho_y_web),
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
                "ratio1": float(spec.rho_x_boundary),
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
    reinforcement_selection_name = ""
    if str(spec.reinforcement_mode).strip().lower() == "hybrid":
        discrete_area = _boundary_discrete_area(spec)
        next_rebar_tag = project.next_element_tag()
        for side in (0, 1):
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
                    group="rc-wall-rebar",
                    truss_area=float(discrete_area),
                    truss_material_tag=int(syb),
                )
                reinforcement_element_tags.append(next_rebar_tag)
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
            f"{spec.name} · Discrete Boundary Steel",
        )
        project.add_selection_set(
            SelectionSetData(
                reinforcement_selection_name,
                element_tags=set(reinforcement_element_tags),
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
        boundary_discrete_rho_y=float(boundary_discrete_rho_y),
        boundary_smeared_rho_y=float(boundary_smeared_rho_y),
    )
