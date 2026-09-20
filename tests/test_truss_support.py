from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.validation import validate_project


def test_importer_reconstructs_truss_area_material_and_options():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 3.0, 0.0, 0.0)
ops.uniaxialMaterial('Elastic', 10, 200.0e9)
ops.element('Truss', 21, 1, 2, 0.003, 10,
            '-rho', 7.85, '-cMass', 1, '-doRayleigh', 1)
"""

    result = import_openseespy_source(
        source,
        source_name="truss.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0

    element = result.project.model.elements[21]
    assert element.element_type == "truss"
    assert element.i == 1
    assert element.j == 2
    assert element.truss_area == 0.003
    assert element.truss_material_tag == 10
    assert element.mass_per_length == 7.85
    assert element.consistent_mass is True
    assert element.truss_do_rayleigh is True
    assert element.section_tag is None
    assert element.transf_tag is None


def test_truss_generator_round_trip_has_no_unsupported_error():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 3.0, 0.0, 0.0)
ops.uniaxialMaterial('Elastic', 10, 200.0e9)
ops.element('truss', 21, 1, 2, 0.003, 10, '-rho', 7.85)
"""
    imported = import_openseespy_source(
        source,
        source_name="truss_lowercase.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    project = imported.project
    script = to_openseespy(
        project.model,
        project.materials,
        project.sections,
        project.transformations,
        project.constraints,
        project.connections,
        project.time_series,
        project.load_patterns,
        project.nodal_loads,
        project.analyses,
        project.active_analysis_tag,
        element_loads=project.element_loads,
        prescribed_displacements=project.prescribed_displacements,
        recorders=project.recorders,
        units=project.units,
    )

    assert "# ERROR:" not in script
    assert "ops.element('Truss', 21, 1, 2, 0.003, 10" in script
    assert "'-rho', 7.85" in script

    round_trip = import_openseespy_source(
        script,
        source_name="truss_roundtrip.py",
        units=project.units,
    )
    assert round_trip.error_count == 0
    restored = round_trip.project.model.elements[21]
    assert restored.element_type == "truss"
    assert restored.truss_area == 0.003
    assert restored.truss_material_tag == 10


def test_truss_validation_does_not_require_frame_section_or_transformation():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 3.0, 0.0, 0.0)
ops.uniaxialMaterial('Elastic', 10, 200.0e9)
ops.element('Truss', 21, 1, 2, 0.003, 10)
"""
    project = import_openseespy_source(
        source,
        source_name="truss_validation.py",
        units={"length": "m", "force": "N", "time": "s"},
    ).project

    issues = validate_project(project)
    element_errors = [
        issue for issue in issues
        if issue.entity_kind == "element"
        and issue.entity_tag == 21
        and issue.severity == "ERROR"
    ]
    assert element_errors == []
