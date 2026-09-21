from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    ConstraintData,
    LoadPatternData,
    PrescribedDisplacementData,
    ProjectDatabase,
    SelectionSetData,
    SolutionResultData,
    TimeSeriesData,
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
            control_dof=3,
            displacement_increment=0.001,
        )
    )

    assert project.analyses[34].control_dof == 3


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
