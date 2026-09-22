from __future__ import annotations

from dataclasses import dataclass, field
import math

from .project import ProjectDatabase, SurfaceGeometryData
from .shell_mesh import (
    ShellMeshBuildResult,
    ShellMeshSpec,
    build_shell_mesh,
    resolve_shell_mesh_parameters,
)


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
class SurfaceConformityIssue:
    surface_a: int
    surface_b: int
    edge_a: int
    edge_b: int
    divisions_a: int
    divisions_b: int
    issue_type: str
    message: str


@dataclass(slots=True)
class SurfaceConformityReport:
    surface_count: int
    shared_edge_count: int
    issues: list[SurfaceConformityIssue] = field(default_factory=list)

    @property
    def conforming(self) -> bool:
        return not self.issues


@dataclass(slots=True)
class SurfaceMeshState:
    surface_tag: int
    status: str
    tracked_element_tags: list[int] = field(default_factory=list)
    live_element_tags: list[int] = field(default_factory=list)
    missing_element_tags: list[int] = field(default_factory=list)
    foreign_element_tags: list[int] = field(default_factory=list)
    untracked_owned_element_tags: list[int] = field(default_factory=list)
    tracked_node_tags: list[int] = field(default_factory=list)
    missing_node_tags: list[int] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.status in {"unmeshed", "meshed"}

    @property
    def issue_count(self) -> int:
        return (
            len(self.missing_element_tags)
            + len(self.foreign_element_tags)
            + len(self.untracked_owned_element_tags)
            + len(self.missing_node_tags)
        )


@dataclass(slots=True)
class SurfaceMeshIntegrityReport:
    surface_count: int
    states: list[SurfaceMeshState] = field(default_factory=list)

    @property
    def stale_states(self) -> list[SurfaceMeshState]:
        return [state for state in self.states if not state.healthy]

    @property
    def healthy(self) -> bool:
        return not self.stale_states


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
    grid: list[list[int]] = field(default_factory=list)
    u_coordinates: list[float] = field(default_factory=list)
    v_coordinates: list[float] = field(default_factory=list)


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
            bias_u=surface.bias_u,
            bias_v=surface.bias_v,
            edge_divisions=surface.edge_divisions,
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
        grid=[list(row) for row in mesh_result.grid],
        u_coordinates=list(mesh_result.u_coordinates),
        v_coordinates=list(mesh_result.v_coordinates),
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


def inspect_surface_mesh_state(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceMeshState:
    """Describe whether a Surface still owns a complete generated FE mesh."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")

    expected_group = f"surface:{tag}"
    tracked_elements = sorted({
        int(element_tag)
        for element_tag in surface.generated_element_tags
    })
    live_elements = [
        element_tag
        for element_tag in tracked_elements
        if element_tag in project.model.elements
    ]
    missing_elements = [
        element_tag
        for element_tag in tracked_elements
        if element_tag not in project.model.elements
    ]
    foreign_elements = [
        element_tag
        for element_tag in live_elements
        if project.model.elements[element_tag].group != expected_group
    ]
    owned_elements = sorted(
        int(element_tag)
        for element_tag, element in project.model.elements.items()
        if element.group == expected_group
    )
    untracked_owned = [
        element_tag
        for element_tag in owned_elements
        if element_tag not in tracked_elements
    ]

    tracked_nodes = sorted({
        int(node_tag)
        for node_tag in surface.generated_node_tags
    })
    missing_nodes = [
        node_tag
        for node_tag in tracked_nodes
        if node_tag not in project.model.nodes
    ]

    has_tracking = bool(
        tracked_elements
        or tracked_nodes
        or owned_elements
    )
    stale = bool(
        missing_elements
        or foreign_elements
        or untracked_owned
        or missing_nodes
        or (has_tracking and not live_elements and not owned_elements)
    )
    if not has_tracking:
        status = "unmeshed"
    elif stale:
        status = "stale"
    else:
        status = "meshed"

    return SurfaceMeshState(
        surface_tag=tag,
        status=status,
        tracked_element_tags=tracked_elements,
        live_element_tags=live_elements,
        missing_element_tags=missing_elements,
        foreign_element_tags=foreign_elements,
        untracked_owned_element_tags=untracked_owned,
        tracked_node_tags=tracked_nodes,
        missing_node_tags=missing_nodes,
    )


def audit_surface_mesh_integrity(
    project: ProjectDatabase,
    surface_tags=None,
) -> SurfaceMeshIntegrityReport:
    """Audit generated FE ownership/tracking for one or more Surfaces."""
    tags = sorted(
        int(tag)
        for tag in (
            project.surfaces
            if surface_tags is None
            else surface_tags
        )
        if int(tag) in project.surfaces
    )
    return SurfaceMeshIntegrityReport(
        surface_count=len(tags),
        states=[
            inspect_surface_mesh_state(project, tag)
            for tag in tags
        ],
    )


def delete_surface_mesh(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceMeshDeleteResult:
    """Delete only FE entities generated by one Surface geometry object."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")

    state = inspect_surface_mesh_state(project, tag)
    if state.foreign_element_tags or state.untracked_owned_element_tags:
        details: list[str] = []
        if state.foreign_element_tags:
            details.append(
                "tracked element(s) owned elsewhere: "
                + ", ".join(map(str, state.foreign_element_tags))
            )
        if state.untracked_owned_element_tags:
            details.append(
                "owned but untracked element(s): "
                + ", ".join(map(str, state.untracked_owned_element_tags))
            )
        raise ValueError(
            "Cannot delete/remesh Surface generated FE mesh because its "
            "tracked FE ownership is inconsistent ("
            + "; ".join(details)
            + "). Run Audit Mesh Integrity before changing the Surface."
        )

    live_elements = set(state.live_element_tags)
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


