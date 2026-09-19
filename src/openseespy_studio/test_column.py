from __future__ import annotations

from dataclasses import dataclass, field

from .model import StructuralModel
from .project import (
    LoadPatternData,
    NodalLoadData,
    PrescribedDisplacementData,
    ProjectDatabase,
    TimeSeriesData,
    TransformationData,
)


@dataclass(slots=True)
class TestColumnSpec:
    height: float = 3.0
    num_elements: int = 1
    axis: int = 3
    lateral_direction: int = 1
    planar: bool = True
    replace_geometry: bool = True

    section_tag: int | None = None
    transformation_tag: int | None = None
    transformation_type: str = "PDelta"

    element_type: str = "forceBeamColumn"
    integration_type: str = "Lobatto"
    integration_points: int = 5
    force_max_iter: int = 10
    force_tolerance: float = 1.0e-12

    base_support: str = "Fixed"
    top_support: str = "Free"

    top_mass: float = 0.0
    top_mass_directions: tuple[int, ...] = (1, 2, 3)

    axial_load: float = 0.0
    lateral_reference_load: float = 0.0
    prescribed_displacement: float = 0.0

    name_prefix: str = "Test Column"


@dataclass(slots=True)
class TestColumnBuildResult:
    node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    base_node: int = 0
    top_node: int = 0
    transformation_tag: int | None = None
    created_transformation: bool = False
    axial_pattern_tag: int | None = None
    lateral_pattern_tag: int | None = None
    prescribed_pattern_tag: int | None = None


def _support_fixity(name: str) -> tuple[int, ...]:
    if name == "Fixed":
        return (1, 1, 1, 1, 1, 1)
    if name == "Pinned":
        return (1, 1, 1, 0, 0, 0)
    if name == "Free":
        return (0, 0, 0, 0, 0, 0)
    raise ValueError(f"Unsupported test-column support: {name}")


def _merge_fixity(
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> tuple[int, ...]:
    return tuple(
        1 if bool(a) or bool(b) else 0
        for a, b in zip(left, right)
    )


def _planar_fixity(
    axis: int,
    lateral_direction: int,
) -> tuple[int, ...]:
    """Keep the two in-plane translations and rotation about plane normal."""
    axis = int(axis)
    lateral_direction = int(lateral_direction)
    if axis not in (1, 2, 3) or lateral_direction not in (1, 2, 3):
        raise ValueError("Column and lateral axes must be X, Y, or Z.")
    if axis == lateral_direction:
        raise ValueError(
            "Planar test needs a lateral direction different from the "
            "column axis."
        )
    normal = ({1, 2, 3} - {axis, lateral_direction}).pop()
    fixity = [0, 0, 0, 0, 0, 0]
    fixity[normal - 1] = 1
    # Rotations about the two in-plane axes are out-of-plane beam rotations.
    fixity[axis + 2] = 1
    fixity[lateral_direction + 2] = 1
    return tuple(fixity)


def _safe_vecxz(axis: int) -> tuple[float, float, float]:
    if int(axis) == 3:
        return (1.0, 0.0, 0.0)
    return (0.0, 0.0, 1.0)


def _same_vector(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
    tol: float = 1.0e-12,
) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(left, right))


def _resolve_transformation(
    project: ProjectDatabase,
    spec: TestColumnSpec,
) -> tuple[int, bool]:
    if spec.transformation_tag is not None:
        tag = int(spec.transformation_tag)
        if tag not in project.transformations:
            raise ValueError(
                f"Transformation {tag} does not exist in the project."
            )
        return tag, False

    vecxz = _safe_vecxz(spec.axis)
    for tag in sorted(project.transformations):
        item = project.transformations[tag]
        if (
            item.transformation_type == spec.transformation_type
            and _same_vector(item.vecxz, vecxz)
        ):
            return tag, False

    tag = project.next_transformation_tag()
    project.add_transformation(
        TransformationData(
            tag=tag,
            name=f"{spec.name_prefix} {spec.transformation_type}",
            transformation_type=spec.transformation_type,
            vecxz=vecxz,
        )
    )
    return tag, True


