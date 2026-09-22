from __future__ import annotations

from dataclasses import dataclass, field
import math

from .model import SHELL_ELEMENT_TYPES
from .project import ProjectDatabase, SHELL_SECTION_TYPES


@dataclass(slots=True)
class ShellMeshSpec:
    corner_nodes: tuple[int, int, int, int]
    divisions_u: int = 1
    divisions_v: int = 1
    target_size: float | None = None
    bias_u: float = 1.0
    bias_v: float = 1.0
    edge_divisions: tuple[
        int | None,
        int | None,
        int | None,
        int | None,
    ] | None = None
    formulation: str = "ASDShellQ4"
    section_tag: int = 0
    corotational: bool = False
    local_x: tuple[float, float, float] | None = None
    no_eas: bool = False
    drilling_stab: float | None = None
    drilling_nl: bool = False
    reuse_existing_nodes: bool = True
    conform_existing_edges: bool = True
    merge_tolerance: float | None = None
    group: str = "shell"


@dataclass(slots=True)
class ShellMeshBuildResult:
    node_tags: list[int] = field(default_factory=list)
    reused_node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    grid: list[list[int]] = field(default_factory=list)
    divisions_u: int = 0
    divisions_v: int = 0
    conformed_u: bool = False
    conformed_v: bool = False
    u_coordinates: list[float] = field(default_factory=list)
    v_coordinates: list[float] = field(default_factory=list)


def _bilinear_point(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
    p4: tuple[float, float, float],
    u: float,
    v: float,
) -> tuple[float, float, float]:
    return tuple(
        (1.0 - u) * (1.0 - v) * p1[index]
        + u * (1.0 - v) * p2[index]
        + u * v * p3[index]
        + (1.0 - u) * v * p4[index]
        for index in range(3)
    )


def _distance(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return math.sqrt(
        sum(
            (float(b[index]) - float(a[index])) ** 2
            for index in range(3)
        )
    )


def resolve_shell_mesh_divisions(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
    p4: tuple[float, float, float],
    *,
    divisions_u: int,
    divisions_v: int,
    target_size: float | None,
) -> tuple[int, int]:
    if target_size is not None:
        size = float(target_size)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError(
                "Shell mesh target size must be a finite positive value."
            )
        u_length = 0.5 * (_distance(p1, p2) + _distance(p4, p3))
        v_length = 0.5 * (_distance(p1, p4) + _distance(p2, p3))
        nu = max(1, int(math.ceil(u_length / size)))
        nv = max(1, int(math.ceil(v_length / size)))
    else:
        nu = int(divisions_u)
        nv = int(divisions_v)

    if nu < 1 or nv < 1:
        raise ValueError("Shell mesh divisions U and V must be at least 1.")
    if nu > 500 or nv > 500:
        raise ValueError(
            "Shell mesh divisions are limited to 500 per direction."
        )
    return nu, nv


def _apply_edge_divisions(
    nu: int,
    nv: int,
    edge_divisions,
) -> tuple[int, int]:
    if edge_divisions is None:
        return int(nu), int(nv)
    if len(edge_divisions) != 4:
        raise ValueError(
            "Shell edge seeding requires four edge division entries."
        )
    seeds: list[int | None] = []
    for index, value in enumerate(edge_divisions, start=1):
        if value is None:
            seeds.append(None)
            continue
        seed = int(value)
        if not 1 <= seed <= 500:
            raise ValueError(
                f"Shell edge {index} divisions must be in 1..500."
            )
        seeds.append(seed)

    u_values = [
        value for value in (seeds[0], seeds[2])
        if value is not None
    ]
    v_values = [
        value for value in (seeds[1], seeds[3])
        if value is not None
    ]
    if len(set(u_values)) > 1:
        raise ValueError(
            "Mapped Shell mesh requires equal divisions on "
            "opposite edges 1 and 3."
        )
    if len(set(v_values)) > 1:
        raise ValueError(
            "Mapped Shell mesh requires equal divisions on "
            "opposite edges 2 and 4."
        )
    if u_values:
        nu = int(u_values[0])
    if v_values:
        nv = int(v_values[0])
    return int(nu), int(nv)


def biased_mesh_coordinates(
    divisions: int,
    bias: float = 1.0,
) -> list[float]:
    """Return normalized mapped-mesh coordinates with end/start size bias.

    bias = 1 gives uniform spacing. Values >1 create smaller cells near
    coordinate 0 and larger cells near coordinate 1; values <1 reverse it.
    """
    n = int(divisions)
    if n < 1:
        raise ValueError("Mesh divisions must be at least 1.")
    value = float(bias)
    if (
        not math.isfinite(value)
        or value < 0.01
        or value > 100.0
    ):
        raise ValueError(
            "Mesh bias must be finite and in 0.01..100."
        )
    if n == 1 or abs(value - 1.0) <= 1.0e-12:
        return [index / n for index in range(n + 1)]

    # Let consecutive interval sizes form a geometric progression.
    # The requested bias is last interval / first interval.
    ratio = value ** (1.0 / (n - 1))
    if abs(ratio - 1.0) <= 1.0e-12:
        return [index / n for index in range(n + 1)]
    weights = [ratio ** index for index in range(n)]
    total = sum(weights)
    result = [0.0]
    cumulative = 0.0
    for weight in weights:
        cumulative += weight
        result.append(cumulative / total)
    result[-1] = 1.0
    return result


def resolve_shell_mesh_parameters(
    p1,
    p2,
    p3,
    p4,
    *,
    divisions_u: int,
    divisions_v: int,
    target_size: float | None,
    bias_u: float = 1.0,
    bias_v: float = 1.0,
    edge_divisions=None,
) -> tuple[list[float], list[float]]:
    nu, nv = resolve_shell_mesh_divisions(
        p1,
        p2,
        p3,
        p4,
        divisions_u=divisions_u,
        divisions_v=divisions_v,
        target_size=target_size,
    )
    nu, nv = _apply_edge_divisions(
        nu,
        nv,
        edge_divisions,
    )
    return (
        biased_mesh_coordinates(nu, bias_u),
        biased_mesh_coordinates(nv, bias_v),
    )


def _mesh_merge_tolerance(
    project: ProjectDatabase,
    requested: float | None,
) -> float:
    if requested is not None:
        value = float(requested)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                "Shell mesh merge tolerance must be a finite positive value."
            )
        return value
    if not project.model.nodes:
        return 1.0e-9
    xs = [float(node.xyz[0]) for node in project.model.nodes.values()]
    ys = [float(node.xyz[1]) for node in project.model.nodes.values()]
    zs = [float(node.xyz[2]) for node in project.model.nodes.values()]
    span = max(
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
        1.0,
    )
    return 1.0e-9 * span


