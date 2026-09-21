import pytest

from openseespy_studio.project import (
    ConnectionData,
    ConstraintData,
    MaterialData,
    SectionData,
    TransformationData,
)


def test_material_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        MaterialData(1.5, "Steel", "Elastic")

    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        MaterialData.from_dict(
            {
                "tag": 1.5,
                "name": "Steel",
                "material_type": "Elastic",
            }
        )


def test_section_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(ValueError, match=r"Section tag must be an integer"):
        SectionData(2.5, "Section", "Elastic")

    with pytest.raises(ValueError, match=r"Section tag must be an integer"):
        SectionData.from_dict(
            {
                "tag": 2.5,
                "name": "Section",
                "section_type": "Elastic",
            }
        )


def test_transformation_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Transformation tag must be an integer",
    ):
        TransformationData(3.5, "PDelta", "PDelta")

    with pytest.raises(
        ValueError,
        match=r"Transformation tag must be an integer",
    ):
        TransformationData.from_dict(
            {
                "tag": 3.5,
                "name": "PDelta",
                "transformation_type": "PDelta",
                "vecxz": [0.0, 0.0, 1.0],
            }
        )


def test_constraint_rejects_fractional_tag_on_create_and_load():
    kwargs = {
        "name": "Equal DOF",
        "constraint_type": "equalDOF",
        "retained_node": 1,
        "constrained_nodes": [2],
        "dofs": (1,),
    }
    with pytest.raises(ValueError, match=r"Constraint tag must be an integer"):
        ConstraintData(tag=4.5, **kwargs)

    with pytest.raises(ValueError, match=r"Constraint tag must be an integer"):
        ConstraintData.from_dict({"tag": 4.5, **kwargs})


def test_connection_rejects_fractional_tag_on_create_and_load():
    kwargs = {
        "name": "Spring",
        "connection_type": "zeroLength",
        "node_i": 1,
        "node_j": 2,
        "materials_by_dof": {1: 1},
    }
    with pytest.raises(ValueError, match=r"Connection tag must be an integer"):
        ConnectionData(tag=5.5, **kwargs)

    with pytest.raises(ValueError, match=r"Connection tag must be an integer"):
        ConnectionData.from_dict(
            {
                "tag": 5.5,
                "name": "Spring",
                "connection_type": "zeroLength",
                "node_i": 1,
                "node_j": 2,
                "materials_by_dof": {"1": 1},
            }
        )
