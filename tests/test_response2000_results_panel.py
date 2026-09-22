from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.results_panel import ResultsPanel


_APP = QApplication.instance() or QApplication([])


def _moment_curvature_result():
    return {
        "moment_curvature": {
            "kind": "moment-curvature",
            "section_tag": 7,
            "element_tag": 1,
            "moment_component": "Mz",
            "moment_index": 1,
            "moment_sign": 1.0,
        },
        "history": {
            "moment_curvature": {
                "force": [
                    [0.0, 100.0e6],
                    [0.0, 180.0e6],
                    [0.0, 220.0e6],
                ],
                "deformation": [
                    [0.0, 1.0e-6],
                    [0.0, 2.0e-6],
                    [0.0, 4.0e-6],
                ],
            }
        },
    }


def test_response2000_overlay_is_converted_and_compared_in_results_panel():
    panel = ResultsPanel()
    try:
        panel.set_units({"length": "mm", "force": "N", "time": "s"})
        panel.set_result(_moment_curvature_result())

        applied = panel._apply_response2000_dataset(
            {
                "headers": [
                    "Curvature-Y (rad/km)",
                    "Moment-Y (kN-m)",
                ],
                "rows": [
                    [0.0, 0.0],
                    [1.0, 100.0],
                    [2.0, 180.0],
                    [4.0, 220.0],
                ],
            },
            path="response2000.txt",
        )

        assert applied is True

        assert panel.moment_curvature_plot._overlay_x == pytest.approx(
            [0.0, 1.0e-6, 2.0e-6, 4.0e-6]
        )
        assert panel.moment_curvature_plot._overlay_y == pytest.approx(
            [0.0, 100.0e6, 180.0e6, 220.0e6]
        )
        assert panel.response2000_compare_table.rowCount() == 4
        assert panel.response2000_compare_table.isHidden() is False
        assert "Response-2000" in panel.response2000_info.text()
        assert "NRMSE" in panel.response2000_info.text()
    finally:
        panel.close()
        panel.deleteLater()
        _APP.processEvents()



def test_response2000_clipboard_paste_populates_overlay():
    panel = ResultsPanel()
    clipboard = QApplication.clipboard()
    old_text = clipboard.text()
    try:
        panel.set_units({"length": "m", "force": "kN", "time": "s"})
        panel.set_result(
            {
                "moment_curvature": {
                    "kind": "moment-curvature",
                    "section_tag": 7,
                    "element_tag": 1,
                    "moment_component": "Mz",
                    "moment_index": 1,
                    "moment_sign": 1.0,
                },
                "history": {
                    "moment_curvature": {
                        "force": [[0.0, 100.0], [0.0, 180.0]],
                        "deformation": [[0.0, 0.001], [0.0, 0.002]],
                    }
                },
            }
        )
        clipboard.setText(
            "Curvature-Y (rad/km)\tMoment-Y (kN-m)\n"
            "0\t0\n"
            "1\t100\n"
            "2\t180\n"
        )

        panel._paste_response2000_data()

        assert panel._response2000_source_name == "Response-2000 clipboard"
        assert panel.moment_curvature_plot._overlay_x == pytest.approx(
            [0.0, 0.001, 0.002]
        )
        assert panel.moment_curvature_plot._overlay_y == pytest.approx(
            [0.0, 100.0, 180.0]
        )
    finally:
        clipboard.setText(old_text)
        panel.close()
        panel.deleteLater()
        _APP.processEvents()
