from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from typing import Any

from .beam_loads import resolve_self_weight_local
from .model import StructuralModel
from .project import (
    ElementLoadData,
    MaterialData,
    SectionData,
    TransformationData,
)


LOCAL_FORCE_COMPONENTS: tuple[str, ...] = (
    "N",
    "Vy",
    "Vz",
    "T",
    "My",
    "Mz",
)

LOCAL_FORCE_INDEX: dict[str, int] = {
    name: index
    for index, name in enumerate(LOCAL_FORCE_COMPONENTS)
}

# Current Studio 3D ElasticSection/FiberSection section-resultant order.
# OpenSees source uses P, Mz, My, T for both section classes.
SECTION_FORCE_INDEX: dict[str, int] = {
    "N": 0,
    "Mz": 1,
    "My": 2,
    "T": 3,
}


NODAL_COMPONENT_INDEX: dict[str, int] = {
    "UX": 0,
    "UY": 1,
    "UZ": 2,
    "RX": 3,
    "RY": 4,
    "RZ": 5,
    "FX": 0,
    "FY": 1,
    "FZ": 2,
    "MX": 3,
    "MY": 4,
    "MZ": 5,
}

NODAL_MAGNITUDE_COMPONENTS: dict[str, tuple[int, ...]] = {
    "|U|": (0, 1, 2),
    "|R|": (3, 4, 5),
    "|F|": (0, 1, 2),
    "|M|": (3, 4, 5),
}


def nodal_result_scalar(
    values: Sequence[float],
    component: str,
) -> float | None:
    """Extract one scalar from a six-DOF nodal result vector.

    Displacement aliases (UX..RZ) and reaction aliases (FX..MZ) share the
    same six-DOF ordering. Magnitude components keep translation/force and
    rotation/moment groups separate so incompatible units are never mixed.
    """
    component = str(component).strip().upper()
    index = NODAL_COMPONENT_INDEX.get(component)
    if index is not None:
        if len(values) <= index:
            return None
        return float(values[index])

    magnitude_indices = NODAL_MAGNITUDE_COMPONENTS.get(component)
    if magnitude_indices is not None:
        if len(values) <= max(magnitude_indices):
            return None
        return math.sqrt(sum(float(values[index]) ** 2 for index in magnitude_indices))

    raise ValueError(f"Unsupported nodal result component: {component}")


def pushover_capacity_curve(
    result: dict[str, Any] | None,
) -> tuple[list[float], list[float], int | None, int | None]:
    """Return control displacement and applied base shear for pushover.

    OpenSees support reactions oppose the applied lateral load, so the
    capacity curve uses minus the summed reactions. A positive push therefore
    gives positive control displacement and positive applied base shear.
    """
    if not isinstance(result, dict):
        return [], [], None, None

    analysis = result.get("analysis", {})
    history = result.get("history", {})
    if not isinstance(analysis, dict) or not isinstance(history, dict):
        return [], [], None, None
    if str(analysis.get("type", "")) != "Pushover":
        return [], [], None, None

    control_node_raw = history.get(
        "monitor_node",
        analysis.get("control_node"),
    )
    control_dof_raw = history.get(
        "control_dof",
        analysis.get("control_dof", 1),
    )
    try:
        control_node = (
            int(control_node_raw)
            if control_node_raw is not None
            else None
        )
    except (TypeError, ValueError):
        control_node = None
    try:
        control_dof = int(control_dof_raw)
    except (TypeError, ValueError):
        control_dof = 1
    if control_dof not in range(1, 7):
        control_dof = 1

    displacement_rows = history.get("displacement", [])
    reaction_sums = history.get("base_shear", [])
    if not isinstance(displacement_rows, (list, tuple)):
        return [], [], control_node, control_dof
    if not isinstance(reaction_sums, (list, tuple)):
        return [], [], control_node, control_dof

    x: list[float] = []
    y: list[float] = []
    index = control_dof - 1
    for row, reaction_sum in zip(displacement_rows, reaction_sums):
        if not isinstance(row, (list, tuple)) or len(row) <= index:
            continue
        try:
            displacement = float(row[index])
            base_shear = -float(reaction_sum)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(displacement) or not math.isfinite(base_shear):
            continue
        x.append(displacement)
        y.append(base_shear)

    return x, y, control_node, control_dof


TIME_HISTORY_NODE_KEYS: dict[str, str] = {
    "displacement": "disp",
    "velocity": "vel",
    "acceleration": "accel",
    "reaction": "reaction",
}


def cyclic_hysteresis_curve(
    result: dict[str, Any] | None,
) -> tuple[list[float], list[float], int | None, int | None]:
    """Return control displacement and applied base shear for Cyclic analysis."""
    if not isinstance(result, dict):
        return [], [], None, None
    analysis = result.get("analysis", {})
    history = result.get("history", {})
    if not isinstance(analysis, dict) or not isinstance(history, dict):
        return [], [], None, None
    if str(analysis.get("type", "")) != "Cyclic":
        return [], [], None, None

    try:
        node = int(history.get("monitor_node", analysis.get("control_node")))
    except (TypeError, ValueError):
        node = None
    try:
        dof = int(history.get("control_dof", analysis.get("control_dof", 1)))
    except (TypeError, ValueError):
        dof = 1
    if dof not in range(1, 7):
        dof = 1

    rows = history.get("displacement", [])
    shear = history.get("base_shear", [])
    if not isinstance(rows, (list, tuple)) or not isinstance(shear, (list, tuple)):
        return [], [], node, dof

    x: list[float] = [0.0]
    y: list[float] = [0.0]
    index = dof - 1
    for row, raw_shear in zip(rows, shear):
        if not isinstance(row, (list, tuple)) or len(row) <= index:
            continue
        try:
            displacement = float(row[index])
            base_shear = -float(raw_shear)
        except (TypeError, ValueError):
            continue
        if math.isfinite(displacement) and math.isfinite(base_shear):
            x.append(displacement)
            y.append(base_shear)
    if len(x) == 1:
        return [], [], node, dof
    return x, y, node, dof


