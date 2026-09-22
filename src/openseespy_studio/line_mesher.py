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
    coordinates: list[float] = field(default_factory=list)


@dataclass(slots=True)
class LineMeshState:
    line_tag: int
    status: str
    tracked_element_tags: list[int] = field(default_factory=list)
    live_element_tags: list[int] = field(default_factory=list)
    missing_element_tags: list[int] = field(default_factory=list)
    foreign_element_tags: list[int] = field(default_factory=list)
    untracked_owned_element_tags: list[int] = field(default_factory=list)
    tracked_node_tags: list[int] = field(default_factory=list)
    missing_node_tags: list[int] = field(default_factory=list)
    owned_node_tags: list[int] = field(default_factory=list)
    missing_owned_node_tags: list[int] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.status in {"unmeshed", "meshed"}

    @property
    def issue_count(self) -> int:
        return sum(
            len(values)
            for values in (
                self.missing_element_tags,
                self.foreign_element_tags,
                self.untracked_owned_element_tags,
                self.missing_node_tags,
                self.missing_owned_node_tags,
            )
        )


@dataclass(slots=True)
class LineMeshDeleteResult:
    line_tag: int
    removed_element_tags: list[int] = field(default_factory=list)
    removed_node_tags: list[int] = field(default_factory=list)
    kept_node_tags: list[int] = field(default_factory=list)


@dataclass(slots=True)
class LineMeshIntegrityReport:
    line_count: int
    states: list[LineMeshState] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return sum(state.issue_count for state in self.states)


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


def line_mesh_divisions(
    project: ProjectDatabase,
    line: LineGeometryData,
) -> int:
    _a, _b, length = _line_points(project, line)
    divisions = int(line.divisions)
    if line.mesh_mode == "target_size":
        if line.target_size is None:
            raise ValueError("Target element size is required.")
        divisions = max(
            1,
            int(math.ceil(length / float(line.target_size))),
        )
    return divisions


def line_mesh_coordinates(
    divisions: int,
    bias: float = 1.0,
) -> list[float]:
    """Return normalized node coordinates from 0 to 1.

    Bias is the last element length divided by the first. A value of 1.0
    produces a uniform mesh. Values >1 grow toward Point J; values <1 refine
    toward Point J.
    """
    count = int(divisions)
    if count < 1:
        raise ValueError("Line mesh divisions must be positive.")
    factor = float(bias)
    if not math.isfinite(factor) or factor <= 0.0:
        raise ValueError("Line mesh bias must be finite and positive.")
    if count == 1:
        return [0.0, 1.0]
    if abs(factor - 1.0) <= 1.0e-12:
        return [index / count for index in range(count + 1)]

    log_ratio = math.log(factor) / float(count - 1)
    weights = [math.exp(log_ratio * index) for index in range(count)]
    total = sum(weights)
    coords = [0.0]
    running = 0.0
    for weight in weights:
        running += weight
        coords.append(running / total)
    coords[-1] = 1.0
    return coords


def line_mesh_preview_points(
    project: ProjectDatabase,
    line: LineGeometryData,
) -> tuple[int, list[tuple[float, float, float]]]:
    a, b, _length = _line_points(project, line)
    divisions = line_mesh_divisions(project, line)
    coordinates = line_mesh_coordinates(divisions, line.bias)
    points = [
        tuple(
            a[axis] + ratio * (b[axis] - a[axis])
            for axis in range(3)
        )
        for ratio in coordinates
    ]
    return divisions, points


def mesh_line_geometry(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshResult:
    """Discretize one Geometry Line into owned OpenSees Frame/Truss elements."""
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
            "Delete/remesh its generated FE mesh before meshing again."
        )

    a, b, _length = _line_points(project, line)
    divisions = line_mesh_divisions(project, line)
    coordinates = line_mesh_coordinates(divisions, line.bias)

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

        for ratio in coordinates:
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

        if len(set(node_tags)) != len(node_tags):
            raise ValueError(
                "Line mesh collapsed onto duplicate FE nodes. "
                "Reduce merge tolerance conflicts or change the mesh recipe."
            )

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

        line.generated_node_tags = list(node_tags)
        line.owned_node_tags = sorted(set(created))
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
        coordinates=list(coordinates),
    )


