from __future__ import annotations

from dataclasses import dataclass
import math

from .model import SHELL_ELEMENT_TYPES
from .project import ProjectDatabase


@dataclass(slots=True)
class ShellElementQuality:
    element_tag: int
    area: float
    aspect_ratio: float
    max_skew_deg: float
    warpage_deg: float


@dataclass(slots=True)
class ShellMeshQualitySummary:
    element_count: int
    min_area: float
    max_aspect_ratio: float
    max_skew_deg: float
    max_warpage_deg: float
    worst_aspect_element: int | None = None
    worst_skew_element: int | None = None
    worst_warpage_element: int | None = None

    @property
    def heuristic_status(self) -> str:
        """Studio geometry heuristic; not a solver acceptance criterion."""
        if self.element_count == 0:
            return "No mesh"
        if (
            self.max_aspect_ratio > 5.0
            or self.max_skew_deg > 45.0
            or self.max_warpage_deg > 20.0
        ):
            return "Review recommended"
        return "Geometry OK"


def _sub(a, b):
    return tuple(float(a[i]) - float(b[i]) for i in range(3))


def _dot(a, b) -> float:
    return sum(float(a[i]) * float(b[i]) for i in range(3))


def _cross(a, b):
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def _norm(a) -> float:
    return math.sqrt(_dot(a, a))


def _angle_deg(a, b) -> float:
    na = _norm(a)
    nb = _norm(b)
    if na <= 1.0e-15 or nb <= 1.0e-15:
        return 180.0
    cosine = max(-1.0, min(1.0, _dot(a, b) / (na * nb)))
    return math.degrees(math.acos(cosine))


def shell_element_quality_from_model(
    model,
    element_tag: int,
) -> ShellElementQuality:
    tag = int(element_tag)
    element = model.elements.get(tag)
    if element is None or element.element_type not in SHELL_ELEMENT_TYPES:
        raise ValueError(f"Element {tag} is not a Shell element.")

    node_tags = element.node_tags()
    if len(node_tags) != 4:
        raise ValueError(f"Shell element {tag} requires four nodes.")
    points = [
        model.nodes[node_tag].xyz
        for node_tag in node_tags
    ]
    p0, p1, p2, p3 = points

    n1 = _cross(_sub(p1, p0), _sub(p2, p0))
    n2 = _cross(_sub(p2, p0), _sub(p3, p0))
    area = 0.5 * (_norm(n1) + _norm(n2))

    edges = [
        _norm(_sub(points[(i + 1) % 4], points[i]))
        for i in range(4)
    ]
    min_edge = min(edges)
    aspect = (
        float("inf")
        if min_edge <= 1.0e-15
        else max(edges) / min_edge
    )

    interior_angles: list[float] = []
    for i in range(4):
        current = points[i]
        previous = points[(i - 1) % 4]
        following = points[(i + 1) % 4]
        interior_angles.append(
            _angle_deg(
                _sub(previous, current),
                _sub(following, current),
            )
        )
    max_skew = max(abs(angle - 90.0) for angle in interior_angles)

    if _norm(n1) <= 1.0e-15 or _norm(n2) <= 1.0e-15:
        warpage = 180.0
    else:
        warpage = _angle_deg(n1, n2)

    return ShellElementQuality(
        element_tag=tag,
        area=area,
        aspect_ratio=aspect,
        max_skew_deg=max_skew,
        warpage_deg=warpage,
    )


def shell_element_quality(
    project: ProjectDatabase,
    element_tag: int,
) -> ShellElementQuality:
    return shell_element_quality_from_model(
        project.model,
        element_tag,
    )


def shell_mesh_quality_summary(
    project: ProjectDatabase,
    element_tags,
) -> ShellMeshQualitySummary:
    tags = [
        int(tag)
        for tag in element_tags
        if (
            int(tag) in project.model.elements
            and project.model.elements[int(tag)].element_type
            in SHELL_ELEMENT_TYPES
        )
    ]
    if not tags:
        return ShellMeshQualitySummary(
            element_count=0,
            min_area=0.0,
            max_aspect_ratio=0.0,
            max_skew_deg=0.0,
            max_warpage_deg=0.0,
        )

    records = [
        shell_element_quality(project, tag)
        for tag in tags
    ]
    worst_aspect = max(records, key=lambda item: item.aspect_ratio)
    worst_skew = max(records, key=lambda item: item.max_skew_deg)
    worst_warpage = max(records, key=lambda item: item.warpage_deg)

    return ShellMeshQualitySummary(
        element_count=len(records),
        min_area=min(item.area for item in records),
        max_aspect_ratio=worst_aspect.aspect_ratio,
        max_skew_deg=worst_skew.max_skew_deg,
        max_warpage_deg=worst_warpage.warpage_deg,
        worst_aspect_element=worst_aspect.element_tag,
        worst_skew_element=worst_skew.element_tag,
        worst_warpage_element=worst_warpage.element_tag,
    )
