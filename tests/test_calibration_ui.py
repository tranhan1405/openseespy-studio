from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidget

from openseespy_studio.project import MaterialData, ProjectDatabase
from openseespy_studio.ui.calibration_dialog import (
    ApplyCalibrationCaseDialog,
    CalibrationDialog,
)
from openseespy_studio.ui.results_panel import ResultsPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _project_with_material() -> ProjectDatabase:
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            tag=1,
            name="Concrete",
            material_type="Concrete02",
            parameters={"fpc": -30.0e6},
        )
    )
    return project


def test_calibration_dialog_builds_material_parameter_grid(qapp):
    dialog = CalibrationDialog(_project_with_material())
    try:
        enabled = dialog.parameter_table.cellWidget(0, 0)
        material = dialog.parameter_table.cellWidget(0, 1)
        parameter = dialog.parameter_table.cellWidget(0, 2)

        assert enabled.isChecked()
        assert material.currentData() == 1
        assert parameter.findData("fpc") >= 0
        assert dialog.strategy.currentData() == "adaptive"
        assert "Adaptive: 3 case(s)/round × 3 rounds" in (
            dialog.case_info.text()
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_calibration_dialog_request_extracts_experimental_reference(qapp):
    dialog = CalibrationDialog(_project_with_material())
    try:
        dialog._dataset = {
            "headers": ["Displacement", "Force"],
            "rows": [
                [0.0, 0.0],
                [2.0, 20.0],
                [0.0, 0.0],
                [-2.0, -18.0],
            ],
            "delimiter": ",",
            "skipped_rows": 0,
        }
        dialog._dataset_path = "/tmp/experiment.csv"
        dialog.exp_x.addItem("Displacement", 0)
        dialog.exp_x.addItem("Force", 1)
        dialog.exp_y.addItem("Displacement", 0)
        dialog.exp_y.addItem("Force", 1)
        dialog.exp_x.setCurrentIndex(0)
        dialog.exp_y.setCurrentIndex(1)
        dialog.strategy.setCurrentIndex(
            dialog.strategy.findData("grid")
        )

        request = dialog.request()

        assert request["strategy"] == "grid"
        assert len(request["cases"]) == 3
        assert request["experiment_x"] == pytest.approx(
            [0.0, 2.0, 0.0, -2.0]
        )
        assert request["experiment_y"] == pytest.approx(
            [0.0, 20.0, 0.0, -18.0]
        )
        assert request["weights"].peak_force == pytest.approx(1.0)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_calibration_dialog_adaptive_request_reports_round_controls(qapp):
    dialog = CalibrationDialog(_project_with_material())
    try:
        dialog._dataset = {
            "headers": ["Displacement", "Force"],
            "rows": [
                [0.0, 0.0],
                [2.0, 20.0],
                [0.0, 0.0],
                [-2.0, -18.0],
            ],
            "delimiter": ",",
            "skipped_rows": 0,
        }
        dialog._dataset_path = "/tmp/experiment.csv"
        dialog.exp_x.addItem("Displacement", 0)
        dialog.exp_y.addItem("Force", 1)
        dialog.adaptive_rounds.setValue(3)
        dialog.adaptive_shrink.setValue(0.5)

        request = dialog.request()

        assert request["strategy"] == "adaptive"
        assert request["cases"] == []
        assert len(request["parameters"]) == 1
        assert request["adaptive_rounds"] == 3
        assert request["adaptive_shrink_ratio"] == pytest.approx(0.5)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_results_panel_calibration_table_links_ranked_case_to_job(qapp):
    panel = ResultsPanel()
    captured: list[int] = []
    panel.job_selected.connect(captured.append)
    rows = [
        {
            "rank": 1,
            "job_id": 12,
            "case_id": 2,
            "round": 2,
            "round_case": 3,
            "score": 4.5,
            "components": {
                "peak_force": 3.0,
                "reversal_nrmse": 4.0,
                "cycle_energy": 6.5,
            },
            "matched_reversal_count": 8,
            "values": {
                "material:1:fpc": -32.0e6,
                "material:2:Fy": 500.0e6,
            },
            "status": "Scored",
        }
    ]
    try:
        panel.set_calibration_results(rows)
        panel.show_calibration()
        qapp.processEvents()

        assert panel.tabs.tabText(panel.tabs.currentIndex()) == "Calibration"
        assert panel.calibration_table.rowCount() == 1
        assert panel.calibration_table.item(0, 0).text() == "1"
        assert panel.calibration_table.item(0, 1).text() == "12"
        assert panel.calibration_table.item(0, 2).text() == "2"
        assert panel.calibration_table.item(0, 3).text() == "4.5"
        assert "M1.fpc=" in panel.calibration_table.item(0, 8).text()
        assert "M2.Fy=" in panel.calibration_table.item(0, 8).text()

        panel._calibration_row_activated(0, 0)
        assert captured == [12]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()



def test_results_panel_apply_selected_emits_only_scored_case(qapp):
    panel = ResultsPanel()
    captured: list[dict] = []
    panel.calibration_case_apply_requested.connect(captured.append)
    try:
        panel.set_calibration_results([
            {
                "rank": 1,
                "job_id": 21,
                "case_id": 4,
                "score": 2.5,
                "components": {},
                "matched_reversal_count": 5,
                "values": {"material:1:fpc": -31.0e6},
                "status": "Scored",
            },
            {
                "rank": None,
                "job_id": 22,
                "case_id": 5,
                "score": None,
                "components": {},
                "matched_reversal_count": 0,
                "values": {"material:1:fpc": -35.0e6},
                "status": "Failed",
            },
        ])

        panel.calibration_table.selectRow(0)
        qapp.processEvents()
        assert panel.calibration_apply.isEnabled()
        panel._request_apply_calibration_case()
        assert len(captured) == 1
        assert captured[0]["case_id"] == 4

        panel.calibration_table.selectRow(1)
        qapp.processEvents()
        assert not panel.calibration_apply.isEnabled()
        panel._request_apply_calibration_case()
        assert len(captured) == 1
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_apply_calibration_case_dialog_displays_old_and_new_values(qapp):
    dialog = ApplyCalibrationCaseDialog(
        [
            {
                "material_tag": 1,
                "material_name": "Concrete",
                "material_type": "Concrete02",
                "parameter": "fpc",
                "old_value": -30.0e6,
                "new_value": -33.0e6,
                "changed": True,
            }
        ],
        case_id=2,
        rank=1,
        score=3.25,
    )
    try:
        tables = dialog.findChildren(QTableWidget)
        assert len(tables) == 1
        table = tables[0]
        assert table.rowCount() == 1
        assert table.item(0, 0).text() == "[1] Concrete"
        assert table.item(0, 2).text() == "fpc"
        assert float(table.item(0, 4).text()) == pytest.approx(-33.0e6)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_results_panel_calibration_history_plots_best_score_and_parameter_path(
    qapp,
):
    panel = ResultsPanel()
    rows = [
        {
            "rank": 3,
            "job_id": 31,
            "case_id": 1,
            "round": 1,
            "round_case": 1,
            "score": 10.0,
            "components": {},
            "matched_reversal_count": 4,
            "values": {
                "material:1:Fy": 450.0,
                "material:2:fpc": -30.0,
            },
            "status": "Scored",
        },
        {
            "rank": 2,
            "job_id": 32,
            "case_id": 2,
            "round": 2,
            "round_case": 1,
            "score": 6.0,
            "components": {},
            "matched_reversal_count": 4,
            "values": {
                "material:1:Fy": 500.0,
                "material:2:fpc": -32.0,
            },
            "status": "Scored",
        },
        {
            "rank": 1,
            "job_id": 33,
            "case_id": 3,
            "round": 3,
            "round_case": 1,
            "score": 4.0,
            "components": {},
            "matched_reversal_count": 4,
            "values": {
                "material:1:Fy": 525.0,
                "material:2:fpc": -33.0,
            },
            "status": "Scored",
        },
    ]
    try:
        panel.set_calibration_results(rows)
        qapp.processEvents()

        assert panel.calibration_score_plot._x == pytest.approx(
            [1.0, 2.0, 3.0]
        )
        assert panel.calibration_score_plot._y == pytest.approx(
            [10.0, 6.0, 4.0]
        )
        assert "best 4%" in panel.calibration_score_info.text()

        fy_index = panel.calibration_parameter_combo.findData(
            "material:1:Fy"
        )
        assert fy_index >= 0
        panel.calibration_parameter_combo.setCurrentIndex(fy_index)
        qapp.processEvents()

        assert panel.calibration_parameter_plot._x == pytest.approx(
            [1.0, 2.0, 3.0]
        )
        assert panel.calibration_parameter_plot._y == pytest.approx(
            [450.0, 500.0, 525.0]
        )
        assert "M1.Fy round-best trajectory" in (
            panel.calibration_parameter_info.text()
        )
        assert "R3 C3: 525" in panel.calibration_parameter_info.text()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()



def test_results_panel_pareto_tab_builds_front_projection(qapp):
    panel = ResultsPanel()
    rows = [
        {
            "rank": 1,
            "job_id": 41,
            "case_id": 1,
            "round": 1,
            "score": 4.0,
            "components": {
                "peak_force": 2.0,
                "reversal_nrmse": 9.0,
                "cycle_energy": 7.0,
                "max_displacement": 1.0,
            },
            "matched_reversal_count": 5,
            "values": {"material:1:Fy": 450.0},
            "pareto_rank": 1,
            "pareto_front": True,
            "pareto_eligible": True,
            "pareto_objectives": [
                "peak_force",
                "reversal_nrmse",
                "cycle_energy",
            ],
            "status": "Scored",
        },
        {
            "rank": 2,
            "job_id": 42,
            "case_id": 2,
            "round": 1,
            "score": 5.0,
            "components": {
                "peak_force": 4.0,
                "reversal_nrmse": 4.0,
                "cycle_energy": 4.0,
                "max_displacement": 2.0,
            },
            "matched_reversal_count": 5,
            "values": {"material:1:Fy": 500.0},
            "pareto_rank": 1,
            "pareto_front": True,
            "pareto_eligible": True,
            "pareto_objectives": [
                "peak_force",
                "reversal_nrmse",
                "cycle_energy",
            ],
            "status": "Scored",
        },
        {
            "rank": 3,
            "job_id": 43,
            "case_id": 3,
            "round": 1,
            "score": 9.0,
            "components": {
                "peak_force": 8.0,
                "reversal_nrmse": 8.0,
                "cycle_energy": 8.0,
                "max_displacement": 3.0,
            },
            "matched_reversal_count": 5,
            "values": {"material:1:Fy": 550.0},
            "pareto_rank": 2,
            "pareto_front": False,
            "pareto_eligible": True,
            "pareto_objectives": [
                "peak_force",
                "reversal_nrmse",
                "cycle_energy",
            ],
            "status": "Scored",
        },
    ]
    selected: list[int] = []
    panel.job_selected.connect(selected.append)
    try:
        panel.set_calibration_results(rows)
        qapp.processEvents()

        assert panel.calibration_table.columnCount() == 11
        assert panel.calibration_table.item(0, 9).text() == "P1"
        assert panel.calibration_table.item(2, 9).text() == "P2"

        assert panel.calibration_pareto_x.findData("peak_force") >= 0
        assert panel.calibration_pareto_y.findData("cycle_energy") >= 0
        assert len(panel.calibration_pareto_plot._points) == 3
        assert sum(
            bool(point["global_pareto_front"])
            for point in panel.calibration_pareto_plot._points
        ) == 2
        assert "global P1: 2" in panel.calibration_pareto_info.text()
        assert "Global Pareto objectives:" in (
            panel.calibration_pareto_info.text()
        )

        panel._calibration_pareto_job_selected(42)
        qapp.processEvents()
        assert selected == [42]
        assert panel.calibration_table.currentRow() == 1
        assert panel.calibration_pareto_plot._selected_job_id == 42
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
