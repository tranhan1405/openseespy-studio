from openseespy_studio.model import StructuralModel
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase, SelectionSetData, SolutionResultData


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


def test_force_displacement_solution_result_round_trips():
    project = build_project()
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Cyclic",
            "Cyclic",
            control_node=2,
        )
    )
    project.add_solution_result(
        SolutionResultData(
            2,
            1,
            "Force–Displacement",
            "ForceDisplacement",
            node_scope=[2],
            settings={"force_source": "Base shear"},
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    result = restored.solution_results[2]
    assert result.result_type == "ForceDisplacement"
    assert result.node_scope == [2]
    assert result.settings["force_source"] == "Base shear"
