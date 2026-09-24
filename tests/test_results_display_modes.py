from __future__ import annotations

import inspect
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.results_panel import ResultsPanel
from openseespy_studio.ui.viewport import ModelViewport


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




def test_crack_pattern_result_restores_controls_and_reports_panels(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Static"},
        "mefi_crack_specs": {
            "10": {
                "source": "MEFI RCPanel panel_strain",
                "panels": [
                    {
                        "panel": 1,
                        "width": 0.5,
                        "section_tag": 3,
                        "cracking_strain": 1.0e-4,
                    }
                ],
            }
        },
        "history": {
            "time": [1.0, 2.0],
            "nodes": {
                "1": {
                    "disp": [
                        [0.0, 0.0, 0.0],
                        [0.001, 0.0, 0.0],
                    ]
                }
            },
            "mefi_panel_strains": {
                "10": {
                    "1": [
                        [5.0e-5, 0.0, 0.0],
                        [2.0e-4, 0.0, 0.0],
                    ]
                }
            },
        },
        "final": {
            "node_displacements": {"1": [0.001, 0.0, 0.0]},
            "mefi_panel_strains": {
                "10": {"1": [2.0e-4, 0.0, 0.0]}
            },
        },
        "convergence": {"steps": []},
        "modes": {},
    }
    captured = []
    panel.crack_frame_requested.connect(
        lambda frame, accumulate, line_scale, scope: captured.append(
            (int(frame), bool(accumulate), float(line_scale), list(scope))
        )
    )
    try:
        panel.set_result(result)
        panel.show_solution_result(
            "CrackPattern",
            {
                "accumulate": True,
                "line_scale": 0.65,
                "_element_scope": [10],
            },
        )
        qapp.processEvents()

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Crack Pattern"
        assert panel.crack_accumulate.isChecked()
        assert panel.crack_line_scale.value() == pytest.approx(0.65)
        assert panel.crack_table.rowCount() == 1
        assert panel.crack_table.item(0, 5).text() == "Cracked"
        assert "1 cracked" in panel.crack_summary.text()
        assert "max ε1/εcr = 2.000" in panel.crack_summary.text()
        assert not panel.motion_page.isHidden()
        assert panel._motion_frame_index == 1
        assert panel.motion_slider.value() == 1

        captured.clear()
        panel._crack_controls_changed()
        qapp.processEvents()
        assert captured
        assert captured[-1][0] == 1
        assert captured[-1][1:] == (True, pytest.approx(0.65), [10])
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_crack_principal_strain_and_main_window_wiring():
    epsilon_1, theta_1 = ModelViewport._principal_tensile_strain(
        [2.0e-4, 0.0, 0.0]
    )
    assert epsilon_1 == pytest.approx(2.0e-4)
    assert theta_1 == pytest.approx(0.0)

    shear_epsilon, shear_theta = ModelViewport._principal_tensile_strain(
        [0.0, 0.0, 2.0e-4]
    )
    assert shear_epsilon == pytest.approx(1.0e-4)
    assert abs(shear_theta) == pytest.approx(math.pi / 4.0)

    dock_source = inspect.getsource(MainWindow._build_bottom_docks)
    render_source = inspect.getsource(MainWindow._render_result_data)
    prereq_source = inspect.getsource(
        MainWindow._prepare_solution_result_prerequisites
    )
    frame_source = inspect.getsource(MainWindow._show_crack_frame_result)

    assert "crack_frame_requested.connect" in dock_source
    assert 'result_type == "CrackPattern"' in render_source
    assert "show_crack_pattern" in render_source
    assert 'kind == "CrackPattern"' in prereq_source
    assert 'element.element_type == "MEFI"' in prereq_source
    assert "frame_index=None if frame < 0 else frame" in frame_source



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


