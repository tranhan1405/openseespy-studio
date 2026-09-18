from __future__ import annotations

from dataclasses import dataclass

from .model import StructuralModel
from .project import ConnectionData, ConstraintData, LoadPatternData, MaterialData, NodalLoadData, SectionData, TimeSeriesData, TransformationData


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


def generate_frame_grid(model: StructuralModel, spec: FrameGridSpec) -> None:
    """Create a regular 3-D frame grid.

    nx/ny are bay counts, nz is storey count. Ground-level nodes are included.
    """
    model.clear()
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


def material_to_openseespy(material: MaterialData) -> str:
    p = material.parameters
    if material.material_type == "Elastic":
        return f"ops.uniaxialMaterial('Elastic', {material.tag}, {p['E']:g})"
    if material.material_type == "Steel02":
        return (
            "ops.uniaxialMaterial('Steel02', "
            f"{material.tag}, {p['Fy']:g}, {p['E0']:g}, {p['b']:g}, "
            f"{p['R0']:g}, {p['cR1']:g}, {p['cR2']:g})"
        )
    if material.material_type == "Concrete02":
        return (
            "ops.uniaxialMaterial('Concrete02', "
            f"{material.tag}, {p['fpc']:g}, {p['epsc0']:g}, "
            f"{p['fpcu']:g}, {p['epsU']:g}, {p['lambda']:g}, "
            f"{p['ft']:g}, {p['Ets']:g})"
        )
    raise ValueError(f"Unsupported material type: {material.material_type}")


def section_to_openseespy(
    section: SectionData,
    materials: dict[int, MaterialData] | None = None,
) -> list[str]:
    p = (
        section.resolved_elastic_parameters(materials)
        if section.section_type == "Elastic"
        else section.parameters
    )
    if section.section_type == "Elastic":
        return [
            "ops.section('Elastic', "
            f"{section.tag}, {p['E']:g}, {p['A']:g}, "
            f"{p['Iz']:g}, {p['Iy']:g}, {p['G']:g}, {p['J']:g})"
        ]

    if section.section_type == "Fiber":
        lines = [
            f"ops.section('Fiber', {section.tag}, '-GJ', {p['GJ']:g})"
        ]
        for fiber in section.fibers:
            lines.append(
                "ops.fiber("
                f"{fiber.y:g}, {fiber.z:g}, {fiber.area:g}, "
                f"{fiber.material_tag})"
            )
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
    directions = sorted(connection.materials_by_dof)
    materials = [connection.materials_by_dof[dof] for dof in directions]

    mat_text = ", ".join(str(tag) for tag in materials)
    dir_text = ", ".join(str(dof) for dof in directions)
    ox = ", ".join(f"{value:g}" for value in connection.orient_x)
    oy = ", ".join(f"{value:g}" for value in connection.orient_y)

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


def nodal_load_to_openseespy(load: NodalLoadData) -> str:
    values = ", ".join(f"{value:g}" for value in load.values)
    return f"ops.load({load.node_tag}, {values})"


def transformation_to_openseespy(
    transformation: TransformationData,
) -> str:
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
) -> str:
    lines: list[str] = [
        "import openseespy.opensees as ops",
        "",
        "ops.wipe()",
        f"ops.model('basic', '-ndm', {model.ndm}, '-ndf', {model.ndf})",
        "",
        "# Nodes",
    ]

    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        x, y, z = node.xyz
        lines.append(f"ops.node({tag}, {x:g}, {y:g}, {z:g})")

    mass_nodes = [
        tag for tag, node in model.nodes.items()
        if any(abs(value) > 0.0 for value in node.mass)
    ]
    if mass_nodes:
        lines.extend(["", "# Nodal masses"])
        for tag in sorted(mass_nodes):
            mass = ", ".join(f"{value:g}" for value in model.nodes[tag].mass)
            lines.append(f"ops.mass({tag}, {mass})")

    lines.extend(["", "# Boundary conditions"])
    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        if any(node.fixity):
            fix = ", ".join(str(v) for v in node.fixity)
            lines.append(f"ops.fix({tag}, {fix})")

    if constraints:
        lines.extend(["", "# Multi-point constraints"])
        for tag in sorted(constraints):
            lines.extend(constraint_to_openseespy(constraints[tag]))

    if materials:
        lines.extend(["", "# Materials"])
        for tag in sorted(materials):
            lines.append(material_to_openseespy(materials[tag]))

    if sections:
        lines.extend(["", "# Sections"])
        for tag in sorted(sections):
            lines.extend(
                section_to_openseespy(sections[tag], materials)
            )

    default_transf_tag = 1
    if transformations:
        default_transf_tag = min(transformations)
        lines.extend(["", "# Geometric transformations"])
        for tag in sorted(transformations):
            lines.append(
                transformation_to_openseespy(transformations[tag])
            )

    lines.extend([
        "",
        "# Placeholder elastic properties for MVP visualization",
        "A = 0.02",
        "E = 2.0e11",
        "G = 7.6923e10",
        "J = 8.0e-5",
        "Iy = 8.0e-5",
        "Iz = 8.0e-5",
    ])
    if not transformations:
        lines.append("ops.geomTransf('Linear', 1, 0, 1, 0)")

    lines.extend([
        "",
        "# Elements",
    ])
    for tag in sorted(model.elements):
        e = model.elements[tag]
        transf_tag = e.transf_tag or default_transf_tag

        assigned_section = (
            sections.get(e.section_tag)
            if sections is not None and e.section_tag is not None
            else None
        )

        if (
            e.element_type == "elasticBeamColumn"
            and assigned_section is not None
            and assigned_section.section_type == "Elastic"
        ):
            p = assigned_section.resolved_elastic_parameters(materials)
            lines.append(
                "ops.element('elasticBeamColumn', "
                f"{tag}, {e.i}, {e.j}, {p['A']:g}, {p['E']:g}, "
                f"{p['G']:g}, {p['J']:g}, {p['Iy']:g}, {p['Iz']:g}, "
                f"{transf_tag})"
            )
            continue

        if assigned_section is not None and assigned_section.section_type != "Elastic":
            lines.append(
                f"# WARNING: Element {tag} ({e.element_type}) is assigned "
                f"section {assigned_section.tag} ({assigned_section.section_type}); "
                "full nonlinear element generation is not implemented yet."
            )

        lines.append(
            "ops.element('elasticBeamColumn', "
            f"{tag}, {e.i}, {e.j}, A, E, G, J, Iy, Iz, {transf_tag})"
        )

    if connections:
        lines.extend(["", "# Connections / springs / links"])
        for tag in sorted(connections):
            lines.append(connection_to_openseespy(connections[tag]))

    if time_series:
        lines.extend(["", "# Time series"])
        for tag in sorted(time_series):
            lines.append(time_series_to_openseespy(time_series[tag]))

    if load_patterns:
        lines.extend(["", "# Load patterns"])
        loads_by_pattern: dict[int, list[NodalLoadData]] = {}
        for load in (nodal_loads or {}).values():
            loads_by_pattern.setdefault(load.pattern_tag, []).append(load)

        for tag in sorted(load_patterns):
            pattern = load_patterns[tag]
            lines.append(load_pattern_to_openseespy(pattern))
            if pattern.pattern_type == "Plain":
                for load in sorted(
                    loads_by_pattern.get(tag, []),
                    key=lambda item: item.tag,
                ):
                    lines.append(
                        f"# Nodal load {load.tag}: {load.name}"
                    )
                    lines.append(nodal_load_to_openseespy(load))

    lines.extend(["", "print('Model generated by OpenSeesPy Studio MVP')"])
    return "\n".join(lines) + "\n"
