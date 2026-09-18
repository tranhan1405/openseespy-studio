from __future__ import annotations

import math

from .project import FiberComponentData


def _validate_common(
    *,
    height: float,
    flange_width: float,
    flange_thickness: float,
    web_width: float,
    cover: float,
    is_i_section: bool,
) -> None:
    height = float(height)
    flange_width = float(flange_width)
    flange_thickness = float(flange_thickness)
    web_width = float(web_width)
    cover = float(cover)

    if min(height, flange_width, flange_thickness, web_width) <= 0.0:
        raise ValueError("Section dimensions must be positive.")
    if web_width > flange_width:
        raise ValueError("Web width cannot exceed flange width.")
    if is_i_section:
        if 2.0 * flange_thickness >= height:
            raise ValueError(
                "I-section needs 2 × flange thickness < total height."
            )
    elif flange_thickness >= height:
        raise ValueError(
            "T-section flange thickness must be smaller than total height."
        )

    if cover < 0.0:
        raise ValueError("Concrete cover cannot be negative.")
    if cover > 0.0:
        if 2.0 * cover >= web_width:
            raise ValueError(
                "Cover is too large for the web width."
            )
        if 2.0 * cover >= flange_thickness:
            raise ValueError(
                "Cover is too large for the flange thickness."
            )
        if 2.0 * cover >= flange_width:
            raise ValueError(
                "Cover is too large for the flange width."
            )


def _scaled_divisions(
    length: float,
    reference_length: float,
    total_divisions: int,
) -> int:
    if length <= 0.0:
        return 0
    if reference_length <= 0.0:
        return 1
    return max(
        1,
        int(round(int(total_divisions) * length / reference_length)),
    )


def _append_rect(
    components: list[FiberComponentData],
    *,
    name: str,
    material_tag: int,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    total_height: float,
    total_width: float,
    n_y: int,
    n_z: int,
) -> None:
    height = float(y1) - float(y0)
    width = float(z1) - float(z0)
    if height <= 1.0e-14 or width <= 1.0e-14:
        return

    components.append(
        FiberComponentData(
            "RectPatch",
            name,
            int(material_tag),
            {
                "y_center": 0.5 * (float(y0) + float(y1)),
                "z_center": 0.5 * (float(z0) + float(z1)),
                "width_y": height,
                "depth_z": width,
                "n_y": _scaled_divisions(
                    height,
                    total_height,
                    n_y,
                ),
                "n_z": _scaled_divisions(
                    width,
                    total_width,
                    n_z,
                ),
            },
        )
    )


