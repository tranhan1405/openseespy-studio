import pytest

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
    ConnectionData,
    ConstraintData,
    FiberData,
    ElementLoadData,
    LoadPatternData,
    NodalLoadData,
    MaterialData,
    PrescribedDisplacementData,
    RecorderData,
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


def test_generator_rejects_prescribed_displacement_as_static_dc_driver():
    model = StructuralModel("static-dc-driver", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))

    series = {1: TimeSeriesData(1, "Reference", "Linear", factor=1.0)}
    patterns = {
        1: LoadPatternData(
            1,
            "Bad driver",
            "Plain",
            time_series_tag=1,
        )
    }
    prescribed = {
        1: PrescribedDisplacementData(
            1,
            "Bad imposed displacement",
            1,
            2,
            1,
            0.01,
        )
    }
    analyses = {
        1: AnalysisSettingsData(
            1,
            "Static DC",
            "Static",
            integrator="DisplacementControl",
            control_node=2,
            control_dof=1,
            deferred_pattern_tags=[1],
        )
    }

    with pytest.raises(ValueError, match="force reference-load pattern"):
        to_openseespy(
            model,
            time_series=series,
            load_patterns=patterns,
            prescribed_displacements=prescribed,
            analyses=analyses,
            active_analysis_tag=1,
        )


def test_generator_rejects_control_dof_above_model_ndf():
    model = StructuralModel("ndf-control-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    analysis = AnalysisSettingsData(
        10,
        "Invalid model-aware control DOF",
        "Static",
        control_dof=5,
    )

    with pytest.raises(
        ValueError,
        match=r"control DOF 5 .* model ndf=3",
    ):
        to_openseespy(
            model,
            analyses={10: analysis},
            active_analysis_tag=10,
        )


def test_generator_accepts_control_dof_within_model_ndf():
    model = StructuralModel("valid-control-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    analysis = AnalysisSettingsData(
        11,
        "Valid model-aware control DOF",
        "Static",
        control_dof=3,
    )

    code = to_openseespy(
        model,
        analyses={11: analysis},
        active_analysis_tag=11,
    )

    assert "'control_dof': 3" in code


