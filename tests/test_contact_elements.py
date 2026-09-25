from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    NDMaterialData,
    ProjectDatabase,
    TransformationData,
)
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
        friction_models=project.friction_models,
    )


def test_mixed_node_ndf_round_trip():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0, 0.0, ndf=3)
    project.model.set_fixity(2, (1, 0, 1))
    project.model.set_mass(2, (1.0, 2.0, 3.0))

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.model.nodes[1].ndf == 6
    assert restored.model.nodes[2].ndf == 3
    assert restored.model.nodes[2].fixity == (1, 0, 1)
    assert restored.model.nodes[2].mass == (1.0, 2.0, 3.0)

    script = _script(restored)
    assert "ops.model('basic', '-ndm', 3, '-ndf', 3)" in script
    assert "ops.node(2, 1, 0, 0)" in script
    assert "ops.fix(2, 1, 0, 1)" in script
    assert "ops.mass(2, 1, 2, 3)" in script


def test_zero_length_contact_2d_generator():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=2)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0)
    project.model.add_element(
        10,
        1,
        2,
        element_type="zeroLengthContact2D",
        special_parameters={
            "Kn": 1.0e9,
            "Kt": 2.0e8,
            "mu": 0.35,
            "normal": (1.0, 0.0),
        },
    )

    project.validate_element_state(10)
    issues = validate_project(project)
    assert not [
        issue for issue in issues
        if issue.entity_tag == 10 and issue.severity == "ERROR"
    ]

    script = _script(project)
    assert (
        "ops.element('zeroLengthContact2D', 10, 1, 2, "
        "1e+06, 200000, 0.35, '-normal', 1, 0)"
    ) in script


def test_zero_length_contact_3d_generator():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=3)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 0.0)
    project.model.add_element(
        11,
        1,
        2,
        element_type="zeroLengthContact3D",
        special_parameters={
            "Kn": 1.0e9,
            "Kt": 2.0e8,
            "mu": 0.30,
            "cohesion": 5000.0,
            "dir": 3,
        },
    )

    project.validate_element_state(11)
    script = _script(project)
    assert (
        "ops.element('zeroLengthContact3D', 11, 1, 2, "
        "1e+06, 200000, 0.3, 5, 3)"
    ) in script


def test_contact_material_generation():
    project = ProjectDatabase()
    project.add_nd_material(
        NDMaterialData(
            21,
            "2D contact",
            "ContactMaterial2D",
            {"mu": 0.3, "G": 1.0e8, "c": 2.0e6, "t": 1.0e6},
        )
    )
    project.add_nd_material(
        NDMaterialData(
            22,
            "3D contact",
            "ContactMaterial3D",
            {"mu": 0.4, "G": 2.0e8, "c": 3.0e6, "t": 1.5e6},
        )
    )

    script = _script(project)
    assert (
        "ops.nDMaterial('ContactMaterial2D', 21, 0.3, 100000, 2000, 1000)"
        in script
    )
    assert (
        "ops.nDMaterial('ContactMaterial3D', 22, 0.4, 200000, 3000, 1500)"
        in script
    )


def test_beam_contact_2d_mixed_dof_generation():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0)
    project.model.add_node(3, 0.5, 0.1, ndf=2)
    project.model.add_node(4, 0.5, 0.1, ndf=2)
    project.add_nd_material(
        NDMaterialData(
            31,
            "2D interface",
            "ContactMaterial2D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        )
    )
    project.model.add_element(
        20,
        1,
        2,
        k=3,
        l=4,
        element_type="BeamContact2D",
        special_parameters={
            "nd_material_tag": 31,
            "width": 0.3,
            "gTol": 1.0e-8,
            "fTol": 1.0e-4,
            "cFlag": 0,
        },
    )

    project.validate_element_state(20)
    script = _script(project)
    assert (
        "ops.element('BeamContact2D', 20, 1, 2, 3, 4, "
        "31, 0.3, 1e-08, 1e-07, 0)"
    ) in script
    assert script.count("'-ndf', 2") >= 1


def test_beam_contact_3d_mixed_dof_generation():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0, 0.0)
    project.model.add_node(3, 0.5, 0.2, 0.0, ndf=3)
    project.model.add_node(4, 0.5, 0.2, 0.0, ndf=3)
    project.add_nd_material(
        NDMaterialData(
            32,
            "3D interface",
            "ContactMaterial3D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        )
    )
    project.add_transformation(
        TransformationData(
            9,
            "Contact beam",
            "Linear",
            (0.0, 0.0, 1.0),
        )
    )
    project.model.add_element(
        21,
        1,
        2,
        k=3,
        l=4,
        element_type="BeamContact3D",
        special_parameters={
            "nd_material_tag": 32,
            "radius": 0.15,
            "transf_tag": 9,
            "gTol": 1.0e-8,
            "fTol": 1.0e-4,
            "cFlag": 1,
        },
    )

    project.validate_element_state(21)
    script = _script(project)
    assert (
        "ops.element('BeamContact3D', 21, 1, 2, 3, 4, "
        "0.15, 9, 32, 1e-08, 1e-07, 1)"
    ) in script


def test_beam_contact_rejects_wrong_node_ndfs():
    model = StructuralModel(ndm=3, ndf=6)
    for tag in range(1, 5):
        model.add_node(tag, float(tag), 0.0, 0.0)
    try:
        model.add_element(
            1,
            1,
            2,
            k=3,
            l=4,
            element_type="BeamContact3D",
            special_parameters={
                "nd_material_tag": 1,
                "radius": 0.15,
                "transf_tag": 1,
                "gTol": 1.0e-8,
                "fTol": 1.0e-4,
                "cFlag": 0,
            },
        )
    except ValueError as exc:
        assert "constrained/Lagrange nodes ndf=3" in str(exc)
    else:
        raise AssertionError("BeamContact3D accepted 6DOF contact nodes")


def test_contact_nd_material_dependency_tracks_rename_and_delete():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0)
    project.model.add_node(3, 0.5, 0.1, ndf=2)
    project.model.add_node(4, 0.5, 0.1, ndf=2)
    project.add_nd_material(
        NDMaterialData(
            40,
            "contact",
            "ContactMaterial2D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        )
    )
    project.model.add_element(
        30,
        1,
        2,
        k=3,
        l=4,
        element_type="BeamContact2D",
        special_parameters={
            "nd_material_tag": 40,
            "width": 0.3,
            "gTol": 1.0e-8,
            "fTol": 1.0e-4,
            "cFlag": 0,
        },
    )

    project.update_nd_material(
        40,
        NDMaterialData(
            41,
            "renamed",
            "ContactMaterial2D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        ),
    )
    assert project.model.elements[30].special_parameters["nd_material_tag"] == 41

    try:
        project.remove_nd_material(41)
    except ValueError as exc:
        assert "element" in str(exc).lower()
    else:
        raise AssertionError("Referenced contact nD material was deleted")
