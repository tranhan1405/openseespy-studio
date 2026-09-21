import pytest

from openseespy_studio.project import ConnectionData, ConstraintData


def test_rigid_diaphragm_rejects_fractional_perpendicular_direction():
    with pytest.raises(
        ValueError,
        match=r"Rigid diaphragm perpendicular direction must be an integer",
    ):
        ConstraintData(
            20,
            "Diaphragm",
            "rigidDiaphragm",
            retained_node=1,
            constrained_nodes=[2],
            perp_dirn=2.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Rigid diaphragm perpendicular direction must be an integer",
    ):
        ConstraintData.from_dict(
            {
                "tag": 20,
                "name": "Diaphragm",
                "constraint_type": "rigidDiaphragm",
                "retained_node": 1,
                "constrained_nodes": [2],
                "perp_dirn": 2.5,
            }
        )


def test_connection_rejects_fractional_material_dof():
    with pytest.raises(
        ValueError,
        match=r"Connection DOF must be an integer",
    ):
        ConnectionData(
            21,
            "Link",
            "twoNodeLink",
            node_i=1,
            node_j=2,
            materials_by_dof={1.5: 1},
        )

    with pytest.raises(
        ValueError,
        match=r"Connection DOF must be an integer",
    ):
        ConnectionData.from_dict(
            {
                "tag": 21,
                "name": "Link",
                "connection_type": "twoNodeLink",
                "node_i": 1,
                "node_j": 2,
                "materials_by_dof": {"1.5": 1},
            }
        )


def test_connection_rejects_fractional_material_reference():
    with pytest.raises(
        ValueError,
        match=r"Connection material tag must be an integer",
    ):
        ConnectionData(
            22,
            "Link",
            "twoNodeLink",
            node_i=1,
            node_j=2,
            materials_by_dof={1: 2.5},
        )

    with pytest.raises(
        ValueError,
        match=r"Connection material tag must be an integer",
    ):
        ConnectionData.from_dict(
            {
                "tag": 22,
                "name": "Link",
                "connection_type": "twoNodeLink",
                "node_i": 1,
                "node_j": 2,
                "materials_by_dof": {"1": 2.5},
            }
        )


def test_connection_rejects_fractional_generated_ground_node():
    with pytest.raises(
        ValueError,
        match=r"Connection generated ground node must be an integer",
    ):
        ConnectionData(
            23,
            "Ground spring",
            "zeroLength",
            node_i=1,
            node_j=2,
            materials_by_dof={1: 1},
            generated_ground_node=9.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Connection generated ground node must be an integer",
    ):
        ConnectionData.from_dict(
            {
                "tag": 23,
                "name": "Ground spring",
                "connection_type": "zeroLength",
                "node_i": 1,
                "node_j": 2,
                "materials_by_dof": {"1": 1},
                "generated_ground_node": 9.5,
            }
        )


def test_zero_length_section_rejects_fractional_section_reference():
    with pytest.raises(
        ValueError,
        match=r"Connection section tag must be an integer",
    ):
        ConnectionData(
            24,
            "Section spring",
            "zeroLengthSection",
            node_i=1,
            node_j=2,
            section_tag=3.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Connection section tag must be an integer",
    ):
        ConnectionData.from_dict(
            {
                "tag": 24,
                "name": "Section spring",
                "connection_type": "zeroLengthSection",
                "node_i": 1,
                "node_j": 2,
                "section_tag": 3.5,
            }
        )
