import pytest

from openseespy_studio.model import StructuralModel


def _model():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_element(1, 1, 2)
    return model


def test_assign_transformation_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.assign_transformation([1.5], 4)
    assert model.elements[1].transf_tag is None


def test_entity_node_tags_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        model.entity_node_tags(node_tags=[1.5])


def test_entity_node_tags_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.entity_node_tags(element_tags=[1.5])


def test_copy_entities_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.copy_entities(
            element_tags=[1.5],
            dx=1.0,
        )
    assert len(model.elements) == 1


def test_copy_entities_rejects_fractional_reserved_element_reference():
    model = _model()
    with pytest.raises(
        ValueError,
        match=r"Reserved element tag must be an integer",
    ):
        model.copy_entities(
            element_tags=[1],
            dx=1.0,
            reserved_element_tags=[5.5],
        )
    assert len(model.elements) == 1
