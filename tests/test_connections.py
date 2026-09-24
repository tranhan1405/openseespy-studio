from openseespy_studio.generator import (
    connection_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
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


def frame2d_project() -> ProjectDatabase:
    model = StructuralModel(name="2D joint test", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 0.0)
    model.add_node(10, 0.0, 0.0, 0.0)   # left
    model.add_node(11, 1.0, 1.0, 0.0)   # top
    model.add_node(12, 2.0, 0.0, 0.0)   # right
    model.add_node(13, 1.0, -1.0, 0.0)  # bottom
    project = ProjectDatabase(model=model)
    project.add_material(elastic_material())
    return project


def test_rigid_connection_exports_rigid_link_beam():
    connection = ConnectionData(
        tag=20,
        name="Rigid beam-column joint",
        connection_type="rigid",
        node_i=1,
        node_j=2,
    )

    line = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert line == "ops.rigidLink('beam', 1, 2)"


def test_pinned_connection_ties_only_2d_translations():
    connection = ConnectionData(
        tag=21,
        name="Pinned beam end",
        connection_type="pinned",
        node_i=1,
        node_j=2,
    )

    line = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert line == "ops.equalDOF(1, 2, 1, 2)"
    assert ", 3)" not in line


def test_semi_rigid_2d_connection_exports_zero_length_rz_spring():
    connection = ConnectionData(
        tag=22,
        name="Semi-rigid RZ",
        connection_type="semiRigid",
        node_i=1,
        node_j=2,
        materials_by_dof={3: 1},
    )

    line = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert "ops.equalDOF(1, 2, 1, 2)" in line
    assert "ops.element('zeroLength', 22, 1, 2" in line
    assert "'-mat', 1, '-dir', 3" in line


def test_joint2d_round_trip_and_generator():
    project = frame2d_project()
    connection = ConnectionData(
        tag=30,
        name="RC beam-column joint",
        connection_type="Joint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 1,
        },
    )
    project.add_connection(connection)

    restored = ProjectDatabase.from_dict(project.to_dict())
    script = connection_to_openseespy(
        restored.connections[30],
        ndm=2,
        ndf=3,
    )

    assert restored.connections[30].parameters["external_nodes"] == [
        10,
        11,
        12,
        13,
    ]
    assert "_sare_joint2d_center_30" in script
    assert (
        "ops.element('Joint2D', 30, 10, 11, 12, 13, "
        "_sare_joint2d_center_30, 0, 0, 0, 0, 1, 1)"
        in script
    )


def test_krawinkler_panel_zone_generator_builds_expected_macro():
    project = frame2d_project()
    connection = ConnectionData(
        tag=40,
        name="Steel panel zone",
        connection_type="KrawinklerPanelZone",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "rigid_A": 1000.0,
            "rigid_E": 2.0e11,
            "rigid_I": 1000.0,
        },
    )
    project.add_connection(connection)

    script = connection_to_openseespy(
        connection,
        ndm=2,
        ndf=3,
    )

    assert script.count("ops.element('elasticBeamColumn'") == 8
    assert script.count("ops.equalDOF(") == 4
    assert (
        "ops.element('zeroLength', 40, "
        "_sare_pz_40_tlh, _sare_pz_40_tlv, '-mat', 1, '-dir', 3"
        in script
    )
    assert "ops.geomTransf('Linear', _sare_pz_40_tr)" in script
    assert "_sare_pz_40_ebase = max(" in script


def test_joint_models_are_restricted_to_2d_three_dof_frame_for_now():
    project = base_project()
    project.model.add_node(3, 0.0, 1.0, 0.0)
    project.model.add_node(4, 1.0, 1.0, 0.0)
    connection = ConnectionData(
        tag=31,
        name="Wrong dimensional Joint2D",
        connection_type="Joint2D",
        node_i=1,
        node_j=2,
        parameters={
            "external_nodes": [1, 2, 3, 4],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "2D frame model" in str(exc)
    else:
        raise AssertionError("Expected Joint2D in a 3D model to fail")


def test_joint_panel_material_is_tracked_as_connection_dependency():
    project = frame2d_project()
    connection = ConnectionData(
        tag=32,
        name="Dependency joint",
        connection_type="Joint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
        },
    )
    project.add_connection(connection)

    assert project.connections_using_material(1) == [32]


def test_krawinkler_internal_element_tags_reserve_future_connection_tags():
    connection = ConnectionData(
        tag=40,
        name="Panel zone tag reservation",
        connection_type="KrawinklerPanelZone",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "rigid_A": 1000.0,
            "rigid_E": 2.0e11,
            "rigid_I": 1000.0,
        },
    )

    script = connection_to_openseespy(
        connection,
        ndm=2,
        ndf=3,
        reserved_element_tag_max=75,
    )

    assert "+ [75]) + 1" in script
