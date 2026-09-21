import pytest

from math import isclose

from openseespy_studio.model import StructuralModel


def make_line_model() -> StructuralModel:
    model = StructuralModel("GeometryOps")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_element(1, 1, 2, group="beam-x")
    return model


def test_translate_selected_element_moves_its_nodes():
    model = make_line_model()

    moved = model.translate_entities(element_tags={1}, dx=1.0, dy=2.0, dz=3.0)

    assert moved == {1, 2}
    assert model.nodes[1].xyz == (1.0, 2.0, 3.0)
    assert model.nodes[2].xyz == (3.0, 2.0, 3.0)


def test_copy_element_duplicates_connectivity_and_offset():
    model = make_line_model()

    new_nodes, new_elements = model.copy_entities(
        element_tags={1},
        dx=0.0,
        dy=5.0,
        dz=0.0,
        copies=2,
    )

    assert new_nodes == {3, 4, 5, 6}
    assert new_elements == {2, 3}
    assert model.elements[2].i == 3
    assert model.elements[2].j == 4
    assert model.nodes[3].xyz == (0.0, 5.0, 0.0)
    assert model.nodes[5].xyz == (0.0, 10.0, 0.0)


def test_rotate_about_z_axis():
    model = make_line_model()

    model.rotate_entities(element_tags={1}, axis="z", angle_deg=90.0)

    x, y, z = model.nodes[2].xyz
    assert isclose(x, 0.0, abs_tol=1.0e-12)
    assert isclose(y, 2.0, abs_tol=1.0e-12)
    assert isclose(z, 0.0, abs_tol=1.0e-12)


def test_mirror_about_yz_plane():
    model = make_line_model()

    model.mirror_entities(element_tags={1}, normal_axis="x", coordinate=1.0)

    assert model.nodes[1].xyz == (2.0, 0.0, 0.0)
    assert model.nodes[2].xyz == (0.0, 0.0, 0.0)


def test_copy_element_skips_reserved_connection_tags():
    model = make_line_model()

    new_nodes, new_elements = model.copy_entities(
        element_tags={1},
        dx=0.0,
        dy=5.0,
        dz=0.0,
        copies=2,
        reserved_element_tags={2, 4},
    )

    assert new_elements == {3, 5}
    assert model.elements[3].i == 3
    assert model.elements[3].j == 4
    assert model.elements[5].i == 5
    assert model.elements[5].j == 6


def test_translate_rejects_nonfinite_offsets_without_mutating_model():
    model = make_line_model()
    before = model.nodes[1].xyz, model.nodes[2].xyz

    with pytest.raises(ValueError, match=r"Translation offsets must be finite"):
        model.translate_entities(
            element_tags={1},
            dx=float("nan"),
        )

    assert (model.nodes[1].xyz, model.nodes[2].xyz) == before


def test_rotate_rejects_nonfinite_angle_or_pivot_without_mutating_model():
    model = make_line_model()
    before = model.nodes[1].xyz, model.nodes[2].xyz

    with pytest.raises(
        ValueError,
        match=r"Rotation angle and pivot must be finite",
    ):
        model.rotate_entities(
            element_tags={1},
            axis="z",
            angle_deg=float("nan"),
        )

    assert (model.nodes[1].xyz, model.nodes[2].xyz) == before

    with pytest.raises(
        ValueError,
        match=r"Rotation angle and pivot must be finite",
    ):
        model.rotate_entities(
            element_tags={1},
            axis="z",
            angle_deg=10.0,
            pivot=(0.0, float("inf"), 0.0),
        )

    assert (model.nodes[1].xyz, model.nodes[2].xyz) == before


def test_mirror_rejects_nonfinite_coordinate_without_mutating_model():
    model = make_line_model()
    before = model.nodes[1].xyz, model.nodes[2].xyz

    with pytest.raises(ValueError, match=r"Mirror coordinate must be finite"):
        model.mirror_entities(
            element_tags={1},
            normal_axis="x",
            coordinate=float("inf"),
        )

    assert (model.nodes[1].xyz, model.nodes[2].xyz) == before


def test_assign_section_skips_truss_in_mixed_selection():
    model = StructuralModel("mixed-section")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 2.0, 0.0, 0.0)
    model.add_element(1, 1, 2, element_type="elasticBeamColumn")
    model.add_element(
        2,
        2,
        3,
        element_type="truss",
        truss_area=0.01,
        truss_material_tag=1,
    )

    assigned = model.assign_section({1, 2}, 9)

    assert assigned == {1}
    assert model.elements[1].section_tag == 9
    assert model.elements[2].section_tag is None


def test_assign_transformation_skips_truss_in_mixed_selection():
    model = StructuralModel("mixed-transformation")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 2.0, 0.0, 0.0)
    model.add_element(1, 1, 2, element_type="elasticBeamColumn")
    model.add_element(
        2,
        2,
        3,
        element_type="truss",
        truss_area=0.01,
        truss_material_tag=1,
    )

    assigned = model.assign_transformation({1, 2}, 7)

    assert assigned == {1}
    assert model.elements[1].transf_tag == 7
    assert model.elements[2].transf_tag is None
