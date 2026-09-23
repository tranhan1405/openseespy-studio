from __future__ import annotations

from pathlib import Path
import math
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..calibration import (
    CalibrationParameter,
    CalibrationWeights,
    build_grid_cases,
    calibration_grid_size,
)
from ..postprocess import experimental_csv_series, parse_experimental_csv_text
from ..project import MATERIAL_PARAMETER_ORDER, ProjectDatabase


class CalibrationDialog(QDialog):
    def __init__(
        self,
        project: ProjectDatabase,
        parent=None,
        *,
        new_material_callback=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibration / Parameter Study")
        self.resize(900, 620)
        self.project = project
        self._new_material_callback = new_material_callback
        self._dataset: dict[str, Any] = {}
        self._dataset_path = ""

        root = QVBoxLayout(self)

        intro = QLabel(
            "Material calibration for the active Cyclic analysis. Grid sweep "
            "evaluates one fixed parameter grid; Adaptive refinement repeats "
            "the grid in progressively smaller windows around the best scored "
            "case. Geometry, loading protocol and analysis settings are unchanged."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        strategy_row = QHBoxLayout()
        strategy_row.addWidget(QLabel("Search strategy:"))
        self.strategy = QComboBox()
        self.strategy.addItem("Grid sweep", "grid")
        self.strategy.addItem(
            "Adaptive refinement · coarse → refine → refine",
            "adaptive",
        )
        self.strategy.currentIndexChanged.connect(
            self._strategy_changed
        )
        strategy_row.addWidget(self.strategy, 1)

        strategy_row.addWidget(QLabel("Rounds:"))
        self.adaptive_rounds = QSpinBox()
        self.adaptive_rounds.setRange(2, 5)
        self.adaptive_rounds.setValue(3)
        self.adaptive_rounds.valueChanged.connect(
            self._update_case_count
        )
        strategy_row.addWidget(self.adaptive_rounds)

        strategy_row.addWidget(QLabel("Shrink:"))
        self.adaptive_shrink = QDoubleSpinBox()
        self.adaptive_shrink.setRange(0.10, 0.90)
        self.adaptive_shrink.setSingleStep(0.05)
        self.adaptive_shrink.setDecimals(2)
        self.adaptive_shrink.setValue(0.50)
        self.adaptive_shrink.setToolTip(
            "Range width retained after each round. 0.50 halves each "
            "parameter window around the best scored case."
        )
        self.adaptive_shrink.valueChanged.connect(
            self._update_case_count
        )
        strategy_row.addWidget(self.adaptive_shrink)
        root.addLayout(strategy_row)
        self.strategy.setCurrentIndex(1)

        self.parameter_table = QTableWidget(3, 6)
        self.parameter_table.setHorizontalHeaderLabels(
            ["Use", "Material", "Parameter", "Min", "Max", "Points"]
        )
        self.parameter_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.parameter_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.parameter_table)

        material_actions = QHBoxLayout()
        material_actions.addStretch(1)
        self.new_material = QPushButton("New Material...")
        self.new_material.setEnabled(callable(self._new_material_callback))
        self.new_material.setToolTip(
            "Define a calibratable Material without closing Calibration."
        )
        self.new_material.clicked.connect(self._create_material_dependency)
        material_actions.addWidget(self.new_material)
        root.addLayout(material_actions)

        self.case_info = QLabel("")
        self.case_info.setWordWrap(True)

        for row in range(3):
            enabled = QCheckBox()
            enabled.setChecked(row == 0)
            self.parameter_table.setCellWidget(row, 0, enabled)

            material = QComboBox()
            self._populate_material_combo(material)
            material.currentIndexChanged.connect(
                lambda _index, r=row: self._material_changed(r)
            )
            self.parameter_table.setCellWidget(row, 1, material)

            parameter = QComboBox()
            parameter.currentIndexChanged.connect(
                lambda _index, r=row: self._parameter_changed(r)
            )
            self.parameter_table.setCellWidget(row, 2, parameter)

            minimum = QDoubleSpinBox()
            minimum.setDecimals(10)
            minimum.setRange(-1.0e18, 1.0e18)
            self.parameter_table.setCellWidget(row, 3, minimum)

            maximum = QDoubleSpinBox()
            maximum.setDecimals(10)
            maximum.setRange(-1.0e18, 1.0e18)
            self.parameter_table.setCellWidget(row, 4, maximum)

            points = QSpinBox()
            points.setRange(1, 25)
            points.setValue(3)
            points.valueChanged.connect(self._update_case_count)
            self.parameter_table.setCellWidget(row, 5, points)

            enabled.toggled.connect(self._update_case_count)
            minimum.valueChanged.connect(self._update_case_count)
            maximum.valueChanged.connect(self._update_case_count)
            self._material_changed(row)

        root.addWidget(self.case_info)

        experiment_title = QLabel("Experimental cyclic reference")
        experiment_title.setStyleSheet("font-weight: 600;")
        root.addWidget(experiment_title)

        file_row = QHBoxLayout()
        import_button = QPushButton("Import CSV / TSV...")
        import_button.clicked.connect(self._import_experiment)
        file_row.addWidget(import_button)
        self.experiment_file = QLabel("No experimental file loaded.")
        self.experiment_file.setWordWrap(True)
        file_row.addWidget(self.experiment_file, 1)
        root.addLayout(file_row)

        mapping = QHBoxLayout()
        mapping.addWidget(QLabel("X:"))
        self.exp_x = QComboBox()
        mapping.addWidget(self.exp_x, 1)
        mapping.addWidget(QLabel("×"))
        self.exp_x_scale = QDoubleSpinBox()
        self.exp_x_scale.setDecimals(8)
        self.exp_x_scale.setRange(-1.0e9, 1.0e9)
        self.exp_x_scale.setValue(1.0)
        mapping.addWidget(self.exp_x_scale)

        mapping.addWidget(QLabel("Y:"))
        self.exp_y = QComboBox()
        mapping.addWidget(self.exp_y, 1)
        mapping.addWidget(QLabel("×"))
        self.exp_y_scale = QDoubleSpinBox()
        self.exp_y_scale.setDecimals(8)
        self.exp_y_scale.setRange(-1.0e9, 1.0e9)
        self.exp_y_scale.setValue(1.0)
        mapping.addWidget(self.exp_y_scale)
        root.addLayout(mapping)

        objective_title = QLabel("Objective weights")
        objective_title.setStyleSheet("font-weight: 600;")
        root.addWidget(objective_title)

        objective_form = QFormLayout()
        self.weight_peak = self._weight_spin(1.0)
        objective_form.addRow("Peak |V| error", self.weight_peak)
        self.weight_reversal = self._weight_spin(1.0)
        objective_form.addRow(
            "Matched-reversal force NRMSE",
            self.weight_reversal,
        )
        self.weight_energy = self._weight_spin(1.0)
        objective_form.addRow(
            "Closed-cycle energy error",
            self.weight_energy,
        )
        self.weight_displacement = self._weight_spin(0.0)
        objective_form.addRow(
            "Max |u| error",
            self.weight_displacement,
        )
        root.addLayout(objective_form)

        note = QLabel(
            "Score = weighted mean of available absolute percentage errors. "
            "Lower score means closer agreement with the imported experiment; "
            "it is a calibration metric, not an acceptance criterion. "
            "Pareto analysis treats every objective with weight > 0 as an "
            "active minimization objective; weight magnitude affects the "
            "scalar score but not Pareto dominance."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #617080;")
        root.addWidget(note)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText("Run Batch")
        self.buttons.accepted.connect(self._accept_checked)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._strategy_changed()

    def _populate_material_combo(
        self,
        combo: QComboBox,
        *,
        select_tag: int | None = None,
    ) -> None:
        current = combo.currentData() if combo.count() else None
        wanted = select_tag if select_tag is not None else current
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select Material...", None)
        for tag in sorted(self.project.materials):
            item = self.project.materials[tag]
            if not item.parameters:
                continue
            combo.addItem(
                f"[{tag}] {item.name} · {item.material_type}",
                int(tag),
            )
        if wanted is not None:
            index = combo.findData(int(wanted))
            if index >= 0:
                combo.setCurrentIndex(index)
        elif combo.count() == 2:
            combo.setCurrentIndex(1)
        combo.blockSignals(False)

    def _create_material_dependency(self) -> None:
        if not callable(self._new_material_callback):
            return
        material = self._new_material_callback()
        if material is None:
            return
        for row in range(self.parameter_table.rowCount()):
            combo = self.parameter_table.cellWidget(row, 1)
            if not isinstance(combo, QComboBox):
                continue
            selected = (
                int(material.tag)
                if row == 0
                else combo.currentData()
            )
            self._populate_material_combo(
                combo,
                select_tag=selected,
            )
            self._material_changed(row)
        self._update_case_count()

    @staticmethod
    def _weight_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1000.0)
        spin.setDecimals(3)
        spin.setValue(float(value))
        return spin

    def _widgets(self, row: int):
        return (
            self.parameter_table.cellWidget(row, 0),
            self.parameter_table.cellWidget(row, 1),
            self.parameter_table.cellWidget(row, 2),
            self.parameter_table.cellWidget(row, 3),
            self.parameter_table.cellWidget(row, 4),
            self.parameter_table.cellWidget(row, 5),
        )

    def _material_changed(self, row: int) -> None:
        (
            _enabled,
            material_combo,
            parameter_combo,
            _minimum,
            _maximum,
            _points,
        ) = self._widgets(row)
        if not isinstance(material_combo, QComboBox):
            return
        if not isinstance(parameter_combo, QComboBox):
            return
        tag = material_combo.currentData()
        parameter_combo.blockSignals(True)
        parameter_combo.clear()
        if tag is not None:
            material = self.project.materials.get(int(tag))
            if material is not None:
                order = MATERIAL_PARAMETER_ORDER.get(
                    material.material_type,
                    tuple(material.parameters),
                )
                for name in order:
                    if name in material.parameters:
                        parameter_combo.addItem(str(name), str(name))
        parameter_combo.blockSignals(False)
        self._parameter_changed(row)

    def _parameter_changed(self, row: int) -> None:
        (
            _enabled,
            material_combo,
            parameter_combo,
            minimum,
            maximum,
            _points,
        ) = self._widgets(row)
        if not all(
            isinstance(widget, (QComboBox, QDoubleSpinBox))
            for widget in (
                material_combo,
                parameter_combo,
                minimum,
                maximum,
            )
        ):
            return
        tag = material_combo.currentData()
        parameter = parameter_combo.currentData()
        if tag is None or parameter is None:
            return
        material = self.project.materials.get(int(tag))
        if material is None:
            return
        current = float(material.parameters[str(parameter)])
        if abs(current) > 1.0e-15:
            low = min(0.8 * current, 1.2 * current)
            high = max(0.8 * current, 1.2 * current)
        else:
            low, high = -0.1, 0.1
        minimum.blockSignals(True)
        maximum.blockSignals(True)
        minimum.setValue(low)
        maximum.setValue(high)
        minimum.blockSignals(False)
        maximum.blockSignals(False)
        self._update_case_count()

    def _parameters(self) -> list[CalibrationParameter]:
        parameters: list[CalibrationParameter] = []
        for row in range(self.parameter_table.rowCount()):
            (
                enabled,
                material_combo,
                parameter_combo,
                minimum,
                maximum,
                points,
            ) = self._widgets(row)
            if not isinstance(enabled, QCheckBox) or not enabled.isChecked():
                continue
            if not isinstance(material_combo, QComboBox):
                continue
            if not isinstance(parameter_combo, QComboBox):
                continue
            tag = material_combo.currentData()
            parameter = parameter_combo.currentData()
            if tag is None or parameter is None:
                continue
            parameters.append(
                CalibrationParameter(
                    material_tag=int(tag),
                    parameter=str(parameter),
                    minimum=float(minimum.value()),
                    maximum=float(maximum.value()),
                    points=int(points.value()),
                )
            )
        return parameters

    def _strategy_changed(self, *_args) -> None:
        adaptive = self.strategy.currentData() == "adaptive"
        self.adaptive_rounds.setEnabled(adaptive)
        self.adaptive_shrink.setEnabled(adaptive)
        self._update_case_count()

    def _update_case_count(self, *_args) -> None:
        parameters = self._parameters()
        try:
            # Build once for duplicate-target/bounds validation.
            build_grid_cases(parameters, max_cases=96)
        except ValueError as exc:
            self.case_info.setText(str(exc))
            return

        per_round = calibration_grid_size(parameters)
        strategy = str(self.strategy.currentData() or "grid")
        if strategy == "adaptive":
            rounds = int(self.adaptive_rounds.value())
            upper = per_round * rounds
            if upper > 96:
                self.case_info.setText(
                    f"Adaptive plan can create up to {upper} cases, "
                    "exceeding the safety limit of 96. Reduce Points, "
                    "parameters, or rounds."
                )
                return
            self.case_info.setText(
                f"Adaptive: {per_round} case(s)/round × {rounds} rounds "
                f"≤ {upper} case(s). Duplicate center cases are skipped. "
                f"Each next window retains {self.adaptive_shrink.value():.0%} "
                "of the previous range."
            )
        else:
            if per_round > 64:
                self.case_info.setText(
                    f"Grid creates {per_round} cases, exceeding the "
                    "safety limit of 64."
                )
                return
            self.case_info.setText(
                f"Grid size: {per_round} case(s). "
                "Current safety limit: 64 cases."
            )

    def _import_experiment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Experimental Cyclic Data",
            "",
            "CSV/TSV files (*.csv *.txt *.tsv);;All files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(
                self,
                "Calibration",
                f"Could not read experimental file:\n{exc}",
            )
            return

        dataset = parse_experimental_csv_text(text)
        headers = dataset.get("headers", [])
        rows = dataset.get("rows", [])
        if not headers or not rows:
            QMessageBox.warning(
                self,
                "Calibration",
                "No usable numeric experimental data were found.",
            )
            return

        self._dataset = dict(dataset)
        self._dataset_path = path
        self.exp_x.clear()
        self.exp_y.clear()
        for index, header in enumerate(headers):
            self.exp_x.addItem(str(header), index)
            self.exp_y.addItem(str(header), index)

        def find_column(words: tuple[str, ...], fallback: int) -> int:
            for index, header in enumerate(headers):
                normalized = str(header).strip().lower()
                if any(word in normalized for word in words):
                    return index
            return min(fallback, len(headers) - 1)

        self.exp_x.setCurrentIndex(
            find_column(
                ("displacement", "disp", "drift", "stroke", "position"),
                0,
            )
        )
        self.exp_y.setCurrentIndex(
            find_column(
                ("force", "load", "shear"),
                1 if len(headers) > 1 else 0,
            )
        )
        self.experiment_file.setText(
            f"{Path(path).name} · {len(rows)} parsed row(s)"
        )

    def weights(self) -> CalibrationWeights:
        return CalibrationWeights(
            peak_force=self.weight_peak.value(),
            reversal_nrmse=self.weight_reversal.value(),
            cycle_energy=self.weight_energy.value(),
            max_displacement=self.weight_displacement.value(),
        )

    def request(self) -> dict[str, Any]:
        parameters = self._parameters()
        strategy = str(self.strategy.currentData() or "grid")
        if strategy == "adaptive":
            per_round = calibration_grid_size(parameters)
            rounds = int(self.adaptive_rounds.value())
            upper = per_round * rounds
            if upper > 96:
                raise ValueError(
                    f"Adaptive plan can create up to {upper} cases, "
                    "exceeding the safety limit of 96."
                )
            # Validate duplicate targets and numerical ranges.
            build_grid_cases(parameters, max_cases=96)
            cases: list[Any] = []
        else:
            cases = build_grid_cases(parameters, max_cases=64)
            rounds = 1
        if not self._dataset:
            raise ValueError(
                "Import experimental cyclic displacement-force data first."
            )
        x_column = self.exp_x.currentData()
        y_column = self.exp_y.currentData()
        if x_column is None or y_column is None:
            raise ValueError("Select experimental X and Y columns.")
        x, y = experimental_csv_series(
            self._dataset,
            int(x_column),
            int(y_column),
            x_scale=float(self.exp_x_scale.value()),
            y_scale=float(self.exp_y_scale.value()),
        )
        if len(x) < 3 or len(y) < 3:
            raise ValueError(
                "Experimental X/Y selection needs at least three numeric "
                "paired points."
            )
        weights = self.weights()
        weights.normalized()
        return {
            "strategy": strategy,
            "parameters": parameters,
            "cases": cases,
            "adaptive_rounds": rounds,
            "adaptive_shrink_ratio": float(
                self.adaptive_shrink.value()
            ),
            "experiment_x": x,
            "experiment_y": y,
            "experiment_path": self._dataset_path,
            "weights": weights,
        }

    def _accept_checked(self) -> None:
        try:
            self.request()
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration", str(exc))
            return
        self.accept()