def create_t_section_components(
    *,
    height: float,
    flange_width: float,
    flange_thickness: float,
    web_width: float,
    cover: float,
    core_material_tag: int,
    cover_material_tag: int,
    n_y: int = 24,
    n_z: int = 24,
) -> list[FiberComponentData]:
    """Create non-overlapping rectangular patches for a T fiber section.

    Local y is vertical, local z is horizontal, and the flange is at +y.
    The cover is measured inward from exposed faces. The flange/web
    interface inside the section is not treated as an exposed cover face.
    """
    _validate_common(
        height=height,
        flange_width=flange_width,
        flange_thickness=flange_thickness,
        web_width=web_width,
        cover=cover,
        is_i_section=False,
    )
    if int(n_y) < 1 or int(n_z) < 1:
        raise ValueError("Fiber subdivisions must be at least 1.")

    h = float(height)
    bf = float(flange_width)
    tf = float(flange_thickness)
    bw = float(web_width)
    c = float(cover)
    core_mat = int(core_material_tag)
    cover_mat = int(cover_material_tag)

    y_bottom = -0.5 * h
    y_top = 0.5 * h
    y_flange_bottom = y_top - tf
    z_flange_left = -0.5 * bf
    z_flange_right = 0.5 * bf
    z_web_left = -0.5 * bw
    z_web_right = 0.5 * bw

    components: list[FiberComponentData] = []

    if c <= 1.0e-14:
        _append_rect(
            components,
            name="T web",
            material_tag=core_mat,
            y0=y_bottom,
            y1=y_flange_bottom,
            z0=z_web_left,
            z1=z_web_right,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="T flange",
            material_tag=core_mat,
            y0=y_flange_bottom,
            y1=y_top,
            z0=z_flange_left,
            z1=z_flange_right,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )
        return components

    # Core: the web continues into the flange by one cover thickness,
    # so the internal web/flange interface is never assigned as cover.
    _append_rect(
        components,
        name="Core - web",
        material_tag=core_mat,
        y0=y_bottom + c,
        y1=y_flange_bottom + c,
        z0=z_web_left + c,
        z1=z_web_right - c,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )
    _append_rect(
        components,
        name="Core - flange",
        material_tag=core_mat,
        y0=y_flange_bottom + c,
        y1=y_top - c,
        z0=z_flange_left + c,
        z1=z_flange_right - c,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )

    # Exposed cover regions. These rectangles partition outer minus core
    # without overlap.
    _append_rect(
        components,
        name="Cover - flange top",
        material_tag=cover_mat,
        y0=y_top - c,
        y1=y_top,
        z0=z_flange_left,
        z1=z_flange_right,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )
    for side, z0, z1 in (
        ("left", z_flange_left, z_flange_left + c),
        ("right", z_flange_right - c, z_flange_right),
    ):
        _append_rect(
            components,
            name=f"Cover - flange {side} face",
            material_tag=cover_mat,
            y0=y_flange_bottom + c,
            y1=y_top - c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    for side, z0, z1 in (
        ("left", z_flange_left, z_web_left),
        ("right", z_web_right, z_flange_right),
    ):
        _append_rect(
            components,
            name=f"Cover - flange underside {side}",
            material_tag=cover_mat,
            y0=y_flange_bottom,
            y1=y_flange_bottom + c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    for side, z0, z1 in (
        ("left", z_web_left, z_web_left + c),
        ("right", z_web_right - c, z_web_right),
    ):
        _append_rect(
            components,
            name=f"Cover - web {side} face",
            material_tag=cover_mat,
            y0=y_bottom + c,
            y1=y_flange_bottom + c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    _append_rect(
        components,
        name="Cover - web bottom",
        material_tag=cover_mat,
        y0=y_bottom,
        y1=y_bottom + c,
        z0=z_web_left,
        z1=z_web_right,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )

    return components


def create_i_section_components(
    *,
    height: float,
    flange_width: float,
    flange_thickness: float,
    web_width: float,
    cover: float,
    core_material_tag: int,
    cover_material_tag: int,
    n_y: int = 24,
    n_z: int = 24,
) -> list[FiberComponentData]:
    """Create non-overlapping rectangular patches for a symmetric I section.

    Local y is vertical and local z is horizontal. Top and bottom flanges
    use the same width and thickness.
    """
    _validate_common(
        height=height,
        flange_width=flange_width,
        flange_thickness=flange_thickness,
        web_width=web_width,
        cover=cover,
        is_i_section=True,
    )
    if int(n_y) < 1 or int(n_z) < 1:
        raise ValueError("Fiber subdivisions must be at least 1.")

    h = float(height)
    bf = float(flange_width)
    tf = float(flange_thickness)
    bw = float(web_width)
    c = float(cover)
    core_mat = int(core_material_tag)
    cover_mat = int(cover_material_tag)

    y_bottom = -0.5 * h
    y_top = 0.5 * h
    y_bottom_flange_top = y_bottom + tf
    y_top_flange_bottom = y_top - tf
    z_flange_left = -0.5 * bf
    z_flange_right = 0.5 * bf
    z_web_left = -0.5 * bw
    z_web_right = 0.5 * bw

    components: list[FiberComponentData] = []

    if c <= 1.0e-14:
        _append_rect(
            components,
            name="I bottom flange",
            material_tag=core_mat,
            y0=y_bottom,
            y1=y_bottom_flange_top,
            z0=z_flange_left,
            z1=z_flange_right,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="I web",
            material_tag=core_mat,
            y0=y_bottom_flange_top,
            y1=y_top_flange_bottom,
            z0=z_web_left,
            z1=z_web_right,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="I top flange",
            material_tag=core_mat,
            y0=y_top_flange_bottom,
            y1=y_top,
            z0=z_flange_left,
            z1=z_flange_right,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )
        return components

    # Core patches.
    _append_rect(
        components,
        name="Core - bottom flange",
        material_tag=core_mat,
        y0=y_bottom + c,
        y1=y_bottom_flange_top - c,
        z0=z_flange_left + c,
        z1=z_flange_right - c,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )
    _append_rect(
        components,
        name="Core - web",
        material_tag=core_mat,
        y0=y_bottom_flange_top - c,
        y1=y_top_flange_bottom + c,
        z0=z_web_left + c,
        z1=z_web_right - c,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )
    _append_rect(
        components,
        name="Core - top flange",
        material_tag=core_mat,
        y0=y_top_flange_bottom + c,
        y1=y_top - c,
        z0=z_flange_left + c,
        z1=z_flange_right - c,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )

    # Top exposed cover.
    _append_rect(
        components,
        name="Cover - top face",
        material_tag=cover_mat,
        y0=y_top - c,
        y1=y_top,
        z0=z_flange_left,
        z1=z_flange_right,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )
    for side, z0, z1 in (
        ("left", z_flange_left, z_flange_left + c),
        ("right", z_flange_right - c, z_flange_right),
    ):
        _append_rect(
            components,
            name=f"Cover - top flange {side} face",
            material_tag=cover_mat,
            y0=y_top_flange_bottom + c,
            y1=y_top - c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    for side, z0, z1 in (
        ("left", z_flange_left, z_web_left),
        ("right", z_web_right, z_flange_right),
    ):
        _append_rect(
            components,
            name=f"Cover - top flange underside {side}",
            material_tag=cover_mat,
            y0=y_top_flange_bottom,
            y1=y_top_flange_bottom + c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    # Web side cover.
    for side, z0, z1 in (
        ("left", z_web_left, z_web_left + c),
        ("right", z_web_right - c, z_web_right),
    ):
        _append_rect(
            components,
            name=f"Cover - web {side} face",
            material_tag=cover_mat,
            y0=y_bottom_flange_top - c,
            y1=y_top_flange_bottom + c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    # Bottom flange upper exposed wings.
    for side, z0, z1 in (
        ("left", z_flange_left, z_web_left),
        ("right", z_web_right, z_flange_right),
    ):
        _append_rect(
            components,
            name=f"Cover - bottom flange top {side}",
            material_tag=cover_mat,
            y0=y_bottom_flange_top - c,
            y1=y_bottom_flange_top,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    for side, z0, z1 in (
        ("left", z_flange_left, z_flange_left + c),
        ("right", z_flange_right - c, z_flange_right),
    ):
        _append_rect(
            components,
            name=f"Cover - bottom flange {side} face",
            material_tag=cover_mat,
            y0=y_bottom + c,
            y1=y_bottom_flange_top - c,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=bf,
            n_y=n_y,
            n_z=n_z,
        )

    _append_rect(
        components,
        name="Cover - bottom face",
        material_tag=cover_mat,
        y0=y_bottom,
        y1=y_bottom + c,
        z0=z_flange_left,
        z1=z_flange_right,
        total_height=h,
        total_width=bf,
        n_y=n_y,
        n_z=n_z,
    )

    return components


def create_rectangle_section_components(
    *,
    height: float,
    width: float,
    cover: float,
    core_material_tag: int,
    cover_material_tag: int,
    n_y: int = 24,
    n_z: int = 24,
    rebar_material_tag: int | None = None,
    bar_diameter: float = 0.0,
    bars_top: int = 0,
    bars_bottom: int = 0,
    side_bars_each: int = 0,
) -> list[FiberComponentData]:
    """Create a rectangular RC section with non-overlapping core/cover.

    Local y is vertical and local z is horizontal. Rebar counts on the
    top/bottom rows include the row endpoints. side_bars_each adds
    intermediate bars on each vertical face and therefore does not duplicate
    the top/bottom corner bars.
    """
    h = float(height)
    b = float(width)
    cvr = float(cover)
    if h <= 0.0 or b <= 0.0:
        raise ValueError("Rectangle dimensions must be positive.")
    if cvr < 0.0:
        raise ValueError("Concrete cover cannot be negative.")
    if 2.0 * cvr >= min(h, b) and cvr > 0.0:
        raise ValueError(
            "Cover is too large for the rectangle dimensions."
        )
    if int(n_y) < 1 or int(n_z) < 1:
        raise ValueError("Fiber subdivisions must be at least 1.")

    core_mat = int(core_material_tag)
    cover_mat = int(cover_material_tag)
    components: list[FiberComponentData] = []

    y0 = -0.5 * h
    y1 = 0.5 * h
    z0 = -0.5 * b
    z1 = 0.5 * b

    if cvr <= 1.0e-14:
        _append_rect(
            components,
            name="Rectangle concrete",
            material_tag=core_mat,
            y0=y0,
            y1=y1,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=b,
            n_y=n_y,
            n_z=n_z,
        )
    else:
        _append_rect(
            components,
            name="Core",
            material_tag=core_mat,
            y0=y0 + cvr,
            y1=y1 - cvr,
            z0=z0 + cvr,
            z1=z1 - cvr,
            total_height=h,
            total_width=b,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="Cover - top",
            material_tag=cover_mat,
            y0=y1 - cvr,
            y1=y1,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=b,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="Cover - bottom",
            material_tag=cover_mat,
            y0=y0,
            y1=y0 + cvr,
            z0=z0,
            z1=z1,
            total_height=h,
            total_width=b,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="Cover - left",
            material_tag=cover_mat,
            y0=y0 + cvr,
            y1=y1 - cvr,
            z0=z0,
            z1=z0 + cvr,
            total_height=h,
            total_width=b,
            n_y=n_y,
            n_z=n_z,
        )
        _append_rect(
            components,
            name="Cover - right",
            material_tag=cover_mat,
            y0=y0 + cvr,
            y1=y1 - cvr,
            z0=z1 - cvr,
            z1=z1,
            total_height=h,
            total_width=b,
            n_y=n_y,
            n_z=n_z,
        )

    top = max(0, int(bars_top))
    bottom = max(0, int(bars_bottom))
    sides = max(0, int(side_bars_each))
    rebar_count = top + bottom + 2 * sides
    if rebar_count <= 0:
        return components
    if rebar_material_tag is None:
        raise ValueError(
            "A rebar material is required when reinforcement is enabled."
        )
    db = float(bar_diameter)
    if db <= 0.0:
        raise ValueError(
            "Bar diameter must be positive when reinforcement is enabled."
        )

    offset = cvr + 0.5 * db
    if 2.0 * offset >= h or 2.0 * offset >= b:
        raise ValueError(
            "Cover plus half the bar diameter leaves no valid rebar region."
        )
    bar_area = math.pi * db**2 / 4.0
    y_bot_bar = y0 + offset
    y_top_bar = y1 - offset
    z_left_bar = z0 + offset
    z_right_bar = z1 - offset
    rebar_mat = int(rebar_material_tag)

    if top > 0:
        components.append(
            FiberComponentData(
                "StraightLayer",
                "Rebar - top",
                rebar_mat,
                {
                    "y_i": y_top_bar,
                    "z_i": z_left_bar,
                    "y_j": y_top_bar,
                    "z_j": z_right_bar,
                    "n_bars": top,
                    "bar_area": bar_area,
                },
            )
        )
    if bottom > 0:
        components.append(
            FiberComponentData(
                "StraightLayer",
                "Rebar - bottom",
                rebar_mat,
                {
                    "y_i": y_bot_bar,
                    "z_i": z_left_bar,
                    "y_j": y_bot_bar,
                    "z_j": z_right_bar,
                    "n_bars": bottom,
                    "bar_area": bar_area,
                },
            )
        )

    if sides > 0:
        for index in range(1, sides + 1):
            fraction = index / (sides + 1)
            y = y_bot_bar + fraction * (y_top_bar - y_bot_bar)
            components.append(
                FiberComponentData(
                    "SingleFiber",
                    f"Rebar - left side {index}",
                    rebar_mat,
                    {
                        "y": y,
                        "z": z_left_bar,
                        "area": bar_area,
                    },
                )
            )
            components.append(
                FiberComponentData(
                    "SingleFiber",
                    f"Rebar - right side {index}",
                    rebar_mat,
                    {
                        "y": y,
                        "z": z_right_bar,
                        "area": bar_area,
                    },
                )
            )

    return components


def create_circle_section_components(
    *,
    outer_diameter: float,
    inner_diameter: float,
    cover: float,
    core_material_tag: int,
    cover_material_tag: int,
    n_radial: int = 12,
    n_circum: int = 48,
    rebar_material_tag: int | None = None,
    bar_diameter: float = 0.0,
    outer_bars: int = 0,
    inner_bars: int = 0,
) -> list[FiberComponentData]:
    """Create solid or hollow circular RC section components.

    inner_diameter=0 creates a solid circle. For a hollow section the
    concrete cover is applied at both the outer and inner exposed faces.
    Optional reinforcement can be placed in outer and inner circular layers.
    """
    do = float(outer_diameter)
    di = float(inner_diameter)
    cvr = float(cover)
    if do <= 0.0:
        raise ValueError("Outer diameter must be positive.")
    if di < 0.0 or di >= do:
        raise ValueError(
            "Inner diameter must satisfy 0 <= Di < Do."
        )
    if cvr < 0.0:
        raise ValueError("Concrete cover cannot be negative.")
    if int(n_radial) < 1 or int(n_circum) < 1:
        raise ValueError("Fiber subdivisions must be at least 1.")

    ro = 0.5 * do
    ri = 0.5 * di
    wall = ro - ri
    if ri > 0.0:
        if cvr > 0.0 and 2.0 * cvr >= wall:
            raise ValueError(
                "Cover is too large for the hollow circular wall thickness."
            )
    elif cvr >= ro and cvr > 0.0:
        raise ValueError(
            "Cover is too large for the solid circular section."
        )

    core_mat = int(core_material_tag)
    cover_mat = int(cover_material_tag)
    nr = int(n_radial)
    nt = int(n_circum)
    components: list[FiberComponentData] = []

    def radial_divisions(thickness: float) -> int:
        return max(1, int(round(nr * thickness / wall)))

    def add_ring(
        name: str,
        material_tag: int,
        r_inner: float,
        r_outer: float,
    ) -> None:
        thickness = r_outer - r_inner
        if thickness <= 1.0e-14:
            return
        components.append(
            FiberComponentData(
                "CircPatch",
                name,
                material_tag,
                {
                    "y_center": 0.0,
                    "z_center": 0.0,
                    "r_inner": r_inner,
                    "r_outer": r_outer,
                    "n_radial": radial_divisions(thickness),
                    "n_circum": nt,
                    "start_angle": 0.0,
                    "end_angle": 360.0,
                },
            )
        )

    if cvr <= 1.0e-14:
        add_ring("Circular concrete", core_mat, ri, ro)
    elif ri <= 1.0e-14:
        add_ring("Core", core_mat, 0.0, ro - cvr)
        add_ring("Cover - outer", cover_mat, ro - cvr, ro)
    else:
        add_ring("Cover - inner", cover_mat, ri, ri + cvr)
        add_ring("Core", core_mat, ri + cvr, ro - cvr)
        add_ring("Cover - outer", cover_mat, ro - cvr, ro)

    n_outer = max(0, int(outer_bars))
    n_inner = max(0, int(inner_bars))
    if n_inner > 0 and ri <= 1.0e-14:
        raise ValueError(
            "Inner rebar layer requires a hollow circular section."
        )
    if n_outer + n_inner <= 0:
        return components
    if rebar_material_tag is None:
        raise ValueError(
            "A rebar material is required when reinforcement is enabled."
        )
    db = float(bar_diameter)
    if db <= 0.0:
        raise ValueError(
            "Bar diameter must be positive when reinforcement is enabled."
        )

    bar_area = math.pi * db**2 / 4.0
    rebar_mat = int(rebar_material_tag)
    if n_outer > 0:
        radius = ro - cvr - 0.5 * db
        if radius <= ri + 0.5 * db:
            raise ValueError(
                "Outer rebar layer does not fit inside the concrete wall."
            )
        components.append(
            FiberComponentData(
                "CircLayer",
                "Rebar - outer ring",
                rebar_mat,
                {
                    "y_center": 0.0,
                    "z_center": 0.0,
                    "radius": radius,
                    "n_bars": n_outer,
                    "bar_area": bar_area,
                    "start_angle": 0.0,
                    "end_angle": 360.0,
                },
            )
        )
    if n_inner > 0:
        radius = ri + cvr + 0.5 * db
        if radius >= ro - 0.5 * db:
            raise ValueError(
                "Inner rebar layer does not fit inside the concrete wall."
            )
        components.append(
            FiberComponentData(
                "CircLayer",
                "Rebar - inner ring",
                rebar_mat,
                {
                    "y_center": 0.0,
                    "z_center": 0.0,
                    "radius": radius,
                    "n_bars": n_inner,
                    "bar_area": bar_area,
                    "start_angle": 0.0,
                    "end_angle": 360.0,
                },
            )
        )

    return components
