from __future__ import annotations

from PySide6.QtCore import QObject, Signal


def parse_tag_expression(text: str) -> set[int]:
    tags: set[int] = set()
    cleaned = text.replace(";", ",")
    for raw_part in cleaned.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            bits = [item.strip() for item in part.split("-", 1)]
            if len(bits) != 2 or not bits[0] or not bits[1]:
                raise ValueError(f"Invalid ID range: {part!r}")
            start = int(bits[0])
            end = int(bits[1])
            if start <= 0 or end <= 0:
                raise ValueError("IDs must be positive integers.")
            if end < start:
                start, end = end, start
            tags.update(range(start, end + 1))
        else:
            value = int(part)
            if value <= 0:
                raise ValueError("IDs must be positive integers.")
            tags.add(value)
    return tags


class SelectionManager(QObject):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes: set[int] = set()
        self.elements: set[int] = set()
        self.filter = "all"

    def snapshot(self) -> dict[str, frozenset[int]]:
        return {
            "nodes": frozenset(self.nodes),
            "elements": frozenset(self.elements),
        }

    def set_filter(self, value: str) -> None:
        value = value.lower()
        if value not in {"all", "node", "element"}:
            raise ValueError(f"Unknown selection filter: {value}")
        self.filter = value

    def clear(self) -> None:
        if not self.nodes and not self.elements:
            return
        self.nodes.clear()
        self.elements.clear()
        self.changed.emit(self.snapshot())

    def set_selection(
        self,
        *,
        nodes: set[int] | None = None,
        elements: set[int] | None = None,
    ) -> None:
        new_nodes = set() if nodes is None else set(nodes)
        new_elements = set() if elements is None else set(elements)
        if new_nodes == self.nodes and new_elements == self.elements:
            return
        self.nodes = new_nodes
        self.elements = new_elements
        self.changed.emit(self.snapshot())

    def select_many(
        self,
        *,
        nodes: set[int] | None = None,
        elements: set[int] | None = None,
        mode: str = "replace",
    ) -> None:
        new_nodes = set(nodes or ())
        new_elements = set(elements or ())

        if self.filter == "node":
            new_elements.clear()
        elif self.filter == "element":
            new_nodes.clear()

        if mode == "replace":
            self.nodes = new_nodes
            self.elements = new_elements
        elif mode == "add":
            self.nodes.update(new_nodes)
            self.elements.update(new_elements)
        elif mode == "toggle":
            self.nodes.symmetric_difference_update(new_nodes)
            self.elements.symmetric_difference_update(new_elements)
        else:
            raise ValueError(f"Unknown selection mode: {mode}")

        self.changed.emit(self.snapshot())

    def select(self, kind: str, tag: int, mode: str = "replace") -> None:
        if kind == "node" and self.filter == "element":
            return
        if kind == "element" and self.filter == "node":
            return
        if kind not in {"node", "element"}:
            return

        target = self.nodes if kind == "node" else self.elements
        other = self.elements if kind == "node" else self.nodes

        if mode == "replace":
            self.nodes.clear()
            self.elements.clear()
            target = self.nodes if kind == "node" else self.elements
            target.add(tag)
        elif mode == "add":
            target.add(tag)
        elif mode == "toggle":
            if tag in target:
                target.remove(tag)
            else:
                target.add(tag)
        else:
            raise ValueError(f"Unknown selection mode: {mode}")

        self.changed.emit(self.snapshot())
