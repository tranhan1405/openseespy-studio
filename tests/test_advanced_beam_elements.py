from openseespy_studio.generator import (
    section_to_openseespy,
    to_openseespy,
    transformation_to_openseespy,
)
from openseespy_studio.line_mesher import mesh_line_geometry
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    FiberData,
    LineGeometryData,
    MaterialData,
    PointGeometryData,
    ProjectDatabase,
    SectionData,
    TransformationData,
)
from openseespy_studio.validation import validate_project



def _script(project: ProjectDatabase) -> str:
    return to_openseespy(
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
        element_loads=project.element_loads,
        prescribed_displacements=project.prescribed_displacements,
        recorders=project.recorders,
        units=project.units,
        solution_results=project.solution_results,
        nd_materials=project.nd_materials,
    )


def _elastic_section(tag=1):
    return SectionData(
        tag,
        "Elastic shear beam",
        "Elastic",
        {
            "E": 30e9,
            "A": 0.30,
            "Iz": 0.02,
            "Iy": 0.015,
            "G": 12e9,
            "J": 0.01,
            "Avy": 0.24,
            "Avz": 0.22,
        },
    )


def test_elastic_timoshenko_beam_2d_generator():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 3.0, 0.0)
    project.add_section(_elastic_section())
    project.add_transformation(
        TransformationData(1, "Linear", "Linear")
    )
    project.model.add_element(
        1,
        1,
        2,
        element_type="ElasticTimoshenkoBeam",
        section_tag=1,
        transf_tag=1,
        mass_per_length=2.5,
        consistent_mass=True,
    )
    project.validate_element_state(1)
    script = _script(project)
    assert (
        "ops.element('ElasticTimoshenkoBeam', 1, 1, 2, "
        "3e+07, 1.2e+07, 0.3, 0.02, 0.24, 1, "
        "'-mass', 2.5, '-cMass')"
    ) in script


def test_elastic_timoshenko_beam_3d_generator():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 3.0, 0.0, 0.0)
    project.add_section(_elastic_section())
    project.add_transformation(
        TransformationData(
            1,
            "Linear",
            "Linear",
            vecxz=(0.0, 0.0, 1.0),
            orientation_mode="manual",
        )
    )
    project.model.add_element(
        1,
        1,
        2,
        element_type="ElasticTimoshenkoBeam",
        section_tag=1,
        transf_tag=1,
    )
    project.validate_element_state(1)
    script = _script(project)
    assert (
        "ops.element('ElasticTimoshenkoBeam', 1, 1, 2, "
        "3e+07, 1.2e+07, 0.3, 0.01, 0.015, 0.02, "
        "0.24, 0.22, 1)"
    ) in script


def _fiber_int_project():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 3.0)
    project.add_material(
        MaterialData(
            1,
            "Concrete",
            "Concrete02",
            {
                "fpc": -30e6,
                "epsc0": -0.002,
                "fpcu": -6e6,
                "epsU": -0.006,
                "lambda": 0.1,
                "ft": 3e6,
                "Ets": 2e8,
            },
        )
    )
    project.add_material(
        MaterialData(
            1001,
            "Vertical steel",
            "Steel02",
            {"Fy": 500e6, "E0": 200e9, "b": 0.01},
        )
    )
    project.add_material(
        MaterialData(
            1002,
            "Horizontal steel",
            "Steel02",
            {"Fy": 500e6, "E0": 200e9, "b": 0.01},
        )
    )
    section = SectionData(
        2,
        "FiberInt wall strip",
        "FiberInt",
        {
            "nStrip1": 1,
            "thick1": 0.20,
            "nStrip2": 1,
            "thick2": 0.15,
            "nStrip3": 1,
            "thick3": 0.20,
        },
        fibers=[
            FiberData(-0.5, 0.0, 0.06, 1),
            FiberData(-0.5, 0.0, 0.002, 1001),
            FiberData(0.0, 0.0, 0.05, 1),
            FiberData(0.0, 0.0, 0.002, 1001),
            FiberData(0.5, 0.0, 0.06, 1),
            FiberData(0.5, 0.0, 0.002, 1001),
        ],
        horizontal_fibers=[
            FiberData(0.0, 0.0, 0.0015, 1002),
        ],
    )
    project.add_section(section)
    project.add_transformation(
        TransformationData(1, "LinearInt", "LinearInt")
    )
    return project


def test_fiber_int_and_disp_beam_column_int_generation():
    project = _fiber_int_project()
    project.model.add_element(
        7,
        1,
        2,
        element_type="dispBeamColumnInt",
        section_tag=2,
        transf_tag=1,
        integration_points=3,
        beam_center_ratio=0.4,
        mass_per_length=1.25,
    )
    project.validate_element_state(7)
    script = _script(project)
    assert (
        "ops.section('FiberInt', 2, '-NStrip', "
        "1, 0.2, 1, 0.15, 1, 0.2)"
    ) in script
    assert "ops.Hfiber(0, 0, 0.0015, 1002)" in script
    assert "ops.geomTransf('LinearInt', 1)" in script
    assert (
        "ops.element('dispBeamColumnInt', 7, 1, 2, 3, 2, 1, "
        "0.4, '-mass', 1.25)"
    ) in script


