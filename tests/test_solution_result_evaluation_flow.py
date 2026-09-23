from __future__ import annotations

import inspect

from openseespy_studio.ui.main_window import MainWindow, PropertiesPanel


def test_insert_auto_displays_only_when_current_job_is_ready():
    source = inspect.getsource(MainWindow._insert_solution_result)
    assert 'status.code == "up_to_date"' in source
    assert "_evaluate_solution_result(result.tag)" in source
    assert "_offer_result_analysis_run" not in source


def test_evaluate_does_not_run_solver_implicitly():
    source = inspect.getsource(MainWindow._evaluate_solution_result)
    assert 'status.code != "up_to_date"' in source
    assert "_run_analysis_from_tree" not in source
    assert "_offer_result_analysis_run" not in source


def test_result_details_expose_status_and_evaluate_gate():
    source = inspect.getsource(PropertiesPanel.set_solution_result)
    assert "status_text" in source
    assert "status_tooltip" in source
    assert "can_evaluate" in source
    assert "result_evaluate_button.setEnabled" in source
