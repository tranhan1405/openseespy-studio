from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import tempfile

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QKeySequence, QPainter, QPen, QShortcut, QTextCursor, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
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

from ..frame_setup import prepare_frame_grid
from ..generator import FrameGridSpec, cyclic_displacement_steps, generate_frame_grid, to_openseespy
from ..jobs import JobRecord
from ..live_convergence import parse_opensees_convergence_line
from ..model import StructuralModel, classify_fixity
from ..postprocess import enrich_fiber_state_results, enrich_member_force_results
from ..result_catalog import (
    convergence_result_label,
    result_choices_for_analysis,
)
from ..project import AnalysisSettingsData, ConnectionData, ConstraintData, ElementLoadData, LoadPatternData, MaterialData, NodalLoadData, ProjectDatabase, RecorderData, SectionData, SelectionSetData, SolutionResultData, TimeSeriesData, TransformationData
from ..runtime import build_worker_pythonpath, probe_opensees_runtime
from ..validation import ValidationIssue, validate_project
from ..units import UnitSystem
from .analysis_dialog import AnalysisDialog
from .code_editor import CodeEditor
from .connection_dialog import ConnectionDialog
from .constraint_dialog import ConstraintDialog
from .geometry_dialogs import (
    ElementDialog,
    ElementFormulationDialog,
    MirrorDialog,
    NodeDialog,
    RotateDialog,
    SelectByIdDialog,
    VectorDialog,
)
from .history import ProjectSnapshotCommand
from .load_dialogs import ElementLoadDialog, LoadPatternDialog, MassDialog, NodalLoadDialog, TimeSeriesDialog
from .material_dialog import MaterialDialog
from .model_check_dialog import ModelCheckDialog
from .recorder_dialog import RecorderDialog
from .section_dialog import SectionDialog
from .transformation_dialog import TransformationDialog
from .icons import studio_icon
from .results_panel import ResultsPanel
from .restraint_dialog import RestraintDialog
from .selection import SelectionManager, parse_tag_expression
from .viewport import ModelViewport


