from __future__ import annotations

from dataclasses import asdict
import inspect
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.generator import (
    nd_material_source_comments,
    nd_material_to_openseespy,
)
from openseespy_studio import nd_material_library as nd_library
from openseespy_studio.nd_material_library import (
    filter_verified_nd_material_library,
    load_verified_nd_material_library,
    nd_material_from_library_record,
    nd_material_library_facets,
)
from openseespy_studio.project import (
    MaterialData,
    NDMaterialData,
    ProjectDatabase,
    nd_material_requires_stage_update,
    nd_material_supported_formulations,
    nd_material_supports_plate_fiber,
)
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.nd_material_library_dialog import (
    NDMaterialLibraryDialog,
)
from openseespy_studio.ui.shell_dialog import (
    NDMaterialDialog,
    ShellSectionDialog,
)


_APP = QApplication.instance() or QApplication([])


def _record(model: str):
    return next(
        item
        for item in load_verified_nd_material_library()
        if item.model == model
    )


def test_verified_nd_library_baseline_has_nine_supported_models():
    records = load_verified_nd_material_library()

    assert len(records) == 9
    assert {record.model for record in records} == {
        "ElasticIsotropic",
        "ElasticOrthotropic",
        "J2Plasticity",
        "DruckerPrager",
        "PressureIndependMultiYield",
        "PressureDependMultiYield",
        "ASDConcrete3D",
        "OrthotropicRAConcrete",
        "SmearedSteelDoubleLayer",
    }
    assert all(record.is_verified for record in records)
    assert all(record.is_starter_template for record in records)
    assert all(record.source_url for record in records)
    assert all(record.compatibility for record in records)
    assert all(record.verification_date == "2026-09-24" for record in records)
    assert all(record.citation_text for record in records)


def test_verified_nd_library_declares_formulation_compatibility():
    records = load_verified_nd_material_library()
    plate_fiber = {
        record.model
        for record in records
        if "PlateFiber" in record.compatibility
    }
    assert plate_fiber == {
        "ElasticIsotropic",
        "ElasticOrthotropic",
        "J2Plasticity",
    }

    drucker = _record("DruckerPrager")
    assert drucker.compatibility == (
        "ThreeDimensional",
        "PlaneStrain",
    )
    assert not nd_material_supports_plate_fiber("DruckerPrager")

    multi_yield = _record("PressureIndependMultiYield")
    assert multi_yield.compatibility == (
        "PlaneStrain",
        "ThreeDimensional",
    )
    assert not nd_material_supports_plate_fiber(
        "PressureIndependMultiYield"
    )

    pressure_depend = _record("PressureDependMultiYield")
    assert pressure_depend.compatibility == (
        "ThreeDimensional",
        "PlaneStrain",
    )
    assert not nd_material_supports_plate_fiber(
        "PressureDependMultiYield"
    )
    assert nd_material_requires_stage_update(
        "PressureIndependMultiYield"
    )
    assert nd_material_requires_stage_update(
        "PressureDependMultiYield"
    )

    asd = _record("ASDConcrete3D")
    assert asd.compatibility == ("ThreeDimensional",)
    assert not nd_material_supports_plate_fiber("ASDConcrete3D")

    ra = _record("OrthotropicRAConcrete")
    assert ra.compatibility == ("Plane Stress",)
    assert not nd_material_supports_plate_fiber(
        "OrthotropicRAConcrete"
    )

    smeared = _record("SmearedSteelDoubleLayer")
    assert smeared.compatibility == ("Plane Stress",)
    assert not nd_material_supports_plate_fiber(
        "SmearedSteelDoubleLayer"
    )

    for record in records:
        assert set(record.compatibility) == set(
            nd_material_supported_formulations(record.model)
        )


