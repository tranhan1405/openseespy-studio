from __future__ import annotations

import pytest

from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ProjectDatabase, SectionData
from openseespy_studio.validation import validate_project


def _elastic_section(tag: int = 5) -> SectionData:
    return SectionData(
        tag=tag,
        name=f"Axial section {tag}",
        section_type="Elastic",
        parameters={
            "E": 2.0e11,
            "A": 0.01,
            "Iz": 1.0e-4,
            "Iy": 1.0e-4,
            "G": 7.7e10,
            "J": 1.0e-5,
        },
    )


def _script(project: ProjectDatabase) -> str:
    return to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        time_series=project.time_series,
        load_patterns=project.load_patterns,
        nodal_loads=project.nodal_loads,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
        element_loads=project.element_loads,
        prescribed_displacements=project.prescribed_displacements,
        recorders=project.recorders,
        units=project.units,
        solution_results=project.solution_results,
        nd_materials=project.nd_materials,
        friction_models=project.friction_models,
    )


def test_truss_section_generation_and_project_round_trip():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=2)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 3.0, 0.0)
    project.add_section(_elastic_section(5))
    project.model.add_element(
        11,
        1,
        2,
        element_type="trussSection",
        section_tag=5,
        group="truss",
        mass_per_length=2.5,
        consistent_mass=True,
        truss_do_rayleigh=True,
    )

    project.validate_element_state(11)
    restored = ProjectDatabase.from_dict(project.to_dict())
    element = restored.model.elements[11]

    assert element.element_type == "trussSection"
    assert element.section_tag == 5
    assert element.truss_area == 0.0
    assert element.truss_material_tag is None

    script = _script(restored)
    assert (
        "ops.element('TrussSection', 11, 1, 2, 5, "
        "'-rho', 2.5, '-cMass', 1, '-doRayleigh', 1)"
    ) in script
    assert "# ERROR:" not in script


def test_corot_truss_section_generation():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=2)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 3.0, 0.0)
    project.add_section(_elastic_section(7))
    project.model.add_element(
        12,
        1,
        2,
        element_type="corotTrussSection",
        section_tag=7,
        group="truss",
    )

    project.validate_element_state(12)
    script = _script(project)

    assert "ops.element('corotTrussSection', 12, 1, 2, 7)" in script
    assert "# ERROR:" not in script


def test_importer_recognizes_truss_section_variants():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 2)
ops.node(1, 0.0, 0.0)
ops.node(2, 3.0, 0.0)
ops.node(3, 6.0, 0.0)
ops.section('Elastic', 5, 2.0e11, 0.01, 1.0e-4)
ops.element('TrussSection', 21, 1, 2, 5,
            '-rho', 2.5, '-cMass', 1, '-doRayleigh', 1)
ops.element('corotTrussSection', 22, 2, 3, 5)
"""
    result = import_openseespy_source(
        source,
        source_name="truss_sections.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0

    linear = result.project.model.elements[21]
    corot = result.project.model.elements[22]
    assert linear.element_type == "trussSection"
    assert linear.section_tag == 5
    assert linear.mass_per_length == 2.5
    assert linear.consistent_mass is True
    assert linear.truss_do_rayleigh is True
    assert corot.element_type == "corotTrussSection"
    assert corot.section_tag == 5


def test_section_truss_validation_rejects_missing_section():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=2)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 3.0, 0.0)
    project.model.add_element(
        31,
        1,
        2,
        element_type="trussSection",
        section_tag=99,
    )

    issues = validate_project(project)
    assert any(
        issue.entity_tag == 31
        and issue.severity == "ERROR"
        and issue.category == "Section"
        and "99" in issue.message
        for issue in issues
    )

    with pytest.raises(ValueError, match="existing section"):
        project.validate_element_state(31)
