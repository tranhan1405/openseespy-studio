from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
                "First-mode approximation",
                "Custom",
            ]
        )
        self.push_custom = QLineEdit()
        self.push_custom.setPlaceholderText(
            "node:weight, e.g. 11:1, 21:2, 31:3"
        )
        form.addRow(
            f"Target displacement [{self.unit_system.length}]:",
            self.push_target,
        )
        form.addRow(
            f"Maximum increment [{self.unit_system.length}]:",
            self.push_increment,
        )
        form.addRow("Reference load distribution:", self.push_distribution)
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
            self.push_custom,
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._update_summary)
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self._update_summary)
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._update_summary)
        self.push_distribution.currentTextChanged.connect(
            self._sync_custom_weight_fields
        )
        self._sync_custom_weight_fields()
        return page

    def _build_cyclic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.cyclic_increment = _double(0.001, 1.0e-12)
        self.cyclic_distribution = QComboBox()
        self.cyclic_distribution.addItems(
            [
                "Uniform",
                "Triangular",
                "Mass proportional",
                "First-mode approximation",
                "Custom",
            ]
        )
        self.cyclic_custom = QLineEdit()
        self.cyclic_custom.setPlaceholderText(
            "node:weight, optional custom reference pattern"
        )
        form.addRow(
            f"Maximum branch increment [{self.unit_system.length}]:",
            self.cyclic_increment,
        )
        form.addRow("Reference load distribution:", self.cyclic_distribution)
        form.addRow("Custom node weights:", self.cyclic_custom)
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
        import_csv = QPushButton("Import CSV/TXT...")
        add.clicked.connect(self._add_protocol_row)
        remove.clicked.connect(self._remove_protocol_row)
        import_csv.clicked.connect(self._import_protocol)
        row.addWidget(add)
        row.addWidget(remove)
        row.addWidget(import_csv)
        row.addStretch(1)
        layout.addLayout(row)

        self.protocol_preview = QLabel()
        self.protocol_preview.setWordWrap(True)
        layout.addWidget(self.protocol_preview)

        self.cyclic_increment.valueChanged.connect(self._update_summary)
        self.cyclic_distribution.currentTextChanged.connect(
            self._update_summary
        )
        self.cyclic_distribution.currentTextChanged.connect(
            self._sync_custom_weight_fields
        )
        self.cyclic_custom.textChanged.connect(self._update_summary)
        self._sync_custom_weight_fields()
        self._update_cyclic_preview()
        return page

    def _build_nlth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        component_title = QLabel("Ground-motion components")
        component_title.setObjectName("SectionTitle")
        layout.addWidget(component_title)

        grid = QGridLayout()
        for column, label in enumerate(
            ("Use", "Axis", "File", "", "Column", "Scale")
        ):
            grid.addWidget(QLabel(label), 0, column)

        self.gm_enabled: dict[int, QCheckBox] = {}
        self.gm_files: dict[int, QLineEdit] = {}
        self.gm_columns: dict[int, QSpinBox] = {}
        self.gm_scales: dict[int, QDoubleSpinBox] = {}

        for row, (direction, axis) in enumerate(
            ((1, "X"), (2, "Y"), (3, "Z")),
            start=1,
        ):
            enabled = QCheckBox()
            enabled.setChecked(direction == 1)
            file_edit = QLineEdit()
            file_edit.setReadOnly(True)
            browse = QPushButton("Browse...")
            column_spin = QSpinBox()
            column_spin.setRange(1, 100)
            column_spin.setValue(1)
            scale = _double(1.0)

            self.gm_enabled[direction] = enabled
            self.gm_files[direction] = file_edit
            self.gm_columns[direction] = column_spin
            self.gm_scales[direction] = scale

            grid.addWidget(enabled, row, 0)
            grid.addWidget(QLabel(axis), row, 1)
            grid.addWidget(file_edit, row, 2)
            grid.addWidget(browse, row, 3)
            grid.addWidget(column_spin, row, 4)
            grid.addWidget(scale, row, 5)

            browse.clicked.connect(
                lambda checked=False, d=direction:
                self._browse_ground_motion(d)
            )
            column_spin.valueChanged.connect(
                lambda _value, d=direction:
                self._reload_ground_motion(d)
            )
            enabled.toggled.connect(self._update_summary)
            scale.valueChanged.connect(self._update_summary)

        layout.addLayout(grid)

        form = QFormLayout()
        self.gm_dt = _double(0.01, 1.0e-12)
        self.gm_unit = QComboBox()
        self.gm_unit.addItems(["g", "m/s²", "cm/s²"])
        self.damping_ratio = _double(0.05, 0.0, 0.999999, 5)
        self.damping_mode_i = QSpinBox()
        self.damping_mode_i.setRange(1, 1000)
        self.damping_mode_i.setValue(1)
        self.damping_mode_j = QSpinBox()
        self.damping_mode_j.setRange(1, 1000)
        self.damping_mode_j.setValue(3)

        form.addRow("Record dt [s]:", self.gm_dt)
        form.addRow("Input acceleration unit:", self.gm_unit)
        form.addRow("Rayleigh damping ratio:", self.damping_ratio)
        form.addRow("Rayleigh mode i:", self.damping_mode_i)
        form.addRow("Rayleigh mode j:", self.damping_mode_j)
        layout.addLayout(form)

        self.gm_preview = QLabel(
            "Enable X/Y/Z and choose one TXT/CSV/DAT record per component."
        )
        self.gm_preview.setWordWrap(True)
        layout.addWidget(self.gm_preview)

        note = QLabel(
            "All enabled components use the same dt and input unit. "
            "Each component has its own column and scale factor. "
            "Acceleration is converted to "
            f"[{self.unit_system.acceleration_label}] before generation."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        for widget in (
            self.gm_dt,
            self.damping_ratio,
            self.damping_mode_i,
            self.damping_mode_j,
        ):
            widget.valueChanged.connect(self._update_summary)
        self.gm_dt.valueChanged.connect(
            lambda _value: self._update_ground_motion_preview()
        )
        self.gm_unit.currentTextChanged.connect(
            self._update_ground_motion_preview
        )
        return page

    def _sync_template(self, kind: str) -> None:
        index = {
            "Pushover": 0,
            "Cyclic": 1,
            "Nonlinear Time History": 2,
        }[str(kind)]
        self.pages.setCurrentIndex(index)
        self.direction.setEnabled(index != 2)
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

    @staticmethod
    def _parse_custom_weights(text: str) -> dict[int, float]:
        source = str(text).strip()
        if not source:
            return {}
        weights: dict[int, float] = {}
        for raw in source.replace(";", ",").split(","):
            token = raw.strip()
            if not token:
                continue
            separator = ":" if ":" in token else "=" if "=" in token else None
            if separator is None:
                raise ValueError(
                    "Custom weights must use node:weight pairs."
                )
            tag_text, weight_text = token.split(separator, 1)
            tag = int(tag_text.strip())
            weight = float(weight_text.strip())
            if tag <= 0:
                raise ValueError("Custom node tags must be positive.")
            weights[tag] = weight
        if not weights:
            raise ValueError("Custom distribution needs at least one weight.")
        return weights

    def _sync_custom_weight_fields(self, *_args) -> None:
        if hasattr(self, "push_custom"):
            self.push_custom.setEnabled(
                self.push_distribution.currentText() == "Custom"
            )
        if hasattr(self, "cyclic_custom"):
            self.cyclic_custom.setEnabled(
                self.cyclic_distribution.currentText() == "Custom"
            )

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
            text = Path(path).read_text(
                encoding="utf-8",
                errors="ignore",
            )
            rows = parse_cyclic_protocol_text(text)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Cyclic Protocol",
                str(exc),
            )
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
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Ground Motion { {1: 'X', 2: 'Y', 3: 'Z'}[int(direction)] }",
            "",
            "Ground motion (*.txt *.dat *.csv);;All files (*)",
        )
        if not path:
            return
        direction = int(direction)
        self.gm_files[direction].setText(path)
        self.gm_enabled[direction].setChecked(True)
        self._reload_ground_motion(direction)

    def _reload_ground_motion(self, direction: int) -> None:
        direction = int(direction)
        path = self.gm_files[direction].text().strip()
        if not path:
            self._ground_motion_values[direction] = []
            self._update_ground_motion_preview()
            return
        try:
            text = Path(path).read_text(
                encoding="utf-8",
                errors="ignore",
            )
            values = parse_ground_motion_text(
                text,
                column=self.gm_columns[direction].value(),
            )
        except (OSError, ValueError) as exc:
            self._ground_motion_values[direction] = []
            QMessageBox.warning(
                self,
                "Ground Motion",
                f"{ {1: 'X', 2: 'Y', 3: 'Z'}[direction] }: {exc}",
            )
            self._update_ground_motion_preview()
            return
        self._ground_motion_values[direction] = values
        self._update_ground_motion_preview()

    def _update_ground_motion_preview(self, *_args) -> None:
        details: list[str] = []
        for direction, axis in ((1, "X"), (2, "Y"), (3, "Z")):
            if not self.gm_enabled[direction].isChecked():
                continue
            values = self._ground_motion_values[direction]
            if not values:
                details.append(f"{axis}: no record")
                continue
            pga = max(abs(value) for value in values)
            duration = max(0, len(values) - 1) * self.gm_dt.value()
            details.append(
                f"{axis}: {len(values)} pts, {duration:g} s, "
                f"PGA={pga:g} {self.gm_unit.currentText()}, "
                f"scale={self.gm_scales[direction].value():g}"
            )
        self.gm_preview.setText(
            " · ".join(details)
            if details
            else "Enable at least one excitation component."
        )
        self._update_summary()


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
            enabled = [
                direction
                for direction in (1, 2, 3)
                if self.gm_enabled[direction].isChecked()
            ]
            axes = "/".join(
                {1: "X", 2: "Y", 3: "Z"}[direction]
                for direction in enabled
            ) or "-"
            points = max(
                (
                    len(self._ground_motion_values[direction])
                    for direction in enabled
                ),
                default=0,
            )
            text = (
                f"NLTH {axes} · up to {points} point(s) · "
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
                    "custom_weights": (
                        self._parse_custom_weights(
                            self.push_custom.text()
                        )
                        if self.push_distribution.currentText() == "Custom"
                        else {}
                    ),
                }
            )
        elif kind == "Cyclic":
            base.update(
                {
                    "protocol_rows": self._protocol_rows(),
                    "max_increment": self.cyclic_increment.value(),
                    "distribution": self.cyclic_distribution.currentText(),
                    "custom_weights": (
                        self._parse_custom_weights(
                            self.cyclic_custom.text()
                        )
                        if self.cyclic_distribution.currentText() == "Custom"
                        else {}
                    ),
                }
            )
        else:
            components: list[dict[str, object]] = []
            for direction, axis in ((1, "X"), (2, "Y"), (3, "Z")):
                if not self.gm_enabled[direction].isChecked():
                    continue
                values = self._ground_motion_values[direction]
                if not values:
                    raise ValueError(
                        f"Choose a valid {axis}-direction ground-motion file."
                    )
                components.append(
                    {
                        "direction": direction,
                        "label": axis,
                        "values": list(values),
                        "input_unit": self.gm_unit.currentText(),
                        "scale_factor": self.gm_scales[
                            direction
                        ].value(),
                        "file": self.gm_files[
                            direction
                        ].text().strip(),
                    }
                )
            if not components:
                raise ValueError(
                    "Enable at least one NLTH excitation component."
                )
            base.update(
                {
                    "components": components,
                    "dt": self.gm_dt.value(),
                    "monitor_node": self.control_node.value(),
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
