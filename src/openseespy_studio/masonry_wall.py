from __future__ import annotations

from dataclasses import dataclass, field
import math

from .project import (
    MaterialData,
    ProjectDatabase,
    SectionData,
    SelectionSetData,
    TransformationData,
)


@dataclass(slots=True)
class MasonryWallSpec:
    """Unified masonry/infill wall definition used by the FEWIZ wizard."""

    name: str = "Masonry Wall"
    formulation: str = "EquivalentStrut"
    width: float = 3.0
    height: float = 2.8
    thickness: float = 0.15
    origin_x: float = 0.0
    origin_y: float = 0.0
    replace_geometry: bool = True

    # Equivalent-strut formulation.
    strut_width_ratio: float = 0.10
    crossed_struts: bool = True

    # MasonPan12 formulation.
    masonpan_w_tot: float = 0.25
    masonpan_w1: float = 0.50

    # Surrounding frame required for a stable standalone infill model.
    boundary_E: float = 30.0e9
    boundary_width: float = 0.30
    boundary_depth: float = 0.30

    # OpenSees Masonry material strategy.
    material_strategy: str = "CreateCustom"
    existing_material_tag: int | None = None
    existing_lateral_material_tag: int | None = None

    # OpenSees Masonry material (Crisafulli/Torrisi).
    Fm: float = -5.0e6
    Ft: float = 0.20e6
    Um: float = -0.002
    Uult: float = -0.010
    Ucl: float = 0.0005
    Emo: float = 2.5e9
    L: float = 1.0
    a1: float = 1.0
    a2: float = 0.20
    D1: float = -0.002
    D2: float = -0.006
    Ach: float = 0.40
    Are: float = 0.30
    Ba: float = 1.75
    Bch: float = 0.20
    Gun: float = 2.0
    Gplu: float = 0.60
    Gplr: float = 1.30
    Exp1: float = 1.75
    Exp2: float = 1.25
    IENV: int = 0


@dataclass(slots=True)
class MasonryWallBuildResult:
    node_tags: list[int] = field(default_factory=list)
    element_tags: list[int] = field(default_factory=list)
    material_tags: list[int] = field(default_factory=list)
    boundary_element_tags: list[int] = field(default_factory=list)
    boundary_section_tag: int | None = None
    boundary_transformation_tag: int | None = None
    selection_set_names: tuple[str, ...] = ()