def test_generic_section_response_result_selects_requested_beam_ip(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Static", "integrator": "LoadControl"},
        "section_responses": {
            "request:12": {
                "key": "request:12",
                "kind": "section-response",
                "request_tag": 12,
                "element_tag": 23,
                "element_kind": "forceBeamColumn",
                "section_tag": 4,
                "query_mode": "indexed",
                "section_number": 2,
                "component": "Mz",
                "force_index": 1,
                "deformation_index": 1,
                "force_label": "Moment Mz",
                "deformation_label": "Curvature κz",
                "pair_label": "Mz–κz",
                "automatic": False,
            }
        },
        "history": {
            "time": [1.0, 2.0],
            "nodes": {},
            "section_responses": {
                "request:12": {
                    "force": [[-10.0, 12.0], [-10.0, 24.0]],
                    "deformation": [[-0.001, 0.002], [-0.002, 0.004]],
                }
            },
        },
        "final": {},
        "convergence": {"steps": []},
        "modes": {},
    }
    try:
        panel.set_result(result)
        panel.show_solution_result(
            "SectionResponse",
            {
                "_element_scope": [23],
                "section": 2,
                "component": "Mz",
            },
        )
        qapp.processEvents()

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Section Response"
        assert panel.section_response_plot._x == pytest.approx([0.002, 0.004])
        assert panel.section_response_plot._y == pytest.approx([12.0, 24.0])
        assert "forceBeamColumn element 23" in panel.section_response_info.text()
        assert "IP 2" in panel.section_response_info.text()
        assert "Mz–κz" in panel.section_response_info.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_dense_results_use_subtabs(qapp):
    panel = ResultsPanel()
    try:
        assert [
            panel.convergence_detail_tabs.tabText(index)
            for index in range(panel.convergence_detail_tabs.count())
        ] == ["Overview", "Step Details"]

        assert [
            panel.moment_curvature_detail_tabs.tabText(index)
            for index in range(panel.moment_curvature_detail_tabs.count())
        ] == ["Curve", "Response-2000"]

        assert [
            panel.specimen_detail_tabs.tabText(index)
            for index in range(panel.specimen_detail_tabs.count())
        ] == ["Response", "Research Metrics", "Fiber History"]

        assert [
            panel.calibration_detail_tabs.tabText(index)
            for index in range(panel.calibration_detail_tabs.count())
        ] == ["History", "Pareto", "Cases"]

        # Cyclic was already the reference pattern for dense result pages.
        assert [
            panel.cyclic_detail_tabs.tabText(index)
            for index in range(panel.cyclic_detail_tabs.count())
        ] == ["Curve", "Experiment", "Reversals", "Cycles"]

        panel.moment_curvature_detail_tabs.setCurrentIndex(1)
        panel.show_solution_result("MomentCurvature")
        assert panel.moment_curvature_detail_tabs.currentIndex() == 0

        panel.specimen_detail_tabs.setCurrentIndex(2)
        panel.show_solution_result("SpecimenResponse")
        assert panel.specimen_detail_tabs.currentIndex() == 0

        panel.convergence_detail_tabs.setCurrentIndex(1)
        panel.show_solution_result("Convergence")
        assert panel.convergence_detail_tabs.currentIndex() == 0

        panel.show_calibration()
        assert panel.calibration_detail_tabs.currentIndex() == 2
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_clear_all_resets_dense_result_state(qapp):
    panel = ResultsPanel()
    try:
        # Seed state that previously survived Delete All Jobs / result reset.
        panel._response2000_dataset = {"headers": ["k", "M"], "rows": [[0, 0]]}
        panel._response2000_path = "/tmp/response.txt"
        panel._response2000_source_name = "response.txt"
        panel.response2000_curvature_column.addItem("k", 0)
        panel.response2000_moment_column.addItem("M", 1)
        panel.response2000_compare_table.setRowCount(2)
        panel.response2000_curvature_factor.setValue(2.0)
        panel.response2000_moment_factor.setValue(-1.0)
        panel.moment_curvature_plot.set_overlay([0.0, 1.0], [0.0, 2.0])

        panel.specimen_quantity.addItem("Old response", "old")
        panel.specimen_plot.set_series([0.0, 1.0], [0.0, 1.0])
        panel.specimen_research_table.setRowCount(2)
        panel.specimen_fiber_table.setRowCount(3)
        panel.specimen_exp_x_scale.setValue(2.0)
        panel.specimen_exp_y_scale.setValue(3.0)

        panel.cyclic_cycle_table.setRowCount(4)
        panel.cyclic_exp_x_scale.setValue(4.0)
        panel.cyclic_exp_y_scale.setValue(5.0)
        panel.cyclic_experiment_info.setText("old experiment")
        panel.cyclic_research_info.setText("old research")

        panel.motion_source.addItem("Old motion", 1)
        panel.motion_slider.setRange(0, 9)
        panel.motion_counter.setText("5 / 10")

        panel.clear_all()
        qapp.processEvents()

        assert panel._response2000_dataset == {}
        assert panel._response2000_path == ""
        assert panel._response2000_source_name == ""
        assert panel.response2000_curvature_column.count() == 0
        assert panel.response2000_moment_column.count() == 0
        assert panel.response2000_compare_table.rowCount() == 0
        assert panel.moment_curvature_plot._overlay_x == []
        assert panel.moment_curvature_plot._overlay_y == []
        assert panel.response2000_curvature_factor.value() == pytest.approx(1.0)
        assert panel.response2000_moment_factor.value() == pytest.approx(1.0)

        assert panel.specimen_quantity.count() == 0
        assert panel.specimen_plot._x == []
        assert panel.specimen_plot._y == []
        assert panel.specimen_research_table.rowCount() == 0
        assert panel.specimen_fiber_table.rowCount() == 0
        assert panel.specimen_exp_x_scale.value() == pytest.approx(1.0)
        assert panel.specimen_exp_y_scale.value() == pytest.approx(1.0)
        assert panel.specimen_metrics.text().startswith("Mmax: -")

        assert panel.cyclic_cycle_table.rowCount() == 0
        assert panel.cyclic_exp_x_scale.value() == pytest.approx(1.0)
        assert panel.cyclic_exp_y_scale.value() == pytest.approx(1.0)
        assert "Optional:" in panel.cyclic_experiment_info.text()
        assert "1D-column research metrics" in panel.cyclic_research_info.text()

        assert panel.motion_slider.maximum() == 0
        assert panel.motion_counter.text() == "/ 0"
        assert not panel.motion_play.isEnabled()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()



