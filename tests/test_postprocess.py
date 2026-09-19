import math

from openseespy_studio.model import StructuralModel
from openseespy_studio.postprocess import (
    component_end_resultants,
    enrich_member_force_results,
    equilibrium_component_samples,
    local_end_actions,
    member_end_resultants,
    nodal_result_scalar,
    section_component_samples,
)
from openseespy_studio.project import (
    ElementLoadData,
    SectionData,
    TransformationData,
)



def test_nodal_result_scalar_keeps_force_and_moment_groups_separate():
    values = [3.0, 4.0, 12.0, 0.1, 0.2, 0.2]

    assert nodal_result_scalar(values, "UX") == 3.0
    assert nodal_result_scalar(values, "FY") == 4.0
    assert math.isclose(nodal_result_scalar(values, "|U|"), 13.0)
    assert math.isclose(nodal_result_scalar(values, "|F|"), 13.0)
    assert math.isclose(nodal_result_scalar(values, "|R|"), 0.3)
    assert math.isclose(nodal_result_scalar(values, "|M|"), 0.3)


def test_nodal_result_scalar_handles_short_vectors_and_bad_components():
    assert nodal_result_scalar([1.0, 2.0, 3.0], "RZ") is None

    try:
        nodal_result_scalar([1.0] * 6, "Q")
    except ValueError as exc:
        assert "Unsupported nodal result component" in str(exc)
    else:
        raise AssertionError("Expected unsupported nodal component to fail")

def _local_force_vector():
    return [
        -10.0,
        -20.0,
        -30.0,
        -40.0,
        -50.0,
        -60.0,
        10.0,
        21.0,
        31.0,
        41.0,
        51.0,
        61.0,
    ]


def test_local_end_actions_follow_3d_local_dof_order():
    actions = local_end_actions(_local_force_vector())

    assert actions["N"] == (-10.0, 10.0)
    assert actions["Vy"] == (-20.0, 21.0)
    assert actions["Vz"] == (-30.0, 31.0)
    assert actions["T"] == (-40.0, 41.0)
    assert actions["My"] == (-50.0, 51.0)
    assert actions["Mz"] == (-60.0, 61.0)


def test_member_end_resultants_follow_opensees_section_signs():
    resultants = member_end_resultants(_local_force_vector())

    assert resultants["N"] == (10.0, 10.0)
    # OpenSees 3D localForce uses the opposite nodal-action convention for
    # local-y shear compared with the section Vy resultant.
    assert resultants["Vy"] == (-20.0, -21.0)
    assert resultants["Vz"] == (30.0, 31.0)
    assert resultants["T"] == (40.0, 41.0)
    assert resultants["My"] == (50.0, 51.0)
    assert resultants["Mz"] == (60.0, 61.0)


def test_component_end_resultants_returns_none_for_short_response():
    assert component_end_resultants([1.0, 2.0], "N") is None


def test_component_end_resultants_validates_component_name():
    try:
        component_end_resultants(_local_force_vector(), "Q")
    except ValueError as exc:
        assert "Unsupported local force component" in str(exc)
    else:
        raise AssertionError("Expected unsupported component to fail")


def test_uniform_load_equilibrium_diagram_is_parabolic_and_exact_at_midspan():
    # L=4, wy=-10. Section Vy starts +20 and ends -20.
    # Mz starts and ends at zero: Mz(x)=20x-5x^2.
    local = [
        0.0, 20.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 20.0, 0.0, 0.0, 0.0, 0.0,
    ]
    loads = [{"type": "Uniform", "wx": 0.0, "wy": -10.0, "wz": 0.0}]

    samples = equilibrium_component_samples(
        local,
        4.0,
        "Mz",
        loads,
        sample_count=6,
    )
    by_x = {round(x, 8): value for x, value in samples}

    # The extrema finder must insert the true shear-zero location even though
    # 2.0 is not a point in a six-point uniform sample grid.
    assert 2.0 in by_x
    assert math.isclose(by_x[2.0], 20.0)
    assert math.isclose(samples[0][1], 0.0)
    assert math.isclose(samples[-1][1], 0.0)


