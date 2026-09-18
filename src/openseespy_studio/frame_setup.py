from __future__ import annotations

import math

from .generator import FrameGridSpec
from .project import ProjectDatabase, TransformationData


COLUMN_TRANSFORMATION_NAME = "Column_PDelta"
BEAM_TRANSFORMATION_NAME = "Beam_Linear"
COLUMN_VECXZ = (1.0, 0.0, 0.0)
BEAM_VECXZ = (0.0, 0.0, 1.0)


def _same_vector(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
    *,
    tolerance: float = 1.0e-12,
) -> bool:
    return all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=tolerance)
        for a, b in zip(left, right)
    )


def _find_compatible_transformation(
    project: ProjectDatabase,
    transformation_type: str,
    vecxz: tuple[float, float, float],
) -> int | None:
    for tag in sorted(project.transformations):
        transformation = project.transformations[tag]
        if (
            transformation.transformation_type == transformation_type
            and _same_vector(transformation.vecxz, vecxz)
        ):
            return tag
    return None


def _ensure_transformation(
    project: ProjectDatabase,
    *,
    name: str,
    transformation_type: str,
    vecxz: tuple[float, float, float],
) -> tuple[int, bool]:
    existing = _find_compatible_transformation(
        project,
        transformation_type,
        vecxz,
    )
    if existing is not None:
        return existing, False

    tag = project.next_transformation_tag()
    project.add_transformation(
        TransformationData(
            tag=tag,
            name=name,
            transformation_type=transformation_type,
            vecxz=vecxz,
        )
    )
    return tag, True


def prepare_frame_grid(
    project: ProjectDatabase,
    spec: FrameGridSpec,
) -> list[TransformationData]:
    """Resolve safe geometric transformations for an axis-aligned frame grid.

    Explicit user assignments are preserved. A missing column assignment gets
    a PDelta transformation with global X as vecxz, which is perpendicular to
    the grid's vertical (global Z) columns. A missing beam assignment gets a
    Linear transformation with global Z as vecxz, which is perpendicular to
    both global X and global Y grid beams.

    The supplied spec is updated in-place so generate_frame_grid() can assign
    the resolved tags directly to each member.
    """
    created: list[TransformationData] = []

    if spec.column_transf_tag is not None:
        if spec.column_transf_tag not in project.transformations:
            raise ValueError(
                "Column transformation "
                f"{spec.column_transf_tag} does not exist in the project."
            )
    elif spec.create_columns:
        tag, was_created = _ensure_transformation(
            project,
            name=COLUMN_TRANSFORMATION_NAME,
            transformation_type="PDelta",
            vecxz=COLUMN_VECXZ,
        )
        spec.column_transf_tag = tag
        if was_created:
            created.append(project.transformations[tag])

    beams_requested = spec.create_beams_x or spec.create_beams_y
    if spec.beam_transf_tag is not None:
        if spec.beam_transf_tag not in project.transformations:
            raise ValueError(
                "Beam transformation "
                f"{spec.beam_transf_tag} does not exist in the project."
            )
    elif beams_requested:
        tag, was_created = _ensure_transformation(
            project,
            name=BEAM_TRANSFORMATION_NAME,
            transformation_type="Linear",
            vecxz=BEAM_VECXZ,
        )
        spec.beam_transf_tag = tag
        if was_created:
            created.append(project.transformations[tag])

    return created
