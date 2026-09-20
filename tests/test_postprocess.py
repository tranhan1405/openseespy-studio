import math

import pytest

from openseespy_studio.model import StructuralModel
from openseespy_studio.postprocess import (
    classify_fiber_state,
    component_end_resultants,
    convergence_series,
    convergence_steps,
    convergence_trace,
    convergence_summary,
    cyclic_backbone_curve,
    cyclic_curve_comparison,
    cyclic_hysteresis_curve,
    cyclic_hysteresis_metrics,
    cyclic_reversal_comparison,
    cyclic_reversal_points,
    experimental_csv_series,
    parse_experimental_csv_text,
    column_cyclic_cycle_metrics,
    column_cyclic_reversal_metrics,
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
    column_fiber_history_catalog,
    column_interface_moment_rotation_curve,
    column_moment_curvature_curve,
    column_response_summary,
    column_rotation_decomposition,
    column_specimen_research_metrics,
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


def test_cyclic_hysteresis_curve_uses_control_displacement_and_applied_shear():
    result = {
        "analysis": {
            "type": "Cyclic",
            "control_node": 8,
            "control_dof": 1,
        },
        "history": {
            "monitor_node": 8,
            "control_dof": 1,
            "displacement": [
                [0.001, 0, 0, 0, 0, 0],
                [0.002, 0, 0, 0, 0, 0],
                [0.001, 0, 0, 0, 0, 0],
                [0.0, 0, 0, 0, 0, 0],
            ],
            "base_shear": [-10.0, -20.0, -5.0, 0.0],
        },
    }

    x, y, node, dof = cyclic_hysteresis_curve(result)

    assert x == [0.0, 0.001, 0.002, 0.001, 0.0]
    assert y == [0.0, 10.0, 20.0, 5.0, -0.0]
    assert node == 8
    assert dof == 1


def test_cyclic_reversals_and_closed_path_energy():
    x = [0.0, 1.0, 2.0, 1.0, 0.0, -1.0, 0.0]
    y = [0.0, 2.0, 4.0, 1.0, 0.0, -1.0, 0.0]

    reversals = cyclic_reversal_points(x, y)
    assert reversals[0]["displacement"] == 2.0
    assert reversals[0]["force"] == 4.0
    assert reversals[0]["secant_stiffness"] == 2.0
    assert reversals[1]["displacement"] == -1.0
    assert reversals[1]["force"] == -1.0

    metrics = cyclic_hysteresis_metrics(x, y)
    assert metrics["closed_path"] is True
    assert metrics["dissipated_energy"] is not None
    assert math.isclose(
        metrics["dissipated_energy"],
        abs(metrics["signed_work"]),
    )
    assert metrics["max_abs_displacement"] == 2.0
    assert metrics["max_abs_force"] == 4.0


def test_cyclic_open_path_does_not_label_work_as_dissipated_energy():
    metrics = cyclic_hysteresis_metrics(
        [0.0, 0.01, 0.02],
        [0.0, 10.0, 15.0],
    )

    assert metrics["closed_path"] is False
    assert metrics["dissipated_energy"] is None
    assert metrics["signed_work"] > 0.0




def test_cyclic_repeated_amplitude_reports_strength_and_stiffness_ratios():
    x = [0.0, 1.0, -1.0, 1.0, -1.0, 0.0]
    y = [0.0, 10.0, -9.0, 8.0, -7.0, 0.0]

    metrics = cyclic_hysteresis_metrics(x, y)
    reversals = metrics["reversals"]

    positive = [
        item for item in reversals
        if item["displacement"] > 0.0
    ]
    negative = [
        item for item in reversals
        if item["displacement"] < 0.0
    ]

    assert positive[0]["strength_ratio"] == pytest.approx(1.0)
    assert positive[1]["strength_ratio"] == pytest.approx(0.8)
    assert positive[1]["stiffness_ratio"] == pytest.approx(0.8)
    assert negative[0]["strength_ratio"] == pytest.approx(1.0)
    assert negative[1]["strength_ratio"] == pytest.approx(7.0 / 9.0)
    assert metrics["closed_cycle_count"] >= 1
    assert metrics["cycle_energies"][0]["energy"] > 0.0
    assert metrics["peak_positive_force"] == 10.0
    assert metrics["peak_negative_force"] == -9.0
    assert metrics["residual_displacement"] == 0.0

def test_convergence_dashboard_helpers_summarize_recovery_and_failure():
    result = {
        "convergence": {
            "test": "NormDispIncr",
            "tolerance": 1.0e-8,
            "max_iterations": 50,
            "primary_algorithm": "Newton",
            "steps": [
                {
                    "step": 1,
                    "status": "converged",
                    "algorithm": "Newton",
                    "iterations": 4,
                    "norm": 1.0e-10,
                    "recovered": False,
                    "time": 0.1,
                    "attempts": [
                        {
                            "algorithm": "Newton",
                            "iterations": 4,
                            "norm": 1.0e-10,
                            "code": 0,
                            "success": True,
                        }
                    ],
                },
                {
                    "step": 2,
                    "status": "recovered",
                    "algorithm": "NewtonLineSearch",
                    "iterations": 7,
                    "norm": 5.0e-9,
                    "recovered": True,
                    "time": 0.2,
                    "attempts": [
                        {
                            "algorithm": "Newton",
                            "iterations": 50,
                            "norm": 2.0e-4,
                            "code": -3,
                            "success": False,
                        },
                        {
                            "algorithm": "NewtonLineSearch",
                            "iterations": 7,
                            "norm": 5.0e-9,
                            "code": 0,
                            "success": True,
                        },
                    ],
                },
                {
                    "step": 3,
                    "status": "failed",
                    "algorithm": "ModifiedNewton",
                    "iterations": 50,
                    "norm": 1.0e-2,
                    "recovered": False,
                    "time": 0.2,
                    "attempts": [
                        {
                            "algorithm": "Newton",
                            "iterations": 50,
                            "norm": 1.0e-3,
                            "code": -3,
                            "success": False,
                        },
                        {
                            "algorithm": "ModifiedNewton",
                            "iterations": 50,
                            "norm": 1.0e-2,
                            "code": -3,
                            "success": False,
                        },
                    ],
                },
            ],
        }
    }

    steps = convergence_steps(result)
    assert [row["step"] for row in steps] == [1, 2, 3]

    summary = convergence_summary(result)
    assert summary["steps"] == 3
    assert summary["converged"] == 1
    assert summary["recovered"] == 1
    assert summary["failed"] == 1
    assert summary["total_attempts"] == 5
    assert summary["max_iterations_used"] == 50
    assert summary["worst_norm"] == 1.0e-2
    assert summary["worst_step"] == 3
    assert summary["algorithms"] == [
        "ModifiedNewton",
        "Newton",
        "NewtonLineSearch",
    ]

    assert convergence_series(
        result,
        "iterations",
    ) == ([1.0, 2.0, 3.0], [4.0, 7.0, 50.0])
    assert convergence_series(
        result,
        "norm",
    ) == ([1.0, 2.0, 3.0], [1.0e-10, 5.0e-9, 1.0e-2])


def test_convergence_helpers_handle_empty_and_validate_quantity():
    assert convergence_steps({}) == []
    summary = convergence_summary({})
    assert summary["steps"] == 0
    assert summary["failed"] == 0
    assert convergence_series({}, "norm") == ([], [])

    try:
        convergence_series({}, "energy")
    except ValueError as exc:
        assert "Unsupported convergence series quantity" in str(exc)
    else:
        raise AssertionError("Expected bad convergence quantity to fail")


def test_convergence_summary_reports_adaptive_cutbacks_and_minimum_step():
    result = {
        "convergence": {
            "test": "NormDispIncr",
            "tolerance": 1.0e-8,
            "max_iterations": 50,
            "primary_algorithm": "Newton",
            "adaptive_step": True,
            "cutback_factor": 0.5,
            "minimum_factor": 0.125,
            "growth_factor": 1.5,
            "steps": [
                {
                    "step": 1,
                    "status": "recovered",
                    "algorithm": "Newton",
                    "iterations": 3,
                    "total_iterations": 61,
                    "norm": 1.0e-10,
                    "recovered": True,
                    "adaptive": True,
                    "cutbacks": 1,
                    "min_step_size_used": 0.005,
                    "attempts": [
                        {
                            "algorithm": "Newton",
                            "iterations": 50,
                            "norm": 1.0e-3,
                        },
                        {
                            "algorithm": "NewtonLineSearch",
                            "iterations": 8,
                            "norm": 1.0e-4,
                        },
                        {
                            "algorithm": "Newton",
                            "iterations": 3,
                            "norm": 1.0e-10,
                        },
                    ],
                },
                {
                    "step": 2,
                    "status": "converged",
                    "algorithm": "Newton",
                    "iterations": 2,
                    "norm": 1.0e-11,
                    "recovered": False,
                    "adaptive": True,
                    "cutbacks": 0,
                    "min_step_size_used": 0.0075,
                    "attempts": [
                        {
                            "algorithm": "Newton",
                            "iterations": 2,
                            "norm": 1.0e-11,
                        }
                    ],
                },
            ],
        }
    }

    summary = convergence_summary(result)

    assert summary["adaptive_step"] is True
    assert summary["adaptive_steps"] == 2
    assert summary["total_cutbacks"] == 1
    assert summary["minimum_step_size"] == 0.005
    assert summary["cutback_factor"] == 0.5
    assert summary["minimum_factor"] == 0.125
    assert summary["growth_factor"] == 1.5

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



def test_convergence_trace_uses_cumulative_iterations_and_adaptive_markers():
    result = {
        "convergence": {
            "tolerance": 1.0e-8,
            "steps": [
                {
                    "step": 1,
                    "status": "converged",
                    "time": 0.1,
                    "attempts": [
                        {
                            "algorithm": "Newton",
                            "iterations": 3,
                            "norm": 1.0e-9,
                            "norm_history": [1.0e-2, 1.0e-5, 1.0e-9],
                        }
                    ],
                },
                {
                    "step": 2,
                    "status": "recovered",
                    "time": 0.15,
                    "substeps": [
                        {
                            "accepted": False,
                            "time": 0.1,
                            "attempts": [
                                {
                                    "algorithm": "Newton",
                                    "iterations": 2,
                                    "norm": 1.0e-3,
                                    "norm_history": [1.0e-2, 1.0e-3],
                                }
                            ],
                        },
                        {
                            "accepted": True,
                            "time": 0.15,
                            "attempts": [
                                {
                                    "algorithm": "Newton",
                                    "iterations": 2,
                                    "norm": 1.0e-9,
                                    "norm_history": [1.0e-3, 1.0e-9],
                                }
                            ],
                        },
                    ],
                    "attempts": [],
                },
            ],
        }
    }

    trace = convergence_trace(result)

    assert trace["iteration"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert trace["norm"] == [
        1.0e-2,
        1.0e-5,
        1.0e-9,
        1.0e-2,
        1.0e-3,
        1.0e-3,
        1.0e-9,
    ]
    assert trace["criterion"] == 1.0e-8
    assert trace["cutbacks"] == [5.0]
    assert trace["converged"] == [3.0, 7.0]
    assert trace["coordinate_iteration"] == [0.0, 3.0, 7.0]
    assert trace["coordinate"] == [0.0, 0.1, 0.15]
    assert trace["total_iterations"] == 7


def test_convergence_trace_falls_back_to_final_norm_without_history():
    result = {
        "convergence": {
            "tolerance": 1.0e-6,
            "steps": [
                {
                    "step": 1,
                    "status": "converged",
                    "time": 1.0,
                    "attempts": [
                        {
                            "iterations": 4,
                            "norm": 2.0e-7,
                        }
                    ],
                }
            ],
        }
    }

    trace = convergence_trace(result)

    assert trace["iteration"] == [4.0]
    assert trace["norm"] == [2.0e-7]
    assert trace["converged"] == [4.0]
    assert trace["coordinate_iteration"] == [0.0, 4.0]
    assert trace["coordinate"] == [0.0, 1.0]



def _specimen_history_result():
    return {
        "specimen": {
            "kind": "test-column",
            "element_tag": 10,
            "base_node": 1,
            "top_node": 2,
            "ground_node": 3,
            "height": 3000.0,
            "lateral_direction": 1,
            "bending_rotation_dof": 5,
            "moment_component": "My",
            "moment_index": 2,
            "moment_sign": -1.0,
            "interface_type": "zeroLengthSection",
            "interface_name": "Bond_SP01 strain penetration",
        },
        "history": {
            "time": [1.0, 2.0],
            "nodes": {
                "1": {
                    "disp": [
                        [1.5, 0.0, 0.0, 0.0, 0.0001, 0.0],
                        [3.0, 0.0, 0.0, 0.0, 0.0002, 0.0],
                    ]
                },
                "2": {
                    "disp": [
                        [15.0, 0.0, 0.0, 0.0, 0.004, 0.0],
                        [30.0, 0.0, 0.0, 0.0, 0.008, 0.0],
                    ]
                },
                "3": {
                    "disp": [
                        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    ]
                },
            },
            "specimen": {
                "section_force": [
                    [100.0, 0.0, -10.0, 0.0],
                    [100.0, 0.0, -20.0, 0.0],
                ],
                "section_deformation": [
                    [0.0, 0.0, -0.001, 0.0],
                    [0.0, 0.0, -0.002, 0.0],
                ],
                "interface_force": [
                    [100.0, 0.0, -9.0, 0.0],
                    [100.0, 0.0, -18.0, 0.0],
                ],
                "interface_deformation": [
                    [0.0, 0.0, -0.0001, 0.0],
                    [0.0, 0.0, -0.0002, 0.0],
                ],
                "base_fibers": [
                    [
                        {
                            "label": "steel_max",
                            "material_tag": 2,
                            "material_type": "ReinforcingSteel",
                            "y": 0.0,
                            "z": 150.0,
                            "stress": 200.0,
                            "strain": 0.001,
                        }
                    ],
                    [
                        {
                            "label": "steel_max",
                            "material_tag": 2,
                            "material_type": "ReinforcingSteel",
                            "y": 0.0,
                            "z": 150.0,
                            "stress": 400.0,
                            "strain": 0.002,
                        }
                    ],
                ],
                "interface_fibers": [
                    [
                        {
                            "label": "bond_max",
                            "material_tag": 3,
                            "material_type": "Bond_SP01",
                            "y": 0.0,
                            "z": 150.0,
                            "stress": 180.0,
                            "slip": 0.5,
                        }
                    ],
                    [
                        {
                            "label": "bond_max",
                            "material_tag": 3,
                            "material_type": "Bond_SP01",
                            "y": 0.0,
                            "z": 150.0,
                            "stress": 350.0,
                            "slip": 1.0,
                        }
                    ],
                ],
            },
        },
    }


def test_test_column_moment_curvature_uses_local_to_global_sign():
    curvature, moment, component = column_moment_curvature_curve(
        _specimen_history_result()
    )

    assert component == "My"
    assert curvature == pytest.approx([0.0, 0.001, 0.002])
    assert moment == pytest.approx([0.0, 10.0, 20.0])


def test_test_column_rotation_decomposition_separates_interface_terms():
    rows = column_rotation_decomposition(_specimen_history_result())

    assert rows["time"] == [1.0, 2.0]
    assert rows["total"] == pytest.approx([0.005, 0.01])
    assert rows["interface_rotation"] == pytest.approx([0.0001, 0.0002])
    assert rows["interface_slip"] == pytest.approx([0.0005, 0.001])
    assert rows["column"] == pytest.approx([0.0044, 0.0088])


def test_test_column_fiber_history_catalog_distinguishes_strain_and_bond_slip():
    catalog = column_fiber_history_catalog(_specimen_history_result())
    keys = {row["key"] for row in catalog}

    assert "base_fibers:steel_max:stress" in keys
    assert "base_fibers:steel_max:strain" in keys
    assert "interface_fibers:bond_max:stress" in keys
    assert "interface_fibers:bond_max:slip" in keys

    slip = next(
        row
        for row in catalog
        if row["key"] == "interface_fibers:bond_max:slip"
    )
    assert slip["y"] == pytest.approx([0.5, 1.0])
    assert slip["latest"] == pytest.approx(1.0)


def test_test_column_response_summary_reports_peak_diagnostics():
    summary = column_response_summary(_specimen_history_result())

    assert summary["moment_component"] == "My"
    assert summary["max_abs_moment"] == pytest.approx(20.0)
    assert summary["max_abs_curvature"] == pytest.approx(0.002)
    assert summary["max_abs_total_drift"] == pytest.approx(0.01)
    assert summary["max_abs_interface_rotation"] == pytest.approx(0.0002)
    assert summary["max_abs_interface_slip_drift"] == pytest.approx(0.001)


def test_test_column_interface_moment_rotation_is_separate_from_member_response():
    rotation, moment, component = column_interface_moment_rotation_curve(
        _specimen_history_result()
    )

    assert component == "My"
    assert rotation == pytest.approx([0.0, 0.0001, 0.0002])
    assert moment == pytest.approx([0.0, 9.0, 18.0])


def test_test_column_research_metrics_capture_interface_share_and_bond_slip():
    metrics = column_specimen_research_metrics(
        _specimen_history_result()
    )

    assert metrics["moment_component"] == "My"
    assert metrics["peak_positive_moment"] == pytest.approx(20.0)
    assert metrics["peak_negative_moment"] is None
    assert metrics["peak_abs_curvature"] == pytest.approx(0.002)
    assert metrics["peak_abs_total_drift"] == pytest.approx(0.01)
    assert metrics["peak_abs_column_drift"] == pytest.approx(0.0088)
    assert metrics["peak_abs_interface_rotation"] == pytest.approx(0.0002)
    assert metrics["peak_abs_interface_slip_drift"] == pytest.approx(0.001)
    assert metrics["interface_share_at_peak_drift_percent"] == pytest.approx(12.0)
    assert metrics["peak_abs_steel_strain"] == pytest.approx(0.002)
    assert metrics["peak_abs_concrete_strain"] is None
    assert metrics["peak_abs_bond_slip"] == pytest.approx(1.0)
    assert metrics["interface_signed_work"] == pytest.approx(0.0018)
    assert metrics["interface_path_energy"] == pytest.approx(0.0018)



def _cyclic_specimen_research_result():
    displacement = [1.0, 2.0, 1.0, 0.0, -1.0, -2.0, -1.0, 0.0, 1.0, 2.0, 1.0]
    shear = [10.0, 20.0, 8.0, 0.0, -10.0, -18.0, -7.0, 0.0, 9.0, 16.0, 6.0]
    moments = [30.0, 60.0, 24.0, 0.0, -30.0, -54.0, -21.0, 0.0, 27.0, 48.0, 18.0]
    curvature = [0.001, 0.002, 0.001, 0.0, -0.001, -0.002, -0.001, 0.0, 0.001, 0.002, 0.001]
    interface_rotation = [
        0.0001, 0.0002, 0.0001, 0.0, -0.0001, -0.0002,
        -0.0001, 0.0, 0.0001, 0.0002, 0.0001,
    ]
    result = {
        "analysis": {
            "type": "Cyclic",
            "control_node": 2,
            "control_dof": 1,
        },
        "specimen": {
            "kind": "test-column",
            "element_tag": 10,
            "base_node": 1,
            "top_node": 2,
            "ground_node": 3,
            "height": 1000.0,
            "lateral_direction": 1,
            "bending_rotation_dof": 5,
            "moment_component": "My",
            "moment_index": 2,
            "moment_sign": -1.0,
            "interface_type": "zeroLengthSection",
            "interface_name": "Bond_SP01 strain penetration",
        },
        "history": {
            "time": [float(index + 1) for index in range(len(displacement))],
            "control_dof": 1,
            "displacement": [
                [value, 0.0, 0.0, 0.0, 0.0, 0.0]
                for value in displacement
            ],
            "base_shear": [-value for value in shear],
            "nodes": {
                "1": {
                    "disp": [
                        [0.0, 0.0, 0.0, 0.0, theta, 0.0]
                        for theta in interface_rotation
                    ]
                },
                "2": {
                    "disp": [
                        [value, 0.0, 0.0, 0.0, theta, 0.0]
                        for value, theta in zip(
                            displacement,
                            interface_rotation,
                        )
                    ]
                },
                "3": {
                    "disp": [
                        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        for _ in displacement
                    ]
                },
            },
            "specimen": {
                "section_force": [
                    [100.0, 0.0, -value, 0.0]
                    for value in moments
                ],
                "section_deformation": [
                    [0.0, 0.0, -value, 0.0]
                    for value in curvature
                ],
                "interface_force": [
                    [100.0, 0.0, -0.9 * value, 0.0]
                    for value in moments
                ],
                "interface_deformation": [
                    [0.0, 0.0, -value, 0.0]
                    for value in interface_rotation
                ],
                "base_fibers": [
                    [
                        {
                            "label": "steel_max",
                            "material_tag": 2,
                            "material_type": "ReinforcingSteel",
                            "y": 0.0,
                            "z": 150.0,
                            "stress": 200.0 * value,
                            "strain": 0.001 * value,
                        },
                        {
                            "label": "concrete_min",
                            "material_tag": 4,
                            "material_type": "Concrete02",
                            "y": 0.0,
                            "z": -150.0,
                            "stress": -15.0 * abs(value),
                            "strain": -0.0015 * abs(value),
                        },
                    ]
                    for value in displacement
                ],
                "interface_fibers": [
                    [
                        {
                            "label": "bond_max",
                            "material_tag": 3,
                            "material_type": "Bond_SP01",
                            "y": 0.0,
                            "z": 150.0,
                            "stress": 150.0 * value,
                            "slip": 0.1 * value,
                        }
                    ]
                    for value in displacement
                ],
            },
        },
    }
    return result


def test_column_cyclic_reversal_metrics_synchronize_global_section_and_fibers():
    rows = column_cyclic_reversal_metrics(
        _cyclic_specimen_research_result()
    )

    assert len(rows) == 3
    first_positive, negative, second_positive = rows

    assert first_positive["history_step"] == 1
    assert first_positive["displacement"] == pytest.approx(2.0)
    assert first_positive["base_shear"] == pytest.approx(20.0)
    assert first_positive["drift_angle"] == pytest.approx(0.002)
    assert first_positive["moment"] == pytest.approx(60.0)
    assert first_positive["curvature"] == pytest.approx(0.002)
    assert first_positive["steel_strain"] == pytest.approx(0.002)
    assert first_positive["concrete_strain"] == pytest.approx(-0.003)
    assert first_positive["bond_slip"] == pytest.approx(0.2)
    assert first_positive["interface_rotation"] == pytest.approx(0.0002)

    assert negative["history_step"] == 5
    assert negative["displacement"] == pytest.approx(-2.0)
    assert negative["moment"] == pytest.approx(-54.0)
    assert negative["steel_strain"] == pytest.approx(-0.002)

    assert second_positive["history_step"] == 9
    assert second_positive["strength_ratio"] == pytest.approx(0.8)
    assert second_positive["stiffness_ratio"] == pytest.approx(0.8)
    assert second_positive["closed_cycle_number"] == 1
    assert second_positive["closed_cycle_energy"] is not None
    assert second_positive["closed_cycle_energy"] > 0.0
    assert second_positive["interface_closed_cycle_energy"] is not None


def test_column_cyclic_cycle_metrics_returns_compact_closed_cycle_rows():
    cycles = column_cyclic_cycle_metrics(
        _cyclic_specimen_research_result()
    )

    assert len(cycles) == 1
    assert cycles[0]["cycle"] == 1
    assert cycles[0]["end_reversal"] == 3
    assert cycles[0]["amplitude"] == pytest.approx(2.0)
    assert cycles[0]["repeat_index"] == 2
    assert cycles[0]["strength_ratio"] == pytest.approx(0.8)
    assert cycles[0]["stiffness_ratio"] == pytest.approx(0.8)
    assert cycles[0]["energy"] > 0.0
    assert cycles[0]["interface_energy"] is not None



def test_parse_experimental_csv_supports_headers_and_semicolon_decimal_comma():
    dataset = parse_experimental_csv_text(
        "Displacement;Force;Note\n"
        "0,0;0,0;start\n"
        "1,5;12,0;peak\n"
        "-1,5;-10,0;peak\n"
    )

    assert dataset["headers"] == ["Displacement", "Force", "Note"]
    assert dataset["delimiter"] == ";"
    assert dataset["rows"][1][0] == pytest.approx(1.5)
    assert dataset["rows"][1][1] == pytest.approx(12.0)
    assert dataset["rows"][1][2] is None

    x, y = experimental_csv_series(
        dataset,
        0,
        1,
        x_scale=2.0,
        y_scale=-1.0,
    )
    assert x == pytest.approx([0.0, 3.0, -3.0])
    assert y == pytest.approx([0.0, -12.0, 10.0])


def test_parse_experimental_csv_supports_headerless_numeric_files():
    dataset = parse_experimental_csv_text(
        "0,0\n"
        "1,10\n"
        "-1,-9\n"
    )

    assert dataset["headers"] == ["Column 1", "Column 2"]
    x, y = experimental_csv_series(dataset, 0, 1)
    assert x == pytest.approx([0.0, 1.0, -1.0])
    assert y == pytest.approx([0.0, 10.0, -9.0])


def test_cyclic_backbone_uses_strongest_repeated_reversal_at_each_amplitude():
    x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0, -2.0, 0.0]
    y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0, -15.0, 0.0]

    backbone_x, backbone_y = cyclic_backbone_curve(x, y)

    assert backbone_x == pytest.approx([-2.0, 0.0, 2.0])
    assert backbone_y == pytest.approx([-18.0, 0.0, 20.0])


