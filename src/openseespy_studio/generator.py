from __future__ import annotations

from dataclasses import dataclass
import math

from .beam_loads import resolve_self_weight_local
from .units import UnitSystem
from .model import StructuralModel
from .project import MATERIAL_PARAMETER_ORDER, AnalysisSettingsData, ConnectionData, ConstraintData, ElementLoadData, FiberComponentData, LoadPatternData, MaterialData, NodalLoadData, PrescribedDisplacementData, RecorderData, SectionData, TimeSeriesData, TransformationData
from .section_response import automatic_moment_curvature_spec, build_section_response_specs


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

    if material.material_type == "Hysteretic":
        args = [
            p["s1p"], p["e1p"], p["s2p"], p["e2p"], p["s3p"], p["e3p"],
            p["s1n"], p["e1n"], p["s2n"], p["e2n"], p["s3n"], p["e3n"],
            p["pinchX"], p["pinchY"], p["damage1"], p["damage2"], p["beta"],
        ]
        return "ops.uniaxialMaterial('Hysteretic', " + str(material.tag) + ", " + ", ".join(f"{v:g}" for v in args) + ")"

    if material.material_type == "HystereticSmooth":
        return (
            "ops.uniaxialMaterial('HystereticSmooth', "
            f"{material.tag}, {p['ka']:g}, {p['kb']:g}, "
            f"{p['fbar']:g}, {p['beta']:g})"
        )

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

def analysis_to_openseespy(
    settings: AnalysisSettingsData,
    *,
    ndm: int = 3,
    node_tags: list[int] | None = None,
    element_tags: list[int] | None = None,
    frame_element_tags: list[int] | None = None,
    truss_element_tags: list[int] | None = None,
    support_node_tags: list[int] | None = None,
    plain_pattern_tags: list[int] | None = None,
    monitor_node: int | None = None,
    fiber_response_specs: dict[int, dict[str, object]] | None = None,
    specimen_response_spec: dict[str, object] | None = None,
    moment_curvature_spec: dict[str, object] | None = None,
    section_response_specs: list[dict[str, object]] | None = None,
) -> list[str]:
    ndm = int(ndm)
    translational_dofs = tuple(range(1, max(ndm, 0) + 1))
    node_tags = list(node_tags or [])
    element_tags = list(element_tags or [])
    frame_element_tags = list(frame_element_tags or [])
    truss_element_tags = list(truss_element_tags or [])
    support_node_tags = list(support_node_tags or [])
    plain_pattern_tags = list(plain_pattern_tags or [])
    fiber_response_specs = dict(fiber_response_specs or {})
    specimen_response_spec = dict(specimen_response_spec or {})
    moment_curvature_spec = dict(moment_curvature_spec or {})
    section_response_specs = [
        dict(spec) for spec in (section_response_specs or [])
    ]
    section_response_catalog = {
        str(spec.get('key', f'response:{index}')): dict(spec)
        for index, spec in enumerate(section_response_specs)
    }
    section_response_history = {
        key: {'force': [], 'deformation': []}
        for key in section_response_catalog
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
        "    'schema_version': 12,",
        "    'analysis': {",
        f"        'tag': {settings.tag},",
        f"        'name': {settings.name!r},",
        f"        'type': {settings.analysis_type!r},",
        f"        'constraints_handler': {settings.constraints_handler!r},",
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
        "    'moment_curvature': " + repr(moment_curvature_spec) + ",",
        "    'section_responses': " + repr(section_response_catalog) + ",",
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
        "'moment_curvature': {'force': [], 'deformation': []}, "
        "'section_responses': " + repr(section_response_history) + ", "
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
        f"_studio_moment_curvature_spec = {moment_curvature_spec!r}",
        f"_studio_section_response_specs = {section_response_catalog!r}",
        f"_studio_monitor_node = {monitor_node}",
        f"ops.constraints('{settings.constraints_handler}')",
        f"ops.numberer('{settings.numberer}')",
        system_command,
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

    _studio_print_flag = 1 if settings.live_convergence else 0
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
    solution_results: dict[int, object] | None = None,
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
        missing = [
            int(tag)
            for tag in (element.i, element.j)
            if int(tag) not in model.nodes
        ]
        if missing:
            geometry_reference_errors.append(
                f"element {element.tag} -> missing node "
                + ", ".join(map(str, sorted(set(missing))))
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
            if length2 <= 1.0e-24:
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
        "forceBeamColumn",
        "dispBeamColumn",
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
            vx, vy, vz = (
                float(value) for value in transformation.vecxz
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
                    model.ndm,
                )
            )

    if transformations:
        lines.extend(["", "# Geometric transformations"])
        for tag in sorted(transformations):
            lines.append(
                transformation_to_openseespy(
                    transformations[tag],
                    model.ndm,
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

        lines.extend(
            analysis_to_openseespy(
                active,
                ndm=model.ndm,
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
            )
        )

    lines.extend(["", "print('Model generated by OpenSeesPy Studio MVP')"])
    return "\n".join(lines) + "\n"
