from openseespy_studio.project import (
    FiberComponentData,
    MaterialData,
    SectionData,
)
from openseespy_studio.section_templates import (
    create_circle_section_components,
    create_rectangle_section_components,
)
from openseespy_studio.section_validation import (
    validate_fiber_section_geometry,
)


def concrete(tag: int) -> MaterialData:
    return MaterialData(
        tag=tag,
        name=f"Concrete {tag}",
        material_type="Concrete02",
    )


def steel(tag: int) -> MaterialData:
    return MaterialData(
        tag=tag,
        name=f"Steel {tag}",
        material_type="Steel02",
    )


def codes(issues):
    return {issue.code for issue in issues}


def test_rectangle_rc_template_passes_geometry_validation():
    materials = {
        1: concrete(1),
        2: concrete(2),
        3: steel(3),
    }
    section = SectionData(
        1,
        "Rectangle RC",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=create_rectangle_section_components(
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
        ),
    )

    issues = validate_fiber_section_geometry(section, materials)

    assert not [
        issue for issue in issues
        if issue.severity == "ERROR"
    ]
    assert "PATCH_OVERLAP" not in codes(issues)
    assert "REBAR_OUTSIDE_CONCRETE" not in codes(issues)


def test_hollow_circle_rebar_inside_void_is_an_error():
    materials = {
        1: concrete(1),
        2: concrete(2),
        3: steel(3),
    }
    components = create_circle_section_components(
        outer_diameter=0.60,
        inner_diameter=0.30,
        cover=0.04,
        core_material_tag=1,
        cover_material_tag=2,
    )
    components.append(
        FiberComponentData(
            "SingleFiber",
            "Bad bar",
            3,
            {
                "y": 0.0,
                "z": 0.0,
                "area": 3.0e-4,
            },
        )
    )
    section = SectionData(
        2,
        "Bad Hollow",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=components,
    )

    issues = validate_fiber_section_geometry(section, materials)

    assert "REBAR_OUTSIDE_CONCRETE" in codes(issues)


def test_overlapping_rectangular_patches_are_reported():
    section = SectionData(
        3,
        "Overlap",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "A",
                1,
                {
                    "y_center": 0.0,
                    "z_center": 0.0,
                    "width_y": 0.4,
                    "depth_z": 0.4,
                    "n_y": 4,
                    "n_z": 4,
                },
            ),
            FiberComponentData(
                "RectPatch",
                "B",
                1,
                {
                    "y_center": 0.1,
                    "z_center": 0.0,
                    "width_y": 0.4,
                    "depth_z": 0.4,
                    "n_y": 4,
                    "n_z": 4,
                },
            ),
        ],
    )

    issues = validate_fiber_section_geometry(
        section,
        {1: concrete(1)},
    )

    assert "PATCH_OVERLAP" in codes(issues)


def test_duplicate_rebar_and_nonpositive_gj_are_reported():
    materials = {
        1: concrete(1),
        3: steel(3),
    }
    section = SectionData(
        4,
        "Duplicates",
        "Fiber",
        {"GJ": 0.0},
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Concrete",
                1,
                {
                    "width_y": 0.5,
                    "depth_z": 0.5,
                    "n_y": 4,
                    "n_z": 4,
                },
            ),
            FiberComponentData(
                "SingleFiber",
                "Bar A",
                3,
                {"y": 0.1, "z": 0.1, "area": 1.0e-4},
            ),
            FiberComponentData(
                "SingleFiber",
                "Bar B",
                3,
                {"y": 0.1, "z": 0.1, "area": 1.0e-4},
            ),
        ],
    )

    issues = validate_fiber_section_geometry(section, materials)

    assert "NONPOSITIVE_GJ" in codes(issues)
    assert "DUPLICATE_REBAR" in codes(issues)


def test_concentric_circular_patch_gap_is_reported():
    materials = {1: concrete(1)}
    section = SectionData(
        5,
        "Gap",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=[
            FiberComponentData(
                "CircPatch",
                "Inner",
                1,
                {
                    "r_inner": 0.0,
                    "r_outer": 0.10,
                    "n_radial": 2,
                    "n_circum": 16,
                },
            ),
            FiberComponentData(
                "CircPatch",
                "Outer",
                1,
                {
                    "r_inner": 0.12,
                    "r_outer": 0.20,
                    "n_radial": 2,
                    "n_circum": 16,
                },
            ),
        ],
    )

    issues = validate_fiber_section_geometry(section, materials)

    assert "CIRCULAR_GAP" in codes(issues)
