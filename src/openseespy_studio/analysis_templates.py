from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable

from .project import (
    AnalysisSettingsData,
    LoadPatternData,
    NodalLoadData,
    ProjectDatabase,
    SolutionResultData,
    TimeSeriesData,
)
from .units import UnitSystem


SOLVER_PRESETS: dict[str, dict[str, object]] = {
    "Robust": {
        "test": "NormUnbalance",
        "tolerance": 1.0e-7,
        "max_iterations": 100,
        "algorithm": "Newton",
        "recovery": True,
        "adaptive_step": True,
        "adaptive_cutback_factor": 0.5,
        "adaptive_min_factor": 0.0625,
        "adaptive_growth_factor": 1.25,
        "adaptive_easy_iterations": 4,
        "adaptive_growth_after": 2,
    },
    "Balanced": {
        "test": "NormDispIncr",
        "tolerance": 1.0e-8,
        "max_iterations": 50,
        "algorithm": "Newton",
        "recovery": True,
        "adaptive_step": True,
        "adaptive_cutback_factor": 0.5,
        "adaptive_min_factor": 0.125,
        "adaptive_growth_factor": 1.5,
        "adaptive_easy_iterations": 4,
        "adaptive_growth_after": 3,
    },
    "Fast": {
        "test": "NormDispIncr",
        "tolerance": 1.0e-7,
        "max_iterations": 30,
        "algorithm": "Newton",
        "recovery": False,
        "adaptive_step": False,
        "adaptive_cutback_factor": 0.5,
        "adaptive_min_factor": 0.25,
        "adaptive_growth_factor": 1.5,
        "adaptive_easy_iterations": 4,
        "adaptive_growth_after": 3,
    },
}


@dataclass(slots=True)
class AnalysisTemplatePlan:
    analysis: AnalysisSettingsData
    time_series: list[TimeSeriesData] = field(default_factory=list)
    load_patterns: list[LoadPatternData] = field(default_factory=list)
    nodal_loads: list[NodalLoadData] = field(default_factory=list)
    results: list[SolutionResultData] = field(default_factory=list)
    summary: str = ""


def expand_cyclic_protocol(
    rows: Iterable[tuple[float, int]],
    *,
    finish_at_zero: bool = True,
) -> list[float]:
    """Expand amplitude/cycle rows into absolute displacement targets."""
    targets: list[float] = []
    for raw_amplitude, raw_cycles in rows:
        amplitude = abs(float(raw_amplitude))
        cycles = int(raw_cycles)
        if amplitude <= 0.0:
            raise ValueError("Cyclic amplitude must be positive.")
        if cycles < 1:
            raise ValueError("Cyclic cycle count must be at least 1.")
        for _ in range(cycles):
            targets.extend((amplitude, -amplitude))
    if finish_at_zero and targets:
        targets.append(0.0)
    if not targets:
        raise ValueError("Cyclic protocol needs at least one row.")
    return targets


def parse_ground_motion_text(
    text: str,
    *,
    column: int = 1,
) -> list[float]:
    """Read one numeric acceleration column from common TXT/CSV content."""
    column = int(column)
    if column < 1:
        raise ValueError("Ground-motion column is 1-based and must be positive.")

    values: list[float] = []
    for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "%")):
            continue
        tokens = line.replace(",", " ").replace(";", " ").split()
        numeric: list[float] = []
        for token in tokens:
            try:
                numeric.append(float(token))
            except ValueError:
                continue
        if not numeric:
            continue
        if column > len(numeric):
            raise ValueError(
                f"Ground-motion line {line_number} has only "
                f"{len(numeric)} numeric column(s)."
            )
        values.append(numeric[column - 1])
    if not values:
        raise ValueError("Ground-motion file contains no numeric values.")
    return values


def default_control_node(project: ProjectDatabase) -> int:
    if not project.model.nodes:
        return 1
    candidates = [
        node
        for node in project.model.nodes.values()
        if not all(bool(value) for value in node.fixity[:3])
    ]
    if not candidates:
        candidates = list(project.model.nodes.values())
    node = max(
        candidates,
        key=lambda item: (
            float(item.xyz[2]),
            float(item.xyz[1]),
            float(item.xyz[0]),
            int(item.tag),
        ),
    )
    return int(node.tag)


