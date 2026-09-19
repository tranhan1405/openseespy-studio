from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from typing import Any

from .beam_loads import resolve_self_weight_local
from .model import StructuralModel
from .project import (
    ElementLoadData,
    MaterialData,
    SectionData,
    TransformationData,
)


LOCAL_FORCE_COMPONENTS: tuple[str, ...] = (
    "N",
    "Vy",
    "Vz",
    "T",
    "My",
    "Mz",
)

LOCAL_FORCE_INDEX: dict[str, int] = {
    name: index
    for index, name in enumerate(LOCAL_FORCE_COMPONENTS)
}

# Current Studio 3D ElasticSection/FiberSection section-resultant order.
# OpenSees source uses P, Mz, My, T for both section classes.
SECTION_FORCE_INDEX: dict[str, int] = {
    "N": 0,
    "Mz": 1,
    "My": 2,
    "T": 3,
}


def local_end_actions(
    values: Sequence[float],
) -> dict[str, tuple[float, float]]:
    """Return OpenSees local nodal end actions for a 3D frame element.

    OpenSees orders the 12 local-force values by the six local DOFs at
    node I followed by the six local DOFs at node J:
    Fx, Fy, Fz, Mx, My, Mz at each end.
    """
    if len(values) < 12:
        return {}
    numeric = [float(value) for value in values[:12]]
    return {
        component: (
            numeric[index],
            numeric[index + 6],
        )
        for component, index in LOCAL_FORCE_INDEX.items()
    }


def member_end_resultants(
    values: Sequence[float],
) -> dict[str, tuple[float, float]]:
    """Convert local nodal actions to OpenSees section-resultant signs.

    The signs follow the 3D beam-column section convention used internally
    by OpenSees. The local-y shear is the one exception to the simple
    "reverse I / retain J" rule: Vy_I is retained and Vy_J is reversed.
    """
    actions = local_end_actions(values)
    if not actions:
        return {}

    result: dict[str, tuple[float, float]] = {}
    for component, (end_i, end_j) in actions.items():
        if component == "Vy":
            result[component] = (end_i, -end_j)
        else:
            result[component] = (-end_i, end_j)
    return result


def component_end_resultants(
    values: Sequence[float],
    component: str,
) -> tuple[float, float] | None:
    component = str(component)
    if component not in LOCAL_FORCE_INDEX:
        raise ValueError(
            f"Unsupported local force component: {component}"
        )
    return member_end_resultants(values).get(component)


def section_component_samples(
    section_data: dict[str, Any] | None,
    component: str,
) -> list[tuple[float, float]]:
    """Return (physical x, resultant) values captured at integration points."""
    component = str(component)
    index = SECTION_FORCE_INDEX.get(component)
    if index is None or not isinstance(section_data, dict):
        return []

    locations = section_data.get("locations", [])
    forces = section_data.get("forces", [])
    if not isinstance(locations, (list, tuple)):
        return []
    if not isinstance(forces, (list, tuple)):
        return []

    samples: list[tuple[float, float]] = []
    for location, vector in zip(locations, forces):
        if not isinstance(vector, (list, tuple)) or len(vector) <= index:
            continue
        samples.append((float(location), float(vector[index])))
    return samples


def _active_load_factor(
    load: ElementLoadData,
    load_factors: dict[str, Any] | dict[int, Any],
) -> float | None:
    if str(load.pattern_tag) in load_factors:
        return float(load_factors[str(load.pattern_tag)])
    if load.pattern_tag in load_factors:
        return float(load_factors[load.pattern_tag])
    return None


