from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..project import (
    MATERIAL_CATEGORIES,
    MATERIAL_DEFAULTS,
    MATERIAL_ENGINEERING_DEFAULTS,
    MATERIAL_PARAMETER_KINDS,
    MATERIAL_PARAMETER_ORDER,
    MaterialData,
)
from ..units import UnitSystem
from .material_test_dialog import MaterialTestDialog


PA_PER_MPA = 1.0e6

PREVIEW_MATERIAL_TYPES = {
    "Hysteretic",
    "Pinching4",
    "FRPConfinedConcrete02",
}

PARAMETER_LABELS = {
    "mode": "FRP definition",
    "dmgType": "Damage type",
    "damage": "Gap damage",
    "tfrp": "FRP jacket thickness tfrp",
    "R": "Column radius R",
    "Sy": "Yield slip Sy",
    "Su": "Ultimate slip Su",
    "eps_sh": "Strain at hardening eps_sh",
    "eps_ult": "Ultimate strain eps_ult",
}

SWITCH_OPTIONS = {
    "mode": (("JacketC - circular FRP jacket", 0.0), ("Ultimate - user-defined fcu/ecu", 1.0)),
    "dmgType": (("cycle", 0.0), ("energy", 1.0)),
    "damage": (("noDamage", 0.0), ("damage", 1.0)),
}


