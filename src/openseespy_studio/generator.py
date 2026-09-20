from __future__ import annotations

from dataclasses import dataclass
import math

from .beam_loads import resolve_self_weight_local
from .units import UnitSystem
from .model import StructuralModel
from .project import MATERIAL_PARAMETER_ORDER, AnalysisSettingsData, ConnectionData, ConstraintData, ElementLoadData, FiberComponentData, LoadPatternData, MaterialData, NodalLoadData, PrescribedDisplacementData, RecorderData, SectionData, TimeSeriesData, TransformationData


@dataclass(slots=True)
class FrameGridSpec:
    nx: int = 4
    ny: int = 3
    nz: int = 3
    dx: float = 5.0
    dy: float = 6.0
    dz: float = 3.5
    start_node_tag: int = 1
    start_element_tag: int = 1
    create_columns: bool = True
    create_beams_x: bool = True
    create_beams_y: bool = True
    column_section_tag: int | None = None
    beam_section_tag: int | None = None
    column_transf_tag: int | None = None
    beam_transf_tag: int | None = None
    planar_2d: bool = False
    planar_base_support: str = "Fixed"


def generate_frame_grid(model: StructuralModel, spec: FrameGridSpec) -> None:
    """Create a regular frame grid.

    Standard mode creates a 3-D X-Y-Z frame. Planar mode creates an X-Z
    frame while retaining the Studio 3-D / 6-DOF backend and automatically
    restraining all out-of-plane DOFs.
    """
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
                    i * spec.dx,
                    0.0,
                    k * spec.dz,
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
                        section_tag=spec.column_section_tag,
                        transf_tag=spec.column_transf_tag,
                        group="column-2d",
                    )
                    ele_tag += 1

        if spec.create_beams_x:
            for k in range(1, spec.nz + 1):
                for i in range(spec.nx):
                    model.add_element(
                        ele_tag,
                        node_at_2d[(i, k)],
                        node_at_2d[(i + 1, k)],
                        section_tag=spec.beam_section_tag,
                        transf_tag=spec.beam_transf_tag,
                        group="beam-2d",
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
                model.add_node(node_tag, i * spec.dx, j * spec.dy, k * spec.dz)
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
                        section_tag=spec.column_section_tag,
                        transf_tag=spec.column_transf_tag,
                        group="column",
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
                        section_tag=spec.beam_section_tag,
                        transf_tag=spec.beam_transf_tag,
                        group="beam-x",
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
                        section_tag=spec.beam_section_tag,
                        transf_tag=spec.beam_transf_tag,
                        group="beam-y",
                    )
                    ele_tag += 1

    for j in range(spec.ny + 1):
        for i in range(spec.nx + 1):
            model.set_fixity(node_at[(i, j, 0)], (1, 1, 1, 1, 1, 1))


