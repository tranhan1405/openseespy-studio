import pytest

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ConnectionData,
    MassSourceData,
    RecorderData,
)


def test_model_load_parses_false_consistent_mass_string():
    data = StructuralModel(ndm=2, ndf=3).to_dict()
    data["nodes"] = [
        {"tag": 1, "xyz": [0.0, 0.0, 0.0], "fixity": [0, 0, 0], "mass": [0.0, 0.0, 0.0]},
        {"tag": 2, "xyz": [1.0, 0.0, 0.0], "fixity": [0, 0, 0], "mass": [0.0, 0.0, 0.0]},
    ]
    data["elements"] = [
        {
            "tag": 1,
            "i": 1,
            "j": 2,
            "element_type": "elasticBeamColumn",
            "consistent_mass": "false",
        }
    ]

    restored = StructuralModel.from_dict(data)

    assert restored.elements[1].consistent_mass is False


def test_model_load_parses_false_truss_rayleigh_string():
    data = StructuralModel(ndm=2, ndf=3).to_dict()
    data["nodes"] = [
        {"tag": 1, "xyz": [0.0, 0.0, 0.0], "fixity": [0, 0, 0], "mass": [0.0, 0.0, 0.0]},
        {"tag": 2, "xyz": [1.0, 0.0, 0.0], "fixity": [0, 0, 0], "mass": [0.0, 0.0, 0.0]},
    ]
    data["elements"] = [
        {
            "tag": 1,
            "i": 1,
            "j": 2,
            "element_type": "truss",
            "truss_area": 0.01,
            "truss_material_tag": 1,
            "truss_do_rayleigh": "false",
        }
    ]

    restored = StructuralModel.from_dict(data)

    assert restored.elements[1].truss_do_rayleigh is False


def test_connection_load_parses_false_rayleigh_string():
    connection = ConnectionData.from_dict(
        {
            "tag": 1,
            "name": "Spring",
            "connection_type": "zeroLength",
            "node_i": 1,
            "node_j": 2,
            "materials_by_dof": {"1": 1},
            "do_rayleigh": "false",
        }
    )

    assert connection.do_rayleigh is False


def test_mass_source_load_parses_false_self_mass_string():
    source = MassSourceData.from_dict(
        {
            "tag": 1,
            "name": "Mass",
            "include_self_mass": "false",
            "load_factors": {},
            "gravity_axis": 3,
            "directions": [1, 2],
        }
    )

    assert source.include_self_mass is False


def test_recorder_load_parses_false_include_time_string():
    recorder = RecorderData.from_dict(
        {
            "tag": 1,
            "name": "Node Disp",
            "recorder_type": "Node",
            "target_tags": [1],
            "response": "disp",
            "dofs": [1],
            "include_time": "false",
        }
    )

    assert recorder.include_time is False


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: ConnectionData(
                tag=1,
                name="Spring",
                connection_type="zeroLength",
                node_i=1,
                node_j=2,
                materials_by_dof={1: 1},
                do_rayleigh="maybe",
            ),
            "Connection Rayleigh flag must be a boolean",
        ),
        (
            lambda: MassSourceData(
                tag=1,
                name="Mass",
                include_self_mass="maybe",
            ),
            "Mass source include_self_mass must be a boolean",
        ),
        (
            lambda: RecorderData(
                tag=1,
                name="Node Disp",
                recorder_type="Node",
                target_tags=[1],
                include_time="maybe",
            ),
            "Recorder include_time must be a boolean",
        ),
    ],
)
def test_project_boolean_fields_reject_ambiguous_strings(factory, message):
    with pytest.raises(ValueError, match=message):
        factory()
