from __future__ import annotations

import math

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

Vec3 = Tuple[float, float, float]

FRAME_ELEMENT_TYPES = {
    "elasticBeamColumn",
    "ElasticTimoshenkoBeam",
    "forceBeamColumn",
    "dispBeamColumn",
    "dispBeamColumnInt",
}
BEAM_INTEGRATION_ELEMENT_TYPES = {
    "forceBeamColumn",
    "dispBeamColumn",
}
SHELL_ELEMENT_TYPES = {
    "ASDShellQ4",
    "ShellMITC4",
    "ShellDKGQ",
    "ShellNLDKGQ",
}
MEMBRANE_ELEMENT_TYPES = {"MEFI"}
CONTINUUM_QUAD_ELEMENT_TYPES = {
    "quad",
    "SSPquad",
    "bbarQuad",
    "enhancedQuad",
}
SOLID_ELEMENT_TYPES = {"stdBrick", "SSPbrick", "bbarBrick"}
WALL_MACRO_2D_ELEMENT_TYPES = {"MVLEM", "SFI_MVLEM"}
WALL_MACRO_3D_ELEMENT_TYPES = {"MVLEM_3D"}
WALL_MACRO_ELEMENT_TYPES = (
    WALL_MACRO_2D_ELEMENT_TYPES | WALL_MACRO_3D_ELEMENT_TYPES
)
TRUSS_ELEMENT_TYPES = {"truss", "corotTruss"}
CABLE_ELEMENT_TYPES = {"CatenaryCable"}
BEARING_ELEMENT_TYPES = {"elastomericBearingPlasticity"}
SPECIAL_TWO_NODE_ELEMENT_TYPES = CABLE_ELEMENT_TYPES | BEARING_ELEMENT_TYPES
EMBEDDED_ELEMENT_TYPES = {"ASDEmbeddedNodeElement"}
QUAD_ELEMENT_TYPES = (
    SHELL_ELEMENT_TYPES
    | MEMBRANE_ELEMENT_TYPES
    | CONTINUUM_QUAD_ELEMENT_TYPES
    | WALL_MACRO_3D_ELEMENT_TYPES
)
SUPPORTED_ELEMENT_TYPES = (
    FRAME_ELEMENT_TYPES
    | QUAD_ELEMENT_TYPES
    | SOLID_ELEMENT_TYPES
    | WALL_MACRO_2D_ELEMENT_TYPES
    | TRUSS_ELEMENT_TYPES
    | SPECIAL_TWO_NODE_ELEMENT_TYPES
    | EMBEDDED_ELEMENT_TYPES
)


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


def _normalize_special_element_parameters(
    element_type: str,
    parameters: object,
) -> dict[str, object]:
    if element_type not in SPECIAL_TWO_NODE_ELEMENT_TYPES:
        return {}
    if not isinstance(parameters, dict):
        raise ValueError(
            f"{element_type} special parameters must be an object."
        )
    raw = dict(parameters)

    if element_type == "CatenaryCable":
        required = (
            "weight", "E", "A", "L0", "alpha", "temperature_change",
            "rho", "errorTol", "Nsubsteps", "massType",
        )
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(
                "CatenaryCable requires parameter(s): "
                + ", ".join(missing)
                + "."
            )
        extra = sorted(set(raw) - set(required))
        if extra:
            raise ValueError(
                "Unsupported CatenaryCable parameter(s): "
                + ", ".join(extra)
                + "."
            )
        result: dict[str, object] = {
            key: float(raw[key])
            for key in (
                "weight", "E", "A", "L0", "alpha",
                "temperature_change", "rho", "errorTol",
            )
        }
        result["Nsubsteps"] = _strict_int(
            raw["Nsubsteps"],
            "CatenaryCable Nsubsteps",
        )
        result["massType"] = _strict_int(
            raw["massType"],
            "CatenaryCable massType",
        )
        if any(
            not math.isfinite(float(result[key]))
            for key in (
                "weight", "E", "A", "L0", "alpha",
                "temperature_change", "rho", "errorTol",
            )
        ):
            raise ValueError("CatenaryCable parameters must be finite.")
        for key in ("E", "A", "L0", "errorTol"):
            if float(result[key]) <= 0.0:
                raise ValueError(
                    f"CatenaryCable {key} must be positive."
                )
        if float(result["rho"]) < 0.0:
            raise ValueError("CatenaryCable rho cannot be negative.")
        if int(result["Nsubsteps"]) < 1:
            raise ValueError(
                "CatenaryCable Nsubsteps must be at least 1."
            )
        if int(result["massType"]) != 0:
            raise ValueError(
                "CatenaryCable currently supports massType=0 "
                "(lumped mass) only."
            )
        return result

    required = (
        "kInit", "qd", "alpha1", "alpha2", "mu",
        "p_mat_tag", "mz_mat_tag",
    )
    optional = {
        "t_mat_tag",
        "my_mat_tag",
        "orientation",
        "shearDist",
        "doRayleigh",
        "mass",
    }
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(
            "elastomericBearingPlasticity requires parameter(s): "
            + ", ".join(missing)
            + "."
        )
    extra = sorted(set(raw) - set(required) - optional)
    if extra:
        raise ValueError(
            "Unsupported elastomericBearingPlasticity parameter(s): "
            + ", ".join(extra)
            + "."
        )

    result = {
        key: float(raw[key])
        for key in ("kInit", "qd", "alpha1", "alpha2", "mu")
    }
    result["p_mat_tag"] = _strict_int(
        raw["p_mat_tag"],
        "Bearing axial material tag",
    )
    result["mz_mat_tag"] = _strict_int(
        raw["mz_mat_tag"],
        "Bearing Mz material tag",
    )
    for key, label in (
        ("t_mat_tag", "Bearing torsion material tag"),
        ("my_mat_tag", "Bearing My material tag"),
    ):
        value = raw.get(key)
        result[key] = (
            None if value is None else _strict_int(value, label)
        )
    result["shearDist"] = float(raw.get("shearDist", 0.5))
    result["doRayleigh"] = _strict_bool(
        raw.get("doRayleigh", False),
        "Bearing Rayleigh flag",
    )
    result["mass"] = float(raw.get("mass", 0.0))

    orientation = raw.get("orientation")
    if orientation is None:
        result["orientation"] = None
    else:
        try:
            values = tuple(float(value) for value in orientation)
        except TypeError as exc:
            raise ValueError(
                "Bearing orientation must contain six values."
            ) from exc
        if len(values) != 6 or any(
            not math.isfinite(value) for value in values
        ):
            raise ValueError(
                "Bearing orientation must contain six finite values."
            )
        x = values[:3]
        y = values[3:]
        x_norm2 = sum(value * value for value in x)
        y_norm2 = sum(value * value for value in y)
        cross = (
            x[1] * y[2] - x[2] * y[1],
            x[2] * y[0] - x[0] * y[2],
            x[0] * y[1] - x[1] * y[0],
        )
        if (
            x_norm2 <= 1.0e-24
            or y_norm2 <= 1.0e-24
            or sum(value * value for value in cross)
            <= 1.0e-16 * x_norm2 * y_norm2
        ):
            raise ValueError(
                "Bearing orientation x/y vectors must be non-zero "
                "and non-parallel."
            )
        result["orientation"] = values

    if any(
        not math.isfinite(float(result[key]))
        for key in (
            "kInit", "qd", "alpha1", "alpha2", "mu",
            "shearDist", "mass",
        )
    ):
        raise ValueError(
            "elastomericBearingPlasticity parameters must be finite."
        )
    if float(result["kInit"]) <= 0.0:
        raise ValueError("Bearing kInit must be positive.")
    if float(result["qd"]) < 0.0:
        raise ValueError("Bearing qd cannot be negative.")
    if float(result["alpha1"]) < 0.0 or float(result["alpha2"]) < 0.0:
        raise ValueError("Bearing alpha1/alpha2 cannot be negative.")
    if float(result["mu"]) <= 0.0:
        raise ValueError("Bearing mu must be positive.")
    if not 0.0 <= float(result["shearDist"]) <= 1.0:
        raise ValueError("Bearing shearDist must satisfy 0 <= value <= 1.")
    if float(result["mass"]) < 0.0:
        raise ValueError("Bearing mass cannot be negative.")
    for key in ("p_mat_tag", "mz_mat_tag", "t_mat_tag", "my_mat_tag"):
        value = result.get(key)
        if value is not None and int(value) <= 0:
            raise ValueError("Bearing material tags must be positive.")
    return result


FIXITY_PRESETS: dict[str, Tuple[int, ...]] = {
    "Fixed": (1, 1, 1, 1, 1, 1),
    "Pinned": (1, 1, 1, 0, 0, 0),
    "Roller X": (0, 1, 1, 0, 0, 0),
    "Roller Y": (1, 0, 1, 0, 0, 0),
    "Roller Z": (1, 1, 0, 0, 0, 0),
}


def dof_labels_for_model(ndm: int, ndf: int) -> tuple[str, ...]:
    """Return OpenSees nodal DOF labels for a model dimension/DOF count."""
    ndm = _strict_int(ndm, "Model ndm")
    ndf = _strict_int(ndf, "Model ndf")
    if ndm == 1:
        return ("UX",)[:ndf] + tuple(
            f"DOF {index}" for index in range(2, ndf + 1)
        )
    if ndm == 2:
        if ndf <= 2:
            return ("UX", "UY")[:ndf]
        if ndf == 3:
            return ("UX", "UY", "RZ")
        base = ("UX", "UY", "RZ")
        return base + tuple(f"DOF {index}" for index in range(4, ndf + 1))
    if ndm == 3:
        labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        return labels[:ndf]
    return tuple(f"DOF {index}" for index in range(1, ndf + 1))