def _existing_shell_edge_divisions(
    project: ProjectDatabase,
    start_tag: int,
    end_tag: int,
    *,
    tolerance: float,
) -> int | None:
    """Return existing conforming edge divisions when a full shell chain exists."""
    start = project.model.nodes.get(int(start_tag))
    end = project.model.nodes.get(int(end_tag))
    if start is None or end is None:
        return None

    a = tuple(float(value) for value in start.xyz)
    b = tuple(float(value) for value in end.xyz)
    ab = tuple(b[index] - a[index] for index in range(3))
    length2 = sum(value * value for value in ab)
    if length2 <= tolerance * tolerance:
        return None

    shell_edges: set[tuple[int, int]] = set()
    shell_nodes: set[int] = set()
    for element in project.model.elements.values():
        if element.element_type not in SHELL_ELEMENT_TYPES:
            continue
        tags = element.node_tags()
        shell_nodes.update(int(tag) for tag in tags)
        for left, right in zip(tags, tags[1:] + tags[:1]):
            shell_edges.add(tuple(sorted((int(left), int(right)))))

    if int(start_tag) not in shell_nodes or int(end_tag) not in shell_nodes:
        return None

    tolerance2 = tolerance * tolerance
    points: list[tuple[float, int]] = []
    for tag in shell_nodes:
        node = project.model.nodes.get(tag)
        if node is None:
            continue
        point = tuple(float(value) for value in node.xyz)
        ap = tuple(point[index] - a[index] for index in range(3))
        t = sum(ap[index] * ab[index] for index in range(3)) / length2
        if t < -1.0e-10 or t > 1.0 + 1.0e-10:
            continue
        closest = tuple(
            a[index] + t * ab[index]
            for index in range(3)
        )
        distance2 = sum(
            (point[index] - closest[index]) ** 2
            for index in range(3)
        )
        if distance2 <= tolerance2:
            points.append((max(0.0, min(1.0, t)), int(tag)))

    points.sort(key=lambda item: (item[0], item[1]))
    unique: list[tuple[float, int]] = []
    for t, tag in points:
        if unique and abs(t - unique[-1][0]) <= 1.0e-10:
            if tag in {int(start_tag), int(end_tag)}:
                unique[-1] = (t, tag)
            continue
        unique.append((t, tag))

    if len(unique) < 2:
        return None
    if unique[0][1] != int(start_tag) or unique[-1][1] != int(end_tag):
        return None

    for left, right in zip(unique, unique[1:]):
        if tuple(sorted((left[1], right[1]))) not in shell_edges:
            return None

    divisions = len(unique) - 1
    for index, (t, _tag) in enumerate(unique):
        expected = index / divisions
        if abs(t - expected) > max(
            1.0e-8,
            5.0 * tolerance / math.sqrt(length2),
        ):
            raise ValueError(
                "Existing shell edge mesh is non-uniform; structured "
                "automatic conformity requires evenly spaced edge nodes."
            )
    return divisions


