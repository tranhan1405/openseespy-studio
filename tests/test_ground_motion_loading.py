import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    LoadPatternData,
    ProjectDatabase,
    TimeSeriesData,
)
from openseespy_studio.ui.load_dialogs import GroundMotionDialog
from openseespy_studio.validation import validate_project


def test_ground_motion_dialog_builds_path_and_uniform_excitation_pair():
    app = QApplication.instance() or QApplication([])
    dialog = GroundMotionDialog(
        next_series_tag=4,
        next_pattern_tag=7,
        units={"length": "m", "force": "N", "time": "s"},
    )
    dialog.name.setText("EQ X")
    dialog.direction.setCurrentIndex(
        dialog.direction.findData(1)
    )
    dialog.dt.setValue(0.02)
    dialog.scale.setValue(1.5)
    dialog.values.setPlainText("0.0, 0.1\n-0.2")

    series, pattern = dialog.data()

    assert series.tag == 4
    assert series.series_type == "Path"
    assert series.dt == 0.02
    assert series.factor == 1.5
    assert series.values == [0.0, 0.1, -0.2]
    assert pattern.tag == 7
    assert pattern.pattern_type == "UniformExcitation"
    assert pattern.time_series_tag == 4
    assert pattern.direction == 1
    assert pattern.factor == 1.0


def test_ground_motion_editor_combines_existing_series_and_pattern_scale():
    app = QApplication.instance() or QApplication([])
    series = TimeSeriesData(
        2,
        "Record",
        "Path",
        factor=2.0,
        dt=0.01,
        values=[0.0, 1.0],
    )
    pattern = LoadPatternData(
        3,
        "Imported EQ",
        "UniformExcitation",
        time_series_tag=2,
        direction=2,
        factor=0.5,
    )

    dialog = GroundMotionDialog(
        series=series,
        pattern=pattern,
        units={"length": "m", "force": "N", "time": "s"},
    )
    updated_series, updated_pattern = dialog.data()

    assert updated_series.factor == 1.0
    assert updated_pattern.factor == 1.0
    assert updated_pattern.direction == 2
    assert not dialog.series_tag.isEnabled()
    assert not dialog.pattern_tag.isEnabled()


