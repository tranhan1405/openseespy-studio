from __future__ import annotations

import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidget

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase
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


def _holder(project: ProjectDatabase):
    holder = SimpleNamespace(
        tree=QTreeWidget(),
        project=project,
        model=project.model,
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
    return holder


def test_cyclic_protocol_is_visible_in_model_tree():
    model = StructuralModel("Cyclic tree", ndm=2, ndf=3)
    model.add_node(4, 0.0, 0.0)
    project = ProjectDatabase(
        name="Cyclic tree",
        model=model,
    )
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Column cyclic",
            analysis_type="Cyclic",
            control_node=4,
            control_dof=1,
            cyclic_targets=[-1.0, 1.0, -2.0, 2.0, 0.0],
            cyclic_increment=0.25,
            recovery=False,
        )
    )

    holder = _holder(project)
    MainWindow._refresh_tree(holder)

    protocol = _find_payload(
        holder.tree,
        ("analysis_cyclic_protocol", 1),
    )
    assert protocol is not None
    assert protocol.text(0) == "Cyclic Protocol (5 targets)"
    texts = [
        protocol.child(index).text(0)
        for index in range(protocol.childCount())
    ]
    assert "Control · Node 4 · DOF 1" in texts
    assert "Max increment · 0.25" in texts
    assert "Target 1 · -1" in texts
    assert "Target 5 · 0" in texts


def test_long_cyclic_protocol_is_collapsed_in_model_tree():
    model = StructuralModel("Long cyclic tree", ndm=2, ndf=3)
    model.add_node(4, 0.0, 0.0)
    project = ProjectDatabase(
        name="Long cyclic tree",
        model=model,
    )
    targets = [float(value) for value in range(100)]
    project.add_analysis(
        AnalysisSettingsData(
            7,
            "Imported long history",
            analysis_type="Cyclic",
            control_node=4,
            control_dof=1,
            cyclic_targets=targets,
            cyclic_increment=1.0,
            recovery=False,
        )
    )

    holder = _holder(project)
    MainWindow._refresh_tree(holder)

    protocol = _find_payload(
        holder.tree,
        ("analysis_cyclic_protocol", 7),
    )
    assert protocol is not None
    texts = [
        protocol.child(index).text(0)
        for index in range(protocol.childCount())
    ]
    assert "Target 1 · 0" in texts
    assert "Target 12 · 11" in texts
    assert "Target 97 · 96" in texts
    assert "Target 100 · 99" in texts
    assert "… 84 target(s) hidden in tree" in texts
    assert protocol.childCount() == 19
