from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import NDMaterialData, TransformationData
from openseespy_studio.ui.isolation_contact_dialog import ContactElementDialog


_APP = QApplication.instance() or QApplication([])


def _combo_tags(combo):
    return {
        int(combo.itemData(index))
        for index in range(combo.count())
        if combo.itemData(index) is not None
    }


def _close(dialog: ContactElementDialog) -> None:
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
