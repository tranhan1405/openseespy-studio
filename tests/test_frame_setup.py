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



def test_generate_planar_2d_frame_counts_and_restraints():
    project = ProjectDatabase(model=StructuralModel())
    spec = FrameGridSpec(
        nx=2,
        nz=2,
        dx=5.0,
        dz=3.0,
        planar_2d=True,
        planar_base_support="Fixed",
    )

    prepare_frame_grid(project, spec)
    generate_frame_grid(project.model, spec)

    assert len(project.model.nodes) == 9
    assert len(project.model.elements) == 10
    assert all(
        abs(node.xyz[1]) <= 1.0e-12
        for node in project.model.nodes.values()
    )

    base = [
        node
        for node in project.model.nodes.values()
        if abs(node.xyz[2]) <= 1.0e-12
    ]
    upper = [
        node
        for node in project.model.nodes.values()
        if node.xyz[2] > 1.0e-12
    ]
    assert all(node.fixity == (1, 1, 1, 1, 1, 1) for node in base)
    assert all(node.fixity == (0, 1, 0, 1, 0, 1) for node in upper)

    groups = [element.group for element in project.model.elements.values()]
    assert groups.count("column-2d") == 6
    assert groups.count("beam-2d") == 4

    orientation_errors = [
        issue
        for issue in validate_project(project)
        if issue.category == "Transformation orientation"
        and issue.severity == "ERROR"
    ]
    assert orientation_errors == []


def test_generate_planar_2d_pinned_base_keeps_in_plane_rotation_free():
    project = ProjectDatabase(model=StructuralModel())
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        planar_base_support="Pinned",
    )

    prepare_frame_grid(project, spec)
    generate_frame_grid(project.model, spec)

    base = [
        node
        for node in project.model.nodes.values()
        if abs(node.xyz[2]) <= 1.0e-12
    ]
    assert len(base) == 2
    assert all(node.fixity == (1, 1, 1, 1, 0, 1) for node in base)


def test_planar_2d_does_not_generate_y_direction_beams():
    project = ProjectDatabase(model=StructuralModel())
    spec = FrameGridSpec(
        nx=3,
        ny=5,
        nz=1,
        planar_2d=True,
        create_beams_y=True,
    )

    prepare_frame_grid(project, spec)
    generate_frame_grid(project.model, spec)

    assert all(
        abs(project.model.nodes[element.i].xyz[1]) <= 1.0e-12
        and abs(project.model.nodes[element.j].xyz[1]) <= 1.0e-12
        for element in project.model.elements.values()
    )
    assert not any(
        element.group == "beam-y"
        for element in project.model.elements.values()
    )