def delete_surface_geometry(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceMeshDeleteResult:
    """Atomically delete a Surface together with the FE mesh it owns."""
    tag = int(surface_tag)
    if tag not in project.surfaces:
        raise ValueError(f"Surface geometry {tag} does not exist.")

    before = project.to_dict()
    try:
        deleted = delete_surface_mesh(project, tag)
        project.remove_surface(tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return deleted


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


def _surface_bilinear_point(
    surface: SurfaceGeometryData,
    u: float,
    v: float,
) -> tuple[float, float, float]:
    p1, p2, p3, p4 = surface.points
    return tuple(
        (1.0 - u) * (1.0 - v) * p1[index]
        + u * (1.0 - v) * p2[index]
        + u * v * p3[index]
        + (1.0 - u) * v * p4[index]
        for index in range(3)
    )


def surface_preview_parameters(
    surface: SurfaceGeometryData,
) -> tuple[list[float], list[float]]:
    """Resolve requested Surface grid coordinates without mutating FE state."""
    return resolve_shell_mesh_parameters(
        *surface.points,
        divisions_u=surface.divisions_u,
        divisions_v=surface.divisions_v,
        target_size=(
            surface.target_size
            if surface.mesh_mode == "target_size"
            else None
        ),
        bias_u=surface.bias_u,
        bias_v=surface.bias_v,
        edge_divisions=surface.edge_divisions,
    )


def surface_preview_divisions(
    surface: SurfaceGeometryData,
) -> tuple[int, int]:
    """Resolve the Surface's requested mesh sizing without mutating FE state."""
    u_coordinates, v_coordinates = surface_preview_parameters(surface)
    return len(u_coordinates) - 1, len(v_coordinates) - 1


def surface_mesh_preview_segments(
    surface: SurfaceGeometryData,
) -> tuple[int, int, list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]]:
    """Return structured U/V grid segments without creating Nodes/Elements."""
    u_coordinates, v_coordinates = surface_preview_parameters(surface)
    nu = len(u_coordinates) - 1
    nv = len(v_coordinates) - 1
    segments: list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ] = []

    for u in u_coordinates:
        for j in range(nv):
            v0 = v_coordinates[j]
            v1 = v_coordinates[j + 1]
            segments.append((
                _surface_bilinear_point(surface, u, v0),
                _surface_bilinear_point(surface, u, v1),
            ))

    for v in v_coordinates:
        for i in range(nu):
            u0 = u_coordinates[i]
            u1 = u_coordinates[i + 1]
            segments.append((
                _surface_bilinear_point(surface, u0, v),
                _surface_bilinear_point(surface, u1, v),
            ))
    return nu, nv, segments


def _distance3(a, b) -> float:
    return math.sqrt(sum(
        (float(a[index]) - float(b[index])) ** 2
        for index in range(3)
    ))


def _surface_span(project: ProjectDatabase, surfaces) -> float:
    coords = [
        value
        for surface in surfaces
        for point in surface.points
        for value in point
    ]
    if not coords:
        return 1.0
    points = [point for surface in surfaces for point in surface.points]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    return max(
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
        1.0,
    )


def _surface_edges(surface: SurfaceGeometryData):
    p = surface.points
    nu, nv = surface_preview_divisions(surface)
    return (
        (p[0], p[1], nu, 1),
        (p[1], p[2], nv, 2),
        (p[2], p[3], nu, 3),
        (p[3], p[0], nv, 4),
    )


def _same_edge(a0, a1, b0, b1, tolerance: float) -> bool:
    direct = (
        _distance3(a0, b0) <= tolerance
        and _distance3(a1, b1) <= tolerance
    )
    reverse = (
        _distance3(a0, b1) <= tolerance
        and _distance3(a1, b0) <= tolerance
    )
    return direct or reverse


