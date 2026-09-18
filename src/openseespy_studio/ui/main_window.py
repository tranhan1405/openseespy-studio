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
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..generator import FrameGridSpec, generate_frame_grid, to_openseespy
from ..model import StructuralModel
from .code_editor import CodeEditor
from .icons import studio_icon
from .results_panel import ResultsPanel
from .viewport import ModelViewport


APP_STYLE = """
QMainWindow {
    background: #edf1f5;
    color: #23364a;
}
QMenuBar {
    background: #f7f8fa;
    color: #1f2f40;
    border-bottom: 1px solid #ccd4dd;
    padding: 1px 3px;
}
QMenuBar::item {
    padding: 5px 9px;
    background: transparent;
}
QMenuBar::item:selected {
    background: #e4edf8;
}
QToolBar#Ribbon {
    background: #f7f8fa;
    border: none;
    border-bottom: 1px solid #c9d1da;
    spacing: 0;
    padding: 3px 4px 0 4px;
}
QWidget#RibbonGroup {
    border-right: 1px solid #d5dbe2;
    background: transparent;
}
QLabel#RibbonCaption {
    color: #526273;
    font-size: 10px;
    padding: 1px 3px 2px 3px;
}
QToolButton#RibbonButton {
    color: #203247;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 3px 5px;
    min-width: 47px;
    min-height: 53px;
}
QToolButton#RibbonButton:hover {
    background: #e4effc;
    border-color: #b6cee9;
}
QToolButton#RibbonButton:pressed,
QToolButton#RibbonButton:checked {
    background: #d0e6ff;
    border-color: #7fb0e6;
}
QDockWidget {
    color: #203247;
    font-weight: 600;
}
QDockWidget::title {
    background: #f1f4f7;
    border: 1px solid #cbd3dc;
    padding: 6px 8px;
    text-align: left;
}
QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #cbd3dc;
}
QTabBar::tab {
    background: #edf1f5;
    color: #4b5e71;
    border: 1px solid #cbd3dc;
    border-bottom: none;
    padding: 6px 12px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #163f68;
    border-top: 2px solid #2f80ed;
    font-weight: 600;
}
QTreeWidget, QTableWidget, QPlainTextEdit {
    background: #ffffff;
    color: #23364a;
    border: 0;
    selection-background-color: #2f80ed;
    selection-color: #ffffff;
}
QTreeWidget {
    alternate-background-color: #fbfcfd;
    padding: 3px;
}
QTreeWidget::item {
    min-height: 21px;
    padding: 1px 2px;
}
QTreeWidget::item:hover {
    background: #e8f2fe;
}
QTableWidget {
    gridline-color: #e1e6ec;
}
QPushButton {
    min-height: 27px;
    border: 1px solid #bcc7d2;
    border-radius: 3px;
    background: #f8fafc;
    color: #26394c;
    padding: 3px 10px;
}
QPushButton:hover {
    background: #e9f3ff;
    border-color: #86b4e7;
}
QPushButton:checked {
    background: #dcecff;
    border-color: #79aee8;
    color: #14599d;
    font-weight: 600;
}
QPushButton#PrimaryButton {
    background: #1877d3;
    border-color: #1877d3;
    color: white;
    font-weight: 700;
    min-width: 92px;
}
QPushButton#PrimaryButton:hover {
    background: #0f68c2;
}
QPushButton#CloseButton {
    min-width: 86px;
}
QSpinBox, QDoubleSpinBox, QComboBox {
    min-height: 25px;
    border: 1px solid #bac6d2;
    border-radius: 3px;
    background: #ffffff;
    color: #25394c;
    padding: 1px 5px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #2f80ed;
}
QCheckBox {
    spacing: 6px;
    color: #263a4f;
}
QLabel#PanelTitle {
    font-size: 14px;
    font-weight: 700;
    color: #183e65;
}
QLabel#SectionTitle {
    font-size: 12px;
    font-weight: 700;
    color: #1f3348;
    padding-top: 4px;
}
QLabel#Muted {
    color: #718195;
}
QFrame#SectionLine {
    color: #d7dee6;
}
QStatusBar {
    background: #f7f8fa;
    color: #42566b;
    border-top: 1px solid #ccd4dd;
}
"""


