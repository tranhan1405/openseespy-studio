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


def test_force_displacement_rejects_boolean_force_node():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "FD",
        "ForceDisplacement",
        settings={"force_node": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting force_node must be an integer",
    ):
        project.add_solution_result(result)


def test_force_displacement_rejects_boolean_displacement_dof():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "FD",
        "ForceDisplacement",
        settings={"displacement_dof": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting displacement_dof must be an integer",
    ):
        project.add_solution_result(result)


def test_force_displacement_rejects_boolean_force_dof():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "FD",
        "ForceDisplacement",
        settings={"force_dof": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting force_dof must be an integer",
    ):
        project.add_solution_result(result)


def test_fiber_result_rejects_boolean_section_setting():
    project = _static_project()
    result = SolutionResultData(
        1,
        1,
        "Fiber",
        "FiberStress",
        settings={"section": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting section must be an integer",
    ):
        project.add_solution_result(result)


def test_modal_result_rejects_boolean_mode_setting():
    project = ProjectDatabase()
    project.analyses[1] = AnalysisSettingsData(
        1,
        "Modes",
        "Modal",
        num_modes=3,
    )
    result = SolutionResultData(
        1,
        1,
        "Mode",
        "ModeShape",
        settings={"mode": True},
    )
    with pytest.raises(
        ValueError,
        match=r"Solution result setting mode must be an integer",
    ):
        project.add_solution_result(result)
