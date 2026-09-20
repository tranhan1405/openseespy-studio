from openseespy_studio.generator import recorder_to_openseespy, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ProjectDatabase, RecorderData


def recorder_model() -> StructuralModel:
    model = StructuralModel("RecorderModel")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.add_element(
        10,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
        integration_points=5,
    )
    return model


def test_recorder_round_trip_and_project_validation():
    project = ProjectDatabase(model=recorder_model())
    node = RecorderData(
        1,
        "Roof displacement",
        "Node",
        target_tags=[2],
        response="disp",
        dofs=[1, 2],
        file_name="recorders/roof_disp.out",
    )
    fiber = RecorderData(
        2,
        "Steel fiber",
        "Fiber",
        target_tags=[10],
        response="stressStrain",
        section_number=1,
        fiber_y=0.2,
        fiber_z=-0.1,
        material_tag=3,
        file_name="recorders/fiber.out",
    )

    project.add_recorder(node)
    project.add_recorder(fiber)
    restored = ProjectDatabase.from_dict(project.to_dict())

    assert restored.recorders[1].target_tags == [2]
    assert restored.recorders[1].dofs == [1, 2]
    assert restored.recorders[2].section_number == 1
    assert restored.recorders[2].material_tag == 3


def test_recorder_rejects_missing_or_incompatible_targets():
    project = ProjectDatabase(model=recorder_model())

    try:
        project.add_recorder(
            RecorderData(
                1,
                "Bad node",
                "Node",
                target_tags=[99],
                response="disp",
                dofs=[1],
            )
        )
    except ValueError as exc:
        assert "missing node" in str(exc)
    else:
        raise AssertionError("Expected missing recorder node to fail")

    project.model.elements[10].element_type = "elasticBeamColumn"
    try:
        project.add_recorder(
            RecorderData(
                2,
                "Bad section",
                "Section",
                target_tags=[10],
                response="force",
                section_number=1,
            )
        )
    except ValueError as exc:
        assert "forceBeamColumn or dispBeamColumn" in str(exc)
    else:
        raise AssertionError("Expected incompatible section recorder to fail")


def test_native_recorder_commands():
    node = RecorderData(
        1,
        "Node recorder",
        "Node",
        target_tags=[2, 3],
        response="accel",
        dofs=[1, 3],
        file_name="recorders/node.out",
    )
    section = RecorderData(
        2,
        "Section recorder",
        "Section",
        target_tags=[10],
        response="force",
        section_number=3,
        file_name="recorders/section.out",
    )
    fiber = RecorderData(
        3,
        "Fiber recorder",
        "Fiber",
        target_tags=[10],
        response="stressStrain",
        section_number=2,
        fiber_y=0.15,
        fiber_z=-0.2,
        material_tag=7,
        file_name="recorders/fiber.out",
    )

    node_text = "\n".join(recorder_to_openseespy(node))
    section_text = "\n".join(recorder_to_openseespy(section))
    fiber_text = "\n".join(recorder_to_openseespy(fiber))

    assert (
        "ops.recorder('Node', '-file', 'recorders/node.out', '-time', "
        "'-node', 2, 3, '-dof', 1, 3, 'accel')"
        in node_text
    )
    assert (
        "ops.recorder('Element', '-file', 'recorders/section.out', '-time', "
        "'-ele', 10, 'section', 3, 'force')"
        in section_text
    )
    assert (
        "'section', 2, 'fiber', 0.15, -0.2, 7, 'stressStrain'"
        in fiber_text
    )


def test_full_generator_emits_recorders_before_analysis():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    recorder = RecorderData(
        1,
        "Node displacement",
        "Node",
        target_tags=[1],
        response="disp",
        dofs=[1],
    )

    code = to_openseespy(model, recorders={1: recorder})

    assert "# Recorders" in code
    assert "# Recorder 1: Node displacement" in code
    assert "ops.recorder('Node'" in code
    assert "os.makedirs(" in code


def test_2d_node_recorder_rejects_dof_above_model_ndf():
    model = StructuralModel("Recorder2D", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0, 0.0)
    project = ProjectDatabase(model=model)

    try:
        project.add_recorder(
            RecorderData(
                1,
                "Bad 2D recorder",
                "Node",
                target_tags=[1],
                response="disp",
                dofs=[4],
            )
        )
    except ValueError as exc:
        assert "ndf=3" in str(exc)
    else:
        raise AssertionError("Expected invalid 2D recorder DOF to fail")
