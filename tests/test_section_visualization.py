import math

from openseespy_studio.project import (
    FiberComponentData,
    FiberData,
    SectionData,
)
from openseespy_studio.section_visualization import (
    component_bounds,
    equivalent_fiber_radius,
    section_dimensions,
    section_preview_bounds,
)


def test_rect_patch_preview_bounds_use_full_component_geometry():
    component = FiberComponentData(
        "RectPatch",
        "Concrete",
        1,
        {
            "y_center": 0.1,
            "z_center": -0.2,
            "width_y": 0.6,
            "depth_z": 0.4,
            "n_y": 6,
            "n_z": 4,
        },
    )

    assert component_bounds(component) == (
        -0.2,
        0.4,
        -0.4,
        0.0,
    )


def test_section_dimensions_follow_local_y_z_extents():
    section = SectionData(
        1,
        "Rect",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Patch",
                1,
                {
                    "y_center": 0.0,
                    "z_center": 0.0,
                    "width_y": 0.5,
                    "depth_z": 0.3,
                    "n_y": 10,
                    "n_z": 6,
                },
            )
        ],
    )

    height_y, breadth_z = section_dimensions(section)

    assert math.isclose(height_y, 0.5)
    assert math.isclose(breadth_z, 0.3)


def test_rebar_layer_bounds_include_physical_bar_radius():
    bar_area = math.pi * 0.02**2 / 4.0
    component = FiberComponentData(
        "StraightLayer",
        "Bars",
        2,
        {
            "y_i": -0.1,
            "z_i": -0.15,
            "y_j": 0.1,
            "z_j": 0.15,
            "n_bars": 4,
            "bar_area": bar_area,
        },
    )
    y_min, y_max, z_min, z_max = component_bounds(component)

    assert math.isclose(y_min, -0.11)
    assert math.isclose(y_max, 0.11)
    assert math.isclose(z_min, -0.16)
    assert math.isclose(z_max, 0.16)


def test_preview_bounds_combine_patch_rebar_and_manual_fibers():
    section = SectionData(
        1,
        "Mixed",
        "Fiber",
        {"GJ": 1.0e6},
        fibers=[
            FiberData(
                y=0.0,
                z=0.4,
                area=math.pi * 0.01**2,
                material_tag=3,
            )
        ],
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Patch",
                1,
                {
                    "width_y": 0.4,
                    "depth_z": 0.4,
                    "n_y": 4,
                    "n_z": 4,
                },
            )
        ],
    )

    bounds = section_preview_bounds(section)

    assert bounds is not None
    assert math.isclose(bounds[0], -0.2)
    assert math.isclose(bounds[1], 0.2)
    assert math.isclose(bounds[2], -0.2)
    assert math.isclose(bounds[3], 0.41)


def test_equivalent_fiber_radius_recovers_circle_radius():
    area = math.pi * 0.025**2

    assert math.isclose(
        equivalent_fiber_radius(area),
        0.025,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
