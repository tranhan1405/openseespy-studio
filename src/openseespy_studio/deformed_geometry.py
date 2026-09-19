from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .project import SectionData


@dataclass(frozen=True)
class SweptMemberGeometry:
    """Surface mesh payload for a deformed beam/column member."""

    points: np.ndarray
    faces: np.ndarray
    magnitudes: np.ndarray
    centerline: np.ndarray


def normalize_display_geometry(raw: object) -> dict[str, object]:
    """Return a compact, JSON-safe section display-geometry mapping."""
    if not isinstance(raw, dict):
        return {}
    shape = str(raw.get("shape", "") or "").strip()
    dimensions = raw.get("dimensions", {})
    if not shape or not isinstance(dimensions, dict):
        return {}

    normalized: dict[str, float] = {}
    for key, value in dimensions.items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    if not normalized:
        return {}
    return {"shape": shape, "dimensions": normalized}


def _component_rect_bounds(component) -> tuple[float, float, float, float] | None:
    if getattr(component, "component_type", "") != "RectPatch":
        return None
    p = component.parameters
    hy = 0.5 * float(p["width_y"])
    hz = 0.5 * float(p["depth_z"])
    yc = float(p["y_center"])
    zc = float(p["z_center"])
    return yc - hy, yc + hy, zc - hz, zc + hz


def _union_bounds(bounds: list[tuple[float, float, float, float]]):
    return (
        min(value[0] for value in bounds),
        max(value[1] for value in bounds),
        min(value[2] for value in bounds),
        max(value[3] for value in bounds),
    )


def infer_fiber_display_geometry(section: SectionData) -> dict[str, object]:
    """Infer simple display geometry from generated Fiber Builder components.

    This intentionally avoids inventing a shape for arbitrary manual fibers.
    """
    if section.section_type != "Fiber":
        return {}

    components = list(section.fiber_components)
    if not components:
        return {}

    patch_components = [
        component
        for component in components
        if component.component_type in {"RectPatch", "CircPatch"}
    ]
    if not patch_components:
        return {}

    if all(component.component_type == "CircPatch" for component in patch_components):
        centers = {
            (
                round(float(component.parameters["y_center"]), 12),
                round(float(component.parameters["z_center"]), 12),
            )
            for component in patch_components
        }
        if len(centers) != 1:
            return {}
        outer = max(float(component.parameters["r_outer"]) for component in patch_components)
        inner = min(float(component.parameters["r_inner"]) for component in patch_components)
        if outer <= 0.0:
            return {}
        dimensions = {
            "outer_diameter": 2.0 * outer,
            "inner_diameter": 2.0 * max(0.0, inner),
        }
        shape = "Hollow Circle" if inner > 1.0e-12 else "Circle"
        return {"shape": shape, "dimensions": dimensions}

    if not all(component.component_type == "RectPatch" for component in patch_components):
        return {}

    rects = [
        (component, _component_rect_bounds(component))
        for component in patch_components
    ]
    rects = [(component, bounds) for component, bounds in rects if bounds is not None]
    if not rects:
        return {}

    names = [str(component.name).strip().lower() for component, _ in rects]
    all_bounds = [bounds for _, bounds in rects]
    y0, y1, z0, z1 = _union_bounds(all_bounds)
    height = y1 - y0
    flange_width = z1 - z0
    if height <= 0.0 or flange_width <= 0.0:
        return {}

    has_flange = any("flange" in name for name in names)
    has_web = any("web" in name for name in names)
    if not (has_flange and has_web):
        rectangle_template_names = {
            "core",
            "rectangle concrete",
            "cover - top",
            "cover - bottom",
            "cover - left",
            "cover - right",
        }
        if all(name in rectangle_template_names for name in names):
            return {
                "shape": "Rectangle",
                "dimensions": {
                    "height": height,
                    "width": flange_width,
                },
            }
        return {}

    web_bounds = [
        bounds
        for (component, bounds), name in zip(rects, names)
        if "web" in name
    ]
    if not web_bounds:
        return {}
    _, _, web_z0, web_z1 = _union_bounds(web_bounds)
    web_width = web_z1 - web_z0

    bottom_flange = any("bottom flange" in name for name in names)
    top_flange_bounds = [
        bounds
        for (component, bounds), name in zip(rects, names)
        if "flange" in name and "bottom" not in name
    ]
    if not top_flange_bounds:
        top_flange_bounds = [
            bounds
            for (component, bounds), name in zip(rects, names)
            if "flange" in name
        ]
    flange_y0 = min(bounds[0] for bounds in top_flange_bounds)
    flange_thickness = y1 - flange_y0

    if min(web_width, flange_thickness) <= 0.0:
        return {}
    return {
        "shape": "I" if bottom_flange else "T",
        "dimensions": {
            "height": height,
            "flange_width": flange_width,
            "flange_thickness": flange_thickness,
            "web_width": web_width,
        },
    }


