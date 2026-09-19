from openseespy_studio.generator import analysis_to_openseespy, cyclic_displacement_steps, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase


def model():
    m=StructuralModel(); m.add_node(1,0,0,0); m.add_node(2,1,0,0); return m


def test_analysis_round_trip_and_active():
    p=ProjectDatabase(model=model())
    a=AnalysisSettingsData(1,"Gravity","Static",steps=10,load_increment=0.1)
    p.add_analysis(a)
    assert p.active_analysis_tag==1
    restored=ProjectDatabase.from_dict(p.to_dict())
    assert restored.active_analysis_tag==1
    assert restored.analyses[1].analysis_type=="Static"


def test_static_analysis_generator():
    a=AnalysisSettingsData(1,"Gravity","Static",steps=5,load_increment=0.2,recovery=True)
    lines=analysis_to_openseespy(a)
    text="\n".join(lines)
    assert "ops.constraints('Transformation')" in text
    assert "ops.integrator('LoadControl', 0.2)" in text
    assert "ops.analysis('Static')" in text
    assert "for _studio_step in range(5):" in text
    assert "NewtonLineSearch" in text


def test_pushover_generator():
    a=AnalysisSettingsData(1,"Push","Pushover",steps=100,control_node=2,control_dof=1,displacement_increment=0.002)
    text="\n".join(analysis_to_openseespy(a))
    assert "ops.integrator('DisplacementControl', 2, 1, 0.002)" in text
    assert "'control_node': 2" in text
    assert "'control_dof': 1" in text
    assert "'monitor_node': 2, 'control_dof': 1" in text


