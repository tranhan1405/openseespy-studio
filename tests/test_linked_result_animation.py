from __future__ import annotations

import inspect

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.results_panel import ResultsPanel
from openseespy_studio.ui.viewport import ModelViewport


def test_linked_frame_handler_animates_nodal_contours_without_duplicate_motion():
    handler = inspect.getsource(MainWindow._show_linked_result_frame)
    motion = inspect.getsource(MainWindow._show_motion_frame_result)
    render = inspect.getsource(MainWindow._render_result_data)

    assert "result_frame_payload" in handler
    assert "show_node_contour" in handler
    assert "NodalDisplacement" in handler
    assert "NodalReaction" in handler
    assert "_active_linked_result_type" in motion
    assert "_show_linked_result_frame" in render


def test_global_animation_contour_range_is_prepared_from_history():
    source = inspect.getsource(
        MainWindow._prepare_contour_animation_options
    )
    assert 'contour_range_mode' in source
    assert '"global"' in source
    assert "nodal_history_contour_range" in source


def test_fast_contour_update_precedes_range_resolution():
    source = inspect.getsource(ModelViewport.show_node_contour)

    assert source.index("animation_state =") < source.index(
        "resolve_contour_range"
    )
    assert '"line_node_tags"' in source
    assert '"node_point_tags"' in source
    assert "if display.deformed_geometry" in source


def test_result_speed_caps_redraw_and_advances_frames():
    build = inspect.getsource(ResultsPanel._build_frame_bar)
    timer = inspect.getsource(ResultsPanel._update_motion_timer)
    advance = inspect.getsource(ResultsPanel._advance_motion)

    assert '"0.25×"' in build
    assert '"16×"' in build
    assert "setInterval(40)" in timer
    assert "_motion_frame_accumulator" in advance
    assert "_motion_frames_per_tick" in advance


def test_animation_frame_sampling_retains_first_and_last_frames():
    panel_source = inspect.getsource(ResultsPanel._rebuild_playback_frame_indices)
    advance_source = inspect.getsource(ResultsPanel._advance_motion)

    assert "_playback_frame_limit" in panel_source
    assert "count - 1" in panel_source
    assert "dict.fromkeys" in panel_source
    assert "_playback_frame_indices" in advance_source
    assert "_playback_sample_cursor" in advance_source


def test_results_ribbon_exposes_frame_count_and_extrema_toggles():
    build = inspect.getsource(MainWindow._build_actions_and_ribbon)
    render = inspect.getsource(MainWindow._render_result_data)
    toggle = inspect.getsource(MainWindow._set_result_extrema_visibility)
    frame_choice = inspect.getsource(
        MainWindow._apply_result_animation_frame_choice
    )
    custom_frame = inspect.getsource(
        MainWindow._apply_result_animation_custom_frame_limit
    )
    frame_limit = inspect.getsource(ResultsPanel.set_playback_frame_limit)

    assert "result_frame_count_ribbon = QComboBox()" in build
    assert '("5 Frames", 5)' in build
    assert '("20 Frames", 20)' in build
    assert '("100 Frames", 100)' in build
    assert '("User Defined...", "user")' in build
    assert "findData(20)" in build
    assert "result_frame_custom_ribbon = QSpinBox()" in build
    assert "setRange(5, 100)" in build
    assert "setVisible(False)" in build
    assert '"result_show_min"' in build
    assert '"result_show_max"' in build
    assert 'str(raw) == "user"' in frame_choice
    assert 'currentData()) != "user"' in custom_frame
    assert "max(5, min(100" in frame_limit
    assert "_sync_result_contour_ribbon_controls" in render
    assert "is_motion_playing" in toggle


def test_transient_animation_uses_physical_time_clock():
    advance = inspect.getsource(ResultsPanel._advance_motion)
    times = inspect.getsource(ResultsPanel._transient_time_values)
    sampling = inspect.getsource(ResultsPanel._rebuild_playback_frame_indices)

    assert "time.monotonic()" in advance
    assert "_motion_playback_time" in advance
    assert "elapsed * max(0.01, self._motion_speed_value())" in advance
    assert "history.get(\"time\"" in times
    assert "values[index] <= values[index - 1]" in times
    assert "uniformly in physical time" in sampling
    assert "target_time" in sampling
