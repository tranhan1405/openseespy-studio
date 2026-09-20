from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .beam_loads import resolve_self_weight_local
from .project import AnalysisSettingsData, ProjectDatabase
from .units import UnitSystem


FRAME_ELEMENT_TYPES = {
    "elasticBeamColumn",
    "forceBeamColumn",
    "dispBeamColumn",
}
SUPPORTED_ELEMENT_TYPES = {
    "elasticBeamColumn",
    "forceBeamColumn",
    "dispBeamColumn",
    "truss",
}


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


def _element_geometry_checks(
    project: ProjectDatabase,
    issues: list[ValidationIssue],
) -> None:
    model = project.model
    seen_pairs: dict[tuple[int, int], int] = {}

    for tag in sorted(model.elements):
        element = model.elements[tag]
        node_i = model.nodes.get(element.i)
        node_j = model.nodes.get(element.j)
        if node_i is None or node_j is None:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Geometry",
                    f"Element {tag} references a missing node.",
                    "element",
                    tag,
                    "Repair or recreate the element connectivity.",
                )
            )
            continue

        axis = tuple(
            node_j.xyz[index] - node_i.xyz[index]
            for index in range(3)
        )
        length = _norm(axis)
        if length <= 1.0e-12:
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

        pair = tuple(sorted((element.i, element.j)))
        if pair in seen_pairs:
            other = seen_pairs[pair]
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Geometry",
                    f"Element {tag} duplicates the node pair of element {other}.",
                    "element",
                    tag,
                    "Confirm that the duplicate member is intentional.",
                )
            )
        else:
            seen_pairs[pair] = tag

        if element.element_type not in SUPPORTED_ELEMENT_TYPES:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Element formulation",
                    f"Element {tag} uses {element.element_type}, which the "
                    "current generator does not yet emit faithfully.",
                    "element",
                    tag,
                    "Use elasticBeamColumn for now or wait for the dedicated "
                    "formulation generator.",
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
                element.element_type == "elasticBeamColumn"
                and section.section_type != "Elastic"
            ):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "Element formulation",
                        f"elasticBeamColumn element {tag} cannot use "
                        f"{section.section_type} section {section.tag} in the "
                        "current Studio generator.",
                        "element",
                        tag,
                        "Use an Elastic section, or switch the element to "
                        "forceBeamColumn / dispBeamColumn for Fiber sections.",
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

        if length <= 1.0e-12:
            continue

        if int(model.ndm) == 3:
            vecxz = transformation.vecxz
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
            int(project.model.ndm) == 3
            and transformation is not None
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


def _driving_load_checks(
    project: ProjectDatabase,
    analysis: AnalysisSettingsData,
    issues: list[ValidationIssue],
) -> None:
    if analysis.analysis_type not in {"Pushover", "Cyclic"}:
        return

    driver_tags = list(analysis.deferred_pattern_tags)
    if not driver_tags:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Driving load",
                f"{analysis.analysis_type} analysis has no driving/reference "
                "load pattern.",
                suggestion=(
                    "Edit Analysis Settings and use Auto-generate reference "
                    "pattern, or select an existing Plain pattern."
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
                    "Pushover/Cyclic require a Plain reference-load pattern.",
                    suggestion="Use a Plain force pattern as the driver.",
                )
            )
            continue

        has_nodal_reference = any(
            load.pattern_tag == int(tag)
            and any(abs(float(value)) > 1.0e-15 for value in load.values)
            for load in project.nodal_loads.values()
        )
        has_element_reference = any(
            load.pattern_tag == int(tag)
            for load in project.element_loads.values()
        )
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


def _dynamic_checks(
    project: ProjectDatabase,
    analysis: AnalysisSettingsData,
    issues: list[ValidationIssue],
) -> None:
    if analysis.analysis_type not in {"Transient", "Modal"}:
        return

    model = project.model
    translational_mass = sum(
        sum(max(0.0, float(value)) for value in node.mass[:3])
        for node in model.nodes.values()
    )
    if translational_mass <= 0.0:
        issues.append(
            ValidationIssue(
                "ERROR",
                "Mass",
                f"{analysis.analysis_type} analysis has no positive "
                "translational nodal mass.",
                suggestion="Assign UX/UY/UZ nodal masses before dynamic "
                "or modal analysis.",
            )
        )
    else:
        zero_mass_free_nodes = [
            tag
            for tag, node in model.nodes.items()
            if any(value == 0 for value in node.fixity[:3])
            and sum(max(0.0, float(value)) for value in node.mass[:3]) <= 0.0
        ]
        if zero_mass_free_nodes:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "Mass",
                    f"{len(zero_mass_free_nodes)} free node(s) have zero "
                    "translational mass.",
                    "node",
                    zero_mass_free_nodes[0],
                    "Confirm that the mass distribution is intentional.",
                )
            )

    for pattern in project.load_patterns.values():
        if pattern.pattern_type != "UniformExcitation":
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
        if pattern.direction > model.ndf:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "Ground motion",
                    f"UniformExcitation pattern {pattern.tag} uses DOF "
                    f"{pattern.direction}, but the model has ndf={model.ndf}.",
                    suggestion="Choose an excitation direction supported by the model.",
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
