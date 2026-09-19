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
class GroundMotionComponentSpec:
    direction: int
    values: list[float]
    scale_factor: float = 1.0
    name: str = ""


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
    """Read amplitude/cycle rows from CSV/TXT protocol data."""
    amplitude_column = int(amplitude_column)
    cycles_column = int(cycles_column)
    if amplitude_column < 1 or cycles_column < 1:
        raise ValueError("Protocol columns are 1-based and must be positive.")

    rows: list[tuple[float, int]] = []
    required = max(amplitude_column, cycles_column)
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "%")):
            continue
        tokens = line.replace(",", " ").replace(";", " ").split()
        if len(tokens) < required:
            continue
        try:
            amplitude = float(tokens[amplitude_column - 1])
            cycles_value = float(tokens[cycles_column - 1])
        except ValueError:
            # Allow a header row such as "Amplitude,Cycles".
            continue
        cycles = int(round(cycles_value))
        if not math.isclose(cycles_value, cycles, abs_tol=1.0e-9):
            raise ValueError("Protocol cycle counts must be integers.")
        if abs(amplitude) <= 1.0e-15:
            raise ValueError("Protocol amplitudes must be nonzero.")
        if cycles < 1:
            raise ValueError("Protocol cycle counts must be at least 1.")
        rows.append((abs(amplitude), cycles))
    if not rows:
        raise ValueError("Protocol file contains no amplitude/cycle rows.")
    return rows


def parse_cyclic_targets_text(
    text: str,
    *,
    column: int = 1,
) -> list[float]:
    """Read absolute cyclic displacement/drift targets from TXT/CSV content."""
    column = int(column)
    if column < 1:
        raise ValueError("Target column is 1-based and must be positive.")

    targets: list[float] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "%")):
            continue
        tokens = line.replace(",", " ").replace(";", " ").split()
        if len(tokens) < column:
            continue
        try:
            value = float(tokens[column - 1])
        except ValueError:
            # Allow a heading such as "Target".
            continue
        if not math.isfinite(value):
            raise ValueError("Cyclic target values must be finite.")
        targets.append(value)
    if not targets:
        raise ValueError("Protocol file contains no cyclic targets.")
    return targets


def parse_node_weight_text(text: str) -> dict[int, float]:
    """Read custom lateral-load weights as node,weight pairs."""
    result: dict[int, float] = {}
    for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "%")):
            continue
        tokens = line.replace(",", " ").replace(";", " ").split()
        if len(tokens) < 2:
            continue
        try:
            node = int(tokens[0])
            weight = float(tokens[1])
        except ValueError as exc:
            raise ValueError(
                f"Custom distribution line {line_number} must be "
                "'node, weight'."
            ) from exc
        if node <= 0:
            raise ValueError("Custom distribution node tags must be positive.")
        if abs(weight) <= 1.0e-15:
            continue
        result[node] = weight
    if not result:
        raise ValueError("Custom distribution contains no nonzero weights.")
    return result


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


def infer_height_axis(project: ProjectDatabase) -> int:
    """Return a sensible vertical coordinate axis for common frame layouts."""
    spans = [
        max(
            (node.xyz[index] for node in project.model.nodes.values()),
            default=0.0,
        )
        - min(
            (node.xyz[index] for node in project.model.nodes.values()),
            default=0.0,
        )
        for index in range(3)
    ]
    if spans[2] > 1.0e-12:
        return 3
    if spans[1] > 1.0e-12:
        return 2
    if spans[0] > 1.0e-12:
        return 1
    return 3


def structure_reference_height(
    project: ProjectDatabase,
    *,
    control_node: int,
    height_axis: int,
) -> float:
    axis = int(height_axis) - 1
    if axis not in (0, 1, 2):
        raise ValueError("Height axis must be X, Y or Z.")
    if int(control_node) not in project.model.nodes:
        raise ValueError(f"Control node {control_node} does not exist.")
    values = [
        float(node.xyz[axis])
        for node in project.model.nodes.values()
    ]
    if not values:
        raise ValueError("Reference height needs at least one model node.")
    control_value = float(project.model.nodes[int(control_node)].xyz[axis])
    base = min(values)
    height = abs(control_value - base)
    if height <= 1.0e-15:
        height = max(values) - min(values)
    if height <= 1.0e-15:
        raise ValueError(
            "Reference height is zero on the selected height axis."
        )
    return height


