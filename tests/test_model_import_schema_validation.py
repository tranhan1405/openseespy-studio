import pytest

from openseespy_studio.model import StructuralModel


def test_model_import_rejects_nonlist_nodes_container():
    with pytest.raises(ValueError, match=r"Model nodes must be a list"):
        StructuralModel.from_dict({"nodes": {}})


def test_model_import_rejects_nonobject_node_item():
    with pytest.raises(ValueError, match=r"Model node item 0 must be an object"):
        StructuralModel.from_dict({"nodes": [1]})


def test_model_import_rejects_nonlist_elements_container():
    with pytest.raises(ValueError, match=r"Model elements must be a list"):
        StructuralModel.from_dict({"elements": {}})


def test_model_import_rejects_nonobject_element_item():
    with pytest.raises(
        ValueError,
        match=r"Model element item 0 must be an object",
    ):
        StructuralModel.from_dict({"elements": [1]})


def test_model_import_rejects_node_coordinates_missing_y():
    with pytest.raises(
        ValueError,
        match=r"Node 1 coordinates need X and Y",
    ):
        StructuralModel.from_dict(
            {
                "nodes": [
                    {
                        "tag": 1,
                        "xyz": [0.0],
                    }
                ]
            }
        )
