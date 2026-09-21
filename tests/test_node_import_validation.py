import math

import pytest

from openseespy_studio.model import Node, StructuralModel


def test_direct_node_rejects_nonfinite_coordinate():
    with pytest.raises(ValueError, match=r"Node coordinates must be finite"):
        Node(1, (math.nan, 0.0, 0.0))


def test_direct_node_rejects_fractional_fixity():
    with pytest.raises(ValueError, match=r"Fixity value must be an integer"):
        Node(
            1,
            (0.0, 0.0, 0.0),
            fixity=(0.5, 0, 0, 0, 0, 0),
        )


def test_direct_node_rejects_nonfinite_mass():
    with pytest.raises(ValueError, match=r"Nodal mass values must be finite"):
        Node(
            1,
            (0.0, 0.0, 0.0),
            mass=(math.inf, 0, 0, 0, 0, 0),
        )


def test_direct_node_rejects_negative_mass():
    with pytest.raises(
        ValueError,
        match=r"Nodal mass values cannot be negative",
    ):
        Node(
            1,
            (0.0, 0.0, 0.0),
            mass=(-1.0, 0, 0, 0, 0, 0),
        )


def test_model_import_rejects_fractional_fixity_without_truncating():
    data = {
        "ndm": 3,
        "ndf": 6,
        "nodes": [
            {
                "tag": 1,
                "xyz": [0.0, 0.0, 0.0],
                "fixity": [0.5, 0, 0, 0, 0, 0],
                "mass": [0, 0, 0, 0, 0, 0],
            }
        ],
    }
    with pytest.raises(ValueError, match=r"Fixity value must be an integer"):
        StructuralModel.from_dict(data)
