from __future__ import annotations

import pytest

from openseespy_studio.generator import material_to_openseespy
from openseespy_studio.hinge_backbone import (
    HingeBackbonePoint,
    build_symmetric_hysteretic_hinge,
    hinge_rotations,
    suggest_hinge_backbone_points,
)


def _points():
    return [
        HingeBackbonePoint(100.0e3, 0.001),
        HingeBackbonePoint(150.0e3, 0.005),
        HingeBackbonePoint(135.0e3, 0.020),
    ]


def test_moment_rotation_backbone_keeps_explicit_rotations():
    rotations = hinge_rotations(
        _points(),
        basis="moment_rotation",
    )

    assert rotations == pytest.approx((0.001, 0.005, 0.020))


def test_moment_curvature_requires_explicit_equivalent_hinge_length():
    with pytest.raises(ValueError, match="Equivalent hinge length"):
        hinge_rotations(
            _points(),
            basis="moment_curvature",
        )

    rotations = hinge_rotations(
        _points(),
        basis="moment_curvature",
        equivalent_hinge_length_m=0.40,
    )
    assert rotations == pytest.approx((0.0004, 0.0020, 0.0080))


def test_backbone_deformation_must_increase_strictly():
    points = [
        HingeBackbonePoint(100.0e3, 0.001),
        HingeBackbonePoint(150.0e3, 0.001),
        HingeBackbonePoint(135.0e3, 0.020),
    ]

    with pytest.raises(ValueError, match="increase strictly"):
        hinge_rotations(points, basis="moment_rotation")


def test_builder_creates_symmetric_moment_rotation_hysteretic_material():
    material = build_symmetric_hysteretic_hinge(
        tag=8,
        name="RC column hinge",
        points=_points(),
        basis="moment_rotation",
        source_kind="response_2000",
        source_note="Column C1",
    )

    assert material.material_type == "Hysteretic"
    assert material.parameters["s1p"] == pytest.approx(100.0e3)
    assert material.parameters["e2p"] == pytest.approx(0.005)
    assert material.parameters["s3p"] == pytest.approx(135.0e3)
    assert material.parameters["s1n"] == pytest.approx(-100.0e3)
    assert material.parameters["e2n"] == pytest.approx(-0.005)
    assert material.parameters["s3n"] == pytest.approx(-135.0e3)
    assert material.parameters["pinchX"] == pytest.approx(1.0)
    assert material.parameters["pinchY"] == pytest.approx(1.0)
    assert material.parameters["damage1"] == pytest.approx(0.0)
    assert material.parameters["damage2"] == pytest.approx(0.0)
    assert material.parameters["beta"] == pytest.approx(0.0)

    assert material.source["response_quantity"] == "moment_rotation"
    calibration = material.source["calibration"]
    assert calibration["source_kind"] == "response_2000"
    assert calibration["source_note"] == "Column C1"
    assert calibration["symmetry"] == "mirrored_positive_branch"
    assert "not inferred" in calibration["cyclic_rule_note"]


def test_hinge_material_exports_moment_in_active_project_units():
    material = build_symmetric_hysteretic_hinge(
        tag=9,
        name="RC hinge",
        points=_points(),
        basis="moment_rotation",
    )

    command = material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )

    assert command.startswith(
        "ops.uniaxialMaterial('Hysteretic', 9, "
        "100, 0.001, 150, 0.005, 135, 0.02"
    )
    assert "-100, -0.001" in command


def test_monotonic_backbone_does_not_silently_infer_cyclic_parameters():
    material = build_symmetric_hysteretic_hinge(
        tag=10,
        name="Explicit cyclic assumptions",
        points=_points(),
        basis="moment_rotation",
        pinch_x=0.7,
        pinch_y=0.8,
        damage_1=0.1,
        damage_2=0.2,
        beta=0.3,
    )

    assert material.parameters["pinchX"] == pytest.approx(0.7)
    assert material.parameters["pinchY"] == pytest.approx(0.8)
    assert material.parameters["damage1"] == pytest.approx(0.1)
    assert material.parameters["damage2"] == pytest.approx(0.2)
    assert material.parameters["beta"] == pytest.approx(0.3)



def test_suggest_hinge_points_uses_positive_curve_and_terminal_point():
    curvature = [
        0.0,
        0.0005,
        0.0010,
        0.0020,
        0.0040,
        0.0080,
        0.0120,
    ]
    moment = [
        0.0,
        40.0e3,
        78.0e3,
        125.0e3,
        150.0e3,
        158.0e3,
        155.0e3,
    ]

    points = suggest_hinge_backbone_points(curvature, moment)

    assert len(points) == 3
    assert 0.0 < points[0].deformation < points[1].deformation
    assert points[1].deformation < points[2].deformation
    assert points[2].deformation == pytest.approx(0.0120)
    assert points[2].moment_nm == pytest.approx(155.0e3)
    assert all(point.moment_nm > 0.0 for point in points)
