from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QPointF, QRectF, QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..material_test import (
    MATERIAL_TEST_PROTOCOLS,
    MaterialTestSpec,
    build_material_test_script,
    default_material_test_spec,
)
from ..project import MaterialData
from ..runtime import build_worker_pythonpath, probe_opensees_runtime


class MaterialTestPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(620, 400)
        self._x: list[float] = []
        self._y: list[float] = []
        self._x_label = "Deformation"
        self._y_label = "Response"

    def set_result(
        self,
        deformation: list[float],
        response: list[float],
        *,
        x_label: str,
        y_label: str,
    ) -> None:
        self._x = [float(value) for value in deformation]
        self._y = [float(value) for value in response]
        self._x_label = str(x_label)
        self._y_label = str(y_label)
        self.update()

    @staticmethod
    def _expanded_range(values: list[float]) -> tuple[float, float]:
        low = min(values)
        high = max(values)
        if math.isclose(low, high, abs_tol=1.0e-15):
            pad = max(abs(low) * 0.1, 1.0)
            return low - pad, high + pad
        pad = 0.08 * (high - low)
        return low - pad, high + pad

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#ccd6df"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        plot = QRectF(
            74.0,
            28.0,
            max(120.0, self.width() - 105.0),
            max(120.0, self.height() - 92.0),
        )
        painter.setPen(QPen(QColor("#d8e0e8"), 1))
        painter.drawRect(plot)

        painter.setPen(QColor("#3c5064"))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 30.0, plot.width(), 24.0),
            Qt.AlignCenter,
            self._x_label,
        )
        painter.save()
        painter.translate(18.0, plot.center().y())
        painter.rotate(-90.0)
        painter.drawText(
            QRectF(-plot.height() / 2.0, 0.0, plot.height(), 24.0),
            Qt.AlignCenter,
            self._y_label,
        )
        painter.restore()

        if len(self._x) < 2 or len(self._x) != len(self._y):
            painter.setPen(QColor("#758596"))
            painter.drawText(
                plot,
                Qt.AlignCenter,
                "Run the material test to plot the OpenSees response.",
            )
            return

        xmin, xmax = self._expanded_range(self._x)
        ymin, ymax = self._expanded_range(self._y)

        def map_point(x: float, y: float) -> QPointF:
            px = plot.left() + (x - xmin) / (xmax - xmin) * plot.width()
            py = plot.bottom() - (y - ymin) / (ymax - ymin) * plot.height()
            return QPointF(px, py)

        painter.setPen(QPen(QColor("#b7c2cd"), 1))
        if xmin <= 0.0 <= xmax:
            painter.drawLine(map_point(0.0, ymin), map_point(0.0, ymax))
        if ymin <= 0.0 <= ymax:
            painter.drawLine(map_point(xmin, 0.0), map_point(xmax, 0.0))

        path = QPainterPath()
        path.moveTo(map_point(self._x[0], self._y[0]))
        for x, y in zip(self._x[1:], self._y[1:]):
            path.lineTo(map_point(x, y))
        painter.setPen(QPen(QColor("#c62828"), 2.0))
        painter.drawPath(path)

        painter.setPen(QColor("#637487"))
        painter.drawText(
            QPointF(plot.left(), plot.bottom() + 16.0),
            f"{xmin:.4g}",
        )
        right_text = f"{xmax:.4g}"
        metrics = painter.fontMetrics()
        painter.drawText(
            QPointF(plot.right() - metrics.horizontalAdvance(right_text), plot.bottom() + 16.0),
            right_text,
        )
        painter.drawText(
            QPointF(plot.left() - 8.0 - metrics.horizontalAdvance(f"{ymax:.4g}"), plot.top() + 5.0),
            f"{ymax:.4g}",
        )
        painter.drawText(
            QPointF(plot.left() - 8.0 - metrics.horizontalAdvance(f"{ymin:.4g}"), plot.bottom()),
            f"{ymin:.4g}",
        )


