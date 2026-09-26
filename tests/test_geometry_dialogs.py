from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import MaterialData, SectionData, TransformationData
from openseespy_studio.ui.geometry_dialogs import ElementDialog, TrussDialog


_APP = QApplication.instance() or QApplication([])


def _close(dialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_frame_dialog_constructs_with_real_transformation_field_name():
    sections = {
        1: SectionData(1, "Elastic column", "Elastic"),
        2: SectionData(2, "Fiber column", "Fiber"),
    }
    transformations = {
        1: TransformationData(
            1,
            "PDelta column",
            "PDelta",
            (1.0, 0.0, 0.0),
        )
    }

    dialog = ElementDialog(
        10,
        node_i=1,
        node_j=2,
        sections=sections,
        transformations=transformations,
    )
    try:
        assert dialog.transformation.count() == 1
        assert "PDelta column" in dialog.transformation.currentText()
        assert "(PDelta)" in dialog.transformation.currentText()

        # Elastic formulation must only expose Elastic sections.
        assert dialog.element_type.currentText() == "elasticBeamColumn"
        assert dialog.section.count() == 1
        assert dialog.section.currentData() == 1

        values = dialog.values()
        assert values[0] == 10
        assert values[1:3] == (1, 2)
        assert values[3] == "elasticBeamColumn"
        assert values[4] == 1
        assert values[5] == 1
    finally:
        _close(dialog)


def test_frame_dialog_allows_fiber_section_for_force_beam_column():
    sections = {
        1: SectionData(1, "Elastic column", "Elastic"),
        2: SectionData(2, "Fiber column", "Fiber"),
    }
    transformations = {
        1: TransformationData(
            1,
            "Linear column",
            "Linear",
            (1.0, 0.0, 0.0),
        )
    }

    dialog = ElementDialog(
        11,
        node_i=1,
        node_j=2,
        sections=sections,
        transformations=transformations,
    )
    try:
        dialog.element_type.setCurrentText("forceBeamColumn")
        _APP.processEvents()

        assert dialog.section.count() == 2
        assert dialog.section.findData(2) >= 0
        assert dialog.integration_type.isEnabled()
        assert dialog.integration_points.isEnabled()
    finally:
        _close(dialog)


def test_truss_dialog_exposes_area_material_mass_and_rayleigh():
    materials = {
        4: MaterialData(
            4,
            "Truss steel",
            "Elastic",
            parameters={"E": 200.0e9},
        )
    }
    dialog = TrussDialog(
        30,
        node_i=2,
        node_j=5,
        materials=materials,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert dialog.material.currentData() == 4
        assert dialog.area.value() == 1.0e-3

        dialog.area.setValue(0.0025)
        dialog.rho.setValue(7.85)
        dialog.consistent_mass.setChecked(True)
        dialog.do_rayleigh.setChecked(True)

        values = dialog.values()
        assert values[:5] == (30, 2, 5, 0.0025, 4)
        assert values[5] == "truss"
        assert values[6] == 7.85
        assert values[7] is True
        assert values[8] is True
    finally:
        _close(dialog)


def test_truss_dialog_uses_unit_aware_default_area():
    materials = {
        1: MaterialData(
            1,
            "Elastic",
            "Elastic",
            parameters={"E": 200.0e9},
        )
    }
    dialog = TrussDialog(
        1,
        node_i=1,
        node_j=2,
        materials=materials,
        units={"length": "mm", "force": "N", "time": "s"},
    )
    try:
        # 0.001 m² = 1000 mm².
        assert dialog.area.value() == 1000.0
    finally:
        _close(dialog)



def test_truss_dialog_switches_between_material_and_section_formulations():
    materials = {
        4: MaterialData(
            4,
            "Truss steel",
            "Elastic",
            parameters={"E": 200.0e9},
        )
    }
    sections = {
        7: SectionData(7, "Axial elastic", "Elastic"),
        8: SectionData(8, "Axial fiber", "Fiber"),
        9: SectionData(
            9,
            "Shell plate",
            "ElasticMembranePlate",
        ),
    }
    dialog = TrussDialog(
        31,
        node_i=2,
        node_j=5,
        materials=materials,
        sections=sections,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert dialog.formulation.currentData() == "truss"
        assert dialog.area.isEnabled()
        assert dialog.material_holder.isEnabled()
        assert not dialog.section_holder.isEnabled()

        index = dialog.formulation.findData("trussSection")
        assert index >= 0
        dialog.formulation.setCurrentIndex(index)
        _APP.processEvents()

        assert not dialog.area.isEnabled()
        assert not dialog.material_holder.isEnabled()
        assert dialog.section_holder.isEnabled()
        assert dialog.section.findData(7) >= 0
        assert dialog.section.findData(8) >= 0
        assert dialog.section.findData(9) < 0

        dialog.section.setCurrentIndex(dialog.section.findData(7))
        values = dialog.values()
        assert values[:3] == (31, 2, 5)
        assert values[3] == 0.0
        assert values[4] is None
        assert values[9] == "trussSection"
        assert values[10] == 7
    finally:
        _close(dialog)


def test_truss_dialog_edits_existing_section_based_formulation():
    model = StructuralModel(ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0)
    model.add_element(
        44,
        1,
        2,
        element_type="corotTrussSection",
        section_tag=7,
        group="brace",
        mass_per_length=3.2,
        consistent_mass=True,
        truss_do_rayleigh=True,
    )
    sections = {
        7: SectionData(7, "Axial elastic", "Elastic"),
    }
    dialog = TrussDialog(
        44,
        materials={},
        sections=sections,
        units={"length": "m", "force": "N", "time": "s"},
        element=model.elements[44],
    )
    try:
        assert not dialog.tag.isEnabled()
        assert dialog.formulation.currentData() == "corotTrussSection"
        assert dialog.section.currentData() == 7
        assert dialog.group.currentText() == "brace"
        assert dialog.rho.value() == 3.2
        assert dialog.consistent_mass.isChecked()
        assert dialog.do_rayleigh.isChecked()

        values = dialog.values()
        assert values[9] == "corotTrussSection"
        assert values[10] == 7
    finally:
        _close(dialog)
