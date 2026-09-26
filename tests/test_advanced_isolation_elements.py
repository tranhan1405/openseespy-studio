from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    FrictionModelData,
    MaterialData,
    ProjectDatabase,
)
from openseespy_studio.validation import validate_project


def _elastic(tag: int, stiffness: float = 1.0e8) -> MaterialData:
    return MaterialData(
        tag=tag,
        name=f"Elastic {tag}",
        material_type="Elastic",
        parameters={"E": stiffness},
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


def test_friction_models_round_trip_and_generation():
    project = ProjectDatabase()
    project.add_friction_model(
        FrictionModelData(
            1,
            "Constant PTFE",
            "Coulomb",
            {"mu": 0.05},
        )
    )
    project.add_friction_model(
        FrictionModelData(
            2,
            "Velocity PTFE",
            "VelDependent",
            {
                "muSlow": 0.03,
                "muFast": 0.08,
                "transRate": 2.5,
            },
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.friction_models[1].parameters["mu"] == 0.05
    assert restored.friction_models[2].friction_type == "VelDependent"

    script = _script(restored)
    assert "ops.frictionModel('Coulomb', 1, 0.05)" in script
    assert (
        "ops.frictionModel('VelDependent', 2, 0.03, 0.08, 2.5)"
        in script
    )


def test_lead_rubber_x_generation_3d():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.5)
    project.model.add_element(
        10,
        1,
        2,
        element_type="LeadRubberX",
        group="isolation",
        special_parameters={
            "Fy": 120000.0,
            "alpha": 0.1,
            "Gr": 0.8e6,
            "Kbulk": 2.0e9,
            "D1": 0.1,
            "D2": 0.8,
            "ts": 0.003,
            "tr": 0.01,
            "n": 20,
            "orientation": (0.0, 0.0, 1.0, 1.0, 0.0, 0.0),
            "tag5": 1,
        },
    )

    project.validate_element_state(10)
    script = _script(project)

    assert "ops.element('LeadRubberX', 10, 1, 2" in script
    assert ", 120, 0.1, 800, 2e+06, 0.1, 0.8, 0.003, 0.01, 20" in script
    assert script.count("LeadRubberX") == 1


def test_lead_rubber_x_rejects_non_3d6dof_model():
    model = StructuralModel(ndm=3, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 1.0)

    try:
        model.add_element(
            1,
            1,
            2,
            element_type="LeadRubberX",
            special_parameters={
                "Fy": 100000.0,
                "alpha": 0.1,
                "Gr": 0.8e6,
                "Kbulk": 2.0e9,
                "D1": 0.1,
                "D2": 0.8,
                "ts": 0.003,
                "tr": 0.01,
                "n": 20,
            },
        )
    except ValueError as exc:
        assert "ndm=3/ndf=6" in str(exc)
    else:
        raise AssertionError("LeadRubberX accepted non-3D/6DOF model")


def test_triple_friction_pendulum_generation_and_dependencies():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.5)

    for tag in range(1, 5):
        project.add_material(_elastic(tag))
    for tag, mu in ((1, 0.03), (2, 0.05), (3, 0.08)):
        project.add_friction_model(
            FrictionModelData(
                tag,
                f"Friction {tag}",
                "Coulomb",
                {"mu": mu},
            )
        )

    project.model.add_element(
        20,
        1,
        2,
        element_type="TripleFrictionPendulum",
        group="isolation",
        special_parameters={
            "frnTag1": 1,
            "frnTag2": 2,
            "frnTag3": 3,
            "vertMatTag": 1,
            "rotZMatTag": 2,
            "rotXMatTag": 3,
            "rotYMatTag": 4,
            "L1": 0.36,
            "L2": 1.25,
            "L3": 1.25,
            "d1": 0.10,
            "d2": 0.20,
            "d3": 0.20,
            "W": 1.0e6,
            "uy": 0.0005,
            "kvt": 1000.0,
            "minFv": 100.0,
            "tol": 1.0e-5,
        },
    )

    project.validate_element_state(20)
    assert not [
        issue for issue in validate_project(project)
        if issue.entity_tag == 20 and issue.severity == "ERROR"
    ]

    script = _script(project)
    assert (
        "ops.element('TripleFrictionPendulum', 20, 1, 2, "
        "1, 2, 3, 1, 2, 3, 4, 0.36, 1.25, 1.25, "
        "0.1, 0.2, 0.2, 1000, 0.0005, 1, 0.1, 1e-05)"
    ) in script


def test_triple_friction_pendulum_reports_missing_friction_model():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.5)
    for tag in range(1, 5):
        project.add_material(_elastic(tag))
    project.add_friction_model(
        FrictionModelData(1, "Friction 1", "Coulomb", {"mu": 0.03})
    )

    project.model.add_element(
        21,
        1,
        2,
        element_type="TripleFrictionPendulum",
        special_parameters={
            "frnTag1": 1,
            "frnTag2": 2,
            "frnTag3": 3,
            "vertMatTag": 1,
            "rotZMatTag": 2,
            "rotXMatTag": 3,
            "rotYMatTag": 4,
            "L1": 0.36,
            "L2": 1.25,
            "L3": 1.25,
            "d1": 0.10,
            "d2": 0.20,
            "d3": 0.20,
            "W": 1.0e6,
            "uy": 0.0005,
            "kvt": 1000.0,
            "minFv": 100.0,
            "tol": 1.0e-5,
        },
    )

    issues = validate_project(project)
    assert any(
        issue.entity_tag == 21
        and issue.category == "Friction model"
        and "2" in issue.message
        and "3" in issue.message
        for issue in issues
    )

    try:
        project.validate_element_state(21)
    except ValueError as exc:
        assert "missing friction model" in str(exc)
    else:
        raise AssertionError("Missing TFP friction model was accepted")


def test_friction_model_delete_is_blocked_when_used_by_tfp():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.5)
    for tag in range(1, 5):
        project.add_material(_elastic(tag))
    for tag in range(1, 4):
        project.add_friction_model(
            FrictionModelData(
                tag,
                f"Friction {tag}",
                "Coulomb",
                {"mu": 0.04},
            )
        )
    project.model.add_element(
        22,
        1,
        2,
        element_type="TripleFrictionPendulum",
        special_parameters={
            "frnTag1": 1,
            "frnTag2": 2,
            "frnTag3": 3,
            "vertMatTag": 1,
            "rotZMatTag": 2,
            "rotXMatTag": 3,
            "rotYMatTag": 4,
            "L1": 0.36,
            "L2": 1.25,
            "L3": 1.25,
            "d1": 0.10,
            "d2": 0.20,
            "d3": 0.20,
            "W": 1.0e6,
            "uy": 0.0005,
            "kvt": 1000.0,
            "minFv": 100.0,
            "tol": 1.0e-5,
        },
    )

    try:
        project.remove_friction_model(2)
    except ValueError as exc:
        assert "TripleFrictionPendulum element(s): 22" in str(exc)
    else:
        raise AssertionError("Referenced friction model was deleted")