def _next_tag(items: dict[int, object]) -> int:
    return max(items, default=0) + 1


def _solver_kwargs(name: str) -> dict[str, object]:
    try:
        return dict(SOLVER_PRESETS[str(name)])
    except KeyError as exc:
        raise ValueError(f"Unknown solver preset: {name}") from exc


def _active_lateral_nodes(project: ProjectDatabase, dof: int) -> list[int]:
    index = int(dof) - 1
    if index not in (0, 1, 2):
        raise ValueError(
            "Analysis templates currently support translational control DOFs "
            "UX, UY or UZ."
        )
    tags = [
        tag
        for tag, node in project.model.nodes.items()
        if not bool(node.fixity[index])
    ]
    if not tags:
        raise ValueError(
            "No unconstrained nodes are available in the selected direction."
        )
    return sorted(tags)


def lateral_load_weights(
    project: ProjectDatabase,
    *,
    dof: int,
    distribution: str,
) -> dict[int, float]:
    tags = _active_lateral_nodes(project, dof)
    kind = str(distribution)

    if kind == "Uniform":
        raw = {tag: 1.0 for tag in tags}
    elif kind == "Triangular":
        z_values = [
            float(project.model.nodes[tag].xyz[2])
            for tag in tags
        ]
        z0 = min(z_values)
        raw = {
            tag: max(
                float(project.model.nodes[tag].xyz[2]) - z0,
                0.0,
            )
            for tag in tags
        }
        if sum(raw.values()) <= 1.0e-15:
            raw = {tag: 1.0 for tag in tags}
    elif kind == "Mass proportional":
        index = int(dof) - 1
        raw = {
            tag: max(float(project.model.nodes[tag].mass[index]), 0.0)
            for tag in tags
        }
        if sum(raw.values()) <= 1.0e-15:
            raw = {tag: 1.0 for tag in tags}
    else:
        raise ValueError(f"Unsupported lateral-load distribution: {kind}")

    total = sum(raw.values())
    return {tag: value / total for tag, value in raw.items()}


def _reference_lateral_loading(
    project: ProjectDatabase,
    *,
    dof: int,
    distribution: str,
    prefix: str,
) -> tuple[list[TimeSeriesData], list[LoadPatternData], list[NodalLoadData]]:
    weights = lateral_load_weights(
        project,
        dof=dof,
        distribution=distribution,
    )
    series_tag = _next_tag(project.time_series)
    pattern_tag = _next_tag(project.load_patterns)
    load_tag = _next_tag(project.nodal_loads)

    series = TimeSeriesData(
        tag=series_tag,
        name=f"{prefix} Reference",
        series_type="Linear",
        factor=1.0,
    )
    pattern = LoadPatternData(
        tag=pattern_tag,
        name=f"{prefix} Lateral Pattern",
        pattern_type="Plain",
        time_series_tag=series_tag,
    )
    loads: list[NodalLoadData] = []
    for offset, tag in enumerate(sorted(weights)):
        values = [0.0] * 6
        values[int(dof) - 1] = float(weights[tag])
        loads.append(
            NodalLoadData(
                tag=load_tag + offset,
                name=f"{prefix} Node {tag}",
                pattern_tag=pattern_tag,
                node_tag=tag,
                values=tuple(values),
            )
        )
    return [series], [pattern], loads


def _result_objects(
    project: ProjectDatabase,
    analysis_tag: int,
    specs: list[tuple[str, str, dict[str, object]]],
) -> list[SolutionResultData]:
    tag = project.next_solution_result_tag()
    result: list[SolutionResultData] = []
    for name, result_type, settings in specs:
        result.append(
            SolutionResultData(
                tag=tag,
                analysis_tag=analysis_tag,
                name=name,
                result_type=result_type,
                settings=dict(settings),
            )
        )
        tag += 1
    return result