def _conform_shell_mesh_divisions(
    project: ProjectDatabase,
    corners: tuple[int, int, int, int],
    *,
    nu: int,
    nv: int,
    tolerance: float,
) -> tuple[int, int, bool, bool]:
    u_counts = {
        count
        for count in (
            _existing_shell_edge_divisions(
                project, corners[0], corners[1], tolerance=tolerance
            ),
            _existing_shell_edge_divisions(
                project, corners[3], corners[2], tolerance=tolerance
            ),
        )
        if count is not None
    }
    v_counts = {
        count
        for count in (
            _existing_shell_edge_divisions(
                project, corners[0], corners[3], tolerance=tolerance
            ),
            _existing_shell_edge_divisions(
                project, corners[1], corners[2], tolerance=tolerance
            ),
        )
        if count is not None
    }
    if len(u_counts) > 1:
        raise ValueError(
            "Opposite existing shell edges have incompatible U divisions."
        )
    if len(v_counts) > 1:
        raise ValueError(
            "Opposite existing shell edges have incompatible V divisions."
        )

    conformed_u = bool(u_counts and next(iter(u_counts)) != nu)
    conformed_v = bool(v_counts and next(iter(v_counts)) != nv)
    if u_counts:
        nu = next(iter(u_counts))
    if v_counts:
        nv = next(iter(v_counts))
    return nu, nv, conformed_u, conformed_v


def _node_spatial_key(
    xyz: tuple[float, float, float],
    tolerance: float,
) -> tuple[int, int, int]:
    return tuple(
        int(round(float(value) / tolerance))
        for value in xyz
    )


def _nearby_existing_node(
    xyz: tuple[float, float, float],
    *,
    project: ProjectDatabase,
    buckets: dict[tuple[int, int, int], list[int]],
    tolerance: float,
) -> int | None:
    base = _node_spatial_key(xyz, tolerance)
    tolerance2 = tolerance * tolerance
    best: tuple[float, int] | None = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for tag in buckets.get(
                    (base[0] + dx, base[1] + dy, base[2] + dz),
                    (),
                ):
                    node = project.model.nodes.get(tag)
                    if node is None:
                        continue
                    distance2 = sum(
                        (
                            float(node.xyz[index])
                            - float(xyz[index])
                        ) ** 2
                        for index in range(3)
                    )
                    if distance2 <= tolerance2 and (
                        best is None or distance2 < best[0]
                    ):
                        best = (distance2, int(tag))
    return None if best is None else best[1]