def test_disp_beam_column_int_rejects_wrong_section_and_transform():
    project = _fiber_int_project()
    project.add_section(_elastic_section(3))
    project.model.add_element(
        8,
        1,
        2,
        element_type="dispBeamColumnInt",
        section_tag=3,
        transf_tag=1,
        integration_points=3,
        beam_center_ratio=0.4,
    )
    try:
        project.validate_element_state(8)
    except ValueError as exc:
        assert "FiberInt" in str(exc)
    else:
        raise AssertionError("dispBeamColumnInt accepted a non-FiberInt section")

    project.model.elements[8].section_tag = 2
    project.transformations[1] = TransformationData(1, "Linear", "Linear")
    try:
        project.validate_element_state(8)
    except ValueError as exc:
        assert "LinearInt" in str(exc)
    else:
        raise AssertionError("dispBeamColumnInt accepted a non-LinearInt transform")


def test_disp_beam_column_int_round_trip_preserves_crot():
    project = _fiber_int_project()
    project.model.add_element(
        9,
        1,
        2,
        element_type="dispBeamColumnInt",
        section_tag=2,
        transf_tag=1,
        integration_points=5,
        beam_center_ratio=0.37,
    )
    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.model.elements[9].beam_center_ratio == 0.37
    assert restored.sections[2].horizontal_fibers[0].material_tag == 1002
    assert restored.transformations[1].transformation_type == "LinearInt"


def test_disp_beam_column_int_is_2d_only():
    model = StructuralModel(ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    try:
        model.add_element(
            1,
            1,
            2,
            element_type="dispBeamColumnInt",
            section_tag=1,
            transf_tag=1,
        )
    except ValueError as exc:
        assert "ndm=2/ndf=3" in str(exc)
    else:
        raise AssertionError("dispBeamColumnInt accepted a 3D model")

def test_model_check_reports_disp_beam_column_int_transform_mismatch():
    project = _fiber_int_project()
    project.model.add_element(
        10,
        1,
        2,
        element_type="dispBeamColumnInt",
        section_tag=2,
        transf_tag=1,
        integration_points=3,
        beam_center_ratio=0.4,
    )
    project.transformations[1] = TransformationData(1, "Linear", "Linear")

    issues = validate_project(project)

    assert any(
        issue.category == "Transformation"
        and "LinearInt" in issue.message
        and issue.entity_tag == 10
        for issue in issues
    )


def test_model_check_requires_elastic_section_for_timoshenko_beam():
    project = _fiber_int_project()
    project.transformations[1] = TransformationData(1, "Linear", "Linear")
    project.model.add_element(
        11,
        1,
        2,
        element_type="ElasticTimoshenkoBeam",
        section_tag=2,
        transf_tag=1,
    )

    issues = validate_project(project)

    assert any(
        issue.category == "Element formulation"
        and "Elastic Section" in issue.suggestion
        and issue.entity_tag == 11
        for issue in issues
    )


def test_disp_beam_column_int_line_mesh_preserves_crot_and_one_point():
    project = _fiber_int_project()
    project.add_point(PointGeometryData(1, "P1", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "P2", (0.0, 3.0, 0.0)))
    project.add_line(
        LineGeometryData(
            1,
            "Interaction wall line",
            1,
            2,
            divisions=2,
            element_type="dispBeamColumnInt",
            section_tag=2,
            transformation_tag=1,
            integration_points=1,
            center_rotation=0.33,
        )
    )

    result = mesh_line_geometry(project, 1)

    assert len(result.element_tags) == 2
    assert all(
        project.model.elements[tag].element_type == "dispBeamColumnInt"
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].integration_points == 1
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].beam_center_ratio == 0.33
        for tag in result.element_tags
    )


def test_disp_beam_column_int_line_recipe_rejects_wrong_section():
    project = _fiber_int_project()
    project.add_section(_elastic_section(3))
    project.add_point(PointGeometryData(1, "P1", (0.0, 0.0, 0.0)))
    project.add_point(PointGeometryData(2, "P2", (0.0, 3.0, 0.0)))

    try:
        project.add_line(
            LineGeometryData(
                1,
                "Bad interaction line",
                1,
                2,
                element_type="dispBeamColumnInt",
                section_tag=3,
                transformation_tag=1,
                integration_points=3,
                center_rotation=0.4,
            )
        )
    except ValueError as exc:
        assert "FiberInt" in str(exc)
    else:
        raise AssertionError(
            "dispBeamColumnInt Line recipe accepted a non-FiberInt section"
        )

