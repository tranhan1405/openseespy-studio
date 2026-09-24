from openseespy_studio.generator import (
    analysis_to_openseespy,
    connection_to_openseespy,
    recorder_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.result_catalog import result_choices_for_analysis
from openseespy_studio.project import (
    AnalysisSettingsData,
    ConnectionData,
    MaterialData,
    ProjectDatabase,
    RecorderData,
    SolutionResultData,
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
        response="force",
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


def test_krawinkler_internal_members_are_excluded_from_rayleigh_damping():
    settings = AnalysisSettingsData(
        tag=1,
        name="Panel-zone transient",
        analysis_type="Transient",
        constraints_handler="Transformation",
        rayleigh_model="DirectCoefficients",
        rayleigh_alpha_m=0.0,
        rayleigh_beta_k=0.02,
        rayleigh_beta_k_init=0.0,
        rayleigh_beta_k_comm=0.0,
    )

    script = "\n".join(analysis_to_openseespy(
        settings,
        ndm=2,
        node_tags=[1],
        element_tags=[40],
        krawinkler_panel_zone_tags=[40],
    ))

    rayleigh_index = script.index("ops.rayleigh(0, 0.02, 0, 0)")
    region_text = (
        "ops.region(40, '-eleOnly', "
        "_sare_pz_40_ebase + 0, _sare_pz_40_ebase + 1, "
        "_sare_pz_40_ebase + 2, _sare_pz_40_ebase + 3, "
        "_sare_pz_40_ebase + 4, _sare_pz_40_ebase + 5, "
        "_sare_pz_40_ebase + 6, _sare_pz_40_ebase + 7, "
        "'-rayleigh', 0.0, 0.0, 0.0, 0.0)"
    )
    region_index = script.index(region_text)

    assert region_index > rayleigh_index


def add_elastic_materials(
    project: ProjectDatabase,
    start: int,
    stop: int,
) -> None:
    for tag in range(start, stop + 1):
        if tag in project.materials:
            continue
        project.add_material(elastic_material(tag))


def test_beam_column_joint_exports_13_material_components_and_factors():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    connection = ConnectionData(
        tag=90,
        name="RC beam-column joint",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 0.85,
            "width_factor": 0.9,
        },
    )
    project.add_connection(connection)

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert (
        "ops.element('beamColumnJoint', 90, 11, 12, 13, 10, "
        + ", ".join(str(tag) for tag in range(1, 14))
        + ", 0.85, 0.9)"
        in script
    )
    assert project.connections_using_material(13) == [90]


def test_beam_column_joint_omits_default_geometry_factors():
    connection = ConnectionData(
        tag=91,
        name="Default factors",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    )

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert script.endswith(", 11, 12, 13)")
    assert ", 1, 1)" not in script[-12:]


def test_importer_recovers_beam_column_joint():
    material_lines = "\n".join(
        f"ops.uniaxialMaterial('Elastic', {tag}, {1000.0 + tag})"
        for tag in range(1, 14)
    )
    source = f"""
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(10, 0.0, 0.0)
ops.node(11, 1.0, 1.0)
ops.node(12, 2.0, 0.0)
ops.node(13, 1.0, -1.0)
{material_lines}
ops.element(
    'beamColumnJoint', 90, 11, 12, 13, 10,
    {", ".join(str(tag) for tag in range(1, 14))},
    0.8, 0.9,
)
"""
    result = import_openseespy_source(
        source,
        source_name="beam_column_joint.py",
    )
    connection = result.project.connections[90]

    assert connection.connection_type == "BeamColumnJoint"
    assert connection.parameters["component_materials"] == list(
        range(1, 14)
    )
    assert connection.parameters["height_factor"] == 0.8
    assert connection.parameters["width_factor"] == 0.9


def test_lehigh_joint2d_exports_nine_mode_materials_ccw():
    project = frame2d_project()
    add_elastic_materials(project, 2, 9)
    connection = ConnectionData(
        tag=92,
        name="Lehigh joint",
        connection_type="LehighJoint2D",
        node_i=10,
        node_j=13,
        parameters={
            "external_nodes": [10, 13, 12, 11],
            "mode_materials": list(range(1, 10)),
        },
    )
    project.add_connection(connection)

    script = connection_to_openseespy(connection, ndm=2, ndf=3)

    assert (
        "ops.element('LehighJoint2D', 92, 10, 13, 12, 11, "
        + ", ".join(str(tag) for tag in range(1, 10))
        + ")"
        in script
    )


def test_lehigh_joint2d_rejects_clockwise_node_order():
    project = frame2d_project()
    add_elastic_materials(project, 2, 9)
    connection = ConnectionData(
        tag=93,
        name="Clockwise Lehigh",
        connection_type="LehighJoint2D",
        node_i=10,
        node_j=11,
        parameters={
            "external_nodes": [10, 11, 12, 13],
            "mode_materials": list(range(1, 10)),
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "counter-clockwise" in str(exc)
    else:
        raise AssertionError(
            "Expected clockwise LehighJoint2D node order to fail"
        )


def test_importer_recovers_lehigh_joint2d():
    material_lines = "\n".join(
        f"ops.uniaxialMaterial('Elastic', {tag}, {1000.0 + tag})"
        for tag in range(1, 10)
    )
    source = f"""
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(10, 0.0, 0.0)
ops.node(13, 1.0, -1.0)
ops.node(12, 2.0, 0.0)
ops.node(11, 1.0, 1.0)
{material_lines}
ops.element(
    'LehighJoint2D', 92, 10, 13, 12, 11,
    {", ".join(str(tag) for tag in range(1, 10))}
)
"""
    result = import_openseespy_source(
        source,
        source_name="lehigh_joint.py",
    )
    connection = result.project.connections[92]

    assert connection.connection_type == "LehighJoint2D"
    assert connection.parameters["external_nodes"] == [10, 13, 12, 11]
    assert connection.parameters["mode_materials"] == list(range(1, 10))


def test_joint_response_result_catalog_is_available_for_nonlinear_analysis():
    choices = result_choices_for_analysis(
        "Cyclic",
        "NormUnbalance",
    )

    joint_choices = [
        choice
        for choice in choices
        if choice.result_type == "JointResponse"
    ]

    assert len(joint_choices) == 1
    assert joint_choices[0].category == "Connections & Joints"


def test_joint_response_validates_target_and_response_query():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=94,
        name="RC response joint",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    project.add_analysis(AnalysisSettingsData(
        tag=1,
        name="Cyclic",
        analysis_type="Cyclic",
        constraints_handler="Transformation",
        control_node=12,
        control_dof=1,
        cyclic_targets=[0.01, -0.01],
        cyclic_increment=0.005,
    ))

    result = SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="Panel shear",
        result_type="JointResponse",
        element_scope=[94],
        settings={
            "response": "shearPanel",
            "component": 1,
            "curve_mode": "force_deformation",
        },
    )
    project.add_solution_result(result)
    assert project.solution_results[1].settings["response"] == "shearPanel"

    bad = SolutionResultData(
        tag=2,
        analysis_tag=1,
        name="Bad query",
        result_type="JointResponse",
        element_scope=[94],
        settings={"response": "localForce"},
    )
    try:
        project.add_solution_result(bad)
    except ValueError as exc:
        assert "localForce" in str(exc)
        assert "BeamColumnJoint" in str(exc)
    else:
        raise AssertionError(
            "Expected unsupported BeamColumnJoint result query to fail"
        )


def test_generated_analysis_captures_requested_joint_histories_only():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=95,
        name="Captured joint",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    analysis = AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    )
    project.add_analysis(analysis)
    project.add_solution_result(SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="Panel loop",
        result_type="JointResponse",
        element_scope=[95],
        settings={
            "response": "shearPanel",
            "component": 1,
            "curve_mode": "force_deformation",
        },
    ))

    script = to_openseespy(
        project.model,
        materials=project.materials,
        connections=project.connections,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
        solution_results=project.solution_results,
    )

    assert "'joints':" in script
    assert "_studio_joint_response_specs" in script
    assert "'shearPanel'" in script
    assert (
        "ops.eleResponse(_studio_joint_tag, _studio_joint_response, "
        "'stressStrain')"
        in script
    )


