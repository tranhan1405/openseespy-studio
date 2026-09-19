from __future__ import annotations

from dataclasses import dataclass, field

from .project import (
    MATERIAL_DEFAULTS,
    MaterialData,
    SectionData,
)
from .section_templates import (
    create_circle_section_components,
    create_rectangle_section_components,
)
from .units import UnitSystem


CONCRETE_TYPES = {"Concrete01", "Concrete02", "Concrete04"}
REBAR_TYPES = {"Steel01", "Steel02", "ReinforcingSteel"}


@dataclass(slots=True)
class FRPColumnSpec:
    section_tag: int
    section_name: str
    shape: str = "Circular"
    diameter: float = 400.0
    height: float = 400.0
    width: float = 400.0
    cover: float = 35.0
    gj: float = 1.0e6

    concrete_material_tag: int | None = None
    create_concrete02: bool = False
    concrete02_parameters: dict[str, float] = field(default_factory=dict)

    rebar_material_tag: int | None = None
    create_reinforcing_steel: bool = False
    reinforcing_steel_parameters: dict[str, float] = field(default_factory=dict)

    bar_diameter: float = 16.0
    circular_bars: int = 8
    bars_top: int = 3
    bars_bottom: int = 3
    side_bars_each: int = 2

    n_radial: int = 12
    n_circum: int = 48
    n_y: int = 24
    n_z: int = 24

    frp_family: str = "Custom"
    frp_layers: int = 2
    frp_layer_thickness_m: float = 0.000167
    frp_modulus_pa: float = 72.0e9
    frp_rupture_strain: float = 0.015
    confinement_scope: str = "all_concrete"

    ultimate_fcu_pa: float = -45.0e6
    ultimate_ecu: float = -0.015
    tensile_strength_pa: float | None = None
    tension_softening_pa: float | None = None

    def __post_init__(self) -> None:
        self.section_tag = int(self.section_tag)
        self.section_name = str(self.section_name).strip() or (
            f"FRP RC Column {self.section_tag}"
        )
        self.shape = str(self.shape).strip().title()
        if self.shape not in {"Circular", "Rectangular"}:
            raise ValueError("FRP RC column shape must be Circular or Rectangular.")
        if self.section_tag <= 0:
            raise ValueError("Section tag must be positive.")
        self.diameter = float(self.diameter)
        self.height = float(self.height)
        self.width = float(self.width)
        self.cover = float(self.cover)
        self.gj = float(self.gj)

        self.concrete_material_tag = (
            None if self.concrete_material_tag is None
            else int(self.concrete_material_tag)
        )
        self.rebar_material_tag = (
            None if self.rebar_material_tag is None
            else int(self.rebar_material_tag)
        )
        self.create_concrete02 = bool(self.create_concrete02)
        self.create_reinforcing_steel = bool(self.create_reinforcing_steel)

        self.bar_diameter = float(self.bar_diameter)
        self.circular_bars = int(self.circular_bars)
        self.bars_top = int(self.bars_top)
        self.bars_bottom = int(self.bars_bottom)
        self.side_bars_each = int(self.side_bars_each)

        self.n_radial = int(self.n_radial)
        self.n_circum = int(self.n_circum)
        self.n_y = int(self.n_y)
        self.n_z = int(self.n_z)

        self.frp_family = str(self.frp_family).strip() or "Custom"
        self.frp_layers = int(self.frp_layers)
        self.frp_layer_thickness_m = float(self.frp_layer_thickness_m)
        self.frp_modulus_pa = float(self.frp_modulus_pa)
        self.frp_rupture_strain = float(self.frp_rupture_strain)
        self.confinement_scope = str(self.confinement_scope)
        self.ultimate_fcu_pa = float(self.ultimate_fcu_pa)
        self.ultimate_ecu = float(self.ultimate_ecu)
        self.tensile_strength_pa = (
            None if self.tensile_strength_pa is None
            else float(self.tensile_strength_pa)
        )
        self.tension_softening_pa = (
            None if self.tension_softening_pa is None
            else float(self.tension_softening_pa)
        )

        if self.cover < 0.0:
            raise ValueError("Concrete cover cannot be negative.")
        if self.gj < 0.0:
            raise ValueError("GJ cannot be negative.")
        if self.shape == "Circular":
            if self.diameter <= 0.0:
                raise ValueError("Circular column diameter must be positive.")
            if 2.0 * self.cover >= self.diameter:
                raise ValueError("Cover is too large for the circular column.")
            if self.circular_bars < 1:
                raise ValueError("Circular RC column needs at least one rebar.")
        else:
            if self.height <= 0.0 or self.width <= 0.0:
                raise ValueError("Rectangular column dimensions must be positive.")
            if 2.0 * self.cover >= min(self.height, self.width):
                raise ValueError("Cover is too large for the rectangular column.")
            if self.bars_top < 1 or self.bars_bottom < 1:
                raise ValueError(
                    "Rectangular RC column needs top and bottom reinforcement."
                )

        if self.bar_diameter <= 0.0:
            raise ValueError("Rebar diameter must be positive.")
        if min(self.n_radial, self.n_circum, self.n_y, self.n_z) < 1:
            raise ValueError("Fiber subdivisions must be at least 1.")
        if self.frp_layers < 1:
            raise ValueError("FRP layer count must be at least 1.")
        if self.frp_layer_thickness_m <= 0.0:
            raise ValueError("FRP layer thickness must be positive.")
        if self.frp_modulus_pa <= 0.0:
            raise ValueError("FRP modulus must be positive.")
        if self.frp_rupture_strain <= 0.0:
            raise ValueError("FRP rupture strain must be positive.")
        if self.confinement_scope not in {"all_concrete", "core_only"}:
            raise ValueError(
                "Confinement scope must be all_concrete or core_only."
            )
        if self.shape == "Rectangular":
            if self.ultimate_fcu_pa >= 0.0:
                raise ValueError(
                    "Rectangular Ultimate mode expects compressive fcu < 0."
                )
            if self.ultimate_ecu >= 0.0:
                raise ValueError(
                    "Rectangular Ultimate mode expects compressive ecu < 0."
                )


