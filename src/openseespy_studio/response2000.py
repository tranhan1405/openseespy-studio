from __future__ import annotations

import math
import re
from bisect import bisect_right
from collections.abc import Sequence
from typing import Any

from .postprocess import parse_experimental_csv_text
from .units import UnitSystem


_NUMBER_RE = re.compile(
    r"[-+]?(?:(?:\d+(?:[\.,]\d*)?)|(?:[\.,]\d+))(?:[Ee][-+]?\d+)?"
)


def _finite_rows(dataset: dict[str, Any]) -> int:
    rows = dataset.get("rows", [])
    if not isinstance(rows, (list, tuple)):
        return 0
    return sum(
        1
        for row in rows
        if isinstance(row, (list, tuple))
        and sum(value is not None for value in row) >= 2
    )


def parse_response2000_chart_text(text: str) -> dict[str, Any]:
    """Parse Response-2000 chart data copied/exported as text.

    Response-2000's manual describes Copy Chart Data as a table of numbers
    that may need to be parsed before spreadsheet use. This parser therefore
    accepts ordinary CSV/TSV/semicolon files first, then falls back to generic
    whitespace/text rows containing at least two finite numbers.
    """
    raw = str(text or "").lstrip("\ufeff")
    dataset = parse_experimental_csv_text(raw)
    if len(dataset.get("headers", [])) >= 2 and _finite_rows(dataset) >= 2:
        result = dict(dataset)
        result["format"] = "delimited"
        return result

    lines = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "//"))
    ]
    numeric_rows: list[list[float | None]] = []
    for line in lines:
        tokens = _NUMBER_RE.findall(line)
        if len(tokens) < 2:
            continue
        values: list[float | None] = []
        for token in tokens:
            value = token.strip()
            if "," in value and "." not in value:
                value = value.replace(",", ".")
            try:
                number = float(value)
            except ValueError:
                number = math.nan
            values.append(number if math.isfinite(number) else None)
        if sum(value is not None for value in values) >= 2:
            numeric_rows.append(values)

    if not numeric_rows:
        return {
            "headers": [],
            "rows": [],
            "delimiter": "whitespace",
            "skipped_rows": 0,
            "format": "whitespace",
        }

    width = max(len(row) for row in numeric_rows)
    rows = [
        row + [None] * (width - len(row))
        for row in numeric_rows
    ]

    # Response chart titles/axis labels are often present separately from the
    # numeric table. Preserve useful semantics when they can be recognized.
    joined = " ".join(lines[:12]).lower()
    headers = [f"Column {index + 1}" for index in range(width)]
    if width >= 2 and (
        "curvature" in joined
        or "kappa" in joined
        or "κ" in joined
    ) and "moment" in joined:
        headers[0] = "Curvature"
        headers[1] = "Moment"

    return {
        "headers": headers,
        "rows": rows,
        "delimiter": "whitespace",
        "skipped_rows": 0,
        "format": "whitespace",
    }


def suggest_response2000_columns(
    headers: Sequence[str],
) -> tuple[int, int]:
    """Suggest curvature and moment columns from chart/table headers."""
    normalized = [str(header).strip().lower() for header in headers]

    def score_curvature(value: str) -> int:
        score = 0
        if "curvature" in value:
            score += 10
        if "kappa" in value or "κ" in value:
            score += 9
        if "curv" in value:
            score += 5
        if "moment" in value:
            score -= 5
        return score

    def score_moment(value: str) -> int:
        score = 0
        if "moment" in value:
            score += 10
        if re.search(r"(^|[^a-z])m[xyz]?([^a-z]|$)", value):
            score += 5
        if "curvature" in value or "kappa" in value or "κ" in value:
            score -= 5
        return score

    if not normalized:
        return 0, 1
    x_scores = [score_curvature(value) for value in normalized]
    y_scores = [score_moment(value) for value in normalized]
    x_index = max(range(len(normalized)), key=lambda index: x_scores[index])
    y_index = max(range(len(normalized)), key=lambda index: y_scores[index])

    if max(x_scores) <= 0:
        x_index = 0
    if max(y_scores) <= 0 or y_index == x_index:
        y_index = next(
            (index for index in range(len(normalized)) if index != x_index),
            x_index,
        )
    return int(x_index), int(y_index)


