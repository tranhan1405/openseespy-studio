from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

Vec3 = Tuple[float, float, float]


@dataclass(slots=True)
class Node:
    tag: int
    xyz: Vec3
    fixity: Tuple[int, ...] = (0, 0, 0, 0, 0, 0)


@dataclass(slots=True)
class Element:
    tag: int
    i: int
    j: int
    element_type: str = "elasticBeamColumn"
    section_tag: int | None = None
    transf_tag: int | None = None
    group: str = "frame"


@dataclass
class StructuralModel:
    name: str = "Untitled"
    ndm: int = 3
    ndf: int = 6
    nodes: Dict[int, Node] = field(default_factory=dict)
    elements: Dict[int, Element] = field(default_factory=dict)

    def clear(self) -> None:
        self.nodes.clear()
        self.elements.clear()

    def add_node(self, tag: int, x: float, y: float, z: float = 0.0) -> Node:
        if tag in self.nodes:
            raise ValueError(f"Node tag {tag} already exists")
        node = Node(tag, (float(x), float(y), float(z)))
        self.nodes[tag] = node
        return node

    def add_element(
        self,
        tag: int,
        i: int,
        j: int,
        element_type: str = "elasticBeamColumn",
        section_tag: int | None = None,
        transf_tag: int | None = None,
        group: str = "frame",
    ) -> Element:
        if tag in self.elements:
            raise ValueError(f"Element tag {tag} already exists")
        if i not in self.nodes or j not in self.nodes:
            raise ValueError(f"Element {tag} references missing nodes {i}, {j}")
        ele = Element(tag, i, j, element_type, section_tag, transf_tag, group)
        self.elements[tag] = ele
        return ele

    def set_fixity(self, tag: int, values: Iterable[int]) -> None:
        node = self.nodes[tag]
        vals = tuple(int(v) for v in values)
        if len(vals) != self.ndf:
            raise ValueError(f"Expected {self.ndf} fixity values, got {len(vals)}")
        node.fixity = vals

    def bounds(self) -> tuple[Vec3, Vec3]:
        if not self.nodes:
            return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        xs, ys, zs = zip(*(n.xyz for n in self.nodes.values()))
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
