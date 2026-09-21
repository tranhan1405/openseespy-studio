import pytest

from openseespy_studio.project import (
    AnalysisSettingsData,
    ElementLoadData,
    ProjectDatabase,
    RecorderData,
)


def test_remove_element_load_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = ElementLoadData(1, "E", 1, 1)
    project.element_loads[1] = item
    with pytest.raises(ValueError, match=r"Element load tag must be an integer"):
        project.remove_element_load(1.5)
    assert project.element_loads[1] is item


def test_update_recorder_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = RecorderData(1, "R", "Node", [1], dofs=[1])
    project.recorders[1] = item
    with pytest.raises(
        ValueError,
        match=r"Recorder original tag must be an integer",
    ):
        project.update_recorder(1.5, item)
    assert project.recorders[1] is item


def test_remove_recorder_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = RecorderData(1, "R", "Node", [1], dofs=[1])
    project.recorders[1] = item
    with pytest.raises(ValueError, match=r"Recorder tag must be an integer"):
        project.remove_recorder(1.5)
    assert project.recorders[1] is item


def test_update_analysis_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = AnalysisSettingsData(1, "A", "Static")
    project.analyses[1] = item
    with pytest.raises(
        ValueError,
        match=r"Analysis original tag must be an integer",
    ):
        project.update_analysis(1.5, item)
    assert project.analyses[1] is item


def test_remove_analysis_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = AnalysisSettingsData(1, "A", "Static")
    project.analyses[1] = item
    with pytest.raises(ValueError, match=r"Analysis tag must be an integer"):
        project.remove_analysis(1.5)
    assert project.analyses[1] is item
