from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class MEFICrackPanelState:
    element_tag: int
    panel: int
    width: float
    section_tag: int
    cracking_strain: float | None
    epsilon_1: float | None
    theta_1: float | None
    ratio: float | None
    cracked: bool
    valid: bool


def principal_tensile_strain(
    values: object,
) -> tuple[float, float] | None:
    """Return maximum in-plane principal strain and its direction."""
    if not isinstance(values, (list, tuple)) or len(values) < 3:
        return None
    try:
        ex = float(values[0])
        ey = float(values[1])
        gxy = float(values[2])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (ex, ey, gxy)):
        return None

    average = 0.5 * (ex + ey)
    radius = math.sqrt(
        (0.5 * (ex - ey)) ** 2 + (0.5 * gxy) ** 2
    )
    epsilon_1 = average + radius
    theta_1 = 0.5 * math.atan2(gxy, ex - ey)
    return float(epsilon_1), float(theta_1)


def _normalise_scope(
    element_tags: Iterable[int] | None,
) -> set[int] | None:
    if element_tags is None:
        return None
    values = {int(tag) for tag in element_tags}
    return values or None


def _panel_candidates(
    *,
    final_panels: dict[str, Any],
    history_panels: dict[str, Any],
    element_key: str,
    panel_key: str,
    frame_index: int | None,
    accumulate: bool,
) -> list[object]:
    final_element = final_panels.get(element_key, {})
    final_row = (
        final_element.get(panel_key, [])
        if isinstance(final_element, dict)
        else []
    )
    history_element = history_panels.get(element_key, {})
    rows = (
        history_element.get(panel_key, [])
        if isinstance(history_element, dict)
        else []
    )
    rows = list(rows) if isinstance(rows, list) else []

    if frame_index is None:
        if accumulate and rows:
            return rows
        return [final_row] if final_row else []

    if rows:
        index = max(0, min(int(frame_index), len(rows) - 1))
        return rows[: index + 1] if accumulate else [rows[index]]

    return [final_row] if final_row else []


def mefi_crack_panel_states(
    result: dict[str, Any] | None,
    *,
    frame_index: int | None = None,
    accumulate: bool = False,
    element_tags: Iterable[int] | None = None,
) -> list[MEFICrackPanelState]:
    """Return one normalized crack state per MEFI macro-fiber panel."""
    payload = result if isinstance(result, dict) else {}
    specs = payload.get("mefi_crack_specs", {})
    final = payload.get("final", {})
    history = payload.get("history", {})
    final_panels = (
        final.get("mefi_panel_strains", {})
        if isinstance(final, dict)
        else {}
    )
    history_panels = (
        history.get("mefi_panel_strains", {})
        if isinstance(history, dict)
        else {}
    )
    if not isinstance(specs, dict):
        return []
    if not isinstance(final_panels, dict):
        final_panels = {}
    if not isinstance(history_panels, dict):
        history_panels = {}

    requested = _normalise_scope(element_tags)
    states: list[MEFICrackPanelState] = []

    def sort_key(item: tuple[object, object]) -> tuple[int, str]:
        try:
            return (int(item[0]), "")
        except (TypeError, ValueError):
            return (10**12, str(item[0]))

    for raw_tag, spec in sorted(specs.items(), key=sort_key):
        try:
            tag = int(raw_tag)
        except (TypeError, ValueError):
            continue
        if requested is not None and tag not in requested:
            continue
        if not isinstance(spec, dict):
            continue

        panels = spec.get("panels", [])
        if not isinstance(panels, list):
            continue

        for index, panel in enumerate(panels, start=1):
            if not isinstance(panel, dict):
                continue
            try:
                panel_no = int(panel.get("panel", index))
            except (TypeError, ValueError):
                panel_no = int(index)
            try:
                width = float(panel.get("width", 0.0))
            except (TypeError, ValueError):
                width = 0.0
            try:
                section_tag = int(panel.get("section_tag", 0))
            except (TypeError, ValueError):
                section_tag = 0
            try:
                threshold = float(panel.get("cracking_strain"))
            except (TypeError, ValueError):
                threshold = None
            if threshold is not None and (
                not math.isfinite(threshold) or threshold <= 0.0
            ):
                threshold = None

            candidates = _panel_candidates(
                final_panels=final_panels,
                history_panels=history_panels,
                element_key=str(tag),
                panel_key=str(panel_no),
                frame_index=frame_index,
                accumulate=bool(accumulate),
            )

            best_ratio: float | None = None
            best_epsilon: float | None = None
            best_theta: float | None = None
            fallback: tuple[float, float] | None = None
            for values in candidates:
                principal = principal_tensile_strain(values)
                if principal is None:
                    continue
                epsilon_1, theta_1 = principal
                fallback = (epsilon_1, theta_1)
                if threshold is None:
                    continue
                ratio = epsilon_1 / threshold
                if best_ratio is None or ratio > best_ratio:
                    best_ratio = float(ratio)
                    best_epsilon = float(epsilon_1)
                    best_theta = float(theta_1)

            if best_ratio is None and fallback is not None:
                best_epsilon, best_theta = fallback

            valid = (
                threshold is not None
                and best_ratio is not None
                and best_epsilon is not None
                and best_theta is not None
            )
            states.append(
                MEFICrackPanelState(
                    element_tag=tag,
                    panel=panel_no,
                    width=max(0.0, width),
                    section_tag=section_tag,
                    cracking_strain=threshold,
                    epsilon_1=best_epsilon,
                    theta_1=best_theta,
                    ratio=best_ratio,
                    cracked=bool(valid and best_ratio >= 1.0),
                    valid=bool(valid),
                )
            )

    return states