class RibbonGroup(QWidget):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 1, 6, 0)
        layout.setSpacing(0)

        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(1)
        layout.addLayout(self.button_row)

        label = QLabel(caption)
        label.setObjectName("RibbonCaption")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    def add_action(self, action: QAction) -> None:
        button = QToolButton()
        button.setObjectName("RibbonButton")
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(25, 25))
        button.setAutoRaise(True)
        self.button_row.addWidget(button)


class FrameGridPanel(QWidget):
    def __init__(self, generate_callback, close_callback, parent=None):
        super().__init__(parent)
        self.generate_callback = generate_callback
        self.close_callback = close_callback

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 8)
        root.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        title = QLabel("Create Frame Grid")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        mode_row = QHBoxLayout()
        self.rectangular = QPushButton("Rectangular Grid")
        self.rectangular.setCheckable(True)
        self.rectangular.setChecked(True)
        self.circular = QPushButton("Circular Grid")
        self.circular.setEnabled(False)
        mode_row.addWidget(self.rectangular)
        mode_row.addWidget(self.circular)
        layout.addLayout(mode_row)

        self.nx = self._int_spin(4)
        self.dx = self._float_spin(5.0)
        self.ny = self._int_spin(3)
        self.dy = self._float_spin(6.0)
        self.nz = self._int_spin(3)
        self.dz = self._float_spin(3.5)

        self._add_section(layout, "X Direction (Bays)", [
            ("Number of bays", self.nx),
            ("Bay width (m)", self.dx),
        ])
        self._add_section(layout, "Y Direction (Bays)", [
            ("Number of bays", self.ny),
            ("Bay width (m)", self.dy),
        ])
        self._add_section(layout, "Z Direction (Storeys)", [
            ("Number of storeys", self.nz),
            ("Storey height (m)", self.dz),
        ])

        options_title = QLabel("Options")
        options_title.setObjectName("SectionTitle")
        layout.addWidget(options_title)
        self.columns = QCheckBox("Create columns")
        self.beams_x = QCheckBox("Create beams in X")
        self.beams_y = QCheckBox("Create beams in Y")
        for checkbox in (self.columns, self.beams_x, self.beams_y):
            checkbox.setChecked(True)
            layout.addWidget(checkbox)

        self.column_section = QComboBox()
        self.column_section.addItems(["1 - Column Section"])
        self.beam_section = QComboBox()
        self.beam_section.addItems(["2 - Beam Section"])
        assignment = QFormLayout()
        assignment.setContentsMargins(0, 2, 0, 0)
        assignment.addRow("Assign section (columns)", self.column_section)
        assignment.addRow("Assign section (beams)", self.beam_section)
        assign_widget = QWidget()
        assign_widget.setLayout(assignment)
        layout.addWidget(assign_widget)

        self.node_tag = self._int_spin(1, 1, 10_000_000)
        self.element_tag = self._int_spin(1, 1, 10_000_000)
        tags = QFormLayout()
        tags.setContentsMargins(0, 2, 0, 0)
        tags.addRow("Start node tag", self.node_tag)
        tags.addRow("Start element tag", self.element_tag)
        tags_widget = QWidget()
        tags_widget.setLayout(tags)
        layout.addWidget(tags_widget)

        layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        generate = QPushButton("Generate")
        generate.setObjectName("PrimaryButton")
        generate.clicked.connect(self._generate)
        close = QPushButton("Close")
        close.setObjectName("CloseButton")
        close.clicked.connect(self.close_callback)
        buttons.addWidget(generate)
        buttons.addWidget(close)
        root.addLayout(buttons)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("SectionLine")
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        return line

    def _add_section(self, parent_layout, title: str, rows) -> None:
        if parent_layout.count() > 2:
            parent_layout.addWidget(self._separator())
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        parent_layout.addWidget(label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(5)
        for text, widget in rows:
            form.addRow(text, widget)
        container = QWidget()
        container.setLayout(form)
        parent_layout.addWidget(container)

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
        self.generate_callback(FrameGridSpec(
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
        ))


class PropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 6)
        layout.setSpacing(4)

        self.entity_label = QLabel("Node")
        self.entity_label.setObjectName("PanelTitle")
        layout.addWidget(self.entity_label)

        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(True)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 115)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        apply_button = QPushButton("Apply")
        apply_button.setEnabled(False)
        row.addWidget(apply_button)
        layout.addLayout(row)

    def set_properties(self, title: str, rows: list[tuple[str, object]]) -> None:
        self.entity_label.setText(title)
        self.table.setRowCount(len(rows))
        for index, (key, value) in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(str(key)))
            self.table.setItem(index, 1, QTableWidgetItem(str(value)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenSeesPy Studio (Beta) - [Untitled]")
        self.resize(1536, 960)
        self.setMinimumSize(1150, 720)
        self.setStyleSheet(APP_STYLE)

        self.model = StructuralModel("3D_Frame")
        self.actions: dict[str, QAction] = {}

        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        self._build_central_view()
        self._build_model_tree_dock()
        self._build_properties_dock()
        self._build_create_dock()
        self._build_bottom_docks()
        self._build_actions_and_ribbon()
        self._build_status_bar()
        self._create_default_model()
        self._size_initial_docks()

    def _build_central_view(self) -> None:
        self.viewport = ModelViewport(self)
        self.setCentralWidget(self.viewport)

    def _build_model_tree_dock(self) -> None:
        dock = QDockWidget("Model Tree", self)
        dock.setObjectName("ModelTreeDock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        dock.setMinimumWidth(245)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIconSize(QSize(17, 17))
        self.tree.setIndentation(17)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)

        history = QLabel("Command history will appear here.")
        history.setAlignment(Qt.AlignCenter)
        history.setObjectName("Muted")

        tabs.addTab(self.tree, "Model Tree")
        tabs.addTab(history, "History")
        dock.setWidget(tabs)

        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.model_tree_dock = dock

    def _build_properties_dock(self) -> None:
        dock = QDockWidget("Properties", self)
        dock.setObjectName("PropertiesDock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        dock.setMinimumWidth(245)

        self.properties_panel = PropertiesPanel()
        dock.setWidget(self.properties_panel)

        self.splitDockWidget(self.model_tree_dock, dock, Qt.Vertical)
        self.properties_dock = dock

    def _build_create_dock(self) -> None:
        dock = QDockWidget("Create Frame Grid", self)
        dock.setObjectName("CreateDock")
        dock.setAllowedAreas(Qt.RightDockWidgetArea)
        dock.setMinimumWidth(315)

        self.frame_grid_panel = FrameGridPanel(
            self._generate_frame_grid,
            dock.hide,
        )
        dock.setWidget(self.frame_grid_panel)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.create_dock = dock

    def _build_bottom_docks(self) -> None:
        script_dock = QDockWidget("Python Script", self)
        script_dock.setObjectName("PythonDock")
        script_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.script = CodeEditor()
        script_dock.setWidget(self.script)
        self.addDockWidget(Qt.BottomDockWidgetArea, script_dock)

        console_dock = QDockWidget("Console", self)
        console_dock.setObjectName("ConsoleDock")
        console_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))
        console_dock.setWidget(self.console)
        self.splitDockWidget(script_dock, console_dock, Qt.Horizontal)

        results_dock = QDockWidget("Results Viewer", self)
        results_dock.setObjectName("ResultsDock")
        results_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.results_panel = ResultsPanel()
        results_dock.setWidget(self.results_panel)
        self.splitDockWidget(console_dock, results_dock, Qt.Horizontal)

        self.script_dock = script_dock
        self.console_dock = console_dock
        self.results_dock = results_dock

    def _make_action(
        self,
        key: str,
        text: str,
        icon_name: str,
        callback,
        tooltip: str,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(studio_icon(icon_name), text, self)
        action.setToolTip(tooltip)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        self.actions[key] = action
        return action

    def _build_actions_and_ribbon(self) -> None:
        menus = {}
        for name in (
            "File", "Edit", "View", "Geometry", "Model", "Loads",
            "Analysis", "Results", "Tools", "Window", "Help",
        ):
            menus[name] = self.menuBar().addMenu(name)

        self._make_action("new", "New", "new", self._new_model, "New model")
        self._make_action("open", "Open", "open", self._not_implemented, "Open model")
        self._make_action("save", "Save", "save", self._export_script, "Export OpenSeesPy script")
        self._make_action("undo", "Undo", "undo", self._not_implemented, "Undo")
        self._make_action("redo", "Redo", "redo", self._not_implemented, "Redo")

        self._make_action("node", "Node", "node", self._not_implemented, "Create node")
        self._make_action("line", "Line", "element", self._not_implemented, "Create line")
        self._make_action("frame", "Frame", "element", self._not_implemented, "Create frame element")
        self._make_action("grid", "Grid", "grid", self._show_frame_grid, "Create frame grid")
        self._make_action("extrude", "Extrude", "copy", self._not_implemented, "Extrude geometry")

        for key, label, icon in (
            ("copy", "Copy", "copy"),
            ("move", "Move", "move"),
            ("rotate", "Rotate", "rotate"),
            ("mirror", "Mirror", "mirror"),
            ("delete", "Delete", "delete"),
        ):
            self._make_action(key, label, icon, self._not_implemented, label)

        for key, label, icon in (
            ("select", "Select", "select"),
            ("box", "Box", "box"),
            ("polygon", "Polygon", "polygon"),
            ("byid", "By ID", "by-id"),
            ("bytype", "By Type", "by-id"),
        ):
            self._make_action(key, label, icon, self._not_implemented, label)

        for key, label, icon, view in (
            ("xy", "XY", "xy", "xy"),
            ("yz", "YZ", "yz", "yz"),
            ("xz", "XZ", "xz", "xz"),
            ("iso", "ISO", "iso", "iso"),
        ):
            self._make_action(
                key, label, icon,
                lambda checked=False, v=view: self.viewport.set_view(v),
                f"{label} view",
            )

        self._make_action("run", "Run", "run", self._run_generated_model, "Run model")
        self._make_action("plot", "Plot", "plot", self._not_implemented, "Plot results")

        menus["File"].addActions([
            self.actions["new"], self.actions["open"], self.actions["save"],
        ])
        menus["Edit"].addActions([self.actions["undo"], self.actions["redo"]])
        menus["Geometry"].addActions([
            self.actions["node"], self.actions["line"], self.actions["frame"],
            self.actions["grid"], self.actions["extrude"],
        ])
        menus["View"].addActions([
            self.actions["xy"], self.actions["yz"], self.actions["xz"], self.actions["iso"],
        ])
        menus["Analysis"].addAction(self.actions["run"])
        menus["Results"].addAction(self.actions["plot"])

        ribbon = QToolBar("Ribbon", self)
        ribbon.setObjectName("Ribbon")
        ribbon.setMovable(False)
        ribbon.setFloatable(False)
        self.addToolBar(Qt.TopToolBarArea, ribbon)

        groups = (
            ("File", ["new", "open", "save"]),
            ("Edit", ["undo", "redo"]),
            ("Geometry", ["node", "line", "frame", "grid", "extrude"]),
            ("Modify", ["copy", "move", "rotate", "mirror", "delete"]),
            ("Selection", ["select", "box", "polygon", "byid", "bytype"]),
            ("View", ["xy", "yz", "xz", "iso"]),
            ("Analysis", ["run", "plot"]),
        )

        for caption, keys in groups:
            group = RibbonGroup(caption)
            for key in keys:
                group.add_action(self.actions[key])
            ribbon.addWidget(group)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ribbon.addWidget(spacer)

        logo = QWidget()
        logo_layout = QHBoxLayout(logo)
        logo_layout.setContentsMargins(12, 2, 10, 2)
        mark = QLabel("∿")
        mark.setStyleSheet("font-size: 32px; font-weight: 700; color: #c62828;")
        title = QLabel("<b>OpenSeesPy Studio</b><br><span style='color:#6d7b89'>Model · Analyze · Visualize</span>")
        logo_layout.addWidget(mark)
        logo_layout.addWidget(title)
        ribbon.addWidget(logo)

    def _build_status_bar(self) -> None:
        self.status_message = QLabel("Ready")
        self.status_units = QLabel("Units: m, kN, s")
        self.status_view = QLabel("View: 3D")
        self.status_counts = QLabel("Nodes: 0   Elements: 0")

        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self.status_units)
        self.statusBar().addPermanentWidget(self.status_view)
        self.statusBar().addPermanentWidget(self.status_counts)

    def _size_initial_docks(self) -> None:
        self.resizeDocks(
            [self.model_tree_dock, self.create_dock],
            [270, 340],
            Qt.Horizontal,
        )
        self.resizeDocks(
            [self.model_tree_dock, self.properties_dock],
            [570, 230],
            Qt.Vertical,
        )
        self.resizeDocks(
            [self.script_dock, self.console_dock, self.results_dock],
            [510, 280, 480],
            Qt.Horizontal,
        )
        self.resizeDocks(
            [self.script_dock],
            [250],
            Qt.Vertical,
        )

    def _create_default_model(self) -> None:
        generate_frame_grid(self.model, FrameGridSpec(nx=4, ny=3, nz=3))
        self._refresh_all("Generated default 4 × 3 bay, 3-storey frame")
        self._show_frame_grid()

    def _new_model(self) -> None:
        self.model.clear()
        self._refresh_all("New empty model")

    def _show_frame_grid(self) -> None:
        self.create_dock.show()
        self.create_dock.raise_()

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
        root.addChild(geometry)

        nodes = QTreeWidgetItem([f"Nodes ({len(self.model.nodes)})"])
        nodes.setIcon(0, studio_icon("node"))
        lines = QTreeWidgetItem(["Lines (0)"])
        lines.setIcon(0, studio_icon("element"))
        frame_grids = QTreeWidgetItem(["Frame Grids (1)"])
        frame_grids.setIcon(0, studio_icon("grid"))
        geometry.addChildren([nodes, lines, frame_grids])

        elements = QTreeWidgetItem([f"Elements ({len(self.model.elements)})"])
        elements.setIcon(0, studio_icon("element"))
        root.addChild(elements)

        type_counts = {
            "elasticBeamColumn": 0,
            "forceBeamColumn": 0,
            "zeroLength": 0,
            "truss": 0,
        }
        for element in self.model.elements.values():
            type_counts[element.element_type] = type_counts.get(element.element_type, 0) + 1

        type_items = {}
        for element_type in ("elasticBeamColumn", "forceBeamColumn", "zeroLength", "truss"):
            item = QTreeWidgetItem([f"{element_type} ({type_counts.get(element_type, 0)})"])
            item.setIcon(0, studio_icon("element"))
            type_items[element_type] = item
            elements.addChild(item)

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
            type_items.get(element.element_type, elements).addChild(item)

        fixed_count = sum(any(node.fixity) for node in self.model.nodes.values())
        for label, icon in (
            ("Materials (0)", "material"),
            ("Sections (0)", "section"),
            ("Transformations (0)", "transform"),
            (f"Boundary Conditions ({fixed_count})", "boundary"),
            ("Time Series (0)", "timeseries"),
            ("Load Patterns (0)", "load"),
        ):
            item = QTreeWidgetItem([label])
            item.setIcon(0, studio_icon(icon))
            root.addChild(item)

        analysis = QTreeWidgetItem(["Analysis"])
        analysis.setIcon(0, studio_icon("analysis"))
        settings = QTreeWidgetItem(["Settings"])
        settings.setIcon(0, studio_icon("analysis"))
        recorders = QTreeWidgetItem(["Recorders (0)"])
        recorders.setIcon(0, studio_icon("recorder"))
        analysis.addChildren([settings, recorders])
        root.addChild(analysis)

        results = QTreeWidgetItem(["Results"])
        results.setIcon(0, studio_icon("results"))
        root.addChild(results)

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
                element.tag
                for element in self.model.elements.values()
                if element.i == tag or element.j == tag
            ]
            self.properties_panel.set_properties(
                "Node",
                [
                    ("Tag", tag),
                    ("Coordinates (m)", f"{node.xyz}"),
                    ("X", f"{node.xyz[0]:g}"),
                    ("Y", f"{node.xyz[1]:g}"),
                    ("Z", f"{node.xyz[2]:g}"),
                    ("Fixity", node.fixity),
                    ("Mass", "0.0, 0.0, 0.0"),
                    ("Connected", ", ".join(map(str, connected)) or "-"),
                ],
            )
        elif kind == "element":
            element = self.model.elements[tag]
            self.properties_panel.set_properties(
                "Element",
                [
                    ("Tag", tag),
                    ("Type", element.element_type),
                    ("Nodes", f"{element.i}, {element.j}"),
                    ("Group", element.group),
                    ("Section", element.section_tag or "-"),
                    ("Transformation", element.transf_tag or "-"),
                ],
            )

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
            self.status_message.setText("Model executed successfully")
        except Exception as exc:
            self._log(f"ERROR: {type(exc).__name__}: {exc}")
            QMessageBox.critical(self, "Execution error", str(exc))

    def _not_implemented(self) -> None:
        action = self.sender()
        label = action.text() if isinstance(action, QAction) else "Command"
        self._log(f"{label}: planned for the next milestone")

    def _log(self, text: str) -> None:
        self.console.appendPlainText(">> " + text)
