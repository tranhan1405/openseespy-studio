from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .beam_loads import resolve_self_weight_local
from .model import (
    BEARING_ELEMENT_TYPES,
    CABLE_ELEMENT_TYPES,
    EMBEDDED_ELEMENT_TYPES,
    FRAME_ELEMENT_TYPES,
    SHELL_ELEMENT_TYPES,
    SUPPORTED_ELEMENT_TYPES,
)
from .project import (
    AnalysisSettingsData,
    ProjectDatabase,
    SHELL_SECTION_TYPES,
    resolve_transformation_vecxz,
)
from .units import UnitSystem



@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str
    category: str
    message: str
    entity_kind: str | None = None
    entity_tag: int | None = None
    suggestion: str = ""

    def __post_init__(self) -> None:
        severity = self.severity.upper()
        if severity not in {"ERROR", "WARNING", "INFO"}:
            raise ValueError(f"Unsupported validation severity: {self.severity}")
        object.__setattr__(self, "severity", severity)


def _norm(values: Iterable[float]) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in values))


def _cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _suggest_vecxz(
    axis: tuple[float, float, float],
) -> tuple[float, float, float]:
    # Prefer global Z for beams. If the member is vertical, fall back to X,
    # then Y. This gives intuitive building-frame defaults.
    candidates = (
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    axis_norm = _norm(axis)
    if axis_norm <= 1.0e-15:
        return candidates[0]
    for candidate in candidates:
        sine = _norm(_cross(axis, candidate)) / axis_norm
        if sine > 1.0e-6:
            return candidate
    return (1.0, 0.0, 0.0)


def _format_vector(values: tuple[float, float, float]) -> str:
    return "(" + ", ".join(f"{value:g}" for value in values) + ")"


def _point_in_triangle_xy(
    point: tuple[float, float, float],
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    d: tuple[float, float, float],
    *,
    tolerance: float = 1.0e-8,
) -> tuple[bool, bool]:
    """Return (inside_or_boundary, nondegenerate) using barycentric weights."""
    denominator = (
        (b[1] - d[1]) * (a[0] - d[0])
        + (d[0] - b[0]) * (a[1] - d[1])
    )
    scale = max(
        abs(a[0]), abs(a[1]),
        abs(b[0]), abs(b[1]),
        abs(d[0]), abs(d[1]),
        1.0,
    )
    if abs(denominator) <= 1.0e-14 * scale * scale:
        return False, False

    w1 = (
        (b[1] - d[1]) * (point[0] - d[0])
        + (d[0] - b[0]) * (point[1] - d[1])
    ) / denominator
    w2 = (
        (d[1] - a[1]) * (point[0] - d[0])
        + (a[0] - d[0]) * (point[1] - d[1])
    ) / denominator
    w3 = 1.0 - w1 - w2
    inside = all(
        -tolerance <= value <= 1.0 + tolerance
        for value in (w1, w2, w3)
    )
    return inside, True


def _shell_quad_ordering_issue(
    points: list[tuple[float, float, float]],
) -> str | None:
    """Return a concise shell-boundary issue for an invalid quadrilateral."""
    normal = [0.0, 0.0, 0.0]
    for index in range(4):
        current = points[index]
        following = points[(index + 1) % 4]
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
    if sum(value * value for value in normal) <= 1.0e-24:
        return "crossed or degenerate quadrilateral boundary"

    drop_axis = max(range(3), key=lambda axis: abs(normal[axis]))
    projected = [
        tuple(
            point[axis]
            for axis in range(3)
            if axis != drop_axis
        )
        for point in points
    ]

    def orient2d(a, b, c) -> float:
        return (
            (b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0])
        )

    def proper_intersection(a, b, c, d) -> bool:
        o1 = orient2d(a, b, c)
        o2 = orient2d(a, b, d)
        o3 = orient2d(c, d, a)
        o4 = orient2d(c, d, b)
        scale = max(abs(o1), abs(o2), abs(o3), abs(o4), 1.0)
        tol = 1.0e-12 * scale
        return (
            o1 * o2 < -(tol * tol)
            and o3 * o4 < -(tol * tol)
        )

    if (
        proper_intersection(
            projected[0], projected[1],
            projected[2], projected[3],
        )
        or proper_intersection(
            projected[1], projected[2],
            projected[3], projected[0],
        )
    ):
        return "self-intersecting quadrilateral boundary"

    turns = [
        orient2d(
            projected[index],
            projected[(index + 1) % 4],
            projected[(index + 2) % 4],
        )
        for index in range(4)
    ]
    turn_scale = max(max(abs(value) for value in turns), 1.0)
    meaningful = [
        value
        for value in turns
        if abs(value) > 1.0e-12 * turn_scale
    ]
    if meaningful and min(meaningful) < 0.0 < max(meaningful):
        return "concave quadrilateral boundary"
    return None


