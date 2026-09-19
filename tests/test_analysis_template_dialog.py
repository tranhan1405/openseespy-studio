from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    LoadPatternData,
    PrescribedDisplacementData,
    ProjectDatabase,
    TimeSeriesData,
)
from openseespy_studio.ui.analysis_dialog import AnalysisDialog
from openseespy_studio.ui.analysis_template_dialog import AnalysisTemplateDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize(
    ("template_name", "page_index"),
    [
        ("Modal", 3),
        ("Pushover", 0),
        ("Cyclic", 1),
        ("Nonlinear Time History", 2),
    ],
)
def test_analysis_template_dialog_opens_for_every_template(
    qapp,
    template_name: str,
    page_index: int,
):
    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template=template_name,
    )
    try:
        assert dialog.windowTitle() == "Analysis Template"
        assert dialog.template.currentText() == template_name
        assert dialog.pages.currentIndex() == page_index
        assert dialog.summary.text().strip()
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_analysis_settings_dialog_can_shrink_and_scroll(qapp):
    dialog = AnalysisDialog(next_tag=1, default_node=1)
    try:
        dialog.show()
        qapp.processEvents()
        dialog.resize(420, 320)
        qapp.processEvents()

        assert dialog.height() <= 340
        assert dialog.scroll.widgetResizable() is True
        assert dialog.scroll.verticalScrollBar().maximum() > 0
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize(
    "template_name",
    ["Modal", "Pushover", "Cyclic", "Nonlinear Time History"],
)
def test_analysis_template_dialog_can_shrink_and_scroll(
    qapp,
    template_name: str,
):
    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template=template_name,
    )
    try:
        dialog.show()
        qapp.processEvents()
        dialog.resize(460, 340)
        qapp.processEvents()

        assert dialog.height() <= 360
        assert dialog.scroll.widgetResizable() is True
        assert dialog.scroll.verticalScrollBar().maximum() > 0
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_pushover_dialog_converts_roof_drift_to_displacement(qapp):
    model = StructuralModel("2d-pushover", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0, 0.0)
    model.add_node(3, 0.0, 6.0, 0.0)
    model.set_fixity(1, (1, 1, 1))
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=3,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Pushover",
        project=project,
    )
    try:
        dialog.push_target_mode.setCurrentText("Roof drift ratio")
        dialog.push_height_axis.setCurrentIndex(
            dialog.push_height_axis.findData(2)
        )
        dialog.push_drift.setValue(2.0)
        qapp.processEvents()

        request = dialog.request()
        assert request["target_mode"] == "Roof drift ratio"
        assert request["height_axis"] == 2
        assert request["reference_height"] == pytest.approx(6.0)
        assert request["target_displacement"] == pytest.approx(0.12)
        assert "2% drift" in dialog.summary.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_cyclic_dialog_2d_uses_translational_directions_and_drift(qapp):
    model = StructuralModel("cyclic-dialog-2d", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0, 0.0)
    model.add_node(3, 0.0, 6.0, 0.0)
    model.set_fixity(1, (1, 1, 1))
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=3,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Cyclic",
        project=project,
    )
    try:
        assert [
            dialog.direction.itemData(index)
            for index in range(dialog.direction.count())
        ] == [1, 2]

        dialog.cyclic_protocol_unit.setCurrentText("Drift ratio [%]")
        dialog.cyclic_height_axis.setCurrentIndex(
            dialog.cyclic_height_axis.findData(2)
        )
        dialog.protocol.setItem(0, 0, QTableWidgetItem("1.0"))
        dialog.protocol.setItem(0, 1, QTableWidgetItem("1"))
        dialog.protocol.setRowCount(1)
        qapp.processEvents()

        request = dialog.request()
        assert request["control_mode"] == "Displacement"
        assert request["reference_height"] == pytest.approx(6.0)
        assert request["raw_protocol_targets"] == pytest.approx(
            [1.0, -1.0, 0.0]
        )
        assert request["protocol_targets"] == pytest.approx(
            [0.06, -0.06, 0.0]
        )
        assert "displacement-controlled" in dialog.summary.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_cyclic_dialog_absolute_targets_preserve_asymmetry(qapp):
    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Cyclic",
    )
    try:
        dialog.cyclic_protocol_mode.setCurrentIndex(
            dialog.cyclic_protocol_mode.findData("absolute_targets")
        )
        dialog.protocol.setRowCount(4)
        for row, value in enumerate((0.005, -0.003, 0.010, 0.0)):
            dialog.protocol.setItem(
                row, 0, QTableWidgetItem(str(value))
            )
        qapp.processEvents()

        request = dialog.request()
        assert request["protocol_targets"] == pytest.approx(
            [0.005, -0.003, 0.010, 0.0]
        )
        assert request["protocol_mode"] == "absolute_targets"
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_templates_exclude_prescribed_displacement_driver_patterns(qapp):
    model = StructuralModel("template-driver-filter")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0, 0.0)
    project = ProjectDatabase(model=model)
    project.add_time_series(TimeSeriesData(1, "Linear", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Settlement", "Plain", 1)
    )
    project.add_load_pattern(
        LoadPatternData(2, "Lateral force shape", "Plain", 1)
    )
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            1,
            "Move support",
            1,
            2,
            1,
            0.01,
        )
    )

    dialog = AnalysisTemplateDialog(
        default_node=2,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Pushover",
        project=project,
    )
    try:
        push_tags = [
            dialog.push_load_source.itemData(index)
            for index in range(dialog.push_load_source.count())
        ]
        cyclic_tags = [
            dialog.cyclic_load_source.itemData(index)
            for index in range(dialog.cyclic_load_source.count())
        ]
        assert 1 not in push_tags
        assert 1 not in cyclic_tags
        assert 2 in push_tags
        assert 2 in cyclic_tags
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_nlth_dialog_2d_only_offers_xy_ground_motion_components(qapp):
    model = StructuralModel("nlth-dialog-2d", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0, 0.0)
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=2,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Nonlinear Time History",
        project=project,
    )
    try:
        assert dialog._nlth_directions == (1, 2)
        assert set(dialog.gm_files) == {1, 2}
        assert 3 not in dialog.gm_files
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_nlth_dialog_common_pga_scaling_preserves_component_ratio(qapp):
    model = StructuralModel("nlth-dialog-3d")
    model.add_node(1, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Nonlinear Time History",
        project=project,
    )
    try:
        dialog._ground_motion_values[1] = [0.0, 0.5, -0.5]
        dialog._ground_motion_values[2] = [0.0, 0.2, -0.2]
        dialog.gm_unit.setCurrentText("g")
        dialog.gm_scale_mode.setCurrentIndex(
            dialog.gm_scale_mode.findData("target_common_pga")
        )
        dialog.gm_target_pga.setValue(0.4)
        dialog._apply_target_pga_scaling()
        qapp.processEvents()

        assert dialog.gm_scales[1].value() == pytest.approx(0.8)
        assert dialog.gm_scales[2].value() == pytest.approx(0.8)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_nlth_dialog_requests_mass_gravity_and_optional_damping(qapp):
    model = StructuralModel("nlth-dialog-settings")
    model.add_node(1, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Nonlinear Time History",
        project=project,
    )
    try:
        dialog._ground_motion_values[1] = [0.0, 0.1, 0.0]
        dialog.nlth_preload_gravity.setChecked(False)
        dialog.nlth_gravity_steps.setValue(20)
        dialog.nlth_require_mass.setChecked(True)
        dialog.nlth_use_damping.setChecked(False)
        request = dialog.request()

        assert request["preload_gravity"] is False
        assert request["gravity_steps"] == 20
        assert request["require_nodal_mass"] is True
        assert request["damping_ratio"] == 0.0
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_nlth_bundled_el_centro_can_create_request_without_browse(qapp):
    model = StructuralModel("nlth-bundled")
    model.add_node(1, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Nonlinear Time History",
        project=project,
    )
    try:
        index = dialog.gm_library.findData("el-centro-1940")
        assert index >= 0
        dialog.gm_library.setCurrentIndex(index)
        qapp.processEvents()

        assert len(dialog._ground_motion_values[1]) == 1559
        assert dialog.gm_dt.value() == pytest.approx(0.02)
        assert dialog.gm_unit.currentText() == "g"
        assert dialog.gm_files[1].text().startswith("[Built-in]")
        request = dialog.request()
        assert len(request["components"]) == 1
        assert request["components"][0]["direction"] == 1
        assert len(request["components"][0]["values"]) == 1559
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_nlth_reference_only_preset_clears_previous_auto_record(qapp):
    model = StructuralModel("nlth-reference-only")
    model.add_node(1, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)

    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template="Nonlinear Time History",
        project=project,
    )
    try:
        dialog.gm_library.setCurrentIndex(
            dialog.gm_library.findData("el-centro-1940")
        )
        qapp.processEvents()
        assert dialog._ground_motion_values[1]

        dialog.gm_library.setCurrentIndex(
            dialog.gm_library.findData("kobe-1995-kjma")
        )
        qapp.processEvents()
        assert not dialog._ground_motion_values[1]
        assert "Reference only" in dialog.gm_library_info.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
