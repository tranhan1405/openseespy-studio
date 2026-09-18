from __future__ import annotations

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
