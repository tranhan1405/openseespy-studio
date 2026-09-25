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
    QMenu,
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
from ..crack_results import (
    crack_severity,
    mefi_crack_panel_states,
    mefi_crack_summary,
    principal_tensile_strain,
)
from ..deformed_geometry import (
    build_swept_member_geometry,
    deformed_member_frames,
    section_axis_strength_labels,
)
from ..model import (
    EMBEDDED_ELEMENT_TYPES,
    QUAD_ELEMENT_TYPES,
    SHELL_ELEMENT_TYPES,
    TRUSS_ELEMENT_TYPES,
    StructuralModel,
    classify_fixity,
    shell_surface_geometry,
)
from ..postprocess import (
    component_end_resultants,
    nodal_result_scalar,
    shell_principal_strains,
    shell_surface_strains,
)
from ..shell_quality import shell_element_quality_from_model
from ..surface_mesher import surface_mesh_preview_segments
from ..project import (
    ConnectionData,
    ConstraintData,
    ElementLoadData,
    LineGeometryData,
    MaterialData,
    NodalLoadData,
    PointGeometryData,
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
    geometry_sketch_moved = Signal(object)
    geometry_sketch_finished = Signal()
    measure_moved = Signal(object)
    view_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        if QtInteractor is None:
            raise RuntimeError(
                "PyVista/pyvistaqt are required. Run: pip install -r requirements.txt"
            )

        self.setObjectName("ViewportRoot")
        self._model: StructuralModel | None = None
        self._connections: dict[int, ConnectionData] = {}
        self._constraints: dict[int, ConstraintData] = {}
        self._nodal_loads: dict[int, NodalLoadData] = {}
        self._prescribed_displacements: dict[
            int,
            PrescribedDisplacementData,
        ] = {}
        self._element_loads: dict[int, ElementLoadData] = {}
        self._transformations: dict[int, TransformationData] = {}
        self._sections: dict[int, SectionData] = {}
        self._materials: dict[int, MaterialData] = {}
        self._points: dict[int, PointGeometryData] = {}
        self._lines: dict[int, LineGeometryData] = {}
        self._surfaces: dict[int, SurfaceGeometryData] = {}
        self._display_domain = "fe"
        self._background_preset = "ANSYS Gradient"
        self._background_bottom = "#f2f5f8"
        self._background_top = "#e1e8ef"
        self._geometry_mesh_overlay_visible = False
        self._surface_orientation_tags: set[int] = set()
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
            "masses": False,
            "section_axes": False,
            "load_values": True,
            "reinforcement": True,
        }
        self._model_representation = "tube"
        self._model_color_mode = "uniform"
        self._selection_filter = "all"
        self._selected_nodes: set[int] = set()
        self._selected_elements: set[int] = set()
        self._selected_geometry_surfaces: set[int] = set()
        self._hover_ref: tuple[str, int] | None = None

        self._hidden_nodes: set[int] = set()
        self._hidden_elements: set[int] = set()
        self._isolate_active = False
        self._isolate_nodes: set[int] = set()
        self._isolate_elements: set[int] = set()

        self._node_actor = None
        self._node_tags: list[int] = []
        self._geometry_point_actor = None
        self._geometry_point_tags: list[int] = []
        self._geometry_line_actor = None
        self._geometry_line_mesh = None
        self._geometry_line_tags: list[int] = []
        self._selected_geometry_lines: set[int] = set()
        self._geometry_surface_actor = None
        self._geometry_surface_mesh = None
        self._geometry_surface_tags: list[int] = []
        self._line_mesh_preview: tuple[
            int,
            list[tuple[float, float, float]],
            str,
        ] | None = None
        self._line_intersection_preview: list[
            tuple[
                tuple[float, float, float],
                str,
                tuple[int, int],
            ]
        ] = []
        self._surface_mesh_preview_tags: set[int] = set()
        self._surface_quality_tags: set[int] = set()
        self._surface_quality_metric: str | None = None
        self._surface_pressure_preview_tags: set[int] = set()
        self._surface_pressure_preview_value: float | None = None
        self._surface_edge_preview_refs: set[tuple[int, int]] = set()
        self._surface_edge_load_preview: tuple[
            int,
            int,
            tuple[float, float, float, float, float, float],
        ] | None = None
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
        self._geometry_sketch_plane = "xy"
        self._geometry_sketch_plane_offset = 0.0
        self._geometry_sketch_plane_name = "Global XY"
        self._geometry_sketch_origin = np.asarray((0.0, 0.0, 0.0), dtype=float)
        self._geometry_sketch_u_axis = np.asarray((1.0, 0.0, 0.0), dtype=float)
        self._geometry_sketch_v_axis = np.asarray((0.0, 1.0, 0.0), dtype=float)
        self._geometry_sketch_normal = np.asarray((0.0, 0.0, 1.0), dtype=float)
        self._geometry_sketch_preview: dict[str, object] | None = None
        self._geometry_sketch_grid_visible = True
        self._origin_axes_visible = True
        self._last_geometry_sketch_qt_pos: tuple[float, float] | None = None
        self._last_measure_qt_pos: tuple[float, float] | None = None
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
        self._motion_extrema_visible = False
        self._motion_extrema_snapshot: tuple[
            tuple[int, float, tuple[float, float, float]],
            tuple[int, float, tuple[float, float, float]],
        ] | None = None
        self._node_probe_tag: int | None = None
        self._node_probe_label = ""

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
            button.clicked.connect(
                lambda checked=False, v=view: self.view_requested.emit(v)
            )
            self.view_group.addButton(button)
            views.addWidget(button)
            if view == "iso":
                button.setChecked(True)
        header.addLayout(views)

        header.addStretch(1)

        tools = QHBoxLayout()
        tools.setSpacing(3)
        for icon, tip, callback in (
            ("iso", "Orientation cube", lambda: self.view_requested.emit("iso")),
            ("box", "Fit selection", self.fit_view),
            ("display", "Display options", self._show_display_options_menu),
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
        if tool not in {"select", "box", "geometry_sketch", "measure"}:
            raise ValueError(f"Unknown interaction tool: {tool}")
        self._interaction_tool = tool
        self._box_origin = None
        self._left_press_pos = None
        self._right_press_pos = None
        self._nav_mode = None
        self._nav_last_pos = None
        self._last_geometry_sketch_qt_pos = None
        self._last_measure_qt_pos = None
        self._pending_hover_vtk_pos = None
        self._rubber_band.hide() if self._rubber_band is not None else None

    def interaction_tool(self) -> str:
        return self._interaction_tool

    def display_domain(self) -> str:
        return str(self._display_domain)

    @staticmethod
    def _normalized_sketch_axis(value, label: str) -> np.ndarray:
        axis = np.asarray(tuple(float(item) for item in value), dtype=float)
        if axis.shape != (3,) or not np.all(np.isfinite(axis)):
            raise ValueError(f"{label} must be a finite XYZ vector.")
        length = float(np.linalg.norm(axis))
        if length <= 1.0e-12:
            raise ValueError(f"{label} cannot be zero.")
        return axis / length

    def set_geometry_sketch_frame(
        self,
        origin,
        u_axis,
        v_axis,
        *,
        name: str = "Sketch Plane",
        key: str = "custom",
    ) -> None:
        origin_array = np.asarray(
            tuple(float(item) for item in origin),
            dtype=float,
        )
        if origin_array.shape != (3,) or not np.all(np.isfinite(origin_array)):
            raise ValueError("Sketch Plane origin must be finite XYZ.")
        u = self._normalized_sketch_axis(u_axis, "Sketch Plane U axis")
        raw_v = self._normalized_sketch_axis(v_axis, "Sketch Plane V axis")
        raw_v = raw_v - float(np.dot(raw_v, u)) * u
        v_length = float(np.linalg.norm(raw_v))
        if v_length <= 1.0e-12:
            raise ValueError("Sketch Plane U and V axes cannot be parallel.")
        v = raw_v / v_length
        normal = np.cross(u, v)
        normal /= max(float(np.linalg.norm(normal)), 1.0e-12)

        self._geometry_sketch_plane = str(key).strip().lower() or "custom"
        self._geometry_sketch_plane_name = str(name).strip() or "Sketch Plane"
        self._geometry_sketch_origin = origin_array
        self._geometry_sketch_u_axis = u
        self._geometry_sketch_v_axis = v
        self._geometry_sketch_normal = normal
        self._geometry_sketch_plane_offset = float(
            np.dot(origin_array, normal)
        )
        if self._geometry_sketch_grid_visible:
            self._remove_overlay("geometry-sketch-grid")
            if self._display_domain == "geometry":
                self._render_geometry_sketch_grid()
                self.plotter.render()

    def set_geometry_sketch_plane(
        self,
        plane: str,
        offset: float = 0.0,
    ) -> None:
        normalized = str(plane).strip().lower()
        if normalized not in {"xy", "xz", "yz"}:
            raise ValueError("Geometry sketch plane must be XY, XZ, or YZ.")
        numeric_offset = float(offset)
        if not math.isfinite(numeric_offset):
            raise ValueError("Geometry sketch plane offset must be finite.")
        frames = {
            "xy": (
                (0.0, 0.0, numeric_offset),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                "Global XY",
            ),
            "xz": (
                (0.0, numeric_offset, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0),
                "Global XZ",
            ),
            "yz": (
                (numeric_offset, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                "Global YZ",
            ),
        }
        origin, u_axis, v_axis, name = frames[normalized]
        self.set_geometry_sketch_frame(
            origin,
            u_axis,
            v_axis,
            name=name,
            key=normalized,
        )
        self._geometry_sketch_plane_offset = numeric_offset

    def geometry_sketch_plane(self) -> tuple[str, float]:
        return (
            self._geometry_sketch_plane,
            float(self._geometry_sketch_plane_offset),
        )

    def geometry_sketch_frame(self) -> dict[str, object]:
        return {
            "key": self._geometry_sketch_plane,
            "name": self._geometry_sketch_plane_name,
            "origin": tuple(float(value) for value in self._geometry_sketch_origin),
            "u_axis": tuple(float(value) for value in self._geometry_sketch_u_axis),
            "v_axis": tuple(float(value) for value in self._geometry_sketch_v_axis),
            "normal": tuple(float(value) for value in self._geometry_sketch_normal),
        }

    def geometry_world_to_local(self, xyz) -> tuple[float, float]:
        point = np.asarray(tuple(float(value) for value in xyz), dtype=float)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            raise ValueError("Geometry point must be finite XYZ.")
        delta = point - self._geometry_sketch_origin
        return (
            float(np.dot(delta, self._geometry_sketch_u_axis)),
            float(np.dot(delta, self._geometry_sketch_v_axis)),
        )

    def geometry_local_to_world(
        self,
        u: float,
        v: float,
    ) -> tuple[float, float, float]:
        point = (
            self._geometry_sketch_origin
            + float(u) * self._geometry_sketch_u_axis
            + float(v) * self._geometry_sketch_v_axis
        )
        return tuple(float(value) for value in point)

    def set_geometry_sketch_grid_visible(self, visible: bool) -> None:
        self._geometry_sketch_grid_visible = bool(visible)
        self._remove_overlay("geometry-sketch-grid")
        if (
            self._geometry_sketch_grid_visible
            and self._display_domain == "geometry"
        ):
            self._render_geometry_sketch_grid()
        self.plotter.render()

    def set_geometry_sketch_plane_offset_from_point(self, xyz) -> None:
        raw_point = tuple(float(value) for value in xyz)
        if (
            len(raw_point) != 3
            or not all(math.isfinite(value) for value in raw_point)
        ):
            raise ValueError("Sketch plane point requires finite X, Y, Z.")
        point = np.asarray(raw_point, dtype=float)
        signed = float(
            np.dot(
                point - self._geometry_sketch_origin,
                self._geometry_sketch_normal,
            )
        )
        self._geometry_sketch_origin = (
            self._geometry_sketch_origin
            + signed * self._geometry_sketch_normal
        )
        self._geometry_sketch_plane_offset = float(
            np.dot(
                self._geometry_sketch_origin,
                self._geometry_sketch_normal,
            )
        )
        if self._geometry_sketch_grid_visible:
            self._remove_overlay("geometry-sketch-grid")
            if self._display_domain == "geometry":
                self._render_geometry_sketch_grid()
                self.plotter.render()

    def geometry_world_to_screen(
        self,
        xyz,
    ) -> tuple[float, float]:
        return self._world_to_qt(xyz)

    def geometry_workplane_point(
        self,
        x: int,
        y: int,
    ) -> tuple[float, float, float] | None:
        renderer = self.plotter.renderer
        origin = getattr(self, "_geometry_sketch_origin", None)
        normal = getattr(self, "_geometry_sketch_normal", None)
        if origin is None or normal is None:
            plane = getattr(self, "_geometry_sketch_plane", "xy")
            offset = float(
                getattr(self, "_geometry_sketch_plane_offset", 0.0)
            )
            legacy_frames = {
                "xy": ((0.0, 0.0, offset), (0.0, 0.0, 1.0)),
                "xz": ((0.0, offset, 0.0), (0.0, -1.0, 0.0)),
                "yz": ((offset, 0.0, 0.0), (1.0, 0.0, 0.0)),
            }
            legacy_origin, legacy_normal = legacy_frames.get(
                str(plane).strip().lower(),
                legacy_frames["xy"],
            )
            origin = np.asarray(legacy_origin, dtype=float)
            normal = np.asarray(legacy_normal, dtype=float)
        else:
            origin = np.asarray(origin, dtype=float)
            normal = np.asarray(normal, dtype=float)

        def normalized_world(value) -> np.ndarray | None:
            if value is None or len(value) < 4:
                return None
            w = float(value[3])
            if not math.isfinite(w) or abs(w) <= 1.0e-15:
                return None
            point = np.asarray(
                [
                    float(value[0]) / w,
                    float(value[1]) / w,
                    float(value[2]) / w,
                ],
                dtype=float,
            )
            if not np.all(np.isfinite(point)):
                return None
            return point

        # When looking normal to the active workplane, all plane points share
        # one display depth. This is the most stable CAD-like unprojection.
        current_view = getattr(self, "_current_view", "iso")
        active_plane = getattr(self, "_geometry_sketch_plane", "xy")
        if current_view in {active_plane, "sketch"}:
            renderer.SetWorldPoint(
                float(origin[0]),
                float(origin[1]),
                float(origin[2]),
                1.0,
            )
            renderer.WorldToDisplay()
            display = renderer.GetDisplayPoint()
            if display is not None and len(display) >= 3:
                depth = float(display[2])
                if math.isfinite(depth):
                    renderer.SetDisplayPoint(float(x), float(y), depth)
                    renderer.DisplayToWorld()
                    point = normalized_world(renderer.GetWorldPoint())
                    if point is not None:
                        distance = float(np.dot(point - origin, normal))
                        point = point - distance * normal
                        return tuple(float(value) for value in point)

        def display_world(depth: float) -> np.ndarray | None:
            renderer.SetDisplayPoint(float(x), float(y), float(depth))
            renderer.DisplayToWorld()
            return normalized_world(renderer.GetWorldPoint())

        near = display_world(0.0)
        far = display_world(1.0)
        if near is None or far is None:
            return None
        direction = far - near
        denominator = float(np.dot(direction, normal))
        if not math.isfinite(denominator) or abs(denominator) <= 1.0e-14:
            return None
        t = float(np.dot(origin - near, normal)) / denominator
        if not math.isfinite(t) or t < -1.0e-6:
            return None
        point = near + t * direction
        if not np.all(np.isfinite(point)):
            return None
        distance = float(np.dot(point - origin, normal))
        point = point - distance * normal
        return tuple(float(value) for value in point)

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

    def set_origin_axes_visible(self, visible: bool) -> None:
        self._origin_axes_visible = bool(visible)
        for name in (
            "origin-axes-o",
            "origin-axis-x",
            "origin-axis-y",
            "origin-axis-z",
            "origin-axis-label-o",
            "origin-axis-label-x",
            "origin-axis-label-y",
            "origin-axis-label-z",
        ):
            self._remove_overlay(name)
        if self._origin_axes_visible:
            self._render_origin_axes()
        self.plotter.render()

    def origin_axes_visible(self) -> bool:
        return bool(self._origin_axes_visible)

    def _origin_axes_span(self) -> float:
        coords: list[tuple[float, float, float]] = []
        if self._model is not None:
            coords.extend(
                tuple(float(value) for value in node.xyz)
                for node in self._model.nodes.values()
            )
        coords.extend(
            tuple(float(value) for value in point.xyz)
            for point in self._points.values()
        )
        if not coords:
            return 1.0
        values = np.asarray(coords, dtype=float)
        if values.ndim != 2 or values.shape[1] != 3:
            return 1.0
        finite = values[np.all(np.isfinite(values), axis=1)]
        if not len(finite):
            return 1.0
        low = finite.min(axis=0)
        high = finite.max(axis=0)
        return max(
            float(high[0] - low[0]),
            float(high[1] - low[1]),
            float(high[2] - low[2]),
            float(np.max(np.abs(finite))) * 0.15,
            1.0,
        )

    def _render_origin_axes(self) -> None:
        for name in (
            "origin-axes-o",
            "origin-axis-x",
            "origin-axis-y",
            "origin-axis-z",
            "origin-axis-label-o",
            "origin-axis-label-x",
            "origin-axis-label-y",
            "origin-axis-label-z",
        ):
            self._remove_overlay(name)
        if not self._origin_axes_visible:
            return

        origin = np.asarray((0.0, 0.0, 0.0), dtype=float)
        length = max(self._origin_axes_span() * 0.14, 1.0e-6)
        endpoints = {
            "x": origin + np.asarray((length, 0.0, 0.0)),
            "y": origin + np.asarray((0.0, length, 0.0)),
            "z": origin + np.asarray((0.0, 0.0, length)),
        }
        axis_styles = {
            "x": ("#d62828", "X"),
            "y": ("#2a9d45", "Y"),
            "z": ("#1769d2", "Z"),
        }

        self.plotter.add_mesh(
            pv.PolyData([origin]),
            name="origin-axes-o",
            color=self._background_foreground_color(),
            render_points_as_spheres=True,
            point_size=10,
            pickable=False,
            render=False,
        )
        for key, endpoint in endpoints.items():
            color, _label = axis_styles[key]
            self.plotter.add_mesh(
                pv.Line(origin, endpoint),
                name=f"origin-axis-{key}",
                color=color,
                line_width=5,
                render_lines_as_tubes=True,
                pickable=False,
                render=False,
            )

        self._add_annotation_labels(
            [origin],
            ["O"],
            name="origin-axis-label-o",
            text_color=self._background_foreground_color(),
            font_size=11,
            always_visible=True,
        )
        for key, endpoint in endpoints.items():
            color, label = axis_styles[key]
            self._add_annotation_labels(
                [endpoint],
                [label],
                name=f"origin-axis-label-{key}",
                text_color=color,
                font_size=12,
                always_visible=True,
            )

    @staticmethod
    def _nice_geometry_grid_spacing(span: float) -> float:
        value = max(float(span) / 12.0, 1.0e-9)
        power = 10.0 ** math.floor(math.log10(value))
        scaled = value / power
        if scaled <= 1.0:
            factor = 1.0
        elif scaled <= 2.0:
            factor = 2.0
        elif scaled <= 5.0:
            factor = 5.0
        else:
            factor = 10.0
        return factor * power

    def _geometry_sketch_grid_spec(self) -> dict[str, float] | None:
        """Return the visible sketch-grid lattice in local U/V coordinates."""
        if not self._geometry_sketch_grid_visible:
            return None

        local_points: list[tuple[float, float]] = []
        for point in self._points.values():
            try:
                local_points.append(self.geometry_world_to_local(point.xyz))
            except ValueError:
                continue
        if local_points:
            values = np.asarray(local_points, dtype=float)
            min_u, min_v = values.min(axis=0)
            max_u, max_v = values.max(axis=0)
        else:
            min_u = min_v = -5.0
            max_u = max_v = 5.0

        span = max(float(max_u - min_u), float(max_v - min_v), 10.0)
        spacing = self._nice_geometry_grid_spacing(span)
        half = max(6.0 * spacing, 0.75 * span)
        center_u = 0.5 * float(min_u + max_u)
        center_v = 0.5 * float(min_v + max_v)
        start_u = math.floor((center_u - half) / spacing) * spacing
        end_u = math.ceil((center_u + half) / spacing) * spacing
        start_v = math.floor((center_v - half) / spacing) * spacing
        end_v = math.ceil((center_v + half) / spacing) * spacing
        return {
            "spacing": float(spacing),
            "start_u": float(start_u),
            "end_u": float(end_u),
            "start_v": float(start_v),
            "end_v": float(end_v),
        }

    def geometry_sketch_grid_snap(
        self,
        xyz,
    ) -> tuple[tuple[float, float, float], float] | None:
        """Return the nearest visible grid intersection for a workplane point."""
        spec = self._geometry_sketch_grid_spec()
        if spec is None:
            return None
        try:
            u, v = self.geometry_world_to_local(xyz)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(u) or not math.isfinite(v):
            return None

        spacing = float(spec["spacing"])
        if not math.isfinite(spacing) or spacing <= 0.0:
            return None
        epsilon = max(spacing * 1.0e-9, 1.0e-12)
        if (
            u < spec["start_u"] - epsilon
            or u > spec["end_u"] + epsilon
            or v < spec["start_v"] - epsilon
            or v > spec["end_v"] + epsilon
        ):
            return None

        snapped_u = round(u / spacing) * spacing
        snapped_v = round(v / spacing) * spacing
        if (
            snapped_u < spec["start_u"] - epsilon
            or snapped_u > spec["end_u"] + epsilon
            or snapped_v < spec["start_v"] - epsilon
            or snapped_v > spec["end_v"] + epsilon
        ):
            return None
        point = self.geometry_local_to_world(snapped_u, snapped_v)
        return (
            tuple(float(value) for value in point),
            spacing,
        )

    def _render_geometry_sketch_grid(self) -> None:
        self._remove_overlay("geometry-sketch-grid")
        if (
            not self._geometry_sketch_grid_visible
            or self._display_domain != "geometry"
        ):
            return

        spec = self._geometry_sketch_grid_spec()
        if spec is None:
            return
        spacing = float(spec["spacing"])
        start_u = float(spec["start_u"])
        end_u = float(spec["end_u"])
        start_v = float(spec["start_v"])
        end_v = float(spec["end_v"])

        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        count_u = int(round((end_u - start_u) / spacing))
        count_v = int(round((end_v - start_v) / spacing))
        for index in range(count_u + 1):
            value = start_u + index * spacing
            base = len(points)
            points.extend((
                self.geometry_local_to_world(value, start_v),
                self.geometry_local_to_world(value, end_v),
            ))
            lines.extend((2, base, base + 1))
        for index in range(count_v + 1):
            value = start_v + index * spacing
            base = len(points)
            points.extend((
                self.geometry_local_to_world(start_u, value),
                self.geometry_local_to_world(end_u, value),
            ))
            lines.extend((2, base, base + 1))

        if not points:
            return
        mesh = pv.PolyData(
            np.asarray(points, dtype=float),
            lines=np.asarray(lines, dtype=np.int64),
            deep=True,
        )
        self.plotter.add_mesh(
            mesh,
            name="geometry-sketch-grid",
            color=self._background_grid_color(),
            line_width=1.0,
            opacity=0.55,
            pickable=False,
            render=False,
        )

    def _invalidate_geometry_sketch_cursor_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        if isinstance(self._geometry_sketch_preview, dict):
            self._geometry_sketch_preview = dict(
                self._geometry_sketch_preview
            )
            self._geometry_sketch_preview["cursor"] = None
            self._geometry_sketch_preview["snap_label"] = None
            self._last_geometry_sketch_qt_pos = None
            self._render_geometry_sketch_preview(render=render)
        else:
            self._last_geometry_sketch_qt_pos = None

    def clear_geometry_sketch_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._geometry_sketch_preview = None
        for name in (
            "geometry-sketch-preview-path",
            "geometry-sketch-preview-points",
            "geometry-sketch-snap",
            "geometry-sketch-label",
        ):
            self._remove_overlay(name)
        if render:
            self.plotter.render()

    def show_geometry_sketch_preview(
        self,
        points,
        *,
        cursor=None,
        closed: bool = False,
        snap_label: str | None = None,
    ) -> None:
        coords = [
            tuple(float(value) for value in point)
            for point in points
        ]
        cursor_point = (
            None
            if cursor is None
            else tuple(float(value) for value in cursor)
        )
        self._geometry_sketch_preview = {
            "points": coords,
            "cursor": cursor_point,
            "closed": bool(closed),
            "snap_label": snap_label,
        }
        self._render_geometry_sketch_preview(render=True)

    def _render_geometry_sketch_preview(
        self,
        *,
        render: bool = False,
    ) -> None:
        for name in (
            "geometry-sketch-preview-path",
            "geometry-sketch-preview-points",
            "geometry-sketch-snap",
            "geometry-sketch-label",
        ):
            self._remove_overlay(name)
        data = self._geometry_sketch_preview
        if (
            self._display_domain != "geometry"
            or not isinstance(data, dict)
        ):
            if render:
                self.plotter.render()
            return

        points = list(data.get("points", []))
        cursor = data.get("cursor")
        closed = bool(data.get("closed", False))
        snap_label = data.get("snap_label")
        path_points = list(points)
        if cursor is not None:
            path_points.append(cursor)
        if closed and len(path_points) >= 3:
            path_points.append(path_points[0])

        if points:
            self.plotter.add_mesh(
                pv.PolyData(np.asarray(points, dtype=float)),
                name="geometry-sketch-preview-points",
                color="#ff7a00",
                render_points_as_spheres=True,
                point_size=13,
                pickable=False,
                render=False,
            )
        if len(path_points) >= 2:
            self.plotter.add_mesh(
                pv.lines_from_points(
                    np.asarray(path_points, dtype=float),
                    close=False,
                ),
                name="geometry-sketch-preview-path",
                color="#ff7a00",
                line_width=3.5,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )
        if cursor is not None:
            self.plotter.add_mesh(
                pv.PolyData(np.asarray([cursor], dtype=float)),
                name="geometry-sketch-snap",
                color="#00a8a8",
                render_points_as_spheres=True,
                point_size=15,
                pickable=False,
                render=False,
            )
            if snap_label:
                self._add_annotation_labels(
                    [cursor],
                    [str(snap_label)],
                    name="geometry-sketch-label",
                    text_color="#087f7f",
                    font_size=10,
                    always_visible=True,
                )
        if render:
            self.plotter.render()

    def clear_geometry_pick_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        for name in (
            "geometry-pick-points",
            "geometry-pick-path",
        ):
            self._remove_overlay(name)
        if render:
            self.plotter.render()

    def show_geometry_pick_preview(
        self,
        point_tags: list[int] | tuple[int, ...],
        *,
        closed: bool = False,
    ) -> None:
        self.clear_geometry_pick_preview(render=False)
        valid = [
            int(tag)
            for tag in point_tags
            if int(tag) in self._points
        ]
        if not valid:
            self.plotter.render()
            return
        coords = np.asarray(
            [self._points[tag].xyz for tag in valid],
            dtype=float,
        )
        self.plotter.add_mesh(
            pv.PolyData(coords),
            name="geometry-pick-points",
            color="#ff7a00",
            render_points_as_spheres=True,
            point_size=16,
            pickable=False,
            render=False,
        )
        if len(coords) >= 2:
            path_points = coords
            if closed and len(coords) >= 3:
                path_points = np.vstack((coords, coords[0]))
            lines = pv.lines_from_points(
                path_points,
                close=False,
            )
            self.plotter.add_mesh(
                lines,
                name="geometry-pick-path",
                color="#ff7a00",
                line_width=4,
                render_lines_as_tubes=True,
                pickable=False,
                render=False,
            )
        self.plotter.render()

    def clear_measure_snap_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        """Remove the temporary Measure snap target and preview line."""
        for name in (
            "measure-snap-target",
            "measure-snap-line",
            "measure-snap-label",
        ):
            self._remove_overlay(name)
        if render:
            self.plotter.render()

    def show_measure_snap_preview(
        self,
        xyz,
        *,
        label: str | None = None,
        anchor=None,
    ) -> None:
        """Preview the point Measure will snap to before the user clicks."""
        self.clear_measure_snap_preview(render=False)
        point = np.asarray(tuple(float(value) for value in xyz), dtype=float)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            self.plotter.render()
            return

        self.plotter.add_mesh(
            pv.PolyData([point]),
            name="measure-snap-target",
            color="#00a8a8",
            render_points_as_spheres=True,
            point_size=15,
            pickable=False,
            render=False,
        )

        if anchor is not None:
            first = np.asarray(
                tuple(float(value) for value in anchor),
                dtype=float,
            )
            if (
                first.shape == (3,)
                and np.all(np.isfinite(first))
                and float(np.linalg.norm(point - first)) > 1.0e-15
            ):
                self.plotter.add_mesh(
                    pv.Line(first, point),
                    name="measure-snap-line",
                    color="#6f42c1",
                    line_width=2,
                    opacity=0.75,
                    pickable=False,
                    render=False,
                )

        if label:
            self._add_annotation_labels(
                [point],
                [str(label)],
                name="measure-snap-label",
                text_color="#087f7f",
                font_size=10,
                always_visible=True,
            )
        self.plotter.render()

    def clear_measure_anchor(self, *, render: bool = True) -> None:
        """Remove the temporary first-point marker for the Measure tool."""
        self._remove_overlay("measure-anchor")
        if render:
            self.plotter.render()

    def show_measure_anchor_at(self, xyz) -> None:
        """Highlight an arbitrary world-space first measurement point."""
        self.clear_measure_anchor(render=False)
        point = np.asarray(tuple(float(value) for value in xyz), dtype=float)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            self.plotter.render()
            return
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

    def show_measure_anchor(self, node_tag: int) -> None:
        """Highlight the first FE node selected for a distance measurement."""
        if self._model is None or int(node_tag) not in self._model.nodes:
            self.clear_measure_anchor(render=True)
            return
        self.show_measure_anchor_at(self._model.nodes[int(node_tag)].xyz)

    def add_point_distance_measurement(
        self,
        first_xyz,
        second_xyz,
        *,
        first_label: str | None = None,
        second_label: str | None = None,
    ) -> dict[str, float]:
        """Draw a persistent distance measurement between arbitrary XYZ points."""
        p1 = np.asarray(tuple(float(value) for value in first_xyz), dtype=float)
        p2 = np.asarray(tuple(float(value) for value in second_xyz), dtype=float)
        if (
            p1.shape != (3,)
            or p2.shape != (3,)
            or not np.all(np.isfinite(p1))
            or not np.all(np.isfinite(p2))
        ):
            raise ValueError("Measure points require finite XYZ coordinates.")

        delta = p2 - p1
        distance = float(np.linalg.norm(delta))
        if distance <= 1.0e-15:
            raise ValueError("Measure Distance requires two different points.")

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
        title = ""
        if first_label or second_label:
            title = (
                f"{first_label or 'P1'} → {second_label or 'P2'}\n"
            )
        label = (
            f"{title}"
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

    def add_distance_measurement(
        self,
        first_node_tag: int,
        second_node_tag: int,
    ) -> dict[str, float]:
        """Draw and return an FE node-to-node distance measurement."""
        if self._model is None:
            raise ValueError("No model is currently displayed.")
        first_tag = int(first_node_tag)
        second_tag = int(second_node_tag)
        if first_tag not in self._model.nodes or second_tag not in self._model.nodes:
            raise ValueError("Measure nodes must exist in the current model.")
        return self.add_point_distance_measurement(
            self._model.nodes[first_tag].xyz,
            self._model.nodes[second_tag].xyz,
            first_label=f"N{first_tag}",
            second_label=f"N{second_tag}",
        )

    def clear_measurements(self, *, render: bool = True) -> None:
        """Remove all persistent Measure overlays from the viewport."""
        self.clear_measure_anchor(render=False)
        self.clear_measure_snap_preview(render=False)
        for name in tuple(self._measurement_actor_names):
            self._remove_overlay(name)
        self._measurement_actor_names.clear()
        if render:
            self.plotter.render()

    def _install_mouse_observers(self) -> None:
        # All viewport mouse input is handled through Qt so the default VTK
        # left/right-drag navigation cannot conflict with selection/context menus.
        self.plotter.interactor.installEventFilter(self)

    def _qt_vtk_pixel_scales(self) -> tuple[float, float]:
        """Return the Qt-to-VTK device pixel ratio used by QVTK itself."""
        widget = self.plotter.interactor
        ratio = None
        getter = getattr(widget, "_getPixelRatio", None)
        if callable(getter):
            try:
                ratio = float(getter())
            except Exception:
                ratio = None
        if ratio is None:
            getter = getattr(widget, "devicePixelRatioF", None)
            if callable(getter):
                try:
                    ratio = float(getter())
                except Exception:
                    ratio = None
        if ratio is None:
            getter = getattr(widget, "devicePixelRatio", None)
            if callable(getter):
                try:
                    ratio = float(getter())
                except Exception:
                    ratio = None
        if ratio is None or not math.isfinite(ratio) or ratio <= 0.0:
            ratio = 1.0
        return ratio, ratio

    def _vtk_position_from_qt(self, event) -> tuple[int, int]:
        pos = event.position()
        scale_x, scale_y = self._qt_vtk_pixel_scales()
        widget_height = float(self.plotter.interactor.height())
        x = int(round(float(pos.x()) * scale_x))
        y = int(
            round(
                (widget_height - float(pos.y()) - 1.0)
                * scale_y
            )
        )
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
        # ANSYS-style navigation. During an active 2D sketch, plain MMB pans
        # instead of rotating the camera away from the locked work plane.
        ctrl = bool(modifiers & Qt.ControlModifier)
        shift = bool(modifiers & Qt.ShiftModifier)
        if ctrl and shift:
            self._nav_mode = None
        elif ctrl:
            self._nav_mode = "pan"
        elif shift:
            self._nav_mode = "zoom"
        elif self._interaction_tool == "geometry_sketch":
            self._nav_mode = "pan"
        else:
            self._nav_mode = "rotate"
        self._invalidate_geometry_sketch_cursor_preview(render=False)
        self._nav_last_pos = pos
        self._hover_ref = None
        self._hover_pick_timer.stop()
        self._pending_hover_vtk_pos = None
        self._id_label_restore_timer.stop()
        self._set_id_labels_visible(False, render=False)
        self._remove_overlay("hover-element")
        self._remove_overlay("hover-node")
        self._remove_overlay("hover-geometry-line")
        self._remove_overlay("hover-geometry-surface")
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
        self._invalidate_geometry_sketch_cursor_preview(render=False)
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
                if (
                    self._interaction_tool == "geometry_sketch"
                    and self._display_domain == "geometry"
                ):
                    last = self._last_geometry_sketch_qt_pos
                    if (
                        last is None
                        or (qt_pos[0] - last[0]) ** 2
                        + (qt_pos[1] - last[1]) ** 2 >= 9.0
                    ):
                        self._last_geometry_sketch_qt_pos = qt_pos
                        vtk_pos = self._vtk_position_from_qt(event)
                        world = self.geometry_workplane_point(*vtk_pos)
                        if world is not None:
                            self.geometry_sketch_moved.emit(
                                {
                                    "world": world,
                                    "screen": qt_pos,
                                    "plane": self._geometry_sketch_plane,
                                }
                            )
                        else:
                            self._invalidate_geometry_sketch_cursor_preview(
                                render=True
                            )
                    return False
                if self._interaction_tool == "measure":
                    last = self._last_measure_qt_pos
                    if (
                        last is None
                        or (qt_pos[0] - last[0]) ** 2
                        + (qt_pos[1] - last[1]) ** 2 >= 9.0
                    ):
                        self._last_measure_qt_pos = qt_pos
                        vtk_pos = self._vtk_position_from_qt(event)
                        world = (
                            self.geometry_workplane_point(*vtk_pos)
                            if self._display_domain == "geometry"
                            else None
                        )
                        self.measure_moved.emit(
                            {
                                "world": world,
                                "screen": qt_pos,
                                "plane": (
                                    self._geometry_sketch_plane
                                    if self._display_domain == "geometry"
                                    else None
                                ),
                            }
                        )
                    if self._display_domain != "geometry":
                        self._schedule_hover_from_qt(event)
                    return False
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
                    world = (
                        self.geometry_workplane_point(*vtk_pos)
                        if self._display_domain == "geometry"
                        else None
                    )
                    pos = event.position()
                    self.entity_clicked.emit(
                        {
                            "kind": entity[0] if entity else None,
                            "tag": entity[1] if entity else None,
                            "mode": self._selection_mode_from_modifiers(
                                event.modifiers()
                            ),
                            "world": world,
                            "screen": (float(pos.x()), float(pos.y())),
                            "plane": (
                                self._geometry_sketch_plane
                                if self._display_domain == "geometry"
                                else None
                            ),
                        }
                    )
                self._left_press_pos = None
                return True

            if event.button() == Qt.RightButton:
                if (
                    self._interaction_tool == "geometry_sketch"
                    and not self._moved(self._right_press_pos, vtk_pos)
                ):
                    self._right_press_pos = None
                    self.geometry_sketch_finished.emit()
                    return True
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
            if (
                event.button() == Qt.LeftButton
                and self._interaction_tool == "geometry_sketch"
            ):
                self._left_press_pos = None
                self.geometry_sketch_finished.emit()
                return True
            if event.button() == Qt.LeftButton:
                entity = self.pick_entity(*self._vtk_position_from_qt(event))
                if entity:
                    self.entity_double_clicked.emit(
                        {"kind": entity[0], "tag": entity[1]}
                    )
                return True

        elif event_type == QEvent.Leave:
            if self._interaction_tool == "geometry_sketch":
                self._invalidate_geometry_sketch_cursor_preview(render=True)
            self._pending_hover_vtk_pos = None
            return False

        elif event_type == QEvent.Wheel:
            self._wheel_zoom(event.angleDelta().y())
            return True

        return super().eventFilter(obj, event)

    def _world_to_qt(self, xyz) -> tuple[float, float]:
        renderer = self.plotter.renderer
        renderer.SetWorldPoint(
            float(xyz[0]),
            float(xyz[1]),
            float(xyz[2]),
            1.0,
        )
        renderer.WorldToDisplay()
        display = renderer.GetDisplayPoint()
        scale_x, scale_y = self._qt_vtk_pixel_scales()
        inv_x = 1.0 / max(scale_x, 1.0e-12)
        inv_y = 1.0 / max(scale_y, 1.0e-12)
        return (
            float(display[0]) * inv_x,
            float(self.plotter.interactor.height())
            - 1.0
            - float(display[1]) * inv_y,
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

    def _show_display_options_menu(self) -> None:
        """Show compact model-display toggles next to the viewport button."""
        menu = QMenu(self)
        definitions = (
            ("reinforcement", "Discrete reinforcement"),
            ("node_numbers", "Node numbers"),
            ("element_numbers", "Element numbers"),
            ("masses", "Mass symbols"),
            ("section_axes", "Section / shell axes"),
            ("nodal_loads", "Nodal loads"),
            ("element_loads", "Element loads"),
            (
                "prescribed_displacements",
                "Prescribed displacements",
            ),
            ("load_values", "Load values"),
        )
        for key, label in definitions:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.display_option(key))
            action.toggled.connect(
                lambda checked, name=key:
                self.set_display_option(name, checked)
            )

        sender = self.sender()
        if isinstance(sender, QToolButton):
            menu.exec(
                sender.mapToGlobal(sender.rect().bottomLeft())
            )
        else:
            menu.exec(self.mapToGlobal(self.rect().center()))

    def _toggle_fullscreen(self):
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
        else:
            window.showFullScreen()

    @staticmethod
    def _normalized_background_color(
        value: str,
        fallback: str,
    ) -> str:
        text = str(value or "").strip()
        if text.startswith("#"):
            text = text[1:]
        if len(text) != 6:
            return str(fallback)
        try:
            int(text, 16)
        except ValueError:
            return str(fallback)
        return "#" + text.lower()

    @staticmethod
    def background_style_spec(
        preset: str,
        *,
        custom_bottom: str = "#f2f5f8",
        custom_top: str = "#e1e8ef",
    ) -> tuple[str, str | None]:
        preset = str(preset or "ANSYS Gradient")
        custom_bottom = ModelViewport._normalized_background_color(
            custom_bottom,
            "#f2f5f8",
        )
        custom_top = ModelViewport._normalized_background_color(
            custom_top,
            "#e1e8ef",
        )
        styles: dict[str, tuple[str, str | None]] = {
            "Light": ("#f2f5f8", None),
            "Dark": ("#20262e", None),
            "ANSYS Gradient": ("#f2f5f8", "#e1e8ef"),
            "Publication White": ("#ffffff", None),
            "Custom Solid": (custom_bottom, None),
            "Custom Gradient": (
                custom_bottom,
                custom_top,
            ),
        }
        if preset not in styles:
            raise ValueError(f"Unsupported viewport background: {preset}")
        return styles[preset]

    @staticmethod
    def _hex_luminance(value: str) -> float:
        text = str(value).strip().lstrip("#")
        if len(text) != 6:
            return 1.0
        try:
            red = int(text[0:2], 16) / 255.0
            green = int(text[2:4], 16) / 255.0
            blue = int(text[4:6], 16) / 255.0
        except ValueError:
            return 1.0
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    def _background_is_dark(self) -> bool:
        bottom, top = self.background_style_spec(
            self._background_preset,
            custom_bottom=self._background_bottom,
            custom_top=self._background_top,
        )
        values = [self._hex_luminance(bottom)]
        if top is not None:
            values.append(self._hex_luminance(top))
        return sum(values) / len(values) < 0.45

    def _background_foreground_color(self) -> str:
        return "#e8edf2" if self._background_is_dark() else "#29445e"

    def _background_grid_color(self) -> str:
        return "#66727f" if self._background_is_dark() else "#cfd8e3"

    def background_style(self) -> dict[str, str]:
        return {
            "preset": self._background_preset,
            "bottom": self._background_bottom,
            "top": self._background_top,
        }

    def set_background_style(
        self,
        preset: str,
        *,
        custom_bottom: str | None = None,
        custom_top: str | None = None,
        render: bool = True,
    ) -> None:
        preset = str(preset or "ANSYS Gradient")
        # Validate before mutating the current display state.
        self.background_style_spec(
            preset,
            custom_bottom=custom_bottom or self._background_bottom,
            custom_top=custom_top or self._background_top,
        )
        self._background_preset = preset
        if custom_bottom is not None:
            self._background_bottom = self._normalized_background_color(
                custom_bottom,
                "#f2f5f8",
            )
        if custom_top is not None:
            self._background_top = self._normalized_background_color(
                custom_top,
                "#e1e8ef",
            )

        self._apply_background(render=False)
        self._apply_axes_widget()

        if self._origin_axes_visible:
            self._render_origin_axes()
        if (
            self._geometry_sketch_grid_visible
            and self._display_domain == "geometry"
        ):
            self._render_geometry_sketch_grid()
        if render:
            self.plotter.render()

    def _apply_background(self, *, render: bool = False) -> None:
        bottom, top = self.background_style_spec(
            self._background_preset,
            custom_bottom=self._background_bottom,
            custom_top=self._background_top,
        )
        if top is None:
            self.plotter.set_background(bottom)
        else:
            self.plotter.set_background(bottom, top=top)
        if render:
            self.plotter.render()

    def _apply_axes_widget(self) -> None:
        try:
            self.plotter.hide_axes()
        except Exception:
            pass
        self.plotter.add_axes(
            line_width=2,
            color=self._background_foreground_color(),
            xlabel="X",
            ylabel="Y",
            zlabel="Z",
        )

    def _reset_scene(self) -> None:
        self._apply_background(render=False)
        self._apply_axes_widget()

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
        if element.element_type in TRUSS_ELEMENT_TYPES:
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
            if element.element_type in QUAD_ELEMENT_TYPES
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
                if str(element.group).startswith("rc-wall-rebar"):
                    color = "#d64545"
                elif element.group == "column":
                    color = "#687d90"
                elif element.element_type in QUAD_ELEMENT_TYPES:
                    color = "#8fa3b5"
                else:
                    color = "#74889b"
                mapping[int(tag)] = self._hex_rgb(color)
            return mapping, []

        section_material_cache: dict[int, int | None] = {}
        fiber_material_tags: set[int] = set()

        def key_for_tag(tag: int) -> tuple[str, object]:
            element = self._model.elements[tag]
            if self._model_color_mode != "material":
                return self._element_color_key(element)

            if element.element_type in TRUSS_ELEMENT_TYPES:
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
        if name == "reinforcement":
            self._rebuild_visible_scene()
            return
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
        if not self._display_options.get("reinforcement", True):
            tags = {
                tag
                for tag in tags
                if not str(self._model.elements[tag].group).startswith(
                    "rc-wall-rebar"
                )
            }
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

    @staticmethod
    def _support_visual_spec(support_type: str) -> dict[str, object]:
        """Return viewport style metadata for common boundary conditions."""
        return {
            "Fixed": {
                "family": "fixed",
                "color": "#12843d",
                "free_axis": None,
            },
            "Pinned": {
                "family": "pinned",
                "color": "#19b74e",
                "free_axis": None,
            },
            "Roller X": {
                "family": "roller",
                "color": "#16a3a8",
                "free_axis": "x",
            },
            "Roller Y": {
                "family": "roller",
                "color": "#16a3a8",
                "free_axis": "y",
            },
            "Roller Z": {
                "family": "roller",
                "color": "#16a3a8",
                "free_axis": "z",
            },
        }.get(
            str(support_type),
            {
                "family": "custom",
                "color": "#d7a21b",
                "free_axis": None,
            },
        )

    def _draw_support_symbol(
        self,
        support_type: str,
        xyz: tuple[float, float, float],
        size: float,
    ) -> None:
        """Draw one Mechanical-style support glyph in the FE viewport."""
        spec = self._support_visual_spec(support_type)
        family = str(spec["family"])
        color = str(spec["color"])
        free_axis = spec["free_axis"]
        x, y, z = (float(value) for value in xyz)
        edge_color = "#0b6330"

        if family == "fixed":
            self.plotter.add_mesh(
                pv.Cube(
                    center=(x, y, z - size * 0.34),
                    x_length=size * 1.18,
                    y_length=size * 1.18,
                    z_length=size * 0.50,
                ),
                color=color,
                edge_color=edge_color,
                show_edges=True,
                line_width=1,
                pickable=False,
                render=False,
            )
            self.plotter.add_mesh(
                pv.Cube(
                    center=(x, y, z - size * 0.64),
                    x_length=size * 1.55,
                    y_length=size * 1.55,
                    z_length=size * 0.10,
                ),
                color="#a8cdb4",
                edge_color=edge_color,
                show_edges=True,
                pickable=False,
                render=False,
            )
            return

        support = pv.Cone(
            center=(x, y, z - size * 0.54),
            direction=(0.0, 0.0, -1.0),
            height=size * 1.02,
            radius=size * 0.68,
            resolution=4,
        )
        self.plotter.add_mesh(
            support,
            color=color,
            edge_color=edge_color,
            show_edges=True,
            line_width=1,
            pickable=False,
            render=False,
        )

        if family == "pinned":
            self.plotter.add_mesh(
                pv.Cube(
                    center=(x, y, z - size * 1.08),
                    x_length=size * 1.45,
                    y_length=size * 1.45,
                    z_length=size * 0.08,
                ),
                color="#b7ddc1",
                edge_color=edge_color,
                show_edges=True,
                pickable=False,
                render=False,
            )
            return

        if family == "roller" and isinstance(free_axis, str):
            axis_vectors = {
                "x": np.asarray((1.0, 0.0, 0.0)),
                "y": np.asarray((0.0, 1.0, 0.0)),
                "z": np.asarray((0.0, 0.0, 1.0)),
            }
            axis_colors = {
                "x": "#d64545",
                "y": "#2e9f57",
                "z": "#2b6cb0",
            }
            direction = axis_vectors[free_axis]

            # Two rollers make the support visually distinct from a pin.
            roller_offset = (
                direction
                if free_axis in {"x", "y"}
                else np.asarray((1.0, 0.0, 0.0))
            )
            base = np.asarray((x, y, z - size * 1.08))
            for sign in (-1.0, 1.0):
                center = base + roller_offset * sign * size * 0.34
                self.plotter.add_mesh(
                    pv.Sphere(
                        radius=size * 0.14,
                        center=tuple(center),
                        theta_resolution=12,
                        phi_resolution=8,
                    ),
                    color="#d9eeee",
                    edge_color="#147b80",
                    show_edges=True,
                    pickable=False,
                    render=False,
                )

            # A double-ended guide explicitly communicates the released
            # translation direction X/Y/Z, including the ambiguous Roller Z.
            if free_axis == "z":
                guide_center = np.asarray(
                    (x + size * 0.92, y, z - size * 0.45)
                )
            else:
                guide_center = np.asarray((x, y, z + size * 0.28))
            half = size * 0.78
            p1 = guide_center - direction * half
            p2 = guide_center + direction * half
            axis_color = axis_colors[free_axis]
            self.plotter.add_mesh(
                pv.Line(tuple(p1), tuple(p2)),
                color=axis_color,
                line_width=4,
                pickable=False,
                render=False,
            )
            for end, sign in ((p1, -1.0), (p2, 1.0)):
                self.plotter.add_mesh(
                    pv.Cone(
                        center=tuple(end),
                        direction=tuple(direction * sign),
                        height=size * 0.26,
                        radius=size * 0.10,
                        resolution=12,
                    ),
                    color=axis_color,
                    pickable=False,
                    render=False,
                )
            return

        # Custom restraint: deliberately neutral/amber because an arbitrary
        # DOF pattern cannot be represented safely by a standard support icon.
        self.plotter.add_mesh(
            pv.Sphere(
                radius=size * 0.18,
                center=(x, y, z - size * 1.05),
                theta_resolution=12,
                phi_resolution=8,
            ),
            color="#f2c94c",
            edge_color="#9f7b08",
            show_edges=True,
            pickable=False,
            render=False,
        )

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
            if element is None or element.element_type in QUAD_ELEMENT_TYPES:
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
    def _batched_reinforcement_mesh(
        model: StructuralModel,
        tags,
        span: float,
    ) -> object | None:
        """Build schematic separated RC-wall reinforcement line geometry."""
        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        cell_tags: list[int] = []

        mefi = next(
            (
                element
                for element in model.elements.values()
                if (
                    element.element_type == "MEFI"
                    and len(element.mefi_widths) >= 2
                )
            ),
            None,
        )
        low, high = model.bounds()
        wall_width = max(float(high[0] - low[0]), 1.0e-12)
        boundary_width = (
            float(mefi.mefi_widths[0])
            if mefi is not None and mefi.mefi_widths
            else wall_width * 0.18
        )
        layer_offset = max(float(span) * 0.004, boundary_width * 0.04)

        for tag in tags:
            element = model.elements.get(int(tag))
            if element is None:
                continue
            node_i = model.nodes.get(element.i)
            node_j = model.nodes.get(element.j)
            if node_i is None or node_j is None:
                continue

            start = np.asarray(node_i.xyz, dtype=float).copy()
            end = np.asarray(node_j.xyz, dtype=float).copy()
            group = str(element.group)

            if group.startswith("rc-wall-rebar-left-") or group.startswith(
                "rc-wall-rebar-right-"
            ):
                side = (
                    "left"
                    if group.startswith("rc-wall-rebar-left-")
                    else "right"
                )
                tail = group.split(f"rc-wall-rebar-{side}-", 1)[1]
                parts = tail.split("-")
                layer = parts[0] if parts else "center"
                token = next(
                    (part for part in parts if part.startswith("b")),
                    "",
                )
                index = 1
                count = 1
                if "of" in token:
                    try:
                        index_text, count_text = token[1:].split("of", 1)
                        index = max(int(index_text), 1)
                        count = max(int(count_text), 1)
                    except (TypeError, ValueError):
                        index, count = 1, 1

                fraction = (
                    0.5
                    if count <= 1
                    else (index - 1) / max(count - 1, 1)
                )
                inset_fraction = 0.16 + 0.68 * fraction
                x_offset = boundary_width * inset_fraction
                if side == "right":
                    x_offset = -x_offset
                start[0] += x_offset
                end[0] += x_offset

                if layer == "front":
                    start[2] += layer_offset
                    end[2] += layer_offset
                elif layer == "back":
                    start[2] -= layer_offset
                    end[2] -= layer_offset

            elif (
                group.startswith("rc-wall-rebar-web-horizontal-")
                or group.startswith(
                    "rc-wall-rebar-boundary-horizontal-left-"
                )
                or group.startswith(
                    "rc-wall-rebar-boundary-horizontal-right-"
                )
            ):
                if group.startswith("rc-wall-rebar-web-horizontal-"):
                    tail = group.split(
                        "rc-wall-rebar-web-horizontal-",
                        1,
                    )[1]
                elif group.startswith(
                    "rc-wall-rebar-boundary-horizontal-left-"
                ):
                    tail = group.split(
                        "rc-wall-rebar-boundary-horizontal-left-",
                        1,
                    )[1]
                else:
                    tail = group.split(
                        "rc-wall-rebar-boundary-horizontal-right-",
                        1,
                    )[1]
                layer = tail.split("-", 1)[0]
                if layer == "front":
                    start[2] += layer_offset
                    end[2] += layer_offset
                elif layer == "back":
                    start[2] -= layer_offset
                    end[2] -= layer_offset

            elif group.startswith("rc-wall-rebar-web-vertical-"):
                tail = group.split(
                    "rc-wall-rebar-web-vertical-",
                    1,
                )[1]
                layer = tail.split("-", 1)[0]
                if layer == "front":
                    start[2] += layer_offset
                    end[2] += layer_offset
                elif layer == "back":
                    start[2] -= layer_offset
                    end[2] -= layer_offset

            index0 = len(points)
            points.extend((tuple(start), tuple(end)))
            lines.extend((2, index0, index0 + 1))
            cell_tags.append(int(tag))

        if not points:
            return None
        mesh = pv.PolyData(
            np.asarray(points, dtype=float),
            lines=np.asarray(lines, dtype=np.int64),
            deep=True,
        )
        mesh.cell_data["element_tag"] = np.asarray(
            cell_tags,
            dtype=np.int64,
        )
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
                or element.element_type not in QUAD_ELEMENT_TYPES
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
            if element is None or element.element_type in QUAD_ELEMENT_TYPES:
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
            if self._model.elements[tag].element_type in QUAD_ELEMENT_TYPES
        ]
        line_tags = [
            tag
            for tag in visible_tags
            if (
                tag not in set(shell_tags)
                and self._model.elements[tag].element_type
                not in EMBEDDED_ELEMENT_TYPES
            )
        ]
        reinforcement_tags = [
            tag
            for tag in line_tags
            if str(self._model.elements[tag].group).startswith(
                "rc-wall-rebar"
            )
        ]
        structural_line_tags = [
            tag
            for tag in line_tags
            if tag not in set(reinforcement_tags)
        ]
        beam_tags = [
            tag
            for tag in structural_line_tags
            if self._model.elements[tag].group != "column"
        ]
        column_tags = [
            tag
            for tag in structural_line_tags
            if self._model.elements[tag].group == "column"
        ]

        shell_mesh = self._batched_shell_mesh(
            self._model,
            shell_tags,
        )

        reinforcement_mesh = self._batched_reinforcement_mesh(
            self._model,
            reinforcement_tags,
            span,
        )

        if representation == "centerline":
            combined = {}
            for name, tags in (
                ("column", column_tags),
                ("beam", beam_tags),
            ):
                mesh = self._batched_centerline_mesh(self._model, tags)
                if mesh is not None:
                    combined[name] = mesh
            if reinforcement_mesh is not None:
                combined["reinforcement"] = reinforcement_mesh
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
            if reinforcement_mesh is not None:
                combined["reinforcement"] = reinforcement_mesh
            if shell_mesh is not None:
                combined["shell"] = shell_mesh
            return combined

        # Actual-section view remains geometry-driven for frame members.
        # RC-wall discrete reinforcement keeps a compact tube representation
        # because it has an area/material rather than a beam Section object.
        groups: dict[str, list[object]] = {
            "column": [],
            "beam": [],
        }
        beam_size = max(span * 0.010, 0.08)
        column_size = max(span * 0.0115, 0.09)
        fallback: dict[str, list[int]] = {
            "column": [],
            "beam": [],
        }

        for tag in structural_line_tags:
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
        if reinforcement_mesh is not None:
            combined["reinforcement"] = reinforcement_mesh
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

    @staticmethod
    def _polyline_mesh(
        points: list[tuple[float, float, float]],
    ):
        """Build one VTK polyline from ordered 3D points."""
        if len(points) < 2:
            return None
        mesh = pv.PolyData(np.asarray(points, dtype=float))
        mesh.lines = np.hstack((
            np.asarray([len(points)], dtype=np.int64),
            np.arange(len(points), dtype=np.int64),
        ))
        return mesh

    @staticmethod
    def _zero_length_spring_points(
        center: tuple[float, float, float],
        orient_x: tuple[float, float, float],
        size: float,
    ) -> list[tuple[float, float, float]]:
        """Return a compact zig-zag spring glyph around a zeroLength point."""
        origin = np.asarray(center, dtype=float)
        axis = np.asarray(orient_x, dtype=float)
        norm = float(np.linalg.norm(axis))
        if norm <= 1.0e-12:
            axis = np.asarray((1.0, 0.0, 0.0), dtype=float)
        else:
            axis /= norm

        reference = (
            np.asarray((0.0, 0.0, 1.0), dtype=float)
            if abs(float(axis[2])) < 0.85
            else np.asarray((0.0, 1.0, 0.0), dtype=float)
        )
        transverse = np.cross(axis, reference)
        transverse_norm = float(np.linalg.norm(transverse))
        if transverse_norm <= 1.0e-12:
            transverse = np.asarray((0.0, 1.0, 0.0), dtype=float)
        else:
            transverse /= transverse_norm

        half = float(size) * 1.25
        amplitude = float(size) * 0.34
        axial = (-1.0, -0.78, -0.52, -0.26, 0.0, 0.26, 0.52, 0.78, 1.0)
        lateral = (0.0, 0.0, 1.0, -1.0, 1.0, -1.0, 1.0, 0.0, 0.0)
        return [
            tuple(
                float(value)
                for value in (
                    origin
                    + axis * (half * t)
                    + transverse * (amplitude * s)
                )
            )
            for t, s in zip(axial, lateral)
        ]

    def _draw_connection_symbol(
        self,
        connection: ConnectionData,
        size: float,
    ) -> None:
        """Draw a schematic connection glyph without changing FE geometry."""
        if self._model is None:
            return

        joint_types = {
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }
        external_nodes = []
        if connection.connection_type in joint_types:
            external_nodes = [
                int(tag)
                for tag in connection.parameters.get("external_nodes", ())
                if int(tag) in self._model.nodes
            ]
            if len(external_nodes) != 4:
                return
            joint_points = [
                self._model.nodes[tag].xyz
                for tag in external_nodes
            ]
            center = tuple(
                sum(float(point[index]) for point in joint_points) / 4.0
                for index in range(3)
            )
            xs = [float(point[0]) for point in joint_points]
            ys = [float(point[1]) for point in joint_points]
            x_length = max(max(xs) - min(xs), size * 1.8)
            y_length = max(max(ys) - min(ys), size * 1.8)
            thickness = max(size * 0.24, 1.0e-6)

            if connection.connection_type == "Joint2D":
                glyph = pv.Cube(
                    center=center,
                    x_length=x_length,
                    y_length=y_length,
                    z_length=thickness,
                )
                self.plotter.add_mesh(
                    glyph,
                    name=f"connection-joint2d-{connection.tag}",
                    color="#7e57c2",
                    opacity=0.26,
                    edge_color="#5e35b1",
                    show_edges=True,
                    line_width=3,
                    pickable=False,
                    render=False,
                )
                self.plotter.add_mesh(
                    pv.Sphere(
                        radius=size * 0.24,
                        center=center,
                    ),
                    name=f"connection-joint2d-center-{connection.tag}",
                    color="#5e35b1",
                    pickable=False,
                    render=False,
                )
                return

            if connection.connection_type == "BeamColumnJoint":
                points = np.asarray(joint_points, dtype=float)
                faces = np.asarray([4, 0, 1, 2, 3], dtype=np.int64)
                glyph = pv.PolyData(points, faces)
                self.plotter.add_mesh(
                    glyph,
                    name=f"connection-beam-column-joint-{connection.tag}",
                    color="#00897b",
                    opacity=0.22,
                    edge_color="#00695c",
                    show_edges=True,
                    line_width=3,
                    pickable=False,
                    render=False,
                )
                # Make the two physical opposite-node chords explicit:
                # Node 1↔3 controls joint height, Node 2↔4 controls width.
                for suffix, start, end in (
                    ("13", joint_points[0], joint_points[2]),
                    ("24", joint_points[1], joint_points[3]),
                ):
                    self.plotter.add_mesh(
                        pv.Line(start, end),
                        name=(
                            f"connection-beam-column-joint-chord-"
                            f"{suffix}-{connection.tag}"
                        ),
                        color="#00695c",
                        line_width=3,
                        pickable=False,
                        render=False,
                    )
                self.plotter.add_mesh(
                    pv.Sphere(
                        radius=size * 0.22,
                        center=center,
                    ),
                    name=f"connection-joint-center-{connection.tag}",
                    color="#00695c",
                    pickable=False,
                    render=False,
                )
                return

            if connection.connection_type == "LehighJoint2D":
                glyph = pv.Cube(
                    center=center,
                    x_length=x_length,
                    y_length=y_length,
                    z_length=thickness,
                )
                self.plotter.add_mesh(
                    glyph,
                    name=f"connection-lehigh-joint-{connection.tag}",
                    color="#3949ab",
                    opacity=0.22,
                    edge_color="#283593",
                    show_edges=True,
                    line_width=3,
                    pickable=False,
                    render=False,
                )
                self.plotter.add_mesh(
                    pv.Sphere(
                        radius=size * 0.22,
                        center=center,
                    ),
                    name=f"connection-joint-center-{connection.tag}",
                    color="#283593",
                    pickable=False,
                    render=False,
                )
                return

            glyph = pv.Cube(
                center=center,
                x_length=x_length,
                y_length=y_length,
                z_length=thickness,
            )
            self.plotter.add_mesh(
                glyph,
                name=f"connection-panel-zone-{connection.tag}",
                color="#ef6c00",
                opacity=0.20,
                edge_color="#e65100",
                show_edges=True,
                line_width=4,
                pickable=False,
                render=False,
            )
            self.plotter.add_mesh(
                pv.Sphere(
                    radius=size * 0.22,
                    center=center,
                ),
                name=f"connection-panel-zone-center-{connection.tag}",
                color="#e65100",
                pickable=False,
                render=False,
            )
            return

        if (
            connection.node_i not in self._model.nodes
            or connection.node_j not in self._model.nodes
        ):
            return

        a = self._model.nodes[connection.node_i].xyz
        b = self._model.nodes[connection.node_j].xyz
        center = tuple(
            (float(x) + float(y)) * 0.5
            for x, y in zip(a, b)
        )

        if connection.connection_type == "rigid":
            if tuple(a) != tuple(b):
                self.plotter.add_mesh(
                    pv.Line(a, b),
                    name=f"connection-rigid-line-{connection.tag}",
                    color="#37474f",
                    line_width=8,
                    render_lines_as_tubes=True,
                    pickable=False,
                    render=False,
                )
            self.plotter.add_mesh(
                pv.Cube(
                    center=center,
                    x_length=size * 0.72,
                    y_length=size * 0.72,
                    z_length=size * 0.72,
                ),
                name=f"connection-rigid-{connection.tag}",
                color="#455a64",
                edge_color="#263238",
                show_edges=True,
                pickable=False,
                render=False,
            )
            return

        if connection.connection_type == "pinned":
            self.plotter.add_mesh(
                pv.Sphere(
                    radius=size * 0.44,
                    center=center,
                    theta_resolution=14,
                    phi_resolution=10,
                ),
                name=f"connection-pin-{connection.tag}",
                color="#f5f5f5",
                edge_color="#37474f",
                show_edges=True,
                pickable=False,
                render=False,
            )
            return

        if connection.connection_type == "twoNodeLink":
            self.plotter.add_mesh(
                pv.Line(a, b),
                name=f"connection-link-{connection.tag}",
                color="#8e44ad",
                line_width=4,
                pickable=False,
                render=False,
            )
            self.plotter.add_mesh(
                pv.Sphere(
                    radius=size * 0.34,
                    center=center,
                ),
                name=f"connection-link-center-{connection.tag}",
                color="#9b59b6",
                pickable=False,
                render=False,
            )
            return

        if connection.connection_type in {"zeroLength", "semiRigid"}:
            spring = self._polyline_mesh(
                self._zero_length_spring_points(
                    center,
                    connection.orient_x,
                    size,
                )
            )
            if spring is not None:
                self.plotter.add_mesh(
                    spring,
                    name=f"connection-spring-{connection.tag}",
                    color=(
                        "#1565c0"
                        if connection.connection_type == "semiRigid"
                        else "#8e44ad"
                    ),
                    line_width=4,
                    render_lines_as_tubes=True,
                    pickable=False,
                    render=False,
                )
            self.plotter.add_mesh(
                pv.Sphere(
                    radius=size * 0.18,
                    center=center,
                ),
                name=f"connection-spring-center-{connection.tag}",
                color=(
                    "#0d47a1"
                    if connection.connection_type == "semiRigid"
                    else "#6c3483"
                ),
                pickable=False,
                render=False,
            )
            return

        # zeroLengthSection: compact joint/hinge glyph.
        self.plotter.add_mesh(
            pv.Sphere(
                radius=size * 0.58,
                center=center,
                theta_resolution=12,
                phi_resolution=8,
            ),
            name=f"connection-section-{connection.tag}",
            color="#8e44ad",
            edge_color="#5e3370",
            show_edges=True,
            pickable=False,
            render=False,
        )

    def _draw_constraint_symbol(
        self,
        constraint: ConstraintData,
        size: float,
        visible_nodes: set[int],
    ) -> None:
        """Draw retained/slave relationships for MPC-style constraints."""
        if self._model is None:
            return
        retained = int(constraint.retained_node)
        if retained not in visible_nodes or retained not in self._model.nodes:
            return

        master = self._model.nodes[retained].xyz
        if constraint.constraint_type == "rigidLink":
            color = "#34495e"
            width = 6
        elif constraint.constraint_type == "rigidDiaphragm":
            color = "#148f77"
            width = 3
        else:
            color = "#2471a3"
            width = 2

        for slave_tag in constraint.constrained_nodes:
            slave_tag = int(slave_tag)
            if (
                slave_tag not in visible_nodes
                or slave_tag not in self._model.nodes
            ):
                continue
            slave = self._model.nodes[slave_tag].xyz
            self.plotter.add_mesh(
                pv.Line(master, slave),
                name=(
                    f"constraint-{constraint.tag}-"
                    f"{retained}-{slave_tag}"
                ),
                color=color,
                line_width=width,
                pickable=False,
                render=False,
            )

        # Retained/master node marker. Slave nodes remain ordinary FE nodes;
        # this asymmetry makes the master/slave relationship readable.
        self.plotter.add_mesh(
            pv.Sphere(
                radius=size * 0.34,
                center=master,
                theta_resolution=10,
                phi_resolution=8,
            ),
            name=f"constraint-master-{constraint.tag}",
            color=color,
            edge_color="#263238",
            show_edges=True,
            pickable=False,
            render=False,
        )

    def draw_model(
        self,
        model: StructuralModel,
        connections: dict[int, ConnectionData] | None = None,
        surfaces: dict[int, SurfaceGeometryData] | None = None,
        points: dict[int, PointGeometryData] | None = None,
        lines: dict[int, LineGeometryData] | None = None,
        *,
        constraints: dict[int, ConstraintData] | None = None,
        reset_camera: bool = True,
    ) -> None:
        self._model = model
        self._connections = dict(connections or {})
        self._constraints = dict(constraints or {})
        self._surfaces = dict(surfaces or {})
        self._points = dict(points or {})
        self._lines = dict(lines or {})
        self._selected_geometry_lines.intersection_update(self._lines)
        self._selected_geometry_surfaces.intersection_update(self._surfaces)
        self._hidden_nodes.clear()
        self._hidden_elements.clear()
        self._isolate_active = False
        self._isolate_nodes.clear()
        self._isolate_elements.clear()
        self._selected_nodes.clear()
        self._selected_elements.clear()
        self._hover_ref = None
        self._last_geometry_sketch_qt_pos = None
        self._render_model(reset_camera=bool(reset_camera))

    def set_display_domain(self, domain: str) -> None:
        """Show either preprocessing Geometry or the OpenSees FE model."""
        normalized = str(domain).strip().lower()
        if normalized not in {"geometry", "fe"}:
            raise ValueError("Viewport display domain must be geometry or fe.")
        if normalized == self._display_domain:
            return
        self._display_domain = normalized
        self._selected_nodes.clear()
        self._selected_elements.clear()
        self._hover_ref = None
        self._left_press_pos = None
        self._right_press_pos = None
        self._last_geometry_sketch_qt_pos = None
        if normalized != "geometry":
            self.clear_geometry_sketch_preview(render=False)
        self._render_model(reset_camera=True)

    def set_geometry_line_selection(
        self,
        line_tags,
    ) -> None:
        self._selected_geometry_lines = {
            int(tag)
            for tag in line_tags
            if int(tag) in self._lines
        }
        if self._display_domain == "geometry":
            self._update_highlight_overlays()

    def set_geometry_surface_selection(
        self,
        surface_tags,
    ) -> None:
        self._selected_geometry_surfaces = {
            int(tag)
            for tag in surface_tags
            if int(tag) in self._surfaces
        }
        if self._display_domain == "geometry":
            self._update_highlight_overlays()

    def show_line_mesh_preview(
        self,
        line_tag: int,
        points,
        *,
        family: str = "Frame",
    ) -> None:
        tag = int(line_tag)
        coords = [
            tuple(float(value) for value in point)
            for point in points
        ]
        if len(coords) < 2:
            raise ValueError(
                "Line mesh preview requires at least two points."
            )
        if any(len(point) != 3 for point in coords):
            raise ValueError(
                "Line mesh preview points require three coordinates."
            )
        self._line_mesh_preview = (
            tag,
            coords,
            str(family),
        )
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_line_mesh_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._line_mesh_preview = None
        self._remove_overlay("line-mesh-preview")
        self._remove_overlay("line-mesh-preview-nodes")
        self._remove_overlay("line-mesh-preview-label")
        if render:
            self.plotter.render()

    def _render_line_mesh_preview(self) -> None:
        if (
            self._display_domain != "geometry"
            or self._line_mesh_preview is None
        ):
            return
        line_tag, coords, family = self._line_mesh_preview
        if line_tag not in self._lines or len(coords) < 2:
            return
        array = np.asarray(coords, dtype=float)
        mesh = pv.lines_from_points(array, close=False)
        self.plotter.add_mesh(
            mesh,
            name="line-mesh-preview",
            color="#8a2be2",
            line_width=3.0,
            render_lines_as_tubes=False,
            pickable=False,
            render=False,
        )
        self.plotter.add_mesh(
            pv.PolyData(array),
            name="line-mesh-preview-nodes",
            color="#8a2be2",
            render_points_as_spheres=True,
            point_size=10,
            pickable=False,
            render=False,
        )
        midpoint = array[len(array) // 2]
        self._add_annotation_labels(
            [midpoint],
            [
                f"L{line_tag} · {family} · "
                f"{len(coords) - 1} element(s)"
            ],
            name="line-mesh-preview-label",
            text_color="#63308f",
            font_size=10,
            always_visible=True,
        )

    def show_line_intersection_preview(
        self,
        intersections,
    ) -> None:
        preview: list[
            tuple[
                tuple[float, float, float],
                str,
                tuple[int, int],
            ]
        ] = []
        for item in intersections:
            point = tuple(float(value) for value in item.point)
            if len(point) != 3:
                continue
            preview.append(
                (
                    point,
                    str(item.kind),
                    (
                        int(item.line_tags[0]),
                        int(item.line_tags[1]),
                    ),
                )
            )
        self._line_intersection_preview = preview
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_line_intersection_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._line_intersection_preview = []
        self._remove_overlay("line-intersection-preview")
        self._remove_overlay("line-intersection-preview-label")
        if render:
            self.plotter.render()

    def _render_line_intersection_preview(self) -> None:
        if (
            self._display_domain != "geometry"
            or not self._line_intersection_preview
        ):
            return
        points = [
            item[0]
            for item in self._line_intersection_preview
        ]
        array = np.asarray(points, dtype=float)
        self.plotter.add_mesh(
            pv.PolyData(array),
            name="line-intersection-preview",
            color="#d64b4b",
            render_points_as_spheres=True,
            point_size=16,
            pickable=False,
            render=False,
        )
        labels = [
            (
                f"{kind} · L{line_tags[0]}/L{line_tags[1]}"
            )
            for _point, kind, line_tags
            in self._line_intersection_preview
        ]
        self._add_annotation_labels(
            points,
            labels,
            name="line-intersection-preview-label",
            text_color="#8f2d2d",
            font_size=10,
            always_visible=True,
        )

    def show_surface_mesh_definition_preview(
        self,
        surface: SurfaceGeometryData,
    ) -> None:
        """Preview a transient Surface mesh definition without FE mutation."""
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
        self._remove_overlay("surface-mesh-preview")
        _nu, _nv, segments = surface_mesh_preview_segments(surface)
        if not segments:
            self.plotter.render()
            return
        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        for start, end in segments:
            base = len(points)
            points.extend((start, end))
            lines.extend((2, base, base + 1))
        mesh = pv.PolyData(
            np.asarray(points, dtype=float),
            lines=np.asarray(lines, dtype=np.int64),
            deep=True,
        )
        self.plotter.add_mesh(
            mesh,
            name="surface-mesh-preview",
            color="#8a2be2",
            line_width=2.4,
            render_lines_as_tubes=False,
            pickable=False,
            render=False,
        )
        self.plotter.render()

    def show_surface_mesh_preview(
        self,
        surface_tags,
    ) -> None:
        self._surface_mesh_preview_tags = {
            int(tag)
            for tag in surface_tags
            if int(tag) in self._surfaces
        }
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_surface_mesh_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._surface_mesh_preview_tags.clear()
        self._remove_overlay("surface-mesh-preview")
        if render:
            self.plotter.render()

    def show_surface_mesh_quality(
        self,
        surface_tags,
        metric: str,
    ) -> None:
        metric_key = str(metric).strip().lower()
        if metric_key not in {"aspect_ratio", "skew", "warpage"}:
            raise ValueError(
                "Surface quality metric must be aspect_ratio, skew, or warpage."
            )
        self._surface_quality_tags = {
            int(tag)
            for tag in surface_tags
            if int(tag) in self._surfaces
        }
        self._surface_quality_metric = metric_key
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_surface_mesh_quality(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._surface_quality_tags.clear()
        self._surface_quality_metric = None
        self._remove_overlay("surface-quality-overlay")
        if render:
            self.plotter.render()

    def _render_surface_quality_overlay(self) -> None:
        self._remove_overlay("surface-quality-overlay")
        if (
            self._model is None
            or self._display_domain != "geometry"
            or not self._surface_quality_tags
            or self._surface_quality_metric is None
        ):
            return

        element_tags = sorted({
            int(element_tag)
            for surface_tag in self._surface_quality_tags
            for element_tag in self._surfaces[
                surface_tag
            ].generated_element_tags
            if (
                surface_tag in self._surfaces
                and int(element_tag) in self._model.elements
                and self._model.elements[
                    int(element_tag)
                ].element_type in SHELL_ELEMENT_TYPES
            )
        })
        if not element_tags:
            return
        mesh = self._batched_shell_mesh(
            self._model,
            element_tags,
        )
        if mesh is None:
            return

        values: dict[int, float] = {}
        for tag in element_tags:
            quality = shell_element_quality_from_model(
                self._model,
                tag,
            )
            if self._surface_quality_metric == "aspect_ratio":
                values[tag] = float(quality.aspect_ratio)
            elif self._surface_quality_metric == "skew":
                values[tag] = float(quality.max_skew_deg)
            else:
                values[tag] = float(quality.warpage_deg)

        cell_tags = np.asarray(
            mesh.cell_data["element_tag"],
            dtype=np.int64,
        )
        scalars = np.asarray(
            [values.get(int(tag), float("nan")) for tag in cell_tags],
            dtype=float,
        )
        mesh.cell_data["surface_quality"] = scalars
        title = {
            "aspect_ratio": "Aspect ratio",
            "skew": "Skew [deg]",
            "warpage": "Warpage [deg]",
        }[self._surface_quality_metric]
        self.plotter.add_mesh(
            mesh,
            name="surface-quality-overlay",
            scalars="surface_quality",
            cmap="viridis",
            show_edges=True,
            edge_color="#243b52",
            line_width=1,
            opacity=0.9,
            pickable=False,
            scalar_bar_args={"title": title},
            render=False,
        )

    def show_surface_pressure_preview(
        self,
        surface_tags,
        pressure: float,
    ) -> None:
        value = float(pressure)
        if not math.isfinite(value):
            raise ValueError("Preview pressure must be finite.")
        self._surface_pressure_preview_tags = {
            int(tag)
            for tag in surface_tags
            if int(tag) in self._surfaces
        }
        self._surface_pressure_preview_value = value
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_surface_pressure_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._surface_pressure_preview_tags.clear()
        self._surface_pressure_preview_value = None
        self._remove_overlay("surface-pressure-preview")
        self._remove_overlay("surface-pressure-preview-labels")
        if render:
            self.plotter.render()

    def _render_surface_pressure_preview(self) -> None:
        self._remove_overlay("surface-pressure-preview")
        self._remove_overlay("surface-pressure-preview-labels")
        if (
            self._display_domain != "geometry"
            or not self._surface_pressure_preview_tags
            or self._surface_pressure_preview_value is None
        ):
            return

        pressure = float(self._surface_pressure_preview_value)
        sign = 1.0 if pressure >= 0.0 else -1.0
        records = []
        label_points = []
        label_texts = []
        for tag in sorted(self._surface_pressure_preview_tags):
            surface = self._surfaces.get(tag)
            if surface is None:
                continue
            axes = self._surface_axes(surface)
            if axes is None:
                continue
            center, _x, _y, normal, scale = axes
            direction = normal * sign
            records.append((center, direction, scale * 0.9))
            label_points.append(
                center + direction * scale * 1.05
            )
            label_texts.append(
                f"S{tag}: p={pressure:.4g} "
                + ("(+N)" if pressure >= 0.0 else "(-N)")
            )

        mesh = self._batched_arrow_mesh(records)
        if mesh is not None:
            self.plotter.add_mesh(
                mesh,
                name="surface-pressure-preview",
                color="#b03a2e",
                pickable=False,
                render=False,
            )
        if label_points:
            self._add_annotation_labels(
                label_points,
                label_texts,
                name="surface-pressure-preview-labels",
                text_color="#7a251d",
                font_size=10,
                always_visible=True,
            )

    def show_surface_edge_preview(self, edge_refs) -> None:
        refs: set[tuple[int, int]] = set()
        for surface_tag, edge_index in edge_refs:
            tag = int(surface_tag)
            edge = int(edge_index)
            if tag not in self._surfaces:
                continue
            if edge not in {1, 2, 3, 4}:
                raise ValueError(
                    "Surface edge preview index must be 1, 2, 3, or 4."
                )
            refs.add((tag, edge))
        self._surface_edge_preview_refs = refs
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_surface_edge_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._surface_edge_preview_refs.clear()
        self._remove_overlay("surface-edge-preview")
        self._remove_overlay("surface-edge-preview-labels")
        if render:
            self.plotter.render()

    def _render_surface_edge_preview(self) -> None:
        self._remove_overlay("surface-edge-preview")
        self._remove_overlay("surface-edge-preview-labels")
        if (
            self._display_domain != "geometry"
            or not self._surface_edge_preview_refs
        ):
            return

        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        label_points = []
        label_texts = []
        for surface_tag, edge_index in sorted(
            self._surface_edge_preview_refs
        ):
            surface = self._surfaces.get(surface_tag)
            if surface is None:
                continue
            p = surface.points
            edge_points = {
                1: (p[0], p[1]),
                2: (p[1], p[2]),
                3: (p[2], p[3]),
                4: (p[3], p[0]),
            }
            start, end = edge_points[edge_index]
            base = len(points)
            points.extend((start, end))
            lines.extend((2, base, base + 1))
            label_points.append(
                tuple(
                    0.5 * (float(start[i]) + float(end[i]))
                    for i in range(3)
                )
            )
            label_texts.append(f"S{surface_tag}:E{edge_index}")

        if points:
            mesh = pv.PolyData(
                np.asarray(points, dtype=float),
                lines=np.asarray(lines, dtype=np.int64),
                deep=True,
            )
            self.plotter.add_mesh(
                mesh,
                name="surface-edge-preview",
                color="#ff7f0e",
                line_width=5.0,
                render_lines_as_tubes=False,
                pickable=False,
                render=False,
            )
        if label_points:
            self._add_annotation_labels(
                label_points,
                label_texts,
                name="surface-edge-preview-labels",
                text_color="#9a4d00",
                font_size=11,
                always_visible=True,
            )

    def show_surface_edge_load_preview(
        self,
        surface_tag: int,
        edge_index: int,
        values_per_length,
    ) -> None:
        tag = int(surface_tag)
        edge = int(edge_index)
        if tag not in self._surfaces:
            raise ValueError(f"Surface {tag} does not exist.")
        if edge not in {1, 2, 3, 4}:
            raise ValueError(
                "Surface edge load preview index must be 1, 2, 3, or 4."
            )
        values = tuple(float(value) for value in values_per_length)
        if len(values) != 6 or any(
            not math.isfinite(value) for value in values
        ):
            raise ValueError(
                "Surface edge load preview needs six finite components."
            )
        self._surface_edge_load_preview = (
            tag,
            edge,
            values,  # type: ignore[arg-type]
        )
        self._surface_edge_preview_refs = {(tag, edge)}
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_model(reset_camera=False)

    def clear_surface_edge_load_preview(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._surface_edge_load_preview = None
        self._remove_overlay("surface-edge-load-preview")
        self._remove_overlay("surface-edge-load-preview-labels")
        if render:
            self.plotter.render()

    def _render_surface_edge_load_preview(self) -> None:
        self._remove_overlay("surface-edge-load-preview")
        self._remove_overlay("surface-edge-load-preview-labels")
        if (
            self._display_domain != "geometry"
            or self._surface_edge_load_preview is None
        ):
            return

        surface_tag, edge_index, values = self._surface_edge_load_preview
        surface = self._surfaces.get(surface_tag)
        if surface is None:
            return
        p = surface.points
        start, end = {
            1: (p[0], p[1]),
            2: (p[1], p[2]),
            3: (p[2], p[3]),
            4: (p[3], p[0]),
        }[edge_index]
        a = np.asarray(start, dtype=float)
        b = np.asarray(end, dtype=float)
        edge_vector = b - a
        edge_length = float(np.linalg.norm(edge_vector))
        if edge_length <= 1.0e-12:
            return

        q = np.asarray(values[:3], dtype=float)
        q_norm = float(np.linalg.norm(q))
        records = []
        direction = None
        if q_norm > 1.0e-15:
            direction = q / q_norm
            arrow_length = max(edge_length * 0.12, 1.0e-9)
            for t in np.linspace(0.1, 0.9, 5):
                point = a + float(t) * edge_vector
                records.append((point, direction, arrow_length))

        mesh = self._batched_arrow_mesh(records)
        if mesh is not None:
            self.plotter.add_mesh(
                mesh,
                name="surface-edge-load-preview",
                color="#b03a2e",
                pickable=False,
                render=False,
            )

        midpoint = 0.5 * (a + b)
        label_point = midpoint
        if direction is not None:
            label_point = midpoint + direction * edge_length * 0.16
        self._add_annotation_labels(
            [label_point],
            [
                f"S{surface_tag}:E{edge_index} "
                f"q=({values[0]:.4g}, {values[1]:.4g}, {values[2]:.4g}) "
                f"m=({values[3]:.4g}, {values[4]:.4g}, {values[5]:.4g})"
            ],
            name="surface-edge-load-preview-labels",
            text_color="#7a251d",
            font_size=10,
            always_visible=True,
        )

    def set_geometry_mesh_overlay_visible(
        self,
        visible: bool,
    ) -> None:
        """Toggle a non-pickable Shell FE wireframe over Geometry mode."""
        value = bool(visible)
        if value == self._geometry_mesh_overlay_visible:
            return
        self._geometry_mesh_overlay_visible = value
        if self._display_domain == "geometry":
            self._render_model(reset_camera=False)

    def geometry_mesh_overlay_visible(self) -> bool:
        return bool(self._geometry_mesh_overlay_visible)

    def clear_surface_orientation(
        self,
        *,
        render: bool = True,
    ) -> None:
        self._surface_orientation_tags.clear()
        for name in (
            "surface-axis-x",
            "surface-axis-y",
            "surface-axis-n",
        ):
            self._remove_overlay(name)
        if render:
            self.plotter.render()

    def show_surface_orientation(
        self,
        surface_tags,
    ) -> None:
        self._surface_orientation_tags = {
            int(tag)
            for tag in surface_tags
            if int(tag) in self._surfaces
        }
        if self._display_domain != "geometry":
            self.set_display_domain("geometry")
            return
        self._render_surface_orientation_overlays()
        self.plotter.render()

    @staticmethod
    def _surface_axes(surface):
        points = np.asarray(surface.points, dtype=float)
        if points.shape != (4, 3):
            return None
        center = points.mean(axis=0)

        normal = np.zeros(3, dtype=float)
        for index in range(4):
            current = points[index]
            following = points[(index + 1) % 4]
            normal += np.asarray((
                (current[1] - following[1])
                * (current[2] + following[2]),
                (current[2] - following[2])
                * (current[0] + following[0]),
                (current[0] - following[0])
                * (current[1] + following[1]),
            ))
        norm_n = float(np.linalg.norm(normal))
        if norm_n <= 1.0e-12:
            return None
        normal /= norm_n

        if getattr(surface, "local_x", None) is not None:
            local_x = np.asarray(surface.local_x, dtype=float)
        else:
            local_x = points[1] - points[0]
        local_x = local_x - normal * float(np.dot(local_x, normal))
        norm_x = float(np.linalg.norm(local_x))
        if norm_x <= 1.0e-12:
            local_x = points[3] - points[0]
            local_x = local_x - normal * float(np.dot(local_x, normal))
            norm_x = float(np.linalg.norm(local_x))
        if norm_x <= 1.0e-12:
            return None
        local_x /= norm_x
        local_y = np.cross(normal, local_x)
        norm_y = float(np.linalg.norm(local_y))
        if norm_y <= 1.0e-12:
            return None
        local_y /= norm_y

        edge_lengths = [
            float(np.linalg.norm(points[(i + 1) % 4] - points[i]))
            for i in range(4)
        ]
        scale = max(min(edge_lengths), 1.0e-6) * 0.28
        return center, local_x, local_y, normal, scale

    def _render_surface_orientation_overlays(self) -> None:
        for name in (
            "surface-axis-x",
            "surface-axis-y",
            "surface-axis-n",
        ):
            self._remove_overlay(name)
        if (
            self._display_domain != "geometry"
            or not self._surface_orientation_tags
        ):
            return

        x_records = []
        y_records = []
        n_records = []
        for tag in sorted(self._surface_orientation_tags):
            surface = self._surfaces.get(tag)
            if surface is None:
                continue
            axes = self._surface_axes(surface)
            if axes is None:
                continue
            center, local_x, local_y, normal, scale = axes
            x_records.append((center, local_x, scale))
            y_records.append((center, local_y, scale))
            n_records.append((center, normal, scale))

        for name, records, color in (
            ("surface-axis-x", x_records, "#d62728"),
            ("surface-axis-y", y_records, "#2ca02c"),
            ("surface-axis-n", n_records, "#1f77b4"),
        ):
            mesh = self._batched_arrow_mesh(records)
            if mesh is None:
                continue
            self.plotter.add_mesh(
                mesh,
                name=name,
                color=color,
                pickable=False,
                render=False,
            )

    def _render_model(self, *, reset_camera: bool) -> None:
        preserved_camera = None
        if not reset_camera:
            try:
                preserved_camera = self.plotter.camera_position
            except Exception:
                preserved_camera = None

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
        self._geometry_point_actor = None
        self._geometry_point_tags = []
        self._geometry_line_actor = None
        self._geometry_line_mesh = None
        self._geometry_line_tags = []
        self._geometry_surface_actor = None
        self._geometry_surface_mesh = None
        self._geometry_surface_tags = []
        self._element_actor_data.clear()
        self._undeformed_element_actors.clear()
        self._navigation_proxy_actor = None
        self._navigation_lod_enabled = False
        self._undeformed_model_visible = True

        # Persistent world-space origin reference. Unlike the orientation
        # cube, this triad sits at the model's actual global (0, 0, 0).
        self._render_origin_axes()

        # The sketch grid is viewport state, not model geometry. Rebuild it
        # after plotter.clear() so committing a Line/Surface never hides it.
        if self._display_domain != "fe":
            self._render_geometry_sketch_grid()

        if self._model is None:
            if preserved_camera is not None:
                self.plotter.camera_position = preserved_camera
            self.plotter.render()
            return
        if (
            not self._model.nodes
            and not self._points
            and not self._lines
            and not self._surfaces
        ):
            if preserved_camera is not None:
                self.plotter.camera_position = preserved_camera
            elif reset_camera and self._origin_axes_visible:
                self.plotter.reset_camera()
                self.plotter.camera.zoom(1.15)
            self.plotter.render()
            return

        if self._display_domain == "geometry":
            self._update_model_color_legend([])
            self._cell_picker.InitializePickList()
            self._cell_picker.PickFromListOn()
            self._point_picker.InitializePickList()
            self._point_picker.PickFromListOn()

            if self._points:
                self._geometry_point_tags = sorted(self._points)
                geometry_points = np.asarray(
                    [
                        self._points[tag].xyz
                        for tag in self._geometry_point_tags
                    ],
                    dtype=float,
                )
                self._geometry_point_actor = self.plotter.add_mesh(
                    pv.PolyData(geometry_points),
                    name="geometry-points",
                    color="#d9892b",
                    render_points_as_spheres=True,
                    point_size=10,
                    opacity=0.95,
                    pickable=True,
                    render=False,
                )
                self._point_picker.AddPickList(
                    self._geometry_point_actor
                )

            line_points: list[tuple[float, float, float]] = []
            line_cells: list[int] = []
            self._geometry_line_tags = []
            for line_tag in sorted(self._lines):
                line = self._lines[line_tag]
                point_i = self._points.get(line.point_i)
                point_j = self._points.get(line.point_j)
                if point_i is None or point_j is None:
                    continue
                base = len(line_points)
                line_points.extend((point_i.xyz, point_j.xyz))
                line_cells.extend((2, base, base + 1))
                self._geometry_line_tags.append(int(line_tag))

            if line_points:
                self._geometry_line_mesh = pv.PolyData(
                    np.asarray(line_points, dtype=float),
                    lines=np.asarray(line_cells, dtype=np.int64),
                    deep=True,
                )
                self._geometry_line_mesh.cell_data["line_tag"] = np.asarray(
                    self._geometry_line_tags,
                    dtype=np.int64,
                )
                self._geometry_line_actor = self.plotter.add_mesh(
                    self._geometry_line_mesh,
                    name="line-geometry",
                    color="#d9892b",
                    line_width=5,
                    render_lines_as_tubes=True,
                    opacity=0.95,
                    pickable=True,
                    render=False,
                )
                self._cell_picker.AddPickList(
                    self._geometry_line_actor
                )

            surface_points: list[tuple[float, float, float]] = []
            surface_faces: list[int] = []
            self._geometry_surface_tags = []
            for surface_tag in sorted(self._surfaces):
                surface = self._surfaces[surface_tag]
                points = [
                    tuple(float(value) for value in point)
                    for point in surface.points
                ]
                if len(points) != 4:
                    continue
                base = len(surface_points)
                surface_points.extend(points)
                surface_faces.extend(
                    (4, base, base + 1, base + 2, base + 3)
                )
                self._geometry_surface_tags.append(int(surface_tag))

            if surface_points:
                self._geometry_surface_mesh = pv.PolyData(
                    np.asarray(surface_points, dtype=float),
                    faces=np.asarray(surface_faces, dtype=np.int64),
                    deep=True,
                )
                self._geometry_surface_mesh.cell_data[
                    "surface_tag"
                ] = np.asarray(
                    self._geometry_surface_tags,
                    dtype=np.int64,
                )
                self._geometry_surface_actor = self.plotter.add_mesh(
                    self._geometry_surface_mesh,
                    name="surface-geometry",
                    color="#6aaed6",
                    edge_color="#1f6f9f",
                    show_edges=True,
                    line_width=2,
                    opacity=0.24,
                    smooth_shading=False,
                    pickable=True,
                    render=False,
                )
                self._cell_picker.AddPickList(
                    self._geometry_surface_actor
                )

            self._render_line_mesh_preview()
            self._render_line_intersection_preview()
            self._render_geometry_sketch_preview(render=False)

            if self._surface_mesh_preview_tags:
                preview_points: list[tuple[float, float, float]] = []
                preview_lines: list[int] = []
                for surface_tag in sorted(
                    self._surface_mesh_preview_tags
                ):
                    surface = self._surfaces.get(surface_tag)
                    if surface is None:
                        continue
                    _nu, _nv, segments = surface_mesh_preview_segments(
                        surface
                    )
                    for start, end in segments:
                        base = len(preview_points)
                        preview_points.extend((start, end))
                        preview_lines.extend((2, base, base + 1))
                if preview_points:
                    preview = pv.PolyData(
                        np.asarray(preview_points, dtype=float),
                        lines=np.asarray(preview_lines, dtype=np.int64),
                        deep=True,
                    )
                    self.plotter.add_mesh(
                        preview,
                        name="surface-mesh-preview",
                        color="#8a2be2",
                        line_width=2.2,
                        render_lines_as_tubes=False,
                        pickable=False,
                        render=False,
                    )

            if self._geometry_mesh_overlay_visible:
                shell_tags = sorted({
                    int(element_tag)
                    for surface in self._surfaces.values()
                    for element_tag in surface.generated_element_tags
                    if (
                        int(element_tag) in self._model.elements
                        and self._model.elements[
                            int(element_tag)
                        ].element_type in SHELL_ELEMENT_TYPES
                    )
                })
                mesh = self._batched_shell_mesh(
                    self._model,
                    shell_tags,
                )
                if mesh is not None:
                    self.plotter.add_mesh(
                        mesh,
                        name="geometry-shell-mesh-overlay",
                        style="wireframe",
                        color="#40586f",
                        line_width=1.4,
                        opacity=0.72,
                        pickable=False,
                        render=False,
                    )

            self._update_highlight_overlays(render=False)
            self._render_surface_quality_overlay()
            self._render_surface_pressure_preview()
            self._render_surface_edge_preview()
            self._render_surface_edge_load_preview()
            self._render_surface_orientation_overlays()
            if preserved_camera is not None:
                self.plotter.camera_position = preserved_camera
            else:
                self.set_view(self._current_view, render=False)
                if reset_camera:
                    self.plotter.reset_camera()
                    self.plotter.camera.zoom(1.18)
            self.plotter.render()
            return

        if not self._model.nodes:
            self._update_model_color_legend([])
            if preserved_camera is not None:
                self.plotter.camera_position = preserved_camera
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
                    or (
                        group_name != "reinforcement"
                        and self._model_representation == "tube"
                    )
                ),
                line_width=(
                    5
                    if group_name == "reinforcement"
                    else 3
                    if self._model_representation == "centerline"
                    else 1
                ),
                render_lines_as_tubes=(
                    group_name == "reinforcement"
                    or self._model_representation == "centerline"
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
            self._draw_support_symbol(
                classify_fixity(node.fixity),
                node.xyz,
                support_size,
            )

        visible_node_set = set(visible_nodes)
        connection_size = max(span * 0.012, 0.06)
        for connection in self._connections.values():
            if (
                connection.node_i not in visible_node_set
                or connection.node_j not in visible_node_set
            ):
                continue
            self._draw_connection_symbol(connection, connection_size)

        constraint_size = max(span * 0.011, 0.055)
        for constraint in self._constraints.values():
            self._draw_constraint_symbol(
                constraint,
                constraint_size,
                visible_node_set,
            )

        self._update_highlight_overlays(render=False)
        self._update_display_overlays(render=False)
        if preserved_camera is not None:
            self.plotter.camera_position = preserved_camera
        else:
            self.set_view(self._current_view, render=False)
            if reset_camera:
                self.plotter.reset_camera()
                self.plotter.camera.zoom(1.28)
        self.plotter.render()

    def pick_entity(self, x: int, y: int) -> tuple[str, int] | None:
        renderer = self.plotter.renderer

        if self._display_domain == "geometry":
            if self._geometry_point_actor is not None:
                if self._point_picker.Pick(x, y, 0, renderer):
                    actor = self._point_picker.GetActor()
                    point_id = self._point_picker.GetPointId()
                    if (
                        self._actor_key(actor)
                        == self._actor_key(self._geometry_point_actor)
                        and 0 <= point_id < len(self._geometry_point_tags)
                    ):
                        return (
                            "geometry_point",
                            int(self._geometry_point_tags[point_id]),
                        )
            if self._geometry_line_actor is not None:
                if self._cell_picker.Pick(x, y, 0, renderer):
                    actor = self._cell_picker.GetActor()
                    cell_id = self._cell_picker.GetCellId()
                    if (
                        self._actor_key(actor)
                        == self._actor_key(self._geometry_line_actor)
                        and 0 <= cell_id < len(self._geometry_line_tags)
                    ):
                        return (
                            "geometry_line",
                            int(self._geometry_line_tags[cell_id]),
                        )
            if self._geometry_surface_actor is not None:
                if self._cell_picker.Pick(x, y, 0, renderer):
                    actor = self._cell_picker.GetActor()
                    cell_id = self._cell_picker.GetCellId()
                    if (
                        self._actor_key(actor)
                        == self._actor_key(self._geometry_surface_actor)
                        and 0 <= cell_id < len(self._geometry_surface_tags)
                    ):
                        return (
                            "geometry_surface",
                            int(self._geometry_surface_tags[cell_id]),
                        )
            return None

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

    def _geometry_line_overlay_mesh(self, tags: set[int]):
        if (
            not tags
            or self._geometry_line_mesh is None
            or not self._geometry_line_tags
        ):
            return None
        ids = [
            index
            for index, tag in enumerate(self._geometry_line_tags)
            if int(tag) in tags
        ]
        if not ids:
            return None
        return self._geometry_line_mesh.extract_cells(
            np.asarray(ids, dtype=np.int64)
        )

    def _geometry_surface_overlay_mesh(self, tags: set[int]):
        if (
            not tags
            or self._geometry_surface_mesh is None
            or not self._geometry_surface_tags
        ):
            return None
        ids = [
            index
            for index, tag in enumerate(self._geometry_surface_tags)
            if int(tag) in tags
        ]
        if not ids:
            return None
        return self._geometry_surface_mesh.extract_cells(
            np.asarray(ids, dtype=np.int64)
        )

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
            "selection-connections",
            "selection-zero-connections",
            "selection-nodes",
            "hover-element",
            "hover-node",
            "selection-geometry-lines",
            "hover-geometry-line",
            "selection-geometry-surfaces",
            "hover-geometry-surface",
        ):
            self._remove_overlay(name)

        if self._model is None:
            return

        if self._display_domain == "geometry":
            selected_line_mesh = self._geometry_line_overlay_mesh(
                self._selected_geometry_lines
            )
            if selected_line_mesh is not None:
                self.plotter.add_mesh(
                    selected_line_mesh,
                    name="selection-geometry-lines",
                    color="#ff9800",
                    line_width=8,
                    render_lines_as_tubes=True,
                    opacity=1.0,
                    pickable=False,
                    render=False,
                )
            if (
                self._hover_ref
                and self._hover_ref[0] == "geometry_line"
                and self._hover_ref[1]
                not in self._selected_geometry_lines
            ):
                hover_line = self._geometry_line_overlay_mesh(
                    {int(self._hover_ref[1])}
                )
                if hover_line is not None:
                    self.plotter.add_mesh(
                        hover_line,
                        name="hover-geometry-line",
                        color="#20c5e8",
                        line_width=8,
                        render_lines_as_tubes=True,
                        opacity=0.92,
                        pickable=False,
                        render=False,
                    )
            selected_surface_mesh = self._geometry_surface_overlay_mesh(
                self._selected_geometry_surfaces
            )
            if selected_surface_mesh is not None:
                self.plotter.add_mesh(
                    selected_surface_mesh,
                    name="selection-geometry-surfaces",
                    color="#ff9800",
                    edge_color="#c75f00",
                    show_edges=True,
                    line_width=4,
                    opacity=0.42,
                    pickable=False,
                    render=False,
                )
            if (
                self._hover_ref
                and self._hover_ref[0] == "geometry_surface"
                and self._hover_ref[1]
                not in self._selected_geometry_surfaces
            ):
                hover_surface = self._geometry_surface_overlay_mesh(
                    {int(self._hover_ref[1])}
                )
                if hover_surface is not None:
                    self.plotter.add_mesh(
                        hover_surface,
                        name="hover-geometry-surface",
                        color="#20c5e8",
                        edge_color="#087a94",
                        show_edges=True,
                        line_width=3,
                        opacity=0.34,
                        pickable=False,
                        render=False,
                    )
            if render:
                self.plotter.render()
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

        # Connection tags share the FE element tag namespace, but are stored
        # separately from StructuralModel.elements. Highlight them explicitly.
        selected_connection_tags = sorted(
            set(self._selected_elements) & set(self._connections)
        )
        connection_line_points: list[tuple[float, float, float]] = []
        connection_line_cells: list[int] = []
        zero_connection_points: list[tuple[float, float, float]] = []
        for tag in selected_connection_tags:
            connection = self._connections[tag]
            if (
                connection.node_i not in self._model.nodes
                or connection.node_j not in self._model.nodes
            ):
                continue
            a = self._model.nodes[connection.node_i].xyz
            b = self._model.nodes[connection.node_j].xyz
            if connection.connection_type == "twoNodeLink":
                start = len(connection_line_points)
                connection_line_points.extend((a, b))
                connection_line_cells.extend((2, start, start + 1))
            else:
                zero_connection_points.append(tuple(
                    (float(x) + float(y)) * 0.5
                    for x, y in zip(a, b)
                ))

        if connection_line_points:
            link_overlay = pv.PolyData(
                np.asarray(connection_line_points, dtype=float)
            )
            link_overlay.lines = np.asarray(
                connection_line_cells,
                dtype=np.int64,
            )
            self.plotter.add_mesh(
                link_overlay,
                name="selection-connections",
                color="#ff9800",
                line_width=9,
                render_lines_as_tubes=True,
                pickable=False,
                render=False,
            )
        if zero_connection_points:
            self.plotter.add_mesh(
                pv.PolyData(zero_connection_points),
                name="selection-zero-connections",
                color="#ff9800",
                render_points_as_spheres=True,
                point_size=16,
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
            "display-mass-points",
            "display-mass-labels",
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
            text_color=(
                "#63b3ff"
                if self._background_is_dark()
                else "#0b5cad"
            ),
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
            text_color=(
                "#ffb15c"
                if self._background_is_dark()
                else "#7a3d00"
            ),
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

    def _draw_masses(self) -> None:
        """Draw a dedicated FE mass overlay without treating mass as a load."""
        if self._model is None:
            return

        visible_nodes = self._visible_node_tags()
        visible_elements = self._visible_element_tags()
        mass_points: list[tuple[float, float, float]] = []
        label_points: list[tuple[float, float, float]] = []
        labels: list[str] = []

        for tag in sorted(visible_nodes):
            node = self._model.nodes.get(tag)
            if (
                node is None
                or not any(abs(float(value)) > 0.0 for value in node.mass)
            ):
                continue
            xyz = tuple(float(value) for value in node.xyz)
            mass_points.append(xyz)
            label_points.append(xyz)
            labels.append("M")

        for tag in sorted(visible_elements):
            element = self._model.elements.get(tag)
            if element is None or float(element.mass_per_length) <= 0.0:
                continue
            nodes = [
                self._model.nodes.get(node_tag)
                for node_tag in element.node_tags()
            ]
            if not nodes or any(node is None for node in nodes):
                continue
            center = tuple(
                sum(
                    float(node.xyz[index])
                    for node in nodes
                    if node is not None
                ) / len(nodes)
                for index in range(3)
            )
            label_points.append(center)
            labels.append("ρL")

        if mass_points:
            cloud = pv.PolyData(np.asarray(mass_points, dtype=float))
            self.plotter.add_mesh(
                cloud,
                name="display-mass-points",
                color="#6f4aa8",
                point_size=15,
                render_points_as_spheres=True,
                pickable=False,
                render=False,
            )

        if label_points:
            self._add_annotation_labels(
                label_points,
                labels,
                name="display-mass-labels",
                text_color="#5b3b8c",
                font_size=11,
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
        *,
        end: bool = False,
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
            if load.load_type in {"Uniform", "Triangular", "Trapezoidal"}:
                values = (
                    (load.wx_end, load.wy_end, load.wz_end)
                    if end and load.load_type in {"Triangular", "Trapezoidal"}
                    else (load.wx, load.wy, load.wz)
                )
                prefix = "w"
            elif load.load_type == "Point":
                values = (load.px, load.py, load.pz)
                prefix = "P"
            else:
                values = None
                prefix = "w"

            if values is not None and load.coordinate_system == "global":
                return np.asarray(values, dtype=float), prefix

            local_x, local_y, local_z = element_local_axes(
                self._model,
                element,
                transformation,
            )
            if values is not None:
                local = values
            else:
                local = resolve_self_weight_local(
                    load,
                    self._model,
                    self._sections,
                    self._materials,
                    self._transformations,
                    self._units,
                )
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
        variable_types = {"Triangular", "Trapezoidal"}
        for load in self._element_loads.values():
            if load.element_tag not in visible_elements:
                continue
            element = self._model.elements.get(load.element_tag)
            if element is None:
                continue
            end_vector = None
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
            elif load.load_type in variable_types:
                resolved = self._element_load_global_vector(load)
                resolved_end = self._element_load_global_vector(load, end=True)
                if resolved is None or resolved_end is None:
                    continue
                vector, prefix = resolved
                end_vector, _ = resolved_end
                magnitude = max(
                    self._vector_norm(vector),
                    self._vector_norm(end_vector),
                )
            else:
                resolved = self._element_load_global_vector(load)
                if resolved is None:
                    continue
                vector, prefix = resolved
                magnitude = self._vector_norm(vector)
            max_magnitude = max(max_magnitude, magnitude)
            entries.append(
                (load, element, vector, end_vector, prefix, magnitude)
            )

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

        for load, element, vector, end_vector, prefix, magnitude in entries:
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

            if load.load_type in variable_types:
                a = min(max(float(load.a_over_l), 0.0), 1.0)
                b = min(max(float(load.b_over_l), a), 1.0)
                positions = np.linspace(a, b, 6)
                for position in positions:
                    fraction = (
                        (float(position) - a) / (b - a)
                        if b - a > 1.0e-15
                        else 0.0
                    )
                    current = (
                        (1.0 - fraction) * np.asarray(vector, dtype=float)
                        + fraction * np.asarray(end_vector, dtype=float)
                    )
                    current_magnitude = self._vector_norm(current)
                    if current_magnitude <= 1.0e-15:
                        continue
                    current_length = base_length * (
                        current_magnitude / max_magnitude
                        if max_magnitude > 1.0e-15
                        else 1.0
                    )
                    arrow = self._arrow_record(
                        p_i + float(position) * member,
                        current,
                        length=max(current_length, base_length * 0.08),
                    )
                    if arrow is not None:
                        arrows.append(arrow)
                label_point = p_i + 0.5 * (a + b) * member
                unit = line_unit
            elif load.load_type in {"Uniform", "SelfWeight"}:
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

            input_vector = (
                (load.wx, load.wy, load.wz)
                if load.load_type == "Uniform"
                else (load.px, load.py, load.pz)
                if load.load_type == "Point"
                else None
            )
            title = f"Elem {load.element_tag} · {load.load_type}"
            if load.load_type in variable_types:
                coordinate_label = (
                    "global" if load.coordinate_system == "global" else "local"
                )
                title += (
                    "\n"
                    + self._format_vector(
                        f"w_start_{coordinate_label}",
                        (load.wx, load.wy, load.wz),
                        unit,
                    )
                    + "\n"
                    + self._format_vector(
                        f"w_end_{coordinate_label}",
                        (load.wx_end, load.wy_end, load.wz_end),
                        unit,
                    )
                    + f"\na/L={load.a_over_l:g} · b/L={load.b_over_l:g}"
                )
            elif input_vector is not None:
                coordinate_label = (
                    "global"
                    if load.coordinate_system == "global"
                    else "local"
                )
                title += "\n" + self._format_vector(
                    f"{prefix}_{coordinate_label}",
                    input_vector,
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
                text_color="#8b1042",
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
            "masses": (
                "display-mass-points",
                "display-mass-labels",
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
        elif name == "masses" and self._display_options[name]:
            self._draw_masses()
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
            if self._display_options["masses"]:
                self._draw_masses()

        if render and (
            self._display_options["nodal_loads"]
            or self._display_options["element_loads"]
            or self._display_options["prescribed_displacements"]
            or self._display_options["masses"]
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
        if self._display_options["masses"]:
            self._draw_masses()
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

    def clear_node_probe_overlay(
        self,
        *,
        render: bool = True,
        forget: bool = True,
    ) -> None:
        for name in ("node-probe-point", "node-probe-label"):
            self._remove_overlay(name)
        if forget:
            self._node_probe_tag = None
            self._node_probe_label = ""
        if render:
            self.plotter.render()

    def show_node_probe(
        self,
        node_tag: int,
        label: str,
        *,
        position: tuple[float, float, float] | None = None,
        render: bool = True,
    ) -> None:
        self.clear_node_probe_overlay(render=False, forget=False)
        if self._model is None:
            return
        node = self._model.nodes.get(int(node_tag))
        if node is None:
            return
        self._node_probe_tag = int(node_tag)
        self._node_probe_label = str(label)
        probe_position = (
            tuple(float(value) for value in position)
            if position is not None
            else tuple(float(value) for value in node.xyz)
        )
        cloud = pv.PolyData(np.asarray([probe_position], dtype=float))
        self.plotter.add_mesh(
            cloud,
            name="node-probe-point",
            color="#8f4db8",
            point_size=18,
            render_points_as_spheres=True,
            pickable=False,
            show_scalar_bar=False,
            render=False,
        )
        self._add_annotation_labels(
            [probe_position],
            [str(label)],
            name="node-probe-label",
            text_color="#6a318f",
            font_size=11,
            always_visible=True,
        )
        if render:
            self.plotter.render()

    def clear_result_overlay(
        self,
        *,
        render: bool = True,
        preserve_probe: bool = False,
    ) -> None:
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
            "result-shell-deformation-contour",
            "result-crack-pattern",
            "result-crack-pattern-mild",
            "result-crack-pattern-moderate",
            "result-crack-pattern-severe",
            "result-hinge-members",
            "result-hinge-points",
            "motion-overlay",
            "motion-nodes",
            "motion-max-point",
            "motion-min-point",
            "motion-max-label",
            "motion-min-label",
        ):
            self._remove_overlay(name)
        if not preserve_probe:
            self.clear_node_probe_overlay(render=False)
        self._result_overlay_active = False
        self._active_result_view_key = None
        self._motion_element_mesh = None
        self._motion_node_mesh = None
        self._motion_element_node_tags = []
        self._motion_node_tags = []
        self._motion_topology_key = None
        self._motion_extrema_snapshot = None
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

            if element.element_type in QUAD_ELEMENT_TYPES:
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


    @staticmethod
    def _principal_tensile_strain(
        values: object,
    ) -> tuple[float, float] | None:
        """Compatibility wrapper around the shared crack evaluator."""
        return principal_tensile_strain(values)


    def show_crack_pattern(
        self,
        result: dict[str, object],
        *,
        frame_index: int | None = None,
        accumulate: bool = False,
        line_scale: float = 0.65,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> dict[str, float | int]:
        """Draw MEFI/RCLMS smeared-crack lines from shared panel states."""
        if self._model is None:
            return {
                "panels": 0,
                "valid_panels": 0,
                "cracked": 0,
                "max_ratio": 0.0,
                "elements": 0,
            }

        states = mefi_crack_panel_states(
            result if isinstance(result, dict) else {},
            frame_index=frame_index,
            accumulate=bool(accumulate),
            element_tags=element_tags,
        )
        stats = mefi_crack_summary(states)
        line_scale = max(0.05, min(1.0, float(line_scale)))

        by_element: dict[int, list[object]] = {}
        for state in states:
            by_element.setdefault(int(state.element_tag), []).append(state)

        severity_geometry: dict[str, dict[str, list[object]]] = {
            "mild": {"points": [], "lines": [], "scales": []},
            "moderate": {"points": [], "lines": [], "scales": []},
            "severe": {"points": [], "lines": [], "scales": []},
        }
        intensity: list[float] = []

        for tag, panel_states in sorted(by_element.items()):
            element = self._model.elements.get(tag)
            if (
                element is None
                or element.element_type != "MEFI"
                or element.k is None
                or element.l is None
            ):
                continue

            node_i = self._model.nodes.get(element.i)
            node_j = self._model.nodes.get(element.j)
            node_k = self._model.nodes.get(element.k)
            node_l = self._model.nodes.get(element.l)
            if any(
                node is None
                for node in (node_i, node_j, node_k, node_l)
            ):
                continue

            pi = np.asarray(node_i.xyz, dtype=float)
            pj = np.asarray(node_j.xyz, dtype=float)
            pk = np.asarray(node_k.xyz, dtype=float)
            pl = np.asarray(node_l.xyz, dtype=float)

            edge_x = 0.5 * ((pj - pi) + (pk - pl))
            width_geom = float(np.linalg.norm(edge_x))
            if width_geom <= 1.0e-12:
                continue
            local_x = edge_x / width_geom

            edge_y = 0.5 * ((pl - pi) + (pk - pj))
            edge_y = (
                edge_y
                - float(np.dot(edge_y, local_x)) * local_x
            )
            height_geom = float(np.linalg.norm(edge_y))
            if height_geom <= 1.0e-12:
                continue
            local_y = edge_y / height_geom

            normal = np.cross(local_x, local_y)
            normal_norm = float(np.linalg.norm(normal))
            if normal_norm <= 1.0e-12:
                continue
            normal /= normal_norm

            total_width = sum(
                max(0.0, float(state.width))
                for state in panel_states
            )
            if total_width <= 1.0e-12:
                continue

            cumulative = 0.0
            for state in panel_states:
                raw_width = max(0.0, float(state.width))
                if (
                    not bool(state.cracked)
                    or state.theta_1 is None
                    or state.ratio is None
                ):
                    cumulative += raw_width
                    continue

                u = (cumulative + 0.5 * raw_width) / total_width
                bottom = (1.0 - u) * pi + u * pj
                top = (1.0 - u) * pl + u * pk
                panel_width_geom = (
                    raw_width / total_width * width_geom
                )

                crack_angle = float(state.theta_1) + 0.5 * math.pi
                dx = math.cos(crack_angle)
                dy = math.sin(crack_angle)
                limits: list[float] = []
                if abs(dx) > 1.0e-12:
                    limits.append(
                        0.5 * panel_width_geom / abs(dx)
                    )
                if abs(dy) > 1.0e-12:
                    limits.append(
                        0.5 * height_geom / abs(dy)
                    )
                if not limits:
                    cumulative += raw_width
                    continue

                half_length = line_scale * min(limits)
                direction = dx * local_x + dy * local_y
                direction_norm = float(np.linalg.norm(direction))
                if direction_norm <= 1.0e-12:
                    cumulative += raw_width
                    continue
                direction = direction / direction_norm

                # Build thin 3D crack strokes rather than wide ribbons.
                # Severity controls both colour and a small thickness change.
                severity = crack_severity(float(state.ratio))
                if severity == "none":
                    cumulative += raw_width
                    continue
                bucket = severity_geometry[severity]
                bucket_points = bucket["points"]
                bucket_lines = bucket["lines"]
                bucket_scales = bucket["scales"]

                stroke_scale = max(width_geom, height_geom)
                surface_offset = normal * stroke_scale * 8.0e-3

                # Duplicate the stroke on both wall faces so it remains visible
                # when the wall is viewed from either side.
                for face_sign in (1.0, -1.0):
                    face_center = (
                        0.5 * (bottom + top)
                        + face_sign * surface_offset
                    )
                    start_point = face_center - half_length * direction
                    end_point = face_center + half_length * direction

                    base = len(bucket_points)
                    bucket_points.extend((start_point, end_point))
                    bucket_lines.extend((2, base, base + 1))

                bucket_scales.append(stroke_scale)
                intensity.append(float(state.ratio))
                cumulative += raw_width

        stats["rendered_segments"] = len(intensity)
        self.clear_result_overlay(render=False)
        self.set_undeformed_model_visible(True, render=False)
        if not intensity:
            self.plotter.render()
            return stats

        severity_style = {
            "mild": ("#f9a825", 2.0e-3),
            "moderate": ("#ef6c00", 2.8e-3),
            "severe": ("#c62828", 3.8e-3),
        }
        rendered_any = False
        for severity, (color, radius_factor) in severity_style.items():
            bucket = severity_geometry[severity]
            bucket_points = bucket["points"]
            bucket_lines = bucket["lines"]
            bucket_scales = bucket["scales"]
            if not bucket_points:
                continue

            line_mesh = pv.PolyData(np.asarray(bucket_points, dtype=float))
            line_mesh.lines = np.asarray(bucket_lines, dtype=np.int64)
            typical_scale = (
                float(np.median(bucket_scales))
                if bucket_scales
                else 1.0
            )
            crack_radius = max(
                typical_scale * radius_factor,
                1.0e-6,
            )
            try:
                mesh = line_mesh.tube(
                    radius=crack_radius,
                    n_sides=8,
                    capping=True,
                )
            except Exception:
                mesh = line_mesh

            self.plotter.add_mesh(
                mesh,
                name=f"result-crack-pattern-{severity}",
                color=color,
                opacity=0.96,
                line_width=3,
                render_lines_as_tubes=True,
                lighting=False,
                show_edges=False,
                culling=False,
                pickable=False,
                render=False,
            )
            rendered_any = True

        self._result_overlay_active = rendered_any
        self._active_result_view_key = None
        self.plotter.render()
        return stats


    def show_shell_deformation_contour(
        self,
        result: dict[str, object],
        component: str,
        *,
        location: str = "mid",
        frame_index: int | None = None,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> dict[str, object]:
        """Show shell generalized strain/curvature contours.

        frame_index=None uses the final-state Gauss-point average payload.
        A non-negative frame index uses captured shell deformation history so
        the fringe follows result animation.
        """
        stats: dict[str, object] = {
            "rendered_elements": 0,
            "missing_thickness": 0,
            "frame_index": frame_index,
            "location": str(location),
            "component": str(component),
        }
        if self._model is None:
            return stats

        component = str(component)
        location = str(location or "mid").strip().lower()
        if location not in {"mid", "top", "bottom"}:
            location = "mid"
        stats["location"] = location

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
        principal_index = {
            "E1": 0,
            "E2": 1,
        }.get(component)
        if component_index is None and principal_index is None:
            self.clear_result_overlay()
            return stats

        final = result.get("final", {}) if isinstance(result, dict) else {}
        history = (
            result.get("history", {})
            if isinstance(result, dict)
            else {}
        )
        use_history = frame_index is not None and int(frame_index) >= 0
        if use_history:
            shell_data = (
                history.get("shell_section_deformations", {})
                if isinstance(history, dict)
                else {}
            )
        else:
            shell_data = (
                final.get("shell_section_deformations", {})
                if isinstance(final, dict)
                else {}
            )
        if not isinstance(shell_data, dict) or not shell_data:
            self.clear_result_overlay()
            return stats

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
            if use_history:
                if not isinstance(payload, list):
                    continue
                source_index = int(frame_index or 0)
                if source_index < 0 or source_index >= len(payload):
                    continue
                average = payload[source_index]
            else:
                if not isinstance(payload, dict):
                    continue
                average = payload.get("average", [])
            if not isinstance(average, (list, tuple)):
                continue

            element = self._model.elements.get(tag)
            if (
                element is None
                or element.k is None
                or element.l is None
            ):
                continue

            if component in {"Exx", "Eyy", "Gxy", "E1", "E2"}:
                z = 0.0
                if location != "mid":
                    section = (
                        self._sections.get(int(element.section_tag))
                        if element.section_tag is not None
                        else None
                    )
                    thickness = (
                        float(section.shell_total_thickness())
                        if section is not None
                        else 0.0
                    )
                    if not math.isfinite(thickness) or thickness <= 0.0:
                        stats["missing_thickness"] = (
                            int(stats["missing_thickness"]) + 1
                        )
                        continue
                    z = 0.5 * thickness * (
                        1.0 if location == "top" else -1.0
                    )

                surface_strain = shell_surface_strains(average, z)
                if surface_strain is None:
                    continue
                if principal_index is not None:
                    principal = shell_principal_strains(surface_strain)
                    if principal is None:
                        continue
                    value = float(principal[principal_index])
                else:
                    membrane_index = {
                        "Exx": 0,
                        "Eyy": 1,
                        "Gxy": 2,
                    }[component]
                    value = float(surface_strain[membrane_index])
            else:
                if (
                    component_index is None
                    or len(average) <= component_index
                ):
                    continue
                try:
                    value = float(average[component_index])
                except (TypeError, ValueError):
                    continue

            if not np.isfinite(value):
                continue
            tags.append(tag)
            values.append(value)

        if not tags:
            self.clear_result_overlay()
            return stats

        view_key = self._result_view_key(
            cache_key,
            "shell-deformation",
            component,
            location
            if component in {"Exx", "Eyy", "Gxy", "E1", "E2"}
            else "mid",
            -1 if frame_index is None else int(frame_index),
            self._result_scope_key(set(tags)),
        )
        if self._show_cached_result_view(view_key):
            stats["rendered_elements"] = len(tags)
            return stats

        mesh = self._batched_shell_mesh(self._model, tags)
        if mesh is None or mesh.n_cells != len(values):
            self.clear_result_overlay()
            return stats

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
        component_title = {
            "E1": "ε1 (max principal strain)",
            "E2": "ε2 (min principal strain)",
        }.get(component, component)
        if component in {"Exx", "Eyy", "Gxy", "E1", "E2"}:
            location_label = {
                "mid": "Mid",
                "top": "Top (+z)",
                "bottom": "Bottom (-z)",
            }[location]
            component_title = f"{component_title} · {location_label}"
        if frame_index is not None and int(frame_index) >= 0:
            component_title = (
                f"{component_title} · Frame {int(frame_index) + 1}"
            )
        title = (
            f"{component_title} [{unit_text}]"
            if unit_text and unit_text != "-"
            else component_title
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
        stats["rendered_elements"] = len(tags)
        self.plotter.render()
        return stats

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

    def show_shell_displacement_contour(
        self,
        result: dict[str, object],
        component: str,
        *,
        display_mode: str = "deformed_only",
        deformation_scale: float = 10.0,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        """Fringe nodal displacement only on true Shell element surfaces."""
        if self._model is None:
            return
        shell_tags = {
            int(tag)
            for tag in self._visible_element_tags()
            if (
                tag in self._model.elements
                and self._model.elements[tag].element_type
                in SHELL_ELEMENT_TYPES
            )
        }
        if element_tags:
            shell_tags.intersection_update(
                int(tag) for tag in element_tags
            )
        if not shell_tags:
            self.clear_result_overlay()
            return
        self.show_node_contour(
            result,
            "Displacement",
            str(component),
            display_mode=str(display_mode),
            deformation_scale=float(deformation_scale),
            element_tags=shell_tags,
            cache_key=cache_key,
        )

    def show_node_contour(
        self,
        result: dict[str, object],
        quantity: str,
        component: str,
        *,
        display_mode: str = "deformed_only",
        deformation_scale: float = 10.0,
        node_tags: set[int] | None = None,
        element_tags: set[int] | None = None,
        cache_key: object | None = None,
    ) -> None:
        """Show a nodal displacement/reaction scalar on line and quad meshes."""
        if self._model is None:
            return

        quantity = str(quantity)
        component = str(component)
        display_mode = self._normalized_deformation_display_mode(
            display_mode
        )
        deformation_scale = float(deformation_scale)
        view_key = self._result_view_key(
            cache_key,
            "node-contour",
            quantity,
            component,
            display_mode,
            deformation_scale,
            self._result_scope_key(node_tags),
            self._result_scope_key(element_tags),
        )

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

        displacement_data = final.get("node_displacements", {})
        if not isinstance(displacement_data, dict):
            displacement_data = {}

        def point_for(tag: int) -> tuple[float, float, float]:
            node = self._model.nodes[tag]
            if display_mode == "undeformed_only":
                return tuple(float(value) for value in node.xyz)
            raw = displacement_data.get(
                str(tag),
                displacement_data.get(tag, (0.0, 0.0, 0.0)),
            )
            values = list(raw) if isinstance(raw, (list, tuple)) else []
            while len(values) < 3:
                values.append(0.0)
            dx = float(values[0])
            dy = float(values[1])
            dz = 0.0 if self._model.ndm == 2 else float(values[2])
            return (
                float(node.xyz[0]) + deformation_scale * dx,
                float(node.xyz[1]) + deformation_scale * dy,
                float(node.xyz[2]) + deformation_scale * dz,
            )

        def value_for(tag: int) -> float | None:
            raw = data.get(str(tag), data.get(tag))
            if not isinstance(raw, (list, tuple)):
                return None
            try:
                return nodal_result_scalar(raw, component)
            except ValueError:
                return None

        line_points: list[tuple[float, float, float]] = []
        line_cells: list[int] = []
        line_scalars: list[float] = []

        quad_points: list[tuple[float, float, float]] = []
        quad_faces: list[int] = []
        quad_scalars: list[float] = []

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
            element = self._model.elements.get(tag)
            if element is None:
                continue

            element_nodes = element.node_tags()
            if element.element_type in QUAD_ELEMENT_TYPES:
                if len(element_nodes) != 4:
                    continue
                values = [value_for(node_tag) for node_tag in element_nodes]
                if any(value is None for value in values):
                    continue
                if any(
                    self._model.nodes.get(node_tag) is None
                    for node_tag in element_nodes
                ):
                    continue
                base = len(quad_points)
                quad_points.extend(
                    point_for(node_tag)
                    for node_tag in element_nodes
                )
                quad_scalars.extend(float(value) for value in values)
                quad_faces.extend(
                    (4, base, base + 1, base + 2, base + 3)
                )
                continue

            if len(element_nodes) < 2:
                continue
            node_i, node_j = element_nodes[:2]
            value_i = value_for(node_i)
            value_j = value_for(node_j)
            if value_i is None or value_j is None:
                continue
            if (
                self._model.nodes.get(node_i) is None
                or self._model.nodes.get(node_j) is None
            ):
                continue
            index = len(line_points)
            line_points.extend((point_for(node_i), point_for(node_j)))
            line_scalars.extend((float(value_i), float(value_j)))
            line_cells.extend((2, index, index + 1))

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
                    scoped_nodes.update(element.node_tags())
            visible_nodes.intersection_update(scoped_nodes)

        for tag in sorted(visible_nodes):
            node = self._model.nodes.get(tag)
            value = value_for(tag)
            if node is None or value is None:
                continue
            node_points.append(point_for(tag))
            node_scalars.append(float(value))

        if not line_points and not quad_points and not node_points:
            self.clear_result_overlay()
            return

        all_values = line_scalars + quad_scalars + node_scalars
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

        if quad_points:
            quad_mesh = pv.PolyData(
                np.asarray(quad_points, dtype=float),
                faces=np.asarray(quad_faces, dtype=np.int64),
                deep=True,
            )
            quad_mesh.point_data[scalar_name] = np.asarray(
                quad_scalars,
                dtype=float,
            )
            quad_kwargs = {
                "name": "result-shell-contour",
                "scalars": scalar_name,
                "cmap": cmap,
                "show_edges": True,
                "edge_color": "#263746",
                "line_width": 1,
                "smooth_shading": False,
                "pickable": False,
                "scalar_bar_args": scalar_bar_args,
                "render": False,
            }
            if clim is not None:
                quad_kwargs["clim"] = clim
            self.plotter.add_mesh(quad_mesh, **quad_kwargs)
            cache_kwargs = dict(quad_kwargs)
            cache_kwargs.pop("render", None)
            entries.append((quad_mesh, cache_kwargs))

        if line_points:
            line_mesh = pv.PolyData(np.asarray(line_points, dtype=float))
            line_mesh.lines = np.asarray(line_cells, dtype=np.int64)
            line_mesh.point_data[scalar_name] = np.asarray(
                line_scalars,
                dtype=float,
            )
            line_kwargs = {
                "name": "result-contour",
                "scalars": scalar_name,
                "cmap": cmap,
                "line_width": 7,
                "render_lines_as_tubes": True,
                "pickable": False,
                "show_scalar_bar": not bool(quad_points),
                "scalar_bar_args": scalar_bar_args,
                "render": False,
            }
            if clim is not None:
                line_kwargs["clim"] = clim
            self.plotter.add_mesh(line_mesh, **line_kwargs)
            cache_kwargs = dict(line_kwargs)
            cache_kwargs.pop("render", None)
            entries.append((line_mesh, cache_kwargs))

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
                "show_scalar_bar": not bool(quad_points or line_points),
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
        self.set_undeformed_model_visible(
            display_mode == "both",
            render=False,
        )
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

            if element.element_type in TRUSS_ELEMENT_TYPES:
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

    def set_motion_extrema_visible(
        self,
        visible: bool,
        *,
        render: bool = True,
    ) -> None:
        """Toggle frame-local Min/Max annotations for result animation."""
        self._motion_extrema_visible = bool(visible)
        if not self._motion_extrema_visible:
            for name in (
                "motion-max-point",
                "motion-min-point",
                "motion-max-label",
                "motion-min-label",
            ):
                self._remove_overlay(name)
        elif self._motion_extrema_snapshot is not None:
            self._draw_motion_extrema_snapshot(
                self._motion_extrema_snapshot,
                render=False,
            )
        if render:
            self.plotter.render()

    def _draw_motion_extrema_snapshot(
        self,
        snapshot: tuple[
            tuple[int, float, tuple[float, float, float]],
            tuple[int, float, tuple[float, float, float]],
        ],
        *,
        render: bool = False,
    ) -> None:
        min_data, max_data = snapshot
        min_tag, min_value, min_point = min_data
        max_tag, max_value, max_point = max_data
        unit = str(self._units.get("length", "")).strip()
        suffix = f" {unit}" if unit else ""

        max_cloud = pv.PolyData(np.asarray([max_point], dtype=float))
        self.plotter.add_mesh(
            max_cloud,
            name="motion-max-point",
            color="#c62828",
            point_size=15,
            render_points_as_spheres=True,
            pickable=False,
            show_scalar_bar=False,
            render=False,
        )
        self._add_annotation_labels(
            [max_point],
            [f"MAX {max_value:.4g}{suffix} · Node {max_tag}"],
            name="motion-max-label",
            text_color="#c62828",
            font_size=12,
            always_visible=True,
        )

        min_cloud = pv.PolyData(np.asarray([min_point], dtype=float))
        self.plotter.add_mesh(
            min_cloud,
            name="motion-min-point",
            color="#1565c0",
            point_size=13,
            render_points_as_spheres=True,
            pickable=False,
            show_scalar_bar=False,
            render=False,
        )
        self._add_annotation_labels(
            [min_point],
            [f"MIN {min_value:.4g}{suffix} · Node {min_tag}"],
            name="motion-min-label",
            text_color="#1565c0",
            font_size=12,
            always_visible=True,
        )

        if render:
            self.plotter.render()

    def _update_motion_extrema(
        self,
        *,
        node_tags: tuple[int, ...],
        displaced,
        displacement_magnitude,
        render: bool = False,
    ) -> None:
        """Cache frame extrema and draw them only when the ribbon toggle is on."""
        for name in (
            "motion-max-point",
            "motion-min-point",
            "motion-max-label",
            "motion-min-label",
        ):
            self._remove_overlay(name)

        if self._model is None:
            self._motion_extrema_snapshot = None
            return
        candidates = [
            int(tag)
            for tag in node_tags
            if int(tag) in self._model.nodes
        ]
        if not candidates:
            self._motion_extrema_snapshot = None
            return

        values = {
            tag: float(displacement_magnitude(tag))
            for tag in candidates
        }
        min_tag = min(candidates, key=lambda tag: values[tag])
        max_tag = max(candidates, key=lambda tag: values[tag])
        self._motion_extrema_snapshot = (
            (min_tag, values[min_tag], displaced(min_tag)),
            (max_tag, values[max_tag], displaced(max_tag)),
        )

        if self._motion_extrema_visible:
            self._draw_motion_extrema_snapshot(
                self._motion_extrema_snapshot,
                render=False,
            )
        if render:
            self.plotter.render()

    def show_motion_frame(
        self,
        vectors: dict[str, object],
        *,
        scale: float = 1.0,
        auto_scale: bool = True,
        reference_magnitude: float = 0.0,
        display_mode: str = "deformed_only",
    ) -> None:
        """Update a persistent deformation overlay for animation playback."""
        if self._model is None or not self._model.nodes:
            return

        display_mode = self._normalized_deformation_display_mode(
            display_mode
        )
        visible_elements = tuple(sorted(self._visible_element_tags()))
        visible_nodes = tuple(sorted(self._visible_node_tags()))
        reference = abs(float(reference_magnitude))
        scalar_upper = max(reference, 1.0e-15)
        topology_key = (
            visible_elements,
            visible_nodes,
            scalar_upper,
        )

        if self._motion_topology_key != topology_key:
            # Probe is an independent result annotation. Rebuilding the
            # animation mesh must not remove it or the contour scalar bar.
            self.clear_result_overlay(
                render=False,
                preserve_probe=True,
            )

            element_points: list[tuple[float, float, float]] = []
            element_lines: list[int] = []
            element_faces: list[int] = []
            element_node_tags: list[int] = []
            for element_tag in visible_elements:
                element = self._model.elements.get(element_tag)
                if element is None:
                    continue

                node_tags = element.node_tags()
                if element.element_type in QUAD_ELEMENT_TYPES:
                    if (
                        len(node_tags) != 4
                        or any(
                            node_tag not in self._model.nodes
                            for node_tag in node_tags
                        )
                    ):
                        continue
                    index = len(element_points)
                    element_points.extend(
                        self._model.nodes[node_tag].xyz
                        for node_tag in node_tags
                    )
                    element_node_tags.extend(node_tags)
                    element_faces.extend(
                        (4, index, index + 1, index + 2, index + 3)
                    )
                    continue

                if (
                    len(node_tags) < 2
                    or node_tags[0] not in self._model.nodes
                    or node_tags[1] not in self._model.nodes
                ):
                    continue
                index = len(element_points)
                element_points.extend(
                    (
                        self._model.nodes[node_tags[0]].xyz,
                        self._model.nodes[node_tags[1]].xyz,
                    )
                )
                element_node_tags.extend((node_tags[0], node_tags[1]))
                element_lines.extend((2, index, index + 1))

            if element_points:
                mesh = pv.PolyData(
                    np.asarray(element_points, dtype=float)
                )
                if element_lines:
                    mesh.lines = np.asarray(
                        element_lines,
                        dtype=np.int64,
                    )
                if element_faces:
                    mesh.faces = np.asarray(
                        element_faces,
                        dtype=np.int64,
                    )
                mesh.point_data["magnitude"] = np.zeros(
                    len(element_points),
                    dtype=float,
                )
                length_unit = str(self._units.get("length", "")).strip()
                scalar_title = (
                    f"Displacement magnitude [{length_unit}]"
                    if length_unit
                    else "Displacement magnitude"
                )
                self.plotter.add_mesh(
                    mesh,
                    name="motion-overlay",
                    scalars="magnitude",
                    cmap="turbo",
                    clim=(0.0, scalar_upper),
                    show_edges=bool(element_faces),
                    edge_color="#263746",
                    line_width=3 if element_faces else 5,
                    render_lines_as_tubes=True,
                    smooth_shading=False,
                    pickable=False,
                    scalar_bar_args={"title": scalar_title},
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
                node_mesh.point_data["magnitude"] = np.zeros(
                    len(node_points),
                    dtype=float,
                )
                length_unit = str(self._units.get("length", "")).strip()
                scalar_title = (
                    f"Displacement magnitude [{length_unit}]"
                    if length_unit
                    else "Displacement magnitude"
                )
                self.plotter.add_mesh(
                    node_mesh,
                    name="motion-nodes",
                    scalars="magnitude",
                    cmap="turbo",
                    clim=(0.0, scalar_upper),
                    render_points_as_spheres=True,
                    point_size=7,
                    pickable=False,
                    show_scalar_bar=not bool(element_points),
                    scalar_bar_args={"title": scalar_title},
                    render=False,
                )
                self._motion_node_mesh = node_mesh
                self._motion_node_tags = node_tags

            self._motion_topology_key = topology_key

        effective_scale = float(scale)
        if auto_scale and reference > 1.0e-15:
            low, high = self._model.bounds()
            span = max(
                high[0] - low[0],
                high[1] - low[1],
                high[2] - low[2],
                1.0,
            )
            effective_scale *= 0.12 * span / reference

        def vector_components(tag: int) -> tuple[float, float, float]:
            raw = vectors.get(
                str(tag),
                vectors.get(tag, (0.0, 0.0, 0.0)),
            )
            values = list(raw) if raw is not None else []
            while len(values) < 3:
                values.append(0.0)
            dx = float(values[0])
            dy = float(values[1])
            dz = 0.0 if self._model.ndm == 2 else float(values[2])
            return dx, dy, dz

        def displaced(tag: int) -> tuple[float, float, float]:
            node = self._model.nodes[tag]
            if display_mode == "undeformed_only":
                return tuple(float(value) for value in node.xyz)
            dx, dy, dz = vector_components(tag)
            return (
                node.xyz[0] + effective_scale * dx,
                node.xyz[1] + effective_scale * dy,
                node.xyz[2] + effective_scale * dz,
            )

        def displacement_magnitude(tag: int) -> float:
            dx, dy, dz = vector_components(tag)
            return math.sqrt(dx * dx + dy * dy + dz * dz)

        if self._motion_element_mesh is not None:
            self._motion_element_mesh.points = np.asarray(
                [
                    displaced(tag)
                    for tag in self._motion_element_node_tags
                ],
                dtype=float,
            )
            self._motion_element_mesh.point_data["magnitude"] = np.asarray(
                [
                    displacement_magnitude(tag)
                    for tag in self._motion_element_node_tags
                ],
                dtype=float,
            )
        if self._motion_node_mesh is not None:
            self._motion_node_mesh.points = np.asarray(
                [displaced(tag) for tag in self._motion_node_tags],
                dtype=float,
            )
            self._motion_node_mesh.point_data["magnitude"] = np.asarray(
                [
                    displacement_magnitude(tag)
                    for tag in self._motion_node_tags
                ],
                dtype=float,
            )

        self._update_motion_extrema(
            node_tags=visible_nodes,
            displaced=displaced,
            displacement_magnitude=displacement_magnitude,
            render=False,
        )

        if (
            self._node_probe_tag is not None
            and self._node_probe_tag in self._model.nodes
        ):
            # Keep the probe attached to the animated/deformed node while the
            # motion contour and its scalar bar remain untouched.
            self.show_node_probe(
                self._node_probe_tag,
                self._node_probe_label,
                position=displaced(self._node_probe_tag),
                render=False,
            )

        self._result_overlay_active = True
        self._active_result_view_key = None
        self.set_undeformed_model_visible(
            display_mode == "both",
            render=False,
        )
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

    def current_view(self) -> str:
        return str(self._current_view)

    def set_view(self, view: str, *, render: bool = True) -> None:
        normalized = str(view).strip().lower()
        functions = {
            "iso": self.plotter.view_isometric,
            "xy": self.plotter.view_xy,
            "xz": self.plotter.view_xz,
            "yz": self.plotter.view_yz,
        }
        if normalized not in functions:
            raise ValueError(
                "Viewport view must be iso, xy, xz, or yz."
            )
        self._current_view = normalized
        self._invalidate_geometry_sketch_cursor_preview(render=False)
        function = functions[normalized]
        function()
        if render:
            self.plotter.render()

        for button in self.view_group.buttons():
            button.setChecked(button.property("view_name") == normalized)

    def view_active_sketch_plane(self, *, render: bool = True) -> None:
        origin = self._geometry_sketch_origin
        normal = self._geometry_sketch_normal
        up = self._geometry_sketch_v_axis
        camera = self.plotter.camera
        current_position = np.asarray(camera.GetPosition(), dtype=float)
        current_focal = np.asarray(camera.GetFocalPoint(), dtype=float)
        distance = max(
            float(np.linalg.norm(current_position - current_focal)),
            10.0,
        )
        camera.SetFocalPoint(*origin)
        camera.SetPosition(*(origin + normal * distance))
        camera.SetViewUp(*up)
        camera.SetParallelProjection(True)
        camera.OrthogonalizeViewUp()
        self._current_view = "sketch"
        self._invalidate_geometry_sketch_cursor_preview(render=False)
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.18)
        for button in self.view_group.buttons():
            button.setChecked(False)
        if render:
            self.plotter.render()

    def fit_view(self) -> None:
        if self._selected_nodes or self._selected_elements:
            self.zoom_to_selection(self._selected_nodes, self._selected_elements)
            return
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.18)
        self.plotter.render()
