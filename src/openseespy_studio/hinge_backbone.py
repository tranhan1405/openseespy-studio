from __future__ import annotations

from dataclasses import dataclass
import math

from .project import MaterialData


@dataclass(frozen=True, slots=True)
class HingeBackbonePoint:
    """One positive-branch characteristic point in SI units."""

    moment_nm: float
    deformation: float



def suggest_hinge_backbone_points(
    deformation: list[float] | tuple[float, ...],
    moment: list[float] | tuple[float, ...],
) -> tuple[HingeBackbonePoint, HingeBackbonePoint, HingeBackbonePoint]:
    """Suggest three traceable positive-branch points from a monotonic curve.

    The suggestions are deliberately heuristic, not physical labels:
    Point 1 is the first clear stiffness-drop point, Point 2 is the normalized
    knee between Point 1 and the terminal point, and Point 3 is the terminal
    positive-branch point. The researcher must still confirm/edit them.
    """
    samples: list[tuple[float, float]] = []
    last_x = -math.inf
    for raw_x, raw_y in zip(deformation, moment):
        try:
            x = float(raw_x)
            y = float(raw_y)
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or x <= 0.0
            or y <= 0.0
            or x <= last_x
        ):
            continue
        samples.append((x, y))
        last_x = x

    if len(samples) < 3:
        raise ValueError(
            "At least three finite positive, increasing curve points are "
            "required to suggest a hinge backbone."
        )

    n = len(samples)
    terminal_index = n - 1

    # Estimate initial stiffness from the first few secant slopes.  The median
    # is robust to a noisy first sample.
    initial_count = min(max(3, int(round(0.10 * n))), n - 2)
    initial_slopes = sorted(
        y / x
        for x, y in samples[:initial_count]
        if x > 0.0
    )
    initial_stiffness = initial_slopes[len(initial_slopes) // 2]

    first_index = None
    threshold = 0.85 * initial_stiffness
    for index in range(1, terminal_index - 1):
        x, y = samples[index]
        if y / x <= threshold:
            first_index = index
            break

    if first_index is None:
        first_index = max(0, min(terminal_index - 2, int(round(0.20 * terminal_index))))

    # Find a dimensionless geometric knee between Point 1 and the terminal
    # point.  Normalizing each axis prevents unit scaling from biasing the
    # distance measure.
    if first_index >= terminal_index - 1:
        first_index = max(0, terminal_index - 2)

    x1, y1 = samples[first_index]
    x3, y3 = samples[terminal_index]
    x_scale = max(abs(x3), 1.0e-30)
    y_scale = max(max(abs(y) for _, y in samples), 1.0e-30)
    ax, ay = x1 / x_scale, y1 / y_scale
    bx, by = x3 / x_scale, y3 / y_scale
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)

    second_index = None
    best_distance = -1.0
    for index in range(first_index + 1, terminal_index):
        x, y = samples[index]
        px, py = x / x_scale, y / y_scale
        if norm <= 1.0e-30:
            distance = 0.0
        else:
            distance = abs(dy * (px - ax) - dx * (py - ay)) / norm
        if distance > best_distance:
            best_distance = distance
            second_index = index

    if second_index is None:
        second_index = first_index + max(
            1,
            (terminal_index - first_index) // 2,
        )
        second_index = min(second_index, terminal_index - 1)

    if not (first_index < second_index < terminal_index):
        first_index = max(0, terminal_index // 3)
        second_index = max(first_index + 1, (2 * terminal_index) // 3)
        second_index = min(second_index, terminal_index - 1)

    selected = (
        samples[first_index],
        samples[second_index],
        samples[terminal_index],
    )
    return tuple(
        HingeBackbonePoint(moment_nm=float(y), deformation=float(x))
        for x, y in selected
    )

def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be a finite positive value.")
    return number


def hinge_rotations(
    points: list[HingeBackbonePoint] | tuple[HingeBackbonePoint, ...],
    *,
    basis: str,
    equivalent_hinge_length_m: float | None = None,
) -> tuple[float, float, float]:
    """Convert three positive backbone deformation ordinates to rotations.

    moment_rotation accepts radians directly.

    moment_curvature accepts curvature in 1/m and uses the explicit
    equivalent-hinge assumption theta = kappa * L_eq. SARE deliberately
    requires the user to provide L_eq rather than estimating a plastic-hinge
    length silently.
    """
    if len(points) != 3:
        raise ValueError("Hinge backbone requires exactly three positive points.")

    mode = str(basis).strip().lower()
    if mode not in {"moment_rotation", "moment_curvature"}:
        raise ValueError(f"Unsupported hinge-backbone basis: {basis!r}.")

    moments = [
        _finite_positive(point.moment_nm, f"Point {index} moment")
        for index, point in enumerate(points, start=1)
    ]
    raw = [
        _finite_positive(point.deformation, f"Point {index} deformation")
        for index, point in enumerate(points, start=1)
    ]

    if mode == "moment_rotation":
        rotations = raw
    else:
        length = _finite_positive(
            float(equivalent_hinge_length_m or 0.0),
            "Equivalent hinge length",
        )
        rotations = [value * length for value in raw]

    if not (rotations[0] < rotations[1] < rotations[2]):
        raise ValueError(
            "Backbone deformation must increase strictly from Point 1 to "
            "Point 2 to Point 3."
        )

    _ = moments
    return tuple(float(value) for value in rotations)


def build_symmetric_hysteretic_hinge(
    *,
    tag: int,
    name: str,
    points: list[HingeBackbonePoint] | tuple[HingeBackbonePoint, ...],
    basis: str,
    equivalent_hinge_length_m: float | None = None,
    source_kind: str = "manual",
    source_note: str = "",
    pinch_x: float = 1.0,
    pinch_y: float = 1.0,
    damage_1: float = 0.0,
    damage_2: float = 0.0,
    beta: float = 0.0,
) -> MaterialData:
    """Create a symmetric OpenSees Hysteretic moment-rotation material.

    Only the backbone is derived here. Cyclic pinching/degradation parameters
    are carried explicitly and are never inferred from a monotonic section
    curve.
    """
    points = tuple(points)
    rotations = hinge_rotations(
        points,
        basis=basis,
        equivalent_hinge_length_m=equivalent_hinge_length_m,
    )
    moments = tuple(
        _finite_positive(point.moment_nm, f"Point {index} moment")
        for index, point in enumerate(points, start=1)
    )

    for value, label in (
        (pinch_x, "pinchX"),
        (pinch_y, "pinchY"),
    ):
        if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{label} must be between 0 and 1.")
    for value, label in (
        (damage_1, "damage1"),
        (damage_2, "damage2"),
    ):
        if not math.isfinite(float(value)) or float(value) < 0.0:
            raise ValueError(f"{label} must be finite and non-negative.")
    if not math.isfinite(float(beta)):
        raise ValueError("beta must be finite.")

    parameters = {
        "s1p": moments[0],
        "e1p": rotations[0],
        "s2p": moments[1],
        "e2p": rotations[1],
        "s3p": moments[2],
        "e3p": rotations[2],
        "s1n": -moments[0],
        "e1n": -rotations[0],
        "s2n": -moments[1],
        "e2n": -rotations[1],
        "s3n": -moments[2],
        "e3n": -rotations[2],
        "pinchX": float(pinch_x),
        "pinchY": float(pinch_y),
        "damage1": float(damage_1),
        "damage2": float(damage_2),
        "beta": float(beta),
    }

    normalized_basis = str(basis).strip().lower()
    point_key = (
        "rotation_rad"
        if normalized_basis == "moment_rotation"
        else "curvature_per_m"
    )
    calibration_points = []
    for label, moment, point in zip(
        ("point_1", "point_2", "point_3"),
        moments,
        points,
    ):
        calibration_points.append({
            "label": label,
            "moment_nm": moment,
            point_key: float(point.deformation),
        })

    calibration = {
        "workflow": "hinge_backbone",
        "source_kind": str(source_kind).strip() or "manual",
        "source_note": str(source_note).strip(),
        "basis": normalized_basis,
        "symmetry": "mirrored_positive_branch",
        "characteristic_points": calibration_points,
        "cyclic_rule_note": (
            "Pinching and deterioration parameters are user inputs; they are "
            "not inferred from the monotonic backbone."
        ),
    }
    if normalized_basis == "moment_curvature":
        calibration["conversion"] = "theta = kappa * L_eq"
        calibration["equivalent_hinge_length_m"] = float(
            equivalent_hinge_length_m or 0.0
        )

    return MaterialData(
        tag=int(tag),
        name=str(name).strip() or f"Hinge Backbone {int(tag)}",
        material_type="Hysteretic",
        parameters=parameters,
        poisson_ratio=0.0,
        density=0.0,
        source={
            "library": "SARE Hinge Backbone Builder",
            "status": "user-derived",
            "response_quantity": "moment_rotation",
            "calibration": calibration,
        },
    )
