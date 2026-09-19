from __future__ import annotations

import math
import re
from typing import Any


_FLOAT = r"[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][-+]?\\d+)?|[-+]?inf|nan"
_ITERATION_RE = re.compile(
    rf"CTest(?P<test>[A-Za-z0-9_]+)::test\\(\\)\\s*-\\s*"
    rf"iteration:\\s*(?P<iteration>\\d+)\\s+"
    rf"current\\s+(?:Norm|EnergyIncr|Energy\\s+Norm):\\s*"
    rf"(?P<norm>{_FLOAT})\\s*"
    rf"\\(max:\\s*(?P<tolerance>{_FLOAT})",
    re.IGNORECASE,
)
_FAILED_RE = re.compile(
    rf"CTest(?P<test>[A-Za-z0-9_]+)::test\\(\\)\\s*-\\s*"
    rf"failed\\s+to\\s+converge.*?"
    rf"(?:after:\\s*(?P<iteration>\\d+)\\s+iterations.*?)?"
    rf"current\\s+(?:Norm|EnergyIncr|Energy\\s+Norm):\\s*"
    rf"(?P<norm>{_FLOAT})\\s*"
    rf"\\(max:\\s*(?P<tolerance>{_FLOAT})",
    re.IGNORECASE,
)


def _number(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def parse_opensees_convergence_line(
    line: str,
) -> dict[str, Any] | None:
    """Parse native OpenSees convergence-test iteration output."""
    text = str(line).strip()
    match = _ITERATION_RE.search(text)
    failed = False
    if match is None:
        match = _FAILED_RE.search(text)
        failed = match is not None
    if match is None:
        return None

    norm = _number(match.group("norm"))
    tolerance = _number(match.group("tolerance"))
    if norm is None or tolerance is None:
        return None

    iteration_raw = match.groupdict().get("iteration")
    iteration = int(iteration_raw) if iteration_raw else 0
    return {
        "test": match.group("test"),
        "iteration": iteration,
        "norm": norm,
        "tolerance": tolerance,
        "failed": failed,
    }
