from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("#23384d", top="#10253a")
        self.plotter.add_axes(line_width=2)

    def draw_model(self, model: StructuralModel) -> None:
        self.plotter.clear()
        self.plotter.add_axes(line_width=2)
        if not model.nodes:
            self.plotter.render()
            return

        points = [model.nodes[t].xyz for t in sorted(model.nodes)]
        node_tags = list(sorted(model.nodes))
        poly = pv.PolyData(points)
        poly["tag"] = node_tags
        self.plotter.add_mesh(
            poly,
            render_points_as_spheres=True,
            point_size=9,
            color="#1667d9",
            pickable=True,
        )

        for e in model.elements.values():
            a = model.nodes[e.i].xyz
            b = model.nodes[e.j].xyz
            self.plotter.add_mesh(
                pv.Line(a, b),
                color="#7d93a8",
                line_width=5,
            )

        support_points = [n.xyz for n in model.nodes.values() if any(n.fixity)]
        if support_points:
            supports = pv.PolyData(support_points)
            self.plotter.add_mesh(
                supports,
                render_points_as_spheres=True,
                point_size=13,
                color="#36d34a",
            )

        self.plotter.reset_camera()
        self.plotter.view_isometric()
        self.plotter.render()

    def set_view(self, view: str) -> None:
        fn = {
            "iso": self.plotter.view_isometric,
            "xy": self.plotter.view_xy,
            "xz": self.plotter.view_xz,
            "yz": self.plotter.view_yz,
        }[view]
        fn()
        self.plotter.render()
