from __future__ import annotations

from dataclasses import dataclass, field

from .model import SHELL_ELEMENT_TYPES
from .project import ProjectDatabase, SHELL_SECTION_TYPES


@dataclass(slots=True)
class ShellMeshSpec:
    corner_nodes: tuple[int, int, int, int]
    divisions_u: int = 1
    divisions_v: int = 1
    formulation: str = "ASDShellQ4"
    section_tag: int = 0
    corotational: bool = False
    local_x: tuple[float, float, float] | None = None
    no_eas: bool = False
    drilling_stab: float | None = None
    drilling_nl: bool = False
    group: str = "shell"


@dataclass(slots=True)
class ShellMeshBuildResult:
    node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    grid: list[list[int]] = field(default_factory=list)


def _bilinear_point(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
    p4: tuple[float, float, float],
    u: float,
    v: float,
) -> tuple[float, float, float]:
    return tuple(
        (1.0 - u) * (1.0 - v) * p1[index]
        + u * (1.0 - v) * p2[index]
        + u * v * p3[index]
        + (1.0 - u) * v * p4[index]
        for index in range(3)
    )


def build_shell_mesh(
    project: ProjectDatabase,
    spec: ShellMeshSpec,
) -> ShellMeshBuildResult:
    """Mesh a four-corner surface with structured quadrilateral shells."""
    if (int(project.model.ndm), int(project.model.ndf)) != (3, 6):
        raise ValueError(
            "Shell surface meshing requires a 3D/6DOF structural model."
        )

    corners = tuple(int(tag) for tag in spec.corner_nodes)
    if len(corners) != 4 or len(set(corners)) != 4:
        raise ValueError(
            "Shell surface meshing requires four distinct corner nodes."
        )
    missing = [tag for tag in corners if tag not in project.model.nodes]
    if missing:
        raise ValueError(
            "Shell surface corners reference missing node tag(s): "
            + ", ".join(map(str, missing))
        )

    nu = int(spec.divisions_u)
    nv = int(spec.divisions_v)
    if nu < 1 or nv < 1:
        raise ValueError("Shell mesh divisions U and V must be at least 1.")
    if nu > 500 or nv > 500:
        raise ValueError(
            "Shell mesh divisions are limited to 500 per direction."
        )

    formulation = str(spec.formulation)
    if formulation not in SHELL_ELEMENT_TYPES:
        raise ValueError(
            f"Unsupported shell formulation: {formulation}"
        )

    section_tag = int(spec.section_tag)
    section = project.sections.get(section_tag)
    if (
        section is None
        or section.section_type not in SHELL_SECTION_TYPES
    ):
        raise ValueError(
            "Shell mesh requires an existing shell-compatible Section."
        )

    p1 = project.model.nodes[corners[0]].xyz
    p2 = project.model.nodes[corners[1]].xyz
    p3 = project.model.nodes[corners[2]].xyz
    p4 = project.model.nodes[corners[3]].xyz

    corner_lookup = {
        (0, 0): corners[0],
        (nu, 0): corners[1],
        (nu, nv): corners[2],
        (0, nv): corners[3],
    }

    next_node = project.model.next_node_tag()
    grid: list[list[int]] = []
    created_nodes: list[int] = []

    for j in range(nv + 1):
        row: list[int] = []
        v = j / nv
        for i in range(nu + 1):
            if (i, j) in corner_lookup:
                row.append(corner_lookup[(i, j)])
                continue

            u = i / nu
            xyz = _bilinear_point(p1, p2, p3, p4, u, v)
            while next_node in project.model.nodes:
                next_node += 1
            project.model.add_node(next_node, *xyz)
            row.append(next_node)
            created_nodes.append(next_node)
            next_node += 1
        grid.append(row)

    next_element = project.next_element_tag()
    created_elements: list[int] = []
    try:
        for j in range(nv):
            for i in range(nu):
                while (
                    next_element in project.model.elements
                    or next_element in project.connections
                ):
                    next_element += 1
                node_tags = (
                    grid[j][i],
                    grid[j][i + 1],
                    grid[j + 1][i + 1],
                    grid[j + 1][i],
                )
                project.model.add_element(
                    next_element,
                    node_tags[0],
                    node_tags[1],
                    element_type=formulation,
                    section_tag=section_tag,
                    group=str(spec.group or "shell"),
                    k=node_tags[2],
                    l=node_tags[3],
                    shell_corotational=(
                        bool(spec.corotational)
                        if formulation == "ASDShellQ4"
                        else False
                    ),
                    shell_local_x=(
                        spec.local_x
                        if formulation == "ASDShellQ4"
                        else None
                    ),
                    shell_no_eas=(
                        bool(spec.no_eas)
                        if formulation == "ASDShellQ4"
                        else False
                    ),
                    shell_drilling_stab=(
                        spec.drilling_stab
                        if formulation == "ASDShellQ4"
                        else None
                    ),
                    shell_drilling_nl=(
                        bool(spec.drilling_nl)
                        if formulation == "ASDShellQ4"
                        else False
                    ),
                )
                created_elements.append(next_element)
                project.validate_element_state(next_element)
                next_element += 1
    except Exception:
        for tag in created_elements:
            project.model.elements.pop(tag, None)
        for tag in created_nodes:
            project.model.nodes.pop(tag, None)
        raise

    return ShellMeshBuildResult(
        node_tags=created_nodes,
        element_tags=created_elements,
        grid=grid,
    )