def test_joint_history_capture_is_absent_without_joint_result_request():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=96,
        name="Unrequested joint",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    project.add_analysis(AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    ))

    script = to_openseespy(
        project.model,
        materials=project.materials,
        connections=project.connections,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
        solution_results=project.solution_results,
    )

    # The generic runtime scaffold exists, but no joint tag/response is
    # requested and therefore no per-step eleResponse work is scheduled.
    assert "_studio_joint_response_specs = {}" in script

def test_beam_column_joint_component_recorder_adds_stress_strain_query():
    recorder = RecorderData(
        tag=40,
        name="Shear panel loop",
        recorder_type="Element",
        target_tags=[90],
        response="shearPanel",
    )

    command = "\n".join(recorder_to_openseespy(recorder))

    assert "'shearPanel', 'stressStrain'" in command


def test_generated_joint_history_uses_stress_strain_for_rc_components():
    settings = AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    )

    script = "\n".join(analysis_to_openseespy(
        settings,
        ndm=2,
        node_tags=[1],
        element_tags=[90],
        joint_response_specs={
            90: {
                "connection_type": "BeamColumnJoint",
                "responses": ["shearPanel", "deformation"],
            }
        },
    ))

    assert (
        "ops.eleResponse(_studio_joint_tag, "
        "_studio_joint_response, 'stressStrain')"
        in script
    )
    assert "'shearPanel'" in script


