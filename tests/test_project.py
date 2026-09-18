from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ProjectDatabase, SelectionSetData


def build_project() -> ProjectDatabase:
    model = StructuralModel("Frame")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 5.0, 0.0, 0.0)
    model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    model.add_element(
        10,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=2,
        transf_tag=1,
        group="beam-x",
    )
    project = ProjectDatabase(name="Demo", model=model)
    project.selection_sets["BeamA"] = SelectionSetData(
        name="BeamA",
        node_tags={1, 2},
        element_tags={10},
    )
    return project


def test_project_round_trip_dict():
    original = build_project()
    restored = ProjectDatabase.from_dict(original.to_dict())

    assert restored.name == "Demo"
    assert restored.model.name == "Frame"
    assert restored.model.nodes[1].fixity == (1, 1, 1, 1, 1, 1)
    assert restored.model.elements[10].section_tag == 2
    assert restored.model.elements[10].transf_tag == 1
    assert restored.selection_sets["BeamA"].node_tags == {1, 2}
    assert restored.selection_sets["BeamA"].element_tags == {10}


def test_project_save_load(tmp_path):
    project = build_project()
    path = tmp_path / "demo.opsstudio"

    project.save(path)
    loaded = ProjectDatabase.load(path)

    assert loaded.to_dict() == project.to_dict()


def test_future_project_version_is_rejected():
    data = build_project().to_dict()
    data["version"] = 999

    try:
        ProjectDatabase.from_dict(data)
    except ValueError as exc:
        assert "newer than supported" in str(exc)
    else:
        raise AssertionError("Expected a future project version to be rejected")
