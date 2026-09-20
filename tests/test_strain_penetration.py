from __future__ import annotations

import pytest

from openseespy_studio.generator import (
    connection_to_openseespy,
    column_response_spec,
    to_openseespy,
)
from openseespy_studio.project import (
    ConnectionData,
    FiberComponentData,
    MATERIAL_DEFAULTS,
    AnalysisSettingsData,
    MaterialData,
    ProjectDatabase,
    SectionData,
)
from openseespy_studio.strain_penetration import (
    build_bond_sp01_strain_penetration_section,
)
from openseespy_studio.test_column import (
    TestColumnSpec,
    build_test_column,
)


def _materials() -> dict[int, MaterialData]:
    return {
        1: MaterialData(
            1,
            "Concrete",
            "Concrete02",
            parameters=MATERIAL_DEFAULTS["Concrete02"],
        ),
        2: MaterialData(
            2,
            "Steel",
            "ReinforcingSteel",
            parameters=MATERIAL_DEFAULTS["ReinforcingSteel"],
        ),
        3: MaterialData(
            3,
            "Bond",
            "Bond_SP01",
            parameters=MATERIAL_DEFAULTS["Bond_SP01"],
        ),
    }


def _fiber_section(tag: int = 1) -> SectionData:
    return SectionData(
        tag=tag,
        name="RC section",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Concrete core",
                1,
                {
                    "y_center": 0.0,
                    "z_center": 0.0,
                    "width_y": 400.0,
                    "depth_z": 400.0,
                    "n_y": 8,
                    "n_z": 8,
                },
            ),
            FiberComponentData(
                "StraightLayer",
                "Top rebars",
                2,
                {
                    "y_i": -150.0,
                    "z_i": 150.0,
                    "y_j": 150.0,
                    "z_j": 150.0,
                    "n_bars": 4,
                    "bar_area": 201.0,
                },
            ),
            FiberComponentData(
                "StraightLayer",
                "Bottom rebars",
                2,
                {
                    "y_i": -150.0,
                    "z_i": -150.0,
                    "y_j": 150.0,
                    "z_j": -150.0,
                    "n_bars": 4,
                    "bar_area": 201.0,
                },
            ),
        ],
        display_geometry={
            "shape": "Rectangle",
            "dimensions": {"height": 400.0, "width": 400.0},
        },
    )


def test_strain_penetration_section_replaces_only_rebar_material():
    materials = _materials()
    source = _fiber_section()

    result = build_bond_sp01_strain_penetration_section(
        source,
        materials,
        bond_material_tag=3,
        section_tag=9,
    )

    assert result.section.tag == 9
    assert result.replaced_material_tags == [2]
    assert result.section.fiber_components[0].material_tag == 1
    assert result.section.fiber_components[1].material_tag == 3
    assert result.section.fiber_components[2].material_tag == 3
    assert result.section.display_geometry == source.display_geometry


def test_strain_penetration_requires_fiber_section_and_bond_material():
    materials = _materials()
    elastic = SectionData(2, "Elastic", "Elastic")

    with pytest.raises(ValueError, match="Fiber"):
        build_bond_sp01_strain_penetration_section(
            elastic,
            materials,
            bond_material_tag=3,
            section_tag=10,
        )

    with pytest.raises(ValueError, match="not Bond_SP01"):
        build_bond_sp01_strain_penetration_section(
            _fiber_section(),
            materials,
            bond_material_tag=2,
            section_tag=10,
        )


def test_zero_length_section_connection_generates_native_command():
    connection = ConnectionData(
        tag=20,
        name="Strain penetration",
        connection_type="zeroLengthSection",
        node_i=1,
        node_j=2,
        section_tag=9,
        orient_x=(0.0, 0.0, 1.0),
        orient_y=(1.0, 0.0, 0.0),
        do_rayleigh=False,
    )
    command = connection_to_openseespy(connection)
    assert command == (
        "ops.element('zeroLengthSection', 20, 1, 2, 9, "
        "'-orient', 0, 0, 1, 1, 0, 0, '-doRayleigh', 0)"
    )


def test_test_column_builds_bond_sp01_zero_length_section():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            axis=3,
            lateral_direction=1,
            planar=True,
            section_tag=1,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
            base_interface_rayleigh=False,
        ),
    )

    assert result.base_connection_tag is not None
    assert result.base_section_tag is not None
    connection = project.connections[result.base_connection_tag]
    assert connection.connection_type == "zeroLengthSection"
    assert connection.section_tag == result.base_section_tag
    assert connection.generated_section_tag == result.base_section_tag
    assert connection.orient_x == pytest.approx((0.0, 0.0, 1.0))
    assert connection.orient_y == pytest.approx((0.0, -1.0, 0.0))
    assert connection.do_rayleigh is False
    assert result.base_constraint_tag is not None
    assert connection.generated_constraint_tag == result.base_constraint_tag

    # Z-axis column + X lateral: planar scaffolding fixes UY/RX/RZ.
    # UX shear is transferred to the fixed footing by equalDOF, while
    # UZ and RY remain interface freedoms carried by zeroLengthSection.
    assert project.model.nodes[result.base_node].fixity == (
        0, 1, 0, 1, 0, 1
    )
    constraint = project.constraints[result.base_constraint_tag]
    assert constraint.constraint_type == "equalDOF"
    assert constraint.retained_node == result.base_ground_node
    assert constraint.constrained_nodes == [result.base_node]
    assert constraint.dofs == (1,)

    interface_section = project.sections[result.base_section_tag]
    assert interface_section.fiber_components[0].material_tag == 1
    assert interface_section.fiber_components[1].material_tag == 3
    assert interface_section.fiber_components[2].material_tag == 3


