from __future__ import annotations

from dataclasses import dataclass

from .project import MATERIAL_DEFAULTS, MaterialData


@dataclass(slots=True)
class SpringMaterialChainSpec:
    """Research-oriented chain for a zeroLength/link uniaxial spring."""

    base_material_tag: int | None = None
    create_steel02: bool = False
    steel02_parameters: dict[str, float] | None = None
    add_fatigue: bool = True
    fatigue_parameters: dict[str, float] | None = None
    add_minmax: bool = True
    minmax_parameters: dict[str, float] | None = None
    name_prefix: str = "Spring"

    def __post_init__(self) -> None:
        self.base_material_tag = (
            None
            if self.base_material_tag is None
            else int(self.base_material_tag)
        )
        self.create_steel02 = bool(self.create_steel02)
        self.add_fatigue = bool(self.add_fatigue)
        self.add_minmax = bool(self.add_minmax)
        self.name_prefix = str(self.name_prefix).strip() or "Spring"

        if not self.create_steel02 and self.base_material_tag is None:
            raise ValueError(
                "Choose an existing base material or create a new Steel02."
            )
        if not self.add_fatigue and not self.add_minmax:
            raise ValueError(
                "A research chain must add Fatigue and/or MinMax."
            )


@dataclass(slots=True)
class SpringMaterialChainResult:
    materials: list[MaterialData]
    base_tag: int
    final_tag: int

    def tags(self) -> list[int]:
        return [material.tag for material in self.materials]


def _next_free_tag(used: set[int], start: int) -> int:
    tag = max(1, int(start))
    while tag in used:
        tag += 1
    used.add(tag)
    return tag


def build_spring_material_chain(
    spec: SpringMaterialChainSpec,
    existing_materials: dict[int, MaterialData],
    *,
    next_tag: int | None = None,
) -> SpringMaterialChainResult:
    """Create pending MaterialData objects without mutating the project."""
    used = set(int(tag) for tag in existing_materials)
    start = (
        max(used, default=0) + 1
        if next_tag is None
        else max(1, int(next_tag))
    )
    created: list[MaterialData] = []

    if spec.create_steel02:
        steel_tag = _next_free_tag(used, start)
        steel_parameters = dict(MATERIAL_DEFAULTS["Steel02"])
        if spec.steel02_parameters:
            steel_parameters.update(
                {
                    str(key): float(value)
                    for key, value in spec.steel02_parameters.items()
                }
            )
        steel = MaterialData(
            tag=steel_tag,
            name=f"{spec.name_prefix} · Steel02",
            material_type="Steel02",
            parameters=steel_parameters,
        )
        created.append(steel)
        current_tag = steel_tag
        start = steel_tag + 1
    else:
        current_tag = int(spec.base_material_tag or 0)
        if current_tag not in existing_materials:
            raise ValueError(
                f"Base material tag {current_tag} does not exist."
            )

    base_tag = current_tag

    if spec.add_fatigue:
        fatigue_tag = _next_free_tag(used, start)
        fatigue_parameters = dict(MATERIAL_DEFAULTS["Fatigue"])
        if spec.fatigue_parameters:
            fatigue_parameters.update(
                {
                    str(key): float(value)
                    for key, value in spec.fatigue_parameters.items()
                }
            )
        fatigue = MaterialData(
            tag=fatigue_tag,
            name=f"{spec.name_prefix} · Fatigue",
            material_type="Fatigue",
            parameters=fatigue_parameters,
            base_material_tag=current_tag,
        )
        created.append(fatigue)
        current_tag = fatigue_tag
        start = fatigue_tag + 1

    if spec.add_minmax:
        minmax_tag = _next_free_tag(used, start)
        minmax_parameters = dict(MATERIAL_DEFAULTS["MinMax"])
        if spec.minmax_parameters:
            minmax_parameters.update(
                {
                    str(key): float(value)
                    for key, value in spec.minmax_parameters.items()
                }
            )
        minmax = MaterialData(
            tag=minmax_tag,
            name=f"{spec.name_prefix} · MinMax",
            material_type="MinMax",
            parameters=minmax_parameters,
            base_material_tag=current_tag,
        )
        created.append(minmax)
        current_tag = minmax_tag

    return SpringMaterialChainResult(
        materials=created,
        base_tag=base_tag,
        final_tag=current_tag,
    )


def describe_material_chain(
    final_tag: int,
    materials: dict[int, MaterialData],
) -> list[MaterialData]:
    """Return a readable inner-to-outer path for single-base wrappers."""
    path: list[MaterialData] = []
    seen: set[int] = set()
    tag = int(final_tag)

    while tag in materials and tag not in seen:
        seen.add(tag)
        material = materials[tag]
        path.append(material)
        if (
            material.material_type in {"MinMax", "Fatigue"}
            and material.base_material_tag is not None
        ):
            tag = material.base_material_tag
            continue
        break

    path.reverse()
    return path
