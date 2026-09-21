import pytest

from openseespy_studio.project import (
    LoadPatternData,
    MassSourceData,
    ProjectDatabase,
    TimeSeriesData,
)


def test_remove_time_series_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = TimeSeriesData(1, "TS", "Linear")
    project.time_series[1] = item
    with pytest.raises(ValueError, match=r"Time series tag must be an integer"):
        project.remove_time_series(1.5)
    assert project.time_series[1] is item


def test_update_load_pattern_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = LoadPatternData(1, "P", "Plain", 1)
    project.load_patterns[1] = item
    with pytest.raises(
        ValueError,
        match=r"Load pattern original tag must be an integer",
    ):
        project.update_load_pattern(1.5, item)
    assert project.load_patterns[1] is item


def test_remove_load_pattern_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = LoadPatternData(1, "P", "Plain", 1)
    project.load_patterns[1] = item
    with pytest.raises(ValueError, match=r"Load pattern tag must be an integer"):
        project.remove_load_pattern(1.5)
    assert project.load_patterns[1] is item


def test_update_mass_source_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = MassSourceData(1, "M")
    project.mass_sources[1] = item
    with pytest.raises(
        ValueError,
        match=r"Mass source original tag must be an integer",
    ):
        project.update_mass_source(1.5, item)
    assert project.mass_sources[1] is item


def test_remove_mass_source_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = MassSourceData(1, "M")
    project.mass_sources[1] = item
    with pytest.raises(ValueError, match=r"Mass source tag must be an integer"):
        project.remove_mass_source(1.5)
    assert project.mass_sources[1] is item
