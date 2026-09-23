from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence


def build_period_grid(
    step_1: float,
    end_1: float,
    step_2: float,
    end_2: float,
    step_3: float,
    end_3: float,
) -> list[float]:
    """Build the three-region period grid used by spectrum generation."""
    regions = (
        (float(step_1), float(end_1)),
        (float(step_2), float(end_2)),
        (float(step_3), float(end_3)),
    )
    periods: list[float] = []
    previous_end = 0.0
    for index, (step, end) in enumerate(regions):
        if not math.isfinite(step) or step <= 0.0:
            raise ValueError("Response-spectrum period intervals must be positive.")
        if not math.isfinite(end) or end <= 0.0:
            raise ValueError("Response-spectrum region ends must be positive.")
        if index and end < previous_end:
            raise ValueError(
                "Response-spectrum region ends must be non-decreasing."
            )
        value = step if index == 0 else previous_end + step
        tolerance = max(1.0, abs(end)) * 1.0e-12
        while value <= end + tolerance:
            periods.append(float(round(value, 12)))
            value += step
        previous_end = end
    if not periods:
        raise ValueError("Response-spectrum period grid is empty.")
    return periods


def _newmark_relative_displacement(
    acceleration: Sequence[float],
    dt: float,
    period: float,
    damping_ratio: float,
) -> list[float]:
    """Linear SDOF relative-displacement history using average acceleration."""
    values = [float(value) for value in acceleration]
    dt = float(dt)
    period = float(period)
    damping_ratio = float(damping_ratio)
    if dt <= 0.0:
        raise ValueError("Ground-motion dt must be positive.")
    if period <= 0.0:
        raise ValueError("Response-spectrum period must be positive.")
    if not 0.0 <= damping_ratio < 1.0:
        raise ValueError("Response-spectrum damping ratio must be in [0, 1).")
    if not values:
        raise ValueError("Ground-motion acceleration history is empty.")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Ground-motion acceleration values must be finite.")

    gamma = 0.5
    beta = 0.25
    omega = 2.0 * math.pi / period
    stiffness = omega * omega
    damping = 2.0 * damping_ratio * omega

    a0 = 1.0 / (beta * dt * dt)
    a1 = gamma / (beta * dt)
    a2 = 1.0 / (beta * dt)
    a3 = 1.0 / (2.0 * beta) - 1.0
    a4 = gamma / beta - 1.0
    a5 = dt * (gamma / (2.0 * beta) - 1.0)
    effective_stiffness = stiffness + a0 + a1 * damping

    displacement = 0.0
    velocity = 0.0
    relative_acceleration = -values[0]
    history = [0.0]

    for ground_acceleration in values[1:]:
        effective_force = (
            -ground_acceleration
            + a0 * displacement
            + a2 * velocity
            + a3 * relative_acceleration
            + damping
            * (
                a1 * displacement
                + a4 * velocity
                + a5 * relative_acceleration
            )
        )
        next_displacement = effective_force / effective_stiffness
        next_acceleration = (
            a0 * (next_displacement - displacement)
            - a2 * velocity
            - a3 * relative_acceleration
        )
        next_velocity = velocity + dt * (
            (1.0 - gamma) * relative_acceleration
            + gamma * next_acceleration
        )
        displacement = next_displacement
        velocity = next_velocity
        relative_acceleration = next_acceleration
        history.append(displacement)

    return history


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("Cannot calculate a median from an empty sequence.")
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return 0.5 * (ordered[midpoint - 1] + ordered[midpoint])


