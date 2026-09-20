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
        assert panel.deformation_representation.currentData() == "actual_section"
        assert panel.deformation_smooth.isChecked()
        assert panel.mode_display.currentData() == "deformed_only"
        assert panel.mode_representation.currentData() == "actual_section"
        assert panel.mode_smooth.isChecked()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_deformation_signal_includes_display_mode(qapp):
    panel = ResultsPanel()
    captured: list[tuple[float, str, str, bool]] = []
    panel.deformation_requested.connect(
        lambda scale, mode, representation, smooth: captured.append(
            (
                float(scale),
                str(mode),
                str(representation),
                bool(smooth),
            )
        )
    )
    try:
        panel.deformation_scale.setValue(12.5)
        panel.deformation_display.setCurrentIndex(
            panel.deformation_display.findData("both")
        )
        panel.deformation_show_button.click()
        qapp.processEvents()

        assert captured == [(12.5, "both", "actual_section", True)]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_mode_signal_includes_display_mode(qapp):
    panel = ResultsPanel()
    captured: list[tuple[int, float, str, str, bool]] = []
    panel.mode_shape_requested.connect(
        lambda mode, scale, display, representation, smooth: captured.append(
            (
                int(mode),
                float(scale),
                str(display),
                str(representation),
                bool(smooth),
            )
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

        assert captured == [
            (1, 2.0, "undeformed_only", "actual_section", True)
        ]
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
                "representation": "centerline",
                "smooth_curvature": False,
            },
        )
        assert panel.deformation_scale.value() == pytest.approx(8.0)
        assert panel.deformation_display.currentData() == "both"
        assert panel.deformation_representation.currentData() == "centerline"
        assert not panel.deformation_smooth.isChecked()

        panel.mode_combo.addItem("Mode 2", 2)
        panel.show_solution_result(
            "ModeShape",
            {
                "mode": 2,
                "scale": 1.5,
                "display_mode": "undeformed_only",
                "representation": "tube",
                "smooth_curvature": False,
            },
        )
        assert panel.mode_combo.currentData() == 2
        assert panel.mode_scale.value() == pytest.approx(1.5)
        assert panel.mode_display.currentData() == "undeformed_only"
        assert panel.mode_representation.currentData() == "tube"
        assert not panel.mode_smooth.isChecked()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()



def test_specimen_response_tab_loads_moment_curvature_and_fiber_choices(qapp):
    panel = ResultsPanel()
    result = {
        "specimen": {
            "kind": "test-column",
            "element_tag": 10,
            "base_node": 1,
            "top_node": 2,
            "ground_node": 3,
            "height": 3.0,
            "lateral_direction": 1,
            "bending_rotation_dof": 5,
            "moment_component": "My",
            "moment_index": 2,
            "moment_sign": -1.0,
            "interface_type": "zeroLengthSection",
            "interface_name": "Bond_SP01 strain penetration",
        },
        "history": {
            "time": [1.0],
            "nodes": {
                "1": {"disp": [[0.001, 0, 0, 0, 0.0001, 0]]},
                "2": {"disp": [[0.01, 0, 0, 0, 0.001, 0]]},
                "3": {"disp": [[0, 0, 0, 0, 0, 0]]},
            },
            "specimen": {
                "section_force": [[0.0, 0.0, -20.0, 0.0]],
                "section_deformation": [[0.0, 0.0, -0.002, 0.0]],
                "base_fibers": [[{
                    "label": "steel_max",
                    "material_tag": 2,
                    "material_type": "ReinforcingSteel",
                    "y": 0.0,
                    "z": 0.15,
                    "stress": 400.0,
                    "strain": 0.002,
                }]],
                "interface_force": [[0.0, 0.0, -18.0, 0.0]],
                "interface_deformation": [[0.0, 0.0, -0.0002, 0.0]],
                "interface_fibers": [[{
                    "label": "bond_max",
                    "material_tag": 3,
                    "material_type": "Bond_SP01",
                    "y": 0.0,
                    "z": 0.15,
                    "stress": 350.0,
                    "slip": 0.001,
                }]],
            },
        },
        "analysis": {"type": "Cyclic"},
        "final": {},
        "convergence": {"steps": []},
        "modes": {},
    }
    try:
        panel.set_result(result)
        panel.show_solution_result("SpecimenResponse")
        qapp.processEvents()

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Specimen Response"
        assert panel.specimen_quantity.findData("moment_curvature") >= 0
        assert (
            panel.specimen_quantity.findData(
                "interface_fibers:bond_max:slip"
            )
            >= 0
        )
        assert panel.specimen_fiber_table.rowCount() == 4
        assert panel.specimen_plot._x == pytest.approx([0.0, 0.002])
        assert panel.specimen_plot._y == pytest.approx([0.0, 20.0])
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