def _element_geometry_checks(
    project: ProjectDatabase,
    issues: list[ValidationIssue],
) -> None:
    model = project.model
    seen_connectivity: dict[tuple[int, ...], list[int]] = {}
    shell_edge_owners: dict[
        tuple[int, int],
        list[tuple[int, int, int]],
    ] = {}
    shell_node_tags: set[int] = set()

    for tag in sorted(model.elements):
        element = model.elements[tag]
        node_tags = tuple(int(value) for value in element.node_tags())
        missing = [
            node_tag
            for node_tag in node_tags
            if node_tag not in model.nodes
        ]
        if missing:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Geometry",
                    f"Element {tag} references missing node tag(s): "
                    + ", ".join(map(str, missing)),
                    "element",
                    tag,
                    "Repair or recreate the element connectivity.",
                )
            )
            continue

        connectivity = tuple(sorted(node_tags))
        previous_tags = seen_connectivity.setdefault(connectivity, [])
        if previous_tags:
            group = str(element.group or "")
            is_rc_wall_rebar = group.startswith("rc-wall-rebar-")

            duplicate_of: int | None = None
            duplicate_is_same_rebar = False

            if is_rc_wall_rebar and len(node_tags) == 2:
                # RC-wall discrete bars intentionally share the same MEFI
                # node pair under the current perfect-bond formulation.
                # Different bar/layer groups are therefore parallel physical
                # bars, not duplicate geometry. Only flag a repeated segment
                # when the same bar identity/group appears on the same pair.
                for previous_tag in previous_tags:
                    previous = model.elements[previous_tag]
                    previous_group = str(previous.group or "")
                    if (
                        previous_group.startswith("rc-wall-rebar-")
                        and previous_group == group
                    ):
                        duplicate_of = previous_tag
                        duplicate_is_same_rebar = True
                        break

                # A reinforcement bar overlapping a non-reinforcement
                # two-node element is still suspicious and remains visible.
                if duplicate_of is None:
                    for previous_tag in previous_tags:
                        previous = model.elements[previous_tag]
                        if not str(previous.group or "").startswith(
                            "rc-wall-rebar-"
                        ):
                            duplicate_of = previous_tag
                            break
            else:
                duplicate_of = previous_tags[0]

            if duplicate_of is not None:
                if duplicate_is_same_rebar:
                    duplicate_message = (
                        f"Element {tag} duplicates the node pair and "
                        f"reinforcement identity of element {duplicate_of}."
                    )
                    duplicate_suggestion = (
                        "Remove the repeated reinforcement segment or assign "
                        "it a distinct bar/layer identity if it is intentional."
                    )
                else:
                    duplicate_message = (
                        f"Element {tag} duplicates the node pair of element "
                        f"{duplicate_of}."
                        if len(node_tags) == 2
                        else (
                            f"Element {tag} duplicates the shell connectivity "
                            f"of element {duplicate_of}."
                        )
                    )
                    duplicate_suggestion = (
                        "Confirm that the duplicate element is intentional."
                    )

                issues.append(
                    ValidationIssue(
                        "WARNING",
                        "Geometry",
                        duplicate_message,
                        "element",
                        tag,
                        duplicate_suggestion,
                    )
                )

        previous_tags.append(tag)

        if element.element_type not in SUPPORTED_ELEMENT_TYPES:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Element formulation",
                    f"Element {tag} uses {element.element_type}, which the "
                    "current generator does not yet emit faithfully.",
                    "element",
                    tag,
                    "Choose a formulation supported by FEWIZ.",
                )
            )
            continue

        if element.element_type in EMBEDDED_ELEMENT_TYPES:
            if int(model.ndm) != 2 or int(model.ndf) not in {2, 3}:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Embedded reinforcement",
                        f"Embedded element {tag} currently requires a 2D "
                        "model with ndf=2 or ndf=3.",
                        "element",
                        tag,
                        "Use the embedded-rebar infrastructure only with "
                        "the current 2D continuum/MEFI workflow.",
                    )
                )
                continue

            constrained = tuple(
                float(value) for value in model.nodes[element.i].xyz
            )
            retained = [
                tuple(float(value) for value in model.nodes[node_tag].xyz)
                for node_tag in (element.j, element.k, element.l)
            ]
            inside, nondegenerate = _point_in_triangle_xy(
                constrained,
                retained[0],
                retained[1],
                retained[2],
            )
            if not nondegenerate:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Embedded reinforcement",
                        f"Embedded element {tag} uses a degenerate retained "
                        "triangle.",
                        "element",
                        tag,
                        "Choose three non-collinear host nodes.",
                    )
                )
            elif not inside:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Embedded reinforcement",
                        f"Embedded node {element.i} lies outside the retained "
                        f"triangle {element.j}-{element.k}-{element.l}.",
                        "element",
                        tag,
                        "Reassign the embedded node to a host triangle that "
                        "contains it.",
                    )
                )

            if (
                element.embedded_constrain_rotation
                and int(model.ndf) < 3
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Embedded reinforcement",
                        f"Embedded element {tag} requests rotational coupling "
                        f"but the model has ndf={model.ndf}.",
                        "element",
                        tag,
                        "Disable rotational coupling or use ndf=3.",
                    )
                )
            if element.embedded_penalty is None:
                issues.append(
                    ValidationIssue(
                        "WARNING",
                        "Embedded reinforcement",
                        f"Embedded element {tag} uses the OpenSees default "
                        "penalty stiffness.",
                        "element",
                        tag,
                        "Prefer an explicit penalty stiffness of the same "
                        "order as the surrounding material modulus.",
                    )
                )
            continue

        if element.element_type == "MEFI":
            if (int(model.ndm), int(model.ndf)) not in {
                (2, 3), (3, 6),
            }:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI",
                        f"MEFI element {tag} requires ndm=2/ndf=3 or "
                        "ndm=3/ndf=6.",
                        "element",
                        tag,
                        "Use the RC Wall Wizard 2D model signature or a "
                        "compatible 3D/6DOF domain.",
                    )
                )
            points = [
                tuple(float(value) for value in model.nodes[node_tag].xyz)
                for node_tag in node_tags
            ]
            if len(points) != 4:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI geometry",
                        f"MEFI element {tag} does not have four nodes.",
                        "element",
                        tag,
                        "Recreate the element with four counter-clockwise nodes.",
                    )
                )
                continue
            ordering_issue = _shell_quad_ordering_issue(points)
            if ordering_issue is not None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI geometry",
                        f"MEFI element {tag} has {ordering_issue}.",
                        "element",
                        tag,
                        "Order MEFI nodes counter-clockwise around the panel.",
                    )
                )
            if int(model.ndm) == 2:
                signed_twice_area = sum(
                    points[index][0] * points[(index + 1) % 4][1]
                    - points[(index + 1) % 4][0] * points[index][1]
                    for index in range(4)
                )
                if signed_twice_area <= 0.0:
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "MEFI geometry",
                            f"MEFI element {tag} nodes are not "
                            "counter-clockwise in the XY plane.",
                            "element",
                            tag,
                            "Use I-J-K-L node order counter-clockwise, as "
                            "required by the OpenSees MEFI formulation.",
                        )
                    )
            edge_width = _norm(tuple(
                points[1][axis] - points[0][axis]
                for axis in range(3)
            ))
            width_sum = sum(float(value) for value in element.mefi_widths)
            if abs(width_sum - edge_width) > max(
                1.0e-9,
                1.0e-6 * max(edge_width, 1.0),
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI macro-fibers",
                        f"MEFI element {tag} macro-fiber widths sum to "
                        f"{width_sum:g}, but its i-j edge width is "
                        f"{edge_width:g}.",
                        "element",
                        tag,
                        "Make the macro-fiber widths sum to the panel width.",
                    )
                )
            if len(element.mefi_widths) != len(element.mefi_section_tags):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI macro-fibers",
                        f"MEFI element {tag} width/section arrays differ "
                        "in length.",
                        "element",
                        tag,
                        "Assign one RCLMS section to every macro-fiber.",
                    )
                )
            missing_sections = sorted({
                int(section_tag)
                for section_tag in element.mefi_section_tags
                if int(section_tag) not in project.sections
            })
            if missing_sections:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI Section",
                        f"MEFI element {tag} references missing section "
                        "tag(s): " + ", ".join(map(str, missing_sections)),
                        "element",
                        tag,
                        "Create or reassign the missing RCLMS sections.",
                    )
                )
            incompatible = sorted({
                int(section_tag)
                for section_tag in element.mefi_section_tags
                if (
                    int(section_tag) in project.sections
                    and project.sections[
                        int(section_tag)
                    ].section_type != "RCLMS"
                )
            })
            if incompatible:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MEFI Section",
                        f"MEFI element {tag} requires RCLMS sections; "
                        "incompatible tag(s): "
                        + ", ".join(map(str, incompatible)),
                        "element",
                        tag,
                        "Assign RCLMS sections to all MEFI macro-fibers.",
                    )
                )
            continue

        if element.element_type in SHELL_ELEMENT_TYPES:
            shell_node_tags.update(node_tags)
            if (int(model.ndm), int(model.ndf)) != (3, 6):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Shell",
                        f"{element.element_type} element {tag} requires "
                        "ndm=3 and ndf=6.",
                        "element",
                        tag,
                        "Use the standard 3D/6DOF structural model for shell "
                        "surfaces.",
                    )
                )

            points = [
                tuple(float(value) for value in model.nodes[node_tag].xyz)
                for node_tag in node_tags
            ]
            edge_vectors = [
                tuple(
                    points[(index + 1) % 4][axis]
                    - points[index][axis]
                    for axis in range(3)
                )
                for index in range(4)
            ]
            if any(_norm(vector) <= 1.0e-12 for vector in edge_vectors):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Shell geometry",
                        f"Shell element {tag} has a zero-length edge.",
                        "element",
                        tag,
                        "Use four distinct boundary nodes in clockwise or "
                        "counter-clockwise order.",
                    )
                )

            diagonal_a = tuple(
                points[2][axis] - points[0][axis]
                for axis in range(3)
            )
            diagonal_b = tuple(
                points[3][axis] - points[1][axis]
                for axis in range(3)
            )
            area_measure = _norm(_cross(diagonal_a, diagonal_b))
            if area_measure <= 1.0e-12:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Shell geometry",
                        f"Shell element {tag} has zero or near-zero area.",
                        "element",
                        tag,
                        "Reorder or move the four shell nodes.",
                    )
                )

            ordering_issue = _shell_quad_ordering_issue(points)
            if ordering_issue is not None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Shell geometry",
                        f"Shell element {tag} has {ordering_issue}.",
                        "element",
                        tag,
                        "Order nodes around a convex shell boundary "
                        "clockwise or counter-clockwise.",
                    )
                )

            edge_lengths = [_norm(vector) for vector in edge_vectors]
            positive_edges = [
                length for length in edge_lengths
                if length > 1.0e-12
            ]
            if positive_edges:
                aspect_ratio = max(positive_edges) / min(positive_edges)
                if aspect_ratio > 10.0:
                    issues.append(
                        ValidationIssue(
                            "WARNING",
                            "Shell quality",
                            f"Shell element {tag} has edge aspect ratio "
                            f"{aspect_ratio:.3g} (> 10).",
                            "element",
                            tag,
                            "Refine or repartition the surface to avoid "
                            "highly stretched quadrilateral shell elements.",
                        )
                    )

            tri_a = _cross(
                tuple(
                    points[1][axis] - points[0][axis]
                    for axis in range(3)
                ),
                tuple(
                    points[2][axis] - points[0][axis]
                    for axis in range(3)
                ),
            )
            tri_b = _cross(
                tuple(
                    points[2][axis] - points[0][axis]
                    for axis in range(3)
                ),
                tuple(
                    points[3][axis] - points[0][axis]
                    for axis in range(3)
                ),
            )
            norm_a = _norm(tri_a)
            norm_b = _norm(tri_b)
            if norm_a > 1.0e-12 and norm_b > 1.0e-12:
                cosine = sum(
                    tri_a[axis] * tri_b[axis]
                    for axis in range(3)
                ) / (norm_a * norm_b)
                cosine = max(-1.0, min(1.0, cosine))
                warpage_deg = math.degrees(math.acos(cosine))
                if warpage_deg > 15.0:
                    issues.append(
                        ValidationIssue(
                            "WARNING",
                            "Shell quality",
                            f"Shell element {tag} has warpage angle "
                            f"{warpage_deg:.3g}° (> 15°).",
                            "element",
                            tag,
                            "Refine the mesh or use a flatter quadrilateral "
                            "patch where practical.",
                        )
                    )

            if element.section_tag is None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Shell Section",
                        f"Shell element {tag} has no section assigned.",
                        "element",
                        tag,
                        "Create and assign a Shell Section.",
                    )
                )
            else:
                section = project.sections.get(int(element.section_tag))
                if section is None:
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "Shell Section",
                            f"Shell element {tag} references missing section "
                            f"{element.section_tag}.",
                            "element",
                            tag,
                            "Assign an existing Shell Section.",
                        )
                    )
                elif section.section_type not in SHELL_SECTION_TYPES:
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "Shell Section",
                            f"Shell element {tag} cannot use "
                            f"{section.section_type} section {section.tag}.",
                            "element",
                            tag,
                            "Assign an ElasticMembranePlate Shell Section.",
                        )
                    )

            for left, right in zip(
                node_tags,
                node_tags[1:] + node_tags[:1],
            ):
                edge_key = tuple(sorted((int(left), int(right))))
                shell_edge_owners.setdefault(edge_key, []).append(
                    (int(tag), int(left), int(right))
                )
            continue

        node_i = model.nodes[element.i]
        node_j = model.nodes[element.j]
        axis = tuple(
            node_j.xyz[index] - node_i.xyz[index]
            for index in range(3)
        )
        length = _norm(axis)
        if (
            length <= 1.0e-12
            and element.element_type not in BEARING_ELEMENT_TYPES
        ):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Geometry",
                    f"Element {tag} has zero or near-zero length.",
                    "element",
                    tag,
                    "Move one end node or delete the element.",
                )
            )

        if element.element_type == "truss":
            if element.truss_area <= 0.0:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Truss",
                        f"Truss element {tag} has non-positive area.",
                        "element",
                        tag,
                        "Assign a positive cross-sectional area.",
                    )
                )
            if element.truss_material_tag is None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Material",
                        f"Truss element {tag} has no material assigned.",
                        "element",
                        tag,
                        "Assign a uniaxial material before running.",
                    )
                )
            elif element.truss_material_tag not in project.materials:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Material",
                        f"Truss element {tag} references missing material "
                        f"{element.truss_material_tag}.",
                        "element",
                        tag,
                        "Assign an existing uniaxial material.",
                    )
                )
            continue

        if element.element_type in CABLE_ELEMENT_TYPES:
            if (
                int(model.ndm) != 3
                or int(model.ndf) not in {3, 6}
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Cable formulation",
                        f"CatenaryCable element {tag} requires ndm=3 with "
                        f"ndf=3 or 6; got ndm={model.ndm}, ndf={model.ndf}.",
                        "element",
                        tag,
                        "Use a 3D model with 3 or 6 DOF per node.",
                    )
                )
            continue

        if element.element_type in BEARING_ELEMENT_TYPES:
            signature = (int(model.ndm), int(model.ndf))
            if signature not in {(2, 3), (3, 6)}:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Bearing formulation",
                        f"elastomericBearingPlasticity element {tag} "
                        f"requires 2D/3DOF or 3D/6DOF; got "
                        f"ndm={model.ndm}, ndf={model.ndf}.",
                        "element",
                        tag,
                        "Use a 2D/3DOF or 3D/6DOF structural model.",
                    )
                )
            referenced = {
                int(value)
                for key in (
                    "p_mat_tag", "t_mat_tag", "my_mat_tag", "mz_mat_tag"
                )
                for value in [element.special_parameters.get(key)]
                if value is not None
            }
            missing = sorted(
                mat_tag for mat_tag in referenced
                if mat_tag not in project.materials
            )
            if missing:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Bearing material",
                        f"elastomericBearingPlasticity element {tag} "
                        "references missing uniaxial material tag(s): "
                        + ", ".join(map(str, missing))
                        + ".",
                        "element",
                        tag,
                        "Assign existing uniaxial materials to all bearing "
                        "directions.",
                    )
                )
            if signature == (3, 6) and (
                element.special_parameters.get("t_mat_tag") is None
                or element.special_parameters.get("my_mat_tag") is None
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Bearing material",
                        f"3D elastomericBearingPlasticity element {tag} "
                        "requires axial, torsion, My, and Mz materials.",
                        "element",
                        tag,
                        "Assign all four 3D bearing material directions.",
                    )
                )
            continue

        if element.element_type not in FRAME_ELEMENT_TYPES:
            continue

        if element.section_tag is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Section",
                    f"Element {tag} has no section assigned.",
                    "element",
                    tag,
                    "Assign a section before running.",
                )
            )
        else:
            section = project.sections.get(element.section_tag)
            if section is None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Section",
                        f"Element {tag} references missing section "
                        f"{element.section_tag}.",
                        "element",
                        tag,
                        "Assign an existing section.",
                    )
                )
            elif (
                element.element_type
                in {"elasticBeamColumn", "ElasticTimoshenkoBeam"}
                and section.section_type != "Elastic"
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Element formulation",
                        f"{element.element_type} element {tag} cannot use "
                        f"{section.section_type} section {section.tag}; "
                        "an Elastic section is required.",
                        "element",
                        tag,
                        "Assign an Elastic Section to this element.",
                    )
                )
            elif element.element_type == "dispBeamColumnInt":
                if (int(model.ndm), int(model.ndf)) != (2, 3):
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "Element formulation",
                            f"dispBeamColumnInt element {tag} requires "
                            "ndm=2 and ndf=3.",
                            "element",
                            tag,
                            "Use this formulation only in a 2D/3DOF model.",
                        )
                    )
                if section.section_type != "FiberInt":
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "Element formulation",
                            f"dispBeamColumnInt element {tag} requires a "
                            f"FiberInt section; got {section.section_type} "
                            f"section {section.tag}.",
                            "element",
                            tag,
                            "Assign a FiberInt section.",
                        )
                    )
                if element.integration_points < 1:
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "Beam integration",
                            f"dispBeamColumnInt element {tag} needs at least "
                            "1 integration point.",
                            "element",
                            tag,
                            "Increase the integration-point count.",
                        )
                    )
                if not 0.0 <= float(element.beam_center_ratio) <= 1.0:
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "Element formulation",
                            f"dispBeamColumnInt element {tag} has cRot="
                            f"{element.beam_center_ratio:g}; expected 0..1.",
                            "element",
                            tag,
                            "Set the center-of-rotation ratio cRot in 0..1.",
                        )
                    )
            elif (
                element.element_type
                in {"forceBeamColumn", "dispBeamColumn"}
                and element.integration_points < 2
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Beam integration",
                        f"Element {tag} needs at least 2 integration points.",
                        "element",
                        tag,
                        "Increase the integration-point count.",
                    )
                )

        if element.transf_tag is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Transformation",
                    f"Element {tag} has no geometric transformation assigned.",
                    "element",
                    tag,
                    "Assign a transformation before running.",
                )
            )
            continue

        transformation = project.transformations.get(element.transf_tag)
        if transformation is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Transformation",
                    f"Element {tag} references missing transformation "
                    f"{element.transf_tag}.",
                    "element",
                    tag,
                    "Assign an existing transformation.",
                )
            )
            continue

        if (
            element.element_type == "dispBeamColumnInt"
            and transformation.transformation_type != "LinearInt"
        ):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Transformation",
                    f"dispBeamColumnInt element {tag} requires a LinearInt "
                    f"transformation; got {transformation.transformation_type}.",
                    "element",
                    tag,
                    "Assign a LinearInt geometric transformation.",
                )
            )
            continue
        if (
            element.element_type != "dispBeamColumnInt"
            and transformation.transformation_type == "LinearInt"
        ):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Transformation",
                    f"LinearInt transformation {transformation.tag} is reserved "
                    "for dispBeamColumnInt elements.",
                    "element",
                    tag,
                    "Use Linear/PDelta/Corotational for this frame formulation.",
                )
            )
            continue

        if length <= 1.0e-12:
            continue

        try:
            vecxz = resolve_transformation_vecxz(model, transformation)
        except ValueError as exc:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Transformation orientation",
                    f"Element {tag}: {exc}",
                    "element",
                    tag,
                    "Use separate Auto transformations for incompatible "
                    "member direction families, or switch to Manual.",
                )
            )
            continue
        sine = _norm(_cross(axis, vecxz)) / (length * _norm(vecxz))
        if sine <= 1.0e-8:
            suggested = _suggest_vecxz(axis)
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Transformation orientation",
                    f"Element {tag}: transformation {transformation.tag} "
                    f"vecxz={_format_vector(vecxz)} is parallel to the "
                    "element axis.",
                    "element",
                    tag,
                    f"Suggested vecxz: {_format_vector(suggested)}.",
                )
            )
        elif sine <= 1.0e-3:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Transformation orientation",
                    f"Element {tag}: transformation {transformation.tag} is "
                    "nearly parallel to the element axis.",
                    "element",
                    tag,
                    f"Consider vecxz={_format_vector(_suggest_vecxz(axis))}.",
                )
            )


    for edge, owners in sorted(shell_edge_owners.items()):
        if len(owners) > 2:
            owner_tags = ", ".join(str(item[0]) for item in owners)
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Shell topology",
                    f"Shell edge {edge[0]}-{edge[1]} is shared by "
                    f"{len(owners)} elements ({owner_tags}).",
                    "element",
                    owners[0][0],
                    "Check for overlapping or non-manifold shell surfaces.",
                )
            )
        if len(owners) < 2:
            continue

        reference = owners[0]
        for neighbour in owners[1:]:
            same_direction = (
                reference[1] == neighbour[1]
                and reference[2] == neighbour[2]
            )
            if not same_direction:
                continue
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Shell orientation",
                    f"Shell elements {reference[0]} and {neighbour[0]} "
                    f"traverse shared edge {edge[0]}-{edge[1]} in the same "
                    "direction; their surface normals are inconsistent.",
                    "element",
                    neighbour[0],
                    "Reverse one shell orientation so adjacent elements "
                    "traverse their shared edge in opposite directions.",
                )
            )


    if len(shell_node_tags) > 1:
        shell_nodes = [
            model.nodes[tag]
            for tag in sorted(shell_node_tags)
            if tag in model.nodes
        ]
        if shell_nodes:
            xs = [float(node.xyz[0]) for node in shell_nodes]
            ys = [float(node.xyz[1]) for node in shell_nodes]
            zs = [float(node.xyz[2]) for node in shell_nodes]
            span = max(
                max(xs) - min(xs),
                max(ys) - min(ys),
                max(zs) - min(zs),
                1.0,
            )
            tolerance = 1.0e-9 * span
            tolerance2 = tolerance * tolerance
            buckets: dict[
                tuple[int, int, int],
                list[int],
            ] = {}
            reported_pairs: set[tuple[int, int]] = set()

            def spatial_key(
                xyz: tuple[float, float, float],
            ) -> tuple[int, int, int]:
                return tuple(
                    int(round(float(value) / tolerance))
                    for value in xyz
                )

            for node in shell_nodes:
                base = spatial_key(node.xyz)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            for other_tag in buckets.get(
                                (
                                    base[0] + dx,
                                    base[1] + dy,
                                    base[2] + dz,
                                ),
                                (),
                            ):
                                if other_tag == node.tag:
                                    continue
                                other = model.nodes.get(other_tag)
                                if other is None:
                                    continue
                                distance2 = sum(
                                    (
                                        float(node.xyz[index])
                                        - float(other.xyz[index])
                                    ) ** 2
                                    for index in range(3)
                                )
                                if distance2 > tolerance2:
                                    continue
                                pair = tuple(
                                    sorted((int(node.tag), int(other_tag)))
                                )
                                if pair in reported_pairs:
                                    continue
                                reported_pairs.add(pair)
                                issues.append(
                                    ValidationIssue(
                                        "WARNING",
                                        "Shell connectivity",
                                        f"Shell nodes {pair[0]} and {pair[1]} "
                                        "are coincident but use different "
                                        "node tags.",
                                        "node",
                                        pair[0],
                                        "Run Surfaces → Stitch Coincident "
                                        "Shell Nodes when these patches "
                                        "should be structurally continuous.",
                                    )
                                )
                buckets.setdefault(base, []).append(int(node.tag))

        # Detect shell T-junctions: a node used by one shell lies on the
        # interior of another shell's edge without being part of that edge.
        # This is the typical signature of non-conforming adjacent meshes.
        shell_points = {
            int(tag): tuple(
                float(value) for value in model.nodes[tag].xyz
            )
            for tag in shell_node_tags
            if tag in model.nodes
        }
        hanging_reported: set[tuple[int, int, int]] = set()
        for edge, owners in sorted(shell_edge_owners.items()):
            if edge[0] not in shell_points or edge[1] not in shell_points:
                continue
            a = shell_points[edge[0]]
            b = shell_points[edge[1]]
            ab = tuple(
                b[index] - a[index]
                for index in range(3)
            )
            length2 = sum(value * value for value in ab)
            if length2 <= tolerance2:
                continue
            for node_tag, point in shell_points.items():
                if node_tag in edge:
                    continue
                ap = tuple(
                    point[index] - a[index]
                    for index in range(3)
                )
                t = sum(
                    ap[index] * ab[index]
                    for index in range(3)
                ) / length2
                if t <= 1.0e-8 or t >= 1.0 - 1.0e-8:
                    continue
                closest = tuple(
                    a[index] + t * ab[index]
                    for index in range(3)
                )
                distance2 = sum(
                    (
                        point[index] - closest[index]
                    ) ** 2
                    for index in range(3)
                )
                if distance2 > tolerance2:
                    continue
                key = (edge[0], edge[1], int(node_tag))
                if key in hanging_reported:
                    continue
                hanging_reported.add(key)
                owner_tags = ", ".join(
                    str(owner[0]) for owner in owners
                )
                issues.append(
                    ValidationIssue(
                        "WARNING",
                        "Shell conformity",
                        f"Shell node {node_tag} lies on the interior of "
                        f"edge {edge[0]}-{edge[1]} used by element(s) "
                        f"{owner_tags}, but is not connected to that edge.",
                        "node",
                        int(node_tag),
                        "Use conforming edge divisions or remesh adjacent "
                        "patches so both sides share the same edge nodes.",
                    )
                )