def cyclic_reversal_points(
    displacement: Sequence[float],
    force: Sequence[float],
) -> list[dict[str, float]]:
    """Return reversals plus repeated-amplitude strength/stiffness ratios."""
    count = min(len(displacement), len(force))
    if count < 3:
        return []

    x = [float(value) for value in displacement[:count]]
    y = [float(value) for value in force[:count]]
    reversals: list[dict[str, float]] = []

    previous_sign = 0
    for index in range(1, count):
        delta = x[index] - x[index - 1]
        sign = 1 if delta > 1.0e-15 else -1 if delta < -1.0e-15 else 0
        if sign == 0:
            continue
        if previous_sign and sign != previous_sign:
            peak_index = index - 1
            u = x[peak_index]
            v = y[peak_index]
            stiffness = abs(v / u) if abs(u) > 1.0e-15 else math.nan
            reversals.append({
                "index": float(peak_index),
                "displacement": u,
                "force": v,
                "secant_stiffness": stiffness,
            })
        previous_sign = sign

    amplitude_tolerance = max(
        max((abs(value) for value in x), default=0.0) * 1.0e-6,
        1.0e-12,
    )
    references: list[dict[str, float]] = []
    for reversal in reversals:
        u = float(reversal["displacement"])
        v = float(reversal["force"])
        stiffness = float(reversal["secant_stiffness"])
        sign = 1.0 if u >= 0.0 else -1.0
        amplitude = abs(u)

        reference = next(
            (
                item
                for item in references
                if item["sign"] == sign
                and abs(item["amplitude"] - amplitude)
                <= amplitude_tolerance
            ),
            None,
        )
        if reference is None:
            reference = {
                "sign": sign,
                "amplitude": amplitude,
                "force": abs(v),
                "stiffness": abs(stiffness),
                "count": 0.0,
            }
            references.append(reference)

        reference["count"] += 1.0
        ref_force = float(reference["force"])
        ref_stiffness = float(reference["stiffness"])
        reversal["repeat_index"] = float(reference["count"])
        reversal["strength_ratio"] = (
            abs(v) / ref_force
            if ref_force > 1.0e-15
            else math.nan
        )
        reversal["stiffness_ratio"] = (
            abs(stiffness) / ref_stiffness
            if ref_stiffness > 1.0e-15
            and math.isfinite(ref_stiffness)
            else math.nan
        )

    return reversals


def cyclic_closed_cycle_energies(
    displacement: Sequence[float],
    force: Sequence[float],
    reversals: Sequence[dict[str, float]] | None = None,
) -> list[dict[str, float]]:
    """Estimate energy for repeated closed cycles at the same positive peak."""
    count = min(len(displacement), len(force))
    if count < 4:
        return []
    x = [float(value) for value in displacement[:count]]
    y = [float(value) for value in force[:count]]
    points = list(reversals or cyclic_reversal_points(x, y))
    positives = [
        item
        for item in points
        if float(item.get("displacement", 0.0)) > 1.0e-15
    ]
    tolerance = max(
        max((abs(value) for value in x), default=0.0) * 1.0e-6,
        1.0e-12,
    )
    cycles: list[dict[str, float]] = []
    last_by_amplitude: list[tuple[float, int]] = []
    for reversal in positives:
        amplitude = abs(float(reversal["displacement"]))
        index = int(round(float(reversal["index"])))
        match_index = None
        match_slot = None
        for slot, (known_amplitude, known_index) in enumerate(
            last_by_amplitude
        ):
            if abs(known_amplitude - amplitude) <= tolerance:
                match_index = known_index
                match_slot = slot
                break
        if match_index is not None and index > match_index + 1:
            signed = sum(
                0.5 * (y[i] + y[i - 1]) * (x[i] - x[i - 1])
                for i in range(match_index + 1, index + 1)
            )
            cycles.append({
                "amplitude": amplitude,
                "start_index": float(match_index),
                "end_index": float(index),
                "energy": abs(signed),
            })
        if match_slot is None:
            last_by_amplitude.append((amplitude, index))
        else:
            last_by_amplitude[match_slot] = (amplitude, index)
    return cycles


def cyclic_hysteresis_metrics(
    displacement: Sequence[float],
    force: Sequence[float],
) -> dict[str, Any]:
    """Summarize a cyclic force-displacement path."""
    count = min(len(displacement), len(force))
    if count < 2:
        return {
            "signed_work": 0.0,
            "dissipated_energy": None,
            "closed_path": False,
            "max_abs_displacement": 0.0,
            "max_abs_force": 0.0,
            "reversals": [],
        }

    x = [float(value) for value in displacement[:count]]
    y = [float(value) for value in force[:count]]
    signed_work = sum(
        0.5 * (y[index] + y[index - 1]) * (x[index] - x[index - 1])
        for index in range(1, count)
    )
    max_abs_displacement = max(abs(value) for value in x)
    max_abs_force = max(abs(value) for value in y)
    tolerance = max(max_abs_displacement, 1.0) * 1.0e-8
    closed_path = abs(x[-1] - x[0]) <= tolerance

    reversals = cyclic_reversal_points(x, y)
    cycle_energies = cyclic_closed_cycle_energies(x, y, reversals)
    return {
        "signed_work": signed_work,
        "dissipated_energy": abs(signed_work) if closed_path else None,
        "closed_path": closed_path,
        "max_abs_displacement": max_abs_displacement,
        "max_abs_force": max_abs_force,
        "peak_positive_force": max(y),
        "peak_negative_force": min(y),
        "residual_displacement": x[-1],
        "reversals": reversals,
        "cycle_energies": cycle_energies,
        "closed_cycle_count": len(cycle_energies),
    }



def test_column_moment_curvature_curve(
    result: dict[str, Any] | None,
) -> tuple[list[float], list[float], str]:
    """Return base-section curvature and moment for a Quick 1D Column."""
    if not isinstance(result, dict):
        return [], [], ""
    specimen = result.get("specimen", {})
    history = result.get("history", {})
    if not isinstance(specimen, dict) or not isinstance(history, dict):
        return [], [], ""
    specimen_history = history.get("specimen", {})
    if not isinstance(specimen_history, dict):
        return [], [], ""

    try:
        index = int(specimen.get("moment_index", 1))
        sign = float(specimen.get("moment_sign", 1.0))
    except (TypeError, ValueError):
        return [], [], ""
    force_rows = specimen_history.get("section_force", [])
    deformation_rows = specimen_history.get("section_deformation", [])
    if not isinstance(force_rows, (list, tuple)):
        return [], [], ""
    if not isinstance(deformation_rows, (list, tuple)):
        return [], [], ""

    curvature: list[float] = []
    moment: list[float] = []
    for force_row, deformation_row in zip(force_rows, deformation_rows):
        if (
            not isinstance(force_row, (list, tuple))
            or not isinstance(deformation_row, (list, tuple))
            or len(force_row) <= index
            or len(deformation_row) <= index
        ):
            continue
        try:
            force_value = sign * float(force_row[index])
            deformation_value = sign * float(deformation_row[index])
        except (TypeError, ValueError):
            continue
        if math.isfinite(force_value) and math.isfinite(deformation_value):
            curvature.append(deformation_value)
            moment.append(force_value)

    if curvature and (
        abs(curvature[0]) > 1.0e-15 or abs(moment[0]) > 1.0e-15
    ):
        curvature.insert(0, 0.0)
        moment.insert(0, 0.0)
    return curvature, moment, str(specimen.get("moment_component", ""))