def section_display_geometry(section: SectionData | None) -> dict[str, object]:
    if section is None:
        return {}
    explicit = normalize_display_geometry(
        getattr(section, "display_geometry", {})
    )
    if explicit:
        return explicit
    return infer_fiber_display_geometry(section)


def geometry_contours(
    display_geometry: dict[str, object],
    *,
    circle_resolution: int = 32,
) -> list[np.ndarray]:
    geometry = normalize_display_geometry(display_geometry)
    if not geometry:
        return []

    shape = str(geometry["shape"]).strip().lower()
    dims = dict(geometry["dimensions"])

    if shape == "rectangle":
        h = float(dims.get("height", 0.0))
        b = float(dims.get("width", 0.0))
        if min(h, b) <= 0.0:
            return []
        return [
            np.asarray(
                [
                    [0.5 * h, -0.5 * b],
                    [0.5 * h, 0.5 * b],
                    [-0.5 * h, 0.5 * b],
                    [-0.5 * h, -0.5 * b],
                ],
                dtype=float,
            )
        ]

    if shape in {"circle", "hollow circle"}:
        do = float(dims.get("outer_diameter", 0.0))
        di = float(dims.get("inner_diameter", 0.0))
        if do <= 0.0 or di < 0.0 or di >= do:
            return []
        count = max(12, int(circle_resolution))
        angles = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
        outer = np.column_stack(
            (0.5 * do * np.cos(angles), 0.5 * do * np.sin(angles))
        )
        contours = [outer]
        if shape == "hollow circle" and di > 0.0:
            contours.append(
                np.column_stack(
                    (0.5 * di * np.cos(angles), 0.5 * di * np.sin(angles))
                )
            )
        return contours

    if shape in {"t", "i"}:
        h = float(dims.get("height", 0.0))
        bf = float(dims.get("flange_width", 0.0))
        tf = float(dims.get("flange_thickness", 0.0))
        bw = float(dims.get("web_width", 0.0))
        if min(h, bf, tf, bw) <= 0.0 or bw > bf:
            return []

        yt = 0.5 * h
        yb = -0.5 * h
        if shape == "t":
            yfb = yt - tf
            if yfb <= yb:
                return []
            contour = np.asarray(
                [
                    [yt, -0.5 * bf],
                    [yt, 0.5 * bf],
                    [yfb, 0.5 * bf],
                    [yfb, 0.5 * bw],
                    [yb, 0.5 * bw],
                    [yb, -0.5 * bw],
                    [yfb, -0.5 * bw],
                    [yfb, -0.5 * bf],
                ],
                dtype=float,
            )
            # Elastic T sections use centroidal section axes. Fiber templates
            # omit this metadata so their explicitly defined y coordinates are
            # preserved exactly.
            centroid_y = float(dims.get("centroid_y", 0.0))
            contour[:, 0] -= centroid_y
            return [contour]

        y_top_web = yt - tf
        y_bottom_web = yb + tf
        if y_top_web <= y_bottom_web:
            return []
        contour = np.asarray(
            [
                [yt, -0.5 * bf],
                [yt, 0.5 * bf],
                [y_top_web, 0.5 * bf],
                [y_top_web, 0.5 * bw],
                [y_bottom_web, 0.5 * bw],
                [y_bottom_web, 0.5 * bf],
                [yb, 0.5 * bf],
                [yb, -0.5 * bf],
                [y_bottom_web, -0.5 * bf],
                [y_bottom_web, -0.5 * bw],
                [y_top_web, -0.5 * bw],
                [y_top_web, -0.5 * bf],
            ],
            dtype=float,
        )
        return [contour]

    return []


def section_contours(
    section: SectionData | None,
    *,
    circle_resolution: int = 32,
) -> list[np.ndarray]:
    return geometry_contours(
        section_display_geometry(section),
        circle_resolution=circle_resolution,
    )