def dof_is_rotation(ndm: int, ndf: int, dof: int) -> bool:
    dof = _strict_int(dof, "DOF")
    labels = dof_labels_for_model(ndm, ndf)
    return 1 <= dof <= len(labels) and labels[dof - 1].startswith("R")


def fixity_presets_for_model(
    ndm: int,
    ndf: int,
) -> dict[str, Tuple[int, ...]]:
    """Return support presets that are representable by this OpenSees model."""
    ndm = _strict_int(ndm, "Model ndm")
    ndf = _strict_int(ndf, "Model ndf")
    if (ndm, ndf) == (3, 6):
        return dict(FIXITY_PRESETS)
    if (ndm, ndf) == (2, 3):
        return {
            "Fixed": (1, 1, 1),
            "Pinned": (1, 1, 0),
            "Roller X": (0, 1, 0),
            "Roller Y": (1, 0, 0),
        }
    if (ndm, ndf) == (2, 2):
        return {
            "Fixed": (1, 1),
            "Roller X": (0, 1),
            "Roller Y": (1, 0),
        }
    if (ndm, ndf) == (3, 3):
        return {
            "Fixed": (1, 1, 1),
            "Roller X": (0, 1, 1),
            "Roller Y": (1, 0, 1),
            "Roller Z": (1, 1, 0),
        }
    return {"Fixed": (1,) * ndf}


def classify_fixity(
    values: Iterable[int],
    *,
    ndm: int | None = None,
) -> str:
    fixity = tuple(
        _strict_int(value, "Fixity value")
        for value in values
    )
    if not any(fixity):
        return "Free"
    presets = (
        fixity_presets_for_model(ndm, len(fixity))
        if ndm is not None
        else FIXITY_PRESETS
    )
    for name, preset in presets.items():
        if fixity == preset:
            return name
    return "Custom"


@dataclass(slots=True)
class Node:
    tag: int
    xyz: Vec3
    fixity: Tuple[int, ...] = (0, 0, 0, 0, 0, 0)
    mass: Tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Node tag")
        if self.tag < 0:
            raise ValueError("Node tag must be a non-negative integer.")

        self.xyz = tuple(float(value) for value in self.xyz)
        if len(self.xyz) != 3:
            raise ValueError("Node coordinates must contain three values.")
        if any(not math.isfinite(value) for value in self.xyz):
            raise ValueError("Node coordinates must be finite.")

        self.fixity = tuple(
            _strict_int(value, "Fixity value")
            for value in self.fixity
        )
        if any(value not in {0, 1} for value in self.fixity):
            raise ValueError("Fixity values must be 0 or 1.")

        self.mass = tuple(float(value) for value in self.mass)
        if any(not math.isfinite(value) for value in self.mass):
            raise ValueError("Nodal mass values must be finite.")
        if any(value < 0.0 for value in self.mass):
            raise ValueError("Nodal mass values cannot be negative.")