def test_transient_generator():
    a=AnalysisSettingsData(1,"EQ","Transient",steps=200,dt=0.005,gamma=0.5,beta=0.25)
    text="\n".join(
        analysis_to_openseespy(
            a,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )
    assert "ops.integrator('Newmark', 0.5, 0.25)" in text
    assert "ops.analyze(1, 0.005)" in text
    assert "ops.reactions('-dynamic', '-rayleigh')" in text
    assert "'base_reactions': []" in text
    assert "'disp': [], 'vel': [], 'accel': [], 'reaction': []" in text
    assert "ops.nodeVel(_studio_node)" in text
    assert "ops.nodeAccel(_studio_node)" in text


def test_modal_generator():
    a=AnalysisSettingsData(
        1,
        "Modes",
        "Modal",
        num_modes=6,
        eigen_solver="-fullGenLapack",
    )
    text="\n".join(analysis_to_openseespy(a))
    assert (
        "_studio_eigenvalues = ops.eigen('-fullGenLapack', 6)"
        in text
    )
    assert "'frequency_hz': _studio_frequency" in text
    assert "'period_s': _studio_period" in text
    assert "'participation': _studio_participation" in text
    assert "ops.integrator" not in text


def test_only_active_analysis_is_generated():
    m=model()
    analyses={
        1:AnalysisSettingsData(1,"Static","Static"),
        2:AnalysisSettingsData(2,"Modes","Modal",num_modes=4),
    }
    script=to_openseespy(m,analyses=analyses,active_analysis_tag=2)
    assert "# Active analysis 2: Modes" in script
    assert "ops.eigen('-genBandArpack', 4)" in script
    assert "# Active analysis 1: Static" not in script


def test_pushover_control_node_is_validated():
    p=ProjectDatabase(model=model())
    try:
        p.add_analysis(AnalysisSettingsData(1,"Bad","Pushover",control_node=99))
    except ValueError as exc:
        assert "control node" in str(exc)
    else:
        raise AssertionError("Expected control node validation")


def test_cyclic_displacement_steps_hit_each_target_exactly():
    increments = cyclic_displacement_steps(
        [0.005, -0.005, 0.01, -0.01, 0.0],
        0.003,
    )

    position = 0.0
    reached = []
    targets = [0.005, -0.005, 0.01, -0.01, 0.0]
    target_index = 0
    for increment in increments:
        assert abs(increment) <= 0.003 + 1.0e-15
        position += increment
        if target_index < len(targets) and abs(position - targets[target_index]) <= 1.0e-12:
            reached.append(position)
            target_index += 1

    assert len(reached) == len(targets)
    assert all(
        abs(value - target) <= 1.0e-12
        for value, target in zip(reached, targets)
    )


def test_cyclic_analysis_round_trip_and_generator():
    analysis = AnalysisSettingsData(
        3,
        "Cyclic",
        "Cyclic",
        control_node=2,
        control_dof=1,
        cyclic_targets=[0.002, -0.002, 0.0],
        cyclic_increment=0.001,
    )
    project = ProjectDatabase(model=model())
    project.add_analysis(analysis)
    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.analyses[3].analysis_type == "Cyclic"
    assert restored.analyses[3].cyclic_targets == [0.002, -0.002, 0.0]
    assert restored.analyses[3].cyclic_increment == 0.001

    text = "\n".join(
        analysis_to_openseespy(
            restored.analyses[3],
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )
    assert "_studio_cyclic_increments" in text
    assert "ops.integrator('DisplacementControl', 2, 1, _studio_disp_increment)" in text
    assert "analysis_type='Cyclic'" in text
    assert "'cyclic_targets': [0.002, -0.002, 0.0]" in text
    assert "'planned_steps': 8" in text


def test_cyclic_analysis_requires_valid_control_node():
    project = ProjectDatabase(model=model())
    try:
        project.add_analysis(
            AnalysisSettingsData(
                4,
                "Bad cyclic",
                "Cyclic",
                control_node=99,
                cyclic_targets=[0.01, -0.01],
                cyclic_increment=0.001,
            )
        )
    except ValueError as exc:
        assert "Cyclic control node" in str(exc)
    else:
        raise AssertionError("Expected cyclic control node validation")


def test_adaptive_settings_round_trip_and_validation():
    project = ProjectDatabase(model=model())
    analysis = AnalysisSettingsData(
        20,
        "Adaptive push",
        "Pushover",
        control_node=2,
        displacement_increment=0.004,
        adaptive_step=True,
        adaptive_cutback_factor=0.5,
        adaptive_min_factor=0.125,
        adaptive_growth_factor=1.5,
        adaptive_easy_iterations=4,
        adaptive_growth_after=3,
    )
    project.add_analysis(analysis)
    restored = ProjectDatabase.from_dict(project.to_dict()).analyses[20]

    assert restored.adaptive_step is True
    assert restored.adaptive_cutback_factor == 0.5
    assert restored.adaptive_min_factor == 0.125
    assert restored.adaptive_growth_factor == 1.5
    assert restored.adaptive_easy_iterations == 4
    assert restored.adaptive_growth_after == 3

    try:
        AnalysisSettingsData(
            21,
            "Bad adaptive",
            "Pushover",
            displacement_increment=0.0,
            adaptive_step=True,
        )
    except ValueError as exc:
        assert "nonzero displacement increment" in str(exc)
    else:
        raise AssertionError("Expected zero adaptive pushover increment to fail")


def test_adaptive_static_generator_preserves_nominal_target_with_cutback_loop():
    analysis = AnalysisSettingsData(
        22,
        "Adaptive gravity",
        "Static",
        steps=4,
        load_increment=0.25,
        adaptive_step=True,
        adaptive_cutback_factor=0.5,
        adaptive_min_factor=0.125,
        adaptive_growth_factor=1.5,
        adaptive_easy_iterations=4,
        adaptive_growth_after=2,
    )

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )

    assert "_studio_nominal_increment = 0.25" in text
    assert "_studio_remaining = _studio_nominal_increment" in text
    assert "while abs(_studio_remaining) > _studio_remaining_tol:" in text
    assert "ops.integrator('LoadControl', _studio_trial_increment)" in text
    assert "_studio_emit('cutback'" in text
    assert "_studio_emit('grow'" in text
    assert "_studio_emit('adaptive_substep'" in text
    assert "'substeps': list(_studio_substeps)" in text
    assert "'cutbacks': _studio_cutbacks" in text
    compile(text, "<adaptive-static>", "exec")


def test_adaptive_pushover_generator_retries_with_smaller_displacement_increment():
    analysis = AnalysisSettingsData(
        23,
        "Adaptive push",
        "Pushover",
        steps=3,
        control_node=2,
        control_dof=1,
        displacement_increment=0.006,
        adaptive_step=True,
    )

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )

    assert (
        "ops.integrator('DisplacementControl', 2, 1, "
        "_studio_trial_increment)"
        in text
    )
    assert "_studio_new_size = max(" in text
    assert "_studio_trial_size * _studio_cutback_factor" in text
    compile(text, "<adaptive-pushover>", "exec")


def test_adaptive_transient_generator_splits_nominal_dt_without_changing_target_time():
    analysis = AnalysisSettingsData(
        24,
        "Adaptive EQ",
        "Transient",
        steps=5,
        dt=0.01,
        adaptive_step=True,
    )

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )

    assert "_studio_nominal_increment = 0.01" in text
    assert "ops.analyze(1, _studio_trial_size)" in text
    assert "_studio_remaining -= _studio_trial_increment" in text
    compile(text, "<adaptive-transient>", "exec")


def test_adaptive_cyclic_generator_keeps_explicit_protocol_increments():
    analysis = AnalysisSettingsData(
        25,
        "Adaptive cyclic",
        "Cyclic",
        control_node=2,
        cyclic_targets=[0.004, -0.004, 0.0],
        cyclic_increment=0.002,
        adaptive_step=True,
    )

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )

    assert (
        "_studio_nominal_increment = "
        "_studio_cyclic_increments[_studio_step]"
        in text
    )
    assert "_studio_remaining -= _studio_trial_increment" in text
    compile(text, "<adaptive-cyclic>", "exec")
