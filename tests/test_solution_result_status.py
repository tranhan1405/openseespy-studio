from openseespy_studio.solution_status import (
    classify_solution_result_status,
    solver_input_signature,
)


def _project_payload():
    return {
        "name": "Demo",
        "units": {"length": "m"},
        "model": {"nodes": [{"tag": 1, "coords": [0.0, 0.0]}]},
        "materials": [{"tag": 1, "type": "Elastic", "E": 1.0}],
        "analyses": [
            {"tag": 1, "type": "Static", "steps": 10},
            {"tag": 2, "type": "Transient", "steps": 20},
        ],
        "recorders": [],
        "solution_results": [],
        "selection_sets": [],
        "active_analysis_tag": 1,
    }


def test_solver_signature_ignores_result_and_recorder_views():
    base = _project_payload()
    signature = solver_input_signature(base, analysis_tag=1)

    changed = _project_payload()
    changed["solution_results"] = [{"tag": 4, "result_type": "DeformedShape"}]
    changed["recorders"] = [{"tag": 8, "response": "disp"}]
    changed["active_analysis_tag"] = 2
    changed["selection_sets"] = [{"name": "display-only"}]

    assert solver_input_signature(changed, analysis_tag=1) == signature


def test_solver_signature_changes_for_model_or_target_analysis():
    base = _project_payload()
    signature = solver_input_signature(base, analysis_tag=1)

    model_changed = _project_payload()
    model_changed["model"]["nodes"][0]["coords"][0] = 1.0
    assert solver_input_signature(model_changed, analysis_tag=1) != signature

    analysis_changed = _project_payload()
    analysis_changed["analyses"][0]["steps"] = 11
    assert solver_input_signature(analysis_changed, analysis_tag=1) != signature

    other_analysis_changed = _project_payload()
    other_analysis_changed["analyses"][1]["steps"] = 99
    assert solver_input_signature(other_analysis_changed, analysis_tag=1) == signature


def test_solution_result_status_lifecycle():
    status = classify_solution_result_status(has_job=False)
    assert status.code == "needs_evaluation"
    assert status.symbol == "⚡"

    status = classify_solution_result_status(
        has_job=True,
        job_status="Running",
        has_results=False,
    )
    assert status.code == "needs_evaluation"

    status = classify_solution_result_status(
        has_job=True,
        job_status="Failed",
        has_results=False,
    )
    assert status.code == "unavailable"
    assert status.symbol == "!"

    status = classify_solution_result_status(
        has_job=True,
        job_status="Completed",
        has_results=True,
        job_signature="old",
        current_signature="new",
    )
    assert status.code == "stale"
    assert status.symbol == "↻"

    status = classify_solution_result_status(
        has_job=True,
        job_status="Completed",
        has_results=True,
        job_signature="same",
        current_signature="same",
    )
    assert status.code == "up_to_date"
    assert status.symbol == "✓"
