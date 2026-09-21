from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    LoadPatternData,
    ElementLoadData,
    NodalLoadData,
    ProjectDatabase,
    TimeSeriesData,
)
from openseespy_studio.validation import validate_project


def _project():
    model = StructuralModel("driver-check", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0)
    model.set_fixity(1, (1, 1, 1))
    return ProjectDatabase(model=model)


def test_pushover_without_driving_pattern_is_blocked():
    project = _project()
    analysis = AnalysisSettingsData(
        1,
        "Push",
        "Pushover",
        control_node=2,
        control_dof=1,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Driving load"
        and "no driving/reference load pattern" in issue.message
        for issue in issues
    )


def test_pushover_with_nonzero_plain_driver_passes_driving_check():
    project = _project()
    project.add_time_series(
        TimeSeriesData(1, "Reference", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Lateral",
            "Plain",
            time_series_tag=1,
        )
    )
    project.add_nodal_load(
        NodalLoadData(
            1,
            "Reference force",
            1,
            2,
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "Push",
        "Pushover",
        control_node=2,
        control_dof=1,
        deferred_pattern_tags=[1],
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.category == "Driving load"
        and issue.severity == "ERROR"
        for issue in issues
    )


def test_displacement_control_missing_control_node_is_blocked():
    project = _project()
    analysis = AnalysisSettingsData(
        1,
        "Push",
        "Pushover",
        control_node=99,
        control_dof=1,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Analysis control"
        and "missing control node 99" in issue.message
        for issue in issues
    )


def test_displacement_control_fixed_control_dof_is_blocked():
    project = _project()
    analysis = AnalysisSettingsData(
        1,
        "Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=1,
        control_dof=1,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Analysis control"
        and "is restrained" in issue.message
        for issue in issues
    )


def test_displacement_control_unavailable_dof_is_blocked():
    project = _project()
    analysis = AnalysisSettingsData(
        1,
        "Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=4,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Analysis control"
        and "ndf=3" in issue.message
        for issue in issues
    )


def test_displacement_control_free_control_dof_has_no_control_error():
    project = _project()
    analysis = AnalysisSettingsData(
        1,
        "Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=1,
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.category == "Analysis control"
        and issue.severity == "ERROR"
        for issue in issues
    )


def test_static_displacement_control_without_force_reference_is_blocked():
    project = _project()
    analysis = AnalysisSettingsData(
        1,
        "Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=1,
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Driving load"
        and "no nonzero driving/reference force pattern" in issue.message
        for issue in issues
    )


def test_legacy_static_displacement_control_can_use_existing_plain_force():
    project = _project()
    project.add_time_series(
        TimeSeriesData(1, "Reference", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(1, "Reference", "Plain", time_series_tag=1)
    )
    project.add_nodal_load(
        NodalLoadData(
            1,
            "Reference force",
            1,
            2,
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "Legacy Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=1,
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.severity == "ERROR"
        and issue.category == "Driving load"
        for issue in issues
    )
    assert any(
        issue.severity == "WARNING"
        and issue.category == "Driving load"
        and "unscoped" in issue.message
        for issue in issues
    )


def test_zero_element_load_does_not_count_as_displacement_control_driver():
    project = _project()
    project.model.add_element(
        1,
        1,
        2,
        element_type="truss",
        truss_area=1.0,
        truss_material_tag=1,
    )
    project.add_time_series(
        TimeSeriesData(1, "Reference", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(1, "Zero reference", "Plain", time_series_tag=1)
    )
    project.add_element_load(
        ElementLoadData(
            1,
            "Zero load",
            1,
            1,
            "Uniform",
            wx=0.0,
            wy=0.0,
            wz=0.0,
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=1,
        deferred_pattern_tags=[1],
    )

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Driving load"
        and "no nonzero reference force" in issue.message
        for issue in issues
    )


def test_misaligned_nodal_driver_warns_but_does_not_block_coupled_model():
    project = _project()
    project.add_time_series(
        TimeSeriesData(1, "Reference", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(1, "Reference", "Plain", time_series_tag=1)
    )
    project.add_nodal_load(
        NodalLoadData(
            1,
            "Y reference force",
            1,
            2,
            (0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    analysis = AnalysisSettingsData(
        1,
        "Static DC",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=1,
        deferred_pattern_tags=[1],
    )

    issues = validate_project(project, analysis)

    assert not any(
        issue.severity == "ERROR"
        and issue.category == "Driving load"
        for issue in issues
    )
    assert any(
        issue.severity == "WARNING"
        and issue.category == "Driving load"
        and "no direct nodal force in control DOF 1" in issue.message
        for issue in issues
    )
