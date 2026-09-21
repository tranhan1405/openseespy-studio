import pytest

from openseespy_studio.project import (
    ProjectDatabase,
    SectionData,
    TransformationData,
)


def test_remove_section_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = SectionData(1, "S", "Elastic")
    project.sections[1] = item
    with pytest.raises(ValueError, match=r"Section tag must be an integer"):
        project.remove_section(1.5)
    assert project.sections[1] is item


def test_sections_using_material_rejects_fractional_reference():
    project = ProjectDatabase()
    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        project.sections_using_material(1.5)


def test_update_transformation_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = TransformationData(1, "T", "Linear")
    project.transformations[1] = item
    with pytest.raises(
        ValueError,
        match=r"Transformation original tag must be an integer",
    ):
        project.update_transformation(1.5, item)
    assert project.transformations[1] is item


def test_remove_transformation_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = TransformationData(1, "T", "Linear")
    project.transformations[1] = item
    with pytest.raises(
        ValueError,
        match=r"Transformation tag must be an integer",
    ):
        project.remove_transformation(1.5)
    assert project.transformations[1] is item


def test_create_ground_node_rejects_fractional_source_node_reference():
    project = ProjectDatabase()
    project.model.add_node(1, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match=r"Source node tag must be an integer"):
        project.create_ground_node(1.5)
    assert set(project.model.nodes) == {1}
