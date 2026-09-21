from __future__ import annotations

import pytest

from openseespy_studio.generator import (
    material_source_comments,
    material_to_openseespy,
)
from openseespy_studio.material_library import (
    load_verified_material_library,
    material_from_library_record,
)
from openseespy_studio.project import MaterialData


def _record(record_id: str):
    return next(
        record
        for record in load_verified_material_library()
        if record.id == record_id
    )


def test_verified_material_library_contains_only_traceable_records():
    records = load_verified_material_library()

    assert len(records) == 179
    assert all(record.is_verified for record in records)
    assert all(record.doi for record in records)
    assert all(
        record.parameter_evidence.get("location")
        for record in records
    )


def test_carreno_a615_grade60_steel02_parameters_are_exact():
    record = _record("carreno-2020-a615-grade60-steel02")

    assert record.grade == "ASTM A615 Grade 60"
    assert record.model == "Steel02"
    assert record.parameters_si == {
        "Fy": 480.0e6,
        "E0": 202.0e9,
        "b": 0.02,
        "R0": 20.0,
        "cR1": 0.9,
        "cR2": 0.08,
        "a1": 0.039,
        "a2": 1.0,
        "a3": 0.029,
        "a4": 1.0,
    }
    assert record.doi == "10.1061/(ASCE)ST.1943-541X.0002505"
    assert "Table 3.12" in str(
        record.parameter_evidence.get("location", "")
    )


def test_carreno_a706_grade60_steel02_parameters_are_exact():
    record = _record("carreno-2020-a706-grade60-steel02")

    assert record.grade == "ASTM A706 Grade 60"
    assert record.parameters_si["Fy"] == 476.0e6
    assert record.parameters_si["E0"] == 202.0e9
    assert record.parameters_si["b"] == 0.012
    assert record.parameters_si["a1"] == 0.039
    assert record.parameters_si["a3"] == 0.029


def test_library_material_carries_provenance_through_project_round_trip():
    record = _record("carreno-2020-a615-grade60-steel02")
    material = material_from_library_record(record, tag=7)

    assert material.material_type == "Steel02"
    assert material.source["status"] == "verified"
    assert (
        material.source["primary_reference"]["doi"]
        == "10.1061/(ASCE)ST.1943-541X.0002505"
    )

    restored = MaterialData.from_dict(material.to_dict())
    assert restored.source == material.source
    assert restored.parameters == material.parameters


def test_verified_steel02_exports_complete_hardening_parameter_set():
    material = material_from_library_record(
        _record("carreno-2020-a615-grade60-steel02"),
        tag=12,
    )
    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert command == (
        "ops.uniaxialMaterial('Steel02', 12, 480, 202000, 0.02, "
        "20, 0.9, 0.08, 0.039, 1, 0.029, 1)"
    )


def test_legacy_six_parameter_steel02_gets_no_isotropic_hardening_defaults():
    material = MaterialData(
        tag=4,
        name="Legacy Steel02",
        material_type="Steel02",
        parameters={
            "Fy": 355.0e6,
            "E0": 200.0e9,
            "b": 0.01,
            "R0": 20.0,
            "cR1": 0.925,
            "cR2": 0.15,
        },
    )

    assert material.parameters["a1"] == 0.0
    assert material.parameters["a2"] == 1.0
    assert material.parameters["a3"] == 0.0
    assert material.parameters["a4"] == 1.0


def test_sourced_material_export_comments_are_traceable():
    material = material_from_library_record(
        _record("carreno-2020-a615-grade60-steel02"),
        tag=20,
    )
    comments = material_source_comments(material)

    assert "# Source status: verified" in comments
    assert any("Material Model Parameters" in line for line in comments)
    assert (
        "# DOI: 10.1061/(ASCE)ST.1943-541X.0002505"
        in comments
    )
    assert any("Table 3.12" in line for line in comments)


