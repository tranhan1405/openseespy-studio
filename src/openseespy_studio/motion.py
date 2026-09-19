from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class MotionInfo:
    kind: str
    frame_count: int
    mode: int | None
    reference_magnitude: float
    coordinate_name: str
    transient_dt: float | None = None


@dataclass(frozen=True, slots=True)
class MotionFrame:
    index: int
    frame_count: int
    vectors: dict[str, list[float]]
    label: str
    coordinate: float | None = None


def available_modal_modes(result: dict[str, Any]) -> list[int]:
    modes = result.get("modes", {}) if isinstance(result, dict) else {}
    if not isinstance(modes, dict):
        return []
    values: list[int] = []
    for key in modes:
        try:
            values.append(int(key))
        except (TypeError, ValueError):
            continue
    return sorted(set(values))


def _vector3(raw: object) -> list[float]:
    values = list(raw) if isinstance(raw, (list, tuple)) else []
    while len(values) < 3:
        values.append(0.0)
    return [float(values[0]), float(values[1]), float(values[2])]


def _magnitude(values: list[float]) -> float:
    return math.sqrt(
        values[0] * values[0]
        + values[1] * values[1]
        + values[2] * values[2]
    )


def _modal_reference_magnitude(
    result: dict[str, Any],
    mode: int,
) -> float:
    modes = result.get("modes", {})
    mode_data = (
        modes.get(str(int(mode)), modes.get(int(mode), {}))
        if isinstance(modes, dict)
        else {}
    )
    vectors = mode_data.get("vectors", {}) if isinstance(mode_data, dict) else {}
    if not isinstance(vectors, dict):
        return 0.0
    return max(
        (_magnitude(_vector3(vector)) for vector in vectors.values()),
        default=0.0,
    )


def _history_frame_count(result: dict[str, Any]) -> int:
    history = result.get("history", {}) if isinstance(result, dict) else {}
    nodes = history.get("nodes", {}) if isinstance(history, dict) else {}
    if not isinstance(nodes, dict):
        return 0
    count = 0
    for node_data in nodes.values():
        if not isinstance(node_data, dict):
            continue
        rows = node_data.get("disp", [])
        if isinstance(rows, list):
            count = max(count, len(rows))
    return count


