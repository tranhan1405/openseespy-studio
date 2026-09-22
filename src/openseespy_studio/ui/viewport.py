from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QTimer, Qt, Signal
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

from ..beam_loads import element_local_axes, resolve_self_weight_local
from ..deformed_geometry import (
    build_swept_member_geometry,
    deformed_member_frames,
    section_axis_strength_labels,
)
from ..model import (
    SHELL_ELEMENT_TYPES,
    StructuralModel,
    classify_fixity,
    shell_surface_geometry,
)
from ..postprocess import component_end_resultants, nodal_result_scalar
from ..project import (
    ConnectionData,
    ElementLoadData,
    MaterialData,
    NodalLoadData,
    PrescribedDisplacementData,
    SectionData,
    SurfaceGeometryData,
    TransformationData,
)
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
        self._connections: dict[int, ConnectionData] = {}
        self._nodal_loads: dict[int, NodalLoadData] = {}
        self._prescribed_displacements: dict[
            int,
            PrescribedDisplacementData,
        ] = {}
        self._element_loads: dict[int, ElementLoadData] = {}
        self._transformations: dict[int, TransformationData] = {}
        self._sections: dict[int, SectionData] = {}
        self._materials: dict[int, MaterialData] = {}
        self._surfaces: dict[int, SurfaceGeometryData] = {}
        self._units: dict[str, str] = {
            "length": "m",
            "force": "kN",
            "time": "s",
        }
        self._display_options = {
            "node_numbers": False,
            "element_numbers": False,
            "nodal_loads": False,
            "element_loads": False,
            "prescribed_displacements": False,
            "section_axes": False,
            "load_values": True,
        }
        self._model_representation = "tube"
        self._model_color_mode = "uniform"
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
        self._annotation_label_actors: dict[str, object] = {}
        self._undeformed_element_actors: list[object] = []
        self._navigation_proxy_actor = None
        self._navigation_lod_enabled = False
        self._undeformed_model_visible = True
        self._left_press_pos: tuple[int, int] | None = None
        self._right_press_pos: tuple[int, int] | None = None
        self._nav_mode: str | None = None
        self._nav_last_pos: tuple[float, float] | None = None
        self._interaction_tool = "select"
        self._measurement_actor_names: set[str] = set()
        self._measurement_counter = 0
        self._box_origin: QPoint | None = None
        self._rubber_band: QRubberBand | None = None
        self._result_overlay_active = False
        self._active_result_view_key: object | None = None
        self._result_view_cache: OrderedDict[
            object,
            list[tuple[object, dict[str, object]]],
        ] = OrderedDict()
        self._result_view_cache_limit = 18
        self._motion_element_mesh = None
        self._motion_node_mesh = None
        self._motion_element_node_tags: list[int] = []
        self._motion_node_tags: list[int] = []
        self._motion_topology_key: object | None = None

        # Point-label mappers are comparatively expensive while the camera is
        # moving. Keep IDs visible at rest, but suspend only the node/element
        # number actors during navigation and restore them as soon as the
        # interaction ends.
        self._id_label_restore_timer = QTimer(self)
        self._id_label_restore_timer.setSingleShot(True)
        self._id_label_restore_timer.setInterval(120)
        self._id_label_restore_timer.timeout.connect(
            self._restore_id_labels_after_navigation
        )

        # Hover picking is surprisingly expensive on large VTK meshes.  Keep
        # only the latest pointer position and pick at a modest cadence instead
        # of once for every MouseMove event.
        self._hover_pick_timer = QTimer(self)
        self._hover_pick_timer.setSingleShot(True)
        self._hover_pick_timer.timeout.connect(self._perform_pending_hover_pick)
        self._pending_hover_vtk_pos: tuple[int, int] | None = None
        self._last_hover_pick_pos: tuple[int, int] | None = None

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
        self.connection_label = QLabel("Connections: 0")
        self.material_label = QLabel("Materials: 0")
        self.section_label = QLabel("Sections: 0")
        for label in (
            self.node_label,
            self.element_label,
            self.connection_label,
            self.material_label,
            self.section_label,
        ):
            label.setStyleSheet("color: #43566a;")
        info.addWidget(self.model_label)
        info.addWidget(self.node_label)
        info.addWidget(self.element_label)
        info.addWidget(self.connection_label)
        info.addWidget(self.material_label)
        info.addWidget(self.section_label)
        header.addLayout(info)

        self.color_legend = QLabel()
        self.color_legend.setObjectName("ModelColorLegend")
        self.color_legend.setTextFormat(Qt.RichText)
        self.color_legend.setWordWrap(True)
        self.color_legend.setMaximumWidth(520)
        self.color_legend.setStyleSheet(
            "color: #34495e; padding: 2px 8px;"
        )
        self.color_legend.hide()
        header.addWidget(self.color_legend)

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

    def clear_frame_anchor(self, *, render: bool = True) -> None:
        """Remove the temporary first-node marker for Frame picking."""
        self._remove_overlay("frame-anchor")
        if render:
            self.plotter.render()

    def show_frame_anchor(self, node_tag: int) -> None:
        """Highlight the first node selected by the interactive Frame tool."""
        self.clear_frame_anchor(render=False)
        if self._model is None or int(node_tag) not in self._model.nodes:
            self.plotter.render()
            return
        point = self._model.nodes[int(node_tag)].xyz
        self.plotter.add_mesh(
            pv.PolyData([point]),
            name="frame-anchor",
            color="#087ff5",
            render_points_as_spheres=True,
            point_size=16,
            pickable=False,
            render=False,
        )
        self.plotter.render()

    def clear_truss_anchor(self, *, render: bool = True) -> None:
        """Remove the temporary first-node marker for Truss picking."""
        self._remove_overlay("truss-anchor")
        if render:
            self.plotter.render()

    def show_truss_anchor(self, node_tag: int) -> None:
        """Highlight the first node selected by the interactive Truss tool."""
        self.clear_truss_anchor(render=False)
        if self._model is None or int(node_tag) not in self._model.nodes:
            self.plotter.render()
            return
        point = self._model.nodes[int(node_tag)].xyz
        self.plotter.add_mesh(
            pv.PolyData([point]),
            name="truss-anchor",
            color="#c96b12",
            render_points_as_spheres=True,
            point_size=16,
            pickable=False,
            render=False,
        )
        self.plotter.render()

    # Compatibility aliases for projects/extensions written against the short-lived
    # Line tool API. The Studio UI now exposes a single Frame object.
    def clear_line_anchor(self, *, render: bool = True) -> None:
        self.clear_frame_anchor(render=render)

    def show_line_anchor(self, node_tag: int) -> None:
        self.show_frame_anchor(node_tag)

    def clear_measure_anchor(self, *, render: bool = True) -> None:
        """Remove the temporary first-point marker for the Measure tool."""
        self._remove_overlay("measure-anchor")
        if render:
            self.plotter.render()

    def show_measure_anchor(self, node_tag: int) -> None:
        """Highlight the first node selected for a distance measurement."""
        self.clear_measure_anchor(render=False)
        if self._model is None or int(node_tag) not in self._model.nodes:
            self.plotter.render()
            return
        point = self._model.nodes[int(node_tag)].xyz
        self.plotter.add_mesh(
            pv.PolyData([point]),
            name="measure-anchor",
            color="#6f42c1",
            render_points_as_spheres=True,
            point_size=16,
            pickable=False,
            render=False,
        )
        self.plotter.render()

    def add_distance_measurement(
        self,
        first_node_tag: int,
        second_node_tag: int,
    ) -> dict[str, float]:
        """Draw and return a node-to-node distance measurement."""
        if self._model is None:
            raise ValueError("No model is currently displayed.")
        first_tag = int(first_node_tag)
        second_tag = int(second_node_tag)
        if first_tag not in self._model.nodes or second_tag not in self._model.nodes:
            raise ValueError("Measure nodes must exist in the current model.")

        p1 = np.asarray(self._model.nodes[first_tag].xyz, dtype=float)
        p2 = np.asarray(self._model.nodes[second_tag].xyz, dtype=float)
        delta = p2 - p1
        distance = float(np.linalg.norm(delta))
        unit = str(self._units.get("length", "")).strip()
        suffix = f" {unit}" if unit else ""

        self._measurement_counter += 1
        prefix = f"measure-{self._measurement_counter}"
        line_name = f"{prefix}-line"
        point_name = f"{prefix}-points"
        label_name = f"{prefix}-label"

        self.plotter.add_mesh(
            pv.Line(p1, p2),
            name=line_name,
            color="#6f42c1",
            line_width=3,
            pickable=False,
            render=False,
        )
        self.plotter.add_mesh(
            pv.PolyData(np.vstack((p1, p2))),
            name=point_name,
            color="#6f42c1",
            render_points_as_spheres=True,
            point_size=11,
            pickable=False,
            render=False,
        )

        midpoint = (p1 + p2) * 0.5
        label = (
            f"L = {distance:.4g}{suffix}\n"
            f"ΔX = {delta[0]:.4g}{suffix}   "
            f"ΔY = {delta[1]:.4g}{suffix}   "
            f"ΔZ = {delta[2]:.4g}{suffix}"
        )
        self._add_annotation_labels(
            [midpoint],
            [label],
            name=label_name,
            text_color="#4f2f86",
            font_size=11,
            always_visible=True,
        )
        self._measurement_actor_names.update(
            {line_name, point_name, label_name}
        )
        self.clear_measure_anchor(render=False)
        self.plotter.render()

        return {
            "distance": distance,
            "dx": float(delta[0]),
            "dy": float(delta[1]),
            "dz": float(delta[2]),
        }

    def clear_measurements(self, *, render: bool = True) -> None:
        """Remove all persistent Measure overlays from the viewport."""
        self.clear_measure_anchor(render=False)
        for name in tuple(self._measurement_actor_names):
            self._remove_overlay(name)
        self._measurement_actor_names.clear()
        if render:
            self.plotter.render()

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
        self._hover_pick_timer.stop()
        self._pending_hover_vtk_pos = None
        self._id_label_restore_timer.stop()
        self._set_id_labels_visible(False, render=False)
        self._remove_overlay("hover-element")
        self._remove_overlay("hover-node")
        self._set_navigation_lod(True, render=True)

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
        self._set_id_labels_visible(False, render=False)
        self._set_navigation_lod(True, render=False)
        steps = delta_y / 120.0
        factor = math.pow(1.12, steps)
        self.plotter.camera.Zoom(factor)
        self.plotter.render()
        # Restart the debounce on every wheel event so labels are restored
        # only after the user pauses zooming.
        self._id_label_restore_timer.start()

    def _hover_pick_interval_ms(self) -> int:
        if self._model is None:
            return 45
        count = len(self._model.elements)
        if count >= 3000:
            return 100
        if count >= 1000:
            return 70
        return 40

    def _schedule_hover_from_qt(self, event) -> None:
        if event.buttons() != Qt.NoButton or self._nav_mode is not None:
            return
        vtk_pos = self._vtk_position_from_qt(event)
        if self._last_hover_pick_pos is not None:
            dx = vtk_pos[0] - self._last_hover_pick_pos[0]
            dy = vtk_pos[1] - self._last_hover_pick_pos[1]
            if dx * dx + dy * dy < 9:
                return
        self._pending_hover_vtk_pos = vtk_pos
        if not self._hover_pick_timer.isActive():
            self._hover_pick_timer.start(self._hover_pick_interval_ms())

    def _perform_pending_hover_pick(self) -> None:
        if self._pending_hover_vtk_pos is None or self._nav_mode is not None:
            return
        vtk_pos = self._pending_hover_vtk_pos
        self._pending_hover_vtk_pos = None
        self._last_hover_pick_pos = vtk_pos
        entity = self.pick_entity(*vtk_pos)
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
                self._schedule_hover_from_qt(event)
                return False

            # Consume left/right dragging so VTK cannot interpret it as camera motion.
            if event.buttons() & (Qt.LeftButton | Qt.RightButton):
                return True

        elif event_type == QEvent.MouseButtonRelease:
            vtk_pos = self._vtk_position_from_qt(event)

            if event.button() == Qt.MiddleButton:
                self._nav_mode = None
                self._nav_last_pos = None
                self._id_label_restore_timer.stop()
                self._set_navigation_lod(False, render=False)
                self._set_id_labels_visible(True, render=True)
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

    @staticmethod
    def _normalized_model_representation(value: str) -> str:
        representation = str(value or "tube").strip().lower()
        aliases = {
            "actual": "actual_section",
            "actual section": "actual_section",
            "section": "actual_section",
            "line": "centerline",
        }
        representation = aliases.get(representation, representation)
        if representation not in {"actual_section", "tube", "centerline"}:
            return "tube"
        return representation

    def set_model_representation(self, value: str) -> None:
        representation = self._normalized_model_representation(value)
        if representation == self._model_representation:
            return
        self._model_representation = representation
        if self._model is not None:
            self._rebuild_visible_scene()

    def model_representation(self) -> str:
        return self._model_representation

    @staticmethod
    def _normalized_model_color_mode(value: str) -> str:
        mode = str(value or "uniform").strip().lower().replace(" ", "_")
        aliases = {
            "type": "element_type",
            "element": "element_type",
            "elementtype": "element_type",
            "mat": "material",
            "sec": "section",
        }
        mode = aliases.get(mode, mode)
        if mode not in {"uniform", "element_type", "material", "section"}:
            return "uniform"
        return mode

    def set_model_color_mode(self, value: str) -> None:
        mode = self._normalized_model_color_mode(value)
        if mode == self._model_color_mode:
            return
        self._model_color_mode = mode
        if self._model is not None:
            self._rebuild_visible_scene()

    def model_color_mode(self) -> str:
        return self._model_color_mode

    @staticmethod
    def _display_palette() -> tuple[str, ...]:
        return (
            "#2f80ed",
            "#e67e22",
            "#27ae60",
            "#9b51e0",
            "#eb5757",
            "#00a8a8",
            "#f2c94c",
            "#6c757d",
            "#8d6e63",
            "#d81b60",
            "#3949ab",
            "#7cb342",
        )

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        text = str(value).strip().lstrip("#")
        if len(text) != 6:
            return 116, 136, 155
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))

    def _material_label(self, tag: int | None) -> str:
        if tag is None:
            return "Unassigned material"
        material = self._materials.get(int(tag))
        if material is None:
            return f"Material {int(tag)}"
        return f"{material.name} [{material.tag}]"

    def _section_label(self, tag: int | None) -> str:
        if tag is None:
            return "Unassigned section"
        section = self._sections.get(int(tag))
        if section is None:
            return f"Section {int(tag)}"
        return f"{section.name} [{section.tag}]"

    def _dominant_fiber_material(self, section: SectionData) -> int | None:
        totals: dict[int, float] = {}
        for fiber in section.compiled_fibers():
            totals[int(fiber.material_tag)] = (
                totals.get(int(fiber.material_tag), 0.0)
                + max(float(fiber.area), 0.0)
            )
        if not totals:
            return None
        return max(totals, key=lambda tag: (totals[tag], -tag))

    def _element_material_tag(self, element) -> int | None:
        if element.element_type == "truss":
            return element.truss_material_tag
        if element.section_tag is None:
            return None
        section = self._sections.get(int(element.section_tag))
        if section is None:
            return None
        if section.section_type == "Elastic":
            return section.material_tag
        if section.section_type == "Fiber":
            return self._dominant_fiber_material(section)
        return None

    def _element_color_key(self, element) -> tuple[str, object]:
        mode = self._model_color_mode
        if mode == "element_type":
            return "element_type", str(element.element_type)
        if mode == "section":
            return "section", element.section_tag
        if mode == "material":
            return "material", self._element_material_tag(element)
        return "uniform", (
            "shell"
            if element.element_type in SHELL_ELEMENT_TYPES
            else "column"
            if element.group == "column"
            else "beam"
        )

    def _element_color_label(self, key: tuple[str, object]) -> str:
        kind, value = key
        if kind == "element_type":
            return str(value)
        if kind == "section":
            return self._section_label(
                None if value is None else int(value)
            )
        if kind == "material":
            return self._material_label(
                None if value is None else int(value)
            )
        if value == "shell":
            return "Shell / Surface"
        return "Column" if value == "column" else "Beam / Truss"

    def _color_map_for_elements(
        self,
        visible_tags: set[int],
    ) -> tuple[dict[int, tuple[int, int, int]], list[tuple[str, str]]]:
        if self._model is None:
            return {}, []

        if self._model_color_mode == "uniform":
            mapping = {}
            for tag in visible_tags:
                element = self._model.elements[tag]
                color = "#687d90" if element.group == "column" else "#74889b"
                mapping[int(tag)] = self._hex_rgb(color)
            return mapping, []

        section_material_cache: dict[int, int | None] = {}
        fiber_material_tags: set[int] = set()

        def key_for_tag(tag: int) -> tuple[str, object]:
            element = self._model.elements[tag]
            if self._model_color_mode != "material":
                return self._element_color_key(element)

            if element.element_type == "truss":
                return "material", element.truss_material_tag
            if element.section_tag is None:
                return "material", None

            section_tag = int(element.section_tag)
            if section_tag not in section_material_cache:
                section = self._sections.get(section_tag)
                if section is None:
                    section_material_cache[section_tag] = None
                elif section.section_type == "Elastic":
                    section_material_cache[section_tag] = section.material_tag
                elif section.section_type == "Fiber":
                    section_material_cache[section_tag] = (
                        self._dominant_fiber_material(section)
                    )
                    fiber_material_tags.update(section.fiber_material_tags())
                else:
                    section_material_cache[section_tag] = None
            return "material", section_material_cache[section_tag]

        tag_keys = {
            int(tag): key_for_tag(int(tag))
            for tag in visible_tags
        }
        ordered_keys = sorted(
            set(tag_keys.values()),
            key=lambda item: (item[0], str(item[1])),
        )
        palette = self._display_palette()
        key_colors = {
            key: palette[index % len(palette)]
            for index, key in enumerate(ordered_keys)
        }
        mapping = {
            tag: self._hex_rgb(key_colors[key])
            for tag, key in tag_keys.items()
        }
        legend = [
            (self._element_color_label(key), key_colors[key])
            for key in ordered_keys
        ]

        if self._model_color_mode == "material":
            existing = {label for label, _ in legend}
            next_index = len(ordered_keys)
            for material_tag in sorted(fiber_material_tags):
                label = self._material_label(material_tag)
                if label in existing:
                    continue
                color = palette[next_index % len(palette)]
                legend.append((label, color))
                existing.add(label)
                next_index += 1

        return mapping, legend

    def _apply_element_colors(
        self,
        mesh,
        element_colors: dict[int, tuple[int, int, int]],
    ) -> bool:
        tags = np.asarray(mesh.cell_data.get("element_tag", []), dtype=np.int64)
        if not len(tags):
            return False
        rgb = np.asarray(
            [
                element_colors.get(
                    int(tag),
                    self._hex_rgb("#74889b"),
                )
                for tag in tags
            ],
            dtype=np.uint8,
        )
        mesh.cell_data["display_rgb"] = rgb
        return True

    def _update_model_color_legend(
        self,
        legend: list[tuple[str, str]],
    ) -> None:
        if not legend or self._model_color_mode == "uniform":
            self.color_legend.clear()
            self.color_legend.hide()
            return
        title = {
            "element_type": "Element Type",
            "material": "Material",
            "section": "Section",
        }.get(self._model_color_mode, "Color By")
        entries = []
        for label, color in legend[:12]:
            entries.append(
                f'<span style="color:{color};font-size:15px;">■</span> '
                f'{label}'
            )
        if len(legend) > 12:
            entries.append(f"+{len(legend) - 12} more")
        self.color_legend.setText(
            f"<b>Color By · {title}</b><br>" + " &nbsp; ".join(entries)
        )
        self.color_legend.show()

    def set_display_data(
        self,
        *,
        nodal_loads: dict[int, NodalLoadData] | None = None,
        prescribed_displacements: dict[
            int,
            PrescribedDisplacementData,
        ] | None = None,
        element_loads: dict[int, ElementLoadData] | None = None,
        transformations: dict[int, TransformationData] | None = None,
        sections: dict[int, SectionData] | None = None,
        materials: dict[int, MaterialData] | None = None,
        units: dict[str, str] | None = None,
        refresh: bool = True,
    ) -> None:
        geometry_changed = (
            dict(transformations or {}) != self._transformations
            or dict(sections or {}) != self._sections
            or dict(materials or {}) != self._materials
        )
        self._nodal_loads = dict(nodal_loads or {})
        self._prescribed_displacements = dict(
            prescribed_displacements or {}
        )
        self._element_loads = dict(element_loads or {})
        self._transformations = dict(transformations or {})
        self._sections = dict(sections or {})
        self._materials = dict(materials or {})
        if units is not None:
            self._units = dict(units)
        if refresh:
            if (
                geometry_changed
                and self._model is not None
                and (
                    self._model_representation == "actual_section"
                    or self._model_color_mode in {"material", "section"}
                )
            ):
                self._rebuild_visible_scene()
            else:
                self._refresh_load_overlays()
                if geometry_changed and self._display_options["section_axes"]:
                    self._update_display_option("section_axes")

    def set_display_option(self, name: str, enabled: bool) -> None:
        if name not in self._display_options:
            raise ValueError(f"Unknown display option: {name}")
        enabled = bool(enabled)
        if self._display_options[name] == enabled:
            return
        self._display_options[name] = enabled
        self._update_display_option(name)

    def display_option(self, name: str) -> bool:
        return bool(self._display_options.get(name, False))

    def set_model_info(
        self,
        name: str,
        nodes: int,
        elements: int,
        materials: int = 0,
        sections: int = 0,
        connections: int = 0,
    ) -> None:
        self.model_label.setText(f"Model: {name}")
        self.node_label.setText(f"Nodes: {nodes}")
        self.element_label.setText(f"Elements: {elements}")
        self.connection_label.setText(f"Connections: {connections}")
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
                tags.update(element.node_tags())
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
                render=False,
            )
        for j in range(ny + 1):
            y = gy0 + (gy1 - gy0) * j / ny
            self.plotter.add_mesh(
                pv.Line((gx0, y, z), (gx1, y, z)),
                color=color,
                line_width=1,
                pickable=False,
                render=False,
            )

    @staticmethod
    def _batched_centerline_mesh(model: StructuralModel, tags) -> object | None:
        """Build many frame centerlines as one PolyData object."""
        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        cell_tags: list[int] = []
        for tag in tags:
            element = model.elements.get(int(tag))
            if element is None or element.element_type in SHELL_ELEMENT_TYPES:
                continue
            node_i = model.nodes.get(element.i)
            node_j = model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue
            index = len(points)
            points.extend((node_i.xyz, node_j.xyz))
            lines.extend((2, index, index + 1))
            cell_tags.append(int(tag))
        if not points:
            return None
        mesh = pv.PolyData(
            np.asarray(points, dtype=float),
            lines=np.asarray(lines, dtype=np.int64),
            deep=True,
        )
        mesh.cell_data["element_tag"] = np.asarray(cell_tags, dtype=np.int64)
        return mesh

    @staticmethod
    def _batched_shell_mesh(
        model: StructuralModel,
        tags,
    ) -> object | None:
        """Build four-node shell surfaces as one pickable PolyData."""
        points: list[tuple[float, float, float]] = []
        faces: list[int] = []
        cell_tags: list[int] = []
        for tag in tags:
            element = model.elements.get(int(tag))
            if (
                element is None
                or element.element_type not in SHELL_ELEMENT_TYPES
                or element.k is None
                or element.l is None
            ):
                continue
            node_tags = element.node_tags()
            nodes = [model.nodes.get(node_tag) for node_tag in node_tags]
            if any(node is None for node in nodes):
                continue
            base = len(points)
            points.extend(node.xyz for node in nodes if node is not None)
            faces.extend((4, base, base + 1, base + 2, base + 3))
            cell_tags.append(int(tag))
        if not points:
            return None
        mesh = pv.PolyData(
            np.asarray(points, dtype=float),
            faces=np.asarray(faces, dtype=np.int64),
            deep=True,
        )
        mesh.cell_data["element_tag"] = np.asarray(
            cell_tags,
            dtype=np.int64,
        )
        return mesh

    @staticmethod
    def _batched_tube_mesh(
        model: StructuralModel,
        tags,
        half_width: float,
    ) -> object | None:
        """Build square-prism members directly, avoiding thousands of filters."""
        points: list[np.ndarray] = []
        faces: list[int] = []
        cell_tags: list[int] = []

        for tag in tags:
            element = model.elements.get(int(tag))
            if element is None or element.element_type in SHELL_ELEMENT_TYPES:
                continue
            node_i = model.nodes.get(element.i)
            node_j = model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue

            start = np.asarray(node_i.xyz, dtype=float)
            end = np.asarray(node_j.xyz, dtype=float)
            axis = end - start
            length = float(np.linalg.norm(axis))
            if length <= 1.0e-12:
                continue
            axis /= length

            # Pick a stable reference that is not parallel to the member.
            reference = (
                np.asarray((0.0, 0.0, 1.0), dtype=float)
                if abs(float(axis[2])) < 0.90
                else np.asarray((0.0, 1.0, 0.0), dtype=float)
            )
            local_y = np.cross(axis, reference)
            norm_y = float(np.linalg.norm(local_y))
            if norm_y <= 1.0e-12:
                reference = np.asarray((1.0, 0.0, 0.0), dtype=float)
                local_y = np.cross(axis, reference)
                norm_y = float(np.linalg.norm(local_y))
                if norm_y <= 1.0e-12:
                    continue
            local_y /= norm_y
            local_z = np.cross(axis, local_y)
            local_z /= max(float(np.linalg.norm(local_z)), 1.0e-12)

            w = float(half_width)
            offsets = (
                local_y * w + local_z * w,
                -local_y * w + local_z * w,
                -local_y * w - local_z * w,
                local_y * w - local_z * w,
            )
            base = len(points)
            points.extend([start + offset for offset in offsets])
            points.extend([end + offset for offset in offsets])

            quads = (
                (0, 3, 2, 1),
                (4, 5, 6, 7),
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
            )
            for quad in quads:
                faces.extend((4, *(base + index for index in quad)))
                cell_tags.append(int(tag))

        if not points:
            return None
        mesh = pv.PolyData(
            np.asarray(points, dtype=float),
            faces=np.asarray(faces, dtype=np.int64),
            deep=True,
        )
        mesh.cell_data["element_tag"] = np.asarray(cell_tags, dtype=np.int64)
        return mesh

    @staticmethod
    def _surface_mesh_from_swept_geometry(geometry):
        points = np.asarray(geometry.points, dtype=float)
        faces = np.asarray(geometry.faces, dtype=np.int64)

        if points.ndim != 2 or points.shape[1] != 3 or not len(points):
            return None
        if not np.all(np.isfinite(points)):
            return None
        if faces.ndim != 1 or not len(faces) or len(faces) % 5 != 0:
            return None

        records = faces.reshape((-1, 5))
        if not np.all(records[:, 0] == 4):
            return None
        connectivity = records[:, 1:]
        if connectivity.size == 0:
            return None
        if int(connectivity.min()) < 0 or int(connectivity.max()) >= len(points):
            return None

        # Own the NumPy buffers inside VTK.  A shallow faces assignment can
        # leave VTK referencing temporary connectivity memory, which may later
        # surface as absurd vtkIdList allocation requests after interaction.
        try:
            return pv.PolyData(
                np.ascontiguousarray(points),
                faces=np.ascontiguousarray(faces),
                deep=True,
            )
        except (TypeError, ValueError):
            return None

    def _actual_section_member_mesh(self, element):
        if self._model is None:
            return None
        if element.section_tag is None or element.transf_tag is None:
            return None
        section = self._sections.get(element.section_tag)
        transformation = self._transformations.get(element.transf_tag)
        if section is None or transformation is None:
            return None
        try:
            _, local_y, local_z = element_local_axes(
                self._model,
                element,
                transformation,
            )
            zeros = (0.0,) * max(int(self._model.ndf), 3)
            geometry = build_swept_member_geometry(
                section,
                self._model.nodes[element.i].xyz,
                self._model.nodes[element.j].xyz,
                local_y,
                local_z,
                zeros,
                zeros,
                ndm=self._model.ndm,
                scale=1.0,
                stations=2,
                smooth=False,
                circle_resolution=12,
            )
        except (KeyError, TypeError, ValueError):
            geometry = None
        if geometry is None:
            return None
        return self._surface_mesh_from_swept_geometry(geometry)

    def _combined_element_meshes(self, visible_tags: set[int], span: float):
        if self._model is None:
            return {}

        representation = self._normalized_model_representation(
            self._model_representation
        )
        shell_tags = [
            tag
            for tag in visible_tags
            if self._model.elements[tag].element_type in SHELL_ELEMENT_TYPES
        ]
        line_tags = [
            tag
            for tag in visible_tags
            if tag not in set(shell_tags)
        ]
        beam_tags = [
            tag
            for tag in line_tags
            if self._model.elements[tag].group != "column"
        ]
        column_tags = [
            tag
            for tag in line_tags
            if self._model.elements[tag].group == "column"
        ]

        shell_mesh = self._batched_shell_mesh(
            self._model,
            shell_tags,
        )

        if representation == "centerline":
            combined = {}
            for name, tags in (("column", column_tags), ("beam", beam_tags)):
                mesh = self._batched_centerline_mesh(self._model, tags)
                if mesh is not None:
                    combined[name] = mesh
            if shell_mesh is not None:
                combined["shell"] = shell_mesh
            return combined

        if representation == "tube":
            beam_size = max(span * 0.010, 0.08)
            column_size = max(span * 0.0115, 0.09)
            combined = {}
            column_mesh = self._batched_tube_mesh(
                self._model,
                column_tags,
                column_size,
            )
            beam_mesh = self._batched_tube_mesh(
                self._model,
                beam_tags,
                beam_size,
            )
            if column_mesh is not None:
                combined["column"] = column_mesh
            if beam_mesh is not None:
                combined["beam"] = beam_mesh
            if shell_mesh is not None:
                combined["shell"] = shell_mesh
            return combined

        # Actual-section view remains geometry-driven for line members.
        # Shells remain true surface cells for all representation modes.
        groups: dict[str, list[object]] = {"column": [], "beam": []}
        beam_size = max(span * 0.010, 0.08)
        column_size = max(span * 0.0115, 0.09)
        fallback: dict[str, list[int]] = {"column": [], "beam": []}

        for tag in line_tags:
            element = self._model.elements[tag]
            group = "column" if element.group == "column" else "beam"
            mesh = self._actual_section_member_mesh(element)
            if mesh is None:
                fallback[group].append(tag)
                continue
            mesh.cell_data["element_tag"] = np.full(
                mesh.n_cells,
                tag,
                dtype=np.int64,
            )
            groups[group].append(mesh)

        combined = {}
        for name, meshes in groups.items():
            parts = list(meshes)
            fallback_mesh = self._batched_tube_mesh(
                self._model,
                fallback[name],
                column_size if name == "column" else beam_size,
            )
            if fallback_mesh is not None:
                parts.append(fallback_mesh)
            if parts:
                combined[name] = (
                    parts[0]
                    if len(parts) == 1
                    else pv.merge(parts, merge_points=False)
                )
        if shell_mesh is not None:
            combined["shell"] = shell_mesh
        return combined


    def _fiber_material_points(
        self,
        visible_tags: set[int],
        *,
        max_total_points: int = 12000,
        max_points_per_element: int = 180,
    ) -> dict[int, list[tuple[float, float, float]]]:
        if (
            self._model is None
            or self._model_color_mode != "material"
            or self._model_representation != "actual_section"
        ):
            return {}

        grouped: dict[int, list[tuple[float, float, float]]] = {}
        total = 0
        for tag in sorted(visible_tags):
            if total >= max_total_points:
                break
            element = self._model.elements[tag]
            if element.section_tag is None or element.transf_tag is None:
                continue
            section = self._sections.get(int(element.section_tag))
            transformation = self._transformations.get(int(element.transf_tag))
            if (
                section is None
                or section.section_type != "Fiber"
                or transformation is None
            ):
                continue
            fibers = section.compiled_fibers()
            if not fibers:
                continue
            try:
                _, local_y, local_z = element_local_axes(
                    self._model,
                    element,
                    transformation,
                )
            except ValueError:
                continue
            node_i = self._model.nodes.get(element.i)
            node_j = self._model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue
            center = 0.5 * (
                np.asarray(node_i.xyz, dtype=float)
                + np.asarray(node_j.xyz, dtype=float)
            )
            y_axis = np.asarray(local_y, dtype=float)
            z_axis = np.asarray(local_z, dtype=float)

            stride = max(1, math.ceil(len(fibers) / max_points_per_element))
            for fiber in fibers[::stride]:
                if total >= max_total_points:
                    break
                point = (
                    center
                    + y_axis * float(fiber.y)
                    + z_axis * float(fiber.z)
                )
                grouped.setdefault(int(fiber.material_tag), []).append(
                    tuple(float(value) for value in point)
                )
                total += 1
        return grouped

    def _draw_fiber_material_markers(
        self,
        visible_tags: set[int],
        legend: list[tuple[str, str]],
    ) -> None:
        grouped = self._fiber_material_points(visible_tags)
        if not grouped:
            return
        label_colors = dict(legend)
        palette = self._display_palette()
        for index, material_tag in enumerate(sorted(grouped)):
            points = grouped[material_tag]
            if not points:
                continue
            color = label_colors.get(
                self._material_label(material_tag),
                palette[index % len(palette)],
            )
            self.plotter.add_mesh(
                pv.PolyData(points),
                name=f"fiber-material-{material_tag}",
                color=color,
                render_points_as_spheres=True,
                point_size=7,
                opacity=0.95,
                pickable=False,
                render=False,
            )

    def draw_model(
        self,
        model: StructuralModel,
        connections: dict[int, ConnectionData] | None = None,
        surfaces: dict[int, SurfaceGeometryData] | None = None,
    ) -> None:
        self._model = model
        self._connections = dict(connections or {})
        self._surfaces = dict(surfaces or {})
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
        # A model/visibility rebuild invalidates every cached post-processing
        # mesh because its geometry/scope may no longer match the scene.
        self._result_view_cache.clear()
        self._active_result_view_key = None
        self._result_overlay_active = False
        self.plotter.clear()
        self._measurement_actor_names.clear()
        self._measurement_counter = 0
        self._annotation_label_actors.clear()
        self._reset_scene()
        self._node_actor = None
        self._node_tags = []
        self._element_actor_data.clear()
        self._undeformed_element_actors.clear()
        self._navigation_proxy_actor = None
        self._navigation_lod_enabled = False
        self._undeformed_model_visible = True

        if self._model is None:
            self.plotter.render()
            return
        if not self._model.nodes and not self._surfaces:
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
        element_colors, color_legend = self._color_map_for_elements(
            visible_elements
        )
        self._update_model_color_legend(color_legend)

        # For large models keep a single, cheap centerline actor ready for
        # rotate/pan/zoom.  The detailed tube/section geometry is hidden only
        # while the camera is moving.
        self._navigation_lod_enabled = len(visible_elements) >= 700
        if self._navigation_lod_enabled:
            proxy_mesh = self._batched_centerline_mesh(
                self._model,
                sorted(visible_elements),
            )
            if proxy_mesh is not None:
                self._navigation_proxy_actor = self.plotter.add_mesh(
                    proxy_mesh,
                    name="navigation-lod-centerline",
                    color="#65798b",
                    line_width=1,
                    render_lines_as_tubes=False,
                    pickable=False,
                    render=False,
                )
                try:
                    self._navigation_proxy_actor.SetVisibility(0)
                except Exception:
                    pass

        self._cell_picker.InitializePickList()
        self._cell_picker.PickFromListOn()

        # Geometry Surfaces are independent preprocessing objects. Draw them
        # even before any FE nodes/elements exist so creating a Surface is
        # immediately visible in the viewport.
        for surface_tag in sorted(self._surfaces):
            surface = self._surfaces[surface_tag]
            points = np.asarray(surface.points, dtype=float)
            if points.shape != (4, 3):
                continue
            face = pv.PolyData(
                points,
                faces=np.asarray([4, 0, 1, 2, 3], dtype=np.int64),
                deep=True,
            )
            live_mesh = any(
                int(element_tag) in self._model.elements
                for element_tag in surface.generated_element_tags
            )
            actor = self.plotter.add_mesh(
                face,
                name=f"surface-geometry-{surface_tag}",
                color="#6aaed6",
                edge_color="#1f6f9f",
                show_edges=True,
                line_width=2,
                opacity=0.06 if live_mesh else 0.22,
                smooth_shading=False,
                pickable=False,
                render=False,
            )
            self._undeformed_element_actors.append(actor)

        for group_name, mesh in group_meshes.items():
            has_rgb = self._apply_element_colors(mesh, element_colors)
            actor = self.plotter.add_mesh(
                mesh,
                scalars="display_rgb" if has_rgb else None,
                rgb=has_rgb,
                show_scalar_bar=False,
                color=(
                    None
                    if has_rgb
                    else "#687d90"
                    if group_name == "column"
                    else "#8fa3b5"
                    if group_name == "shell"
                    else "#74889b"
                ),
                edge_color="#243b52",
                show_edges=(
                    group_name == "shell"
                    or self._model_representation == "tube"
                ),
                line_width=(
                    3 if self._model_representation == "centerline" else 1
                ),
                render_lines_as_tubes=(
                    self._model_representation == "centerline"
                ),
                smooth_shading=False,
                pickable=True,
                render=False,
            )
            tags = np.asarray(mesh.cell_data["element_tag"], dtype=np.int64)
            self._element_actor_data[self._actor_key(actor)] = (mesh, tags)
            self._undeformed_element_actors.append(actor)
            self._cell_picker.AddPickList(actor)

        self._draw_fiber_material_markers(
            visible_elements,
            color_legend,
        )

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
                render=False,
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

            support_type = classify_fixity(node.fixity)
            x, y, z = node.xyz

            if support_type == "Fixed":
                support = pv.Cube(
                    center=(x, y, z - support_size * 0.42),
                    x_length=support_size * 1.15,
                    y_length=support_size * 1.15,
                    z_length=support_size * 0.52,
                )
                color = "#12843d"
            else:
                support = pv.Cone(
                    center=(x, y, z - support_size * 0.58),
                    direction=(0.0, 0.0, -1.0),
                    height=support_size * 1.12,
                    radius=support_size * 0.72,
                    resolution=4,
                )
                color = (
                    "#19b74e"
                    if support_type == "Pinned"
                    else "#16a3a8"
                    if support_type.startswith("Roller")
                    else "#d7a21b"
                )

            self.plotter.add_mesh(
                support,
                color=color,
                edge_color="#0b6330",
                show_edges=True,
                line_width=1,
                pickable=False,
                render=False,
            )

            if support_type.startswith("Roller"):
                axis = support_type[-1].lower()
                direction = {
                    "x": (1.0, 0.0, 0.0),
                    "y": (0.0, 1.0, 0.0),
                    "z": (0.0, 0.0, 1.0),
                }[axis]
                half = support_size * 0.65
                p1 = (
                    x - direction[0] * half,
                    y - direction[1] * half,
                    z - support_size * 1.05 - direction[2] * half,
                )
                p2 = (
                    x + direction[0] * half,
                    y + direction[1] * half,
                    z - support_size * 1.05 + direction[2] * half,
                )
                self.plotter.add_mesh(
                    pv.Line(p1, p2),
                    color="#147b80",
                    line_width=3,
                    pickable=False,
                    render=False,
                )

        visible_node_set = set(visible_nodes)
        connection_size = max(span * 0.012, 0.06)
        for connection in self._connections.values():
            if (
                connection.node_i not in visible_node_set
                or connection.node_j not in visible_node_set
            ):
                continue
            a = self._model.nodes[connection.node_i].xyz
            b = self._model.nodes[connection.node_j].xyz

            if connection.connection_type == "twoNodeLink":
                self.plotter.add_mesh(
                    pv.Line(a, b),
                    color="#8e44ad",
                    line_width=4,
                    pickable=False,
                    render=False,
                )
                center = tuple(
                    (float(x) + float(y)) * 0.5
                    for x, y in zip(a, b)
                )
                self.plotter.add_mesh(
                    pv.Sphere(
                        radius=connection_size * 0.42,
                        center=center,
                    ),
                    color="#9b59b6",
                    pickable=False,
                    render=False,
                )
            else:
                center = tuple(
                    (float(x) + float(y)) * 0.5
                    for x, y in zip(a, b)
                )
                self.plotter.add_mesh(
                    pv.Sphere(
                        radius=connection_size * 0.58,
                        center=center,
                        theta_resolution=12,
                        phi_resolution=8,
                    ),
                    color="#8e44ad",
                    edge_color="#5e3370",
                    show_edges=True,
                    pickable=False,
                    render=False,
                )

        self._update_highlight_overlays(render=False)
        self._update_display_overlays(render=False)
        self.set_view(self._current_view, render=False)
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
        self._annotation_label_actors.pop(name, None)
        try:
            self.plotter.remove_actor(name, reset_camera=False, render=False)
        except Exception:
            pass

    def _set_navigation_lod(
        self,
        active: bool,
        *,
        render: bool = False,
    ) -> None:
        """Switch large models to a cheap centerline preview while navigating."""
        if not self._navigation_lod_enabled or self._navigation_proxy_actor is None:
            return

        detailed_visible = bool(
            (not active) and self._undeformed_model_visible
        )
        for actor in self._undeformed_element_actors:
            try:
                actor.SetVisibility(1 if detailed_visible else 0)
            except Exception:
                continue
        if self._node_actor is not None:
            try:
                self._node_actor.SetVisibility(1 if detailed_visible else 0)
            except Exception:
                pass
        try:
            self._navigation_proxy_actor.SetVisibility(
                1 if active and self._undeformed_model_visible else 0
            )
        except Exception:
            pass

        # All point-label mappers are expensive during camera motion, not just
        # node/element IDs. Restore their previous presence after navigation.
        for actor in self._annotation_label_actors.values():
            try:
                actor.SetVisibility(0 if active else 1)
            except Exception:
                continue

        if render:
            self.plotter.render()

    def _set_id_labels_visible(
        self,
        visible: bool,
        *,
        render: bool = False,
    ) -> None:
        """Cheaply hide/show expensive node and element number labels."""
        for option, name in (
            ("node_numbers", "display-node-numbers"),
            ("element_numbers", "display-element-numbers"),
        ):
            if visible and not self._display_options.get(option, False):
                continue
            actor = self._annotation_label_actors.get(name)
            if actor is None:
                continue
            try:
                actor.SetVisibility(1 if visible else 0)
            except Exception:
                try:
                    actor.SetVisibility(bool(visible))
                except Exception:
                    continue
        if render:
            self.plotter.render()

    def _restore_id_labels_after_navigation(self) -> None:
        self._set_navigation_lod(False, render=False)
        self._set_id_labels_visible(True, render=True)

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

    @classmethod
    def _element_highlight_style(
        cls,
        representation: str,
        *,
        hover: bool = False,
    ) -> dict:
        """Return overlay rendering that stays visible for each representation."""
        centerline = (
            cls._normalized_model_representation(representation)
            == "centerline"
        )
        if centerline:
            return {
                "show_edges": False,
                "line_width": 6 if hover else 8,
                "render_lines_as_tubes": True,
            }
        return {
            "show_edges": True,
            "line_width": 2,
            "render_lines_as_tubes": False,
        }

    def _update_highlight_overlays(
        self,
        *,
        render: bool = True,
    ) -> None:
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
            selection_style = self._element_highlight_style(
                self._model_representation
            )
            self.plotter.add_mesh(
                selected_element_mesh,
                name="selection-elements",
                color="#ff9800",
                edge_color="#d46500",
                show_edges=selection_style["show_edges"],
                line_width=selection_style["line_width"],
                render_lines_as_tubes=(
                    selection_style["render_lines_as_tubes"]
                ),
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
                    hover_style = self._element_highlight_style(
                        self._model_representation,
                        hover=True,
                    )
                    self.plotter.add_mesh(
                        mesh,
                        name="hover-element",
                        color="#20c5e8",
                        edge_color="#087a94",
                        show_edges=hover_style["show_edges"],
                        line_width=hover_style["line_width"],
                        render_lines_as_tubes=(
                            hover_style["render_lines_as_tubes"]
                        ),
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

        if self._display_options.get("section_axes", False):
            self._draw_section_axis_labels()

        if render:
            self.plotter.render()

    def _clear_display_overlays(self) -> None:
        for name in (
            "display-node-numbers",
            "display-element-numbers",
            "display-nodal-load-arrows",
            "display-nodal-load-labels",
            "display-element-load-arrows",
            "display-element-load-labels",
            "display-prescribed-displacement-arrows",
            "display-prescribed-displacement-rotation-arcs",
            "display-prescribed-displacement-rotation-heads",
            "display-prescribed-displacement-labels",
            "display-section-axis-y",
            "display-section-axis-z",
            "display-section-axis-labels",
        ):
            self._remove_overlay(name)

    def _model_span(self) -> float:
        if self._model is None or not self._model.nodes:
            return 1.0
        low, high = self._model.bounds()
        return max(
            high[0] - low[0],
            high[1] - low[1],
            high[2] - low[2],
            1.0,
        )

    @staticmethod
    def _vector_norm(vector) -> float:
        values = np.asarray(vector, dtype=float)
        return float(np.linalg.norm(values))

    @staticmethod
    def _format_vector(prefix: str, vector, unit: str) -> str:
        values = tuple(float(value) for value in vector)
        return (
            f"{prefix}=({values[0]:.4g}, {values[1]:.4g}, "
            f"{values[2]:.4g}) {unit}"
        )

    @staticmethod
    def _arrow_record(point, vector, *, length: float):
        direction = np.asarray(vector, dtype=float)
        norm = float(np.linalg.norm(direction))
        if norm <= 1.0e-15:
            return None
        unit = direction / norm
        target = np.asarray(point, dtype=float)
        start = target - unit * float(length)
        return start, unit, float(length)

    def _batched_arrow_mesh(self, records):
        if not records:
            return None
        points = np.asarray(
            [record[0] for record in records],
            dtype=float,
        )
        vectors = np.asarray(
            [record[1] for record in records],
            dtype=float,
        )
        scales = np.asarray(
            [record[2] for record in records],
            dtype=float,
        )
        pdata = pv.PolyData(points)
        pdata.point_data["vectors"] = vectors
        pdata.point_data["scale"] = scales
        source = pv.Arrow(
            start=(0.0, 0.0, 0.0),
            direction=(1.0, 0.0, 0.0),
            scale=1.0,
            tip_length=0.26,
            tip_radius=0.12,
            shaft_radius=0.035,
        )
        return pdata.glyph(
            orient="vectors",
            scale="scale",
            factor=1.0,
            geom=source,
        )

    @staticmethod
    def _batched_axis_line_mesh(records):
        if not records:
            return None
        points = []
        lines = []
        for center, direction, length in records:
            start = np.asarray(center, dtype=float)
            unit = np.asarray(direction, dtype=float)
            norm = float(np.linalg.norm(unit))
            if norm <= 1.0e-15:
                continue
            unit = unit / norm
            index = len(points)
            points.extend((start, start + unit * float(length)))
            lines.extend((2, index, index + 1))
        if not points:
            return None
        mesh = pv.PolyData(np.asarray(points, dtype=float))
        mesh.lines = np.asarray(lines, dtype=np.int64)
        return mesh

    def _add_annotation_labels(
        self,
        points,
        labels,
        *,
        name: str,
        text_color: str,
        font_size: int = 11,
        always_visible: bool = False,
    ) -> None:
        if not points:
            return
        actor = self.plotter.add_point_labels(
            np.asarray(points, dtype=float),
            [str(label) for label in labels],
            name=name,
            font_size=font_size,
            text_color=text_color,
            shape=None,
            show_points=False,
            always_visible=bool(always_visible),
            pickable=False,
            render=False,
        )
        # Keep the actual label actor handle. Point-label actors are not
        # guaranteed to be exposed through renderer.actors like mesh actors.
        self._annotation_label_actors[name] = actor

    def _draw_node_numbers(self) -> None:
        if self._model is None:
            return
        tags = sorted(self._visible_node_tags())
        self._add_annotation_labels(
            [self._model.nodes[tag].xyz for tag in tags],
            [str(tag) for tag in tags],
            name="display-node-numbers",
            text_color="#0b5cad",
            font_size=10,
            always_visible=True,
        )

    def _draw_element_numbers(self) -> None:
        if self._model is None:
            return
        points = []
        labels = []
        for tag in sorted(self._visible_element_tags()):
            element = self._model.elements.get(tag)
            if element is None:
                continue
            nodes = [
                self._model.nodes.get(node_tag)
                for node_tag in element.node_tags()
            ]
            if not nodes or any(node is None for node in nodes):
                continue
            points.append(
                tuple(
                    sum(float(node.xyz[index]) for node in nodes if node is not None)
                    / len(nodes)
                    for index in range(3)
                )
            )
            labels.append(str(tag))
        self._add_annotation_labels(
            points,
            labels,
            name="display-element-numbers",
            text_color="#7a3d00",
            font_size=10,
            always_visible=True,
        )

    def _draw_nodal_loads(self) -> None:
        if self._model is None or not self._nodal_loads:
            return
        visible_nodes = self._visible_node_tags()
        candidates = [
            load
            for load in self._nodal_loads.values()
            if load.node_tag in visible_nodes
            and load.node_tag in self._model.nodes
        ]
        if not candidates:
            return

        max_force = max(
            (
                self._vector_norm(load.values[:3])
                for load in candidates
            ),
            default=0.0,
        )
        span = self._model_span()
        base_length = max(span * 0.10, 0.12)
        arrows = []
        label_points = []
        labels = []
        force_unit = str(self._units.get("force", ""))
        moment_unit = (
            f"{force_unit}·{self._units.get('length', '')}"
        )

        for load in candidates:
            point = np.asarray(
                self._model.nodes[load.node_tag].xyz,
                dtype=float,
            )
            force = tuple(float(value) for value in load.values[:3])
            moment = tuple(float(value) for value in load.values[3:6])
            force_mag = self._vector_norm(force)
            arrow = None
            if force_mag > 1.0e-15:
                ratio = (
                    force_mag / max_force
                    if max_force > 1.0e-15
                    else 1.0
                )
                arrow = self._arrow_record(
                    point,
                    force,
                    length=base_length * (0.45 + 0.55 * ratio),
                )
                if arrow is not None:
                    arrows.append(arrow)

            parts = [f"Node {load.node_tag}"]
            if force_mag > 1.0e-15:
                parts.append(
                    self._format_vector("F", force, force_unit)
                )
            if self._vector_norm(moment) > 1.0e-15:
                parts.append(
                    self._format_vector("M", moment, moment_unit)
                )
            if len(parts) > 1:
                label_points.append(point)
                labels.append("\n".join(parts))

        arrow_mesh = self._batched_arrow_mesh(arrows)
        if arrow_mesh is not None:
            self.plotter.add_mesh(
                arrow_mesh,
                name="display-nodal-load-arrows",
                color="#d62828",
                smooth_shading=False,
                pickable=False,
                render=False,
            )
        if self._display_options["load_values"]:
            self._add_annotation_labels(
                label_points,
                labels,
                name="display-nodal-load-labels",
                text_color="#a71919",
                font_size=10,
                always_visible=True,
            )

    @staticmethod
    def _prescribed_displacement_axis(dof: int) -> np.ndarray:
        index = (int(dof) - 1) % 3
        axis = np.zeros(3, dtype=float)
        axis[index] = 1.0
        return axis

    @staticmethod
    def _rotation_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        unit_axis = np.asarray(axis, dtype=float)
        norm = float(np.linalg.norm(unit_axis))
        if norm <= 1.0e-15:
            unit_axis = np.asarray((0.0, 0.0, 1.0), dtype=float)
        else:
            unit_axis = unit_axis / norm

        reference = (
            np.asarray((0.0, 0.0, 1.0), dtype=float)
            if abs(float(unit_axis[2])) < 0.9
            else np.asarray((1.0, 0.0, 0.0), dtype=float)
        )
        basis_u = np.cross(unit_axis, reference)
        basis_u /= max(float(np.linalg.norm(basis_u)), 1.0e-15)
        basis_v = np.cross(unit_axis, basis_u)
        basis_v /= max(float(np.linalg.norm(basis_v)), 1.0e-15)
        return basis_u, basis_v

    def _rotation_arc_mesh(self, records):
        if not records:
            return None, []
        all_points: list[np.ndarray] = []
        lines: list[int] = []
        arrow_records = []
        point_offset = 0

        for center, axis, sign, radius in records:
            basis_u, basis_v = self._rotation_basis(axis)
            direction_sign = 1.0 if float(sign) >= 0.0 else -1.0
            angles = np.linspace(
                -0.75 * math.pi,
                0.75 * math.pi,
                25,
            ) * direction_sign
            arc_points = [
                np.asarray(center, dtype=float)
                + float(radius)
                * (
                    math.cos(float(angle)) * basis_u
                    + math.sin(float(angle)) * basis_v
                )
                for angle in angles
            ]
            all_points.extend(arc_points)
            lines.extend(
                [
                    len(arc_points),
                    *range(point_offset, point_offset + len(arc_points)),
                ]
            )
            point_offset += len(arc_points)

            end = arc_points[-1]
            angle = float(angles[-1])
            tangent = direction_sign * (
                -math.sin(angle) * basis_u
                + math.cos(angle) * basis_v
            )
            tangent_norm = float(np.linalg.norm(tangent))
            if tangent_norm > 1.0e-15:
                tangent = tangent / tangent_norm
                head_length = max(float(radius) * 0.42, 1.0e-6)
                arrow_records.append(
                    (
                        end - tangent * head_length,
                        tangent,
                        head_length,
                    )
                )

        mesh = pv.PolyData(np.asarray(all_points, dtype=float))
        mesh.lines = np.asarray(lines, dtype=np.int64)
        return mesh, arrow_records

    def _draw_prescribed_displacements(self) -> None:
        if self._model is None or not self._prescribed_displacements:
            return

        visible_nodes = self._visible_node_tags()
        candidates = [
            displacement
            for displacement in self._prescribed_displacements.values()
            if displacement.node_tag in visible_nodes
            and displacement.node_tag in self._model.nodes
        ]
        if not candidates:
            return

        span = self._model_span()
        base_length = max(span * 0.10, 0.12)
        translational = [
            displacement
            for displacement in candidates
            if displacement.dof <= 3
        ]
        max_translation = max(
            (abs(float(item.value)) for item in translational),
            default=0.0,
        )

        arrows = []
        rotation_records = []
        label_points = []
        labels = []
        length_unit = str(self._units.get("length", ""))
        dof_labels = ("UX", "UY", "UZ", "RX", "RY", "RZ")

        for displacement in candidates:
            point = np.asarray(
                self._model.nodes[displacement.node_tag].xyz,
                dtype=float,
            )
            value = float(displacement.value)
            axis = self._prescribed_displacement_axis(displacement.dof)
            dof_label = dof_labels[displacement.dof - 1]

            if displacement.dof <= 3:
                if abs(value) > 1.0e-15:
                    ratio = (
                        abs(value) / max_translation
                        if max_translation > 1.0e-15
                        else 1.0
                    )
                    signed_axis = axis * (1.0 if value >= 0.0 else -1.0)
                    arrow_length = base_length * (
                        0.55 + 0.45 * ratio
                    )
                    arrows.append(
                        (
                            point,
                            signed_axis,
                            arrow_length,
                        )
                    )
                unit = length_unit
            else:
                if abs(value) > 1.0e-15:
                    radius = max(base_length * 0.48, span * 0.035)
                    rotation_records.append(
                        (
                            point,
                            axis,
                            1.0 if value >= 0.0 else -1.0,
                            radius,
                        )
                    )
                unit = "rad"

            label_points.append(point)
            labels.append(
                f"Node {displacement.node_tag}\n"
                f"{dof_label} = {value:+.4g} {unit}"
            )

        arrow_mesh = self._batched_arrow_mesh(arrows)
        if arrow_mesh is not None:
            self.plotter.add_mesh(
                arrow_mesh,
                name="display-prescribed-displacement-arrows",
                color="#6a1b9a",
                smooth_shading=False,
                pickable=False,
                render=False,
            )

        rotation_mesh, rotation_heads = self._rotation_arc_mesh(
            rotation_records
        )
        if rotation_mesh is not None:
            self.plotter.add_mesh(
                rotation_mesh,
                name="display-prescribed-displacement-rotation-arcs",
                color="#7b1fa2",
                line_width=4,
                pickable=False,
                render=False,
            )
        rotation_head_mesh = self._batched_arrow_mesh(rotation_heads)
        if rotation_head_mesh is not None:
            self.plotter.add_mesh(
                rotation_head_mesh,
                name="display-prescribed-displacement-rotation-heads",
                color="#7b1fa2",
                smooth_shading=False,
                pickable=False,
                render=False,
            )

        if self._display_options["load_values"]:
            self._add_annotation_labels(
                label_points,
                labels,
                name="display-prescribed-displacement-labels",
                text_color="#5b1677",
                font_size=10,
                always_visible=True,
            )

    def _element_load_global_vector(
        self,
        load: ElementLoadData,
    ) -> tuple[np.ndarray, str] | None:
        if self._model is None:
            return None
        element = self._model.elements.get(load.element_tag)
        if element is None or element.transf_tag is None:
            return None
        transformation = self._transformations.get(element.transf_tag)
        if transformation is None:
            return None
        try:
            local_x, local_y, local_z = element_local_axes(
                self._model,
                element,
                transformation,
            )
            if load.load_type == "Uniform":
                local = (load.wx, load.wy, load.wz)
                prefix = "w"
            elif load.load_type == "Point":
                local = (load.px, load.py, load.pz)
                prefix = "P"
            else:
                local = resolve_self_weight_local(
                    load,
                    self._model,
                    self._sections,
                    self._materials,
                    self._transformations,
                    self._units,
                )
                prefix = "w"
        except ValueError:
            return None

        global_vector = (
            np.asarray(local_x, dtype=float) * float(local[0])
            + np.asarray(local_y, dtype=float) * float(local[1])
            + np.asarray(local_z, dtype=float) * float(local[2])
        )
        return global_vector, prefix

    def _section_axis_label_tags(self) -> set[int]:
        tags = set(self._selected_elements)
        if self._hover_ref and self._hover_ref[0] == "element":
            tags.add(int(self._hover_ref[1]))
        return tags & self._visible_element_tags()

    def _draw_section_axis_labels(self) -> None:
        if self._model is None:
            return

        self._remove_overlay("display-section-axis-labels")
        label_tags = self._section_axis_label_tags()
        if not label_tags:
            return

        axis_length = max(self._model_span() * 0.075, 0.10)
        label_points = []
        labels = []

        for tag in sorted(label_tags):
            element = self._model.elements.get(tag)
            if element is None or element.transf_tag is None:
                continue
            transformation = self._transformations.get(element.transf_tag)
            if transformation is None:
                continue
            node_i = self._model.nodes.get(element.i)
            node_j = self._model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue
            try:
                _, local_y, local_z = element_local_axes(
                    self._model,
                    element,
                    transformation,
                )
            except ValueError:
                continue

            center = np.asarray(
                [
                    0.5 * (float(x) + float(y))
                    for x, y in zip(node_i.xyz, node_j.xyz)
                ],
                dtype=float,
            )
            y_axis = np.asarray(local_y, dtype=float)
            z_axis = np.asarray(local_z, dtype=float)
            section = (
                self._sections.get(element.section_tag)
                if element.section_tag is not None
                else None
            )
            y_label, z_label = section_axis_strength_labels(
                section,
                self._materials,
            )
            label_points.extend(
                (
                    center + y_axis * axis_length * 1.08,
                    center + z_axis * axis_length * 1.08,
                )
            )
            def selected_axis_text(axis: str, label: str) -> str:
                if "·" not in label:
                    return axis
                detail = label.split("·", 1)[-1].strip().upper()
                return f"{axis}  ·  {detail}"

            labels.extend(
                (
                    selected_axis_text("y", y_label),
                    selected_axis_text("z", z_label),
                )
            )

        self._add_annotation_labels(
            label_points,
            labels,
            name="display-section-axis-labels",
            text_color="#1f2937",
            font_size=11,
            always_visible=True,
        )

    def _draw_section_axes(self) -> None:
        if self._model is None:
            return

        axis_length = max(self._model_span() * 0.075, 0.10)
        y_records = []
        z_records = []
        shell_x_records = []
        shell_y_records = []
        shell_n_records = []

        for tag in sorted(self._visible_element_tags()):
            element = self._model.elements.get(tag)
            if element is None:
                continue

            if element.element_type in SHELL_ELEMENT_TYPES:
                shell_nodes = [
                    self._model.nodes.get(node_tag)
                    for node_tag in element.node_tags()
                ]
                if any(node is None for node in shell_nodes):
                    continue
                points = np.asarray(
                    [node.xyz for node in shell_nodes],
                    dtype=float,
                )
                center = np.mean(points, axis=0)
                normal = np.zeros(3, dtype=float)
                for index in range(4):
                    current = points[index]
                    following = points[(index + 1) % 4]
                    normal += np.asarray(
                        [
                            (current[1] - following[1])
                            * (current[2] + following[2]),
                            (current[2] - following[2])
                            * (current[0] + following[0]),
                            (current[0] - following[0])
                            * (current[1] + following[1]),
                        ],
                        dtype=float,
                    )
                normal_norm = float(np.linalg.norm(normal))
                if normal_norm <= 1.0e-12:
                    continue
                normal /= normal_norm

                if element.shell_local_x is not None:
                    local_x = np.asarray(
                        element.shell_local_x,
                        dtype=float,
                    )
                else:
                    local_x = points[1] - points[0]
                local_x = local_x - np.dot(local_x, normal) * normal
                local_x_norm = float(np.linalg.norm(local_x))
                if local_x_norm <= 1.0e-12:
                    local_x = points[3] - points[0]
                    local_x = (
                        local_x - np.dot(local_x, normal) * normal
                    )
                    local_x_norm = float(np.linalg.norm(local_x))
                if local_x_norm <= 1.0e-12:
                    continue
                local_x /= local_x_norm
                local_y = np.cross(normal, local_x)
                local_y_norm = float(np.linalg.norm(local_y))
                if local_y_norm <= 1.0e-12:
                    continue
                local_y /= local_y_norm

                shell_x_records.append(
                    (center, local_x, axis_length)
                )
                shell_y_records.append(
                    (center, local_y, axis_length)
                )
                shell_n_records.append(
                    (center, normal, axis_length)
                )
                continue

            if element.transf_tag is None:
                continue
            transformation = self._transformations.get(element.transf_tag)
            if transformation is None:
                continue
            node_i = self._model.nodes.get(element.i)
            node_j = self._model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue
            try:
                _, local_y, local_z = element_local_axes(
                    self._model,
                    element,
                    transformation,
                )
            except ValueError:
                continue

            center = np.asarray(
                [
                    0.5 * (float(x) + float(y))
                    for x, y in zip(node_i.xyz, node_j.xyz)
                ],
                dtype=float,
            )
            y_records.append(
                (center, np.asarray(local_y, dtype=float), axis_length)
            )
            z_records.append(
                (center, np.asarray(local_z, dtype=float), axis_length)
            )

        y_mesh = self._batched_axis_line_mesh(y_records)
        if y_mesh is not None:
            self.plotter.add_mesh(
                y_mesh,
                name="display-section-axis-y",
                color="#2e8b57",
                line_width=2,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )
        z_mesh = self._batched_axis_line_mesh(z_records)
        if z_mesh is not None:
            self.plotter.add_mesh(
                z_mesh,
                name="display-section-axis-z",
                color="#4169e1",
                line_width=2,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )

        shell_x_mesh = self._batched_axis_line_mesh(shell_x_records)
        if shell_x_mesh is not None:
            self.plotter.add_mesh(
                shell_x_mesh,
                name="display-shell-axis-x",
                color="#c0392b",
                line_width=2,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )
        shell_y_mesh = self._batched_axis_line_mesh(shell_y_records)
        if shell_y_mesh is not None:
            self.plotter.add_mesh(
                shell_y_mesh,
                name="display-shell-axis-y",
                color="#2e8b57",
                line_width=2,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )
        shell_n_mesh = self._batched_axis_line_mesh(shell_n_records)
        if shell_n_mesh is not None:
            self.plotter.add_mesh(
                shell_n_mesh,
                name="display-shell-axis-normal",
                color="#4169e1",
                line_width=3,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )

        self._draw_section_axis_labels()

    def _draw_element_loads(self) -> None:
        if self._model is None or not self._element_loads:
            return
        visible_elements = self._visible_element_tags()
        entries = []
        max_magnitude = 0.0
        for load in self._element_loads.values():
            if load.element_tag not in visible_elements:
                continue
            element = self._model.elements.get(load.element_tag)
            if element is None:
                continue
            if load.load_type == "SurfacePressure":
                try:
                    _center, shell_normal, _area = shell_surface_geometry(
                        self._model,
                        element,
                    )
                except ValueError:
                    continue
                vector = tuple(
                    float(load.pressure) * float(value)
                    for value in shell_normal
                )
                prefix = "P_normal"
                magnitude = abs(float(load.pressure))
            else:
                resolved = self._element_load_global_vector(load)
                if resolved is None:
                    continue
                vector, prefix = resolved
                magnitude = self._vector_norm(vector)
            max_magnitude = max(max_magnitude, magnitude)
            entries.append((load, element, vector, prefix, magnitude))

        if not entries:
            return

        span = self._model_span()
        base_length = max(span * 0.085, 0.10)
        arrows = []
        label_points = []
        labels = []
        force_unit = str(self._units.get("force", ""))
        line_unit = (
            f"{force_unit}/{self._units.get('length', '')}"
        )

        for load, element, vector, prefix, magnitude in entries:
            ratio = (
                magnitude / max_magnitude
                if max_magnitude > 1.0e-15
                else 1.0
            )
            arrow_length = base_length * (0.45 + 0.55 * ratio)

            if load.load_type == "SurfacePressure":
                node_tags = element.node_tags()
                shell_points = [
                    np.asarray(
                        self._model.nodes[node_tag].xyz,
                        dtype=float,
                    )
                    for node_tag in node_tags
                    if node_tag in self._model.nodes
                ]
                if len(shell_points) != 4:
                    continue
                p1, p2, p3, p4 = shell_points
                for xi, eta in (
                    (0.25, 0.25),
                    (0.75, 0.25),
                    (0.75, 0.75),
                    (0.25, 0.75),
                ):
                    point = (
                        (1.0 - xi) * (1.0 - eta) * p1
                        + xi * (1.0 - eta) * p2
                        + xi * eta * p3
                        + (1.0 - xi) * eta * p4
                    )
                    arrow = self._arrow_record(
                        point,
                        vector,
                        length=arrow_length,
                    )
                    if arrow is not None:
                        arrows.append(arrow)
                label_point = 0.25 * (p1 + p2 + p3 + p4)
                unit = (
                    f"{force_unit}/{self._units.get('length', '')}²"
                )
            else:
                node_i = self._model.nodes.get(element.i)
                node_j = self._model.nodes.get(element.j)
                if node_i is None or node_j is None:
                    continue
                p_i = np.asarray(node_i.xyz, dtype=float)
                p_j = np.asarray(node_j.xyz, dtype=float)
                member = p_j - p_i

            if load.load_type in {"Uniform", "SelfWeight"}:
                positions = (0.18, 0.39, 0.61, 0.82)
                for position in positions:
                    point = p_i + float(position) * member
                    arrow = self._arrow_record(
                        point,
                        vector,
                        length=arrow_length,
                    )
                    if arrow is not None:
                        arrows.append(arrow)
                label_point = p_i + 0.5 * member
                unit = line_unit
            elif load.load_type != "SurfacePressure":
                position = min(max(float(load.x_over_l), 0.0), 1.0)
                label_point = p_i + position * member
                arrow = self._arrow_record(
                    label_point,
                    vector,
                    length=arrow_length,
                )
                if arrow is not None:
                    arrows.append(arrow)
                unit = force_unit

            local_vector = (
                (load.wx, load.wy, load.wz)
                if load.load_type == "Uniform"
                else (load.px, load.py, load.pz)
                if load.load_type == "Point"
                else None
            )
            title = (
                f"Elem {load.element_tag} · {load.load_type}"
            )
            if local_vector is not None:
                title += "\n" + self._format_vector(
                    f"{prefix}_local",
                    local_vector,
                    unit,
                )
            elif load.load_type == "SurfacePressure":
                title += (
                    "\n"
                    + f"P={load.pressure:g} {unit}"
                    + " · +outward / -inward"
                )
            else:
                title += "\nSelf weight"
            label_points.append(label_point)
            labels.append(title)

        arrow_mesh = self._batched_arrow_mesh(arrows)
        if arrow_mesh is not None:
            self.plotter.add_mesh(
                arrow_mesh,
                name="display-element-load-arrows",
                color="#c2185b",
                smooth_shading=False,
                pickable=False,
                render=False,
            )
        if self._display_options["load_values"]:
            self._add_annotation_labels(
                label_points,
                labels,
                name="display-element-load-labels",
                text_color="#9b164a",
                font_size=10,
                always_visible=True,
            )

    def _update_display_option(
        self,
        name: str,
        *,
        render: bool = True,
    ) -> None:
        actor_names = {
            "node_numbers": ("display-node-numbers",),
            "element_numbers": ("display-element-numbers",),
            "nodal_loads": (
                "display-nodal-load-arrows",
                "display-nodal-load-labels",
            ),
            "element_loads": (
                "display-element-load-arrows",
                "display-element-load-labels",
            ),
            "prescribed_displacements": (
                "display-prescribed-displacement-arrows",
                "display-prescribed-displacement-rotation-arcs",
                "display-prescribed-displacement-rotation-heads",
                "display-prescribed-displacement-labels",
            ),
            "section_axes": (
                "display-section-axis-y",
                "display-section-axis-z",
                "display-section-axis-labels",
                "display-shell-axis-x",
                "display-shell-axis-y",
                "display-shell-axis-normal",
            ),
            "load_values": (
                "display-nodal-load-labels",
                "display-element-load-labels",
                "display-prescribed-displacement-labels",
            ),
        }
        for actor_name in actor_names[name]:
            self._remove_overlay(actor_name)

        if self._model is None or not self._model.nodes:
            if render:
                self.plotter.render()
            return

        if name == "node_numbers" and self._display_options[name]:
            self._draw_node_numbers()
        elif name == "element_numbers" and self._display_options[name]:
            self._draw_element_numbers()
        elif name == "nodal_loads" and self._display_options[name]:
            self._draw_nodal_loads()
        elif name == "element_loads" and self._display_options[name]:
            self._draw_element_loads()
        elif (
            name == "prescribed_displacements"
            and self._display_options[name]
        ):
            self._draw_prescribed_displacements()
        elif name == "section_axes" and self._display_options[name]:
            self._draw_section_axes()
        elif name == "load_values" and self._display_options[name]:
            if self._display_options["nodal_loads"]:
                self._draw_nodal_loads()
            if self._display_options["element_loads"]:
                self._draw_element_loads()
            if self._display_options["prescribed_displacements"]:
                self._draw_prescribed_displacements()

        if render:
            self.plotter.render()

    def _refresh_load_overlays(self, *, render: bool = True) -> None:
        for name in (
            "display-nodal-load-arrows",
            "display-nodal-load-labels",
            "display-element-load-arrows",
            "display-element-load-labels",
            "display-prescribed-displacement-arrows",
            "display-prescribed-displacement-rotation-arcs",
            "display-prescribed-displacement-rotation-heads",
            "display-prescribed-displacement-labels",
        ):
            self._remove_overlay(name)

        if self._model is not None and self._model.nodes:
            if self._display_options["nodal_loads"]:
                self._draw_nodal_loads()
            if self._display_options["element_loads"]:
                self._draw_element_loads()
            if self._display_options["prescribed_displacements"]:
                self._draw_prescribed_displacements()

        if render and (
            self._display_options["nodal_loads"]
            or self._display_options["element_loads"]
            or self._display_options["prescribed_displacements"]
        ):
            self.plotter.render()

    def _update_display_overlays(self, *, render: bool = True) -> None:
        self._clear_display_overlays()
        if self._model is None or not self._model.nodes:
            if render:
                self.plotter.render()
            return
        if self._display_options["node_numbers"]:
            self._draw_node_numbers()
        if self._display_options["element_numbers"]:
            self._draw_element_numbers()
        if self._display_options["nodal_loads"]:
            self._draw_nodal_loads()
        if self._display_options["element_loads"]:
            self._draw_element_loads()
        if self._display_options["prescribed_displacements"]:
            self._draw_prescribed_displacements()
        if self._display_options["section_axes"]:
            self._draw_section_axes()
        if render:
            self.plotter.render()

    def set_undeformed_model_visible(
        self,
        visible: bool,
        *,
        render: bool = True,
    ) -> None:
        """Show/hide the original structural frame under result overlays."""
        visible = bool(visible)
        self._undeformed_model_visible = visible

        for actor in list(self._undeformed_element_actors):
            try:
                actor.SetVisibility(1 if visible else 0)
            except Exception:
                continue

        if self._node_actor is not None:
            try:
                self._node_actor.SetVisibility(1 if visible else 0)
            except Exception:
                pass

        if visible:
            self._update_highlight_overlays(render=False)
        else:
            for name in (
                "selection-elements",
                "selection-nodes",
                "hover-element",
                "hover-node",
            ):
                self._remove_overlay(name)

        if render:
            self.plotter.render()

    @staticmethod
    def _normalized_deformation_display_mode(mode: str) -> str:
        value = str(mode or "deformed_only").strip().lower()
        aliases = {
            "deformed": "deformed_only",
            "deformed only": "deformed_only",
            "undeformed": "undeformed_only",
            "undeformed only": "undeformed_only",
            "both": "both",
            "undeformed + deformed": "both",
        }
        value = aliases.get(value, value)
        if value not in {"deformed_only", "both", "undeformed_only"}:
            return "deformed_only"
        return value

    @staticmethod
    def _normalized_deformation_representation(value: str) -> str:
        representation = str(value or "actual_section").strip().lower()
        aliases = {
            "actual": "actual_section",
            "section": "actual_section",
            "extruded": "actual_section",
            "extruded section": "actual_section",
            "actual section": "actual_section",
            "line": "centerline",
        }
        representation = aliases.get(representation, representation)
        if representation not in {"actual_section", "tube", "centerline"}:
            return "actual_section"
        return representation

    def clear_result_overlay(self, *, render: bool = True) -> None:
        for name in (
            "result-overlay",
            "result-section-surface",
            "result-nodes",
            "result-force-diagram",
            "result-force-connectors",
            "result-force-labels",
            "result-contour",
            "result-contour-nodes",
            "result-shell-contour",
            "result-hinge-members",
            "result-hinge-points",
            "motion-overlay",
            "motion-nodes",
        ):
            self._remove_overlay(name)
        self._result_overlay_active = False
        self._active_result_view_key = None
        self._motion_element_mesh = None
        self._motion_node_mesh = None
        self._motion_element_node_tags = []
        self._motion_node_tags = []
        self._motion_topology_key = None
        self.set_undeformed_model_visible(True, render=False)
        if render:
            self.plotter.render()

    @staticmethod
    def _result_scope_key(tags: set[int] | None) -> tuple[int, ...]:
        return tuple(sorted(int(tag) for tag in (tags or ())))

    def _result_view_key(
        self,
        source_key: object | None,
        kind: str,
        *parts: object,
    ) -> object | None:
        if source_key is None:
            return None
        try:
            key = (source_key, str(kind), *parts)
            hash(key)
        except TypeError:
            return None
        return key

    def _show_cached_result_view(self, key: object | None) -> bool:
        if key is None:
            return False
        if (
            key == self._active_result_view_key
            and self._result_overlay_active
        ):
            return True

        cached = self._result_view_cache.get(key)
        if cached is None:
            return False

        self.clear_result_overlay(render=False)
        for mesh, raw_kwargs in cached:
            kwargs = dict(raw_kwargs)
            kwargs["render"] = False
            self.plotter.add_mesh(mesh, **kwargs)

        self._result_view_cache.move_to_end(key)
        self._active_result_view_key = key
        self._result_overlay_active = True
        self.plotter.render()
        return True

    def _remember_result_view(
        self,
        key: object | None,
        entries: list[tuple[object, dict[str, object]]],
    ) -> None:
        if key is None or not entries:
            return
        self._result_view_cache[key] = [
            (mesh, dict(kwargs))
            for mesh, kwargs in entries
        ]
        self._result_view_cache.move_to_end(key)
        while len(self._result_view_cache) > self._result_view_cache_limit:
            self._result_view_cache.popitem(last=False)
        self._active_result_view_key = key

    def _show_vector_overlay(
        self,
        vectors: dict[str, object],
        *,
        scale: float,
        label: str,
        representation: str = "actual_section",
        smooth_curvature: bool = True,
        stations: int = 17,
        node_tags: set[int] | None = None,
        element_tags: set[int] | None = None,
        view_cache_key: object | None = None,
    ) -> None:
        if self._model is None or not self._model.elements:
            return
        if self._show_cached_result_view(view_cache_key):
            return

        representation = self._normalized_deformation_representation(
            representation
        )
        self.clear_result_overlay(render=False)
        entries: list[tuple[object, dict[str, object]]] = []
        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        magnitudes: list[float] = []
        surface_meshes: list[object] = []

        def raw_vector(tag: int) -> object:
            return vectors.get(
                str(tag),
                vectors.get(tag, (0.0, 0.0, 0.0)),
            )

        def displaced(tag: int):
            node = self._model.nodes[tag]
            raw = raw_vector(tag)
            values = list(raw) if raw is not None else []
            while len(values) < 3:
                values.append(0.0)
            if self._model.ndm == 2:
                dx = float(values[0])
                dy = float(values[1])
                dz = 0.0
            else:
                dx, dy, dz = (
                    float(values[0]),
                    float(values[1]),
                    float(values[2]),
                )
            xyz = (
                node.xyz[0] + scale * dx,
                node.xyz[1] + scale * dy,
                node.xyz[2] + scale * dz,
            )
            magnitude = math.sqrt(dx * dx + dy * dy + dz * dz)
            return xyz, magnitude

        visible_elements = set(self._visible_element_tags())
        if element_tags:
            visible_elements.intersection_update(element_tags)
        elif node_tags:
            visible_elements = {
                tag
                for tag in visible_elements
                if all(
                    node_tag in node_tags
                    for node_tag in self._model.elements[tag].node_tags()
                )
            }

        for tag in sorted(visible_elements):
            element = self._model.elements[tag]
            element_node_tags = element.node_tags()
            if any(
                node_tag not in self._model.nodes
                for node_tag in element_node_tags
            ):
                continue

            if element.element_type in SHELL_ELEMENT_TYPES:
                if len(element_node_tags) != 4:
                    continue
                shell_points: list[tuple[float, float, float]] = []
                shell_magnitudes: list[float] = []
                for node_tag in element_node_tags:
                    point, magnitude = displaced(node_tag)
                    shell_points.append(point)
                    shell_magnitudes.append(magnitude)
                surface = pv.PolyData(
                    np.asarray(shell_points, dtype=float),
                    faces=np.asarray(
                        [4, 0, 1, 2, 3],
                        dtype=np.int64,
                    ),
                    deep=True,
                )
                surface.point_data["magnitude"] = np.asarray(
                    shell_magnitudes,
                    dtype=float,
                )
                surface_meshes.append(surface)
                continue

            rendered_surface = False
            if representation == "actual_section":
                section = (
                    self._sections.get(element.section_tag)
                    if element.section_tag is not None
                    else None
                )
                transformation = (
                    self._transformations.get(element.transf_tag)
                    if element.transf_tag is not None
                    else None
                )
                if section is not None and transformation is not None:
                    try:
                        _, local_y, local_z = element_local_axes(
                            self._model,
                            element,
                            transformation,
                        )
                        geometry = build_swept_member_geometry(
                            section,
                            self._model.nodes[element.i].xyz,
                            self._model.nodes[element.j].xyz,
                            local_y,
                            local_z,
                            raw_vector(element.i),
                            raw_vector(element.j),
                            ndm=self._model.ndm,
                            scale=float(scale),
                            stations=max(3, int(stations)),
                            smooth=bool(smooth_curvature),
                        )
                    except (KeyError, TypeError, ValueError):
                        geometry = None

                    if geometry is not None:
                        surface = self._surface_mesh_from_swept_geometry(
                            geometry
                        )
                        if surface is not None:
                            surface.point_data["magnitude"] = np.asarray(
                                geometry.magnitudes,
                                dtype=float,
                            )
                            surface_meshes.append(surface)
                            rendered_surface = True

            if rendered_surface:
                continue

            # Centerline/Tube views must honor the same smooth-curvature
            # option as Actual Section.  Previously these representations
            # always connected displaced end nodes with one straight chord,
            # even when rotational DOFs were available and the UI explicitly
            # requested cubic beam interpolation.
            curved = None
            curved_magnitudes = None
            if smooth_curvature:
                try:
                    transformation = (
                        self._transformations.get(element.transf_tag)
                        if element.transf_tag is not None
                        else None
                    )
                    if transformation is not None:
                        _, local_y, local_z = element_local_axes(
                            self._model,
                            element,
                            transformation,
                        )
                    else:
                        start = np.asarray(
                            self._model.nodes[element.i].xyz,
                            dtype=float,
                        )
                        end = np.asarray(
                            self._model.nodes[element.j].xyz,
                            dtype=float,
                        )
                        axis = end - start
                        length = float(np.linalg.norm(axis))
                        if length <= 1.0e-12:
                            raise ValueError("Zero-length member.")
                        axis /= length
                        reference = (
                            np.asarray((0.0, 0.0, 1.0), dtype=float)
                            if abs(float(axis[2])) < 0.90
                            else np.asarray((0.0, 1.0, 0.0), dtype=float)
                        )
                        local_y = np.cross(axis, reference)
                        norm_y = float(np.linalg.norm(local_y))
                        if norm_y <= 1.0e-12:
                            reference = np.asarray(
                                (1.0, 0.0, 0.0),
                                dtype=float,
                            )
                            local_y = np.cross(axis, reference)
                            norm_y = float(np.linalg.norm(local_y))
                        local_y /= max(norm_y, 1.0e-12)
                        local_z = np.cross(axis, local_y)
                        local_z /= max(
                            float(np.linalg.norm(local_z)),
                            1.0e-12,
                        )

                    curved, _frame_y, _frame_z, curved_magnitudes = (
                        deformed_member_frames(
                            self._model.nodes[element.i].xyz,
                            self._model.nodes[element.j].xyz,
                            local_y,
                            local_z,
                            raw_vector(element.i),
                            raw_vector(element.j),
                            ndm=self._model.ndm,
                            scale=float(scale),
                            stations=max(3, int(stations)),
                            smooth=True,
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    curved = None
                    curved_magnitudes = None

            if curved is not None and curved_magnitudes is not None:
                index = len(points)
                count = int(curved.shape[0])
                points.extend(
                    tuple(float(value) for value in row)
                    for row in curved
                )
                magnitudes.extend(
                    float(value)
                    for value in curved_magnitudes
                )
                lines.extend(
                    (count, *range(index, index + count))
                )
                continue

            p1, m1 = displaced(element.i)
            p2, m2 = displaced(element.j)
            index = len(points)
            points.extend((p1, p2))
            magnitudes.extend((m1, m2))
            lines.extend((2, index, index + 1))

        if surface_meshes:
            surface_mesh = (
                surface_meshes[0]
                if len(surface_meshes) == 1
                else pv.merge(surface_meshes, merge_points=False)
            )
            surface_kwargs = {
                "name": "result-section-surface",
                "scalars": "magnitude",
                "cmap": "turbo",
                "smooth_shading": False,
                "show_edges": False,
                "pickable": False,
                "scalar_bar_args": {"title": label},
            }
            self.plotter.add_mesh(
                surface_mesh,
                **surface_kwargs,
                render=False,
            )
            entries.append((surface_mesh, surface_kwargs))

        if points:
            mesh = pv.PolyData(np.asarray(points, dtype=float))
            mesh.lines = np.asarray(lines, dtype=np.int64)
            mesh.point_data["magnitude"] = np.asarray(
                magnitudes,
                dtype=float,
            )
            mesh_kwargs = {
                "name": "result-overlay",
                "scalars": "magnitude",
                "cmap": "turbo",
                "line_width": 5 if representation != "centerline" else 3,
                "render_lines_as_tubes": representation != "centerline",
                "pickable": False,
                "show_scalar_bar": not bool(surface_meshes),
                "scalar_bar_args": {"title": label},
            }
            self.plotter.add_mesh(
                mesh,
                **mesh_kwargs,
                render=False,
            )
            entries.append((mesh, mesh_kwargs))

        result_node_tags = set(self._visible_node_tags())
        if node_tags:
            result_node_tags.intersection_update(node_tags)
        elif element_tags:
            scoped_nodes: set[int] = set()
            for tag in element_tags:
                element = self._model.elements.get(tag)
                if element is not None:
                    scoped_nodes.update(element.node_tags())
            result_node_tags.intersection_update(scoped_nodes)
        result_nodes = sorted(result_node_tags)
        node_points = []
        node_magnitudes = []
        for tag in result_nodes:
            point, magnitude = displaced(tag)
            node_points.append(point)
            node_magnitudes.append(magnitude)
        if not points and not surface_meshes and not node_points:
            return

        if node_points:
            node_mesh = pv.PolyData(np.asarray(node_points, dtype=float))
            node_mesh.point_data["magnitude"] = np.asarray(
                node_magnitudes,
                dtype=float,
            )
            node_kwargs = {
                "name": "result-nodes",
                "scalars": "magnitude",
                "cmap": "turbo",
                "render_points_as_spheres": True,
                "point_size": 7,
                "pickable": False,
                "show_scalar_bar": False,
            }
            self.plotter.add_mesh(
                node_mesh,
                **node_kwargs,
                render=False,
            )
            entries.append((node_mesh, node_kwargs))

        self._remember_result_view(view_cache_key, entries)
        self._result_overlay_active = True
        self.plotter.render()

    def show_shell_deformation_contour(
        self,
        result: dict[str, object],
        component: str,
        *,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        """Show averaged shell generalized strains/curvatures as contours."""
        if self._model is None:
            return

        component = str(component)
        component_index = {
            "Exx": 0,
            "Eyy": 1,
            "Gxy": 2,
            "Kxx": 3,
            "Kyy": 4,
            "Kxy": 5,
            "Gxz": 6,
            "Gyz": 7,
        }.get(component)
        if component_index is None:
            self.clear_result_overlay()
            return

        final = result.get("final", {}) if isinstance(result, dict) else {}
        shell_data = (
            final.get("shell_section_deformations", {})
            if isinstance(final, dict)
            else {}
        )
        if not isinstance(shell_data, dict) or not shell_data:
            self.clear_result_overlay()
            return

        visible = {
            int(tag)
            for tag in self._visible_element_tags()
            if (
                tag in self._model.elements
                and self._model.elements[tag].element_type
                in SHELL_ELEMENT_TYPES
            )
        }
        if element_tags:
            visible.intersection_update(
                int(tag) for tag in element_tags
            )

        tags: list[int] = []
        values: list[float] = []
        for tag in sorted(visible):
            payload = shell_data.get(str(tag), shell_data.get(tag))
            if not isinstance(payload, dict):
                continue
            average = payload.get("average", [])
            if (
                not isinstance(average, (list, tuple))
                or len(average) <= component_index
            ):
                continue
            try:
                value = float(average[component_index])
            except (TypeError, ValueError):
                continue
            if not np.isfinite(value):
                continue
            element = self._model.elements.get(tag)
            if (
                element is None
                or element.k is None
                or element.l is None
            ):
                continue
            tags.append(tag)
            values.append(value)

        if not tags:
            self.clear_result_overlay()
            return

        view_key = self._result_view_key(
            cache_key,
            "shell-deformation",
            component,
            self._result_scope_key(set(tags)),
        )
        if self._show_cached_result_view(view_key):
            return

        mesh = self._batched_shell_mesh(self._model, tags)
        if mesh is None or mesh.n_cells != len(values):
            self.clear_result_overlay()
            return

        scalar_name = "shell_deformation"
        mesh.cell_data[scalar_name] = np.asarray(values, dtype=float)

        max_abs = max(abs(value) for value in values)
        clim = (
            (-max_abs, max_abs)
            if max_abs > 1.0e-15
            else None
        )
        length_unit = str(self._units.get("length", "")).strip()
        unit_text = (
            f"1/{length_unit}"
            if component.startswith("K") and length_unit
            else "-"
        )
        title = (
            f"{component} [{unit_text}]"
            if unit_text and unit_text != "-"
            else component
        )

        self.clear_result_overlay(render=False)
        kwargs: dict[str, object] = {
            "name": "result-shell-deformation-contour",
            "scalars": scalar_name,
            "preference": "cell",
            "cmap": "coolwarm",
            "show_edges": True,
            "edge_color": "#263746",
            "line_width": 1,
            "opacity": 0.92,
            "pickable": False,
            "scalar_bar_args": {"title": title},
        }
        if clim is not None:
            kwargs["clim"] = clim

        self.plotter.add_mesh(
            mesh,
            **kwargs,
            render=False,
        )
        self._remember_result_view(
            view_key,
            [(mesh, kwargs)],
        )
        self._result_overlay_active = True
        self.plotter.render()

    def show_shell_force_contour(
        self,
        result: dict[str, object],
        component: str,
        *,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        """Show averaged shell section resultants as a surface contour."""
        if self._model is None:
            return

        component = str(component)
        component_index = {
            "Nxx": 0,
            "Nyy": 1,
            "Nxy": 2,
            "Mxx": 3,
            "Myy": 4,
            "Mxy": 5,
            "Qx": 6,
            "Qy": 7,
        }.get(component)
        if component_index is None:
            self.clear_result_overlay()
            return

        final = result.get("final", {}) if isinstance(result, dict) else {}
        shell_data = (
            final.get("shell_section_forces", {})
            if isinstance(final, dict)
            else {}
        )
        if not isinstance(shell_data, dict) or not shell_data:
            self.clear_result_overlay()
            return

        visible = {
            int(tag)
            for tag in self._visible_element_tags()
            if (
                tag in self._model.elements
                and self._model.elements[tag].element_type
                in SHELL_ELEMENT_TYPES
            )
        }
        if element_tags:
            visible.intersection_update(
                int(tag) for tag in element_tags
            )

        tags: list[int] = []
        values: list[float] = []
        for tag in sorted(visible):
            payload = shell_data.get(str(tag), shell_data.get(tag))
            if not isinstance(payload, dict):
                continue
            average = payload.get("average", [])
            if (
                not isinstance(average, (list, tuple))
                or len(average) <= component_index
            ):
                continue
            try:
                value = float(average[component_index])
            except (TypeError, ValueError):
                continue
            if not np.isfinite(value):
                continue
            element = self._model.elements.get(tag)
            if (
                element is None
                or element.k is None
                or element.l is None
            ):
                continue
            tags.append(tag)
            values.append(value)

        if not tags:
            self.clear_result_overlay()
            return

        view_key = self._result_view_key(
            cache_key,
            "shell-force",
            component,
            self._result_scope_key(set(tags)),
        )
        if self._show_cached_result_view(view_key):
            return

        mesh = self._batched_shell_mesh(self._model, tags)
        if mesh is None or mesh.n_cells != len(values):
            self.clear_result_overlay()
            return

        scalar_name = "shell_resultant"
        mesh.cell_data[scalar_name] = np.asarray(values, dtype=float)

        max_abs = max(abs(value) for value in values)
        clim = (
            (-max_abs, max_abs)
            if max_abs > 1.0e-15
            else None
        )
        force_unit = str(self._units.get("force", "")).strip()
        length_unit = str(self._units.get("length", "")).strip()
        if component.startswith("M"):
            unit_text = (
                force_unit
                if force_unit
                else ""
            )
        else:
            unit_text = (
                f"{force_unit}/{length_unit}"
                if force_unit and length_unit
                else force_unit
            )
        title = (
            f"{component} [{unit_text}]"
            if unit_text
            else component
        )

        self.clear_result_overlay(render=False)
        kwargs: dict[str, object] = {
            "name": "result-shell-contour",
            "scalars": scalar_name,
            "preference": "cell",
            "cmap": "coolwarm",
            "show_edges": True,
            "edge_color": "#263746",
            "line_width": 1,
            "opacity": 0.92,
            "pickable": False,
            "scalar_bar_args": {"title": title},
        }
        if clim is not None:
            kwargs["clim"] = clim

        self.plotter.add_mesh(
            mesh,
            **kwargs,
            render=False,
        )
        self._remember_result_view(
            view_key,
            [(mesh, kwargs)],
        )
        self._result_overlay_active = True
        self.plotter.render()

    def show_node_contour(
        self,
        result: dict[str, object],
        quantity: str,
        component: str,
        *,
        node_tags: set[int] | None = None,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        """Show a nodal displacement or reaction scalar on the frame mesh."""
        if self._model is None:
            return

        quantity = str(quantity)
        component = str(component)
        view_key = self._result_view_key(
            cache_key,
            "node-contour",
            quantity,
            component,
            self._result_scope_key(node_tags),
            self._result_scope_key(element_tags),
        )
        # Member-force views include sparse numeric labels. Rebuild this
        # lightweight overlay so labels stay in sync with the active result,
        # component, scope, and scale instead of restoring only cached meshes.
        final = result.get("final", {}) if isinstance(result, dict) else {}
        if not isinstance(final, dict):
            self.clear_result_overlay()
            return

        key = (
            "node_displacements"
            if quantity == "Displacement"
            else "node_reactions"
        )
        data = final.get(key, {})
        if not isinstance(data, dict) or not data:
            self.clear_result_overlay()
            return

        def value_for(tag: int) -> float | None:
            raw = data.get(str(tag), data.get(tag))
            if not isinstance(raw, (list, tuple)):
                return None
            try:
                return nodal_result_scalar(raw, component)
            except ValueError:
                return None

        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        scalars: list[float] = []

        visible_elements = set(self._visible_element_tags())
        if element_tags:
            visible_elements.intersection_update(element_tags)
        elif node_tags:
            visible_elements = {
                tag
                for tag in visible_elements
                if (
                    self._model.elements[tag].i in node_tags
                    and self._model.elements[tag].j in node_tags
                )
            }

        for tag in sorted(visible_elements):
            element = self._model.elements.get(tag)
            if element is None:
                continue
            value_i = value_for(element.i)
            value_j = value_for(element.j)
            if value_i is None or value_j is None:
                continue
            node_i = self._model.nodes.get(element.i)
            node_j = self._model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue
            index = len(points)
            points.extend((node_i.xyz, node_j.xyz))
            scalars.extend((float(value_i), float(value_j)))
            lines.extend((2, index, index + 1))

        node_points: list[tuple[float, float, float]] = []
        node_scalars: list[float] = []
        visible_nodes = set(self._visible_node_tags())
        if node_tags:
            visible_nodes.intersection_update(node_tags)
        elif element_tags:
            scoped_nodes: set[int] = set()
            for element_tag in element_tags:
                element = self._model.elements.get(element_tag)
                if element is not None:
                    scoped_nodes.update((element.i, element.j))
            visible_nodes.intersection_update(scoped_nodes)

        for tag in sorted(visible_nodes):
            node = self._model.nodes.get(tag)
            value = value_for(tag)
            if node is None or value is None:
                continue
            node_points.append(node.xyz)
            node_scalars.append(float(value))

        if not points and not node_points:
            self.clear_result_overlay()
            return

        all_values = scalars + node_scalars
        magnitude = component.startswith("|")
        cmap = "turbo" if magnitude else "coolwarm"
        clim = None
        if not magnitude and all_values:
            max_abs = max(abs(value) for value in all_values)
            if max_abs > 1.0e-15:
                clim = (-max_abs, max_abs)

        self.clear_result_overlay(render=False)
        entries: list[tuple[object, dict[str, object]]] = []

        scalar_name = "nodal_result"
        scalar_bar_args = {
            "title": f"{quantity} {component}",
        }

        if points:
            mesh = pv.PolyData(np.asarray(points, dtype=float))
            mesh.lines = np.asarray(lines, dtype=np.int64)
            mesh.point_data[scalar_name] = np.asarray(scalars, dtype=float)
            mesh_kwargs = {
                "name": "result-contour",
                "scalars": scalar_name,
                "cmap": cmap,
                "line_width": 7,
                "render_lines_as_tubes": True,
                "pickable": False,
                "scalar_bar_args": scalar_bar_args,
                "render": False,
            }
            if clim is not None:
                mesh_kwargs["clim"] = clim
            self.plotter.add_mesh(mesh, **mesh_kwargs)
            cache_kwargs = dict(mesh_kwargs)
            cache_kwargs.pop("render", None)
            entries.append((mesh, cache_kwargs))

        if node_points:
            node_mesh = pv.PolyData(np.asarray(node_points, dtype=float))
            node_mesh.point_data[scalar_name] = np.asarray(
                node_scalars,
                dtype=float,
            )
            node_kwargs = {
                "name": "result-contour-nodes",
                "scalars": scalar_name,
                "cmap": cmap,
                "render_points_as_spheres": True,
                "point_size": 9,
                "pickable": False,
                "show_scalar_bar": not bool(points),
                "scalar_bar_args": scalar_bar_args,
                "render": False,
            }
            if clim is not None:
                node_kwargs["clim"] = clim
            self.plotter.add_mesh(node_mesh, **node_kwargs)
            cache_kwargs = dict(node_kwargs)
            cache_kwargs.pop("render", None)
            entries.append((node_mesh, cache_kwargs))

        self._remember_result_view(view_key, entries)
        self._result_overlay_active = True
        self.plotter.render()

    def show_hinge_states(
        self,
        result: dict[str, object],
        *,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        """Show fiber-derived section state severity on nonlinear members."""
        if self._model is None:
            return

        view_key = self._result_view_key(
            cache_key,
            "hinge-state",
            self._result_scope_key(element_tags),
        )
        if self._show_cached_result_view(view_key):
            return

        final = result.get("final", {}) if isinstance(result, dict) else {}
        summary = (
            final.get("fiber_state_summary", {})
            if isinstance(final, dict)
            else {}
        )
        if not isinstance(summary, dict) or not summary:
            self.clear_result_overlay()
            return

        member_points: list[tuple[float, float, float]] = []
        member_lines: list[int] = []
        member_severity: list[float] = []
        state_points: list[np.ndarray] = []
        state_severity: list[float] = []

        visible_elements = set(self._visible_element_tags())
        if element_tags:
            visible_elements.intersection_update(element_tags)

        for tag in sorted(visible_elements):
            payload = summary.get(str(tag), summary.get(tag))
            element = self._model.elements.get(tag)
            if not isinstance(payload, dict) or element is None:
                continue
            node_i = self._model.nodes.get(element.i)
            node_j = self._model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue

            try:
                severity = int(payload.get("severity", -1))
            except (TypeError, ValueError):
                severity = -1
            if severity < 0:
                continue

            p_i = np.asarray(node_i.xyz, dtype=float)
            p_j = np.asarray(node_j.xyz, dtype=float)
            member_vector = p_j - p_i
            length = float(np.linalg.norm(member_vector))
            if length <= 1.0e-15:
                continue

            index = len(member_points)
            member_points.extend((tuple(p_i), tuple(p_j)))
            member_lines.extend((2, index, index + 1))
            member_severity.append(float(severity))

            sections = payload.get("sections", [])
            if not isinstance(sections, list):
                continue
            for section in sections:
                if not isinstance(section, dict):
                    continue
                try:
                    section_severity = int(section.get("severity", -1))
                    location = float(section.get("location", 0.0))
                except (TypeError, ValueError):
                    continue
                if section_severity < 1:
                    continue
                ratio = min(max(location / length, 0.0), 1.0)
                state_points.append(p_i + ratio * member_vector)
                state_severity.append(float(section_severity))

        if not member_points:
            self.clear_result_overlay()
            return

        self.clear_result_overlay(render=False)
        entries: list[tuple[object, dict[str, object]]] = []
        state_cmap = [
            "#8fa2b5",
            "#e7b34c",
            "#f07c36",
            "#c0392b",
        ]

        member_mesh = pv.PolyData(np.asarray(member_points, dtype=float))
        member_mesh.lines = np.asarray(member_lines, dtype=np.int64)
        member_mesh.cell_data["state_severity"] = np.asarray(
            member_severity,
            dtype=float,
        )
        member_kwargs = {
            "name": "result-hinge-members",
            "scalars": "state_severity",
            "preference": "cell",
            "cmap": state_cmap,
            "clim": (-0.5, 3.5),
            "line_width": 9,
            "render_lines_as_tubes": True,
            "pickable": False,
            "scalar_bar_args": {
                "title": (
                    "Fiber state: 0 Elastic · 1 Nonlinear · "
                    "2 Yielding · 3 Plastic/Crushing"
                )
            },
        }
        self.plotter.add_mesh(
            member_mesh,
            **member_kwargs,
            render=False,
        )
        entries.append((member_mesh, member_kwargs))

        if state_points:
            point_mesh = pv.PolyData(
                np.asarray(state_points, dtype=float)
            )
            point_mesh.point_data["state_severity"] = np.asarray(
                state_severity,
                dtype=float,
            )
            point_kwargs = {
                "name": "result-hinge-points",
                "scalars": "state_severity",
                "cmap": state_cmap,
                "clim": (-0.5, 3.5),
                "render_points_as_spheres": True,
                "point_size": 13,
                "pickable": False,
                "show_scalar_bar": False,
            }
            self.plotter.add_mesh(
                point_mesh,
                **point_kwargs,
                render=False,
            )
            entries.append((point_mesh, point_kwargs))

        self._remember_result_view(view_key, entries)
        self._result_overlay_active = True
        self.plotter.render()

    def show_member_force_diagram(
        self,
        result: dict[str, object],
        transformations: dict[int, object],
        component: str,
        *,
        scale: float = 1.0,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        if self._model is None or not self._model.elements:
            return

        component = str(component)
        view_key = self._result_view_key(
            cache_key,
            "member-force",
            component,
            float(scale),
            self._result_scope_key(element_tags),
        )
        if self._show_cached_result_view(view_key):
            return

        final = result.get("final", {}) if isinstance(result, dict) else {}
        local_forces = (
            final.get("element_local_forces", {})
            if isinstance(final, dict)
            else {}
        )
        diagrams = (
            final.get("member_force_diagrams", {})
            if isinstance(final, dict)
            else {}
        )
        if not isinstance(local_forces, dict):
            local_forces = {}
        if not isinstance(diagrams, dict):
            diagrams = {}

        available: dict[int, tuple[list[float], list[float]]] = {}
        visible_elements = set(self._visible_element_tags())
        if element_tags:
            visible_elements.intersection_update(element_tags)
        for tag in visible_elements:
            by_component = diagrams.get(str(tag), diagrams.get(tag, {}))
            diagram = (
                by_component.get(component, {})
                if isinstance(by_component, dict)
                else {}
            )
            if isinstance(diagram, dict):
                xs = diagram.get("x", [])
                values = diagram.get("values", [])
                if (
                    isinstance(xs, (list, tuple))
                    and isinstance(values, (list, tuple))
                    and len(xs) == len(values)
                    and len(xs) >= 2
                ):
                    available[tag] = (
                        [float(value) for value in xs],
                        [float(value) for value in values],
                    )
                    continue

            raw = local_forces.get(str(tag), local_forces.get(tag))
            if not isinstance(raw, (list, tuple)):
                continue
            ends = component_end_resultants(raw, component)
            element = self._model.elements.get(tag)
            if ends is None or element is None:
                continue
            p_i = np.asarray(self._model.nodes[element.i].xyz, dtype=float)
            p_j = np.asarray(self._model.nodes[element.j].xyz, dtype=float)
            length = float(np.linalg.norm(p_j - p_i))
            if length <= 1.0e-15:
                continue
            available[tag] = (
                [0.0, length],
                [float(ends[0]), float(ends[1])],
            )

        if not available:
            self.clear_result_overlay()
            return

        max_abs = max(
            (
                abs(value)
                for _xs, values in available.values()
                for value in values
            ),
            default=0.0,
        )
        if max_abs <= 1.0e-15:
            max_abs = 1.0

        low, high = self._model.bounds()
        model_span = max(
            high[0] - low[0],
            high[1] - low[1],
            high[2] - low[2],
            1.0,
        )
        force_scale = (
            max(float(scale), 0.0)
            * 0.14
            * model_span
            / max_abs
        )

        diagram_points: list[np.ndarray] = []
        diagram_lines: list[int] = []
        diagram_values: list[float] = []
        connector_points: list[np.ndarray] = []
        connector_lines: list[int] = []
        label_candidates: list[tuple[float, np.ndarray, float]] = []

        use_local_y = component in {"N", "Vy", "T", "Mz"}

        for tag in sorted(available):
            element = self._model.elements.get(tag)
            if element is None:
                continue

            p_i = np.asarray(
                self._model.nodes[element.i].xyz,
                dtype=float,
            )
            p_j = np.asarray(
                self._model.nodes[element.j].xyz,
                dtype=float,
            )
            member_vector = p_j - p_i
            length = float(np.linalg.norm(member_vector))
            if length <= 1.0e-15:
                continue

            if element.element_type == "truss":
                if component != "N":
                    continue
                member_axis = member_vector / length
                axis = None
                for reference in (
                    np.asarray((0.0, 0.0, 1.0)),
                    np.asarray((0.0, 1.0, 0.0)),
                    np.asarray((1.0, 0.0, 0.0)),
                ):
                    candidate = np.cross(member_axis, reference)
                    norm = float(np.linalg.norm(candidate))
                    if norm > 1.0e-9:
                        axis = candidate / norm
                        break
                if axis is None:
                    continue
            else:
                if element.transf_tag is None:
                    continue
                transformation = transformations.get(element.transf_tag)
                if transformation is None:
                    continue
                try:
                    _, local_y, local_z = element_local_axes(
                        self._model,
                        element,
                        transformation,
                    )
                except ValueError:
                    continue
                axis = np.asarray(
                    local_y if use_local_y else local_z,
                    dtype=float,
                )

            xs, values = available[tag]
            first_index = len(diagram_points)
            sampled_base: list[np.ndarray] = []
            sampled_diagram: list[np.ndarray] = []

            for x, value in zip(xs, values):
                ratio = min(max(float(x) / length, 0.0), 1.0)
                base = p_i + ratio * member_vector
                point = base + axis * float(value) * force_scale
                sampled_base.append(base)
                sampled_diagram.append(point)
                diagram_points.append(point)
                diagram_values.append(float(value))

            sample_count = len(sampled_diagram)
            if sample_count < 2:
                continue
            diagram_lines.extend(
                [sample_count]
                + list(
                    range(
                        first_index,
                        first_index + sample_count,
                    )
                )
            )

            # One sparse numeric annotation per member. For a constant
            # Truss axial-force diagram, use the visual midpoint; otherwise
            # label the sampled point with the largest absolute resultant.
            numeric_values = [float(value) for value in values]
            if numeric_values:
                spread = max(numeric_values) - min(numeric_values)
                tolerance = max(
                    max(abs(value) for value in numeric_values) * 1.0e-9,
                    1.0e-12,
                )
                if abs(spread) <= tolerance:
                    if sample_count == 2:
                        label_point = (
                            sampled_diagram[0] + sampled_diagram[1]
                        ) * 0.5
                        label_value = 0.5 * (
                            numeric_values[0] + numeric_values[-1]
                        )
                    else:
                        label_index = sample_count // 2
                        label_point = sampled_diagram[label_index]
                        label_value = numeric_values[label_index]
                else:
                    label_index = max(
                        range(sample_count),
                        key=lambda index: abs(numeric_values[index]),
                    )
                    label_point = sampled_diagram[label_index]
                    label_value = numeric_values[label_index]
                # Push the annotation a little beyond the force diagram so
                # it does not sit directly on top of a member/diagram line.
                label_point = (
                    np.asarray(label_point, dtype=float)
                    + axis * (0.018 * model_span)
                )
                label_candidates.append(
                    (
                        abs(float(label_value)),
                        label_point,
                        float(label_value),
                    )
                )

            connector_indices = {
                0,
                sample_count // 2,
                sample_count - 1,
            }
            for index in sorted(connector_indices):
                base_index = len(connector_points)
                connector_points.extend(
                    (
                        sampled_base[index],
                        sampled_diagram[index],
                    )
                )
                connector_lines.extend(
                    (2, base_index, base_index + 1)
                )

        if not diagram_points:
            self.clear_result_overlay()
            return

        self.clear_result_overlay(render=False)
        entries: list[tuple[object, dict[str, object]]] = []

        mesh = pv.PolyData(
            np.asarray(diagram_points, dtype=float)
        )
        mesh.lines = np.asarray(diagram_lines, dtype=np.int64)
        mesh.point_data["member_force"] = np.asarray(
            diagram_values,
            dtype=float,
        )
        mesh_kwargs = {
            "name": "result-force-diagram",
            "scalars": "member_force",
            "cmap": "coolwarm",
            "line_width": 5,
            "render_lines_as_tubes": True,
            "pickable": False,
            "scalar_bar_args": {
                "title": f"{component} · local member resultant"
            },
        }
        self.plotter.add_mesh(
            mesh,
            **mesh_kwargs,
            render=False,
        )
        entries.append((mesh, mesh_kwargs))

        if connector_points:
            connectors = pv.PolyData(
                np.asarray(connector_points, dtype=float)
            )
            connectors.lines = np.asarray(
                connector_lines,
                dtype=np.int64,
            )
            connector_kwargs = {
                "name": "result-force-connectors",
                "color": "#6f7f8f",
                "line_width": 1,
                "opacity": 0.6,
                "pickable": False,
                "show_scalar_bar": False,
            }
            self.plotter.add_mesh(
                connectors,
                **connector_kwargs,
                render=False,
            )
            entries.append((connectors, connector_kwargs))

        if label_candidates:
            # Keep the strongest labels if the model is dense. This preserves
            # readability while still giving direct numerical values on the
            # force diagram itself.
            selected_labels = sorted(
                label_candidates,
                key=lambda item: item[0],
                reverse=True,
            )[:12]
            selected_labels.sort(key=lambda item: tuple(item[1]))

            force_unit = str(self._units.get("force", "")).strip()
            length_unit = str(self._units.get("length", "")).strip()
            if component in {"T", "My", "Mz"}:
                unit_text = (
                    f" {force_unit}·{length_unit}"
                    if force_unit and length_unit
                    else ""
                )
            else:
                unit_text = f" {force_unit}" if force_unit else ""

            self._add_annotation_labels(
                [item[1] for item in selected_labels],
                [
                    f"{item[2]:.4g}{unit_text}"
                    for item in selected_labels
                ],
                name="result-force-labels",
                text_color="#182533",
                font_size=13,
                always_visible=True,
            )

        self._remember_result_view(view_key, entries)
        self._result_overlay_active = True
        self.plotter.render()

    def show_motion_frame(
        self,
        vectors: dict[str, object],
        *,
        scale: float = 1.0,
        auto_scale: bool = True,
        reference_magnitude: float = 0.0,
    ) -> None:
        """Update a persistent deformation overlay for animation playback."""
        if self._model is None or not self._model.nodes:
            return

        visible_elements = tuple(sorted(self._visible_element_tags()))
        visible_nodes = tuple(sorted(self._visible_node_tags()))
        topology_key = (visible_elements, visible_nodes)

        if self._motion_topology_key != topology_key:
            self.clear_result_overlay(render=False)

            element_points: list[tuple[float, float, float]] = []
            element_lines: list[int] = []
            element_node_tags: list[int] = []
            for element_tag in visible_elements:
                element = self._model.elements.get(element_tag)
                if element is None:
                    continue
                if (
                    element.i not in self._model.nodes
                    or element.j not in self._model.nodes
                ):
                    continue
                index = len(element_points)
                element_points.extend(
                    (
                        self._model.nodes[element.i].xyz,
                        self._model.nodes[element.j].xyz,
                    )
                )
                element_node_tags.extend((element.i, element.j))
                element_lines.extend((2, index, index + 1))

            if element_points:
                mesh = pv.PolyData(
                    np.asarray(element_points, dtype=float)
                )
                mesh.lines = np.asarray(element_lines, dtype=np.int64)
                self.plotter.add_mesh(
                    mesh,
                    name="motion-overlay",
                    color="#d94848",
                    line_width=5,
                    render_lines_as_tubes=True,
                    pickable=False,
                    render=False,
                )
                self._motion_element_mesh = mesh
                self._motion_element_node_tags = element_node_tags

            node_points = [
                self._model.nodes[tag].xyz
                for tag in visible_nodes
                if tag in self._model.nodes
            ]
            node_tags = [
                tag for tag in visible_nodes if tag in self._model.nodes
            ]
            if node_points:
                node_mesh = pv.PolyData(
                    np.asarray(node_points, dtype=float)
                )
                self.plotter.add_mesh(
                    node_mesh,
                    name="motion-nodes",
                    color="#d94848",
                    render_points_as_spheres=True,
                    point_size=7,
                    pickable=False,
                    render=False,
                )
                self._motion_node_mesh = node_mesh
                self._motion_node_tags = node_tags

            self._motion_topology_key = topology_key

        effective_scale = float(scale)
        reference = abs(float(reference_magnitude))
        if auto_scale and reference > 1.0e-15:
            low, high = self._model.bounds()
            span = max(
                high[0] - low[0],
                high[1] - low[1],
                high[2] - low[2],
                1.0,
            )
            effective_scale *= 0.12 * span / reference

        def displaced(tag: int) -> tuple[float, float, float]:
            node = self._model.nodes[tag]
            raw = vectors.get(
                str(tag),
                vectors.get(tag, (0.0, 0.0, 0.0)),
            )
            values = list(raw) if raw is not None else []
            while len(values) < 3:
                values.append(0.0)
            return (
                node.xyz[0] + effective_scale * float(values[0]),
                node.xyz[1] + effective_scale * float(values[1]),
                node.xyz[2] + effective_scale * float(values[2]),
            )

        if self._motion_element_mesh is not None:
            self._motion_element_mesh.points = np.asarray(
                [
                    displaced(tag)
                    for tag in self._motion_element_node_tags
                ],
                dtype=float,
            )
        if self._motion_node_mesh is not None:
            self._motion_node_mesh.points = np.asarray(
                [displaced(tag) for tag in self._motion_node_tags],
                dtype=float,
            )

        self._result_overlay_active = True
        self._active_result_view_key = None
        self.plotter.render()

    def show_deformed_shape(
        self,
        result: dict[str, object],
        *,
        scale: float = 1.0,
        display_mode: str = "deformed_only",
        representation: str = "actual_section",
        smooth_curvature: bool = True,
        node_tags: set[int] | None = None,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        display_mode = self._normalized_deformation_display_mode(
            display_mode
        )
        if display_mode == "undeformed_only":
            self.clear_result_overlay(render=False)
            self.set_undeformed_model_visible(True, render=True)
            return

        final = result.get("final", {}) if isinstance(result, dict) else {}
        vectors = (
            final.get("node_displacements", {})
            if isinstance(final, dict)
            else {}
        )
        if not isinstance(vectors, dict) or not vectors:
            self.clear_result_overlay()
            return
        view_key = self._result_view_key(
            cache_key,
            "deformed-shape",
            float(scale),
            self._normalized_deformation_representation(representation),
            bool(smooth_curvature),
            self._result_scope_key(node_tags),
            self._result_scope_key(element_tags),
        )
        self._show_vector_overlay(
            vectors,
            scale=float(scale),
            label="Displacement magnitude",
            representation=representation,
            smooth_curvature=bool(smooth_curvature),
            node_tags=node_tags,
            element_tags=element_tags,
            view_cache_key=view_key,
        )
        self.set_undeformed_model_visible(
            display_mode == "both",
            render=True,
        )

    def show_mode_shape(
        self,
        result: dict[str, object],
        mode: int,
        *,
        scale: float = 1.0,
        display_mode: str = "deformed_only",
        representation: str = "actual_section",
        smooth_curvature: bool = True,
        node_tags: set[int] | None = None,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        display_mode = self._normalized_deformation_display_mode(
            display_mode
        )
        if display_mode == "undeformed_only":
            self.clear_result_overlay(render=False)
            self.set_undeformed_model_visible(True, render=True)
            return

        view_key = self._result_view_key(
            cache_key,
            "mode-shape",
            int(mode),
            float(scale),
            self._normalized_deformation_representation(representation),
            bool(smooth_curvature),
            self._result_scope_key(node_tags),
            self._result_scope_key(element_tags),
        )
        if self._show_cached_result_view(view_key):
            return

        modes = result.get("modes", {}) if isinstance(result, dict) else {}
        mode_data = modes.get(str(int(mode)), {}) if isinstance(modes, dict) else {}
        vectors = (
            mode_data.get("vectors", {})
            if isinstance(mode_data, dict)
            else {}
        )
        if not isinstance(vectors, dict) or not vectors:
            self.clear_result_overlay()
            return

        max_component = max(
            (
                abs(float(value))
                for vector in vectors.values()
                for value in list(vector)[:3]
            ),
            default=0.0,
        )
        auto_scale = float(scale)
        if max_component > 1.0e-15 and self._model is not None:
            low, high = self._model.bounds()
            span = max(
                high[0] - low[0],
                high[1] - low[1],
                high[2] - low[2],
                1.0,
            )
            auto_scale *= 0.12 * span / max_component

        self._show_vector_overlay(
            vectors,
            scale=auto_scale,
            label=f"Mode {int(mode)} amplitude",
            representation=representation,
            smooth_curvature=bool(smooth_curvature),
            node_tags=node_tags,
            element_tags=element_tags,
            view_cache_key=view_key,
        )
        self.set_undeformed_model_visible(
            display_mode == "both",
            render=True,
        )

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
                    self._model.nodes[node_tag].xyz
                    for node_tag in element.node_tags()
                    if node_tag in self._model.nodes
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

    def set_view(self, view: str, *, render: bool = True) -> None:
        self._current_view = view
        function = {
            "iso": self.plotter.view_isometric,
            "xy": self.plotter.view_xy,
            "xz": self.plotter.view_xz,
            "yz": self.plotter.view_yz,
        }[view]
        function()
        if render:
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
