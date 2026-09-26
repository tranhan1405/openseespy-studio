from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import MaterialData, ProjectDatabase
from openseespy_studio.validation import validate_project


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
    )


def _elastic_material(tag: int) -> MaterialData:
    return MaterialData(
        tag,
        f"Elastic {tag}",
        "Elastic",
        {"E": 2.0e11},
    )


def test_catenary_cable_generator_and_round_trip():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=3)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 10.0, 0.0, 0.0)
    project.model.add_element(
        1,
        1,
        2,
        element_type="CatenaryCable",
        group="cable",
        special_parameters={
            "weight": 500.0,
            "E": 2.0e11,
            "A": 0.001,
            "L0": 10.2,
            "alpha": 1.2e-5,
            "temperature_change": 20.0,
            "rho": 7.85,
            "errorTol": 1.0e-8,
            "Nsubsteps": 10,
            "massType": 0,
        },
    )

    project.validate_element_state(1)
    script = _script(project)
    assert (
        "ops.element('CatenaryCable', 1, 1, 2, 0.5, 2e+08, "
        "0.001, 10.2, 1.2e-05, 20, 0.00785, 1e-08, 10, 0)"
    ) in script

    restored = ProjectDatabase.from_dict(project.to_dict())
    params = restored.model.elements[1].special_parameters
    assert params["L0"] == 10.2
    assert params["Nsubsteps"] == 10
    assert params["massType"] == 0


def test_catenary_cable_rejects_3d_six_dof_nodes():
    model = StructuralModel(ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    try:
        model.add_element(
            1,
            1,
            2,
            element_type="CatenaryCable",
            special_parameters={
                "weight": 1.0,
                "E": 2.0e11,
                "A": 0.001,
                "L0": 1.0,
                "alpha": 0.0,
                "temperature_change": 0.0,
                "rho": 1.0,
                "errorTol": 1.0e-8,
                "Nsubsteps": 5,
                "massType": 0,
            },
        )
    except ValueError as exc:
        assert "ndm=3/ndf=3" in str(exc)
    else:
        raise AssertionError("CatenaryCable accepted 3D/6DOF nodes")


def test_catenary_cable_rejects_unsupported_mass_type():
    model = StructuralModel(ndm=3, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    try:
        model.add_element(
            1,
            1,
            2,
            element_type="CatenaryCable",
            special_parameters={
                "weight": 1.0,
                "E": 2.0e11,
                "A": 0.001,
                "L0": 1.0,
                "alpha": 0.0,
                "temperature_change": 0.0,
                "rho": 1.0,
                "errorTol": 1.0e-8,
                "Nsubsteps": 5,
                "massType": 1,
            },
        )
    except ValueError as exc:
        assert "massType=0" in str(exc)
    else:
        raise AssertionError("Unsupported CatenaryCable massType was accepted")


def test_catenary_cable_rejects_incompatible_model_dimension():
    model = StructuralModel(ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    try:
        model.add_element(
            1,
            1,
            2,
            element_type="CatenaryCable",
            special_parameters={
                "weight": 1.0,
                "E": 2.0e11,
                "A": 0.001,
                "L0": 1.0,
                "alpha": 0.0,
                "temperature_change": 0.0,
                "rho": 1.0,
                "errorTol": 1.0e-8,
                "Nsubsteps": 5,
                "massType": 0,
            },
        )
    except ValueError as exc:
        assert "ndm=3" in str(exc)
    else:
        raise AssertionError("CatenaryCable accepted a 2D model")


def test_elastomeric_bearing_plasticity_2d_generator_zero_length():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0)
    project.add_material(_elastic_material(1))
    project.add_material(_elastic_material(2))
    project.model.add_element(
        5,
        1,
        2,
        element_type="elastomericBearingPlasticity",
        group="bearing",
        special_parameters={
            "kInit": 20.0e6,
            "qd": 2500.0,
            "alpha1": 0.02,
            "alpha2": 0.0,
            "mu": 3.0,
            "p_mat_tag": 1,
            "mz_mat_tag": 2,
            "shearDist": 0.4,
            "doRayleigh": True,
            "mass": 300.0,
        },
    )

    project.validate_element_state(5)
    issues = validate_project(project)
    assert not any(
        issue.category == "Geometry" and issue.entity_tag == 5
        for issue in issues
    )

    script = _script(project)
    assert (
        "ops.element('elastomericBearingPlasticity', 5, 1, 2, "
        "20000, 2.5, 0.02, 0, 3, '-P', 1, '-Mz', 2, "
        "'-shearDist', 0.4, '-doRayleigh', '-mass', 0.3)"
    ) in script


def test_elastomeric_bearing_plasticity_3d_generator_orientation():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.5)
    for tag in range(1, 5):
        project.add_material(_elastic_material(tag))

    project.model.add_element(
        6,
        1,
        2,
        element_type="elastomericBearingPlasticity",
        group="bearing",
        special_parameters={
            "kInit": 30.0e6,
            "qd": 5000.0,
            "alpha1": 0.05,
            "alpha2": 0.01,
            "mu": 2.0,
            "p_mat_tag": 1,
            "t_mat_tag": 2,
            "my_mat_tag": 3,
            "mz_mat_tag": 4,
            "orientation": (0.0, 0.0, 1.0, 0.0, 1.0, 0.0),
            "shearDist": 0.5,
            "doRayleigh": False,
            "mass": 0.0,
        },
    )

    project.validate_element_state(6)
    script = _script(project)
    assert (
        "ops.element('elastomericBearingPlasticity', 6, 1, 2, "
        "30000, 5, 0.05, 0.01, 2, '-P', 1, '-T', 2, "
        "'-My', 3, '-Mz', 4, '-orient', 0, 0, 1, 0, 1, 0)"
    ) in script


def test_bearing_material_dependency_tracks_rename_and_delete():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.2)
    project.add_material(_elastic_material(1))
    project.add_material(_elastic_material(2))
    project.model.add_element(
        7,
        1,
        2,
        element_type="elastomericBearingPlasticity",
        special_parameters={
            "kInit": 10.0e6,
            "qd": 1000.0,
            "alpha1": 0.02,
            "alpha2": 0.0,
            "mu": 2.0,
            "p_mat_tag": 1,
            "mz_mat_tag": 2,
        },
    )

    project.update_material(1, _elastic_material(11))
    assert project.model.elements[7].special_parameters["p_mat_tag"] == 11

    try:
        project.remove_material(2)
    except ValueError as exc:
        assert "bearing elements 7" in str(exc)
    else:
        raise AssertionError("Referenced bearing material was deleted")