def _live_surface_edge_nodes(
    project: ProjectDatabase,
    surface: SurfaceGeometryData,
    start,
    end,
    *,
    tolerance: float,
) -> list[int] | None:
    live_elements = [
        project.model.elements[int(tag)]
        for tag in surface.generated_element_tags
        if int(tag) in project.model.elements
    ]
    if not live_elements:
        return None

    a = tuple(float(value) for value in start)
    b = tuple(float(value) for value in end)
    ab = tuple(b[i] - a[i] for i in range(3))
    length2 = sum(value * value for value in ab)
    if length2 <= tolerance * tolerance:
        return []

    candidates: list[tuple[float, int]] = []
    node_tags = {
        int(node_tag)
        for element in live_elements
        for node_tag in element.node_tags()
    }
    for node_tag in node_tags:
        node = project.model.nodes.get(node_tag)
        if node is None:
            continue
        point = tuple(float(value) for value in node.xyz)
        ap = tuple(point[i] - a[i] for i in range(3))
        t = sum(ap[i] * ab[i] for i in range(3)) / length2
        if t < -1.0e-9 or t > 1.0 + 1.0e-9:
            continue
        closest = tuple(a[i] + t * ab[i] for i in range(3))
        if _distance3(point, closest) <= tolerance:
            candidates.append((max(0.0, min(1.0, t)), node_tag))

    candidates.sort(key=lambda item: (item[0], item[1]))
    unique: list[tuple[float, int]] = []
    for t, node_tag in candidates:
        if unique and abs(t - unique[-1][0]) <= 1.0e-9:
            continue
        unique.append((t, node_tag))
    return [node_tag for _t, node_tag in unique]


def audit_surface_conformity(
    project: ProjectDatabase,
    surface_tags=None,
    *,
    tolerance: float | None = None,
) -> SurfaceConformityReport:
    """Audit shared Surface edges for subdivision and FE connectivity mismatch."""
    tags = sorted(
        int(tag)
        for tag in (
            project.surfaces
            if surface_tags is None
            else surface_tags
        )
        if int(tag) in project.surfaces
    )
    surfaces = [project.surfaces[tag] for tag in tags]
    tol = (
        float(tolerance)
        if tolerance is not None
        else 1.0e-8 * _surface_span(project, surfaces)
    )
    if not math.isfinite(tol) or tol <= 0.0:
        raise ValueError(
            "Surface conformity tolerance must be finite and positive."
        )

    shared_edge_count = 0
    issues: list[SurfaceConformityIssue] = []
    for index, surface_a in enumerate(surfaces):
        for surface_b in surfaces[index + 1:]:
            for a0, a1, divisions_a, edge_a in _surface_edges(surface_a):
                for b0, b1, divisions_b, edge_b in _surface_edges(surface_b):
                    if not _same_edge(a0, a1, b0, b1, tol):
                        continue
                    shared_edge_count += 1

                    nodes_a = _live_surface_edge_nodes(
                        project,
                        surface_a,
                        a0,
                        a1,
                        tolerance=tol,
                    )
                    nodes_b = _live_surface_edge_nodes(
                        project,
                        surface_b,
                        b0,
                        b1,
                        tolerance=tol,
                    )
                    actual_a = (
                        len(nodes_a) - 1
                        if nodes_a is not None and len(nodes_a) >= 2
                        else divisions_a
                    )
                    actual_b = (
                        len(nodes_b) - 1
                        if nodes_b is not None and len(nodes_b) >= 2
                        else divisions_b
                    )

                    if actual_a != actual_b:
                        issues.append(SurfaceConformityIssue(
                            surface_a=surface_a.tag,
                            surface_b=surface_b.tag,
                            edge_a=edge_a,
                            edge_b=edge_b,
                            divisions_a=actual_a,
                            divisions_b=actual_b,
                            issue_type="division_mismatch",
                            message=(
                                f"Surface {surface_a.tag} edge {edge_a} has "
                                f"{actual_a} division(s), Surface "
                                f"{surface_b.tag} edge {edge_b} has "
                                f"{actual_b}."
                            ),
                        ))
                        continue

                    if nodes_a is not None and nodes_b is not None:
                        same_connectivity = (
                            nodes_a == nodes_b
                            or nodes_a == list(reversed(nodes_b))
                        )
                        if not same_connectivity:
                            issues.append(SurfaceConformityIssue(
                                surface_a=surface_a.tag,
                                surface_b=surface_b.tag,
                                edge_a=edge_a,
                                edge_b=edge_b,
                                divisions_a=actual_a,
                                divisions_b=actual_b,
                                issue_type="disconnected_nodes",
                                message=(
                                    f"Surface {surface_a.tag} and Surface "
                                    f"{surface_b.tag} have coincident edge "
                                    "subdivisions but do not share the same "
                                    "FE node tags."
                                ),
                            ))

    return SurfaceConformityReport(
        surface_count=len(surfaces),
        shared_edge_count=shared_edge_count,
        issues=issues,
    )
