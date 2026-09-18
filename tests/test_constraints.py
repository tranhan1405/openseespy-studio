from openseespy_studio.generator import constraint_to_openseespy, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import ConstraintData, ProjectDatabase


def model_with_nodes() -> StructuralModel:
    model = StructuralModel()
    for tag in range(1, 6):
        model.add_node(tag, float(tag - 1), 0.0, 0.0)
    return model


def test_constraint_project_round_trip():
    project = ProjectDatabase(model=model_with_nodes())
    project.add_constraint(
        ConstraintData(
            tag=1,
            name="Floor equal DOF",
            constraint_type="equalDOF",
            retained_node=1,
            constrained_nodes=[2, 3, 4],
            dofs=(1, 2),
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())
    constraint = restored.constraints[1]

    assert constraint.constraint_type == "equalDOF"
    assert constraint.retained_node == 1
    assert constraint.constrained_nodes == [2, 3, 4]
    assert constraint.dofs == (1, 2)


def test_missing_constraint_node_is_rejected():
    project = ProjectDatabase(model=model_with_nodes())

    try:
        project.add_constraint(
            ConstraintData(
                tag=1,
                name="Bad",
                constraint_type="rigidLink",
                retained_node=1,
                constrained_nodes=[99],
                link_type="beam",
            )
        )
    except ValueError as exc:
        assert "missing node" in str(exc)
    else:
        raise AssertionError("Expected missing constraint node validation")


def test_equal_dof_generator():
    constraint = ConstraintData(
        tag=1,
        name="Equal",
        constraint_type="equalDOF",
        retained_node=1,
        constrained_nodes=[2, 3],
        dofs=(1, 2, 6),
    )

    lines = constraint_to_openseespy(constraint)

    assert "ops.equalDOF(1, 2, 1, 2, 6)" in lines
    assert "ops.equalDOF(1, 3, 1, 2, 6)" in lines


def test_rigid_link_generator():
    constraint = ConstraintData(
        tag=2,
        name="Rigid link",
        constraint_type="rigidLink",
        retained_node=1,
        constrained_nodes=[2, 3],
        link_type="beam",
    )

    lines = constraint_to_openseespy(constraint)

    assert "ops.rigidLink('beam', 1, 2)" in lines
    assert "ops.rigidLink('beam', 1, 3)" in lines


def test_rigid_diaphragm_generator():
    constraint = ConstraintData(
        tag=3,
        name="Floor 2",
        constraint_type="rigidDiaphragm",
        retained_node=1,
        constrained_nodes=[2, 3, 4],
        perp_dirn=3,
    )

    lines = constraint_to_openseespy(constraint)

    assert "ops.rigidDiaphragm(3, 1, 2, 3, 4)" in lines


def test_full_script_contains_constraints():
    model = model_with_nodes()
    constraint = ConstraintData(
        tag=1,
        name="Equal",
        constraint_type="equalDOF",
        retained_node=1,
        constrained_nodes=[2],
        dofs=(1, 2, 3),
    )

    script = to_openseespy(model, constraints={1: constraint})

    assert "# Multi-point constraints" in script
    assert "ops.equalDOF(1, 2, 1, 2, 3)" in script


def test_prune_constraints_after_node_deletion():
    project = ProjectDatabase(model=model_with_nodes())
    project.add_constraint(
        ConstraintData(
            tag=1,
            name="Equal",
            constraint_type="equalDOF",
            retained_node=1,
            constrained_nodes=[2, 3],
            dofs=(1, 2),
        )
    )
    project.add_constraint(
        ConstraintData(
            tag=2,
            name="Link",
            constraint_type="rigidLink",
            retained_node=4,
            constrained_nodes=[5],
            link_type="bar",
        )
    )

    project.model.remove_node(3, cascade=True)
    project.model.remove_node(4, cascade=True)
    removed = project.prune_constraints()

    assert removed == [2]
    assert project.constraints[1].constrained_nodes == [2]