def build_pushover_template(
    project: ProjectDatabase,
    *,
    name: str,
    control_node: int,
    control_dof: int,
    target_displacement: float,
    max_increment: float,
    distribution: str = "Triangular",
    solver_preset: str = "Robust",
) -> AnalysisTemplatePlan:
    if int(control_node) not in project.model.nodes:
        raise ValueError(f"Control node {control_node} does not exist.")
    target = float(target_displacement)
    max_increment = abs(float(max_increment))
    if abs(target) <= 1.0e-15:
        raise ValueError("Pushover target displacement must be nonzero.")
    if max_increment <= 0.0:
        raise ValueError("Pushover increment must be positive.")

    steps = max(1, int(math.ceil(abs(target) / max_increment)))
    increment = target / steps
    series, patterns, loads = _reference_lateral_loading(
        project,
        dof=int(control_dof),
        distribution=distribution,
        prefix="Pushover",
    )
    tag = project.next_analysis_tag()
    analysis = AnalysisSettingsData(
        tag=tag,
        name=str(name).strip() or f"Pushover {tag}",
        analysis_type="Pushover",
        steps=steps,
        control_node=int(control_node),
        control_dof=int(control_dof),
        displacement_increment=increment,
        preload_gravity=True,
        gravity_steps=10,
        deferred_pattern_tags=[patterns[0].tag],
        **_solver_kwargs(solver_preset),
    )
    component = {1: "FX", 2: "FY", 3: "FZ"}[int(control_dof)]
    results = _result_objects(
        project,
        tag,
        [
            ("Pushover Capacity Curve", "PushoverCurve", {}),
            ("Deformed Shape", "DeformedShape", {"scale": 10.0}),
            ("Hinge / Yield State", "HingeState", {}),
            ("Member Force Mz", "MemberForce", {"component": "Mz", "scale": 1.0}),
            (f"Reaction {component}", "NodalReaction", {"component": component}),
            ("Convergence", "Convergence", {"test": analysis.test}),
        ],
    )
    return AnalysisTemplatePlan(
        analysis=analysis,
        time_series=series,
        load_patterns=patterns,
        nodal_loads=loads,
        results=results,
        summary=(
            f"Pushover · {distribution} reference pattern · "
            f"{steps} step(s) to {target:g}"
        ),
    )


def build_cyclic_template(
    project: ProjectDatabase,
    *,
    name: str,
    control_node: int,
    control_dof: int,
    protocol_rows: Iterable[tuple[float, int]],
    max_increment: float,
    distribution: str = "Uniform",
    solver_preset: str = "Robust",
) -> AnalysisTemplatePlan:
    if int(control_node) not in project.model.nodes:
        raise ValueError(f"Control node {control_node} does not exist.")
    targets = expand_cyclic_protocol(protocol_rows)
    max_increment = abs(float(max_increment))
    if max_increment <= 0.0:
        raise ValueError("Cyclic max increment must be positive.")

    series, patterns, loads = _reference_lateral_loading(
        project,
        dof=int(control_dof),
        distribution=distribution,
        prefix="Cyclic",
    )
    tag = project.next_analysis_tag()
    analysis = AnalysisSettingsData(
        tag=tag,
        name=str(name).strip() or f"Cyclic {tag}",
        analysis_type="Cyclic",
        control_node=int(control_node),
        control_dof=int(control_dof),
        cyclic_targets=targets,
        cyclic_increment=max_increment,
        preload_gravity=True,
        gravity_steps=10,
        deferred_pattern_tags=[patterns[0].tag],
        **_solver_kwargs(solver_preset),
    )
    results = _result_objects(
        project,
        tag,
        [
            ("Cyclic Hysteresis", "CyclicHysteresis", {}),
            ("Deformed Shape", "DeformedShape", {"scale": 10.0}),
            ("Hinge / Yield State", "HingeState", {}),
            ("Member Force Mz", "MemberForce", {"component": "Mz", "scale": 1.0}),
            ("Convergence", "Convergence", {"test": analysis.test}),
        ],
    )
    return AnalysisTemplatePlan(
        analysis=analysis,
        time_series=series,
        load_patterns=patterns,
        nodal_loads=loads,
        results=results,
        summary=(
            f"Cyclic · {len(targets)} target(s) · "
            f"{distribution} reference pattern"
        ),
    )