def build_shell_mesh(
    project: ProjectDatabase,
    spec: ShellMeshSpec,
) -> ShellMeshBuildResult:
    """Mesh a four-corner surface with structured quadrilateral shells."""
    if (int(project.model.ndm), int(project.model.ndf)) != (3, 6):
        raise ValueError(
            "Shell surface meshing requires a 3D/6DOF structural model."
        )

    corners = tuple(int(tag) for tag in spec.corner_nodes)
    if len(corners) != 4 or len(set(corners)) != 4:
        raise ValueError(
            "Shell surface meshing requires four distinct corner nodes."
        )
    missing = [tag for tag in corners if tag not in project.model.nodes]
    if missing:
        raise ValueError(
            "Shell surface corners reference missing node tag(s): "
            + ", ".join(map(str, missing))
        )

    p1 = project.model.nodes[corners[0]].xyz
    p2 = project.model.nodes[corners[1]].xyz
    p3 = project.model.nodes[corners[2]].xyz
    p4 = project.model.nodes[corners[3]].xyz

    def triangle_area2(a, b, d) -> float:
        ab = tuple(
            float(b[index]) - float(a[index])
            for index in range(3)
        )
        ad = tuple(
            float(d[index]) - float(a[index])
            for index in range(3)
        )
        cross = (
            ab[1] * ad[2] - ab[2] * ad[1],
            ab[2] * ad[0] - ab[0] * ad[2],
            ab[0] * ad[1] - ab[1] * ad[0],
        )
        return math.sqrt(sum(value * value for value in cross))

    corner_area2 = triangle_area2(p1, p2, p3)
    corner_area2 += triangle_area2(p1, p3, p4)
    if corner_area2 <= 1.0e-12:
        raise ValueError(
            "Shell mesh corner surface has zero or near-zero area."
        )

    u_coordinates, v_coordinates = resolve_shell_mesh_parameters(
        p1,
        p2,
        p3,
        p4,
        divisions_u=spec.divisions_u,
        divisions_v=spec.divisions_v,
        target_size=spec.target_size,
        bias_u=spec.bias_u,
        bias_v=spec.bias_v,
        edge_divisions=spec.edge_divisions,
    )
    nu = len(u_coordinates) - 1
    nv = len(v_coordinates) - 1
    merge_tolerance = _mesh_merge_tolerance(
        project,
        spec.merge_tolerance,
    )
    conformed_u = False
    conformed_v = False
    if spec.conform_existing_edges:
        nu, nv, conformed_u, conformed_v = (
            _conform_shell_mesh_divisions(
                project,
                corners,
                nu=nu,
                nv=nv,
                tolerance=merge_tolerance,
            )
        )
        u_coordinates = biased_mesh_coordinates(nu, spec.bias_u)
        v_coordinates = biased_mesh_coordinates(nv, spec.bias_v)

    formulation = str(spec.formulation)
    if formulation not in SHELL_ELEMENT_TYPES:
        raise ValueError(
            f"Unsupported shell formulation: {formulation}"
        )

    section_tag = int(spec.section_tag)
    section = project.sections.get(section_tag)
    if (
        section is None
        or section.section_type not in SHELL_SECTION_TYPES
    ):
        raise ValueError(
            "Shell mesh requires an existing shell-compatible Section."
        )

    corner_lookup = {
        (0, 0): corners[0],
        (nu, 0): corners[1],
        (nu, nv): corners[2],
        (0, nv): corners[3],
    }

    next_node = project.model.next_node_tag()
    grid: list[list[int]] = []
    created_nodes: list[int] = []
    reused_nodes: set[int] = set()
    node_buckets: dict[tuple[int, int, int], list[int]] = {}
    if spec.reuse_existing_nodes:
        for tag, node in project.model.nodes.items():
            key = _node_spatial_key(node.xyz, merge_tolerance)
            node_buckets.setdefault(key, []).append(int(tag))

    for j, v in enumerate(v_coordinates):
        row: list[int] = []
        for i, u in enumerate(u_coordinates):
            if (i, j) in corner_lookup:
                row.append(corner_lookup[(i, j)])
                continue

            xyz = _bilinear_point(p1, p2, p3, p4, u, v)
            existing_tag = None
            if spec.reuse_existing_nodes:
                existing_tag = _nearby_existing_node(
                    xyz,
                    project=project,
                    buckets=node_buckets,
                    tolerance=merge_tolerance,
                )
            if existing_tag is not None:
                row.append(existing_tag)
                reused_nodes.add(existing_tag)
                continue

            while next_node in project.model.nodes:
                next_node += 1
            project.model.add_node(next_node, *xyz)
            row.append(next_node)
            created_nodes.append(next_node)
            if spec.reuse_existing_nodes:
                key = _node_spatial_key(xyz, merge_tolerance)
                node_buckets.setdefault(key, []).append(next_node)
            next_node += 1
        grid.append(row)

    next_element = project.next_element_tag()
    created_elements: list[int] = []
    try:
        for j in range(nv):
            for i in range(nu):
                while (
                    next_element in project.model.elements
                    or next_element in project.connections
                ):
                    next_element += 1
                node_tags = (
                    grid[j][i],
                    grid[j][i + 1],
                    grid[j + 1][i + 1],
                    grid[j + 1][i],
                )
                project.model.add_element(
                    next_element,
                    node_tags[0],
                    node_tags[1],
                    element_type=formulation,
                    section_tag=section_tag,
                    group=str(spec.group or "shell"),
                    k=node_tags[2],
                    l=node_tags[3],
                    shell_corotational=(
                        bool(spec.corotational)
                        if formulation == "ASDShellQ4"
                        else False
                    ),
                    shell_local_x=(
                        spec.local_x
                        if formulation == "ASDShellQ4"
                        else None
                    ),
                    shell_no_eas=(
                        bool(spec.no_eas)
                        if formulation == "ASDShellQ4"
                        else False
                    ),
                    shell_drilling_stab=(
                        spec.drilling_stab
                        if formulation == "ASDShellQ4"
                        else None
                    ),
                    shell_drilling_nl=(
                        bool(spec.drilling_nl)
                        if formulation == "ASDShellQ4"
                        else False
                    ),
                )
                created_elements.append(next_element)
                project.validate_element_state(next_element)
                next_element += 1
    except Exception:
        for tag in created_elements:
            project.model.elements.pop(tag, None)
        for tag in created_nodes:
            project.model.nodes.pop(tag, None)
        raise

    return ShellMeshBuildResult(
        node_tags=created_nodes,
        reused_node_tags=sorted(reused_nodes),
        element_tags=created_elements,
        grid=grid,
        divisions_u=nu,
        divisions_v=nv,
        conformed_u=conformed_u,
        conformed_v=conformed_v,
        u_coordinates=list(u_coordinates),
        v_coordinates=list(v_coordinates),
    )
