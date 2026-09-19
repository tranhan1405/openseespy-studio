from __future__ import annotations

import math

import numpy as np
import pytest

from openseespy_studio.deformed_geometry import (
    build_swept_member_geometry,
    deformed_member_frames,
    geometry_contours,
    infer_fiber_display_geometry,
)
from openseespy_studio.project import (
    FiberComponentData,
    SectionData,
)


def test_rectangle_display_contour_uses_real_dimensions():
    contours = geometry_contours(
        {
            "shape": "Rectangle",
            "dimensions": {"height": 0.6, "width": 0.4},
        }
    )
    assert len(contours) == 1
    contour = contours[0]
    assert np.ptp(contour[:, 0]) == pytest.approx(0.6)
    assert np.ptp(contour[:, 1]) == pytest.approx(0.4)


def test_beam_rotations_create_curved_centerline():
    centerline, _fy, _fz, _m = deformed_member_frames(
        (0.0, 0.0, 0.0),
        (4.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.2),
        ndm=3,
        scale=1.0,
        stations=9,
        smooth=True,
    )
    assert centerline[0] == pytest.approx((0.0, 0.0, 0.0))
    assert centerline[-1] == pytest.approx((4.0, 0.0, 0.0))
    assert abs(float(centerline[4, 1])) > 1.0e-6


def test_rectangle_section_sweeps_along_curved_member():
    section = SectionData(
        tag=1,
        name="R",
        section_type="Elastic",
        display_geometry={
            "shape": "Rectangle",
            "dimensions": {"height": 0.5, "width": 0.3},
        },
    )
    geometry = build_swept_member_geometry(
        section,
        (0.0, 0.0, 0.0),
        (3.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.0, 0.2, 0.0, 0.0, 0.0, 0.15),
        ndm=3,
        scale=2.0,
        stations=7,
        smooth=True,
    )
    assert geometry is not None
    assert geometry.centerline.shape == (7, 3)
    assert geometry.points.shape[0] == 7 * 4
    assert geometry.faces.size == (7 - 1) * 4 * 5
    assert geometry.centerline[-1, 1] == pytest.approx(0.4)


def test_hollow_circle_has_outer_and_inner_skin():
    section = SectionData(
        tag=2,
        name="CHS",
        section_type="Elastic",
        display_geometry={
            "shape": "Hollow Circle",
            "dimensions": {
                "outer_diameter": 0.4,
                "inner_diameter": 0.3,
            },
        },
    )
    geometry = build_swept_member_geometry(
        section,
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0,) * 6,
        (0.0,) * 6,
        ndm=3,
        scale=1.0,
        stations=3,
        circle_resolution=16,
    )
    assert geometry is not None
    assert geometry.points.shape[0] == 2 * 3 * 16


def test_generated_circular_fiber_section_can_infer_display_shape():
    section = SectionData(
        tag=3,
        name="Circular fiber",
        section_type="Fiber",
        fiber_components=[
            FiberComponentData(
                "CircPatch",
                "Core",
                1,
                {
                    "r_inner": 0.0,
                    "r_outer": 0.18,
                    "n_radial": 4,
                    "n_circum": 24,
                },
            ),
            FiberComponentData(
                "CircPatch",
                "Cover - outer",
                2,
                {
                    "r_inner": 0.18,
                    "r_outer": 0.20,
                    "n_radial": 1,
                    "n_circum": 24,
                },
            ),
        ],
    )
    inferred = infer_fiber_display_geometry(section)
    assert inferred["shape"] == "Circle"
    assert inferred["dimensions"]["outer_diameter"] == pytest.approx(0.4)
