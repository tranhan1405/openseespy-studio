import pytest

from openseespy_studio.project import (
    AnalysisSettingsData,
    ProjectDatabase,
    SolutionResultData,
)


def _static_project():
    project = ProjectDatabase()
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.analyses[1] = AnalysisSettingsData(1, "Static", "Static")
    return project


def test_remove_solution_result_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = SolutionResultData(1, 1, "Disp", "NodalDisplacement")
    project.solution_results[1] = item
    with pytest.raises(
        ValueError,
        match=r"Solution result tag must be an integer",
    ):
        project.remove_solution_result(1.5)
    assert project.solution_results[1] is item


def test_solution_results_for_analysis_rejects_fractional_analysis_tag():
    project = ProjectDatabase()
    with pytest.raises(ValueError, match=r"Analysis tag must be an integer"):
        project.solution_results_for_analysis(1.5)


def test_time_history_rejects_boolean_node_setting():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "History",
        "TimeHistory",
        settings={"node": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting node must be an integer",
    ):
        project.add_solution_result(result)


def test_time_history_rejects_boolean_dof_setting():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "History",
        "TimeHistory",
        settings={"node": 1, "dof": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting dof must be an integer",
    ):
        project.add_solution_result(result)


def test_force_displacement_rejects_boolean_displacement_node():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "FD",
        "ForceDisplacement",
        settings={"displacement_node": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting displacement_node must be an integer",
    ):
        project.add_solution_result(result)