def test_column_rotation_decomposition(
    result: dict[str, Any] | None,
) -> dict[str, list[float]]:
    """Split total drift angle into member, interface-rotation and slip parts.

    The member contribution is drift-equivalent: total top drift angle minus
    rigid interface rotation minus lateral interface slip divided by height.
    This is a kinematic diagnostic, not a section-curvature integration.
    """
    empty = {
        "time": [],
        "total": [],
        "column": [],
        "interface_rotation": [],
        "interface_slip": [],
    }
    if not isinstance(result, dict):
        return empty
    specimen = result.get("specimen", {})
    history = result.get("history", {})
    if not isinstance(specimen, dict) or not isinstance(history, dict):
        return empty
    specimen_history = history.get("specimen", {})
    nodes = history.get("nodes", {})
    times = history.get("time", [])
    if (
        not isinstance(specimen_history, dict)
        or not isinstance(nodes, dict)
        or not isinstance(times, (list, tuple))
    ):
        return empty

    try:
        height = abs(float(specimen.get("height", 0.0)))
        lateral_index = int(specimen.get("lateral_direction", 1)) - 1
        rotation_index = int(specimen.get("bending_rotation_dof", 4)) - 1
        moment_index = int(specimen.get("moment_index", 1))
        sign = float(specimen.get("moment_sign", 1.0))
        top_node = int(specimen.get("top_node"))
        base_node = int(specimen.get("base_node"))
    except (TypeError, ValueError):
        return empty
    if height <= 1.0e-15 or lateral_index not in range(3):
        return empty

    ground_raw = specimen.get("ground_node")
    try:
        ground_node = int(ground_raw) if ground_raw is not None else None
    except (TypeError, ValueError):
        ground_node = None

    def displacement_rows(node_tag: int | None) -> list[Any]:
        if node_tag is None:
            return []
        payload = nodes.get(str(node_tag), nodes.get(node_tag, {}))
        if not isinstance(payload, dict):
            return []
        rows = payload.get("disp", [])
        return list(rows) if isinstance(rows, (list, tuple)) else []

    top_rows = displacement_rows(top_node)
    base_rows = displacement_rows(base_node)
    ground_rows = displacement_rows(ground_node)
    interface_rows = specimen_history.get("interface_deformation", [])
    if not isinstance(interface_rows, (list, tuple)):
        interface_rows = []

    result_rows = {
        "time": [],
        "total": [],
        "column": [],
        "interface_rotation": [],
        "interface_slip": [],
    }
    count = min(len(times), len(top_rows))
    for index in range(count):
        top = top_rows[index]
        if not isinstance(top, (list, tuple)) or len(top) <= lateral_index:
            continue
        base = (
            base_rows[index]
            if index < len(base_rows)
            and isinstance(base_rows[index], (list, tuple))
            else []
        )
        ground = (
            ground_rows[index]
            if index < len(ground_rows)
            and isinstance(ground_rows[index], (list, tuple))
            else []
        )

        try:
            top_u = float(top[lateral_index])
            base_u = (
                float(base[lateral_index])
                if len(base) > lateral_index
                else 0.0
            )
            ground_u = (
                float(ground[lateral_index])
                if len(ground) > lateral_index
                else 0.0
            )
            time_value = float(times[index])
        except (TypeError, ValueError):
            continue

        total = (top_u - ground_u) / height
        slip = (base_u - ground_u) / height

        interface_rotation = 0.0
        row = (
            interface_rows[index]
            if index < len(interface_rows)
            and isinstance(interface_rows[index], (list, tuple))
            else []
        )
        interface_type = str(specimen.get("interface_type", ""))
        if (
            interface_type == "zeroLengthSection"
            and len(row) > moment_index
        ):
            try:
                interface_rotation = sign * float(row[moment_index])
            except (TypeError, ValueError):
                interface_rotation = 0.0
        elif ground_node is not None:
            try:
                base_r = (
                    float(base[rotation_index])
                    if len(base) > rotation_index
                    else 0.0
                )
                ground_r = (
                    float(ground[rotation_index])
                    if len(ground) > rotation_index
                    else 0.0
                )
                interface_rotation = base_r - ground_r
            except (TypeError, ValueError):
                interface_rotation = 0.0

        values = (time_value, total, interface_rotation, slip)
        if not all(math.isfinite(value) for value in values):
            continue
        column = total - interface_rotation - slip
        result_rows["time"].append(time_value)
        result_rows["total"].append(total)
        result_rows["interface_rotation"].append(interface_rotation)
        result_rows["interface_slip"].append(slip)
        result_rows["column"].append(column)

    return result_rows


