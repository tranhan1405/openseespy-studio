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


def parse_cyclic_protocol_text(
    text: str,
    *,
    amplitude_column: int = 1,
    cycles_column: int = 2,
) -> list[tuple[float, int]]:
    """Parse amplitude/cycle rows from CSV/TXT protocol content."""
    amplitude_column = int(amplitude_column)
    cycles_column = int(cycles_column)
    if amplitude_column < 1 or cycles_column < 1:
        raise ValueError("Protocol columns are 1-based and must be positive.")

    rows: list[tuple[float, int]] = []
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
        required = max(amplitude_column, cycles_column)
        if len(numeric) < required:
            raise ValueError(
                f"Cyclic protocol line {line_number} has only "
                f"{len(numeric)} numeric column(s)."
            )
        amplitude = abs(float(numeric[amplitude_column - 1]))
        cycles_raw = float(numeric[cycles_column - 1])
        cycles = int(round(cycles_raw))
        if amplitude <= 0.0:
            raise ValueError(
                f"Cyclic protocol line {line_number} has zero amplitude."
            )
        if cycles < 1 or not math.isclose(
            cycles_raw,
            cycles,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise ValueError(
                f"Cyclic protocol line {line_number} needs a positive "
                "integer cycle count."
            )
        rows.append((amplitude, cycles))
    if not rows:
        raise ValueError("Cyclic protocol file contains no amplitude/cycle rows.")
    return rows


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
    custom_weights: dict[int, float] | None = None,
) -> dict[int, float]:
    tags = _active_lateral_nodes(project, dof)
    kind = str(distribution)

    if kind == "Uniform":
        raw = {tag: 1.0 for tag in tags}
    elif kind == "Triangular":
        z0 = min(
            float(node.xyz[2])
            for node in project.model.nodes.values()
        )
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
    elif kind == "First-mode approximation":
        z_values = {
            tag: float(project.model.nodes[tag].xyz[2])
            for tag in tags
        }
        z0 = min(
            float(node.xyz[2])
            for node in project.model.nodes.values()
        )
        height = max(z_values.values()) - z0
        if height <= 1.0e-15:
            raw = {tag: 1.0 for tag in tags}
        else:
            index = int(dof) - 1
            raw = {}
            for tag in tags:
                shape = math.sin(
                    0.5
                    * math.pi
                    * (z_values[tag] - z0)
                    / height
                )
                mass = max(
                    float(project.model.nodes[tag].mass[index]),
                    0.0,
                )
                raw[tag] = shape * (mass if mass > 0.0 else 1.0)
    elif kind == "Custom":
        supplied = {
            int(tag): float(value)
            for tag, value in dict(custom_weights or {}).items()
        }
        invalid = sorted(set(supplied) - set(tags))
        if invalid:
            raise ValueError(
                "Custom lateral weights reference constrained/missing node(s): "
                + ", ".join(map(str, invalid))
            )
        raw = {
            tag: supplied.get(tag, 0.0)
            for tag in tags
        }
    else:
        raise ValueError(f"Unsupported lateral-load distribution: {kind}")

    total = sum(abs(value) for value in raw.values())
    if total <= 1.0e-15:
        raise ValueError(
            f"{kind} lateral-load distribution has zero total weight."
        )
    return {tag: value / total for tag, value in raw.items() if abs(value) > 0.0}


