from inspect import signature

from openseespy_studio.generator import analysis_to_openseespy
from openseespy_studio.project import AnalysisSettingsData
from openseespy_studio.ui.results_panel import ResultsPanel


def test_heavy_transient_throttles_live_solver_ui_stream():
    analysis = AnalysisSettingsData(
        901,
        "Heavy transient",
        "Transient",
        steps=10000,
        dt=0.001,
        live_convergence=True,
    )

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )

    assert "live_convergence=False" in text
    assert "live_convergence_requested=True" in text
    assert "ui_stride=25" in text
    assert "ui_throttled=True" in text
    assert (
        "if False or _studio_step_no == 1 or "
        "_studio_step_no == 10000 or _studio_step_no % 25 == 0:"
        in text
    )
    assert ", 0)" in next(
        line for line in text.splitlines() if line.startswith("ops.test(")
    )
    compile(text, "<heavy-transient>", "exec")


def test_normal_analysis_keeps_live_iteration_stream():
    analysis = AnalysisSettingsData(
        902,
        "Normal transient",
        "Transient",
        steps=200,
        dt=0.005,
        live_convergence=True,
    )

    text = "\n".join(
        analysis_to_openseespy(
            analysis,
            node_tags=[1, 2],
            support_node_tags=[1],
        )
    )

    assert "live_convergence=True" in text
    assert "live_convergence_requested=True" in text
    assert "ui_stride=1" in text
    assert "ui_throttled=False" in text
    assert ", 1)" in next(
        line for line in text.splitlines() if line.startswith("ops.test(")
    )


def test_live_convergence_panel_supports_deferred_repaint():
    for method_name in (
        "start_live_convergence",
        "begin_live_convergence_step",
        "append_live_convergence_iteration",
        "mark_live_substep_converged",
        "update_live_analysis_coordinate",
        "finish_live_convergence",
    ):
        parameters = signature(
            getattr(ResultsPanel, method_name)
        ).parameters
        assert "refresh" in parameters
        assert parameters["refresh"].default is True

    assert hasattr(ResultsPanel, "refresh_live_convergence_display")