def test_column_fiber_history_catalog(
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return selectable critical-fiber histories captured for the specimen."""
    if not isinstance(result, dict):
        return []
    history = result.get("history", {})
    if not isinstance(history, dict):
        return []
    specimen_history = history.get("specimen", {})
    times = history.get("time", [])
    if (
        not isinstance(specimen_history, dict)
        or not isinstance(times, (list, tuple))
    ):
        return []

    catalog: list[dict[str, Any]] = []
    for source, history_key, quantities in (
        ("Base section", "base_fibers", ("stress", "strain")),
        ("Bond interface", "interface_fibers", ("stress", "slip")),
    ):
        snapshots = specimen_history.get(history_key, [])
        if not isinstance(snapshots, (list, tuple)) or not snapshots:
            continue

        identities: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            if not isinstance(snapshot, list):
                continue
            for fiber in snapshot:
                if not isinstance(fiber, dict):
                    continue
                label = str(fiber.get("label", "") or "")
                if label and label not in identities:
                    identities[label] = dict(fiber)

        for label, metadata in sorted(identities.items()):
            for quantity in quantities:
                x: list[float] = []
                y: list[float] = []
                for time_value, snapshot in zip(times, snapshots):
                    if not isinstance(snapshot, list):
                        continue
                    match = next(
                        (
                            fiber
                            for fiber in snapshot
                            if isinstance(fiber, dict)
                            and str(fiber.get("label", "")) == label
                        ),
                        None,
                    )
                    if match is None or match.get(quantity) is None:
                        continue
                    try:
                        tx = float(time_value)
                        value = float(match[quantity])
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(tx) and math.isfinite(value):
                        x.append(tx)
                        y.append(value)
                if not y:
                    continue
                catalog.append({
                    "key": f"{history_key}:{label}:{quantity}",
                    "source": source,
                    "label": label,
                    "quantity": quantity,
                    "x": x,
                    "y": y,
                    "material_tag": metadata.get("material_tag"),
                    "material_type": metadata.get("material_type"),
                    "y_coord": metadata.get("y"),
                    "z_coord": metadata.get("z"),
                    "latest": y[-1],
                })
    return catalog


def test_column_response_summary(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize the specialized 1D-column instrumentation."""
    curvature, moment, component = test_column_moment_curvature_curve(result)
    rotations = test_column_rotation_decomposition(result)
    fibers = test_column_fiber_history_catalog(result)

    def maximum_absolute(values: Sequence[float]) -> float | None:
        finite = [
            abs(float(value))
            for value in values
            if math.isfinite(float(value))
        ]
        return max(finite) if finite else None

    return {
        "moment_component": component,
        "max_abs_moment": maximum_absolute(moment),
        "max_abs_curvature": maximum_absolute(curvature),
        "max_abs_total_drift": maximum_absolute(rotations["total"]),
        "max_abs_interface_rotation": maximum_absolute(
            rotations["interface_rotation"]
        ),
        "max_abs_interface_slip_drift": maximum_absolute(
            rotations["interface_slip"]
        ),
        "critical_fibers": fibers,
    }


def convergence_steps(
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return normalized per-step convergence records."""
    if not isinstance(result, dict):
        return []
    convergence = result.get("convergence", {})
    if not isinstance(convergence, dict):
        return []
    raw_steps = convergence.get("steps", [])
    if not isinstance(raw_steps, list):
        return []

    rows: list[dict[str, Any]] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        try:
            step = int(raw.get("step", 0))
        except (TypeError, ValueError):
            continue
        row = dict(raw)
        row["step"] = step
        attempts = row.get("attempts", [])
        row["attempts"] = (
            [dict(item) for item in attempts if isinstance(item, dict)]
            if isinstance(attempts, list)
            else []
        )
        rows.append(row)
    return sorted(rows, key=lambda item: int(item["step"]))


def convergence_summary(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize solver convergence performance for the dashboard."""
    steps = convergence_steps(result)
    algorithms: set[str] = set()
    total_attempts = 0
    recovered = 0
    failed = 0
    max_iterations = 0
    total_cutbacks = 0
    adaptive_steps = 0
    minimum_step_size: float | None = None
    worst_norm: float | None = None
    worst_step: int | None = None

    for row in steps:
        if bool(row.get("recovered")):
            recovered += 1
        if str(row.get("status", "")) == "failed":
            failed += 1
        if bool(row.get("adaptive")):
            adaptive_steps += 1
        try:
            total_cutbacks += int(row.get("cutbacks", 0) or 0)
        except (TypeError, ValueError):
            pass
        raw_min_step = row.get("min_step_size_used")
        if raw_min_step is not None:
            try:
                min_step = abs(float(raw_min_step))
            except (TypeError, ValueError):
                min_step = math.nan
            if math.isfinite(min_step) and (
                minimum_step_size is None or min_step < minimum_step_size
            ):
                minimum_step_size = min_step

        attempts = row.get("attempts", [])
        if isinstance(attempts, list):
            total_attempts += len(attempts)
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                algorithm = str(attempt.get("algorithm", "") or "")
                if algorithm:
                    algorithms.add(algorithm)

        try:
            iterations = int(row.get("iterations", 0) or 0)
        except (TypeError, ValueError):
            iterations = 0
        max_iterations = max(max_iterations, iterations)

        raw_norm = row.get("norm")
        if raw_norm is not None:
            try:
                norm = abs(float(raw_norm))
            except (TypeError, ValueError):
                norm = math.nan
            if math.isfinite(norm) and (
                worst_norm is None or norm > worst_norm
            ):
                worst_norm = norm
                worst_step = int(row["step"])

    convergence = (
        result.get("convergence", {})
        if isinstance(result, dict)
        else {}
    )
    if not isinstance(convergence, dict):
        convergence = {}

    return {
        "steps": len(steps),
        "converged": sum(
            1
            for row in steps
            if str(row.get("status", "")) == "converged"
        ),
        "recovered": recovered,
        "failed": failed,
        "total_attempts": total_attempts,
        "max_iterations_used": max_iterations,
        "adaptive_steps": adaptive_steps,
        "total_cutbacks": total_cutbacks,
        "minimum_step_size": minimum_step_size,
        "worst_norm": worst_norm,
        "worst_step": worst_step,
        "algorithms": sorted(algorithms),
        "test": str(convergence.get("test", "") or ""),
        "tolerance": convergence.get("tolerance"),
        "configured_max_iterations": convergence.get("max_iterations"),
        "primary_algorithm": str(
            convergence.get("primary_algorithm", "") or ""
        ),
        "adaptive_step": bool(convergence.get("adaptive_step", False)),
        "cutback_factor": convergence.get("cutback_factor"),
        "minimum_factor": convergence.get("minimum_factor"),
        "growth_factor": convergence.get("growth_factor"),
    }


def convergence_trace(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return an ANSYS-style cumulative-iteration convergence trace."""
    convergence = (
        result.get("convergence", {})
        if isinstance(result, dict)
        else {}
    )
    if not isinstance(convergence, dict):
        convergence = {}

    tolerance = convergence.get("tolerance")
    try:
        tolerance_value = (
            abs(float(tolerance))
            if tolerance is not None
            else None
        )
    except (TypeError, ValueError):
        tolerance_value = None
    if (
        tolerance_value is not None
        and (
            not math.isfinite(tolerance_value)
            or tolerance_value <= 0.0
        )
    ):
        tolerance_value = None

    cumulative = 0
    norm_x: list[float] = []
    norm_y: list[float] = []
    cutbacks: list[float] = []
    converged: list[float] = []
    coordinate_x: list[float] = [0.0]
    coordinate_y: list[float] = [0.0]

    def append_attempts(raw_attempts: Any) -> None:
        nonlocal cumulative
        attempts = raw_attempts if isinstance(raw_attempts, list) else []
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            history = attempt.get("norm_history", [])
            used_history = False
            if isinstance(history, (list, tuple)):
                for raw_norm in history:
                    try:
                        norm = abs(float(raw_norm))
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(norm) or norm <= 0.0:
                        continue
                    cumulative += 1
                    norm_x.append(float(cumulative))
                    norm_y.append(norm)
                    used_history = True

            if used_history:
                continue

            try:
                iterations = max(
                    0,
                    int(attempt.get("iterations", 0) or 0),
                )
            except (TypeError, ValueError):
                iterations = 0
            raw_norm = attempt.get("norm")
            try:
                norm = (
                    abs(float(raw_norm))
                    if raw_norm is not None
                    else None
                )
            except (TypeError, ValueError):
                norm = None
            if iterations > 0:
                cumulative += iterations
            elif norm is not None:
                cumulative += 1
            if (
                norm is not None
                and math.isfinite(norm)
                and norm > 0.0
            ):
                norm_x.append(float(cumulative))
                norm_y.append(norm)

    for row in convergence_steps(result):
        substeps = row.get("substeps", [])
        if isinstance(substeps, list) and substeps:
            for substep in substeps:
                if not isinstance(substep, dict):
                    continue
                append_attempts(substep.get("attempts", []))
                marker_x = float(cumulative)
                if bool(substep.get("accepted")):
                    if marker_x > 0.0:
                        converged.append(marker_x)
                    raw_coordinate = substep.get("time")
                    if raw_coordinate is not None:
                        try:
                            coordinate = float(raw_coordinate)
                        except (TypeError, ValueError):
                            coordinate = math.nan
                        if math.isfinite(coordinate):
                            coordinate_x.append(marker_x)
                            coordinate_y.append(coordinate)
                elif marker_x > 0.0:
                    cutbacks.append(marker_x)
        else:
            append_attempts(row.get("attempts", []))
            marker_x = float(cumulative)
            if str(row.get("status", "")) != "failed" and marker_x > 0.0:
                converged.append(marker_x)
            try:
                cutback_count = int(row.get("cutbacks", 0) or 0)
            except (TypeError, ValueError):
                cutback_count = 0
            if cutback_count > 0 and marker_x > 0.0:
                cutbacks.extend([marker_x] * cutback_count)

        raw_coordinate = row.get("time")
        if raw_coordinate is not None and cumulative > 0:
            try:
                coordinate = float(raw_coordinate)
            except (TypeError, ValueError):
                coordinate = math.nan
            if math.isfinite(coordinate):
                marker_x = float(cumulative)
                if (
                    coordinate_x[-1] != marker_x
                    or coordinate_y[-1] != coordinate
                ):
                    coordinate_x.append(marker_x)
                    coordinate_y.append(coordinate)

    return {
        "iteration": norm_x,
        "norm": norm_y,
        "criterion": tolerance_value,
        "cutbacks": cutbacks,
        "converged": converged,
        "coordinate_iteration": coordinate_x,
        "coordinate": coordinate_y,
        "total_iterations": cumulative,
    }

def convergence_series(
    result: dict[str, Any] | None,
    quantity: str,
) -> tuple[list[float], list[float]]:
    """Return step-number series for iteration count or final convergence norm."""
    key = str(quantity).strip().lower()
    if key not in {"iterations", "norm"}:
        raise ValueError(
            f"Unsupported convergence series quantity: {quantity}"
        )

    x: list[float] = []
    y: list[float] = []
    for row in convergence_steps(result):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        if key == "norm":
            value = abs(value)
        x.append(float(row["step"]))
        y.append(value)
    return x, y


def time_history_node_tags(
    result: dict[str, Any] | None,
) -> list[int]:
    """Return sorted node tags that have recorded nodal histories."""
    if not isinstance(result, dict):
        return []
    history = result.get("history", {})
    if not isinstance(history, dict):
        return []

    nodes = history.get("nodes", {})
    tags: list[int] = []
    if isinstance(nodes, dict):
        for raw_tag in nodes:
            try:
                tags.append(int(raw_tag))
            except (TypeError, ValueError):
                continue
    if tags:
        return sorted(set(tags))

    # Backward compatibility with schema <= 3, which recorded only the
    # monitor-node displacement history.
    try:
        monitor = int(history.get("monitor_node"))
    except (TypeError, ValueError):
        return []
    return [monitor]


def time_history_series(
    result: dict[str, Any] | None,
    quantity: str,
    *,
    node_tag: int | None = None,
    dof: int = 1,
) -> tuple[list[float], list[float]]:
    """Extract a nodal or base-response time-history series.

    Base shear uses the applied-equivalent sign convention: minus the summed
    support reactions. Nodal reactions keep the native OpenSees sign.
    """
    if not isinstance(result, dict):
        return [], []
    history = result.get("history", {})
    if not isinstance(history, dict):
        return [], []

    try:
        dof = int(dof)
    except (TypeError, ValueError):
        return [], []
    if dof not in range(1, 7):
        return [], []

    raw_time = history.get("time", [])
    if not isinstance(raw_time, (list, tuple)):
        return [], []
    times: list[float] = []
    for value in raw_time:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return [], []
        if not math.isfinite(numeric):
            return [], []
        times.append(numeric)

    normalized = str(quantity).strip().lower()
    if normalized == "base shear":
        if dof > 3:
            return [], []
        rows = history.get("base_reactions", [])
        if isinstance(rows, (list, tuple)) and rows:
            values: list[float] = []
            selected_time: list[float] = []
            index = dof - 1
            for time_value, row in zip(times, rows):
                if not isinstance(row, (list, tuple)) or len(row) <= index:
                    continue
                try:
                    value = -float(row[index])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value):
                    selected_time.append(time_value)
                    values.append(value)
            return selected_time, values

        # Schema <= 3 stored only the reaction sum for the control DOF.
        try:
            control_dof = int(history.get("control_dof", 1))
        except (TypeError, ValueError):
            control_dof = 1
        if dof != control_dof:
            return [], []
        raw_values = history.get("base_shear", [])
        if not isinstance(raw_values, (list, tuple)):
            return [], []
        selected_time = []
        values = []
        for time_value, raw_value in zip(times, raw_values):
            try:
                value = -float(raw_value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                selected_time.append(time_value)
                values.append(value)
        return selected_time, values

    key = TIME_HISTORY_NODE_KEYS.get(normalized)
    if key is None or node_tag is None:
        return [], []

    nodes = history.get("nodes", {})
    rows: Any = []
    if isinstance(nodes, dict):
        node_data = nodes.get(str(int(node_tag)), nodes.get(int(node_tag), {}))
        if isinstance(node_data, dict):
            rows = node_data.get(key, [])

    if (
        normalized == "displacement"
        and (not isinstance(rows, (list, tuple)) or not rows)
    ):
        try:
            monitor_node = int(history.get("monitor_node"))
        except (TypeError, ValueError):
            monitor_node = None
        if monitor_node == int(node_tag):
            rows = history.get("displacement", [])

    if not isinstance(rows, (list, tuple)):
        return [], []

    index = dof - 1
    selected_time: list[float] = []
    values: list[float] = []
    for time_value, row in zip(times, rows):
        if not isinstance(row, (list, tuple)) or len(row) <= index:
            continue
        try:
            value = float(row[index])
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            selected_time.append(time_value)
            values.append(value)
    return selected_time, values


def fiber_response_element_tags(
    result: dict[str, Any] | None,
) -> list[int]:
    """Return sorted element tags with captured fiber responses."""
    if not isinstance(result, dict):
        return []
    final = result.get("final", {})
    if not isinstance(final, dict):
        return []
    data = final.get("element_fiber_responses", {})
    if not isinstance(data, dict):
        return []
    tags: list[int] = []
    for raw_tag, payload in data.items():
        if not isinstance(payload, dict):
            continue
        sections = payload.get("sections", [])
        if not isinstance(sections, list) or not sections:
            continue
        try:
            tags.append(int(raw_tag))
        except (TypeError, ValueError):
            continue
    return sorted(set(tags))


def fiber_response_sections(
    result: dict[str, Any] | None,
    element_tag: int,
) -> list[dict[str, Any]]:
    """Return normalized fiber-response sections for one element."""
    if not isinstance(result, dict):
        return []
    final = result.get("final", {})
    if not isinstance(final, dict):
        return []
    data = final.get("element_fiber_responses", {})
    if not isinstance(data, dict):
        return []
    payload = data.get(str(int(element_tag)), data.get(int(element_tag), {}))
    if not isinstance(payload, dict):
        return []
    sections = payload.get("sections", [])
    if not isinstance(sections, list):
        return []
    result_sections: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        fibers = section.get("fibers", [])
        if not isinstance(fibers, list):
            continue
        result_sections.append(section)
    return result_sections


def fiber_response_range(
    section: dict[str, Any] | None,
    quantity: str,
) -> tuple[float | None, float | None]:
    """Return finite min/max stress or strain for a fiber section."""
    if not isinstance(section, dict):
        return None, None
    key = str(quantity).strip().lower()
    if key not in {"stress", "strain"}:
        raise ValueError(f"Unsupported fiber-response quantity: {quantity}")
    values: list[float] = []
    fibers = section.get("fibers", [])
    if not isinstance(fibers, list):
        return None, None
    for fiber in fibers:
        if not isinstance(fiber, dict):
            continue
        raw = fiber.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    if not values:
        return None, None
    return min(values), max(values)


FIBER_STATE_LABELS: dict[int, str] = {
    0: "Elastic",
    1: "Nonlinear / near yield",
    2: "Yielding / softening",
    3: "Plastic / crushing",
}


def classify_fiber_state(
    fiber: dict[str, Any] | None,
    materials: dict[int, MaterialData],
) -> dict[str, Any]:
    """Classify one fiber using material-specific strain limits.

    The classification is intentionally diagnostic rather than a code-based
    acceptance check. Steel02 uses yield strain Fy/E0. Concrete02 uses the
    cracking strain ft/Ec, peak-compression strain epsc0, and ultimate
    compression strain epsU.
    """
    if not isinstance(fiber, dict):
        return {
            "severity": -1,
            "state": "Unknown",
            "material_type": "Unknown",
            "metric": None,
        }

    try:
        material_tag = int(fiber.get("material_tag"))
    except (TypeError, ValueError):
        material_tag = 0
    material = materials.get(material_tag)
    if material is None:
        return {
            "severity": -1,
            "state": "Unknown",
            "material_tag": material_tag,
            "material_type": "Unknown",
            "metric": None,
        }

    try:
        strain = float(fiber.get("strain"))
    except (TypeError, ValueError):
        strain = math.nan
    if not math.isfinite(strain):
        return {
            "severity": -1,
            "state": "Unknown",
            "material_tag": material_tag,
            "material_type": material.material_type,
            "metric": None,
        }

    severity = 0
    state = FIBER_STATE_LABELS[0]
    metric: float | None = None
    details: dict[str, Any] = {}

    if material.material_type == "Steel02":
        fy = abs(float(material.parameters["Fy"]))
        e0 = abs(float(material.parameters["E0"]))
        eps_y = fy / e0 if e0 > 1.0e-30 else math.inf
        ratio = abs(strain) / eps_y if eps_y > 1.0e-30 else 0.0
        metric = ratio
        details["yield_strain"] = eps_y
        details["strain_to_yield"] = ratio
        if ratio >= 2.0:
            severity = 3
            state = "Plastic"
        elif ratio >= 1.0:
            severity = 2
            state = "Yielding"
        elif ratio >= 0.8:
            severity = 1
            state = "Near yield"

    elif material.material_type == "Concrete02":
        epsc0 = float(material.parameters["epsc0"])
        eps_u = float(material.parameters["epsU"])
        ft = max(float(material.parameters["ft"]), 0.0)
        try:
            ec = abs(float(material.elastic_modulus()))
        except ValueError:
            ec = 0.0
        eps_cr = ft / ec if ec > 1.0e-30 else math.inf
        details["cracking_strain"] = eps_cr
        details["peak_compression_strain"] = epsc0
        details["ultimate_compression_strain"] = eps_u

        if strain < 0.0 and epsc0 < 0.0:
            compression_ratio = abs(strain) / max(abs(epsc0), 1.0e-30)
            metric = compression_ratio
            if eps_u < 0.0 and strain <= eps_u:
                severity = 3
                state = "Crushing limit"
            elif strain <= epsc0:
                severity = 2
                state = "Compression softening"
            elif compression_ratio >= 0.8:
                severity = 1
                state = "Nonlinear compression"
        elif strain > 0.0 and math.isfinite(eps_cr) and eps_cr > 0.0:
            tension_ratio = strain / eps_cr
            metric = tension_ratio
            if tension_ratio >= 1.0:
                severity = 1
                state = "Tension cracked"

    elif material.material_type == "Elastic":
        metric = 0.0

    return {
        "severity": severity,
        "state": state,
        "material_tag": material_tag,
        "material_type": material.material_type,
        "strain": strain,
        "stress": fiber.get("stress"),
        "metric": metric,
        **details,
    }


def enrich_fiber_state_results(
    result: dict[str, Any],
    materials: dict[int, MaterialData],
) -> dict[str, Any]:
    """Attach section/element state summaries derived from fiber responses."""
    enriched = copy.deepcopy(result)
    final = enriched.setdefault("final", {})
    if not isinstance(final, dict):
        return enriched

    fiber_data = final.get("element_fiber_responses", {})
    if not isinstance(fiber_data, dict):
        return enriched

    summary: dict[str, Any] = {}
    for raw_tag, payload in fiber_data.items():
        if not isinstance(payload, dict):
            continue
        sections = payload.get("sections", [])
        if not isinstance(sections, list):
            continue

        section_rows: list[dict[str, Any]] = []
        element_severity = -1
        hinge_count = 0

        for section in sections:
            if not isinstance(section, dict):
                continue
            fibers = section.get("fibers", [])
            if not isinstance(fibers, list):
                fibers = []

            fiber_states: list[dict[str, Any]] = []
            controlling: dict[str, Any] | None = None
            section_severity = -1

            for index, fiber in enumerate(fibers):
                state = classify_fiber_state(
                    fiber if isinstance(fiber, dict) else None,
                    materials,
                )
                state = dict(state)
                state["fiber_index"] = index
                fiber_states.append(state)
                severity = int(state.get("severity", -1))
                if severity > section_severity:
                    section_severity = severity
                    controlling = {
                        **state,
                        "fiber_index": index,
                        "y": (
                            fiber.get("y")
                            if isinstance(fiber, dict)
                            else None
                        ),
                        "z": (
                            fiber.get("z")
                            if isinstance(fiber, dict)
                            else None
                        ),
                    }

            if section_severity < 0:
                section_state = "Unknown"
            else:
                section_state = FIBER_STATE_LABELS.get(
                    section_severity,
                    "Unknown",
                )
            if section_severity >= 2:
                hinge_count += 1
            element_severity = max(element_severity, section_severity)

            section_rows.append({
                "number": section.get("number"),
                "location": section.get("location"),
                "severity": section_severity,
                "state": section_state,
                "controlling_fiber": controlling,
                "fiber_states": fiber_states,
            })

        summary[str(raw_tag)] = {
            "severity": element_severity,
            "state": (
                FIBER_STATE_LABELS.get(element_severity, "Unknown")
                if element_severity >= 0
                else "Unknown"
            ),
            "hinge_count": hinge_count,
            "sections": section_rows,
        }

    final["fiber_state_summary"] = summary
    return enriched


def fiber_state_element_tags(
    result: dict[str, Any] | None,
) -> list[int]:
    if not isinstance(result, dict):
        return []
    final = result.get("final", {})
    if not isinstance(final, dict):
        return []
    summary = final.get("fiber_state_summary", {})
    if not isinstance(summary, dict):
        return []
    tags: list[int] = []
    for raw_tag, payload in summary.items():
        if not isinstance(payload, dict):
            continue
        try:
            tags.append(int(raw_tag))
        except (TypeError, ValueError):
            continue
    return sorted(set(tags))


def fiber_state_sections(
    result: dict[str, Any] | None,
    element_tag: int,
) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    final = result.get("final", {})
    if not isinstance(final, dict):
        return []
    summary = final.get("fiber_state_summary", {})
    if not isinstance(summary, dict):
        return []
    payload = summary.get(
        str(int(element_tag)),
        summary.get(int(element_tag), {}),
    )
    if not isinstance(payload, dict):
        return []
    sections = payload.get("sections", [])
    return [
        section
        for section in sections
        if isinstance(section, dict)
    ] if isinstance(sections, list) else []


def local_end_actions(
    values: Sequence[float],
) -> dict[str, tuple[float, float]]:
    """Return OpenSees local nodal end actions for a 3D frame element.

    OpenSees orders the 12 local-force values by the six local DOFs at
    node I followed by the six local DOFs at node J:
    Fx, Fy, Fz, Mx, My, Mz at each end.
    """
    if len(values) < 12:
        return {}
    numeric = [float(value) for value in values[:12]]
    return {
        component: (
            numeric[index],
            numeric[index + 6],
        )
        for component, index in LOCAL_FORCE_INDEX.items()
    }


def member_end_resultants(
    values: Sequence[float],
) -> dict[str, tuple[float, float]]:
    """Convert local nodal actions to OpenSees section-resultant signs.

    The signs follow the 3D beam-column section convention used internally
    by OpenSees. The local-y shear is the one exception to the simple
    "reverse I / retain J" rule: Vy_I is retained and Vy_J is reversed.
    """
    actions = local_end_actions(values)
    if not actions:
        return {}

    result: dict[str, tuple[float, float]] = {}
    for component, (end_i, end_j) in actions.items():
        if component == "Vy":
            result[component] = (end_i, -end_j)
        else:
            result[component] = (-end_i, end_j)
    return result


def component_end_resultants(
    values: Sequence[float],
    component: str,
) -> tuple[float, float] | None:
    component = str(component)
    if component not in LOCAL_FORCE_INDEX:
        raise ValueError(
            f"Unsupported local force component: {component}"
        )
    return member_end_resultants(values).get(component)


def section_component_samples(
    section_data: dict[str, Any] | None,
    component: str,
) -> list[tuple[float, float]]:
    """Return (physical x, resultant) values captured at integration points."""
    component = str(component)
    index = SECTION_FORCE_INDEX.get(component)
    if index is None or not isinstance(section_data, dict):
        return []

    locations = section_data.get("locations", [])
    forces = section_data.get("forces", [])
    if not isinstance(locations, (list, tuple)):
        return []
    if not isinstance(forces, (list, tuple)):
        return []

    samples: list[tuple[float, float]] = []
    for location, vector in zip(locations, forces):
        if not isinstance(vector, (list, tuple)) or len(vector) <= index:
            continue
        samples.append((float(location), float(vector[index])))
    return samples


def _active_load_factor(
    load: ElementLoadData,
    load_factors: dict[str, Any] | dict[int, Any],
) -> float | None:
    if str(load.pattern_tag) in load_factors:
        return float(load_factors[str(load.pattern_tag)])
    if load.pattern_tag in load_factors:
        return float(load_factors[load.pattern_tag])
    return None


def _active_local_element_loads(
    element_tag: int,
    element_loads: dict[int, ElementLoadData],
    load_factors: dict[str, Any] | dict[int, Any],
    model: StructuralModel,
    sections: dict[int, SectionData],
    materials: dict[int, MaterialData],
    transformations: dict[int, TransformationData],
    units: dict[str, str] | None,
) -> list[dict[str, float]] | None:
    active: list[dict[str, float]] = []
    for load in sorted(element_loads.values(), key=lambda item: item.tag):
        if load.element_tag != element_tag:
            continue
        factor = _active_load_factor(load, load_factors)
        if factor is None:
            return None

        if load.load_type == "Uniform":
            active.append({
                "type": "Uniform",
                "wx": factor * load.wx,
                "wy": factor * load.wy,
                "wz": factor * load.wz,
            })
        elif load.load_type == "Point":
            active.append({
                "type": "Point",
                "px": factor * load.px,
                "py": factor * load.py,
                "pz": factor * load.pz,
                "x_over_l": load.x_over_l,
            })
        elif load.load_type == "SelfWeight":
            wx, wy, wz = resolve_self_weight_local(
                load,
                model,
                sections,
                materials,
                transformations,
                units,
            )
            active.append({
                "type": "Uniform",
                "wx": factor * wx,
                "wy": factor * wy,
                "wz": factor * wz,
            })
        else:
            return None
    return active


def _aggregate_uniform(
    active_loads: Sequence[dict[str, float]],
) -> tuple[float, float, float]:
    wx = wy = wz = 0.0
    for load in active_loads:
        if load.get("type") != "Uniform":
            continue
        wx += float(load.get("wx", 0.0))
        wy += float(load.get("wy", 0.0))
        wz += float(load.get("wz", 0.0))
    return wx, wy, wz


def _point_loads(
    active_loads: Sequence[dict[str, float]],
    length: float,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for load in active_loads:
        if load.get("type") != "Point":
            continue
        ratio = min(max(float(load.get("x_over_l", 0.0)), 0.0), 1.0)
        points.append({
            "x": ratio * length,
            "px": float(load.get("px", 0.0)),
            "py": float(load.get("py", 0.0)),
            "pz": float(load.get("pz", 0.0)),
        })
    return sorted(points, key=lambda item: item["x"])


def _resultant_at(
    local_force: Sequence[float],
    length: float,
    component: str,
    active_loads: Sequence[dict[str, float]],
    x: float,
    *,
    side: str = "right",
) -> float:
    if len(local_force) < 12:
        raise ValueError("A 12-value localForce response is required.")
    if length <= 0.0:
        raise ValueError("Element length must be positive.")

    values = [float(value) for value in local_force[:12]]
    n0 = -values[0]
    vy0 = values[1]
    vz0 = -values[2]
    t0 = -values[3]
    my0 = -values[4]
    mz0 = -values[5]

    wx, wy, wz = _aggregate_uniform(active_loads)
    points = _point_loads(active_loads, length)
    tol = max(length, 1.0) * 1.0e-12

    px_sum = py_sum = pz_sum = 0.0
    py_moment = pz_moment = 0.0
    for point in points:
        a = point["x"]
        passed = x > a + tol or (
            abs(x - a) <= tol and side == "right"
        )
        if not passed:
            continue
        px_sum += point["px"]
        py_sum += point["py"]
        pz_sum += point["pz"]
        lever = max(0.0, x - a)
        py_moment += point["py"] * lever
        pz_moment += point["pz"] * lever

    if component == "N":
        return n0 - wx * x - px_sum
    if component == "Vy":
        return vy0 + wy * x + py_sum
    if component == "Vz":
        return vz0 - wz * x - pz_sum
    if component == "T":
        return t0
    if component == "Mz":
        return mz0 + vy0 * x + 0.5 * wy * x * x + py_moment
    if component == "My":
        return my0 + vz0 * x - 0.5 * wz * x * x - pz_moment
    raise ValueError(f"Unsupported local force component: {component}")


def _moment_extrema_positions(
    local_force: Sequence[float],
    length: float,
    component: str,
    active_loads: Sequence[dict[str, float]],
) -> list[float]:
    if component not in {"My", "Mz"} or len(local_force) < 12:
        return []

    values = [float(value) for value in local_force[:12]]
    wx, wy, wz = _aggregate_uniform(active_loads)
    _ = wx
    points = _point_loads(active_loads, length)
    breakpoints = sorted({
        0.0,
        float(length),
        *(float(point["x"]) for point in points),
    })

    roots: list[float] = []
    tol = max(length, 1.0) * 1.0e-12
    for left, right in zip(breakpoints, breakpoints[1:]):
        if right - left <= tol:
            continue
        midpoint = 0.5 * (left + right)

        if component == "Mz":
            slope = wy
            constant = values[1]
            for point in points:
                if point["x"] < midpoint:
                    constant += point["py"]
        else:
            # dMy/dx = Vz = -localForce_I(Vz) - wz*x - sum(Pz)
            slope = -wz
            constant = -values[2]
            for point in points:
                if point["x"] < midpoint:
                    constant -= point["pz"]

        if abs(slope) <= 1.0e-15:
            continue
        root = -constant / slope
        if left + tol < root < right - tol:
            roots.append(root)
    return roots


def equilibrium_component_samples(
    local_force: Sequence[float],
    length: float,
    component: str,
    active_loads: Sequence[dict[str, float]] | None,
    *,
    sample_count: int = 65,
) -> list[tuple[float, float]]:
    """Sample the exact 1D equilibrium field for Studio beam load types.

    Uniform and point beam loads are evaluated analytically from the I-end
    local force. Point-load coordinates are duplicated for components that
    jump there, so a plotted polyline shows the discontinuity explicitly.
    """
    component = str(component)
    if component not in LOCAL_FORCE_INDEX:
        raise ValueError(
            f"Unsupported local force component: {component}"
        )
    if len(local_force) < 12 or length <= 0.0:
        return []
    if active_loads is None:
        ends = component_end_resultants(local_force, component)
        if ends is None:
            return []
        return [(0.0, ends[0]), (float(length), ends[1])]

    count = max(2, int(sample_count))
    positions = {
        float(length) * index / (count - 1)
        for index in range(count)
    }
    positions.update(
        _moment_extrema_positions(
            local_force,
            length,
            component,
            active_loads,
        )
    )

    points = _point_loads(active_loads, length)
    point_positions = {point["x"] for point in points}

    samples: list[tuple[float, float]] = []
    for x in sorted(positions | point_positions):
        has_point = any(
            math.isclose(
                x,
                point["x"],
                rel_tol=0.0,
                abs_tol=max(length, 1.0) * 1.0e-12,
            )
            for point in points
        )
        if has_point and component in {"N", "Vy", "Vz"}:
            samples.append((
                x,
                _resultant_at(
                    local_force,
                    length,
                    component,
                    active_loads,
                    x,
                    side="left",
                ),
            ))
            samples.append((
                x,
                _resultant_at(
                    local_force,
                    length,
                    component,
                    active_loads,
                    x,
                    side="right",
                ),
            ))
        else:
            samples.append((
                x,
                _resultant_at(
                    local_force,
                    length,
                    component,
                    active_loads,
                    x,
                    side="right",
                ),
            ))
    return samples


def _merge_section_samples_with_ends(
    section_samples: Sequence[tuple[float, float]],
    end_values: tuple[float, float],
    length: float,
) -> list[tuple[float, float]]:
    tol = max(length, 1.0) * 1.0e-10
    samples = [
        (float(x), float(value))
        for x, value in section_samples
        if -tol <= float(x) <= length + tol
    ]

    def upsert(x: float, value: float) -> None:
        for index, (existing_x, _) in enumerate(samples):
            if abs(existing_x - x) <= tol:
                # Prefer the directly queried section value.
                return
        samples.append((x, value))

    upsert(0.0, end_values[0])
    upsert(length, end_values[1])
    return sorted(samples, key=lambda item: item[0])


def enrich_member_force_results(
    result: dict[str, Any],
    model: StructuralModel,
    element_loads: dict[int, ElementLoadData],
    sections: dict[int, SectionData],
    materials: dict[int, MaterialData],
    transformations: dict[int, TransformationData],
    units: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Attach display-ready member-force distributions to a result payload."""
    enriched = copy.deepcopy(result)
    final = enriched.setdefault("final", {})
    if not isinstance(final, dict):
        return enriched

    local_forces = final.get("element_local_forces", {})
    section_forces = final.get("element_section_forces", {})
    load_factors = final.get("load_factors", {})
    if not isinstance(local_forces, dict):
        return enriched
    if not isinstance(section_forces, dict):
        section_forces = {}
    if not isinstance(load_factors, dict):
        load_factors = {}

    diagrams: dict[str, dict[str, Any]] = {}
    analysis_type = str(
        enriched.get("analysis", {}).get("type", "")
        if isinstance(enriched.get("analysis", {}), dict)
        else ""
    )

    for tag in sorted(model.elements):
        element = model.elements[tag]
        raw = local_forces.get(str(tag), local_forces.get(tag))
        if not isinstance(raw, (list, tuple)) or len(raw) < 12:
            continue

        node_i = model.nodes.get(element.i)
        node_j = model.nodes.get(element.j)
        if node_i is None or node_j is None:
            continue
        length = math.sqrt(sum(
            (float(b) - float(a)) ** 2
            for a, b in zip(node_i.xyz, node_j.xyz)
        ))
        if length <= 1.0e-15:
            continue

        active_loads = _active_local_element_loads(
            tag,
            element_loads,
            load_factors,
            model,
            sections,
            materials,
            transformations,
            units,
        )
        section_data = section_forces.get(
            str(tag),
            section_forces.get(tag),
        )
        per_component: dict[str, Any] = {}

        for component in LOCAL_FORCE_COMPONENTS:
            end_values = component_end_resultants(raw, component)
            if end_values is None:
                continue

            direct = section_component_samples(
                section_data if isinstance(section_data, dict) else None,
                component,
            )

            # For displacement-based beam-columns, preserve the actual
            # constitutive section resultants at integration points. For
            # force-based and elastic members, equilibrium reconstruction
            # gives the continuous force field under Studio Uniform/Point
            # beam loads and can be checked against section IP responses.
            if (
                element.element_type == "dispBeamColumn"
                and component in SECTION_FORCE_INDEX
                and direct
            ):
                samples = _merge_section_samples_with_ends(
                    direct,
                    end_values,
                    length,
                )
                source = "section integration points"
            elif active_loads is not None:
                samples = equilibrium_component_samples(
                    raw,
                    length,
                    component,
                    active_loads,
                )
                source = "equilibrium"
            elif component in SECTION_FORCE_INDEX and direct:
                samples = _merge_section_samples_with_ends(
                    direct,
                    end_values,
                    length,
                )
                source = "section integration points"
            else:
                samples = [
                    (0.0, end_values[0]),
                    (length, end_values[1]),
                ]
                source = "end-force fallback"

            verification = None
            if direct and active_loads is not None:
                differences = []
                for x, value in direct:
                    reconstructed = _resultant_at(
                        raw,
                        length,
                        component,
                        active_loads,
                        x,
                        side="right",
                    )
                    differences.append(abs(reconstructed - value))
                if differences:
                    verification = max(differences)

            per_component[component] = {
                "x": [float(x) for x, _ in samples],
                "values": [float(value) for _, value in samples],
                "source": source,
                "section_points": [
                    [float(x), float(value)]
                    for x, value in direct
                ],
                "verification_max_abs_difference": verification,
                "analysis_type": analysis_type,
            }

        if per_component:
            diagrams[str(tag)] = per_component

    final["member_force_diagrams"] = diagrams
    return enriched