def compute_response_spectrum(
    components: Sequence[Mapping[str, object]],
    periods: Iterable[float],
    damping_ratio: float,
    gravity: float,
    *,
    include_component_x: bool = True,
    include_component_y: bool = True,
    include_rotd50: bool = True,
    include_rotd100: bool = True,
    rotation_step_deg: int = 1,
) -> dict[str, object]:
    """Compute component and RotD pseudo-acceleration spectra in Sa/g."""
    source = [dict(component) for component in components]
    if len(source) not in {1, 2}:
        raise ValueError("Response spectrum needs one or two components.")
    gravity = abs(float(gravity))
    if not math.isfinite(gravity) or gravity <= 0.0:
        raise ValueError("Reference gravity must be a positive finite value.")
    damping_ratio = float(damping_ratio)
    if not 0.0 <= damping_ratio < 1.0:
        raise ValueError("Response-spectrum damping ratio must be in [0, 1).")
    rotation_step_deg = int(rotation_step_deg)
    if rotation_step_deg < 1 or rotation_step_deg > 179:
        raise ValueError("RotD rotation step must be between 1 and 179 degrees.")

    prepared: list[dict[str, object]] = []
    for component in source:
        dt = float(component.get("dt", 0.0))
        values = [float(value) for value in component.get("values", [])]
        if dt <= 0.0 or not values:
            raise ValueError("Response-spectrum sources need Path data and dt.")
        prepared.append({
            "pattern_tag": component.get("pattern_tag"),
            "time_series_tag": component.get("time_series_tag"),
            "direction": component.get("direction"),
            "name": str(component.get("name", "")),
            "dt": dt,
            "values": values,
        })

    bidirectional = len(prepared) == 2
    if bidirectional:
        if not math.isclose(
            float(prepared[0]["dt"]),
            float(prepared[1]["dt"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError(
                "Bidirectional RotD sources must use the same time step."
            )
        if len(prepared[0]["values"]) != len(prepared[1]["values"]):
            raise ValueError(
                "Bidirectional RotD sources must have the same number of points."
            )

    period_values = [float(value) for value in periods]
    if not period_values or any(
        not math.isfinite(value) or value <= 0.0
        for value in period_values
    ):
        raise ValueError("Response-spectrum periods must be positive and finite.")

    result: dict[str, object] = {
        "period_s": period_values,
        "damping_ratio": damping_ratio,
        "sources": [
            {
                key: component.get(key)
                for key in (
                    "pattern_tag",
                    "time_series_tag",
                    "direction",
                    "name",
                    "dt",
                )
            }
            for component in prepared
        ],
    }
    component_x: list[float] = []
    component_y: list[float] = []
    rotd50: list[float] = []
    rotd100: list[float] = []

    for period in period_values:
        omega = 2.0 * math.pi / period
        ux = _newmark_relative_displacement(
            prepared[0]["values"],
            float(prepared[0]["dt"]),
            period,
            damping_ratio,
        )
        if include_component_x:
            component_x.append(
                omega * omega * max(abs(value) for value in ux) / gravity
            )

        if bidirectional:
            uy = _newmark_relative_displacement(
                prepared[1]["values"],
                float(prepared[1]["dt"]),
                period,
                damping_ratio,
            )
            if include_component_y:
                component_y.append(
                    omega * omega * max(abs(value) for value in uy) / gravity
                )
            if include_rotd50 or include_rotd100:
                rotated: list[float] = []
                for theta in range(0, 180, rotation_step_deg):
                    radians = math.radians(theta)
                    cosine = math.cos(radians)
                    sine = math.sin(radians)
                    peak = max(
                        abs(x * cosine + y * sine)
                        for x, y in zip(ux, uy)
                    )
                    rotated.append(omega * omega * peak / gravity)
                if include_rotd50:
                    rotd50.append(_median(rotated))
                if include_rotd100:
                    rotd100.append(max(rotated))

    if include_component_x:
        result["component_x_sa_g"] = component_x
    if bidirectional and include_component_y:
        result["component_y_sa_g"] = component_y
    if bidirectional and include_rotd50:
        result["rotd50_sa_g"] = rotd50
    if bidirectional and include_rotd100:
        result["rotd100_sa_g"] = rotd100
    return result