def test_result_ribbon_display_modes_cover_nodal_contours_and_motion():
    set_mode_source = inspect.getsource(MainWindow._set_result_display_mode)
    render_source = inspect.getsource(MainWindow._render_result_data)
    node_source = inspect.getsource(MainWindow._show_node_contour_result)
    motion_source = inspect.getsource(MainWindow._show_motion_frame_result)

    assert '{"deformation", "mode", "node", "motion"}' in set_mode_source
    assert 'kind == "node"' in set_mode_source
    assert 'self.results_panel._emit_current_motion_frame()' in set_mode_source
    assert 'result_type in {"NodalDisplacement", "NodalReaction"}' in render_source
    assert '"node",' in render_source
    assert 'result_type == "Motion"' in render_source
    assert 'options.get("probe", False)' in render_source
    assert 'display_mode=mode' in node_source
    assert 'deformation_scale=scale' in node_source
    assert 'display_mode=display_mode' in motion_source


def test_node_contour_display_mode_changes_result_geometry():
    source = inspect.getsource(ModelViewport.show_node_contour)

    assert 'display_mode: str = "deformed_only"' in source
    assert 'deformation_scale: float = 10.0' in source
    assert 'display_mode == "undeformed_only"' in source
    assert 'final.get("node_displacements", {})' in source
    assert 'deformation_scale * dx' in source
    assert 'display_mode == "both"' in source


def test_motion_display_mode_supports_deformed_both_and_undeformed():
    source = inspect.getsource(ModelViewport.show_motion_frame)

    assert 'display_mode: str = "deformed_only"' in source
    assert 'display_mode == "undeformed_only"' in source
    assert 'display_mode == "both"' in source
    assert 'self.set_undeformed_model_visible(' in source


