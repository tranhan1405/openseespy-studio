import pytest

from openseespy_studio.project import (
    LoadPatternData,
    PROJECT_FORMAT,
    PROJECT_FORMAT_VERSION,
    ProjectDatabase,
)


def test_recorders_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Recorders must be a list"):
        ProjectDatabase._load_recorders({})


def test_recorders_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Recorder item 0 must be an object"):
        ProjectDatabase._load_recorders([1])


def test_project_import_rejects_nonlist_selection_sets():
    with pytest.raises(ValueError, match=r"Selection sets must be a list"):
        ProjectDatabase.from_dict(
            {
                "format": PROJECT_FORMAT,
                "version": PROJECT_FORMAT_VERSION,
                "selection_sets": {},
            }
        )


def test_project_import_rejects_nonobject_selection_set_item():
    with pytest.raises(
        ValueError,
        match=r"Selection set item 0 must be an object",
    ):
        ProjectDatabase.from_dict(
            {
                "format": PROJECT_FORMAT,
                "version": PROJECT_FORMAT_VERSION,
                "selection_sets": [1],
            }
        )


def test_uniform_excitation_rejects_fractional_direction_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"UniformExcitation direction must be an integer",
    ):
        LoadPatternData(
            1,
            "EQ",
            "UniformExcitation",
            1,
            direction=1.5,
        )

    with pytest.raises(
        ValueError,
        match=r"UniformExcitation direction must be an integer",
    ):
        LoadPatternData.from_dict(
            {
                "tag": 1,
                "name": "EQ",
                "pattern_type": "UniformExcitation",
                "time_series_tag": 1,
                "direction": 1.5,
            }
        )
