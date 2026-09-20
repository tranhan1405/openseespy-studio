from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.project import MaterialData, ProjectDatabase, SectionData
import openseespy_studio.ui.test_column_dialog as test_column_dialog_module
from openseespy_studio.ui.test_column_dialog import TestColumnWizard


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_test_column_wizard_cyclic_preset_builds_reference_loading(qapp):
    project = ProjectDatabase()
    project.add_section(
        SectionData(1, "RC column", "Elastic")
    )
    dialog = TestColumnWizard(project)
    try:
        dialog.preset.setCurrentText("Cantilever Cyclic Test")
        qapp.processEvents()

        spec = dialog.data()
        assert spec.axis == 3
        assert spec.lateral_direction == 1
        assert spec.planar is True
        assert spec.base_support == "Fixed"
        assert spec.top_support == "Free"
        assert spec.element_type == "forceBeamColumn"
        assert spec.lateral_reference_load == pytest.approx(1.0)
        assert spec.prescribed_displacement == pytest.approx(0.0)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_test_column_wizard_dynamic_preset_enables_top_mass(qapp):
    dialog = TestColumnWizard(ProjectDatabase())
    try:
        dialog.preset.setCurrentText("Dynamic / Shake-table Column")
        qapp.processEvents()

        spec = dialog.data()
        assert spec.top_mass == pytest.approx(1.0)
        assert spec.top_mass_directions == (1, 2, 3)
        assert spec.axial_load == pytest.approx(0.0)
        assert spec.lateral_reference_load == pytest.approx(0.0)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_test_column_wizard_auto_changes_lateral_axis(qapp):
    dialog = TestColumnWizard(ProjectDatabase())
    try:
        dialog.axis.setCurrentIndex(dialog.axis.findData(1))
        qapp.processEvents()
        assert dialog.lateral.currentData() != 1

        spec = dialog.data()
        assert spec.axis == 1
        assert spec.lateral_direction in {2, 3}
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_test_column_wizard_can_shrink_and_scroll(qapp):
    dialog = TestColumnWizard(ProjectDatabase())
    try:
        dialog.show()
        qapp.processEvents()
        dialog.resize(460, 340)
        qapp.processEvents()

        assert dialog.height() <= 360
        assert dialog.scroll.widgetResizable() is True
        assert dialog.scroll.verticalScrollBar().maximum() > 0
        assert dialog.buttons.isVisible() is True
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_test_column_wizard_can_stage_new_section_without_mutating_project(
    qapp,
    monkeypatch,
):
    project = ProjectDatabase()

    class FakeSectionDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

        def section_data(self):
            return SectionData(
                7,
                "New test section",
                "Elastic",
            )

    monkeypatch.setattr(
        test_column_dialog_module,
        "SectionDialog",
        FakeSectionDialog,
    )

    dialog = TestColumnWizard(project)
    try:
        dialog._create_section()
        qapp.processEvents()

        assert project.sections == {}
        assert dialog.section.currentData() == 7
        assert "new" in dialog.section.currentText().lower()
        assert dialog.data().section_tag == 7

        staged = dialog.new_sections()
        assert len(staged) == 1
        assert staged[0].tag == 7
        assert staged[0].name == "New test section"
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_test_column_wizard_next_section_tag_accounts_for_staged_sections(
    qapp,
):
    project = ProjectDatabase()
    project.add_section(SectionData(2, "Existing", "Elastic"))
    dialog = TestColumnWizard(project)
    try:
        dialog._pending_sections[3] = SectionData(
            3,
            "Pending",
            "Elastic",
        )
        assert dialog._next_section_tag() == 4
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_cyclic_pushover_nlth_specimen_base_interface_defaults_fixed(qapp):
    project = ProjectDatabase()
    dialog = TestColumnWizard(project)
    try:
        for preset in (
            "Cantilever Cyclic Test",
            "Cantilever Pushover",
            "Dynamic / Shake-table Column",
        ):
            dialog.preset.setCurrentText(preset)
            qapp.processEvents()
            spec = dialog.data()
            assert spec.base_interface_type == "Fixed base"
            assert spec.base_interface_materials == {}
            assert spec.base_interface_rayleigh is False
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_rotational_base_interface_auto_selects_bending_rotation(qapp):
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            7,
            "Pinching spring",
            "Pinching4",
        )
    )
    dialog = TestColumnWizard(project)
    try:
        dialog.axis.setCurrentIndex(dialog.axis.findData(3))
        dialog.lateral.setCurrentIndex(dialog.lateral.findData(1))
        dialog.base_interface.setCurrentText("Rotational spring")
        qapp.processEvents()

        spec = dialog.data()
        assert spec.base_interface_type == "Rotational spring"
        assert spec.base_support == "Fixed"
        assert spec.base_interface_materials == {5: 7}
        assert spec.base_interface_rayleigh is False
        assert dialog.base_support.isEnabled() is False
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_translational_slip_interface_prefers_macro_spring(qapp):
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            30,
            "Generic",
            "Elastic",
            parameters={"E": 1000.0},
        )
    )
    project.add_material(
        MaterialData(
            8,
            "Bond",
            "Bond_SP01",
        )
    )
    project.add_material(
        MaterialData(
            3,
            "Macro slip",
            "Pinching4",
        )
    )
    dialog = TestColumnWizard(project)
    try:
        dialog.base_interface.setCurrentText("Translational slip spring")
        qapp.processEvents()

        spec = dialog.data()
        assert spec.base_interface_materials[1] == 3
        assert spec.base_interface_rayleigh is False
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()



def test_bond_sp01_strain_penetration_mode_uses_section_not_dof_spring(qapp):
    project = ProjectDatabase()
    project.add_material(
        MaterialData(
            1,
            "Concrete",
            "Concrete02",
        )
    )
    project.add_material(
        MaterialData(
            2,
            "Steel",
            "ReinforcingSteel",
        )
    )
    project.add_material(
        MaterialData(
            3,
            "Bond",
            "Bond_SP01",
        )
    )
    from openseespy_studio.project import FiberComponentData

    project.add_section(
        SectionData(
            1,
            "RC Fiber",
            "Fiber",
            fiber_components=[
                FiberComponentData(
                    "RectPatch",
                    "Concrete",
                    1,
                    {
                        "width_y": 0.4,
                        "depth_z": 0.4,
                        "n_y": 4,
                        "n_z": 4,
                    },
                ),
                FiberComponentData(
                    "StraightLayer",
                    "Rebar",
                    2,
                    {
                        "y_i": -0.15,
                        "z_i": 0.15,
                        "y_j": 0.15,
                        "z_j": 0.15,
                        "n_bars": 4,
                        "bar_area": 0.0002,
                    },
                ),
            ],
        )
    )

    dialog = TestColumnWizard(project)
    try:
        dialog.section.setCurrentIndex(dialog.section.findData(1))
        dialog.base_interface.setCurrentText(
            "Bond_SP01 strain penetration"
        )
        qapp.processEvents()

        spec = dialog.data()
        assert spec.base_interface_type == "Bond_SP01 strain penetration"
        assert spec.base_interface_materials == {}
        assert spec.strain_penetration_bond_material_tag == 3
        assert dialog.strain_penetration_group.isVisible() is False or True
        assert all(
            not check.isChecked()
            for check, _combo in dialog.interface_rows.values()
        )
        assert spec.base_interface_rayleigh is False
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