def test_nd_library_facets_and_combined_filters():
    records = load_verified_nd_material_library()
    facets = nd_material_library_facets(records)

    assert facets["family"] == (
        "Concrete continuum",
        "Elastic continuum",
        "Multi-yield soil",
        "Plastic continuum",
        "Pressure-sensitive plasticity",
        "RC membrane concrete",
        "RC membrane reinforcement",
    )
    assert "PlateFiber" in facets["compatibility"]
    assert "BeamFiber" in facets["compatibility"]
    assert "ElasticOrthotropic" in facets["model"]
    assert "Orthotropic" in facets["behavior"]

    beam_fiber = filter_verified_nd_material_library(
        records,
        family="Elastic continuum",
        compatibility="BeamFiber",
    )
    assert [record.model for record in beam_fiber] == [
        "ElasticOrthotropic"
    ]

    j2 = filter_verified_nd_material_library(
        records,
        query="pressure-insensitive metal",
    )
    assert [record.model for record in j2] == ["J2Plasticity"]

    source_search = filter_verified_nd_material_library(
        records,
        query="OpenSees Documentation orthotropic",
    )
    assert [record.model for record in source_search] == [
        "ElasticOrthotropic"
    ]

    elastic_behavior = filter_verified_nd_material_library(
        records,
        behavior="Orthotropic",
    )
    assert [record.model for record in elastic_behavior] == [
        "ElasticOrthotropic"
    ]
    assert filter_verified_nd_material_library(()) == ()


def test_nd_library_rejects_invalid_physical_parameters(monkeypatch):
    raw = asdict(_record("ElasticIsotropic"))
    raw["parameters_si"]["E"] = -1.0
    payload = {
        "schema_version": 1,
        "records": [raw],
    }
    monkeypatch.setattr(
        nd_library,
        "_resource_text",
        lambda: json.dumps(payload),
    )

    try:
        nd_library.load_verified_nd_material_library()
    except ValueError as exc:
        assert "E > 0" in str(exc)
    else:
        raise AssertionError("Invalid E should be rejected.")


def test_nd_library_rejects_missing_verification_date(monkeypatch):
    raw = asdict(_record("ElasticIsotropic"))
    raw["verification"].pop("checked_on", None)
    payload = {
        "schema_version": 1,
        "records": [raw],
    }
    monkeypatch.setattr(
        nd_library,
        "_resource_text",
        lambda: json.dumps(payload),
    )

    try:
        nd_library.load_verified_nd_material_library()
    except ValueError as exc:
        assert "checked_on" in str(exc)
    else:
        raise AssertionError("Missing checked_on should be rejected.")


def test_nd_library_rejects_incomplete_source_units(monkeypatch):
    raw = asdict(_record("ElasticOrthotropic"))
    raw["source_units"].pop("Gzx")
    payload = {
        "schema_version": 1,
        "records": [raw],
    }
    monkeypatch.setattr(
        nd_library,
        "_resource_text",
        lambda: json.dumps(payload),
    )

    try:
        nd_library.load_verified_nd_material_library()
    except ValueError as exc:
        assert "source_units" in str(exc)
    else:
        raise AssertionError("Incomplete source_units should be rejected.")


def test_nd_library_insert_carries_traceable_source_metadata():
    record = _record("ElasticIsotropic")
    material = nd_material_from_library_record(record, tag=7)

    assert material.tag == 7
    assert material.material_type == "ElasticIsotropic"
    assert material.parameters == record.parameters_si
    assert material.source["status"] == "verified"
    assert material.source["record_id"] == record.id
    assert "PlateFiber" in material.source["compatibility"]
    assert (
        material.source["verification"]["parameter_status"]
        == "starter_template"
    )

    restored = NDMaterialData.from_dict(material.to_dict())
    assert restored.source == material.source
    assert restored.parameters == material.parameters


def test_nd_library_export_includes_provenance_and_valid_command():
    material = nd_material_from_library_record(
        _record("ElasticIsotropic"),
        tag=8,
    )

    comments = nd_material_source_comments(material)
    assert "# Source status: verified" in comments
    assert any(line.startswith("# Source URL: https://") for line in comments)
    assert any("PlateFiber" in line for line in comments)
    assert "# Parameter status: starter_template" in comments
    assert "# Source verified on: 2026-09-24" in comments

    command = nd_material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )
    assert command == (
        "ops.nDMaterial('ElasticIsotropic', "
        "8, 200000, 0.3, 0)"
    )