def _next_free_tag(store: dict[int, object], start: int = 1) -> int:
    tag = max(int(start), 1)
    while tag in store:
        tag += 1
    return tag


def _add_plain_pattern(
    project: ProjectDatabase,
    *,
    name: str,
) -> int:
    series_tag = project.next_time_series_tag()
    project.add_time_series(
        TimeSeriesData(
            tag=series_tag,
            name=f"{name} Series",
            series_type="Linear",
            factor=1.0,
        )
    )
    pattern_tag = project.next_load_pattern_tag()
    project.add_load_pattern(
        LoadPatternData(
            tag=pattern_tag,
            name=name,
            pattern_type="Plain",
            time_series_tag=series_tag,
        )
    )
    return pattern_tag


def _axis_vector(
    dof: int,
    value: float,
) -> tuple[float, float, float, float, float, float]:
    values = [0.0] * 6
    values[int(dof) - 1] = float(value)
    return tuple(values)


def _clear_model_linked_data(project: ProjectDatabase) -> None:
    """Clear objects that would otherwise be accidentally rebound by tag."""
    project.selection_sets.clear()
    project.constraints.clear()
    project.connections.clear()
    project.time_series.clear()
    project.load_patterns.clear()
    project.nodal_loads.clear()
    project.prescribed_displacements.clear()
    project.element_loads.clear()
    project.mass_sources.clear()
    project.analyses.clear()
    project.recorders.clear()
    project.solution_results.clear()
    project.active_analysis_tag = None


