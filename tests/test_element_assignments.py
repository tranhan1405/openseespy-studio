from openseespy_studio.generator import FrameGridSpec, generate_frame_grid, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ElementLoadData,
    FiberData,
    LoadPatternData,
    MaterialData,
    ProjectDatabase,
    RecorderData,
    SectionData,
    TimeSeriesData,
    TransformationData,
)


def elastic_section(tag: int = 3) -> SectionData:
    return SectionData(
        tag=tag,
        name="Assigned Elastic",
        section_type="Elastic",
        parameters={
            "E": 210e9,
            "A": 0.025,
            "Iz": 9.0e-5,
            "Iy": 7.0e-5,
            "G": 80e9,
            "J": 6.0e-5,
        },
    )


def transformation(tag: int = 4) -> TransformationData:
    return TransformationData(
        tag=tag,
        name="PDelta",
        transformation_type="PDelta",
        vecxz=(0.0, 1.0, 0.0),
    )


def test_bulk_assign_and_clear_section_and_transformation():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_node(3, 2, 0, 0)
    model.add_element(1, 1, 2)
    model.add_element(2, 2, 3)

    assert model.assign_section({1, 2}, 3) == {1, 2}
    assert model.assign_transformation({1, 2}, 4) == {1, 2}
    assert model.elements[1].section_tag == 3
    assert model.elements[2].transf_tag == 4

    model.assign_section({1}, None)
    model.assign_transformation({2}, None)

    assert model.elements[1].section_tag is None
    assert model.elements[2].transf_tag is None


def test_frame_grid_assigns_column_and_beam_properties():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        column_section_tag=10,
        beam_section_tag=20,
        column_transf_tag=30,
        beam_transf_tag=40,
    )

    generate_frame_grid(model, spec)

    columns = [e for e in model.elements.values() if e.group == "column"]
    beams = [e for e in model.elements.values() if e.group.startswith("beam")]

    assert columns
    assert beams
    assert all(e.section_tag == 10 for e in columns)
    assert all(e.transf_tag == 30 for e in columns)
    assert all(e.section_tag == 20 for e in beams)
    assert all(e.transf_tag == 40 for e in beams)


def test_generator_uses_assigned_elastic_section_and_transformation():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_element(
        1,
        1,
        2,
        element_type="elasticBeamColumn",
        section_tag=3,
        transf_tag=4,
    )

    section = elastic_section(3)
    transf = transformation(4)

    script = to_openseespy(
        model,
        sections={3: section},
        transformations={4: transf},
    )

    assert "ops.geomTransf('PDelta', 4, 0, 1, 0)" in script
    assert (
        "ops.element('elasticBeamColumn', 1, 1, 2, "
        "0.025, 2.1e+08, 8e+07, 6e-05, 7e-05, 9e-05, 4)"
        in script
    )



def test_force_beam_column_uses_real_beam_integration_and_fiber_section():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 3, 0, 0)
    model.add_element(
        1,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=2,
        transf_tag=4,
        integration_type="Lobatto",
        integration_points=6,
        force_max_iter=20,
        force_tolerance=1.0e-10,
    )
    materials = {
        1: MaterialData(
            1,
            "Steel",
            "Elastic",
            {"E": 200e9},
        )
    }
    sections = {
        2: SectionData(
            2,
            "Fiber",
            "Fiber",
            {"GJ": 1.0e6},
            fibers=[
                FiberData(-0.1, 0.0, 1.0e-4, 1),
                FiberData(0.1, 0.0, 1.0e-4, 1),
            ],
        )
    }
    transformations = {
        4: TransformationData(
            4,
            "Linear",
            "Linear",
            (0.0, 0.0, 1.0),
        )
    }

    script = to_openseespy(
        model,
        materials=materials,
        sections=sections,
        transformations=transformations,
    )

    assert "ops.section('Fiber', 2, '-GJ', 1e+06)" in script
    assert "ops.beamIntegration('Lobatto', 1, 2, 6)" in script
    assert (
        "ops.element('forceBeamColumn', 1, 1, 2, 4, 1, "
        "'-iter', 20, 1e-10)"
        in script
    )
    assert "full nonlinear element generation is not implemented" not in script


def test_disp_beam_column_uses_real_beam_integration():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 3, 0, 0)
    model.add_element(
        8,
        1,
        2,
        element_type="dispBeamColumn",
        section_tag=3,
        transf_tag=4,
        integration_type="Legendre",
        integration_points=5,
        mass_per_length=2.5,
        consistent_mass=True,
    )
    sections = {3: elastic_section(3)}
    transformations = {4: transformation(4)}

    script = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
    )

    assert "ops.beamIntegration('Legendre', 8, 3, 5)" in script
    assert (
        "ops.element('dispBeamColumn', 8, 1, 2, 4, 8, "
        "'-cMass', '-mass', 2.5)"
        in script
    )


def test_unknown_element_is_not_silently_replaced_by_elastic_beam():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 1, 0, 0)
    model.add_element(
        1,
        1,
        2,
        element_type="unsupportedElement",
        section_tag=3,
        transf_tag=4,
    )

    script = to_openseespy(
        model,
        sections={3: elastic_section(3)},
        transformations={4: transformation(4)},
    )

    assert "type 'unsupportedElement' is not implemented" in script
    assert "ops.element('elasticBeamColumn', 1" not in script


