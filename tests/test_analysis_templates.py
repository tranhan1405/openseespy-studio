import math

from openseespy_studio.analysis_templates import (
    GroundMotionComponentSpec,
    build_cyclic_template,
    build_nlth_multi_template,
    build_nlth_template,
    build_pushover_template,
    expand_cyclic_protocol,
    lateral_load_weights,
    parse_cyclic_protocol_text,
    parse_ground_motion_text,
    parse_node_weight_text,
)
from openseespy_studio.generator import (
    analysis_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    LoadPatternData,
    NodalLoadData,
    ProjectDatabase,
    TimeSeriesData,
)


def project_with_two_storeys():
    model = StructuralModel("template-test")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.add_node(3, 0.0, 0.0, 6.0)
    model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    return ProjectDatabase(model=model)


def test_expand_cyclic_protocol_builds_repeated_reversals_and_zero_return():
    targets = expand_cyclic_protocol([(0.01, 2), (0.02, 1)])
    assert targets == [
        0.01,
        -0.01,
        0.01,
        -0.01,
        0.02,
        -0.02,
        0.0,
    ]


def test_parse_ground_motion_text_accepts_csv_and_comments():
    text = """
# time, accel
0.00, 0.10
0.01, -0.20
0.02, 0.30
"""
    assert parse_ground_motion_text(text, column=2) == [0.10, -0.20, 0.30]


def test_triangular_distribution_loads_first_free_floor_from_model_base():
    project = project_with_two_storeys()
    weights = lateral_load_weights(
        project,
        dof=1,
        distribution="Triangular",
    )

    assert set(weights) == {2, 3}
    assert weights[2] > 0.0
    assert weights[3] > weights[2]
    assert math.isclose(weights[2], 1.0 / 3.0)
    assert math.isclose(weights[3], 2.0 / 3.0)


def test_pushover_template_creates_normalized_lateral_pattern_and_results():
    project = project_with_two_storeys()
    plan = build_pushover_template(
        project,
        name="Push X",
        control_node=3,
        control_dof=1,
        target_displacement=0.12,
        max_increment=0.01,
        distribution="Triangular",
        solver_preset="Robust",
    )

    assert plan.analysis.analysis_type == "Pushover"
    assert plan.analysis.control_node == 3
    assert plan.analysis.steps == 12
    assert math.isclose(plan.analysis.displacement_increment, 0.01)
    assert plan.analysis.adaptive_step is True
    assert plan.analysis.preload_gravity is True
    assert plan.analysis.deferred_pattern_tags == [
        plan.load_patterns[0].tag
    ]
    assert len(plan.time_series) == 1
    assert len(plan.load_patterns) == 1
    assert plan.load_patterns[0].pattern_type == "Plain"
    assert math.isclose(
        sum(load.values[0] for load in plan.nodal_loads),
        1.0,
        rel_tol=1.0e-12,
    )
    assert any(result.result_type == "PushoverCurve" for result in plan.results)
    assert any(result.result_type == "HingeState" for result in plan.results)


def test_cyclic_template_uses_protocol_builder_targets():
    project = project_with_two_storeys()
    plan = build_cyclic_template(
        project,
        name="Cyclic X",
        control_node=3,
        control_dof=1,
        protocol_rows=[(0.01, 1), (0.02, 2)],
        max_increment=0.002,
        distribution="Uniform",
        solver_preset="Balanced",
    )

    assert plan.analysis.analysis_type == "Cyclic"
    assert plan.analysis.cyclic_targets == [
        0.01,
        -0.01,
        0.02,
        -0.02,
        0.02,
        -0.02,
        0.0,
    ]
    assert plan.analysis.cyclic_increment == 0.002
    assert any(
        result.result_type == "CyclicHysteresis"
        for result in plan.results
    )


def test_nlth_template_converts_g_and_creates_uniform_excitation():
    project = project_with_two_storeys()
    plan = build_nlth_template(
        project,
        name="EQ X",
        ground_motion_values=[0.0, 0.5, -1.0],
        dt=0.02,
        input_unit="g",
        scale_factor=1.25,
        direction=1,
        monitor_node=3,
        damping_ratio=0.05,
        damping_mode_i=1,
        damping_mode_j=3,
        solver_preset="Robust",
    )

    series = plan.time_series[0]
    pattern = plan.load_patterns[0]
    assert series.series_type == "Path"
    assert math.isclose(series.values[1], 0.5 * 9.80665)
    assert math.isclose(series.values[2], -9.80665)
    assert series.factor == 1.25
    assert pattern.pattern_type == "UniformExcitation"
    assert pattern.direction == 1
    assert plan.analysis.analysis_type == "Transient"
    assert plan.analysis.steps == 3
    assert plan.analysis.rayleigh_damping_ratio == 0.05
    assert plan.analysis.rayleigh_mode_i == 1
    assert plan.analysis.rayleigh_mode_j == 3
    assert any(
        result.result_type == "TimeHistory"
        and result.settings.get("quantity") == "Acceleration"
        for result in plan.results
    )


def test_nlth_ground_motion_conversion_respects_mm_model_units():
    project = project_with_two_storeys()
    project.units = {"length": "mm", "force": "N", "time": "s"}
    plan = build_nlth_template(
        project,
        name="EQ mm",
        ground_motion_values=[1.0],
        dt=0.01,
        input_unit="g",
        scale_factor=1.0,
        direction=1,
        monitor_node=3,
    )
    assert math.isclose(plan.time_series[0].values[0], 9806.65)


