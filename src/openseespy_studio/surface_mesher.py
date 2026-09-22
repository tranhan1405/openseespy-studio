from __future__ import annotations

from dataclasses import dataclass, field
import math

from .project import ProjectDatabase, SurfaceGeometryData
from .shell_mesh import ShellMeshBuildResult, ShellMeshSpec, build_shell_mesh


@dataclass(slots=True)
class SurfaceMeshResult:
    surface_tag: int
    corner_node_tags: list[int] = field(default_factory=list)
    created_corner_node_tags: list[int] = field(default_factory=list)
    created_node_tags: list[int] = field(default_factory=list)
    reused_node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    divisions_u: int = 0
    divisions_v: int = 0
    conformed_u: bool = False
    conformed_v: bool = False


def rectangle_surface_points(
    origin: tuple[float, float, float],
    width: float,
    height: float,
    *,
    plane: str = "XY",
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    """Return four ordered rectangle corners on an XY/XZ/YZ working plane."""
    x, y, z = (float(value) for value in origin)
    width = float(width)
    height = float(height)
    if not math.isfinite(width) or width <= 0.0:
        raise ValueError("Rectangle width must be finite and positive.")
    if not math.isfinite(height) or height <= 0.0:
        raise ValueError("Rectangle height must be finite and positive.")

    plane = str(plane).upper()
    if plane == "XY":
        return (
            (x, y, z),
            (x + width, y, z),
            (x + width, y + height, z),
            (x, y + height, z),
        )
    if plane == "XZ":
        return (
            (x, y, z),
            (x + width, y, z),
            (x + width, y, z + height),
            (x, y, z + height),
        )
    if plane == "YZ":
        return (
            (x, y, z),
            (x, y + width, z),
            (x, y + width, z + height),
            (x, y, z + height),
        )
    raise ValueError("Rectangle plane must be XY, XZ, or YZ.")


def _surface_corner_node_tags(
    project: ProjectDatabase,
    surface: SurfaceGeometryData,
    *,
    tolerance: float | None = None,
) -> tuple[list[int], list[int]]:
    points = surface.points
    if tolerance is None:
        if project.model.nodes:
            xs = [float(node.xyz[0]) for node in project.model.nodes.values()]
            ys = [float(node.xyz[1]) for node in project.model.nodes.values()]
            zs = [float(node.xyz[2]) for node in project.model.nodes.values()]
            span = max(
                max(xs) - min(xs),
                max(ys) - min(ys),
                max(zs) - min(zs),
                1.0,
            )
        else:
            flat = [coordinate for point in points for coordinate in point]
            span = max(max(flat) - min(flat), 1.0)
        tolerance = 1.0e-9 * span
    tolerance = float(tolerance)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError(
            "Surface corner merge tolerance must be finite and positive."
        )

    tolerance2 = tolerance * tolerance
    corner_tags: list[int] = []
    created_tags: list[int] = []
    next_tag = project.model.next_node_tag()

    for point in points:
        best: tuple[float, int] | None = None
        for tag, node in project.model.nodes.items():
            distance2 = sum(
                (float(node.xyz[index]) - float(point[index])) ** 2
                for index in range(3)
            )
            if distance2 <= tolerance2 and (
                best is None or distance2 < best[0]
            ):
                best = (distance2, int(tag))

        if best is not None:
            corner_tags.append(best[1])
            continue

        while next_tag in project.model.nodes:
            next_tag += 1
        project.model.add_node(next_tag, *point)
        corner_tags.append(next_tag)
        created_tags.append(next_tag)
        next_tag += 1

    if len(set(corner_tags)) != 4:
        raise ValueError(
            "Surface geometry corners collapse onto fewer than four model nodes."
        )
    return corner_tags, created_tags


def mesh_surface_geometry(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceMeshResult:
    """Create a mapped quadrilateral shell mesh from an independent surface."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")
    if surface.section_tag is None:
        raise ValueError(
            f"Surface geometry {tag} requires a Shell Section before meshing."
        )
    existing_elements = [
        element_tag
        for element_tag in surface.generated_element_tags
        if element_tag in project.model.elements
    ]
    if existing_elements:
        raise ValueError(
            f"Surface geometry {tag} is already meshed. "
            "Delete/remesh its generated mesh before meshing again."
        )

    before = project.to_dict()
    try:
        corner_tags, created_corners = _surface_corner_node_tags(
            project,
            surface,
        )
        spec = ShellMeshSpec(
            corner_nodes=tuple(corner_tags),
            divisions_u=surface.divisions_u,
            divisions_v=surface.divisions_v,
            target_size=(
                surface.target_size
                if surface.mesh_mode == "target_size"
                else None
            ),
            formulation=surface.formulation,
            section_tag=surface.section_tag,
            reuse_existing_nodes=surface.reuse_existing_nodes,
            conform_existing_edges=surface.conform_existing_edges,
            group=f"surface:{surface.tag}",
        )
        mesh_result: ShellMeshBuildResult = build_shell_mesh(
            project,
            spec,
        )
        generated_nodes = sorted(set(
            created_corners + list(mesh_result.node_tags)
        ))
        surface.generated_node_tags = generated_nodes
        surface.generated_element_tags = list(mesh_result.element_tags)
        surface.divisions_u = mesh_result.divisions_u
        surface.divisions_v = mesh_result.divisions_v
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise

    return SurfaceMeshResult(
        surface_tag=surface.tag,
        corner_node_tags=list(corner_tags),
        created_corner_node_tags=list(created_corners),
        created_node_tags=list(generated_nodes),
        reused_node_tags=sorted(set(mesh_result.reused_node_tags)),
        element_tags=list(mesh_result.element_tags),
        divisions_u=mesh_result.divisions_u,
        divisions_v=mesh_result.divisions_v,
        conformed_u=mesh_result.conformed_u,
        conformed_v=mesh_result.conformed_v,
    )
