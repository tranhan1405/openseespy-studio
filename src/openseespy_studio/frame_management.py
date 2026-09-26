from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any

from .frame_presets import frame_spec_from_preset
from .frame_setup import prepare_frame_grid
from .generator import FrameGridSpec, generate_frame_project
from .project import ProjectDatabase


FRAME_MANAGED_SNAPSHOT_VERSION = 1

_FRAME_STATE_DOMAINS = (
    "model_settings",
    "nodes",
    "elements",
    "constraints",
    "connections",
    "time_series",
    "load_patterns",
    "nodal_loads",
    "prescribed_displacements",
    "element_loads",
    "mass_sources",
    "analyses",
    "recorders",
    "solution_results",
    "active_analysis",
)

_FRAME_TAG_DOMAINS = (
    "nodes",
    "elements",
    "constraints",
    "connections",
    "time_series",
    "load_patterns",
    "nodal_loads",
    "prescribed_displacements",
    "element_loads",
    "mass_sources",
    "analyses",
    "recorders",
    "solution_results",
)


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _project_frame_state_payload(project: ProjectDatabase) -> dict[str, Any]:
    data = project.to_dict()
    model = dict(data.get("model", {}))
    return {
        "model_settings": {
            "name": model.get("name"),
            "ndm": model.get("ndm"),
            "ndf": model.get("ndf"),
        },
        "nodes": list(model.get("nodes", [])),
        "elements": list(model.get("elements", [])),
        "constraints": list(data.get("constraints", [])),
        "connections": list(data.get("connections", [])),
        "time_series": list(data.get("time_series", [])),
        "load_patterns": list(data.get("load_patterns", [])),
        "nodal_loads": list(data.get("nodal_loads", [])),
        "prescribed_displacements": list(
            data.get("prescribed_displacements", [])
        ),
        "element_loads": list(data.get("element_loads", [])),
        "mass_sources": list(data.get("mass_sources", [])),
        "analyses": list(data.get("analyses", [])),
        "recorders": list(data.get("recorders", [])),
        "solution_results": list(data.get("solution_results", [])),
        "active_analysis": data.get("active_analysis_tag"),
    }


def managed_frame_snapshot(project: ProjectDatabase) -> dict[str, Any]:
    payload = _project_frame_state_payload(project)
    counts = {
        domain: (
            len(payload[domain])
            if isinstance(payload[domain], list)
            else int(payload[domain] is not None)
        )
        for domain in _FRAME_STATE_DOMAINS
    }
    counts["nodes"] = len(project.model.nodes)
    counts["elements"] = len(project.model.elements)
    return {
        "version": FRAME_MANAGED_SNAPSHOT_VERSION,
        "digests": {
            domain: _canonical_digest(payload[domain])
            for domain in _FRAME_STATE_DOMAINS
        },
        "counts": counts,
    }


def managed_frame_tag_sets(
    project: ProjectDatabase,
) -> dict[str, tuple[int, ...]]:
    return {
        "nodes": tuple(sorted(int(tag) for tag in project.model.nodes)),
        "elements": tuple(sorted(int(tag) for tag in project.model.elements)),
        "constraints": tuple(sorted(int(tag) for tag in project.constraints)),
        "connections": tuple(sorted(int(tag) for tag in project.connections)),
        "time_series": tuple(sorted(int(tag) for tag in project.time_series)),
        "load_patterns": tuple(
            sorted(int(tag) for tag in project.load_patterns)
        ),
        "nodal_loads": tuple(sorted(int(tag) for tag in project.nodal_loads)),
        "prescribed_displacements": tuple(
            sorted(int(tag) for tag in project.prescribed_displacements)
        ),
        "element_loads": tuple(
            sorted(int(tag) for tag in project.element_loads)
        ),
        "mass_sources": tuple(sorted(int(tag) for tag in project.mass_sources)),
        "analyses": tuple(sorted(int(tag) for tag in project.analyses)),
        "recorders": tuple(sorted(int(tag) for tag in project.recorders)),
        "solution_results": tuple(
            sorted(int(tag) for tag in project.solution_results)
        ),
    }


def build_frame_candidate(
    project: ProjectDatabase,
    spec: FrameGridSpec,
) -> tuple[ProjectDatabase, dict[str, int | float], int]:
    candidate = ProjectDatabase.from_dict(project.to_dict())
    candidate.frame_wizard_recipe = {}
    candidate_spec = replace(spec)
    created_transformations = prepare_frame_grid(
        candidate,
        candidate_spec,
    )
    result = dict(generate_frame_project(candidate, candidate_spec))
    return candidate, result, len(created_transformations)


def expected_managed_frame_snapshot(
    project: ProjectDatabase,
    recipe: dict[str, Any],
) -> dict[str, Any]:
    stored = recipe.get("managed_snapshot")
    if (
        isinstance(stored, dict)
        and int(stored.get("version", 0))
        == FRAME_MANAGED_SNAPSHOT_VERSION
        and isinstance(stored.get("digests"), dict)
    ):
        return stored
    spec = frame_spec_from_preset(recipe)
    candidate, _, _ = build_frame_candidate(project, spec)
    return managed_frame_snapshot(candidate)


def managed_frame_conflicts(
    project: ProjectDatabase,
    recipe: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = expected_managed_frame_snapshot(project, recipe)
    current = managed_frame_snapshot(project)
    expected_digests = dict(expected.get("digests", {}))
    expected_counts = dict(expected.get("counts", {}))
    current_digests = dict(current.get("digests", {}))
    current_counts = dict(current.get("counts", {}))

    conflicts: list[dict[str, Any]] = []
    for domain in _FRAME_STATE_DOMAINS:
        if expected_digests.get(domain) == current_digests.get(domain):
            continue
        conflicts.append(
            {
                "domain": domain,
                "expected_count": int(expected_counts.get(domain, 0)),
                "current_count": int(current_counts.get(domain, 0)),
            }
        )
    return conflicts


def frame_regeneration_plan(
    project: ProjectDatabase,
    recipe: dict[str, Any],
    candidate_spec: FrameGridSpec,
) -> dict[str, Any]:
    original_spec = frame_spec_from_preset(recipe)
    baseline, _, _ = build_frame_candidate(project, original_spec)
    candidate, result, created_transformations = build_frame_candidate(
        project,
        candidate_spec,
    )
    before_tags = managed_frame_tag_sets(baseline)
    after_tags = managed_frame_tag_sets(candidate)

    tag_domains = {}
    all_stable = True
    for domain in _FRAME_TAG_DOMAINS:
        before = before_tags[domain]
        after = after_tags[domain]
        before_set = set(before)
        after_set = set(after)
        retained = len(before_set & after_set)
        stable = before == after
        all_stable = all_stable and stable
        tag_domains[domain] = {
            "before": len(before),
            "after": len(after),
            "delta": len(after) - len(before),
            "retained": retained,
            "stable": stable,
        }

    conflicts = managed_frame_conflicts(project, recipe)
    return {
        "compatible": bool(all_stable and not conflicts),
        "all_tags_stable": bool(all_stable),
        "conflicts": conflicts,
        "domains": tag_domains,
        "candidate_snapshot": managed_frame_snapshot(candidate),
        "candidate_result": result,
        "created_transformations": int(created_transformations),
    }
