from __future__ import annotations

import math
from dataclasses import dataclass

from .project import (
    FiberComponentData,
    FiberData,
    MaterialData,
    SectionData,
)


@dataclass(frozen=True)
class FiberSectionValidationIssue:
    severity: str
    code: str
    message: str

    def __post_init__(self) -> None:
        severity = str(self.severity).upper()
        if severity not in {"ERROR", "WARNING", "INFO"}:
            raise ValueError(f"Unsupported validation severity: {severity}")
        object.__setattr__(self, "severity", severity)


def _is_full_circle(component: FiberComponentData) -> bool:
    if component.component_type != "CircPatch":
        return False
    p = component.parameters
    return math.isclose(
        p["end_angle"] - p["start_angle"],
        360.0,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    )


def _patch_area(component: FiberComponentData) -> float:
    p = component.parameters
    if component.component_type == "RectPatch":
        return p["width_y"] * p["depth_z"]
    if component.component_type == "CircPatch":
        span = math.radians(p["end_angle"] - p["start_angle"])
        return 0.5 * span * (
            p["r_outer"] ** 2 - p["r_inner"] ** 2
        )
    return 0.0


def _rect_bounds(
    component: FiberComponentData,
) -> tuple[float, float, float, float]:
    p = component.parameters
    return (
        p["y_center"] - 0.5 * p["width_y"],
        p["y_center"] + 0.5 * p["width_y"],
        p["z_center"] - 0.5 * p["depth_z"],
        p["z_center"] + 0.5 * p["depth_z"],
    )


def _rectangles_overlap(
    a: FiberComponentData,
    b: FiberComponentData,
    tolerance: float,
) -> bool:
    ay0, ay1, az0, az1 = _rect_bounds(a)
    by0, by1, bz0, bz1 = _rect_bounds(b)
    overlap_y = min(ay1, by1) - max(ay0, by0)
    overlap_z = min(az1, bz1) - max(az0, bz0)
    return overlap_y > tolerance and overlap_z > tolerance


def _full_circular_patches_overlap(
    a: FiberComponentData,
    b: FiberComponentData,
    tolerance: float,
) -> bool:
    if not (_is_full_circle(a) and _is_full_circle(b)):
        return False
    pa = a.parameters
    pb = b.parameters
    if not (
        math.isclose(
            pa["y_center"],
            pb["y_center"],
            abs_tol=tolerance,
        )
        and math.isclose(
            pa["z_center"],
            pb["z_center"],
            abs_tol=tolerance,
        )
    ):
        return False
    overlap = min(pa["r_outer"], pb["r_outer"]) - max(
        pa["r_inner"],
        pb["r_inner"],
    )
    return overlap > tolerance


def _angle_in_span(
    angle_deg: float,
    start_deg: float,
    end_deg: float,
    tolerance: float = 1.0e-9,
) -> bool:
    span = end_deg - start_deg
    if span >= 360.0 - tolerance:
        return True
    angle = (angle_deg - start_deg) % 360.0
    return angle <= span + tolerance


def _fiber_inside_patch(
    fiber: FiberData,
    patch: FiberComponentData,
    tolerance: float,
) -> bool:
    radius = math.sqrt(max(fiber.area, 0.0) / math.pi)
    p = patch.parameters

    if patch.component_type == "RectPatch":
        y0, y1, z0, z1 = _rect_bounds(patch)
        return (
            fiber.y - radius >= y0 - tolerance
            and fiber.y + radius <= y1 + tolerance
            and fiber.z - radius >= z0 - tolerance
            and fiber.z + radius <= z1 + tolerance
        )

    if patch.component_type == "CircPatch":
        dy = fiber.y - p["y_center"]
        dz = fiber.z - p["z_center"]
        radial = math.hypot(dy, dz)
        if radial - radius < p["r_inner"] - tolerance:
            return False
        if radial + radius > p["r_outer"] + tolerance:
            return False
        angle = math.degrees(math.atan2(dz, dy)) % 360.0
        return _angle_in_span(
            angle,
            p["start_angle"],
            p["end_angle"],
        )

    return False


def _material_is_concrete(
    tag: int,
    materials: dict[int, MaterialData] | None,
) -> bool:
    if materials is None:
        return True
    material = materials.get(int(tag))
    return (
        material is not None
        and material.material_type == "Concrete02"
    )


def _material_is_steel(
    tag: int,
    materials: dict[int, MaterialData] | None,
) -> bool:
    if materials is None:
        return True
    material = materials.get(int(tag))
    return (
        material is not None
        and material.material_type == "Steel02"
    )


