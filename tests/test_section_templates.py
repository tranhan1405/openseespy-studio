import math

from openseespy_studio.project import SectionData
from openseespy_studio.section_templates import (
    create_i_section_components,
    create_t_section_components,
)
from openseespy_studio.section_visualization import (
    section_dimensions,
    section_preview_bounds,
)


def _component_area(component) -> float:
    p = component.parameters
    return p["width_y"] * p["depth_z"]


def test_t_template_partitions_outer_shape_without_overlap():
    h = 0.60
    bf = 0.80
    tf = 0.15
    bw = 0.30
    components = create_t_section_components(
        height=h,
        flange_width=bf,
        flange_thickness=tf,
        web_width=bw,
        cover=0.04,
        core_material_tag=1,
        cover_material_tag=2,
        n_y=24,
        n_z=32,
    )

    expected_area = bf * tf + bw * (h - tf)
    actual_area = sum(_component_area(component) for component in components)

    assert math.isclose(
        actual_area,
        expected_area,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert {component.material_tag for component in components} == {1, 2}
    assert any(component.name == "Core - web" for component in components)
    assert any(component.name == "Core - flange" for component in components)

    section = SectionData(
        1,
        "T",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=components,
    )
    height_y, width_z = section_dimensions(section)
    assert math.isclose(height_y, h)
    assert math.isclose(width_z, bf)


def test_t_template_keeps_internal_web_flange_interface_out_of_cover():
    h = 0.60
    tf = 0.15
    cover = 0.04
    components = create_t_section_components(
        height=h,
        flange_width=0.80,
        flange_thickness=tf,
        web_width=0.30,
        cover=cover,
        core_material_tag=1,
        cover_material_tag=2,
    )

    web_core = next(
        component
        for component in components
        if component.name == "Core - web"
    )
    p = web_core.parameters
    web_core_top = p["y_center"] + 0.5 * p["width_y"]
    flange_bottom = 0.5 * h - tf

    assert math.isclose(
        web_core_top,
        flange_bottom + cover,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )


def test_i_template_partitions_outer_shape_without_overlap():
    h = 0.80
    bf = 0.70
    tf = 0.14
    bw = 0.25
    components = create_i_section_components(
        height=h,
        flange_width=bf,
        flange_thickness=tf,
        web_width=bw,
        cover=0.035,
        core_material_tag=10,
        cover_material_tag=20,
        n_y=32,
        n_z=28,
    )

    expected_area = 2.0 * bf * tf + bw * (h - 2.0 * tf)
    actual_area = sum(_component_area(component) for component in components)

    assert math.isclose(
        actual_area,
        expected_area,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert {component.material_tag for component in components} == {10, 20}
    assert any(
        component.name == "Core - bottom flange"
        for component in components
    )
    assert any(component.name == "Core - web" for component in components)
    assert any(
        component.name == "Core - top flange"
        for component in components
    )

    section = SectionData(
        2,
        "I",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=components,
    )
    bounds = section_preview_bounds(section)
    assert bounds is not None
    assert math.isclose(bounds[0], -0.5 * h)
    assert math.isclose(bounds[1], 0.5 * h)
    assert math.isclose(bounds[2], -0.5 * bf)
    assert math.isclose(bounds[3], 0.5 * bf)


def test_zero_cover_templates_reduce_to_shape_rectangles():
    t_components = create_t_section_components(
        height=0.60,
        flange_width=0.80,
        flange_thickness=0.15,
        web_width=0.30,
        cover=0.0,
        core_material_tag=1,
        cover_material_tag=2,
    )
    i_components = create_i_section_components(
        height=0.80,
        flange_width=0.70,
        flange_thickness=0.14,
        web_width=0.25,
        cover=0.0,
        core_material_tag=1,
        cover_material_tag=2,
    )

    assert len(t_components) == 2
    assert len(i_components) == 3
    assert all(component.material_tag == 1 for component in t_components)
    assert all(component.material_tag == 1 for component in i_components)


def test_template_validation_rejects_invalid_geometry():
    try:
        create_i_section_components(
            height=0.50,
            flange_width=0.40,
            flange_thickness=0.26,
            web_width=0.20,
            cover=0.03,
            core_material_tag=1,
            cover_material_tag=2,
        )
    except ValueError as exc:
        assert "2 × flange thickness" in str(exc)
    else:
        raise AssertionError("Expected invalid I-section geometry to fail")

    try:
        create_t_section_components(
            height=0.60,
            flange_width=0.50,
            flange_thickness=0.12,
            web_width=0.10,
            cover=0.055,
            core_material_tag=1,
            cover_material_tag=2,
        )
    except ValueError as exc:
        assert "Cover is too large" in str(exc)
    else:
        raise AssertionError("Expected excessive cover to fail")