def test_point_load_creates_explicit_shear_jump_and_continuous_moment():
    # Simply supported-like equilibrium for Py=-10 at L/2.
    local = [
        0.0, 5.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 5.0, 0.0, 0.0, 0.0, 0.0,
    ]
    loads = [
        {
            "type": "Point",
            "px": 0.0,
            "py": -10.0,
            "pz": 0.0,
            "x_over_l": 0.5,
        }
    ]

    shear = equilibrium_component_samples(
        local,
        4.0,
        "Vy",
        loads,
        sample_count=5,
    )
    at_mid = [value for x, value in shear if math.isclose(x, 2.0)]
    assert at_mid == [5.0, -5.0]

    moment = equilibrium_component_samples(
        local,
        4.0,
        "Mz",
        loads,
        sample_count=5,
    )
    at_mid_m = [value for x, value in moment if math.isclose(x, 2.0)]
    assert at_mid_m == [10.0]


def test_section_component_samples_use_3d_section_force_order():
    section_data = {
        "locations": [0.0, 2.0, 4.0],
        "forces": [
            [10.0, 20.0, 30.0, 40.0],
            [11.0, 21.0, 31.0, 41.0],
            [12.0, 22.0, 32.0, 42.0],
        ],
    }

    assert section_component_samples(section_data, "N") == [
        (0.0, 10.0), (2.0, 11.0), (4.0, 12.0)
    ]
    assert section_component_samples(section_data, "Mz")[1] == (2.0, 21.0)
    assert section_component_samples(section_data, "My")[1] == (2.0, 31.0)
    assert section_component_samples(section_data, "T")[1] == (2.0, 41.0)
    assert section_component_samples(section_data, "Vy") == []


def _frame_model(element_type: str) -> StructuralModel:
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type=element_type,
        section_tag=1,
        transf_tag=1,
    )
    return model


def test_enrichment_prefers_section_points_for_disp_beam_nonlinear_resultants():
    model = _frame_model("dispBeamColumn")
    local = [
        -10.0, 5.0, 0.0, -2.0, 3.0, 4.0,
        10.0, -5.0, 0.0, 2.0, 7.0, 8.0,
    ]
    result = {
        "analysis": {"type": "Static"},
        "final": {
            "element_local_forces": {"1": local},
            "element_section_forces": {
                "1": {
                    "locations": [0.5, 2.0, 3.5],
                    "weights": [1.0, 2.0, 1.0],
                    "forces": [
                        [10.0, -3.0, -2.0, 2.0],
                        [10.0, 2.0, 1.0, 2.0],
                        [10.0, 7.0, 5.0, 2.0],
                    ],
                }
            },
            "load_factors": {},
        },
    }

    enriched = enrich_member_force_results(
        result,
        model,
        {},
        {1: SectionData(1, "S", "Elastic", {"A": 0.1})},
        {},
        {1: TransformationData(1, "T", "Linear", (0.0, 0.0, 1.0))},
        {"length": "m", "force": "kN", "time": "s"},
    )

    mz = enriched["final"]["member_force_diagrams"]["1"]["Mz"]
    assert mz["source"] == "section integration points"
    assert mz["x"] == [0.0, 0.5, 2.0, 3.5, 4.0]
    assert mz["values"][1:4] == [-3.0, 2.0, 7.0]


def test_enrichment_uses_current_plain_pattern_factor_for_equilibrium():
    model = _frame_model("forceBeamColumn")
    local = [
        0.0, 10.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 10.0, 0.0, 0.0, 0.0, 0.0,
    ]
    load = ElementLoadData(
        1,
        "Half active UDL",
        7,
        1,
        "Uniform",
        wy=-10.0,
    )
    result = {
        "analysis": {"type": "Static"},
        "final": {
            "element_local_forces": {"1": local},
            "element_section_forces": {},
            "load_factors": {"7": 0.5},
        },
    }

    enriched = enrich_member_force_results(
        result,
        model,
        {1: load},
        {1: SectionData(1, "S", "Elastic", {"A": 0.1})},
        {},
        {1: TransformationData(1, "T", "Linear", (0.0, 0.0, 1.0))},
        {"length": "m", "force": "kN", "time": "s"},
    )

    vy = enriched["final"]["member_force_diagrams"]["1"]["Vy"]
    assert vy["source"] == "equilibrium"
    assert math.isclose(vy["values"][0], 10.0)
    assert math.isclose(vy["values"][-1], -10.0)
