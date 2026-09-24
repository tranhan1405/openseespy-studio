from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.result_catalog import result_choices_for_analysis
from openseespy_studio.project import AnalysisSettingsData
from openseespy_studio.ui.results_panel import ResultsPanel, TimeHistoryPlot
from openseespy_studio.ui.viewport import ModelViewport


_APP = QApplication.instance() or QApplication([])


def _transient_result(frame_count: int = 101) -> dict:
    times = [0.01 * index for index in range(frame_count)]
    rows = [[float(index), 0.0, 0.0] for index in range(frame_count)]
    return {
        "analysis": {"type": "Transient"},
        "history": {
            "time": times,
            "nodes": {
                "1": {"disp": rows},
            },
        },
        "final": {
            "node_displacements": {
                "1": rows[-1],
            },
            "node_reactions": {},
        },
    }


def test_animation_result_remains_available_for_modal_and_transient():
    modal = AnalysisSettingsData(1, "Modes", "Modal")
    transient = AnalysisSettingsData(2, "EQ", "Transient", steps=10, dt=0.01)

    modal_types = {
        choice.result_type for choice in result_choices_for_analysis(modal)
    }
    transient_types = {
        choice.result_type for choice in result_choices_for_analysis(transient)
    }

    assert "Motion" in modal_types
    assert "Motion" in transient_types


def test_animation_is_inline_in_results_viewer_not_a_separate_tab():
    source = inspect.getsource(ResultsPanel)

    assert 'QPushButton("▶ Animate")' in source
    assert 'QPushButton("▶ Animate Mode")' in source
    assert 'root.addWidget(self.motion_page)' in source
    assert 'self.tabs.addTab(page, "Animation")' not in source
    assert 'self._select_tab("Animation")' not in source
    assert 'QLabel("Frame Rate:")' in source
    assert 'setSuffix(" fps")' in source
    assert 'QLabel("Frame:")' in source
    assert 'QPushButton("■ Stop")' in source


def test_animation_keeps_every_result_frame_and_fps_controls_playback_only():
    panel = ResultsPanel()
    try:
        panel.set_result(_transient_result(1000), cache_key=("job", 1))
        panel.show_solution_result("NodalDisplacement", {"component": "UX"})

        assert panel.motion_page.isHidden() is False
        assert panel._motion_source_frame_count == 1000
        assert panel._motion_display_frame_count == 1000
        assert panel.motion_slider.maximum() == 999
        assert panel.motion_frame_spin.maximum() == 1000
        assert panel._motion_source_index(0) == 0
        assert panel._motion_source_index(999) == 999

        panel.motion_frame_rate.setValue(20)
        assert panel._motion_timer_interval_ms() == 50
        assert panel._motion_display_frame_count == 1000
    finally:
        panel.close()
        panel.deleteLater()
        _APP.processEvents()


def test_pause_updates_displacement_table_to_current_result_frame():
    panel = ResultsPanel()
    try:
        panel.set_result(_transient_result(101), cache_key=("job", 2))
        panel.show_solution_result("NodalDisplacement", {"component": "UX"})
        panel._set_motion_index(30)
        source_index = panel._motion_source_index(30)

        panel._sync_paused_motion_values()

        assert panel.node_table.item(0, 1).text() == f"{float(source_index):.6g}"
        assert "animation frame 31/101" in panel.node_frame_status.text()
        assert f"result frame {source_index + 1}/101" in panel.node_frame_status.text()
    finally:
        panel.close()
        panel.deleteLater()
        _APP.processEvents()


def test_time_history_marker_draws_vertical_tracker_and_point():
    source = inspect.getsource(TimeHistoryPlot.paintEvent)

    assert "painter.drawLine(" in source
    assert "QPointF(marker.x(), top)" in source
    assert "QPointF(marker.x(), bottom)" in source
    assert "painter.drawEllipse(marker, 5.0, 5.0)" in source


def test_motion_frame_keeps_displacement_contour_scale_visible():
    source = inspect.getsource(ModelViewport.show_motion_frame)

    assert 'scalars="magnitude"' in source
    assert 'cmap="turbo"' in source
    assert 'clim=(0.0, scalar_upper)' in source
    assert 'scalar_bar_args={"title": scalar_title}' in source
    assert 'point_data["magnitude"]' in source
    assert 'show_scalar_bar=not bool(element_points)' in source


def test_animation_transport_shows_time_or_analysis_coordinate():
    build_source = inspect.getsource(ResultsPanel._build_motion_tab)
    coordinate_source = inspect.getsource(ResultsPanel._motion_coordinate_text)
    emit_source = inspect.getsource(ResultsPanel._emit_current_motion_frame)

    assert 'self.motion_coordinate_label = QLabel("Time: -")' in build_source
    assert 'return f"Time: {value:.6g} {unit}"' in coordinate_source
    assert 'return f"Phase: {value:.1f}°"' in coordinate_source
    assert 'return f"Coordinate: {value:.6g}"' in coordinate_source
    assert 'return f"Value: {100.0 * value:.1f}%"' in coordinate_source
    assert 'self.motion_coordinate_label.setText(' in emit_source


def test_force_displacement_curve_tracks_animation_frame():
    build_source = inspect.getsource(ResultsPanel._build_force_displacement_tab)
    show_source = inspect.getsource(ResultsPanel.show_solution_result)
    sync_source = inspect.getsource(ResultsPanel._sync_motion_markers)

    assert 'self.force_disp_animate_button = QPushButton("▶ Animate")' in build_source
    assert '_open_animation(source="force_displacement")' in build_source
    assert '"ForceDisplacement"' in show_source
    assert 'self.motion_page.setVisible(' in show_source
    assert 'self.force_disp_plot.set_marker(index)' in sync_source
