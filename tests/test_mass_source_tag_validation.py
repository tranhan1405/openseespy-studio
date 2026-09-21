import pytest

from openseespy_studio.project import MassSourceData


def test_mass_source_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Mass source tag must be an integer",
    ):
        MassSourceData(
            1.5,
            "Mass",
        )

    with pytest.raises(
        ValueError,
        match=r"Mass source tag must be an integer",
    ):
        MassSourceData.from_dict(
            {
                "tag": 1.5,
                "name": "Mass",
            }
        )


def test_mass_source_rejects_fractional_load_pattern_reference():
    with pytest.raises(
        ValueError,
        match=r"Mass source load-pattern tag must be an integer",
    ):
        MassSourceData(
            2,
            "Mass",
            load_factors={1.5: 0.5},
        )

    with pytest.raises(
        ValueError,
        match=r"Mass source load-pattern tag must be an integer",
    ):
        MassSourceData.from_dict(
            {
                "tag": 2,
                "name": "Mass",
                "load_factors": {"1.5": 0.5},
            }
        )


def test_mass_source_rejects_fractional_gravity_axis():
    with pytest.raises(
        ValueError,
        match=r"Mass source gravity axis must be an integer",
    ):
        MassSourceData(
            3,
            "Mass",
            gravity_axis=2.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Mass source gravity axis must be an integer",
    ):
        MassSourceData.from_dict(
            {
                "tag": 3,
                "name": "Mass",
                "gravity_axis": 2.5,
            }
        )


def test_mass_source_rejects_fractional_direction():
    with pytest.raises(
        ValueError,
        match=r"Mass source direction must be an integer",
    ):
        MassSourceData(
            4,
            "Mass",
            directions=(1, 2.5),
        )

    with pytest.raises(
        ValueError,
        match=r"Mass source direction must be an integer",
    ):
        MassSourceData.from_dict(
            {
                "tag": 4,
                "name": "Mass",
                "directions": [1, 2.5],
            }
        )

