import pytest

from openseespy_studio.model import StructuralModel


def _model():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_element(1, 1, 2)
    return model


def test_set_coordinates_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(
        ValueError,
        match=r"Node tag must be an integer",
    ):
        model.set_coordinates(1.5, 2.0, 0.0, 0.0)


def test_copy_entities_rejects_fractional_copy_count():
    model = _model()
    with pytest.raises(
        ValueError,
        match=r"Copy count must be an integer",
    ):
        model.copy_entities(
            node_tags=[1, 2],
            element_tags=[1],
            dx=1.0,
            copies=1.5,
        )
