import pytest

from openseespy_studio.project import ConnectionData, ConstraintData


def test_constraint_rejects_fractional_retained_node_reference():
    with pytest.raises(
        ValueError,
        match=r"Constraint retained node must be an integer",
    ):
        ConstraintData(
            1,
            "Equal",
            "equalDOF",
            retained_node=1.5,
            constrained_nodes=[2],
            dofs=(1,),
        )

    with pytest.raises(
        ValueError,
        match=r"Constraint retained node must be an integer",
    ):
        ConstraintData.from_dict(
            {
                "tag": 1,
                "name": "Equal",
                "constraint_type": "equalDOF",
                "retained_node": 1.5,
                "constrained_nodes": [2],
                "dofs": [1],
            }
        )


def test_constraint_rejects_fractional_constrained_node_reference():
    with pytest.raises(
        ValueError,
        match=r"Constraint constrained node must be an integer",
    ):
        ConstraintData(
            2,
            "Equal",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2.5],
            dofs=(1,),
        )

    with pytest.raises(
        ValueError,
        match=r"Constraint constrained node must be an integer",
    ):
        ConstraintData.from_dict(
            {
                "tag": 2,
                "name": "Equal",
                "constraint_type": "equalDOF",
                "retained_node": 1,
                "constrained_nodes": [2.5],
                "dofs": [1],
            }
        )


def test_equal_dof_constraint_rejects_fractional_dof():
    with pytest.raises(
        ValueError,
        match=r"Constraint DOF must be an integer",
    ):
        ConstraintData(
            3,
            "Equal",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1.5,),
        )

    with pytest.raises(
        ValueError,
        match=r"Constraint DOF must be an integer",
    ):
        ConstraintData.from_dict(
            {
                "tag": 3,
                "name": "Equal",
                "constraint_type": "equalDOF",
                "retained_node": 1,
                "constrained_nodes": [2],
                "dofs": [1.5],
            }
        )


def test_connection_rejects_fractional_node_i_reference():
    with pytest.raises(
        ValueError,
        match=r"Connection node i must be an integer",
    ):
        ConnectionData(
            4,
            "Link",
            "twoNodeLink",
            node_i=1.5,
            node_j=2,
            materials_by_dof={1: 1},
        )

    with pytest.raises(
        ValueError,
        match=r"Connection node i must be an integer",
    ):
        ConnectionData.from_dict(
            {
                "tag": 4,
                "name": "Link",
                "connection_type": "twoNodeLink",
                "node_i": 1.5,
                "node_j": 2,
                "materials_by_dof": {"1": 1},
            }
        )


def test_connection_rejects_fractional_node_j_reference():
    with pytest.raises(
        ValueError,
        match=r"Connection node j must be an integer",
    ):
        ConnectionData(
            5,
            "Link",
            "twoNodeLink",
            node_i=1,
            node_j=2.5,
            materials_by_dof={1: 1},
        )

    with pytest.raises(
        ValueError,
        match=r"Connection node j must be an integer",
    ):
        ConnectionData.from_dict(
            {
                "tag": 5,
                "name": "Link",
                "connection_type": "twoNodeLink",
                "node_i": 1,
                "node_j": 2.5,
                "materials_by_dof": {"1": 1},
            }
        )
