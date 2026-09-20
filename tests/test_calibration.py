from __future__ import annotations

import json

import pytest

from openseespy_studio.calibration import (
    CalibrationCase,
    CalibrationParameter,
    CalibrationWeights,
    apply_calibration_case,
    build_grid_cases,
    calibration_active_objectives,
    calibration_available_objectives,
    calibration_best_score_history,
    calibration_case_changes,
    calibration_grid_size,
    calibration_objective_label,
    calibration_parameter_keys,
    calibration_pareto_projection,
    calibration_parameter_label,
    calibration_round_best_parameter_series,
    calibration_parameter_payload,
    pareto_rank_calibration_cases,
    rank_calibration_cases,
    refine_calibration_parameters,
    score_cyclic_calibration,
)
from openseespy_studio.calibration_worker import run_plan
from openseespy_studio.project import MaterialData, ProjectDatabase


def _cyclic_result(force_scale: float = 1.0):
    displacement = [2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    force = [
        20.0 * force_scale,
        0.0,
        -18.0 * force_scale,
        0.0,
        16.0 * force_scale,
        0.0,
    ]
    return {
        "analysis": {
            "type": "Cyclic",
            "control_node": 2,
            "control_dof": 1,
        },
        "history": {
            "control_dof": 1,
            "displacement": [
                [value, 0.0, 0.0, 0.0, 0.0, 0.0]
                for value in displacement
            ],
            "base_shear": [-value for value in force],
        },
    }


def test_grid_cases_are_cartesian_and_parameter_keys_are_stable():
    cases = build_grid_cases(
        [
            CalibrationParameter(1, "fpc", -36.0, -24.0, 3),
            CalibrationParameter(2, "Fy", 400.0, 500.0, 2),
        ],
        max_cases=10,
    )

    assert len(cases) == 6
    assert cases[0].values == {
        "material:1:fpc": pytest.approx(-36.0),
        "material:2:Fy": pytest.approx(400.0),
    }
    assert cases[-1].values == {
        "material:1:fpc": pytest.approx(-24.0),
        "material:2:Fy": pytest.approx(500.0),
    }


def test_grid_case_limit_prevents_accidental_large_batch():
    with pytest.raises(ValueError, match="exceeding"):
        build_grid_cases(
            [
                CalibrationParameter(1, "fpc", -40.0, -20.0, 5),
                CalibrationParameter(2, "Fy", 400.0, 600.0, 5),
            ],
            max_cases=20,
        )


def test_apply_calibration_case_clones_project_without_mutating_baseline():
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            tag=1,
            name="Concrete",
            material_type="Concrete02",
            parameters={"fpc": -30.0},
        )
    )
    case = CalibrationCase(
        case_id=1,
        values={
            "material:1:fpc": -36.0,
            "material:1:epsc0": -0.0025,
        },
    )

    calibrated = apply_calibration_case(project, case)

    assert project.materials[1].parameters["fpc"] == pytest.approx(-30.0)
    assert calibrated.materials[1].parameters["fpc"] == pytest.approx(-36.0)
    assert calibrated.materials[1].parameters["epsc0"] == pytest.approx(
        -0.0025
    )


def test_cyclic_calibration_score_combines_available_percentage_errors():
    experiment_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    experiment_y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0]

    exact = score_cyclic_calibration(
        _cyclic_result(1.0),
        experiment_x,
        experiment_y,
        weights=CalibrationWeights(
            peak_force=1.0,
            reversal_nrmse=1.0,
            cycle_energy=0.0,
            max_displacement=0.0,
        ),
    )
    weaker = score_cyclic_calibration(
        _cyclic_result(0.8),
        experiment_x,
        experiment_y,
        weights=CalibrationWeights(
            peak_force=1.0,
            reversal_nrmse=1.0,
            cycle_energy=0.0,
            max_displacement=0.0,
        ),
    )

    assert exact["status"] == "ok"
    assert exact["score"] == pytest.approx(0.0)
    assert weaker["score"] is not None
    assert weaker["score"] > exact["score"]


def test_rank_calibration_cases_places_unavailable_cases_last():
    ranked = rank_calibration_cases(
        [
            {"case_id": 1, "score": 12.0},
            {"case_id": 2, "score": None},
            {"case_id": 3, "score": 4.0},
        ]
    )

    assert [row["case_id"] for row in ranked] == [3, 1, 2]
    assert [row["rank"] for row in ranked] == [1, 2, None]


