from __future__ import annotations

import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
except ImportError:
    pv = None
    QtInteractor = None

from ..model import StructuralModel


class ModelViewport(QWidget):
    node_picked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        if QtInteractor is None:
            raise RuntimeError(
                "PyVista/pyvistaqt are required. Run: pip install -r requirements.txt"
            )

        self.setObjectName("ViewportRoot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.model_label = QLabel("Model: Untitled")
        self.model_label.setStyleSheet(
            "font-weight: 700; color: #203a55; font-size: 12px;"
        )
        self.count_label = QLabel("Nodes: 0   Elements: 0")
        self.count_label.setStyleSheet("color: #637588;")
        top.addWidget(self.model_label)
        top.addSpacing(10)
        top.addWidget(self.count_label)
        top.addStretch(1)

        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        for label, view in (
            ("Perspective", "iso"),
            ("Top (XY)", "xy"),
            ("Front (XZ)", "xz"),
            ("Right (YZ)", "yz"),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("view_name", view)
            button.setMinimumHeight(26)
            button.clicked.connect(
                lambda checked=False, v=view: self.set_view(v)
            )
            self.view_group.addButton(button)
            top.addWidget(button)
            if view == "iso":
                button.setChecked(True)

        fit = QPushButton("Fit")
        fit.clicked.connect(self.fit_view)
        top.addWidget(fit)
        layout.addLayout(top)

        self.plotter = QtInteractor(self)
        self.plotter.interactor.setStyleSheet(
            "border: 1px solid #c8d1db; background: #edf1f5;"
        )
        layout.addWidget(self.plotter.interactor, 1)

        self._current_view = "iso"
        self._reset_scene()

    def _reset_scene(self) -> None:
        self.plotter.set_background("#eef2f6", top="#dfe7ef")
        self.plotter.add_axes(
            line_width=2,
            color="#29445e",
            xlabel="X",
            ylabel="Y",
            zlabel="Z",
        )

    def set_model_info(self, name: str, nodes: int, elements: int) -> None:
        self.model_label.setText(f"Model: {name}")
        self.count_label.setText(f"Nodes: {nodes}   Elements: {elements}")

    def _add_ground_grid(self, model: StructuralModel) -> None:
        low, high = model.bounds()
        xmin, ymin, zmin = low
        xmax, ymax, _ = high
        span_x = max(xmax - xmin, 1.0)
        span_y = max(ymax - ymin, 1.0)

        nx = min(12, max(4, len({round(n.xyz[0], 8) for n in model.nodes.values()})))
        ny = min(12, max(4, len({round(n.xyz[1], 8) for n in model.nodes.values()})))

        dx = span_x / max(nx - 1, 1)
        dy = span_y / max(ny - 1, 1)
        pad_x = dx * 0.5
        pad_y = dy * 0.5

        gx0, gx1 = xmin - pad_x, xmax + pad_x
        gy0, gy1 = ymin - pad_y, ymax + pad_y
        z = zmin - max(span_x, span_y) * 0.002

        color = "#cfd8e2"
        for i in range(nx + 1):
            x = gx0 + (gx1 - gx0) * i / nx
            self.plotter.add_mesh(
                pv.Line((x, gy0, z), (x, gy1, z)),
                color=color,
                line_width=1,
            )
        for j in range(ny + 1):
            y = gy0 + (gy1 - gy0) * j / ny
            self.plotter.add_mesh(
                pv.Line((gx0, y, z), (gx1, y, z)),
                color=color,
                line_width=1,
            )

    def draw_model(self, model: StructuralModel) -> None:
        self.plotter.clear()
        self._reset_scene()

        if not model.nodes:
            self.plotter.render()
            return

        self._add_ground_grid(model)

        # Members: dark outline + lighter inner stroke gives a rectangular
        # engineering-member appearance without requiring section extrusion.
        for element in model.elements.values():
            start = model.nodes[element.i].xyz
            end = model.nodes[element.j].xyz
            line = pv.Line(start, end)

            outline = "#31485f"
            inner = "#74889b" if element.group != "column" else "#64798d"
            self.plotter.add_mesh(line, color=outline, line_width=8, pickable=True)
            self.plotter.add_mesh(line, color=inner, line_width=5, pickable=True)

        points = [model.nodes[tag].xyz for tag in sorted(model.nodes)]
        tags = list(sorted(model.nodes))
        nodes = pv.PolyData(points)
        nodes["tag"] = tags
        self.plotter.add_mesh(
            nodes,
            render_points_as_spheres=True,
            point_size=7,
            color="#064fd4",
            pickable=True,
        )

        low, high = model.bounds()
        span = max(
            high[0] - low[0],
            high[1] - low[1],
            high[2] - low[2],
            1.0,
        )

        support_size = max(span * 0.017, 0.08)
        for node in model.nodes.values():
            if not any(node.fixity):
                continue
            x, y, z = node.xyz
            support = pv.Cone(
                center=(x, y, z - support_size * 0.55),
                direction=(0.0, 0.0, -1.0),
                height=support_size * 1.15,
                radius=support_size * 0.72,
                resolution=4,
            )
            self.plotter.add_mesh(
                support,
                color="#16b34a",
                edge_color="#0b7d32",
                show_edges=True,
                line_width=1,
            )

        self.set_view(self._current_view)
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.30)
        self.plotter.add_text(
            "OpenSeesPy Studio",
            position="lower_right",
            font_size=8,
            color="#75869a",
        )
        self.plotter.render()

    def set_view(self, view: str) -> None:
        self._current_view = view
        function = {
            "iso": self.plotter.view_isometric,
            "xy": self.plotter.view_xy,
            "xz": self.plotter.view_xz,
            "yz": self.plotter.view_yz,
        }[view]
        function()
        self.plotter.render()

        for button in self.view_group.buttons():
            if button.property("view_name") == view:
                button.setChecked(True)

    def fit_view(self) -> None:
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.20)
        self.plotter.render()
