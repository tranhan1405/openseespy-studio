from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class SolutionResultStatus:
    code: str
    symbol: str
    label: str
    action: str

    @property
    def tooltip(self) -> str:
        return f"{self.label}. {self.action}".strip()


UP_TO_DATE = SolutionResultStatus(
    "up_to_date",
    "✓",
    "Up to date",
    "Evaluate refreshes the display from the current completed Job.",
)
NEEDS_EVALUATION = SolutionResultStatus(
    "needs_evaluation",
    "⚡",
    "Needs evaluation",
    "Run Analysis to create current result data; Evaluate does not run the solver.",
)
STALE = SolutionResultStatus(
    "stale",
    "↻",
    "Analysis changed / stale",
    "Re-run Analysis before evaluating this result.",
)
UNAVAILABLE = SolutionResultStatus(
    "unavailable",
    "!",
    "Data unavailable",
    "The latest analysis did not produce usable result data; run or re-run the analysis.",
)


# Project entries that affect the OpenSees model / analysis response.  Result
# requests and recorder definitions are intentionally excluded: adding a view
# must not make already-valid structural response data stale.
_SOLVER_INPUT_KEYS = (
    "units",
    "model",
    "surface_edge_supports",
    "surface_edge_loads",
    "surface_pressures",
    "materials",
    "nd_materials",
    "sections",
    "transformations",
    "constraints",
    "connections",
    "time_series",
    "load_patterns",
    "nodal_loads",
    "prescribed_displacements",
    "element_loads",
    "mass_sources",
)


def solver_input_signature(
    project_payload: dict[str, Any],
    *,
    analysis_tag: int | None = None,
) -> str:
    """Return a stable signature of solver-relevant project input.

    Solution-result objects and recorder requests are deliberately excluded so
    inserting a post-processing view does not invalidate an existing Job.
    """
    payload = dict(project_payload or {})
    reduced: dict[str, Any] = {
        key: payload.get(key)
        for key in _SOLVER_INPUT_KEYS
        if key in payload
    }

    analyses = payload.get("analyses", [])
    if isinstance(analyses, list):
        if analysis_tag is None:
            reduced["analyses"] = analyses
        else:
            target = int(analysis_tag)
            reduced["analyses"] = [
                item
                for item in analyses
                if isinstance(item, dict)
                and int(item.get("tag", -1)) == target
            ]

    canonical = json.dumps(
        reduced,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classify_solution_result_status(
    *,
    has_job: bool,
    job_status: str = "",
    has_results: bool = False,
    job_signature: str = "",
    current_signature: str = "",
) -> SolutionResultStatus:
    """Classify a persistent Solution Result against the latest Job."""
    if not has_job:
        return NEEDS_EVALUATION

    normalized = str(job_status or "").strip().lower()
    if normalized in {"queued", "running"}:
        return NEEDS_EVALUATION
    if normalized != "completed" or not bool(has_results):
        return UNAVAILABLE

    source = str(job_signature or "")
    current = str(current_signature or "")
    if source and current and source != current:
        return STALE

    return UP_TO_DATE