def test_moodley_2026_adds_fifty_exact_steel02_parameter_sets():
    records = [
        record
        for record in load_verified_material_library()
        if (
            record.id.startswith("moodley-2026-")
            and record.model == "Steel02"
        )
    ]

    assert len(records) == 50
    assert all(record.model == "Steel02" for record in records)
    assert all(
        record.doi == "10.1016/j.jobe.2026.115378"
        for record in records
    )


def test_moodley_2026_spot_checks_truss_and_beam_column_sets():
    truss = _record(
        "moodley-2026-en14301-cr-12-ld5-truss-steel02"
    )
    assert truss.parameters_si == {
        "Fy": 825.0e6,
        "E0": 207500.0e6,
        "b": 0.010,
        "R0": 11.72,
        "cR1": 0.925,
        "cR2": 0.15,
        "a1": 0.012,
        "a2": 1.0,
        "a3": 0.026,
        "a4": 1.0,
    }
    assert "Table B.1" in str(
        truss.parameter_evidence.get("location", "")
    )

    beam = _record(
        "moodley-2026-b500c-16-ld15-beam-steel02"
    )
    assert beam.parameters_si == {
        "Fy": 594.0e6,
        "E0": 195500.0e6,
        "b": 0.00052,
        "R0": 11.13,
        "cR1": 0.925,
        "cR2": 0.15,
        "a1": 0.003,
        "a2": 1.0,
        "a3": 0.000,
        "a4": 1.0,
    }
    assert "Table B.4" in str(
        beam.parameter_evidence.get("location", "")
    )


def test_moodley_2026_records_encode_model_applicability():
    records = [
        record
        for record in load_verified_material_library()
        if (
            record.id.startswith("moodley-2026-")
            and record.model == "Steel02"
        )
    ]
    truss = [record for record in records if "-truss-" in record.id]
    beam = [record for record in records if "-beam-" in record.id]

    assert len(truss) == 25
    assert len(beam) == 25
    assert all(
        any("L/D =" in item for item in record.applicability)
        for record in records
    )
    assert all(
        any("truss" in item.lower() for item in record.applicability)
        for record in truss
    )
    assert all(
        any("beam-column" in item.lower() for item in record.applicability)
        for record in beam
    )


def test_verified_library_reaches_one_hundred_seventy_nine_with_expected_source_counts():
    records = load_verified_material_library()
    prefixes = {
        "carreno-2020-": 2,
        "moodley-2026-": 100,
        "qiu-2023-": 12,
        "singh-2024-": 17,
        "benedetti-2022-": 3,
        "bhandari-2023-": 4,
        "benedetti-2025-": 6,
        "shang-2022-": 6,
        "delgiudice-2022-": 4,
        "georgantzia-2024-": 3,
        "doci-2024-": 2,
        "caballero-castro-2025-": 3,
        "melo-2020-": 2,
        "sosa-caiza-2015-": 4,
        "hung-eltawil-2009-": 2,
        "yigitbas-2026-": 1,
        "georgantzia-2025-": 3,
        "zhang-2025-": 2,
        "zhou-2021-": 1,
        "teng-2016-": 2,
    }

    assert len(records) == 179
    assert len({record.id for record in records}) == 179
    for prefix, expected in prefixes.items():
        assert sum(
            record.id.startswith(prefix)
            for record in records
        ) == expected



def test_delgiudice_2022_adds_traceable_steel02_and_concrete01_sets():
    steel = _record("delgiudice-2022-am-microrebar-steel02")
    hh_lh = _record("delgiudice-2022-hh-lh-core-concrete01")
    hl_ll = _record("delgiudice-2022-hl-ll-core-concrete01")

    assert steel.parameters_si == {
        "Fy": 377.8e6,
        "E0": 177.0e9,
        "b": 0.003,
        "R0": 15.0,
        "cR1": 0.925,
        "cR2": 0.15,
        "a1": 0.0,
        "a2": 1.0,
        "a3": 0.02,
        "a4": 1.0,
    }
    assert hh_lh.parameters_si == {
        "fpc": -43.11e6,
        "epsc0": -0.008,
        "fpcu": -38.40e6,
        "epsU": -0.059,
    }
    assert hl_ll.parameters_si == {
        "fpc": -38.26e6,
        "epsc0": -0.005,
        "fpcu": -23.64e6,
        "epsU": -0.048,
    }
    assert steel.doi == "10.1002/eqe.3578"
    assert "Table 3" in str(steel.parameter_evidence.get("location", ""))
    assert "Table 4" in str(hh_lh.parameter_evidence.get("location", ""))


