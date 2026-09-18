from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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
        layout.setSpacing(5)

        top = QHBoxLayout()
        self.model_label = QLabel("Model: Untitled")
        self.model_label.setStyleSheet("font-weight: 700; color: #24384d;")
        self.count_label = QLabel("Nodes: 0   Elements: 0")
        self.count_label.setStyleSheet("color: #657384;")
        top.addWidget(self.model_label)
        top.addSpacing(12)
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
            button.setMinimumHeight(25)
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
            "border: 1px solid #c9d1db; background: #f5f7fa;"
        )
        layout.addWidget(self.plotter.interactor, 1)

        self.plotter.set_background("#f6f8fb", top="#e8edf3")
        self.plotter.add_axes(
            line_width=2,
            color="#27374a",
            xlabel="X",
            ylabel="Y",
            zlabel="Z",
        )
        self._current_view = "iso"

    def set_model_info(self, name: str, nodes: int, elements: int) -> None:
        self.model_label.setText(f"Model: {name}")
        self.count_label.setText(f"Nodes: {nodes}   Elements: {elements}")

    def draw_model(self, model: StructuralModel) -> None:
        self.plotter.clear()
        self.plotter.set_background("#f6f8fb", top="#e8edf3")
        self.plotter.add_axes(
            line_width=2,
            color="#27374a",
            xlabel="X",
            ylabel="Y",
            zlabel="Z",
        )

        if not model.nodes:
            self.plotter.render()
            return

        points = [model.nodes[tag].xyz for tag in sorted(model.nodes)]
        tags = list(sorted(model.nodes))
        nodes = pv.PolyData(points)
        nodes["tag"] = tags
        self.plotter.add_mesh(
            nodes,
            render_points_as_spheres=True,
            point_size=8,
            color="#1558c0",
            pickable=True,
        )

        group_color = {
            "column": "#5d6f82",
            "beam-x": "#73879a",
            "beam-y": "#73879a",
        }
        for element in model.elements.values():
            start = model.nodes[element.i].xyz
            end = model.nodes[element.j].xyz
            self.plotter.add_mesh(
                pv.Line(start, end),
                color=group_color.get(element.group, "#6c7f91"),
                line_width=5,
                pickable=True,
            )

        support_points = [
            node.xyz for node in model.nodes.values() if any(node.fixity)
        ]
        if support_points:
            supports = pv.PolyData(support_points)
            self.plotter.add_mesh(
                supports,
                render_points_as_spheres=True,
                point_size=11,
                color="#24a148",
            )

        bounds_min, bounds_max = model.bounds()
        span = max(
            bounds_max[0] - bounds_min[0],
            bounds_max[1] - bounds_min[1],
            bounds_max[2] - bounds_min[2],
            1.0,
        )
        self.plotter.show_grid(
            color="#c8d0d9",
            font_size=9,
            grid="back",
            location="outer",
            all_edges=False,
        )
        self.plotter.add_text(
            "OpenSeesPy Studio",
            position="lower_right",
            font_size=8,
            color="#7b8794",
        )

        self.set_view(self._current_view)
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.05)
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
        self.plotter.render()