def test_cyclic_reversal_comparison_matches_sign_amplitude_and_repeat_index():
    sim_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    sim_y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0]
    exp_x = [0.0, 2.02, 0.0, -1.98, 0.0, 2.01, 0.0]
    exp_y = [0.0, 19.0, 0.0, -17.0, 0.0, 15.0, 0.0]

    rows = cyclic_reversal_comparison(sim_x, sim_y, exp_x, exp_y)

    assert len(rows) == 3
    assert rows[0]["simulation_reversal"] == 1
    assert rows[0]["experiment_reversal"] == 1
    assert rows[0]["repeat_index"] == 1
    assert rows[0]["force_error_percent"] == pytest.approx(
        (20.0 - 19.0) / 19.0 * 100.0
    )
    assert rows[2]["repeat_index"] == 2
    assert rows[2]["simulation_strength_ratio"] == pytest.approx(0.8)
    assert rows[2]["experiment_strength_ratio"] == pytest.approx(15.0 / 19.0)


def test_cyclic_curve_comparison_reports_peaks_energy_and_reversal_nrmse():
    sim_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    sim_y = [0.0, 20.0, 0.0, -18.0, 0.0, 16.0, 0.0]
    exp_x = [0.0, 2.0, 0.0, -2.0, 0.0, 2.0, 0.0]
    exp_y = [0.0, 19.0, 0.0, -17.0, 0.0, 15.0, 0.0]

    comparison = cyclic_curve_comparison(sim_x, sim_y, exp_x, exp_y)

    assert comparison["matched_reversal_count"] == 3
    assert comparison["simulation_reversal_count"] == 3
    assert comparison["experiment_reversal_count"] == 3
    assert comparison["reversal_force_nrmse_percent"] is not None

    metrics = {
        row["key"]: row
        for row in comparison["metrics"]
    }
    assert metrics["peak_positive_force"]["simulation"] == pytest.approx(20.0)
    assert metrics["peak_positive_force"]["experiment"] == pytest.approx(19.0)
    assert metrics["peak_abs_force"]["difference_percent"] == pytest.approx(
        (20.0 - 19.0) / 19.0 * 100.0
    )
    assert metrics["closed_cycle_energy_sum"]["simulation"] >= 0.0


def test_enrichment_builds_axial_force_diagram_for_truss():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 3.0, 4.0, 0.0)
    model.add_element(
        9,
        1,
        2,
        element_type="truss",
        group="truss",
        truss_area=0.002,
        truss_material_tag=1,
    )
    result = {
        "analysis": {"type": "Static"},
        "final": {
            "element_axial_forces": {"9": 125.0},
            "element_local_forces": {},
            "element_section_forces": {},
            "load_factors": {},
        },
    }

    enriched = enrich_member_force_results(
        result,
        model,
        {},
        {},
        {1: MaterialData(1, "Steel", "Elastic", {"E": 200.0e9})},
        {},
        {"length": "m", "force": "kN", "time": "s"},
    )

    diagram = enriched["final"]["member_force_diagrams"]["9"]["N"]
    assert diagram["source"] == "truss axialForce"
    assert diagram["x"] == [0.0, 5.0]
    assert diagram["values"] == [125.0, 125.0]
