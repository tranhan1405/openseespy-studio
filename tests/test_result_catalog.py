from openseespy_studio.result_catalog import (
    convergence_result_label,
    result_choices_for_analysis,
)


def _types(analysis_type: str) -> set[str]:
    return {
        choice.result_type
        for choice in result_choices_for_analysis(analysis_type)
    }


def test_modal_catalog_exposes_mode_shape_and_motion():
    choices = result_choices_for_analysis("Modal")
    types = {choice.result_type for choice in choices}

    assert types == {"ModeShape", "Motion"}
    assert any(
        choice.result_type == "ModeShape"
        and choice.category == "Mode Results"
        for choice in choices
    )
    assert any(
        choice.result_type == "Motion"
        and choice.category == "Motion"
        for choice in choices
    )


def test_pushover_catalog_includes_capacity_curve_and_common_results():
    types = _types("Pushover")

    assert "DeformedShape" in types
    assert "Motion" in types
    assert "MemberForce" in types
    assert "FiberStress" in types
    assert "SpecimenResponse" in types
    assert "TimeHistory" in types
    assert "ForceDisplacement" in types
    assert "Convergence" in types
    assert "PushoverCurve" in types
    assert "CyclicHysteresis" not in types
    choices = result_choices_for_analysis("Pushover")
    capacity = next(
        choice for choice in choices
        if choice.result_type == "PushoverCurve"
    )
    assert capacity.category == "Nonlinear Results"


def test_cyclic_catalog_includes_hysteresis_not_pushover_curve():
    choices = result_choices_for_analysis("Cyclic")
    types = {choice.result_type for choice in choices}

    assert "CyclicHysteresis" in types
    assert "CyclicBackbone" in types
    assert "CyclicReversalMetrics" in types
    assert "CyclicCycleMetrics" in types
    assert "SpecimenResponse" in types
    assert "PushoverCurve" not in types
    assert "TimeHistory" in types
    assert "ForceDisplacement" in types

    nonlinear = {
        choice.result_type: choice
        for choice in choices
        if choice.result_type.startswith("Cyclic")
    }
    assert nonlinear["CyclicHysteresis"].category == "Nonlinear Results"
    assert (
        nonlinear["CyclicHysteresis"].label
        == "Hysteretic Force–Displacement"
    )
    assert nonlinear["CyclicBackbone"].label == "Backbone / Envelope"
    assert (
        nonlinear["CyclicCycleMetrics"].label
        == "Cycle Energy & Degradation"
    )


def test_static_catalog_excludes_cyclic_response_metrics():
    types = _types("Static")
    assert "PushoverCurve" not in types
    assert "CyclicHysteresis" not in types
    assert "TimeHistory" in types
    assert "ForceDisplacement" in types
    assert "SpecimenResponse" in types
    assert "Motion" in types
    assert "Convergence" in types


def test_transient_catalog_exposes_capability_based_cyclic_response_metrics():
    choices = result_choices_for_analysis("Transient")
    types = {choice.result_type for choice in choices}

    assert "PushoverCurve" not in types
    assert "CyclicHysteresis" in types
    assert "CyclicBackbone" in types
    assert "CyclicReversalMetrics" in types
    assert "CyclicCycleMetrics" in types
    assert all(
        choice.category == "Nonlinear Results"
        for choice in choices
        if choice.result_type.startswith("Cyclic")
    )
    assert "TimeHistory" in types
    assert "ForceDisplacement" in types



def test_section_response_catalog_is_capability_gated():
    available = {
        choice.result_type
        for choice in result_choices_for_analysis(
            "Static",
            integrator="DisplacementControl",
            section_response_available=True,
        )
    }
    unavailable = {
        choice.result_type
        for choice in result_choices_for_analysis(
            "Static",
            integrator="DisplacementControl",
            section_response_available=False,
        )
    }

    assert "SectionResponse" in available
    assert "SectionResponse" not in unavailable
    # MomentCurvature is now an automatic recognized workflow rather than
    # a generic manual result request exposed for every Static DC analysis.
    assert "MomentCurvature" not in available


def test_convergence_result_label_matches_analysis_test():
    assert (
        convergence_result_label("NormUnbalance")
        == "Force / Residual Convergence"
    )
    assert (
        convergence_result_label("NormDispIncr")
        == "Displacement Increment Convergence"
    )
    assert (
        convergence_result_label("EnergyIncr")
        == "Energy Increment Convergence"
    )


def test_result_catalog_uses_specific_convergence_name():
    choices = result_choices_for_analysis(
        "Static",
        convergence_test="NormUnbalance",
    )
    convergence = next(
        choice for choice in choices
        if choice.result_type == "Convergence"
    )

    assert convergence.label == "Force / Residual Convergence"
    assert convergence.name == "Force / Residual Convergence"
    assert convergence.settings["test"] == "NormUnbalance"


def test_force_displacement_catalog_default_uses_base_shear():
    choices = result_choices_for_analysis("Cyclic")
    item = next(
        choice
        for choice in choices
        if choice.result_type == "ForceDisplacement"
    )

    assert item.category == "Charts / History"
    assert item.label == "Force–Displacement"
    assert item.settings["force_source"] == "Base shear"

def test_nodal_results_default_to_global_animation_contour_range():
    for analysis_kind in ("Static", "Transient", "Cyclic", "Pushover"):
        choices = result_choices_for_analysis(analysis_kind)
        nodal = [
            choice
            for choice in choices
            if choice.result_type in {"NodalDisplacement", "NodalReaction"}
        ]
        assert nodal
        assert all(
            choice.settings.get("contour_range_mode") == "global"
            for choice in nodal
        )

