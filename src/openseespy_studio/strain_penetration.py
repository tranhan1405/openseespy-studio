from __future__ import annotations

from dataclasses import dataclass

from .project import (
    FiberComponentData,
    FiberData,
    MaterialData,
    SectionData,
)


STEEL_MATERIAL_TYPES = {
    "Steel01",
    "Steel02",
    "ReinforcingSteel",
}


@dataclass(slots=True)
class StrainPenetrationSectionResult:
    section: SectionData
    replaced_material_tags: list[int]


def _material_is_steel_like(
    tag: int,
    materials: dict[int, MaterialData],
    seen: set[int] | None = None,
) -> bool:
    tag = int(tag)
    material = materials.get(tag)
    if material is None:
        return False
    if material.material_type in STEEL_MATERIAL_TYPES:
        return True

    visited = set(seen or ())
    if tag in visited:
        return False
    visited.add(tag)

    if (
        material.material_type in {"MinMax", "Fatigue"}
        and material.base_material_tag is not None
    ):
        return _material_is_steel_like(
            material.base_material_tag,
            materials,
            visited,
        )
    if material.material_type in {"Parallel", "Series"}:
        return any(
            _material_is_steel_like(child, materials, visited)
            for child in material.material_tags
        )
    return False


def build_bond_sp01_strain_penetration_section(
    source: SectionData,
    materials: dict[int, MaterialData],
    *,
    bond_material_tag: int,
    section_tag: int,
    name: str | None = None,
) -> StrainPenetrationSectionResult:
    """Clone an RC Fiber section for a zeroLengthSection interface.

    Concrete fibers/components retain their source material. Steel-like fibers
    and rebar layers are replaced with Bond_SP01 so their material deformation
    represents bar slip rather than steel strain.
    """
    if source.section_type != "Fiber":
        raise ValueError(
            "Bond_SP01 strain penetration requires a Fiber source section."
        )

    bond_material_tag = int(bond_material_tag)
    bond = materials.get(bond_material_tag)
    if bond is None:
        raise ValueError(
            f"Bond_SP01 material {bond_material_tag} does not exist."
        )
    if bond.material_type != "Bond_SP01":
        raise ValueError(
            f"Material {bond_material_tag} is {bond.material_type}, "
            "not Bond_SP01."
        )

    replaced: set[int] = set()
    fibers: list[FiberData] = []
    for fiber in source.fibers:
        material_tag = int(fiber.material_tag)
        if _material_is_steel_like(material_tag, materials):
            replaced.add(material_tag)
            material_tag = bond_material_tag
        fibers.append(
            FiberData(
                y=float(fiber.y),
                z=float(fiber.z),
                area=float(fiber.area),
                material_tag=material_tag,
            )
        )

    components: list[FiberComponentData] = []
    for component in source.fiber_components:
        material_tag = int(component.material_tag)
        if _material_is_steel_like(material_tag, materials):
            replaced.add(material_tag)
            material_tag = bond_material_tag
        components.append(
            FiberComponentData(
                component_type=component.component_type,
                name=component.name,
                material_tag=material_tag,
                parameters=dict(component.parameters),
            )
        )

    if not replaced:
        raise ValueError(
            "The selected Fiber section contains no steel/rebar material "
            "that can be replaced by Bond_SP01."
        )

    section = SectionData(
        tag=int(section_tag),
        name=(
            str(name).strip()
            if name is not None and str(name).strip()
            else f"{source.name} · Bond_SP01 strain penetration"
        ),
        section_type="Fiber",
        parameters=dict(source.parameters),
        fibers=fibers,
        fiber_components=components,
        display_geometry=dict(source.display_geometry),
    )
    return StrainPenetrationSectionResult(
        section=section,
        replaced_material_tags=sorted(replaced),
    )
