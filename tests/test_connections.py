from openseespy_studio.generator import (
    analysis_to_openseespy,
    connection_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.project import (
    AnalysisSettingsData,
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


def test_joint2d_forces_compatible_constraint_handler_on_export():
    settings = AnalysisSettingsData(
        tag=1,
        name="Joint analysis",
        analysis_type="Static",
        constraints_handler="Plain",
    )

    lines = analysis_to_openseespy(
        settings,
        ndm=2,
        node_tags=[1],
        requires_joint2d_handler=True,
    )
    script = "\n".join(lines)

    assert "ops.constraints('Transformation')" in script
    assert "'constraints_handler': 'Transformation'" in script
    assert "Joint2D requires Transformation/Penalty" in script


def test_joint2d_rejects_external_chords_that_do_not_bisect():
    project = frame2d_project()
    connection = ConnectionData(
        tag=33,
        name="Bad joint geometry",
        connection_type="Joint2D",
        node_i=10,
        node_j=12,
        parameters={
            "external_nodes": [10, 12, 11, 13],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "bisect" in str(exc) or "cyclically" in str(exc)
    else:
        raise AssertionError("Expected invalid Joint2D geometry to fail")


def test_krawinkler_requires_axis_aligned_left_top_right_bottom_layout():
    model = StructuralModel(name="Rotated panel", ndm=2, ndf=3)
    model.add_node(20, -1.0, -1.0, 0.0)
    model.add_node(21, -1.0, 1.0, 0.0)
    model.add_node(22, 1.0, 1.0, 0.0)
    model.add_node(23, 1.0, -1.0, 0.0)
    project = ProjectDatabase(model=model)
    project.add_material(elastic_material())
    connection = ConnectionData(
        tag=41,
        name="Rotated Krawinkler layout",
        connection_type="KrawinklerPanelZone",
        node_i=20,
        node_j=21,
        parameters={
            "external_nodes": [20, 21, 22, 23],
            "panel_material": 1,
            "rigid_A": 1000.0,
            "rigid_E": 2.0e11,
            "rigid_I": 1000.0,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "axis-aligned" in str(exc)
    else:
        raise AssertionError("Expected non-axis-aligned Krawinkler layout to fail")


def test_joint_external_node_edit_revalidates_joint_geometry():
    project = frame2d_project()
    connection = ConnectionData(
        tag=34,
        name="Editable joint",
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
    project.model.set_coordinates(12, 3.0, 0.0, 0.0)

    try:
        project.validate_node_state(12)
    except ValueError as exc:
        assert "bisect" in str(exc)
    else:
        raise AssertionError("Expected edited external node to invalidate Joint2D")


def test_importer_recovers_native_joint2d():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(10, 0.0, 0.0)
ops.node(11, 1.0, 1.0)
ops.node(12, 2.0, 0.0)
ops.node(13, 1.0, -1.0)
ops.uniaxialMaterial('Elastic', 1, 1000.0)
ops.element('Joint2D', 30, 10, 11, 12, 13, 130, 1, 0)
"""
    result = import_openseespy_source(
        source,
        source_name="joint2d_import.py",
    )

    assert 30 in result.project.connections
    connection = result.project.connections[30]
    assert connection.connection_type == "Joint2D"
    assert connection.parameters["external_nodes"] == [10, 11, 12, 13]
    assert connection.parameters["panel_material"] == 1
    assert connection.parameters["interface_materials"] == [0, 0, 0, 0]
    assert connection.parameters["large_disp"] == 0
    assert connection.parameters["imported_center_node_tag"] == 130


def test_plain_analysis_rejected_when_joint2d_exists():
    project = frame2d_project()
    project.add_connection(
        ConnectionData(
            tag=35,
            name="Joint before analysis",
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
    )
    analysis = AnalysisSettingsData(
        tag=1,
        name="Bad Plain analysis",
        analysis_type="Static",
        constraints_handler="Plain",
    )

    try:
        project.add_analysis(analysis)
    except ValueError as exc:
        assert "Joint2D" in str(exc)
        assert "Transformation" in str(exc)
    else:
        raise AssertionError(
            "Expected Plain analysis with Joint2D to be rejected"
        )


def test_joint2d_rejected_when_plain_analysis_already_exists():
    project = frame2d_project()
    project.add_analysis(
        AnalysisSettingsData(
            tag=1,
            name="Existing Plain analysis",
            analysis_type="Static",
            constraints_handler="Plain",
        )
    )
    connection = ConnectionData(
        tag=36,
        name="Joint after analysis",
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

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "Joint2D" in str(exc)
        assert "Transformation" in str(exc)
    else:
        raise AssertionError(
            "Expected Joint2D with existing Plain analysis to be rejected"
        )
