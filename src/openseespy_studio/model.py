from __future__ import annotations

import math

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

Vec3 = Tuple[float, float, float]

FRAME_ELEMENT_TYPES = {
    "elasticBeamColumn",
    "forceBeamColumn",
    "dispBeamColumn",
}
SHELL_ELEMENT_TYPES = {
    "ASDShellQ4",
    "ShellMITC4",
    "ShellDKGQ",
    "ShellNLDKGQ",
}
SUPPORTED_ELEMENT_TYPES = FRAME_ELEMENT_TYPES | SHELL_ELEMENT_TYPES | {
    "truss",
}


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

    @property
    def is_shell(self) -> bool:
        return self.element_type in SHELL_ELEMENT_TYPES

    def node_tags(self) -> tuple[int, ...]:
        if self.is_shell:
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
                if self.element_type == "truss"
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
        if self.is_shell:
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
        else:
            self.k = None
            self.l = None
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

        uses_section_reference = self.element_type != "truss"
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
        if self.is_shell:
            self.transf_tag = None

        if self.element_type in FRAME_ELEMENT_TYPES and self.integration_type not in {
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
            self.element_type in FRAME_ELEMENT_TYPES
            and self.integration_type in {"Lobatto", "Legendre", "Radau"}
        ):
            if self.integration_points < 2:
                raise ValueError("Beam integration needs at least 2 points.")
        elif (
            self.element_type in FRAME_ELEMENT_TYPES
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
            self.element_type in FRAME_ELEMENT_TYPES
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
        raw_nodes = [i, j]
        if is_shell:
            if k is None or l is None:
                raise ValueError(
                    f"{element_type} element {tag} requires four nodes."
                )
            k = _strict_int(k, "Element K-node tag")
            l = _strict_int(l, "Element L-node tag")
            raw_nodes.extend([k, l])
        if len(set(raw_nodes)) != len(raw_nodes):
            if is_shell:
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
            if element is None or element.element_type == "truss":
                continue
            element.section_tag = value
            assigned.add(element.tag)
        return assigned

    def assign_truss_material(
        self,
        element_tags: Iterable[int],
        material_tag: int | None,
    ) -> set[int]:
        """Assign a uniaxial material only to Truss elements."""
        assigned: set[int] = set()
        value = (
            None
            if material_tag is None
            else _strict_int(material_tag, "Material tag")
        )
        for tag in element_tags:
            normalized_tag = _strict_int(tag, "Element tag")
            element = self.elements.get(normalized_tag)
            if element is None or element.element_type != "truss":
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
