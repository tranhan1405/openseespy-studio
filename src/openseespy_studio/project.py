from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import StructuralModel


PROJECT_FORMAT = "openseespy-studio"
PROJECT_FORMAT_VERSION = 2

MATERIAL_PARAMETER_ORDER: dict[str, tuple[str, ...]] = {
    "Elastic": ("E",),
    "Steel02": ("Fy", "E0", "b", "R0", "cR1", "cR2"),
    "Concrete02": ("fpc", "epsc0", "fpcu", "epsU", "lambda", "ft", "Ets"),
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "material_type": self.material_type,
            "parameters": dict(self.parameters),
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
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    transformations: dict[str, dict[str, Any]] = field(default_factory=dict)
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
            "sections": self.sections,
            "transformations": self.transformations,
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
            sections=dict(data.get("sections", {})),
            transformations=dict(data.get("transformations", {})),
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