def test_generator_does_not_apply_control_dof_ndf_preflight_to_modal():
    model = StructuralModel("modal-control-dof", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    analysis = AnalysisSettingsData(
        12,
        "Modal ignores control DOF",
        "Modal",
        num_modes=1,
        control_dof=6,
    )

    code = to_openseespy(
        model,
        analyses={12: analysis},
        active_analysis_tag=12,
    )

    assert "ops.eigen('-genBandArpack', 1)" in code


@pytest.mark.parametrize(
    ("analysis_type", "integrator"),
    [
        ("Static", "DisplacementControl"),
        ("Pushover", "DisplacementControl"),
        ("Cyclic", "DisplacementControl"),
    ],
)
def test_generator_rejects_missing_active_control_node(
    analysis_type,
    integrator,
):
    model = StructuralModel("missing-control-node", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)

    kwargs = {
        "integrator": integrator,
        "control_node": 99,
        "control_dof": 1,
    }
    if analysis_type == "Static":
        kwargs["displacement_increment"] = 0.001
    elif analysis_type == "Pushover":
        kwargs["displacement_increment"] = 0.001
    else:
        kwargs.update(
            cyclic_targets=[0.001, -0.001],
            cyclic_increment=0.0005,
        )

    analysis = AnalysisSettingsData(
        13,
        "Missing control node",
        analysis_type,
        **kwargs,
    )

    with pytest.raises(
        ValueError,
        match=r"control node 99 does not exist in the model",
    ):
        to_openseespy(
            model,
            analyses={13: analysis},
            active_analysis_tag=13,
        )


@pytest.mark.parametrize(
    ("analysis_type", "integrator"),
    [
        ("Static", "LoadControl"),
        ("Static", "ArcLength"),
        ("Transient", "Newmark"),
        ("Modal", "None"),
    ],
)
def test_generator_ignores_stale_control_node_when_analysis_does_not_use_it(
    analysis_type,
    integrator,
):
    model = StructuralModel("unused-control-node", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)

    kwargs = {
        "integrator": integrator,
        "control_node": 99,
        "control_dof": 1,
    }
    if analysis_type == "Transient":
        kwargs.update(dt=0.01)
    elif analysis_type == "Modal":
        kwargs.update(num_modes=1)

    analysis = AnalysisSettingsData(
        14,
        "Unused stale control node",
        analysis_type,
        **kwargs,
    )

    code = to_openseespy(
        model,
        analyses={14: analysis},
        active_analysis_tag=14,
    )

    if analysis_type == "Modal":
        assert "ops.eigen('-genBandArpack', 1)" in code
    else:
        assert "ops.analysis(" in code


@pytest.mark.parametrize(
    ("analysis_type", "integrator"),
    [
        ("Static", "DisplacementControl"),
        ("Pushover", "DisplacementControl"),
        ("Cyclic", "DisplacementControl"),
    ],
)
def test_generator_rejects_restrained_control_dof(
    analysis_type,
    integrator,
):
    model = StructuralModel("restrained-control-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(2, (1, 0, 0))

    kwargs = {
        "integrator": integrator,
        "control_node": 2,
        "control_dof": 1,
    }
    if analysis_type == "Static":
        kwargs["displacement_increment"] = 0.001
    elif analysis_type == "Pushover":
        kwargs["displacement_increment"] = 0.001
    else:
        kwargs.update(
            cyclic_targets=[0.001, -0.001],
            cyclic_increment=0.0005,
        )

    analysis = AnalysisSettingsData(
        15,
        "Restrained control DOF",
        analysis_type,
        **kwargs,
    )

    with pytest.raises(
        ValueError,
        match=r"control node 2 DOF 1 is restrained by a support",
    ):
        to_openseespy(
            model,
            analyses={15: analysis},
            active_analysis_tag=15,
        )


def test_generator_accepts_free_control_dof_on_partially_restrained_node():
    model = StructuralModel("free-control-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(2, (1, 0, 1))
    analysis = AnalysisSettingsData(
        16,
        "Free control DOF",
        "Pushover",
        control_node=2,
        control_dof=2,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        analyses={16: analysis},
        active_analysis_tag=16,
    )

    assert "ops.integrator('DisplacementControl', 2, 2" in code


def test_generator_rejects_active_prescribed_displacement_on_control_dof():
    model = StructuralModel("prescribed-control-conflict", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Background", "Plain", time_series_tag=1)
    }
    prescribed = {
        1: PrescribedDisplacementData(
            1,
            "Imposed UX",
            1,
            2,
            1,
            0.001,
        )
    }
    analysis = AnalysisSettingsData(
        17,
        "Push",
        "Pushover",
        control_node=2,
        control_dof=1,
        displacement_increment=0.001,
    )

    with pytest.raises(
        ValueError,
        match=r"control node 2 DOF 1 conflicts with active Prescribed Displacement",
    ):
        to_openseespy(
            model,
            time_series=series,
            load_patterns=patterns,
            prescribed_displacements=prescribed,
            analyses={17: analysis},
            active_analysis_tag=17,
        )


def test_generator_ignores_prescribed_displacement_in_other_deferred_analysis():
    model = StructuralModel("inactive-prescribed-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {
        1: TimeSeriesData(1, "Current", "Linear"),
        2: TimeSeriesData(2, "Other", "Linear"),
    }
    patterns = {
        1: LoadPatternData(1, "Current driver", "Plain", time_series_tag=1),
        2: LoadPatternData(2, "Other driver", "Plain", time_series_tag=2),
    }
    prescribed = {
        1: PrescribedDisplacementData(
            1,
            "Other imposed UX",
            2,
            2,
            1,
            0.001,
        )
    }
    current = AnalysisSettingsData(
        18,
        "Current push",
        "Pushover",
        control_node=2,
        control_dof=1,
        displacement_increment=0.001,
        deferred_pattern_tags=[1],
    )
    other = AnalysisSettingsData(
        19,
        "Other static",
        "Static",
        integrator="LoadControl",
        deferred_pattern_tags=[2],
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={18: current, 19: other},
        active_analysis_tag=18,
    )

    assert "ops.sp(2, 1, 0.001)" not in code


def test_generator_rejects_equal_dof_constrained_control_dof():
    model = StructuralModel("equal-dof-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        1,
        "Tie node 2 to node 3",
        "equalDOF",
        retained_node=3,
        constrained_nodes=[2],
        dofs=(1, 2),
    )
    analysis = AnalysisSettingsData(
        24,
        "Push dependent DOF",
        "Pushover",
        control_node=2,
        control_dof=1,
        displacement_increment=0.001,
    )

    with pytest.raises(
        ValueError,
        match=r"control node 2 DOF 1 is a constrained/dependent DOF in equalDOF",
    ):
        to_openseespy(
            model,
            constraints={1: constraint},
            analyses={24: analysis},
            active_analysis_tag=24,
        )


def test_generator_allows_equal_dof_retained_node_as_control():
    model = StructuralModel("equal-dof-retained-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        2,
        "Tie node 2 to node 3",
        "equalDOF",
        retained_node=3,
        constrained_nodes=[2],
        dofs=(1,),
    )
    analysis = AnalysisSettingsData(
        25,
        "Push retained DOF",
        "Pushover",
        control_node=3,
        control_dof=1,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        constraints={2: constraint},
        analyses={25: analysis},
        active_analysis_tag=25,
    )

    assert "ops.equalDOF(3, 2, 1)" in code
    assert "ops.integrator('DisplacementControl', 3, 1" in code


def test_generator_allows_unconstrained_dof_on_equal_dof_secondary_node():
    model = StructuralModel("equal-dof-free-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        3,
        "Tie UX only",
        "equalDOF",
        retained_node=3,
        constrained_nodes=[2],
        dofs=(1,),
    )
    analysis = AnalysisSettingsData(
        26,
        "Push free UY",
        "Pushover",
        control_node=2,
        control_dof=2,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        constraints={3: constraint},
        analyses={26: analysis},
        active_analysis_tag=26,
    )

    assert "ops.integrator('DisplacementControl', 2, 2" in code


def test_generator_rejects_rigid_link_bar_translational_control_dof():
    model = StructuralModel("rigid-link-bar-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        4,
        "Rigid bar",
        "rigidLink",
        retained_node=3,
        constrained_nodes=[2],
        link_type="bar",
    )
    analysis = AnalysisSettingsData(
        27,
        "Push dependent UX",
        "Pushover",
        control_node=2,
        control_dof=1,
        displacement_increment=0.001,
    )

    with pytest.raises(
        ValueError,
        match=r"control node 2 DOF 1 is a constrained/dependent DOF in rigidLink",
    ):
        to_openseespy(
            model,
            constraints={4: constraint},
            analyses={27: analysis},
            active_analysis_tag=27,
        )


def test_generator_allows_rigid_link_bar_rotational_control_dof():
    model = StructuralModel("rigid-link-bar-rotation", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        5,
        "Rigid bar",
        "rigidLink",
        retained_node=3,
        constrained_nodes=[2],
        link_type="bar",
    )
    analysis = AnalysisSettingsData(
        28,
        "Push free RZ",
        "Pushover",
        control_node=2,
        control_dof=3,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        constraints={5: constraint},
        analyses={28: analysis},
        active_analysis_tag=28,
    )

    assert "ops.rigidLink('bar', 3, 2)" in code
    assert "ops.integrator('DisplacementControl', 2, 3" in code


def test_generator_rejects_rigid_link_beam_rotational_control_dof():
    model = StructuralModel("rigid-link-beam-rotation", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        6,
        "Rigid beam",
        "rigidLink",
        retained_node=3,
        constrained_nodes=[2],
        link_type="beam",
    )
    analysis = AnalysisSettingsData(
        29,
        "Push dependent RZ",
        "Pushover",
        control_node=2,
        control_dof=3,
        displacement_increment=0.001,
    )

    with pytest.raises(
        ValueError,
        match=r"control node 2 DOF 3 is a constrained/dependent DOF in rigidLink",
    ):
        to_openseespy(
            model,
            constraints={6: constraint},
            analyses={29: analysis},
            active_analysis_tag=29,
        )


def test_generator_allows_rigid_link_retained_node_as_control():
    model = StructuralModel("rigid-link-master-control", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        7,
        "Rigid beam",
        "rigidLink",
        retained_node=3,
        constrained_nodes=[2],
        link_type="beam",
    )
    analysis = AnalysisSettingsData(
        30,
        "Push master UX",
        "Pushover",
        control_node=3,
        control_dof=1,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        constraints={7: constraint},
        analyses={30: analysis},
        active_analysis_tag=30,
    )

    assert "ops.integrator('DisplacementControl', 3, 1" in code


@pytest.mark.parametrize(
    ("perp_dirn", "control_dof"),
    [
        (1, 2),
        (1, 3),
        (1, 4),
        (2, 1),
        (2, 3),
        (2, 5),
        (3, 1),
        (3, 2),
        (3, 6),
    ],
)
def test_generator_rejects_3d_rigid_diaphragm_dependent_control_dofs(
    perp_dirn,
    control_dof,
):
    model = StructuralModel("rigid-diaphragm-3d", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 1.0, 0.0)
    model.add_node(3, 0.0, 0.0, 0.0)

    constraint = ConstraintData(
        8,
        "Rigid diaphragm",
        "rigidDiaphragm",
        retained_node=3,
        constrained_nodes=[2],
        perp_dirn=perp_dirn,
    )
    analysis = AnalysisSettingsData(
        31,
        "Push diaphragm dependent DOF",
        "Pushover",
        control_node=2,
        control_dof=control_dof,
        displacement_increment=0.001,
    )

    with pytest.raises(
        ValueError,
        match=r"constrained/dependent DOF in rigidDiaphragm",
    ):
        to_openseespy(
            model,
            constraints={8: constraint},
            analyses={31: analysis},
            active_analysis_tag=31,
        )


def test_generator_allows_3d_rigid_diaphragm_unconstrained_control_dof():
    model = StructuralModel("rigid-diaphragm-free-3d", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 1.0, 0.0)
    model.add_node(3, 0.0, 0.0, 0.0)

    constraint = ConstraintData(
        9,
        "XY diaphragm",
        "rigidDiaphragm",
        retained_node=3,
        constrained_nodes=[2],
        perp_dirn=3,
    )
    analysis = AnalysisSettingsData(
        32,
        "Push free UZ",
        "Pushover",
        control_node=2,
        control_dof=3,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        constraints={9: constraint},
        analyses={32: analysis},
        active_analysis_tag=32,
    )

    assert "ops.rigidDiaphragm(3, 3, 2)" in code
    assert "ops.integrator('DisplacementControl', 2, 3" in code


@pytest.mark.parametrize(
    ("perp_dirn", "control_dof"),
    [(1, 1), (2, 2), (3, 1), (3, 2), (3, 3)],
)
def test_generator_rejects_2d_rigid_diaphragm_dependent_control_dofs(
    perp_dirn,
    control_dof,
):
    model = StructuralModel("rigid-diaphragm-2d", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 0.0, 0.0)

    constraint = ConstraintData(
        10,
        "Rigid diaphragm 2D",
        "rigidDiaphragm",
        retained_node=3,
        constrained_nodes=[2],
        perp_dirn=perp_dirn,
    )
    analysis = AnalysisSettingsData(
        33,
        "Push dependent 2D DOF",
        "Pushover",
        control_node=2,
        control_dof=control_dof,
        displacement_increment=0.001,
    )

    with pytest.raises(
        ValueError,
        match=r"constrained/dependent DOF in rigidDiaphragm",
    ):
        to_openseespy(
            model,
            constraints={10: constraint},
            analyses={33: analysis},
            active_analysis_tag=33,
        )


def test_generator_allows_rigid_diaphragm_retained_node_as_control():
    model = StructuralModel("rigid-diaphragm-master", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 1.0, 0.0)
    model.add_node(3, 0.0, 0.0, 0.0)

    constraint = ConstraintData(
        11,
        "XY diaphragm",
        "rigidDiaphragm",
        retained_node=3,
        constrained_nodes=[2],
        perp_dirn=3,
    )
    analysis = AnalysisSettingsData(
        34,
        "Push diaphragm master",
        "Pushover",
        control_node=3,
        control_dof=1,
        displacement_increment=0.001,
    )

    code = to_openseespy(
        model,
        constraints={11: constraint},
        analyses={34: analysis},
        active_analysis_tag=34,
    )

    assert "ops.integrator('DisplacementControl', 3, 1" in code


@pytest.mark.parametrize(
    ("ndm", "ndf"),
    [
        (2, 2),
        (3, 3),
        (3, 4),
    ],
)
def test_generator_rejects_rigid_diaphragm_on_unsupported_model_signature(
    ndm,
    ndf,
):
    model = StructuralModel("bad-rigid-diaphragm-signature", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        12,
        "Unsupported diaphragm",
        "rigidDiaphragm",
        retained_node=1,
        constrained_nodes=[2],
        perp_dirn=3,
    )

    with pytest.raises(
        ValueError,
        match=r"require a 2D/3DOF or 3D/6DOF model",
    ):
        to_openseespy(
            model,
            constraints={12: constraint},
        )


@pytest.mark.parametrize(
    ("ndm", "ndf"),
    [
        (2, 3),
        (3, 6),
    ],
)
def test_generator_accepts_rigid_diaphragm_supported_model_signatures(
    ndm,
    ndf,
):
    model = StructuralModel("valid-rigid-diaphragm-signature", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        13,
        "Supported diaphragm",
        "rigidDiaphragm",
        retained_node=1,
        constrained_nodes=[2],
        perp_dirn=3,
    )

    code = to_openseespy(
        model,
        constraints={13: constraint},
    )

    assert "ops.rigidDiaphragm(3, 1, 2)" in code


@pytest.mark.parametrize(
    ("ndm", "ndf", "invalid_dof"),
    [
        (2, 2, 3),
        (2, 3, 5),
        (3, 3, 4),
    ],
)
def test_generator_rejects_equal_dof_above_model_ndf(
    ndm,
    ndf,
    invalid_dof,
):
    model = StructuralModel("bad-equal-dof", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        14,
        "Invalid equalDOF",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1, invalid_dof),
    )

    with pytest.raises(
        ValueError,
        match=rf"equalDOF constraint DOF\(s\) exceed model ndf={ndf}",
    ):
        to_openseespy(
            model,
            constraints={14: constraint},
        )


def test_generator_accepts_equal_dof_up_to_model_ndf():
    model = StructuralModel("valid-equal-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        15,
        "Valid equalDOF",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1, 3),
    )

    code = to_openseespy(
        model,
        constraints={15: constraint},
    )

    assert "ops.equalDOF(1, 2, 1, 3)" in code


@pytest.mark.parametrize(
    ("ndm", "ndf"),
    [
        (2, 1),
        (3, 2),
    ],
)
def test_generator_rejects_rigid_link_bar_when_ndf_below_ndm(
    ndm,
    ndf,
):
    model = StructuralModel("bad-rigid-bar-signature", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        16,
        "Invalid rigid bar",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="bar",
    )

    with pytest.raises(
        ValueError,
        match=r"rigidLink bar requires ndf >= ndm",
    ):
        to_openseespy(model, constraints={16: constraint})


@pytest.mark.parametrize(
    ("ndm", "ndf"),
    [
        (2, 2),
        (2, 3),
        (2, 4),
        (3, 3),
        (3, 4),
        (3, 6),
    ],
)
def test_generator_rigid_link_bar_accepts_any_ndf_at_least_ndm(
    ndm,
    ndf,
):
    model = StructuralModel("valid-rigid-bar-signature", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        17,
        "Valid rigid bar",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="bar",
    )

    code = to_openseespy(model, constraints={17: constraint})
    assert "ops.rigidLink('bar', 1, 2)" in code


@pytest.mark.parametrize(
    ("ndm", "ndf"),
    [
        (2, 4),
        (2, 6),
        (3, 4),
        (3, 5),
    ],
)
def test_generator_rejects_unsupported_rigid_link_beam_signatures(
    ndm,
    ndf,
):
    model = StructuralModel("bad-rigid-beam-signature", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        18,
        "Invalid rigid beam",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="beam",
    )

    with pytest.raises(
        ValueError,
        match=r"rigidLink beam requires ndf == ndm, 2D/3DOF, or 3D/6DOF",
    ):
        to_openseespy(model, constraints={18: constraint})


@pytest.mark.parametrize(
    ("ndm", "ndf"),
    [
        (2, 2),
        (2, 3),
        (3, 3),
        (3, 6),
    ],
)
def test_generator_accepts_supported_rigid_link_beam_signatures(
    ndm,
    ndf,
):
    model = StructuralModel("valid-rigid-beam-signature", ndm=ndm, ndf=ndf)
    if ndm == 2:
        model.add_node(1, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0)
    else:
        model.add_node(1, 0.0, 0.0, 0.0)
        model.add_node(2, 1.0, 0.0, 0.0)

    constraint = ConstraintData(
        19,
        "Valid rigid beam",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="beam",
    )

    code = to_openseespy(model, constraints={19: constraint})
    assert "ops.rigidLink('beam', 1, 2)" in code


def test_generator_rejects_overlapping_mpcs_on_same_dependent_dof():
    model = StructuralModel("overlapping-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraints = {
        20: ConstraintData(
            20,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        ),
        21: ConstraintData(
            21,
            "Rigid bar",
            "rigidLink",
            retained_node=3,
            constrained_nodes=[2],
            link_type="bar",
        ),
    }

    with pytest.raises(
        ValueError,
        match=r"Multiple MPC constraints assign the same dependent DOF",
    ):
        to_openseespy(model, constraints=constraints)


def test_generator_allows_multiple_mpcs_on_disjoint_dependent_dofs():
    model = StructuralModel("disjoint-mpc", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraints = {
        22: ConstraintData(
            22,
            "Tie RZ",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(3,),
        ),
        23: ConstraintData(
            23,
            "Rigid bar",
            "rigidLink",
            retained_node=3,
            constrained_nodes=[2],
            link_type="bar",
        ),
    }

    code = to_openseespy(model, constraints=constraints)

    assert "ops.equalDOF(1, 2, 3)" in code
    assert "ops.rigidLink('bar', 3, 2)" in code


def test_generator_rejects_mpc_dependent_dof_also_fixed_by_support():
    model = StructuralModel("fixed-mpc-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(2, (1, 0, 0))

    constraint = ConstraintData(
        24,
        "Tie fixed UX",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1,),
    )

    with pytest.raises(
        ValueError,
        match=r"MPC dependent DOF\(s\) are also fixed by supports",
    ):
        to_openseespy(model, constraints={24: constraint})


def test_generator_allows_support_on_dof_not_owned_by_mpc():
    model = StructuralModel("fixed-free-mpc-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(2, (0, 0, 1))

    constraint = ConstraintData(
        25,
        "Rigid bar translations",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="bar",
    )

    code = to_openseespy(model, constraints={25: constraint})

    assert "ops.fix(2, 0, 0, 1)" in code
    assert "ops.rigidLink('bar', 1, 2)" in code


@pytest.mark.parametrize(
    ("constraint_type", "kwargs"),
    [
        (
            "equalDOF",
            {"dofs": (1,)},
        ),
        (
            "rigidLink",
            {"link_type": "bar"},
        ),
        (
            "rigidDiaphragm",
            {"perp_dirn": 3},
        ),
    ],
)
def test_generator_rejects_constraint_with_missing_retained_node(
    constraint_type,
    kwargs,
):
    model = StructuralModel("missing-retained-node", ndm=2, ndf=3)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        26,
        "Missing retained node",
        constraint_type,
        retained_node=99,
        constrained_nodes=[2],
        **kwargs,
    )

    with pytest.raises(
        ValueError,
        match=r"Constraint\(s\) reference missing model node tag\(s\): 26: 99",
    ):
        to_openseespy(
            model,
            constraints={26: constraint},
        )


@pytest.mark.parametrize(
    ("constraint_type", "kwargs"),
    [
        (
            "equalDOF",
            {"dofs": (1,)},
        ),
        (
            "rigidLink",
            {"link_type": "beam"},
        ),
        (
            "rigidDiaphragm",
            {"perp_dirn": 3},
        ),
    ],
)
def test_generator_rejects_constraint_with_missing_constrained_node(
    constraint_type,
    kwargs,
):
    model = StructuralModel("missing-secondary-node", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)

    constraint = ConstraintData(
        27,
        "Missing constrained node",
        constraint_type,
        retained_node=1,
        constrained_nodes=[98],
        **kwargs,
    )

    with pytest.raises(
        ValueError,
        match=r"Constraint\(s\) reference missing model node tag\(s\): 27: 98",
    ):
        to_openseespy(
            model,
            constraints={27: constraint},
        )


def test_generator_reports_all_missing_nodes_by_constraint():
    model = StructuralModel("multiple-missing-constraint-nodes", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)

    constraints = {
        28: ConstraintData(
            28,
            "Missing equalDOF nodes",
            "equalDOF",
            retained_node=97,
            constrained_nodes=[98],
            dofs=(1,),
        ),
        29: ConstraintData(
            29,
            "Missing rigidLink node",
            "rigidLink",
            retained_node=1,
            constrained_nodes=[99],
            link_type="bar",
        ),
    }

    with pytest.raises(ValueError) as exc_info:
        to_openseespy(model, constraints=constraints)

    message = str(exc_info.value)
    assert "28: 97, 98" in message
    assert "29: 99" in message


def test_generator_transformation_rejects_multiple_mp_objects_same_node():
    model = StructuralModel("transformation-multiple-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraints = {
        30: ConstraintData(
            30,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        ),
        31: ConstraintData(
            31,
            "Tie RZ",
            "equalDOF",
            retained_node=3,
            constrained_nodes=[2],
            dofs=(3,),
        ),
    }
    analysis = AnalysisSettingsData(
        40,
        "Transformation static",
        "Static",
        constraints_handler="Transformation",
    )

    with pytest.raises(
        ValueError,
        match=r"Transformation constraint handler supports only one MP constraint object",
    ):
        to_openseespy(
            model,
            constraints=constraints,
            analyses={40: analysis},
            active_analysis_tag=40,
        )


def test_generator_plain_allows_disjoint_equal_dof_objects_same_node():
    model = StructuralModel("plain-multiple-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraints = {
        32: ConstraintData(
            32,
            "Tie UX",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        ),
        33: ConstraintData(
            33,
            "Tie RZ",
            "equalDOF",
            retained_node=3,
            constrained_nodes=[2],
            dofs=(3,),
        ),
    }
    analysis = AnalysisSettingsData(
        41,
        "Plain static",
        "Static",
        constraints_handler="Plain",
    )

    code = to_openseespy(
        model,
        constraints=constraints,
        analyses={41: analysis},
        active_analysis_tag=41,
    )

    assert "ops.equalDOF(1, 2, 1)" in code
    assert "ops.equalDOF(3, 2, 3)" in code


def test_generator_plain_rejects_offset_rigid_link_beam():
    model = StructuralModel("plain-rigid-beam", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        34,
        "Offset rigid beam",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="beam",
    )
    analysis = AnalysisSettingsData(
        42,
        "Plain static",
        "Static",
        constraints_handler="Plain",
    )

    with pytest.raises(
        ValueError,
        match=r"Plain constraint handler would ignore non-identity MP transformation matrix",
    ):
        to_openseespy(
            model,
            constraints={34: constraint},
            analyses={42: analysis},
            active_analysis_tag=42,
        )


def test_generator_plain_allows_rigid_link_bar_with_offset():
    model = StructuralModel("plain-rigid-bar", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        35,
        "Rigid bar",
        "rigidLink",
        retained_node=1,
        constrained_nodes=[2],
        link_type="bar",
    )
    analysis = AnalysisSettingsData(
        43,
        "Plain static",
        "Static",
        constraints_handler="Plain",
    )

    code = to_openseespy(
        model,
        constraints={35: constraint},
        analyses={43: analysis},
        active_analysis_tag=43,
    )

    assert "ops.rigidLink('bar', 1, 2)" in code


def test_generator_plain_rejects_coupled_rigid_diaphragm():
    model = StructuralModel("plain-rigid-diaphragm", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 1.0, 0.0)

    constraint = ConstraintData(
        36,
        "XY diaphragm",
        "rigidDiaphragm",
        retained_node=1,
        constrained_nodes=[2],
        perp_dirn=3,
    )
    analysis = AnalysisSettingsData(
        44,
        "Plain static",
        "Static",
        constraints_handler="Plain",
    )

    with pytest.raises(
        ValueError,
        match=r"Plain constraint handler would ignore non-identity MP transformation matrix",
    ):
        to_openseespy(
            model,
            constraints={36: constraint},
            analyses={44: analysis},
            active_analysis_tag=44,
        )


def test_generator_plain_rejects_active_nonzero_prescribed_displacement():
    model = StructuralModel("plain-nonzero-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Imposed displacement", "Plain", time_series_tag=1)
    }
    prescribed = {
        37: PrescribedDisplacementData(
            37,
            "Imposed UX",
            1,
            2,
            1,
            0.01,
        )
    }
    analysis = AnalysisSettingsData(
        45,
        "Plain static",
        "Static",
        constraints_handler="Plain",
    )

    with pytest.raises(
        ValueError,
        match=r"Plain constraint handler cannot enforce non-zero Prescribed Displacement",
    ):
        to_openseespy(
            model,
            time_series=series,
            load_patterns=patterns,
            prescribed_displacements=prescribed,
            analyses={45: analysis},
            active_analysis_tag=45,
        )


def test_generator_plain_allows_zero_prescribed_displacement():
    model = StructuralModel("plain-zero-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Zero displacement", "Plain", time_series_tag=1)
    }
    prescribed = {
        38: PrescribedDisplacementData(
            38,
            "Zero UX",
            1,
            2,
            1,
            0.0,
        )
    }
    analysis = AnalysisSettingsData(
        46,
        "Plain static",
        "Static",
        constraints_handler="Plain",
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={46: analysis},
        active_analysis_tag=46,
    )

    assert "ops.sp(2, 1, 0)" in code


