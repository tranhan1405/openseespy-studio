from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..generator import FrameGridSpec, generate_frame_grid, to_openseespy
from ..model import StructuralModel
from .icons import studio_icon
from .viewport import ModelViewport


APP_STYLE = """
QMainWindow {
    background: #eaf0f6;
    color: #23364a;
}
QMenuBar {
    background: #fbfcfe;
    color: #23364a;
    border-bottom: 1px solid #c9d4df;
    padding: 2px 4px;
}
QMenuBar::item {
    padding: 6px 10px;
    margin: 0 1px;
    background: transparent;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background: #dfeeff;
    color: #1659a7;
}
QToolBar {
    background: #f8fafc;
    border: none;
    border-bottom: 1px solid #c7d2de;
    spacing: 3px;
    padding: 5px 6px;
}
QToolBar::separator {
    background: #c9d4df;
    width: 1px;
    margin: 4px 6px;
}
QToolBar QToolButton {
    min-width: 52px;
    min-height: 48px;
    padding: 4px 6px;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #2c4055;
}
QToolBar QToolButton:hover {
    background: #e1efff;
    border-color: #b7d2f3;
    color: #14589e;
}
QToolBar QToolButton:pressed,
QToolBar QToolButton:checked {
    background: #cfe5ff;
    border-color: #6fa8e8;
    color: #0f4f91;
}
QDockWidget {
    color: #22364b;
    font-weight: 600;
}
QDockWidget::title {
    background: #e8eef5;
    border: 1px solid #c9d4df;
    padding: 7px 9px;
    text-align: left;
}
QTreeWidget, QTableWidget, QPlainTextEdit {
    background: #ffffff;
    color: #25384b;
    border: 1px solid #cbd5df;
    selection-background-color: #2f80ed;
    selection-color: #ffffff;
}
QTreeWidget {
    padding: 4px;
    alternate-background-color: #f7faff;
}
QTreeWidget::item {
    min-height: 22px;
    padding: 2px 3px;
    border-radius: 2px;
}
QTreeWidget::item:hover {
    background: #eaf3ff;
    color: #1b5fa9;
}
QTreeWidget::item:selected {
    background: #2f80ed;
    color: #ffffff;
}
QTableWidget {
    gridline-color: #e0e7ef;
}
QHeaderView::section {
    background: #eef3f8;
    color: #2c4055;
    border: none;
    border-right: 1px solid #d6dee7;
    border-bottom: 1px solid #d6dee7;
    padding: 5px;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #c8d3de;
    background: #ffffff;
}
QTabBar::tab {
    background: #e8eef5;
    color: #516477;
    border: 1px solid #c8d3de;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 1px;
}
QTabBar::tab:hover {
    background: #edf5ff;
    color: #1c62aa;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1a5fa8;
    border-top: 3px solid #2f80ed;
    padding-top: 5px;
    font-weight: 600;
}
QGroupBox {
    font-weight: 600;
    color: #2d4359;
    background: #fbfcfe;
    border: 1px solid #ccd7e2;
    border-radius: 5px;
    margin-top: 12px;
    padding-top: 9px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 9px;
    padding: 0 5px;
    color: #234b72;
    background: #fbfcfe;
}
QSpinBox, QDoubleSpinBox, QComboBox {
    min-height: 26px;
    color: #24384c;
    border: 1px solid #b9c7d5;
    border-radius: 4px;
    background: #ffffff;
    padding: 2px 6px;
}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
    border-color: #7eaee2;
}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #2f80ed;
    background: #fbfdff;
}
QCheckBox {
    color: #2c4055;
    spacing: 7px;
}
QPushButton {
    min-height: 29px;
    color: #2c4055;
    border: 1px solid #b9c7d5;
    border-radius: 4px;
    background: #f9fbfd;
    padding: 4px 11px;
}
QPushButton:hover {
    background: #e9f3ff;
    border-color: #86b4e7;
    color: #155a9e;
}
QPushButton:checked {
    background: #2f80ed;
    border-color: #2f80ed;
    color: #ffffff;
    font-weight: 600;
}
QPushButton:disabled {
    color: #9aa8b6;
    background: #eef2f6;
    border-color: #d6dee7;
}
QPushButton#PrimaryButton {
    background: #2f80ed;
    border-color: #2f80ed;
    color: #ffffff;
    font-weight: 700;
    min-width: 96px;
}
QPushButton#PrimaryButton:hover {
    background: #1f6fd1;
    border-color: #1f6fd1;
}
QLabel#PanelTitle {
    font-size: 15px;
    font-weight: 700;
    color: #183e65;
}
QLabel#Muted {
    color: #718296;
}
QStatusBar {
    background: #f8fafc;
    color: #44576a;
    border-top: 1px solid #c9d4df;
}
QStatusBar QLabel {
    padding: 0 4px;
}
"""


