from __future__ import annotations

from typing import Any

from .model import StructuralModel


SECTION_COMPONENTS_2D: dict[str, dict[str, object]] = {
    "P": {
        "index": 0,
        "force_label": "Axial force P",
        "deformation_label": "Axial strain ε",
        "pair_label": "P–ε",
    },
    "Mz": {
        "index": 1,
        "force_label": "Moment Mz",
        "deformation_label": "Curvature κz",
        "pair_label": "Mz–κz",
    },
}

SECTION_COMPONENTS_3D: dict[str, dict[str, object]] = {
    "P": {
        "index": 0,
        "force_label": "Axial force P",
        "deformation_label": "Axial strain ε",
        "pair_label": "P–ε",
    },
    "Mz": {
        "index": 1,
        "force_label": "Moment Mz",
        "deformation_label": "Curvature κz",
        "pair_label": "Mz–κz",
    },
    "My": {
        "index": 2,
        "force_label": "Moment My",
        "deformation_label": "Curvature κy",
        "pair_label": "My–κy",
    },
    "T": {
        "index": 3,
        "force_label": "Torsion T",
        "deformation_label": "Twist rate θ′",
        "pair_label": "T–θ′",
    },
}


def section_component_catalog(ndm: int) -> dict[str, dict[str, object]]:
    """Return semantic section-resultant pairs for the current model dimension.

    OpenSees standard 2D frame sections use [P, Mz]. Standard 3D frame
    sections use [P, Mz, My, T].  Keep these semantics centralized instead of
    scattering hard-coded indices through plotting and generator code.
    """
    source = SECTION_COMPONENTS_2D if int(ndm) == 2 else SECTION_COMPONENTS_3D
    return {name: dict(values) for name, values in source.items()}


def section_response_sources(
    model: StructuralModel,
    connections: dict[int, Any] | None = None,
) -> list[dict[str, object]]:
    """Describe model objects that expose meaningful section responses."""
    components = tuple(section_component_catalog(model.ndm))
    sources: list[dict[str, object]] = []

    for tag in sorted(model.elements):
        element = model.elements[tag]
        if element.element_type not in {"forceBeamColumn", "dispBeamColumn"}:
            continue
        section_tag = element.section_tag
        if section_tag is None:
            continue
        count = max(1, int(element.integration_points))
        sources.append({
            "element_tag": int(tag),
            "element_kind": str(element.element_type),
            "section_tag": (
                int(section_tag) if section_tag is not None else None
            ),
            "query_mode": "indexed",
            "locations": list(range(1, count + 1)),
            "components": list(components),
        })

    for tag in sorted(connections or {}):
        connection = (connections or {})[tag]
        if (
            connection.connection_type != "zeroLengthSection"
            or connection.section_tag is None
        ):
            continue
        sources.append({
            "element_tag": int(tag),
            "element_kind": "zeroLengthSection",
            "section_tag": int(connection.section_tag),
            "query_mode": "direct",
            "locations": [1],
            "components": list(components),
        })

    return sources


def section_response_source(
    model: StructuralModel,
    connections: dict[int, Any] | None,
    element_tag: int,
) -> dict[str, object] | None:
    target = int(element_tag)
    return next(
        (
            source
            for source in section_response_sources(model, connections)
            if int(source["element_tag"]) == target
        ),
        None,
    )


def validate_section_response_request(
    model: StructuralModel,
    connections: dict[int, Any] | None,
    *,
    element_tag: int,
    section_number: int = 1,
    component: str = "Mz",
) -> dict[str, object]:
    """Validate and normalize one section-response request."""
    source = section_response_source(model, connections, int(element_tag))
    if source is None:
        raise ValueError(
            f"Element {element_tag} does not expose a supported section "
            "force/deformation response."
        )

    component = str(component)
    catalog = section_component_catalog(model.ndm)
    if component not in catalog:
        available = ", ".join(catalog)
        raise ValueError(
            f"Section component {component!r} is not available for "
            f"ndm={model.ndm}; choose one of: {available}."
        )

    section_number = int(section_number)
    locations = [int(value) for value in source.get("locations", [1])]
    if section_number not in locations:
        raise ValueError(
            f"Section/IP {section_number} is not available for element "
            f"{element_tag}; valid locations are "
            + ", ".join(map(str, locations))
            + "."
        )

    semantic = dict(catalog[component])
    return {
        **source,
        **semantic,
        "section_number": section_number,
        "component": component,
        "force_index": int(semantic["index"]),
        "deformation_index": int(semantic["index"]),
    }


