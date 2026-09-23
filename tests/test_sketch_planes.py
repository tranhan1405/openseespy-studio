from __future__ import annotations

import math

import pytest

from openseespy_studio.project import ProjectDatabase, SketchPlaneData


def test_sketch_plane_builds_orthonormal_basis_and_roundtrips_local_coordinates():
    plane = SketchPlaneData(
        tag=1,
        name="Inclined",
        origin=(1.0, 2.0, 3.0),
        u_axis=(2.0, 0.0, 0.0),
        v_axis=(1.0, 2.0, 2.0),
    )

    u = plane.u_axis
    v = plane.v_axis
    n = plane.normal
    assert math.sqrt(sum(value * value for value in u)) == pytest.approx(1.0)
    assert math.sqrt(sum(value * value for value in v)) == pytest.approx(1.0)
    assert math.sqrt(sum(value * value for value in n)) == pytest.approx(1.0)
    assert sum(u[i] * v[i] for i in range(3)) == pytest.approx(0.0)

    world = plane.world_from_uv(4.0, -2.5)
    local = plane.uv_from_world(world)
    assert local == pytest.approx((4.0, -2.5))
    assert plane.signed_distance(world) == pytest.approx(0.0)


def test_project_roundtrip_preserves_custom_sketch_planes():
    project = ProjectDatabase()
    project.add_sketch_plane(
        SketchPlaneData(
            tag=1,
            name="Floor 2",
            origin=(0.0, 0.0, 3.5),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
        )
    )

    restored = ProjectDatabase.from_dict(project.to_dict())

    assert 1 in restored.sketch_planes
    plane = restored.sketch_planes[1]
    assert plane.name == "Floor 2"
    assert plane.origin == pytest.approx((0.0, 0.0, 3.5))
    assert plane.normal == pytest.approx((0.0, 0.0, 1.0))


def test_three_point_plane_rejects_collinear_axes():
    with pytest.raises(ValueError, match="parallel"):
        SketchPlaneData(
            tag=1,
            name="Bad",
            origin=(0.0, 0.0, 0.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(2.0, 0.0, 0.0),
        )
