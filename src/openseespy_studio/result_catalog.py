from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .postprocess import nodal_dof_component_labels


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
    ndm: int = 3,
    ndf: int = 6,
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

    displacement_labels = nodal_dof_component_labels(
        ndm=ndm,
        ndf=ndf,
        quantity="Displacement",
    )
    translational_count = min(int(ndm), len(displacement_labels))
    displacement_components = [
        ("Total Deformation", "|U|"),
        *[
            (f"Directional {component}", component)
            for component in displacement_labels[:translational_count]
        ],
    ]
    for component in displacement_labels[translational_count:]:
        displacement_components.append(
            (f"Rotation {component}", component)
        )
    for label, component in displacement_components:
        choices.append(
            ResultChoice(
                "Nodal Displacement",
                label,
                "NodalDisplacement",
                label,
                {"component": component},
            )
        )

    reaction_components = nodal_dof_component_labels(
        ndm=ndm,
        ndf=ndf,
        quantity="Reaction",
    )
    for component in reaction_components:
        choices.append(
            ResultChoice(
                "Nodal Reaction",
                f"Reaction {component}",
                "NodalReaction",
                f"Reaction {component}",
                {"component": component},
            )
        )

    member_components = (
        ("N", "Vy", "Mz")
        if int(ndm) == 2
        else ("N", "Vy", "Vz", "T", "My", "Mz")
    )
    for component in member_components:
        choices.append(
            ResultChoice(
                "Member Forces",
                component,
                "MemberForce",
                f"Member Force {component}",
                {"component": component, "scale": 1.0},
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
