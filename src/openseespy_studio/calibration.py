from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
import math
from typing import Any, Sequence

from .generator import to_openseespy
from .postprocess import cyclic_curve_comparison
from .project import ProjectDatabase


@dataclass(frozen=True, slots=True)
class CalibrationParameter:
    material_tag: int
    parameter: str
    minimum: float
    maximum: float
    points: int = 3

    def values(self) -> list[float]:
        points = max(1, int(self.points))
        minimum = float(self.minimum)
        maximum = float(self.maximum)
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError("Calibration parameter bounds must be finite.")
        if points == 1:
            return [minimum]
        step = (maximum - minimum) / float(points - 1)
        return [minimum + step * index for index in range(points)]


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    case_id: int
    values: dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        if not self.values:
            return f"Case {self.case_id}"
        parts = [
            f"{key}={value:.6g}"
            for key, value in sorted(self.values.items())
        ]
        return f"Case {self.case_id}: " + ", ".join(parts)


@dataclass(frozen=True, slots=True)
class CalibrationWeights:
    peak_force: float = 1.0
    reversal_nrmse: float = 1.0
    cycle_energy: float = 1.0
    max_displacement: float = 0.0

    def normalized(self) -> dict[str, float]:
        raw = {
            "peak_force": max(0.0, float(self.peak_force)),
            "reversal_nrmse": max(0.0, float(self.reversal_nrmse)),
            "cycle_energy": max(0.0, float(self.cycle_energy)),
            "max_displacement": max(0.0, float(self.max_displacement)),
        }
        total = sum(raw.values())
        if total <= 0.0:
            raise ValueError(
                "At least one calibration objective weight must be positive."
            )
        return {key: value / total for key, value in raw.items()}


def parameter_key(material_tag: int, parameter: str) -> str:
    return f"material:{int(material_tag)}:{str(parameter)}"


def build_grid_cases(
    parameters: Sequence[CalibrationParameter],
    *,
    max_cases: int = 500,
) -> list[CalibrationCase]:
    specs = list(parameters)
    if not specs:
        raise ValueError("Select at least one calibration parameter.")
    if max_cases <= 0:
        raise ValueError("Maximum case count must be positive.")

    keys: list[str] = []
    value_sets: list[list[float]] = []
    seen: set[str] = set()
    for spec in specs:
        key = parameter_key(spec.material_tag, spec.parameter)
        if key in seen:
            raise ValueError(f"Duplicate calibration parameter: {key}")
        seen.add(key)
        values = spec.values()
        keys.append(key)
        value_sets.append(values)

    case_count = math.prod(len(values) for values in value_sets)
    if case_count > int(max_cases):
        raise ValueError(
            f"Grid creates {case_count} cases, exceeding the limit "
            f"of {int(max_cases)}."
        )

    cases: list[CalibrationCase] = []
    for case_id, combination in enumerate(product(*value_sets), start=1):
        cases.append(
            CalibrationCase(
                case_id=case_id,
                values={
                    key: float(value)
                    for key, value in zip(keys, combination)
                },
            )
        )
    return cases


def apply_calibration_case(
    project: ProjectDatabase,
    case: CalibrationCase,
) -> ProjectDatabase:
    clone = ProjectDatabase.from_dict(project.to_dict())
    for key, value in case.values.items():
        parts = str(key).split(":", 2)
        if len(parts) != 3 or parts[0] != "material":
            raise ValueError(f"Unsupported calibration target: {key}")
        material_tag = int(parts[1])
        parameter = str(parts[2])
        material = clone.materials.get(material_tag)
        if material is None:
            raise ValueError(
                f"Calibration material {material_tag} does not exist."
            )
        if parameter not in material.parameters:
            raise ValueError(
                f"Material {material_tag} ({material.material_type}) "
                f"has no parameter '{parameter}'."
            )
        material.parameters[parameter] = float(value)
    return clone


