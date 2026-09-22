from __future__ import annotations

from dataclasses import dataclass, field
import math

from .model import SHELL_ELEMENT_TYPES
from .project import (
    ElementLoadData,
    NodalLoadData,
    ProjectDatabase,
    RecorderData,
    SurfaceEdgeLoadData,
    SurfaceEdgeSupportData,
    SurfaceGeometryData,
    SurfacePressureData,
    SurfaceRecorderData,
)
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
class SurfaceEdgeInfo:
    surface_tag: int
    edge_index: int
    start_point: tuple[float, float, float]
    end_point: tuple[float, float, float]
    length: float
    requested_divisions: int
    live_node_tags: list[int] = field(default_factory=list)
    actual_divisions: int = 0
    neighbor_edges: list[tuple[int, int]] = field(default_factory=list)
    connected_neighbor_edges: list[tuple[int, int]] = field(default_factory=list)

    @property
    def is_boundary(self) -> bool:
        return not self.neighbor_edges

    @property
    def connectivity_status(self) -> str:
        if not self.live_node_tags:
            return "unmeshed"
        if not self.neighbor_edges:
            return "boundary"
        if set(self.connected_neighbor_edges) == set(self.neighbor_edges):
            return "shared"
        if self.connected_neighbor_edges:
            return "partially-shared"
        return "disconnected"


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


def managed_surface_support_node_tags(
    project: ProjectDatabase,
) -> set[int]:
    return {
        int(node_tag)
        for support in project.surface_edge_supports.values()
        for node_tag in support.generated_node_tags
        if int(node_tag) in project.model.nodes
    }


def _other_surface_support_fixity(
    project: ProjectDatabase,
    node_tag: int,
    *,
    exclude_support_tag: int,
) -> tuple[int, int, int, int, int, int]:
    values = [0, 0, 0, 0, 0, 0]
    target = int(node_tag)
    for support in project.surface_edge_supports.values():
        if support.tag == int(exclude_support_tag):
            continue
        if target not in support.generated_node_tags:
            continue
        for index, fixed in enumerate(support.fixity):
            if fixed:
                values[index] = 1
    return tuple(values)  # type: ignore[return-value]


def detach_surface_edge_support(
    project: ProjectDatabase,
    support_tag: int,
) -> list[int]:
    support = project.surface_edge_supports.get(int(support_tag))
    if support is None:
        raise ValueError(
            f"Surface edge support {int(support_tag)} does not exist."
        )
    changed: list[int] = []
    for node_tag in list(support.generated_node_tags):
        node = project.model.nodes.get(int(node_tag))
        if node is None:
            continue
        other = _other_surface_support_fixity(
            project,
            int(node_tag),
            exclude_support_tag=support.tag,
        )
        current = list(node.fixity)
        for index, owned in enumerate(support.fixity[:len(current)]):
            if owned and not other[index]:
                current[index] = 0
        project.model.set_fixity(int(node_tag), current)
        changed.append(int(node_tag))
    support.generated_node_tags = []
    return sorted(changed)


def sync_surface_edge_support(
    project: ProjectDatabase,
    support_tag: int,
) -> list[int]:
    tag = int(support_tag)
    support = project.surface_edge_supports.get(tag)
    if support is None:
        raise ValueError(f"Surface edge support {tag} does not exist.")
    if int(project.model.ndf) != 6:
        raise ValueError(
            "Managed Surface edge supports require a 3D shell model "
            "with ndf=6."
        )

    before = project.to_dict()
    try:
        detach_surface_edge_support(project, tag)
        node_tags = surface_edge_node_tags(
            project,
            support.surface_tag,
            support.edge_index,
        )
        requested = tuple(int(value) for value in support.fixity)
        conflicts: list[str] = []
        for node_tag in node_tags:
            node = project.model.nodes[int(node_tag)]
            other = _other_surface_support_fixity(
                project,
                int(node_tag),
                exclude_support_tag=tag,
            )
            for index, fixed in enumerate(requested):
                if not fixed:
                    continue
                dof = index + 1
                if any(
                    displacement.node_tag == int(node_tag)
                    and displacement.dof == dof
                    for displacement
                    in project.prescribed_displacements.values()
                ):
                    conflicts.append(
                        f"Node {node_tag} DOF {dof} has prescribed displacement"
                    )
                    continue
                if bool(node.fixity[index]) and not bool(other[index]):
                    conflicts.append(
                        f"Node {node_tag} DOF {dof} has manual restraint"
                    )
        if conflicts:
            raise ValueError(
                "Managed Surface edge support conflicts with existing "
                "node state: " + "; ".join(conflicts[:12])
            )

        for node_tag in node_tags:
            node = project.model.nodes[int(node_tag)]
            values = tuple(
                1 if bool(node.fixity[index]) or bool(requested[index]) else 0
                for index in range(6)
            )
            project.model.set_fixity(int(node_tag), values)
            project.validate_node_state(int(node_tag))
        support.generated_node_tags = list(node_tags)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return list(support.generated_node_tags)