def lateral_load_weights(
    project: ProjectDatabase,
    *,
    dof: int,
    distribution: str,
    custom_weights: dict[int, float] | None = None,
    height_axis: int = 3,
) -> dict[int, float]:
    tags = _active_lateral_nodes(project, dof)
    kind = str(distribution)

    if kind == "Uniform":
        raw = {tag: 1.0 for tag in tags}
    elif kind == "Triangular":
        axis = int(height_axis) - 1
        if axis not in (0, 1, 2):
            raise ValueError("Height axis must be X, Y or Z.")
        h0 = min(
            float(node.xyz[axis])
            for node in project.model.nodes.values()
        )
        raw = {
            tag: max(
                float(project.model.nodes[tag].xyz[axis]) - h0,
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
    elif kind in {"First-mode proportional", "Custom"}:
        supplied = dict(custom_weights or {})
        unknown = sorted(set(supplied) - set(project.model.nodes))
        if unknown:
            raise ValueError(
                "Lateral-load weights reference missing node(s): "
                + ", ".join(map(str, unknown))
            )
        raw = {
            tag: float(supplied.get(tag, 0.0))
            for tag in tags
            if abs(float(supplied.get(tag, 0.0))) > 1.0e-15
        }
        if not raw:
            raise ValueError(
                f"{kind} loading needs at least one nonzero active-node weight."
            )
    else:
        raise ValueError(f"Unsupported lateral-load distribution: {kind}")

    total = sum(abs(value) for value in raw.values())
    if total <= 1.0e-15:
        raise ValueError("Lateral-load distribution has zero total weight.")
    return {tag: value / total for tag, value in raw.items()}


def _reference_lateral_loading(
    project: ProjectDatabase,
    *,
    dof: int,
    distribution: str,
    prefix: str,
    custom_weights: dict[int, float] | None = None,
    height_axis: int = 3,
) -> tuple[list[TimeSeriesData], list[LoadPatternData], list[NodalLoadData]]:
    weights = lateral_load_weights(
        project,
        dof=dof,
        distribution=distribution,
        custom_weights=custom_weights,
        height_axis=height_axis,
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


def build_modal_template(
    project: ProjectDatabase,
    *,
    name: str,
    num_modes: int = 6,
    eigen_solver: str = "-genBandArpack",
    require_nodal_mass: bool = True,
) -> AnalysisTemplatePlan:
    if not project.model.nodes:
        raise ValueError("Modal template needs a structural model.")
    num_modes = int(num_modes)
    if num_modes < 1:
        raise ValueError("Number of modes must be at least 1.")

    has_translational_mass = any(
        any(abs(float(value)) > 1.0e-15 for value in node.mass[:3])
        for node in project.model.nodes.values()
    )
    if require_nodal_mass and not has_translational_mass:
        raise ValueError(
            "Modal template found no translational nodal mass. "
            "Assign nodal mass first, or disable the mass check if mass is "
            "provided by another supported modeling mechanism."
        )

    tag = project.next_analysis_tag()
    analysis = AnalysisSettingsData(
        tag=tag,
        name=str(name).strip() or f"Modal {tag}",
        analysis_type="Modal",
        num_modes=num_modes,
        eigen_solver=str(eigen_solver),
        recovery=False,
        adaptive_step=False,
        live_convergence=False,
    )
    result_specs = [
        (
            "Mode Motion",
            "Motion",
            {"mode": 1, "scale": 1.0, "auto_scale": True},
        )
    ] + [
        (
            f"Mode Shape {mode}",
            "ModeShape",
            {"mode": mode, "scale": 1.0},
        )
        for mode in range(1, num_modes + 1)
    ]
    results = _result_objects(project, tag, result_specs)
    mass_note = (
        "nodal mass detected"
        if has_translational_mass
        else "mass check bypassed"
    )
    return AnalysisTemplatePlan(
        analysis=analysis,
        results=results,
        summary=(
            f"Modal · {num_modes} mode(s) · {eigen_solver} · {mass_note}"
        ),
    )


def build_pushover_template(
    project: ProjectDatabase,
    *,
    name: str,
    control_node: int,
    control_dof: int,
    target_displacement: float,
    max_increment: float,
    distribution: str = "Triangular",
    distribution_weights: dict[int, float] | None = None,
    height_axis: int = 3,
    driver_pattern_tag: int | None = None,
    preload_gravity: bool = True,
    gravity_steps: int = 10,
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
    gravity_steps = int(gravity_steps)
    if gravity_steps < 1:
        raise ValueError("Gravity preload steps must be at least 1.")

    steps = max(1, int(math.ceil(abs(target) / max_increment)))
    increment = target / steps

    driver_description = f"{distribution} reference pattern"
    if driver_pattern_tag is None:
        series, patterns, loads = _reference_lateral_loading(
            project,
            dof=int(control_dof),
            distribution=distribution,
            prefix="Pushover",
            custom_weights=distribution_weights,
            height_axis=int(height_axis),
        )
        deferred_pattern_tag = patterns[0].tag
    else:
        driver_pattern_tag = int(driver_pattern_tag)
        pattern = project.load_patterns.get(driver_pattern_tag)
        if pattern is None:
            raise ValueError(
                f"Pushover driving pattern {driver_pattern_tag} does not exist."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Pushover driving pattern must be a Plain load pattern."
            )
        series, patterns, loads = [], [], []
        deferred_pattern_tag = driver_pattern_tag
        driver_description = (
            f"existing pattern {driver_pattern_tag} ({pattern.name})"
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
        preload_gravity=bool(preload_gravity),
        gravity_steps=gravity_steps,
        deferred_pattern_tags=[deferred_pattern_tag],
        **_solver_kwargs(solver_preset),
    )
    component = {1: "FX", 2: "FY", 3: "FZ"}[int(control_dof)]
    results = _result_objects(
        project,
        tag,
        [
            ("Pushover Capacity Curve", "PushoverCurve", {}),
            ("Motion", "Motion", {"scale": 1.0, "auto_scale": True}),
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
            f"Pushover · {driver_description} · "
            f"{steps} step(s) to {target:g}"
        ),
    )


def build_cyclic_template(
    project: ProjectDatabase,
    *,
    name: str,
    control_node: int,
    control_dof: int,
    protocol_rows: Iterable[tuple[float, int]] | None = None,
    protocol_targets: Iterable[float] | None = None,
    max_increment: float,
    distribution: str = "Uniform",
    distribution_weights: dict[int, float] | None = None,
    height_axis: int = 3,
    driver_pattern_tag: int | None = None,
    preload_gravity: bool = True,
    gravity_steps: int = 10,
    finish_at_zero: bool = True,
    solver_preset: str = "Robust",
) -> AnalysisTemplatePlan:
    if int(control_node) not in project.model.nodes:
        raise ValueError(f"Control node {control_node} does not exist.")

    if protocol_targets is not None:
        targets = [float(value) for value in protocol_targets]
        if not targets:
            raise ValueError("Cyclic protocol needs at least one target.")
        if any(not math.isfinite(value) for value in targets):
            raise ValueError("Cyclic targets must be finite.")
        if all(abs(value) <= 1.0e-15 for value in targets):
            raise ValueError(
                "Cyclic protocol needs at least one nonzero target."
            )
    else:
        targets = expand_cyclic_protocol(
            list(protocol_rows or []),
            finish_at_zero=bool(finish_at_zero),
        )

    max_increment = abs(float(max_increment))
    if max_increment <= 0.0:
        raise ValueError("Cyclic max increment must be positive.")
    gravity_steps = int(gravity_steps)
    if gravity_steps < 1:
        raise ValueError("Gravity preload steps must be at least 1.")

    driver_description = f"{distribution} reference pattern"
    if driver_pattern_tag is None:
        series, patterns, loads = _reference_lateral_loading(
            project,
            dof=int(control_dof),
            distribution=distribution,
            prefix="Cyclic",
            custom_weights=distribution_weights,
            height_axis=int(height_axis),
        )
        deferred_pattern_tag = patterns[0].tag
    else:
        driver_pattern_tag = int(driver_pattern_tag)
        pattern = project.load_patterns.get(driver_pattern_tag)
        if pattern is None:
            raise ValueError(
                f"Cyclic driving pattern {driver_pattern_tag} does not exist."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Cyclic driving pattern must be a Plain load pattern."
            )
        series, patterns, loads = [], [], []
        deferred_pattern_tag = driver_pattern_tag
        driver_description = (
            f"existing pattern {driver_pattern_tag} ({pattern.name})"
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
        preload_gravity=bool(preload_gravity),
        gravity_steps=gravity_steps,
        deferred_pattern_tags=[deferred_pattern_tag],
        **_solver_kwargs(solver_preset),
    )
    component = {1: "FX", 2: "FY", 3: "FZ"}[int(control_dof)]
    results = _result_objects(
        project,
        tag,
        [
            ("Cyclic Hysteresis", "CyclicHysteresis", {}),
            ("Motion", "Motion", {"scale": 1.0, "auto_scale": True}),
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
            f"Cyclic · {len(targets)} target(s) · "
            f"{driver_description}"
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


def build_nlth_multi_template(
    project: ProjectDatabase,
    *,
    name: str,
    components: Iterable[GroundMotionComponentSpec],
    dt: float,
    input_unit: str,
    monitor_node: int,
    monitor_dof: int,
    damping_ratio: float = 0.05,
    damping_mode_i: int = 1,
    damping_mode_j: int = 3,
    preload_gravity: bool = True,
    gravity_steps: int = 10,
    require_nodal_mass: bool = False,
    solver_preset: str = "Robust",
) -> AnalysisTemplatePlan:
    specs = list(components)
    if not specs:
        raise ValueError("NLTH needs at least one ground-motion component.")
    dt = float(dt)
    if dt <= 0.0:
        raise ValueError("Ground-motion dt must be positive.")
    if int(monitor_node) not in project.model.nodes:
        raise ValueError(f"Monitor node {monitor_node} does not exist.")
    if int(monitor_dof) not in (1, 2, 3):
        raise ValueError("NLTH monitor DOF must be X, Y or Z.")

    directions = [int(spec.direction) for spec in specs]
    if any(direction not in (1, 2, 3) for direction in directions):
        raise ValueError("NLTH components must use X, Y or Z excitation.")
    if any(direction > int(project.model.ndm) for direction in directions):
        raise ValueError(
            f"NLTH excitation direction exceeds model ndm={project.model.ndm}."
        )
    if len(set(directions)) != len(directions):
        raise ValueError("NLTH excitation directions must be unique.")

    gravity_steps = int(gravity_steps)
    if gravity_steps < 1:
        raise ValueError("NLTH gravity steps must be at least 1.")

    if require_nodal_mass:
        missing_mass_directions = []
        for direction in directions:
            index = direction - 1
            total_mass = sum(
                max(0.0, float(node.mass[index]))
                for node in project.model.nodes.values()
                if index < len(node.mass)
                and not bool(node.fixity[index])
            )
            if total_mass <= 1.0e-15:
                missing_mass_directions.append(
                    {1: "X", 2: "Y", 3: "Z"}[direction]
                )
        if missing_mass_directions:
            raise ValueError(
                "NLTH needs positive translational nodal mass in excitation "
                "direction(s): "
                + ", ".join(missing_mass_directions)
                + ". Assign nodal mass first or disable the template mass check."
            )

    next_series = _next_tag(project.time_series)
    next_pattern = _next_tag(project.load_patterns)
    time_series: list[TimeSeriesData] = []
    patterns: list[LoadPatternData] = []
    max_points = 0
    axis_name = {1: "X", 2: "Y", 3: "Z"}

    for offset, spec in enumerate(specs):
        raw = [float(value) for value in spec.values]
        if not raw:
            raise ValueError(
                f"Ground-motion component {axis_name[int(spec.direction)]} "
                "is empty."
            )
        converted = [
            _acceleration_to_model_units(
                value,
                input_unit,
                project.units,
            )
            for value in raw
        ]
        direction = int(spec.direction)
        label = str(spec.name).strip() or axis_name[direction]
        series_tag = next_series + offset
        pattern_tag = next_pattern + offset
        time_series.append(
            TimeSeriesData(
                tag=series_tag,
                name=f"{name} {label} Ground Motion",
                series_type="Path",
                factor=float(spec.scale_factor),
                dt=dt,
                values=converted,
            )
        )
        patterns.append(
            LoadPatternData(
                tag=pattern_tag,
                name=f"{name} {label} Uniform Excitation",
                pattern_type="UniformExcitation",
                time_series_tag=series_tag,
                direction=direction,
                factor=1.0,
            )
        )
        max_points = max(max_points, len(converted))

    # Path samples are defined from t=0 through (N-1)*dt. The transient
    # analysis therefore advances N-1 nominal intervals to the record end.
    analysis_steps = max(1, max_points - 1)

    tag = project.next_analysis_tag()
    analysis = AnalysisSettingsData(
        tag=tag,
        name=str(name).strip() or f"NLTH {tag}",
        analysis_type="Transient",
        steps=analysis_steps,
        control_node=int(monitor_node),
        control_dof=int(monitor_dof),
        dt=dt,
        gamma=0.5,
        beta=0.25,
        rayleigh_damping_ratio=float(damping_ratio),
        rayleigh_mode_i=int(damping_mode_i),
        rayleigh_mode_j=int(damping_mode_j),
        preload_gravity=bool(preload_gravity),
        gravity_steps=gravity_steps,
        deferred_pattern_tags=[pattern.tag for pattern in patterns],
        **_solver_kwargs(solver_preset),
    )

    result_specs: list[tuple[str, str, dict[str, object]]] = []
    for direction in directions:
        axis = axis_name[direction]
        result_specs.extend([
            (
                f"Displacement History {axis}",
                "TimeHistory",
                {
                    "node": int(monitor_node),
                    "quantity": "Displacement",
                    "dof": direction,
                },
            ),
            (
                f"Velocity History {axis}",
                "TimeHistory",
                {
                    "node": int(monitor_node),
                    "quantity": "Velocity",
                    "dof": direction,
                },
            ),
            (
                f"Acceleration History {axis}",
                "TimeHistory",
                {
                    "node": int(monitor_node),
                    "quantity": "Acceleration",
                    "dof": direction,
                },
            ),
            (
                f"Base Shear History {axis}",
                "TimeHistory",
                {
                    "quantity": "Base shear",
                    "dof": direction,
                },
            ),
        ])
    result_specs.extend([
        ("Motion", "Motion", {"scale": 1.0, "auto_scale": True}),
        ("Deformed Shape", "DeformedShape", {"scale": 10.0}),
        ("Hinge / Yield State", "HingeState", {}),
        ("Member Force Mz", "MemberForce", {"component": "Mz", "scale": 1.0}),
        ("Convergence", "Convergence", {"test": analysis.test}),
    ])
    results = _result_objects(project, tag, result_specs)

    component_text = "+".join(axis_name[direction] for direction in directions)
    return AnalysisTemplatePlan(
        analysis=analysis,
        time_series=time_series,
        load_patterns=patterns,
        results=results,
        summary=(
            f"NLTH {component_text} · {analysis_steps} analysis step(s) · "
            f"duration≈{(max_points - 1) * dt:g} s · dt={dt:g} s · "
            f"{input_unit}"
        ),
    )


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
    preload_gravity: bool = True,
    gravity_steps: int = 10,
    require_nodal_mass: bool = False,
    solver_preset: str = "Robust",
) -> AnalysisTemplatePlan:
    """Backward-compatible one-component NLTH template."""
    return build_nlth_multi_template(
        project,
        name=name,
        components=[
            GroundMotionComponentSpec(
                direction=int(direction),
                values=[float(value) for value in ground_motion_values],
                scale_factor=float(scale_factor),
                name={1: "X", 2: "Y", 3: "Z"}.get(
                    int(direction),
                    str(direction),
                ),
            )
        ],
        dt=dt,
        input_unit=input_unit,
        monitor_node=monitor_node,
        monitor_dof=int(direction),
        damping_ratio=damping_ratio,
        damping_mode_i=damping_mode_i,
        damping_mode_j=damping_mode_j,
        preload_gravity=preload_gravity,
        gravity_steps=gravity_steps,
        require_nodal_mass=require_nodal_mass,
        solver_preset=solver_preset,
    )
