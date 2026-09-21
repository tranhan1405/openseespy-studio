import pytest

from openseespy_studio.model import StructuralModel, classify_fixity


def _model():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_element(1, 1, 2)
    return model


def test_classify_fixity_rejects_fractional_value():
    with pytest.raises(ValueError, match=r"Fixity value must be an integer"):
        classify_fixity((0.5, 0, 0, 0, 0, 0))


def test_set_fixity_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        model.set_fixity(1.5, (1, 0, 0, 0, 0, 0))
    assert model.nodes[1].fixity == (0, 0, 0, 0, 0, 0)


def test_set_fixity_rejects_fractional_fixity_value():
    model = _model()
    with pytest.raises(ValueError, match=r"Fixity value must be an integer"):
        model.set_fixity(1, (0.5, 0, 0, 0, 0, 0))
    assert model.nodes[1].fixity == (0, 0, 0, 0, 0, 0)


def test_set_fixity_many_rejects_fractional_node_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        model.set_fixity_many([1.5], (1, 0, 0, 0, 0, 0))
    assert model.nodes[1].fixity == (0, 0, 0, 0, 0, 0)


def test_set_fixity_many_rejects_fractional_fixity_value():
    model = _model()
    with pytest.raises(ValueError, match=r"Fixity value must be an integer"):
        model.set_fixity_many([1], (0.5, 0, 0, 0, 0, 0))
    assert model.nodes[1].fixity == (0, 0, 0, 0, 0, 0)
