from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    FrictionModelData,
    MaterialData,
    ProjectDatabase,
)
from openseespy_studio.validation import validate_project


def _elastic(tag: int) -> MaterialData:
    return MaterialData(
        tag,
        f"Elastic {tag}",
        "Elastic",
        {"E": 1.0e8},
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


def test_flat_slider_bearing_2d_generation_and_dependencies():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.2)
    project.add_material(_elastic(1))
    project.add_material(_elastic(2))
    project.add_friction_model(
        FrictionModelData(1, "PTFE", "Coulomb", {"mu": 0.05})
    )
    project.model.add_element(
        10,
        1,
        2,
        element_type="flatSliderBearing",
        group="isolation",
        special_parameters={
            "frn_model_tag": 1,
            "kInit": 20.0e6,
            "p_mat_tag": 1,
            "mz_mat_tag": 2,
            "shearDist": 0.25,
            "doRayleigh": True,
            "mass": 100.0,
            "maxIter": 50,
            "tol": 1.0e-10,
        },
    )

    project.validate_element_state(10)
    assert not [
        issue
        for issue in validate_project(project)
        if issue.entity_tag == 10 and issue.severity == "ERROR"
    ]

    script = _script(project)
    assert (
        "ops.element('flatSliderBearing', 10, 1, 2, 1, 20000, "
        "'-P', 1, '-Mz', 2, '-shearDist', 0.25, '-doRayleigh', "
        "'-mass', 0.1, '-iter', 50, 1e-10)"
    ) in script


def test_single_fp_bearing_3d_generation():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.4)
    for tag in range(1, 5):
        project.add_material(_elastic(tag))
    project.add_friction_model(
        FrictionModelData(
            2,
            "Velocity PTFE",
            "VelDependent",
            {"muSlow": 0.03, "muFast": 0.08, "transRate": 2.0},
        )
    )
    project.model.add_element(
        11,
        1,
        2,
        element_type="singleFPBearing",
        group="isolation",
        special_parameters={
            "frn_model_tag": 2,
            "Reff": 2.5,
            "kInit": 30.0e6,
            "p_mat_tag": 1,
            "t_mat_tag": 2,
            "my_mat_tag": 3,
            "mz_mat_tag": 4,
            "orientation": (0.0, 0.0, 1.0, 1.0, 0.0, 0.0),
        },
    )

    project.validate_element_state(11)
    script = _script(project)
    assert (
        "ops.element('singleFPBearing', 11, 1, 2, 2, 2.5, 30000, "
        "'-P', 1, '-T', 2, '-My', 3, '-Mz', 4, "
        "'-orient', 0, 0, 1, 1, 0, 0)"
    ) in script


def test_friction_bearing_requires_3d_rotational_materials():
    model = StructuralModel(ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 0.5)

    try:
        model.add_element(
            1,
            1,
            2,
            element_type="flatSliderBearing",
            special_parameters={
                "frn_model_tag": 1,
                "kInit": 1.0e7,
                "p_mat_tag": 1,
                "mz_mat_tag": 2,
            },
        )
    except ValueError as exc:
        assert "t_mat_tag and my_mat_tag" in str(exc)
    else:
        raise AssertionError("3D friction bearing accepted missing T/My materials")


def test_friction_bearing_model_check_reports_missing_friction_model():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.2)
    project.add_material(_elastic(1))
    project.add_material(_elastic(2))
    project.model.add_element(
        12,
        1,
        2,
        element_type="flatSliderBearing",
        special_parameters={
            "frn_model_tag": 99,
            "kInit": 1.0e7,
            "p_mat_tag": 1,
            "mz_mat_tag": 2,
        },
    )

    issues = validate_project(project)
    assert any(
        issue.entity_tag == 12
        and issue.category == "Friction model"
        and "99" in issue.message
        for issue in issues
    )


def test_friction_bearing_dependency_tracks_rename_and_blocks_delete():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.2)
    project.add_material(_elastic(1))
    project.add_material(_elastic(2))
    project.add_friction_model(
        FrictionModelData(1, "PTFE", "Coulomb", {"mu": 0.05})
    )
    project.model.add_element(
        13,
        1,
        2,
        element_type="flatSliderBearing",
        special_parameters={
            "frn_model_tag": 1,
            "kInit": 1.0e7,
            "p_mat_tag": 1,
            "mz_mat_tag": 2,
        },
    )

    project.update_friction_model(
        1,
        FrictionModelData(7, "PTFE renamed", "Coulomb", {"mu": 0.05}),
    )
    assert project.model.elements[13].special_parameters["frn_model_tag"] == 7

    try:
        project.remove_friction_model(7)
    except ValueError as exc:
        assert "bearing element(s): 13" in str(exc)
    else:
        raise AssertionError("Referenced friction model was deleted")


def test_friction_bearings_import_with_friction_models():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 0.0, 0.2)
ops.node(3, 0.0, 0.4)
ops.uniaxialMaterial('Elastic', 1, 1.0e8)
ops.uniaxialMaterial('Elastic', 2, 1.0e8)
ops.frictionModel('Coulomb', 1, 0.05)
ops.frictionModel('VelDependent', 2, 0.03, 0.08, 2.0)
ops.element('flatSliderBearing', 10, 1, 2, 1, 2.0e7,
            '-P', 1, '-Mz', 2, '-shearDist', 0.25, '-iter', 40, 1e-9)
ops.element('singleFPBearing', 11, 2, 3, 2, 2.5, 3.0e7,
            '-P', 1, '-Mz', 2)
"""
    result = import_openseespy_source(
        source,
        source_name="friction_bearings.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.project.friction_models[1].friction_type == "Coulomb"
    assert result.project.friction_models[2].friction_type == "VelDependent"

    flat = result.project.model.elements[10]
    assert flat.element_type == "flatSliderBearing"
    assert flat.special_parameters["frn_model_tag"] == 1
    assert flat.special_parameters["kInit"] == 2.0e7
    assert flat.special_parameters["maxIter"] == 40
    assert flat.special_parameters["tol"] == 1.0e-9

    fp = result.project.model.elements[11]
    assert fp.element_type == "singleFPBearing"
    assert fp.special_parameters["Reff"] == 2.5
    assert fp.special_parameters["frn_model_tag"] == 2
