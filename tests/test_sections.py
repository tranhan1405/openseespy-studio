from openseespy_studio.generator import section_to_openseespy, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    FiberData,
    MaterialData,
    ProjectDatabase,
    SectionData,
)


def material(tag: int = 1) -> MaterialData:
    return MaterialData(
        tag=tag,
        name="Steel",
        material_type="Elastic",
        parameters={"E": 2.0e11},
    )


def test_elastic_section_round_trip():
    project = ProjectDatabase()
    section = SectionData(
        tag=1,
        name="Column",
        section_type="Elastic",
        parameters={
            "E": 2.0e11,
            "A": 0.03,
            "Iz": 1.0e-4,
            "Iy": 8.0e-5,
            "G": 7.7e10,
            "J": 5.0e-5,
        },
    )
    project.add_section(section)

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.sections[1].name == "Column"
    assert restored.sections[1].parameters["A"] == 0.03


def test_fiber_section_validates_material_references():
    project = ProjectDatabase()
    project.add_material(material(1))
    section = SectionData(
        tag=2,
        name="Fiber",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fibers=[
            FiberData(y=-0.1, z=0.0, area=1.0e-4, material_tag=1),
            FiberData(y=0.1, z=0.0, area=1.0e-4, material_tag=1),
        ],
    )

    project.add_section(section)

    assert project.sections_using_material(1) == [2]


def test_fiber_section_rejects_missing_material():
    project = ProjectDatabase()
    section = SectionData(
        tag=1,
        name="Fiber",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fibers=[
            FiberData(y=0.0, z=0.0, area=1.0e-4, material_tag=99),
        ],
    )

    try:
        project.add_section(section)
    except ValueError as exc:
        assert "missing material" in str(exc)
    else:
        raise AssertionError("Expected missing material validation error")


def test_section_generator_elastic_and_fiber():
    elastic = SectionData(
        tag=1,
        name="Elastic",
        section_type="Elastic",
        parameters={
            "E": 2.0e11,
            "A": 0.02,
            "Iz": 8.0e-5,
            "Iy": 8.0e-5,
            "G": 7.6923e10,
            "J": 8.0e-5,
        },
    )
    fiber = SectionData(
        tag=2,
        name="Fiber",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fibers=[
            FiberData(y=0.0, z=0.0, area=1.0e-4, material_tag=1),
        ],
    )

    elastic_lines = section_to_openseespy(elastic)
    fiber_lines = section_to_openseespy(fiber)

    assert elastic_lines[0].startswith("ops.section('Elastic', 1")
    assert fiber_lines[0].startswith("ops.section('Fiber', 2")
    assert fiber_lines[1] == "ops.fiber(0, 0, 0.0001, 1)"


def test_full_script_contains_sections():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_element(1, 1, 2)

    mat = material(1)
    sec = SectionData(
        tag=1,
        name="Fiber",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fibers=[FiberData(0.0, 0.0, 1.0e-4, 1)],
    )

    script = to_openseespy(model, {1: mat}, {1: sec})

    assert "# Sections" in script
    assert "ops.section('Fiber', 1" in script
    assert "ops.fiber(0, 0, 0.0001, 1)" in script
