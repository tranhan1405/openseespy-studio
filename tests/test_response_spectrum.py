import math

from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    LoadPatternData,
    TimeSeriesData,
)
from openseespy_studio.response_spectrum import (
    build_period_grid,
    compute_response_spectrum,
)


def test_piecewise_period_grid_matches_rotd_script_regions():
    periods = build_period_grid(0.1, 1.0, 0.2, 2.0, 0.5, 5.0)

    assert periods[:3] == [0.1, 0.2, 0.3]
    assert 1.0 in periods
    assert 1.1 not in periods
    assert 1.2 in periods
    assert 2.0 in periods
    assert 2.5 in periods
    assert periods[-1] == 5.0


def test_single_component_spectrum_returns_sa_over_g():
    dt = 0.01
    values = [
        9.80665 * 0.1 * math.sin(2.0 * math.pi * index * dt)
        for index in range(400)
    ]
    result = compute_response_spectrum(
        [{"dt": dt, "values": values, "direction": 1}],
        [0.5, 1.0, 2.0],
        0.05,
        9.80665,
        include_component_y=False,
        include_rotd50=False,
        include_rotd100=False,
    )

    assert result["period_s"] == [0.5, 1.0, 2.0]
    assert len(result["component_x_sa_g"]) == 3
    assert all(value >= 0.0 for value in result["component_x_sa_g"])
    assert "rotd50_sa_g" not in result


def test_bidirectional_spectrum_produces_rotd50_and_rotd100():
    dt = 0.01
    x = [
        9.80665 * 0.08 * math.sin(2.0 * math.pi * index * dt)
        for index in range(300)
    ]
    y = [
        9.80665 * 0.05 * math.cos(2.0 * math.pi * index * dt)
        for index in range(300)
    ]
    result = compute_response_spectrum(
        [
            {"dt": dt, "values": x, "direction": 1},
            {"dt": dt, "values": y, "direction": 2},
        ],
        [0.5, 1.0],
        0.05,
        9.80665,
    )

    assert len(result["rotd50_sa_g"]) == 2
    assert len(result["rotd100_sa_g"]) == 2
    assert all(
        maximum >= median
        for median, maximum in zip(
            result["rotd50_sa_g"],
            result["rotd100_sa_g"],
        )
    )


def test_response_spectrum_settings_round_trip():
    analysis = AnalysisSettingsData(
        9,
        "RotD spectrum",
        "Response Spectrum",
        deferred_pattern_tags=[21, 22],
        response_spectrum_mode="Bidirectional / RotD",
        response_spectrum_damping_ratio=0.05,
        response_spectrum_rotd50=True,
        response_spectrum_rotd100=True,
    )

    restored = AnalysisSettingsData.from_dict(analysis.to_dict())

    assert restored.analysis_type == "Response Spectrum"
    assert restored.integrator == "None"
    assert restored.deferred_pattern_tags == [21, 22]
    assert restored.response_spectrum_mode == "Bidirectional / RotD"
    assert restored.response_spectrum_rotd50 is True
    assert restored.response_spectrum_rotd100 is True


def test_generator_embeds_response_spectrum_worker():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)

    series = {
        1: TimeSeriesData(
            1,
            "GM X",
            "Path",
            dt=0.02,
            values=[0.0, 0.1, -0.1, 0.0],
            factor=9.80665,
        ),
        2: TimeSeriesData(
            2,
            "GM Y",
            "Path",
            dt=0.02,
            values=[0.0, 0.05, -0.05, 0.0],
            factor=9.80665,
        ),
    }
    patterns = {
        21: LoadPatternData(21, "X", "UniformExcitation", 1, direction=1),
        22: LoadPatternData(22, "Y", "UniformExcitation", 2, direction=2),
    }
    analysis = AnalysisSettingsData(
        9,
        "RotD spectrum",
        "Response Spectrum",
        deferred_pattern_tags=[21, 22],
        response_spectrum_mode="Bidirectional / RotD",
    )

    script = to_openseespy(
        model,
        time_series=series,
        load_patterns=patterns,
        analyses={9: analysis},
        active_analysis_tag=9,
    )

    assert "compute_response_spectrum" in script
    assert "'response_spectrum'" in script
    assert "'rotd50_sa_g'" in script
    assert "Linear Newmark SDOF" in script
    assert "ops.analysis('Transient')" not in script
    compile(script, "<response-spectrum>", "exec")