def _active_local_element_loads(
    element_tag: int,
    element_loads: dict[int, ElementLoadData],
    load_factors: dict[str, Any] | dict[int, Any],
    model: StructuralModel,
    sections: dict[int, SectionData],
    materials: dict[int, MaterialData],
    transformations: dict[int, TransformationData],
    units: dict[str, str] | None,
) -> list[dict[str, float]] | None:
    active: list[dict[str, float]] = []
    for load in sorted(element_loads.values(), key=lambda item: item.tag):
        if load.element_tag != element_tag:
            continue
        factor = _active_load_factor(load, load_factors)
        if factor is None:
            return None

        if load.load_type == "Uniform":
            active.append({
                "type": "Uniform",
                "wx": factor * load.wx,
                "wy": factor * load.wy,
                "wz": factor * load.wz,
            })
        elif load.load_type == "Point":
            active.append({
                "type": "Point",
                "px": factor * load.px,
                "py": factor * load.py,
                "pz": factor * load.pz,
                "x_over_l": load.x_over_l,
            })
        elif load.load_type == "SelfWeight":
            wx, wy, wz = resolve_self_weight_local(
                load,
                model,
                sections,
                materials,
                transformations,
                units,
            )
            active.append({
                "type": "Uniform",
                "wx": factor * wx,
                "wy": factor * wy,
                "wz": factor * wz,
            })
        else:
            return None
    return active


def _aggregate_uniform(
    active_loads: Sequence[dict[str, float]],
) -> tuple[float, float, float]:
    wx = wy = wz = 0.0
    for load in active_loads:
        if load.get("type") != "Uniform":
            continue
        wx += float(load.get("wx", 0.0))
        wy += float(load.get("wy", 0.0))
        wz += float(load.get("wz", 0.0))
    return wx, wy, wz