def test_georgantzia_2024_aluminium_steel02_sets_are_exact():
    expected = {
        "georgantzia-2024-6082-t6-steel02": (
            266.0e6, 66.634e9, 0.005, 7.5, 0.051, 0.042
        ),
        "georgantzia-2024-6063-t6-steel02": (
            326.0e6, 64.176e9, 0.003, 8.5, 0.035, 0.020
        ),
        "georgantzia-2024-6060-t5-steel02": (
            306.0e6, 65.797e9, 0.003, 8.5, 0.046, 0.021
        ),
    }
    for record_id, values in expected.items():
        record = _record(record_id)
        fy, e0, b, r0, a1, a3 = values
        assert record.parameters_si["Fy"] == fy
        assert record.parameters_si["E0"] == e0
        assert record.parameters_si["b"] == b
        assert record.parameters_si["R0"] == r0
        assert record.parameters_si["cR1"] == 0.6
        assert record.parameters_si["cR2"] == 0.15
        assert record.parameters_si["a1"] == a1
        assert record.parameters_si["a2"] == 1.0
        assert record.parameters_si["a3"] == a3
        assert record.parameters_si["a4"] == 1.0
        assert record.doi == "10.1061/JMCEE7.MTENG-17314"
        assert "Tables 3 and 4" in str(
            record.parameter_evidence.get("location", "")
        )


def test_doci_2024_brace_steel02_sets_are_exact():
    test1 = _record("doci-2024-cbf-test1-hss-steel02")
    test2 = _record("doci-2024-cbf-test2-pipe-steel02")

    assert test1.parameters_si["Fy"] == 475.0e6
    assert test2.parameters_si["Fy"] == 408.0e6
    for record in (test1, test2):
        assert record.parameters_si["E0"] == 210.0e9
        assert record.parameters_si["b"] == 0.0001
        assert record.parameters_si["R0"] == 20.0
        assert record.parameters_si["cR1"] == 0.925
        assert record.parameters_si["cR2"] == 0.15
        assert record.parameters_si["a1"] == 0.00001
        assert record.parameters_si["a2"] == 0.1
        assert record.parameters_si["a3"] == 0.00001
        assert record.parameters_si["a4"] == 0.1
        assert record.doi == "10.3390/met14121388"
        assert "Table 4" in str(
            record.parameter_evidence.get("location", "")
        )



def test_caballero_castro_2025_tadas_and_concrete_sets_are_exact():
    unconfined = _record(
        "caballero-castro-2025-unconfined-concrete01"
    )
    confined = _record(
        "caballero-castro-2025-confined-concrete01"
    )
    tadas = _record("caballero-castro-2025-tadas-steel02")

    assert unconfined.parameters_si == {
        "fpc": -28.0e6,
        "epsc0": -0.0027,
        "fpcu": -5.6e6,
        "epsU": -0.0082,
    }
    assert confined.parameters_si == {
        "fpc": -36.4e6,
        "epsc0": -0.0035,
        "fpcu": -7.3e6,
        "epsU": -0.0127,
    }
    assert tadas.parameters_si == {
        "Fy": 240.0e6,
        "E0": 200.0e9,
        "b": 0.02,
        "R0": 30.0,
        "cR1": 0.959,
        "cR2": 0.50,
        "a1": 0.097,
        "a2": 1.0,
        "a3": 0.097,
        "a4": 1.0,
    }
    for record in (unconfined, confined, tadas):
        assert record.doi == "10.1016/j.istruc.2025.108732"
        assert "Table 2" in str(
            record.parameter_evidence.get("location", "")
        )



