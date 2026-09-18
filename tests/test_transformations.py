from openseespy_studio.generator import (
    to_openseespy,
    transformation_to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ProjectDatabase,
    TransformationData,
)


def test_transformation_round_trip():
    project = ProjectDatabase()
    project.add_transformation(
        TransformationData(
            tag=2,
            name="Columns PDelta",
            transformation_type="PDelta",
            vecxz=(0.0, 1.0, 0.0),
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    transformation = restored.transformations[2]
    assert transformation.name == "Columns PDelta"
    assert transformation.transformation_type == "PDelta"
    assert transformation.vecxz == (0.0, 1.0, 0.0)


def test_zero_orientation_vector_is_rejected():
    try:
        TransformationData(
            tag=1,
            name="Bad",
            transformation_type="Linear",
            vecxz=(0.0, 0.0, 0.0),
        )
    except ValueError as exc:
        assert "cannot be zero" in str(exc)
    else:
        raise AssertionError("Expected zero orientation vector to fail")


def test_transformation_generator():
    transformation = TransformationData(
        tag=3,
        name="Corot",
        transformation_type="Corotational",
        vecxz=(0.0, 1.0, 0.0),
    )

    line = transformation_to_openseespy(transformation)

    assert line == "ops.geomTransf('Corotational', 3, 0, 1, 0)"


def test_element_uses_assigned_transformation():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_element(1, 1, 2, transf_tag=5)

    transformation = TransformationData(
        tag=5,
        name="Linear",
        transformation_type="Linear",
        vecxz=(0.0, 1.0, 0.0),
    )

    script = to_openseespy(
        model,
        transformations={5: transformation},
    )

    assert "ops.geomTransf('Linear', 5, 0, 1, 0)" in script
    assert "Iy, Iz, 5)" in script
