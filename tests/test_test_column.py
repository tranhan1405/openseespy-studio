from __future__ import annotations

import pytest

from openseespy_studio.project import (
    ConnectionData,
    LoadPatternData,
    MaterialData,
    NodalLoadData,
    ProjectDatabase,
    SectionData,
    TimeSeriesData,
)
from openseespy_studio.test_column import (
    TestColumnSpec,
    build_test_column,
)


def project_with_section() -> ProjectDatabase:
    project = ProjectDatabase()
    project.add_section(
        SectionData(
            tag=1,
            name="Test section",
            section_type="Elastic",
        )
    )
    return project


def test_default_test_column_builds_vertical_planar_cantilever():
    project = project_with_section()
    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            num_elements=1,
            axis=3,
            lateral_direction=1,
            planar=True,
            section_tag=1,
        ),
    )

    assert project.model.ndm == 3
    assert project.model.ndf == 6
    assert result.node_tags == [1, 2]
    assert result.element_tags == [1]
    assert project.model.nodes[1].xyz == pytest.approx((0.0, 0.0, 0.0))
    assert project.model.nodes[2].xyz == pytest.approx((0.0, 0.0, 3.0))
    assert project.model.nodes[1].fixity == (1, 1, 1, 1, 1, 1)
    assert project.model.nodes[2].fixity == (0, 1, 0, 1, 0, 1)

    element = project.model.elements[1]
    assert element.group == "test-column"
    assert element.element_type == "forceBeamColumn"
    assert element.section_tag == 1
    assert element.integration_type == "Lobatto"
    assert element.integration_points == 5

    transformation = project.transformations[result.transformation_tag]
    assert transformation.transformation_type == "PDelta"
    assert transformation.vecxz == pytest.approx((1.0, 0.0, 0.0))


def test_test_column_can_divide_member_into_multiple_elements():
    project = project_with_section()
    result = build_test_column(
        project,
        TestColumnSpec(
            height=4.0,
            num_elements=4,
            section_tag=1,
        ),
    )

    assert result.node_tags == [1, 2, 3, 4, 5]
    assert result.element_tags == [1, 2, 3, 4]
    assert [project.model.nodes[tag].xyz[2] for tag in result.node_tags] == (
        pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])
    )


def test_test_column_creates_separate_axial_and_lateral_patterns():
    project = project_with_section()
    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            section_tag=1,
            axial_load=200.0,
            lateral_reference_load=1.0,
        ),
    )

    assert result.axial_pattern_tag is not None
    assert result.lateral_pattern_tag is not None
    assert result.axial_pattern_tag != result.lateral_pattern_tag

    axial = next(
        load
        for load in project.nodal_loads.values()
        if load.pattern_tag == result.axial_pattern_tag
    )
    lateral = next(
        load
        for load in project.nodal_loads.values()
        if load.pattern_tag == result.lateral_pattern_tag
    )
    assert axial.node_tag == result.top_node
    assert axial.values == pytest.approx((0.0, 0.0, -200.0, 0.0, 0.0, 0.0))
    assert lateral.values == pytest.approx((1.0, 0.0, 0.0, 0.0, 0.0, 0.0))


def test_test_column_top_mass_and_prescribed_displacement():
    project = project_with_section()
    result = build_test_column(
        project,
        TestColumnSpec(
            section_tag=1,
            top_mass=2.5,
            top_mass_directions=(1, 2),
            prescribed_displacement=0.02,
        ),
    )

    assert project.model.nodes[result.top_node].mass == pytest.approx(
        (2.5, 2.5, 0.0, 0.0, 0.0, 0.0)
    )
    assert result.prescribed_pattern_tag is not None
    displacement = next(iter(project.prescribed_displacements.values()))
    assert displacement.node_tag == result.top_node
    assert displacement.dof == 1
    assert displacement.value == pytest.approx(0.02)


