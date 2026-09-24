from openseespy_studio.generator import (
    analysis_to_openseespy,
    connection_to_openseespy,
    recorder_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.project import (
    AnalysisSettingsData,
    ConnectionData,
    MaterialData,
    ProjectDatabase,
    RecorderData,
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
    assert "'-doRayleigh'" in line
    assert "'-doRayleigh', 1" not in line


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
        materials_by_dof={6: 1},
    )

    line = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert "ops.equalDOF(1, 2, 1, 2)" in line
    assert "ops.element('zeroLength', 22, 1, 2" in line
    assert "'-mat', 1, '-dir', 6" in line


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
        "_sare_joint2d_center_30, 1, 1)"
        in script
    )
    assert ", 0, 0, 0, 0, 1, 1)" not in script


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
        "_sare_pz_40_tlh, _sare_pz_40_tlv, '-mat', 1, '-dir', 6"
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


def test_zero_length_2d_uses_direction_6_for_rz():
    project = frame2d_project()
    connection = ConnectionData(
        tag=50,
        name="2D zeroLength RZ",
        connection_type="zeroLength",
        node_i=1,
        node_j=2,
        materials_by_dof={6: 1},
    )

    project.add_connection(connection)
    script = connection_to_openseespy(
        connection,
        ndm=2,
        ndf=3,
    )

    assert "'-dir', 6" in script


