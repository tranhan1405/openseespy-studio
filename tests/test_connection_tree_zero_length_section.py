from __future__ import annotations

import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidget

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ConnectionData,
    ProjectDatabase,
    SectionData,
    SUPPORTED_CONNECTION_TYPES,
)
from openseespy_studio.ui.main_window import MainWindow


_APP = QApplication.instance() or QApplication([])


def _find_payload(tree: QTreeWidget, payload):
    def visit(item):
        if item.data(0, Qt.UserRole) == payload:
            return item
        for index in range(item.childCount()):
            found = visit(item.child(index))
            if found is not None:
                return found
        return None

    for index in range(tree.topLevelItemCount()):
        found = visit(tree.topLevelItem(index))
        if found is not None:
            return found
    return None


def test_supported_connection_catalog_includes_zero_length_section():
    assert "zeroLengthSection" in SUPPORTED_CONNECTION_TYPES


def test_model_tree_refresh_handles_zero_length_section_connection():
    model = StructuralModel("MomentCurvature", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)

    project = ProjectDatabase(name="MomentCurvature", model=model)
    project.add_section(
        SectionData(
            1,
            "Imported Fiber 1",
            "Fiber",
            parameters={"GJ": 1.0e6},
        )
    )
    project.add_connection(
        ConnectionData(
            1,
            "Imported zeroLengthSection 1",
            "zeroLengthSection",
            1,
            2,
            section_tag=1,
        )
    )

    holder = SimpleNamespace(
        tree=QTreeWidget(),
        project=project,
        model=model,
        _tree_node_items={},
        _tree_element_items={},
        _jobs={},
    )
    holder._tree_item_state_key = MainWindow._tree_item_state_key
    holder._capture_tree_expansion_state = MethodType(
        MainWindow._capture_tree_expansion_state,
        holder,
    )
    holder._restore_tree_expansion_state = MethodType(
        MainWindow._restore_tree_expansion_state,
        holder,
    )

    MainWindow._refresh_tree(holder)

    elements_root = _find_payload(
        holder.tree,
        ("elements_root", None),
    )
    assert elements_root is not None
    assert elements_root.text(0) == "Elements (1)"

    group = _find_payload(
        holder.tree,
        ("connection_group", "zeroLengthSection"),
    )
    assert group is not None
    assert group.parent() is elements_root
    assert group.text(0) == "zeroLengthSection (1)"
    assert group.childCount() == 1
    assert group.child(0).text(0).startswith("Element 1")
    assert group.child(0).data(0, Qt.UserRole) == ("connection", 1)
