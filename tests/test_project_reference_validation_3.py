import pytest

from openseespy_studio.project import ProjectDatabase


def _project_with_element():
    project = ProjectDatabase()
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0, 0.0)
    project.model.add_element(1, 1, 2)
    return project


def test_connections_using_material_rejects_fractional_reference():
    project = ProjectDatabase()
    with pytest.raises(ValueError, match=r"Material tag must be an integer"):
        project.connections_using_material(1.5)


def test_validate_node_state_rejects_fractional_node_reference():
    project = _project_with_element()
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        project.validate_node_state(1.5)


def test_validate_element_state_rejects_fractional_element_reference():
    project = _project_with_element()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        project.validate_element_state(1.5)


def test_assign_element_formulation_rejects_fractional_element_reference():
    project = _project_with_element()
    with pytest.raises(ValueError, match=r"Element tag must be an integer"):
        project.assign_element_formulation(
            [1.5],
            element_type="forceBeamColumn",
        )
    assert project.model.elements[1].element_type == "elasticBeamColumn"


def test_assign_section_to_elements_rejects_fractional_section_reference():
    project = _project_with_element()
    with pytest.raises(ValueError, match=r"Section tag must be an integer"):
        project.assign_section_to_elements([1], 2.5)
    assert project.model.elements[1].section_tag is None