def _support_and_connectivity_checks(
    project: ProjectDatabase,
    issues: list[ValidationIssue],
) -> None:
    model = project.model
    support_nodes = {
        tag
        for tag, node in model.nodes.items()
        if any(node.fixity)
    }
    if (model.elements or project.connections) and not support_nodes:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Stability",
                "The structural model has no restrained/support node.",
                suggestion="Add at least one physically appropriate support.",
            )
        )

    adjacency: dict[int, set[int]] = {
        tag: set() for tag in model.nodes
    }
    active_nodes: set[int] = set()

    def connect(a: int, b: int) -> None:
        if a not in adjacency or b not in adjacency:
            return
        adjacency[a].add(b)
        adjacency[b].add(a)
        active_nodes.update((a, b))

    for element in model.elements.values():
        node_tags = element.node_tags()
        if element.element_type in EMBEDDED_ELEMENT_TYPES:
            for retained in (element.j, element.k, element.l):
                if retained is not None:
                    connect(element.i, retained)
        elif (
            element.element_type in SHELL_ELEMENT_TYPES
            or element.element_type == "MEFI"
        ):
            for left, right in zip(
                node_tags,
                node_tags[1:] + node_tags[:1],
            ):
                connect(left, right)
        else:
            connect(element.i, element.j)
    for connection in project.connections.values():
        connect(connection.node_i, connection.node_j)
    for constraint in project.constraints.values():
        for constrained in constraint.constrained_nodes:
            connect(constraint.retained_node, constrained)

    isolated = sorted(
        tag
        for tag in model.nodes
        if not adjacency[tag] and tag not in support_nodes
    )
    if isolated:
        preview = ", ".join(map(str, isolated[:8]))
        suffix = "..." if len(isolated) > 8 else ""
        issues.append(
            ValidationIssue(
                "WARNING",
                "Connectivity",
                f"{len(isolated)} isolated node(s) are not connected to the "
                f"structural model: {preview}{suffix}",
                "node",
                isolated[0],
                "Delete unused nodes or connect them intentionally.",
            )
        )

    unseen = set(active_nodes)
    components: list[set[int]] = []
    while unseen:
        seed = unseen.pop()
        stack = [seed]
        component = {seed}
        while stack:
            current = stack.pop()
            for neighbour in adjacency[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    component.add(neighbour)
                    stack.append(neighbour)
        components.append(component)

    unsupported_components = [
        component
        for component in components
        if not (component & support_nodes)
    ]
    for component in unsupported_components:
        representative = min(component)
        issues.append(
            ValidationIssue(
                "ERROR",
                "Stability",
                f"Structural component containing node {representative} "
                "has no path to a restrained node.",
                "node",
                representative,
                "Connect this component to the supported structure or add "
                "appropriate restraints.",
            )
        )

    supported_components = [
        component
        for component in components
        if component & support_nodes
    ]
    if len(supported_components) > 1:
        representatives = sorted(min(component) for component in supported_components)
        issues.append(
            ValidationIssue(
                "WARNING",
                "Connectivity",
                f"The model contains {len(supported_components)} disconnected "
                f"supported structural components (e.g. nodes "
                f"{', '.join(map(str, representatives[:6]))}).",
                "node",
                representatives[0],
                "Confirm that independent structural components are intentional.",
            )
        )


def _prescribed_displacement_checks(
    project: ProjectDatabase,
    issues: list[ValidationIssue],
) -> None:
    seen: dict[tuple[int, int], int] = {}
    for tag in sorted(project.prescribed_displacements):
        displacement = project.prescribed_displacements[tag]
        node = project.model.nodes.get(displacement.node_tag)
        if node is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Prescribed displacement",
                    f"Prescribed displacement {tag} references missing node "
                    f"{displacement.node_tag}.",
                    "node",
                    displacement.node_tag,
                    "Reassign or delete the prescribed displacement.",
                )
            )
            continue

        pattern = project.load_patterns.get(displacement.pattern_tag)
        if pattern is None or pattern.pattern_type != "Plain":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Prescribed displacement",
                    f"Prescribed displacement {tag} must belong to a Plain "
                    "load pattern.",
                    "node",
                    node.tag,
                    "Assign it to an existing Plain load pattern.",
                )
            )

        if displacement.dof > project.model.ndf:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Prescribed displacement",
                    f"Prescribed displacement {tag} uses unavailable DOF "
                    f"{displacement.dof} for ndf={project.model.ndf}.",
                    "node",
                    node.tag,
                    "Choose a DOF available in the current model.",
                )
            )
            continue

        if bool(node.fixity[displacement.dof - 1]):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Prescribed displacement",
                    f"Node {node.tag} DOF {displacement.dof} is both "
                    "restrained and prescribed.",
                    "node",
                    node.tag,
                    "Clear the support restraint on this DOF or delete the "
                    "prescribed displacement.",
                )
            )

        key = (node.tag, displacement.dof)
        if key in seen:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Prescribed displacement",
                    f"Node {node.tag} DOF {displacement.dof} has multiple "
                    "prescribed displacement objects.",
                    "node",
                    node.tag,
                    "Keep only one imposed displacement per node/DOF.",
                )
            )
        else:
            seen[key] = tag


