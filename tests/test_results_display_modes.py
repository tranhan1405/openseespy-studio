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
        assert panel.specimen_research_table.rowCount() >= 6
        assert panel.specimen_quantity.findData(
            "interface_moment_rotation"
        ) >= 0
        assert panel.specimen_plot._x == pytest.approx([0.0, 0.002])
        assert panel.specimen_plot._y == pytest.approx([0.0, 20.0])

        panel.specimen_quantity.setCurrentIndex(
            panel.specimen_quantity.findData(
                "interface_moment_rotation"
            )
        )
        qapp.processEvents()
        assert panel.specimen_plot._x == pytest.approx([0.0, 0.0002])
        assert panel.specimen_plot._y == pytest.approx([0.0, 18.0])

        panel._set_cyclic_experiment_dataset(
            {
                "headers": [
                    "Displacement",
                    "Force",
                    "Curvature",
                    "Moment",
                ],
                "rows": [
                    [0.0, 0.0, 0.0, 0.0],
                    [0.01, 18.0, 0.002, 19.0],
                ],
                "delimiter": ",",
                "skipped_rows": 0,
            },
            path="/tmp/specimen_response.csv",
        )
        panel.specimen_quantity.setCurrentIndex(
            panel.specimen_quantity.findData("moment_curvature")
        )
        qapp.processEvents()

        assert panel.specimen_exp_x_column.currentText() == "Curvature"
        assert panel.specimen_exp_y_column.currentText() == "Moment"
        assert panel.specimen_plot._overlay_x == pytest.approx(
            [0.0, 0.002]
        )
        assert panel.specimen_plot._overlay_y == pytest.approx(
            [0.0, 19.0]
        )
        assert "specimen_response.csv" in panel.specimen_experiment_info.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()



