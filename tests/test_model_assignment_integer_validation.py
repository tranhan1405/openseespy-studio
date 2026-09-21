import pytest

from openseespy_studio.model import StructuralModel


def _model():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 2.0, 0.0, 0.0)
    model.add_element(1, 1, 2)
    model.add_element(
        2,
        2,
        3,
        element_type="truss",
        truss_area=1.0,
    )
    return model


def test_assign_section_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.assign_section([1.5], 2)
    assert model.elements[1].section_tag is None


def test_assign_truss_material_rejects_fractional_material_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        model.assign_truss_material([2], 3.5)
    assert model.elements[2].truss_material_tag is None


def test_assign_truss_material_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.assign_truss_material([2.5], 3)
    assert model.elements[2].truss_material_tag is None


def test_assign_element_formulation_rejects_fractional_element_reference():
    model = _model()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        model.assign_element_formulation(
            [1.5],
            element_type="forceBeamColumn",
        )
    assert model.elements[1].element_type == "elasticBeamColumn"


def test_assign_transformation_rejects_fractional_transformation_reference():
    model = _model()
    with pytest.raises(
        ValueError,
        match=r"Transformation tag must be an integer",
    ):
        model.assign_transformation([1], 4.5)
    assert model.elements[1].transf_tag is None