def test_rayleigh_settings_round_trip_and_generator():
    project = project_with_two_storeys()
    plan = build_nlth_template(
        project,
        name="Damped EQ",
        ground_motion_values=[0.0, 0.1],
        dt=0.01,
        input_unit="m/s²",
        scale_factor=1.0,
        direction=1,
        monitor_node=3,
        damping_ratio=0.05,
        damping_mode_i=1,
        damping_mode_j=3,
    )
    project.add_analysis(plan.analysis)

    restored = ProjectDatabase.from_dict(project.to_dict())
    analysis = restored.analyses[plan.analysis.tag]
    assert analysis.rayleigh_damping_ratio == 0.05
    assert analysis.rayleigh_mode_i == 1
    assert analysis.rayleigh_mode_j == 3

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2, 3],
            support_node_tags=[1],
        )
    )
    assert "_studio_damping_eigs = ops.eigen(3)" in text
    assert "ops.rayleigh(_studio_alpha_m, 0.0, 0.0, _studio_beta_k)" in text


def test_template_sequence_preloads_existing_plain_pattern_before_driver():
    project = project_with_two_storeys()
    gravity_series = TimeSeriesData(
        1,
        "Gravity",
        "Linear",
        factor=1.0,
    )
    gravity_pattern = LoadPatternData(
        1,
        "Gravity",
        "Plain",
        time_series_tag=1,
    )
    gravity_load = NodalLoadData(
        1,
        "Gravity load",
        1,
        3,
        (0.0, 0.0, -1.0, 0.0, 0.0, 0.0),
    )
    project.add_time_series(gravity_series)
    project.add_load_pattern(gravity_pattern)
    project.add_nodal_load(gravity_load)

    plan = build_pushover_template(
        project,
        name="Staged Push",
        control_node=3,
        control_dof=1,
        target_displacement=0.02,
        max_increment=0.002,
        distribution="Uniform",
    )
    for series in plan.time_series:
        project.add_time_series(series)
    for pattern in plan.load_patterns:
        project.add_load_pattern(pattern)
    for load in plan.nodal_loads:
        project.add_nodal_load(load)
    project.add_analysis(plan.analysis)
    project.set_active_analysis(plan.analysis.tag)

    script = to_openseespy(
        project.model,
        time_series=project.time_series,
        load_patterns=project.load_patterns,
        nodal_loads=project.nodal_loads,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
        units=project.units,
    )

    driver_tag = plan.load_patterns[0].tag
    gravity_pos = script.index("# Template sequence: gravity")
    hold_pos = script.index("ops.loadConst('-time', 0.0)")
    driver_pos = script.index(
        f"ops.pattern('Plain', {driver_tag}, "
    )
    main_analysis_pos = script.index(
        f"# Active analysis {plan.analysis.tag}:"
    )
    assert gravity_pos < hold_pos < driver_pos < main_analysis_pos


def test_generator_rejects_missing_deferred_pattern():
    project = project_with_two_storeys()
    plan = build_pushover_template(
        project,
        name="Missing driver",
        control_node=3,
        control_dof=1,
        target_displacement=0.01,
        max_increment=0.001,
    )
    project.add_analysis(plan.analysis)

    try:
        to_openseespy(
            project.model,
            analyses=project.analyses,
            active_analysis_tag=plan.analysis.tag,
        )
    except ValueError as exc:
        assert "missing driving load pattern" in str(exc)
    else:
        raise AssertionError("Expected missing driving-pattern validation")



def test_parse_cyclic_protocol_text_accepts_header_and_csv():
    rows = parse_cyclic_protocol_text(
        "Amplitude,Cycles\n0.005,2\n0.010,3\n"
    )
    assert rows == [(0.005, 2), (0.01, 3)]


def test_parse_custom_node_weights_and_normalize():
    project = project_with_two_storeys()
    weights = parse_node_weight_text("2, 2\n3, 6\n")
    normalized = lateral_load_weights(
        project,
        dof=1,
        distribution="Custom",
        custom_weights=weights,
    )
    assert normalized == {2: 0.25, 3: 0.75}


def test_pushover_accepts_first_mode_weight_map():
    project = project_with_two_storeys()
    plan = build_pushover_template(
        project,
        name="Mode Push",
        control_node=3,
        control_dof=1,
        target_displacement=0.03,
        max_increment=0.003,
        distribution="First-mode proportional",
        distribution_weights={2: 0.4, 3: 1.0},
    )
    force_by_node = {
        load.node_tag: load.values[0]
        for load in plan.nodal_loads
    }
    assert math.isclose(
        sum(abs(value) for value in force_by_node.values()),
        1.0,
    )
    assert force_by_node[3] > force_by_node[2]


def test_multi_component_nlth_creates_one_excitation_per_axis():
    project = project_with_two_storeys()
    plan = build_nlth_multi_template(
        project,
        name="BiDir EQ",
        components=[
            GroundMotionComponentSpec(
                direction=1,
                values=[0.0, 0.1, -0.1],
                scale_factor=1.0,
                name="X",
            ),
            GroundMotionComponentSpec(
                direction=2,
                values=[0.0, 0.2, -0.2, 0.1],
                scale_factor=0.8,
                name="Y",
            ),
        ],
        dt=0.01,
        input_unit="g",
        monitor_node=3,
        monitor_dof=1,
    )

    assert len(plan.time_series) == 2
    assert len(plan.load_patterns) == 2
    assert [pattern.direction for pattern in plan.load_patterns] == [1, 2]
    assert plan.analysis.steps == 4
    assert plan.analysis.deferred_pattern_tags == [
        pattern.tag for pattern in plan.load_patterns
    ]
    histories = [
        result
        for result in plan.results
        if result.result_type == "TimeHistory"
    ]
    assert {result.settings["dof"] for result in histories} == {1, 2}
