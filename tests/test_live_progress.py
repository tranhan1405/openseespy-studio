from openseespy_studio.generator import analysis_to_openseespy
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase
from openseespy_studio.model import StructuralModel


def test_analysis_generator_emits_live_progress_and_convergence_events():
    settings = AnalysisSettingsData(
        1,
        "Push",
        "Pushover",
        steps=20,
        control_node=2,
        control_dof=1,
        displacement_increment=0.002,
        recovery=True,
    )

    text = "\n".join(
        analysis_to_openseespy(
            settings,
            node_tags=[1, 2],
            support_node_tags=[1],
            monitor_node=2,
        )
    )

    assert "[STUDIO_EVENT]" in text
    assert "_studio_emit('progress'" in text
    assert "_studio_emit('convergence_failed'" in text
    assert "_studio_emit('fallback'" in text
    assert "_studio_emit('recovered'" in text
    assert "ops.testIter()" in text
    assert "ops.testNorms()" in text
    assert "ops.test('NormDispIncr', 1e-08, 50, 1)" in text
    assert "_studio_emit('step_start'" in text
    assert "'norm_history': list(_studio_norm_history)" in text
    assert "base_shear=_studio_base" in text


def test_modal_generator_emits_mode_progress():
    settings = AnalysisSettingsData(
        1,
        "Modes",
        "Modal",
        num_modes=5,
    )

    text = "\n".join(
        analysis_to_openseespy(
            settings,
            node_tags=[1, 2],
        )
    )

    assert "_studio_emit('start', total=5" in text
    assert "_studio_emit('progress', step=_studio_mode" in text
    assert "eigenvalue=float(_studio_lambda)" in text


def test_external_console_setting_round_trip():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Static",
            "Static",
            show_external_console=True,
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.analyses[1].show_external_console is True
