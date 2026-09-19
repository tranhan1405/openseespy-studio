from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import StructuralModel
from .units import DEFAULT_PROJECT_UNITS, normalize_project_units


PROJECT_FORMAT = "openseespy-studio"
PROJECT_FORMAT_VERSION = 25

MATERIAL_CATEGORIES: dict[str, str] = {
    "Elastic": "General",
    "Steel01": "Steel",
    "Steel02": "Steel",
    "ReinforcingSteel": "Steel",
    "Concrete01": "Concrete",
    "Concrete02": "Concrete",
    "Concrete04": "Concrete",
    "Hysteretic": "Hysteretic / Connection",
    "Pinching4": "Hysteretic / Connection",
    "Bond_SP01": "Bond / Interface",
    "ElasticPPGap": "Hysteretic / Connection",
    "FRPConfinedConcrete02": "Concrete / FRP",
    "MinMax": "Wrapper / Composite",
    "Fatigue": "Wrapper / Composite",
    "Parallel": "Wrapper / Composite",
    "Series": "Wrapper / Composite",
}

MATERIAL_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "Elastic": ("E",),
    "Steel01": ("Fy", "E0", "b", "a1", "a2", "a3", "a4"),
    "Steel02": ("Fy", "E0", "b", "R0", "cR1", "cR2"),
    "ReinforcingSteel": ("fy", "fu", "Es", "Esh", "eps_sh", "eps_ult"),
    "Concrete01": ("fpc", "epsc0", "fpcu", "epsU"),
    "Concrete02": ("fpc", "epsc0", "fpcu", "epsU", "lambda", "ft", "Ets"),
    "Concrete04": ("fc", "epsc", "epscu", "Ec", "fct", "et", "beta"),
    "Hysteretic": (
        "s1p", "e1p", "s2p", "e2p", "s3p", "e3p",
        "s1n", "e1n", "s2n", "e2n", "s3n", "e3n",
        "pinchX", "pinchY", "damage1", "damage2", "beta",
    ),
    "Pinching4": (
        "ePf1", "ePd1", "ePf2", "ePd2", "ePf3", "ePd3", "ePf4", "ePd4",
        "eNf1", "eNd1", "eNf2", "eNd2", "eNf3", "eNd3", "eNf4", "eNd4",
        "rDispP", "rForceP", "uForceP", "rDispN", "rForceN", "uForceN",
        "gK1", "gK2", "gK3", "gK4", "gKLim",
        "gD1", "gD2", "gD3", "gD4", "gDLim",
        "gF1", "gF2", "gF3", "gF4", "gFLim", "gE", "dmgType",
    ),
    "Bond_SP01": ("Fy", "Sy", "Fu", "Su", "b", "R"),
    "ElasticPPGap": ("E", "Fy", "gap", "eta", "damage"),
    "FRPConfinedConcrete02": (
        "fc0", "Ec", "ec0", "mode", "tfrp", "Efrp", "erup", "R",
        "fcu", "ecu", "ft", "Ets",
    ),
    "MinMax": ("min", "max"),
    "Fatigue": ("E0", "m", "min", "max"),
    "Parallel": (),
    "Series": (),
}

MATERIAL_PARAMETER_KINDS: dict[str, dict[str, str]] = {
    "Elastic": {"E": "stress"},
    "Steel01": {"Fy": "stress", "E0": "stress"},
    "Steel02": {"Fy": "stress", "E0": "stress"},
    "ReinforcingSteel": {
        "fy": "stress", "fu": "stress", "Es": "stress", "Esh": "stress",
    },
    "Concrete01": {"fpc": "stress", "fpcu": "stress"},
    "Concrete02": {
        "fpc": "stress", "fpcu": "stress", "ft": "stress", "Ets": "stress",
    },
    "Concrete04": {
        "fc": "stress", "Ec": "stress", "fct": "stress",
    },
    "Hysteretic": {},
    "Pinching4": {},
    "Bond_SP01": {
        "Fy": "stress", "Fu": "stress", "Sy": "length", "Su": "length",
    },
    "ElasticPPGap": {},
    "FRPConfinedConcrete02": {
        "fc0": "stress", "Ec": "stress", "tfrp": "length",
        "Efrp": "stress", "R": "length", "fcu": "stress",
        "ft": "stress", "Ets": "stress",
    },
    "MinMax": {},
    "Fatigue": {},
    "Parallel": {},
    "Series": {},
}

MATERIAL_ENGINEERING_DEFAULTS: dict[str, dict[str, float]] = {
    name: {
        "poisson_ratio": 0.2 if "Concrete" in name else 0.3,
        "density": 2400.0 if "Concrete" in name else 7850.0 if name in {"Steel01", "Steel02", "ReinforcingSteel"} else 0.0,
    }
    for name in MATERIAL_PARAMETER_ORDER
}

MATERIAL_DEFAULTS: dict[str, dict[str, float]] = {
    "Elastic": {"E": 2.0e11},
    "Steel01": {"Fy": 3.55e8, "E0": 2.0e11, "b": 0.01, "a1": 0.0, "a2": 1.0, "a3": 0.0, "a4": 1.0},
    "Steel02": {"Fy": 3.55e8, "E0": 2.0e11, "b": 0.01, "R0": 20.0, "cR1": 0.925, "cR2": 0.15},
    "ReinforcingSteel": {"fy": 5.0e8, "fu": 6.5e8, "Es": 2.0e11, "Esh": 5.0e9, "eps_sh": 0.01, "eps_ult": 0.12},
    "Concrete01": {"fpc": -30.0e6, "epsc0": -0.002, "fpcu": -6.0e6, "epsU": -0.006},
    "Concrete02": {"fpc": -30.0e6, "epsc0": -0.002, "fpcu": -6.0e6, "epsU": -0.006, "lambda": 0.1, "ft": 3.0e6, "Ets": 2.0e8},
    "Concrete04": {"fc": -30.0e6, "epsc": -0.002, "epscu": -0.006, "Ec": 3.0e10, "fct": 3.0e6, "et": 0.0002, "beta": 0.1},
    "Hysteretic": {"s1p": 1.0, "e1p": 0.001, "s2p": 1.2, "e2p": 0.01, "s3p": 1.0, "e3p": 0.03, "s1n": -1.0, "e1n": -0.001, "s2n": -1.2, "e2n": -0.01, "s3n": -1.0, "e3n": -0.03, "pinchX": 0.5, "pinchY": 0.5, "damage1": 0.0, "damage2": 0.0, "beta": 0.0},
    "Pinching4": {
        "ePf1": 1.0, "ePd1": 0.001, "ePf2": 1.2, "ePd2": 0.01, "ePf3": 1.1, "ePd3": 0.02, "ePf4": 0.8, "ePd4": 0.04,
        "eNf1": -1.0, "eNd1": -0.001, "eNf2": -1.2, "eNd2": -0.01, "eNf3": -1.1, "eNd3": -0.02, "eNf4": -0.8, "eNd4": -0.04,
        "rDispP": 0.5, "rForceP": 0.25, "uForceP": 0.05, "rDispN": 0.5, "rForceN": 0.25, "uForceN": 0.05,
        "gK1": 0.0, "gK2": 0.0, "gK3": 0.0, "gK4": 0.0, "gKLim": 0.0,
        "gD1": 0.0, "gD2": 0.0, "gD3": 0.0, "gD4": 0.0, "gDLim": 0.0,
        "gF1": 0.0, "gF2": 0.0, "gF3": 0.0, "gF4": 0.0, "gFLim": 0.0, "gE": 10.0, "dmgType": 0.0,
    },
    "Bond_SP01": {"Fy": 5.0e8, "Sy": 0.001, "Fu": 6.5e8, "Su": 0.01, "b": 0.4, "R": 0.8},
    "ElasticPPGap": {"E": 1.0, "Fy": 1.0, "gap": 0.0, "eta": 0.0, "damage": 0.0},
    "FRPConfinedConcrete02": {"fc0": -30.0e6, "Ec": 3.0e10, "ec0": -0.002, "mode": 0.0, "tfrp": 0.000334, "Efrp": 7.2e10, "erup": 0.015, "R": 0.2, "fcu": -45.0e6, "ecu": -0.015, "ft": 3.0e6, "Ets": 1.5e9},
    "MinMax": {"min": -1.0e16, "max": 1.0e16},
    "Fatigue": {"E0": 0.191, "m": -0.458, "min": -1.0e16, "max": 1.0e16},
    "Parallel": {},
    "Series": {},
}


@dataclass
class MaterialData:
    tag: int
    name: str
    material_type: str
    parameters: dict[str, float] = field(default_factory=dict)
    poisson_ratio: float = 0.3
    density: float = 0.0
    base_material_tag: int | None = None
    material_tags: list[int] = field(default_factory=list)
    factors: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Material {self.tag}"
        self.material_type = str(self.material_type)
        if self.tag <= 0:
            raise ValueError("Material tag must be a positive integer.")
        if self.material_type not in MATERIAL_PARAMETER_ORDER:
            raise ValueError(f"Unsupported material type: {self.material_type}")

        defaults = MATERIAL_DEFAULTS[self.material_type]
        normalized: dict[str, float] = {}
        for key in MATERIAL_PARAMETER_ORDER[self.material_type]:
            normalized[key] = float(self.parameters.get(key, defaults[key]))
        self.parameters = normalized

        self.base_material_tag = (
            None
            if self.base_material_tag is None
            else int(self.base_material_tag)
        )
        self.material_tags = [int(tag) for tag in self.material_tags]
        self.factors = [float(value) for value in self.factors]

        if self.material_type in {"MinMax", "Fatigue"}:
            if self.base_material_tag is None or self.base_material_tag <= 0:
                raise ValueError(
                    f"{self.material_type} requires a valid base material tag."
                )
            self.material_tags = []
            self.factors = []
        elif self.material_type in {"Parallel", "Series"}:
            self.base_material_tag = None
            if not self.material_tags:
                raise ValueError(
                    f"{self.material_type} requires at least one component material."
                )
            if any(tag <= 0 for tag in self.material_tags):
                raise ValueError("Component material tags must be positive.")
            if len(set(self.material_tags)) != len(self.material_tags):
                raise ValueError(
                    f"{self.material_type} component material tags must be unique."
                )
            if self.material_type == "Parallel":
                if not self.factors:
                    self.factors = [1.0] * len(self.material_tags)
                if len(self.factors) != len(self.material_tags):
                    raise ValueError(
                        "Parallel requires one factor per component material."
                    )
            else:
                self.factors = []
        else:
            self.base_material_tag = None
            self.material_tags = []
            self.factors = []

        engineering_defaults = MATERIAL_ENGINEERING_DEFAULTS[self.material_type]
        if self.poisson_ratio is None:
            self.poisson_ratio = engineering_defaults["poisson_ratio"]
        if self.density is None:
            self.density = engineering_defaults["density"]

        self.poisson_ratio = float(self.poisson_ratio)
        self.density = float(self.density)
        if not (-0.99 < self.poisson_ratio < 0.5):
            raise ValueError("Poisson ratio must be between -0.99 and 0.5.")
        if self.density < 0.0:
            raise ValueError("Material density cannot be negative.")

    def elastic_modulus(self) -> float:
        if self.material_type == "Elastic":
            return float(self.parameters["E"])
        if self.material_type in {"Steel01", "Steel02"}:
            return float(self.parameters["E0"])
        if self.material_type == "ReinforcingSteel":
            return float(self.parameters["Es"])
        if self.material_type in {"Concrete01", "Concrete02"}:
            epsc0 = float(self.parameters["epsc0"])
            if abs(epsc0) <= 1.0e-16:
                raise ValueError(
                    f"Concrete02 material {self.tag} has zero epsc0."
                )
            return abs(2.0 * float(self.parameters["fpc"]) / epsc0)
        if self.material_type == "Concrete04":
            return float(self.parameters["Ec"])
        if self.material_type == "FRPConfinedConcrete02":
            return float(self.parameters["Ec"])
        raise ValueError(
            f"Material {self.tag} does not expose an elastic modulus."
        )

    def shear_modulus(self) -> float:
        return self.elastic_modulus() / (2.0 * (1.0 + self.poisson_ratio))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "material_type": self.material_type,
            "parameters": dict(self.parameters),
            "poisson_ratio": self.poisson_ratio,
            "density": self.density,
            "base_material_tag": self.base_material_tag,
            "material_tags": list(self.material_tags),
            "factors": list(self.factors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MaterialData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Material {data['tag']}")),
            material_type=str(
                data.get("material_type", data.get("type", "Elastic"))
            ),
            parameters={
                str(key): float(value)
                for key, value in dict(data.get("parameters", {})).items()
            },
            poisson_ratio=float(
                data.get(
                    "poisson_ratio",
                    MATERIAL_ENGINEERING_DEFAULTS[
                        str(data.get("material_type", data.get("type", "Elastic")))
                    ]["poisson_ratio"],
                )
            ),
            density=float(
                data.get(
                    "density",
                    MATERIAL_ENGINEERING_DEFAULTS[
                        str(data.get("material_type", data.get("type", "Elastic")))
                    ]["density"],
                )
            ),
            base_material_tag=(
                None
                if data.get("base_material_tag") is None
                else int(data.get("base_material_tag"))
            ),
            material_tags=[
                int(value) for value in data.get("material_tags", [])
            ],
            factors=[
                float(value) for value in data.get("factors", [])
            ],
        )


