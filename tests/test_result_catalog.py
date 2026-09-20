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


def test_cyclic_catalog_includes_hysteresis_not_pushover_curve():
    types = _types("Cyclic")

    assert "CyclicHysteresis" in types
    assert "SpecimenResponse" in types
    assert "PushoverCurve" not in types
    assert "TimeHistory" in types
    assert "ForceDisplacement" in types


def test_static_and_transient_catalogs_exclude_specialized_curves():
    for analysis_type in ("Static", "Transient"):
        types = _types(analysis_type)
        assert "PushoverCurve" not in types
        assert "CyclicHysteresis" not in types
        assert "TimeHistory" in types
        assert "ForceDisplacement" in types
        assert "SpecimenResponse" in types
        assert "Motion" in types
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


def test_2d_result_catalog_exposes_only_physical_components():
    choices = result_choices_for_analysis(
        "Static",
        ndm=2,
        ndf=3,
    )
    displacement = {
        choice.settings.get("component")
        for choice in choices
        if choice.result_type == "NodalDisplacement"
    }
    reaction = {
        choice.settings.get("component")
        for choice in choices
        if choice.result_type == "NodalReaction"
    }
    member = {
        choice.settings.get("component")
        for choice in choices
        if choice.result_type == "MemberForce"
    }

    assert displacement == {"|U|", "UX", "UY", "RZ"}
    assert reaction == {"FX", "FY", "MZ"}
    assert member == {"N", "Vy", "Mz"}