def test_viewport_background_presets_and_custom_colors_are_stable():
    assert ModelViewport.background_style_spec("Light") == (
        "#f2f5f8",
        None,
    )
    assert ModelViewport.background_style_spec("Dark") == (
        "#20262e",
        None,
    )
    assert ModelViewport.background_style_spec("ANSYS Gradient") == (
        "#f2f5f8",
        "#e1e8ef",
    )
    assert ModelViewport.background_style_spec("Publication White") == (
        "#ffffff",
        None,
    )
    assert ModelViewport.background_style_spec(
        "Custom Solid",
        custom_bottom="#123456",
    ) == ("#123456", None)
    assert ModelViewport.background_style_spec(
        "Custom Gradient",
        custom_bottom="#123456",
        custom_top="#abcdef",
    ) == ("#123456", "#abcdef")
    assert ModelViewport.background_style_spec(
        "Custom Solid",
        custom_bottom="not-a-color",
    ) == ("#f2f5f8", None)

    with pytest.raises(ValueError, match="Unsupported viewport background"):
        ModelViewport.background_style_spec("Unknown")


def test_display_ribbon_exposes_compact_background_menu():
    build_source = inspect.getsource(MainWindow._build_actions_and_ribbon)
    sync_source = inspect.getsource(MainWindow._sync_background_menu)
    save_source = inspect.getsource(
        MainWindow._save_background_preferences
    )
    reset_source = inspect.getsource(ModelViewport._reset_scene)

    assert '"Appearance"' in build_source
    assert 'setText("Background")' in build_source
    assert "QToolButton.InstantPopup" in build_source
    assert '"Publication White"' in build_source
    assert '"Custom Solid..."' in build_source
    assert '"Custom Gradient..."' in build_source
    assert '"Reset to ANSYS Gradient"' in build_source

    # Background settings belong inside the drop-down menu rather than
    # consuming three rows of ribbon space.
    assert "background_combo" not in build_source
    assert "background_bottom_button" not in build_source
    assert "background_top_button" not in build_source
    assert "background_reset_button" not in build_source

    assert "background_preset_actions" in sync_source
    assert "setChecked" in sync_source
    assert "set_background_style" in sync_source

    assert '"display/backgroundPreset"' in save_source
    assert '"display/backgroundBottom"' in save_source
    assert '"display/backgroundTop"' in save_source

    # Scene refreshes must preserve the selected background instead of
    # restoring a hard-coded color.
    assert "_apply_background(render=False)" in reset_source
    assert "_apply_axes_widget()" in reset_source


def test_nodal_contour_preserves_quad_shell_surfaces():
    source = inspect.getsource(ModelViewport.show_node_contour)

    assert "element.element_type in QUAD_ELEMENT_TYPES" in source
    assert "element.node_tags()" in source
    assert "quad_faces.extend" in source
    assert 'faces=np.asarray(quad_faces' in source
    assert '"result-shell-contour"' in source
    assert '"show_edges": True' in source
    assert "scoped_nodes.update(element.node_tags())" in source


def test_animation_preserves_quad_shell_topology():
    source = inspect.getsource(ModelViewport.show_motion_frame)

    assert "element.element_type in QUAD_ELEMENT_TYPES" in source
    assert "node_tags = element.node_tags()" in source
    assert "element_faces.extend" in source
    assert "mesh.faces = np.asarray" in source
    assert "show_edges=bool(element_faces)" in source
    assert "element_node_tags.extend(node_tags)" in source


def test_crack_pattern_renderer_is_high_contrast_and_diagnostic():
    source = inspect.getsource(ModelViewport.show_crack_pattern)

    assert "mefi_crack_panel_states" in source
    assert "mefi_crack_summary" in source
    assert 'color="#c62828"' in source
    assert "line_width=9" in source
    assert "lighting=False" in source
    assert "return stats" in source


