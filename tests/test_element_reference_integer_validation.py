import pytest

from openseespy_studio.model import Element, StructuralModel


def test_direct_element_rejects_unsupported_type():
    with pytest.raises(ValueError, match=r"Unsupported element type"):
        Element(
            1,
            1,
            2,
            element_type="notAnElement",
        )

    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_element(1, 1, 2)
    with pytest.raises(ValueError, match=r"Unsupported element type"):
        model.assign_element_formulation(
            [1],
            element_type="notAnElement",
        )


def test_frame_element_rejects_fractional_section_reference():
    with pytest.raises(
        ValueError,
        match=r"Element section tag must be an integer",
    ):
        Element(
            2,
            1,
            2,
            element_type="elasticBeamColumn",
            section_tag=1.5,
        )


def test_frame_element_rejects_fractional_transformation_reference():
    with pytest.raises(
        ValueError,
        match=r"Element transformation tag must be an integer",
    ):
        Element(
            3,
            1,
            2,
            element_type="elasticBeamColumn",
            transf_tag=1.5,
        )


def test_hinge_integration_rejects_fractional_i_section_reference():
    with pytest.raises(
        ValueError,
        match=r"Element I-hinge section tag must be an integer",
    ):
        Element(
            4,
            1,
            2,
            element_type="forceBeamColumn",
            integration_type="HingeRadau",
            hinge_i_section_tag=1.5,
            hinge_j_section_tag=2,
            interior_section_tag=3,
        )


def test_hinge_integration_rejects_fractional_j_section_reference():
    with pytest.raises(
        ValueError,
        match=r"Element J-hinge section tag must be an integer",
    ):
        Element(
            5,
            1,
            2,
            element_type="forceBeamColumn",
            integration_type="HingeRadau",
            hinge_i_section_tag=1,
            hinge_j_section_tag=2.5,
            interior_section_tag=3,
        )


def test_hinge_integration_rejects_fractional_interior_section_reference():
    with pytest.raises(
        ValueError,
        match=r"Element interior section tag must be an integer",
    ):
        Element(
            6,
            1,
            2,
            element_type="forceBeamColumn",
            integration_type="HingeRadau",
            hinge_i_section_tag=1,
            hinge_j_section_tag=2,
            interior_section_tag=3.5,
        )


def test_truss_rejects_fractional_material_reference():
    with pytest.raises(
        ValueError,
        match=r"Truss material tag must be an integer",
    ):
        Element(
            7,
            1,
            2,
            element_type="truss",
            truss_material_tag=1.5,
        )
