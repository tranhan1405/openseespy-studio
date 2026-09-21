import pytest

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    ConnectionData,
    ConstraintData,
    FiberComponentData,
    FiberData,
    ElementLoadData,
    LoadPatternData,
    NodalLoadData,
    MaterialData,
    PrescribedDisplacementData,
    RecorderData,
    SectionData,
    ProjectDatabase,
    SelectionSetData,
    SolutionResultData,
    TimeSeriesData,
    TransformationData,
)


def build_project() -> ProjectDatabase:
    model = StructuralModel("Frame")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 5.0, 0.0, 0.0)
    model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    model.add_element(
        10,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=2,
        transf_tag=1,
        group="beam-x",
    )
    project = ProjectDatabase(name="Demo", model=model)
    project.selection_sets["BeamA"] = SelectionSetData(
        name="BeamA",
        node_tags={1, 2},
        element_tags={10},
    )
    return project


def test_project_round_trip_dict():
    original = build_project()
    restored = ProjectDatabase.from_dict(original.to_dict())

    assert restored.name == "Demo"
    assert restored.model.name == "Frame"
    assert restored.model.nodes[1].fixity == (1, 1, 1, 1, 1, 1)
    assert restored.model.elements[10].section_tag == 2
    assert restored.model.elements[10].transf_tag == 1
    assert restored.selection_sets["BeamA"].node_tags == {1, 2}
    assert restored.selection_sets["BeamA"].element_tags == {10}


def test_project_save_load(tmp_path):
    project = build_project()
    path = tmp_path / "demo.opsstudio"

    project.save(path)
    loaded = ProjectDatabase.load(path)

    assert loaded.to_dict() == project.to_dict()


def test_future_project_version_is_rejected():
    data = build_project().to_dict()
    data["version"] = 999

    try:
        ProjectDatabase.from_dict(data)
    except ValueError as exc:
        assert "newer than supported" in str(exc)
    else:
        raise AssertionError("Expected a future project version to be rejected")



def test_solution_result_round_trip_and_analysis_link():
    project = build_project()
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Push",
            "Pushover",
            control_node=2,
        )
    )
    project.add_solution_result(
        SolutionResultData(
            1,
            1,
            "Moment Mz",
            "MemberForce",
            element_scope=[10],
            settings={"component": "Mz", "scale": 1.0},
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.solution_results[1].analysis_tag == 1
    assert restored.solution_results[1].result_type == "MemberForce"
    assert restored.solution_results[1].element_scope == [10]
    assert restored.solution_results[1].settings["component"] == "Mz"
    assert restored.solution_results_for_analysis(1)[0].name == "Moment Mz"


def test_solution_results_follow_analysis_tag_change_and_delete():
    project = build_project()
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Static",
            "Static",
        )
    )
    project.add_solution_result(
        SolutionResultData(
            1,
            1,
            "Deformed Shape",
            "DeformedShape",
        )
    )

    project.update_analysis(
        1,
        AnalysisSettingsData(
            3,
            "Static renamed",
            "Static",
        ),
    )
    assert project.solution_results[1].analysis_tag == 3

    project.remove_analysis(3)
    assert project.solution_results == {}


def test_solution_result_scope_validation():
    project = build_project()
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Static",
            "Static",
        )
    )

    try:
        project.add_solution_result(
            SolutionResultData(
                1,
                1,
                "Bad Scope",
                "MemberForce",
                element_scope=[999],
            )
        )
    except ValueError as exc:
        assert "missing element" in str(exc)
    else:
        raise AssertionError("Expected solution result scope validation")



def test_solution_result_details_settings_update_and_round_trip():
    project = build_project()
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "History",
            "Transient",
            steps=20,
            dt=0.01,
        )
    )
    project.add_solution_result(
        SolutionResultData(
            1,
            1,
            "Node 2 UX History",
            "TimeHistory",
            node_scope=[2],
            settings={
                "node": 2,
                "quantity": "Displacement",
                "dof": 1,
            },
        )
    )

    updated = SolutionResultData(
        1,
        1,
        "Node 2 UY History",
        "TimeHistory",
        node_scope=[2],
        element_scope=[10],
        settings={
            "node": 2,
            "quantity": "Displacement",
            "dof": 2,
        },
    )
    project.update_solution_result(1, updated)

    restored = ProjectDatabase.from_dict(project.to_dict())
    result = restored.solution_results[1]

    assert result.name == "Node 2 UY History"
    assert result.node_scope == [2]
    assert result.element_scope == [10]
    assert result.settings == {
        "node": 2,
        "quantity": "Displacement",
        "dof": 2,
    }


def test_project_rejects_restrained_displacement_control_dof_on_add():
    project = build_project()
    project.model.set_fixity(2, (1, 0, 0, 0, 0, 0))
    analysis = AnalysisSettingsData(
        20,
        "Restrained push",
        "Pushover",
        control_node=2,
        control_dof=1,
        displacement_increment=0.001,
    )

    try:
        project.add_analysis(analysis)
    except ValueError as exc:
        assert "control node 2 DOF 1 is restrained by a support" in str(exc)
    else:
        raise AssertionError("Expected restrained control DOF validation")


def test_project_rejects_restrained_displacement_control_dof_on_update():
    project = build_project()
    project.add_analysis(
        AnalysisSettingsData(
            21,
            "Initial push",
            "Pushover",
            control_node=2,
            control_dof=2,
            displacement_increment=0.001,
        )
    )
    project.model.set_fixity(2, (1, 0, 0, 0, 0, 0))

    try:
        project.update_analysis(
            21,
            AnalysisSettingsData(
                21,
                "Updated push",
                "Pushover",
                control_node=2,
                control_dof=1,
                displacement_increment=0.001,
            ),
        )
    except ValueError as exc:
        assert "control node 2 DOF 1 is restrained by a support" in str(exc)
    else:
        raise AssertionError("Expected restrained control DOF validation")


def _add_plain_prescribed_fixture(project: ProjectDatabase) -> None:
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Plain", "Plain", time_series_tag=1)
    )


