from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile

from PySide6.QtCore import QProcess, QTimer, QSize, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QKeySequence, QPainter, QPen, QShortcut, QTextCursor, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QMenu,
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
from ..project import MaterialData, ProjectDatabase, SectionData, SelectionSetData, TransformationData
from .code_editor import CodeEditor
from .geometry_dialogs import (
    ElementDialog,
    MirrorDialog,
    NodeDialog,
    RotateDialog,
    SelectByIdDialog,
    VectorDialog,
)
from .history import ProjectSnapshotCommand
from .material_dialog import MaterialDialog
from .section_dialog import SectionDialog
from .transformation_dialog import TransformationDialog
from .icons import studio_icon
from .results_panel import ResultsPanel
from .selection import SelectionManager, parse_tag_expression
from .viewport import ModelViewport


APP_STYLE = """
QMainWindow {
    background: #eef2f6;
    color: #23364a;
}
QMenuBar {
    background: #fbfcfd;
    color: #1f2f40;
    border-bottom: 1px solid #d2d9e1;
    padding: 1px 3px;
}
QMenuBar::item {
    padding: 5px 9px;
}
QMenuBar::item:selected {
    background: #e9f2fd;
}
QToolBar#Ribbon {
    background: #fafbfd;
    border: none;
    border-bottom: 1px solid #cbd4de;
    spacing: 0;
    padding: 2px 4px 0 4px;
}
QWidget#RibbonGroup {
    border-right: 1px solid #d6dde5;
    background: transparent;
}
QLabel#RibbonCaption {
    color: #596a7b;
    font-size: 9px;
    padding: 0 2px 2px 2px;
}
QToolButton#RibbonButton {
    color: #203247;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px 4px;
    min-width: 45px;
    min-height: 50px;
}
QToolButton#RibbonButton:hover {
    background: #e9f3ff;
    border-color: #bed3eb;
}
QToolButton#RibbonButton:pressed,
QToolButton#RibbonButton:checked {
    background: #d5eaff;
    border-color: #79ace3;
}
QDockWidget {
    color: #203247;
    font-weight: 600;
}
QDockWidget::title {
    background: #f4f6f8;
    border: 1px solid #cfd7df;
    padding: 5px 7px;
    text-align: left;
}
QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #cfd7df;
}
QTabBar::tab {
    background: #f0f3f6;
    color: #4d6072;
    border: 1px solid #cfd7df;
    border-bottom: none;
    padding: 5px 11px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #173f68;
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
    alternate-background-color: #fbfcfe;
    padding: 2px;
}
QTreeWidget::item {
    min-height: 20px;
    padding: 1px 2px;
}
QTreeWidget::item:hover {
    background: #eaf3fe;
}
QTableWidget {
    gridline-color: #e0e6ed;
}
QPushButton {
    min-height: 26px;
    border: 1px solid #bdc8d3;
    border-radius: 3px;
    background: #fafbfd;
    color: #26394c;
    padding: 2px 9px;
}
QPushButton:hover {
    background: #eaf4ff;
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
    min-width: 90px;
}
QPushButton#PrimaryButton:hover {
    background: #0f68c2;
}
QPushButton#CloseButton {
    min-width: 82px;
}
QPushButton#MoreButton {
    min-width: 28px;
    max-width: 28px;
    padding: 0;
}
QSpinBox, QDoubleSpinBox, QComboBox {
    min-height: 24px;
    border: 1px solid #bcc7d2;
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
    font-size: 13px;
    font-weight: 700;
    color: #173e65;
}
QLabel#SectionTitle {
    font-size: 11px;
    font-weight: 700;
    color: #20364d;
    padding-top: 3px;
}
QLabel#Muted {
    color: #718195;
}
QFrame#SectionLine {
    color: #d7dee6;
}
QStatusBar {
    background: #fafbfd;
    color: #42566b;
    border-top: 1px solid #ccd5df;
}
"""


class BrandWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(215)
        self.setMaximumWidth(245)
        self.setMinimumHeight(64)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(QColor("#c62828"), 2.4)
        painter.setPen(pen)
        points = [
            (7, 31), (16, 31), (20, 16), (25, 46), (31, 8),
            (36, 40), (41, 21), (47, 34), (54, 34), (58, 25),
            (63, 37), (69, 31), (76, 31),
        ]
        for a, b in zip(points[:-1], points[1:]):
            painter.drawLine(a[0], a[1], b[0], b[1])

        painter.setPen(QColor("#17356d"))
        font = QFont(self.font())
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(84, 28, "OpenSeesPy Studio")

        painter.setPen(QColor("#6f7d8c"))
        font.setPointSize(7)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(84, 45, "Model  ·  Analyze  ·  Visualize")


class RibbonGroup(QWidget):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 1, 5, 0)
        layout.setSpacing(0)

        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(0)
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
        button.setIconSize(QSize(24, 24))
        button.setAutoRaise(True)
        self.button_row.addWidget(button)

    def add_widget(self, widget: QWidget) -> None:
        self.button_row.addWidget(widget)


class FrameGridPanel(QWidget):
    def __init__(self, generate_callback, close_callback, parent=None):
        super().__init__(parent)
        self.generate_callback = generate_callback
        self.close_callback = close_callback

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(5)

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
            ("Number of bays:", self.nx, False),
            ("Bay width (m):", self.dx, True),
        ])
        self._add_section(layout, "Y Direction (Bays)", [
            ("Number of bays:", self.ny, False),
            ("Bay width (m):", self.dy, True),
        ])
        self._add_section(layout, "Z Direction (Storeys)", [
            ("Number of storeys:", self.nz, False),
            ("Storey height (m):", self.dz, True),
        ])

        layout.addWidget(self._separator())
        options_title = QLabel("Options")
        options_title.setObjectName("SectionTitle")
        layout.addWidget(options_title)

        self.columns = QCheckBox("Create columns:")
        self.beams = QCheckBox("Create beams:")
        self.columns.setChecked(True)
        self.beams.setChecked(True)
        layout.addWidget(self.columns)
        layout.addWidget(self.beams)

        self.column_section = QComboBox()
        self.beam_section = QComboBox()
        self.column_transformation = QComboBox()
        self.beam_transformation = QComboBox()
        self.refresh_assignments({}, {})

        assignment = QFormLayout()
        assignment.setContentsMargins(0, 1, 0, 0)
        assignment.setVerticalSpacing(5)
        assignment.addRow("Section (columns):", self.column_section)
        assignment.addRow("Section (beams):", self.beam_section)
        assignment.addRow("Transformation (columns):", self.column_transformation)
        assignment.addRow("Transformation (beams):", self.beam_transformation)
        assign_widget = QWidget()
        assign_widget.setLayout(assignment)
        layout.addWidget(assign_widget)

        self.node_tag = self._int_spin(1, 1, 10_000_000)
        self.element_tag = self._int_spin(1, 1, 10_000_000)
        tags = QFormLayout()
        tags.setContentsMargins(0, 1, 0, 0)
        tags.setVerticalSpacing(5)
        tags.addRow("Start node tag:", self.node_tag)
        tags.addRow("Start element tag:", self.element_tag)
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

    def _value_with_more(self, widget: QWidget) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(widget, 1)
        more = QPushButton("...")
        more.setObjectName("MoreButton")
        more.setToolTip("Advanced spacing options")
        more.setEnabled(False)
        row.addWidget(more)
        return container

    def _add_section(self, parent_layout, title: str, rows) -> None:
        if parent_layout.count() > 2:
            parent_layout.addWidget(self._separator())

        label = QLabel(title)
        label.setObjectName("SectionTitle")
        parent_layout.addWidget(label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(5)
        for text, widget, has_more in rows:
            form.addRow(text, self._value_with_more(widget) if has_more else widget)
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

    def refresh_assignments(self, sections, transformations) -> None:
        combos = (
            self.column_section,
            self.beam_section,
            self.column_transformation,
            self.beam_transformation,
        )
        previous = [combo.currentData() for combo in combos]

        for combo in combos:
            combo.clear()
            combo.addItem("None", None)

        for tag in sorted(sections):
            section = sections[tag]
            text = f"{tag} - {section.name} ({section.section_type})"
            self.column_section.addItem(text, tag)
            self.beam_section.addItem(text, tag)

        for tag in sorted(transformations):
            transformation = transformations[tag]
            text = (
                f"{tag} - {transformation.name} "
                f"({transformation.transformation_type})"
            )
            self.column_transformation.addItem(text, tag)
            self.beam_transformation.addItem(text, tag)

        for combo, value in zip(combos, previous):
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)

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
            create_beams_x=self.beams.isChecked(),
            create_beams_y=self.beams.isChecked(),
            column_section_tag=self.column_section.currentData(),
            beam_section_tag=self.beam_section.currentData(),
            column_transf_tag=self.column_transformation.currentData(),
            beam_transf_tag=self.beam_transformation.currentData(),
        ))


class PropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(3)

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
        self.table.setColumnWidth(0, 112)
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

        self.project = ProjectDatabase(
            name="Untitled",
            model=StructuralModel("3D_Frame"),
        )
        self.model = self.project.model
        self._project_path: Path | None = None
        self.actions: dict[str, QAction] = {}
        self.undo_stack = QUndoStack(self)
        self.selection = SelectionManager(self)
        self._tree_node_items: dict[int, QTreeWidgetItem] = {}
        self._tree_element_items: dict[int, QTreeWidgetItem] = {}
        self._shortcuts: list[QShortcut] = []
        self._analysis_process: QProcess | None = None
        self._analysis_script_path: str | None = None
        self._dirty = False

        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        self._build_central_view()
        self._build_model_tree_dock()
        self._build_properties_dock()
        self._build_create_dock()
        self._build_bottom_docks()
        self._build_actions_and_ribbon()
        self._build_status_bar()
        self._wire_history()
        self._wire_selection()
        self._install_shortcuts()
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
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setIconSize(QSize(17, 17))
        self.tree.setIndentation(16)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        self.tree.itemDoubleClicked.connect(self._tree_item_double_clicked)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)

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

        self.frame_grid_panel = FrameGridPanel(self._generate_frame_grid, dock.hide)
        dock.setWidget(self.frame_grid_panel)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.create_dock = dock

    def _build_bottom_docks(self) -> None:
        script_dock = QDockWidget("", self)
        script_dock.setObjectName("PythonDock")
        script_dock.setAllowedAreas(Qt.BottomDockWidgetArea)

        script_tabs = QTabWidget()
        script_tabs.setDocumentMode(True)
        self.script = CodeEditor()
        command = QPlainTextEdit()
        command.setReadOnly(True)
        command.setPlaceholderText("Interactive OpenSeesPy command console (planned)")
        script_tabs.addTab(self.script, "Python Script")
        script_tabs.addTab(command, "Command")
        script_dock.setWidget(script_tabs)
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

        self._make_action("new", "New", "new", self._new_model, "New project")
        self._make_action("open", "Open", "open", self._open_project, "Open project")
        self._make_action("save", "Save", "save", self._save_project, "Save project")
        self._make_action("undo", "Undo", "undo", self.undo_stack.undo, "Undo")
        self._make_action("redo", "Redo", "redo", self.undo_stack.redo, "Redo")
        self._make_action("save_as", "Save As...", "save", self._save_project_as, "Save project as")
        self._make_action("export_py", "Export Python...", "save", self._export_script, "Export OpenSeesPy script")

        self.actions["save"].setShortcut(QKeySequence.Save)
        self.actions["open"].setShortcut(QKeySequence.Open)
        self.actions["new"].setShortcut(QKeySequence.New)
        self.actions["undo"].setShortcut(QKeySequence.Undo)
        self.actions["redo"].setShortcut(QKeySequence.Redo)

        self._make_action("node", "Node", "node", self._create_node, "Create node")
        self._make_action("line", "Line", "element", self._create_element, "Create element")
        self._make_action("frame", "Frame", "element", self._create_element, "Create frame element")
        self._make_action("grid", "Grid", "grid", self._show_frame_grid, "Create frame grid")
        self._make_action("extrude", "Extrude", "copy", self._not_implemented, "Extrude geometry")

        modify_callbacks = {
            "copy": self._copy_selection,
            "move": self._move_selection,
            "rotate": self._rotate_selection,
            "mirror": self._mirror_selection,
            "delete": self._delete_selection,
        }
        for key, label, icon in (
            ("copy", "Copy", "copy"),
            ("move", "Move", "move"),
            ("rotate", "Rotate", "rotate"),
            ("mirror", "Mirror", "mirror"),
            ("delete", "Delete", "delete"),
        ):
            self._make_action(key, label, icon, modify_callbacks[key], label)

        selection_callbacks = {
            "select": self._activate_select_tool,
            "box": self._activate_box_tool,
            "polygon": self._not_implemented,
            "byid": self._select_by_id,
            "bytype": self._select_by_type,
        }
        for key, label, icon in (
            ("select", "Select", "select"),
            ("box", "Box", "box"),
            ("polygon", "Polygon", "polygon"),
            ("byid", "By ID", "by-id"),
            ("bytype", "By Type", "by-id"),
        ):
            self._make_action(
                key,
                label,
                icon,
                selection_callbacks[key],
                label,
                checkable=(key in {"select", "box"}),
            )
        self.actions["select"].setChecked(True)

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

        self._make_action(
            "new_material",
            "New Material...",
            "material",
            self._create_material,
            "Create OpenSees uniaxial material",
        )
        self._make_action(
            "new_section",
            "New Section...",
            "section",
            self._create_section,
            "Create OpenSees section",
        )
        self._make_action(
            "new_transformation",
            "New Transformation...",
            "transform",
            self._create_transformation,
            "Create OpenSees geometric transformation",
        )
        self._make_action(
            "assign_section",
            "Assign Section...",
            "section",
            self._assign_section_to_selection,
            "Assign section to selected elements",
        )
        self._make_action(
            "assign_transformation",
            "Assign Transformation...",
            "transform",
            self._assign_transformation_to_selection,
            "Assign geometric transformation to selected elements",
        )
        self._make_action("run", "Run", "run", self._toggle_analysis, "Run / stop model")
        self._make_action("plot", "Plot", "plot", self._not_implemented, "Plot results")

        menus["File"].addActions([self.actions["new"], self.actions["open"], self.actions["save"]])
        menus["File"].addAction(self.actions["save_as"])
        menus["File"].addSeparator()
        menus["File"].addAction(self.actions["export_py"])
        menus["Edit"].addActions([self.actions["undo"], self.actions["redo"]])
        menus["Model"].addAction(self.actions["new_material"])
        menus["Model"].addAction(self.actions["new_section"])
        menus["Model"].addAction(self.actions["new_transformation"])
        menus["Model"].addSeparator()
        menus["Model"].addAction(self.actions["assign_section"])
        menus["Model"].addAction(self.actions["assign_transformation"])
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
            if caption == "Selection":
                self.selection_filter_combo = QComboBox()
                self.selection_filter_combo.addItems(["All", "Node", "Element"])
                self.selection_filter_combo.setFixedWidth(76)
                self.selection_filter_combo.setToolTip("Selection filter")
                self.selection_filter_combo.currentTextChanged.connect(
                    self._set_selection_filter
                )
                group.add_widget(self.selection_filter_combo)
            ribbon.addWidget(group)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ribbon.addWidget(spacer)
        ribbon.addWidget(BrandWidget())

    def _build_status_bar(self) -> None:
        self.status_message = QLabel("Ready")
        self.status_units = QLabel("Units: m, kN, s")
        self.status_view = QLabel("View: 3D")
        self.status_navigation = QLabel(
            "MMB Rotate · Ctrl+MMB Pan · Shift+MMB Zoom · Wheel Zoom"
        )
        self.status_navigation.setStyleSheet("color: #6c7c8d;")
        self.status_counts = QLabel("Nodes: 0   Elements: 0")

        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self.status_navigation)
        self.statusBar().addPermanentWidget(self.status_units)
        self.statusBar().addPermanentWidget(self.status_view)
        self.statusBar().addPermanentWidget(self.status_counts)

    def _size_initial_docks(self) -> None:
        self.resizeDocks([self.model_tree_dock, self.create_dock], [275, 340], Qt.Horizontal)
        self.resizeDocks([self.model_tree_dock, self.properties_dock], [575, 230], Qt.Vertical)
        self.resizeDocks(
            [self.script_dock, self.console_dock, self.results_dock],
            [500, 275, 480],
            Qt.Horizontal,
        )
        self.resizeDocks([self.script_dock], [245], Qt.Vertical)

    def _create_default_model(self) -> None:
        generate_frame_grid(self.model, FrameGridSpec(nx=4, ny=3, nz=3))
        self._refresh_all("Generated default 4 × 3 bay, 3-storey frame")
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_dirty(False)
        self._show_frame_grid()

    def _new_model(self) -> None:
        if not self._maybe_save_changes():
            return
        self.selection.clear()
        self.project = ProjectDatabase(
            name="Untitled",
            model=StructuralModel("Untitled"),
        )
        self.model = self.project.model
        self._project_path = None
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_dirty(False)
        self._refresh_all("New empty project")

    def _show_frame_grid(self) -> None:
        self.frame_grid_panel.refresh_assignments(
            self.project.sections,
            self.project.transformations,
        )
        self.create_dock.show()
        self.create_dock.raise_()

    def _generate_frame_grid(self, spec: FrameGridSpec) -> None:
        before = self.project.to_dict()
        self.selection.clear()
        generate_frame_grid(self.model, spec)
        self._refresh_all(
            f"Generated {spec.nx} × {spec.ny} bay, {spec.nz}-storey frame"
        )
        self._record_project_change("Generate frame grid", before)

    def _refresh_all(self, message: str = "") -> None:
        self.viewport.draw_model(self.model)
        self._refresh_project_metadata(message)

    def _refresh_project_metadata(self, message: str = "") -> None:
        self.viewport.set_model_info(
            self.model.name,
            len(self.model.nodes),
            len(self.model.elements),
            len(self.project.materials),
            len(self.project.sections),
        )
        self.frame_grid_panel.refresh_assignments(
            self.project.sections,
            self.project.transformations,
        )
        self._refresh_tree()
        self.script.setPlainText(
            to_openseespy(
                self.model,
                self.project.materials,
                self.project.sections,
                self.project.transformations,
            )
        )
        self._selection_changed(self.selection.snapshot())

        if message:
            self._log(message)
            self.status_message.setText(message)

        self.status_counts.setText(
            f"Nodes: {len(self.model.nodes)}   Elements: {len(self.model.elements)}"
        )
        units = self.project.units
        self.status_units.setText(
            f"Units: {units.get('length', 'm')}, "
            f"{units.get('force', 'kN')}, {units.get('time', 's')}"
        )

    def _refresh_tree(self) -> None:
        self.tree.clear()
        self._tree_node_items.clear()
        self._tree_element_items.clear()

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
        frame_grids = QTreeWidgetItem(["Frame Grids (1)" if self.model.nodes else "Frame Grids (0)"])
        frame_grids.setIcon(0, studio_icon("grid"))
        geometry.addChildren([nodes, lines, frame_grids])

        elements = QTreeWidgetItem([f"Elements ({len(self.model.elements)})"])
        elements.setIcon(0, studio_icon("element"))
        elements.setExpanded(True)
        root.addChild(elements)

        type_counts: dict[str, int] = {}
        for element in self.model.elements.values():
            type_counts[element.element_type] = type_counts.get(element.element_type, 0) + 1

        type_items: dict[str, QTreeWidgetItem] = {}
        known_types = {
            "elasticBeamColumn",
            "forceBeamColumn",
            "dispBeamColumn",
            "zeroLength",
            "truss",
        }
        for element_type in sorted(known_types | set(type_counts)):
            item = QTreeWidgetItem([f"{element_type} ({type_counts.get(element_type, 0)})"])
            item.setIcon(0, studio_icon("element"))
            type_items[element_type] = item
            elements.addChild(item)

        for tag in sorted(self.model.nodes):
            item = QTreeWidgetItem([f"Node {tag}"])
            item.setIcon(0, studio_icon("node"))
            item.setData(0, Qt.UserRole, ("node", tag))
            nodes.addChild(item)
            self._tree_node_items[tag] = item

        for tag in sorted(self.model.elements):
            element = self.model.elements[tag]
            item = QTreeWidgetItem([f"Element {tag}"])
            item.setIcon(0, studio_icon("element"))
            item.setData(0, Qt.UserRole, ("element", tag))
            type_items.get(element.element_type, elements).addChild(item)
            self._tree_element_items[tag] = item

        named_sets = QTreeWidgetItem([
            f"Named Selections ({len(self.project.selection_sets)})"
        ])
        named_sets.setIcon(0, studio_icon("select"))
        named_sets.setExpanded(True)
        root.addChild(named_sets)

        for name in sorted(self.project.selection_sets):
            selection_set = self.project.selection_sets[name]
            item = QTreeWidgetItem([
                f"{name}  ({len(selection_set.node_tags)}N / "
                f"{len(selection_set.element_tags)}E)"
            ])
            item.setIcon(0, studio_icon("select"))
            item.setData(0, Qt.UserRole, ("set", name))
            named_sets.addChild(item)

        materials_root = QTreeWidgetItem([
            f"Materials ({len(self.project.materials)})"
        ])
        materials_root.setIcon(0, studio_icon("material"))
        materials_root.setData(0, Qt.UserRole, ("materials_root", None))
        materials_root.setExpanded(True)
        root.addChild(materials_root)

        for tag in sorted(self.project.materials):
            material = self.project.materials[tag]
            item = QTreeWidgetItem([
                f"{material.material_type} [{tag}]  {material.name}"
            ])
            item.setIcon(0, studio_icon("material"))
            item.setData(0, Qt.UserRole, ("material", tag))
            materials_root.addChild(item)

        sections_root = QTreeWidgetItem([
            f"Sections ({len(self.project.sections)})"
        ])
        sections_root.setIcon(0, studio_icon("section"))
        sections_root.setData(0, Qt.UserRole, ("sections_root", None))
        sections_root.setExpanded(True)
        root.addChild(sections_root)

        for tag in sorted(self.project.sections):
            section = self.project.sections[tag]
            item = QTreeWidgetItem([
                f"{section.section_type} [{tag}]  {section.name}"
            ])
            item.setIcon(0, studio_icon("section"))
            item.setData(0, Qt.UserRole, ("section", tag))
            sections_root.addChild(item)

        transformations_root = QTreeWidgetItem([
            f"Transformations ({len(self.project.transformations)})"
        ])
        transformations_root.setIcon(0, studio_icon("transform"))
        transformations_root.setData(
            0,
            Qt.UserRole,
            ("transformations_root", None),
        )
        transformations_root.setExpanded(True)
        root.addChild(transformations_root)

        for tag in sorted(self.project.transformations):
            transformation = self.project.transformations[tag]
            item = QTreeWidgetItem([
                f"{transformation.transformation_type} [{tag}]  "
                f"{transformation.name}"
            ])
            item.setIcon(0, studio_icon("transform"))
            item.setData(0, Qt.UserRole, ("transformation", tag))
            transformations_root.addChild(item)

        fixed_count = sum(any(node.fixity) for node in self.model.nodes.values())

        for label, icon in (
            (f"Boundary Conditions ({fixed_count})", "boundary"),
            (f"Time Series ({len(self.project.time_series)})", "timeseries"),
            (f"Load Patterns ({len(self.project.load_patterns)})", "load"),
        ):
            item = QTreeWidgetItem([label])
            item.setIcon(0, studio_icon(icon))
            root.addChild(item)

        analysis = QTreeWidgetItem(["Analysis"])
        analysis.setIcon(0, studio_icon("analysis"))
        analysis.setExpanded(True)
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
        nodes: set[int] = set()
        elements: set[int] = set()
        material_tag: int | None = None
        section_tag: int | None = None
        transformation_tag: int | None = None

        for item in self.tree.selectedItems():
            payload = item.data(0, Qt.UserRole)
            if not payload:
                continue
            kind, tag = payload
            if kind == "node":
                nodes.add(tag)
            elif kind == "element":
                elements.add(tag)
            elif kind == "set":
                selection_set = self.project.selection_sets.get(str(tag))
                if selection_set is not None:
                    nodes.update(selection_set.node_tags)
                    elements.update(selection_set.element_tags)
            elif kind == "material":
                material_tag = int(tag)
            elif kind == "section":
                section_tag = int(tag)
            elif kind == "transformation":
                transformation_tag = int(tag)

        self.selection.set_selection(nodes=nodes, elements=elements)
        if material_tag is not None:
            self._show_material_properties(material_tag)
        elif section_tag is not None:
            self._show_section_properties(section_tag)
        elif transformation_tag is not None:
            self._show_transformation_properties(transformation_tag)

    def _wire_selection(self) -> None:
        self.selection.changed.connect(self._selection_changed)
        self.viewport.entity_clicked.connect(self._viewport_entity_clicked)
        self.viewport.entity_hovered.connect(self._viewport_entity_hovered)
        self.viewport.entity_double_clicked.connect(self._viewport_entity_double_clicked)
        self.viewport.context_requested.connect(self._show_viewport_context_menu)
        self.viewport.box_selected.connect(self._viewport_box_selected)
        self.viewport.set_selection_filter(self.selection.filter)

    def _install_shortcuts(self) -> None:
        bindings = (
            ("Escape", self.selection.clear),
            ("Delete", self._delete_selection),
            ("F", self._zoom_selection),
            ("H", self._hide_selection),
            ("Shift+H", self._show_all),
            ("I", self._isolate_selection),
        )
        for sequence, callback in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _activate_select_tool(self) -> None:
        self.viewport.set_interaction_tool("select")
        self.actions["select"].setChecked(True)
        self.actions["box"].setChecked(False)
        self.status_message.setText("Select tool active")

    def _activate_box_tool(self) -> None:
        self.viewport.set_interaction_tool("box")
        self.actions["select"].setChecked(False)
        self.actions["box"].setChecked(True)
        self.status_message.setText(
            "Box select: left→right = window, right→left = crossing"
        )

    def _set_selection_filter(self, text: str) -> None:
        value = text.lower()
        self.selection.set_filter(value)
        self.viewport.set_selection_filter(value)
        self.status_message.setText(f"Selection filter: {text}")

    def _viewport_entity_clicked(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        kind = payload.get("kind")
        tag = payload.get("tag")
        mode = payload.get("mode", "replace")
        if kind is None:
            if mode == "replace":
                self.selection.clear()
            return
        self.selection.select(str(kind), int(tag), str(mode))

    def _viewport_box_selected(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        nodes = set(payload.get("nodes", ()))
        elements = set(payload.get("elements", ()))
        mode = str(payload.get("mode", "replace"))
        self.selection.select_many(
            nodes=nodes,
            elements=elements,
            mode=mode,
        )
        selection_kind = "crossing" if payload.get("crossing") else "window"
        self.status_message.setText(
            f"Box {selection_kind}: {len(nodes)} node(s), "
            f"{len(elements)} element(s)"
        )

    def _viewport_entity_hovered(self, payload: object) -> None:
        if isinstance(payload, dict):
            kind = str(payload.get("kind", "")).title()
            tag = payload.get("tag")
            self.status_message.setText(f"Hover: {kind} {tag}")
        elif not self.selection.nodes and not self.selection.elements:
            self.status_message.setText("Ready")

    def _viewport_entity_double_clicked(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        kind = str(payload.get("kind"))
        tag = int(payload.get("tag"))
        self.selection.select(kind, tag, "replace")
        self._show_entity_properties(kind, tag)
        self.properties_dock.raise_()

    def _selection_changed(self, snapshot: object) -> None:
        if not isinstance(snapshot, dict):
            return
        nodes = set(snapshot.get("nodes", ()))
        elements = set(snapshot.get("elements", ()))

        self.viewport.set_selection(nodes, elements)

        self.tree.blockSignals(True)
        self.tree.clearSelection()
        first_item = None
        for tag in sorted(nodes):
            item = self._tree_node_items.get(tag)
            if item is not None:
                item.setSelected(True)
                first_item = first_item or item
        for tag in sorted(elements):
            item = self._tree_element_items.get(tag)
            if item is not None:
                item.setSelected(True)
                first_item = first_item or item
        self.tree.blockSignals(False)

        if first_item is not None:
            self.tree.scrollToItem(first_item)

        total = len(nodes) + len(elements)
        if total == 1:
            if nodes:
                self._show_entity_properties("node", next(iter(nodes)))
            else:
                self._show_entity_properties("element", next(iter(elements)))
        elif total > 1:
            self.properties_panel.set_properties(
                "Selection",
                [
                    ("Nodes", len(nodes)),
                    ("Elements", len(elements)),
                    ("Total", total),
                ],
            )
        else:
            self.properties_panel.set_properties("Properties", [])

        if total:
            self.status_message.setText(
                f"Selected: {len(nodes)} node(s), {len(elements)} element(s)"
            )
        else:
            self.status_message.setText("Ready")

    def _show_entity_properties(self, kind: str, tag: int) -> None:
        if kind == "node":
            node = self.model.nodes.get(tag)
            if node is None:
                return
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
            element = self.model.elements.get(tag)
            if element is None:
                return
            section_text = "-"
            if element.section_tag is not None:
                section = self.project.sections.get(element.section_tag)
                section_text = (
                    f"{element.section_tag} - {section.name}"
                    if section is not None
                    else f"{element.section_tag} (missing)"
                )

            transformation_text = "-"
            if element.transf_tag is not None:
                transformation = self.project.transformations.get(
                    element.transf_tag
                )
                transformation_text = (
                    f"{element.transf_tag} - {transformation.name}"
                    if transformation is not None
                    else f"{element.transf_tag} (missing)"
                )

            self.properties_panel.set_properties(
                "Element",
                [
                    ("Tag", tag),
                    ("Type", element.element_type),
                    ("Nodes", f"{element.i}, {element.j}"),
                    ("Group", element.group),
                    ("Section", section_text),
                    ("Transformation", transformation_text),
                ],
            )

    def _show_viewport_context_menu(self, payload: object) -> None:
        if isinstance(payload, dict):
            kind = str(payload.get("kind"))
            tag = int(payload.get("tag"))
            selected = (
                tag in self.selection.nodes
                if kind == "node"
                else tag in self.selection.elements
            )
            if not selected:
                self.selection.select(kind, tag, "replace")

        menu = QMenu(self)

        if isinstance(payload, dict):
            kind = str(payload.get("kind"))
            tag = int(payload.get("tag"))
            header = menu.addAction(f"{kind.title()} {tag}")
            header.setEnabled(False)
            menu.addSeparator()

            query = menu.addAction("Query / Properties")
            query.triggered.connect(
                lambda checked=False, k=kind, t=tag: self._show_entity_properties(k, t)
            )

        zoom = menu.addAction("Zoom to Selection")
        zoom.triggered.connect(self._zoom_selection)
        menu.addSeparator()

        hide = menu.addAction("Hide")
        hide.triggered.connect(self._hide_selection)
        isolate = menu.addAction("Isolate")
        isolate.triggered.connect(self._isolate_selection)
        show_all = menu.addAction("Show All")
        show_all.triggered.connect(self._show_all)

        menu.addSeparator()
        assign_menu = menu.addMenu("Assign")
        assign_menu.setEnabled(bool(self.selection.elements))
        assign_section = assign_menu.addAction("Section...")
        assign_section.triggered.connect(self._assign_section_to_selection)
        assign_transformation = assign_menu.addAction("Transformation...")
        assign_transformation.triggered.connect(
            self._assign_transformation_to_selection
        )
        assign_menu.addSeparator()
        clear_section = assign_menu.addAction("Clear Section")
        clear_section.triggered.connect(self._clear_section_assignment)
        clear_transformation = assign_menu.addAction("Clear Transformation")
        clear_transformation.triggered.connect(
            self._clear_transformation_assignment
        )

        menu.addSeparator()
        move_action = menu.addAction("Move...")
        move_action.triggered.connect(self._move_selection)
        copy_action = menu.addAction("Copy...")
        copy_action.triggered.connect(self._copy_selection)
        rotate_action = menu.addAction("Rotate...")
        rotate_action.triggered.connect(self._rotate_selection)
        mirror_action = menu.addAction("Mirror...")
        mirror_action.triggered.connect(self._mirror_selection)

        menu.addSeparator()
        copy_tag = menu.addAction("Copy Tag(s)")
        copy_tag.triggered.connect(self._copy_selected_tags)
        create_set = menu.addAction("Create Named Selection")
        create_set.triggered.connect(self._create_named_selection)

        menu.addSeparator()
        delete = menu.addAction("Delete")
        delete.triggered.connect(self._delete_selection)
        clear = menu.addAction("Clear Selection")
        clear.triggered.connect(self.selection.clear)

        menu.exec(QCursor.pos())

    def _selection_sets(self) -> tuple[set[int], set[int]]:
        return set(self.selection.nodes), set(self.selection.elements)

    def _selected_element_tags(
        self,
        title: str,
    ) -> set[int] | None:
        tags = set(self.selection.elements)
        if not tags:
            QMessageBox.information(
                self,
                title,
                "Select at least one element first.",
            )
            return None
        return tags

    def _assign_section_to_selection(self) -> None:
        element_tags = self._selected_element_tags("Assign Section")
        if element_tags is None:
            return
        if not self.project.sections:
            QMessageBox.information(
                self,
                "Assign Section",
                "No sections exist yet. Create a section first.",
            )
            return

        tags = sorted(self.project.sections)
        labels = [
            (
                f"{tag} - {self.project.sections[tag].name} "
                f"({self.project.sections[tag].section_type})"
            )
            for tag in tags
        ]
        label, ok = QInputDialog.getItem(
            self,
            "Assign Section",
            f"Assign to {len(element_tags)} selected element(s):",
            labels,
            0,
            False,
        )
        if not ok:
            return
        section_tag = tags[labels.index(label)]

        before = self.project.to_dict()
        assigned = self.model.assign_section(element_tags, section_tag)
        self._refresh_project_metadata(
            f"Assigned section {section_tag} to {len(assigned)} element(s)"
        )
        self._record_project_change(
            f"Assign section {section_tag}",
            before,
        )

    def _assign_transformation_to_selection(self) -> None:
        element_tags = self._selected_element_tags(
            "Assign Transformation"
        )
        if element_tags is None:
            return
        if not self.project.transformations:
            QMessageBox.information(
                self,
                "Assign Transformation",
                "No transformations exist yet. "
                "Create a transformation first.",
            )
            return

        tags = sorted(self.project.transformations)
        labels = [
            (
                f"{tag} - {self.project.transformations[tag].name} "
                f"({self.project.transformations[tag].transformation_type})"
            )
            for tag in tags
        ]
        label, ok = QInputDialog.getItem(
            self,
            "Assign Transformation",
            f"Assign to {len(element_tags)} selected element(s):",
            labels,
            0,
            False,
        )
        if not ok:
            return
        transformation_tag = tags[labels.index(label)]

        before = self.project.to_dict()
        assigned = self.model.assign_transformation(
            element_tags,
            transformation_tag,
        )
        self._refresh_project_metadata(
            f"Assigned transformation {transformation_tag} "
            f"to {len(assigned)} element(s)"
        )
        self._record_project_change(
            f"Assign transformation {transformation_tag}",
            before,
        )

    def _clear_section_assignment(self) -> None:
        element_tags = self._selected_element_tags("Clear Section")
        if element_tags is None:
            return
        before = self.project.to_dict()
        assigned = self.model.assign_section(element_tags, None)
        self._refresh_project_metadata(
            f"Cleared section on {len(assigned)} element(s)"
        )
        self._record_project_change("Clear section assignment", before)

    def _clear_transformation_assignment(self) -> None:
        element_tags = self._selected_element_tags(
            "Clear Transformation"
        )
        if element_tags is None:
            return
        before = self.project.to_dict()
        assigned = self.model.assign_transformation(
            element_tags,
            None,
        )
        self._refresh_project_metadata(
            f"Cleared transformation on {len(assigned)} element(s)"
        )
        self._record_project_change(
            "Clear transformation assignment",
            before,
        )

    def _create_node(self) -> None:
        dialog = NodeDialog(self.model.next_node_tag(), self)
        if not dialog.exec():
            return
        tag, x, y, z = dialog.values()
        before = self.project.to_dict()
        try:
            self.model.add_node(tag, x, y, z)
        except ValueError as exc:
            QMessageBox.warning(self, "Create Node", str(exc))
            return
        self._refresh_all(f"Created node {tag}")
        self.selection.select("node", tag, "replace")
        self._record_project_change(f"Create node {tag}", before)

    def _create_element(self) -> None:
        selected_nodes = sorted(self.selection.nodes)
        node_i = selected_nodes[0] if len(selected_nodes) >= 1 else min(self.model.nodes, default=1)
        node_j = selected_nodes[1] if len(selected_nodes) >= 2 else (
            sorted(self.model.nodes)[1]
            if len(self.model.nodes) >= 2
            else node_i + 1
        )
        dialog = ElementDialog(
            self.model.next_element_tag(),
            node_i=node_i,
            node_j=node_j,
            parent=self,
        )
        if not dialog.exec():
            return
        tag, i, j, element_type, group = dialog.values()
        before = self.project.to_dict()
        try:
            self.model.add_element(
                tag,
                i,
                j,
                element_type=element_type,
                group=group,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Create Element", str(exc))
            return
        self._refresh_all(f"Created element {tag}")
        self.selection.select("element", tag, "replace")
        self._record_project_change(f"Create element {tag}", before)

    def _require_selection(self, title: str) -> tuple[set[int], set[int]] | None:
        nodes, elements = self._selection_sets()
        if not nodes and not elements:
            QMessageBox.information(
                self,
                title,
                "Select at least one node or element first.",
            )
            return None
        return nodes, elements

    def _move_selection(self) -> None:
        selected = self._require_selection("Move")
        if selected is None:
            return
        dialog = VectorDialog("Move Selection", self)
        if not dialog.exec():
            return
        dx, dy, dz, _ = dialog.values()
        if abs(dx) + abs(dy) + abs(dz) <= 1.0e-15:
            return
        nodes, elements = selected
        before = self.project.to_dict()
        self.model.translate_entities(
            node_tags=nodes,
            element_tags=elements,
            dx=dx,
            dy=dy,
            dz=dz,
        )
        self._refresh_all("Moved selected entities")
        self._record_project_change("Move selection", before)

    def _copy_selection(self) -> None:
        selected = self._require_selection("Copy")
        if selected is None:
            return
        dialog = VectorDialog("Copy Selection", self, copies=True)
        if not dialog.exec():
            return
        dx, dy, dz, copies = dialog.values()
        nodes, elements = selected
        before = self.project.to_dict()
        new_nodes, new_elements = self.model.copy_entities(
            node_tags=nodes,
            element_tags=elements,
            dx=dx,
            dy=dy,
            dz=dz,
            copies=copies,
        )
        self._refresh_all(
            f"Created {copies} copy/copies: "
            f"{len(new_nodes)} node(s), {len(new_elements)} element(s)"
        )
        self.selection.set_selection(
            nodes=set(new_nodes),
            elements=set(new_elements),
        )
        self._record_project_change("Copy selection", before)

    def _rotate_selection(self) -> None:
        selected = self._require_selection("Rotate")
        if selected is None:
            return
        dialog = RotateDialog(self)
        if not dialog.exec():
            return
        axis, angle, pivot = dialog.values()
        if abs(angle) <= 1.0e-15:
            return
        nodes, elements = selected
        before = self.project.to_dict()
        self.model.rotate_entities(
            node_tags=nodes,
            element_tags=elements,
            axis=axis,
            angle_deg=angle,
            pivot=pivot,
        )
        self._refresh_all(
            f"Rotated selection {angle:g}° about {axis.upper()}"
        )
        self._record_project_change("Rotate selection", before)

    def _mirror_selection(self) -> None:
        selected = self._require_selection("Mirror")
        if selected is None:
            return
        dialog = MirrorDialog(self)
        if not dialog.exec():
            return
        normal_axis, coordinate = dialog.values()
        nodes, elements = selected
        before = self.project.to_dict()
        self.model.mirror_entities(
            node_tags=nodes,
            element_tags=elements,
            normal_axis=normal_axis,
            coordinate=coordinate,
        )
        self._refresh_all(
            f"Mirrored selection about {normal_axis.upper()}={coordinate:g}"
        )
        self._record_project_change("Mirror selection", before)

    def _select_by_id(self) -> None:
        dialog = SelectByIdDialog(self)
        if not dialog.exec():
            return
        entity, expression = dialog.values()
        try:
            requested = parse_tag_expression(expression)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Select By ID", str(exc))
            return

        if entity == "node":
            found = requested & set(self.model.nodes)
            missing = requested - set(self.model.nodes)
            self.selection.select_many(nodes=found, mode="replace")
        else:
            found = requested & set(self.model.elements)
            missing = requested - set(self.model.elements)
            self.selection.select_many(elements=found, mode="replace")

        if missing:
            self.status_message.setText(
                f"Selected {len(found)} {entity}(s); "
                f"{len(missing)} ID(s) not found"
            )

    def _select_by_type(self) -> None:
        if not self.model.elements:
            return
        element_types = sorted({e.element_type for e in self.model.elements.values()})
        groups = sorted({e.group for e in self.model.elements.values()})
        choices = [f"Type: {value}" for value in element_types]
        choices += [f"Group: {value}" for value in groups]
        choice, ok = QInputDialog.getItem(
            self,
            "Select By Type",
            "Filter:",
            choices,
            0,
            False,
        )
        if not ok or not choice:
            return

        prefix, value = choice.split(": ", 1)
        if prefix == "Type":
            tags = {
                tag
                for tag, element in self.model.elements.items()
                if element.element_type == value
            }
        else:
            tags = {
                tag
                for tag, element in self.model.elements.items()
                if element.group == value
            }
        self.selection.select_many(elements=tags, mode="replace")

    def _zoom_selection(self) -> None:
        nodes, elements = self._selection_sets()
        self.viewport.zoom_to_selection(nodes, elements)

    def _hide_selection(self) -> None:
        nodes, elements = self._selection_sets()
        if not nodes and not elements:
            return
        self.viewport.hide_entities(nodes, elements)
        self.selection.clear()

    def _isolate_selection(self) -> None:
        nodes, elements = self._selection_sets()
        if not nodes and not elements:
            return
        self.viewport.isolate_entities(nodes, elements)

    def _show_all(self) -> None:
        self.viewport.show_all()
        self.status_message.setText("All entities visible")

    def _copy_selected_tags(self) -> None:
        nodes, elements = self._selection_sets()
        parts = []
        if nodes:
            parts.append("Nodes: " + ", ".join(map(str, sorted(nodes))))
        if elements:
            parts.append("Elements: " + ", ".join(map(str, sorted(elements))))
        QApplication.clipboard().setText("\n".join(parts))

    def _delete_selection(self) -> None:
        nodes, elements = self._selection_sets()
        if not nodes and not elements:
            return

        answer = QMessageBox.question(
            self,
            "Delete selected entities",
            f"Delete {len(nodes)} node(s) and {len(elements)} element(s)?\n"
            "Deleting a node also deletes connected elements.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.model.delete_entities(
            node_tags=nodes,
            element_tags=elements,
            cascade_nodes=True,
        )
        self._prune_selection_sets()
        self.selection.clear()
        self._refresh_all("Deleted selected entities")
        self._record_project_change("Delete selected entities", before)

    def _wire_history(self) -> None:
        self.actions["undo"].setEnabled(False)
        self.actions["redo"].setEnabled(False)
        self.undo_stack.canUndoChanged.connect(self.actions["undo"].setEnabled)
        self.undo_stack.canRedoChanged.connect(self.actions["redo"].setEnabled)
        self.undo_stack.undoTextChanged.connect(
            lambda text: self.actions["undo"].setText(
                f"Undo {text}" if text else "Undo"
            )
        )
        self.undo_stack.redoTextChanged.connect(
            lambda text: self.actions["redo"].setText(
                f"Redo {text}" if text else "Redo"
            )
        )
        self.undo_stack.cleanChanged.connect(
            lambda clean: self._set_dirty(not clean)
        )

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        self._update_window_title()

    def _update_window_title(self) -> None:
        display_name = (
            self._project_path.name
            if self._project_path is not None
            else self.project.name
        )
        marker = " *" if self._dirty else ""
        self.setWindowTitle(
            f"OpenSeesPy Studio (Beta) - [{display_name}]{marker}"
        )

    def _record_project_change(self, text: str, before: dict) -> None:
        after = self.project.to_dict()
        if before == after:
            return
        self.undo_stack.push(
            ProjectSnapshotCommand(
                text,
                before,
                after,
                self._apply_project_snapshot,
                already_applied=True,
            )
        )

    def _apply_project_snapshot(self, snapshot: dict) -> None:
        self.project = ProjectDatabase.from_dict(snapshot)
        self.model = self.project.model
        self.selection.clear()
        self._refresh_all()

    def _save_project(self) -> bool:
        if self._project_path is None:
            return self._save_project_as()
        try:
            self.project.save(self._project_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save project", str(exc))
            return False

        self.undo_stack.setClean()
        self._set_dirty(False)
        self.status_message.setText(f"Saved {self._project_path.name}")
        return True

    def _save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save OpenSeesPy Studio Project",
            str(self._project_path or Path("Untitled.opsstudio")),
            "OpenSeesPy Studio Project (*.opsstudio)",
        )
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".opsstudio":
            target = target.with_suffix(".opsstudio")
        self._project_path = target
        self.project.name = target.stem
        return self._save_project()

    def _open_project(self) -> None:
        if not self._maybe_save_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open OpenSeesPy Studio Project",
            "",
            "OpenSeesPy Studio Project (*.opsstudio);;All Files (*)",
        )
        if not path:
            return

        try:
            project = ProjectDatabase.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open project", str(exc))
            return

        self.selection.clear()
        self.project = project
        self.model = project.model
        self._project_path = Path(path)
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_dirty(False)
        self._refresh_all(f"Opened {self._project_path.name}")

    def _maybe_save_changes(self) -> bool:
        if not self._dirty:
            return True

        answer = QMessageBox.warning(
            self,
            "Unsaved changes",
            "The project has unsaved changes.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self._save_project()
        return True

    def _create_material(self) -> None:
        dialog = MaterialDialog(
            next_tag=self.project.next_material_tag(),
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            material = dialog.material_data()
            self.project.add_material(material)
        except ValueError as exc:
            QMessageBox.warning(self, "Material Editor", str(exc))
            return

        self._refresh_project_metadata(
            f"Created {material.material_type} material {material.tag}"
        )
        self._show_material_properties(material.tag)
        self._record_project_change(
            f"Create material {material.tag}",
            before,
        )

    def _edit_material(self, tag: int) -> None:
        material = self.project.materials.get(tag)
        if material is None:
            return

        dialog = MaterialDialog(material=material, parent=self)
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            updated = dialog.material_data()
            self.project.update_material(tag, updated)
            if updated.tag != tag:
                for section in self.project.sections.values():
                    if section.material_tag == tag:
                        section.material_tag = updated.tag
                    for fiber in section.fibers:
                        if fiber.material_tag == tag:
                            fiber.material_tag = updated.tag
        except ValueError as exc:
            QMessageBox.warning(self, "Material Editor", str(exc))
            return

        self._refresh_project_metadata(
            f"Updated material {updated.tag}"
        )
        self._show_material_properties(updated.tag)
        self._record_project_change(
            f"Edit material {tag}",
            before,
        )

    def _duplicate_material(self, tag: int) -> None:
        source = self.project.materials.get(tag)
        if source is None:
            return

        new_tag = self.project.next_material_tag()
        before = self.project.to_dict()
        duplicate = MaterialData(
            tag=new_tag,
            name=f"{source.name} Copy",
            material_type=source.material_type,
            parameters=dict(source.parameters),
            poisson_ratio=source.poisson_ratio,
            density=source.density,
        )
        self.project.add_material(duplicate)
        self._refresh_project_metadata(
            f"Duplicated material {tag} as {new_tag}"
        )
        self._show_material_properties(new_tag)
        self._record_project_change(
            f"Duplicate material {tag}",
            before,
        )

    def _delete_material(self, tag: int) -> None:
        material = self.project.materials.get(tag)
        if material is None:
            return

        used_by = self.project.sections_using_material(tag)
        if used_by:
            QMessageBox.warning(
                self,
                "Delete Material",
                "Material is used by section(s): "
                + ", ".join(map(str, used_by))
                + ". Reassign those section/material links first.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Material",
            f"Delete material {tag} ({material.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.project.remove_material(tag)
        self._refresh_project_metadata(f"Deleted material {tag}")
        self._record_project_change(
            f"Delete material {tag}",
            before,
        )

    def _show_material_properties(self, tag: int) -> None:
        material = self.project.materials.get(tag)
        if material is None:
            return
        rows: list[tuple[str, object]] = [
            ("Tag", material.tag),
            ("Name", material.name),
            ("Type", material.material_type),
            ("Poisson ratio", f"{material.poisson_ratio:g}"),
            ("Density", f"{material.density:g}"),
            ("Elastic E", f"{material.elastic_modulus():g}"),
            ("Elastic G", f"{material.shear_modulus():g}"),
        ]
        rows.extend(
            (key, f"{value:g}")
            for key, value in material.parameters.items()
        )
        self.properties_panel.set_properties("Material", rows)

    def _create_section(self) -> None:
        dialog = SectionDialog(
            self.project.materials,
            next_tag=self.project.next_section_tag(),
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            section = dialog.section_data()
            self.project.add_section(section)
        except ValueError as exc:
            QMessageBox.warning(self, "Section Editor", str(exc))
            return

        self._refresh_project_metadata(
            f"Created {section.section_type} section {section.tag}"
        )
        self._show_section_properties(section.tag)
        self._record_project_change(
            f"Create section {section.tag}",
            before,
        )

    def _edit_section(self, tag: int) -> None:
        section = self.project.sections.get(tag)
        if section is None:
            return

        dialog = SectionDialog(
            self.project.materials,
            section=section,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            updated = dialog.section_data()
            self.project.update_section(tag, updated)
            if updated.tag != tag:
                for element in self.model.elements.values():
                    if element.section_tag == tag:
                        element.section_tag = updated.tag
        except ValueError as exc:
            QMessageBox.warning(self, "Section Editor", str(exc))
            return

        self._refresh_project_metadata(
            f"Updated section {updated.tag}"
        )
        self._show_section_properties(updated.tag)
        self._record_project_change(
            f"Edit section {tag}",
            before,
        )

    def _duplicate_section(self, tag: int) -> None:
        source = self.project.sections.get(tag)
        if source is None:
            return

        new_tag = self.project.next_section_tag()
        before = self.project.to_dict()
        duplicate = SectionData.from_dict(source.to_dict())
        duplicate.tag = new_tag
        duplicate.name = f"{source.name} Copy"
        self.project.add_section(duplicate)
        self._refresh_project_metadata(
            f"Duplicated section {tag} as {new_tag}"
        )
        self._show_section_properties(new_tag)
        self._record_project_change(
            f"Duplicate section {tag}",
            before,
        )

    def _delete_section(self, tag: int) -> None:
        section = self.project.sections.get(tag)
        if section is None:
            return

        used_by = sorted(
            element.tag
            for element in self.model.elements.values()
            if element.section_tag == tag
        )
        if used_by:
            QMessageBox.warning(
                self,
                "Delete Section",
                "Section is assigned to element(s): "
                + ", ".join(map(str, used_by[:20]))
                + ("..." if len(used_by) > 20 else ""),
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Section",
            f"Delete section {tag} ({section.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.project.remove_section(tag)
        self._refresh_project_metadata(f"Deleted section {tag}")
        self._record_project_change(
            f"Delete section {tag}",
            before,
        )

    def _show_section_properties(self, tag: int) -> None:
        section = self.project.sections.get(tag)
        if section is None:
            return

        rows: list[tuple[str, object]] = [
            ("Tag", section.tag),
            ("Name", section.name),
            ("Type", section.section_type),
        ]

        if section.section_type == "Elastic":
            if section.material_tag is None:
                rows.append(("Material", "Manual"))
                resolved = section.resolved_elastic_parameters()
            else:
                material = self.project.materials.get(section.material_tag)
                material_text = (
                    f"{section.material_tag} - {material.name}"
                    if material is not None
                    else f"{section.material_tag} (missing)"
                )
                rows.append(("Material", material_text))
                try:
                    resolved = section.resolved_elastic_parameters(
                        self.project.materials
                    )
                except ValueError:
                    resolved = dict(section.parameters)

            for key in ("A", "Iz", "Iy", "J"):
                rows.append((key, f"{resolved[key]:g}"))
            rows.append(("Resolved E", f"{resolved['E']:g}"))
            rows.append(("Resolved G", f"{resolved['G']:g}"))
            if section.material_tag is not None:
                material = self.project.materials.get(section.material_tag)
                if material is not None:
                    rows.append(("Density", f"{material.density:g}"))
        else:
            rows.extend(
                (key, f"{value:g}")
                for key, value in section.parameters.items()
            )
            rows.append(("Fibers", len(section.fibers)))
            material_tags = sorted({
                fiber.material_tag
                for fiber in section.fibers
            })
            rows.append((
                "Materials",
                ", ".join(map(str, material_tags)) or "-",
            ))

        self.properties_panel.set_properties("Section", rows)

    def _create_transformation(self) -> None:
        dialog = TransformationDialog(
            next_tag=self.project.next_transformation_tag(),
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            transformation = dialog.transformation_data()
            self.project.add_transformation(transformation)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Transformation Editor",
                str(exc),
            )
            return

        self._refresh_project_metadata(
            f"Created {transformation.transformation_type} "
            f"transformation {transformation.tag}"
        )
        self._show_transformation_properties(transformation.tag)
        self._record_project_change(
            f"Create transformation {transformation.tag}",
            before,
        )

    def _edit_transformation(self, tag: int) -> None:
        transformation = self.project.transformations.get(tag)
        if transformation is None:
            return

        dialog = TransformationDialog(
            transformation=transformation,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            updated = dialog.transformation_data()
            self.project.update_transformation(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Transformation Editor",
                str(exc),
            )
            return

        if updated.tag != tag:
            for element in self.model.elements.values():
                if element.transf_tag == tag:
                    element.transf_tag = updated.tag

        self._refresh_project_metadata(
            f"Updated transformation {updated.tag}"
        )
        self._show_transformation_properties(updated.tag)
        self._record_project_change(
            f"Edit transformation {tag}",
            before,
        )

    def _duplicate_transformation(self, tag: int) -> None:
        source = self.project.transformations.get(tag)
        if source is None:
            return

        new_tag = self.project.next_transformation_tag()
        before = self.project.to_dict()
        duplicate = TransformationData(
            tag=new_tag,
            name=f"{source.name} Copy",
            transformation_type=source.transformation_type,
            vecxz=source.vecxz,
        )
        self.project.add_transformation(duplicate)
        self._refresh_project_metadata(
            f"Duplicated transformation {tag} as {new_tag}"
        )
        self._show_transformation_properties(new_tag)
        self._record_project_change(
            f"Duplicate transformation {tag}",
            before,
        )

    def _delete_transformation(self, tag: int) -> None:
        transformation = self.project.transformations.get(tag)
        if transformation is None:
            return

        used_by = sorted(
            element.tag
            for element in self.model.elements.values()
            if element.transf_tag == tag
        )
        if used_by:
            QMessageBox.warning(
                self,
                "Delete Transformation",
                "Transformation is assigned to element(s): "
                + ", ".join(map(str, used_by[:20]))
                + ("..." if len(used_by) > 20 else ""),
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Transformation",
            f"Delete transformation {tag} ({transformation.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.project.remove_transformation(tag)
        self._refresh_project_metadata(
            f"Deleted transformation {tag}"
        )
        self._record_project_change(
            f"Delete transformation {tag}",
            before,
        )

    def _show_transformation_properties(self, tag: int) -> None:
        transformation = self.project.transformations.get(tag)
        if transformation is None:
            return
        self.properties_panel.set_properties(
            "Transformation",
            [
                ("Tag", transformation.tag),
                ("Name", transformation.name),
                ("Type", transformation.transformation_type),
                ("vecxz X", f"{transformation.vecxz[0]:g}"),
                ("vecxz Y", f"{transformation.vecxz[1]:g}"),
                ("vecxz Z", f"{transformation.vecxz[2]:g}"),
            ],
        )

    def _create_named_selection(self) -> None:
        nodes, elements = self._selection_sets()
        if not nodes and not elements:
            QMessageBox.information(
                self,
                "Named Selection",
                "Select at least one node or element first.",
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "Create Named Selection",
            "Name:",
        )
        name = name.strip()
        if not ok or not name:
            return
        if name in self.project.selection_sets:
            QMessageBox.warning(
                self,
                "Named Selection",
                f"A named selection called '{name}' already exists.",
            )
            return

        before = self.project.to_dict()
        self.project.selection_sets[name] = SelectionSetData(
            name=name,
            node_tags=set(nodes),
            element_tags=set(elements),
        )
        self._refresh_tree()
        self._record_project_change(f"Create named selection {name}", before)
        self.status_message.setText(f"Created named selection: {name}")

    def _show_tree_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        payload = item.data(0, Qt.UserRole)
        if not payload:
            return

        kind, value = payload
        menu = QMenu(self)

        if kind == "materials_root":
            create_action = menu.addAction("New Material...")
            create_action.triggered.connect(self._create_material)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "material":
            tag = int(value)
            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(
                lambda: self._edit_material(tag)
            )
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(
                lambda: self._duplicate_material(tag)
            )
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_material(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "sections_root":
            create_action = menu.addAction("New Section...")
            create_action.triggered.connect(self._create_section)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "section":
            tag = int(value)
            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(
                lambda: self._edit_section(tag)
            )
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(
                lambda: self._duplicate_section(tag)
            )
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_section(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "transformations_root":
            create_action = menu.addAction("New Transformation...")
            create_action.triggered.connect(self._create_transformation)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "transformation":
            tag = int(value)
            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(
                lambda: self._edit_transformation(tag)
            )
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(
                lambda: self._duplicate_transformation(tag)
            )
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_transformation(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind != "set":
            return

        name = str(value)
        select_action = menu.addAction("Select")
        select_action.triggered.connect(
            lambda: self._select_named_selection(name)
        )

        update_action = menu.addAction("Update from Current Selection")
        update_action.triggered.connect(
            lambda: self._update_named_selection(name)
        )

        menu.addSeparator()
        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(
            lambda: self._rename_named_selection(name)
        )
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(
            lambda: self._delete_named_selection(name)
        )

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _tree_item_double_clicked(self, item, column: int) -> None:
        payload = item.data(0, Qt.UserRole)
        if not payload:
            return
        kind, value = payload
        if kind == "material":
            self._edit_material(int(value))
        elif kind == "section":
            self._edit_section(int(value))
        elif kind == "transformation":
            self._edit_transformation(int(value))

    def _select_named_selection(self, name: str) -> None:
        selection_set = self.project.selection_sets.get(name)
        if selection_set is None:
            return
        self.selection.set_selection(
            nodes=set(selection_set.node_tags),
            elements=set(selection_set.element_tags),
        )

    def _update_named_selection(self, name: str) -> None:
        selection_set = self.project.selection_sets.get(name)
        if selection_set is None:
            return
        nodes, elements = self._selection_sets()
        if not nodes and not elements:
            return

        before = self.project.to_dict()
        selection_set.node_tags = set(nodes)
        selection_set.element_tags = set(elements)
        self._refresh_tree()
        self._record_project_change(f"Update named selection {name}", before)

    def _rename_named_selection(self, old_name: str) -> None:
        selection_set = self.project.selection_sets.get(old_name)
        if selection_set is None:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Named Selection",
            "Name:",
            text=old_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if new_name in self.project.selection_sets:
            QMessageBox.warning(
                self,
                "Named Selection",
                f"A named selection called '{new_name}' already exists.",
            )
            return

        before = self.project.to_dict()
        self.project.selection_sets.pop(old_name)
        selection_set.name = new_name
        self.project.selection_sets[new_name] = selection_set
        self._refresh_tree()
        self._record_project_change(
            f"Rename named selection {old_name}",
            before,
        )

    def _delete_named_selection(self, name: str) -> None:
        if name not in self.project.selection_sets:
            return
        before = self.project.to_dict()
        self.project.selection_sets.pop(name)
        self._refresh_tree()
        self._record_project_change(f"Delete named selection {name}", before)

    def _prune_selection_sets(self) -> None:
        node_tags = set(self.model.nodes)
        element_tags = set(self.model.elements)
        for selection_set in self.project.selection_sets.values():
            selection_set.node_tags.intersection_update(node_tags)
            selection_set.element_tags.intersection_update(element_tags)

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

    def _toggle_analysis(self) -> None:
        if self._analysis_process is not None:
            if self._analysis_process.state() != QProcess.NotRunning:
                self._stop_analysis()
                return
        self._start_analysis()

    def _start_analysis(self) -> None:
        script_text = self.script.toPlainText()
        if not script_text.strip():
            QMessageBox.information(self, "Run", "The generated script is empty.")
            return

        fd, path = tempfile.mkstemp(
            prefix="openseespy_studio_",
            suffix=".py",
            text=True,
        )
        os.close(fd)
        Path(path).write_text(script_text, encoding="utf-8")
        self._analysis_script_path = path

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments([
            "-m",
            "openseespy_studio.solver_worker",
            path,
        ])
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_analysis_stdout)
        process.readyReadStandardError.connect(self._read_analysis_stderr)
        process.finished.connect(self._analysis_finished)
        process.errorOccurred.connect(self._analysis_process_error)
        self._analysis_process = process

        self.console.appendPlainText(
            f">> Starting analysis worker with {Path(sys.executable).name}..."
        )
        self.status_message.setText("Analysis running...")
        self.actions["run"].setText("Stop")
        self.actions["run"].setToolTip("Stop running analysis")
        process.start()

    def _stop_analysis(self) -> None:
        process = self._analysis_process
        if process is None or process.state() == QProcess.NotRunning:
            return

        self.console.appendPlainText(">> Stopping analysis worker...")
        self.status_message.setText("Stopping analysis...")
        process.terminate()
        QTimer.singleShot(2000, self._kill_analysis_if_needed)

    def _kill_analysis_if_needed(self) -> None:
        process = self._analysis_process
        if process is not None and process.state() != QProcess.NotRunning:
            self.console.appendPlainText(
                ">> Worker did not stop in time; forcing termination."
            )
            process.kill()

    def _read_analysis_stdout(self) -> None:
        process = self._analysis_process
        if process is None:
            return
        text = bytes(process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )
        if text:
            self.console.moveCursor(QTextCursor.End)
            self.console.insertPlainText(text)

    def _read_analysis_stderr(self) -> None:
        process = self._analysis_process
        if process is None:
            return
        text = bytes(process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )
        if text:
            self.console.moveCursor(QTextCursor.End)
            self.console.insertPlainText(text)

    def _analysis_process_error(self, error) -> None:
        process = self._analysis_process
        if process is None:
            return
        self.console.appendPlainText(
            f"\n>> Analysis worker process error: {process.errorString()}"
        )

    def _analysis_finished(self, exit_code: int, exit_status) -> None:
        crashed = exit_status == QProcess.CrashExit
        if crashed:
            self.console.appendPlainText(
                f"\n>> Analysis worker crashed (exit code {exit_code}). "
                "The Studio GUI remains available."
            )
            self.status_message.setText("Analysis worker crashed")
        elif exit_code == 0:
            self.console.appendPlainText(
                "\n>> Analysis worker completed successfully."
            )
            self.status_message.setText("Analysis completed")
        else:
            self.console.appendPlainText(
                f"\n>> Analysis worker exited with code {exit_code}."
            )
            self.status_message.setText(
                f"Analysis failed (exit code {exit_code})"
            )

        self.actions["run"].setText("Run")
        self.actions["run"].setToolTip("Run model")
        self._cleanup_analysis_script()
        self._analysis_process = None

    def _cleanup_analysis_script(self) -> None:
        path = self._analysis_script_path
        self._analysis_script_path = None
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def closeEvent(self, event) -> None:
        if not self._maybe_save_changes():
            event.ignore()
            return
        process = self._analysis_process
        if process is not None and process.state() != QProcess.NotRunning:
            process.kill()
            process.waitForFinished(1000)
        self._cleanup_analysis_script()
        super().closeEvent(event)

    def _not_implemented(self) -> None:
        action = self.sender()
        label = action.text() if isinstance(action, QAction) else "Command"
        self._log(f"{label}: planned for the next milestone")

    def _log(self, text: str) -> None:
        self.console.appendPlainText(">> " + text)
