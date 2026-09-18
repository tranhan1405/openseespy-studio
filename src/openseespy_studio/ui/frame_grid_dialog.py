from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from ..generator import FrameGridSpec


class FrameGridDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Frame Grid")
        self.setMinimumWidth(360)

        self.nx = self._int(4, 1, 50)
        self.ny = self._int(3, 1, 50)
        self.nz = self._int(3, 1, 50)
        self.dx = self._float(5.0)
        self.dy = self._float(6.0)
        self.dz = self._float(3.5)
        self.columns = QCheckBox("Create columns")
        self.beams_x = QCheckBox("Create X beams")
        self.beams_y = QCheckBox("Create Y beams")
        for cb in (self.columns, self.beams_x, self.beams_y):
            cb.setChecked(True)

        geometry = QGroupBox("Grid geometry")
        form = QFormLayout(geometry)
        form.addRow("X bays", self.nx)
        form.addRow("X bay width (m)", self.dx)
        form.addRow("Y bays", self.ny)
        form.addRow("Y bay width (m)", self.dy)
        form.addRow("Storeys", self.nz)
        form.addRow("Storey height (m)", self.dz)

        options = QGroupBox("Members")
        opts = QVBoxLayout(options)
        opts.addWidget(self.columns)
        opts.addWidget(self.beams_x)
        opts.addWidget(self.beams_y)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(geometry)
        layout.addWidget(options)
        layout.addWidget(buttons)

    @staticmethod
    def _int(value: int, lo: int, hi: int) -> QSpinBox:
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setValue(value)
        return w

    @staticmethod
    def _float(value: float) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(0.01, 1_000_000.0)
        w.setDecimals(3)
        w.setValue(value)
        return w

    def spec(self) -> FrameGridSpec:
        return FrameGridSpec(
            nx=self.nx.value(), ny=self.ny.value(), nz=self.nz.value(),
            dx=self.dx.value(), dy=self.dy.value(), dz=self.dz.value(),
            create_columns=self.columns.isChecked(),
            create_beams_x=self.beams_x.isChecked(),
            create_beams_y=self.beams_y.isChecked(),
        )