def suggest_response2000_units(
    curvature_header: str,
    moment_header: str,
) -> tuple[str, str]:
    """Infer common Response-2000 chart units from axis/header text."""
    x = str(curvature_header or "").lower().replace(" ", "")
    y = (
        str(moment_header or "")
        .lower()
        .replace(" ", "")
        .replace("·", "")
        .replace("-", "")
    )

    if "/km" in x or "rad/km" in x:
        curvature_unit = "rad_per_km"
    elif "/mm" in x or "1/mm" in x:
        curvature_unit = "per_mm"
    elif "/cm" in x or "1/cm" in x:
        curvature_unit = "per_cm"
    elif "/in" in x or "1/in" in x:
        curvature_unit = "per_in"
    elif "/ft" in x or "1/ft" in x:
        curvature_unit = "per_ft"
    elif "/m" in x or "1/m" in x:
        curvature_unit = "per_m"
    else:
        curvature_unit = "same"

    if "knm" in y:
        moment_unit = "kn_m"
    elif "nmm" in y:
        moment_unit = "n_mm"
    elif "knmm" in y:
        moment_unit = "kn_mm"
    elif "kipft" in y:
        moment_unit = "kip_ft"
    elif "kipin" in y:
        moment_unit = "kip_in"
    elif "kgfm" in y:
        moment_unit = "kgf_m"
    elif "kgfcm" in y:
        moment_unit = "kgf_cm"
    elif "nm" in y:
        moment_unit = "n_m"
    else:
        moment_unit = "same"
    return curvature_unit, moment_unit


_CURVATURE_TO_PER_M = {
    "per_m": 1.0,
    "rad_per_km": 1.0e-3,
    "per_mm": 1.0e3,
    "per_cm": 1.0e2,
    "per_in": 1.0 / 0.0254,
    "per_ft": 1.0 / 0.3048,
}

_MOMENT_TO_NM = {
    "n_m": 1.0,
    "kn_m": 1.0e3,
    "n_mm": 1.0e-3,
    "kn_mm": 1.0,
    "kip_in": 4448.2216152605 * 0.0254,
    "kip_ft": 4448.2216152605 * 0.3048,
    "kgf_m": 9.80665,
    "kgf_cm": 9.80665 * 0.01,
}


def response2000_series(
    dataset: dict[str, Any] | None,
    curvature_column: int,
    moment_column: int,
    *,
    curvature_unit: str = "same",
    moment_unit: str = "same",
    units=None,
    curvature_factor: float = 1.0,
    moment_factor: float = 1.0,
) -> tuple[list[float], list[float]]:
    """Extract and convert Response-2000 M-kappa data to active model units."""
    if not isinstance(dataset, dict):
        return [], []
    rows = dataset.get("rows", [])
    if not isinstance(rows, (list, tuple)):
        return [], []

    try:
        x_index = int(curvature_column)
        y_index = int(moment_column)
        x_factor = float(curvature_factor)
        y_factor = float(moment_factor)
    except (TypeError, ValueError):
        return [], []
    if (
        x_index < 0
        or y_index < 0
        or not math.isfinite(x_factor)
        or not math.isfinite(y_factor)
    ):
        return [], []

    unit_system = UnitSystem.from_mapping(units)
    x_mode = str(curvature_unit or "same")
    y_mode = str(moment_unit or "same")

    result_x: list[float] = []
    result_y: list[float] = []
    for row in rows:
        if (
            not isinstance(row, (list, tuple))
            or x_index >= len(row)
            or y_index >= len(row)
        ):
            continue
        raw_x = row[x_index]
        raw_y = row[y_index]
        if raw_x is None or raw_y is None:
            continue
        try:
            x_value = float(raw_x) * x_factor
            y_value = float(raw_y) * y_factor
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            continue

        if x_mode != "same":
            per_m = x_value * _CURVATURE_TO_PER_M.get(x_mode, 1.0)
            x_value = per_m * unit_system.length_to_m
        if y_mode != "same":
            moment_nm = y_value * _MOMENT_TO_NM.get(y_mode, 1.0)
            y_value = unit_system.moment_from_nm(moment_nm)

        result_x.append(float(x_value))
        result_y.append(float(y_value))
    return result_x, result_y


def _clean_curve(
    x_values: Sequence[float],
    y_values: Sequence[float],
) -> tuple[list[float], list[float]]:
    pairs: list[tuple[float, float]] = []
    for raw_x, raw_y in zip(x_values, y_values):
        try:
            x = float(raw_x)
            y = float(raw_y)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            pairs.append((x, y))
    pairs.sort(key=lambda pair: pair[0])

    clean: list[tuple[float, float]] = []
    for x, y in pairs:
        if clean and abs(x - clean[-1][0]) <= 1.0e-15:
            clean[-1] = (x, y)
        else:
            clean.append((x, y))
    return [pair[0] for pair in clean], [pair[1] for pair in clean]


def _interp(x: Sequence[float], y: Sequence[float], target: float) -> float:
    if not x:
        return math.nan
    if target <= x[0]:
        return float(y[0])
    if target >= x[-1]:
        return float(y[-1])
    right = bisect_right(x, target)
    left = max(0, right - 1)
    right = min(right, len(x) - 1)
    x0, x1 = float(x[left]), float(x[right])
    y0, y1 = float(y[left]), float(y[right])
    if abs(x1 - x0) <= 1.0e-30:
        return y1
    ratio = (target - x0) / (x1 - x0)
    return y0 + ratio * (y1 - y0)


