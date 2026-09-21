import pytest

from openseespy_studio.project import (
    ElementLoadData,
    LoadPatternData,
    NodalLoadData,
    PrescribedDisplacementData,
    TimeSeriesData,
)


def test_time_series_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(ValueError, match=r"Time series tag must be an integer"):
        TimeSeriesData(1.5, "Linear", "Linear")

    with pytest.raises(ValueError, match=r"Time series tag must be an integer"):
        TimeSeriesData.from_dict(
            {
                "tag": 1.5,
                "name": "Linear",
                "series_type": "Linear",
            }
        )


def test_load_pattern_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(ValueError, match=r"Load pattern tag must be an integer"):
        LoadPatternData(
            2.5,
            "Pattern",
            "Plain",
            time_series_tag=1,
        )

    with pytest.raises(ValueError, match=r"Load pattern tag must be an integer"):
        LoadPatternData.from_dict(
            {
                "tag": 2.5,
                "name": "Pattern",
                "pattern_type": "Plain",
                "time_series_tag": 1,
            }
        )


def test_nodal_load_rejects_fractional_tag_on_create_and_load():
    values = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    with pytest.raises(ValueError, match=r"Nodal load tag must be an integer"):
        NodalLoadData(
            3.5,
            "Node load",
            pattern_tag=1,
            node_tag=1,
            values=values,
        )

    with pytest.raises(ValueError, match=r"Nodal load tag must be an integer"):
        NodalLoadData.from_dict(
            {
                "tag": 3.5,
                "name": "Node load",
                "pattern_tag": 1,
                "node_tag": 1,
                "values": list(values),
            }
        )


def test_prescribed_displacement_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Prescribed displacement tag must be an integer",
    ):
        PrescribedDisplacementData(
            4.5,
            "SP",
            pattern_tag=1,
            node_tag=1,
            dof=1,
            value=0.001,
        )

    with pytest.raises(
        ValueError,
        match=r"Prescribed displacement tag must be an integer",
    ):
        PrescribedDisplacementData.from_dict(
            {
                "tag": 4.5,
                "name": "SP",
                "pattern_tag": 1,
                "node_tag": 1,
                "dof": 1,
                "value": 0.001,
            }
        )


def test_element_load_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(ValueError, match=r"Element load tag must be an integer"):
        ElementLoadData(
            5.5,
            "Beam load",
            pattern_tag=1,
            element_tag=1,
        )

    with pytest.raises(ValueError, match=r"Element load tag must be an integer"):
        ElementLoadData.from_dict(
            {
                "tag": 5.5,
                "name": "Beam load",
                "pattern_tag": 1,
                "element_tag": 1,
                "load_type": "Uniform",
            }
        )
