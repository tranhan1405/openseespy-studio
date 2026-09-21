from __future__ import annotations

import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidget

from openseespy_studio.model import StructuralModel
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase
from openseespy_studio.ui.main_window import MainWindow, PropertiesPanel


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


def _project_with_cyclic(targets: list[float]) -> ProjectDatabase:
    model = StructuralModel("Cyclic tree", ndm=2, ndf=3)
    model.add_node(4, 0.0, 0.0)
    project = ProjectDatabase(name="Cyclic tree", model=model)
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Column cyclic",
            analysis_type="Cyclic",
            control_node=4,
            control_dof=1,
            cyclic_targets=targets,
            cyclic_increment=0.25,
            recovery=False,
        )
    )
    return project


def test_cyclic_protocol_is_one_compact_model_tree_item():
    project = _project_with_cyclic([-1.0, 1.0, -2.0, 2.0, 0.0])
    holder = _holder(project)

    MainWindow._refresh_tree(holder)

    protocol = _find_payload(
        holder.tree,
        ("analysis_cyclic_protocol", 1),
    )
    assert protocol is not None
    assert protocol.text(0) == "Cyclic Protocol (5 targets)"
    assert protocol.childCount() == 0


def test_long_cyclic_protocol_does_not_expand_targets_in_tree():
    project = _project_with_cyclic(
        [float(value) for value in range(100)]
    )
    holder = _holder(project)

    MainWindow._refresh_tree(holder)

    protocol = _find_payload(
        holder.tree,
        ("analysis_cyclic_protocol", 1),
    )
    assert protocol is not None
    assert protocol.text(0) == "Cyclic Protocol (100 targets)"
    assert protocol.childCount() == 0


def test_cyclic_protocol_properties_use_table_and_plot():
    settings = _project_with_cyclic(
        [-1.0, 1.0, -2.0, 2.0, 0.0]
    ).analyses[1]
    panel = PropertiesPanel()

    panel.set_cyclic_protocol(settings)

    assert panel.entity_label.text() == "Cyclic Protocol"
    assert panel.cyclic_protocol_view.isHidden() is False
    assert panel.table.isHidden() is True
    assert panel.cyclic_protocol_table.rowCount() == 5
    assert panel.cyclic_protocol_table.item(0, 0).text() == "1"
    assert panel.cyclic_protocol_table.item(0, 1).text() == "-1"
    assert panel.cyclic_protocol_table.item(4, 1).text() == "0"
    assert panel.cyclic_protocol_preview._targets == [
        0.0,
        -1.0,
        1.0,
        -2.0,
        2.0,
        0.0,
    ]
    assert "Node 4" in panel.cyclic_protocol_summary.text()
    assert "DOF 1" in panel.cyclic_protocol_summary.text()
