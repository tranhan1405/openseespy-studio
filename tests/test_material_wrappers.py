from __future__ import annotations

from openseespy_studio.generator import (
    material_to_openseespy,
    ordered_material_tags,
)
from openseespy_studio.material_test import (
    MaterialTestSpec,
    build_material_test_script,
)
from openseespy_studio.project import MaterialData, ProjectDatabase


def elastic(tag: int, e: float = 2.0e11) -> MaterialData:
    return MaterialData(
        tag,
        f"Elastic {tag}",
        "Elastic",
        parameters={"E": e},
    )


def test_minmax_and_fatigue_generate_wrapper_commands():
    minmax = MaterialData(
        2,
        "Limited",
        "MinMax",
        parameters={"min": -0.02, "max": 0.03},
        base_material_tag=1,
    )
    fatigue = MaterialData(
        3,
        "Fatigue",
        "Fatigue",
        parameters={"E0": 0.2, "m": -0.45, "min": -0.1, "max": 0.1},
        base_material_tag=2,
    )

    assert material_to_openseespy(minmax) == (
        "ops.uniaxialMaterial('MinMax', 2, 1, "
        "'-min', -0.02, '-max', 0.03)"
    )
    assert material_to_openseespy(fatigue) == (
        "ops.uniaxialMaterial('Fatigue', 3, 2, "
        "'-E0', 0.2, '-m', -0.45, '-min', -0.1, '-max', 0.1)"
    )


def test_parallel_and_series_generate_component_lists_and_factors():
    parallel = MaterialData(
        10,
        "Parallel",
        "Parallel",
        material_tags=[1, 2],
        factors=[1.0, -0.5],
    )
    series = MaterialData(
        11,
        "Series",
        "Series",
        material_tags=[1, 2],
    )

    assert material_to_openseespy(parallel) == (
        "ops.uniaxialMaterial('Parallel', 10, 1, 2, "
        "'-factors', 1, -0.5)"
    )
    assert material_to_openseespy(series) == (
        "ops.uniaxialMaterial('Series', 11, 1, 2)"
    )


def test_dependency_order_ignores_numeric_tag_order():
    materials = {
        1: MaterialData(
            1,
            "Wrapper with lower tag",
            "MinMax",
            parameters={"min": -0.02, "max": 0.02},
            base_material_tag=20,
        ),
        20: elastic(20),
    }
    assert ordered_material_tags(materials) == [20, 1]


def test_project_rejects_missing_and_cyclic_wrapper_references():
    project = ProjectDatabase()
    project.add_material(elastic(1))

    try:
        project.add_material(
            MaterialData(
                2,
                "Missing",
                "MinMax",
                base_material_tag=99,
            )
        )
    except ValueError as exc:
        assert "missing material" in str(exc).lower()
    else:
        raise AssertionError("Expected missing material dependency rejection")

    project.add_material(
        MaterialData(
            2,
            "Wrapper",
            "MinMax",
            base_material_tag=1,
        )
    )
    try:
        project.update_material(
            1,
            MaterialData(
                1,
                "Cycle",
                "MinMax",
                base_material_tag=2,
            ),
        )
    except ValueError as exc:
        assert "dependency cycle" in str(exc).lower()
    else:
        raise AssertionError("Expected wrapper cycle rejection")


def test_wrapper_round_trip_preserves_references_and_factors():
    material = MaterialData(
        5,
        "Parallel",
        "Parallel",
        material_tags=[1, 2, 3],
        factors=[1.0, 0.75, -0.25],
    )
    restored = MaterialData.from_dict(material.to_dict())
    assert restored.material_tags == [1, 2, 3]
    assert restored.factors == [1.0, 0.75, -0.25]


def test_material_test_script_builds_dependencies_before_wrapper():
    base = elastic(20)
    wrapper = MaterialData(
        1,
        "Limited",
        "MinMax",
        parameters={"min": -0.01, "max": 0.01},
        base_material_tag=20,
    )
    script = build_material_test_script(
        wrapper,
        {"length": "m", "force": "kN", "time": "s"},
        MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=0.015,
            levels=1,
            cycles_per_level=1,
            steps_per_segment=2,
        ),
        {1: wrapper, 20: base},
    )
    assert script.index("uniaxialMaterial('Elastic', 20") < script.index(
        "uniaxialMaterial('MinMax', 1"
    )
    assert "ops.testUniaxialMaterial(1)" in script