@dataclass(slots=True)
class Element:
    tag: int
    i: int
    j: int
    element_type: str = "elasticBeamColumn"
    section_tag: int | None = None
    transf_tag: int | None = None
    group: str = "frame"
    integration_type: str = "Lobatto"
    integration_points: int = 5
    force_max_iter: int = 10
    force_tolerance: float = 1.0e-12
    mass_per_length: float = 0.0
    consistent_mass: bool = False
    hinge_i_section_tag: int | None = None
    hinge_j_section_tag: int | None = None
    interior_section_tag: int | None = None
    hinge_i_length: float = 0.0
    hinge_j_length: float = 0.0
    truss_area: float = 0.0
    truss_material_tag: int | None = None
    truss_do_rayleigh: bool = False
    k: int | None = None
    l: int | None = None
    shell_corotational: bool = False
    shell_local_x: tuple[float, float, float] | None = None
    shell_no_eas: bool = False
    shell_drilling_stab: float | None = None
    shell_drilling_nl: bool = False
    mefi_widths: tuple[float, ...] = ()
    mefi_section_tags: tuple[int, ...] = ()
    embedded_penalty: float | None = None
    embedded_constrain_rotation: bool = False
    continuum_thickness: float = 1.0
    continuum_material_tag: int | None = None
    continuum_type: str = "PlaneStrain"
    continuum_pressure: float = 0.0
    continuum_density: float = 0.0
    continuum_body_force: tuple[float, float] = (0.0, 0.0)
    m: int | None = None
    n: int | None = None
    p: int | None = None
    q: int | None = None
    solid_material_tag: int | None = None
    solid_body_force: tuple[float, float, float] = (0.0, 0.0, 0.0)
    wall_center_ratio: float = 0.4
    wall_density: float = 0.0
    wall_thicknesses: tuple[float, ...] = ()
    wall_widths: tuple[float, ...] = ()
    wall_rhos: tuple[float, ...] = ()
    wall_concrete_tags: tuple[int, ...] = ()
    wall_steel_tags: tuple[int, ...] = ()
    wall_shear_tag: int | None = None
    wall_nd_material_tags: tuple[int, ...] = ()
    wall_thick_mod: float = 0.63
    wall_poisson: float = 0.25
    beam_center_ratio: float = 0.4
    special_parameters: dict[str, object] = field(default_factory=dict)

    @property
    def is_shell(self) -> bool:
        return self.element_type in SHELL_ELEMENT_TYPES

    @property
    def is_quad(self) -> bool:
        return self.element_type in QUAD_ELEMENT_TYPES

    @property
    def is_embedded(self) -> bool:
        return self.element_type in EMBEDDED_ELEMENT_TYPES

    @property
    def is_continuum_quad(self) -> bool:
        return self.element_type in CONTINUUM_QUAD_ELEMENT_TYPES

    @property
    def is_solid(self) -> bool:
        return self.element_type in SOLID_ELEMENT_TYPES

    @property
    def is_wall_macro(self) -> bool:
        return self.element_type in WALL_MACRO_ELEMENT_TYPES

    def node_tags(self) -> tuple[int, ...]:
        if self.is_solid:
            tail = (self.k, self.l, self.m, self.n, self.p, self.q)
            if any(value is None for value in tail):
                return (self.i, self.j)
            return (
                self.i,
                self.j,
                *(int(value) for value in tail if value is not None),
            )
        if self.is_quad or self.is_embedded:
            if self.k is None or self.l is None:
                return (self.i, self.j)
            return (self.i, self.j, self.k, self.l)
        return (self.i, self.j)

    def __post_init__(self) -> None:
        self.tag = _strict_int(self.tag, "Element tag")
        self.i = _strict_int(self.i, "Element I-node tag")
        self.j = _strict_int(self.j, "Element J-node tag")
        self.element_type = str(self.element_type)
        if self.element_type not in SUPPORTED_ELEMENT_TYPES:
            raise ValueError(
                f"Unsupported element type: {self.element_type}"
            )
        self.group = str(self.group)
        self.integration_type = str(self.integration_type)
        self.integration_points = _strict_int(
            self.integration_points,
            "Beam integration-point count",
        )
        self.force_max_iter = _strict_int(
            self.force_max_iter,
            "Force-based element max iterations",
        )
        self.force_tolerance = float(self.force_tolerance)
        self.mass_per_length = float(self.mass_per_length)
        self.consistent_mass = _strict_bool(
            self.consistent_mass,
            "Element consistent_mass",
        )
        hinge_types = {
            "HingeRadau",
            "HingeRadauTwo",
            "HingeMidpoint",
            "HingeEndpoint",
            "ConcentratedPlasticity",
        }
        uses_hinge_sections = self.integration_type in hinge_types
        self.hinge_i_section_tag = (
            None
            if self.hinge_i_section_tag is None
            else (
                _strict_int(
                    self.hinge_i_section_tag,
                    "Element I-hinge section tag",
                )
                if uses_hinge_sections
                else int(self.hinge_i_section_tag)
            )
        )
        self.hinge_j_section_tag = (
            None
            if self.hinge_j_section_tag is None
            else (
                _strict_int(
                    self.hinge_j_section_tag,
                    "Element J-hinge section tag",
                )
                if uses_hinge_sections
                else int(self.hinge_j_section_tag)
            )
        )
        self.interior_section_tag = (
            None
            if self.interior_section_tag is None
            else (
                _strict_int(
                    self.interior_section_tag,
                    "Element interior section tag",
                )
                if uses_hinge_sections
                else int(self.interior_section_tag)
            )
        )
        self.hinge_i_length = float(self.hinge_i_length)
        self.hinge_j_length = float(self.hinge_j_length)
        self.truss_area = float(self.truss_area)
        self.truss_material_tag = (
            None
            if self.truss_material_tag is None
            else (
                _strict_int(
                    self.truss_material_tag,
                    "Truss material tag",
                )
                if self.element_type in TRUSS_ELEMENT_TYPES
                else int(self.truss_material_tag)
            )
        )
        self.truss_do_rayleigh = _strict_bool(
            self.truss_do_rayleigh,
            "Truss Rayleigh flag",
        )
        self.shell_corotational = _strict_bool(
            self.shell_corotational,
            "Shell corotational flag",
        )
        self.shell_no_eas = _strict_bool(
            self.shell_no_eas,
            "Shell no-EAS flag",
        )
        self.shell_drilling_nl = _strict_bool(
            self.shell_drilling_nl,
            "Shell nonlinear drilling flag",
        )
        if self.shell_drilling_stab is not None:
            self.shell_drilling_stab = float(self.shell_drilling_stab)
            if (
                not math.isfinite(self.shell_drilling_stab)
                or self.shell_drilling_stab < 0.0
            ):
                raise ValueError(
                    "Shell drilling stabilization must be a finite "
                    "non-negative value."
                )
        if self.shell_local_x is not None:
            values = tuple(float(value) for value in self.shell_local_x)
            if len(values) != 3 or any(
                not math.isfinite(value) for value in values
            ):
                raise ValueError(
                    "Shell local X vector needs three finite values."
                )
            if sum(value * value for value in values) <= 1.0e-24:
                raise ValueError(
                    "Shell local X vector cannot be zero."
                )
            self.shell_local_x = values
        if self.is_solid:
            tail = (self.k, self.l, self.m, self.n, self.p, self.q)
            if any(value is None for value in tail):
                raise ValueError(
                    f"{self.element_type} requires eight node tags."
                )
            self.k = _strict_int(self.k, "Element K-node tag")
            self.l = _strict_int(self.l, "Element L-node tag")
            self.m = _strict_int(self.m, "Element M-node tag")
            self.n = _strict_int(self.n, "Element N-node tag")
            self.p = _strict_int(self.p, "Element P-node tag")
            self.q = _strict_int(self.q, "Element Q-node tag")
            if len(set(self.node_tags())) != 8:
                raise ValueError(
                    f"{self.element_type} requires eight distinct node tags."
                )
        elif self.is_quad or self.is_embedded:
            if self.k is None or self.l is None:
                raise ValueError(
                    f"{self.element_type} requires four node tags."
                )
            self.k = _strict_int(self.k, "Element K-node tag")
            self.l = _strict_int(self.l, "Element L-node tag")
            if len(set(self.node_tags())) != 4:
                raise ValueError(
                    f"{self.element_type} requires four distinct node tags."
                )
            self.m = None
            self.n = None
            self.p = None
            self.q = None
        else:
            self.k = None
            self.l = None
            self.m = None
            self.n = None
            self.p = None
            self.q = None

        if not self.is_shell:
            self.shell_corotational = False
            self.shell_local_x = None
            self.shell_no_eas = False
            self.shell_drilling_stab = None
            self.shell_drilling_nl = False
        if self.is_shell and self.element_type != "ASDShellQ4":
            self.shell_corotational = False
            self.shell_local_x = None
            self.shell_no_eas = False
            self.shell_drilling_stab = None
            self.shell_drilling_nl = False

        self.mefi_widths = tuple(float(value) for value in self.mefi_widths)
        self.mefi_section_tags = tuple(
            _strict_int(value, "MEFI section tag")
            for value in self.mefi_section_tags
        )
        if self.element_type == "MEFI":
            if not self.mefi_widths:
                raise ValueError("MEFI requires at least one macro-fiber width.")
            if len(self.mefi_widths) != len(self.mefi_section_tags):
                raise ValueError(
                    "MEFI requires one section tag per macro-fiber width."
                )
            if any(
                not math.isfinite(value) or value <= 0.0
                for value in self.mefi_widths
            ):
                raise ValueError(
                    "MEFI macro-fiber widths must be finite and positive."
                )
            if any(tag <= 0 for tag in self.mefi_section_tags):
                raise ValueError("MEFI section tags must be positive.")
        else:
            self.mefi_widths = ()
            self.mefi_section_tags = ()

        self.embedded_constrain_rotation = _strict_bool(
            self.embedded_constrain_rotation,
            "Embedded-node rotation flag",
        )
        if self.embedded_penalty is not None:
            self.embedded_penalty = float(self.embedded_penalty)
            if (
                not math.isfinite(self.embedded_penalty)
                or self.embedded_penalty <= 0.0
            ):
                raise ValueError(
                    "Embedded-node penalty stiffness must be finite and positive."
                )
        if not self.is_embedded:
            self.embedded_penalty = None
            self.embedded_constrain_rotation = False

        self.continuum_type = str(self.continuum_type)
        self.continuum_thickness = float(self.continuum_thickness)
        self.continuum_pressure = float(self.continuum_pressure)
        self.continuum_density = float(self.continuum_density)
        self.continuum_body_force = tuple(
            float(value) for value in self.continuum_body_force
        )
        if self.is_continuum_quad:
            if self.continuum_type not in {"PlaneStress", "PlaneStrain"}:
                raise ValueError(
                    "2D continuum type must be PlaneStress or PlaneStrain."
                )
            if (
                not math.isfinite(self.continuum_thickness)
                or self.continuum_thickness <= 0.0
            ):
                raise ValueError(
                    "2D continuum thickness must be finite and positive."
                )
            if self.continuum_material_tag is None:
                raise ValueError(
                    f"{self.element_type} requires an nDMaterial tag."
                )
            self.continuum_material_tag = _strict_int(
                self.continuum_material_tag,
                "2D continuum nDMaterial tag",
            )
            if self.continuum_material_tag <= 0:
                raise ValueError(
                    "2D continuum nDMaterial tag must be positive."
                )
            if len(self.continuum_body_force) != 2 or any(
                not math.isfinite(value)
                for value in self.continuum_body_force
            ):
                raise ValueError(
                    "2D continuum body force needs two finite values."
                )
            if (
                not math.isfinite(self.continuum_pressure)
                or not math.isfinite(self.continuum_density)
                or self.continuum_density < 0.0
            ):
                raise ValueError(
                    "2D continuum pressure/density values are invalid."
                )
            if (
                self.element_type == "bbarQuad"
                and self.continuum_type != "PlaneStrain"
            ):
                raise ValueError(
                    "bbarQuad supports PlaneStrain material behavior only."
                )
            if self.element_type in {"SSPquad", "bbarQuad", "enhancedQuad"}:
                self.continuum_pressure = 0.0
                self.continuum_density = 0.0
            if self.element_type in {"bbarQuad", "enhancedQuad"}:
                self.continuum_body_force = (0.0, 0.0)
        else:
            self.continuum_thickness = 1.0
            self.continuum_material_tag = None
            self.continuum_type = "PlaneStrain"
            self.continuum_pressure = 0.0
            self.continuum_density = 0.0
            self.continuum_body_force = (0.0, 0.0)

        self.solid_body_force = tuple(
            float(value) for value in self.solid_body_force
        )
        if self.is_solid:
            if self.solid_material_tag is None:
                raise ValueError(
                    f"{self.element_type} requires an nDMaterial tag."
                )
            self.solid_material_tag = _strict_int(
                self.solid_material_tag,
                "3D solid nDMaterial tag",
            )
            if self.solid_material_tag <= 0:
                raise ValueError(
                    "3D solid nDMaterial tag must be positive."
                )
            if len(self.solid_body_force) != 3 or any(
                not math.isfinite(value)
                for value in self.solid_body_force
            ):
                raise ValueError(
                    "3D solid body force needs three finite values."
                )
        else:
            self.solid_material_tag = None
            self.solid_body_force = (0.0, 0.0, 0.0)

        self.wall_center_ratio = float(self.wall_center_ratio)
        self.wall_density = float(self.wall_density)
        self.wall_thicknesses = tuple(
            float(value) for value in self.wall_thicknesses
        )
        self.wall_widths = tuple(
            float(value) for value in self.wall_widths
        )
        self.wall_rhos = tuple(float(value) for value in self.wall_rhos)
        self.wall_concrete_tags = tuple(
            _strict_int(value, "MVLEM concrete material tag")
            for value in self.wall_concrete_tags
        )
        self.wall_steel_tags = tuple(
            _strict_int(value, "MVLEM steel material tag")
            for value in self.wall_steel_tags
        )
        self.wall_nd_material_tags = tuple(
            _strict_int(value, "SFI_MVLEM nDMaterial tag")
            for value in self.wall_nd_material_tags
        )
        self.wall_thick_mod = float(self.wall_thick_mod)
        self.wall_poisson = float(self.wall_poisson)
        if self.is_wall_macro:
            fiber_count = len(self.wall_widths)
            if fiber_count < 2:
                raise ValueError(
                    f"{self.element_type} requires at least two macro-fibers."
                )
            if len(self.wall_thicknesses) != fiber_count:
                raise ValueError(
                    f"{self.element_type} requires one thickness per "
                    "macro-fiber."
                )
            if any(
                not math.isfinite(value) or value <= 0.0
                for value in (*self.wall_widths, *self.wall_thicknesses)
            ):
                raise ValueError(
                    "Wall macro-fiber widths/thicknesses must be finite "
                    "and positive."
                )
            if (
                not math.isfinite(self.wall_center_ratio)
                or not 0.0 <= self.wall_center_ratio <= 1.0
            ):
                raise ValueError(
                    "Wall center-of-rotation ratio c must satisfy 0 <= c <= 1."
                )
            if (
                not math.isfinite(self.wall_density)
                or self.wall_density < 0.0
            ):
                raise ValueError(
                    "Wall macro-element density must be finite and "
                    "non-negative."
                )

            if self.element_type == "SFI_MVLEM":
                if len(self.wall_nd_material_tags) != fiber_count:
                    raise ValueError(
                        "SFI_MVLEM requires one FSAM nDMaterial tag per "
                        "macro-fiber."
                    )
                if any(tag <= 0 for tag in self.wall_nd_material_tags):
                    raise ValueError(
                        "SFI_MVLEM nDMaterial tags must be positive."
                    )
                self.wall_rhos = ()
                self.wall_concrete_tags = ()
                self.wall_steel_tags = ()
                self.wall_shear_tag = None
                self.wall_density = 0.0
            else:
                if (
                    len(self.wall_rhos) != fiber_count
                    or len(self.wall_concrete_tags) != fiber_count
                    or len(self.wall_steel_tags) != fiber_count
                ):
                    raise ValueError(
                        f"{self.element_type} requires rho, concrete, and "
                        "steel values for every macro-fiber."
                    )
                if any(
                    not math.isfinite(value) or not 0.0 <= value <= 1.0
                    for value in self.wall_rhos
                ):
                    raise ValueError(
                        "MVLEM reinforcement ratios must satisfy 0 <= rho <= 1."
                    )
                if any(
                    tag <= 0
                    for tag in (
                        *self.wall_concrete_tags,
                        *self.wall_steel_tags,
                    )
                ):
                    raise ValueError(
                        "MVLEM concrete/steel material tags must be positive."
                    )
                if self.wall_shear_tag is None:
                    raise ValueError(
                        f"{self.element_type} requires a shear material tag."
                    )
                self.wall_shear_tag = _strict_int(
                    self.wall_shear_tag,
                    "MVLEM shear material tag",
                )
                if self.wall_shear_tag <= 0:
                    raise ValueError(
                        "MVLEM shear material tag must be positive."
                    )
                self.wall_nd_material_tags = ()

            if self.element_type == "MVLEM_3D":
                if (
                    not math.isfinite(self.wall_thick_mod)
                    or self.wall_thick_mod <= 0.0
                ):
                    raise ValueError(
                        "MVLEM_3D thickness modifier must be positive."
                    )
                if not -1.0 < self.wall_poisson < 0.5:
                    raise ValueError(
                        "MVLEM_3D Poisson ratio must satisfy -1 < nu < 0.5."
                    )
            else:
                self.wall_thick_mod = 0.63
                self.wall_poisson = 0.25
        else:
            self.wall_center_ratio = 0.4
            self.wall_density = 0.0
            self.wall_thicknesses = ()
            self.wall_widths = ()
            self.wall_rhos = ()
            self.wall_concrete_tags = ()
            self.wall_steel_tags = ()
            self.wall_shear_tag = None
            self.wall_nd_material_tags = ()
            self.wall_thick_mod = 0.63
            self.wall_poisson = 0.25

        self.beam_center_ratio = float(self.beam_center_ratio)
        if self.element_type == "dispBeamColumnInt":
            if (
                not math.isfinite(self.beam_center_ratio)
                or not 0.0 <= self.beam_center_ratio <= 1.0
            ):
                raise ValueError(
                    "dispBeamColumnInt center-of-rotation ratio cRot "
                    "must satisfy 0 <= cRot <= 1."
                )
            if self.integration_points < 1:
                raise ValueError(
                    "dispBeamColumnInt needs at least one integration point."
                )
            self.consistent_mass = False
        else:
            self.beam_center_ratio = 0.4

        self.special_parameters = _normalize_special_element_parameters(
            self.element_type,
            self.special_parameters,
        )

        uses_section_reference = self.element_type not in (
            TRUSS_ELEMENT_TYPES
            | EMBEDDED_ELEMENT_TYPES
            | CONTINUUM_QUAD_ELEMENT_TYPES
            | SOLID_ELEMENT_TYPES
            | WALL_MACRO_ELEMENT_TYPES
            | SPECIAL_TWO_NODE_ELEMENT_TYPES
            | {"MEFI"}
        )
        uses_frame_reference = self.element_type in FRAME_ELEMENT_TYPES
        self.section_tag = (
            None
            if self.section_tag is None
            else (
                _strict_int(self.section_tag, "Element section tag")
                if uses_section_reference
                else int(self.section_tag)
            )
        )
        self.transf_tag = (
            None
            if self.transf_tag is None
            else (
                _strict_int(
                    self.transf_tag,
                    "Element transformation tag",
                )
                if uses_frame_reference
                else int(self.transf_tag)
            )
        )
        if (
            self.is_quad
            or self.is_embedded
            or self.is_solid
            or self.is_wall_macro
            or self.element_type in SPECIAL_TWO_NODE_ELEMENT_TYPES
        ):
            self.transf_tag = None
        if self.element_type in SPECIAL_TWO_NODE_ELEMENT_TYPES:
            self.section_tag = None

        if self.element_type in BEAM_INTEGRATION_ELEMENT_TYPES and self.integration_type not in {
            "Lobatto",
            "Legendre",
            "Radau",
            "HingeRadau",
            "HingeRadauTwo",
            "HingeMidpoint",
            "HingeEndpoint",
            "ConcentratedPlasticity",
        }:
            raise ValueError(
                f"Unsupported beam integration type: {self.integration_type}"
            )
        beam_hinge_types = {
            "HingeRadau",
            "HingeRadauTwo",
            "HingeMidpoint",
            "HingeEndpoint",
        }
        if (
            self.element_type in BEAM_INTEGRATION_ELEMENT_TYPES
            and self.integration_type in {"Lobatto", "Legendre", "Radau"}
        ):
            if self.integration_points < 2:
                raise ValueError("Beam integration needs at least 2 points.")
        elif (
            self.element_type in BEAM_INTEGRATION_ELEMENT_TYPES
            and self.integration_type in beam_hinge_types
        ):
            if (
                self.hinge_i_section_tag is None
                or self.hinge_j_section_tag is None
                or self.interior_section_tag is None
            ):
                raise ValueError(
                    f"{self.integration_type} requires I-end, J-end, and interior sections."
                )
            if self.hinge_i_length < 0.0 or self.hinge_j_length < 0.0:
                raise ValueError("Plastic hinge lengths cannot be negative.")
        elif (
            self.element_type in BEAM_INTEGRATION_ELEMENT_TYPES
            and self.integration_type == "ConcentratedPlasticity"
        ):
            if (
                self.hinge_i_section_tag is None
                or self.hinge_j_section_tag is None
                or self.interior_section_tag is None
            ):
                raise ValueError(
                    "ConcentratedPlasticity requires I-end, J-end, and interior sections."
                )
        numeric_values = (
            self.force_tolerance,
            self.mass_per_length,
            self.hinge_i_length,
            self.hinge_j_length,
            self.truss_area,
        )
        if any(not math.isfinite(value) for value in numeric_values):
            raise ValueError("Element numeric values must be finite.")
        if self.force_max_iter < 1:
            raise ValueError("Force-based element max iterations must be >= 1.")
        if self.force_tolerance <= 0.0:
            raise ValueError("Force-based element tolerance must be positive.")
        if self.mass_per_length < 0.0:
            raise ValueError("Element mass per length cannot be negative.")
        if self.truss_area < 0.0:
            raise ValueError("Truss area cannot be negative.")
        if (
            self.truss_material_tag is not None
            and self.truss_material_tag <= 0
        ):
            raise ValueError("Truss material tag must be positive.")


