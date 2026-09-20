from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.material_dialog import MaterialDialog


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


def test_material_without_live_envelope_hides_large_preview_pane():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Bond_SP01")

        assert dialog.preview_host.isHidden()
        assert not dialog.material_note.isHidden()
        assert dialog.preview.minimumWidth() <= 260
        assert dialog.preview.minimumHeight() <= 180
    finally:
        _close(dialog)


def test_material_with_live_envelope_shows_compact_preview_pane():
    dialog = MaterialDialog(
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        _select_material_type(dialog, "Hysteretic")

        assert not dialog.preview_host.isHidden()
        assert not dialog.preview_title.isHidden()
        assert dialog.preview.minimumWidth() == 260
        assert dialog.preview.minimumHeight() == 180
    finally:
        _close(dialog)
