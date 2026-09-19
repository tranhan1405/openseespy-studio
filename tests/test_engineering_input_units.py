from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.project import MaterialData, SectionData
from openseespy_studio.ui.material_dialog import MaterialDialog
from openseespy_studio.ui.section_dialog import SectionDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_material_stress_parameters_are_edited_in_mpa_and_stored_in_pa(qapp):
    material = MaterialData(
        tag=1,
        name="Steel S355",
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
    dialog = MaterialDialog(material)
    try:
        assert math.isclose(dialog._parameter_spins["Fy"].value(), 355.0)
        assert math.isclose(dialog._parameter_spins["E0"].value(), 200000.0)
        assert (
            dialog.parameter_form.labelForField(
                dialog._parameter_spins["Fy"]
            ).text()
            == "Fy [MPa]:"
        )
        assert (
            dialog.parameter_form.labelForField(
                dialog._parameter_spins["E0"]
            ).text()
            == "E0 [MPa]:"
        )

        dialog._parameter_spins["Fy"].setValue(420.0)
        dialog._parameter_spins["E0"].setValue(210000.0)
        stored = dialog.material_data()
        assert math.isclose(stored.parameters["Fy"], 420.0e6)
        assert math.isclose(stored.parameters["E0"], 210.0e9)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_elastic_section_e_and_g_are_edited_in_mpa_and_stored_in_pa(qapp):
    section = SectionData(
        tag=1,
        name="Elastic beam",
        section_type="Elastic",
        parameters={
            "E": 210.0e9,
            "A": 0.02,
            "Iz": 8.0e-5,
            "Iy": 7.0e-5,
            "G": 80.0e9,
            "J": 1.0e-5,
        },
    )
    dialog = SectionDialog({}, section=section)
    try:
        assert math.isclose(dialog.elastic_spins["E"].value(), 210000.0)
        assert math.isclose(dialog.elastic_spins["G"].value(), 80000.0)

        dialog.elastic_spins["E"].setValue(205000.0)
        dialog.elastic_spins["G"].setValue(79000.0)
        stored = dialog.section_data()
        assert math.isclose(stored.parameters["E"], 205.0e9)
        assert math.isclose(stored.parameters["G"], 79.0e9)
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
