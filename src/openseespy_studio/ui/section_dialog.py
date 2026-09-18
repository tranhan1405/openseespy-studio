from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..generator import section_to_openseespy
from ..project import (
    FiberComponentData,
    FiberData,
    SECTION_DEFAULTS,
    SECTION_PARAMETER_ORDER,
    MaterialData,
    SectionData,
)


def _float_spin(
    value: float = 0.0,
    *,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 10,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(low, high)
    spin.setValue(float(value))
    return spin


def _positive_int(value: int, high: int = 10000) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, high)
    spin.setValue(int(value))
    return spin


def _material_color(tag: int) -> QColor:
    return QColor.fromHsv((int(tag) * 47) % 360, 150, 215)


class FiberPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self._fibers: list[FiberData] = []
        self._materials: dict[int, MaterialData] = {}
        self.show_axes = True
        self.show_centroid = True
        self.show_fibers = True

    def set_data(
        self,
        fibers: list[FiberData],
        materials: dict[int, MaterialData],
    ) -> None:
        self._fibers = list(fibers)
        self._materials = dict(materials)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#ccd6df"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if not self._fibers:
            painter.setPen(QColor("#708090"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No fibers yet\nAdd a patch, rebar layer, or manual fiber.",
            )
            return

        ys = [fiber.y for fiber in self._fibers]
        zs = [fiber.z for fiber in self._fibers]
        y_min, y_max = min(ys), max(ys)
        z_min, z_max = min(zs), max(zs)

        max_equivalent_radius = max(
            math.sqrt(max(fiber.area, 0.0) / math.pi)
            for fiber in self._fibers
        )
        y_min -= max_equivalent_radius
        y_max += max_equivalent_radius
        z_min -= max_equivalent_radius
        z_max += max_equivalent_radius

        span_y = max(y_max - y_min, 1.0e-9)
        span_z = max(z_max - z_min, 1.0e-9)
        margin = 48.0
        legend_height = min(84.0, 20.0 + 18.0 * len({
            fiber.material_tag for fiber in self._fibers
        }))
        available_w = max(40.0, self.width() - 2.0 * margin)
        available_h = max(
            40.0,
            self.height() - 2.0 * margin - legend_height,
        )
        scale = min(available_w / span_y, available_h / span_z)
        center_y = 0.5 * (y_min + y_max)
        center_z = 0.5 * (z_min + z_max)
        origin_x = 0.5 * self.width() - center_y * scale
        origin_y = (
            margin
            + 0.5 * available_h
            + center_z * scale
        )

        def map_point(y: float, z: float) -> QPointF:
            return QPointF(
                origin_x + y * scale,
                origin_y - z * scale,
            )

        if self.show_axes:
            axis_pen = QPen(QColor("#5b6b7d"), 1)
            painter.setPen(axis_pen)
            zero = map_point(0.0, 0.0)
            painter.drawLine(
                QPointF(margin, zero.y()),
                QPointF(self.width() - margin, zero.y()),
            )
            painter.drawLine(
                QPointF(zero.x(), margin),
                QPointF(zero.x(), margin + available_h),
            )
            painter.drawText(
                QPointF(self.width() - margin - 12.0, zero.y() - 6.0),
                "y",
            )
            painter.drawText(
                QPointF(zero.x() + 7.0, margin + 12.0),
                "z",
            )

        if self.show_fibers:
            for fiber in self._fibers:
                point = map_point(fiber.y, fiber.z)
                radius = math.sqrt(max(fiber.area, 0.0) / math.pi) * scale
                radius = max(1.8, min(radius, 11.0))
                color = _material_color(fiber.material_tag)
                painter.setBrush(color)
                painter.setPen(QPen(color.darker(135), 0.6))
                painter.drawEllipse(point, radius, radius)

        total_area = sum(fiber.area for fiber in self._fibers)
        if total_area > 0.0 and self.show_centroid:
            cy = (
                sum(fiber.y * fiber.area for fiber in self._fibers)
                / total_area
            )
            cz = (
                sum(fiber.z * fiber.area for fiber in self._fibers)
                / total_area
            )
            point = map_point(cy, cz)
            painter.setPen(QPen(QColor("#d32f2f"), 2))
            painter.drawLine(
                QPointF(point.x() - 7, point.y()),
                QPointF(point.x() + 7, point.y()),
            )
            painter.drawLine(
                QPointF(point.x(), point.y() - 7),
                QPointF(point.x(), point.y() + 7),
            )

        legend_tags = sorted({
            fiber.material_tag for fiber in self._fibers
        })
        x = margin
        y = self.height() - legend_height + 18
        painter.setPen(QColor("#34495e"))
        for tag in legend_tags:
            color = _material_color(tag)
            painter.fillRect(QRectF(x, y - 10, 11, 11), color)
            painter.setPen(QPen(QColor("#34495e"), 1))
            material = self._materials.get(tag)
            label = (
                f"{tag} - {material.name}"
                if material is not None
                else f"Material {tag}"
            )
            painter.drawText(QPointF(x + 17, y), label)
            y += 18


class FiberComponentDialog(QDialog):
    def __init__(
        self,
        materials: dict[int, MaterialData],
        component_type: str,
        component: FiberComponentData | None = None,
        *,
        preview_callback: Callable[[FiberComponentData | None], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Fiber Component")
        self.setModal(True)
        self.setMinimumWidth(430)
        self.materials = materials
        self.component_type = (
            component.component_type
            if component is not None
            else component_type
        )
        self.preview_callback = preview_callback
        self._initial = component

        defaults = FiberComponentData(
            self.component_type,
            self.component_type,
            next(iter(sorted(materials)), 1),
        )
        source = component or defaults
        p = source.parameters

        root = QVBoxLayout(self)
        form = QFormLayout()

        type_label = QLabel(self._pretty_type(self.component_type))
        type_label.setStyleSheet("font-weight: 700;")
        self.name = QLineEdit(source.name)
        self.material = QComboBox()
        for tag in sorted(materials):
            mat = materials[tag]
            self.material.addItem(
                f"{tag} - {mat.name} ({mat.material_type})",
                tag,
            )
        index = self.material.findData(source.material_tag)
        if index >= 0:
            self.material.setCurrentIndex(index)

        form.addRow("Type:", type_label)
        form.addRow("Name:", self.name)
        form.addRow("Material:", self.material)

        self.fields: dict[str, QWidget] = {}

        if self.component_type == "RectPatch":
            self._add_float(form, "y_center", "Center y:", p["y_center"])
            self._add_float(form, "z_center", "Center z:", p["z_center"])
            self._add_float(
                form, "width_y", "Width along y:", p["width_y"], low=1.0e-12
            )
            self._add_float(
                form, "depth_z", "Depth along z:", p["depth_z"], low=1.0e-12
            )
            self._add_int(form, "n_y", "Fibers along y:", int(p["n_y"]))
            self._add_int(form, "n_z", "Fibers along z:", int(p["n_z"]))
        elif self.component_type == "CircPatch":
            self._add_float(form, "y_center", "Center y:", p["y_center"])
            self._add_float(form, "z_center", "Center z:", p["z_center"])
            self._add_float(
                form, "r_inner", "Inner radius:", p["r_inner"], low=0.0
            )
            self._add_float(
                form, "r_outer", "Outer radius:", p["r_outer"], low=1.0e-12
            )
            self._add_int(
                form, "n_radial", "Radial divisions:", int(p["n_radial"])
            )
            self._add_int(
                form, "n_circum", "Circumferential divisions:", int(p["n_circum"])
            )
            self._add_float(
                form, "start_angle", "Start angle (deg):", p["start_angle"]
            )
            self._add_float(
                form, "end_angle", "End angle (deg):", p["end_angle"]
            )
        elif self.component_type == "StraightLayer":
            self._add_float(form, "y_i", "Start y:", p["y_i"])
            self._add_float(form, "z_i", "Start z:", p["z_i"])
            self._add_float(form, "y_j", "End y:", p["y_j"])
            self._add_float(form, "z_j", "End z:", p["z_j"])
            self._add_int(
                form, "n_bars", "Number of bars:", int(p["n_bars"]), 1000
            )
            diameter = math.sqrt(4.0 * p["bar_area"] / math.pi)
            self._add_float(
                form, "diameter", "Bar diameter:", diameter, low=1.0e-12
            )
        elif self.component_type == "CircLayer":
            self._add_float(form, "y_center", "Center y:", p["y_center"])
            self._add_float(form, "z_center", "Center z:", p["z_center"])
            self._add_float(
                form, "radius", "Layer radius:", p["radius"], low=1.0e-12
            )
            self._add_int(
                form, "n_bars", "Number of bars:", int(p["n_bars"]), 1000
            )
            diameter = math.sqrt(4.0 * p["bar_area"] / math.pi)
            self._add_float(
                form, "diameter", "Bar diameter:", diameter, low=1.0e-12
            )
            self._add_float(
                form, "start_angle", "Start angle (deg):", p["start_angle"]
            )
            self._add_float(
                form, "end_angle", "End angle (deg):", p["end_angle"]
            )
        elif self.component_type == "SingleFiber":
            self._add_float(form, "y", "y:", p["y"])
            self._add_float(form, "z", "z:", p["z"])
            self._add_float(
                form, "area", "Area:", p["area"], low=1.0e-16
            )

        root.addLayout(form)
        hint = QLabel(
            "Coordinates are in the section local y-z system. The same y-z "
            "axes are attached to the element through its geometric transformation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #657586;")
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self._cancel)
        root.addWidget(buttons)

        self.name.textChanged.connect(self._emit_preview)
        self.material.currentIndexChanged.connect(self._emit_preview)
        self._emit_preview()

    @staticmethod
    def _pretty_type(component_type: str) -> str:
        return {
            "RectPatch": "Rectangle Patch",
            "CircPatch": "Circular Patch",
            "StraightLayer": "Straight Rebar Layer",
            "CircLayer": "Circular Rebar Layer",
            "SingleFiber": "Single Fiber",
        }.get(component_type, component_type)

    def _add_float(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        value: float,
        *,
        low: float = -1.0e20,
        high: float = 1.0e20,
    ) -> None:
        widget = _float_spin(value, low=low, high=high)
        widget.valueChanged.connect(self._emit_preview)
        self.fields[key] = widget
        form.addRow(label, widget)

    def _add_int(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        value: int,
        high: int = 10000,
    ) -> None:
        widget = _positive_int(value, high)
        widget.valueChanged.connect(self._emit_preview)
        self.fields[key] = widget
        form.addRow(label, widget)

    def component_data(self) -> FiberComponentData:
        if self.material.currentData() is None:
            raise ValueError("Create and select a material first.")

        parameters: dict[str, float] = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QSpinBox):
                parameters[key] = float(widget.value())
            else:
                parameters[key] = float(widget.value())

        if "diameter" in parameters:
            diameter = parameters.pop("diameter")
            parameters["bar_area"] = math.pi * diameter * diameter / 4.0

        return FiberComponentData(
            component_type=self.component_type,
            name=self.name.text().strip() or self._pretty_type(self.component_type),
            material_tag=int(self.material.currentData()),
            parameters=parameters,
        )

    def _emit_preview(self, *args) -> None:
        if self.preview_callback is None:
            return
        try:
            component = self.component_data()
        except (ValueError, TypeError):
            return
        self.preview_callback(component)

    def _accept(self) -> None:
        try:
            self.component_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Fiber Component", str(exc))
            return
        self.accept()

    def _cancel(self) -> None:
        if self.preview_callback is not None:
            self.preview_callback(None)
        self.reject()


class SectionDialog(QDialog):
    def __init__(
        self,
        materials: dict[int, MaterialData],
        section: SectionData | None = None,
        *,
        next_tag: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Section Editor")
        self.setModal(True)
        self.resize(1040, 700)
        self.materials = materials
        self._initial_section = section
        self._components = [
            FiberComponentData.from_dict(component.to_dict())
            for component in (
                section.fiber_components
                if section and section.section_type == "Fiber"
                else []
            )
        ]

        root = QVBoxLayout(self)

        header = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(section.tag if section else next_tag)

        self.name = QLineEdit()
        self.name.setText(section.name if section else f"Section {next_tag}")

        self.section_type = QComboBox()
        self.section_type.addItems(["Elastic", "Fiber"])
        if section:
            self.section_type.setCurrentText(section.section_type)

        header.addRow("Tag:", self.tag)
        header.addRow("Name:", self.name)
        header.addRow("Type:", self.section_type)
        root.addLayout(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.elastic_page = self._build_elastic_page(section)
        self.stack.addWidget(self.elastic_page)

        self.fiber_page = self._build_fiber_page(section)
        self.stack.addWidget(self.fiber_page)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.section_type.currentTextChanged.connect(self._sync_page)
        self.tag.valueChanged.connect(self._update_fiber_outputs)
        self.name.textChanged.connect(self._update_fiber_outputs)
        self._sync_page(self.section_type.currentText())
        self._refresh_component_list()
        self._update_fiber_outputs()

    def _build_elastic_page(
        self,
        section: SectionData | None,
    ) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.elastic_material = QComboBox()
        self.elastic_material.addItem("Manual section properties", None)
        for tag in sorted(self.materials):
            material = self.materials[tag]
            self.elastic_material.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                tag,
            )
        if (
            section is not None
            and section.section_type == "Elastic"
            and section.material_tag is not None
        ):
            index = self.elastic_material.findData(section.material_tag)
            if index >= 0:
                self.elastic_material.setCurrentIndex(index)
        form.addRow("Material:", self.elastic_material)

        self.elastic_spins: dict[str, QDoubleSpinBox] = {}
        for key in SECTION_PARAMETER_ORDER["Elastic"]:
            initial = (
                section.parameters.get(
                    key,
                    SECTION_DEFAULTS["Elastic"][key],
                )
                if section and section.section_type == "Elastic"
                else SECTION_DEFAULTS["Elastic"][key]
            )
            spin = _float_spin(initial)
            form.addRow(f"{key}:", spin)
            self.elastic_spins[key] = spin

        self.elastic_material.currentIndexChanged.connect(
            self._update_elastic_material_link
        )
        self._update_elastic_material_link()
        return page

    def _build_fiber_page(
        self,
        section: SectionData | None,
    ) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        gj_form = QFormLayout()
        gj_value = (
            section.parameters.get(
                "GJ",
                SECTION_DEFAULTS["Fiber"]["GJ"],
            )
            if section and section.section_type == "Fiber"
            else SECTION_DEFAULTS["Fiber"]["GJ"]
        )
        self.gj = _float_spin(gj_value, low=0.0)
        self.gj.valueChanged.connect(self._update_fiber_outputs)
        gj_form.addRow("Torsional stiffness GJ:", self.gj)
        root.addLayout(gj_form)

        self.fiber_tabs = QTabWidget()
        root.addWidget(self.fiber_tabs, 1)

        self.builder_page = QWidget()
        builder_layout = QVBoxLayout(self.builder_page)

        splitter = QSplitter(Qt.Horizontal)
        builder_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.addWidget(QLabel("Section components"))
        self.component_list = QListWidget()
        self.component_list.itemDoubleClicked.connect(
            lambda _item: self._edit_selected_component()
        )
        left_layout.addWidget(self.component_list, 1)

        add_row_1 = QHBoxLayout()
        for text, kind in (
            ("+ Rectangle", "RectPatch"),
            ("+ Circle", "CircPatch"),
            ("+ Fiber", "SingleFiber"),
        ):
            button = QPushButton(text)
            button.clicked.connect(
                lambda checked=False, k=kind: self._add_component(k)
            )
            add_row_1.addWidget(button)
        left_layout.addLayout(add_row_1)

        add_row_2 = QHBoxLayout()
        for text, kind in (
            ("+ Rebar Line", "StraightLayer"),
            ("+ Rebar Circle", "CircLayer"),
        ):
            button = QPushButton(text)
            button.clicked.connect(
                lambda checked=False, k=kind: self._add_component(k)
            )
            add_row_2.addWidget(button)
        left_layout.addLayout(add_row_2)

        edit_row = QHBoxLayout()
        edit_button = QPushButton("Edit")
        remove_button = QPushButton("Remove")
        up_button = QPushButton("↑")
        down_button = QPushButton("↓")
        edit_button.clicked.connect(self._edit_selected_component)
        remove_button.clicked.connect(self._remove_selected_component)
        up_button.clicked.connect(lambda: self._move_component(-1))
        down_button.clicked.connect(lambda: self._move_component(1))
        edit_row.addWidget(edit_button)
        edit_row.addWidget(remove_button)
        edit_row.addStretch(1)
        edit_row.addWidget(up_button)
        edit_row.addWidget(down_button)
        left_layout.addLayout(edit_row)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)

        controls = QHBoxLayout()
        self.show_axes = QCheckBox("Axes")
        self.show_axes.setChecked(True)
        self.show_centroid = QCheckBox("Centroid")
        self.show_centroid.setChecked(True)
        self.show_fibers = QCheckBox("Fibers")
        self.show_fibers.setChecked(True)
        for checkbox in (
            self.show_axes,
            self.show_centroid,
            self.show_fibers,
        ):
            checkbox.toggled.connect(self._sync_preview_options)
            controls.addWidget(checkbox)
        controls.addStretch(1)
        right_layout.addLayout(controls)

        self.preview = FiberPreviewWidget()
        right_layout.addWidget(self.preview, 1)

        self.fiber_stats = QLabel()
        self.fiber_stats.setWordWrap(True)
        self.fiber_stats.setStyleSheet("color: #526578;")
        right_layout.addWidget(self.fiber_stats)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.fiber_tabs.addTab(self.builder_page, "Builder")

        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        hint = QLabel(
            "Manual/discrete fibers. Builder components are stored separately "
            "and compiled into fibers automatically."
        )
        hint.setWordWrap(True)
        table_layout.addWidget(hint)

        self.fiber_table = QTableWidget(0, 4)
        self.fiber_table.setHorizontalHeaderLabels(
            ["y", "z", "Area", "Material"]
        )
        self.fiber_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.fiber_table.itemChanged.connect(
            lambda _item: self._update_fiber_outputs()
        )
        table_layout.addWidget(self.fiber_table, 1)

        table_buttons = QHBoxLayout()
        add_fiber = QPushButton("Add Manual Fiber")
        remove_fiber = QPushButton("Remove Selected")
        add_fiber.clicked.connect(self._add_fiber_row)
        remove_fiber.clicked.connect(self._remove_selected_fibers)
        table_buttons.addWidget(add_fiber)
        table_buttons.addWidget(remove_fiber)
        table_buttons.addStretch(1)
        table_layout.addLayout(table_buttons)
        self.fiber_tabs.addTab(table_page, "Fiber Table")

        code_page = QWidget()
        code_layout = QVBoxLayout(code_page)
        self.generated_code = QPlainTextEdit()
        self.generated_code.setReadOnly(True)
        self.generated_code.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
        )
        code_layout.addWidget(self.generated_code)
        self.fiber_tabs.addTab(code_page, "Generated OpenSeesPy")

        if section and section.section_type == "Fiber":
            for fiber in section.fibers:
                self._add_fiber_row(fiber)

        return page

    def _update_elastic_material_link(self) -> None:
        material_tag = self.elastic_material.currentData()
        linked = material_tag is not None
        self.elastic_spins["E"].setEnabled(not linked)
        self.elastic_spins["G"].setEnabled(not linked)
        if not linked:
            return
        material = self.materials.get(int(material_tag))
        if material is None:
            return
        self.elastic_spins["E"].setValue(material.elastic_modulus())
        self.elastic_spins["G"].setValue(material.shear_modulus())

    def _sync_page(self, section_type: str) -> None:
        self.stack.setCurrentIndex(
            0 if section_type == "Elastic" else 1
        )
        if section_type == "Fiber":
            self._update_fiber_outputs()

    def _material_combo(
        self,
        selected_tag: int | None = None,
    ) -> QComboBox:
        combo = QComboBox()
        for tag in sorted(self.materials):
            material = self.materials[tag]
            combo.addItem(f"{tag} - {material.name}", tag)
        if selected_tag is not None:
            index = combo.findData(selected_tag)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(self._update_fiber_outputs)
        return combo

    def _add_fiber_row(
        self,
        fiber: FiberData | None = None,
    ) -> None:
        row = self.fiber_table.rowCount()
        self.fiber_table.blockSignals(True)
        self.fiber_table.insertRow(row)
        values = (
            (fiber.y, fiber.z, fiber.area)
            if fiber is not None
            else (0.0, 0.0, 1.0e-4)
        )
        for column, value in enumerate(values):
            self.fiber_table.setItem(
                row,
                column,
                QTableWidgetItem(f"{float(value):.10g}"),
            )
        selected_tag = (
            fiber.material_tag if fiber is not None else None
        )
        self.fiber_table.setCellWidget(
            row,
            3,
            self._material_combo(selected_tag),
        )
        self.fiber_table.blockSignals(False)
        self._update_fiber_outputs()

    def _remove_selected_fibers(self) -> None:
        rows = sorted(
            {
                index.row()
                for index in self.fiber_table.selectedIndexes()
            },
            reverse=True,
        )
        for row in rows:
            self.fiber_table.removeRow(row)
        self._update_fiber_outputs()

    def _fiber_data(self) -> list[FiberData]:
        fibers: list[FiberData] = []
        for row in range(self.fiber_table.rowCount()):
            combo = self.fiber_table.cellWidget(row, 3)
            if combo is None or combo.currentData() is None:
                raise ValueError(
                    f"Fiber row {row + 1} has no material assigned."
                )
            for column in range(3):
                if self.fiber_table.item(row, column) is None:
                    raise ValueError(
                        f"Fiber row {row + 1} is incomplete."
                    )
            fibers.append(
                FiberData(
                    y=float(self.fiber_table.item(row, 0).text()),
                    z=float(self.fiber_table.item(row, 1).text()),
                    area=float(self.fiber_table.item(row, 2).text()),
                    material_tag=int(combo.currentData()),
                )
            )
        return fibers

    def _component_summary(
        self,
        component: FiberComponentData,
    ) -> str:
        p = component.parameters
        if component.component_type == "RectPatch":
            detail = (
                f"{p['width_y']:g}×{p['depth_z']:g}, "
                f"{int(p['n_y'])}×{int(p['n_z'])}"
            )
        elif component.component_type == "CircPatch":
            detail = (
                f"R={p['r_outer']:g}, "
                f"{int(p['n_radial'])}×{int(p['n_circum'])}"
            )
        elif component.component_type == "StraightLayer":
            detail = f"{int(p['n_bars'])} bars"
        elif component.component_type == "CircLayer":
            detail = (
                f"{int(p['n_bars'])} bars, R={p['radius']:g}"
            )
        else:
            detail = f"A={p['area']:g}"
        return (
            f"{component.name} · {self._pretty_type(component.component_type)} "
            f"· Mat {component.material_tag} · {detail}"
        )

    @staticmethod
    def _pretty_type(component_type: str) -> str:
        return FiberComponentDialog._pretty_type(component_type)

    def _refresh_component_list(self) -> None:
        current = self.component_list.currentRow()
        self.component_list.clear()
        for component in self._components:
            self.component_list.addItem(
                self._component_summary(component)
            )
        if self._components:
            self.component_list.setCurrentRow(
                min(max(current, 0), len(self._components) - 1)
            )

    def _add_component(self, component_type: str) -> None:
        if not self.materials:
            QMessageBox.information(
                self,
                "Fiber Section Builder",
                "Create at least one material first.",
            )
            return

        original = list(self._components)

        def preview(component: FiberComponentData | None) -> None:
            if component is None:
                self._components = original
            else:
                self._components = original + [component]
            self._update_fiber_outputs()

        dialog = FiberComponentDialog(
            self.materials,
            component_type,
            preview_callback=preview,
            parent=self,
        )
        if dialog.exec():
            self._components = original + [dialog.component_data()]
            self._refresh_component_list()
        else:
            self._components = original
        self._update_fiber_outputs()

    def _edit_selected_component(self) -> None:
        index = self.component_list.currentRow()
        if index < 0 or index >= len(self._components):
            return
        original = [
            FiberComponentData.from_dict(component.to_dict())
            for component in self._components
        ]

        def preview(component: FiberComponentData | None) -> None:
            self._components = [
                FiberComponentData.from_dict(item.to_dict())
                for item in original
            ]
            if component is not None:
                self._components[index] = component
            self._update_fiber_outputs()

        dialog = FiberComponentDialog(
            self.materials,
            original[index].component_type,
            original[index],
            preview_callback=preview,
            parent=self,
        )
        if dialog.exec():
            self._components = original
            self._components[index] = dialog.component_data()
        else:
            self._components = original
        self._refresh_component_list()
        self.component_list.setCurrentRow(index)
        self._update_fiber_outputs()

    def _remove_selected_component(self) -> None:
        index = self.component_list.currentRow()
        if index < 0 or index >= len(self._components):
            return
        self._components.pop(index)
        self._refresh_component_list()
        self._update_fiber_outputs()

    def _move_component(self, direction: int) -> None:
        index = self.component_list.currentRow()
        target = index + int(direction)
        if (
            index < 0
            or target < 0
            or target >= len(self._components)
        ):
            return
        self._components[index], self._components[target] = (
            self._components[target],
            self._components[index],
        )
        self._refresh_component_list()
        self.component_list.setCurrentRow(target)
        self._update_fiber_outputs()

    def _sync_preview_options(self) -> None:
        self.preview.show_axes = self.show_axes.isChecked()
        self.preview.show_centroid = self.show_centroid.isChecked()
        self.preview.show_fibers = self.show_fibers.isChecked()
        self.preview.update()

    def _temporary_fiber_section(self) -> SectionData:
        return SectionData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Section {self.tag.value()}",
            section_type="Fiber",
            parameters={"GJ": self.gj.value()},
            fibers=self._fiber_data(),
            fiber_components=[
                FiberComponentData.from_dict(component.to_dict())
                for component in self._components
            ],
        )

    def _update_fiber_outputs(self, *args) -> None:
        if not hasattr(self, "preview"):
            return
        try:
            section = self._temporary_fiber_section()
            fibers = section.compiled_fibers()
        except (ValueError, AttributeError, TypeError):
            return

        self.preview.set_data(fibers, self.materials)
        total_area, (cy, cz) = section.fiber_area_and_centroid()
        self.fiber_stats.setText(
            f"Components: {len(section.fiber_components)}   ·   "
            f"Manual fibers: {len(section.fibers)}   ·   "
            f"Compiled fibers: {len(fibers)}   ·   "
            f"Area: {total_area:.6g}   ·   "
            f"Centroid (y,z): ({cy:.6g}, {cz:.6g})"
        )
        try:
            lines = section_to_openseespy(section, self.materials)
            self.generated_code.setPlainText("\n".join(lines))
        except ValueError as exc:
            self.generated_code.setPlainText(f"# {exc}")

    def _validate_and_accept(self) -> None:
        try:
            section = self.section_data()
            if section.section_type == "Fiber":
                if not self.materials:
                    raise ValueError(
                        "Create at least one material before defining a Fiber section."
                    )
                if not section.compiled_fibers():
                    raise ValueError(
                        "Fiber section needs at least one patch, rebar layer, "
                        "or manual fiber."
                    )
        except (ValueError, AttributeError) as exc:
            QMessageBox.warning(self, "Section Editor", str(exc))
            return
        self.accept()

    def section_data(self) -> SectionData:
        section_type = self.section_type.currentText()
        if section_type == "Elastic":
            parameters = {
                key: self.elastic_spins[key].value()
                for key in SECTION_PARAMETER_ORDER["Elastic"]
            }
            fibers: list[FiberData] = []
            components: list[FiberComponentData] = []
            material_tag = self.elastic_material.currentData()
        else:
            parameters = {"GJ": self.gj.value()}
            fibers = self._fiber_data()
            components = [
                FiberComponentData.from_dict(component.to_dict())
                for component in self._components
            ]
            material_tag = None

        return SectionData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Section {self.tag.value()}",
            section_type=section_type,
            parameters=parameters,
            fibers=fibers,
            fiber_components=components,
            material_tag=material_tag,
        )