def test_standalone_test_column_clears_old_model_linked_objects():
    project = project_with_section()
    project.model.add_node(20, 9.0, 9.0, 9.0)
    project.add_time_series(TimeSeriesData(10, "Old", "Linear"))
    project.add_load_pattern(LoadPatternData(10, "Old", "Plain", 10))
    project.add_nodal_load(
        NodalLoadData(
            10,
            "Old load",
            10,
            20,
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )

    result = build_test_column(
        project,
        TestColumnSpec(section_tag=1, replace_geometry=True),
    )

    assert set(project.model.nodes) == set(result.node_tags)
    assert 20 not in project.model.nodes
    assert 10 not in project.load_patterns
    assert 10 not in project.nodal_loads
    assert project.time_series == {}


def test_append_test_column_rejects_true_2d_backend():
    project = project_with_section()
    project.model.ndm = 2
    project.model.ndf = 3

    with pytest.raises(ValueError, match="3D/6DOF"):
        build_test_column(
            project,
            TestColumnSpec(
                section_tag=1,
                replace_geometry=False,
            ),
        )


def test_planar_direction_must_differ_from_column_axis():
    project = project_with_section()

    with pytest.raises(ValueError, match="differ"):
        build_test_column(
            project,
            TestColumnSpec(
                axis=3,
                lateral_direction=3,
                planar=True,
                section_tag=1,
            ),
        )



def test_test_column_rotational_base_interface_creates_zero_length():
    project = project_with_section()
    project.add_material(
        MaterialData(
            10,
            "Base rotation",
            "Elastic",
            parameters={"E": 5.0e6},
        )
    )

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            axis=3,
            lateral_direction=1,
            planar=True,
            section_tag=1,
            base_interface_type="Rotational spring",
            base_interface_materials={5: 10},
            base_interface_rayleigh=False,
        ),
    )

    assert result.base_connection_tag is not None
    assert result.base_ground_node is not None
    assert result.base_ground_node in project.model.nodes
    assert project.model.nodes[result.base_ground_node].xyz == pytest.approx(
        project.model.nodes[result.base_node].xyz
    )
    assert project.model.nodes[result.base_ground_node].fixity == (1, 1, 1, 1, 1, 1)

    # Z-axis column + X lateral direction bends about global Y => RY / DOF 5.
    assert project.model.nodes[result.base_node].fixity == (1, 1, 1, 1, 0, 1)
    connection = project.connections[result.base_connection_tag]
    assert connection.connection_type == "zeroLength"
    assert connection.materials_by_dof == {5: 10}
    assert connection.do_rayleigh is False
    assert connection.generated_ground_node == result.base_ground_node


def test_test_column_bond_slip_interface_can_release_lateral_translation():
    project = project_with_section()
    project.add_material(
        MaterialData(
            11,
            "Bond slip surrogate",
            "Elastic",
            parameters={"E": 1000.0},
        )
    )

    result = build_test_column(
        project,
        TestColumnSpec(
            section_tag=1,
            axis=3,
            lateral_direction=1,
            planar=True,
            base_interface_type="Translational slip spring",
            base_interface_materials={1: 11},
        ),
    )

    assert project.model.nodes[result.base_node].fixity == (0, 1, 1, 1, 1, 1)
    connection = project.connections[result.base_connection_tag]
    assert connection.materials_by_dof == {1: 11}


def test_planar_test_rejects_out_of_plane_base_interface_dof():
    project = project_with_section()
    project.add_material(
        MaterialData(
            12,
            "Spring",
            "Elastic",
            parameters={"E": 1000.0},
        )
    )

    with pytest.raises(ValueError, match="Planar test restrains"):
        build_test_column(
            project,
            TestColumnSpec(
                section_tag=1,
                axis=3,
                lateral_direction=1,
                planar=True,
                base_interface_type="Custom zeroLength",
                # For X-Z plane, UY is an out-of-plane restrained DOF.
                base_interface_materials={2: 12},
            ),
        )


