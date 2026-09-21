from __future__ import annotations

import math

from openseespy_studio.material_test import (
    MaterialTestSpec,
    build_material_test_script,
    default_material_test_spec,
    material_test_history,
    material_test_targets,
)
from openseespy_studio.project import MATERIAL_DEFAULTS, MaterialData


def _material(tag: int, material_type: str) -> MaterialData:
    return MaterialData(
        tag=tag,
        name=material_type,
        material_type=material_type,
        parameters=MATERIAL_DEFAULTS[material_type],
    )


def test_symmetric_cyclic_targets_and_history():
    spec = MaterialTestSpec(
        protocol="symmetric_cyclic",
        amplitude=0.04,
        levels=2,
        cycles_per_level=1,
        steps_per_segment=4,
    )
    assert material_test_targets(spec) == [
        0.0,
        0.02,
        -0.02,
        0.04,
        -0.04,
        0.0,
    ]
    history = material_test_history(spec)
    assert history[0] == 0.0
    assert math.isclose(history[-1], 0.0)
    assert math.isclose(max(history), 0.04)
    assert math.isclose(min(history), -0.04)
    assert len(history) == 1 + 5 * 4


def test_compression_protocol_never_goes_positive():
    spec = MaterialTestSpec(
        protocol="compression_cyclic",
        amplitude=0.008,
        levels=4,
        cycles_per_level=1,
        steps_per_segment=5,
    )
    history = material_test_history(spec)
    assert max(history) <= 1.0e-15
    assert math.isclose(min(history), -0.008)


def test_default_protocols_follow_material_family():
    concrete = default_material_test_spec(_material(1, "Concrete02"))
    assert concrete.protocol == "compression_cyclic"
    assert concrete.amplitude >= 0.006

    pinching = default_material_test_spec(_material(2, "Pinching4"))
    assert pinching.protocol == "symmetric_cyclic"
    assert pinching.amplitude >= 0.04

    steel = default_material_test_spec(_material(3, "Steel02"))
    assert steel.protocol == "symmetric_cyclic"
    assert math.isclose(steel.amplitude, 0.03)


def test_bond_default_amplitude_converts_to_active_length_units():
    bond = _material(4, "Bond_SP01")
    spec = default_material_test_spec(
        bond,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert math.isclose(spec.amplitude, 10.0)


def test_material_test_script_uses_real_opensees_uniaxial_tester():
    material = _material(5, "Steel02")
    spec = MaterialTestSpec(
        protocol="symmetric_cyclic",
        amplitude=0.02,
        levels=2,
        cycles_per_level=1,
        steps_per_segment=3,
    )
    script = build_material_test_script(
        material,
        {"length": "m", "force": "kN", "time": "s"},
        spec,
    )
    assert "import openseespy.opensees as ops" in script
    assert "ops.uniaxialMaterial('Steel02', 5," in script
    assert "ops.testUniaxialMaterial(5)" in script
    assert "ops.setStrain" in script
    assert "ops.getStress()" in script
    assert "ops.getTangent()" in script
    assert "'material_test'" in script


def test_frp_material_test_requires_safe_n_mm_mpa_project_units():
    material = _material(6, "FRPConfinedConcrete02")
    spec = default_material_test_spec(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    script = build_material_test_script(
        material,
        {"length": "mm", "force": "N", "time": "s"},
        spec,
    )
    assert "FRPConfinedConcrete02" in script
    assert "'-JacketC'" in script

    try:
        build_material_test_script(
            material,
            {"length": "m", "force": "kN", "time": "s"},
            spec,
        )
    except ValueError as exc:
        assert "mm - N - s" in str(exc)
    else:
        raise AssertionError("Expected unsafe FRP project units to be rejected")


def test_new_steel_materials_get_cyclic_material_test_defaults():
    for tag, material_type in enumerate(
        ("Hardening", "ElasticPP", "ElasticBilin"),
        start=20,
    ):
        spec = default_material_test_spec(_material(tag, material_type))
        assert spec.protocol == "symmetric_cyclic"
        assert spec.amplitude >= 0.01


def test_hysteretic_smooth_gets_cyclic_material_test_default():
    spec = default_material_test_spec(_material(30, "HystereticSmooth"))

    assert spec.protocol == "symmetric_cyclic"
    assert spec.amplitude > 0.0


def test_hardening_material_test_uses_stress_strain_axes():
    from openseespy_studio.material_test import material_test_axis_labels

    material = _material(31, "Hardening")
    x_label, y_label = material_test_axis_labels(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert x_label == "Strain"
    assert y_label == "Stress [MPa]"


def test_hardening_material_test_script_uses_real_constitutive_command():
    material = _material(32, "Hardening")
    spec = default_material_test_spec(material)
    script = build_material_test_script(
        material,
        {"length": "mm", "force": "N", "time": "s"},
        spec,
    )

    assert "ops.uniaxialMaterial('Hardening', 32," in script
    assert "ops.testUniaxialMaterial(32)" in script
