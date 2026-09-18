import math

from openseespy_studio.section_geometry import (
    circle_properties,
    i_section_properties,
    rectangle_properties,
    section_geometry_properties,
    t_section_properties,
)


def test_rectangle_geometry_properties_use_local_y_z_axes():
    props = rectangle_properties(height=0.50, width=0.30)

    assert math.isclose(props.area, 0.15)
    assert math.isclose(props.iy, 0.50 * 0.30**3 / 12.0)
    assert math.isclose(props.iz, 0.30 * 0.50**3 / 12.0)
    assert props.j > 0.0
    assert props.j_is_approximate


def test_circle_and_hollow_circle_properties_are_exact():
    solid = circle_properties(outer_diameter=0.40)
    hollow = circle_properties(
        outer_diameter=0.40,
        inner_diameter=0.20,
    )

    assert math.isclose(
        solid.area,
        math.pi * 0.40**2 / 4.0,
    )
    assert math.isclose(
        solid.iy,
        math.pi * 0.40**4 / 64.0,
    )
    assert math.isclose(
        solid.j,
        math.pi * 0.40**4 / 32.0,
    )
    assert not solid.j_is_approximate

    assert math.isclose(
        hollow.area,
        math.pi * (0.40**2 - 0.20**2) / 4.0,
    )
    assert math.isclose(hollow.iy, hollow.iz)
    assert math.isclose(hollow.j, 2.0 * hollow.iy)


def test_i_section_geometry_matches_composite_rectangles():
    h = 0.60
    bf = 0.30
    tf = 0.04
    bw = 0.02
    props = i_section_properties(
        height=h,
        flange_width=bf,
        flange_thickness=tf,
        web_width=bw,
    )

    hw = h - 2.0 * tf
    expected_area = 2.0 * bf * tf + bw * hw
    expected_iy = (
        2.0 * tf * bf**3 / 12.0
        + hw * bw**3 / 12.0
    )

    assert math.isclose(props.area, expected_area)
    assert math.isclose(props.iy, expected_iy)
    assert math.isclose(props.centroid_y, 0.0)
    assert props.j_is_approximate


def test_t_section_geometry_reports_shifted_centroid():
    props = t_section_properties(
        height=0.60,
        flange_width=0.50,
        flange_thickness=0.12,
        web_width=0.20,
    )

    assert math.isclose(
        props.area,
        0.50 * 0.12 + 0.20 * (0.60 - 0.12),
    )
    assert props.centroid_y > 0.0
    assert props.iy > 0.0
    assert props.iz > 0.0


def test_geometry_dispatch_and_validation():
    props = section_geometry_properties(
        "Hollow Circle",
        outer_diameter=0.50,
        inner_diameter=0.30,
    )
    assert props.area > 0.0

    try:
        circle_properties(
            outer_diameter=0.30,
            inner_diameter=0.31,
        )
    except ValueError as exc:
        assert "smaller than outer diameter" in str(exc)
    else:
        raise AssertionError("Expected invalid hollow circle to fail")
