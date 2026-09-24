from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget
)

from ..ground_motion_library import (
    available_ground_motion_presets,
    load_ground_motion_record,
    parse_ground_motion_record_text,
    pga_in_g,
    record_preset,
)
from ..model import dof_is_rotation, dof_labels_for_model
from ..project import ElementLoadData, LoadPatternData, NodalLoadData, PrescribedDisplacementData, TimeSeriesData
from ..units import UnitSystem


def _spin(value=0.0, low=-1e20, high=1e20):
    w=QDoubleSpinBox(); w.setDecimals(10); w.setRange(low,high); w.setValue(float(value)); return w


class MassDialog(QDialog):
    labels=("MX","MY","MZ","MRX","MRY","MRZ")
    def __init__(self, initial=None, *, units=None, parent=None):
        super().__init__(parent); self.setWindowTitle("Nodal Mass"); self.setModal(True)
        root=QVBoxLayout(self); form=QFormLayout()
        unit_system=UnitSystem.from_mapping(units)
        vals=tuple(initial or (0.0,)*6); self.spins=[]
        for index,(label,val) in enumerate(zip(self.labels, vals)):
            s=_spin(val,0.0,1e20)
            unit_label=(
                unit_system.mass_label
                if index < 3
                else f"{unit_system.mass_label}·{unit_system.length}²"
            )
            form.addRow(f"{label} [{unit_label}]:",s); self.spins.append(s)
        root.addLayout(form)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); root.addWidget(b)
    def values(self): return tuple(s.value() for s in self.spins)


def _dependency_row(
    combo: QComboBox,
    button_text: str,
    callback,
) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    row.addWidget(combo, 1)
    button = QPushButton(button_text)
    button.setEnabled(callable(callback))
    if callable(callback):
        button.clicked.connect(callback)
    row.addWidget(button)
    holder.dependency_button = button
    return holder


def _refresh_plain_pattern_combo(
    combo: QComboBox,
    patterns,
    *,
    select_tag: int | None = None,
) -> None:
    current = combo.currentData() if combo.count() else None
    wanted = select_tag if select_tag is not None else current
    combo.clear()
    combo.addItem("Select Plain load pattern...", None)
    for tag in sorted(patterns):
        pattern = patterns[tag]
        if pattern.pattern_type == "Plain":
            combo.addItem(f"{tag} - {pattern.name}", int(tag))
    if wanted is not None:
        index = combo.findData(int(wanted))
        if index >= 0:
            combo.setCurrentIndex(index)
    elif combo.count() == 2:
        combo.setCurrentIndex(1)


class TimeSeriesDialog(QDialog):
    def __init__(self, series=None, *, next_tag=1, parent=None):
        super().__init__(parent); self.setWindowTitle("Time Series Editor"); self.setModal(True); self.resize(430,420)
        root=QVBoxLayout(self); form=QFormLayout()
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(series.tag if series else next_tag)
        self.name=QLineEdit(series.name if series else f"Time Series {next_tag}")
        self.kind=QComboBox(); self.kind.addItems(["Linear","Constant","Path"]); self.kind.setCurrentText(series.series_type if series else "Linear")
        self.factor=_spin(series.factor if series else 1.0)
        self.dt=_spin(series.dt if series else 0.01,1e-12,1e20)
        form.addRow("Tag:",self.tag); form.addRow("Name:",self.name); form.addRow("Type:",self.kind); form.addRow("Factor:",self.factor); form.addRow("Path dt:",self.dt)
        root.addLayout(form)
        root.addWidget(QLabel("Path values (space/comma/newline separated):"))
        self.values=QPlainTextEdit()
        if series and series.values: self.values.setPlainText(" ".join(f"{v:g}" for v in series.values))
        root.addWidget(self.values,1)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self._accept); b.rejected.connect(self.reject); root.addWidget(b)
        self.kind.currentTextChanged.connect(self._sync); self._sync(self.kind.currentText())
    def _sync(self, kind): self.dt.setEnabled(kind=="Path"); self.values.setEnabled(kind=="Path")
    def _parsed_values(self):
        text=self.values.toPlainText().replace(","," ")
        return [float(x) for x in text.split()] if text.strip() else []
    def data(self):
        return TimeSeriesData(self.tag.value(),self.name.text().strip() or f"Time Series {self.tag.value()}",self.kind.currentText(),self.factor.value(),self.dt.value(),self._parsed_values())
    def _accept(self):
        try: self.data()
        except ValueError as e: QMessageBox.warning(self,"Time Series Editor",str(e)); return
        self.accept()


