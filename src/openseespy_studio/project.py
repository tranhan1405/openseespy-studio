from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import (
    CONTINUUM_QUAD_ELEMENT_TYPES,
    FRAME_ELEMENT_TYPES,
    SHELL_ELEMENT_TYPES,
    SOLID_ELEMENT_TYPES,
    WALL_MACRO_3D_ELEMENT_TYPES,
    WALL_MACRO_ELEMENT_TYPES,
    StructuralModel,
    Vec3,
)
from .result_catalog import result_choices_for_analysis
from .section_response import validate_section_response_request
from .units import DEFAULT_PROJECT_UNITS, normalize_project_units


def _strict_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{label} must be a boolean.")


def _strict_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{label} must be an integer.")
    return int(numeric)


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    return value


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


PROJECT_FORMAT = "openseespy-studio"
PROJECT_FORMAT_VERSION = 48

MATERIAL_CATEGORIES: dict[str, str] = {
    "Elastic": "General",
    "Steel01": "Steel",
    "Steel02": "Steel",
    "RambergOsgoodSteel": "Steel",
    "Hardening": "Steel",
    "ElasticPP": "Steel",
    "ElasticBilin": "Steel",
    "ReinforcingSteel": "Steel",
    "Concrete01": "Concrete",
    "Concrete02": "Concrete",
    "Concrete04": "Concrete",
    "ConcreteCM": "Concrete",
    "Hysteretic": "Hysteretic / Connection",
    "HystereticSmooth": "Hysteretic / Connection",
    "Pinching4": "Hysteretic / Connection",
    "Bond_SP01": "Bond / Interface",
    "ElasticPPGap": "Hysteretic / Connection",
    "FRPConfinedConcrete": "Concrete / FRP",
    "FRPConfinedConcrete02": "Concrete / FRP",
    "MinMax": "Wrapper / Composite",
    "Fatigue": "Wrapper / Composite",
    "Parallel": "Wrapper / Composite",
    "Series": "Wrapper / Composite",
}

MATERIAL_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "Elastic": ("E",),
    "Steel01": ("Fy", "E0", "b", "a1", "a2", "a3", "a4"),
    "Steel02": (
        "Fy", "E0", "b", "R0", "cR1", "cR2",
        "a1", "a2", "a3", "a4",
    ),
    "RambergOsgoodSteel": ("fy", "E0", "a", "n"),
    "Hardening": ("E", "sigmaY", "H_iso", "H_kin", "eta"),
    "ElasticPP": ("E", "epsyP", "epsyN", "eps0"),
    "ElasticBilin": ("EP1", "EP2", "epsP2", "EN1", "EN2", "epsN2"),
    "ReinforcingSteel": ("fy", "fu", "Es", "Esh", "eps_sh", "eps_ult"),
    "Concrete01": ("fpc", "epsc0", "fpcu", "epsU"),
    "Concrete02": ("fpc", "epsc0", "fpcu", "epsU", "lambda", "ft", "Ets"),
    "Concrete04": ("fc", "epsc", "epscu", "Ec", "fct", "et", "beta"),
    "ConcreteCM": (
        "fpcc", "epcc", "Ec", "rc", "xcrn",
        "ft", "et", "rt", "xcrp", "GapClose",
    ),
    "HystereticSmooth": ("ka", "kb", "fbar", "beta"),
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
    "FRPConfinedConcrete": (
        "fpc1", "fpc2", "epsc0", "D", "c", "Ej", "Sj", "tj",
        "eju", "S", "fyl", "fyh", "dlong", "dtrans", "Es",
        "nu0", "k", "useBuck",
    ),
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
    "RambergOsgoodSteel": {"fy": "stress", "E0": "stress"},
    "Hardening": {
        "E": "stress",
        "sigmaY": "stress",
        "H_iso": "stress",
        "H_kin": "stress",
        "eta": "stress",
    },
    "ElasticPP": {"E": "stress"},
    "ElasticBilin": {
        "EP1": "stress", "EP2": "stress",
        "EN1": "stress", "EN2": "stress",
    },
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
    "ConcreteCM": {
        "fpcc": "stress", "Ec": "stress", "ft": "stress",
    },
    "Hysteretic": {},
    "HystereticSmooth": {},
    "Pinching4": {},
    "Bond_SP01": {
        "Fy": "stress", "Fu": "stress", "Sy": "length", "Su": "length",
    },
    "ElasticPPGap": {},
    "FRPConfinedConcrete": {
        "fpc1": "stress", "fpc2": "stress",
        "D": "length", "c": "length", "Ej": "stress",
        "Sj": "length", "tj": "length", "S": "length",
        "fyl": "stress", "fyh": "stress",
        "dlong": "length", "dtrans": "length", "Es": "stress",
    },
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

PINCHING4_RESPONSE_KEYS = {
    "ePf1", "ePf2", "ePf3", "ePf4",
    "eNf1", "eNf2", "eNf3", "eNf4",
}
PINCHING4_DEFORMATION_KEYS = {
    "ePd1", "ePd2", "ePd3", "ePd4",
    "eNd1", "eNd2", "eNd3", "eNd4",
}
HYSTERETIC_RESPONSE_KEYS = {
    "s1p", "s2p", "s3p", "s1n", "s2n", "s3n",
}
HYSTERETIC_DEFORMATION_KEYS = {
    "e1p", "e2p", "e3p", "e1n", "e2n", "e3n",
}


def material_parameter_kind(
    material: "MaterialData",
    key: str,
) -> str:
    """Return the physical storage/display kind for one material parameter.

    Most OpenSees uniaxial materials have fixed semantics. Pinching4 is more
    general: its envelope may represent force-displacement, moment-rotation,
    or stress-strain. Verified library records declare that context explicitly
    in source metadata so values can remain unit-safe across project systems.
    Legacy/manual Pinching4 definitions without metadata remain raw for
    backward compatibility.
    """
    if material.material_type not in {"Pinching4", "Hysteretic"}:
        return MATERIAL_PARAMETER_KINDS.get(
            material.material_type,
            {},
        ).get(key, "raw")

    response_quantity = str(
        material.source.get("response_quantity", "")
    ).strip().lower()
    response_keys = (
        PINCHING4_RESPONSE_KEYS
        if material.material_type == "Pinching4"
        else HYSTERETIC_RESPONSE_KEYS
    )
    deformation_keys = (
        PINCHING4_DEFORMATION_KEYS
        if material.material_type == "Pinching4"
        else HYSTERETIC_DEFORMATION_KEYS
    )
    if key in response_keys:
        return {
            "force_displacement": "force",
            "moment_rotation": "moment",
            "stress_strain": "stress",
        }.get(response_quantity, "raw")
    if key in deformation_keys:
        return {
            "force_displacement": "length",
            "moment_rotation": "rotation",
            "stress_strain": "strain",
        }.get(response_quantity, "raw")
    return "raw"


MATERIAL_ENGINEERING_DEFAULTS: dict[str, dict[str, float]] = {
    name: {
        "poisson_ratio": 0.2 if "Concrete" in name else 0.3,
        "density": 2400.0 if "Concrete" in name else 7850.0 if name in {
            "Steel01", "Steel02", "RambergOsgoodSteel", "Hardening",
            "ElasticPP", "ElasticBilin", "ReinforcingSteel",
        } else 0.0,
    }
    for name in MATERIAL_PARAMETER_ORDER
}

MATERIAL_DEFAULTS: dict[str, dict[str, float]] = {
    "Elastic": {"E": 2.0e11},
    "Steel01": {"Fy": 3.55e8, "E0": 2.0e11, "b": 0.01, "a1": 0.0, "a2": 55.0, "a3": 0.0, "a4": 55.0},
    "Steel02": {
        "Fy": 3.55e8,
        "E0": 2.0e11,
        "b": 0.01,
        "R0": 20.0,
        "cR1": 0.925,
        "cR2": 0.15,
        "a1": 0.0,
        "a2": 1.0,
        "a3": 0.0,
        "a4": 1.0,
    },
    "RambergOsgoodSteel": {
        "fy": 6.0e8,
        "E0": 2.0e11,
        "a": 0.002,
        "n": 10.0,
    },
    "Hardening": {
        "E": 2.0e11,
        "sigmaY": 3.55e8,
        "H_iso": 0.0,
        "H_kin": 2.02e9,
        "eta": 0.0,
    },
    "ElasticPP": {
        "E": 2.0e11,
        "epsyP": 0.001775,
        "epsyN": -0.001775,
        "eps0": 0.0,
    },
    "ElasticBilin": {
        "EP1": 2.0e11,
        "EP2": 2.0e9,
        "epsP2": 0.001775,
        "EN1": 2.0e11,
        "EN2": 2.0e9,
        "epsN2": -0.001775,
    },
    "ReinforcingSteel": {"fy": 5.0e8, "fu": 6.5e8, "Es": 2.0e11, "Esh": 5.0e9, "eps_sh": 0.01, "eps_ult": 0.12},
    "Concrete01": {"fpc": -30.0e6, "epsc0": -0.002, "fpcu": -6.0e6, "epsU": -0.006},
    "Concrete02": {"fpc": -30.0e6, "epsc0": -0.002, "fpcu": -6.0e6, "epsU": -0.006, "lambda": 0.1, "ft": 3.0e6, "Ets": 2.0e8},
    "Concrete04": {"fc": -30.0e6, "epsc": -0.002, "epscu": -0.006, "Ec": 3.0e10, "fct": 3.0e6, "et": 0.0002, "beta": 0.1},
    "ConcreteCM": {
        "fpcc": -30.0e6, "epcc": -0.002, "Ec": 3.0e10,
        "rc": 7.0, "xcrn": 1.02, "ft": 3.0e6, "et": 0.0001,
        "rt": 1.2, "xcrp": 10000.0, "GapClose": 0.0,
    },
    "Hysteretic": {"s1p": 1.0, "e1p": 0.001, "s2p": 1.2, "e2p": 0.01, "s3p": 1.0, "e3p": 0.03, "s1n": -1.0, "e1n": -0.001, "s2n": -1.2, "e2n": -0.01, "s3n": -1.0, "e3n": -0.03, "pinchX": 0.5, "pinchY": 0.5, "damage1": 0.0, "damage2": 0.0, "beta": 0.0},
    "HystereticSmooth": {
        "ka": 1.0,
        "kb": 0.01,
        "fbar": 1.0,
        "beta": -1.0,
    },
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
    "FRPConfinedConcrete": {
        "fpc1": 27.5e6, "fpc2": 27.5e6, "epsc0": 0.002,
        "D": 0.400, "c": 0.035, "Ej": 266.0e9,
        "Sj": 0.0, "tj": 0.000222, "eju": 0.0163,
        "S": 0.150, "fyl": 374.0e6, "fyh": 363.0e6,
        "dlong": 0.016, "dtrans": 0.006, "Es": 200.0e9,
        "nu0": 0.2, "k": 0.8, "useBuck": 1.0,
    },
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
    source: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Material tag")
        self.name = str(self.name).strip() or f"Material {self.tag}"
        self.material_type = str(self.material_type)
        if not isinstance(self.source, dict):
            raise ValueError("Material source metadata must be an object.")
        self.source = deepcopy(self.source)
        if self.tag <= 0:
            raise ValueError("Material tag must be a positive integer.")
        if self.material_type not in MATERIAL_PARAMETER_ORDER:
            raise ValueError(f"Unsupported material type: {self.material_type}")

        defaults = MATERIAL_DEFAULTS[self.material_type]
        normalized: dict[str, float] = {}
        for key in MATERIAL_PARAMETER_ORDER[self.material_type]:
            normalized[key] = float(self.parameters.get(key, defaults[key]))
        self.parameters = normalized

        raw_base_material_tag = self.base_material_tag
        raw_material_tags = list(self.material_tags)
        self.factors = [float(value) for value in self.factors]

        if self.material_type in {"MinMax", "Fatigue"}:
            self.base_material_tag = (
                None
                if raw_base_material_tag is None
                else _strict_int(
                    raw_base_material_tag,
                    "Base material tag",
                )
            )
            if self.base_material_tag is None or self.base_material_tag <= 0:
                raise ValueError(
                    f"{self.material_type} requires a valid base material tag."
                )
            self.material_tags = []
            self.factors = []
        elif self.material_type in {"Parallel", "Series"}:
            self.base_material_tag = None
            self.material_tags = [
                _strict_int(tag, "Component material tag")
                for tag in raw_material_tags
            ]
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
        numeric_values = [
            *self.parameters.values(),
            *self.factors,
            self.poisson_ratio,
            self.density,
        ]
        if any(not math.isfinite(value) for value in numeric_values):
            raise ValueError("Material numeric values must be finite.")
        if not (-0.99 < self.poisson_ratio < 0.5):
            raise ValueError("Poisson ratio must be between -0.99 and 0.5.")
        if self.density < 0.0:
            raise ValueError("Material density cannot be negative.")

    def elastic_modulus(self) -> float:
        if self.material_type == "Elastic":
            return float(self.parameters["E"])
        if self.material_type in {"Steel01", "Steel02", "RambergOsgoodSteel"}:
            return float(self.parameters["E0"])
        if self.material_type in {"Hardening", "ElasticPP"}:
            return float(self.parameters["E"])
        if self.material_type == "ElasticBilin":
            return float(self.parameters["EP1"])
        if self.material_type == "ReinforcingSteel":
            return float(self.parameters["Es"])
        if self.material_type in {"Concrete01", "Concrete02"}:
            epsc0 = float(self.parameters["epsc0"])
            if abs(epsc0) <= 1.0e-16:
                raise ValueError(
                    f"Concrete02 material {self.tag} has zero epsc0."
                )
            return abs(2.0 * float(self.parameters["fpc"]) / epsc0)
        if self.material_type in {"Concrete04", "ConcreteCM"}:
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
            "source": deepcopy(self.source),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MaterialData":
        return cls(
            tag=data["tag"],
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
            base_material_tag=data.get("base_material_tag"),
            material_tags=list(data.get("material_tags", [])),
            factors=[
                float(value) for value in data.get("factors", [])
            ],
            source=deepcopy(dict(data.get("source", {}))),
        )


ND_MATERIAL_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "ElasticIsotropic": ("E", "nu", "rho"),
    "ElasticOrthotropic": (
        "Ex", "Ey", "Ez",
        "nu_xy", "nu_yz", "nu_zx",
        "Gxy", "Gyz", "Gzx",
        "rho",
    ),
    "J2Plasticity": (
        "K", "G", "sig0", "sigInf", "delta", "H",
    ),
    "DruckerPrager": (
        "K", "G", "sigmaY", "rho", "rhoBar",
        "Kinf", "Ko", "delta1", "delta2", "H",
        "theta", "density", "atmPressure",
    ),
    "PressureIndependMultiYield": (
        "nd", "rho", "refShearModul", "refBulkModul",
        "cohesi", "peakShearStra", "frictionAng", "refPress",
        "pressDependCoe", "noYieldSurf",
    ),
    "PressureDependMultiYield": (
        "nd", "rho", "refShearModul", "refBulkModul",
        "frictionAng", "peakShearStra", "refPress",
        "pressDependCoe", "PTAng", "contrac", "dilat1", "dilat2",
        "liquefac1", "liquefac2", "liquefac3", "noYieldSurf",
        "e", "cs1", "cs2", "cs3", "pa", "c",
    ),
    "ASDConcrete3D": (
        "E", "nu", "rho", "fc", "ft", "implex", "Kc", "cdf",
    ),
    "OrthotropicRAConcrete": (
        "conc", "ecr", "ec", "rho", "DamageCte1", "DamageCte2",
    ),
    "SmearedSteelDoubleLayer": (
        "mat1", "mat2", "ratio1", "ratio2", "orientation",
    ),
    "FSAM": (
        "rho", "sX", "sY", "conc", "rouX", "rouY", "nu", "alfadow",
    ),
}

ND_MATERIAL_PARAMETER_KINDS: dict[str, dict[str, str]] = {
    "ElasticIsotropic": {
        "E": "stress",
        "nu": "dimensionless",
        "rho": "density",
    },
    "ElasticOrthotropic": {
        "Ex": "stress",
        "Ey": "stress",
        "Ez": "stress",
        "nu_xy": "dimensionless",
        "nu_yz": "dimensionless",
        "nu_zx": "dimensionless",
        "Gxy": "stress",
        "Gyz": "stress",
        "Gzx": "stress",
        "rho": "density",
    },
    "J2Plasticity": {
        "K": "stress",
        "G": "stress",
        "sig0": "stress",
        "sigInf": "stress",
        "delta": "dimensionless",
        "H": "stress",
    },
    "DruckerPrager": {
        "K": "stress",
        "G": "stress",
        "sigmaY": "stress",
        "rho": "dimensionless",
        "rhoBar": "dimensionless",
        "Kinf": "stress",
        "Ko": "stress",
        "delta1": "dimensionless",
        "delta2": "dimensionless",
        "H": "stress",
        "theta": "dimensionless",
        "density": "density",
        "atmPressure": "stress",
    },
    "PressureIndependMultiYield": {
        "nd": "dimensionless",
        "rho": "density",
        "refShearModul": "stress",
        "refBulkModul": "stress",
        "cohesi": "stress",
        "peakShearStra": "dimensionless",
        "frictionAng": "dimensionless",
        "refPress": "stress",
        "pressDependCoe": "dimensionless",
        "noYieldSurf": "dimensionless",
    },
    "PressureDependMultiYield": {
        "nd": "dimensionless",
        "rho": "density",
        "refShearModul": "stress",
        "refBulkModul": "stress",
        "frictionAng": "dimensionless",
        "peakShearStra": "dimensionless",
        "refPress": "stress",
        "pressDependCoe": "dimensionless",
        "PTAng": "dimensionless",
        "contrac": "dimensionless",
        "dilat1": "dimensionless",
        "dilat2": "dimensionless",
        "liquefac1": "stress",
        "liquefac2": "dimensionless",
        "liquefac3": "dimensionless",
        "noYieldSurf": "dimensionless",
        "e": "dimensionless",
        "cs1": "dimensionless",
        "cs2": "dimensionless",
        "cs3": "dimensionless",
        "pa": "stress",
        "c": "stress",
    },
    "ASDConcrete3D": {
        "E": "stress",
        "nu": "dimensionless",
        "rho": "density",
        "fc": "stress",
        "ft": "stress",
        "implex": "dimensionless",
        "Kc": "dimensionless",
        "cdf": "dimensionless",
    },
    "OrthotropicRAConcrete": {
        "conc": "dimensionless",
        "ecr": "dimensionless",
        "ec": "dimensionless",
        "rho": "density",
        "DamageCte1": "dimensionless",
        "DamageCte2": "dimensionless",
    },
    "SmearedSteelDoubleLayer": {
        "mat1": "dimensionless",
        "mat2": "dimensionless",
        "ratio1": "dimensionless",
        "ratio2": "dimensionless",
        "orientation": "dimensionless",
    },
    "FSAM": {
        "rho": "density",
        "sX": "dimensionless",
        "sY": "dimensionless",
        "conc": "dimensionless",
        "rouX": "dimensionless",
        "rouY": "dimensionless",
        "nu": "dimensionless",
        "alfadow": "dimensionless",
    },
}

ND_MATERIAL_DEFAULTS: dict[str, dict[str, float]] = {
    "ElasticIsotropic": {
        "E": 2.0e11,
        "nu": 0.30,
        "rho": 0.0,
    },
    "ElasticOrthotropic": {
        "Ex": 2.0e11,
        "Ey": 2.0e11,
        "Ez": 2.0e11,
        "nu_xy": 0.30,
        "nu_yz": 0.30,
        "nu_zx": 0.30,
        "Gxy": 7.6923e10,
        "Gyz": 7.6923e10,
        "Gzx": 7.6923e10,
        "rho": 0.0,
    },
    "J2Plasticity": {
        "K": 1.6667e11,
        "G": 7.6923e10,
        "sig0": 2.50e8,
        "sigInf": 3.50e8,
        "delta": 16.0,
        "H": 1.0e9,
    },
    "DruckerPrager": {
        "K": 1.0e8,
        "G": 5.0e7,
        "sigmaY": 1.0e5,
        "rho": 0.10,
        "rhoBar": 0.10,
        "Kinf": 0.0,
        "Ko": 0.0,
        "delta1": 0.0,
        "delta2": 0.0,
        "H": 0.0,
        "theta": 1.0,
        "density": 0.0,
        "atmPressure": 101325.0,
    },
    "PressureIndependMultiYield": {
        "nd": 2.0,
        "rho": 1500.0,
        "refShearModul": 6.0e7,
        "refBulkModul": 3.0e8,
        "cohesi": 3.7e4,
        "peakShearStra": 0.10,
        "frictionAng": 0.0,
        "refPress": 1.0e5,
        "pressDependCoe": 0.0,
        "noYieldSurf": 20.0,
    },
    "PressureDependMultiYield": {
        "nd": 2.0,
        "rho": 1900.0,
        "refShearModul": 7.5e7,
        "refBulkModul": 2.0e8,
        "frictionAng": 33.0,
        "peakShearStra": 0.10,
        "refPress": 8.0e4,
        "pressDependCoe": 0.5,
        "PTAng": 27.0,
        "contrac": 0.07,
        "dilat1": 0.4,
        "dilat2": 2.0,
        "liquefac1": 1.0e4,
        "liquefac2": 0.01,
        "liquefac3": 1.0,
        "noYieldSurf": 20.0,
        "e": 0.6,
        "cs1": 0.9,
        "cs2": 0.02,
        "cs3": 0.7,
        "pa": 1.01e5,
        "c": 3.0e2,
    },
    "ASDConcrete3D": {
        "E": 3.0e10,
        "nu": 0.20,
        "rho": 2400.0,
        "fc": 3.0e7,
        "ft": 3.0e6,
        "implex": 0.0,
        "Kc": 2.0 / 3.0,
        "cdf": 0.0,
    },
    "OrthotropicRAConcrete": {
        "conc": 1.0,
        "ecr": 8.0e-5,
        "ec": -0.002,
        "rho": 0.0,
        "DamageCte1": 0.14,
        "DamageCte2": 0.6,
    },
    "SmearedSteelDoubleLayer": {
        "mat1": 1.0,
        "mat2": 2.0,
        "ratio1": 0.01,
        "ratio2": 0.01,
        "orientation": 0.0,
    },
    "FSAM": {
        "rho": 0.0,
        "sX": 1.0,
        "sY": 2.0,
        "conc": 3.0,
        "rouX": 0.0025,
        "rouY": 0.0025,
        "nu": 0.35,
        "alfadow": 0.005,
    },
}


def nd_material_parameter_kind(
    material_type: str,
    parameter: str,
) -> str:
    return ND_MATERIAL_PARAMETER_KINDS.get(
        str(material_type),
        {},
    ).get(str(parameter), "dimensionless")


ND_MATERIAL_FORMULATIONS: dict[str, tuple[str, ...]] = {
    "ElasticIsotropic": (
        "ThreeDimensional", "PlaneStrain", "Plane Stress",
        "AxiSymmetric", "PlateFiber",
    ),
    "ElasticOrthotropic": (
        "ThreeDimensional", "PlaneStrain", "Plane Stress",
        "AxiSymmetric", "BeamFiber", "PlateFiber",
    ),
    "J2Plasticity": (
        "ThreeDimensional", "PlaneStrain", "Plane Stress",
        "AxiSymmetric", "PlateFiber",
    ),
    "DruckerPrager": ("ThreeDimensional", "PlaneStrain"),
    "PressureIndependMultiYield": ("ThreeDimensional", "PlaneStrain"),
    "PressureDependMultiYield": ("ThreeDimensional", "PlaneStrain"),
    "ASDConcrete3D": ("ThreeDimensional",),
    "OrthotropicRAConcrete": ("Plane Stress",),
    "SmearedSteelDoubleLayer": ("Plane Stress",),
    "FSAM": ("Plane Stress",),
}


def nd_material_supported_formulations(
    material_type: str,
) -> tuple[str, ...]:
    return ND_MATERIAL_FORMULATIONS.get(str(material_type), ())


ND_MATERIAL_STAGE_UPDATE_TYPES = {
    "PressureIndependMultiYield",
    "PressureDependMultiYield",
}


def nd_material_requires_stage_update(material_type: str) -> bool:
    return str(material_type) in ND_MATERIAL_STAGE_UPDATE_TYPES


def nd_material_supports_plate_fiber(material_type: str) -> bool:
    return (
        "PlateFiber"
        in nd_material_supported_formulations(material_type)
    )


@dataclass
class NDMaterialData:
    """OpenSees nDMaterial definition kept separate from uniaxial materials."""

    tag: int
    name: str
    material_type: str
    parameters: dict[str, float] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "nDMaterial tag")
        self.name = str(self.name).strip() or f"nDMaterial {self.tag}"
        self.material_type = str(self.material_type)
        if self.tag <= 0:
            raise ValueError("nDMaterial tag must be a positive integer.")
        if self.material_type not in ND_MATERIAL_PARAMETER_ORDER:
            raise ValueError(
                f"Unsupported nDMaterial type: {self.material_type}"
            )
        defaults = ND_MATERIAL_DEFAULTS[self.material_type]
        self.parameters = {
            key: float(self.parameters.get(key, defaults[key]))
            for key in ND_MATERIAL_PARAMETER_ORDER[self.material_type]
        }
        if any(
            not math.isfinite(value)
            for value in self.parameters.values()
        ):
            raise ValueError("nDMaterial parameters must be finite.")
        if self.material_type == "ElasticIsotropic":
            if self.parameters["E"] <= 0.0:
                raise ValueError(
                    "ElasticIsotropic elastic modulus E must be positive."
                )
            if not -1.0 < self.parameters["nu"] < 0.5:
                raise ValueError(
                    "ElasticIsotropic Poisson ratio must satisfy "
                    "-1 < nu < 0.5."
                )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "ElasticIsotropic density rho cannot be negative."
                )
        elif self.material_type == "ElasticOrthotropic":
            for key in ("Ex", "Ey", "Ez", "Gxy", "Gyz", "Gzx"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(
                        f"ElasticOrthotropic {key} must be positive."
                    )
            for key in ("nu_xy", "nu_yz", "nu_zx"):
                if not -1.0 < self.parameters[key] < 1.0:
                    raise ValueError(
                        f"ElasticOrthotropic {key} must lie between -1 and 1."
                    )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "ElasticOrthotropic density rho cannot be negative."
                )
        elif self.material_type == "J2Plasticity":
            for key in ("K", "G"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(
                        f"J2Plasticity {key} must be positive."
                    )
            for key in ("sig0", "sigInf", "delta", "H"):
                if self.parameters[key] < 0.0:
                    raise ValueError(
                        f"J2Plasticity {key} cannot be negative."
                    )
        elif self.material_type == "DruckerPrager":
            for key in ("K", "G", "sigmaY", "atmPressure"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(
                        f"DruckerPrager {key} must be positive."
                    )
            for key in ("Kinf", "Ko", "delta1", "delta2", "H", "density"):
                if self.parameters[key] < 0.0:
                    raise ValueError(
                        f"DruckerPrager {key} cannot be negative."
                    )
            rho = self.parameters["rho"]
            rho_bar = self.parameters["rhoBar"]
            if rho < 0.0:
                raise ValueError("DruckerPrager rho cannot be negative.")
            if not 0.0 <= rho_bar <= rho:
                raise ValueError(
                    "DruckerPrager rhoBar must satisfy 0 <= rhoBar <= rho."
                )
            theta = self.parameters["theta"]
            if not 0.0 <= theta <= 1.0:
                raise ValueError(
                    "DruckerPrager theta must satisfy 0 <= theta <= 1."
                )
        elif self.material_type == "PressureIndependMultiYield":
            nd = self.parameters["nd"]
            if nd not in {2.0, 3.0}:
                raise ValueError(
                    "PressureIndependMultiYield nd must be 2 or 3."
                )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "PressureIndependMultiYield rho cannot be negative."
                )
            for key in ("refShearModul", "refBulkModul", "refPress"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(
                        f"PressureIndependMultiYield {key} must be positive."
                    )
            if self.parameters["cohesi"] < 0.0:
                raise ValueError(
                    "PressureIndependMultiYield cohesi cannot be negative."
                )
            if self.parameters["peakShearStra"] <= 0.0:
                raise ValueError(
                    "PressureIndependMultiYield peakShearStra must be positive."
                )
            friction = self.parameters["frictionAng"]
            if not 0.0 <= friction < 90.0:
                raise ValueError(
                    "PressureIndependMultiYield frictionAng must satisfy "
                    "0 <= frictionAng < 90 degrees."
                )
            if self.parameters["pressDependCoe"] < 0.0:
                raise ValueError(
                    "PressureIndependMultiYield pressDependCoe cannot be negative."
                )
            surfaces = self.parameters["noYieldSurf"]
            if not surfaces.is_integer() or not 1.0 <= surfaces < 40.0:
                raise ValueError(
                    "PressureIndependMultiYield noYieldSurf must be an "
                    "integer from 1 to 39. Custom negative surface counts "
                    "are not supported by SARE yet."
                )
        elif self.material_type == "PressureDependMultiYield":
            nd = self.parameters["nd"]
            if nd not in {2.0, 3.0}:
                raise ValueError(
                    "PressureDependMultiYield nd must be 2 or 3."
                )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "PressureDependMultiYield rho cannot be negative."
                )
            for key in ("refShearModul", "refBulkModul", "refPress", "pa"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(
                        f"PressureDependMultiYield {key} must be positive."
                    )
            if self.parameters["peakShearStra"] <= 0.0:
                raise ValueError(
                    "PressureDependMultiYield peakShearStra must be positive."
                )
            for key in ("frictionAng", "PTAng"):
                angle = self.parameters[key]
                if not 0.0 <= angle < 90.0:
                    raise ValueError(
                        f"PressureDependMultiYield {key} must satisfy "
                        f"0 <= {key} < 90 degrees."
                    )
            for key in (
                "pressDependCoe", "contrac", "dilat1", "dilat2",
                "liquefac1", "liquefac2", "liquefac3", "e",
                "cs1", "cs2", "cs3", "c",
            ):
                if self.parameters[key] < 0.0:
                    raise ValueError(
                        f"PressureDependMultiYield {key} cannot be negative."
                    )
            surfaces = self.parameters["noYieldSurf"]
            if not surfaces.is_integer() or not 1.0 <= surfaces < 40.0:
                raise ValueError(
                    "PressureDependMultiYield noYieldSurf must be an "
                    "integer from 1 to 39. Custom negative surface counts "
                    "are not supported by SARE yet."
                )
        elif self.material_type == "ASDConcrete3D":
            if self.parameters["E"] <= 0.0:
                raise ValueError(
                    "ASDConcrete3D elastic modulus E must be positive."
                )
            if not -1.0 < self.parameters["nu"] < 0.5:
                raise ValueError(
                    "ASDConcrete3D Poisson ratio must satisfy -1 < nu < 0.5."
                )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "ASDConcrete3D density rho cannot be negative."
                )
            if self.parameters["fc"] <= 0.0:
                raise ValueError(
                    "ASDConcrete3D compressive strength fc must be positive."
                )
            if self.parameters["ft"] < 0.0:
                raise ValueError(
                    "ASDConcrete3D tensile strength ft cannot be negative."
                )
            if self.parameters["implex"] not in {0.0, 1.0}:
                raise ValueError(
                    "ASDConcrete3D implex must be 0 (implicit) or 1 (IMPL-EX)."
                )
            kc = self.parameters["Kc"]
            if not 0.5 < kc <= 1.0:
                raise ValueError(
                    "ASDConcrete3D Kc must satisfy 0.5 < Kc <= 1."
                )
            if self.parameters["cdf"] < 0.0:
                raise ValueError(
                    "ASDConcrete3D cdf cannot be negative."
                )
        elif self.material_type == "OrthotropicRAConcrete":
            conc = self.parameters["conc"]
            if not conc.is_integer() or conc <= 0.0:
                raise ValueError(
                    "OrthotropicRAConcrete conc must be a positive "
                    "uniaxial material tag."
                )
            if self.parameters["ecr"] <= 0.0:
                raise ValueError(
                    "OrthotropicRAConcrete ecr must be positive."
                )
            if self.parameters["ec"] >= 0.0:
                raise ValueError(
                    "OrthotropicRAConcrete ec must be negative."
                )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "OrthotropicRAConcrete density rho cannot be negative."
                )
            for key in ("DamageCte1", "DamageCte2"):
                if self.parameters[key] < 0.0:
                    raise ValueError(
                        f"OrthotropicRAConcrete {key} cannot be negative."
                    )
        elif self.material_type == "SmearedSteelDoubleLayer":
            for key in ("mat1", "mat2"):
                tag = self.parameters[key]
                if not tag.is_integer() or tag <= 0.0:
                    raise ValueError(
                        f"SmearedSteelDoubleLayer {key} must be a positive "
                        "uniaxial material tag."
                    )
            for key in ("ratio1", "ratio2"):
                if not 0.0 <= self.parameters[key] <= 1.0:
                    raise ValueError(
                        f"SmearedSteelDoubleLayer {key} must satisfy 0 <= "
                        f"{key} <= 1."
                    )
        elif self.material_type == "FSAM":
            for key in ("sX", "sY", "conc"):
                tag = self.parameters[key]
                if not tag.is_integer() or tag <= 0.0:
                    raise ValueError(
                        f"FSAM {key} must be a positive uniaxial material tag."
                    )
            if self.parameters["rho"] < 0.0:
                raise ValueError("FSAM density rho cannot be negative.")
            for key in ("rouX", "rouY"):
                if not 0.0 <= self.parameters[key] <= 1.0:
                    raise ValueError(
                        f"FSAM {key} must satisfy 0 <= {key} <= 1."
                    )
            if not 0.0 < self.parameters["nu"] < 1.5:
                raise ValueError(
                    "FSAM friction coefficient nu must satisfy 0 < nu < 1.5."
                )
            if not 0.0 < self.parameters["alfadow"] < 0.05:
                raise ValueError(
                    "FSAM dowel coefficient alfadow must satisfy "
                    "0 < alfadow < 0.05."
                )
        if not isinstance(self.source, dict):
            raise ValueError("nDMaterial source metadata must be an object.")
        self.source = deepcopy(self.source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "material_type": self.material_type,
            "parameters": dict(self.parameters),
            "source": deepcopy(self.source),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NDMaterialData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", f"nDMaterial {data['tag']}")),
            material_type=str(
                data.get(
                    "material_type",
                    data.get("type", "ElasticIsotropic"),
                )
            ),
            parameters={
                str(key): float(value)
                for key, value in dict(data.get("parameters", {})).items()
            },
            source=deepcopy(dict(data.get("source", {}))),
        )


SECTION_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "Elastic": ("E", "A", "Iz", "Iy", "G", "J", "Avy", "Avz"),
    "Fiber": ("GJ",),
    "FiberInt": (
        "nStrip1", "thick1",
        "nStrip2", "thick2",
        "nStrip3", "thick3",
    ),
    "ElasticMembranePlate": ("E", "nu", "h", "rho", "EpModifier"),
    "PlateFiber": ("h",),
    "LayeredShell": (),
    "RCLMS": (),
}
SHELL_SECTION_TYPES = {
    "ElasticMembranePlate",
    "PlateFiber",
    "LayeredShell",
}
MEMBRANE_SECTION_TYPES = {"RCLMS"}


SECTION_DEFAULTS: dict[str, dict[str, float]] = {
    "Elastic": {
        "E": 2.0e11,
        "A": 0.02,
        "Iz": 8.0e-5,
        "Iy": 8.0e-5,
        "G": 7.6923e10,
        "J": 8.0e-5,
        "Avy": 0.02,
        "Avz": 0.02,
    },
    "Fiber": {
        "GJ": 1.0e6,
    },
    "FiberInt": {
        "nStrip1": 1.0, "thick1": 0.20,
        "nStrip2": 1.0, "thick2": 0.20,
        "nStrip3": 1.0, "thick3": 0.20,
    },
    "ElasticMembranePlate": {
        "E": 2.0e11,
        "nu": 0.30,
        "h": 0.20,
        "rho": 0.0,
        "EpModifier": 1.0,
    },
    "PlateFiber": {
        "h": 0.20,
    },
    "LayeredShell": {},
    "RCLMS": {},
}


@dataclass
class FiberData:
    y: float
    z: float
    area: float
    material_tag: int

    def __post_init__(self) -> None:
        self.y = float(self.y)
        self.z = float(self.z)
        self.area = float(self.area)
        self.material_tag = _strict_int(
            self.material_tag,
            "Fiber material tag",
        )
        if any(
            not math.isfinite(value)
            for value in (self.y, self.z, self.area)
        ):
            raise ValueError("Fiber coordinates and area must be finite.")
        if self.area <= 0.0:
            raise ValueError("Fiber area must be positive.")
        if self.material_tag <= 0:
            raise ValueError("Fiber material tag must be positive.")

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
            material_tag=data["material_tag"],
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
        self.material_tag = _strict_int(
            self.material_tag,
            "Fiber component material tag",
        )
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
        if any(
            not math.isfinite(value)
            for value in self.parameters.values()
        ):
            raise ValueError("Fiber component parameters must be finite.")
        self._validate()

    def _positive_int(self, key: str) -> int:
        numeric = self.parameters[key]
        if not float(numeric).is_integer():
            raise ValueError(f"{key} must be an integer.")
        value = int(numeric)
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
            material_tag=data["material_tag"],
            parameters={
                str(key): float(value)
                for key, value in dict(data.get("parameters", {})).items()
            },
        )


