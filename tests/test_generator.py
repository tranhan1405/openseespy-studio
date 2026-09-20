from openseespy_studio.generator import (
    FrameGridSpec,
    generate_frame_grid,
    material_to_openseespy,
    section_to_openseespy,
    transformation_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    MATERIAL_DEFAULTS,
    MaterialData,
    SectionData,
    TransformationData,
)


def test_frame_grid_counts():
    model = StructuralModel()
    spec = FrameGridSpec(nx=2, ny=1, nz=2)
    generate_frame_grid(model, spec)

    assert len(model.nodes) == (2 + 1) * (1 + 1) * (2 + 1)

    expected_columns = 2 * 2 * 3
    expected_x = 2 * 2 * 2
    expected_y = 2 * 1 * 3

    assert len(model.elements) == (
        expected_columns + expected_x + expected_y
    )


def test_generated_python_contains_model_entities():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        column_section_tag=1,
        beam_section_tag=1,
        column_transf_tag=1,
        beam_transf_tag=2,
    )
    generate_frame_grid(model, spec)
    transformations = {
        1: TransformationData(
            1, "Column", "PDelta", (1.0, 0.0, 0.0)
        ),
        2: TransformationData(
            2, "Beam", "Linear", (0.0, 0.0, 1.0)
        ),
    }

    sections = {
        1: SectionData(
            1,
            "Elastic",
            "Elastic",
        )
    }

    code = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
    )

    assert "ops.model('basic', '-ndm', 3, '-ndf', 6)" in code
    assert "ops.node(1" in code
    assert "ops.fix(1, 1, 1, 1, 1, 1, 1)" in code
    assert "ops.geomTransf('PDelta', 1, 1, 0, 0)" in code
    assert "ops.geomTransf('Linear', 2, 0, 0, 1)" in code
    assert "ops.element('elasticBeamColumn'" in code


def test_generator_does_not_invent_hidden_transformation():
    model = StructuralModel()
    generate_frame_grid(model, FrameGridSpec(nx=1, ny=1, nz=1))

    code = to_openseespy(model)

    assert "ops.geomTransf(" not in code
    assert "# ERROR: Element 1 has no geometric transformation assigned" in code



def test_research_material_library_generates_supported_commands():
    material_types = (
        "Concrete01",
        "Concrete04",
        "Steel01",
        "ReinforcingSteel",
        "Hysteretic",
        "Pinching4",
        "Bond_SP01",
        "ElasticPPGap",
        "FRPConfinedConcrete02",
    )
    for tag, material_type in enumerate(material_types, start=100):
        material = MaterialData(
            tag,
            material_type,
            material_type,
            parameters=MATERIAL_DEFAULTS[material_type],
        )
        units = (
            {"length": "mm", "force": "N", "time": "s"}
            if material_type == "FRPConfinedConcrete02"
            else None
        )
        command = material_to_openseespy(material, units)
        assert f"ops.uniaxialMaterial('{material_type}', {tag}," in command

    frp = MaterialData(
        200,
        "FRP Jacket",
        "FRPConfinedConcrete02",
        parameters=MATERIAL_DEFAULTS["FRPConfinedConcrete02"],
    )
    frp_command = material_to_openseespy(
        frp,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert "'-JacketC'" in frp_command
    assert ", 0.334," in frp_command
    assert ", 200," in frp_command

    pinching = MaterialData(
        201,
        "Pinching",
        "Pinching4",
        parameters=MATERIAL_DEFAULTS["Pinching4"],
    )
    assert "'cycle'" in material_to_openseespy(pinching)


def test_frp_confined_concrete02_supports_ultimate_mode():
    parameters = dict(MATERIAL_DEFAULTS["FRPConfinedConcrete02"])
    parameters["mode"] = 1.0
    material = MaterialData(
        202,
        "FRP Ultimate",
        "FRPConfinedConcrete02",
        parameters=parameters,
    )
    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert "'-Ultimate'" in command
    assert "'-JacketC'" not in command


def test_frp_confined_concrete02_rejects_incompatible_project_units():
    material = MaterialData(
        203,
        "FRP Jacket",
        "FRPConfinedConcrete02",
        parameters=MATERIAL_DEFAULTS["FRPConfinedConcrete02"],
    )
    try:
        material_to_openseespy(
            material,
            {"length": "m", "force": "kN", "time": "s"},
        )
    except ValueError as exc:
        assert "mm - N - s" in str(exc)
    else:
        raise AssertionError("Expected FRP unit-system validation")


def test_bond_sp01_slip_converts_from_si_storage_to_model_length():
    material = MaterialData(
        204,
        "Bond",
        "Bond_SP01",
        parameters=MATERIAL_DEFAULTS["Bond_SP01"],
    )
    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert ", 1," in command
    assert ", 10," in command


def test_2d_elastic_section_uses_ndm2_signature():
    section = SectionData(
        1,
        "2D elastic",
        "Elastic",
        parameters={
            "E": 200.0e9,
            "A": 0.02,
            "Iz": 8.0e-5,
            "Iy": 6.0e-5,
            "G": 80.0e9,
            "J": 1.0e-4,
        },
    )

    lines = section_to_openseespy(
        section,
        units={"length": "m", "force": "N", "time": "s"},
        ndm=2,
    )

    assert lines == [
        "ops.section('Elastic', 1, 2e+11, 0.02, 8e-05)"
    ]


def test_2d_geom_transf_omits_vecxz():
    transformation = TransformationData(
        1,
        "2D linear",
        "Linear",
        (0.0, 0.0, 1.0),
    )

    assert transformation_to_openseespy(
        transformation,
        ndm=2,
    ) == "ops.geomTransf('Linear', 1)"


def test_2d_elastic_beam_column_uses_ndm2_signature():
    model = StructuralModel("2d-elastic", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        section_tag=1,
        transf_tag=1,
    )
    sections = {
        1: SectionData(
            1,
            "2D elastic",
            "Elastic",
            parameters={
                "E": 200.0e9,
                "A": 0.02,
                "Iz": 8.0e-5,
                "Iy": 6.0e-5,
                "G": 80.0e9,
                "J": 1.0e-4,
            },
        )
    }
    transformations = {
        1: TransformationData(
            1,
            "2D linear",
            "Linear",
            (0.0, 0.0, 1.0),
        )
    }

    code = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert "ops.geomTransf('Linear', 1)" in code
    assert (
        "ops.element('elasticBeamColumn', 1, 1, 2, 0.02, 2e+11, "
        "8e-05, 1)"
        in code
    )
    assert "8e+10, 0.0001, 6e-05" not in code
