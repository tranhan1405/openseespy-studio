import pytest

from openseespy_studio.project import (
    ConnectionData,
    ConstraintData,
    ProjectDatabase,
    TimeSeriesData,
)


def test_update_constraint_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = ConstraintData(1, "C", "equalDOF", 1, [2], (1,))
    project.constraints[1] = item
    with pytest.raises(
        ValueError,
        match=r"Constraint original tag must be an integer",
    ):
        project.update_constraint(1.5, item)
    assert project.constraints[1] is item


def test_remove_constraint_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = ConstraintData(1, "C", "equalDOF", 1, [2], (1,))
    project.constraints[1] = item
    with pytest.raises(ValueError, match=r"Constraint tag must be an integer"):
        project.remove_constraint(1.5)
    assert project.constraints[1] is item


def test_update_connection_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = ConnectionData(1, "L", "twoNodeLink", 1, 2, {1: 1})
    project.connections[1] = item
    with pytest.raises(
        ValueError,
        match=r"Connection original tag must be an integer",
    ):
        project.update_connection(1.5, item)
    assert project.connections[1] is item


def test_remove_connection_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = ConnectionData(1, "L", "twoNodeLink", 1, 2, {1: 1})
    project.connections[1] = item
    with pytest.raises(ValueError, match=r"Connection tag must be an integer"):
        project.remove_connection(1.5)
    assert project.connections[1] is item


def test_update_time_series_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = TimeSeriesData(1, "TS", "Linear")
    project.time_series[1] = item
    with pytest.raises(
        ValueError,
        match=r"Time series original tag must be an integer",
    ):
        project.update_time_series(1.5, item)
    assert project.time_series[1] is item