def material_to_openseespy(
    material: MaterialData,
    units: dict[str, str] | None = None,
) -> str:
    p = material.parameters
    unit_system = UnitSystem.from_mapping(units)
    stress = unit_system.stress_from_pa

    if material.material_type == "Elastic":
        return f"ops.uniaxialMaterial('Elastic', {material.tag}, {stress(p['E']):g})"

    if material.material_type == "Steel01":
        return (
            "ops.uniaxialMaterial('Steel01', "
            f"{material.tag}, {stress(p['Fy']):g}, {stress(p['E0']):g}, "
            f"{p['b']:g}, {p['a1']:g}, {p['a2']:g}, {p['a3']:g}, {p['a4']:g})"
        )

    if material.material_type == "Steel02":
        return (
            "ops.uniaxialMaterial('Steel02', "
            f"{material.tag}, {stress(p['Fy']):g}, {stress(p['E0']):g}, {p['b']:g}, "
            f"{p['R0']:g}, {p['cR1']:g}, {p['cR2']:g})"
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

    if material.material_type == "Hysteretic":
        args = [
            p["s1p"], p["e1p"], p["s2p"], p["e2p"], p["s3p"], p["e3p"],
            p["s1n"], p["e1n"], p["s2n"], p["e2n"], p["s3n"], p["e3n"],
            p["pinchX"], p["pinchY"], p["damage1"], p["damage2"], p["beta"],
        ]
        return "ops.uniaxialMaterial('Hysteretic', " + str(material.tag) + ", " + ", ".join(f"{v:g}" for v in args) + ")"

    if material.material_type == "Pinching4":
        keys = MATERIAL_PARAMETER_ORDER["Pinching4"][:-1]
        args = ", ".join(f"{p[key]:g}" for key in keys)
        dmg_type = "cycle" if p["dmgType"] < 0.5 else "energy"
        return f"ops.uniaxialMaterial('Pinching4', {material.tag}, {args}, {dmg_type!r})"

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
    *,
    ndm: int = 3,
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

    if section.section_type == "Fiber":
        lines = (
            [f"ops.section('Fiber', {section.tag})"]
            if int(ndm) == 2
            else [f"ops.section('Fiber', {section.tag}, '-GJ', {p['GJ']:g})"]
        )

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


def connection_to_openseespy(connection: ConnectionData) -> str:
    ox = ", ".join(f"{value:g}" for value in connection.orient_x)
    oy = ", ".join(f"{value:g}" for value in connection.orient_y)

    if connection.connection_type == "zeroLengthSection":
        return (
            "ops.element('zeroLengthSection', "
            f"{connection.tag}, {connection.node_i}, {connection.node_j}, "
            f"{connection.section_tag}, '-orient', {ox}, {oy}, "
            f"'-doRayleigh', {1 if connection.do_rayleigh else 0})"
        )

    directions = sorted(connection.materials_by_dof)
    materials = [connection.materials_by_dof[dof] for dof in directions]

    mat_text = ", ".join(str(tag) for tag in materials)
    dir_text = ", ".join(str(dof) for dof in directions)
    return (
        f"ops.element('{connection.connection_type}', {connection.tag}, "
        f"{connection.node_i}, {connection.node_j}, "
        f"'-mat', {mat_text}, '-dir', {dir_text}, "
        f"'-orient', {ox}, {oy}, "
        f"'-doRayleigh', {1 if connection.do_rayleigh else 0})"
    )


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
    if load.load_type == "Uniform":
        wx, wy, wz = load.wx, load.wy, load.wz
    elif load.load_type == "Point":
        if int(model.ndm) == 2:
            return (
                "ops.eleLoad('-ele', "
                f"{load.element_tag}, '-type', '-beamPoint', "
                f"{load.py:g}, {load.x_over_l:g}, {load.px:g})"
            )
        return (
            "ops.eleLoad('-ele', "
            f"{load.element_tag}, '-type', '-beamPoint', "
            f"{load.py:g}, {load.pz:g}, {load.x_over_l:g}, {load.px:g})"
        )
    elif load.load_type == "SelfWeight":
        wx, wy, wz = resolve_self_weight_local(
            load,
            model,
            sections or {},
            materials or {},
            transformations or {},
            units,
        )
    else:
        raise ValueError(
            f"Unsupported element load type: {load.load_type}"
        )

    if int(model.ndm) == 2:
        return (
            "ops.eleLoad('-ele', "
            f"{load.element_tag}, '-type', '-beamUniform', "
            f"{wy:g}, {wx:g})"
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
        lines.append(prefix + f", {recorder.response!r})")
        return lines
    if recorder.recorder_type == "Section":
        lines.append(
            prefix
            + f", 'section', {recorder.section_number}, "
            + f"{recorder.response!r})"
        )
        return lines

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
        tuple(float(value) for value in transformation.vecxz)
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
            material_types={"Steel01", "Steel02", "ReinforcingSteel"},
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


def analysis_to_openseespy(
    settings: AnalysisSettingsData,
    *,
    node_tags: list[int] | None = None,
    element_tags: list[int] | None = None,
    frame_element_tags: list[int] | None = None,
    truss_element_tags: list[int] | None = None,
    support_node_tags: list[int] | None = None,
    plain_pattern_tags: list[int] | None = None,
    monitor_node: int | None = None,
    fiber_response_specs: dict[int, dict[str, object]] | None = None,
    specimen_response_spec: dict[str, object] | None = None,
) -> list[str]:
    node_tags = list(node_tags or [])
    element_tags = list(element_tags or [])
    frame_element_tags = list(frame_element_tags or [])
    truss_element_tags = list(truss_element_tags or [])
    support_node_tags = list(support_node_tags or [])
    plain_pattern_tags = list(plain_pattern_tags or [])
    fiber_response_specs = dict(fiber_response_specs or {})
    specimen_response_spec = dict(specimen_response_spec or {})
    cyclic_steps = (
        cyclic_displacement_steps(
            settings.cyclic_targets,
            settings.cyclic_increment,
        )
        if settings.analysis_type == "Cyclic"
        else []
    )
    total_steps = len(cyclic_steps) if settings.analysis_type == "Cyclic" else settings.steps
    if monitor_node is None and (
        settings.analysis_type in {"Pushover", "Cyclic"}
        or (
            settings.analysis_type == "Static"
            and settings.integrator == "DisplacementControl"
        )
    ):
        monitor_node = settings.control_node
    monitor_node = int(monitor_node or (node_tags[0] if node_tags else 1))

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
        "    'schema_version': 11,",
        "    'analysis': {",
        f"        'tag': {settings.tag},",
        f"        'name': {settings.name!r},",
        f"        'type': {settings.analysis_type!r},",
        f"        'constraints_handler': {settings.constraints_handler!r},",
        f"        'numberer': {settings.numberer!r},",
        f"        'system': {settings.system!r},",
        f"        'test': {settings.test!r},",
        f"        'tolerance': {settings.tolerance:g},",
        f"        'max_iterations': {settings.max_iterations},",
        f"        'algorithm': {settings.algorithm!r},",
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
        f"        'eigen_solver': {settings.eigen_solver!r},"
        "    },",
        "    'specimen': " + repr(specimen_response_spec) + ",",
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
        f"_studio_support_node_tags = {support_node_tags!r}",
        f"_studio_plain_pattern_tags = {plain_pattern_tags!r}",
        f"_studio_fiber_response_specs = {fiber_response_specs!r}",
        f"_studio_specimen_response_spec = {specimen_response_spec!r}",
        f"_studio_monitor_node = {monitor_node}",
        f"ops.constraints('{settings.constraints_handler}')",
        f"ops.numberer('{settings.numberer}')",
        f"ops.system('{settings.system}')",
    ]

    if (
        settings.analysis_type == "Transient"
        and settings.rayleigh_damping_ratio > 0.0
    ):
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
                f"_studio_lambda_i = float(_studio_damping_eigs["
                f"{settings.rayleigh_mode_i - 1}])"
            ),
            (
                f"_studio_lambda_j = float(_studio_damping_eigs["
                f"{settings.rayleigh_mode_j - 1}])"
            ),
            "_studio_omega_i = math.sqrt(max(_studio_lambda_i, 0.0))",
            "_studio_omega_j = math.sqrt(max(_studio_lambda_j, 0.0))",
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
            "_studio_total_lumped_mass = {}",
            "for _studio_dof in (1, 2, 3):",
            "    _studio_mass_total = 0.0",
            "    for _studio_node in _studio_node_tags:",
            "        try:",
            "            _studio_mass_total += max(",
            "                0.0, float(ops.nodeMass(_studio_node, _studio_dof))",
            "            )",
            "        except Exception:",
            "            pass",
            "    _studio_total_lumped_mass[str(_studio_dof)] = _studio_mass_total",
            "_studio_results['modal_summary'] = {",
            f"    'eigen_solver': {settings.eigen_solver!r},",
            "    'total_lumped_mass': dict(_studio_total_lumped_mass),",
            "}",
        ])
        lines.append(
            "for _studio_mode, _studio_lambda in "
            "enumerate(_studio_eigenvalues, start=1):"
        )
        lines.extend([
            "    _studio_lambda = float(_studio_lambda)",
            "    _studio_omega = math.sqrt(max(_studio_lambda, 0.0))",
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
            "    for _studio_dof in (1, 2, 3):",
            "        _studio_num = 0.0",
            "        _studio_den = 0.0",
            "        for _studio_node in _studio_node_tags:",
            "            try:",
            "                _studio_mass = max(",
            "                    0.0, float(ops.nodeMass(_studio_node, _studio_dof))",
            "                )",
            "            except Exception:",
            "                _studio_mass = 0.0",
            "            _studio_vector = _studio_vectors.get(str(_studio_node), [])",
            "            _studio_phi = (",
            "                float(_studio_vector[_studio_dof - 1])",
            "                if len(_studio_vector) >= _studio_dof",
            "                else 0.0",
            "            )",
            "            _studio_num += _studio_mass * _studio_phi",
            "            _studio_den += _studio_mass * _studio_phi * _studio_phi",
            "        _studio_gamma = (",
            "            _studio_num / _studio_den",
            "            if _studio_den > 0.0 else 0.0",
            "        )",
            "        _studio_effective_mass = (",
            "            (_studio_num * _studio_num) / _studio_den",
            "            if _studio_den > 0.0 else 0.0",
            "        )",
            "        _studio_total_mass = _studio_total_lumped_mass[str(_studio_dof)]",
            "        _studio_mass_ratio = (",
            "            _studio_effective_mass / _studio_total_mass",
            "            if _studio_total_mass > 0.0 else 0.0",
            "        )",
            "        _studio_participation[str(_studio_dof)] = {",
            "            'factor': float(_studio_gamma),",
            "            'effective_mass': float(_studio_effective_mass),",
            "            'mass_ratio': float(_studio_mass_ratio),",
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

    _studio_print_flag = 1 if settings.live_convergence else 0
    lines.append(
        f"ops.test('{settings.test}', {settings.tolerance:g}, "
        f"{settings.max_iterations}, {_studio_print_flag})"
    )
    lines.append(f"ops.algorithm('{settings.algorithm}')")
    lines.append(f"_studio_primary_algorithm = {settings.algorithm!r}")

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
        f"live_convergence={settings.live_convergence!r}, "
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
            "    _studio_emit('step_start', step=_studio_step_no, "
            f"total={total_steps}, algorithm=_studio_primary_algorithm, "
            f"test={settings.test!r}, tolerance={settings.tolerance:g}, "
            f"live_convergence={settings.live_convergence!r}, "
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
        lines.append("        ops.algorithm(_studio_primary_algorithm)")

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

        if settings.recovery:
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
            "                ops.algorithm(_studio_primary_algorithm)"
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
        lines.append("        ops.algorithm(_studio_primary_algorithm)")
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
            "    _studio_emit('step_start', step=_studio_step_no, "
            f"total={total_steps}, algorithm=_studio_primary_algorithm, "
            f"test={settings.test!r}, tolerance={settings.tolerance:g}, "
            f"live_convergence={settings.live_convergence!r})"
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
    
        if settings.recovery:
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
            lines.append("        ops.algorithm(_studio_primary_algorithm)")
    
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
    lines.append(
        "    _studio_disp = "
        "[float(v) for v in ops.nodeDisp(_studio_monitor_node)]"
    )
    lines.append(
        "    _studio_results['history']['displacement'].append(_studio_disp)"
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
        "_studio_interface_tag, 'force') or []"
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
        "_studio_interface_tag, 'deformation') or []"
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
        "    _studio_emit('progress', step=_studio_step_no, "
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
        "    'element_fiber_responses': _studio_element_fiber_responses,",
        "    'load_factors': _studio_load_factors,",
        "}",
        "print('Analysis completed:', "
        f"{settings.analysis_type!r}, {total_steps}, 'step(s)')",
    ])
    return lines

def transformation_to_openseespy(
    transformation: TransformationData,
    *,
    ndm: int = 3,
) -> str:
    if int(ndm) == 2:
        return (
            f"ops.geomTransf('{transformation.transformation_type}', "
            f"{transformation.tag})"
        )
    x, y, z = transformation.vecxz
    return (
        f"ops.geomTransf('{transformation.transformation_type}', "
        f"{transformation.tag}, {x:g}, {y:g}, {z:g})"
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
    missing_deferred = sorted(
        deferred_pattern_tags - set((load_patterns or {}).keys())
    )
    if missing_deferred:
        raise ValueError(
            "Analysis references missing driving load pattern tag(s): "
            + ", ".join(map(str, missing_deferred))
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

    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        coordinates = tuple(node.xyz[:model.ndm])
        coordinate_text = ", ".join(f"{value:g}" for value in coordinates)
        lines.append(f"ops.node({tag}, {coordinate_text})")

    mass_nodes = [
        tag for tag, node in model.nodes.items()
        if any(abs(value) > 0.0 for value in node.mass)
    ]
    if mass_nodes:
        lines.extend(["", "# Nodal masses"])
        for tag in sorted(mass_nodes):
            mass = ", ".join(
                f"{value:g}"
                for value in model.nodes[tag].mass[:model.ndf]
            )
            lines.append(f"ops.mass({tag}, {mass})")

    lines.extend(["", "# Boundary conditions"])
    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        if any(node.fixity):
            fix = ", ".join(
                str(v) for v in node.fixity[:model.ndf]
            )
            lines.append(f"ops.fix({tag}, {fix})")

    if constraints:
        lines.extend(["", "# Multi-point constraints"])
        for tag in sorted(constraints):
            lines.extend(constraint_to_openseespy(constraints[tag]))

    if materials:
        lines.extend(["", "# Materials"])
        for tag in ordered_material_tags(materials):
            lines.append(material_to_openseespy(materials[tag], units))

    if sections:
        lines.extend(["", "# Sections"])
        for tag in sorted(sections):
            lines.extend(
                section_to_openseespy(
                    sections[tag],
                    materials,
                    units,
                    ndm=model.ndm,
                )
            )

    if transformations:
        lines.extend(["", "# Geometric transformations"])
        for tag in sorted(transformations):
            lines.append(
                transformation_to_openseespy(
                    transformations[tag],
                    ndm=model.ndm,
                )
            )

    lines.extend([
        "",
        "# Elements",
    ])
    for tag in sorted(model.elements):
        e = model.elements[tag]

        if e.element_type == "truss":
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

            args = (
                "ops.element('Truss', "
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

        if e.element_type == "elasticBeamColumn":
            if assigned_section.section_type != "Elastic":
                lines.append(
                    f"# ERROR: elasticBeamColumn element {tag} requires an "
                    "Elastic section in the current Studio generator; "
                    "element not generated."
                )
                continue
            p = elastic_section_parameters_in_model_units(
                assigned_section,
                materials,
                units,
            )
            if int(model.ndm) == 2:
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

    if connections:
        lines.extend(["", "# Connections / springs / links"])
        for tag in sorted(connections):
            lines.append(connection_to_openseespy(connections[tag]))

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

    displacement_by_pattern: dict[int, list[PrescribedDisplacementData]] = {}
    for displacement in (prescribed_displacements or {}).values():
        displacement_by_pattern.setdefault(
            displacement.pattern_tag,
            [],
        ).append(displacement)

    if (
        active_analysis is not None
        and active_analysis.analysis_type in {"Pushover", "Cyclic"}
    ):
        invalid_driver_patterns = sorted(
            tag
            for tag in deferred_pattern_tags
            if displacement_by_pattern.get(tag)
        )
        if invalid_driver_patterns:
            raise ValueError(
                "Pushover/Cyclic driving load pattern(s) cannot contain "
                "Prescribed Displacement objects: "
                + ", ".join(map(str, invalid_driver_patterns))
                + ". Use a force reference-load pattern for "
                "DisplacementControl."
            )

    if load_patterns:
        lines.extend(["", "# Load patterns"])
        for tag in sorted(load_patterns):
            if tag in deferred_pattern_tags:
                continue
            pattern = load_patterns[tag]
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
                )
            )

    if recorders:
        lines.extend(["", "# Recorders"])
        for tag in sorted(recorders):
            recorder = recorders[tag]
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
            )
        )
        if active.preload_gravity and preload_plain_tags:
            gravity_increment = 1.0 / active.gravity_steps
            lines.extend([
                "",
                "# Template sequence: gravity / existing Plain-load preload",
                f"ops.constraints({active.constraints_handler!r})",
                f"ops.numberer({active.numberer!r})",
                f"ops.system({active.system!r})",
                (
                    f"ops.test({active.test!r}, {active.tolerance:g}, "
                    f"{active.max_iterations}, 0)"
                ),
                f"ops.algorithm({active.algorithm!r})",
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

        if deferred_pattern_tags:
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
            set(model.elements) | set((connections or {}).keys())
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

        lines.extend(
            analysis_to_openseespy(
                active,
                node_tags=sorted(model.nodes),
                element_tags=result_element_tags,
                frame_element_tags=sorted(
                    tag
                    for tag, element in model.elements.items()
                    if element.element_type in {
                        "elasticBeamColumn",
                        "forceBeamColumn",
                        "dispBeamColumn",
                    }
                ),
                truss_element_tags=sorted(
                    tag
                    for tag, element in model.elements.items()
                    if element.element_type == "truss"
                ),
                support_node_tags=support_node_tags,
                plain_pattern_tags=sorted(
                    tag
                    for tag, pattern in (load_patterns or {}).items()
                    if pattern.pattern_type == "Plain"
                ),
                monitor_node=monitor_node,
                fiber_response_specs=fiber_response_specs,
                specimen_response_spec=specimen_response_spec,
            )
        )

    lines.extend(["", "print('Model generated by OpenSeesPy Studio MVP')"])
    return "\n".join(lines) + "\n"
