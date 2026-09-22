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


def convergence_result_label(test: str | None) -> str:
    key = str(test or "").strip()
    labels = {
        "NormUnbalance": "Force / Residual Convergence",
        "NormDispIncr": "Displacement Increment Convergence",
        "EnergyIncr": "Energy Increment Convergence",
    }
    if key in labels:
        return labels[key]
    return f"{key} Convergence" if key else "Convergence History"


def result_choices_for_analysis(
    analysis_type: str,
    convergence_test: str | None = None,
    *,
    integrator: str | None = None,
    section_response_available: bool = True,
) -> list[ResultChoice]:
    """Return the shared result catalog for Solution and Job menus."""
    kind = str(analysis_type)
    if kind == "Modal":
        return [
            ResultChoice(
                "Mode Results",
                "Mode Shape",
                "ModeShape",
                "Mode Shape 1",
                {
                    "mode": 1,
                    "scale": 1.0,
                    "representation": "actual_section",
                    "smooth_curvature": True,
                },
            ),
            ResultChoice(
                "Motion",
                "Mode Animation",
                "Motion",
                "Mode Motion",
                {"mode": 1, "scale": 1.0, "auto_scale": True},
            ),
        ]

    choices: list[ResultChoice] = [
        ResultChoice(
            "Deformation",
            "Deformed Shape",
            "DeformedShape",
            "Deformed Shape",
            {
                "scale": 10.0,
                "representation": "actual_section",
                "smooth_curvature": True,
            },
        ),
        ResultChoice(
            "Motion",
            "Deformation Animation",
            "Motion",
            "Motion",
            {"scale": 1.0, "auto_scale": True},
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

    for label, component in (
        ("Membrane Nxx", "Nxx"),
        ("Membrane Nyy", "Nyy"),
        ("Membrane Nxy", "Nxy"),
        ("Bending Mxx", "Mxx"),
        ("Bending Myy", "Myy"),
        ("Bending Mxy", "Mxy"),
        ("Transverse Shear Qx", "Qx"),
        ("Transverse Shear Qy", "Qy"),
    ):
        choices.append(
            ResultChoice(
                "Shell Results",
                label,
                "ShellForce",
                f"Shell {component}",
                {"component": component},
            )
        )

    choices.append(
        ResultChoice(
            "Nonlinear Results",
            "1D Column / Specimen Response",
            "SpecimenResponse",
            "1D Column / Specimen Response",
            {},
        )
    )

    if section_response_available:
        choices.append(
            ResultChoice(
                "Nonlinear Results",
                "Section Response",
                "SectionResponse",
                "Section Response",
                {"component": "Mz", "section": 1},
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

    choices.append(
        ResultChoice(
            "Charts / History",
            "Force–Displacement",
            "ForceDisplacement",
            "Force–Displacement",
            {
                "force_source": "Base shear",
            },
        )
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
    choices.append(
        ResultChoice(
            "Charts / History",
            "Response History",
            "TimeHistory",
            "Response History",
            {},
        )
    )
    convergence_name = convergence_result_label(convergence_test)
    choices.append(
        ResultChoice(
            "Solver Results",
            convergence_name,
            "Convergence",
            convergence_name,
            {"test": str(convergence_test or "")},
        )
    )

    return choices