def test_base_interface_requires_existing_material():
    project = project_with_section()
    with pytest.raises(ValueError, match="missing material"):
        build_test_column(
            project,
            TestColumnSpec(
                section_tag=1,
                base_interface_type="Rotational spring",
                base_interface_materials={5: 999},
            ),
        )


def test_test_column_hinge_radau_stores_member_hinge_definition():
    project = project_with_section()
    project.add_section(
        SectionData(
            tag=2,
            name="Elastic interior",
            section_type="Elastic",
        )
    )

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            num_elements=1,
            section_tag=1,
            integration_type="HingeRadau",
            hinge_i_section_tag=1,
            hinge_j_section_tag=1,
            interior_section_tag=2,
            hinge_i_length=0.30,
            hinge_j_length=0.10,
        ),
    )

    element = project.model.elements[result.element_tags[0]]
    assert element.integration_type == "HingeRadau"
    assert element.hinge_i_section_tag == 1
    assert element.hinge_j_section_tag == 1
    assert element.interior_section_tag == 2
    assert element.hinge_i_length == pytest.approx(0.30)
    assert element.hinge_j_length == pytest.approx(0.10)


def test_test_column_hinge_integration_requires_one_physical_member_element():
    project = project_with_section()

    with pytest.raises(ValueError, match="requires Number of elements = 1"):
        build_test_column(
            project,
            TestColumnSpec(
                height=3.0,
                num_elements=2,
                section_tag=1,
                integration_type="HingeRadauTwo",
                hinge_i_length=0.30,
            ),
        )


def test_test_column_radau_allows_subdivided_distributed_plasticity():
    project = project_with_section()

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            num_elements=3,
            section_tag=1,
            integration_type="Radau",
            integration_points=4,
        ),
    )

    assert len(result.element_tags) == 3
    assert all(
        project.model.elements[tag].integration_type == "Radau"
        for tag in result.element_tags
    )


def test_appended_test_column_skips_existing_connection_element_tag():
    project = project_with_section()
    project.add_material(
        MaterialData(1, "Spring", "Elastic", {"E": 1000.0})
    )
    project.model.add_node(1, 10.0, 0.0, 0.0)
    project.model.add_node(2, 10.0, 0.0, 0.0)
    project.add_connection(
        ConnectionData(
            1,
            "Existing spring",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
        )
    )

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            num_elements=1,
            section_tag=1,
            replace_geometry=False,
        ),
    )

    assert result.element_tags == [2]
    assert 1 in project.connections
    assert 1 not in project.model.elements
    assert 2 in project.model.elements



def test_test_column_section_interface_creates_zero_length_section():
    project = project_with_section()
    project.add_section(
        SectionData(
            tag=2,
            name="Base interface section",
            section_type="Elastic",
        )
    )

    result = build_test_column(
        project,
        TestColumnSpec(
            height=3.0,
            axis=3,
            lateral_direction=1,
            planar=True,
            section_tag=1,
            base_interface_type="Section interface",
            base_interface_section_tag=2,
            base_interface_rayleigh=False,
        ),
    )

    connection = project.connections[result.base_connection_tag]
    assert connection.connection_type == "zeroLengthSection"
    assert connection.section_tag == 2
    assert connection.generated_section_tag is None
    assert connection.generated_ground_node == result.base_ground_node
    assert connection.do_rayleigh is False
    assert result.base_section_tag == 2

    assert result.base_constraint_tag is not None
    constraint = project.constraints[result.base_constraint_tag]
    assert constraint.constraint_type == "equalDOF"
    assert constraint.retained_node == result.base_ground_node
    assert constraint.constrained_nodes == [result.base_node]
    assert constraint.dofs == [1]


def test_test_column_section_interface_requires_existing_section():
    project = project_with_section()

    with pytest.raises(ValueError, match="does not exist"):
        build_test_column(
            project,
            TestColumnSpec(
                section_tag=1,
                base_interface_type="Section interface",
                base_interface_section_tag=999,
            ),
        )
