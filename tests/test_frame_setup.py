from openseespy_studio.frame_setup import (
    BEAM_TRANSFORMATION_NAME,
    BEAM_VECXZ,
    COLUMN_TRANSFORMATION_NAME,
    COLUMN_VECXZ,
    prepare_frame_grid,
)
from openseespy_studio.generator import FrameGridSpec, generate_frame_grid
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ProjectDatabase, TransformationData
from openseespy_studio.validation import validate_project


def test_prepare_frame_grid_creates_and_assigns_safe_defaults():
    project = ProjectDatabase(model=StructuralModel())
    spec = FrameGridSpec(nx=2, ny=2, nz=3)

    created = prepare_frame_grid(project, spec)
    generate_frame_grid(project.model, spec)

    assert len(created) == 2
    assert spec.column_transf_tag is not None
    assert spec.beam_transf_tag is not None

    column = project.transformations[spec.column_transf_tag]
    beam = project.transformations[spec.beam_transf_tag]
    assert column.name == COLUMN_TRANSFORMATION_NAME
    assert column.transformation_type == "PDelta"
    assert column.vecxz == COLUMN_VECXZ
    assert beam.name == BEAM_TRANSFORMATION_NAME
    assert beam.transformation_type == "Linear"
    assert beam.vecxz == BEAM_VECXZ

    for element in project.model.elements.values():
        if element.group == "column":
            assert element.transf_tag == column.tag
        else:
            assert element.transf_tag == beam.tag

    orientation_errors = [
        issue
        for issue in validate_project(project)
        if issue.category == "Transformation orientation"
        and issue.severity == "ERROR"
    ]
    assert orientation_errors == []


def test_prepare_frame_grid_reuses_existing_compatible_defaults():
    project = ProjectDatabase(model=StructuralModel())
    project.add_transformation(
        TransformationData(
            7,
            "My Column PDelta",
            "PDelta",
            COLUMN_VECXZ,
        )
    )
    project.add_transformation(
        TransformationData(
            9,
            "My Beam Linear",
            "Linear",
            BEAM_VECXZ,
        )
    )
    spec = FrameGridSpec(nx=1, ny=1, nz=1)

    created = prepare_frame_grid(project, spec)

    assert created == []
    assert spec.column_transf_tag == 7
    assert spec.beam_transf_tag == 9
    assert len(project.transformations) == 2


def test_prepare_frame_grid_preserves_explicit_assignments():
    project = ProjectDatabase(model=StructuralModel())
    project.add_transformation(
        TransformationData(
            3,
            "Explicit Columns",
            "Linear",
            (0.0, 1.0, 0.0),
        )
    )
    project.add_transformation(
        TransformationData(
            4,
            "Explicit Beams",
            "Corotational",
            (0.0, 0.0, 1.0),
        )
    )
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        column_transf_tag=3,
        beam_transf_tag=4,
    )

    created = prepare_frame_grid(project, spec)

    assert created == []
    assert spec.column_transf_tag == 3
    assert spec.beam_transf_tag == 4
    assert len(project.transformations) == 2


def test_prepare_frame_grid_rejects_missing_explicit_tag():
    project = ProjectDatabase(model=StructuralModel())
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        column_transf_tag=123,
    )

    try:
        prepare_frame_grid(project, spec)
    except ValueError as exc:
        assert "Column transformation 123 does not exist" in str(exc)
    else:
        raise AssertionError("Expected missing transformation tag to fail")


def test_disabled_member_family_does_not_create_unused_transformation():
    project = ProjectDatabase(model=StructuralModel())
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        create_columns=False,
        create_beams_x=True,
        create_beams_y=True,
    )

    created = prepare_frame_grid(project, spec)

    assert len(created) == 1
    assert spec.column_transf_tag is None
    assert spec.beam_transf_tag == created[0].tag
    assert created[0].name == BEAM_TRANSFORMATION_NAME
