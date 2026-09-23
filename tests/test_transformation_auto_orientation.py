import math

from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    TransformationData,
    resolve_transformation_vecxz,
)
from openseespy_studio.validation import validate_project


def _section():
    return SectionData(1, "Elastic", "Elastic")


def test_legacy_transformation_defaults_to_manual():
    restored = TransformationData.from_dict({
        "tag": 1,
        "name": "Legacy",
        "transformation_type": "Linear",
        "vecxz": [0.0, 1.0, 0.0],
    })
    assert restored.orientation_mode == "manual"
    assert restored.vecxz == (0.0, 1.0, 0.0)


def test_auto_orientation_vertical_member_avoids_global_z():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.add_element(1, 1, 2, section_tag=1, transf_tag=8)
    transformation = TransformationData(
        8, "Auto", "PDelta", orientation_mode="auto"
    )

    assert resolve_transformation_vecxz(model, transformation) == (1.0, 0.0, 0.0)


def test_auto_orientation_horizontal_xy_frame_prefers_global_z():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_node(3, 0.0, 5.0, 0.0)
    model.add_element(1, 1, 2, section_tag=1, transf_tag=8)
    model.add_element(2, 1, 3, section_tag=1, transf_tag=8)
    transformation = TransformationData(
        8, "Auto", "Linear", orientation_mode="auto"
    )

    assert resolve_transformation_vecxz(model, transformation) == (0.0, 0.0, 1.0)


def test_auto_orientation_mixed_xyz_members_is_safe_for_all():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 0.0, 1.0, 0.0)
    model.add_node(4, 0.0, 0.0, 1.0)
    for tag, node_j in enumerate((2, 3, 4), start=1):
        model.add_element(tag, 1, node_j, section_tag=1, transf_tag=8)
    transformation = TransformationData(
        8, "Auto", "Linear", orientation_mode="auto"
    )
    vec = resolve_transformation_vecxz(model, transformation)

    assert all(abs(value) > 0.0 for value in vec)
    for node_j in (2, 3, 4):
        axis = model.nodes[node_j].xyz
        cross = (
            vec[1] * axis[2] - vec[2] * axis[1],
            vec[2] * axis[0] - vec[0] * axis[2],
            vec[0] * axis[1] - vec[1] * axis[0],
        )
        assert math.sqrt(sum(value * value for value in cross)) > 1.0e-6


def test_auto_orientation_exports_resolved_vecxz_and_validates_cleanly():
    project = ProjectDatabase(model=StructuralModel())
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 0.0, 0.0, 3.0)
    project.model.add_element(1, 1, 2, section_tag=1, transf_tag=8)
    project.add_section(_section())
    project.add_transformation(
        TransformationData(
            8,
            "Auto Column",
            "PDelta",
            vecxz=(0.0, 0.0, 1.0),
            orientation_mode="auto",
        )
    )

    script = to_openseespy(
        project.model,
        sections=project.sections,
        transformations=project.transformations,
    )
    assert "ops.geomTransf('PDelta', 8, 1, 0, 0)" in script
    errors = [
        issue for issue in validate_project(project)
        if issue.category == "Transformation orientation"
        and issue.severity == "ERROR"
    ]
    assert errors == []
