import pytest

from openseespy_studio.project import (
    ConnectionData,
    MaterialData,
    ProjectDatabase,
    SectionData,
)


def test_materials_using_material_rejects_fractional_reference():
    project = ProjectDatabase()
    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        project.materials_using_material(1.5)


def test_update_material_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = MaterialData(1, "M", "Elastic")
    project.materials[1] = item
    with pytest.raises(
        ValueError,
        match=r"Material original tag must be an integer",
    ):
        project.update_material(1.5, item)
    assert project.materials[1] is item


def test_remove_material_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = MaterialData(1, "M", "Elastic")
    project.materials[1] = item
    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        project.remove_material(1.5)
    assert project.materials[1] is item


def test_update_section_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = SectionData(1, "S", "Elastic")
    project.sections[1] = item
    with pytest.raises(
        ValueError,
        match=r"Section original tag must be an integer",
    ):
        project.update_section(1.5, item)
    assert project.sections[1] is item


def test_connections_using_section_rejects_fractional_reference():
    project = ProjectDatabase()
    project.connections[1] = ConnectionData(
        1,
        "L",
        "twoNodeLink",
        1,
        2,
        {1: 1},
        section_tag=1,
    )
    with pytest.raises(ValueError, match=r"Section tag must be an integer"):
        project.connections_using_section(1.5)
