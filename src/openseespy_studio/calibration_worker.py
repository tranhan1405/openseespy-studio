from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import traceback
from typing import Any

from .calibration import (
    CalibrationCase,
    CalibrationWeights,
    build_grid_cases,
    calibration_case_script,
    calibration_grid_size,
    calibration_parameters_from_payload,
    calibration_parameter_payload,
    rank_calibration_cases,
    refine_calibration_parameters,
    score_cyclic_calibration,
)
from .project import ProjectDatabase


EVENT_PREFIX = "@@STUDIO_CALIBRATION@@"


def _emit(payload: dict[str, Any]) -> None:
    print(
        EVENT_PREFIX + json.dumps(payload, ensure_ascii=False),
        flush=True,
    )


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _weights(raw: Any) -> CalibrationWeights:
    data = raw if isinstance(raw, dict) else {}
    return CalibrationWeights(
        peak_force=float(data.get("peak_force", 1.0)),
        reversal_nrmse=float(data.get("reversal_nrmse", 1.0)),
        cycle_energy=float(data.get("cycle_energy", 1.0)),
        max_displacement=float(data.get("max_displacement", 0.0)),
    )


def _case_signature(values: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple(
        sorted(
            (str(key), round(float(value), 14))
            for key, value in values.items()
        )
    )


def _best_scored_case(
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = math.inf
    for row in rows:
        score = row.get("score")
        try:
            numeric = float(score)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        if numeric < best_score:
            best = row
            best_score = numeric
    return best


def _execute_case(
    *,
    case: CalibrationCase,
    script: str,
    round_index: int,
    round_case: int,
    current: int,
    total: int,
    experiment_x: list[float],
    experiment_y: list[float],
    weights: CalibrationWeights,
) -> dict[str, Any]:
    values = dict(case.values)
    _emit(
        {
            "event": "case_start",
            "case_id": case.case_id,
            "round": round_index,
            "round_case": round_case,
            "current": current,
            "total": total,
            "values": values,
        }
    )

    namespace: dict[str, Any] = {
        "__name__": "__main__",
        "__file__": f"<calibration-case-{case.case_id}>",
        "__package__": None,
    }
    try:
        code = compile(
            script,
            f"<calibration-case-{case.case_id}>",
            "exec",
        )
        exec(code, namespace)
        result = namespace.get("_studio_results", {})
        if not isinstance(result, dict):
            result = {}
        scored = score_cyclic_calibration(
            result,
            experiment_x,
            experiment_y,
            weights=weights,
        )
        row = {
            "case_id": case.case_id,
            "round": int(round_index),
            "round_case": int(round_case),
            "values": values,
            "execution_status": "completed",
            "error": "",
            "result": result,
            **scored,
        }
    except BaseException:
        error = traceback.format_exc()
        row = {
            "case_id": case.case_id,
            "round": int(round_index),
            "round_case": int(round_case),
            "values": values,
            "execution_status": "failed",
            "error": error,
            "result": {},
            "score": None,
            "status": "unavailable",
            "reason": "Solver execution failed.",
            "components": {},
            "comparison": {},
        }

    _emit(
        {
            "event": "case_finish",
            "case_id": case.case_id,
            "round": round_index,
            "round_case": round_case,
            "current": current,
            "total": total,
            "status": row.get("execution_status", "failed"),
            "score": row.get("score"),
        }
    )
    return row


def _run_grid(
    plan: dict[str, Any],
    *,
    experiment_x: list[float],
    experiment_y: list[float],
    weights: CalibrationWeights,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases = plan.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("Calibration plan contains no cases.")

    total = len(cases)
    _emit(
        {
            "event": "start",
            "strategy": "grid",
            "total": total,
            "rounds": 1,
        }
    )
    completed: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases, start=1):
        if not isinstance(raw_case, dict):
            continue
        case = CalibrationCase(
            case_id=int(raw_case.get("case_id", index)),
            values={
                str(key): float(value)
                for key, value in dict(
                    raw_case.get("values", {})
                ).items()
            },
        )
        completed.append(
            _execute_case(
                case=case,
                script=str(raw_case.get("script", "")),
                round_index=1,
                round_case=index,
                current=index,
                total=total,
                experiment_x=experiment_x,
                experiment_y=experiment_y,
                weights=weights,
            )
        )
    return completed, {
        "strategy": "grid",
        "rounds_completed": 1,
        "planned_case_count": total,
        "stop_reason": "",
    }


def _run_adaptive(
    plan: dict[str, Any],
    *,
    experiment_x: list[float],
    experiment_y: list[float],
    weights: CalibrationWeights,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    project_raw = plan.get("project")
    if not isinstance(project_raw, dict):
        raise ValueError(
            "Adaptive calibration plan is missing the project snapshot."
        )
    project = ProjectDatabase.from_dict(project_raw)
    parameters = calibration_parameters_from_payload(
        plan.get("parameters")
    )
    rounds = max(1, int(plan.get("rounds", 3)))
    shrink_ratio = float(plan.get("shrink_ratio", 0.5))
    if rounds > 6:
        raise ValueError("Adaptive calibration supports at most 6 rounds.")
    if not (0.0 < shrink_ratio < 1.0):
        raise ValueError(
            "Adaptive shrink ratio must be greater than 0 and less than 1."
        )

    per_round = calibration_grid_size(parameters)
    planned_total = per_round * rounds
    max_total = int(plan.get("max_total_cases", 96))
    if planned_total > max_total:
        raise ValueError(
            f"Adaptive plan can create up to {planned_total} cases, "
            f"exceeding the limit of {max_total}."
        )

    _emit(
        {
            "event": "start",
            "strategy": "adaptive",
            "total": planned_total,
            "rounds": rounds,
            "shrink_ratio": shrink_ratio,
        }
    )

    completed: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, float], ...]] = set()
    current_parameters = list(parameters)
    next_case_id = 1
    executed = 0
    rounds_completed = 0
    stop_reason = ""

    for round_index in range(1, rounds + 1):
        _emit(
            {
                "event": "round_start",
                "round": round_index,
                "rounds": rounds,
                "bounds": calibration_parameter_payload(
                    current_parameters
                ),
            }
        )

        candidates = build_grid_cases(
            current_parameters,
            max_cases=max_total,
            start_case_id=1,
        )
        round_executed = 0
        for candidate in candidates:
            signature = _case_signature(candidate.values)
            if signature in seen:
                continue
            seen.add(signature)
            case = CalibrationCase(
                case_id=next_case_id,
                values=dict(candidate.values),
            )
            next_case_id += 1
            executed += 1
            round_executed += 1
            script = calibration_case_script(project, case)
            completed.append(
                _execute_case(
                    case=case,
                    script=script,
                    round_index=round_index,
                    round_case=round_executed,
                    current=executed,
                    total=planned_total,
                    experiment_x=experiment_x,
                    experiment_y=experiment_y,
                    weights=weights,
                )
            )

        rounds_completed = round_index
        best = _best_scored_case(completed)
        _emit(
            {
                "event": "round_finish",
                "round": round_index,
                "rounds": rounds,
                "executed": round_executed,
                "best_case_id": (
                    int(best["case_id"])
                    if best is not None
                    else None
                ),
                "best_score": (
                    float(best["score"])
                    if best is not None
                    else None
                ),
            }
        )

        if best is None:
            stop_reason = (
                "No scored case was available to define the next "
                "adaptive refinement window."
            )
            break
        if round_index >= rounds:
            break
        if round_executed == 0:
            stop_reason = (
                "No new unique cases remained in the refinement window."
            )
            break

        best_values = best.get("values", {})
        if not isinstance(best_values, dict):
            stop_reason = "Best case did not contain parameter values."
            break
        current_parameters = refine_calibration_parameters(
            current_parameters,
            {
                str(key): float(value)
                for key, value in best_values.items()
            },
            shrink_ratio=shrink_ratio,
        )

    return completed, {
        "strategy": "adaptive",
        "rounds_completed": rounds_completed,
        "planned_case_count": planned_total,
        "stop_reason": stop_reason,
        "shrink_ratio": shrink_ratio,
    }


