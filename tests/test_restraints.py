from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import (
    FIXITY_PRESETS,
    StructuralModel,
    classify_fixity,
)


def make_nodes() -> StructuralModel:
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 2.0, 0.0, 0.0)
    return model


def test_fixity_presets_are_classified():
    for name, fixity in FIXITY_PRESETS.items():
        assert classify_fixity(fixity) == name

    assert classify_fixity((0, 0, 0, 0, 0, 0)) == "Free"
    assert classify_fixity((1, 0, 0, 0, 1, 0)) == "Custom"


def test_bulk_restraint_apply_and_clear():
    model = make_nodes()

    updated = model.set_fixity_many({1, 2}, FIXITY_PRESETS["Pinned"])

    assert updated == {1, 2}
    assert model.nodes[1].fixity == (1, 1, 1, 0, 0, 0)
    assert model.nodes[2].fixity == (1, 1, 1, 0, 0, 0)
    assert model.nodes[3].fixity == (0, 0, 0, 0, 0, 0)

    cleared = model.clear_fixity_many({2})

    assert cleared == {2}
    assert model.nodes[2].fixity == (0, 0, 0, 0, 0, 0)


def test_generator_emits_support_fixity():
    model = make_nodes()
    model.set_fixity_many({1}, FIXITY_PRESETS["Roller X"])

    script = to_openseespy(model)

    assert "ops.fix(1, 0, 1, 1, 0, 0, 0)" in script


def test_fixity_round_trip():
    model = make_nodes()
    model.set_fixity_many({1}, FIXITY_PRESETS["Fixed"])
    model.set_fixity_many({2}, FIXITY_PRESETS["Roller Z"])

    restored = StructuralModel.from_dict(model.to_dict())

    assert restored.nodes[1].fixity == FIXITY_PRESETS["Fixed"]
    assert restored.nodes[2].fixity == FIXITY_PRESETS["Roller Z"]
