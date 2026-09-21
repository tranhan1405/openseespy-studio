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