def test_melo_2020_bond_sp01_sets_are_complete_and_traceable():
    plain = _record("melo-2020-cpa3-plain-bond-sp01")
    deformed = _record("melo-2020-cd-deformed-bond-sp01")

    assert plain.model == "Bond_SP01"
    assert plain.parameters_si == {
        "Fy": 405.0e6,
        "Sy": 0.00046,
        "Fu": 470.0e6,
        "Su": 0.0184,
        "b": 0.30,
        "R": 0.30,
    }
    assert deformed.parameters_si == {
        "Fy": 465.0e6,
        "Sy": 0.00044,
        "Fu": 585.0e6,
        "Su": 0.0176,
        "b": 0.40,
        "R": 0.80,
    }
    for record in (plain, deformed):
        assert record.doi == "10.3389/fbuil.2020.586690"
        location = str(record.parameter_evidence.get("location", ""))
        assert "Table 1" in location
        assert "Table 2" in location


def test_melo_2020_bond_sp01_is_unit_safe_in_export():
    material = material_from_library_record(
        _record("melo-2020-cpa3-plain-bond-sp01"),
        tag=50,
    )

    n_mm = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    kn_m = material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )

    assert "'Bond_SP01', 50, 405, 0.46, 470, 18.4, 0.3, 0.3" in n_mm
    assert (
        "'Bond_SP01', 50, 405000, 0.00046, 470000, 0.0184, 0.3, 0.3"
        in kn_m
    )


def test_sosa_caiza_2015_reinforcingsteel_set_is_exact():
    record = _record(
        "sosa-caiza-2015-e1-connection-reinforcingsteel"
    )

    assert record.model == "ReinforcingSteel"
    assert record.parameters_si == {
        "fy": 489.53e6,
        "fu": 675.69e6,
        "Es": 199948.0e6,
        "Esh": 4482.0e6,
        "eps_sh": 0.0124,
        "eps_ult": 0.132,
    }
    assert record.doi == "10.2174/1874149501509010236"
    location = str(record.parameter_evidence.get("location", ""))
    assert "Table 5" in location
    assert "Table 6" in location



def test_sosa_caiza_2015_elasticpp_strand_sets_are_exact():
    e1_e7 = _record("sosa-caiza-2015-strand-e1-e7-elasticpp")
    e2_e5_e6 = _record(
        "sosa-caiza-2015-strand-e2-e5-e6-elasticpp"
    )
    e3_e4 = _record("sosa-caiza-2015-strand-e3-e4-elasticpp")

    expected = {
        e1_e7.id: {
            "E": 192295.0e6,
            "epsyP": 0.0008,
            "epsyN": -0.0004,
            "eps0": -0.0008,
        },
        e2_e5_e6.id: {
            "E": 192295.0e6,
            "epsyP": 0.0048,
            "epsyN": -0.0024,
            "eps0": -0.0048,
        },
        e3_e4.id: {
            "E": 192295.0e6,
            "epsyP": 0.0078,
            "epsyN": -0.0039,
            "eps0": -0.0064,
        },
    }
    for record in (e1_e7, e2_e5_e6, e3_e4):
        assert record.model == "ElasticPP"
        assert record.parameters_si == expected[record.id]
        assert record.doi == "10.2174/1874149501509010236"
        location = str(record.parameter_evidence.get("location", ""))
        assert "Table 5" in location
        assert "Table 7" in location


