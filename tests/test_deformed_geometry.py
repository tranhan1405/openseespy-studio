from __future__ import annotations

import math

import numpy as np
import pytest

from openseespy_studio.deformed_geometry import (
    build_swept_member_geometry,
    deformed_member_frames,
    geometry_contours,
    infer_fiber_display_geometry,
    section_axis_strength_labels,
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


def test_t_display_contour_can_be_shifted_to_centroidal_axis():
    contour = geometry_contours(
        {
            "shape": "T",
            "dimensions": {
                "height": 0.6,
                "flange_width": 0.5,
                "flange_thickness": 0.12,
                "web_width": 0.2,
                "centroid_y": 0.08,
            },
        }
    )[0]
    assert float(np.max(contour[:, 0])) == pytest.approx(0.3 - 0.08)
    assert float(np.min(contour[:, 0])) == pytest.approx(-0.3 - 0.08)


def test_arbitrary_rectangular_fiber_patches_do_not_fake_a_rectangle():
    section = SectionData(
        tag=9,
        name="Custom fiber",
        section_type="Fiber",
        fiber_components=[
            FiberComponentData(
                "RectPatch",
                "Patch A",
                1,
                {
                    "y_center": 0.0,
                    "z_center": -0.2,
                    "width_y": 0.1,
                    "depth_z": 0.1,
                    "n_y": 2,
                    "n_z": 2,
                },
            ),
            FiberComponentData(
                "RectPatch",
                "Patch B",
                1,
                {
                    "y_center": 0.0,
                    "z_center": 0.2,
                    "width_y": 0.1,
                    "depth_z": 0.1,
                    "n_y": 2,
                    "n_z": 2,
                },
            ),
        ],
    )
    assert infer_fiber_display_geometry(section) == {}


def test_section_axis_strength_labels_identify_major_axis():
    section = SectionData(
        tag=11,
        name="Rectangular elastic",
        section_type="Elastic",
        parameters={
            "E": 30.0e9,
            "A": 0.15,
            "Iz": 0.003125,
            "Iy": 0.001125,
            "G": 12.0e9,
            "J": 0.001,
        },
    )
    y_label, z_label = section_axis_strength_labels(section)
    assert y_label == "y · Iy weak"
    assert z_label == "z · Iz strong"


def test_section_axis_strength_labels_keep_symmetric_axes_neutral():
    section = SectionData(
        tag=12,
        name="Circular elastic",
        section_type="Elastic",
        parameters={
            "E": 30.0e9,
            "A": 0.125,
            "Iz": 0.001,
            "Iy": 0.001,
            "G": 12.0e9,
            "J": 0.002,
        },
    )
    assert section_axis_strength_labels(section) == ("y · Iy", "z · Iz")


def test_unsmoothed_member_can_use_two_stations_for_model_view():
    centerline, _fy, _fz, _m = deformed_member_frames(
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0,) * 6,
        (0.0,) * 6,
        ndm=3,
        scale=1.0,
        stations=2,
        smooth=False,
    )
    assert centerline.shape == (2, 3)


def test_swept_quad_connectivity_stays_within_point_bounds():
    section = SectionData(
        tag=13,
        name="Model-view rectangle",
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
        (0.0,) * 6,
        (0.0,) * 6,
        ndm=3,
        scale=1.0,
        stations=2,
        smooth=False,
    )
    assert geometry is not None
    records = geometry.faces.reshape((-1, 5))
    assert np.all(records[:, 0] == 4)
    assert int(records[:, 1:].min()) >= 0
    assert int(records[:, 1:].max()) < len(geometry.points)


def test_fiber_i_section_display_geometry_reports_strong_weak_axes():
    section = SectionData(
        tag=14,
        name="Fiber I",
        section_type="Fiber",
        display_geometry={
            "shape": "I",
            "dimensions": {
                "height": 0.60,
                "flange_width": 0.30,
                "flange_thickness": 0.03,
                "web_width": 0.02,
            },
        },
    )
    y_label, z_label = section_axis_strength_labels(section)
    assert "weak" in y_label
    assert "strong" in z_label