class FrameGridPanel(QWidget):
    def __init__(self, generate_callback, parent=None):
        super().__init__(parent)
        self.generate_callback = generate_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Create Frame Grid")
        title.setObjectName("PanelTitle")
        subtitle = QLabel("Generate a regular 3D structural frame.")
        subtitle.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        mode_row = QHBoxLayout()
        self.rectangular = QPushButton("Rectangular Grid")
        self.rectangular.setCheckable(True)
        self.rectangular.setChecked(True)
        self.circular = QPushButton("Circular Grid")
        self.circular.setEnabled(False)
        mode_row.addWidget(self.rectangular)
        mode_row.addWidget(self.circular)
        layout.addLayout(mode_row)

        geometry = QGroupBox("Grid Geometry")
        form = QFormLayout(geometry)
        self.nx = self._int_spin(4)
        self.dx = self._float_spin(5.0)
        self.ny = self._int_spin(3)
        self.dy = self._float_spin(6.0)
        self.nz = self._int_spin(3)
        self.dz = self._float_spin(3.5)
        form.addRow("X bays", self.nx)
        form.addRow("X bay width (m)", self.dx)
        form.addRow("Y bays", self.ny)
        form.addRow("Y bay width (m)", self.dy)
        form.addRow("Storeys", self.nz)
        form.addRow("Storey height (m)", self.dz)
        layout.addWidget(geometry)

        members = QGroupBox("Members")
        members_layout = QVBoxLayout(members)
        self.columns = QCheckBox("Create columns")
        self.beams_x = QCheckBox("Create beams in X")
        self.beams_y = QCheckBox("Create beams in Y")
        for checkbox in (self.columns, self.beams_x, self.beams_y):
            checkbox.setChecked(True)
            members_layout.addWidget(checkbox)
        layout.addWidget(members)

        assignment = QGroupBox("Assignment")
        assign_form = QFormLayout(assignment)
        self.column_section = QComboBox()
        self.column_section.addItems(["1 - Column Section (placeholder)"])
        self.beam_section = QComboBox()
        self.beam_section.addItems(["2 - Beam Section (placeholder)"])
        assign_form.addRow("Column section", self.column_section)
        assign_form.addRow("Beam section", self.beam_section)
        layout.addWidget(assignment)

        tags = QGroupBox("Tags")
        tags_form = QFormLayout(tags)
        self.node_tag = self._int_spin(1, 1, 10_000_000)
        self.element_tag = self._int_spin(1, 1, 10_000_000)
        tags_form.addRow("Start node tag", self.node_tag)
        tags_form.addRow("Start element tag", self.element_tag)
        layout.addWidget(tags)

        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        generate = QPushButton("Generate")
        generate.setObjectName("PrimaryButton")
        generate.clicked.connect(self._generate)
        button_row.addWidget(generate)
        layout.addLayout(button_row)

    @staticmethod
    def _int_spin(value: int, low: int = 1, high: int = 100) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(low, high)
        widget.setValue(value)
        return widget

    @staticmethod
    def _float_spin(value: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(0.001, 1_000_000.0)
        widget.setDecimals(3)
        widget.setValue(value)
        return widget

    def _generate(self) -> None:
        spec = FrameGridSpec(
            nx=self.nx.value(),
            ny=self.ny.value(),
            nz=self.nz.value(),
            dx=self.dx.value(),
            dy=self.dy.value(),
            dz=self.dz.value(),
            start_node_tag=self.node_tag.value(),
            start_element_tag=self.element_tag.value(),
            create_columns=self.columns.isChecked(),
            create_beams_x=self.beams_x.isChecked(),
            create_beams_y=self.beams_y.isChecked(),
        )
        self.generate_callback(spec)


class PropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.title = QLabel("Properties")
        self.title.setObjectName("PanelTitle")
        self.subtitle = QLabel("Select an entity in the model tree.")
        self.subtitle.setObjectName("Muted")
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def set_properties(self, entity_title: str, rows: list[tuple[str, object]]) -> None:
        self.title.setText(entity_title)
        self.subtitle.setText("Entity information")
        self.table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.table.setItem(row, 1, QTableWidgetItem(str(value)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenSeesPy Studio (Alpha)")
        self.resize(1600, 960)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(APP_STYLE)

        self.model = StructuralModel("3D_Frame")
        self.context_mode = "frame-grid"

        self._build_ui()
        self._create_default_model()

    def _build_ui(self) -> None:
        self.viewport = ModelViewport(self)
        self.setCentralWidget(self.viewport)

        self._build_tree()
        self._build_context_panel()
        self._build_bottom_panel()
        self._build_actions()
        self._build_status_bar()

    def _build_tree(self) -> None:
        dock = QDockWidget("Model Tree", self)
        dock.setObjectName("ModelTreeDock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMinimumWidth(250)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setIndentation(18)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)

        dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.model_tree_dock = dock

    def _build_context_panel(self) -> None:
        dock = QDockWidget("Create / Edit", self)
        dock.setObjectName("ContextDock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMinimumWidth(325)

        self.context_stack = QStackedWidget()
        self.frame_grid_panel = FrameGridPanel(self._generate_frame_grid)
        self.properties_panel = PropertiesPanel()
        self.context_stack.addWidget(self.frame_grid_panel)
        self.context_stack.addWidget(self.properties_panel)

        dock.setWidget(self.context_stack)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.context_dock = dock

    def _build_bottom_panel(self) -> None:
        dock = QDockWidget("Workspace", self)
        dock.setObjectName("BottomDock")
        dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        self.script = QPlainTextEdit()
        self.script.setFont(QFont("Consolas", 10))
        self.script.setLineWrapMode(QPlainTextEdit.NoWrap)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))

        results = QWidget()
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(12, 12, 12, 12)
        result_header = QHBoxLayout()
        for label in ("Deformation", "Mode Shape", "Node Results", "Element Results"):
            button = QPushButton(label)
            button.setEnabled(False)
            result_header.addWidget(button)
        result_header.addStretch(1)
        results_layout.addLayout(result_header)

        empty_results = QLabel(
            "Results Viewer\n\nRun an analysis to populate deformation, mode shapes, "
            "nodal results and element results."
        )
        empty_results.setAlignment(Qt.AlignCenter)
        empty_results.setObjectName("Muted")
        results_layout.addWidget(empty_results, 1)

        tabs.addTab(self.script, "Python Script")
        tabs.addTab(self.console, "Console")
        tabs.addTab(results, "Results Viewer")

        dock.setWidget(tabs)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [185], Qt.Vertical)
        self.bottom_dock = dock

    def _build_actions(self) -> None:
        menus = {}
        for name in (
            "File", "Edit", "View", "Geometry", "Model", "Loads",
            "Analysis", "Results", "Tools", "Window", "Help",
        ):
            menus[name] = self.menuBar().addMenu(name)

        toolbar = QToolBar("CAE Tools")
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(26, 26))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        new_action = self._action(
            "New",
            "new",
            self._new_model,
            "Create a new model",
        )
        open_action = self._action(
            "Open",
            "open",
            self._not_implemented,
            "Open model (coming next)",
        )
        export_action = self._action(
            "Export",
            "save",
            self._export_script,
            "Export generated OpenSeesPy script",
        )
        undo_action = self._action(
            "Undo",
            "undo",
            self._not_implemented,
            "Undo (coming next)",
        )
        redo_action = self._action(
            "Redo",
            "redo",
            self._not_implemented,
            "Redo (coming next)",
        )

        for action in (new_action, open_action, export_action):
            menus["File"].addAction(action)
        menus["Edit"].addActions([undo_action, redo_action])

        for action in (new_action, open_action, export_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(undo_action)
        toolbar.addAction(redo_action)
        toolbar.addSeparator()

        node_action = self._action(
            "Node",
            "node",
            self._not_implemented,
            "Create node by GUI (next milestone)",
        )
        element_action = self._action(
            "Element",
            "element",
            self._not_implemented,
            "Create element by GUI (next milestone)",
        )
        grid_action = self._action(
            "Frame Grid",
            "grid",
            self._show_frame_grid,
            "Create regular frame grid",
        )
        menus["Geometry"].addActions([node_action, element_action, grid_action])
        for action in (node_action, element_action, grid_action):
            toolbar.addAction(action)

        toolbar.addSeparator()
        for label, icon_name in (
            ("Copy", "copy"),
            ("Move", "move"),
            ("Rotate", "rotate"),
            ("Mirror", "mirror"),
            ("Delete", "delete"),
        ):
            action = self._action(
                label,
                icon_name,
                self._not_implemented,
                f"{label} geometry (coming next)",
            )
            toolbar.addAction(action)

        toolbar.addSeparator()
        for label, icon_name in (
            ("Select", "select"),
            ("Box", "box"),
            ("Polygon", "polygon"),
            ("By ID", "by-id"),
        ):
            action = self._action(
                label,
                icon_name,
                self._not_implemented,
                f"{label} selection (coming next)",
            )
            toolbar.addAction(action)

        toolbar.addSeparator()
        for label, view in (
            ("XY", "xy"),
            ("XZ", "xz"),
            ("YZ", "yz"),
            ("ISO", "iso"),
        ):
            action = self._action(
                label,
                view,
                lambda checked=False, v=view: self.viewport.set_view(v),
                f"Set {label} view",
            )
            menus["View"].addAction(action)
            toolbar.addAction(action)

        fit_action = self._action(
            "Fit",
            "fit",
            self.viewport.fit_view,
            "Fit model in viewport",
        )
        toolbar.addAction(fit_action)

        toolbar.addSeparator()
        run_action = self._action(
            "Run",
            "run",
            self._run_generated_model,
            "Execute generated OpenSeesPy model",
        )
        plot_action = self._action(
            "Plot",
            "plot",
            self._not_implemented,
            "Post-processing plots (coming later)",
        )
        menus["Analysis"].addAction(run_action)
        menus["Results"].addAction(plot_action)
        toolbar.addAction(run_action)
        toolbar.addAction(plot_action)

    def _build_status_bar(self) -> None:
        self.status_message = QLabel("Ready")
        self.status_units = QLabel("Units: m, kN, s")
        self.status_view = QLabel("View: 3D")
        self.status_counts = QLabel("Nodes: 0   Elements: 0")

        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self._status_separator())
        self.statusBar().addPermanentWidget(self.status_units)
        self.statusBar().addPermanentWidget(self._status_separator())
        self.statusBar().addPermanentWidget(self.status_view)
        self.statusBar().addPermanentWidget(self._status_separator())
        self.statusBar().addPermanentWidget(self.status_counts)

    @staticmethod
    def _status_separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _action(self, text, icon_name, callback, tooltip) -> QAction:
        action = QAction(studio_icon(icon_name), text, self)
        action.setToolTip(tooltip)
        action.triggered.connect(callback)
        return action

    def _create_default_model(self) -> None:
        generate_frame_grid(self.model, FrameGridSpec(nx=4, ny=3, nz=3))
        self._refresh_all("Generated default 4 × 3 bay, 3-storey frame")
        self._show_frame_grid()

    def _new_model(self) -> None:
        self.model.clear()
        self._refresh_all("New empty model")
        self._show_frame_grid()

    def _show_frame_grid(self) -> None:
        self.context_mode = "frame-grid"
        self.context_dock.setWindowTitle("Create / Edit")
        self.context_stack.setCurrentWidget(self.frame_grid_panel)

    def _show_properties(self) -> None:
        self.context_mode = "properties"
        self.context_dock.setWindowTitle("Properties")
        self.context_stack.setCurrentWidget(self.properties_panel)

    def _generate_frame_grid(self, spec: FrameGridSpec) -> None:
        generate_frame_grid(self.model, spec)
        self._refresh_all(
            f"Generated {spec.nx} × {spec.ny} bay, {spec.nz}-storey frame"
        )

    def _refresh_all(self, message: str = "") -> None:
        self.viewport.draw_model(self.model)
        self.viewport.set_model_info(
            self.model.name,
            len(self.model.nodes),
            len(self.model.elements),
        )
        self._refresh_tree()
        self.script.setPlainText(to_openseespy(self.model))

        if message:
            self._log(message)
            self.status_message.setText(message)

        self.status_counts.setText(
            f"Nodes: {len(self.model.nodes)}   Elements: {len(self.model.elements)}"
        )

    def _refresh_tree(self) -> None:
        self.tree.clear()

        root = QTreeWidgetItem(["OpenSees Model"])
        root.setIcon(0, studio_icon("model"))
        root.setExpanded(True)

        geometry = QTreeWidgetItem(["Geometry"])
        geometry.setIcon(0, studio_icon("grid"))
        geometry.setExpanded(True)
        nodes = QTreeWidgetItem([f"Nodes ({len(self.model.nodes)})"])
        nodes.setIcon(0, studio_icon("node"))
        elements = QTreeWidgetItem([f"Elements ({len(self.model.elements)})"])
        elements.setIcon(0, studio_icon("element"))
        geometry.addChild(nodes)
        geometry.addChild(elements)
        root.addChild(geometry)

        element_groups: dict[str, QTreeWidgetItem] = {}
        for group in ("column", "beam-x", "beam-y"):
            count = sum(e.group == group for e in self.model.elements.values())
            child = QTreeWidgetItem([f"{group} ({count})"])
            child.setIcon(0, studio_icon("element"))
            element_groups[group] = child
            elements.addChild(child)

        for tag in sorted(self.model.nodes):
            item = QTreeWidgetItem([f"Node {tag}"])
            item.setIcon(0, studio_icon("node"))
            item.setData(0, Qt.UserRole, ("node", tag))
            nodes.addChild(item)

        for tag in sorted(self.model.elements):
            element = self.model.elements[tag]
            item = QTreeWidgetItem([f"Element {tag}"])
            item.setIcon(0, studio_icon("element"))
            item.setData(0, Qt.UserRole, ("element", tag))
            element_groups.get(element.group, elements).addChild(item)

        fixed_count = sum(any(n.fixity) for n in self.model.nodes.values())

        categories = (
            ("Materials (0)", "material"),
            ("Sections (0)", "section"),
            ("Transformations (0)", "transform"),
            (f"Boundary Conditions ({fixed_count})", "boundary"),
            ("Time Series (0)", "timeseries"),
            ("Load Patterns (0)", "load"),
            ("Recorders (0)", "recorder"),
            ("Analysis", "analysis"),
            ("Results", "results"),
        )
        for label, icon_name in categories:
            item = QTreeWidgetItem([label])
            item.setIcon(0, studio_icon(icon_name))
            root.addChild(item)

        self.tree.addTopLevelItem(root)

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
            connected = [
                e.tag
                for e in self.model.elements.values()
                if e.i == tag or e.j == tag
            ]
            self.properties_panel.set_properties(
                f"Node {tag}",
                [
                    ("Tag", tag),
                    ("Coordinates", node.xyz),
                    ("X", node.xyz[0]),
                    ("Y", node.xyz[1]),
                    ("Z", node.xyz[2]),
                    ("Fixity", node.fixity),
                    ("Connected elements", ", ".join(map(str, connected)) or "-"),
                ],
            )
        elif kind == "element":
            element = self.model.elements[tag]
            self.properties_panel.set_properties(
                f"Element {tag}",
                [
                    ("Tag", tag),
                    ("Type", element.element_type),
                    ("Node I", element.i),
                    ("Node J", element.j),
                    ("Group", element.group),
                    ("Section", element.section_tag or "-"),
                    ("Transformation", element.transf_tag or "-"),
                ],
            )

        self._show_properties()

    def _export_script(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export OpenSeesPy script",
            "model.py",
            "Python (*.py)",
        )
        if not path:
            return

        Path(path).write_text(self.script.toPlainText(), encoding="utf-8")
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
            self.status_message.setText("Analysis model executed successfully")
        except Exception as exc:
            self._log(f"ERROR: {type(exc).__name__}: {exc}")
            QMessageBox.critical(self, "Execution error", str(exc))

    def _not_implemented(self) -> None:
        action = self.sender()
        label = action.text() if isinstance(action, QAction) else "Command"
        self._log(f"{label}: planned for the next milestone")

    def _log(self, text: str) -> None:
        self.console.appendPlainText(">> " + text)
