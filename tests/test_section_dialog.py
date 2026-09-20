from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.project import MaterialData, ProjectDatabase
from openseespy_studio.ui.section_dialog import SectionDialog


_APP = QApplication.instance() or QApplication([])


def _close(dialog: SectionDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_new_section_dialog_starts_with_empty_pending_materials():
    dialog = SectionDialog(
        {},
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert dialog.pending_materials() == []

        section = dialog.section_data()
        project = ProjectDatabase()
        for material in dialog.pending_materials():
            project.add_material(material)
        project.add_section(section)

        assert project.sections[1].section_type == "Elastic"
    finally:
        _close(dialog)


def test_section_dialog_with_existing_frp_material_constructs_cleanly():
    material = MaterialData(
        tag=1,
        name="FRP confined concrete",
        material_type="FRPConfinedConcrete02",
    )
    dialog = SectionDialog(
        {1: material},
        next_tag=1,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        assert dialog.pending_materials() == []
        assert dialog.frp_material_combo.currentData() == 1
    finally:
        _close(dialog)


def test_section_dialog_stages_materials_without_mutating_project_mapping():
    material = MaterialData(
        tag=1,
        name="Steel",
        material_type="Elastic",
        parameters={"E": 200.0e9},
    )
    project_materials = {1: material}
    dialog = SectionDialog(
        project_materials,
        next_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        dialog.materials[2] = MaterialData(
            tag=2,
            name="Temporary",
            material_type="Elastic",
            parameters={"E": 100.0e9},
        )

        assert 2 not in project_materials
        assert 2 not in dialog._project_materials
    finally:
        _close(dialog)