def mefi_crack_summary(
    states: Iterable[MEFICrackPanelState],
) -> dict[str, float | int]:
    rows = list(states)
    valid = [state for state in rows if state.valid]
    cracked = [state for state in valid if state.cracked]
    ratios = [
        float(state.ratio)
        for state in valid
        if state.ratio is not None and math.isfinite(float(state.ratio))
    ]
    return {
        "panels": len(rows),
        "valid_panels": len(valid),
        "cracked": len(cracked),
        "max_ratio": max(ratios) if ratios else 0.0,
        "elements": len({state.element_tag for state in rows}),
    }


def mefi_crack_frame_count(
    result: dict[str, Any] | None,
    *,
    element_tags: Iterable[int] | None = None,
) -> int:
    payload = result if isinstance(result, dict) else {}
    specs = payload.get("mefi_crack_specs", {})
    history = payload.get("history", {})
    history_panels = (
        history.get("mefi_panel_strains", {})
        if isinstance(history, dict)
        else {}
    )
    if not isinstance(specs, dict) or not isinstance(history_panels, dict):
        return 0
    requested = _normalise_scope(element_tags)
    count = 0
    for raw_tag in specs:
        try:
            tag = int(raw_tag)
        except (TypeError, ValueError):
            continue
        if requested is not None and tag not in requested:
            continue
        element_rows = history_panels.get(str(tag), {})
        if not isinstance(element_rows, dict):
            continue
        for rows in element_rows.values():
            if isinstance(rows, list):
                count = max(count, len(rows))
    return count


def mefi_crack_evolution(
    result: dict[str, Any] | None,
    *,
    element_tags: Iterable[int] | None = None,
) -> list[dict[str, float | int]]:
    count = mefi_crack_frame_count(
        result,
        element_tags=element_tags,
    )
    rows: list[dict[str, float | int]] = []
    for frame_index in range(count):
        states = mefi_crack_panel_states(
            result,
            frame_index=frame_index,
            accumulate=False,
            element_tags=element_tags,
        )
        summary = mefi_crack_summary(states)
        rows.append({
            "frame": frame_index,
            **summary,
        })
    return rows


def mefi_crack_data_health(
    result: dict[str, Any] | None,
    *,
    element_tags: Iterable[int] | None = None,
) -> dict[str, int]:
    payload = result if isinstance(result, dict) else {}
    specs = payload.get("mefi_crack_specs", {})
    states = mefi_crack_panel_states(
        payload,
        element_tags=element_tags,
    )
    thresholds = sum(
        1 for state in states if state.cracking_strain is not None
    )
    strains = sum(
        1 for state in states if state.epsilon_1 is not None
    )
    valid = sum(1 for state in states if state.valid)
    return {
        "spec_elements": len(specs) if isinstance(specs, dict) else 0,
        "panels": len(states),
        "thresholds": thresholds,
        "strains": strains,
        "valid": valid,
        "history_frames": mefi_crack_frame_count(
            payload,
            element_tags=element_tags,
        ),
    }