class LoadPatternDialog(QDialog):
    def __init__(
        self,
        time_series,
        pattern=None,
        *,
        next_tag=1,
        allow_uniform_excitation=True,
        new_time_series_callback=None,
        parent=None,
    ):
        super().__init__(parent); self.setWindowTitle("Load Pattern Editor"); self.setModal(True)
        self._time_series = dict(time_series)
        self._new_time_series_callback = new_time_series_callback
        root=QVBoxLayout(self); form=QFormLayout()
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(pattern.tag if pattern else next_tag)
        self.name=QLineEdit(pattern.name if pattern else f"Load Pattern {next_tag}")
        self.kind=QComboBox()
        kinds=["Plain"]
        if allow_uniform_excitation or (
            pattern is not None
            and pattern.pattern_type == "UniformExcitation"
        ):
            kinds.append("UniformExcitation")
        self.kind.addItems(kinds)
        self.kind.setCurrentText(pattern.pattern_type if pattern else "Plain")
        self.ts=QComboBox()
        self._refresh_time_series(
            pattern.time_series_tag if pattern else None
        )
        self.ts_holder = _dependency_row(
            self.ts,
            "New Time Series...",
            self._create_time_series_dependency,
        )
        self.direction=QComboBox()
        for i,name in enumerate(("X","Y","Z","RX","RY","RZ"),1): self.direction.addItem(f"{name} (DOF {i})",i)
        if pattern:
            i=self.direction.findData(pattern.direction)
            if i>=0:self.direction.setCurrentIndex(i)
        self.factor=_spin(pattern.factor if pattern else 1.0)
        self.vel0=_spin(pattern.vel0 if pattern else 0.0)
        for label,w in (("Tag:",self.tag),("Name:",self.name),("Type:",self.kind),("Time series:",self.ts_holder),("Direction:",self.direction),("Scale factor:",self.factor),("Initial velocity:",self.vel0)): form.addRow(label,w)
        root.addLayout(form)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self._accept); b.rejected.connect(self.reject); root.addWidget(b)
        self.kind.currentTextChanged.connect(self._sync); self._sync(self.kind.currentText())
    def _refresh_time_series(self, select_tag=None):
        current=self.ts.currentData() if self.ts.count() else None
        wanted=select_tag if select_tag is not None else current
        self.ts.clear(); self.ts.addItem("Select Time Series...",None)
        for tag in sorted(self._time_series):
            s=self._time_series[tag]
            self.ts.addItem(f"{tag} - {s.name} ({s.series_type})",int(tag))
        if wanted is not None:
            i=self.ts.findData(int(wanted))
            if i>=0:self.ts.setCurrentIndex(i)
        elif self.ts.count()==2:self.ts.setCurrentIndex(1)
    def _create_time_series_dependency(self):
        if not callable(self._new_time_series_callback): return
        series=self._new_time_series_callback()
        if series is None:return
        self._time_series[int(series.tag)]=series
        self._refresh_time_series(int(series.tag))
    def _sync(self,kind):
        dynamic=kind=="UniformExcitation"; self.direction.setEnabled(dynamic); self.factor.setEnabled(dynamic); self.vel0.setEnabled(dynamic)
    def data(self):
        if self.ts.currentData() is None: raise ValueError("Create a time series first.")
        return LoadPatternData(self.tag.value(),self.name.text().strip() or f"Load Pattern {self.tag.value()}",self.kind.currentText(),int(self.ts.currentData()),int(self.direction.currentData()),self.factor.value(),self.vel0.value())
    def _accept(self):
        try:self.data()
        except ValueError as e: QMessageBox.warning(self,"Load Pattern Editor",str(e)); return
        self.accept()


