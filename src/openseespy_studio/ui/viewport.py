from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
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
from .icons import studio_icon


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

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)

        info = QVBoxLayout()
        info.setSpacing(0)
        self.model_label = QLabel("Model: Untitled")
        self.model_label.setStyleSheet("font-weight: 700; color: #203a55;")
        self.node_label = QLabel("Nodes: 0")
        self.element_label = QLabel("Elements: 0")
        self.material_label = QLabel("Materials: 0")
        self.section_label = QLabel("Sections: 0")
        for label in (
            self.node_label,
            self.element_label,
            self.material_label,
            self.section_label,
        ):
            label.setStyleSheet("color: #43566a;")
        info.addWidget(self.model_label)
        info.addWidget(self.node_label)
        info.addWidget(self.element_label)
        info.addWidget(self.material_label)
        info.addWidget(self.section_label)
        header.addLayout(info)

        header.addStretch(1)

        views = QHBoxLayout()
        views.setSpacing(2)
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
            button.setMinimumHeight(27)
            button.clicked.connect(lambda checked=False, v=view: self.set_view(v))
            self.view_group.addButton(button)
            views.addWidget(button)
            if view == "iso":
                button.setChecked(True)
        header.addLayout(views)

        header.addStretch(1)

        tools = QHBoxLayout()
        tools.setSpacing(3)
        for icon, tip, callback in (
            ("iso", "Orientation cube", lambda: self.set_view("iso")),
            ("box", "Fit selection", self.fit_view),
            ("display", "Display options", self._noop),
            ("fullscreen", "Toggle fullscreen", self._toggle_fullscreen),
        ):
            button = QToolButton()
            button.setIcon(studio_icon(icon))
            button.setIconSize(QSize(20, 20))
            button.setToolTip(tip)
            button.setAutoRaise(False)
            button.setFixedSize(32, 30)
            button.clicked.connect(callback)
            tools.addWidget(button)
        header.addLayout(tools)

        layout.addLayout(header)

        self.plotter = QtInteractor(self)
        self.plotter.interactor.setStyleSheet(
            "border: 1px solid #cbd4de; background: #edf2f6;"
        )
        layout.addWidget(self.plotter.interactor, 1)

        self._current_view = "iso"
        self._reset_scene()

    def _noop(self):
        return None

    def _toggle_fullscreen(self):
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
        else:
            window.showFullScreen()

    def _reset_scene(self) -> None:
        self.plotter.set_background("#f2f5f8", top="#e1e8ef")
        self.plotter.add_axes(
            line_width=2,
            color="#29445e",
            xlabel="X",
            ylabel="Y",
            zlabel="Z",
        )

    def set_model_info(
        self,
        name: str,
        nodes: int,
        elements: int,
        materials: int = 0,
        sections: int = 0,
    ) -> None:
        self.model_label.setText(f"Model: {name}")
        self.node_label.setText(f"Nodes: {nodes}")
        self.element_label.setText(f"Elements: {elements}")
        self.material_label.setText(f"Materials: {materials}")
        self.section_label.setText(f"Sections: {sections}")

    def _add_ground_grid(self, model: StructuralModel) -> None:
        low, high = model.bounds()
        xmin, ymin, zmin = low
        xmax, ymax, _ = high
        span_x = max(xmax - xmin, 1.0)
        span_y = max(ymax - ymin, 1.0)

        x_values = sorted({round(n.xyz[0], 8) for n in model.nodes.values()})
        y_values = sorted({round(n.xyz[1], 8) for n in model.nodes.values()})
        dx = min(
            [b - a for a, b in zip(x_values[:-1], x_values[1:]) if b > a] or [span_x / 4]
        )
        dy = min(
            [b - a for a, b in zip(y_values[:-1], y_values[1:]) if b > a] or [span_y / 4]
        )

        gx0, gx1 = xmin - dx * 0.55, xmax + dx * 0.55
        gy0, gy1 = ymin - dy * 0.55, ymax + dy * 0.55
        z = zmin - max(span_x, span_y) * 0.003

        nx = min(14, max(5, int(round((gx1 - gx0) / max(dx, 1e-9)))))
        ny = min(14, max(5, int(round((gy1 - gy0) / max(dy, 1e-9)))))
        color = "#d2d9e1"

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

    @staticmethod
    def _member_mesh(start, end, half_width):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-12:
            return None

        center = (
            (start[0] + end[0]) * 0.5,
            (start[1] + end[1]) * 0.5,
            (start[2] + end[2]) * 0.5,
        )
        direction = (dx / length, dy / length, dz / length)
        return pv.Cylinder(
            center=center,
            direction=direction,
            radius=half_width,
            height=length,
            resolution=4,
            capping=True,
        )

    def draw_model(self, model: StructuralModel) -> None:
        self.plotter.clear()
        self._reset_scene()

        if not model.nodes:
            self.plotter.render()
            return

        self._add_ground_grid(model)

        low, high = model.bounds()
        span = max(
            high[0] - low[0],
            high[1] - low[1],
            high[2] - low[2],
            1.0,
        )

        beam_size = max(span * 0.010, 0.08)
        column_size = max(span * 0.0115, 0.09)

        for element in model.elements.values():
            start = model.nodes[element.i].xyz
            end = model.nodes[element.j].xyz
            radius = column_size if element.group == "column" else beam_size
            mesh = self._member_mesh(start, end, radius)
            if mesh is None:
                continue
            self.plotter.add_mesh(
                mesh,
                color="#74889b" if element.group != "column" else "#687d90",
                edge_color="#243b52",
                show_edges=True,
                line_width=1,
                smooth_shading=False,
                pickable=True,
            )

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

        support_size = max(span * 0.016, 0.08)
        for node in model.nodes.values():
            if not any(node.fixity):
                continue
            x, y, z = node.xyz
            support = pv.Cone(
                center=(x, y, z - support_size * 0.58),
                direction=(0.0, 0.0, -1.0),
                height=support_size * 1.12,
                radius=support_size * 0.72,
                resolution=4,
            )
            self.plotter.add_mesh(
                support,
                color="#19b74e",
                edge_color="#0b7d32",
                show_edges=True,
                line_width=1,
            )

        self.set_view(self._current_view)
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.28)
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
            button.setChecked(button.property("view_name") == view)

    def fit_view(self) -> None:
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.18)
        self.plotter.render()