def test_generator_transformation_allows_nonzero_prescribed_displacement():
    model = StructuralModel("transformation-nonzero-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Imposed displacement", "Plain", time_series_tag=1)
    }
    prescribed = {
        39: PrescribedDisplacementData(
            39,
            "Imposed UX",
            1,
            2,
            1,
            0.01,
        )
    }
    analysis = AnalysisSettingsData(
        47,
        "Transformation static",
        "Static",
        constraints_handler="Transformation",
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={47: analysis},
        active_analysis_tag=47,
    )

    assert "ops.sp(2, 1, 0.01)" in code


def test_generator_plain_ignores_nonzero_prescribed_displacement_in_other_driver():
    model = StructuralModel("plain-inactive-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {
        1: TimeSeriesData(1, "Current", "Linear"),
        2: TimeSeriesData(2, "Other", "Linear"),
    }
    patterns = {
        1: LoadPatternData(1, "Current driver", "Plain", time_series_tag=1),
        2: LoadPatternData(2, "Other driver", "Plain", time_series_tag=2),
    }
    prescribed = {
        40: PrescribedDisplacementData(
            40,
            "Other imposed UX",
            2,
            2,
            1,
            0.01,
        )
    }
    current = AnalysisSettingsData(
        48,
        "Current static",
        "Static",
        constraints_handler="Plain",
        deferred_pattern_tags=[1],
    )
    other = AnalysisSettingsData(
        49,
        "Other static",
        "Static",
        constraints_handler="Transformation",
        deferred_pattern_tags=[2],
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={48: current, 49: other},
        active_analysis_tag=48,
    )

    assert "ops.sp(2, 1, 0.01)" not in code