def test_calibration_worker_isolates_failed_cases_and_ranks_successes(tmp_path):
    experiment_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    experiment_y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0]

    exact = repr(_cyclic_result(1.0))
    weak = repr(_cyclic_result(0.8))
    plan = {
        "experiment": {
            "x": experiment_x,
            "y": experiment_y,
        },
        "weights": {
            "peak_force": 1.0,
            "reversal_nrmse": 1.0,
            "cycle_energy": 0.0,
            "max_displacement": 0.0,
        },
        "cases": [
            {
                "case_id": 1,
                "values": {"material:1:Fy": 500.0},
                "script": f"_studio_results = {exact}",
            },
            {
                "case_id": 2,
                "values": {"material:1:Fy": 400.0},
                "script": f"_studio_results = {weak}",
            },
            {
                "case_id": 3,
                "values": {"material:1:Fy": 300.0},
                "script": "raise RuntimeError('case failure')",
            },
        ],
    }
    plan_path = tmp_path / "plan.json"
    result_path = tmp_path / "result.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    exit_code = run_plan(plan_path, result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert len(payload["cases"]) == 3
    assert payload["cases"][0]["case_id"] == 1
    assert payload["cases"][0]["rank"] == 1
    failed = next(
        row for row in payload["cases"]
        if row["case_id"] == 3
    )
    assert failed["execution_status"] == "failed"
    assert failed["rank"] is None



def test_calibration_case_changes_reports_current_and_new_values():
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            tag=1,
            name="Concrete",
            material_type="Concrete02",
            parameters={"fpc": -30.0, "epsc0": -0.002},
        )
    )
    case = CalibrationCase(
        case_id=7,
        values={
            "material:1:fpc": -33.0,
            "material:1:epsc0": -0.002,
        },
    )

    changes = calibration_case_changes(project, case)

    assert len(changes) == 2
    fpc = next(item for item in changes if item["parameter"] == "fpc")
    epsc0 = next(
        item for item in changes if item["parameter"] == "epsc0"
    )
    assert fpc["material_name"] == "Concrete"
    assert fpc["old_value"] == pytest.approx(-30.0)
    assert fpc["new_value"] == pytest.approx(-33.0)
    assert fpc["changed"] is True
    assert epsc0["changed"] is False


def test_calibration_case_changes_rejects_case_after_material_schema_changed():
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            tag=1,
            name="Elastic",
            material_type="Elastic",
            parameters={"E": 200.0},
        )
    )
    case = CalibrationCase(
        case_id=3,
        values={"material:1:Fy": 500.0},
    )

    with pytest.raises(ValueError, match="no longer has parameter"):
        calibration_case_changes(project, case)



def test_refine_calibration_parameters_centers_and_clips_window():
    parameters = [
        CalibrationParameter(
            material_tag=1,
            parameter="Fy",
            minimum=400.0,
            maximum=600.0,
            points=3,
        )
    ]

    centered = refine_calibration_parameters(
        parameters,
        {"material:1:Fy": 500.0},
        shrink_ratio=0.5,
    )
    assert centered[0].minimum == pytest.approx(450.0)
    assert centered[0].maximum == pytest.approx(550.0)

    edge = refine_calibration_parameters(
        parameters,
        {"material:1:Fy": 600.0},
        shrink_ratio=0.5,
    )
    assert edge[0].minimum == pytest.approx(500.0)
    assert edge[0].maximum == pytest.approx(600.0)


def test_adaptive_grid_budget_uses_points_per_round():
    parameters = [
        CalibrationParameter(1, "fpc", -36.0, -24.0, 3),
        CalibrationParameter(2, "Fy", 450.0, 550.0, 3),
    ]

    assert calibration_grid_size(parameters) == 9
    payload = calibration_parameter_payload(parameters)
    assert payload[0]["material_tag"] == 1
    assert payload[1]["points"] == 3


