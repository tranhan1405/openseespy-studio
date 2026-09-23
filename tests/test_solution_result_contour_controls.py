from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.project import SolutionResultData
from openseespy_studio.ui.main_window import MainWindow, PropertiesPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_contour_result_details_restore_and_persist_display_state(qapp):
    panel = PropertiesPanel()
    result = SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="UX",
        result_type="NodalDisplacement",
        settings={
            "component": "UX",
            "contour_range_mode": "user",
            "contour_min": -0.02,
            "contour_max": 0.03,
            "contour_symmetric": False,
            "contour_bands": 15,
            "contour_palette": "diverging",
            "contour_show_min": True,
            "contour_show_max": False,
            "contour_deformed_geometry": True,
            "contour_deformation_scale": 8.0,
        },
    )
    try:
        panel.set_solution_result(result, analysis_name="EQ-X")
        assert panel.result_contour_range.currentData() == "user"
        assert panel.result_contour_min.value() == pytest.approx(-0.02)
        assert panel.result_contour_max.value() == pytest.approx(0.03)
        assert panel.result_contour_bands.value() == 15
        assert panel.result_contour_palette.currentData() == "diverging"
        assert panel.result_contour_show_min.isChecked()
        assert not panel.result_contour_show_max.isChecked()
        assert panel.result_contour_deformed.isChecked()
        assert panel.result_contour_deformation_scale.value() == pytest.approx(8.0)

        settings = panel._solution_payload()["settings"]
        assert settings["contour_range_mode"] == "user"
        assert settings["contour_bands"] == 15
        assert settings["contour_deformed_geometry"] is True
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_magnitude_contour_disables_symmetric_range(qapp):
    panel = PropertiesPanel()
    result = SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="Total Displacement",
        result_type="NodalDisplacement",
        settings={"component": "|U|", "contour_symmetric": True},
    )
    try:
        panel.set_solution_result(result, analysis_name="Static")
        assert not panel.result_contour_symmetric.isEnabled()
        assert not panel.result_contour_symmetric.isChecked()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_result_renderer_routes_contour_options_to_viewport():
    source = inspect.getsource(MainWindow._render_result_data)
    assert source.count("contour_options=options") >= 3
    assert "show_shell_force_contour" in source
    assert "show_shell_deformation_contour" in source
