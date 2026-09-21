import pytest

from openseespy_studio.project import (
    FiberComponentData,
    FiberData,
    MaterialData,
    SectionData,
)


def test_wrapper_material_rejects_fractional_base_material_reference():
    with pytest.raises(
        ValueError,
        match=r"Base material tag must be an integer",
    ):
        MaterialData(
            10,
            "MinMax",
            "MinMax",
            base_material_tag=1.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Base material tag must be an integer",
    ):
        MaterialData.from_dict(
            {
                "tag": 10,
                "name": "MinMax",
                "material_type": "MinMax",
                "base_material_tag": 1.5,
            }
        )


def test_composite_material_rejects_fractional_component_reference():
    with pytest.raises(
        ValueError,
        match=r"Component material tag must be an integer",
    ):
        MaterialData(
            11,
            "Parallel",
            "Parallel",
            material_tags=[1, 2.5],
        )

    with pytest.raises(
        ValueError,
        match=r"Component material tag must be an integer",
    ):
        MaterialData.from_dict(
            {
                "tag": 11,
                "name": "Parallel",
                "material_type": "Parallel",
                "material_tags": [1, 2.5],
            }
        )


def test_fiber_rejects_fractional_material_reference():
    with pytest.raises(
        ValueError,
        match=r"Fiber material tag must be an integer",
    ):
        FiberData(
            0.0,
            0.0,
            0.001,
            1.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Fiber material tag must be an integer",
    ):
        FiberData.from_dict(
            {
                "y": 0.0,
                "z": 0.0,
                "area": 0.001,
                "material_tag": 1.5,
            }
        )


def test_fiber_component_rejects_fractional_material_reference():
    with pytest.raises(
        ValueError,
        match=r"Fiber component material tag must be an integer",
    ):
        FiberComponentData(
            "SingleFiber",
            "Fiber",
            1.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Fiber component material tag must be an integer",
    ):
        FiberComponentData.from_dict(
            {
                "component_type": "SingleFiber",
                "name": "Fiber",
                "material_tag": 1.5,
            }
        )


def test_elastic_section_rejects_fractional_material_reference():
    with pytest.raises(
        ValueError,
        match=r"Section material tag must be an integer",
    ):
        SectionData(
            12,
            "Elastic section",
            "Elastic",
            material_tag=1.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Section material tag must be an integer",
    ):
        SectionData.from_dict(
            {
                "tag": 12,
                "name": "Elastic section",
                "section_type": "Elastic",
                "material_tag": 1.5,
            }
        )
