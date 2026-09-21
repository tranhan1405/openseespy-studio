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
    assert "355000" in line
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
    assert "ops.uniaxialMaterial('Elastic', 1, 2e+08)" in script


def test_v1_empty_material_dictionary_still_loads():
    project = ProjectDatabase()
    data = project.to_dict()
    data["version"] = 1
    data["materials"] = {}

    restored = ProjectDatabase.from_dict(data)

    assert restored.materials == {}


def test_material_generator_can_use_n_m_s_without_stress_scaling():
    steel = MaterialData(
        tag=5,
        name="Steel SI",
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

    line = material_to_openseespy(
        steel,
        {"length": "m", "force": "N", "time": "s"},
    )

    assert "3.55e+08" in line
    assert "2e+11" in line


def test_frp_confined_concrete_generator_preserves_documented_n_mm_mpa_inputs():
    material = MaterialData(
        tag=9,
        name="FRP confined circular concrete",
        material_type="FRPConfinedConcrete",
        parameters={
            "fpc1": 27.5e6,
            "fpc2": 27.5e6,
            "epsc0": 0.002,
            "D": 0.400,
            "c": 0.035,
            "Ej": 266.0e9,
            "Sj": 0.0,
            "tj": 0.000222,
            "eju": 0.0163,
            "S": 0.150,
            "fyl": 374.0e6,
            "fyh": 363.0e6,
            "dlong": 0.016,
            "dtrans": 0.006,
            "Es": 200.0e9,
            "nu0": 0.2,
            "k": 0.8,
            "useBuck": 1.0,
        },
    )
    line = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert line == (
        "ops.uniaxialMaterial('FRPConfinedConcrete', 9, "
        "27.5, 27.5, 0.002, 400, 35, 266000, 0, 0.222, "
        "0.0163, 150, 374, 363, 16, 6, 200000, 0.2, 0.8, 1)"
    )


def test_frp_confined_concrete_rejects_non_documented_project_units():
    material = MaterialData(
        tag=9,
        name="FRP confined circular concrete",
        material_type="FRPConfinedConcrete",
    )
    try:
        material_to_openseespy(
            material,
            {"length": "m", "force": "N", "time": "s"},
        )
    except ValueError as exc:
        assert "mm - N - s" in str(exc)
    else:
        raise AssertionError(
            "FRPConfinedConcrete should reject non-mm/N project units"
        )


def test_steel01_three_parameter_defaults_match_opensees_source():
    material = MaterialData(
        tag=20,
        name="Steel01 default hardening",
        material_type="Steel01",
        parameters={
            "Fy": 250.0e6,
            "E0": 200.0e9,
            "b": 0.014,
        },
    )

    assert material.parameters["a1"] == 0.0
    assert material.parameters["a2"] == 55.0
    assert material.parameters["a3"] == 0.0
    assert material.parameters["a4"] == 55.0

    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert command == (
        "ops.uniaxialMaterial('Steel01', 20, 250, 200000, "
        "0.014, 0, 55, 0, 55)"
    )
