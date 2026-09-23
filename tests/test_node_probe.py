import inspect

from openseespy_studio.ui.main_window import MainWindow
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
