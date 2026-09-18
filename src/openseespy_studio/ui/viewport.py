from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRubberBand,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkPointPicker
except ImportError:
    pv = None
    QtInteractor = None
    vtkCellPicker = None
    vtkPointPicker = None

from ..model import StructuralModel
from .icons import studio_icon


class ModelViewport(QWidget):
    entity_clicked = Signal(object)
    entity_hovered = Signal(object)
    entity_double_clicked = Signal(object)
    context_requested = Signal(object)
    box_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        if QtInteractor is None:
            raise RuntimeError(
                "PyVista/pyvistaqt are required. Run: pip install -r requirements.txt"
            )

        self.setObjectName("ViewportRoot")
        self._model: StructuralModel | None = None
        self._selection_filter = "all"
        self._selected_nodes: set[int] = set()
        self._selected_elements: set[int] = set()
        self._hover_ref: tuple[str, int] | None = None

        self._hidden_nodes: set[int] = set()
        self._hidden_elements: set[int] = set()
        self._isolate_active = False
        self._isolate_nodes: set[int] = set()
        self._isolate_elements: set[int] = set()

        self._node_actor = None
        self._node_tags: list[int] = []
        self._element_actor_data: dict[str, tuple[object, np.ndarray]] = {}
        self._left_press_pos: tuple[int, int] | None = None
        self._right_press_pos: tuple[int, int] | None = None
        self._nav_mode: str | None = None
        self._nav_last_pos: tuple[float, float] | None = None
        self._interaction_tool = "select"
        self._box_origin: QPoint | None = None
        self._rubber_band: QRubberBand | None = None

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
        self.plotter.interactor.setMouseTracking(True)
        layout.addWidget(self.plotter.interactor, 1)
        self._rubber_band = QRubberBand(
            QRubberBand.Rectangle,
            self.plotter.interactor,
        )
        self._rubber_band.hide() if self._rubber_band is not None else None

        self._current_view = "iso"
        self._point_picker = vtkPointPicker()
        self._point_picker.SetTolerance(0.018)
        self._cell_picker = vtkCellPicker()
        self._cell_picker.SetTolerance(0.006)

        self._install_mouse_observers()
        self._reset_scene()

    def set_interaction_tool(self, tool: str) -> None:
        if tool not in {"select", "box"}:
            raise ValueError(f"Unknown interaction tool: {tool}")
        self._interaction_tool = tool
        self._box_origin = None
        self._rubber_band.hide() if self._rubber_band is not None else None

    def interaction_tool(self) -> str:
        return self._interaction_tool

    def _install_mouse_observers(self) -> None:
        # All viewport mouse input is handled through Qt so the default VTK
        # left/right-drag navigation cannot conflict with selection/context menus.
        self.plotter.interactor.installEventFilter(self)

    def _vtk_position_from_qt(self, event) -> tuple[int, int]:
        pos = event.position()
        x = int(pos.x())
        y = int(self.plotter.interactor.height() - pos.y())
        return x, y

    @staticmethod
    def _moved(a: tuple[int, int] | None, b: tuple[int, int], tol: int = 5) -> bool:
        if a is None:
            return True
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 > tol * tol

    @staticmethod
    def _actor_key(actor) -> str:
        if actor is None:
            return ""
        try:
            return actor.GetAddressAsString("")
        except Exception:
            return str(id(actor))

    @staticmethod
    def _selection_mode_from_modifiers(modifiers) -> str:
        if modifiers & Qt.ControlModifier:
            return "toggle"
        if modifiers & Qt.ShiftModifier:
            return "add"
        return "replace"

    def _start_navigation(self, modifiers, pos: tuple[float, float]) -> None:
        # ANSYS-style current navigation:
        # MMB = rotate, Ctrl+MMB = pan, Shift+MMB = zoom.
        ctrl = bool(modifiers & Qt.ControlModifier)
        shift = bool(modifiers & Qt.ShiftModifier)
        if ctrl and shift:
            self._nav_mode = None
        elif ctrl:
            self._nav_mode = "pan"
        elif shift:
            self._nav_mode = "zoom"
        else:
            self._nav_mode = "rotate"
        self._nav_last_pos = pos
        self._hover_ref = None
        self._update_highlight_overlays()

    def _navigate(self, pos: tuple[float, float]) -> None:
        if self._nav_mode is None or self._nav_last_pos is None:
            return

        dx = pos[0] - self._nav_last_pos[0]
        dy = pos[1] - self._nav_last_pos[1]
        self._nav_last_pos = pos

        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return

        camera = self.plotter.camera

        if self._nav_mode == "rotate":
            camera.Azimuth(-dx * 0.35)
            camera.Elevation(dy * 0.35)
            camera.OrthogonalizeViewUp()

        elif self._nav_mode == "pan":
            position = np.asarray(camera.GetPosition(), dtype=float)
            focal = np.asarray(camera.GetFocalPoint(), dtype=float)
            view_up = np.asarray(camera.GetViewUp(), dtype=float)
            direction = focal - position
            distance = float(np.linalg.norm(direction))
            if distance <= 1e-12:
                return
            direction /= distance
            view_up_norm = np.linalg.norm(view_up)
            if view_up_norm <= 1e-12:
                return
            view_up /= view_up_norm
            right = np.cross(direction, view_up)
            right_norm = np.linalg.norm(right)
            if right_norm <= 1e-12:
                return
            right /= right_norm
            up = np.cross(right, direction)
            up /= max(np.linalg.norm(up), 1e-12)

            height = max(self.plotter.interactor.height(), 1)
            if camera.GetParallelProjection():
                world_per_pixel = 2.0 * camera.GetParallelScale() / height
            else:
                view_angle = math.radians(camera.GetViewAngle())
                world_per_pixel = (
                    2.0 * distance * math.tan(view_angle * 0.5) / height
                )

            translation = (
                -dx * world_per_pixel * right
                + dy * world_per_pixel * up
            )
            camera.SetPosition(*(position + translation))
            camera.SetFocalPoint(*(focal + translation))

        elif self._nav_mode == "zoom":
            factor = math.exp(-dy * 0.012)
            factor = max(0.25, min(4.0, factor))
            camera.Zoom(factor)

        self.plotter.render()

    def _wheel_zoom(self, delta_y: int) -> None:
        if delta_y == 0:
            return
        steps = delta_y / 120.0
        factor = math.pow(1.12, steps)
        self.plotter.camera.Zoom(factor)
        self.plotter.render()

    def _update_hover_from_qt(self, event) -> None:
        if event.buttons() != Qt.NoButton:
            return
        entity = self.pick_entity(*self._vtk_position_from_qt(event))
        if entity == self._hover_ref:
            return
        self._hover_ref = entity
        self._update_highlight_overlays()
        self.entity_hovered.emit(
            {"kind": entity[0], "tag": entity[1]} if entity else None
        )

    def eventFilter(self, obj, event):
        if obj is not self.plotter.interactor:
            return super().eventFilter(obj, event)

        event_type = event.type()

        if event_type == QEvent.MouseButtonPress:
            pos = event.position()
            qt_pos = (float(pos.x()), float(pos.y()))

            if event.button() == Qt.LeftButton:
                if self._interaction_tool == "box":
                    self._box_origin = event.position().toPoint()
                    if self._rubber_band is None:
                        return True
                    self._rubber_band.setGeometry(
                        QRect(self._box_origin, self._box_origin)
                    )
                    if self._rubber_band is None:
                    return True
                self._rubber_band.setStyleSheet(
                        "border: 1px solid #2f80ed;"
                        "background-color: rgba(47,128,237,35);"
                    )
                    self._rubber_band.show()
                else:
                    self._left_press_pos = self._vtk_position_from_qt(event)
                return True

            if event.button() == Qt.MiddleButton:
                self._start_navigation(event.modifiers(), qt_pos)
                return True

            if event.button() == Qt.RightButton:
                self._right_press_pos = self._vtk_position_from_qt(event)
                return True

        elif event_type == QEvent.MouseMove:
            pos = event.position()
            qt_pos = (float(pos.x()), float(pos.y()))

            if event.buttons() & Qt.MiddleButton:
                self._navigate(qt_pos)
                return True

            if (
                self._interaction_tool == "box"
                and self._box_origin is not None
                and event.buttons() & Qt.LeftButton
            ):
                current = event.position().toPoint()
                crossing = current.x() < self._box_origin.x()
                self._rubber_band.setStyleSheet(
                    (
                        "border: 1px solid #1c9b50;"
                        "background-color: rgba(28,155,80,35);"
                    )
                    if crossing
                    else (
                        "border: 1px solid #2f80ed;"
                        "background-color: rgba(47,128,237,35);"
                    )
                )
                self._rubber_band.setGeometry(
                    QRect(self._box_origin, current).normalized()
                )
                return True

            if event.buttons() == Qt.NoButton:
                self._update_hover_from_qt(event)
                return False

            # Consume left/right dragging so VTK cannot interpret it as camera motion.
            if event.buttons() & (Qt.LeftButton | Qt.RightButton):
                return True

        elif event_type == QEvent.MouseButtonRelease:
            vtk_pos = self._vtk_position_from_qt(event)

            if event.button() == Qt.MiddleButton:
                self._nav_mode = None
                self._nav_last_pos = None
                return True

            if event.button() == Qt.LeftButton:
                if self._interaction_tool == "box" and self._box_origin is not None:
                    end = event.position().toPoint()
                    rect = QRect(self._box_origin, end).normalized()
                    crossing = end.x() < self._box_origin.x()
                    self._rubber_band.hide() if self._rubber_band is not None else None
                    if rect.width() >= 3 and rect.height() >= 3:
                        nodes, elements = self.entities_in_screen_rect(
                            rect,
                            crossing=crossing,
                        )
                        self.box_selected.emit(
                            {
                                "nodes": nodes,
                                "elements": elements,
                                "mode": self._selection_mode_from_modifiers(
                                    event.modifiers()
                                ),
                                "crossing": crossing,
                            }
                        )
                    self._box_origin = None
                    return True

                if not self._moved(self._left_press_pos, vtk_pos):
                    entity = self.pick_entity(*vtk_pos)
                    self.entity_clicked.emit(
                        {
                            "kind": entity[0] if entity else None,
                            "tag": entity[1] if entity else None,
                            "mode": self._selection_mode_from_modifiers(
                                event.modifiers()
                            ),
                        }
                    )
                self._left_press_pos = None
                return True

            if event.button() == Qt.RightButton:
                if not self._moved(self._right_press_pos, vtk_pos):
                    entity = self.pick_entity(*vtk_pos)
                    self.context_requested.emit(
                        {"kind": entity[0], "tag": entity[1]}
                        if entity
                        else None
                    )
                self._right_press_pos = None
                return True

        elif event_type == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                entity = self.pick_entity(*self._vtk_position_from_qt(event))
                if entity:
                    self.entity_double_clicked.emit(
                        {"kind": entity[0], "tag": entity[1]}
                    )
                return True

        elif event_type == QEvent.Wheel:
            self._wheel_zoom(event.angleDelta().y())
            return True

        return super().eventFilter(obj, event)

    def _world_to_qt(self, xyz) -> tuple[float, float]:
        renderer = self.plotter.renderer
        renderer.SetWorldPoint(float(xyz[0]), float(xyz[1]), float(xyz[2]), 1.0)
        renderer.WorldToDisplay()
        display = renderer.GetDisplayPoint()
        return (
            float(display[0]),
            float(self.plotter.interactor.height() - display[1]),
        )

    @staticmethod
    def _point_inside_rect(point: tuple[float, float], rect: QRect) -> bool:
        return (
            rect.left() <= point[0] <= rect.right()
            and rect.top() <= point[1] <= rect.bottom()
        )

    @staticmethod
    def _segments_intersect(a, b, c, d) -> bool:
        def orient(p, q, r):
            value = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
            if abs(value) < 1.0e-9:
                return 0
            return 1 if value > 0 else 2

        o1 = orient(a, b, c)
        o2 = orient(a, b, d)
        o3 = orient(c, d, a)
        o4 = orient(c, d, b)
        return o1 != o2 and o3 != o4

    def _segment_intersects_rect(self, a, b, rect: QRect) -> bool:
        if self._point_inside_rect(a, rect) or self._point_inside_rect(b, rect):
            return True
        left = float(rect.left())
        right = float(rect.right())
        top = float(rect.top())
        bottom = float(rect.bottom())
        edges = (
            ((left, top), (right, top)),
            ((right, top), (right, bottom)),
            ((right, bottom), (left, bottom)),
            ((left, bottom), (left, top)),
        )
        return any(self._segments_intersect(a, b, p, q) for p, q in edges)

    def entities_in_screen_rect(
        self,
        rect: QRect,
        *,
        crossing: bool,
    ) -> tuple[set[int], set[int]]:
        if self._model is None:
            return set(), set()

        node_screen = {
            tag: self._world_to_qt(self._model.nodes[tag].xyz)
            for tag in self._visible_node_tags()
        }

        nodes: set[int] = set()
        elements: set[int] = set()

        if self._selection_filter in {"all", "node"}:
            nodes = {
                tag
                for tag, point in node_screen.items()
                if self._point_inside_rect(point, rect)
            }

        if self._selection_filter in {"all", "element"}:
            for tag in self._visible_element_tags():
                element = self._model.elements[tag]
                a = node_screen.get(element.i)
                b = node_screen.get(element.j)
                if a is None or b is None:
                    continue
                if crossing:
                    selected = self._segment_intersects_rect(a, b, rect)
                else:
                    selected = (
                        self._point_inside_rect(a, rect)
                        and self._point_inside_rect(b, rect)
                    )
                if selected:
                    elements.add(tag)

        return nodes, elements

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

    def set_selection_filter(self, value: str) -> None:
        self._selection_filter = value.lower()
        self._hover_ref = None
        self._update_highlight_overlays()

    def set_selection(self, nodes: set[int], elements: set[int]) -> None:
        self._selected_nodes = set(nodes)
        self._selected_elements = set(elements)
        self._update_highlight_overlays()

    def _visible_element_tags(self) -> set[int]:
        if self._model is None:
            return set()
        tags = set(self._model.elements) - self._hidden_elements
        if self._isolate_active:
            tags &= self._isolate_elements
        return tags

    def _visible_node_tags(self) -> set[int]:
        if self._model is None:
            return set()
        tags = set(self._model.nodes) - self._hidden_nodes
        if self._isolate_active:
            tags &= self._isolate_nodes
            for element_tag in self._visible_element_tags():
                element = self._model.elements[element_tag]
                tags.update((element.i, element.j))
        return tags

    def hide_entities(self, nodes: set[int], elements: set[int]) -> None:
        self._hidden_nodes.update(nodes)
        self._hidden_elements.update(elements)
        self._rebuild_visible_scene()

    def isolate_entities(self, nodes: set[int], elements: set[int]) -> None:
        self._isolate_active = True
        self._isolate_nodes = set(nodes)
        self._isolate_elements = set(elements)
        self._rebuild_visible_scene()

    def show_all(self) -> None:
        self._hidden_nodes.clear()
        self._hidden_elements.clear()
        self._isolate_active = False
        self._isolate_nodes.clear()
        self._isolate_elements.clear()
        self._rebuild_visible_scene()

    def _rebuild_visible_scene(self) -> None:
        if self._model is None:
            return
        camera = self.plotter.camera_position
        self._render_model(reset_camera=False)
        self.plotter.camera_position = camera
        self.plotter.render()

    def _add_ground_grid(self, model: StructuralModel) -> None:
        low, high = model.bounds()
        xmin, ymin, zmin = low
        xmax, ymax, _ = high
        span_x = max(xmax - xmin, 1.0)
        span_y = max(ymax - ymin, 1.0)

        x_values = sorted({round(n.xyz[0], 8) for n in model.nodes.values()})
        y_values = sorted({round(n.xyz[1], 8) for n in model.nodes.values()})
        dx = min(
            [b - a for a, b in zip(x_values[:-1], x_values[1:]) if b > a]
            or [span_x / 4]
        )
        dy = min(
            [b - a for a, b in zip(y_values[:-1], y_values[1:]) if b > a]
            or [span_y / 4]
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
                pickable=False,
            )
        for j in range(ny + 1):
            y = gy0 + (gy1 - gy0) * j / ny
            self.plotter.add_mesh(
                pv.Line((gx0, y, z), (gx1, y, z)),
                color=color,
                line_width=1,
                pickable=False,
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

    def _combined_element_meshes(self, visible_tags: set[int], span: float):
        if self._model is None:
            return {}
        groups: dict[str, list[object]] = {"column": [], "beam": []}
        beam_size = max(span * 0.010, 0.08)
        column_size = max(span * 0.0115, 0.09)

        for tag in visible_tags:
            element = self._model.elements[tag]
            start = self._model.nodes[element.i].xyz
            end = self._model.nodes[element.j].xyz
            is_column = element.group == "column"
            mesh = self._member_mesh(
                start,
                end,
                column_size if is_column else beam_size,
            )
            if mesh is None:
                continue
            mesh.cell_data["element_tag"] = np.full(mesh.n_cells, tag, dtype=np.int64)
            groups["column" if is_column else "beam"].append(mesh)

        combined = {}
        for name, meshes in groups.items():
            if meshes:
                combined[name] = pv.merge(meshes, merge_points=False)
        return combined

    def draw_model(self, model: StructuralModel) -> None:
        self._model = model
        self._hidden_nodes.clear()
        self._hidden_elements.clear()
        self._isolate_active = False
        self._isolate_nodes.clear()
        self._isolate_elements.clear()
        self._selected_nodes.clear()
        self._selected_elements.clear()
        self._hover_ref = None
        self._render_model(reset_camera=True)

    def _render_model(self, *, reset_camera: bool) -> None:
        self.plotter.clear()
        self._reset_scene()
        self._node_actor = None
        self._node_tags = []
        self._element_actor_data.clear()

        if self._model is None or not self._model.nodes:
            self.plotter.render()
            return

        self._add_ground_grid(self._model)

        low, high = self._model.bounds()
        span = max(
            high[0] - low[0],
            high[1] - low[1],
            high[2] - low[2],
            1.0,
        )

        visible_elements = self._visible_element_tags()
        group_meshes = self._combined_element_meshes(visible_elements, span)
        group_colors = {"column": "#687d90", "beam": "#74889b"}

        self._cell_picker.InitializePickList()
        self._cell_picker.PickFromListOn()

        for group_name, mesh in group_meshes.items():
            actor = self.plotter.add_mesh(
                mesh,
                color=group_colors[group_name],
                edge_color="#243b52",
                show_edges=True,
                line_width=1,
                smooth_shading=False,
                pickable=True,
            )
            tags = np.asarray(mesh.cell_data["element_tag"], dtype=np.int64)
            self._element_actor_data[self._actor_key(actor)] = (mesh, tags)
            self._cell_picker.AddPickList(actor)

        self._point_picker.InitializePickList()
        self._point_picker.PickFromListOn()

        visible_nodes = sorted(self._visible_node_tags())
        if visible_nodes:
            points = [self._model.nodes[tag].xyz for tag in visible_nodes]
            nodes = pv.PolyData(points)
            nodes.point_data["node_tag"] = np.asarray(visible_nodes, dtype=np.int64)
            self._node_actor = self.plotter.add_mesh(
                nodes,
                render_points_as_spheres=True,
                point_size=7,
                color="#064fd4",
                pickable=True,
            )
            self._node_tags = visible_nodes
            self._point_picker.InitializePickList()
            self._point_picker.AddPickList(self._node_actor)
            self._point_picker.PickFromListOn()

        support_size = max(span * 0.016, 0.08)
        for tag in visible_nodes:
            node = self._model.nodes[tag]
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
                pickable=False,
            )

        self._update_highlight_overlays()
        self.set_view(self._current_view)
        if reset_camera:
            self.plotter.reset_camera()
            self.plotter.camera.zoom(1.28)
        self.plotter.render()

    def pick_entity(self, x: int, y: int) -> tuple[str, int] | None:
        renderer = self.plotter.renderer

        if self._selection_filter in {"all", "node"} and self._node_actor is not None:
            if self._point_picker.Pick(x, y, 0, renderer):
                point_id = self._point_picker.GetPointId()
                if 0 <= point_id < len(self._node_tags):
                    return "node", int(self._node_tags[point_id])

        if self._selection_filter in {"all", "element"}:
            if self._cell_picker.Pick(x, y, 0, renderer):
                actor = self._cell_picker.GetActor()
                cell_id = self._cell_picker.GetCellId()
                data = self._element_actor_data.get(self._actor_key(actor))
                if data is not None and cell_id >= 0:
                    _, tags = data
                    if cell_id < len(tags):
                        return "element", int(tags[cell_id])

        return None

    def _remove_overlay(self, name: str) -> None:
        try:
            self.plotter.remove_actor(name, reset_camera=False, render=False)
        except Exception:
            pass

    def _element_overlay_mesh(self, tags: set[int]):
        if not tags:
            return None
        pieces = []
        for mesh, cell_tags in self._element_actor_data.values():
            ids = np.flatnonzero(np.isin(cell_tags, list(tags)))
            if len(ids):
                pieces.append(mesh.extract_cells(ids))
        if not pieces:
            return None
        return pieces[0] if len(pieces) == 1 else pv.merge(pieces, merge_points=False)

    def _update_highlight_overlays(self) -> None:
        for name in (
            "selection-elements",
            "selection-nodes",
            "hover-element",
            "hover-node",
        ):
            self._remove_overlay(name)

        if self._model is None:
            return

        selected_element_mesh = self._element_overlay_mesh(self._selected_elements)
        if selected_element_mesh is not None:
            self.plotter.add_mesh(
                selected_element_mesh,
                name="selection-elements",
                color="#ff9800",
                edge_color="#d46500",
                show_edges=True,
                line_width=2,
                opacity=1.0,
                pickable=False,
                render=False,
            )

        selected_node_tags = [
            tag
            for tag in self._selected_nodes
            if tag in self._model.nodes and tag in self._visible_node_tags()
        ]
        if selected_node_tags:
            selected_nodes = pv.PolyData(
                [self._model.nodes[tag].xyz for tag in selected_node_tags]
            )
            self.plotter.add_mesh(
                selected_nodes,
                name="selection-nodes",
                color="#ff6d00",
                render_points_as_spheres=True,
                point_size=13,
                pickable=False,
                render=False,
            )

        if self._hover_ref:
            kind, tag = self._hover_ref
            if kind == "element" and tag not in self._selected_elements:
                mesh = self._element_overlay_mesh({tag})
                if mesh is not None:
                    self.plotter.add_mesh(
                        mesh,
                        name="hover-element",
                        color="#20c5e8",
                        edge_color="#087a94",
                        show_edges=True,
                        line_width=2,
                        opacity=0.78,
                        pickable=False,
                        render=False,
                    )
            elif (
                kind == "node"
                and tag not in self._selected_nodes
                and tag in self._model.nodes
            ):
                node = pv.PolyData([self._model.nodes[tag].xyz])
                self.plotter.add_mesh(
                    node,
                    name="hover-node",
                    color="#21c7e8",
                    render_points_as_spheres=True,
                    point_size=11,
                    pickable=False,
                    render=False,
                )

        self.plotter.render()

    def zoom_to_selection(self, nodes: set[int], elements: set[int]) -> None:
        if self._model is None:
            return
        points = []
        for tag in nodes:
            if tag in self._model.nodes:
                points.append(self._model.nodes[tag].xyz)
        for tag in elements:
            element = self._model.elements.get(tag)
            if element:
                points.extend(
                    (self._model.nodes[element.i].xyz, self._model.nodes[element.j].xyz)
                )
        if not points:
            return

        arr = np.asarray(points, dtype=float)
        mins = arr.min(axis=0)
        maxs = arr.max(axis=0)
        span = max(float(np.max(maxs - mins)), 1.0)
        pad = span * 0.25
        bounds = (
            mins[0] - pad,
            maxs[0] + pad,
            mins[1] - pad,
            maxs[1] + pad,
            mins[2] - pad,
            maxs[2] + pad,
        )
        self.plotter.renderer.reset_camera(bounds=bounds)
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
        if self._selected_nodes or self._selected_elements:
            self.zoom_to_selection(self._selected_nodes, self._selected_elements)
            return
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.18)
        self.plotter.render()