def test_nd_library_dialog_browses_and_filters_records():
    dialog = NDMaterialLibraryDialog(
        next_tag=11,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        assert dialog.add_button.isEnabled()
        assert dialog.material_data().tag == 11
        assert dialog.material_data().source["status"] == "verified"
        assert dialog.result_count.text() == "9 / 9 shown"
        assert dialog.copy_command.isEnabled()
        assert dialog.command_preview.text() == (
            "ops.nDMaterial('ElasticIsotropic', "
            "11, 200000, 0.3, 0)"
        )

        model_index = dialog.model_filter.findData("J2Plasticity")
        assert model_index >= 0
        dialog.model_filter.setCurrentIndex(model_index)
        _APP.processEvents()
        assert dialog.result_count.text() == "1 / 9 shown"
        assert dialog.material_data().material_type == "J2Plasticity"

        dialog.clear_filters.click()
        _APP.processEvents()
        behavior_index = dialog.behavior_filter.findData("Orthotropic")
        assert behavior_index >= 0
        dialog.behavior_filter.setCurrentIndex(behavior_index)
        _APP.processEvents()
        assert dialog.result_count.text() == "1 / 9 shown"
        assert (
            dialog.material_data().material_type
            == "ElasticOrthotropic"
        )

        dialog.clear_filters.click()
        _APP.processEvents()
        formulation_index = dialog.compatibility_filter.findData(
            "BeamFiber"
        )
        assert formulation_index >= 0
        dialog.compatibility_filter.setCurrentIndex(formulation_index)
        _APP.processEvents()
        assert dialog.result_count.text() == "1 / 9 shown"
        assert (
            dialog.material_data().material_type
            == "ElasticOrthotropic"
        )

        dialog.clear_filters.click()
        dialog.search.setText("J2")
        _APP.processEvents()

        visible_models = []
        root = dialog.tree.invisibleRootItem()
        for family_index in range(root.childCount()):
            family = root.child(family_index)
            for item_index in range(family.childCount()):
                item = family.child(item_index)
                if not item.isHidden():
                    visible_models.append(item.text(0))
        assert any("J2Plasticity" in text for text in visible_models)
        assert all(
            "J2Plasticity" in text
            for text in visible_models
        )

        dialog.search.setText("definitely-no-such-material")
        _APP.processEvents()
        assert dialog.result_count.text() == "0 / 9 shown"
        assert not dialog.add_button.isEnabled()
        assert not dialog.copy_command.isEnabled()

        dialog.clear_filters.click()
        _APP.processEvents()
        assert dialog.result_count.text() == "9 / 9 shown"
        assert "Verified against source: 2026-09-24" in dialog.source.text()

        dialog.copy_citation.click()
        _APP.processEvents()
        assert "OpenSees Documentation" in QApplication.clipboard().text()

        dialog.copy_source_url.click()
        _APP.processEvents()
        assert QApplication.clipboard().text().startswith("https://")

        dialog.copy_command.click()
        _APP.processEvents()
        assert (
            QApplication.clipboard().text()
            == dialog.command_preview.text()
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_smeared_steel_library_record_is_dependency_aware():
    record = _record("SmearedSteelDoubleLayer")
    material = nd_material_from_library_record(record, tag=81)

    assert material.parameters["mat1"] == 1.0
    assert material.parameters["mat2"] == 2.0
    assert material.parameters["ratio1"] == 0.01
    assert material.parameters["ratio2"] == 0.01
    assert "dependency tags" in " ".join(record.limitations)

    project = ProjectDatabase()
    try:
        project.add_nd_material(material)
    except ValueError as exc:
        assert "missing uniaxial material" in str(exc)
    else:
        raise AssertionError(
            "Smeared steel starter must require its uniaxial dependencies."
        )

    project.add_material(MaterialData(1, "Steel X", "Steel02"))
    project.add_material(MaterialData(2, "Steel Y", "Steel02"))
    project.add_nd_material(material)
    assert project.nd_materials_using_material(1) == [81]
    assert project.nd_materials_using_material(2) == [81]


def test_pressure_independ_multi_yield_library_and_generator():
    record = _record("PressureIndependMultiYield")
    material = nd_material_from_library_record(record, tag=41)

    assert material.parameters["nd"] == 2.0
    assert material.parameters["rho"] == 1500.0
    assert material.parameters["noYieldSurf"] == 20.0
    assert "updateMaterialStage" in " ".join(record.limitations)

    command = nd_material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )
    assert command == (
        "ops.nDMaterial('PressureIndependMultiYield', 41, "
        "2, 1.5, 60000, 300000, 37, 0.1, 0, 80, 0, 20)"
    )


def test_pressure_independ_multi_yield_editor_and_validation():
    dialog = NDMaterialDialog(
        next_tag=42,
        units={"length": "m", "force": "kN", "time": "s"},
    )
    try:
        index = dialog.material_type.findData(
            "PressureIndependMultiYield"
        )
        assert index >= 0
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()

        material = dialog.material_data()
        assert material.material_type == "PressureIndependMultiYield"
        assert material.parameters["nd"] == 2.0
        assert material.parameters["noYieldSurf"] == 20.0
        assert "updateMaterialStage" in dialog.note.text()
        assert "custom surface pairs" in dialog.note.text()

        nd_widget = dialog._parameter_widgets["nd"]
        surf_widget = dialog._parameter_widgets["noYieldSurf"]
        assert nd_widget.decimals() == 0
        assert surf_widget.decimals() == 0
        assert surf_widget.minimum() == 1.0
        assert surf_widget.maximum() == 39.0
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()

    bad = dict(_record("PressureIndependMultiYield").parameters_si)
    bad["noYieldSurf"] = -10.0
    try:
        NDMaterialData(
            tag=43,
            name="Invalid custom surfaces",
            material_type="PressureIndependMultiYield",
            parameters=bad,
        )
    except ValueError as exc:
        assert "noYieldSurf" in str(exc)
        assert "not supported" in str(exc)
    else:
        raise AssertionError(
            "Negative custom noYieldSurf should be rejected."
        )


def test_nd_library_rejects_core_compatibility_drift(monkeypatch):
    raw = asdict(_record("PressureIndependMultiYield"))
    raw["compatibility"].append("PlateFiber")
    payload = {
        "schema_version": 1,
        "records": [raw],
    }
    monkeypatch.setattr(
        nd_library,
        "_resource_text",
        lambda: json.dumps(payload),
    )

    try:
        nd_library.load_verified_nd_material_library()
    except ValueError as exc:
        assert "core formulations" in str(exc)
    else:
        raise AssertionError(
            "Library/core compatibility drift should be rejected."
        )


def test_pressure_depend_multi_yield_library_and_generator():
    record = _record("PressureDependMultiYield")
    material = nd_material_from_library_record(record, tag=51)

    assert material.parameters["rho"] == 1900.0
    assert material.parameters["frictionAng"] == 33.0
    assert material.parameters["e"] == 0.7
    assert material.parameters["noYieldSurf"] == 20.0
    assert "updateMaterialStage" in " ".join(record.limitations)

    command = nd_material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )
    assert command == (
        "ops.nDMaterial('PressureDependMultiYield', 51, "
        "2, 1.9, 75000, 200000, 33, 0.1, 80, 0.5, 27, "
        "0.07, 0.4, 2, 10, 0.01, 1, 20, 0.7, 0.9, "
        "0.02, 0.7, 101, 0.3)"
    )


