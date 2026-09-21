import pytest

from openseespy_studio.model import Node
from openseespy_studio.project import ProjectDatabase


def test_legacy_transformation_loader_rejects_fractional_key():
    with pytest.raises(
        ValueError,
        match=r"Legacy transformation tag must be an integer",
    ):
        ProjectDatabase._load_transformations({"1.5": {}})


def test_legacy_material_loader_rejects_nonobject_record():
    with pytest.raises(
        ValueError,
        match=r"Legacy material '1' must be an object",
    ):
        ProjectDatabase._load_materials({"1": "bad"})


def test_legacy_section_loader_rejects_nonobject_record():
    with pytest.raises(
        ValueError,
        match=r"Legacy section '1' must be an object",
    ):
        ProjectDatabase._load_sections({"1": "bad"})


def test_legacy_transformation_loader_rejects_nonobject_record():
    with pytest.raises(
        ValueError,
        match=r"Legacy transformation '1' must be an object",
    ):
        ProjectDatabase._load_transformations({"1": "bad"})


def test_direct_node_rejects_fractional_tag():
    with pytest.raises(ValueError, match=r"Node tag must be an integer"):
        Node(1.5, (0.0, 0.0, 0.0))
