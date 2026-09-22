from __future__ import annotations

from dataclasses import dataclass, field
import math

from .project import ProjectDatabase, SurfaceGeometryData
from .shell_mesh import ShellMeshBuildResult, ShellMeshSpec, build_shell_mesh


@dataclass(slots=True)
class SurfaceMeshDeleteResult:
    surface_tag: int
    removed_element_tags: list[int] = field(default_factory=list)
    removed_node_tags: list[int] = field(default_factory=list)
    kept_node_tags: list[int] = field(default_factory=list)


@dataclass(slots=True)
class SurfaceRemeshResult:
    deleted: SurfaceMeshDeleteResult
    mesh: "SurfaceMeshResult"


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
            corotational=surface.corotational,
            local_x=surface.local_x,
            no_eas=surface.no_eas,
            drilling_stab=surface.drilling_stab,
            drilling_nl=surface.drilling_nl,
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



def _surface_element_dependency_blockers(
    project: ProjectDatabase,
    element_tags: set[int],
) -> list[str]:
    blockers: list[str] = []
    if not element_tags:
        return blockers

    load_tags = sorted(
        load.tag
        for load in project.element_loads.values()
        if int(load.element_tag) in element_tags
    )
    if load_tags:
        blockers.append(
            "element load(s) " + ", ".join(map(str, load_tags))
        )

    recorder_tags = sorted(
        recorder.tag
        for recorder in project.recorders.values()
        if (
            recorder.recorder_type != "Node"
            and any(
                int(tag) in element_tags
                for tag in recorder.target_tags
            )
        )
    )
    if recorder_tags:
        blockers.append(
            "recorder(s) " + ", ".join(map(str, recorder_tags))
        )

    result_tags = sorted(
        result.tag
        for result in project.solution_results.values()
        if any(
            int(tag) in element_tags
            for tag in result.element_scope
        )
    )
    if result_tags:
        blockers.append(
            "result request(s) " + ", ".join(map(str, result_tags))
        )

    set_names = sorted(
        selection.name
        for selection in project.selection_sets.values()
        if any(
            int(tag) in element_tags
            for tag in selection.element_tags
        )
    )
    if set_names:
        blockers.append(
            "named selection(s) " + ", ".join(set_names)
        )
    return blockers


def _surface_node_is_externally_used(
    project: ProjectDatabase,
    node_tag: int,
) -> bool:
    tag = int(node_tag)
    node = project.model.nodes.get(tag)
    if node is None:
        return False

    if any(node.fixity) or any(abs(float(v)) > 0.0 for v in node.mass):
        return True
    if any(
        tag in element.node_tags()
        for element in project.model.elements.values()
    ):
        return True
    if any(
        tag in {connection.node_i, connection.node_j}
        for connection in project.connections.values()
    ):
        return True
    if any(
        (
            constraint.retained_node == tag
            or tag in constraint.constrained_nodes
        )
        for constraint in project.constraints.values()
    ):
        return True
    if any(
        load.node_tag == tag
        for load in project.nodal_loads.values()
    ):
        return True
    if any(
        displacement.node_tag == tag
        for displacement in project.prescribed_displacements.values()
    ):
        return True
    if any(
        recorder.recorder_type == "Node"
        and tag in recorder.target_tags
        for recorder in project.recorders.values()
    ):
        return True
    if any(
        tag in result.node_scope
        for result in project.solution_results.values()
    ):
        return True
    if any(
        tag in selection.node_tags
        for selection in project.selection_sets.values()
    ):
        return True
    return False


def delete_surface_mesh(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceMeshDeleteResult:
    """Delete only FE entities generated by one Surface geometry object."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")

    live_elements = {
        int(element_tag)
        for element_tag in surface.generated_element_tags
        if int(element_tag) in project.model.elements
    }
    blockers = _surface_element_dependency_blockers(
        project,
        live_elements,
    )
    if blockers:
        raise ValueError(
            "Cannot delete/remesh Surface generated FE mesh because it is "
            "referenced by " + "; ".join(blockers) + "."
        )

    before = project.to_dict()
    try:
        for element_tag in sorted(live_elements):
            project.model.elements.pop(element_tag, None)

        removed_nodes: list[int] = []
        kept_nodes: list[int] = []
        for node_tag in sorted(set(surface.generated_node_tags)):
            if node_tag not in project.model.nodes:
                continue
            if _surface_node_is_externally_used(project, node_tag):
                kept_nodes.append(int(node_tag))
                continue
            project.model.nodes.pop(int(node_tag), None)
            removed_nodes.append(int(node_tag))

        surface.generated_node_tags = []
        surface.generated_element_tags = []
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise

    return SurfaceMeshDeleteResult(
        surface_tag=surface.tag,
        removed_element_tags=sorted(live_elements),
        removed_node_tags=removed_nodes,
        kept_node_tags=kept_nodes,
    )


def remesh_surface_geometry(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceRemeshResult:
    """Atomically replace one Surface's generated FE mesh."""
    before = project.to_dict()
    try:
        deleted = delete_surface_mesh(project, surface_tag)
        mesh = mesh_surface_geometry(project, surface_tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return SurfaceRemeshResult(deleted=deleted, mesh=mesh)


def surface_unit_normal(
    surface: SurfaceGeometryData,
) -> tuple[float, float, float]:
    """Return the normalized Newell normal for the ordered Surface corners."""
    normal = [0.0, 0.0, 0.0]
    for index, current in enumerate(surface.points):
        following = surface.points[(index + 1) % 4]
        normal[0] += (
            (current[1] - following[1])
            * (current[2] + following[2])
        )
        normal[1] += (
            (current[2] - following[2])
            * (current[0] + following[0])
        )
        normal[2] += (
            (current[0] - following[0])
            * (current[1] + following[1])
        )
    magnitude = math.sqrt(sum(value * value for value in normal))
    if magnitude <= 1.0e-12:
        raise ValueError("Surface geometry has no stable normal.")
    return tuple(value / magnitude for value in normal)


def flip_surface_orientation(
    project: ProjectDatabase,
    surface_tag: int,
    *,
    remesh_if_meshed: bool = True,
) -> SurfaceMeshResult | None:
    """Reverse Surface winding and optionally rebuild its generated Shell mesh."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")

    before = project.to_dict()
    try:
        had_mesh = any(
            element_tag in project.model.elements
            for element_tag in surface.generated_element_tags
        )
        if had_mesh:
            if not remesh_if_meshed:
                raise ValueError(
                    "Surface has a generated FE mesh; remesh is required "
                    "to flip its orientation safely."
                )
            delete_surface_mesh(project, tag)

        p1, p2, p3, p4 = surface.points
        surface.points = (p1, p4, p3, p2)
        if surface.corner_point_tags is not None:
            q1, q2, q3, q4 = surface.corner_point_tags
            surface.corner_point_tags = (q1, q4, q3, q2)

        if had_mesh:
            return mesh_surface_geometry(project, tag)
        return None
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
