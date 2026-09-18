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
