import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from openseespy_studio.ui.main_window import MainWindow


def _item(text, payload, *, expanded=False):
    item = QTreeWidgetItem([text])
    item.setData(0, Qt.UserRole, payload)
    item.setExpanded(expanded)
    return item


def test_tree_expansion_state_survives_rebuild_and_count_changes():
    app = QApplication.instance() or QApplication([])
    tree = QTreeWidget()

    root = _item("OpenSees Model", ("model_root", None), expanded=True)
    elements = _item("Elements (2)", ("elements_root", None), expanded=False)
    truss = _item(
        "truss (2)",
        ("element_type_group", "truss"),
        expanded=True,
    )
    truss.addChild(_item("Element 1", ("element", 1)))
    truss.addChild(_item("Element 2", ("element", 2)))
    elements.addChild(truss)
    root.addChild(elements)
    tree.addTopLevelItem(root)
    # Expansion state is a view property in Qt; set it after insertion.
    root.setExpanded(True)
    elements.setExpanded(False)
    truss.setExpanded(True)

    holder = SimpleNamespace(tree=tree)
    holder._tree_item_state_key = MainWindow._tree_item_state_key

    state = MainWindow._capture_tree_expansion_state(holder)

    tree.clear()
    rebuilt_root = _item(
        "OpenSees Model",
        ("model_root", None),
        expanded=True,
    )
    rebuilt_elements = _item(
        "Elements (3)",
        ("elements_root", None),
        expanded=True,
    )
    rebuilt_truss = _item(
        "truss (3)",
        ("element_type_group", "truss"),
        expanded=False,
    )
    rebuilt_truss.addChild(_item("Element 1", ("element", 1)))
    rebuilt_truss.addChild(_item("Element 2", ("element", 2)))
    rebuilt_truss.addChild(_item("Element 3", ("element", 3)))
    rebuilt_elements.addChild(rebuilt_truss)
    rebuilt_root.addChild(rebuilt_elements)
    tree.addTopLevelItem(rebuilt_root)
    rebuilt_root.setExpanded(True)
    rebuilt_elements.setExpanded(True)
    rebuilt_truss.setExpanded(False)

    MainWindow._restore_tree_expansion_state(holder, state)

    assert rebuilt_root.isExpanded()
    assert not rebuilt_elements.isExpanded()
    assert rebuilt_truss.isExpanded()



def test_material_tree_menu_prioritizes_new_and_keeps_ai_last():
    app = QApplication.instance() or QApplication([])

    class _Holder(QWidget):
        def _create_material(self):
            pass

        def _show_material_library(self):
            pass

        def _ask_ai_about_tree_item(self, _kind, _value):
            pass

    holder = _Holder()
    menu = QMenu(holder)
    try:
        MainWindow._populate_materials_root_context_menu(
            holder,
            menu,
        )
        MainWindow._append_tree_ai_action(
            holder,
            menu,
            "materials_root",
            None,
        )

        labels = [
            action.text()
            for action in menu.actions()
            if not action.isSeparator()
        ]
        assert labels == [
            "New Material...",
            "Insert from Material Library...",
            "Ask AI about this",
        ]
    finally:
        menu.close()
        menu.deleteLater()
        holder.close()
        holder.deleteLater()
        app.processEvents()


def test_tree_selection_display_context_matches_mechanical_workflow():
    assert MainWindow._tree_selection_display_context(
        {"geometry_root"}
    ) == ("geometry", "Geometry")
    assert MainWindow._tree_selection_display_context(
        {"surface_geometry"}
    ) == ("geometry", "Geometry")

    # Mesh is a discretized FE context, not a CAD-only Geometry context.
    assert MainWindow._tree_selection_display_context(
        {"mesh_root"}
    ) == ("fe", "Model")
    assert MainWindow._tree_selection_display_context(
        {"surface_mesh_recipe"}
    ) == ("fe", "Model")

    assert MainWindow._tree_selection_display_context(
        {"fe_model_root"}
    ) == ("fe", "Model")
    assert MainWindow._tree_selection_display_context(
        {"analyses_root"}
    ) == ("fe", "Analysis")
    assert MainWindow._tree_selection_display_context(
        {"solution_root"}
    ) == ("fe", "Result")
    assert MainWindow._tree_selection_display_context(
        {"named_sets_root"}
    ) == ("fe", "Selection")

def test_model_and_geometry_roots_exit_result_display():
    assert MainWindow._tree_selection_resets_result_overlay(
        {"model_root"}
    )
    assert MainWindow._tree_selection_resets_result_overlay(
        {"geometry_root"}
    )
    assert not MainWindow._tree_selection_resets_result_overlay(
        {"mesh_root"}
    )
    assert not MainWindow._tree_selection_resets_result_overlay(
        {"solution_root"}
    )

