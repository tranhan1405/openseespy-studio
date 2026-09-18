from openseespy_studio.generator import FrameGridSpec, generate_frame_grid
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    LoadPatternData,
    ProjectDatabase,
    SectionData,
    TimeSeriesData,
    TransformationData,
)
from openseespy_studio.validation import validate_project


def _elastic_section(tag=1):
    return SectionData(
        tag=tag,
        name="Elastic",
        section_type="Elastic",
    )


def _frame_project(*, beam_vec=(0.0, 0.0, 1.0)):
    model = StructuralModel()
    generate_frame_grid(
        model,
        FrameGridSpec(
            nx=2,
            ny=2,
            nz=3,
            column_section_tag=1,
            beam_section_tag=1,
            column_transf_tag=1,
            beam_transf_tag=2,
        ),
    )
    project = ProjectDatabase(model=model)
    project.sections[1] = _elastic_section()
    project.transformations[1] = TransformationData(
        1,
        "Column",
        "Linear",
        (1.0, 0.0, 0.0),
    )
    project.transformations[2] = TransformationData(
        2,
        "Beam",
        "Linear",
        beam_vec,
    )
    return project


def test_valid_building_frame_passes_static_model_check():
    project = _frame_project()
    analysis = AnalysisSettingsData(1, "Static", "Static")

    issues = validate_project(project, analysis)

    assert issues == []


def test_bad_beam_transformation_finds_first_y_beam_element_46():
    project = _frame_project(beam_vec=(0.0, 1.0, 0.0))
    analysis = AnalysisSettingsData(1, "Static", "Static")

    issues = validate_project(project, analysis)
    orientation_errors = [
        issue
        for issue in issues
        if issue.category == "Transformation orientation"
        and issue.severity == "ERROR"
    ]

    assert orientation_errors
    assert orientation_errors[0].entity_kind == "element"
    assert orientation_errors[0].entity_tag == 46
    assert "Suggested vecxz: (0, 0, 1)" in orientation_errors[0].suggestion


def test_missing_section_and_transformation_are_errors():
    model = StructuralModel()
    generate_frame_grid(model, FrameGridSpec(nx=1, ny=1, nz=1))
    project = ProjectDatabase(model=model)

    issues = validate_project(
        project,
        AnalysisSettingsData(1, "Static", "Static"),
    )

    categories = {
        issue.category
        for issue in issues
        if issue.severity == "ERROR"
    }
    assert "Section" in categories
    assert "Transformation" in categories


def test_zero_length_and_duplicate_geometry_are_detected():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 0.0)
    model.add_node(3, 1.0, 0.0, 0.0)
    model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    model.add_element(1, 1, 2, section_tag=1, transf_tag=1)
    model.add_element(2, 1, 3, section_tag=1, transf_tag=1)
    model.add_element(3, 3, 1, section_tag=1, transf_tag=1)
    project = ProjectDatabase(model=model)
    project.sections[1] = _elastic_section()
    project.transformations[1] = TransformationData(
        1,
        "Frame",
        "Linear",
        (0.0, 0.0, 1.0),
    )

    issues = validate_project(project)

    assert any(
        issue.severity == "ERROR"
        and "zero or near-zero length" in issue.message
        for issue in issues
    )
    assert any(
        issue.severity == "WARNING"
        and "duplicates the node pair" in issue.message
        for issue in issues
    )


def test_unsupported_element_formulation_blocks_run():
    project = _frame_project()
    project.model.elements[1].element_type = "forceBeamColumn"

    issues = validate_project(project)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Element formulation"
        and issue.entity_tag == 1
        for issue in issues
    )


def test_dynamic_analysis_requires_positive_translational_mass():
    project = _frame_project()
    analysis = AnalysisSettingsData(1, "EQ", "Transient")

    issues = validate_project(project, analysis)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Mass"
        for issue in issues
    )

    for tag, node in project.model.nodes.items():
        if not all(node.fixity[:3]):
            project.model.set_mass(
                tag,
                (1.0, 1.0, 1.0, 0.0, 0.0, 0.0),
            )

    issues = validate_project(project, analysis)
    assert not any(
        issue.severity == "ERROR"
        and issue.category == "Mass"
        for issue in issues
    )


def test_uniform_excitation_missing_time_series_is_error():
    project = _frame_project()
    for tag, node in project.model.nodes.items():
        if not all(node.fixity[:3]):
            project.model.set_mass(
                tag,
                (1.0, 1.0, 1.0, 0.0, 0.0, 0.0),
            )
    project.load_patterns[1] = LoadPatternData(
        1,
        "EQ-X",
        "UniformExcitation",
        99,
        direction=1,
    )

    issues = validate_project(
        project,
        AnalysisSettingsData(1, "EQ", "Transient"),
    )

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Ground motion"
        and "missing time series 99" in issue.message
        for issue in issues
    )


def test_no_support_is_obvious_stability_error():
    project = _frame_project()
    for node in project.model.nodes.values():
        node.fixity = (0, 0, 0, 0, 0, 0)

    issues = validate_project(project)

    assert any(
        issue.severity == "ERROR"
        and issue.category == "Stability"
        and "no restrained/support node" in issue.message
        for issue in issues
    )