@pytest.mark.parametrize("handler", ["Transformation", "Plain"])
def test_generator_rejects_chained_mp_constraints(handler):
    model = StructuralModel("chained-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraints = {
        41: ConstraintData(
            41,
            "Node 2 follows node 1",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        ),
        42: ConstraintData(
            42,
            "Node 3 follows node 2",
            "equalDOF",
            retained_node=2,
            constrained_nodes=[3],
            dofs=(1,),
        ),
    }
    analysis = AnalysisSettingsData(
        50,
        "Static chain",
        "Static",
        constraints_handler=handler,
    )

    with pytest.raises(
        ValueError,
        match=rf"{handler} constraint handler does not follow chained MP constraints",
    ):
        to_openseespy(
            model,
            constraints=constraints,
            analyses={50: analysis},
            active_analysis_tag=50,
        )


@pytest.mark.parametrize("handler", ["Transformation", "Plain"])
def test_generator_allows_nonchained_mp_constraints(handler):
    model = StructuralModel("nonchained-mp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)
    model.add_node(4, 3.0, 0.0)

    constraints = {
        43: ConstraintData(
            43,
            "Pair one",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        ),
        44: ConstraintData(
            44,
            "Pair two",
            "equalDOF",
            retained_node=3,
            constrained_nodes=[4],
            dofs=(1,),
        ),
    }
    analysis = AnalysisSettingsData(
        51,
        "Static nonchain",
        "Static",
        constraints_handler=handler,
    )

    code = to_openseespy(
        model,
        constraints=constraints,
        analyses={51: analysis},
        active_analysis_tag=51,
    )

    assert "ops.equalDOF(1, 2, 1)" in code
    assert "ops.equalDOF(3, 4, 1)" in code


def test_generator_chain_error_reports_relevant_constraint_tags():
    model = StructuralModel("chain-diagnostics", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraints = {
        45: ConstraintData(
            45,
            "Upstream",
            "equalDOF",
            retained_node=1,
            constrained_nodes=[2],
            dofs=(1,),
        ),
        46: ConstraintData(
            46,
            "Downstream",
            "equalDOF",
            retained_node=2,
            constrained_nodes=[3],
            dofs=(2,),
        ),
    }
    analysis = AnalysisSettingsData(
        52,
        "Transformation chain",
        "Static",
        constraints_handler="Transformation",
    )

    with pytest.raises(ValueError) as exc_info:
        to_openseespy(
            model,
            constraints=constraints,
            analyses={52: analysis},
            active_analysis_tag=52,
        )

    message = str(exc_info.value)
    assert "constraint 46 retains node 2" in message
    assert "constrained by 45" in message


def test_generator_rejects_active_prescribed_displacement_on_mpc_dependent_dof():
    model = StructuralModel("sp-mpc-conflict", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        47,
        "Tie UX",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1,),
    )
    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Imposed UX", "Plain", time_series_tag=1)
    }
    prescribed = {
        41: PrescribedDisplacementData(
            41,
            "SP UX",
            1,
            2,
            1,
            0.0,
        )
    }
    analysis = AnalysisSettingsData(
        53,
        "Static",
        "Static",
        constraints_handler="Transformation",
    )

    with pytest.raises(
        ValueError,
        match=r"Active Prescribed Displacement object\(s\) overlap MPC dependent DOF",
    ):
        to_openseespy(
            model,
            constraints={47: constraint},
            time_series=series,
            load_patterns=patterns,
            prescribed_displacements=prescribed,
            analyses={53: analysis},
            active_analysis_tag=53,
        )