def _element_load_checks(
    project: ProjectDatabase,
    issues: list[ValidationIssue],
) -> None:
    for tag in sorted(project.element_loads):
        load = project.element_loads[tag]
        element = project.model.elements.get(load.element_tag)
        if element is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Element load",
                    f"Element load {load.tag} references missing element "
                    f"{load.element_tag}.",
                    suggestion="Reassign or delete the element load.",
                )
            )
            continue

        pattern = project.load_patterns.get(load.pattern_tag)
        if pattern is None or pattern.pattern_type != "Plain":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Element load",
                    f"Element load {load.tag} must belong to a Plain load "
                    "pattern.",
                    "element",
                    element.tag,
                    "Assign the load to an existing Plain load pattern.",
                )
            )

        transformation = (
            project.transformations.get(element.transf_tag)
            if element.transf_tag is not None
            else None
        )
        if (
            transformation is not None
            and transformation.transformation_type == "Corotational"
        ):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Element load",
                    f"Element load {load.tag} is assigned to element "
                    f"{element.tag} using a Corotational transformation. "
                    "OpenSees 3D beam eleLoad is not supported with this "
                    "transformation.",
                    "element",
                    element.tag,
                    "Use Linear/PDelta for loaded 3D beam-column elements.",
                )
            )

        if load.load_type == "SelfWeight":
            try:
                resolve_self_weight_local(
                    load,
                    project.model,
                    project.sections,
                    project.materials,
                    project.transformations,
                    project.units,
                )
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Self weight",
                        str(exc),
                        "element",
                        element.tag,
                        "Link an Elastic section to a material with positive "
                        "density, or provide a density override.",
                    )
                )


