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
            frame_element_tags=[1],
            support_node_tags=[1],
            plain_pattern_tags=[7],
            monitor_node=2,
        )
    )

    assert "_studio_results =" in text
    assert "ops.nodeDisp(_studio_monitor_node)" in text
    assert "ops.nodeReaction(_studio_node)" in text
    assert "ops.eleForce(_studio_element)" in text
    assert "ops.eleResponse(_studio_element, 'localForce')" in text
    assert "'element_local_forces': _studio_element_local_forces" in text
    assert "ops.eleResponse(_studio_element, 'integrationPoints')" in text
    assert "ops.eleResponse(_studio_element, 'integrationWeights')" in text
    assert "'section', _studio_sec_no, 'force'" in text
    assert "'element_section_forces': _studio_element_section_forces" in text
    assert "ops.getLoadFactor(_studio_pattern)" in text
    assert "'load_factors': _studio_load_factors" in text
    assert "'schema_version': 3" in text
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