def test_hung_eltawil_2009_concrete02_sets_preserve_table_i_values():
    unconfined = _record("hung-eltawil-2009-unconfined-concrete02")
    confined = _record("hung-eltawil-2009-confined-concrete02")

    assert unconfined.model == "Concrete02"
    assert abs(unconfined.parameters_si["fpc"] + 6.0 * 6.894757293168e6) < 1.0e-6
    assert unconfined.parameters_si["epsc0"] == -0.002
    assert abs(unconfined.parameters_si["fpcu"] + 0.4 * 6.894757293168e6) < 1.0e-6
    assert unconfined.parameters_si["epsU"] == -0.01
    assert unconfined.parameters_si["lambda"] == 0.1
    assert abs(unconfined.parameters_si["ft"] - 0.6 * 6.894757293168e6) < 1.0e-6
    assert abs(unconfined.parameters_si["Ets"] - 300.0 * 6.894757293168e6) < 1.0e-3

    assert abs(confined.parameters_si["fpc"] + 7.2 * 6.894757293168e6) < 1.0e-6
    assert confined.parameters_si["epsc0"] == -0.0045
    assert abs(confined.parameters_si["fpcu"] + 2.4 * 6.894757293168e6) < 1.0e-6
    assert confined.parameters_si["epsU"] == -0.03
    assert confined.parameters_si["lambda"] == 0.1
    assert abs(confined.parameters_si["ft"] - 0.72 * 6.894757293168e6) < 1.0e-6
    assert abs(confined.parameters_si["Ets"] - 360.0 * 6.894757293168e6) < 1.0e-3

    for record in (unconfined, confined):
        assert record.doi == "10.1002/eqe.921"
        assert "Table I" in str(
            record.parameter_evidence.get("location", "")
        )


def test_yigitbas_2026_concrete04_set_is_exact():
    record = _record("yigitbas-2026-frame-concrete04")

    assert record.model == "Concrete04"
    assert record.parameters_si == {
        "fc": -38.59e6,
        "epsc": -0.0022,
        "epscu": -0.0141,
        "Ec": 32989.0e6,
        "fct": 2.05e6,
        "et": 0.00004,
        "beta": 0.1,
    }
    assert record.doi == "10.65102/is202545"
    assert "Table 1" in str(
        record.parameter_evidence.get("location", "")
    )



def test_fatigue_library_records_require_and_preserve_base_material():
    record = _record("georgantzia-2025-6082-t6-fatigue")

    with pytest.raises(ValueError, match="requires an existing base material"):
        material_from_library_record(record, tag=61)

    material = material_from_library_record(
        record,
        tag=61,
        base_material_tag=60,
    )
    assert material.material_type == "Fatigue"
    assert material.base_material_tag == 60
    assert material.source["status"] == "verified"
    assert material.source["record_id"] == record.id


def test_georgantzia_2025_aluminium_fatigue_sets_are_exact():
    expected = {
        "georgantzia-2025-6082-t6-fatigue": (0.168, -0.375),
        "georgantzia-2025-6063-t6-fatigue": (0.204, -0.397),
        "georgantzia-2025-6060-t5-fatigue": (0.112, -0.293),
    }
    for record_id, (e0, m) in expected.items():
        record = _record(record_id)
        assert record.model == "Fatigue"
        assert record.parameters_si == {
            "E0": e0,
            "m": m,
            "min": -1.0e16,
            "max": 1.0e16,
        }
        assert record.doi == "10.1007/s10518-025-02097-x"
        location = str(record.parameter_evidence.get("location", ""))
        assert "Table 5" in location
        assert "OpenSees Fatigue" in str(
            record.parameter_evidence.get("relationship", "")
        )


def test_zhang_2025_rebar_fatigue_sets_are_exact():
    expected = {
        "zhang-2025-rebar-ld5-fatigue": (0.138, -0.393),
        "zhang-2025-rebar-ld12p5-fatigue": (0.257, -0.677),
    }
    for record_id, (e0, m) in expected.items():
        record = _record(record_id)
        assert record.parameters_si["E0"] == e0
        assert record.parameters_si["m"] == m
        assert record.parameters_si["min"] == -1.0e16
        assert record.parameters_si["max"] == 1.0e16
        assert record.doi == "10.1007/s10518-025-02131-y"
        assert "Fig. 15" in str(
            record.parameter_evidence.get("location", "")
        )


def test_verified_fatigue_exports_wrapper_with_selected_base_tag():
    material = material_from_library_record(
        _record("georgantzia-2025-6082-t6-fatigue"),
        tag=71,
        base_material_tag=70,
    )
    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert command.startswith(
        "ops.uniaxialMaterial('Fatigue', 71, 70, "
    )
    assert "'-E0', 0.168" in command
    assert "'-m', -0.375" in command
    assert "'-min', -1e+16" in command
    assert "'-max', 1e+16" in command



