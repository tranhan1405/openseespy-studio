from __future__ import annotations

import inspect

from openseespy_studio.ui.main_window import MainWindow


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