def test_zero_length_2d_rejects_direction_3_as_out_of_plane_translation():
    project = frame2d_project()
    connection = ConnectionData(
        tag=51,
        name="Wrong 2D zeroLength direction",
        connection_type="zeroLength",
        node_i=1,
        node_j=2,
        materials_by_dof={3: 1},
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "Allowed directions" in str(exc)
        assert "[1, 2, 6]" in str(exc)
    else:
        raise AssertionError(
            "Expected 2D zeroLength direction 3 to be rejected"
        )


def test_two_node_link_2d_uses_direction_3_for_rz():
    project = frame2d_project()
    # twoNodeLink can be finite length, so use separated external nodes.
    connection = ConnectionData(
        tag=52,
        name="2D twoNodeLink RZ",
        connection_type="twoNodeLink",
        node_i=10,
        node_j=12,
        materials_by_dof={3: 1},
    )

    project.add_connection(connection)
    script = connection_to_openseespy(
        connection,
        ndm=2,
        ndf=3,
    )

    assert "'-dir', 3" in script


def test_importer_accepts_2d_zero_length_rz_direction_6():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 0.0, 0.0)
ops.uniaxialMaterial('Elastic', 1, 1000.0)
ops.element('zeroLength', 20, 1, 2, '-mat', 1, '-dir', 6)
"""
    result = import_openseespy_source(
        source,
        source_name="zero_length_rz_2d.py",
    )

    assert 20 in result.project.connections
    assert result.project.connections[20].materials_by_dof == {6: 1}


def test_offset_rigid_connection_requires_transformation_handler():
    project = frame2d_project()
    project.add_analysis(
        AnalysisSettingsData(
            tag=1,
            name="Plain analysis",
            analysis_type="Static",
            constraints_handler="Plain",
        )
    )
    connection = ConnectionData(
        tag=60,
        name="Offset rigid arm",
        connection_type="rigid",
        node_i=10,
        node_j=12,
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "Rigid connections between separated nodes" in str(exc)
        assert "Transformation" in str(exc)
    else:
        raise AssertionError(
            "Expected offset rigid connection with Plain handler to fail"
        )


def test_coincident_rigid_connection_can_coexist_with_plain_handler():
    project = frame2d_project()
    project.add_analysis(
        AnalysisSettingsData(
            tag=1,
            name="Plain analysis",
            analysis_type="Static",
            constraints_handler="Plain",
        )
    )
    connection = ConnectionData(
        tag=61,
        name="Coincident rigid joint",
        connection_type="rigid",
        node_i=1,
        node_j=2,
    )

    project.add_connection(connection)

    assert project.connections[61].connection_type == "rigid"


def three_basic_connection_project() -> ProjectDatabase:
    model = StructuralModel(name="Basic connection models", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 0.0, 0.0, 0.0)
    model.add_node(4, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)
    project.add_material(elastic_material())
    project.add_connection(ConnectionData(
        tag=20,
        name="Rigid",
        connection_type="rigid",
        node_i=1,
        node_j=2,
    ))
    project.add_connection(ConnectionData(
        tag=21,
        name="Pinned",
        connection_type="pinned",
        node_i=1,
        node_j=3,
    ))
    project.add_connection(ConnectionData(
        tag=22,
        name="Semi-rigid RZ",
        connection_type="semiRigid",
        node_i=1,
        node_j=4,
        materials_by_dof={6: 1},
    ))
    return project


def test_rigid_and_pinned_are_not_element_recorder_targets():
    project = three_basic_connection_project()

    for recorder_tag, connection_tag in ((1, 20), (2, 21)):
        recorder = RecorderData(
            tag=recorder_tag,
            name=f"Bad recorder {connection_tag}",
            recorder_type="Element",
            target_tags=[connection_tag],
            response="globalForce",
        )
        try:
            project.add_recorder(recorder)
        except ValueError as exc:
            assert "MPC constraints" in str(exc)
            assert str(connection_tag) in str(exc)
        else:
            raise AssertionError(
                "Rigid/Pinned connection should not be accepted as "
                "an Element recorder target"
            )


def test_semi_rigid_remains_an_element_recorder_target():
    project = three_basic_connection_project()
    recorder = RecorderData(
        tag=3,
        name="Semi-rigid force",
        recorder_type="Element",
        target_tags=[22],
        response="force",
    )

    project.add_recorder(recorder)

    assert project.recorders[3].target_tags == [22]
    assert project.recorders[3].response == "force"


def test_editing_semi_rigid_to_rigid_prunes_element_recorder():
    project = three_basic_connection_project()
    project.add_recorder(RecorderData(
        tag=4,
        name="Spring force",
        recorder_type="Element",
        target_tags=[22],
        response="globalForce",
    ))

    project.update_connection(
        22,
        ConnectionData(
            tag=22,
            name="Now rigid",
            connection_type="rigid",
            node_i=1,
            node_j=2,
        ),
    )

    assert 4 not in project.recorders


def test_generated_analysis_element_scope_excludes_rigid_and_pinned():
    project = three_basic_connection_project()
    analysis = AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
    )
    project.add_analysis(analysis)

    script = to_openseespy(
        project.model,
        materials=project.materials,
        connections=project.connections,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
    )

    assert "ops.rigidLink('beam', 1, 2)" in script
    assert "ops.equalDOF(1, 3, 1, 2)" in script
    assert "ops.element('zeroLength', 22, 1, 4" in script
    assert "_studio_element_tags = [22]" in script


def test_generator_rejects_stale_element_recorder_on_rigid_connection():
    project = three_basic_connection_project()
    stale = RecorderData(
        tag=5,
        name="Legacy rigid recorder",
        recorder_type="Element",
        target_tags=[20],
        response="globalForce",
    )

    try:
        to_openseespy(
            project.model,
            materials=project.materials,
            connections=project.connections,
            recorders={5: stale},
        )
    except ValueError as exc:
        assert "non-element" in str(exc)
        assert "20" in str(exc)
    else:
        raise AssertionError(
            "Generator should reject an Element recorder targeting rigidLink"
        )


def test_semi_rigid_3d_ties_all_non_spring_dofs():
    connection = ConnectionData(
        tag=23,
        name="3D semi-rigid RZ",
        connection_type="semiRigid",
        node_i=1,
        node_j=2,
        materials_by_dof={6: 1},
    )

    script = connection_to_openseespy(
        connection,
        ndm=3,
        ndf=6,
    )

    assert "ops.equalDOF(1, 2, 1, 2, 3, 4, 5)" in script
    assert "'-dir', 6" in script


def test_two_node_link_nonzero_length_uses_geometry_orientation_by_default():
    project = frame2d_project()
    connection = ConnectionData(
        tag=70,
        name="Geometry-oriented link",
        connection_type="twoNodeLink",
        node_i=10,
        node_j=12,
        materials_by_dof={1: 1, 3: 1},
        parameters={
            "orientation_override": False,
            "p_delta": [],
            "shear_dist": [],
            "mass": 0.0,
        },
    )
    project.add_connection(connection)

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert "ops.element('twoNodeLink', 70, 10, 12" in script
    assert "'-dir', 1, 3" in script
    assert "'-orient'" not in script


def test_two_node_link_exports_advanced_options_with_native_flags():
    project = frame2d_project()
    connection = ConnectionData(
        tag=71,
        name="Advanced link",
        connection_type="twoNodeLink",
        node_i=10,
        node_j=12,
        materials_by_dof={1: 1, 3: 1},
        orient_x=(0.0, 1.0, 0.0),
        orient_y=(-1.0, 0.0, 0.0),
        do_rayleigh=True,
        parameters={
            "orientation_override": True,
            "p_delta": [0.4, 0.4],
            "shear_dist": [0.35],
            "mass": 2.5,
        },
    )
    project.add_connection(connection)

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert "'-orient', 0, 1, 0, -1, 0, 0" in script
    assert "'-pDelta', 0.4, 0.4" in script
    assert "'-shearDist', 0.35" in script
    assert "'-doRayleigh'" in script
    assert "'-doRayleigh', 1" not in script
    assert "'-mass', 2.5" in script


def test_two_node_link_rejects_wrong_advanced_option_count_for_dimension():
    project = frame2d_project()
    connection = ConnectionData(
        tag=72,
        name="Wrong 2D PDelta",
        connection_type="twoNodeLink",
        node_i=10,
        node_j=12,
        materials_by_dof={1: 1},
        parameters={
            "orientation_override": False,
            "p_delta": [0.2, 0.2, 0.2, 0.2],
            "shear_dist": [],
            "mass": 0.0,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "2D requires 2 p_delta" in str(exc)
    else:
        raise AssertionError(
            "Expected 2D twoNodeLink with four P-Delta ratios to fail"
        )


def test_importer_preserves_two_node_link_advanced_options():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 2.0, 0.0)
ops.uniaxialMaterial('Elastic', 1, 1000.0)
ops.element(
    'twoNodeLink', 20, 1, 2,
    '-mat', 1, 1,
    '-dir', 1, 3,
    '-orient', 0.0, 1.0, 0.0, -1.0, 0.0, 0.0,
    '-pDelta', 0.3, 0.4,
    '-shearDist', 0.25,
    '-doRayleigh',
    '-mass', 3.5,
)
"""
    result = import_openseespy_source(
        source,
        source_name="two_node_link_advanced.py",
    )

    connection = result.project.connections[20]
    assert connection.connection_type == "twoNodeLink"
    assert connection.materials_by_dof == {1: 1, 3: 1}
    assert connection.parameters["orientation_override"] is True
    assert connection.parameters["p_delta"] == [0.3, 0.4]
    assert connection.parameters["shear_dist"] == [0.25]
    assert connection.parameters["mass"] == 3.5
    assert connection.do_rayleigh is True

    script = connection_to_openseespy(connection, ndm=2, ndf=3)
    assert "'-pDelta', 0.3, 0.4" in script
    assert "'-shearDist', 0.25" in script
    assert "'-doRayleigh'" in script