def section_axis_inertias(
    section: SectionData | None,
    materials: dict[int, Any] | None = None,
) -> tuple[float, float] | None:
    """Return (Iy, Iz) for display/axis annotation when available."""
    if section is None:
        return None

    if section.section_type == "Elastic":
        try:
            values = section.resolved_elastic_parameters(materials)
        except ValueError:
            values = dict(section.parameters)
        try:
            iy = float(values["Iy"])
            iz = float(values["Iz"])
        except (KeyError, TypeError, ValueError):
            return None
        if iy < 0.0 or iz < 0.0:
            return None
        return iy, iz

    fibers = section.compiled_fibers()
    if not fibers:
        return None
    total, (cy, cz) = section.fiber_area_and_centroid()
    if total <= 0.0:
        return None
    iy = sum(
        float(fiber.area) * (float(fiber.z) - float(cz)) ** 2
        for fiber in fibers
    )
    iz = sum(
        float(fiber.area) * (float(fiber.y) - float(cy)) ** 2
        for fiber in fibers
    )
    return float(iy), float(iz)


def section_axis_strength_labels(
    section: SectionData | None,
    materials: dict[int, Any] | None = None,
) -> tuple[str, str]:
    """Return human-readable local-y/local-z bending-axis labels."""
    inertias = section_axis_inertias(section, materials)
    if inertias is None:
        return "y", "z"
    iy, iz = inertias
    scale = max(abs(iy), abs(iz), 1.0e-30)
    if abs(iy - iz) <= 1.0e-6 * scale:
        return "y · Iy", "z · Iz"
    if iy > iz:
        return "y · Iy strong", "z · Iz weak"
    return "y · Iy weak", "z · Iz strong"


def _vector_parts(raw: object, ndm: int) -> tuple[np.ndarray, np.ndarray, bool]:
    values = list(raw) if isinstance(raw, (list, tuple, np.ndarray)) else []
    if int(ndm) == 2:
        while len(values) < 2:
            values.append(0.0)
        translation = np.asarray(
            [float(values[0]), float(values[1]), 0.0],
            dtype=float,
        )
        has_rotation = len(values) >= 3
        rotation = np.asarray(
            [0.0, 0.0, float(values[2]) if has_rotation else 0.0],
            dtype=float,
        )
        return translation, rotation, has_rotation

    while len(values) < 3:
        values.append(0.0)
    translation = np.asarray(
        [float(values[0]), float(values[1]), float(values[2])],
        dtype=float,
    )
    has_rotation = len(values) >= 6
    rotation = np.asarray(
        [
            float(values[3]) if has_rotation else 0.0,
            float(values[4]) if has_rotation else 0.0,
            float(values[5]) if has_rotation else 0.0,
        ],
        dtype=float,
    )
    return translation, rotation, has_rotation


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1.0e-14:
        raise ValueError("Cannot normalize a zero-length vector.")
    return vector / norm