def _analysis_control_checks(
    project: ProjectDatabase,
    analysis: AnalysisSettingsData,
    issues: list[ValidationIssue],
) -> None:
    if analysis.integrator != "DisplacementControl":
        return

    node = project.model.nodes.get(int(analysis.control_node))
    if node is None:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Analysis control",
                f"{analysis.analysis_type} DisplacementControl references "
                f"missing control node {analysis.control_node}.",
                "node",
                int(analysis.control_node),
                "Choose an existing free control node before running.",
            )
        )
        return

    dof = int(analysis.control_dof)
    if dof < 1 or dof > int(project.model.ndf):
        issues.append(
            ValidationIssue(
                "ERROR",
                "Analysis control",
                f"{analysis.analysis_type} DisplacementControl uses control "
                f"DOF {dof}, but the model has ndf={project.model.ndf}.",
                "node",
                node.tag,
                "Choose a control DOF available in the current model.",
            )
        )
        return

    if bool(node.fixity[dof - 1]):
        issues.append(
            ValidationIssue(
                "ERROR",
                "Analysis control",
                f"Control node {node.tag} DOF {dof} is restrained, so "
                "DisplacementControl cannot advance that degree of freedom.",
                "node",
                node.tag,
                "Use a free control DOF or remove the support restraint.",
            )
        )


