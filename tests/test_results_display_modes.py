from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.results_panel import ResultsPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_deformation_display_defaults_to_deformed_only(qapp):
    panel = ResultsPanel()
    try:
        assert panel.deformation_display.currentData() == "deformed_only"
        assert panel.mode_display.currentData() == "deformed_only"
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_deformation_signal_includes_display_mode(qapp):
    panel = ResultsPanel()
    captured: list[tuple[float, str]] = []
    panel.deformation_requested.connect(
        lambda scale, mode: captured.append((float(scale), str(mode)))
    )
    try:
        panel.deformation_scale.setValue(12.5)
        panel.deformation_display.setCurrentIndex(
            panel.deformation_display.findData("both")
        )
        panel.deformation_show_button.click()
        qapp.processEvents()

        assert captured == [(12.5, "both")]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_mode_signal_includes_display_mode(qapp):
    panel = ResultsPanel()
    captured: list[tuple[int, float, str]] = []
    panel.mode_shape_requested.connect(
        lambda mode, scale, display: captured.append(
            (int(mode), float(scale), str(display))
        )
    )
    try:
        panel.mode_combo.addItem("Mode 1", 1)
        panel.mode_scale.setValue(2.0)
        panel.mode_display.setCurrentIndex(
            panel.mode_display.findData("undeformed_only")
        )
        panel.mode_show_button.click()
        qapp.processEvents()

        assert captured == [(1, 2.0, "undeformed_only")]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_solution_result_restores_display_mode(qapp):
    panel = ResultsPanel()
    try:
        panel.show_solution_result(
            "DeformedShape",
            {
                "scale": 8.0,
                "display_mode": "both",
            },
        )
        assert panel.deformation_scale.value() == pytest.approx(8.0)
        assert panel.deformation_display.currentData() == "both"

        panel.mode_combo.addItem("Mode 2", 2)
        panel.show_solution_result(
            "ModeShape",
            {
                "mode": 2,
                "scale": 1.5,
                "display_mode": "undeformed_only",
            },
        )
        assert panel.mode_combo.currentData() == 2
        assert panel.mode_scale.value() == pytest.approx(1.5)
        assert panel.mode_display.currentData() == "undeformed_only"
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
