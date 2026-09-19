import math

from openseespy_studio.model import StructuralModel
from openseespy_studio.postprocess import (
    classify_fiber_state,
    component_end_resultants,
    enrich_fiber_state_results,
    enrich_member_force_results,
    equilibrium_component_samples,
    fiber_response_element_tags,
    fiber_response_range,
    fiber_response_sections,
    fiber_state_element_tags,
    fiber_state_sections,
    local_end_actions,
    member_end_resultants,
    nodal_result_scalar,
    pushover_capacity_curve,
    section_component_samples,
    time_history_node_tags,
    time_history_series,
)
from openseespy_studio.project import (
    ElementLoadData,
    MaterialData,
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


def test_pushover_capacity_curve_uses_control_dof_and_applied_shear_sign():
    result = {
        "analysis": {
            "type": "Pushover",
            "control_node": 9,
            "control_dof": 2,
        },
        "history": {
            "monitor_node": 9,
            "control_dof": 2,
            "displacement": [
                [0.0, 0.01, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.02, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.03, 0.0, 0.0, 0.0, 0.0],
            ],
            "base_shear": [-100.0, -180.0, -150.0],
        },
    }

    x, y, node, dof = pushover_capacity_curve(result)

    assert x == [0.01, 0.02, 0.03]
    assert y == [100.0, 180.0, 150.0]
    assert node == 9
    assert dof == 2


def test_pushover_capacity_curve_rejects_non_pushover_results():
    x, y, node, dof = pushover_capacity_curve(
        {
            "analysis": {"type": "Static"},
            "history": {
                "displacement": [[0.1] * 6],
                "base_shear": [-10.0],
            },
        }
    )

    assert x == []
    assert y == []
    assert node is None
    assert dof is None


def test_time_history_node_tags_and_nodal_series():
    result = {
        "history": {
            "time": [0.1, 0.2],
            "monitor_node": 2,
            "nodes": {
                "2": {
                    "disp": [[1.0, 2.0], [3.0, 4.0]],
                    "vel": [[5.0, 6.0], [7.0, 8.0]],
                    "accel": [[9.0, 10.0], [11.0, 12.0]],
                    "reaction": [[-1.0, -2.0], [-3.0, -4.0]],
                },
                "10": {
                    "disp": [[0.0, 0.5], [0.0, 1.0]],
                    "vel": [[0.0, 1.5], [0.0, 2.0]],
                    "accel": [[0.0, 2.5], [0.0, 3.0]],
                    "reaction": [[0.0, -5.0], [0.0, -6.0]],
                },
            },
        },
    }

    assert time_history_node_tags(result) == [2, 10]
    assert time_history_series(
        result, "Displacement", node_tag=10, dof=2
    ) == ([0.1, 0.2], [0.5, 1.0])
    assert time_history_series(
        result, "Velocity", node_tag=2, dof=1
    ) == ([0.1, 0.2], [5.0, 7.0])
    assert time_history_series(
        result, "Acceleration", node_tag=2, dof=2
    ) == ([0.1, 0.2], [10.0, 12.0])
    assert time_history_series(
        result, "Reaction", node_tag=10, dof=2
    ) == ([0.1, 0.2], [-5.0, -6.0])


def test_time_history_base_shear_uses_all_support_reaction_components():
    result = {
        "history": {
            "time": [0.1, 0.2],
            "control_dof": 1,
            "base_reactions": [
                [-100.0, 20.0, 0.0, 0.0, 0.0, 0.0],
                [-150.0, 30.0, 0.0, 0.0, 0.0, 0.0],
            ],
        },
    }

    assert time_history_series(
        result, "Base shear", dof=1
    ) == ([0.1, 0.2], [100.0, 150.0])
    assert time_history_series(
        result, "Base shear", dof=2
    ) == ([0.1, 0.2], [-20.0, -30.0])
    assert time_history_series(result, "Base shear", dof=4) == ([], [])


def test_time_history_schema3_monitor_displacement_remains_readable():
    result = {
        "history": {
            "time": [1.0, 2.0],
            "monitor_node": 7,
            "control_dof": 1,
            "displacement": [[0.01], [0.02]],
            "base_shear": [-10.0, -20.0],
        },
    }

    assert time_history_node_tags(result) == [7]
    assert time_history_series(
        result, "Displacement", node_tag=7, dof=1
    ) == ([1.0, 2.0], [0.01, 0.02])
    assert time_history_series(
        result, "Base shear", dof=1
    ) == ([1.0, 2.0], [10.0, 20.0])


def test_fiber_response_helpers_extract_sections_and_ranges():
    result = {
        "final": {
            "element_fiber_responses": {
                "12": {
                    "section_tag": 4,
                    "sections": [
                        {
                            "number": 1,
                            "location": 0.0,
                            "fibers": [
                                {
                                    "y": -0.1,
                                    "z": 0.0,
                                    "area": 0.01,
                                    "material_tag": 2,
                                    "stress": -25.0,
                                    "strain": -0.001,
                                },
                                {
                                    "y": 0.1,
                                    "z": 0.0,
                                    "area": 0.01,
                                    "material_tag": 3,
                                    "stress": 40.0,
                                    "strain": 0.002,
                                },
                            ],
                        }
                    ],
                }
            }
        }
    }

    assert fiber_response_element_tags(result) == [12]
    sections = fiber_response_sections(result, 12)
    assert len(sections) == 1
    assert fiber_response_range(sections[0], "stress") == (-25.0, 40.0)
    assert fiber_response_range(sections[0], "strain") == (-0.001, 0.002)


def test_fiber_response_range_ignores_missing_values_and_validates_quantity():
    section = {
        "fibers": [
            {"stress": None, "strain": 0.0},
            {"stress": 2.5, "strain": None},
        ]
    }

    assert fiber_response_range(section, "stress") == (2.5, 2.5)
    assert fiber_response_range({}, "strain") == (None, None)
    try:
        fiber_response_range(section, "energy")
    except ValueError as exc:
        assert "Unsupported fiber-response quantity" in str(exc)
    else:
        raise AssertionError("Expected unsupported fiber quantity to fail")


def test_steel02_fiber_state_uses_yield_strain_ratio():
    steel = MaterialData(
        2,
        "Steel",
        "Steel02",
        parameters={
            "Fy": 400.0e6,
            "E0": 200.0e9,
            "b": 0.01,
            "R0": 20.0,
            "cR1": 0.925,
            "cR2": 0.15,
        },
    )
    materials = {2: steel}

    elastic = classify_fiber_state(
        {"material_tag": 2, "strain": 0.0010, "stress": 200.0e6},
        materials,
    )
    near = classify_fiber_state(
        {"material_tag": 2, "strain": 0.0018, "stress": 350.0e6},
        materials,
    )
    yielding = classify_fiber_state(
        {"material_tag": 2, "strain": 0.0022, "stress": 402.0e6},
        materials,
    )
    plastic = classify_fiber_state(
        {"material_tag": 2, "strain": 0.0040, "stress": 410.0e6},
        materials,
    )

    assert elastic["severity"] == 0
    assert near["severity"] == 1
    assert yielding["severity"] == 2
    assert plastic["severity"] == 3
    assert math.isclose(yielding["yield_strain"], 0.002)


def test_concrete02_fiber_state_tracks_cracking_softening_and_crushing():
    concrete = MaterialData(
        3,
        "Concrete",
        "Concrete02",
    )
    materials = {3: concrete}

    cracked = classify_fiber_state(
        {"material_tag": 3, "strain": 0.00015, "stress": 1.0e6},
        materials,
    )
    nonlinear = classify_fiber_state(
        {"material_tag": 3, "strain": -0.0017, "stress": -28.0e6},
        materials,
    )
    softening = classify_fiber_state(
        {"material_tag": 3, "strain": -0.0030, "stress": -20.0e6},
        materials,
    )
    crushing = classify_fiber_state(
        {"material_tag": 3, "strain": -0.0065, "stress": -5.0e6},
        materials,
    )

    assert cracked["severity"] == 1
    assert nonlinear["severity"] == 1
    assert softening["severity"] == 2
    assert crushing["severity"] == 3


def test_fiber_state_enrichment_summarizes_hinge_locations():
    materials = {
        2: MaterialData(2, "Steel", "Steel02"),
    }
    result = {
        "final": {
            "element_fiber_responses": {
                "10": {
                    "sections": [
                        {
                            "number": 1,
                            "location": 0.0,
                            "fibers": [
                                {
                                    "material_tag": 2,
                                    "strain": 0.001,
                                    "stress": 200.0e6,
                                    "y": -0.1,
                                    "z": 0.0,
                                }
                            ],
                        },
                        {
                            "number": 2,
                            "location": 1.5,
                            "fibers": [
                                {
                                    "material_tag": 2,
                                    "strain": 0.003,
                                    "stress": 360.0e6,
                                    "y": 0.1,
                                    "z": 0.0,
                                }
                            ],
                        },
                    ]
                }
            }
        }
    }

    enriched = enrich_fiber_state_results(result, materials)

    assert fiber_state_element_tags(enriched) == [10]
    sections = fiber_state_sections(enriched, 10)
    assert [row["severity"] for row in sections] == [0, 2]
    summary = enriched["final"]["fiber_state_summary"]["10"]
    assert summary["severity"] == 2
    assert summary["hinge_count"] == 1
    assert sections[1]["controlling_fiber"]["material_tag"] == 2

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