@dataclass(slots=True)
class FRPColumnBuildResult:
    section: SectionData
    materials: list[MaterialData]
    base_concrete_tag: int
    rebar_material_tag: int
    frp_material_tag: int

    def combined_materials(
        self,
        existing: dict[int, MaterialData],
    ) -> dict[int, MaterialData]:
        result = dict(existing)
        result.update({material.tag: material for material in self.materials})
        return result


def _next_free_tag(used: set[int], start: int) -> int:
    tag = max(1, int(start))
    while tag in used:
        tag += 1
    used.add(tag)
    return tag


def _concrete_seed(
    material: MaterialData,
) -> tuple[float, float, float, float, float]:
    p = material.parameters
    if material.material_type == "Concrete01":
        return (
            float(p["fpc"]),
            float(material.elastic_modulus()),
            float(p["epsc0"]),
            0.0,
            1.0,
        )
    if material.material_type == "Concrete02":
        return (
            float(p["fpc"]),
            float(material.elastic_modulus()),
            float(p["epsc0"]),
            float(p["ft"]),
            float(p["Ets"]),
        )
    if material.material_type == "Concrete04":
        return (
            float(p["fc"]),
            float(p["Ec"]),
            float(p["epsc"]),
            float(p["fct"]),
            max(float(p["Ec"]) * 0.05, 1.0),
        )
    raise ValueError(
        "FRP RC Column Wizard needs Concrete01, Concrete02, or Concrete04 "
        "as the unconfined concrete source."
    )


