import pytest

from openseespy_studio.model import StructuralModel


def _model():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 2.0, 0.0, 0.0)
    model.add_element(1, 1, 2)
    return model


def test_set_mass_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        model.set_mass(1.5, (1.0, 0, 0, 0, 0, 0))
    assert model.nodes[1].mass == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_set_mass_many_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        model.set_mass_many([1.5], (1.0, 0, 0, 0, 0, 0))
    assert model.nodes[1].mass == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_remove_element_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.remove_element(1.5)
    assert 1 in model.elements


def test_remove_node_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        model.remove_node(3.5)
    assert 3 in model.nodes


def test_assign_section_rejects_fractional_section_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Section tag must be an integer"):
        model.assign_section([1], 2.5)
    assert model.elements[1].section_tag is None
