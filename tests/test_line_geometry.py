from __future__ import annotations

from openseespy_studio.line_mesher import mesh_line_geometry
from openseespy_studio.project import (
    LineGeometryData,
    MaterialData,
    PointGeometryData,
    ProjectDatabase,
    SectionData,
    TransformationData,
)


def _frame_project() -> ProjectDatabase:
    project = ProjectDatabase(name="line-mesh")
    project.add_section(SectionData(1, "Frame section", "Elastic"))
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "B", (4.0, 0.0, 0.0)))
    return project


def test_point_line_geometry_round_trip():
    project = _frame_project()
    project.add_line(
        LineGeometryData(
            1,
            "Beam axis",
            1,
            2,
            divisions=4,
            section_tag=1,
            transformation_tag=1,
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.points[1].xyz == (0.0, 0.0, 0.0)
    assert restored.points[2].xyz == (4.0, 0.0, 0.0)
    assert restored.lines[1].point_i == 1
    assert restored.lines[1].point_j == 2
    assert restored.lines[1].divisions == 4
    assert restored.lines[1].element_family == "Frame"


def test_line_mesher_generates_frame_chain():
    project = _frame_project()
    project.add_line(
        LineGeometryData(
            1,
            "Beam axis",
            1,
            2,
            divisions=4,
            element_family="Frame",
            element_type="dispBeamColumn",
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = mesh_line_geometry(project, 1)

    assert result.divisions == 4
    assert len(result.node_tags) == 5
    assert len(result.element_tags) == 4
    assert [project.model.nodes[tag].xyz[0] for tag in result.node_tags] == [
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
    ]
    assert all(
        project.model.elements[tag].element_type == "dispBeamColumn"
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].section_tag == 1
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].transf_tag == 1
        for tag in result.element_tags
    )
    assert project.lines[1].generated_element_tags == result.element_tags


def test_line_mesher_target_size_rounds_up():
    project = _frame_project()
    project.add_line(
        LineGeometryData(
            1,
            "Beam axis",
            1,
            2,
            mesh_mode="target_size",
            target_size=1.5,
            section_tag=1,
            transformation_tag=1,
        )
    )

    result = mesh_line_geometry(project, 1)

    assert result.divisions == 3
    assert len(result.element_tags) == 3


def test_line_mesher_generates_truss_chain():
    project = ProjectDatabase(name="truss-line")
    project.add_material(
        MaterialData(
            3,
            "Elastic steel",
            "Elastic",
            parameters={"E": 200.0e9},
        )
    )
    project.add_point(PointGeometryData(1, "A", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "B", (3.0, 0.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Tie",
            1,
            2,
            divisions=3,
            element_family="Truss",
            element_type="truss",
            material_tag=3,
            area=0.002,
        )
    )

    result = mesh_line_geometry(project, 1)

    assert len(result.element_tags) == 3
    assert all(
        project.model.elements[tag].element_type == "truss"
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].truss_material_tag == 3
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].truss_area == 0.002
        for tag in result.element_tags
    )


def test_line_mesher_reuses_existing_end_nodes():
    project = _frame_project()
    project.model.add_node(10, 0.0, 0.0, 0.0)
    project.model.add_node(11, 4.0, 0.0, 0.0)
    project.add_line(
        LineGeometryData(
            1,
            "Beam axis",
            1,
            2,
            divisions=1,
            section_tag=1,
            transformation_tag=1,
            reuse_existing_nodes=True,
        )
    )

    result = mesh_line_geometry(project, 1)

    assert result.node_tags == [10, 11]
    assert result.created_node_tags == []
    assert result.reused_node_tags == [10, 11]
    assert len(result.element_tags) == 1
