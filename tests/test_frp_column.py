from __future__ import annotations

import math

from openseespy_studio.frp_column import (
    FRPColumnSpec,
    build_frp_rc_column,
)
from openseespy_studio.generator import (
    material_to_openseespy,
    section_to_openseespy,
)


UNITS = {"length": "mm", "force": "N", "time": "s"}


def test_circular_wizard_builds_concrete_rebar_frp_and_fiber_section():
    spec = FRPColumnSpec(
        section_tag=10,
        section_name="Circular CFRP column",
        shape="Circular",
        diameter=400.0,
        cover=35.0,
        create_concrete02=True,
        create_reinforcing_steel=True,
        circular_bars=8,
        bar_diameter=16.0,
        frp_family="CFRP",
        frp_layers=2,
        frp_layer_thickness_m=0.000167,
        frp_modulus_pa=230.0e9,
        frp_rupture_strain=0.012,
        confinement_scope="all_concrete",
    )
    result = build_frp_rc_column(spec, {}, UNITS)

    assert result.section.section_type == "Fiber"
    assert result.section.display_geometry["shape"] == "Circle"
    assert [m.material_type for m in result.materials] == [
        "Concrete02",
        "ReinforcingSteel",
        "FRPConfinedConcrete02",
    ]

    frp = next(
        material
        for material in result.materials
        if material.tag == result.frp_material_tag
    )
    assert frp.parameters["mode"] == 0.0
    assert math.isclose(frp.parameters["tfrp"], 0.000334)
    assert math.isclose(frp.parameters["R"], 0.2)

    concrete_patches = [
        component
        for component in result.section.fiber_components
        if component.component_type == "CircPatch"
    ]
    assert concrete_patches
    assert {
        component.material_tag for component in concrete_patches
    } == {result.frp_material_tag}

    rebar_layers = [
        component
        for component in result.section.fiber_components
        if component.component_type == "CircLayer"
    ]
    assert len(rebar_layers) == 1
    assert int(rebar_layers[0].parameters["n_bars"]) == 8


def test_circular_core_only_keeps_unconfined_cover():
    spec = FRPColumnSpec(
        section_tag=11,
        section_name="Core-only idealization",
        shape="Circular",
        diameter=500.0,
        cover=40.0,
        create_concrete02=True,
        create_reinforcing_steel=True,
        circular_bars=10,
        confinement_scope="core_only",
    )
    result = build_frp_rc_column(spec, {}, UNITS)

    patches = [
        component
        for component in result.section.fiber_components
        if component.component_type == "CircPatch"
    ]
    names = {component.name: component.material_tag for component in patches}
    assert names["Core"] == result.frp_material_tag
    assert names["Cover - outer"] == result.base_concrete_tag


def test_rectangular_wizard_uses_ultimate_mode_and_user_point():
    spec = FRPColumnSpec(
        section_tag=20,
        section_name="Rectangular GFRP column",
        shape="Rectangular",
        height=500.0,
        width=400.0,
        cover=40.0,
        create_concrete02=True,
        create_reinforcing_steel=True,
        bars_top=4,
        bars_bottom=4,
        side_bars_each=2,
        bar_diameter=20.0,
        frp_family="GFRP",
        frp_layers=3,
        frp_layer_thickness_m=0.0005,
        frp_modulus_pa=55.0e9,
        frp_rupture_strain=0.02,
        ultimate_fcu_pa=-52.0e6,
        ultimate_ecu=-0.018,
    )
    result = build_frp_rc_column(spec, {}, UNITS)
    frp = next(
        material
        for material in result.materials
        if material.tag == result.frp_material_tag
    )

    assert result.section.display_geometry["shape"] == "Rectangle"
    assert frp.parameters["mode"] == 1.0
    assert frp.parameters["fcu"] == -52.0e6
    assert frp.parameters["ecu"] == -0.018

    command = material_to_openseespy(frp, UNITS)
    assert "'-Ultimate'" in command
    assert "'-JacketC'" not in command


def test_wizard_can_use_existing_concrete_and_rebar_materials():
    first = build_frp_rc_column(
        FRPColumnSpec(
            section_tag=1,
            section_name="Seed",
            create_concrete02=True,
            create_reinforcing_steel=True,
        ),
        {},
        UNITS,
    )
    concrete = next(
        item for item in first.materials
        if item.material_type == "Concrete02"
    )
    rebar = next(
        item for item in first.materials
        if item.material_type == "ReinforcingSteel"
    )
    existing = {concrete.tag: concrete, rebar.tag: rebar}

    result = build_frp_rc_column(
        FRPColumnSpec(
            section_tag=2,
            section_name="Use existing",
            shape="Circular",
            concrete_material_tag=concrete.tag,
            rebar_material_tag=rebar.tag,
            circular_bars=8,
        ),
        existing,
        UNITS,
    )

    assert len(result.materials) == 1
    assert result.materials[0].material_type == "FRPConfinedConcrete02"


def test_generated_frp_material_and_section_are_valid_openseespy_text():
    result = build_frp_rc_column(
        FRPColumnSpec(
            section_tag=30,
            section_name="Generated column",
            shape="Circular",
            create_concrete02=True,
            create_reinforcing_steel=True,
            circular_bars=8,
        ),
        {},
        UNITS,
    )
    combined = result.combined_materials({})
    frp_command = material_to_openseespy(
        combined[result.frp_material_tag],
        UNITS,
    )
    section_lines = section_to_openseespy(
        result.section,
        combined,
        UNITS,
    )

    assert "FRPConfinedConcrete02" in frp_command
    assert "'-JacketC'" in frp_command
    assert section_lines[0].startswith("ops.section('Fiber', 30")
    assert any("ops.patch('circ'" in line for line in section_lines)
    assert any("ops.layer('circ'" in line for line in section_lines)


def test_frp_column_wizard_rejects_non_n_mm_project_units():
    spec = FRPColumnSpec(
        section_tag=40,
        section_name="Unsafe units",
        create_concrete02=True,
        create_reinforcing_steel=True,
    )
    try:
        build_frp_rc_column(
            spec,
            {},
            {"length": "m", "force": "kN", "time": "s"},
        )
    except ValueError as exc:
        assert "mm - N - s" in str(exc)
    else:
        raise AssertionError("Expected FRP wizard unit guard")
