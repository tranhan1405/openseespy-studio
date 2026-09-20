from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback
from typing import Any

from .calibration import CalibrationWeights, rank_calibration_cases, score_cyclic_calibration


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


def run_plan(plan_path: Path, result_path: Path) -> int:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        error = traceback.format_exc()
        _write_payload(
            result_path,
            {"status": "failed", "error": error, "cases": []},
        )
        return 2

    cases = plan.get("cases", [])
    experiment = plan.get("experiment", {})
    weights_raw = plan.get("weights", {})
    if not isinstance(cases, list) or not cases:
        _write_payload(
            result_path,
            {
                "status": "failed",
                "error": "Calibration plan contains no cases.",
                "cases": [],
            },
        )
        return 2

    x = list(experiment.get("x", []))
    y = list(experiment.get("y", []))
    weights = CalibrationWeights(
        peak_force=float(weights_raw.get("peak_force", 1.0)),
        reversal_nrmse=float(weights_raw.get("reversal_nrmse", 1.0)),
        cycle_energy=float(weights_raw.get("cycle_energy", 1.0)),
        max_displacement=float(weights_raw.get("max_displacement", 0.0)),
    )

    completed: list[dict[str, Any]] = []
    total = len(cases)
    _emit({"event": "start", "total": total})

    for index, case in enumerate(cases, start=1):
        case_id = int(case.get("case_id", index))
        values = dict(case.get("values", {}))
        script = str(case.get("script", ""))
        _emit(
            {
                "event": "case_start",
                "case_id": case_id,
                "current": index,
                "total": total,
                "values": values,
            }
        )

        namespace: dict[str, Any] = {
            "__name__": "__main__",
            "__file__": f"<calibration-case-{case_id}>",
            "__package__": None,
        }
        try:
            code = compile(
                script,
                f"<calibration-case-{case_id}>",
                "exec",
            )
            exec(code, namespace)
            result = namespace.get("_studio_results", {})
            if not isinstance(result, dict):
                result = {}
            scored = score_cyclic_calibration(
                result,
                x,
                y,
                weights=weights,
            )
            row = {
                "case_id": case_id,
                "values": values,
                "status": "completed",
                "error": "",
                "result": result,
                **scored,
            }
        except BaseException:
            error = traceback.format_exc()
            row = {
                "case_id": case_id,
                "values": values,
                "status": "failed",
                "error": error,
                "result": {},
                "score": None,
                "components": {},
                "comparison": {},
            }

        completed.append(row)
        _emit(
            {
                "event": "case_finish",
                "case_id": case_id,
                "current": index,
                "total": total,
                "status": row["status"],
                "score": row.get("score"),
            }
        )

    ranked = rank_calibration_cases(completed)
    payload = {
        "status": "completed",
        "error": "",
        "cases": ranked,
        "case_count": total,
    }
    _write_payload(result_path, payload)
    _emit({"event": "finish", "total": total})
    return 0


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
