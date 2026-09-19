import math

from openseespy_studio.analysis_templates import (
    build_cyclic_template,
    build_nlth_template,
    build_pushover_template,
    expand_cyclic_protocol,
    parse_ground_motion_text,
)
from openseespy_studio.generator import analysis_to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ProjectDatabase


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