class ApplyCalibrationCaseDialog(QDialog):
    def __init__(
        self,
        changes: list[dict[str, Any]],
        *,
        case_id: int,
        rank: int | None,
        score: float | None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Apply Calibration Case")
        self.resize(760, 420)

        root = QVBoxLayout(self)
        rank_text = str(rank) if rank is not None else "-"
        score_text = (
            f"{float(score):.6g}%"
            if score is not None and math.isfinite(float(score))
            else "-"
        )
        heading = QLabel(
            f"<b>Case {int(case_id)}</b> · rank {rank_text} · "
            f"calibration score {score_text}"
        )
        root.addWidget(heading)

        description = QLabel(
            "Review the current project values against the calibrated case. "
            "Applying changes only the listed material parameters; geometry, "
            "sections, loading and analysis settings are preserved."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        table = QTableWidget(len(changes), 6)
        table.setHorizontalHeaderLabels(
            [
                "Material",
                "Type",
                "Parameter",
                "Current",
                "Calibrated",
                "Δ [%]",
            ]
        )
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)

        changed_count = 0
        for row, change in enumerate(changes):
            old_value = float(change["old_value"])
            new_value = float(change["new_value"])
            if bool(change.get("changed", True)):
                changed_count += 1
            if abs(old_value) > 1.0e-15:
                delta = (new_value - old_value) / abs(old_value) * 100.0
                delta_text = f"{delta:.6g}"
            elif abs(new_value) <= 1.0e-15:
                delta_text = "0"
            else:
                delta_text = "n/a"

            values = [
                f"[{int(change['material_tag'])}] {change['material_name']}",
                str(change["material_type"]),
                str(change["parameter"]),
                f"{old_value:.10g}",
                f"{new_value:.10g}",
                delta_text,
            ]
            for column, value in enumerate(values):
                table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        root.addWidget(table, 1)

        warning = QLabel(
            f"{changed_count} parameter value(s) will change. "
            "The operation is added to the project Undo stack, so Ctrl+Z "
            "restores the previous values. Existing calibration Jobs remain "
            "historical results from the completed batch."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #617080;")
        root.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Apply to Model")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
