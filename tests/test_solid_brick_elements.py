from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import NDMaterialData, ProjectDatabase


def _project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=3)
    coords = (
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (2.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.5),
        (2.0, 0.0, 1.5),
        (2.0, 1.0, 1.5),
        (0.0, 1.0, 1.5),
    )
    for tag, xyz in enumerate(coords, 1):
        project.model.add_node(tag, *xyz)
    project.add_nd_material(
        NDMaterialData(
            tag=1,
            name="Elastic solid",
            material_type="ElasticIsotropic",
            parameters={"E": 30.0e9, "nu": 0.2, "rho": 0.0},
        )
    )
    return project


def _add(project: ProjectDatabase, tag: int, formulation: str):
    project.model.add_element(
        tag,
        1,
        2,
        element_type=formulation,
        k=3,
        l=4,
        m=5,
        n=6,
        p=7,
        q=8,
        group="solid-3d",
        solid_material_tag=1,
        solid_body_force=(1.0, -2.0, -9.81),
    )
    project.validate_element_state(tag)


def test_solid_brick_generation_for_all_batch2_formulations():
    project = _project()
    for tag, formulation in enumerate(
        ("stdBrick", "SSPbrick", "bbarBrick"),
        1,
    ):
        _add(project, tag, formulation)

    script = to_openseespy(
        project.model,
        nd_materials=project.nd_materials,
        units=project.units,
    )
    for tag, formulation in enumerate(
        ("stdBrick", "SSPbrick", "bbarBrick"),
        1,
    ):
        assert (
            f"ops.element('{formulation}', {tag}, 1, 2, 3, 4, "
            "5, 6, 7, 8, 1, 1, -2, -9.81)"
        ) in script


def test_solid_brick_round_trip_preserves_eight_nodes_and_material():
    project = _project()
    _add(project, 1, "SSPbrick")

    restored = ProjectDatabase.from_dict(project.to_dict())
    element = restored.model.elements[1]
    assert element.element_type == "SSPbrick"
    assert element.node_tags() == (1, 2, 3, 4, 5, 6, 7, 8)
    assert element.solid_material_tag == 1
    assert element.solid_body_force == (1.0, -2.0, -9.81)


def test_solid_brick_requires_3d_3dof_model():
    model = StructuralModel(ndm=3, ndf=6)
    for tag, xyz in enumerate(
        (
            (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
            (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
        ),
        1,
    ):
        model.add_node(tag, *xyz)
    try:
        model.add_element(
            1, 1, 2,
            element_type="stdBrick",
            k=3, l=4, m=5, n=6, p=7, q=8,
            solid_material_tag=1,
        )
    except ValueError as exc:
        assert "ndm=3/ndf=3" in str(exc)
    else:
        raise AssertionError("stdBrick accepted a 3D/6DOF model")


def test_solid_brick_rejects_inverted_node_order():
    project = _project()
    try:
        project.model.add_element(
            1,
            2,
            1,
            element_type="bbarBrick",
            k=4,
            l=3,
            m=6,
            n=5,
            p=8,
            q=7,
            solid_material_tag=1,
        )
    except ValueError as exc:
        assert "positively oriented" in str(exc)
    else:
        raise AssertionError("bbarBrick accepted inverted node ordering")