def test_joint_force_deformation_request_adds_paired_response():
    project = frame2d_project()
    project.add_connection(ConnectionData(
        tag=97,
        name="Panel spring",
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
    ))
    analysis = AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    )
    project.add_analysis(analysis)
    project.add_solution_result(SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="Panel M-rotation",
        result_type="JointResponse",
        element_scope=[97],
        settings={
            "response": "force",
            "curve_mode": "force_deformation",
        },
    ))

    from openseespy_studio.generator import build_joint_response_specs

    specs = build_joint_response_specs(
        connections=project.connections,
        solution_results=project.solution_results,
        active_analysis=analysis,
    )

    assert specs[97]["responses"] == ["force", "deformation"]


def beam_column_joint_3d_project() -> ProjectDatabase:
    model = StructuralModel()
    model.ndm = 3
    model.ndf = 6
    # Four coplanar nodes: Node 1↔3 is the joint-height chord and
    # Node 2↔4 is the joint-width chord.
    model.add_node(101, 0.0, 0.0, -1.0)
    model.add_node(102, 1.0, 0.0, 0.0)
    model.add_node(103, 0.0, 0.0, 1.0)
    model.add_node(104, -1.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)
    for tag in range(1, 14):
        project.add_material(elastic_material(tag))
    return project


def test_beam_column_joint_supports_native_3d_six_dof_formulation():
    project = beam_column_joint_3d_project()
    connection = ConnectionData(
        tag=190,
        name="3D RC beam-column joint",
        connection_type="BeamColumnJoint",
        node_i=101,
        node_j=102,
        parameters={
            "external_nodes": [101, 102, 103, 104],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    )

    project.add_connection(connection)
    script = connection_to_openseespy(
        connection,
        ndm=3,
        ndf=6,
    )

    assert project.connections[190].parameters["external_nodes"] == [
        101, 102, 103, 104
    ]
    assert (
        "ops.element('beamColumnJoint', 190, 101, 102, 103, 104, "
        + ", ".join(str(tag) for tag in range(1, 14))
        + ")"
        in script
    )


def test_beam_column_joint_3d_rejects_nonorthogonal_opposite_chords():
    project = beam_column_joint_3d_project()
    # Preserve the common midpoint but skew the 2↔4 chord so it is no
    # longer perpendicular to the 1↔3 height chord.
    project.model.nodes[102].xyz = (1.0, 0.0, 0.5)
    project.model.nodes[104].xyz = (-1.0, 0.0, -0.5)
    connection = ConnectionData(
        tag=191,
        name="Skew 3D joint",
        connection_type="BeamColumnJoint",
        node_i=101,
        node_j=102,
        parameters={
            "external_nodes": [101, 102, 103, 104],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "perpendicular" in str(exc)
    else:
        raise AssertionError(
            "Expected a nonorthogonal 3D BeamColumnJoint to be rejected"
        )


def test_beam_column_joint_3d_preserves_nondefault_geometry_factors():
    project = beam_column_joint_3d_project()
    connection = ConnectionData(
        tag=192,
        name="3D preserved factors",
        connection_type="BeamColumnJoint",
        node_i=101,
        node_j=102,
        parameters={
            "external_nodes": [101, 102, 103, 104],
            "component_materials": list(range(1, 14)),
            "height_factor": 0.8,
            "width_factor": 0.9,
        },
    )

    project.add_connection(connection)
    script = connection_to_openseespy(
        connection,
        ndm=3,
        ndf=6,
    )

    assert project.connections[192].parameters["height_factor"] == 0.8
    assert project.connections[192].parameters["width_factor"] == 0.9
    assert script.endswith(", 0.8, 0.9)")


def test_beam_column_joint_deformation_vector_has_four_named_components():
    # OpenSees BeamColumnJoint deformation response returns four values:
    # bar-slip, interface shear, shear panel, and total joint deformation.
    result = SolutionResultData(
        tag=100,
        analysis_tag=1,
        name="Total joint deformation",
        result_type="JointResponse",
        element_scope=[190],
        settings={
            "response": "deformation",
            "component": 4,
            "connection_type": "BeamColumnJoint",
            "curve_mode": "history",
        },
    )

    assert result.settings["response"] == "deformation"
    assert result.settings["component"] == 4


def test_beam_column_joint_2d_requires_global_y_height_and_x_width():
    model = StructuralModel(name="Rotated BCJ", ndm=2, ndf=3)
    # A geometrically valid square rotated 45 degrees. BeamColumnJoint2d
    # uses global UX/UY directly, so this orientation is not supported by
    # the native element without a transformation.
    model.add_node(201, 1.0, 1.0, 0.0)
    model.add_node(202, 1.0, -1.0, 0.0)
    model.add_node(203, -1.0, -1.0, 0.0)
    model.add_node(204, -1.0, 1.0, 0.0)
    project = ProjectDatabase(model=model)
    for tag in range(1, 14):
        project.add_material(elastic_material(tag))

    connection = ConnectionData(
        tag=193,
        name="Rotated 2D RC joint",
        connection_type="BeamColumnJoint",
        node_i=201,
        node_j=202,
        parameters={
            "external_nodes": [201, 202, 203, 204],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    )

    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "global Y" in str(exc)
        assert "global X" in str(exc)
    else:
        raise AssertionError(
            "Expected rotated BeamColumnJoint2d geometry to be rejected"
        )


def test_importer_warns_and_preserves_beam_column_joint_3d_factors():
    material_lines = "\n".join(
        f"ops.uniaxialMaterial('Elastic', {tag}, {1000.0 + tag})"
        for tag in range(1, 14)
    )
    source = f"""
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(101, 0.0, 0.0, -1.0)
ops.node(102, 1.0, 0.0, 0.0)
ops.node(103, 0.0, 0.0, 1.0)
ops.node(104, -1.0, 0.0, 0.0)
{material_lines}
ops.element(
    'beamColumnJoint', 190, 101, 102, 103, 104,
    {", ".join(str(tag) for tag in range(1, 14))},
    0.8, 0.9,
)
"""
    result = import_openseespy_source(
        source,
        source_name="beam_column_joint_3d_factors.py",
    )

    connection = result.project.connections[190]
    assert connection.parameters["height_factor"] == 0.8
    assert connection.parameters["width_factor"] == 0.9
    assert any(
        issue.severity == "WARNING"
        and "factors were preserved" in issue.message
        and "elemHeight/elemWidth" in issue.message
        for issue in result.issues
    )


def test_beam_column_joint_material_tag_update_propagates_to_components():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=194,
        name="RC dependency joint",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))

    project.update_material(13, elastic_material(130))

    assert project.connections[194].parameters["component_materials"][-1] == 130
    assert project.connections_using_material(130) == [194]
    assert project.connections_using_material(13) == []


def test_beam_column_joint_blocks_deleting_component_material():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=195,
        name="RC delete guard",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))

    try:
        project.remove_material(13)
    except ValueError as exc:
        assert "connections 195" in str(exc)
    else:
        raise AssertionError(
            "Expected BeamColumnJoint component material deletion to be blocked"
        )


