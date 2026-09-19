from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
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
    parse_cyclic_protocol_text,
    parse_ground_motion_text,
    parse_node_weight_text,
)
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


class AnalysisTemplateDialog(QDialog):
    """Wizard-like editor for common nonlinear analysis workflows."""

    def __init__(
        self,
        *,
        default_node: int,
        units: dict[str, str] | None = None,
        initial_template: str = "Pushover",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Analysis Template")
        self.setModal(True)
        self.resize(620, 610)

        self.unit_system = UnitSystem.from_mapping(units)
        self._ground_motion_values: dict[int, list[float]] = {
            1: [],
            2: [],
            3: [],
        }

        root = QVBoxLayout(self)

        intro = QLabel(
            "Create a ready-to-run nonlinear workflow. Studio will add the "
            "analysis settings, required excitation/reference load objects, "
            "and a useful default Result set."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        top = QFormLayout()
        self.template = QComboBox()
        self.template.addItems(
            ["Pushover", "Cyclic", "Nonlinear Time History"]
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
        for dof, name in ((1, "X / UX"), (2, "Y / UY"), (3, "Z / UZ")):
            self.direction.addItem(name, dof)

        top.addRow("Template:", self.template)
        top.addRow("Name:", self.name)
        top.addRow("Solver strategy:", self.solver)
        top.addRow("Control / monitor node:", self.control_node)
        top.addRow("Direction:", self.direction)
        root.addLayout(top)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_pushover_page())
        self.pages.addWidget(self._build_cyclic_page())
        self.pages.addWidget(self._build_nlth_page())
        root.addWidget(self.pages, 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("Muted")
        root.addWidget(self.summary)

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
        self._sync_template(self.template.currentText())

    def _build_pushover_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.push_target = _double(0.10)
        self.push_increment = _double(0.001, 1.0e-12)
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
        form.addRow(
            f"Target displacement [{self.unit_system.length}]:",
            self.push_target,
        )
        form.addRow(
            f"Maximum increment [{self.unit_system.length}]:",
            self.push_increment,
        )
        form.addRow("Reference load distribution:", self.push_distribution)
        form.addRow("Mode number:", self.push_mode)
        form.addRow("Custom node weights:", self.push_custom)

        note = QLabel(
            "Studio creates a normalized lateral reference pattern and uses "
            "DisplacementControl at the selected node/DOF."
        )
        note.setWordWrap(True)
        form.addRow(note)

        for widget in (
            self.push_target,
            self.push_increment,
            self.push_distribution,
            self.push_mode,
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._update_summary)
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self._update_summary)
        self.push_distribution.currentTextChanged.connect(
            self._sync_pushover_distribution
        )
        self.push_custom.textChanged.connect(self._update_summary)
        self._sync_pushover_distribution(
            self.push_distribution.currentText()
        )
        return page

    def _build_cyclic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.cyclic_increment = _double(0.001, 1.0e-12)
        self.cyclic_distribution = QComboBox()
        self.cyclic_distribution.addItems(
            ["Uniform", "Triangular", "Mass proportional"]
        )
        form.addRow(
            f"Maximum branch increment [{self.unit_system.length}]:",
            self.cyclic_increment,
        )
        form.addRow("Reference load distribution:", self.cyclic_distribution)
        layout.addLayout(form)

        layout.addWidget(QLabel("Loading protocol:"))
        self.protocol = QTableWidget(4, 2)
        self.protocol.setHorizontalHeaderLabels(
            [
                f"Amplitude [{self.unit_system.length}]",
                "Cycles",
            ]
        )
        defaults = ((0.005, 2), (0.010, 2), (0.020, 2), (0.040, 2))
        for row, (amplitude, cycles) in enumerate(defaults):
            self.protocol.setItem(row, 0, QTableWidgetItem(f"{amplitude:g}"))
            self.protocol.setItem(row, 1, QTableWidgetItem(str(cycles)))
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
        layout.addWidget(self.protocol_preview)

        self.cyclic_increment.valueChanged.connect(self._update_summary)
        self.cyclic_distribution.currentTextChanged.connect(
            self._update_summary
        )
        self._update_cyclic_preview()
        return page

    def _build_nlth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        shared = QFormLayout()
        self.gm_column = QSpinBox()
        self.gm_column.setRange(1, 100)
        self.gm_column.setValue(1)
        self.gm_dt = _double(0.01, 1.0e-12)
        self.gm_unit = QComboBox()
        self.gm_unit.addItems(["g", "m/s²", "cm/s²"])
        shared.addRow("Acceleration column:", self.gm_column)
        shared.addRow("Record dt [s]:", self.gm_dt)
        shared.addRow("Input acceleration unit:", self.gm_unit)
        layout.addLayout(shared)

        self.gm_files: dict[int, QLineEdit] = {}
        self.gm_scales: dict[int, QDoubleSpinBox] = {}
        self.gm_previews: dict[int, QLabel] = {}
        axes = {1: "X", 2: "Y", 3: "Z"}

        for direction in (1, 2, 3):
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
            file_layout.addWidget(edit, 1)
            file_layout.addWidget(browse)
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
            layout.addLayout(form)
            scale.valueChanged.connect(self._update_summary)

        damping = QFormLayout()
        self.damping_ratio = _double(0.05, 0.0, 0.999999, 5)
        self.damping_mode_i = QSpinBox()
        self.damping_mode_i.setRange(1, 1000)
        self.damping_mode_i.setValue(1)
        self.damping_mode_j = QSpinBox()
        self.damping_mode_j.setRange(1, 1000)
        self.damping_mode_j.setValue(3)
        damping.addRow("Rayleigh damping ratio:", self.damping_ratio)
        damping.addRow("Rayleigh mode i:", self.damping_mode_i)
        damping.addRow("Rayleigh mode j:", self.damping_mode_j)
        layout.addLayout(damping)

        note = QLabel(
            "Assign one, two, or three components. All components use the "
            "common dt/column/unit above; each component has its own scale. "
            "Studio creates one Path TimeSeries + UniformExcitation per axis."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.gm_column.valueChanged.connect(
            self._reload_all_ground_motions
        )
        self.gm_dt.valueChanged.connect(self._update_summary)
        self.gm_unit.currentTextChanged.connect(self._update_summary)
        self.damping_ratio.valueChanged.connect(self._update_summary)
        self.damping_mode_i.valueChanged.connect(self._update_summary)
        self.damping_mode_j.valueChanged.connect(self._update_summary)
        return page

    def _sync_template(self, kind: str) -> None:
        index = {
            "Pushover": 0,
            "Cyclic": 1,
            "Nonlinear Time History": 2,
        }[str(kind)]
        self.pages.setCurrentIndex(index)
        current = self.name.text().strip()
        generic = (
            not current
            or current.startswith("Pushover")
            or current.startswith("Cyclic")
            or current.startswith("NLTH")
        )
        if generic:
            self.name.setText(
                {
                    0: "Pushover Template",
                    1: "Cyclic Template",
                    2: "NLTH Template",
                }[index]
            )
        self._update_summary()

    def _sync_pushover_distribution(self, kind: str) -> None:
        first_mode = str(kind) == "First-mode proportional"
        custom = str(kind) == "Custom"
        self.push_mode.setEnabled(first_mode)
        self.push_custom.setEnabled(custom)
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
            rows = parse_cyclic_protocol_text(text)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cyclic Protocol", str(exc))
            return

        self.protocol.blockSignals(True)
        try:
            self.protocol.setRowCount(len(rows))
            for row, (amplitude, cycles) in enumerate(rows):
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

    def _update_cyclic_preview(self, *_args) -> None:
        try:
            targets = expand_cyclic_protocol(self._protocol_rows())
        except (TypeError, ValueError) as exc:
            self.protocol_preview.setText(f"Protocol: {exc}")
            return
        short = ", ".join(f"{value:g}" for value in targets[:12])
        if len(targets) > 12:
            short += ", ..."
        self.protocol_preview.setText(
            f"{len(targets)} absolute targets: {short}"
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
                    previous = abs(float(item.text())) * 2.0
                except ValueError:
                    pass
        self.protocol.setItem(row, 0, QTableWidgetItem(f"{previous:g}"))
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

    def _browse_ground_motion(self, direction: int) -> None:
        axis = {1: "X", 2: "Y", 3: "Z"}[int(direction)]
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {axis} Ground Motion",
            "",
            "Ground motion (*.txt *.dat *.csv);;All files (*)",
        )
        if not path:
            return
        self.gm_files[int(direction)].setText(path)
        self._reload_ground_motion(int(direction))

    def _reload_ground_motion(self, direction: int) -> None:
        direction = int(direction)
        path = self.gm_files[direction].text().strip()
        axis = {1: "X", 2: "Y", 3: "Z"}[direction]
        if not path:
            self._ground_motion_values[direction] = []
            self.gm_previews[direction].setText(f"{axis}: not assigned")
            self._update_summary()
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            values = parse_ground_motion_text(
                text,
                column=self.gm_column.value(),
            )
        except (OSError, ValueError) as exc:
            self._ground_motion_values[direction] = []
            self.gm_previews[direction].setText(
                f"{axis}: cannot read record: {exc}"
            )
            self._update_summary()
            return

        self._ground_motion_values[direction] = values
        pga = max((abs(value) for value in values), default=0.0)
        duration = max(0, len(values) - 1) * self.gm_dt.value()
        self.gm_previews[direction].setText(
            f"{axis}: {len(values)} points · duration ≈ {duration:g} s · "
            f"raw PGA = {pga:g} {self.gm_unit.currentText()}"
        )
        self._update_summary()

    def _reload_all_ground_motions(self, *_args) -> None:
        for direction in (1, 2, 3):
            if self.gm_files[direction].text().strip():
                self._reload_ground_motion(direction)

    def _update_summary(self, *_args) -> None:
        kind = self.template.currentText()
        if kind == "Pushover":
            target = self.push_target.value()
            increment = self.push_increment.value()
            steps = (
                max(1, int(abs(target) / increment + 0.999999))
                if increment > 0.0
                else 0
            )
            text = (
                f"Pushover · {steps} nominal step(s) · "
                f"{self.push_distribution.currentText()} loading · "
                f"{self.solver.currentText()} solver"
            )
        elif kind == "Cyclic":
            try:
                count = len(expand_cyclic_protocol(self._protocol_rows()))
            except (TypeError, ValueError):
                count = 0
            text = (
                f"Cyclic · {count} target(s) · "
                f"{self.cyclic_distribution.currentText()} reference loading · "
                f"{self.solver.currentText()} solver"
            )
        else:
            active = [
                axis
                for axis, direction in (("X", 1), ("Y", 2), ("Z", 3))
                if self._ground_motion_values[direction]
            ]
            point_count = max(
                (
                    len(self._ground_motion_values[direction])
                    for direction in (1, 2, 3)
                ),
                default=0,
            )
            text = (
                f"NLTH {'+'.join(active) if active else '-'} · "
                f"{point_count} max point(s) · "
                f"dt={self.gm_dt.value():g} s · "
                f"ζ={self.damping_ratio.value():g} · "
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
        if kind == "Pushover":
            base.update(
                {
                    "target_displacement": self.push_target.value(),
                    "max_increment": self.push_increment.value(),
                    "distribution": self.push_distribution.currentText(),
                    "mode_number": self.push_mode.value(),
                    "custom_weights": (
                        parse_node_weight_text(
                            self.push_custom.toPlainText()
                        )
                        if self.push_distribution.currentText() == "Custom"
                        else None
                    ),
                }
            )
        elif kind == "Cyclic":
            base.update(
                {
                    "protocol_rows": self._protocol_rows(),
                    "max_increment": self.cyclic_increment.value(),
                    "distribution": self.cyclic_distribution.currentText(),
                }
            )
        else:
            components = []
            for direction in (1, 2, 3):
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
                    "damping_ratio": self.damping_ratio.value(),
                    "damping_mode_i": self.damping_mode_i.value(),
                    "damping_mode_j": self.damping_mode_j.value(),
                }
            )
        return base

    def _accept(self) -> None:
        try:
            request = self.request()
            if request["template"] == "Cyclic":
                expand_cyclic_protocol(request["protocol_rows"])
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
