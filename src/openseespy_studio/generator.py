from __future__ import annotations

from dataclasses import dataclass

from .model import StructuralModel
from .project import MaterialData, SectionData, TransformationData


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


def section_to_openseespy(section: SectionData) -> list[str]:
    p = section.parameters
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

    lines.extend(["", "# Boundary conditions"])
    for tag in sorted(model.nodes):
        node = model.nodes[tag]
        if any(node.fixity):
            fix = ", ".join(str(v) for v in node.fixity)
            lines.append(f"ops.fix({tag}, {fix})")

    if materials:
        lines.extend(["", "# Materials"])
        for tag in sorted(materials):
            lines.append(material_to_openseespy(materials[tag]))

    if sections:
        lines.extend(["", "# Sections"])
        for tag in sorted(sections):
            lines.extend(section_to_openseespy(sections[tag]))

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
        lines.append(
            "ops.element('elasticBeamColumn', "
            f"{tag}, {e.i}, {e.j}, A, E, G, J, Iy, Iz, {transf_tag})"
        )

    lines.extend(["", "print('Model generated by OpenSeesPy Studio MVP')"])
    return "\n".join(lines) + "\n"