SECTION_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "Elastic": ("E", "A", "Iz", "Iy", "G", "J"),
    "Fiber": ("GJ",),
}

SECTION_DEFAULTS: dict[str, dict[str, float]] = {
    "Elastic": {
        "E": 2.0e11,
        "A": 0.02,
        "Iz": 8.0e-5,
        "Iy": 8.0e-5,
        "G": 7.6923e10,
        "J": 8.0e-5,
    },
    "Fiber": {
        "GJ": 1.0e6,
    },
}


@dataclass
class FiberData:
    y: float
    z: float
    area: float
    material_tag: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "y": float(self.y),
            "z": float(self.z),
            "area": float(self.area),
            "material_tag": int(self.material_tag),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FiberData":
        return cls(
            y=float(data["y"]),
            z=float(data["z"]),
            area=float(data["area"]),
            material_tag=int(data["material_tag"]),
        )


@dataclass
class FiberComponentData:
    component_type: str
    name: str
    material_tag: int
    parameters: dict[str, float] = field(default_factory=dict)

    DEFAULTS: dict[str, dict[str, float]] = field(
        init=False,
        repr=False,
        default_factory=lambda: {
            "RectPatch": {
                "y_center": 0.0,
                "z_center": 0.0,
                "width_y": 0.4,
                "depth_z": 0.4,
                "n_y": 10.0,
                "n_z": 10.0,
            },
            "CircPatch": {
                "y_center": 0.0,
                "z_center": 0.0,
                "r_inner": 0.0,
                "r_outer": 0.2,
                "n_radial": 4.0,
                "n_circum": 24.0,
                "start_angle": 0.0,
                "end_angle": 360.0,
            },
            "StraightLayer": {
                "y_i": -0.15,
                "z_i": -0.15,
                "y_j": 0.15,
                "z_j": -0.15,
                "n_bars": 4.0,
                "bar_area": math.pi * 0.02 ** 2 / 4.0,
            },
            "CircLayer": {
                "y_center": 0.0,
                "z_center": 0.0,
                "radius": 0.15,
                "n_bars": 8.0,
                "bar_area": math.pi * 0.02 ** 2 / 4.0,
                "start_angle": 0.0,
                "end_angle": 360.0,
            },
            "SingleFiber": {
                "y": 0.0,
                "z": 0.0,
                "area": 1.0e-4,
            },
        },
    )

    def __post_init__(self) -> None:
        self.component_type = str(self.component_type)
        self.name = str(self.name).strip() or self.component_type
        self.material_tag = int(self.material_tag)
        defaults = self.DEFAULTS.get(self.component_type)
        if defaults is None:
            raise ValueError(
                f"Unsupported fiber component type: {self.component_type}"
            )
        if self.material_tag <= 0:
            raise ValueError(
                "Fiber component material tag must be positive."
            )
        self.parameters = {
            key: float(self.parameters.get(key, default))
            for key, default in defaults.items()
        }
        self._validate()

    def _positive_int(self, key: str) -> int:
        value = int(round(self.parameters[key]))
        if value < 1:
            raise ValueError(f"{key} must be at least 1.")
        self.parameters[key] = float(value)
        return value

    def _validate_angles(self) -> None:
        start = self.parameters["start_angle"]
        end = self.parameters["end_angle"]
        span = end - start
        if span <= 0.0 or span > 360.0 + 1.0e-9:
            raise ValueError(
                "Fiber component angle span must be in (0, 360] degrees."
            )

    def _validate(self) -> None:
        p = self.parameters
        if self.component_type == "RectPatch":
            if p["width_y"] <= 0.0 or p["depth_z"] <= 0.0:
                raise ValueError("Rectangle patch dimensions must be positive.")
            self._positive_int("n_y")
            self._positive_int("n_z")
        elif self.component_type == "CircPatch":
            if p["r_inner"] < 0.0 or p["r_outer"] <= p["r_inner"]:
                raise ValueError(
                    "Circular patch needs 0 <= inner radius < outer radius."
                )
            self._positive_int("n_radial")
            self._positive_int("n_circum")
            self._validate_angles()
        elif self.component_type == "StraightLayer":
            self._positive_int("n_bars")
            if p["bar_area"] <= 0.0:
                raise ValueError("Rebar area must be positive.")
        elif self.component_type == "CircLayer":
            self._positive_int("n_bars")
            if p["radius"] <= 0.0 or p["bar_area"] <= 0.0:
                raise ValueError(
                    "Circular rebar radius and bar area must be positive."
                )
            self._validate_angles()
        elif self.component_type == "SingleFiber":
            if p["area"] <= 0.0:
                raise ValueError("Fiber area must be positive.")

    def compile_fibers(self) -> list[FiberData]:
        p = self.parameters
        mat = self.material_tag
        result: list[FiberData] = []

        if self.component_type == "RectPatch":
            n_y = int(p["n_y"])
            n_z = int(p["n_z"])
            dy = p["width_y"] / n_y
            dz = p["depth_z"] / n_z
            y0 = p["y_center"] - 0.5 * p["width_y"]
            z0 = p["z_center"] - 0.5 * p["depth_z"]
            area = dy * dz
            for iy in range(n_y):
                y = y0 + (iy + 0.5) * dy
                for iz in range(n_z):
                    z = z0 + (iz + 0.5) * dz
                    result.append(FiberData(y, z, area, mat))
            return result

        if self.component_type == "CircPatch":
            n_r = int(p["n_radial"])
            n_t = int(p["n_circum"])
            r0 = p["r_inner"]
            r1 = p["r_outer"]
            dr = (r1 - r0) / n_r
            start = math.radians(p["start_angle"])
            span = math.radians(p["end_angle"] - p["start_angle"])
            dtheta = span / n_t
            for ir in range(n_r):
                inner = r0 + ir * dr
                outer = inner + dr
                ring_delta = outer * outer - inner * inner
                for it in range(n_t):
                    theta0 = start + it * dtheta
                    theta = theta0 + 0.5 * dtheta
                    area = 0.5 * ring_delta * dtheta
                    if ring_delta <= 1.0e-30:
                        radius = 0.0
                    else:
                        radius = (
                            4.0
                            * math.sin(0.5 * dtheta)
                            * (outer ** 3 - inner ** 3)
                            / (3.0 * dtheta * ring_delta)
                        )
                    result.append(
                        FiberData(
                            p["y_center"] + radius * math.cos(theta),
                            p["z_center"] + radius * math.sin(theta),
                            area,
                            mat,
                        )
                    )
            return result

        if self.component_type == "StraightLayer":
            count = int(p["n_bars"])
            if count == 1:
                positions = [(0.5,)]
            else:
                positions = [
                    (index / (count - 1),)
                    for index in range(count)
                ]
            for (ratio,) in positions:
                result.append(
                    FiberData(
                        p["y_i"] + ratio * (p["y_j"] - p["y_i"]),
                        p["z_i"] + ratio * (p["z_j"] - p["z_i"]),
                        p["bar_area"],
                        mat,
                    )
                )
            return result

        if self.component_type == "CircLayer":
            count = int(p["n_bars"])
            start_deg = p["start_angle"]
            span_deg = p["end_angle"] - start_deg
            closed = math.isclose(span_deg, 360.0, abs_tol=1.0e-9)
            if count == 1:
                angles = [start_deg + 0.5 * span_deg]
            elif closed:
                angles = [
                    start_deg + span_deg * index / count
                    for index in range(count)
                ]
            else:
                angles = [
                    start_deg + span_deg * index / (count - 1)
                    for index in range(count)
                ]
            for angle_deg in angles:
                angle = math.radians(angle_deg)
                result.append(
                    FiberData(
                        p["y_center"] + p["radius"] * math.cos(angle),
                        p["z_center"] + p["radius"] * math.sin(angle),
                        p["bar_area"],
                        mat,
                    )
                )
            return result

        if self.component_type == "SingleFiber":
            return [
                FiberData(
                    p["y"],
                    p["z"],
                    p["area"],
                    mat,
                )
            ]

        raise ValueError(
            f"Unsupported fiber component type: {self.component_type}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_type": self.component_type,
            "name": self.name,
            "material_tag": self.material_tag,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FiberComponentData":
        return cls(
            component_type=str(data["component_type"]),
            name=str(data.get("name", data["component_type"])),
            material_tag=int(data["material_tag"]),
            parameters={
                str(key): float(value)
                for key, value in dict(data.get("parameters", {})).items()
            },
        )


@dataclass
class SectionData:
    tag: int
    name: str
    section_type: str
    parameters: dict[str, float] = field(default_factory=dict)
    fibers: list[FiberData] = field(default_factory=list)
    material_tag: int | None = None
    fiber_components: list[FiberComponentData] = field(default_factory=list)
    display_geometry: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Section {self.tag}"
        self.section_type = str(self.section_type)
        if self.tag <= 0:
            raise ValueError("Section tag must be a positive integer.")
        if self.section_type not in SECTION_PARAMETER_ORDER:
            raise ValueError(f"Unsupported section type: {self.section_type}")

        defaults = SECTION_DEFAULTS[self.section_type]
        self.parameters = {
            key: float(self.parameters.get(key, defaults[key]))
            for key in SECTION_PARAMETER_ORDER[self.section_type]
        }
        self.fibers = [
            fiber if isinstance(fiber, FiberData) else FiberData.from_dict(fiber)
            for fiber in self.fibers
        ]
        self.fiber_components = [
            component
            if isinstance(component, FiberComponentData)
            else FiberComponentData.from_dict(component)
            for component in self.fiber_components
        ]
        self.material_tag = (
            None if self.material_tag is None else int(self.material_tag)
        )
        if self.section_type != "Elastic":
            self.material_tag = None

        raw_geometry = (
            self.display_geometry
            if isinstance(self.display_geometry, dict)
            else {}
        )
        shape = str(raw_geometry.get("shape", "") or "").strip()
        raw_dimensions = raw_geometry.get("dimensions", {})
        dimensions: dict[str, float] = {}
        if isinstance(raw_dimensions, dict):
            for key, value in raw_dimensions.items():
                try:
                    dimensions[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
        self.display_geometry = (
            {"shape": shape, "dimensions": dimensions}
            if shape and dimensions
            else {}
        )

    def compiled_fibers(self) -> list[FiberData]:
        if self.section_type != "Fiber":
            return []
        compiled = list(self.fibers)
        for component in self.fiber_components:
            compiled.extend(component.compile_fibers())
        return compiled

    def fiber_material_tags(self) -> set[int]:
        if self.section_type != "Fiber":
            return set()
        return {
            fiber.material_tag
            for fiber in self.fibers
        } | {
            component.material_tag
            for component in self.fiber_components
        }

    def fiber_area_and_centroid(
        self,
    ) -> tuple[float, tuple[float, float]]:
        fibers = self.compiled_fibers()
        total = sum(fiber.area for fiber in fibers)
        if total <= 0.0:
            return 0.0, (0.0, 0.0)
        y = sum(fiber.y * fiber.area for fiber in fibers) / total
        z = sum(fiber.z * fiber.area for fiber in fibers) / total
        return total, (y, z)

    def resolved_elastic_parameters(
        self,
        materials: dict[int, MaterialData] | None = None,
    ) -> dict[str, float]:
        if self.section_type != "Elastic":
            raise ValueError(
                f"Section {self.tag} is not an Elastic section."
            )

        resolved = dict(self.parameters)
        if self.material_tag is None:
            return resolved
        if materials is None or self.material_tag not in materials:
            raise ValueError(
                f"Section {self.tag} references missing material "
                f"{self.material_tag}."
            )

        material = materials[self.material_tag]
        resolved["E"] = material.elastic_modulus()
        resolved["G"] = material.shear_modulus()
        return resolved

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "section_type": self.section_type,
            "parameters": dict(self.parameters),
            "fibers": [fiber.to_dict() for fiber in self.fibers],
            "fiber_components": [
                component.to_dict()
                for component in self.fiber_components
            ],
            "material_tag": self.material_tag,
            "display_geometry": {
                "shape": str(self.display_geometry.get("shape", "")),
                "dimensions": dict(
                    self.display_geometry.get("dimensions", {})
                ),
            }
            if self.display_geometry
            else {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectionData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Section {data['tag']}")),
            section_type=str(
                data.get("section_type", data.get("type", "Elastic"))
            ),
            parameters={
                str(key): float(value)
                for key, value in dict(data.get("parameters", {})).items()
            },
            fibers=[
                FiberData.from_dict(dict(item))
                for item in data.get("fibers", [])
            ],
            fiber_components=[
                FiberComponentData.from_dict(dict(item))
                for item in data.get("fiber_components", [])
            ],
            material_tag=data.get("material_tag"),
            display_geometry=dict(data.get("display_geometry", {})),
        )


@dataclass
class TransformationData:
    tag: int
    name: str
    transformation_type: str
    vecxz: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Transformation {self.tag}"
        self.transformation_type = str(self.transformation_type)
        if self.tag <= 0:
            raise ValueError("Transformation tag must be a positive integer.")
        if self.transformation_type not in {
            "Linear",
            "PDelta",
            "Corotational",
        }:
            raise ValueError(
                f"Unsupported transformation type: {self.transformation_type}"
            )
        self.vecxz = tuple(float(value) for value in self.vecxz)
        if len(self.vecxz) != 3:
            raise ValueError("Transformation orientation vector must have 3 values.")
        if sum(value * value for value in self.vecxz) <= 1.0e-24:
            raise ValueError("Transformation orientation vector cannot be zero.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "transformation_type": self.transformation_type,
            "vecxz": list(self.vecxz),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransformationData":
        raw_vec = data.get("vecxz", (0.0, 0.0, 1.0))
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Transformation {data['tag']}")),
            transformation_type=str(
                data.get(
                    "transformation_type",
                    data.get("type", "Linear"),
                )
            ),
            vecxz=(
                float(raw_vec[0]),
                float(raw_vec[1]),
                float(raw_vec[2]),
            ),
        )


@dataclass
class ConstraintData:
    tag: int
    name: str
    constraint_type: str
    retained_node: int
    constrained_nodes: list[int] = field(default_factory=list)
    dofs: tuple[int, ...] = ()
    link_type: str = "beam"
    perp_dirn: int = 3

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Constraint {self.tag}"
        self.constraint_type = str(self.constraint_type)
        self.retained_node = int(self.retained_node)
        self.constrained_nodes = sorted({
            int(tag)
            for tag in self.constrained_nodes
            if int(tag) != self.retained_node
        })
        self.dofs = tuple(sorted({int(dof) for dof in self.dofs}))
        self.link_type = str(self.link_type)
        self.perp_dirn = int(self.perp_dirn)

        if self.tag <= 0:
            raise ValueError("Constraint tag must be a positive integer.")
        if self.retained_node <= 0:
            raise ValueError("Retained node must be a positive integer.")
        if not self.constrained_nodes:
            raise ValueError("Constraint needs at least one constrained node.")

        if self.constraint_type == "equalDOF":
            if not self.dofs:
                raise ValueError("equalDOF needs at least one DOF.")
            if any(dof < 1 or dof > 6 for dof in self.dofs):
                raise ValueError("equalDOF DOFs must be in the range 1..6.")
        elif self.constraint_type == "rigidLink":
            if self.link_type not in {"bar", "beam"}:
                raise ValueError("rigidLink type must be 'bar' or 'beam'.")
        elif self.constraint_type == "rigidDiaphragm":
            if self.perp_dirn not in {1, 2, 3}:
                raise ValueError(
                    "rigidDiaphragm perpendicular direction must be 1, 2, or 3."
                )
        else:
            raise ValueError(
                f"Unsupported constraint type: {self.constraint_type}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "constraint_type": self.constraint_type,
            "retained_node": self.retained_node,
            "constrained_nodes": list(self.constrained_nodes),
            "dofs": list(self.dofs),
            "link_type": self.link_type,
            "perp_dirn": self.perp_dirn,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConstraintData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Constraint {data['tag']}")),
            constraint_type=str(data.get("constraint_type", "equalDOF")),
            retained_node=int(data["retained_node"]),
            constrained_nodes=[
                int(tag) for tag in data.get("constrained_nodes", [])
            ],
            dofs=tuple(int(dof) for dof in data.get("dofs", [])),
            link_type=str(data.get("link_type", "beam")),
            perp_dirn=int(data.get("perp_dirn", 3)),
        )


@dataclass
class ConnectionData:
    tag: int
    name: str
    connection_type: str
    node_i: int
    node_j: int
    materials_by_dof: dict[int, int] = field(default_factory=dict)
    orient_x: tuple[float, float, float] = (1.0, 0.0, 0.0)
    orient_y: tuple[float, float, float] = (0.0, 1.0, 0.0)
    do_rayleigh: bool = False
    generated_ground_node: int | None = None

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Connection {self.tag}"
        self.connection_type = str(self.connection_type)
        self.node_i = int(self.node_i)
        self.node_j = int(self.node_j)
        self.materials_by_dof = {
            int(dof): int(material_tag)
            for dof, material_tag in self.materials_by_dof.items()
        }
        self.orient_x = tuple(float(v) for v in self.orient_x)
        self.orient_y = tuple(float(v) for v in self.orient_y)
        self.do_rayleigh = bool(self.do_rayleigh)
        self.generated_ground_node = (
            None
            if self.generated_ground_node is None
            else int(self.generated_ground_node)
        )

        if self.tag <= 0:
            raise ValueError("Connection tag must be a positive integer.")
        if self.connection_type not in {"zeroLength", "twoNodeLink"}:
            raise ValueError(
                f"Unsupported connection type: {self.connection_type}"
            )
        if self.node_i <= 0 or self.node_j <= 0:
            raise ValueError("Connection node tags must be positive.")
        if self.node_i == self.node_j:
            raise ValueError("Connection needs two different node tags.")
        if not self.materials_by_dof:
            raise ValueError("Connection needs at least one active DOF.")
        if any(dof < 1 or dof > 6 for dof in self.materials_by_dof):
            raise ValueError("Connection DOFs must be in the range 1..6.")
        if len(self.orient_x) != 3 or len(self.orient_y) != 3:
            raise ValueError("Connection orientation vectors need 3 values.")
        if sum(v * v for v in self.orient_x) <= 1.0e-24:
            raise ValueError("Connection local X vector cannot be zero.")
        if sum(v * v for v in self.orient_y) <= 1.0e-24:
            raise ValueError("Connection local Y vector cannot be zero.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "connection_type": self.connection_type,
            "node_i": self.node_i,
            "node_j": self.node_j,
            "materials_by_dof": {
                str(dof): material_tag
                for dof, material_tag in sorted(self.materials_by_dof.items())
            },
            "orient_x": list(self.orient_x),
            "orient_y": list(self.orient_y),
            "do_rayleigh": self.do_rayleigh,
            "generated_ground_node": self.generated_ground_node,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectionData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Connection {data['tag']}")),
            connection_type=str(
                data.get("connection_type", "zeroLength")
            ),
            node_i=int(data["node_i"]),
            node_j=int(data["node_j"]),
            materials_by_dof={
                int(dof): int(material_tag)
                for dof, material_tag in dict(
                    data.get("materials_by_dof", {})
                ).items()
            },
            orient_x=tuple(
                float(v) for v in data.get("orient_x", (1.0, 0.0, 0.0))
            ),
            orient_y=tuple(
                float(v) for v in data.get("orient_y", (0.0, 1.0, 0.0))
            ),
            do_rayleigh=bool(data.get("do_rayleigh", False)),
            generated_ground_node=data.get("generated_ground_node"),
        )


@dataclass
class TimeSeriesData:
    tag: int
    name: str
    series_type: str
    factor: float = 1.0
    dt: float = 0.01
    values: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Time Series {self.tag}"
        self.series_type = str(self.series_type)
        self.factor = float(self.factor)
        self.dt = float(self.dt)
        self.values = [float(value) for value in self.values]
        if self.tag <= 0:
            raise ValueError("Time series tag must be positive.")
        if self.series_type not in {"Constant", "Linear", "Path"}:
            raise ValueError(f"Unsupported time series type: {self.series_type}")
        if self.series_type == "Path":
            if self.dt <= 0.0:
                raise ValueError("Path time series dt must be positive.")
            if not self.values:
                raise ValueError("Path time series needs at least one value.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "series_type": self.series_type,
            "factor": self.factor,
            "dt": self.dt,
            "values": list(self.values),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimeSeriesData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Time Series {data['tag']}")),
            series_type=str(data.get("series_type", "Linear")),
            factor=float(data.get("factor", 1.0)),
            dt=float(data.get("dt", 0.01)),
            values=[float(value) for value in data.get("values", [])],
        )


@dataclass
class LoadPatternData:
    tag: int
    name: str
    pattern_type: str
    time_series_tag: int
    direction: int = 1
    factor: float = 1.0
    vel0: float = 0.0

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Load Pattern {self.tag}"
        self.pattern_type = str(self.pattern_type)
        self.time_series_tag = int(self.time_series_tag)
        self.direction = int(self.direction)
        self.factor = float(self.factor)
        self.vel0 = float(self.vel0)
        if self.tag <= 0:
            raise ValueError("Load pattern tag must be positive.")
        if self.time_series_tag <= 0:
            raise ValueError("Load pattern needs a valid time series tag.")
        if self.pattern_type not in {"Plain", "UniformExcitation"}:
            raise ValueError(f"Unsupported pattern type: {self.pattern_type}")
        if self.pattern_type == "UniformExcitation" and not 1 <= self.direction <= 6:
            raise ValueError("UniformExcitation direction must be 1..6.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "pattern_type": self.pattern_type,
            "time_series_tag": self.time_series_tag,
            "direction": self.direction,
            "factor": self.factor,
            "vel0": self.vel0,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoadPatternData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Load Pattern {data['tag']}")),
            pattern_type=str(data.get("pattern_type", "Plain")),
            time_series_tag=int(data["time_series_tag"]),
            direction=int(data.get("direction", 1)),
            factor=float(data.get("factor", 1.0)),
            vel0=float(data.get("vel0", 0.0)),
        )


@dataclass
class NodalLoadData:
    tag: int
    name: str
    pattern_tag: int
    node_tag: int
    values: tuple[float, float, float, float, float, float]

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Nodal Load {self.tag}"
        self.pattern_tag = int(self.pattern_tag)
        self.node_tag = int(self.node_tag)
        self.values = tuple(float(value) for value in self.values)
        if self.tag <= 0:
            raise ValueError("Nodal load tag must be positive.")
        if self.pattern_tag <= 0 or self.node_tag <= 0:
            raise ValueError("Nodal load needs valid pattern and node tags.")
        if len(self.values) != 6:
            raise ValueError("Nodal load needs six DOF values.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "pattern_tag": self.pattern_tag,
            "node_tag": self.node_tag,
            "values": list(self.values),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodalLoadData":
        values = tuple(float(value) for value in data.get("values", (0.0,) * 6))
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Nodal Load {data['tag']}")),
            pattern_tag=int(data["pattern_tag"]),
            node_tag=int(data["node_tag"]),
            values=values,
        )


@dataclass
class PrescribedDisplacementData:
    tag: int
    name: str
    pattern_tag: int
    node_tag: int
    dof: int
    value: float

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = (
            str(self.name).strip()
            or f"Prescribed Displacement {self.tag}"
        )
        self.pattern_tag = int(self.pattern_tag)
        self.node_tag = int(self.node_tag)
        self.dof = int(self.dof)
        self.value = float(self.value)
        if self.tag <= 0:
            raise ValueError(
                "Prescribed displacement tag must be positive."
            )
        if self.pattern_tag <= 0 or self.node_tag <= 0:
            raise ValueError(
                "Prescribed displacement needs valid pattern and node tags."
            )
        if self.dof not in range(1, 7):
            raise ValueError(
                "Prescribed displacement DOF must be between 1 and 6."
            )
        if not math.isfinite(self.value):
            raise ValueError(
                "Prescribed displacement value must be finite."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "pattern_tag": self.pattern_tag,
            "node_tag": self.node_tag,
            "dof": self.dof,
            "value": self.value,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "PrescribedDisplacementData":
        return cls(
            tag=int(data["tag"]),
            name=str(
                data.get(
                    "name",
                    f"Prescribed Displacement {data['tag']}",
                )
            ),
            pattern_tag=int(data["pattern_tag"]),
            node_tag=int(data["node_tag"]),
            dof=int(data.get("dof", 1)),
            value=float(data.get("value", 0.0)),
        )


@dataclass
class ElementLoadData:
    tag: int
    name: str
    pattern_tag: int
    element_tag: int
    load_type: str = "Uniform"
    wx: float = 0.0
    wy: float = 0.0
    wz: float = 0.0
    px: float = 0.0
    py: float = 0.0
    pz: float = 0.0
    x_over_l: float = 0.5
    gravity: tuple[float, float, float] = (0.0, 0.0, -9.81)
    density_override: float = 0.0

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Element Load {self.tag}"
        self.pattern_tag = int(self.pattern_tag)
        self.element_tag = int(self.element_tag)
        self.load_type = str(self.load_type)
        self.wx = float(self.wx)
        self.wy = float(self.wy)
        self.wz = float(self.wz)
        self.px = float(self.px)
        self.py = float(self.py)
        self.pz = float(self.pz)
        self.x_over_l = float(self.x_over_l)
        self.gravity = tuple(float(value) for value in self.gravity)
        self.density_override = float(self.density_override)

        if self.tag <= 0:
            raise ValueError("Element load tag must be positive.")
        if self.pattern_tag <= 0 or self.element_tag <= 0:
            raise ValueError(
                "Element load needs valid pattern and element tags."
            )
        if self.load_type not in {"Uniform", "Point", "SelfWeight"}:
            raise ValueError(
                f"Unsupported element load type: {self.load_type}"
            )
        if len(self.gravity) != 3:
            raise ValueError("Gravity vector needs three components.")
        if self.density_override < 0.0:
            raise ValueError("Density override cannot be negative.")
        if self.load_type == "Point" and not 0.0 <= self.x_over_l <= 1.0:
            raise ValueError("Point-load x/L must be between 0 and 1.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "pattern_tag": self.pattern_tag,
            "element_tag": self.element_tag,
            "load_type": self.load_type,
            "wx": self.wx,
            "wy": self.wy,
            "wz": self.wz,
            "px": self.px,
            "py": self.py,
            "pz": self.pz,
            "x_over_l": self.x_over_l,
            "gravity": list(self.gravity),
            "density_override": self.density_override,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementLoadData":
        gravity = data.get("gravity", (0.0, 0.0, -9.81))
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Element Load {data['tag']}")),
            pattern_tag=int(data["pattern_tag"]),
            element_tag=int(data["element_tag"]),
            load_type=str(data.get("load_type", "Uniform")),
            wx=float(data.get("wx", 0.0)),
            wy=float(data.get("wy", 0.0)),
            wz=float(data.get("wz", 0.0)),
            px=float(data.get("px", 0.0)),
            py=float(data.get("py", 0.0)),
            pz=float(data.get("pz", 0.0)),
            x_over_l=float(data.get("x_over_l", 0.5)),
            gravity=(
                float(gravity[0]),
                float(gravity[1]),
                float(gravity[2]),
            ),
            density_override=float(data.get("density_override", 0.0)),
        )


@dataclass
class MassSourceData:
    tag: int
    name: str
    include_self_mass: bool = True
    load_factors: dict[int, float] = field(default_factory=dict)
    gravity_axis: int = 3
    directions: tuple[int, ...] = (1, 2)

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Mass Source {self.tag}"
        self.include_self_mass = bool(self.include_self_mass)
        raw_load_factors = {
            int(tag): float(factor)
            for tag, factor in dict(self.load_factors).items()
        }
        if any(
            not math.isfinite(factor) or factor < 0.0
            for factor in raw_load_factors.values()
        ):
            raise ValueError(
                "Mass source load factors must be finite and non-negative."
            )
        self.load_factors = {
            tag: factor
            for tag, factor in raw_load_factors.items()
            if factor > 0.0
        }
        self.gravity_axis = int(self.gravity_axis)
        self.directions = tuple(
            sorted({int(dof) for dof in self.directions})
        )
        if self.tag <= 0:
            raise ValueError("Mass source tag must be positive.")
        if self.gravity_axis not in (1, 2, 3):
            raise ValueError("Mass source gravity axis must be 1, 2, or 3.")
        if not self.directions or any(
            dof not in (1, 2, 3) for dof in self.directions
        ):
            raise ValueError(
                "Mass source directions must contain translational DOFs 1..3."
            )
        if any(factor < 0.0 for factor in self.load_factors.values()):
            raise ValueError("Mass source load factors cannot be negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "include_self_mass": self.include_self_mass,
            "load_factors": {
                str(tag): factor
                for tag, factor in sorted(self.load_factors.items())
            },
            "gravity_axis": self.gravity_axis,
            "directions": list(self.directions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MassSourceData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Mass Source {data['tag']}")),
            include_self_mass=bool(data.get("include_self_mass", True)),
            load_factors={
                int(tag): float(factor)
                for tag, factor in dict(
                    data.get("load_factors", {})
                ).items()
            },
            gravity_axis=int(data.get("gravity_axis", 3)),
            directions=tuple(
                int(dof) for dof in data.get("directions", (1, 2))
            ),
        )


@dataclass
class AnalysisSettingsData:
    tag: int
    name: str
    analysis_type: str = "Static"
    constraints_handler: str = "Transformation"
    numberer: str = "RCM"
    system: str = "UmfPack"
    test: str = "NormDispIncr"
    tolerance: float = 1.0e-8
    max_iterations: int = 50
    algorithm: str = "Newton"
    steps: int = 10
    load_increment: float = 0.1
    control_node: int = 1
    control_dof: int = 1
    displacement_increment: float = 0.001
    cyclic_targets: list[float] = field(
        default_factory=lambda: [0.005, -0.005, 0.01, -0.01, 0.0]
    )
    cyclic_increment: float = 0.001
    dt: float = 0.01
    gamma: float = 0.5
    beta: float = 0.25
    rayleigh_damping_ratio: float = 0.0
    rayleigh_mode_i: int = 1
    rayleigh_mode_j: int = 3
    preload_gravity: bool = False
    gravity_steps: int = 10
    deferred_pattern_tags: list[int] = field(default_factory=list)
    num_modes: int = 3
    eigen_solver: str = "-genBandArpack"
    recovery: bool = True
    adaptive_step: bool = False
    adaptive_cutback_factor: float = 0.5
    adaptive_min_factor: float = 0.125
    adaptive_growth_factor: float = 1.5
    adaptive_easy_iterations: int = 4
    adaptive_growth_after: int = 3
    live_convergence: bool = True
    show_external_console: bool = False

    def __post_init__(self) -> None:
        self.tag=int(self.tag); self.name=str(self.name).strip() or f"Analysis {self.tag}"
        self.analysis_type=str(self.analysis_type)
        self.tolerance=float(self.tolerance); self.max_iterations=int(self.max_iterations)
        self.steps=int(self.steps); self.load_increment=float(self.load_increment)
        self.control_node=int(self.control_node); self.control_dof=int(self.control_dof)
        self.displacement_increment=float(self.displacement_increment)
        self.cyclic_targets=[float(value) for value in self.cyclic_targets]
        self.cyclic_increment=abs(float(self.cyclic_increment))
        self.dt=float(self.dt); self.gamma=float(self.gamma); self.beta=float(self.beta)
        self.rayleigh_damping_ratio=float(self.rayleigh_damping_ratio)
        self.rayleigh_mode_i=int(self.rayleigh_mode_i)
        self.rayleigh_mode_j=int(self.rayleigh_mode_j)
        self.preload_gravity=bool(self.preload_gravity)
        self.gravity_steps=int(self.gravity_steps)
        self.deferred_pattern_tags=sorted({
            int(tag) for tag in self.deferred_pattern_tags
        })
        self.num_modes=int(self.num_modes)
        self.eigen_solver=str(self.eigen_solver)
        self.recovery=bool(self.recovery)
        self.adaptive_step=bool(self.adaptive_step)
        self.adaptive_cutback_factor=float(self.adaptive_cutback_factor)
        self.adaptive_min_factor=float(self.adaptive_min_factor)
        self.adaptive_growth_factor=float(self.adaptive_growth_factor)
        self.adaptive_easy_iterations=int(self.adaptive_easy_iterations)
        self.adaptive_growth_after=int(self.adaptive_growth_after)
        self.live_convergence=bool(self.live_convergence)
        self.show_external_console=bool(self.show_external_console)
        if self.tag<=0: raise ValueError("Analysis tag must be positive.")
        if self.analysis_type not in {"Static","Pushover","Cyclic","Transient","Modal"}:
            raise ValueError(f"Unsupported analysis type: {self.analysis_type}")
        if self.constraints_handler not in {"Transformation","Plain"}:
            raise ValueError("Unsupported constraints handler.")
        if self.numberer not in {"RCM","Plain"}: raise ValueError("Unsupported numberer.")
        if self.system not in {"UmfPack","BandGeneral","ProfileSPD"}: raise ValueError("Unsupported system.")
        if self.test not in {"NormDispIncr","NormUnbalance","EnergyIncr"}: raise ValueError("Unsupported convergence test.")
        if self.algorithm not in {"Newton","ModifiedNewton","NewtonLineSearch"}: raise ValueError("Unsupported algorithm.")
        if self.tolerance<=0 or self.max_iterations<1: raise ValueError("Invalid convergence settings.")
        if self.steps<1: raise ValueError("Analysis steps must be at least 1.")
        if self.control_dof not in range(1,7): raise ValueError("Control DOF must be 1..6.")
        if self.adaptive_cutback_factor <= 0.0 or self.adaptive_cutback_factor >= 1.0:
            raise ValueError("Adaptive cutback factor must be between 0 and 1.")
        if self.adaptive_min_factor <= 0.0 or self.adaptive_min_factor > 1.0:
            raise ValueError("Adaptive minimum factor must be in (0, 1].")
        if self.adaptive_growth_factor < 1.0:
            raise ValueError("Adaptive growth factor must be at least 1.")
        if self.adaptive_easy_iterations < 1:
            raise ValueError("Adaptive easy-iteration threshold must be positive.")
        if self.adaptive_growth_after < 1:
            raise ValueError("Adaptive growth-after count must be positive.")
        if self.adaptive_step and self.analysis_type == "Static" and abs(self.load_increment) <= 1.0e-30:
            raise ValueError("Adaptive static analysis needs a nonzero load increment.")
        if self.adaptive_step and self.analysis_type == "Pushover" and abs(self.displacement_increment) <= 1.0e-30:
            raise ValueError("Adaptive pushover needs a nonzero displacement increment.")
        if self.analysis_type == "Cyclic":
            if not self.cyclic_targets:
                raise ValueError("Cyclic analysis needs at least one displacement target.")
            if self.cyclic_increment <= 0.0:
                raise ValueError("Cyclic max displacement increment must be positive.")
        if self.dt<=0: raise ValueError("Transient dt must be positive.")
        if not 0.0 <= self.rayleigh_damping_ratio < 1.0:
            raise ValueError("Rayleigh damping ratio must be in [0, 1).")
        if self.rayleigh_mode_i < 1 or self.rayleigh_mode_j < 1:
            raise ValueError("Rayleigh damping modes must be positive.")
        if self.rayleigh_mode_i == self.rayleigh_mode_j and self.rayleigh_damping_ratio > 0.0:
            raise ValueError("Rayleigh damping needs two different modes.")
        if self.gravity_steps < 1:
            raise ValueError("Gravity preload steps must be at least 1.")
        if any(tag <= 0 for tag in self.deferred_pattern_tags):
            raise ValueError("Deferred load-pattern tags must be positive.")
        if self.num_modes<1: raise ValueError("Number of modes must be at least 1.")
        if self.eigen_solver not in {
            "-genBandArpack",
            "-fullGenLapack",
            "-symmBandLapack",
        }:
            raise ValueError("Unsupported eigen solver.")

    def to_dict(self) -> dict[str, Any]:
        return {key:getattr(self,key) for key in (
            "tag","name","analysis_type","constraints_handler","numberer","system",
            "test","tolerance","max_iterations","algorithm","steps","load_increment",
            "control_node","control_dof","displacement_increment",
            "cyclic_targets","cyclic_increment","dt","gamma","beta",
            "rayleigh_damping_ratio","rayleigh_mode_i","rayleigh_mode_j",
            "preload_gravity","gravity_steps","deferred_pattern_tags",
            "num_modes","eigen_solver","recovery","adaptive_step",
            "adaptive_cutback_factor","adaptive_min_factor",
            "adaptive_growth_factor","adaptive_easy_iterations",
            "adaptive_growth_after","live_convergence","show_external_console"
        )}

    @classmethod
    def from_dict(cls,data:dict[str,Any]) -> "AnalysisSettingsData":
        return cls(**{key:value for key,value in data.items() if key in cls.__dataclass_fields__})


@dataclass
class RecorderData:
    tag: int
    name: str
    recorder_type: str
    target_tags: list[int] = field(default_factory=list)
    response: str = "disp"
    dofs: list[int] = field(default_factory=lambda: [1])
    file_name: str = ""
    include_time: bool = True
    section_number: int = 1
    fiber_y: float = 0.0
    fiber_z: float = 0.0
    material_tag: int | None = None

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.name = str(self.name).strip() or f"Recorder {self.tag}"
        self.recorder_type = str(self.recorder_type)
        self.target_tags = sorted({int(tag) for tag in self.target_tags})
        self.response = str(self.response)
        self.dofs = sorted({int(dof) for dof in self.dofs})
        self.file_name = str(self.file_name).strip()
        self.include_time = bool(self.include_time)
        self.section_number = int(self.section_number)
        self.fiber_y = float(self.fiber_y)
        self.fiber_z = float(self.fiber_z)
        self.material_tag = (
            int(self.material_tag)
            if self.material_tag is not None
            else None
        )
        if self.tag <= 0:
            raise ValueError("Recorder tag must be positive.")
        if self.recorder_type not in {"Node", "Element", "Section", "Fiber"}:
            raise ValueError(f"Unsupported recorder type: {self.recorder_type}")
        if not self.target_tags:
            raise ValueError("Recorder must target at least one node or element.")
        if any(tag <= 0 for tag in self.target_tags):
            raise ValueError("Recorder target tags must be positive.")
        if not self.file_name:
            self.file_name = f"recorders/recorder_{self.tag}.out"
        if self.recorder_type == "Node":
            if self.response not in {"disp", "vel", "accel", "reaction"}:
                raise ValueError("Unsupported Node recorder response.")
            if not self.dofs or any(dof not in range(1, 7) for dof in self.dofs):
                raise ValueError("Node recorder DOFs must be in 1..6.")
        elif self.recorder_type == "Element":
            if self.response not in {"globalForce", "localForce"}:
                raise ValueError("Unsupported Element recorder response.")
        elif self.recorder_type == "Section":
            if self.response not in {"force", "deformation"}:
                raise ValueError("Unsupported Section recorder response.")
            if self.section_number < 1:
                raise ValueError("Section recorder number must be at least 1.")
        elif self.recorder_type == "Fiber":
            if self.response not in {"stress", "strain", "stressStrain"}:
                raise ValueError("Unsupported Fiber recorder response.")
            if self.section_number < 1:
                raise ValueError("Fiber recorder section number must be at least 1.")
            if self.material_tag is not None and self.material_tag <= 0:
                raise ValueError("Fiber recorder material tag must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "recorder_type": self.recorder_type,
            "target_tags": list(self.target_tags),
            "response": self.response,
            "dofs": list(self.dofs),
            "file_name": self.file_name,
            "include_time": self.include_time,
            "section_number": self.section_number,
            "fiber_y": self.fiber_y,
            "fiber_z": self.fiber_z,
            "material_tag": self.material_tag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecorderData":
        return cls(
            tag=int(data["tag"]),
            name=str(data.get("name", f"Recorder {data['tag']}")),
            recorder_type=str(data.get("recorder_type", "Node")),
            target_tags=[int(tag) for tag in data.get("target_tags", [])],
            response=str(data.get("response", "disp")),
            dofs=[int(dof) for dof in data.get("dofs", [1])],
            file_name=str(data.get("file_name", "")),
            include_time=bool(data.get("include_time", True)),
            section_number=int(data.get("section_number", 1)),
            fiber_y=float(data.get("fiber_y", 0.0)),
            fiber_z=float(data.get("fiber_z", 0.0)),
            material_tag=(
                int(data["material_tag"])
                if data.get("material_tag") is not None
                else None
            ),
        )


SOLUTION_RESULT_TYPES = {
    "DeformedShape",
    "NodalDisplacement",
    "NodalReaction",
    "MemberForce",
    "FiberStress",
    "FiberStrain",
    "HingeState",
    "PushoverCurve",
    "CyclicHysteresis",
    "TimeHistory",
    "ModeShape",
    "Motion",
    "Convergence",
}


@dataclass
class SolutionResultData:
    tag: int
    analysis_tag: int
    name: str
    result_type: str
    node_scope: list[int] = field(default_factory=list)
    element_scope: list[int] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tag = int(self.tag)
        self.analysis_tag = int(self.analysis_tag)
        self.name = str(self.name).strip() or f"Result {self.tag}"
        self.result_type = str(self.result_type)
        self.node_scope = sorted({int(tag) for tag in self.node_scope})
        self.element_scope = sorted({int(tag) for tag in self.element_scope})
        self.settings = dict(self.settings)
        if self.tag <= 0:
            raise ValueError("Solution result tag must be positive.")
        if self.analysis_tag <= 0:
            raise ValueError("Solution result analysis tag must be positive.")
        if self.result_type not in SOLUTION_RESULT_TYPES:
            raise ValueError(
                f"Unsupported solution result type: {self.result_type}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "analysis_tag": self.analysis_tag,
            "name": self.name,
            "result_type": self.result_type,
            "node_scope": list(self.node_scope),
            "element_scope": list(self.element_scope),
            "settings": dict(self.settings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SolutionResultData":
        return cls(
            tag=int(data["tag"]),
            analysis_tag=int(data["analysis_tag"]),
            name=str(data.get("name", "")),
            result_type=str(data["result_type"]),
            node_scope=[
                int(tag)
                for tag in data.get("node_scope", [])
            ],
            element_scope=[
                int(tag)
                for tag in data.get("element_scope", [])
            ],
            settings=dict(data.get("settings", {})),
        )


@dataclass
class SelectionSetData:
    name: str
    node_tags: set[int] = field(default_factory=set)
    element_tags: set[int] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node_tags": sorted(self.node_tags),
            "element_tags": sorted(self.element_tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectionSetData":
        return cls(
            name=str(data["name"]),
            node_tags={int(tag) for tag in data.get("node_tags", [])},
            element_tags={int(tag) for tag in data.get("element_tags", [])},
        )


@dataclass
class ProjectDatabase:
    name: str = "Untitled"
    model: StructuralModel = field(default_factory=StructuralModel)
    selection_sets: dict[str, SelectionSetData] = field(default_factory=dict)
    materials: dict[int, MaterialData] = field(default_factory=dict)

    # Reserved object stores. They are persisted now so future editors can be
    # added without changing the top-level project architecture.
    sections: dict[int, SectionData] = field(default_factory=dict)
    transformations: dict[int, TransformationData] = field(default_factory=dict)
    constraints: dict[int, ConstraintData] = field(default_factory=dict)
    connections: dict[int, ConnectionData] = field(default_factory=dict)
    time_series: dict[int, TimeSeriesData] = field(default_factory=dict)
    load_patterns: dict[int, LoadPatternData] = field(default_factory=dict)
    nodal_loads: dict[int, NodalLoadData] = field(default_factory=dict)
    prescribed_displacements: dict[int, PrescribedDisplacementData] = field(
        default_factory=dict
    )
    element_loads: dict[int, ElementLoadData] = field(default_factory=dict)
    mass_sources: dict[int, MassSourceData] = field(default_factory=dict)
    analyses: dict[int, AnalysisSettingsData] = field(default_factory=dict)
    recorders: dict[int, RecorderData] = field(default_factory=dict)
    solution_results: dict[int, SolutionResultData] = field(
        default_factory=dict
    )
    active_analysis_tag: int | None = None

    units: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PROJECT_UNITS)
    )

    @staticmethod
    def material_dependencies(material: MaterialData) -> list[int]:
        if material.material_type in {"MinMax", "Fatigue"}:
            return (
                []
                if material.base_material_tag is None
                else [material.base_material_tag]
            )
        if material.material_type in {"Parallel", "Series"}:
            return list(material.material_tags)
        return []

    def _validate_material_dependencies(
        self,
        material: MaterialData,
        *,
        replacing_tag: int | None = None,
    ) -> None:
        dependencies = self.material_dependencies(material)
        if material.tag in dependencies:
            raise ValueError("A material cannot reference itself.")
        available = set(self.materials)
        if replacing_tag is not None:
            available.discard(int(replacing_tag))
        available.add(material.tag)
        missing = sorted(tag for tag in dependencies if tag not in available)
        if missing:
            raise ValueError(
                f"{material.material_type} references missing material tag(s): "
                + ", ".join(map(str, missing))
            )

        graph = {
            tag: self.material_dependencies(item)
            for tag, item in self.materials.items()
            if replacing_tag is None or tag != int(replacing_tag)
        }
        graph[material.tag] = dependencies

        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(tag: int) -> None:
            if tag in visited:
                return
            if tag in visiting:
                raise ValueError(
                    "Material wrapper references contain a dependency cycle."
                )
            visiting.add(tag)
            for dependency in graph.get(tag, []):
                if dependency in graph:
                    visit(dependency)
            visiting.remove(tag)
            visited.add(tag)

        for tag in graph:
            visit(tag)

    def materials_using_material(self, material_tag: int) -> list[int]:
        target = int(material_tag)
        return sorted(
            material.tag
            for material in self.materials.values()
            if target in self.material_dependencies(material)
        )

    def next_material_tag(self) -> int:
        return max(self.materials, default=0) + 1

    def add_material(self, material: MaterialData) -> None:
        if material.tag in self.materials:
            raise ValueError(f"Material tag {material.tag} already exists.")
        self._validate_material_dependencies(material)
        self.materials[material.tag] = material

    def update_material(self, original_tag: int, material: MaterialData) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.materials:
            raise ValueError(f"Material tag {original_tag} does not exist.")
        if material.tag != original_tag and material.tag in self.materials:
            raise ValueError(f"Material tag {material.tag} already exists.")
        self._validate_material_dependencies(
            material,
            replacing_tag=original_tag,
        )
        self.materials.pop(original_tag)
        self.materials[material.tag] = material

    def remove_material(self, tag: int) -> None:
        self.materials.pop(int(tag), None)

    def next_section_tag(self) -> int:
        return max(self.sections, default=0) + 1

    def add_section(self, section: SectionData) -> None:
        if section.tag in self.sections:
            raise ValueError(f"Section tag {section.tag} already exists.")
        self._validate_section_materials(section)
        self.sections[section.tag] = section

    def update_section(self, original_tag: int, section: SectionData) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.sections:
            raise ValueError(f"Section tag {original_tag} does not exist.")
        if section.tag != original_tag and section.tag in self.sections:
            raise ValueError(f"Section tag {section.tag} already exists.")
        self._validate_section_materials(section)
        self.sections.pop(original_tag)
        self.sections[section.tag] = section

    def remove_section(self, tag: int) -> None:
        self.sections.pop(int(tag), None)

    def _validate_section_materials(self, section: SectionData) -> None:
        if (
            section.section_type == "Elastic"
            and section.material_tag is not None
            and section.material_tag not in self.materials
        ):
            raise ValueError(
                f"Elastic section references missing material tag "
                f"{section.material_tag}."
            )

        if section.section_type != "Fiber":
            return

        missing = sorted(
            material_tag
            for material_tag in section.fiber_material_tags()
            if material_tag not in self.materials
        )
        if missing:
            raise ValueError(
                "Fiber section references missing material tag(s): "
                + ", ".join(map(str, missing))
            )

    def sections_using_material(self, material_tag: int) -> list[int]:
        material_tag = int(material_tag)
        return sorted(
            section.tag
            for section in self.sections.values()
            if (
                section.material_tag == material_tag
                or material_tag in section.fiber_material_tags()
            )
        )

    def next_transformation_tag(self) -> int:
        return max(self.transformations, default=0) + 1

    def add_transformation(self, transformation: TransformationData) -> None:
        if transformation.tag in self.transformations:
            raise ValueError(
                f"Transformation tag {transformation.tag} already exists."
            )
        self.transformations[transformation.tag] = transformation

    def update_transformation(
        self,
        original_tag: int,
        transformation: TransformationData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.transformations:
            raise ValueError(
                f"Transformation tag {original_tag} does not exist."
            )
        if (
            transformation.tag != original_tag
            and transformation.tag in self.transformations
        ):
            raise ValueError(
                f"Transformation tag {transformation.tag} already exists."
            )
        self.transformations.pop(original_tag)
        self.transformations[transformation.tag] = transformation

    def remove_transformation(self, tag: int) -> None:
        self.transformations.pop(int(tag), None)

    def next_constraint_tag(self) -> int:
        return max(self.constraints, default=0) + 1

    def _validate_constraint_nodes(self, constraint: ConstraintData) -> None:
        missing = []
        if constraint.retained_node not in self.model.nodes:
            missing.append(constraint.retained_node)
        missing.extend(
            tag
            for tag in constraint.constrained_nodes
            if tag not in self.model.nodes
        )
        if missing:
            raise ValueError(
                "Constraint references missing node tag(s): "
                + ", ".join(map(str, sorted(set(missing))))
            )

    def add_constraint(self, constraint: ConstraintData) -> None:
        if constraint.tag in self.constraints:
            raise ValueError(
                f"Constraint tag {constraint.tag} already exists."
            )
        self._validate_constraint_nodes(constraint)
        self.constraints[constraint.tag] = constraint

    def update_constraint(
        self,
        original_tag: int,
        constraint: ConstraintData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.constraints:
            raise ValueError(
                f"Constraint tag {original_tag} does not exist."
            )
        if (
            constraint.tag != original_tag
            and constraint.tag in self.constraints
        ):
            raise ValueError(
                f"Constraint tag {constraint.tag} already exists."
            )
        self._validate_constraint_nodes(constraint)
        self.constraints.pop(original_tag)
        self.constraints[constraint.tag] = constraint

    def remove_constraint(self, tag: int) -> None:
        self.constraints.pop(int(tag), None)

    def prune_constraints(self) -> list[int]:
        removed: list[int] = []
        existing_nodes = set(self.model.nodes)
        for tag, constraint in list(self.constraints.items()):
            if constraint.retained_node not in existing_nodes:
                self.constraints.pop(tag)
                removed.append(tag)
                continue
            constraint.constrained_nodes = [
                node_tag
                for node_tag in constraint.constrained_nodes
                if node_tag in existing_nodes
                and node_tag != constraint.retained_node
            ]
            if not constraint.constrained_nodes:
                self.constraints.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def next_connection_tag(self) -> int:
        return max(
            set(self.connections) | set(self.model.elements),
            default=0,
        ) + 1

    def _validate_connection(self, connection: ConnectionData) -> None:
        if connection.tag in self.model.elements:
            raise ValueError(
                f"Connection tag {connection.tag} conflicts with an element tag."
            )
        missing_nodes = [
            tag
            for tag in (connection.node_i, connection.node_j)
            if tag not in self.model.nodes
        ]
        if missing_nodes:
            raise ValueError(
                "Connection references missing node tag(s): "
                + ", ".join(map(str, missing_nodes))
            )
        missing_materials = sorted({
            material_tag
            for material_tag in connection.materials_by_dof.values()
            if material_tag not in self.materials
        })
        if missing_materials:
            raise ValueError(
                "Connection references missing material tag(s): "
                + ", ".join(map(str, missing_materials))
            )

        if connection.connection_type == "zeroLength":
            a = self.model.nodes[connection.node_i].xyz
            b = self.model.nodes[connection.node_j].xyz
            distance2 = sum((x - y) ** 2 for x, y in zip(a, b))
            if distance2 > 1.0e-14:
                raise ValueError(
                    "zeroLength connection nodes must be coincident. "
                    "Use twoNodeLink for separated nodes."
                )

    def add_connection(self, connection: ConnectionData) -> None:
        if connection.tag in self.connections:
            raise ValueError(
                f"Connection tag {connection.tag} already exists."
            )
        self._validate_connection(connection)
        self.connections[connection.tag] = connection

    def update_connection(
        self,
        original_tag: int,
        connection: ConnectionData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.connections:
            raise ValueError(
                f"Connection tag {original_tag} does not exist."
            )
        if (
            connection.tag != original_tag
            and connection.tag in self.connections
        ):
            raise ValueError(
                f"Connection tag {connection.tag} already exists."
            )
        self._validate_connection(connection)
        self.connections.pop(original_tag)
        self.connections[connection.tag] = connection

    def _ground_node_in_use_elsewhere(
        self,
        node_tag: int,
        *,
        excluding_connection: int | None = None,
    ) -> bool:
        if any(
            element.i == node_tag or element.j == node_tag
            for element in self.model.elements.values()
        ):
            return True
        for tag, connection in self.connections.items():
            if tag == excluding_connection:
                continue
            if node_tag in {connection.node_i, connection.node_j}:
                return True
        for constraint in self.constraints.values():
            if (
                constraint.retained_node == node_tag
                or node_tag in constraint.constrained_nodes
            ):
                return True
        return False

    def remove_connection(
        self,
        tag: int,
        *,
        cleanup_ground: bool = True,
    ) -> None:
        tag = int(tag)
        connection = self.connections.pop(tag, None)
        if connection is None or not cleanup_ground:
            return
        ground_tag = connection.generated_ground_node
        if (
            ground_tag is not None
            and ground_tag in self.model.nodes
            and not self._ground_node_in_use_elsewhere(ground_tag)
        ):
            self.model.remove_node(ground_tag, cascade=True)

    def create_ground_node(self, source_node_tag: int) -> int:
        source_node_tag = int(source_node_tag)
        source = self.model.nodes.get(source_node_tag)
        if source is None:
            raise ValueError(
                f"Source node {source_node_tag} does not exist."
            )
        tag = self.model.next_node_tag()
        node = self.model.add_node(tag, *source.xyz)
        node.fixity = (1,) * self.model.ndf
        return tag

    def connections_using_material(self, material_tag: int) -> list[int]:
        material_tag = int(material_tag)
        return sorted(
            connection.tag
            for connection in self.connections.values()
            if material_tag in connection.materials_by_dof.values()
        )

    def prune_connections(self) -> list[int]:
        removed: list[int] = []
        existing_nodes = set(self.model.nodes)
        for tag, connection in list(self.connections.items()):
            if (
                connection.node_i not in existing_nodes
                or connection.node_j not in existing_nodes
            ):
                self.remove_connection(tag, cleanup_ground=True)
                removed.append(tag)
        return sorted(removed)

    def next_time_series_tag(self) -> int:
        return max(self.time_series, default=0) + 1

    def add_time_series(self, series: TimeSeriesData) -> None:
        if series.tag in self.time_series:
            raise ValueError(f"Time series tag {series.tag} already exists.")
        self.time_series[series.tag] = series

    def update_time_series(self, original_tag: int, series: TimeSeriesData) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.time_series:
            raise ValueError(f"Time series tag {original_tag} does not exist.")
        if series.tag != original_tag and series.tag in self.time_series:
            raise ValueError(f"Time series tag {series.tag} already exists.")
        self.time_series.pop(original_tag)
        self.time_series[series.tag] = series
        if series.tag != original_tag:
            for pattern in self.load_patterns.values():
                if pattern.time_series_tag == original_tag:
                    pattern.time_series_tag = series.tag

    def remove_time_series(self, tag: int) -> None:
        tag = int(tag)
        used_by = sorted(
            pattern.tag
            for pattern in self.load_patterns.values()
            if pattern.time_series_tag == tag
        )
        if used_by:
            raise ValueError(
                "Time series is used by load pattern(s): "
                + ", ".join(map(str, used_by))
            )
        self.time_series.pop(tag, None)

    def next_load_pattern_tag(self) -> int:
        return max(self.load_patterns, default=0) + 1

    def _validate_load_pattern(self, pattern: LoadPatternData) -> None:
        if pattern.time_series_tag not in self.time_series:
            raise ValueError(
                f"Load pattern references missing time series "
                f"{pattern.time_series_tag}."
            )

    def add_load_pattern(self, pattern: LoadPatternData) -> None:
        if pattern.tag in self.load_patterns:
            raise ValueError(f"Load pattern tag {pattern.tag} already exists.")
        self._validate_load_pattern(pattern)
        self.load_patterns[pattern.tag] = pattern

    def update_load_pattern(
        self,
        original_tag: int,
        pattern: LoadPatternData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.load_patterns:
            raise ValueError(f"Load pattern tag {original_tag} does not exist.")
        if pattern.tag != original_tag and pattern.tag in self.load_patterns:
            raise ValueError(f"Load pattern tag {pattern.tag} already exists.")
        self._validate_load_pattern(pattern)
        if pattern.pattern_type != "Plain":
            dependent_nodal = [
                load.tag
                for load in self.nodal_loads.values()
                if load.pattern_tag == original_tag
            ]
            dependent_element = [
                load.tag
                for load in self.element_loads.values()
                if load.pattern_tag == original_tag
            ]
            dependent_displacement = [
                displacement.tag
                for displacement in self.prescribed_displacements.values()
                if displacement.pattern_tag == original_tag
            ]
            if (
                dependent_nodal
                or dependent_element
                or dependent_displacement
            ):
                raise ValueError(
                    "A Plain pattern containing nodal loads, beam loads, "
                    "or prescribed displacements cannot be changed to "
                    "UniformExcitation."
                )
        self.load_patterns.pop(original_tag)
        self.load_patterns[pattern.tag] = pattern
        if pattern.tag != original_tag:
            for source in self.mass_sources.values():
                if original_tag in source.load_factors:
                    factor = source.load_factors.pop(original_tag)
                    source.load_factors[pattern.tag] = factor
            for load in self.nodal_loads.values():
                if load.pattern_tag == original_tag:
                    load.pattern_tag = pattern.tag
            for load in self.element_loads.values():
                if load.pattern_tag == original_tag:
                    load.pattern_tag = pattern.tag
            for displacement in self.prescribed_displacements.values():
                if displacement.pattern_tag == original_tag:
                    displacement.pattern_tag = pattern.tag

    def remove_load_pattern(self, tag: int) -> None:
        tag = int(tag)
        self.load_patterns.pop(tag, None)
        for load_tag, load in list(self.nodal_loads.items()):
            if load.pattern_tag == tag:
                self.nodal_loads.pop(load_tag)
        for load_tag, load in list(self.element_loads.items()):
            if load.pattern_tag == tag:
                self.element_loads.pop(load_tag)
        for displacement_tag, displacement in list(
            self.prescribed_displacements.items()
        ):
            if displacement.pattern_tag == tag:
                self.prescribed_displacements.pop(displacement_tag)
        for source in self.mass_sources.values():
            source.load_factors.pop(tag, None)

    def next_mass_source_tag(self) -> int:
        return max(self.mass_sources, default=0) + 1

    def _validate_mass_source(self, source: MassSourceData) -> None:
        missing = sorted(
            tag
            for tag in source.load_factors
            if tag not in self.load_patterns
        )
        if missing:
            raise ValueError(
                "Mass source references missing load pattern tag(s): "
                + ", ".join(map(str, missing))
            )
        invalid = sorted(
            tag
            for tag in source.load_factors
            if self.load_patterns[tag].pattern_type != "Plain"
        )
        if invalid:
            raise ValueError(
                "Mass source can only reference Plain load patterns: "
                + ", ".join(map(str, invalid))
            )

    def add_mass_source(self, source: MassSourceData) -> None:
        if source.tag in self.mass_sources:
            raise ValueError(
                f"Mass source tag {source.tag} already exists."
            )
        self._validate_mass_source(source)
        self.mass_sources[source.tag] = source

    def update_mass_source(
        self,
        original_tag: int,
        source: MassSourceData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.mass_sources:
            raise ValueError(
                f"Mass source tag {original_tag} does not exist."
            )
        if source.tag != original_tag and source.tag in self.mass_sources:
            raise ValueError(
                f"Mass source tag {source.tag} already exists."
            )
        self._validate_mass_source(source)
        self.mass_sources.pop(original_tag)
        self.mass_sources[source.tag] = source

    def remove_mass_source(self, tag: int) -> None:
        self.mass_sources.pop(int(tag), None)

    def next_nodal_load_tag(self) -> int:
        return max(self.nodal_loads, default=0) + 1

    def _validate_nodal_load(self, load: NodalLoadData) -> None:
        if load.node_tag not in self.model.nodes:
            raise ValueError(
                f"Nodal load references missing node {load.node_tag}."
            )
        pattern = self.load_patterns.get(load.pattern_tag)
        if pattern is None:
            raise ValueError(
                f"Nodal load references missing pattern {load.pattern_tag}."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Nodal loads can only be assigned to Plain load patterns."
            )

    def add_nodal_load(self, load: NodalLoadData) -> None:
        if load.tag in self.nodal_loads:
            raise ValueError(f"Nodal load tag {load.tag} already exists.")
        self._validate_nodal_load(load)
        self.nodal_loads[load.tag] = load

    def update_nodal_load(self, original_tag: int, load: NodalLoadData) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.nodal_loads:
            raise ValueError(f"Nodal load tag {original_tag} does not exist.")
        if load.tag != original_tag and load.tag in self.nodal_loads:
            raise ValueError(f"Nodal load tag {load.tag} already exists.")
        self._validate_nodal_load(load)
        self.nodal_loads.pop(original_tag)
        self.nodal_loads[load.tag] = load

    def remove_nodal_load(self, tag: int) -> None:
        self.nodal_loads.pop(int(tag), None)

    def prune_nodal_loads(self) -> list[int]:
        removed: list[int] = []
        existing_nodes = set(self.model.nodes)
        existing_patterns = set(self.load_patterns)
        for tag, load in list(self.nodal_loads.items()):
            if (
                load.node_tag not in existing_nodes
                or load.pattern_tag not in existing_patterns
            ):
                self.nodal_loads.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def next_prescribed_displacement_tag(self) -> int:
        return max(self.prescribed_displacements, default=0) + 1

    def _validate_prescribed_displacement(
        self,
        displacement: PrescribedDisplacementData,
        *,
        original_tag: int | None = None,
    ) -> None:
        node = self.model.nodes.get(displacement.node_tag)
        if node is None:
            raise ValueError(
                "Prescribed displacement references missing node "
                f"{displacement.node_tag}."
            )
        pattern = self.load_patterns.get(displacement.pattern_tag)
        if pattern is None:
            raise ValueError(
                "Prescribed displacement references missing pattern "
                f"{displacement.pattern_tag}."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Prescribed displacements can only be assigned to Plain "
                "load patterns."
            )
        if displacement.dof > int(self.model.ndf):
            raise ValueError(
                f"DOF {displacement.dof} is not available for an "
                f"ndf={self.model.ndf} model."
            )
        if (
            displacement.dof <= len(node.fixity)
            and bool(node.fixity[displacement.dof - 1])
        ):
            raise ValueError(
                "Cannot prescribe a displacement on a DOF that is already "
                "restrained by a support."
            )
        for tag, existing in self.prescribed_displacements.items():
            if original_tag is not None and int(tag) == int(original_tag):
                continue
            if (
                existing.node_tag == displacement.node_tag
                and existing.dof == displacement.dof
            ):
                raise ValueError(
                    "Node "
                    f"{displacement.node_tag} DOF {displacement.dof} already "
                    "has a prescribed displacement."
                )

    def add_prescribed_displacement(
        self,
        displacement: PrescribedDisplacementData,
    ) -> None:
        if displacement.tag in self.prescribed_displacements:
            raise ValueError(
                "Prescribed displacement tag "
                f"{displacement.tag} already exists."
            )
        self._validate_prescribed_displacement(displacement)
        self.prescribed_displacements[displacement.tag] = displacement

    def update_prescribed_displacement(
        self,
        original_tag: int,
        displacement: PrescribedDisplacementData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.prescribed_displacements:
            raise ValueError(
                "Prescribed displacement tag "
                f"{original_tag} does not exist."
            )
        if (
            displacement.tag != original_tag
            and displacement.tag in self.prescribed_displacements
        ):
            raise ValueError(
                "Prescribed displacement tag "
                f"{displacement.tag} already exists."
            )
        self._validate_prescribed_displacement(
            displacement,
            original_tag=original_tag,
        )
        self.prescribed_displacements.pop(original_tag)
        self.prescribed_displacements[displacement.tag] = displacement

    def remove_prescribed_displacement(self, tag: int) -> None:
        self.prescribed_displacements.pop(int(tag), None)

    def prune_prescribed_displacements(self) -> list[int]:
        removed: list[int] = []
        existing_nodes = set(self.model.nodes)
        existing_patterns = set(self.load_patterns)
        for tag, displacement in list(
            self.prescribed_displacements.items()
        ):
            if (
                displacement.node_tag not in existing_nodes
                or displacement.pattern_tag not in existing_patterns
            ):
                self.prescribed_displacements.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def next_element_load_tag(self) -> int:
        return max(self.element_loads, default=0) + 1

    def _validate_element_load(self, load: ElementLoadData) -> None:
        element = self.model.elements.get(load.element_tag)
        if element is None:
            raise ValueError(
                f"Element load references missing element {load.element_tag}."
            )
        pattern = self.load_patterns.get(load.pattern_tag)
        if pattern is None:
            raise ValueError(
                f"Element load references missing pattern {load.pattern_tag}."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Element loads can only be assigned to Plain load patterns."
            )
        if element.element_type not in {
            "elasticBeamColumn",
            "forceBeamColumn",
            "dispBeamColumn",
        }:
            raise ValueError(
                "Beam element loads require a beam-column element."
            )

    def add_element_load(self, load: ElementLoadData) -> None:
        if load.tag in self.element_loads:
            raise ValueError(
                f"Element load tag {load.tag} already exists."
            )
        self._validate_element_load(load)
        self.element_loads[load.tag] = load

    def update_element_load(
        self,
        original_tag: int,
        load: ElementLoadData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.element_loads:
            raise ValueError(
                f"Element load tag {original_tag} does not exist."
            )
        if load.tag != original_tag and load.tag in self.element_loads:
            raise ValueError(
                f"Element load tag {load.tag} already exists."
            )
        self._validate_element_load(load)
        self.element_loads.pop(original_tag)
        self.element_loads[load.tag] = load

    def remove_element_load(self, tag: int) -> None:
        self.element_loads.pop(int(tag), None)

    def prune_element_loads(self) -> list[int]:
        removed: list[int] = []
        existing_elements = set(self.model.elements)
        existing_patterns = set(self.load_patterns)
        for tag, load in list(self.element_loads.items()):
            if (
                load.element_tag not in existing_elements
                or load.pattern_tag not in existing_patterns
            ):
                self.element_loads.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def next_recorder_tag(self) -> int:
        return max(self.recorders, default=0) + 1

    def _validate_recorder(self, recorder: RecorderData) -> None:
        if recorder.recorder_type == "Node":
            missing = [tag for tag in recorder.target_tags if tag not in self.model.nodes]
            if missing:
                raise ValueError(
                    "Recorder references missing node tag(s): "
                    + ", ".join(map(str, missing))
                )
            return
        valid_elements = set(self.model.elements) | set(self.connections)
        missing = [tag for tag in recorder.target_tags if tag not in valid_elements]
        if missing:
            raise ValueError(
                "Recorder references missing element tag(s): "
                + ", ".join(map(str, missing))
            )
        if recorder.recorder_type in {"Section", "Fiber"}:
            incompatible = [
                tag
                for tag in recorder.target_tags
                if tag not in self.model.elements
                or self.model.elements[tag].element_type
                not in {"forceBeamColumn", "dispBeamColumn"}
            ]
            if incompatible:
                raise ValueError(
                    "Section/Fiber recorders require forceBeamColumn or "
                    "dispBeamColumn element tag(s): "
                    + ", ".join(map(str, incompatible))
                )
            too_short = [
                tag
                for tag in recorder.target_tags
                if self.model.elements[tag].integration_points
                < recorder.section_number
            ]
            if too_short:
                raise ValueError(
                    f"Recorder section {recorder.section_number} exceeds "
                    "the integration-point count for element tag(s): "
                    + ", ".join(map(str, too_short))
                )

    def add_recorder(self, recorder: RecorderData) -> None:
        if recorder.tag in self.recorders:
            raise ValueError(f"Recorder tag {recorder.tag} already exists.")
        self._validate_recorder(recorder)
        self.recorders[recorder.tag] = recorder

    def update_recorder(self, original_tag: int, recorder: RecorderData) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.recorders:
            raise ValueError(f"Recorder tag {original_tag} does not exist.")
        if recorder.tag != original_tag and recorder.tag in self.recorders:
            raise ValueError(f"Recorder tag {recorder.tag} already exists.")
        self._validate_recorder(recorder)
        self.recorders.pop(original_tag)
        self.recorders[recorder.tag] = recorder

    def remove_recorder(self, tag: int) -> None:
        self.recorders.pop(int(tag), None)

    def prune_recorders(self) -> list[int]:
        removed: list[int] = []
        valid_nodes = set(self.model.nodes)
        valid_elements = set(self.model.elements) | set(self.connections)
        for tag, recorder in list(self.recorders.items()):
            valid = valid_nodes if recorder.recorder_type == "Node" else valid_elements
            recorder.target_tags = [item for item in recorder.target_tags if item in valid]
            if not recorder.target_tags:
                self.recorders.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def next_analysis_tag(self) -> int:
        return max(self.analyses, default=0) + 1

    def add_analysis(self, analysis: AnalysisSettingsData) -> None:
        if analysis.tag in self.analyses:
            raise ValueError(f"Analysis tag {analysis.tag} already exists.")
        if analysis.analysis_type in {"Pushover", "Cyclic"} and analysis.control_node not in self.model.nodes:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} does not exist."
            )
        self.analyses[analysis.tag]=analysis
        if self.active_analysis_tag is None:
            self.active_analysis_tag=analysis.tag

    def update_analysis(self, original_tag:int, analysis:AnalysisSettingsData) -> None:
        original_tag=int(original_tag)
        if original_tag not in self.analyses: raise ValueError(f"Analysis tag {original_tag} does not exist.")
        if analysis.tag!=original_tag and analysis.tag in self.analyses: raise ValueError(f"Analysis tag {analysis.tag} already exists.")
        if analysis.analysis_type in {"Pushover", "Cyclic"} and analysis.control_node not in self.model.nodes:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} does not exist."
            )
        self.analyses.pop(original_tag); self.analyses[analysis.tag]=analysis
        if analysis.tag != original_tag:
            for result in self.solution_results.values():
                if result.analysis_tag == original_tag:
                    result.analysis_tag = analysis.tag
        if self.active_analysis_tag==original_tag: self.active_analysis_tag=analysis.tag

    def remove_analysis(self, tag:int) -> None:
        tag=int(tag); self.analyses.pop(tag,None)
        for result_tag, result in list(self.solution_results.items()):
            if result.analysis_tag == tag:
                self.solution_results.pop(result_tag)
        if self.active_analysis_tag==tag:
            self.active_analysis_tag=min(self.analyses,default=None)

    def set_active_analysis(self, tag:int) -> None:
        tag=int(tag)
        if tag not in self.analyses: raise ValueError(f"Analysis tag {tag} does not exist.")
        self.active_analysis_tag=tag

    def next_solution_result_tag(self) -> int:
        return max(self.solution_results, default=0) + 1

    def _validate_solution_result(self, result: SolutionResultData) -> None:
        if result.analysis_tag not in self.analyses:
            raise ValueError(
                f"Solution result references missing analysis "
                f"{result.analysis_tag}."
            )
        missing_nodes = [
            tag for tag in result.node_scope
            if tag not in self.model.nodes
        ]
        if missing_nodes:
            raise ValueError(
                "Solution result references missing node tag(s): "
                + ", ".join(map(str, missing_nodes))
            )
        valid_elements = set(self.model.elements) | set(self.connections)
        missing_elements = [
            tag for tag in result.element_scope
            if tag not in valid_elements
        ]
        if missing_elements:
            raise ValueError(
                "Solution result references missing element tag(s): "
                + ", ".join(map(str, missing_elements))
            )

    def add_solution_result(self, result: SolutionResultData) -> None:
        if result.tag in self.solution_results:
            raise ValueError(
                f"Solution result tag {result.tag} already exists."
            )
        self._validate_solution_result(result)
        self.solution_results[result.tag] = result

    def update_solution_result(
        self,
        original_tag: int,
        result: SolutionResultData,
    ) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.solution_results:
            raise ValueError(
                f"Solution result tag {original_tag} does not exist."
            )
        if (
            result.tag != original_tag
            and result.tag in self.solution_results
        ):
            raise ValueError(
                f"Solution result tag {result.tag} already exists."
            )
        self._validate_solution_result(result)
        self.solution_results.pop(original_tag)
        self.solution_results[result.tag] = result

    def remove_solution_result(self, tag: int) -> None:
        self.solution_results.pop(int(tag), None)

    def solution_results_for_analysis(
        self,
        analysis_tag: int,
    ) -> list[SolutionResultData]:
        target = int(analysis_tag)
        return [
            self.solution_results[tag]
            for tag in sorted(self.solution_results)
            if self.solution_results[tag].analysis_tag == target
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": PROJECT_FORMAT,
            "version": PROJECT_FORMAT_VERSION,
            "name": self.name,
            "units": dict(self.units),
            "model": self.model.to_dict(),
            "selection_sets": [
                self.selection_sets[name].to_dict()
                for name in sorted(self.selection_sets)
            ],
            "materials": [
                self.materials[tag].to_dict()
                for tag in sorted(self.materials)
            ],
            "sections": [
                self.sections[tag].to_dict()
                for tag in sorted(self.sections)
            ],
            "transformations": [
                self.transformations[tag].to_dict()
                for tag in sorted(self.transformations)
            ],
            "constraints": [
                self.constraints[tag].to_dict()
                for tag in sorted(self.constraints)
            ],
            "connections": [
                self.connections[tag].to_dict()
                for tag in sorted(self.connections)
            ],
            "time_series": [
                self.time_series[tag].to_dict()
                for tag in sorted(self.time_series)
            ],
            "load_patterns": [
                self.load_patterns[tag].to_dict()
                for tag in sorted(self.load_patterns)
            ],
            "nodal_loads": [
                self.nodal_loads[tag].to_dict()
                for tag in sorted(self.nodal_loads)
            ],
            "prescribed_displacements": [
                self.prescribed_displacements[tag].to_dict()
                for tag in sorted(self.prescribed_displacements)
            ],
            "element_loads": [
                self.element_loads[tag].to_dict()
                for tag in sorted(self.element_loads)
            ],
            "mass_sources": [
                self.mass_sources[tag].to_dict()
                for tag in sorted(self.mass_sources)
            ],
            "analyses": [
                self.analyses[tag].to_dict()
                for tag in sorted(self.analyses)
            ],
            "recorders": [
                self.recorders[tag].to_dict()
                for tag in sorted(self.recorders)
            ],
            "solution_results": [
                self.solution_results[tag].to_dict()
                for tag in sorted(self.solution_results)
            ],
            "active_analysis_tag": self.active_analysis_tag,
        }

    @staticmethod
    def _load_materials(raw: Any) -> dict[int, MaterialData]:
        materials: dict[int, MaterialData] = {}

        if isinstance(raw, list):
            for item in raw:
                material = MaterialData.from_dict(dict(item))
                if material.tag in materials:
                    raise ValueError(f"Duplicate material tag {material.tag}.")
                materials[material.tag] = material
            return materials

        # Backward compatibility with v1 placeholder dictionaries.
        if isinstance(raw, dict):
            for raw_tag, raw_data in raw.items():
                if not isinstance(raw_data, dict):
                    continue
                data = dict(raw_data)
                if "tag" not in data:
                    try:
                        data["tag"] = int(raw_tag)
                    except (TypeError, ValueError):
                        continue
                data.setdefault("name", f"Material {data['tag']}")
                data.setdefault(
                    "material_type",
                    data.get("type", "Elastic"),
                )
                if "parameters" not in data:
                    material_type = str(data["material_type"])
                    order = MATERIAL_PARAMETER_ORDER.get(material_type, ())
                    data["parameters"] = {
                        key: data[key]
                        for key in order
                        if key in data
                    }
                material = MaterialData.from_dict(data)
                materials[material.tag] = material

        return materials

    @staticmethod
    def _load_sections(raw: Any) -> dict[int, SectionData]:
        sections: dict[int, SectionData] = {}

        if isinstance(raw, list):
            for item in raw:
                section = SectionData.from_dict(dict(item))
                if section.tag in sections:
                    raise ValueError(f"Duplicate section tag {section.tag}.")
                sections[section.tag] = section
            return sections

        if isinstance(raw, dict):
            for raw_tag, raw_data in raw.items():
                if not isinstance(raw_data, dict):
                    continue
                data = dict(raw_data)
                if "tag" not in data:
                    try:
                        data["tag"] = int(raw_tag)
                    except (TypeError, ValueError):
                        continue
                data.setdefault("name", f"Section {data['tag']}")
                data.setdefault(
                    "section_type",
                    data.get("type", "Elastic"),
                )
                if "parameters" not in data:
                    section_type = str(data["section_type"])
                    order = SECTION_PARAMETER_ORDER.get(section_type, ())
                    data["parameters"] = {
                        key: data[key]
                        for key in order
                        if key in data
                    }
                section = SectionData.from_dict(data)
                sections[section.tag] = section

        return sections

    @staticmethod
    def _load_transformations(raw: Any) -> dict[int, TransformationData]:
        transformations: dict[int, TransformationData] = {}

        if isinstance(raw, list):
            for item in raw:
                transformation = TransformationData.from_dict(dict(item))
                if transformation.tag in transformations:
                    raise ValueError(
                        f"Duplicate transformation tag {transformation.tag}."
                    )
                transformations[transformation.tag] = transformation
            return transformations

        if isinstance(raw, dict):
            for raw_tag, raw_data in raw.items():
                if not isinstance(raw_data, dict):
                    continue
                data = dict(raw_data)
                if "tag" not in data:
                    try:
                        data["tag"] = int(raw_tag)
                    except (TypeError, ValueError):
                        continue
                data.setdefault(
                    "name",
                    f"Transformation {data['tag']}",
                )
                data.setdefault(
                    "transformation_type",
                    data.get("type", "Linear"),
                )
                data.setdefault("vecxz", [0.0, 0.0, 1.0])
                transformation = TransformationData.from_dict(data)
                transformations[transformation.tag] = transformation

        return transformations

    @staticmethod
    def _load_constraints(raw: Any) -> dict[int, ConstraintData]:
        constraints: dict[int, ConstraintData] = {}
        if not isinstance(raw, list):
            return constraints
        for item in raw:
            constraint = ConstraintData.from_dict(dict(item))
            if constraint.tag in constraints:
                raise ValueError(
                    f"Duplicate constraint tag {constraint.tag}."
                )
            constraints[constraint.tag] = constraint
        return constraints

    @staticmethod
    def _load_connections(raw: Any) -> dict[int, ConnectionData]:
        connections: dict[int, ConnectionData] = {}
        if not isinstance(raw, list):
            return connections
        for item in raw:
            connection = ConnectionData.from_dict(dict(item))
            if connection.tag in connections:
                raise ValueError(
                    f"Duplicate connection tag {connection.tag}."
                )
            connections[connection.tag] = connection
        return connections

    @staticmethod
    def _load_time_series(raw: Any) -> dict[int, TimeSeriesData]:
        result: dict[int, TimeSeriesData] = {}
        if isinstance(raw, list):
            for item in raw:
                series = TimeSeriesData.from_dict(dict(item))
                result[series.tag] = series
        return result

    @staticmethod
    def _load_patterns(raw: Any) -> dict[int, LoadPatternData]:
        result: dict[int, LoadPatternData] = {}
        if isinstance(raw, list):
            for item in raw:
                pattern = LoadPatternData.from_dict(dict(item))
                result[pattern.tag] = pattern
        return result

    @staticmethod
    def _load_nodal_loads(raw: Any) -> dict[int, NodalLoadData]:
        result: dict[int, NodalLoadData] = {}
        if isinstance(raw, list):
            for item in raw:
                load = NodalLoadData.from_dict(dict(item))
                result[load.tag] = load
        return result

    @staticmethod
    def _load_prescribed_displacements(
        raw: Any,
    ) -> dict[int, PrescribedDisplacementData]:
        result: dict[int, PrescribedDisplacementData] = {}
        if isinstance(raw, list):
            for item in raw:
                displacement = PrescribedDisplacementData.from_dict(
                    dict(item)
                )
                result[displacement.tag] = displacement
        return result

    @staticmethod
    def _load_element_loads(raw: Any) -> dict[int, ElementLoadData]:
        result: dict[int, ElementLoadData] = {}
        if isinstance(raw, list):
            for item in raw:
                load = ElementLoadData.from_dict(dict(item))
                result[load.tag] = load
        return result

    @staticmethod
    def _load_mass_sources(raw: Any) -> dict[int, MassSourceData]:
        result: dict[int, MassSourceData] = {}
        if isinstance(raw, list):
            for item in raw:
                source = MassSourceData.from_dict(dict(item))
                if source.tag in result:
                    raise ValueError(
                        f"Duplicate mass source tag {source.tag}."
                    )
                result[source.tag] = source
        return result

    @staticmethod
    def _load_analyses(raw: Any) -> dict[int, AnalysisSettingsData]:
        result: dict[int, AnalysisSettingsData] = {}
        if isinstance(raw,list):
            for item in raw:
                analysis=AnalysisSettingsData.from_dict(dict(item))
                result[analysis.tag]=analysis
        return result

    @staticmethod
    def _load_solution_results(
        raw: Any,
    ) -> dict[int, SolutionResultData]:
        result: dict[int, SolutionResultData] = {}
        if isinstance(raw, list):
            for item in raw:
                solution_result = SolutionResultData.from_dict(dict(item))
                if solution_result.tag in result:
                    raise ValueError(
                        f"Duplicate solution result tag "
                        f"{solution_result.tag}."
                    )
                result[solution_result.tag] = solution_result
        return result

    @staticmethod
    def _load_recorders(raw: Any) -> dict[int, RecorderData]:
        result: dict[int, RecorderData] = {}
        if isinstance(raw, list):
            for item in raw:
                recorder = RecorderData.from_dict(dict(item))
                if recorder.tag in result:
                    raise ValueError(f"Duplicate recorder tag {recorder.tag}.")
                result[recorder.tag] = recorder
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectDatabase":
        project_format = data.get("format")
        if project_format != PROJECT_FORMAT:
            raise ValueError(
                f"Not an OpenSeesPy Studio project: format={project_format!r}"
            )

        version = int(data.get("version", 0))
        if version > PROJECT_FORMAT_VERSION:
            raise ValueError(
                f"Project version {version} is newer than supported "
                f"version {PROJECT_FORMAT_VERSION}."
            )
        if version < 1:
            raise ValueError(f"Unsupported project version: {version}")

        selection_sets = {}
        for item in data.get("selection_sets", []):
            selection_set = SelectionSetData.from_dict(item)
            selection_sets[selection_set.name] = selection_set

        return cls(
            name=str(data.get("name", "Untitled")),
            model=StructuralModel.from_dict(data.get("model", {})),
            selection_sets=selection_sets,
            materials=cls._load_materials(data.get("materials", [])),
            sections=cls._load_sections(data.get("sections", [])),
            transformations=cls._load_transformations(data.get("transformations", [])),
            constraints=cls._load_constraints(data.get("constraints", [])),
            connections=cls._load_connections(data.get("connections", [])),
            time_series=cls._load_time_series(data.get("time_series", [])),
            load_patterns=cls._load_patterns(data.get("load_patterns", [])),
            nodal_loads=cls._load_nodal_loads(data.get("nodal_loads", [])),
            prescribed_displacements=cls._load_prescribed_displacements(
                data.get("prescribed_displacements", [])
            ),
            element_loads=cls._load_element_loads(
                data.get("element_loads", [])
            ),
            mass_sources=cls._load_mass_sources(
                data.get("mass_sources", [])
            ),
            analyses=cls._load_analyses(data.get("analyses", [])),
            recorders=cls._load_recorders(data.get("recorders", [])),
            solution_results=cls._load_solution_results(
                data.get("solution_results", [])
            ),
            active_analysis_tag=(
                int(data["active_analysis_tag"])
                if data.get("active_analysis_tag") is not None
                else None
            ),
            units=normalize_project_units(
                {
                    str(key): str(value)
                    for key, value in data.get(
                        "units",
                        DEFAULT_PROJECT_UNITS,
                    ).items()
                }
            ),
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProjectDatabase":
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Project root must be a JSON object.")
        return cls.from_dict(data)
