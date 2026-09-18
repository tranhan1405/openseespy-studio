import math

from openseespy_studio.generator import section_to_openseespy
from openseespy_studio.project import (
    FiberComponentData,
    FiberData,
    MaterialData,
    ProjectDatabase,
    SectionData,
)


def _material(tag: int, name: str = "Mat") -> MaterialData:
    return MaterialData(
        tag=tag,
        name=name,
        material_type="Elastic",
        parameters={"E": 2.0e11},
    )


def test_rectangle_patch_compiles_to_cell_center_fibers():
    component = FiberComponentData(
        "RectPatch",
        "Core",
        1,
        {
            "y_center": 0.0,
            "z_center": 0.0,
            "width_y": 0.4,
            "depth_z": 0.2,
            "n_y": 4,
            "n_z": 2,
        },
    )

    fibers = component.compile_fibers()

    assert len(fibers) == 8
    assert all(
        math.isclose(fiber.area, 0.01, rel_tol=0.0, abs_tol=1e-12)
        for fiber in fibers
    )
    assert math.isclose(
        sum(fiber.area for fiber in fibers),
        0.08,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert {round(fiber.y, 6) for fiber in fibers} == {
        -0.15,
        -0.05,
        0.05,
        0.15,
    }
    assert {round(fiber.z, 6) for fiber in fibers} == {-0.05, 0.05}


def test_circular_patch_preserves_annular_sector_area():
    component = FiberComponentData(
        "CircPatch",
        "Ring",
        2,
        {
            "y_center": 0.1,
            "z_center": -0.2,
            "r_inner": 0.1,
            "r_outer": 0.3,
            "n_radial": 4,
            "n_circum": 24,
            "start_angle": 0.0,
            "end_angle": 180.0,
        },
    )

    fibers = component.compile_fibers()
    expected = 0.5 * math.pi * (0.3**2 - 0.1**2)

    assert len(fibers) == 96
    assert math.isclose(
        sum(fiber.area for fiber in fibers),
        expected,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_straight_rebar_layer_places_bars_including_endpoints():
    area = math.pi * 0.02**2 / 4.0
    component = FiberComponentData(
        "StraightLayer",
        "Bottom bars",
        3,
        {
            "y_i": -0.15,
            "z_i": -0.15,
            "y_j": 0.15,
            "z_j": -0.15,
            "n_bars": 4,
            "bar_area": area,
        },
    )

    fibers = component.compile_fibers()

    assert [round(fiber.y, 6) for fiber in fibers] == [
        -0.15,
        -0.05,
        0.05,
        0.15,
    ]
    assert all(math.isclose(fiber.z, -0.15) for fiber in fibers)
    assert all(math.isclose(fiber.area, area) for fiber in fibers)


def test_full_circular_rebar_layer_does_not_duplicate_end_bar():
    component = FiberComponentData(
        "CircLayer",
        "Bars",
        4,
        {
            "y_center": 0.0,
            "z_center": 0.0,
            "radius": 0.2,
            "n_bars": 8,
            "bar_area": 1.0e-4,
            "start_angle": 0.0,
            "end_angle": 360.0,
        },
    )

    fibers = component.compile_fibers()
    coordinates = {
        (round(fiber.y, 10), round(fiber.z, 10))
        for fiber in fibers
    }

    assert len(fibers) == 8
    assert len(coordinates) == 8
    assert abs(sum(fiber.y for fiber in fibers)) < 1e-12
    assert abs(sum(fiber.z for fiber in fibers)) < 1e-12


def test_section_combines_builder_components_and_manual_fibers():
    section = SectionData(
        tag=1,
        name="Mixed",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fibers=[FiberData(0.5, 0.0, 2.0e-4, 2)],
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Core",
                1,
                {
                    "width_y": 0.2,
                    "depth_z": 0.2,
                    "n_y": 2,
                    "n_z": 2,
                },
            )
        ],
    )

    fibers = section.compiled_fibers()
    area, centroid = section.fiber_area_and_centroid()

    assert len(fibers) == 5
    assert math.isclose(area, 0.0402, rel_tol=0.0, abs_tol=1e-12)
    assert centroid[0] > 0.0
    assert section.fiber_material_tags() == {1, 2}


def test_fiber_builder_round_trip_is_editable_not_flattened():
    project = ProjectDatabase()
    project.add_material(_material(1, "Concrete"))
    section = SectionData(
        2,
        "RC Column",
        "Fiber",
        {"GJ": 2.0e6},
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Concrete core",
                1,
                {
                    "width_y": 0.4,
                    "depth_z": 0.4,
                    "n_y": 20,
                    "n_z": 20,
                },
            )
        ],
    )
    project.add_section(section)

    restored = ProjectDatabase.from_dict(project.to_dict())
    component = restored.sections[2].fiber_components[0]

    assert component.component_type == "RectPatch"
    assert component.name == "Concrete core"
    assert component.parameters["width_y"] == 0.4
    assert component.parameters["n_y"] == 20.0
    assert len(restored.sections[2].compiled_fibers()) == 400


def test_generator_compiles_builder_to_opensees_fibers():
    section = SectionData(
        5,
        "Builder",
        "Fiber",
        {"GJ": 3.0e6},
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Patch",
                7,
                {
                    "width_y": 0.2,
                    "depth_z": 0.1,
                    "n_y": 2,
                    "n_z": 2,
                },
            )
        ],
    )

    lines = section_to_openseespy(section)

    assert lines[0] == "ops.section('Fiber', 5, '-GJ', 3e+06)"
    assert len([line for line in lines if line.startswith("ops.fiber(")]) == 4
    assert not any("ops.patch(" in line for line in lines)


def test_project_validates_material_references_inside_builder_components():
    project = ProjectDatabase()
    section = SectionData(
        1,
        "Bad",
        "Fiber",
        {"GJ": 1.0e6},
        fiber_components=[
            FiberComponentData(
                "SingleFiber",
                "Fiber",
                99,
                {"y": 0.0, "z": 0.0, "area": 1.0e-4},
            )
        ],
    )

    try:
        project.add_section(section)
    except ValueError as exc:
        assert "missing material" in str(exc)
        assert "99" in str(exc)
    else:
        raise AssertionError("Expected builder material reference validation")


def test_invalid_fiber_component_geometry_is_rejected():
    try:
        FiberComponentData(
            "CircPatch",
            "Bad Ring",
            1,
            {
                "r_inner": 0.2,
                "r_outer": 0.1,
            },
        )
    except ValueError as exc:
        assert "inner radius" in str(exc)
    else:
        raise AssertionError("Expected invalid circular patch to fail")
