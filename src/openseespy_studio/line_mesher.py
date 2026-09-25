from __future__ import annotations

from dataclasses import dataclass, field
import math

from .model import FRAME_ELEMENT_TYPES
from .project import LineGeometryData, PointGeometryData, ProjectDatabase


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


def _find_topology_endpoint_node(
    project: ProjectDatabase,
    line: LineGeometryData,
    ratio: float,
) -> int | None:
    """Reuse the FE node of a shared Geometry Point regardless of merge mode.

    Geometry topology is authoritative: if two Lines reference the same Point,
    their endpoint FE nodes must be identical. The reuse_existing_nodes flag
    only controls coordinate-based merging between otherwise unrelated
    geometry.
    """

    endpoint_point_tag: int | None = None
    if abs(float(ratio)) <= 1.0e-12:
        endpoint_point_tag = int(line.point_i)
    elif abs(float(ratio) - 1.0) <= 1.0e-12:
        endpoint_point_tag = int(line.point_j)
    if endpoint_point_tag is None:
        return None

    candidates: list[int] = []
    for other in project.lines.values():
        if int(other.tag) == int(line.tag):
            continue
        if not other.generated_node_tags:
            continue
        if not any(
            int(element_tag) in project.model.elements
            for element_tag in other.generated_element_tags
        ):
            continue
        if int(other.point_i) == endpoint_point_tag:
            candidates.append(int(other.generated_node_tags[0]))
        if int(other.point_j) == endpoint_point_tag:
            candidates.append(int(other.generated_node_tags[-1]))

    live = sorted({
        tag
        for tag in candidates
        if tag in project.model.nodes
    })
    if not live:
        return None
    return live[0]


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

    if not line.mesh_recipe_configured:
        raise ValueError(
            f"Line geometry {tag} has no Mesh recipe yet. "
            "Configure Line Mesh before generating Frame/Truss FE."
        )

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
            existing = _find_topology_endpoint_node(
                project,
                line,
                ratio,
            )
            if existing is None and line.reuse_existing_nodes:
                existing = _find_existing_node(
                    project,
                    xyz,
                    tolerance,
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
                    beam_center_ratio=line.center_rotation,
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

@dataclass(slots=True)
class LineMeshQuality:
    """Length-quality summary for one Geometry Line FE discretization."""

    line_tag: int
    element_count: int
    total_length: float
    min_length: float
    max_length: float
    mean_length: float
    length_ratio: float
    lengths: list[float] = field(default_factory=list)

    @property
    def uniform(self) -> bool:
        return self.length_ratio <= 1.0 + 1.0e-9


@dataclass(slots=True)
class LineConnectivityIssue:
    """One geometric Line intersection that is not FE-connected."""

    kind: str
    line_tags: tuple[int, int]
    point: tuple[float, float, float]
    parameters: tuple[float, float]
    message: str


def _distance(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return math.sqrt(
        sum(
            (float(left[index]) - float(right[index])) ** 2
            for index in range(3)
        )
    )


def line_mesh_quality(
    project: ProjectDatabase,
    line_tag: int,
) -> LineMeshQuality:
    """Return actual FE segment-length statistics, or preview stats if unmeshed."""

    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")

    if not line.mesh_recipe_configured:
        raise ValueError(
            f"Line geometry {tag} has no Mesh recipe yet."
        )

    state = inspect_line_mesh_state(project, tag)
    lengths: list[float] = []
    if state.live_element_tags:
        for element_tag in line.generated_element_tags:
            element = project.model.elements.get(int(element_tag))
            if element is None or element.group != f"line:{tag}":
                continue
            node_i = project.model.nodes.get(int(element.i))
            node_j = project.model.nodes.get(int(element.j))
            if node_i is None or node_j is None:
                continue
            lengths.append(_distance(node_i.xyz, node_j.xyz))
    else:
        _divisions, points = line_mesh_preview_points(project, line)
        lengths = [
            _distance(a, b)
            for a, b in zip(points[:-1], points[1:])
        ]

    if not lengths or any(length <= 1.0e-15 for length in lengths):
        raise ValueError(
            f"Line geometry {tag} does not have a valid positive-length mesh."
        )

    total = sum(lengths)
    minimum = min(lengths)
    maximum = max(lengths)
    return LineMeshQuality(
        line_tag=tag,
        element_count=len(lengths),
        total_length=total,
        min_length=minimum,
        max_length=maximum,
        mean_length=total / len(lengths),
        length_ratio=maximum / minimum,
        lengths=list(lengths),
    )


def reverse_line_geometry(
    project: ProjectDatabase,
    line_tag: int,
    *,
    remesh: bool = True,
) -> LineMeshResult | None:
    """Reverse I/J while preserving the physical grading distribution."""

    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")
    state = inspect_line_mesh_state(project, tag)
    had_live_mesh = bool(state.live_element_tags)
    if had_live_mesh and not remesh:
        raise ValueError(
            "A meshed Geometry Line must be remeshed when its direction is "
            "reversed."
        )

    before = project.to_dict()
    try:
        if had_live_mesh:
            delete_line_mesh(project, tag)
        line = project.lines[tag]
        line.point_i, line.point_j = line.point_j, line.point_i
        line.bias = 1.0 / float(line.bias)
        project._validate_line_geometry(line)
        if had_live_mesh:
            return mesh_line_geometry(project, tag)
        return None
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


_LINE_RECIPE_FIELDS = (
    "mesh_recipe_configured",
    "mesh_mode",
    "divisions",
    "target_size",
    "bias",
    "reuse_existing_nodes",
    "element_family",
    "element_type",
    "section_tag",
    "transformation_tag",
    "material_tag",
    "area",
    "integration_type",
    "integration_points",
    "mass_per_length",
    "consistent_mass",
    "do_rayleigh",
)


def copy_line_mesh_recipe(
    project: ProjectDatabase,
    source_tag: int,
    target_tags,
    *,
    remesh_live: bool = True,
) -> dict[int, LineMeshResult | None]:
    """Copy FE/mesh settings without changing target Line identity/topology."""

    source_key = int(source_tag)
    source = project.lines.get(source_key)
    if source is None:
        raise ValueError(f"Source Line geometry {source_key} does not exist.")

    targets = sorted({
        int(tag)
        for tag in target_tags
        if int(tag) != source_key
    })
    missing = [tag for tag in targets if tag not in project.lines]
    if missing:
        raise ValueError(
            "Target Line geometry tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )

    live_before = {
        tag: bool(inspect_line_mesh_state(project, tag).live_element_tags)
        for tag in targets
    }
    blocked = [
        tag for tag, live in live_before.items()
        if live and not remesh_live
    ]
    if blocked:
        raise ValueError(
            "Meshed target Line(s) require remesh_live=True: "
            + ", ".join(map(str, blocked))
        )

    before = project.to_dict()
    results: dict[int, LineMeshResult | None] = {}
    try:
        for tag in targets:
            if live_before[tag]:
                delete_line_mesh(project, tag)

            current = project.lines[tag]
            data = current.to_dict()
            for field_name in _LINE_RECIPE_FIELDS:
                data[field_name] = getattr(source, field_name)
            data["generated_node_tags"] = []
            data["owned_node_tags"] = []
            data["generated_element_tags"] = []
            updated = LineGeometryData.from_dict(data)
            project.update_line(tag, updated)
            results[tag] = (
                mesh_line_geometry(project, tag)
                if live_before[tag]
                else None
            )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise
    return results


def remesh_line_batch(
    project: ProjectDatabase,
    line_tags,
) -> dict[int, LineMeshResult]:
    """Atomically remesh a connected set of Lines with shared-node reuse."""

    tags = sorted({int(tag) for tag in line_tags})
    if not tags:
        return {}
    missing = [tag for tag in tags if tag not in project.lines]
    if missing:
        raise ValueError(
            "Geometry Line tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )

    states = {
        tag: inspect_line_mesh_state(project, tag)
        for tag in tags
    }
    stale = [
        tag for tag, state in states.items()
        if not state.healthy
    ]
    if stale:
        raise ValueError(
            "Cannot batch-remesh stale Line mesh ownership: "
            + ", ".join(map(str, stale))
        )

    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    before = project.to_dict()
    try:
        for tag in tags:
            if states[tag].live_element_tags:
                delete_line_mesh(project, tag)

        for node_tag in sorted(candidate_owned_nodes):
            if node_tag not in project.model.nodes:
                continue
            if any(
                node_tag in element.node_tags()
                for element in project.model.elements.values()
            ):
                continue
            project.model.nodes.pop(node_tag, None)

        results: dict[int, LineMeshResult] = {}
        for tag in tags:
            results[tag] = mesh_line_geometry(project, tag)
        return results
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def _segment_intersection(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    d: tuple[float, float, float],
    tolerance: float,
) -> tuple[tuple[float, float, float], float, float] | None:
    """Return a non-parallel 3D segment intersection within tolerance."""

    u = tuple(b[index] - a[index] for index in range(3))
    v = tuple(d[index] - c[index] for index in range(3))
    w = tuple(a[index] - c[index] for index in range(3))
    uu = sum(value * value for value in u)
    uv = sum(u[index] * v[index] for index in range(3))
    vv = sum(value * value for value in v)
    uw = sum(u[index] * w[index] for index in range(3))
    vw = sum(v[index] * w[index] for index in range(3))
    denominator = uu * vv - uv * uv
    if uu <= 1.0e-24 or vv <= 1.0e-24:
        return None
    if abs(denominator) <= 1.0e-12 * uu * vv:
        return None

    s = (uv * vw - vv * uw) / denominator
    t = (uu * vw - uv * uw) / denominator
    param_tol = tolerance / max(math.sqrt(uu), math.sqrt(vv), tolerance)
    if not (-param_tol <= s <= 1.0 + param_tol):
        return None
    if not (-param_tol <= t <= 1.0 + param_tol):
        return None

    p = tuple(a[index] + s * u[index] for index in range(3))
    q = tuple(c[index] + t * v[index] for index in range(3))
    if _distance(p, q) > tolerance:
        return None
    point = tuple(
        0.5 * (p[index] + q[index])
        for index in range(3)
    )
    return point, min(max(s, 0.0), 1.0), min(max(t, 0.0), 1.0)


def _line_nodes_at_point(
    project: ProjectDatabase,
    line: LineGeometryData,
    point: tuple[float, float, float],
    tolerance: float,
) -> set[int]:
    return {
        int(node_tag)
        for node_tag in line.generated_node_tags
        if (
            int(node_tag) in project.model.nodes
            and _distance(project.model.nodes[int(node_tag)].xyz, point)
            <= tolerance
        )
    }


def audit_line_network_connectivity(
    project: ProjectDatabase,
    line_tags=None,
) -> list[LineConnectivityIssue]:
    """Find geometric Line intersections that do not share an FE node."""

    tags = sorted({
        int(tag)
        for tag in (
            project.lines.keys()
            if line_tags is None
            else line_tags
        )
        if int(tag) in project.lines
    })
    if len(tags) < 2:
        return []

    points = [
        project.points[point_tag].xyz
        for tag in tags
        for point_tag in (
            project.lines[tag].point_i,
            project.lines[tag].point_j,
        )
        if point_tag in project.points
    ]
    tolerance = _merge_tolerance(
        project,
        points or [(0.0, 0.0, 0.0)],
    )
    issues: list[LineConnectivityIssue] = []

    for left_index, left_tag in enumerate(tags):
        left = project.lines[left_tag]
        left_state = inspect_line_mesh_state(project, left_tag)
        if not left_state.live_element_tags:
            continue
        a, b, _ = _line_points(project, left)

        for right_tag in tags[left_index + 1:]:
            right = project.lines[right_tag]
            right_state = inspect_line_mesh_state(project, right_tag)
            if not right_state.live_element_tags:
                continue
            c, d, _ = _line_points(project, right)
            intersection = _segment_intersection(
                a, b, c, d, tolerance
            )
            if intersection is None:
                continue
            point, s, t = intersection
            left_nodes = _line_nodes_at_point(
                project, left, point, tolerance
            )
            right_nodes = _line_nodes_at_point(
                project, right, point, tolerance
            )
            if left_nodes & right_nodes:
                continue

            endpoint_tol = 1.0e-8
            left_end = s <= endpoint_tol or s >= 1.0 - endpoint_tol
            right_end = t <= endpoint_tol or t >= 1.0 - endpoint_tol
            if left_end and right_end:
                kind = "endpoint"
            elif left_end or right_end:
                kind = "t_junction"
            else:
                kind = "crossing"
            issues.append(
                LineConnectivityIssue(
                    kind=kind,
                    line_tags=(left_tag, right_tag),
                    point=tuple(float(value) for value in point),
                    parameters=(float(s), float(t)),
                    message=(
                        f"Geometry Lines {left_tag} and {right_tag} intersect "
                        f"but do not share an FE node ({kind})."
                    ),
                )
            )
    return issues

@dataclass(slots=True)
class LineGeometryIntersection:
    line_tags: tuple[int, int]
    point: tuple[float, float, float]
    parameters: tuple[float, float]
    kind: str


@dataclass(slots=True)
class LineSplitResult:
    original_line_tag: int
    line_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    point_tags: list[int] = field(default_factory=list)
    created_point_tags: list[int] = field(default_factory=list)
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


@dataclass(slots=True)
class LineNetworkConformResult:
    input_line_tags: list[int] = field(default_factory=list)
    output_line_tags: list[int] = field(default_factory=list)
    split_line_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    created_point_tags: list[int] = field(default_factory=list)
    intersection_count: int = 0
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


def line_geometry_intersections(
    project: ProjectDatabase,
    line_tags=None,
) -> list[LineGeometryIntersection]:
    """Return non-collinear geometric intersections between Geometry Lines."""

    tags = sorted({
        int(tag)
        for tag in (
            project.lines.keys()
            if line_tags is None
            else line_tags
        )
        if int(tag) in project.lines
    })
    if len(tags) < 2:
        return []

    point_coords = [
        project.points[point_tag].xyz
        for tag in tags
        for point_tag in (
            project.lines[tag].point_i,
            project.lines[tag].point_j,
        )
        if point_tag in project.points
    ]
    tolerance = _merge_tolerance(
        project,
        point_coords or [(0.0, 0.0, 0.0)],
    )
    endpoint_tol = 1.0e-8
    intersections: list[LineGeometryIntersection] = []

    for left_index, left_tag in enumerate(tags):
        left = project.lines[left_tag]
        a, b, _ = _line_points(project, left)
        for right_tag in tags[left_index + 1:]:
            right = project.lines[right_tag]
            c, d, _ = _line_points(project, right)
            intersection = _segment_intersection(
                a,
                b,
                c,
                d,
                tolerance,
            )
            if intersection is None:
                continue
            point, s, t = intersection
            left_end = s <= endpoint_tol or s >= 1.0 - endpoint_tol
            right_end = t <= endpoint_tol or t >= 1.0 - endpoint_tol
            if left_end and right_end:
                kind = "endpoint"
            elif left_end or right_end:
                kind = "t_junction"
            else:
                kind = "crossing"
            intersections.append(
                LineGeometryIntersection(
                    line_tags=(left_tag, right_tag),
                    point=tuple(float(value) for value in point),
                    parameters=(float(s), float(t)),
                    kind=kind,
                )
            )
    return intersections


def _find_geometry_point_at(
    project: ProjectDatabase,
    xyz: tuple[float, float, float],
    tolerance: float,
) -> int | None:
    best: tuple[float, int] | None = None
    tol2 = tolerance * tolerance
    for tag, point in project.points.items():
        distance2 = sum(
            (float(point.xyz[index]) - float(xyz[index])) ** 2
            for index in range(3)
        )
        if distance2 <= tol2 and (
            best is None or distance2 < best[0]
        ):
            best = (distance2, int(tag))
    return None if best is None else best[1]


def _allocate_split_divisions(
    total_divisions: int,
    fractions: list[float],
) -> list[int]:
    count = len(fractions)
    if count <= 0:
        return []
    total = max(int(total_divisions), count)
    allocation = [1] * count
    remaining = total - count
    if remaining <= 0:
        return allocation

    weight_sum = sum(max(float(value), 0.0) for value in fractions)
    if weight_sum <= 1.0e-15:
        for index in range(remaining):
            allocation[index % count] += 1
        return allocation

    raw = [
        remaining * max(float(value), 0.0) / weight_sum
        for value in fractions
    ]
    base = [int(math.floor(value)) for value in raw]
    allocation = [
        allocation[index] + base[index]
        for index in range(count)
    ]
    leftovers = remaining - sum(base)
    order = sorted(
        range(count),
        key=lambda index: (
            -(raw[index] - base[index]),
            -fractions[index],
            index,
        ),
    )
    for index in order[:leftovers]:
        allocation[index] += 1
    return allocation


def _split_unmeshed_line(
    project: ProjectDatabase,
    line_tag: int,
    split_points: list[tuple[float, int]],
) -> LineSplitResult:
    """Split one unmeshed Line at normalized parameters using existing Points."""

    tag = int(line_tag)
    source = project.lines.get(tag)
    if source is None:
        raise ValueError(f"Line geometry {tag} does not exist.")
    if inspect_line_mesh_state(project, tag).live_element_tags:
        raise ValueError(
            f"Line geometry {tag} must be unmeshed before topology splitting."
        )

    endpoint_tol = 1.0e-8
    normalized: list[tuple[float, int]] = []
    for parameter, point_tag in sorted(
        (
            (float(parameter), int(point_tag))
            for parameter, point_tag in split_points
        ),
        key=lambda item: item[0],
    ):
        if parameter <= endpoint_tol or parameter >= 1.0 - endpoint_tol:
            continue
        if point_tag not in project.points:
            raise ValueError(
                f"Split point Geometry Point {point_tag} does not exist."
            )
        if normalized and abs(parameter - normalized[-1][0]) <= endpoint_tol:
            continue
        normalized.append((parameter, point_tag))

    if not normalized:
        return LineSplitResult(
            original_line_tag=tag,
            line_tags=[tag],
        )

    boundaries = [
        (0.0, int(source.point_i)),
        *normalized,
        (1.0, int(source.point_j)),
    ]
    fractions = [
        boundaries[index + 1][0] - boundaries[index][0]
        for index in range(len(boundaries) - 1)
    ]
    if any(value <= endpoint_tol for value in fractions):
        raise ValueError(
            f"Line geometry {tag} split would create a zero-length segment."
        )

    if source.mesh_mode == "divisions":
        divisions = _allocate_split_divisions(
            source.divisions,
            fractions,
        )
    else:
        divisions = [source.divisions] * len(fractions)

    source_data = source.to_dict()
    child_tags: list[int] = []
    created_line_tags: list[int] = []
    for index, fraction in enumerate(fractions):
        child_tag = tag if index == 0 else project.next_line_tag()
        data = dict(source_data)
        data["tag"] = child_tag
        data["name"] = (
            source.name
            if index == 0
            else f"{source.name} [{index + 1}/{len(fractions)}]"
        )
        data["point_i"] = boundaries[index][1]
        data["point_j"] = boundaries[index + 1][1]
        data["divisions"] = divisions[index]
        data["bias"] = float(source.bias) ** float(fraction)
        data["generated_node_tags"] = []
        data["owned_node_tags"] = []
        data["generated_element_tags"] = []
        child = LineGeometryData.from_dict(data)
        if index == 0:
            project.update_line(tag, child)
        else:
            project.add_line(child)
            created_line_tags.append(child_tag)
        child_tags.append(child_tag)

    return LineSplitResult(
        original_line_tag=tag,
        line_tags=child_tags,
        created_line_tags=created_line_tags,
        point_tags=[point_tag for _, point_tag in normalized],
    )


def split_line_geometry_at_point(
    project: ProjectDatabase,
    line_tag: int,
    xyz,
    *,
    remesh: bool = True,
) -> LineSplitResult:
    """Split a Line at one interior point projected onto its straight segment."""

    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")
    point = tuple(float(value) for value in xyz)
    if len(point) != 3 or any(not math.isfinite(value) for value in point):
        raise ValueError("Line split point requires three finite coordinates.")

    a, b, length = _line_points(project, line)
    direction = tuple(b[index] - a[index] for index in range(3))
    length2 = length * length
    parameter = sum(
        (point[index] - a[index]) * direction[index]
        for index in range(3)
    ) / length2
    projected = tuple(
        a[index] + parameter * direction[index]
        for index in range(3)
    )
    tolerance = _merge_tolerance(project, (a, b, point))
    if _distance(projected, point) > tolerance:
        raise ValueError("Line split point is not on the Geometry Line.")
    if not 1.0e-8 < parameter < 1.0 - 1.0e-8:
        raise ValueError("Line split point must lie inside the Line, not at an end.")

    before = project.to_dict()
    state = inspect_line_mesh_state(project, tag)
    had_mesh = bool(state.live_element_tags)
    created_point_tags: list[int] = []
    try:
        if had_mesh:
            delete_line_mesh(project, tag)
        point_tag = _find_geometry_point_at(
            project,
            projected,
            tolerance,
        )
        if point_tag is None:
            point_tag = project.next_point_tag()
            project.add_point(
                PointGeometryData(
                    point_tag,
                    f"Line intersection {point_tag}",
                    projected,
                )
            )
            created_point_tags.append(point_tag)

        result = _split_unmeshed_line(
            project,
            tag,
            [(parameter, point_tag)],
        )
        result.created_point_tags = created_point_tags
        if had_mesh and remesh:
            for child_tag in result.line_tags:
                result.mesh_results[child_tag] = mesh_line_geometry(
                    project,
                    child_tag,
                )
        return result
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def conform_line_network(
    project: ProjectDatabase,
    line_tags=None,
    *,
    mesh: bool = True,
) -> LineNetworkConformResult:
    """Unify endpoint topology, split crossings/T-junctions, and create a conforming FE network."""

    tags = sorted({
        int(tag)
        for tag in (
            project.lines.keys()
            if line_tags is None
            else line_tags
        )
    })
    missing = [tag for tag in tags if tag not in project.lines]
    if missing:
        raise ValueError(
            "Geometry Line tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )
    if not tags:
        return LineNetworkConformResult()

    intersections = line_geometry_intersections(project, tags)
    endpoint_tol = 1.0e-8

    states = {
        tag: inspect_line_mesh_state(project, tag)
        for tag in tags
    }
    stale = [
        tag for tag, state in states.items()
        if not state.healthy
    ]
    if stale:
        raise ValueError(
            "Cannot conform stale Line mesh ownership: "
            + ", ".join(map(str, stale))
        )

    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    before = project.to_dict()
    created_point_tags: list[int] = []
    created_line_tags: list[int] = []
    split_line_tags: list[int] = []
    output_line_tags: list[int] = []
    mesh_results: dict[int, LineMeshResult] = {}

    try:
        for tag in tags:
            if states[tag].live_element_tags:
                delete_line_mesh(project, tag)

        for node_tag in sorted(candidate_owned_nodes):
            if node_tag not in project.model.nodes:
                continue
            if any(
                node_tag in element.node_tags()
                for element in project.model.elements.values()
            ):
                continue
            project.model.nodes.pop(node_tag, None)

        point_coords = [
            project.points[point_tag].xyz
            for tag in tags
            for point_tag in (
                project.lines[tag].point_i,
                project.lines[tag].point_j,
            )
            if point_tag in project.points
        ]
        tolerance = _merge_tolerance(
            project,
            point_coords or [(0.0, 0.0, 0.0)],
        )

        split_definitions: dict[int, list[tuple[float, int]]] = {
            tag: [] for tag in tags
        }
        canonical_points: list[tuple[tuple[float, float, float], int]] = []

        for intersection in intersections:
            left_tag, right_tag = intersection.line_tags
            left_parameter, right_parameter = intersection.parameters
            endpoint_point_tags: list[int] = []

            for line_tag, parameter in (
                (left_tag, left_parameter),
                (right_tag, right_parameter),
            ):
                line = project.lines[line_tag]
                if parameter <= endpoint_tol:
                    endpoint_point_tags.append(int(line.point_i))
                elif parameter >= 1.0 - endpoint_tol:
                    endpoint_point_tags.append(int(line.point_j))

            point_tag = None
            for existing_xyz, existing_tag in canonical_points:
                if _distance(existing_xyz, intersection.point) <= tolerance:
                    point_tag = existing_tag
                    break
            if point_tag is None and endpoint_point_tags:
                point_tag = min(endpoint_point_tags)
            if point_tag is None:
                point_tag = _find_geometry_point_at(
                    project,
                    intersection.point,
                    tolerance,
                )
            if point_tag is None:
                point_tag = project.next_point_tag()
                project.add_point(
                    PointGeometryData(
                        point_tag,
                        f"Line intersection {point_tag}",
                        intersection.point,
                    )
                )
                created_point_tags.append(point_tag)
            canonical_points.append((intersection.point, point_tag))

            for line_tag, parameter in (
                (left_tag, left_parameter),
                (right_tag, right_parameter),
            ):
                line = project.lines[line_tag]
                if endpoint_tol < parameter < 1.0 - endpoint_tol:
                    split_definitions[line_tag].append(
                        (parameter, point_tag)
                    )
                    continue
                if parameter <= endpoint_tol:
                    line.point_i = point_tag
                elif parameter >= 1.0 - endpoint_tol:
                    line.point_j = point_tag
                project._validate_line_geometry(line)

        for tag in tags:
            if split_definitions[tag]:
                split = _split_unmeshed_line(
                    project,
                    tag,
                    split_definitions[tag],
                )
                split_line_tags.append(tag)
                created_line_tags.extend(split.created_line_tags)
                output_line_tags.extend(split.line_tags)
            else:
                output_line_tags.append(tag)

        output_line_tags = sorted(set(output_line_tags))
        if mesh:
            for tag in output_line_tags:
                mesh_results[tag] = mesh_line_geometry(project, tag)

        return LineNetworkConformResult(
            input_line_tags=tags,
            output_line_tags=output_line_tags,
            split_line_tags=sorted(split_line_tags),
            created_line_tags=sorted(set(created_line_tags)),
            created_point_tags=sorted(set(created_point_tags)),
            intersection_count=len(intersections),
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise

@dataclass(slots=True)
class LineTrimExtendResult:
    line_tag: int
    target_line_tag: int
    operation: str
    endpoint: str
    intersection_point_tag: int
    intersection: tuple[float, float, float]
    created_point_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    affected_line_tags: list[int] = field(default_factory=list)
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


@dataclass(slots=True)
class LineMergeResult:
    keeper_line_tag: int
    removed_line_tags: list[int] = field(default_factory=list)
    source_line_tags: list[int] = field(default_factory=list)
    internal_point_tags: list[int] = field(default_factory=list)
    mesh_result: LineMeshResult | None = None


@dataclass(slots=True)
class LineCopyResult:
    source_line_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    created_point_tags: list[int] = field(default_factory=list)
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


@dataclass(slots=True)
class LinePairSplitResult:
    source_line_tags: tuple[int, int]
    intersection_point_tag: int
    intersection: tuple[float, float, float]
    output_line_tags: dict[int, list[int]] = field(default_factory=dict)
    created_point_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


@dataclass(slots=True)
class LineBatchTrimExtendResult:
    subject_line_tags: list[int]
    target_line_tag: int
    operation: str
    target_line_tags: list[int] = field(default_factory=list)
    intersection_point_tags: dict[int, int] = field(default_factory=dict)
    created_point_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


@dataclass(slots=True)
class LineCornerEditResult:
    operation: str
    source_line_tags: tuple[int, int]
    connector_line_tags: list[int] = field(default_factory=list)
    created_point_tags: list[int] = field(default_factory=list)
    created_line_tags: list[int] = field(default_factory=list)
    mesh_results: dict[int, LineMeshResult] = field(default_factory=dict)


def _infinite_line_intersection(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    d: tuple[float, float, float],
    tolerance: float,
) -> tuple[tuple[float, float, float], float, float] | None:
    """Return intersection parameters of two non-parallel infinite 3D lines."""

    u = tuple(b[index] - a[index] for index in range(3))
    v = tuple(d[index] - c[index] for index in range(3))
    w = tuple(a[index] - c[index] for index in range(3))
    uu = sum(value * value for value in u)
    uv = sum(u[index] * v[index] for index in range(3))
    vv = sum(value * value for value in v)
    uw = sum(u[index] * w[index] for index in range(3))
    vw = sum(v[index] * w[index] for index in range(3))
    denominator = uu * vv - uv * uv
    if uu <= 1.0e-24 or vv <= 1.0e-24:
        return None
    if abs(denominator) <= 1.0e-12 * uu * vv:
        return None

    s = (uv * vw - vv * uw) / denominator
    t = (uu * vw - uv * uw) / denominator
    p = tuple(a[index] + s * u[index] for index in range(3))
    q = tuple(c[index] + t * v[index] for index in range(3))
    if _distance(p, q) > tolerance:
        return None
    point = tuple(
        0.5 * (p[index] + q[index])
        for index in range(3)
    )
    return point, float(s), float(t)


def _remove_orphan_fe_nodes(
    project: ProjectDatabase,
    candidate_tags,
) -> None:
    for node_tag in sorted({int(tag) for tag in candidate_tags}):
        if node_tag not in project.model.nodes:
            continue
        if any(
            node_tag in element.node_tags()
            for element in project.model.elements.values()
        ):
            continue
        project.model.nodes.pop(node_tag, None)


def trim_extend_line_to_line(
    project: ProjectDatabase,
    line_tag: int,
    target_line_tag: int,
    *,
    endpoint: str = "nearest",
    operation: str = "auto",
    remesh: bool = True,
) -> LineTrimExtendResult:
    """Trim or extend one Geometry Line to a finite target Line.

    operation may be "trim", "extend", or "auto". Explicit modes are strict
    so a CAD command never performs the opposite edit silently. "auto"
    preserves the previous API behavior for programmatic/context-menu use.

    The subject endpoint is reassigned to shared Geometry topology. If the
    intersection lies inside the target Line, the target is split so the
    resulting FE network can share the same node.
    """

    subject_tag = int(line_tag)
    target_tag = int(target_line_tag)
    if subject_tag == target_tag:
        raise ValueError("Trim/extend requires two different Geometry Lines.")
    subject = project.lines.get(subject_tag)
    target = project.lines.get(target_tag)
    if subject is None or target is None:
        raise ValueError("Trim/extend references a missing Geometry Line.")

    a, b, subject_length = _line_points(project, subject)
    c, d, _target_length = _line_points(project, target)
    tolerance = _merge_tolerance(project, (a, b, c, d))
    hit = _infinite_line_intersection(a, b, c, d, tolerance)
    if hit is None:
        raise ValueError(
            "The selected Lines are parallel, collinear, or skew and do not "
            "define a unique trim/extend intersection."
        )
    point, subject_parameter, target_parameter = hit
    parameter_tol = max(
        1.0e-8,
        tolerance / max(subject_length, 1.0e-12),
    )
    if not -parameter_tol <= target_parameter <= 1.0 + parameter_tol:
        raise ValueError(
            "The subject Line meets only the infinite extension of the target. "
            "Extend the target first or choose another target Line."
        )

    endpoint_key = str(endpoint).strip().lower()
    if endpoint_key not in {"nearest", "i", "j"}:
        raise ValueError("Trim/extend endpoint must be 'nearest', 'i', or 'j'.")

    requested_operation = str(operation).strip().lower()
    if requested_operation not in {"auto", "trim", "extend"}:
        raise ValueError(
            "Trim/extend operation must be 'auto', 'trim', or 'extend'."
        )

    if endpoint_key == "nearest":
        endpoint_key = (
            "i"
            if _distance(a, point) <= _distance(b, point)
            else "j"
        )

    if endpoint_key == "i":
        if _distance(a, point) <= tolerance:
            raise ValueError(
                "Point I already lies on the target Line; no trim/extend "
                "operation is required."
            )
        if _distance(b, point) <= tolerance:
            raise ValueError("Trim/extend would collapse the subject Line.")
        if subject_parameter > 1.0 + parameter_tol:
            raise ValueError(
                "The intersection lies beyond Point J. Modify Point J or "
                "select the Point J side."
            )
        resolved_operation = (
            "extend"
            if subject_parameter < 0.0
            else "trim"
        )
    else:
        if _distance(b, point) <= tolerance:
            raise ValueError(
                "Point J already lies on the target Line; no trim/extend "
                "operation is required."
            )
        if _distance(a, point) <= tolerance:
            raise ValueError("Trim/extend would collapse the subject Line.")
        if subject_parameter < -parameter_tol:
            raise ValueError(
                "The intersection lies beyond Point I. Modify Point I or "
                "select the Point I side."
            )
        resolved_operation = (
            "extend"
            if subject_parameter > 1.0
            else "trim"
        )

    if (
        requested_operation != "auto"
        and resolved_operation != requested_operation
    ):
        if requested_operation == "trim":
            raise ValueError(
                "This boundary lies outside the selected Line endpoint, so "
                "the edit would EXTEND the Line. Use Extend instead."
            )
        raise ValueError(
            "This boundary lies inside the selected Line, so the edit would "
            "TRIM the Line. Use Trim instead."
        )
    operation = resolved_operation

    subject_state = inspect_line_mesh_state(project, subject_tag)
    target_state = inspect_line_mesh_state(project, target_tag)
    if not subject_state.healthy or not target_state.healthy:
        raise ValueError(
            "Trim/extend requires healthy Line mesh ownership. Run the Line "
            "mesh integrity audit first."
        )
    subject_had_mesh = bool(subject_state.live_element_tags)
    target_had_mesh = bool(target_state.live_element_tags)
    before = project.to_dict()
    created_point_tags: list[int] = []
    created_line_tags: list[int] = []
    mesh_results: dict[int, LineMeshResult] = {}
    candidate_owned_nodes = {
        *subject_state.owned_node_tags,
        *target_state.owned_node_tags,
    }

    try:
        if subject_had_mesh:
            delete_line_mesh(project, subject_tag)

        endpoint_tol = 1.0e-8
        target_split = endpoint_tol < target_parameter < 1.0 - endpoint_tol
        if target_split and target_had_mesh:
            delete_line_mesh(project, target_tag)

        if target_parameter <= endpoint_tol:
            point_tag = int(project.lines[target_tag].point_i)
        elif target_parameter >= 1.0 - endpoint_tol:
            point_tag = int(project.lines[target_tag].point_j)
        else:
            point_tag = _find_geometry_point_at(
                project,
                point,
                tolerance,
            )
            if point_tag is None:
                point_tag = project.next_point_tag()
                project.add_point(
                    PointGeometryData(
                        point_tag,
                        f"Line trim intersection {point_tag}",
                        point,
                    )
                )
                created_point_tags.append(point_tag)

        subject = project.lines[subject_tag]
        if endpoint_key == "i":
            subject.point_i = point_tag
        else:
            subject.point_j = point_tag
        project._validate_line_geometry(subject)

        target_children = [target_tag]
        if target_split:
            split = _split_unmeshed_line(
                project,
                target_tag,
                [(target_parameter, point_tag)],
            )
            target_children = list(split.line_tags)
            created_line_tags.extend(split.created_line_tags)

        _remove_orphan_fe_nodes(project, candidate_owned_nodes)

        if remesh and subject_had_mesh:
            mesh_results[subject_tag] = mesh_line_geometry(
                project,
                subject_tag,
            )
        if remesh and target_had_mesh:
            for child_tag in target_children:
                mesh_results[child_tag] = mesh_line_geometry(
                    project,
                    child_tag,
                )

        affected = sorted({
            subject_tag,
            *target_children,
        })
        return LineTrimExtendResult(
            line_tag=subject_tag,
            target_line_tag=target_tag,
            operation=operation,
            endpoint=endpoint_key,
            intersection_point_tag=point_tag,
            intersection=point,
            created_point_tags=created_point_tags,
            created_line_tags=sorted(set(created_line_tags)),
            affected_line_tags=affected,
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def _line_shared_corner(
    project: ProjectDatabase,
    left_tag: int,
    right_tag: int,
) -> tuple[
    LineGeometryData,
    LineGeometryData,
    int,
    int,
    int,
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    left = project.lines.get(int(left_tag))
    right = project.lines.get(int(right_tag))
    if left is None or right is None:
        raise ValueError("Corner edit references a missing Geometry Line.")
    if int(left_tag) == int(right_tag):
        raise ValueError("Corner edit requires two different Geometry Lines.")

    shared = (
        {int(left.point_i), int(left.point_j)}
        & {int(right.point_i), int(right.point_j)}
    )
    if len(shared) != 1:
        raise ValueError(
            "Fillet/Chamfer requires two Geometry Lines sharing exactly "
            "one Geometry Point."
        )
    corner_tag = next(iter(shared))
    left_other = (
        int(left.point_j)
        if int(left.point_i) == corner_tag
        else int(left.point_i)
    )
    right_other = (
        int(right.point_j)
        if int(right.point_i) == corner_tag
        else int(right.point_i)
    )
    corner = project.points[corner_tag].xyz
    left_xyz = project.points[left_other].xyz
    right_xyz = project.points[right_other].xyz
    return (
        left,
        right,
        corner_tag,
        left_other,
        right_other,
        corner,
        left_xyz,
        right_xyz,
    )


def _unit_direction(
    origin: tuple[float, float, float],
    target: tuple[float, float, float],
) -> tuple[tuple[float, float, float], float]:
    vector = tuple(
        float(target[index]) - float(origin[index])
        for index in range(3)
    )
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1.0e-12:
        raise ValueError("Corner edit cannot use a zero-length Geometry Line.")
    return tuple(value / length for value in vector), length


def _corner_recipe_is_compatible(
    left: LineGeometryData,
    right: LineGeometryData,
) -> bool:
    if bool(left.mesh_recipe_configured) != bool(
        right.mesh_recipe_configured
    ):
        return False
    if not left.mesh_recipe_configured:
        return True
    return _line_recipe_merge_signature(left) == _line_recipe_merge_signature(
        right
    )


def _new_line_from_recipe(
    project: ProjectDatabase,
    source: LineGeometryData,
    point_i: int,
    point_j: int,
    name: str,
) -> LineGeometryData:
    data = source.to_dict()
    data.update({
        "tag": project.next_line_tag(),
        "name": str(name),
        "point_i": int(point_i),
        "point_j": int(point_j),
        "divisions": 1,
        "bias": 1.0,
        "generated_node_tags": [],
        "owned_node_tags": [],
        "generated_element_tags": [],
    })
    return LineGeometryData.from_dict(data)


def _set_line_corner_endpoint(
    project: ProjectDatabase,
    line: LineGeometryData,
    corner_tag: int,
    replacement_tag: int,
) -> None:
    if int(line.point_i) == int(corner_tag):
        line.point_i = int(replacement_tag)
    elif int(line.point_j) == int(corner_tag):
        line.point_j = int(replacement_tag)
    else:
        raise ValueError(
            f"Geometry Line {line.tag} no longer contains corner "
            f"Point {corner_tag}."
        )
    project._validate_line_geometry(line)


def split_line_pair_at_intersection(
    project: ProjectDatabase,
    left_line_tag: int,
    right_line_tag: int,
    *,
    remesh: bool = True,
) -> LinePairSplitResult:
    """Split two finite Geometry Lines at their common geometric intersection."""

    left_tag = int(left_line_tag)
    right_tag = int(right_line_tag)
    if left_tag == right_tag:
        raise ValueError("Split by Line requires two different Geometry Lines.")
    left = project.lines.get(left_tag)
    right = project.lines.get(right_tag)
    if left is None or right is None:
        raise ValueError("Split by Line references a missing Geometry Line.")

    a, b, _ = _line_points(project, left)
    c, d, _ = _line_points(project, right)
    tolerance = _merge_tolerance(project, (a, b, c, d))
    hit = _segment_intersection(a, b, c, d, tolerance)
    if hit is None:
        raise ValueError(
            "The selected Geometry Lines do not intersect as finite segments."
        )
    point, left_parameter, right_parameter = hit
    endpoint_tol = 1.0e-8
    if (
        (left_parameter <= endpoint_tol or left_parameter >= 1.0 - endpoint_tol)
        and (
            right_parameter <= endpoint_tol
            or right_parameter >= 1.0 - endpoint_tol
        )
    ):
        raise ValueError(
            "The selected Lines already meet endpoint-to-endpoint; there is "
            "nothing to split."
        )

    states = {
        left_tag: inspect_line_mesh_state(project, left_tag),
        right_tag: inspect_line_mesh_state(project, right_tag),
    }
    if any(not state.healthy for state in states.values()):
        raise ValueError(
            "Split by Line requires healthy Line mesh ownership. Run the "
            "Line mesh integrity audit first."
        )
    had_mesh = {
        tag: bool(state.live_element_tags)
        for tag, state in states.items()
    }
    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    before = project.to_dict()
    created_point_tags: list[int] = []
    created_line_tags: list[int] = []
    output_line_tags: dict[int, list[int]] = {}
    mesh_results: dict[int, LineMeshResult] = {}

    try:
        for tag, state in states.items():
            if state.live_element_tags:
                delete_line_mesh(project, tag)

        endpoint_candidates: list[int] = []
        for line, parameter in (
            (project.lines[left_tag], left_parameter),
            (project.lines[right_tag], right_parameter),
        ):
            if parameter <= endpoint_tol:
                endpoint_candidates.append(int(line.point_i))
            elif parameter >= 1.0 - endpoint_tol:
                endpoint_candidates.append(int(line.point_j))

        point_tag = (
            min(endpoint_candidates)
            if endpoint_candidates
            else _find_geometry_point_at(project, point, tolerance)
        )
        if point_tag is None:
            point_tag = project.next_point_tag()
            project.add_point(
                PointGeometryData(
                    point_tag,
                    f"Line split intersection {point_tag}",
                    point,
                )
            )
            created_point_tags.append(point_tag)

        for tag, parameter in (
            (left_tag, left_parameter),
            (right_tag, right_parameter),
        ):
            line = project.lines[tag]
            if endpoint_tol < parameter < 1.0 - endpoint_tol:
                split = _split_unmeshed_line(
                    project,
                    tag,
                    [(parameter, point_tag)],
                )
                output_line_tags[tag] = list(split.line_tags)
                created_line_tags.extend(split.created_line_tags)
            else:
                if parameter <= endpoint_tol:
                    line.point_i = point_tag
                else:
                    line.point_j = point_tag
                project._validate_line_geometry(line)
                output_line_tags[tag] = [tag]

        _remove_orphan_fe_nodes(project, candidate_owned_nodes)

        if remesh:
            for source_tag in (left_tag, right_tag):
                if not had_mesh[source_tag]:
                    continue
                for child_tag in output_line_tags[source_tag]:
                    mesh_results[child_tag] = mesh_line_geometry(
                        project,
                        child_tag,
                    )

        return LinePairSplitResult(
            source_line_tags=(left_tag, right_tag),
            intersection_point_tag=point_tag,
            intersection=tuple(float(value) for value in point),
            output_line_tags=output_line_tags,
            created_point_tags=created_point_tags,
            created_line_tags=sorted(set(created_line_tags)),
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def trim_extend_lines_to_line(
    project: ProjectDatabase,
    line_tags,
    target_line_tag: int,
    *,
    operation: str,
    remesh: bool = True,
) -> LineBatchTrimExtendResult:
    """Trim or extend multiple subject Lines to one finite target Line."""

    subject_tags = sorted({int(tag) for tag in line_tags})
    target_tag = int(target_line_tag)
    requested_operation = str(operation).strip().lower()
    if requested_operation not in {"trim", "extend"}:
        raise ValueError("Batch Line edit operation must be trim or extend.")
    if not subject_tags:
        raise ValueError("Select at least one subject Geometry Line.")
    if target_tag in subject_tags:
        raise ValueError("The target boundary cannot also be a subject Line.")

    target = project.lines.get(target_tag)
    if target is None:
        raise ValueError(f"Target Geometry Line {target_tag} does not exist.")
    missing = [tag for tag in subject_tags if tag not in project.lines]
    if missing:
        raise ValueError(
            "Geometry Line tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )

    c, d, _ = _line_points(project, target)
    plans: dict[
        int,
        tuple[
            str,
            tuple[float, float, float],
            float,
        ],
    ] = {}
    all_coords = [c, d]
    for subject_tag in subject_tags:
        subject = project.lines[subject_tag]
        a, b, subject_length = _line_points(project, subject)
        all_coords.extend((a, b))
        tolerance = _merge_tolerance(project, (a, b, c, d))
        hit = _infinite_line_intersection(a, b, c, d, tolerance)
        if hit is None:
            raise ValueError(
                f"Line {subject_tag} is parallel, collinear, or skew to "
                f"target Line {target_tag}."
            )
        point, subject_parameter, target_parameter = hit
        parameter_tol = max(
            1.0e-8,
            tolerance / max(subject_length, 1.0e-12),
        )
        if not -parameter_tol <= target_parameter <= 1.0 + parameter_tol:
            raise ValueError(
                f"Line {subject_tag} meets only the infinite extension of "
                f"target Line {target_tag}."
            )

        endpoint = (
            "i"
            if _distance(a, point) <= _distance(b, point)
            else "j"
        )
        if endpoint == "i":
            if _distance(a, point) <= tolerance:
                raise ValueError(
                    f"Line {subject_tag} Point I already lies on the target."
                )
            if _distance(b, point) <= tolerance:
                raise ValueError(
                    f"Editing Line {subject_tag} would collapse the Line."
                )
            resolved = (
                "extend"
                if subject_parameter < 0.0
                else "trim"
            )
        else:
            if _distance(b, point) <= tolerance:
                raise ValueError(
                    f"Line {subject_tag} Point J already lies on the target."
                )
            if _distance(a, point) <= tolerance:
                raise ValueError(
                    f"Editing Line {subject_tag} would collapse the Line."
                )
            resolved = (
                "extend"
                if subject_parameter > 1.0
                else "trim"
            )

        if resolved != requested_operation:
            raise ValueError(
                f"Line {subject_tag} would {resolved.upper()}, not "
                f"{requested_operation.upper()}. Use the matching batch tool."
            )
        plans[subject_tag] = (
            endpoint,
            tuple(float(value) for value in point),
            float(target_parameter),
        )

    involved_tags = [*subject_tags, target_tag]
    states = {
        tag: inspect_line_mesh_state(project, tag)
        for tag in involved_tags
    }
    if any(not state.healthy for state in states.values()):
        raise ValueError(
            "Batch Trim/Extend requires healthy Line mesh ownership. Run the "
            "Line mesh integrity audit first."
        )
    had_mesh = {
        tag: bool(state.live_element_tags)
        for tag, state in states.items()
    }
    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    tolerance = _merge_tolerance(project, all_coords)
    endpoint_tol = 1.0e-8
    before = project.to_dict()
    created_point_tags: list[int] = []
    intersection_point_tags: dict[int, int] = {}
    mesh_results: dict[int, LineMeshResult] = {}

    try:
        for tag, state in states.items():
            if state.live_element_tags:
                delete_line_mesh(project, tag)

        target = project.lines[target_tag]
        split_definitions: list[tuple[float, int]] = []
        for subject_tag in subject_tags:
            endpoint, point, target_parameter = plans[subject_tag]
            if target_parameter <= endpoint_tol:
                point_tag = int(target.point_i)
            elif target_parameter >= 1.0 - endpoint_tol:
                point_tag = int(target.point_j)
            else:
                point_tag = _find_geometry_point_at(
                    project,
                    point,
                    tolerance,
                )
                if point_tag is None:
                    point_tag = project.next_point_tag()
                    project.add_point(
                        PointGeometryData(
                            point_tag,
                            f"Batch {requested_operation} intersection "
                            f"{point_tag}",
                            point,
                        )
                    )
                    created_point_tags.append(point_tag)
                split_definitions.append(
                    (target_parameter, point_tag)
                )

            subject = project.lines[subject_tag]
            if endpoint == "i":
                subject.point_i = point_tag
            else:
                subject.point_j = point_tag
            project._validate_line_geometry(subject)
            intersection_point_tags[subject_tag] = point_tag

        target_split = _split_unmeshed_line(
            project,
            target_tag,
            split_definitions,
        )
        target_children = list(target_split.line_tags)
        created_line_tags = list(target_split.created_line_tags)

        _remove_orphan_fe_nodes(project, candidate_owned_nodes)

        if remesh:
            for subject_tag in subject_tags:
                if had_mesh[subject_tag]:
                    mesh_results[subject_tag] = mesh_line_geometry(
                        project,
                        subject_tag,
                    )
            if had_mesh[target_tag]:
                for child_tag in target_children:
                    mesh_results[child_tag] = mesh_line_geometry(
                        project,
                        child_tag,
                    )

        return LineBatchTrimExtendResult(
            subject_line_tags=subject_tags,
            target_line_tag=target_tag,
            operation=requested_operation,
            target_line_tags=target_children,
            intersection_point_tags=intersection_point_tags,
            created_point_tags=created_point_tags,
            created_line_tags=created_line_tags,
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def chamfer_lines(
    project: ProjectDatabase,
    left_line_tag: int,
    right_line_tag: int,
    *,
    distance: float,
    remesh: bool = True,
) -> LineCornerEditResult:
    """Replace one shared Line corner by a straight chamfer segment."""

    (
        left,
        right,
        corner_tag,
        _left_other,
        _right_other,
        corner,
        left_xyz,
        right_xyz,
    ) = _line_shared_corner(project, left_line_tag, right_line_tag)
    if not _corner_recipe_is_compatible(left, right):
        raise ValueError(
            "Chamfer requires matching mesh / FE recipes on the two Lines. "
            "Use Copy Mesh / FE Recipe first."
        )

    left_direction, left_length = _unit_direction(corner, left_xyz)
    right_direction, right_length = _unit_direction(corner, right_xyz)
    dot = sum(
        left_direction[index] * right_direction[index]
        for index in range(3)
    )
    if abs(abs(dot) - 1.0) <= 1.0e-10:
        raise ValueError(
            "Chamfer requires two non-collinear Geometry Lines."
        )

    setback = float(distance)
    if not math.isfinite(setback) or setback <= 0.0:
        raise ValueError("Chamfer distance must be finite and positive.")
    tolerance = _merge_tolerance(
        project,
        (corner, left_xyz, right_xyz),
    )
    if setback >= min(left_length, right_length) - tolerance:
        raise ValueError(
            "Chamfer distance must be shorter than both connected Lines."
        )

    states = {
        int(left.tag): inspect_line_mesh_state(project, int(left.tag)),
        int(right.tag): inspect_line_mesh_state(project, int(right.tag)),
    }
    if any(not state.healthy for state in states.values()):
        raise ValueError(
            "Chamfer requires healthy Line mesh ownership."
        )
    mesh_flags = {
        bool(state.live_element_tags)
        for state in states.values()
    }
    if len(mesh_flags) != 1:
        raise ValueError(
            "Chamfer requires both source Lines to be either meshed or "
            "unmeshed before the corner edit."
        )
    had_mesh = next(iter(mesh_flags))
    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    before = project.to_dict()
    created_point_tags: list[int] = []
    mesh_results: dict[int, LineMeshResult] = {}

    try:
        for tag, state in states.items():
            if state.live_element_tags:
                delete_line_mesh(project, tag)

        tangent_tags: list[int] = []
        for label, direction in (
            ("A", left_direction),
            ("B", right_direction),
        ):
            xyz = tuple(
                float(corner[index]) + setback * direction[index]
                for index in range(3)
            )
            point_tag = _find_geometry_point_at(
                project,
                xyz,
                tolerance,
            )
            if point_tag is None:
                point_tag = project.next_point_tag()
                project.add_point(
                    PointGeometryData(
                        point_tag,
                        f"Chamfer tangent {label} {point_tag}",
                        xyz,
                    )
                )
                created_point_tags.append(point_tag)
            tangent_tags.append(point_tag)

        _set_line_corner_endpoint(
            project,
            project.lines[int(left.tag)],
            corner_tag,
            tangent_tags[0],
        )
        _set_line_corner_endpoint(
            project,
            project.lines[int(right.tag)],
            corner_tag,
            tangent_tags[1],
        )

        connector = _new_line_from_recipe(
            project,
            project.lines[int(left.tag)],
            tangent_tags[0],
            tangent_tags[1],
            f"Chamfer {left.tag}-{right.tag}",
        )
        project.add_line(connector)
        _remove_orphan_fe_nodes(project, candidate_owned_nodes)

        if remesh and had_mesh:
            for tag in (int(left.tag), int(right.tag), connector.tag):
                mesh_results[tag] = mesh_line_geometry(project, tag)

        return LineCornerEditResult(
            operation="chamfer",
            source_line_tags=(int(left.tag), int(right.tag)),
            connector_line_tags=[connector.tag],
            created_point_tags=created_point_tags,
            created_line_tags=[connector.tag],
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def fillet_lines(
    project: ProjectDatabase,
    left_line_tag: int,
    right_line_tag: int,
    *,
    radius: float,
    segments: int = 8,
    remesh: bool = True,
) -> LineCornerEditResult:
    """Replace one shared corner by a tangent polyline approximation of a fillet."""

    (
        left,
        right,
        corner_tag,
        _left_other,
        _right_other,
        corner,
        left_xyz,
        right_xyz,
    ) = _line_shared_corner(project, left_line_tag, right_line_tag)
    if not _corner_recipe_is_compatible(left, right):
        raise ValueError(
            "Fillet requires matching mesh / FE recipes on the two Lines. "
            "Use Copy Mesh / FE Recipe first."
        )

    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("Fillet radius must be finite and positive.")
    segment_count = int(segments)
    if not 2 <= segment_count <= 64:
        raise ValueError("Fillet segment count must be in 2..64.")

    u, left_length = _unit_direction(corner, left_xyz)
    v, right_length = _unit_direction(corner, right_xyz)
    dot = max(
        -1.0,
        min(
            1.0,
            sum(u[index] * v[index] for index in range(3)),
        ),
    )
    angle = math.acos(dot)
    if angle <= 1.0e-8 or abs(math.pi - angle) <= 1.0e-8:
        raise ValueError(
            "Fillet requires two non-collinear, non-opposite Geometry Lines."
        )

    tangent_distance = radius / math.tan(0.5 * angle)
    tolerance = _merge_tolerance(
        project,
        (corner, left_xyz, right_xyz),
    )
    if tangent_distance >= min(left_length, right_length) - tolerance:
        raise ValueError(
            "Fillet radius is too large for the connected Line lengths."
        )

    cross_uv = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    normal_length = math.sqrt(sum(value * value for value in cross_uv))
    if normal_length <= 1.0e-12:
        raise ValueError("Fillet plane is undefined for collinear Lines.")
    normal = tuple(value / normal_length for value in cross_uv)

    tangent_a = tuple(
        float(corner[index]) + tangent_distance * u[index]
        for index in range(3)
    )
    tangent_b = tuple(
        float(corner[index]) + tangent_distance * v[index]
        for index in range(3)
    )
    bisector_raw = tuple(u[index] + v[index] for index in range(3))
    bisector_length = math.sqrt(
        sum(value * value for value in bisector_raw)
    )
    if bisector_length <= 1.0e-12:
        raise ValueError("Fillet bisector is undefined.")
    bisector = tuple(
        value / bisector_length
        for value in bisector_raw
    )
    center_distance = radius / math.sin(0.5 * angle)
    center = tuple(
        float(corner[index]) + center_distance * bisector[index]
        for index in range(3)
    )
    r0 = tuple(
        tangent_a[index] - center[index]
        for index in range(3)
    )
    r1 = tuple(
        tangent_b[index] - center[index]
        for index in range(3)
    )
    cross_r = (
        r0[1] * r1[2] - r0[2] * r1[1],
        r0[2] * r1[0] - r0[0] * r1[2],
        r0[0] * r1[1] - r0[1] * r1[0],
    )
    signed_angle = math.atan2(
        sum(normal[index] * cross_r[index] for index in range(3)),
        sum(r0[index] * r1[index] for index in range(3)),
    )
    if abs(signed_angle) <= 1.0e-12:
        raise ValueError("Fillet arc angle is too small.")

    states = {
        int(left.tag): inspect_line_mesh_state(project, int(left.tag)),
        int(right.tag): inspect_line_mesh_state(project, int(right.tag)),
    }
    if any(not state.healthy for state in states.values()):
        raise ValueError("Fillet requires healthy Line mesh ownership.")
    mesh_flags = {
        bool(state.live_element_tags)
        for state in states.values()
    }
    if len(mesh_flags) != 1:
        raise ValueError(
            "Fillet requires both source Lines to be either meshed or "
            "unmeshed before the corner edit."
        )
    had_mesh = next(iter(mesh_flags))
    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    before = project.to_dict()
    created_point_tags: list[int] = []
    created_line_tags: list[int] = []
    mesh_results: dict[int, LineMeshResult] = {}

    try:
        for tag, state in states.items():
            if state.live_element_tags:
                delete_line_mesh(project, tag)

        arc_point_tags: list[int] = []
        for index in range(segment_count + 1):
            fraction = index / segment_count
            phi = signed_angle * fraction
            cos_phi = math.cos(phi)
            sin_phi = math.sin(phi)
            cross_nr0 = (
                normal[1] * r0[2] - normal[2] * r0[1],
                normal[2] * r0[0] - normal[0] * r0[2],
                normal[0] * r0[1] - normal[1] * r0[0],
            )
            dot_nr0 = sum(
                normal[axis] * r0[axis]
                for axis in range(3)
            )
            rotated = tuple(
                r0[axis] * cos_phi
                + cross_nr0[axis] * sin_phi
                + normal[axis] * dot_nr0 * (1.0 - cos_phi)
                for axis in range(3)
            )
            xyz = tuple(
                center[axis] + rotated[axis]
                for axis in range(3)
            )
            point_tag = _find_geometry_point_at(
                project,
                xyz,
                tolerance,
            )
            if point_tag is None:
                point_tag = project.next_point_tag()
                project.add_point(
                    PointGeometryData(
                        point_tag,
                        f"Fillet point {index + 1} {point_tag}",
                        xyz,
                    )
                )
                created_point_tags.append(point_tag)
            arc_point_tags.append(point_tag)

        _set_line_corner_endpoint(
            project,
            project.lines[int(left.tag)],
            corner_tag,
            arc_point_tags[0],
        )
        _set_line_corner_endpoint(
            project,
            project.lines[int(right.tag)],
            corner_tag,
            arc_point_tags[-1],
        )

        for index in range(segment_count):
            connector = _new_line_from_recipe(
                project,
                project.lines[int(left.tag)],
                arc_point_tags[index],
                arc_point_tags[index + 1],
                (
                    f"Fillet {left.tag}-{right.tag} "
                    f"[{index + 1}/{segment_count}]"
                ),
            )
            project.add_line(connector)
            created_line_tags.append(connector.tag)

        _remove_orphan_fe_nodes(project, candidate_owned_nodes)

        if remesh and had_mesh:
            for tag in (
                int(left.tag),
                int(right.tag),
                *created_line_tags,
            ):
                mesh_results[tag] = mesh_line_geometry(project, tag)

        return LineCornerEditResult(
            operation="fillet",
            source_line_tags=(int(left.tag), int(right.tag)),
            connector_line_tags=list(created_line_tags),
            created_point_tags=created_point_tags,
            created_line_tags=created_line_tags,
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def _line_recipe_merge_signature(line: LineGeometryData) -> tuple:
    return (
        line.mesh_mode,
        line.target_size,
        line.reuse_existing_nodes,
        line.element_family,
        line.element_type,
        line.section_tag,
        line.transformation_tag,
        line.material_tag,
        float(line.area),
        line.integration_type,
        line.integration_points,
        float(line.mass_per_length),
        line.consistent_mass,
        line.do_rayleigh,
    )


def merge_collinear_lines(
    project: ProjectDatabase,
    line_tags,
    *,
    remesh: bool = True,
) -> LineMergeResult:
    """Merge a contiguous collinear chain with compatible uniform mesh recipes."""

    tags = sorted({int(tag) for tag in line_tags})
    if len(tags) < 2:
        raise ValueError("Merge requires at least two Geometry Lines.")
    missing = [tag for tag in tags if tag not in project.lines]
    if missing:
        raise ValueError(
            "Geometry Line tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )

    lines = [project.lines[tag] for tag in tags]
    signature = _line_recipe_merge_signature(lines[0])
    if any(_line_recipe_merge_signature(line) != signature for line in lines[1:]):
        raise ValueError(
            "Collinear Lines can be merged only when their FE/mesh recipes "
            "match. Use Copy Mesh / FE Recipe first."
        )
    if any(abs(float(line.bias) - 1.0) > 1.0e-12 for line in lines):
        raise ValueError(
            "Merge currently requires uniform Line meshes (bias = 1). "
            "Use uniform grading before merging."
        )

    adjacency: dict[int, list[tuple[int, int]]] = {}
    for line in lines:
        adjacency.setdefault(int(line.point_i), []).append(
            (int(line.tag), int(line.point_j))
        )
        adjacency.setdefault(int(line.point_j), []).append(
            (int(line.tag), int(line.point_i))
        )
    if any(len(users) > 2 for users in adjacency.values()):
        raise ValueError("Selected Lines form a branch, not one mergeable chain.")
    endpoints = sorted(
        point_tag
        for point_tag, users in adjacency.items()
        if len(users) == 1
    )
    if len(endpoints) != 2:
        raise ValueError(
            "Selected Lines must form one open contiguous chain with two ends."
        )

    first = lines[0]
    start_tag = (
        int(first.point_i)
        if int(first.point_i) in endpoints
        else int(first.point_j)
        if int(first.point_j) in endpoints
        else endpoints[0]
    )
    ordered_line_tags: list[int] = []
    ordered_point_tags: list[int] = [start_tag]
    previous_line: int | None = None
    current_point = start_tag
    while len(ordered_line_tags) < len(tags):
        candidates = [
            (line_tag, other_point)
            for line_tag, other_point in adjacency[current_point]
            if line_tag != previous_line
            and line_tag not in ordered_line_tags
        ]
        if len(candidates) != 1:
            raise ValueError("Selected Lines are not one contiguous chain.")
        next_line, next_point = candidates[0]
        ordered_line_tags.append(next_line)
        ordered_point_tags.append(next_point)
        previous_line = next_line
        current_point = next_point
    if current_point != endpoints[0] and current_point != endpoints[1]:
        raise ValueError("Selected Lines do not terminate at the chain endpoint.")

    start_xyz = project.points[ordered_point_tags[0]].xyz
    end_xyz = project.points[ordered_point_tags[-1]].xyz
    axis = tuple(
        float(end_xyz[index]) - float(start_xyz[index])
        for index in range(3)
    )
    axis_length = math.sqrt(sum(value * value for value in axis))
    if axis_length <= 1.0e-12:
        raise ValueError("Cannot merge a zero-length Line chain.")
    point_coords = [
        project.points[tag].xyz
        for tag in ordered_point_tags
    ]
    tolerance = _merge_tolerance(project, point_coords)
    for point in point_coords[1:-1]:
        relative = tuple(
            float(point[index]) - float(start_xyz[index])
            for index in range(3)
        )
        cross = (
            relative[1] * axis[2] - relative[2] * axis[1],
            relative[2] * axis[0] - relative[0] * axis[2],
            relative[0] * axis[1] - relative[1] * axis[0],
        )
        if math.sqrt(sum(value * value for value in cross)) / axis_length > tolerance:
            raise ValueError("Selected Lines are contiguous but not collinear.")

    states = {
        tag: inspect_line_mesh_state(project, tag)
        for tag in tags
    }
    if any(not state.healthy for state in states.values()):
        raise ValueError(
            "Merge requires healthy Line mesh ownership. Run the Line mesh "
            "integrity audit first."
        )
    had_mesh = any(state.live_element_tags for state in states.values())
    candidate_owned_nodes = {
        int(node_tag)
        for state in states.values()
        for node_tag in state.owned_node_tags
    }
    before = project.to_dict()
    keeper_tag = ordered_line_tags[0]
    removed = [tag for tag in ordered_line_tags if tag != keeper_tag]
    internal_points = ordered_point_tags[1:-1]

    try:
        for tag in ordered_line_tags:
            if states[tag].live_element_tags:
                delete_line_mesh(project, tag)
        _remove_orphan_fe_nodes(project, candidate_owned_nodes)

        keeper = project.lines[keeper_tag]
        keeper.point_i = ordered_point_tags[0]
        keeper.point_j = ordered_point_tags[-1]
        if keeper.mesh_mode == "divisions":
            keeper.divisions = sum(
                int(project.lines[tag].divisions)
                for tag in ordered_line_tags
            )
        keeper.bias = 1.0
        project._validate_line_geometry(keeper)

        for tag in removed:
            project.remove_line(tag)

        mesh_result = (
            mesh_line_geometry(project, keeper_tag)
            if had_mesh and remesh
            else None
        )
        return LineMergeResult(
            keeper_line_tag=keeper_tag,
            removed_line_tags=sorted(removed),
            source_line_tags=ordered_line_tags,
            internal_point_tags=list(internal_points),
            mesh_result=mesh_result,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def divide_line_geometry(
    project: ProjectDatabase,
    line_tag: int,
    *,
    segments: int | None = None,
    distance_from_i: float | None = None,
    remesh: bool = True,
) -> LineSplitResult:
    """Divide one Geometry Line into equal segments or split at a distance."""

    tag = int(line_tag)
    line = project.lines.get(tag)
    if line is None:
        raise ValueError(f"Line geometry {tag} does not exist.")
    if (segments is None) == (distance_from_i is None):
        raise ValueError(
            "Specify either equal segment count or distance from Point I."
        )

    a, b, length = _line_points(project, line)
    if segments is not None:
        count = int(segments)
        if count < 2 or count > 1000:
            raise ValueError("Geometry Line division count must be in 2..1000.")
        parameters = [
            index / count
            for index in range(1, count)
        ]
    else:
        distance = float(distance_from_i)
        if not math.isfinite(distance) or not 0.0 < distance < length:
            raise ValueError(
                "Split distance must be finite and inside the Line length."
            )
        parameters = [distance / length]

    state = inspect_line_mesh_state(project, tag)
    if not state.healthy:
        raise ValueError(
            "Divide requires healthy Line mesh ownership. Run the Line mesh "
            "integrity audit first."
        )
    had_mesh = bool(state.live_element_tags)
    before = project.to_dict()
    created_points: list[int] = []
    try:
        if had_mesh:
            delete_line_mesh(project, tag)

        tolerance = _merge_tolerance(project, (a, b))
        definitions: list[tuple[float, int]] = []
        for parameter in parameters:
            xyz = tuple(
                a[axis] + parameter * (b[axis] - a[axis])
                for axis in range(3)
            )
            point_tag = _find_geometry_point_at(
                project,
                xyz,
                tolerance,
            )
            if point_tag is None:
                point_tag = project.next_point_tag()
                project.add_point(
                    PointGeometryData(
                        point_tag,
                        f"Line division {point_tag}",
                        xyz,
                    )
                )
                created_points.append(point_tag)
            definitions.append((parameter, point_tag))

        result = _split_unmeshed_line(
            project,
            tag,
            definitions,
        )
        result.created_point_tags = created_points
        if had_mesh and remesh:
            for child_tag in result.line_tags:
                result.mesh_results[child_tag] = mesh_line_geometry(
                    project,
                    child_tag,
                )
        return result
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise


def copy_offset_line_geometry(
    project: ProjectDatabase,
    line_tags,
    *,
    dx: float,
    dy: float,
    dz: float,
    copies: int = 1,
    mesh: bool = True,
) -> LineCopyResult:
    """Copy/offset a Geometry Line network while retaining shared topology."""

    tags = sorted({int(tag) for tag in line_tags})
    if not tags:
        raise ValueError("Copy/offset requires at least one Geometry Line.")
    missing = [tag for tag in tags if tag not in project.lines]
    if missing:
        raise ValueError(
            "Geometry Line tag(s) do not exist: "
            + ", ".join(map(str, missing))
        )
    offset = (float(dx), float(dy), float(dz))
    if any(not math.isfinite(value) for value in offset):
        raise ValueError("Line copy offset values must be finite.")
    count = int(copies)
    if count < 1 or count > 1000:
        raise ValueError("Line copy count must be in 1..1000.")
    if sum(abs(value) for value in offset) <= 1.0e-15:
        raise ValueError("Line copy/offset requires a non-zero vector.")

    before = project.to_dict()
    created_points: list[int] = []
    created_lines: list[int] = []
    mesh_results: dict[int, LineMeshResult] = {}
    point_map: dict[tuple[int, int], int] = {}
    try:
        for copy_index in range(1, count + 1):
            shift = tuple(
                copy_index * offset[axis]
                for axis in range(3)
            )
            for source_tag in tags:
                source = project.lines[source_tag]
                new_endpoints: list[int] = []
                for source_point_tag in (source.point_i, source.point_j):
                    key = (copy_index, int(source_point_tag))
                    new_point_tag = point_map.get(key)
                    if new_point_tag is None:
                        source_point = project.points[int(source_point_tag)]
                        xyz = tuple(
                            float(source_point.xyz[axis]) + shift[axis]
                            for axis in range(3)
                        )
                        new_point_tag = project.next_point_tag()
                        project.add_point(
                            PointGeometryData(
                                new_point_tag,
                                f"{source_point.name} copy {copy_index}",
                                xyz,
                            )
                        )
                        point_map[key] = new_point_tag
                        created_points.append(new_point_tag)
                    new_endpoints.append(new_point_tag)

                data = source.to_dict()
                new_line_tag = project.next_line_tag()
                data["tag"] = new_line_tag
                data["name"] = f"{source.name} copy {copy_index}"
                data["point_i"] = new_endpoints[0]
                data["point_j"] = new_endpoints[1]
                data["generated_node_tags"] = []
                data["owned_node_tags"] = []
                data["generated_element_tags"] = []
                copied = LineGeometryData.from_dict(data)
                project.add_line(copied)
                created_lines.append(new_line_tag)

                source_meshed = bool(
                    inspect_line_mesh_state(
                        project,
                        source_tag,
                    ).live_element_tags
                )
                if mesh and source_meshed:
                    mesh_results[new_line_tag] = mesh_line_geometry(
                        project,
                        new_line_tag,
                    )

        return LineCopyResult(
            source_line_tags=tags,
            created_line_tags=created_lines,
            created_point_tags=created_points,
            mesh_results=mesh_results,
        )
    except Exception:
        restored = ProjectDatabase.from_dict(before)
        project.__dict__.clear()
        project.__dict__.update(restored.__dict__)
        raise