def deformed_member_frames(
    start: object,
    end: object,
    local_y: object,
    local_z: object,
    displacement_i: object,
    displacement_j: object,
    *,
    ndm: int,
    scale: float,
    stations: int = 17,
    smooth: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate a beam centerline and rigid cross-section frames.

    Transverse displacement uses cubic Hermite interpolation when rotational
    DOFs are available. The slopes are derived from the small-rotation relation
    d(tangent) = rotation × local-x, which avoids hard-coded 2D/3D sign guesses.
    """
    p_i = np.asarray(start, dtype=float)
    p_j = np.asarray(end, dtype=float)
    member = p_j - p_i
    length = float(np.linalg.norm(member))
    if length <= 1.0e-14:
        raise ValueError("Cannot deform a zero-length member.")

    ex = member / length
    ey = np.asarray(local_y, dtype=float)
    ey = ey - float(np.dot(ey, ex)) * ex
    ey = _normalize(ey)
    ez = _normalize(np.cross(ex, ey))
    if float(np.dot(ez, np.asarray(local_z, dtype=float))) < 0.0:
        ey = -ey
        ez = -ez

    trans_i, rot_i, has_rot_i = _vector_parts(displacement_i, ndm)
    trans_j, rot_j, has_rot_j = _vector_parts(displacement_j, ndm)

    basis = np.vstack((ex, ey, ez))
    ui = basis @ trans_i
    uj = basis @ trans_j
    ri = basis @ rot_i
    rj = basis @ rot_j

    minimum_stations = 3 if smooth else 2
    count = max(minimum_stations, int(stations))
    s_values = np.linspace(0.0, 1.0, count)
    centerline = np.zeros((count, 3), dtype=float)
    magnitudes = np.zeros(count, dtype=float)

    use_hermite = bool(smooth and has_rot_i and has_rot_j)
    for index, s in enumerate(s_values):
        axial = (1.0 - s) * ui[0] + s * uj[0]
        if use_hermite:
            h00 = 2.0 * s**3 - 3.0 * s**2 + 1.0
            h10 = s**3 - 2.0 * s**2 + s
            h01 = -2.0 * s**3 + 3.0 * s**2
            h11 = s**3 - s**2
            slope_v_i = ri[2]
            slope_v_j = rj[2]
            slope_w_i = -ri[1]
            slope_w_j = -rj[1]
            transverse_y = (
                h00 * ui[1]
                + h10 * length * slope_v_i
                + h01 * uj[1]
                + h11 * length * slope_v_j
            )
            transverse_z = (
                h00 * ui[2]
                + h10 * length * slope_w_i
                + h01 * uj[2]
                + h11 * length * slope_w_j
            )
        else:
            transverse_y = (1.0 - s) * ui[1] + s * uj[1]
            transverse_z = (1.0 - s) * ui[2] + s * uj[2]

        local_displacement = np.asarray(
            [axial, transverse_y, transverse_z],
            dtype=float,
        )
        global_displacement = (
            local_displacement[0] * ex
            + local_displacement[1] * ey
            + local_displacement[2] * ez
        )
        centerline[index] = (
            p_i + s * member + float(scale) * global_displacement
        )
        magnitudes[index] = float(np.linalg.norm(global_displacement))

    tangents = np.gradient(centerline, axis=0)
    frame_y = np.zeros_like(centerline)
    frame_z = np.zeros_like(centerline)

    for index, tangent in enumerate(tangents):
        t = _normalize(tangent)
        candidate_y = ey - float(np.dot(ey, t)) * t
        if float(np.linalg.norm(candidate_y)) <= 1.0e-12:
            candidate_y = np.cross(ez, t)
        candidate_y = _normalize(candidate_y)
        candidate_z = _normalize(np.cross(t, candidate_y))
        if float(np.dot(candidate_z, ez)) < 0.0:
            candidate_y = -candidate_y
            candidate_z = -candidate_z

        twist = 0.0
        if use_hermite:
            s = float(s_values[index])
            twist = float(scale) * (
                (1.0 - s) * ri[0] + s * rj[0]
            )
        cosine = math.cos(twist)
        sine = math.sin(twist)
        frame_y[index] = cosine * candidate_y + sine * candidate_z
        frame_z[index] = -sine * candidate_y + cosine * candidate_z

    return centerline, frame_y, frame_z, magnitudes


def build_swept_member_geometry(
    section: SectionData | None,
    start: object,
    end: object,
    local_y: object,
    local_z: object,
    displacement_i: object,
    displacement_j: object,
    *,
    ndm: int,
    scale: float,
    stations: int = 17,
    smooth: bool = True,
    circle_resolution: int = 32,
) -> SweptMemberGeometry | None:
    contours = section_contours(
        section,
        circle_resolution=circle_resolution,
    )
    if not contours:
        return None

    centerline, frame_y, frame_z, station_magnitudes = (
        deformed_member_frames(
            start,
            end,
            local_y,
            local_z,
            displacement_i,
            displacement_j,
            ndm=ndm,
            scale=scale,
            stations=stations,
            smooth=smooth,
        )
    )

    points: list[np.ndarray] = []
    magnitudes: list[float] = []
    faces: list[int] = []

    station_count = centerline.shape[0]
    for contour in contours:
        vertex_count = int(contour.shape[0])
        if vertex_count < 3:
            continue
        offset = len(points)
        for station in range(station_count):
            for y, z in contour:
                points.append(
                    centerline[station]
                    + float(y) * frame_y[station]
                    + float(z) * frame_z[station]
                )
                magnitudes.append(float(station_magnitudes[station]))

        for station in range(station_count - 1):
            row0 = offset + station * vertex_count
            row1 = row0 + vertex_count
            for index in range(vertex_count):
                next_index = (index + 1) % vertex_count
                faces.extend(
                    (
                        4,
                        row0 + index,
                        row0 + next_index,
                        row1 + next_index,
                        row1 + index,
                    )
                )

    if not points or not faces:
        return None

    return SweptMemberGeometry(
        points=np.asarray(points, dtype=float),
        faces=np.asarray(faces, dtype=np.int64),
        magnitudes=np.asarray(magnitudes, dtype=float),
        centerline=centerline,
    )
