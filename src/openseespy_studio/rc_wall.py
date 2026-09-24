from __future__ import annotations

from dataclasses import dataclass, field

from .project import (
    MaterialData,
    NDMaterialData,
    ProjectDatabase,
    SectionData,
    ShellLayerData,
)


@dataclass(slots=True)
class RCWallSpec:
    """Planar 2D reinforced-concrete wall built with RCLMS + MEFI."""

    width: float = 1220.0
    height: float = 2209.8
    thickness: float = 152.4
    boundary_width: float = 228.6
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

    boundary_unconfined_thickness: float = 50.8
    boundary_confined_thickness: float = 101.6

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


def _next_tags(store: dict[int, object], count: int) -> list[int]:
    candidate = max(store, default=0) + 1
    tags: list[int] = []
    while len(tags) < int(count):
        if candidate not in store:
            tags.append(candidate)
        candidate += 1
    return tags


def _validate(spec: RCWallSpec) -> None:
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
    for name, value in (
        ("rho_x_web", spec.rho_x_web),
        ("rho_y_web", spec.rho_y_web),
        ("rho_x_boundary", spec.rho_x_boundary),
        ("rho_y_boundary", spec.rho_y_boundary),
    ):
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{name} must be a reinforcement ratio in [0, 1].")


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
    project.add_nd_material(
        NDMaterialData(
            steel_boundary,
            f"{spec.name} · Smeared Steel Boundary",
            "SmearedSteelDoubleLayer",
            parameters={
                "mat1": float(sx),
                "mat2": float(syb),
                "ratio1": float(spec.rho_x_boundary),
                "ratio2": float(spec.rho_y_boundary),
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
        y = float(spec.height) * row / rows
        left = first_node + 2 * row
        right = left + 1
        model.add_node(left, 0.0, y, 0.0)
        model.add_node(right, float(spec.width), y, 0.0)
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

    return RCWallBuildResult(
        node_tags=node_tags,
        element_tags=element_tags,
        material_tags=material_tags,
        nd_material_tags=nd_tags,
        section_tags=section_tags,
        web_section_tag=web_section,
        boundary_section_tag=boundary_section,
        top_node_tags=(node_tags[-2], node_tags[-1]),
    )