def _point_loads(
    active_loads: Sequence[dict[str, float]],
    length: float,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for load in active_loads:
        if load.get("type") != "Point":
            continue
        ratio = min(max(float(load.get("x_over_l", 0.0)), 0.0), 1.0)
        points.append({
            "x": ratio * length,
            "px": float(load.get("px", 0.0)),
            "py": float(load.get("py", 0.0)),
            "pz": float(load.get("pz", 0.0)),
        })
    return sorted(points, key=lambda item: item["x"])


def _resultant_at(
    local_force: Sequence[float],
    length: float,
    component: str,
    active_loads: Sequence[dict[str, float]],
    x: float,
    *,
    side: str = "right",
) -> float:
    if len(local_force) < 12:
        raise ValueError("A 12-value localForce response is required.")
    if length <= 0.0:
        raise ValueError("Element length must be positive.")

    values = [float(value) for value in local_force[:12]]
    n0 = -values[0]
    vy0 = values[1]
    vz0 = -values[2]
    t0 = -values[3]
    my0 = -values[4]
    mz0 = -values[5]

    wx, wy, wz = _aggregate_uniform(active_loads)
    points = _point_loads(active_loads, length)
    tol = max(length, 1.0) * 1.0e-12

    px_sum = py_sum = pz_sum = 0.0
    py_moment = pz_moment = 0.0
    for point in points:
        a = point["x"]
        passed = x > a + tol or (
            abs(x - a) <= tol and side == "right"
        )
        if not passed:
            continue
        px_sum += point["px"]
        py_sum += point["py"]
        pz_sum += point["pz"]
        lever = max(0.0, x - a)
        py_moment += point["py"] * lever
        pz_moment += point["pz"] * lever

    if component == "N":
        return n0 - wx * x - px_sum
    if component == "Vy":
        return vy0 + wy * x + py_sum
    if component == "Vz":
        return vz0 - wz * x - pz_sum
    if component == "T":
        return t0
    if component == "Mz":
        return mz0 + vy0 * x + 0.5 * wy * x * x + py_moment
    if component == "My":
        return my0 + vz0 * x - 0.5 * wz * x * x - pz_moment
    raise ValueError(f"Unsupported local force component: {component}")


def _moment_extrema_positions(
    local_force: Sequence[float],
    length: float,
    component: str,
    active_loads: Sequence[dict[str, float]],
) -> list[float]:
    if component not in {"My", "Mz"} or len(local_force) < 12:
        return []

    values = [float(value) for value in local_force[:12]]
    wx, wy, wz = _aggregate_uniform(active_loads)
    _ = wx
    points = _point_loads(active_loads, length)
    breakpoints = sorted({
        0.0,
        float(length),
        *(float(point["x"]) for point in points),
    })

    roots: list[float] = []
    tol = max(length, 1.0) * 1.0e-12
    for left, right in zip(breakpoints, breakpoints[1:]):
        if right - left <= tol:
            continue
        midpoint = 0.5 * (left + right)

        if component == "Mz":
            slope = wy
            constant = values[1]
            for point in points:
                if point["x"] < midpoint:
                    constant += point["py"]
        else:
            # dMy/dx = Vz = -localForce_I(Vz) - wz*x - sum(Pz)
            slope = -wz
            constant = -values[2]
            for point in points:
                if point["x"] < midpoint:
                    constant -= point["pz"]

        if abs(slope) <= 1.0e-15:
            continue
        root = -constant / slope
        if left + tol < root < right - tol:
            roots.append(root)
    return roots


def equilibrium_component_samples(
    local_force: Sequence[float],
    length: float,
    component: str,
    active_loads: Sequence[dict[str, float]] | None,
    *,
    sample_count: int = 65,
) -> list[tuple[float, float]]:
    """Sample the exact 1D equilibrium field for Studio beam load types.

    Uniform and point beam loads are evaluated analytically from the I-end
    local force. Point-load coordinates are duplicated for components that
    jump there, so a plotted polyline shows the discontinuity explicitly.
    """
    component = str(component)
    if component not in LOCAL_FORCE_INDEX:
        raise ValueError(
            f"Unsupported local force component: {component}"
        )
    if len(local_force) < 12 or length <= 0.0:
        return []
    if active_loads is None:
        ends = component_end_resultants(local_force, component)
        if ends is None:
            return []
        return [(0.0, ends[0]), (float(length), ends[1])]

    count = max(2, int(sample_count))
    positions = {
        float(length) * index / (count - 1)
        for index in range(count)
    }
    positions.update(
        _moment_extrema_positions(
            local_force,
            length,
            component,
            active_loads,
        )
    )

    points = _point_loads(active_loads, length)
    point_positions = {point["x"] for point in points}

    samples: list[tuple[float, float]] = []
    for x in sorted(positions | point_positions):
        has_point = any(
            math.isclose(
                x,
                point["x"],
                rel_tol=0.0,
                abs_tol=max(length, 1.0) * 1.0e-12,
            )
            for point in points
        )
        if has_point and component in {"N", "Vy", "Vz"}:
            samples.append((
                x,
                _resultant_at(
                    local_force,
                    length,
                    component,
                    active_loads,
                    x,
                    side="left",
                ),
            ))
            samples.append((
                x,
                _resultant_at(
                    local_force,
                    length,
                    component,
                    active_loads,
                    x,
                    side="right",
                ),
            ))
        else:
            samples.append((
                x,
                _resultant_at(
                    local_force,
                    length,
                    component,
                    active_loads,
                    x,
                    side="right",
                ),
            ))
    return samples


def _merge_section_samples_with_ends(
    section_samples: Sequence[tuple[float, float]],
    end_values: tuple[float, float],
    length: float,
) -> list[tuple[float, float]]:
    tol = max(length, 1.0) * 1.0e-10
    samples = [
        (float(x), float(value))
        for x, value in section_samples
        if -tol <= float(x) <= length + tol
    ]

    def upsert(x: float, value: float) -> None:
        for index, (existing_x, _) in enumerate(samples):
            if abs(existing_x - x) <= tol:
                # Prefer the directly queried section value.
                return
        samples.append((x, value))

    upsert(0.0, end_values[0])
    upsert(length, end_values[1])
    return sorted(samples, key=lambda item: item[0])


def enrich_member_force_results(
    result: dict[str, Any],
    model: StructuralModel,
    element_loads: dict[int, ElementLoadData],
    sections: dict[int, SectionData],
    materials: dict[int, MaterialData],
    transformations: dict[int, TransformationData],
    units: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Attach display-ready member-force distributions to a result payload."""
    enriched = copy.deepcopy(result)
    final = enriched.setdefault("final", {})
    if not isinstance(final, dict):
        return enriched

    local_forces = final.get("element_local_forces", {})
    section_forces = final.get("element_section_forces", {})
    load_factors = final.get("load_factors", {})
    if not isinstance(local_forces, dict):
        return enriched
    if not isinstance(section_forces, dict):
        section_forces = {}
    if not isinstance(load_factors, dict):
        load_factors = {}

    diagrams: dict[str, dict[str, Any]] = {}
    analysis_type = str(
        enriched.get("analysis", {}).get("type", "")
        if isinstance(enriched.get("analysis", {}), dict)
        else ""
    )

    for tag in sorted(model.elements):
        element = model.elements[tag]
        raw = local_forces.get(str(tag), local_forces.get(tag))
        if not isinstance(raw, (list, tuple)) or len(raw) < 12:
            continue

        node_i = model.nodes.get(element.i)
        node_j = model.nodes.get(element.j)
        if node_i is None or node_j is None:
            continue
        length = math.sqrt(sum(
            (float(b) - float(a)) ** 2
            for a, b in zip(node_i.xyz, node_j.xyz)
        ))
        if length <= 1.0e-15:
            continue

        active_loads = _active_local_element_loads(
            tag,
            element_loads,
            load_factors,
            model,
            sections,
            materials,
            transformations,
            units,
        )
        section_data = section_forces.get(
            str(tag),
            section_forces.get(tag),
        )
        per_component: dict[str, Any] = {}

        for component in LOCAL_FORCE_COMPONENTS:
            end_values = component_end_resultants(raw, component)
            if end_values is None:
                continue

            direct = section_component_samples(
                section_data if isinstance(section_data, dict) else None,
                component,
            )

            # For displacement-based beam-columns, preserve the actual
            # constitutive section resultants at integration points. For
            # force-based and elastic members, equilibrium reconstruction
            # gives the continuous force field under Studio Uniform/Point
            # beam loads and can be checked against section IP responses.
            if (
                element.element_type == "dispBeamColumn"
                and component in SECTION_FORCE_INDEX
                and direct
            ):
                samples = _merge_section_samples_with_ends(
                    direct,
                    end_values,
                    length,
                )
                source = "section integration points"
            elif active_loads is not None:
                samples = equilibrium_component_samples(
                    raw,
                    length,
                    component,
                    active_loads,
                )
                source = "equilibrium"
            elif component in SECTION_FORCE_INDEX and direct:
                samples = _merge_section_samples_with_ends(
                    direct,
                    end_values,
                    length,
                )
                source = "section integration points"
            else:
                samples = [
                    (0.0, end_values[0]),
                    (length, end_values[1]),
                ]
                source = "end-force fallback"

            verification = None
            if direct and active_loads is not None:
                differences = []
                for x, value in direct:
                    reconstructed = _resultant_at(
                        raw,
                        length,
                        component,
                        active_loads,
                        x,
                        side="right",
                    )
                    differences.append(abs(reconstructed - value))
                if differences:
                    verification = max(differences)

            per_component[component] = {
                "x": [float(x) for x, _ in samples],
                "values": [float(value) for _, value in samples],
                "source": source,
                "section_points": [
                    [float(x), float(value)]
                    for x, value in direct
                ],
                "verification_max_abs_difference": verification,
                "analysis_type": analysis_type,
            }

        if per_component:
            diagrams[str(tag)] = per_component

    final["member_force_diagrams"] = diagrams
    return enriched