def _reference_lateral_loading(
    project: ProjectDatabase,
    *,
    dof: int,
    distribution: str,
    prefix: str,
    custom_weights: dict[int, float] | None = None,
) -> tuple[list[TimeSeriesData], list[LoadPatternData], list[NodalLoadData]]:
    weights = lateral_load_weights(
        project,
        dof=dof,
        distribution=distribution,
        custom_weights=custom_weights,
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
    custom_weights: dict[int, float] | None = None,
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
        custom_weights=custom_weights,
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
    custom_weights: dict[int, float] | None = None,
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
        custom_weights=custom_weights,
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
    ground_motion_values: Iterable[float] | None = None,
    dt: float,
    input_unit: str = "g",
    scale_factor: float = 1.0,
    direction: int = 1,
    monitor_node: int,
    damping_ratio: float = 0.05,
    damping_mode_i: int = 1,
    damping_mode_j: int = 3,
    solver_preset: str = "Robust",
    components: Iterable[dict[str, object]] | None = None,
) -> AnalysisTemplatePlan:
    dt = float(dt)
    if dt <= 0.0:
        raise ValueError("Ground-motion dt must be positive.")
    if int(monitor_node) not in project.model.nodes:
        raise ValueError(f"Monitor node {monitor_node} does not exist.")

    component_rows: list[dict[str, object]]
    if components is None:
        raw = [float(value) for value in (ground_motion_values or [])]
        component_rows = [
            {
                "direction": int(direction),
                "values": raw,
                "input_unit": input_unit,
                "scale_factor": float(scale_factor),
                "label": {1: "X", 2: "Y", 3: "Z"}.get(
                    int(direction),
                    str(direction),
                ),
            }
        ]
    else:
        component_rows = [dict(item) for item in components]

    if not component_rows:
        raise ValueError("NLTH needs at least one excitation component.")

    directions: set[int] = set()
    series_list: list[TimeSeriesData] = []
    pattern_list: list[LoadPatternData] = []
    next_series = _next_tag(project.time_series)
    next_pattern = _next_tag(project.load_patterns)
    max_points = 0

    for offset, row in enumerate(component_rows):
        component_direction = int(row.get("direction", 0))
        if component_direction not in (1, 2, 3):
            raise ValueError("NLTH components support X, Y or Z excitation.")
        if component_direction in directions:
            raise ValueError(
                f"NLTH direction {component_direction} is duplicated."
            )
        directions.add(component_direction)

        raw = [float(value) for value in row.get("values", [])]
        if not raw:
            raise ValueError(
                f"Ground-motion component {component_direction} is empty."
            )
        component_unit = str(row.get("input_unit", input_unit))
        component_scale = float(row.get("scale_factor", scale_factor))
        label = str(
            row.get(
                "label",
                {1: "X", 2: "Y", 3: "Z"}[component_direction],
            )
        )
        converted = [
            _acceleration_to_model_units(
                value,
                component_unit,
                project.units,
            )
            for value in raw
        ]
        max_points = max(max_points, len(converted))
        series_tag = next_series + offset
        pattern_tag = next_pattern + offset
        series_list.append(
            TimeSeriesData(
                tag=series_tag,
                name=f"{name} GM {label}",
                series_type="Path",
                factor=component_scale,
                dt=dt,
                values=converted,
            )
        )
        pattern_list.append(
            LoadPatternData(
                tag=pattern_tag,
                name=f"{name} Excitation {label}",
                pattern_type="UniformExcitation",
                time_series_tag=series_tag,
                direction=component_direction,
                factor=1.0,
            )
        )

    primary_direction = int(component_rows[0]["direction"])
    tag = project.next_analysis_tag()
    analysis = AnalysisSettingsData(
        tag=tag,
        name=str(name).strip() or f"NLTH {tag}",
        analysis_type="Transient",
        steps=max_points,
        control_node=int(monitor_node),
        control_dof=primary_direction,
        dt=dt,
        gamma=0.5,
        beta=0.25,
        rayleigh_damping_ratio=float(damping_ratio),
        rayleigh_mode_i=int(damping_mode_i),
        rayleigh_mode_j=int(damping_mode_j),
        preload_gravity=True,
        gravity_steps=10,
        deferred_pattern_tags=[
            pattern.tag for pattern in pattern_list
        ],
        **_solver_kwargs(solver_preset),
    )

    specs: list[tuple[str, str, dict[str, object]]] = []
    for component_direction in sorted(directions):
        axis = {1: "X", 2: "Y", 3: "Z"}[component_direction]
        specs.extend(
            [
                (
                    f"Acceleration History {axis}",
                    "TimeHistory",
                    {
                        "node": int(monitor_node),
                        "quantity": "Acceleration",
                        "dof": component_direction,
                    },
                ),
                (
                    f"Displacement History {axis}",
                    "TimeHistory",
                    {
                        "node": int(monitor_node),
                        "quantity": "Displacement",
                        "dof": component_direction,
                    },
                ),
            ]
        )
    specs.extend(
        [
            ("Deformed Shape", "DeformedShape", {"scale": 10.0}),
            ("Hinge / Yield State", "HingeState", {}),
            ("Member Force Mz", "MemberForce", {"component": "Mz", "scale": 1.0}),
            ("Convergence", "Convergence", {"test": analysis.test}),
        ]
    )
    results = _result_objects(project, tag, specs)
    component_names = "/".join(
        {1: "X", 2: "Y", 3: "Z"}[direction]
        for direction in sorted(directions)
    )
    return AnalysisTemplatePlan(
        analysis=analysis,
        time_series=series_list,
        load_patterns=pattern_list,
        results=results,
        summary=(
            f"NLTH {component_names} · up to {max_points} point(s) · "
            f"dt={dt:g} s"
        ),
    )