def test_pressure_depend_multi_yield_editor_and_validation():
    dialog = NDMaterialDialog(
        next_tag=52,
        units={"length": "m", "force": "kN", "time": "s"},
    )
    try:
        index = dialog.material_type.findData(
            "PressureDependMultiYield"
        )
        assert index >= 0
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()

        material = dialog.material_data()
        assert material.material_type == "PressureDependMultiYield"
        assert material.parameters["nd"] == 2.0
        assert material.parameters["e"] == 0.6
        assert material.parameters["pa"] == 101000.0
        assert material.parameters["c"] == 300.0
        assert "updateMaterialStage" in dialog.note.text()
        assert "critical-state" in dialog.note.text()
        assert "custom surface pairs" in dialog.note.text()

        assert dialog._parameter_widgets["nd"].decimals() == 0
        assert dialog._parameter_widgets["noYieldSurf"].decimals() == 0
        assert dialog._parameter_widgets["noYieldSurf"].maximum() == 39.0
        assert dialog._parameter_widgets["PTAng"].maximum() < 90.0
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()

    bad = dict(_record("PressureDependMultiYield").parameters_si)
    bad["PTAng"] = 95.0
    try:
        NDMaterialData(
            tag=53,
            name="Invalid pressure-dependent soil",
            material_type="PressureDependMultiYield",
            parameters=bad,
        )
    except ValueError as exc:
        assert "PTAng" in str(exc)
    else:
        raise AssertionError("PTAng >= 90 should be rejected.")


