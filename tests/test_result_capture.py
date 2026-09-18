from openseespy_studio.generator import analysis_to_openseespy
from openseespy_studio.project import AnalysisSettingsData


def test_static_generator_collects_results_and_history():
    settings = AnalysisSettingsData(
        1,
        "Gravity",
        "Static",
        steps=2,
        load_increment=0.5,
    )
    text = "\n".join(
        analysis_to_openseespy(
            settings,
            node_tags=[1, 2],
            element_tags=[1],
            support_node_tags=[1],
            monitor_node=2,
        )
    )

    assert "_studio_results =" in text
    assert "ops.nodeDisp(_studio_monitor_node)" in text
    assert "ops.nodeReaction(_studio_node)" in text
    assert "ops.eleForce(_studio_element)" in text
    assert "'monitor_node': 2" in text


def test_modal_generator_collects_mode_vectors():
    settings = AnalysisSettingsData(
        1,
        "Modes",
        "Modal",
        num_modes=3,
    )
    text = "\n".join(
        analysis_to_openseespy(
            settings,
            node_tags=[1, 2],
        )
    )

    assert "ops.eigen(3)" in text
    assert "ops.nodeEigenvector(_studio_node, _studio_mode)" in text
    assert "_studio_results['modes']" in text