def test_generator_allows_prescribed_displacement_on_nondependent_dof():
    model = StructuralModel("sp-mpc-other-dof", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        48,
        "Tie UX",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1,),
    )
    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Imposed UY", "Plain", time_series_tag=1)
    }
    prescribed = {
        42: PrescribedDisplacementData(
            42,
            "SP UY",
            1,
            2,
            2,
            0.0,
        )
    }
    analysis = AnalysisSettingsData(
        54,
        "Static",
        "Static",
        constraints_handler="Transformation",
    )

    code = to_openseespy(
        model,
        constraints={48: constraint},
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={54: analysis},
        active_analysis_tag=54,
    )

    assert "ops.sp(2, 2, 0)" in code


def test_generator_allows_prescribed_displacement_on_mpc_retained_node():
    model = StructuralModel("sp-mpc-retained", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        49,
        "Tie UX",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1,),
    )
    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Master imposed UX", "Plain", time_series_tag=1)
    }
    prescribed = {
        43: PrescribedDisplacementData(
            43,
            "Master SP UX",
            1,
            1,
            1,
            0.0,
        )
    }
    analysis = AnalysisSettingsData(
        55,
        "Static",
        "Static",
        constraints_handler="Transformation",
    )

    code = to_openseespy(
        model,
        constraints={49: constraint},
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={55: analysis},
        active_analysis_tag=55,
    )

    assert "ops.sp(1, 1, 0)" in code