def _element_load_has_nonzero_reference(load) -> bool:
    tolerance = 1.0e-15
    if load.load_type == "Uniform":
        values = (load.wx, load.wy, load.wz)
    elif load.load_type in {"Triangular", "Trapezoidal"}:
        values = (
            load.wx, load.wy, load.wz,
            load.wx_end, load.wy_end, load.wz_end,
        )
    elif load.load_type == "Point":
        values = (load.px, load.py, load.pz)
    elif load.load_type == "SelfWeight":
        values = load.gravity
    elif load.load_type == "SurfacePressure":
        values = (load.pressure,)
    else:
        return False
    return any(abs(float(value)) > tolerance for value in values)


def _pattern_has_nonzero_force_reference(
    project: ProjectDatabase,
    pattern_tag: int,
) -> bool:
    tag = int(pattern_tag)
    if any(
        load.pattern_tag == tag
        and any(abs(float(value)) > 1.0e-15 for value in load.values)
        for load in project.nodal_loads.values()
    ):
        return True
    return any(
        load.pattern_tag == tag
        and _element_load_has_nonzero_reference(load)
        for load in project.element_loads.values()
    )


def _driving_load_checks(
    project: ProjectDatabase,
    analysis: AnalysisSettingsData,
    issues: list[ValidationIssue],
) -> None:
    static_dc = (
        analysis.analysis_type == "Static"
        and analysis.integrator == "DisplacementControl"
    )
    if analysis.analysis_type not in {"Pushover", "Cyclic"} and not static_dc:
        return

    driver_tags = [int(tag) for tag in analysis.deferred_pattern_tags]
    if not driver_tags and static_dc:
        # Backward compatibility for older/manual Static DisplacementControl
        # analyses that predate explicit driver ownership.
        driver_tags = [
            int(tag)
            for tag, pattern in project.load_patterns.items()
            if (
                pattern.pattern_type == "Plain"
                and _pattern_has_nonzero_force_reference(project, int(tag))
                and not any(
                    item.pattern_tag == int(tag)
                    for item in project.prescribed_displacements.values()
                )
            )
        ]
        if driver_tags:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Driving load",
                    "Static DisplacementControl uses unscoped project Plain "
                    "load pattern(s) as its force reference.",
                    suggestion=(
                        "Edit Analysis Settings and choose an explicit Driving "
                        "Load so the analysis is isolated from unrelated loads."
                    ),
                )
            )

    if not driver_tags:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Driving load",
                f"{analysis.analysis_type} DisplacementControl has no "
                "nonzero driving/reference force pattern.",
                suggestion=(
                    "Edit Analysis Settings and use Auto-generate reference "
                    "pattern, or select an existing nonzero Plain pattern."
                ),
            )
        )
        return

    for tag in driver_tags:
        pattern = project.load_patterns.get(int(tag))
        if pattern is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Driving load",
                    f"{analysis.analysis_type} analysis references missing "
                    f"driving pattern {tag}.",
                    suggestion="Select or auto-generate a valid Plain pattern.",
                )
            )
            continue
        if pattern.pattern_type != "Plain":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Driving load",
                    f"Driving pattern {tag} is {pattern.pattern_type}; "
                    "DisplacementControl requires a Plain reference-load "
                    "pattern.",
                    suggestion="Use a Plain force pattern as the driver.",
                )
            )
            continue

        nodal_reference_loads = [
            load
            for load in project.nodal_loads.values()
            if (
                load.pattern_tag == int(tag)
                and any(
                    abs(float(value)) > 1.0e-15
                    for value in load.values
                )
            )
        ]
        element_reference_loads = [
            load
            for load in project.element_loads.values()
            if (
                load.pattern_tag == int(tag)
                and _element_load_has_nonzero_reference(load)
            )
        ]
        has_nodal_reference = bool(nodal_reference_loads)
        has_element_reference = bool(element_reference_loads)
        if not has_nodal_reference and not has_element_reference:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Driving load",
                    f"Driving pattern {tag} contains no nonzero reference "
                    "force load.",
                    suggestion=(
                        "Auto-generate the reference pattern or add a nonzero "
                        "nodal/element load to the selected Plain pattern."
                    ),
                )
            )

        if any(
            item.pattern_tag == int(tag)
            for item in project.prescribed_displacements.values()
        ):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Driving load",
                    f"Driving pattern {tag} contains Prescribed Displacement "
                    "objects. DisplacementControl requires a force reference "
                    "pattern instead.",
                    suggestion="Move prescribed displacements to another pattern.",
                )
            )

        dof_index = int(analysis.control_dof) - 1
        if (
            has_nodal_reference
            and not has_element_reference
            and 0 <= dof_index < int(project.model.ndf)
            and not any(
                dof_index < len(load.values)
                and abs(float(load.values[dof_index])) > 1.0e-15
                for load in nodal_reference_loads
            )
        ):
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Driving load",
                    f"Driving pattern {tag} has no direct nodal force in "
                    f"control DOF {analysis.control_dof}.",
                    suggestion=(
                        "Confirm that structural coupling is intentional, or "
                        "use a reference force aligned with the control DOF."
                    ),
                )
            )