@dataclass
class StructuralModel:
    name: str = "Untitled"
    ndm: int = 3
    ndf: int = 6
    nodes: Dict[int, Node] = field(default_factory=dict)
    elements: Dict[int, Element] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip() or "Untitled"
        self.ndm = _strict_int(self.ndm, "Model ndm")
        self.ndf = _strict_int(self.ndf, "Model ndf")
        if self.ndm not in {1, 2, 3}:
            raise ValueError("Model ndm must be 1, 2, or 3.")
        if self.ndf < 1 or self.ndf > 6:
            raise ValueError("Model ndf must be between 1 and 6.")

    def clear(self) -> None:
        self.nodes.clear()
        self.elements.clear()

    def add_node(self, tag: int, x: float, y: float, z: float = 0.0) -> Node:
        tag = _strict_int(tag, "Node tag")
        if tag < 0:
            raise ValueError("Node tag must be a non-negative integer.")
        if tag in self.nodes:
            raise ValueError(f"Node tag {tag} already exists")
        xyz = (float(x), float(y), float(z))
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("Node coordinates must be finite.")
        node = Node(
            tag,
            xyz,
            fixity=(0,) * self.ndf,
            mass=(0.0,) * self.ndf,
        )
        self.nodes[tag] = node
        return node

    def set_coordinates(
        self,
        tag: int,
        x: float,
        y: float,
        z: float = 0.0,
    ) -> None:
        tag = _strict_int(tag, "Node tag")
        node = self.nodes[tag]
        xyz = (float(x), float(y), float(z))
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("Node coordinates must be finite.")
        node.xyz = xyz

    def add_element(
        self,
        tag: int,
        i: int,
        j: int,
        element_type: str = "elasticBeamColumn",
        section_tag: int | None = None,
        transf_tag: int | None = None,
        group: str = "frame",
        integration_type: str = "Lobatto",
        integration_points: int = 5,
        force_max_iter: int = 10,
        force_tolerance: float = 1.0e-12,
        mass_per_length: float = 0.0,
        consistent_mass: bool = False,
        hinge_i_section_tag: int | None = None,
        hinge_j_section_tag: int | None = None,
        interior_section_tag: int | None = None,
        hinge_i_length: float = 0.0,
        hinge_j_length: float = 0.0,
        truss_area: float = 0.0,
        truss_material_tag: int | None = None,
        truss_do_rayleigh: bool = False,
        k: int | None = None,
        l: int | None = None,
        shell_corotational: bool = False,
        shell_local_x: tuple[float, float, float] | None = None,
        shell_no_eas: bool = False,
        shell_drilling_stab: float | None = None,
        shell_drilling_nl: bool = False,
        mefi_widths: tuple[float, ...] | list[float] = (),
        mefi_section_tags: tuple[int, ...] | list[int] = (),
        embedded_penalty: float | None = None,
        embedded_constrain_rotation: bool = False,
        continuum_thickness: float = 1.0,
        continuum_material_tag: int | None = None,
        continuum_type: str = "PlaneStrain",
        continuum_pressure: float = 0.0,
        continuum_density: float = 0.0,
        continuum_body_force: tuple[float, float] | list[float] = (0.0, 0.0),
        m: int | None = None,
        n: int | None = None,
        p: int | None = None,
        q: int | None = None,
        solid_material_tag: int | None = None,
        solid_body_force: tuple[float, float, float] | list[float] = (
            0.0, 0.0, 0.0
        ),
        wall_center_ratio: float = 0.4,
        wall_density: float = 0.0,
        wall_thicknesses: tuple[float, ...] | list[float] = (),
        wall_widths: tuple[float, ...] | list[float] = (),
        wall_rhos: tuple[float, ...] | list[float] = (),
        wall_concrete_tags: tuple[int, ...] | list[int] = (),
        wall_steel_tags: tuple[int, ...] | list[int] = (),
        wall_shear_tag: int | None = None,
        wall_nd_material_tags: tuple[int, ...] | list[int] = (),
        wall_thick_mod: float = 0.63,
        wall_poisson: float = 0.25,
        beam_center_ratio: float = 0.4,
        special_parameters: dict[str, object] | None = None,
    ) -> Element:
        tag = _strict_int(tag, "Element tag")
        i = _strict_int(i, "Element I-node tag")
        j = _strict_int(j, "Element J-node tag")
        element_type = str(element_type)
        if tag <= 0:
            raise ValueError("Element tag must be a positive integer.")
        if tag in self.elements:
            raise ValueError(f"Element tag {tag} already exists")
        if element_type not in SUPPORTED_ELEMENT_TYPES:
            raise ValueError(f"Unsupported element type: {element_type}")
        is_shell = element_type in SHELL_ELEMENT_TYPES
        is_quad = element_type in QUAD_ELEMENT_TYPES
        is_embedded = element_type in EMBEDDED_ELEMENT_TYPES
        is_solid = element_type in SOLID_ELEMENT_TYPES
        raw_nodes = [i, j]
        if is_solid:
            tail = (k, l, m, n, p, q)
            if any(value is None for value in tail):
                raise ValueError(
                    f"{element_type} element {tag} requires eight nodes."
                )
            k = _strict_int(k, "Element K-node tag")
            l = _strict_int(l, "Element L-node tag")
            m = _strict_int(m, "Element M-node tag")
            n = _strict_int(n, "Element N-node tag")
            p = _strict_int(p, "Element P-node tag")
            q = _strict_int(q, "Element Q-node tag")
            raw_nodes.extend([k, l, m, n, p, q])
        elif is_quad or is_embedded:
            if k is None or l is None:
                raise ValueError(
                    f"{element_type} element {tag} requires four nodes."
                )
            k = _strict_int(k, "Element K-node tag")
            l = _strict_int(l, "Element L-node tag")
            raw_nodes.extend([k, l])
        if len(set(raw_nodes)) != len(raw_nodes):
            if is_solid:
                raise ValueError(
                    f"{element_type} element {tag} requires eight distinct "
                    "node tags."
                )
            if is_quad or is_embedded:
                raise ValueError(
                    f"{element_type} element {tag} requires four distinct "
                    "node tags."
                )
            raise ValueError(
                f"Element {tag} must connect two different node tags."
            )
        missing = [node_tag for node_tag in raw_nodes if node_tag not in self.nodes]
        if missing:
            raise ValueError(
                f"Element {tag} references missing node tag(s): "
                + ", ".join(map(str, missing))
            )
        if is_shell and (self.ndm, self.ndf) != (3, 6):
            raise ValueError(
                f"{element_type} requires a 3D/6DOF model; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if is_solid and (self.ndm, self.ndf) != (3, 3):
            raise ValueError(
                f"{element_type} requires ndm=3/ndf=3; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if (
            element_type == "CatenaryCable"
            and (int(self.ndm), int(self.ndf)) != (3, 3)
        ):
            raise ValueError(
                "CatenaryCable requires ndm=3/ndf=3; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if (
            element_type == "elastomericBearingPlasticity"
            and (int(self.ndm), int(self.ndf)) not in {(2, 3), (3, 6)}
        ):
            raise ValueError(
                "elastomericBearingPlasticity requires ndm=2/ndf=3 "
                "or ndm=3/ndf=6; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        normalized_special = _normalize_special_element_parameters(
            element_type,
            special_parameters or {},
        )
        if element_type == "elastomericBearingPlasticity":
            if int(self.ndm) == 3:
                if (
                    normalized_special.get("t_mat_tag") is None
                    or normalized_special.get("my_mat_tag") is None
                ):
                    raise ValueError(
                        "3D elastomericBearingPlasticity requires "
                        "t_mat_tag and my_mat_tag."
                    )
            elif (
                normalized_special.get("t_mat_tag") is not None
                or normalized_special.get("my_mat_tag") is not None
            ):
                raise ValueError(
                    "2D elastomericBearingPlasticity does not use "
                    "t_mat_tag or my_mat_tag."
                )
        if (
            element_type == "dispBeamColumnInt"
            and (self.ndm, self.ndf) != (2, 3)
        ):
            raise ValueError(
                "dispBeamColumnInt requires ndm=2/ndf=3; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if (
            element_type in WALL_MACRO_2D_ELEMENT_TYPES
            and (self.ndm, self.ndf) != (2, 3)
        ):
            raise ValueError(
                f"{element_type} requires ndm=2/ndf=3; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if (
            element_type in WALL_MACRO_3D_ELEMENT_TYPES
            and (self.ndm, self.ndf) != (3, 6)
        ):
            raise ValueError(
                f"{element_type} requires ndm=3/ndf=6; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if is_embedded and (
            int(self.ndm) != 2 or int(self.ndf) not in {2, 3}
        ):
            raise ValueError(
                "ASDEmbeddedNodeElement infrastructure currently supports "
                "2D models with ndf=2 or ndf=3."
            )
        if (
            element_type in CONTINUUM_QUAD_ELEMENT_TYPES
            and (self.ndm, self.ndf) != (2, 2)
        ):
            raise ValueError(
                f"{element_type} requires ndm=2/ndf=2; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if is_solid:
            points = [
                self.nodes[node_tag].xyz
                for node_tag in (i, j, k, l, m, n, p, q)
            ]
            natural = (
                (-1.0, -1.0, -1.0),
                (1.0, -1.0, -1.0),
                (1.0, 1.0, -1.0),
                (-1.0, 1.0, -1.0),
                (-1.0, -1.0, 1.0),
                (1.0, -1.0, 1.0),
                (1.0, 1.0, 1.0),
                (-1.0, 1.0, 1.0),
            )
            jacobian = [[0.0] * 3 for _ in range(3)]
            for point, signs in zip(points, natural):
                for row in range(3):
                    for col in range(3):
                        jacobian[row][col] += (
                            float(point[row]) * signs[col] / 8.0
                        )
            det_j = (
                jacobian[0][0] * (
                    jacobian[1][1] * jacobian[2][2]
                    - jacobian[1][2] * jacobian[2][1]
                )
                - jacobian[0][1] * (
                    jacobian[1][0] * jacobian[2][2]
                    - jacobian[1][2] * jacobian[2][0]
                )
                + jacobian[0][2] * (
                    jacobian[1][0] * jacobian[2][1]
                    - jacobian[1][1] * jacobian[2][0]
                )
            )
            spans = [
                max(float(point[axis]) for point in points)
                - min(float(point[axis]) for point in points)
                for axis in range(3)
            ]
            scale = max(max(spans), 1.0)
            if det_j <= scale ** 3 * 1.0e-12:
                raise ValueError(
                    f"{element_type} requires a non-degenerate, positively "
                    "oriented eight-node brick ordering."
                )

        if element_type in CONTINUUM_QUAD_ELEMENT_TYPES:
            points = [
                self.nodes[node_tag].xyz
                for node_tag in (i, j, k, l)
            ]
            cross_values = []
            for index in range(4):
                a = points[index]
                b = points[(index + 1) % 4]
                c = points[(index + 2) % 4]
                cross_values.append(
                    (b[0] - a[0]) * (c[1] - b[1])
                    - (b[1] - a[1]) * (c[0] - b[0])
                )
            scale = max(
                max(
                    abs(float(point[axis]))
                    for point in points
                )
                for axis in (0, 1)
            )
            tol = max(1.0, scale * scale) * 1.0e-12
            if any(value <= tol for value in cross_values):
                raise ValueError(
                    f"{element_type} requires four convex nodes ordered "
                    "counter-clockwise in the XY plane."
                )

        if element_type == "MEFI" and (self.ndm, self.ndf) not in {
            (2, 3), (3, 6),
        }:
            raise ValueError(
                "MEFI requires ndm=2/ndf=3 or ndm=3/ndf=6; got "
                f"ndm={self.ndm}, ndf={self.ndf}."
            )
        if element_type == "MEFI":
            widths = tuple(float(value) for value in mefi_widths)
            if widths:
                ni = self.nodes[i].xyz
                nj = self.nodes[j].xyz
                edge_width = math.sqrt(sum(
                    (float(nj[index]) - float(ni[index])) ** 2
                    for index in range(3)
                ))
                if edge_width > 0.0 and abs(sum(widths) - edge_width) > max(
                    1.0e-9, 1.0e-6 * edge_width
                ):
                    raise ValueError(
                        "MEFI macro-fiber widths must sum to the element "
                        f"width ({edge_width:g}); got {sum(widths):g}."
                    )
        ele = Element(
            tag,
            i,
            j,
            element_type,
            section_tag,
            transf_tag,
            group,
            integration_type,
            integration_points,
            force_max_iter,
            force_tolerance,
            mass_per_length,
            consistent_mass,
            hinge_i_section_tag,
            hinge_j_section_tag,
            interior_section_tag,
            hinge_i_length,
            hinge_j_length,
            truss_area,
            truss_material_tag,
            truss_do_rayleigh,
            k,
            l,
            shell_corotational,
            shell_local_x,
            shell_no_eas,
            shell_drilling_stab,
            shell_drilling_nl,
            tuple(mefi_widths),
            tuple(mefi_section_tags),
            embedded_penalty=embedded_penalty,
            embedded_constrain_rotation=embedded_constrain_rotation,
            continuum_thickness=continuum_thickness,
            continuum_material_tag=continuum_material_tag,
            continuum_type=continuum_type,
            continuum_pressure=continuum_pressure,
            continuum_density=continuum_density,
            continuum_body_force=tuple(continuum_body_force),
            m=m,
            n=n,
            p=p,
            q=q,
            solid_material_tag=solid_material_tag,
            solid_body_force=tuple(solid_body_force),
            wall_center_ratio=wall_center_ratio,
            wall_density=wall_density,
            wall_thicknesses=tuple(wall_thicknesses),
            wall_widths=tuple(wall_widths),
            wall_rhos=tuple(wall_rhos),
            wall_concrete_tags=tuple(wall_concrete_tags),
            wall_steel_tags=tuple(wall_steel_tags),
            wall_shear_tag=wall_shear_tag,
            wall_nd_material_tags=tuple(wall_nd_material_tags),
            wall_thick_mod=wall_thick_mod,
            wall_poisson=wall_poisson,
            beam_center_ratio=beam_center_ratio,
            special_parameters=normalized_special,
        )
        self.elements[tag] = ele
        return ele

    def set_fixity(self, tag: int, values: Iterable[int]) -> None:
        tag = _strict_int(tag, "Node tag")
        node = self.nodes[tag]
        vals = tuple(
            _strict_int(value, "Fixity value")
            for value in values
        )
        if len(vals) != self.ndf:
            raise ValueError(f"Expected {self.ndf} fixity values, got {len(vals)}")
        if any(value not in {0, 1} for value in vals):
            raise ValueError("Fixity values must be 0 or 1.")
        node.fixity = vals

    def set_fixity_many(
        self,
        node_tags: Iterable[int],
        values: Iterable[int],
    ) -> set[int]:
        vals = tuple(
            _strict_int(value, "Fixity value")
            for value in values
        )
        if len(vals) != self.ndf:
            raise ValueError(
                f"Expected {self.ndf} fixity values, got {len(vals)}"
            )
        if any(value not in {0, 1} for value in vals):
            raise ValueError("Fixity values must be 0 or 1.")
        updated: set[int] = set()
        for tag in node_tags:
            normalized_tag = _strict_int(tag, "Node tag")
            node = self.nodes.get(normalized_tag)
            if node is None:
                continue
            node.fixity = vals
            updated.add(node.tag)
        return updated

    def clear_fixity_many(self, node_tags: Iterable[int]) -> set[int]:
        return self.set_fixity_many(node_tags, (0,) * self.ndf)

    def set_mass(self, tag: int, values: Iterable[float]) -> None:
        tag = _strict_int(tag, "Node tag")
        node = self.nodes[tag]
        vals = tuple(float(v) for v in values)
        if len(vals) != self.ndf:
            raise ValueError(
                f"Expected {self.ndf} mass values, got {len(vals)}"
            )
        if any(not math.isfinite(value) for value in vals):
            raise ValueError("Nodal mass values must be finite.")
        if any(value < 0.0 for value in vals):
            raise ValueError("Nodal mass values cannot be negative.")
        node.mass = vals

    def set_mass_many(
        self,
        node_tags: Iterable[int],
        values: Iterable[float],
    ) -> set[int]:
        vals = tuple(float(v) for v in values)
        if len(vals) != self.ndf:
            raise ValueError(
                f"Expected {self.ndf} mass values, got {len(vals)}"
            )
        if any(not math.isfinite(value) for value in vals):
            raise ValueError("Nodal mass values must be finite.")
        if any(value < 0.0 for value in vals):
            raise ValueError("Nodal mass values cannot be negative.")
        updated: set[int] = set()
        for tag in node_tags:
            normalized_tag = _strict_int(tag, "Node tag")
            node = self.nodes.get(normalized_tag)
            if node is None:
                continue
            node.mass = vals
            updated.add(node.tag)
        return updated

    def clear_mass_many(self, node_tags: Iterable[int]) -> set[int]:
        return self.set_mass_many(node_tags, (0.0,) * self.ndf)

    def remove_element(self, tag: int) -> None:
        tag = _strict_int(tag, "Element tag")
        self.elements.pop(tag, None)

    def remove_node(self, tag: int, *, cascade: bool = False) -> None:
        tag = _strict_int(tag, "Node tag")
        if tag not in self.nodes:
            return
        connected = [
            element_tag
            for element_tag, element in self.elements.items()
            if tag in element.node_tags()
        ]
        if connected and not cascade:
            raise ValueError(
                f"Node {tag} is connected to elements {connected}; use cascade=True"
            )
        for element_tag in connected:
            self.elements.pop(element_tag, None)
        self.nodes.pop(tag, None)

    def delete_entities(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
        cascade_nodes: bool = True,
    ) -> None:
        for element_tag in set(element_tags):
            self.remove_element(element_tag)
        for node_tag in set(node_tags):
            self.remove_node(node_tag, cascade=cascade_nodes)

    def assign_section(
        self,
        element_tags: Iterable[int],
        section_tag: int | None,
    ) -> set[int]:
        assigned: set[int] = set()
        value = (
            None
            if section_tag is None
            else _strict_int(section_tag, "Section tag")
        )
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            element = self.elements.get(normalized_tag)
            if (
                element is None
                or element.element_type in TRUSS_ELEMENT_TYPES
                or element.element_type in SPECIAL_TWO_NODE_ELEMENT_TYPES
            ):
                continue
            element.section_tag = value
            assigned.add(element.tag)
        return assigned

    def assign_truss_material(
        self,
        element_tags: Iterable[int],
        material_tag: int | None,
    ) -> set[int]:
        """Assign a uniaxial material only to Truss/CorotTruss elements."""
        assigned: set[int] = set()
        value = (
            None
            if material_tag is None
            else _strict_int(material_tag, "Material tag")
        )
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            element = self.elements.get(normalized_tag)
            if element is None or element.element_type not in TRUSS_ELEMENT_TYPES:
                continue
            element.truss_material_tag = value
            assigned.add(element.tag)
        return assigned

    def assign_element_formulation(
        self,
        element_tags: Iterable[int],
        *,
        element_type: str,
        integration_type: str = "Lobatto",
        integration_points: int = 5,
        force_max_iter: int = 10,
        force_tolerance: float = 1.0e-12,
        mass_per_length: float = 0.0,
        consistent_mass: bool = False,
        hinge_i_section_tag: int | None = None,
        hinge_j_section_tag: int | None = None,
        interior_section_tag: int | None = None,
        hinge_i_length: float = 0.0,
        hinge_j_length: float = 0.0,
        beam_center_ratio: float = 0.4,
    ) -> set[int]:
        updated: set[int] = set()
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            element = self.elements.get(normalized_tag)
            if element is None or element.element_type not in FRAME_ELEMENT_TYPES:
                continue
            candidate = Element(
                tag=element.tag,
                i=element.i,
                j=element.j,
                element_type=element_type,
                section_tag=element.section_tag,
                transf_tag=element.transf_tag,
                group=element.group,
                integration_type=integration_type,
                integration_points=integration_points,
                force_max_iter=force_max_iter,
                force_tolerance=force_tolerance,
                mass_per_length=mass_per_length,
                consistent_mass=consistent_mass,
                hinge_i_section_tag=hinge_i_section_tag,
                hinge_j_section_tag=hinge_j_section_tag,
                interior_section_tag=interior_section_tag,
                hinge_i_length=hinge_i_length,
                hinge_j_length=hinge_j_length,
                beam_center_ratio=beam_center_ratio,
                truss_area=element.truss_area,
                truss_material_tag=element.truss_material_tag,
                truss_do_rayleigh=element.truss_do_rayleigh,
            )
            self.elements[element.tag] = candidate
            updated.add(element.tag)
        return updated

    def assign_transformation(
        self,
        element_tags: Iterable[int],
        transf_tag: int | None,
    ) -> set[int]:
        assigned: set[int] = set()
        value = (
            None
            if transf_tag is None
            else _strict_int(transf_tag, "Transformation tag")
        )
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            element = self.elements.get(normalized_tag)
            if element is None or element.element_type not in FRAME_ELEMENT_TYPES:
                continue
            element.transf_tag = value
            assigned.add(element.tag)
        return assigned

    def next_node_tag(self) -> int:
        return max(self.nodes, default=0) + 1

    def next_element_tag(self) -> int:
        return max(self.elements, default=0) + 1

    def reverse_shell_orientation(
        self,
        tags: Iterable[int],
    ) -> list[int]:
        """Reverse selected shell node ordering while preserving options."""
        reversed_tags: list[int] = []
        for raw_tag in tags:
            tag = _strict_int(raw_tag, "Shell element tag")
            element = self.elements.get(tag)
            if element is None:
                raise ValueError(f"Element {tag} does not exist.")
            if element.element_type not in SHELL_ELEMENT_TYPES:
                raise ValueError(
                    f"Element {tag} is not a Shell element."
                )
            if element.l is None:
                raise ValueError(
                    f"Shell element {tag} is missing its fourth node."
                )
            old_j = element.j
            element.j = element.l
            element.l = old_j
            element.__post_init__()
            reversed_tags.append(tag)
        return reversed_tags

    def entity_node_tags(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
    ) -> set[int]:
        tags: set[int] = set()
        for tag in node_tags:
            normalized_tag = _strict_int(tag, "Node tag")
            if normalized_tag in self.nodes:
                tags.add(normalized_tag)
        for element_tag in element_tags:
            normalized_tag = _strict_int(element_tag, "Element tag")
            element = self.elements.get(normalized_tag)
            if element is not None:
                tags.update(element.node_tags())
        return tags

    def translate_entities(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
    ) -> set[int]:
        offsets = (float(dx), float(dy), float(dz))
        if any(not math.isfinite(value) for value in offsets):
            raise ValueError("Translation offsets must be finite.")
        tags = self.entity_node_tags(
            node_tags=node_tags,
            element_tags=element_tags,
        )
        for tag in tags:
            node = self.nodes[tag]
            x, y, z = node.xyz
            self.set_coordinates(
                tag,
                x + offsets[0],
                y + offsets[1],
                z + offsets[2],
            )
        return tags

    def rotate_entities(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
        axis: str = "z",
        angle_deg: float = 0.0,
        pivot: Vec3 = (0.0, 0.0, 0.0),
    ) -> set[int]:
        import math

        axis = axis.lower()
        if axis not in {"x", "y", "z"}:
            raise ValueError("Rotation axis must be x, y, or z.")

        tags = self.entity_node_tags(
            node_tags=node_tags,
            element_tags=element_tags,
        )
        px, py, pz = map(float, pivot)
        raw_angle = float(angle_deg)
        if (
            not math.isfinite(raw_angle)
            or any(not math.isfinite(value) for value in (px, py, pz))
        ):
            raise ValueError("Rotation angle and pivot must be finite.")
        angle = math.radians(raw_angle)
        c = math.cos(angle)
        s = math.sin(angle)

        for tag in tags:
            node = self.nodes[tag]
            x, y, z = node.xyz
            x -= px
            y -= py
            z -= pz

            if axis == "x":
                y, z = y * c - z * s, y * s + z * c
            elif axis == "y":
                x, z = x * c + z * s, -x * s + z * c
            else:
                x, y = x * c - y * s, x * s + y * c

            self.set_coordinates(tag, x + px, y + py, z + pz)
        return tags

    def mirror_entities(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
        normal_axis: str = "x",
        coordinate: float = 0.0,
    ) -> set[int]:
        axis = normal_axis.lower()
        if axis not in {"x", "y", "z"}:
            raise ValueError("Mirror normal axis must be x, y, or z.")

        tags = self.entity_node_tags(
            node_tags=node_tags,
            element_tags=element_tags,
        )
        coordinate = float(coordinate)
        if not math.isfinite(coordinate):
            raise ValueError("Mirror coordinate must be finite.")
        for tag in tags:
            node = self.nodes[tag]
            xyz = list(node.xyz)
            index = {"x": 0, "y": 1, "z": 2}[axis]
            xyz[index] = 2.0 * coordinate - xyz[index]
            self.set_coordinates(tag, xyz[0], xyz[1], xyz[2])
        return tags

    def copy_entities(
        self,
        *,
        node_tags: Iterable[int] = (),
        element_tags: Iterable[int] = (),
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        copies: int = 1,
        reserved_element_tags: Iterable[int] = (),
    ) -> tuple[set[int], set[int]]:
        copies = _strict_int(copies, "Copy count")
        if copies < 1:
            raise ValueError("copies must be at least 1")

        selected_elements: set[int] = set()
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            if normalized_tag in self.elements:
                selected_elements.add(normalized_tag)
        source_nodes = self.entity_node_tags(
            node_tags=node_tags,
            element_tags=selected_elements,
        )
        if not source_nodes and not selected_elements:
            return set(), set()

        base_nodes = {
            tag: (
                self.nodes[tag].xyz,
                self.nodes[tag].fixity,
                self.nodes[tag].mass,
            )
            for tag in source_nodes
        }
        base_elements = {
            tag: self.elements[tag]
            for tag in selected_elements
        }

        next_node = self.next_node_tag()
        reserved_elements = {
            _strict_int(tag, "Reserved element tag")
            for tag in reserved_element_tags
        } | set(self.elements)
        next_element = self.next_element_tag()
        created_nodes: set[int] = set()
        created_elements: set[int] = set()

        for copy_index in range(1, copies + 1):
            node_map: dict[int, int] = {}
            for source_tag in sorted(source_nodes):
                xyz, fixity, mass = base_nodes[source_tag]
                new_tag = next_node
                next_node += 1
                node = self.add_node(
                    new_tag,
                    xyz[0] + float(dx) * copy_index,
                    xyz[1] + float(dy) * copy_index,
                    xyz[2] + float(dz) * copy_index,
                )
                node.fixity = tuple(fixity)
                node.mass = tuple(mass)
                node_map[source_tag] = new_tag
                created_nodes.add(new_tag)

            for source_tag in sorted(selected_elements):
                source = base_elements[source_tag]
                while next_element in reserved_elements:
                    next_element += 1
                new_tag = next_element
                reserved_elements.add(new_tag)
                next_element += 1
                self.add_element(
                    new_tag,
                    node_map[source.i],
                    node_map[source.j],
                    source.element_type,
                    source.section_tag,
                    source.transf_tag,
                    source.group,
                    source.integration_type,
                    source.integration_points,
                    source.force_max_iter,
                    source.force_tolerance,
                    source.mass_per_length,
                    source.consistent_mass,
                    source.hinge_i_section_tag,
                    source.hinge_j_section_tag,
                    source.interior_section_tag,
                    source.hinge_i_length,
                    source.hinge_j_length,
                    source.truss_area,
                    source.truss_material_tag,
                    source.truss_do_rayleigh,
                    k=(
                        node_map[source.k]
                        if source.k is not None
                        else None
                    ),
                    l=(
                        node_map[source.l]
                        if source.l is not None
                        else None
                    ),
                    shell_corotational=source.shell_corotational,
                    shell_local_x=source.shell_local_x,
                    shell_no_eas=source.shell_no_eas,
                    shell_drilling_stab=source.shell_drilling_stab,
                    shell_drilling_nl=source.shell_drilling_nl,
                    mefi_widths=source.mefi_widths,
                    mefi_section_tags=source.mefi_section_tags,
                    embedded_penalty=source.embedded_penalty,
                    embedded_constrain_rotation=(
                        source.embedded_constrain_rotation
                    ),
                    continuum_thickness=source.continuum_thickness,
                    continuum_material_tag=source.continuum_material_tag,
                    continuum_type=source.continuum_type,
                    continuum_pressure=source.continuum_pressure,
                    continuum_density=source.continuum_density,
                    continuum_body_force=source.continuum_body_force,
                    m=(
                        node_map[source.m]
                        if source.m is not None
                        else None
                    ),
                    n=(
                        node_map[source.n]
                        if source.n is not None
                        else None
                    ),
                    p=(
                        node_map[source.p]
                        if source.p is not None
                        else None
                    ),
                    q=(
                        node_map[source.q]
                        if source.q is not None
                        else None
                    ),
                    solid_material_tag=source.solid_material_tag,
                    solid_body_force=source.solid_body_force,
                    wall_center_ratio=source.wall_center_ratio,
                    wall_density=source.wall_density,
                    wall_thicknesses=source.wall_thicknesses,
                    wall_widths=source.wall_widths,
                    wall_rhos=source.wall_rhos,
                    wall_concrete_tags=source.wall_concrete_tags,
                    wall_steel_tags=source.wall_steel_tags,
                    wall_shear_tag=source.wall_shear_tag,
                    wall_nd_material_tags=source.wall_nd_material_tags,
                    wall_thick_mod=source.wall_thick_mod,
                    wall_poisson=source.wall_poisson,
                    beam_center_ratio=source.beam_center_ratio,
                    special_parameters=dict(source.special_parameters),
                )
                created_elements.add(new_tag)

        return created_nodes, created_elements

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ndm": self.ndm,
            "ndf": self.ndf,
            "nodes": [
                {
                    "tag": node.tag,
                    "xyz": list(node.xyz),
                    "fixity": list(node.fixity),
                    "mass": list(node.mass),
                }
                for node in sorted(self.nodes.values(), key=lambda item: item.tag)
            ],
            "elements": [
                {
                    "tag": element.tag,
                    "i": element.i,
                    "j": element.j,
                    "element_type": element.element_type,
                    "section_tag": element.section_tag,
                    "transf_tag": element.transf_tag,
                    "group": element.group,
                    "integration_type": element.integration_type,
                    "integration_points": element.integration_points,
                    "force_max_iter": element.force_max_iter,
                    "force_tolerance": element.force_tolerance,
                    "mass_per_length": element.mass_per_length,
                    "consistent_mass": element.consistent_mass,
                    "hinge_i_section_tag": element.hinge_i_section_tag,
                    "hinge_j_section_tag": element.hinge_j_section_tag,
                    "interior_section_tag": element.interior_section_tag,
                    "hinge_i_length": element.hinge_i_length,
                    "hinge_j_length": element.hinge_j_length,
                    "truss_area": element.truss_area,
                    "truss_material_tag": element.truss_material_tag,
                    "truss_do_rayleigh": element.truss_do_rayleigh,
                    "k": element.k,
                    "l": element.l,
                    "shell_corotational": element.shell_corotational,
                    "shell_local_x": (
                        list(element.shell_local_x)
                        if element.shell_local_x is not None
                        else None
                    ),
                    "shell_no_eas": element.shell_no_eas,
                    "shell_drilling_stab": element.shell_drilling_stab,
                    "shell_drilling_nl": element.shell_drilling_nl,
                    "mefi_widths": list(element.mefi_widths),
                    "mefi_section_tags": list(element.mefi_section_tags),
                    "embedded_penalty": element.embedded_penalty,
                    "embedded_constrain_rotation": (
                        element.embedded_constrain_rotation
                    ),
                    "continuum_thickness": element.continuum_thickness,
                    "continuum_material_tag": element.continuum_material_tag,
                    "continuum_type": element.continuum_type,
                    "continuum_pressure": element.continuum_pressure,
                    "continuum_density": element.continuum_density,
                    "continuum_body_force": list(element.continuum_body_force),
                    "m": element.m,
                    "n": element.n,
                    "p": element.p,
                    "q": element.q,
                    "solid_material_tag": element.solid_material_tag,
                    "solid_body_force": list(element.solid_body_force),
                    "wall_center_ratio": element.wall_center_ratio,
                    "wall_density": element.wall_density,
                    "wall_thicknesses": list(element.wall_thicknesses),
                    "wall_widths": list(element.wall_widths),
                    "wall_rhos": list(element.wall_rhos),
                    "wall_concrete_tags": list(element.wall_concrete_tags),
                    "wall_steel_tags": list(element.wall_steel_tags),
                    "wall_shear_tag": element.wall_shear_tag,
                    "wall_nd_material_tags": list(
                        element.wall_nd_material_tags
                    ),
                    "wall_thick_mod": element.wall_thick_mod,
                    "wall_poisson": element.wall_poisson,
                    "beam_center_ratio": element.beam_center_ratio,
                    "special_parameters": dict(element.special_parameters),
                }
                for element in sorted(self.elements.values(), key=lambda item: item.tag)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructuralModel":
        model = cls(
            name=str(data.get("name", "Untitled")),
            ndm=data.get("ndm", 3),
            ndf=data.get("ndf", 6),
        )

        raw_nodes = data.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise ValueError("Model nodes must be a list.")
        for index, item in enumerate(raw_nodes):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Model node item {index} must be an object."
                )
            xyz = item.get("xyz", (0.0, 0.0, 0.0))
            if not isinstance(xyz, (list, tuple)) or len(xyz) < 2:
                raise ValueError(
                    f"Node {item.get('tag', '?')} coordinates need X and Y."
                )
            node = model.add_node(
                item["tag"],
                float(xyz[0]),
                float(xyz[1]),
                float(xyz[2]) if len(xyz) > 2 else 0.0,
            )
            fixity = tuple(
                _strict_int(value, "Fixity value")
                for value in item.get("fixity", (0,) * model.ndf)
            )
            if len(fixity) != model.ndf:
                raise ValueError(
                    f"Node {node.tag} has {len(fixity)} fixities; expected {model.ndf}."
                )
            if any(value not in {0, 1} for value in fixity):
                raise ValueError(
                    f"Node {node.tag} fixity values must be 0 or 1."
                )
            node.fixity = fixity
            mass = tuple(
                float(value)
                for value in item.get("mass", (0.0,) * model.ndf)
            )
            if len(mass) != model.ndf:
                raise ValueError(
                    f"Node {node.tag} has {len(mass)} mass values; "
                    f"expected {model.ndf}."
                )
            if any(not math.isfinite(value) for value in mass):
                raise ValueError(
                    f"Node {node.tag} mass values must be finite."
                )
            if any(value < 0.0 for value in mass):
                raise ValueError(
                    f"Node {node.tag} mass values cannot be negative."
                )
            node.mass = mass

        raw_elements = data.get("elements", [])
        if not isinstance(raw_elements, list):
            raise ValueError("Model elements must be a list.")
        for index, item in enumerate(raw_elements):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Model element item {index} must be an object."
                )
            model.add_element(
                item["tag"],
                item["i"],
                item["j"],
                str(item.get("element_type", "elasticBeamColumn")),
                item.get("section_tag"),
                item.get("transf_tag"),
                str(item.get("group", "frame")),
                str(item.get("integration_type", "Lobatto")),
                item.get("integration_points", 5),
                item.get("force_max_iter", 10),
                float(item.get("force_tolerance", 1.0e-12)),
                float(item.get("mass_per_length", 0.0)),
                item.get("consistent_mass", False),
                item.get("hinge_i_section_tag"),
                item.get("hinge_j_section_tag"),
                item.get("interior_section_tag"),
                float(item.get("hinge_i_length", 0.0)),
                float(item.get("hinge_j_length", 0.0)),
                float(item.get("truss_area", 0.0)),
                item.get("truss_material_tag"),
                item.get("truss_do_rayleigh", False),
                item.get("k"),
                item.get("l"),
                item.get("shell_corotational", False),
                (
                    tuple(item["shell_local_x"])
                    if item.get("shell_local_x") is not None
                    else None
                ),
                item.get("shell_no_eas", False),
                item.get("shell_drilling_stab"),
                item.get("shell_drilling_nl", False),
                tuple(item.get("mefi_widths", ())),
                tuple(item.get("mefi_section_tags", ())),
                item.get("embedded_penalty"),
                item.get("embedded_constrain_rotation", False),
                float(item.get("continuum_thickness", 1.0)),
                item.get("continuum_material_tag"),
                str(item.get("continuum_type", "PlaneStrain")),
                float(item.get("continuum_pressure", 0.0)),
                float(item.get("continuum_density", 0.0)),
                tuple(item.get("continuum_body_force", (0.0, 0.0))),
                m=item.get("m"),
                n=item.get("n"),
                p=item.get("p"),
                q=item.get("q"),
                solid_material_tag=item.get("solid_material_tag"),
                solid_body_force=tuple(
                    item.get("solid_body_force", (0.0, 0.0, 0.0))
                ),
                wall_center_ratio=float(
                    item.get("wall_center_ratio", 0.4)
                ),
                wall_density=float(item.get("wall_density", 0.0)),
                wall_thicknesses=tuple(
                    item.get("wall_thicknesses", ())
                ),
                wall_widths=tuple(item.get("wall_widths", ())),
                wall_rhos=tuple(item.get("wall_rhos", ())),
                wall_concrete_tags=tuple(
                    item.get("wall_concrete_tags", ())
                ),
                wall_steel_tags=tuple(
                    item.get("wall_steel_tags", ())
                ),
                wall_shear_tag=item.get("wall_shear_tag"),
                wall_nd_material_tags=tuple(
                    item.get("wall_nd_material_tags", ())
                ),
                wall_thick_mod=float(
                    item.get("wall_thick_mod", 0.63)
                ),
                wall_poisson=float(
                    item.get("wall_poisson", 0.25)
                ),
                beam_center_ratio=float(
                    item.get("beam_center_ratio", 0.4)
                ),
                special_parameters=dict(
                    item.get("special_parameters", {})
                ),
            )

        return model

    def bounds(self) -> tuple[Vec3, Vec3]:
        if not self.nodes:
            return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        xs, ys, zs = zip(*(n.xyz for n in self.nodes.values()))
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def shell_surface_geometry(
    model: StructuralModel,
    element: Element,
) -> tuple[Vec3, Vec3, float]:
    """Return shell centroid, ordered surface normal, and triangulated area."""
    if element.element_type not in SHELL_ELEMENT_TYPES:
        raise ValueError(
            f"Element {element.tag} is not a Shell element."
        )
    node_tags = element.node_tags()
    if len(node_tags) != 4:
        raise ValueError(
            f"Shell element {element.tag} requires four nodes."
        )
    missing = [
        int(tag)
        for tag in node_tags
        if int(tag) not in model.nodes
    ]
    if missing:
        raise ValueError(
            f"Shell element {element.tag} references missing node tag(s): "
            + ", ".join(map(str, missing))
        )

    points = [
        tuple(float(value) for value in model.nodes[int(tag)].xyz)
        for tag in node_tags
    ]
    center: Vec3 = tuple(
        sum(point[axis] for point in points) / 4.0
        for axis in range(3)
    )

    newell = [0.0, 0.0, 0.0]
    for index, current in enumerate(points):
        following = points[(index + 1) % 4]
        newell[0] += (
            (current[1] - following[1])
            * (current[2] + following[2])
        )
        newell[1] += (
            (current[2] - following[2])
            * (current[0] + following[0])
        )
        newell[2] += (
            (current[0] - following[0])
            * (current[1] + following[1])
        )
    normal_norm = math.sqrt(sum(value * value for value in newell))
    if normal_norm <= 1.0e-12:
        raise ValueError(
            f"Shell element {element.tag} has zero or near-zero area."
        )
    normal: Vec3 = tuple(
        value / normal_norm for value in newell
    )

    def triangle_area(a: Vec3, b: Vec3, d: Vec3) -> float:
        ab = tuple(b[i] - a[i] for i in range(3))
        ad = tuple(d[i] - a[i] for i in range(3))
        cross = (
            ab[1] * ad[2] - ab[2] * ad[1],
            ab[2] * ad[0] - ab[0] * ad[2],
            ab[0] * ad[1] - ab[1] * ad[0],
        )
        return 0.5 * math.sqrt(sum(value * value for value in cross))

    area = (
        triangle_area(points[0], points[1], points[2])
        + triangle_area(points[0], points[2], points[3])
    )
    if area <= 1.0e-12:
        raise ValueError(
            f"Shell element {element.tag} has zero or near-zero area."
        )
    return center, normal, area
