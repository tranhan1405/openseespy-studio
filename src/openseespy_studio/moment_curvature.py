from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math

from .model import StructuralModel
from .project import (
    AnalysisSettingsData,
    ConnectionData,
    LoadPatternData,
    NodalLoadData,
    ProjectDatabase,
    TimeSeriesData,
)


@dataclass(frozen=True, slots=True)
class MomentCurvatureSpec:
    section_tag: int
    axis: str = "Mz"
    axial_load: float = 0.0
    max_curvature: float = 0.02
    increments: int = 100

    def __post_init__(self) -> None:
        if int(self.section_tag) <= 0:
            raise ValueError("Section tag must be positive.")
        if str(self.axis) not in {"My", "Mz"}:
            raise ValueError("Bending axis must be My or Mz.")
        if not math.isfinite(float(self.axial_load)):
            raise ValueError("Axial load must be finite.")
        if (
            not math.isfinite(float(self.max_curvature))
            or float(self.max_curvature) <= 0.0
        ):
            raise ValueError("Maximum curvature must be finite and positive.")
        if int(self.increments) <= 0:
            raise ValueError("Number of increments must be positive.")


def build_moment_curvature_project(
    source: ProjectDatabase,
    spec: MomentCurvatureSpec,
) -> ProjectDatabase:
    """Build an isolated classic zeroLengthSection M-kappa test project.

    The returned project owns only the temporary analysis geometry/loading.
    The source project's material definitions and selected Section are copied
    so running the research workflow cannot modify the user's structural model.
    Numeric loads and curvature are already in the active project unit system.
    """
    section_tag = int(spec.section_tag)
    section = source.sections.get(section_tag)
    if section is None:
        raise ValueError(f"Section {section_tag} does not exist.")

    ndm = int(source.model.ndm)
    if ndm not in {2, 3}:
        raise ValueError("Moment-curvature workflow requires ndm=2 or ndm=3.")
    axis = str(spec.axis)
    if ndm == 2 and axis != "Mz":
        raise ValueError("A 2D model supports only the Mz bending axis.")

    ndf = 3 if ndm == 2 else 6
    model = StructuralModel(
        name=f"Moment-Curvature Section {section_tag}",
        ndm=ndm,
        ndf=ndf,
    )
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 0.0)

    if ndm == 2:
        control_dof = 3
        model.set_fixity(1, (1, 1, 1))
        model.set_fixity(2, (0, 1, 0))
    elif axis == "My":
        control_dof = 5
        model.set_fixity(1, (1, 1, 1, 1, 1, 1))
        model.set_fixity(2, (0, 1, 1, 1, 0, 1))
    else:
        control_dof = 6
        model.set_fixity(1, (1, 1, 1, 1, 1, 1))
        model.set_fixity(2, (0, 1, 1, 1, 1, 0))

    project = ProjectDatabase(
        name=f"Moment-Curvature · Section {section_tag}",
        model=model,
        units=dict(source.units),
    )

    required_materials: set[int] = set()
    if section.section_type == "Elastic" and section.material_tag is not None:
        required_materials.add(int(section.material_tag))
    elif section.section_type == "Fiber":
        required_materials.update(
            int(tag) for tag in section.fiber_material_tags()
        )

    stack = list(required_materials)
    while stack:
        tag = int(stack.pop())
        material = source.materials.get(tag)
        if material is None:
            raise ValueError(
                f"Section {section_tag} references missing material {tag}."
            )
        for dependency in source.material_dependencies(material):
            dependency = int(dependency)
            if dependency not in required_materials:
                required_materials.add(dependency)
                stack.append(dependency)

    # Preserve dependency order by adding lower-level materials first.
    pending = set(required_materials)
    while pending:
        progressed = False
        for tag in sorted(pending):
            material = source.materials[tag]
            dependencies = {
                int(value)
                for value in source.material_dependencies(material)
            }
            if dependencies.issubset(project.materials):
                project.add_material(deepcopy(material))
                pending.remove(tag)
                progressed = True
                break
        if not progressed:
            raise ValueError(
                "Section material dependencies contain an unresolved cycle."
            )

    project.add_section(deepcopy(section))

    project.add_connection(
        ConnectionData(
            tag=1,
            name=f"Moment-Curvature Section {section_tag}",
            connection_type="zeroLengthSection",
            node_i=1,
            node_j=2,
            section_tag=section_tag,
        )
    )

    project.add_time_series(
        TimeSeriesData(
            tag=1,
            name="Axial preload",
            series_type="Constant",
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            tag=1,
            name="Axial preload",
            pattern_type="Plain",
            time_series_tag=1,
        )
    )
    axial_values = [0.0] * 6
    axial_values[0] = float(spec.axial_load)
    project.add_nodal_load(
        NodalLoadData(
            tag=1,
            name="Section axial load",
            pattern_tag=1,
            node_tag=2,
            values=tuple(axial_values),
        )
    )

    project.add_time_series(
        TimeSeriesData(
            tag=2,
            name="Unit moment reference",
            series_type="Linear",
        )
    )
    project.add_load_pattern(
        LoadPatternData(
            tag=2,
            name=f"Unit {axis} reference",
            pattern_type="Plain",
            time_series_tag=2,
        )
    )
    moment_values = [0.0] * 6
    moment_values[control_dof - 1] = 1.0
    project.add_nodal_load(
        NodalLoadData(
            tag=2,
            name=f"Unit {axis} reference moment",
            pattern_tag=2,
            node_tag=2,
            values=tuple(moment_values),
        )
    )

    increments = int(spec.increments)
    project.add_analysis(
        AnalysisSettingsData(
            tag=1,
            name=f"Moment-Curvature · Section {section_tag} · {axis}",
            analysis_type="Static",
            constraints_handler="Plain",
            numberer="Plain",
            system="SparseGeneral",
            test="NormUnbalance",
            tolerance=1.0e-9,
            max_iterations=30,
            algorithm="Newton",
            steps=increments,
            control_node=2,
            control_dof=control_dof,
            displacement_increment=float(spec.max_curvature) / increments,
            preload_gravity=True,
            gravity_steps=1,
            deferred_pattern_tags=[2],
            recovery=True,
            adaptive_step=False,
            integrator="DisplacementControl",
        )
    )
    project.active_analysis_tag = 1
    return project