APP_STYLE = """
QMainWindow {
    background: #eef2f6;
    color: #23364a;
}
QMainWindow::separator {
    background: #c7d0da;
    width: 5px;
    height: 5px;
}
QMainWindow::separator:hover {
    background: #2f80ed;
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

        for combo in (self.column_section, self.beam_section):
            combo.clear()
            combo.addItem("None", None)

        self.column_transformation.clear()
        self.column_transformation.addItem(
            "Auto (Column_PDelta)", None
        )
        self.beam_transformation.clear()
        self.beam_transformation.addItem(
            "Auto (Beam_Linear)", None
        )

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

    def set_assignment_tags(
        self,
        *,
        column_section_tag: int | None = None,
        beam_section_tag: int | None = None,
        column_transf_tag: int | None = None,
        beam_transf_tag: int | None = None,
    ) -> None:
        for combo, value in (
            (self.column_section, column_section_tag),
            (self.beam_section, beam_section_tag),
            (self.column_transformation, column_transf_tag),
            (self.beam_transformation, beam_transf_tag),
        ):
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)

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
    solution_result_apply = Signal(int, object)
    solution_result_evaluate = Signal(int, object)
    solution_scope_from_selection = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._solution_result_tag: int | None = None

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

        self.result_editor = QWidget()
        result_layout = QVBoxLayout(self.result_editor)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(5)

        self.result_form = QFormLayout()
        self.result_name = QLineEdit()
        self.result_analysis = QLineEdit()
        self.result_analysis.setReadOnly(True)
        self.result_type = QLineEdit()
        self.result_type.setReadOnly(True)
        self.result_data_source = QComboBox()
        self.result_data_source.addItem("Latest Job", "latest")
        self.result_frame = QComboBox()
        self.result_frame.setEnabled(False)

        self.result_node_scope = QLineEdit()
        self.result_node_scope.setPlaceholderText("All nodes")
        self.result_element_scope = QLineEdit()
        self.result_element_scope.setPlaceholderText("All elements")
        self.result_use_selection = QPushButton("Use Current Selection")
        self.result_use_selection.clicked.connect(
            self._request_current_selection
        )

        self.result_component = QComboBox()
        self.result_scale = QDoubleSpinBox()
        self.result_scale.setDecimals(6)
        self.result_scale.setRange(1.0e-6, 1.0e9)
        self.result_scale.setValue(1.0)

        self.result_mode = QSpinBox()
        self.result_mode.setRange(1, 100000)

        self.result_history_node = QSpinBox()
        self.result_history_node.setRange(1, 2147483647)
        self.result_history_quantity = QComboBox()
        self.result_history_quantity.addItems(
            [
                "Displacement",
                "Velocity",
                "Acceleration",
                "Reaction",
                "Base shear",
            ]
        )
        self.result_history_dof = QSpinBox()
        self.result_history_dof.setRange(1, 6)

        self.result_fiber_section = QSpinBox()
        self.result_fiber_section.setRange(1, 100000)

        rows = (
            ("Name", self.result_name),
            ("Analysis", self.result_analysis),
            ("Result Type", self.result_type),
            ("Data Source", self.result_data_source),
            ("Frame", self.result_frame),
            ("Node Scope", self.result_node_scope),
            ("Element Scope", self.result_element_scope),
            ("Scope", self.result_use_selection),
            ("Component", self.result_component),
            ("Scale", self.result_scale),
            ("Mode", self.result_mode),
            ("History Node", self.result_history_node),
            ("History Quantity", self.result_history_quantity),
            ("History DOF", self.result_history_dof),
            ("Section / IP", self.result_fiber_section),
        )
        for label, widget in rows:
            self.result_form.addRow(label + ":", widget)
        result_layout.addLayout(self.result_form)
        result_layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.result_apply_button = QPushButton("Apply")
        self.result_evaluate_button = QPushButton("Evaluate")
        self.result_apply_button.clicked.connect(
            self._emit_solution_result_apply
        )
        self.result_evaluate_button.clicked.connect(
            self._emit_solution_result_evaluate
        )
        button_row.addWidget(self.result_apply_button)
        button_row.addWidget(self.result_evaluate_button)
        result_layout.addLayout(button_row)

        layout.addWidget(self.result_editor, 1)
        self.result_editor.hide()

        row = QHBoxLayout()
        row.addStretch(1)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        row.addWidget(self.apply_button)
        layout.addLayout(row)

        self._result_optional_widgets = (
            self.result_component,
            self.result_scale,
            self.result_mode,
            self.result_history_node,
            self.result_history_quantity,
            self.result_history_dof,
            self.result_fiber_section,
        )

    def _set_form_row_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(bool(visible))
        label = self.result_form.labelForField(widget)
        if label is not None:
            label.setVisible(bool(visible))

    def set_properties(self, title: str, rows: list[tuple[str, object]]) -> None:
        self._solution_result_tag = None
        self.result_editor.hide()
        self.table.show()
        self.apply_button.show()
        self.entity_label.setText(title)
        self.table.setRowCount(len(rows))
        for index, (key, value) in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(str(key)))
            self.table.setItem(index, 1, QTableWidgetItem(str(value)))

    def set_solution_result(
        self,
        result: SolutionResultData,
        *,
        analysis_name: str,
    ) -> None:
        self._solution_result_tag = int(result.tag)
        self.table.hide()
        self.apply_button.hide()
        self.result_editor.show()
        self.entity_label.setText(result.name)

        self.result_name.setText(result.name)
        self.result_analysis.setText(str(analysis_name))
        self.result_type.setText(result.result_type)
        self.result_node_scope.setText(
            ", ".join(map(str, result.node_scope))
        )
        self.result_element_scope.setText(
            ", ".join(map(str, result.element_scope))
        )

        for widget in self._result_optional_widgets:
            self._set_form_row_visible(widget, False)

        kind = result.result_type
        options = dict(result.settings)

        if kind in {
            "DeformedShape",
            "NodalDisplacement",
            "NodalReaction",
            "MemberForce",
            "FiberStress",
            "FiberStrain",
            "HingeState",
        }:
            self.result_frame.clear()
            self.result_frame.addItem("Final", "final")
        elif kind == "ModeShape":
            self.result_frame.clear()
            self.result_frame.addItem("Mode", "mode")
        else:
            self.result_frame.clear()
            self.result_frame.addItem("All Frames", "all")

        component_options: list[str] = []
        if kind == "NodalDisplacement":
            component_options = [
                "|U|", "UX", "UY", "UZ", "|R|", "RX", "RY", "RZ"
            ]
        elif kind == "NodalReaction":
            component_options = [
                "|F|", "FX", "FY", "FZ", "|M|", "MX", "MY", "MZ"
            ]
        elif kind == "MemberForce":
            component_options = ["N", "Vy", "Vz", "T", "My", "Mz"]

        if component_options:
            self._set_form_row_visible(self.result_component, True)
            self.result_component.clear()
            self.result_component.addItems(component_options)
            component = str(
                options.get("component", component_options[0])
            )
            index = self.result_component.findText(component)
            self.result_component.setCurrentIndex(
                index if index >= 0 else 0
            )

        if kind in {"DeformedShape", "MemberForce", "ModeShape"}:
            self._set_form_row_visible(self.result_scale, True)
            try:
                self.result_scale.setValue(
                    float(options.get(
                        "scale",
                        10.0 if kind == "DeformedShape" else 1.0,
                    ))
                )
            except (TypeError, ValueError):
                self.result_scale.setValue(1.0)

        if kind == "ModeShape":
            self._set_form_row_visible(self.result_mode, True)
            self.result_mode.setValue(
                max(1, int(options.get("mode", 1)))
            )

        if kind == "TimeHistory":
            for widget in (
                self.result_history_node,
                self.result_history_quantity,
                self.result_history_dof,
            ):
                self._set_form_row_visible(widget, True)
            self.result_history_node.setValue(
                max(1, int(options.get("node", 1)))
            )
            quantity = str(options.get("quantity", "Displacement"))
            index = self.result_history_quantity.findText(quantity)
            self.result_history_quantity.setCurrentIndex(
                index if index >= 0 else 0
            )
            self.result_history_dof.setValue(
                max(1, min(6, int(options.get("dof", 1))))
            )

        if kind in {"FiberStress", "FiberStrain"}:
            self._set_form_row_visible(
                self.result_fiber_section,
                True,
            )
            self.result_fiber_section.setValue(
                max(1, int(options.get("section", 1)))
            )

    def set_solution_scope(
        self,
        nodes: set[int],
        elements: set[int],
    ) -> None:
        self.result_node_scope.setText(
            ", ".join(map(str, sorted(nodes)))
        )
        self.result_element_scope.setText(
            ", ".join(map(str, sorted(elements)))
        )

    def _request_current_selection(self) -> None:
        if self._solution_result_tag is not None:
            self.solution_scope_from_selection.emit(
                self._solution_result_tag
            )

    def _solution_payload(self) -> dict[str, object]:
        kind = self.result_type.text()
        settings: dict[str, object] = {}

        if kind in {
            "NodalDisplacement",
            "NodalReaction",
            "MemberForce",
        }:
            settings["component"] = self.result_component.currentText()
        if kind in {"DeformedShape", "MemberForce", "ModeShape"}:
            settings["scale"] = self.result_scale.value()
        if kind == "ModeShape":
            settings["mode"] = self.result_mode.value()
        if kind == "TimeHistory":
            settings.update({
                "node": self.result_history_node.value(),
                "quantity": self.result_history_quantity.currentText(),
                "dof": self.result_history_dof.value(),
            })
        if kind in {"FiberStress", "FiberStrain"}:
            settings["section"] = self.result_fiber_section.value()
            settings["quantity"] = (
                "Stress" if kind == "FiberStress" else "Strain"
            )

        return {
            "name": self.result_name.text().strip(),
            "node_scope": self.result_node_scope.text().strip(),
            "element_scope": self.result_element_scope.text().strip(),
            "settings": settings,
        }

    def _emit_solution_result_apply(self) -> None:
        if self._solution_result_tag is not None:
            self.solution_result_apply.emit(
                self._solution_result_tag,
                self._solution_payload(),
            )

    def _emit_solution_result_evaluate(self) -> None:
        if self._solution_result_tag is not None:
            self.solution_result_evaluate.emit(
                self._solution_result_tag,
                self._solution_payload(),
            )


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
        self._analysis_result_path: str | None = None
        self._analysis_log_path: str | None = None
        self._analysis_stdout_buffer = ""
        self._analysis_stderr_buffer = ""
        self._analysis_external_console = False
        self._external_log_paths: list[str] = []
        self._analysis_stop_requested = False
        self._jobs: dict[int, JobRecord] = {}
        self._job_counter = 0
        self._current_job_id: int | None = None
        self._live_convergence_context: dict[str, object] = {
            "step": 0,
            "total": 0,
            "algorithm": "",
            "test": "",
            "tolerance": None,
            "enabled": False,
        }
        self._last_result: dict[str, object] = {}
        self._active_solution_result_tag: int | None = None
        self._results_dock_sized_once = False
        self._dirty = False
        self._job_ui_timer = QTimer(self)
        self._job_ui_timer.setInterval(1000)
        self._job_ui_timer.timeout.connect(self._refresh_running_job_ui)

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
        self.properties_panel.solution_result_apply.connect(
            self._apply_solution_result_details
        )
        self.properties_panel.solution_result_evaluate.connect(
            self._evaluate_solution_result_details
        )
        self.properties_panel.solution_scope_from_selection.connect(
            self._use_current_selection_for_solution_result
        )
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
        script_dock.setMinimumWidth(120)

        script_tabs = QTabWidget()
        script_tabs.setDocumentMode(True)
        script_tabs.setMinimumWidth(0)
        script_tabs.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Expanding,
        )
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
        console_dock.setMinimumWidth(120)
        self.console = QPlainTextEdit()
        self.console.setMinimumWidth(0)
        self.console.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Expanding,
        )
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))
        console_dock.setWidget(self.console)
        self.splitDockWidget(script_dock, console_dock, Qt.Horizontal)

        results_dock = QDockWidget("Results Viewer", self)
        results_dock.setObjectName("ResultsDock")
        results_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        results_dock.setMinimumWidth(80)
        self.results_panel = ResultsPanel()
        self.results_panel.setMinimumWidth(0)
        self.results_panel.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Expanding,
        )
        self.results_panel.deformation_requested.connect(
            self._show_deformation_result
        )
        self.results_panel.mode_shape_requested.connect(
            self._show_mode_shape_result
        )
        self.results_panel.member_force_requested.connect(
            self._show_member_force_result
        )
        self.results_panel.node_contour_requested.connect(
            self._show_node_contour_result
        )
        self.results_panel.hinge_state_requested.connect(
            self._show_hinge_state_result
        )
        self.results_panel.element_selected.connect(
            self._select_result_element
        )
        self.results_panel.clear_overlay_requested.connect(
            self.viewport.clear_result_overlay
        )
        self.results_panel.job_selected.connect(self._select_job_result)
        results_dock.setWidget(self.results_panel)
        self.splitDockWidget(console_dock, results_dock, Qt.Horizontal)

        self.script_dock = script_dock
        self.console_dock = console_dock
        self.results_dock = results_dock
        self.results_dock.visibilityChanged.connect(
            self._results_dock_visibility_changed
        )
        self.results_dock.hide()

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
        self._make_action(
            "element_formulation",
            "Element Formulation...",
            "element",
            self._set_element_formulation,
            "Set elastic, force-based, or displacement-based formulation",
        )
        self._make_action(
            "support",
            "Support...",
            "boundary",
            self._apply_restraint,
            "Apply support / restraint to selected nodes",
        )
        self._make_action(
            "clear_support",
            "Clear Support",
            "boundary",
            self._clear_restraint,
            "Clear restraint on selected nodes",
        )
        self._make_action(
            "constraint",
            "Constraint...",
            "transform",
            self._create_constraint,
            "Create equalDOF, rigidLink, or rigidDiaphragm",
        )
        self._make_action(
            "connection",
            "Connection...",
            "element",
            self._create_connection,
            "Create zeroLength or twoNodeLink spring / link",
        )
        self._make_action("mass", "Mass...", "load", self._assign_mass, "Assign nodal mass")
        self._make_action("time_series", "Time Series...", "timeseries", self._create_time_series, "Create time series")
        self._make_action("load_pattern", "Load Pattern...", "load", self._create_load_pattern, "Create load pattern or ground motion")
        self._make_action("nodal_load", "Nodal Load...", "load", self._create_nodal_load, "Create nodal load")
        self._make_action("beam_load", "Beam Load...", "load", self._create_element_load, "Create uniform, point, or self-weight beam load")
        self._make_action("analysis_setup", "Analysis Setup...", "analysis", self._create_analysis, "Create analysis settings")
        self._make_action("check_model", "Check Model", "analysis", self._check_model, "Validate the model before analysis")
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
        menus["Model"].addAction(self.actions["element_formulation"])
        menus["Geometry"].addActions([
            self.actions["node"], self.actions["line"], self.actions["frame"],
            self.actions["grid"], self.actions["extrude"],
        ])
        menus["View"].addActions([
            self.actions["xy"], self.actions["yz"], self.actions["xz"], self.actions["iso"],
        ])
        menus["Loads"].addAction(self.actions["support"])
        menus["Loads"].addAction(self.actions["clear_support"])
        menus["Loads"].addSeparator()
        menus["Loads"].addAction(self.actions["constraint"])
        menus["Loads"].addAction(self.actions["connection"])
        menus["Loads"].addSeparator()
        menus["Loads"].addAction(self.actions["mass"])
        menus["Loads"].addAction(self.actions["time_series"])
        menus["Loads"].addAction(self.actions["load_pattern"])
        menus["Loads"].addAction(self.actions["nodal_load"])
        menus["Loads"].addAction(self.actions["beam_load"])
        menus["Analysis"].addAction(self.actions["analysis_setup"])
        menus["Analysis"].addAction(self.actions["check_model"])
        menus["Analysis"].addAction(self.actions["run"])
        menus["Results"].addAction(self.actions["plot"])

        menus["Window"].addAction(self.model_tree_dock.toggleViewAction())
        menus["Window"].addAction(self.properties_dock.toggleViewAction())
        menus["Window"].addAction(self.script_dock.toggleViewAction())
        menus["Window"].addAction(self.console_dock.toggleViewAction())
        menus["Window"].addAction(self.results_dock.toggleViewAction())
        menus["Window"].addAction(self.create_dock.toggleViewAction())
        menus["Window"].addSeparator()
        reset_layout = QAction("Reset Dock Layout", self)
        reset_layout.triggered.connect(self._reset_dock_layout)
        menus["Window"].addAction(reset_layout)

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
            ("Supports", ["support", "clear_support", "constraint", "connection"]),
            ("Loads", ["mass", "time_series", "load_pattern", "nodal_load", "beam_load"]),
            ("Analysis", ["analysis_setup", "check_model", "run", "plot"]),
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
        self.status_units = QLabel("Units: m, kN, s · mass t")
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
        self.resizeDocks(
            [self.model_tree_dock, self.create_dock],
            [275, 340],
            Qt.Horizontal,
        )
        self.resizeDocks(
            [self.model_tree_dock, self.properties_dock],
            [575, 230],
            Qt.Vertical,
        )
        self.resizeDocks(
            [self.script_dock, self.console_dock],
            [620, 360],
            Qt.Horizontal,
        )
        self.resizeDocks(
            [self.script_dock],
            [245],
            Qt.Vertical,
        )

    def _results_dock_visibility_changed(self, visible: bool) -> None:
        if not visible or self._results_dock_sized_once:
            return
        self._results_dock_sized_once = True
        QTimer.singleShot(0, self._size_bottom_docks_with_results)

    def _size_bottom_docks_with_results(self) -> None:
        if not self.results_dock.isVisible():
            return
        self.resizeDocks(
            [self.script_dock, self.console_dock, self.results_dock],
            [560, 300, 320],
            Qt.Horizontal,
        )

    def _reset_dock_layout(self) -> None:
        self.model_tree_dock.show()
        self.properties_dock.show()
        self.script_dock.show()
        self.console_dock.show()
        self.create_dock.show()
        self.results_dock.setVisible(bool(self._jobs))
        self._results_dock_sized_once = False
        self._size_initial_docks()
        if self.results_dock.isVisible():
            self._results_dock_visibility_changed(True)
        self.status_message.setText("Dock layout reset")

    def _create_default_model(self) -> None:
        spec = FrameGridSpec(nx=4, ny=3, nz=3)
        prepare_frame_grid(self.project, spec)
        generate_frame_grid(self.model, spec)
        self._refresh_all(
            "Generated default 4 × 3 bay, 3-storey frame "
            "with automatic geometric transformations"
        )
        self.frame_grid_panel.set_assignment_tags(
            column_transf_tag=spec.column_transf_tag,
            beam_transf_tag=spec.beam_transf_tag,
        )
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
        self._reset_runtime_results()
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
        try:
            created_transformations = prepare_frame_grid(
                self.project,
                spec,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Create Frame Grid", str(exc))
            return

        generate_frame_grid(self.model, spec)
        self._prune_selection_sets()
        self.project.prune_constraints()
        self.project.prune_connections()
        self.project.prune_nodal_loads()
        self.project.prune_element_loads()
        self.project.prune_recorders()

        if created_transformations:
            names = ", ".join(
                f"{item.name} [{item.tag}]"
                for item in created_transformations
            )
            message = (
                f"Generated {spec.nx} × {spec.ny} bay, "
                f"{spec.nz}-storey frame · created {names}"
            )
        else:
            message = (
                f"Generated {spec.nx} × {spec.ny} bay, "
                f"{spec.nz}-storey frame"
            )

        self._refresh_all(message)
        self.frame_grid_panel.set_assignment_tags(
            column_section_tag=spec.column_section_tag,
            beam_section_tag=spec.beam_section_tag,
            column_transf_tag=spec.column_transf_tag,
            beam_transf_tag=spec.beam_transf_tag,
        )
        self._record_project_change("Generate frame grid", before)

    def _refresh_all(self, message: str = "") -> None:
        self.viewport.draw_model(self.model, self.project.connections)
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
                self.project.constraints,
                self.project.connections,
                self.project.time_series,
                self.project.load_patterns,
                self.project.nodal_loads,
                self.project.analyses,
                self.project.active_analysis_tag,
                element_loads=self.project.element_loads,
                recorders=self.project.recorders,
                units=self.project.units,
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
        unit_system = UnitSystem.from_mapping(units)
        self.status_units.setText(
            f"Units: {unit_system.length}, {unit_system.force}, "
            f"{unit_system.time} · mass {unit_system.mass_label}"
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

        constrained_nodes = {
            tag: classify_fixity(node.fixity)
            for tag, node in self.model.nodes.items()
            if any(node.fixity)
        }
        boundary_root = QTreeWidgetItem([
            f"Boundary Conditions ({len(constrained_nodes)})"
        ])
        boundary_root.setIcon(0, studio_icon("boundary"))
        boundary_root.setData(0, Qt.UserRole, ("boundary_root", None))
        boundary_root.setExpanded(True)
        root.addChild(boundary_root)

        grouped: dict[str, list[int]] = {}
        for tag, support_type in constrained_nodes.items():
            grouped.setdefault(support_type, []).append(tag)

        support_order = [
            "Fixed",
            "Pinned",
            "Roller X",
            "Roller Y",
            "Roller Z",
            "Custom",
        ]
        for support_type in support_order:
            tags = sorted(grouped.get(support_type, []))
            if not tags:
                continue
            group_item = QTreeWidgetItem([
                f"{support_type} ({len(tags)})"
            ])
            group_item.setIcon(0, studio_icon("boundary"))
            group_item.setExpanded(True)
            boundary_root.addChild(group_item)
            for tag in tags:
                node_item = QTreeWidgetItem([f"Node {tag}"])
                node_item.setIcon(0, studio_icon("boundary"))
                node_item.setData(0, Qt.UserRole, ("node", tag))
                group_item.addChild(node_item)

        constraints_root = QTreeWidgetItem([
            f"Constraints ({len(self.project.constraints)})"
        ])
        constraints_root.setIcon(0, studio_icon("transform"))
        constraints_root.setData(0, Qt.UserRole, ("constraints_root", None))
        constraints_root.setExpanded(True)
        root.addChild(constraints_root)

        for tag in sorted(self.project.constraints):
            constraint = self.project.constraints[tag]
            item = QTreeWidgetItem([
                f"{constraint.constraint_type} [{tag}]  {constraint.name}"
            ])
            item.setIcon(0, studio_icon("transform"))
            item.setData(0, Qt.UserRole, ("constraint", tag))
            constraints_root.addChild(item)

        connections_root = QTreeWidgetItem([
            f"Connections ({len(self.project.connections)})"
        ])
        connections_root.setIcon(0, studio_icon("element"))
        connections_root.setData(0, Qt.UserRole, ("connections_root", None))
        connections_root.setExpanded(True)
        root.addChild(connections_root)

        connection_groups: dict[str, QTreeWidgetItem] = {}
        for connection_type in ("zeroLength", "twoNodeLink"):
            tags = [
                tag
                for tag, connection in self.project.connections.items()
                if connection.connection_type == connection_type
            ]
            group = QTreeWidgetItem([
                f"{connection_type} ({len(tags)})"
            ])
            group.setIcon(0, studio_icon("element"))
            group.setExpanded(True)
            connections_root.addChild(group)
            connection_groups[connection_type] = group

        for tag in sorted(self.project.connections):
            connection = self.project.connections[tag]
            item = QTreeWidgetItem([
                f"{connection.name} [{tag}]"
            ])
            item.setIcon(0, studio_icon("element"))
            item.setData(0, Qt.UserRole, ("connection", tag))
            connection_groups[connection.connection_type].addChild(item)

        mass_nodes = [
            tag for tag, node in self.model.nodes.items()
            if any(abs(value) > 0.0 for value in node.mass)
        ]
        masses_root = QTreeWidgetItem([f"Masses ({len(mass_nodes)})"])
        masses_root.setIcon(0, studio_icon("load"))
        masses_root.setData(0, Qt.UserRole, ("masses_root", None))
        root.addChild(masses_root)
        for tag in sorted(mass_nodes):
            item = QTreeWidgetItem([f"Node {tag}"])
            item.setIcon(0, studio_icon("load"))
            item.setData(0, Qt.UserRole, ("node", tag))
            masses_root.addChild(item)

        series_root = QTreeWidgetItem([f"Time Series ({len(self.project.time_series)})"])
        series_root.setIcon(0, studio_icon("timeseries"))
        series_root.setData(0, Qt.UserRole, ("time_series_root", None))
        series_root.setExpanded(True)
        root.addChild(series_root)
        for tag in sorted(self.project.time_series):
            series = self.project.time_series[tag]
            item = QTreeWidgetItem([f"{series.series_type} [{tag}]  {series.name}"])
            item.setIcon(0, studio_icon("timeseries"))
            item.setData(0, Qt.UserRole, ("time_series", tag))
            series_root.addChild(item)

        patterns_root = QTreeWidgetItem([f"Load Patterns ({len(self.project.load_patterns)})"])
        patterns_root.setIcon(0, studio_icon("load"))
        patterns_root.setData(0, Qt.UserRole, ("load_patterns_root", None))
        patterns_root.setExpanded(True)
        root.addChild(patterns_root)
        for tag in sorted(self.project.load_patterns):
            pattern = self.project.load_patterns[tag]
            item = QTreeWidgetItem([f"{pattern.pattern_type} [{tag}]  {pattern.name}"])
            item.setIcon(0, studio_icon("load"))
            item.setData(0, Qt.UserRole, ("load_pattern", tag))
            item.setExpanded(True)
            patterns_root.addChild(item)
            for load_tag in sorted(self.project.nodal_loads):
                load = self.project.nodal_loads[load_tag]
                if load.pattern_tag != tag:
                    continue
                load_item = QTreeWidgetItem([f"{load.name} [{load.tag}] → Node {load.node_tag}"])
                load_item.setIcon(0, studio_icon("load"))
                load_item.setData(0, Qt.UserRole, ("nodal_load", load.tag))
                item.addChild(load_item)
            for load_tag in sorted(self.project.element_loads):
                load = self.project.element_loads[load_tag]
                if load.pattern_tag != tag:
                    continue
                load_item = QTreeWidgetItem([
                    f"{load.load_type}: {load.name} [{load.tag}] "
                    f"→ Element {load.element_tag}"
                ])
                load_item.setIcon(0, studio_icon("load"))
                load_item.setData(
                    0,
                    Qt.UserRole,
                    ("element_load", load.tag),
                )
                item.addChild(load_item)

        analysis = QTreeWidgetItem([f"Analysis ({len(self.project.analyses)})"])
        analysis.setIcon(0, studio_icon("analysis"))
        analysis.setData(0, Qt.UserRole, ("analyses_root", None))
        analysis.setExpanded(True)
        for tag in sorted(self.project.analyses):
            settings = self.project.analyses[tag]
            active = " [Active]" if tag == self.project.active_analysis_tag else ""
            item = QTreeWidgetItem([f"{settings.analysis_type} [{tag}] {settings.name}{active}"])
            item.setIcon(0, studio_icon("analysis"))
            item.setData(0, Qt.UserRole, ("analysis", tag))
            item.setExpanded(True)
            analysis.addChild(item)

            settings_item = QTreeWidgetItem(["Analysis Settings"])
            settings_item.setIcon(0, studio_icon("analysis"))
            settings_item.setData(
                0,
                Qt.UserRole,
                ("analysis_settings", tag),
            )
            item.addChild(settings_item)

            solution_results = self.project.solution_results_for_analysis(tag)
            solution = QTreeWidgetItem([
                f"Solution ({len(solution_results)})"
            ])
            solution.setIcon(0, studio_icon("results"))
            solution.setData(0, Qt.UserRole, ("solution_root", tag))
            solution.setExpanded(True)
            item.addChild(solution)

            information = QTreeWidgetItem(["Solution Information"])
            information.setIcon(0, studio_icon("results"))
            information.setData(
                0,
                Qt.UserRole,
                ("solution_information", tag),
            )
            information.setExpanded(True)
            solution.addChild(information)

            solver_output = QTreeWidgetItem(["Solver Output"])
            solver_output.setIcon(0, studio_icon("results"))
            solver_output.setData(
                0,
                Qt.UserRole,
                ("solver_output", tag),
            )
            information.addChild(solver_output)

            convergence = QTreeWidgetItem([
                convergence_result_label(settings.test)
            ])
            convergence.setIcon(0, studio_icon("results"))
            convergence.setData(
                0,
                Qt.UserRole,
                ("solution_convergence", tag),
            )
            information.addChild(convergence)

            for result in solution_results:
                result_item = QTreeWidgetItem([result.name])
                result_item.setIcon(0, studio_icon("results"))
                result_item.setData(
                    0,
                    Qt.UserRole,
                    ("solution_result", result.tag),
                )
                solution.addChild(result_item)

        recorders = QTreeWidgetItem([
            f"Recorders ({len(self.project.recorders)})"
        ])
        recorders.setIcon(0, studio_icon("recorder"))
        recorders.setData(0, Qt.UserRole, ("recorders_root", None))
        recorders.setExpanded(True)
        analysis.addChild(recorders)
        for tag in sorted(self.project.recorders):
            recorder = self.project.recorders[tag]
            targets = ", ".join(map(str, recorder.target_tags))
            item = QTreeWidgetItem([
                f"{recorder.recorder_type} [{tag}] {recorder.name} "
                f"→ {targets}"
            ])
            item.setIcon(0, studio_icon("recorder"))
            item.setData(0, Qt.UserRole, ("recorder", tag))
            recorders.addChild(item)
        root.addChild(analysis)

        results = QTreeWidgetItem([f"Results / Jobs ({len(self._jobs)})"])
        results.setIcon(0, studio_icon("results"))
        results.setData(0, Qt.UserRole, ("jobs_root", None))
        results.setExpanded(True)
        for job_id in sorted(self._jobs, reverse=True):
            job = self._jobs[job_id]
            item = QTreeWidgetItem([
                f"Job {job_id} · {job.analysis_name} "
                f"({job.analysis_type}) · {job.status}"
            ])
            item.setIcon(0, studio_icon("results"))
            item.setData(0, Qt.UserRole, ("job", job_id))
            item.setExpanded(True)
            results.addChild(item)

            for plot in job.plots:
                if not isinstance(plot, dict):
                    continue
                plot_id = int(plot.get("plot_id", 0) or 0)
                if plot_id <= 0:
                    continue
                plot_item = QTreeWidgetItem([
                    str(plot.get("name", f"Result {plot_id}"))
                ])
                plot_item.setIcon(0, studio_icon("results"))
                plot_item.setData(
                    0,
                    Qt.UserRole,
                    ("job_plot", (job_id, plot_id)),
                )
                item.addChild(plot_item)
        root.addChild(results)

        self.tree.addTopLevelItem(root)

    def _tree_selection_changed(self) -> None:
        nodes: set[int] = set()
        elements: set[int] = set()
        material_tag: int | None = None
        section_tag: int | None = None
        transformation_tag: int | None = None
        constraint_tag: int | None = None
        connection_tag: int | None = None
        time_series_tag: int | None = None
        load_pattern_tag: int | None = None
        nodal_load_tag: int | None = None
        element_load_tag: int | None = None
        analysis_tag: int | None = None
        recorder_tag: int | None = None
        solution_result_tag: int | None = None
        solution_information_tag: int | None = None
        solver_output_tag: int | None = None
        solution_convergence_tag: int | None = None
        job_id: int | None = None
        job_plot_ref: tuple[int, int] | None = None
        show_jobs_root = False

        selected_payload_kinds: set[str] = set()
        for item in self.tree.selectedItems():
            payload = item.data(0, Qt.UserRole)
            if not payload:
                continue
            kind, tag = payload
            selected_payload_kinds.add(str(kind))
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
            elif kind == "constraint":
                constraint_tag = int(tag)
            elif kind == "connection":
                connection_tag = int(tag)
            elif kind == "time_series":
                time_series_tag = int(tag)
            elif kind == "load_pattern":
                load_pattern_tag = int(tag)
            elif kind == "nodal_load":
                nodal_load_tag = int(tag)
            elif kind == "element_load":
                element_load_tag = int(tag)
            elif kind == "analysis":
                analysis_tag = int(tag)
            elif kind == "analysis_settings":
                analysis_tag = int(tag)
            elif kind == "recorder":
                recorder_tag = int(tag)
            elif kind == "solution_result":
                solution_result_tag = int(tag)
            elif kind == "solution_information":
                solution_information_tag = int(tag)
            elif kind == "solver_output":
                solver_output_tag = int(tag)
            elif kind == "solution_convergence":
                solution_convergence_tag = int(tag)
            elif kind == "job":
                job_id = int(tag)
            elif kind == "job_plot":
                try:
                    job_plot_ref = (int(tag[0]), int(tag[1]))
                except (TypeError, ValueError, IndexError):
                    job_plot_ref = None
            elif kind == "jobs_root":
                show_jobs_root = True

        if (
            solution_result_tag is None
            and "solution_root" not in selected_payload_kinds
            and "solution_information" not in selected_payload_kinds
            and "solution_convergence" not in selected_payload_kinds
            and "solver_output" not in selected_payload_kinds
        ):
            self._active_solution_result_tag = None

        self.selection.set_selection(nodes=nodes, elements=elements)
        if material_tag is not None:
            self._show_material_properties(material_tag)
        elif section_tag is not None:
            self._show_section_properties(section_tag)
        elif transformation_tag is not None:
            self._show_transformation_properties(transformation_tag)
        elif constraint_tag is not None:
            self._show_constraint_properties(constraint_tag)
        elif connection_tag is not None:
            self._show_connection_properties(connection_tag)
        elif time_series_tag is not None:
            self._show_time_series_properties(time_series_tag)
        elif load_pattern_tag is not None:
            self._show_load_pattern_properties(load_pattern_tag)
        elif nodal_load_tag is not None:
            self._show_nodal_load_properties(nodal_load_tag)
        elif element_load_tag is not None:
            self._show_element_load_properties(element_load_tag)
        elif analysis_tag is not None:
            self._show_analysis_properties(analysis_tag)
        elif recorder_tag is not None:
            self._show_recorder_properties(recorder_tag)
        elif solution_result_tag is not None:
            self._show_solution_result_properties(solution_result_tag)
            self._evaluate_solution_result(solution_result_tag)
        elif solution_convergence_tag is not None:
            self._show_solution_information(
                solution_convergence_tag,
                "Convergence Monitor",
            )
            self._show_solution_convergence(solution_convergence_tag)
        elif solver_output_tag is not None:
            self._show_solution_information(
                solver_output_tag,
                "Solver Output",
            )
            self.console_dock.show()
            self.console_dock.raise_()
        elif solution_information_tag is not None:
            self._show_solution_information(
                solution_information_tag,
                "Solution Information",
            )
        elif job_plot_ref is not None:
            self._show_job_plot(
                job_plot_ref[0],
                job_plot_ref[1],
            )
        elif job_id is not None:
            self._select_job_result(job_id)
        elif show_jobs_root:
            self._show_jobs_summary()

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
        if (
            self._active_solution_result_tag is not None
            and self._active_solution_result_tag
            in self.project.solution_results
        ):
            self.status_message.setText(
                f"Selection for result scope: "
                f"{len(nodes)} node(s), {len(elements)} element(s)"
            )
            return

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
                    ("Support", classify_fixity(node.fixity)),
                    ("Fixity", node.fixity),
                    ("UX", "Fixed" if node.fixity[0] else "Free"),
                    ("UY", "Fixed" if node.fixity[1] else "Free"),
                    ("UZ", "Fixed" if node.fixity[2] else "Free"),
                    ("RX", "Fixed" if node.fixity[3] else "Free"),
                    ("RY", "Fixed" if node.fixity[4] else "Free"),
                    ("RZ", "Fixed" if node.fixity[5] else "Free"),
                    ("Mass", ", ".join(f"{value:g}" for value in node.mass)),
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
                    (
                        "Integration",
                        (
                            f"{element.integration_type} × "
                            f"{element.integration_points}"
                            if element.element_type
                            in {"forceBeamColumn", "dispBeamColumn"}
                            else "-"
                        ),
                    ),
                    (
                        "Force iter/tol",
                        (
                            f"{element.force_max_iter} / "
                            f"{element.force_tolerance:g}"
                            if element.element_type == "forceBeamColumn"
                            else "-"
                        ),
                    ),
                    ("Mass / length", f"{element.mass_per_length:g}"),
                    (
                        "Mass matrix",
                        "Consistent"
                        if element.consistent_mass
                        else "Lumped",
                    ),
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
        support_menu = menu.addMenu("Support / Restraint")
        support_menu.setEnabled(bool(self.selection.nodes))
        apply_support = support_menu.addAction("Apply / Edit...")
        apply_support.triggered.connect(self._apply_restraint)
        clear_support = support_menu.addAction("Clear")
        clear_support.triggered.connect(self._clear_restraint)

        constraint_action = menu.addAction("Create Constraint...")
        constraint_action.setEnabled(len(self.selection.nodes) >= 2)
        constraint_action.triggered.connect(self._create_constraint)

        connection_action = menu.addAction("Create Connection / Spring...")
        connection_action.setEnabled(1 <= len(self.selection.nodes) <= 2)
        connection_action.triggered.connect(self._create_connection)

        mass_action = menu.addAction("Assign Mass...")
        mass_action.setEnabled(bool(self.selection.nodes))
        mass_action.triggered.connect(self._assign_mass)
        load_action = menu.addAction("Create Nodal Load...")
        load_action.setEnabled(bool(self.selection.nodes))
        load_action.triggered.connect(self._create_nodal_load)
        beam_load_action = menu.addAction("Create Beam Load...")
        beam_load_action.setEnabled(bool(self.selection.elements))
        beam_load_action.triggered.connect(self._create_element_load)
        formulation_action = menu.addAction(
            "Element Formulation..."
        )
        formulation_action.setEnabled(bool(self.selection.elements))
        formulation_action.triggered.connect(
            self._set_element_formulation
        )

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

    def _selected_node_tags(
        self,
        title: str,
    ) -> set[int] | None:
        tags = set(self.selection.nodes)
        if not tags:
            QMessageBox.information(
                self,
                title,
                "Select at least one node first.",
            )
            return None
        return tags

    def _apply_restraint(self) -> None:
        node_tags = self._selected_node_tags("Support / Restraint")
        if node_tags is None:
            return

        fixities = {
            tuple(self.model.nodes[tag].fixity)
            for tag in node_tags
            if tag in self.model.nodes
        }
        initial = next(iter(fixities)) if len(fixities) == 1 else None

        dialog = RestraintDialog(initial=initial, parent=self)
        if not dialog.exec():
            return

        fixity = dialog.fixity()
        before = self.project.to_dict()
        updated = self.model.set_fixity_many(node_tags, fixity)
        support_type = classify_fixity(fixity)
        self._refresh_all(
            f"Applied {support_type} restraint to {len(updated)} node(s)"
        )
        self._record_project_change(
            f"Apply {support_type} restraint",
            before,
        )

    def _clear_restraint(self) -> None:
        node_tags = self._selected_node_tags("Clear Support")
        if node_tags is None:
            return

        before = self.project.to_dict()
        updated = self.model.clear_fixity_many(node_tags)
        self._refresh_all(
            f"Cleared restraint on {len(updated)} node(s)"
        )
        self._record_project_change(
            "Clear restraint",
            before,
        )

    def _assign_mass(self) -> None:
        node_tags = self._selected_node_tags("Nodal Mass")
        if node_tags is None:
            return
        masses = {
            tuple(self.model.nodes[tag].mass)
            for tag in node_tags
            if tag in self.model.nodes
        }
        initial = next(iter(masses)) if len(masses) == 1 else None
        dialog = MassDialog(
            initial=initial,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = self.model.set_mass_many(node_tags, dialog.values())
        except ValueError as exc:
            QMessageBox.warning(self, "Nodal Mass", str(exc))
            return
        self._refresh_project_metadata(
            f"Assigned mass to {len(updated)} node(s)"
        )
        self._record_project_change("Assign nodal mass", before)

    def _clear_mass(self) -> None:
        node_tags = self._selected_node_tags("Clear Mass")
        if node_tags is None:
            return
        before = self.project.to_dict()
        updated = self.model.clear_mass_many(node_tags)
        self._refresh_project_metadata(
            f"Cleared mass on {len(updated)} node(s)"
        )
        self._record_project_change("Clear nodal mass", before)

    def _create_time_series(self) -> None:
        dialog = TimeSeriesDialog(
            next_tag=self.project.next_time_series_tag(),
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            series = dialog.data()
            self.project.add_time_series(series)
        except ValueError as exc:
            QMessageBox.warning(self, "Time Series Editor", str(exc))
            return
        self._refresh_project_metadata(f"Created time series {series.tag}")
        self._show_time_series_properties(series.tag)
        self._record_project_change(f"Create time series {series.tag}", before)

    def _edit_time_series(self, tag: int) -> None:
        series = self.project.time_series.get(tag)
        if series is None:
            return
        dialog = TimeSeriesDialog(series=series, parent=self)
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_time_series(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "Time Series Editor", str(exc))
            return
        self._refresh_project_metadata(f"Updated time series {updated.tag}")
        self._show_time_series_properties(updated.tag)
        self._record_project_change(f"Edit time series {tag}", before)

    def _delete_time_series(self, tag: int) -> None:
        if tag not in self.project.time_series:
            return
        before = self.project.to_dict()
        try:
            self.project.remove_time_series(tag)
        except ValueError as exc:
            QMessageBox.warning(self, "Delete Time Series", str(exc))
            return
        self._refresh_project_metadata(f"Deleted time series {tag}")
        self._record_project_change(f"Delete time series {tag}", before)

    def _show_time_series_properties(self, tag: int) -> None:
        series = self.project.time_series.get(tag)
        if series is None:
            return
        rows = [
            ("Tag", series.tag), ("Name", series.name),
            ("Type", series.series_type), ("Factor", f"{series.factor:g}"),
        ]
        if series.series_type == "Path":
            rows.extend([
                ("dt", f"{series.dt:g}"),
                ("Points", len(series.values)),
            ])
        self.properties_panel.set_properties("Time Series", rows)

    def _create_load_pattern(self) -> None:
        if not self.project.time_series:
            QMessageBox.information(
                self, "Load Pattern", "Create a time series first."
            )
            return
        dialog = LoadPatternDialog(
            self.project.time_series,
            next_tag=self.project.next_load_pattern_tag(),
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            pattern = dialog.data()
            self.project.add_load_pattern(pattern)
        except ValueError as exc:
            QMessageBox.warning(self, "Load Pattern Editor", str(exc))
            return
        self._refresh_project_metadata(f"Created load pattern {pattern.tag}")
        self._show_load_pattern_properties(pattern.tag)
        self._record_project_change(f"Create load pattern {pattern.tag}", before)

    def _edit_load_pattern(self, tag: int) -> None:
        pattern = self.project.load_patterns.get(tag)
        if pattern is None:
            return
        dialog = LoadPatternDialog(
            self.project.time_series, pattern=pattern, parent=self
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_load_pattern(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "Load Pattern Editor", str(exc))
            return
        self._refresh_project_metadata(f"Updated load pattern {updated.tag}")
        self._show_load_pattern_properties(updated.tag)
        self._record_project_change(f"Edit load pattern {tag}", before)

    def _delete_load_pattern(self, tag: int) -> None:
        if tag not in self.project.load_patterns:
            return
        before = self.project.to_dict()
        self.project.remove_load_pattern(tag)
        self._refresh_project_metadata(f"Deleted load pattern {tag}")
        self._record_project_change(f"Delete load pattern {tag}", before)

    def _show_load_pattern_properties(self, tag: int) -> None:
        pattern = self.project.load_patterns.get(tag)
        if pattern is None:
            return
        series = self.project.time_series.get(pattern.time_series_tag)
        rows = [
            ("Tag", pattern.tag), ("Name", pattern.name),
            ("Type", pattern.pattern_type),
            ("Time Series", f"{pattern.time_series_tag} - {series.name}" if series else pattern.time_series_tag),
        ]
        if pattern.pattern_type == "UniformExcitation":
            rows.extend([
                ("Direction", pattern.direction),
                ("Scale", f"{pattern.factor:g}"),
                ("Vel0", f"{pattern.vel0:g}"),
            ])
        else:
            rows.append((
                "Nodal Loads",
                sum(
                    load.pattern_tag == tag
                    for load in self.project.nodal_loads.values()
                ),
            ))
            rows.append((
                "Element Loads",
                sum(
                    load.pattern_tag == tag
                    for load in self.project.element_loads.values()
                ),
            ))
        self.properties_panel.set_properties("Load Pattern", rows)

    def _create_nodal_load(self) -> None:
        plain = {
            tag: pattern
            for tag, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }
        if not plain:
            QMessageBox.information(
                self, "Nodal Load", "Create a Plain load pattern first."
            )
            return
        selected = sorted(self.selection.nodes)
        node_tag = selected[0] if selected else min(self.model.nodes, default=1)
        dialog = NodalLoadDialog(
            plain,
            next_tag=self.project.next_nodal_load_tag(),
            node_tag=node_tag,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        template = dialog.data()
        targets = selected or [template.node_tag]
        before = self.project.to_dict()
        created = []
        next_tag = template.tag
        try:
            for node_tag in targets:
                while next_tag in self.project.nodal_loads:
                    next_tag += 1
                load = NodalLoadData(
                    tag=next_tag,
                    name=(
                        f"{template.name} - Node {node_tag}"
                        if len(targets) > 1 else template.name
                    ),
                    pattern_tag=template.pattern_tag,
                    node_tag=node_tag,
                    values=template.values,
                )
                self.project.add_nodal_load(load)
                created.append(load.tag)
                next_tag += 1
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Nodal Load Editor", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(
            f"Created {len(created)} nodal load(s)"
        )
        self._record_project_change("Create nodal load(s)", before)

    def _edit_nodal_load(self, tag: int) -> None:
        load = self.project.nodal_loads.get(tag)
        if load is None:
            return
        plain = {
            key: pattern
            for key, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }
        dialog = NodalLoadDialog(
            plain,
            load=load,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_nodal_load(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "Nodal Load Editor", str(exc))
            return
        self._refresh_project_metadata(f"Updated nodal load {updated.tag}")
        self._show_nodal_load_properties(updated.tag)
        self._record_project_change(f"Edit nodal load {tag}", before)

    def _delete_nodal_load(self, tag: int) -> None:
        if tag not in self.project.nodal_loads:
            return
        before = self.project.to_dict()
        self.project.remove_nodal_load(tag)
        self._refresh_project_metadata(f"Deleted nodal load {tag}")
        self._record_project_change(f"Delete nodal load {tag}", before)

    def _show_nodal_load_properties(self, tag: int) -> None:
        load = self.project.nodal_loads.get(tag)
        if load is None:
            return
        labels = ("FX", "FY", "FZ", "MX", "MY", "MZ")
        rows = [
            ("Tag", load.tag), ("Name", load.name),
            ("Pattern", load.pattern_tag), ("Node", load.node_tag),
        ]
        rows.extend((label, f"{value:g}") for label, value in zip(labels, load.values))
        self.properties_panel.set_properties("Nodal Load", rows)

    def _create_element_load(self) -> None:
        plain = {
            tag: pattern
            for tag, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }
        if not plain:
            QMessageBox.information(
                self,
                "Beam / Element Load",
                "Create a Plain load pattern first.",
            )
            return

        selected = sorted(self.selection.elements)
        if not selected:
            QMessageBox.information(
                self,
                "Beam / Element Load",
                "Select at least one beam-column element first.",
            )
            return

        dialog = ElementLoadDialog(
            plain,
            next_tag=self.project.next_element_load_tag(),
            element_tag=selected[0],
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return

        template = dialog.data()
        before = self.project.to_dict()
        created: list[int] = []
        next_tag = template.tag
        try:
            for element_tag in selected:
                while next_tag in self.project.element_loads:
                    next_tag += 1
                load = ElementLoadData(
                    tag=next_tag,
                    name=(
                        f"{template.name} - Element {element_tag}"
                        if len(selected) > 1
                        else template.name
                    ),
                    pattern_tag=template.pattern_tag,
                    element_tag=element_tag,
                    load_type=template.load_type,
                    wx=template.wx,
                    wy=template.wy,
                    wz=template.wz,
                    px=template.px,
                    py=template.py,
                    pz=template.pz,
                    x_over_l=template.x_over_l,
                    gravity=template.gravity,
                    density_override=template.density_override,
                )
                self.project.add_element_load(load)
                created.append(load.tag)
                next_tag += 1
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(
                self,
                "Beam / Element Load Editor",
                str(exc),
            )
            self._refresh_all()
            return

        self._refresh_project_metadata(
            f"Created {len(created)} element load(s)"
        )
        self._record_project_change(
            "Create element load(s)",
            before,
        )

    def _edit_element_load(self, tag: int) -> None:
        load = self.project.element_loads.get(tag)
        if load is None:
            return
        plain = {
            key: pattern
            for key, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }
        dialog = ElementLoadDialog(
            plain,
            load=load,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_element_load(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Beam / Element Load Editor",
                str(exc),
            )
            return
        self._refresh_project_metadata(
            f"Updated element load {updated.tag}"
        )
        self._show_element_load_properties(updated.tag)
        self._record_project_change(
            f"Edit element load {tag}",
            before,
        )

    def _delete_element_load(self, tag: int) -> None:
        if tag not in self.project.element_loads:
            return
        before = self.project.to_dict()
        self.project.remove_element_load(tag)
        self._refresh_project_metadata(
            f"Deleted element load {tag}"
        )
        self._record_project_change(
            f"Delete element load {tag}",
            before,
        )

    def _show_element_load_properties(self, tag: int) -> None:
        load = self.project.element_loads.get(tag)
        if load is None:
            return
        rows: list[tuple[str, object]] = [
            ("Tag", load.tag),
            ("Name", load.name),
            ("Pattern", load.pattern_tag),
            ("Element", load.element_tag),
            ("Type", load.load_type),
        ]
        if load.load_type == "Uniform":
            rows.extend([
                ("Wx", f"{load.wx:g}"),
                ("Wy", f"{load.wy:g}"),
                ("Wz", f"{load.wz:g}"),
            ])
        elif load.load_type == "Point":
            rows.extend([
                ("Px", f"{load.px:g}"),
                ("Py", f"{load.py:g}"),
                ("Pz", f"{load.pz:g}"),
                ("x/L", f"{load.x_over_l:g}"),
            ])
        else:
            rows.extend([
                ("Gravity", ", ".join(
                    f"{value:g}" for value in load.gravity
                )),
                (
                    "Density override",
                    (
                        f"{load.density_override:g}"
                        if load.density_override > 0.0
                        else "Linked material"
                    ),
                ),
            ])
        self.properties_panel.set_properties(
            "Beam / Element Load",
            rows,
        )

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

    def _set_element_formulation(self) -> None:
        element_tags = self._selected_element_tags(
            "Element Formulation"
        )
        if element_tags is None:
            return

        selected = [
            self.model.elements[tag]
            for tag in sorted(element_tags)
            if tag in self.model.elements
        ]
        first = selected[0]
        same_type = all(
            element.element_type == first.element_type
            for element in selected
        )
        same_integration = all(
            (
                element.integration_type,
                element.integration_points,
                element.force_max_iter,
                element.force_tolerance,
                element.mass_per_length,
                element.consistent_mass,
            )
            == (
                first.integration_type,
                first.integration_points,
                first.force_max_iter,
                first.force_tolerance,
                first.mass_per_length,
                first.consistent_mass,
            )
            for element in selected
        )

        dialog = ElementFormulationDialog(
            element_type=(
                first.element_type
                if same_type and first.element_type
                in {
                    "elasticBeamColumn",
                    "forceBeamColumn",
                    "dispBeamColumn",
                }
                else "elasticBeamColumn"
            ),
            integration_type=(
                first.integration_type
                if same_integration
                else "Lobatto"
            ),
            integration_points=(
                first.integration_points
                if same_integration
                else 5
            ),
            force_max_iter=(
                first.force_max_iter
                if same_integration
                else 10
            ),
            force_tolerance=(
                first.force_tolerance
                if same_integration
                else 1.0e-12
            ),
            mass_per_length=(
                first.mass_per_length
                if same_integration
                else 0.0
            ),
            consistent_mass=(
                first.consistent_mass
                if same_integration
                else False
            ),
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            updated = self.model.assign_element_formulation(
                element_tags,
                **dialog.values(),
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Element Formulation",
                str(exc),
            )
            return

        self._refresh_project_metadata(
            f"Updated formulation for {len(updated)} element(s)"
        )
        self._record_project_change(
            "Set element formulation",
            before,
        )

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
        (
            tag,
            i,
            j,
            element_type,
            group,
            integration_type,
            integration_points,
        ) = dialog.values()
        before = self.project.to_dict()
        try:
            if tag in self.project.connections:
                raise ValueError(
                    f"Element tag {tag} is already used by a connection."
                )
            self.model.add_element(
                tag,
                i,
                j,
                element_type=element_type,
                group=group,
                integration_type=integration_type,
                integration_points=integration_points,
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
        self.project.prune_constraints()
        self.project.prune_connections()
        self.project.prune_nodal_loads()
        self.project.prune_element_loads()
        self.project.prune_recorders()
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
        self._reset_runtime_results()
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
                    for component in section.fiber_components:
                        if component.material_tag == tag:
                            component.material_tag = updated.tag
                for connection in self.project.connections.values():
                    connection.materials_by_dof = {
                        dof: (
                            updated.tag
                            if material_tag == tag
                            else material_tag
                        )
                        for dof, material_tag
                        in connection.materials_by_dof.items()
                    }
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
        connection_uses = self.project.connections_using_material(tag)
        if used_by or connection_uses:
            details = []
            if used_by:
                details.append(
                    "section(s): " + ", ".join(map(str, used_by))
                )
            if connection_uses:
                details.append(
                    "connection(s): "
                    + ", ".join(map(str, connection_uses))
                )
            QMessageBox.warning(
                self,
                "Delete Material",
                "Material is still referenced by "
                + "; ".join(details)
                + ". Reassign those references first.",
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
            units=self.project.units,
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
            units=self.project.units,
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
            compiled = section.compiled_fibers()
            total_area, (cy, cz) = section.fiber_area_and_centroid()
            rows.append(("Builder Components", len(section.fiber_components)))
            rows.append(("Manual Fibers", len(section.fibers)))
            rows.append(("Compiled Fibers", len(compiled)))
            rows.append(("Fiber Area", f"{total_area:g}"))
            rows.append(("Centroid y", f"{cy:g}"))
            rows.append(("Centroid z", f"{cz:g}"))
            material_tags = sorted(section.fiber_material_tags())
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

    def _connection_dialog_defaults(self) -> tuple[int, int, bool]:
        selected = sorted(self.selection.nodes)
        if len(selected) >= 2:
            return selected[0], selected[1], False
        if len(selected) == 1:
            return selected[0], selected[0], True

        tags = sorted(self.model.nodes)
        if len(tags) >= 2:
            return tags[0], tags[1], False
        if len(tags) == 1:
            return tags[0], tags[0], True
        return 1, 2, False

    def _create_connection(self) -> None:
        if not self.model.nodes:
            QMessageBox.information(
                self,
                "Connection Editor",
                "Create at least one node first.",
            )
            return
        if not self.project.materials:
            QMessageBox.information(
                self,
                "Connection Editor",
                "Create at least one uniaxial material first.",
            )
            return

        node_i, node_j, to_ground = self._connection_dialog_defaults()
        dialog = ConnectionDialog(
            self.project.materials,
            next_tag=self.project.next_connection_tag(),
            initial_node_i=node_i,
            initial_node_j=node_j,
            default_to_ground=to_ground,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        created_ground = None
        try:
            spec = dialog.spec()
            node_j = int(spec["node_j"])
            if spec["to_ground"]:
                created_ground = self.project.create_ground_node(
                    int(spec["node_i"])
                )
                node_j = created_ground

            connection = ConnectionData(
                tag=int(spec["tag"]),
                name=str(spec["name"]),
                connection_type=str(spec["connection_type"]),
                node_i=int(spec["node_i"]),
                node_j=node_j,
                materials_by_dof=dict(spec["materials_by_dof"]),
                orient_x=tuple(spec["orient_x"]),
                orient_y=tuple(spec["orient_y"]),
                do_rayleigh=bool(spec["do_rayleigh"]),
                generated_ground_node=created_ground,
            )
            self.project.add_connection(connection)
        except ValueError as exc:
            if created_ground is not None:
                self.model.remove_node(created_ground, cascade=True)
            QMessageBox.warning(self, "Connection Editor", str(exc))
            return

        self._refresh_all(
            f"Created {connection.connection_type} connection "
            f"{connection.tag}"
        )
        self._show_connection_properties(connection.tag)
        self._record_project_change(
            f"Create connection {connection.tag}",
            before,
        )

    def _edit_connection(self, tag: int) -> None:
        connection = self.project.connections.get(tag)
        if connection is None:
            return

        dialog = ConnectionDialog(
            self.project.materials,
            connection=connection,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        old_ground = connection.generated_ground_node
        created_ground = None
        try:
            spec = dialog.spec()
            requested_ground = bool(spec["to_ground"])
            node_j = int(spec["node_j"])

            if requested_ground:
                if (
                    old_ground is not None
                    and old_ground in self.model.nodes
                    and int(spec["node_i"]) == connection.node_i
                ):
                    node_j = old_ground
                    created_ground = old_ground
                else:
                    created_ground = self.project.create_ground_node(
                        int(spec["node_i"])
                    )
                    node_j = created_ground

            updated = ConnectionData(
                tag=int(spec["tag"]),
                name=str(spec["name"]),
                connection_type=str(spec["connection_type"]),
                node_i=int(spec["node_i"]),
                node_j=node_j,
                materials_by_dof=dict(spec["materials_by_dof"]),
                orient_x=tuple(spec["orient_x"]),
                orient_y=tuple(spec["orient_y"]),
                do_rayleigh=bool(spec["do_rayleigh"]),
                generated_ground_node=(
                    created_ground if requested_ground else None
                ),
            )
            self.project.update_connection(tag, updated)

            if (
                old_ground is not None
                and old_ground != updated.generated_ground_node
                and old_ground in self.model.nodes
                and old_ground not in {updated.node_i, updated.node_j}
                and not self.project._ground_node_in_use_elsewhere(
                    old_ground,
                    excluding_connection=updated.tag,
                )
            ):
                self.model.remove_node(old_ground, cascade=True)
        except ValueError as exc:
            if (
                created_ground is not None
                and created_ground != old_ground
                and created_ground in self.model.nodes
            ):
                self.model.remove_node(created_ground, cascade=True)
            QMessageBox.warning(self, "Connection Editor", str(exc))
            return

        self._refresh_all(
            f"Updated connection {updated.tag}"
        )
        self._show_connection_properties(updated.tag)
        self._record_project_change(
            f"Edit connection {tag}",
            before,
        )

    def _delete_connection(self, tag: int) -> None:
        connection = self.project.connections.get(tag)
        if connection is None:
            return

        answer = QMessageBox.question(
            self,
            "Delete Connection",
            f"Delete connection {tag} ({connection.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.project.remove_connection(tag, cleanup_ground=True)
        self._refresh_all(f"Deleted connection {tag}")
        self._record_project_change(
            f"Delete connection {tag}",
            before,
        )

    def _show_connection_properties(self, tag: int) -> None:
        connection = self.project.connections.get(tag)
        if connection is None:
            return

        dof_labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        material_text = []
        for dof in sorted(connection.materials_by_dof):
            material_tag = connection.materials_by_dof[dof]
            material = self.project.materials.get(material_tag)
            name = material.name if material is not None else "missing"
            material_text.append(
                f"{dof_labels[dof - 1]} → {material_tag} - {name}"
            )

        rows: list[tuple[str, object]] = [
            ("Tag", connection.tag),
            ("Name", connection.name),
            ("Type", connection.connection_type),
            ("Node I", connection.node_i),
            ("Node J", connection.node_j),
            (
                "To ground",
                "Yes" if connection.generated_ground_node else "No",
            ),
            ("DOF materials", "; ".join(material_text)),
            ("Rayleigh", "Yes" if connection.do_rayleigh else "No"),
            ("Local X", connection.orient_x),
            ("Local Y", connection.orient_y),
        ]
        self.properties_panel.set_properties("Connection", rows)

    def _create_constraint(self) -> None:
        selected_nodes = sorted(self.selection.nodes)
        if len(selected_nodes) >= 2:
            retained = selected_nodes[0]
            constrained = selected_nodes[1:]
        else:
            retained = selected_nodes[0] if selected_nodes else min(
                self.model.nodes,
                default=1,
            )
            constrained = []

        dialog = ConstraintDialog(
            next_tag=self.project.next_constraint_tag(),
            initial_retained=retained,
            initial_constrained=constrained,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            constraint = dialog.constraint_data()
            self.project.add_constraint(constraint)
        except ValueError as exc:
            QMessageBox.warning(self, "Constraint Editor", str(exc))
            return

        self._refresh_project_metadata(
            f"Created {constraint.constraint_type} constraint "
            f"{constraint.tag}"
        )
        self._show_constraint_properties(constraint.tag)
        self._record_project_change(
            f"Create constraint {constraint.tag}",
            before,
        )

    def _edit_constraint(self, tag: int) -> None:
        constraint = self.project.constraints.get(tag)
        if constraint is None:
            return

        dialog = ConstraintDialog(
            constraint=constraint,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            updated = dialog.constraint_data()
            self.project.update_constraint(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "Constraint Editor", str(exc))
            return

        self._refresh_project_metadata(
            f"Updated constraint {updated.tag}"
        )
        self._show_constraint_properties(updated.tag)
        self._record_project_change(
            f"Edit constraint {tag}",
            before,
        )

    def _delete_constraint(self, tag: int) -> None:
        constraint = self.project.constraints.get(tag)
        if constraint is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Constraint",
            f"Delete constraint {tag} ({constraint.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.project.remove_constraint(tag)
        self._refresh_project_metadata(
            f"Deleted constraint {tag}"
        )
        self._record_project_change(
            f"Delete constraint {tag}",
            before,
        )

    def _show_constraint_properties(self, tag: int) -> None:
        constraint = self.project.constraints.get(tag)
        if constraint is None:
            return

        rows: list[tuple[str, object]] = [
            ("Tag", constraint.tag),
            ("Name", constraint.name),
            ("Type", constraint.constraint_type),
            ("Retained", constraint.retained_node),
            (
                "Constrained",
                ", ".join(map(str, constraint.constrained_nodes)),
            ),
        ]
        if constraint.constraint_type == "equalDOF":
            labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")
            rows.append((
                "DOFs",
                ", ".join(labels[dof - 1] for dof in constraint.dofs),
            ))
        elif constraint.constraint_type == "rigidLink":
            rows.append(("Link type", constraint.link_type))
        elif constraint.constraint_type == "rigidDiaphragm":
            axis = {1: "X", 2: "Y", 3: "Z"}[constraint.perp_dirn]
            rows.append(("Normal axis", axis))

        self.properties_panel.set_properties("Constraint", rows)

    def _create_analysis(self) -> None:
        self._create_analysis_of_type(None)

    def _create_analysis_of_type(
        self,
        analysis_type: str | None,
    ) -> None:
        default_node = min(self.model.nodes, default=1)
        dialog = AnalysisDialog(
            next_tag=self.project.next_analysis_tag(),
            default_node=default_node,
            analysis_type=analysis_type,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            settings = dialog.data()
            self.project.add_analysis(settings)
        except ValueError as exc:
            QMessageBox.warning(self, "Analysis Settings", str(exc))
            return
        self._refresh_project_metadata(f"Created analysis {settings.tag}")
        self._show_analysis_properties(settings.tag)
        self._record_project_change(f"Create analysis {settings.tag}", before)

    def _edit_analysis(self, tag: int) -> None:
        settings = self.project.analyses.get(tag)
        if settings is None:
            return
        dialog = AnalysisDialog(analysis=settings, parent=self)
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_analysis(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "Analysis Settings", str(exc))
            return
        self._refresh_project_metadata(f"Updated analysis {updated.tag}")
        self._show_analysis_properties(updated.tag)
        self._record_project_change(f"Edit analysis {tag}", before)

    def _latest_job_for_analysis(
        self,
        analysis_tag: int,
    ) -> JobRecord | None:
        target = int(analysis_tag)
        for job_id in sorted(self._jobs, reverse=True):
            job = self._jobs[job_id]
            if job.analysis_tag == target and job.results:
                return job
        return None

    def _insert_solution_result(
        self,
        analysis_tag: int,
        result_type: str,
        name: str,
        settings: dict[str, object] | None = None,
    ) -> None:
        before = self.project.to_dict()
        result = SolutionResultData(
            tag=self.project.next_solution_result_tag(),
            analysis_tag=int(analysis_tag),
            name=str(name),
            result_type=str(result_type),
            node_scope=sorted(self.selection.nodes),
            element_scope=sorted(self.selection.elements),
            settings=dict(settings or {}),
        )
        try:
            self.project.add_solution_result(result)
        except ValueError as exc:
            QMessageBox.warning(self, "Solution Result", str(exc))
            return
        self._record_project_change(
            f"Insert solution result {result.name}",
            before,
        )
        self._refresh_tree()
        self._show_solution_result_properties(result.tag)
        self._evaluate_solution_result(result.tag)
        self.status_message.setText(
            f"Inserted result: {result.name}"
        )

    def _delete_solution_result(self, tag: int) -> None:
        result = self.project.solution_results.get(int(tag))
        if result is None:
            return
        before = self.project.to_dict()
        self.project.remove_solution_result(tag)
        self._record_project_change(
            f"Delete solution result {result.name}",
            before,
        )
        self.viewport.clear_result_overlay()
        self._refresh_tree()
        self.status_message.setText(
            f"Deleted result: {result.name}"
        )

    def _rename_solution_result(self, tag: int) -> None:
        result = self.project.solution_results.get(int(tag))
        if result is None:
            return
        name, ok = QInputDialog.getText(
            self,
            "Rename Result",
            "Name:",
            text=result.name,
        )
        name = str(name).strip()
        if not ok or not name or name == result.name:
            return
        before = self.project.to_dict()
        result.name = name
        self._record_project_change(
            f"Rename solution result {tag}",
            before,
        )
        self._refresh_tree()
        self._show_solution_result_properties(tag)

    def _duplicate_solution_result(self, tag: int) -> None:
        source = self.project.solution_results.get(int(tag))
        if source is None:
            return
        before = self.project.to_dict()
        duplicate = SolutionResultData(
            tag=self.project.next_solution_result_tag(),
            analysis_tag=source.analysis_tag,
            name=f"{source.name} Copy",
            result_type=source.result_type,
            node_scope=list(source.node_scope),
            element_scope=list(source.element_scope),
            settings=dict(source.settings),
        )
        self.project.add_solution_result(duplicate)
        self._record_project_change(
            f"Duplicate solution result {source.name}",
            before,
        )
        self._refresh_tree()

    def _show_solution_information(
        self,
        analysis_tag: int,
        title: str,
    ) -> None:
        settings = self.project.analyses.get(int(analysis_tag))
        job = self._latest_job_for_analysis(analysis_tag)
        rows: list[tuple[str, object]] = [
            ("Analysis", settings.name if settings else analysis_tag),
            (
                "Type",
                settings.analysis_type if settings else "-",
            ),
        ]
        if job is None:
            rows.extend([
                ("Result", "Not evaluated"),
                ("Job", "-"),
                ("Status", "-"),
            ])
        else:
            rows.extend([
                ("Result", "Latest job"),
                ("Job", job.job_id),
                ("Status", job.status),
                ("Progress", f"{job.progress_percent:.1f}%"),
                ("Message", job.message or "-"),
            ])
        self.properties_panel.set_properties(title, rows)

    def _show_solution_result_properties(self, tag: int) -> None:
        result = self.project.solution_results.get(int(tag))
        if result is None:
            return
        self._active_solution_result_tag = int(tag)
        analysis = self.project.analyses.get(result.analysis_tag)
        self.properties_panel.set_solution_result(
            result,
            analysis_name=(
                analysis.name
                if analysis is not None
                else f"Analysis {result.analysis_tag}"
            ),
        )

    def _solution_result_from_payload(
        self,
        tag: int,
        payload: object,
    ) -> SolutionResultData:
        current = self.project.solution_results.get(int(tag))
        if current is None:
            raise ValueError(
                f"Solution result tag {tag} does not exist."
            )
        data = dict(payload) if isinstance(payload, dict) else {}
        name = str(data.get("name", "")).strip() or current.name

        raw_nodes = str(data.get("node_scope", "") or "").strip()
        raw_elements = str(
            data.get("element_scope", "") or ""
        ).strip()
        node_scope = sorted(
            parse_tag_expression(raw_nodes)
            if raw_nodes
            else set()
        )
        element_scope = sorted(
            parse_tag_expression(raw_elements)
            if raw_elements
            else set()
        )
        settings = (
            dict(data.get("settings", {}))
            if isinstance(data.get("settings", {}), dict)
            else {}
        )
        return SolutionResultData(
            tag=current.tag,
            analysis_tag=current.analysis_tag,
            name=name,
            result_type=current.result_type,
            node_scope=node_scope,
            element_scope=element_scope,
            settings=settings,
        )

    def _apply_solution_result_details(
        self,
        tag: int,
        payload: object,
    ) -> None:
        before = self.project.to_dict()
        try:
            updated = self._solution_result_from_payload(tag, payload)
            self.project.update_solution_result(tag, updated)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Solution Result",
                str(exc),
            )
            return
        self._record_project_change(
            f"Edit solution result {updated.name}",
            before,
        )
        self._refresh_tree()
        self._show_solution_result_properties(updated.tag)
        self.status_message.setText(
            f"Updated result: {updated.name}"
        )

    def _evaluate_solution_result_details(
        self,
        tag: int,
        payload: object,
    ) -> None:
        before = self.project.to_dict()
        try:
            updated = self._solution_result_from_payload(tag, payload)
            self.project.update_solution_result(tag, updated)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Solution Result",
                str(exc),
            )
            return
        self._record_project_change(
            f"Edit and evaluate solution result {updated.name}",
            before,
        )
        self._refresh_tree()
        self._evaluate_solution_result(updated.tag)
        self._show_solution_result_properties(updated.tag)

    def _use_current_selection_for_solution_result(
        self,
        tag: int,
    ) -> None:
        if int(tag) not in self.project.solution_results:
            return
        self.properties_panel.set_solution_scope(
            set(self.selection.nodes),
            set(self.selection.elements),
        )
        self.status_message.setText(
            "Result scope updated from current selection; "
            "click Apply or Evaluate to save."
        )

    def _load_analysis_result(
        self,
        analysis_tag: int,
    ) -> dict[str, object] | None:
        job = self._latest_job_for_analysis(analysis_tag)
        if job is None:
            self.status_message.setText(
                "Result object is not evaluated yet — run its analysis first."
            )
            return None
        result = dict(job.results)
        self._last_result = result
        self.results_panel.set_result(result)
        return result

    def _show_solution_convergence(self, analysis_tag: int) -> None:
        result = self._load_analysis_result(analysis_tag)
        if result is None:
            return
        self.results_panel.show_solution_result("Convergence", {})
        self.results_dock.show()
        self.results_dock.raise_()

    def _evaluate_solution_result(self, tag: int) -> None:
        result_object = self.project.solution_results.get(int(tag))
        if result_object is None:
            return
        result = self._load_analysis_result(result_object.analysis_tag)
        if result is None:
            return

        self._render_result_data(
            result,
            result_object.result_type,
            dict(result_object.settings),
            node_scope=set(result_object.node_scope),
            element_scope=set(result_object.element_scope),
            restore_scope_selection=True,
        )
        self.status_message.setText(
            f"Evaluated result: {result_object.name}"
        )
        self._show_solution_result_properties(result_object.tag)

    def _evaluate_all_solution_results(self, analysis_tag: int) -> None:
        objects = self.project.solution_results_for_analysis(analysis_tag)
        if not objects:
            self.status_message.setText(
                "Solution contains no inserted result objects."
            )
            return
        for result in objects:
            self._evaluate_solution_result(result.tag)
        self.status_message.setText(
            f"Evaluated {len(objects)} solution result object(s)"
        )

    def _delete_analysis(self, tag: int) -> None:
        if tag not in self.project.analyses:
            return
        before = self.project.to_dict()
        self.project.remove_analysis(tag)
        self._refresh_project_metadata(f"Deleted analysis {tag}")
        self._record_project_change(f"Delete analysis {tag}", before)

    def _set_active_analysis(self, tag: int) -> None:
        before = self.project.to_dict()
        try:
            self.project.set_active_analysis(tag)
        except ValueError as exc:
            QMessageBox.warning(self, "Analysis Settings", str(exc))
            return
        self._refresh_project_metadata(f"Active analysis: {tag}")
        self._record_project_change(f"Set active analysis {tag}", before)

    def _show_analysis_properties(self, tag: int) -> None:
        settings = self.project.analyses.get(tag)
        if settings is None:
            return
        rows = [
            ("Tag", settings.tag), ("Name", settings.name),
            ("Type", settings.analysis_type),
            ("Active", "Yes" if tag == self.project.active_analysis_tag else "No"),
            ("Constraints", settings.constraints_handler),
            ("Numberer", settings.numberer), ("System", settings.system),
        ]
        if settings.analysis_type == "Modal":
            rows.append(("Modes", settings.num_modes))
        else:
            rows.extend([
                ("Test", settings.test), ("Tolerance", f"{settings.tolerance:g}"),
                ("Max iterations", settings.max_iterations),
                ("Algorithm", settings.algorithm), ("Steps", settings.steps),
                ("Recovery", "On" if settings.recovery else "Off"),
                ("Adaptive step", "On" if settings.adaptive_step else "Off"),
                (
                    "Cutback / min / grow",
                    (
                        f"{settings.adaptive_cutback_factor:g} / "
                        f"{settings.adaptive_min_factor:g} / "
                        f"{settings.adaptive_growth_factor:g}"
                    ),
                ),
                (
                    "Easy / grow-after",
                    (
                        f"≤ {settings.adaptive_easy_iterations} iter / "
                        f"{settings.adaptive_growth_after} easy step(s)"
                    ),
                ),
                (
                    "Live convergence",
                    "On" if settings.live_convergence else "Off",
                ),
                (
                    "External terminal",
                    "On" if settings.show_external_console else "Off",
                ),
            ])
            if settings.analysis_type == "Static":
                rows.append(("Load increment", f"{settings.load_increment:g}"))
            elif settings.analysis_type == "Pushover":
                rows.extend([
                    ("Control node", settings.control_node),
                    ("Control DOF", settings.control_dof),
                    ("Disp. increment", f"{settings.displacement_increment:g}"),
                ])
            elif settings.analysis_type == "Cyclic":
                expanded = cyclic_displacement_steps(
                    settings.cyclic_targets,
                    settings.cyclic_increment,
                )
                rows.extend([
                    ("Control node", settings.control_node),
                    ("Control DOF", settings.control_dof),
                    (
                        "Targets",
                        ", ".join(f"{value:g}" for value in settings.cyclic_targets),
                    ),
                    ("Max increment", f"{settings.cyclic_increment:g}"),
                    ("Expanded steps", len(expanded)),
                ])
            elif settings.analysis_type == "Transient":
                rows.extend([
                    ("dt", f"{settings.dt:g}"), ("gamma", f"{settings.gamma:g}"),
                    ("beta", f"{settings.beta:g}"),
                ])
        self.properties_panel.set_properties("Analysis Settings", rows)

    def _create_recorder(self) -> None:
        initial_nodes = set(self.selection.nodes)
        initial_elements = set(self.selection.elements)
        dialog = RecorderDialog(
            next_tag=self.project.next_recorder_tag(),
            initial_node_tags=initial_nodes,
            initial_element_tags=initial_elements,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            recorder = dialog.data()
            self.project.add_recorder(recorder)
        except ValueError as exc:
            QMessageBox.warning(self, "Recorder", str(exc))
            return
        self._refresh_project_metadata(
            f"Created {recorder.recorder_type} recorder {recorder.tag}"
        )
        self._show_recorder_properties(recorder.tag)
        self._record_project_change(
            f"Create recorder {recorder.tag}",
            before,
        )

    def _edit_recorder(self, tag: int) -> None:
        recorder = self.project.recorders.get(tag)
        if recorder is None:
            return
        dialog = RecorderDialog(
            recorder=recorder,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_recorder(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "Recorder", str(exc))
            return
        self._refresh_project_metadata(
            f"Updated recorder {updated.tag}"
        )
        self._show_recorder_properties(updated.tag)
        self._record_project_change(
            f"Edit recorder {tag}",
            before,
        )

    def _delete_recorder(self, tag: int) -> None:
        recorder = self.project.recorders.get(tag)
        if recorder is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Recorder",
            f"Delete recorder {tag} ({recorder.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        before = self.project.to_dict()
        self.project.remove_recorder(tag)
        self._refresh_project_metadata(f"Deleted recorder {tag}")
        self._record_project_change(
            f"Delete recorder {tag}",
            before,
        )

    def _show_recorder_properties(self, tag: int) -> None:
        recorder = self.project.recorders.get(tag)
        if recorder is None:
            return
        rows: list[tuple[str, object]] = [
            ("Tag", recorder.tag),
            ("Name", recorder.name),
            ("Type", recorder.recorder_type),
            (
                "Targets",
                ", ".join(map(str, recorder.target_tags)),
            ),
            ("Response", recorder.response),
            ("File", recorder.file_name),
            ("Include time", "Yes" if recorder.include_time else "No"),
        ]
        if recorder.recorder_type == "Node":
            rows.append(
                ("DOFs", ", ".join(map(str, recorder.dofs)))
            )
        if recorder.recorder_type in {"Section", "Fiber"}:
            rows.append(("Section/IP", recorder.section_number))
        if recorder.recorder_type == "Fiber":
            rows.extend([
                ("Fiber y", f"{recorder.fiber_y:g}"),
                ("Fiber z", f"{recorder.fiber_z:g}"),
                (
                    "Material",
                    recorder.material_tag
                    if recorder.material_tag is not None
                    else "Nearest fiber",
                ),
            ])
        self.properties_panel.set_properties("Recorder", rows)

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

    def _populate_result_choice_menu(
        self,
        parent_menu: QMenu,
        analysis_type: str,
        callback,
        *,
        convergence_test: str | None = None,
    ) -> None:
        categories: dict[str, QMenu] = {}
        for choice in result_choices_for_analysis(
            analysis_type,
            convergence_test,
        ):
            submenu = categories.get(choice.category)
            if submenu is None:
                submenu = parent_menu.addMenu(choice.category)
                categories[choice.category] = submenu
            action = submenu.addAction(choice.label)
            action.triggered.connect(
                lambda checked=False, ch=choice: callback(
                    ch.result_type,
                    ch.name,
                    dict(ch.settings),
                )
            )

    def _render_result_data(
        self,
        result: dict[str, object],
        result_type: str,
        settings: dict[str, object] | None = None,
        *,
        node_scope: set[int] | None = None,
        element_scope: set[int] | None = None,
        restore_scope_selection: bool = False,
    ) -> None:
        payload = dict(result or {})
        if not payload:
            self.status_message.setText("No result data available")
            return

        options = dict(settings or {})
        nodes = set(node_scope or ())
        elements = set(element_scope or ())
        options["_node_scope"] = sorted(nodes)
        options["_element_scope"] = sorted(elements)

        self._last_result = payload
        self.results_panel.set_result(payload)
        self.results_panel.show_solution_result(result_type, options)
        self.results_dock.show()
        self.results_dock.raise_()

        if restore_scope_selection and (nodes or elements):
            self.selection.set_selection(
                nodes=nodes,
                elements=elements,
            )

        if result_type == "DeformedShape":
            self.viewport.show_deformed_shape(
                payload,
                scale=float(options.get("scale", 10.0)),
                node_tags=nodes or None,
                element_tags=elements or None,
            )
        elif result_type in {"NodalDisplacement", "NodalReaction"}:
            quantity = (
                "Reaction"
                if result_type == "NodalReaction"
                else "Displacement"
            )
            component = str(
                options.get(
                    "component",
                    "FX" if quantity == "Reaction" else "|U|",
                )
            )
            self.viewport.show_node_contour(
                payload,
                quantity,
                component,
                node_tags=nodes or None,
                element_tags=elements or None,
            )
        elif result_type == "MemberForce":
            self.viewport.show_member_force_diagram(
                payload,
                self.project.transformations,
                str(options.get("component", "Mz")),
                scale=float(options.get("scale", 1.0)),
                element_tags=elements or None,
            )
        elif result_type == "HingeState":
            self.viewport.show_hinge_states(
                payload,
                element_tags=elements or None,
            )
        elif result_type == "ModeShape":
            modes = payload.get("modes", {})
            mode = int(options.get("mode", 1))
            if isinstance(modes, dict) and str(mode) not in modes and modes:
                mode = min(int(key) for key in modes)
            self.viewport.show_mode_shape(
                payload,
                mode,
                scale=float(options.get("scale", 1.0)),
                node_tags=nodes or None,
                element_tags=elements or None,
            )

    def _show_jobs_summary(self) -> None:
        completed = sum(
            1 for job in self._jobs.values()
            if job.status == "Completed"
        )
        running = sum(
            1 for job in self._jobs.values()
            if job.status == "Running"
        )
        failed = sum(
            1 for job in self._jobs.values()
            if job.status in {"Failed", "Crashed"}
        )
        self.properties_panel.set_properties(
            "Results / Jobs",
            [
                ("Jobs", len(self._jobs)),
                ("Running", running),
                ("Completed", completed),
                ("Failed / Crashed", failed),
                (
                    "Quick plot",
                    "Right-click a Job → Plot",
                ),
                (
                    "Job manager",
                    "Right-click Results / Jobs → Show Job Manager",
                ),
            ],
        )

    def _job_convergence_test(self, job: JobRecord | None) -> str | None:
        if job is None:
            return None
        convergence = (
            job.results.get("convergence", {})
            if isinstance(job.results, dict)
            else {}
        )
        if isinstance(convergence, dict):
            test = str(convergence.get("test", "") or "").strip()
            if test:
                return test
        if job.analysis_tag is not None:
            analysis = self.project.analyses.get(int(job.analysis_tag))
            if analysis is not None:
                return analysis.test
        return None

    def _unique_solution_result_name(
        self,
        analysis_tag: int,
        base_name: str,
    ) -> str:
        existing = {
            result.name
            for result in self.project.solution_results_for_analysis(
                analysis_tag
            )
        }
        name = str(base_name)
        if name not in existing:
            return name
        suffix = 2
        while f"{name} {suffix}" in existing:
            suffix += 1
        return f"{name} {suffix}"

    def _select_tree_payload(self, kind: str, value: object) -> None:
        root = self.tree.invisibleRootItem()

        def visit(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            payload = item.data(0, Qt.UserRole)
            if (
                isinstance(payload, tuple)
                and len(payload) == 2
                and payload[0] == kind
                and payload[1] == value
            ):
                return item
            for index in range(item.childCount()):
                found = visit(item.child(index))
                if found is not None:
                    return found
            return None

        for index in range(root.childCount()):
            found = visit(root.child(index))
            if found is not None:
                self.tree.setCurrentItem(found)
                found.setSelected(True)
                parent = found.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.tree.scrollToItem(found)
                return

    def _show_job_properties(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        self.properties_panel.set_properties(
            f"Job {job.job_id}",
            [
                ("Analysis", job.analysis_name),
                ("Type", job.analysis_type),
                ("Status", job.status),
                ("Progress", f"{job.progress_percent:.1f}%"),
                ("Algorithm", job.current_algorithm or "-"),
                ("Iterations", job.iterations),
                ("Result data", "Available" if job.results else "Not available"),
                ("Message", job.message or "-"),
            ],
        )

    def _activate_job_result(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None or not job.results:
            self.status_message.setText(
                f"Job {job_id} has no captured result data."
            )
            return
        self._last_result = dict(job.results)
        self.results_panel.set_result(self._last_result)
        self._show_job_properties(job.job_id)
        self.status_message.setText(
            f"Job {job.job_id} is the active quick-plot result source. "
            "Right-click the Job → Plot to open a result view."
        )

    def _show_job_plot(
        self,
        job_id: int,
        plot_id: int,
    ) -> None:
        job = self._jobs.get(int(job_id))
        if job is None or not job.results:
            self.status_message.setText(
                f"Job {job_id} has no captured result data."
            )
            return
        plot = job.plot(plot_id)
        if plot is None:
            return

        settings = dict(plot.get("settings", {}))
        node_scope = {
            int(tag)
            for tag in plot.get("node_scope", [])
        }
        element_scope = {
            int(tag)
            for tag in plot.get("element_scope", [])
        }
        self._active_solution_result_tag = None
        self._render_result_data(
            dict(job.results),
            str(plot.get("result_type", "")),
            settings,
            node_scope=node_scope,
            element_scope=element_scope,
            restore_scope_selection=True,
        )
        self.properties_panel.set_properties(
            str(plot.get("name", f"Result {plot_id}")),
            [
                ("Job", job.job_id),
                ("Analysis", job.analysis_name),
                ("Type", job.analysis_type),
                (
                    "Result Type",
                    str(plot.get("result_type", "-")),
                ),
                (
                    "Node Scope",
                    ", ".join(map(str, sorted(node_scope))) or "All",
                ),
                (
                    "Element Scope",
                    ", ".join(map(str, sorted(element_scope))) or "All",
                ),
                (
                    "Convergence Test",
                    self._job_convergence_test(job) or "-",
                ),
            ],
        )
        self.status_message.setText(
            f"Job {job.job_id} · "
            f"{plot.get('name', f'Result {plot_id}')}"
        )

    def _delete_job_plot(
        self,
        job_id: int,
        plot_id: int,
    ) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        plot = job.plot(plot_id)
        if plot is None:
            return
        name = str(plot.get("name", f"Result {plot_id}"))
        job.remove_plot(plot_id)
        self.viewport.clear_result_overlay()
        self._refresh_tree()
        self.status_message.setText(
            f"Removed Job {job.job_id} result: {name}"
        )

    def _quick_plot_job_result(
        self,
        job_id: int,
        result_type: str,
        name: str,
        settings: dict[str, object],
    ) -> None:
        job = self._jobs.get(int(job_id))
        if job is None or not job.results:
            self.status_message.setText(
                f"Job {job_id} has no captured result data."
            )
            return

        plot = job.add_plot(
            name=str(name),
            result_type=str(result_type),
            settings=dict(settings),
            node_scope=sorted(self.selection.nodes),
            element_scope=sorted(self.selection.elements),
        )
        plot_id = int(plot["plot_id"])

        self._refresh_tree()
        self._select_tree_payload(
            "job_plot",
            (job.job_id, plot_id),
        )
        self._show_job_plot(job.job_id, plot_id)
        self.status_message.setText(
            f"Job {job.job_id} · added result: {plot['name']}"
        )

    def _export_job_result_json(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None or not job.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Job Results",
            f"job_{job.job_id}_results.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        Path(path).write_text(
            json.dumps(job.results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.status_message.setText(
            f"Exported Job {job.job_id} results to {Path(path).name}"
        )

    def _show_tree_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        payload = item.data(0, Qt.UserRole)
        if not payload:
            return

        kind, value = payload
        menu = QMenu(self)

        if kind == "node":
            tag = int(value)
            if tag not in self.selection.nodes:
                self.selection.select("node", tag, "replace")
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(
                lambda: self._show_entity_properties("node", tag)
            )
            menu.addSeparator()
            support_action = menu.addAction("Support / Restraint...")
            support_action.triggered.connect(self._apply_restraint)
            clear_action = menu.addAction("Clear Support")
            clear_action.triggered.connect(self._clear_restraint)
            menu.addSeparator()
            mass_action = menu.addAction("Assign Mass...")
            mass_action.triggered.connect(self._assign_mass)
            clear_mass = menu.addAction("Clear Mass")
            clear_mass.triggered.connect(self._clear_mass)
            nodal_load = menu.addAction("Create Nodal Load...")
            nodal_load.triggered.connect(self._create_nodal_load)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "element":
            tag = int(value)
            if tag not in self.selection.elements:
                self.selection.select("element", tag, "replace")
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(
                lambda: self._show_entity_properties("element", tag)
            )
            formulation = menu.addAction("Element Formulation...")
            formulation.triggered.connect(
                self._set_element_formulation
            )
            section_action = menu.addAction("Assign Section...")
            section_action.triggered.connect(
                self._assign_section_to_selection
            )
            transformation_action = menu.addAction(
                "Assign Transformation..."
            )
            transformation_action.triggered.connect(
                self._assign_transformation_to_selection
            )
            beam_load = menu.addAction("Create Beam Load...")
            beam_load.triggered.connect(self._create_element_load)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "constraints_root":
            create_action = menu.addAction("New Constraint...")
            create_action.triggered.connect(self._create_constraint)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "constraint":
            tag = int(value)
            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(
                lambda: self._edit_constraint(tag)
            )
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_constraint(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "connections_root":
            create_action = menu.addAction("New Connection / Spring...")
            create_action.triggered.connect(self._create_connection)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "connection":
            tag = int(value)
            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(
                lambda: self._edit_connection(tag)
            )
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_connection(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "analyses_root":
            insert_menu = menu.addMenu("Insert")
            for analysis_type in (
                "Static",
                "Pushover",
                "Cyclic",
                "Transient",
                "Modal",
            ):
                action = insert_menu.addAction(
                    f"{analysis_type} Analysis"
                )
                action.triggered.connect(
                    lambda checked=False, kind=analysis_type:
                    self._create_analysis_of_type(kind)
                )
            menu.addSeparator()
            action = menu.addAction("New Analysis...")
            action.triggered.connect(self._create_analysis)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind in {"analysis", "analysis_settings"}:
            tag = int(value)
            active = menu.addAction("Set Active")
            active.setEnabled(tag != self.project.active_analysis_tag)
            active.triggered.connect(lambda: self._set_active_analysis(tag))
            edit = menu.addAction("Edit Analysis Settings...")
            edit.triggered.connect(lambda: self._edit_analysis(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_analysis(tag))
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "solution_root":
            analysis_tag = int(value)
            analysis_settings = self.project.analyses.get(analysis_tag)
            analysis_type = (
                analysis_settings.analysis_type
                if analysis_settings is not None
                else ""
            )
            insert_menu = menu.addMenu("Insert")
            self._populate_result_choice_menu(
                insert_menu,
                analysis_type,
                lambda result_type, name, settings:
                self._insert_solution_result(
                    analysis_tag,
                    result_type,
                    name,
                    settings,
                ),
                convergence_test=(
                    analysis_settings.test
                    if analysis_settings is not None
                    else None
                ),
            )

            menu.addSeparator()
            evaluate_all = menu.addAction("Evaluate All Results")
            evaluate_all.triggered.connect(
                lambda: self._evaluate_all_solution_results(analysis_tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "solution_result":
            tag = int(value)
            evaluate = menu.addAction("Evaluate")
            evaluate.triggered.connect(
                lambda: self._evaluate_solution_result(tag)
            )
            duplicate = menu.addAction("Duplicate")
            duplicate.triggered.connect(
                lambda: self._duplicate_solution_result(tag)
            )
            rename = menu.addAction("Rename...")
            rename.triggered.connect(
                lambda: self._rename_solution_result(tag)
            )
            menu.addSeparator()
            delete = menu.addAction("Delete")
            delete.triggered.connect(
                lambda: self._delete_solution_result(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "solution_convergence":
            analysis_tag = int(value)
            analysis = self.project.analyses.get(analysis_tag)
            label = convergence_result_label(
                analysis.test if analysis is not None else None
            )
            evaluate = menu.addAction(f"Open {label}")
            evaluate.triggered.connect(
                lambda: self._show_solution_convergence(analysis_tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "solver_output":
            show = menu.addAction("Show Solver Output")
            show.triggered.connect(
                lambda: (
                    self.console_dock.show(),
                    self.console_dock.raise_(),
                )
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "jobs_root":
            show_jobs = menu.addAction("Show Job Manager")
            show_jobs.triggered.connect(
                lambda: (
                    self.results_panel.show_jobs(),
                    self.results_dock.show(),
                    self.results_dock.raise_(),
                )
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "job":
            job_id = int(value)
            job = self._jobs.get(job_id)

            activate = menu.addAction("Set as Active Result Source")
            activate.setEnabled(bool(job and job.results))
            activate.triggered.connect(
                lambda: self._activate_job_result(job_id)
            )

            plot_menu = menu.addMenu("Plot")
            plot_menu.setEnabled(
                bool(
                    job
                    and job.results
                    and job.analysis_tag is not None
                    and job.analysis_tag in self.project.analyses
                )
            )
            if job is not None:
                self._populate_result_choice_menu(
                    plot_menu,
                    job.analysis_type,
                    lambda result_type, name, settings:
                    self._quick_plot_job_result(
                        job_id,
                        result_type,
                        name,
                        settings,
                    ),
                    convergence_test=self._job_convergence_test(job),
                )

            menu.addSeparator()
            export = menu.addAction("Export Results JSON...")
            export.setEnabled(bool(job and job.results))
            export.triggered.connect(
                lambda: self._export_job_result_json(job_id)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "recorders_root":
            action = menu.addAction("New Recorder...")
            action.triggered.connect(self._create_recorder)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "recorder":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_recorder(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_recorder(tag))
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "masses_root":
            assign_action = menu.addAction("Assign to Current Node Selection...")
            assign_action.triggered.connect(self._assign_mass)
            clear_action = menu.addAction("Clear Current Node Selection")
            clear_action.triggered.connect(self._clear_mass)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "time_series_root":
            action = menu.addAction("New Time Series...")
            action.triggered.connect(self._create_time_series)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "time_series":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_time_series(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_time_series(tag))
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "load_patterns_root":
            action = menu.addAction("New Load Pattern...")
            action.triggered.connect(self._create_load_pattern)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "load_pattern":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_load_pattern(tag))
            pattern = self.project.load_patterns.get(tag)
            if pattern is not None and pattern.pattern_type == "Plain":
                add_load = menu.addAction("Add Nodal Load...")
                add_load.triggered.connect(self._create_nodal_load)
                add_element_load = menu.addAction("Add Beam Load...")
                add_element_load.triggered.connect(
                    self._create_element_load
                )
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_load_pattern(tag))
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "nodal_load":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_nodal_load(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_nodal_load(tag))
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        if kind == "element_load":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(
                lambda: self._edit_element_load(tag)
            )
            delete = menu.addAction("Delete")
            delete.triggered.connect(
                lambda: self._delete_element_load(tag)
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

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
        elif kind == "constraint":
            self._edit_constraint(int(value))
        elif kind == "connection":
            self._edit_connection(int(value))
        elif kind == "time_series":
            self._edit_time_series(int(value))
        elif kind == "load_pattern":
            self._edit_load_pattern(int(value))
        elif kind == "nodal_load":
            self._edit_nodal_load(int(value))
        elif kind == "element_load":
            self._edit_element_load(int(value))
        elif kind in {"analysis", "analysis_settings"}:
            self._edit_analysis(int(value))
        elif kind == "job":
            self._activate_job_result(int(value))
        elif kind == "recorder":
            self._edit_recorder(int(value))

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

    def _focus_validation_issue(
        self,
        issue: ValidationIssue,
    ) -> None:
        tag = issue.entity_tag
        if tag is None:
            return
        if issue.entity_kind == "element" and tag in self.model.elements:
            self.selection.set_selection(elements={tag})
            self.viewport.zoom_to_selection(set(), {tag})
            self.status_message.setText(
                f"Model Check: selected element {tag}"
            )
        elif issue.entity_kind == "node" and tag in self.model.nodes:
            self.selection.set_selection(nodes={tag})
            self.viewport.zoom_to_selection({tag}, set())
            self.status_message.setText(
                f"Model Check: selected node {tag}"
            )

    def _model_check_issues(
        self,
        settings: AnalysisSettingsData | None,
    ) -> list[ValidationIssue]:
        return validate_project(self.project, settings)

    def _show_model_check(
        self,
        issues: list[ValidationIssue],
        *,
        allow_run: bool,
    ) -> bool:
        errors = sum(issue.severity == "ERROR" for issue in issues)
        warnings = sum(issue.severity == "WARNING" for issue in issues)
        self.console.appendPlainText(
            f">> Model check: {errors} error(s), {warnings} warning(s)"
        )
        dialog = ModelCheckDialog(
            issues,
            allow_run=allow_run and errors == 0,
            select_callback=self._focus_validation_issue,
            parent=self,
        )
        return dialog.exec() == QDialog.Accepted

    def _check_model(self) -> None:
        settings = self.project.analyses.get(
            self.project.active_analysis_tag
        )
        issues = self._model_check_issues(settings)
        if not issues:
            self.console.appendPlainText(
                ">> Model check passed: no errors or warnings."
            )
            self.status_message.setText(
                "Model check passed"
            )
            QMessageBox.information(
                self,
                "Model Check",
                "Model check passed. No errors or warnings were found.",
            )
            return
        self._show_model_check(issues, allow_run=False)

    def _toggle_analysis(self) -> None:
        if self._analysis_process is not None:
            if self._analysis_process.state() != QProcess.NotRunning:
                self._stop_analysis()
                return
        self._start_analysis()

    def _start_analysis(self) -> None:
        active_tag = self.project.active_analysis_tag
        settings = self.project.analyses.get(active_tag)
        if settings is None:
            QMessageBox.information(
                self,
                "Run",
                "Create an Analysis Settings object and set it Active first.",
            )
            return

        script_text = self.script.toPlainText()
        if not script_text.strip():
            QMessageBox.information(
                self,
                "Run",
                "The generated script is empty.",
            )
            return

        issues = self._model_check_issues(settings)
        errors = [
            issue for issue in issues
            if issue.severity == "ERROR"
        ]
        warnings = [
            issue for issue in issues
            if issue.severity == "WARNING"
        ]
        if errors:
            self._show_model_check(issues, allow_run=False)
            self.status_message.setText(
                f"Run blocked: {len(errors)} model error(s)"
            )
            return
        if warnings:
            proceed = self._show_model_check(
                issues,
                allow_run=True,
            )
            if not proceed:
                self.status_message.setText(
                    "Run cancelled after model check"
                )
                return
        else:
            self.console.appendPlainText(
                ">> Model check passed — starting solver."
            )
            self.status_message.setText(
                "Model check passed — starting solver"
            )

        runtime_ok, runtime_detail = probe_opensees_runtime(
            sys.executable
        )
        if not runtime_ok:
            self.console.appendPlainText(
                ">> OpenSeesPy runtime check FAILED"
            )
            for line in runtime_detail.splitlines():
                self.console.appendPlainText(">> " + line)
            self.status_message.setText(
                "OpenSeesPy runtime unavailable"
            )
            QMessageBox.critical(
                self,
                "OpenSeesPy Runtime",
                "OpenSeesPy cannot start in the current Python environment.\n\n"
                + runtime_detail
                + "\n\nOn Windows, use the Studio Python 3.12 environment "
                  "and reinstall the project dependencies.",
            )
            return

        self.console.appendPlainText(
            ">> OpenSeesPy runtime check OK"
        )
        for line in runtime_detail.splitlines():
            self.console.appendPlainText(">> " + line)

        fd, path = tempfile.mkstemp(
            prefix="openseespy_studio_",
            suffix=".py",
            text=True,
        )
        os.close(fd)
        Path(path).write_text(script_text, encoding="utf-8")
        self._analysis_script_path = path

        result_fd, result_path = tempfile.mkstemp(
            prefix="openseespy_studio_result_",
            suffix=".json",
            text=True,
        )
        os.close(result_fd)
        self._analysis_result_path = result_path

        log_fd, log_path = tempfile.mkstemp(
            prefix="openseespy_studio_job_",
            suffix=".log",
            text=True,
        )
        os.close(log_fd)
        self._analysis_log_path = log_path
        self._analysis_stdout_buffer = ""
        self._analysis_stderr_buffer = ""
        self._analysis_external_console = bool(
            settings.show_external_console
        )

        self._job_counter += 1
        job = JobRecord(
            job_id=self._job_counter,
            analysis_tag=settings.tag,
            analysis_name=settings.name,
            analysis_type=settings.analysis_type,
        )
        job.start()
        if settings.analysis_type == "Modal":
            total = settings.num_modes
        elif settings.analysis_type == "Cyclic":
            total = len(
                cyclic_displacement_steps(
                    settings.cyclic_targets,
                    settings.cyclic_increment,
                )
            )
        else:
            total = settings.steps
        job.update_progress(
            0,
            total,
            algorithm=(
                "Eigen"
                if settings.analysis_type == "Modal"
                else settings.algorithm
            ),
            message="Starting solver",
        )
        self._jobs[job.job_id] = job
        self._current_job_id = job.job_id
        self._analysis_stop_requested = False
        self.results_panel.add_or_update_job(job)
        self._refresh_tree()

        self._append_analysis_log(
            f"OpenSeesPy Studio · Job {job.job_id}\n"
            f"Analysis: {settings.name} ({settings.analysis_type})\n"
            f"Python: {sys.executable}\n"
            + "-" * 72
            + "\n"
        )

        if settings.show_external_console:
            self._launch_external_solver_terminal(log_path, job.job_id)

        process = QProcess(self)
        process_environment = QProcessEnvironment.systemEnvironment()
        process_environment.insert(
            "PYTHONPATH",
            build_worker_pythonpath(
                process_environment.value("PYTHONPATH")
            ),
        )
        process.setProcessEnvironment(process_environment)
        process.setProgram(sys.executable)
        process.setArguments([
            "-m",
            "openseespy_studio.solver_worker",
            path,
            "--result-file",
            result_path,
        ])
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_analysis_stdout)
        process.readyReadStandardError.connect(self._read_analysis_stderr)
        process.finished.connect(self._analysis_finished)
        process.errorOccurred.connect(self._analysis_process_error)
        self._analysis_process = process

        self.console.appendPlainText(
            f">> Job {job.job_id}: starting {settings.analysis_type} "
            f"analysis with {Path(sys.executable).name}..."
        )
        self.console.appendPlainText(
            ">> Worker source path: "
            + build_worker_pythonpath("").split(os.pathsep)[0]
        )
        self.status_message.setText(
            f"Job {job.job_id} · 0/{total} · 0% · starting"
        )
        self.actions["run"].setText("Stop")
        self.actions["run"].setToolTip("Stop running analysis")
        self._job_ui_timer.start()
        process.start()

    def _launch_external_solver_terminal(
        self,
        log_path: str,
        job_id: int,
    ) -> None:
        if sys.platform != "win32":
            self.console.appendPlainText(
                ">> External solver terminal is currently supported "
                "only on Windows."
            )
            return

        escaped_path = str(log_path).replace("'", "''")
        command = (
            f"$host.UI.RawUI.WindowTitle='OpenSeesPy Studio - Job {job_id}'; "
            f"Get-Content -LiteralPath '{escaped_path}' -Wait"
        )
        try:
            result = QProcess.startDetached(
                "powershell.exe",
                [
                    "-NoLogo",
                    "-NoProfile",
                    "-NoExit",
                    "-Command",
                    command,
                ],
            )
            started = (
                bool(result[0])
                if isinstance(result, tuple)
                else bool(result)
            )
        except Exception as exc:
            started = False
            self.console.appendPlainText(
                f">> Could not open external solver terminal: {exc}"
            )

        if started:
            self.console.appendPlainText(
                f">> External solver terminal opened for Job {job_id}. "
                "Close that PowerShell window manually when finished."
            )
        else:
            self.console.appendPlainText(
                ">> External solver terminal could not be started. "
                "Live output remains available in the Studio Console."
            )

    def _append_analysis_log(self, text: str) -> None:
        path = self._analysis_log_path
        if not path or not text:
            return
        try:
            with Path(path).open("a", encoding="utf-8") as stream:
                stream.write(text)
        except OSError:
            pass

    def _format_solver_event(
        self,
        payload: dict[str, object],
    ) -> str:
        event = str(payload.get("event", ""))
        step = int(payload.get("step", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        algorithm = str(payload.get("algorithm", "") or "")
        iterations = int(payload.get("iterations", 0) or 0)
        norm = payload.get("norm")

        if event == "start":
            return (
                f"[Job] Solver started · {payload.get('analysis_type', '')} "
                f"· total={total} · algorithm={algorithm}"
            )

        if event == "step_start":
            return (
                f"▶ Step {step}/{total} · {algorithm} · "
                f"{payload.get('test', '')} · "
                f"tol={float(payload.get('tolerance', 0.0) or 0.0):.3e}"
            )

        if event == "progress":
            percent = float(payload.get("percent", 0.0) or 0.0)
            if "eigenvalue" in payload:
                return (
                    f"Mode {step}/{total} · {percent:5.1f}% "
                    f"· λ={float(payload.get('eigenvalue', 0.0)):.6g}"
                )

            time_value = float(payload.get("time", 0.0) or 0.0)
            monitor = float(payload.get("monitor", 0.0) or 0.0)
            base_shear = float(
                payload.get("base_shear", 0.0) or 0.0
            )
            norm_text = (
                f"{float(norm):.3e}"
                if norm is not None
                else "-"
            )
            return (
                f"Step {step}/{total} · {percent:5.1f}% "
                f"· t={time_value:.6g} · iter={iterations} "
                f"· norm={norm_text} · alg={algorithm} "
                f"· monitor={monitor:.6g} "
                f"· Vbase={base_shear:.6g} · OK"
            )

        if event == "convergence_failed":
            code = int(payload.get("code", 0) or 0)
            norm_text = (
                f"{float(norm):.3e}"
                if norm is not None
                else "-"
            )
            return (
                f"!! Step {step}/{total} · {algorithm} failed "
                f"· code={code} · iter={iterations} · norm={norm_text}"
            )

        if event == "fallback":
            return (
                f"→ Step {step}/{total} · trying fallback {algorithm}"
            )

        if event == "recovered":
            norm_text = (
                f"{float(norm):.3e}"
                if norm is not None
                else "-"
            )
            return (
                f"✓ Step {step}/{total} · recovered with {algorithm} "
                f"· iter={iterations} · norm={norm_text}"
            )

        if event == "failed":
            return (
                f"✗ Step {step}/{total} · convergence recovery exhausted "
                f"· algorithm={algorithm}"
            )

        if event == "cutback":
            return (
                f"↘ CUTBACK Step {step}/{total} · "
                f"|Δ| {float(payload.get('old_size', 0.0)):.6g} → "
                f"{float(payload.get('new_size', 0.0)):.6g} · "
                f"remaining={float(payload.get('remaining', 0.0)):.6g}"
            )

        if event == "grow":
            return (
                f"↗ GROW Step {step}/{total} · "
                f"|Δ| {float(payload.get('old_size', 0.0)):.6g} → "
                f"{float(payload.get('new_size', 0.0)):.6g}"
            )

        if event == "adaptive_substep":
            return (
                f"• Step {step}/{total} adaptive substep accepted · "
                f"Δ={float(payload.get('accepted_increment', 0.0)):.6g} · "
                f"remaining={float(payload.get('remaining', 0.0)):.6g} · "
                f"next |Δ|={float(payload.get('next_size', 0.0)):.6g}"
            )

        return "[Solver event] " + json.dumps(
            payload,
            ensure_ascii=False,
        )

    def _handle_solver_event(
        self,
        payload: dict[str, object],
    ) -> None:
        job = (
            self._jobs.get(self._current_job_id)
            if self._current_job_id is not None
            else None
        )
        if job is None:
            return

        event = str(payload.get("event", ""))
        if event == "start":
            self._live_convergence_context = {
                "step": 0,
                "total": int(payload.get("total", 0) or 0),
                "algorithm": str(payload.get("algorithm", "") or ""),
                "test": str(payload.get("test", "") or ""),
                "tolerance": payload.get("tolerance"),
                "enabled": bool(payload.get("live_convergence", False)),
            }
            if (
                str(payload.get("analysis_type", "")) != "Modal"
                and bool(payload.get("live_convergence", False))
            ):
                self.results_panel.start_live_convergence(
                    total=int(payload.get("total", 0) or 0),
                    test=str(payload.get("test", "") or ""),
                    tolerance=payload.get("tolerance"),
                    algorithm=str(payload.get("algorithm", "") or ""),
                )
                self.results_dock.show()
                self.results_dock.raise_()
        elif event == "step_start":
            self._live_convergence_context = {
                "step": int(payload.get("step", 0) or 0),
                "total": int(payload.get("total", 0) or 0),
                "algorithm": str(payload.get("algorithm", "") or ""),
                "test": str(payload.get("test", "") or ""),
                "tolerance": payload.get("tolerance"),
                "enabled": bool(payload.get("live_convergence", False)),
            }
            if bool(payload.get("live_convergence", False)):
                algorithm_label = str(payload.get("algorithm", "") or "")
                if payload.get("step_size") is not None:
                    algorithm_label += (
                        f" · |Δ|={float(payload.get('step_size', 0.0)):.6g}"
                    )
                self.results_panel.begin_live_convergence_step(
                    step=int(payload.get("step", 0) or 0),
                    total=int(payload.get("total", 0) or 0),
                    algorithm=algorithm_label,
                    test=str(payload.get("test", "") or ""),
                    tolerance=payload.get("tolerance"),
                )
        elif event == "progress":
            step = int(payload.get("step", 0) or 0)
            total = int(payload.get("total", 0) or 0)
            algorithm = str(payload.get("algorithm", "") or "")
            iterations = int(payload.get("iterations", 0) or 0)
            message = (
                f"{algorithm} · iter {iterations}"
                if algorithm
                else f"Step {step}/{total}"
            )
            job.update_progress(
                step,
                total,
                algorithm=algorithm,
                iterations=iterations,
                message=message,
            )
            self.status_message.setText(
                f"Job {job.job_id} · {step}/{total} "
                f"· {job.progress_percent:.1f}% · {message}"
            )
            if (
                "eigenvalue" not in payload
                and bool(self._live_convergence_context.get("enabled"))
            ):
                self.results_panel.update_live_analysis_coordinate(
                    payload.get("time")
                )
                self.results_panel.finish_live_convergence("CONVERGED")
        elif event == "convergence_failed":
            job.message = (
                f"Step {payload.get('step')}: "
                f"{payload.get('algorithm')} failed; recovering"
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.finish_live_convergence("RECOVERING")
        elif event == "fallback":
            job.message = (
                f"Trying {payload.get('algorithm')} "
                f"at step {payload.get('step')}"
            )
            self._live_convergence_context["algorithm"] = str(
                payload.get("algorithm", "") or ""
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.begin_live_convergence_attempt(
                    str(payload.get("algorithm", "") or "")
                )
        elif event == "recovered":
            job.message = (
                f"Recovered with {payload.get('algorithm')} "
                f"at step {payload.get('step')}"
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.finish_live_convergence("RECOVERED")
        elif event == "failed":
            job.message = (
                f"Convergence failed at step {payload.get('step')}"
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.finish_live_convergence("FAILED")

        elif event == "cutback":
            old_size = float(payload.get("old_size", 0.0) or 0.0)
            new_size = float(payload.get("new_size", 0.0) or 0.0)
            job.message = (
                f"CUTBACK step {payload.get('step')}: "
                f"|Δ| {old_size:.6g} → {new_size:.6g}"
            )
            self._live_convergence_context["algorithm"] = str(
                payload.get("algorithm", "") or ""
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.finish_live_convergence("CUTBACK")
                self.results_panel.begin_live_convergence_attempt(
                    f"{payload.get('algorithm', '-')} · CUTBACK |Δ|={new_size:.6g}"
                )
        elif event == "grow":
            old_size = float(payload.get("old_size", 0.0) or 0.0)
            new_size = float(payload.get("new_size", 0.0) or 0.0)
            job.message = (
                f"GROW step {payload.get('step')}: "
                f"|Δ| {old_size:.6g} → {new_size:.6g}"
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.set_live_convergence_message(
                    f"GROW · Step {payload.get('step')}/"
                    f"{payload.get('total')} · |Δ| {old_size:.6g} → "
                    f"{new_size:.6g}"
                )
        elif event == "adaptive_substep":
            next_size = float(payload.get("next_size", 0.0) or 0.0)
            job.message = (
                f"Adaptive substep accepted at step {payload.get('step')}; "
                f"next |Δ|={next_size:.6g}"
            )
            self._live_convergence_context["algorithm"] = str(
                payload.get("algorithm", "") or ""
            )
            if bool(self._live_convergence_context.get("enabled")):
                self.results_panel.mark_live_substep_converged(
                    payload.get("time")
                )
                self.results_panel.begin_live_convergence_attempt(
                    f"{payload.get('algorithm', '-')} · |Δ|={next_size:.6g}"
                )

        self.results_panel.add_or_update_job(job)

    def _handle_solver_line(
        self,
        line: str,
        *,
        is_stderr: bool = False,
    ) -> None:
        if not line:
            return

        display = line
        parsed_convergence = parse_opensees_convergence_line(line)
        if (
            parsed_convergence is not None
            and bool(self._live_convergence_context.get("enabled"))
        ):
            iteration = int(
                parsed_convergence.get("iteration", 0) or 0
            )
            if iteration > 0:
                self.results_panel.append_live_convergence_iteration(
                    iteration=iteration,
                    norm=float(
                        parsed_convergence.get("norm", 0.0) or 0.0
                    ),
                    tolerance=parsed_convergence.get("tolerance"),
                    test=str(
                        parsed_convergence.get("test", "") or ""
                    ),
                    algorithm=str(
                        self._live_convergence_context.get(
                            "algorithm",
                            "",
                        )
                        or ""
                    ),
                )

        prefix = "[STUDIO_EVENT] "
        if line.startswith(prefix):
            try:
                payload = json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                self._handle_solver_event(payload)
                display = self._format_solver_event(payload)

        if is_stderr:
            display = "[stderr] " + display

        self.console.appendPlainText(display)
        self._append_analysis_log(display + "\n")

    def _consume_solver_text(
        self,
        text: str,
        *,
        is_stderr: bool,
    ) -> None:
        attribute = (
            "_analysis_stderr_buffer"
            if is_stderr
            else "_analysis_stdout_buffer"
        )
        combined = getattr(self, attribute) + text
        lines = combined.split("\n")
        setattr(self, attribute, lines.pop())
        for line in lines:
            self._handle_solver_line(
                line.rstrip("\r"),
                is_stderr=is_stderr,
            )

    def _flush_solver_buffers(self) -> None:
        for attribute, is_stderr in (
            ("_analysis_stdout_buffer", False),
            ("_analysis_stderr_buffer", True),
        ):
            remainder = getattr(self, attribute)
            if remainder:
                self._handle_solver_line(
                    remainder.rstrip("\r"),
                    is_stderr=is_stderr,
                )
            setattr(self, attribute, "")

    def _refresh_running_job_ui(self) -> None:
        if self._current_job_id is None:
            self._job_ui_timer.stop()
            return
        job = self._jobs.get(self._current_job_id)
        if job is None:
            self._job_ui_timer.stop()
            return
        self.results_panel.add_or_update_job(job)

    def _stop_analysis(self) -> None:
        process = self._analysis_process
        if process is None or process.state() == QProcess.NotRunning:
            return

        self._analysis_stop_requested = True
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
            self._consume_solver_text(text, is_stderr=False)

    def _read_analysis_stderr(self) -> None:
        process = self._analysis_process
        if process is None:
            return
        text = bytes(process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )
        if text:
            self._consume_solver_text(text, is_stderr=True)

    def _analysis_process_error(self, error) -> None:
        process = self._analysis_process
        if process is None:
            return
        self.console.appendPlainText(
            f"\n>> Analysis worker process error: {process.errorString()}"
        )

    def _read_worker_result(self) -> tuple[dict[str, object], str]:
        path = self._analysis_result_path
        if not path:
            return {}, ""
        try:
            text = Path(path).read_text(encoding="utf-8").strip()
            if not text:
                return {}, ""
            payload = json.loads(text)
            if not isinstance(payload, dict):
                return {}, ""
            results = payload.get("results", {})
            error = str(payload.get("error", "") or "")
            return (
                dict(results) if isinstance(results, dict) else {},
                error,
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}, ""

    def _analysis_finished(self, exit_code: int, exit_status) -> None:
        self._flush_solver_buffers()
        self._job_ui_timer.stop()
        crashed = exit_status == QProcess.CrashExit
        result, worker_error = self._read_worker_result()
        job = (
            self._jobs.get(self._current_job_id)
            if self._current_job_id is not None
            else None
        )

        if self._analysis_stop_requested:
            status = "Stopped"
            message = "Stopped by user"
            self.console.appendPlainText("\n>> Analysis worker stopped.")
            self.status_message.setText("Analysis stopped")
        elif crashed:
            status = "Crashed"
            message = worker_error.splitlines()[-1] if worker_error else "Worker crashed"
            self.console.appendPlainText(
                f"\n>> Analysis worker crashed (exit code {exit_code}). "
                "The Studio GUI remains available."
            )
            self.status_message.setText("Analysis worker crashed")
        elif exit_code == 0:
            status = "Completed"
            message = "Results captured" if result else "Completed; no result data"
            self.console.appendPlainText(
                "\n>> Analysis worker completed successfully."
            )
            self.status_message.setText("Analysis completed")
        else:
            status = "Failed"
            message = worker_error.splitlines()[-1] if worker_error else f"Exit code {exit_code}"
            self.console.appendPlainText(
                f"\n>> Analysis worker exited with code {exit_code}."
            )
            self.status_message.setText(
                f"Analysis failed (exit code {exit_code})"
            )

        if result:
            try:
                result = enrich_member_force_results(
                    result,
                    self.model,
                    self.project.element_loads,
                    self.project.sections,
                    self.project.materials,
                    self.project.transformations,
                    self.project.units,
                )
                result = enrich_fiber_state_results(
                    result,
                    self.project.materials,
                )
            except ValueError as exc:
                self._log(
                    "Member-force post-processing warning: "
                    + str(exc)
                )

        if job is not None:
            job.finish(
                status,
                exit_code=exit_code,
                message=message,
                results=result,
            )
            self.results_panel.add_or_update_job(job)

        if result:
            self._last_result = result
            self.results_panel.set_result(result)
            analysis_type = str(result.get("analysis", {}).get("type", ""))
            if analysis_type == "Modal":
                modes = result.get("modes", {})
                if isinstance(modes, dict) and modes:
                    first_mode = min(int(key) for key in modes)
                    self.viewport.show_mode_shape(
                        result,
                        first_mode,
                        scale=1.0,
                    )
            elif result.get("final"):
                self.viewport.show_deformed_shape(result, scale=10.0)

        self._append_analysis_log(
            "-" * 72 + "\n"
            + f"Job finished · status={status} · exit_code={exit_code}\n"
        )
        self.actions["run"].setText("Run")
        self.actions["run"].setToolTip("Run model")
        self._analysis_process = None
        self._analysis_stop_requested = False
        self._current_job_id = None
        self._cleanup_analysis_files()
        self._refresh_tree()

    def _reset_runtime_results(self) -> None:
        self._jobs.clear()
        self._job_counter = 0
        self._current_job_id = None
        self._live_convergence_context = {
            "step": 0,
            "total": 0,
            "algorithm": "",
            "test": "",
            "tolerance": None,
            "enabled": False,
        }
        self._last_result = {}
        self._active_solution_result_tag = None
        self.viewport.clear_result_overlay()
        self.results_panel.clear_all()

    def _select_job_result(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        if job.results:
            self._last_result = dict(job.results)
            self.results_panel.set_result(self._last_result)
        self._show_job_properties(job.job_id)
        self.status_message.setText(
            f"Selected Job {job.job_id}: {job.analysis_name}"
        )

    def _show_deformation_result(self, scale: float) -> None:
        if not self._last_result:
            self.status_message.setText("No analysis result available")
            return
        self.viewport.show_deformed_shape(
            self._last_result,
            scale=float(scale),
        )
        self.status_message.setText(
            f"Showing deformed shape · scale {float(scale):g}"
        )

    def _show_node_contour_result(
        self,
        quantity: str,
        component: str,
    ) -> None:
        if not self._last_result:
            self.status_message.setText("No nodal result available")
            return
        self.viewport.show_node_contour(
            self._last_result,
            str(quantity),
            str(component),
        )
        self.status_message.setText(
            f"Showing {str(quantity).lower()} contour · {component}"
        )

    def _select_result_element(self, tag: int) -> None:
        tag = int(tag)
        if tag not in self.model.elements:
            return
        self.selection.set_selection(elements={tag})
        self.viewport.zoom_to_selection(set(), {tag})
        self.status_message.setText(
            f"Selected result member {tag}"
        )

    def _show_hinge_state_result(self) -> None:
        if not self._last_result:
            self.status_message.setText(
                "No fiber-state result available"
            )
            return
        self.viewport.show_hinge_states(self._last_result)
        self.status_message.setText(
            "Showing fiber-based plastic hinge / limit states"
        )

    def _show_member_force_result(
        self,
        component: str,
        scale: float,
    ) -> None:
        if not self._last_result:
            self.status_message.setText(
                "No member-force result available"
            )
            return
        self.viewport.show_member_force_diagram(
            self._last_result,
            self.project.transformations,
            str(component),
            scale=float(scale),
        )
        self.status_message.setText(
            f"Showing local {component} diagram · scale "
            f"{float(scale):g}"
        )

    def _show_mode_shape_result(self, mode: int, scale: float) -> None:
        if not self._last_result:
            self.status_message.setText("No modal result available")
            return
        self.viewport.show_mode_shape(
            self._last_result,
            int(mode),
            scale=float(scale),
        )
        self.status_message.setText(
            f"Showing mode {int(mode)} · scale {float(scale):g}"
        )

    def _cleanup_analysis_files(self) -> None:
        paths = (
            self._analysis_script_path,
            self._analysis_result_path,
        )
        self._analysis_script_path = None
        self._analysis_result_path = None
        for path in paths:
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass

        log_path = self._analysis_log_path
        self._analysis_log_path = None
        if log_path:
            if self._analysis_external_console:
                self._external_log_paths.append(log_path)
            else:
                try:
                    Path(log_path).unlink(missing_ok=True)
                except OSError:
                    pass
        self._analysis_external_console = False

    def closeEvent(self, event) -> None:
        if not self._maybe_save_changes():
            event.ignore()
            return
        process = self._analysis_process
        if process is not None and process.state() != QProcess.NotRunning:
            process.kill()
            process.waitForFinished(1000)
        self._cleanup_analysis_files()
        for path in self._external_log_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        self._external_log_paths.clear()
        super().closeEvent(event)

    def _not_implemented(self) -> None:
        action = self.sender()
        label = action.text() if isinstance(action, QAction) else "Command"
        self._log(f"{label}: planned for the next milestone")

    def _log(self, text: str) -> None:
        self.console.appendPlainText(">> " + text)
