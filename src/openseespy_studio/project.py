from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import StructuralModel


PROJECT_FORMAT = "openseespy-studio"
PROJECT_FORMAT_VERSION = 6

MATERIAL_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "Elastic": ("E",),
    "Steel02": ("Fy", "E0", "b", "R0", "cR1", "cR2"),
    "Concrete02": ("fpc", "epsc0", "fpcu", "epsU", "lambda", "ft", "Ets"),
}

MATERIAL_ENGINEERING_DEFAULTS: dict[str, dict[str, float]] = {
    "Elastic": {"poisson_ratio": 0.3, "density": 0.0},
    "Steel02": {"poisson_ratio": 0.3, "density": 7850.0},
    "Concrete02": {"poisson_ratio": 0.2, "density": 2400.0},
}

MATERIAL_DEFAULTS: dict[str, dict[str, float]] = {
    "Elastic": {
        "E": 2.0e11,
    },
    "Steel02": {
        "Fy": 3.55e8,
        "E0": 2.0e11,
        "b": 0.01,
        "R0": 20.0,
        "cR1": 0.925,
        "cR2": 0.15,
    },
    "Concrete02": {
        "fpc": -30.0e6,
        "epsc0": -0.002,
        "fpcu": -6.0e6,
        "epsU": -0.006,
        "lambda": 0.1,
        "ft": 3.0e6,
        "Ets": 2.0e8,
    },
}


@dataclass
class MaterialData:
    tag: int
    name: str
    material_type: str
    parameters: dict[str, float] = field(default_factory=dict)
    poisson_ratio: float = 0.3
    density: float = 0.0

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
        if self.material_type == "Steel02":
            return float(self.parameters["E0"])
        if self.material_type == "Concrete02":
            epsc0 = float(self.parameters["epsc0"])
            if abs(epsc0) <= 1.0e-16:
                raise ValueError(
                    f"Concrete02 material {self.tag} has zero epsc0."
                )
            return abs(2.0 * float(self.parameters["fpc"]) / epsc0)
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
class SectionData:
    tag: int
    name: str
    section_type: str
    parameters: dict[str, float] = field(default_factory=dict)
    fibers: list[FiberData] = field(default_factory=list)
    material_tag: int | None = None

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
        self.material_tag = (
            None if self.material_tag is None else int(self.material_tag)
        )
        if self.section_type != "Elastic":
            self.material_tag = None

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
            "material_tag": self.material_tag,
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
            material_tag=data.get("material_tag"),
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
    time_series: dict[str, dict[str, Any]] = field(default_factory=dict)
    load_patterns: dict[str, dict[str, Any]] = field(default_factory=dict)
    analyses: dict[str, dict[str, Any]] = field(default_factory=dict)

    units: dict[str, str] = field(
        default_factory=lambda: {
            "length": "m",
            "force": "kN",
            "time": "s",
        }
    )

    def next_material_tag(self) -> int:
        return max(self.materials, default=0) + 1

    def add_material(self, material: MaterialData) -> None:
        if material.tag in self.materials:
            raise ValueError(f"Material tag {material.tag} already exists.")
        self.materials[material.tag] = material

    def update_material(self, original_tag: int, material: MaterialData) -> None:
        original_tag = int(original_tag)
        if original_tag not in self.materials:
            raise ValueError(f"Material tag {original_tag} does not exist.")
        if material.tag != original_tag and material.tag in self.materials:
            raise ValueError(f"Material tag {material.tag} already exists.")
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

        missing = sorted({
            fiber.material_tag
            for fiber in section.fibers
            if fiber.material_tag not in self.materials
        })
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
                or any(
                    fiber.material_tag == material_tag
                    for fiber in section.fibers
                )
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
            "time_series": self.time_series,
            "load_patterns": self.load_patterns,
            "analyses": self.analyses,
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
            time_series=dict(data.get("time_series", {})),
            load_patterns=dict(data.get("load_patterns", {})),
            analyses=dict(data.get("analyses", {})),
            units={
                str(key): str(value)
                for key, value in data.get(
                    "units",
                    {"length": "m", "force": "kN", "time": "s"},
                ).items()
            },
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
