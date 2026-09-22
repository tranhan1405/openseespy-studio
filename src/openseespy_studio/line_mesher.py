from __future__ import annotations

from dataclasses import dataclass, field
import math

from .model import FRAME_ELEMENT_TYPES
from .project import LineGeometryData, ProjectDatabase


@dataclass(slots=True)
class LineMeshResult:
    line_tag: int
    node_tags: list[int] = field(default_factory=list)
    created_node_tags: list[int] = field(default_factory=list)
    reused_node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    divisions: int = 0


def _merge_tolerance(project: ProjectDatabase, points) -> float:
    if project.model.nodes:
        coords = [node.xyz for node in project.model.nodes.values()]
        xs = [float(p[0]) for p in coords]
        ys = [float(p[1]) for p in coords]
        zs = [float(p[2]) for p in coords]
        span = max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs),
            1.0,
        )
    else:
        flat = [float(value) for point in points for value in point]
        span = max(max(flat) - min(flat), 1.0)
    return 1.0e-9 * span


def _find_existing_node(
    project: ProjectDatabase,
    xyz: tuple[float, float, float],
    tolerance: float,
) -> int | None:
    tol2 = tolerance * tolerance
    best: tuple[float, int] | None = None
    for tag, node in project.model.nodes.items():
        d2 = sum(
            (float(node.xyz[index]) - float(xyz[index])) ** 2
            for index in range(3)
        )
        if d2 <= tol2 and (best is None or d2 < best[0]):
            best = (d2, int(tag))
    return None if best is None else best[1]


def _line_points(project: ProjectDatabase, line: LineGeometryData):
    point_i = project.points.get(line.point_i)
    point_j = project.points.get(line.point_j)
    if point_i is None or point_j is None:
        raise ValueError(
            f"Line geometry {line.tag} references missing Point geometry."
        )
    a = tuple(float(v) for v in point_i.xyz)
    b = tuple(float(v) for v in point_j.xyz)
    length = math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))
    if length <= 1.0e-12:
        raise ValueError(f"Line geometry {line.tag} has zero length.")
    return a, b, length


def mesh_line_geometry(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshResult:
    """Discretize one geometry Line into OpenSees Frame or Truss elements."""
    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")

    live = [
        element_tag
        for element_tag in line.generated_element_tags
        if element_tag in project.model.elements
    ]
    if live:
        raise ValueError(
            f"Line geometry {tag} is already meshed. "
            "Delete its generated FE elements before meshing again."
        )

    a, b, length = _line_points(project, line)
    divisions = int(line.divisions)
    if line.mesh_mode == "target_size":
        if line.target_size is None:
            raise ValueError("Target element size is required.")
        divisions = max(1, int(math.ceil(length / float(line.target_size))))

    if line.element_family == "Frame":
        if line.element_type not in FRAME_ELEMENT_TYPES:
            raise ValueError(
                f"Unsupported Frame formulation: {line.element_type}"
            )
        if line.section_tag is None or line.section_tag not in project.sections:
            raise ValueError("Frame line requires a valid Section.")
        if (
            line.transformation_tag is None
            or line.transformation_tag not in project.transformations
        ):
            raise ValueError(
                "Frame line requires a valid Geometric Transformation."
            )
    elif line.element_family == "Truss":
        if (
            line.material_tag is None
            or line.material_tag not in project.materials
        ):
            raise ValueError("Truss line requires a valid uniaxial Material.")
        if line.area <= 0.0:
            raise ValueError("Truss line area must be positive.")
    else:
        raise ValueError(
            f"Unsupported line FE family: {line.element_family}"
        )

    before = project.to_dict()
    try:
        tolerance = _merge_tolerance(project, (a, b))
        node_tags: list[int] = []
        created: list[int] = []
        reused: list[int] = []

        for index in range(divisions + 1):
            ratio = index / divisions
            xyz = tuple(
                a[axis] + ratio * (b[axis] - a[axis])
                for axis in range(3)
            )
            existing = (
                _find_existing_node(project, xyz, tolerance)
                if line.reuse_existing_nodes
                else None
            )
            if existing is not None:
                node_tags.append(existing)
                reused.append(existing)
                continue

            node_tag = project.model.next_node_tag()
            project.model.add_node(node_tag, *xyz)
            node_tags.append(node_tag)
            created.append(node_tag)

        element_tags: list[int] = []
        for node_i, node_j in zip(node_tags[:-1], node_tags[1:]):
            element_tag = project.next_element_tag()
            if line.element_family == "Frame":
                project.model.add_element(
                    element_tag,
                    node_i,
                    node_j,
                    element_type=line.element_type,
                    section_tag=line.section_tag,
                    transf_tag=line.transformation_tag,
                    group=f"line:{line.tag}",
                    integration_type=line.integration_type,
                    integration_points=line.integration_points,
                    mass_per_length=line.mass_per_length,
                    consistent_mass=line.consistent_mass,
                )
            else:
                project.model.add_element(
                    element_tag,
                    node_i,
                    node_j,
                    element_type="truss",
                    group=f"line:{line.tag}",
                    truss_area=line.area,
                    truss_material_tag=line.material_tag,
                    mass_per_length=line.mass_per_length,
                    consistent_mass=line.consistent_mass,
                    truss_do_rayleigh=line.do_rayleigh,
                )
            element_tags.append(element_tag)

        line.generated_node_tags = sorted(set(created))
        line.generated_element_tags = list(element_tags)
        line.divisions = divisions
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise

    return LineMeshResult(
        line_tag=line.tag,
        node_tags=list(node_tags),
        created_node_tags=sorted(set(created)),
        reused_node_tags=sorted(set(reused)),
        element_tags=list(element_tags),
        divisions=divisions,
    )
