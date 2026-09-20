from openseespy_studio.generator import (
    connection_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.ui.connection_dialog import ConnectionDialog
from openseespy_studio.project import (
    ConnectionData,
    MaterialData,
    ProjectDatabase,
)


def elastic_material(tag: int = 1) -> MaterialData:
    return MaterialData(
        tag=tag,
        name="Spring K",
        material_type="Elastic",
        parameters={"E": 1000.0},
    )


def base_project() -> ProjectDatabase:
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)
    project.add_material(elastic_material())
    return project


def test_zero_length_connection_round_trip():
    project = base_project()
    project.model.add_node(3, 0.0, 0.0, 0.0)
    connection = ConnectionData(
        tag=10,
        name="UX spring",
        connection_type="zeroLength",
        node_i=1,
        node_j=3,
        materials_by_dof={1: 1},
    )
    project.add_connection(connection)

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.connections[10].materials_by_dof == {1: 1}
    assert restored.connections[10].connection_type == "zeroLength"


def test_zero_length_rejects_separated_nodes():
    project = base_project()
    connection = ConnectionData(
        tag=10,
        name="Bad zero length",
        connection_type="zeroLength",
        node_i=1,
        node_j=2,
        materials_by_dof={1: 1},
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "coincident" in str(exc)
    else:
        raise AssertionError("Expected separated zeroLength nodes to fail")


def test_two_node_link_allows_separated_nodes():
    project = base_project()
    connection = ConnectionData(
        tag=10,
        name="Link",
        connection_type="twoNodeLink",
        node_i=1,
        node_j=2,
        materials_by_dof={1: 1, 6: 1},
    )

    project.add_connection(connection)

    assert project.connections[10].node_j == 2


def test_spring_to_ground_node_is_created_and_cleaned():
    project = base_project()
    ground = project.create_ground_node(1)
    connection = ConnectionData(
        tag=10,
        name="Ground spring",
        connection_type="zeroLength",
        node_i=1,
        node_j=ground,
        materials_by_dof={1: 1},
        generated_ground_node=ground,
    )
    project.add_connection(connection)

    assert project.model.nodes[ground].fixity == (1, 1, 1, 1, 1, 1)

    project.remove_connection(10, cleanup_ground=True)

    assert ground not in project.model.nodes


def test_connection_generator_orders_materials_by_dof():
    connection = ConnectionData(
        tag=10,
        name="6D link",
        connection_type="twoNodeLink",
        node_i=1,
        node_j=2,
        materials_by_dof={6: 3, 1: 1, 3: 2},
        orient_x=(1.0, 0.0, 0.0),
        orient_y=(0.0, 1.0, 0.0),
        do_rayleigh=True,
    )

    line = connection_to_openseespy(connection)

    assert "'-mat', 1, 2, 3" in line
    assert "'-dir', 1, 3, 6" in line
    assert "'-doRayleigh', 1" in line


def test_full_script_contains_connection():
    project = base_project()
    project.model.add_node(3, 0.0, 0.0, 0.0)
    connection = ConnectionData(
        tag=10,
        name="Spring",
        connection_type="zeroLength",
        node_i=1,
        node_j=3,
        materials_by_dof={1: 1},
    )

    script = to_openseespy(
        project.model,
        materials=project.materials,
        connections={10: connection},
    )

    assert "# Connections / springs / links" in script
    assert "ops.element('zeroLength', 10, 1, 3" in script


def test_connection_tag_cannot_conflict_with_structural_element():
    project = base_project()
    project.model.add_element(10, 1, 2)
    project.model.add_node(3, 0.0, 0.0, 0.0)

    connection = ConnectionData(
        tag=10,
        name="Conflict",
        connection_type="zeroLength",
        node_i=1,
        node_j=3,
        materials_by_dof={1: 1},
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "conflicts with an element tag" in str(exc)
    else:
        raise AssertionError("Expected connection/element tag conflict")


def test_2d_connection_dialog_maps_rz_to_dir3():
    assert ConnectionDialog.dof_labels_for_model(2, 3) == (
        ("UX", "Local translation X"),
        ("UY", "Local translation Y"),
        ("RZ", "Local rotation Z"),
    )
    presets = dict(ConnectionDialog.presets_for_model(2, 3))
    assert presets["Rotational hinge RZ"] == (3,)
    assert presets["Planar joint UX-UY-RZ"] == (1, 2, 3)
    assert "Full 6-DOF spring" not in presets


def test_2d_connection_project_rejects_dir6_and_accepts_rz_dir3():
    model = StructuralModel("2d-connection", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)
    project.add_material(elastic_material())

    bad = ConnectionData(
        10,
        "Bad RZ mapping",
        "zeroLength",
        1,
        2,
        materials_by_dof={6: 1},
    )
    try:
        project.add_connection(bad)
    except ValueError as exc:
        assert "ndf=3" in str(exc)
    else:
        raise AssertionError("Expected invalid 2D connection DOF to fail")

    good = ConnectionData(
        11,
        "2D RZ spring",
        "zeroLength",
        1,
        2,
        materials_by_dof={3: 1},
    )
    project.add_connection(good)
    assert project.connections[11].materials_by_dof == {3: 1}