def _shell_section_has_mass(
    project: ProjectDatabase,
    section,
) -> bool:
    if section is None:
        return False
    if section.section_type == "ElasticMembranePlate":
        return float(section.parameters.get("rho", 0.0)) > 0.0
    if section.section_type == "PlateFiber":
        if section.nd_material_tag is None:
            return False
        material = project.nd_materials.get(int(section.nd_material_tag))
        return bool(
            material is not None
            and float(material.parameters.get("rho", 0.0)) > 0.0
        )
    if section.section_type == "LayeredShell":
        return any(
            (
                project.nd_materials.get(int(layer.material_tag)) is not None
                and float(
                    project.nd_materials[
                        int(layer.material_tag)
                    ].parameters.get("rho", 0.0)
                ) > 0.0
            )
            for layer in section.shell_layers
        )
    return False


def _node_has_incident_element_mass(
    project: ProjectDatabase,
    node_tag: int,
) -> bool:
    target = int(node_tag)
    for element in project.model.elements.values():
        if target not in element.node_tags():
            continue
        if float(element.mass_per_length) > 0.0:
            return True
        if element.element_type in SHELL_ELEMENT_TYPES:
            section = project.sections.get(
                int(element.section_tag)
                if element.section_tag is not None
                else -1
            )
            if (
                section is not None
                and section.section_type in SHELL_SECTION_TYPES
                and _shell_section_has_mass(project, section)
            ):
                return True
    return False


def _has_dynamic_mass_in_direction(
    project: ProjectDatabase,
    dof: int,
) -> bool:
    index = int(dof) - 1
    if index < 0 or index >= int(project.model.ndf):
        return False

    for node in project.model.nodes.values():
        if (
            index < len(node.fixity)
            and not bool(node.fixity[index])
            and index < len(node.mass)
            and float(node.mass[index]) > 0.0
        ):
            return True

    for element in project.model.elements.values():
        has_element_mass = float(element.mass_per_length) > 0.0
        if element.element_type in SHELL_ELEMENT_TYPES:
            section = project.sections.get(
                int(element.section_tag)
                if element.section_tag is not None
                else -1
            )
            has_element_mass = has_element_mass or bool(
                section is not None
                and section.section_type in SHELL_SECTION_TYPES
                and _shell_section_has_mass(project, section)
            )
        if not has_element_mass:
            continue
        for node_tag in element.node_tags():
            node = project.model.nodes.get(int(node_tag))
            if (
                node is not None
                and index < len(node.fixity)
                and not bool(node.fixity[index])
            ):
                return True
    return False


