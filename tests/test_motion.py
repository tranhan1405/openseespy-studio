import math

from openseespy_studio.motion import (
    available_modal_modes,
    motion_frame,
    motion_info,
)


def modal_result():
    return {
        "analysis": {"type": "Modal"},
        "modes": {
            "1": {
                "eigenvalue": 4.0,
                "vectors": {
                    "1": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "2": [1.0, 0.0, 0.5, 0.0, 0.0, 0.0],
                },
            },
            "2": {
                "eigenvalue": 9.0,
                "vectors": {
                    "1": [0.0, 0.0, 0.0],
                    "2": [0.0, 2.0, 0.0],
                },
            },
        },
    }


def transient_result():
    return {
        "analysis": {"type": "Transient"},
        "history": {
            "time": [0.01, 0.02, 0.03],
            "nodes": {
                "1": {
                    "disp": [
                        [0.0, 0.0, 0.0],
                        [0.1, 0.0, 0.0],
                        [0.2, 0.0, 0.0],
                    ]
                },
                "2": {
                    "disp": [
                        [0.0, 0.0, 0.0],
                        [0.0, -0.3, 0.0],
                        [0.0, -0.4, 0.0],
                    ]
                },
            },
        },
    }


def test_available_modal_modes_sorted():
    assert available_modal_modes(modal_result()) == [1, 2]


def test_modal_motion_uses_sinusoidal_mode_amplitude():
    result = modal_result()
    info = motion_info(result, mode=1, modal_frames=8)

    assert info.kind == "Modal"
    assert info.frame_count == 8
    assert info.mode == 1
    assert math.isclose(
        info.reference_magnitude,
        math.sqrt(1.0 + 0.25),
    )

    quarter = motion_frame(
        result,
        2,
        mode=1,
        modal_frames=8,
        info=info,
    )
    assert math.isclose(quarter.vectors["2"][0], 1.0)
    assert math.isclose(quarter.vectors["2"][2], 0.5)
    assert "phase 90.0" in quarter.label

    three_quarter = motion_frame(
        result,
        6,
        mode=1,
        modal_frames=8,
        info=info,
    )
    assert math.isclose(three_quarter.vectors["2"][0], -1.0)
    assert math.isclose(three_quarter.vectors["2"][2], -0.5)


def test_transient_motion_reads_node_displacement_history():
    result = transient_result()
    info = motion_info(result)

    assert info.kind == "Transient"
    assert info.frame_count == 3
    assert math.isclose(info.transient_dt, 0.01)
    assert math.isclose(info.reference_magnitude, 0.4)

    frame = motion_frame(result, 1, info=info)
    assert frame.vectors["1"] == [0.1, 0.0, 0.0]
    assert frame.vectors["2"] == [0.0, -0.3, 0.0]
    assert math.isclose(frame.coordinate, 0.02)
    assert "t = 0.02 s" in frame.label


def test_static_history_motion_uses_analysis_coordinate():
    result = transient_result()
    result["analysis"]["type"] = "Static"
    info = motion_info(result)
    frame = motion_frame(result, 2, info=info)

    assert info.kind == "Static"
    assert info.transient_dt is None
    assert frame.coordinate == 0.03
    assert "coordinate = 0.03" in frame.label


def test_final_only_result_falls_back_to_interpolation():
    result = {
        "analysis": {"type": "Static"},
        "final": {
            "node_displacements": {
                "1": [0.0, 0.0, 0.0],
                "2": [1.0, 2.0, 0.0],
            }
        },
    }
    info = motion_info(result, fallback_frames=5)
    assert info.frame_count == 5

    start = motion_frame(result, 0, fallback_frames=5, info=info)
    final = motion_frame(result, 4, fallback_frames=5, info=info)
    assert start.vectors["2"] == [0.0, 0.0, 0.0]
    assert final.vectors["2"] == [1.0, 2.0, 0.0]
    assert "100.0%" in final.label


def test_motion_index_is_clamped():
    result = transient_result()
    info = motion_info(result)
    frame = motion_frame(result, 999, info=info)
    assert frame.index == 2
    assert frame.vectors["1"] == [0.2, 0.0, 0.0]
