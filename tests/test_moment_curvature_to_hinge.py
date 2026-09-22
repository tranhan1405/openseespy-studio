from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.results_panel import ResultsPanel


_APP = QApplication.instance() or QApplication([])


def test_moment_curvature_result_can_be_sent_to_hinge_builder():
    panel = ResultsPanel()
    captured = []
    panel.moment_curvature_hinge_requested.connect(captured.append)

    result = {
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
                    [0.0, 10.0],
                    [0.0, 20.0],
                ],
                "deformation": [
                    [0.0, 0.001],
                    [0.0, 0.002],
                ],
            }
        },
    }

    try:
        panel.set_result(result)
        panel._send_moment_curvature_to_hinge()

        assert len(captured) == 1
        payload = captured[0]
        assert payload["source_kind"] == "sare_moment_curvature"
        assert payload["basis"] == "moment_curvature"
        assert payload["section_tag"] == 7
        assert payload["component"] == "Mz"
        assert payload["curvature"] == [0.0, 0.001, 0.002]
        assert payload["moment"] == [0.0, 10.0, 20.0]
    finally:
        panel.close()
        panel.deleteLater()
        _APP.processEvents()
