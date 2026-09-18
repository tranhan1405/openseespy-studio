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

    def remove_element(self, tag: int) -> None:
        self.elements.pop(tag, None)

    def remove_node(self, tag: int, *, cascade: bool = False) -> None:
        if tag not in self.nodes:
            return
        connected = [
            element_tag
            for element_tag, element in self.elements.items()
            if element.i == tag or element.j == tag
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

    def bounds(self) -> tuple[Vec3, Vec3]:
        if not self.nodes:
            return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        xs, ys, zs = zip(*(n.xyz for n in self.nodes.values()))
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