def test_generator_ignores_prescribed_mpc_conflict_in_inactive_other_driver():
    model = StructuralModel("sp-mpc-inactive", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    constraint = ConstraintData(
        50,
        "Tie UX",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1,),
    )
    series = {
        1: TimeSeriesData(1, "Current", "Linear"),
        2: TimeSeriesData(2, "Other", "Linear"),
    }
    patterns = {
        1: LoadPatternData(1, "Current", "Plain", time_series_tag=1),
        2: LoadPatternData(2, "Other", "Plain", time_series_tag=2),
    }
    prescribed = {
        44: PrescribedDisplacementData(
            44,
            "Other SP UX",
            2,
            2,
            1,
            0.0,
        )
    }
    current = AnalysisSettingsData(
        56,
        "Current",
        "Static",
        constraints_handler="Transformation",
        deferred_pattern_tags=[1],
    )
    other = AnalysisSettingsData(
        57,
        "Other",
        "Static",
        constraints_handler="Transformation",
        deferred_pattern_tags=[2],
    )

    code = to_openseespy(
        model,
        constraints={50: constraint},
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={56: current, 57: other},
        active_analysis_tag=56,
    )

    assert "ops.sp(2, 1, 0)" not in code


def test_generator_rejects_multiple_active_prescribed_displacements_same_dof():
    model = StructuralModel("duplicate-active-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {
        1: TimeSeriesData(1, "One", "Linear"),
        2: TimeSeriesData(2, "Two", "Linear"),
    }
    patterns = {
        1: LoadPatternData(1, "Pattern one", "Plain", time_series_tag=1),
        2: LoadPatternData(2, "Pattern two", "Plain", time_series_tag=2),
    }
    prescribed = {
        45: PrescribedDisplacementData(45, "SP one", 1, 2, 1, 0.01),
        46: PrescribedDisplacementData(46, "SP two", 2, 2, 1, 0.02),
    }
    analysis = AnalysisSettingsData(
        58,
        "Static",
        "Static",
        constraints_handler="Transformation",
    )

    with pytest.raises(
        ValueError,
        match=r"Multiple active Prescribed Displacement objects target the same node/DOF",
    ):
        to_openseespy(
            model,
            time_series=series,
            load_patterns=patterns,
            prescribed_displacements=prescribed,
            analyses={58: analysis},
            active_analysis_tag=58,
        )


