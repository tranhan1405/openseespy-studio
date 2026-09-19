from openseespy_studio.generator import (
    FrameGridSpec,
    generate_frame_grid,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import SectionData, TransformationData


def test_frame_grid_counts():
    model = StructuralModel()
    spec = FrameGridSpec(nx=2, ny=1, nz=2)
    generate_frame_grid(model, spec)

    assert len(model.nodes) == (2 + 1) * (1 + 1) * (2 + 1)

    expected_columns = 2 * 2 * 3
    expected_x = 2 * 2 * 2
    expected_y = 2 * 1 * 3

    assert len(model.elements) == (
        expected_columns + expected_x + expected_y
    )


def test_generated_python_contains_model_entities():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        column_section_tag=1,
        beam_section_tag=1,
        column_transf_tag=1,
        beam_transf_tag=2,
    )
    generate_frame_grid(model, spec)
    transformations = {
        1: TransformationData(
            1, "Column", "PDelta", (1.0, 0.0, 0.0)
        ),
        2: TransformationData(
            2, "Beam", "Linear", (0.0, 0.0, 1.0)
        ),
    }

    sections = {
        1: SectionData(
            1,
            "Elastic",
            "Elastic",
        )
    }

    code = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
    )

    assert "ops.model('basic', '-ndm', 3, '-ndf', 6)" in code
    assert "ops.node(1" in code
    assert "ops.fix(1, 1, 1, 1, 1, 1, 1)" in code
    assert "ops.geomTransf('PDelta', 1, 1, 0, 0)" in code
    assert "ops.geomTransf('Linear', 2, 0, 0, 1)" in code
    assert "ops.element('elasticBeamColumn'" in code


def test_generator_does_not_invent_hidden_transformation():
    model = StructuralModel()
    generate_frame_grid(model, FrameGridSpec(nx=1, ny=1, nz=1))

    code = to_openseespy(model)

    assert "ops.geomTransf(" not in code
    assert "# ERROR: Element 1 has no geometric transformation assigned" in code



def test_planar_2d_frame_counts_coordinates_and_restraints():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=2,
        nz=2,
        dx=5.0,
        dz=3.0,
        planar_2d=True,
        planar_base_support="Fixed",
    )
    generate_frame_grid(model, spec)

    assert len(model.nodes) == (2 + 1) * (2 + 1)
    assert len(model.elements) == 2 * (2 + 1) + 2 * 2
    assert all(node.xyz[1] == 0.0 for node in model.nodes.values())

    base = [
        node
        for node in model.nodes.values()
        if node.xyz[2] == 0.0
    ]
    upper = [
        node
        for node in model.nodes.values()
        if node.xyz[2] > 0.0
    ]
    assert all(node.fixity == (1, 1, 1, 1, 1, 1) for node in base)
    assert all(node.fixity == (0, 1, 0, 1, 0, 1) for node in upper)
    assert {element.group for element in model.elements.values()} == {
        "column-2d",
        "beam-2d",
    }


def test_planar_2d_pinned_base_keeps_in_plane_rotation_free():
    model = StructuralModel()
    generate_frame_grid(
        model,
        FrameGridSpec(
            nx=1,
            nz=1,
            planar_2d=True,
            planar_base_support="Pinned",
        ),
    )

    base_nodes = [
        node
        for node in model.nodes.values()
        if node.xyz[2] == 0.0
    ]
    assert all(
        node.fixity == (1, 1, 1, 1, 0, 1)
        for node in base_nodes
    )


def test_planar_2d_generated_script_keeps_3d_compatible_backend():
    model = StructuralModel()
    generate_frame_grid(
        model,
        FrameGridSpec(
            nx=1,
            nz=1,
            planar_2d=True,
            column_section_tag=1,
            beam_section_tag=1,
            column_transf_tag=1,
            beam_transf_tag=2,
        ),
    )
    transformations = {
        1: TransformationData(
            1,
            "Column",
            "PDelta",
            (1.0, 0.0, 0.0),
        ),
        2: TransformationData(
            2,
            "Beam",
            "Linear",
            (0.0, 0.0, 1.0),
        ),
    }
    sections = {
        1: SectionData(
            1,
            "Elastic",
            "Elastic",
        )
    }

    code = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
    )

    assert "ops.model('basic', '-ndm', 3, '-ndf', 6)" in code
    assert "ops.fix(3, 0, 1, 0, 1, 0, 1)" in code