def test_validation_rejects_uniform_excitation_without_path_series():
    model = StructuralModel("dynamic", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))
    model.nodes[2].mass = (1.0, 1.0)

    project = ProjectDatabase(model=model)
    project.add_time_series(
        TimeSeriesData(1, "Wrong", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "EQ",
            "UniformExcitation",
            time_series_tag=1,
            direction=1,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "NLTH",
        "Transient",
        steps=2,
        dt=0.01,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Ground motion"
        and "must use a Path time series" in issue.message
        for issue in issues
    )


def test_validation_rejects_ground_motion_direction_beyond_model_ndm():
    model = StructuralModel("dynamic", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))
    model.nodes[2].mass = (1.0, 1.0)

    project = ProjectDatabase(model=model)
    project.add_time_series(
        TimeSeriesData(
            1,
            "Record",
            "Path",
            dt=0.01,
            values=[0.0, 0.1],
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "EQ Z",
            "UniformExcitation",
            time_series_tag=1,
            direction=3,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "NLTH",
        "Transient",
        steps=2,
        dt=0.01,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and "model has ndm=2" in issue.message
        for issue in issues
    )


def test_ground_motion_dialog_loads_bundled_el_centro_and_converts_to_model_units():
    app = QApplication.instance() or QApplication([])
    dialog = GroundMotionDialog(
        next_series_tag=10,
        next_pattern_tag=11,
        units={"length": "m", "force": "N", "time": "s"},
        initial_source="builtin",
    )
    try:
        index = dialog.library.findData("el-centro-1940")
        assert index >= 0
        dialog.library.setCurrentIndex(index)
        dialog._library_changed()

        raw_values = dialog._parsed_values()
        assert len(raw_values) == 1559
        assert dialog.dt.value() == 0.02
        assert dialog.input_unit.currentText() == "g"

        series, pattern = dialog.data()
        assert len(series.values) == 1559
        assert series.dt == 0.02
        assert pattern.pattern_type == "UniformExcitation"
        peak_raw = max(abs(value) for value in raw_values)
        peak_model = max(abs(value) for value in series.values)
        assert abs(peak_model - peak_raw * 9.80665) < 1.0e-8
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_ground_motion_dialog_converts_g_to_mm_per_s2_model_units():
    app = QApplication.instance() or QApplication([])
    dialog = GroundMotionDialog(
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        dialog.source_mode.setCurrentIndex(
            dialog.source_mode.findData("manual")
        )
        dialog.input_unit.setCurrentText("g")
        dialog.values.setPlainText("0.0 1.0 -0.5")
        series, _ = dialog.data()
        assert series.values == [0.0, 9806.65, -4903.325]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_ground_motion_dialog_library_is_offline_only_without_download_button():
    app = QApplication.instance() or QApplication([])
    dialog = GroundMotionDialog(
        units={"length": "m", "force": "N", "time": "s"},
        initial_source="builtin",
    )
    try:
        assert not hasattr(dialog, "library_download")
        assert dialog.library.findData("el-centro-1940") >= 0
        assert dialog.library.findData("northridge-1994-rinaldi") >= 0
        assert dialog.library.findData("northridge-1994-arleta-360") >= 0
        assert dialog.library.findData("chi-chi-1999-nsk-e") >= 0
        assert all(
            "[Offline]" in dialog.library.itemText(index)
            for index in range(dialog.library.count())
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_validation_rejects_rotational_uniform_excitation_in_2d_ndf3_model():
    model = StructuralModel("dynamic", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1, 1))
    model.nodes[2].mass = (1.0, 1.0, 0.0)

    project = ProjectDatabase(model=model)
    project.add_time_series(
        TimeSeriesData(
            1,
            "Record",
            "Path",
            dt=0.01,
            values=[0.0, 0.1],
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Bad rotational excitation",
            "UniformExcitation",
            time_series_tag=1,
            direction=3,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "NLTH",
        "Transient",
        steps=2,
        dt=0.01,
        deferred_pattern_tags=[1],
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Ground motion"
        and "ndm=2" in issue.message
        for issue in issues
    )


def test_transient_validation_ignores_stale_inactive_ground_motion():
    model = StructuralModel("dynamic", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))
    model.nodes[2].mass = (1.0, 1.0)

    project = ProjectDatabase(model=model)
    project.add_time_series(
        TimeSeriesData(
            1,
            "Current record",
            "Path",
            dt=0.01,
            values=[0.0, 0.1],
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Current EQ",
            "UniformExcitation",
            time_series_tag=1,
            direction=1,
        )
    )
    project.add_time_series(
        TimeSeriesData(2, "Stale wrong series", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(
            2,
            "Stale EQ",
            "UniformExcitation",
            time_series_tag=2,
            direction=1,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "Current NLTH",
        "Transient",
        steps=2,
        dt=0.01,
        deferred_pattern_tags=[1],
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.category == "Ground motion"
        and "pattern 2" in issue.message
        for issue in issues
    )
    assert not any(
        issue.category == "Ground motion"
        and issue.severity == "ERROR"
        for issue in issues
    )


def test_modal_validation_ignores_ground_motion_objects():
    model = StructuralModel("modal", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1, 1))
    model.nodes[2].mass = (1.0, 1.0, 0.0)

    project = ProjectDatabase(model=model)
    project.add_time_series(
        TimeSeriesData(1, "Wrong for EQ", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Unused EQ",
            "UniformExcitation",
            time_series_tag=1,
            direction=3,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "Modes",
        "Modal",
        num_modes=1,
    )

    issues = validate_project(project, analysis)

    assert not any(issue.category == "Ground motion" for issue in issues)


def test_transient_validation_reports_missing_owned_excitation_pattern():
    model = StructuralModel("dynamic", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))
    model.nodes[2].mass = (1.0, 1.0)

    project = ProjectDatabase(model=model)
    analysis = AnalysisSettingsData(
        1,
        "NLTH",
        "Transient",
        steps=2,
        dt=0.01,
        deferred_pattern_tags=[99],
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Ground motion"
        and "missing excitation pattern 99" in issue.message
        for issue in issues
    )


def _directional_mass_project(
    *,
    mass_x: float,
    mass_y: float,
    element_mass: float = 0.0,
):
    model = StructuralModel("directional-mass", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))
    model.nodes[2].mass = (mass_x, mass_y)
    if element_mass > 0.0:
        model.add_element(
            1,
            1,
            2,
            element_type="truss",
            truss_area=1.0,
            truss_material_tag=1,
            mass_per_length=element_mass,
        )

    project = ProjectDatabase(model=model)
    project.add_time_series(
        TimeSeriesData(
            1,
            "EQ",
            "Path",
            dt=0.01,
            values=[0.0, 0.1],
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "EQ X",
            "UniformExcitation",
            time_series_tag=1,
            direction=1,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "NLTH X",
        "Transient",
        steps=1,
        dt=0.01,
        deferred_pattern_tags=[1],
    )
    return project, analysis


def test_transient_requires_mass_in_active_excitation_direction():
    project, analysis = _directional_mass_project(
        mass_x=0.0,
        mass_y=1.0,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Mass"
        and "active in X" in issue.message
        for issue in issues
    )


def test_transient_accepts_nodal_mass_in_active_excitation_direction():
    project, analysis = _directional_mass_project(
        mass_x=1.0,
        mass_y=0.0,
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.severity == "ERROR"
        and issue.category == "Mass"
        for issue in issues
    )


def test_transient_accepts_positive_element_mass_for_active_direction():
    project, analysis = _directional_mass_project(
        mass_x=0.0,
        mass_y=0.0,
        element_mass=2.5,
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.severity == "ERROR"
        and issue.category == "Mass"
        for issue in issues
    )


def test_modal_accepts_positive_element_mass_without_nodal_mass():
    model = StructuralModel("modal-element-mass", ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.set_fixity(1, (1, 1))
    model.add_element(
        1,
        1,
        2,
        element_type="truss",
        truss_area=1.0,
        truss_material_tag=1,
        mass_per_length=1.0,
    )
    project = ProjectDatabase(model=model)
    analysis = AnalysisSettingsData(
        1,
        "Modes",
        "Modal",
        num_modes=1,
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.severity == "ERROR"
        and issue.category == "Mass"
        for issue in issues
    )