def sync_surface_edge_supports_for_surface(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    support_tags = sorted(
        support.tag
        for support in project.surface_edge_supports.values()
        if support.surface_tag == int(surface_tag)
    )
    touched: set[int] = set()
    for support_tag in support_tags:
        touched.update(sync_surface_edge_support(project, support_tag))
    return sorted(touched)


def replace_surface_edge_support(
    project: ProjectDatabase,
    support: SurfaceEdgeSupportData,
) -> list[int]:
    """Atomically replace one managed support and rebind its FE ownership."""
    existing = project.surface_edge_supports.get(int(support.tag))
    if existing is None:
        raise ValueError(
            f"Surface edge support {int(support.tag)} does not exist."
        )
    before = project.to_dict()
    try:
        detach_surface_edge_support(project, existing.tag)
        support.generated_node_tags = []
        project.update_surface_edge_support(existing.tag, support)
        return sync_surface_edge_support(project, support.tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def remove_surface_edge_support(
    project: ProjectDatabase,
    support_tag: int,
) -> list[int]:
    tag = int(support_tag)
    if tag not in project.surface_edge_supports:
        raise ValueError(f"Surface edge support {tag} does not exist.")
    before = project.to_dict()
    try:
        changed = detach_surface_edge_support(project, tag)
        project.remove_surface_edge_support_definition(tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return changed


def managed_surface_edge_load_nodal_tags(
    project: ProjectDatabase,
) -> set[int]:
    return {
        int(load_tag)
        for edge_load in project.surface_edge_loads.values()
        for load_tag in edge_load.generated_nodal_load_tags
        if int(load_tag) in project.nodal_loads
    }


def detach_surface_edge_load(
    project: ProjectDatabase,
    edge_load_tag: int,
) -> list[int]:
    tag = int(edge_load_tag)
    edge_load = project.surface_edge_loads.get(tag)
    if edge_load is None:
        raise ValueError(f"Surface edge load {tag} does not exist.")
    removed: list[int] = []
    for load_tag in list(edge_load.generated_nodal_load_tags):
        normalized = int(load_tag)
        if normalized in project.nodal_loads:
            project.nodal_loads.pop(normalized)
            removed.append(normalized)
    edge_load.generated_nodal_load_tags = []
    return removed


def surface_edge_consistent_nodal_weights(
    project: ProjectDatabase,
    surface_tag: int,
    edge_index: int,
) -> tuple[list[int], list[float]]:
    """Return ordered nodes and exact weights for a uniform line resultant."""
    node_tags = surface_edge_node_tags(
        project,
        surface_tag,
        edge_index,
    )
    if len(node_tags) < 2:
        raise ValueError("Surface edge requires at least two FE nodes.")
    weights = [0.0 for _ in node_tags]
    for index in range(len(node_tags) - 1):
        node_i = project.model.nodes[node_tags[index]]
        node_j = project.model.nodes[node_tags[index + 1]]
        length = math.sqrt(sum(
            (
                float(node_j.xyz[axis])
                - float(node_i.xyz[axis])
            ) ** 2
            for axis in range(3)
        ))
        if not math.isfinite(length) or length <= 1.0e-12:
            raise ValueError(
                "Surface edge contains a zero-length FE segment."
            )
        contribution = 0.5 * length
        weights[index] += contribution
        weights[index + 1] += contribution
    return list(node_tags), weights


def sync_surface_edge_load(
    project: ProjectDatabase,
    edge_load_tag: int,
) -> list[int]:
    """Regenerate consistent equivalent nodal loads for one edge load."""
    tag = int(edge_load_tag)
    edge_load = project.surface_edge_loads.get(tag)
    if edge_load is None:
        raise ValueError(f"Surface edge load {tag} does not exist.")
    if int(project.model.ndf) != 6:
        raise ValueError(
            "Managed Surface edge line loads require a 3D shell model "
            "with ndf=6."
        )
    project._validate_surface_edge_load(edge_load)

    before = project.to_dict()
    try:
        detach_surface_edge_load(project, tag)
        node_tags, weights = surface_edge_consistent_nodal_weights(
            project,
            edge_load.surface_tag,
            edge_load.edge_index,
        )
        next_tag = project.next_nodal_load_tag()
        generated: list[int] = []
        for node_tag, weight in zip(node_tags, weights):
            while next_tag in project.nodal_loads:
                next_tag += 1
            values = tuple(
                float(value) * float(weight)
                for value in edge_load.values_per_length
            )
            load = NodalLoadData(
                tag=next_tag,
                name=(
                    f"{edge_load.name} [managed S{edge_load.surface_tag}:"
                    f"E{edge_load.edge_index}] Node {node_tag}"
                ),
                pattern_tag=edge_load.pattern_tag,
                node_tag=node_tag,
                values=values,
            )
            project.add_nodal_load(load)
            generated.append(next_tag)
            next_tag += 1
        edge_load.generated_nodal_load_tags = generated
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return list(edge_load.generated_nodal_load_tags)


def sync_surface_edge_loads_for_surface(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    load_tags = sorted(
        edge_load.tag
        for edge_load in project.surface_edge_loads.values()
        if edge_load.surface_tag == int(surface_tag)
    )
    generated: list[int] = []
    for load_tag in load_tags:
        generated.extend(sync_surface_edge_load(project, load_tag))
    return generated


def replace_surface_edge_load(
    project: ProjectDatabase,
    edge_load: SurfaceEdgeLoadData,
) -> list[int]:
    existing = project.surface_edge_loads.get(int(edge_load.tag))
    if existing is None:
        raise ValueError(
            f"Surface edge load {int(edge_load.tag)} does not exist."
        )
    before = project.to_dict()
    try:
        detach_surface_edge_load(project, existing.tag)
        edge_load.generated_nodal_load_tags = []
        project.update_surface_edge_load(existing.tag, edge_load)
        return sync_surface_edge_load(project, edge_load.tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def remove_surface_edge_load(
    project: ProjectDatabase,
    edge_load_tag: int,
) -> list[int]:
    tag = int(edge_load_tag)
    if tag not in project.surface_edge_loads:
        raise ValueError(f"Surface edge load {tag} does not exist.")
    before = project.to_dict()
    try:
        removed = detach_surface_edge_load(project, tag)
        project.remove_surface_edge_load_definition(tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return removed


def managed_surface_pressure_element_load_tags(
    project: ProjectDatabase,
) -> set[int]:
    return {
        int(load_tag)
        for pressure in project.surface_pressures.values()
        for load_tag in pressure.generated_element_load_tags
        if int(load_tag) in project.element_loads
    }


def detach_surface_pressure(
    project: ProjectDatabase,
    pressure_tag: int,
) -> list[int]:
    tag = int(pressure_tag)
    pressure = project.surface_pressures.get(tag)
    if pressure is None:
        raise ValueError(f"Surface pressure {tag} does not exist.")
    removed: list[int] = []
    for load_tag in list(pressure.generated_element_load_tags):
        normalized = int(load_tag)
        if normalized in project.element_loads:
            project.element_loads.pop(normalized)
            removed.append(normalized)
    pressure.generated_element_load_tags = []
    return removed


def sync_surface_pressure(
    project: ProjectDatabase,
    pressure_tag: int,
) -> list[int]:
    tag = int(pressure_tag)
    pressure = project.surface_pressures.get(tag)
    if pressure is None:
        raise ValueError(f"Surface pressure {tag} does not exist.")
    project._validate_surface_pressure(pressure)
    state = inspect_surface_mesh_state(project, pressure.surface_tag)
    if state.status != "meshed":
        raise ValueError(
            f"Surface {pressure.surface_tag} must have a healthy mesh "
            "before managed pressure can be applied."
        )

    before = project.to_dict()
    try:
        detach_surface_pressure(project, tag)
        surface = project.surfaces[pressure.surface_tag]
        element_tags = [
            int(element_tag)
            for element_tag in surface.generated_element_tags
            if (
                int(element_tag) in project.model.elements
                and project.model.elements[
                    int(element_tag)
                ].element_type in SHELL_ELEMENT_TYPES
            )
        ]
        next_tag = project.next_element_load_tag()
        generated: list[int] = []
        for element_tag in element_tags:
            while next_tag in project.element_loads:
                next_tag += 1
            load = ElementLoadData(
                tag=next_tag,
                name=(
                    f"{pressure.name} [managed S{pressure.surface_tag}] "
                    f"Shell {element_tag}"
                ),
                pattern_tag=pressure.pattern_tag,
                element_tag=element_tag,
                load_type="SurfacePressure",
                pressure=pressure.pressure,
            )
            project.add_element_load(load)
            generated.append(next_tag)
            next_tag += 1
        pressure.generated_element_load_tags = generated
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return list(pressure.generated_element_load_tags)


def sync_surface_pressures_for_surface(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    pressure_tags = sorted(
        pressure.tag
        for pressure in project.surface_pressures.values()
        if pressure.surface_tag == int(surface_tag)
    )
    generated: list[int] = []
    for pressure_tag in pressure_tags:
        generated.extend(sync_surface_pressure(project, pressure_tag))
    return generated


def replace_surface_pressure(
    project: ProjectDatabase,
    pressure: SurfacePressureData,
) -> list[int]:
    existing = project.surface_pressures.get(int(pressure.tag))
    if existing is None:
        raise ValueError(
            f"Surface pressure {int(pressure.tag)} does not exist."
        )
    before = project.to_dict()
    try:
        detach_surface_pressure(project, existing.tag)
        pressure.generated_element_load_tags = []
        project.update_surface_pressure(existing.tag, pressure)
        return sync_surface_pressure(project, pressure.tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def remove_surface_pressure(
    project: ProjectDatabase,
    pressure_tag: int,
) -> list[int]:
    tag = int(pressure_tag)
    if tag not in project.surface_pressures:
        raise ValueError(f"Surface pressure {tag} does not exist.")
    before = project.to_dict()
    try:
        removed = detach_surface_pressure(project, tag)
        project.remove_surface_pressure_definition(tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return removed


def managed_surface_recorder_tags(
    project: ProjectDatabase,
) -> set[int]:
    return {
        int(surface_recorder.generated_recorder_tag)
        for surface_recorder in project.surface_recorders.values()
        if (
            surface_recorder.generated_recorder_tag is not None
            and int(surface_recorder.generated_recorder_tag)
            in project.recorders
        )
    }


def detach_surface_recorder(
    project: ProjectDatabase,
    surface_recorder_tag: int,
) -> int | None:
    tag = int(surface_recorder_tag)
    surface_recorder = project.surface_recorders.get(tag)
    if surface_recorder is None:
        raise ValueError(f"Surface recorder {tag} does not exist.")
    generated_tag = surface_recorder.generated_recorder_tag
    if generated_tag is not None:
        project.recorders.pop(int(generated_tag), None)
    surface_recorder.generated_recorder_tag = None
    return None if generated_tag is None else int(generated_tag)


def sync_surface_recorder(
    project: ProjectDatabase,
    surface_recorder_tag: int,
) -> int:
    tag = int(surface_recorder_tag)
    surface_recorder = project.surface_recorders.get(tag)
    if surface_recorder is None:
        raise ValueError(f"Surface recorder {tag} does not exist.")
    state = inspect_surface_mesh_state(
        project,
        surface_recorder.surface_tag,
    )
    if state.status != "meshed":
        raise ValueError(
            f"Surface {surface_recorder.surface_tag} must have a healthy "
            "mesh before a managed Shell recorder can be generated."
        )

    before = project.to_dict()
    try:
        detach_surface_recorder(project, tag)
        surface = project.surfaces[surface_recorder.surface_tag]
        target_tags = [
            int(element_tag)
            for element_tag in surface.generated_element_tags
            if (
                int(element_tag) in project.model.elements
                and project.model.elements[
                    int(element_tag)
                ].element_type in SHELL_ELEMENT_TYPES
            )
        ]
        if not target_tags:
            raise ValueError(
                f"Surface {surface.tag} has no generated Shell elements."
            )
        recorder_tag = project.next_recorder_tag()
        recorder = RecorderData(
            tag=recorder_tag,
            name=(
                f"{surface_recorder.name} "
                f"[managed Surface {surface_recorder.surface_tag}]"
            ),
            recorder_type="Shell",
            target_tags=target_tags,
            response=surface_recorder.response,
            file_name=surface_recorder.file_name,
            include_time=surface_recorder.include_time,
            section_number=surface_recorder.section_number,
        )
        project.add_recorder(recorder)
        surface_recorder.generated_recorder_tag = recorder.tag
        project._validate_surface_recorder(surface_recorder)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return int(surface_recorder.generated_recorder_tag)


def sync_surface_recorders_for_surface(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    definition_tags = sorted(
        surface_recorder.tag
        for surface_recorder in project.surface_recorders.values()
        if surface_recorder.surface_tag == int(surface_tag)
    )
    return [
        sync_surface_recorder(project, definition_tag)
        for definition_tag in definition_tags
    ]


def replace_surface_recorder(
    project: ProjectDatabase,
    surface_recorder: SurfaceRecorderData,
) -> int:
    existing = project.surface_recorders.get(int(surface_recorder.tag))
    if existing is None:
        raise ValueError(
            f"Surface recorder {int(surface_recorder.tag)} does not exist."
        )
    before = project.to_dict()
    try:
        detach_surface_recorder(project, existing.tag)
        surface_recorder.generated_recorder_tag = None
        project.update_surface_recorder(existing.tag, surface_recorder)
        return sync_surface_recorder(project, surface_recorder.tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def remove_surface_recorder(
    project: ProjectDatabase,
    surface_recorder_tag: int,
) -> int | None:
    tag = int(surface_recorder_tag)
    if tag not in project.surface_recorders:
        raise ValueError(f"Surface recorder {tag} does not exist.")
    before = project.to_dict()
    try:
        generated_tag = detach_surface_recorder(project, tag)
        project.remove_surface_recorder_definition(tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return generated_tag


def managed_surface_result_tags(
    project: ProjectDatabase,
) -> set[int]:
    return {
        int(result.tag)
        for result in project.solution_results.values()
        if result.surface_scope
    }


def sync_solution_result_surface_scope(
    project: ProjectDatabase,
    result_tag: int,
) -> list[int]:
    tag = int(result_tag)
    result = project.solution_results.get(tag)
    if result is None:
        raise ValueError(f"Solution result {tag} does not exist.")
    if not result.surface_scope:
        return list(result.element_scope)
    missing = [
        surface_tag
        for surface_tag in result.surface_scope
        if surface_tag not in project.surfaces
    ]
    if missing:
        raise ValueError(
            "Managed Surface result references missing Surface tag(s): "
            + ", ".join(map(str, missing))
        )
    result.element_scope = sorted({
        int(element_tag)
        for surface_tag in result.surface_scope
        for element_tag in project.surfaces[
            surface_tag
        ].generated_element_tags
        if (
            int(element_tag) in project.model.elements
            and project.model.elements[
                int(element_tag)
            ].element_type in SHELL_ELEMENT_TYPES
        )
    })
    project._validate_solution_result(result)
    return list(result.element_scope)


def sync_surface_results_for_surface(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    tag = int(surface_tag)
    result_tags = sorted(
        result.tag
        for result in project.solution_results.values()
        if tag in result.surface_scope
    )
    for result_tag in result_tags:
        sync_solution_result_surface_scope(project, result_tag)
    return result_tags


def detach_surface_result_scope(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")
    if not surface.mesh_recipe_configured:
        raise ValueError(
            f"Surface geometry {tag} has no Mesh recipe yet. "
            "Configure Surface Mesh before generating Shell FE."
        )
    owned_elements = {
        int(element_tag)
        for element_tag in surface.generated_element_tags
    }
    changed: list[int] = []
    for result in project.solution_results.values():
        if tag not in result.surface_scope:
            continue
        before = list(result.element_scope)
        result.element_scope = [
            int(element_tag)
            for element_tag in result.element_scope
            if int(element_tag) not in owned_elements
        ]
        if result.element_scope != before:
            changed.append(int(result.tag))
    return sorted(changed)


def remove_surface_from_managed_result_scopes(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[int]:
    tag = int(surface_tag)
    removed_results: list[int] = []
    for result_tag, result in list(project.solution_results.items()):
        if tag not in result.surface_scope:
            continue
        result.surface_scope = [
            surface
            for surface in result.surface_scope
            if int(surface) != tag
        ]
        if not result.surface_scope:
            project.solution_results.pop(result_tag, None)
            removed_results.append(int(result_tag))
        else:
            sync_solution_result_surface_scope(project, result_tag)
    return sorted(removed_results)


def managed_surface_selection_names(
    project: ProjectDatabase,
) -> set[str]:
    return {
        str(selection.name)
        for selection in project.selection_sets.values()
        if selection.surface_tags
    }


def sync_selection_set_surface_scope(
    project: ProjectDatabase,
    name: str,
) -> tuple[set[int], set[int]]:
    key = str(name)
    selection = project.selection_sets.get(key)
    if selection is None:
        raise ValueError(f"Named selection {key!r} does not exist.")
    if not selection.surface_tags:
        return set(selection.node_tags), set(selection.element_tags)
    project._materialize_selection_set_surface_scope(selection)
    project.validate_selection_set(selection)
    return set(selection.node_tags), set(selection.element_tags)


def sync_surface_selection_sets_for_surface(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[str]:
    tag = int(surface_tag)
    names = sorted(
        selection.name
        for selection in project.selection_sets.values()
        if tag in selection.surface_tags
    )
    for name in names:
        sync_selection_set_surface_scope(project, name)
    return names


def detach_surface_selection_scope(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[str]:
    tag = int(surface_tag)
    changed: list[str] = []
    for selection in project.selection_sets.values():
        if tag not in selection.surface_tags:
            continue
        include_nodes = selection.surface_scope_mode in {
            "nodes",
            "nodes_and_elements",
        }
        include_elements = selection.surface_scope_mode in {
            "elements",
            "nodes_and_elements",
        }
        remaining = {
            int(source_tag)
            for source_tag in selection.surface_tags
            if int(source_tag) != tag
            and int(source_tag) in project.surfaces
        }
        selection.node_tags = (
            {
                int(node_tag)
                for source_tag in remaining
                for node_tag in project.surfaces[
                    source_tag
                ].generated_node_tags
                if int(node_tag) in project.model.nodes
            }
            if include_nodes
            else set()
        )
        selection.element_tags = (
            {
                int(element_tag)
                for source_tag in remaining
                for element_tag in project.surfaces[
                    source_tag
                ].generated_element_tags
                if (
                    int(element_tag) in project.model.elements
                    and project.model.elements[
                        int(element_tag)
                    ].element_type in SHELL_ELEMENT_TYPES
                )
            }
            if include_elements
            else set()
        )
        changed.append(str(selection.name))
    return sorted(changed)


def remove_surface_from_managed_selection_sets(
    project: ProjectDatabase,
    surface_tag: int,
) -> list[str]:
    tag = int(surface_tag)
    removed: list[str] = []
    for name, selection in list(project.selection_sets.items()):
        if tag not in selection.surface_tags:
            continue
        selection.surface_tags = {
            int(source_tag)
            for source_tag in selection.surface_tags
            if int(source_tag) != tag
        }
        if not selection.surface_tags:
            project.selection_sets.pop(name, None)
            removed.append(str(name))
        else:
            sync_selection_set_surface_scope(project, name)
    return sorted(removed)


def mesh_surface_geometry(
    project: ProjectDatabase,
    surface_tag: int,
) -> SurfaceMeshResult:
    """Create a mapped quadrilateral shell mesh from an independent surface."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")
    if not surface.mesh_recipe_configured:
        raise ValueError(
            f"Surface geometry {tag} has no Mesh recipe yet. "
            "Configure Surface Mesh before generating Shell FE."
        )
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
        sync_surface_edge_supports_for_surface(project, surface.tag)
        sync_surface_edge_loads_for_surface(project, surface.tag)
        sync_surface_pressures_for_surface(project, surface.tag)
        sync_surface_recorders_for_surface(project, surface.tag)
        sync_surface_results_for_surface(project, surface.tag)
        sync_surface_selection_sets_for_surface(project, surface.tag)
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

    managed_pressure_load_tags = managed_surface_pressure_element_load_tags(
        project
    )
    load_tags = sorted(
        load.tag
        for load in project.element_loads.values()
        if (
            int(load.element_tag) in element_tags
            and int(load.tag) not in managed_pressure_load_tags
        )
    )
    if load_tags:
        blockers.append(
            "element load(s) " + ", ".join(map(str, load_tags))
        )

    managed_recorder_tags = managed_surface_recorder_tags(project)
    recorder_tags = sorted(
        recorder.tag
        for recorder in project.recorders.values()
        if (
            recorder.recorder_type != "Node"
            and int(recorder.tag) not in managed_recorder_tags
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

    managed_result_tags = managed_surface_result_tags(project)
    result_tags = sorted(
        result.tag
        for result in project.solution_results.values()
        if (
            int(result.tag) not in managed_result_tags
            and any(
                int(tag) in element_tags
                for tag in result.element_scope
            )
        )
    )
    if result_tags:
        blockers.append(
            "result request(s) " + ", ".join(map(str, result_tags))
        )

    managed_selection_names = managed_surface_selection_names(project)
    set_names = sorted(
        selection.name
        for selection in project.selection_sets.values()
        if (
            selection.name not in managed_selection_names
            and any(
                int(tag) in element_tags
                for tag in selection.element_tags
            )
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
        and not selection.surface_tags
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
    managed_selection_names = managed_surface_selection_names(project)
    tracked_nodes = set(state.tracked_node_tags)
    direct_node_selection_names = sorted(
        selection.name
        for selection in project.selection_sets.values()
        if (
            selection.name not in managed_selection_names
            and any(
                int(node_tag) in tracked_nodes
                for node_tag in selection.node_tags
            )
        )
    )
    if direct_node_selection_names:
        blockers.append(
            "named selection(s) "
            + ", ".join(direct_node_selection_names)
        )
    if blockers:
        raise ValueError(
            "Cannot delete/remesh Surface generated FE mesh because it is "
            "referenced by " + "; ".join(blockers) + "."
        )

    before = project.to_dict()
    try:
        detach_surface_selection_scope(project, tag)
        detach_surface_result_scope(project, tag)

        surface_recorder_tags = sorted(
            surface_recorder.tag
            for surface_recorder in project.surface_recorders.values()
            if surface_recorder.surface_tag == tag
        )
        for surface_recorder_tag in surface_recorder_tags:
            detach_surface_recorder(project, surface_recorder_tag)

        pressure_tags = sorted(
            pressure.tag
            for pressure in project.surface_pressures.values()
            if pressure.surface_tag == tag
        )
        for pressure_tag in pressure_tags:
            detach_surface_pressure(project, pressure_tag)

        edge_load_tags = sorted(
            edge_load.tag
            for edge_load in project.surface_edge_loads.values()
            if edge_load.surface_tag == tag
        )
        for edge_load_tag in edge_load_tags:
            detach_surface_edge_load(project, edge_load_tag)

        support_tags = sorted(
            support.tag
            for support in project.surface_edge_supports.values()
            if support.surface_tag == tag
        )
        for support_tag in support_tags:
            detach_surface_edge_support(project, support_tag)

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
        support_tags = sorted(
            support.tag
            for support in project.surface_edge_supports.values()
            if support.surface_tag == tag
        )
        edge_load_tags = sorted(
            edge_load.tag
            for edge_load in project.surface_edge_loads.values()
            if edge_load.surface_tag == tag
        )
        pressure_tags = sorted(
            pressure.tag
            for pressure in project.surface_pressures.values()
            if pressure.surface_tag == tag
        )
        surface_recorder_tags = sorted(
            surface_recorder.tag
            for surface_recorder in project.surface_recorders.values()
            if surface_recorder.surface_tag == tag
        )
        deleted = delete_surface_mesh(project, tag)
        for support_tag in support_tags:
            project.surface_edge_supports.pop(support_tag, None)
        for edge_load_tag in edge_load_tags:
            project.surface_edge_loads.pop(edge_load_tag, None)
        for pressure_tag in pressure_tags:
            project.surface_pressures.pop(pressure_tag, None)
        for surface_recorder_tag in surface_recorder_tags:
            project.surface_recorders.pop(surface_recorder_tag, None)
        remove_surface_from_managed_result_scopes(project, tag)
        remove_surface_from_managed_selection_sets(project, tag)
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

        for support in project.surface_edge_supports.values():
            if support.surface_tag == tag:
                support.edge_index = 5 - int(support.edge_index)
        for edge_load in project.surface_edge_loads.values():
            if edge_load.surface_tag == tag:
                edge_load.edge_index = 5 - int(edge_load.edge_index)
        for pressure in project.surface_pressures.values():
            if pressure.surface_tag == tag:
                pressure.pressure = -float(pressure.pressure)

        # Reversing winding with P1 fixed exchanges the Surface U/V
        # directions. Preserve the physical mapped-mesh recipe instead of
        # silently changing the subdivisions on each physical edge.
        surface.divisions_u, surface.divisions_v = (
            surface.divisions_v,
            surface.divisions_u,
        )
        surface.bias_u, surface.bias_v = (
            surface.bias_v,
            surface.bias_u,
        )
        if surface.edge_divisions is not None:
            e1, e2, e3, e4 = surface.edge_divisions
            surface.edge_divisions = (e4, e3, e2, e1)

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


def _surface_edge_record(
    surface: SurfaceGeometryData,
    edge_index: int,
):
    index = int(edge_index)
    if index not in {1, 2, 3, 4}:
        raise ValueError("Surface edge index must be 1, 2, 3, or 4.")
    for start, end, divisions, candidate in _surface_edges(surface):
        if candidate == index:
            return start, end, int(divisions)
    raise ValueError(f"Surface edge {index} does not exist.")


def surface_edge_info(
    project: ProjectDatabase,
    surface_tag: int,
    edge_index: int,
    *,
    tolerance: float | None = None,
) -> SurfaceEdgeInfo:
    """Resolve one geometry edge and its ordered live FE edge nodes."""
    tag = int(surface_tag)
    surface = project.surfaces.get(tag)
    if surface is None:
        raise ValueError(f"Surface geometry {tag} does not exist.")

    start, end, requested = _surface_edge_record(surface, edge_index)
    surfaces = list(project.surfaces.values())
    tol = (
        float(tolerance)
        if tolerance is not None
        else 1.0e-8 * _surface_span(project, surfaces)
    )
    if not math.isfinite(tol) or tol <= 0.0:
        raise ValueError("Surface edge tolerance must be finite and positive.")

    nodes = _live_surface_edge_nodes(
        project,
        surface,
        start,
        end,
        tolerance=tol,
    )
    live_nodes = list(nodes or [])
    actual = len(live_nodes) - 1 if len(live_nodes) >= 2 else 0

    neighbors: list[tuple[int, int]] = []
    connected: list[tuple[int, int]] = []
    for other_tag, other in sorted(project.surfaces.items()):
        if int(other_tag) == tag:
            continue
        for other_start, other_end, _divisions, other_edge in _surface_edges(
            other
        ):
            if not _same_edge(start, end, other_start, other_end, tol):
                continue
            ref = (int(other_tag), int(other_edge))
            neighbors.append(ref)
            other_nodes = _live_surface_edge_nodes(
                project,
                other,
                other_start,
                other_end,
                tolerance=tol,
            )
            if (
                nodes is not None
                and other_nodes is not None
                and (
                    nodes == other_nodes
                    or nodes == list(reversed(other_nodes))
                )
            ):
                connected.append(ref)

    return SurfaceEdgeInfo(
        surface_tag=tag,
        edge_index=int(edge_index),
        start_point=tuple(float(value) for value in start),
        end_point=tuple(float(value) for value in end),
        length=_distance3(start, end),
        requested_divisions=requested,
        live_node_tags=live_nodes,
        actual_divisions=actual,
        neighbor_edges=sorted(set(neighbors)),
        connected_neighbor_edges=sorted(set(connected)),
    )


def surface_edge_node_tags(
    project: ProjectDatabase,
    surface_tag: int,
    edge_index: int,
) -> list[int]:
    """Return ordered FE node tags along one meshed Surface edge."""
    info = surface_edge_info(project, surface_tag, edge_index)
    if len(info.live_node_tags) < 2:
        raise ValueError(
            f"Surface {int(surface_tag)} edge {int(edge_index)} has no "
            "live FE edge nodes. Mesh the Surface first."
        )
    return list(info.live_node_tags)


# Task 2: external boundary extraction for one or more selected Surfaces.
def surface_boundary_edges(
    project: ProjectDatabase,
    surface_tags,
) -> list[SurfaceEdgeInfo]:
    tags = sorted({
        int(tag)
        for tag in surface_tags
        if int(tag) in project.surfaces
    })
    selected = set(tags)
    boundary: list[SurfaceEdgeInfo] = []
    for tag in tags:
        for edge_index in range(1, 5):
            info = surface_edge_info(project, tag, edge_index)
            if any(
                neighbor_tag in selected
                for neighbor_tag, _neighbor_edge in info.neighbor_edges
            ):
                continue
            boundary.append(info)
    return boundary


def surface_boundary_node_tags(
    project: ProjectDatabase,
    surface_tags,
) -> list[int]:
    tags = sorted({
        int(tag)
        for tag in surface_tags
        if int(tag) in project.surfaces
    })
    bad = [
        tag
        for tag in tags
        if inspect_surface_mesh_state(project, tag).status != "meshed"
    ]
    if bad:
        raise ValueError(
            "Mesh the following Surface geometry before selecting its "
            "boundary FE nodes: " + ", ".join(map(str, bad))
        )

    nodes: set[int] = set()
    for info in surface_boundary_edges(project, tags):
        nodes.update(info.live_node_tags)
    if not nodes and tags:
        raise ValueError(
            "No live FE nodes were found on the selected Surface boundary."
        )
    return sorted(nodes)


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