def test_beam_column_joint_result_component_range_is_validated():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=196,
        name="RC result component guard",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    project.add_analysis(AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    ))

    project.add_solution_result(SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="Total deformation",
        result_type="JointResponse",
        element_scope=[196],
        settings={
            "response": "deformation",
            "component": 4,
        },
    ))
    assert project.solution_results[1].settings["component"] == 4

    bad = SolutionResultData(
        tag=2,
        analysis_tag=1,
        name="Bad deformation component",
        result_type="JointResponse",
        element_scope=[196],
        settings={
            "response": "deformation",
            "component": 5,
        },
    )
    try:
        project.add_solution_result(bad)
    except ValueError as exc:
        assert "outside 1..4" in str(exc)
    else:
        raise AssertionError(
            "Expected BeamColumnJoint deformation component 5 to fail"
        )


def test_beam_column_joint_invalid_legacy_node_order_is_rejected_on_load():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=197,
        name="Valid RC joint before legacy mutation",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    data = project.to_dict()
    connection_data = next(
        item for item in data["connections"] if item["tag"] == 197
    )
    # Reproduce the old generic Left → Top → Right → Bottom ordering.
    connection_data["node_i"] = 10
    connection_data["node_j"] = 11
    connection_data["parameters"]["external_nodes"] = [10, 11, 12, 13]

    try:
        ProjectDatabase.from_dict(data)
    except ValueError as exc:
        assert "global Y" in str(exc)
        assert "global X" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid legacy BeamColumnJoint node order to fail load"
        )


