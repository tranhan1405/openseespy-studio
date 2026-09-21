from __future__ import annotations

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

    assert len(records) == 2
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
