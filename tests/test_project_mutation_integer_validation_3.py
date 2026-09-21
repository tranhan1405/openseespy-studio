import pytest

from openseespy_studio.project import (
    ElementLoadData,
    NodalLoadData,
    PrescribedDisplacementData,
    ProjectDatabase,
)


def test_update_nodal_load_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = NodalLoadData(1, "N", 1, 1, (0, 0, 0, 0, 0, 0))
    project.nodal_loads[1] = item
    with pytest.raises(
        ValueError,
        match=r"Nodal load original tag must be an integer",
    ):
        project.update_nodal_load(1.5, item)
    assert project.nodal_loads[1] is item


def test_remove_nodal_load_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = NodalLoadData(1, "N", 1, 1, (0, 0, 0, 0, 0, 0))
    project.nodal_loads[1] = item
    with pytest.raises(ValueError, match=r"Nodal load tag must be an integer"):
        project.remove_nodal_load(1.5)
    assert project.nodal_loads[1] is item


def test_update_prescribed_displacement_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = PrescribedDisplacementData(1, "D", 1, 1, 1, 0.0)
    project.prescribed_displacements[1] = item
    with pytest.raises(
        ValueError,
        match=r"Prescribed displacement original tag must be an integer",
    ):
        project.update_prescribed_displacement(1.5, item)
    assert project.prescribed_displacements[1] is item


def test_remove_prescribed_displacement_rejects_fractional_tag_without_deleting():
    project = ProjectDatabase()
    item = PrescribedDisplacementData(1, "D", 1, 1, 1, 0.0)
    project.prescribed_displacements[1] = item
    with pytest.raises(
        ValueError,
        match=r"Prescribed displacement tag must be an integer",
    ):
        project.remove_prescribed_displacement(1.5)
    assert project.prescribed_displacements[1] is item


def test_update_element_load_rejects_fractional_original_tag():
    project = ProjectDatabase()
    item = ElementLoadData(1, "E", 1, 1)
    project.element_loads[1] = item
    with pytest.raises(
        ValueError,
        match=r"Element load original tag must be an integer",
    ):
        project.update_element_load(1.5, item)
    assert project.element_loads[1] is item