def build_test_column(
    project: ProjectDatabase,
    spec: TestColumnSpec,
) -> TestColumnBuildResult:
    """Create a one-line column specimen and optional test loading scaffold."""
    height = float(spec.height)
    count = int(spec.num_elements)
    axis = int(spec.axis)
    lateral = int(spec.lateral_direction)

    if height <= 0.0:
        raise ValueError("Test-column height must be positive.")
    if count < 1:
        raise ValueError("Test column needs at least one element.")
    if axis not in (1, 2, 3):
        raise ValueError("Column axis must be X, Y, or Z.")
    if lateral not in (1, 2, 3):
        raise ValueError("Lateral direction must be X, Y, or Z.")
    if lateral == axis and (
        spec.planar
        or abs(float(spec.lateral_reference_load)) > 0.0
        or abs(float(spec.prescribed_displacement)) > 0.0
    ):
        raise ValueError(
            "Lateral direction must differ from the column axis."
        )
    if spec.section_tag is not None and int(spec.section_tag) not in project.sections:
        raise ValueError(
            f"Section {spec.section_tag} does not exist in the project."
        )
    if spec.element_type not in {
        "elasticBeamColumn",
        "forceBeamColumn",
        "dispBeamColumn",
    }:
        raise ValueError(
            f"Unsupported test-column element type: {spec.element_type}"
        )
    if int(spec.integration_points) < 2:
        raise ValueError("Beam integration needs at least 2 points.")
    if float(spec.top_mass) < 0.0:
        raise ValueError("Top mass cannot be negative.")
    if any(int(dof) not in (1, 2, 3) for dof in spec.top_mass_directions):
        raise ValueError("Top-mass directions must be UX, UY, or UZ.")

    if spec.replace_geometry:
        _clear_model_linked_data(project)
        project.model.clear()
        project.model.ndm = 3
        project.model.ndf = 6
    elif int(project.model.ndm) != 3 or int(project.model.ndf) != 6:
        raise ValueError(
            "Appending a Quick 1D Column currently requires a 3D/6DOF "
            "Studio model. Use standalone/replace mode for other models."
        )

    model: StructuralModel = project.model
    node_tag = model.next_node_tag()
    element_tag = model.next_element_tag()

    transformation_tag, created_transformation = _resolve_transformation(
        project,
        spec,
    )

    node_tags: list[int] = []
    for index in range(count + 1):
        distance = height * index / count
        xyz = [0.0, 0.0, 0.0]
        xyz[axis - 1] = distance
        tag = node_tag + index
        if tag in model.nodes:
            tag = model.next_node_tag()
            node_tag = tag - index
        model.add_node(tag, *xyz)
        node_tags.append(tag)

    element_tags: list[int] = []
    next_element = element_tag
    for index in range(count):
        while next_element in model.elements:
            next_element += 1
        model.add_element(
            next_element,
            node_tags[index],
            node_tags[index + 1],
            element_type=spec.element_type,
            section_tag=spec.section_tag,
            transf_tag=transformation_tag,
            group="test-column",
            integration_type=spec.integration_type,
            integration_points=int(spec.integration_points),
            force_max_iter=int(spec.force_max_iter),
            force_tolerance=float(spec.force_tolerance),
        )
        element_tags.append(next_element)
        next_element += 1

    plane = (
        _planar_fixity(axis, lateral)
        if spec.planar
        else (0, 0, 0, 0, 0, 0)
    )
    for tag in node_tags:
        model.set_fixity(tag, plane)
    model.set_fixity(
        node_tags[0],
        _merge_fixity(plane, _support_fixity(spec.base_support)),
    )
    model.set_fixity(
        node_tags[-1],
        _merge_fixity(plane, _support_fixity(spec.top_support)),
    )

    if float(spec.top_mass) > 0.0:
        values = [0.0] * 6
        for dof in sorted(set(int(value) for value in spec.top_mass_directions)):
            values[dof - 1] = float(spec.top_mass)
        model.set_mass(node_tags[-1], values)

    result = TestColumnBuildResult(
        node_tags=node_tags,
        element_tags=element_tags,
        base_node=node_tags[0],
        top_node=node_tags[-1],
        transformation_tag=transformation_tag,
        created_transformation=created_transformation,
    )

    if abs(float(spec.axial_load)) > 0.0:
        pattern_tag = _add_plain_pattern(
            project,
            name=f"{spec.name_prefix} Axial",
        )
        project.add_nodal_load(
            NodalLoadData(
                tag=project.next_nodal_load_tag(),
                name=f"{spec.name_prefix} Axial Load",
                pattern_tag=pattern_tag,
                node_tag=result.top_node,
                values=_axis_vector(axis, -abs(float(spec.axial_load))),
            )
        )
        result.axial_pattern_tag = pattern_tag

    if abs(float(spec.lateral_reference_load)) > 0.0:
        pattern_tag = _add_plain_pattern(
            project,
            name=f"{spec.name_prefix} Lateral Reference",
        )
        project.add_nodal_load(
            NodalLoadData(
                tag=project.next_nodal_load_tag(),
                name=f"{spec.name_prefix} Lateral Reference Load",
                pattern_tag=pattern_tag,
                node_tag=result.top_node,
                values=_axis_vector(
                    lateral,
                    float(spec.lateral_reference_load),
                ),
            )
        )
        result.lateral_pattern_tag = pattern_tag

    if abs(float(spec.prescribed_displacement)) > 0.0:
        if model.nodes[result.top_node].fixity[lateral - 1]:
            raise ValueError(
                "Top support/planar restraint fixes the selected prescribed "
                "displacement DOF."
            )
        pattern_tag = _add_plain_pattern(
            project,
            name=f"{spec.name_prefix} Prescribed Displacement",
        )
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                tag=project.next_prescribed_displacement_tag(),
                name=f"{spec.name_prefix} Top Displacement",
                pattern_tag=pattern_tag,
                node_tag=result.top_node,
                dof=lateral,
                value=float(spec.prescribed_displacement),
            )
        )
        result.prescribed_pattern_tag = pattern_tag

    return result