def test_force_beam_column_generates_hinge_radau_integration():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 0, 0, 3)
    model.add_element(
        20,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=2,
        transf_tag=4,
        integration_type="HingeRadau",
        hinge_i_section_tag=2,
        hinge_j_section_tag=2,
        interior_section_tag=3,
        hinge_i_length=0.35,
        hinge_j_length=0.15,
    )
    sections = {
        2: elastic_section(2),
        3: elastic_section(3),
    }
    transformations = {4: transformation(4)}

    script = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
    )

    assert (
        "ops.beamIntegration('HingeRadau', 20, 2, 0.35, 2, 0.15, 3)"
        in script
    )
    assert "ops.element('forceBeamColumn', 20, 1, 2, 4, 20" in script


def test_force_beam_column_generates_radau_distributed_integration():
    model = StructuralModel()
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 0, 0, 3)
    model.add_element(
        21,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=3,
        transf_tag=4,
        integration_type="Radau",
        integration_points=5,
    )

    script = to_openseespy(
        model,
        sections={3: elastic_section(3)},
        transformations={4: transformation(4)},
    )

    assert "ops.beamIntegration('Radau', 21, 3, 5)" in script


def _assignment_project(
    *,
    element_type: str = "elasticBeamColumn",
) -> ProjectDatabase:
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type=element_type,
        section_tag=1,
        transf_tag=1,
        integration_type="Lobatto",
        integration_points=5,
    )
    project = ProjectDatabase(name="Assignments", model=model)
    project.add_section(elastic_section(1))
    project.add_transformation(
        TransformationData(1, "Good", "Linear", (0.0, 0.0, 1.0))
    )
    return project


def test_bulk_formulation_rolls_back_when_existing_recorder_becomes_invalid():
    project = _assignment_project(element_type="forceBeamColumn")
    project.add_recorder(
        RecorderData(
            1,
            "Section force",
            "Section",
            target_tags=[1],
            response="force",
            section_number=1,
        )
    )

    try:
        project.assign_element_formulation(
            {1},
            element_type="elasticBeamColumn",
            integration_type="Lobatto",
            integration_points=5,
            force_max_iter=10,
            force_tolerance=1.0e-12,
            mass_per_length=0.0,
            consistent_mass=False,
        )
    except ValueError as exc:
        assert "Section/Fiber recorders require" in str(exc)
    else:
        raise AssertionError("Expected dependent-recorder validation failure")

    assert project.model.elements[1].element_type == "forceBeamColumn"


def test_bulk_section_assignment_rejects_fiber_on_elastic_beam_and_rolls_back():
    project = _assignment_project()
    project.add_section(
        SectionData(
            2,
            "Fiber",
            "Fiber",
            {"GJ": 1.0e6},
            fibers=[],
        )
    )

    try:
        project.assign_section_to_elements({1}, 2)
    except ValueError as exc:
        assert "requires an Elastic section" in str(exc)
    else:
        raise AssertionError("Expected elastic-section compatibility failure")

    assert project.model.elements[1].section_tag == 1


def test_bulk_transformation_assignment_rejects_parallel_axis_and_rolls_back():
    project = _assignment_project()
    project.add_transformation(
        TransformationData(2, "Parallel", "Linear", (1.0, 0.0, 0.0))
    )

    try:
        project.assign_transformation_to_elements({1}, 2)
    except ValueError as exc:
        assert "parallel to element 1" in str(exc)
    else:
        raise AssertionError("Expected transformation-axis validation failure")

    assert project.model.elements[1].transf_tag == 1


def test_clear_section_rolls_back_when_selfweight_depends_on_it():
    project = _assignment_project()
    project.add_time_series(TimeSeriesData(1, "Gravity", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Gravity", "Plain", time_series_tag=1)
    )
    project.add_element_load(
        ElementLoadData(
            1,
            "Self weight",
            1,
            1,
            load_type="SelfWeight",
            density_override=7850.0,
        )
    )

    try:
        project.assign_section_to_elements({1}, None)
    except ValueError as exc:
        assert "SelfWeight requires the target element to have a section" in str(exc)
    else:
        raise AssertionError("Expected SelfWeight section dependency failure")

    assert project.model.elements[1].section_tag == 1


def test_clear_transformation_rolls_back_when_selfweight_depends_on_it():
    project = _assignment_project()
    project.add_time_series(TimeSeriesData(1, "Gravity", "Linear"))
    project.add_load_pattern(
        LoadPatternData(1, "Gravity", "Plain", time_series_tag=1)
    )
    project.add_element_load(
        ElementLoadData(
            1,
            "Self weight",
            1,
            1,
            load_type="SelfWeight",
            density_override=7850.0,
        )
    )

    try:
        project.assign_transformation_to_elements({1}, None)
    except ValueError as exc:
        assert "SelfWeight requires a geometric transformation" in str(exc)
    else:
        raise AssertionError(
            "Expected SelfWeight transformation dependency failure"
        )

    assert project.model.elements[1].transf_tag == 1