def _acceleration_to_model_units(
    value: float,
    input_unit: str,
    units: dict[str, str],
) -> float:
    unit = str(input_unit)
    if unit == "g":
        si = float(value) * 9.80665
    elif unit == "m/s²":
        si = float(value)
    elif unit == "cm/s²":
        si = float(value) * 0.01
    else:
        raise ValueError(f"Unsupported acceleration unit: {input_unit}")
    return UnitSystem.from_mapping(units).acceleration_from_m_per_s2(si)


def build_nlth_template(
    project: ProjectDatabase,
    *,
    name: str,
    ground_motion_values: Iterable[float],
    dt: float,
    input_unit: str,
    scale_factor: float,
    direction: int,
    monitor_node: int,
    damping_ratio: float = 0.05,
    damping_mode_i: int = 1,
    damping_mode_j: int = 3,
    solver_preset: str = "Robust",
) -> AnalysisTemplatePlan:
    raw = [float(value) for value in ground_motion_values]
    if not raw:
        raise ValueError("Ground-motion record is empty.")
    dt = float(dt)
    if dt <= 0.0:
        raise ValueError("Ground-motion dt must be positive.")
    if int(direction) not in (1, 2, 3):
        raise ValueError("NLTH template supports X, Y or Z excitation.")
    if int(monitor_node) not in project.model.nodes:
        raise ValueError(f"Monitor node {monitor_node} does not exist.")

    converted = [
        _acceleration_to_model_units(value, input_unit, project.units)
        for value in raw
    ]
    series_tag = _next_tag(project.time_series)
    pattern_tag = _next_tag(project.load_patterns)
    series = TimeSeriesData(
        tag=series_tag,
        name=f"{name} Ground Motion",
        series_type="Path",
        factor=float(scale_factor),
        dt=dt,
        values=converted,
    )
    pattern = LoadPatternData(
        tag=pattern_tag,
        name=f"{name} Uniform Excitation",
        pattern_type="UniformExcitation",
        time_series_tag=series_tag,
        direction=int(direction),
        factor=1.0,
    )
    tag = project.next_analysis_tag()
    analysis = AnalysisSettingsData(
        tag=tag,
        name=str(name).strip() or f"NLTH {tag}",
        analysis_type="Transient",
        steps=len(converted),
        control_node=int(monitor_node),
        control_dof=int(direction),
        dt=dt,
        gamma=0.5,
        beta=0.25,
        rayleigh_damping_ratio=float(damping_ratio),
        rayleigh_mode_i=int(damping_mode_i),
        rayleigh_mode_j=int(damping_mode_j),
        preload_gravity=True,
        gravity_steps=10,
        deferred_pattern_tags=[pattern.tag],
        **_solver_kwargs(solver_preset),
    )
    results = _result_objects(
        project,
        tag,
        [
            (
                "Acceleration History",
                "TimeHistory",
                {
                    "node": int(monitor_node),
                    "quantity": "Acceleration",
                    "dof": int(direction),
                },
            ),
            (
                "Displacement History",
                "TimeHistory",
                {
                    "node": int(monitor_node),
                    "quantity": "Displacement",
                    "dof": int(direction),
                },
            ),
            ("Deformed Shape", "DeformedShape", {"scale": 10.0}),
            ("Hinge / Yield State", "HingeState", {}),
            ("Member Force Mz", "MemberForce", {"component": "Mz", "scale": 1.0}),
            ("Convergence", "Convergence", {"test": analysis.test}),
        ],
    )
    return AnalysisTemplatePlan(
        analysis=analysis,
        time_series=[series],
        load_patterns=[pattern],
        results=results,
        summary=(
            f"NLTH · {len(converted)} point(s) · dt={dt:g} s · "
            f"{input_unit} × {float(scale_factor):g}"
        ),
    )