def test_generator_allows_same_dof_sp_in_inactive_other_driver():
    model = StructuralModel("scoped-same-dof-sp", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)

    series = {
        1: TimeSeriesData(1, "One", "Linear"),
        2: TimeSeriesData(2, "Two", "Linear"),
    }
    patterns = {
        1: LoadPatternData(1, "Pattern one", "Plain", time_series_tag=1),
        2: LoadPatternData(2, "Pattern two", "Plain", time_series_tag=2),
    }
    prescribed = {
        47: PrescribedDisplacementData(47, "SP one", 1, 2, 1, 0.01),
        48: PrescribedDisplacementData(48, "SP two", 2, 2, 1, 0.02),
    }
    current = AnalysisSettingsData(
        59,
        "Current",
        "Static",
        constraints_handler="Transformation",
        deferred_pattern_tags=[1],
    )
    other = AnalysisSettingsData(
        60,
        "Other",
        "Static",
        constraints_handler="Transformation",
        deferred_pattern_tags=[2],
    )

    code = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={59: current, 60: other},
        active_analysis_tag=59,
    )

    assert "ops.sp(2, 1, 0.01)" in code
    assert "ops.sp(2, 1, 0.02)" not in code


def test_generator_allows_retained_master_sp_through_preload_and_load_const():
    model = StructuralModel("master-sp-preload", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 2.0, 0.0)

    constraint = ConstraintData(
        51,
        "Slave follows master",
        "equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1,),
    )
    series = {
        1: TimeSeriesData(1, "Preload", "Linear"),
        2: TimeSeriesData(2, "Driver", "Linear"),
    }
    patterns = {
        1: LoadPatternData(1, "Master preload", "Plain", time_series_tag=1),
        2: LoadPatternData(2, "Driver", "Plain", time_series_tag=2),
    }
    prescribed = {
        49: PrescribedDisplacementData(
            49,
            "Master imposed UX",
            1,
            1,
            1,
            0.01,
        )
    }
    analysis = AnalysisSettingsData(
        61,
        "Static with preload",
        "Static",
        constraints_handler="Transformation",
        preload_gravity=True,
        gravity_steps=10,
        deferred_pattern_tags=[2],
    )

    code = to_openseespy(
        model,
        constraints={51: constraint},
        time_series=series,
        load_patterns=patterns,
        prescribed_displacements=prescribed,
        analyses={61: analysis},
        active_analysis_tag=61,
    )

    sp_index = code.index("ops.sp(1, 1, 0.01)")
    const_index = code.index("ops.loadConst('-time', 0.0)")
    driver_index = code.index("ops.pattern('Plain', 2, 2)")
    assert sp_index < const_index < driver_index
    assert "ops.equalDOF(1, 2, 1)" in code


def test_generator_rejects_load_pattern_with_missing_time_series():
    model = StructuralModel("orphan-time-series", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)

    patterns = {
        1: LoadPatternData(1, "Orphan pattern", "Plain", time_series_tag=99)
    }

    with pytest.raises(
        ValueError,
        match=r"Load pattern\(s\) reference missing time series",
    ):
        to_openseespy(
            model,
            time_series={},
            load_patterns=patterns,
        )


