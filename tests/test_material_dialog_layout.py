from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.project import MaterialData
from openseespy_studio.ui.material_library_dialog import MaterialLibraryDialog
from openseespy_studio.ui.material_dialog import (
    MaterialDialog,
    MaterialEnvelopePreview,
)


_APP = QApplication.instance() or QApplication([])


def _select_material_type(dialog: MaterialDialog, material_type: str) -> None:
    index = dialog.material_type.findData(material_type)
    assert index >= 0
    dialog.material_type.setCurrentIndex(index)
    _APP.processEvents()


def _close(dialog: MaterialDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_wrapper_material_hides_response_diagram():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        # Fatigue is a wrapper around an existing material and does not have
        # an independent response curve of its own.
        _select_material_type(dialog, "Fatigue")

        assert dialog.preview_host.isHidden()
        assert not dialog.material_note.isHidden()
        assert dialog.preview.minimumWidth() <= 260
        assert dialog.preview.minimumHeight() <= 180
    finally:
        _close(dialog)


def test_bond_sp01_shows_compact_stress_slip_diagram():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Bond_SP01")

        assert not dialog.preview_host.isHidden()
        assert "parameter diagram" in dialog.preview_title.text().lower()
        points, note, annotations = dialog.preview._curve()
        assert len(points) == 5
        assert "stress-slip" in note
        assert any(label == "Sy / Fy" for _x, _y, label in annotations)
        assert any(label == "Su / Fu" for _x, _y, label in annotations)
    finally:
        _close(dialog)


def test_concrete02_diagram_contains_compression_and_tension_parameters():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Concrete02")

        assert not dialog.preview_host.isHidden()
        points, note, annotations = dialog.preview._curve()
        assert len(points) > 10
        assert "Concrete02" in note
        labels = {label for _x, _y, label in annotations}
        assert "epsc0 / fpc" in labels
        assert "epsU / fpcu" in labels
        assert "ft" in labels
        assert "Ets" in labels
        assert min(y for _x, y in points) < 0.0
        assert max(y for _x, y in points) > 0.0
    finally:
        _close(dialog)


def test_steel02_diagram_uses_current_material_parameters():
    preview = MaterialEnvelopePreview()
    try:
        preview.set_material(
            "Steel02",
            {
                "Fy": 355.0,
                "E0": 200000.0,
                "b": 0.01,
                "R0": 20.0,
                "cR1": 0.925,
                "cR2": 0.15,
            },
        )
        points, note, annotations = preview._curve()

        assert len(points) == 41
        assert "Menegotto-Pinto" in note
        assert points[0][0] < 0.0 < points[-1][0]
        assert points[0][1] < 0.0 < points[-1][1]
        assert any(label == "Fy / E0" for _x, _y, label in annotations)
    finally:
        preview.close()
        preview.deleteLater()
        _APP.processEvents()


def test_reinforcing_steel_diagram_marks_hardening_and_ultimate_strain():
    preview = MaterialEnvelopePreview()
    try:
        preview.set_material(
            "ReinforcingSteel",
            {
                "fy": 500.0,
                "fu": 650.0,
                "Es": 200000.0,
                "Esh": 5000.0,
                "eps_sh": 0.01,
                "eps_ult": 0.12,
            },
        )
        points, _note, annotations = preview._curve()

        labels = {label for _x, _y, label in annotations}
        assert points[-1][0] == 0.12
        assert "fy" in labels
        assert "eps_sh" in labels
        assert "eps_ult / fu" in labels
    finally:
        preview.close()
        preview.deleteLater()
        _APP.processEvents()


def test_new_material_types_build_parameter_groups_and_previews():
    expected = {
        "Hardening": {"E", "sigmaY", "H_iso", "H_kin", "eta"},
        "ElasticPP": {"E", "epsyP", "epsyN", "eps0"},
        "ElasticBilin": {"EP1", "EP2", "epsP2", "EN1", "EN2", "epsN2"},
        "HystereticSmooth": {"ka", "kb", "fbar", "beta"},
    }
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        for material_type, keys in expected.items():
            _select_material_type(dialog, material_type)
            assert set(dialog._parameter_widgets) == keys
            assert not dialog.preview_host.isHidden()
            points, _note, _annotations = dialog.preview._curve()
            assert len(points) >= 3
    finally:
        _close(dialog)


def test_eta_label_is_material_specific():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Hardening")
        assert "Viscoplastic" in dialog._parameter_label(
            "Hardening",
            "eta",
        )

        _select_material_type(dialog, "ElasticPPGap")
        assert "Hardening ratio" in dialog._parameter_label(
            "ElasticPPGap",
            "eta",
        )
    finally:
        _close(dialog)


def test_verified_fatigue_preset_selects_existing_base_material():
    base = MaterialData(
        tag=10,
        name="6082-T6 base",
        material_type="Steel02",
    )
    dialog = MaterialLibraryDialog(
        next_tag=11,
        units={"length": "mm", "force": "N", "time": "s"},
        materials={10: base},
    )
    try:
        target = "georgantzia-2025-6082-t6-fatigue"
        root = dialog.tree.invisibleRootItem()
        stack = [
            root.child(index)
            for index in range(root.childCount())
        ]
        item = None
        while stack:
            current = stack.pop(0)
            if current.data(0, 256) == target:
                item = current
                break
            stack.extend(
                current.child(index)
                for index in range(current.childCount())
            )

        assert item is not None
        dialog.tree.setCurrentItem(item)
        _APP.processEvents()

        assert not dialog.wrapper_base_host.isHidden()
        assert dialog.wrapper_base_combo.currentData() == 10
        assert dialog.add_button.isEnabled()

        material = dialog.material_data()
        assert material.material_type == "Fatigue"
        assert material.base_material_tag == 10
        assert material.parameters["E0"] == 0.168
        assert material.parameters["m"] == -0.375
    finally:
        _close(dialog)


def test_verified_fatigue_preset_disables_insert_without_base_material():
    dialog = MaterialLibraryDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
        materials={},
    )
    try:
        target = "zhang-2025-rebar-ld5-fatigue"
        root = dialog.tree.invisibleRootItem()
        stack = [
            root.child(index)
            for index in range(root.childCount())
        ]
        item = None
        while stack:
            current = stack.pop(0)
            if current.data(0, 256) == target:
                item = current
                break
            stack.extend(
                current.child(index)
                for index in range(current.childCount())
            )

        assert item is not None
        dialog.tree.setCurrentItem(item)
        _APP.processEvents()

        assert not dialog.wrapper_base_host.isHidden()
        assert dialog.wrapper_base_combo.count() == 0
        assert not dialog.add_button.isEnabled()
    finally:
        _close(dialog)


def test_reference_only_ramberg_osgood_is_not_offered_for_new_materials():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        assert dialog.material_type.findData("RambergOsgoodSteel") < 0
    finally:
        _close(dialog)


def test_ramberg_osgood_library_record_is_previewable_but_not_insertable():
    dialog = MaterialLibraryDialog(
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
        materials={},
    )
    try:
        target = "yao-2021-600c-natural-ramberg-osgood"
        root = dialog.tree.invisibleRootItem()
        stack = [
            root.child(index)
            for index in range(root.childCount())
        ]
        item = None
        while stack:
            current = stack.pop(0)
            if current.data(0, 256) == target:
                item = current
                break
            stack.extend(
                current.child(index)
                for index in range(current.childCount())
            )

        assert item is not None
        dialog.tree.setCurrentItem(item)
        _APP.processEvents()

        assert not dialog.add_button.isEnabled()
        assert "REFERENCE ONLY" in dialog.summary.text()
        assert "temporarily removed" in dialog.scope.text()
        points, _note, _annotations = dialog.preview._curve()
        assert len(points) > 10
    finally:
        _close(dialog)
