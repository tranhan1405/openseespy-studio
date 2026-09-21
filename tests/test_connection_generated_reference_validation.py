import pytest

from openseespy_studio.project import ConnectionData


def _connection(**kwargs):
    return ConnectionData(
        1,
        "Link",
        "twoNodeLink",
        1,
        2,
        {1: 1},
        **kwargs,
    )


def test_connection_rejects_fractional_generated_section_tag():
    with pytest.raises(
        ValueError,
        match=r"Connection generated section tag must be an integer",
    ):
        _connection(generated_section_tag=3.5)


def test_connection_rejects_fractional_generated_constraint_tag():
    with pytest.raises(
        ValueError,
        match=r"Connection generated constraint tag must be an integer",
    ):
        _connection(generated_constraint_tag=4.5)


def test_connection_rejects_nonpositive_generated_ground_node():
    with pytest.raises(
        ValueError,
        match=r"Connection generated ground node must be positive",
    ):
        _connection(generated_ground_node=0)


def test_connection_rejects_nonpositive_generated_section_tag():
    with pytest.raises(
        ValueError,
        match=r"Connection generated section tag must be positive",
    ):
        _connection(generated_section_tag=0)


def test_connection_rejects_nonpositive_generated_constraint_tag():
    with pytest.raises(
        ValueError,
        match=r"Connection generated constraint tag must be positive",
    ):
        _connection(generated_constraint_tag=0)
