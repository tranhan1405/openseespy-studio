from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis_templates import (
    SOLVER_PRESETS,
    expand_cyclic_protocol,
    infer_height_axis,
    lateral_load_weights,
    parse_cyclic_protocol_text,
    parse_cyclic_targets_text,
    parse_node_weight_text,
    structure_reference_height,
)
from ..ground_motion_library import (
    GROUND_MOTION_LIBRARY,
    common_scale_factor_for_target_pga,
    load_bundled_ground_motion_record,
    pga_in_g,
    parse_ground_motion_record_text,
    record_preset,
    scale_factor_for_target_pga,
)
from ..project import ProjectDatabase
from ..units import UnitSystem


def _double(
    value: float,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 8,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(low, high)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


class CyclicProtocolPreview(QWidget):
    """Compact displacement/drift target-path preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._targets: list[float] = []
        self.setMinimumHeight(120)

    def set_targets(self, targets: list[float]) -> None:
        self._targets = [0.0] + [float(value) for value in targets]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if len(self._targets) < 2:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No valid cyclic protocol",
            )
            return

        left, right = 36.0, max(37.0, float(self.width()) - 10.0)
        top, bottom = 10.0, max(11.0, float(self.height()) - 24.0)
        max_abs = max(abs(value) for value in self._targets)
        max_abs = max(max_abs, 1.0e-12)
        count = max(1, len(self._targets) - 1)

        zero_y = 0.5 * (top + bottom)
        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(QPointF(left, zero_y), QPointF(right, zero_y))
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))

        points: list[QPointF] = []
        for index, value in enumerate(self._targets):
            x = left + (right - left) * index / count
            y = zero_y - 0.5 * (bottom - top) * value / max_abs
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor("#2f80ed"), 2))
        for first, second in zip(points, points[1:]):
            painter.drawLine(first, second)

        painter.setPen(QColor("#718195"))
        painter.drawText(
            4,
            int(top + 12),
            f"+{max_abs:g}",
        )
        painter.drawText(
            4,
            int(bottom),
            f"-{max_abs:g}",
        )
        painter.drawText(
            int(max(left, right - 55)),
            int(self.height() - 5),
            "target",
        )


class GroundMotionPlotWidget(QWidget):
    """Lightweight acceleration-time preview without extra plotting deps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: list[tuple[str, list[float]]] = []
        self._dt = 0.01
        self._unit = "g"
        self.setMinimumSize(640, 300)

    def set_data(
        self,
        series: list[tuple[str, list[float]]],
        *,
        dt: float,
        unit: str,
    ) -> None:
        self._series = [
            (str(label), [float(value) for value in values])
            for label, values in series
            if values
        ]
        self._dt = max(float(dt), 1.0e-15)
        self._unit = str(unit)
        self.update()

    @property
    def series_count(self) -> int:
        return len(self._series)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if not self._series:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No ground-motion data",
            )
            return

        left = 62.0
        right = max(left + 10.0, float(self.width()) - 18.0)
        top = 24.0
        bottom = max(top + 10.0, float(self.height()) - 42.0)

        max_points = max(len(values) for _, values in self._series)
        max_time = max(0.0, (max_points - 1) * self._dt)
        max_abs = max(
            (
                abs(value)
                for _, values in self._series
                for value in values
            ),
            default=1.0,
        )
        max_abs = max(max_abs, 1.0e-12)

        zero_y = 0.5 * (top + bottom)
        painter.setPen(QPen(QColor("#d5dce5"), 1))
        painter.drawLine(QPointF(left, zero_y), QPointF(right, zero_y))
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))

        palette = (
            QColor("#1565c0"),
            QColor("#c62828"),
            QColor("#2e7d32"),
            QColor("#6a1b9a"),
            QColor("#ef6c00"),
            QColor("#455a64"),
        )

        for series_index, (label, values) in enumerate(self._series):
            if len(values) < 2:
                continue
            pen = QPen(palette[series_index % len(palette)], 1.5)
            painter.setPen(pen)

            # Decimate only for painting; all statistics/use in OpenSees keep
            # the full parsed record.
            target_points = max(300, int(right - left) * 2)
            stride = max(1, len(values) // target_points)
            indices = list(range(0, len(values), stride))
            if indices[-1] != len(values) - 1:
                indices.append(len(values) - 1)

            previous = None
            for index in indices:
                x = (
                    left
                    if max_points <= 1
                    else left
                    + (right - left) * index / max(1, max_points - 1)
                )
                y = zero_y - (
                    0.46
                    * (bottom - top)
                    * float(values[index])
                    / max_abs
                )
                point = QPointF(x, y)
                if previous is not None:
                    painter.drawLine(previous, point)
                previous = point

            legend_x = left + 8.0 + (series_index % 3) * 170.0
            legend_y = top + 14.0 + (series_index // 3) * 18.0
            painter.drawLine(
                QPointF(legend_x, legend_y),
                QPointF(legend_x + 18.0, legend_y),
            )
            painter.drawText(
                QPointF(legend_x + 24.0, legend_y + 4.0),
                label,
            )

        painter.setPen(QColor("#526273"))
        painter.drawText(4, int(top + 5), f"+{max_abs:.4g}")
        painter.drawText(8, int(zero_y + 4), "0")
        painter.drawText(4, int(bottom), f"-{max_abs:.4g}")
        painter.drawText(
            int(left),
            int(self.height() - 12),
            "0 s",
        )
        painter.drawText(
            int(max(left, right - 85)),
            int(self.height() - 12),
            f"{max_time:.4g} s",
        )
        painter.drawText(
            int(left + 8),
            int(top - 6),
            f"Acceleration [{self._unit}]",
        )


class GroundMotionPreviewDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        series: list[tuple[str, list[float]]],
        dt: float,
        unit: str,
        details: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 460)
        layout = QVBoxLayout(self)

        self.plot = GroundMotionPlotWidget(self)
        self.plot.set_data(series, dt=dt, unit=unit)
        layout.addWidget(self.plot, 1)

        info = QLabel(details)
        info.setWordWrap(True)
        info.setObjectName("Muted")
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        layout.addWidget(buttons)


class AnalysisTemplateDialog(QDialog):
    """Wizard-like editor for common nonlinear analysis workflows."""

    def __init__(
        self,
        *,
        default_node: int,
        units: dict[str, str] | None = None,
        initial_template: str = "Pushover",
        project: ProjectDatabase | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Analysis Template")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.resize(640, 620)
        self._initializing = True

        self.unit_system = UnitSystem.from_mapping(units)
        self.project = project
        self._ground_motion_values: dict[int, list[float]] = {
            1: [],
            2: [],
            3: [],
        }
        self._ground_motion_formats: dict[int, str] = {
            1: "",
            2: "",
            3: "",
        }
        self._ground_motion_builtin_keys: dict[int, str] = {
            1: "",
            2: "",
            3: "",
        }

        root = QVBoxLayout(self)

        body = QWidget()
        body_layout = QVBoxLayout(body)

        intro = QLabel(
            "Create a ready-to-run analysis workflow. Studio will add the "
            "analysis settings, required excitation/reference load objects, "
            "and a useful default Result set."
        )
        intro.setWordWrap(True)
        body_layout.addWidget(intro)

        top = QFormLayout()
        self.template = QComboBox()
        self.template.addItems(
            ["Modal", "Pushover", "Cyclic", "Nonlinear Time History"]
        )
        self.template.setCurrentText(initial_template)
        self.name = QLineEdit()
        self.solver = QComboBox()
        self.solver.addItems(list(SOLVER_PRESETS))
        self.solver.setCurrentText("Robust")
        self.control_node = QSpinBox()
        self.control_node.setRange(1, 2_147_483_647)
        self.control_node.setValue(int(default_node))
        self.direction = QComboBox()
        directions = [(1, "X / UX"), (2, "Y / UY")]
        if self.project is None or int(self.project.model.ndm) >= 3:
            directions.append((3, "Z / UZ"))
        for dof, name in directions:
            self.direction.addItem(name, dof)

        top.addRow("Template:", self.template)
        top.addRow("Name:", self.name)
        top.addRow("Solver strategy:", self.solver)
        top.addRow("Control / monitor node:", self.control_node)
        top.addRow("Direction:", self.direction)
        body_layout.addLayout(top)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_pushover_page())
        self.pages.addWidget(self._build_cyclic_page())
        self.pages.addWidget(self._build_nlth_page())
        self.pages.addWidget(self._build_modal_page())
        body_layout.addWidget(self.pages)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("Muted")
        body_layout.addWidget(self.summary)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Create Template")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.template.currentTextChanged.connect(self._sync_template)
        self.direction.currentIndexChanged.connect(self._update_summary)
        self.solver.currentTextChanged.connect(self._update_summary)
        self._initializing = False
        self._sync_template(self.template.currentText())
        self._update_pushover_preview()
        self._update_cyclic_preview()
        self._update_cyclic_load_preview()

    def _build_pushover_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        target_group = QGroupBox("Target & control")
        target_form = QFormLayout(target_group)

        self.push_target_mode = QComboBox()
        self.push_target_mode.addItems(
            ["Displacement", "Roof drift ratio"]
        )
        self.push_target = _double(0.10)
        self.push_drift = _double(2.0, -100.0, 100.0, decimals=4)
        self.push_height_axis = QComboBox()
        for axis, label in ((1, "X"), (2, "Y"), (3, "Z")):
            self.push_height_axis.addItem(label, axis)
        default_axis = (
            infer_height_axis(self.project)
            if self.project is not None
            else 3
        )
        self.push_height_axis.setCurrentIndex(
            max(0, self.push_height_axis.findData(default_axis))
        )
        self.push_auto_height = QCheckBox(
            "Auto from control node to model base"
        )
        self.push_auto_height.setChecked(self.project is not None)
        self.push_reference_height = _double(
            1.0, 1.0e-12, 1.0e20
        )
        self.push_increment = _double(0.001, 1.0e-12)

        target_form.addRow("Target definition:", self.push_target_mode)
        target_form.addRow(
            f"Target displacement [{self.unit_system.length}]:",
            self.push_target,
        )
        target_form.addRow("Roof drift ratio [%]:", self.push_drift)
        target_form.addRow("Height axis:", self.push_height_axis)
        target_form.addRow("Reference height:", self.push_auto_height)
        target_form.addRow(
            f"Height [{self.unit_system.length}]:",
            self.push_reference_height,
        )
        target_form.addRow(
            f"Maximum increment [{self.unit_system.length}]:",
            self.push_increment,
        )
        layout.addWidget(target_group)

        load_group = QGroupBox("Lateral loading")
        load_form = QFormLayout(load_group)

        self.push_load_source = QComboBox()
        self.push_load_source.addItem(
            "Auto-generate reference pattern",
            None,
        )
        if self.project is not None:
            for tag in sorted(self.project.load_patterns):
                pattern = self.project.load_patterns[tag]
                has_prescribed = any(
                    displacement.pattern_tag == tag
                    for displacement in (
                        self.project.prescribed_displacements.values()
                    )
                )
                if pattern.pattern_type == "Plain" and not has_prescribed:
                    self.push_load_source.addItem(
                        f"Existing {tag} - {pattern.name}",
                        int(tag),
                    )

        self.push_distribution = QComboBox()
        self.push_distribution.addItems(
            [
                "Triangular",
                "Uniform",
                "Mass proportional",
                "First-mode proportional",
                "Custom",
            ]
        )
        self.push_mode = QSpinBox()
        self.push_mode.setRange(1, 1000)
        self.push_mode.setValue(1)
        self.push_custom = QPlainTextEdit()
        self.push_custom.setPlaceholderText(
            "Custom node weights, one per line:\n"
            "101, 0.20\n102, 0.35\n103, 0.45"
        )
        self.push_custom.setMaximumHeight(92)
        self.push_load_preview = QLabel()
        self.push_load_preview.setWordWrap(True)
        self.push_load_preview.setObjectName("Muted")

        load_form.addRow("Load source:", self.push_load_source)
        load_form.addRow(
            "Reference load distribution:",
            self.push_distribution,
        )
        load_form.addRow("Mode number:", self.push_mode)
        load_form.addRow("Custom node weights:", self.push_custom)
        load_form.addRow("Preview:", self.push_load_preview)
        layout.addWidget(load_group)

        gravity_group = QGroupBox("Gravity / staged loading")
        gravity_form = QFormLayout(gravity_group)
        self.push_preload_gravity = QCheckBox(
            "Preload existing Plain patterns and hold with loadConst"
        )
        self.push_preload_gravity.setChecked(True)
        self.push_gravity_steps = QSpinBox()
        self.push_gravity_steps.setRange(1, 100000)
        self.push_gravity_steps.setValue(10)
        gravity_note = QLabel(
            "The selected pushover driving pattern is excluded from the "
            "gravity stage. Other existing Plain patterns are preloaded first."
        )
        gravity_note.setWordWrap(True)
        gravity_note.setObjectName("Muted")
        gravity_form.addRow(self.push_preload_gravity)
        gravity_form.addRow("Gravity steps:", self.push_gravity_steps)
        gravity_form.addRow(gravity_note)
        layout.addWidget(gravity_group)

        note = QLabel(
            "Studio uses DisplacementControl at the selected control node/DOF. "
            "Adaptive cutback and recovery follow the selected solver strategy."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.push_target_mode.currentTextChanged.connect(
            self._sync_pushover_target_mode
        )
        self.push_target.valueChanged.connect(self._update_summary)
        self.push_drift.valueChanged.connect(self._update_summary)
        self.push_height_axis.currentIndexChanged.connect(
            self._refresh_pushover_reference_height
        )
        self.push_height_axis.currentIndexChanged.connect(
            self._update_pushover_preview
        )
        self.push_auto_height.toggled.connect(
            self._refresh_pushover_reference_height
        )
        self.push_reference_height.valueChanged.connect(
            self._update_summary
        )
        self.push_increment.valueChanged.connect(self._update_summary)
        self.push_load_source.currentIndexChanged.connect(
            self._sync_pushover_load_source
        )
        self.push_distribution.currentTextChanged.connect(
            self._sync_pushover_distribution
        )
        self.push_mode.valueChanged.connect(self._update_pushover_preview)
        self.push_custom.textChanged.connect(self._update_pushover_preview)
        self.push_preload_gravity.toggled.connect(
            self._sync_pushover_gravity
        )
        self.push_gravity_steps.valueChanged.connect(self._update_summary)
        self.control_node.valueChanged.connect(
            self._refresh_pushover_reference_height
        )
        self.control_node.valueChanged.connect(
            self._update_pushover_preview
        )
        self.direction.currentIndexChanged.connect(
            self._update_pushover_preview
        )

        self._sync_pushover_target_mode(
            self.push_target_mode.currentText()
        )
        self._refresh_pushover_reference_height()
        self._sync_pushover_load_source()
        self._sync_pushover_gravity()
        return page

    def _build_cyclic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        protocol_group = QGroupBox("Control & loading protocol")
        protocol_form = QFormLayout(protocol_group)

        self.cyclic_control_info = QLabel(
            "Displacement-controlled: prescribed displacement/drift is the "
            "input; base shear / reaction force is the structural response."
        )
        self.cyclic_control_info.setWordWrap(True)
        self.cyclic_control_info.setObjectName("Muted")

        self.cyclic_protocol_mode = QComboBox()
        self.cyclic_protocol_mode.addItem(
            "Amplitude + cycles",
            "amplitude_cycles",
        )
        self.cyclic_protocol_mode.addItem(
            "Absolute targets",
            "absolute_targets",
        )

        self.cyclic_protocol_unit = QComboBox()
        self.cyclic_protocol_unit.addItems(
            ["Displacement", "Drift ratio [%]"]
        )

        self.cyclic_height_axis = QComboBox()
        for axis, label in ((1, "X"), (2, "Y"), (3, "Z")):
            self.cyclic_height_axis.addItem(label, axis)
        default_axis = (
            infer_height_axis(self.project)
            if self.project is not None
            else 3
        )
        self.cyclic_height_axis.setCurrentIndex(
            max(0, self.cyclic_height_axis.findData(default_axis))
        )

        self.cyclic_auto_height = QCheckBox(
            "Auto from control node to model base"
        )
        self.cyclic_auto_height.setChecked(self.project is not None)
        self.cyclic_reference_height = _double(
            1.0, 1.0e-12, 1.0e20
        )
        self.cyclic_increment = _double(0.001, 1.0e-12)
        self.cyclic_return_zero = QCheckBox(
            "Return to zero after the final amplitude block"
        )
        self.cyclic_return_zero.setChecked(True)

        protocol_form.addRow(self.cyclic_control_info)
        protocol_form.addRow(
            "Protocol definition:",
            self.cyclic_protocol_mode,
        )
        protocol_form.addRow(
            "Protocol quantity:",
            self.cyclic_protocol_unit,
        )
        protocol_form.addRow("Height axis:", self.cyclic_height_axis)
        protocol_form.addRow(
            "Reference height:",
            self.cyclic_auto_height,
        )
        protocol_form.addRow(
            f"Height [{self.unit_system.length}]:",
            self.cyclic_reference_height,
        )
        protocol_form.addRow(
            f"Maximum solver increment [{self.unit_system.length}]:",
            self.cyclic_increment,
        )
        protocol_form.addRow(self.cyclic_return_zero)
        layout.addWidget(protocol_group)

        layout.addWidget(QLabel("Loading protocol:"))
        self.protocol = QTableWidget(4, 2)
        defaults = ((0.005, 2), (0.010, 2), (0.020, 2), (0.040, 2))
        for row, (amplitude, cycles) in enumerate(defaults):
            self.protocol.setItem(
                row, 0, QTableWidgetItem(f"{amplitude:g}")
            )
            self.protocol.setItem(
                row, 1, QTableWidgetItem(str(cycles))
            )
        self.protocol.itemChanged.connect(self._update_cyclic_preview)
        layout.addWidget(self.protocol)

        row = QHBoxLayout()
        add = QPushButton("Add Row")
        remove = QPushButton("Remove Row")
        import_protocol = QPushButton("Import CSV/TXT...")
        add.clicked.connect(self._add_protocol_row)
        remove.clicked.connect(self._remove_protocol_row)
        import_protocol.clicked.connect(self._import_protocol)
        row.addWidget(add)
        row.addWidget(remove)
        row.addWidget(import_protocol)
        row.addStretch(1)
        layout.addLayout(row)

        self.protocol_preview = QLabel()
        self.protocol_preview.setWordWrap(True)
        self.protocol_preview.setObjectName("Muted")
        layout.addWidget(self.protocol_preview)
        self.cyclic_protocol_plot = CyclicProtocolPreview()
        layout.addWidget(self.cyclic_protocol_plot)

        load_group = QGroupBox("Reference lateral loading")
        load_form = QFormLayout(load_group)

        self.cyclic_load_source = QComboBox()
        self.cyclic_load_source.addItem(
            "Auto-generate reference pattern",
            None,
        )
        if self.project is not None:
            for tag in sorted(self.project.load_patterns):
                pattern = self.project.load_patterns[tag]
                has_prescribed = any(
                    displacement.pattern_tag == tag
                    for displacement in (
                        self.project.prescribed_displacements.values()
                    )
                )
                if pattern.pattern_type == "Plain" and not has_prescribed:
                    self.cyclic_load_source.addItem(
                        f"Existing {tag} - {pattern.name}",
                        int(tag),
                    )

        self.cyclic_distribution = QComboBox()
        self.cyclic_distribution.addItems(
            [
                "Uniform",
                "Triangular",
                "Mass proportional",
                "First-mode proportional",
                "Custom",
            ]
        )
        self.cyclic_mode = QSpinBox()
        self.cyclic_mode.setRange(1, 1000)
        self.cyclic_mode.setValue(1)
        self.cyclic_custom = QPlainTextEdit()
        self.cyclic_custom.setPlaceholderText(
            "Custom node weights, one per line:\n"
            "101, 0.20\n102, 0.35\n103, 0.45"
        )
        self.cyclic_custom.setMaximumHeight(92)
        self.cyclic_load_preview = QLabel()
        self.cyclic_load_preview.setWordWrap(True)
        self.cyclic_load_preview.setObjectName("Muted")

        load_form.addRow("Load source:", self.cyclic_load_source)
        load_form.addRow(
            "Reference load distribution:",
            self.cyclic_distribution,
        )
        load_form.addRow("Mode number:", self.cyclic_mode)
        load_form.addRow("Custom node weights:", self.cyclic_custom)
        load_form.addRow("Preview:", self.cyclic_load_preview)
        layout.addWidget(load_group)

        gravity_group = QGroupBox("Gravity / staged loading")
        gravity_form = QFormLayout(gravity_group)
        self.cyclic_preload_gravity = QCheckBox(
            "Preload existing Plain patterns and hold with loadConst"
        )
        self.cyclic_preload_gravity.setChecked(True)
        self.cyclic_gravity_steps = QSpinBox()
        self.cyclic_gravity_steps.setRange(1, 100000)
        self.cyclic_gravity_steps.setValue(10)
        gravity_note = QLabel(
            "The cyclic driving pattern is excluded from the gravity stage. "
            "Other existing Plain patterns are preloaded first."
        )
        gravity_note.setWordWrap(True)
        gravity_note.setObjectName("Muted")
        gravity_form.addRow(self.cyclic_preload_gravity)
        gravity_form.addRow("Gravity steps:", self.cyclic_gravity_steps)
        gravity_form.addRow(gravity_note)
        layout.addWidget(gravity_group)

        self.cyclic_protocol_mode.currentIndexChanged.connect(
            self._sync_cyclic_protocol_mode
        )
        self.cyclic_protocol_unit.currentTextChanged.connect(
            self._sync_cyclic_protocol_unit
        )
        self.cyclic_height_axis.currentIndexChanged.connect(
            self._refresh_cyclic_reference_height
        )
        self.cyclic_height_axis.currentIndexChanged.connect(
            self._update_cyclic_load_preview
        )
        self.cyclic_auto_height.toggled.connect(
            self._refresh_cyclic_reference_height
        )
        self.cyclic_reference_height.valueChanged.connect(
            self._update_cyclic_preview
        )
        self.cyclic_increment.valueChanged.connect(
            self._update_cyclic_preview
        )
        self.cyclic_return_zero.toggled.connect(
            self._update_cyclic_preview
        )

        self.cyclic_load_source.currentIndexChanged.connect(
            self._sync_cyclic_load_source
        )
        self.cyclic_distribution.currentTextChanged.connect(
            self._sync_cyclic_distribution
        )
        self.cyclic_mode.valueChanged.connect(
            self._update_cyclic_load_preview
        )
        self.cyclic_custom.textChanged.connect(
            self._update_cyclic_load_preview
        )
        self.cyclic_preload_gravity.toggled.connect(
            self._sync_cyclic_gravity
        )
        self.cyclic_gravity_steps.valueChanged.connect(
            self._update_summary
        )
        self.control_node.valueChanged.connect(
            self._refresh_cyclic_reference_height
        )
        self.control_node.valueChanged.connect(
            self._update_cyclic_load_preview
        )
        self.direction.currentIndexChanged.connect(
            self._update_cyclic_load_preview
        )

        self._sync_cyclic_protocol_mode()
        self._sync_cyclic_protocol_unit()
        self._refresh_cyclic_reference_height()
        self._sync_cyclic_load_source()
        self._sync_cyclic_gravity()
        return page

    def _build_nlth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._nlth_directions = (
            (1, 2, 3)
            if self.project is None or int(self.project.model.ndm) >= 3
            else (1, 2)
        )

        motion_group = QGroupBox("Ground motion & scaling")
        motion_layout = QVBoxLayout(motion_group)
        shared = QFormLayout()
        self.gm_library = QComboBox()
        for preset in GROUND_MOTION_LIBRARY:
            self.gm_library.addItem(preset.label, preset.key)

        self.gm_library_info = QLabel()
        self.gm_library_info.setWordWrap(True)
        self.gm_library_info.setObjectName("Muted")

        self.gm_column = QSpinBox()
        self.gm_column.setRange(1, 100)
        self.gm_column.setValue(1)
        self.gm_column.setToolTip(
            "Used for TXT/CSV/DAT files. PEER AT2 automatically reads "
            "all acceleration values after the NPTS/DT header."
        )
        self.gm_dt = _double(0.01, 1.0e-12)
        self.gm_unit = QComboBox()
        self.gm_unit.addItems(["g", "m/s²", "cm/s²"])

        self.gm_scale_mode = QComboBox()
        self.gm_scale_mode.addItem("Direct factor", "factor")
        self.gm_scale_mode.addItem(
            "Target PGA · each component independently",
            "target_pga",
        )
        self.gm_scale_mode.addItem(
            "Target PGA · common factor (preserve component ratios)",
            "target_common_pga",
        )
        self.gm_target_pga = _double(0.35, 1.0e-6, 10.0, 5)
        self.gm_target_pga.setSuffix(" g")
        self.gm_target_pga.setToolTip(
            "Independent target PGA scales each component separately. "
            "Common-factor target PGA scales all active components by one "
            "factor so the strongest component reaches the target."
        )

        shared.addRow("Benchmark reference:", self.gm_library)
        shared.addRow("", self.gm_library_info)
        shared.addRow("Acceleration column:", self.gm_column)
        shared.addRow("Record dt [s]:", self.gm_dt)
        shared.addRow("Input acceleration unit:", self.gm_unit)
        shared.addRow("Scaling:", self.gm_scale_mode)
        shared.addRow("Target PGA:", self.gm_target_pga)
        motion_layout.addLayout(shared)

        self.gm_files: dict[int, QLineEdit] = {}
        self.gm_scales: dict[int, QDoubleSpinBox] = {}
        self.gm_previews: dict[int, QLabel] = {}
        axes = {1: "X", 2: "Y", 3: "Z"}

        for direction in self._nlth_directions:
            axis = axes[direction]
            form = QFormLayout()
            file_row = QWidget()
            file_layout = QHBoxLayout(file_row)
            file_layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setReadOnly(True)
            browse = QPushButton(f"Browse {axis}...")
            browse.clicked.connect(
                lambda checked=False, d=direction:
                self._browse_ground_motion(d)
            )
            clear = QPushButton("Clear")
            clear.clicked.connect(
                lambda checked=False, d=direction:
                self._clear_ground_motion(d)
            )
            file_layout.addWidget(edit, 1)
            file_layout.addWidget(browse)
            file_layout.addWidget(clear)
            scale = _double(1.0)
            preview = QLabel(f"{axis}: not assigned")
            preview.setWordWrap(True)
            preview.setObjectName("Muted")
            self.gm_files[direction] = edit
            self.gm_scales[direction] = scale
            self.gm_previews[direction] = preview
            form.addRow(f"{axis} record:", file_row)
            form.addRow(f"{axis} scale:", scale)
            form.addRow("", preview)
            motion_layout.addLayout(form)
            scale.valueChanged.connect(
                lambda _value, d=direction:
                self._refresh_ground_motion_preview(d)
            )

        self.gm_analysis_preview = QLabel()
        self.gm_analysis_preview.setWordWrap(True)
        self.gm_analysis_preview.setObjectName("Muted")
        motion_layout.addWidget(self.gm_analysis_preview)
        layout.addWidget(motion_group)

        damping_group = QGroupBox("Damping")
        damping = QFormLayout(damping_group)
        self.nlth_use_damping = QCheckBox(
            "Use Rayleigh damping from two modal frequencies"
        )
        self.nlth_use_damping.setChecked(True)
        self.damping_ratio = _double(0.05, 0.0, 0.999999, 5)
        self.damping_mode_i = QSpinBox()
        self.damping_mode_i.setRange(1, 1000)
        self.damping_mode_i.setValue(1)
        self.damping_mode_j = QSpinBox()
        self.damping_mode_j.setRange(1, 1000)
        self.damping_mode_j.setValue(3)
        damping.addRow(self.nlth_use_damping)
        damping.addRow("Rayleigh damping ratio:", self.damping_ratio)
        damping.addRow("Rayleigh mode i:", self.damping_mode_i)
        damping.addRow("Rayleigh mode j:", self.damping_mode_j)
        layout.addWidget(damping_group)

        stage_group = QGroupBox("Mass & gravity / staged loading")
        stage = QFormLayout(stage_group)
        self.nlth_require_mass = QCheckBox(
            "Require positive nodal mass in every excitation direction"
        )
        self.nlth_require_mass.setChecked(True)
        self.nlth_preload_gravity = QCheckBox(
            "Preload existing Plain patterns and hold with loadConst"
        )
        self.nlth_preload_gravity.setChecked(True)
        self.nlth_gravity_steps = QSpinBox()
        self.nlth_gravity_steps.setRange(1, 100000)
        self.nlth_gravity_steps.setValue(10)
        stage.addRow("Mass check:", self.nlth_require_mass)
        stage.addRow(self.nlth_preload_gravity)
        stage.addRow("Gravity steps:", self.nlth_gravity_steps)
        layout.addWidget(stage_group)

        note = QLabel(
            "Assign one, two, or three translational components (two for a "
            "true 2D model). PEER AT2 can supply dt automatically. Studio "
            "creates one Path TimeSeries + UniformExcitation per active axis. "
            "OpenSees UniformExcitation nodal acceleration response is relative "
            "to the moving support/ground."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.gm_library.currentIndexChanged.connect(
            self._record_library_changed
        )
        self.gm_column.valueChanged.connect(
            self._reload_all_ground_motions
        )
        self.gm_dt.valueChanged.connect(
            self._refresh_all_ground_motion_previews
        )
        self.gm_unit.currentTextChanged.connect(
            self._ground_motion_unit_changed
        )
        self.gm_scale_mode.currentIndexChanged.connect(
            self._sync_ground_motion_scale_mode
        )
        self.gm_target_pga.valueChanged.connect(
            self._apply_target_pga_scaling
        )
        self.nlth_use_damping.toggled.connect(self._sync_nlth_damping)
        self.damping_ratio.valueChanged.connect(self._update_summary)
        self.damping_mode_i.valueChanged.connect(self._update_summary)
        self.damping_mode_j.valueChanged.connect(self._update_summary)
        self.nlth_preload_gravity.toggled.connect(self._sync_nlth_gravity)
        self.nlth_gravity_steps.valueChanged.connect(self._update_summary)
        self.nlth_require_mass.toggled.connect(self._update_summary)

        self._record_library_changed()
        self._sync_ground_motion_scale_mode()
        self._sync_nlth_damping()
        self._sync_nlth_gravity()
        return page

    def _build_modal_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.modal_modes = QSpinBox()
        self.modal_modes.setRange(1, 1000)
        self.modal_modes.setValue(6)

        self.modal_solver = QComboBox()
        self.modal_solver.addItem("ARPACK · general / sparse", "-genBandArpack")
        self.modal_solver.addItem("Full General LAPACK", "-fullGenLapack")
        self.modal_solver.addItem(
            "Symmetric Band LAPACK",
            "-symmBandLapack",
        )

        self.modal_require_mass = QCheckBox(
            "Require translational nodal mass before creating template"
        )
        self.modal_require_mass.setChecked(True)

        form.addRow("Number of modes:", self.modal_modes)
        form.addRow("Eigen solver:", self.modal_solver)
        form.addRow("Mass check:", self.modal_require_mass)

        note = QLabel(
            "Studio creates one Mode Shape result object per requested mode. "
            "The completed Modal Job stores eigenvalue, frequency, period, "
            "mode vectors and lumped-nodal-mass participation data for UX/UY/UZ."
        )
        note.setWordWrap(True)
        form.addRow(note)

        self.modal_modes.valueChanged.connect(self._update_summary)
        self.modal_solver.currentIndexChanged.connect(self._update_summary)
        self.modal_require_mass.toggled.connect(self._update_summary)
        return page

    def _sync_template(self, kind: str) -> None:
        index = {
            "Pushover": 0,
            "Cyclic": 1,
            "Nonlinear Time History": 2,
            "Modal": 3,
        }[str(kind)]
        self.pages.setCurrentIndex(index)
        current = self.name.text().strip()
        generic = (
            not current
            or current.startswith("Pushover")
            or current.startswith("Cyclic")
            or current.startswith("NLTH")
            or current.startswith("Modal")
        )
        if generic:
            self.name.setText(
                {
                    0: "Pushover Template",
                    1: "Cyclic Template",
                    2: "NLTH Template",
                    3: "Modal Template",
                }[index]
            )
        modal = str(kind) == "Modal"
        self.solver.setEnabled(not modal)
        self.control_node.setEnabled(not modal)
        self.direction.setEnabled(not modal)
        self._update_summary()

    def _sync_pushover_target_mode(self, kind: str) -> None:
        drift = str(kind) == "Roof drift ratio"
        self.push_target.setEnabled(not drift)
        self.push_drift.setEnabled(drift)
        self.push_height_axis.setEnabled(drift or self.push_distribution.currentText() == "Triangular")
        self.push_auto_height.setEnabled(drift and self.project is not None)
        self.push_reference_height.setEnabled(
            drift and not self.push_auto_height.isChecked()
        )
        self._update_summary()

    def _refresh_pushover_reference_height(self, *_args) -> None:
        use_auto = (
            self.push_auto_height.isChecked()
            and self.project is not None
        )
        self.push_reference_height.setEnabled(
            self.push_target_mode.currentText() == "Roof drift ratio"
            and not use_auto
        )
        if use_auto:
            try:
                height = structure_reference_height(
                    self.project,
                    control_node=self.control_node.value(),
                    height_axis=int(self.push_height_axis.currentData()),
                )
            except ValueError:
                height = None
            if height is not None:
                self.push_reference_height.blockSignals(True)
                self.push_reference_height.setValue(height)
                self.push_reference_height.blockSignals(False)
        self._update_summary()

    def _pushover_target_displacement(self) -> float:
        if self.push_target_mode.currentText() == "Roof drift ratio":
            return (
                self.push_drift.value()
                * 0.01
                * self.push_reference_height.value()
            )
        return self.push_target.value()

    def _sync_pushover_load_source(self, *_args) -> None:
        automatic = self.push_load_source.currentData() is None
        self.push_distribution.setEnabled(automatic)
        self.push_height_axis.setEnabled(
            self.push_target_mode.currentText() == "Roof drift ratio"
            or (
                automatic
                and self.push_distribution.currentText() == "Triangular"
            )
        )
        self._sync_pushover_distribution(
            self.push_distribution.currentText()
        )
        self._update_pushover_preview()

    def _sync_pushover_distribution(self, kind: str) -> None:
        automatic = self.push_load_source.currentData() is None
        first_mode = automatic and str(kind) == "First-mode proportional"
        custom = automatic and str(kind) == "Custom"
        self.push_mode.setEnabled(first_mode)
        self.push_custom.setEnabled(custom)
        self.push_height_axis.setEnabled(
            self.push_target_mode.currentText() == "Roof drift ratio"
            or (automatic and str(kind) == "Triangular")
        )
        self._update_pushover_preview()

    def _sync_pushover_gravity(self, *_args) -> None:
        self.push_gravity_steps.setEnabled(
            self.push_preload_gravity.isChecked()
        )
        self._update_summary()

    def _update_pushover_preview(self, *_args) -> None:
        if self._initializing:
            return
        driver_tag = self.push_load_source.currentData()
        if driver_tag is not None:
            if self.project is None:
                self.push_load_preview.setText(
                    f"Existing Plain pattern {driver_tag}."
                )
            else:
                nodal_count = sum(
                    1
                    for load in self.project.nodal_loads.values()
                    if load.pattern_tag == int(driver_tag)
                )
                self.push_load_preview.setText(
                    f"Existing Plain pattern {driver_tag} · "
                    f"{nodal_count} nodal load(s) · no new reference "
                    "pattern will be created."
                )
            self._update_summary()
            return

        distribution = self.push_distribution.currentText()
        if distribution == "First-mode proportional":
            self.push_load_preview.setText(
                f"Mode {self.push_mode.value()} weights will be taken from "
                "the latest compatible Modal job when the template is created."
            )
            self._update_summary()
            return
        if self.project is None:
            self.push_load_preview.setText(
                f"{distribution} normalized reference loading."
            )
            self._update_summary()
            return

        try:
            custom = (
                parse_node_weight_text(self.push_custom.toPlainText())
                if distribution == "Custom"
                else None
            )
            weights = lateral_load_weights(
                self.project,
                dof=int(self.direction.currentData()),
                distribution=distribution,
                custom_weights=custom,
                height_axis=int(self.push_height_axis.currentData()),
            )
            axis = int(self.push_height_axis.currentData()) - 1
            ordered = sorted(
                weights.items(),
                key=lambda item: (
                    self.project.model.nodes[item[0]].xyz[axis],
                    item[0],
                ),
            )
            shown = ", ".join(
                f"N{tag}={weight:.3g}"
                for tag, weight in ordered[:10]
            )
            if len(ordered) > 10:
                shown += ", ..."
            self.push_load_preview.setText(
                f"{len(weights)} active node(s), Σ|w|=1 · {shown}"
            )
        except (TypeError, ValueError) as exc:
            self.push_load_preview.setText(f"Preview: {exc}")
        self._update_summary()

    def _sync_cyclic_protocol_mode(self, *_args) -> None:
        absolute = (
            self.cyclic_protocol_mode.currentData() == "absolute_targets"
        )
        self.protocol.setColumnHidden(1, absolute)
        self.cyclic_return_zero.setEnabled(not absolute)
        self._sync_cyclic_protocol_unit()
        self._update_cyclic_preview()

    def _sync_cyclic_protocol_unit(self, *_args) -> None:
        drift = self.cyclic_protocol_unit.currentText() == "Drift ratio [%]"
        absolute = (
            self.cyclic_protocol_mode.currentData() == "absolute_targets"
        )
        if drift:
            first = "Target drift [%]" if absolute else "Amplitude drift [%]"
        else:
            first = (
                f"Target [{self.unit_system.length}]"
                if absolute
                else f"Amplitude [{self.unit_system.length}]"
            )
        self.protocol.setHorizontalHeaderLabels([first, "Cycles"])
        self.cyclic_height_axis.setEnabled(
            drift
            or (
                self.cyclic_load_source.currentData() is None
                and self.cyclic_distribution.currentText() == "Triangular"
            )
        )
        self.cyclic_auto_height.setEnabled(
            drift and self.project is not None
        )
        self.cyclic_reference_height.setEnabled(
            drift and not self.cyclic_auto_height.isChecked()
        )
        self._refresh_cyclic_reference_height()
        self._update_cyclic_preview()

    def _refresh_cyclic_reference_height(self, *_args) -> None:
        drift = self.cyclic_protocol_unit.currentText() == "Drift ratio [%]"
        use_auto = (
            drift
            and self.cyclic_auto_height.isChecked()
            and self.project is not None
        )
        self.cyclic_reference_height.setEnabled(
            drift and not use_auto
        )
        if use_auto:
            try:
                height = structure_reference_height(
                    self.project,
                    control_node=self.control_node.value(),
                    height_axis=int(self.cyclic_height_axis.currentData()),
                )
            except ValueError:
                height = None
            if height is not None:
                self.cyclic_reference_height.blockSignals(True)
                self.cyclic_reference_height.setValue(height)
                self.cyclic_reference_height.blockSignals(False)
        self._update_cyclic_preview()

    def _sync_cyclic_load_source(self, *_args) -> None:
        automatic = self.cyclic_load_source.currentData() is None
        self.cyclic_distribution.setEnabled(automatic)
        self._sync_cyclic_distribution(
            self.cyclic_distribution.currentText()
        )
        self._update_cyclic_load_preview()

    def _sync_cyclic_distribution(self, kind: str) -> None:
        automatic = self.cyclic_load_source.currentData() is None
        first_mode = automatic and str(kind) == "First-mode proportional"
        custom = automatic and str(kind) == "Custom"
        self.cyclic_mode.setEnabled(first_mode)
        self.cyclic_custom.setEnabled(custom)
        self.cyclic_height_axis.setEnabled(
            self.cyclic_protocol_unit.currentText() == "Drift ratio [%]"
            or (automatic and str(kind) == "Triangular")
        )
        self._update_cyclic_load_preview()

    def _sync_cyclic_gravity(self, *_args) -> None:
        self.cyclic_gravity_steps.setEnabled(
            self.cyclic_preload_gravity.isChecked()
        )
        self._update_summary()

    def _update_cyclic_load_preview(self, *_args) -> None:
        if self._initializing:
            return
        driver_tag = self.cyclic_load_source.currentData()
        if driver_tag is not None:
            if self.project is None:
                self.cyclic_load_preview.setText(
                    f"Existing Plain pattern {driver_tag}."
                )
            else:
                nodal_count = sum(
                    1
                    for load in self.project.nodal_loads.values()
                    if load.pattern_tag == int(driver_tag)
                )
                self.cyclic_load_preview.setText(
                    f"Existing Plain pattern {driver_tag} · "
                    f"{nodal_count} nodal load(s) · no new reference "
                    "pattern will be created."
                )
            self._update_summary()
            return

        distribution = self.cyclic_distribution.currentText()
        if distribution == "First-mode proportional":
            self.cyclic_load_preview.setText(
                f"Mode {self.cyclic_mode.value()} weights will be taken from "
                "the latest compatible Modal job when the template is created."
            )
            self._update_summary()
            return
        if self.project is None:
            self.cyclic_load_preview.setText(
                f"{distribution} normalized reference loading."
            )
            self._update_summary()
            return

        try:
            custom = (
                parse_node_weight_text(self.cyclic_custom.toPlainText())
                if distribution == "Custom"
                else None
            )
            weights = lateral_load_weights(
                self.project,
                dof=int(self.direction.currentData()),
                distribution=distribution,
                custom_weights=custom,
                height_axis=int(self.cyclic_height_axis.currentData()),
            )
            axis = int(self.cyclic_height_axis.currentData()) - 1
            ordered = sorted(
                weights.items(),
                key=lambda item: (
                    self.project.model.nodes[item[0]].xyz[axis],
                    item[0],
                ),
            )
            shown = ", ".join(
                f"N{tag}={weight:.3g}"
                for tag, weight in ordered[:10]
            )
            if len(ordered) > 10:
                shown += ", ..."
            self.cyclic_load_preview.setText(
                f"{len(weights)} active node(s), Σ|w|=1 · {shown}"
            )
        except (TypeError, ValueError) as exc:
            self.cyclic_load_preview.setText(f"Preview: {exc}")
        self._update_summary()

    def _import_protocol(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Cyclic Protocol",
            "",
            "Protocol (*.csv *.txt *.dat);;All files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            absolute = (
                self.cyclic_protocol_mode.currentData()
                == "absolute_targets"
            )
            data = (
                parse_cyclic_targets_text(text)
                if absolute
                else parse_cyclic_protocol_text(text)
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cyclic Protocol", str(exc))
            return

        self.protocol.blockSignals(True)
        try:
            self.protocol.setRowCount(len(data))
            if absolute:
                for row, target in enumerate(data):
                    self.protocol.setItem(
                        row,
                        0,
                        QTableWidgetItem(f"{float(target):g}"),
                    )
                    self.protocol.setItem(row, 1, QTableWidgetItem(""))
            else:
                for row, (amplitude, cycles) in enumerate(data):
                    self.protocol.setItem(
                        row,
                        0,
                        QTableWidgetItem(f"{amplitude:g}"),
                    )
                    self.protocol.setItem(
                        row,
                        1,
                        QTableWidgetItem(str(cycles)),
                    )
        finally:
            self.protocol.blockSignals(False)
        self._update_cyclic_preview()

    def _protocol_rows(self) -> list[tuple[float, int]]:
        rows: list[tuple[float, int]] = []
        for row in range(self.protocol.rowCount()):
            amplitude_item = self.protocol.item(row, 0)
            cycles_item = self.protocol.item(row, 1)
            if amplitude_item is None or not amplitude_item.text().strip():
                continue
            amplitude = float(amplitude_item.text())
            cycles = int(
                cycles_item.text()
                if cycles_item is not None and cycles_item.text().strip()
                else "1"
            )
            rows.append((amplitude, cycles))
        return rows

    def _protocol_absolute_targets(self) -> list[float]:
        targets: list[float] = []
        for row in range(self.protocol.rowCount()):
            item = self.protocol.item(row, 0)
            if item is None or not item.text().strip():
                continue
            targets.append(float(item.text()))
        if not targets:
            raise ValueError("Cyclic protocol needs at least one target.")
        return targets

    def _cyclic_raw_targets(self) -> list[float]:
        if self.cyclic_protocol_mode.currentData() == "absolute_targets":
            return self._protocol_absolute_targets()
        return expand_cyclic_protocol(
            self._protocol_rows(),
            finish_at_zero=self.cyclic_return_zero.isChecked(),
        )

    def _cyclic_displacement_targets(self) -> list[float]:
        targets = self._cyclic_raw_targets()
        if self.cyclic_protocol_unit.currentText() == "Drift ratio [%]":
            scale = 0.01 * self.cyclic_reference_height.value()
            return [value * scale for value in targets]
        return targets

    def _update_cyclic_preview(self, *_args) -> None:
        if self._initializing:
            return
        try:
            raw_targets = self._cyclic_raw_targets()
            targets = self._cyclic_displacement_targets()
            increment = self.cyclic_increment.value()
            if increment <= 0.0:
                raise ValueError(
                    "Maximum solver increment must be positive."
                )
            solver_steps = 0
            current = 0.0
            for target in targets:
                delta = float(target) - current
                if abs(delta) > 1.0e-15:
                    solver_steps += max(
                        1,
                        int(abs(delta) / increment + 0.999999999),
                    )
                current = float(target)
        except (TypeError, ValueError) as exc:
            self.protocol_preview.setText(f"Protocol: {exc}")
            self.cyclic_protocol_plot.set_targets([])
            self._update_summary()
            return

        self.cyclic_protocol_plot.set_targets(raw_targets)
        short = ", ".join(f"{value:g}" for value in raw_targets[:12])
        if len(raw_targets) > 12:
            short += ", ..."
        unit_note = (
            "%"
            if self.cyclic_protocol_unit.currentText() == "Drift ratio [%]"
            else self.unit_system.length
        )
        max_abs = max((abs(value) for value in raw_targets), default=0.0)
        return_zero = (
            "yes"
            if raw_targets and abs(raw_targets[-1]) <= 1.0e-15
            else "no"
        )
        self.protocol_preview.setText(
            f"{len(raw_targets)} reversal/target point(s) · "
            f"max |target|={max_abs:g} {unit_note} · "
            f"{solver_steps} solver increment(s) · "
            f"return to zero: {return_zero}. Targets: {short}"
        )
        self._update_summary()

    def _add_protocol_row(self) -> None:
        row = self.protocol.rowCount()
        self.protocol.insertRow(row)
        previous = 0.01
        if row:
            item = self.protocol.item(row - 1, 0)
            if item is not None:
                try:
                    previous = abs(float(item.text()))
                except ValueError:
                    pass
        if self.cyclic_protocol_mode.currentData() == "absolute_targets":
            value = previous * -1.0 if row % 2 else previous
            if abs(value) <= 1.0e-15:
                value = 0.01
            self.protocol.setItem(row, 0, QTableWidgetItem(f"{value:g}"))
            self.protocol.setItem(row, 1, QTableWidgetItem(""))
        else:
            value = previous * 2.0 if row else 0.01
            self.protocol.setItem(row, 0, QTableWidgetItem(f"{value:g}"))
            self.protocol.setItem(row, 1, QTableWidgetItem("2"))

    def _remove_protocol_row(self) -> None:
        rows = sorted(
            {index.row() for index in self.protocol.selectedIndexes()},
            reverse=True,
        )
        if not rows and self.protocol.rowCount():
            rows = [self.protocol.rowCount() - 1]
        for row in rows:
            self.protocol.removeRow(row)
        self._update_cyclic_preview()

    def _clear_auto_loaded_ground_motions(self) -> None:
        changed = False
        for direction in self._nlth_directions:
            if not self._ground_motion_builtin_keys.get(direction):
                continue
            self._ground_motion_builtin_keys[direction] = ""
            self._ground_motion_values[direction] = []
            self._ground_motion_formats[direction] = ""
            self.gm_files[direction].clear()
            self.gm_scales[direction].setValue(1.0)
            changed = True
        if changed:
            self._refresh_all_ground_motion_previews()

    def _record_library_changed(self, *_args) -> None:
        key = str(self.gm_library.currentData() or "custom")
        preset = record_preset(key)
        self._clear_auto_loaded_ground_motions()
        if preset.key == "custom":
            self.gm_library_info.setText(
                "Custom / Local Record · Browse a local file for at least "
                "one active direction."
            )
            self._update_summary()
            return

        year = f" ({preset.year})" if preset.year is not None else ""
        availability = (
            "Built-in record available and loaded automatically."
            if preset.bundled_resource
            else "Reference only; Browse a record file to use this preset."
        )
        self.gm_library_info.setText(
            f"{preset.event}{year} · {preset.station} · "
            f"Source: {preset.source}. {availability} {preset.notes}"
        )
        current = self.name.text().strip()
        if not current or current.startswith("NLTH"):
            self.name.setText(f"NLTH · {preset.label.split(' · ')[0]}")

        if preset.bundled_resource:
            direction = int(self.direction.currentData() or 1)
            if direction not in self._nlth_directions:
                direction = int(self._nlth_directions[0])
            self._load_bundled_ground_motion(direction, key)
        self._update_summary()

    def _load_bundled_ground_motion(
        self,
        direction: int,
        key: str,
    ) -> None:
        direction = int(direction)
        axis = {1: "X", 2: "Y", 3: "Z"}[direction]
        preset = record_preset(key)
        try:
            parsed = load_bundled_ground_motion_record(key)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Ground Motion Library",
                str(exc),
            )
            return

        if parsed.dt is not None:
            other_active = any(
                self._ground_motion_values[other]
                for other in self._nlth_directions
                if other != direction
            )
            current_dt = self.gm_dt.value()
            tolerance = max(1.0e-12, abs(current_dt) * 1.0e-6)
            if (
                other_active
                and abs(parsed.dt - current_dt) > tolerance
            ):
                QMessageBox.warning(
                    self,
                    "Ground Motion Library",
                    (
                        f"Built-in {axis} record dt={parsed.dt:g} s does not "
                        f"match the active component dt={current_dt:g} s. "
                        "Clear the other component or use records with the "
                        "same dt."
                    ),
                )
                return
            self.gm_dt.setValue(parsed.dt)

        if parsed.input_unit is not None:
            self.gm_unit.setCurrentText(parsed.input_unit)
        self._ground_motion_values[direction] = list(parsed.values)
        self._ground_motion_formats[direction] = (
            f"{parsed.format} · built-in"
        )
        self._ground_motion_builtin_keys[direction] = key
        self.gm_files[direction].setText(
            f"[Built-in] {preset.label}"
        )
        if self.gm_scale_mode.currentData() in {
            "target_pga",
            "target_common_pga",
        }:
            self._apply_target_pga_scaling()
        else:
            self._refresh_all_ground_motion_previews()

    def _clear_ground_motion(self, direction: int) -> None:
        direction = int(direction)
        if direction not in self._nlth_directions:
            return
        self.gm_files[direction].clear()
        self._ground_motion_builtin_keys[direction] = ""
        self._ground_motion_values[direction] = []
        self._ground_motion_formats[direction] = ""
        self.gm_scales[direction].setValue(1.0)
        self._apply_target_pga_scaling()
        self._refresh_all_ground_motion_previews()

    def _sync_nlth_damping(self, *_args) -> None:
        enabled = self.nlth_use_damping.isChecked()
        self.damping_ratio.setEnabled(enabled)
        self.damping_mode_i.setEnabled(enabled)
        self.damping_mode_j.setEnabled(enabled)
        self._update_summary()

    def _sync_nlth_gravity(self, *_args) -> None:
        self.nlth_gravity_steps.setEnabled(
            self.nlth_preload_gravity.isChecked()
        )
        self._update_summary()

    def _update_ground_motion_analysis_preview(self) -> None:
        active = [
            direction
            for direction in self._nlth_directions
            if self._ground_motion_values[direction]
        ]
        if not active:
            self.gm_analysis_preview.setText(
                "No active ground-motion component."
            )
            return
        max_points = max(
            len(self._ground_motion_values[direction])
            for direction in active
        )
        duration = max(0, max_points - 1) * self.gm_dt.value()
        step_count = max(1, max_points - 1)
        component_text = "+".join(
            {1: "X", 2: "Y", 3: "Z"}[direction]
            for direction in active
        )
        self.gm_analysis_preview.setText(
            f"Analysis window: {component_text} · longest record "
            f"{max_points} point(s) · {step_count} nominal interval(s) · "
            f"end time ≈ {duration:g} s. Shorter components become zero "
            "after their Path TimeSeries ends."
        )

    def _sync_ground_motion_scale_mode(self, *_args) -> None:
        mode = str(self.gm_scale_mode.currentData() or "factor")
        target_mode = mode in {"target_pga", "target_common_pga"}
        self.gm_target_pga.setEnabled(target_mode)
        for scale in self.gm_scales.values():
            scale.setEnabled(mode == "factor")
        if target_mode:
            self._apply_target_pga_scaling()
        else:
            self._refresh_all_ground_motion_previews()

    def _ground_motion_unit_changed(self, *_args) -> None:
        mode = str(self.gm_scale_mode.currentData() or "factor")
        if mode in {"target_pga", "target_common_pga"}:
            self._apply_target_pga_scaling()
        else:
            self._refresh_all_ground_motion_previews()

    def _browse_ground_motion(self, direction: int) -> None:
        axis = {1: "X", 2: "Y", 3: "Z"}[int(direction)]
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {axis} Ground Motion",
            "",
            "Ground motion (*.at2 *.AT2 *.txt *.dat *.csv *.json);;All files (*)",
        )
        if not path:
            return
        self._ground_motion_builtin_keys[int(direction)] = ""
        self.gm_files[int(direction)].setText(path)
        self._reload_ground_motion(int(direction))

    def _reload_ground_motion(self, direction: int) -> None:
        direction = int(direction)
        builtin_key = self._ground_motion_builtin_keys.get(direction, "")
        if builtin_key:
            self._load_bundled_ground_motion(direction, builtin_key)
            return
        path = self.gm_files[direction].text().strip()
        axis = {1: "X", 2: "Y", 3: "Z"}[direction]
        if not path:
            self._ground_motion_values[direction] = []
            self._ground_motion_formats[direction] = ""
            self.gm_previews[direction].setText(f"{axis}: not assigned")
            self._update_summary()
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            parsed = parse_ground_motion_record_text(
                text,
                column=self.gm_column.value(),
                filename=path,
            )
        except (OSError, ValueError) as exc:
            self._ground_motion_values[direction] = []
            self._ground_motion_formats[direction] = ""
            self.gm_previews[direction].setText(
                f"{axis}: cannot read record: {exc}"
            )
            self._update_summary()
            return

        if parsed.dt is not None:
            other_active = any(
                self._ground_motion_values[other]
                for other in self._nlth_directions
                if other != direction
            )
            current_dt = self.gm_dt.value()
            tolerance = max(1.0e-12, abs(current_dt) * 1.0e-6)
            if (
                other_active
                and abs(parsed.dt - current_dt) > tolerance
            ):
                QMessageBox.warning(
                    self,
                    "Ground Motion",
                    (
                        f"{axis} record dt={parsed.dt:g} s does not match "
                        f"the active component dt={current_dt:g} s."
                    ),
                )
                return
            self.gm_dt.setValue(parsed.dt)

        if parsed.input_unit is not None:
            self.gm_unit.setCurrentText(parsed.input_unit)

        self._ground_motion_values[direction] = list(parsed.values)
        self._ground_motion_formats[direction] = parsed.format

        if self.gm_scale_mode.currentData() in {
            "target_pga",
            "target_common_pga",
        }:
            self._apply_target_pga_scaling()
        else:
            self._refresh_ground_motion_preview(direction)
        self._update_summary()

    def _reload_all_ground_motions(self, *_args) -> None:
        for direction in self._nlth_directions:
            if self.gm_files[direction].text().strip():
                self._reload_ground_motion(direction)

    def _apply_target_pga_scaling(self, *_args) -> None:
        mode = str(self.gm_scale_mode.currentData() or "factor")
        if mode not in {"target_pga", "target_common_pga"}:
            self._refresh_all_ground_motion_previews()
            return

        target = self.gm_target_pga.value()
        input_unit = self.gm_unit.currentText()
        active = [
            direction
            for direction in self._nlth_directions
            if self._ground_motion_values[direction]
        ]
        if not active:
            self._refresh_all_ground_motion_previews()
            return

        if mode == "target_common_pga":
            try:
                common = common_scale_factor_for_target_pga(
                    [
                        self._ground_motion_values[direction]
                        for direction in active
                    ],
                    input_unit,
                    target,
                )
            except ValueError:
                self._refresh_all_ground_motion_previews()
                return
            factors = {direction: common for direction in active}
        else:
            factors = {}
            for direction in active:
                try:
                    factors[direction] = scale_factor_for_target_pga(
                        self._ground_motion_values[direction],
                        input_unit,
                        target,
                    )
                except ValueError:
                    continue

        for direction, factor in factors.items():
            scale = self.gm_scales[direction]
            scale.blockSignals(True)
            try:
                scale.setValue(factor)
            finally:
                scale.blockSignals(False)
        self._refresh_all_ground_motion_previews()

    def _refresh_ground_motion_preview(self, direction: int) -> None:
        direction = int(direction)
        axis = {1: "X", 2: "Y", 3: "Z"}[direction]
        values = self._ground_motion_values[direction]
        if not values:
            self.gm_previews[direction].setText(f"{axis}: not assigned")
            return
        try:
            raw_pga = pga_in_g(values, self.gm_unit.currentText())
        except ValueError:
            raw_pga = 0.0
        factor = self.gm_scales[direction].value()
        scaled_pga = raw_pga * abs(factor)
        duration = max(0, len(values) - 1) * self.gm_dt.value()
        format_name = self._ground_motion_formats[direction] or "record"
        self.gm_previews[direction].setText(
            f"{axis}: {len(values)} points · {format_name} · "
            f"duration ≈ {duration:g} s · raw PGA={raw_pga:.4g} g · "
            f"scale={factor:.4g} → {scaled_pga:.4g} g"
        )
        self._update_summary()

    def _refresh_all_ground_motion_previews(self, *_args) -> None:
        for direction in self._nlth_directions:
            self._refresh_ground_motion_preview(direction)
        self._update_ground_motion_analysis_preview()

    def _update_summary(self, *_args) -> None:
        if self._initializing:
            return
        kind = self.template.currentText()
        if kind == "Modal":
            text = (
                f"Modal · {self.modal_modes.value()} mode(s) · "
                f"{self.modal_solver.currentData()} · "
                + (
                    "mass check ON"
                    if self.modal_require_mass.isChecked()
                    else "mass check OFF"
                )
            )
        elif kind == "Pushover":
            target = self._pushover_target_displacement()
            increment = self.push_increment.value()
            steps = (
                max(1, int(abs(target) / increment + 0.999999))
                if increment > 0.0 and abs(target) > 0.0
                else 0
            )
            driver_tag = self.push_load_source.currentData()
            loading = (
                f"existing pattern {driver_tag}"
                if driver_tag is not None
                else self.push_distribution.currentText()
            )
            target_note = (
                f"{self.push_drift.value():g}% drift → "
                f"{target:g} {self.unit_system.length}"
                if self.push_target_mode.currentText() == "Roof drift ratio"
                else f"{target:g} {self.unit_system.length}"
            )
            gravity = (
                f"gravity {self.push_gravity_steps.value()} steps"
                if self.push_preload_gravity.isChecked()
                else "gravity preload OFF"
            )
            text = (
                f"Pushover · target {target_note} · "
                f"{steps} nominal step(s) · {loading} loading · "
                f"{gravity} · {self.solver.currentText()} solver"
            )
        elif kind == "Cyclic":
            try:
                raw_targets = self._cyclic_raw_targets()
                targets = self._cyclic_displacement_targets()
                count = len(targets)
                peak = max((abs(value) for value in raw_targets), default=0.0)
            except (TypeError, ValueError):
                count = 0
                peak = 0.0
            driver_tag = self.cyclic_load_source.currentData()
            loading = (
                f"existing pattern {driver_tag}"
                if driver_tag is not None
                else self.cyclic_distribution.currentText()
            )
            quantity = (
                f"drift, max {peak:g}%"
                if self.cyclic_protocol_unit.currentText() == "Drift ratio [%]"
                else f"displacement, max {peak:g} {self.unit_system.length}"
            )
            gravity = (
                f"gravity {self.cyclic_gravity_steps.value()} steps"
                if self.cyclic_preload_gravity.isChecked()
                else "gravity preload OFF"
            )
            text = (
                f"Cyclic · displacement-controlled · {count} target(s) · "
                f"{quantity} · {loading} loading · {gravity} · "
                f"{self.solver.currentText()} solver"
            )
        else:
            active = [
                {1: "X", 2: "Y", 3: "Z"}[direction]
                for direction in self._nlth_directions
                if self._ground_motion_values[direction]
            ]
            point_count = max(
                (
                    len(self._ground_motion_values[direction])
                    for direction in self._nlth_directions
                ),
                default=0,
            )
            duration = max(0, point_count - 1) * self.gm_dt.value()
            damping = (
                f"Rayleigh ζ={self.damping_ratio.value():g} "
                f"(modes {self.damping_mode_i.value()},"
                f"{self.damping_mode_j.value()})"
                if self.nlth_use_damping.isChecked()
                else "damping OFF"
            )
            gravity = (
                f"gravity {self.nlth_gravity_steps.value()} steps"
                if self.nlth_preload_gravity.isChecked()
                else "gravity preload OFF"
            )
            mass_check = (
                "mass check ON"
                if self.nlth_require_mass.isChecked()
                else "mass check OFF"
            )
            text = (
                f"NLTH {'+'.join(active) if active else '-'} · "
                f"duration≈{duration:g} s · dt={self.gm_dt.value():g} s · "
                f"{damping} · {gravity} · {mass_check} · "
                f"{self.solver.currentText()} solver"
            )
        self.summary.setText(text)

    def request(self) -> dict[str, object]:
        kind = self.template.currentText()
        base: dict[str, object] = {
            "template": kind,
            "name": self.name.text().strip(),
            "solver_preset": self.solver.currentText(),
            "control_node": self.control_node.value(),
            "control_dof": int(self.direction.currentData()),
        }
        if kind == "Modal":
            base.update(
                {
                    "num_modes": self.modal_modes.value(),
                    "eigen_solver": str(self.modal_solver.currentData()),
                    "require_nodal_mass": self.modal_require_mass.isChecked(),
                }
            )
        elif kind == "Pushover":
            base.update(
                {
                    "target_displacement": self._pushover_target_displacement(),
                    "target_mode": self.push_target_mode.currentText(),
                    "drift_ratio_percent": self.push_drift.value(),
                    "reference_height": self.push_reference_height.value(),
                    "height_axis": int(self.push_height_axis.currentData()),
                    "max_increment": self.push_increment.value(),
                    "driver_pattern_tag": self.push_load_source.currentData(),
                    "distribution": self.push_distribution.currentText(),
                    "mode_number": self.push_mode.value(),
                    "custom_weights": (
                        parse_node_weight_text(
                            self.push_custom.toPlainText()
                        )
                        if (
                            self.push_load_source.currentData() is None
                            and self.push_distribution.currentText() == "Custom"
                        )
                        else None
                    ),
                    "preload_gravity": self.push_preload_gravity.isChecked(),
                    "gravity_steps": self.push_gravity_steps.value(),
                }
            )
        elif kind == "Cyclic":
            base.update(
                {
                    "control_mode": "Displacement",
                    "protocol_mode": self.cyclic_protocol_mode.currentData(),
                    "protocol_unit": self.cyclic_protocol_unit.currentText(),
                    "protocol_rows": self._protocol_rows(),
                    "protocol_targets": self._cyclic_displacement_targets(),
                    "raw_protocol_targets": self._cyclic_raw_targets(),
                    "finish_at_zero": self.cyclic_return_zero.isChecked(),
                    "reference_height": self.cyclic_reference_height.value(),
                    "height_axis": int(self.cyclic_height_axis.currentData()),
                    "max_increment": self.cyclic_increment.value(),
                    "driver_pattern_tag": self.cyclic_load_source.currentData(),
                    "distribution": self.cyclic_distribution.currentText(),
                    "mode_number": self.cyclic_mode.value(),
                    "custom_weights": (
                        parse_node_weight_text(
                            self.cyclic_custom.toPlainText()
                        )
                        if (
                            self.cyclic_load_source.currentData() is None
                            and self.cyclic_distribution.currentText() == "Custom"
                        )
                        else None
                    ),
                    "preload_gravity": self.cyclic_preload_gravity.isChecked(),
                    "gravity_steps": self.cyclic_gravity_steps.value(),
                }
            )
        else:
            components = []
            for direction in self._nlth_directions:
                values = self._ground_motion_values[direction]
                if not values:
                    continue
                components.append(
                    {
                        "direction": direction,
                        "values": list(values),
                        "scale_factor": self.gm_scales[direction].value(),
                        "file": self.gm_files[direction].text().strip(),
                    }
                )
            if not components:
                raise ValueError(
                    "Choose at least one valid X, Y, or Z ground-motion file."
                )
            base.update(
                {
                    "components": components,
                    "dt": self.gm_dt.value(),
                    "input_unit": self.gm_unit.currentText(),
                    "monitor_node": self.control_node.value(),
                    "monitor_dof": int(self.direction.currentData()),
                    "damping_ratio": (
                        self.damping_ratio.value()
                        if self.nlth_use_damping.isChecked()
                        else 0.0
                    ),
                    "damping_mode_i": self.damping_mode_i.value(),
                    "damping_mode_j": self.damping_mode_j.value(),
                    "preload_gravity": self.nlth_preload_gravity.isChecked(),
                    "gravity_steps": self.nlth_gravity_steps.value(),
                    "require_nodal_mass": self.nlth_require_mass.isChecked(),
                }
            )
        return base

    def _accept(self) -> None:
        try:
            request = self.request()
            if request["template"] == "Pushover":
                if abs(float(request["target_displacement"])) <= 1.0e-15:
                    raise ValueError(
                        "Pushover target displacement must be nonzero."
                    )
                if float(request["max_increment"]) <= 0.0:
                    raise ValueError(
                        "Pushover maximum increment must be positive."
                    )
                if (
                    request["target_mode"] == "Roof drift ratio"
                    and float(request["reference_height"]) <= 0.0
                ):
                    raise ValueError(
                        "Pushover reference height must be positive."
                    )
            if request["template"] == "Cyclic":
                targets = [float(value) for value in request["protocol_targets"]]
                if not targets:
                    raise ValueError(
                        "Cyclic protocol needs at least one target."
                    )
                if float(request["max_increment"]) <= 0.0:
                    raise ValueError(
                        "Cyclic maximum solver increment must be positive."
                    )
                if (
                    request["protocol_unit"] == "Drift ratio [%]"
                    and float(request["reference_height"]) <= 0.0
                ):
                    raise ValueError(
                        "Cyclic reference height must be positive."
                    )
            if (
                request["template"] == "Nonlinear Time History"
                and request["damping_ratio"] > 0.0
                and request["damping_mode_i"] == request["damping_mode_j"]
            ):
                raise ValueError(
                    "Rayleigh damping needs two different modes."
                )
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Analysis Template", str(exc))
            return
        self.accept()