def automatic_moment_curvature_spec(
    model: StructuralModel,
    *,
    connections: dict[int, Any] | None = None,
    active_analysis: Any | None = None,
) -> dict[str, object] | None:
    """Recognize the classic zeroLengthSection moment-curvature procedure."""
    if (
        active_analysis is None
        or active_analysis.analysis_type != "Static"
        or active_analysis.integrator != "DisplacementControl"
    ):
        return None

    control_node = int(active_analysis.control_node)
    control_dof = int(active_analysis.control_dof)
    if int(model.ndm) == 2 and int(model.ndf) >= 3:
        component_by_dof = {3: "Mz"}
    elif int(model.ndm) == 3 and int(model.ndf) >= 6:
        component_by_dof = {5: "My", 6: "Mz"}
    else:
        return None
    component = component_by_dof.get(control_dof)
    if component is None:
        return None

    candidates = sorted(
        (
            connection
            for connection in (connections or {}).values()
            if connection.connection_type == "zeroLengthSection"
            and connection.section_tag is not None
            and control_node in {
                int(connection.node_i),
                int(connection.node_j),
            }
        ),
        key=lambda connection: (
            0 if int(connection.node_j) == control_node else 1,
            int(connection.tag),
        ),
    )
    if not candidates:
        return None

    connection = candidates[0]
    spec = validate_section_response_request(
        model,
        connections,
        element_tag=int(connection.tag),
        section_number=1,
        component=component,
    )
    spec.update({
        "key": "auto:moment-curvature",
        "kind": "moment-curvature",
        "section_tag": int(connection.section_tag),
        "node_i": int(connection.node_i),
        "node_j": int(connection.node_j),
        "control_node": control_node,
        "control_dof": control_dof,
        "moment_component": component,
        "moment_index": int(spec["force_index"]),
        "moment_sign": 1.0,
        "include_origin": True,
        "automatic": True,
    })
    return spec


def build_section_response_specs(
    model: StructuralModel,
    *,
    connections: dict[int, Any] | None = None,
    solution_results: dict[int, Any] | None = None,
    active_analysis: Any | None = None,
) -> list[dict[str, object]]:
    """Build only the section histories needed by the active analysis.

    The automatic classic M-kappa workflow is retained. Other histories are
    opt-in through SectionResponse result requests so large models do not
    record every section at every step.
    """
    specs: list[dict[str, object]] = []
    auto = automatic_moment_curvature_spec(
        model,
        connections=connections,
        active_analysis=active_analysis,
    )
    if auto is not None:
        specs.append(auto)

    if active_analysis is None:
        return specs

    seen = {
        (
            int(spec["element_tag"]),
            int(spec.get("section_number", 1)),
            str(spec.get("component", "")),
        )
        for spec in specs
    }
    for tag in sorted(solution_results or {}):
        request = (solution_results or {})[tag]
        if (
            int(getattr(request, "analysis_tag", -1))
            != int(active_analysis.tag)
            or str(getattr(request, "result_type", "")) != "SectionResponse"
        ):
            continue

        element_scope = list(getattr(request, "element_scope", []) or [])
        if len(element_scope) != 1:
            raise ValueError(
                "SectionResponse requires exactly one element in its "
                "element scope."
            )
        settings = dict(getattr(request, "settings", {}) or {})
        normalized = validate_section_response_request(
            model,
            connections,
            element_tag=int(element_scope[0]),
            section_number=int(settings.get("section", 1)),
            component=str(settings.get("component", "Mz")),
        )
        identity = (
            int(normalized["element_tag"]),
            int(normalized["section_number"]),
            str(normalized["component"]),
        )
        if identity in seen:
            continue
        seen.add(identity)
        normalized.update({
            "key": f"request:{int(tag)}",
            "kind": "section-response",
            "request_tag": int(tag),
            "include_origin": bool(settings.get("include_origin", False)),
            "automatic": False,
        })
        specs.append(normalized)

    return specs
