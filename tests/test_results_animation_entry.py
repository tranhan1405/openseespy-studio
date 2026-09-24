import inspect

from openseespy_studio.result_catalog import result_choices_for_analysis
from openseespy_studio.project import AnalysisSettingsData
from openseespy_studio.ui.results_panel import ResultsPanel


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


def test_animation_is_exposed_from_result_tabs_not_only_hidden_motion_route():
    source = inspect.getsource(ResultsPanel)

    assert 'QPushButton("▶ Animate")' in source
    assert 'QPushButton("▶ Animate Mode")' in source
    assert 'self.tabs.addTab(page, "Animation")' in source
    assert 'self._select_tab("Animation")' in source
    assert '_open_animation(source="deformation")' in source
    assert '_open_animation(source="node")' in source
    assert '_open_animation(source="mode")' in source