def validate_fiber_section_geometry(
    section: SectionData,
    materials: dict[int, MaterialData] | None = None,
    *,
    tolerance: float = 1.0e-10,
) -> list[FiberSectionValidationIssue]:
    if section.section_type != "Fiber":
        return []

    issues: list[FiberSectionValidationIssue] = []

    if section.parameters.get("GJ", 0.0) <= 0.0:
        issues.append(
            FiberSectionValidationIssue(
                "ERROR",
                "NONPOSITIVE_GJ",
                "Fiber section torsional stiffness GJ must be positive.",
            )
        )

    missing = sorted(
        tag
        for tag in section.fiber_material_tags()
        if materials is not None and tag not in materials
    )
    if missing:
        issues.append(
            FiberSectionValidationIssue(
                "ERROR",
                "MISSING_MATERIAL",
                "Missing material tag(s): "
                + ", ".join(str(tag) for tag in missing),
            )
        )

    patches = [
        component
        for component in section.fiber_components
        if component.component_type in {"RectPatch", "CircPatch"}
    ]
    concrete_patches = [
        component
        for component in patches
        if _material_is_concrete(component.material_tag, materials)
    ]

    for index, first in enumerate(patches):
        for second in patches[index + 1 :]:
            overlap = False
            if (
                first.component_type == "RectPatch"
                and second.component_type == "RectPatch"
            ):
                overlap = _rectangles_overlap(
                    first,
                    second,
                    tolerance,
                )
            elif (
                first.component_type == "CircPatch"
                and second.component_type == "CircPatch"
            ):
                overlap = _full_circular_patches_overlap(
                    first,
                    second,
                    tolerance,
                )
            if overlap:
                issues.append(
                    FiberSectionValidationIssue(
                        "WARNING",
                        "PATCH_OVERLAP",
                        f"Patch '{first.name}' overlaps patch "
                        f"'{second.name}'. Overlap double-counts area unless "
                        "it is intentional.",
                    )
                )

    # For concentric full circular patches, identify radial gaps directly.
    full_circular = [
        component
        for component in concrete_patches
        if component.component_type == "CircPatch"
        and _is_full_circle(component)
    ]
    if len(full_circular) >= 2:
        centers = {
            (
                round(component.parameters["y_center"], 12),
                round(component.parameters["z_center"], 12),
            )
            for component in full_circular
        }
        if len(centers) == 1:
            intervals = sorted(
                (
                    component.parameters["r_inner"],
                    component.parameters["r_outer"],
                    component.name,
                )
                for component in full_circular
            )
            for (_, previous_outer, previous_name), (
                current_inner,
                _,
                current_name,
            ) in zip(intervals, intervals[1:]):
                if current_inner - previous_outer > tolerance:
                    issues.append(
                        FiberSectionValidationIssue(
                            "WARNING",
                            "CIRCULAR_GAP",
                            f"Radial gap between '{previous_name}' and "
                            f"'{current_name}'.",
                        )
                    )

    reinforcement_components = [
        component
        for component in section.fiber_components
        if (
            component.component_type in {
                "StraightLayer",
                "CircLayer",
                "SingleFiber",
            }
            and _material_is_steel(component.material_tag, materials)
        )
    ]

    reinforcement_fibers: list[
        tuple[str, int, FiberData]
    ] = []
    for component in reinforcement_components:
        for fiber in component.compile_fibers():
            reinforcement_fibers.append(
                (component.name, component.material_tag, fiber)
            )

    if concrete_patches and reinforcement_fibers:
        for name, _, fiber in reinforcement_fibers:
            if not any(
                _fiber_inside_patch(
                    fiber,
                    patch,
                    tolerance,
                )
                for patch in concrete_patches
            ):
                issues.append(
                    FiberSectionValidationIssue(
                        "ERROR",
                        "REBAR_OUTSIDE_CONCRETE",
                        f"Reinforcement in '{name}' at "
                        f"(y={fiber.y:.6g}, z={fiber.z:.6g}) lies outside "
                        "the concrete patches or inside a void.",
                    )
                )
                # One representative error per component is enough.
                reinforcement_fibers = [
                    item
                    for item in reinforcement_fibers
                    if item[0] != name
                ]
                break

    seen: dict[tuple[int, int, int], str] = {}
    for name, material_tag, fiber in reinforcement_fibers:
        quantum = max(tolerance, 1.0e-12)
        key = (
            int(material_tag),
            round(fiber.y / quantum),
            round(fiber.z / quantum),
        )
        previous = seen.get(key)
        if previous is not None:
            issues.append(
                FiberSectionValidationIssue(
                    "WARNING",
                    "DUPLICATE_REBAR",
                    f"Reinforcement '{name}' duplicates a bar from "
                    f"'{previous}' at the same y-z location.",
                )
            )
        else:
            seen[key] = name

    if not section.compiled_fibers():
        issues.append(
            FiberSectionValidationIssue(
                "ERROR",
                "EMPTY_SECTION",
                "Fiber section contains no fibers.",
            )
        )

    if patches:
        patch_area = sum(_patch_area(component) for component in patches)
        if patch_area <= tolerance:
            issues.append(
                FiberSectionValidationIssue(
                    "ERROR",
                    "ZERO_PATCH_AREA",
                    "Concrete/patch area must be positive.",
                )
            )

    return issues