def test_bearing_model_check_reports_missing_material():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.3)
    project.add_material(_elastic_material(1))
    project.model.add_element(
        8,
        1,
        2,
        element_type="elastomericBearingPlasticity",
        special_parameters={
            "kInit": 10.0e6,
            "qd": 1000.0,
            "alpha1": 0.02,
            "alpha2": 0.0,
            "mu": 2.0,
            "p_mat_tag": 1,
            "mz_mat_tag": 99,
        },
    )

    issues = validate_project(project)

    assert any(
        issue.category == "Bearing material"
        and issue.entity_tag == 8
        and "99" in issue.message
        for issue in issues
    )


def test_special_element_copy_preserves_parameters():
    model = StructuralModel(ndm=3, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 10.0, 0.0, 0.0)
    source = model.add_element(
        1,
        1,
        2,
        element_type="CatenaryCable",
        group="cable",
        special_parameters={
            "weight": 500.0,
            "E": 2.0e11,
            "A": 0.001,
            "L0": 10.2,
            "alpha": 1.2e-5,
            "temperature_change": 10.0,
            "rho": 7.85,
            "errorTol": 1.0e-8,
            "Nsubsteps": 10,
            "massType": 0,
        },
    )

    _nodes, elements = model.copy_entities(
        element_tags={1},
        dx=0.0,
        dy=2.0,
        dz=0.0,
    )

    copied_tag = next(iter(elements))
    copied = model.elements[copied_tag]
    assert copied.element_type == "CatenaryCable"
    assert copied.group == source.group
    assert copied.special_parameters == source.special_parameters
    assert copied.special_parameters is not source.special_parameters