def test_full_generator_places_section_before_zero_length_section_element():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            section_tag=1,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
        ),
    )
    script = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
    )
    section_text = f"ops.section('Fiber', {result.base_section_tag}"
    element_text = (
        f"ops.element('zeroLengthSection', {result.base_connection_tag}"
    )
    assert section_text in script
    assert element_text in script
    assert script.index(section_text) < script.index(element_text)
    assert "ops.equalDOF(" in script
    assert script.index("ops.equalDOF(") < script.index(element_text)
    assert "ops.uniaxialMaterial('Bond_SP01', 3," in script


def test_removing_generated_connection_cleans_ground_and_interface_section():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            section_tag=1,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
        ),
    )
    ground = result.base_ground_node
    section_tag = result.base_section_tag
    constraint_tag = result.base_constraint_tag
    assert constraint_tag in project.constraints

    project.remove_connection(result.base_connection_tag)

    assert ground not in project.model.nodes
    assert section_tag not in project.sections
    assert constraint_tag not in project.constraints
    assert 1 in project.sections



@pytest.mark.parametrize(
    ("axis", "expected_x", "expected_y"),
    [
        (1, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (2, (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
        (3, (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
    ],
)
def test_strain_penetration_orientation_matches_beam_local_axes(
    axis,
    expected_x,
    expected_y,
):
    from openseespy_studio.test_column import zero_length_section_orientation

    x, y = zero_length_section_orientation(axis)
    assert x == pytest.approx(expected_x)
    assert y == pytest.approx(expected_y)


def test_3d_strain_penetration_constrains_both_transverse_shear_dofs():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            axis=3,
            lateral_direction=1,
            planar=False,
            section_tag=1,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
        ),
    )

    assert project.model.nodes[result.base_node].fixity == (
        0, 0, 0, 0, 0, 0
    )
    assert result.base_constraint_tag is not None
    constraint = project.constraints[result.base_constraint_tag]
    assert constraint.dofs == (1, 2)

    connection = project.connections[result.base_connection_tag]
    assert connection.connection_type == "zeroLengthSection"
    assert connection.orient_x == pytest.approx((0.0, 0.0, 1.0))
    assert connection.orient_y == pytest.approx((0.0, -1.0, 0.0))



def test_generated_constraint_metadata_round_trip():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            section_tag=1,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
        ),
    )

    restored = ProjectDatabase.from_dict(project.to_dict())
    connection = restored.connections[result.base_connection_tag]
    assert connection.generated_constraint_tag == result.base_constraint_tag
    assert connection.generated_section_tag == result.base_section_tag
    assert result.base_constraint_tag in restored.constraints



def test_test_column_response_spec_identifies_base_hinge_and_bond_fibers():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    built = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            axis=3,
            lateral_direction=1,
            section_tag=1,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
        ),
    )
    analysis = AnalysisSettingsData(
        1,
        "Cyclic",
        "Cyclic",
        control_node=built.top_node,
        control_dof=1,
        cyclic_targets=[10.0, -10.0, 0.0],
        cyclic_increment=2.0,
    )

    spec = column_response_spec(
        project.model,
        sections=project.sections,
        materials=project.materials,
        transformations=project.transformations,
        connections=project.connections,
        active_analysis=analysis,
    )

    assert spec is not None
    assert spec["element_tag"] == built.element_tags[0]
    assert spec["base_node"] == built.base_node
    assert spec["top_node"] == built.top_node
    assert spec["moment_component"] == "My"
    assert spec["moment_index"] == 2
    assert spec["moment_sign"] == pytest.approx(-1.0)
    assert spec["interface_tag"] == built.base_connection_tag
    assert len(spec["base_fibers"]) >= 2
    assert {row["material_type"] for row in spec["base_fibers"]} >= {
        "ReinforcingSteel",
        "Concrete02",
    }
    assert len(spec["interface_fibers"]) == 2
    assert all(
        row["material_type"] == "Bond_SP01"
        for row in spec["interface_fibers"]
    )


def test_full_generator_captures_specimen_histories_for_active_analysis():
    project = ProjectDatabase(
        units={"length": "mm", "force": "N", "time": "s"}
    )
    for material in _materials().values():
        project.add_material(material)
    project.add_section(_fiber_section())

    built = build_test_column(
        project,
        TestColumnSpec(
            height=3000.0,
            section_tag=1,
            lateral_reference_load=1.0,
            base_interface_type="Bond_SP01 strain penetration",
            strain_penetration_bond_material_tag=3,
        ),
    )
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Push",
            "Pushover",
            steps=2,
            control_node=built.top_node,
            control_dof=1,
            displacement_increment=1.0,
        )
    )
    project.active_analysis_tag = 1

    script = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        time_series=project.time_series,
        load_patterns=project.load_patterns,
        nodal_loads=project.nodal_loads,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
        units=project.units,
    )

    assert "'schema_version': 11" in script
    assert "_studio_specimen_response_spec" in script
    assert "'section_deformation': []" in script
    assert "'interface_deformation': []" in script
    assert "'interface_fibers': []" in script
    assert "'section', _studio_specimen_section, 'deformation'" in script
    assert "'section', 'fiber'" in script
    assert "'slip':" in script
