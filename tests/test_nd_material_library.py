from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.generator import (
    nd_material_source_comments,
    nd_material_to_openseespy,
)
from openseespy_studio.nd_material_library import (
    load_verified_nd_material_library,
    nd_material_from_library_record,
)
from openseespy_studio.project import NDMaterialData
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.nd_material_library_dialog import (
    NDMaterialLibraryDialog,
)
from openseespy_studio.ui.shell_dialog import NDMaterialDialog


_APP = QApplication.instance() or QApplication([])


def _record(model: str):
    return next(
        item
        for item in load_verified_nd_material_library()
        if item.model == model
    )


def test_verified_nd_library_baseline_has_three_supported_models():
    records = load_verified_nd_material_library()

    assert len(records) == 3
    assert {record.model for record in records} == {
        "ElasticIsotropic",
        "ElasticOrthotropic",
        "J2Plasticity",
    }
    assert all(record.is_verified for record in records)
    assert all(record.is_starter_template for record in records)
    assert all(record.source_url for record in records)
    assert all(record.compatibility for record in records)


def test_verified_nd_library_declares_plate_fiber_compatibility():
    records = load_verified_nd_material_library()

    assert all(
        "PlateFiber" in record.compatibility
        for record in records
    )


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