def test_verified_minmax_failure_limit_sets_are_exact():
    micro = _record("delgiudice-2022-am-microrebar-minmax")
    collapse = _record("zhou-2021-rc-rebar-collapse-minmax")

    assert micro.model == "MinMax"
    assert micro.parameters_si == {
        "min": -1.0e16,
        "max": 0.135,
    }
    assert micro.doi == "10.1002/eqe.3578"
    assert "Table 3" in str(
        micro.parameter_evidence.get("location", "")
    )

    assert collapse.parameters_si == {
        "min": -0.04,
        "max": 0.12,
    }
    assert collapse.doi == "10.1186/s40069-021-00463-y"
    assert "Fig. 4" in str(
        collapse.parameter_evidence.get("location", "")
    )


def test_verified_minmax_exports_selected_base_material():
    material = material_from_library_record(
        _record("zhou-2021-rc-rebar-collapse-minmax"),
        tag=81,
        base_material_tag=80,
    )
    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert command == (
        "ops.uniaxialMaterial('MinMax', 81, 80, "
        "'-min', -0.04, '-max', 0.12)"
    )



def test_teng_2016_frpconfinedconcrete02_jacketc_sets_use_active_schema():
    csr1 = _record(
        "teng-2016-csr1-timehistory-frpconfinedconcrete02"
    )
    c5 = _record("teng-2016-c5-frpconfinedconcrete02")

    expected_keys = {
        "fc0", "Ec", "ec0", "mode",
        "tfrp", "Efrp", "erup", "R",
        "ft", "Ets",
    }
    for record in (csr1, c5):
        assert record.model == "FRPConfinedConcrete02"
        assert set(record.parameters_si) == expected_keys
        assert "fcu" not in record.parameters_si
        assert "ecu" not in record.parameters_si
        assert record.parameters_si["mode"] == 0.0
        assert (
            record.doi
            == "10.1061/(ASCE)CC.1943-5614.0000584"
        )
        assert "Table 1" in str(
            record.parameter_evidence.get("location", "")
        )

    assert csr1.parameters_si["fc0"] == -40.82e6
    assert csr1.parameters_si["tfrp"] == 0.000671
    assert csr1.parameters_si["Efrp"] == 231.7e9
    assert csr1.parameters_si["erup"] == 0.018
    assert csr1.parameters_si["R"] == 0.305

    assert c5.parameters_si["fc0"] == -36.5e6
    assert c5.parameters_si["tfrp"] == 0.005
    assert c5.parameters_si["Efrp"] == 18.6e9
    assert c5.parameters_si["erup"] == 0.0286
    assert c5.parameters_si["R"] == 0.1525


def test_teng_c5_frpconfinedconcrete02_exports_jacketc_command():
    material = material_from_library_record(
        _record("teng-2016-c5-frpconfinedconcrete02"),
        tag=90,
    )

    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert command.startswith(
        "ops.uniaxialMaterial('FRPConfinedConcrete02', 90, "
        "-36.5, 28576.4, -0.002, '-JacketC', 5, 18600, "
        "0.0286, 152.5"
    )
    assert ", 3.81824, 1428.82, 1)" in command
    assert "'-Ultimate'" not in command


def test_all_pinching4_library_records_have_physical_context_and_full_schema():
    records = [
        record
        for record in load_verified_material_library()
        if record.model == "Pinching4"
    ]

    assert len(records) == 48
    assert all(
        record.response_quantity
        in {"force_displacement", "moment_rotation", "stress_strain"}
        for record in records
    )
    assert all(record.source_units.get("response") for record in records)
    assert all(record.source_units.get("deformation") for record in records)
    assert all(len(record.parameters_si) == 39 for record in records)
    assert all(len(record.verified_parameters) == 39 for record in records)