def _initial_stiffness(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) < 2:
        return None
    peak = max((abs(float(value)) for value in y), default=0.0)
    if peak <= 1.0e-30:
        return None

    candidates = [
        (float(xv), float(yv))
        for xv, yv in zip(x, y)
        if abs(float(xv)) > 1.0e-15
        and abs(float(yv)) <= 0.20 * peak
    ]
    if len(candidates) < 2:
        candidates = [
            (float(xv), float(yv))
            for xv, yv in zip(x[: min(5, len(x))], y[: min(5, len(y))])
            if abs(float(xv)) > 1.0e-15
        ]
    if not candidates:
        return None

    denominator = sum(xv * xv for xv, _ in candidates)
    if denominator <= 1.0e-30:
        return None
    return sum(xv * yv for xv, yv in candidates) / denominator


def _area_abs(
    x: Sequence[float],
    y: Sequence[float],
    lower: float,
    upper: float,
) -> float | None:
    if upper <= lower or len(x) < 2:
        return None
    grid = [lower]
    grid.extend(value for value in x if lower < value < upper)
    grid.append(upper)
    grid = sorted(set(float(value) for value in grid))
    if len(grid) < 2:
        return None
    values = [abs(_interp(x, y, value)) for value in grid]
    return sum(
        0.5 * (values[index] + values[index - 1])
        * (grid[index] - grid[index - 1])
        for index in range(1, len(grid))
    )


def _percent(simulation: float | None, reference: float | None) -> float | None:
    if simulation is None or reference is None:
        return None
    if not math.isfinite(simulation) or not math.isfinite(reference):
        return None
    if abs(reference) <= 1.0e-15:
        return None
    return (simulation - reference) / abs(reference) * 100.0


def response2000_curve_comparison(
    simulation_curvature: Sequence[float],
    simulation_moment: Sequence[float],
    response_curvature: Sequence[float],
    response_moment: Sequence[float],
) -> dict[str, Any]:
    """Return descriptive SARE/OpenSees versus Response-2000 M-kappa metrics."""
    sim_x, sim_y = _clean_curve(simulation_curvature, simulation_moment)
    ref_x, ref_y = _clean_curve(response_curvature, response_moment)
    if min(len(sim_x), len(sim_y), len(ref_x), len(ref_y)) < 2:
        return {}

    sim_peak_index = max(range(len(sim_y)), key=lambda i: abs(sim_y[i]))
    ref_peak_index = max(range(len(ref_y)), key=lambda i: abs(ref_y[i]))
    sim_peak = abs(sim_y[sim_peak_index])
    ref_peak = abs(ref_y[ref_peak_index])
    sim_peak_kappa = abs(sim_x[sim_peak_index])
    ref_peak_kappa = abs(ref_x[ref_peak_index])

    sim_stiffness = _initial_stiffness(sim_x, sim_y)
    ref_stiffness = _initial_stiffness(ref_x, ref_y)

    lower = max(min(sim_x), min(ref_x))
    upper = min(max(sim_x), max(ref_x))
    sim_area = _area_abs(sim_x, sim_y, lower, upper)
    ref_area = _area_abs(ref_x, ref_y, lower, upper)

    overlap_points = [value for value in sim_x if lower <= value <= upper]
    nrmse = None
    if overlap_points and ref_peak > 1.0e-15:
        square_errors = []
        for value in overlap_points:
            sim_value = _interp(sim_x, sim_y, value)
            ref_value = _interp(ref_x, ref_y, value)
            square_errors.append((sim_value - ref_value) ** 2)
        if square_errors:
            nrmse = (
                math.sqrt(sum(square_errors) / len(square_errors))
                / ref_peak
                * 100.0
            )

    metrics = [
        {
            "key": "peak_moment",
            "label": "Peak |M|",
            "simulation": sim_peak,
            "response2000": ref_peak,
            "difference_percent": _percent(sim_peak, ref_peak),
        },
        {
            "key": "curvature_at_peak",
            "label": "|κ| at peak |M|",
            "simulation": sim_peak_kappa,
            "response2000": ref_peak_kappa,
            "difference_percent": _percent(sim_peak_kappa, ref_peak_kappa),
        },
        {
            "key": "initial_stiffness",
            "label": "Initial dM/dκ",
            "simulation": sim_stiffness,
            "response2000": ref_stiffness,
            "difference_percent": _percent(sim_stiffness, ref_stiffness),
        },
        {
            "key": "common_area",
            "label": "Area |M|dκ over overlap",
            "simulation": sim_area,
            "response2000": ref_area,
            "difference_percent": _percent(sim_area, ref_area),
        },
    ]
    return {
        "metrics": metrics,
        "moment_nrmse_percent": nrmse,
        "overlap_min_curvature": lower,
        "overlap_max_curvature": upper,
        "overlap_point_count": len(overlap_points),
    }