class MaterialTestDialog(QDialog):
    def __init__(
        self,
        material: MaterialData,
        *,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Material Test Lab · {material.name}")
        self.setModal(True)
        self.resize(900, 690)

        self.material = material
        self.units = dict(units or {})
        self._process: QProcess | None = None
        self._script_path: str | None = None
        self._result_path: str | None = None
        self._output_buffer = ""
        self._result: dict[str, object] | None = None

        default = default_material_test_spec(material, self.units)

        root = QVBoxLayout(self)

        heading = QLabel(
            f"<b>{material.name}</b> · {material.material_type} · Tag {material.tag}"
        )
        heading.setStyleSheet("color: #17356d; font-size: 13px;")
        root.addWidget(heading)

        note = QLabel(
            "This test runs the real OpenSees UniaxialMaterial object in an "
            "isolated worker process. The constitutive material is exercised "
            "directly, so the response is not contaminated by structural "
            "equilibrium or model boundary conditions."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 7px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(note)

        controls = QFormLayout()

        self.protocol = QComboBox()
        for label, value in MATERIAL_TEST_PROTOCOLS:
            self.protocol.addItem(label, value)
        index = self.protocol.findData(default.protocol)
        if index >= 0:
            self.protocol.setCurrentIndex(index)
        controls.addRow("Protocol:", self.protocol)

        self.amplitude = QDoubleSpinBox()
        self.amplitude.setDecimals(10)
        self.amplitude.setRange(1.0e-12, 1.0e12)
        self.amplitude.setValue(default.amplitude)
        controls.addRow("Peak material deformation:", self.amplitude)

        self.levels = QSpinBox()
        self.levels.setRange(1, 20)
        self.levels.setValue(default.levels)
        controls.addRow("Amplitude levels:", self.levels)

        self.cycles = QSpinBox()
        self.cycles.setRange(1, 20)
        self.cycles.setValue(default.cycles_per_level)
        controls.addRow("Cycles per level:", self.cycles)

        self.steps = QSpinBox()
        self.steps.setRange(1, 500)
        self.steps.setValue(default.steps_per_segment)
        controls.addRow("Steps per segment:", self.steps)

        root.addLayout(controls)

        self.plot = MaterialTestPlot()
        root.addWidget(self.plot, 1)

        self.summary = QLabel("No OpenSees material test has been run yet.")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            "padding: 7px; background: #f5f7f9; color: #526578;"
        )
        root.addWidget(self.summary)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #526578;")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run OpenSees Test")
        self.run_button.setObjectName("PrimaryButton")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.export_button = QPushButton("Export CSV...")
        self.export_button.setEnabled(False)
        close_button = QPushButton("Close")

        self.run_button.clicked.connect(self._run_test)
        self.stop_button.clicked.connect(self._stop_test)
        self.export_button.clicked.connect(self._export_csv)
        close_button.clicked.connect(self.accept)

        buttons.addWidget(self.run_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        root.addLayout(buttons)

        self.protocol.currentIndexChanged.connect(self._protocol_changed)
        self._protocol_changed()

    def _protocol_changed(self) -> None:
        cyclic = self.protocol.currentData() in {
            "symmetric_cyclic",
            "compression_cyclic",
        }
        self.levels.setEnabled(cyclic)
        self.cycles.setEnabled(cyclic)

    def _spec(self) -> MaterialTestSpec:
        return MaterialTestSpec(
            protocol=str(self.protocol.currentData()),
            amplitude=self.amplitude.value(),
            levels=self.levels.value(),
            cycles_per_level=self.cycles.value(),
            steps_per_segment=self.steps.value(),
        )

    def _cleanup_files(self) -> None:
        for path in (self._script_path, self._result_path):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
        self._script_path = None
        self._result_path = None

    def _run_test(self) -> None:
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            return

        try:
            spec = self._spec()
            script = build_material_test_script(
                self.material,
                self.units,
                spec,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Material Test Lab", str(exc))
            return

        runtime_ok, runtime_detail = probe_opensees_runtime()
        if not runtime_ok:
            QMessageBox.warning(
                self,
                "Material Test Lab",
                "OpenSeesPy runtime is not available:\n\n" + runtime_detail,
            )
            return

        self._cleanup_files()
        script_fd, script_path = tempfile.mkstemp(
            prefix="openseespy_studio_material_test_",
            suffix=".py",
            text=True,
        )
        os.close(script_fd)
        Path(script_path).write_text(script, encoding="utf-8")
        self._script_path = script_path

        result_fd, result_path = tempfile.mkstemp(
            prefix="openseespy_studio_material_result_",
            suffix=".json",
            text=True,
        )
        os.close(result_fd)
        self._result_path = result_path

        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert(
            "PYTHONPATH",
            build_worker_pythonpath(environment.value("PYTHONPATH")),
        )
        process.setProcessEnvironment(environment)
        process.setProgram(sys.executable)
        process.setArguments([
            "-m",
            "openseespy_studio.solver_worker",
            script_path,
            "--result-file",
            result_path,
        ])
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)

        self._process = process
        self._output_buffer = ""
        self._result = None
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.status.setText(
            "Running OpenSees material test in isolated worker..."
        )
        process.start()

    def _read_output(self) -> None:
        process = self._process
        if process is None:
            return
        data = bytes(process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )
        self._output_buffer += data

    def _process_error(self, error) -> None:
        self.status.setText(f"Material test process error: {error}")

    def _stop_test(self) -> None:
        process = self._process
        if process is None or process.state() == QProcess.NotRunning:
            return
        process.kill()
        process.waitForFinished(1000)
        self.status.setText("Material test stopped.")

    def _finished(self, exit_code: int, exit_status) -> None:
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        path = self._result_path
        payload: dict[str, object] = {}
        if path and Path(path).exists():
            try:
                payload = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}

        if exit_code != 0 or payload.get("status") != "completed":
            error = str(payload.get("error", "") or self._output_buffer).strip()
            if len(error) > 1800:
                error = error[-1800:]
            self.status.setText("OpenSees material test failed.")
            QMessageBox.warning(
                self,
                "Material Test Lab",
                error or f"Worker exited with code {exit_code}.",
            )
            self._cleanup_files()
            return

        results = payload.get("results", {})
        if not isinstance(results, dict):
            results = {}
        result = results.get("material_test", {})
        if not isinstance(result, dict):
            result = {}

        deformation = [
            float(value) for value in result.get("deformation", [])
        ]
        response = [
            float(value) for value in result.get("response", [])
        ]
        tangent = [
            float(value) for value in result.get("tangent", [])
        ]
        if not deformation or len(deformation) != len(response):
            self.status.setText("OpenSees returned no material response.")
            self._cleanup_files()
            return

        self._result = {
            "deformation": deformation,
            "response": response,
            "tangent": tangent,
            "x_label": str(result.get("x_label", "Material deformation")),
            "y_label": str(result.get("y_label", "Material response")),
        }
        self.plot.set_result(
            deformation,
            response,
            x_label=str(self._result["x_label"]),
            y_label=str(self._result["y_label"]),
        )
        self._update_summary(deformation, response, tangent)
        self.export_button.setEnabled(True)
        self.status.setText(
            f"Completed · {len(deformation)} OpenSees constitutive trial points."
        )
        self._cleanup_files()

    def _update_summary(
        self,
        deformation: list[float],
        response: list[float],
        tangent: list[float],
    ) -> None:
        peak_positive = max(response)
        peak_negative = min(response)
        max_abs_deformation = max(abs(value) for value in deformation)
        path_work = 0.0
        for index in range(1, len(deformation)):
            dx = deformation[index] - deformation[index - 1]
            avg = 0.5 * (response[index] + response[index - 1])
            path_work += avg * dx

        initial_tangent = tangent[0] if tangent else float("nan")
        tangent_text = (
            f"{initial_tangent:.6g}"
            if math.isfinite(initial_tangent)
            else "-"
        )
        self.summary.setText(
            f"Peak + response: {peak_positive:.6g}   ·   "
            f"Peak − response: {peak_negative:.6g}   ·   "
            f"Max |deformation|: {max_abs_deformation:.6g}   ·   "
            f"Initial tangent: {tangent_text}   ·   "
            f"Path work ∫R·dδ: {path_work:.6g}"
        )
        self.summary.setStyleSheet(
            "padding: 7px; background: #eaf6ee; color: #276738;"
        )

    def _export_csv(self) -> None:
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Material Test",
            f"material_{self.material.tag}_{self.material.material_type}.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        deformation = list(self._result["deformation"])
        response = list(self._result["response"])
        tangent = list(self._result["tangent"])
        try:
            with Path(path).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow([
                    str(self._result["x_label"]),
                    str(self._result["y_label"]),
                    "Tangent",
                ])
                for index, (x, y) in enumerate(zip(deformation, response)):
                    t = tangent[index] if index < len(tangent) else ""
                    writer.writerow([x, y, t])
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export Material Test",
                str(exc),
            )
            return
        self.status.setText(f"Exported {Path(path).name}")

    def closeEvent(self, event) -> None:
        process = self._process
        if process is not None and process.state() != QProcess.NotRunning:
            process.kill()
            process.waitForFinished(1000)
        self._cleanup_files()
        super().closeEvent(event)
