from openseespy_studio.generator import (
    FrameGridSpec,
    generate_frame_grid,
    material_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    MATERIAL_DEFAULTS,
    AnalysisSettingsData,
    LoadPatternData,
    MaterialData,
    SectionData,
    TimeSeriesData,
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


def _scoped_nlth_generation_fixture(*, preload_gravity: bool):
    model = StructuralModel("scoped-nlth", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)

    time_series = {
        1: TimeSeriesData(
            1, "Current EQ", "Path", dt=0.01, values=[0.0, 0.1]
        ),
        2: TimeSeriesData(
            2, "Old EQ", "Path", dt=0.01, values=[0.0, 0.2]
        ),
        3: TimeSeriesData(3, "Gravity", "Linear", factor=1.0),
        4: TimeSeriesData(
            4, "Unowned EQ", "Path", dt=0.01, values=[0.0, 0.3]
        ),
    }
    load_patterns = {
        1: LoadPatternData(
            1,
            "Current excitation",
            "UniformExcitation",
            time_series_tag=1,
            direction=1,
        ),
        2: LoadPatternData(
            2,
            "Old excitation",
            "UniformExcitation",
            time_series_tag=2,
            direction=1,
        ),
        3: LoadPatternData(
            3,
            "Gravity",
            "Plain",
            time_series_tag=3,
        ),
        4: LoadPatternData(
            4,
            "Unowned excitation",
            "UniformExcitation",
            time_series_tag=4,
            direction=1,
        ),
    }
    current = AnalysisSettingsData(
        1,
        "Current NLTH",
        analysis_type="Transient",
        steps=1,
        dt=0.01,
        control_node=1,
        control_dof=1,
        preload_gravity=preload_gravity,
        deferred_pattern_tags=[1],
    )
    old = AnalysisSettingsData(
        2,
        "Old NLTH",
        analysis_type="Transient",
        steps=1,
        dt=0.01,
        control_node=1,
        control_dof=1,
        deferred_pattern_tags=[2],
    )
    return model, time_series, load_patterns, {1: current, 2: old}


def test_template_analysis_does_not_leak_other_analysis_patterns():
    model, series, patterns, analyses = _scoped_nlth_generation_fixture(
        preload_gravity=False
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        analyses=analyses,
        active_analysis_tag=1,
    )

    assert "ops.pattern('UniformExcitation', 1," in code
    assert "ops.pattern('UniformExcitation', 2," not in code
    assert "ops.pattern('UniformExcitation', 4," not in code
    assert "ops.pattern('Plain', 3," not in code
    assert "ops.loadConst('-time', 0.0)" not in code


def test_template_preload_uses_only_background_plain_patterns():
    model, series, patterns, analyses = _scoped_nlth_generation_fixture(
        preload_gravity=True
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        analyses=analyses,
        active_analysis_tag=1,
    )

    assert "ops.pattern('Plain', 3, 3)" in code
    assert "ops.loadConst('-time', 0.0)" in code
    assert "ops.pattern('UniformExcitation', 1," in code
    assert "ops.pattern('UniformExcitation', 2," not in code
    assert "ops.pattern('UniformExcitation', 4," not in code
