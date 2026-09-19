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
    assert "'schema_version': 9" in text
    assert "'monitor_node': 2" in text
    assert "'base_reactions': []" in text
    assert "'nodes': {}" in text
    assert "'convergence': {" in text
    assert "'primary_algorithm': 'Newton'" in text
    assert "_studio_attempts.append({" in text
    assert "_studio_results['convergence']['steps'].append({" in text


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


def test_generator_collects_fiber_stress_strain_at_section_points():
    settings = AnalysisSettingsData(
        2,
        "Push",
        "Pushover",
        steps=1,
        control_node=2,
        control_dof=1,
    )
    specs = {
        10: {
            "section_tag": 3,
            "locations": [0.0, 0.5, 1.0],
            "fibers": [
                {
                    "y": 0.1,
                    "z": -0.2,
                    "area": 0.001,
                    "material_tag": 7,
                }
            ],
        }
    }

    text = "\n".join(
        analysis_to_openseespy(
            settings,
            node_tags=[1, 2],
            element_tags=[10],
            frame_element_tags=[10],
            support_node_tags=[1],
            monitor_node=2,
            fiber_response_specs=specs,
        )
    )

    assert "_studio_fiber_response_specs" in text
    assert "'fiber', _studio_y, _studio_z, _studio_mat" in text
    assert "'stressStrain'" in text
    assert "'element_fiber_responses': _studio_element_fiber_responses" in text