def test_beam_column_joint_total_result_menu_targets_component_four():
    from openseespy_studio.ui.main_window import MainWindow

    connection = ConnectionData(
        tag=198,
        name="Result mapping joint",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    )

    choices = MainWindow._joint_response_choices(None, connection)
    total = next(
        item for item in choices
        if item[0] == "Total Joint Deformation"
    )

    assert total == ("Total Joint Deformation", "deformation", 4)


def test_results_panel_labels_beam_column_joint_deformation_components():
    from openseespy_studio.ui.results_panel import ResultsPanel

    labels = ResultsPanel._joint_component_labels(
        "BeamColumnJoint",
        "deformation",
        4,
    )

    assert labels == [
        "Bar-slip contribution",
        "Interface shear contribution",
        "Shear-panel contribution",
        "Total joint deformation",
    ]


def test_generic_joint_result_insert_defaults_beam_column_joint_to_total():
    import inspect
    from openseespy_studio.ui.main_window import MainWindow

    source = inspect.getsource(MainWindow._insert_solution_result)

    assert 'generic_joint_request' in source
    assert 'connection.connection_type == "BeamColumnJoint"' in source
    assert 'result_settings["component"] = 4' in source
    assert '"connection_type" not in result_settings' in source


def test_beam_column_joint_3d_blocks_external_displacement_result_query():
    project = beam_column_joint_3d_project()
    project.add_connection(ConnectionData(
        tag=199,
        name="3D external displacement guard",
        connection_type="BeamColumnJoint",
        node_i=101,
        node_j=102,
        parameters={
            "external_nodes": [101, 102, 103, 104],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    project.add_analysis(AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    ))

    result = SolutionResultData(
        tag=10,
        analysis_tag=1,
        name="Unsafe external displacement",
        result_type="JointResponse",
        element_scope=[199],
        settings={
            "response": "externalDisplacement",
            "component": 1,
        },
    )
    try:
        project.add_solution_result(result)
    except ValueError as exc:
        assert "externalDisplacement is disabled" in str(exc)
        assert "24 external DOFs" in str(exc)
    else:
        raise AssertionError(
            "Expected BeamColumnJoint3d externalDisplacement to be blocked"
        )


def test_beam_column_joint_2d_external_displacement_remains_available():
    project = frame2d_project()
    add_elastic_materials(project, 2, 13)
    project.add_connection(ConnectionData(
        tag=200,
        name="2D external displacement",
        connection_type="BeamColumnJoint",
        node_i=11,
        node_j=12,
        parameters={
            "external_nodes": [11, 12, 13, 10],
            "component_materials": list(range(1, 14)),
            "height_factor": 1.0,
            "width_factor": 1.0,
        },
    ))
    project.add_analysis(AnalysisSettingsData(
        tag=1,
        name="Static",
        analysis_type="Static",
        constraints_handler="Transformation",
        steps=1,
        load_increment=1.0,
    ))
    project.add_solution_result(SolutionResultData(
        tag=11,
        analysis_tag=1,
        name="2D external displacement",
        result_type="JointResponse",
        element_scope=[200],
        settings={
            "response": "externalDisplacement",
            "component": 12,
        },
    ))

    assert project.solution_results[11].settings["component"] == 12
