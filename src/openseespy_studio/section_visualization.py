from __future__ import annotations

import math
from collections.abc import Iterable

from .project import FiberComponentData, FiberData, SectionData


BoundsYZ = tuple[float, float, float, float]


def equivalent_fiber_radius(area: float) -> float:
    return math.sqrt(max(float(area), 0.0) / math.pi)


def component_bounds(component: FiberComponentData) -> BoundsYZ:
    p = component.parameters

    if component.component_type == "RectPatch":
        half_y = 0.5 * p["width_y"]
        half_z = 0.5 * p["depth_z"]
        return (
            p["y_center"] - half_y,
            p["y_center"] + half_y,
            p["z_center"] - half_z,
            p["z_center"] + half_z,
        )

    if component.component_type == "CircPatch":
        radius = p["r_outer"]
        return (
            p["y_center"] - radius,
            p["y_center"] + radius,
            p["z_center"] - radius,
            p["z_center"] + radius,
        )

    if component.component_type == "StraightLayer":
        radius = equivalent_fiber_radius(p["bar_area"])
        return (
            min(p["y_i"], p["y_j"]) - radius,
            max(p["y_i"], p["y_j"]) + radius,
            min(p["z_i"], p["z_j"]) - radius,
            max(p["z_i"], p["z_j"]) + radius,
        )

    if component.component_type == "CircLayer":
        radius = p["radius"] + equivalent_fiber_radius(p["bar_area"])
        return (
            p["y_center"] - radius,
            p["y_center"] + radius,
            p["z_center"] - radius,
            p["z_center"] + radius,
        )

    if component.component_type == "SingleFiber":
        radius = equivalent_fiber_radius(p["area"])
        return (
            p["y"] - radius,
            p["y"] + radius,
            p["z"] - radius,
            p["z"] + radius,
        )

    raise ValueError(
        f"Unsupported fiber component type: {component.component_type}"
    )


def fiber_bounds(fiber: FiberData) -> BoundsYZ:
    radius = equivalent_fiber_radius(fiber.area)
    return (
        fiber.y - radius,
        fiber.y + radius,
        fiber.z - radius,
        fiber.z + radius,
    )


def combine_bounds(bounds: Iterable[BoundsYZ]) -> BoundsYZ | None:
    items = list(bounds)
    if not items:
        return None
    return (
        min(item[0] for item in items),
        max(item[1] for item in items),
        min(item[2] for item in items),
        max(item[3] for item in items),
    )


def section_preview_bounds(section: SectionData) -> BoundsYZ | None:
    if section.section_type != "Fiber":
        return None

    items: list[BoundsYZ] = [
        component_bounds(component)
        for component in section.fiber_components
    ]
    items.extend(fiber_bounds(fiber) for fiber in section.fibers)

    if not items:
        items.extend(
            fiber_bounds(fiber)
            for fiber in section.compiled_fibers()
        )
    return combine_bounds(items)


def section_dimensions(
    section: SectionData,
) -> tuple[float, float] | None:
    bounds = section_preview_bounds(section)
    if bounds is None:
        return None
    y_min, y_max, z_min, z_max = bounds
    return y_max - y_min, z_max - z_min