def run_plan(plan_path: Path, result_path: Path) -> int:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise ValueError("Calibration plan must be a JSON object.")

        experiment = plan.get("experiment", {})
        if not isinstance(experiment, dict):
            raise ValueError("Calibration experiment must be an object.")
        experiment_x = [
            float(value)
            for value in experiment.get("x", [])
        ]
        experiment_y = [
            float(value)
            for value in experiment.get("y", [])
        ]
        weights = _weights(plan.get("weights", {}))
        weights.normalized()

        strategy = str(plan.get("strategy", "grid")).strip().lower()
        if strategy == "adaptive":
            completed, metadata = _run_adaptive(
                plan,
                experiment_x=experiment_x,
                experiment_y=experiment_y,
                weights=weights,
            )
        elif strategy == "grid":
            completed, metadata = _run_grid(
                plan,
                experiment_x=experiment_x,
                experiment_y=experiment_y,
                weights=weights,
            )
        else:
            raise ValueError(
                f"Unsupported calibration strategy: {strategy}"
            )

        ranked = rank_calibration_cases(completed)
        payload = {
            "status": "completed",
            "error": "",
            "cases": ranked,
            "case_count": len(completed),
            **metadata,
        }
        _write_payload(result_path, payload)
        _emit(
            {
                "event": "finish",
                "strategy": metadata.get("strategy", strategy),
                "total": len(completed),
                "rounds_completed": metadata.get(
                    "rounds_completed",
                    1,
                ),
                "stop_reason": metadata.get("stop_reason", ""),
            }
        )
        return 0
    except BaseException:
        error = traceback.format_exc()
        _write_payload(
            result_path,
            {
                "status": "failed",
                "error": error,
                "cases": [],
            },
        )
        _emit(
            {
                "event": "failed",
                "error": error.splitlines()[-1] if error else "Unknown error",
            }
        )
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OpenSeesPy Studio calibration worker"
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("--result-file", type=Path, required=True)
    args = parser.parse_args()
    return run_plan(args.plan, args.result_file)


if __name__ == "__main__":
    raise SystemExit(main())
