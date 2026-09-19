from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResultChoice:
    category: str
    label: str
    result_type: str
    name: str
    settings: dict[str, Any] = field(default_factory=dict)


def result_choices_for_analysis(analysis_type: str) -> list[ResultChoice]:
    """Return the shared result catalog for Solution and Job menus."""
    kind = str(analysis_type)
    choices: list[ResultChoice] = [
        ResultChoice(
            "Deformation",
            "Deformed Shape",
            "DeformedShape",
            "Deformed Shape",
            {"scale": 10.0},
        ),
    ]

    for label, component in (
        ("Total Deformation", "|U|"),
        ("Directional UX", "UX"),
        ("Directional UY", "UY"),
        ("Directional UZ", "UZ"),
    ):
        choices.append(
            ResultChoice(
                "Nodal Displacement",
                label,
                "NodalDisplacement",
                label,
                {"component": component},
            )
        )

    for component in ("FX", "FY", "FZ", "MX", "MY", "MZ"):
        choices.append(
            ResultChoice(
                "Nodal Reaction",
                f"Reaction {component}",
                "NodalReaction",
                f"Reaction {component}",
                {"component": component},
            )
        )

    for component in ("N", "Vy", "Vz", "T", "My", "Mz"):
        choices.append(
            ResultChoice(
                "Member Forces",
                component,
                "MemberForce",
                f"Member Force {component}",
                {"component": component, "scale": 1.0},
            )
        )

    choices.extend(
        [
            ResultChoice(
                "Nonlinear Results",
                "Fiber Stress",
                "FiberStress",
                "Fiber Stress",
                {"quantity": "Stress"},
            ),
            ResultChoice(
                "Nonlinear Results",
                "Fiber Strain",
                "FiberStrain",
                "Fiber Strain",
                {"quantity": "Strain"},
            ),
            ResultChoice(
                "Nonlinear Results",
                "Hinge / Yield State",
                "HingeState",
                "Hinge / Yield State",
                {},
            ),
        ]
    )

    if kind == "Pushover":
        choices.append(
            ResultChoice(
                "Charts / History",
                "Pushover Capacity Curve",
                "PushoverCurve",
                "Pushover Capacity Curve",
                {},
            )
        )
    if kind == "Cyclic":
        choices.append(
            ResultChoice(
                "Charts / History",
                "Cyclic Hysteresis",
                "CyclicHysteresis",
                "Cyclic Hysteresis",
                {},
            )
        )
    if kind == "Modal":
        choices.append(
            ResultChoice(
                "Charts / History",
                "Mode Shape",
                "ModeShape",
                "Mode Shape 1",
                {"mode": 1, "scale": 1.0},
            )
        )
    else:
        choices.append(
            ResultChoice(
                "Charts / History",
                "Response History",
                "TimeHistory",
                "Response History",
                {},
            )
        )
        choices.append(
            ResultChoice(
                "Solver Results",
                "Convergence History",
                "Convergence",
                "Convergence History",
                {},
            )
        )

    return choices
