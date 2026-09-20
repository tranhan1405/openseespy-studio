from __future__ import annotations

import math

from .model import Element, StructuralModel
from .project import (
    ElementLoadData,
    MaterialData,
    SectionData,
    TransformationData,
)
from .units import UnitSystem


Vec3 = tuple[float, float, float]


def _norm(vector: Vec3) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _unit(vector: Vec3) -> Vec3:
    length = _norm(vector)
    if length <= 1.0e-15:
        raise ValueError("Cannot define local axes for a zero-length element.")
    return tuple(value / length for value in vector)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return sum(x * y for x, y in zip(a, b))


def element_local_axes(
    model: StructuralModel,
    element: Element,
    transformation: TransformationData,
) -> tuple[Vec3, Vec3, Vec3]:
    """Return OpenSees local x/y/z unit vectors in global coordinates."""
    node_i = model.nodes.get(element.i)
    node_j = model.nodes.get(element.j)
    if node_i is None or node_j is None:
        raise ValueError(
            f"Element {element.tag} references a missing node."
        )

    local_x = _unit(tuple(
        node_j.xyz[index] - node_i.xyz[index]
        for index in range(3)
    ))
    if int(model.ndm) == 2:
        # OpenSees 2D geomTransf does not take vecxz. Its local y axis is
        # the in-plane normal obtained from global Z x local x.
        local_y = _unit(_cross((0.0, 0.0, 1.0), local_x))
        local_z = (0.0, 0.0, 1.0)
        return local_x, local_y, local_z

    # OpenSees 3D defines local y = vecxz x local x, then z = x x y.
    local_y = _unit(_cross(transformation.vecxz, local_x))
    local_z = _unit(_cross(local_x, local_y))
    return local_x, local_y, local_z


def resolve_self_weight_local(
    load: ElementLoadData,
    model: StructuralModel,
    sections: dict[int, SectionData],
    materials: dict[int, MaterialData],
    transformations: dict[int, TransformationData],
    units: dict[str, str] | None = None,
) -> tuple[float, float, float]:
    element = model.elements.get(load.element_tag)
    if element is None:
        raise ValueError(
            f"Self-weight load {load.tag} references missing element "
            f"{load.element_tag}."
        )
    if element.section_tag is None:
        raise ValueError(
            f"Self-weight load {load.tag}: element {element.tag} has no section."
        )
    section = sections.get(element.section_tag)
    if section is None:
        raise ValueError(
            f"Self-weight load {load.tag}: section {element.section_tag} "
            "does not exist."
        )
    if section.section_type != "Elastic":
        raise ValueError(
            f"Self-weight load {load.tag}: automatic self-weight currently "
            "requires an Elastic section."
        )
    if element.transf_tag is None:
        raise ValueError(
            f"Self-weight load {load.tag}: element {element.tag} has no "
            "geometric transformation."
        )
    transformation = transformations.get(element.transf_tag)
    if transformation is None:
        raise ValueError(
            f"Self-weight load {load.tag}: transformation "
            f"{element.transf_tag} does not exist."
        )

    density = load.density_override
    if density <= 0.0:
        if section.material_tag is None:
            raise ValueError(
                f"Self-weight load {load.tag}: section {section.tag} has no "
                "linked material density. Set a density override or link "
                "the section to a material."
            )
        material = materials.get(section.material_tag)
        if material is None:
            raise ValueError(
                f"Self-weight load {load.tag}: material "
                f"{section.material_tag} does not exist."
            )
        density = material.density

    if density <= 0.0:
        raise ValueError(
            f"Self-weight load {load.tag}: density must be positive."
        )

    area = float(section.parameters["A"])
    unit_system = UnitSystem.from_mapping(units)
    global_line_load = tuple(
        unit_system.line_force_from_density_area_gravity(
            density,
            area,
            unit_system.acceleration_from_m_per_s2(component),
        )
        for component in load.gravity
    )
    local_x, local_y, local_z = element_local_axes(
        model,
        element,
        transformation,
    )
    return (
        _dot(global_line_load, local_x),
        _dot(global_line_load, local_y),
        _dot(global_line_load, local_z),
    )