def _history_reference_magnitude(result: dict[str, Any]) -> float:
    history = result.get("history", {}) if isinstance(result, dict) else {}
    nodes = history.get("nodes", {}) if isinstance(history, dict) else {}
    if not isinstance(nodes, dict):
        return 0.0
    maximum = 0.0
    for node_data in nodes.values():
        if not isinstance(node_data, dict):
            continue
        rows = node_data.get("disp", [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            maximum = max(maximum, _magnitude(_vector3(row)))
    return maximum


def _final_reference_magnitude(result: dict[str, Any]) -> float:
    final = result.get("final", {}) if isinstance(result, dict) else {}
    vectors = (
        final.get("node_displacements", {})
        if isinstance(final, dict)
        else {}
    )
    if not isinstance(vectors, dict):
        return 0.0
    return max(
        (_magnitude(_vector3(vector)) for vector in vectors.values()),
        default=0.0,
    )


def motion_info(
    result: dict[str, Any],
    *,
    mode: int | None = None,
    modal_frames: int = 48,
    fallback_frames: int = 30,
) -> MotionInfo:
    analysis = result.get("analysis", {}) if isinstance(result, dict) else {}
    analysis_type = (
        str(analysis.get("type", ""))
        if isinstance(analysis, dict)
        else ""
    )

    if analysis_type == "Modal":
        modes = available_modal_modes(result)
        selected_mode = int(mode) if mode is not None else (modes[0] if modes else None)
        if selected_mode is None or selected_mode not in modes:
            return MotionInfo(
                kind="Modal",
                frame_count=0,
                mode=selected_mode,
                reference_magnitude=0.0,
                coordinate_name="Phase",
            )
        return MotionInfo(
            kind="Modal",
            frame_count=max(8, int(modal_frames)),
            mode=selected_mode,
            reference_magnitude=_modal_reference_magnitude(
                result,
                selected_mode,
            ),
            coordinate_name="Phase",
        )

    history_count = _history_frame_count(result)
    if history_count > 0:
        history = result.get("history", {})
        times = history.get("time", []) if isinstance(history, dict) else []
        transient_dt: float | None = None
        if analysis_type == "Transient" and isinstance(times, list) and len(times) >= 2:
            deltas = [
                float(times[index]) - float(times[index - 1])
                for index in range(1, len(times))
                if float(times[index]) > float(times[index - 1])
            ]
            if deltas:
                deltas.sort()
                transient_dt = deltas[len(deltas) // 2]
        return MotionInfo(
            kind=analysis_type or "Analysis",
            frame_count=history_count,
            mode=None,
            reference_magnitude=_history_reference_magnitude(result),
            coordinate_name=(
                "Time"
                if analysis_type == "Transient"
                else "Analysis coordinate"
            ),
            transient_dt=transient_dt,
        )

    final = result.get("final", {}) if isinstance(result, dict) else {}
    vectors = (
        final.get("node_displacements", {})
        if isinstance(final, dict)
        else {}
    )
    if isinstance(vectors, dict) and vectors:
        return MotionInfo(
            kind=analysis_type or "Static",
            frame_count=max(2, int(fallback_frames)),
            mode=None,
            reference_magnitude=_final_reference_magnitude(result),
            coordinate_name="Interpolation",
        )

    return MotionInfo(
        kind=analysis_type or "Analysis",
        frame_count=0,
        mode=None,
        reference_magnitude=0.0,
        coordinate_name="Frame",
    )


def motion_frame(
    result: dict[str, Any],
    index: int,
    *,
    mode: int | None = None,
    modal_frames: int = 48,
    fallback_frames: int = 30,
    info: MotionInfo | None = None,
) -> MotionFrame:
    if info is None:
        info = motion_info(
            result,
            mode=mode,
            modal_frames=modal_frames,
            fallback_frames=fallback_frames,
        )
    if info.frame_count <= 0:
        return MotionFrame(
            index=0,
            frame_count=0,
            vectors={},
            label="No motion data",
        )

    frame_index = max(0, min(int(index), info.frame_count - 1))
    analysis = result.get("analysis", {}) if isinstance(result, dict) else {}
    analysis_type = (
        str(analysis.get("type", ""))
        if isinstance(analysis, dict)
        else ""
    )

    if info.kind == "Modal" and info.mode is not None:
        modes = result.get("modes", {})
        mode_data = (
            modes.get(str(info.mode), modes.get(info.mode, {}))
            if isinstance(modes, dict)
            else {}
        )
        raw_vectors = (
            mode_data.get("vectors", {})
            if isinstance(mode_data, dict)
            else {}
        )
        phase = 2.0 * math.pi * frame_index / info.frame_count
        amplitude = math.sin(phase)
        vectors = {
            str(tag): [amplitude * value for value in _vector3(vector)]
            for tag, vector in (
                raw_vectors.items()
                if isinstance(raw_vectors, dict)
                else []
            )
        }
        phase_deg = math.degrees(phase)
        return MotionFrame(
            index=frame_index,
            frame_count=info.frame_count,
            vectors=vectors,
            label=(
                f"Mode {info.mode} · phase {phase_deg:.1f}° · "
                f"amplitude {amplitude:+.3f}"
            ),
            coordinate=phase_deg,
        )

    history = result.get("history", {}) if isinstance(result, dict) else {}
    nodes = history.get("nodes", {}) if isinstance(history, dict) else {}
    if isinstance(nodes, dict) and nodes:
        vectors: dict[str, list[float]] = {}
        for tag, node_data in nodes.items():
            if not isinstance(node_data, dict):
                continue
            rows = node_data.get("disp", [])
            if not isinstance(rows, list) or frame_index >= len(rows):
                continue
            vectors[str(tag)] = _vector3(rows[frame_index])

        times = history.get("time", []) if isinstance(history, dict) else []
        coordinate: float | None = None
        if isinstance(times, list) and frame_index < len(times):
            try:
                coordinate = float(times[frame_index])
            except (TypeError, ValueError):
                coordinate = None

        if analysis_type == "Transient" and coordinate is not None:
            label = (
                f"Frame {frame_index + 1}/{info.frame_count} · "
                f"t = {coordinate:.6g} s"
            )
        elif coordinate is not None:
            label = (
                f"Step {frame_index + 1}/{info.frame_count} · "
                f"coordinate = {coordinate:.6g}"
            )
        else:
            label = f"Step {frame_index + 1}/{info.frame_count}"

        return MotionFrame(
            index=frame_index,
            frame_count=info.frame_count,
            vectors=vectors,
            label=label,
            coordinate=coordinate,
        )

    final = result.get("final", {}) if isinstance(result, dict) else {}
    raw_vectors = (
        final.get("node_displacements", {})
        if isinstance(final, dict)
        else {}
    )
    factor = (
        frame_index / (info.frame_count - 1)
        if info.frame_count > 1
        else 1.0
    )
    vectors = {
        str(tag): [factor * value for value in _vector3(vector)]
        for tag, vector in (
            raw_vectors.items()
            if isinstance(raw_vectors, dict)
            else []
        )
    }
    return MotionFrame(
        index=frame_index,
        frame_count=info.frame_count,
        vectors=vectors,
        label=(
            f"Interpolated deformation · "
            f"{100.0 * factor:.1f}% of final"
        ),
        coordinate=factor,
    )