def test_generator_rejects_orphan_nodal_load_pattern():
    model = StructuralModel("orphan-nodal-pattern", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    load = NodalLoadData(
        1,
        "Orphan nodal load",
        99,
        1,
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    )

    with pytest.raises(
        ValueError,
        match=r"nodal load 1 -> missing pattern 99",
    ):
        to_openseespy(
            model,
            nodal_loads={1: load},
        )


def test_generator_rejects_orphan_element_load_reference():
    model = StructuralModel("orphan-element-load", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    series = {1: TimeSeriesData(1, "Linear", "Linear")}
    patterns = {
        1: LoadPatternData(1, "Plain", "Plain", time_series_tag=1)
    }
    load = ElementLoadData(
        1,
        "Orphan beam load",
        1,
        99,
        load_type="Uniform",
        wy=-1.0,
    )

    with pytest.raises(
        ValueError,
        match=r"element load 1 -> missing element 99",
    ):
        to_openseespy(
            model,
            time_series=series,
            load_patterns=patterns,
            element_loads={1: load},
        )


def test_generator_rejects_prescribed_displacement_with_missing_pattern():
    model = StructuralModel("orphan-sp-pattern", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    displacement = PrescribedDisplacementData(
        1,
        "Orphan SP",
        99,
        1,
        1,
        0.01,
    )

    with pytest.raises(
        ValueError,
        match=r"prescribed displacement 1 -> missing pattern 99",
    ):
        to_openseespy(
            model,
            prescribed_displacements={1: displacement},
        )


def test_generator_rejects_regular_load_on_uniform_excitation_pattern():
    model = StructuralModel("load-on-excitation", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    series = {1: TimeSeriesData(1, "Path", "Path", dt=0.01, values=[0.0, 1.0])}
    patterns = {
        1: LoadPatternData(
            1,
            "Excitation",
            "UniformExcitation",
            time_series_tag=1,
            direction=1,
        )
    }
    load = NodalLoadData(
        2,
        "Invalid nodal load",
        1,
        1,
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    )

    with pytest.raises(
        ValueError,
        match=r"nodal load 2 -> non-Plain pattern 1",
    ):
        to_openseespy(
            model,
            time_series=series,
            load_patterns=patterns,
            nodal_loads={2: load},
        )


def test_generator_rejects_section_with_missing_material():
    model = StructuralModel("orphan-section-material", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    section = SectionData(
        1,
        "Fiber",
        "Fiber",
        fibers=[FiberData(0.0, 0.0, 0.01, 99)],
    )

    with pytest.raises(
        ValueError,
        match=r"section 1 -> missing material 99",
    ):
        to_openseespy(
            model,
            materials={},
            sections={1: section},
        )


def test_generator_rejects_truss_with_missing_material_reference():
    model = StructuralModel("orphan-truss-material", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="truss",
        truss_area=0.01,
        truss_material_tag=99,
    )

    with pytest.raises(
        ValueError,
        match=r"truss element 1 -> missing material 99",
    ):
        to_openseespy(model, materials={})


def test_generator_rejects_element_with_missing_section_reference():
    model = StructuralModel("orphan-element-section", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=99,
        transf_tag=1,
    )

    with pytest.raises(
        ValueError,
        match=r"element 1 -> missing section 99",
    ):
        to_openseespy(model, sections={})


def test_generator_rejects_connection_with_missing_material():
    model = StructuralModel("orphan-connection-material", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    connection = ConnectionData(
        10,
        "Spring",
        "zeroLength",
        1,
        2,
        materials_by_dof={1: 99},
    )

    with pytest.raises(
        ValueError,
        match=r"connection 10 -> missing material 99",
    ):
        to_openseespy(
            model,
            materials={},
            connections={10: connection},
        )


def test_generator_rejects_zero_length_section_with_missing_section():
    model = StructuralModel("orphan-connection-section", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    connection = ConnectionData(
        11,
        "Section spring",
        "zeroLengthSection",
        1,
        2,
        section_tag=99,
    )

    with pytest.raises(
        ValueError,
        match=r"connection 11 -> missing section 99",
    ):
        to_openseespy(
            model,
            sections={},
            connections={11: connection},
        )


def test_generator_rejects_fiber_recorder_with_missing_material_reference():
    model = StructuralModel("orphan-fiber-recorder-material", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    recorder = RecorderData(
        1,
        "Fiber",
        "Fiber",
        target_tags=[1],
        response="stressStrain",
        section_number=1,
        material_tag=99,
    )

    with pytest.raises(
        ValueError,
        match=r"fiber recorder 1 -> missing material 99",
    ):
        to_openseespy(
            model,
            materials={},
            recorders={1: recorder},
        )


def test_generator_rejects_frame_element_with_missing_transformation():
    model = StructuralModel("orphan-transformation", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=99,
    )
    section = SectionData(1, "Elastic", "Elastic")

    with pytest.raises(
        ValueError,
        match=r"element 1 -> missing transformation 99",
    ):
        to_openseespy(
            model,
            sections={1: section},
            transformations={},
        )


def test_generator_rejects_frame_element_without_transformation_assignment():
    model = StructuralModel("missing-transformation-assignment", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=None,
    )
    section = SectionData(1, "Elastic", "Elastic")

    with pytest.raises(
        ValueError,
        match=r"element 1 -> no geometric transformation assigned",
    ):
        to_openseespy(
            model,
            sections={1: section},
            transformations={},
        )


def test_generator_truss_does_not_require_geometric_transformation():
    model = StructuralModel("truss-no-transformation", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="truss",
        truss_area=0.01,
        truss_material_tag=1,
    )
    material = MaterialData(
        1,
        "Elastic",
        "Elastic",
        {"E": 200000.0},
    )

    code = to_openseespy(
        model,
        materials={1: material},
        transformations={},
    )

    assert "ops.element('Truss', 1" in code


def test_generator_rejects_element_with_missing_endpoint_node():
    model = StructuralModel("orphan-element-node", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(99, 1.0, 0.0)
    model.add_element(
        1,
        1,
        99,
        element_type="elasticBeamColumn",
        section_tag=1,
        transf_tag=1,
    )
    model.nodes.pop(99)

    with pytest.raises(
        ValueError,
        match=r"element 1 -> missing node 99",
    ):
        to_openseespy(model)


def test_generator_rejects_connection_with_missing_endpoint_node():
    model = StructuralModel("orphan-connection-node", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    connection = ConnectionData(
        10,
        "Orphan link",
        "twoNodeLink",
        1,
        99,
        materials_by_dof={1: 1},
    )

    with pytest.raises(
        ValueError,
        match=r"connection 10 -> missing node 99",
    ):
        to_openseespy(
            model,
            connections={10: connection},
        )


def test_generator_rejects_node_recorder_with_missing_target_node():
    model = StructuralModel("orphan-node-recorder", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    recorder = RecorderData(
        1,
        "Node recorder",
        "Node",
        target_tags=[99],
        response="disp",
        dofs=[1],
    )

    with pytest.raises(
        ValueError,
        match=r"node recorder 1 -> missing node 99",
    ):
        to_openseespy(
            model,
            recorders={1: recorder},
        )


def test_generator_rejects_element_recorder_with_missing_target_element():
    model = StructuralModel("orphan-element-recorder", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    recorder = RecorderData(
        2,
        "Element recorder",
        "Element",
        target_tags=[99],
        response="globalForce",
    )

    with pytest.raises(
        ValueError,
        match=r"element recorder 2 -> missing element 99",
    ):
        to_openseespy(
            model,
            recorders={2: recorder},
        )
