import inspect

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.results_panel import ResultsPanel
from openseespy_studio.ui.viewport import ModelViewport


def test_solution_tree_groups_time_history_probes():
    source = inspect.getsource(MainWindow._refresh_tree)

    assert '"solution_probes_root"' in source
    assert 'f"Probes ({len(probes)})"' in source
    assert 'result.result_type == "TimeHistory"' in source
    assert 'result.settings.get("probe", False)' in source


def test_node_context_exposes_probe_workflow():
    source = inspect.getsource(MainWindow._show_tree_context_menu)

    assert 'probe_menu = menu.addMenu("Probe")' in source
    assert '"Displacement"' in source
    assert '"Velocity"' in source
    assert '"Acceleration"' in source
    assert '"Reaction"' in source
    assert '"Add Node Probe..."' in source
    assert 'if kind == "solution_probes_root":' in source


def test_node_probe_uses_time_history_backend():
    source = inspect.getsource(MainWindow._create_node_probe)

    assert 'result_type="TimeHistory"' in source
    assert '"probe": True' in source
    assert 'self.viewport.show_node_probe' in source
    assert 'self._evaluate_solution_result' in source


def test_viewport_has_dedicated_probe_marker():
    show_source = inspect.getsource(ModelViewport.show_node_probe)
    clear_source = inspect.getsource(ModelViewport.clear_node_probe_overlay)

    assert '"node-probe-point"' in show_source
    assert '"node-probe-label"' in show_source
    assert '"node-probe-point"' in clear_source


def test_probe_does_not_replace_animation_contour_or_scalar_bar():
    probe_source = inspect.getsource(ModelViewport.show_node_probe)
    motion_source = inspect.getsource(ModelViewport.show_motion_frame)
    clear_source = inspect.getsource(ModelViewport.clear_result_overlay)

    assert 'show_scalar_bar=False' in probe_source
    assert 'preserve_probe=True' in motion_source
    assert 'position=displaced(self._node_probe_tag)' in motion_source
    assert 'scalar_bar_args={"title": scalar_title}' in motion_source
    assert 'preserve_probe: bool = False' in clear_source
    assert 'if not preserve_probe:' in clear_source


def test_node_probe_time_history_exposes_shared_animation_transport():
    build_source = inspect.getsource(ResultsPanel._build_history_tab)
    show_source = inspect.getsource(ResultsPanel.show_solution_result)

    assert 'QPushButton("▶ Animate")' in build_source
    assert '_open_animation(source="history")' in build_source
    assert 'self.history_animate_button.setVisible(False)' in build_source
    assert 'kind == "TimeHistory"' in show_source
    assert 'options.get("probe", False)' in show_source
    assert 'self.history_animate_button.setVisible(is_probe)' in show_source
    assert 'self.motion_page.setVisible(' in show_source


def test_animation_shows_frame_local_min_max_without_changing_scalar_range():
    extrema_source = inspect.getsource(ModelViewport._update_motion_extrema)
    motion_source = inspect.getsource(ModelViewport.show_motion_frame)
    clear_source = inspect.getsource(ModelViewport.clear_result_overlay)

    assert '"MAX {max_value:.4g}' in extrema_source
    assert '"MIN {min_value:.4g}' in extrema_source
    assert 'text_color="#c62828"' in extrema_source
    assert 'text_color="#1565c0"' in extrema_source
    assert 'show_scalar_bar=False' in extrema_source
    assert 'self._update_motion_extrema(' in motion_source
    assert 'clim=(0.0, scalar_upper)' in motion_source
    assert '"motion-max-label"' in clear_source
    assert '"motion-min-label"' in clear_source