def test_crack_summary_reports_max_cracking_ratio(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Static"},
        "mefi_crack_specs": {
            "1": {
                "panels": [
                    {
                        "panel": 1,
                        "width": 1.0,
                        "section_tag": 1,
                        "cracking_strain": 1.0e-4,
                    }
                ]
            }
        },
        "history": {
            "mefi_panel_strains": {
                "1": {"1": [[2.0e-4, 0.0, 0.0]]}
            }
        },
        "final": {
            "mefi_panel_strains": {
                "1": {"1": [2.0e-4, 0.0, 0.0]}
            }
        },
        "modes": {},
    }
    try:
        panel.set_result(result)
        assert "1 cracked" in panel.crack_summary.text()
        assert "max ε1/εcr = 2.000" in panel.crack_summary.text()
        assert "max ε1/εcr = 2.000" in panel.crack_summary.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_nodal_reaction_table_follows_animation_frames_and_can_export(
    qapp,
    tmp_path,
    monkeypatch,
):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Static"},
        "history": {
            "time": [0.5, 1.0],
            "nodes": {
                "1": {
                    "disp": [
                        [0.001, 0.0, 0.0],
                        [0.002, 0.0, 0.0],
                    ],
                    "vel": [[], []],
                    "accel": [[], []],
                    "reaction": [
                        [-10.0, -2.0, 0.0],
                        [-25.0, -4.0, 0.0],
                    ],
                },
                "2": {
                    "disp": [
                        [0.0015, 0.0, 0.0],
                        [0.0030, 0.0, 0.0],
                    ],
                    "vel": [[], []],
                    "accel": [[], []],
                    "reaction": [
                        [-12.0, -3.0, 0.0],
                        [-30.0, -5.0, 0.0],
                    ],
                },
            },
            "base_reactions": [
                [-22.0, -5.0, 0.0],
                [-55.0, -9.0, 0.0],
            ],
            "base_shear": [-22.0, -55.0],
            "displacement": [
                [0.0015, 0.0, 0.0],
                [0.0030, 0.0, 0.0],
            ],
        },
        "final": {
            "node_displacements": {
                "1": [0.002, 0.0, 0.0],
                "2": [0.003, 0.0, 0.0],
            },
            "node_reactions": {
                "1": [-25.0, -4.0, 0.0],
                "2": [-30.0, -5.0, 0.0],
            },
        },
        "convergence": {"steps": []},
        "modes": {},
    }
    target = tmp_path / "reaction_frame.csv"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "CSV files (*.csv)"),
    )
    try:
        panel.set_result(result)
        panel.show_solution_result(
            "NodalReaction",
            {"component": "FX"},
        )
        qapp.processEvents()

        assert not panel.node_animate_button.isHidden()
        assert not panel.motion_page.isHidden()

        panel._set_motion_index(0)
        qapp.processEvents()
        assert panel.node_table.horizontalHeaderItem(1).text() == "FX"
        assert panel.node_table.item(0, 1).text() == "-10"
        assert "live animation frame 1/2" in panel.node_frame_status.text()

        panel._set_motion_index(1)
        qapp.processEvents()
        assert panel.node_table.item(0, 1).text() == "-25"
        assert panel.node_table.item(1, 1).text() == "-30"
        assert "live animation frame 2/2" in panel.node_frame_status.text()

        panel._export_node_table_csv()
        exported = target.read_text(encoding="utf-8")
        assert "Node,FX,FY,FZ,MX,MY,MZ" in exported
        assert "1,-25,-4,0,0,0,0" in exported
        assert "2,-30,-5,0,0,0,0" in exported
        assert "Exported 2 nodal reaction row(s)" in panel.node_frame_status.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_node_result_animation_text_no_longer_freezes_tables():
    source = inspect.getsource(ResultsPanel)

    assert "node tables update live" in source
    assert "Values frozen during playback" not in source
    assert "tables update on Pause" not in source
    assert "def _export_node_table_csv" in source


