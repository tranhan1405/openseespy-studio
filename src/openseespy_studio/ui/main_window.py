from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
)

from ..generator import FrameGridSpec, generate_frame_grid, to_openseespy
from ..model import StructuralModel
from .frame_grid_dialog import FrameGridDialog
from .viewport import ModelViewport


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenSeesPy Studio (MVP)")
        self.resize(1500, 900)
        self.model = StructuralModel("3D_Frame")
        self._build_ui()
        self._create_default_model()

    def _build_ui(self) -> None:
        self.viewport = ModelViewport(self)
        self.setCentralWidget(self.viewport)
        self._build_tree()
        self._build_properties()
        self._build_bottom()
        self._build_actions()
        self.statusBar().showMessage("Ready")

    def _build_tree(self) -> None:
        dock = QDockWidget("Model Tree", self)
        dock.setObjectName("ModelTreeDock")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_properties(self) -> None:
        dock = QDockWidget("Properties", self)
        dock.setObjectName("PropertiesDock")
        self.properties = QTableWidget(0, 2)
        self.properties.horizontalHeader().hide()
        self.properties.verticalHeader().hide()
        self.properties.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        dock.setWidget(self.properties)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _build_bottom(self) -> None:
        dock = QDockWidget("Console / Python", self)
        dock.setObjectName("BottomDock")
        tabs = QTabWidget()
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.script = QPlainTextEdit()
        self.script.setFont(QFont("Consolas", 10))
        tabs.addTab(self.console, "Message")
        tabs.addTab(self.script, "Python Script")
        dock.setWidget(tabs)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        geometry_menu = self.menuBar().addMenu("Geometry")
        view_menu = self.menuBar().addMenu("View")
        analysis_menu = self.menuBar().addMenu("Analysis")

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        new_action = QAction("New", self)
        new_action.triggered.connect(self._new_model)

        save_action = QAction("Export .py", self)
        save_action.triggered.connect(self._export_script)

        grid_action = QAction("Frame Grid", self)
        grid_action.triggered.connect(self._frame_grid)

        run_action = QAction("Run", self)
        run_action.triggered.connect(self._run_generated_model)

        for action in (new_action, save_action):
            file_menu.addAction(action)
        geometry_menu.addAction(grid_action)
        analysis_menu.addAction(run_action)

        toolbar.addAction(new_action)
        toolbar.addAction(save_action)
        toolbar.addSeparator()
        toolbar.addAction(grid_action)
        toolbar.addSeparator()

        for label, view in (
            ("XY", "xy"),
            ("XZ", "xz"),
            ("YZ", "yz"),
            ("ISO", "iso"),
        ):
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, v=view: self.viewport.set_view(v)
            )
            view_menu.addAction(action)
            toolbar.addAction(action)

        toolbar.addSeparator()
        toolbar.addAction(run_action)

    def _create_default_model(self) -> None:
        generate_frame_grid(self.model, FrameGridSpec(nx=4, ny=3, nz=3))
        self._refresh_all("Generated default 4 × 3 bay, 3-storey frame")

    def _new_model(self) -> None:
        self.model.clear()
        self._refresh_all("New empty model")

    def _frame_grid(self) -> None:
        dialog = FrameGridDialog(self)
        if dialog.exec():
            generate_frame_grid(self.model, dialog.spec())
            self._refresh_all("Frame grid generated")

    def _refresh_all(self, message: str = "") -> None:
        self.viewport.draw_model(self.model)
        self._refresh_tree()
        self.script.setPlainText(to_openseespy(self.model))
        if message:
            self._log(message)
        self.statusBar().showMessage(
            f"Nodes: {len(self.model.nodes)}   "
            f"Elements: {len(self.model.elements)}"
        )

    def _refresh_tree(self) -> None:
        self.tree.clear()

        root = QTreeWidgetItem(["OpenSees Model"])
        geometry = QTreeWidgetItem(["Geometry"])
        nodes = QTreeWidgetItem([f"Nodes ({len(self.model.nodes)})"])
        elements = QTreeWidgetItem([f"Elements ({len(self.model.elements)})"])

        mats = QTreeWidgetItem(["Materials (MVP)"])
        sections = QTreeWidgetItem(["Sections (MVP)"])
        fixed_count = sum(any(n.fixity) for n in self.model.nodes.values())
        bcs = QTreeWidgetItem([f"Boundary Conditions ({fixed_count})"])
        loads = QTreeWidgetItem(["Load Patterns (MVP)"])
        analysis = QTreeWidgetItem(["Analysis"])
        results = QTreeWidgetItem(["Results"])

        geometry.addChild(nodes)
        geometry.addChild(elements)
        root.addChild(geometry)

        for item in (mats, sections, bcs, loads, analysis, results):
            root.addChild(item)

        for tag in sorted(self.model.nodes):
            item = QTreeWidgetItem([f"Node {tag}"])
            item.setData(0, Qt.UserRole, ("node", tag))
            nodes.addChild(item)

        for tag in sorted(self.model.elements):
            e = self.model.elements[tag]
            item = QTreeWidgetItem([f"Element {tag} [{e.group}]"])
            item.setData(0, Qt.UserRole, ("element", tag))
            elements.addChild(item)

        self.tree.addTopLevelItem(root)
        root.setExpanded(True)
        geometry.setExpanded(True)

    def _tree_selection_changed(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return

        payload = items[0].data(0, Qt.UserRole)
        if not payload:
            return

        kind, tag = payload
        if kind == "node":
            node = self.model.nodes[tag]
            self._set_properties([
                ("Entity", "Node"),
                ("Tag", tag),
                ("X", node.xyz[0]),
                ("Y", node.xyz[1]),
                ("Z", node.xyz[2]),
                ("Fixity", str(node.fixity)),
            ])
        elif kind == "element":
            element = self.model.elements[tag]
            self._set_properties([
                ("Entity", "Element"),
                ("Tag", tag),
                ("Type", element.element_type),
                ("Node I", element.i),
                ("Node J", element.j),
                ("Group", element.group),
            ])

    def _set_properties(self, rows: list[tuple[str, object]]) -> None:
        self.properties.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.properties.setItem(row, 0, QTableWidgetItem(str(key)))
            self.properties.setItem(row, 1, QTableWidgetItem(str(value)))

    def _export_script(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export OpenSeesPy script",
            "model.py",
            "Python (*.py)",
        )
        if not path:
            return

        Path(path).write_text(
            self.script.toPlainText(),
            encoding="utf-8",
        )
        self._log(f"Exported: {path}")

    def _run_generated_model(self) -> None:
        try:
            import openseespy.opensees as ops  # noqa: F401
        except ImportError:
            QMessageBox.warning(
                self,
                "OpenSeesPy missing",
                "Install dependencies first: pip install -r requirements.txt",
            )
            return

        scope = {}
        try:
            exec(self.script.toPlainText(), scope, scope)
            self._log("OpenSeesPy model executed successfully")
        except Exception as exc:
            self._log(f"ERROR: {type(exc).__name__}: {exc}")
            QMessageBox.critical(self, "Execution error", str(exc))

    def _log(self, text: str) -> None:
        self.console.appendPlainText(">> " + text)
