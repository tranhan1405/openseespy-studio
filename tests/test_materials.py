from openseespy_studio.generator import material_to_openseespy, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import MaterialData, ProjectDatabase


def test_material_project_round_trip():
    project = ProjectDatabase(name="Materials")
    project.add_material(
        MaterialData(
            tag=1,
            name="Steel S355",
            material_type="Steel02",
            parameters={
                "Fy": 355e6,
                "E0": 200e9,
                "b": 0.01,
                "R0": 20.0,
                "cR1": 0.925,
                "cR2": 0.15,
            },
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.materials[1].name == "Steel S355"
    assert restored.materials[1].material_type == "Steel02"
    assert restored.materials[1].parameters["Fy"] == 355e6


def test_material_tags_must_be_unique():
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            tag=1,
            name="E1",
            material_type="Elastic",
            parameters={"E": 200e9},
        )
    )

    try:
        project.add_material(
            MaterialData(
                tag=1,
                name="E2",
                material_type="Elastic",
                parameters={"E": 100e9},
            )
        )
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected duplicate material tag to fail")


def test_material_generator_lines():
    steel = MaterialData(
        tag=4,
        name="Steel",
        material_type="Steel02",
        parameters={
            "Fy": 355e6,
            "E0": 200e9,
            "b": 0.01,
            "R0": 20.0,
            "cR1": 0.925,
            "cR2": 0.15,
        },
    )
    line = material_to_openseespy(steel)

    assert "Steel02" in line
    assert "3.55e+08" in line
    assert line.startswith("ops.uniaxialMaterial")


def test_full_script_contains_project_materials():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_element(1, 1, 2)

    material = MaterialData(
        tag=1,
        name="Elastic",
        material_type="Elastic",
        parameters={"E": 2.0e11},
    )
    script = to_openseespy(model, {1: material})

    assert "# Materials" in script
    assert "ops.uniaxialMaterial('Elastic', 1, 2e+11)" in script


def test_v1_empty_material_dictionary_still_loads():
    project = ProjectDatabase()
    data = project.to_dict()
    data["version"] = 1
    data["materials"] = {}

    restored = ProjectDatabase.from_dict(data)

    assert restored.materials == {}