def test_calibration_worker_adaptive_refines_around_best_case(
    tmp_path,
    monkeypatch,
):
    from openseespy_studio import calibration_worker

    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            tag=1,
            name="Elastic",
            material_type="Elastic",
            parameters={"E": 1.0},
        )
    )

    def fake_case_script(_project, case):
        scale = float(case.values["material:1:E"])
        return f"_studio_results = {repr(_cyclic_result(scale))}"

    monkeypatch.setattr(
        calibration_worker,
        "calibration_case_script",
        fake_case_script,
    )

    experiment_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    experiment_y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0]
    plan = {
        "strategy": "adaptive",
        "project": project.to_dict(),
        "parameters": [
            {
                "material_tag": 1,
                "parameter": "E",
                "minimum": 0.6,
                "maximum": 1.0,
                "points": 3,
            }
        ],
        "rounds": 3,
        "shrink_ratio": 0.5,
        "max_total_cases": 96,
        "experiment": {
            "x": experiment_x,
            "y": experiment_y,
        },
        "weights": {
            "peak_force": 1.0,
            "reversal_nrmse": 1.0,
            "cycle_energy": 0.0,
            "max_displacement": 0.0,
        },
    }
    plan_path = tmp_path / "adaptive-plan.json"
    result_path = tmp_path / "adaptive-result.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    exit_code = calibration_worker.run_plan(
        plan_path,
        result_path,
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["strategy"] == "adaptive"
    assert payload["rounds_completed"] == 3
    assert payload["planned_case_count"] == 9
    # The best center value from earlier rounds is not re-run.
    assert payload["case_count"] < payload["planned_case_count"]
    assert max(row["round"] for row in payload["cases"]) == 3
    assert payload["cases"][0]["rank"] == 1
    assert payload["cases"][0]["values"]["material:1:E"] == pytest.approx(
        1.0
    )
    assert payload["cases"][0]["score"] == pytest.approx(0.0)



def test_calibration_best_score_history_uses_execution_order_and_holds_best():
    rows = [
        {
            "case_id": 4,
            "round": 2,
            "score": 5.0,
            "values": {"material:1:Fy": 520.0},
        },
        {
            "case_id": 1,
            "round": 1,
            "score": None,
            "values": {"material:1:Fy": 450.0},
        },
        {
            "case_id": 3,
            "round": 1,
            "score": 8.0,
            "values": {"material:1:Fy": 500.0},
        },
        {
            "case_id": 2,
            "round": 1,
            "score": 10.0,
            "values": {"material:1:Fy": 475.0},
        },
        {
            "case_id": 5,
            "round": 2,
            "score": 6.0,
            "values": {"material:1:Fy": 540.0},
        },
    ]

    history = calibration_best_score_history(rows)

    assert history["cumulative_analyses"] == pytest.approx(
        [2.0, 3.0, 4.0, 5.0]
    )
    assert history["best_score"] == pytest.approx(
        [10.0, 8.0, 5.0, 5.0]
    )
    assert history["case_ids"] == [2, 3, 4, 5]


def test_round_best_parameter_series_tracks_best_case_in_each_round():
    rows = [
        {
            "case_id": 1,
            "round": 1,
            "score": 10.0,
            "values": {
                "material:1:Fy": 450.0,
                "material:2:fpc": -30.0,
            },
        },
        {
            "case_id": 2,
            "round": 1,
            "score": 7.0,
            "values": {
                "material:1:Fy": 500.0,
                "material:2:fpc": -32.0,
            },
        },
        {
            "case_id": 3,
            "round": 2,
            "score": 5.0,
            "values": {
                "material:1:Fy": 525.0,
                "material:2:fpc": -33.0,
            },
        },
        {
            "case_id": 4,
            "round": 2,
            "score": 6.0,
            "values": {
                "material:1:Fy": 550.0,
                "material:2:fpc": -34.0,
            },
        },
        {
            "case_id": 5,
            "round": 3,
            "score": None,
            "values": {
                "material:1:Fy": 537.5,
                "material:2:fpc": -33.5,
            },
        },
        {
            "case_id": 6,
            "round": 3,
            "score": 4.0,
            "values": {
                "material:1:Fy": 531.25,
                "material:2:fpc": -33.25,
            },
        },
    ]

    assert calibration_parameter_keys(rows) == [
        "material:1:Fy",
        "material:2:fpc",
    ]
    assert calibration_parameter_label("material:1:Fy") == "M1.Fy"

    series = calibration_round_best_parameter_series(
        rows,
        "material:1:Fy",
    )

    assert series["rounds"] == pytest.approx([1.0, 2.0, 3.0])
    assert series["values"] == pytest.approx(
        [500.0, 525.0, 531.25]
    )
    assert series["scores"] == pytest.approx([7.0, 5.0, 4.0])
    assert series["case_ids"] == [2, 3, 6]