def test_project_rejects_analysis_when_active_prescribed_displacement_owns_control_dof():
    project = build_project()
    _add_plain_prescribed_fixture(project)
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            1,
            "Imposed UX",
            1,
            2,
            1,
            0.001,
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                22,
                "Conflicting push",
                "Pushover",
                control_node=2,
                control_dof=1,
                displacement_increment=0.001,
            )
        )
    except ValueError as exc:
        assert "conflicts with active Prescribed Displacement" in str(exc)
    else:
        raise AssertionError(
            "Expected prescribed displacement/control DOF conflict"
        )


def test_project_rejects_prescribed_displacement_when_control_analysis_exists():
    project = build_project()
    _add_plain_prescribed_fixture(project)
    project.add_analysis(
        AnalysisSettingsData(
            23,
            "Push",
            "Pushover",
            control_node=2,
            control_dof=1,
            displacement_increment=0.001,
        )
    )

    try:
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                2,
                "Imposed UX",
                1,
                2,
                1,
                0.001,
            )
        )
    except ValueError as exc:
        assert "conflicts with active Pushover analysis 23" in str(exc)
    else:
        raise AssertionError(
            "Expected prescribed displacement/control analysis conflict"
        )


def test_project_rejects_analysis_using_equal_dof_dependent_control_dof():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_constraint(
        ConstraintData(
            30,
            "Tie node 2",
            "equalDOF",
            retained_node=3,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                30,
                "Conflicting push",
                "Pushover",
                control_node=2,
                control_dof=1,
                displacement_increment=0.001,
            )
        )
    except ValueError as exc:
        assert "constrained/dependent DOF in equalDOF constraint" in str(exc)
    else:
        raise AssertionError("Expected equalDOF/control analysis conflict")


def test_project_rejects_equal_dof_added_after_control_analysis():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_analysis(
        AnalysisSettingsData(
            31,
            "Push",
            "Pushover",
            control_node=2,
            control_dof=1,
            displacement_increment=0.001,
        )
    )

    try:
        project.add_constraint(
            ConstraintData(
                31,
                "Tie controlled DOF",
                "equalDOF",
                retained_node=3,
                constrained_nodes=[2],
                dofs=(1,),
            )
        )
    except ValueError as exc:
        assert "makes a DisplacementControl DOF dependent" in str(exc)
    else:
        raise AssertionError("Expected analysis/equalDOF conflict")