def test_joint2d_nonzero_interface_materials_export_full_form():
    project = frame2d_project()
    project.add_material(elastic_material(2))
    connection = ConnectionData(
        tag=73,
        name="Joint with interface springs",
        connection_type="Joint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "interface_materials": [2, 0, 2, 0],
            "large_disp": 2,
        },
    )
    project.add_connection(connection)

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert (
        "ops.element('Joint2D', 73, 10, 11, 12, 13, "
        "_sare_joint2d_center_73, 2, 0, 2, 0, 1, 2)"
        in script
    )


def test_imported_joint2d_center_node_tag_is_preserved_on_export():
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
        source_name="joint2d_center_roundtrip.py",
    )
    connection = result.project.connections[30]

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert "# Preserved imported Joint2D center-node tag 130" in script
    assert "ops.element('Joint2D', 30, 10, 11, 12, 13, 130, 1, 0)" in script
    assert "_sare_joint2d_center_30 =" not in script


def test_joint2d_center_node_tag_cannot_collide_with_existing_node():
    project = frame2d_project()
    project.model.add_node(130, 5.0, 5.0, 0.0)
    connection = ConnectionData(
        tag=74,
        name="Center collision",
        connection_type="Joint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
            "imported_center_node_tag": 130,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "center node tag 130 already exists" in str(exc)
    else:
        raise AssertionError(
            "Expected Joint2D center-node collision to be rejected"
        )


def test_connection_specific_element_recorder_responses_are_validated():
    project = frame2d_project()
    project.add_connection(ConnectionData(
        tag=75,
        name="Link response",
        connection_type="twoNodeLink",
        node_i=10,
        node_j=12,
        materials_by_dof={1: 1},
        parameters={
            "orientation_override": False,
            "p_delta": [],
            "shear_dist": [],
            "mass": 0.0,
        },
    ))
    project.add_connection(ConnectionData(
        tag=76,
        name="Joint response",
        connection_type="Joint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
        },
    ))

    project.add_recorder(RecorderData(
        tag=20,
        name="Link basic force",
        recorder_type="Element",
        target_tags=[75],
        response="basicForce",
    ))
    project.add_recorder(RecorderData(
        tag=21,
        name="Joint deformation",
        recorder_type="Element",
        target_tags=[76],
        response="deformation",
    ))

    assert project.recorders[20].response == "basicForce"
    assert project.recorders[21].response == "deformation"

    bad = RecorderData(
        tag=22,
        name="Bad joint local force",
        recorder_type="Element",
        target_tags=[76],
        response="localForce",
    )
    try:
        project.add_recorder(bad)
    except ValueError as exc:
        assert "Joint2D" in str(exc)
        assert "localForce" in str(exc)
    else:
        raise AssertionError(
            "Expected unsupported Joint2D recorder response to fail"
        )