def inspect_line_mesh_state(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshState:
    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")

    expected_group = f"line:{tag}"
    tracked_elements = sorted({
        int(element_tag)
        for element_tag in line.generated_element_tags
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

    tracked_nodes = [
        int(node_tag)
        for node_tag in line.generated_node_tags
    ]
    missing_nodes = [
        node_tag
        for node_tag in tracked_nodes
        if node_tag not in project.model.nodes
    ]
    owned_nodes = sorted({
        int(node_tag)
        for node_tag in line.owned_node_tags
    })
    missing_owned_nodes = [
        node_tag
        for node_tag in owned_nodes
        if node_tag not in project.model.nodes
    ]

    has_tracking = bool(
        tracked_elements
        or tracked_nodes
        or owned_elements
        or owned_nodes
    )
    stale = bool(
        missing_elements
        or foreign_elements
        or untracked_owned
        or missing_nodes
        or missing_owned_nodes
        or (has_tracking and not live_elements and owned_elements)
    )
    if not has_tracking:
        status = "unmeshed"
    elif stale:
        status = "stale"
    else:
        status = "meshed"

    return LineMeshState(
        line_tag=tag,
        status=status,
        tracked_element_tags=tracked_elements,
        live_element_tags=live_elements,
        missing_element_tags=missing_elements,
        foreign_element_tags=foreign_elements,
        untracked_owned_element_tags=untracked_owned,
        tracked_node_tags=tracked_nodes,
        missing_node_tags=missing_nodes,
        owned_node_tags=owned_nodes,
        missing_owned_node_tags=missing_owned_nodes,
    )


def audit_line_mesh_integrity(
    project: ProjectDatabase,
    line_tags=None,
) -> LineMeshIntegrityReport:
    tags = sorted(
        int(tag)
        for tag in (
            project.lines
            if line_tags is None
            else line_tags
        )
        if int(tag) in project.lines
    )
    return LineMeshIntegrityReport(
        line_count=len(tags),
        states=[
            inspect_line_mesh_state(project, tag)
            for tag in tags
        ],
    )


def _line_element_dependency_blockers(
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
                int(target) in element_tags
                for target in recorder.target_tags
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
            int(target) in element_tags
            for target in result.element_scope
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
            int(target) in element_tags
            for target in selection.element_tags
        )
    )
    if set_names:
        blockers.append(
            "named selection(s) " + ", ".join(set_names)
        )
    return blockers


def _line_owned_node_dependency_blockers(
    project: ProjectDatabase,
    node_tags: set[int],
    owned_element_tags: set[int],
) -> list[str]:
    blockers: list[str] = []
    if not node_tags:
        return blockers

    stateful = sorted(
        tag
        for tag in node_tags
        if (
            tag in project.model.nodes
            and (
                any(project.model.nodes[tag].fixity)
                or any(
                    abs(float(value)) > 0.0
                    for value in project.model.nodes[tag].mass
                )
            )
        )
    )
    if stateful:
        blockers.append(
            "node restraint/mass at node(s) "
            + ", ".join(map(str, stateful))
        )

    connection_nodes = sorted({
        tag
        for tag in node_tags
        if any(
            tag in {connection.node_i, connection.node_j}
            for connection in project.connections.values()
        )
    })
    if connection_nodes:
        blockers.append(
            "connection node(s) "
            + ", ".join(map(str, connection_nodes))
        )

    constraint_nodes = sorted({
        tag
        for tag in node_tags
        if any(
            (
                constraint.retained_node == tag
                or tag in constraint.constrained_nodes
            )
            for constraint in project.constraints.values()
        )
    })
    if constraint_nodes:
        blockers.append(
            "constraint node(s) "
            + ", ".join(map(str, constraint_nodes))
        )

    load_tags = sorted(
        load.tag
        for load in project.nodal_loads.values()
        if int(load.node_tag) in node_tags
    )
    if load_tags:
        blockers.append(
            "nodal load(s) " + ", ".join(map(str, load_tags))
        )

    displacement_tags = sorted(
        displacement.tag
        for displacement in project.prescribed_displacements.values()
        if int(displacement.node_tag) in node_tags
    )
    if displacement_tags:
        blockers.append(
            "prescribed displacement(s) "
            + ", ".join(map(str, displacement_tags))
        )

    recorder_tags = sorted(
        recorder.tag
        for recorder in project.recorders.values()
        if (
            recorder.recorder_type == "Node"
            and any(
                int(target) in node_tags
                for target in recorder.target_tags
            )
        )
    )
    if recorder_tags:
        blockers.append(
            "node recorder(s) " + ", ".join(map(str, recorder_tags))
        )

    result_tags = sorted(
        result.tag
        for result in project.solution_results.values()
        if any(
            int(target) in node_tags
            for target in result.node_scope
        )
    )
    if result_tags:
        blockers.append(
            "node result request(s) "
            + ", ".join(map(str, result_tags))
        )

    set_names = sorted(
        selection.name
        for selection in project.selection_sets.values()
        if any(
            int(target) in node_tags
            for target in selection.node_tags
        )
    )
    if set_names:
        blockers.append(
            "named selection(s) " + ", ".join(set_names)
        )

    # An external element may legitimately share a generated Line node. Keep
    # that node after deleting the owned Line elements; do not block remesh.
    return blockers


def _line_node_used_by_surviving_element(
    project: ProjectDatabase,
    node_tag: int,
    deleting_elements: set[int],
) -> bool:
    tag = int(node_tag)
    return any(
        int(element_tag) not in deleting_elements
        and tag in element.node_tags()
        for element_tag, element in project.model.elements.items()
    )


def delete_line_mesh(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshDeleteResult:
    """Delete only FE entities owned by one Geometry Line."""
    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")

    state = inspect_line_mesh_state(project, tag)
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
            "Cannot delete/remesh Line generated FE mesh because its "
            "ownership is inconsistent ("
            + "; ".join(details)
            + "). Run Audit Line Mesh Integrity first."
        )

    live_elements = set(state.live_element_tags)
    blockers = _line_element_dependency_blockers(
        project,
        live_elements,
    )
    blockers.extend(
        _line_owned_node_dependency_blockers(
            project,
            set(state.owned_node_tags),
            live_elements,
        )
    )
    if blockers:
        raise ValueError(
            "Cannot delete/remesh Line generated FE mesh because it is "
            "referenced by " + "; ".join(blockers) + "."
        )

    before = project.to_dict()
    try:
        for element_tag in sorted(live_elements):
            project.model.elements.pop(element_tag, None)

        removed_nodes: list[int] = []
        kept_nodes: list[int] = []
        for node_tag in state.owned_node_tags:
            if node_tag not in project.model.nodes:
                continue
            if _line_node_used_by_surviving_element(
                project,
                node_tag,
                live_elements,
            ):
                kept_nodes.append(node_tag)
                continue
            project.model.nodes.pop(node_tag, None)
            removed_nodes.append(node_tag)

        line.generated_node_tags = []
        line.owned_node_tags = []
        line.generated_element_tags = []
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise

    return LineMeshDeleteResult(
        line_tag=tag,
        removed_element_tags=sorted(live_elements),
        removed_node_tags=sorted(removed_nodes),
        kept_node_tags=sorted(kept_nodes),
    )


def remesh_line_geometry(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshResult:
    tag = int(line_tag)
    if tag not in project.lines:
        raise ValueError(f"Line geometry {tag} does not exist.")
    before = project.to_dict()
    try:
        delete_line_mesh(project, tag)
        return mesh_line_geometry(project, tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def delete_line_geometry(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshDeleteResult:
    """Atomically delete a Line and the Frame/Truss mesh it owns."""
    tag = int(line_tag)
    if tag not in project.lines:
        raise ValueError(f"Line geometry {tag} does not exist.")
    before = project.to_dict()
    try:
        deleted = delete_line_mesh(project, tag)
        project.remove_line(tag)
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return deleted