def test_project_allows_retained_equal_dof_node_as_control():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_constraint(
        ConstraintData(
            32,
            "Tie node 2",
            "equalDOF",
            retained_node=3,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    project.add_analysis(
        AnalysisSettingsData(
            32,
            "Push master",
            "Pushover",
            control_node=3,
            control_dof=1,
            displacement_increment=0.001,
        )
    )

    assert project.analyses[32].control_node == 3


def test_project_rejects_analysis_using_rigid_link_bar_dependent_translation():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_constraint(
        ConstraintData(
            33,
            "Rigid bar",
            "rigidLink",
            retained_node=3,
            constrained_nodes=[2],
            link_type="bar",
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                33,
                "Push constrained UX",
                "Pushover",
                control_node=2,
                control_dof=1,
                displacement_increment=0.001,
            )
        )
    except ValueError as exc:
        assert "constrained/dependent DOF in rigidLink constraint" in str(exc)
    else:
        raise AssertionError("Expected rigidLink/control analysis conflict")


def test_project_allows_rigid_link_bar_rotation_as_control():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_constraint(
        ConstraintData(
            34,
            "Rigid bar",
            "rigidLink",
            retained_node=3,
            constrained_nodes=[2],
            link_type="bar",
        )
    )

    project.add_analysis(
        AnalysisSettingsData(
            34,
            "Push constrained RZ",
            "Pushover",
            control_node=2,
            control_dof=6,
            displacement_increment=0.001,
        )
    )

    assert project.analyses[34].control_dof == 6


def test_project_rejects_rigid_link_beam_added_after_rotation_control_analysis():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_analysis(
        AnalysisSettingsData(
            35,
            "Push RZ",
            "Pushover",
            control_node=2,
            control_dof=3,
            displacement_increment=0.001,
        )
    )

    try:
        project.add_constraint(
            ConstraintData(
                35,
                "Rigid beam",
                "rigidLink",
                retained_node=3,
                constrained_nodes=[2],
                link_type="beam",
            )
        )
    except ValueError as exc:
        assert "makes a DisplacementControl DOF dependent" in str(exc)
    else:
        raise AssertionError("Expected analysis/rigidLink conflict")


def test_project_rejects_analysis_using_rigid_diaphragm_dependent_dof():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_constraint(
        ConstraintData(
            36,
            "XY diaphragm",
            "rigidDiaphragm",
            retained_node=3,
            constrained_nodes=[2],
            perp_dirn=3,
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                36,
                "Push constrained UX",
                "Pushover",
                control_node=2,
                control_dof=1,
                displacement_increment=0.001,
            )
        )
    except ValueError as exc:
        assert "constrained/dependent DOF in rigidDiaphragm" in str(exc)
    else:
        raise AssertionError(
            "Expected rigidDiaphragm/control analysis conflict"
        )


def test_project_rejects_rigid_diaphragm_added_after_control_analysis():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_analysis(
        AnalysisSettingsData(
            37,
            "Push UX",
            "Pushover",
            control_node=2,
            control_dof=1,
            displacement_increment=0.001,
        )
    )

    try:
        project.add_constraint(
            ConstraintData(
                37,
                "XY diaphragm",
                "rigidDiaphragm",
                retained_node=3,
                constrained_nodes=[2],
                perp_dirn=3,
            )
        )
    except ValueError as exc:
        assert "makes a DisplacementControl DOF dependent" in str(exc)
    else:
        raise AssertionError(
            "Expected analysis/rigidDiaphragm conflict"
        )


def test_project_allows_rigid_diaphragm_retained_node_as_control():
    project = build_project()
    project.model.add_node(3, 10.0, 0.0, 0.0)
    project.add_constraint(
        ConstraintData(
            38,
            "XY diaphragm",
            "rigidDiaphragm",
            retained_node=3,
            constrained_nodes=[2],
            perp_dirn=3,
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            38,
            "Push master UX",
            "Pushover",
            control_node=3,
            control_dof=1,
            displacement_increment=0.001,
        )
    )

    assert project.analyses[38].control_node == 3


def test_project_rejects_rigid_diaphragm_on_unsupported_model_signature():
    model = StructuralModel("2D-2DOF", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Bad diaphragm", model=model)

    try:
        project.add_constraint(
            ConstraintData(
                39,
                "Unsupported diaphragm",
                "rigidDiaphragm",
                retained_node=1,
                constrained_nodes=[2],
                perp_dirn=3,
            )
        )
    except ValueError as exc:
        assert "requires a 2D/3DOF or 3D/6DOF model" in str(exc)
    else:
        raise AssertionError(
            "Expected rigidDiaphragm model signature validation"
        )


def test_project_accepts_rigid_diaphragm_on_supported_2d_3dof_model():
    model = StructuralModel("2D-3DOF", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Good diaphragm", model=model)

    project.add_constraint(
        ConstraintData(
            40,
            "Supported diaphragm",
            "rigidDiaphragm",
            retained_node=1,
            constrained_nodes=[2],
            perp_dirn=3,
        )
    )

    assert project.constraints[40].constraint_type == "rigidDiaphragm"


def test_project_rejects_equal_dof_above_model_ndf():
    model = StructuralModel("2D-3DOF equalDOF", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Bad equalDOF", model=model)

    try:
        project.add_constraint(
            ConstraintData(
                41,
                "Invalid equalDOF",
                "equalDOF",
                retained_node=1,
                constrained_nodes=[2],
                dofs=(1, 5),
            )
        )
    except ValueError as exc:
        assert "DOF(s) 5 not available for model ndf=3" in str(exc)
    else:
        raise AssertionError("Expected equalDOF model-ndf validation")


def test_project_accepts_equal_dof_at_model_ndf():
    model = StructuralModel("2D-3DOF equalDOF", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Good equalDOF", model=model)

    project.add_constraint(
        ConstraintData(
            42,
            "Valid equalDOF",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1, 3),
        )
    )

    assert project.constraints[42].dofs == (1, 3)


def test_project_update_rejects_equal_dof_above_model_ndf():
    model = StructuralModel("2D-3DOF equalDOF update", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Update equalDOF", model=model)
    project.add_constraint(
        ConstraintData(
            43,
            "Initial equalDOF",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    try:
        project.update_constraint(
            43,
            ConstraintData(
                43,
                "Invalid updated equalDOF",
                "equalDOF",
                retained_node=1,
                constrained_nodes=[2],
                dofs=(1, 4),
            ),
        )
    except ValueError as exc:
        assert "DOF(s) 4 not available for model ndf=3" in str(exc)
    else:
        raise AssertionError("Expected equalDOF update model-ndf validation")


def test_project_rejects_rigid_link_bar_when_ndf_below_ndm():
    model = StructuralModel("3D-2DOF rigid bar", ndm=3, ndf=2)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    project = ProjectDatabase(name="Bad rigid bar", model=model)

    try:
        project.add_constraint(
            ConstraintData(
                44,
                "Invalid rigid bar",
                "rigidLink",
                retained_node=1,
                constrained_nodes=[2],
                link_type="bar",
            )
        )
    except ValueError as exc:
        assert "requires ndf >= ndm" in str(exc)
    else:
        raise AssertionError("Expected rigidLink bar signature validation")


def test_project_rejects_unsupported_rigid_link_beam_signature():
    model = StructuralModel("3D-4DOF rigid beam", ndm=3, ndf=4)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    project = ProjectDatabase(name="Bad rigid beam", model=model)

    try:
        project.add_constraint(
            ConstraintData(
                45,
                "Invalid rigid beam",
                "rigidLink",
                retained_node=1,
                constrained_nodes=[2],
                link_type="beam",
            )
        )
    except ValueError as exc:
        assert "requires ndf == ndm, 2D/3DOF, or 3D/6DOF" in str(exc)
    else:
        raise AssertionError("Expected rigidLink beam signature validation")


def test_project_accepts_3d_4dof_rigid_link_bar():
    model = StructuralModel("3D-4DOF rigid bar", ndm=3, ndf=4)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    project = ProjectDatabase(name="Good rigid bar", model=model)

    project.add_constraint(
        ConstraintData(
            46,
            "Valid rigid bar",
            "rigidLink",
            retained_node=1,
            constrained_nodes=[2],
            link_type="bar",
        )
    )

    assert project.constraints[46].link_type == "bar"


def test_project_accepts_3d_6dof_rigid_link_beam():
    model = StructuralModel("3D-6DOF rigid beam", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    project = ProjectDatabase(name="Good rigid beam", model=model)

    project.add_constraint(
        ConstraintData(
            47,
            "Valid rigid beam",
            "rigidLink",
            retained_node=1,
            constrained_nodes=[2],
            link_type="beam",
        )
    )

    assert project.constraints[47].link_type == "beam"


def test_project_rejects_overlapping_mpcs_on_same_dependent_dof():
    model = StructuralModel("project-overlap-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Overlap MPC", model=model)

    project.add_constraint(
        ConstraintData(
            48,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    try:
        project.add_constraint(
            ConstraintData(
                49,
                "Rigid bar",
                "rigidLink",
                retained_node=3,
                constrained_nodes=[2],
                link_type="bar",
            )
        )
    except ValueError as exc:
        assert "overlaps an existing MPC" in str(exc)
        assert "node 2 DOF 1" in str(exc)
    else:
        raise AssertionError("Expected overlapping MPC validation")


def test_project_allows_disjoint_mpcs_on_same_constrained_node():
    model = StructuralModel("project-disjoint-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Disjoint MPC", model=model)

    project.add_constraint(
        ConstraintData(
            50,
            "Tie RZ",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(3,),
        )
    )
    project.add_constraint(
        ConstraintData(
            51,
            "Rigid bar",
            "rigidLink",
            retained_node=3,
            constrained_nodes=[2],
            link_type="bar",
        )
    )

    assert set(project.constraints) == {50, 51}


def test_project_rejects_mpc_dependent_dof_fixed_by_support():
    model = StructuralModel("project-fixed-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(2, (1, 0, 0))
    project = ProjectDatabase(name="Fixed MPC", model=model)

    try:
        project.add_constraint(
            ConstraintData(
                52,
                "Tie fixed UX",
                "equalDOF",
                retained_node=1,
                constrained_nodes=[2],
                dofs=(1,),
            )
        )
    except ValueError as exc:
        assert "already fixed by a support" in str(exc)
        assert "node 2 DOF 1" in str(exc)
    else:
        raise AssertionError("Expected support/MPC conflict validation")


def test_project_update_ignores_original_constraint_when_checking_overlap():
    model = StructuralModel("project-update-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Update MPC", model=model)
    project.add_constraint(
        ConstraintData(
            53,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    project.update_constraint(
        53,
        ConstraintData(
            53,
            "Tie UX UY",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1, 2),
        ),
    )

    assert project.constraints[53].dofs == (1, 2)


def test_project_transformation_analysis_rejects_multiple_mp_objects_same_node():
    model = StructuralModel("project-transformation-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Transformation MP", model=model)
    project.add_constraint(
        ConstraintData(
            54,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_constraint(
        ConstraintData(
            55,
            "Tie RZ",
            "equalDOF",
            retained_node=3,
            constrained_nodes=[2],
            dofs=(3,),
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                54,
                "Transformation static",
                "Static",
                constraints_handler="Transformation",
            )
        )
    except ValueError as exc:
        assert "supports only one MP constraint object" in str(exc)
    else:
        raise AssertionError(
            "Expected Transformation multi-MP node validation"
        )


def test_project_rejects_second_mp_added_after_transformation_analysis():
    model = StructuralModel("project-late-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Late MP", model=model)
    project.add_analysis(
        AnalysisSettingsData(
            55,
            "Transformation static",
            "Static",
            constraints_handler="Transformation",
        )
    )
    project.add_constraint(
        ConstraintData(
            56,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    try:
        project.add_constraint(
            ConstraintData(
                57,
                "Tie RZ",
                "equalDOF",
                retained_node=3,
                constrained_nodes=[2],
                dofs=(3,),
            )
        )
    except ValueError as exc:
        assert "supports only one MP constraint object" in str(exc)
    else:
        raise AssertionError(
            "Expected late Transformation multi-MP validation"
        )


def test_project_plain_analysis_rejects_offset_rigid_link_beam():
    model = StructuralModel("project-plain-rigid-beam", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Plain rigid beam", model=model)
    project.add_constraint(
        ConstraintData(
            58,
            "Offset rigid beam",
            "rigidLink",
            retained_node=1,
            constrained_nodes=[2],
            link_type="beam",
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                56,
                "Plain static",
                "Static",
                constraints_handler="Plain",
            )
        )
    except ValueError as exc:
        assert "would ignore non-identity MP transformation matrix" in str(exc)
    else:
        raise AssertionError("Expected Plain rigid beam validation")


def test_project_plain_analysis_allows_equal_dof():
    model = StructuralModel("project-plain-equal-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Plain equalDOF", model=model)
    project.add_constraint(
        ConstraintData(
            59,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            57,
            "Plain static",
            "Static",
            constraints_handler="Plain",
        )
    )

    assert project.analyses[57].constraints_handler == "Plain"


def test_project_plain_analysis_rejects_existing_active_nonzero_prescribed_displacement():
    model = StructuralModel("project-plain-nonzero-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Plain nonzero SP", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed displacement", "Plain", time_series_tag=1)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            60,
            "Imposed UX",
            1,
            2,
            1,
            0.01,
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                58,
                "Plain static",
                "Static",
                constraints_handler="Plain",
            )
        )
    except ValueError as exc:
        assert "cannot enforce non-zero Prescribed Displacement" in str(exc)
    else:
        raise AssertionError(
            "Expected Plain/non-zero prescribed displacement validation"
        )


def test_project_rejects_nonzero_prescribed_displacement_added_after_plain_analysis():
    model = StructuralModel("project-late-nonzero-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Late nonzero SP", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed displacement", "Plain", time_series_tag=1)
    )
    project.add_analysis(
        AnalysisSettingsData(
            59,
            "Plain static",
            "Static",
            constraints_handler="Plain",
        )
    )

    try:
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                61,
                "Imposed UX",
                1,
                2,
                1,
                0.01,
            )
        )
    except ValueError as exc:
        assert "uses the Plain constraint handler" in str(exc)
    else:
        raise AssertionError(
            "Expected late Plain/non-zero prescribed displacement validation"
        )


def test_project_plain_analysis_allows_zero_prescribed_displacement():
    model = StructuralModel("project-plain-zero-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Plain zero SP", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Zero displacement", "Plain", time_series_tag=1)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            62,
            "Zero UX",
            1,
            2,
            1,
            0.0,
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            60,
            "Plain static",
            "Static",
            constraints_handler="Plain",
        )
    )

    assert project.analyses[60].constraints_handler == "Plain"


def test_project_update_analysis_rejects_switch_to_plain_with_nonzero_sp():
    model = StructuralModel("project-switch-plain-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Switch Plain SP", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed displacement", "Plain", time_series_tag=1)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            63,
            "Imposed UX",
            1,
            2,
            1,
            0.01,
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            61,
            "Transformation static",
            "Static",
            constraints_handler="Transformation",
        )
    )

    try:
        project.update_analysis(
            61,
            AnalysisSettingsData(
                61,
                "Plain static",
                "Static",
                constraints_handler="Plain",
            ),
        )
    except ValueError as exc:
        assert "cannot enforce non-zero Prescribed Displacement" in str(exc)
    else:
        raise AssertionError("Expected Plain handler switch validation")


@pytest.mark.parametrize("handler", ["Transformation", "Plain"])
def test_project_rejects_analysis_with_chained_mp_constraints(handler):
    model = StructuralModel("project-chained-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Chained MPC", model=model)
    project.add_constraint(
        ConstraintData(
            64,
            "Upstream",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_constraint(
        ConstraintData(
            65,
            "Downstream",
            "equalDOF",
            retained_node=2,
            constrained_nodes=[3],
            dofs=(2,),
        )
    )

    try:
        project.add_analysis(
            AnalysisSettingsData(
                62,
                "Static chain",
                "Static",
                constraints_handler=handler,
            )
        )
    except ValueError as exc:
        assert "does not follow chained MP constraints" in str(exc)
        assert "retains node 2" in str(exc)
    else:
        raise AssertionError("Expected chained-MPC handler validation")


@pytest.mark.parametrize("handler", ["Transformation", "Plain"])
def test_project_rejects_constraint_that_creates_chain_after_analysis(handler):
    model = StructuralModel("project-late-chain", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Late chain", model=model)
    project.add_analysis(
        AnalysisSettingsData(
            63,
            "Static",
            "Static",
            constraints_handler=handler,
        )
    )
    project.add_constraint(
        ConstraintData(
            66,
            "Upstream",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    try:
        project.add_constraint(
            ConstraintData(
                67,
                "Downstream",
                "equalDOF",
                retained_node=2,
                constrained_nodes=[3],
                dofs=(2,),
            )
        )
    except ValueError as exc:
        assert "does not follow chained MP constraints" in str(exc)
    else:
        raise AssertionError("Expected late chained-MPC validation")


def test_project_rejects_constraint_when_active_sp_owns_dependent_dof():
    model = StructuralModel("project-sp-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="SP MPC", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed UX", "Plain", time_series_tag=1)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            68,
            "SP UX",
            1,
            2,
            1,
            0.0,
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            64,
            "Static",
            "Static",
            constraints_handler="Transformation",
        )
    )

    with pytest.raises(
        ValueError,
        match=r"active Prescribed Displacement",
    ):
        project.add_constraint(
            ConstraintData(
                68,
                "Tie UX",
                "equalDOF",
                retained_node=1,
                constrained_nodes=[2],
                dofs=(1,),
            )
        )


def test_project_rejects_prescribed_displacement_when_mpc_dependent_dof_active():
    model = StructuralModel("project-mpc-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="MPC SP", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed UX", "Plain", time_series_tag=1)
    )
    project.add_constraint(
        ConstraintData(
            69,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            65,
            "Static",
            "Static",
            constraints_handler="Transformation",
        )
    )

    with pytest.raises(
        ValueError,
        match=r"conflicts with dependent DOF in MPC constraint",
    ):
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                69,
                "SP UX",
                1,
                2,
                1,
                0.0,
            )
        )


def test_project_allows_prescribed_displacement_on_other_dof_with_mpc():
    model = StructuralModel("project-mpc-sp-other-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="MPC SP other DOF", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed UY", "Plain", time_series_tag=1)
    )
    project.add_constraint(
        ConstraintData(
            70,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            66,
            "Static",
            "Static",
            constraints_handler="Transformation",
        )
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            70,
            "SP UY",
            1,
            2,
            2,
            0.0,
        )
    )

    assert project.prescribed_displacements[70].dof == 2


def test_project_rejects_analysis_that_activates_existing_sp_mpc_conflict():
    model = StructuralModel("project-analysis-sp-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Analysis activates SP MPC", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Imposed UX", "Plain", time_series_tag=1)
    )
    project.add_constraint(
        ConstraintData(
            71,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            71,
            "SP UX",
            1,
            2,
            1,
            0.0,
        )
    )

    with pytest.raises(
        ValueError,
        match=r"activates Prescribed Displacement object\(s\) on MPC dependent DOF",
    ):
        project.add_analysis(
            AnalysisSettingsData(
                67,
                "Static",
                "Static",
                constraints_handler="Transformation",
            )
        )


def test_project_allows_same_dof_sp_in_separate_analysis_drivers():
    model = StructuralModel("project-scoped-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Scoped SP", model=model)
    project.add_time_series(TimeSeriesData(1, "One", "Linear"))
    project.add_time_series(TimeSeriesData(2, "Two", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Pattern one", "Plain", time_series_tag=1)
    )
    project.add_load_pattern(
        LoadPatternData(2, "Pattern two", "Plain", time_series_tag=2)
    )
    project.add_analysis(
        AnalysisSettingsData(
            68,
            "Analysis one",
            "Static",
            constraints_handler="Transformation",
            deferred_pattern_tags=[1],
        )
    )
    project.add_analysis(
        AnalysisSettingsData(
            69,
            "Analysis two",
            "Static",
            constraints_handler="Transformation",
            deferred_pattern_tags=[2],
        )
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(72, "SP one", 1, 2, 1, 0.01)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(73, "SP two", 2, 2, 1, 0.02)
    )

    assert set(project.prescribed_displacements) == {72, 73}


def test_project_rejects_duplicate_sp_in_same_pattern_same_dof():
    model = StructuralModel("project-same-pattern-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Same pattern SP", model=model)
    project.add_time_series(TimeSeriesData(1, "One", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Pattern one", "Plain", time_series_tag=1)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(74, "SP one", 1, 2, 1, 0.01)
    )

    with pytest.raises(
        ValueError,
        match=r"already has a prescribed displacement in load pattern 1",
    ):
        project.add_prescribed_displacement(
            PrescribedDisplacementData(75, "SP two", 1, 2, 1, 0.02)
        )


def test_project_rejects_analysis_activating_two_same_dof_sp_patterns():
    model = StructuralModel("project-active-duplicate-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Active duplicate SP", model=model)
    project.add_time_series(TimeSeriesData(1, "One", "Linear"))
    project.add_time_series(TimeSeriesData(2, "Two", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Pattern one", "Plain", time_series_tag=1)
    )
    project.add_load_pattern(
        LoadPatternData(2, "Pattern two", "Plain", time_series_tag=2)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(76, "SP one", 1, 2, 1, 0.01)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(77, "SP two", 2, 2, 1, 0.02)
    )

    with pytest.raises(
        ValueError,
        match=r"activates multiple Prescribed Displacement objects on the same DOF",
    ):
        project.add_analysis(
            AnalysisSettingsData(
                70,
                "All patterns static",
                "Static",
                constraints_handler="Transformation",
            )
        )


def test_project_load_pattern_tag_rename_cascades_to_analysis_driver():
    model = StructuralModel("pattern-rename", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Pattern rename", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Driver", "Plain", time_series_tag=1)
    )
    project.add_analysis(
        AnalysisSettingsData(
            71,
            "Pushover",
            "Pushover",
            control_node=1,
            control_dof=1,
            deferred_pattern_tags=[1],
        )
    )

    project.update_load_pattern(
        1,
        LoadPatternData(5, "Driver renamed", "Plain", time_series_tag=1),
    )

    assert project.analyses[71].deferred_pattern_tags == [5]


def test_project_rejects_removing_pattern_used_by_analysis_driver():
    model = StructuralModel("pattern-remove-driver", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Pattern remove", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Driver", "Plain", time_series_tag=1)
    )
    project.add_analysis(
        AnalysisSettingsData(
            72,
            "Transient",
            "Transient",
            deferred_pattern_tags=[1],
        )
    )

    with pytest.raises(
        ValueError,
        match=r"used as a driving/excitation pattern",
    ):
        project.remove_load_pattern(1)

    assert 1 in project.load_patterns


def test_project_allows_staged_analysis_with_future_driver_pattern():
    model = StructuralModel("missing-driver", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Missing driver", model=model)

    project.add_analysis(
        AnalysisSettingsData(
            73,
            "Transient",
            "Transient",
            deferred_pattern_tags=[99],
        )
    )

    assert project.analyses[73].deferred_pattern_tags == [99]


def test_project_ignores_stale_modal_deferred_pattern_reference():
    model = StructuralModel("modal-stale-driver", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Modal stale", model=model)

    project.add_analysis(
        AnalysisSettingsData(
            74,
            "Modal",
            "Modal",
            deferred_pattern_tags=[99],
        )
    )

    assert project.analyses[74].deferred_pattern_tags == [99]


def test_project_removing_pattern_cleans_inactive_stale_analysis_reference():
    model = StructuralModel("cleanup-stale-driver", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Cleanup stale", model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Background", "Plain", time_series_tag=1)
    )
    project.add_analysis(
        AnalysisSettingsData(
            75,
            "Modal",
            "Modal",
            deferred_pattern_tags=[1],
        )
    )

    project.remove_load_pattern(1)

    assert project.analyses[75].deferred_pattern_tags == []


def test_project_material_tag_rename_cascades_all_references():
    model = StructuralModel("material-rename", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="truss",
        truss_area=0.01,
        truss_material_tag=1,
    )
    project = ProjectDatabase(name="Material rename", model=model)
    project.add_material(
        MaterialData(1, "Base", "Elastic", {"E": 200000.0})
    )
    project.add_material(
        MaterialData(
            2,
            "Wrapper",
            "MinMax",
            {},
            base_material_tag=1,
        )
    )
    project.add_section(
        SectionData(
            1,
            "Elastic section",
            "Elastic",
            material_tag=1,
        )
    )
    project.add_section(
        SectionData(
            2,
            "Fiber section",
            "Fiber",
            fibers=[FiberData(0.0, 0.0, 0.01, 1)],
            fiber_components=[
                FiberComponentData("SingleFiber", "Extra", 1)
            ],
        )
    )
    project.add_connection(
        ConnectionData(
            10,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )

    project.update_material(
        1,
        MaterialData(5, "Base renamed", "Elastic", {"E": 200000.0}),
    )

    assert project.materials[2].base_material_tag == 5
    assert project.sections[1].material_tag == 5
    assert project.sections[2].fibers[0].material_tag == 5
    assert project.sections[2].fiber_components[0].material_tag == 5
    assert project.model.elements[1].truss_material_tag == 5
    assert project.connections[10].materials_by_dof[1] == 5


def test_project_rejects_removing_referenced_material():
    model = StructuralModel("material-delete", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(name="Material delete", model=model)
    project.add_material(
        MaterialData(1, "Steel", "Elastic", {"E": 200000.0})
    )
    project.add_section(
        SectionData(1, "Elastic", "Elastic", material_tag=1)
    )

    with pytest.raises(
        ValueError,
        match=r"Material 1 is still referenced by sections 1",
    ):
        project.remove_material(1)

    assert 1 in project.materials


def test_project_section_tag_rename_cascades_element_and_connection():
    model = StructuralModel("section-rename", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
        hinge_i_section_tag=1,
        hinge_j_section_tag=1,
        interior_section_tag=1,
        integration_type="HingeRadau",
    )
    project = ProjectDatabase(name="Section rename", model=model)
    project.add_section(SectionData(1, "Fiber", "Fiber"))
    project.connections[10] = ConnectionData(
        10,
        "Section spring",
        "zeroLengthSection",
        2,
        3,
        section_tag=1,
    )

    project.update_section(1, SectionData(5, "Fiber renamed", "Fiber"))

    element = project.model.elements[1]
    assert element.section_tag == 5
    assert element.hinge_i_section_tag == 5
    assert element.hinge_j_section_tag == 5
    assert element.interior_section_tag == 5
    assert project.connections[10].section_tag == 5


def test_project_rejects_removing_section_used_by_element():
    model = StructuralModel("section-delete", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    project = ProjectDatabase(name="Section delete", model=model)
    project.add_section(SectionData(1, "Elastic", "Elastic"))

    with pytest.raises(
        ValueError,
        match=r"Section 1 is still referenced by elements 1",
    ):
        project.remove_section(1)

    assert 1 in project.sections


def test_project_allows_staged_fiber_recorder_material_reference():
    model = StructuralModel("fiber-recorder-material", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    project = ProjectDatabase(name="Fiber recorder", model=model)

    project.add_recorder(
        RecorderData(
            1,
            "Fiber",
            "Fiber",
            target_tags=[1],
            response="stressStrain",
            section_number=1,
            material_tag=99,
        )
    )

    assert project.recorders[1].material_tag == 99


def test_project_transformation_tag_rename_cascades_to_frame_elements():
    model = StructuralModel("transformation-rename", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    project = ProjectDatabase(name="Transformation rename", model=model)
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )

    project.update_transformation(
        1,
        TransformationData(5, "Linear renamed", "Linear"),
    )

    assert 1 not in project.transformations
    assert 5 in project.transformations
    assert project.model.elements[1].transf_tag == 5


def test_project_rejects_removing_transformation_used_by_element():
    model = StructuralModel("transformation-delete", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    project = ProjectDatabase(name="Transformation delete", model=model)
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )

    with pytest.raises(
        ValueError,
        match=r"Transformation 1 is still referenced by element\(s\): 1",
    ):
        project.remove_transformation(1)

    assert 1 in project.transformations


def test_project_delete_entities_cascades_node_dependencies():
    model = StructuralModel("delete-node-cascade", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 1.0, 0.0)
    model.add_element(
        10,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    project = ProjectDatabase(name="Delete node cascade", model=model)
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            20,
            "Link",
            "zeroLength",
            2,
            3,
            materials_by_dof={1: 1},
        )
    )
    project.add_constraint(
        ConstraintData(
            30,
            "Tie",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Plain", "Plain", time_series_tag=1)
    )
    project.add_nodal_load(
        NodalLoadData(
            40,
            "Node load",
            1,
            2,
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            41,
            "SP",
            1,
            2,
            2,
            0.0,
        )
    )
    project.add_element_load(
        ElementLoadData(
            42,
            "Beam load",
            1,
            10,
            load_type="Uniform",
            wy=-1.0,
        )
    )
    project.add_recorder(
        RecorderData(
            50,
            "Node recorder",
            "Node",
            target_tags=[2],
            response="disp",
            dofs=[1],
        )
    )
    project.add_recorder(
        RecorderData(
            51,
            "Element recorder",
            "Element",
            target_tags=[10],
            response="globalForce",
        )
    )
    project.selection_sets["Delete"] = SelectionSetData(
        "Delete",
        node_tags={2},
        element_tags={10},
    )

    project.delete_entities(node_tags=[2], cascade_nodes=True)

    assert 2 not in project.model.nodes
    assert 10 not in project.model.elements
    assert 20 not in project.connections
    assert 30 not in project.constraints
    assert 40 not in project.nodal_loads
    assert 41 not in project.prescribed_displacements
    assert 42 not in project.element_loads
    assert 50 not in project.recorders
    assert 51 not in project.recorders
    assert project.selection_sets["Delete"].node_tags == set()
    assert project.selection_sets["Delete"].element_tags == set()


def test_project_delete_entities_rejects_analysis_control_node():
    model = StructuralModel("delete-control-node", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Control node delete", model=model)
    project.add_analysis(
        AnalysisSettingsData(
            76,
            "Pushover",
            "Pushover",
            control_node=2,
            control_dof=1,
        )
    )

    with pytest.raises(
        ValueError,
        match=r"Cannot delete control node\(s\) used by analysis tag\(s\): 76",
    ):
        project.delete_entities(node_tags=[2], cascade_nodes=True)

    assert 2 in project.model.nodes


def test_project_ground_node_cleanup_preserves_semantically_used_node():
    model = StructuralModel("ground-node-protection", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(name="Ground protection", model=model)
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Plain", "Plain", time_series_tag=1)
    )
    connection = ConnectionData(
        90,
        "Ground spring",
        "zeroLength",
        1,
        2,
        materials_by_dof={1: 1},
        generated_ground_node=2,
    )
    project.add_connection(connection)
    project.add_nodal_load(
        NodalLoadData(
            91,
            "Ground load",
            1,
            2,
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )

    project.remove_connection(90, cleanup_ground=True)

    assert 2 in project.model.nodes
    assert 91 in project.nodal_loads


def test_project_connection_tag_rename_cascades_references():
    model = StructuralModel("connection-rename", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(name="Connection rename", model=model)
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            10,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )
    project.add_recorder(
        RecorderData(
            20,
            "Connection force",
            "Element",
            target_tags=[10],
            response="globalForce",
        )
    )
    project.add_analysis(
        AnalysisSettingsData(30, "Static", "Static")
    )
    project.add_solution_result(
        SolutionResultData(
            40,
            30,
            "Connection result",
            "MemberForce",
            element_scope=[10],
        )
    )

    project.update_connection(
        10,
        ConnectionData(
            15,
            "Spring renamed",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        ),
    )

    assert 10 not in project.connections
    assert 15 in project.connections
    assert project.recorders[20].target_tags == [15]
    assert project.solution_results[40].element_scope == [15]


def test_project_remove_connection_prunes_element_recorder():
    model = StructuralModel("connection-delete-recorder", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(
        name="Connection delete recorder",
        model=model,
    )
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            10,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )
    project.add_recorder(
        RecorderData(
            20,
            "Connection force",
            "Element",
            target_tags=[10],
            response="globalForce",
        )
    )

    project.remove_connection(10)

    assert 10 not in project.connections
    assert 20 not in project.recorders


def test_project_connection_cleanup_preserves_generated_hinge_section():
    model = StructuralModel("connection-generated-section", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    model.add_node(3, 1.0, 0.0)
    model.add_element(
        1,
        1,
        3,
        element_type="forceBeamColumn",
        section_tag=6,
        transf_tag=1,
        hinge_i_section_tag=5,
        hinge_j_section_tag=6,
        interior_section_tag=6,
        integration_type="HingeRadau",
    )
    project = ProjectDatabase(
        name="Generated hinge section",
        model=model,
    )
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_section(SectionData(5, "Generated hinge", "Fiber"))
    project.add_section(SectionData(6, "Member section", "Fiber"))
    project.add_connection(
        ConnectionData(
            10,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
            generated_section_tag=5,
        )
    )

    project.remove_connection(10, cleanup_ground=True)

    assert 10 not in project.connections
    assert 5 in project.sections


def test_project_delete_entities_prunes_solution_result_scope():
    model = StructuralModel("result-scope-delete", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    project = ProjectDatabase(name="Result scope delete", model=model)
    project.add_analysis(
        AnalysisSettingsData(1, "Static", "Static")
    )
    project.add_solution_result(
        SolutionResultData(
            10,
            1,
            "Scoped displacement",
            "NodalDisplacement",
            node_scope=[2, 3],
        )
    )

    project.delete_entities(node_tags=[2], cascade_nodes=True)

    assert project.solution_results[10].node_scope == [3]

    project.delete_entities(node_tags=[3], cascade_nodes=True)

    assert 10 not in project.solution_results


def test_project_remove_connection_drops_fully_scoped_solution_result():
    model = StructuralModel("connection-result-delete", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(name="Connection result delete", model=model)
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            10,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )
    project.add_analysis(
        AnalysisSettingsData(20, "Static", "Static")
    )
    project.add_solution_result(
        SolutionResultData(
            30,
            20,
            "Connection force",
            "MemberForce",
            element_scope=[10],
        )
    )

    project.remove_connection(10)

    assert 30 not in project.solution_results


def test_project_sync_generated_ground_node_after_geometry_edit():
    model = StructuralModel("ground-sync", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(name="Ground sync", model=model)
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            10,
            "Ground spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
            generated_ground_node=2,
        )
    )

    project.model.translate_entities(node_tags=[1], dx=2.5, dy=-1.0)
    updated = project.sync_generated_ground_nodes()

    assert updated == [2]
    assert project.model.nodes[2].xyz == project.model.nodes[1].xyz
    assert project.model.nodes[2].fixity == (1, 1, 1)

    # Managed ground nodes cannot remain detached even if they were moved
    # directly as part of a broad geometry selection.
    project.model.nodes[2].xyz = (99.0, 99.0, 0.0)
    project.sync_generated_ground_nodes()
    assert project.model.nodes[2].xyz == project.model.nodes[1].xyz


def test_project_validate_node_state_rejects_detached_zero_length():
    model = StructuralModel("node-edit-zero-length", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    project = ProjectDatabase(name="Node edit zero length", model=model)
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            10,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )

    project.model.nodes[2].xyz = (0.1, 0.0, 0.0)

    with pytest.raises(
        ValueError,
        match=r"zeroLength connection nodes must be coincident",
    ):
        project.validate_node_state(2)


def test_project_validate_node_state_rejects_support_on_mpc_dependent_dof():
    model = StructuralModel("node-edit-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Node edit MPC", model=model)
    project.add_constraint(
        ConstraintData(
            10,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        )
    )

    project.model.nodes[2].fixity = (1, 0, 0)

    with pytest.raises(
        ValueError,
        match=r"already fixed by a support",
    ):
        project.validate_node_state(2)


def test_project_validate_node_state_rejects_fixed_analysis_control_dof():
    model = StructuralModel("node-edit-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    project = ProjectDatabase(name="Node edit control", model=model)
    project.add_analysis(
        AnalysisSettingsData(
            10,
            "Push",
            "Pushover",
            control_node=2,
            control_dof=1,
            displacement_increment=0.001,
        )
    )

    project.model.nodes[2].fixity = (1, 0, 0)

    with pytest.raises(
        ValueError,
        match=r"control node 2 DOF 1 is restrained by a support",
    ):
        project.validate_node_state(2)


def test_project_validate_element_state_rejects_recorder_after_ip_reduction():
    model = StructuralModel("element-edit-ip", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
        integration_points=5,
    )
    project = ProjectDatabase(name="Element edit IP", model=model)
    project.add_recorder(
        RecorderData(
            10,
            "Section 5",
            "Section",
            target_tags=[1],
            response="force",
            section_number=5,
        )
    )

    project.model.elements[1].integration_points = 2

    with pytest.raises(
        ValueError,
        match=r"Recorder section 5 exceeds the integration-point count",
    ):
        project.validate_element_state(1)


def test_project_validate_element_state_rejects_incompatible_recorder_after_formulation_change():
    model = StructuralModel("element-edit-formulation", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
        integration_points=5,
    )
    project = ProjectDatabase(name="Element edit formulation", model=model)
    project.add_recorder(
        RecorderData(
            10,
            "Section force",
            "Section",
            target_tags=[1],
            response="force",
            section_number=1,
        )
    )

    project.model.elements[1].element_type = "elasticBeamColumn"

    with pytest.raises(
        ValueError,
        match=r"Section/Fiber recorders require forceBeamColumn or dispBeamColumn",
    ):
        project.validate_element_state(1)


def test_project_load_pattern_tag_rename_preserves_driver_order():
    model = StructuralModel("pattern-rename-order", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Pattern rename order", model=model)
    project.add_time_series(TimeSeriesData(1, "One", "Linear"))
    project.add_time_series(TimeSeriesData(2, "Two", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "First", "Plain", time_series_tag=1)
    )
    project.add_load_pattern(
        LoadPatternData(2, "Second", "Plain", time_series_tag=2)
    )
    project.add_analysis(
        AnalysisSettingsData(
            80,
            "Transient",
            "Transient",
            deferred_pattern_tags=[1, 2],
        )
    )

    project.update_load_pattern(
        1,
        LoadPatternData(5, "First renamed", "Plain", time_series_tag=1),
    )

    assert project.analyses[80].deferred_pattern_tags == [5, 2]


def test_project_clear_model_linked_data_preserves_definition_libraries():
    model = StructuralModel("replace-geometry", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    project = ProjectDatabase(name="Replace geometry", model=model)
    project.add_material(
        MaterialData(1, "Elastic", "Elastic", {"E": 1000.0})
    )
    project.add_section(
        SectionData(1, "Elastic section", "Elastic")
    )
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )
    project.selection_sets["Old"] = SelectionSetData(
        "Old", node_tags={1}
    )
    project.add_time_series(TimeSeriesData(1, "Old", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Old", "Plain", time_series_tag=1)
    )
    project.add_nodal_load(
        NodalLoadData(
            1,
            "Old load",
            1,
            1,
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    project.add_analysis(
        AnalysisSettingsData(1, "Old static", "Static")
    )
    project.add_solution_result(
        SolutionResultData(
            1,
            1,
            "Old displacement",
            "NodalDisplacement",
            node_scope=[1],
        )
    )

    project.clear_model_linked_data()

    assert project.selection_sets == {}
    assert project.time_series == {}
    assert project.load_patterns == {}
    assert project.nodal_loads == {}
    assert project.analyses == {}
    assert project.solution_results == {}
    assert project.active_analysis_tag is None

    assert 1 in project.materials
    assert 1 in project.sections
    assert 1 in project.transformations


def test_project_next_element_tag_shares_namespace_with_connections():
    model = StructuralModel("shared-element-tags", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    model.add_node(3, 1.0, 0.0)
    model.add_element(
        1,
        1,
        3,
        element_type="truss",
        truss_area=0.01,
        truss_material_tag=1,
    )
    project = ProjectDatabase(name="Shared tags", model=model)
    project.add_material(
        MaterialData(1, "Elastic", "Elastic", {"E": 1000.0})
    )
    project.add_connection(
        ConnectionData(
            2,
            "Spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )

    assert project.next_element_tag() == 3
    assert project.next_connection_tag() == 3
