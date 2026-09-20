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
        integration_type="Legendre",
        integration_points=7,
        force_max_iter=25,
        force_tolerance=1.0e-10,
        mass_per_length=12.5,
        consistent_mass=True,
    )

    restored = StructuralModel.from_dict(model.to_dict())

    assert restored.to_dict() == model.to_dict()



def test_bulk_assign_element_formulation():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_node(3, 2, 0, 0)
    model.add_element(1, 1, 2)
    model.add_element(2, 2, 3)

    updated = model.assign_element_formulation(
        {1, 2},
        element_type="forceBeamColumn",
        integration_type="Lobatto",
        integration_points=6,
        force_max_iter=30,
        force_tolerance=1.0e-11,
        mass_per_length=5.0,
    )

    assert updated == {1, 2}
    assert all(
        element.element_type == "forceBeamColumn"
        for element in model.elements.values()
    )
    assert all(
        element.integration_points == 6
        for element in model.elements.values()
    )
    assert all(
        element.force_max_iter == 30
        for element in model.elements.values()
    )


def test_invalid_beam_integration_settings_are_rejected():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)

    try:
        model.add_element(
            1,
            1,
            2,
            element_type="forceBeamColumn",
            integration_points=1,
        )
    except ValueError as exc:
        assert "at least 2 points" in str(exc)
    else:
        raise AssertionError("Expected integration-point validation failure")


def test_hinge_integration_round_trip_dict():
    model = StructuralModel("HingeRoundTrip")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.add_element(
        10,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=2,
        integration_type="HingeRadauTwo",
        hinge_i_section_tag=1,
        hinge_j_section_tag=1,
        interior_section_tag=3,
        hinge_i_length=0.30,
        hinge_j_length=0.10,
    )

    restored = StructuralModel.from_dict(model.to_dict())

    assert restored.to_dict() == model.to_dict()
    element = restored.elements[10]
    assert element.integration_type == "HingeRadauTwo"
    assert element.hinge_i_section_tag == 1
    assert element.interior_section_tag == 3
