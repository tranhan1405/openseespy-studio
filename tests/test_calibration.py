from __future__ import annotations

import json

import pytest

from openseespy_studio.calibration import (
    CalibrationCase,
    CalibrationParameter,
    CalibrationWeights,
    apply_calibration_case,
    build_grid_cases,
    calibration_case_changes,
    rank_calibration_cases,
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