def test_cyclic_tab_shows_synchronized_column_reversal_and_cycle_metrics(qapp):
    displacement = [1.0, 2.0, 1.0, 0.0, -1.0, -2.0, -1.0, 0.0, 1.0, 2.0, 1.0]
    shear = [10.0, 20.0, 8.0, 0.0, -10.0, -18.0, -7.0, 0.0, 9.0, 16.0, 6.0]
    moments = [30.0, 60.0, 24.0, 0.0, -30.0, -54.0, -21.0, 0.0, 27.0, 48.0, 18.0]
    curvature = [0.001, 0.002, 0.001, 0.0, -0.001, -0.002, -0.001, 0.0, 0.001, 0.002, 0.001]
    interface_rotation = [
        0.0001, 0.0002, 0.0001, 0.0, -0.0001, -0.0002,
        -0.0001, 0.0, 0.0001, 0.0002, 0.0001,
    ]
    result = {
        "analysis": {
            "type": "Cyclic",
            "control_node": 2,
            "control_dof": 1,
        },
        "specimen": {
            "kind": "test-column",
            "element_tag": 10,
            "base_node": 1,
            "top_node": 2,
            "ground_node": 3,
            "height": 1000.0,
            "lateral_direction": 1,
            "bending_rotation_dof": 5,
            "moment_component": "My",
            "moment_index": 2,
            "moment_sign": -1.0,
            "interface_type": "zeroLengthSection",
            "interface_name": "Bond_SP01 strain penetration",
        },
        "history": {
            "time": [float(index + 1) for index in range(len(displacement))],
            "control_dof": 1,
            "displacement": [
                [value, 0.0, 0.0, 0.0, 0.0, 0.0]
                for value in displacement
            ],
            "base_shear": [-value for value in shear],
            "nodes": {
                "1": {
                    "disp": [
                        [0.0, 0.0, 0.0, 0.0, theta, 0.0]
                        for theta in interface_rotation
                    ]
                },
                "2": {
                    "disp": [
                        [value, 0.0, 0.0, 0.0, theta, 0.0]
                        for value, theta in zip(
                            displacement,
                            interface_rotation,
                        )
                    ]
                },
                "3": {
                    "disp": [
                        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        for _ in displacement
                    ]
                },
            },
            "specimen": {
                "section_force": [
                    [100.0, 0.0, -value, 0.0]
                    for value in moments
                ],
                "section_deformation": [
                    [0.0, 0.0, -value, 0.0]
                    for value in curvature
                ],
                "interface_force": [
                    [100.0, 0.0, -0.9 * value, 0.0]
                    for value in moments
                ],
                "interface_deformation": [
                    [0.0, 0.0, -value, 0.0]
                    for value in interface_rotation
                ],
                "base_fibers": [
                    [
                        {
                            "label": "steel_max",
                            "material_tag": 2,
                            "material_type": "ReinforcingSteel",
                            "y": 0.0,
                            "z": 0.15,
                            "stress": 200.0 * value,
                            "strain": 0.001 * value,
                        },
                        {
                            "label": "concrete_min",
                            "material_tag": 4,
                            "material_type": "Concrete02",
                            "y": 0.0,
                            "z": -0.15,
                            "stress": -15.0 * abs(value),
                            "strain": -0.0015 * abs(value),
                        },
                    ]
                    for value in displacement
                ],
                "interface_fibers": [
                    [
                        {
                            "label": "bond_max",
                            "material_tag": 3,
                            "material_type": "Bond_SP01",
                            "y": 0.0,
                            "z": 0.15,
                            "stress": 150.0 * value,
                            "slip": 0.1 * value,
                        }
                    ]
                    for value in displacement
                ],
            },
        },
        "final": {},
        "convergence": {"steps": []},
        "modes": {},
    }

    panel = ResultsPanel()
    try:
        panel.set_result(result)
        panel.show_solution_result("CyclicHysteresis")
        qapp.processEvents()

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Cyclic Hysteresis"
        assert panel.cyclic_reversal_table.columnCount() == 20
        assert panel.cyclic_reversal_table.rowCount() == 3
        assert panel.cyclic_cycle_table.rowCount() == 1

        assert panel.cyclic_reversal_table.item(0, 3).text() == "0.002"
        assert panel.cyclic_reversal_table.item(0, 4).text() == "60"
        assert panel.cyclic_reversal_table.item(0, 5).text() == "0.002"
        assert panel.cyclic_reversal_table.item(0, 6).text() == "0.002"
        assert panel.cyclic_reversal_table.item(0, 7).text() == "-0.003"
        assert panel.cyclic_reversal_table.item(0, 8).text() == "0.2"
        assert panel.cyclic_reversal_table.item(0, 9).text() == "0.0002"

        assert panel.cyclic_reversal_table.item(2, 11).text() == "0.8"
        assert panel.cyclic_reversal_table.item(2, 12).text() == "0.8"
        assert panel.cyclic_reversal_table.item(2, 14).text() == "1"
        assert float(panel.cyclic_reversal_table.item(2, 15).text()) > 0.0

        assert panel.cyclic_cycle_table.item(0, 0).text() == "1"
        assert panel.cyclic_cycle_table.item(0, 1).text() == "3"
        assert panel.cyclic_cycle_table.item(0, 2).text() == "2"

        experimental_force = [
            9.5, 19.0, 7.5, 0.0, -9.5, -17.0,
            -6.5, 0.0, 8.5, 15.0, 5.5,
        ]
        panel._set_cyclic_experiment_dataset(
            {
                "headers": ["Displacement [mm]", "Force [kN]"],
                "rows": [
                    [0.0, 0.0],
                    *[
                        [u, force]
                        for u, force in zip(
                            displacement,
                            experimental_force,
                        )
                    ],
                ],
                "delimiter": ",",
                "skipped_rows": 0,
            },
            path="/tmp/specimen_test.csv",
        )
        qapp.processEvents()

        assert not panel.cyclic_compare_table.isHidden()
        assert panel.cyclic_compare_table.rowCount() == 5
        assert len(panel.cyclic_plot._overlay_x) == len(displacement) + 1
        assert len(panel.cyclic_plot._overlay_y) == len(displacement) + 1
        assert panel.cyclic_reversal_table.item(0, 16).text() == "19"
        assert float(panel.cyclic_reversal_table.item(0, 17).text()) > 5.0
        assert panel.cyclic_reversal_table.item(0, 18).text() != "-"
        assert "matched reversals 3/3" in panel.cyclic_experiment_info.text()

        panel.cyclic_compare_view.setCurrentIndex(
            panel.cyclic_compare_view.findData("backbone")
        )
        qapp.processEvents()
        assert panel.cyclic_plot._x == pytest.approx([-2.0, 0.0, 2.0])
        assert panel.cyclic_plot._overlay_x == pytest.approx(
            [-2.0, 0.0, 2.0]
        )
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_2d_modal_summary_does_not_fake_uz_mass_participation(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Modal"},
        "final": {},
        "convergence": {"steps": []},
        "modes": {
            "1": {
                "eigenvalue": 4.0,
                "frequency_hz": 1.0,
                "period_s": 1.0,
                "vectors": {},
                "participation": {
                    "1": {"mass_ratio": 0.60},
                    "2": {"mass_ratio": 0.20},
                },
            },
            "2": {
                "eigenvalue": 9.0,
                "frequency_hz": 1.5,
                "period_s": 2.0 / 3.0,
                "vectors": {},
                "participation": {
                    "1": {"mass_ratio": 0.30},
                    "2": {"mass_ratio": 0.70},
                },
            },
        },
    }
    try:
        panel.set_result(result)
        qapp.processEvents()

        assert panel.modal_summary_table.item(0, 4).text() == "60.000"
        assert panel.modal_summary_table.item(0, 5).text() == "20.000"
        assert panel.modal_summary_table.item(0, 6).text() == "-"
        assert panel.modal_summary_table.item(1, 7).text() == "90.000"
        assert panel.modal_summary_table.item(1, 8).text() == "90.000"
        assert panel.modal_summary_table.item(1, 9).text() == "-"
        assert "UX=60.00%" in panel.mode_info.text()
        assert "UY=20.00%" in panel.mode_info.text()
        assert "UZ=" not in panel.mode_info.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_modal_mass_coverage_warns_when_relevant_direction_is_below_reference(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Modal"},
        "modal_summary": {
            "total_free_mass": {"1": 10.0, "2": 8.0}
        },
        "final": {},
        "convergence": {"steps": []},
        "modes": {
            "1": {
                "eigenvalue": 4.0,
                "frequency_hz": 1.0,
                "period_s": 1.0,
                "vectors": {},
                "participation": {
                    "1": {"mass_ratio": 0.50},
                    "2": {"mass_ratio": 0.40},
                },
            },
            "2": {
                "eigenvalue": 9.0,
                "frequency_hz": 1.5,
                "period_s": 2.0 / 3.0,
                "vectors": {},
                "participation": {
                    "1": {"mass_ratio": 0.25},
                    "2": {"mass_ratio": 0.55},
                },
            },
        },
    }
    try:
        panel.set_result(result)
        qapp.processEvents()

        text = panel.modal_mass_coverage.text()
        assert "UX=75.00%" in text
        assert "UY=95.00%" in text
        assert "below 90% reference in UX" in text
        assert "consider extracting more modes" in text
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_modal_mass_coverage_ignores_direction_without_positive_free_mass(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Modal"},
        "modal_summary": {
            "total_free_mass": {"1": 10.0, "2": 0.0}
        },
        "final": {},
        "convergence": {"steps": []},
        "modes": {
            "1": {
                "eigenvalue": 4.0,
                "frequency_hz": 1.0,
                "period_s": 1.0,
                "vectors": {},
                "participation": {
                    "1": {"mass_ratio": 0.92},
                    "2": {"mass_ratio": 0.0},
                },
            },
        },
    }
    try:
        panel.set_result(result)
        qapp.processEvents()

        text = panel.modal_mass_coverage.text()
        assert "UX=92.00%" in text
        assert "UY=" not in text
        assert "All shown translational directions ≥ 90% reference." in text
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_dedicated_moment_curvature_result_selects_and_populates_tab(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {
            "type": "Static",
            "integrator": "DisplacementControl",
        },
        "moment_curvature": {
            "kind": "moment-curvature",
            "element_tag": 1,
            "section_tag": 1,
            "control_node": 2,
            "control_dof": 3,
            "moment_component": "Mz",
            "moment_index": 1,
            "moment_sign": 1.0,
        },
        "history": {
            "time": [1.0, 2.0],
            "nodes": {},
            "moment_curvature": {
                "force": [[-180.0, 10.0], [-180.0, 20.0]],
                "deformation": [[0.0, 0.001], [0.0, 0.002]],
            },
        },
        "final": {},
        "convergence": {"steps": []},
        "modes": {},
    }
    try:
        panel.set_result(result)
        panel.show_solution_result("MomentCurvature")
        qapp.processEvents()

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Moment–Curvature"
        assert panel.moment_curvature_plot._x == pytest.approx(
            [0.0, 0.001, 0.002]
        )
        assert panel.moment_curvature_plot._y == pytest.approx(
            [0.0, 10.0, 20.0]
        )
        assert "zeroLengthSection element 1" in panel.moment_curvature_info.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