def test_pressure_depend_library_searches_cyclic_mobility():
    matches = filter_verified_nd_material_library(
        query="medium sand cyclic mobility",
    )
    assert [record.model for record in matches] == [
        "PressureDependMultiYield"
    ]


def test_asd_concrete_3d_library_generator_and_editor():
    record = _record("ASDConcrete3D")
    material = nd_material_from_library_record(record, tag=71)

    assert material.parameters["fc"] == 30.0e6
    assert material.parameters["ft"] == 3.0e6
    assert material.parameters["Kc"] == 2.0 / 3.0
    assert "custom Te/Ts/Td/Ce/Cs/Cd" in " ".join(record.limitations)

    command = nd_material_to_openseespy(
        material,
        {"length": "m", "force": "N", "time": "s"},
    )
    assert command.startswith(
        "ops.nDMaterial('ASDConcrete3D', 71, "
    )
    assert "'-rho', 2400" in command
    assert "'-fc', 3e+07" in command
    assert "'-ft', 3e+06" in command
    assert "'-Kc', 0.666667" in command
    assert "'-cdf', 0" in command
    assert "'-implex'" not in command

    dialog = NDMaterialDialog(
        next_tag=71,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        index = dialog.material_type.findData("ASDConcrete3D")
        assert index >= 0
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()
        assert dialog.material_data().material_type == "ASDConcrete3D"
        assert dialog._parameter_widgets["implex"].decimals() == 0
        assert dialog._parameter_widgets["Kc"].minimum() > 0.5
        assert "Custom backbone lists" in dialog.note.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_orthotropic_ra_concrete_dependency_generator_and_editor():
    record = _record("OrthotropicRAConcrete")
    material = nd_material_from_library_record(record, tag=72)
    project = ProjectDatabase()

    try:
        project.add_nd_material(material)
    except ValueError as exc:
        assert "missing uniaxial material" in str(exc)
    else:
        raise AssertionError(
            "OrthotropicRAConcrete must reject a missing concrete dependency."
        )

    project.add_material(
        MaterialData(1, "Concrete base", "Concrete02")
    )
    project.add_nd_material(material)
    assert project.nd_materials_using_material(1) == [72]

    command = nd_material_to_openseespy(
        material,
        {"length": "m", "force": "N", "time": "s"},
    )
    assert command == (
        "ops.nDMaterial('OrthotropicRAConcrete', 72, 1, "
        "8e-05, -0.002, 0, '-damageCte1', 0.14, "
        "'-damageCte2', 0.6)"
    )

    project.update_material(
        1,
        MaterialData(2, "Concrete base renamed", "Concrete02"),
    )
    assert project.nd_materials[72].parameters["conc"] == 2.0
    try:
        project.remove_material(2)
    except ValueError as exc:
        assert "nDMaterials 72" in str(exc)
    else:
        raise AssertionError(
            "Referenced concrete material deletion should be blocked."
        )

    dialog = NDMaterialDialog(
        next_tag=73,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        index = dialog.material_type.findData("OrthotropicRAConcrete")
        assert index >= 0
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()
        assert dialog._parameter_widgets["conc"].decimals() == 0
        assert dialog._parameter_widgets["ec"].maximum() < 0.0
        assert "Referenced uniaxial concrete tag" in dialog.note.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_concrete_nd_library_search_terms():
    asd = filter_verified_nd_material_library(
        query="plastic-damage concrete",
    )
    assert [record.model for record in asd] == ["ASDConcrete3D"]

    rotating = filter_verified_nd_material_library(
        query="rotating-angle cyclic compression",
    )
    assert [record.model for record in rotating] == [
        "OrthotropicRAConcrete"
    ]


def test_drucker_prager_library_generates_unit_safe_command():
    material = nd_material_from_library_record(
        _record("DruckerPrager"),
        tag=31,
    )

    command = nd_material_to_openseespy(
        material,
        {"length": "mm", "force": "N", "time": "s"},
    )

    assert command == (
        "ops.nDMaterial('DruckerPrager', 31, "
        "100, 50, 0.1, 0.1, 0.1, 0, 0, 0, 0, 0, "
        "1, 0, 0.101325)"
    )


def test_drucker_prager_editor_is_exposed_and_not_plate_fiber():
    dialog = NDMaterialDialog(
        next_tag=32,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        index = dialog.material_type.findData("DruckerPrager")
        assert index >= 0
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()

        material = dialog.material_data()
        assert material.material_type == "DruckerPrager"
        assert "not available for PlateFiber" in dialog.note.text()
        assert material.parameters["theta"] == 1.0
        assert material.parameters["atmPressure"] == 101325.0
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_drucker_prager_parameter_validation():
    record = _record("DruckerPrager")
    bad = dict(record.parameters_si)
    bad["rhoBar"] = bad["rho"] + 0.01

    try:
        NDMaterialData(
            tag=33,
            name="Invalid Drucker-Prager",
            material_type="DruckerPrager",
            parameters=bad,
        )
    except ValueError as exc:
        assert "rhoBar" in str(exc)
    else:
        raise AssertionError("rhoBar > rho should be rejected.")


def test_shell_workflow_guards_non_plate_fiber_materials():
    source = inspect.getsource(ShellSectionDialog._new_nd_material)
    assert "nd_material_supports_plate_fiber" in source
    assert "not compatible with" in source
    assert "PlateFiber shell sections" in source


def test_drucker_prager_editor_uses_frictional_rho_label():
    dialog = NDMaterialDialog(
        next_tag=34,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        index = dialog.material_type.findData("DruckerPrager")
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()

        labels = [
            dialog.parameter_form.itemAt(
                row,
                dialog.parameter_form.LabelRole,
            ).widget().text()
            for row in range(dialog.parameter_form.rowCount())
        ]
        assert any(
            "Frictional strength parameter" in label
            for label in labels
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_nd_material_editor_preserves_library_provenance():
    material = nd_material_from_library_record(
        _record("J2Plasticity"),
        tag=12,
    )
    dialog = NDMaterialDialog(
        next_tag=12,
        material=material,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        updated = dialog.material_data()
        assert updated.source == material.source
        assert updated.source["record_id"] == material.source["record_id"]
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_nd_material_editor_clears_provenance_if_model_type_changes():
    material = nd_material_from_library_record(
        _record("J2Plasticity"),
        tag=13,
    )
    dialog = NDMaterialDialog(
        next_tag=13,
        material=material,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        index = dialog.material_type.findData("ElasticIsotropic")
        assert index >= 0
        dialog.material_type.setCurrentIndex(index)
        _APP.processEvents()

        updated = dialog.material_data()
        assert updated.material_type == "ElasticIsotropic"
        assert updated.source == {}
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_model_ribbon_and_menu_expose_nd_material_library():
    source = inspect.getsource(MainWindow._build_actions_and_ribbon)

    assert '"nd_material_library"' in source
    assert '"nD Material Library..."' in source
    assert '"new_nd_material"' in source
    assert '"New nD Material..."' in source
    assert 'model_menu.addAction(self.actions["nd_material_library"])' in source
    assert '"nd_material_library",' in source


def test_nd_material_root_context_menu_exposes_library():
    source = inspect.getsource(MainWindow._show_tree_context_menu)

    assert 'if kind == "nd_materials_root":' in source
    assert '"Open nD Material Library..."' in source
    assert "self._show_nd_material_library" in source


def test_nd_properties_surface_library_provenance():
    source = inspect.getsource(MainWindow._show_nd_material_properties)

    assert '"Source status"' in source
    assert '"Library record"' in source
    assert '"Official source"' in source
    assert '"Compatibility"' in source
    assert '"Parameter status"' in source
