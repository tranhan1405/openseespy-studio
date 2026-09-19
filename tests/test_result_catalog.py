from openseespy_studio.result_catalog import (
    convergence_result_label,
    result_choices_for_analysis,
)


def _types(analysis_type: str) -> set[str]:
    return {
        choice.result_type
        for choice in result_choices_for_analysis(analysis_type)
    }


def test_modal_catalog_only_exposes_mode_shape():
    choices = result_choices_for_analysis("Modal")

    assert len(choices) == 1
    assert choices[0].result_type == "ModeShape"
    assert choices[0].category == "Mode Results"


def test_pushover_catalog_includes_capacity_curve_and_common_results():
    types = _types("Pushover")

    assert "DeformedShape" in types
    assert "MemberForce" in types
    assert "FiberStress" in types
    assert "TimeHistory" in types
    assert "Convergence" in types
    assert "PushoverCurve" in types
    assert "CyclicHysteresis" not in types


def test_cyclic_catalog_includes_hysteresis_not_pushover_curve():
    types = _types("Cyclic")

    assert "CyclicHysteresis" in types
    assert "PushoverCurve" not in types
    assert "TimeHistory" in types


def test_static_and_transient_catalogs_exclude_specialized_curves():
    for analysis_type in ("Static", "Transient"):
        types = _types(analysis_type)
        assert "PushoverCurve" not in types
        assert "CyclicHysteresis" not in types
        assert "TimeHistory" in types
        assert "Convergence" in types



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
