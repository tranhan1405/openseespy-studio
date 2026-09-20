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
        assert "Grid size: 3 case(s)" in dialog.case_info.text()
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

        request = dialog.request()

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


def test_results_panel_calibration_table_links_ranked_case_to_job(qapp):
    panel = ResultsPanel()
    captured: list[int] = []
    panel.job_selected.connect(captured.append)
    rows = [
        {
            "rank": 1,
            "job_id": 12,
            "case_id": 2,
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
        assert panel.calibration_table.item(0, 2).text() == "4.5"
        assert "M1.fpc=" in panel.calibration_table.item(0, 7).text()
        assert "M2.Fy=" in panel.calibration_table.item(0, 7).text()

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
