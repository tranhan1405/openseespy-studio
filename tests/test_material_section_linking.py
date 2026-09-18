from math import isclose

from openseespy_studio.generator import section_to_openseespy, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    MaterialData,
    ProjectDatabase,
    SectionData,
)


def steel_material(tag: int = 1) -> MaterialData:
    return MaterialData(
        tag=tag,
        name="S355",
        material_type="Steel02",
        parameters={
            "Fy": 355e6,
            "E0": 210e9,
            "b": 0.01,
            "R0": 20.0,
            "cR1": 0.925,
            "cR2": 0.15,
        },
        poisson_ratio=0.30,
        density=7850.0,
    )


def linked_elastic_section(tag: int = 10, material_tag: int = 1) -> SectionData:
    return SectionData(
        tag=tag,
        name="IPE",
        section_type="Elastic",
        parameters={
            "E": 1.0,
            "A": 0.02,
            "Iz": 8.0e-5,
            "Iy": 6.0e-5,
            "G": 1.0,
            "J": 4.0e-5,
        },
        material_tag=material_tag,
    )


def test_material_engineering_properties_round_trip():
    project = ProjectDatabase()
    project.add_material(steel_material())

    restored = ProjectDatabase.from_dict(project.to_dict())
    material = restored.materials[1]

    assert material.poisson_ratio == 0.30
    assert material.density == 7850.0
    assert material.elastic_modulus() == 210e9
    assert isclose(
        material.shear_modulus(),
        210e9 / (2.0 * 1.30),
        rel_tol=1.0e-12,
    )


def test_elastic_section_resolves_E_and_G_from_linked_material():
    material = steel_material()
    section = linked_elastic_section()

    resolved = section.resolved_elastic_parameters({1: material})

    assert resolved["E"] == 210e9
    assert isclose(
        resolved["G"],
        210e9 / 2.6,
        rel_tol=1.0e-12,
    )
    assert resolved["A"] == 0.02
    assert resolved["Iz"] == 8.0e-5


def test_project_validates_linked_elastic_section_material():
    project = ProjectDatabase()
    section = linked_elastic_section(material_tag=99)

    try:
        project.add_section(section)
    except ValueError as exc:
        assert "missing material" in str(exc)
    else:
        raise AssertionError("Expected missing linked material validation")


def test_sections_using_material_includes_elastic_links():
    project = ProjectDatabase()
    project.add_material(steel_material())
    project.add_section(linked_elastic_section())

    assert project.sections_using_material(1) == [10]


def test_section_generator_uses_linked_material_properties():
    material = steel_material()
    section = linked_elastic_section()

    line = section_to_openseespy(section, {1: material})[0]

    assert "2.1e+11" in line
    assert "8.07692e+10" in line
    assert "0.02" in line


def test_element_generator_uses_linked_section_material_properties():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_element(1, 1, 2, section_tag=10)

    material = steel_material()
    section = linked_elastic_section()

    script = to_openseespy(
        model,
        materials={1: material},
        sections={10: section},
    )

    assert "2.1e+11" in script
    assert "8.07692e+10" in script


def test_legacy_elastic_section_without_material_remains_manual():
    section = SectionData(
        tag=1,
        name="Legacy",
        section_type="Elastic",
        parameters={
            "E": 200e9,
            "A": 0.03,
            "Iz": 9.0e-5,
            "Iy": 8.0e-5,
            "G": 77e9,
            "J": 7.0e-5,
        },
    )

    resolved = section.resolved_elastic_parameters()

    assert section.material_tag is None
    assert resolved["E"] == 200e9
    assert resolved["G"] == 77e9
