from __future__ import annotations

from openseespy_studio.generator import ordered_material_tags, to_openseespy
from openseespy_studio.material_chain import (
    SpringMaterialChainSpec,
    build_spring_material_chain,
    describe_material_chain,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ConnectionData,
    MaterialData,
    ProjectDatabase,
)


def elastic(tag: int) -> MaterialData:
    return MaterialData(
        tag=tag,
        name=f"Elastic {tag}",
        material_type="Elastic",
        parameters={"E": 1000.0},
    )


def test_build_new_steel_fatigue_minmax_chain():
    result = build_spring_material_chain(
        SpringMaterialChainSpec(
            create_steel02=True,
            add_fatigue=True,
            add_minmax=True,
            name_prefix="Cyclic spring",
            minmax_parameters={"min": -0.03, "max": 0.03},
        ),
        {},
    )

    assert [item.material_type for item in result.materials] == [
        "Steel02",
        "Fatigue",
        "MinMax",
    ]
    steel, fatigue, minmax = result.materials
    assert fatigue.base_material_tag == steel.tag
    assert minmax.base_material_tag == fatigue.tag
    assert result.base_tag == steel.tag
    assert result.final_tag == minmax.tag


def test_chain_can_start_from_existing_material():
    base = elastic(20)
    result = build_spring_material_chain(
        SpringMaterialChainSpec(
            base_material_tag=20,
            add_fatigue=False,
            add_minmax=True,
            name_prefix="Limit spring",
        ),
        {20: base},
    )

    assert len(result.materials) == 1
    assert result.materials[0].material_type == "MinMax"
    assert result.materials[0].base_material_tag == 20
    assert result.final_tag == result.materials[0].tag


def test_chain_avoids_existing_tags_and_generates_in_dependency_order():
    existing = {
        1: elastic(1),
        2: elastic(2),
        4: elastic(4),
    }
    result = build_spring_material_chain(
        SpringMaterialChainSpec(
            create_steel02=True,
            add_fatigue=True,
            add_minmax=True,
        ),
        existing,
        next_tag=2,
    )

    assert result.tags() == [3, 5, 6]
    combined = dict(existing)
    combined.update({item.tag: item for item in result.materials})
    order = ordered_material_tags(combined)
    assert order.index(3) < order.index(5) < order.index(6)


def test_chain_pending_materials_can_be_committed_to_project():
    project = ProjectDatabase()
    project.add_material(elastic(1))

    result = build_spring_material_chain(
        SpringMaterialChainSpec(
            base_material_tag=1,
            add_fatigue=True,
            add_minmax=True,
        ),
        project.materials,
    )
    for material in result.materials:
        project.add_material(material)

    assert result.final_tag in project.materials
    assert project.materials_using_material(1) == [result.materials[0].tag]


def test_describe_material_chain_returns_inner_to_outer_order():
    result = build_spring_material_chain(
        SpringMaterialChainSpec(
            create_steel02=True,
            add_fatigue=True,
            add_minmax=True,
        ),
        {},
    )
    materials = {item.tag: item for item in result.materials}
    path = describe_material_chain(result.final_tag, materials)
    assert [item.material_type for item in path] == [
        "Steel02",
        "Fatigue",
        "MinMax",
    ]


def test_chain_requires_at_least_one_wrapper():
    try:
        SpringMaterialChainSpec(
            create_steel02=True,
            add_fatigue=False,
            add_minmax=False,
        )
    except ValueError as exc:
        assert "Fatigue and/or MinMax" in str(exc)
    else:
        raise AssertionError("Expected empty chain to be rejected")



def test_full_zero_length_chain_generates_before_connection():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)

    result = build_spring_material_chain(
        SpringMaterialChainSpec(
            create_steel02=True,
            add_fatigue=True,
            add_minmax=True,
            name_prefix="Research spring",
        ),
        project.materials,
    )
    for material in result.materials:
        project.add_material(material)

    connection = ConnectionData(
        tag=10,
        name="Research zeroLength",
        connection_type="zeroLength",
        node_i=1,
        node_j=2,
        materials_by_dof={1: result.final_tag},
    )
    project.add_connection(connection)

    script = to_openseespy(
        project.model,
        materials=project.materials,
        connections=project.connections,
    )
    steel_pos = script.index("uniaxialMaterial('Steel02'")
    fatigue_pos = script.index("uniaxialMaterial('Fatigue'")
    minmax_pos = script.index("uniaxialMaterial('MinMax'")
    spring_pos = script.index("element('zeroLength'")

    assert steel_pos < fatigue_pos < minmax_pos < spring_pos
    assert f"'-mat', {result.final_tag}" in script