class MaterialEnvelopePreview(QWidget):
    """Lightweight live envelope preview for research-oriented materials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 180)
        self._material_type = ""
        self._parameters: dict[str, float] = {}

    def set_material(self, material_type: str, parameters: dict[str, float]) -> None:
        self._material_type = str(material_type)
        self._parameters = dict(parameters)
        self.update()

    def _curve(self) -> tuple[list[tuple[float, float]], str]:
        p = self._parameters
        if self._material_type == "Hysteretic":
            pts = [
                (p.get("e3n", 0.0), p.get("s3n", 0.0)),
                (p.get("e2n", 0.0), p.get("s2n", 0.0)),
                (p.get("e1n", 0.0), p.get("s1n", 0.0)),
                (0.0, 0.0),
                (p.get("e1p", 0.0), p.get("s1p", 0.0)),
                (p.get("e2p", 0.0), p.get("s2p", 0.0)),
                (p.get("e3p", 0.0), p.get("s3p", 0.0)),
            ]
            return pts, "Envelope preview · response vs deformation"

        if self._material_type == "Pinching4":
            pts = [
                (p.get("eNd4", 0.0), p.get("eNf4", 0.0)),
                (p.get("eNd3", 0.0), p.get("eNf3", 0.0)),
                (p.get("eNd2", 0.0), p.get("eNf2", 0.0)),
                (p.get("eNd1", 0.0), p.get("eNf1", 0.0)),
                (0.0, 0.0),
                (p.get("ePd1", 0.0), p.get("ePf1", 0.0)),
                (p.get("ePd2", 0.0), p.get("ePf2", 0.0)),
                (p.get("ePd3", 0.0), p.get("ePf3", 0.0)),
                (p.get("ePd4", 0.0), p.get("ePf4", 0.0)),
            ]
            return pts, "Envelope preview · Pinching4 cyclic rules use this backbone"

        if self._material_type == "FRPConfinedConcrete02":
            fc0 = p.get("fc0", 0.0)
            ec0 = p.get("ec0", 0.0)
            pts = [(0.0, 0.0), (ec0, fc0)]
            if p.get("mode", 0.0) >= 0.5:
                pts.append((p.get("ecu", ec0), p.get("fcu", fc0)))
            return pts, "Compression backbone input · OpenSees evaluates the full FRP law"

        return [], "Live envelope preview is available for Hysteretic, Pinching4 and FRP concrete."

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfcfe"))
        painter.setPen(QPen(QColor("#ccd6df"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        title_rect = QRectF(14, 10, self.width() - 28, 28)
        painter.setPen(QColor("#17356d"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, self._material_type or "Material Preview")

        points, note = self._curve()
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#647486"))
        painter.drawText(
            QRectF(14, self.height() - 54, self.width() - 28, 42),
            Qt.AlignLeft | Qt.TextWordWrap,
            note,
        )

        plot = QRectF(48, 48, max(80, self.width() - 76), max(90, self.height() - 126))
        painter.setPen(QPen(QColor("#d8e0e8"), 1))
        painter.drawRect(plot)

        if len(points) < 2:
            painter.setPen(QColor("#7b8997"))
            painter.drawText(plot, Qt.AlignCenter, "No envelope preview for this material.")
            return

        xs = [float(x) for x, _ in points]
        ys = [float(y) for _, y in points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if abs(xmax - xmin) <= 1.0e-15:
            xmin -= 1.0
            xmax += 1.0
        if abs(ymax - ymin) <= 1.0e-15:
            ymin -= 1.0
            ymax += 1.0
        padx = 0.08 * (xmax - xmin)
        pady = 0.08 * (ymax - ymin)
        xmin -= padx
        xmax += padx
        ymin -= pady
        ymax += pady

        def map_point(x: float, y: float) -> QPointF:
            px = plot.left() + (x - xmin) / (xmax - xmin) * plot.width()
            py = plot.bottom() - (y - ymin) / (ymax - ymin) * plot.height()
            return QPointF(px, py)

        if xmin <= 0.0 <= xmax:
            p0 = map_point(0.0, ymin)
            p1 = map_point(0.0, ymax)
            painter.setPen(QPen(QColor("#bac5d0"), 1))
            painter.drawLine(p0, p1)
        if ymin <= 0.0 <= ymax:
            p0 = map_point(xmin, 0.0)
            p1 = map_point(xmax, 0.0)
            painter.setPen(QPen(QColor("#bac5d0"), 1))
            painter.drawLine(p0, p1)

        path = QPainterPath()
        first = map_point(*points[0])
        path.moveTo(first)
        for point in points[1:]:
            path.lineTo(map_point(*point))
        painter.setPen(QPen(QColor("#c62828"), 2.2))
        painter.drawPath(path)

        painter.setBrush(QColor("#17356d"))
        painter.setPen(Qt.NoPen)
        for point in points:
            q = map_point(*point)
            painter.drawEllipse(q, 3.2, 3.2)


class MaterialDialog(QDialog):
    def __init__(
        self,
        material: MaterialData | None = None,
        *,
        next_tag: int = 1,
        units=None,
        materials: dict[int, MaterialData] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Material Editor")
        self.setModal(True)
        self.resize(920, 680)
        self.unit_system = UnitSystem.from_mapping(units)
        self.materials = dict(materials or {})
        if material is not None:
            self.materials.pop(material.tag, None)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(material.tag if material else next_tag)

        self.name = QLineEdit()
        self.name.setText(material.name if material else f"Material {next_tag}")

        self.material_type = QComboBox()
        ordered_types = sorted(
            MATERIAL_PARAMETER_ORDER,
            key=lambda name: (MATERIAL_CATEGORIES.get(name, ""), name),
        )
        for name in ordered_types:
            category = MATERIAL_CATEGORIES.get(name, "General")
            self.material_type.addItem(f"{category} · {name}", name)
        if material:
            index = self.material_type.findData(material.material_type)
            if index >= 0:
                self.material_type.setCurrentIndex(index)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.material_type)

        current_type = material.material_type if material else str(self.material_type.currentData())
        engineering_defaults = MATERIAL_ENGINEERING_DEFAULTS[current_type]

        self.poisson_ratio = QDoubleSpinBox()
        self.poisson_ratio.setDecimals(6)
        self.poisson_ratio.setRange(-0.99, 0.499999)
        self.poisson_ratio.setSingleStep(0.01)
        self.poisson_ratio.setValue(
            material.poisson_ratio if material is not None else engineering_defaults["poisson_ratio"]
        )

        self.density = QDoubleSpinBox()
        self.density.setDecimals(6)
        self.density.setRange(0.0, 1.0e12)
        self.density.setValue(
            material.density if material is not None else engineering_defaults["density"]
        )

        form.addRow("Poisson ratio ν:", self.poisson_ratio)
        form.addRow("Density ρ [kg/m³]:", self.density)
        root.addLayout(form)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.parameter_widget = QWidget()
        self.parameter_form = QFormLayout(self.parameter_widget)
        self.parameter_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll.setWidget(self.parameter_widget)
        splitter.addWidget(scroll)

        self.preview_host = QWidget()
        preview_layout = QVBoxLayout(self.preview_host)
        preview_layout.setContentsMargins(6, 0, 0, 0)
        self.preview_title = QLabel("Research response preview")
        self.preview_title.setStyleSheet(
            "font-weight: 700; color: #17356d;"
        )
        preview_layout.addWidget(self.preview_title)
        self.preview = MaterialEnvelopePreview()
        preview_layout.addWidget(self.preview, 1)
        splitter.addWidget(self.preview_host)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(1, True)
        splitter.setSizes([650, 270])

        # Keep material guidance available without forcing a permanent preview
        # pane.  Materials without a meaningful live envelope use the full
        # editor width and show only this compact note.
        self.material_note = QLabel()
        self.material_note.setWordWrap(True)
        self.material_note.setStyleSheet(
            "padding: 7px; background: #f2f5f8; color: #526578;"
        )
        root.addWidget(self.material_note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.test_material_button = buttons.addButton(
            "Test Material...",
            QDialogButtonBox.ActionRole,
        )
        self.test_material_button.clicked.connect(self._open_material_test)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._parameter_widgets: dict[str, QWidget] = {}
        # Backward-compatible handle used by engineering-unit tests and a few
        # internal callers; switch parameters live only in _parameter_widgets.
        self._parameter_spins: dict[str, QDoubleSpinBox] = {}
        self._initial_material = material
        self._frp_jacket_group: QGroupBox | None = None
        self._frp_ultimate_group: QGroupBox | None = None
        self._base_material_combo: QComboBox | None = None
        self._component_table: QTableWidget | None = None

        self.material_type.currentIndexChanged.connect(
            lambda _index: self._material_type_changed(str(self.material_type.currentData()))
        )
        self._rebuild_parameters(str(self.material_type.currentData()))

    def _material_type_changed(self, material_type: str) -> None:
        self._initial_material = None
        self._rebuild_parameters(material_type)
        defaults = MATERIAL_ENGINEERING_DEFAULTS[material_type]
        self.poisson_ratio.setValue(defaults["poisson_ratio"])
        self.density.setValue(defaults["density"])

    def _clear_parameter_form(self) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self._parameter_widgets.clear()
        self._parameter_spins.clear()
        self._frp_jacket_group = None
        self._frp_ultimate_group = None
        self._base_material_combo = None
        self._component_table = None

    def _parameter_kind(self, material_type: str, key: str) -> str:
        return MATERIAL_PARAMETER_KINDS.get(material_type, {}).get(key, "raw")

    def _display_value(self, material_type: str, key: str, stored: float) -> float:
        kind = self._parameter_kind(material_type, key)
        if kind == "stress":
            return stored / PA_PER_MPA
        if kind == "length":
            return self.unit_system.length_from_m(stored)
        return stored

    def _stored_value(self, material_type: str, key: str, display: float) -> float:
        kind = self._parameter_kind(material_type, key)
        if kind == "stress":
            return display * PA_PER_MPA
        if kind == "length":
            return self.unit_system.length_to_m_value(display)
        return display

    def _parameter_label(self, material_type: str, key: str) -> str:
        base = PARAMETER_LABELS.get(key, key)
        kind = self._parameter_kind(material_type, key)
        if kind == "stress":
            return f"{base} [MPa]:"
        if kind == "length":
            return f"{base} [{self.unit_system.length}]:"
        if material_type == "MinMax":
            self._add_base_material_selector(material_type)
            self._add_group(
                "Failure strain limits",
                material_type,
                ("min", "max"),
            )
        elif material_type == "Fatigue":
            self._add_base_material_selector(material_type)
            self._add_group(
                "Coffin-Manson fatigue / global limits",
                material_type,
                ("E0", "m", "min", "max"),
            )
        elif material_type in {"Parallel", "Series"}:
            self._add_composite_selector(material_type)
        elif material_type == "Hysteretic":
            if key.startswith("s"):
                return f"{key} response:"
            if key.startswith("e"):
                return f"{key} deformation:"
        if material_type == "Pinching4":
            if "f" in key and key.startswith(("eP", "eN")):
                return f"{key} response:"
            if "d" in key and key.startswith(("eP", "eN")):
                return f"{key} deformation:"
        return f"{base}:"

    def _initial_value(self, material_type: str, key: str) -> float:
        defaults = MATERIAL_DEFAULTS[material_type]
        if (
            self._initial_material is not None
            and self._initial_material.material_type == material_type
        ):
            stored = float(self._initial_material.parameters.get(key, defaults[key]))
        else:
            stored = float(defaults[key])
        return self._display_value(material_type, key, stored)

    def _make_widget(self, material_type: str, key: str) -> QWidget:
        if key in SWITCH_OPTIONS:
            combo = QComboBox()
            for label, value in SWITCH_OPTIONS[key]:
                combo.addItem(label, value)
            initial = self._initial_value(material_type, key)
            index = 0
            for candidate in range(combo.count()):
                if abs(float(combo.itemData(candidate)) - initial) < 0.5:
                    index = candidate
                    break
            combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(self._parameter_changed)
            self._parameter_widgets[key] = combo
            return combo

        spin = QDoubleSpinBox()
        kind = self._parameter_kind(material_type, key)
        spin.setDecimals(6 if kind == "stress" else 10)
        spin.setRange(-1.0e20, 1.0e20)
        spin.setSingleStep(1.0 if kind == "stress" else 0.01)
        spin.setValue(self._initial_value(material_type, key))
        spin.valueChanged.connect(self._parameter_changed)
        self._parameter_widgets[key] = spin
        self._parameter_spins[key] = spin
        return spin

    def _widget_value(self, key: str) -> float:
        widget = self._parameter_widgets[key]
        if isinstance(widget, QComboBox):
            return float(widget.currentData())
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        raise TypeError(f"Unsupported parameter widget for {key}")

    def _add_group(self, title: str, material_type: str, keys: tuple[str, ...]) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)
        for key in keys:
            form.addRow(self._parameter_label(material_type, key), self._make_widget(material_type, key))
        self.parameter_form.addRow(group)
        return group

    def _reference_material_combo(
        self,
        selected_tag: int | None = None,
    ) -> QComboBox:
        combo = QComboBox()
        for tag in sorted(self.materials):
            item = self.materials[tag]
            combo.addItem(
                f"{tag} - {item.name} ({item.material_type})",
                tag,
            )
        if selected_tag is not None:
            index = combo.findData(int(selected_tag))
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(self._parameter_changed)
        return combo

    def _add_base_material_selector(self, material_type: str) -> None:
        group = QGroupBox("Wrapped material")
        form = QFormLayout(group)
        selected = (
            self._initial_material.base_material_tag
            if (
                self._initial_material is not None
                and self._initial_material.material_type == material_type
            )
            else None
        )
        self._base_material_combo = self._reference_material_combo(selected)
        if self._base_material_combo.count() == 0:
            self._base_material_combo.addItem(
                "Create a base material first",
                None,
            )
            self._base_material_combo.setEnabled(False)
        form.addRow("Base material:", self._base_material_combo)
        self.parameter_form.addRow(group)

    def _add_component_row(
        self,
        material_tag: int | None = None,
        factor: float = 1.0,
    ) -> None:
        table = self._component_table
        if table is None:
            return
        row = table.rowCount()
        table.insertRow(row)

        combo = self._reference_material_combo(material_tag)
        if combo.count() == 0:
            combo.addItem("No materials available", None)
            combo.setEnabled(False)
        table.setCellWidget(row, 0, combo)

        if str(self.material_type.currentData()) == "Parallel":
            spin = QDoubleSpinBox()
            spin.setDecimals(8)
            spin.setRange(-1.0e12, 1.0e12)
            spin.setValue(float(factor))
            spin.valueChanged.connect(self._parameter_changed)
            table.setCellWidget(row, 1, spin)
        else:
            table.setItem(row, 1, QTableWidgetItem("—"))

        self._parameter_changed()

    def _remove_component_rows(self) -> None:
        table = self._component_table
        if table is None:
            return
        rows = sorted(
            {index.row() for index in table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            table.removeRow(row)
        self._parameter_changed()

    def _add_composite_selector(self, material_type: str) -> None:
        group = QGroupBox(
            "Parallel components"
            if material_type == "Parallel"
            else "Series components"
        )
        layout = QVBoxLayout(group)
        self._component_table = QTableWidget(0, 2)
        self._component_table.setHorizontalHeaderLabels(
            ["Material", "Factor" if material_type == "Parallel" else "Series"]
        )
        self._component_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.Stretch,
        )
        self._component_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,
        )
        layout.addWidget(self._component_table)

        buttons = QHBoxLayout()
        add_button = QPushButton("Add Material")
        remove_button = QPushButton("Remove Selected")
        add_button.clicked.connect(lambda: self._add_component_row())
        remove_button.clicked.connect(self._remove_component_rows)
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.parameter_form.addRow(group)

        tags: list[int] = []
        factors: list[float] = []
        if (
            self._initial_material is not None
            and self._initial_material.material_type == material_type
        ):
            tags = list(self._initial_material.material_tags)
            factors = list(self._initial_material.factors)
        if not tags and self.materials:
            tags = [next(iter(sorted(self.materials)))]
        for index, tag in enumerate(tags):
            factor = (
                factors[index]
                if index < len(factors)
                else 1.0
            )
            self._add_component_row(tag, factor)

    def _wrapper_references(
        self,
        material_type: str,
    ) -> tuple[int | None, list[int], list[float]]:
        if material_type in {"MinMax", "Fatigue"}:
            base = (
                None
                if self._base_material_combo is None
                else self._base_material_combo.currentData()
            )
            return (
                None if base is None else int(base),
                [],
                [],
            )

        if material_type not in {"Parallel", "Series"}:
            return None, [], []

        tags: list[int] = []
        factors: list[float] = []
        table = self._component_table
        if table is None:
            return None, tags, factors
        for row in range(table.rowCount()):
            combo = table.cellWidget(row, 0)
            if not isinstance(combo, QComboBox) or combo.currentData() is None:
                continue
            tags.append(int(combo.currentData()))
            if material_type == "Parallel":
                factor = table.cellWidget(row, 1)
                factors.append(
                    float(factor.value())
                    if isinstance(factor, QDoubleSpinBox)
                    else 1.0
                )
        return None, tags, factors

    def _rebuild_parameters(self, material_type: str) -> None:
        self._clear_parameter_form()

        if material_type == "Hysteretic":
            self._add_group(
                "Positive envelope",
                material_type,
                ("s1p", "e1p", "s2p", "e2p", "s3p", "e3p"),
            )
            self._add_group(
                "Negative envelope",
                material_type,
                ("s1n", "e1n", "s2n", "e2n", "s3n", "e3n"),
            )
            self._add_group(
                "Pinching and degradation",
                material_type,
                ("pinchX", "pinchY", "damage1", "damage2", "beta"),
            )
        elif material_type == "Pinching4":
            self._add_group(
                "Positive envelope · 4 points",
                material_type,
                ("ePf1", "ePd1", "ePf2", "ePd2", "ePf3", "ePd3", "ePf4", "ePd4"),
            )
            self._add_group(
                "Negative envelope · 4 points",
                material_type,
                ("eNf1", "eNd1", "eNf2", "eNd2", "eNf3", "eNd3", "eNf4", "eNd4"),
            )
            self._add_group(
                "Pinching",
                material_type,
                ("rDispP", "rForceP", "uForceP", "rDispN", "rForceN", "uForceN"),
            )
            self._add_group(
                "Unloading stiffness degradation",
                material_type,
                ("gK1", "gK2", "gK3", "gK4", "gKLim"),
            )
            self._add_group(
                "Reloading stiffness degradation",
                material_type,
                ("gD1", "gD2", "gD3", "gD4", "gDLim"),
            )
            self._add_group(
                "Strength degradation",
                material_type,
                ("gF1", "gF2", "gF3", "gF4", "gFLim"),
            )
            self._add_group("Energy / damage rule", material_type, ("gE", "dmgType"))
        elif material_type == "FRPConfinedConcrete02":
            self._add_group("Unconfined concrete", material_type, ("fc0", "Ec", "ec0"))
            self._add_group("Confinement definition", material_type, ("mode",))
            self._frp_jacket_group = self._add_group(
                "Circular FRP jacket · JacketC",
                material_type,
                ("tfrp", "Efrp", "erup", "R"),
            )
            self._frp_ultimate_group = self._add_group(
                "User-defined confined ultimate point",
                material_type,
                ("fcu", "ecu"),
            )
            self._add_group("Tension", material_type, ("ft", "Ets"))
        else:
            for key in MATERIAL_PARAMETER_ORDER[material_type]:
                self.parameter_form.addRow(
                    self._parameter_label(material_type, key),
                    self._make_widget(material_type, key),
                )

        self._sync_special_visibility()
        self._update_preview()

    def _parameter_changed(self, *args) -> None:
        self._sync_special_visibility()
        self._update_preview()

    def _sync_special_visibility(self) -> None:
        if "mode" not in self._parameter_widgets:
            return
        jacket = self._widget_value("mode") < 0.5
        if self._frp_jacket_group is not None:
            self._frp_jacket_group.setVisible(jacket)
        if self._frp_ultimate_group is not None:
            self._frp_ultimate_group.setVisible(not jacket)

    def _display_parameter_values(self) -> dict[str, float]:
        return {
            key: self._widget_value(key)
            for key in self._parameter_widgets
        }

    def _update_preview(self) -> None:
        material_type = str(self.material_type.currentData())
        values = self._display_parameter_values()

        preview_available = material_type in PREVIEW_MATERIAL_TYPES
        self.preview_host.setVisible(preview_available)
        if preview_available:
            self.preview.set_material(material_type, values)

        if material_type == "FRPConfinedConcrete02":
            unit_ok = (
                self.unit_system.length == "mm"
                and self.unit_system.force == "N"
            )
            if unit_ok:
                self.material_note.setText(
                    "FRPConfinedConcrete02 uses the OpenSees SI metric convention "
                    "(N, mm, MPa). JacketC represents the wrap through the concrete "
                    "constitutive law; do not create a duplicate column element."
                )
                self.material_note.setStyleSheet(
                    "padding: 7px; background: #eaf6ee; color: #276738;"
                )
            else:
                self.material_note.setText(
                    "FRPConfinedConcrete02 is unit-sensitive. For research-safe "
                    "generation use project units mm - N - s (stress = MPa). "
                    "Studio will block generation in other unit systems."
                )
                self.material_note.setStyleSheet(
                    "padding: 7px; background: #fff4df; color: #7a5600;"
                )
        elif material_type in {"MinMax", "Fatigue"}:
            base, _, _ = self._wrapper_references(material_type)
            base_text = (
                f"material {base}"
                if base is not None
                else "no base material selected"
            )
            self.material_note.setText(
                f"{material_type} wraps {base_text}. The wrapped material must "
                "already exist; Studio generates dependencies before wrappers "
                "and blocks circular references."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        elif material_type in {"Parallel", "Series"}:
            _, tags, factors = self._wrapper_references(material_type)
            factor_text = (
                " with explicit linear-combination factors"
                if material_type == "Parallel"
                else ""
            )
            self.material_note.setText(
                f"{material_type} combines {len(tags)} referenced material(s)"
                f"{factor_text}. Use Material Test to exercise the assembled "
                "OpenSees constitutive object."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        elif material_type in {"Hysteretic", "Pinching4"}:
            self.material_note.setText(
                "Envelope points are shown live. These materials may represent "
                "stress-strain or force-deformation response depending on where "
                "they are assigned (fiber vs zeroLength/link)."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        else:
            self.material_note.setText(
                "Parameters are stored in research-friendly engineering units. "
                "Stress/modulus inputs are entered in MPa."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #f2f5f8; color: #526578;"
            )

    def _open_material_test(self) -> None:
        try:
            material = self.material_data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Material Test Lab",
                str(exc),
            )
            return

        test_materials = dict(self.materials)
        test_materials[material.tag] = material
        dialog = MaterialTestDialog(
            material,
            units=self.unit_system.as_mapping(),
            materials=test_materials,
            parent=self,
        )
        dialog.exec()

    def material_data(self) -> MaterialData:
        material_type = str(self.material_type.currentData())
        base_material_tag, material_tags, factors = (
            self._wrapper_references(material_type)
        )
        return MaterialData(
            tag=self.tag.value(),
            name=self.name.text().strip() or f"Material {self.tag.value()}",
            material_type=material_type,
            parameters={
                key: self._stored_value(
                    material_type,
                    key,
                    self._widget_value(key),
                )
                for key in MATERIAL_PARAMETER_ORDER[material_type]
            },
            poisson_ratio=self.poisson_ratio.value(),
            density=self.density.value(),
            base_material_tag=base_material_tag,
            material_tags=material_tags,
            factors=factors,
        )