def project_to_script(project: ProjectDatabase) -> str:
    return to_openseespy(
        project.model,
        project.materials,
        project.sections,
        project.transformations,
        project.constraints,
        project.connections,
        project.time_series,
        project.load_patterns,
        project.nodal_loads,
        project.analyses,
        project.active_analysis_tag,
        element_loads=project.element_loads,
        prescribed_displacements=project.prescribed_displacements,
        recorders=project.recorders,
        units=project.units,
    )


def calibration_case_script(
    project: ProjectDatabase,
    case: CalibrationCase,
) -> str:
    return project_to_script(apply_calibration_case(project, case))


def _metric_difference(
    comparison: dict[str, Any],
    key: str,
) -> float | None:
    metrics = comparison.get("metrics", [])
    if not isinstance(metrics, list):
        return None
    for item in metrics:
        if not isinstance(item, dict) or item.get("key") != key:
            continue
        value = item.get("difference_percent")
        if value is None:
            return None
        try:
            number = abs(float(value))
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
    return None


def score_cyclic_calibration(
    result: dict[str, Any] | None,
    experiment_displacement: Sequence[float],
    experiment_force: Sequence[float],
    *,
    weights: CalibrationWeights | None = None,
) -> dict[str, Any]:
    from .postprocess import cyclic_hysteresis_curve

    x, y, _node, _dof = cyclic_hysteresis_curve(result)
    if not x or not y:
        return {
            "score": None,
            "status": "unavailable",
            "reason": "No usable cyclic hysteresis result.",
            "components": {},
            "comparison": {},
        }

    comparison = cyclic_curve_comparison(
        x,
        y,
        experiment_displacement,
        experiment_force,
    )
    if not comparison:
        return {
            "score": None,
            "status": "unavailable",
            "reason": "Experimental comparison could not be evaluated.",
            "components": {},
            "comparison": {},
        }

    selected = (weights or CalibrationWeights()).normalized()
    components: dict[str, float | None] = {
        "peak_force": _metric_difference(
            comparison,
            "peak_abs_force",
        ),
        "reversal_nrmse": (
            abs(float(comparison["reversal_force_nrmse_percent"]))
            if comparison.get("reversal_force_nrmse_percent") is not None
            else None
        ),
        "cycle_energy": _metric_difference(
            comparison,
            "closed_cycle_energy_sum",
        ),
        "max_displacement": _metric_difference(
            comparison,
            "max_abs_displacement",
        ),
    }

    numerator = 0.0
    denominator = 0.0
    for key, normalized_weight in selected.items():
        if normalized_weight <= 0.0:
            continue
        value = components.get(key)
        if value is None or not math.isfinite(float(value)):
            continue
        numerator += normalized_weight * abs(float(value))
        denominator += normalized_weight

    if denominator <= 0.0:
        return {
            "score": None,
            "status": "unavailable",
            "reason": "No selected objective component is available.",
            "components": components,
            "comparison": comparison,
        }

    return {
        "score": numerator / denominator,
        "status": "ok",
        "reason": "",
        "components": components,
        "comparison": comparison,
        "matched_reversal_count": int(
            comparison.get("matched_reversal_count", 0)
        ),
    }


def rank_calibration_cases(
    cases: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in cases]

    def sort_key(item: dict[str, Any]) -> tuple[int, float, int]:
        score = item.get("score")
        try:
            numeric = float(score)
        except (TypeError, ValueError):
            numeric = math.inf
        valid = math.isfinite(numeric)
        case_id = int(item.get("case_id", 0) or 0)
        return (0 if valid else 1, numeric, case_id)

    rows.sort(key=sort_key)
    rank = 0
    for item in rows:
        score = item.get("score")
        try:
            numeric = float(score)
        except (TypeError, ValueError):
            numeric = math.inf
        if math.isfinite(numeric):
            rank += 1
            item["rank"] = rank
        else:
            item["rank"] = None
    return rows
