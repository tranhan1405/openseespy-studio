from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.analysis_dialog import AnalysisDialog


_APP = QApplication.instance() or QApplication([])


def _shown(widget) -> bool:
    return not widget.isHidden()


def _close(dialog: AnalysisDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_static_analysis_hides_irrelevant_fields():
    dialog = AnalysisDialog(analysis_type="Static")
    try:
        assert _shown(dialog.load_inc)
        assert _shown(dialog.steps)
        assert _shown(dialog.test)
        assert _shown(dialog.algorithm)
        assert _shown(dialog.integrator)
        assert dialog.integrator.currentText() == "LoadControl"
        assert dialog.integrator.isEnabled()

        assert not _shown(dialog.control_node)
        assert not _shown(dialog.cyclic_targets)
        assert not _shown(dialog.dt)
        assert not _shown(dialog.modes)
        assert not _shown(dialog.preload_gravity)
        assert not _shown(dialog.cutback)
    finally:
        _close(dialog)


def test_modal_analysis_shows_only_modal_specific_solver_fields():
    dialog = AnalysisDialog(analysis_type="Modal")
    try:
        assert _shown(dialog.constraints)
        assert _shown(dialog.numberer)
        assert _shown(dialog.system)
        assert _shown(dialog.modes)
        assert _shown(dialog.eigen_solver)
        assert _shown(dialog.integrator)
        assert dialog.integrator.currentText() == "None"
        assert not dialog.integrator.isEnabled()

        assert not _shown(dialog.test)
        assert not _shown(dialog.steps)
        assert not _shown(dialog.load_inc)
        assert not _shown(dialog.recovery)
        assert not _shown(dialog.adaptive)
        assert not _shown(dialog.live_convergence)
    finally:
        _close(dialog)


def test_transient_and_adaptive_rows_expand_only_when_needed():
    dialog = AnalysisDialog(analysis_type="Transient")
    try:
        assert _shown(dialog.steps)
        assert _shown(dialog.dt)
        assert _shown(dialog.gamma)
        assert _shown(dialog.beta)
        assert _shown(dialog.damping_ratio)
        assert _shown(dialog.integrator)
        assert dialog.integrator.currentText() == "Newmark"
        assert dialog.integrator.isEnabled()
        assert _shown(dialog.gamma)
        assert _shown(dialog.beta)
        assert not _shown(dialog.hht_alpha)
        assert not _shown(dialog.generalized_alpha_m)
        assert not _shown(dialog.damping_mode_i)
        assert not _shown(dialog.damping_mode_j)

        dialog.damping_ratio.setValue(0.05)
        _APP.processEvents()
        assert _shown(dialog.damping_mode_i)
        assert _shown(dialog.damping_mode_j)

        assert _shown(dialog.adaptive)
        assert not _shown(dialog.cutback)
        dialog.adaptive.setChecked(True)
        _APP.processEvents()
        assert _shown(dialog.cutback)
        assert _shown(dialog.min_factor)
        assert _shown(dialog.growth)
        assert _shown(dialog.easy_iter)
        assert _shown(dialog.grow_after)

        assert _shown(dialog.preload_gravity)
        assert not _shown(dialog.gravity_steps)
        dialog.preload_gravity.setChecked(True)
        _APP.processEvents()
        assert _shown(dialog.gravity_steps)
    finally:
        _close(dialog)


def test_cyclic_protocol_hides_nominal_steps_and_uses_model_ndf():
    dialog = AnalysisDialog(analysis_type="Cyclic", ndf=2)
    try:
        assert _shown(dialog.control_node)
        assert _shown(dialog.control_dof)
        assert _shown(dialog.cyclic_targets)
        assert _shown(dialog.cyclic_inc)
        assert not _shown(dialog.steps)
        assert not _shown(dialog.disp_inc)
        assert _shown(dialog.integrator)
        assert dialog.integrator.currentText() == "DisplacementControl"
        assert not dialog.integrator.isEnabled()

        assert dialog.control_dof.count() == 2
        assert dialog.control_dof.itemData(0) == 1
        assert dialog.control_dof.itemData(1) == 2
    finally:
        _close(dialog)


def test_static_integrator_switches_parameter_rows():
    dialog = AnalysisDialog(analysis_type="Static")
    try:
        dialog.integrator.setCurrentText("DisplacementControl")
        _APP.processEvents()
        assert _shown(dialog.control_node)
        assert _shown(dialog.control_dof)
        assert _shown(dialog.disp_inc)
        assert not _shown(dialog.load_inc)
        assert not _shown(dialog.arc_length_s)

        dialog.integrator.setCurrentText("ArcLength")
        _APP.processEvents()
        assert _shown(dialog.arc_length_s)
        assert _shown(dialog.arc_length_alpha)
        assert not _shown(dialog.control_node)
        assert not _shown(dialog.load_inc)
    finally:
        _close(dialog)


def test_transient_integrator_switches_parameter_rows():
    dialog = AnalysisDialog(analysis_type="Transient")
    try:
        dialog.integrator.setCurrentText("HHT")
        _APP.processEvents()
        assert _shown(dialog.hht_alpha)
        assert not _shown(dialog.gamma)
        assert not _shown(dialog.beta)

        dialog.integrator.setCurrentText("GeneralizedAlpha")
        _APP.processEvents()
        assert _shown(dialog.generalized_alpha_m)
        assert _shown(dialog.generalized_alpha_f)
        assert not _shown(dialog.hht_alpha)
        assert not _shown(dialog.gamma)
    finally:
        _close(dialog)


def test_pushover_new_analysis_defaults_to_safe_auto_driving_load():
    dialog = AnalysisDialog(
        analysis_type="Pushover",
        plain_patterns={4: "Existing lateral"},
    )
    try:
        assert _shown(dialog.driver_mode)
        assert _shown(dialog.driver_distribution)
        assert not _shown(dialog.driver_pattern)
        assert not _shown(dialog.deferred_patterns)
        assert dialog.driver_mode.currentData() == "auto"
        assert dialog.driver_distribution.currentText() == "Triangular"
        assert dialog.data().deferred_pattern_tags == []
    finally:
        _close(dialog)


def test_cyclic_can_use_existing_plain_driving_pattern():
    dialog = AnalysisDialog(
        analysis_type="Cyclic",
        plain_patterns={7: "Cyclic reference"},
    )
    try:
        index = dialog.driver_mode.findData("existing")
        dialog.driver_mode.setCurrentIndex(index)
        _APP.processEvents()
        assert _shown(dialog.driver_pattern)
        assert not _shown(dialog.driver_distribution)
        pattern_index = dialog.driver_pattern.findData(7)
        dialog.driver_pattern.setCurrentIndex(pattern_index)
        assert dialog.data().deferred_pattern_tags == [7]
    finally:
        _close(dialog)


def test_cyclic_protocol_import_accepts_absolute_targets():
    dialog = AnalysisDialog(analysis_type="Cyclic")
    try:
        targets = dialog._apply_cyclic_protocol_text(
            "Target\n0.005\n-0.005\n0.01\n0\n",
            mode="targets",
        )
        assert targets == [0.005, -0.005, 0.01, 0.0]
        assert dialog.data().cyclic_targets == targets
    finally:
        _close(dialog)


def test_cyclic_protocol_import_expands_amplitude_cycle_rows():
    dialog = AnalysisDialog(analysis_type="Cyclic")
    try:
        targets = dialog._apply_cyclic_protocol_text(
            "Amplitude,Cycles\n0.005,1\n0.01,2\n",
            mode="amplitude_cycles",
        )
        assert targets == [
            0.005,
            -0.005,
            0.01,
            -0.01,
            0.01,
            -0.01,
            0.0,
        ]
        assert dialog.data().cyclic_targets == targets
    finally:
        _close(dialog)


def test_static_displacement_control_gets_fail_safe_driving_load_controls():
    dialog = AnalysisDialog(
        analysis_type="Static",
        plain_patterns={7: "Existing reference"},
    )
    try:
        dialog.integrator.setCurrentText("DisplacementControl")
        _APP.processEvents()

        assert _shown(dialog.driver_mode)
        assert _shown(dialog.driver_distribution)
        assert not _shown(dialog.driver_pattern)
        assert _shown(dialog.preload_gravity)
        assert dialog.driver_mode.currentData() == "auto"
        assert dialog.driver_distribution.currentText() == "Uniform"
        assert dialog.driving_load_config()["mode"] == "auto"
        assert dialog.data().deferred_pattern_tags == []

        dialog.driver_mode.setCurrentIndex(
            dialog.driver_mode.findData("existing")
        )
        _APP.processEvents()
        assert _shown(dialog.driver_pattern)
        assert not _shown(dialog.driver_distribution)
        assert dialog.data().deferred_pattern_tags == [7]
    finally:
        _close(dialog)


def test_hidden_gravity_preload_state_is_not_serialized_for_unsupported_analysis():
    dialog = AnalysisDialog(analysis_type="Transient")
    try:
        dialog.preload_gravity.setChecked(True)
        _APP.processEvents()
        assert _shown(dialog.preload_gravity)
        assert dialog.data().preload_gravity is True

        dialog.kind.setCurrentText("Static")
        _APP.processEvents()

        assert dialog.integrator.currentText() == "LoadControl"
        assert not _shown(dialog.preload_gravity)
        assert dialog.preload_gravity.isChecked()
        assert dialog.data().preload_gravity is False
    finally:
        _close(dialog)


def test_static_displacement_control_only_serializes_preload_while_supported():
    dialog = AnalysisDialog(analysis_type="Static")
    try:
        dialog.integrator.setCurrentText("DisplacementControl")
        dialog.preload_gravity.setChecked(True)
        _APP.processEvents()
        assert _shown(dialog.preload_gravity)
        assert dialog.data().preload_gravity is True

        dialog.integrator.setCurrentText("ArcLength")
        _APP.processEvents()

        assert not _shown(dialog.preload_gravity)
        assert dialog.preload_gravity.isChecked()
        assert dialog.data().preload_gravity is False
    finally:
        _close(dialog)


def test_cpu_execution_controls_enable_thread_count_only_for_multithread():
    dialog = AnalysisDialog(analysis_type="Static")
    try:
        assert dialog.execution_mode.currentText() == "Auto"
        assert not dialog.num_threads.isEnabled()

        dialog.execution_mode.setCurrentText("Multi-thread")
        _APP.processEvents()
        assert dialog.num_threads.isEnabled()
        dialog.num_threads.setValue(4)
        data = dialog.data()
        assert data.execution_mode == "Multi-thread"
        assert data.num_threads == 4

        dialog.execution_mode.setCurrentText("Single Thread")
        _APP.processEvents()
        assert not dialog.num_threads.isEnabled()
        assert dialog.num_threads.value() == 1
        data = dialog.data()
        assert data.execution_mode == "Single Thread"
        assert data.num_threads == 1

        dialog.execution_mode.setCurrentText("Multi-thread")
        _APP.processEvents()
        assert dialog.num_threads.isEnabled()
        assert dialog.num_threads.value() == 4
    finally:
        _close(dialog)
