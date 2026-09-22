from __future__ import annotations

from dataclasses import dataclass, field
import math

from .beam_loads import element_local_axes, resolve_self_weight_local
from .project import MassSourceData, ProjectDatabase, SectionData
from .units import UnitSystem


Vec3 = tuple[float, float, float]


@dataclass(slots=True)
class MassSourceSummary:
    """Summary of one mass-source evaluation in model mass units."""

    nodal_mass: dict[int, float] = field(default_factory=dict)
    self_mass: float = 0.0
    load_mass: float = 0.0
    skipped_element_mass_tags: list[int] = field(default_factory=list)
    skipped_self_weight_load_tags: list[int] = field(default_factory=list)

    @property
    def total_mass(self) -> float:
        return float(self.self_mass + self.load_mass)

    @property
    def active_nodes(self) -> int:
        return sum(value > 1.0e-15 for value in self.nodal_mass.values())


def _length(project: ProjectDatabase, element_tag: int) -> float:
    element = project.model.elements[element_tag]
    node_i = project.model.nodes[element.i]
    node_j = project.model.nodes[element.j]
    return math.sqrt(
        sum(
            (node_j.xyz[index] - node_i.xyz[index]) ** 2
            for index in range(3)
        )
    )


def _shell_area_vector(
    project: ProjectDatabase,
    element_tag: int,
) -> Vec3:
    """Return oriented quadrilateral area vector in model length²."""
    element = project.model.elements[int(element_tag)]
    node_tags = element.node_tags()
    if len(node_tags) != 4:
        return (0.0, 0.0, 0.0)
    p = [
        project.model.nodes[tag].xyz
        for tag in node_tags
    ]

    def subtract(a, b):
        return tuple(float(a[i]) - float(b[i]) for i in range(3))

    def cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    a1 = cross(subtract(p[1], p[0]), subtract(p[2], p[0]))
    a2 = cross(subtract(p[2], p[0]), subtract(p[3], p[0]))
    return tuple(0.5 * (a1[i] + a2[i]) for i in range(3))


def _shell_area(
    project: ProjectDatabase,
    element_tag: int,
) -> float:
    vector = _shell_area_vector(project, element_tag)
    return math.sqrt(sum(value * value for value in vector))


def _section_mass_per_length(
    project: ProjectDatabase,
    section: SectionData,
) -> float:
    """Return section self mass/length from linked material densities."""
    units = UnitSystem.from_mapping(project.units)

    if section.section_type == "Elastic":
        if section.material_tag is None:
            return 0.0
        material = project.materials.get(section.material_tag)
        if material is None or material.density <= 0.0:
            return 0.0
        density = units.density_from_kg_per_m3(material.density)
        return density * float(section.parameters.get("A", 0.0))

    if section.section_type == "Fiber":
        value = 0.0
        for fiber in section.compiled_fibers():
            material = project.materials.get(fiber.material_tag)
            if material is None or material.density <= 0.0:
                continue
            density = units.density_from_kg_per_m3(material.density)
            value += density * float(fiber.area)
        return value

    return 0.0


def _local_vector_to_global(
    project: ProjectDatabase,
    element_tag: int,
    local_vector: Vec3,
) -> Vec3:
    element = project.model.elements.get(int(element_tag))
    if element is None:
        raise ValueError(f"Element {element_tag} does not exist.")
    if element.transf_tag is None:
        raise ValueError(
            f"Element {element.tag} needs a geometric transformation "
            "before its local beam load can be converted to seismic mass."
        )
    transformation = project.transformations.get(element.transf_tag)
    if transformation is None:
        raise ValueError(
            f"Element {element.tag} references missing transformation "
            f"{element.transf_tag}."
        )
    local_x, local_y, local_z = element_local_axes(
        project.model,
        element,
        transformation,
    )
    wx, wy, wz = (float(value) for value in local_vector)
    return tuple(
        wx * local_x[index]
        + wy * local_y[index]
        + wz * local_z[index]
        for index in range(3)
    )


def _pattern_amplitude(
    project: ProjectDatabase,
    pattern_tag: int,
) -> float:
    pattern = project.load_patterns.get(int(pattern_tag))
    if pattern is None:
        raise ValueError(f"Mass source references missing pattern {pattern_tag}.")
    if pattern.pattern_type != "Plain":
        raise ValueError(
            f"Mass source pattern {pattern.tag} must be a Plain load pattern."
        )
    series = project.time_series.get(pattern.time_series_tag)
    if series is None:
        raise ValueError(
            f"Mass source pattern {pattern.tag} references missing time "
            f"series {pattern.time_series_tag}."
        )
    if series.series_type not in {"Linear", "Constant"}:
        raise ValueError(
            f"Mass source pattern {pattern.tag} uses {series.series_type} "
            "time series. Only Linear/Constant gravity-style patterns can "
            "be converted to seismic mass."
        )
    return abs(float(series.factor))


