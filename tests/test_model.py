from openseespy_studio.model import StructuralModel


def test_delete_node_cascades_connected_elements():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_node(3, 2, 0, 0)
    model.add_element(1, 1, 2)
    model.add_element(2, 2, 3)

    model.delete_entities(node_tags={2}, cascade_nodes=True)

    assert 2 not in model.nodes
    assert model.elements == {}


def test_remove_node_without_cascade_rejects_connected_node():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_element(1, 1, 2)

    try:
        model.remove_node(1, cascade=False)
    except ValueError as exc:
        assert "connected" in str(exc)
    else:
        raise AssertionError("Expected ValueError for connected node")



def test_model_round_trip_dict():
    model = StructuralModel("RoundTrip")
    model.add_node(1, 1.0, 2.0, 3.0)
    model.add_node(2, 4.0, 5.0, 6.0)
    model.set_fixity(1, (1, 0, 1, 0, 1, 0))
    model.add_element(
        5,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=3,
        transf_tag=2,
        group="column",
    )

    restored = StructuralModel.from_dict(model.to_dict())

    assert restored.to_dict() == model.to_dict()