def build_frp_rc_column(
    spec: FRPColumnSpec,
    existing_materials: dict[int, MaterialData],
    units: dict[str, str] | None,
) -> FRPColumnBuildResult:
    unit_system = UnitSystem.from_mapping(units)
    if not (
        unit_system.length == "mm"
        and unit_system.force == "N"
    ):
        raise ValueError(
            "FRP RC Column Wizard currently requires project units mm - N - s "
            "because FRPConfinedConcrete02 is generated in the OpenSees "
            "N-mm-MPa convention."
        )

    used = set(int(tag) for tag in existing_materials)
    next_tag = max(used, default=0) + 1
    created: list[MaterialData] = []

    if spec.create_concrete02:
        tag = _next_free_tag(used, next_tag)
        params = dict(MATERIAL_DEFAULTS["Concrete02"])
        params.update({
            str(key): float(value)
            for key, value in spec.concrete02_parameters.items()
        })
        concrete = MaterialData(
            tag=tag,
            name=f"{spec.section_name} · Concrete02",
            material_type="Concrete02",
            parameters=params,
            poisson_ratio=0.2,
            density=2400.0,
        )
        created.append(concrete)
        base_concrete_tag = tag
        next_tag = tag + 1
    else:
        if spec.concrete_material_tag is None:
            raise ValueError("Select an unconfined concrete material.")
        base_concrete_tag = int(spec.concrete_material_tag)
        concrete = existing_materials.get(base_concrete_tag)
        if concrete is None:
            raise ValueError(
                f"Concrete material {base_concrete_tag} does not exist."
            )
        if concrete.material_type not in CONCRETE_TYPES:
            raise ValueError(
                f"Material {base_concrete_tag} is {concrete.material_type}, "
                "not a supported concrete source."
            )

    if spec.create_reinforcing_steel:
        tag = _next_free_tag(used, next_tag)
        params = dict(MATERIAL_DEFAULTS["ReinforcingSteel"])
        params.update({
            str(key): float(value)
            for key, value in spec.reinforcing_steel_parameters.items()
        })
        rebar = MaterialData(
            tag=tag,
            name=f"{spec.section_name} · ReinforcingSteel",
            material_type="ReinforcingSteel",
            parameters=params,
            poisson_ratio=0.3,
            density=7850.0,
        )
        created.append(rebar)
        rebar_tag = tag
        next_tag = tag + 1
    else:
        if spec.rebar_material_tag is None:
            raise ValueError("Select a reinforcement material.")
        rebar_tag = int(spec.rebar_material_tag)
        rebar = existing_materials.get(rebar_tag)
        if rebar is None:
            raise ValueError(
                f"Rebar material {rebar_tag} does not exist."
            )
        if rebar.material_type not in REBAR_TYPES:
            raise ValueError(
                f"Material {rebar_tag} is {rebar.material_type}, "
                "not a supported reinforcement material."
            )

    fc0, ec, ec0, ft_seed, ets_seed = _concrete_seed(concrete)
    ft = (
        ft_seed
        if spec.tensile_strength_pa is None
        else spec.tensile_strength_pa
    )
    ets = (
        ets_seed
        if spec.tension_softening_pa is None
        else spec.tension_softening_pa
    )

    frp_tag = _next_free_tag(used, next_tag)
    total_t = spec.frp_layers * spec.frp_layer_thickness_m
    radius_m = (
        unit_system.length_to_m_value(0.5 * spec.diameter)
        if spec.shape == "Circular"
        else unit_system.length_to_m_value(
            0.5 * min(spec.height, spec.width)
        )
    )
    frp = MaterialData(
        tag=frp_tag,
        name=(
            f"{spec.section_name} · {spec.frp_family} "
            f"{spec.frp_layers}L FRP-confined concrete"
        ),
        material_type="FRPConfinedConcrete02",
        parameters={
            "fc0": fc0,
            "Ec": ec,
            "ec0": ec0,
            "mode": 0.0 if spec.shape == "Circular" else 1.0,
            "tfrp": total_t,
            "Efrp": spec.frp_modulus_pa,
            "erup": spec.frp_rupture_strain,
            "R": radius_m,
            "fcu": spec.ultimate_fcu_pa,
            "ecu": spec.ultimate_ecu,
            "ft": ft,
            "Ets": ets,
        },
        poisson_ratio=0.2,
        density=2400.0,
    )
    created.append(frp)

    core_tag = frp_tag
    cover_tag = (
        frp_tag
        if spec.confinement_scope == "all_concrete"
        else base_concrete_tag
    )

    if spec.shape == "Circular":
        components = create_circle_section_components(
            outer_diameter=spec.diameter,
            inner_diameter=0.0,
            cover=spec.cover,
            core_material_tag=core_tag,
            cover_material_tag=cover_tag,
            n_radial=spec.n_radial,
            n_circum=spec.n_circum,
            rebar_material_tag=rebar_tag,
            bar_diameter=spec.bar_diameter,
            outer_bars=spec.circular_bars,
            inner_bars=0,
        )
        display_geometry = {
            "shape": "Circle",
            "dimensions": {
                "outer_diameter": spec.diameter,
                "inner_diameter": 0.0,
            },
        }
    else:
        components = create_rectangle_section_components(
            height=spec.height,
            width=spec.width,
            cover=spec.cover,
            core_material_tag=core_tag,
            cover_material_tag=cover_tag,
            n_y=spec.n_y,
            n_z=spec.n_z,
            rebar_material_tag=rebar_tag,
            bar_diameter=spec.bar_diameter,
            bars_top=spec.bars_top,
            bars_bottom=spec.bars_bottom,
            side_bars_each=spec.side_bars_each,
        )
        display_geometry = {
            "shape": "Rectangle",
            "dimensions": {
                "height": spec.height,
                "width": spec.width,
            },
        }

    section = SectionData(
        tag=spec.section_tag,
        name=spec.section_name,
        section_type="Fiber",
        parameters={"GJ": spec.gj},
        fiber_components=components,
        display_geometry=display_geometry,
    )

    return FRPColumnBuildResult(
        section=section,
        materials=created,
        base_concrete_tag=base_concrete_tag,
        rebar_material_tag=rebar_tag,
        frp_material_tag=frp_tag,
    )
