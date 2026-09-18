import math

from openseespy_studio.section_templates import (
    create_circle_section_components,
    create_rectangle_section_components,
)


def _rect_area(component) -> float:
    p = component.parameters
    return p["width_y"] * p["depth_z"]


def _ring_area(component) -> float:
    p = component.parameters
    return math.pi * (
        p["r_outer"]**2 - p["r_inner"]**2
    )


def test_rectangle_rc_template_partitions_core_and_cover_exactly():
    components = create_rectangle_section_components(
        height=0.50,
        width=0.40,
        cover=0.04,
        core_material_tag=1,
        cover_material_tag=2,
        n_y=20,
        n_z=16,
    )
    patches = [
        component
        for component in components
        if component.component_type == "RectPatch"
    ]

    assert len(patches) == 5
    assert math.isclose(
        sum(_rect_area(component) for component in patches),
        0.50 * 0.40,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert {component.material_tag for component in patches} == {1, 2}


def test_rectangle_rc_template_places_requested_rebars_without_duplicates():
    components = create_rectangle_section_components(
        height=0.50,
        width=0.40,
        cover=0.04,
        core_material_tag=1,
        cover_material_tag=2,
        rebar_material_tag=3,
        bar_diameter=0.02,
        bars_top=4,
        bars_bottom=4,
        side_bars_each=2,
    )

    rebar_fibers = []
    for component in components:
        if component.material_tag == 3:
            rebar_fibers.extend(component.compile_fibers())

    coordinates = {
        (round(fiber.y, 12), round(fiber.z, 12))
        for fiber in rebar_fibers
    }
    assert len(rebar_fibers) == 12
    assert len(coordinates) == 12


def test_circle_template_supports_solid_and_hollow_cover():
    solid = create_circle_section_components(
        outer_diameter=0.50,
        inner_diameter=0.0,
        cover=0.04,
        core_material_tag=1,
        cover_material_tag=2,
    )
    hollow = create_circle_section_components(
        outer_diameter=0.60,
        inner_diameter=0.30,
        cover=0.04,
        core_material_tag=1,
        cover_material_tag=2,
    )

    solid_patches = [
        component for component in solid
        if component.component_type == "CircPatch"
    ]
    hollow_patches = [
        component for component in hollow
        if component.component_type == "CircPatch"
    ]

    assert [component.name for component in solid_patches] == [
        "Core",
        "Cover - outer",
    ]
    assert [component.name for component in hollow_patches] == [
        "Cover - inner",
        "Core",
        "Cover - outer",
    ]

    expected = math.pi * (
        (0.60 / 2.0) ** 2 - (0.30 / 2.0) ** 2
    )
    assert math.isclose(
        sum(_ring_area(component) for component in hollow_patches),
        expected,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )


def test_hollow_circle_can_create_outer_and_inner_rebar_rings():
    components = create_circle_section_components(
        outer_diameter=0.80,
        inner_diameter=0.30,
        cover=0.05,
        core_material_tag=1,
        cover_material_tag=2,
        rebar_material_tag=3,
        bar_diameter=0.02,
        outer_bars=12,
        inner_bars=8,
    )

    layers = [
        component for component in components
        if component.component_type == "CircLayer"
    ]
    assert len(layers) == 2
    assert sum(
        len(component.compile_fibers())
        for component in layers
    ) == 20


def test_circle_template_rejects_cover_that_consumes_hollow_wall():
    try:
        create_circle_section_components(
            outer_diameter=0.50,
            inner_diameter=0.40,
            cover=0.03,
            core_material_tag=1,
            cover_material_tag=2,
        )
    except ValueError as exc:
        assert "wall thickness" in str(exc)
    else:
        raise AssertionError("Expected excessive hollow cover to fail")
