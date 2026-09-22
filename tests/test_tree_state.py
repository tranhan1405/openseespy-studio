import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
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



def test_material_tree_menu_prioritizes_new_and_keeps_ai_last(monkeypatch):
    app = QApplication.instance() or QApplication([])

    item = QTreeWidgetItem(["Materials (0)"])
    item.setData(0, Qt.UserRole, ("materials_root", None))

    class _Viewport:
        @staticmethod
        def mapToGlobal(position):
            return QPoint(position)

    class _Tree:
        @staticmethod
        def itemAt(_position):
            return item

        @staticmethod
        def viewport():
            return _Viewport()

    class _Holder(QWidget):
        def __init__(self):
            super().__init__()
            self.tree = _Tree()

        def _create_material(self):
            pass

        def _show_material_library(self):
            pass

        def _ask_ai_about_tree_item(self, _kind, _value):
            pass

    captured = []

    def _capture_exec(menu, _position):
        captured.extend(
            action.text()
            for action in menu.actions()
            if not action.isSeparator()
        )

    monkeypatch.setattr(QMenu, "exec", _capture_exec)

    holder = _Holder()
    try:
        MainWindow._show_tree_context_menu(holder, QPoint(0, 0))
        assert captured == [
            "New Material...",
            "Insert from Material Library...",
            "Ask AI about this",
        ]
    finally:
        holder.close()
        holder.deleteLater()
        app.processEvents()
