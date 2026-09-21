import pytest

from openseespy_studio.project import SolutionResultData


def test_solution_result_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Solution result tag must be an integer",
    ):
        SolutionResultData(
            1.5,
            1,
            "Displacement",
            "NodalDisplacement",
        )

    with pytest.raises(
        ValueError,
        match=r"Solution result tag must be an integer",
    ):
        SolutionResultData.from_dict(
            {
                "tag": 1.5,
                "analysis_tag": 1,
                "name": "Displacement",
                "result_type": "NodalDisplacement",
            }
        )


def test_solution_result_rejects_fractional_analysis_reference():
    with pytest.raises(
        ValueError,
        match=r"Solution result analysis tag must be an integer",
    ):
        SolutionResultData(
            2,
            1.5,
            "Displacement",
            "NodalDisplacement",
        )

    with pytest.raises(
        ValueError,
        match=r"Solution result analysis tag must be an integer",
    ):
        SolutionResultData.from_dict(
            {
                "tag": 2,
                "analysis_tag": 1.5,
                "name": "Displacement",
                "result_type": "NodalDisplacement",
            }
        )


def test_solution_result_rejects_fractional_node_scope_reference():
    with pytest.raises(
        ValueError,
        match=r"Solution result node tag must be an integer",
    ):
        SolutionResultData(
            3,
            1,
            "Displacement",
            "NodalDisplacement",
            node_scope=[1.5],
        )

    with pytest.raises(
        ValueError,
        match=r"Solution result node tag must be an integer",
    ):
        SolutionResultData.from_dict(
            {
                "tag": 3,
                "analysis_tag": 1,
                "name": "Displacement",
                "result_type": "NodalDisplacement",
                "node_scope": [1.5],
            }
        )
