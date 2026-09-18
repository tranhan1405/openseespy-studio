from openseespy_studio.generator import (
    FrameGridSpec,
    generate_frame_grid,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import TransformationData


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

    code = to_openseespy(model, transformations=transformations)

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
