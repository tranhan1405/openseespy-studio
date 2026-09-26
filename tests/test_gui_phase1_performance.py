import inspect

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport


def test_selection_updates_are_coalesced_and_skip_noop_renders():
    source = inspect.getsource(ModelViewport.set_selection)

    assert "next_nodes == self._selected_nodes" in source
    assert "next_elements == self._selected_elements" in source
    assert "_update_highlight_overlays(render=False)" in source
    assert "self.request_render()" in source
    assert "plotter.render()" not in source


def test_selection_filter_uses_the_same_lightweight_render_path():
    source = inspect.getsource(ModelViewport.set_selection_filter)

    assert "normalized == self._selection_filter" in source
    assert "_update_highlight_overlays(render=False)" in source
    assert "self.request_render()" in source


def test_visible_scene_rebuild_does_not_render_twice():
    source = inspect.getsource(ModelViewport._rebuild_visible_scene)

    assert "_render_model(reset_camera=False)" in source
    assert "plotter.render()" not in source
    assert "camera_position =" not in source


def test_viewport_has_single_shot_render_scheduler():
    init_source = inspect.getsource(ModelViewport.__init__)
    request_source = inspect.getsource(ModelViewport.request_render)
    flush_source = inspect.getsource(ModelViewport._flush_scheduled_render)

    assert "self._render_timer = QTimer(self)" in init_source
    assert "self._render_timer.setSingleShot(True)" in init_source
    assert "self._render_timer.setInterval(0)" in init_source
    assert "if not self._render_timer.isActive()" in request_source
    assert "self._render_timer.start()" in request_source
    assert "self.plotter.render()" in flush_source


def test_reusable_property_edits_do_not_force_full_viewport_redraw():
    source = inspect.getsource(MainWindow._apply_direct_property_edit)

    assert 'kind in {"material", "section", "transformation"}' in source
    assert "self._sync_viewport_display_data(refresh=True)" in source
    assert "sync_viewport_display=False" in source
    assert "refresh_tree=property_id in" in source
    assert "else:" in source
    assert "self._refresh_all(message)" in source


def test_metadata_refresh_can_skip_expensive_tree_rebuild():
    source = inspect.getsource(MainWindow._refresh_project_metadata)

    assert "refresh_tree: bool = True" in source
    assert "if refresh_tree:" in source
    assert "self._refresh_tree()" in source