def evaluate_mass_source(
    project: ProjectDatabase,
    source: MassSourceData,
) -> MassSourceSummary:
    """Calculate lumped nodal seismic mass without mutating the project."""
    axis = int(source.gravity_axis)
    if axis not in (1, 2, 3):
        raise ValueError("Mass-source gravity axis must be X, Y, or Z.")

    unit_system = UnitSystem.from_mapping(project.units)
    g_model = abs(unit_system.acceleration_from_m_per_s2(9.80665))
    if g_model <= 0.0:
        raise ValueError("Invalid model gravity acceleration.")

    managed_ground_nodes = {
        int(connection.generated_ground_node)
        for connection in project.connections.values()
        if connection.generated_ground_node is not None
    }
    summary = MassSourceSummary(
        nodal_mass={tag: 0.0 for tag in project.model.nodes}
    )

    def add_node(tag: int, mass: float, *, category: str) -> None:
        if int(tag) in managed_ground_nodes:
            return
        value = max(0.0, float(mass))
        if value <= 0.0:
            return
        summary.nodal_mass[int(tag)] = (
            summary.nodal_mass.get(int(tag), 0.0) + value
        )
        if category == "self":
            summary.self_mass += value
        else:
            summary.load_mass += value

    if source.include_self_mass:
        for element_tag in sorted(project.model.elements):
            element = project.model.elements[element_tag]
            if element.mass_per_length > 0.0:
                # OpenSees will already put this mass into the element mass
                # matrix. Adding it again as nodal mass would double-count.
                summary.skipped_element_mass_tags.append(element.tag)
                continue
            if element.section_tag is None:
                continue
            section = project.sections.get(element.section_tag)
            if section is None:
                continue
            if (
                element.element_type in {
                    "ASDShellQ4",
                    "ShellMITC4",
                    "ShellDKGQ",
                    "ShellNLDKGQ",
                }
                and section.section_type == "ElasticMembranePlate"
            ):
                density = float(section.parameters.get("rho", 0.0))
                thickness = float(section.parameters.get("h", 0.0))
                total = density * thickness * _shell_area(
                    project,
                    element.tag,
                )
                for node_tag in element.node_tags():
                    add_node(
                        node_tag,
                        0.25 * total,
                        category="self",
                    )
                continue
            mass_per_length = _section_mass_per_length(project, section)
            if mass_per_length <= 0.0:
                continue
            total = mass_per_length * _length(project, element.tag)
            add_node(element.i, 0.5 * total, category="self")
            add_node(element.j, 0.5 * total, category="self")

    for pattern_tag, participation in sorted(source.load_factors.items()):
        factor = float(participation)
        if factor <= 0.0:
            continue
        amplitude = _pattern_amplitude(project, pattern_tag)
        multiplier = factor * amplitude

        for load in project.nodal_loads.values():
            if load.pattern_tag != pattern_tag:
                continue
            force = abs(float(load.values[axis - 1])) * multiplier
            add_node(load.node_tag, force / g_model, category="load")

        for load in project.element_loads.values():
            if load.pattern_tag != pattern_tag:
                continue
            element = project.model.elements.get(load.element_tag)
            if element is None:
                raise ValueError(
                    f"Element load {load.tag} references missing element "
                    f"{load.element_tag}."
                )

            if load.load_type == "SelfWeight":
                if source.include_self_mass:
                    summary.skipped_self_weight_load_tags.append(load.tag)
                    continue
                local = resolve_self_weight_local(
                    load,
                    project.model,
                    project.sections,
                    project.materials,
                    project.transformations,
                    project.units,
                )
                global_vector = _local_vector_to_global(
                    project,
                    element.tag,
                    local,
                )
                line_force = abs(global_vector[axis - 1]) * multiplier
                total_mass = line_force * _length(project, element.tag) / g_model
                add_node(element.i, 0.5 * total_mass, category="load")
                add_node(element.j, 0.5 * total_mass, category="load")
                continue

            if load.load_type == "Uniform":
                global_vector = _local_vector_to_global(
                    project,
                    element.tag,
                    (load.wx, load.wy, load.wz),
                )
                line_force = abs(global_vector[axis - 1]) * multiplier
                total_mass = line_force * _length(project, element.tag) / g_model
                add_node(element.i, 0.5 * total_mass, category="load")
                add_node(element.j, 0.5 * total_mass, category="load")
                continue

            if load.load_type == "SurfacePressure":
                area_vector = _shell_area_vector(
                    project,
                    element.tag,
                )
                force_axis = abs(
                    float(load.pressure)
                    * float(area_vector[axis - 1])
                ) * multiplier
                total_mass = force_axis / g_model
                for node_tag in element.node_tags():
                    add_node(
                        node_tag,
                        0.25 * total_mass,
                        category="load",
                    )
                continue

            if load.load_type == "Point":
                global_vector = _local_vector_to_global(
                    project,
                    element.tag,
                    (load.px, load.py, load.pz),
                )
                force = abs(global_vector[axis - 1]) * multiplier
                total_mass = force / g_model
                xi = min(1.0, max(0.0, float(load.x_over_l)))
                add_node(element.i, (1.0 - xi) * total_mass, category="load")
                add_node(element.j, xi * total_mass, category="load")
                continue

    return summary


def apply_mass_source(
    project: ProjectDatabase,
    source: MassSourceData,
) -> MassSourceSummary:
    """Evaluate and assign a mass source to selected translational DOFs.

    Selected translational mass components are replaced, not incremented, so
    regenerating a source cannot silently accumulate duplicate mass. Rotational
    mass and unselected translational directions are preserved.
    """
    summary = evaluate_mass_source(project, source)
    directions = tuple(sorted(set(int(dof) for dof in source.directions)))
    if not directions:
        raise ValueError("Mass source needs at least one translational direction.")
    max_translational = min(3, int(project.model.ndm))
    if any(dof < 1 or dof > max_translational for dof in directions):
        raise ValueError(
            "Mass-source directions must be valid translational model DOFs."
        )

    managed_ground_nodes = {
        int(connection.generated_ground_node)
        for connection in project.connections.values()
        if connection.generated_ground_node is not None
    }
    for tag, node in project.model.nodes.items():
        if int(tag) in managed_ground_nodes:
            project.model.set_mass(tag, (0.0,) * int(project.model.ndf))
            continue
        values = list(node.mass)
        scalar = float(summary.nodal_mass.get(tag, 0.0))
        for dof in directions:
            values[dof - 1] = scalar
        project.model.set_mass(tag, values)

    return summary
