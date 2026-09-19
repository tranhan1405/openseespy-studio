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
        self._ground_motion_values: list[float] = []

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
            ["Triangular", "Uniform", "Mass proportional"]
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
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._update_summary)
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self._update_summary)
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
        add.clicked.connect(self._add_protocol_row)
        remove.clicked.connect(self._remove_protocol_row)
        row.addWidget(add)
        row.addWidget(remove)
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
        form = QFormLayout()

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.gm_file = QLineEdit()
        self.gm_file.setReadOnly(True)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_ground_motion)
        file_layout.addWidget(self.gm_file, 1)
        file_layout.addWidget(browse)
        form.addRow("Ground-motion file:", file_row)

        self.gm_column = QSpinBox()
        self.gm_column.setRange(1, 100)
        self.gm_column.setValue(1)
        self.gm_column.valueChanged.connect(self._reload_ground_motion)
        self.gm_dt = _double(0.01, 1.0e-12)
        self.gm_unit = QComboBox()
        self.gm_unit.addItems(["g", "m/s²", "cm/s²"])
        self.gm_scale = _double(1.0)
        self.damping_ratio = _double(0.05, 0.0, 0.999999, 5)
        self.damping_mode_i = QSpinBox()
        self.damping_mode_i.setRange(1, 1000)
        self.damping_mode_i.setValue(1)
        self.damping_mode_j = QSpinBox()
        self.damping_mode_j.setRange(1, 1000)
        self.damping_mode_j.setValue(3)

        form.addRow("Acceleration column:", self.gm_column)
        form.addRow("Record dt [s]:", self.gm_dt)
        form.addRow("Input acceleration unit:", self.gm_unit)
        form.addRow("Scale factor:", self.gm_scale)
        form.addRow("Rayleigh damping ratio:", self.damping_ratio)
        form.addRow("Rayleigh mode i:", self.damping_mode_i)
        form.addRow("Rayleigh mode j:", self.damping_mode_j)
        layout.addLayout(form)

        self.gm_preview = QLabel(
            "Choose a TXT/CSV/DAT ground-motion file."
        )
        self.gm_preview.setWordWrap(True)
        layout.addWidget(self.gm_preview)

        note = QLabel(
            "The imported acceleration is converted into the current model "
            f"acceleration unit [{self.unit_system.acceleration_label}]. "
            "Studio creates a Path TimeSeries and UniformExcitation pattern."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        for widget in (
            self.gm_dt,
            self.gm_scale,
            self.damping_ratio,
            self.damping_mode_i,
            self.damping_mode_j,
        ):
            widget.valueChanged.connect(self._update_summary)
        self.gm_unit.currentTextChanged.connect(self._update_summary)
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

    def _browse_ground_motion(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Ground Motion",
            "",
            "Ground motion (*.txt *.dat *.csv);;All files (*)",
        )
        if not path:
            return
        self.gm_file.setText(path)
        self._reload_ground_motion()

    def _reload_ground_motion(self, *_args) -> None:
        path = self.gm_file.text().strip()
        if not path:
            self._ground_motion_values = []
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            values = parse_ground_motion_text(
                text,
                column=self.gm_column.value(),
            )
        except (OSError, ValueError) as exc:
            self._ground_motion_values = []
            self.gm_preview.setText(f"Cannot read record: {exc}")
            return
        self._ground_motion_values = values
        pga = max((abs(value) for value in values), default=0.0)
        duration = max(0, len(values) - 1) * self.gm_dt.value()
        self.gm_preview.setText(
            f"{len(values)} points · duration ≈ {duration:g} s · "
            f"raw PGA = {pga:g} {self.gm_unit.currentText()}"
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
            text = (
                f"NLTH · {len(self._ground_motion_values)} point(s) · "
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
            if not self._ground_motion_values:
                raise ValueError("Choose a valid ground-motion file first.")
            base.update(
                {
                    "ground_motion_values": list(
                        self._ground_motion_values
                    ),
                    "dt": self.gm_dt.value(),
                    "input_unit": self.gm_unit.currentText(),
                    "scale_factor": self.gm_scale.value(),
                    "direction": int(self.direction.currentData()),
                    "monitor_node": self.control_node.value(),
                    "damping_ratio": self.damping_ratio.value(),
                    "damping_mode_i": self.damping_mode_i.value(),
                    "damping_mode_j": self.damping_mode_j.value(),
                    "ground_motion_file": self.gm_file.text().strip(),
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
