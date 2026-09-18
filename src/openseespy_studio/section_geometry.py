from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionGeometryProperties:
    area: float
    iy: float
    iz: float
    j: float
    centroid_y: float = 0.0
    centroid_z: float = 0.0
    j_is_approximate: bool = False

    def as_elastic_parameters(self) -> dict[str, float]:
        return {
            "A": float(self.area),
            "Iy": float(self.iy),
            "Iz": float(self.iz),
            "J": float(self.j),
        }


def _positive(value: float, label: str) -> float:
    result = float(value)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive.")
    return result


def rectangle_torsion_constant(height: float, width: float) -> float:
    """Saint-Venant torsion constant for a solid rectangle.

    Uses the standard engineering approximation with a >= b:
    J = a*b^3*(1/3 - 0.21*(b/a)*(1 - b^4/(12*a^4))).
    """
    h = _positive(height, "Rectangle height")
    b = _positive(width, "Rectangle width")
    a = max(h, b)
    t = min(h, b)
    ratio = t / a
    return a * t**3 * (
        1.0 / 3.0
        - 0.21 * ratio * (1.0 - ratio**4 / 12.0)
    )


def rectangle_properties(
    *,
    height: float,
    width: float,
) -> SectionGeometryProperties:
    h = _positive(height, "Rectangle height")
    b = _positive(width, "Rectangle width")
    return SectionGeometryProperties(
        area=b * h,
        iy=h * b**3 / 12.0,
        iz=b * h**3 / 12.0,
        j=rectangle_torsion_constant(h, b),
        j_is_approximate=True,
    )


def circle_properties(
    *,
    outer_diameter: float,
    inner_diameter: float = 0.0,
) -> SectionGeometryProperties:
    do = _positive(outer_diameter, "Outer diameter")
    di = float(inner_diameter)
    if di < 0.0:
        raise ValueError("Inner diameter cannot be negative.")
    if di >= do:
        raise ValueError(
            "Inner diameter must be smaller than outer diameter."
        )

    area = math.pi * (do**2 - di**2) / 4.0
    inertia = math.pi * (do**4 - di**4) / 64.0
    torsion = math.pi * (do**4 - di**4) / 32.0
    return SectionGeometryProperties(
        area=area,
        iy=inertia,
        iz=inertia,
        j=torsion,
    )


def i_section_properties(
    *,
    height: float,
    flange_width: float,
    flange_thickness: float,
    web_width: float,
) -> SectionGeometryProperties:
    h = _positive(height, "I-section height")
    bf = _positive(flange_width, "Flange width")
    tf = _positive(flange_thickness, "Flange thickness")
    bw = _positive(web_width, "Web width")
    if bw > bf:
        raise ValueError("Web width cannot exceed flange width.")
    if 2.0 * tf >= h:
        raise ValueError(
            "I-section needs 2 × flange thickness < total height."
        )

    hw = h - 2.0 * tf
    area = 2.0 * bf * tf + bw * hw

    iy = (
        2.0 * tf * bf**3 / 12.0
        + hw * bw**3 / 12.0
    )

    flange_centroid = 0.5 * h - 0.5 * tf
    iz = (
        2.0
        * (
            bf * tf**3 / 12.0
            + bf * tf * flange_centroid**2
        )
        + bw * hw**3 / 12.0
    )

    # Thin-wall engineering approximation for open I sections.
    j = (
        2.0 * bf * tf**3
        + hw * bw**3
    ) / 3.0

    return SectionGeometryProperties(
        area=area,
        iy=iy,
        iz=iz,
        j=j,
        j_is_approximate=True,
    )


def t_section_properties(
    *,
    height: float,
    flange_width: float,
    flange_thickness: float,
    web_width: float,
) -> SectionGeometryProperties:
    h = _positive(height, "T-section height")
    bf = _positive(flange_width, "Flange width")
    tf = _positive(flange_thickness, "Flange thickness")
    bw = _positive(web_width, "Web width")
    if bw > bf:
        raise ValueError("Web width cannot exceed flange width.")
    if tf >= h:
        raise ValueError(
            "T-section flange thickness must be smaller than total height."
        )

    hw = h - tf
    web_area = bw * hw
    flange_area = bf * tf
    area = web_area + flange_area

    # Centroid measured from the section mid-height in local +y.
    y_bottom = -0.5 * h
    web_y = y_bottom + 0.5 * hw
    flange_y = 0.5 * h - 0.5 * tf
    centroid_y = (
        web_area * web_y + flange_area * flange_y
    ) / area

    iy = (
        hw * bw**3 / 12.0
        + tf * bf**3 / 12.0
    )
    iz = (
        bw * hw**3 / 12.0
        + web_area * (web_y - centroid_y) ** 2
        + bf * tf**3 / 12.0
        + flange_area * (flange_y - centroid_y) ** 2
    )

    # Thin-wall engineering approximation for an open T section.
    j = (
        bf * tf**3
        + hw * bw**3
    ) / 3.0

    return SectionGeometryProperties(
        area=area,
        iy=iy,
        iz=iz,
        j=j,
        centroid_y=centroid_y,
        j_is_approximate=True,
    )


def section_geometry_properties(
    shape: str,
    **dimensions: float,
) -> SectionGeometryProperties:
    key = str(shape).strip().lower()
    if key == "rectangle":
        return rectangle_properties(
            height=dimensions["height"],
            width=dimensions["width"],
        )
    if key in {"circle", "hollow circle"}:
        return circle_properties(
            outer_diameter=dimensions["outer_diameter"],
            inner_diameter=(
                0.0
                if key == "circle"
                else dimensions.get("inner_diameter", 0.0)
            ),
        )
    if key == "t":
        return t_section_properties(
            height=dimensions["height"],
            flange_width=dimensions["flange_width"],
            flange_thickness=dimensions["flange_thickness"],
            web_width=dimensions["web_width"],
        )
    if key == "i":
        return i_section_properties(
            height=dimensions["height"],
            flange_width=dimensions["flange_width"],
            flange_thickness=dimensions["flange_thickness"],
            web_width=dimensions["web_width"],
        )
    raise ValueError(f"Unsupported section geometry: {shape}")