def test_pareto_rank_calibration_cases_finds_non_dominated_fronts():
    rows = [
        {
            "case_id": 1,
            "components": {
                "peak_force": 3.0,
                "reversal_nrmse": 8.0,
                "cycle_energy": 7.0,
            },
        },
        {
            "case_id": 2,
            "components": {
                "peak_force": 5.0,
                "reversal_nrmse": 5.0,
                "cycle_energy": 5.0,
            },
        },
        {
            "case_id": 3,
            "components": {
                "peak_force": 8.0,
                "reversal_nrmse": 3.0,
                "cycle_energy": 4.0,
            },
        },
        {
            "case_id": 4,
            "components": {
                "peak_force": 9.0,
                "reversal_nrmse": 9.0,
                "cycle_energy": 9.0,
            },
        },
        {
            "case_id": 5,
            "components": {
                "peak_force": 2.0,
                "reversal_nrmse": None,
                "cycle_energy": 2.0,
            },
        },
    ]

    ranked = pareto_rank_calibration_cases(
        rows,
        ["peak_force", "reversal_nrmse", "cycle_energy"],
    )
    by_case = {row["case_id"]: row for row in ranked}

    assert by_case[1]["pareto_rank"] == 1
    assert by_case[2]["pareto_rank"] == 1
    assert by_case[3]["pareto_rank"] == 1
    assert by_case[4]["pareto_rank"] == 2
    assert by_case[5]["pareto_rank"] is None
    assert by_case[5]["pareto_eligible"] is False
    assert by_case[1]["pareto_front"] is True


def test_pareto_active_objectives_follow_positive_weights():
    weights = CalibrationWeights(
        peak_force=1.0,
        reversal_nrmse=0.0,
        cycle_energy=2.0,
        max_displacement=0.0,
    )

    assert calibration_active_objectives(weights) == [
        "peak_force",
        "cycle_energy",
    ]
    assert calibration_objective_label("peak_force").startswith("Peak")


def test_pareto_projection_marks_selected_axis_front_independently():
    rows = pareto_rank_calibration_cases(
        [
            {
                "case_id": 1,
                "components": {
                    "peak_force": 2.0,
                    "reversal_nrmse": 9.0,
                    "cycle_energy": 7.0,
                },
            },
            {
                "case_id": 2,
                "components": {
                    "peak_force": 4.0,
                    "reversal_nrmse": 4.0,
                    "cycle_energy": 4.0,
                },
            },
            {
                "case_id": 3,
                "components": {
                    "peak_force": 7.0,
                    "reversal_nrmse": 2.0,
                    "cycle_energy": 3.0,
                },
            },
            {
                "case_id": 4,
                "components": {
                    "peak_force": 8.0,
                    "reversal_nrmse": 8.0,
                    "cycle_energy": 8.0,
                },
            },
        ],
        ["peak_force", "reversal_nrmse", "cycle_energy"],
    )

    assert calibration_available_objectives(rows) == [
        "peak_force",
        "reversal_nrmse",
        "cycle_energy",
    ]
    points = calibration_pareto_projection(
        rows,
        "peak_force",
        "cycle_energy",
    )
    by_case = {point["case_id"]: point for point in points}

    assert by_case[1]["projection_front"] is True
    assert by_case[2]["projection_front"] is True
    assert by_case[3]["projection_front"] is True
    assert by_case[4]["projection_front"] is False
    assert by_case[4]["global_pareto_front"] is False


def test_calibration_worker_adds_pareto_metadata(tmp_path):
    experiment_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    experiment_y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0]
    plan = {
        "strategy": "grid",
        "experiment": {"x": experiment_x, "y": experiment_y},
        "weights": {
            "peak_force": 1.0,
            "reversal_nrmse": 1.0,
            "cycle_energy": 0.0,
            "max_displacement": 0.0,
        },
        "cases": [
            {
                "case_id": 1,
                "values": {"material:1:E": 1.0},
                "script": f"_studio_results = {repr(_cyclic_result(1.0))}",
            },
            {
                "case_id": 2,
                "values": {"material:1:E": 0.8},
                "script": f"_studio_results = {repr(_cyclic_result(0.8))}",
            },
        ],
    }
    plan_path = tmp_path / "pareto-plan.json"
    result_path = tmp_path / "pareto-result.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    exit_code = run_plan(plan_path, result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["pareto_objectives"] == [
        "peak_force",
        "reversal_nrmse",
    ]
    assert payload["pareto_front_count"] == 1
    assert payload["cases"][0]["case_id"] == 1
    assert payload["cases"][0]["pareto_rank"] == 1
    assert payload["cases"][0]["pareto_front"] is True
    assert payload["cases"][1]["pareto_rank"] == 2