def _has_any_translational_dynamic_mass(
    project: ProjectDatabase,
) -> bool:
    return any(
        _has_dynamic_mass_in_direction(project, dof)
        for dof in range(1, int(project.model.ndm) + 1)
    )


def _dynamic_checks(
    project: ProjectDatabase,
    analysis: AnalysisSettingsData,
    issues: list[ValidationIssue],
) -> None:
    if analysis.analysis_type not in {"Transient", "Modal"}:
        return

    model = project.model
    has_any_mass = _has_any_translational_dynamic_mass(project)
    if not has_any_mass:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Mass",
                f"{analysis.analysis_type} analysis has no positive "
                "translational nodal or element mass on a free DOF.",
                suggestion=(
                    "Assign nodal mass, generate mass from a Mass Source, "
                    "or assign positive element mass/length before dynamic "
                    "or modal analysis."
                ),
            )
        )
    else:
        translational_count = min(int(model.ndm), int(model.ndf), 3)
        zero_mass_free_nodes = [
            tag
            for tag, node in model.nodes.items()
            if any(
                not bool(node.fixity[index])
                for index in range(translational_count)
            )
            and not any(
                (
                    not bool(node.fixity[index])
                    and float(node.mass[index]) > 0.0
                )
                for index in range(translational_count)
            )
            and not _node_has_incident_element_mass(project, tag)
        ]
        if zero_mass_free_nodes:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Mass",
                    f"{len(zero_mass_free_nodes)} free node(s) have no "
                    "direct nodal mass and are not connected to an element "
                    "with positive mass/length.",
                    "node",
                    zero_mass_free_nodes[0],
                    "Confirm that the mass distribution is intentional.",
                )
            )

    # Modal analysis does not consume excitation patterns. Stale or incomplete
    # ground motions elsewhere in the project must not block an eigen solve.
    if analysis.analysis_type != "Transient":
        return

    if analysis.deferred_pattern_tags:
        candidate_tags = [int(tag) for tag in analysis.deferred_pattern_tags]
        patterns = []
        for tag in candidate_tags:
            pattern = project.load_patterns.get(tag)
            if pattern is None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Ground motion",
                        f"Transient analysis references missing excitation "
                        f"pattern {tag}.",
                        suggestion=(
                            "Edit the analysis and assign an existing "
                            "UniformExcitation ground-motion pattern."
                        ),
                    )
                )
                continue
            patterns.append(pattern)
    else:
        # Legacy/manual transient analyses without explicit ownership retain
        # the historical behavior of validating all UniformExcitation loads.
        patterns = [
            pattern
            for pattern in project.load_patterns.values()
            if pattern.pattern_type == "UniformExcitation"
        ]

    for pattern in patterns:
        if pattern.pattern_type != "UniformExcitation":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Ground motion",
                    f"Transient excitation pattern {pattern.tag} is "
                    f"{pattern.pattern_type}; NLTH excitation must use "
                    "UniformExcitation.",
                    suggestion=(
                        "Assign a UniformExcitation pattern backed by a "
                        "Path acceleration time series."
                    ),
                )
            )
            continue

        series = project.time_series.get(pattern.time_series_tag)
        if series is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Ground motion",
                    f"UniformExcitation pattern {pattern.tag} references "
                    f"missing time series {pattern.time_series_tag}.",
                    suggestion="Assign a valid acceleration time series.",
                )
            )
            continue
        if series.series_type != "Path":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Ground motion",
                    f"UniformExcitation pattern {pattern.tag} must use a "
                    f"Path time series, not {series.series_type}.",
                    suggestion=(
                        "Use Loading > Ground Motions to define an "
                        "acceleration record."
                    ),
                )
            )
            continue
        if series.dt <= 0.0 or not series.values:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Ground motion",
                    f"Path time series {series.tag} used by "
                    f"UniformExcitation pattern {pattern.tag} has no "
                    "usable ground-motion data.",
                    suggestion="Provide positive dt and acceleration values.",
                )
            )
        if pattern.direction < 1 or pattern.direction > model.ndm:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Ground motion",
                    f"UniformExcitation pattern {pattern.tag} uses "
                    f"translational direction {pattern.direction}, but the "
                    f"model has ndm={model.ndm}.",
                    suggestion=(
                        "Choose a global translational excitation direction "
                        "supported by the model geometry."
                    ),
                )
            )

    active_directions = sorted({
        int(pattern.direction)
        for pattern in patterns
        if (
            pattern.pattern_type == "UniformExcitation"
            and 1 <= int(pattern.direction) <= int(model.ndm)
        )
    })
    if has_any_mass:
        for direction in active_directions:
            if _has_dynamic_mass_in_direction(project, direction):
                continue
            axis = {1: "X", 2: "Y", 3: "Z"}.get(
                direction,
                f"DOF {direction}",
            )
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Mass",
                    f"Transient excitation is active in {axis}, but the "
                    f"model has no positive dynamic mass on a free "
                    f"{axis} translational DOF.",
                    suggestion=(
                        f"Assign/generate mass in {axis} or remove the "
                        f"{axis} excitation component."
                    ),
                )
            )



def _recorder_checks(
    project: ProjectDatabase,
    issues: list[ValidationIssue],
) -> None:
    for tag in sorted(project.recorders):
        recorder = project.recorders[tag]
        try:
            project._validate_recorder(recorder)
        except ValueError as exc:
            entity_kind = (
                "node" if recorder.recorder_type == "Node" else "element"
            )
            entity_tag = recorder.target_tags[0] if recorder.target_tags else None
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Recorder",
                    f"Recorder {tag} ({recorder.name}): {exc}",
                    entity_kind,
                    entity_tag,
                    "Edit or remove the recorder before running.",
                )
            )


def validate_project(
    project: ProjectDatabase,
    analysis: AnalysisSettingsData | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    try:
        UnitSystem.from_mapping(project.units)
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Units",
                str(exc),
                suggestion=(
                    "Use a supported consistent model unit system before "
                    "running the analysis."
                ),
            )
        )

    if not project.model.nodes:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Geometry",
                "The model contains no nodes.",
                suggestion="Create or generate structural geometry first.",
            )
        )
        return issues

    _element_geometry_checks(project, issues)
    _support_and_connectivity_checks(project, issues)
    _prescribed_displacement_checks(project, issues)
    _element_load_checks(project, issues)
    _recorder_checks(project, issues)

    if analysis is not None:
        _analysis_control_checks(project, analysis, issues)
        _driving_load_checks(project, analysis, issues)
        _dynamic_checks(project, analysis, issues)

    severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    return sorted(
        issues,
        key=lambda issue: (
            severity_order[issue.severity],
            issue.category,
            issue.entity_tag if issue.entity_tag is not None else -1,
            issue.message,
        ),
    )