def _two_frame_motion_result():
    return {
        "analysis": {"type": "Static"},
        "history": {
            "time": [0.5, 1.0],
            "nodes": {
                "1": {
                    "disp": [
                        [0.001, 0.0, 0.0],
                        [0.002, 0.0, 0.0],
                    ],
                    "vel": [[], []],
                    "accel": [[], []],
                    "reaction": [[], []],
                }
            },
            "element_local_forces": {
                "10": [
                    [
                        10.0, 2.0, 3.0, 4.0, 5.0, 6.0,
                        -10.0, -2.0, -3.0, -4.0, -5.0, -6.0,
                    ],
                    [
                        20.0, 4.0, 6.0, 8.0, 10.0, 12.0,
                        -20.0, -4.0, -6.0, -8.0, -10.0, -12.0,
                    ],
                ]
            },
            "shell_section_forces": {
                "20": [
                    [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                    [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0],
                ]
            },
            "shell_section_deformations": {
                "20": [
                    [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008],
                    [0.011, 0.012, 0.013, 0.014, 0.015, 0.016, 0.017, 0.018],
                ]
            },
            "mefi_panel_strains": {
                "30": {
                    "1": [
                        [5.0e-5, 0.0, 0.0],
                        [2.0e-4, 0.0, 0.0],
                    ]
                }
            },
            "base_reactions": [[], []],
            "base_shear": [0.0, 0.0],
            "displacement": [
                [0.001, 0.0, 0.0],
                [0.002, 0.0, 0.0],
            ],
        },
        "final": {
            "node_displacements": {"1": [0.002, 0.0, 0.0]},
            "node_reactions": {"1": [0.0, 0.0, 0.0]},
            "element_local_forces": {
                "10": [
                    20.0, 4.0, 6.0, 8.0, 10.0, 12.0,
                    -20.0, -4.0, -6.0, -8.0, -10.0, -12.0,
                ]
            },
            "shell_section_forces": {
                "20": {
                    "average": [
                        11.0, 12.0, 13.0, 14.0,
                        15.0, 16.0, 17.0, 18.0,
                    ],
                    "gauss_points": [],
                }
            },
            "shell_section_deformations": {
                "20": {
                    "average": [
                        0.011, 0.012, 0.013, 0.014,
                        0.015, 0.016, 0.017, 0.018,
                    ],
                    "gauss_points": [],
                }
            },
            "mefi_panel_strains": {
                "30": {"1": [2.0e-4, 0.0, 0.0]}
            },
        },
        "mefi_crack_specs": {
            "30": {
                "panels": [
                    {
                        "panel": 1,
                        "width": 1.0,
                        "section_tag": 1,
                        "cracking_strain": 1.0e-4,
                    }
                ]
            }
        },
        "convergence": {"steps": []},
        "modes": {},
    }


def test_member_force_table_follows_animation_frame(qapp):
    panel = ResultsPanel()
    try:
        panel.set_result(_two_frame_motion_result())
        panel.show_solution_result(
            "MemberForce",
            {"component": "N", "_element_scope": [10]},
        )
        qapp.processEvents()

        panel._set_motion_index(0)
        qapp.processEvents()
        first_i = panel.element_table.item(0, 1).text()
        first_j = panel.element_table.item(0, 2).text()

        panel._set_motion_index(1)
        qapp.processEvents()
        second_i = panel.element_table.item(0, 1).text()
        second_j = panel.element_table.item(0, 2).text()

        assert (first_i, first_j) != (second_i, second_j)
        assert "live animation frame 2/2" in panel.element_info.text()
        assert not panel.member_animate_button.isHidden()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_shell_force_and_deformation_tables_follow_animation_frame(qapp):
    panel = ResultsPanel()
    try:
        panel.set_result(_two_frame_motion_result())

        panel.show_solution_result(
            "ShellForce",
            {"component": "Nxx", "_element_scope": [20]},
        )
        panel._set_motion_index(0)
        qapp.processEvents()
        assert panel.shell_tables["Membrane"].item(0, 1).text() == "1"
        panel._set_motion_index(1)
        qapp.processEvents()
        assert panel.shell_tables["Membrane"].item(0, 1).text() == "11"
        assert "live force summary" in panel.shell_info.text()

        panel.show_solution_result(
            "ShellDeformation",
            {"component": "Exx", "_element_scope": [20]},
        )
        panel._set_motion_index(0)
        qapp.processEvents()
        assert (
            panel.shell_tables["Membrane Strain"].item(0, 1).text()
            == "0.001"
        )
        panel._set_motion_index(1)
        qapp.processEvents()
        assert (
            panel.shell_tables["Membrane Strain"].item(0, 1).text()
            == "0.011"
        )
        assert "live deformation summary" in panel.shell_info.text()
        assert not panel.shell_animate_button.isHidden()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_crack_table_follows_animation_frame_and_accumulate(qapp):
    panel = ResultsPanel()
    try:
        panel.set_result(_two_frame_motion_result())
        panel.show_solution_result(
            "CrackPattern",
            {
                "accumulate": False,
                "line_scale": 0.82,
                "_element_scope": [30],
            },
        )

        panel._set_motion_index(0)
        qapp.processEvents()
        assert panel.crack_table.item(0, 5).text() == "Below εcr"
        assert "active frame 1/2" in panel.crack_summary.text()

        panel._set_motion_index(1)
        qapp.processEvents()
        assert panel.crack_table.item(0, 5).text() == "Cracked"
        assert "active frame 2/2" in panel.crack_summary.text()

        panel.crack_accumulate.setChecked(True)
        panel._set_motion_index(1)
        qapp.processEvents()
        assert panel.crack_table.item(0, 5).text() == "Cracked"
        assert "accumulated frame 2/2" in panel.crack_summary.text()
        assert "max≤frame" in panel.crack_table.horizontalHeaderItem(3).text()
        assert not panel.crack_animate_button.isHidden()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_crack_result_viewer_uses_compact_subtabs_and_data_health(qapp):
    panel = ResultsPanel()
    try:
        panel.set_result(_two_frame_motion_result())
        panel.show_solution_result(
            "CrackPattern",
            {
                "accumulate": False,
                "line_scale": 0.82,
                "_element_scope": [30],
            },
        )
        qapp.processEvents()

        assert panel.crack_detail_tabs.count() == 3
        assert [
            panel.crack_detail_tabs.tabText(index)
            for index in range(panel.crack_detail_tabs.count())
        ] == ["Overview", "Panels", "Evolution"]
        assert "Data health: READY" in panel.crack_health.text()
        assert "εcr=1/1" in panel.crack_health.text()
        assert "panel strain=1/1" in panel.crack_health.text()
        assert panel.crack_evolution_table.rowCount() == 2
        assert panel.crack_evolution_table.item(0, 4).text() == "Below εcr"
        assert panel.crack_evolution_table.item(1, 4).text() == "Cracked"

        panel._crack_evolution_row_clicked(0, 0)
        qapp.processEvents()
        assert panel._motion_frame_index == 0
        assert panel.crack_table.item(0, 5).text() == "Below εcr"

        panel._crack_evolution_row_clicked(1, 0)
        qapp.processEvents()
        assert panel._motion_frame_index == 1
        assert panel.crack_table.item(0, 5).text() == "Cracked"
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_crack_display_button_emits_current_frame(qapp):
    panel = ResultsPanel()
    captured = []
    panel.crack_frame_requested.connect(
        lambda frame, accumulate, line_scale, scope: captured.append(
            (int(frame), bool(accumulate), float(line_scale), list(scope))
        )
    )
    try:
        panel.set_result(_two_frame_motion_result())
        panel.show_solution_result(
            "CrackPattern",
            {
                "accumulate": False,
                "line_scale": 0.7,
                "_element_scope": [30],
            },
        )
        panel._set_motion_index(1)
        panel._display_current_crack_frame()
        qapp.processEvents()

        assert captured
        assert captured[-1][0] == 1
        assert captured[-1][1] is False
        assert captured[-1][2] == pytest.approx(0.7)
        assert captured[-1][3] == [30]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
