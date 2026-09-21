import pytest

from openseespy_studio.project import (
    AnalysisSettingsData,
    ProjectDatabase,
    SolutionResultData,
)


def _project_with_element():
    project = ProjectDatabase()
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0, 0.0)
    project.model.add_element(1, 1, 2)
    return project


def test_assign_transformation_to_elements_rejects_fractional_reference():
    project = _project_with_element()
    with pytest.raises(
        ValueError,
        match=r"Transformation tag must be an integer",
    ):
        project.assign_transformation_to_elements([1], 2.5)
    assert project.model.elements[1].transf_tag is None


def test_delete_entities_rejects_fractional_node_reference():
    project = _project_with_element()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        project.delete_entities(node_tags=[1.5])
    assert 1 in project.model.nodes


def test_delete_entities_rejects_fractional_element_reference():
    project = _project_with_element()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        project.delete_entities(element_tags=[1.5])
    assert 1 in project.model.elements


def test_set_active_analysis_rejects_fractional_reference():
    project = ProjectDatabase()
    project.analyses[1] = AnalysisSettingsData(1, "A", "Static")
    with pytest.raises(ValueError, match=r"Analysis tag must be an integer"):
        project.set_active_analysis(1.5)
    assert project.active_analysis_tag is None


def test_update_solution_result_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = SolutionResultData(
        1,
        1,
        "Disp",
        "NodalDisplacement",
    )
    project.solution_results[1] = item
    with pytest.raises(
        ValueError,
        match=r"Solution result original tag must be an integer",
    ):
        project.update_solution_result(1.5, item)
    assert project.solution_results[1] is item
