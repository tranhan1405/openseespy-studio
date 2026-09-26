from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    FrictionModelData,
    MaterialData,
    NDMaterialData,
    TransformationData,
)
from openseespy_studio.ui.isolation_contact_dialog import (
    ContactElementDialog,
    FrictionBearingDialog,
    LeadRubberXDialog,
    TripleFrictionPendulumDialog,
)


_APP = QApplication.instance() or QApplication([])


def _combo_tags(combo):
    return {
        int(combo.itemData(index))
        for index in range(combo.count())
        if combo.itemData(index) is not None
    }


def _close(dialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_contact_dialog_filters_2d_nodes_and_materials_by_formulation():
    model = StructuralModel(ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0)
    model.add_node(3, 0.5, 0.1, ndf=2)
    model.add_node(4, 0.5, 0.1, ndf=2)
    nd_materials = {
        10: NDMaterialData(
            10,
            "2D contact",
            "ContactMaterial2D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        ),
        11: NDMaterialData(
            11,
            "3D contact",
            "ContactMaterial3D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        ),
    }
    dialog = ContactElementDialog(
        tag=1,
        nodes=model.nodes,
        ndm=2,
        nd_materials=nd_materials,
        transformations={},
        next_node_tag=5,
    )
    try:
        assert _combo_tags(dialog.node_i) == {3, 4}
        assert _combo_tags(dialog.node_j) == {3, 4}

        index = dialog.kind.findData("BeamContact2D")
        assert index >= 0
        dialog.kind.setCurrentIndex(index)
        _APP.processEvents()

        assert _combo_tags(dialog.node_i) == {1, 2}
        assert _combo_tags(dialog.node_j) == {1, 2}
        assert _combo_tags(dialog.node_k) == {3, 4}
        assert _combo_tags(dialog.node_l) == {3, 4}
        assert _combo_tags(dialog.nd_material) == {10}
        assert "ndf=3" in dialog.note.text()
        assert "ndf=2" in dialog.note.text()
    finally:
        _close(dialog)


def test_contact_dialog_filters_3d_nodes_and_materials_by_formulation():
    model = StructuralModel(ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 0.5, 0.1, 0.0, ndf=3)
    model.add_node(4, 0.5, 0.1, 0.0, ndf=3)
    nd_materials = {
        20: NDMaterialData(
            20,
            "2D contact",
            "ContactMaterial2D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        ),
        21: NDMaterialData(
            21,
            "3D contact",
            "ContactMaterial3D",
            {"mu": 0.3, "G": 1.0e8, "c": 0.0, "t": 0.0},
        ),
    }
    transformations = {
        7: TransformationData(
            7,
            "Contact beam",
            "Linear",
            (0.0, 0.0, 1.0),
        )
    }
    dialog = ContactElementDialog(
        tag=1,
        nodes=model.nodes,
        ndm=3,
        nd_materials=nd_materials,
        transformations=transformations,
        next_node_tag=5,
    )
    try:
        assert _combo_tags(dialog.node_i) == {3, 4}
        assert _combo_tags(dialog.node_j) == {3, 4}

        index = dialog.kind.findData("BeamContact3D")
        assert index >= 0
        dialog.kind.setCurrentIndex(index)
        _APP.processEvents()

        assert _combo_tags(dialog.node_i) == {1, 2}
        assert _combo_tags(dialog.node_j) == {1, 2}
        assert _combo_tags(dialog.node_k) == {3, 4}
        assert _combo_tags(dialog.node_l) == {3, 4}
        assert _combo_tags(dialog.nd_material) == {21}
        assert dialog.transformation.isEnabled()
        assert "ndf=6" in dialog.note.text()
        assert "ndf=3" in dialog.note.text()
    finally:
        _close(dialog)


def test_zero_length_contact_2d_rejects_zero_normal_in_dialog():
    model = StructuralModel(ndm=2, ndf=2)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    dialog = ContactElementDialog(
        tag=1,
        nodes=model.nodes,
        ndm=2,
        nd_materials={},
        transformations={},
        next_node_tag=3,
    )
    try:
        dialog.node_i.setCurrentIndex(dialog.node_i.findData(1))
        dialog.node_j.setCurrentIndex(dialog.node_j.findData(2))
        dialog.nx.setValue(0.0)
        dialog.ny.setValue(0.0)

        with pytest.raises(ValueError, match="normal cannot be zero"):
            dialog.values()
    finally:
        _close(dialog)



def test_lead_rubber_x_dialog_explains_flags_and_gates_heating_fields():
    dialog = LeadRubberXDialog(
        tag=1,
        node_i=1,
        node_j=2,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert "Cavitation" in dialog.flags[0].text()
        assert "Buckling" in dialog.flags[1].text()
        assert "Horizontal-stiffness" in dialog.flags[2].text()
        assert "Vertical-stiffness" in dialog.flags[3].text()
        assert "heating degradation" in dialog.flags[4].text()

        assert not dialog.ql.isEnabled()
        assert not dialog.cl.isEnabled()
        assert not dialog.ks.isEnabled()
        assert not dialog.a_s.isEnabled()

        dialog.flags[4].setChecked(True)
        _APP.processEvents()

        assert dialog.ql.isEnabled()
        assert dialog.cl.isEnabled()
        assert dialog.ks.isEnabled()
        assert dialog.a_s.isEnabled()
    finally:
        _close(dialog)


def test_lead_rubber_x_dialog_rejects_bad_geometry_and_orientation():
    dialog = LeadRubberXDialog(
        tag=1,
        node_i=1,
        node_j=2,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        dialog.d1.setValue(0.8)
        dialog.d2.setValue(0.8)
        with pytest.raises(ValueError, match="D1 < bearing diameter D2"):
            dialog.values()

        dialog.d1.setValue(0.1)
        dialog.custom_orientation.setChecked(True)
        for widget, value in zip(
            dialog.orientation,
            (1.0, 0.0, 0.0, 2.0, 0.0, 0.0),
        ):
            widget.setValue(value)

        with pytest.raises(ValueError, match="non-zero and non-parallel"):
            dialog.values()
    finally:
        _close(dialog)


def test_triple_friction_pendulum_dialog_uses_opensees_semantic_labels():
    materials = {
        tag: MaterialData(
            tag,
            f"Elastic {tag}",
            "Elastic",
            {"E": 1.0e8},
        )
        for tag in range(1, 5)
    }
    friction_models = {
        tag: FrictionModelData(
            tag,
            f"Friction {tag}",
            "Coulomb",
            {"mu": 0.03 + 0.01 * tag},
        )
        for tag in range(1, 4)
    }
    dialog = TripleFrictionPendulumDialog(
        tag=10,
        node_i=1,
        node_j=2,
        materials=materials,
        friction_models=friction_models,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert "matP" in dialog.form.labelForField(dialog.materials[0]).text()
        assert "matT" in dialog.form.labelForField(dialog.materials[1]).text()
        assert "matMy" in dialog.form.labelForField(dialog.materials[2]).text()
        assert "matMz" in dialog.form.labelForField(dialog.materials[3]).text()
        assert "Ubar1" in dialog.form.labelForField(dialog.lengths["d1"]).text()
        assert "Ubar2" in dialog.form.labelForField(dialog.lengths["d2"]).text()
        assert "Ubar3" in dialog.form.labelForField(dialog.lengths["d3"]).text()
        kvt_label = dialog.form.labelForField(dialog.kvt).text()
        assert "stiffness" in kvt_label.lower()
        assert "[N/m]" in kvt_label
        assert "flexibility" not in kvt_label.lower()
        assert "Ubar1/Ubar2/Ubar3" in dialog.note.text()
    finally:
        _close(dialog)



def test_tfp_auto_selects_single_available_dependencies():
    materials = {
        1: MaterialData(
            1,
            "Elastic",
            "Elastic",
            {"E": 1.0e8},
        )
    }
    friction_models = {
        2: FrictionModelData(
            2,
            "PTFE",
            "Coulomb",
            {"mu": 0.05},
        )
    }
    dialog = TripleFrictionPendulumDialog(
        tag=10,
        node_i=1,
        node_j=2,
        materials=materials,
        friction_models=friction_models,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert [combo.currentData() for combo in dialog.friction] == [2, 2, 2]
        assert [combo.currentData() for combo in dialog.materials] == [1, 1, 1, 1]
        assert "force/length" in dialog.kvt.toolTip()
        assert "backward-compatible" in dialog.lengths["d1"].toolTip()
    finally:
        _close(dialog)



def test_friction_bearing_dialog_switches_formulation_and_2d_dependencies():
    materials = {
        1: MaterialData(1, "Axial", "Elastic", {"E": 1.0e8}),
        2: MaterialData(2, "Rotation", "Elastic", {"E": 1.0e8}),
    }
    friction_models = {
        3: FrictionModelData(3, "PTFE", "Coulomb", {"mu": 0.05}),
    }
    dialog = FrictionBearingDialog(
        tag=20,
        node_i=1,
        node_j=2,
        ndm=2,
        materials=materials,
        friction_models=friction_models,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert dialog.kind.currentData() == "flatSliderBearing"
        assert not dialog.reff.isEnabled()
        assert not dialog.mat_t.isEnabled()
        assert not dialog.mat_my.isEnabled()
        assert dialog.friction.currentData() == 3

        dialog.mat_p.setCurrentIndex(dialog.mat_p.findData(1))
        dialog.mat_mz.setCurrentIndex(dialog.mat_mz.findData(2))
        values = dialog.values()
        assert values[3] == "flatSliderBearing"
        assert "Reff" not in values[5]
        assert values[5]["t_mat_tag"] is None
        assert values[5]["my_mat_tag"] is None

        single = dialog.kind.findData("singleFPBearing")
        dialog.kind.setCurrentIndex(single)
        _APP.processEvents()
        assert dialog.reff.isEnabled()
        values = dialog.values()
        assert values[3] == "singleFPBearing"
        assert values[5]["Reff"] == pytest.approx(2.5)
        assert "spherical sliding surface" in dialog.note.text()
    finally:
        _close(dialog)


def test_friction_bearing_dialog_3d_requires_torsion_and_my_materials():
    materials = {
        1: MaterialData(1, "Elastic", "Elastic", {"E": 1.0e8}),
    }
    friction_models = {
        2: FrictionModelData(2, "PTFE", "Coulomb", {"mu": 0.05}),
    }
    dialog = FrictionBearingDialog(
        tag=21,
        node_i=1,
        node_j=2,
        ndm=3,
        materials=materials,
        friction_models=friction_models,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert dialog.friction.currentData() == 2
        assert dialog.mat_p.currentData() == 1
        assert dialog.mat_t.currentData() == 1
        assert dialog.mat_my.currentData() == 1
        assert dialog.mat_mz.currentData() == 1
        assert dialog.mat_t.isEnabled()
        assert dialog.mat_my.isEnabled()

        values = dialog.values()
        assert values[5]["p_mat_tag"] == 1
        assert values[5]["t_mat_tag"] == 1
        assert values[5]["my_mat_tag"] == 1
        assert values[5]["mz_mat_tag"] == 1
        assert "3D/6DOF" in dialog.note.text()
    finally:
        _close(dialog)


def test_friction_bearing_dialog_rejects_parallel_orientation():
    material = MaterialData(1, "Elastic", "Elastic", {"E": 1.0e8})
    friction = FrictionModelData(1, "PTFE", "Coulomb", {"mu": 0.05})
    dialog = FrictionBearingDialog(
        tag=22,
        node_i=1,
        node_j=2,
        ndm=3,
        materials={1: material},
        friction_models={1: friction},
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        dialog.custom_orientation.setChecked(True)
        for widget, value in zip(
            dialog.orientation,
            (1.0, 0.0, 0.0, 2.0, 0.0, 0.0),
        ):
            widget.setValue(value)
        with pytest.raises(ValueError, match="non-zero and non-parallel"):
            dialog.values()
    finally:
        _close(dialog)

def test_friction_bearing_dialog_exposes_dependency_roles_and_counts():
    materials = {
        1: MaterialData(1, "Axial", "Elastic", {"E": 1.0e8}),
        2: MaterialData(2, "Rotation", "Elastic", {"E": 1.0e8}),
    }
    friction_models = {
        3: FrictionModelData(3, "PTFE", "Coulomb", {"mu": 0.05}),
    }
    dialog = FrictionBearingDialog(
        tag=23,
        node_i=1,
        node_j=2,
        ndm=3,
        materials=materials,
        friction_models=friction_models,
        units={"length": "m", "force": "N", "time": "s"},
    )
    try:
        assert "frnMdlTag" in dialog.friction.toolTip()
        assert "OpenSees -P" in dialog.mat_p.toolTip()
        assert "OpenSees -T" in dialog.mat_t.toolTip()
        assert "OpenSees -My" in dialog.mat_my.toolTip()
        assert "OpenSees -Mz" in dialog.mat_mz.toolTip()
        assert "1 friction model(s)" in dialog.note.text()
        assert "2 uniaxial material(s)" in dialog.note.text()
    finally:
        _close(dialog)


def test_friction_bearing_dialog_keeps_missing_references_visible_for_repair():
    class _Element:
        tag = 24
        i = 1
        j = 2
        group = "isolation"
        element_type = "flatSliderBearing"
        special_parameters = {
            "frn_model_tag": 91,
            "kInit": 2.0e7,
            "p_mat_tag": 92,
            "mz_mat_tag": 93,
        }

    dialog = FrictionBearingDialog(
        tag=24,
        node_i=1,
        node_j=2,
        ndm=2,
        materials={},
        friction_models={},
        units={"length": "m", "force": "N", "time": "s"},
        element=_Element(),
    )
    try:
        assert dialog.friction.currentData() == 91
        assert "missing reference" in dialog.friction.currentText()
        assert dialog.mat_p.currentData() == 92
        assert "missing reference" in dialog.mat_p.currentText()
        assert dialog.mat_mz.currentData() == 93
        assert "missing reference" in dialog.mat_mz.currentText()
    finally:
        _close(dialog)