def test_qiu_2023_moment_rotation_parameters_are_stored_in_si():
    record = _record("qiu-2023-elbow-s1-pinching4")

    assert record.response_quantity == "moment_rotation"
    assert record.source_units == {
        "response": "kN·m",
        "deformation": "rad",
    }
    assert record.parameters_si["ePf1"] == 1127.2
    assert record.parameters_si["ePd1"] == 0.0005
    assert record.parameters_si["eNf2"] == -2219.6
    assert record.parameters_si["eNd2"] == -0.0407


def test_qiu_generic_dn150_uses_published_symmetric_generic_model():
    record = _record("qiu-2023-generic-tee-dn150-pinching4")

    assert record.parameters_si["ePf3"] == 6750.0
    assert record.parameters_si["eNf3"] == -6750.0
    assert record.parameters_si["uForceP"] == 0.1
    assert record.parameters_si["uForceN"] == 0.1
    assert "Table 4" in str(record.parameter_evidence.get("location", ""))


def test_singh_2024_cfs02_and_scaled_wall_parameters():
    base = _record("singh-2024-cfs02-pinching4")
    west = _record("singh-2024-west-corridor-l1-pinching4")

    assert base.parameters_si["ePf1"] == 43290.0
    assert base.parameters_si["ePd4"] == 0.05826
    assert base.parameters_si["gK3"] == 2.0
    assert base.parameters_si["dmgType"] == 1.0

    assert west.parameters_si["ePf3"] == 275600.0
    assert west.parameters_si["ePd2"] == 0.02257
    assert "Appendix Table A.2" in str(
        west.parameter_evidence.get("location", "")
    )


def test_benedetti_2022_sheathing_parameters():
    record = _record(
        "benedetti-2022-sheathing-to-framing-pinching4"
    )

    assert record.parameters_si["ePf2"] == 1850.0
    assert abs(record.parameters_si["ePd2"] - 0.0069) < 1.0e-12
    assert record.parameters_si["rDispP"] == 0.651
    assert record.parameters_si["gK1"] == 0.0
    assert record.doi == "10.3390/buildings12070981"


def test_bhandari_2023_published_and_symmetry_derived_branches():
    tension = _record("bhandari-2023-tension-pinching4")
    inter = _record(
        "bhandari-2023-inter-horizontal-vertical-pinching4"
    )

    assert tension.parameters_si["ePf1"] == 4420.0
    assert tension.parameters_si["eNf1"] == -4420.0
    assert "symmetric" in str(
        tension.parameter_evidence.get("relationship", "")
    ).lower()

    assert inter.parameters_si["ePf3"] == 89800.0
    assert inter.parameters_si["eNf3"] == -147000.0
    assert inter.parameters_si["eNd4"] == -0.0316


def test_benedetti_2025_preserves_asymmetric_hold_down_fourth_point():
    record = _record(
        "benedetti-2025-floors-2-5-hold-down-pinching4"
    )

    assert record.parameters_si["ePf4"] == 12480.0
    assert record.parameters_si["eNf4"] == -14460.0
    assert record.parameters_si["gK1"] == -2.5
    assert record.parameters_si["gDLim"] == 0.08


def test_shang_2022_sway_brace_parameters():
    record = _record("shang-2022-1000-60-2-pinching4")

    assert record.parameters_si["ePf3"] == 24800.0
    assert abs(record.parameters_si["ePd3"] - 0.0447) < 1.0e-12
    assert record.parameters_si["ePf4"] == 5000.0
    assert record.parameters_si["gKLim"] == -2.0
    assert record.parameters_si["dmgType"] == 0.0


def test_sourced_force_displacement_pinching4_converts_between_project_units():
    material = material_from_library_record(
        _record("singh-2024-cfs02-pinching4"),
        tag=30,
    )

    n_mm = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    kn_m = material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )

    assert "'Pinching4', 30, 43290, 1.65" in n_mm
    assert "'Pinching4', 30, 43.29, 0.00165" in kn_m


def test_sourced_moment_rotation_pinching4_converts_moment_only():
    material = material_from_library_record(
        _record("qiu-2023-elbow-s1-pinching4"),
        tag=31,
    )

    n_mm = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    kn_m = material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )

    assert "'Pinching4', 31, 1.1272e+06, 0.0005" in n_mm
    assert "'Pinching4', 31, 1.1272, 0.0005" in kn_m


