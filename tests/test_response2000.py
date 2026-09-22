from __future__ import annotations

import pytest

from openseespy_studio.response2000 import (
    parse_response2000_chart_text,
    response2000_curve_comparison,
    response2000_series,
    suggest_response2000_columns,
    suggest_response2000_units,
)


def test_parse_response2000_whitespace_chart_data():
    text = """
Moment-Y - Curvature
Curvature-Y (rad/km)    Moment-Y (kN-m)
0.0    0.0
1.5    120.0
3.0    210.0
5.0    245.0
"""

    dataset = parse_response2000_chart_text(text)

    assert dataset["format"] == "whitespace"
    assert len(dataset["rows"]) == 4
    assert dataset["rows"][2][:2] == pytest.approx([3.0, 210.0])
    assert len(dataset["headers"]) >= 2


def test_response2000_header_detection_recognizes_common_axis_units():
    headers = ["Curvature-Y (rad/km)", "Moment-Y (kN-m)"]

    x_index, y_index = suggest_response2000_columns(headers)
    x_unit, y_unit = suggest_response2000_units(
        headers[x_index],
        headers[y_index],
    )

    assert (x_index, y_index) == (0, 1)
    assert x_unit == "rad_per_km"
    assert y_unit == "kn_m"


def test_response2000_unit_conversion_to_mm_n_project():
    dataset = {
        "headers": ["Curvature-Y (rad/km)", "Moment-Y (kN-m)"],
        "rows": [
            [0.0, 0.0],
            [2.0, 300.0],
            [4.0, 500.0],
        ],
    }

    curvature, moment = response2000_series(
        dataset,
        0,
        1,
        curvature_unit="rad_per_km",
        moment_unit="kn_m",
        units={"length": "mm", "force": "N", "time": "s"},
    )

    assert curvature == pytest.approx([0.0, 2.0e-6, 4.0e-6])
    assert moment == pytest.approx([0.0, 300.0e6, 500.0e6])


def test_response2000_comparison_is_zero_for_matching_curves():
    curvature = [0.0, 0.001, 0.002, 0.004]
    moment = [0.0, 100.0, 180.0, 220.0]

    comparison = response2000_curve_comparison(
        curvature,
        moment,
        curvature,
        moment,
    )

    assert comparison["moment_nrmse_percent"] == pytest.approx(0.0)
    assert comparison["overlap_point_count"] == 4
    for metric in comparison["metrics"]:
        assert metric["difference_percent"] == pytest.approx(0.0)


def test_response2000_comparison_reports_peak_difference():
    simulation_x = [0.0, 0.001, 0.002, 0.004]
    simulation_y = [0.0, 90.0, 162.0, 198.0]
    response_x = [0.0, 0.001, 0.002, 0.004]
    response_y = [0.0, 100.0, 180.0, 220.0]

    comparison = response2000_curve_comparison(
        simulation_x,
        simulation_y,
        response_x,
        response_y,
    )

    peak = next(
        metric
        for metric in comparison["metrics"]
        if metric["key"] == "peak_moment"
    )
    assert peak["difference_percent"] == pytest.approx(-10.0)
    assert comparison["moment_nrmse_percent"] == pytest.approx(10.0)