@dataclass
class ShellLayerData:
    material_tag: int
    thickness: float

    def __post_init__(self) -> None:
        self.material_tag = _strict_int(
            self.material_tag,
            "Shell layer nDMaterial tag",
        )
        self.thickness = float(self.thickness)
        if self.material_tag <= 0:
            raise ValueError(
                "Shell layer nDMaterial tag must be positive."
            )
        if not math.isfinite(self.thickness) or self.thickness <= 0.0:
            raise ValueError(
                "Shell layer thickness must be finite and positive."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_tag": self.material_tag,
            "thickness": self.thickness,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShellLayerData":
        return cls(
            material_tag=data["material_tag"],
            thickness=float(data["thickness"]),
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
    nd_material_tag: int | None = None
    shell_layers: list[ShellLayerData] = field(default_factory=list)
    horizontal_fibers: list[FiberData] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Section tag")
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
        if any(
            not math.isfinite(value)
            for value in self.parameters.values()
        ):
            raise ValueError("Section parameters must be finite.")
        if self.section_type == "ElasticMembranePlate":
            if self.parameters["E"] <= 0.0:
                raise ValueError(
                    "ElasticMembranePlate elastic modulus E must be positive."
                )
            if not -1.0 < self.parameters["nu"] < 0.5:
                raise ValueError(
                    "ElasticMembranePlate Poisson ratio must satisfy "
                    "-1 < nu < 0.5."
                )
            if self.parameters["h"] <= 0.0:
                raise ValueError(
                    "ElasticMembranePlate thickness h must be positive."
                )
            if self.parameters["rho"] < 0.0:
                raise ValueError(
                    "ElasticMembranePlate mass density rho cannot be negative."
                )
            if self.parameters["EpModifier"] <= 0.0:
                raise ValueError(
                    "ElasticMembranePlate EpModifier must be positive."
                )
        if self.section_type == "PlateFiber":
            if self.parameters["h"] <= 0.0:
                raise ValueError(
                    "PlateFiber thickness h must be positive."
                )
            self.nd_material_tag = (
                None
                if self.nd_material_tag is None
                else _strict_int(
                    self.nd_material_tag,
                    "PlateFiber nDMaterial tag",
                )
            )
            if self.nd_material_tag is None or self.nd_material_tag <= 0:
                raise ValueError(
                    "PlateFiber requires a valid nDMaterial tag."
                )
        elif self.section_type == "RCLMS":
            self.nd_material_tag = (
                None
                if self.nd_material_tag is None
                else _strict_int(
                    self.nd_material_tag,
                    "RCLMS reinforcing-steel nDMaterial tag",
                )
            )
            if self.nd_material_tag is None or self.nd_material_tag <= 0:
                raise ValueError(
                    "RCLMS requires a SmearedSteelDoubleLayer nDMaterial tag."
                )
        else:
            self.nd_material_tag = None

        self.shell_layers = [
            layer
            if isinstance(layer, ShellLayerData)
            else ShellLayerData.from_dict(dict(layer))
            for layer in self.shell_layers
        ]
        if self.section_type == "LayeredShell":
            if len(self.shell_layers) < 3:
                raise ValueError(
                    "LayeredShell requires at least three material layers "
                    "for the OpenSees LayeredShell section."
                )
        elif self.section_type == "RCLMS":
            if not self.shell_layers:
                raise ValueError(
                    "RCLMS requires at least one concrete nDMaterial layer."
                )
        else:
            self.shell_layers = []
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
        self.horizontal_fibers = [
            fiber if isinstance(fiber, FiberData) else FiberData.from_dict(fiber)
            for fiber in self.horizontal_fibers
        ]
        if self.section_type == "Elastic":
            for key in ("E", "A", "Iz", "Avy", "Avz"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(
                        f"Elastic section parameter {key} must be positive."
                    )
            for key in ("Iy", "G", "J"):
                if self.parameters[key] < 0.0:
                    raise ValueError(
                        f"Elastic section parameter {key} cannot be negative."
                    )
        if self.section_type == "FiberInt":
            for key in ("nStrip1", "nStrip2", "nStrip3"):
                value = self.parameters[key]
                if not float(value).is_integer() or value < 0.0:
                    raise ValueError(
                        f"FiberInt {key} must be a non-negative integer."
                    )
            for key in ("thick1", "thick2", "thick3"):
                if self.parameters[key] <= 0.0:
                    raise ValueError(f"FiberInt {key} must be positive.")
            strip_count = sum(
                int(self.parameters[key])
                for key in ("nStrip1", "nStrip2", "nStrip3")
            )
            if strip_count < 1:
                raise ValueError("FiberInt requires at least one strip.")
            if not self.fibers:
                raise ValueError(
                    "FiberInt requires vertical concrete/steel fibers."
                )
            if not self.horizontal_fibers:
                raise ValueError(
                    "FiberInt requires at least one horizontal Hfiber."
                )
            unique_y = {round(float(fiber.y), 12) for fiber in self.fibers}
            if len(unique_y) != strip_count:
                raise ValueError(
                    "FiberInt NStrip total must match the number of distinct "
                    "vertical-fiber y locations."
                )
            self.fiber_components = []
        elif self.section_type != "Fiber":
            self.horizontal_fibers = []
        if self.section_type == "Elastic" and self.material_tag is not None:
            self.material_tag = _strict_int(
                self.material_tag,
                "Section material tag",
            )
        else:
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
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(numeric):
                    raise ValueError(
                        "Section display-geometry dimensions must be finite."
                    )
                dimensions[str(key)] = numeric
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
        if self.section_type == "Fiber":
            return {
                fiber.material_tag
                for fiber in self.fibers
            } | {
                component.material_tag
                for component in self.fiber_components
            }
        if self.section_type == "FiberInt":
            return {
                fiber.material_tag
                for fiber in (*self.fibers, *self.horizontal_fibers)
            }
        return set()

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

    def shell_nd_material_tags(self) -> set[int]:
        if self.section_type == "PlateFiber":
            return (
                set()
                if self.nd_material_tag is None
                else {int(self.nd_material_tag)}
            )
        if self.section_type == "LayeredShell":
            return {
                int(layer.material_tag)
                for layer in self.shell_layers
            }
        if self.section_type == "RCLMS":
            tags = {
                int(layer.material_tag)
                for layer in self.shell_layers
            }
            if self.nd_material_tag is not None:
                tags.add(int(self.nd_material_tag))
            return tags
        return set()

    def shell_total_thickness(self) -> float:
        if self.section_type == "ElasticMembranePlate":
            return float(self.parameters["h"])
        if self.section_type == "PlateFiber":
            return float(self.parameters["h"])
        if self.section_type in {"LayeredShell", "RCLMS"}:
            return sum(
                float(layer.thickness)
                for layer in self.shell_layers
            )
        return 0.0

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
            "horizontal_fibers": [
                fiber.to_dict() for fiber in self.horizontal_fibers
            ],
            "material_tag": self.material_tag,
            "nd_material_tag": self.nd_material_tag,
            "shell_layers": [
                layer.to_dict()
                for layer in self.shell_layers
            ],
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
            tag=data["tag"],
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
            horizontal_fibers=[
                FiberData.from_dict(dict(item))
                for item in data.get("horizontal_fibers", [])
            ],
            material_tag=data.get("material_tag"),
            display_geometry=dict(data.get("display_geometry", {})),
            nd_material_tag=data.get("nd_material_tag"),
            shell_layers=[
                ShellLayerData.from_dict(dict(item))
                for item in data.get("shell_layers", [])
            ],
        )


@dataclass
class TransformationData:
    tag: int
    name: str
    transformation_type: str
    vecxz: tuple[float, float, float] = (0.0, 0.0, 1.0)
    orientation_mode: str = "manual"

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Transformation tag")
        self.name = str(self.name).strip() or f"Transformation {self.tag}"
        self.transformation_type = str(self.transformation_type)
        self.orientation_mode = str(self.orientation_mode).strip().lower()
        if self.tag <= 0:
            raise ValueError("Transformation tag must be a positive integer.")
        if self.transformation_type not in {
            "Linear",
            "PDelta",
            "Corotational",
            "LinearInt",
        }:
            raise ValueError(
                f"Unsupported transformation type: {self.transformation_type}"
            )
        if self.orientation_mode not in {"auto", "manual"}:
            raise ValueError(
                "Transformation orientation mode must be Auto or Manual."
            )
        self.vecxz = tuple(float(value) for value in self.vecxz)
        if len(self.vecxz) != 3:
            raise ValueError("Transformation orientation vector must have 3 values.")
        if any(not math.isfinite(value) for value in self.vecxz):
            raise ValueError(
                "Transformation orientation vector values must be finite."
            )
        if sum(value * value for value in self.vecxz) <= 1.0e-24:
            raise ValueError("Transformation orientation vector cannot be zero.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "transformation_type": self.transformation_type,
            "vecxz": list(self.vecxz),
            "orientation_mode": self.orientation_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransformationData":
        raw_vec = data.get("vecxz", (0.0, 0.0, 1.0))
        return cls(
            tag=data["tag"],
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
            # Legacy projects explicitly stored vecxz, so preserve their
            # behavior as Manual unless the newer mode is present.
            orientation_mode=str(data.get("orientation_mode", "manual")),
        )


def resolve_transformation_vecxz(
    model: StructuralModel,
    transformation: TransformationData,
) -> tuple[float, float, float]:
    """Return a stable effective OpenSees vecxz for one transformation.

    Auto mode follows a fixed building-frame convention instead of searching
    for an arbitrary "best" vector: Global Z is the preferred up direction;
    Global X, then Global Y, are deterministic fallbacks when the preferred
    direction is too close to a member axis. The same reference must be safe
    for every frame member sharing the transformation tag. If one Auto tag
    mixes incompatible member families (for example X-, Y-, and Z-aligned
    members), SARE requires separate Auto transformations rather than silently
    rotating section axes.
    """
    if (
        transformation.orientation_mode != "auto"
        or int(model.ndm) == 2
    ):
        return tuple(float(value) for value in transformation.vecxz)

    member_axes: list[tuple[float, float, float]] = []
    for element in model.elements.values():
        if (
            element.element_type not in FRAME_ELEMENT_TYPES
            or element.transf_tag is None
            or int(element.transf_tag) != int(transformation.tag)
        ):
            continue
        node_i = model.nodes.get(int(element.i))
        node_j = model.nodes.get(int(element.j))
        if node_i is None or node_j is None:
            continue
        delta = tuple(
            float(node_j.xyz[index]) - float(node_i.xyz[index])
            for index in range(3)
        )
        norm = math.sqrt(sum(value * value for value in delta))
        if norm <= 1.0e-15:
            continue
        member_axes.append(tuple(value / norm for value in delta))

    if not member_axes:
        return tuple(float(value) for value in transformation.vecxz)

    # Keep the preferred up direction until the geometry is genuinely close
    # to the singular case. This avoids orientation changes from small model
    # perturbations while still protecting OpenSees from near-parallel vecxz.
    min_sine = math.sin(math.radians(5.0))
    candidates = (
        (0.0, 0.0, 1.0),  # Global Z: normal beam / inclined-member up
        (1.0, 0.0, 0.0),  # Global X: vertical-column fallback
        (0.0, 1.0, 0.0),  # Global Y: secondary deterministic fallback
    )
    for candidate in candidates:
        if all(
            math.sqrt(max(
                0.0,
                1.0 - sum(
                    candidate[index] * axis[index]
                    for index in range(3)
                ) ** 2,
            )) >= min_sine
            for axis in member_axes
        ):
            return candidate

    raise ValueError(
        "Auto orientation cannot preserve a stable Global-Up convention for "
        f"transformation {transformation.tag} because it is shared by "
        "incompatible member directions. Assign separate Auto "
        "transformations to those member families, or use Manual orientation."
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
        self.tag = _strict_int(self.tag, "Constraint tag")
        self.name = str(self.name).strip() or f"Constraint {self.tag}"
        self.constraint_type = str(self.constraint_type)
        self.retained_node = _strict_int(
            self.retained_node,
            "Constraint retained node",
        )
        normalized_constrained_nodes = {
            _strict_int(tag, "Constraint constrained node")
            for tag in self.constrained_nodes
        }
        self.constrained_nodes = sorted(
            tag
            for tag in normalized_constrained_nodes
            if tag != self.retained_node
        )
        self.dofs = tuple(sorted({
            (
                _strict_int(dof, "Constraint DOF")
                if self.constraint_type == "equalDOF"
                else int(dof)
            )
            for dof in self.dofs
        }))
        self.link_type = str(self.link_type)
        self.perp_dirn = (
            _strict_int(
                self.perp_dirn,
                "Rigid diaphragm perpendicular direction",
            )
            if self.constraint_type == "rigidDiaphragm"
            else int(self.perp_dirn)
        )

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
            tag=data["tag"],
            name=str(data.get("name", f"Constraint {data['tag']}")),
            constraint_type=str(data.get("constraint_type", "equalDOF")),
            retained_node=data["retained_node"],
            constrained_nodes=list(data.get("constrained_nodes", [])),
            dofs=tuple(data.get("dofs", [])),
            link_type=str(data.get("link_type", "beam")),
            perp_dirn=data.get("perp_dirn", 3),
        )


SUPPORTED_CONNECTION_TYPES: tuple[str, ...] = (
    "rigid",
    "pinned",
    "semiRigid",
    "zeroLength",
    "CoupledZeroLength",
    "zeroLengthSection",
    "twoNodeLink",
    "Joint2D",
    "BeamColumnJoint",
    "LehighJoint2D",
    "KrawinklerPanelZone",
)

# Only these connection records create a real OpenSees element tag.
# rigid -> rigidLink and pinned -> equalDOF are MPC/kinematic relations,
# so they must never be exposed to Element recorders/results.
ELEMENT_BACKED_CONNECTION_TYPES: tuple[str, ...] = (
    "semiRigid",
    "zeroLength",
    "CoupledZeroLength",
    "zeroLengthSection",
    "twoNodeLink",
    "Joint2D",
    "BeamColumnJoint",
    "LehighJoint2D",
    "KrawinklerPanelZone",
)

CONNECTION_RECORDER_RESPONSES: dict[str, set[str]] = {
    # semiRigid is exported as a zeroLength element.
    "semiRigid": {"force", "deformation"},
    "zeroLength": {"force", "deformation"},
    # OpenSees documents force and material ...; SARE exposes force here
    # because RecorderData does not yet model response arguments.
    "CoupledZeroLength": {"force"},
    "zeroLengthSection": {"force", "deformation", "stiff"},
    "twoNodeLink": {
        "force",
        "localForce",
        "basicForce",
        "localDisplacement",
        "basicDisplacement",
    },
    "Joint2D": {
        "force",
        "deformation",
        "centralNode",
        "size",
        "stiffness",
        "defoANDforce",
    },
    "BeamColumnJoint": {
        "internalDisplacement",
        "externalDisplacement",
        "deformation",
        "node1BarSlipL",
        "node1BarSlipR",
        "node1InterfaceShear",
        "node2BarSlipB",
        "node2BarSlipT",
        "node2InterfaceShear",
        "node3BarSlipL",
        "node3BarSlipR",
        "node3InterfaceShear",
        "node4BarSlipB",
        "node4BarSlipT",
        "node4InterfaceShear",
        "shearPanel",
    },
    # Verified against OpenSees LehighJoint2d::setResponse.
    "LehighJoint2D": {
        "globalForce",
        "localForce",
        "basicForces",
        "Deformation",
    },
    # The public Krawinkler object exposes its zeroLength panel spring tag.
    "KrawinklerPanelZone": {"force", "deformation"},
}




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
    section_tag: int | None = None
    generated_section_tag: int | None = None
    generated_constraint_tag: int | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Connection tag")
        self.name = str(self.name).strip() or f"Connection {self.tag}"
        self.connection_type = str(self.connection_type)
        self.node_i = _strict_int(self.node_i, "Connection node i")
        self.node_j = _strict_int(self.node_j, "Connection node j")
        self.materials_by_dof = {
            _strict_int(dof, "Connection DOF"): _strict_int(
                material_tag,
                "Connection material tag",
            )
            for dof, material_tag in self.materials_by_dof.items()
        }
        self.orient_x = tuple(float(v) for v in self.orient_x)
        self.orient_y = tuple(float(v) for v in self.orient_y)
        self.do_rayleigh = _strict_bool(
            self.do_rayleigh,
            "Connection Rayleigh flag",
        )
        self.generated_ground_node = (
            None
            if self.generated_ground_node is None
            else _strict_int(
                self.generated_ground_node,
                "Connection generated ground node",
            )
        )
        self.section_tag = (
            None
            if self.section_tag is None
            else (
                _strict_int(
                    self.section_tag,
                    "Connection section tag",
                )
                if self.connection_type == "zeroLengthSection"
                else int(self.section_tag)
            )
        )
        self.generated_section_tag = (
            None
            if self.generated_section_tag is None
            else _strict_int(
                self.generated_section_tag,
                "Connection generated section tag",
            )
        )
        self.generated_constraint_tag = (
            None
            if self.generated_constraint_tag is None
            else _strict_int(
                self.generated_constraint_tag,
                "Connection generated constraint tag",
            )
        )
        self.parameters = dict(self.parameters or {})

        if self.tag <= 0:
            raise ValueError("Connection tag must be a positive integer.")
        if self.connection_type not in SUPPORTED_CONNECTION_TYPES:
            raise ValueError(
                f"Unsupported connection type: {self.connection_type}"
            )
        if self.node_i < 0 or self.node_j < 0:
            raise ValueError("Connection node tags must be non-negative.")
        if (
            self.generated_ground_node is not None
            and self.generated_ground_node <= 0
        ):
            raise ValueError(
                "Connection generated ground node must be positive."
            )
        if (
            self.generated_section_tag is not None
            and self.generated_section_tag <= 0
        ):
            raise ValueError(
                "Connection generated section tag must be positive."
            )
        if (
            self.generated_constraint_tag is not None
            and self.generated_constraint_tag <= 0
        ):
            raise ValueError(
                "Connection generated constraint tag must be positive."
            )
        if self.node_i == self.node_j:
            raise ValueError("Connection needs two different node tags.")
        if self.connection_type == "zeroLengthSection":
            if self.section_tag is None or self.section_tag <= 0:
                raise ValueError(
                    "zeroLengthSection requires a valid section tag."
                )
            if self.materials_by_dof:
                raise ValueError(
                    "zeroLengthSection uses one Section object, not "
                    "materials_by_dof."
                )
        elif self.connection_type == "CoupledZeroLength":
            if len(self.materials_by_dof) != 2:
                raise ValueError(
                    "CoupledZeroLength requires exactly two coupled directions."
                )
            if any(dof < 1 or dof > 6 for dof in self.materials_by_dof):
                raise ValueError(
                    "CoupledZeroLength directions must be in the range 1..6."
                )
            if len(set(self.materials_by_dof.values())) != 1:
                raise ValueError(
                    "CoupledZeroLength uses one UniaxialMaterial shared by "
                    "both coupled directions."
                )
        elif self.connection_type in {
            "rigid",
            "pinned",
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }:
            if self.materials_by_dof:
                raise ValueError(
                    f"{self.connection_type} does not use materials_by_dof."
                )
        else:
            if not self.materials_by_dof:
                raise ValueError("Connection needs at least one active DOF.")
            if any(dof < 1 or dof > 6 for dof in self.materials_by_dof):
                raise ValueError("Connection DOFs must be in the range 1..6.")

        if self.connection_type in {
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }:
            external_nodes = self.parameters.get("external_nodes", ())
            if not isinstance(external_nodes, (list, tuple)) or len(external_nodes) != 4:
                raise ValueError(
                    f"{self.connection_type} requires four external_nodes."
                )
            external_nodes = tuple(
                _strict_int(tag, "Joint external node")
                for tag in external_nodes
            )
            if len(set(external_nodes)) != 4:
                raise ValueError("Joint external nodes must be four distinct tags.")
            self.parameters["external_nodes"] = list(external_nodes)

            if self.connection_type in {"Joint2D", "KrawinklerPanelZone"}:
                panel_material = _strict_int(
                    self.parameters.get("panel_material", 0),
                    "Joint panel material",
                )
                if panel_material <= 0:
                    raise ValueError(
                        f"{self.connection_type} requires a panel material."
                    )
                self.parameters["panel_material"] = panel_material

        if self.connection_type == "Joint2D":
            interface_materials = self.parameters.get(
                "interface_materials",
                (0, 0, 0, 0),
            )
            if (
                not isinstance(interface_materials, (list, tuple))
                or len(interface_materials) != 4
            ):
                raise ValueError(
                    "Joint2D interface_materials must contain four tags."
                )
            normalized_interface = tuple(
                _strict_int(tag, "Joint2D interface material")
                for tag in interface_materials
            )
            if any(tag < 0 for tag in normalized_interface):
                raise ValueError(
                    "Joint2D interface material tags must be zero or positive."
                )
            self.parameters["interface_materials"] = list(
                normalized_interface
            )
            large_disp = _strict_int(
                self.parameters.get("large_disp", 0),
                "Joint2D large displacement flag",
            )
            if large_disp not in {0, 1, 2}:
                raise ValueError(
                    "Joint2D large_disp must be 0, 1, or 2."
                )
            self.parameters["large_disp"] = large_disp
            imported_center = self.parameters.get(
                "imported_center_node_tag"
            )
            if imported_center is not None:
                imported_center = _strict_int(
                    imported_center,
                    "Joint2D imported center node tag",
                )
                if imported_center <= 0:
                    raise ValueError(
                        "Joint2D imported center node tag must be positive."
                    )
                self.parameters["imported_center_node_tag"] = imported_center

        if self.connection_type == "BeamColumnJoint":
            component_materials = self.parameters.get(
                "component_materials",
                (),
            )
            if (
                not isinstance(component_materials, (list, tuple))
                or len(component_materials) != 13
            ):
                raise ValueError(
                    "BeamColumnJoint requires exactly 13 component materials."
                )
            normalized_components = [
                _strict_int(tag, "BeamColumnJoint component material")
                for tag in component_materials
            ]
            if any(tag <= 0 for tag in normalized_components):
                raise ValueError(
                    "BeamColumnJoint component material tags must be positive."
                )
            self.parameters["component_materials"] = normalized_components
            height_factor = float(
                self.parameters.get("height_factor", 1.0)
            )
            width_factor = float(
                self.parameters.get("width_factor", 1.0)
            )
            if (
                not math.isfinite(height_factor)
                or height_factor <= 0.0
                or not math.isfinite(width_factor)
                or width_factor <= 0.0
            ):
                raise ValueError(
                    "BeamColumnJoint height/width factors must be positive."
                )
            self.parameters["height_factor"] = height_factor
            self.parameters["width_factor"] = width_factor

        if self.connection_type == "LehighJoint2D":
            mode_materials = self.parameters.get("mode_materials", ())
            if (
                not isinstance(mode_materials, (list, tuple))
                or len(mode_materials) != 9
            ):
                raise ValueError(
                    "LehighJoint2D requires exactly 9 deformation-mode materials."
                )
            normalized_modes = [
                _strict_int(tag, "LehighJoint2D material")
                for tag in mode_materials
            ]
            if any(tag <= 0 for tag in normalized_modes):
                raise ValueError(
                    "LehighJoint2D material tags must be positive."
                )
            self.parameters["mode_materials"] = normalized_modes

        if self.connection_type == "KrawinklerPanelZone":
            for key in ("rigid_A", "rigid_E", "rigid_I"):
                value = float(self.parameters.get(key, 0.0))
                if not math.isfinite(value) or value <= 0.0:
                    raise ValueError(
                        f"KrawinklerPanelZone requires positive {key}."
                    )
                self.parameters[key] = value

        if self.connection_type == "twoNodeLink":
            # Historical SARE projects always emitted -orient. Preserve that
            # behavior unless a newer project explicitly stores False.
            orientation_override = self.parameters.get(
                "orientation_override",
                True,
            )
            self.parameters["orientation_override"] = _strict_bool(
                orientation_override,
                "twoNodeLink orientation_override",
            )

            p_delta = self.parameters.get("p_delta", ())
            if p_delta is None:
                p_delta = ()
            if not isinstance(p_delta, (list, tuple)):
                raise ValueError("twoNodeLink p_delta must be a list.")
            p_delta_values = [float(value) for value in p_delta]
            if len(p_delta_values) not in {0, 2, 4}:
                raise ValueError(
                    "twoNodeLink p_delta must contain 2 values for 2D or "
                    "4 values for 3D."
                )
            if any(
                not math.isfinite(value) or value < 0.0
                for value in p_delta_values
            ):
                raise ValueError(
                    "twoNodeLink p_delta values must be finite and non-negative."
                )
            if len(p_delta_values) == 2 and sum(p_delta_values) > 1.0 + 1.0e-12:
                raise ValueError(
                    "twoNodeLink 2D p_delta end-moment ratios must sum to <= 1."
                )
            if len(p_delta_values) == 4 and (
                p_delta_values[0] + p_delta_values[1] > 1.0 + 1.0e-12
                or p_delta_values[2] + p_delta_values[3] > 1.0 + 1.0e-12
            ):
                raise ValueError(
                    "twoNodeLink 3D p_delta end-moment ratio pairs must "
                    "each sum to <= 1."
                )
            self.parameters["p_delta"] = p_delta_values

            shear_dist = self.parameters.get("shear_dist", ())
            if shear_dist is None:
                shear_dist = ()
            if not isinstance(shear_dist, (list, tuple)):
                raise ValueError("twoNodeLink shear_dist must be a list.")
            shear_values = [float(value) for value in shear_dist]
            if len(shear_values) not in {0, 1, 2}:
                raise ValueError(
                    "twoNodeLink shear_dist must contain 1 value for 2D or "
                    "2 values for 3D."
                )
            if any(
                not math.isfinite(value) or not 0.0 <= value <= 1.0
                for value in shear_values
            ):
                raise ValueError(
                    "twoNodeLink shear_dist values must be within [0, 1]."
                )
            self.parameters["shear_dist"] = shear_values

            link_mass = float(self.parameters.get("mass", 0.0))
            if not math.isfinite(link_mass) or link_mass < 0.0:
                raise ValueError(
                    "twoNodeLink mass must be finite and non-negative."
                )
            self.parameters["mass"] = link_mass
        if len(self.orient_x) != 3 or len(self.orient_y) != 3:
            raise ValueError("Connection orientation vectors need 3 values.")
        if any(
            not math.isfinite(value)
            for value in (*self.orient_x, *self.orient_y)
        ):
            raise ValueError(
                "Connection orientation vector values must be finite."
            )
        if sum(v * v for v in self.orient_x) <= 1.0e-24:
            raise ValueError("Connection local X vector cannot be zero.")
        if sum(v * v for v in self.orient_y) <= 1.0e-24:
            raise ValueError("Connection local Y vector cannot be zero.")
        cross = (
            self.orient_x[1] * self.orient_y[2]
            - self.orient_x[2] * self.orient_y[1],
            self.orient_x[2] * self.orient_y[0]
            - self.orient_x[0] * self.orient_y[2],
            self.orient_x[0] * self.orient_y[1]
            - self.orient_x[1] * self.orient_y[0],
        )
        nx = math.sqrt(sum(value * value for value in self.orient_x))
        ny = math.sqrt(sum(value * value for value in self.orient_y))
        nc = math.sqrt(sum(value * value for value in cross))
        if nc / (nx * ny) <= 1.0e-8:
            raise ValueError(
                "Connection local X and Y-plane vectors cannot be parallel."
            )

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
            "section_tag": self.section_tag,
            "generated_section_tag": self.generated_section_tag,
            "generated_constraint_tag": self.generated_constraint_tag,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectionData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", f"Connection {data['tag']}")),
            connection_type=str(
                data.get("connection_type", "zeroLength")
            ),
            node_i=data["node_i"],
            node_j=data["node_j"],
            materials_by_dof=dict(
                data.get("materials_by_dof", {})
            ),
            orient_x=tuple(
                float(v) for v in data.get("orient_x", (1.0, 0.0, 0.0))
            ),
            orient_y=tuple(
                float(v) for v in data.get("orient_y", (0.0, 1.0, 0.0))
            ),
            do_rayleigh=data.get("do_rayleigh", False),
            generated_ground_node=data.get("generated_ground_node"),
            section_tag=data.get("section_tag"),
            generated_section_tag=data.get("generated_section_tag"),
            generated_constraint_tag=data.get("generated_constraint_tag"),
            parameters=dict(data.get("parameters", {})),
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
        self.tag = _strict_int(self.tag, "Time series tag")
        self.name = str(self.name).strip() or f"Time Series {self.tag}"
        self.series_type = str(self.series_type)
        self.factor = float(self.factor)
        self.dt = float(self.dt)
        self.values = [float(value) for value in self.values]
        if self.tag <= 0:
            raise ValueError("Time series tag must be positive.")
        if (
            not math.isfinite(self.factor)
            or not math.isfinite(self.dt)
            or any(not math.isfinite(value) for value in self.values)
        ):
            raise ValueError("Time series numeric values must be finite.")
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
            tag=data["tag"],
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
        self.tag = _strict_int(self.tag, "Load pattern tag")
        self.name = str(self.name).strip() or f"Load Pattern {self.tag}"
        self.pattern_type = str(self.pattern_type)
        self.time_series_tag = _strict_int(
            self.time_series_tag,
            "Load pattern time series tag",
        )
        self.direction = (
            _strict_int(
                self.direction,
                "UniformExcitation direction",
            )
            if self.pattern_type == "UniformExcitation"
            else int(self.direction)
        )
        self.factor = float(self.factor)
        self.vel0 = float(self.vel0)
        if self.tag <= 0:
            raise ValueError("Load pattern tag must be positive.")
        if self.time_series_tag <= 0:
            raise ValueError("Load pattern needs a valid time series tag.")
        if self.pattern_type not in {"Plain", "UniformExcitation"}:
            raise ValueError(f"Unsupported pattern type: {self.pattern_type}")
        if not math.isfinite(self.factor) or not math.isfinite(self.vel0):
            raise ValueError(
                "Load pattern factor and initial velocity must be finite."
            )
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
            tag=data["tag"],
            name=str(data.get("name", f"Load Pattern {data['tag']}")),
            pattern_type=str(data.get("pattern_type", "Plain")),
            time_series_tag=data["time_series_tag"],
            direction=data.get("direction", 1),
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
        self.tag = _strict_int(self.tag, "Nodal load tag")
        self.name = str(self.name).strip() or f"Nodal Load {self.tag}"
        self.pattern_tag = _strict_int(
            self.pattern_tag,
            "Nodal load pattern tag",
        )
        self.node_tag = _strict_int(
            self.node_tag,
            "Nodal load node tag",
        )
        self.values = tuple(float(value) for value in self.values)
        if self.tag <= 0:
            raise ValueError("Nodal load tag must be positive.")
        if self.pattern_tag <= 0 or self.node_tag <= 0:
            raise ValueError("Nodal load needs valid pattern and node tags.")
        if len(self.values) != 6:
            raise ValueError("Nodal load needs six DOF values.")
        if any(not math.isfinite(value) for value in self.values):
            raise ValueError("Nodal load values must be finite.")

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
            tag=data["tag"],
            name=str(data.get("name", f"Nodal Load {data['tag']}")),
            pattern_tag=data["pattern_tag"],
            node_tag=data["node_tag"],
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
        self.tag = _strict_int(
            self.tag,
            "Prescribed displacement tag",
        )
        self.name = (
            str(self.name).strip()
            or f"Prescribed Displacement {self.tag}"
        )
        self.pattern_tag = _strict_int(
            self.pattern_tag,
            "Prescribed displacement pattern tag",
        )
        self.node_tag = _strict_int(
            self.node_tag,
            "Prescribed displacement node tag",
        )
        self.dof = _strict_int(
            self.dof,
            "Prescribed displacement DOF",
        )
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
            tag=data["tag"],
            name=str(
                data.get(
                    "name",
                    f"Prescribed Displacement {data['tag']}",
                )
            ),
            pattern_tag=data["pattern_tag"],
            node_tag=data["node_tag"],
            dof=data.get("dof", 1),
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
    pressure: float = 0.0
    coordinate_system: str = "local"
    wx_end: float = 0.0
    wy_end: float = 0.0
    wz_end: float = 0.0
    a_over_l: float = 0.0
    b_over_l: float = 1.0

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Element load tag")
        self.name = str(self.name).strip() or f"Element Load {self.tag}"
        self.pattern_tag = _strict_int(
            self.pattern_tag,
            "Element load pattern tag",
        )
        self.element_tag = _strict_int(
            self.element_tag,
            "Element load element tag",
        )
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
        self.pressure = float(self.pressure)
        self.coordinate_system = str(
            self.coordinate_system or "local"
        ).strip().lower()
        self.wx_end = float(self.wx_end)
        self.wy_end = float(self.wy_end)
        self.wz_end = float(self.wz_end)
        self.a_over_l = float(self.a_over_l)
        self.b_over_l = float(self.b_over_l)

        if self.tag <= 0:
            raise ValueError("Element load tag must be positive.")
        if self.pattern_tag <= 0 or self.element_tag <= 0:
            raise ValueError(
                "Element load needs valid pattern and element tags."
            )
        if self.load_type not in {
            "Uniform", "Triangular", "Trapezoidal", "Point",
            "SelfWeight", "SurfacePressure"
        }:
            raise ValueError(
                f"Unsupported element load type: {self.load_type}"
            )
        if self.coordinate_system not in {"local", "global"}:
            raise ValueError(
                "Beam-load coordinate system must be Local or Global."
            )
        if len(self.gravity) != 3:
            raise ValueError("Gravity vector needs three components.")
        numeric_values = (
            self.wx,
            self.wy,
            self.wz,
            self.px,
            self.py,
            self.pz,
            self.x_over_l,
            self.density_override,
            self.pressure,
            self.wx_end,
            self.wy_end,
            self.wz_end,
            self.a_over_l,
            self.b_over_l,
            *self.gravity,
        )
        if any(not math.isfinite(value) for value in numeric_values):
            raise ValueError("Element load numeric values must be finite.")
        if self.density_override < 0.0:
            raise ValueError("Density override cannot be negative.")
        if self.load_type == "Point" and not 0.0 <= self.x_over_l <= 1.0:
            raise ValueError("Point-load x/L must be between 0 and 1.")
        if self.load_type in {"Triangular", "Trapezoidal"}:
            if not 0.0 <= self.a_over_l < self.b_over_l <= 1.0:
                raise ValueError(
                    "Distributed-load limits must satisfy "
                    "0 <= a/L < b/L <= 1."
                )
        if self.load_type == "Triangular":
            tolerance = 1.0e-12
            start_zero = all(
                abs(value) <= tolerance
                for value in (self.wx, self.wy, self.wz)
            )
            end_zero = all(
                abs(value) <= tolerance
                for value in (self.wx_end, self.wy_end, self.wz_end)
            )
            if start_zero == end_zero:
                raise ValueError(
                    "Triangular beam load requires exactly one zero-intensity "
                    "end; use Trapezoidal when both ends are nonzero."
                )

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
            "pressure": self.pressure,
            "coordinate_system": self.coordinate_system,
            "wx_end": self.wx_end,
            "wy_end": self.wy_end,
            "wz_end": self.wz_end,
            "a_over_l": self.a_over_l,
            "b_over_l": self.b_over_l,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementLoadData":
        gravity = data.get("gravity", (0.0, 0.0, -9.81))
        return cls(
            tag=data["tag"],
            name=str(data.get("name", f"Element Load {data['tag']}")),
            pattern_tag=data["pattern_tag"],
            element_tag=data["element_tag"],
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
            pressure=float(data.get("pressure", 0.0)),
            # Existing projects stored beam components in local axes.
            coordinate_system=str(data.get("coordinate_system", "local")),
            wx_end=float(data.get("wx_end", 0.0)),
            wy_end=float(data.get("wy_end", 0.0)),
            wz_end=float(data.get("wz_end", 0.0)),
            a_over_l=float(data.get("a_over_l", 0.0)),
            b_over_l=float(data.get("b_over_l", 1.0)),
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
        self.tag = _strict_int(self.tag, "Mass source tag")
        self.name = str(self.name).strip() or f"Mass Source {self.tag}"
        self.include_self_mass = _strict_bool(
            self.include_self_mass,
            "Mass source include_self_mass",
        )
        raw_load_factors = {
            _strict_int(tag, "Mass source load-pattern tag"): float(factor)
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
        self.gravity_axis = _strict_int(
            self.gravity_axis,
            "Mass source gravity axis",
        )
        self.directions = tuple(
            sorted({
                _strict_int(dof, "Mass source direction")
                for dof in self.directions
            })
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
            tag=data["tag"],
            name=str(data.get("name", f"Mass Source {data['tag']}")),
            include_self_mass=data.get("include_self_mass", True),
            load_factors={
                tag: float(factor)
                for tag, factor in dict(
                    data.get("load_factors", {})
                ).items()
            },
            gravity_axis=data.get("gravity_axis", 3),
            directions=tuple(
                data.get("directions", (1, 2))
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
    # Keep new integrator fields at the end so existing positional
    # AnalysisSettingsData construction remains backward compatible.
    integrator: str = "Auto"
    hht_alpha: float = 0.9
    generalized_alpha_m: float = 1.0
    generalized_alpha_f: float = 1.0
    arc_length_s: float = 0.01
    arc_length_alpha: float = 1.0
    algorithm_initial: bool = False
    system_pivoting: bool = False
    gravity_algorithm: str = "Auto"
    rayleigh_model: str = "TwoMode"
    rayleigh_alpha_m: float = 0.0
    rayleigh_beta_k: float = 0.0
    rayleigh_beta_k_init: float = 0.0
    rayleigh_beta_k_comm: float = 0.0
    # Response-spectrum generation uses one or two existing
    # UniformExcitation patterns as acceleration sources. RotD50/RotD100
    # are outputs of the same analysis, not separate analysis types.
    response_spectrum_mode: str = "Bidirectional / RotD"
    response_spectrum_damping_ratio: float = 0.05
    response_spectrum_t1_step: float = 0.1
    response_spectrum_t1_end: float = 1.0
    response_spectrum_t2_step: float = 0.2
    response_spectrum_t2_end: float = 2.0
    response_spectrum_t3_step: float = 0.5
    response_spectrum_t3_end: float = 5.0
    response_spectrum_component_x: bool = True
    response_spectrum_component_y: bool = True
    response_spectrum_rotd50: bool = True
    response_spectrum_rotd100: bool = True
    # CPU/thread execution controls. Keep these at the end so existing
    # positional AnalysisSettingsData construction remains backward compatible.
    execution_mode: str = "Auto"
    num_threads: int = 1

    def __post_init__(self) -> None:
        self.tag=_strict_int(self.tag, "Analysis tag"); self.name=str(self.name).strip() or f"Analysis {self.tag}"
        self.analysis_type=str(self.analysis_type)
        self.integrator=str(self.integrator or "Auto")
        self.tolerance=float(self.tolerance)
        self.max_iterations=(
            _strict_int(self.max_iterations, "Analysis max iterations")
            if self.analysis_type not in {"Modal", "Response Spectrum"}
            else int(self.max_iterations)
        )
        self.steps=(
            _strict_int(self.steps, "Analysis steps")
            if self.analysis_type in {"Static", "Pushover", "Transient"}
            else int(self.steps)
        )
        self.load_increment=float(self.load_increment)
        raw_control_node = self.control_node
        raw_control_dof = self.control_dof
        self.displacement_increment=float(self.displacement_increment)
        self.cyclic_targets=[float(value) for value in self.cyclic_targets]
        self.cyclic_increment=abs(float(self.cyclic_increment))
        self.dt=float(self.dt); self.gamma=float(self.gamma); self.beta=float(self.beta)
        self.hht_alpha=float(self.hht_alpha)
        self.generalized_alpha_m=float(self.generalized_alpha_m)
        self.generalized_alpha_f=float(self.generalized_alpha_f)
        self.arc_length_s=float(self.arc_length_s)
        self.arc_length_alpha=float(self.arc_length_alpha)
        self.rayleigh_damping_ratio=float(self.rayleigh_damping_ratio)
        raw_rayleigh_mode_i = self.rayleigh_mode_i
        raw_rayleigh_mode_j = self.rayleigh_mode_j
        self.preload_gravity=_strict_bool(
            self.preload_gravity,
            "Analysis preload_gravity",
        )
        self.gravity_steps=(
            _strict_int(self.gravity_steps, "Analysis gravity steps")
            if self.preload_gravity
            else int(self.gravity_steps)
        )
        raw_deferred_pattern_tags = list(self.deferred_pattern_tags)
        self.num_modes=(
            _strict_int(self.num_modes, "Analysis number of modes")
            if self.analysis_type == "Modal"
            else int(self.num_modes)
        )
        self.eigen_solver=str(self.eigen_solver)
        self.recovery=_strict_bool(
            self.recovery,
            "Analysis recovery",
        )
        self.adaptive_step=_strict_bool(
            self.adaptive_step,
            "Analysis adaptive_step",
        )
        self.adaptive_cutback_factor=float(self.adaptive_cutback_factor)
        self.adaptive_min_factor=float(self.adaptive_min_factor)
        self.adaptive_growth_factor=float(self.adaptive_growth_factor)
        uses_adaptive_integer_settings = (
            self.adaptive_step
            and self.analysis_type not in {"Modal", "Response Spectrum"}
        )
        self.adaptive_easy_iterations = (
            _strict_int(
                self.adaptive_easy_iterations,
                "Analysis adaptive easy iterations",
            )
            if uses_adaptive_integer_settings
            else int(self.adaptive_easy_iterations)
        )
        self.adaptive_growth_after = (
            _strict_int(
                self.adaptive_growth_after,
                "Analysis adaptive growth after",
            )
            if uses_adaptive_integer_settings
            else int(self.adaptive_growth_after)
        )
        self.live_convergence=_strict_bool(
            self.live_convergence,
            "Analysis live_convergence",
        )
        self.show_external_console=_strict_bool(
            self.show_external_console,
            "Analysis show_external_console",
        )
        self.algorithm_initial=_strict_bool(
            self.algorithm_initial,
            "Analysis algorithm_initial",
        )
        self.system_pivoting=_strict_bool(
            self.system_pivoting,
            "Analysis system_pivoting",
        )
        self.gravity_algorithm=str(self.gravity_algorithm or "Auto")
        self.rayleigh_model=str(self.rayleigh_model or "TwoMode")
        self.rayleigh_alpha_m=float(self.rayleigh_alpha_m)
        self.rayleigh_beta_k=float(self.rayleigh_beta_k)
        self.rayleigh_beta_k_init=float(self.rayleigh_beta_k_init)
        self.rayleigh_beta_k_comm=float(self.rayleigh_beta_k_comm)
        self.response_spectrum_mode = str(
            self.response_spectrum_mode or "Bidirectional / RotD"
        )
        self.response_spectrum_damping_ratio = float(
            self.response_spectrum_damping_ratio
        )
        self.response_spectrum_t1_step = float(self.response_spectrum_t1_step)
        self.response_spectrum_t1_end = float(self.response_spectrum_t1_end)
        self.response_spectrum_t2_step = float(self.response_spectrum_t2_step)
        self.response_spectrum_t2_end = float(self.response_spectrum_t2_end)
        self.response_spectrum_t3_step = float(self.response_spectrum_t3_step)
        self.response_spectrum_t3_end = float(self.response_spectrum_t3_end)
        self.response_spectrum_component_x = _strict_bool(
            self.response_spectrum_component_x,
            "Response spectrum component X output",
        )
        self.response_spectrum_component_y = _strict_bool(
            self.response_spectrum_component_y,
            "Response spectrum component Y output",
        )
        self.response_spectrum_rotd50 = _strict_bool(
            self.response_spectrum_rotd50,
            "Response spectrum RotD50 output",
        )
        self.response_spectrum_rotd100 = _strict_bool(
            self.response_spectrum_rotd100,
            "Response spectrum RotD100 output",
        )
        self.execution_mode = str(self.execution_mode or "Auto")
        self.num_threads = _strict_int(
            self.num_threads,
            "Analysis number of threads",
        )
        numeric_values = (
            self.tolerance,
            self.load_increment,
            self.displacement_increment,
            self.cyclic_increment,
            self.dt,
            self.gamma,
            self.beta,
            self.hht_alpha,
            self.generalized_alpha_m,
            self.generalized_alpha_f,
            self.arc_length_s,
            self.arc_length_alpha,
            self.rayleigh_damping_ratio,
            self.rayleigh_alpha_m,
            self.rayleigh_beta_k,
            self.rayleigh_beta_k_init,
            self.rayleigh_beta_k_comm,
            self.response_spectrum_damping_ratio,
            self.response_spectrum_t1_step,
            self.response_spectrum_t1_end,
            self.response_spectrum_t2_step,
            self.response_spectrum_t2_end,
            self.response_spectrum_t3_step,
            self.response_spectrum_t3_end,
            self.adaptive_cutback_factor,
            self.adaptive_min_factor,
            self.adaptive_growth_factor,
            *self.cyclic_targets,
        )
        if any(not math.isfinite(value) for value in numeric_values):
            raise ValueError("Analysis numeric settings must be finite.")
        if self.tag<=0: raise ValueError("Analysis tag must be positive.")
        if self.execution_mode not in {
            "Auto",
            "Single Thread",
            "Multi-thread",
        }:
            raise ValueError(
                "Execution mode must be Auto, Single Thread, or Multi-thread."
            )
        if self.num_threads < 1:
            raise ValueError("Analysis number of threads must be at least 1.")
        if self.execution_mode == "Single Thread":
            self.num_threads = 1
        if self.analysis_type not in {"Static","Pushover","Cyclic","Transient","Modal","Response Spectrum"}:
            raise ValueError(f"Unsupported analysis type: {self.analysis_type}")
        default_integrators = {
            "Static": "LoadControl",
            "Pushover": "DisplacementControl",
            "Cyclic": "DisplacementControl",
            "Transient": "Newmark",
            "Modal": "None",
            "Response Spectrum": "None",
        }
        if self.integrator in {"", "Auto"}:
            self.integrator = default_integrators[self.analysis_type]
        allowed_integrators = {
            "Static": {"LoadControl", "DisplacementControl", "ArcLength"},
            "Pushover": {"DisplacementControl"},
            "Cyclic": {"DisplacementControl"},
            "Transient": {"Newmark", "HHT", "GeneralizedAlpha"},
            "Modal": {"None"},
            "Response Spectrum": {"None"},
        }
        if self.integrator not in allowed_integrators[self.analysis_type]:
            raise ValueError(
                f"Integrator {self.integrator!r} is not valid for "
                f"{self.analysis_type} analysis."
            )

        uses_control_node = (
            self.analysis_type in {"Pushover", "Cyclic"}
            or (
                self.analysis_type == "Static"
                and self.integrator == "DisplacementControl"
            )
        )
        self.control_node = (
            _strict_int(raw_control_node, "Analysis control node")
            if uses_control_node
            else int(raw_control_node)
        )
        self.control_dof = (
            _strict_int(raw_control_dof, "Analysis control DOF")
            if self.analysis_type not in {"Modal", "Response Spectrum"}
            else int(raw_control_dof)
        )

        uses_rayleigh_modes = (
            self.analysis_type == "Transient"
            and self.rayleigh_damping_ratio > 0.0
        )
        self.rayleigh_mode_i = (
            _strict_int(raw_rayleigh_mode_i, "Analysis Rayleigh mode i")
            if uses_rayleigh_modes
            else int(raw_rayleigh_mode_i)
        )
        self.rayleigh_mode_j = (
            _strict_int(raw_rayleigh_mode_j, "Analysis Rayleigh mode j")
            if uses_rayleigh_modes
            else int(raw_rayleigh_mode_j)
        )

        uses_deferred_patterns = (
            self.analysis_type in {"Transient", "Pushover", "Cyclic", "Response Spectrum"}
            or (
                self.analysis_type == "Static"
                and self.integrator == "DisplacementControl"
            )
        )
        self.deferred_pattern_tags = list(dict.fromkeys(
            (
                _strict_int(tag, "Deferred load-pattern tag")
                if uses_deferred_patterns
                else int(tag)
            )
            for tag in raw_deferred_pattern_tags
        ))

        if self.constraints_handler not in {"Transformation","Plain"}:
            raise ValueError("Unsupported constraints handler.")
        if self.numberer not in {"RCM","Plain"}: raise ValueError("Unsupported numberer.")
        if self.system not in {"UmfPack","BandGeneral","ProfileSPD","SparseGeneral"}: raise ValueError("Unsupported system.")
        if self.system_pivoting and self.system != "SparseGeneral":
            raise ValueError(
                "System pivoting (-piv) is only supported for SparseGeneral."
            )
        uses_iterative_convergence = self.analysis_type not in {"Modal", "Response Spectrum"}
        if (
            uses_iterative_convergence
            and self.test not in {"NormDispIncr","NormUnbalance","EnergyIncr"}
        ):
            raise ValueError("Unsupported convergence test.")
        if self.gravity_algorithm not in {
            "Auto", "Linear", "Newton", "ModifiedNewton", "NewtonLineSearch"
        }:
            raise ValueError("Unsupported gravity preload algorithm.")
        if self.algorithm_initial and self.algorithm != "ModifiedNewton":
            raise ValueError(
                "Initial-tangent option is only valid for ModifiedNewton."
            )
        if (
            uses_iterative_convergence
            and self.algorithm not in {
                "Linear",
                "Newton",
                "ModifiedNewton",
                "NewtonLineSearch",
            }
        ):
            raise ValueError("Unsupported algorithm.")
        if (
            uses_iterative_convergence
            and (self.tolerance <= 0 or self.max_iterations < 1)
        ):
            raise ValueError("Invalid convergence settings.")
        if (
            self.analysis_type in {"Static", "Pushover", "Transient"}
            and self.steps < 1
        ):
            raise ValueError("Analysis steps must be at least 1.")
        if (
            self.analysis_type not in {"Modal", "Response Spectrum"}
            and self.control_dof not in range(1, 7)
        ):
            raise ValueError("Control DOF must be 1..6.")
        uses_adaptive_step = (
            self.adaptive_step
            and self.analysis_type not in {"Modal", "Response Spectrum"}
        )
        if (
            uses_adaptive_step
            and (
                self.adaptive_cutback_factor <= 0.0
                or self.adaptive_cutback_factor >= 1.0
            )
        ):
            raise ValueError("Adaptive cutback factor must be between 0 and 1.")
        if (
            uses_adaptive_step
            and (
                self.adaptive_min_factor <= 0.0
                or self.adaptive_min_factor > 1.0
            )
        ):
            raise ValueError("Adaptive minimum factor must be in (0, 1].")
        if uses_adaptive_step and self.adaptive_growth_factor < 1.0:
            raise ValueError("Adaptive growth factor must be at least 1.")
        if uses_adaptive_step and self.adaptive_easy_iterations < 1:
            raise ValueError("Adaptive easy-iteration threshold must be positive.")
        if uses_adaptive_step and self.adaptive_growth_after < 1:
            raise ValueError("Adaptive growth-after count must be positive.")
        if (
            self.analysis_type == "Static"
            and self.integrator == "LoadControl"
            and abs(self.load_increment) <= 1.0e-30
        ):
            raise ValueError("Static LoadControl needs a nonzero load increment.")
        if (
            self.analysis_type == "Static"
            and self.integrator == "DisplacementControl"
            and abs(self.displacement_increment) <= 1.0e-30
        ):
            raise ValueError(
                "Static DisplacementControl needs a nonzero "
                "displacement increment."
            )
        uses_arc_length = (
            self.analysis_type == "Static"
            and self.integrator == "ArcLength"
        )
        if uses_arc_length and self.arc_length_s <= 0.0:
            raise ValueError("ArcLength s must be positive.")
        if uses_arc_length and self.arc_length_alpha <= 0.0:
            raise ValueError("ArcLength alpha must be positive.")
        if self.analysis_type == "Pushover" and abs(self.displacement_increment) <= 1.0e-30:
            raise ValueError("Pushover needs a nonzero displacement increment.")
        if self.analysis_type == "Cyclic":
            if not self.cyclic_targets:
                raise ValueError("Cyclic analysis needs at least one displacement target.")
            if self.cyclic_increment <= 0.0:
                raise ValueError("Cyclic max displacement increment must be positive.")
        if self.analysis_type == "Transient" and self.dt <= 0:
            raise ValueError("Transient dt must be positive.")
        if (
            self.analysis_type == "Transient"
            and self.integrator == "Newmark"
            and self.beta <= 0.0
        ):
            raise ValueError(
                "Newmark beta must be positive for the default displacement-form "
                "integrator used by OpenSeesPy Studio."
            )
        if (
            self.analysis_type == "Transient"
            and self.integrator == "Newmark"
            and self.gamma < 0.5
        ):
            raise ValueError(
                "Newmark gamma must be at least 0.5; gamma below 0.5 is outside "
                "the standard stable range documented by OpenSees."
            )
        if (
            self.analysis_type == "Transient"
            and self.integrator == "HHT"
            and not (2.0 / 3.0 <= self.hht_alpha <= 1.0)
        ):
            raise ValueError("HHT alpha must be between 2/3 and 1.0.")
        if (
            self.analysis_type == "Transient"
            and self.integrator == "GeneralizedAlpha"
            and not (
                self.generalized_alpha_f >= 0.5
                and self.generalized_alpha_m >= self.generalized_alpha_f
            )
        ):
            raise ValueError(
                "GeneralizedAlpha requires alphaM >= alphaF >= 0.5 "
                "for the documented unconditionally stable default scheme."
            )
        if (
            self.analysis_type == "Transient"
            and not 0.0 <= self.rayleigh_damping_ratio < 1.0
        ):
            raise ValueError("Rayleigh damping ratio must be in [0, 1).")
        if self.rayleigh_model not in {
            "TwoMode",
            "SingleModeCommittedStiffness",
            "DirectCoefficients",
        }:
            raise ValueError("Unsupported Rayleigh damping model.")
        if (
            self.analysis_type == "Transient"
            and self.rayleigh_damping_ratio > 0.0
            and self.rayleigh_model == "TwoMode"
            and (self.rayleigh_mode_i < 1 or self.rayleigh_mode_j < 1)
        ):
            raise ValueError("Rayleigh damping modes must be positive.")
        if (
            self.analysis_type == "Transient"
            and self.rayleigh_damping_ratio > 0.0
            and self.rayleigh_model == "SingleModeCommittedStiffness"
            and self.rayleigh_mode_i < 1
        ):
            raise ValueError("Rayleigh damping mode i must be positive.")
        if (
            self.analysis_type == "Transient"
            and self.rayleigh_damping_ratio > 0.0
            and self.rayleigh_model == "TwoMode"
            and self.rayleigh_mode_i == self.rayleigh_mode_j
        ):
            raise ValueError("Two-mode Rayleigh damping needs two different modes.")
        if self.preload_gravity and self.gravity_steps < 1:
            raise ValueError("Gravity preload steps must be at least 1.")
        if (
            uses_deferred_patterns
            and any(tag <= 0 for tag in self.deferred_pattern_tags)
        ):
            raise ValueError("Deferred load-pattern tags must be positive.")
        if self.analysis_type == "Response Spectrum":
            if self.response_spectrum_mode not in {
                "Single Component",
                "Bidirectional / RotD",
            }:
                raise ValueError("Unsupported response-spectrum mode.")
            required_sources = (
                1
                if self.response_spectrum_mode == "Single Component"
                else 2
            )
            if len(self.deferred_pattern_tags) != required_sources:
                raise ValueError(
                    "Response Spectrum "
                    + self.response_spectrum_mode
                    + f" needs exactly {required_sources} UniformExcitation "
                    "pattern tag(s)."
                )
            if not 0.0 <= self.response_spectrum_damping_ratio < 1.0:
                raise ValueError(
                    "Response-spectrum damping ratio must be in [0, 1)."
                )
            if (
                self.response_spectrum_t1_step <= 0.0
                or self.response_spectrum_t2_step <= 0.0
                or self.response_spectrum_t3_step <= 0.0
            ):
                raise ValueError(
                    "Response-spectrum period intervals must be positive."
                )
            if not (
                0.0 < self.response_spectrum_t1_end
                <= self.response_spectrum_t2_end
                <= self.response_spectrum_t3_end
            ):
                raise ValueError(
                    "Response-spectrum region ends must be positive and "
                    "non-decreasing."
                )
            if not any((
                self.response_spectrum_component_x,
                self.response_spectrum_component_y,
                self.response_spectrum_rotd50,
                self.response_spectrum_rotd100,
            )):
                raise ValueError(
                    "Response Spectrum needs at least one requested output."
                )
            if (
                self.response_spectrum_mode == "Single Component"
                and (
                    self.response_spectrum_component_y
                    or self.response_spectrum_rotd50
                    or self.response_spectrum_rotd100
                )
            ):
                raise ValueError(
                    "Single Component response spectrum only supports "
                    "Component X output."
                )

        if self.analysis_type == "Modal" and self.num_modes < 1:
            raise ValueError("Number of modes must be at least 1.")
        uses_eigen_solver = (
            self.analysis_type == "Modal"
            or (
                self.analysis_type == "Transient"
                and self.rayleigh_damping_ratio > 0.0
                and self.rayleigh_model != "DirectCoefficients"
            )
        )
        if uses_eigen_solver and self.eigen_solver not in {
            "-genBandArpack",
            "-fullGenLapack",
            "-symmBandLapack",
        }:
            raise ValueError("Unsupported eigen solver.")

    def to_dict(self) -> dict[str, Any]:
        return {key:getattr(self,key) for key in (
            "tag","name","analysis_type","constraints_handler","numberer","system",
            "test","tolerance","max_iterations","algorithm","integrator",
            "steps","load_increment","control_node","control_dof",
            "displacement_increment","cyclic_targets","cyclic_increment",
            "dt","gamma","beta","hht_alpha","generalized_alpha_m",
            "generalized_alpha_f","arc_length_s","arc_length_alpha",
            "rayleigh_damping_ratio","rayleigh_mode_i","rayleigh_mode_j",
            "preload_gravity","gravity_steps","deferred_pattern_tags",
            "num_modes","eigen_solver","recovery","adaptive_step",
            "adaptive_cutback_factor","adaptive_min_factor",
            "adaptive_growth_factor","adaptive_easy_iterations",
            "adaptive_growth_after","live_convergence","show_external_console",
            "algorithm_initial","system_pivoting","gravity_algorithm",
            "rayleigh_model","rayleigh_alpha_m","rayleigh_beta_k",
            "rayleigh_beta_k_init","rayleigh_beta_k_comm",
            "response_spectrum_mode","response_spectrum_damping_ratio",
            "response_spectrum_t1_step","response_spectrum_t1_end",
            "response_spectrum_t2_step","response_spectrum_t2_end",
            "response_spectrum_t3_step","response_spectrum_t3_end",
            "response_spectrum_component_x","response_spectrum_component_y",
            "response_spectrum_rotd50","response_spectrum_rotd100",
            "execution_mode","num_threads"
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
    fiber_index: int | None = None

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Recorder tag")
        self.name = str(self.name).strip() or f"Recorder {self.tag}"
        self.recorder_type = str(self.recorder_type)
        self.target_tags = sorted({
            _strict_int(tag, "Recorder target tag")
            for tag in self.target_tags
        })
        self.response = str(self.response)
        self.dofs = sorted({
            _strict_int(dof, "Recorder DOF")
            for dof in self.dofs
        })
        self.file_name = str(self.file_name).strip()
        self.include_time = _strict_bool(
            self.include_time,
            "Recorder include_time",
        )
        if self.recorder_type in {"Section", "Fiber", "Shell"}:
            self.section_number = _strict_int(
                self.section_number,
                "Recorder section number",
            )
        else:
            self.section_number = int(self.section_number)
        self.fiber_y = float(self.fiber_y)
        self.fiber_z = float(self.fiber_z)
        if self.recorder_type == "Fiber" and self.material_tag is not None:
            self.material_tag = _strict_int(
                self.material_tag,
                "Recorder material tag",
            )
        elif self.material_tag is not None:
            self.material_tag = int(self.material_tag)

        if self.recorder_type == "Fiber" and self.fiber_index is not None:
            self.fiber_index = _strict_int(
                self.fiber_index,
                "Recorder fiber index",
            )
        elif self.fiber_index is not None:
            self.fiber_index = int(self.fiber_index)
        if self.tag <= 0:
            raise ValueError("Recorder tag must be positive.")
        if not math.isfinite(self.fiber_y) or not math.isfinite(self.fiber_z):
            raise ValueError("Recorder fiber coordinates must be finite.")
        if self.recorder_type not in {
            "Node", "Element", "Section", "Fiber", "Shell"
        }:
            raise ValueError(f"Unsupported recorder type: {self.recorder_type}")
        if not self.target_tags:
            raise ValueError("Recorder must target at least one node or element.")
        if self.recorder_type == "Node":
            if any(tag < 0 for tag in self.target_tags):
                raise ValueError(
                    "Node recorder target tags must be non-negative."
                )
        elif any(tag <= 0 for tag in self.target_tags):
            raise ValueError("Recorder target tags must be positive.")
        if not self.file_name:
            self.file_name = f"recorders/recorder_{self.tag}.out"
        if self.recorder_type == "Node":
            if self.response not in {"disp", "vel", "accel", "reaction"}:
                raise ValueError("Unsupported Node recorder response.")
            if not self.dofs or any(dof not in range(1, 7) for dof in self.dofs):
                raise ValueError("Node recorder DOFs must be in 1..6.")
        elif self.recorder_type == "Element":
            if self.response not in {
                "globalForce",
                "localForce",
                "force",
                "deformation",
                "basicForce",
                "basicForces",
                "Deformation",
                "localDisplacement",
                "basicDisplacement",
                "stiff",
                "centralNode",
                "size",
                "stiffness",
                "defoANDforce",
                "internalDisplacement",
                "externalDisplacement",
                "node1BarSlipL",
                "node1BarSlipR",
                "node1InterfaceShear",
                "node2BarSlipB",
                "node2BarSlipT",
                "node2InterfaceShear",
                "node3BarSlipL",
                "node3BarSlipR",
                "node3InterfaceShear",
                "node4BarSlipB",
                "node4BarSlipT",
                "node4InterfaceShear",
                "shearPanel",
            }:
                raise ValueError("Unsupported Element recorder response.")
        elif self.recorder_type == "Section":
            if self.response not in {"force", "deformation"}:
                raise ValueError("Unsupported Section recorder response.")
            if self.section_number < 1:
                raise ValueError("Section recorder number must be at least 1.")
        elif self.recorder_type == "Shell":
            if self.response not in {"force", "deformation"}:
                raise ValueError("Unsupported Shell recorder response.")
            if self.section_number not in range(1, 5):
                raise ValueError(
                    "Shell recorder Gauss point must be in 1..4."
                )
        elif self.recorder_type == "Fiber":
            if self.response not in {"stress", "strain", "stressStrain"}:
                raise ValueError("Unsupported Fiber recorder response.")
            if self.section_number < 1:
                raise ValueError("Fiber recorder section number must be at least 1.")
            if self.material_tag is not None and self.material_tag <= 0:
                raise ValueError("Fiber recorder material tag must be positive.")
            if self.fiber_index is not None and self.fiber_index < 0:
                raise ValueError("Fiber recorder index must be zero or positive.")

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
            "fiber_index": self.fiber_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecorderData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", f"Recorder {data['tag']}")),
            recorder_type=str(data.get("recorder_type", "Node")),
            target_tags=list(data.get("target_tags", [])),
            response=str(data.get("response", "disp")),
            dofs=list(data.get("dofs", [1])),
            file_name=str(data.get("file_name", "")),
            include_time=data.get("include_time", True),
            section_number=data.get("section_number", 1),
            fiber_y=float(data.get("fiber_y", 0.0)),
            fiber_z=float(data.get("fiber_z", 0.0)),
            material_tag=data.get("material_tag"),
            fiber_index=data.get("fiber_index"),
        )


SOLUTION_RESULT_TYPES = {
    "DeformedShape",
    "NodalDisplacement",
    "NodalReaction",
    "MemberForce",
    "ShellForce",
    "ShellDeformation",
    "ShellDisplacement",
    "CrackPattern",
    "FiberStress",
    "FiberStrain",
    "HingeState",
    "ForceDisplacement",
    "PushoverCurve",
    "CyclicHysteresis",
    "TimeHistory",
    "ModeShape",
    "Motion",
    "Convergence",
    "SpecimenResponse",
    "MomentCurvature",
    "SectionResponse",
    "JointResponse",
    "ResponseSpectrum",
}


@dataclass
class SolutionResultData:
    tag: int
    analysis_tag: int
    name: str
    result_type: str
    node_scope: list[int] = field(default_factory=list)
    element_scope: list[int] = field(default_factory=list)
    surface_scope: list[int] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Solution result tag")
        self.analysis_tag = _strict_int(
            self.analysis_tag,
            "Solution result analysis tag",
        )
        self.name = str(self.name).strip() or f"Result {self.tag}"
        self.result_type = str(self.result_type)
        self.node_scope = sorted({
            _strict_int(tag, "Solution result node tag")
            for tag in self.node_scope
        })
        self.element_scope = sorted({
            _strict_int(tag, "Solution result element tag")
            for tag in self.element_scope
        })
        self.surface_scope = sorted({
            _strict_int(tag, "Solution result Surface tag")
            for tag in self.surface_scope
        })
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
            "surface_scope": list(self.surface_scope),
            "settings": dict(self.settings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SolutionResultData":
        return cls(
            tag=data["tag"],
            analysis_tag=data["analysis_tag"],
            name=str(data.get("name", "")),
            result_type=str(data["result_type"]),
            node_scope=list(data.get("node_scope", [])),
            element_scope=list(data.get("element_scope", [])),
            surface_scope=list(data.get("surface_scope", [])),
            settings=dict(data.get("settings", {})),
        )


@dataclass
class SketchPlaneData:
    """Persistent construction/sketch plane defined by an orthonormal basis."""

    tag: int
    name: str
    origin: Vec3 = (0.0, 0.0, 0.0)
    u_axis: Vec3 = (1.0, 0.0, 0.0)
    v_axis: Vec3 = (0.0, 1.0, 0.0)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Sketch Plane tag")
        if self.tag <= 0:
            raise ValueError("Sketch Plane tag must be positive.")
        self.name = str(self.name).strip() or f"Plane {self.tag}"

        def vector(value, label: str) -> tuple[float, float, float]:
            if len(value) != 3:
                raise ValueError(f"{label} requires three components.")
            result = tuple(float(item) for item in value)
            if any(not math.isfinite(item) for item in result):
                raise ValueError(f"{label} components must be finite.")
            return result  # type: ignore[return-value]

        def norm(value) -> float:
            return math.sqrt(sum(float(item) ** 2 for item in value))

        self.origin = vector(self.origin, "Sketch Plane origin")
        raw_u = vector(self.u_axis, "Sketch Plane U axis")
        raw_v = vector(self.v_axis, "Sketch Plane V axis")
        u_norm = norm(raw_u)
        if u_norm <= 1.0e-12:
            raise ValueError("Sketch Plane U axis cannot be zero.")
        u = tuple(item / u_norm for item in raw_u)
        projection = sum(raw_v[index] * u[index] for index in range(3))
        v_orth = tuple(
            raw_v[index] - projection * u[index]
            for index in range(3)
        )
        v_norm = norm(v_orth)
        if v_norm <= 1.0e-12:
            raise ValueError(
                "Sketch Plane U and V axes must not be parallel."
            )
        v = tuple(item / v_norm for item in v_orth)
        self.u_axis = u  # type: ignore[assignment]
        self.v_axis = v  # type: ignore[assignment]

    @property
    def normal(self) -> Vec3:
        u = self.u_axis
        v = self.v_axis
        return (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )

    def world_from_uv(self, u: float, v: float) -> Vec3:
        uu = float(u)
        vv = float(v)
        if not math.isfinite(uu) or not math.isfinite(vv):
            raise ValueError("Sketch Plane local coordinates must be finite.")
        return tuple(
            self.origin[index]
            + uu * self.u_axis[index]
            + vv * self.v_axis[index]
            for index in range(3)
        )  # type: ignore[return-value]

    def uv_from_world(self, xyz) -> tuple[float, float]:
        point = tuple(float(value) for value in xyz)
        if len(point) != 3 or any(not math.isfinite(value) for value in point):
            raise ValueError("Sketch Plane world point must be finite XYZ.")
        delta = tuple(
            point[index] - self.origin[index]
            for index in range(3)
        )
        return (
            sum(delta[index] * self.u_axis[index] for index in range(3)),
            sum(delta[index] * self.v_axis[index] for index in range(3)),
        )

    def signed_distance(self, xyz) -> float:
        point = tuple(float(value) for value in xyz)
        if len(point) != 3 or any(not math.isfinite(value) for value in point):
            raise ValueError("Sketch Plane world point must be finite XYZ.")
        normal = self.normal
        return sum(
            (point[index] - self.origin[index]) * normal[index]
            for index in range(3)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "origin": list(self.origin),
            "u_axis": list(self.u_axis),
            "v_axis": list(self.v_axis),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SketchPlaneData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            origin=tuple(data.get("origin", (0.0, 0.0, 0.0))),
            u_axis=tuple(data.get("u_axis", (1.0, 0.0, 0.0))),
            v_axis=tuple(data.get("v_axis", (0.0, 1.0, 0.0))),
        )


@dataclass
class PointGeometryData:
    tag: int
    name: str
    xyz: Vec3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Geometry Point tag")
        if self.tag <= 0:
            raise ValueError("Geometry Point tag must be positive.")
        self.name = str(self.name).strip() or f"Point {self.tag}"
        if len(self.xyz) != 3:
            raise ValueError("Geometry Point requires X, Y, Z coordinates.")
        self.xyz = tuple(float(value) for value in self.xyz)
        if any(not math.isfinite(value) for value in self.xyz):
            raise ValueError("Geometry Point coordinates must be finite.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "xyz": list(self.xyz),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PointGeometryData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            xyz=tuple(data.get("xyz", (0.0, 0.0, 0.0))),
        )


@dataclass
class LineGeometryData:
    tag: int
    name: str
    point_i: int
    point_j: int
    mesh_recipe_configured: bool = True
    mesh_mode: str = "divisions"
    divisions: int = 1
    target_size: float | None = None
    bias: float = 1.0
    reuse_existing_nodes: bool = True
    element_family: str = "Frame"
    element_type: str = "elasticBeamColumn"
    section_tag: int | None = None
    transformation_tag: int | None = None
    material_tag: int | None = None
    area: float = 1.0
    integration_type: str = "Lobatto"
    integration_points: int = 5
    mass_per_length: float = 0.0
    consistent_mass: bool = False
    center_rotation: float = 0.4
    do_rayleigh: bool = False
    generated_node_tags: list[int] = field(default_factory=list)
    owned_node_tags: list[int] = field(default_factory=list)
    generated_element_tags: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Geometry Line tag")
        if self.tag <= 0:
            raise ValueError("Geometry Line tag must be positive.")
        self.name = str(self.name).strip() or f"Line {self.tag}"
        self.point_i = _strict_int(self.point_i, "Geometry Line start Point")
        self.point_j = _strict_int(self.point_j, "Geometry Line end Point")
        if self.point_i == self.point_j:
            raise ValueError("Geometry Line requires two different Points.")

        self.mesh_recipe_configured = _strict_bool(
            self.mesh_recipe_configured,
            "Line mesh recipe configured",
        )
        self.mesh_mode = str(self.mesh_mode)
        if self.mesh_mode not in {"divisions", "target_size"}:
            raise ValueError(
                "Line mesh mode must be 'divisions' or 'target_size'."
            )
        self.divisions = _strict_int(self.divisions, "Line mesh divisions")
        if not 1 <= self.divisions <= 10_000:
            raise ValueError("Line mesh divisions must be in 1..10000.")
        if self.target_size is not None:
            self.target_size = float(self.target_size)
            if (
                not math.isfinite(self.target_size)
                or self.target_size <= 0.0
            ):
                raise ValueError(
                    "Line target element size must be finite and positive."
                )
        self.bias = float(self.bias)
        if not math.isfinite(self.bias) or self.bias <= 0.0:
            raise ValueError(
                "Line mesh bias must be finite and positive."
            )

        self.reuse_existing_nodes = _strict_bool(
            self.reuse_existing_nodes,
            "Line reuse existing nodes",
        )
        self.element_family = str(self.element_family)
        if self.element_family not in {"Frame", "Truss"}:
            raise ValueError("Line FE family must be Frame or Truss.")
        self.element_type = str(self.element_type)
        if self.element_family == "Frame":
            if self.element_type not in FRAME_ELEMENT_TYPES:
                raise ValueError(
                    f"Unsupported Frame formulation: {self.element_type}"
                )
        else:
            self.element_type = "truss"

        for attribute, label in (
            ("section_tag", "Line Section tag"),
            ("transformation_tag", "Line Transformation tag"),
            ("material_tag", "Line Material tag"),
        ):
            value = getattr(self, attribute)
            if value is not None:
                value = _strict_int(value, label)
                if value <= 0:
                    raise ValueError(f"{label} must be positive.")
                setattr(self, attribute, value)

        self.area = float(self.area)
        if not math.isfinite(self.area) or self.area <= 0.0:
            raise ValueError("Line Truss area must be finite and positive.")
        self.integration_type = str(self.integration_type)
        self.integration_points = _strict_int(
            self.integration_points,
            "Line integration points",
        )
        minimum_points = (
            1 if self.element_type == "dispBeamColumnInt" else 2
        )
        if not minimum_points <= self.integration_points <= 20:
            raise ValueError(
                "Line integration points must be in "
                f"{minimum_points}..20 for {self.element_type}."
            )
        self.mass_per_length = float(self.mass_per_length)
        if (
            not math.isfinite(self.mass_per_length)
            or self.mass_per_length < 0.0
        ):
            raise ValueError(
                "Line mass per length must be finite and nonnegative."
            )
        self.consistent_mass = _strict_bool(
            self.consistent_mass,
            "Line consistent mass",
        )
        self.center_rotation = float(self.center_rotation)
        if (
            not math.isfinite(self.center_rotation)
            or not 0.0 <= self.center_rotation <= 1.0
        ):
            raise ValueError(
                "Line dispBeamColumnInt cRot must satisfy 0 <= cRot <= 1."
            )
        if self.element_type == "dispBeamColumnInt":
            self.consistent_mass = False
        self.do_rayleigh = _strict_bool(
            self.do_rayleigh,
            "Line Rayleigh flag",
        )
        ordered_generated_nodes: list[int] = []
        seen_generated_nodes: set[int] = set()
        for tag in self.generated_node_tags:
            node_tag = _strict_int(tag, "Line generated node tag")
            if node_tag in seen_generated_nodes:
                continue
            seen_generated_nodes.add(node_tag)
            ordered_generated_nodes.append(node_tag)
        self.generated_node_tags = ordered_generated_nodes
        self.owned_node_tags = sorted({
            _strict_int(tag, "Line owned node tag")
            for tag in (
                self.owned_node_tags
                if self.owned_node_tags
                else self.generated_node_tags
            )
        })
        self.generated_element_tags = sorted({
            _strict_int(tag, "Line generated element tag")
            for tag in self.generated_element_tags
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "point_i": self.point_i,
            "point_j": self.point_j,
            "mesh_recipe_configured": self.mesh_recipe_configured,
            "mesh_mode": self.mesh_mode,
            "divisions": self.divisions,
            "target_size": self.target_size,
            "bias": self.bias,
            "reuse_existing_nodes": self.reuse_existing_nodes,
            "element_family": self.element_family,
            "element_type": self.element_type,
            "section_tag": self.section_tag,
            "transformation_tag": self.transformation_tag,
            "material_tag": self.material_tag,
            "area": self.area,
            "integration_type": self.integration_type,
            "integration_points": self.integration_points,
            "mass_per_length": self.mass_per_length,
            "consistent_mass": self.consistent_mass,
            "center_rotation": self.center_rotation,
            "do_rayleigh": self.do_rayleigh,
            "generated_node_tags": list(self.generated_node_tags),
            "owned_node_tags": list(self.owned_node_tags),
            "generated_element_tags": list(self.generated_element_tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineGeometryData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            point_i=data["point_i"],
            point_j=data["point_j"],
            mesh_recipe_configured=data.get("mesh_recipe_configured", True),
            mesh_mode=str(data.get("mesh_mode", "divisions")),
            divisions=data.get("divisions", 1),
            target_size=data.get("target_size"),
            bias=data.get("bias", 1.0),
            reuse_existing_nodes=data.get("reuse_existing_nodes", True),
            element_family=str(data.get("element_family", "Frame")),
            element_type=str(
                data.get("element_type", "elasticBeamColumn")
            ),
            section_tag=data.get("section_tag"),
            transformation_tag=data.get("transformation_tag"),
            material_tag=data.get("material_tag"),
            area=data.get("area", 1.0),
            integration_type=str(data.get("integration_type", "Lobatto")),
            integration_points=data.get("integration_points", 5),
            mass_per_length=data.get("mass_per_length", 0.0),
            consistent_mass=data.get("consistent_mass", False),
            center_rotation=data.get("center_rotation", 0.4),
            do_rayleigh=data.get("do_rayleigh", False),
            generated_node_tags=list(data.get("generated_node_tags", [])),
            owned_node_tags=list(
                data.get(
                    "owned_node_tags",
                    data.get("generated_node_tags", []),
                )
            ),
            generated_element_tags=list(
                data.get("generated_element_tags", [])
            ),
        )


@dataclass
class SurfaceGeometryData:
    tag: int
    name: str
    surface_type: str = "Quad"
    points: tuple[Vec3, Vec3, Vec3, Vec3] = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    mesh_recipe_configured: bool = True
    section_tag: int | None = None
    formulation: str = "ASDShellQ4"
    corner_point_tags: tuple[int, int, int, int] | None = None
    corotational: bool = False
    local_x: tuple[float, float, float] | None = None
    no_eas: bool = False
    drilling_stab: float | None = None
    drilling_nl: bool = False
    mesh_mode: str = "divisions"
    divisions_u: int = 4
    divisions_v: int = 4
    target_size: float | None = None
    bias_u: float = 1.0
    bias_v: float = 1.0
    edge_divisions: tuple[
        int | None,
        int | None,
        int | None,
        int | None,
    ] | None = None
    reuse_existing_nodes: bool = True
    conform_existing_edges: bool = True
    generated_node_tags: list[int] = field(default_factory=list)
    generated_element_tags: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Surface geometry tag")
        if self.tag <= 0:
            raise ValueError("Surface geometry tag must be positive.")
        self.name = str(self.name).strip() or f"Surface {self.tag}"
        self.surface_type = str(self.surface_type)
        if self.surface_type not in {"Rectangle", "Quad"}:
            raise ValueError(
                f"Unsupported surface geometry type: {self.surface_type}"
            )
        if len(self.points) != 4:
            raise ValueError("Surface geometry requires four corner points.")
        normalized_points = []
        for index, point in enumerate(self.points, start=1):
            if len(point) != 3:
                raise ValueError(
                    f"Surface corner {index} requires X, Y, Z."
                )
            xyz = tuple(float(value) for value in point)
            if any(not math.isfinite(value) for value in xyz):
                raise ValueError(
                    f"Surface corner {index} coordinates must be finite."
                )
            normalized_points.append(xyz)
        self.points = tuple(normalized_points)  # type: ignore[assignment]
        self.mesh_recipe_configured = _strict_bool(
            self.mesh_recipe_configured,
            "Surface mesh recipe configured",
        )

        normal = [0.0, 0.0, 0.0]
        for index, current in enumerate(self.points):
            following = self.points[(index + 1) % 4]
            normal[0] += (
                (current[1] - following[1])
                * (current[2] + following[2])
            )
            normal[1] += (
                (current[2] - following[2])
                * (current[0] + following[0])
            )
            normal[2] += (
                (current[0] - following[0])
                * (current[1] + following[1])
            )
        if math.sqrt(sum(value * value for value in normal)) <= 1.0e-12:
            raise ValueError(
                "Surface geometry has zero or near-zero boundary area."
            )

        if self.section_tag is not None:
            self.section_tag = _strict_int(
                self.section_tag,
                "Surface geometry section tag",
            )
            if self.section_tag <= 0:
                raise ValueError(
                    "Surface geometry section tag must be positive."
                )

        self.formulation = str(self.formulation)
        if self.formulation not in SHELL_ELEMENT_TYPES:
            raise ValueError(
                f"Unsupported shell formulation: {self.formulation}"
            )

        if self.corner_point_tags is not None:
            if len(self.corner_point_tags) != 4:
                raise ValueError(
                    "Surface geometry topology requires four Point tags."
                )
            point_tags = tuple(
                _strict_int(tag, "Surface geometry Point tag")
                for tag in self.corner_point_tags
            )
            if any(tag <= 0 for tag in point_tags):
                raise ValueError(
                    "Surface geometry Point tags must be positive."
                )
            if len(set(point_tags)) != 4:
                raise ValueError(
                    "Surface geometry requires four distinct Point tags."
                )
            self.corner_point_tags = point_tags

        self.corotational = _strict_bool(
            self.corotational,
            "Surface shell corotational flag",
        )
        self.no_eas = _strict_bool(
            self.no_eas,
            "Surface shell no-EAS flag",
        )
        self.drilling_nl = _strict_bool(
            self.drilling_nl,
            "Surface shell nonlinear drilling flag",
        )
        if self.local_x is not None:
            local_x = tuple(float(value) for value in self.local_x)
            if len(local_x) != 3 or any(
                not math.isfinite(value) for value in local_x
            ):
                raise ValueError(
                    "Surface shell local X needs three finite values."
                )
            if sum(value * value for value in local_x) <= 1.0e-24:
                raise ValueError("Surface shell local X cannot be zero.")
            self.local_x = local_x
        if self.drilling_stab is not None:
            self.drilling_stab = float(self.drilling_stab)
            if (
                not math.isfinite(self.drilling_stab)
                or self.drilling_stab < 0.0
            ):
                raise ValueError(
                    "Surface drilling stabilization must be finite "
                    "and non-negative."
                )
        if self.formulation != "ASDShellQ4":
            self.corotational = False
            self.local_x = None
            self.no_eas = False
            self.drilling_stab = None
            self.drilling_nl = False

        self.mesh_mode = str(self.mesh_mode)
        if self.mesh_mode not in {"divisions", "target_size"}:
            raise ValueError(
                "Surface mesh mode must be 'divisions' or 'target_size'."
            )
        self.divisions_u = _strict_int(
            self.divisions_u,
            "Surface U divisions",
        )
        self.divisions_v = _strict_int(
            self.divisions_v,
            "Surface V divisions",
        )
        if not 1 <= self.divisions_u <= 500:
            raise ValueError("Surface U divisions must be in 1..500.")
        if not 1 <= self.divisions_v <= 500:
            raise ValueError("Surface V divisions must be in 1..500.")

        if self.target_size is not None:
            self.target_size = float(self.target_size)
            if (
                not math.isfinite(self.target_size)
                or self.target_size <= 0.0
            ):
                raise ValueError(
                    "Surface target mesh size must be finite and positive."
                )

        self.bias_u = float(self.bias_u)
        self.bias_v = float(self.bias_v)
        for value, label in (
            (self.bias_u, "Surface U mesh bias"),
            (self.bias_v, "Surface V mesh bias"),
        ):
            if (
                not math.isfinite(value)
                or value < 0.01
                or value > 100.0
            ):
                raise ValueError(
                    f"{label} must be finite and in 0.01..100."
                )

        if self.edge_divisions is not None:
            if len(self.edge_divisions) != 4:
                raise ValueError(
                    "Surface edge seeding requires four edge entries."
                )
            normalized_edges: list[int | None] = []
            for index, value in enumerate(
                self.edge_divisions,
                start=1,
            ):
                if value is None:
                    normalized_edges.append(None)
                    continue
                seed = _strict_int(
                    value,
                    f"Surface edge {index} divisions",
                )
                if not 1 <= seed <= 500:
                    raise ValueError(
                        f"Surface edge {index} divisions must be in 1..500."
                    )
                normalized_edges.append(seed)
            if (
                normalized_edges[0] is not None
                and normalized_edges[2] is not None
                and normalized_edges[0] != normalized_edges[2]
            ):
                raise ValueError(
                    "Mapped quad mesh requires equal divisions on "
                    "opposite edges 1 and 3."
                )
            if (
                normalized_edges[1] is not None
                and normalized_edges[3] is not None
                and normalized_edges[1] != normalized_edges[3]
            ):
                raise ValueError(
                    "Mapped quad mesh requires equal divisions on "
                    "opposite edges 2 and 4."
                )
            self.edge_divisions = tuple(normalized_edges)  # type: ignore[assignment]

        self.reuse_existing_nodes = _strict_bool(
            self.reuse_existing_nodes,
            "Surface reuse existing nodes",
        )
        self.conform_existing_edges = _strict_bool(
            self.conform_existing_edges,
            "Surface conform existing edges",
        )
        if self.conform_existing_edges and not self.reuse_existing_nodes:
            self.reuse_existing_nodes = True

        self.generated_node_tags = sorted({
            _strict_int(tag, "Surface generated node tag")
            for tag in self.generated_node_tags
        })
        self.generated_element_tags = sorted({
            _strict_int(tag, "Surface generated element tag")
            for tag in self.generated_element_tags
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "surface_type": self.surface_type,
            "points": [list(point) for point in self.points],
            "mesh_recipe_configured": self.mesh_recipe_configured,
            "section_tag": self.section_tag,
            "formulation": self.formulation,
            "corner_point_tags": (
                None
                if self.corner_point_tags is None
                else list(self.corner_point_tags)
            ),
            "corotational": self.corotational,
            "local_x": (
                None if self.local_x is None else list(self.local_x)
            ),
            "no_eas": self.no_eas,
            "drilling_stab": self.drilling_stab,
            "drilling_nl": self.drilling_nl,
            "mesh_mode": self.mesh_mode,
            "divisions_u": self.divisions_u,
            "divisions_v": self.divisions_v,
            "target_size": self.target_size,
            "bias_u": self.bias_u,
            "bias_v": self.bias_v,
            "edge_divisions": (
                None
                if self.edge_divisions is None
                else list(self.edge_divisions)
            ),
            "reuse_existing_nodes": self.reuse_existing_nodes,
            "conform_existing_edges": self.conform_existing_edges,
            "generated_node_tags": list(self.generated_node_tags),
            "generated_element_tags": list(self.generated_element_tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfaceGeometryData":
        points = tuple(
            tuple(float(value) for value in point)
            for point in data.get("points", [])
        )
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            surface_type=str(data.get("surface_type", "Quad")),
            points=points,  # type: ignore[arg-type]
            mesh_recipe_configured=data.get(
                "mesh_recipe_configured",
                True,
            ),
            section_tag=data.get("section_tag"),
            formulation=str(data.get("formulation", "ASDShellQ4")),
            corner_point_tags=(
                None
                if data.get("corner_point_tags") is None
                else tuple(data.get("corner_point_tags"))
            ),
            corotational=data.get("corotational", False),
            local_x=(
                None
                if data.get("local_x") is None
                else tuple(data.get("local_x"))
            ),
            no_eas=data.get("no_eas", False),
            drilling_stab=data.get("drilling_stab"),
            drilling_nl=data.get("drilling_nl", False),
            mesh_mode=str(data.get("mesh_mode", "divisions")),
            divisions_u=data.get("divisions_u", 4),
            divisions_v=data.get("divisions_v", 4),
            target_size=data.get("target_size"),
            bias_u=data.get("bias_u", 1.0),
            bias_v=data.get("bias_v", 1.0),
            edge_divisions=(
                None
                if data.get("edge_divisions") is None
                else tuple(data.get("edge_divisions"))
            ),
            reuse_existing_nodes=data.get("reuse_existing_nodes", True),
            conform_existing_edges=data.get("conform_existing_edges", True),
            generated_node_tags=list(data.get("generated_node_tags", [])),
            generated_element_tags=list(
                data.get("generated_element_tags", [])
            ),
        )


@dataclass
class SurfaceEdgeSupportData:
    tag: int
    name: str
    surface_tag: int
    edge_index: int
    fixity: tuple[int, int, int, int, int, int] = (1, 1, 1, 1, 1, 1)
    generated_node_tags: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Surface edge support tag")
        self.surface_tag = _strict_int(
            self.surface_tag,
            "Surface edge support Surface tag",
        )
        self.edge_index = _strict_int(
            self.edge_index,
            "Surface edge support edge index",
        )
        self.name = str(self.name).strip() or f"Surface Edge Support {self.tag}"
        if self.tag <= 0 or self.surface_tag <= 0:
            raise ValueError(
                "Surface edge support tag and Surface tag must be positive."
            )
        if self.edge_index not in {1, 2, 3, 4}:
            raise ValueError(
                "Surface edge support edge index must be 1, 2, 3, or 4."
            )
        values = tuple(
            _strict_int(value, "Surface edge support fixity value")
            for value in self.fixity
        )
        if len(values) != 6 or any(value not in {0, 1} for value in values):
            raise ValueError(
                "Surface edge support fixity must contain six 0/1 values."
            )
        if not any(values):
            raise ValueError(
                "Surface edge support must restrain at least one DOF."
            )
        self.fixity = values  # type: ignore[assignment]
        ordered_nodes: list[int] = []
        seen_nodes: set[int] = set()
        for tag in self.generated_node_tags:
            node_tag = _strict_int(
                tag,
                "Surface edge support generated node tag",
            )
            if node_tag in seen_nodes:
                continue
            seen_nodes.add(node_tag)
            ordered_nodes.append(node_tag)
        self.generated_node_tags = ordered_nodes

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "surface_tag": self.surface_tag,
            "edge_index": self.edge_index,
            "fixity": list(self.fixity),
            "generated_node_tags": list(self.generated_node_tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfaceEdgeSupportData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            surface_tag=data["surface_tag"],
            edge_index=data["edge_index"],
            fixity=tuple(data.get("fixity", (1, 1, 1, 1, 1, 1))),
            generated_node_tags=list(
                data.get("generated_node_tags", [])
            ),
        )


@dataclass
class SurfaceEdgeLoadData:
    tag: int
    name: str
    surface_tag: int
    edge_index: int
    pattern_tag: int
    values_per_length: tuple[
        float, float, float, float, float, float
    ] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    generated_nodal_load_tags: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Surface edge load tag")
        self.surface_tag = _strict_int(
            self.surface_tag,
            "Surface edge load Surface tag",
        )
        self.edge_index = _strict_int(
            self.edge_index,
            "Surface edge load edge index",
        )
        self.pattern_tag = _strict_int(
            self.pattern_tag,
            "Surface edge load pattern tag",
        )
        self.name = str(self.name).strip() or f"Surface Edge Load {self.tag}"
        if self.tag <= 0 or self.surface_tag <= 0 or self.pattern_tag <= 0:
            raise ValueError(
                "Surface edge load tag, Surface tag, and pattern tag "
                "must be positive."
            )
        if self.edge_index not in {1, 2, 3, 4}:
            raise ValueError(
                "Surface edge load edge index must be 1, 2, 3, or 4."
            )
        values = tuple(float(value) for value in self.values_per_length)
        if len(values) != 6:
            raise ValueError(
                "Surface edge line load requires six global line-resultant "
                "components."
            )
        if any(not math.isfinite(value) for value in values):
            raise ValueError(
                "Surface edge line load components must be finite."
            )
        if not any(abs(value) > 1.0e-15 for value in values):
            raise ValueError(
                "Surface edge line load requires at least one nonzero "
                "component."
            )
        self.values_per_length = values  # type: ignore[assignment]
        ordered: list[int] = []
        seen: set[int] = set()
        for tag in self.generated_nodal_load_tags:
            load_tag = _strict_int(
                tag,
                "Surface edge load generated nodal-load tag",
            )
            if load_tag in seen:
                continue
            seen.add(load_tag)
            ordered.append(load_tag)
        self.generated_nodal_load_tags = ordered

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "surface_tag": self.surface_tag,
            "edge_index": self.edge_index,
            "pattern_tag": self.pattern_tag,
            "values_per_length": list(self.values_per_length),
            "generated_nodal_load_tags": list(
                self.generated_nodal_load_tags
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfaceEdgeLoadData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            surface_tag=data["surface_tag"],
            edge_index=data["edge_index"],
            pattern_tag=data["pattern_tag"],
            values_per_length=tuple(
                data.get("values_per_length", (0.0,) * 6)
            ),
            generated_nodal_load_tags=list(
                data.get("generated_nodal_load_tags", [])
            ),
        )


@dataclass
class SurfacePressureData:
    tag: int
    name: str
    surface_tag: int
    pattern_tag: int
    pressure: float
    generated_element_load_tags: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Surface pressure tag")
        self.surface_tag = _strict_int(
            self.surface_tag,
            "Surface pressure Surface tag",
        )
        self.pattern_tag = _strict_int(
            self.pattern_tag,
            "Surface pressure pattern tag",
        )
        self.name = str(self.name).strip() or f"Surface Pressure {self.tag}"
        self.pressure = float(self.pressure)
        if self.tag <= 0 or self.surface_tag <= 0 or self.pattern_tag <= 0:
            raise ValueError(
                "Surface pressure tag, Surface tag, and pattern tag "
                "must be positive."
            )
        if not math.isfinite(self.pressure):
            raise ValueError("Surface pressure value must be finite.")
        if abs(self.pressure) <= 1.0e-15:
            raise ValueError("Surface pressure value cannot be zero.")
        ordered: list[int] = []
        seen: set[int] = set()
        for tag in self.generated_element_load_tags:
            load_tag = _strict_int(
                tag,
                "Surface pressure generated element-load tag",
            )
            if load_tag in seen:
                continue
            seen.add(load_tag)
            ordered.append(load_tag)
        self.generated_element_load_tags = ordered

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "surface_tag": self.surface_tag,
            "pattern_tag": self.pattern_tag,
            "pressure": self.pressure,
            "generated_element_load_tags": list(
                self.generated_element_load_tags
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfacePressureData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            surface_tag=data["surface_tag"],
            pattern_tag=data["pattern_tag"],
            pressure=float(data.get("pressure", 0.0)),
            generated_element_load_tags=list(
                data.get("generated_element_load_tags", [])
            ),
        )


@dataclass
class SurfaceRecorderData:
    tag: int
    name: str
    surface_tag: int
    response: str = "force"
    section_number: int = 1
    file_name: str = ""
    include_time: bool = True
    generated_recorder_tag: int | None = None

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Surface recorder tag")
        self.surface_tag = _strict_int(
            self.surface_tag,
            "Surface recorder Surface tag",
        )
        self.name = str(self.name).strip() or f"Surface Recorder {self.tag}"
        self.response = str(self.response)
        self.section_number = _strict_int(
            self.section_number,
            "Surface recorder Gauss point",
        )
        self.file_name = str(self.file_name).strip()
        self.include_time = _strict_bool(
            self.include_time,
            "Surface recorder include_time",
        )
        if self.generated_recorder_tag is not None:
            self.generated_recorder_tag = _strict_int(
                self.generated_recorder_tag,
                "Surface recorder generated recorder tag",
            )

        if self.tag <= 0 or self.surface_tag <= 0:
            raise ValueError(
                "Surface recorder tag and Surface tag must be positive."
            )
        if self.response not in {"force", "deformation"}:
            raise ValueError(
                "Managed Surface Shell recorder response must be "
                "'force' or 'deformation'."
            )
        if self.section_number not in range(1, 5):
            raise ValueError(
                "Managed Surface Shell recorder Gauss point must be in 1..4."
            )
        if not self.file_name:
            self.file_name = f"recorders/surface_recorder_{self.tag}.out"
        if (
            self.generated_recorder_tag is not None
            and self.generated_recorder_tag <= 0
        ):
            raise ValueError(
                "Generated recorder tag must be positive when provided."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "surface_tag": self.surface_tag,
            "response": self.response,
            "section_number": self.section_number,
            "file_name": self.file_name,
            "include_time": self.include_time,
            "generated_recorder_tag": self.generated_recorder_tag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfaceRecorderData":
        return cls(
            tag=data["tag"],
            name=str(data.get("name", "")),
            surface_tag=data["surface_tag"],
            response=str(data.get("response", "force")),
            section_number=data.get("section_number", 1),
            file_name=str(data.get("file_name", "")),
            include_time=data.get("include_time", True),
            generated_recorder_tag=data.get("generated_recorder_tag"),
        )


@dataclass
class SelectionSetData:
    name: str
    node_tags: set[int] = field(default_factory=set)
    element_tags: set[int] = field(default_factory=set)
    surface_tags: set[int] = field(default_factory=set)
    surface_scope_mode: str = "nodes_and_elements"

    def __post_init__(self) -> None:
        self.name = str(self.name)
        self.node_tags = {
            _strict_int(tag, "Selection-set node tag")
            for tag in self.node_tags
        }
        self.element_tags = {
            _strict_int(tag, "Selection-set element tag")
            for tag in self.element_tags
        }
        self.surface_tags = {
            _strict_int(tag, "Selection-set Surface tag")
            for tag in self.surface_tags
        }
        self.surface_scope_mode = str(self.surface_scope_mode)
        if self.surface_scope_mode not in {
            "elements",
            "nodes",
            "nodes_and_elements",
        }:
            raise ValueError(
                "Selection-set Surface scope mode must be 'elements', "
                "'nodes', or 'nodes_and_elements'."
            )

    @property
    def is_surface_managed(self) -> bool:
        return bool(self.surface_tags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node_tags": sorted(self.node_tags),
            "element_tags": sorted(self.element_tags),
            "surface_tags": sorted(self.surface_tags),
            "surface_scope_mode": self.surface_scope_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectionSetData":
        return cls(
            name=str(data["name"]),
            node_tags=set(data.get("node_tags", [])),
            element_tags=set(data.get("element_tags", [])),
            surface_tags=set(data.get("surface_tags", [])),
            surface_scope_mode=str(
                data.get("surface_scope_mode", "nodes_and_elements")
            ),
        )


@dataclass
class ProjectDatabase:
    name: str = "Untitled"
    model: StructuralModel = field(default_factory=StructuralModel)
    selection_sets: dict[str, SelectionSetData] = field(default_factory=dict)
    sketch_planes: dict[int, SketchPlaneData] = field(default_factory=dict)
    points: dict[int, PointGeometryData] = field(default_factory=dict)
    lines: dict[int, LineGeometryData] = field(default_factory=dict)
    surfaces: dict[int, SurfaceGeometryData] = field(default_factory=dict)
    surface_edge_supports: dict[int, SurfaceEdgeSupportData] = field(
        default_factory=dict
    )
    surface_edge_loads: dict[int, SurfaceEdgeLoadData] = field(
        default_factory=dict
    )
    surface_pressures: dict[int, SurfacePressureData] = field(
        default_factory=dict
    )
    surface_recorders: dict[int, SurfaceRecorderData] = field(
        default_factory=dict
    )
    materials: dict[int, MaterialData] = field(default_factory=dict)
    nd_materials: dict[int, NDMaterialData] = field(default_factory=dict)

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

    def _materialize_selection_set_surface_scope(
        self,
        selection_set: SelectionSetData,
    ) -> None:
        if not selection_set.surface_tags:
            return
        missing_surfaces = sorted(
            tag
            for tag in selection_set.surface_tags
            if tag not in self.surfaces
        )
        if missing_surfaces:
            raise ValueError(
                f"Named selection {selection_set.name!r} references "
                "missing Surface tag(s): "
                + ", ".join(map(str, missing_surfaces))
            )
        include_nodes = selection_set.surface_scope_mode in {
            "nodes",
            "nodes_and_elements",
        }
        include_elements = selection_set.surface_scope_mode in {
            "elements",
            "nodes_and_elements",
        }
        selection_set.node_tags = (
            {
                int(node_tag)
                for surface_tag in selection_set.surface_tags
                for node_tag in self.surfaces[
                    surface_tag
                ].generated_node_tags
                if int(node_tag) in self.model.nodes
            }
            if include_nodes
            else set()
        )
        selection_set.element_tags = (
            {
                int(element_tag)
                for surface_tag in selection_set.surface_tags
                for element_tag in self.surfaces[
                    surface_tag
                ].generated_element_tags
                if (
                    int(element_tag) in self.model.elements
                    and self.model.elements[
                        int(element_tag)
                    ].element_type in SHELL_ELEMENT_TYPES
                )
            }
            if include_elements
            else set()
        )

    def validate_selection_set(
        self,
        selection_set: SelectionSetData,
    ) -> None:
        if not selection_set.name.strip():
            raise ValueError("Named selection requires a non-empty name.")
        if selection_set.surface_tags:
            missing_surfaces = sorted(
                tag
                for tag in selection_set.surface_tags
                if tag not in self.surfaces
            )
            if missing_surfaces:
                raise ValueError(
                    f"Named selection {selection_set.name!r} references "
                    "missing Surface tag(s): "
                    + ", ".join(map(str, missing_surfaces))
                )
            expected = SelectionSetData(
                name=selection_set.name,
                surface_tags=set(selection_set.surface_tags),
                surface_scope_mode=selection_set.surface_scope_mode,
            )
            self._materialize_selection_set_surface_scope(expected)
            if (
                selection_set.node_tags != expected.node_tags
                or selection_set.element_tags != expected.element_tags
            ):
                raise ValueError(
                    f"Managed named selection {selection_set.name!r} has "
                    "stale FE membership."
                )
            return

        missing_nodes = sorted(
            tag
            for tag in selection_set.node_tags
            if tag not in self.model.nodes
        )
        missing_elements = sorted(
            tag
            for tag in selection_set.element_tags
            if tag not in self.model.elements
        )
        if missing_nodes or missing_elements:
            details: list[str] = []
            if missing_nodes:
                details.append(
                    "missing node(s) " + ", ".join(map(str, missing_nodes))
                )
            if missing_elements:
                details.append(
                    "missing element(s) "
                    + ", ".join(map(str, missing_elements))
                )
            raise ValueError(
                f"Named selection {selection_set.name!r} references "
                + "; ".join(details)
                + "."
            )

    def add_selection_set(self, selection_set: SelectionSetData) -> None:
        name = str(selection_set.name)
        if name in self.selection_sets:
            raise ValueError(
                f"A named selection called {name!r} already exists."
            )
        self._materialize_selection_set_surface_scope(selection_set)
        self.validate_selection_set(selection_set)
        self.selection_sets[name] = selection_set

    def update_selection_set(
        self,
        original_name: str,
        selection_set: SelectionSetData,
    ) -> None:
        original = str(original_name)
        if original not in self.selection_sets:
            raise ValueError(
                f"Named selection {original!r} does not exist."
            )
        if (
            selection_set.name != original
            and selection_set.name in self.selection_sets
        ):
            raise ValueError(
                f"A named selection called {selection_set.name!r} "
                "already exists."
            )
        self._materialize_selection_set_surface_scope(selection_set)
        self.validate_selection_set(selection_set)
        self.selection_sets.pop(original)
        self.selection_sets[selection_set.name] = selection_set

    def clear_model_linked_data(self) -> None:
        """Clear objects whose meaning depends on the current model geometry.

        Material, section, and transformation libraries are intentionally
        preserved so a replacement geometry can reuse those definitions.
        """
        self.selection_sets.clear()
        self.points.clear()
        self.lines.clear()
        self.surfaces.clear()
        self.surface_edge_supports.clear()
        self.surface_edge_loads.clear()
        self.surface_pressures.clear()
        self.surface_recorders.clear()
        self.constraints.clear()
        self.connections.clear()
        self.time_series.clear()
        self.load_patterns.clear()
        self.nodal_loads.clear()
        self.prescribed_displacements.clear()
        self.element_loads.clear()
        self.mass_sources.clear()
        self.analyses.clear()
        self.recorders.clear()
        self.solution_results.clear()
        self.active_analysis_tag = None

    def reverse_shell_orientation_preserving_pressure(
        self,
        element_tags,
    ) -> dict[str, list[int]]:
        """Reverse shell normals while preserving global SurfacePressure vectors."""
        tags = sorted({
            _strict_int(tag, "Shell element tag")
            for tag in element_tags
        })
        if not tags:
            return {
                "element_tags": [],
                "pressure_load_tags": [],
            }

        for tag in tags:
            element = self.model.elements.get(tag)
            if element is None:
                raise ValueError(f"Element {tag} does not exist.")
            if element.element_type not in SHELL_ELEMENT_TYPES:
                raise ValueError(
                    f"Element {tag} is not a Shell element."
                )

        pressure_load_tags = sorted(
            int(load.tag)
            for load in self.element_loads.values()
            if (
                load.load_type == "SurfacePressure"
                and int(load.element_tag) in tags
            )
        )

        updated = self.model.reverse_shell_orientation(tags)
        for load_tag in pressure_load_tags:
            load = self.element_loads[load_tag]
            load.pressure = -float(load.pressure)
            self._validate_element_load(load)
        for tag in updated:
            self.validate_element_state(tag)

        return {
            "element_tags": sorted(int(tag) for tag in updated),
            "pressure_load_tags": pressure_load_tags,
        }

    def coincident_shell_node_groups(
        self,
        *,
        tolerance: float | None = None,
    ) -> list[list[int]]:
        """Return shell-used node groups that occupy the same position."""
        shell_node_tags = {
            int(node_tag)
            for element in self.model.elements.values()
            if element.element_type in SHELL_ELEMENT_TYPES
            for node_tag in element.node_tags()
            if int(node_tag) in self.model.nodes
        }
        if len(shell_node_tags) < 2:
            return []

        nodes = [
            self.model.nodes[tag]
            for tag in sorted(shell_node_tags)
        ]
        if tolerance is None:
            xs = [float(node.xyz[0]) for node in nodes]
            ys = [float(node.xyz[1]) for node in nodes]
            zs = [float(node.xyz[2]) for node in nodes]
            span = max(
                max(xs) - min(xs),
                max(ys) - min(ys),
                max(zs) - min(zs),
                1.0,
            )
            merge_tolerance = 1.0e-9 * span
        else:
            merge_tolerance = float(tolerance)
            if (
                not math.isfinite(merge_tolerance)
                or merge_tolerance <= 0.0
            ):
                raise ValueError(
                    "Shell stitch tolerance must be a finite positive value."
                )

        tolerance2 = merge_tolerance * merge_tolerance
        buckets: dict[tuple[int, int, int], list[int]] = {}
        parent = {tag: tag for tag in shell_node_tags}

        def find(tag: int) -> int:
            root = int(tag)
            while parent[root] != root:
                parent[root] = parent[parent[root]]
                root = parent[root]
            return root

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left == root_right:
                return
            if root_left < root_right:
                parent[root_right] = root_left
            else:
                parent[root_left] = root_right

        def key_for(xyz) -> tuple[int, int, int]:
            return tuple(
                int(round(float(value) / merge_tolerance))
                for value in xyz
            )

        for node in nodes:
            base = key_for(node.xyz)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for other_tag in buckets.get(
                            (
                                base[0] + dx,
                                base[1] + dy,
                                base[2] + dz,
                            ),
                            (),
                        ):
                            other = self.model.nodes[other_tag]
                            distance2 = sum(
                                (
                                    float(node.xyz[index])
                                    - float(other.xyz[index])
                                ) ** 2
                                for index in range(3)
                            )
                            if distance2 <= tolerance2:
                                union(int(node.tag), int(other_tag))
            buckets.setdefault(base, []).append(int(node.tag))

        groups: dict[int, list[int]] = {}
        for tag in sorted(shell_node_tags):
            groups.setdefault(find(tag), []).append(tag)
        return [
            tags
            for _, tags in sorted(groups.items())
            if len(tags) > 1
        ]
    def stitch_coincident_shell_nodes(
        self,
        *,
        tolerance: float | None = None,
    ) -> dict[str, object]:
        """Merge safe coincident shell nodes and remap shell connectivity."""
        groups = self.coincident_shell_node_groups(
            tolerance=tolerance,
        )
        if not groups:
            return {
                "groups": [],
                "merged_nodes": [],
                "kept_nodes": [],
                "remapped_elements": [],
            }

        mapping: dict[int, int] = {}
        kept_nodes: list[int] = []
        for group in groups:
            keeper = min(int(tag) for tag in group)
            kept_nodes.append(keeper)
            keeper_node = self.model.nodes[keeper]
            for raw_tag in group:
                tag = int(raw_tag)
                if tag == keeper:
                    continue
                node = self.model.nodes[tag]
                if tuple(node.fixity) != tuple(keeper_node.fixity):
                    raise ValueError(
                        f"Cannot stitch shell nodes {keeper} and {tag}: "
                        "their support/fixity states differ."
                    )
                if tuple(node.mass) != tuple(keeper_node.mass):
                    raise ValueError(
                        f"Cannot stitch shell nodes {keeper} and {tag}: "
                        "their nodal mass values differ."
                    )
                mapping[tag] = keeper

        if not mapping:
            return {
                "groups": groups,
                "merged_nodes": [],
                "kept_nodes": sorted(set(kept_nodes)),
                "remapped_elements": [],
            }

        removed = set(mapping)
        blockers: list[str] = []

        non_shell_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                element.element_type not in SHELL_ELEMENT_TYPES
                and any(tag in removed for tag in element.node_tags())
            )
        )
        if non_shell_users:
            blockers.append(
                "non-shell element(s) "
                + ", ".join(map(str, non_shell_users))
            )

        load_users = sorted(
            load.tag
            for load in self.nodal_loads.values()
            if load.node_tag in removed
        )
        if load_users:
            blockers.append(
                "nodal load(s) " + ", ".join(map(str, load_users))
            )

        displacement_users = sorted(
            displacement.tag
            for displacement in self.prescribed_displacements.values()
            if displacement.node_tag in removed
        )
        if displacement_users:
            blockers.append(
                "prescribed displacement(s) "
                + ", ".join(map(str, displacement_users))
            )

        constraint_users = sorted(
            constraint.tag
            for constraint in self.constraints.values()
            if (
                constraint.retained_node in removed
                or any(
                    tag in removed
                    for tag in constraint.constrained_nodes
                )
            )
        )
        if constraint_users:
            blockers.append(
                "constraint(s) "
                + ", ".join(map(str, constraint_users))
            )

        connection_users = sorted(
            connection.tag
            for connection in self.connections.values()
            if (
                connection.node_i in removed
                or connection.node_j in removed
                or connection.generated_ground_node in removed
            )
        )
        if connection_users:
            blockers.append(
                "connection(s) "
                + ", ".join(map(str, connection_users))
            )

        node_recorder_users = sorted(
            recorder.tag
            for recorder in self.recorders.values()
            if (
                recorder.recorder_type == "Node"
                and any(tag in removed for tag in recorder.target_tags)
            )
        )
        if node_recorder_users:
            blockers.append(
                "node recorder(s) "
                + ", ".join(map(str, node_recorder_users))
            )

        control_users = sorted(
            analysis.tag
            for analysis in self.analyses.values()
            if (
                self._analysis_uses_control_node(analysis)
                and int(analysis.control_node) in removed
            )
        )
        if control_users:
            blockers.append(
                "analysis control node(s) in analysis tag(s) "
                + ", ".join(map(str, control_users))
            )

        result_users = sorted(
            result.tag
            for result in self.solution_results.values()
            if any(tag in removed for tag in result.node_scope)
        )
        if result_users:
            blockers.append(
                "solution result node scope(s) "
                + ", ".join(map(str, result_users))
            )

        if blockers:
            raise ValueError(
                "Cannot stitch coincident shell nodes because node(s) "
                + ", ".join(map(str, sorted(removed)))
                + " are referenced by "
                + "; ".join(blockers)
                + ". Reassign those references first."
            )

        remapped_elements: list[int] = []
        proposed: dict[int, tuple[int, int, int, int]] = {}
        for element in self.model.elements.values():
            if element.element_type not in SHELL_ELEMENT_TYPES:
                continue
            tags = tuple(
                mapping.get(int(tag), int(tag))
                for tag in element.node_tags()
            )
            if len(tags) != 4:
                continue
            if len(set(tags)) != 4:
                raise ValueError(
                    f"Cannot stitch coincident shell nodes because shell "
                    f"element {element.tag} would collapse to fewer than "
                    "four distinct nodes."
                )
            if tags != element.node_tags():
                proposed[element.tag] = (
                    int(tags[0]),
                    int(tags[1]),
                    int(tags[2]),
                    int(tags[3]),
                )

        for tag, tags in proposed.items():
            element = self.model.elements[tag]
            element.i, element.j, element.k, element.l = tags
            element.__post_init__()
            remapped_elements.append(int(tag))

        for selection_set in self.selection_sets.values():
            selection_set.node_tags = {
                mapping.get(int(tag), int(tag))
                for tag in selection_set.node_tags
                if int(tag) not in removed or int(tag) in mapping
            }

        for tag in sorted(removed):
            self.model.nodes.pop(tag, None)

        for tag in remapped_elements:
            self.validate_element_state(tag)

        return {
            "groups": [list(group) for group in groups],
            "merged_nodes": sorted(removed),
            "kept_nodes": sorted(set(kept_nodes)),
            "remapped_elements": sorted(remapped_elements),
        }


    def next_sketch_plane_tag(self) -> int:
        return max(self.sketch_planes, default=0) + 1

    def add_sketch_plane(self, plane: SketchPlaneData) -> None:
        if plane.tag in self.sketch_planes:
            raise ValueError(
                f"Sketch Plane tag {plane.tag} already exists."
            )
        self.sketch_planes[plane.tag] = plane

    def remove_sketch_plane(self, tag: int) -> None:
        tag = _strict_int(tag, "Sketch Plane tag")
        self.sketch_planes.pop(tag, None)

    def next_point_tag(self) -> int:
        return max(self.points, default=0) + 1

    def add_point(self, point: PointGeometryData) -> None:
        if point.tag in self.points:
            raise ValueError(
                f"Geometry Point tag {point.tag} already exists."
            )
        self.points[point.tag] = point

    def update_point(
        self,
        original_tag: int,
        point: PointGeometryData,
    ) -> None:
        original_tag = _strict_int(original_tag, "Geometry Point original tag")
        if original_tag not in self.points:
            raise ValueError(
                f"Geometry Point tag {original_tag} does not exist."
            )
        if point.tag != original_tag and point.tag in self.points:
            raise ValueError(
                f"Geometry Point tag {point.tag} already exists."
            )
        old_point = self.points[original_tag]
        affected_lines = [
            line
            for line in self.lines.values()
            if original_tag in {line.point_i, line.point_j}
        ]
        affected_surfaces = [
            surface
            for surface in self.surfaces.values()
            if (
                surface.corner_point_tags is not None
                and original_tag in surface.corner_point_tags
            )
        ]
        coordinates_changed = tuple(point.xyz) != tuple(old_point.xyz)
        if coordinates_changed:
            meshed_lines = [
                line.tag
                for line in affected_lines
                if any(
                    element_tag in self.model.elements
                    for element_tag in line.generated_element_tags
                )
            ]
            meshed_surfaces = [
                surface.tag
                for surface in affected_surfaces
                if any(
                    element_tag in self.model.elements
                    for element_tag in surface.generated_element_tags
                )
            ]
            blockers: list[str] = []
            if meshed_lines:
                blockers.append(
                    "meshed Line(s): "
                    + ", ".join(map(str, sorted(meshed_lines)))
                )
            if meshed_surfaces:
                blockers.append(
                    "meshed Surface(s): "
                    + ", ".join(map(str, sorted(meshed_surfaces)))
                )
            if blockers:
                raise ValueError(
                    "Geometry Point cannot move while it is used by "
                    + "; ".join(blockers)
                    + ". Edit/remesh the owning geometry instead."
                )

        if point.tag != original_tag:
            for line in self.lines.values():
                if line.point_i == original_tag:
                    line.point_i = point.tag
                if line.point_j == original_tag:
                    line.point_j = point.tag
            for surface in affected_surfaces:
                surface.corner_point_tags = tuple(
                    point.tag if tag == original_tag else tag
                    for tag in surface.corner_point_tags
                )

        self.points.pop(original_tag)
        self.points[point.tag] = point
        for surface in affected_surfaces:
            if surface.corner_point_tags is not None:
                surface.points = tuple(
                    self.points[tag].xyz
                    for tag in surface.corner_point_tags
                )

    def remove_point(self, tag: int) -> None:
        tag = _strict_int(tag, "Geometry Point tag")
        line_users = sorted(
            line.tag
            for line in self.lines.values()
            if tag in {line.point_i, line.point_j}
        )
        surface_users = sorted(
            surface.tag
            for surface in self.surfaces.values()
            if (
                surface.corner_point_tags is not None
                and tag in surface.corner_point_tags
            )
        )
        users = []
        if line_users:
            users.append(
                "Line(s): " + ", ".join(map(str, line_users))
            )
        if surface_users:
            users.append(
                "Surface(s): " + ", ".join(map(str, surface_users))
            )
        if users:
            raise ValueError(
                f"Geometry Point {tag} is used by " + "; ".join(users)
            )
        self.points.pop(tag, None)

    def next_line_tag(self) -> int:
        return max(self.lines, default=0) + 1

    def _validate_line_geometry(self, line: LineGeometryData) -> None:
        missing = [
            tag
            for tag in (line.point_i, line.point_j)
            if tag not in self.points
        ]
        if missing:
            raise ValueError(
                "Geometry Line references missing Point(s): "
                + ", ".join(map(str, missing))
            )
        if not line.mesh_recipe_configured:
            return
        if line.element_family == "Frame":
            if (
                line.section_tag is None
                or line.section_tag not in self.sections
            ):
                raise ValueError(
                    "Frame Line requires an existing Section."
                )
            if (
                self.sections[line.section_tag].section_type
                in SHELL_SECTION_TYPES
            ):
                raise ValueError(
                    "Frame Line requires a frame-compatible Section, "
                    "not a Shell Section."
                )
            if (
                line.transformation_tag is None
                or line.transformation_tag not in self.transformations
            ):
                raise ValueError(
                    "Frame Line requires an existing Geometric Transformation."
                )
        else:
            if (
                line.material_tag is None
                or line.material_tag not in self.materials
            ):
                raise ValueError(
                    "Truss Line requires an existing uniaxial Material."
                )

    def add_line(self, line: LineGeometryData) -> None:
        if line.tag in self.lines:
            raise ValueError(
                f"Geometry Line tag {line.tag} already exists."
            )
        self._validate_line_geometry(line)
        self.lines[line.tag] = line

    def update_line(
        self,
        original_tag: int,
        line: LineGeometryData,
    ) -> None:
        original_tag = _strict_int(original_tag, "Geometry Line original tag")
        if original_tag not in self.lines:
            raise ValueError(
                f"Geometry Line tag {original_tag} does not exist."
            )
        if line.tag != original_tag and line.tag in self.lines:
            raise ValueError(
                f"Geometry Line tag {line.tag} already exists."
            )
        self._validate_line_geometry(line)
        self.lines.pop(original_tag)
        self.lines[line.tag] = line

    def remove_line(self, tag: int) -> None:
        tag = _strict_int(tag, "Geometry Line tag")
        self.lines.pop(tag, None)


    def next_surface_tag(self) -> int:
        return max(self.surfaces, default=0) + 1

    def _validate_surface_geometry(
        self,
        surface: SurfaceGeometryData,
    ) -> None:
        if surface.mesh_recipe_configured:
            if (
                surface.section_tag is None
                or surface.section_tag not in self.sections
            ):
                raise ValueError(
                    "Meshed Surface recipe requires an existing Shell Section."
                )
            if (
                self.sections[surface.section_tag].section_type
                not in SHELL_SECTION_TYPES
            ):
                raise ValueError(
                    "Surface geometry requires a shell-compatible Section."
                )
        if surface.corner_point_tags is not None:
            missing = [
                tag
                for tag in surface.corner_point_tags
                if tag not in self.points
            ]
            if missing:
                raise ValueError(
                    "Surface geometry references missing Point(s): "
                    + ", ".join(map(str, missing))
                )
            surface.points = tuple(
                self.points[tag].xyz
                for tag in surface.corner_point_tags
            )

    def add_surface(self, surface: SurfaceGeometryData) -> None:
        if surface.tag in self.surfaces:
            raise ValueError(
                f"Surface geometry tag {surface.tag} already exists."
            )
        self._validate_surface_geometry(surface)
        self.surfaces[surface.tag] = surface

    def update_surface(
        self,
        original_tag: int,
        surface: SurfaceGeometryData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Surface geometry original tag",
        )
        if original_tag not in self.surfaces:
            raise ValueError(
                f"Surface geometry tag {original_tag} does not exist."
            )
        if (
            surface.tag != original_tag
            and surface.tag in self.surfaces
        ):
            raise ValueError(
                f"Surface geometry tag {surface.tag} already exists."
            )
        self._validate_surface_geometry(surface)
        self.surfaces.pop(original_tag)
        self.surfaces[surface.tag] = surface
        if surface.tag != original_tag:
            for support in self.surface_edge_supports.values():
                if support.surface_tag == original_tag:
                    support.surface_tag = surface.tag
            for edge_load in self.surface_edge_loads.values():
                if edge_load.surface_tag == original_tag:
                    edge_load.surface_tag = surface.tag
            for surface_pressure in self.surface_pressures.values():
                if surface_pressure.surface_tag == original_tag:
                    surface_pressure.surface_tag = surface.tag
            for surface_recorder in self.surface_recorders.values():
                if surface_recorder.surface_tag == original_tag:
                    surface_recorder.surface_tag = surface.tag
            for result in self.solution_results.values():
                if original_tag in result.surface_scope:
                    result.surface_scope = [
                        surface.tag if item == original_tag else item
                        for item in result.surface_scope
                    ]
            for selection_set in self.selection_sets.values():
                if original_tag in selection_set.surface_tags:
                    selection_set.surface_tags = {
                        surface.tag if item == original_tag else item
                        for item in selection_set.surface_tags
                    }
                    self._materialize_selection_set_surface_scope(
                        selection_set
                    )

    def remove_surface(self, tag: int) -> None:
        tag = _strict_int(tag, "Surface geometry tag")
        support_tags = sorted(
            support.tag
            for support in self.surface_edge_supports.values()
            if support.surface_tag == tag
        )
        edge_load_tags = sorted(
            edge_load.tag
            for edge_load in self.surface_edge_loads.values()
            if edge_load.surface_tag == tag
        )
        pressure_tags = sorted(
            pressure.tag
            for pressure in self.surface_pressures.values()
            if pressure.surface_tag == tag
        )
        surface_recorder_tags = sorted(
            recorder.tag
            for recorder in self.surface_recorders.values()
            if recorder.surface_tag == tag
        )
        managed_result_tags = sorted(
            result.tag
            for result in self.solution_results.values()
            if tag in result.surface_scope
        )
        managed_selection_names = sorted(
            selection.name
            for selection in self.selection_sets.values()
            if tag in selection.surface_tags
        )
        if (
            support_tags
            or edge_load_tags
            or pressure_tags
            or surface_recorder_tags
            or managed_result_tags
            or managed_selection_names
        ):
            details: list[str] = []
            if support_tags:
                details.append(
                    "managed edge support(s) "
                    + ", ".join(map(str, support_tags))
                )
            if edge_load_tags:
                details.append(
                    "managed edge line load(s) "
                    + ", ".join(map(str, edge_load_tags))
                )
            if pressure_tags:
                details.append(
                    "managed Surface pressure(s) "
                    + ", ".join(map(str, pressure_tags))
                )
            if surface_recorder_tags:
                details.append(
                    "managed Surface recorder(s) "
                    + ", ".join(map(str, surface_recorder_tags))
                )
            if managed_result_tags:
                details.append(
                    "managed Surface result request(s) "
                    + ", ".join(map(str, managed_result_tags))
                )
            if managed_selection_names:
                details.append(
                    "managed Surface named selection(s) "
                    + ", ".join(managed_selection_names)
                )
            raise ValueError(
                f"Surface geometry {tag} has "
                + "; ".join(details)
                + ". Remove them through the Surface lifecycle workflow."
            )
        self.surfaces.pop(tag, None)

    def next_surface_edge_support_tag(self) -> int:
        return max(self.surface_edge_supports, default=0) + 1

    def _validate_surface_edge_support(
        self,
        support: SurfaceEdgeSupportData,
        *,
        replacing_tag: int | None = None,
    ) -> None:
        if support.surface_tag not in self.surfaces:
            raise ValueError(
                "Surface edge support references missing Surface "
                f"{support.surface_tag}."
            )
        for tag, existing in self.surface_edge_supports.items():
            if int(tag) == int(support.tag):
                continue
            if replacing_tag is not None and int(tag) == int(replacing_tag):
                continue
            if (
                existing.surface_tag == support.surface_tag
                and existing.edge_index == support.edge_index
            ):
                raise ValueError(
                    f"Surface {support.surface_tag} edge "
                    f"{support.edge_index} already has managed support "
                    f"{existing.tag}."
                )

    def add_surface_edge_support(
        self,
        support: SurfaceEdgeSupportData,
    ) -> None:
        if support.tag in self.surface_edge_supports:
            raise ValueError(
                f"Surface edge support tag {support.tag} already exists."
            )
        self._validate_surface_edge_support(support)
        self.surface_edge_supports[support.tag] = support

    def update_surface_edge_support(
        self,
        original_tag: int,
        support: SurfaceEdgeSupportData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Surface edge support original tag",
        )
        if original_tag not in self.surface_edge_supports:
            raise ValueError(
                f"Surface edge support tag {original_tag} does not exist."
            )
        if (
            support.tag != original_tag
            and support.tag in self.surface_edge_supports
        ):
            raise ValueError(
                f"Surface edge support tag {support.tag} already exists."
            )
        self._validate_surface_edge_support(
            support,
            replacing_tag=original_tag,
        )
        self.surface_edge_supports.pop(original_tag)
        self.surface_edge_supports[support.tag] = support

    def remove_surface_edge_support_definition(self, tag: int) -> None:
        normalized = _strict_int(tag, "Surface edge support tag")
        self.surface_edge_supports.pop(normalized, None)

    def next_surface_edge_load_tag(self) -> int:
        return max(self.surface_edge_loads, default=0) + 1

    def _validate_surface_edge_load(
        self,
        edge_load: SurfaceEdgeLoadData,
        *,
        replacing_tag: int | None = None,
    ) -> None:
        if edge_load.surface_tag not in self.surfaces:
            raise ValueError(
                "Surface edge load references missing Surface "
                f"{edge_load.surface_tag}."
            )
        pattern = self.load_patterns.get(edge_load.pattern_tag)
        if pattern is None:
            raise ValueError(
                "Surface edge load references missing load pattern "
                f"{edge_load.pattern_tag}."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Surface edge line loads require a Plain load pattern."
            )
        for tag, existing in self.surface_edge_loads.items():
            if int(tag) == int(edge_load.tag):
                continue
            if replacing_tag is not None and int(tag) == int(replacing_tag):
                continue
            if (
                existing.surface_tag == edge_load.surface_tag
                and existing.edge_index == edge_load.edge_index
                and existing.pattern_tag == edge_load.pattern_tag
            ):
                raise ValueError(
                    f"Surface {edge_load.surface_tag} edge "
                    f"{edge_load.edge_index} already has managed line load "
                    f"{existing.tag} in Plain pattern "
                    f"{edge_load.pattern_tag}."
                )

    def add_surface_edge_load(
        self,
        edge_load: SurfaceEdgeLoadData,
    ) -> None:
        if edge_load.tag in self.surface_edge_loads:
            raise ValueError(
                f"Surface edge load tag {edge_load.tag} already exists."
            )
        self._validate_surface_edge_load(edge_load)
        self.surface_edge_loads[edge_load.tag] = edge_load

    def update_surface_edge_load(
        self,
        original_tag: int,
        edge_load: SurfaceEdgeLoadData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Surface edge load original tag",
        )
        if original_tag not in self.surface_edge_loads:
            raise ValueError(
                f"Surface edge load tag {original_tag} does not exist."
            )
        if (
            edge_load.tag != original_tag
            and edge_load.tag in self.surface_edge_loads
        ):
            raise ValueError(
                f"Surface edge load tag {edge_load.tag} already exists."
            )
        self._validate_surface_edge_load(
            edge_load,
            replacing_tag=original_tag,
        )
        self.surface_edge_loads.pop(original_tag)
        self.surface_edge_loads[edge_load.tag] = edge_load

    def remove_surface_edge_load_definition(self, tag: int) -> None:
        normalized = _strict_int(tag, "Surface edge load tag")
        self.surface_edge_loads.pop(normalized, None)

    def next_surface_pressure_tag(self) -> int:
        return max(self.surface_pressures, default=0) + 1

    def _validate_surface_pressure(
        self,
        pressure: SurfacePressureData,
        *,
        replacing_tag: int | None = None,
    ) -> None:
        surface = self.surfaces.get(pressure.surface_tag)
        if surface is None:
            raise ValueError(
                "Surface pressure references missing Surface "
                f"{pressure.surface_tag}."
            )
        pattern = self.load_patterns.get(pressure.pattern_tag)
        if pattern is None:
            raise ValueError(
                "Surface pressure references missing load pattern "
                f"{pressure.pattern_tag}."
            )
        if pattern.pattern_type != "Plain":
            raise ValueError(
                "Managed Surface pressure requires a Plain load pattern."
            )
        for tag, existing in self.surface_pressures.items():
            if int(tag) == int(pressure.tag):
                continue
            if replacing_tag is not None and int(tag) == int(replacing_tag):
                continue
            if (
                existing.surface_tag == pressure.surface_tag
                and existing.pattern_tag == pressure.pattern_tag
            ):
                raise ValueError(
                    f"Surface {pressure.surface_tag} already has managed "
                    f"pressure {existing.tag} in Plain pattern "
                    f"{pressure.pattern_tag}."
                )
        for load_tag in pressure.generated_element_load_tags:
            load = self.element_loads.get(int(load_tag))
            if load is None:
                raise ValueError(
                    f"Managed Surface pressure {pressure.tag} references "
                    f"missing generated element load {load_tag}."
                )
            if (
                load.load_type != "SurfacePressure"
                or load.pattern_tag != pressure.pattern_tag
                or load.element_tag not in surface.generated_element_tags
            ):
                raise ValueError(
                    f"Managed Surface pressure {pressure.tag} has invalid "
                    f"generated element-load provenance at load {load_tag}."
                )

    def add_surface_pressure(
        self,
        pressure: SurfacePressureData,
    ) -> None:
        if pressure.tag in self.surface_pressures:
            raise ValueError(
                f"Surface pressure tag {pressure.tag} already exists."
            )
        self._validate_surface_pressure(pressure)
        self.surface_pressures[pressure.tag] = pressure

    def update_surface_pressure(
        self,
        original_tag: int,
        pressure: SurfacePressureData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Surface pressure original tag",
        )
        if original_tag not in self.surface_pressures:
            raise ValueError(
                f"Surface pressure tag {original_tag} does not exist."
            )
        if (
            pressure.tag != original_tag
            and pressure.tag in self.surface_pressures
        ):
            raise ValueError(
                f"Surface pressure tag {pressure.tag} already exists."
            )
        self._validate_surface_pressure(
            pressure,
            replacing_tag=original_tag,
        )
        self.surface_pressures.pop(original_tag)
        self.surface_pressures[pressure.tag] = pressure

    def remove_surface_pressure_definition(self, tag: int) -> None:
        normalized = _strict_int(tag, "Surface pressure tag")
        self.surface_pressures.pop(normalized, None)

    def next_surface_recorder_tag(self) -> int:
        return max(self.surface_recorders, default=0) + 1

    def _validate_surface_recorder(
        self,
        surface_recorder: SurfaceRecorderData,
        *,
        replacing_tag: int | None = None,
    ) -> None:
        surface = self.surfaces.get(surface_recorder.surface_tag)
        if surface is None:
            raise ValueError(
                "Surface recorder references missing Surface "
                f"{surface_recorder.surface_tag}."
            )
        generated_tag = surface_recorder.generated_recorder_tag
        if generated_tag is None:
            return
        recorder = self.recorders.get(int(generated_tag))
        if recorder is None:
            raise ValueError(
                f"Managed Surface recorder {surface_recorder.tag} references "
                f"missing generated recorder {generated_tag}."
            )
        if recorder.recorder_type != "Shell":
            raise ValueError(
                f"Managed Surface recorder {surface_recorder.tag} generated "
                f"recorder {generated_tag} is not a Shell recorder."
            )
        expected_targets = sorted(
            int(element_tag)
            for element_tag in surface.generated_element_tags
            if (
                int(element_tag) in self.model.elements
                and self.model.elements[
                    int(element_tag)
                ].element_type in SHELL_ELEMENT_TYPES
            )
        )
        if (
            recorder.target_tags != expected_targets
            or recorder.response != surface_recorder.response
            or recorder.section_number != surface_recorder.section_number
            or recorder.file_name != surface_recorder.file_name
            or recorder.include_time != surface_recorder.include_time
        ):
            raise ValueError(
                f"Managed Surface recorder {surface_recorder.tag} has stale "
                "generated recorder provenance."
            )

    def add_surface_recorder(
        self,
        surface_recorder: SurfaceRecorderData,
    ) -> None:
        if surface_recorder.tag in self.surface_recorders:
            raise ValueError(
                f"Surface recorder tag {surface_recorder.tag} already exists."
            )
        self._validate_surface_recorder(surface_recorder)
        self.surface_recorders[surface_recorder.tag] = surface_recorder

    def update_surface_recorder(
        self,
        original_tag: int,
        surface_recorder: SurfaceRecorderData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Surface recorder original tag",
        )
        if original_tag not in self.surface_recorders:
            raise ValueError(
                f"Surface recorder tag {original_tag} does not exist."
            )
        if (
            surface_recorder.tag != original_tag
            and surface_recorder.tag in self.surface_recorders
        ):
            raise ValueError(
                f"Surface recorder tag {surface_recorder.tag} already exists."
            )
        self._validate_surface_recorder(
            surface_recorder,
            replacing_tag=original_tag,
        )
        self.surface_recorders.pop(original_tag)
        self.surface_recorders[surface_recorder.tag] = surface_recorder

    def remove_surface_recorder_definition(self, tag: int) -> None:
        normalized = _strict_int(tag, "Surface recorder tag")
        self.surface_recorders.pop(normalized, None)

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
        target = _strict_int(material_tag, "Material tag")
        return sorted(
            material.tag
            for material in self.materials.values()
            if target in self.material_dependencies(material)
        )

    @staticmethod
    def nd_material_uniaxial_dependencies(
        material: NDMaterialData,
    ) -> list[int]:
        if material.material_type == "OrthotropicRAConcrete":
            return [int(round(material.parameters["conc"]))]
        if material.material_type == "SmearedSteelDoubleLayer":
            return [
                int(round(material.parameters["mat1"])),
                int(round(material.parameters["mat2"])),
            ]
        if material.material_type == "FSAM":
            return [
                int(round(material.parameters["sX"])),
                int(round(material.parameters["sY"])),
                int(round(material.parameters["conc"])),
            ]
        return []

    def _validate_nd_material_dependencies(
        self,
        material: NDMaterialData,
    ) -> None:
        dependencies = self.nd_material_uniaxial_dependencies(material)
        missing = sorted(
            tag for tag in dependencies
            if tag not in self.materials
        )
        if missing:
            raise ValueError(
                f"{material.material_type} references missing uniaxial "
                "material tag(s): " + ", ".join(map(str, missing))
            )
        if material.material_type == "FSAM":
            concrete_tag = int(round(material.parameters["conc"]))
            concrete = self.materials.get(concrete_tag)
            if concrete is not None and concrete.material_type != "ConcreteCM":
                raise ValueError(
                    "FSAM concrete dependency must use ConcreteCM; "
                    f"material {concrete_tag} is {concrete.material_type}."
                )

    def nd_materials_using_material(
        self,
        material_tag: int,
    ) -> list[int]:
        target = _strict_int(material_tag, "Material tag")
        return sorted(
            material.tag
            for material in self.nd_materials.values()
            if target in self.nd_material_uniaxial_dependencies(material)
        )

    def next_nd_material_tag(self) -> int:
        return max(self.nd_materials, default=0) + 1

    def add_nd_material(self, material: NDMaterialData) -> None:
        if material.tag in self.nd_materials:
            raise ValueError(
                f"nDMaterial tag {material.tag} already exists."
            )
        self._validate_nd_material_dependencies(material)
        self.nd_materials[material.tag] = material

    def sections_using_nd_material(self, material_tag: int) -> list[int]:
        target = _strict_int(material_tag, "nDMaterial tag")
        return sorted(
            section.tag
            for section in self.sections.values()
            if target in section.shell_nd_material_tags()
        )

    def update_nd_material(
        self,
        original_tag: int,
        material: NDMaterialData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "nDMaterial original tag",
        )
        if original_tag not in self.nd_materials:
            raise ValueError(
                f"nDMaterial tag {original_tag} does not exist."
            )
        if (
            material.tag != original_tag
            and material.tag in self.nd_materials
        ):
            raise ValueError(
                f"nDMaterial tag {material.tag} already exists."
            )
        self._validate_nd_material_dependencies(material)
        self.nd_materials.pop(original_tag)
        self.nd_materials[material.tag] = material
        if material.tag != original_tag:
            for section in self.sections.values():
                if section.nd_material_tag == original_tag:
                    section.nd_material_tag = material.tag
                for layer in section.shell_layers:
                    if layer.material_tag == original_tag:
                        layer.material_tag = material.tag
            for element in self.model.elements.values():
                if element.continuum_material_tag == original_tag:
                    element.continuum_material_tag = material.tag
                if element.solid_material_tag == original_tag:
                    element.solid_material_tag = material.tag
                if element.element_type == "SFI_MVLEM":
                    element.wall_nd_material_tags = tuple(
                        material.tag if int(tag) == original_tag else int(tag)
                        for tag in element.wall_nd_material_tags
                    )

    def remove_nd_material(self, tag: int) -> None:
        tag = _strict_int(tag, "nDMaterial tag")
        section_users = self.sections_using_nd_material(tag)
        element_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                element.continuum_material_tag == tag
                or element.solid_material_tag == tag
                or (
                    element.element_type == "SFI_MVLEM"
                    and tag in element.wall_nd_material_tags
                )
            )
        )
        if section_users or element_users:
            details = []
            if section_users:
                details.append(
                    "Shell section(s) " + ", ".join(map(str, section_users))
                )
            if element_users:
                details.append(
                    "element(s) " + ", ".join(map(str, element_users))
                )
            raise ValueError(
                f"nDMaterial {tag} is still referenced by "
                + "; ".join(details)
                + ". Reassign those references before deleting it."
            )
        self.nd_materials.pop(tag, None)

    def next_material_tag(self) -> int:
        return max(self.materials, default=0) + 1

    def add_material(self, material: MaterialData) -> None:
        if material.tag in self.materials:
            raise ValueError(f"Material tag {material.tag} already exists.")
        self._validate_material_dependencies(material)
        self.materials[material.tag] = material

    def update_material(self, original_tag: int, material: MaterialData) -> None:
        original_tag = _strict_int(
            original_tag,
            "Material original tag",
        )
        if original_tag not in self.materials:
            raise ValueError(f"Material tag {original_tag} does not exist.")
        if material.tag != original_tag and material.tag in self.materials:
            raise ValueError(f"Material tag {material.tag} already exists.")
        self._validate_material_dependencies(
            material,
            replacing_tag=original_tag,
        )
        elastic_section_users = sorted(
            section.tag
            for section in self.sections.values()
            if (
                section.section_type == "Elastic"
                and section.material_tag == original_tag
            )
        )
        if elastic_section_users:
            try:
                material.elastic_modulus()
                material.shear_modulus()
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Material {original_tag} is linked to Elastic section(s) "
                    + ", ".join(map(str, elastic_section_users))
                    + " and must continue to expose elastic/shear modulus."
                ) from exc

            self_weight_users = sorted(
                load.tag
                for load in self.element_loads.values()
                if (
                    load.load_type == "SelfWeight"
                    and load.density_override <= 0.0
                    and (
                        self.model.elements.get(load.element_tag) is not None
                        and self.model.elements[load.element_tag].section_tag
                        in elastic_section_users
                    )
                )
            )
            if self_weight_users and material.density <= 0.0:
                raise ValueError(
                    f"Material {original_tag} supplies density to SelfWeight "
                    "load(s) "
                    + ", ".join(map(str, self_weight_users))
                    + " and must keep a positive density or those loads need "
                    "a density override."
                )
        self.materials.pop(original_tag)
        self.materials[material.tag] = material
        if material.tag != original_tag:
            for dependent in self.materials.values():
                if dependent.base_material_tag == original_tag:
                    dependent.base_material_tag = material.tag
                dependent.material_tags = [
                    material.tag if int(tag) == original_tag else int(tag)
                    for tag in dependent.material_tags
                ]
            for section in self.sections.values():
                if section.material_tag == original_tag:
                    section.material_tag = material.tag
                for fiber in section.fibers:
                    if fiber.material_tag == original_tag:
                        fiber.material_tag = material.tag
                for component in section.fiber_components:
                    if component.material_tag == original_tag:
                        component.material_tag = material.tag
            for element in self.model.elements.values():
                if element.truss_material_tag == original_tag:
                    element.truss_material_tag = material.tag
                if element.element_type in {"MVLEM", "MVLEM_3D"}:
                    element.wall_concrete_tags = tuple(
                        material.tag if int(tag) == original_tag else int(tag)
                        for tag in element.wall_concrete_tags
                    )
                    element.wall_steel_tags = tuple(
                        material.tag if int(tag) == original_tag else int(tag)
                        for tag in element.wall_steel_tags
                    )
                    if element.wall_shear_tag == original_tag:
                        element.wall_shear_tag = material.tag
            for connection in self.connections.values():
                connection.materials_by_dof = {
                    int(dof): (
                        material.tag
                        if int(material_tag) == original_tag
                        else int(material_tag)
                    )
                    for dof, material_tag
                    in connection.materials_by_dof.items()
                }
                if connection.connection_type == "BeamColumnJoint":
                    connection.parameters["component_materials"] = [
                        (
                            material.tag
                            if int(material_tag) == original_tag
                            else int(material_tag)
                        )
                        for material_tag in connection.parameters.get(
                            "component_materials",
                            (),
                        )
                    ]
            for recorder in self.recorders.values():
                if (
                    recorder.recorder_type == "Fiber"
                    and recorder.material_tag == original_tag
                ):
                    recorder.material_tag = material.tag
            for nd_material in self.nd_materials.values():
                if nd_material.material_type == "OrthotropicRAConcrete":
                    if (
                        int(round(nd_material.parameters["conc"]))
                        == original_tag
                    ):
                        nd_material.parameters["conc"] = float(material.tag)
                elif nd_material.material_type == "SmearedSteelDoubleLayer":
                    for key in ("mat1", "mat2"):
                        if (
                            int(round(nd_material.parameters[key]))
                            == original_tag
                        ):
                            nd_material.parameters[key] = float(material.tag)
                elif nd_material.material_type == "FSAM":
                    for key in ("sX", "sY", "conc"):
                        if (
                            int(round(nd_material.parameters[key]))
                            == original_tag
                        ):
                            nd_material.parameters[key] = float(material.tag)

    def remove_material(self, tag: int) -> None:
        tag = _strict_int(tag, "Material tag")
        dependent_materials = self.materials_using_material(tag)
        dependent_sections = self.sections_using_material(tag)
        dependent_nd_materials = self.nd_materials_using_material(tag)
        dependent_trusses = sorted(
            element.tag
            for element in self.model.elements.values()
            if element.truss_material_tag == tag
        )
        dependent_wall_elements = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                element.element_type in {"MVLEM", "MVLEM_3D"}
                and (
                    tag in element.wall_concrete_tags
                    or tag in element.wall_steel_tags
                    or element.wall_shear_tag == tag
                )
            )
        )
        dependent_connections = self.connections_using_material(tag)
        dependent_recorders = sorted(
            recorder.tag
            for recorder in self.recorders.values()
            if (
                recorder.recorder_type == "Fiber"
                and recorder.material_tag == tag
            )
        )
        if (
            dependent_materials
            or dependent_sections
            or dependent_nd_materials
            or dependent_trusses
            or dependent_wall_elements
            or dependent_connections
            or dependent_recorders
        ):
            details = []
            if dependent_materials:
                details.append(
                    "materials " + ", ".join(map(str, dependent_materials))
                )
            if dependent_sections:
                details.append(
                    "sections " + ", ".join(map(str, dependent_sections))
                )
            if dependent_nd_materials:
                details.append(
                    "nDMaterials "
                    + ", ".join(map(str, dependent_nd_materials))
                )
            if dependent_trusses:
                details.append(
                    "truss elements "
                    + ", ".join(map(str, dependent_trusses))
                )
            if dependent_wall_elements:
                details.append(
                    "wall macro-elements "
                    + ", ".join(map(str, dependent_wall_elements))
                )
            if dependent_connections:
                details.append(
                    "connections "
                    + ", ".join(map(str, dependent_connections))
                )
            if dependent_recorders:
                details.append(
                    "recorders " + ", ".join(map(str, dependent_recorders))
                )
            raise ValueError(
                f"Material {tag} is still referenced by "
                + "; ".join(details)
                + ". Reassign those references before deleting it."
            )
        self.materials.pop(tag, None)

    def next_section_tag(self) -> int:
        return max(self.sections, default=0) + 1

    def add_section(self, section: SectionData) -> None:
        if section.tag in self.sections:
            raise ValueError(f"Section tag {section.tag} already exists.")
        self._validate_section_materials(section)
        self.sections[section.tag] = section

    def update_section(self, original_tag: int, section: SectionData) -> None:
        original_tag = _strict_int(
            original_tag,
            "Section original tag",
        )
        if original_tag not in self.sections:
            raise ValueError(f"Section tag {original_tag} does not exist.")
        if section.tag != original_tag and section.tag in self.sections:
            raise ValueError(f"Section tag {section.tag} already exists.")
        self._validate_section_materials(section)
        elastic_beam_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                element.element_type
                in {"elasticBeamColumn", "ElasticTimoshenkoBeam"}
                and element.section_tag == original_tag
            )
        )
        if elastic_beam_users and section.section_type != "Elastic":
            raise ValueError(
                f"Section {original_tag} is used by elastic frame "
                "element(s) "
                + ", ".join(map(str, elastic_beam_users))
                + " and must remain an Elastic section."
            )

        fiber_int_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                element.element_type == "dispBeamColumnInt"
                and element.section_tag == original_tag
            )
        )
        if fiber_int_users and section.section_type != "FiberInt":
            raise ValueError(
                f"Section {original_tag} is used by dispBeamColumnInt "
                "element(s) "
                + ", ".join(map(str, fiber_int_users))
                + " and must remain a FiberInt section."
            )

        shell_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                element.element_type in SHELL_ELEMENT_TYPES
                and element.section_tag == original_tag
            )
        )
        if shell_users and section.section_type not in SHELL_SECTION_TYPES:
            raise ValueError(
                f"Section {original_tag} is used by Shell element(s) "
                + ", ".join(map(str, shell_users))
                + " and must remain a shell-compatible section."
            )

        self_weight_users = sorted(
            load.tag
            for load in self.element_loads.values()
            if (
                load.load_type == "SelfWeight"
                and self.model.elements.get(load.element_tag) is not None
                and self.model.elements[load.element_tag].section_tag
                == original_tag
            )
        )
        if self_weight_users:
            if section.section_type != "Elastic":
                raise ValueError(
                    f"Section {original_tag} is used by SelfWeight load(s) "
                    + ", ".join(map(str, self_weight_users))
                    + " and must remain an Elastic section."
                )
            needs_linked_density = [
                load_tag
                for load_tag in self_weight_users
                if self.element_loads[load_tag].density_override <= 0.0
            ]
            if needs_linked_density:
                material = (
                    self.materials.get(int(section.material_tag))
                    if section.material_tag is not None
                    else None
                )
                if material is None or material.density <= 0.0:
                    raise ValueError(
                        f"Section {original_tag} supplies SelfWeight load(s) "
                        + ", ".join(map(str, needs_linked_density))
                        + " and must stay linked to a material with positive "
                        "density or those loads need a density override."
                    )
        self.sections.pop(original_tag)
        self.sections[section.tag] = section
        if section.tag != original_tag:
            for element in self.model.elements.values():
                if element.section_tag == original_tag:
                    element.section_tag = section.tag
                if element.element_type == "MEFI":
                    element.mefi_section_tags = tuple(
                        section.tag if int(tag) == original_tag else int(tag)
                        for tag in element.mefi_section_tags
                    )
                if element.hinge_i_section_tag == original_tag:
                    element.hinge_i_section_tag = section.tag
                if element.hinge_j_section_tag == original_tag:
                    element.hinge_j_section_tag = section.tag
                if element.interior_section_tag == original_tag:
                    element.interior_section_tag = section.tag
            for connection in self.connections.values():
                if connection.section_tag == original_tag:
                    connection.section_tag = section.tag
                if connection.generated_section_tag == original_tag:
                    connection.generated_section_tag = section.tag

    def connections_using_section(self, section_tag: int) -> list[int]:
        target = _strict_int(section_tag, "Section tag")
        return sorted(
            connection.tag
            for connection in self.connections.values()
            if (
                connection.section_tag == target
                or connection.generated_section_tag == target
            )
        )

    def remove_section(self, tag: int) -> None:
        tag = _strict_int(tag, "Section tag")
        element_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if (
                tag in {
                    element.section_tag,
                    element.hinge_i_section_tag,
                    element.hinge_j_section_tag,
                    element.interior_section_tag,
                }
                or (
                    element.element_type == "MEFI"
                    and tag in element.mefi_section_tags
                )
            )
        )
        connection_users = self.connections_using_section(tag)
        if element_users or connection_users:
            details = []
            if element_users:
                details.append(
                    "elements " + ", ".join(map(str, element_users))
                )
            if connection_users:
                details.append(
                    "connections " + ", ".join(map(str, connection_users))
                )
            raise ValueError(
                f"Section {tag} is still referenced by "
                + "; ".join(details)
                + ". Reassign those references before deleting it."
            )
        self.sections.pop(tag, None)

    def _validate_section_materials(self, section: SectionData) -> None:
        if section.section_type in {
            "PlateFiber", "LayeredShell", "RCLMS",
        }:
            missing_nd = sorted(
                tag
                for tag in section.shell_nd_material_tags()
                if tag not in self.nd_materials
            )
            if missing_nd:
                raise ValueError(
                    f"{section.section_type} section references missing "
                    "nDMaterial tag(s): "
                    + ", ".join(map(str, missing_nd))
                )
            if section.section_type == "RCLMS":
                steel = self.nd_materials[int(section.nd_material_tag)]
                if steel.material_type != "SmearedSteelDoubleLayer":
                    raise ValueError(
                        "RCLMS reinforcing layer must use "
                        "SmearedSteelDoubleLayer."
                    )
                invalid_concrete = [
                    int(layer.material_tag)
                    for layer in section.shell_layers
                    if self.nd_materials[
                        int(layer.material_tag)
                    ].material_type != "OrthotropicRAConcrete"
                ]
                if invalid_concrete:
                    raise ValueError(
                        "RCLMS concrete layers must use "
                        "OrthotropicRAConcrete nDMaterials."
                    )
            return

        if section.section_type == "Elastic":
            if (
                section.material_tag is not None
                and section.material_tag not in self.materials
            ):
                raise ValueError(
                    f"Elastic section references missing material tag "
                    f"{section.material_tag}."
                )
            if section.material_tag is not None:
                material = self.materials[section.material_tag]
                try:
                    material.elastic_modulus()
                    material.shear_modulus()
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "Elastic section material "
                        f"{section.material_tag} does not expose a usable "
                        "elastic/shear modulus."
                    ) from exc
            return

        if section.section_type not in {"Fiber", "FiberInt"}:
            return

        missing = sorted(
            material_tag
            for material_tag in section.fiber_material_tags()
            if material_tag not in self.materials
        )
        if missing:
            raise ValueError(
                f"{section.section_type} section references missing material "
                "tag(s): " + ", ".join(map(str, missing))
            )
        if section.section_type == "FiberInt":
            concrete_types = {
                "Concrete01", "Concrete02", "Concrete04", "ConcreteCM",
                "FRPConfinedConcrete", "FRPConfinedConcrete02",
            }
            steel_types = {
                "Steel01", "Steel02", "RambergOsgoodSteel", "Hardening",
                "ElasticPP", "ElasticBilin", "ReinforcingSteel",
            }
            for fiber in section.fibers:
                material = self.materials[fiber.material_tag]
                if material.material_type in concrete_types:
                    if fiber.material_tag > 1000:
                        raise ValueError(
                            "FiberInt concrete material tags must be <= 1000."
                        )
                elif material.material_type in steel_types:
                    if fiber.material_tag <= 1000:
                        raise ValueError(
                            "FiberInt steel material tags must be > 1000."
                        )
                else:
                    raise ValueError(
                        "FiberInt vertical fibers must use concrete or steel "
                        "uniaxial materials."
                    )
            for fiber in section.horizontal_fibers:
                material = self.materials[fiber.material_tag]
                if (
                    material.material_type not in steel_types
                    or fiber.material_tag <= 1000
                ):
                    raise ValueError(
                        "FiberInt Hfiber reinforcement must use a steel "
                        "material tag > 1000."
                    )

    def sections_using_material(self, material_tag: int) -> list[int]:
        material_tag = _strict_int(material_tag, "Material tag")
        return sorted(
            section.tag
            for section in self.sections.values()
            if (
                section.material_tag == material_tag
                or material_tag in section.fiber_material_tags()
            )
        )

    def _validate_element_geometry(
        self,
        element,
        *,
        transformation: TransformationData | None = None,
    ) -> None:
        node_tags = tuple(int(tag) for tag in element.node_tags())
        missing = [tag for tag in node_tags if tag not in self.model.nodes]
        if missing:
            raise ValueError(
                f"Element {element.tag} references missing node tag(s): "
                + ", ".join(map(str, missing))
            )

        if element.element_type in (
            SHELL_ELEMENT_TYPES | WALL_MACRO_3D_ELEMENT_TYPES
        ):
            if (int(self.model.ndm), int(self.model.ndf)) != (3, 6):
                raise ValueError(
                    f"{element.element_type} element {element.tag} requires "
                    "ndm=3 and ndf=6."
                )
            p = [
                tuple(float(value) for value in self.model.nodes[tag].xyz)
                for tag in node_tags
            ]

            def triangle_area2(a, b, c) -> float:
                ab = tuple(b[i] - a[i] for i in range(3))
                ac = tuple(c[i] - a[i] for i in range(3))
                cross = (
                    ab[1] * ac[2] - ab[2] * ac[1],
                    ab[2] * ac[0] - ab[0] * ac[2],
                    ab[0] * ac[1] - ab[1] * ac[0],
                )
                return math.sqrt(sum(value * value for value in cross))

            area2 = triangle_area2(p[0], p[1], p[2])
            area2 += triangle_area2(p[0], p[2], p[3])
            if area2 <= 1.0e-12:
                raise ValueError(
                    f"Shell element {element.tag} has zero or near-zero area."
                )

            # Use a Newell polygon normal plus a dominant-plane projection to
            # catch crossed or concave quadrilateral node ordering.  These
            # topologies can have non-zero triangle area yet still produce an
            # invalid/inverted shell mapping.
            normal = [0.0, 0.0, 0.0]
            for index in range(4):
                current = p[index]
                following = p[(index + 1) % 4]
                normal[0] += (
                    (current[1] - following[1])
                    * (current[2] + following[2])
                )
                normal[1] += (
                    (current[2] - following[2])
                    * (current[0] + following[0])
                )
                normal[2] += (
                    (current[0] - following[0])
                    * (current[1] + following[1])
                )
            normal = tuple(normal)
            normal_norm2 = sum(value * value for value in normal)
            if normal_norm2 <= 1.0e-24:
                raise ValueError(
                    f"Shell element {element.tag} has invalid quadrilateral "
                    "node ordering (crossed or degenerate boundary)."
                )

            drop_axis = max(
                range(3),
                key=lambda axis: abs(normal[axis]),
            )
            projected = [
                tuple(
                    point[axis]
                    for axis in range(3)
                    if axis != drop_axis
                )
                for point in p
            ]

            def orient2d(a, b, c) -> float:
                return (
                    (b[0] - a[0]) * (c[1] - a[1])
                    - (b[1] - a[1]) * (c[0] - a[0])
                )

            def proper_intersection(a, b, c, d) -> bool:
                o1 = orient2d(a, b, c)
                o2 = orient2d(a, b, d)
                o3 = orient2d(c, d, a)
                o4 = orient2d(c, d, b)
                scale = max(
                    abs(o1), abs(o2), abs(o3), abs(o4), 1.0
                )
                tol = 1.0e-12 * scale
                return (
                    o1 * o2 < -(tol * tol)
                    and o3 * o4 < -(tol * tol)
                )

            if (
                proper_intersection(
                    projected[0], projected[1],
                    projected[2], projected[3],
                )
                or proper_intersection(
                    projected[1], projected[2],
                    projected[3], projected[0],
                )
            ):
                raise ValueError(
                    f"Shell element {element.tag} has self-intersecting "
                    "quadrilateral node ordering."
                )

            turns = [
                orient2d(
                    projected[index],
                    projected[(index + 1) % 4],
                    projected[(index + 2) % 4],
                )
                for index in range(4)
            ]
            turn_scale = max(
                max(abs(value) for value in turns),
                1.0,
            )
            meaningful = [
                value
                for value in turns
                if abs(value) > 1.0e-12 * turn_scale
            ]
            if (
                meaningful
                and min(meaningful) < 0.0 < max(meaningful)
            ):
                raise ValueError(
                    f"Shell element {element.tag} is concave; use a convex "
                    "four-node boundary or remesh the surface."
                )

            if element.shell_local_x is not None:
                local_x = tuple(
                    float(value)
                    for value in element.shell_local_x
                )
                cross = (
                    local_x[1] * normal[2]
                    - local_x[2] * normal[1],
                    local_x[2] * normal[0]
                    - local_x[0] * normal[2],
                    local_x[0] * normal[1]
                    - local_x[1] * normal[0],
                )
                local_norm2 = sum(value * value for value in local_x)
                normal_norm2 = sum(value * value for value in normal)
                cross_norm2 = sum(value * value for value in cross)
                if (
                    normal_norm2 > 1.0e-24
                    and cross_norm2
                    <= 1.0e-16 * local_norm2 * normal_norm2
                ):
                    raise ValueError(
                        f"Shell element {element.tag} local X vector is "
                        "parallel to the shell normal; choose an in-plane "
                        "direction."
                    )
            return

        node_i = self.model.nodes[int(element.i)]
        node_j = self.model.nodes[int(element.j)]
        delta = tuple(
            float(node_j.xyz[index]) - float(node_i.xyz[index])
            for index in range(3)
        )
        length2 = sum(value * value for value in delta)
        if length2 <= 1.0e-24:
            raise ValueError(
                f"Element {element.tag} has coincident end nodes and zero length."
            )

        if (
            int(self.model.ndm) != 3
            or element.element_type not in FRAME_ELEMENT_TYPES
        ):
            return

        active_transformation = transformation
        if active_transformation is None and element.transf_tag is not None:
            active_transformation = self.transformations.get(
                int(element.transf_tag)
            )
        if active_transformation is None:
            return

        effective_vecxz = (
            resolve_transformation_vecxz(
                self.model,
                active_transformation,
            )
            if active_transformation.orientation_mode == "auto"
            else active_transformation.vecxz
        )
        vx, vy, vz = (
            float(value) for value in effective_vecxz
        )
        dx, dy, dz = delta
        cross = (
            vy * dz - vz * dy,
            vz * dx - vx * dz,
            vx * dy - vy * dx,
        )
        vec_norm2 = vx * vx + vy * vy + vz * vz
        cross_norm2 = sum(value * value for value in cross)
        if cross_norm2 <= 1.0e-16 * vec_norm2 * length2:
            raise ValueError(
                f"Transformation {active_transformation.tag} vecxz is "
                f"parallel to element {element.tag}; choose an orientation "
                "vector not parallel to the member axis."
            )

    def next_transformation_tag(self) -> int:
        return max(self.transformations, default=0) + 1

    def add_transformation(self, transformation: TransformationData) -> None:
        if transformation.tag in self.transformations:
            raise ValueError(
                f"Transformation tag {transformation.tag} already exists."
            )
        for element in self.model.elements.values():
            if element.transf_tag == transformation.tag:
                self._validate_element_geometry(
                    element,
                    transformation=transformation,
                )
        self.transformations[transformation.tag] = transformation

    def update_transformation(
        self,
        original_tag: int,
        transformation: TransformationData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Transformation original tag",
        )
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
        for element in self.model.elements.values():
            if element.transf_tag == original_tag:
                self._validate_element_geometry(
                    element,
                    transformation=transformation,
                )
        self.transformations.pop(original_tag)
        self.transformations[transformation.tag] = transformation
        if transformation.tag != original_tag:
            for element in self.model.elements.values():
                if element.transf_tag == original_tag:
                    element.transf_tag = transformation.tag

    def remove_transformation(self, tag: int) -> None:
        tag = _strict_int(tag, "Transformation tag")
        element_users = sorted(
            element.tag
            for element in self.model.elements.values()
            if element.transf_tag == tag
        )
        if element_users:
            raise ValueError(
                f"Transformation {tag} is still referenced by element(s): "
                + ", ".join(map(str, element_users))
                + ". Reassign those elements before deleting it."
            )
        self.transformations.pop(tag, None)

    def next_constraint_tag(self) -> int:
        return max(self.constraints, default=0) + 1

    def _validate_constraint_model_compatibility(
        self,
        constraint: ConstraintData,
    ) -> None:
        if constraint.constraint_type == "equalDOF":
            invalid_dofs = sorted(
                dof
                for dof in constraint.dofs
                if dof > int(self.model.ndf)
            )
            if invalid_dofs:
                raise ValueError(
                    f"equalDOF constraint {constraint.tag} references DOF(s) "
                    + ", ".join(map(str, invalid_dofs))
                    + f" not available for model ndf={self.model.ndf}."
                )
            return

        if constraint.constraint_type == "rigidLink":
            ndm = int(self.model.ndm)
            ndf = int(self.model.ndf)
            if constraint.link_type == "bar":
                if ndf < ndm:
                    raise ValueError(
                        f"rigidLink bar constraint {constraint.tag} requires "
                        f"ndf >= ndm; got ndm={ndm}, ndf={ndf}."
                    )
                return

            valid_beam_signature = (
                ndf == ndm
                or (ndm, ndf) in {(2, 3), (3, 6)}
            )
            if not valid_beam_signature:
                raise ValueError(
                    f"rigidLink beam constraint {constraint.tag} requires "
                    "ndf == ndm, 2D/3DOF, or 3D/6DOF; got "
                    f"ndm={ndm}, ndf={ndf}."
                )
            return

        if constraint.constraint_type != "rigidDiaphragm":
            return
        signature = (int(self.model.ndm), int(self.model.ndf))
        if signature not in {(2, 3), (3, 6)}:
            raise ValueError(
                f"rigidDiaphragm constraint {constraint.tag} requires a "
                "2D/3DOF or 3D/6DOF model; got "
                f"ndm={self.model.ndm}, ndf={self.model.ndf}."
            )

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

    def _rigid_diaphragm_dependent_dofs(
        self,
        constraint: ConstraintData,
    ) -> set[int]:
        if self.model.ndm == 3 and self.model.ndf == 6:
            return {
                1: {2, 3, 4},
                2: {1, 3, 5},
                3: {1, 2, 6},
            }.get(int(constraint.perp_dirn), set())
        if self.model.ndm == 2 and self.model.ndf == 3:
            return {
                1: {1},
                2: {2},
                3: {1, 2, 3},
            }.get(int(constraint.perp_dirn), set())
        return set()

    def _constraint_dependent_dofs(
        self,
        constraint: ConstraintData,
    ) -> set[int]:
        if constraint.constraint_type == "equalDOF":
            return {
                int(dof)
                for dof in constraint.dofs
                if 1 <= int(dof) <= int(self.model.ndf)
            }
        if constraint.constraint_type == "rigidLink":
            if constraint.link_type == "beam":
                return set(range(1, int(self.model.ndf) + 1))
            return set(
                range(
                    1,
                    min(int(self.model.ndm), int(self.model.ndf)) + 1,
                )
            )
        if constraint.constraint_type == "rigidDiaphragm":
            return self._rigid_diaphragm_dependent_dofs(constraint)
        return set()

    def _validate_constraint_dependency_conflicts(
        self,
        constraint: ConstraintData,
        *,
        ignore_constraint_tags: set[int] | None = None,
    ) -> None:
        dependent_dofs = self._constraint_dependent_dofs(constraint)
        if not dependent_dofs:
            return

        support_conflicts: list[tuple[int, int]] = []
        for node_tag in constraint.constrained_nodes:
            node = self.model.nodes.get(node_tag)
            if node is None:
                continue
            for dof in sorted(dependent_dofs):
                if (
                    dof <= len(node.fixity)
                    and bool(node.fixity[dof - 1])
                ):
                    support_conflicts.append((int(node_tag), int(dof)))
        if support_conflicts:
            details = ", ".join(
                f"node {node_tag} DOF {dof}"
                for node_tag, dof in support_conflicts
            )
            raise ValueError(
                f"{constraint.constraint_type} constraint {constraint.tag} "
                "assigns dependent DOF(s) that are already fixed by a "
                f"support: {details}."
            )

        ignored = {
            int(tag) for tag in (ignore_constraint_tags or set())
        }
        overlap_conflicts: list[tuple[int, int, int]] = []
        constrained_nodes = {
            int(tag) for tag in constraint.constrained_nodes
        }
        for existing_tag, existing in self.constraints.items():
            if int(existing_tag) in ignored:
                continue
            common_nodes = constrained_nodes & {
                int(tag) for tag in existing.constrained_nodes
            }
            if not common_nodes:
                continue
            common_dofs = dependent_dofs & self._constraint_dependent_dofs(
                existing
            )
            for node_tag in sorted(common_nodes):
                for dof in sorted(common_dofs):
                    overlap_conflicts.append(
                        (node_tag, dof, int(existing.tag))
                    )

        if overlap_conflicts:
            details = ", ".join(
                f"node {node_tag} DOF {dof} (existing constraint {tag})"
                for node_tag, dof, tag in overlap_conflicts
            )
            raise ValueError(
                f"{constraint.constraint_type} constraint {constraint.tag} "
                "overlaps an existing MPC on the same dependent DOF(s): "
                + details
                + "."
            )

        prescribed_conflicts: list[tuple[int, int, int, int]] = []
        constrained_nodes = {
            int(tag) for tag in constraint.constrained_nodes
        }
        for displacement in self.prescribed_displacements.values():
            if (
                int(displacement.node_tag) not in constrained_nodes
                or int(displacement.dof) not in dependent_dofs
            ):
                continue
            for analysis_tag, analysis in self.analyses.items():
                if self._analysis_pattern_is_active(
                    analysis,
                    displacement.pattern_tag,
                    ignore_analysis_tags={int(analysis_tag)},
                ):
                    prescribed_conflicts.append(
                        (
                            int(displacement.tag),
                            int(displacement.node_tag),
                            int(displacement.dof),
                            int(analysis.tag),
                        )
                    )
                    break

        if prescribed_conflicts:
            details = ", ".join(
                f"SP {sp_tag} at node {node_tag} DOF {dof} "
                f"(analysis {analysis_tag})"
                for sp_tag, node_tag, dof, analysis_tag
                in prescribed_conflicts
            )
            raise ValueError(
                f"{constraint.constraint_type} constraint {constraint.tag} "
                "assigns dependent DOF(s) that also have active Prescribed "
                "Displacement objects: "
                + details
                + "."
            )

    def _plain_handler_supports_constraint(
        self,
        constraint: ConstraintData,
    ) -> bool:
        if constraint.constraint_type == "equalDOF":
            return True
        if constraint.constraint_type == "rigidLink":
            if constraint.link_type == "bar":
                return True
            if int(self.model.ndf) == int(self.model.ndm):
                return True
            retained = self.model.nodes[constraint.retained_node]
            for node_tag in constraint.constrained_nodes:
                constrained = self.model.nodes[node_tag]
                if any(
                    float(constrained.xyz[i]) != float(retained.xyz[i])
                    for i in range(int(self.model.ndm))
                ):
                    return False
            return True
        if constraint.constraint_type == "rigidDiaphragm":
            retained = self.model.nodes[constraint.retained_node]
            for node_tag in constraint.constrained_nodes:
                constrained = self.model.nodes[node_tag]
                if self.model.ndm == 2 and self.model.ndf == 3:
                    dx = float(constrained.xyz[0]) - float(retained.xyz[0])
                    dy = float(constrained.xyz[1]) - float(retained.xyz[1])
                    if constraint.perp_dirn == 3 and (
                        dx != 0.0 or dy != 0.0
                    ):
                        return False
                elif self.model.ndm == 3 and self.model.ndf == 6:
                    dx = float(constrained.xyz[0]) - float(retained.xyz[0])
                    dy = float(constrained.xyz[1]) - float(retained.xyz[1])
                    dz = float(constrained.xyz[2]) - float(retained.xyz[2])
                    offsets = {
                        1: (dy, dz),
                        2: (dx, dz),
                        3: (dx, dy),
                    }.get(constraint.perp_dirn, ())
                    if any(value != 0.0 for value in offsets):
                        return False
            return True
        return True

    def _validate_analysis_constraint_handler_compatibility(
        self,
        analysis: AnalysisSettingsData,
        *,
        candidate_constraint: ConstraintData | None = None,
        ignore_constraint_tags: set[int] | None = None,
        candidate_connection: ConnectionData | None = None,
        ignore_connection_tags: set[int] | None = None,
    ) -> None:
        ignored_connections = {
            int(tag) for tag in (ignore_connection_tags or set())
        }
        has_joint2d = any(
            (
                int(tag) not in ignored_connections
                and connection.connection_type == "Joint2D"
            )
            for tag, connection in self.connections.items()
        )
        if (
            candidate_connection is not None
            and candidate_connection.connection_type == "Joint2D"
        ):
            has_joint2d = True
        if (
            has_joint2d
            and analysis.constraints_handler != "Transformation"
        ):
            raise ValueError(
                "Joint2D connections require the Transformation constraint "
                "handler in SARE. Change Analysis > Constraints Handler to "
                "Transformation before using Joint2D."
            )

        def _rigid_connection_has_offset(
            connection: ConnectionData,
        ) -> bool:
            if connection.connection_type != "rigid":
                return False
            node_i = self.model.nodes.get(int(connection.node_i))
            node_j = self.model.nodes.get(int(connection.node_j))
            if node_i is None or node_j is None:
                return False
            return any(
                abs(float(a) - float(b)) > 1.0e-12
                for a, b in zip(node_i.xyz, node_j.xyz)
            )

        has_offset_rigid = any(
            (
                int(tag) not in ignored_connections
                and _rigid_connection_has_offset(connection)
            )
            for tag, connection in self.connections.items()
        )
        if (
            candidate_connection is not None
            and _rigid_connection_has_offset(candidate_connection)
        ):
            has_offset_rigid = True
        if (
            has_offset_rigid
            and analysis.constraints_handler != "Transformation"
        ):
            raise ValueError(
                "Rigid connections between separated nodes use rigidLink "
                "beam offset constraints and require the Transformation "
                "constraint handler in SARE."
            )

        ignored = {
            int(tag) for tag in (ignore_constraint_tags or set())
        }
        active_constraints = [
            constraint
            for tag, constraint in self.constraints.items()
            if int(tag) not in ignored
        ]
        if candidate_constraint is not None:
            active_constraints.append(candidate_constraint)
        if not active_constraints:
            return

        constrained_by_node: dict[int, list[int]] = {}
        for constraint in active_constraints:
            for node_tag in constraint.constrained_nodes:
                constrained_by_node.setdefault(
                    int(node_tag),
                    [],
                ).append(int(constraint.tag))

        chain_conflicts: list[tuple[int, int, list[int]]] = []
        for constraint in active_constraints:
            retained_node = int(constraint.retained_node)
            upstream = sorted({
                int(tag)
                for tag in constrained_by_node.get(retained_node, [])
                if int(tag) != int(constraint.tag)
            })
            if upstream:
                chain_conflicts.append(
                    (int(constraint.tag), retained_node, upstream)
                )

        if chain_conflicts and analysis.constraints_handler in {
            "Transformation",
            "Plain",
        }:
            details = "; ".join(
                f"constraint {tag} retains node {node_tag}, which is "
                "constrained by "
                + ", ".join(map(str, upstream))
                for tag, node_tag, upstream in chain_conflicts
            )
            raise ValueError(
                f"{analysis.constraints_handler} constraint handler does "
                "not follow chained MP constraints: "
                + details
                + ". A retained node must not be constrained in another "
                "MP constraint."
            )

        if analysis.constraints_handler == "Transformation":
            by_node: dict[int, list[int]] = {}
            for constraint in active_constraints:
                for node_tag in constraint.constrained_nodes:
                    by_node.setdefault(int(node_tag), []).append(
                        int(constraint.tag)
                    )
            conflicts = {
                node_tag: sorted(tags)
                for node_tag, tags in by_node.items()
                if len(tags) > 1
            }
            if conflicts:
                details = "; ".join(
                    f"node {node_tag}: "
                    + ", ".join(map(str, tags))
                    for node_tag, tags in sorted(conflicts.items())
                )
                raise ValueError(
                    "Transformation constraint handler supports only one "
                    "MP constraint object per constrained node in Studio; "
                    "multiple MP objects found at "
                    + details
                    + "."
                )

        if analysis.constraints_handler == "Plain":
            unsupported = sorted(
                int(constraint.tag)
                for constraint in active_constraints
                if not self._plain_handler_supports_constraint(constraint)
            )
            if unsupported:
                raise ValueError(
                    "Plain constraint handler would ignore non-identity "
                    "MP transformation matrix for constraint(s): "
                    + ", ".join(map(str, unsupported))
                    + ". Use the Transformation constraint handler."
                )

    def _validate_constraint_control_conflicts(
        self,
        constraint: ConstraintData,
        *,
        ignore_analysis_tags: set[int] | None = None,
    ) -> None:
        if constraint.constraint_type not in {
            "equalDOF",
            "rigidLink",
            "rigidDiaphragm",
        }:
            return
        ignored = {
            int(tag) for tag in (ignore_analysis_tags or set())
        }

        def constrains_control_dof(
            analysis: AnalysisSettingsData,
        ) -> bool:
            if analysis.control_node not in constraint.constrained_nodes:
                return False
            if constraint.constraint_type == "equalDOF":
                return analysis.control_dof in constraint.dofs
            if constraint.constraint_type == "rigidDiaphragm":
                return (
                    analysis.control_dof
                    in self._rigid_diaphragm_dependent_dofs(constraint)
                )
            if constraint.link_type == "beam":
                return True
            return analysis.control_dof <= min(
                int(self.model.ndm),
                int(self.model.ndf),
            )

        conflicts = sorted(
            analysis.tag
            for analysis_tag, analysis in self.analyses.items()
            if (
                int(analysis_tag) not in ignored
                and self._analysis_uses_control_node(analysis)
                and constrains_control_dof(analysis)
            )
        )
        if conflicts:
            raise ValueError(
                f"{constraint.constraint_type} constraint {constraint.tag} "
                "makes a DisplacementControl DOF dependent for analysis "
                "tag(s): "
                + ", ".join(map(str, conflicts))
                + ". Use the retained node or another independent DOF."
            )

    def add_constraint(self, constraint: ConstraintData) -> None:
        if constraint.tag in self.constraints:
            raise ValueError(
                f"Constraint tag {constraint.tag} already exists."
            )
        self._validate_constraint_model_compatibility(constraint)
        self._validate_constraint_nodes(constraint)
        self._validate_constraint_dependency_conflicts(constraint)
        for analysis in self.analyses.values():
            self._validate_analysis_constraint_handler_compatibility(
                analysis,
                candidate_constraint=constraint,
            )
        self._validate_constraint_control_conflicts(constraint)
        self.constraints[constraint.tag] = constraint

    def update_constraint(
        self,
        original_tag: int,
        constraint: ConstraintData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Constraint original tag",
        )
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
        self._validate_constraint_model_compatibility(constraint)
        self._validate_constraint_nodes(constraint)
        self._validate_constraint_dependency_conflicts(
            constraint,
            ignore_constraint_tags={original_tag},
        )
        for analysis in self.analyses.values():
            self._validate_analysis_constraint_handler_compatibility(
                analysis,
                candidate_constraint=constraint,
                ignore_constraint_tags={original_tag},
            )
        self._validate_constraint_control_conflicts(constraint)
        self.constraints.pop(original_tag)
        self.constraints[constraint.tag] = constraint
        if constraint.tag != original_tag:
            for connection in self.connections.values():
                if connection.generated_constraint_tag == original_tag:
                    connection.generated_constraint_tag = constraint.tag

    def remove_constraint(self, tag: int) -> None:
        tag = _strict_int(tag, "Constraint tag")
        self.constraints.pop(tag, None)
        for connection in self.connections.values():
            if connection.generated_constraint_tag == tag:
                connection.generated_constraint_tag = None

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
        if removed:
            removed_set = set(removed)
            for connection in self.connections.values():
                if connection.generated_constraint_tag in removed_set:
                    connection.generated_constraint_tag = None
        return sorted(removed)

    def next_element_tag(self) -> int:
        """Return the next OpenSees element tag across frames and connections."""
        return max(
            set(self.model.elements) | set(self.connections),
            default=0,
        ) + 1

    def next_connection_tag(self) -> int:
        return self.next_element_tag()

    def _validate_connection(self, connection: ConnectionData) -> None:
        if connection.tag in self.model.elements:
            raise ValueError(
                f"Connection tag {connection.tag} conflicts with an element tag."
            )
        if (
            connection.generated_ground_node is not None
            and connection.generated_ground_node
            not in {connection.node_i, connection.node_j}
        ):
            raise ValueError(
                "Generated ground node must be one of the connection "
                "endpoint nodes."
            )

        referenced_nodes = {connection.node_i, connection.node_j}
        if connection.connection_type in {
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }:
            referenced_nodes.update(
                int(tag)
                for tag in connection.parameters.get("external_nodes", ())
            )
        missing_nodes = sorted(
            tag for tag in referenced_nodes if tag not in self.model.nodes
        )
        if missing_nodes:
            raise ValueError(
                "Connection references missing node tag(s): "
                + ", ".join(map(str, missing_nodes))
            )

        connection_directions = set(connection.materials_by_dof)
        if connection.connection_type in {"zeroLength", "semiRigid"}:
            if int(self.model.ndm) == 2 and int(self.model.ndf) == 3:
                allowed_directions = {1, 2, 6}
            elif int(self.model.ndm) == 3 and int(self.model.ndf) >= 6:
                allowed_directions = {1, 2, 3, 4, 5, 6}
            else:
                allowed_directions = {
                    direction
                    for direction in (1, 2, 3)
                    if direction <= int(self.model.ndf)
                }
        elif connection.connection_type == "CoupledZeroLength":
            # CoupledZeroLength directions are nodal DOF indices, documented
            # as 1..ndf (unlike zeroLength's physical dir 6 for planar RZ).
            allowed_directions = set(
                range(1, min(int(self.model.ndf), 6) + 1)
            )
        elif connection.connection_type == "twoNodeLink":
            # twoNodeLink uses element basic directions. In a 2D/3-DOF
            # frame its rotational direction is 3, unlike zeroLength where
            # local RZ is direction 6.
            allowed_directions = set(
                range(1, min(int(self.model.ndf), 6) + 1)
            )
        else:
            allowed_directions = set()

        if connection.connection_type == "twoNodeLink":
            p_delta = list(connection.parameters.get("p_delta", ()))
            shear_dist = list(connection.parameters.get("shear_dist", ()))
            expected_p_delta = 2 if int(self.model.ndm) == 2 else 4
            expected_shear = 1 if int(self.model.ndm) == 2 else 2
            if p_delta and len(p_delta) != expected_p_delta:
                raise ValueError(
                    f"twoNodeLink in {self.model.ndm}D requires "
                    f"{expected_p_delta} p_delta ratio value(s)."
                )
            if shear_dist and len(shear_dist) != expected_shear:
                raise ValueError(
                    f"twoNodeLink in {self.model.ndm}D requires "
                    f"{expected_shear} shear_dist value(s)."
                )

        invalid_dofs = sorted(
            direction
            for direction in connection_directions
            if direction not in allowed_directions
        )
        if invalid_dofs:
            raise ValueError(
                f"{connection.connection_type} direction(s) "
                + ", ".join(map(str, invalid_dofs))
                + (
                    " are not available for "
                    f"ndm={self.model.ndm}, ndf={self.model.ndf}. "
                    f"Allowed directions: {sorted(allowed_directions)}."
                )
            )

        referenced_materials = set(connection.materials_by_dof.values())
        if connection.connection_type in {"Joint2D", "KrawinklerPanelZone"}:
            referenced_materials.add(
                int(connection.parameters.get("panel_material", 0))
            )
        if connection.connection_type == "BeamColumnJoint":
            referenced_materials.update(
                int(tag)
                for tag in connection.parameters.get(
                    "component_materials",
                    (),
                )
            )
        if connection.connection_type == "LehighJoint2D":
            referenced_materials.update(
                int(tag)
                for tag in connection.parameters.get(
                    "mode_materials",
                    (),
                )
            )
        if connection.connection_type == "Joint2D":
            referenced_materials.update(
                int(tag)
                for tag in connection.parameters.get(
                    "interface_materials",
                    (),
                )
                if int(tag) > 0
            )
        missing_materials = sorted(
            material_tag
            for material_tag in referenced_materials
            if material_tag > 0 and material_tag not in self.materials
        )
        if missing_materials:
            raise ValueError(
                "Connection references missing material tag(s): "
                + ", ".join(map(str, missing_materials))
            )

        if (
            connection.connection_type == "zeroLengthSection"
            and connection.section_tag not in self.sections
        ):
            raise ValueError(
                "zeroLengthSection references missing section tag "
                f"{connection.section_tag}."
            )

        if connection.connection_type in {
            "zeroLength",
            "CoupledZeroLength",
            "zeroLengthSection",
            "semiRigid",
            "pinned",
        }:
            a = self.model.nodes[connection.node_i].xyz
            b = self.model.nodes[connection.node_j].xyz
            distance2 = sum((x - y) ** 2 for x, y in zip(a, b))
            if distance2 > 1.0e-14:
                raise ValueError(
                    f"{connection.connection_type} connection nodes must be "
                    "coincident. Use rigid/twoNodeLink for separated nodes."
                )

        if connection.connection_type == "BeamColumnJoint":
            ndm = int(self.model.ndm)
            ndf = int(self.model.ndf)
            if (ndm, ndf) not in {(2, 3), (3, 6)}:
                raise ValueError(
                    "BeamColumnJoint requires either a 2D frame "
                    "(ndm=2, ndf=3) or a 3D frame (ndm=3, ndf=6)."
                )

            external_tags = [
                int(tag)
                for tag in connection.parameters["external_nodes"]
            ]
            points = [
                tuple(float(value) for value in self.model.nodes[tag].xyz)
                for tag in external_tags
            ]
            chord_13 = tuple(
                points[2][axis] - points[0][axis]
                for axis in range(3)
            )
            chord_24 = tuple(
                points[1][axis] - points[3][axis]
                for axis in range(3)
            )
            length_13 = math.sqrt(
                sum(value * value for value in chord_13)
            )
            length_24 = math.sqrt(
                sum(value * value for value in chord_24)
            )
            scale = max(length_13, length_24, 1.0)
            tolerance = 1.0e-7 * scale
            if length_13 <= tolerance or length_24 <= tolerance:
                raise ValueError(
                    "BeamColumnJoint needs two non-zero opposite chords "
                    "(Node 1↔3 and Node 2↔4)."
                )

            midpoint_13 = tuple(
                0.5 * (points[0][axis] + points[2][axis])
                for axis in range(3)
            )
            midpoint_24 = tuple(
                0.5 * (points[1][axis] + points[3][axis])
                for axis in range(3)
            )
            midpoint_error = math.sqrt(sum(
                (midpoint_13[axis] - midpoint_24[axis]) ** 2
                for axis in range(3)
            ))
            if midpoint_error > tolerance:
                raise ValueError(
                    "BeamColumnJoint opposite chords must bisect at the "
                    "same joint center."
                )

            orthogonality = abs(sum(
                chord_13[axis] * chord_24[axis]
                for axis in range(3)
            )) / (length_13 * length_24)
            if orthogonality > 1.0e-6:
                raise ValueError(
                    "BeamColumnJoint opposite chords must be perpendicular "
                    "within the SARE geometry tolerance."
                )
            if ndm == 2 and (
                abs(chord_13[0]) > tolerance
                or abs(chord_24[1]) > tolerance
            ):
                raise ValueError(
                    "BeamColumnJoint2d uses global frame DOFs without a "
                    "local transformation. Node 1↔3 must be vertical "
                    "(global Y) and Node 2↔4 horizontal (global X)."
                )

        if connection.connection_type in {
            "Joint2D",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }:
            if int(self.model.ndm) != 2 or int(self.model.ndf) != 3:
                raise ValueError(
                    f"{connection.connection_type} currently requires a "
                    "2D frame model (ndm=2, ndf=3)."
                )

            if connection.connection_type == "Joint2D":
                imported_center = connection.parameters.get(
                    "imported_center_node_tag"
                )
                if imported_center is not None:
                    imported_center = int(imported_center)
                    if imported_center in self.model.nodes:
                        raise ValueError(
                            "Joint2D center node tag "
                            f"{imported_center} already exists in the model; "
                            "NodeC must be reserved for the Joint2D element."
                        )
                    duplicate_center = sorted(
                        int(tag)
                        for tag, other in self.connections.items()
                        if (
                            other.connection_type == "Joint2D"
                            and int(
                                other.parameters.get(
                                    "imported_center_node_tag",
                                    -1,
                                )
                            ) == imported_center
                            and int(tag) != int(connection.tag)
                        )
                    )
                    if duplicate_center:
                        raise ValueError(
                            "Joint2D center node tag "
                            f"{imported_center} is already reserved by "
                            "Joint2D connection(s): "
                            + ", ".join(map(str, duplicate_center))
                        )

            external_tags = [
                int(tag)
                for tag in connection.parameters["external_nodes"]
            ]
            points = [
                self.model.nodes[tag].xyz
                for tag in external_tags
            ]
            xy = [
                (float(point[0]), float(point[1]))
                for point in points
            ]
            chord_a = math.hypot(
                xy[2][0] - xy[0][0],
                xy[2][1] - xy[0][1],
            )
            chord_b = math.hypot(
                xy[3][0] - xy[1][0],
                xy[3][1] - xy[1][1],
            )
            scale = max(chord_a, chord_b, 1.0)
            tolerance = 1.0e-7 * scale
            if chord_a <= tolerance or chord_b <= tolerance:
                raise ValueError(
                    f"{connection.connection_type} needs two non-zero "
                    "opposing external-node chords."
                )

            midpoint_a = (
                0.5 * (xy[0][0] + xy[2][0]),
                0.5 * (xy[0][1] + xy[2][1]),
            )
            midpoint_b = (
                0.5 * (xy[1][0] + xy[3][0]),
                0.5 * (xy[1][1] + xy[3][1]),
            )
            midpoint_error = math.hypot(
                midpoint_a[0] - midpoint_b[0],
                midpoint_a[1] - midpoint_b[1],
            )
            if midpoint_error > tolerance:
                raise ValueError(
                    f"{connection.connection_type} external-node chords "
                    "must bisect at the same joint center."
                )

            center = (
                0.5 * (midpoint_a[0] + midpoint_b[0]),
                0.5 * (midpoint_a[1] + midpoint_b[1]),
            )
            vectors = [
                (point[0] - center[0], point[1] - center[1])
                for point in xy
            ]
            cross_values = [
                vectors[index][0] * vectors[(index + 1) % 4][1]
                - vectors[index][1] * vectors[(index + 1) % 4][0]
                for index in range(4)
            ]
            if (
                connection.connection_type == "LehighJoint2D"
                and not all(
                    value > tolerance * tolerance
                    for value in cross_values
                )
            ):
                raise ValueError(
                    "LehighJoint2D nodes must be entered counter-clockwise."
                )
            if not (
                all(value > tolerance * tolerance for value in cross_values)
                or all(value < -tolerance * tolerance for value in cross_values)
            ):
                raise ValueError(
                    f"{connection.connection_type} external nodes must be "
                    "entered cyclically around the joint."
                )

            if connection.connection_type == "KrawinklerPanelZone":
                left, top, right, bottom = xy
                if (
                    abs(left[1] - right[1]) > tolerance
                    or abs(top[0] - bottom[0]) > tolerance
                    or left[0] >= right[0] - tolerance
                    or bottom[1] >= top[1] - tolerance
                ):
                    raise ValueError(
                        "KrawinklerPanelZone currently requires an axis-aligned "
                        "Left → Top → Right → Bottom external-node layout."
                    )

    def add_connection(self, connection: ConnectionData) -> None:
        if connection.tag in self.connections:
            raise ValueError(
                f"Connection tag {connection.tag} already exists."
            )
        self._validate_connection(connection)
        for analysis in self.analyses.values():
            self._validate_analysis_constraint_handler_compatibility(
                analysis,
                candidate_connection=connection,
            )
        self.connections[connection.tag] = connection

    def update_connection(
        self,
        original_tag: int,
        connection: ConnectionData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Connection original tag",
        )
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
        for analysis in self.analyses.values():
            self._validate_analysis_constraint_handler_compatibility(
                analysis,
                candidate_connection=connection,
                ignore_connection_tags={original_tag},
            )
        self.connections.pop(original_tag)
        self.connections[connection.tag] = connection
        if connection.tag != original_tag:
            for recorder in self.recorders.values():
                if recorder.recorder_type == "Node":
                    continue
                recorder.target_tags = [
                    connection.tag if int(tag) == original_tag else int(tag)
                    for tag in recorder.target_tags
                ]
            for result in self.solution_results.values():
                result.element_scope = [
                    connection.tag if int(tag) == original_tag else int(tag)
                    for tag in result.element_scope
                ]

        # A connection may be edited between an element-backed type
        # (e.g. semiRigid/zeroLength) and an MPC-only type (rigid/pinned).
        # Remove now-invalid element recorder/result scopes immediately.
        self.prune_recorders()
        self.prune_solution_results()

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
            referenced_connection_nodes = {
                connection.node_i,
                connection.node_j,
            }
            if connection.connection_type in {
                "Joint2D",
                "BeamColumnJoint",
                "LehighJoint2D",
                "KrawinklerPanelZone",
            }:
                referenced_connection_nodes.update(
                    int(value)
                    for value in connection.parameters.get(
                        "external_nodes",
                        (),
                    )
                )
            if node_tag in referenced_connection_nodes:
                return True
        for constraint in self.constraints.values():
            if (
                constraint.retained_node == node_tag
                or node_tag in constraint.constrained_nodes
            ):
                return True
        if any(
            load.node_tag == node_tag
            for load in self.nodal_loads.values()
        ):
            return True
        if any(
            displacement.node_tag == node_tag
            for displacement in self.prescribed_displacements.values()
        ):
            return True
        if any(
            recorder.recorder_type == "Node"
            and node_tag in recorder.target_tags
            for recorder in self.recorders.values()
        ):
            return True
        if any(
            self._analysis_uses_control_node(analysis)
            and analysis.control_node == node_tag
            for analysis in self.analyses.values()
        ):
            return True
        return False

    def remove_connection(
        self,
        tag: int,
        *,
        cleanup_ground: bool = True,
    ) -> None:
        tag = _strict_int(tag, "Connection tag")
        connection = self.connections.pop(tag, None)
        if connection is None:
            return

        # Recorders and scoped result requests target connection tags like
        # ordinary element tags.  Keep direct connection deletion from
        # leaving orphan references behind even when generated-resource
        # cleanup is disabled.
        self.prune_recorders()
        self.prune_solution_results()

        if not cleanup_ground:
            return
        generated_constraint = connection.generated_constraint_tag
        if generated_constraint is not None:
            self.remove_constraint(generated_constraint)

        ground_tag = connection.generated_ground_node
        if (
            ground_tag is not None
            and ground_tag in self.model.nodes
            and not self._ground_node_in_use_elsewhere(ground_tag)
        ):
            self.model.remove_node(ground_tag, cascade=True)
            self.prune_selection_sets()
            self.prune_solution_results()

        generated_section = connection.generated_section_tag
        if (
            generated_section is not None
            and generated_section in self.sections
            and not any(
                generated_section
                in {
                    element.section_tag,
                    element.hinge_i_section_tag,
                    element.hinge_j_section_tag,
                    element.interior_section_tag,
                }
                for element in self.model.elements.values()
            )
            and not any(
                generated_section in {
                    other.section_tag,
                    other.generated_section_tag,
                }
                for other in self.connections.values()
            )
        ):
            self.sections.pop(generated_section, None)

    def sync_generated_ground_nodes(self) -> list[int]:
        """Keep managed ground nodes coincident with their source nodes."""
        updated: list[int] = []
        fixed = (1,) * int(self.model.ndf)
        for connection in self.connections.values():
            ground_tag = connection.generated_ground_node
            if ground_tag is None:
                continue
            if ground_tag == connection.node_i:
                source_tag = connection.node_j
            elif ground_tag == connection.node_j:
                source_tag = connection.node_i
            else:
                continue
            ground = self.model.nodes.get(int(ground_tag))
            source = self.model.nodes.get(int(source_tag))
            if ground is None or source is None:
                continue
            ground.xyz = tuple(source.xyz)
            ground.fixity = fixed
            ground.mass = (0.0,) * int(self.model.ndf)
            updated.append(int(ground_tag))
        return sorted(set(updated))

    def create_ground_node(self, source_node_tag: int) -> int:
        source_node_tag = _strict_int(
            source_node_tag,
            "Source node tag",
        )
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
        material_tag = _strict_int(material_tag, "Material tag")
        used: list[int] = []
        for connection in self.connections.values():
            tags = set(connection.materials_by_dof.values())
            if connection.connection_type in {
                "Joint2D",
                "BeamColumnJoint",
                "LehighJoint2D",
                "KrawinklerPanelZone",
            }:
                panel_tag = int(
                    connection.parameters.get("panel_material", 0)
                )
                if panel_tag > 0:
                    tags.add(panel_tag)
            if connection.connection_type == "Joint2D":
                tags.update(
                    int(tag)
                    for tag in connection.parameters.get(
                        "interface_materials",
                        (),
                    )
                    if int(tag) > 0
                )
            if connection.connection_type == "BeamColumnJoint":
                tags.update(
                    int(tag)
                    for tag in connection.parameters.get(
                        "component_materials",
                        (),
                    )
                    if int(tag) > 0
                )
            if connection.connection_type == "LehighJoint2D":
                tags.update(
                    int(tag)
                    for tag in connection.parameters.get(
                        "mode_materials",
                        (),
                    )
                    if int(tag) > 0
                )
            if material_tag in tags:
                used.append(connection.tag)
        return sorted(used)

    def prune_selection_sets(self) -> None:
        valid_nodes = set(self.model.nodes)
        valid_elements = set(self.model.elements)
        for selection_set in self.selection_sets.values():
            selection_set.node_tags.intersection_update(valid_nodes)
            selection_set.element_tags.intersection_update(valid_elements)

    def prune_connections(self) -> list[int]:
        removed: list[int] = []
        existing_nodes = set(self.model.nodes)
        for tag, connection in list(self.connections.items()):
            referenced_nodes = {
                connection.node_i,
                connection.node_j,
            }
            if connection.connection_type in {
                "Joint2D",
                "BeamColumnJoint",
                "LehighJoint2D",
                "KrawinklerPanelZone",
            }:
                referenced_nodes.update(
                    int(node_tag)
                    for node_tag in connection.parameters.get(
                        "external_nodes",
                        (),
                    )
                )
            if any(node_tag not in existing_nodes for node_tag in referenced_nodes):
                self.remove_connection(tag, cleanup_ground=True)
                removed.append(tag)
        return sorted(removed)

    def validate_node_state(self, node_tag: int) -> None:
        """Validate cross-object constraints after an in-place node edit."""
        node_tag = _strict_int(node_tag, "Node tag")
        node = self.model.nodes.get(node_tag)
        if node is None:
            raise ValueError(f"Node {node_tag} does not exist.")

        for connection in self.connections.values():
            referenced_connection_nodes = {
                connection.node_i,
                connection.node_j,
            }
            if connection.connection_type in {
                "Joint2D",
                "BeamColumnJoint",
                "LehighJoint2D",
                "KrawinklerPanelZone",
            }:
                referenced_connection_nodes.update(
                    int(tag)
                    for tag in connection.parameters.get(
                        "external_nodes",
                        (),
                    )
                )
            if node_tag in referenced_connection_nodes:
                self._validate_connection(connection)

        incident_elements = sorted(
            element.tag
            for element in self.model.elements.values()
            if node_tag in {int(element.i), int(element.j)}
        )
        for element_tag in incident_elements:
            self.validate_element_state(element_tag)

        for constraint_tag, constraint in self.constraints.items():
            if (
                node_tag != constraint.retained_node
                and node_tag not in constraint.constrained_nodes
            ):
                continue
            self._validate_constraint_model_compatibility(constraint)
            self._validate_constraint_nodes(constraint)
            self._validate_constraint_dependency_conflicts(
                constraint,
                ignore_constraint_tags={int(constraint_tag)},
            )

        for displacement_tag, displacement in self.prescribed_displacements.items():
            if int(displacement.node_tag) != node_tag:
                continue
            self._validate_prescribed_displacement(
                displacement,
                original_tag=int(displacement_tag),
            )

        for analysis in self.analyses.values():
            self._validate_analysis_constraint_handler_compatibility(analysis)
            if (
                self._analysis_uses_control_node(analysis)
                and int(analysis.control_node) == node_tag
                and analysis.control_dof <= len(node.fixity)
                and bool(node.fixity[analysis.control_dof - 1])
            ):
                raise ValueError(
                    f"{analysis.analysis_type} control node {node_tag} DOF "
                    f"{analysis.control_dof} is restrained by a support."
                )

    def validate_element_state(self, element_tag: int) -> None:
        """Validate objects whose semantics depend on an edited element."""
        element_tag = _strict_int(element_tag, "Element tag")
        if element_tag not in self.model.elements:
            raise ValueError(f"Element {element_tag} does not exist.")

        element = self.model.elements[element_tag]
        self._validate_element_geometry(element)

        if element.element_type in CONTINUUM_QUAD_ELEMENT_TYPES:
            material_tag = element.continuum_material_tag
            if material_tag is None or int(material_tag) not in self.nd_materials:
                raise ValueError(
                    f"{element.element_type} element {element_tag} requires "
                    "an existing nDMaterial."
                )

        if element.element_type in SOLID_ELEMENT_TYPES:
            material_tag = element.solid_material_tag
            if material_tag is None or int(material_tag) not in self.nd_materials:
                raise ValueError(
                    f"{element.element_type} element {element_tag} requires "
                    "an existing nDMaterial."
                )

        if element.element_type in {"MVLEM", "MVLEM_3D"}:
            direct_tags = {*element.wall_concrete_tags, *element.wall_steel_tags}
            if element.wall_shear_tag is not None:
                direct_tags.add(int(element.wall_shear_tag))
            missing = sorted(
                tag for tag in direct_tags if int(tag) not in self.materials
            )
            if missing:
                raise ValueError(
                    f"{element.element_type} element {element_tag} "
                    "references missing uniaxial material tag(s): "
                    + ", ".join(map(str, missing))
                )
        elif element.element_type == "SFI_MVLEM":
            missing = sorted(
                tag for tag in element.wall_nd_material_tags
                if int(tag) not in self.nd_materials
            )
            if missing:
                raise ValueError(
                    f"SFI_MVLEM element {element_tag} references missing "
                    "nDMaterial tag(s): " + ", ".join(map(str, missing))
                )
            incompatible = [
                int(tag)
                for tag in element.wall_nd_material_tags
                if self.nd_materials[int(tag)].material_type != "FSAM"
            ]
            if incompatible:
                raise ValueError(
                    f"SFI_MVLEM element {element_tag} requires FSAM "
                    "nDMaterials; incompatible tag(s): "
                    + ", ".join(map(str, incompatible))
                )

        if element.section_tag is not None:
            section = self.sections.get(int(element.section_tag))
            if (
                section is not None
                and element.element_type
                in {"elasticBeamColumn", "ElasticTimoshenkoBeam"}
                and section.section_type != "Elastic"
            ):
                raise ValueError(
                    f"{element.element_type} element {element_tag} requires "
                    "an Elastic section."
                )
            if (
                section is not None
                and element.element_type == "ElasticTimoshenkoBeam"
                and section.section_type == "Elastic"
            ):
                resolved = section.resolved_elastic_parameters(
                    self.materials
                )
                required = (
                    ("E", "G", "A", "Iz", "Avy")
                    if int(self.model.ndm) == 2
                    else (
                        "E", "G", "A", "J", "Iy", "Iz", "Avy", "Avz"
                    )
                )
                invalid = [
                    key
                    for key in required
                    if float(resolved.get(key, 0.0)) <= 0.0
                ]
                if invalid:
                    raise ValueError(
                        f"ElasticTimoshenkoBeam element {element_tag} "
                        "requires positive Elastic section parameter(s): "
                        + ", ".join(invalid)
                    )
            if (
                section is not None
                and element.element_type == "dispBeamColumnInt"
                and section.section_type != "FiberInt"
            ):
                raise ValueError(
                    f"dispBeamColumnInt element {element_tag} requires a "
                    "FiberInt section."
                )
            if (
                section is not None
                and element.element_type in SHELL_ELEMENT_TYPES
                and section.section_type not in SHELL_SECTION_TYPES
            ):
                raise ValueError(
                    f"{element.element_type} element {element_tag} requires "
                    "a shell-compatible section."
                )

        if element.transf_tag is not None:
            transformation = self.transformations.get(
                int(element.transf_tag)
            )
            if transformation is not None:
                if (
                    element.element_type == "dispBeamColumnInt"
                    and transformation.transformation_type != "LinearInt"
                ):
                    raise ValueError(
                        f"dispBeamColumnInt element {element_tag} requires "
                        "a LinearInt geometric transformation."
                    )
                if (
                    element.element_type != "dispBeamColumnInt"
                    and transformation.transformation_type == "LinearInt"
                ):
                    raise ValueError(
                        "LinearInt geometric transformations are reserved "
                        "for dispBeamColumnInt elements."
                    )
                self._validate_element_geometry(
                    element,
                    transformation=transformation,
                )

        for load in self.element_loads.values():
            if int(load.element_tag) == element_tag:
                self._validate_element_load(load)

        for recorder in self.recorders.values():
            if (
                recorder.recorder_type != "Node"
                and element_tag in recorder.target_tags
            ):
                self._validate_recorder(recorder)

    def _mutate_elements_transactionally(
        self,
        element_tags: Iterable[int],
        mutator,
    ) -> set[int]:
        tags: set[int] = set()
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            if normalized_tag in self.model.elements:
                tags.add(normalized_tag)
        snapshots = {
            tag: deepcopy(self.model.elements[tag])
            for tag in tags
        }
        try:
            updated = {
                int(tag) for tag in mutator(tags)
            }
            for tag in sorted(updated):
                self.model.elements[tag].__post_init__()
                self.validate_element_state(tag)
            return updated
        except Exception:
            for tag, element in snapshots.items():
                self.model.elements[tag] = element
            raise

    def assign_element_formulation(
        self,
        element_tags: Iterable[int],
        **values,
    ) -> set[int]:
        return self._mutate_elements_transactionally(
            element_tags,
            lambda tags: self.model.assign_element_formulation(
                tags,
                **values,
            ),
        )

    def assign_section_to_elements(
        self,
        element_tags: Iterable[int],
        section_tag: int | None,
    ) -> set[int]:
        value = (
            None
            if section_tag is None
            else _strict_int(section_tag, "Section tag")
        )
        if value is not None and value not in self.sections:
            raise ValueError(f"Section {value} does not exist.")
        return self._mutate_elements_transactionally(
            element_tags,
            lambda tags: self.model.assign_section(tags, value),
        )

    def assign_transformation_to_elements(
        self,
        element_tags: Iterable[int],
        transformation_tag: int | None,
    ) -> set[int]:
        value = (
            None
            if transformation_tag is None
            else _strict_int(
                transformation_tag,
                "Transformation tag",
            )
        )
        if value is not None and value not in self.transformations:
            raise ValueError(
                f"Transformation {value} does not exist."
            )
        return self._mutate_elements_transactionally(
            element_tags,
            lambda tags: self.model.assign_transformation(tags, value),
        )

    def delete_entities(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
        cascade_nodes: bool = True,
    ) -> None:
        node_tags = {
            _strict_int(tag, "Node tag")
            for tag in node_tags
        }
        element_tags = {
            _strict_int(tag, "Element tag")
            for tag in element_tags
        }

        control_users = sorted(
            analysis.tag
            for analysis in self.analyses.values()
            if (
                self._analysis_uses_control_node(analysis)
                and int(analysis.control_node) in node_tags
            )
        )
        if control_users:
            raise ValueError(
                "Cannot delete control node(s) used by analysis tag(s): "
                + ", ".join(map(str, control_users))
                + ". Reassign the analysis control node first."
            )

        self.model.delete_entities(
            node_tags=node_tags,
            element_tags=element_tags,
            cascade_nodes=cascade_nodes,
        )

        self.prune_constraints()
        self.prune_connections()
        self.prune_nodal_loads()
        self.prune_prescribed_displacements()
        self.prune_element_loads()
        self.prune_recorders()
        self.prune_solution_results()

        self.prune_selection_sets()

    def next_time_series_tag(self) -> int:
        return max(self.time_series, default=0) + 1

    def add_time_series(self, series: TimeSeriesData) -> None:
        if series.tag in self.time_series:
            raise ValueError(f"Time series tag {series.tag} already exists.")
        self.time_series[series.tag] = series

    def update_time_series(self, original_tag: int, series: TimeSeriesData) -> None:
        original_tag = _strict_int(
            original_tag,
            "Time series original tag",
        )
        if original_tag not in self.time_series:
            raise ValueError(f"Time series tag {original_tag} does not exist.")
        if series.tag != original_tag and series.tag in self.time_series:
            raise ValueError(f"Time series tag {series.tag} already exists.")
        mass_source_patterns = sorted(
            pattern.tag
            for pattern in self.load_patterns.values()
            if (
                pattern.time_series_tag == original_tag
                and any(
                    pattern.tag in source.load_factors
                    for source in self.mass_sources.values()
                )
            )
        )
        if (
            mass_source_patterns
            and series.series_type not in {"Linear", "Constant"}
        ):
            raise ValueError(
                f"Time series {original_tag} is used by Mass Source load "
                "pattern(s) "
                + ", ".join(map(str, mass_source_patterns))
                + " and must remain Linear or Constant."
            )
        self.time_series.pop(original_tag)
        self.time_series[series.tag] = series
        if series.tag != original_tag:
            for pattern in self.load_patterns.values():
                if pattern.time_series_tag == original_tag:
                    pattern.time_series_tag = series.tag

    def remove_time_series(self, tag: int) -> None:
        tag = _strict_int(tag, "Time series tag")
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
        if (
            pattern.pattern_type == "UniformExcitation"
            and pattern.direction > int(self.model.ndm)
        ):
            raise ValueError(
                f"UniformExcitation direction {pattern.direction} is not "
                f"available for ndm={self.model.ndm}; excitation directions "
                "must be translational."
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
        original_tag = _strict_int(
            original_tag,
            "Load pattern original tag",
        )
        if original_tag not in self.load_patterns:
            raise ValueError(f"Load pattern tag {original_tag} does not exist.")
        if pattern.tag != original_tag and pattern.tag in self.load_patterns:
            raise ValueError(f"Load pattern tag {pattern.tag} already exists.")
        self._validate_load_pattern(pattern)
        mass_source_users = sorted(
            source.tag
            for source in self.mass_sources.values()
            if original_tag in source.load_factors
        )
        if mass_source_users:
            if pattern.pattern_type != "Plain":
                raise ValueError(
                    f"Load pattern {original_tag} is used by Mass Source "
                    "object(s) "
                    + ", ".join(map(str, mass_source_users))
                    + " and must remain a Plain pattern."
                )
            series = self.time_series[pattern.time_series_tag]
            if series.series_type not in {"Linear", "Constant"}:
                raise ValueError(
                    f"Load pattern {original_tag} is used by Mass Source "
                    "object(s) "
                    + ", ".join(map(str, mass_source_users))
                    + " and must use a Linear or Constant time series."
                )
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
            dependent_surface_edge_load = [
                edge_load.tag
                for edge_load in self.surface_edge_loads.values()
                if edge_load.pattern_tag == original_tag
            ]
            dependent_surface_pressure = [
                pressure.tag
                for pressure in self.surface_pressures.values()
                if pressure.pattern_tag == original_tag
            ]
            if (
                dependent_nodal
                or dependent_element
                or dependent_displacement
                or dependent_surface_edge_load
                or dependent_surface_pressure
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
            for edge_load in self.surface_edge_loads.values():
                if edge_load.pattern_tag == original_tag:
                    edge_load.pattern_tag = pattern.tag
            for surface_pressure in self.surface_pressures.values():
                if surface_pressure.pattern_tag == original_tag:
                    surface_pressure.pattern_tag = pattern.tag
            for analysis in self.analyses.values():
                if original_tag in analysis.deferred_pattern_tags:
                    analysis.deferred_pattern_tags = [
                        pattern.tag if int(tag) == original_tag else int(tag)
                        for tag in analysis.deferred_pattern_tags
                    ]

    def remove_load_pattern(self, tag: int) -> None:
        tag = _strict_int(tag, "Load pattern tag")
        driver_users = sorted(
            analysis.tag
            for analysis in self.analyses.values()
            if (
                self._analysis_uses_deferred_patterns(analysis)
                and tag in analysis.deferred_pattern_tags
            )
        )
        if driver_users:
            raise ValueError(
                "Load pattern is used as a driving/excitation pattern by "
                "analysis tag(s): "
                + ", ".join(map(str, driver_users))
                + ". Reassign or update those analyses before deleting it."
            )

        for analysis in self.analyses.values():
            if tag in analysis.deferred_pattern_tags:
                analysis.deferred_pattern_tags = [
                    int(value)
                    for value in analysis.deferred_pattern_tags
                    if int(value) != tag
                ]

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
        for edge_load_tag, edge_load in list(
            self.surface_edge_loads.items()
        ):
            if edge_load.pattern_tag == tag:
                self.surface_edge_loads.pop(edge_load_tag)
        for pressure_tag, pressure in list(
            self.surface_pressures.items()
        ):
            if pressure.pattern_tag == tag:
                self.surface_pressures.pop(pressure_tag)
        for source in self.mass_sources.values():
            source.load_factors.pop(tag, None)

    def next_mass_source_tag(self) -> int:
        return max(self.mass_sources, default=0) + 1

    def _validate_mass_source(self, source: MassSourceData) -> None:
        invalid_directions = sorted(
            dof
            for dof in source.directions
            if dof > min(int(self.model.ndm), 3)
        )
        if invalid_directions:
            raise ValueError(
                "Mass source translational direction(s) "
                + ", ".join(map(str, invalid_directions))
                + f" are not available for ndm={self.model.ndm}."
            )
        if source.gravity_axis > int(self.model.ndm):
            raise ValueError(
                f"Mass source gravity axis {source.gravity_axis} is not "
                f"available for ndm={self.model.ndm}."
            )
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

        invalid_series: list[str] = []
        for pattern_tag in source.load_factors:
            pattern = self.load_patterns[pattern_tag]
            series = self.time_series.get(pattern.time_series_tag)
            if series is None:
                invalid_series.append(
                    f"pattern {pattern_tag} -> missing time series "
                    f"{pattern.time_series_tag}"
                )
            elif series.series_type not in {"Linear", "Constant"}:
                invalid_series.append(
                    f"pattern {pattern_tag} -> {series.series_type} "
                    f"time series {series.tag}"
                )
        if invalid_series:
            raise ValueError(
                "Mass source requires Linear/Constant gravity-style time "
                "series: "
                + "; ".join(invalid_series)
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
        original_tag = _strict_int(
            original_tag,
            "Mass source original tag",
        )
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
        tag = _strict_int(tag, "Mass source tag")
        self.mass_sources.pop(tag, None)

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
        unavailable = [
            index + 1
            for index, value in enumerate(load.values)
            if index >= int(self.model.ndf)
            and abs(float(value)) > 1.0e-15
        ]
        if unavailable:
            raise ValueError(
                "Nodal load has nonzero value on unavailable DOF(s): "
                + ", ".join(map(str, unavailable))
                + f" for ndf={self.model.ndf}."
            )

    def add_nodal_load(self, load: NodalLoadData) -> None:
        if load.tag in self.nodal_loads:
            raise ValueError(f"Nodal load tag {load.tag} already exists.")
        self._validate_nodal_load(load)
        self.nodal_loads[load.tag] = load

    def update_nodal_load(self, original_tag: int, load: NodalLoadData) -> None:
        original_tag = _strict_int(
            original_tag,
            "Nodal load original tag",
        )
        if original_tag not in self.nodal_loads:
            raise ValueError(f"Nodal load tag {original_tag} does not exist.")
        if load.tag != original_tag and load.tag in self.nodal_loads:
            raise ValueError(f"Nodal load tag {load.tag} already exists.")
        self._validate_nodal_load(load)
        self.nodal_loads.pop(original_tag)
        self.nodal_loads[load.tag] = load

    def remove_nodal_load(self, tag: int) -> None:
        tag = _strict_int(tag, "Nodal load tag")
        self.nodal_loads.pop(tag, None)

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
                existing.node_tag != displacement.node_tag
                or existing.dof != displacement.dof
            ):
                continue
            if existing.pattern_tag == displacement.pattern_tag:
                raise ValueError(
                    "Node "
                    f"{displacement.node_tag} DOF {displacement.dof} already "
                    "has a prescribed displacement in load pattern "
                    f"{displacement.pattern_tag}."
                )
            simultaneous = sorted(
                analysis.tag
                for analysis_tag, analysis in self.analyses.items()
                if (
                    self._analysis_pattern_is_active(
                        analysis,
                        existing.pattern_tag,
                        ignore_analysis_tags={int(analysis_tag)},
                    )
                    and self._analysis_pattern_is_active(
                        analysis,
                        displacement.pattern_tag,
                        ignore_analysis_tags={int(analysis_tag)},
                    )
                )
            )
            if simultaneous:
                raise ValueError(
                    "Node "
                    f"{displacement.node_tag} DOF {displacement.dof} would "
                    "have multiple active Prescribed Displacement objects "
                    "in analysis tag(s): "
                    + ", ".join(map(str, simultaneous))
                    + "."
                )

        mpc_conflicts = sorted(
            constraint.tag
            for constraint in self.constraints.values()
            if (
                displacement.node_tag in constraint.constrained_nodes
                and displacement.dof
                in self._constraint_dependent_dofs(constraint)
            )
        )
        if mpc_conflicts:
            active_in = sorted(
                analysis.tag
                for analysis_tag, analysis in self.analyses.items()
                if self._analysis_pattern_is_active(
                    analysis,
                    displacement.pattern_tag,
                    ignore_analysis_tags={int(analysis_tag)},
                )
            )
            if active_in:
                raise ValueError(
                    "Prescribed displacement at node "
                    f"{displacement.node_tag} DOF {displacement.dof} "
                    "conflicts with dependent DOF in MPC constraint(s): "
                    + ", ".join(map(str, mpc_conflicts))
                    + "; active analysis tag(s): "
                    + ", ".join(map(str, active_in))
                    + "."
                )

        if displacement.value != 0.0:
            for analysis_tag, analysis in self.analyses.items():
                if analysis.constraints_handler != "Plain":
                    continue
                if self._analysis_pattern_is_active(
                    analysis,
                    displacement.pattern_tag,
                    ignore_analysis_tags={int(analysis_tag)},
                ):
                    raise ValueError(
                        "Non-zero Prescribed Displacement "
                        f"{displacement.tag} is active in analysis "
                        f"{analysis.tag}, which uses the Plain constraint "
                        "handler. Use the Transformation constraint handler."
                    )

        for analysis_tag, analysis in self.analyses.items():
            if (
                not self._analysis_uses_control_node(analysis)
                or analysis.control_node != displacement.node_tag
                or analysis.control_dof != displacement.dof
            ):
                continue
            if self._analysis_pattern_is_active(
                analysis,
                displacement.pattern_tag,
                ignore_analysis_tags={int(analysis_tag)},
            ):
                raise ValueError(
                    "Prescribed displacement at node "
                    f"{displacement.node_tag} DOF {displacement.dof} "
                    f"conflicts with active {analysis.analysis_type} "
                    f"analysis {analysis.tag} DisplacementControl."
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
        original_tag = _strict_int(
            original_tag,
            "Prescribed displacement original tag",
        )
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
        tag = _strict_int(tag, "Prescribed displacement tag")
        self.prescribed_displacements.pop(tag, None)

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
        if load.load_type == "SurfacePressure":
            if element.element_type not in SHELL_ELEMENT_TYPES:
                raise ValueError(
                    "SurfacePressure requires a Shell element."
                )
            if (int(self.model.ndm), int(self.model.ndf)) != (3, 6):
                raise ValueError(
                    "Shell SurfacePressure requires ndm=3 and ndf=6."
                )
            self._validate_element_geometry(element)
            return

        if element.element_type not in FRAME_ELEMENT_TYPES:
            raise ValueError(
                "Beam element loads require a beam-column element."
            )

        if load.load_type == "SelfWeight":
            if element.section_tag is None:
                raise ValueError(
                    "SelfWeight requires the target element to have a section."
                )
            section = self.sections.get(int(element.section_tag))
            if section is None:
                raise ValueError(
                    f"SelfWeight references missing section {element.section_tag}."
                )
            if section.section_type != "Elastic":
                raise ValueError(
                    "Automatic SelfWeight currently requires an Elastic section."
                )
            if element.transf_tag is None:
                raise ValueError(
                    "SelfWeight requires a geometric transformation."
                )
            transformation = self.transformations.get(
                int(element.transf_tag)
            )
            if transformation is None:
                raise ValueError(
                    "SelfWeight references missing geometric transformation "
                    f"{element.transf_tag}."
                )
            self._validate_element_geometry(
                element,
                transformation=transformation,
            )
            if load.density_override <= 0.0:
                if section.material_tag is None:
                    raise ValueError(
                        "SelfWeight needs a positive density override or an "
                        "Elastic section linked to a material with density."
                    )
                material = self.materials.get(int(section.material_tag))
                if material is None:
                    raise ValueError(
                        f"SelfWeight references missing material "
                        f"{section.material_tag} through section {section.tag}."
                    )
                if material.density <= 0.0:
                    raise ValueError(
                        "SelfWeight needs a positive density override or a "
                        "linked material with positive density."
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
        original_tag = _strict_int(
            original_tag,
            "Element load original tag",
        )
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
        tag = _strict_int(tag, "Element load tag")
        self.element_loads.pop(tag, None)

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
            missing = [
                tag
                for tag in recorder.target_tags
                if tag not in self.model.nodes
            ]
            if missing:
                raise ValueError(
                    "Recorder references missing node tag(s): "
                    + ", ".join(map(str, missing))
                )
            invalid_dofs = sorted(
                dof
                for dof in recorder.dofs
                if dof > int(self.model.ndf)
            )
            if invalid_dofs:
                raise ValueError(
                    "Node recorder DOF(s) "
                    + ", ".join(map(str, invalid_dofs))
                    + f" are not available for ndf={self.model.ndf}."
                )
            return
        valid_elements = set(self.model.elements) | {
            tag
            for tag, connection in self.connections.items()
            if connection.connection_type in ELEMENT_BACKED_CONNECTION_TYPES
        }
        missing = [tag for tag in recorder.target_tags if tag not in valid_elements]
        if missing:
            mpc_only = sorted(
                tag
                for tag in missing
                if (
                    tag in self.connections
                    and self.connections[tag].connection_type in {"rigid", "pinned"}
                )
            )
            if mpc_only:
                raise ValueError(
                    "Rigid/Pinned connections are MPC constraints, not OpenSees "
                    "elements, and cannot be Element recorder targets: "
                    + ", ".join(map(str, mpc_only))
                    + ". Record connected node responses instead."
                )
            raise ValueError(
                "Recorder references missing element tag(s): "
                + ", ".join(map(str, missing))
            )
        if recorder.recorder_type == "Element":
            connection_targets = [
                self.connections[tag]
                for tag in recorder.target_tags
                if tag in self.connections
            ]
            incompatible_responses = sorted({
                connection.connection_type
                for connection in connection_targets
                if recorder.response not in CONNECTION_RECORDER_RESPONSES.get(
                    connection.connection_type,
                    set(),
                )
            })
            if incompatible_responses:
                raise ValueError(
                    f"Element recorder response {recorder.response!r} is not "
                    "supported by connection type(s): "
                    + ", ".join(incompatible_responses)
                    + "."
                )
            if (
                int(self.model.ndm) == 3
                and recorder.response == "externalDisplacement"
                and any(
                    connection.connection_type == "BeamColumnJoint"
                    for connection in connection_targets
                )
            ):
                raise ValueError(
                    "BeamColumnJoint3d externalDisplacement is disabled in "
                    "SARE because the current OpenSees source allocates a "
                    "12-value response buffer but writes 24 external DOFs."
                )

            structural_targets = [
                tag for tag in recorder.target_tags
                if tag in self.model.elements
            ]
            if (
                structural_targets
                and recorder.response not in {"globalForce", "localForce"}
            ):
                raise ValueError(
                    f"Element recorder response {recorder.response!r} is "
                    "reserved for connection-specific elements; structural "
                    "frame/truss targets currently support globalForce or "
                    "localForce in the generic Element recorder."
                )

        if recorder.recorder_type == "Shell":
            incompatible = [
                tag
                for tag in recorder.target_tags
                if (
                    tag not in self.model.elements
                    or self.model.elements[tag].element_type
                    not in SHELL_ELEMENT_TYPES
                )
            ]
            if incompatible:
                raise ValueError(
                    "Shell recorders require Shell element tag(s): "
                    + ", ".join(map(str, incompatible))
                )
            return
        if recorder.recorder_type in {"Section", "Fiber"}:
            incompatible = [
                tag
                for tag in recorder.target_tags
                if tag not in self.model.elements
                or self.model.elements[tag].element_type
                not in {
                    "forceBeamColumn",
                    "dispBeamColumn",
                    "dispBeamColumnInt",
                }
            ]
            if incompatible:
                raise ValueError(
                    "Section/Fiber recorders require forceBeamColumn or "
                    "dispBeamColumn element tag(s), including "
                    "dispBeamColumnInt: "
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
        original_tag = _strict_int(
            original_tag,
            "Recorder original tag",
        )
        if original_tag not in self.recorders:
            raise ValueError(f"Recorder tag {original_tag} does not exist.")
        if recorder.tag != original_tag and recorder.tag in self.recorders:
            raise ValueError(f"Recorder tag {recorder.tag} already exists.")
        self._validate_recorder(recorder)
        self.recorders.pop(original_tag)
        self.recorders[recorder.tag] = recorder

    def remove_recorder(self, tag: int) -> None:
        tag = _strict_int(tag, "Recorder tag")
        self.recorders.pop(tag, None)

    def prune_recorders(self) -> list[int]:
        removed: list[int] = []
        valid_nodes = set(self.model.nodes)
        valid_elements = set(self.model.elements) | {
            connection_tag
            for connection_tag, connection in self.connections.items()
            if connection.connection_type in ELEMENT_BACKED_CONNECTION_TYPES
        }
        for tag, recorder in list(self.recorders.items()):
            valid = valid_nodes if recorder.recorder_type == "Node" else valid_elements
            recorder.target_tags = [item for item in recorder.target_tags if item in valid]
            if not recorder.target_tags:
                self.recorders.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def prune_solution_results(self) -> list[int]:
        removed: list[int] = []
        valid_nodes = set(self.model.nodes)
        valid_elements = set(self.model.elements) | {
            connection_tag
            for connection_tag, connection in self.connections.items()
            if connection.connection_type in ELEMENT_BACKED_CONNECTION_TYPES
        }
        for tag, result in list(self.solution_results.items()):
            node_scoped = bool(result.node_scope)
            element_scoped = bool(result.element_scope)
            if node_scoped:
                result.node_scope = [
                    item for item in result.node_scope
                    if item in valid_nodes
                ]
            if element_scoped:
                result.element_scope = [
                    item for item in result.element_scope
                    if item in valid_elements
                ]
            if result.surface_scope:
                result.element_scope = [
                    item for item in result.element_scope
                    if item in valid_elements
                ]
            if (
                (node_scoped and not result.node_scope)
                or (
                    element_scoped
                    and not result.element_scope
                    and not result.surface_scope
                )
            ):
                self.solution_results.pop(tag)
                removed.append(tag)
        return sorted(removed)

    def next_analysis_tag(self) -> int:
        return max(self.analyses, default=0) + 1

    @staticmethod
    def _analysis_uses_control_node(
        analysis: AnalysisSettingsData,
    ) -> bool:
        return (
            analysis.analysis_type in {"Pushover", "Cyclic"}
            or (
                analysis.analysis_type == "Static"
                and analysis.integrator == "DisplacementControl"
            )
        )

    @staticmethod
    def _analysis_uses_deferred_patterns(
        analysis: AnalysisSettingsData,
    ) -> bool:
        return bool(
            analysis.analysis_type in {"Transient", "Pushover", "Cyclic", "Response Spectrum"}
            or (
                analysis.analysis_type == "Static"
                and analysis.integrator == "DisplacementControl"
            )
        )

    def _validate_analysis_pattern_references(
        self,
        analysis: AnalysisSettingsData,
    ) -> None:
        if not self._analysis_uses_deferred_patterns(analysis):
            return
        missing = sorted(
            int(tag)
            for tag in analysis.deferred_pattern_tags
            if int(tag) not in self.load_patterns
        )
        if missing:
            raise ValueError(
                f"{analysis.analysis_type} analysis {analysis.tag} "
                "references missing driving load pattern tag(s): "
                + ", ".join(map(str, missing))
                + "."
            )

    def _analysis_pattern_is_active(
        self,
        analysis: AnalysisSettingsData,
        pattern_tag: int,
        *,
        ignore_analysis_tags: set[int] | None = None,
    ) -> bool:
        pattern_tag = int(pattern_tag)
        deferred = {
            int(tag) for tag in analysis.deferred_pattern_tags
        }
        if pattern_tag in deferred:
            return True
        if not deferred:
            return pattern_tag in self.load_patterns

        ignored = {int(analysis.tag)}
        ignored.update(
            int(tag) for tag in (ignore_analysis_tags or set())
        )
        other_driver_tags: set[int] = set()
        for analysis_tag, other in self.analyses.items():
            if int(analysis_tag) in ignored:
                continue
            other_driver_tags.update(
                int(tag) for tag in other.deferred_pattern_tags
            )
        if pattern_tag in other_driver_tags:
            return False

        pattern = self.load_patterns.get(pattern_tag)
        return bool(
            analysis.preload_gravity
            and pattern is not None
            and pattern.pattern_type == "Plain"
        )

    def _validate_analysis_duplicate_prescribed_dofs(
        self,
        analysis: AnalysisSettingsData,
        *,
        ignore_analysis_tags: set[int] | None = None,
    ) -> None:
        active_by_dof: dict[tuple[int, int], list[int]] = {}
        for displacement in self.prescribed_displacements.values():
            if not self._analysis_pattern_is_active(
                analysis,
                displacement.pattern_tag,
                ignore_analysis_tags=ignore_analysis_tags,
            ):
                continue
            key = (
                int(displacement.node_tag),
                int(displacement.dof),
            )
            active_by_dof.setdefault(key, []).append(
                int(displacement.tag)
            )

        conflicts = {
            key: sorted(tags)
            for key, tags in active_by_dof.items()
            if len(tags) > 1
        }
        if conflicts:
            details = "; ".join(
                f"node {node_tag} DOF {dof}: "
                + ", ".join(map(str, tags))
                for (node_tag, dof), tags in sorted(conflicts.items())
            )
            raise ValueError(
                f"Analysis {analysis.tag} activates multiple Prescribed "
                "Displacement objects on the same DOF: "
                + details
                + "."
            )

    def _validate_analysis_prescribed_mpc_conflict(
        self,
        analysis: AnalysisSettingsData,
        *,
        ignore_analysis_tags: set[int] | None = None,
    ) -> None:
        conflicts = []
        for displacement in self.prescribed_displacements.values():
            if not self._analysis_pattern_is_active(
                analysis,
                displacement.pattern_tag,
                ignore_analysis_tags=ignore_analysis_tags,
            ):
                continue
            owners = sorted(
                int(constraint.tag)
                for constraint in self.constraints.values()
                if (
                    displacement.node_tag in constraint.constrained_nodes
                    and displacement.dof
                    in self._constraint_dependent_dofs(constraint)
                )
            )
            if owners:
                conflicts.append(
                    (
                        int(displacement.tag),
                        int(displacement.node_tag),
                        int(displacement.dof),
                        owners,
                    )
                )
        if conflicts:
            details = "; ".join(
                f"SP {sp_tag} at node {node_tag} DOF {dof} -> MPC "
                + ", ".join(map(str, owners))
                for sp_tag, node_tag, dof, owners in conflicts
            )
            raise ValueError(
                f"Analysis {analysis.tag} activates Prescribed "
                "Displacement object(s) on MPC dependent DOF(s): "
                + details
                + "."
            )

    def _validate_analysis_plain_prescribed_displacement_compatibility(
        self,
        analysis: AnalysisSettingsData,
        *,
        ignore_analysis_tags: set[int] | None = None,
    ) -> None:
        if analysis.constraints_handler != "Plain":
            return
        conflicts = sorted(
            displacement.tag
            for displacement in self.prescribed_displacements.values()
            if (
                displacement.value != 0.0
                and self._analysis_pattern_is_active(
                    analysis,
                    displacement.pattern_tag,
                    ignore_analysis_tags=ignore_analysis_tags,
                )
            )
        )
        if conflicts:
            raise ValueError(
                "Plain constraint handler cannot enforce non-zero "
                "Prescribed Displacement object(s): "
                + ", ".join(map(str, conflicts))
                + ". Use the Transformation constraint handler."
            )

    def _validate_analysis_equal_dof_control_conflict(
        self,
        analysis: AnalysisSettingsData,
    ) -> None:
        if not self._analysis_uses_control_node(analysis):
            return
        conflicts = sorted(
            constraint.tag
            for constraint in self.constraints.values()
            if (
                constraint.constraint_type == "equalDOF"
                and analysis.control_node in constraint.constrained_nodes
                and analysis.control_dof in constraint.dofs
            )
        )
        if conflicts:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} DOF {analysis.control_dof} "
                "is a constrained/dependent DOF in equalDOF constraint(s): "
                + ", ".join(map(str, conflicts))
                + ". Use the retained node or another independent DOF."
            )

    def _validate_analysis_rigid_link_control_conflict(
        self,
        analysis: AnalysisSettingsData,
    ) -> None:
        if not self._analysis_uses_control_node(analysis):
            return
        conflicts = sorted(
            constraint.tag
            for constraint in self.constraints.values()
            if (
                constraint.constraint_type == "rigidLink"
                and analysis.control_node in constraint.constrained_nodes
                and (
                    constraint.link_type == "beam"
                    or analysis.control_dof <= min(
                        int(self.model.ndm),
                        int(self.model.ndf),
                    )
                )
            )
        )
        if conflicts:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} DOF {analysis.control_dof} "
                "is a constrained/dependent DOF in rigidLink constraint(s): "
                + ", ".join(map(str, conflicts))
                + ". Use the retained node or another independent DOF."
            )

    def _validate_analysis_rigid_diaphragm_control_conflict(
        self,
        analysis: AnalysisSettingsData,
    ) -> None:
        if not self._analysis_uses_control_node(analysis):
            return
        conflicts = sorted(
            constraint.tag
            for constraint in self.constraints.values()
            if (
                constraint.constraint_type == "rigidDiaphragm"
                and analysis.control_node in constraint.constrained_nodes
                and analysis.control_dof
                in self._rigid_diaphragm_dependent_dofs(constraint)
            )
        )
        if conflicts:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} DOF {analysis.control_dof} "
                "is a constrained/dependent DOF in rigidDiaphragm "
                "constraint(s): "
                + ", ".join(map(str, conflicts))
                + ". Use the retained node or another independent DOF."
            )

    def _validate_analysis_prescribed_control_conflict(
        self,
        analysis: AnalysisSettingsData,
        *,
        ignore_analysis_tags: set[int] | None = None,
    ) -> None:
        if not self._analysis_uses_control_node(analysis):
            return
        conflicts = sorted(
            displacement.tag
            for displacement in self.prescribed_displacements.values()
            if (
                displacement.node_tag == analysis.control_node
                and displacement.dof == analysis.control_dof
                and self._analysis_pattern_is_active(
                    analysis,
                    displacement.pattern_tag,
                    ignore_analysis_tags=ignore_analysis_tags,
                )
            )
        )
        if conflicts:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} DOF {analysis.control_dof} "
                "conflicts with active Prescribed Displacement object(s): "
                + ", ".join(map(str, conflicts))
                + "."
            )

    def add_analysis(self, analysis: AnalysisSettingsData) -> None:
        if analysis.tag in self.analyses:
            raise ValueError(f"Analysis tag {analysis.tag} already exists.")
        self._validate_analysis_constraint_handler_compatibility(analysis)
        self._validate_analysis_duplicate_prescribed_dofs(analysis)
        self._validate_analysis_prescribed_mpc_conflict(analysis)
        self._validate_analysis_plain_prescribed_displacement_compatibility(
            analysis
        )
        uses_control_node = self._analysis_uses_control_node(analysis)
        if uses_control_node and analysis.control_node not in self.model.nodes:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} does not exist."
            )
        if uses_control_node:
            control_node = self.model.nodes[analysis.control_node]
            if (
                analysis.control_dof <= len(control_node.fixity)
                and bool(control_node.fixity[analysis.control_dof - 1])
            ):
                raise ValueError(
                    f"{analysis.analysis_type} control node "
                    f"{analysis.control_node} DOF {analysis.control_dof} "
                    "is restrained by a support."
                )
        self._validate_analysis_equal_dof_control_conflict(analysis)
        self._validate_analysis_rigid_link_control_conflict(analysis)
        self._validate_analysis_rigid_diaphragm_control_conflict(analysis)
        self._validate_analysis_prescribed_control_conflict(analysis)
        self.analyses[analysis.tag]=analysis
        if self.active_analysis_tag is None:
            self.active_analysis_tag=analysis.tag

    def update_analysis(self, original_tag:int, analysis:AnalysisSettingsData) -> None:
        original_tag = _strict_int(
            original_tag,
            "Analysis original tag",
        )
        if original_tag not in self.analyses: raise ValueError(f"Analysis tag {original_tag} does not exist.")
        if analysis.tag!=original_tag and analysis.tag in self.analyses: raise ValueError(f"Analysis tag {analysis.tag} already exists.")
        self._validate_analysis_constraint_handler_compatibility(analysis)
        self._validate_analysis_duplicate_prescribed_dofs(
            analysis,
            ignore_analysis_tags={original_tag},
        )
        self._validate_analysis_prescribed_mpc_conflict(
            analysis,
            ignore_analysis_tags={original_tag},
        )
        self._validate_analysis_plain_prescribed_displacement_compatibility(
            analysis,
            ignore_analysis_tags={original_tag},
        )
        uses_control_node = self._analysis_uses_control_node(analysis)
        if uses_control_node and analysis.control_node not in self.model.nodes:
            raise ValueError(
                f"{analysis.analysis_type} control node "
                f"{analysis.control_node} does not exist."
            )
        if uses_control_node:
            control_node = self.model.nodes[analysis.control_node]
            if (
                analysis.control_dof <= len(control_node.fixity)
                and bool(control_node.fixity[analysis.control_dof - 1])
            ):
                raise ValueError(
                    f"{analysis.analysis_type} control node "
                    f"{analysis.control_node} DOF {analysis.control_dof} "
                    "is restrained by a support."
                )
        self._validate_analysis_equal_dof_control_conflict(analysis)
        self._validate_analysis_rigid_link_control_conflict(analysis)
        self._validate_analysis_rigid_diaphragm_control_conflict(analysis)
        self._validate_analysis_prescribed_control_conflict(
            analysis,
            ignore_analysis_tags={original_tag},
        )
        allowed_result_types = self._allowed_solution_result_types(analysis)
        incompatible_results = sorted(
            result.tag
            for result in self.solution_results.values()
            if (
                result.analysis_tag == original_tag
                and result.result_type not in allowed_result_types
            )
        )
        if incompatible_results:
            raise ValueError(
                f"Changing analysis {original_tag} to "
                f"{analysis.analysis_type} would invalidate Solution Result "
                "object(s): "
                + ", ".join(map(str, incompatible_results))
                + ". Delete or replace those result requests first."
            )
        self.analyses.pop(original_tag); self.analyses[analysis.tag]=analysis
        if analysis.tag != original_tag:
            for result in self.solution_results.values():
                if result.analysis_tag == original_tag:
                    result.analysis_tag = analysis.tag
        if self.active_analysis_tag==original_tag: self.active_analysis_tag=analysis.tag

    def remove_analysis(self, tag:int) -> None:
        tag = _strict_int(tag, "Analysis tag")
        self.analyses.pop(tag,None)
        for result_tag, result in list(self.solution_results.items()):
            if result.analysis_tag == tag:
                self.solution_results.pop(result_tag)
        if self.active_analysis_tag==tag:
            self.active_analysis_tag=min(self.analyses,default=None)

    def set_active_analysis(self, tag:int) -> None:
        tag = _strict_int(tag, "Analysis tag")
        if tag not in self.analyses: raise ValueError(f"Analysis tag {tag} does not exist.")
        self.active_analysis_tag=tag

    def next_solution_result_tag(self) -> int:
        return max(self.solution_results, default=0) + 1

    @staticmethod
    def _allowed_solution_result_types(
        analysis: AnalysisSettingsData,
    ) -> set[str]:
        return {
            choice.result_type
            for choice in result_choices_for_analysis(
                analysis.analysis_type,
                analysis.test,
                integrator=analysis.integrator,
            )
        }

    def _materialize_solution_result_surface_scope(
        self,
        result: SolutionResultData,
    ) -> None:
        if not result.surface_scope:
            return
        result.element_scope = sorted({
            int(element_tag)
            for surface_tag in result.surface_scope
            if surface_tag in self.surfaces
            for element_tag in self.surfaces[
                surface_tag
            ].generated_element_tags
            if (
                int(element_tag) in self.model.elements
                and self.model.elements[
                    int(element_tag)
                ].element_type in SHELL_ELEMENT_TYPES
            )
        })

    def _validate_solution_result(self, result: SolutionResultData) -> None:
        if result.analysis_tag not in self.analyses:
            raise ValueError(
                f"Solution result references missing analysis "
                f"{result.analysis_tag}."
            )
        analysis = self.analyses[result.analysis_tag]
        allowed = self._allowed_solution_result_types(analysis)
        # MomentCurvature is retained as a backward-compatible saved-result
        # type. New user-created section histories use SectionResponse.
        if (
            result.result_type == "MomentCurvature"
            and analysis.analysis_type == "Static"
            and analysis.integrator == "DisplacementControl"
        ):
            allowed = set(allowed)
            allowed.add("MomentCurvature")
        if result.result_type not in allowed:
            raise ValueError(
                f"Solution result type {result.result_type} is not valid for "
                f"{analysis.analysis_type} analysis {analysis.tag}."
            )
        if result.surface_scope:
            if result.result_type not in {
                "ShellForce",
                "ShellDeformation",
                "ShellDisplacement",
            }:
                raise ValueError(
                    "Managed Surface result scope is only supported for "
                    "ShellForce, ShellDeformation and ShellDisplacement."
                )
            missing_surfaces = [
                tag for tag in result.surface_scope
                if tag not in self.surfaces
            ]
            if missing_surfaces:
                raise ValueError(
                    "Solution result references missing Surface tag(s): "
                    + ", ".join(map(str, missing_surfaces))
                )
            expected_scope = sorted({
                int(element_tag)
                for surface_tag in result.surface_scope
                for element_tag in self.surfaces[
                    surface_tag
                ].generated_element_tags
                if (
                    int(element_tag) in self.model.elements
                    and self.model.elements[
                        int(element_tag)
                    ].element_type in SHELL_ELEMENT_TYPES
                )
            })
            if result.element_scope != expected_scope:
                raise ValueError(
                    "Managed Surface result FE scope is stale. "
                    "Remesh/synchronize the Geometry Surface result scope."
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
        valid_elements = set(self.model.elements) | {
            tag
            for tag, connection in self.connections.items()
            if connection.connection_type in ELEMENT_BACKED_CONNECTION_TYPES
        }
        missing_elements = [
            tag for tag in result.element_scope
            if tag not in valid_elements
        ]
        if missing_elements:
            raise ValueError(
                "Solution result references missing element tag(s): "
                + ", ".join(map(str, missing_elements))
            )

        if result.result_type == "JointResponse":
            if len(result.element_scope) != 1:
                raise ValueError(
                    "JointResponse requires exactly one Connection/Joint target."
                )
            connection_tag = int(result.element_scope[0])
            connection = self.connections.get(connection_tag)
            if connection is None:
                raise ValueError(
                    "JointResponse target must be a Connection/Joint object."
                )
            allowed_responses = CONNECTION_RECORDER_RESPONSES.get(
                connection.connection_type,
                set(),
            )
            default_response = (
                "force"
                if connection.connection_type == "CoupledZeroLength"
                else "deformation"
            )
            response = str(
                result.settings.get("response", default_response)
            )
            if response not in allowed_responses:
                raise ValueError(
                    f"Joint response {response!r} is not supported by "
                    f"{connection.connection_type} {connection_tag}. "
                    "Allowed: "
                    + ", ".join(sorted(allowed_responses))
                )
            if connection.connection_type == "BeamColumnJoint":
                if (
                    int(self.model.ndm) == 3
                    and response == "externalDisplacement"
                ):
                    raise ValueError(
                        "BeamColumnJoint3d externalDisplacement is disabled "
                        "in SARE because the current OpenSees source allocates "
                        "12 response values but writes 24 external DOFs."
                    )
                component = _strict_int(
                    result.settings.get("component", 1),
                    "BeamColumnJoint result component",
                )
                material_queries = {
                    "shearPanel",
                    "node1BarSlipL",
                    "node1BarSlipR",
                    "node1InterfaceShear",
                    "node2BarSlipB",
                    "node2BarSlipT",
                    "node2InterfaceShear",
                    "node3BarSlipL",
                    "node3BarSlipR",
                    "node3InterfaceShear",
                    "node4BarSlipB",
                    "node4BarSlipT",
                    "node4InterfaceShear",
                }
                if response == "deformation":
                    maximum_component = 4
                elif response in material_queries:
                    # SARE requests stressStrain from the delegated
                    # UniaxialMaterial: [stress/force, strain/deformation].
                    maximum_component = 2
                elif response == "internalDisplacement":
                    maximum_component = 4
                elif response == "externalDisplacement":
                    maximum_component = (
                        12 if int(self.model.ndm) == 2 else 24
                    )
                else:
                    maximum_component = 1
                if not 1 <= component <= maximum_component:
                    raise ValueError(
                        f"BeamColumnJoint response {response!r} component "
                        f"{component} is outside 1..{maximum_component}."
                    )

        def setting_int(name: str) -> int | None:
            if name not in result.settings:
                return None
            return _strict_int(
                result.settings[name],
                f"Solution result setting {name}",
            )

        if result.result_type in {
            "DeformedShape",
            "MemberForce",
            "ModeShape",
            "Motion",
            "ShellDisplacement",
        } and "scale" in result.settings:
            try:
                scale = float(result.settings["scale"])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(
                    "Solution result scale must be a finite positive number."
                ) from exc
            if not math.isfinite(scale) or scale <= 0.0:
                raise ValueError(
                    "Solution result scale must be a finite positive number."
                )

        if result.result_type == "TimeHistory":
            node_tag = setting_int("node")
            dof = setting_int("dof")
            if node_tag is not None and node_tag not in self.model.nodes:
                raise ValueError(
                    f"TimeHistory references missing node {node_tag}."
                )
            if dof is not None and not 1 <= dof <= int(self.model.ndf):
                raise ValueError(
                    f"TimeHistory DOF {dof} is invalid for ndf={self.model.ndf}."
                )

        if result.result_type == "ForceDisplacement":
            for key in ("displacement_node", "force_node"):
                node_tag = setting_int(key)
                if node_tag is not None and node_tag not in self.model.nodes:
                    raise ValueError(
                        f"ForceDisplacement setting {key} references missing "
                        f"node {node_tag}."
                    )
            for key in ("displacement_dof", "force_dof"):
                dof = setting_int(key)
                if dof is not None and not 1 <= dof <= int(self.model.ndf):
                    raise ValueError(
                        f"ForceDisplacement setting {key}={dof} is invalid "
                        f"for ndf={self.model.ndf}."
                    )

        if result.result_type in {
            "ShellForce",
            "ShellDeformation",
            "ShellDisplacement",
        }:
            if result.result_type == "ShellForce":
                allowed_components = {
                    "Nxx", "Nyy", "Nxy",
                    "Mxx", "Myy", "Mxy",
                    "Qx", "Qy",
                }
                default_component = "Nxx"
            elif result.result_type == "ShellDeformation":
                allowed_components = {
                    "Exx", "Eyy", "Gxy", "E1", "E2",
                    "Kxx", "Kyy", "Kxy",
                    "Gxz", "Gyz",
                }
                default_component = "Exx"
            else:
                allowed_components = {"|U|", "UX", "UY", "UZ"}
                default_component = "|U|"
            component = str(
                result.settings.get("component", default_component)
            )
            if component not in allowed_components:
                raise ValueError(
                    f"Unsupported {result.result_type} component "
                    f"{component!r}."
                )
            if result.result_type == "ShellDeformation":
                location = str(
                    result.settings.get("location", "mid")
                )
                if location not in {"mid", "top", "bottom"}:
                    raise ValueError(
                        "ShellDeformation location must be one of "
                        "'mid', 'top', or 'bottom'."
                    )
            if result.surface_scope:
                scope = list(result.element_scope)
            else:
                scope = (
                    list(result.element_scope)
                    if result.element_scope
                    else [
                        tag
                        for tag, element in self.model.elements.items()
                        if element.element_type in SHELL_ELEMENT_TYPES
                    ]
                )
            if not scope and not result.surface_scope:
                raise ValueError(
                    f"{result.result_type} requires at least one Shell element."
                )
            incompatible = [
                tag
                for tag in scope
                if (
                    tag not in self.model.elements
                    or self.model.elements[tag].element_type
                    not in SHELL_ELEMENT_TYPES
                )
            ]
            if incompatible:
                raise ValueError(
                    f"{result.result_type} requires Shell element tag(s): "
                    + ", ".join(map(str, incompatible))
                )

        if result.result_type == "SectionResponse":
            if len(result.element_scope) != 1:
                raise ValueError(
                    "SectionResponse requires exactly one element in its "
                    "element scope. Select one zeroLengthSection, "
                    "forceBeamColumn, or dispBeamColumn element."
                )
            section_number = setting_int("section")
            if section_number is None:
                section_number = 1
            component = str(result.settings.get("component", "Mz"))
            validate_section_response_request(
                self.model,
                self.connections,
                element_tag=result.element_scope[0],
                section_number=section_number,
                component=component,
            )

        if result.result_type in {"FiberStress", "FiberStrain"}:
            section_number = setting_int("section")
            if section_number is None:
                section_number = 1
            if section_number < 1:
                raise ValueError(
                    "Fiber result section/IP number must be at least 1."
                )
            if result.element_scope:
                incompatible = [
                    tag
                    for tag in result.element_scope
                    if (
                        tag not in self.model.elements
                        or self.model.elements[tag].element_type
                        not in {"forceBeamColumn", "dispBeamColumn"}
                    )
                ]
                if incompatible:
                    raise ValueError(
                        "Fiber results require forceBeamColumn or "
                        "dispBeamColumn element tag(s): "
                        + ", ".join(map(str, incompatible))
                    )
                too_short = [
                    tag
                    for tag in result.element_scope
                    if self.model.elements[tag].integration_points
                    < section_number
                ]
                if too_short:
                    raise ValueError(
                        f"Fiber result section/IP {section_number} exceeds "
                        "the integration-point count for element tag(s): "
                        + ", ".join(map(str, too_short))
                    )

        if (
            result.result_type == "ModeShape"
            or (
                result.result_type == "Motion"
                and analysis.analysis_type == "Modal"
            )
        ):
            mode = setting_int("mode")
            if mode is None:
                mode = 1
            if not 1 <= mode <= int(analysis.num_modes):
                raise ValueError(
                    f"Requested mode {mode} exceeds Modal analysis "
                    f"{analysis.tag} num_modes={analysis.num_modes}."
                )

    def add_solution_result(self, result: SolutionResultData) -> None:
        if result.tag in self.solution_results:
            raise ValueError(
                f"Solution result tag {result.tag} already exists."
            )
        self._materialize_solution_result_surface_scope(result)
        self._validate_solution_result(result)
        self.solution_results[result.tag] = result

    def update_solution_result(
        self,
        original_tag: int,
        result: SolutionResultData,
    ) -> None:
        original_tag = _strict_int(
            original_tag,
            "Solution result original tag",
        )
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
        self._materialize_solution_result_surface_scope(result)
        self._validate_solution_result(result)
        self.solution_results.pop(original_tag)
        self.solution_results[result.tag] = result

    def remove_solution_result(self, tag: int) -> None:
        tag = _strict_int(tag, "Solution result tag")
        self.solution_results.pop(tag, None)

    def solution_results_for_analysis(
        self,
        analysis_tag: int,
    ) -> list[SolutionResultData]:
        target = _strict_int(analysis_tag, "Analysis tag")
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
            "sketch_planes": [
                self.sketch_planes[tag].to_dict()
                for tag in sorted(self.sketch_planes)
            ],
            "points": [
                self.points[tag].to_dict()
                for tag in sorted(self.points)
            ],
            "lines": [
                self.lines[tag].to_dict()
                for tag in sorted(self.lines)
            ],
            "surfaces": [
                self.surfaces[tag].to_dict()
                for tag in sorted(self.surfaces)
            ],
            "surface_edge_supports": [
                self.surface_edge_supports[tag].to_dict()
                for tag in sorted(self.surface_edge_supports)
            ],
            "surface_edge_loads": [
                self.surface_edge_loads[tag].to_dict()
                for tag in sorted(self.surface_edge_loads)
            ],
            "surface_pressures": [
                self.surface_pressures[tag].to_dict()
                for tag in sorted(self.surface_pressures)
            ],
            "surface_recorders": [
                self.surface_recorders[tag].to_dict()
                for tag in sorted(self.surface_recorders)
            ],
            "materials": [
                self.materials[tag].to_dict()
                for tag in sorted(self.materials)
            ],
            "nd_materials": [
                self.nd_materials[tag].to_dict()
                for tag in sorted(self.nd_materials)
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
    def _load_sketch_planes(raw: Any) -> dict[int, SketchPlaneData]:
        result: dict[int, SketchPlaneData] = {}
        for index, item in enumerate(
            _require_list(raw, "Sketch Planes")
        ):
            plane = SketchPlaneData.from_dict(
                _require_object(item, f"Sketch Plane item {index}")
            )
            if plane.tag in result:
                raise ValueError(
                    f"Duplicate Sketch Plane tag {plane.tag}."
                )
            result[plane.tag] = plane
        return result

    @staticmethod
    def _load_points(raw: Any) -> dict[int, PointGeometryData]:
        result: dict[int, PointGeometryData] = {}
        for index, item in enumerate(
            _require_list(raw, "Geometry Points")
        ):
            point = PointGeometryData.from_dict(
                _require_object(item, f"Geometry Point item {index}")
            )
            if point.tag in result:
                raise ValueError(
                    f"Duplicate Geometry Point tag {point.tag}."
                )
            result[point.tag] = point
        return result

    @staticmethod
    def _load_lines(raw: Any) -> dict[int, LineGeometryData]:
        result: dict[int, LineGeometryData] = {}
        for index, item in enumerate(
            _require_list(raw, "Geometry Lines")
        ):
            line = LineGeometryData.from_dict(
                _require_object(item, f"Geometry Line item {index}")
            )
            if line.tag in result:
                raise ValueError(
                    f"Duplicate Geometry Line tag {line.tag}."
                )
            result[line.tag] = line
        return result

    @staticmethod
    def _load_surfaces(raw: Any) -> dict[int, SurfaceGeometryData]:
        result: dict[int, SurfaceGeometryData] = {}
        for index, item in enumerate(
            _require_list(raw, "Surface geometries")
        ):
            surface = SurfaceGeometryData.from_dict(
                _require_object(item, f"Surface geometry item {index}")
            )
            if surface.tag in result:
                raise ValueError(
                    f"Duplicate surface geometry tag {surface.tag}."
                )
            result[surface.tag] = surface
        return result

    @staticmethod
    def _load_surface_edge_supports(
        raw: Any,
    ) -> dict[int, SurfaceEdgeSupportData]:
        result: dict[int, SurfaceEdgeSupportData] = {}
        for index, item in enumerate(
            _require_list(raw, "Surface edge supports")
        ):
            support = SurfaceEdgeSupportData.from_dict(
                _require_object(
                    item,
                    f"Surface edge support item {index}",
                )
            )
            if support.tag in result:
                raise ValueError(
                    f"Duplicate Surface edge support tag {support.tag}."
                )
            result[support.tag] = support
        return result

    @staticmethod
    def _load_surface_edge_loads(
        raw: Any,
    ) -> dict[int, SurfaceEdgeLoadData]:
        result: dict[int, SurfaceEdgeLoadData] = {}
        for index, item in enumerate(
            _require_list(raw, "Surface edge loads")
        ):
            edge_load = SurfaceEdgeLoadData.from_dict(
                _require_object(
                    item,
                    f"Surface edge load item {index}",
                )
            )
            if edge_load.tag in result:
                raise ValueError(
                    f"Duplicate Surface edge load tag {edge_load.tag}."
                )
            result[edge_load.tag] = edge_load
        return result

    @staticmethod
    def _load_surface_pressures(
        raw: Any,
    ) -> dict[int, SurfacePressureData]:
        result: dict[int, SurfacePressureData] = {}
        for index, item in enumerate(
            _require_list(raw, "Surface pressures")
        ):
            pressure = SurfacePressureData.from_dict(
                _require_object(
                    item,
                    f"Surface pressure item {index}",
                )
            )
            if pressure.tag in result:
                raise ValueError(
                    f"Duplicate Surface pressure tag {pressure.tag}."
                )
            result[pressure.tag] = pressure
        return result

    @staticmethod
    def _load_surface_recorders(
        raw: Any,
    ) -> dict[int, SurfaceRecorderData]:
        result: dict[int, SurfaceRecorderData] = {}
        for index, item in enumerate(
            _require_list(raw, "Surface recorders")
        ):
            surface_recorder = SurfaceRecorderData.from_dict(
                _require_object(
                    item,
                    f"Surface recorder item {index}",
                )
            )
            if surface_recorder.tag in result:
                raise ValueError(
                    f"Duplicate Surface recorder tag "
                    f"{surface_recorder.tag}."
                )
            result[surface_recorder.tag] = surface_recorder
        return result

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
                    raise ValueError(
                        f"Legacy material {raw_tag!r} must be an object."
                    )
                data = dict(raw_data)
                if "tag" not in data:
                    data["tag"] = _strict_int(
                        raw_tag,
                        "Legacy material tag",
                    )
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
                if material.tag in materials:
                    raise ValueError(
                        f"Duplicate material tag {material.tag}."
                    )
                materials[material.tag] = material

        return materials

    @staticmethod
    def _load_nd_materials(raw: Any) -> dict[int, NDMaterialData]:
        materials: dict[int, NDMaterialData] = {}
        if raw is None:
            return materials
        items = _require_list(raw, "nDMaterials")
        for index, item in enumerate(items):
            material = NDMaterialData.from_dict(
                _require_object(item, f"nDMaterial item {index}")
            )
            if material.tag in materials:
                raise ValueError(
                    f"Duplicate nDMaterial tag {material.tag}."
                )
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
                    raise ValueError(
                        f"Legacy section {raw_tag!r} must be an object."
                    )
                data = dict(raw_data)
                if "tag" not in data:
                    data["tag"] = _strict_int(
                        raw_tag,
                        "Legacy section tag",
                    )
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
                if section.tag in sections:
                    raise ValueError(
                        f"Duplicate section tag {section.tag}."
                    )
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
                    raise ValueError(
                        f"Legacy transformation {raw_tag!r} must be an object."
                    )
                data = dict(raw_data)
                if "tag" not in data:
                    data["tag"] = _strict_int(
                        raw_tag,
                        "Legacy transformation tag",
                    )
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
                if transformation.tag in transformations:
                    raise ValueError(
                        f"Duplicate transformation tag {transformation.tag}."
                    )
                transformations[transformation.tag] = transformation

        return transformations

    @staticmethod
    def _load_constraints(raw: Any) -> dict[int, ConstraintData]:
        constraints: dict[int, ConstraintData] = {}
        items = _require_list(raw, "Constraints")
        for index, item in enumerate(items):
            constraint = ConstraintData.from_dict(
                _require_object(item, f"Constraint item {index}")
            )
            if constraint.tag in constraints:
                raise ValueError(
                    f"Duplicate constraint tag {constraint.tag}."
                )
            constraints[constraint.tag] = constraint
        return constraints

    @staticmethod
    def _load_connections(raw: Any) -> dict[int, ConnectionData]:
        connections: dict[int, ConnectionData] = {}
        items = _require_list(raw, "Connections")
        for index, item in enumerate(items):
            connection = ConnectionData.from_dict(
                _require_object(item, f"Connection item {index}")
            )
            if connection.tag in connections:
                raise ValueError(
                    f"Duplicate connection tag {connection.tag}."
                )
            connections[connection.tag] = connection
        return connections

    @staticmethod
    def _load_time_series(raw: Any) -> dict[int, TimeSeriesData]:
        result: dict[int, TimeSeriesData] = {}
        items = _require_list(raw, "Time series")
        for index, item in enumerate(items):
            series = TimeSeriesData.from_dict(
                _require_object(item, f"Time series item {index}")
            )
            if series.tag in result:
                raise ValueError(
                    f"Duplicate time series tag {series.tag}."
                )
            result[series.tag] = series
        return result

    @staticmethod
    def _load_patterns(raw: Any) -> dict[int, LoadPatternData]:
        result: dict[int, LoadPatternData] = {}
        items = _require_list(raw, "Load patterns")
        for index, item in enumerate(items):
            pattern = LoadPatternData.from_dict(
                _require_object(item, f"Load pattern item {index}")
            )
            if pattern.tag in result:
                raise ValueError(
                    f"Duplicate load pattern tag {pattern.tag}."
                )
            result[pattern.tag] = pattern
        return result

    @staticmethod
    def _load_nodal_loads(raw: Any) -> dict[int, NodalLoadData]:
        result: dict[int, NodalLoadData] = {}
        items = _require_list(raw, "Nodal loads")
        for index, item in enumerate(items):
            load = NodalLoadData.from_dict(
                _require_object(item, f"Nodal load item {index}")
            )
            if load.tag in result:
                raise ValueError(
                    f"Duplicate nodal load tag {load.tag}."
                )
            result[load.tag] = load
        return result

    @staticmethod
    def _load_prescribed_displacements(
        raw: Any,
    ) -> dict[int, PrescribedDisplacementData]:
        result: dict[int, PrescribedDisplacementData] = {}
        items = _require_list(raw, "Prescribed displacements")
        for index, item in enumerate(items):
            displacement = PrescribedDisplacementData.from_dict(
                _require_object(
                    item,
                    f"Prescribed displacement item {index}",
                )
            )
            if displacement.tag in result:
                raise ValueError(
                    "Duplicate prescribed displacement tag "
                    f"{displacement.tag}."
                )
            result[displacement.tag] = displacement
        return result

    @staticmethod
    def _load_element_loads(raw: Any) -> dict[int, ElementLoadData]:
        result: dict[int, ElementLoadData] = {}
        items = _require_list(raw, "Element loads")
        for index, item in enumerate(items):
            load = ElementLoadData.from_dict(
                _require_object(item, f"Element load item {index}")
            )
            if load.tag in result:
                raise ValueError(
                    f"Duplicate element load tag {load.tag}."
                )
            result[load.tag] = load
        return result

    @staticmethod
    def _load_mass_sources(raw: Any) -> dict[int, MassSourceData]:
        result: dict[int, MassSourceData] = {}
        items = _require_list(raw, "Mass sources")
        for index, item in enumerate(items):
            source = MassSourceData.from_dict(
                _require_object(item, f"Mass source item {index}")
            )
            if source.tag in result:
                raise ValueError(
                    f"Duplicate mass source tag {source.tag}."
                )
            result[source.tag] = source
        return result

    @staticmethod
    def _load_analyses(raw: Any) -> dict[int, AnalysisSettingsData]:
        result: dict[int, AnalysisSettingsData] = {}
        items = _require_list(raw, "Analyses")
        for index, item in enumerate(items):
            analysis = AnalysisSettingsData.from_dict(
                _require_object(item, f"Analysis item {index}")
            )
            if analysis.tag in result:
                raise ValueError(
                    f"Duplicate analysis tag {analysis.tag}."
                )
            result[analysis.tag] = analysis
        return result

    @staticmethod
    def _load_solution_results(
        raw: Any,
    ) -> dict[int, SolutionResultData]:
        result: dict[int, SolutionResultData] = {}
        items = _require_list(raw, "Solution results")
        for index, item in enumerate(items):
            solution_result = SolutionResultData.from_dict(
                _require_object(item, f"Solution result item {index}")
            )
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
        items = _require_list(raw, "Recorders")
        for index, item in enumerate(items):
            recorder = RecorderData.from_dict(
                _require_object(item, f"Recorder item {index}")
            )
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

        version = _strict_int(
            data.get("version", 0),
            "Project version",
        )
        if version > PROJECT_FORMAT_VERSION:
            raise ValueError(
                f"Project version {version} is newer than supported "
                f"version {PROJECT_FORMAT_VERSION}."
            )
        if version < 1:
            raise ValueError(f"Unsupported project version: {version}")

        selection_sets = {}
        raw_selection_sets = _require_list(
            data.get("selection_sets", []),
            "Selection sets",
        )
        for index, item in enumerate(raw_selection_sets):
            selection_set = SelectionSetData.from_dict(
                _require_object(item, f"Selection set item {index}")
            )
            if selection_set.name in selection_sets:
                raise ValueError(
                    f"Duplicate selection set name {selection_set.name!r}."
                )
            selection_sets[selection_set.name] = selection_set

        project = cls(
            name=str(data.get("name", "Untitled")),
            model=StructuralModel.from_dict(data.get("model", {})),
            selection_sets=selection_sets,
            sketch_planes=cls._load_sketch_planes(
                data.get("sketch_planes", [])
            ),
            points=cls._load_points(data.get("points", [])),
            lines=cls._load_lines(data.get("lines", [])),
            surfaces=cls._load_surfaces(data.get("surfaces", [])),
            surface_edge_supports=cls._load_surface_edge_supports(
                data.get("surface_edge_supports", [])
            ),
            surface_edge_loads=cls._load_surface_edge_loads(
                data.get("surface_edge_loads", [])
            ),
            surface_pressures=cls._load_surface_pressures(
                data.get("surface_pressures", [])
            ),
            surface_recorders=cls._load_surface_recorders(
                data.get("surface_recorders", [])
            ),
            materials=cls._load_materials(data.get("materials", [])),
            nd_materials=cls._load_nd_materials(
                data.get("nd_materials", [])
            ),
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
                _strict_int(
                    data["active_analysis_tag"],
                    "Active analysis tag",
                )
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
        for selection_set in project.selection_sets.values():
            project._materialize_selection_set_surface_scope(selection_set)
            project.validate_selection_set(selection_set)
        for line in project.lines.values():
            project._validate_line_geometry(line)
        for surface in project.surfaces.values():
            project._validate_surface_geometry(surface)
        for support in project.surface_edge_supports.values():
            project._validate_surface_edge_support(support)
        for edge_load in project.surface_edge_loads.values():
            project._validate_surface_edge_load(edge_load)
        for surface_pressure in project.surface_pressures.values():
            project._validate_surface_pressure(surface_pressure)
        for surface_recorder in project.surface_recorders.values():
            project._validate_surface_recorder(surface_recorder)
        # BeamColumnJoint has strict node/material semantics and may exist
        # in older SARE files created before those guards were added.
        # Revalidate it on project load so invalid legacy geometry cannot be
        # silently exported to OpenSees.
        beam_column_joint_tags: set[int] = set()
        for connection in project.connections.values():
            if connection.connection_type == "BeamColumnJoint":
                project._validate_connection(connection)
                beam_column_joint_tags.add(int(connection.tag))

        # Legacy project files bypass add_recorder()/add_solution_result()
        # while they are deserialized. Re-run the BeamColumnJoint-specific
        # guards so stale/unsafe response requests cannot reach OpenSees.
        for recorder in project.recorders.values():
            if (
                recorder.recorder_type == "Element"
                and beam_column_joint_tags.intersection(
                    int(tag) for tag in recorder.target_tags
                )
            ):
                project._validate_recorder(recorder)
        for result in project.solution_results.values():
            if (
                result.result_type == "JointResponse"
                and beam_column_joint_tags.intersection(
                    int(tag) for tag in result.element_scope
                )
            ):
                project._validate_solution_result(result)

        if (
            project.active_analysis_tag is not None
            and project.active_analysis_tag not in project.analyses
        ):
            raise ValueError(
                "Active analysis tag "
                f"{project.active_analysis_tag} does not exist."
            )
        return project

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