def test_legacy_manual_pinching4_remains_raw_for_backward_compatibility():
    material = MaterialData(
        tag=32,
        name="Legacy raw Pinching4",
        material_type="Pinching4",
    )

    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert "'Pinching4', 32, 1, 0.001" in command



def test_moodley_2026_adds_fifty_exact_hysteretic_parameter_sets():
    records = [
        record
        for record in load_verified_material_library()
        if (
            record.id.startswith("moodley-2026-")
            and record.model == "Hysteretic"
        )
    ]

    assert len(records) == 50
    assert all(record.response_quantity == "stress_strain" for record in records)
    assert all(
        record.source_units == {
            "response": "MPa",
            "deformation": "% strain",
        }
        for record in records
    )
    assert all(
        record.doi == "10.1016/j.jobe.2026.115378"
        for record in records
    )


def test_moodley_hysteretic_truss_exact_backbone_and_cyclic_parameters():
    record = _record(
        "moodley-2026-en14301-cr-12-ld8-truss-hysteretic"
    )

    assert record.parameters_si == {
        "s1p": 677.0e6,
        "e1p": 0.0033,
        "s2p": 812.0e6,
        "e2p": 0.0158,
        "s3p": 872.0e6,
        "e3p": 0.2175,
        "s1n": -677.0e6,
        "e1n": -0.0033,
        "s2n": -687.0e6,
        "e2n": -0.0076,
        "s3n": -135.0e6,
        "e3n": -0.1455,
        "pinchX": 0.31,
        "pinchY": 0.53,
        "damage1": 0.0,
        "damage2": 0.242,
        "beta": 0.31,
    }
    location = str(record.parameter_evidence.get("location", ""))
    assert "Table B.2" in location
    assert "Table B.3" in location


def test_moodley_hysteretic_beam_uses_source_prescribed_mirrored_backbone():
    record = _record(
        "moodley-2026-b500c-16-ld15-beam-hysteretic"
    )

    assert record.parameters_si["s1p"] == 594.0e6
    assert record.parameters_si["e1p"] == 0.0030
    assert record.parameters_si["s2p"] == 812.0e6
    assert record.parameters_si["e2p"] == 0.0550
    assert record.parameters_si["s3p"] == 872.0e6
    assert record.parameters_si["e3p"] == 0.2175
    assert record.parameters_si["s1n"] == -594.0e6
    assert record.parameters_si["e1n"] == -0.0030
    assert record.parameters_si["s2n"] == -812.0e6
    assert record.parameters_si["e2n"] == -0.0550
    assert record.parameters_si["s3n"] == -872.0e6
    assert record.parameters_si["e3n"] == -0.2175
    assert record.parameters_si["pinchX"] == 0.10
    assert record.parameters_si["pinchY"] == 0.53
    assert record.parameters_si["damage1"] == 0.0
    assert record.parameters_si["damage2"] == 0.053
    assert record.parameters_si["beta"] == 0.17
    location = str(record.parameter_evidence.get("location", ""))
    assert "Section 4.2.2" in location
    assert "Table B.5" in location


def test_sourced_stress_strain_hysteretic_converts_stress_between_units():
    material = material_from_library_record(
        _record(
            "moodley-2026-en14301-hr-12-ld5-truss-hysteretic"
        ),
        tag=40,
    )

    n_mm = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    kn_m = material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )

    assert "'Hysteretic', 40, 562, 0.0028, 745, 0.0442" in n_mm
    assert "'Hysteretic', 40, 562000, 0.0028, 745000, 0.0442" in kn_m


def test_legacy_manual_hysteretic_remains_raw_for_backward_compatibility():
    material = MaterialData(
        tag=41,
        name="Legacy raw Hysteretic",
        material_type="Hysteretic",
    )

    command = material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert "'Hysteretic', 41, 1, 0.001, 1.2, 0.01" in command
