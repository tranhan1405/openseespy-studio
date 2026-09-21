import pytest

from openseespy_studio.project import SelectionSetData


def test_selection_set_rejects_fractional_node_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Selection-set node tag must be an integer",
    ):
        SelectionSetData(
            "Nodes",
            node_tags={1.5},
        )

    with pytest.raises(
        ValueError,
        match=r"Selection-set node tag must be an integer",
    ):
        SelectionSetData.from_dict(
            {
                "name": "Nodes",
                "node_tags": [1.5],
            }
        )


def test_selection_set_rejects_fractional_element_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Selection-set element tag must be an integer",
    ):
        SelectionSetData(
            "Elements",
            element_tags={2.5},
        )

    with pytest.raises(
        ValueError,
        match=r"Selection-set element tag must be an integer",
    ):
        SelectionSetData.from_dict(
            {
                "name": "Elements",
                "element_tags": [2.5],
            }
        )
