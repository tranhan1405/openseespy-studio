from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSpinBox, QVBoxLayout
)

from ..project import ElementLoadData, LoadPatternData, NodalLoadData, TimeSeriesData
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
    def __init__(self, time_series, pattern=None, *, next_tag=1, parent=None):
        super().__init__(parent); self.setWindowTitle("Load Pattern Editor"); self.setModal(True)
        root=QVBoxLayout(self); form=QFormLayout()
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(pattern.tag if pattern else next_tag)
        self.name=QLineEdit(pattern.name if pattern else f"Load Pattern {next_tag}")
        self.kind=QComboBox(); self.kind.addItems(["Plain","UniformExcitation"]); self.kind.setCurrentText(pattern.pattern_type if pattern else "Plain")
        self.ts=QComboBox()
        for tag in sorted(time_series):
            s=time_series[tag]; self.ts.addItem(f"{tag} - {s.name} ({s.series_type})",tag)
        if pattern:
            i=self.ts.findData(pattern.time_series_tag)
            if i>=0:self.ts.setCurrentIndex(i)
        self.direction=QComboBox()
        for i,name in enumerate(("X","Y","Z","RX","RY","RZ"),1): self.direction.addItem(f"{name} (DOF {i})",i)
        if pattern:
            i=self.direction.findData(pattern.direction)
            if i>=0:self.direction.setCurrentIndex(i)
        self.factor=_spin(pattern.factor if pattern else 1.0)
        self.vel0=_spin(pattern.vel0 if pattern else 0.0)
        for label,w in (("Tag:",self.tag),("Name:",self.name),("Type:",self.kind),("Time series:",self.ts),("Direction:",self.direction),("Scale factor:",self.factor),("Initial velocity:",self.vel0)): form.addRow(label,w)
        root.addLayout(form)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self._accept); b.rejected.connect(self.reject); root.addWidget(b)
        self.kind.currentTextChanged.connect(self._sync); self._sync(self.kind.currentText())
    def _sync(self,kind):
        dynamic=kind=="UniformExcitation"; self.direction.setEnabled(dynamic); self.factor.setEnabled(dynamic); self.vel0.setEnabled(dynamic)
    def data(self):
        if self.ts.currentData() is None: raise ValueError("Create a time series first.")
        return LoadPatternData(self.tag.value(),self.name.text().strip() or f"Load Pattern {self.tag.value()}",self.kind.currentText(),int(self.ts.currentData()),int(self.direction.currentData()),self.factor.value(),self.vel0.value())
    def _accept(self):
        try:self.data()
        except ValueError as e: QMessageBox.warning(self,"Load Pattern Editor",str(e)); return
        self.accept()


class NodalLoadDialog(QDialog):
    labels=("FX","FY","FZ","MX","MY","MZ")
    def __init__(self, patterns, load=None, *, next_tag=1, node_tag=1, units=None, parent=None):
        super().__init__(parent); self.setWindowTitle("Nodal Load Editor"); self.setModal(True)
        self.unit_system=UnitSystem.from_mapping(units)
        root=QVBoxLayout(self); form=QFormLayout()
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(load.tag if load else next_tag)
        self.name=QLineEdit(load.name if load else f"Nodal Load {next_tag}")
        self.pattern=QComboBox()
        for tag in sorted(patterns):
            p=patterns[tag]
            if p.pattern_type=="Plain": self.pattern.addItem(f"{tag} - {p.name}",tag)
        if load:
            i=self.pattern.findData(load.pattern_tag)
            if i>=0:self.pattern.setCurrentIndex(i)
        self.node=QSpinBox(); self.node.setRange(1,2147483647); self.node.setValue(load.node_tag if load else node_tag)
        form.addRow("Tag:",self.tag); form.addRow("Name:",self.name); form.addRow("Plain pattern:",self.pattern); form.addRow("Node:",self.node)
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
    def data(self):
        if self.pattern.currentData() is None: raise ValueError("Create a Plain load pattern first.")
        return NodalLoadData(self.tag.value(),self.name.text().strip() or f"Nodal Load {self.tag.value()}",int(self.pattern.currentData()),self.node.value(),tuple(s.value() for s in self.spins))
    def _accept(self):
        try:self.data()
        except ValueError as e: QMessageBox.warning(self,"Nodal Load Editor",str(e)); return
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
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Beam / Element Load Editor")
        self.setModal(True)
        self.resize(500, 500)
        self.unit_system = UnitSystem.from_mapping(units)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2147483647)
        self.tag.setValue(load.tag if load else next_tag)

        self.name = QLineEdit(
            load.name if load else f"Element Load {next_tag}"
        )

        self.pattern = QComboBox()
        for tag in sorted(patterns):
            pattern = patterns[tag]
            if pattern.pattern_type == "Plain":
                self.pattern.addItem(
                    f"{tag} - {pattern.name}",
                    tag,
                )
        if load:
            index = self.pattern.findData(load.pattern_tag)
            if index >= 0:
                self.pattern.setCurrentIndex(index)

        self.element = QSpinBox()
        self.element.setRange(1, 2147483647)
        self.element.setValue(
            load.element_tag if load else element_tag
        )

        self.kind = QComboBox()
        self.kind.addItem("Uniform (local axes)", "Uniform")
        self.kind.addItem("Point (local axes)", "Point")
        self.kind.addItem("Self Weight (global gravity)", "SelfWeight")
        if load:
            index = self.kind.findData(load.load_type)
            if index >= 0:
                self.kind.setCurrentIndex(index)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Plain pattern:", self.pattern)
        form.addRow("Element:", self.element)
        form.addRow("Type:", self.kind)

        self.wx = _spin(load.wx if load else 0.0)
        self.wy = _spin(load.wy if load else 0.0)
        self.wz = _spin(load.wz if load else 0.0)
        line_unit = self.unit_system.line_load_label
        form.addRow(f"Uniform Wx (local x) [{line_unit}]:", self.wx)
        form.addRow(f"Uniform Wy (local y) [{line_unit}]:", self.wy)
        form.addRow(f"Uniform Wz (local z) [{line_unit}]:", self.wz)

        self.px = _spin(load.px if load else 0.0)
        self.py = _spin(load.py if load else 0.0)
        self.pz = _spin(load.pz if load else 0.0)
        self.x_over_l = _spin(
            load.x_over_l if load else 0.5,
            0.0,
            1.0,
        )
        force_unit = self.unit_system.force
        form.addRow(f"Point Px (local x) [{force_unit}]:", self.px)
        form.addRow(f"Point Py (local y) [{force_unit}]:", self.py)
        form.addRow(f"Point Pz (local z) [{force_unit}]:", self.pz)
        form.addRow("Location x/L:", self.x_over_l)

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

        root.addLayout(form)
        note = QLabel(
            "Self Weight: density override = 0 uses the linked material "
            "density. Density [kg/m³] and gravity [m/s²] are physical SI "
            "inputs; Studio converts them automatically and generates "
            f"self-weight in [{self.unit_system.line_load_label}]."
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
        self._sync()

    def _sync(self):
        kind = self.kind.currentData()
        uniform = kind == "Uniform"
        point = kind == "Point"
        self_weight = kind == "SelfWeight"

        for widget in (self.wx, self.wy, self.wz):
            widget.setEnabled(uniform)
        for widget in (self.px, self.py, self.pz, self.x_over_l):
            widget.setEnabled(point)
        for widget in (self.gx, self.gy, self.gz, self.density):
            widget.setEnabled(self_weight)

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
            gravity=(
                self.gx.value(),
                self.gy.value(),
                self.gz.value(),
            ),
            density_override=self.density.value(),
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
