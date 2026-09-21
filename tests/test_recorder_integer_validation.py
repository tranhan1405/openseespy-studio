import pytest

from openseespy_studio.project import RecorderData


def test_recorder_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Recorder tag must be an integer",
    ):
        RecorderData(
            1.5,
            "Node displacement",
            "Node",
            target_tags=[1],
            dofs=[1],
        )

    with pytest.raises(
        ValueError,
        match=r"Recorder tag must be an integer",
    ):
        RecorderData.from_dict(
            {
                "tag": 1.5,
                "name": "Node displacement",
                "recorder_type": "Node",
                "target_tags": [1],
                "dofs": [1],
            }
        )


def test_recorder_rejects_fractional_target_tag():
    with pytest.raises(
        ValueError,
        match=r"Recorder target tag must be an integer",
    ):
        RecorderData(
            2,
            "Node displacement",
            "Node",
            target_tags=[1.5],
            dofs=[1],
        )

    with pytest.raises(
        ValueError,
        match=r"Recorder target tag must be an integer",
    ):
        RecorderData.from_dict(
            {
                "tag": 2,
                "name": "Node displacement",
                "recorder_type": "Node",
                "target_tags": [1.5],
                "dofs": [1],
            }
        )


def test_recorder_rejects_fractional_dof():
    with pytest.raises(
        ValueError,
        match=r"Recorder DOF must be an integer",
    ):
        RecorderData(
            3,
            "Node displacement",
            "Node",
            target_tags=[1],
            dofs=[1.5],
        )

    with pytest.raises(
        ValueError,
        match=r"Recorder DOF must be an integer",
    ):
        RecorderData.from_dict(
            {
                "tag": 3,
                "name": "Node displacement",
                "recorder_type": "Node",
                "target_tags": [1],
                "dofs": [1.5],
            }
        )


def test_section_recorder_rejects_fractional_section_number():
    with pytest.raises(
        ValueError,
        match=r"Recorder section number must be an integer",
    ):
        RecorderData(
            4,
            "Section force",
            "Section",
            target_tags=[1],
            response="force",
            section_number=1.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Recorder section number must be an integer",
    ):
        RecorderData.from_dict(
            {
                "tag": 4,
                "name": "Section force",
                "recorder_type": "Section",
                "target_tags": [1],
                "response": "force",
                "section_number": 1.5,
            }
        )


def test_fiber_recorder_rejects_fractional_material_tag():
    with pytest.raises(
        ValueError,
        match=r"Recorder material tag must be an integer",
    ):
        RecorderData(
            5,
            "Fiber stress",
            "Fiber",
            target_tags=[1],
            response="stress",
            section_number=1,
            material_tag=2.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Recorder material tag must be an integer",
    ):
        RecorderData.from_dict(
            {
                "tag": 5,
                "name": "Fiber stress",
                "recorder_type": "Fiber",
                "target_tags": [1],
                "response": "stress",
                "section_number": 1,
                "material_tag": 2.5,
            }
        )