class GroundMotionPreviewWidget(QWidget):
    """Compact acceleration-time preview for the Ground Motion editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values: list[float] = []
        self._dt = 0.01
        self._unit = "g"
        self.setMinimumHeight(150)

    def set_data(
        self,
        values: list[float],
        *,
        dt: float,
        unit: str,
    ) -> None:
        self._values = [float(value) for value in values]
        self._dt = max(float(dt), 1.0e-15)
        self._unit = str(unit)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if not self._values:
            painter.setPen(QColor("#718195"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No ground-motion data",
            )
            return

        left = 58.0
        right = max(left + 10.0, float(self.width()) - 14.0)
        top = 18.0
        bottom = max(top + 10.0, float(self.height()) - 30.0)
        zero_y = 0.5 * (top + bottom)
        peak = max(max(abs(value) for value in self._values), 1.0e-15)

        painter.setPen(QPen(QColor("#c7d0da"), 1))
        painter.drawLine(QPointF(left, zero_y), QPointF(right, zero_y))
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))

        # Downsample only for painting. Stored data remain untouched.
        width_points = max(2, int(right - left))
        stride = max(1, len(self._values) // width_points)
        sampled = list(range(0, len(self._values), stride))
        if sampled[-1] != len(self._values) - 1:
            sampled.append(len(self._values) - 1)

        points: list[QPointF] = []
        denominator = max(1, len(self._values) - 1)
        for index in sampled:
            x = left + (right - left) * index / denominator
            y = zero_y - 0.5 * (bottom - top) * self._values[index] / peak
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor("#2f80ed"), 1.5))
        for first, second in zip(points, points[1:]):
            painter.drawLine(first, second)

        duration = max(0, len(self._values) - 1) * self._dt
        painter.setPen(QColor("#617080"))
        painter.drawText(4, int(top + 10), f"+{peak:.3g}")
        painter.drawText(4, int(bottom), f"-{peak:.3g}")
        painter.drawText(
            int(max(left, right - 120)),
            int(self.height() - 7),
            f"{duration:.3g} s · {self._unit}",
        )


class GroundMotionDialog(QDialog):
    """Edit one Path time series + UniformExcitation as one object."""

    INPUT_UNITS = ("g", "m/s²", "cm/s²", "mm/s²")

    def __init__(
        self,
        *,
        series=None,
        pattern=None,
        next_series_tag=1,
        next_pattern_tag=1,
        units=None,
        initial_source="manual",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Ground Motion Editor")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.resize(660, 720)
        self.unit_system = UnitSystem.from_mapping(units)
        self._source_path = ""
        self._source_format = ""
        self._builtin_key = ""

        if (series is None) != (pattern is None):
            raise ValueError(
                "Ground motion editing requires both a Path time series "
                "and a UniformExcitation pattern."
            )
        if pattern is not None and pattern.pattern_type != "UniformExcitation":
            raise ValueError(
                "Ground motion pattern must be UniformExcitation."
            )

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.form = form

        self.pattern_tag = QSpinBox()
        self.pattern_tag.setRange(1, 2147483647)
        self.pattern_tag.setValue(
            pattern.tag if pattern else int(next_pattern_tag)
        )
        self.series_tag = QSpinBox()
        self.series_tag.setRange(1, 2147483647)
        self.series_tag.setValue(
            series.tag if series else int(next_series_tag)
        )
        self.pattern_tag.setEnabled(pattern is None)
        self.series_tag.setEnabled(series is None)

        default_name = (
            pattern.name
            if pattern is not None
            else f"Ground Motion {next_pattern_tag}"
        )
        self.name = QLineEdit(default_name)

        self.direction = QComboBox()
        for dof, label in enumerate(
            ("X", "Y", "Z", "RX", "RY", "RZ"),
            start=1,
        ):
            self.direction.addItem(f"{label} (DOF {dof})", dof)
        if pattern is not None:
            index = self.direction.findData(pattern.direction)
            if index >= 0:
                self.direction.setCurrentIndex(index)

        self.source_mode = QComboBox()
        self.source_mode.addItem("Built-in Record", "builtin")
        self.source_mode.addItem("Import File", "file")
        self.source_mode.addItem("Manual / Paste", "manual")

        self.library = QComboBox()
        self.library_host = QWidget()
        library_layout = QHBoxLayout(self.library_host)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.addWidget(self.library, 1)
        self._populate_library()

        self.library_info = QLabel()
        self.library_info.setWordWrap(True)
        self.library_info.setObjectName("Muted")

        file_host = QWidget()
        file_layout = QHBoxLayout(file_host)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_button = QPushButton("Browse...")
        self.file_button.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_path, 1)
        file_layout.addWidget(self.file_button)

        self.column = QSpinBox()
        self.column.setRange(1, 100)
        self.column.setValue(1)
        self.column.setToolTip(
            "Numeric column used for generic TXT/CSV files. "
            "PEER AT2 and SimCenter JSON are auto-detected."
        )

        self.input_unit = QComboBox()
        self.input_unit.addItems(list(self.INPUT_UNITS))
        model_accel_unit = self.unit_system.acceleration_label
        if model_accel_unit in self.INPUT_UNITS:
            self.input_unit.setCurrentText(model_accel_unit)

        self.dt = _spin(
            series.dt if series is not None else 0.01,
            1.0e-12,
            1.0e20,
        )
        combined_scale = 1.0
        if series is not None and pattern is not None:
            combined_scale = float(series.factor) * float(pattern.factor)
        self.scale = _spin(combined_scale)
        self.vel0 = _spin(pattern.vel0 if pattern is not None else 0.0)

        form.addRow("Ground motion tag:", self.pattern_tag)
        form.addRow("Path series tag:", self.series_tag)
        form.addRow("Name:", self.name)
        form.addRow("Direction:", self.direction)
        form.addRow("Source:", self.source_mode)
        form.addRow("Record library:", self.library_host)
        form.addRow("Record info:", self.library_info)
        form.addRow("File:", file_host)
        form.addRow("TXT/CSV column:", self.column)
        form.addRow("Input acceleration unit:", self.input_unit)
        form.addRow(f"dt [{self.unit_system.time}]:", self.dt)
        form.addRow("Scale factor:", self.scale)
        form.addRow(
            f"Initial velocity [{self.unit_system.length}/{self.unit_system.time}]:",
            self.vel0,
        )
        root.addLayout(form)

        note = QLabel(
            "Built-in and imported acceleration data are converted to the "
            f"active model unit ({self.unit_system.acceleration_label}) when "
            "the ground motion is saved. Pushover/Cyclic protocols remain "
            "Analysis settings."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        self.data_info = QLabel("No acceleration data.")
        self.data_info.setWordWrap(True)
        self.data_info.setObjectName("Muted")
        root.addWidget(self.data_info)

        self.preview = GroundMotionPreviewWidget()
        root.addWidget(self.preview)

        self.values_label = QLabel("Acceleration values:")
        root.addWidget(self.values_label)
        self.values = QPlainTextEdit()
        self.values.setPlaceholderText(
            "Paste acceleration values separated by spaces, commas or lines."
        )
        if series is not None and series.values:
            self.source_mode.setCurrentIndex(
                self.source_mode.findData("manual")
            )
            if model_accel_unit in self.INPUT_UNITS:
                self.input_unit.setCurrentText(model_accel_unit)
            self.values.setPlainText(
                " ".join(f"{value:g}" for value in series.values)
            )
        root.addWidget(self.values, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.source_mode.currentIndexChanged.connect(self._sync_source_mode)
        self.library.currentIndexChanged.connect(self._library_changed)
        self.values.textChanged.connect(self._refresh_preview)
        self.dt.valueChanged.connect(self._refresh_preview)
        self.input_unit.currentTextChanged.connect(self._refresh_preview)
        self.scale.valueChanged.connect(self._refresh_preview)
        if series is None:
            source_index = self.source_mode.findData(str(initial_source))
            if source_index >= 0:
                self.source_mode.setCurrentIndex(source_index)
        self._sync_source_mode()
        if series is None and self.source_mode.currentData() == "builtin":
            self._library_changed()
        else:
            self._refresh_preview()

    def _set_form_row_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(bool(visible))
        label = self.form.labelForField(widget)
        if label is not None:
            label.setVisible(bool(visible))

    def _sync_source_mode(self, *_args) -> None:
        mode = str(self.source_mode.currentData() or "manual")
        self._set_form_row_visible(self.library_host, mode == "builtin")
        self._set_form_row_visible(self.library_info, mode == "builtin")
        self._set_form_row_visible(self.file_path.parentWidget(), mode == "file")
        self._set_form_row_visible(self.column, mode == "file")
        self.values.setReadOnly(mode != "manual")
        self.values_label.setText(
            "Acceleration values (editable):"
            if mode == "manual"
            else "Acceleration values (loaded preview):"
        )
        if mode == "builtin":
            self._library_changed()
        self._refresh_preview()

    def _populate_library(self, select_key: str | None = None) -> None:
        current = (
            str(select_key)
            if select_key is not None
            else str(self.library.currentData() or "")
        )
        self.library.blockSignals(True)
        self.library.clear()
        for preset in available_ground_motion_presets(
            include_custom=False
        ):
            self.library.addItem(
                f"{preset.label}  [Offline]",
                preset.key,
            )
        if current:
            index = self.library.findData(current)
            if index >= 0:
                self.library.setCurrentIndex(index)
        self.library.blockSignals(False)

    def _library_changed(self, *_args) -> None:
        key = str(self.library.currentData() or "")
        if not key:
            return
        preset = record_preset(key)
        year = f" ({preset.year})" if preset.year is not None else ""

        try:
            parsed = load_ground_motion_record(key)
        except ValueError as exc:
            QMessageBox.warning(self, "Ground Motion Library", str(exc))
            return

        self._builtin_key = key
        self._source_path = ""
        self._source_format = parsed.format
        if parsed.dt is not None:
            self.dt.setValue(parsed.dt)
        if parsed.input_unit in self.INPUT_UNITS:
            self.input_unit.setCurrentText(parsed.input_unit)
        self.values.setPlainText(
            " ".join(f"{value:g}" for value in parsed.values)
        )
        if not self.name.text().strip() or self.name.text().startswith(
            "Ground Motion "
        ):
            self.name.setText(preset.label)
        self.library_info.setText(
            f"{preset.event}{year} · {preset.station} · Source: "
            f"{preset.source}. Available offline. {preset.notes}"
        )
        self._refresh_preview()

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Ground Motion",
            "",
            (
                "Ground motion (*.at2 *.AT2 *.txt *.dat *.csv *.json);;"
                "All files (*)"
            ),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            parsed = parse_ground_motion_record_text(
                text,
                column=self.column.value(),
                filename=path,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Import Ground Motion",
                str(exc),
            )
            return

        self._source_path = str(path)
        self._source_format = parsed.format
        self._builtin_key = ""
        self.file_path.setText(str(path))
        if parsed.dt is not None:
            self.dt.setValue(parsed.dt)
        if parsed.input_unit in self.INPUT_UNITS:
            self.input_unit.setCurrentText(parsed.input_unit)
        self.values.setPlainText(
            " ".join(f"{value:g}" for value in parsed.values)
        )
        if not self.name.text().strip() or self.name.text().startswith(
            "Ground Motion "
        ):
            self.name.setText(Path(path).stem)
        self._refresh_preview()

    def _parsed_values(self) -> list[float]:
        text = (
            self.values.toPlainText()
            .replace(",", " ")
            .replace(";", " ")
        )
        return [float(value) for value in text.split()] if text.strip() else []

    def _raw_pga_g(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return pga_in_g(values, self.input_unit.currentText())

    def _values_in_model_units(self) -> list[float]:
        values = self._parsed_values()
        unit = self.input_unit.currentText()
        if unit == "g":
            to_m_per_s2 = 9.80665
        elif unit == "m/s²":
            to_m_per_s2 = 1.0
        elif unit == "cm/s²":
            to_m_per_s2 = 0.01
        elif unit == "mm/s²":
            to_m_per_s2 = 0.001
        else:
            raise ValueError(f"Unsupported acceleration unit: {unit}")
        return [
            self.unit_system.acceleration_from_m_per_s2(
                value * to_m_per_s2
            )
            for value in values
        ]

    def _refresh_preview(self, *_args) -> None:
        try:
            values = self._parsed_values()
        except ValueError:
            self.data_info.setText("Acceleration data contain an invalid value.")
            self.preview.set_data(
                [],
                dt=self.dt.value(),
                unit=self.input_unit.currentText(),
            )
            return
        self.preview.set_data(
            values,
            dt=self.dt.value(),
            unit=self.input_unit.currentText(),
        )
        if not values:
            self.data_info.setText("No acceleration data.")
            return
        try:
            raw_pga = self._raw_pga_g(values)
        except ValueError:
            raw_pga = 0.0
        duration = max(0, len(values) - 1) * self.dt.value()
        scaled_pga = raw_pga * abs(self.scale.value())
        source = (
            f"Built-in · {record_preset(self._builtin_key).label}"
            if self._builtin_key
            else (
                f"Imported · {Path(self._source_path).name}"
                if self._source_path
                else "Manual"
            )
        )
        format_text = f" · {self._source_format}" if self._source_format else ""
        self.data_info.setText(
            f"{source}{format_text} · {len(values)} point(s) · "
            f"duration {duration:g} s · raw PGA {raw_pga:.4g} g · "
            f"scaled PGA {scaled_pga:.4g} g"
        )

    def data(self) -> tuple[TimeSeriesData, LoadPatternData]:
        raw_values = self._parsed_values()
        if not raw_values:
            raise ValueError(
                "Ground motion needs acceleration data. Choose a built-in "
                "record, import a file, or paste values manually."
            )
        values = self._values_in_model_units()
        name = (
            self.name.text().strip()
            or f"Ground Motion {self.pattern_tag.value()}"
        )
        series = TimeSeriesData(
            tag=self.series_tag.value(),
            name=f"{name} Acceleration",
            series_type="Path",
            factor=self.scale.value(),
            dt=self.dt.value(),
            values=values,
        )
        pattern = LoadPatternData(
            tag=self.pattern_tag.value(),
            name=name,
            pattern_type="UniformExcitation",
            time_series_tag=series.tag,
            direction=int(self.direction.currentData()),
            factor=1.0,
            vel0=self.vel0.value(),
        )
        return series, pattern

    def _accept(self) -> None:
        try:
            self.data()
        except ValueError as exc:
            QMessageBox.warning(self, "Ground Motion Editor", str(exc))
            return
        self.accept()


class NodalLoadDialog(QDialog):
    labels=("FX","FY","FZ","MX","MY","MZ")
    def __init__(self, patterns, load=None, *, next_tag=1, node_tag=1, units=None, new_pattern_callback=None, parent=None):
        super().__init__(parent); self.setWindowTitle("Nodal Load Editor"); self.setModal(True)
        self.unit_system=UnitSystem.from_mapping(units)
        self._patterns=dict(patterns)
        self._new_pattern_callback=new_pattern_callback
        root=QVBoxLayout(self); form=QFormLayout()
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(load.tag if load else next_tag)
        self.name=QLineEdit(load.name if load else f"Nodal Load {next_tag}")
        self.pattern=QComboBox()
        _refresh_plain_pattern_combo(
            self.pattern,
            self._patterns,
            select_tag=(load.pattern_tag if load else None),
        )
        self.pattern_holder=_dependency_row(
            self.pattern,
            "New Plain Pattern...",
            self._create_pattern_dependency,
        )
        self.node=QSpinBox(); self.node.setRange(1,2147483647); self.node.setValue(load.node_tag if load else node_tag)
        form.addRow("Tag:",self.tag); form.addRow("Name:",self.name); form.addRow("Plain pattern:",self.pattern_holder); form.addRow("Node:",self.node)
        vals=load.values if load else (0.0,)*6; self.spins=[]
        for index,(label,val) in enumerate(zip(self.labels,vals)):
            s=_spin(val)
            unit_label=(
                self.unit_system.force
                if index < 3
                else f"{self.unit_system.force}·{self.unit_system.length}"
            )
            form.addRow(f"{label} [{unit_label}]:",s); self.spins.append(s)
        root.addLayout(form)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self._accept); b.rejected.connect(self.reject); root.addWidget(b)
    def _create_pattern_dependency(self):
        if not callable(self._new_pattern_callback): return
        pattern=self._new_pattern_callback()
        if pattern is None:return
        self._patterns[int(pattern.tag)]=pattern
        _refresh_plain_pattern_combo(self.pattern,self._patterns,select_tag=int(pattern.tag))
    def data(self):
        if self.pattern.currentData() is None: raise ValueError("Create a Plain load pattern first.")
        return NodalLoadData(self.tag.value(),self.name.text().strip() or f"Nodal Load {self.tag.value()}",int(self.pattern.currentData()),self.node.value(),tuple(s.value() for s in self.spins))
    def _accept(self):
        try:self.data()
        except ValueError as e: QMessageBox.warning(self,"Nodal Load Editor",str(e)); return
        self.accept()



class PrescribedDisplacementDialog(QDialog):
    DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

    def __init__(
        self,
        patterns,
        displacement=None,
        *,
        next_tag=1,
        node_tag=1,
        ndm=3,
        ndf=6,
        units=None,
        allowed_load_types=None,
        new_pattern_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Prescribed Displacement Editor")
        self.setModal(True)
        self.unit_system = UnitSystem.from_mapping(units)
        self.ndm = int(ndm)
        self.ndf = max(1, min(6, int(ndf)))
        self._dof_labels = dof_labels_for_model(self.ndm, self.ndf)
        self._patterns = dict(patterns)
        self._new_pattern_callback = new_pattern_callback

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(
            displacement.tag if displacement else next_tag
        )

        self.name = QLineEdit(
            displacement.name
            if displacement
            else f"Prescribed Displacement {next_tag}"
        )

        self.pattern = QComboBox()
        _refresh_plain_pattern_combo(
            self.pattern,
            self._patterns,
            select_tag=(
                displacement.pattern_tag if displacement else None
            ),
        )
        self.pattern_holder = _dependency_row(
            self.pattern,
            "New Plain Pattern...",
            self._create_pattern_dependency,
        )

        self.node = QSpinBox()
        self.node.setRange(1, 2147483647)
        self.node.setValue(
            displacement.node_tag if displacement else node_tag
        )

        self.dof = QComboBox()
        for dof, label in enumerate(self._dof_labels, start=1):
            self.dof.addItem(f"{label} (DOF {dof})", dof)
        if displacement:
            index = self.dof.findData(displacement.dof)
            if index >= 0:
                self.dof.setCurrentIndex(index)

        self.value = _spin(
            displacement.value if displacement else 0.0
        )
        self.value_label = QLabel()

        note = QLabel(
            "This is an imposed nodal displacement inside a Plain load "
            "pattern. Its value is multiplied by the selected Time Series. "
            "It is different from the DisplacementControl integrator used by "
            "Pushover and Cyclic templates."
        )
        note.setWordWrap(True)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Plain pattern:", self.pattern_holder)
        form.addRow("Node:", self.node)
        form.addRow("DOF:", self.dof)
        form.addRow(self.value_label, self.value)
        root.addLayout(form)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.dof.currentIndexChanged.connect(self._sync_value_label)
        self._sync_value_label()

    def _create_pattern_dependency(self) -> None:
        if not callable(self._new_pattern_callback):
            return
        pattern = self._new_pattern_callback()
        if pattern is None:
            return
        self._patterns[int(pattern.tag)] = pattern
        _refresh_plain_pattern_combo(
            self.pattern,
            self._patterns,
            select_tag=int(pattern.tag),
        )

    def _sync_value_label(self, *_args) -> None:
        dof = int(self.dof.currentData() or 1)
        if dof_is_rotation(self.ndm, self.ndf, dof):
            label = "Value [rad]:"
        else:
            label = f"Value [{self.unit_system.length}]:"
        self.value_label.setText(label)

    def data(self) -> PrescribedDisplacementData:
        if self.pattern.currentData() is None:
            raise ValueError("Create a Plain load pattern first.")
        if self.dof.currentData() is None:
            raise ValueError("Choose a valid displacement DOF.")
        return PrescribedDisplacementData(
            tag=self.tag.value(),
            name=(
                self.name.text().strip()
                or f"Prescribed Displacement {self.tag.value()}"
            ),
            pattern_tag=int(self.pattern.currentData()),
            node_tag=self.node.value(),
            dof=int(self.dof.currentData()),
            value=self.value.value(),
        )

    def _accept(self) -> None:
        try:
            self.data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Prescribed Displacement Editor",
                str(exc),
            )
            return
        self.accept()


class ElementLoadDialog(QDialog):
    def __init__(
        self,
        patterns,
        load=None,
        *,
        next_tag=1,
        element_tag=1,
        units=None,
        allowed_load_types=None,
        new_pattern_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Beam / Element Load Editor")
        self.setModal(True)
        self.resize(540, 660)
        self.unit_system = UnitSystem.from_mapping(units)
        self._patterns = dict(patterns)
        self._new_pattern_callback = new_pattern_callback

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(load.tag if load else next_tag)
        self.name = QLineEdit(
            load.name if load else f"Element Load {next_tag}"
        )

        self.pattern = QComboBox()
        _refresh_plain_pattern_combo(
            self.pattern,
            self._patterns,
            select_tag=(load.pattern_tag if load else None),
        )
        self.pattern_holder = _dependency_row(
            self.pattern,
            "New Plain Pattern...",
            self._create_pattern_dependency,
        )

        self.element = QSpinBox()
        self.element.setRange(1, 2147483647)
        self.element.setValue(load.element_tag if load else element_tag)

        self.kind = QComboBox()
        allowed = (
            set(allowed_load_types)
            if allowed_load_types is not None
            else {
                "Uniform", "Triangular", "Trapezoidal", "Point",
                "SelfWeight", "SurfacePressure",
            }
        )
        for label, value in (
            ("Uniform distributed", "Uniform"),
            ("Triangular distributed", "Triangular"),
            ("Trapezoidal / linearly varying", "Trapezoidal"),
            ("Point", "Point"),
            ("Self Weight (global gravity)", "SelfWeight"),
            ("Shell Surface Pressure (normal)", "SurfacePressure"),
        ):
            if value in allowed:
                self.kind.addItem(label, value)
        if load:
            index = self.kind.findData(load.load_type)
            if index >= 0:
                self.kind.setCurrentIndex(index)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Plain pattern:", self.pattern_holder)
        form.addRow("Element:", self.element)
        form.addRow("Type:", self.kind)

        self.coordinate_system = QComboBox()
        self.coordinate_system.addItem("Global XYZ", "global")
        self.coordinate_system.addItem("Local xyz", "local")
        coordinate_value = (
            load.coordinate_system if load is not None else "global"
        )
        coordinate_index = self.coordinate_system.findData(coordinate_value)
        self.coordinate_system.setCurrentIndex(
            coordinate_index if coordinate_index >= 0 else 0
        )
        self.coordinate_system.setToolTip(
            "Global keeps the load direction fixed in model XYZ. Local follows "
            "the member local x/y/z axes defined by its geometric transformation."
        )
        form.addRow("Coordinate system:", self.coordinate_system)

        self.wx = _spin(load.wx if load else 0.0)
        self.wy = _spin(load.wy if load else 0.0)
        self.wz = _spin(load.wz if load else 0.0)
        self.wx_end = _spin(load.wx_end if load else 0.0)
        self.wy_end = _spin(load.wy_end if load else 0.0)
        self.wz_end = _spin(load.wz_end if load else 0.0)
        self.a_over_l = _spin(load.a_over_l if load else 0.0, 0.0, 1.0)
        self.b_over_l = _spin(load.b_over_l if load else 1.0, 0.0, 1.0)
        self.start_x_label = QLabel()
        self.start_y_label = QLabel()
        self.start_z_label = QLabel()
        self.end_x_label = QLabel()
        self.end_y_label = QLabel()
        self.end_z_label = QLabel()
        form.addRow(self.start_x_label, self.wx)
        form.addRow(self.start_y_label, self.wy)
        form.addRow(self.start_z_label, self.wz)
        form.addRow(self.end_x_label, self.wx_end)
        form.addRow(self.end_y_label, self.wy_end)
        form.addRow(self.end_z_label, self.wz_end)
        form.addRow("Distributed start a/L:", self.a_over_l)
        form.addRow("Distributed end b/L:", self.b_over_l)

        self.px = _spin(load.px if load else 0.0)
        self.py = _spin(load.py if load else 0.0)
        self.pz = _spin(load.pz if load else 0.0)
        self.x_over_l = _spin(
            load.x_over_l if load else 0.5,
            0.0,
            1.0,
        )
        self.point_x_label = QLabel()
        self.point_y_label = QLabel()
        self.point_z_label = QLabel()
        form.addRow(self.point_x_label, self.px)
        form.addRow(self.point_y_label, self.py)
        form.addRow(self.point_z_label, self.pz)
        form.addRow("Point location x/L:", self.x_over_l)

        gravity = load.gravity if load else (0.0, 0.0, -9.81)
        self.gx = _spin(gravity[0])
        self.gy = _spin(gravity[1])
        self.gz = _spin(gravity[2])
        self.density = _spin(
            load.density_override if load else 0.0,
            0.0,
            1.0e20,
        )
        form.addRow("Gravity GX [m/s²]:", self.gx)
        form.addRow("Gravity GY [m/s²]:", self.gy)
        form.addRow("Gravity GZ [m/s²]:", self.gz)
        form.addRow("Density override [kg/m³]:", self.density)

        self.pressure = _spin(load.pressure if load else 0.0)
        form.addRow(
            f"Surface pressure [{self.unit_system.stress_label}]:",
            self.pressure,
        )

        root.addLayout(form)
        note = QLabel(
            "Distributed loads use start/end intensity vectors. Triangular "
            "requires exactly one zero-intensity end; Trapezoidal allows both "
            "ends to be nonzero. a/L and b/L define the loaded part of the "
            "member. Uniform, Triangular, Trapezoidal and Point loads can be "
            "entered in Global XYZ or Local member xyz; SARE converts Global "
            "components to OpenSees local axes during export. Self Weight "
            "always uses the global gravity vector."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.kind.currentIndexChanged.connect(self._sync)
        self.coordinate_system.currentIndexChanged.connect(self._sync)
        self._sync()

    def _create_pattern_dependency(self) -> None:
        if not callable(self._new_pattern_callback):
            return
        pattern = self._new_pattern_callback()
        if pattern is None:
            return
        self._patterns[int(pattern.tag)] = pattern
        _refresh_plain_pattern_combo(
            self.pattern,
            self._patterns,
            select_tag=int(pattern.tag),
        )

    def _sync(self):
        kind = self.kind.currentData()
        distributed = kind in {"Uniform", "Triangular", "Trapezoidal"}
        variable = kind in {"Triangular", "Trapezoidal"}
        point = kind == "Point"
        self_weight = kind == "SelfWeight"
        surface_pressure = kind == "SurfacePressure"
        self.coordinate_system.setEnabled(distributed or point)

        coordinate = str(self.coordinate_system.currentData() or "global")
        global_axes = coordinate == "global"
        line_unit = self.unit_system.line_load_label
        force_unit = self.unit_system.force
        axis_names = ("X", "Y", "Z") if global_axes else ("x", "y", "z")
        coordinate_name = "global" if global_axes else "local"
        start_prefix = "Uniform" if kind == "Uniform" else "Start"
        for label, axis in zip(
            (self.start_x_label, self.start_y_label, self.start_z_label),
            axis_names,
        ):
            label.setText(
                f"{start_prefix} {axis} ({coordinate_name}) [{line_unit}]:"
            )
        for label, axis in zip(
            (self.end_x_label, self.end_y_label, self.end_z_label),
            axis_names,
        ):
            label.setText(f"End {axis} ({coordinate_name}) [{line_unit}]:")

        point_names = ("GX", "GY", "GZ") if global_axes else ("Px", "Py", "Pz")
        point_axes = ("global X", "global Y", "global Z") if global_axes else (
            "local x", "local y", "local z"
        )
        for label, name, axis in zip(
            (self.point_x_label, self.point_y_label, self.point_z_label),
            point_names,
            point_axes,
        ):
            label.setText(f"Point {name} ({axis}) [{force_unit}]:")

        for widget in (self.wx, self.wy, self.wz):
            widget.setEnabled(distributed)
        for widget in (
            self.wx_end, self.wy_end, self.wz_end,
            self.a_over_l, self.b_over_l,
        ):
            widget.setEnabled(variable)
        for widget in (self.px, self.py, self.pz, self.x_over_l):
            widget.setEnabled(point)
        for widget in (self.gx, self.gy, self.gz, self.density):
            widget.setEnabled(self_weight)
        self.pressure.setEnabled(surface_pressure)

    def data(self):
        if self.pattern.currentData() is None:
            raise ValueError("Create a Plain load pattern first.")
        return ElementLoadData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Element Load {self.tag.value()}",
            pattern_tag=int(self.pattern.currentData()),
            element_tag=self.element.value(),
            load_type=str(self.kind.currentData()),
            wx=self.wx.value(),
            wy=self.wy.value(),
            wz=self.wz.value(),
            px=self.px.value(),
            py=self.py.value(),
            pz=self.pz.value(),
            x_over_l=self.x_over_l.value(),
            gravity=(self.gx.value(), self.gy.value(), self.gz.value()),
            density_override=self.density.value(),
            pressure=self.pressure.value(),
            coordinate_system=str(
                self.coordinate_system.currentData() or "global"
            ),
            wx_end=self.wx_end.value(),
            wy_end=self.wy_end.value(),
            wz_end=self.wz_end.value(),
            a_over_l=self.a_over_l.value(),
            b_over_l=self.b_over_l.value(),
        )

    def _accept(self):
        try:
            self.data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Beam / Element Load Editor",
                str(exc),
            )
            return
        self.accept()