def validate_masonry_wall_spec(spec: MasonryWallSpec) -> None:
    formulation = str(spec.formulation).strip()
    if formulation not in {"EquivalentStrut", "MasonPan12"}:
        raise ValueError(
            "Masonry Wall formulation must be EquivalentStrut or MasonPan12."
        )
    if min(float(spec.width), float(spec.height), float(spec.thickness)) <= 0.0:
        raise ValueError("Masonry wall width, height and thickness must be positive.")
    if not math.isfinite(float(spec.origin_x)) or not math.isfinite(float(spec.origin_y)):
        raise ValueError("Masonry wall origin must be finite.")
    if (
        not math.isfinite(float(spec.boundary_E))
        or float(spec.boundary_E) <= 0.0
    ):
        raise ValueError("Masonry boundary-frame elastic modulus must be positive.")
    if (
        not math.isfinite(float(spec.boundary_width))
        or not math.isfinite(float(spec.boundary_depth))
        or min(float(spec.boundary_width), float(spec.boundary_depth)) <= 0.0
    ):
        raise ValueError(
            "Masonry boundary-frame width and depth must be positive."
        )

    if str(spec.material_strategy) not in {"CreateCustom", "UseExisting"}:
        raise ValueError(
            "Masonry material strategy must be CreateCustom or UseExisting."
        )

    if float(spec.Fm) >= 0.0:
        raise ValueError("Masonry compression strength Fm must be negative.")
    if float(spec.Ft) <= 0.0:
        raise ValueError("Masonry tension strength Ft must be positive.")
    if float(spec.Um) >= 0.0 or float(spec.Uult) >= 0.0:
        raise ValueError("Masonry Um and Uult compression strains must be negative.")
    if float(spec.Ucl) <= 0.0:
        raise ValueError("Masonry crack-closing strain Ucl must be positive.")
    if float(spec.Emo) <= 0.0:
        raise ValueError("Masonry initial modulus Emo must be positive.")
    if float(spec.L) <= 0.0:
        raise ValueError("Masonry material L must be positive.")
    if float(spec.a1) <= 0.0 or float(spec.a2) < 0.0:
        raise ValueError(
            "Masonry Area1/Area2 factors must be non-negative, "
            "with Area1 > 0."
        )
    if str(spec.material_strategy) == "CreateCustom":
        if not math.isclose(float(spec.L), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError(
                "FEWIZ masonry wall custom materials use normalized L=1. "
                "Use an existing calibrated Masonry material for other L."
            )
        if not math.isclose(float(spec.a1), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError(
                "FEWIZ masonry wall custom materials use normalized Area1=1."
            )
        if float(spec.a2) > 1.0:
            raise ValueError(
                "Normalized Masonry Area2 must satisfy 0 <= Area2 <= 1."
            )
    if float(spec.D1) >= 0.0 or float(spec.D2) >= 0.0:
        raise ValueError("Masonry degradation strains D1/D2 must be negative.")
    if int(spec.IENV) not in {0, 1}:
        raise ValueError("Masonry IENV must be 0 (Sargin) or 1 (parabolic).")
    if not 0.0 < float(spec.strut_width_ratio) <= 1.0:
        raise ValueError("Equivalent-strut width ratio must satisfy 0 < ratio <= 1.")
    if float(spec.masonpan_w_tot) <= 0.0:
        raise ValueError("MasonPan12 total strut-width ratio w_tot must be positive.")
    if not 0.0 < float(spec.masonpan_w1) <= 1.0:
        raise ValueError("MasonPan12 central-width ratio must satisfy 0 < w1 <= 1.")


def _next_tags(store: dict[int, object], count: int) -> list[int]:
    candidate = max(store, default=0) + 1
    tags: list[int] = []
    while len(tags) < int(count):
        if candidate not in store:
            tags.append(candidate)
        candidate += 1
    return tags


def _unique_selection_name(project: ProjectDatabase, base: str) -> str:
    if base not in project.selection_sets:
        return base
    index = 2
    while f"{base} {index}" in project.selection_sets:
        index += 1
    return f"{base} {index}"


def _material_parameters(spec: MasonryWallSpec) -> dict[str, float]:
    return {
        "Fm": float(spec.Fm),
        "Ft": float(spec.Ft),
        "Um": float(spec.Um),
        "Uult": float(spec.Uult),
        "Ucl": float(spec.Ucl),
        "Emo": float(spec.Emo),
        "L": float(spec.L),
        "A1": float(spec.a1),
        "A2": float(spec.a2),
        "D1": float(spec.D1),
        "D2": float(spec.D2),
        "Ach": float(spec.Ach),
        "Are": float(spec.Are),
        "Ba": float(spec.Ba),
        "Bch": float(spec.Bch),
        "Gun": float(spec.Gun),
        "Gplu": float(spec.Gplu),
        "Gplr": float(spec.Gplr),
        "Exp1": float(spec.Exp1),
        "Exp2": float(spec.Exp2),
        "IENV": float(int(spec.IENV)),
    }


def _material_source() -> dict[str, object]:
    return {
        "library": "FEWIZ Masonry Wall Wizard",
        "status": "user_defined",
        "model": "Masonry",
        "reference": {
            "type": "OpenSees source code",
            "title": "Masonry.cpp · Crisafulli/Torrisi Masonry material",
            "url": (
                "https://github.com/OpenSees/OpenSees/blob/master/"
                "SRC/material/uniaxial/Masonry.cpp"
            ),
        },
        "note": (
            "Generic starting values only. Calibrate Masonry parameters "
            "against project-specific masonry/infill test data."
        ),
    }


def _require_masonry_material(
    project: ProjectDatabase,
    tag: int | None,
    *,
    role: str,
) -> int:
    if tag is None:
        raise ValueError(f"{role} Masonry material is not selected.")
    material_tag = int(tag)
    material = project.materials.get(material_tag)
    if material is None:
        raise ValueError(f"{role} Masonry material {material_tag} does not exist.")
    if material.material_type != "Masonry":
        raise ValueError(
            f"{role} material {material_tag} must be Masonry, got "
            f"{material.material_type}."
        )
    return material_tag


def _check_append_overlap(
    project: ProjectDatabase,
    points: list[tuple[float, float, float]],
    span: float,
) -> None:
    if not project.model.nodes:
        return
    tolerance2 = (1.0e-9 * max(float(span), 1.0)) ** 2
    existing = [
        tuple(float(value) for value in node.xyz)
        for node in project.model.nodes.values()
    ]
    for point in points:
        if any(
            sum((point[index] - other[index]) ** 2 for index in range(3))
            <= tolerance2
            for other in existing
        ):
            raise ValueError(
                "Append masonry wall geometry overlaps an existing node near "
                f"({point[0]:g}, {point[1]:g})."
            )


def _add_nodes(
    project: ProjectDatabase,
    points: list[tuple[float, float, float]],
) -> list[int]:
    tags: list[int] = []
    next_tag = project.model.next_node_tag()
    for point in points:
        while next_tag in project.model.nodes:
            next_tag += 1
        project.model.add_node(next_tag, *point)
        tags.append(next_tag)
        next_tag += 1
    return tags


def _prepare_project(project: ProjectDatabase, spec: MasonryWallSpec) -> None:
    if spec.replace_geometry:
        project.clear_model_linked_data()
        project.model.clear()
        project.model.ndm = 2
        project.model.ndf = 3
    elif (int(project.model.ndm), int(project.model.ndf)) != (2, 3):
        raise ValueError(
            "Appending a masonry wall requires an ndm=2 / ndf=3 project."
        )


def _add_boundary_frame(
    project: ProjectDatabase,
    spec: MasonryWallSpec,
    node_tags: list[int],
) -> tuple[list[int], int, int]:
    """Add the surrounding frame that makes the infill topology kinematically valid.

    MasonPan12 is a six-strut infill macro-element. Its perimeter nodes are
    intended to interact with surrounding beams and columns; the element does
    not provide rotational stiffness or a self-stable standalone boundary.
    FEWIZ therefore creates an elastic perimeter frame for the standalone
    wizard workflow instead of leaving the infill nodes as mechanisms.
    """
    section_tag = project.next_section_tag()
    width = float(spec.boundary_width)
    depth = float(spec.boundary_depth)
    area = width * depth
    iz = width * depth**3 / 12.0
    project.add_section(
        SectionData(
            section_tag,
            f"{spec.name} · Boundary Frame",
            "Elastic",
            parameters={
                "E": float(spec.boundary_E),
                "A": area,
                "Iz": iz,
            },
        )
    )

    transf_tag = project.next_transformation_tag()
    project.add_transformation(
        TransformationData(
            transf_tag,
            f"{spec.name} · Boundary Frame Linear",
            "Linear",
            orientation_mode="auto",
        )
    )

    frame_tags: list[int] = []
    pairs = [
        (node_tags[index], node_tags[(index + 1) % len(node_tags)])
        for index in range(len(node_tags))
    ]
    next_element = project.next_element_tag()
    for i_node, j_node in pairs:
        while (
            next_element in project.model.elements
            or next_element in project.connections
        ):
            next_element += 1
        project.model.add_element(
            next_element,
            i_node,
            j_node,
            element_type="elasticBeamColumn",
            section_tag=section_tag,
            transf_tag=transf_tag,
            group="masonry-boundary",
        )
        project.validate_element_state(next_element)
        frame_tags.append(next_element)
        next_element += 1

    return frame_tags, section_tag, transf_tag


def _build_equivalent_strut(
    project: ProjectDatabase,
    spec: MasonryWallSpec,
) -> MasonryWallBuildResult:
    x0 = float(spec.origin_x)
    y0 = float(spec.origin_y)
    width = float(spec.width)
    height = float(spec.height)
    points = [
        (x0, y0, 0.0),
        (x0 + width, y0, 0.0),
        (x0 + width, y0 + height, 0.0),
        (x0, y0 + height, 0.0),
    ]
    if not spec.replace_geometry:
        _check_append_overlap(project, points, max(width, height))
    node_tags = _add_nodes(project, points)
    project.model.nodes[node_tags[0]].fixity = (1, 1, 1)
    project.model.nodes[node_tags[1]].fixity = (1, 1, 1)

    if str(spec.material_strategy) == "UseExisting":
        material_tag = _require_masonry_material(
            project,
            spec.existing_material_tag,
            role="Equivalent-strut",
        )
    else:
        material_tag = _next_tags(project.materials, 1)[0]
        project.add_material(
            MaterialData(
                material_tag,
                f"{spec.name} · Masonry Strut",
                "Masonry",
                parameters=_material_parameters(spec),
                source=_material_source(),
            )
        )

    diagonal = math.hypot(width, height)
    area = float(spec.thickness) * float(spec.strut_width_ratio) * diagonal
    pairs = [
        (node_tags[0], node_tags[2]),
    ]
    if bool(spec.crossed_struts):
        pairs.append((node_tags[1], node_tags[3]))

    element_tags: list[int] = []
    next_element = project.next_element_tag()
    for i_node, j_node in pairs:
        while next_element in project.model.elements or next_element in project.connections:
            next_element += 1
        project.model.add_element(
            next_element,
            i_node,
            j_node,
            element_type="corotTruss",
            group="masonry",
            truss_area=area,
            truss_material_tag=material_tag,
        )
        project.validate_element_state(next_element)
        element_tags.append(next_element)
        next_element += 1

    boundary_tags, boundary_section_tag, boundary_transf_tag = (
        _add_boundary_frame(project, spec, node_tags)
    )

    selection_names = (
        _unique_selection_name(project, f"{spec.name} · Base"),
        _unique_selection_name(project, f"{spec.name} · Top"),
        _unique_selection_name(project, f"{spec.name} · Masonry"),
        _unique_selection_name(project, f"{spec.name} · Boundary Frame"),
    )
    project.add_selection_set(
        SelectionSetData(selection_names[0], node_tags={node_tags[0], node_tags[1]})
    )
    project.add_selection_set(
        SelectionSetData(selection_names[1], node_tags={node_tags[2], node_tags[3]})
    )
    project.add_selection_set(
        SelectionSetData(selection_names[2], element_tags=set(element_tags))
    )
    project.add_selection_set(
        SelectionSetData(selection_names[3], element_tags=set(boundary_tags))
    )
    return MasonryWallBuildResult(
        node_tags=node_tags,
        element_tags=element_tags,
        material_tags=[material_tag],
        boundary_element_tags=boundary_tags,
        boundary_section_tag=boundary_section_tag,
        boundary_transformation_tag=boundary_transf_tag,
        selection_set_names=selection_names,
    )


def _masonpan12_points(spec: MasonryWallSpec) -> list[tuple[float, float, float]]:
    x0 = float(spec.origin_x)
    y0 = float(spec.origin_y)
    width = float(spec.width)
    height = float(spec.height)
    # Counter-clockwise perimeter ordering starting at lower-left, following
    # the OpenSees MasonPan12 command definition.
    return [
        (x0, y0, 0.0),
        (x0 + width / 3.0, y0, 0.0),
        (x0 + 2.0 * width / 3.0, y0, 0.0),
        (x0 + width, y0, 0.0),
        (x0 + width, y0 + height / 3.0, 0.0),
        (x0 + width, y0 + 2.0 * height / 3.0, 0.0),
        (x0 + width, y0 + height, 0.0),
        (x0 + 2.0 * width / 3.0, y0 + height, 0.0),
        (x0 + width / 3.0, y0 + height, 0.0),
        (x0, y0 + height, 0.0),
        (x0, y0 + 2.0 * height / 3.0, 0.0),
        (x0, y0 + height / 3.0, 0.0),
    ]


def _build_masonpan12(
    project: ProjectDatabase,
    spec: MasonryWallSpec,
) -> MasonryWallBuildResult:
    points = _masonpan12_points(spec)
    if not spec.replace_geometry:
        _check_append_overlap(
            project,
            points,
            max(float(spec.width), float(spec.height)),
        )
    node_tags = _add_nodes(project, points)
    for tag in node_tags[:4]:
        project.model.nodes[tag].fixity = (1, 1, 1)

    if str(spec.material_strategy) == "UseExisting":
        central_tag = _require_masonry_material(
            project,
            spec.existing_material_tag,
            role="Central-strut",
        )
        lateral_tag = _require_masonry_material(
            project,
            (
                spec.existing_lateral_material_tag
                if spec.existing_lateral_material_tag is not None
                else spec.existing_material_tag
            ),
            role="Lateral-strut",
        )
    else:
        central_tag, lateral_tag = _next_tags(project.materials, 2)
        params = _material_parameters(spec)
        source = _material_source()
        project.add_material(
            MaterialData(
                central_tag,
                f"{spec.name} · Masonry Central Strut",
                "Masonry",
                parameters=params,
                source=source,
            )
        )
        project.add_material(
            MaterialData(
                lateral_tag,
                f"{spec.name} · Masonry Lateral Struts",
                "Masonry",
                parameters=params,
                source=source,
            )
        )

    element_tag = project.next_element_tag()
    while element_tag in project.model.elements or element_tag in project.connections:
        element_tag += 1
    project.model.add_element(
        element_tag,
        node_tags[0],
        node_tags[1],
        element_type="MasonPan12",
        group="masonry",
        special_parameters={
            "mat_1": central_tag,
            "mat_2": lateral_tag,
            "thick": float(spec.thickness),
            "w_tot": float(spec.masonpan_w_tot),
            "w_1": float(spec.masonpan_w1),
        },
        additional_node_tags=tuple(node_tags[2:]),
    )
    project.validate_element_state(element_tag)

    boundary_tags, boundary_section_tag, boundary_transf_tag = (
        _add_boundary_frame(project, spec, node_tags)
    )

    selection_names = (
        _unique_selection_name(project, f"{spec.name} · Base"),
        _unique_selection_name(project, f"{spec.name} · Top"),
        _unique_selection_name(project, f"{spec.name} · Masonry"),
        _unique_selection_name(project, f"{spec.name} · Boundary Frame"),
    )
    project.add_selection_set(
        SelectionSetData(selection_names[0], node_tags=set(node_tags[:4]))
    )
    project.add_selection_set(
        SelectionSetData(selection_names[1], node_tags=set(node_tags[6:10]))
    )
    project.add_selection_set(
        SelectionSetData(selection_names[2], element_tags={element_tag})
    )
    project.add_selection_set(
        SelectionSetData(selection_names[3], element_tags=set(boundary_tags))
    )
    return MasonryWallBuildResult(
        node_tags=node_tags,
        element_tags=[element_tag],
        material_tags=[central_tag, lateral_tag],
        boundary_element_tags=boundary_tags,
        boundary_section_tag=boundary_section_tag,
        boundary_transformation_tag=boundary_transf_tag,
        selection_set_names=selection_names,
    )


def build_masonry_wall(
    project: ProjectDatabase,
    spec: MasonryWallSpec,
) -> MasonryWallBuildResult:
    """Build one standalone 2D masonry wall/infill panel."""

    validate_masonry_wall_spec(spec)
    _prepare_project(project, spec)
    if str(spec.formulation).strip() == "MasonPan12":
        return _build_masonpan12(project, spec)
    return _build_equivalent_strut(project, spec)