def test_krawinkler_public_tag_records_panel_spring_deformation():
    project = frame2d_project()
    connection = ConnectionData(
        tag=77,
        name="Panel response",
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
    recorder = RecorderData(
        tag=23,
        name="Panel distortion",
        recorder_type="Element",
        target_tags=[77],
        response="deformation",
    )

    project.add_recorder(recorder)
    commands = "\n".join(recorder_to_openseespy(recorder))

    assert "'-ele', 77" in commands
    assert "'deformation'" in commands


def test_joint_internal_nodes_respect_reserved_imported_center_tag():
    project = frame2d_project()
    # Separate joint cross so both macro types can coexist in the same test.
    project.model.add_node(20, 10.0, 0.0, 0.0)
    project.model.add_node(21, 11.0, 1.0, 0.0)
    project.model.add_node(22, 12.0, 0.0, 0.0)
    project.model.add_node(23, 11.0, -1.0, 0.0)

    panel_zone = ConnectionData(
        tag=40,
        name="Panel zone before imported Joint2D",
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
    imported_joint = ConnectionData(
        tag=80,
        name="Imported center reservation",
        connection_type="Joint2D",
        node_i=20,
        node_j=21,
        parameters={
            "external_nodes": [20, 21, 22, 23],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
            "imported_center_node_tag": 130,
        },
    )
    project.add_connection(panel_zone)
    project.add_connection(imported_joint)

    script = to_openseespy(
        project.model,
        materials=project.materials,
        connections=project.connections,
    )

    assert (
        "_sare_pz_40_nbase = max((list(ops.getNodeTags()) or [0]) + [130]) + 1"
        in script
    )
    assert "ops.element('Joint2D', 80, 20, 21, 22, 23, 130, 1, 0)" in script


def test_two_imported_joint2d_center_tags_must_be_unique():
    project = frame2d_project()
    project.model.add_node(20, 10.0, 0.0, 0.0)
    project.model.add_node(21, 11.0, 1.0, 0.0)
    project.model.add_node(22, 12.0, 0.0, 0.0)
    project.model.add_node(23, 11.0, -1.0, 0.0)

    project.add_connection(ConnectionData(
        tag=81,
        name="Joint A",
        connection_type="Joint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
            "imported_center_node_tag": 150,
        },
    ))

    duplicate = ConnectionData(
        tag=82,
        name="Joint B",
        connection_type="Joint2D",
        node_i=20,
        node_j=21,
        parameters={
            "external_nodes": [20, 21, 22, 23],
            "panel_material": 1,
            "interface_materials": [0, 0, 0, 0],
            "large_disp": 0,
            "imported_center_node_tag": 150,
        },
    )
    try:
        project.add_connection(duplicate)
    except ValueError as exc:
        assert "already reserved" in str(exc)
        assert "150" in str(exc)
    else:
        raise AssertionError(
            "Expected duplicate imported Joint2D center tag to fail"
        )
