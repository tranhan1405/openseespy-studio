import math

from openseespy_studio.units import UnitSystem


def test_m_kn_s_derived_units_and_stress_conversion():
    units = UnitSystem("m", "kN", "s")

    assert units.mass_label == "t"
    assert math.isclose(units.mass_unit_kg, 1000.0)
    assert math.isclose(units.stress_from_pa(200.0e9), 200.0e6)
    assert math.isclose(
        units.density_from_kg_per_m3(7850.0),
        7.85,
    )


def test_m_kn_s_self_weight_returns_kn_per_m():
    units = UnitSystem("m", "kN", "s")

    line_load = units.line_force_from_density_area_gravity(
        density_kg_per_m3=2500.0,
        area_model_units=0.20,
        gravity_model_units=-9.81,
    )

    assert math.isclose(line_load, -4.905)


def test_m_n_s_keeps_pa_as_n_per_m2_and_density_as_kg_per_m3():
    units = UnitSystem("m", "N", "s")

    assert units.mass_label == "kg"
    assert math.isclose(units.stress_from_pa(200.0e9), 200.0e9)
    assert math.isclose(
        units.density_from_kg_per_m3(2400.0),
        2400.0,
    )


def test_mm_n_s_conversions_are_dimensionally_consistent():
    units = UnitSystem("mm", "N", "s")

    assert units.mass_label == "t"
    assert math.isclose(units.stress_from_pa(200.0e9), 200000.0)
    assert math.isclose(
        units.acceleration_from_m_per_s2(9.81),
        9810.0,
    )
    line_load = units.line_force_from_density_area_gravity(
        density_kg_per_m3=7850.0,
        area_model_units=1000.0,
        gravity_model_units=-9810.0,
    )
    # 1000 mm^2 steel bar: 0.0770085 N/mm.
    assert math.isclose(
        line_load,
        -0.0770085,
        rel_tol=1.0e-8,
    )


def test_unsupported_units_are_rejected():
    try:
        UnitSystem("cm", "kN", "s")
    except ValueError as exc:
        assert "Unsupported length unit" in str(exc)
    else:
        raise AssertionError("Expected unsupported units to fail")


def test_in_kip_s_converts_ksi_to_pa_consistently():
    units = UnitSystem("in", "kip", "s")

    # 60 kip/in^2 = 60 ksi = 413.68543759 MPa.
    stress_pa = (
        60.0
        * units.force_to_n
        / (units.length_to_m ** 2)
    )
    assert math.isclose(
        stress_pa,
        413.68543759010166e6,
        rel_tol=1.0e-12,
    )
    assert math.isclose(
        units.stress_from_pa(stress_pa),
        60.0,
        rel_tol=1.0e-12,
    )
