from __future__ import annotations

from pathlib import Path
import json
import math
import os
import sys
import tempfile

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, QTimer, QUrl, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QDesktopServices, QFont, QKeySequence, QPainter, QPainterPath, QPen, QShortcut, QTextCursor, QUndoStack
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

from ..brand import (
    BRAND_NAVY,
    BRAND_RED,
    PRODUCT_BACKEND,
    PRODUCT_FULL_NAME,
    PRODUCT_NAME,
    PRODUCT_SHORT_DESCRIPTION,
    PRODUCT_STAGE,
    LEGACY_SETTINGS_APPLICATION,
    LEGACY_SETTINGS_ORGANIZATION,
)
from ..calibration import (
    CalibrationCase,
    apply_calibration_case,
    calibration_case_changes,
    calibration_case_script,
    calibration_grid_size,
    calibration_parameter_payload,
)
from ..ai_assistant import compact_for_llm, prepare_project_snapshot
from ..analysis_templates import (
    GroundMotionComponentSpec,
    build_cyclic_template,
    build_modal_template,
    build_nlth_multi_template,
    build_pushover_template,
    build_reference_lateral_loading,
    default_control_node,
)
from ..frame_setup import prepare_frame_grid
from ..generator import FrameGridSpec, cyclic_displacement_steps, generate_frame_grid, to_openseespy
from ..importer import import_openseespy_source
from ..jobs import JobRecord
from ..live_convergence import parse_opensees_convergence_line
from ..model import (
    FRAME_ELEMENT_TYPES,
    SHELL_ELEMENT_TYPES,
    StructuralModel,
    classify_fixity,
    shell_surface_geometry,
)
from ..mass_source import apply_mass_source, evaluate_mass_source
from ..moment_curvature import build_moment_curvature_project
from ..postprocess import enrich_fiber_state_results, enrich_member_force_results
from ..test_column import build_test_column
from ..result_catalog import (
    convergence_result_label,
    result_choices_for_analysis,
)
from ..shell_mesh import build_shell_mesh
from ..surface_mesher import mesh_surface_geometry
from ..section_response import section_response_sources
from ..project import AnalysisSettingsData, ConnectionData, ConstraintData, ElementLoadData, LoadPatternData, MassSourceData, MaterialData, NDMaterialData, NodalLoadData, PrescribedDisplacementData, ProjectDatabase, RecorderData, SectionData, SelectionSetData, SolutionResultData, TimeSeriesData, TransformationData, SHELL_SECTION_TYPES, SUPPORTED_CONNECTION_TYPES, material_parameter_kind
from ..runtime import (
    build_worker_pythonpath,
    opensees_material_requires_runtime_probe,
    probe_opensees_material_support,
    probe_opensees_runtime,
    worker_process_command,
)
from ..validation import ValidationIssue, validate_project
from ..units import UnitSystem
from .ai_assistant_panel import AIAssistantPanel
from .analysis_dialog import AnalysisDialog
from .analysis_template_dialog import AnalysisTemplateDialog, CyclicProtocolPreview
from .calibration_dialog import (
    ApplyCalibrationCaseDialog,
    CalibrationDialog,
)
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
    TrussDialog,
    VectorDialog,
)
from .history import ProjectSnapshotCommand
from .hinge_backbone_dialog import HingeBackboneDialog
from .import_report_dialog import ImportReportDialog
from .load_dialogs import ElementLoadDialog, GroundMotionDialog, LoadPatternDialog, MassDialog, NodalLoadDialog, PrescribedDisplacementDialog, TimeSeriesDialog
from .material_dialog import MaterialDialog
from .material_library_dialog import MaterialLibraryDialog
from .mass_source_dialog import MassSourceDialog
from .model_check_dialog import ModelCheckDialog
from .moment_curvature_dialog import MomentCurvatureDialog
from .recorder_dialog import RecorderDialog
from .section_dialog import SectionDialog
from .shell_dialog import NDMaterialDialog, ShellElementDialog, ShellMeshDialog, ShellSectionDialog
from .surface_dialog import SurfaceGeometryDialog
from .transformation_dialog import TransformationDialog
from .test_column_dialog import TestColumnWizard
from .icons import studio_icon
from .results_panel import ResultsPanel
from .restraint_dialog import RestraintDialog
from .selection import SelectionManager, parse_tag_expression
from .viewport import ModelViewport


UNIT_PRESETS: tuple[tuple[str, dict[str, str]], ...] = (
    ("m - kN - s", {"length": "m", "force": "kN", "time": "s"}),
    ("m - N - s", {"length": "m", "force": "N", "time": "s"}),
    ("mm - N - s", {"length": "mm", "force": "N", "time": "s"}),
    ("mm - kN - s", {"length": "mm", "force": "kN", "time": "s"}),
    ("in - kip - s", {"length": "in", "force": "kip", "time": "s"}),
)


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
    background: #f6f7f9;
    border: none;
    border-bottom: 1px solid #bfc8d2;
    spacing: 0;
    padding: 0;
}
QTabWidget#RibbonTabs::pane {
    border: none;
    border-top: 1px solid #cfd6de;
    background: #f8f9fb;
}
QTabBar#RibbonTabBar {
    background: #f2f3f5;
}
QTabBar#RibbonTabBar::tab {
    background: #f2f3f5;
    color: #27394b;
    border: none;
    border-right: 1px solid transparent;
    padding: 5px 16px 4px 16px;
    min-width: 48px;
}
QTabBar#RibbonTabBar::tab:hover {
    background: #e7edf5;
}
QTabBar#RibbonTabBar::tab:selected {
    background: #ffffff;
    color: #145da0;
    border-top: 2px solid #2f80ed;
    padding-top: 3px;
    font-weight: 600;
}
QWidget#RibbonPage {
    background: #ffffff;
}
QWidget#RibbonGroup {
    border-right: 1px solid #d4d9df;
    background: transparent;
}
QLabel#RibbonCaption {
    color: #617080;
    font-size: 9px;
    padding: 1px 5px 2px 5px;
}
QToolButton#RibbonLargeButton,
QToolButton#RibbonSmallButton {
    color: #203247;
    border: 1px solid transparent;
    border-radius: 2px;
}
QToolButton#RibbonLargeButton {
    padding: 3px 5px;
    min-width: 54px;
    min-height: 58px;
}
QToolButton#RibbonSmallButton {
    padding: 1px 5px;
    min-width: 84px;
    min-height: 22px;
    text-align: left;
}
QToolButton#RibbonLargeButton:hover,
QToolButton#RibbonSmallButton:hover {
    background: #e9f3ff;
    border-color: #b9d1ec;
}
QToolButton#RibbonLargeButton:pressed,
QToolButton#RibbonLargeButton:checked,
QToolButton#RibbonSmallButton:pressed,
QToolButton#RibbonSmallButton:checked {
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
    """Compact SARE wordmark for the application ribbon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(330)
        self.setMinimumHeight(64)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Primary wordmark.
        painter.setPen(QColor(BRAND_NAVY))
        font = QFont(self.font())
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(8, 31, PRODUCT_NAME)

        # Minimal deformation/response curve under the SARE wordmark.
        path = QPainterPath()
        path.moveTo(8, 43)
        path.cubicTo(28, 43, 40, 42, 51, 35)
        path.cubicTo(61, 29, 68, 24, 77, 27)
        path.cubicTo(86, 30, 91, 40, 101, 43)
        path.cubicTo(108, 45, 116, 44, 124, 43)
        response_pen = QPen(QColor(BRAND_RED), 3.0)
        response_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        response_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(response_pen)
        painter.drawPath(path)

        # Descriptor: detailed enough for identity, compact enough for ribbon.
        painter.setPen(QColor("#556B80"))
        font.setPointSize(7)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(145, 25, "Structural Analysis & Research")
        painter.drawText(145, 39, "Environment for OpenSees")

        painter.setPen(QColor(BRAND_NAVY))
        font.setPointSize(6)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(145, 52, "STRUCTURAL SIMULATION · RESEARCH")


class RibbonGroup(QWidget):
    """Compact ANSYS-style ribbon group with large and stacked commands."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 2, 5, 0)
        layout.setSpacing(0)

        self.body = QHBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(1)
        layout.addLayout(self.body, 1)

        self._small_column: QVBoxLayout | None = None
        self._small_column_count = 0

        label = QLabel(caption)
        label.setObjectName("RibbonCaption")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    def add_large_action(self, action: QAction) -> QToolButton:
        self._small_column = None
        self._small_column_count = 0
        button = QToolButton()
        button.setObjectName("RibbonLargeButton")
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(28, 28))
        button.setAutoRaise(True)
        self.body.addWidget(button, 0, Qt.AlignTop)
        return button

    def _ensure_small_column(self) -> QVBoxLayout:
        if self._small_column is None or self._small_column_count >= 3:
            holder = QWidget()
            column = QVBoxLayout(holder)
            column.setContentsMargins(0, 1, 0, 0)
            column.setSpacing(0)
            column.addStretch(1)
            self.body.addWidget(holder, 0, Qt.AlignTop)
            self._small_column = column
            self._small_column_count = 0
        return self._small_column

    def add_small_action(self, action: QAction) -> QToolButton:
        column = self._ensure_small_column()
        button = QToolButton()
        button.setObjectName("RibbonSmallButton")
        button.setDefaultAction(action)
        ribbon_text = action.property("ribbonText")
        if ribbon_text:
            button.setText(str(ribbon_text))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(16, 16))
        button.setAutoRaise(True)
        column.insertWidget(column.count() - 1, button)
        self._small_column_count += 1
        return button

    def add_action(self, action: QAction) -> None:
        self.add_large_action(action)

    def add_widget(self, widget: QWidget) -> None:
        self._small_column = None
        self._small_column_count = 0
        self.body.addWidget(widget, 0, Qt.AlignVCenter)


class RibbonPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonPage")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(4, 2, 4, 0)
        self.row.setSpacing(0)

    def add_group(self, group: RibbonGroup) -> None:
        self.row.addWidget(group)

    def finish(self) -> None:
        self.row.addStretch(1)


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

        dimension_form = QFormLayout()
        self.dimension = QComboBox()
        self.dimension.addItem("3D Frame Grid", "3D")
        self.dimension.addItem("2D Frame (X-Z)", "2D")
        self.dimension.setToolTip(
            "2D Frame creates one X-Z plane and automatically restrains "
            "UY, RX and RZ at every node so the current 3D-compatible "
            "Studio backend behaves as a planar frame."
        )
        dimension_form.addRow("Frame type:", self.dimension)
        layout.addLayout(dimension_form)

        self.planar_note = QLabel(
            "2D mode: one X-Z frame plane; active structural DOFs are "
            "UX, UZ and RY. UY, RX and RZ are restrained automatically."
        )
        self.planar_note.setWordWrap(True)
        self.planar_note.setObjectName("Muted")
        layout.addWidget(self.planar_note)

        self.frame_preview = QLabel()
        self.frame_preview.setWordWrap(True)
        self.frame_preview.setObjectName("Muted")
        layout.addWidget(self.frame_preview)

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

        self.planar_base_support = QComboBox()
        self.planar_base_support.addItems(["Fixed", "Pinned"])
        base_form = QFormLayout()
        base_form.addRow("2D base support:", self.planar_base_support)
        base_widget = QWidget()
        base_widget.setLayout(base_form)
        layout.addWidget(base_widget)

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

        self.dimension.currentIndexChanged.connect(
            self._sync_dimension_mode
        )
        for widget in (
            self.nx,
            self.ny,
            self.nz,
            self.columns,
            self.beams,
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._update_frame_preview)
            if hasattr(widget, "toggled"):
                widget.toggled.connect(self._update_frame_preview)
        self._sync_dimension_mode()

    def set_planar_2d(self, enabled: bool) -> None:
        index = self.dimension.findData("2D" if enabled else "3D")
        if index >= 0:
            self.dimension.setCurrentIndex(index)
        self._sync_dimension_mode()

    def _sync_dimension_mode(self, *_args) -> None:
        planar = self.dimension.currentData() == "2D"
        self.ny.setEnabled(not planar)
        self.dy.setEnabled(not planar)
        self.planar_base_support.setEnabled(planar)
        self.planar_note.setVisible(planar)
        self.circular.setEnabled(False)
        self._update_frame_preview()

    def _update_frame_preview(self, *_args) -> None:
        planar = self.dimension.currentData() == "2D"
        nx = self.nx.value()
        ny = self.ny.value()
        nz = self.nz.value()
        if planar:
            nodes = (nx + 1) * (nz + 1)
            columns = nz * (nx + 1) if self.columns.isChecked() else 0
            beams = nx * nz if self.beams.isChecked() else 0
            self.frame_preview.setText(
                f"Preview: 2D X-Z · {nodes} nodes · "
                f"{columns + beams} elements "
                f"({columns} columns + {beams} beams)"
            )
            return
        nodes = (nx + 1) * (ny + 1) * (nz + 1)
        columns = (
            nz * (nx + 1) * (ny + 1)
            if self.columns.isChecked()
            else 0
        )
        beams = (
            (
                nx * (ny + 1) * nz
                + ny * (nx + 1) * nz
            )
            if self.beams.isChecked()
            else 0
        )
        self.frame_preview.setText(
            f"Preview: 3D · {nodes} nodes · "
            f"{columns + beams} elements"
        )

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
            create_beams_y=(
                self.beams.isChecked()
                and self.dimension.currentData() != "2D"
            ),
            column_section_tag=self.column_section.currentData(),
            beam_section_tag=self.beam_section.currentData(),
            column_transf_tag=self.column_transformation.currentData(),
            beam_transf_tag=self.beam_transformation.currentData(),
            planar_2d=self.dimension.currentData() == "2D",
            planar_base_support=self.planar_base_support.currentText(),
        ))


class PropertiesPanel(QWidget):
    solution_result_apply = Signal(int, object)
    solution_result_evaluate = Signal(int, object)
    solution_scope_from_selection = Signal(int)
    property_edited = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._solution_result_tag: int | None = None
        self._solution_result_auto_scale = True
        self._property_context: dict[str, object] = {}
        self._building_property_grid = False

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
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.table.itemChanged.connect(self._property_item_changed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 112)
        layout.addWidget(self.table, 1)

        self.cyclic_protocol_view = QWidget()
        cyclic_layout = QVBoxLayout(self.cyclic_protocol_view)
        cyclic_layout.setContentsMargins(0, 0, 0, 0)
        cyclic_layout.setSpacing(6)

        self.cyclic_protocol_summary = QLabel()
        self.cyclic_protocol_summary.setWordWrap(True)
        self.cyclic_protocol_summary.setObjectName("Muted")
        cyclic_layout.addWidget(self.cyclic_protocol_summary)

        self.cyclic_protocol_preview = CyclicProtocolPreview()
        self.cyclic_protocol_preview.setMinimumHeight(130)
        cyclic_layout.addWidget(self.cyclic_protocol_preview)

        self.cyclic_protocol_table = QTableWidget(0, 2)
        self.cyclic_protocol_table.setHorizontalHeaderLabels(
            ["Target #", "Value"]
        )
        self.cyclic_protocol_table.verticalHeader().hide()
        self.cyclic_protocol_table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.cyclic_protocol_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.cyclic_protocol_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.cyclic_protocol_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.cyclic_protocol_table.setColumnWidth(0, 72)
        cyclic_layout.addWidget(self.cyclic_protocol_table, 1)

        layout.addWidget(self.cyclic_protocol_view, 1)
        self.cyclic_protocol_view.hide()

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
        self.result_display = QComboBox()
        self.result_display.addItem("Deformed only", "deformed_only")
        self.result_display.addItem(
            "Undeformed + Deformed",
            "both",
        )
        self.result_display.addItem(
            "Undeformed only",
            "undeformed_only",
        )
        self.result_representation = QComboBox()
        self.result_representation.addItem(
            "Actual Section",
            "actual_section",
        )
        self.result_representation.addItem("Tube", "tube")
        self.result_representation.addItem(
            "Centerline",
            "centerline",
        )
        self.result_smooth_curvature = QCheckBox(
            "Smooth member curvature"
        )
        self.result_smooth_curvature.setChecked(True)
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
            ("Display", self.result_display),
            ("Representation", self.result_representation),
            ("Curvature", self.result_smooth_curvature),
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
            self.result_display,
            self.result_representation,
            self.result_smooth_curvature,
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

    @staticmethod
    def _property_spec(row) -> tuple[str, object, dict[str, object]]:
        if len(row) >= 3 and isinstance(row[2], dict):
            return str(row[0]), row[1], dict(row[2])
        return str(row[0]), row[1], {}

    def _emit_combo_property(
        self,
        property_id: str,
        combo: QComboBox,
    ) -> None:
        if self._building_property_grid:
            return
        self.property_edited.emit({
            "context": dict(self._property_context),
            "id": str(property_id),
            "value": combo.currentData(),
        })

    def _property_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building_property_grid or item.column() != 1:
            return
        spec = item.data(Qt.UserRole)
        if not isinstance(spec, dict) or not spec.get("editable"):
            return
        self.property_edited.emit({
            "context": dict(self._property_context),
            "id": str(spec.get("id", "")),
            "value": item.text(),
        })

    def set_properties(
        self,
        title: str,
        rows,
        *,
        context: dict[str, object] | None = None,
    ) -> None:
        self._solution_result_tag = None
        self._property_context = dict(context or {})
        self.result_editor.hide()
        self.cyclic_protocol_view.hide()
        self.table.show()
        self.apply_button.hide()
        self.entity_label.setText(title)
        self._building_property_grid = True
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows))
            for index, raw_row in enumerate(rows):
                key, value, spec = self._property_spec(raw_row)
                editable = bool(spec.get("editable", False))
                property_id = str(spec.get("id", key))

                key_item = QTableWidgetItem(key)
                key_item.setFlags(
                    key_item.flags() & ~Qt.ItemIsEditable
                )
                key_item.setBackground(QColor("#eef1f4"))
                self.table.setItem(index, 0, key_item)

                kind = str(spec.get("kind", "text"))
                choices = spec.get("choices")
                if editable and kind == "choice" and isinstance(choices, (list, tuple)):
                    combo = QComboBox()
                    for choice in choices:
                        if isinstance(choice, (list, tuple)) and len(choice) >= 2:
                            combo.addItem(str(choice[0]), choice[1])
                        else:
                            combo.addItem(str(choice), choice)
                    current = spec.get("current", value)
                    current_index = combo.findData(current)
                    if current_index < 0:
                        current_index = combo.findText(str(value))
                    if current_index >= 0:
                        combo.setCurrentIndex(current_index)
                    combo.currentIndexChanged.connect(
                        lambda _index, pid=property_id, widget=combo: (
                            self._emit_combo_property(pid, widget)
                        )
                    )
                    self.table.setCellWidget(index, 1, combo)
                    continue

                value_item = QTableWidgetItem(str(value))
                item_spec = dict(spec)
                item_spec["id"] = property_id
                item_spec["editable"] = editable
                value_item.setData(Qt.UserRole, item_spec)
                if not editable:
                    value_item.setFlags(
                        value_item.flags() & ~Qt.ItemIsEditable
                    )
                    value_item.setBackground(QColor("#e3e6e9"))
                    value_item.setForeground(QColor("#69737d"))
                else:
                    value_item.setBackground(QColor("#ffffff"))
                    value_item.setForeground(QColor("#1f2f40"))
                self.table.setItem(index, 1, value_item)
        finally:
            self.table.blockSignals(False)
            self._building_property_grid = False

    def set_cyclic_protocol(
        self,
        settings: AnalysisSettingsData,
    ) -> None:
        self._solution_result_tag = None
        self._property_context = {}
        self.result_editor.hide()
        self.table.hide()
        self.apply_button.hide()
        self.cyclic_protocol_view.show()
        self.entity_label.setText("Cyclic Protocol")

        targets = [float(value) for value in settings.cyclic_targets]
        expanded = cyclic_displacement_steps(
            targets,
            settings.cyclic_increment,
        )
        self.cyclic_protocol_summary.setText(
            f"Control: Node {settings.control_node} · "
            f"DOF {settings.control_dof}   |   "
            f"Targets: {len(targets)}   |   "
            f"Max increment: {settings.cyclic_increment:g}   |   "
            f"Expanded steps: {len(expanded)}"
        )
        self.cyclic_protocol_preview.set_targets(targets)

        table = self.cyclic_protocol_table
        table.setRowCount(len(targets))
        for index, value in enumerate(targets):
            number_item = QTableWidgetItem(str(index + 1))
            number_item.setTextAlignment(Qt.AlignCenter)
            value_item = QTableWidgetItem(f"{value:g}")
            table.setItem(index, 0, number_item)
            table.setItem(index, 1, value_item)
        if targets:
            table.scrollToTop()

    def set_solution_result(
        self,
        result: SolutionResultData,
        *,
        analysis_name: str,
    ) -> None:
        self._solution_result_tag = int(result.tag)
        self.table.hide()
        self.cyclic_protocol_view.hide()
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
        self._solution_result_auto_scale = bool(
            options.get("auto_scale", True)
        )

        if kind in {
            "DeformedShape",
            "NodalDisplacement",
            "NodalReaction",
            "MemberForce",
            "ShellForce",
            "ShellDeformation",
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
        elif kind == "ShellForce":
            component_options = [
                "Nxx", "Nyy", "Nxy",
                "Mxx", "Myy", "Mxy",
                "Qx", "Qy",
            ]
        elif kind == "ShellDeformation":
            component_options = [
                "Exx", "Eyy", "Gxy",
                "Kxx", "Kyy", "Kxy",
                "Gxz", "Gyz",
            ]
        elif kind == "SectionResponse":
            component_options = ["P", "Mz", "My", "T"]

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

        if kind in {"DeformedShape", "MemberForce", "ModeShape", "Motion"}:
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

        if kind in {"DeformedShape", "ModeShape"}:
            self._set_form_row_visible(self.result_display, True)
            self._set_form_row_visible(
                self.result_representation,
                True,
            )
            self._set_form_row_visible(
                self.result_smooth_curvature,
                True,
            )
            display_mode = str(
                options.get("display_mode", "deformed_only")
            )
            index = self.result_display.findData(display_mode)
            self.result_display.setCurrentIndex(
                index if index >= 0 else 0
            )
            representation = str(
                options.get("representation", "actual_section")
            )
            index = self.result_representation.findData(
                representation
            )
            self.result_representation.setCurrentIndex(
                index if index >= 0 else 0
            )
            self.result_smooth_curvature.setChecked(
                bool(options.get("smooth_curvature", True))
            )

        if kind == "ModeShape" or (
            kind == "Motion" and "mode" in options
        ):
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

        if kind in {"FiberStress", "FiberStrain", "SectionResponse"}:
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
            "ShellForce",
            "ShellDeformation",
            "SectionResponse",
        }:
            settings["component"] = self.result_component.currentText()
        if kind in {"DeformedShape", "MemberForce", "ModeShape", "Motion"}:
            settings["scale"] = self.result_scale.value()
        if kind in {"DeformedShape", "ModeShape"}:
            settings["display_mode"] = str(
                self.result_display.currentData()
            )
            settings["representation"] = str(
                self.result_representation.currentData()
            )
            settings["smooth_curvature"] = (
                self.result_smooth_curvature.isChecked()
            )
        if kind == "ModeShape":
            settings["mode"] = self.result_mode.value()
        if kind == "Motion":
            settings["auto_scale"] = self._solution_result_auto_scale
            if self.result_mode.isVisible():
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
        if kind == "SectionResponse":
            settings["section"] = self.result_fiber_section.value()

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


def _dock_toggle_action(
    dock: QDockWidget,
    *,
    fallback_text: str | None = None,
) -> QAction:
    """Return a non-empty dock visibility action for the Window menu."""
    action = dock.toggleViewAction()
    if fallback_text and not action.text().strip():
        action.setText(fallback_text)
    return action


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{PRODUCT_NAME} ({PRODUCT_STAGE}) - [Untitled]")
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
        self._calibration_process: QProcess | None = None
        self._calibration_plan_path: str | None = None
        self._calibration_result_path: str | None = None
        self._calibration_output_buffer = ""
        self._calibration_active_analysis_tag: int | None = None
        self._calibration_project_snapshot: dict[str, object] | None = None
        self._calibration_stop_requested = False
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
        self._ai_focus_override: tuple[str, object] | None = None
        self._live_convergence_context: dict[str, object] = {
            "step": 0,
            "total": 0,
            "algorithm": "",
            "test": "",
            "tolerance": None,
            "enabled": False,
        }
        self._last_result: dict[str, object] = {}
        self._last_result_cache_key: object | None = None
        self._active_solution_result_tag: int | None = None
        self._results_dock_sized_once = False
        self._dirty = False
        self._measure_first_node_tag: int | None = None
        self._frame_first_node_tag: int | None = None
        self._truss_first_node_tag: int | None = None
        self._job_ui_timer = QTimer(self)
        self._job_ui_timer.setInterval(1000)
        self._job_ui_timer.timeout.connect(self._refresh_running_job_ui)

        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        self._build_central_view()
        self._build_model_tree_dock()
        self._build_properties_dock()
        self._build_create_dock()
        self._build_ai_assistant_dock()
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
        self.properties_panel.property_edited.connect(
            self._apply_direct_property_edit
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

    def _build_ai_assistant_dock(self) -> None:
        dock = QDockWidget("SARE AI Assistant", self)
        dock.setObjectName("AIAssistantDock")
        dock.setAllowedAreas(
            Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea
        )
        dock.setMinimumWidth(360)

        self.ai_assistant_panel = AIAssistantPanel(self)
        self.ai_assistant_panel.send_requested.connect(
            self._ai_assistant_send_requested
        )
        dock.setWidget(self.ai_assistant_panel)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.tabifyDockWidget(self.create_dock, dock)
        self.ai_assistant_dock = dock
        dock.hide()

    def _current_ai_focus(self) -> tuple[str, object] | None:
        if self._ai_focus_override is not None:
            return self._ai_focus_override
        item = self.tree.currentItem()
        if item is None:
            return None
        payload = item.data(0, Qt.UserRole)
        if (
            isinstance(payload, tuple)
            and len(payload) == 2
        ):
            return str(payload[0]), payload[1]
        return None

    def _show_ai_assistant(self) -> None:
        self._ai_focus_override = None
        focus = self._current_ai_focus()
        if focus is None:
            self.ai_assistant_panel.set_focus(None)
        else:
            self.ai_assistant_panel.set_focus(focus[0], focus[1])
        self.ai_assistant_dock.show()
        self.ai_assistant_dock.raise_()
        self.ai_assistant_panel.input.setFocus()

    def _ask_ai_about_tree_item(
        self,
        kind: str,
        value: object,
    ) -> None:
        self._ai_focus_override = (str(kind), value)
        self.ai_assistant_panel.set_focus(str(kind), value)
        self.ai_assistant_panel.prefill_question(
            f"Inspect this {kind} ({value}) and explain any important "
            "modeling, analysis, or solver issues you can identify."
        )
        self.ai_assistant_dock.show()
        self.ai_assistant_dock.raise_()

    def _ai_assistant_send_requested(
        self,
        prompt: str,
        raw_config: object,
    ) -> None:
        config = (
            dict(raw_config)
            if isinstance(raw_config, dict)
            else {}
        )
        try:
            include_analysis = bool(
                config.get("include_analysis", True)
            )
            project_payload = self.project.to_dict()
            if not include_analysis:
                project_payload["analyses"] = []
                project_payload["active_analysis_tag"] = None

            focus = self._current_ai_focus()
            snapshot: dict[str, object] = {
                "project": prepare_project_snapshot(project_payload),
                "focus": (
                    {
                        "kind": focus[0],
                        "value": compact_for_llm(
                            focus[1],
                            max_depth=3,
                            max_items=20,
                        ),
                    }
                    if focus is not None
                    else None
                ),
            }

            if bool(config.get("include_selection", True)):
                snapshot["selection"] = {
                    "nodes": sorted(self.selection.nodes),
                    "elements": sorted(self.selection.elements),
                }

            if bool(config.get("include_validation", True)):
                active = (
                    self.project.analyses.get(
                        self.project.active_analysis_tag
                    )
                    if include_analysis
                    else None
                )
                issues = self._model_check_issues(active)
                snapshot["validation"] = [
                    {
                        "severity": issue.severity,
                        "category": issue.category,
                        "message": issue.message,
                        "entity_kind": issue.entity_kind,
                        "entity_tag": issue.entity_tag,
                        "suggestion": issue.suggestion,
                    }
                    for issue in issues
                ]

            if bool(config.get("include_job", True)):
                job_payloads: list[dict[str, object]] = []
                for job_id in sorted(self._jobs)[-5:]:
                    job = self._jobs[job_id]
                    job_payloads.append({
                        "job_id": job.job_id,
                        "analysis_tag": job.analysis_tag,
                        "analysis_name": job.analysis_name,
                        "analysis_type": job.analysis_type,
                        "status": job.status,
                        "exit_code": job.exit_code,
                        "message": job.message,
                        "progress_current": job.progress_current,
                        "progress_total": job.progress_total,
                        "progress_percent": job.progress_percent,
                        "current_algorithm": job.current_algorithm,
                        "iterations": job.iterations,
                        "results": compact_for_llm(
                            job.results,
                            max_depth=6,
                            max_items=32,
                            max_string=8000,
                        ),
                        "plots": compact_for_llm(
                            job.plots,
                            max_depth=4,
                            max_items=24,
                        ),
                    })
                snapshot["jobs"] = job_payloads

            if bool(config.get("include_log", True)):
                console_text = self.console.toPlainText()
                snapshot["solver_log"] = console_text[-16000:]
        except BaseException as exc:
            self.ai_assistant_panel.fail_request(
                "Could not prepare SARE context: "
                f"{type(exc).__name__}: {exc}"
            )
            return

        self.ai_assistant_panel.run_request(
            str(prompt),
            config,
            snapshot,
        )

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
        self.script.setReadOnly(True)
        self.script.setToolTip(
            "Generated OpenSeesPy preview. The Project database is the source "
            "of truth; use File > Export OpenSeesPy to regenerate and verify "
            "a standalone script."
        )
        command = QPlainTextEdit()
        command.setReadOnly(True)
        command.setPlaceholderText("Interactive OpenSeesPy command console (planned)")
        script_tabs.addTab(self.script, "Generated Python")
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
        self.results_panel.set_units(self.project.units)
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
        self.results_panel.motion_frame_requested.connect(
            self._show_motion_frame_result
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
            self._clear_result_display
        )
        self.results_panel.job_selected.connect(self._select_job_result)
        self.results_panel.calibration_case_apply_requested.connect(
            self._apply_selected_calibration_case
        )
        self.results_panel.moment_curvature_hinge_requested.connect(
            self._open_hinge_backbone_from_result
        )
        self._active_result_display_kind: str | None = None
        self._syncing_result_display_controls = False
        self.results_panel.deformation_display.currentIndexChanged.connect(
            lambda _index: self._sync_result_ribbon_from_panel("deformation")
        )
        self.results_panel.deformation_scale.valueChanged.connect(
            lambda _value: self._sync_result_ribbon_from_panel("deformation")
        )
        self.results_panel.mode_display.currentIndexChanged.connect(
            lambda _index: self._sync_result_ribbon_from_panel("mode")
        )
        self.results_panel.mode_scale.valueChanged.connect(
            lambda _value: self._sync_result_ribbon_from_panel("mode")
        )
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
            "File", "Edit", "View", "Geometry", "Model", "Loads & BCs",
            "Analysis", "Results", "Tools", "Window", "Help",
        ):
            menus[name] = self.menuBar().addMenu(name)

        self._make_action("new", "New", "new", self._new_model, "New project")
        self._make_action("open", "Open", "open", self._open_project, "Open project")
        self._make_action(
            "import_py",
            "Import OpenSeesPy...",
            "open",
            self._import_openseespy_script,
            "Safely reconstruct a Studio project from an OpenSeesPy script",
        )
        self._make_action("save", "Save", "save", self._save_project, "Save project")
        self._make_action("undo", "Undo", "undo", self.undo_stack.undo, "Undo")
        self._make_action("redo", "Redo", "redo", self.undo_stack.redo, "Redo")
        self._make_action("save_as", "Save As...", "save", self._save_project_as, "Save project as")
        self._make_action("export_py", "Export OpenSeesPy...", "save", self._export_script, "Export readable OpenSeesPy script")
        self._make_action(
            "close_project",
            "Close Project",
            "delete",
            self._new_model,
            "Close the current project and return to an empty project",
        )
        self._make_action(
            "exit",
            "Exit",
            "delete",
            self.close,
            "Exit SARE",
        )

        self.actions["save"].setShortcut(QKeySequence.Save)
        self.actions["open"].setShortcut(QKeySequence.Open)
        self.actions["new"].setShortcut(QKeySequence.New)
        self.actions["undo"].setShortcut(QKeySequence.Undo)
        self.actions["redo"].setShortcut(QKeySequence.Redo)
        self.actions["exit"].setShortcut(QKeySequence("Ctrl+Q"))

        self._make_action(
            "clear_selection",
            "Clear Selection",
            "select",
            self.selection.clear,
            "Clear the current node/element selection",
        )

        self._make_action(
            "ai_assistant",
            "AI Assistant",
            "analysis",
            self._show_ai_assistant,
            "Open the read-only SARE engineering AI assistant",
        )

        self._make_action("node", "Node", "node", self._create_node, "Create node")
        self._make_action(
            "frame_pick",
            "Create by Picking",
            "element",
            self._activate_frame_pick_tool,
            "Click two nodes in the viewport to create a frame member",
            checkable=True,
        )
        self._make_action(
            "frame_input",
            "Create by Input...",
            "element",
            self._create_frame,
            "Create a frame member by entering nodes and assignments",
        )
        self._make_action(
            "truss_pick",
            "Create by Picking",
            "element",
            self._activate_truss_pick_tool,
            "Click two nodes in the viewport to create a Truss element",
            checkable=True,
        )
        self._make_action(
            "truss_input",
            "Create by Input...",
            "element",
            self._create_truss,
            "Create a Truss element by entering nodes, area, and material",
        )
        self._make_action(
            "surface_geometry",
            "Surface...",
            "grid",
            self._create_surface_geometry,
            "Create reusable Rectangle or Quad surface geometry for Shell meshing",
        )
        self._make_action(
            "shell_input",
            "Direct Shell Element...",
            "element",
            self._create_shell,
            "Create one low-level four-node OpenSees Shell element directly",
        )
        self._make_action("grid", "Grid", "grid", self._show_frame_grid, "Create frame grid")
        self._make_action(
            "column_1d",
            "1D Column",
            "element",
            self._show_test_column_wizard,
            "Quick-create a standalone column / experimental test specimen",
        )
        self._make_action(
            "frame_2d",
            "2D Frame",
            "grid",
            self._show_frame_grid_2d,
            "Quick-create a planar X-Z frame with automatic out-of-plane restraints",
        )
        self._make_action("extrude", "Extrude", "copy", self._not_implemented, "Extrude geometry")
        self.actions["extrude"].setEnabled(False)
        self.actions["extrude"].setToolTip(
            "Extrude is not implemented in the current research-alpha release"
        )

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
            "zoom_selection",
            "Zoom to Selection",
            "fit",
            self._zoom_selection,
            "Fit the selected nodes/elements in the viewport",
        )
        self._make_action(
            "measure_distance",
            "Distance",
            "ruler",
            self._activate_measure_distance,
            "Measure distance and XYZ offsets between two nodes",
            checkable=True,
        )
        self._make_action(
            "clear_measurements",
            "Clear Measurements",
            "delete",
            self._clear_measurements,
            "Remove all measurement overlays from the viewport",
        )
        self._make_action(
            "hide_selection",
            "Hide Selection",
            "display",
            self._hide_selection,
            "Hide the selected nodes/elements",
        )
        self._make_action(
            "isolate_selection",
            "Isolate Selection",
            "select",
            self._isolate_selection,
            "Show only the selected nodes/elements",
        )
        self._make_action(
            "show_all",
            "Show All",
            "display",
            self._show_all,
            "Restore all hidden model entities",
        )

        self._make_action(
            "new_material",
            "New Material...",
            "material",
            self._create_material,
            "Create OpenSees uniaxial material",
        )
        self._make_action(
            "material_library",
            "Material Library...",
            "material",
            self._show_material_library,
            "Browse verified sources and insert a material into this project",
        )
        self._make_action(
            "new_section",
            "New Section...",
            "section",
            self._create_section,
            "Create OpenSees section",
        )
        self._make_action(
            "new_shell_section",
            "New Shell Section...",
            "section",
            self._create_shell_section,
            "Create an ElasticMembranePlate shell section",
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
            "ZeroLength / Link...",
            "element",
            self._create_connection,
            "Create a research zeroLength spring/interface or twoNodeLink",
        )
        self._make_action(
            "recorder",
            "Recorder...",
            "recorder",
            self._create_recorder,
            "Create an OpenSees node, element, section, or fiber recorder",
        )
        self._make_action(
            "mass",
            "Nodal Mass...",
            "load",
            self._assign_mass,
            "Assign nodal mass manually",
        )
        self._make_action(
            "mass_source",
            "Mass Source...",
            "load",
            self._create_mass_source,
            "Generate seismic mass from self mass and selected load patterns",
        )
        self._make_action("time_series", "Time Series...", "timeseries", self._create_time_series, "Create time series")
        self._make_action("load_pattern", "Load Pattern...", "load", self._create_load_pattern, "Create a Plain load pattern")
        self._make_action(
            "ground_motion",
            "Ground Motion...",
            "timeseries",
            self._create_ground_motion,
            "Create a Path record with UniformExcitation for NLTH",
        )
        self._make_action(
            "import_ground_motion",
            "Import Ground Motion...",
            "timeseries",
            self._import_ground_motion,
            "Import AT2, JSON, TXT, CSV or DAT ground-motion data",
        )
        self._make_action("nodal_load", "Nodal Load...", "load", self._create_nodal_load, "Create nodal load")
        self._make_action(
            "prescribed_displacement",
            "Prescribed Displacement...",
            "load",
            self._create_prescribed_displacement,
            "Create an imposed nodal displacement in a Plain load pattern",
        )
        self.actions["prescribed_displacement"].setProperty(
            "ribbonText",
            "Prescr. Disp.",
        )
        self._make_action("beam_load", "Beam Load...", "load", self._create_element_load, "Create uniform, point, or self-weight beam load")
        self._make_action(
            "shell_pressure",
            "Shell Pressure...",
            "load",
            self._create_shell_pressure,
            "Create uniform pressure normal to selected shell surfaces",
        )
        self._make_action("analysis_setup", "Analysis Setup...", "analysis", self._create_analysis, "Create analysis settings")
        self._make_action(
            "analysis_template",
            "Analysis Wizard...",
            "analysis",
            lambda checked=False: self._create_analysis_template("Pushover"),
            "Guided setup that creates analysis, required loading/protocol, and default results",
        )
        self._make_action(
            "modal_template",
            "Modal",
            "analysis",
            lambda checked=False: self._create_analysis_template("Modal"),
            "Create a Modal analysis template",
        )
        self._make_action(
            "pushover_template",
            "Pushover",
            "analysis",
            lambda checked=False: self._create_analysis_template("Pushover"),
            "Create a nonlinear Pushover template",
        )
        self._make_action(
            "cyclic_template",
            "Cyclic",
            "analysis",
            lambda checked=False: self._create_analysis_template("Cyclic"),
            "Create a cyclic displacement-control template",
        )
        self._make_action(
            "nlth_template",
            "NLTH",
            "analysis",
            lambda checked=False: self._create_analysis_template(
                "Nonlinear Time History"
            ),
            "Create a nonlinear time-history earthquake template",
        )
        self._make_action("check_model", "Check Model", "analysis", self._check_model, "Validate the model before analysis")
        self._make_action("run", "Run", "run", self._toggle_analysis, "Run / stop model")
        self._make_action(
            "moment_curvature",
            "Moment-Curvature...",
            "analysis",
            lambda checked=False: self._run_moment_curvature_workflow(),
            (
                "Run an isolated zeroLengthSection section test and plot "
                "moment versus curvature without modifying the model"
            ),
        )
        self._make_action(
            "hinge_backbone",
            "Hinge Backbone...",
            "analysis",
            self._open_hinge_backbone,
            (
                "Convert researcher-identified M-theta or M-kappa backbone "
                "points into a traceable Hysteretic hinge material"
            ),
        )
        self._make_action(
            "calibration",
            "Cyclic Calibration...",
            "analysis",
            self._open_calibration,
            "Calibrate model parameters against experimental cyclic data",
        )
        self._make_action(
            "plot",
            "Plot",
            "plot",
            self._show_plot_menu,
            "Plot results from the selected or latest completed Job",
        )
        self._make_action(
            "fit_view",
            "Fit All",
            "fit",
            self._fit_view,
            "Fit the visible model/result to the viewport",
        )
        self._make_action(
            "export_results",
            "Export Active Job Results...",
            "save",
            self._export_active_job_results,
            "Export the active or latest completed Job results to JSON",
        )

        file_menu = menus["File"]
        file_menu.addActions([
            self.actions["new"],
            self.actions["open"],
            self.actions["import_py"],
        ])
        self.recent_projects_menu = file_menu.addMenu("Recent Projects")
        self.recent_projects_menu.aboutToShow.connect(
            self._refresh_recent_projects_menu
        )
        file_menu.addSeparator()
        file_menu.addActions([self.actions["save"], self.actions["save_as"]])
        file_menu.addSeparator()
        file_menu.addAction(self.actions["export_py"])
        file_menu.addSeparator()
        file_menu.addActions([
            self.actions["close_project"],
            self.actions["exit"],
        ])

        edit_menu = menus["Edit"]
        edit_menu.addActions([self.actions["undo"], self.actions["redo"]])
        edit_menu.addSeparator()
        edit_menu.addActions([
            self.actions["copy"],
            self.actions["move"],
            self.actions["rotate"],
            self.actions["mirror"],
            self.actions["delete"],
        ])
        edit_menu.addSeparator()
        edit_menu.addActions([
            self.actions["byid"],
            self.actions["bytype"],
            self.actions["clear_selection"],
        ])

        geometry_menu = menus["Geometry"]
        geometry_menu.addAction(self.actions["node"])
        frame_menu = geometry_menu.addMenu("Frame")
        frame_menu.setIcon(studio_icon("element"))
        frame_menu.addAction(self.actions["frame_pick"])
        frame_menu.addAction(self.actions["frame_input"])
        truss_menu = geometry_menu.addMenu("Truss")
        truss_menu.setIcon(studio_icon("element"))
        truss_menu.addAction(self.actions["truss_pick"])
        truss_menu.addAction(self.actions["truss_input"])
        geometry_menu.addAction(self.actions["surface_geometry"])
        geometry_menu.addSeparator()
        geometry_menu.addActions([
            self.actions["column_1d"],
            self.actions["frame_2d"],
            self.actions["grid"],
            self.actions["extrude"],
        ])
        modify_menu = geometry_menu.addMenu("Modify")
        modify_menu.addActions([
            self.actions["copy"],
            self.actions["move"],
            self.actions["rotate"],
            self.actions["mirror"],
            self.actions["delete"],
        ])

        view_menu = menus["View"]
        view_menu.addAction(self.actions["fit_view"])
        view_menu.addAction(self.actions["zoom_selection"])
        view_menu.addSeparator()
        view_menu.addActions([
            self.actions["xy"],
            self.actions["xz"],
            self.actions["yz"],
            self.actions["iso"],
        ])
        view_menu.addSeparator()
        representation_menu = view_menu.addMenu("Representation")
        for label, mode in (
            ("Tube", "tube"),
            ("Actual Section", "actual_section"),
            ("Centerline", "centerline"),
        ):
            action = representation_menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=mode: (
                    self.model_representation_combo.setCurrentIndex(
                        self.model_representation_combo.findData(value)
                    )
                )
            )
        color_menu = view_menu.addMenu("Color By")
        for label, mode in (
            ("Uniform", "uniform"),
            ("Element Type", "element_type"),
            ("Material", "material"),
            ("Section", "section"),
        ):
            action = color_menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=mode: (
                    self.model_color_combo.setCurrentIndex(
                        self.model_color_combo.findData(value)
                    )
                )
            )
        self.view_show_menu = view_menu.addMenu("Show")
        view_menu.addSeparator()
        view_menu.addActions([
            self.actions["hide_selection"],
            self.actions["isolate_selection"],
            self.actions["show_all"],
        ])

        model_menu = menus["Model"]
        model_menu.addAction(self.actions["material_library"])
        model_menu.addAction(self.actions["new_material"])
        model_menu.addAction(self.actions["new_section"])
        model_menu.addAction(self.actions["new_shell_section"])
        model_menu.addAction(self.actions["new_transformation"])
        model_menu.addSeparator()
        model_menu.addAction(self.actions["assign_section"])
        model_menu.addAction(self.actions["assign_transformation"])
        model_menu.addAction(self.actions["element_formulation"])
        model_menu.addSeparator()
        model_menu.addAction(self.actions["connection"])
        model_menu.addAction(self.actions["recorder"])

        loads_menu = menus["Loads & BCs"]
        loads_menu.addAction(self.actions["support"])
        loads_menu.addAction(self.actions["clear_support"])
        loads_menu.addAction(self.actions["constraint"])
        loads_menu.addSeparator()
        loads_menu.addAction(self.actions["mass"])
        loads_menu.addAction(self.actions["mass_source"])
        loads_menu.addSeparator()
        loads_menu.addAction(self.actions["time_series"])
        loads_menu.addAction(self.actions["load_pattern"])
        loads_menu.addAction(self.actions["ground_motion"])
        loads_menu.addAction(self.actions["import_ground_motion"])
        loads_menu.addAction(self.actions["nodal_load"])
        loads_menu.addAction(self.actions["prescribed_displacement"])
        loads_menu.addAction(self.actions["beam_load"])
        loads_menu.addAction(self.actions["shell_pressure"])

        template_menu = menus["Analysis"].addMenu("Analysis Wizard")
        template_menu.addAction(self.actions["modal_template"])
        template_menu.addAction(self.actions["pushover_template"])
        template_menu.addAction(self.actions["cyclic_template"])
        template_menu.addAction(self.actions["nlth_template"])
        menus["Analysis"].addSeparator()
        menus["Analysis"].addAction(self.actions["analysis_setup"])
        menus["Analysis"].addAction(self.actions["check_model"])
        menus["Analysis"].addSeparator()
        menus["Analysis"].addAction(self.actions["run"])
        menus["Analysis"].addSeparator()
        research_menu = menus["Analysis"].addMenu("Research Workflows")
        research_menu.addAction(self.actions["moment_curvature"])
        research_menu.addAction(self.actions["hinge_backbone"])
        research_menu.addAction(self.actions["calibration"])

        menus["Results"].addAction(self.actions["plot"])

        menus["Tools"].addAction(self.actions["ai_assistant"])
        menus["Tools"].addSeparator()
        measure_menu = menus["Tools"].addMenu("Measure")
        measure_menu.addAction(self.actions["measure_distance"])
        measure_menu.addAction(self.actions["clear_measurements"])
        menus["Tools"].addSeparator()

        units_menu = menus["Tools"].addMenu("Units")
        for index, (label, _mapping) in enumerate(UNIT_PRESETS):
            action = units_menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=index: (
                    self.unit_combo.setCurrentIndex(value)
                )
            )
        menus["Tools"].addSeparator()
        system_info_action = QAction("Runtime / System Information...", self)
        system_info_action.triggered.connect(self._show_system_info)
        menus["Tools"].addAction(system_info_action)

        menus["Window"].addAction(self.model_tree_dock.toggleViewAction())
        menus["Window"].addAction(self.properties_dock.toggleViewAction())
        menus["Window"].addAction(
            _dock_toggle_action(
                self.script_dock,
                fallback_text="Python / Command",
            )
        )
        menus["Window"].addAction(self.console_dock.toggleViewAction())
        menus["Window"].addAction(self.results_dock.toggleViewAction())
        menus["Window"].addAction(self.create_dock.toggleViewAction())
        menus["Window"].addAction(self.ai_assistant_dock.toggleViewAction())
        menus["Window"].addSeparator()
        reset_layout = QAction("Reset Dock Layout", self)
        reset_layout.triggered.connect(self._reset_dock_layout)
        menus["Window"].addAction(reset_layout)

        getting_started_action = QAction("Getting Started", self)
        getting_started_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(
                    "https://github.com/tranhan1405/openseespy-studio"
                    "#installation-from-source"
                )
            )
        )
        user_guide_action = QAction("User Guide", self)
        user_guide_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/tranhan1405/openseespy-studio")
            )
        )
        opensees_docs_action = QAction("OpenSeesPy Documentation", self)
        opensees_docs_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://openseespydoc.readthedocs.io/")
            )
        )
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_keyboard_shortcuts)
        report_issue_action = QAction("Report Issue", self)
        report_issue_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(
                    "https://github.com/tranhan1405/openseespy-studio/issues/new"
                )
            )
        )
        help_system_action = QAction("System Information", self)
        help_system_action.triggered.connect(self._show_system_info)
        about_action = QAction(f"About {PRODUCT_NAME}", self)
        about_action.triggered.connect(self._show_about)

        menus["Help"].addActions([
            getting_started_action,
            user_guide_action,
            opensees_docs_action,
            shortcuts_action,
        ])
        menus["Help"].addSeparator()
        menus["Help"].addActions([
            report_issue_action,
            help_system_action,
        ])
        menus["Help"].addSeparator()
        menus["Help"].addAction(about_action)

        self._make_action(
            "results_manager",
            "Tabular Data",
            "plot",
            self._show_results_manager,
            "Show completed Jobs and result data",
        )
        self._make_action(
            "clear_result",
            "Clear Result",
            "delete",
            self._clear_result_display,
            "Clear the active result overlay",
        )
        for key, label, mode in (
            ("result_deformed", "Deformed", "deformed_only"),
            ("result_both", "Both", "both"),
            ("result_undeformed", "Undeformed", "undeformed_only"),
        ):
            action = self._make_action(
                key,
                label,
                "plot",
                lambda checked=False, value=mode: (
                    self._set_result_display_mode(value)
                ),
                (
                    "Show only the deformed result"
                    if mode == "deformed_only"
                    else "Show undeformed and deformed shapes together"
                    if mode == "both"
                    else "Show only the undeformed model"
                ),
                checkable=True,
            )
            action.setProperty("resultDisplayMode", mode)
            action.setEnabled(False)
        self.actions["result_deformed"].setChecked(True)
        self._make_action(
            "fit_result",
            "Fit Result",
            "box",
            self._fit_active_result,
            "Fit the active result/model in the viewport",
        )
        self.actions["fit_result"].setEnabled(False)
        self._make_action(
            "solver_output_view",
            "Solver Output",
            "analysis",
            self._show_solver_output,
            "Show solver output console",
        )

        menus["Analysis"].addAction(self.actions["solver_output_view"])

        menus["Results"].addAction(self.actions["results_manager"])
        menus["Results"].addSeparator()
        result_display_menu = menus["Results"].addMenu("Result Display")
        result_display_menu.addActions([
            self.actions["result_deformed"],
            self.actions["result_both"],
            self.actions["result_undeformed"],
        ])
        menus["Results"].addAction(self.actions["fit_result"])
        menus["Results"].addAction(self.actions["clear_result"])
        menus["Results"].addSeparator()
        menus["Results"].addAction(self.actions["export_results"])

        for key, label, icon, option, tooltip in (
            (
                "show_node_numbers",
                "Node Numbers",
                "node",
                "node_numbers",
                "Show node tags in the viewport",
            ),
            (
                "show_element_numbers",
                "Element Numbers",
                "element",
                "element_numbers",
                "Show element tags in the viewport",
            ),
            (
                "show_nodal_loads",
                "Nodal Loads",
                "load",
                "nodal_loads",
                "Show applied nodal load vectors and values",
            ),
            (
                "show_element_loads",
                "Element / Surface Loads",
                "load",
                "element_loads",
                "Show applied element and shell surface load vectors",
            ),
            (
                "show_prescribed_displacements",
                "Prescr. Disp.",
                "load",
                "prescribed_displacements",
                "Show prescribed/imposed nodal displacement symbols",
            ),
            (
                "show_section_axes",
                "Section Axes",
                "transform",
                "section_axes",
                "Show local y/z section axes and strong/weak bending-axis labels",
            ),
            (
                "show_load_values",
                "Load Values",
                "plot",
                "load_values",
                "Show numeric values for visible loads and prescribed displacements",
            ),
        ):
            self._make_action(
                key,
                label,
                icon,
                lambda checked=False, name=option: (
                    self.viewport.set_display_option(name, checked)
                ),
                tooltip,
                checkable=True,
            )
        self.actions["show_load_values"].setChecked(True)

        self.view_show_menu.addActions([
            self.actions["show_node_numbers"],
            self.actions["show_element_numbers"],
            self.actions["show_nodal_loads"],
            self.actions["show_element_loads"],
            self.actions["show_prescribed_displacements"],
            self.actions["show_load_values"],
            self.actions["show_section_axes"],
        ])
        self._refresh_recent_projects_menu()

        ribbon = QToolBar("Ribbon", self)
        ribbon.setObjectName("Ribbon")
        ribbon.setMovable(False)
        ribbon.setFloatable(False)
        ribbon.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.TopToolBarArea, ribbon)

        self.ribbon_tabs = QTabWidget()
        self.ribbon_tabs.setObjectName("RibbonTabs")
        self.ribbon_tabs.tabBar().setObjectName("RibbonTabBar")
        self.ribbon_tabs.setDocumentMode(False)
        self.ribbon_tabs.setTabsClosable(False)
        self.ribbon_tabs.setMovable(False)
        self.ribbon_tabs.setMinimumHeight(105)
        self.ribbon_tabs.setMaximumHeight(112)
        self.ribbon_tabs.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        ribbon.addWidget(self.ribbon_tabs)

        def add_group(
            page: RibbonPage,
            caption: str,
            *,
            large: tuple[str, ...] = (),
            small: tuple[str, ...] = (),
            widgets: tuple[QWidget, ...] = (),
        ) -> RibbonGroup:
            group = RibbonGroup(caption)
            for key in large:
                group.add_large_action(self.actions[key])
            for key in small:
                group.add_small_action(self.actions[key])
            for widget in widgets:
                group.add_widget(widget)
            page.add_group(group)
            return group

        home = RibbonPage()
        add_group(
            home,
            "File",
            large=("new",),
            small=("open", "save", "save_as"),
        )
        add_group(
            home,
            "Edit",
            small=("undo", "redo"),
        )

        self.unit_combo = QComboBox()
        self.unit_combo.setFixedWidth(118)
        self.unit_combo.setToolTip(
            "OpenSees model unit convention. Existing numerical model "
            "values are not automatically rescaled when this is changed."
        )
        for label, mapping in UNIT_PRESETS:
            self.unit_combo.addItem(label, dict(mapping))
        self.unit_combo.currentIndexChanged.connect(
            self._change_project_units
        )
        add_group(
            home,
            "Units",
            widgets=(self.unit_combo,),
        )

        frame_button = QToolButton()
        frame_button.setObjectName("RibbonLargeButton")
        frame_button.setDefaultAction(self.actions["frame_pick"])
        frame_button.setText("Frame")
        frame_button.setIcon(self.actions["frame_pick"].icon())
        frame_button.setIconSize(QSize(28, 28))
        frame_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        frame_button.setPopupMode(QToolButton.MenuButtonPopup)
        frame_button.setAutoRaise(True)
        frame_popup = QMenu(frame_button)
        frame_popup.addAction(self.actions["frame_pick"])
        frame_popup.addAction(self.actions["frame_input"])
        frame_button.setMenu(frame_popup)

        truss_button = QToolButton()
        truss_button.setObjectName("RibbonLargeButton")
        truss_button.setDefaultAction(self.actions["truss_pick"])
        truss_button.setText("Truss")
        truss_button.setIcon(self.actions["truss_pick"].icon())
        truss_button.setIconSize(QSize(28, 28))
        truss_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        truss_button.setPopupMode(QToolButton.MenuButtonPopup)
        truss_button.setAutoRaise(True)
        truss_popup = QMenu(truss_button)
        truss_popup.addAction(self.actions["truss_pick"])
        truss_popup.addAction(self.actions["truss_input"])
        truss_button.setMenu(truss_popup)

        add_group(
            home,
            "Geometry",
            large=("frame_2d",),
            small=(
                "column_1d",
                "grid",
                "node",
                "surface_geometry",
                "extrude",
            ),
            widgets=(frame_button, truss_button),
        )
        add_group(
            home,
            "Modify",
            large=("move",),
            small=("copy", "rotate", "mirror", "delete"),
        )
        home.finish()
        self.ribbon_tabs.addTab(home, "Home")

        model_page = RibbonPage()
        add_group(
            model_page,
            "Definition",
            large=("new_section",),
            small=(
                "material_library",
                "new_material",
                "new_shell_section",
                "new_transformation",
            ),
        )
        add_group(
            model_page,
            "Assign",
            large=("assign_section",),
            small=("assign_transformation", "element_formulation"),
        )
        add_group(
            model_page,
            "Supports",
            large=("support",),
            small=("clear_support", "constraint", "connection"),
        )
        add_group(
            model_page,
            "Loads",
            large=("load_pattern",),
            small=(
                "mass",
                "mass_source",
                "time_series",
                "ground_motion",
                "nodal_load",
                "prescribed_displacement",
                "beam_load",
                "shell_pressure",
            ),
        )
        model_page.finish()
        self.ribbon_tabs.addTab(model_page, "Model")

        analysis_page = RibbonPage()
        add_group(
            analysis_page,
            "Analysis Wizard",
            large=("analysis_template",),
            small=(
                "modal_template",
                "pushover_template",
                "cyclic_template",
                "nlth_template",
            ),
        )
        add_group(
            analysis_page,
            "Solver",
            large=("run",),
            small=("analysis_setup", "check_model", "solver_output_view"),
        )
        add_group(
            analysis_page,
            "Research",
            large=("moment_curvature",),
            small=("hinge_backbone", "calibration", "ai_assistant"),
        )
        add_group(
            analysis_page,
            "Post-processing",
            large=("plot",),
            small=("results_manager",),
        )
        analysis_page.finish()
        self.ribbon_tabs.addTab(analysis_page, "Analysis")

        self.result_scale_ribbon = QDoubleSpinBox()
        self.result_scale_ribbon.setDecimals(3)
        self.result_scale_ribbon.setRange(0.01, 1.0e6)
        self.result_scale_ribbon.setValue(10.0)
        self.result_scale_ribbon.setPrefix("Scale ")
        self.result_scale_ribbon.setFixedWidth(94)
        self.result_scale_ribbon.setToolTip(
            "Display scale for the active Deformed Shape or Mode Shape"
        )
        self.result_scale_ribbon.setEnabled(False)
        self.result_scale_ribbon.editingFinished.connect(
            self._apply_result_ribbon_scale
        )

        result_page = RibbonPage()
        add_group(
            result_page,
            "Outline",
            large=("plot",),
            small=("results_manager", "clear_result"),
        )
        add_group(
            result_page,
            "Solver",
            large=("run",),
            small=("analysis_setup", "solver_output_view"),
        )
        add_group(
            result_page,
            "Result Display",
            small=(
                "result_deformed",
                "result_both",
                "result_undeformed",
            ),
            widgets=(self.result_scale_ribbon,),
        )
        add_group(
            result_page,
            "View",
            large=("fit_result",),
            small=("iso", "xy", "xz", "yz"),
        )
        result_page.finish()
        result_index = self.ribbon_tabs.addTab(result_page, "Result")
        self.ribbon_tabs.tabBar().setTabTextColor(
            result_index,
            QColor("#1768ad"),
        )

        self.model_representation_combo = QComboBox()
        self.model_representation_combo.setFixedWidth(132)
        self.model_representation_combo.addItem("Tube", "tube")
        self.model_representation_combo.addItem(
            "Actual Section",
            "actual_section",
        )
        self.model_representation_combo.addItem(
            "Centerline",
            "centerline",
        )
        self.model_representation_combo.setToolTip(
            "Model-view member representation. Tube is the lightweight "
            "default; use Actual Section to inspect real section size and "
            "orientation, or Centerline for the simplest view."
        )
        self.model_representation_combo.currentIndexChanged.connect(
            lambda _index: self.viewport.set_model_representation(
                str(self.model_representation_combo.currentData())
            )
        )

        self.model_color_combo = QComboBox()
        self.model_color_combo.setFixedWidth(132)
        self.model_color_combo.addItem("Uniform", "uniform")
        self.model_color_combo.addItem("Element Type", "element_type")
        self.model_color_combo.addItem("Material", "material")
        self.model_color_combo.addItem("Section", "section")
        self.model_color_combo.setToolTip(
            "Color the model by element formulation, assigned material, "
            "or assigned section. In Actual Section + Material mode, "
            "Fiber sections also show multi-material fiber markers."
        )
        self.model_color_combo.currentIndexChanged.connect(
            lambda _index: self.viewport.set_model_color_mode(
                str(self.model_color_combo.currentData())
            )
        )

        display_page = RibbonPage()
        add_group(
            display_page,
            "Views",
            large=("iso",),
            small=("xy", "xz", "yz"),
        )
        add_group(
            display_page,
            "Section View",
            small=("show_section_axes",),
            widgets=(
                self.model_representation_combo,
                self.model_color_combo,
            ),
        )
        add_group(
            display_page,
            "Annotations",
            small=(
                "show_node_numbers",
                "show_element_numbers",
                "show_nodal_loads",
                "show_element_loads",
                "show_prescribed_displacements",
                "show_load_values",
            ),
        )

        measure_menu_button = QToolButton()
        measure_menu_button.setObjectName("RibbonLargeButton")
        measure_menu_button.setDefaultAction(self.actions["measure_distance"])
        measure_menu_button.setText("Measure")
        measure_menu_button.setIcon(self.actions["measure_distance"].icon())
        measure_menu_button.setIconSize(QSize(28, 28))
        measure_menu_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        measure_menu_button.setPopupMode(QToolButton.MenuButtonPopup)
        measure_menu_button.setAutoRaise(True)
        measure_popup = QMenu(measure_menu_button)
        measure_popup.addAction(self.actions["measure_distance"])
        measure_popup.addAction(self.actions["clear_measurements"])
        measure_menu_button.setMenu(measure_popup)

        add_group(
            display_page,
            "Inspect",
            widgets=(measure_menu_button,),
        )
        display_page.finish()
        self.ribbon_tabs.addTab(display_page, "Display")

        self.selection_filter_combo = QComboBox()
        self.selection_filter_combo.addItems(["All", "Node", "Element"])
        self.selection_filter_combo.setFixedWidth(98)
        self.selection_filter_combo.setToolTip("Selection filter")
        self.selection_filter_combo.currentTextChanged.connect(
            self._set_selection_filter
        )
        selection_page = RibbonPage()
        add_group(
            selection_page,
            "Select",
            large=("select",),
            small=("box", "polygon"),
        )
        add_group(
            selection_page,
            "Query",
            small=("byid", "bytype"),
            widgets=(self.selection_filter_combo,),
        )
        selection_page.finish()
        self.ribbon_tabs.addTab(selection_page, "Selection")

        self._ribbon_tab_indices = {
            self.ribbon_tabs.tabText(index): index
            for index in range(self.ribbon_tabs.count())
        }

        brand = BrandWidget()
        ribbon.addWidget(brand)

    def _unit_preset_index(self) -> int:
        target = UnitSystem.from_mapping(self.project.units).as_mapping()
        combo = getattr(self, "unit_combo", None)
        if combo is None:
            return -1
        for index in range(combo.count()):
            data = combo.itemData(index)
            if isinstance(data, dict) and data == target:
                return index
        return -1

    def _sync_unit_selector(self) -> None:
        combo = getattr(self, "unit_combo", None)
        if combo is None:
            return
        index = self._unit_preset_index()
        if index < 0 or combo.currentIndex() == index:
            return
        combo.blockSignals(True)
        try:
            combo.setCurrentIndex(index)
        finally:
            combo.blockSignals(False)

    def _change_project_units(self, index: int) -> None:
        combo = getattr(self, "unit_combo", None)
        if combo is None or index < 0:
            return
        raw = combo.itemData(index)
        if not isinstance(raw, dict):
            return

        new_units = UnitSystem.from_mapping(raw).as_mapping()
        old_units = UnitSystem.from_mapping(
            self.project.units
        ).as_mapping()
        if new_units == old_units:
            return

        has_model_data = bool(
            self.model.nodes
            or self.model.elements
            or self.project.nodal_loads
            or self.project.prescribed_displacements
            or self.project.element_loads
            or self.project.sections
        )
        if has_model_data:
            answer = QMessageBox.question(
                self,
                "Change Model Units",
                (
                    "Change the OpenSees model unit convention from "
                    f"{old_units['length']} - {old_units['force']} - "
                    f"{old_units['time']} to "
                    f"{new_units['length']} - {new_units['force']} - "
                    f"{new_units['time']}?\n\n"
                    "Existing numerical geometry, section and load values "
                    "will NOT be rescaled. Their physical interpretation "
                    "will change."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self._sync_unit_selector()
                return

        before = self.project.to_dict()
        self.project.units = dict(new_units)
        self._refresh_project_metadata(
            "Model units changed to "
            f"{new_units['length']} - {new_units['force']} - "
            f"{new_units['time']}"
        )
        self._record_project_change("Change model units", before)

    def _set_result_display_controls_enabled(
        self,
        enabled: bool,
    ) -> None:
        enabled = bool(enabled)
        for key in (
            "result_deformed",
            "result_both",
            "result_undeformed",
        ):
            action = self.actions.get(key)
            if action is not None:
                action.setEnabled(enabled)
        if hasattr(self, "result_scale_ribbon"):
            self.result_scale_ribbon.setEnabled(enabled)
        fit = self.actions.get("fit_result")
        if fit is not None:
            fit.setEnabled(bool(self._last_result))

    def _sync_result_ribbon_controls(
        self,
        kind: str,
        display_mode: str,
        scale: float,
    ) -> None:
        if not hasattr(self, "result_scale_ribbon"):
            return
        self._active_result_display_kind = str(kind)
        self._set_result_display_controls_enabled(True)
        self._syncing_result_display_controls = True
        try:
            mode = str(display_mode)
            for key in (
                "result_deformed",
                "result_both",
                "result_undeformed",
            ):
                action = self.actions.get(key)
                if action is None:
                    continue
                action.setChecked(
                    str(action.property("resultDisplayMode")) == mode
                )
            self.result_scale_ribbon.setValue(float(scale))
        finally:
            self._syncing_result_display_controls = False

    def _sync_result_ribbon_from_panel(self, kind: str) -> None:
        if self._syncing_result_display_controls:
            return
        if str(kind) == "mode":
            display = str(self.results_panel.mode_display.currentData())
            scale = float(self.results_panel.mode_scale.value())
        else:
            display = str(
                self.results_panel.deformation_display.currentData()
            )
            scale = float(self.results_panel.deformation_scale.value())
        self._sync_result_ribbon_controls(kind, display, scale)

    def _set_result_display_mode(self, display_mode: str) -> None:
        if self._syncing_result_display_controls:
            return
        kind = self._active_result_display_kind
        if kind not in {"deformation", "mode"} or not self._last_result:
            self.status_message.setText(
                "Open a Deformed Shape or Mode Shape result first"
            )
            self._set_result_display_controls_enabled(False)
            return

        mode = str(display_mode)
        self._syncing_result_display_controls = True
        try:
            combo = (
                self.results_panel.mode_display
                if kind == "mode"
                else self.results_panel.deformation_display
            )
            index = combo.findData(mode)
            if index >= 0:
                combo.setCurrentIndex(index)
            for key in (
                "result_deformed",
                "result_both",
                "result_undeformed",
            ):
                action = self.actions.get(key)
                if action is not None:
                    action.setChecked(
                        str(action.property("resultDisplayMode")) == mode
                    )
        finally:
            self._syncing_result_display_controls = False

        scale = float(self.result_scale_ribbon.value())
        if kind == "mode":
            mode_number = self.results_panel.mode_combo.currentData()
            if mode_number is None:
                self.status_message.setText("No mode shape is selected")
                return
            self.results_panel.mode_scale.setValue(scale)
            self._show_mode_shape_result(
                int(mode_number),
                scale,
                mode,
                str(
                    self.results_panel.mode_representation.currentData()
                ),
                self.results_panel.mode_smooth.isChecked(),
            )
        else:
            self.results_panel.deformation_scale.setValue(scale)
            self._show_deformation_result(
                scale,
                mode,
                str(
                    self.results_panel.deformation_representation.currentData()
                ),
                self.results_panel.deformation_smooth.isChecked(),
            )

    def _apply_result_ribbon_scale(self) -> None:
        if self._syncing_result_display_controls:
            return
        kind = self._active_result_display_kind
        if kind not in {"deformation", "mode"} or not self._last_result:
            return
        checked_mode = "deformed_only"
        for key in (
            "result_deformed",
            "result_both",
            "result_undeformed",
        ):
            action = self.actions.get(key)
            if action is not None and action.isChecked():
                checked_mode = str(
                    action.property("resultDisplayMode")
                    or "deformed_only"
                )
                break
        self._set_result_display_mode(checked_mode)

    def _fit_view(self) -> None:
        self.viewport.fit_view()
        self.status_message.setText("Fit visible model/result")

    def _fit_active_result(self) -> None:
        self.viewport.fit_view()
        self.status_message.setText("Fit active result")

    def _clear_result_display(self) -> None:
        if hasattr(self, "results_panel"):
            self.results_panel.stop_motion()
        self.viewport.clear_result_overlay()
        self._active_result_display_kind = None
        self._set_result_display_controls_enabled(False)
        fit_action = self.actions.get("fit_result")
        if fit_action is not None:
            fit_action.setEnabled(bool(self._last_result))
        self.status_message.setText("Result overlay cleared")

    def _show_results_manager(self) -> None:
        self.results_panel.show_jobs()
        if not self.results_dock.isVisible():
            self.results_dock.show()
        self.results_dock.raise_()

    def _show_solver_output(self) -> None:
        self.console_dock.show()
        self.console_dock.raise_()

    def _set_ribbon_tab(self, name: str) -> None:
        tabs = getattr(self, "ribbon_tabs", None)
        indices = getattr(self, "_ribbon_tab_indices", {})
        if tabs is None:
            return
        index = indices.get(str(name))
        if index is not None and tabs.currentIndex() != index:
            tabs.setCurrentIndex(index)

    def _sync_ribbon_context(self, kinds: set[str]) -> None:
        result_kinds = {
            "jobs_root",
            "job",
            "job_plot",
            "solution_root",
            "solution_result",
            "solution_information",
            "solution_convergence",
            "solver_output",
        }
        if kinds & result_kinds:
            self._set_ribbon_tab("Result")
            return
        if kinds & {
            "analysis",
            "analysis_settings",
            "analysis_cyclic_protocol",
            "recorder",
        }:
            self._set_ribbon_tab("Analysis")

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
        self.ai_assistant_dock.hide()
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

    def _show_test_column_wizard(self) -> None:
        dialog = TestColumnWizard(
            self.project,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            spec = dialog.data()
            for material in dialog.new_materials():
                self.project.add_material(material)
            for section in dialog.new_sections():
                self.project.add_section(section)

            if spec.replace_geometry:
                self.selection.clear()
                self._reset_runtime_results()

            result = build_test_column(
                self.project,
                spec,
            )
        except (KeyError, TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(
                self,
                "Quick 1D Column",
                str(exc),
            )
            self._refresh_all()
            return

        self.model = self.project.model
        extras = []
        if result.axial_pattern_tag is not None:
            extras.append(f"axial pattern {result.axial_pattern_tag}")
        if result.lateral_pattern_tag is not None:
            extras.append(
                f"lateral pattern {result.lateral_pattern_tag}"
            )
        if result.prescribed_pattern_tag is not None:
            extras.append(
                f"prescribed-displacement pattern "
                f"{result.prescribed_pattern_tag}"
            )
        if spec.top_mass > 0.0:
            extras.append("top mass")
        if result.base_connection_tag is not None:
            extras.append(
                f"{spec.base_interface_type} "
                f"(connection {result.base_connection_tag})"
            )

        message = (
            f"Created 1D test column · {len(result.node_tags)} nodes · "
            f"{len(result.element_tags)} element(s) · "
            f"top node {result.top_node}"
        )
        if extras:
            message += " · " + ", ".join(extras)
        if result.created_transformation:
            message += (
                f" · created transformation {result.transformation_tag}"
            )

        self._refresh_all(message)
        self.selection.set_selection(nodes={result.top_node})
        self._record_project_change(
            "Create 1D test column specimen",
            before,
        )

        plane = {int(spec.axis), int(spec.lateral_direction)}
        if plane == {1, 2}:
            self.viewport.set_view("xy")
        elif plane == {1, 3}:
            self.viewport.set_view("xz")
        elif plane == {2, 3}:
            self.viewport.set_view("yz")
        else:
            self.viewport.set_view("iso")

    def _open_frame_grid(self, *, planar_2d: bool) -> None:
        self.frame_grid_panel.set_planar_2d(planar_2d)
        self.frame_grid_panel.refresh_assignments(
            self.project.sections,
            self.project.transformations,
        )
        self.create_dock.setWindowTitle(
            "Quick 2D Frame" if planar_2d else "Create Frame Grid"
        )
        self.create_dock.show()
        self.create_dock.raise_()
        if planar_2d:
            self.viewport.set_view("xz")

    def _show_frame_grid(self) -> None:
        self._open_frame_grid(planar_2d=False)

    def _show_frame_grid_2d(self) -> None:
        self._open_frame_grid(planar_2d=True)

    def _generate_frame_grid(self, spec: FrameGridSpec) -> None:
        before = self.project.to_dict()
        try:
            created_transformations = prepare_frame_grid(
                self.project,
                spec,
            )
            # Frame Grid is a replacement-geometry command.  Clear every
            # object whose meaning depends on old node/element tags before
            # generating the new model so reused IDs cannot silently rebind
            # old loads, constraints, recorders, or analyses.
            self.project.clear_model_linked_data()
            generate_frame_grid(self.model, spec)
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(self, "Create Frame Grid", str(exc))
            return

        self.selection.clear()

        if created_transformations:
            names = ", ".join(
                f"{item.name} [{item.tag}]"
                for item in created_transformations
            )
            message = (
                (
                    f"Generated 2D {spec.nx}-bay, {spec.nz}-storey frame"
                    if spec.planar_2d
                    else (
                        f"Generated {spec.nx} × {spec.ny} bay, "
                        f"{spec.nz}-storey frame"
                    )
                )
                + f" · created {names}"
            )
        else:
            message = (
                f"Generated 2D {spec.nx}-bay, {spec.nz}-storey frame"
                if spec.planar_2d
                else (
                    f"Generated {spec.nx} × {spec.ny} bay, "
                    f"{spec.nz}-storey frame"
                )
            )

        self._refresh_all(message)
        self.frame_grid_panel.set_assignment_tags(
            column_section_tag=spec.column_section_tag,
            beam_section_tag=spec.beam_section_tag,
            column_transf_tag=spec.column_transf_tag,
            beam_transf_tag=spec.beam_transf_tag,
        )
        self._record_project_change(
            "Generate 2D frame" if spec.planar_2d else "Generate frame grid",
            before,
        )
        if spec.planar_2d:
            self.viewport.set_view("xz")

    def _sync_viewport_display_data(
        self,
        *,
        refresh: bool = True,
    ) -> None:
        self.viewport.set_display_data(
            nodal_loads=self.project.nodal_loads,
            prescribed_displacements=(
                self.project.prescribed_displacements
            ),
            element_loads=self.project.element_loads,
            transformations=self.project.transformations,
            sections=self.project.sections,
            materials=self.project.materials,
            units=self.project.units,
            refresh=refresh,
        )

    def _refresh_all(self, message: str = "") -> None:
        self._sync_viewport_display_data(refresh=False)
        self.viewport.draw_model(
            self.model,
            self.project.connections,
            self.project.surfaces,
        )
        self._refresh_project_metadata(
            message,
            sync_viewport_display=False,
        )

    def _generate_project_script(self) -> str:
        """Generate a fresh standalone OpenSeesPy script from Project data."""
        return to_openseespy(
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
            prescribed_displacements=self.project.prescribed_displacements,
            recorders=self.project.recorders,
            units=self.project.units,
            solution_results=self.project.solution_results,
            nd_materials=self.project.nd_materials,
        )

    def _refresh_project_metadata(
        self,
        message: str = "",
        *,
        sync_viewport_display: bool = True,
    ) -> None:
        if sync_viewport_display:
            self._sync_viewport_display_data(refresh=True)
        self.viewport.set_model_info(
            self.model.name,
            len(self.model.nodes),
            len(self.model.elements) + len(self.project.connections),
            len(self.project.materials),
            len(self.project.sections),
            len(self.project.connections),
        )
        self.frame_grid_panel.refresh_assignments(
            self.project.sections,
            self.project.transformations,
        )
        self._refresh_tree()
        try:
            generated_script = self._generate_project_script()
        except (KeyError, TypeError, ValueError) as exc:
            generated_script = (
                f"# {PRODUCT_NAME} generation error\n"
                f"# {type(exc).__name__}: {exc}\n"
            )
            self._log(f"Script generation error: {exc}")
        self.script.setPlainText(generated_script)
        self._selection_changed(self.selection.snapshot())

        if message:
            self._log(message)
            self.status_message.setText(message)

        self.status_counts.setText(
            f"Nodes: {len(self.model.nodes)}   "
            f"Elements: {len(self.model.elements) + len(self.project.connections)}   "
            f"Connections: {len(self.project.connections)}"
        )
        units = self.project.units
        self.results_panel.set_units(units)
        unit_system = UnitSystem.from_mapping(units)
        self.status_units.setText(
            f"Units: {unit_system.length}, {unit_system.force}, "
            f"{unit_system.time} · mass {unit_system.mass_label}"
        )
        self._sync_unit_selector()

    @staticmethod
    def _tree_item_state_key(
        item: QTreeWidgetItem,
    ) -> tuple[tuple[str, str], ...]:
        """Return a stable tree identity that survives label/count changes."""
        parts: list[tuple[str, str]] = []
        current: QTreeWidgetItem | None = item
        while current is not None:
            payload = current.data(0, Qt.UserRole)
            if isinstance(payload, tuple) and len(payload) == 2:
                kind, value = payload
                parts.append((str(kind), repr(value)))
            else:
                parts.append(("text", current.text(0)))
            current = current.parent()
        parts.reverse()
        return tuple(parts)

    def _capture_tree_expansion_state(
        self,
    ) -> dict[tuple[tuple[str, str], ...], bool]:
        """Remember both expanded and collapsed branches before rebuilding."""
        state: dict[tuple[tuple[str, str], ...], bool] = {}

        def visit(item: QTreeWidgetItem) -> None:
            if item.childCount() > 0:
                state[self._tree_item_state_key(item)] = item.isExpanded()
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        return state

    def _restore_tree_expansion_state(
        self,
        state: dict[tuple[tuple[str, str], ...], bool],
    ) -> None:
        """Restore expansion only for branches that existed before refresh."""
        if not state:
            return

        def visit(item: QTreeWidgetItem) -> None:
            key = self._tree_item_state_key(item)
            if key in state:
                item.setExpanded(state[key])
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))

    def _refresh_tree(self) -> None:
        expansion_state = self._capture_tree_expansion_state()
        vertical_scroll = self.tree.verticalScrollBar().value()
        horizontal_scroll = self.tree.horizontalScrollBar().value()

        self.tree.clear()
        self._tree_node_items.clear()
        self._tree_element_items.clear()

        root = QTreeWidgetItem(["OpenSees Model"])
        root.setIcon(0, studio_icon("model"))
        root.setData(0, Qt.UserRole, ("model_root", None))
        root.setExpanded(True)

        geometry = QTreeWidgetItem(["Geometry"])
        geometry.setIcon(0, studio_icon("grid"))
        geometry.setData(0, Qt.UserRole, ("geometry_root", None))
        geometry.setExpanded(True)
        root.addChild(geometry)

        surfaces = QTreeWidgetItem([
            f"Surfaces ({len(self.project.surfaces)})"
        ])
        surfaces.setIcon(0, studio_icon("element"))
        surfaces.setData(0, Qt.UserRole, ("surfaces_root", None))
        geometry.addChild(surfaces)

        # Tree philosophy: preprocessing geometry and solver FE entities have
        # separate homes.  A Surface may own the recipe/history of a mesh,
        # but generated nodes/elements are real OpenSees entities and live
        # only under FE Model.
        fe_model = QTreeWidgetItem(["FE Model"])
        fe_model.setIcon(0, studio_icon("model"))
        fe_model.setData(0, Qt.UserRole, ("fe_model_root", None))
        fe_model.setExpanded(True)
        root.addChild(fe_model)

        nodes = QTreeWidgetItem([f"Nodes ({len(self.model.nodes)})"])
        nodes.setIcon(0, studio_icon("node"))
        nodes.setData(0, Qt.UserRole, ("nodes_root", None))
        fe_model.addChild(nodes)

        total_element_count = (
            len(self.model.elements) + len(self.project.connections)
        )
        elements = QTreeWidgetItem([
            f"Elements ({total_element_count})"
        ])
        elements.setIcon(0, studio_icon("element"))
        elements.setData(0, Qt.UserRole, ("elements_root", None))
        elements.setExpanded(True)
        fe_model.addChild(elements)

        type_counts: dict[str, int] = {}
        for element in self.model.elements.values():
            type_counts[element.element_type] = (
                type_counts.get(element.element_type, 0) + 1
            )

        # Only show element families that actually exist. Creation belongs in
        # commands/context menus, not in a forest of permanent "(0)" rows.
        type_items: dict[str, QTreeWidgetItem] = {}
        for element_type in sorted(type_counts):
            item = QTreeWidgetItem([
                f"{element_type} ({type_counts[element_type]})"
            ])
            item.setIcon(0, studio_icon("element"))
            item.setData(
                0,
                Qt.UserRole,
                ("element_type_group", element_type),
            )
            type_items[element_type] = item
            elements.addChild(item)

        for tag in sorted(self.model.nodes):
            item = QTreeWidgetItem([f"Node {tag}"])
            item.setIcon(0, studio_icon("node"))
            item.setData(0, Qt.UserRole, ("node", tag))
            nodes.addChild(item)
            self._tree_node_items[tag] = item

        for tag in sorted(self.project.surfaces):
            surface = self.project.surfaces[tag]
            live_elements = [
                int(element_tag)
                for element_tag in surface.generated_element_tags
                if int(element_tag) in self.model.elements
            ]
            mesh_nodes = sorted({
                int(node_tag)
                for element_tag in live_elements
                for node_tag in self.model.elements[element_tag].node_tags()
            })
            if live_elements:
                status = (
                    f"{surface.divisions_u}×{surface.divisions_v} · "
                    f"{len(live_elements)} shells"
                )
            else:
                status = "Unmeshed"
            item = QTreeWidgetItem([
                f"Surface {tag} · {surface.name} [{status}]"
            ])
            item.setIcon(0, studio_icon("grid"))
            item.setData(
                0,
                Qt.UserRole,
                ("surface_geometry", tag),
            )
            surfaces.addChild(item)

            if live_elements:
                mesh_summary = QTreeWidgetItem([
                    f"Mesh ({len(mesh_nodes)} nodes · "
                    f"{len(live_elements)} elements)"
                ])
                mesh_summary.setIcon(0, studio_icon("grid"))
                mesh_summary.setData(
                    0,
                    Qt.UserRole,
                    ("surface_mesh", tag),
                )
                item.addChild(mesh_summary)

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
        named_sets.setData(0, Qt.UserRole, ("named_sets_root", None))
        named_sets.setExpanded(True)
        fe_model.addChild(named_sets)

        for name in sorted(self.project.selection_sets):
            selection_set = self.project.selection_sets[name]
            item = QTreeWidgetItem([
                f"{name}  ({len(selection_set.node_tags)}N / "
                f"{len(selection_set.element_tags)}E)"
            ])
            item.setIcon(0, studio_icon("select"))
            item.setData(0, Qt.UserRole, ("set", name))
            named_sets.addChild(item)

        properties_root = QTreeWidgetItem(["Properties"])
        properties_root.setIcon(0, studio_icon("material"))
        properties_root.setData(
            0,
            Qt.UserRole,
            ("properties_root", None),
        )
        properties_root.setExpanded(True)
        root.addChild(properties_root)

        materials_root = QTreeWidgetItem([
            f"Materials ({len(self.project.materials)})"
        ])
        materials_root.setIcon(0, studio_icon("material"))
        materials_root.setData(0, Qt.UserRole, ("materials_root", None))
        materials_root.setExpanded(True)
        properties_root.addChild(materials_root)

        for tag in sorted(self.project.materials):
            material = self.project.materials[tag]
            item = QTreeWidgetItem([
                f"{material.material_type} [{tag}]  {material.name}"
            ])
            item.setIcon(0, studio_icon("material"))
            item.setData(0, Qt.UserRole, ("material", tag))
            materials_root.addChild(item)

        nd_materials_root = QTreeWidgetItem([
            f"nD Materials ({len(self.project.nd_materials)})"
        ])
        nd_materials_root.setIcon(0, studio_icon("material"))
        nd_materials_root.setData(
            0,
            Qt.UserRole,
            ("nd_materials_root", None),
        )
        nd_materials_root.setExpanded(True)
        properties_root.addChild(nd_materials_root)

        for tag in sorted(self.project.nd_materials):
            material = self.project.nd_materials[tag]
            item = QTreeWidgetItem([
                f"{material.material_type} [{tag}]  {material.name}"
            ])
            item.setIcon(0, studio_icon("material"))
            item.setData(0, Qt.UserRole, ("nd_material", tag))
            nd_materials_root.addChild(item)

        sections_root = QTreeWidgetItem([
            f"Sections ({len(self.project.sections)})"
        ])
        sections_root.setIcon(0, studio_icon("section"))
        sections_root.setData(0, Qt.UserRole, ("sections_root", None))
        sections_root.setExpanded(True)
        properties_root.addChild(sections_root)

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
        properties_root.addChild(transformations_root)

        for tag in sorted(self.project.transformations):
            transformation = self.project.transformations[tag]
            item = QTreeWidgetItem([
                f"{transformation.transformation_type} [{tag}]  "
                f"{transformation.name}"
            ])
            item.setIcon(0, studio_icon("transform"))
            item.setData(0, Qt.UserRole, ("transformation", tag))
            transformations_root.addChild(item)

        loads_bc_root = QTreeWidgetItem(["Loads & BCs"])
        loads_bc_root.setIcon(0, studio_icon("load"))
        loads_bc_root.setData(
            0,
            Qt.UserRole,
            ("loads_bc_root", None),
        )
        loads_bc_root.setExpanded(True)
        root.addChild(loads_bc_root)

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
        loads_bc_root.addChild(boundary_root)

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
            group_item.setData(
                0,
                Qt.UserRole,
                ("boundary_group", support_type),
            )
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
        loads_bc_root.addChild(constraints_root)

        for tag in sorted(self.project.constraints):
            constraint = self.project.constraints[tag]
            item = QTreeWidgetItem([
                f"{constraint.constraint_type} [{tag}]  {constraint.name}"
            ])
            item.setIcon(0, studio_icon("transform"))
            item.setData(0, Qt.UserRole, ("constraint", tag))
            constraints_root.addChild(item)

        # OpenSees zeroLength/twoNodeLink/zeroLengthSection objects are
        # elements even though SARE keeps their editor-specific metadata in
        # ProjectDatabase.connections. Show them under Elements so imported
        # OpenSees models preserve the source model semantics.
        connection_groups: dict[str, QTreeWidgetItem] = {}
        for connection_type in SUPPORTED_CONNECTION_TYPES:
            tags = [
                tag
                for tag, connection in self.project.connections.items()
                if connection.connection_type == connection_type
            ]
            if not tags:
                continue
            group = QTreeWidgetItem([
                f"{connection_type} ({len(tags)})"
            ])
            group.setIcon(0, studio_icon("element"))
            group.setData(
                0,
                Qt.UserRole,
                ("connection_group", connection_type),
            )
            group.setExpanded(True)
            elements.addChild(group)
            connection_groups[connection_type] = group

        for tag in sorted(self.project.connections):
            connection = self.project.connections[tag]
            item = QTreeWidgetItem([
                f"Element {tag} · {connection.name}"
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
        loads_bc_root.addChild(masses_root)
        for tag in sorted(mass_nodes):
            item = QTreeWidgetItem([f"Node {tag}"])
            item.setIcon(0, studio_icon("load"))
            item.setData(0, Qt.UserRole, ("node", tag))
            masses_root.addChild(item)

        mass_sources_root = QTreeWidgetItem([
            f"Mass Sources ({len(self.project.mass_sources)})"
        ])
        mass_sources_root.setIcon(0, studio_icon("load"))
        mass_sources_root.setData(
            0,
            Qt.UserRole,
            ("mass_sources_root", None),
        )
        mass_sources_root.setExpanded(True)
        loads_bc_root.addChild(mass_sources_root)
        for tag in sorted(self.project.mass_sources):
            source = self.project.mass_sources[tag]
            item = QTreeWidgetItem([
                f"{source.name} [{tag}]"
            ])
            item.setIcon(0, studio_icon("load"))
            item.setData(0, Qt.UserRole, ("mass_source", tag))
            mass_sources_root.addChild(item)

        loading_root = QTreeWidgetItem(["Loading"])
        loading_root.setIcon(0, studio_icon("load"))
        loading_root.setData(0, Qt.UserRole, ("loading_root", None))
        loading_root.setExpanded(True)
        loads_bc_root.addChild(loading_root)

        ground_motion_patterns = {
            tag: pattern
            for tag, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "UniformExcitation"
        }
        ground_motion_series_tags = {
            pattern.time_series_tag
            for pattern in ground_motion_patterns.values()
        }
        standalone_series = {
            tag: series
            for tag, series in self.project.time_series.items()
            if tag not in ground_motion_series_tags
        }
        plain_patterns = {
            tag: pattern
            for tag, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }

        series_root = QTreeWidgetItem([
            f"Time Series ({len(standalone_series)})"
        ])
        series_root.setIcon(0, studio_icon("timeseries"))
        series_root.setData(0, Qt.UserRole, ("time_series_root", None))
        series_root.setExpanded(True)
        loading_root.addChild(series_root)
        for tag in sorted(standalone_series):
            series = standalone_series[tag]
            item = QTreeWidgetItem([
                f"{series.series_type} [{tag}]  {series.name}"
            ])
            item.setIcon(0, studio_icon("timeseries"))
            item.setData(0, Qt.UserRole, ("time_series", tag))
            series_root.addChild(item)

        patterns_root = QTreeWidgetItem([
            f"Load Patterns ({len(plain_patterns)})"
        ])
        patterns_root.setIcon(0, studio_icon("load"))
        patterns_root.setData(0, Qt.UserRole, ("load_patterns_root", None))
        patterns_root.setExpanded(True)
        loading_root.addChild(patterns_root)
        for tag in sorted(plain_patterns):
            pattern = plain_patterns[tag]
            item = QTreeWidgetItem([
                f"Plain [{tag}]  {pattern.name}"
            ])
            item.setIcon(0, studio_icon("load"))
            item.setData(0, Qt.UserRole, ("load_pattern", tag))
            item.setExpanded(True)
            patterns_root.addChild(item)
            for load_tag in sorted(self.project.nodal_loads):
                load = self.project.nodal_loads[load_tag]
                if load.pattern_tag != tag:
                    continue
                load_item = QTreeWidgetItem([
                    f"{load.name} [{load.tag}] → Node {load.node_tag}"
                ])
                load_item.setIcon(0, studio_icon("load"))
                load_item.setData(
                    0,
                    Qt.UserRole,
                    ("nodal_load", load.tag),
                )
                item.addChild(load_item)
            for displacement_tag in sorted(
                self.project.prescribed_displacements
            ):
                displacement = self.project.prescribed_displacements[
                    displacement_tag
                ]
                if displacement.pattern_tag != tag:
                    continue
                dof_label = ("UX", "UY", "UZ", "RX", "RY", "RZ")[
                    displacement.dof - 1
                ]
                displacement_item = QTreeWidgetItem([
                    f"Prescribed {dof_label}: {displacement.name} "
                    f"[{displacement.tag}] → Node {displacement.node_tag}"
                ])
                displacement_item.setIcon(0, studio_icon("load"))
                displacement_item.setData(
                    0,
                    Qt.UserRole,
                    ("prescribed_displacement", displacement.tag),
                )
                item.addChild(displacement_item)
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

        ground_motions_root = QTreeWidgetItem([
            f"Ground Motions ({len(ground_motion_patterns)})"
        ])
        ground_motions_root.setIcon(0, studio_icon("timeseries"))
        ground_motions_root.setData(
            0,
            Qt.UserRole,
            ("ground_motions_root", None),
        )
        ground_motions_root.setExpanded(True)
        loading_root.addChild(ground_motions_root)
        axis_name = {1: "X", 2: "Y", 3: "Z"}
        for tag in sorted(ground_motion_patterns):
            pattern = ground_motion_patterns[tag]
            series = self.project.time_series.get(
                pattern.time_series_tag
            )
            axis = axis_name.get(
                pattern.direction,
                f"DOF {pattern.direction}",
            )
            points = (
                len(series.values)
                if series is not None and series.series_type == "Path"
                else 0
            )
            item = QTreeWidgetItem([
                f"{pattern.name} [{tag}] · {axis} · {points} pts"
            ])
            item.setIcon(0, studio_icon("timeseries"))
            item.setData(0, Qt.UserRole, ("ground_motion", tag))
            ground_motions_root.addChild(item)

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

            if settings.analysis_type == "Cyclic":
                targets = list(settings.cyclic_targets)
                protocol_item = QTreeWidgetItem([
                    f"Cyclic Protocol ({len(targets)} targets)"
                ])
                protocol_item.setIcon(0, studio_icon("timeseries"))
                protocol_item.setData(
                    0,
                    Qt.UserRole,
                    ("analysis_cyclic_protocol", tag),
                )
                item.addChild(protocol_item)

            solution_results = self.project.solution_results_for_analysis(tag)
            solution = QTreeWidgetItem([
                f"Result Requests ({len(solution_results)})"
            ])
            solution.setIcon(0, studio_icon("results"))
            solution.setData(0, Qt.UserRole, ("solution_root", tag))
            solution.setExpanded(True)
            item.addChild(solution)

            information = QTreeWidgetItem(["Analysis Information"])
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

        # Rebuilding the tree is common after edits/imports. Preserve the
        # user's navigation context instead of reopening default branches.
        self._restore_tree_expansion_state(expansion_state)
        self.tree.verticalScrollBar().setValue(vertical_scroll)
        self.tree.horizontalScrollBar().setValue(horizontal_scroll)

    def _tree_selection_changed(self) -> None:
        nodes: set[int] = set()
        elements: set[int] = set()
        surface_geometry_tag: int | None = None
        material_tag: int | None = None
        nd_material_tag: int | None = None
        section_tag: int | None = None
        transformation_tag: int | None = None
        constraint_tag: int | None = None
        connection_tag: int | None = None
        time_series_tag: int | None = None
        load_pattern_tag: int | None = None
        ground_motion_tag: int | None = None
        nodal_load_tag: int | None = None
        prescribed_displacement_tag: int | None = None
        element_load_tag: int | None = None
        mass_source_tag: int | None = None
        analysis_tag: int | None = None
        cyclic_protocol_tag: int | None = None
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
            elif kind in {
                "surface_geometry",
                "surface_mesh",
                "surface_shells",
            }:
                surface_geometry_tag = int(tag)
                surface = self.project.surfaces.get(int(tag))
                if surface is not None:
                    elements.update(
                        int(element_tag)
                        for element_tag in surface.generated_element_tags
                        if int(element_tag) in self.model.elements
                    )
            elif kind == "material":
                material_tag = int(tag)
            elif kind == "nd_material":
                nd_material_tag = int(tag)
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
            elif kind == "ground_motion":
                ground_motion_tag = int(tag)
            elif kind == "nodal_load":
                nodal_load_tag = int(tag)
            elif kind == "prescribed_displacement":
                prescribed_displacement_tag = int(tag)
            elif kind == "element_load":
                element_load_tag = int(tag)
            elif kind == "mass_source":
                mass_source_tag = int(tag)
            elif kind == "analysis":
                analysis_tag = int(tag)
            elif kind == "analysis_settings":
                analysis_tag = int(tag)
            elif kind == "analysis_cyclic_protocol":
                cyclic_protocol_tag = int(tag)
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

        self._sync_ribbon_context(selected_payload_kinds)

        if (
            solution_result_tag is None
            and "solution_root" not in selected_payload_kinds
            and "solution_information" not in selected_payload_kinds
            and "solution_convergence" not in selected_payload_kinds
            and "solver_output" not in selected_payload_kinds
        ):
            self._active_solution_result_tag = None

        # Result objects restore their own saved scope below.  Do not clear
        # and then immediately re-apply that selection, because each change
        # rebuilds VTK highlight actors and forces an extra render.
        result_restores_scope = (
            solution_result_tag is not None
            or job_plot_ref is not None
        )
        if not result_restores_scope:
            self.selection.set_selection(
                nodes=nodes,
                elements=elements,
            )

        if surface_geometry_tag is not None:
            self._show_surface_geometry_properties(surface_geometry_tag)
        elif material_tag is not None:
            self._show_material_properties(material_tag)
        elif nd_material_tag is not None:
            self._show_nd_material_properties(nd_material_tag)
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
        elif ground_motion_tag is not None:
            self._show_ground_motion_properties(ground_motion_tag)
        elif nodal_load_tag is not None:
            self._show_nodal_load_properties(nodal_load_tag)
        elif prescribed_displacement_tag is not None:
            self._show_prescribed_displacement_properties(
                prescribed_displacement_tag
            )
        elif element_load_tag is not None:
            self._show_element_load_properties(element_load_tag)
        elif mass_source_tag is not None:
            self._show_mass_source_properties(mass_source_tag)
        elif cyclic_protocol_tag is not None:
            self._show_cyclic_protocol_properties(cyclic_protocol_tag)
        elif analysis_tag is not None:
            self._show_analysis_properties(analysis_tag)
        elif recorder_tag is not None:
            self._show_recorder_properties(recorder_tag)
        elif solution_result_tag is not None:
            self._show_solution_result_properties(solution_result_tag)
            self._evaluate_solution_result(solution_result_tag)
        elif solution_convergence_tag is not None:
            analysis = self.project.analyses.get(
                solution_convergence_tag
            )
            convergence_name = convergence_result_label(
                analysis.test if analysis is not None else None
            )
            self._show_solution_information(
                solution_convergence_tag,
                convergence_name,
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
                "Analysis Information",
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
            ("Escape", self._cancel_current_tool),
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

    def _leave_measure_mode(self) -> None:
        self._measure_first_node_tag = None
        self.viewport.clear_measure_anchor(render=False)
        action = self.actions.get("measure_distance")
        if action is not None:
            action.setChecked(False)
        self.viewport.set_selection_filter(self.selection.filter)

    def _leave_frame_pick_mode(self) -> None:
        self._frame_first_node_tag = None
        self.viewport.clear_frame_anchor(render=False)
        action = self.actions.get("frame_pick")
        if action is not None:
            action.setChecked(False)
        self.viewport.set_selection_filter(self.selection.filter)

    def _leave_truss_pick_mode(self) -> None:
        self._truss_first_node_tag = None
        self.viewport.clear_truss_anchor(render=False)
        action = self.actions.get("truss_pick")
        if action is not None:
            action.setChecked(False)
        self.viewport.set_selection_filter(self.selection.filter)

    def _activate_select_tool(self) -> None:
        self._leave_measure_mode()
        self._leave_frame_pick_mode()
        self._leave_truss_pick_mode()
        self.viewport.set_interaction_tool("select")
        self.actions["select"].setChecked(True)
        self.actions["box"].setChecked(False)
        self.viewport.plotter.render()
        self.status_message.setText("Select tool active")

    def _activate_box_tool(self) -> None:
        self._leave_measure_mode()
        self._leave_frame_pick_mode()
        self._leave_truss_pick_mode()
        self.viewport.set_interaction_tool("box")
        self.actions["select"].setChecked(False)
        self.actions["box"].setChecked(True)
        self.viewport.plotter.render()
        self.status_message.setText(
            "Box select: left→right = window, right→left = crossing"
        )

    def _activate_frame_pick_tool(self, checked: bool = True) -> None:
        action = self.actions.get("frame_pick")
        if action is not None and not action.isChecked() and not checked:
            self._activate_select_tool()
            return
        if len(self.model.nodes) < 2:
            if action is not None:
                action.setChecked(False)
            if not self._ensure_node_count(
                2,
                title="Create Frame",
            ):
                return
        if not self._ensure_prerequisite(
            title="Create Frame",
            message=(
                "Quick Frame creation requires at least one Elastic Section. "
                "Create a Section now?"
            ),
            action_label="Create Section Now...",
            available=lambda: any(
                section.section_type == "Elastic"
                for section in self.project.sections.values()
            ),
            creator=self._create_section,
        ):
            return
        if not self._ensure_prerequisite(
            title="Create Frame",
            message=(
                "Quick Frame creation requires a Geometric Transformation. "
                "Create one now?"
            ),
            action_label="Create Transformation Now...",
            available=lambda: bool(self.project.transformations),
            creator=self._create_transformation,
        ):
            return

        self._leave_measure_mode()
        self._leave_truss_pick_mode()
        self._frame_first_node_tag = None
        self.viewport.clear_frame_anchor(render=False)
        self.viewport.set_interaction_tool("select")
        self.viewport.set_selection_filter("node")
        self.actions["select"].setChecked(False)
        self.actions["box"].setChecked(False)
        if action is not None:
            action.setChecked(True)
        self.viewport.plotter.render()
        self.status_message.setText(
            "Create Frame: click the first node"
        )

    def _activate_truss_pick_tool(self, checked: bool = True) -> None:
        action = self.actions.get("truss_pick")
        if action is not None and not action.isChecked() and not checked:
            self._activate_select_tool()
            return
        if len(self.model.nodes) < 2:
            if action is not None:
                action.setChecked(False)
            if not self._ensure_node_count(
                2,
                title="Create Truss",
            ):
                return
        if not self.project.materials:
            if action is not None:
                action.setChecked(False)
            if not self._ensure_prerequisite(
                title="Create Truss",
                message=(
                    "A Truss requires a uniaxial Material. "
                    "Create the Material now?"
                ),
                action_label="Create Material Now...",
                available=lambda: bool(self.project.materials),
                creator=self._create_material,
            ):
                return

        self._leave_measure_mode()
        self._leave_frame_pick_mode()
        self._truss_first_node_tag = None
        self.viewport.clear_truss_anchor(render=False)
        self.viewport.set_interaction_tool("select")
        self.viewport.set_selection_filter("node")
        self.actions["select"].setChecked(False)
        self.actions["box"].setChecked(False)
        if action is not None:
            action.setChecked(True)
        self.viewport.plotter.render()
        self.status_message.setText(
            "Create Truss: click the first node"
        )

    def _activate_measure_distance(self, checked: bool = True) -> None:
        action = self.actions.get("measure_distance")
        if action is not None and not action.isChecked() and not checked:
            self._activate_select_tool()
            return
        if len(self.model.nodes) < 2:
            if action is not None:
                action.setChecked(False)
            if not self._ensure_node_count(
                2,
                title="Measure Distance",
            ):
                return

        self._leave_frame_pick_mode()
        self._leave_truss_pick_mode()
        self._measure_first_node_tag = None
        self.viewport.clear_measure_anchor(render=False)
        self.viewport.set_interaction_tool("select")
        self.viewport.set_selection_filter("node")
        self.actions["select"].setChecked(False)
        self.actions["box"].setChecked(False)
        if action is not None:
            action.setChecked(True)
        self.viewport.plotter.render()
        self.status_message.setText(
            "Measure Distance: click the first node"
        )

    def _clear_measurements(self) -> None:
        self._measure_first_node_tag = None
        self.viewport.clear_measurements()
        if (
            self.actions.get("measure_distance") is not None
            and self.actions["measure_distance"].isChecked()
        ):
            self.status_message.setText(
                "Measurements cleared · click the first node"
            )
        else:
            self.status_message.setText("Measurements cleared")

    def _cancel_current_tool(self) -> None:
        if (
            self.actions.get("measure_distance") is not None
            and self.actions["measure_distance"].isChecked()
        ):
            self._activate_select_tool()
            return
        if (
            self.actions.get("frame_pick") is not None
            and self.actions["frame_pick"].isChecked()
        ):
            self._activate_select_tool()
            return
        if (
            self.actions.get("truss_pick") is not None
            and self.actions["truss_pick"].isChecked()
        ):
            self._activate_select_tool()
            return
        if self.viewport.interaction_tool() == "box":
            self._activate_select_tool()
            return
        self.selection.clear()

    def _set_selection_filter(self, text: str) -> None:
        value = text.lower()
        self.selection.set_filter(value)
        measure_action = self.actions.get("measure_distance")
        frame_pick_action = self.actions.get("frame_pick")
        truss_pick_action = self.actions.get("truss_pick")
        if measure_action is not None and measure_action.isChecked():
            self.viewport.set_selection_filter("node")
            self.status_message.setText(
                f"Selection filter saved as {text}; "
                "Measure Distance temporarily snaps to nodes"
            )
            return
        if frame_pick_action is not None and frame_pick_action.isChecked():
            self.viewport.set_selection_filter("node")
            self.status_message.setText(
                f"Selection filter saved as {text}; "
                "Create Frame temporarily snaps to nodes"
            )
            return
        if truss_pick_action is not None and truss_pick_action.isChecked():
            self.viewport.set_selection_filter("node")
            self.status_message.setText(
                f"Selection filter saved as {text}; "
                "Create Truss temporarily snaps to nodes"
            )
            return
        self.viewport.set_selection_filter(value)
        self.status_message.setText(f"Selection filter: {text}")

    def _viewport_entity_clicked(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        kind = payload.get("kind")
        tag = payload.get("tag")
        mode = payload.get("mode", "replace")

        truss_pick_action = self.actions.get("truss_pick")
        if truss_pick_action is not None and truss_pick_action.isChecked():
            if kind != "node" or tag is None:
                self.status_message.setText(
                    "Create Truss: click a model node"
                )
                return

            node_tag = int(tag)
            if self._truss_first_node_tag is None:
                self._truss_first_node_tag = node_tag
                self.viewport.show_truss_anchor(node_tag)
                self.status_message.setText(
                    f"Create Truss: node {node_tag} selected · "
                    "click the second node"
                )
                return

            if node_tag == self._truss_first_node_tag:
                self.status_message.setText(
                    "Create Truss: choose a different second node"
                )
                return

            first_tag = self._truss_first_node_tag
            self._truss_first_node_tag = None
            self.viewport.clear_truss_anchor(render=False)
            self._create_truss_between_nodes(first_tag, node_tag)
            if truss_pick_action.isChecked():
                self.status_message.setText(
                    f"Created Truss {first_tag} → {node_tag} · "
                    "click another first node"
                )
            return

        frame_pick_action = self.actions.get("frame_pick")
        if frame_pick_action is not None and frame_pick_action.isChecked():
            if kind != "node" or tag is None:
                self.status_message.setText(
                    "Create Frame: click a model node"
                )
                return

            node_tag = int(tag)
            if self._frame_first_node_tag is None:
                self._frame_first_node_tag = node_tag
                self.viewport.show_frame_anchor(node_tag)
                self.status_message.setText(
                    f"Create Frame: node {node_tag} selected · "
                    "click the second node"
                )
                return

            if node_tag == self._frame_first_node_tag:
                self.status_message.setText(
                    "Create Frame: choose a different second node"
                )
                return

            first_tag = self._frame_first_node_tag
            self._frame_first_node_tag = None
            self.viewport.clear_frame_anchor(render=False)
            self._create_frame_between_nodes(first_tag, node_tag)
            if frame_pick_action.isChecked():
                self.status_message.setText(
                    f"Created frame {first_tag} → {node_tag} · "
                    "click another first node"
                )
            return

        measure_action = self.actions.get("measure_distance")
        if measure_action is not None and measure_action.isChecked():
            if kind != "node" or tag is None:
                self.status_message.setText(
                    "Measure Distance: click a model node"
                )
                return

            node_tag = int(tag)
            if self._measure_first_node_tag is None:
                self._measure_first_node_tag = node_tag
                self.viewport.show_measure_anchor(node_tag)
                self.status_message.setText(
                    f"Measure Distance: node {node_tag} selected · "
                    "click the second node"
                )
                return

            if node_tag == self._measure_first_node_tag:
                self.status_message.setText(
                    "Measure Distance: choose a different second node"
                )
                return

            first_tag = self._measure_first_node_tag
            try:
                measurement = self.viewport.add_distance_measurement(
                    first_tag,
                    node_tag,
                )
            except ValueError as exc:
                self.status_message.setText(str(exc))
                return

            self._measure_first_node_tag = None
            unit = str(self.project.units.get("length", "")).strip()
            suffix = f" {unit}" if unit else ""
            self.status_message.setText(
                f"Measured node {first_tag} → {node_tag}: "
                f"L={measurement['distance']:.4g}{suffix}, "
                f"ΔX={measurement['dx']:.4g}, "
                f"ΔY={measurement['dy']:.4g}, "
                f"ΔZ={measurement['dz']:.4g} · "
                "click another first node"
            )
            return

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

    def _apply_direct_property_edit(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        context = payload.get("context")
        if not isinstance(context, dict):
            return
        kind = str(context.get("kind", ""))
        try:
            tag = int(context.get("tag"))
        except (TypeError, ValueError):
            return
        property_id = str(payload.get("id", ""))
        value = payload.get("value")
        if not property_id:
            return

        before = self.project.to_dict()
        try:
            if kind == "node":
                node = self.model.nodes.get(tag)
                if node is None:
                    return

                managed_by = sorted(
                    connection.tag
                    for connection in self.project.connections.values()
                    if connection.generated_ground_node == tag
                )
                if (
                    managed_by
                    and (
                        property_id in {"x", "y", "z", "mass"}
                        or property_id.startswith("fixity_")
                    )
                ):
                    raise ValueError(
                        "Generated ground node "
                        f"{tag} is managed by connection(s) "
                        + ", ".join(map(str, managed_by))
                        + "; edit the structural/source node or connection "
                        "instead."
                    )

                if property_id in {"x", "y", "z"}:
                    axis = {"x": 0, "y": 1, "z": 2}[property_id]
                    xyz = list(node.xyz)
                    xyz[axis] = float(value)
                    self.model.set_coordinates(tag, *xyz)
                    self.project.sync_generated_ground_nodes()
                    self.project.validate_node_state(tag)
                elif property_id.startswith("fixity_"):
                    index = int(property_id.rsplit("_", 1)[1])
                    values = list(node.fixity)
                    values[index] = 1 if int(value) else 0
                    node.fixity = tuple(values)
                    self.project.validate_node_state(tag)
                elif property_id == "mass":
                    text = str(value).replace(";", ",")
                    parts = [
                        part.strip()
                        for chunk in text.split(",")
                        for part in chunk.split()
                        if part.strip()
                    ]
                    masses = tuple(float(part) for part in parts)
                    if len(masses) != self.model.ndf:
                        raise ValueError(
                            f"Mass requires {self.model.ndf} values."
                        )
                    self.model.set_mass(tag, masses)
                else:
                    return

            elif kind == "element":
                element = self.model.elements.get(tag)
                if element is None:
                    return

                if element.element_type in SHELL_ELEMENT_TYPES:
                    shell_direct_fields = {
                        "group",
                        "section_tag",
                        "shell_corotational",
                        "shell_local_x",
                        "shell_no_eas",
                        "shell_drilling_stab",
                        "shell_drilling_nl",
                    }
                    if property_id not in shell_direct_fields:
                        raise ValueError(
                            "Edit shell topology and formulation through "
                            "'Edit Shell Definition...'."
                        )

                if property_id == "shell_corotational":
                    element.shell_corotational = (
                        value
                        if isinstance(value, bool)
                        else str(value).strip().lower()
                        in {"1", "true", "yes", "on", "corotational"}
                    )
                elif property_id == "shell_no_eas":
                    element.shell_no_eas = (
                        value
                        if isinstance(value, bool)
                        else str(value).strip().lower()
                        in {"1", "true", "yes", "on", "disabled", "noeas"}
                    )
                elif property_id == "shell_drilling_nl":
                    element.shell_drilling_nl = (
                        value
                        if isinstance(value, bool)
                        else str(value).strip().lower()
                        in {"1", "true", "yes", "on", "enabled"}
                    )
                elif property_id == "shell_drilling_stab":
                    text = str(value).strip().lower()
                    element.shell_drilling_stab = (
                        None
                        if text in {"", "default", "auto", "none"}
                        else float(text)
                    )
                elif property_id == "shell_local_x":
                    text = str(value).strip()
                    if text.lower() in {"", "auto", "default", "none"}:
                        element.shell_local_x = None
                    else:
                        parts = [
                            part.strip()
                            for chunk in text.replace(";", ",").split(",")
                            for part in chunk.split()
                            if part.strip()
                        ]
                        if len(parts) != 3:
                            raise ValueError(
                                "Shell local X requires three values or 'auto'."
                            )
                        element.shell_local_x = tuple(
                            float(part) for part in parts
                        )
                elif property_id == "element_type":
                    new_type = str(value)
                    if new_type not in {
                        "elasticBeamColumn",
                        "forceBeamColumn",
                        "dispBeamColumn",
                    }:
                        raise ValueError(
                            f"Unsupported frame formulation: {new_type}"
                        )
                    element.element_type = new_type
                    if new_type == "elasticBeamColumn":
                        section = self.project.sections.get(
                            element.section_tag
                        )
                        if (
                            section is not None
                            and section.section_type != "Elastic"
                        ):
                            element.section_tag = None
                elif property_id == "group":
                    element.group = str(value).strip() or "frame"
                elif property_id == "section_tag":
                    section_tag = None if value is None else int(value)
                    if section_tag is not None:
                        section = self.project.sections.get(section_tag)
                        if section is None:
                            raise ValueError(
                                f"Section {section_tag} does not exist."
                            )
                        if (
                            element.element_type == "elasticBeamColumn"
                            and section.section_type != "Elastic"
                        ):
                            raise ValueError(
                                "elasticBeamColumn requires an Elastic section."
                            )
                        if (
                            element.element_type in SHELL_ELEMENT_TYPES
                            and section.section_type not in SHELL_SECTION_TYPES
                        ):
                            raise ValueError(
                                "Shell elements require a shell-compatible "
                                "section."
                            )
                    element.section_tag = section_tag
                elif property_id == "transf_tag":
                    transf_tag = None if value is None else int(value)
                    if (
                        transf_tag is not None
                        and transf_tag not in self.project.transformations
                    ):
                        raise ValueError(
                            f"Transformation {transf_tag} does not exist."
                        )
                    element.transf_tag = transf_tag
                elif property_id == "integration_type":
                    element.integration_type = str(value)
                elif property_id == "integration_points":
                    element.integration_points = int(str(value).strip())
                elif property_id == "force_max_iter":
                    element.force_max_iter = int(str(value).strip())
                elif property_id == "force_tolerance":
                    element.force_tolerance = float(str(value).strip())
                elif property_id == "mass_per_length":
                    element.mass_per_length = float(str(value).strip())
                elif property_id == "consistent_mass":
                    if isinstance(value, bool):
                        element.consistent_mass = value
                    else:
                        element.consistent_mass = (
                            str(value).strip().lower()
                            in {"1", "true", "yes", "consistent"}
                        )
                elif property_id == "truss_area":
                    element.truss_area = float(str(value).strip())
                elif property_id == "truss_material_tag":
                    material_tag = None if value is None else int(value)
                    if (
                        material_tag is not None
                        and material_tag not in self.project.materials
                    ):
                        raise ValueError(
                            f"Material {material_tag} does not exist."
                        )
                    element.truss_material_tag = material_tag
                elif property_id == "truss_do_rayleigh":
                    if isinstance(value, bool):
                        element.truss_do_rayleigh = value
                    else:
                        element.truss_do_rayleigh = (
                            str(value).strip().lower()
                            in {"1", "true", "yes", "on"}
                        )
                else:
                    return

                # Re-run Element's own checks plus dependent recorder/load
                # validation after an in-place Details-pane edit.
                element.__post_init__()
                self.project.validate_element_state(tag)

            elif kind == "material":
                material = self.project.materials.get(tag)
                if material is None:
                    return
                data = material.to_dict()
                if property_id == "name":
                    data["name"] = str(value).strip()
                elif property_id == "poisson_ratio":
                    data["poisson_ratio"] = float(str(value).strip())
                elif property_id == "density":
                    unit_system = UnitSystem.from_mapping(
                        self.project.units
                    )
                    data["density"] = (
                        unit_system.engineering_density_to_kg_per_m3(
                            float(str(value).strip())
                        )
                    )
                elif property_id.startswith("parameter:"):
                    parameter = property_id.split(":", 1)[1]
                    if parameter not in material.parameters:
                        raise ValueError(
                            f"Material parameter {parameter!r} does not exist."
                        )
                    raw_value = float(str(value).strip())
                    unit_system = UnitSystem.from_mapping(
                        self.project.units
                    )
                    parameter_kind = material_parameter_kind(
                        material,
                        parameter,
                    )
                    if parameter_kind == "stress":
                        raw_value = (
                            unit_system.engineering_stress_to_pa(
                                raw_value
                            )
                        )
                    elif parameter_kind == "length":
                        raw_value = unit_system.length_to_m_value(
                            raw_value
                        )
                    elif parameter_kind == "force":
                        raw_value = unit_system.force_to_n_value(
                            raw_value
                        )
                    elif parameter_kind == "moment":
                        raw_value = unit_system.moment_to_nm_value(
                            raw_value
                        )
                    parameters = dict(data["parameters"])
                    parameters[parameter] = raw_value
                    data["parameters"] = parameters
                    source = dict(data.get("source", {}))
                    if (
                        source
                        and parameter
                        in {
                            str(key)
                            for key in source.get(
                                "verified_parameters",
                                [],
                            )
                        }
                    ):
                        source["status"] = "modified_from_verified"
                        source["modified"] = True
                        data["source"] = source
                else:
                    return
                updated = MaterialData.from_dict(data)
                self.project.update_material(tag, updated)

            elif kind == "section":
                section = self.project.sections.get(tag)
                if section is None:
                    return
                data = section.to_dict()
                if property_id == "name":
                    data["name"] = str(value).strip()
                elif property_id == "material_tag":
                    data["material_tag"] = (
                        None if value is None else int(value)
                    )
                elif property_id.startswith("parameter:"):
                    parameter = property_id.split(":", 1)[1]
                    if parameter not in section.parameters:
                        raise ValueError(
                            f"Section parameter {parameter!r} does not exist."
                        )
                    raw_value = float(str(value).strip())
                    if parameter in {"E", "G"}:
                        raw_value = UnitSystem.from_mapping(
                            self.project.units
                        ).engineering_stress_to_pa(raw_value)
                    parameters = dict(data["parameters"])
                    parameters[parameter] = raw_value
                    data["parameters"] = parameters
                else:
                    return
                updated = SectionData.from_dict(data)
                self.project.update_section(tag, updated)

            elif kind == "transformation":
                transformation = self.project.transformations.get(tag)
                if transformation is None:
                    return
                name = transformation.name
                transformation_type = transformation.transformation_type
                vecxz = list(transformation.vecxz)
                if property_id == "name":
                    name = str(value).strip()
                elif property_id == "transformation_type":
                    transformation_type = str(value)
                elif property_id.startswith("vecxz_"):
                    index = {"vecxz_x": 0, "vecxz_y": 1, "vecxz_z": 2}[
                        property_id
                    ]
                    vecxz[index] = float(str(value).strip())
                else:
                    return
                updated = TransformationData(
                    tag=tag,
                    name=name,
                    transformation_type=transformation_type,
                    vecxz=tuple(vecxz),
                )
                self.project.update_transformation(tag, updated)

            else:
                return

        except (TypeError, ValueError, IndexError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(
                self,
                "Invalid Property Value",
                str(exc),
            )
            return

        self._refresh_all(
            f"Updated {kind} {tag}: {property_id}"
        )
        self._record_project_change(
            f"Edit {kind} {tag} property {property_id}",
            before,
        )

    def _show_entity_properties(self, kind: str, tag: int) -> None:
        if kind == "node":
            node = self.model.nodes.get(tag)
            if node is None:
                return
            connected = [
                element.tag
                for element in self.model.elements.values()
                if tag in element.node_tags()
            ]
            managed_ground_connections = sorted(
                connection.tag
                for connection in self.project.connections.values()
                if connection.generated_ground_node == tag
            )
            node_fields_editable = not managed_ground_connections
            unit_system = UnitSystem.from_mapping(self.project.units)
            dof_labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")[:self.model.ndf]
            rows = [
                ("Tag", tag),
                (
                    f"Coordinates [{unit_system.length}]",
                    ", ".join(f"{value:g}" for value in node.xyz),
                ),
                ("X", f"{node.xyz[0]:g}", {
                    "id": "x", "editable": node_fields_editable, "kind": "float",
                }),
                ("Y", f"{node.xyz[1]:g}", {
                    "id": "y", "editable": node_fields_editable, "kind": "float",
                }),
                ("Z", f"{node.xyz[2]:g}", {
                    "id": "z", "editable": node_fields_editable, "kind": "float",
                }),
                ("Support", classify_fixity(node.fixity)),
                ("Fixity", node.fixity),
            ]
            for index, label in enumerate(dof_labels):
                rows.append((
                    label,
                    "Fixed" if node.fixity[index] else "Free",
                    {
                        "id": f"fixity_{index}",
                        "editable": node_fields_editable,
                        "kind": "choice",
                        "current": int(node.fixity[index]),
                        "choices": [("Free", 0), ("Fixed", 1)],
                    },
                ))
            rows.extend([
                (
                    "Mass",
                    ", ".join(f"{value:g}" for value in node.mass),
                    {
                        "id": "mass",
                        "editable": node_fields_editable,
                        "kind": "text",
                    },
                ),
                (
                    "Managed ground",
                    (
                        "Connection(s) "
                        + ", ".join(map(str, managed_ground_connections))
                        if managed_ground_connections
                        else "No"
                    ),
                ),
                ("Connected", ", ".join(map(str, connected)) or "-"),
            ])
            self.properties_panel.set_properties(
                "Node",
                rows,
                context={"kind": "node", "tag": int(tag)},
            )
            return

        if kind == "element":
            element = self.model.elements.get(tag)
            if element is None:
                return

            if element.element_type in SHELL_ELEMENT_TYPES:
                section_text = "Unassigned"
                if element.section_tag is not None:
                    section = self.project.sections.get(
                        int(element.section_tag)
                    )
                    section_text = (
                        f"{element.section_tag} - {section.name}"
                        if section is not None
                        else f"{element.section_tag} (missing)"
                    )
                shell_section_choices = []
                for section_tag in sorted(self.project.sections):
                    candidate = self.project.sections[section_tag]
                    if candidate.section_type not in SHELL_SECTION_TYPES:
                        continue
                    shell_section_choices.append((
                        f"{section_tag} - {candidate.name} "
                        f"({candidate.section_type})",
                        int(section_tag),
                    ))
                is_asd_shell = element.element_type == "ASDShellQ4"
                self.properties_panel.set_properties(
                    "Shell Element",
                    [
                        ("Tag", tag),
                        ("Type", element.element_type),
                        (
                            "Nodes",
                            ", ".join(
                                map(str, element.node_tags())
                            ),
                        ),
                        ("Topology", "4-node quadrilateral surface"),
                        (
                            "Section",
                            section_text,
                            {
                                "id": "section_tag",
                                "editable": True,
                                "kind": "choice",
                                "current": element.section_tag,
                                "choices": shell_section_choices,
                            },
                        ),
                        (
                            "Kinematics",
                            (
                                "Corotational"
                                if element.shell_corotational
                                else "Small displacement"
                            ),
                            {
                                "id": "shell_corotational",
                                "editable": is_asd_shell,
                                "kind": "choice",
                                "current": bool(element.shell_corotational),
                                "choices": [
                                    ("Small displacement", False),
                                    ("Corotational", True),
                                ],
                            },
                        ),
                        (
                            "Local X axis",
                            (
                                ", ".join(
                                    f"{value:g}"
                                    for value in element.shell_local_x
                                )
                                if element.shell_local_x is not None
                                else "auto"
                            ),
                            {
                                "id": "shell_local_x",
                                "editable": is_asd_shell,
                                "kind": "text",
                            },
                        ),
                        (
                            "Enhanced assumed strain",
                            (
                                "Disabled (-noeas)"
                                if element.shell_no_eas
                                else "Enabled"
                            ),
                            {
                                "id": "shell_no_eas",
                                "editable": is_asd_shell,
                                "kind": "choice",
                                "current": bool(element.shell_no_eas),
                                "choices": [
                                    ("Enabled", False),
                                    ("Disabled (-noeas)", True),
                                ],
                            },
                        ),
                        (
                            "Drilling stabilization",
                            (
                                f"{element.shell_drilling_stab:g}"
                                if element.shell_drilling_stab is not None
                                else "default"
                            ),
                            {
                                "id": "shell_drilling_stab",
                                "editable": is_asd_shell,
                                "kind": "text",
                            },
                        ),
                        (
                            "Nonlinear drilling",
                            (
                                "Enabled (-drillingNL)"
                                if element.shell_drilling_nl
                                else "Disabled"
                            ),
                            {
                                "id": "shell_drilling_nl",
                                "editable": is_asd_shell,
                                "kind": "choice",
                                "current": bool(element.shell_drilling_nl),
                                "choices": [
                                    ("Disabled", False),
                                    ("Enabled (-drillingNL)", True),
                                ],
                            },
                        ),
                        ("Transformation", "Not used by Shell"),
                        ("Beam integration", "Not used by Shell"),
                        (
                            "Group",
                            element.group,
                            {
                                "id": "group",
                                "editable": True,
                                "kind": "text",
                            },
                        ),
                        (
                            "Edit",
                            "Right-click element → Edit Shell Definition...",
                        ),
                    ],
                    context={"kind": "element", "tag": int(tag)},
                )
                return

            if element.element_type == "truss":
                material_text = "Unassigned"
                if element.truss_material_tag is not None:
                    material = self.project.materials.get(
                        element.truss_material_tag
                    )
                    material_text = (
                        f"{element.truss_material_tag} - {material.name}"
                        if material is not None
                        else f"{element.truss_material_tag} (missing)"
                    )
                material_choices = [("Unassigned", None)]
                material_choices.extend(
                    (
                        f"{material_tag} - {material.name} "
                        f"({material.material_type})",
                        int(material_tag),
                    )
                    for material_tag, material in sorted(
                        self.project.materials.items()
                    )
                )
                self.properties_panel.set_properties(
                    "Truss Element",
                    [
                        ("Tag", tag),
                        ("Type", "truss"),
                        ("Nodes", f"{element.i}, {element.j}"),
                        (
                            "Group",
                            element.group,
                            {
                                "id": "group",
                                "editable": True,
                                "kind": "text",
                            },
                        ),
                        (
                            "Area",
                            f"{element.truss_area:g}",
                            {
                                "id": "truss_area",
                                "editable": True,
                                "kind": "float",
                            },
                        ),
                        (
                            "Material",
                            material_text,
                            {
                                "id": "truss_material_tag",
                                "editable": True,
                                "kind": "choice",
                                "current": element.truss_material_tag,
                                "choices": material_choices,
                            },
                        ),
                        ("Section", "Not used by Truss"),
                        ("Transformation", "Not used by Truss"),
                        (
                            "Mass / length (rho)",
                            f"{element.mass_per_length:g}",
                            {
                                "id": "mass_per_length",
                                "editable": True,
                                "kind": "float",
                            },
                        ),
                        (
                            "Mass matrix",
                            (
                                "Consistent"
                                if element.consistent_mass
                                else "Lumped"
                            ),
                            {
                                "id": "consistent_mass",
                                "editable": True,
                                "kind": "choice",
                                "current": bool(element.consistent_mass),
                                "choices": [
                                    ("Lumped", False),
                                    ("Consistent", True),
                                ],
                            },
                        ),
                        (
                            "Rayleigh damping",
                            (
                                "On"
                                if element.truss_do_rayleigh
                                else "Off"
                            ),
                            {
                                "id": "truss_do_rayleigh",
                                "editable": True,
                                "kind": "choice",
                                "current": bool(
                                    element.truss_do_rayleigh
                                ),
                                "choices": [
                                    ("Off", False),
                                    ("On", True),
                                ],
                            },
                        ),
                    ],
                    context={"kind": "element", "tag": int(tag)},
                )
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

            section_choices = [("Unassigned", None)]
            for section_tag in sorted(self.project.sections):
                section = self.project.sections[section_tag]
                if (
                    element.element_type == "elasticBeamColumn"
                    and section.section_type != "Elastic"
                ):
                    continue
                section_choices.append((
                    f"{section_tag} - {section.name} ({section.section_type})",
                    int(section_tag),
                ))

            transformation_choices = [("Unassigned", None)]
            transformation_choices.extend(
                (
                    f"{transf_tag} - {transformation.name} "
                    f"({transformation.transformation_type})",
                    int(transf_tag),
                )
                for transf_tag, transformation in sorted(
                    self.project.transformations.items()
                )
            )

            nonlinear = element.element_type in {
                "forceBeamColumn", "dispBeamColumn"
            }
            force_based = element.element_type == "forceBeamColumn"
            rows = [
                ("Tag", tag),
                (
                    "Type",
                    element.element_type,
                    {
                        "id": "element_type",
                        "editable": True,
                        "kind": "choice",
                        "current": element.element_type,
                        "choices": [
                            ("elasticBeamColumn", "elasticBeamColumn"),
                            ("forceBeamColumn", "forceBeamColumn"),
                            ("dispBeamColumn", "dispBeamColumn"),
                        ],
                    },
                ),
                ("Nodes", f"{element.i}, {element.j}"),
                (
                    "Group",
                    element.group,
                    {
                        "id": "group",
                        "editable": True,
                        "kind": "text",
                    },
                ),
                (
                    "Section",
                    section_text,
                    {
                        "id": "section_tag",
                        "editable": True,
                        "kind": "choice",
                        "current": element.section_tag,
                        "choices": section_choices,
                    },
                ),
                (
                    "Transformation",
                    transformation_text,
                    {
                        "id": "transf_tag",
                        "editable": True,
                        "kind": "choice",
                        "current": element.transf_tag,
                        "choices": transformation_choices,
                    },
                ),
            ]
            if nonlinear:
                rows.extend([
                    (
                        "Integration",
                        element.integration_type,
                        {
                            "id": "integration_type",
                            "editable": True,
                            "kind": "choice",
                            "current": element.integration_type,
                            "choices": [
                                ("Lobatto", "Lobatto"),
                                ("Legendre", "Legendre"),
                                ("Radau", "Radau"),
                            ],
                        },
                    ),
                    (
                        "Integration points",
                        element.integration_points,
                        {
                            "id": "integration_points",
                            "editable": True,
                            "kind": "int",
                        },
                    ),
                ])
            else:
                rows.extend([
                    ("Integration", "-"),
                    ("Integration points", "-"),
                ])

            if force_based:
                rows.extend([
                    (
                        "Force max iterations",
                        element.force_max_iter,
                        {
                            "id": "force_max_iter",
                            "editable": True,
                            "kind": "int",
                        },
                    ),
                    (
                        "Force tolerance",
                        f"{element.force_tolerance:g}",
                        {
                            "id": "force_tolerance",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                ])
            else:
                rows.extend([
                    ("Force max iterations", "-"),
                    ("Force tolerance", "-"),
                ])

            rows.extend([
                (
                    "Mass / length",
                    f"{element.mass_per_length:g}",
                    {
                        "id": "mass_per_length",
                        "editable": True,
                        "kind": "float",
                    },
                ),
                (
                    "Mass matrix",
                    "Consistent" if element.consistent_mass else "Lumped",
                    {
                        "id": "consistent_mass",
                        "editable": True,
                        "kind": "choice",
                        "current": bool(element.consistent_mass),
                        "choices": [
                            ("Lumped", False),
                            ("Consistent", True),
                        ],
                    },
                ),
            ])
            self.properties_panel.set_properties(
                "Frame / Element",
                rows,
                context={"kind": "element", "tag": int(tag)},
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
        apply_support = support_menu.addAction("Apply / Edit...")
        apply_support.triggered.connect(self._apply_restraint)
        clear_support = support_menu.addAction("Clear")
        clear_support.setEnabled(bool(self.selection.nodes))
        clear_support.triggered.connect(self._clear_restraint)

        constraint_action = menu.addAction("Create Constraint...")
        constraint_action.triggered.connect(self._create_constraint)

        connection_action = menu.addAction("Create ZeroLength / Link...")
        connection_action.triggered.connect(self._create_connection)

        mass_action = menu.addAction("Assign Mass...")
        mass_action.triggered.connect(self._assign_mass)
        load_action = menu.addAction("Create Nodal Load...")
        load_action.triggered.connect(self._create_nodal_load)
        displacement_action = menu.addAction(
            "Create Prescribed Displacement..."
        )
        displacement_action.triggered.connect(
            self._create_prescribed_displacement
        )
        selected_elements = [
            self.model.elements[element_tag]
            for element_tag in self.selection.elements
            if element_tag in self.model.elements
        ]
        has_truss = any(
            element.element_type == "truss"
            for element in selected_elements
        )
        has_frame = any(
            element.element_type in FRAME_ELEMENT_TYPES
            for element in selected_elements
        )
        has_shell = any(
            element.element_type in SHELL_ELEMENT_TYPES
            for element in selected_elements
        )

        beam_load_action = menu.addAction("Create Beam Load...")
        beam_load_action.setEnabled(has_frame)
        beam_load_action.triggered.connect(self._create_element_load)
        shell_pressure_action = menu.addAction(
            "Create Surface Pressure..."
        )
        shell_pressure_action.setEnabled(has_shell)
        shell_pressure_action.triggered.connect(
            self._create_shell_pressure
        )
        formulation_action = menu.addAction(
            "Element Formulation..."
        )
        formulation_action.triggered.connect(
            self._set_element_formulation
        )

        menu.addSeparator()
        assign_menu = menu.addMenu("Assign")
        assign_material = assign_menu.addAction("Material (Truss)...")
        assign_material.triggered.connect(
            self._assign_truss_material_to_selection
        )
        assign_section = assign_menu.addAction("Section...")
        assign_section.triggered.connect(self._assign_section_to_selection)
        assign_transformation = assign_menu.addAction("Transformation...")
        assign_transformation.triggered.connect(
            self._assign_transformation_to_selection
        )
        assign_menu.addSeparator()
        clear_material = assign_menu.addAction("Clear Material (Truss)")
        clear_material.setEnabled(has_truss)
        clear_material.triggered.connect(
            self._clear_truss_material_assignment
        )
        clear_section = assign_menu.addAction("Clear Section")
        clear_section.setEnabled(has_frame)
        clear_section.triggered.connect(self._clear_section_assignment)
        clear_transformation = assign_menu.addAction("Clear Transformation")
        clear_transformation.setEnabled(has_frame)
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
        reverse_shell_action = menu.addAction("Reverse Shell Normal")
        reverse_shell_action.setEnabled(has_shell)
        reverse_shell_action.triggered.connect(
            self._reverse_selected_shell_normals
        )
        stitch_shell_action = menu.addAction(
            "Stitch Coincident Shell Nodes..."
        )
        stitch_shell_action.setEnabled(has_shell)
        stitch_shell_action.triggered.connect(
            self._stitch_coincident_shell_nodes
        )

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

    def _ask_create_prerequisite(
        self,
        *,
        title: str,
        message: str,
        action_label: str,
    ) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(str(title))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(str(message))
        create_button = box.addButton(
            str(action_label),
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is create_button

    def _ensure_prerequisite(
        self,
        *,
        title: str,
        message: str,
        action_label: str,
        available,
        creator,
    ) -> bool:
        if bool(available()):
            return True
        if not self._ask_create_prerequisite(
            title=title,
            message=message,
            action_label=action_label,
        ):
            return False
        creator()
        return bool(available())

    def _ensure_node_count(
        self,
        minimum: int,
        *,
        title: str,
    ) -> bool:
        required = max(1, int(minimum))
        while len(self.model.nodes) < required:
            current = len(self.model.nodes)
            if not self._ask_create_prerequisite(
                title=title,
                message=(
                    f"This workflow requires at least {required} node"
                    f"{'s' if required != 1 else ''}. "
                    f"The model currently has {current}.\n\n"
                    "Create the missing node now?"
                ),
                action_label="Create Node Now...",
            ):
                return False
            before = len(self.model.nodes)
            self._create_node()
            if len(self.model.nodes) <= before:
                return False
        return True

    def _plain_load_patterns(self) -> dict[int, LoadPatternData]:
        return {
            tag: pattern
            for tag, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }

    def _ensure_plain_load_pattern(self, *, title: str) -> bool:
        return self._ensure_prerequisite(
            title=title,
            message=(
                "This workflow requires a Plain load pattern first. "
                "Create it now? If no Time Series exists, SARE will offer "
                "to create that prerequisite too."
            ),
            action_label="Create Plain Load Pattern Now...",
            available=lambda: bool(self._plain_load_patterns()),
            creator=self._create_load_pattern,
        )

    def _selected_node_tags(
        self,
        title: str,
        *,
        create_if_missing: bool = False,
    ) -> set[int] | None:
        tags = set(self.selection.nodes)
        if tags:
            return tags
        if create_if_missing and not self.model.nodes:
            if not self._ensure_node_count(1, title=title):
                return None
            tags = set(self.selection.nodes)
            if tags:
                return tags
        QMessageBox.information(
            self,
            title,
            "Select at least one node first.",
        )
        return None

    def _exclude_managed_ground_nodes(
        self,
        node_tags: set[int],
        *,
        title: str,
    ) -> set[int]:
        managed = {
            int(connection.generated_ground_node)
            for connection in self.project.connections.values()
            if connection.generated_ground_node is not None
        }
        editable = set(node_tags) - managed
        skipped = set(node_tags) & managed
        if skipped:
            self.status_message.setText(
                f"{title}: skipped {len(skipped)} managed ground node(s)"
            )
        if not editable and skipped:
            QMessageBox.information(
                self,
                title,
                "Selected node(s) are generated ground nodes managed by "
                "connections. Edit the structural/source node instead.",
            )
        return editable

    def _apply_restraint(self) -> None:
        node_tags = self._selected_node_tags(
            "Support / Restraint",
            create_if_missing=True,
        )
        if node_tags is None:
            return
        node_tags = self._exclude_managed_ground_nodes(
            node_tags,
            title="Support / Restraint",
        )
        if not node_tags:
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
        conflicts = []
        for displacement in self.project.prescribed_displacements.values():
            if displacement.node_tag not in node_tags:
                continue
            dof_index = displacement.dof - 1
            if (
                0 <= dof_index < len(fixity)
                and bool(fixity[dof_index])
            ):
                conflicts.append(
                    f"Node {displacement.node_tag} "
                    f"{('UX','UY','UZ','RX','RY','RZ')[dof_index]}"
                )
        if conflicts:
            QMessageBox.warning(
                self,
                "Support / Restraint",
                "Cannot restrain DOF(s) that already have a prescribed "
                "displacement:\n" + ", ".join(conflicts),
            )
            return

        before = self.project.to_dict()
        updated = self.model.set_fixity_many(node_tags, fixity)
        try:
            for node_tag in sorted(updated):
                self.project.validate_node_state(node_tag)
        except (TypeError, ValueError, IndexError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(self, "Support / Restraint", str(exc))
            return
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
        node_tags = self._exclude_managed_ground_nodes(
            node_tags,
            title="Clear Support",
        )
        if not node_tags:
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
        node_tags = self._selected_node_tags(
            "Nodal Mass",
            create_if_missing=True,
        )
        if node_tags is None:
            return
        node_tags = self._exclude_managed_ground_nodes(
            node_tags,
            title="Nodal Mass",
        )
        if not node_tags:
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
            return None
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

    def _create_mass_source(self) -> None:
        if not self._offer_structural_model_creator():
            return
        dialog = MassSourceDialog(
            self.project,
            next_tag=self.project.next_mass_source_tag(),
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            source = dialog.data()
            self.project.add_mass_source(source)
            summary = apply_mass_source(self.project, source)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Mass Source", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(
            f"Created mass source {source.tag}; "
            f"generated mass {summary.total_mass:.6g}"
        )
        self._record_project_change(
            f"Create mass source {source.tag}",
            before,
        )
        self._refresh_tree()
        self._show_mass_source_properties(source.tag)

    def _edit_mass_source(self, tag: int) -> None:
        source = self.project.mass_sources.get(int(tag))
        if source is None:
            return
        dialog = MassSourceDialog(
            self.project,
            source=source,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_mass_source(tag, updated)
            summary = apply_mass_source(self.project, updated)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Mass Source", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(
            f"Updated mass source {updated.tag}; "
            f"generated mass {summary.total_mass:.6g}"
        )
        self._record_project_change(
            f"Edit mass source {tag}",
            before,
        )
        self._refresh_tree()
        self._show_mass_source_properties(updated.tag)

    def _apply_mass_source(self, tag: int) -> None:
        source = self.project.mass_sources.get(int(tag))
        if source is None:
            return
        before = self.project.to_dict()
        try:
            summary = apply_mass_source(self.project, source)
        except ValueError as exc:
            QMessageBox.warning(self, "Mass Source", str(exc))
            return
        self._refresh_project_metadata(
            f"Applied mass source {tag}; "
            f"generated mass {summary.total_mass:.6g}"
        )
        self._record_project_change(
            f"Apply mass source {tag}",
            before,
        )
        self._refresh_tree()
        self._show_mass_source_properties(tag)

    def _delete_mass_source(self, tag: int) -> None:
        source = self.project.mass_sources.get(int(tag))
        if source is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Mass Source",
            (
                f"Delete mass source '{source.name}'?\n\n"
                "Current nodal mass values will be kept. They can be cleared "
                "manually or replaced by another Mass Source."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        before = self.project.to_dict()
        self.project.remove_mass_source(tag)
        self._refresh_project_metadata(f"Deleted mass source {tag}")
        self._record_project_change(
            f"Delete mass source {tag}",
            before,
        )

    def _show_mass_source_properties(self, tag: int) -> None:
        source = self.project.mass_sources.get(int(tag))
        if source is None:
            return
        try:
            summary = evaluate_mass_source(self.project, source)
            unit = UnitSystem.from_mapping(self.project.units).mass_label
            total = f"{summary.total_mass:.6g} {unit}"
            self_mass = f"{summary.self_mass:.6g} {unit}"
            load_mass = f"{summary.load_mass:.6g} {unit}"
        except ValueError as exc:
            total = self_mass = load_mass = f"Error: {exc}"
        patterns = ", ".join(
            f"{pattern_tag}×{factor:g}"
            for pattern_tag, factor in sorted(source.load_factors.items())
        ) or "-"
        dofs = ", ".join(
            ("UX", "UY", "UZ")[dof - 1]
            for dof in source.directions
        )
        axis = ("X", "Y", "Z")[source.gravity_axis - 1]
        self.properties_panel.set_properties(
            "Mass Source",
            [
                ("Tag", source.tag),
                ("Name", source.name),
                ("Self mass", "Yes" if source.include_self_mass else "No"),
                ("Load patterns", patterns),
                ("Gravity axis", axis),
                ("Mass directions", dofs),
                ("Generated total", total),
                ("From self mass", self_mass),
                ("From loads", load_mass),
                (
                    "Regeneration",
                    "Replaces selected translational nodal mass components",
                ),
            ],
        )

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
        if not self._ensure_prerequisite(
            title="Load Pattern",
            message=(
                "A Load Pattern requires a Time Series. "
                "Create a Time Series now?"
            ),
            action_label="Create Time Series Now...",
            available=lambda: bool(self.project.time_series),
            creator=self._create_time_series,
        ):
            return
        dialog = LoadPatternDialog(
            self.project.time_series,
            next_tag=self.project.next_load_pattern_tag(),
            allow_uniform_excitation=False,
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
            self.project.time_series,
            pattern=pattern,
            allow_uniform_excitation=False,
            parent=self,
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
                "Prescribed Displacements",
                sum(
                    displacement.pattern_tag == tag
                    for displacement in (
                        self.project.prescribed_displacements.values()
                    )
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

    def _ground_motion_pair(
        self,
        pattern_tag: int,
    ) -> tuple[TimeSeriesData, LoadPatternData] | None:
        pattern = self.project.load_patterns.get(int(pattern_tag))
        if (
            pattern is None
            or pattern.pattern_type != "UniformExcitation"
        ):
            return None
        series = self.project.time_series.get(pattern.time_series_tag)
        if series is None or series.series_type != "Path":
            return None
        return series, pattern

    def _create_ground_motion(self) -> None:
        self._create_ground_motion_from_source("builtin")

    def _import_ground_motion(self) -> None:
        self._create_ground_motion_from_source("file")

    def _create_ground_motion_from_source(
        self,
        source_mode: str,
    ) -> None:
        dialog = GroundMotionDialog(
            next_series_tag=self.project.next_time_series_tag(),
            next_pattern_tag=self.project.next_load_pattern_tag(),
            units=self.project.units,
            initial_source=str(source_mode),
            parent=self,
        )
        if str(source_mode) == "file":
            dialog._browse_file()
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            series, pattern = dialog.data()
            if series.tag in self.project.time_series:
                raise ValueError(
                    f"Time series tag {series.tag} already exists."
                )
            if pattern.tag in self.project.load_patterns:
                raise ValueError(
                    f"Load pattern tag {pattern.tag} already exists."
                )
            self.project.add_time_series(series)
            try:
                self.project.add_load_pattern(pattern)
            except Exception:
                self.project.time_series.pop(series.tag, None)
                raise
        except ValueError as exc:
            QMessageBox.warning(self, "Ground Motion Editor", str(exc))
            return
        self._refresh_project_metadata(
            f"Created ground motion {pattern.tag}: {pattern.name}"
        )
        self._show_ground_motion_properties(pattern.tag)
        self._record_project_change(
            f"Create ground motion {pattern.tag}",
            before,
        )

    def _edit_ground_motion(self, pattern_tag: int) -> None:
        pair = self._ground_motion_pair(pattern_tag)
        if pair is None:
            pattern = self.project.load_patterns.get(int(pattern_tag))
            if (
                pattern is None
                or pattern.pattern_type != "UniformExcitation"
            ):
                QMessageBox.warning(
                    self,
                    "Ground Motion Editor",
                    "The selected object is not a valid UniformExcitation "
                    "ground-motion pattern.",
                )
                return

            if not self._ask_create_prerequisite(
                title="Ground Motion Editor",
                message=(
                    "This UniformExcitation pattern has no valid Path time "
                    "series. Create and link a replacement ground-motion "
                    "record now?"
                ),
                action_label="Create / Link Path Series Now...",
            ):
                return

            dialog = GroundMotionDialog(
                next_series_tag=self.project.next_time_series_tag(),
                next_pattern_tag=pattern.tag,
                units=self.project.units,
                initial_source="builtin",
                parent=self,
            )
            dialog.pattern_tag.setValue(pattern.tag)
            dialog.pattern_tag.setEnabled(False)
            dialog.name.setText(pattern.name)
            direction_index = dialog.direction.findData(pattern.direction)
            if direction_index >= 0:
                dialog.direction.setCurrentIndex(direction_index)
            dialog.scale.setValue(float(pattern.factor))
            dialog.vel0.setValue(float(pattern.vel0))
            if not dialog.exec():
                return

            before = self.project.to_dict()
            try:
                new_series, repaired_pattern = dialog.data()
                if new_series.tag in self.project.time_series:
                    raise ValueError(
                        f"Time series tag {new_series.tag} already exists."
                    )
                self.project.add_time_series(new_series)
                try:
                    self.project.update_load_pattern(
                        pattern.tag,
                        repaired_pattern,
                    )
                except Exception:
                    self.project.time_series.pop(new_series.tag, None)
                    raise
            except ValueError as exc:
                self.project = ProjectDatabase.from_dict(before)
                self.model = self.project.model
                QMessageBox.warning(
                    self,
                    "Ground Motion Editor",
                    str(exc),
                )
                self._refresh_all()
                return

            self._refresh_project_metadata(
                f"Repaired ground motion {repaired_pattern.tag}: "
                f"linked Path series {new_series.tag}"
            )
            self._show_ground_motion_properties(repaired_pattern.tag)
            self._record_project_change(
                f"Repair ground motion {repaired_pattern.tag}",
                before,
            )
            return

        series, pattern = pair
        dialog = GroundMotionDialog(
            series=series,
            pattern=pattern,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated_series, updated_pattern = dialog.data()
            self.project.update_time_series(
                series.tag,
                updated_series,
            )
            self.project.update_load_pattern(
                pattern.tag,
                updated_pattern,
            )
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Ground Motion Editor", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(
            f"Updated ground motion {updated_pattern.tag}"
        )
        self._show_ground_motion_properties(updated_pattern.tag)
        self._record_project_change(
            f"Edit ground motion {pattern.tag}",
            before,
        )

    def _delete_ground_motion(self, pattern_tag: int) -> None:
        pair = self._ground_motion_pair(pattern_tag)
        if pair is None:
            return
        series, pattern = pair
        before = self.project.to_dict()
        self.project.remove_load_pattern(pattern.tag)
        if not any(
            item.time_series_tag == series.tag
            for item in self.project.load_patterns.values()
        ):
            self.project.remove_time_series(series.tag)
        self._refresh_project_metadata(
            f"Deleted ground motion {pattern.tag}"
        )
        self._record_project_change(
            f"Delete ground motion {pattern.tag}",
            before,
        )

    def _show_ground_motion_properties(self, pattern_tag: int) -> None:
        pair = self._ground_motion_pair(pattern_tag)
        if pair is None:
            return
        series, pattern = pair
        axis = {1: "X", 2: "Y", 3: "Z"}.get(
            pattern.direction,
            f"DOF {pattern.direction}",
        )
        total_scale = float(series.factor) * float(pattern.factor)
        duration = (
            max(0, len(series.values) - 1) * series.dt
            if series.values
            else 0.0
        )
        unit_system = UnitSystem.from_mapping(self.project.units)
        self.properties_panel.set_properties(
            "Ground Motion",
            [
                ("Pattern Tag", pattern.tag),
                ("Path Series Tag", series.tag),
                ("Name", pattern.name),
                ("Excitation", "UniformExcitation"),
                ("Direction", axis),
                ("dt", f"{series.dt:g} {unit_system.time}"),
                ("Points", len(series.values)),
                ("Duration", f"{duration:g} {unit_system.time}"),
                ("Scale Factor", f"{total_scale:g}"),
                ("Initial Velocity", f"{pattern.vel0:g}"),
            ],
        )

    def _create_nodal_load(self) -> None:
        if not self._ensure_node_count(
            1,
            title="Nodal Load",
        ):
            return
        plain = self._plain_load_patterns()
        if not plain:
            if not self._ensure_plain_load_pattern(title="Nodal Load"):
                return
            plain = self._plain_load_patterns()
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
            allowed_load_types=(
                {"SurfacePressure"}
                if load.load_type == "SurfacePressure"
                else {"Uniform", "Point", "SelfWeight"}
            ),
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

    def _create_prescribed_displacement(self) -> None:
        if not self._ensure_node_count(
            1,
            title="Prescribed Displacement",
        ):
            return
        plain = self._plain_load_patterns()
        if not plain:
            if not self._ensure_plain_load_pattern(
                title="Prescribed Displacement"
            ):
                return
            plain = self._plain_load_patterns()

        selected = sorted(self.selection.nodes)
        node_tag = (
            selected[0]
            if selected
            else min(self.model.nodes, default=1)
        )
        dialog = PrescribedDisplacementDialog(
            plain,
            next_tag=self.project.next_prescribed_displacement_tag(),
            node_tag=node_tag,
            ndf=self.model.ndf,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return

        template = dialog.data()
        targets = selected or [template.node_tag]
        before = self.project.to_dict()
        created: list[int] = []
        next_tag = template.tag
        try:
            for target_node in targets:
                while next_tag in self.project.prescribed_displacements:
                    next_tag += 1
                displacement = PrescribedDisplacementData(
                    tag=next_tag,
                    name=(
                        f"{template.name} - Node {target_node}"
                        if len(targets) > 1
                        else template.name
                    ),
                    pattern_tag=template.pattern_tag,
                    node_tag=target_node,
                    dof=template.dof,
                    value=template.value,
                )
                self.project.add_prescribed_displacement(displacement)
                created.append(displacement.tag)
                next_tag += 1
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(
                self,
                "Prescribed Displacement Editor",
                str(exc),
            )
            self._refresh_all()
            return

        self._refresh_project_metadata(
            f"Created {len(created)} prescribed displacement(s)"
        )
        self._record_project_change(
            "Create prescribed displacement(s)",
            before,
        )

    def _edit_prescribed_displacement(self, tag: int) -> None:
        displacement = self.project.prescribed_displacements.get(tag)
        if displacement is None:
            return
        plain = {
            key: pattern
            for key, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }
        dialog = PrescribedDisplacementDialog(
            plain,
            displacement=displacement,
            ndf=self.model.ndf,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_prescribed_displacement(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Prescribed Displacement Editor",
                str(exc),
            )
            return
        self._refresh_project_metadata(
            f"Updated prescribed displacement {updated.tag}"
        )
        self._show_prescribed_displacement_properties(updated.tag)
        self._record_project_change(
            f"Edit prescribed displacement {tag}",
            before,
        )

    def _delete_prescribed_displacement(self, tag: int) -> None:
        if tag not in self.project.prescribed_displacements:
            return
        before = self.project.to_dict()
        self.project.remove_prescribed_displacement(tag)
        self._refresh_project_metadata(
            f"Deleted prescribed displacement {tag}"
        )
        self._record_project_change(
            f"Delete prescribed displacement {tag}",
            before,
        )

    def _show_prescribed_displacement_properties(
        self,
        tag: int,
    ) -> None:
        displacement = self.project.prescribed_displacements.get(tag)
        if displacement is None:
            return
        dof_label = ("UX", "UY", "UZ", "RX", "RY", "RZ")[
            displacement.dof - 1
        ]
        unit_system = UnitSystem.from_mapping(self.project.units)
        unit = unit_system.length if displacement.dof <= 3 else "rad"
        pattern = self.project.load_patterns.get(
            displacement.pattern_tag
        )
        series = (
            self.project.time_series.get(pattern.time_series_tag)
            if pattern is not None
            else None
        )
        rows = [
            ("Tag", displacement.tag),
            ("Name", displacement.name),
            ("Pattern", displacement.pattern_tag),
            (
                "Time Series",
                (
                    f"{series.tag} - {series.name}"
                    if series is not None
                    else "-"
                ),
            ),
            ("Node", displacement.node_tag),
            ("DOF", f"{dof_label} ({displacement.dof})"),
            ("Value", f"{displacement.value:g} {unit}"),
            (
                "Behavior",
                "Value × Plain-pattern Time Series factor",
            ),
        ]
        self.properties_panel.set_properties(
            "Prescribed Displacement",
            rows,
        )

    def _create_shell_pressure(self) -> None:
        plain = self._plain_load_patterns()
        if not plain:
            if not self._ensure_plain_load_pattern(
                title="Shell Surface Pressure"
            ):
                return
            plain = self._plain_load_patterns()

        selected = sorted(
            int(tag)
            for tag in self.selection.elements
            if (
                tag in self.model.elements
                and self.model.elements[tag].element_type
                in SHELL_ELEMENT_TYPES
            )
        )
        if not selected:
            existing = sorted(
                int(tag)
                for tag, element in self.model.elements.items()
                if element.element_type in SHELL_ELEMENT_TYPES
            )
            if not existing:
                if not self._ensure_prerequisite(
                    title="Shell Surface Pressure",
                    message=(
                        "Surface pressure requires meshed Shell elements. "
                        "Create one now?"
                    ),
                    action_label="Create & Mesh Surface Now...",
                    available=lambda: any(
                        element.element_type in SHELL_ELEMENT_TYPES
                        for element in self.model.elements.values()
                    ),
                    creator=self._create_surface_geometry_and_mesh,
                ):
                    return
                selected = sorted(
                    int(tag)
                    for tag in self.selection.elements
                    if (
                        tag in self.model.elements
                        and self.model.elements[tag].element_type
                        in SHELL_ELEMENT_TYPES
                    )
                )
            else:
                QMessageBox.information(
                    self,
                    "Shell Surface Pressure",
                    "Select at least one Shell element first.",
                )
                return
        if not selected:
            return

        dialog = ElementLoadDialog(
            plain,
            next_tag=self.project.next_element_load_tag(),
            element_tag=selected[0],
            units=self.project.units,
            allowed_load_types={"SurfacePressure"},
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
                        f"{template.name} - Shell {element_tag}"
                        if len(selected) > 1
                        else template.name
                    ),
                    pattern_tag=template.pattern_tag,
                    element_tag=element_tag,
                    load_type="SurfacePressure",
                    pressure=template.pressure,
                )
                self.project.add_element_load(load)
                created.append(load.tag)
                next_tag += 1
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(
                self,
                "Shell Surface Pressure",
                str(exc),
            )
            self._refresh_all()
            return

        self._refresh_project_metadata(
            f"Created {len(created)} shell surface pressure load(s)"
        )
        self._record_project_change(
            "Create shell surface pressure load(s)",
            before,
        )

    def _create_element_load(self) -> None:
        plain = self._plain_load_patterns()
        if not plain:
            if not self._ensure_plain_load_pattern(
                title="Beam / Element Load"
            ):
                return
            plain = self._plain_load_patterns()

        selected_tags = self._selected_element_tags(
            "Beam / Element Load",
            create_if_missing=True,
            frame_only=True,
        )
        if selected_tags is None:
            return
        selected = sorted(selected_tags)

        dialog = ElementLoadDialog(
            plain,
            next_tag=self.project.next_element_load_tag(),
            element_tag=selected[0],
            units=self.project.units,
            allowed_load_types={"Uniform", "Point", "SelfWeight"},
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
                    pressure=template.pressure,
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
        elif load.load_type == "SurfacePressure":
            unit_system = UnitSystem.from_mapping(self.project.units)
            element = self.model.elements.get(load.element_tag)
            try:
                _center, normal, _area = shell_surface_geometry(
                    self.model,
                    element,
                )
                pressure_vector = tuple(
                    float(load.pressure) * float(value)
                    for value in normal
                )
                normal_text = "(" + ", ".join(
                    f"{value:.6g}" for value in normal
                ) + ")"
                pressure_vector_text = "(" + ", ".join(
                    f"{value:.6g}" for value in pressure_vector
                ) + ")"
            except (TypeError, ValueError):
                normal_text = "Unavailable"
                pressure_vector_text = "Unavailable"
            rows.extend([
                (
                    f"Pressure [{unit_system.stress_label}]",
                    f"{load.pressure:g}",
                ),
                (
                    "Direction",
                    "Shell normal: + outward / - inward",
                ),
                ("Shell normal XYZ", normal_text),
                (
                    f"Global pressure vector [{unit_system.stress_label}]",
                    pressure_vector_text,
                ),
                (
                    "OpenSees",
                    "SurfaceLoad + eleLoad -surfaceLoad",
                ),
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
        *,
        create_if_missing: bool = False,
        frame_only: bool = False,
    ) -> set[int] | None:
        frame_types = {
            "elasticBeamColumn",
            "forceBeamColumn",
            "dispBeamColumn",
        }

        def eligible(tag: int) -> bool:
            element = self.model.elements.get(int(tag))
            if element is None:
                return False
            return not frame_only or element.element_type in frame_types

        tags = {
            int(tag)
            for tag in self.selection.elements
            if eligible(int(tag))
        }
        if tags:
            return tags

        available = {
            int(tag)
            for tag in self.model.elements
            if eligible(int(tag))
        }
        if create_if_missing and not available:
            if not self._ensure_prerequisite(
                title=title,
                message=(
                    "This workflow requires a beam-column element first. "
                    "Create a Frame member now?"
                ),
                action_label="Create Frame Now...",
                available=lambda: any(
                    element.element_type in frame_types
                    for element in self.model.elements.values()
                ),
                creator=self._create_frame,
            ):
                return None
            tags = {
                int(tag)
                for tag in self.selection.elements
                if eligible(int(tag))
            }
            if tags:
                return tags

        QMessageBox.information(
            self,
            title,
            (
                "Select at least one beam-column element first."
                if frame_only
                else "Select at least one element first."
            ),
        )
        return None

    def _set_element_formulation(self) -> None:
        element_tags = self._selected_element_tags(
            "Element Formulation",
            create_if_missing=True,
            frame_only=True,
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
            updated = self.project.assign_element_formulation(
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
        element_tags = self._selected_element_tags(
            "Assign Section",
            create_if_missing=True,
            frame_only=True,
        )
        if element_tags is None:
            return
        if not self._ensure_prerequisite(
            title="Assign Section",
            message=(
                "No Sections exist yet. Create a Section now, then return "
                "directly to assignment?"
            ),
            action_label="Create Section Now...",
            available=lambda: bool(self.project.sections),
            creator=self._create_section,
        ):
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
        try:
            assigned = self.project.assign_section_to_elements(
                element_tags,
                section_tag,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Assign Section", str(exc))
            return
        self._refresh_project_metadata(
            f"Assigned section {section_tag} to {len(assigned)} element(s)"
        )
        self._record_project_change(
            f"Assign section {section_tag}",
            before,
        )

    def _assign_truss_material_to_selection(self) -> None:
        if not any(
            element.element_type == "truss"
            for element in self.model.elements.values()
        ):
            if not self._ensure_prerequisite(
                title="Assign Truss Material",
                message=(
                    "No Truss element exists yet. Create a Truss now, then "
                    "return directly to material assignment?"
                ),
                action_label="Create Truss Now...",
                available=lambda: any(
                    element.element_type == "truss"
                    for element in self.model.elements.values()
                ),
                creator=self._create_truss,
            ):
                return
        element_tags = self._selected_element_tags(
            "Assign Truss Material"
        )
        if element_tags is None:
            return
        truss_tags = {
            tag
            for tag in element_tags
            if tag in self.model.elements
            and self.model.elements[tag].element_type == "truss"
        }
        if not truss_tags:
            QMessageBox.information(
                self,
                "Assign Truss Material",
                "Select at least one Truss element first.",
            )
            return
        if not self._ensure_prerequisite(
            title="Assign Truss Material",
            message=(
                "No uniaxial Materials exist yet. Create a Material now, "
                "then return directly to assignment?"
            ),
            action_label="Create Material Now...",
            available=lambda: bool(self.project.materials),
            creator=self._create_material,
        ):
            return

        tags = sorted(self.project.materials)
        labels = [
            (
                f"{tag} - {self.project.materials[tag].name} "
                f"({self.project.materials[tag].material_type})"
            )
            for tag in tags
        ]
        existing = {
            self.model.elements[tag].truss_material_tag
            for tag in truss_tags
        }
        current_index = 0
        if len(existing) == 1:
            current_tag = next(iter(existing))
            if current_tag in tags:
                current_index = tags.index(current_tag)

        label, ok = QInputDialog.getItem(
            self,
            "Assign Truss Material",
            f"Assign to {len(truss_tags)} selected Truss element(s):",
            labels,
            current_index,
            False,
        )
        if not ok:
            return
        material_tag = tags[labels.index(label)]

        before = self.project.to_dict()
        assigned = self.model.assign_truss_material(
            truss_tags,
            material_tag,
        )
        self._refresh_project_metadata(
            f"Assigned material {material_tag} to "
            f"{len(assigned)} Truss element(s)"
        )
        self._record_project_change(
            f"Assign Truss material {material_tag}",
            before,
        )

    def _clear_truss_material_assignment(self) -> None:
        element_tags = self._selected_element_tags(
            "Clear Truss Material"
        )
        if element_tags is None:
            return
        truss_tags = {
            tag
            for tag in element_tags
            if tag in self.model.elements
            and self.model.elements[tag].element_type == "truss"
        }
        if not truss_tags:
            QMessageBox.information(
                self,
                "Clear Truss Material",
                "Select at least one Truss element first.",
            )
            return
        before = self.project.to_dict()
        assigned = self.model.assign_truss_material(
            truss_tags,
            None,
        )
        self._refresh_project_metadata(
            f"Cleared material on {len(assigned)} Truss element(s)"
        )
        self._record_project_change(
            "Clear Truss material assignment",
            before,
        )

    def _assign_transformation_to_selection(self) -> None:
        element_tags = self._selected_element_tags(
            "Assign Transformation",
            create_if_missing=True,
            frame_only=True,
        )
        if element_tags is None:
            return
        if not self._ensure_prerequisite(
            title="Assign Transformation",
            message=(
                "No Geometric Transformations exist yet. Create one now, "
                "then return directly to assignment?"
            ),
            action_label="Create Transformation Now...",
            available=lambda: bool(self.project.transformations),
            creator=self._create_transformation,
        ):
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
        try:
            assigned = self.project.assign_transformation_to_elements(
                element_tags,
                transformation_tag,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Assign Transformation",
                str(exc),
            )
            return
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
        try:
            assigned = self.project.assign_section_to_elements(
                element_tags,
                None,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Clear Section", str(exc))
            return
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
        try:
            assigned = self.project.assign_transformation_to_elements(
                element_tags,
                None,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Clear Transformation",
                str(exc),
            )
            return
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

    def _default_truss_area(self) -> float:
        unit_system = UnitSystem.from_mapping(self.project.units)
        return 1.0e-3 / (unit_system.length_to_m ** 2)

    def _create_truss_between_nodes(
        self,
        node_i: int,
        node_j: int,
    ) -> None:
        """Create one quick axial Truss using current/default assignments."""
        if not self._ensure_prerequisite(
            title="Create Truss",
            message=(
                "A Truss requires a uniaxial Material. "
                "Create the Material now?"
            ),
            action_label="Create Material Now...",
            available=lambda: bool(self.project.materials),
            creator=self._create_material,
        ):
            return

        tag = self.project.next_element_tag()
        material_tag = min(self.project.materials)
        area = self._default_truss_area()
        before = self.project.to_dict()

        try:
            if tag in self.project.connections:
                raise ValueError(
                    f"Element tag {tag} is already used by a connection."
                )
            self.model.add_element(
                tag,
                int(node_i),
                int(node_j),
                element_type="truss",
                group="truss",
                truss_area=area,
                truss_material_tag=material_tag,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Create Truss", str(exc))
            return

        unit_system = UnitSystem.from_mapping(self.project.units)
        self._refresh_all(
            f"Created Truss {tag}: node {node_i} → {node_j} · "
            f"A={area:g} {unit_system.length}² · material {material_tag}"
        )
        self.selection.select("element", tag, "replace")
        self._record_project_change(f"Create Truss {tag}", before)

    def _create_truss(self) -> None:
        """Create a fully specified axial Truss element by input."""
        if not self._ensure_node_count(
            2,
            title="Create Truss Element",
        ):
            return
        if not self._ensure_prerequisite(
            title="Create Truss Element",
            message=(
                "A Truss requires a uniaxial Material for its axial "
                "constitutive response. Create the Material now?"
            ),
            action_label="Create Material Now...",
            available=lambda: bool(self.project.materials),
            creator=self._create_material,
        ):
            return

        selected_nodes = sorted(self.selection.nodes)
        node_i = (
            selected_nodes[0]
            if len(selected_nodes) >= 1
            else min(self.model.nodes)
        )
        node_j = (
            selected_nodes[1]
            if len(selected_nodes) >= 2
            else next(
                node_tag
                for node_tag in sorted(self.model.nodes)
                if node_tag != node_i
            )
        )

        dialog = TrussDialog(
            self.project.next_element_tag(),
            node_i=node_i,
            node_j=node_j,
            materials=self.project.materials,
            units=self.project.units,
            default_area=self._default_truss_area(),
            parent=self,
        )
        if not dialog.exec():
            return

        try:
            (
                tag,
                i,
                j,
                area,
                material_tag,
                group,
                rho,
                consistent_mass,
                do_rayleigh,
            ) = dialog.values()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Create Truss Element",
                str(exc),
            )
            return

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
                element_type="truss",
                group=group,
                mass_per_length=rho,
                consistent_mass=consistent_mass,
                truss_area=area,
                truss_material_tag=material_tag,
                truss_do_rayleigh=do_rayleigh,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Create Truss Element",
                str(exc),
            )
            return

        self._refresh_all(
            f"Created Truss {tag}: node {i} → {j} · "
            f"A={area:g} · material {material_tag}"
        )
        self.selection.select("element", tag, "replace")
        self._record_project_change(f"Create Truss {tag}", before)

    def _create_frame_between_nodes(
        self,
        node_i: int,
        node_j: int,
    ) -> None:
        """Create one quick frame member between two existing nodes."""
        if not self._ensure_prerequisite(
            title="Create Frame",
            message=(
                "Quick Frame creation requires an Elastic Section. "
                "Create a Section now?"
            ),
            action_label="Create Section Now...",
            available=lambda: any(
                section.section_type == "Elastic"
                for section in self.project.sections.values()
            ),
            creator=self._create_section,
        ):
            return
        if not self._ensure_prerequisite(
            title="Create Frame",
            message=(
                "Quick Frame creation requires a Geometric Transformation. "
                "Create one now?"
            ),
            action_label="Create Transformation Now...",
            available=lambda: bool(self.project.transformations),
            creator=self._create_transformation,
        ):
            return

        tag = self.project.next_element_tag()
        section_tag = next(
            section_tag
            for section_tag in sorted(self.project.sections)
            if self.project.sections[section_tag].section_type == "Elastic"
        )
        transf_tag = min(self.project.transformations)

        before = self.project.to_dict()
        try:
            if tag in self.project.connections:
                raise ValueError(
                    f"Element tag {tag} is already used by a connection."
                )
            self.model.add_element(
                tag,
                node_i,
                node_j,
                element_type="elasticBeamColumn",
                section_tag=section_tag,
                transf_tag=transf_tag,
                group="frame",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Create Frame", str(exc))
            return

        assignments: list[str] = []
        if section_tag is not None:
            assignments.append(f"section {section_tag}")
        if transf_tag is not None:
            assignments.append(f"transformation {transf_tag}")

        if section_tag is None or transf_tag is None:
            missing = []
            if section_tag is None:
                missing.append("Elastic section")
            if transf_tag is None:
                missing.append("transformation")
            message = (
                f"Created frame {tag}: node {node_i} → {node_j} · "
                f"assign {' + '.join(missing)} before analysis"
            )
        else:
            message = (
                f"Created frame {tag}: node {node_i} → {node_j} · "
                + " · ".join(assignments)
            )

        self._refresh_all(message)
        self.selection.select("element", tag, "replace")
        self._record_project_change(f"Create frame {tag}", before)

    def _create_frame(self) -> None:
        """Create a solver-ready frame member with explicit assignments."""
        if not self._ensure_node_count(
            2,
            title="Create Frame Member",
        ):
            return
        if not self._ensure_prerequisite(
            title="Create Frame Member",
            message=(
                "A Frame member requires an explicit Section. "
                "Create the Section now?"
            ),
            action_label="Create Section Now...",
            available=lambda: bool(self.project.sections),
            creator=self._create_section,
        ):
            return
        if not self._ensure_prerequisite(
            title="Create Frame Member",
            message=(
                "A Frame member requires a Geometric Transformation. "
                "Create the Transformation now?"
            ),
            action_label="Create Transformation Now...",
            available=lambda: bool(self.project.transformations),
            creator=self._create_transformation,
        ):
            return

        selected_nodes = sorted(self.selection.nodes)
        node_i = (
            selected_nodes[0]
            if len(selected_nodes) >= 1
            else min(self.model.nodes)
        )
        node_j = (
            selected_nodes[1]
            if len(selected_nodes) >= 2
            else next(
                tag
                for tag in sorted(self.model.nodes)
                if tag != node_i
            )
        )

        dialog = ElementDialog(
            self.project.next_element_tag(),
            node_i=node_i,
            node_j=node_j,
            sections=self.project.sections,
            transformations=self.project.transformations,
            parent=self,
        )
        if not dialog.exec():
            return

        try:
            (
                tag,
                i,
                j,
                element_type,
                section_tag,
                transf_tag,
                group,
                integration_type,
                integration_points,
            ) = dialog.values()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Create Frame Member",
                str(exc),
            )
            return

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
                section_tag=section_tag,
                transf_tag=transf_tag,
                group=group,
                integration_type=integration_type,
                integration_points=integration_points,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Create Frame Member",
                str(exc),
            )
            return

        self._refresh_all(
            f"Created frame {tag}: node {i} → {j} · "
            f"{element_type} · section {section_tag} · "
            f"transformation {transf_tag}"
        )
        self.selection.select("element", tag, "replace")
        self._record_project_change(f"Create frame {tag}", before)

    def _create_shell_mesh(self) -> None:
        if (int(self.model.ndm), int(self.model.ndf)) != (3, 6):
            QMessageBox.warning(
                self,
                "Shell Surface Mesh",
                "Shell meshing requires the 3D/6DOF structural model "
                "(ndm=3, ndf=6). This is shell-surface kinematics, not "
                "solid/brick continuum modeling.",
            )
            return
        if not self._ensure_node_count(4, title="Shell Surface Mesh"):
            return
        if not self._ensure_prerequisite(
            title="Shell Surface Mesh",
            message=(
                "A Shell mesh requires a shell-compatible Section. "
                "Create one now?"
            ),
            action_label="Create Shell Section Now...",
            available=lambda: bool(self._shell_sections()),
            creator=self._create_shell_section,
        ):
            return

        selected_nodes = [
            int(tag)
            for tag in sorted(self.selection.nodes)
            if int(tag) in self.model.nodes
        ]
        dialog = ShellMeshDialog(
            nodes=self.model.nodes,
            sections=self.project.sections,
            initial_nodes=selected_nodes[:4],
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            result = build_shell_mesh(
                self.project,
                dialog.spec(),
            )
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(
                self,
                "Shell Surface Mesh",
                str(exc),
            )
            self._refresh_all()
            return

        self.model = self.project.model
        conformity = []
        if result.conformed_u:
            conformity.append("U conformed")
        if result.conformed_v:
            conformity.append("V conformed")
        conformity_text = (
            " · " + ", ".join(conformity)
            if conformity
            else ""
        )
        self._refresh_all(
            f"Created shell surface mesh · "
            f"{result.divisions_u}×{result.divisions_v} = "
            f"{len(result.element_tags)} element(s) · "
            f"{len(result.node_tags)} generated node(s) · "
            f"{len(result.reused_node_tags)} reused node(s)"
            f"{conformity_text}"
        )
        self.selection.set_selection(
            elements=set(result.element_tags),
        )
        self._record_project_change(
            "Create shell surface mesh",
            before,
        )

    def _create_shell(self) -> None:
        if (int(self.model.ndm), int(self.model.ndf)) != (3, 6):
            QMessageBox.warning(
                self,
                "Direct Shell Element",
                "OpenSees shell elements require a 3D/6DOF model "
                "(ndm=3, ndf=6). SARE intentionally stops at shell "
                "surfaces and does not add solid/brick elements.",
            )
            return
        if not self._ensure_node_count(
            4,
            title="Direct Shell Element",
        ):
            return
        if not self._ensure_prerequisite(
            title="Direct Shell Element",
            message=(
                "A direct Shell element requires a shell-compatible Section. "
                "Create an ElasticMembranePlate Section now?"
            ),
            action_label="Create Shell Section Now...",
            available=lambda: bool(self._shell_sections()),
            creator=self._create_shell_section,
        ):
            return

        selected_nodes = [
            int(tag)
            for tag in sorted(self.selection.nodes)
            if int(tag) in self.model.nodes
        ]
        dialog = ShellElementDialog(
            tag=self.project.next_element_tag(),
            nodes=self.model.nodes,
            sections=self.project.sections,
            initial_nodes=selected_nodes[:4],
            parent=self,
        )
        if not dialog.exec():
            return
        try:
            (
                tag,
                node_tags,
                formulation,
                section_tag,
                corotational,
                local_x,
                no_eas,
                drilling_stab,
                drilling_nl,
            ) = dialog.values()
        except ValueError as exc:
            QMessageBox.warning(self, "Direct Shell Element", str(exc))
            return

        before = self.project.to_dict()
        try:
            if tag in self.project.connections:
                raise ValueError(
                    f"Element tag {tag} is already used by a connection."
                )
            self.model.add_element(
                tag,
                node_tags[0],
                node_tags[1],
                element_type=formulation,
                section_tag=section_tag,
                group="shell",
                k=node_tags[2],
                l=node_tags[3],
                shell_corotational=corotational,
                shell_local_x=local_x,
                shell_no_eas=no_eas,
                shell_drilling_stab=drilling_stab,
                shell_drilling_nl=drilling_nl,
            )
            self.project.validate_element_state(tag)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Direct Shell Element", str(exc))
            self._refresh_all()
            return

        self._refresh_all(
            f"Created {formulation} shell {tag}: nodes "
            + ", ".join(map(str, node_tags))
            + f" · section {section_tag}"
        )
        self.selection.select("element", tag, "replace")
        self._record_project_change(f"Create shell {tag}", before)

    def _edit_shell(self, tag: int) -> None:
        element = self.model.elements.get(int(tag))
        if element is None or element.element_type not in SHELL_ELEMENT_TYPES:
            return
        dialog = ShellElementDialog(
            tag=element.tag,
            nodes=self.model.nodes,
            sections=self.project.sections,
            element=element,
            parent=self,
        )
        dialog.tag.setEnabled(False)
        if not dialog.exec():
            return
        try:
            (
                _tag,
                node_tags,
                formulation,
                section_tag,
                corotational,
                local_x,
                no_eas,
                drilling_stab,
                drilling_nl,
            ) = dialog.values()
        except ValueError as exc:
            QMessageBox.warning(self, "Edit Shell", str(exc))
            return

        before = self.project.to_dict()
        try:
            updated = type(element)(
                tag=element.tag,
                i=node_tags[0],
                j=node_tags[1],
                element_type=formulation,
                section_tag=section_tag,
                transf_tag=None,
                group=element.group or "shell",
                k=node_tags[2],
                l=node_tags[3],
                shell_corotational=corotational,
                shell_local_x=local_x,
                shell_no_eas=no_eas,
                shell_drilling_stab=drilling_stab,
                shell_drilling_nl=drilling_nl,
            )
            self.model.elements[element.tag] = updated
            self.project.validate_element_state(element.tag)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Edit Shell", str(exc))
            self._refresh_all()
            return

        self._refresh_all(f"Updated shell element {tag}")
        self._show_entity_properties("element", tag)
        self._record_project_change(f"Edit shell {tag}", before)

    def _stitch_coincident_shell_nodes(self) -> None:
        groups = self.project.coincident_shell_node_groups()
        if not groups:
            QMessageBox.information(
                self,
                "Stitch Coincident Shell Nodes",
                "No coincident shell node groups were found.",
            )
            return

        duplicate_count = sum(len(group) - 1 for group in groups)
        preview = "; ".join(
            " / ".join(map(str, group))
            for group in groups[:6]
        )
        if len(groups) > 6:
            preview += "; ..."

        answer = QMessageBox.question(
            self,
            "Stitch Coincident Shell Nodes",
            (
                f"Found {len(groups)} coincident shell node group(s) "
                f"containing {duplicate_count} duplicate node(s).\n\n"
                f"Groups: {preview}\n\n"
                "SARE will keep the lowest tag in each group and remap "
                "Shell connectivity. The operation is blocked if a node to "
                "be removed has incompatible support/mass data or is used "
                "by loads, constraints, connections, recorders, analysis "
                "control, result scopes, or non-shell elements.\n\n"
                "Continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        try:
            result = self.project.stitch_coincident_shell_nodes()
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(
                self,
                "Stitch Coincident Shell Nodes",
                str(exc),
            )
            return

        self.model = self.project.model
        merged_nodes = {
            int(tag)
            for tag in result.get("merged_nodes", [])
        }
        kept_nodes = {
            int(tag)
            for tag in result.get("kept_nodes", [])
            if int(tag) in self.model.nodes
        }
        remapped_elements = {
            int(tag)
            for tag in result.get("remapped_elements", [])
            if int(tag) in self.model.elements
        }
        self._refresh_all(
            f"Stitched {len(merged_nodes)} duplicate shell node(s) into "
            f"{len(kept_nodes)} keeper node(s) · "
            f"{len(remapped_elements)} shell element(s) remapped"
        )
        self.selection.set_selection(
            nodes=kept_nodes,
            elements=remapped_elements,
        )
        self._record_project_change(
            "Stitch coincident shell nodes",
            before,
        )

    def _reverse_selected_shell_normals(self) -> None:
        shell_tags = sorted(
            int(tag)
            for tag in self.selection.elements
            if (
                tag in self.model.elements
                and self.model.elements[tag].element_type
                in SHELL_ELEMENT_TYPES
            )
        )
        if not shell_tags:
            QMessageBox.information(
                self,
                "Reverse Shell Normal",
                "Select at least one Shell element first.",
            )
            return

        before = self.project.to_dict()
        try:
            result = (
                self.project.reverse_shell_orientation_preserving_pressure(
                    shell_tags
                )
            )
            updated = result["element_tags"]
            pressure_loads = result["pressure_load_tags"]
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(
                self,
                "Reverse Shell Normal",
                str(exc),
            )
            return

        pressure_text = (
            f" · preserved {len(pressure_loads)} surface pressure load(s)"
            if pressure_loads
            else ""
        )
        self._refresh_all(
            f"Reversed surface normal for {len(updated)} shell element(s)"
            f"{pressure_text}"
        )
        self.selection.set_selection(elements=set(updated))
        self._record_project_change(
            "Reverse shell normal",
            before,
        )

    def _assign_shell_section_to_selection(self) -> None:
        element_tags = {
            int(tag)
            for tag in self.selection.elements
            if (
                tag in self.model.elements
                and self.model.elements[tag].element_type in SHELL_ELEMENT_TYPES
            )
        }
        if not element_tags:
            existing = {
                int(tag)
                for tag, element in self.model.elements.items()
                if element.element_type in SHELL_ELEMENT_TYPES
            }
            if not existing:
                if not self._ensure_prerequisite(
                    title="Assign Shell Section",
                    message=(
                        "This workflow requires meshed Shell elements first. "
                        "Create and mesh Surface Geometry now?"
                    ),
                    action_label="Create & Mesh Surface Now...",
                    available=lambda: any(
                        element.element_type in SHELL_ELEMENT_TYPES
                        for element in self.model.elements.values()
                    ),
                    creator=self._create_surface_geometry_and_mesh,
                ):
                    return
                element_tags = {
                    int(tag)
                    for tag in self.selection.elements
                    if (
                        tag in self.model.elements
                        and self.model.elements[tag].element_type
                        in SHELL_ELEMENT_TYPES
                    )
                }
            else:
                QMessageBox.information(
                    self,
                    "Assign Shell Section",
                    "Select at least one Shell element first.",
                )
                return
        if not element_tags:
            return

        if not self._ensure_prerequisite(
            title="Assign Shell Section",
            message=(
                "No Shell Sections exist yet. Create one now?"
            ),
            action_label="Create Shell Section Now...",
            available=lambda: bool(self._shell_sections()),
            creator=self._create_shell_section,
        ):
            return

        tags = sorted(self._shell_sections())
        labels = [
            f"{section_tag} - {self.project.sections[section_tag].name}"
            for section_tag in tags
        ]
        label, ok = QInputDialog.getItem(
            self,
            "Assign Shell Section",
            f"Assign to {len(element_tags)} selected shell element(s):",
            labels,
            0,
            False,
        )
        if not ok:
            return
        section_tag = tags[labels.index(label)]
        before = self.project.to_dict()
        try:
            assigned = self.project.assign_section_to_elements(
                element_tags,
                section_tag,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Assign Shell Section", str(exc))
            return
        self._refresh_project_metadata(
            f"Assigned shell section {section_tag} to "
            f"{len(assigned)} element(s)"
        )
        self._record_project_change(
            f"Assign shell section {section_tag}",
            before,
        )

    def _create_element(self) -> None:
        """Backward-compatible generic element command: use Frame."""
        self._create_frame()

    def _validate_geometry_edit(
        self,
        nodes: set[int],
        elements: set[int],
        before: dict[str, object],
        *,
        title: str,
    ) -> bool:
        self.project.sync_generated_ground_nodes()
        affected = self.model.entity_node_tags(
            node_tags=nodes,
            element_tags=elements,
        )
        try:
            for node_tag in sorted(affected):
                self.project.validate_node_state(node_tag)
        except (TypeError, ValueError, IndexError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(self, title, str(exc))
            return False
        return True

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
        if not self._validate_geometry_edit(
            nodes,
            elements,
            before,
            title="Move Selection",
        ):
            return
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
            reserved_element_tags=self.project.connections,
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
        if not self._validate_geometry_edit(
            nodes,
            elements,
            before,
            title="Rotate Selection",
        ):
            return
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
        if not self._validate_geometry_edit(
            nodes,
            elements,
            before,
            title="Mirror Selection",
        ):
            return
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
        try:
            self.project.delete_entities(
                node_tags=nodes,
                element_tags=elements,
                cascade_nodes=True,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Delete selected entities",
                str(exc),
            )
            return
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
            f"{PRODUCT_NAME} ({PRODUCT_STAGE}) - [{display_name}]{marker}"
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

    def _recent_project_paths(self) -> list[str]:
        settings = QSettings(LEGACY_SETTINGS_ORGANIZATION, LEGACY_SETTINGS_APPLICATION)
        raw = settings.value("recentProjects", [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            return []
        return [str(path) for path in raw if str(path).strip()]

    def _remember_recent_project(self, path: str | Path) -> None:
        value = str(Path(path).resolve())
        paths = [
            item
            for item in self._recent_project_paths()
            if item != value
        ]
        paths.insert(0, value)
        QSettings(
            LEGACY_SETTINGS_ORGANIZATION,
            LEGACY_SETTINGS_APPLICATION,
        ).setValue("recentProjects", paths[:10])
        if hasattr(self, "recent_projects_menu"):
            self._refresh_recent_projects_menu()

    def _forget_recent_project(self, path: str | Path) -> None:
        value = str(Path(path).resolve())
        paths = [
            item
            for item in self._recent_project_paths()
            if str(Path(item).resolve()) != value
        ]
        QSettings(
            LEGACY_SETTINGS_ORGANIZATION,
            LEGACY_SETTINGS_APPLICATION,
        ).setValue("recentProjects", paths)

    def _refresh_recent_projects_menu(self) -> None:
        menu = getattr(self, "recent_projects_menu", None)
        if menu is None:
            return
        menu.clear()
        paths = [
            path
            for path in self._recent_project_paths()
            if Path(path).is_file()
        ]
        stored = self._recent_project_paths()
        if paths != stored:
            QSettings(
                LEGACY_SETTINGS_ORGANIZATION,
                LEGACY_SETTINGS_APPLICATION,
            ).setValue("recentProjects", paths[:10])
        if not paths:
            action = menu.addAction("No recent projects")
            action.setEnabled(False)
            return
        for path in paths[:10]:
            action = menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(
                lambda checked=False, value=path: (
                    self._open_recent_project(value)
                )
            )
        menu.addSeparator()
        clear_action = menu.addAction("Clear Recent Projects")
        clear_action.triggered.connect(self._clear_recent_projects)

    def _clear_recent_projects(self) -> None:
        QSettings(
            LEGACY_SETTINGS_ORGANIZATION,
            LEGACY_SETTINGS_APPLICATION,
        ).remove("recentProjects")
        self._refresh_recent_projects_menu()

    def _open_recent_project(self, path: str) -> None:
        if not self._maybe_save_changes():
            return
        target = Path(path)
        if not target.is_file():
            self._forget_recent_project(target)
            QMessageBox.warning(
                self,
                "Recent project",
                f"Project file no longer exists:\n{target}",
            )
            return
        try:
            project = ProjectDatabase.load(target)
        except Exception as exc:
            QMessageBox.critical(self, "Open project", str(exc))
            return
        self.selection.clear()
        self.project = project
        self.model = project.model
        self._project_path = target
        self._reset_runtime_results()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_dirty(False)
        self._remember_recent_project(target)
        self._refresh_all(f"Opened {target.name}")

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
        self._remember_recent_project(self._project_path)
        self.status_message.setText(f"Saved {self._project_path.name}")
        return True

    def _save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save SARE Project",
            str(self._project_path or Path("Untitled.opsstudio")),
            "SARE Project (*.opsstudio)",
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
            "Open SARE Project",
            "",
            "SARE Project (*.opsstudio);;All Files (*)",
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
        self._remember_recent_project(self._project_path)
        self._refresh_all(f"Opened {self._project_path.name}")

    def _import_openseespy_script(self) -> None:
        if not self._maybe_save_changes():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import OpenSeesPy Script",
            "",
            "Python (*.py);;All Files (*)",
        )
        if not path:
            return

        labels = [label for label, _units in UNIT_PRESETS]
        current_units = dict(self.project.units)
        current_index = 0
        for index, (_label, units) in enumerate(UNIT_PRESETS):
            if units == current_units:
                current_index = index
                break

        label, ok = QInputDialog.getItem(
            self,
            "OpenSeesPy Import Units",
            (
                "OpenSees is unitless. Select the consistent unit system "
                "used by this script:"
            ),
            labels,
            current_index,
            False,
        )
        if not ok:
            return

        selected_units = dict(UNIT_PRESETS[labels.index(label)][1])
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(
                self,
                "Import OpenSeesPy",
                f"Could not read the Python file:\n\n{exc}",
            )
            return

        result = import_openseespy_source(
            source,
            source_name=Path(path).name,
            units=selected_units,
            source_path=Path(path),
        )
        report = ImportReportDialog(result, parent=self)
        if report.exec() != QDialog.Accepted:
            return

        self.selection.clear()
        self.project = result.project
        self.model = self.project.model
        self._project_path = None
        self._reset_runtime_results()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_dirty(True)
        self._refresh_all(
            f"Imported OpenSeesPy: {Path(path).name} · "
            f"{result.imported_total} recovered object(s) · "
            f"{result.unsupported_count} unsupported"
        )
        self._log(
            f"OpenSeesPy import: {Path(path).name}; "
            f"errors={result.error_count}, warnings={result.warning_count}, "
            f"unsupported={result.unsupported_count}"
        )

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

    def _show_material_library(self) -> None:
        try:
            dialog = MaterialLibraryDialog(
                next_tag=self.project.next_material_tag(),
                units=self.project.units,
                materials=self.project.materials,
                parent=self,
            )
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Material Library",
                f"Could not load the verified material library:\n\n{exc}",
            )
            return

        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            for dependency in dialog.pending_materials():
                self.project.add_material(dependency)
            material = dialog.material_data()
            self.project.add_material(material)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Material Library", str(exc))
            self._refresh_all()
            return

        self._refresh_project_metadata(
            f"Added verified {material.material_type} material "
            f"{material.tag} from library"
        )
        self._show_material_properties(material.tag)
        self._record_project_change(
            f"Add verified material {material.tag}",
            before,
        )

    def _create_nd_material(self) -> None:
        dialog = NDMaterialDialog(
            next_tag=self.project.next_nd_material_tag(),
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            material = dialog.material_data()
            self.project.add_nd_material(material)
        except ValueError as exc:
            QMessageBox.warning(self, "nD Material", str(exc))
            return
        self._refresh_project_metadata(
            f"Created {material.material_type} nDMaterial {material.tag}"
        )
        self._show_nd_material_properties(material.tag)
        self._record_project_change(
            f"Create nD material {material.tag}",
            before,
        )

    def _edit_nd_material(self, tag: int) -> None:
        material = self.project.nd_materials.get(int(tag))
        if material is None:
            return
        dialog = NDMaterialDialog(
            next_tag=material.tag,
            material=material,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.material_data()
            self.project.update_nd_material(tag, updated)
        except ValueError as exc:
            QMessageBox.warning(self, "nD Material", str(exc))
            return
        self._refresh_project_metadata(
            f"Updated nDMaterial {updated.tag}"
        )
        self._show_nd_material_properties(updated.tag)
        self._record_project_change(
            f"Edit nD material {tag}",
            before,
        )

    def _delete_nd_material(self, tag: int) -> None:
        material = self.project.nd_materials.get(int(tag))
        if material is None:
            return
        users = self.project.sections_using_nd_material(tag)
        if users:
            QMessageBox.warning(
                self,
                "Delete nD Material",
                f"nDMaterial {tag} is still referenced by Shell section(s): "
                + ", ".join(map(str, users))
                + ". Reassign those references first.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Delete nD Material",
            f"Delete nDMaterial {tag} ({material.name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        before = self.project.to_dict()
        self.project.remove_nd_material(tag)
        self._refresh_project_metadata(f"Deleted nDMaterial {tag}")
        self._record_project_change(
            f"Delete nD material {tag}",
            before,
        )

    def _show_nd_material_properties(self, tag: int) -> None:
        material = self.project.nd_materials.get(int(tag))
        if material is None:
            return
        unit_system = UnitSystem.from_mapping(self.project.units)
        p = material.parameters
        rows = [
            ("Tag", material.tag),
            ("Name", material.name),
            ("Type", material.material_type),
            (
                f"E [{unit_system.engineering_stress_label}]",
                f"{unit_system.engineering_stress_from_pa(p['E']):g}",
            ),
            ("Poisson ratio ν", f"{p['nu']:g}"),
            (
                f"Density ρ [{unit_system.engineering_density_label}]",
                f"{unit_system.engineering_density_from_kg_per_m3(p['rho']):g}",
            ),
            (
                "Used by Shell sections",
                ", ".join(
                    map(
                        str,
                        self.project.sections_using_nd_material(tag),
                    )
                )
                or "-",
            ),
        ]
        self.properties_panel.set_properties("nD Material", rows)

    def _create_material(self) -> None:
        dialog = MaterialDialog(
            next_tag=self.project.next_material_tag(),
            units=self.project.units,
            materials=self.project.materials,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            for dependency in dialog.pending_materials():
                self.project.add_material(dependency)
            material = dialog.material_data()
            self.project.add_material(material)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Material Editor", str(exc))
            self._refresh_all()
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

        dialog = MaterialDialog(
            material=material,
            units=self.project.units,
            materials=self.project.materials,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            for dependency in dialog.pending_materials():
                self.project.add_material(dependency)
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
                for wrapper in self.project.materials.values():
                    if wrapper.tag == updated.tag:
                        continue
                    if wrapper.base_material_tag == tag:
                        wrapper.base_material_tag = updated.tag
                    wrapper.material_tags = [
                        updated.tag if value == tag else value
                        for value in wrapper.material_tags
                    ]
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Material Editor", str(exc))
            self._refresh_all()
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
            base_material_tag=source.base_material_tag,
            material_tags=list(source.material_tags),
            factors=list(source.factors),
            source=dict(source.source),
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
        wrapper_uses = self.project.materials_using_material(tag)
        if used_by or connection_uses or wrapper_uses:
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
            if wrapper_uses:
                details.append(
                    "wrapper material(s): "
                    + ", ".join(map(str, wrapper_uses))
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

        unit_system = UnitSystem.from_mapping(self.project.units)
        density_display = (
            unit_system.engineering_density_from_kg_per_m3(
                material.density
            )
        )
        rows = [
            ("Tag", material.tag),
            (
                "Name",
                material.name,
                {"id": "name", "editable": True, "kind": "text"},
            ),
            ("Type", material.material_type),
            (
                "Poisson ratio",
                f"{material.poisson_ratio:g}",
                {
                    "id": "poisson_ratio",
                    "editable": True,
                    "kind": "float",
                },
            ),
            (
                (
                    "Density "
                    f"[{unit_system.engineering_density_label}]"
                ),
                f"{density_display:g}",
                {
                    "id": "density",
                    "editable": True,
                    "kind": "float",
                },
            ),
        ]
        if material.base_material_tag is not None:
            base = self.project.materials.get(material.base_material_tag)
            rows.append((
                "Base material",
                (
                    f"{material.base_material_tag} - {base.name}"
                    if base is not None
                    else f"{material.base_material_tag} (missing)"
                ),
            ))
        if material.material_tags:
            component_text = ", ".join(
                (
                    f"{component_tag} - "
                    f"{self.project.materials[component_tag].name}"
                    if component_tag in self.project.materials
                    else f"{component_tag} (missing)"
                )
                for component_tag in material.material_tags
            )
            rows.append(("Component materials", component_text))
            if material.material_type == "Parallel":
                rows.append((
                    "Factors",
                    ", ".join(f"{value:g}" for value in material.factors),
                ))

        try:
            elastic_e = material.elastic_modulus()
            elastic_g = material.shear_modulus()
        except ValueError:
            elastic_e = None
            elastic_g = None
        if elastic_e is not None:
            stress_unit = unit_system.engineering_stress_label
            rows.extend([
                (
                    f"Elastic E [{stress_unit}]",
                    f"{unit_system.engineering_stress_from_pa(elastic_e):g}",
                ),
                (
                    f"Elastic G [{stress_unit}]",
                    f"{unit_system.engineering_stress_from_pa(elastic_g):g}",
                ),
            ])

        for key, parameter_value in material.parameters.items():
            parameter_kind = material_parameter_kind(material, key)
            if parameter_kind == "stress":
                label = (
                    f"{key} "
                    f"[{unit_system.engineering_stress_label}]"
                )
                display = unit_system.engineering_stress_from_pa(
                    parameter_value
                )
            elif parameter_kind == "length":
                label = f"{key} [{unit_system.length}]"
                display = unit_system.length_from_m(parameter_value)
            elif parameter_kind == "force":
                label = f"{key} [{unit_system.force}]"
                display = unit_system.force_from_n(parameter_value)
            elif parameter_kind == "moment":
                label = f"{key} [{unit_system.moment_label}]"
                display = unit_system.moment_from_nm(parameter_value)
            elif parameter_kind == "rotation":
                label = f"{key} [rad]"
                display = parameter_value
            elif parameter_kind == "strain":
                label = f"{key} [strain]"
                display = parameter_value
            else:
                label = key
                display = parameter_value
            rows.append((
                label,
                f"{display:g}",
                {
                    "id": f"parameter:{key}",
                    "editable": True,
                    "kind": "float",
                },
            ))

        if material.source:
            source = material.source
            reference = dict(source.get("primary_reference", {}))
            evidence = dict(source.get("parameter_evidence", {}))
            rows.extend([
                ("Constitutive source status", source.get("status", "unknown")),
                ("Library record", source.get("record_id", "")),
                ("Reference", reference.get("title", "")),
                ("DOI", reference.get("doi", "")),
                ("Parameter evidence", evidence.get("location", "")),
                (
                    "Response quantity",
                    source.get("response_quantity", ""),
                ),
                (
                    "Published units",
                    " / ".join(
                        str(value)
                        for value in dict(
                            source.get("source_units", {})
                        ).values()
                    ),
                ),
            ])

        self.properties_panel.set_properties(
            "Material",
            rows,
            context={"kind": "material", "tag": int(tag)},
        )


    def _create_surface_geometry(self) -> int | None:
        if not self._ensure_prerequisite(
            title="New Surface",
            message=(
                "A Surface requires a shell-compatible Section. "
                "Create one now?"
            ),
            action_label="Create Shell Section Now...",
            available=lambda: bool(self._shell_sections()),
            creator=self._create_shell_section,
        ):
            return None

        dialog = SurfaceGeometryDialog(
            next_tag=self.project.next_surface_tag(),
            sections=self._shell_sections(),
            parent=self,
        )
        if not dialog.exec():
            return None

        before = self.project.to_dict()
        try:
            surface = dialog.data()
            self.project.add_surface(surface)
            result = mesh_surface_geometry(
                self.project,
                surface.tag,
            )
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(self, "Create Surface", str(exc))
            return None

        self.model = self.project.model
        self._refresh_all(
            f"Created Surface {surface.tag} · "
            f"{result.divisions_u}×{result.divisions_v} · "
            f"{len(result.element_tags)} Shell element(s) · "
            f"{len(result.created_node_tags)} new node(s)"
        )
        self.selection.set_selection(
            elements=set(result.element_tags),
        )
        self._show_surface_geometry_properties(surface.tag)
        self._record_project_change(
            f"Create Surface {surface.tag}",
            before,
        )
        return int(surface.tag)

    def _create_surface_geometry_and_mesh(self) -> None:
        self._create_surface_geometry()

    def _edit_surface_geometry(self, tag: int) -> None:
        surface = self.project.surfaces.get(int(tag))
        if surface is None:
            return
        if any(
            element_tag in self.model.elements
            for element_tag in surface.generated_element_tags
        ):
            QMessageBox.information(
                self,
                "Edit Surface Geometry",
                "This Surface already owns generated Shell elements. "
                "Remeshing support will manage geometry edits in the next "
                "surface-mesher stage; keep the current mesh or delete it first.",
            )
            return
        dialog = SurfaceGeometryDialog(
            next_tag=surface.tag,
            sections=self._shell_sections(),
            surface=surface,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            updated = dialog.data()
            self.project.update_surface(tag, updated)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Surface Geometry", str(exc))
            return
        self._refresh_all(f"Updated surface geometry {updated.tag}")
        self._show_surface_geometry_properties(updated.tag)
        self._record_project_change(
            f"Edit surface geometry {tag}",
            before,
        )

    def _mesh_surface_geometry(self, tag: int) -> None:
        surface = self.project.surfaces.get(int(tag))
        if surface is None:
            return
        if surface.section_tag is None:
            if not self._ensure_prerequisite(
                title="Mesh Surface Geometry",
                message=(
                    "This Surface needs a Shell Section before meshing. "
                    "Create one now?"
                ),
                action_label="Create Shell Section Now...",
                available=lambda: bool(self._shell_sections()),
                creator=self._create_shell_section,
            ):
                return
            self._edit_surface_geometry(tag)
            surface = self.project.surfaces.get(int(tag))
            if surface is None or surface.section_tag is None:
                return

        before = self.project.to_dict()
        try:
            result = mesh_surface_geometry(self.project, tag)
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            self._refresh_all()
            QMessageBox.warning(
                self,
                "Mesh Surface Geometry",
                str(exc),
            )
            return

        self.model = self.project.model
        conformity = []
        if result.conformed_u:
            conformity.append("U conformed")
        if result.conformed_v:
            conformity.append("V conformed")
        suffix = (
            " · " + ", ".join(conformity)
            if conformity else ""
        )
        self._refresh_all(
            f"Meshed Surface {tag} · "
            f"{result.divisions_u}×{result.divisions_v} · "
            f"{len(result.element_tags)} shell element(s) · "
            f"{len(result.created_node_tags)} new node(s) · "
            f"{len(result.reused_node_tags)} reused node(s)"
            f"{suffix}"
        )
        self.selection.set_selection(
            elements=set(result.element_tags)
        )
        self._record_project_change(
            f"Mesh surface geometry {tag}",
            before,
        )

    def _delete_surface_geometry(self, tag: int) -> None:
        surface = self.project.surfaces.get(int(tag))
        if surface is None:
            return
        live_mesh = [
            element_tag
            for element_tag in surface.generated_element_tags
            if element_tag in self.model.elements
        ]
        message = f"Delete geometry Surface {tag} ({surface.name})?"
        if live_mesh:
            message += (
                "\n\nGenerated Shell elements will be kept as ordinary "
                "FE elements; only the reusable geometry object is removed."
            )
        answer = QMessageBox.question(
            self,
            "Delete Surface",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        before = self.project.to_dict()
        self.project.remove_surface(tag)
        self._refresh_all(f"Deleted surface geometry {tag}")
        self._record_project_change(
            f"Delete surface geometry {tag}",
            before,
        )

    def _show_surface_geometry_properties(self, tag: int) -> None:
        surface = self.project.surfaces.get(int(tag))
        if surface is None:
            return
        section = (
            self.project.sections.get(surface.section_tag)
            if surface.section_tag is not None
            else None
        )
        live_elements = [
            element_tag
            for element_tag in surface.generated_element_tags
            if element_tag in self.model.elements
        ]
        rows = [
            ("Tag", surface.tag),
            ("Name", surface.name),
            ("Shape", surface.surface_type),
            (
                "Corners",
                " · ".join(
                    "(" + ", ".join(f"{value:g}" for value in point) + ")"
                    for point in surface.points
                ),
            ),
            (
                "Shell Section",
                (
                    f"{section.tag} - {section.name}"
                    if section is not None else "Not assigned"
                ),
            ),
            ("Formulation", surface.formulation),
            (
                "Mesh sizing",
                (
                    f"Target size {surface.target_size:g}"
                    if (
                        surface.mesh_mode == "target_size"
                        and surface.target_size is not None
                    )
                    else (
                        f"{surface.divisions_u} × "
                        f"{surface.divisions_v} divisions"
                    )
                ),
            ),
            (
                "Conform shared edges",
                "Yes" if surface.conform_existing_edges else "No",
            ),
            (
                "Reuse coincident nodes",
                "Yes" if surface.reuse_existing_nodes else "No",
            ),
            (
                "Mesh status",
                (
                    f"Meshed · {len(live_elements)} Shell element(s)"
                    if live_elements else "Unmeshed"
                ),
            ),
        ]
        self.properties_panel.set_properties(
            "Surface Geometry",
            rows,
        )

    def _shell_sections(self) -> dict[int, SectionData]:
        return {
            int(tag): section
            for tag, section in self.project.sections.items()
            if section.section_type in SHELL_SECTION_TYPES
        }

    def _create_shell_section(self) -> None:
        dialog = ShellSectionDialog(
            next_tag=self.project.next_section_tag(),
            nd_materials=self.project.nd_materials,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            for material in dialog.staged_nd_materials():
                self.project.add_nd_material(material)
            section = dialog.section_data()
            self.project.add_section(section)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Shell Section", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(
            f"Created shell section {section.tag}"
        )
        self._show_section_properties(section.tag)
        self._record_project_change(
            f"Create shell section {section.tag}",
            before,
        )

    def _edit_shell_section(self, tag: int) -> None:
        section = self.project.sections.get(int(tag))
        if section is None:
            return
        dialog = ShellSectionDialog(
            section=section,
            nd_materials=self.project.nd_materials,
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            for material in dialog.staged_nd_materials():
                self.project.add_nd_material(material)
            updated = dialog.section_data()
            self.project.update_section(tag, updated)
            if updated.tag != tag:
                for element in self.model.elements.values():
                    if element.section_tag == tag:
                        element.section_tag = updated.tag
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Shell Section", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(
            f"Updated shell section {updated.tag}"
        )
        self._show_section_properties(updated.tag)
        self._record_project_change(
            f"Edit shell section {tag}",
            before,
        )

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
        added_material_tags: list[int] = []
        try:
            for pending_material in dialog.pending_materials():
                self.project.add_material(pending_material)
                added_material_tags.append(pending_material.tag)
            section = dialog.section_data()
            self.project.add_section(section)
        except ValueError as exc:
            for material_tag in reversed(added_material_tags):
                self.project.remove_material(material_tag)
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
        if section.section_type in SHELL_SECTION_TYPES:
            self._edit_shell_section(tag)
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
        added_material_tags: list[int] = []
        try:
            for pending_material in dialog.pending_materials():
                self.project.add_material(pending_material)
                added_material_tags.append(pending_material.tag)
            updated = dialog.section_data()
            self.project.update_section(tag, updated)
            if updated.tag != tag:
                for element in self.model.elements.values():
                    if element.section_tag == tag:
                        element.section_tag = updated.tag
        except ValueError as exc:
            for material_tag in reversed(added_material_tags):
                self.project.remove_material(material_tag)
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
        connection_uses = self.project.connections_using_section(tag)
        if used_by or connection_uses:
            QMessageBox.warning(
                self,
                "Delete Section",
                (
                    "Section is assigned to element(s): "
                    + ", ".join(map(str, used_by[:20]))
                    + ("..." if len(used_by) > 20 else "")
                    if used_by
                    else
                    "Section is assigned to zeroLengthSection connection(s): "
                    + ", ".join(map(str, connection_uses[:20]))
                    + ("..." if len(connection_uses) > 20 else "")
                ),
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

        unit_system = UnitSystem.from_mapping(self.project.units)
        stress_unit = unit_system.engineering_stress_label

        if section.section_type in SHELL_SECTION_TYPES:
            p = section.parameters
            rows = [
                ("Tag", section.tag),
                (
                    "Name",
                    section.name,
                    {"id": "name", "editable": True, "kind": "text"},
                ),
                ("Type", section.section_type),
            ]

            if section.section_type == "ElasticMembranePlate":
                rows.extend([
                    ("OpenSees", "ElasticMembranePlateSection"),
                    (
                        f"E [{stress_unit}]",
                        f"{unit_system.engineering_stress_from_pa(p['E']):g}",
                        {
                            "id": "parameter:E",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                    (
                        "Poisson ratio ν",
                        f"{p['nu']:g}",
                        {
                            "id": "parameter:nu",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                    (
                        f"Thickness h [{unit_system.length}]",
                        f"{p['h']:g}",
                        {
                            "id": "parameter:h",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                    (
                        "Mass density ρ [model mass/L³]",
                        f"{p['rho']:g}",
                        {
                            "id": "parameter:rho",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                    (
                        "Out-of-plane E modifier",
                        f"{p['EpModifier']:g}",
                        {
                            "id": "parameter:EpModifier",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                ])
            elif section.section_type == "PlateFiber":
                material = (
                    self.project.nd_materials.get(
                        int(section.nd_material_tag)
                    )
                    if section.nd_material_tag is not None
                    else None
                )
                rows.extend([
                    ("OpenSees", "PlateFiber"),
                    (
                        "nD Material",
                        (
                            f"{section.nd_material_tag} - {material.name}"
                            if material is not None
                            else f"{section.nd_material_tag} (missing)"
                        ),
                    ),
                    (
                        f"Thickness h [{unit_system.length}]",
                        f"{p['h']:g}",
                        {
                            "id": "parameter:h",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                    (
                        "Material model",
                        material.material_type if material is not None else "-",
                    ),
                ])
                if material is not None:
                    rows.extend([
                        (
                            f"Material E [{stress_unit}]",
                            f"{unit_system.engineering_stress_from_pa(material.parameters['E']):g}",
                        ),
                        (
                            "Material ν",
                            f"{material.parameters['nu']:g}",
                        ),
                        (
                            f"Material ρ [{unit_system.engineering_density_label}]",
                            f"{unit_system.engineering_density_from_kg_per_m3(material.parameters['rho']):g}",
                        ),
                    ])
            else:
                rows.extend([
                    ("OpenSees", "LayeredShell"),
                    ("Layers", len(section.shell_layers)),
                    (
                        f"Total thickness [{unit_system.length}]",
                        f"{section.shell_total_thickness():g}",
                    ),
                ])
                for index, layer in enumerate(
                    section.shell_layers,
                    start=1,
                ):
                    material = self.project.nd_materials.get(
                        int(layer.material_tag)
                    )
                    rows.append((
                        f"Layer {index}",
                        (
                            f"mat {layer.material_tag}"
                            + (
                                f" - {material.name}"
                                if material is not None
                                else " (missing)"
                            )
                            + f" · h={layer.thickness:g} "
                            f"{unit_system.length}"
                        ),
                    ))

            rows.append((
                "Edit definition",
                "Double-click or right-click → Edit...",
            ))
            self.properties_panel.set_properties(
                "Shell Section",
                rows,
                context={"kind": "section", "tag": int(tag)},
            )
            return

        rows = [
            ("Tag", section.tag),
            (
                "Name",
                section.name,
                {"id": "name", "editable": True, "kind": "text"},
            ),
            ("Type", section.section_type),
        ]

        if section.section_type == "Elastic":
            material_choices = [("Manual", None)]
            for material_tag in sorted(self.project.materials):
                material = self.project.materials[material_tag]
                try:
                    material.elastic_modulus()
                except ValueError:
                    continue
                material_choices.append((
                    f"{material_tag} - {material.name}",
                    int(material_tag),
                ))

            if section.material_tag is None:
                material_text = "Manual"
                resolved = section.resolved_elastic_parameters()
            else:
                material = self.project.materials.get(section.material_tag)
                material_text = (
                    f"{section.material_tag} - {material.name}"
                    if material is not None
                    else f"{section.material_tag} (missing)"
                )
                try:
                    resolved = section.resolved_elastic_parameters(
                        self.project.materials
                    )
                except ValueError:
                    resolved = dict(section.parameters)

            rows.append((
                "Material",
                material_text,
                {
                    "id": "material_tag",
                    "editable": True,
                    "kind": "choice",
                    "current": section.material_tag,
                    "choices": material_choices,
                },
            ))

            geometry_driven = bool(section.display_geometry)
            for key in ("A", "Iz", "Iy", "J"):
                spec = {}
                if not geometry_driven:
                    spec = {
                        "id": f"parameter:{key}",
                        "editable": True,
                        "kind": "float",
                    }
                rows.append((key, f"{resolved[key]:g}", spec))

            if section.material_tag is None:
                rows.extend([
                    (
                        f"E [{stress_unit}]",
                        f"{unit_system.engineering_stress_from_pa(section.parameters['E']):g}",
                        {
                            "id": "parameter:E",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                    (
                        f"G [{stress_unit}]",
                        f"{unit_system.engineering_stress_from_pa(section.parameters['G']):g}",
                        {
                            "id": "parameter:G",
                            "editable": True,
                            "kind": "float",
                        },
                    ),
                ])
            else:
                rows.extend([
                    (
                        f"Resolved E [{stress_unit}]",
                        f"{unit_system.engineering_stress_from_pa(resolved['E']):g}",
                    ),
                    (
                        f"Resolved G [{stress_unit}]",
                        f"{unit_system.engineering_stress_from_pa(resolved['G']):g}",
                    ),
                ])
                material = self.project.materials.get(section.material_tag)
                if material is not None:
                    rows.append((
                        (
                            "Density "
                            f"[{unit_system.engineering_density_label}]"
                        ),
                        f"{unit_system.engineering_density_from_kg_per_m3(material.density):g}",
                    ))

            if geometry_driven:
                shape = str(section.display_geometry.get("shape", ""))
                rows.append(("Geometry source", shape or "Parametric"))
        else:
            for key, parameter_value in section.parameters.items():
                if key == "GJ":
                    rows.append((
                        key,
                        f"{parameter_value:g}",
                        {
                            "id": f"parameter:{key}",
                            "editable": True,
                            "kind": "float",
                        },
                    ))
                else:
                    rows.append((key, f"{parameter_value:g}"))
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

        self.properties_panel.set_properties(
            "Section",
            rows,
            context={"kind": "section", "tag": int(tag)},
        )

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
                (
                    "Name",
                    transformation.name,
                    {"id": "name", "editable": True, "kind": "text"},
                ),
                (
                    "Type",
                    transformation.transformation_type,
                    {
                        "id": "transformation_type",
                        "editable": True,
                        "kind": "choice",
                        "current": transformation.transformation_type,
                        "choices": [
                            ("Linear", "Linear"),
                            ("PDelta", "PDelta"),
                            ("Corotational", "Corotational"),
                        ],
                    },
                ),
                (
                    "vecxz X",
                    f"{transformation.vecxz[0]:g}",
                    {
                        "id": "vecxz_x",
                        "editable": True,
                        "kind": "float",
                    },
                ),
                (
                    "vecxz Y",
                    f"{transformation.vecxz[1]:g}",
                    {
                        "id": "vecxz_y",
                        "editable": True,
                        "kind": "float",
                    },
                ),
                (
                    "vecxz Z",
                    f"{transformation.vecxz[2]:g}",
                    {
                        "id": "vecxz_z",
                        "editable": True,
                        "kind": "float",
                    },
                ),
            ],
            context={"kind": "transformation", "tag": int(tag)},
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

    def _apply_connection_dialog_resources(
        self,
        spec: dict,
    ) -> None:
        for material in spec.get("pending_materials", []):
            if material.tag not in self.project.materials:
                self.project.add_material(material)

        for operation, original_tag, section in spec.get(
            "pending_section_operations",
            [],
        ):
            if operation == "add":
                self.project.add_section(section)
            elif operation == "update":
                if original_tag is None:
                    raise ValueError(
                        "Section update is missing its original tag."
                    )
                self.project.update_section(int(original_tag), section)
            else:
                raise ValueError(
                    f"Unsupported staged section operation {operation!r}."
                )

    def _create_connection(self) -> None:
        if not self._ensure_node_count(
            1,
            title="Connection Editor",
        ):
            return
        node_i, node_j, to_ground = self._connection_dialog_defaults()
        dialog = ConnectionDialog(
            self.project.materials,
            sections=self.project.sections,
            next_tag=self.project.next_connection_tag(),
            initial_node_i=node_i,
            initial_node_j=node_j,
            default_to_ground=to_ground,
            node_positions={
                tag: node.xyz
                for tag, node in self.model.nodes.items()
            },
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        created_ground = None
        try:
            spec = dialog.spec()
            self._apply_connection_dialog_resources(spec)

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
                section_tag=spec.get("section_tag"),
                orient_x=tuple(spec["orient_x"]),
                orient_y=tuple(spec["orient_y"]),
                do_rayleigh=bool(spec["do_rayleigh"]),
                generated_ground_node=created_ground,
            )
            self.project.add_connection(connection)
        except (KeyError, TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
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
        if (
            connection.connection_type == "zeroLengthSection"
            and (
                connection.generated_section_tag is not None
                or connection.generated_constraint_tag is not None
            )
        ):
            strain_penetration = (
                connection.generated_section_tag is not None
            )
            if strain_penetration:
                title = "Strain Penetration Interface"
                detail = (
                    "its generated Fiber section, Bond_SP01 material, "
                    "base restraints, and orientation"
                )
            else:
                title = "Managed Section Interface"
                detail = (
                    "its selected Section, automatic shear-transfer "
                    "constraint, base restraints, and orientation"
                )
            QMessageBox.information(
                self,
                title,
                "This zeroLengthSection was created by the specimen-level "
                "Quick 1D Column / Test Specimen workflow. Edit/rebuild it "
                "through that wizard so "
                + detail
                + " stay consistent. General zeroLengthSection elements "
                "created manually or imported can be edited directly.",
            )
            self._show_connection_properties(tag)
            return

        dialog = ConnectionDialog(
            self.project.materials,
            connection=connection,
            sections=self.project.sections,
            node_positions={
                node_tag: node.xyz
                for node_tag, node in self.model.nodes.items()
            },
            units=self.project.units,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        old_ground = connection.generated_ground_node
        created_ground = None
        try:
            spec = dialog.spec()
            self._apply_connection_dialog_resources(spec)

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
                section_tag=spec.get("section_tag"),
                orient_x=tuple(spec["orient_x"]),
                orient_y=tuple(spec["orient_y"]),
                do_rayleigh=bool(spec["do_rayleigh"]),
                generated_ground_node=(
                    created_ground if requested_ground else None
                ),
                generated_section_tag=connection.generated_section_tag,
                generated_constraint_tag=connection.generated_constraint_tag,
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
        except (KeyError, TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
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

        from ..material_chain import describe_material_chain

        dof_labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        material_text = []
        for dof in sorted(connection.materials_by_dof):
            material_tag = connection.materials_by_dof[dof]
            material = self.project.materials.get(material_tag)
            name = material.name if material is not None else "missing"
            chain = describe_material_chain(
                material_tag,
                self.project.materials,
            )
            chain_text = " → ".join(
                item.material_type for item in chain
            )
            suffix = f" [{chain_text}]" if len(chain) > 1 else ""
            material_text.append(
                f"{dof_labels[dof - 1]} → {material_tag} - {name}{suffix}"
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
            (
                "Section",
                (
                    f"{connection.section_tag} - "
                    f"{self.project.sections[connection.section_tag].name}"
                    if (
                        connection.section_tag is not None
                        and connection.section_tag in self.project.sections
                    )
                    else (
                        str(connection.section_tag)
                        if connection.section_tag is not None
                        else "-"
                    )
                ),
            ),
            ("DOF materials", "; ".join(material_text) or "-"),
            ("Rayleigh", "Yes" if connection.do_rayleigh else "No"),
            ("Local X", connection.orient_x),
            ("Local Y", connection.orient_y),
        ]
        self.properties_panel.set_properties("Connection", rows)

    def _create_constraint(self) -> None:
        if not self._ensure_node_count(
            2,
            title="Constraint Editor",
        ):
            return
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

    def _ensure_first_mode_modal_prerequisite(
        self,
        template_kind: str,
    ) -> bool:
        for job_id in sorted(self._jobs, reverse=True):
            job = self._jobs[job_id]
            if job.analysis_type == "Modal" and job.results:
                return True

        modal_tags = sorted(
            tag
            for tag, analysis in self.project.analyses.items()
            if analysis.analysis_type == "Modal"
        )
        if not modal_tags:
            if not self._ask_create_prerequisite(
                title=f"{template_kind} · First-mode Loading",
                message=(
                    "First-mode proportional loading requires a completed "
                    "Modal analysis first. Create the Modal analysis now?"
                ),
                action_label="Create Modal Analysis Now...",
            ):
                return False
            self._create_analysis_template("Modal")
            modal_tags = sorted(
                tag
                for tag, analysis in self.project.analyses.items()
                if analysis.analysis_type == "Modal"
            )
            if not modal_tags:
                return False

        modal_tag = modal_tags[-1]
        if self._latest_job_for_analysis(modal_tag) is not None:
            return True

        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            self.status_message.setText(
                "First-mode loading is waiting for a completed Modal result."
            )
            return False

        modal = self.project.analyses[modal_tag]
        if self._ask_create_prerequisite(
            title=f"{template_kind} · First-mode Loading",
            message=(
                f"Modal analysis '{modal.name}' exists but has not been "
                "completed. Run it now?"
            ),
            action_label="Run Modal Analysis Now...",
        ):
            self._run_analysis_from_tree(modal_tag)
        return False

    def _first_mode_lateral_weights(
        self,
        *,
        mode: int,
        dof: int,
        control_node: int,
    ) -> dict[int, float]:
        mode = int(mode)
        dof = int(dof)
        latest_modal = None
        for job_id in sorted(self._jobs, reverse=True):
            job = self._jobs[job_id]
            if job.analysis_type == "Modal" and job.results:
                latest_modal = job
                break
        if latest_modal is None:
            raise ValueError(
                "First-mode proportional loading needs a completed Modal "
                "analysis. Run Modal analysis first, then reopen the "
                "Pushover template."
            )

        modes = latest_modal.results.get("modes", {})
        mode_data = (
            modes.get(str(mode), modes.get(mode))
            if isinstance(modes, dict)
            else None
        )
        if not isinstance(mode_data, dict):
            raise ValueError(
                f"Modal Job {latest_modal.job_id} has no mode {mode}."
            )
        vectors = mode_data.get("vectors", {})
        if not isinstance(vectors, dict):
            raise ValueError("Modal result does not contain nodal vectors.")

        component_index = dof - 1
        control_vector = vectors.get(
            str(int(control_node)),
            vectors.get(int(control_node)),
        )
        control_value = 0.0
        if isinstance(control_vector, (list, tuple)) and len(control_vector) > component_index:
            control_value = float(control_vector[component_index])

        sign = 1.0
        if abs(control_value) > 1.0e-15:
            sign = 1.0 if control_value >= 0.0 else -1.0
        else:
            for vector in vectors.values():
                if (
                    isinstance(vector, (list, tuple))
                    and len(vector) > component_index
                    and abs(float(vector[component_index])) > 1.0e-15
                ):
                    sign = (
                        1.0
                        if float(vector[component_index]) >= 0.0
                        else -1.0
                    )
                    break

        nodal_mass_available = any(
            len(node.mass) > component_index
            and float(node.mass[component_index]) > 0.0
            for node in self.model.nodes.values()
        )
        weights: dict[int, float] = {}
        for tag, node in self.model.nodes.items():
            vector = vectors.get(str(tag), vectors.get(tag))
            if not isinstance(vector, (list, tuple)):
                continue
            if len(vector) <= component_index:
                continue
            phi = sign * float(vector[component_index])
            if abs(phi) <= 1.0e-15:
                continue
            if nodal_mass_available:
                mass = (
                    float(node.mass[component_index])
                    if len(node.mass) > component_index
                    else 0.0
                )
                value = mass * phi
            else:
                value = phi
            if abs(value) > 1.0e-15:
                weights[int(tag)] = value

        if not weights:
            raise ValueError(
                f"Mode {mode} has no usable DOF {dof} participation."
            )
        return weights

    def _offer_structural_model_creator(self) -> bool:
        if self.model.nodes:
            return True

        box = QMessageBox(self)
        box.setWindowTitle("Structural Model Required")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "This workflow needs a structural model first. "
            "Choose a model-creation workflow to open now."
        )
        column_button = box.addButton(
            "1D Column...",
            QMessageBox.ButtonRole.ActionRole,
        )
        frame_button = box.addButton(
            "2D Frame...",
            QMessageBox.ButtonRole.ActionRole,
        )
        node_button = box.addButton(
            "Create Node...",
            QMessageBox.ButtonRole.ActionRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked is column_button:
            self._show_test_column_wizard()
        elif clicked is frame_button:
            self._show_frame_grid_2d()
        elif clicked is node_button:
            self._create_node()
        else:
            return False
        return bool(self.model.nodes)

    def _create_analysis_template(
        self,
        initial_template: str = "Pushover",
    ) -> None:
        if not self._offer_structural_model_creator():
            return

        default_node = default_control_node(self.project)
        try:
            dialog = AnalysisTemplateDialog(
                default_node=default_node,
                units=self.project.units,
                initial_template=str(initial_template),
                project=self.project,
                parent=self,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Analysis Template",
                (
                    "The analysis template dialog could not be opened.\n\n"
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            return
        if not dialog.exec():
            return

        try:
            request = dialog.request()
            kind = str(request["template"])
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Analysis Template", str(exc))
            return

        if (
            kind in {"Pushover", "Cyclic"}
            and request["driver_pattern_tag"] is None
            and str(request["distribution"]) == "First-mode proportional"
            and not self._ensure_first_mode_modal_prerequisite(kind)
        ):
            return

        before = self.project.to_dict()
        try:
            raw_mass_source = request.get("mass_source")
            if isinstance(raw_mass_source, dict):
                source = MassSourceData.from_dict(
                    dict(raw_mass_source)
                )
                if source.tag in self.project.mass_sources:
                    self.project.update_mass_source(
                        source.tag,
                        source,
                    )
                else:
                    self.project.add_mass_source(source)
                mass_summary = apply_mass_source(
                    self.project,
                    source,
                )
                if mass_summary.total_mass <= 1.0e-15:
                    raise ValueError(
                        "The configured Mass Source generated zero nodal "
                        "mass. Check material density and selected load "
                        "patterns/factors."
                    )

            if kind == "Modal":
                plan = build_modal_template(
                    self.project,
                    name=str(request["name"]),
                    num_modes=int(request["num_modes"]),
                    eigen_solver=str(request["eigen_solver"]),
                    require_nodal_mass=bool(
                        request["require_nodal_mass"]
                    ),
                )
            elif kind == "Pushover":
                distribution = str(request["distribution"])
                distribution_weights = request.get("custom_weights")
                if (
                    request["driver_pattern_tag"] is None
                    and distribution == "First-mode proportional"
                ):
                    distribution_weights = self._first_mode_lateral_weights(
                        mode=int(request["mode_number"]),
                        dof=int(request["control_dof"]),
                        control_node=int(request["control_node"]),
                    )
                plan = build_pushover_template(
                    self.project,
                    name=str(request["name"]),
                    control_node=int(request["control_node"]),
                    control_dof=int(request["control_dof"]),
                    target_displacement=float(
                        request["target_displacement"]
                    ),
                    max_increment=float(request["max_increment"]),
                    distribution=distribution,
                    distribution_weights=(
                        dict(distribution_weights)
                        if isinstance(distribution_weights, dict)
                        else None
                    ),
                    height_axis=int(request["height_axis"]),
                    driver_pattern_tag=(
                        int(request["driver_pattern_tag"])
                        if request["driver_pattern_tag"] is not None
                        else None
                    ),
                    preload_gravity=bool(request["preload_gravity"]),
                    gravity_steps=int(request["gravity_steps"]),
                    solver_preset=str(request["solver_preset"]),
                )
            elif kind == "Cyclic":
                distribution = str(request["distribution"])
                distribution_weights = request.get("custom_weights")
                if (
                    request["driver_pattern_tag"] is None
                    and distribution == "First-mode proportional"
                ):
                    distribution_weights = self._first_mode_lateral_weights(
                        mode=int(request["mode_number"]),
                        dof=int(request["control_dof"]),
                        control_node=int(request["control_node"]),
                    )
                plan = build_cyclic_template(
                    self.project,
                    name=str(request["name"]),
                    control_node=int(request["control_node"]),
                    control_dof=int(request["control_dof"]),
                    protocol_targets=list(request["protocol_targets"]),
                    max_increment=float(request["max_increment"]),
                    distribution=distribution,
                    distribution_weights=(
                        dict(distribution_weights)
                        if isinstance(distribution_weights, dict)
                        else None
                    ),
                    height_axis=int(request["height_axis"]),
                    driver_pattern_tag=(
                        int(request["driver_pattern_tag"])
                        if request["driver_pattern_tag"] is not None
                        else None
                    ),
                    preload_gravity=bool(request["preload_gravity"]),
                    gravity_steps=int(request["gravity_steps"]),
                    finish_at_zero=bool(request["finish_at_zero"]),
                    solver_preset=str(request["solver_preset"]),
                )
            else:
                components = [
                    GroundMotionComponentSpec(
                        direction=int(item["direction"]),
                        values=[
                            float(value)
                            for value in item["values"]
                        ],
                        scale_factor=float(item["scale_factor"]),
                        name={1: "X", 2: "Y", 3: "Z"}[
                            int(item["direction"])
                        ],
                    )
                    for item in request["components"]
                ]
                plan = build_nlth_multi_template(
                    self.project,
                    name=str(request["name"]),
                    components=components,
                    dt=float(request["dt"]),
                    input_unit=str(request["input_unit"]),
                    monitor_node=int(request["monitor_node"]),
                    monitor_dof=int(request["monitor_dof"]),
                    damping_ratio=float(request["damping_ratio"]),
                    damping_mode_i=int(request["damping_mode_i"]),
                    damping_mode_j=int(request["damping_mode_j"]),
                    preload_gravity=bool(request["preload_gravity"]),
                    gravity_steps=int(request["gravity_steps"]),
                    require_nodal_mass=bool(
                        request["require_nodal_mass"]
                    ),
                    solver_preset=str(request["solver_preset"]),
                )

            for series in plan.time_series:
                self.project.add_time_series(series)
            for pattern in plan.load_patterns:
                self.project.add_load_pattern(pattern)
            for load in plan.nodal_loads:
                self.project.add_nodal_load(load)
            self.project.add_analysis(plan.analysis)
            for result in plan.results:
                self.project.add_solution_result(result)
            self.project.set_active_analysis(plan.analysis.tag)
        except (TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Analysis Template", str(exc))
            self._refresh_all()
            return

        self._refresh_project_metadata(
            f"Created {plan.summary}"
        )
        self._record_project_change(
            f"Create {plan.analysis.analysis_type} template",
            before,
        )
        self._refresh_tree()
        self._select_tree_payload("analysis", plan.analysis.tag)
        self._show_analysis_properties(plan.analysis.tag)

    def _plain_pattern_choices(self) -> dict[int, str]:
        return {
            int(tag): pattern.name
            for tag, pattern in self.project.load_patterns.items()
            if pattern.pattern_type == "Plain"
        }

    def _apply_analysis_driving_load(
        self,
        settings: AnalysisSettingsData,
        dialog: AnalysisDialog,
    ) -> None:
        """Ensure DisplacementControl analyses have a valid force driver."""
        needs_driver = (
            settings.analysis_type in {"Pushover", "Cyclic"}
            or (
                settings.analysis_type == "Static"
                and settings.integrator == "DisplacementControl"
            )
        )
        if not needs_driver:
            return

        config = dialog.driving_load_config()
        mode = str(config.get("mode", "auto"))
        if mode == "existing":
            pattern_tag = config.get("pattern_tag")
            if pattern_tag is None:
                raise ValueError(
                    "Choose an existing Plain driving load pattern."
                )
            pattern = self.project.load_patterns.get(int(pattern_tag))
            if pattern is None:
                raise ValueError(
                    f"Driving load pattern {pattern_tag} does not exist."
                )
            if pattern.pattern_type != "Plain":
                raise ValueError(
                    "DisplacementControl driving load must be a Plain pattern."
                )
            settings.deferred_pattern_tags = [int(pattern_tag)]
            return

        if mode != "auto":
            raise ValueError(f"Unsupported driving-load mode: {mode}")

        distribution = str(
            config.get(
                "distribution",
                "Triangular"
                if settings.analysis_type == "Pushover"
                else "Uniform",
            )
        )
        height_axis = 2 if self.model.ndm == 2 else 3
        series, patterns, loads = build_reference_lateral_loading(
            self.project,
            dof=settings.control_dof,
            distribution=distribution,
            prefix=(
                "Static DC"
                if settings.analysis_type == "Static"
                else settings.analysis_type
            ),
            height_axis=height_axis,
        )
        for item in series:
            self.project.add_time_series(item)
        for item in patterns:
            self.project.add_load_pattern(item)
        for item in loads:
            self.project.add_nodal_load(item)
        settings.deferred_pattern_tags = [patterns[0].tag]

    def _create_analysis(self) -> None:
        self._create_analysis_of_type(None)

    def _has_dynamic_mass(self) -> bool:
        translational_count = min(
            int(self.model.ndm),
            int(self.model.ndf),
            3,
        )
        for node in self.model.nodes.values():
            for index in range(translational_count):
                if (
                    index < len(node.fixity)
                    and not bool(node.fixity[index])
                    and index < len(node.mass)
                    and float(node.mass[index]) > 0.0
                ):
                    return True

        for element in self.model.elements.values():
            has_element_mass = float(element.mass_per_length) > 0.0
            if element.element_type in SHELL_ELEMENT_TYPES:
                section = self.project.sections.get(
                    int(element.section_tag)
                    if element.section_tag is not None
                    else -1
                )
                shell_has_mass = False
                if (
                    section is not None
                    and section.section_type == "ElasticMembranePlate"
                ):
                    shell_has_mass = (
                        float(section.parameters.get("rho", 0.0)) > 0.0
                    )
                elif (
                    section is not None
                    and section.section_type == "PlateFiber"
                    and section.nd_material_tag is not None
                ):
                    material = self.project.nd_materials.get(
                        int(section.nd_material_tag)
                    )
                    shell_has_mass = bool(
                        material is not None
                        and float(
                            material.parameters.get("rho", 0.0)
                        ) > 0.0
                    )
                elif (
                    section is not None
                    and section.section_type == "LayeredShell"
                ):
                    shell_has_mass = any(
                        (
                            self.project.nd_materials.get(
                                int(layer.material_tag)
                            ) is not None
                            and float(
                                self.project.nd_materials[
                                    int(layer.material_tag)
                                ].parameters.get("rho", 0.0)
                            ) > 0.0
                        )
                        for layer in section.shell_layers
                    )
                has_element_mass = (
                    has_element_mass or shell_has_mass
                )
            if not has_element_mass:
                continue
            for node_tag in element.node_tags():
                node = self.model.nodes.get(int(node_tag))
                if node is None:
                    continue
                if any(
                    index < len(node.fixity)
                    and not bool(node.fixity[index])
                    for index in range(translational_count)
                ):
                    return True
        return False

    def _ensure_dynamic_mass(self, *, title: str) -> bool:
        return self._ensure_prerequisite(
            title=title,
            message=(
                "Modal and Transient analyses require positive dynamic mass "
                "on at least one free translational DOF. Create/apply a "
                "Mass Source now?"
            ),
            action_label="Create Mass Source Now...",
            available=self._has_dynamic_mass,
            creator=self._create_mass_source,
        )

    def _create_analysis_of_type(
        self,
        analysis_type: str | None,
    ) -> None:
        default_node = min(self.model.nodes, default=1)
        dialog = AnalysisDialog(
            next_tag=self.project.next_analysis_tag(),
            default_node=default_node,
            analysis_type=analysis_type,
            ndf=self.model.ndf,
            plain_patterns=self._plain_pattern_choices(),
            parent=self,
        )
        if not dialog.exec():
            return
        before = self.project.to_dict()
        try:
            settings = dialog.data()
            uses_control_node = (
                settings.analysis_type in {"Pushover", "Cyclic"}
                or (
                    settings.analysis_type == "Static"
                    and settings.integrator == "DisplacementControl"
                )
            )
            if (
                uses_control_node
                and settings.control_node not in self.model.nodes
                and not self.model.nodes
            ):
                if not self._ensure_node_count(
                    1,
                    title="Analysis Settings",
                ):
                    return
                settings.control_node = min(self.model.nodes)
            if (
                settings.analysis_type in {"Modal", "Transient"}
                and not self._ensure_dynamic_mass(
                    title="Analysis Settings",
                )
            ):
                return
            self._apply_analysis_driving_load(settings, dialog)
            self.project.add_analysis(settings)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Analysis Settings", str(exc))
            self._refresh_all()
            return
        self._refresh_project_metadata(f"Created analysis {settings.tag}")
        self._show_analysis_properties(settings.tag)
        self._record_project_change(f"Create analysis {settings.tag}", before)

    def _edit_analysis(self, tag: int) -> None:
        settings = self.project.analyses.get(tag)
        if settings is None:
            return
        dialog = AnalysisDialog(
            analysis=settings,
            ndf=self.model.ndf,
            plain_patterns=self._plain_pattern_choices(),
            parent=self,
        )
        if not dialog.exec():
            return
        try:
            updated = dialog.data()
        except ValueError as exc:
            QMessageBox.warning(self, "Analysis Settings", str(exc))
            return

        if (
            updated.analysis_type in {"Modal", "Transient"}
            and not self._ensure_dynamic_mass(
                title="Analysis Settings",
            )
        ):
            return

        before = self.project.to_dict()
        try:
            self._apply_analysis_driving_load(updated, dialog)
            self.project.update_analysis(tag, updated)
        except ValueError as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(self, "Analysis Settings", str(exc))
            self._refresh_all()
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
        prepared = self._prepare_solution_result_prerequisites(
            result_type,
        )
        if prepared is None:
            return
        node_scope, element_scope = prepared

        if int(analysis_tag) not in self.project.analyses:
            self.status_message.setText(
                "The original analysis no longer exists after creating "
                "the prerequisite model object."
            )
            return

        before = self.project.to_dict()
        result = SolutionResultData(
            tag=self.project.next_solution_result_tag(),
            analysis_tag=int(analysis_tag),
            name=str(name),
            result_type=str(result_type),
            node_scope=sorted(node_scope),
            element_scope=sorted(element_scope),
            settings=dict(settings or {}),
        )
        try:
            self.project.add_solution_result(result)
        except ValueError as exc:
            QMessageBox.warning(self, "Result Request", str(exc))
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
        answer = QMessageBox.question(
            self,
            "Delete Result",
            (
                f"Delete result request '{result.name}'?\n\n"
                "This removes the result object from the Model Tree. "
                "Solver Job data is not deleted."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        before = self.project.to_dict()
        self.project.remove_solution_result(tag)
        if self._active_solution_result_tag == int(tag):
            self._active_solution_result_tag = None
        self._record_project_change(
            f"Delete solution result {result.name}",
            before,
        )
        if hasattr(self, "results_panel"):
            self.results_panel.stop_motion()
        self.viewport.clear_result_overlay()
        self._refresh_tree()
        self.status_message.setText(
            f"Deleted result: {result.name}"
        )

    def _delete_all_solution_results(self, analysis_tag: int) -> None:
        results = self.project.solution_results_for_analysis(analysis_tag)
        if not results:
            self.status_message.setText(
                "There are no result requests to delete."
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete All Result Requests",
            (
                f"Delete all {len(results)} result object(s) from this "
                "Result Requests?\n\n"
                "Solver Job data is not deleted."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        tags = {result.tag for result in results}
        before = self.project.to_dict()
        for result in results:
            self.project.remove_solution_result(result.tag)
        if self._active_solution_result_tag in tags:
            self._active_solution_result_tag = None
        self._record_project_change(
            f"Delete all solution results for analysis {analysis_tag}",
            before,
        )
        if hasattr(self, "results_panel"):
            self.results_panel.stop_motion()
        self.viewport.clear_result_overlay()
        self._refresh_tree()
        self.status_message.setText(
            f"Deleted {len(results)} result request(s)"
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
                f"Result request tag {tag} does not exist."
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
                "Result Request",
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
                "Result Request",
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

    def _offer_result_analysis_run(
        self,
        *,
        title: str,
        analysis_tag: int | None = None,
    ) -> bool:
        if not self.model.nodes:
            if not self._offer_structural_model_creator():
                return False

        target_tag = (
            int(analysis_tag)
            if analysis_tag is not None
            else self.project.active_analysis_tag
        )
        settings = self.project.analyses.get(target_tag)
        if settings is None:
            if not self._ensure_prerequisite(
                title=title,
                message=(
                    "This result workflow requires Analysis Settings first. "
                    "Create them now?"
                ),
                action_label="Create Analysis Settings Now...",
                available=lambda: (
                    self.project.analyses.get(
                        self.project.active_analysis_tag
                    )
                    is not None
                ),
                creator=self._create_analysis,
            ):
                return False
            target_tag = self.project.active_analysis_tag
            settings = self.project.analyses.get(target_tag)
            if settings is None:
                return False

        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            self.status_message.setText(
                f"{title}: analysis is already running; "
                "open the result again when it completes."
            )
            return False

        if not self._ask_create_prerequisite(
            title=title,
            message=(
                f"{title} requires a completed result from "
                f"'{settings.name}'. Run that analysis now?"
            ),
            action_label="Run Analysis Now...",
        ):
            return False

        self._run_analysis_from_tree(int(settings.tag))
        return True

    def _load_analysis_result(
        self,
        analysis_tag: int,
    ) -> dict[str, object] | None:
        job = self._latest_job_for_analysis(analysis_tag)
        if job is None:
            self._offer_result_analysis_run(
                title="Evaluate Result",
                analysis_tag=analysis_tag,
            )
            return None
        result = dict(job.results)
        self._last_result = result
        self._last_result_cache_key = ("job", job.job_id)
        self.results_panel.set_result(
            result,
            cache_key=self._last_result_cache_key,
        )
        return result

    def _show_solution_convergence(self, analysis_tag: int) -> None:
        result = self._load_analysis_result(analysis_tag)
        if result is None:
            return
        self.results_panel.show_solution_result("Convergence", {})
        if not self.results_dock.isVisible():
            self.results_dock.show()
            self.results_dock.raise_()

    def _evaluate_solution_result(self, tag: int) -> None:
        result_object = self.project.solution_results.get(int(tag))
        if result_object is None:
            return
        result = self._load_analysis_result(result_object.analysis_tag)
        if result is None:
            return

        source_job = self._latest_job_for_analysis(
            result_object.analysis_tag
        )
        self._render_result_data(
            result,
            result_object.result_type,
            dict(result_object.settings),
            node_scope=set(result_object.node_scope),
            element_scope=set(result_object.element_scope),
            restore_scope_selection=True,
            result_cache_key=(
                ("job", source_job.job_id)
                if source_job is not None
                else None
            ),
        )
        self.status_message.setText(
            f"Evaluated result: {result_object.name}"
        )
        self._show_solution_result_properties(result_object.tag)

    def _evaluate_all_solution_results(self, analysis_tag: int) -> None:
        objects = self.project.solution_results_for_analysis(analysis_tag)
        if not objects:
            self.status_message.setText(
                "There are no result requests to evaluate."
            )
            return
        if self._latest_job_for_analysis(analysis_tag) is None:
            self._offer_result_analysis_run(
                title="Evaluate All Results",
                analysis_tag=analysis_tag,
            )
            return
        for result in objects:
            self._evaluate_solution_result(result.tag)
        self.status_message.setText(
            f"Evaluated {len(objects)} result request(s)"
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

    def _show_cyclic_protocol_properties(self, tag: int) -> None:
        settings = self.project.analyses.get(tag)
        if settings is None or settings.analysis_type != "Cyclic":
            return
        self.properties_panel.set_cyclic_protocol(settings)

    def _show_analysis_properties(self, tag: int) -> None:
        settings = self.project.analyses.get(tag)
        if settings is None:
            return
        rows = [
            ("Tag", settings.tag), ("Name", settings.name),
            ("Type", settings.analysis_type),
            ("Integrator", settings.integrator),
            ("Active", "Yes" if tag == self.project.active_analysis_tag else "No"),
            ("Constraints", settings.constraints_handler),
            ("Numberer", settings.numberer), ("System", settings.system),
            (
                "Gravity preload",
                (
                    f"On · {settings.gravity_steps} step(s)"
                    if settings.preload_gravity
                    else "Off"
                ),
            ),
            (
                "Driving pattern(s)",
                (
                    ", ".join(map(str, settings.deferred_pattern_tags))
                    if settings.deferred_pattern_tags
                    else "-"
                ),
            ),
        ]
        if settings.analysis_type == "Modal":
            rows.extend([
                ("Modes", settings.num_modes),
                ("Eigen solver", settings.eigen_solver),
            ])
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
                if settings.integrator == "LoadControl":
                    rows.append(
                        ("Load increment", f"{settings.load_increment:g}")
                    )
                elif settings.integrator == "DisplacementControl":
                    rows.extend([
                        ("Control node", settings.control_node),
                        ("Control DOF", settings.control_dof),
                        (
                            "Disp. increment",
                            f"{settings.displacement_increment:g}",
                        ),
                    ])
                elif settings.integrator == "ArcLength":
                    rows.extend([
                        ("ArcLength s", f"{settings.arc_length_s:g}"),
                        (
                            "ArcLength alpha",
                            f"{settings.arc_length_alpha:g}",
                        ),
                    ])
            elif settings.analysis_type == "Pushover":
                rows.extend([
                    ("Control node", settings.control_node),
                    ("Control DOF", settings.control_dof),
                    ("Disp. increment", f"{settings.displacement_increment:g}"),
                ])
            elif settings.analysis_type == "Transient":
                rows.append(("Time step", f"{settings.dt:g}"))
                if settings.integrator == "Newmark":
                    rows.extend([
                        ("Newmark gamma", f"{settings.gamma:g}"),
                        ("Newmark beta", f"{settings.beta:g}"),
                    ])
                elif settings.integrator == "HHT":
                    rows.append(
                        ("HHT alpha", f"{settings.hht_alpha:g}")
                    )
                elif settings.integrator == "GeneralizedAlpha":
                    rows.extend([
                        (
                            "Generalized-alpha alphaM",
                            f"{settings.generalized_alpha_m:g}",
                        ),
                        (
                            "Generalized-alpha alphaF",
                            f"{settings.generalized_alpha_f:g}",
                        ),
                    ])
                rows.extend([
                    (
                        "Rayleigh damping",
                        (
                            f"{settings.rayleigh_damping_ratio:g} "
                            f"(modes {settings.rayleigh_mode_i}, "
                            f"{settings.rayleigh_mode_j})"
                            if settings.rayleigh_damping_ratio > 0.0
                            else "Off"
                        ),
                    ),
                ])
            elif settings.analysis_type == "Cyclic":
                expanded = cyclic_displacement_steps(
                    settings.cyclic_targets,
                    settings.cyclic_increment,
                )
                rows.extend([
                    ("Control node", settings.control_node),
                    ("Control DOF", settings.control_dof),
                    ("Target count", len(settings.cyclic_targets)),
                    (
                        "Target min / max",
                        (
                            f"{min(settings.cyclic_targets):g} / "
                            f"{max(settings.cyclic_targets):g}"
                            if settings.cyclic_targets
                            else "-"
                        ),
                    ),
                    ("Max increment", f"{settings.cyclic_increment:g}"),
                    ("Expanded steps", len(expanded)),
                ])
        self.properties_panel.set_properties("Analysis Settings", rows)

    def _choose_existing_prerequisite_tag(
        self,
        *,
        title: str,
        label: str,
        tags: list[int],
    ) -> int | None:
        unique = sorted({int(tag) for tag in tags})
        if not unique:
            return None
        if len(unique) == 1:
            return unique[0]
        choice, ok = QInputDialog.getItem(
            self,
            title,
            label,
            [str(tag) for tag in unique],
            0,
            False,
        )
        if not ok:
            return None
        try:
            return int(choice)
        except (TypeError, ValueError):
            return None

    def _nonlinear_beam_tags(self) -> list[int]:
        return sorted(
            int(tag)
            for tag, element in self.model.elements.items()
            if element.element_type in {
                "forceBeamColumn",
                "dispBeamColumn",
            }
        )

    def _create_nonlinear_beam_prerequisite(self) -> None:
        self._create_frame()
        selected = [
            int(tag)
            for tag in sorted(self.selection.elements)
            if (
                tag in self.model.elements
                and self.model.elements[tag].element_type
                in {
                    "elasticBeamColumn",
                    "forceBeamColumn",
                    "dispBeamColumn",
                }
            )
        ]
        if not selected:
            return
        if any(
            self.model.elements[tag].element_type
            in {"forceBeamColumn", "dispBeamColumn"}
            for tag in selected
        ):
            return
        self._set_element_formulation()

    def _ensure_nonlinear_beam_target(
        self,
        *,
        title: str,
    ) -> int | None:
        selected = [
            int(tag)
            for tag in sorted(self.selection.elements)
            if tag in self._nonlinear_beam_tags()
        ]
        if selected:
            return selected[0]

        existing = self._nonlinear_beam_tags()
        if existing:
            tag = self._choose_existing_prerequisite_tag(
                title=title,
                label="Choose an existing nonlinear beam-column element:",
                tags=existing,
            )
            if tag is not None:
                self.selection.set_selection(elements={tag})
            return tag

        if not self._ensure_prerequisite(
            title=title,
            message=(
                f"{title} requires a forceBeamColumn or dispBeamColumn "
                "element. Create a frame and define its nonlinear "
                "formulation now?"
            ),
            action_label="Create Nonlinear Frame Now...",
            available=lambda: bool(self._nonlinear_beam_tags()),
            creator=self._create_nonlinear_beam_prerequisite,
        ):
            return None

        existing = self._nonlinear_beam_tags()
        if not existing:
            return None
        selected = [
            int(tag)
            for tag in sorted(self.selection.elements)
            if tag in existing
        ]
        tag = (
            selected[0]
            if selected
            else self._choose_existing_prerequisite_tag(
                title=title,
                label="Choose the nonlinear beam-column target:",
                tags=existing,
            )
        )
        if tag is not None:
            self.selection.set_selection(elements={tag})
        return tag

    def _element_uses_fiber_section(self, tag: int) -> bool:
        element = self.model.elements.get(int(tag))
        if element is None:
            return False
        section_tags = {
            value
            for value in (
                element.section_tag,
                element.hinge_i_section_tag,
                element.hinge_j_section_tag,
                element.interior_section_tag,
            )
            if value is not None
        }
        return any(
            section_tag in self.project.sections
            and self.project.sections[section_tag].section_type == "Fiber"
            for section_tag in section_tags
        )

    def _fiber_beam_tags(self) -> list[int]:
        return sorted(
            tag
            for tag in self._nonlinear_beam_tags()
            if self._element_uses_fiber_section(tag)
        )

    def _create_fiber_beam_prerequisite(self) -> None:
        if not any(
            section.section_type == "Fiber"
            for section in self.project.sections.values()
        ):
            if not self._ensure_prerequisite(
                title="Fiber Response Target",
                message=(
                    "Fiber response requires a Fiber Section. "
                    "Create one now?"
                ),
                action_label="Create Fiber Section Now...",
                available=lambda: any(
                    section.section_type == "Fiber"
                    for section in self.project.sections.values()
                ),
                creator=self._create_section,
            ):
                return
        self._create_nonlinear_beam_prerequisite()

    def _ensure_fiber_beam_target(
        self,
        *,
        title: str,
    ) -> int | None:
        existing = self._fiber_beam_tags()
        selected = [
            int(tag)
            for tag in sorted(self.selection.elements)
            if tag in existing
        ]
        if selected:
            return selected[0]

        if existing:
            tag = self._choose_existing_prerequisite_tag(
                title=title,
                label="Choose an existing Fiber-section beam-column element:",
                tags=existing,
            )
            if tag is not None:
                self.selection.set_selection(elements={tag})
            return tag

        if not self._ensure_prerequisite(
            title=title,
            message=(
                f"{title} requires a forceBeamColumn or dispBeamColumn "
                "element backed by a Fiber Section. Create that target now?"
            ),
            action_label="Create Fiber Beam Now...",
            available=lambda: bool(self._fiber_beam_tags()),
            creator=self._create_fiber_beam_prerequisite,
        ):
            return None

        existing = self._fiber_beam_tags()
        if not existing:
            return None
        tag = self._choose_existing_prerequisite_tag(
            title=title,
            label="Choose the Fiber-section beam-column target:",
            tags=existing,
        )
        if tag is not None:
            self.selection.set_selection(elements={tag})
        return tag

    def _recorder_target_creator(
        self,
        recorder_type: str,
    ) -> list[int]:
        kind = str(recorder_type)
        if kind == "Node":
            if not self.model.nodes:
                if not self._ensure_node_count(1, title="Node Recorder"):
                    return []
            selected = sorted(
                int(tag)
                for tag in self.selection.nodes
                if tag in self.model.nodes
            )
            if selected:
                return selected
            tag = self._choose_existing_prerequisite_tag(
                title="Node Recorder",
                label="Choose a node target:",
                tags=list(self.model.nodes),
            )
            return [tag] if tag is not None else []

        if kind == "Element":
            selected = sorted(
                int(tag)
                for tag in self.selection.elements
                if (
                    tag in self.model.elements
                    or tag in self.project.connections
                )
            )
            if selected:
                return selected
            existing = sorted(
                set(self.model.elements)
                | set(self.project.connections)
            )
            if not existing:
                if not self._ensure_prerequisite(
                    title="Element Recorder",
                    message=(
                        "Element Recorder requires an element target. "
                        "Create a Frame element now?"
                    ),
                    action_label="Create Frame Now...",
                    available=lambda: bool(
                        self.model.elements
                        or self.project.connections
                    ),
                    creator=self._create_frame,
                ):
                    return []
                existing = sorted(
                    set(self.model.elements)
                    | set(self.project.connections)
                )
            tag = self._choose_existing_prerequisite_tag(
                title="Element Recorder",
                label="Choose an element target:",
                tags=existing,
            )
            return [tag] if tag is not None else []

        if kind == "Shell":
            selected = sorted(
                int(tag)
                for tag in self.selection.elements
                if (
                    tag in self.model.elements
                    and self.model.elements[tag].element_type
                    in SHELL_ELEMENT_TYPES
                )
            )
            if selected:
                return selected
            existing = sorted(
                int(tag)
                for tag, element in self.model.elements.items()
                if element.element_type in SHELL_ELEMENT_TYPES
            )
            if not existing:
                if not self._ensure_prerequisite(
                    title="Shell Recorder",
                    message=(
                        "Shell Recorder requires meshed Shell elements. "
                        "Create one now?"
                    ),
                    action_label="Create & Mesh Surface Now...",
                    available=lambda: any(
                        element.element_type in SHELL_ELEMENT_TYPES
                        for element in self.model.elements.values()
                    ),
                    creator=self._create_surface_geometry_and_mesh,
                ):
                    return []
                existing = sorted(
                    int(tag)
                    for tag, element in self.model.elements.items()
                    if element.element_type in SHELL_ELEMENT_TYPES
                )
            tag = self._choose_existing_prerequisite_tag(
                title="Shell Recorder",
                label="Choose a Shell element target:",
                tags=existing,
            )
            return [tag] if tag is not None else []

        if kind == "Section":
            tag = self._ensure_nonlinear_beam_target(
                title="Section Recorder",
            )
            return [tag] if tag is not None else []

        if kind == "Fiber":
            tag = self._ensure_fiber_beam_target(
                title="Fiber Recorder",
            )
            return [tag] if tag is not None else []

        return []

    def _prepare_solution_result_prerequisites(
        self,
        result_type: str,
    ) -> tuple[set[int], set[int]] | None:
        kind = str(result_type)
        nodes = set(self.selection.nodes)
        elements = set(self.selection.elements)

        if kind in {"ShellForce", "ShellDeformation"}:
            shell_tags = sorted(
                int(tag)
                for tag, element in self.model.elements.items()
                if element.element_type in SHELL_ELEMENT_TYPES
            )
            if not shell_tags:
                if not self._ensure_prerequisite(
                    title="Shell Result",
                    message=(
                        "Shell Results require at least one meshed Shell "
                        "element. Create and mesh Surface Geometry now?"
                    ),
                    action_label="Create & Mesh Surface Now...",
                    available=lambda: any(
                        element.element_type in SHELL_ELEMENT_TYPES
                        for element in self.model.elements.values()
                    ),
                    creator=self._create_surface_geometry_and_mesh,
                ):
                    return None
                shell_tags = sorted(
                    int(tag)
                    for tag, element in self.model.elements.items()
                    if element.element_type in SHELL_ELEMENT_TYPES
                )
            if not shell_tags:
                return None
            selected_shells = {
                int(tag)
                for tag in elements
                if int(tag) in shell_tags
            }
            elements = selected_shells or set(shell_tags)

        elif kind == "MemberForce":
            frame_tags = sorted(
                int(tag)
                for tag, element in self.model.elements.items()
                if element.element_type in {
                    "elasticBeamColumn",
                    "forceBeamColumn",
                    "dispBeamColumn",
                }
            )
            if not frame_tags:
                if not self._ensure_prerequisite(
                    title="Member Force Result",
                    message=(
                        "Member Force requires a Frame element. "
                        "Create one now?"
                    ),
                    action_label="Create Frame Now...",
                    available=lambda: any(
                        element.element_type in {
                            "elasticBeamColumn",
                            "forceBeamColumn",
                            "dispBeamColumn",
                        }
                        for element in self.model.elements.values()
                    ),
                    creator=self._create_frame,
                ):
                    return None
                frame_tags = sorted(
                    int(tag)
                    for tag, element in self.model.elements.items()
                    if element.element_type in {
                        "elasticBeamColumn",
                        "forceBeamColumn",
                        "dispBeamColumn",
                    }
                )
            selected = [tag for tag in sorted(elements) if tag in frame_tags]
            if not selected:
                tag = self._choose_existing_prerequisite_tag(
                    title="Member Force Result",
                    label="Choose a Frame element for this result:",
                    tags=frame_tags,
                )
                if tag is None:
                    return None
                selected = [tag]
            elements = set(selected)

        elif kind == "SectionResponse":
            sources = section_response_sources(
                self.model,
                self.project.connections,
            )
            source_tags = sorted(
                int(item["element_tag"])
                for item in sources
            )
            selected = [
                tag for tag in sorted(elements)
                if tag in source_tags
            ]
            if not selected and not source_tags:
                tag = self._ensure_nonlinear_beam_target(
                    title="Section Response Result",
                )
                if tag is None:
                    return None
                source_tags = [tag]
                selected = [tag]
            if not selected:
                tag = self._choose_existing_prerequisite_tag(
                    title="Section Response Result",
                    label=(
                        "Choose a zeroLengthSection or nonlinear "
                        "beam-column target:"
                    ),
                    tags=source_tags,
                )
                if tag is None:
                    return None
                selected = [tag]
            elements = {selected[0]}

        elif kind in {"FiberStress", "FiberStrain", "HingeState"}:
            tag = self._ensure_fiber_beam_target(
                title={
                    "FiberStress": "Fiber Stress Result",
                    "FiberStrain": "Fiber Strain Result",
                    "HingeState": "Hinge / Yield State Result",
                }[kind],
            )
            if tag is None:
                return None
            elements = {tag}

        elif kind == "SpecimenResponse":
            specimen_tags = sorted(
                int(tag)
                for tag, element in self.model.elements.items()
                if str(element.group) == "test-column"
            )
            if not specimen_tags:
                if not self._ensure_prerequisite(
                    title="Specimen Response Result",
                    message=(
                        "Specimen Response requires a Quick 1D Column / "
                        "Test Specimen model. Open that wizard now?"
                    ),
                    action_label="Create 1D Column Now...",
                    available=lambda: any(
                        str(element.group) == "test-column"
                        for element in self.model.elements.values()
                    ),
                    creator=self._show_test_column_wizard,
                ):
                    return None
                specimen_tags = sorted(
                    int(tag)
                    for tag, element in self.model.elements.items()
                    if str(element.group) == "test-column"
                )
            if not specimen_tags:
                return None
            elements = set(specimen_tags)

        return nodes, elements

    def _create_recorder(self) -> None:
        if (
            not self.model.nodes
            and not self.model.elements
            and not self.project.connections
        ):
            if not self._ensure_node_count(
                1,
                title="Recorder",
            ):
                return
        initial_nodes = set(self.selection.nodes)
        initial_elements = set(self.selection.elements)
        dialog = RecorderDialog(
            next_tag=self.project.next_recorder_tag(),
            initial_node_tags=initial_nodes,
            initial_element_tags=initial_elements,
            target_creator=self._recorder_target_creator,
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
        if recorder.recorder_type == "Shell":
            rows.append(("Gauss point", recorder.section_number))
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
        if (
            not nodes
            and not elements
            and not self.model.nodes
            and not self.model.elements
        ):
            if not self._ensure_node_count(
                1,
                title="Named Selection",
            ):
                return
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
        integrator: str | None = None,
        section_response_available: bool | None = None,
    ) -> None:
        categories: dict[str, QMenu] = {}
        if section_response_available is None:
            section_response_available = bool(
                section_response_sources(
                    self.model,
                    self.project.connections,
                )
            )
        for choice in result_choices_for_analysis(
            analysis_type,
            convergence_test,
            integrator=integrator,
            section_response_available=bool(
                section_response_available
            ),
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

    def _plot_source_job(self) -> JobRecord | None:
        """Resolve the Job that the global Plot action should use."""
        item = self.tree.currentItem()
        if item is not None:
            payload = item.data(0, Qt.UserRole)
            if payload:
                kind, value = payload
                if kind == "job":
                    job = self._jobs.get(int(value))
                    if job is not None and job.results:
                        return job
                elif kind == "job_plot":
                    try:
                        job_id = int(value[0])
                    except (TypeError, ValueError, IndexError):
                        job_id = -1
                    job = self._jobs.get(job_id)
                    if job is not None and job.results:
                        return job
                elif kind == "solution_result":
                    result_object = self.project.solution_results.get(
                        int(value)
                    )
                    if result_object is not None:
                        job = self._latest_job_for_analysis(
                            result_object.analysis_tag
                        )
                        if job is not None:
                            return job
                elif kind in {
                    "analysis",
                    "analysis_settings",
                    "solution_root",
                    "solution_information",
                    "solution_convergence",
                    "solver_output",
                }:
                    try:
                        analysis_tag = int(value)
                    except (TypeError, ValueError):
                        analysis_tag = -1
                    job = self._latest_job_for_analysis(analysis_tag)
                    if job is not None:
                        return job

        if self._current_job_id is not None:
            current = self._jobs.get(int(self._current_job_id))
            if current is not None and current.results:
                return current

        for job_id in sorted(self._jobs, reverse=True):
            job = self._jobs[job_id]
            if job.results:
                return job
        return None

    def _show_plot_menu(self) -> None:
        """Open the same result catalog used by a Job's Plot submenu."""
        job = self._plot_source_job()
        if job is None:
            self._offer_result_analysis_run(title="Plot Results")
            self.results_panel.show_jobs()
            self.results_dock.show()
            self.results_dock.raise_()
            return

        menu = QMenu(self)
        source = menu.addAction(
            f"Job {job.job_id} · {job.analysis_name}"
        )
        source.setEnabled(False)
        menu.addSeparator()

        self._populate_result_choice_menu(
            menu,
            job.analysis_type,
            lambda result_type, name, settings:
            self._quick_plot_job_result(
                job.job_id,
                result_type,
                name,
                settings,
            ),
            convergence_test=self._job_convergence_test(job),
            integrator=str(
                job.results.get("analysis", {}).get("integrator", "")
            ) if isinstance(job.results.get("analysis", {}), dict) else None,
            section_response_available=bool(
                job.results.get("section_responses", {})
            ),
        )

        menu.addSeparator()
        manager = menu.addAction("Show Job Manager")
        manager.triggered.connect(
            lambda: (
                self.results_panel.show_jobs(),
                self.results_dock.show(),
                self.results_dock.raise_(),
            )
        )
        menu.exec(QCursor.pos())

    def _render_result_data(
        self,
        result: dict[str, object],
        result_type: str,
        settings: dict[str, object] | None = None,
        *,
        node_scope: set[int] | None = None,
        element_scope: set[int] | None = None,
        restore_scope_selection: bool = False,
        result_cache_key: object | None = None,
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
        self._last_result_cache_key = result_cache_key
        fit_action = self.actions.get("fit_result")
        if fit_action is not None:
            fit_action.setEnabled(True)
        self.results_panel.set_result(
            payload,
            cache_key=result_cache_key,
        )
        self.results_panel.show_solution_result(result_type, options)
        if result_type == "DeformedShape":
            self._sync_result_ribbon_controls(
                "deformation",
                str(options.get("display_mode", "deformed_only")),
                float(options.get("scale", 10.0)),
            )
        elif result_type == "ModeShape":
            self._sync_result_ribbon_controls(
                "mode",
                str(options.get("display_mode", "deformed_only")),
                float(options.get("scale", 1.0)),
            )
        else:
            self._active_result_display_kind = None
            self._set_result_display_controls_enabled(False)
        if not self.results_dock.isVisible():
            self.results_dock.show()
            self.results_dock.raise_()

        if restore_scope_selection:
            self.selection.set_selection(
                nodes=nodes,
                elements=elements,
            )

        if result_type == "DeformedShape":
            self.viewport.show_deformed_shape(
                payload,
                scale=float(options.get("scale", 10.0)),
                display_mode=str(
                    options.get("display_mode", "deformed_only")
                ),
                representation=str(
                    options.get("representation", "actual_section")
                ),
                smooth_curvature=bool(
                    options.get("smooth_curvature", True)
                ),
                node_tags=nodes or None,
                element_tags=elements or None,
                cache_key=result_cache_key,
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
                cache_key=result_cache_key,
            )
        elif result_type == "MemberForce":
            self.viewport.show_member_force_diagram(
                payload,
                self.project.transformations,
                str(options.get("component", "Mz")),
                scale=float(options.get("scale", 1.0)),
                element_tags=elements or None,
                cache_key=result_cache_key,
            )
        elif result_type == "ShellForce":
            self.viewport.show_shell_force_contour(
                payload,
                str(options.get("component", "Nxx")),
                element_tags=elements or None,
                cache_key=result_cache_key,
            )
        elif result_type == "ShellDeformation":
            self.viewport.show_shell_deformation_contour(
                payload,
                str(options.get("component", "Exx")),
                element_tags=elements or None,
                cache_key=result_cache_key,
            )
        elif result_type == "HingeState":
            self.viewport.show_hinge_states(
                payload,
                element_tags=elements or None,
                cache_key=result_cache_key,
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
                display_mode=str(
                    options.get("display_mode", "deformed_only")
                ),
                representation=str(
                    options.get("representation", "actual_section")
                ),
                smooth_curvature=bool(
                    options.get("smooth_curvature", True)
                ),
                node_tags=nodes or None,
                element_tags=elements or None,
                cache_key=result_cache_key,
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
                self.tree.clearSelection()
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
                ("Convergence test", self._job_convergence_test(job) or "-"),
                ("Plots", len(job.plots)),
                ("Result data", "Available" if job.results else "Not available"),
                ("Message", job.message or "-"),
            ],
        )

    def _offer_job_analysis_rerun(
        self,
        job_id: int,
        *,
        title: str,
    ) -> bool:
        job = self._jobs.get(int(job_id))
        if job is None:
            return False
        if job.results:
            return True
        if str(job.status) == "Running":
            self.status_message.setText(
                f"{title}: Job {job.job_id} is still running."
            )
            return False
        settings = self.project.analyses.get(int(job.analysis_tag))
        if settings is None:
            self.status_message.setText(
                f"{title}: analysis {job.analysis_tag} no longer exists."
            )
            return False
        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            self.status_message.setText(
                f"{title}: another analysis is currently running."
            )
            return False
        if not self._ask_create_prerequisite(
            title=title,
            message=(
                f"Job {job.job_id} has no captured result data. "
                f"Rerun '{settings.name}' now?"
            ),
            action_label="Run Analysis Again...",
        ):
            return False
        self._run_analysis_from_tree(int(settings.tag))
        return False

    def _activate_job_result(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        if not job.results:
            self._offer_job_analysis_rerun(
                job_id,
                title="Activate Job Result",
            )
            return
        self._last_result = dict(job.results)
        self._last_result_cache_key = ("job", job.job_id)
        self.results_panel.set_result(
            self._last_result,
            cache_key=self._last_result_cache_key,
        )
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
        if job is None:
            return
        if not job.results:
            self._offer_job_analysis_rerun(
                job_id,
                title="Show Job Plot",
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
            result_cache_key=("job", job.job_id),
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
        answer = QMessageBox.question(
            self,
            "Delete Result",
            (
                f"Delete result view '{name}' from Job {job.job_id}?\n\n"
                "The underlying solver data for the Job is kept."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        job.remove_plot(plot_id)
        if hasattr(self, "results_panel"):
            self.results_panel.stop_motion()
        self.viewport.clear_result_overlay()
        self._refresh_tree()
        self.status_message.setText(
            f"Deleted Job {job.job_id} result: {name}"
        )

    def _rebuild_results_panel_jobs(self) -> None:
        self.results_panel.clear_all()
        for job_id in sorted(self._jobs):
            self.results_panel.add_or_update_job(self._jobs[job_id])

    def _delete_job(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
            and self._current_job_id == int(job_id)
        ):
            QMessageBox.information(
                self,
                "Delete Job",
                "Stop the running analysis before deleting this Job.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Job",
            (
                f"Delete Job {job.job_id} and its saved result views?\n\n"
                "This removes the runtime solver results for this Job."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._jobs.pop(job.job_id, None)
        if self._current_job_id == job.job_id:
            self._current_job_id = None
        if self._last_result_cache_key == ("job", job.job_id):
            self._last_result = {}
            self._last_result_cache_key = None
        if hasattr(self, "results_panel"):
            self.results_panel.stop_motion()
        self.viewport.clear_result_overlay()
        self._rebuild_results_panel_jobs()
        self._refresh_tree()
        self.status_message.setText(f"Deleted Job {job.job_id}")

    def _delete_all_jobs(self) -> None:
        if not self._jobs:
            self.status_message.setText("There are no Jobs to delete.")
            return
        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(
                self,
                "Delete All Jobs",
                "Stop the running analysis before deleting Jobs.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete All Jobs",
            (
                f"Delete all {len(self._jobs)} runtime Jobs and their "
                "saved result views?\n\n"
                "Result request definitions under each Analysis are kept."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        count = len(self._jobs)
        self._jobs.clear()
        self._current_job_id = None
        self._last_result = {}
        self._last_result_cache_key = None
        if hasattr(self, "results_panel"):
            self.results_panel.clear_all()
        self.viewport.clear_result_overlay()
        self._refresh_tree()
        self.status_message.setText(f"Deleted {count} Job(s)")

    def _quick_plot_job_result(
        self,
        job_id: int,
        result_type: str,
        name: str,
        settings: dict[str, object],
    ) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        if not job.results:
            self._offer_job_analysis_rerun(
                job_id,
                title="Plot Job Result",
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

    def _export_active_job_results(self) -> None:
        job_id: int | None = None
        cache_key = self._last_result_cache_key
        if (
            isinstance(cache_key, tuple)
            and len(cache_key) == 2
            and cache_key[0] == "job"
        ):
            try:
                job_id = int(cache_key[1])
            except (TypeError, ValueError):
                job_id = None
        if job_id is None and self._jobs:
            completed = [
                job.job_id
                for job in self._jobs.values()
                if job.results
            ]
            if completed:
                job_id = max(completed)
        if job_id is None:
            self._offer_result_analysis_run(
                title="Export Job Results",
            )
            return
        self._export_job_result_json(job_id)

    def _export_job_result_json(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        if not job.results:
            self._offer_job_analysis_rerun(
                job_id,
                title="Export Job Results",
            )
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

    def _select_all_tree_nodes(self) -> None:
        self.selection.set_selection(nodes=set(self.model.nodes))

    def _select_all_tree_elements(
        self,
        element_type: str | None = None,
    ) -> None:
        tags = {
            tag
            for tag, element in self.model.elements.items()
            if element_type is None
            or element.element_type == str(element_type)
        }
        self.selection.set_selection(elements=tags)

    def _select_boundary_group(self, support_type: str) -> None:
        tags = {
            tag
            for tag, node in self.model.nodes.items()
            if any(node.fixity)
            and classify_fixity(node.fixity) == str(support_type)
        }
        self.selection.set_selection(nodes=tags)

    def _run_analysis_from_tree(self, tag: int) -> None:
        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            return
        if int(tag) != self.project.active_analysis_tag:
            self._set_active_analysis(int(tag))
        self._start_analysis()

    def _rename_job_plot(self, job_id: int, plot_id: int) -> None:
        job = self._jobs.get(int(job_id))
        plot = job.plot(plot_id) if job is not None else None
        if job is None or plot is None:
            return
        old_name = str(plot.get("name", f"Result {plot_id}"))
        name, ok = QInputDialog.getText(
            self,
            "Rename Result",
            "Name:",
            text=old_name,
        )
        name = name.strip()
        if not ok or not name or name == old_name:
            return
        existing = {
            str(item.get("name", ""))
            for item in job.plots
            if isinstance(item, dict)
            and int(item.get("plot_id", 0) or 0) != int(plot_id)
        }
        if name in existing:
            QMessageBox.warning(
                self,
                "Rename Result",
                f"A result named '{name}' already exists under this Job.",
            )
            return
        plot["name"] = name
        self._refresh_tree()
        self._select_tree_payload("job_plot", (job.job_id, int(plot_id)))
        self.status_message.setText(
            f"Job {job.job_id} · renamed result to {name}"
        )

    def _duplicate_job_plot(self, job_id: int, plot_id: int) -> None:
        job = self._jobs.get(int(job_id))
        plot = job.plot(plot_id) if job is not None else None
        if job is None or plot is None:
            return
        duplicate = job.add_plot(
            name=f"{plot.get('name', f'Result {plot_id}')} Copy",
            result_type=str(plot.get("result_type", "")),
            settings=dict(plot.get("settings", {})),
            node_scope=list(plot.get("node_scope", [])),
            element_scope=list(plot.get("element_scope", [])),
        )
        new_plot_id = int(duplicate["plot_id"])
        self._refresh_tree()
        self._select_tree_payload(
            "job_plot",
            (job.job_id, new_plot_id),
        )
        self._show_job_plot(job.job_id, new_plot_id)
        self.status_message.setText(
            f"Job {job.job_id} · duplicated result: {duplicate['name']}"
        )

    def _populate_materials_root_context_menu(
        self,
        menu: QMenu,
    ) -> None:
        create_action = menu.addAction("New Material...")
        create_action.triggered.connect(self._create_material)
        library_action = menu.addAction(
            "Insert from Material Library..."
        )
        library_action.triggered.connect(self._show_material_library)

    def _append_tree_ai_action(
        self,
        menu: QMenu,
        kind: str,
        value: object,
    ) -> None:
        actions = menu.actions()
        if actions and not actions[-1].isSeparator():
            menu.addSeparator()
        ask_ai = menu.addAction("Ask AI about this")
        ask_ai.setIcon(studio_icon("analysis"))
        ask_ai.triggered.connect(
            lambda checked=False, k=str(kind), v=value:
            self._ask_ai_about_tree_item(k, v)
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

        def exec_menu() -> None:
            # Creation/editing commands are the primary tree workflow.
            # AI help is deliberately appended last so it never displaces
            # direct modeling commands.
            self._append_tree_ai_action(menu, str(kind), value)
            menu.exec(self.tree.viewport().mapToGlobal(position))

        if kind == "model_root":
            menu.addAction(self.actions["check_model"])
            menu.addAction(self.actions["run"])
            menu.addSeparator()
            show_all = menu.addAction("Show All")
            show_all.triggered.connect(self._show_all)
            exec_menu()
            return

        if kind == "geometry_root":
            surface_action = menu.addAction("New Surface...")
            surface_action.triggered.connect(self._create_surface_geometry)
            menu.addSeparator()
            quick_column = menu.addAction("Generate 1D Test Specimen...")
            quick_column.triggered.connect(self._show_test_column_wizard)
            quick_2d = menu.addAction("Generate 2D Frame...")
            quick_2d.triggered.connect(self._show_frame_grid_2d)
            grid_action = menu.addAction("Generate 3D Frame Grid...")
            grid_action.triggered.connect(self._show_frame_grid)
            exec_menu()
            return

        if kind == "fe_model_root":
            node_action = menu.addAction("New Node...")
            node_action.triggered.connect(self._create_node)
            frame_action = menu.addAction("New Frame...")
            frame_action.triggered.connect(self._create_element)
            truss_action = menu.addAction("New Truss...")
            truss_action.triggered.connect(self._create_truss)
            shell_action = menu.addAction("New Direct Shell Element...")
            shell_action.triggered.connect(self._create_shell)
            connection_action = menu.addAction(
                "New ZeroLength / Link Element..."
            )
            connection_action.triggered.connect(self._create_connection)
            exec_menu()
            return

        if kind == "nodes_root":
            create = menu.addAction("New Node...")
            create.triggered.connect(self._create_node)
            select_all = menu.addAction("Select All Nodes")
            select_all.setEnabled(bool(self.model.nodes))
            select_all.triggered.connect(self._select_all_tree_nodes)
            menu.addSeparator()
            menu.addAction(self.actions["show_node_numbers"])
            exec_menu()
            return

        if kind == "surfaces_root":
            create_geometry = menu.addAction("New Surface...")
            create_geometry.triggered.connect(self._create_surface_geometry)
            stitch = menu.addAction("Stitch Coincident Shell Nodes...")
            stitch.triggered.connect(self._stitch_coincident_shell_nodes)
            section = menu.addAction("New Shell Section...")
            section.triggered.connect(self._create_shell_section)
            pressure = menu.addAction("Create Surface Pressure...")
            pressure.triggered.connect(self._create_shell_pressure)
            exec_menu()
            return

        if kind == "surface_geometry":
            tag = int(value)
            surface = self.project.surfaces.get(tag)
            if surface is None:
                return
            properties = menu.addAction("Properties")
            properties.triggered.connect(
                lambda checked=False, t=tag:
                self._show_surface_geometry_properties(t)
            )
            edit = menu.addAction("Edit Surface...")
            edit.setEnabled(not any(
                element_tag in self.model.elements
                for element_tag in surface.generated_element_tags
            ))
            edit.triggered.connect(
                lambda checked=False, t=tag:
                self._edit_surface_geometry(t)
            )
            mesh = menu.addAction("Generate Surface Mesh...")
            mesh.setEnabled(not any(
                element_tag in self.model.elements
                for element_tag in surface.generated_element_tags
            ))
            mesh.triggered.connect(
                lambda checked=False, t=tag:
                self._mesh_surface_geometry(t)
            )
            menu.addSeparator()
            delete = menu.addAction("Delete Surface")
            delete.triggered.connect(
                lambda checked=False, t=tag:
                self._delete_surface_geometry(t)
            )
            exec_menu()
            return

        if kind == "frame_grids_root":
            quick_column = menu.addAction(
                "Quick 1D Column / Test Specimen..."
            )
            quick_column.triggered.connect(self._show_test_column_wizard)
            quick_2d = menu.addAction("Quick 2D Frame...")
            quick_2d.triggered.connect(self._show_frame_grid_2d)
            create = menu.addAction("Create / Edit Frame Grid...")
            create.triggered.connect(self._show_frame_grid)
            exec_menu()
            return

        if kind == "elements_root":
            create = menu.addAction("New Frame...")
            create.triggered.connect(self._create_element)
            create_truss = menu.addAction("New Truss...")
            create_truss.triggered.connect(self._create_truss)
            create_shell = menu.addAction("New Direct Shell Element...")
            create_shell.triggered.connect(self._create_shell)
            create_connection = menu.addAction(
                "New ZeroLength / Link Element..."
            )
            create_connection.triggered.connect(self._create_connection)
            select_all = menu.addAction("Select All Structural Elements")
            select_all.setEnabled(bool(self.model.elements))
            select_all.triggered.connect(
                lambda: self._select_all_tree_elements()
            )
            menu.addSeparator()
            menu.addAction(self.actions["show_element_numbers"])
            exec_menu()
            return

        if kind == "element_type_group":
            element_type = str(value)
            tags = {
                tag
                for tag, element in self.model.elements.items()
                if element.element_type == element_type
            }
            select_all = menu.addAction(
                f"Select All {element_type} ({len(tags)})"
            )
            select_all.setEnabled(bool(tags))
            select_all.triggered.connect(
                lambda checked=False, t=element_type:
                self._select_all_tree_elements(t)
            )
            menu.addSeparator()
            is_truss_group = element_type == "truss"
            is_shell_group = element_type in SHELL_ELEMENT_TYPES
            formulation = menu.addAction("Element Formulation...")
            formulation.setEnabled(
                not is_truss_group and not is_shell_group
            )
            formulation.triggered.connect(
                lambda checked=False, t=element_type: (
                    self._select_all_tree_elements(t),
                    self._set_element_formulation(),
                )
            )
            if is_shell_group:
                edit_shell = menu.addAction("Edit Shell Definition...")
                edit_shell.setEnabled(len(tags) == 1)
                edit_shell.triggered.connect(
                    lambda checked=False, values=tuple(sorted(tags)): (
                        self._edit_shell(values[0])
                        if len(values) == 1
                        else None
                    )
                )
            assign = menu.addMenu("Assign")
            material = assign.addAction("Material (Truss)...")
            material.setEnabled(is_truss_group)
            material.triggered.connect(
                lambda checked=False, t=element_type: (
                    self._select_all_tree_elements(t),
                    self._assign_truss_material_to_selection(),
                )
            )
            section = assign.addAction(
                "Shell Section..." if is_shell_group else "Section..."
            )
            section.setEnabled(not is_truss_group)
            section.triggered.connect(
                lambda checked=False, t=element_type, shell=is_shell_group: (
                    self._select_all_tree_elements(t),
                    (
                        self._assign_shell_section_to_selection()
                        if shell
                        else self._assign_section_to_selection()
                    ),
                )
            )
            transformation = assign.addAction("Transformation...")
            transformation.setEnabled(
                not is_truss_group and not is_shell_group
            )
            transformation.triggered.connect(
                lambda checked=False, t=element_type: (
                    self._select_all_tree_elements(t),
                    self._assign_transformation_to_selection(),
                )
            )
            if is_truss_group:
                clear_material = assign.addAction("Clear Material")
                clear_material.triggered.connect(
                    lambda checked=False, t=element_type: (
                        self._select_all_tree_elements(t),
                        self._clear_truss_material_assignment(),
                    )
                )
            beam_load = menu.addAction("Create Beam Load...")
            beam_load.setEnabled(
                not is_truss_group and not is_shell_group
            )
            beam_load.triggered.connect(
                lambda checked=False, t=element_type: (
                    self._select_all_tree_elements(t),
                    self._create_element_load(),
                )
            )
            shell_pressure = menu.addAction(
                "Create Surface Pressure..."
            )
            shell_pressure.setEnabled(is_shell_group)
            shell_pressure.triggered.connect(
                lambda checked=False, t=element_type: (
                    self._select_all_tree_elements(t),
                    self._create_shell_pressure(),
                )
            )
            menu.addSeparator()
            named = menu.addAction("Create Named Selection")
            named.setEnabled(bool(tags))
            named.triggered.connect(
                lambda checked=False, t=element_type: (
                    self._select_all_tree_elements(t),
                    self._create_named_selection(),
                )
            )
            exec_menu()
            return

        if kind == "named_sets_root":
            create = menu.addAction("Create from Current Selection...")
            create.triggered.connect(self._create_named_selection)
            exec_menu()
            return

        if kind == "boundary_root":
            constrained = {
                tag
                for tag, node in self.model.nodes.items()
                if any(node.fixity)
            }
            select_all = menu.addAction(
                f"Select All Supported Nodes ({len(constrained)})"
            )
            select_all.setEnabled(bool(constrained))
            select_all.triggered.connect(
                lambda: self.selection.set_selection(nodes=constrained)
            )
            menu.addSeparator()
            apply_support = menu.addAction(
                "Apply / Edit Support on Current Selection..."
            )
            apply_support.triggered.connect(self._apply_restraint)
            clear_support = menu.addAction(
                "Clear Support on Current Selection"
            )
            clear_support.setEnabled(bool(self.selection.nodes))
            clear_support.triggered.connect(self._clear_restraint)
            exec_menu()
            return

        if kind == "boundary_group":
            support_type = str(value)
            tags = {
                tag
                for tag, node in self.model.nodes.items()
                if any(node.fixity)
                and classify_fixity(node.fixity) == support_type
            }
            select_all = menu.addAction(
                f"Select {support_type} Nodes ({len(tags)})"
            )
            select_all.setEnabled(bool(tags))
            select_all.triggered.connect(
                lambda checked=False, s=support_type:
                self._select_boundary_group(s)
            )
            zoom = menu.addAction("Zoom to Group")
            zoom.setEnabled(bool(tags))
            zoom.triggered.connect(
                lambda checked=False, s=support_type: (
                    self._select_boundary_group(s),
                    self._zoom_selection(),
                )
            )
            menu.addSeparator()
            clear = menu.addAction("Clear These Supports")
            clear.setEnabled(bool(tags))
            clear.triggered.connect(
                lambda checked=False, s=support_type: (
                    self._select_boundary_group(s),
                    self._clear_restraint(),
                )
            )
            exec_menu()
            return

        if kind == "connection_group":
            create = menu.addAction("New ZeroLength / Link...")
            create.triggered.connect(self._create_connection)
            exec_menu()
            return

        if kind == "node":
            tag = int(value)
            if tag not in self.selection.nodes:
                self.selection.select("node", tag, "replace")
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(
                lambda: self._show_entity_properties("node", tag)
            )

            menu.addSeparator()
            zoom = menu.addAction("Zoom to Selection")
            zoom.triggered.connect(self._zoom_selection)
            hide = menu.addAction("Hide")
            hide.triggered.connect(self._hide_selection)
            isolate = menu.addAction("Isolate")
            isolate.triggered.connect(self._isolate_selection)
            show_all = menu.addAction("Show All")
            show_all.triggered.connect(self._show_all)

            menu.addSeparator()
            support_action = menu.addAction("Support / Restraint...")
            support_action.triggered.connect(self._apply_restraint)
            clear_action = menu.addAction("Clear Support")
            clear_action.triggered.connect(self._clear_restraint)
            mass_action = menu.addAction("Assign Mass...")
            mass_action.triggered.connect(self._assign_mass)
            clear_mass = menu.addAction("Clear Mass")
            clear_mass.triggered.connect(self._clear_mass)
            nodal_load = menu.addAction("Create Nodal Load...")
            nodal_load.triggered.connect(self._create_nodal_load)

            constraint = menu.addAction("Create Constraint...")
            constraint.triggered.connect(self._create_constraint)
            connection = menu.addAction("Create ZeroLength / Link...")
            connection.setEnabled(1 <= len(self.selection.nodes) <= 2)
            connection.triggered.connect(self._create_connection)

            menu.addSeparator()
            modify = menu.addMenu("Modify")
            move = modify.addAction("Move...")
            move.triggered.connect(self._move_selection)
            copy = modify.addAction("Copy...")
            copy.triggered.connect(self._copy_selection)
            rotate = modify.addAction("Rotate...")
            rotate.triggered.connect(self._rotate_selection)
            mirror = modify.addAction("Mirror...")
            mirror.triggered.connect(self._mirror_selection)
            reverse_shell = modify.addAction("Reverse Shell Normal")
            reverse_shell.setEnabled(has_shell)
            reverse_shell.triggered.connect(
                self._reverse_selected_shell_normals
            )
            stitch_shell = modify.addAction(
                "Stitch Coincident Shell Nodes..."
            )
            stitch_shell.setEnabled(has_shell)
            stitch_shell.triggered.connect(
                self._stitch_coincident_shell_nodes
            )

            copy_tag = menu.addAction("Copy Tag(s)")
            copy_tag.triggered.connect(self._copy_selected_tags)
            named = menu.addAction("Create Named Selection")
            named.triggered.connect(self._create_named_selection)

            menu.addSeparator()
            delete = menu.addAction("Delete")
            delete.triggered.connect(self._delete_selection)
            exec_menu()
            return

        if kind == "element":
            tag = int(value)
            if tag not in self.selection.elements:
                self.selection.select("element", tag, "replace")
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(
                lambda: self._show_entity_properties("element", tag)
            )

            menu.addSeparator()
            zoom = menu.addAction("Zoom to Selection")
            zoom.triggered.connect(self._zoom_selection)
            hide = menu.addAction("Hide")
            hide.triggered.connect(self._hide_selection)
            isolate = menu.addAction("Isolate")
            isolate.triggered.connect(self._isolate_selection)
            show_all = menu.addAction("Show All")
            show_all.triggered.connect(self._show_all)

            selected_elements = [
                self.model.elements[element_tag]
                for element_tag in self.selection.elements
                if element_tag in self.model.elements
            ]
            has_truss = any(
                element.element_type == "truss"
                for element in selected_elements
            )
            has_frame = any(
                element.element_type in FRAME_ELEMENT_TYPES
                for element in selected_elements
            )
            has_shell = any(
                element.element_type in SHELL_ELEMENT_TYPES
                for element in selected_elements
            )

            menu.addSeparator()
            if self.model.elements[tag].element_type in SHELL_ELEMENT_TYPES:
                edit_shell = menu.addAction("Edit Shell Definition...")
                edit_shell.triggered.connect(
                    lambda: self._edit_shell(tag)
                )
            formulation = menu.addAction("Element Formulation...")
            formulation.setEnabled(has_frame)
            formulation.triggered.connect(
                self._set_element_formulation
            )
            assign = menu.addMenu("Assign")
            material_action = assign.addAction("Material (Truss)...")
            material_action.setEnabled(has_truss)
            material_action.triggered.connect(
                self._assign_truss_material_to_selection
            )
            section_action = assign.addAction(
                "Shell Section..." if has_shell and not has_frame else "Section..."
            )
            section_action.setEnabled(has_frame or has_shell)
            section_action.triggered.connect(
                self._assign_shell_section_to_selection
                if has_shell and not has_frame
                else self._assign_section_to_selection
            )
            transformation_action = assign.addAction(
                "Transformation..."
            )
            transformation_action.setEnabled(has_frame)
            transformation_action.triggered.connect(
                self._assign_transformation_to_selection
            )
            assign.addSeparator()
            clear_material = assign.addAction("Clear Material (Truss)")
            clear_material.setEnabled(has_truss)
            clear_material.triggered.connect(
                self._clear_truss_material_assignment
            )
            clear_section = assign.addAction("Clear Section")
            clear_section.setEnabled(has_frame or has_shell)
            clear_section.triggered.connect(
                self._clear_section_assignment
            )
            clear_transformation = assign.addAction(
                "Clear Transformation"
            )
            clear_transformation.setEnabled(has_frame)
            clear_transformation.triggered.connect(
                self._clear_transformation_assignment
            )
            beam_load = menu.addAction("Create Beam Load...")
            beam_load.setEnabled(has_frame)
            beam_load.triggered.connect(self._create_element_load)
            shell_pressure = menu.addAction(
                "Create Surface Pressure..."
            )
            shell_pressure.setEnabled(has_shell)
            shell_pressure.triggered.connect(
                self._create_shell_pressure
            )

            menu.addSeparator()
            modify = menu.addMenu("Modify")
            move = modify.addAction("Move...")
            move.triggered.connect(self._move_selection)
            copy = modify.addAction("Copy...")
            copy.triggered.connect(self._copy_selection)
            rotate = modify.addAction("Rotate...")
            rotate.triggered.connect(self._rotate_selection)
            mirror = modify.addAction("Mirror...")
            mirror.triggered.connect(self._mirror_selection)

            copy_tag = menu.addAction("Copy Tag(s)")
            copy_tag.triggered.connect(self._copy_selected_tags)
            named = menu.addAction("Create Named Selection")
            named.triggered.connect(self._create_named_selection)

            menu.addSeparator()
            delete = menu.addAction("Delete")
            delete.triggered.connect(self._delete_selection)
            exec_menu()
            return

        if kind == "constraints_root":
            create_action = menu.addAction("New Constraint...")
            create_action.triggered.connect(self._create_constraint)
            exec_menu()
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
            exec_menu()
            return

        if kind == "connections_root":
            create_action = menu.addAction("New ZeroLength / Link...")
            create_action.triggered.connect(self._create_connection)
            exec_menu()
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
            exec_menu()
            return

        if kind == "analyses_root":
            template_menu = menu.addMenu("Analysis Wizard")
            for template_name in (
                "Modal",
                "Pushover",
                "Cyclic",
                "Nonlinear Time History",
            ):
                action = template_menu.addAction(template_name)
                action.triggered.connect(
                    lambda checked=False, name=template_name:
                    self._create_analysis_template(name)
                )
            menu.addSeparator()
            action = menu.addAction("New Analysis...")
            action.triggered.connect(self._create_analysis)
            exec_menu()
            return

        if kind in {
            "analysis",
            "analysis_settings",
            "analysis_cyclic_protocol",
        }:
            tag = int(value)
            active = menu.addAction("Set Active")
            active.setEnabled(tag != self.project.active_analysis_tag)
            active.triggered.connect(lambda: self._set_active_analysis(tag))
            run = menu.addAction("Run This Analysis")
            run.setEnabled(
                self._analysis_process is None
                or self._analysis_process.state() == QProcess.NotRunning
            )
            run.triggered.connect(
                lambda: self._run_analysis_from_tree(tag)
            )
            menu.addSeparator()
            edit = menu.addAction("Edit Analysis Settings...")
            edit.triggered.connect(lambda: self._edit_analysis(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_analysis(tag))
            exec_menu()
            return

        if kind == "solution_root":
            analysis_tag = int(value)
            analysis_settings = self.project.analyses.get(analysis_tag)
            analysis_type = (
                analysis_settings.analysis_type
                if analysis_settings is not None
                else ""
            )
            insert_menu = menu.addMenu("Add Result Request")
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
                integrator=(
                    analysis_settings.integrator
                    if analysis_settings is not None
                    else None
                ),
                section_response_available=True,
            )

            menu.addSeparator()
            evaluate_all = menu.addAction("Evaluate All Result Requests")
            evaluate_all.triggered.connect(
                lambda: self._evaluate_all_solution_results(analysis_tag)
            )
            clear_display = menu.addAction("Clear Result Display")
            clear_display.triggered.connect(self._clear_result_display)
            result_objects = self.project.solution_results_for_analysis(
                analysis_tag
            )
            delete_all = menu.addAction("Delete All Result Requests...")
            delete_all.setEnabled(bool(result_objects))
            delete_all.triggered.connect(
                lambda: self._delete_all_solution_results(analysis_tag)
            )
            exec_menu()
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
            clear_display = menu.addAction("Clear Result Display")
            clear_display.triggered.connect(self._clear_result_display)
            delete = menu.addAction("Delete Result...")
            delete.triggered.connect(
                lambda: self._delete_solution_result(tag)
            )
            exec_menu()
            return

        if kind == "solution_information":
            analysis_tag = int(value)
            solver_output = menu.addAction("Show Solver Output")
            solver_output.triggered.connect(
                lambda: (
                    self._show_solution_information(
                        analysis_tag,
                        "Solver Output",
                    ),
                    self.console_dock.show(),
                    self.console_dock.raise_(),
                )
            )
            analysis = self.project.analyses.get(analysis_tag)
            label = convergence_result_label(
                analysis.test if analysis is not None else None
            )
            convergence = menu.addAction(f"Open {label}")
            convergence.triggered.connect(
                lambda: self._show_solution_convergence(analysis_tag)
            )
            exec_menu()
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
            exec_menu()
            return

        if kind == "solver_output":
            show = menu.addAction("Show Solver Output")
            show.triggered.connect(
                lambda: (
                    self.console_dock.show(),
                    self.console_dock.raise_(),
                )
            )
            exec_menu()
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
            menu.addSeparator()
            clear_display = menu.addAction("Clear Result Display")
            clear_display.triggered.connect(self._clear_result_display)
            delete_all_jobs = menu.addAction("Delete All Jobs...")
            delete_all_jobs.setEnabled(bool(self._jobs))
            delete_all_jobs.triggered.connect(self._delete_all_jobs)
            exec_menu()
            return

        if kind == "job":
            job_id = int(value)
            job = self._jobs.get(job_id)

            activate = menu.addAction("Set as Active Result Source")
            activate.setEnabled(job is not None)
            activate.triggered.connect(
                lambda: self._activate_job_result(job_id)
            )

            plot_menu = menu.addMenu("Plot")
            plot_menu.setEnabled(job is not None)
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
                    integrator=str(
                        job.results.get("analysis", {}).get("integrator", "")
                    ) if isinstance(job.results.get("analysis", {}), dict) else None,
                    section_response_available=bool(
                        job.results.get("section_responses", {})
                    ),
                )

            menu.addSeparator()
            clear_display = menu.addAction("Clear Result Display")
            clear_display.triggered.connect(self._clear_result_display)
            export = menu.addAction("Export Results JSON...")
            export.setEnabled(job is not None)
            export.triggered.connect(
                lambda: self._export_job_result_json(job_id)
            )
            menu.addSeparator()
            delete_job = menu.addAction("Delete Job...")
            delete_job.setEnabled(job is not None and job.status != "Running")
            delete_job.triggered.connect(
                lambda: self._delete_job(job_id)
            )
            exec_menu()
            return

        if kind == "job_plot":
            try:
                job_id = int(value[0])
                plot_id = int(value[1])
            except (TypeError, ValueError, IndexError):
                return
            job = self._jobs.get(job_id)
            plot = job.plot(plot_id) if job is not None else None
            if plot is None:
                return

            show = menu.addAction("Show")
            show.triggered.connect(
                lambda: self._show_job_plot(job_id, plot_id)
            )
            rename = menu.addAction("Rename...")
            rename.triggered.connect(
                lambda: self._rename_job_plot(job_id, plot_id)
            )
            duplicate = menu.addAction("Duplicate")
            duplicate.triggered.connect(
                lambda: self._duplicate_job_plot(job_id, plot_id)
            )
            menu.addSeparator()
            clear_display = menu.addAction("Clear Result Display")
            clear_display.triggered.connect(self._clear_result_display)
            delete = menu.addAction("Delete Result...")
            delete.triggered.connect(
                lambda: self._delete_job_plot(job_id, plot_id)
            )
            exec_menu()
            return

        if kind == "recorders_root":
            action = menu.addAction("New Recorder...")
            action.triggered.connect(self._create_recorder)
            exec_menu()
            return

        if kind == "recorder":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_recorder(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_recorder(tag))
            exec_menu()
            return

        if kind == "mass_sources_root":
            action = menu.addAction("New Mass Source...")
            action.triggered.connect(self._create_mass_source)
            exec_menu()
            return

        if kind == "mass_source":
            tag = int(value)
            properties = menu.addAction("Properties")
            properties.triggered.connect(
                lambda: self._show_mass_source_properties(tag)
            )
            apply_action = menu.addAction("Apply / Regenerate Mass")
            apply_action.triggered.connect(
                lambda: self._apply_mass_source(tag)
            )
            edit = menu.addAction("Edit...")
            edit.triggered.connect(
                lambda: self._edit_mass_source(tag)
            )
            menu.addSeparator()
            delete = menu.addAction("Delete Definition")
            delete.triggered.connect(
                lambda: self._delete_mass_source(tag)
            )
            exec_menu()
            return

        if kind == "masses_root":
            assign_action = menu.addAction("Assign to Current Node Selection...")
            assign_action.triggered.connect(self._assign_mass)
            clear_action = menu.addAction("Clear Current Node Selection")
            clear_action.triggered.connect(self._clear_mass)
            exec_menu()
            return

        if kind == "time_series_root":
            action = menu.addAction("New Time Series...")
            action.triggered.connect(self._create_time_series)
            exec_menu()
            return

        if kind == "time_series":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_time_series(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_time_series(tag))
            exec_menu()
            return

        if kind == "loading_root":
            new_pattern = menu.addAction("New Load Pattern...")
            new_pattern.triggered.connect(self._create_load_pattern)
            new_motion = menu.addAction("New Ground Motion...")
            new_motion.triggered.connect(self._create_ground_motion)
            import_motion = menu.addAction("Import Ground Motion...")
            import_motion.triggered.connect(self._import_ground_motion)
            new_series = menu.addAction("New Time Series...")
            new_series.triggered.connect(self._create_time_series)
            exec_menu()
            return

        if kind == "ground_motions_root":
            action = menu.addAction("New Ground Motion...")
            action.triggered.connect(self._create_ground_motion)
            import_action = menu.addAction("Import Ground Motion...")
            import_action.triggered.connect(self._import_ground_motion)
            exec_menu()
            return

        if kind == "ground_motion":
            tag = int(value)
            properties = menu.addAction("Properties")
            properties.triggered.connect(
                lambda: self._show_ground_motion_properties(tag)
            )
            edit = menu.addAction("Edit...")
            edit.triggered.connect(
                lambda: self._edit_ground_motion(tag)
            )
            menu.addSeparator()
            delete = menu.addAction("Delete")
            delete.triggered.connect(
                lambda: self._delete_ground_motion(tag)
            )
            exec_menu()
            return

        if kind == "load_patterns_root":
            action = menu.addAction("New Load Pattern...")
            action.triggered.connect(self._create_load_pattern)
            exec_menu()
            return

        if kind == "load_pattern":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_load_pattern(tag))
            pattern = self.project.load_patterns.get(tag)
            if pattern is not None and pattern.pattern_type == "Plain":
                add_load = menu.addAction("Add Nodal Load...")
                add_load.triggered.connect(self._create_nodal_load)
                add_displacement = menu.addAction(
                    "Add Prescribed Displacement..."
                )
                add_displacement.triggered.connect(
                    self._create_prescribed_displacement
                )
                add_element_load = menu.addAction("Add Beam Load...")
                add_element_load.triggered.connect(
                    self._create_element_load
                )
                add_shell_pressure = menu.addAction(
                    "Add Shell Surface Pressure..."
                )
                add_shell_pressure.triggered.connect(
                    self._create_shell_pressure
                )
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_load_pattern(tag))
            exec_menu()
            return

        if kind == "nodal_load":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(lambda: self._edit_nodal_load(tag))
            delete = menu.addAction("Delete")
            delete.triggered.connect(lambda: self._delete_nodal_load(tag))
            exec_menu()
            return

        if kind == "prescribed_displacement":
            tag = int(value)
            edit = menu.addAction("Edit...")
            edit.triggered.connect(
                lambda: self._edit_prescribed_displacement(tag)
            )
            delete = menu.addAction("Delete")
            delete.triggered.connect(
                lambda: self._delete_prescribed_displacement(tag)
            )
            exec_menu()
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
            exec_menu()
            return

        if kind == "materials_root":
            self._populate_materials_root_context_menu(menu)
            exec_menu()
            return

        if kind == "nd_materials_root":
            create_action = menu.addAction("New nD Material...")
            create_action.triggered.connect(self._create_nd_material)
            exec_menu()
            return

        if kind == "nd_material":
            tag = int(value)
            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(
                lambda: self._edit_nd_material(tag)
            )
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_nd_material(tag)
            )
            exec_menu()
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
            exec_menu()
            return

        if kind == "sections_root":
            create_action = menu.addAction("New Beam / Fiber Section...")
            create_action.triggered.connect(self._create_section)
            shell_action = menu.addAction("New Shell Section...")
            shell_action.triggered.connect(self._create_shell_section)
            exec_menu()
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
            exec_menu()
            return

        if kind == "transformations_root":
            create_action = menu.addAction("New Transformation...")
            create_action.triggered.connect(self._create_transformation)
            exec_menu()
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
            exec_menu()
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

        exec_menu()

    def _tree_item_double_clicked(self, item, column: int) -> None:
        payload = item.data(0, Qt.UserRole)
        if not payload:
            return
        kind, value = payload
        if kind == "material":
            self._edit_material(int(value))
        elif kind == "nd_material":
            self._edit_nd_material(int(value))
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
        elif kind == "ground_motion":
            self._edit_ground_motion(int(value))
        elif kind == "nodal_load":
            self._edit_nodal_load(int(value))
        elif kind == "prescribed_displacement":
            self._edit_prescribed_displacement(int(value))
        elif kind == "element_load":
            self._edit_element_load(int(value))
        elif kind == "mass_source":
            self._edit_mass_source(int(value))
        elif kind in {"analysis", "analysis_settings"}:
            self._edit_analysis(int(value))
        elif kind == "job":
            self._activate_job_result(int(value))
        elif kind == "job_plot":
            try:
                self._show_job_plot(int(value[0]), int(value[1]))
            except (TypeError, ValueError, IndexError):
                return
        elif kind == "solution_result":
            self._evaluate_solution_result(int(value))
        elif kind == "solution_convergence":
            self._show_solution_convergence(int(value))
        elif kind == "solver_output":
            self.console_dock.show()
            self.console_dock.raise_()
        elif kind == "jobs_root":
            self.results_panel.show_jobs()
            self.results_dock.show()
            self.results_dock.raise_()
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
        """Regenerate, validate and export a standalone OpenSeesPy script."""
        settings = self.project.analyses.get(
            self.project.active_analysis_tag
        )
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
            self.status_message.setText(
                f"Export blocked: {len(errors)} model-check error(s)"
            )
            self._show_model_check(issues, allow_run=False)
            return

        if warnings:
            answer = QMessageBox.question(
                self,
                "Export OpenSeesPy with warnings?",
                (
                    f"Model Check found {len(warnings)} warning(s) and no "
                    "errors. Warnings do not necessarily prevent OpenSeesPy "
                    "from running, but they should be reviewed.\n\n"
                    "Export the generated script anyway?"
                ),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            source = self._generate_project_script()
        except (KeyError, TypeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Export OpenSeesPy",
                f"Script generation failed:\n\n{exc}",
            )
            self.status_message.setText("OpenSeesPy export failed")
            return

        generator_errors = [
            line.strip()
            for line in source.splitlines()
            if line.lstrip().startswith("# ERROR:")
        ]
        if generator_errors:
            preview = "\n".join(generator_errors[:8])
            if len(generator_errors) > 8:
                preview += (
                    f"\n... and {len(generator_errors) - 8} more error(s)"
                )
            QMessageBox.critical(
                self,
                "Export OpenSeesPy",
                (
                    "The generator found incomplete or unsupported model "
                    "entities. Export is blocked until these are fixed.\n\n"
                    f"{preview}"
                ),
            )
            self.status_message.setText(
                f"Export blocked: {len(generator_errors)} generator error(s)"
            )
            return

        try:
            compile(source, "<SARE OpenSeesPy export>", "exec")
        except SyntaxError as exc:
            QMessageBox.critical(
                self,
                "Export OpenSeesPy",
                (
                    "Generated Python failed the syntax check.\n\n"
                    f"Line {exc.lineno}: {exc.msg}"
                ),
            )
            self.status_message.setText(
                "Export blocked: generated Python syntax error"
            )
            return

        runtime_ok, runtime_detail = probe_opensees_runtime(timeout=10.0)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export OpenSeesPy script",
            "model.py",
            "Python (*.py)",
        )
        if not path:
            return
        if not path.lower().endswith(".py"):
            path += ".py"

        try:
            Path(path).write_text(source, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Export OpenSeesPy",
                f"Could not write the script:\n\n{exc}",
            )
            self.status_message.setText("OpenSeesPy export failed")
            return

        # Keep the preview synchronized with exactly what was exported.
        self.script.setPlainText(source)
        self._log(
            f"Exported verified OpenSeesPy script: {path} "
            f"(warnings={len(warnings)}, runtime_probe={runtime_ok})"
        )
        self.status_message.setText(
            f"Exported verified OpenSeesPy script: {Path(path).name}"
        )

        summary = (
            "Export completed.\n\n"
            "✓ Regenerated from Project database\n"
            "✓ Model Check: 0 errors"
            + (f", {len(warnings)} warning(s)\n" if warnings else "\n")
            + "✓ Generator error markers: none\n"
            "✓ Python syntax check: passed\n"
            + (
                "✓ Local OpenSeesPy runtime probe: passed"
                if runtime_ok
                else "⚠ Local OpenSeesPy runtime probe: not verified"
            )
        )
        if not runtime_ok and runtime_detail:
            summary += f"\n\nRuntime probe detail:\n{runtime_detail}"

        if runtime_ok:
            QMessageBox.information(
                self,
                "OpenSeesPy Export Verified",
                summary,
            )
        else:
            QMessageBox.warning(
                self,
                "OpenSeesPy Exported with Runtime Warning",
                summary,
            )

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

    def _run_moment_curvature_workflow(
        self,
        checked: bool = False,
    ) -> None:
        self._log("Opening Moment-Curvature research workflow")
        self.status_message.setText("Opening Moment-Curvature...")
        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(
                self,
                "Moment-Curvature",
                "Stop the active analysis before starting a section test.",
            )
            return
        if (
            self._calibration_process is not None
            and self._calibration_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(
                self,
                "Moment-Curvature",
                "Stop the cyclic calibration batch before starting a "
                "section test.",
            )
            return
        if not self._ensure_prerequisite(
            title="Moment-Curvature",
            message=(
                "Moment-Curvature requires an existing Section. "
                "Create the Section now?"
            ),
            action_label="Create Section Now...",
            available=lambda: bool(self.project.sections),
            creator=self._create_section,
        ):
            return
        dialog = MomentCurvatureDialog(self.project, self)
        if not dialog.exec():
            return

        try:
            temporary_project = build_moment_curvature_project(
                self.project,
                dialog.spec(),
            )
            temporary_script = to_openseespy(
                temporary_project.model,
                temporary_project.materials,
                temporary_project.sections,
                temporary_project.transformations,
                temporary_project.constraints,
                temporary_project.connections,
                temporary_project.time_series,
                temporary_project.load_patterns,
                temporary_project.nodal_loads,
                temporary_project.analyses,
                temporary_project.active_analysis_tag,
                element_loads=temporary_project.element_loads,
                prescribed_displacements=(
                    temporary_project.prescribed_displacements
                ),
                recorders=temporary_project.recorders,
                units=temporary_project.units,
                solution_results=temporary_project.solution_results,
                nd_materials=temporary_project.nd_materials,
            )
        except (KeyError, TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Moment-Curvature",
                f"Could not build the isolated section test:\n\n{exc}",
            )
            return

        original_project = self.project
        original_model = self.model
        original_script = self.script.toPlainText()

        try:
            # _start_analysis performs the normal model check, runtime
            # material probes, Job creation and worker launch.  Swap in the
            # isolated project only for that synchronous setup phase.
            self.project = temporary_project
            self.model = temporary_project.model
            self.script.setPlainText(temporary_script)
            self._start_analysis()
        finally:
            self.project = original_project
            self.model = original_model
            self.script.setPlainText(original_script)
            self._refresh_project_metadata()

    def _open_hinge_backbone_from_result(self, payload: object) -> None:
        prefill = dict(payload) if isinstance(payload, dict) else {}
        self._open_hinge_backbone(prefill=prefill)

    def _open_hinge_backbone(
        self,
        checked: bool = False,
        *,
        prefill: dict | None = None,
    ) -> None:
        dialog = HingeBackboneDialog(
            next_tag=self.project.next_material_tag(),
            units=self.project.units,
            prefill=prefill,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            material = dialog.material_data()
            self.project.add_material(material)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Hinge Backbone Builder",
                str(exc),
            )
            return

        self._refresh_project_metadata(
            f"Created hinge-backbone Hysteretic material {material.tag}"
        )
        self._show_material_properties(material.tag)
        self._record_project_change(
            f"Create hinge backbone material {material.tag}",
            before,
        )

    def _open_calibration(self) -> None:
        process = self._calibration_process
        if process is not None and process.state() != QProcess.NotRunning:
            self._calibration_stop_requested = True
            self.console.appendPlainText(
                ">> Stopping calibration worker..."
            )
            self.status_message.setText("Stopping calibration...")
            process.terminate()
            QTimer.singleShot(
                2000,
                self._kill_calibration_if_needed,
            )
            return

        if (
            self._analysis_process is not None
            and self._analysis_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(
                self,
                "Calibration",
                "Stop the active analysis before starting a calibration batch.",
            )
            return

        active_tag = self.project.active_analysis_tag
        settings = self.project.analyses.get(active_tag)
        if settings is None or settings.analysis_type != "Cyclic":
            if not self._ensure_prerequisite(
                title="Cyclic Calibration",
                message=(
                    "Cyclic Calibration requires an active Cyclic analysis. "
                    "Open the Cyclic Analysis Wizard now?"
                ),
                action_label="Create Cyclic Analysis Now...",
                available=lambda: (
                    (
                        self.project.analyses.get(
                            self.project.active_analysis_tag
                        )
                    ) is not None
                    and self.project.analyses[
                        self.project.active_analysis_tag
                    ].analysis_type == "Cyclic"
                ),
                creator=lambda: self._create_analysis_template("Cyclic"),
            ):
                return
            active_tag = self.project.active_analysis_tag
            settings = self.project.analyses.get(active_tag)
            if settings is None or settings.analysis_type != "Cyclic":
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
                f"Calibration blocked: {len(errors)} model error(s)"
            )
            return
        if warnings and not self._show_model_check(
            issues,
            allow_run=True,
        ):
            self.status_message.setText(
                "Calibration cancelled after model check"
            )
            return

        runtime_ok, runtime_detail = probe_opensees_runtime(
            sys.executable
        )
        if not runtime_ok:
            QMessageBox.critical(
                self,
                "OpenSeesPy Runtime",
                "OpenSeesPy cannot start in the current Python environment.\n\n"
                + runtime_detail,
            )
            return

        dialog = CalibrationDialog(self.project, self)
        if not dialog.exec():
            return
        try:
            request = dialog.request()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Calibration",
                str(exc),
            )
            return

        strategy = str(request.get("strategy", "grid") or "grid")
        cases = request.get("cases", [])
        parameters = request.get("parameters", [])
        weights = request.get("weights")
        experiment_x = request.get("experiment_x", [])
        experiment_y = request.get("experiment_y", [])

        if strategy == "grid":
            if not isinstance(cases, list) or not cases:
                QMessageBox.warning(
                    self,
                    "Calibration",
                    "No parameter-study cases were created.",
                )
                return
        elif strategy == "adaptive":
            if not isinstance(parameters, list) or not parameters:
                QMessageBox.warning(
                    self,
                    "Calibration",
                    "Adaptive calibration needs at least one parameter.",
                )
                return
        else:
            QMessageBox.warning(
                self,
                "Calibration",
                f"Unsupported calibration strategy: {strategy}",
            )
            return

        self._calibration_project_snapshot = self.project.to_dict()
        snapshot_project = ProjectDatabase.from_dict(
            self._calibration_project_snapshot
        )
        plan_cases: list[dict[str, object]] = []
        if strategy == "grid":
            try:
                for case in cases:
                    if not isinstance(case, CalibrationCase):
                        continue
                    plan_cases.append({
                        "case_id": case.case_id,
                        "values": dict(case.values),
                        "script": calibration_case_script(
                            snapshot_project,
                            case,
                        ),
                    })
            except ValueError as exc:
                self._calibration_project_snapshot = None
                QMessageBox.warning(
                    self,
                    "Calibration",
                    f"Could not build calibration cases:\n{exc}",
                )
                return

            if not plan_cases:
                self._calibration_project_snapshot = None
                return

        plan_fd, plan_path = tempfile.mkstemp(
            prefix="openseespy_studio_calibration_",
            suffix=".json",
            text=True,
        )
        os.close(plan_fd)
        result_fd, result_path = tempfile.mkstemp(
            prefix="openseespy_studio_calibration_result_",
            suffix=".json",
            text=True,
        )
        os.close(result_fd)

        weight_payload = {
            "peak_force": float(weights.peak_force),
            "reversal_nrmse": float(weights.reversal_nrmse),
            "cycle_energy": float(weights.cycle_energy),
            "max_displacement": float(weights.max_displacement),
        }
        plan = {
            "strategy": strategy,
            "analysis_tag": int(settings.tag),
            "analysis_name": str(settings.name),
            "experiment": {
                "x": [float(value) for value in experiment_x],
                "y": [float(value) for value in experiment_y],
                "source": str(request.get("experiment_path", "")),
            },
            "weights": weight_payload,
        }
        if strategy == "adaptive":
            rounds = int(request.get("adaptive_rounds", 3) or 3)
            shrink_ratio = float(
                request.get("adaptive_shrink_ratio", 0.5) or 0.5
            )
            plan.update({
                "project": self._calibration_project_snapshot,
                "parameters": calibration_parameter_payload(parameters),
                "rounds": rounds,
                "shrink_ratio": shrink_ratio,
                "max_total_cases": 96,
            })
            planned_case_count = (
                calibration_grid_size(parameters) * rounds
            )
        else:
            plan["cases"] = plan_cases
            planned_case_count = len(plan_cases)
        Path(plan_path).write_text(
            json.dumps(plan, ensure_ascii=False),
            encoding="utf-8",
        )

        self._calibration_plan_path = plan_path
        self._calibration_result_path = result_path
        self._calibration_output_buffer = ""
        self._calibration_active_analysis_tag = int(settings.tag)
        self._calibration_stop_requested = False

        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert(
            "PYTHONPATH",
            build_worker_pythonpath(
                environment.value("PYTHONPATH")
            ),
        )
        process.setProcessEnvironment(environment)
        worker_program, worker_prefix = worker_process_command(
            "openseespy_studio.calibration_worker"
        )
        process.setProgram(worker_program)
        process.setArguments([
            *worker_prefix,
            plan_path,
            "--result-file",
            result_path,
        ])
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            self._read_calibration_stdout
        )
        process.finished.connect(self._calibration_finished)
        process.errorOccurred.connect(
            self._calibration_process_error
        )
        self._calibration_process = process

        self.console_dock.show()
        if strategy == "adaptive":
            self.console.appendPlainText(
                f">> Adaptive calibration: up to {planned_case_count} "
                f"cyclic case(s) across {rounds} round(s), "
                f"shrink={shrink_ratio:.3g}"
            )
        else:
            self.console.appendPlainText(
                f">> Grid calibration: starting {planned_case_count} "
                "cyclic case(s)"
            )
        self.console.appendPlainText(
            ">> Experimental reference: "
            + (
                Path(str(request.get("experiment_path", ""))).name
                or "imported data"
            )
        )
        self.status_message.setText(
            f"Calibration · 0/{planned_case_count} planned cases"
        )
        self.actions["calibration"].setText("Stop Calibration")
        self.actions["run"].setEnabled(False)
        process.start()

    def _kill_calibration_if_needed(self) -> None:
        process = self._calibration_process
        if process is not None and process.state() != QProcess.NotRunning:
            process.kill()

    def _consume_calibration_line(self, line: str) -> None:
        text_line = str(line).strip()
        if not text_line:
            return
        prefix = "@@STUDIO_CALIBRATION@@"
        if not text_line.startswith(prefix):
            self.console.appendPlainText(text_line)
            return
        try:
            payload = json.loads(text_line[len(prefix):])
        except json.JSONDecodeError:
            self.console.appendPlainText(text_line)
            return
        event = str(payload.get("event", ""))
        current = int(payload.get("current", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        if event == "case_start":
            case_id = int(payload.get("case_id", current) or current)
            round_index = int(payload.get("round", 1) or 1)
            self.status_message.setText(
                f"Calibration · R{round_index} · "
                f"case {current}/{total} · #{case_id}"
            )
        elif event == "case_finish":
            case_id = int(payload.get("case_id", current) or current)
            round_index = int(payload.get("round", 1) or 1)
            score = payload.get("score")
            score_text = (
                f"{float(score):.4g}%"
                if score is not None
                else "unavailable"
            )
            self.console.appendPlainText(
                f">> Calibration R{round_index} case {case_id}: "
                f"{payload.get('status', '-')} · score={score_text}"
            )
            self.status_message.setText(
                f"Calibration · R{round_index} · "
                f"{current}/{total} planned cases"
            )
        elif event == "round_start":
            round_index = int(payload.get("round", 1) or 1)
            rounds = int(payload.get("rounds", 1) or 1)
            self.console.appendPlainText(
                f">> Adaptive round {round_index}/{rounds} started"
            )
            self.status_message.setText(
                f"Adaptive calibration · round {round_index}/{rounds}"
            )
        elif event == "round_finish":
            round_index = int(payload.get("round", 1) or 1)
            rounds = int(payload.get("rounds", 1) or 1)
            best_case = payload.get("best_case_id")
            best_score = payload.get("best_score")
            best_text = (
                f"case {best_case} · {float(best_score):.4g}%"
                if best_case is not None and best_score is not None
                else "no scored case"
            )
            self.console.appendPlainText(
                f">> Adaptive round {round_index}/{rounds} finished · "
                f"best {best_text}"
            )
        elif event == "start":
            strategy = str(payload.get("strategy", "grid"))
            rounds = int(payload.get("rounds", 1) or 1)
            if strategy == "adaptive":
                self.status_message.setText(
                    f"Adaptive calibration · 0/{total} planned cases · "
                    f"{rounds} rounds"
                )
            else:
                self.status_message.setText(
                    f"Calibration · 0/{total} cases"
                )
        elif event == "finish":
            reason = str(payload.get("stop_reason", "") or "")
            if reason:
                self.console.appendPlainText(
                    f">> Adaptive calibration stop reason: {reason}"
                )
        elif event == "failed":
            error = str(payload.get("error", "") or "")
            if error:
                self.console.appendPlainText(
                    f">> Calibration worker: {error}"
                )

    def _read_calibration_stdout(self) -> None:
        process = self._calibration_process
        if process is None:
            return
        text_data = bytes(
            process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")
        if not text_data:
            return
        self._calibration_output_buffer += text_data
        while "\n" in self._calibration_output_buffer:
            line, self._calibration_output_buffer = (
                self._calibration_output_buffer.split("\n", 1)
            )
            self._consume_calibration_line(line)

    def _calibration_process_error(self, _error) -> None:
        process = self._calibration_process
        if process is None:
            return
        self.console.appendPlainText(
            ">> Calibration worker process error: "
            + process.errorString()
        )

    def _read_calibration_result(self) -> dict[str, object]:
        path = self._calibration_result_path
        if not path:
            return {}
        try:
            payload = json.loads(
                Path(path).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def _calibration_finished(
        self,
        exit_code: int,
        exit_status,
    ) -> None:
        if self._calibration_output_buffer.strip():
            self._consume_calibration_line(
                self._calibration_output_buffer
            )
        self._calibration_output_buffer = ""

        crashed = exit_status == QProcess.CrashExit
        payload = self._read_calibration_result()
        rows = payload.get("cases", [])
        if not isinstance(rows, list):
            rows = []

        if self._calibration_stop_requested:
            self.console.appendPlainText(
                ">> Calibration stopped by user."
            )
            self.status_message.setText("Calibration stopped")
        elif crashed or exit_code != 0:
            error = str(payload.get("error", "") or "")
            self.console.appendPlainText(
                ">> Calibration worker failed"
                + (f": {error.splitlines()[-1]}" if error else "")
            )
            self.status_message.setText("Calibration failed")
        else:
            strategy = str(payload.get("strategy", "grid") or "grid")
            rounds_completed = int(
                payload.get("rounds_completed", 1) or 1
            )
            stop_reason = str(payload.get("stop_reason", "") or "")
            label = (
                f"adaptive · {rounds_completed} round(s)"
                if strategy == "adaptive"
                else "grid"
            )
            self.console.appendPlainText(
                f">> Calibration completed: {len(rows)} case(s) · {label}"
            )
            if stop_reason:
                self.console.appendPlainText(
                    f">> Calibration note: {stop_reason}"
                )

        display_rows: list[dict[str, object]] = []
        snapshot = self._calibration_project_snapshot
        base_project = (
            ProjectDatabase.from_dict(snapshot)
            if isinstance(snapshot, dict)
            else None
        )
        analysis_tag = self._calibration_active_analysis_tag
        analysis = (
            base_project.analyses.get(analysis_tag)
            if base_project is not None and analysis_tag is not None
            else None
        )

        for row in rows:
            if not isinstance(row, dict):
                continue
            result = row.get("result", {})
            if not isinstance(result, dict):
                result = {}
            case_id = int(row.get("case_id", 0) or 0)
            values = row.get("values", {})
            if not isinstance(values, dict):
                values = {}

            if result and base_project is not None:
                try:
                    case_project = apply_calibration_case(
                        base_project,
                        CalibrationCase(
                            case_id=case_id,
                            values={
                                str(key): float(value)
                                for key, value in values.items()
                            },
                        ),
                    )
                    result = enrich_member_force_results(
                        result,
                        case_project.model,
                        case_project.element_loads,
                        case_project.sections,
                        case_project.materials,
                        case_project.transformations,
                        case_project.units,
                    )
                    result = enrich_fiber_state_results(
                        result,
                        case_project.materials,
                    )
                except (TypeError, ValueError) as exc:
                    self.console.appendPlainText(
                        f">> Calibration case {case_id} "
                        f"post-processing warning: {exc}"
                    )

            self._job_counter += 1
            job = JobRecord(
                job_id=self._job_counter,
                analysis_tag=analysis_tag,
                analysis_name=(
                    f"{analysis.name} · Calibration R"
                    f"{int(row.get('round', 1) or 1)} C{case_id}"
                    if analysis is not None
                    else (
                        f"Calibration R{int(row.get('round', 1) or 1)} "
                        f"C{case_id}"
                    )
                ),
                analysis_type=(
                    analysis.analysis_type
                    if analysis is not None
                    else "Cyclic"
                ),
            )
            job.start()
            score = row.get("score")
            execution_status = str(
                row.get("execution_status", "failed")
            )
            job_status = (
                "Completed"
                if execution_status == "completed" and result
                else "Failed"
            )
            score_text = (
                f"{float(score):.6g}%"
                if score is not None
                else "unavailable"
            )
            job.finish(
                job_status,
                exit_code=0 if job_status == "Completed" else 1,
                message=f"Calibration score {score_text}",
                results=result,
            )
            self._jobs[job.job_id] = job
            self.results_panel.add_or_update_job(job)

            display_row = {
                key: value
                for key, value in row.items()
                if key not in {"result", "comparison"}
            }
            display_row["job_id"] = job.job_id
            display_row["status"] = (
                "Scored"
                if row.get("score") is not None
                else execution_status.title()
            )
            display_rows.append(display_row)

        if display_rows:
            display_rows.sort(
                key=lambda item: (
                    item.get("rank") is None,
                    int(item.get("rank") or 10**9),
                    int(item.get("case_id", 0) or 0),
                )
            )
            self.results_panel.set_calibration_results(
                display_rows
            )
            self.results_panel.show_calibration()
            self.results_dock.show()
            self.results_dock.raise_()

            best = next(
                (
                    item
                    for item in display_rows
                    if item.get("rank") == 1
                    and item.get("job_id") is not None
                ),
                None,
            )
            if best is not None:
                job = self._jobs.get(int(best["job_id"]))
                if job is not None and job.results:
                    self._last_result = dict(job.results)
                    self._last_result_cache_key = (
                        "job",
                        job.job_id,
                    )
                    self.results_panel.set_result(
                        self._last_result,
                        cache_key=self._last_result_cache_key,
                    )
                    self.results_panel.set_calibration_results(
                        display_rows
                    )
                    self.results_panel.show_calibration()
                    self.status_message.setText(
                        "Calibration completed · "
                        f"best case #{best.get('case_id')} · "
                        f"score {float(best.get('score')):.4g}%"
                    )
        elif not self._calibration_stop_requested:
            self.status_message.setText(
                "Calibration finished without scored cases"
            )

        self.actions["calibration"].setText("Calibration...")
        self.actions["run"].setEnabled(True)
        self._calibration_process = None
        self._calibration_stop_requested = False
        self._refresh_tree()
        self._cleanup_calibration_files()

    def _cleanup_calibration_files(self) -> None:
        paths = (
            self._calibration_plan_path,
            self._calibration_result_path,
        )
        self._calibration_plan_path = None
        self._calibration_result_path = None
        for path in paths:
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
        self._calibration_active_analysis_tag = None
        self._calibration_project_snapshot = None

    def _toggle_analysis(self) -> None:
        if (
            self._calibration_process is not None
            and self._calibration_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(
                self,
                "Run",
                "Stop the calibration batch before starting a normal analysis.",
            )
            return
        if self._analysis_process is not None:
            if self._analysis_process.state() != QProcess.NotRunning:
                self._stop_analysis()
                return
        self._start_analysis()

    def _start_analysis(self) -> None:
        active_tag = self.project.active_analysis_tag
        settings = self.project.analyses.get(active_tag)
        if settings is None:
            if not self._ensure_prerequisite(
                title="Run",
                message=(
                    "Run requires an active Analysis Settings object. "
                    "Create Analysis Settings now?"
                ),
                action_label="Create Analysis Settings Now...",
                available=lambda: (
                    self.project.analyses.get(
                        self.project.active_analysis_tag
                    )
                    is not None
                ),
                creator=self._create_analysis,
            ):
                return
            active_tag = self.project.active_analysis_tag
            settings = self.project.analyses.get(active_tag)
            if settings is None:
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

        required_material_probes = sorted({
            material.material_type
            for material in self.project.materials.values()
            if opensees_material_requires_runtime_probe(
                material.material_type
            )
        })
        for material_type in required_material_probes:
            material_ok, material_detail = (
                probe_opensees_material_support(
                    material_type,
                    sys.executable,
                )
            )
            if not material_ok:
                self.console.appendPlainText(
                    f">> OpenSees material check FAILED: {material_type}"
                )
                for line in material_detail.splitlines():
                    self.console.appendPlainText(">> " + line)
                self.status_message.setText(
                    f"Run blocked: {material_type} unavailable"
                )
                QMessageBox.critical(
                    self,
                    "OpenSees Material Unavailable",
                    (
                        f"The current OpenSeesPy binary does not provide "
                        f"{material_type}.\n\n"
                        "Studio has kept the imported material definition "
                        "unchanged, but this analysis cannot run with the "
                        "current binary.\n\n"
                        "OpenSees reports that this legacy material may be "
                        "temporarily removed from compiled Tcl/Python builds. "
                        "Use a compatible/custom OpenSees build if you must "
                        "reproduce this constitutive model. Do not substitute "
                        "another material automatically unless you have "
                        "validated that constitutive choice for your study.\n\n"
                        "Runtime detail:\n"
                        + material_detail
                    ),
                )
                return
            self.console.appendPlainText(
                f">> OpenSees material check OK: {material_type}"
            )

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
                settings.eigen_solver
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
            f"SARE · Job {job.job_id}\n"
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
        worker_program, worker_prefix = worker_process_command(
            "openseespy_studio.solver_worker"
        )
        process.setProgram(worker_program)
        process.setArguments([
            *worker_prefix,
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
            f"$host.UI.RawUI.WindowTitle='SARE - Job {job_id}'; "
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
                "Live output remains available in the SARE Console."
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
                "The SARE application remains available."
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
            self._last_result_cache_key = (
                ("job", job.job_id)
                if job is not None
                else None
            )
            self.results_panel.set_result(
                result,
                cache_key=self._last_result_cache_key,
            )
            moment_curvature = result.get("moment_curvature", {})
            is_moment_curvature = (
                isinstance(moment_curvature, dict)
                and moment_curvature.get("kind") == "moment-curvature"
            )
            if is_moment_curvature:
                self.results_panel.show_solution_result("MomentCurvature")
                self.results_dock.show()
                self.results_dock.raise_()
            analysis_type = str(result.get("analysis", {}).get("type", ""))
            if analysis_type == "Modal":
                modes = result.get("modes", {})
                if isinstance(modes, dict) and modes:
                    first_mode = min(int(key) for key in modes)
                    self.viewport.show_mode_shape(
                        result,
                        first_mode,
                        scale=1.0,
                        cache_key=self._last_result_cache_key,
                    )
            elif result.get("final") and not is_moment_curvature:
                self.viewport.show_deformed_shape(
                    result,
                    scale=10.0,
                    cache_key=self._last_result_cache_key,
                )

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
        calibration = self._calibration_process
        if (
            calibration is not None
            and calibration.state() != QProcess.NotRunning
        ):
            calibration.kill()
            calibration.waitForFinished(1000)
        self._calibration_process = None
        self._calibration_stop_requested = False
        self._cleanup_calibration_files()
        if "calibration" in self.actions:
            self.actions["calibration"].setText("Calibration...")
        if "run" in self.actions:
            self.actions["run"].setEnabled(True)

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
        self._last_result_cache_key = None
        self._active_solution_result_tag = None
        self.viewport.clear_result_overlay()
        self.results_panel.clear_all()

    def _apply_selected_calibration_case(
        self,
        row: object,
    ) -> None:
        if not isinstance(row, dict):
            QMessageBox.warning(
                self,
                "Calibration",
                "The selected calibration case is invalid.",
            )
            return

        score = row.get("score")
        try:
            valid_score = score is not None and math.isfinite(
                float(score)
            )
        except (TypeError, ValueError):
            valid_score = False
        if (
            not valid_score
            or str(row.get("status", "")).lower() != "scored"
        ):
            QMessageBox.warning(
                self,
                "Calibration",
                "Only a successfully scored calibration case can be "
                "applied to the model.",
            )
            return

        values = row.get("values", {})
        if not isinstance(values, dict) or not values:
            QMessageBox.warning(
                self,
                "Calibration",
                "The selected case contains no material parameters.",
            )
            return

        try:
            case = CalibrationCase(
                case_id=int(row.get("case_id", 0) or 0),
                values={
                    str(key): float(value)
                    for key, value in values.items()
                },
            )
            changes = calibration_case_changes(
                self.project,
                case,
            )
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Calibration Case No Longer Matches Model",
                str(exc),
            )
            return

        if not any(bool(change.get("changed")) for change in changes):
            QMessageBox.information(
                self,
                "Calibration",
                "The selected case is already applied; all listed project "
                "parameters already match the calibrated values.",
            )
            return

        rank_raw = row.get("rank")
        try:
            rank = (
                int(rank_raw)
                if rank_raw is not None
                else None
            )
        except (TypeError, ValueError):
            rank = None

        preview = ApplyCalibrationCaseDialog(
            changes,
            case_id=case.case_id,
            rank=rank,
            score=float(score),
            parent=self,
        )
        if not preview.exec():
            return

        before = self.project.to_dict()
        try:
            updated = apply_calibration_case(
                self.project,
                case,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Apply Calibration Case",
                str(exc),
            )
            return

        self.project = updated
        self.model = updated.model
        changed_count = sum(
            bool(change.get("changed"))
            for change in changes
        )
        self._refresh_all(
            f"Applied calibration case {case.case_id} "
            f"({changed_count} material parameter(s))"
        )
        self._record_project_change(
            f"Apply calibration case {case.case_id}",
            before,
        )
        self.results_panel.show_calibration()
        self.results_dock.show()
        self.results_dock.raise_()
        self.results_panel.calibration_info.setText(
            f"Applied calibration case {case.case_id} to the model. "
            "Existing batch Jobs remain historical results; rerun "
            "Calibration to evaluate a new search around the updated model."
        )

    def _select_job_result(self, job_id: int) -> None:
        job = self._jobs.get(int(job_id))
        if job is None:
            return
        if job.results:
            self._last_result = dict(job.results)
            self._last_result_cache_key = ("job", job.job_id)
            self.results_panel.set_result(
                self._last_result,
                cache_key=self._last_result_cache_key,
            )
        self._show_job_properties(job.job_id)
        self.status_message.setText(
            f"Selected Job {job.job_id}: {job.analysis_name}"
        )

    def _show_deformation_result(
        self,
        scale: float,
        display_mode: str,
        representation: str,
        smooth_curvature: bool,
    ) -> None:
        if not self._last_result:
            self._offer_result_analysis_run(
                title="Deformed Shape",
            )
            return
        self.viewport.show_deformed_shape(
            self._last_result,
            scale=float(scale),
            display_mode=str(display_mode),
            representation=str(representation),
            smooth_curvature=bool(smooth_curvature),
            cache_key=self._last_result_cache_key,
        )
        label = {
            "deformed_only": "deformed only",
            "both": "undeformed + deformed",
            "undeformed_only": "undeformed only",
        }.get(str(display_mode), "deformed only")
        representation_label = {
            "actual_section": "actual section",
            "tube": "tube",
            "centerline": "centerline",
        }.get(str(representation), "actual section")
        self._sync_result_ribbon_controls(
            "deformation",
            str(display_mode),
            float(scale),
        )
        self.status_message.setText(
            f"Showing {label} · {representation_label} · "
            f"scale {float(scale):g}"
        )

    def _show_motion_frame_result(
        self,
        vectors: object,
        scale: float,
        auto_scale: bool,
        reference_magnitude: float,
        label: str,
    ) -> None:
        if not isinstance(vectors, dict) or not vectors:
            self.status_message.setText("No motion frame data available")
            return
        self.viewport.show_motion_frame(
            vectors,
            scale=float(scale),
            auto_scale=bool(auto_scale),
            reference_magnitude=float(reference_magnitude),
        )
        self.status_message.setText(str(label))

    def _show_node_contour_result(
        self,
        quantity: str,
        component: str,
    ) -> None:
        if not self._last_result:
            self._offer_result_analysis_run(
                title="Nodal Result",
            )
            return
        self.viewport.show_node_contour(
            self._last_result,
            str(quantity),
            str(component),
            cache_key=self._last_result_cache_key,
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
            self._offer_result_analysis_run(
                title="Hinge / Yield State",
            )
            return
        self.viewport.show_hinge_states(
            self._last_result,
            cache_key=self._last_result_cache_key,
        )
        self.status_message.setText(
            "Showing fiber-based plastic hinge / limit states"
        )

    def _show_member_force_result(
        self,
        component: str,
        scale: float,
    ) -> None:
        if not self._last_result:
            self._offer_result_analysis_run(
                title="Member Force Result",
            )
            return
        self.viewport.show_member_force_diagram(
            self._last_result,
            self.project.transformations,
            str(component),
            scale=float(scale),
            cache_key=self._last_result_cache_key,
        )
        self.status_message.setText(
            f"Showing local {component} diagram · scale "
            f"{float(scale):g}"
        )

    def _ensure_active_modal_result(self) -> bool:
        analysis = (
            self._last_result.get("analysis", {})
            if isinstance(self._last_result, dict)
            else {}
        )
        if (
            isinstance(analysis, dict)
            and str(analysis.get("type", "")) == "Modal"
        ):
            return True

        for job_id in sorted(self._jobs, reverse=True):
            job = self._jobs[job_id]
            if job.analysis_type == "Modal" and job.results:
                self._last_result = dict(job.results)
                self._last_result_cache_key = ("job", job.job_id)
                self.results_panel.set_result(
                    self._last_result,
                    cache_key=self._last_result_cache_key,
                )
                return True

        self._ensure_first_mode_modal_prerequisite("Mode Shape")
        return False

    def _show_mode_shape_result(
        self,
        mode: int,
        scale: float,
        display_mode: str,
        representation: str,
        smooth_curvature: bool,
    ) -> None:
        if not self._ensure_active_modal_result():
            return
        self.viewport.show_mode_shape(
            self._last_result,
            int(mode),
            scale=float(scale),
            display_mode=str(display_mode),
            representation=str(representation),
            smooth_curvature=bool(smooth_curvature),
            cache_key=self._last_result_cache_key,
        )
        label = {
            "deformed_only": "deformed only",
            "both": "undeformed + deformed",
            "undeformed_only": "undeformed only",
        }.get(str(display_mode), "deformed only")
        representation_label = {
            "actual_section": "actual section",
            "tube": "tube",
            "centerline": "centerline",
        }.get(str(representation), "actual section")
        self._sync_result_ribbon_controls(
            "mode",
            str(display_mode),
            float(scale),
        )
        self.status_message.setText(
            f"Showing mode {int(mode)} · {label} · "
            f"{representation_label} · scale {float(scale):g}"
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
        calibration = self._calibration_process
        if (
            calibration is not None
            and calibration.state() != QProcess.NotRunning
        ):
            calibration.kill()
            calibration.waitForFinished(1000)
        self._cleanup_analysis_files()
        self._cleanup_calibration_files()
        for path in self._external_log_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        self._external_log_paths.clear()
        super().closeEvent(event)

    def _show_keyboard_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "Project\n"
            "  Ctrl+N   New project\n"
            "  Ctrl+O   Open project\n"
            "  Ctrl+S   Save project\n"
            "  Ctrl+Q   Exit\n\n"
            "Edit / Selection\n"
            "  Ctrl+Z   Undo\n"
            "  Ctrl+Y   Redo\n"
            "  Delete   Delete selection\n"
            "  Esc      Clear selection\n\n"
            "Viewport\n"
            "  F        Zoom to selection\n"
            "  H        Hide selection\n"
            "  Shift+H  Show all\n"
            "  I        Isolate selection",
        )

    def _show_system_info(self) -> None:
        ok, runtime_detail = probe_opensees_runtime(timeout=10.0)
        version = QApplication.applicationVersion() or "Development"
        QMessageBox.information(
            self,
            f"{PRODUCT_NAME} - System Information",
            f"{PRODUCT_NAME}: {version}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"Platform: {sys.platform}\n"
            f"Runtime probe: {'OK' if ok else 'FAILED'}\n\n"
            f"{runtime_detail}",
        )

    def _show_about(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(f"About {PRODUCT_NAME}")
        app = QApplication.instance()
        if app is not None:
            dialog.setWindowIcon(app.windowIcon())
            dialog.setIconPixmap(app.windowIcon().pixmap(72, 72))

        version = QApplication.applicationVersion() or "Development"
        dialog.setText(
            f"<b style='font-size:18px'>{PRODUCT_NAME}</b><br>"
            f"<span style='color:#6f7d8c'>{PRODUCT_FULL_NAME}</span>"
        )
        dialog.setInformativeText(
            f"Version {version}\n\n"
            f"{PRODUCT_SHORT_DESCRIPTION} for nonlinear structural modelling, "
            f"analysis, simulation, and post-processing.\n\n"
            f"Current Python backend: {PRODUCT_BACKEND}.\n\n"
            "Developed by Tran-Van Han.\n"
            "Research software for structural and earthquake engineering.\n"
            "Built with OpenSeesPy, PySide6, and PyVista.\n\n"
            "github.com/tranhan1405/openseespy-studio"
        )
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec()

    def _not_implemented(self) -> None:
        action = self.sender()
        label = action.text() if isinstance(action, QAction) else "Command"
        self._log(f"{label}: planned for the next milestone")

    def _log(self, text: str) -> None:
        self.console.appendPlainText(">> " + text)
