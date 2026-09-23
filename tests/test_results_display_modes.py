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

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Nonlinear Response"
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
        assert panel.motion_counter.text() == "0 / 0"
        assert not panel.motion_play.isEnabled()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()

def test_specialized_cyclic_result_objects_focus_existing_views(qapp):
    panel = ResultsPanel()
    try:
        panel.show_solution_result("CyclicHysteresis")
        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Nonlinear Response"
        assert panel.cyclic_compare_view.currentData() == "hysteresis"
        assert panel.cyclic_detail_tabs.currentIndex() == 0

        panel.show_solution_result("CyclicBackbone")
        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Nonlinear Response"
        assert panel.cyclic_compare_view.currentData() == "backbone"
        assert panel.cyclic_detail_tabs.currentIndex() == 0

        panel.show_solution_result("CyclicReversalMetrics")
        assert panel.cyclic_compare_view.currentData() == "hysteresis"
        assert panel.cyclic_detail_tabs.tabText(
            panel.cyclic_detail_tabs.currentIndex()
        ) == "Reversals"

        panel.show_solution_result("CyclicCycleMetrics")
        assert panel.cyclic_detail_tabs.tabText(
            panel.cyclic_detail_tabs.currentIndex()
        ) == "Cycles"
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()



def test_linked_frame_bar_tracks_motion_and_graph_markers(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Transient"},
        "history": {
            "time": [0.0, 0.1, 0.2],
            "nodes": {
                "1": {
                    "disp": [
                        [0.0, 0.0, 0.0],
                        [0.1, 0.0, 0.0],
                        [0.2, 0.0, 0.0],
                    ],
                    "reaction": [
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [2.0, 0.0, 0.0],
                    ],
                }
            },
        },
        "final": {
            "node_displacements": {"1": [0.2, 0.0, 0.0]},
        },
        "convergence": {"steps": []},
        "modes": {},
    }
    captured: list[tuple[int, str]] = []
    panel.result_frame_requested.connect(
        lambda index, label: captured.append((int(index), str(label)))
    )
    try:
        panel.set_result(result)
        qapp.processEvents()

        assert panel.has_result_frames()
        assert not panel.frame_bar.isHidden()
        assert panel.current_frame_index() == 2
        assert panel.frame_slider.value() == 2
        assert panel.motion_slider.value() == 2

        panel._set_motion_index(1)
        qapp.processEvents()

        assert panel.current_frame_index() == 1
        assert panel.frame_slider.value() == 1
        assert panel.motion_slider.value() == 1
        assert panel.history_plot._marker_index == 1
        assert captured[-1][0] == 1
        assert "t = 0.1 s" in captured[-1][1]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()

def test_shared_frame_bar_exposes_synced_playback_speed(qapp):
    panel = ResultsPanel()
    try:
        assert panel.frame_speed.currentData() == pytest.approx(1.0)
        index = panel.frame_speed.findData(4.0)
        assert index >= 0
        panel.frame_speed.setCurrentIndex(index)
        qapp.processEvents()
        assert panel.motion_speed.currentData() == pytest.approx(4.0)

        index = panel.motion_speed.findData(0.5)
        assert index >= 0
        panel.motion_speed.setCurrentIndex(index)
        qapp.processEvents()
        assert panel.frame_speed.currentData() == pytest.approx(0.5)
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()

def test_linked_contour_frame_emit_skips_duplicate_motion_vectors(qapp):
    panel = ResultsPanel()
    result = {
        "analysis": {"type": "Transient"},
        "history": {
            "time": [0.0, 0.1],
            "nodes": {
                "1": {
                    "disp": [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0]],
                    "reaction": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                }
            },
        },
        "final": {"node_displacements": {"1": [0.1, 0.0, 0.0]}},
        "convergence": {"steps": []},
        "modes": {},
    }
    motion_calls = []
    result_calls = []
    panel.motion_frame_requested.connect(
        lambda *args: motion_calls.append(args)
    )
    panel.result_frame_requested.connect(
        lambda *args: result_calls.append(args)
    )
    try:
        panel.set_linked_contour_active(True)
        panel.set_result(result)
        panel._set_motion_index(1)
        qapp.processEvents()

        assert result_calls
        assert result_calls[-1][0] == 1
        assert not motion_calls
        assert "t = 0.1 s" in result_calls[-1][1]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()

