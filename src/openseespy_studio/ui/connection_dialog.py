from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..project import ConnectionData, MaterialData
from .material_chain_dialog import MaterialChainDialog
from .material_test_dialog import MaterialTestDialog


def _float_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(8)
    spin.setRange(-1.0e12, 1.0e12)
    spin.setSingleStep(0.1)
    spin.setValue(float(value))
    return spin


def _norm(values: tuple[float, float, float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def _dot(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(
    values: tuple[float, float, float],
) -> tuple[float, float, float]:
    length = _norm(values)
    if length <= 1.0e-14:
        raise ValueError("Orientation vector cannot be zero.")
    return tuple(value / length for value in values)


class LocalAxesPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._x = (1.0, 0.0, 0.0)
        self._y = (0.0, 1.0, 0.0)
        self._z = (0.0, 0.0, 1.0)

    def set_axes(
        self,
        x: tuple[float, float, float],
        y: tuple[float, float, float],
    ) -> None:
        try:
            ux = _unit(x)
            projection = _dot(y, ux)
            yp = tuple(y[i] - projection * ux[i] for i in range(3))
            uy = _unit(yp)
            uz = _unit(_cross(ux, uy))
        except ValueError:
            ux = (1.0, 0.0, 0.0)
            uy = (0.0, 1.0, 0.0)
            uz = (0.0, 0.0, 1.0)
        self._x, self._y, self._z = ux, uy, uz
        self.update()

    @staticmethod
    def _project(
        origin: QPointF,
        vector: tuple[float, float, float],
        scale: float,
    ) -> QPointF:
        # Simple isometric projection for a compact orientation preview.
        px = vector[0] - 0.48 * vector[1]
        py = -0.35 * vector[0] - 0.35 * vector[1] - vector[2]
        return QPointF(
            origin.x() + scale * px,
            origin.y() + scale * py,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfcfe"))
        painter.setPen(QPen(QColor("#d7e0e8"), 1))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            5.0,
            5.0,
        )

        origin = QPointF(self.width() * 0.46, self.height() * 0.62)
        scale = min(self.width(), self.height()) * 0.32
        painter.setBrush(QColor("#17356d"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(origin, 4.0, 4.0)

        axes = (
            ("X", self._x, QColor("#c62828")),
            ("Y", self._y, QColor("#2e7d32")),
            ("Z", self._z, QColor("#1565c0")),
        )
        for label, vector, color in axes:
            end = self._project(origin, vector, scale)
            painter.setPen(QPen(color, 2.5))
            painter.drawLine(origin, end)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(end, 4.0, 4.0)
            painter.setPen(color)
            painter.drawText(end + QPointF(6.0, -3.0), label)

        painter.setPen(QColor("#667788"))
        painter.drawText(
            QRectF(10, 8, self.width() - 20, 24),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Local connection axes",
        )


class ConnectionDialog(QDialog):
    DOF_LABELS = (
        ("UX", "Local translation X"),
        ("UY", "Local translation Y"),
        ("UZ", "Local translation Z"),
        ("RX", "Local rotation X"),
        ("RY", "Local rotation Y"),
        ("RZ", "Local rotation Z"),
    )

    @staticmethod
    def dof_labels_for_model(
        ndm: int,
        ndf: int,
    ) -> tuple[tuple[str, str], ...]:
        ndm = int(ndm)
        ndf = int(ndf)
        if ndm == 2:
            labels = [
                ("UX", "Local translation X"),
                ("UY", "Local translation Y"),
            ]
            if ndf >= 3:
                labels.append(("RZ", "Local rotation Z"))
            return tuple(labels[:ndf])
        return ConnectionDialog.DOF_LABELS[:ndf]

    @staticmethod
    def presets_for_model(
        ndm: int,
        ndf: int,
    ) -> tuple[tuple[str, tuple[int, ...]], ...]:
        ndm = int(ndm)
        ndf = int(ndf)
        presets: list[tuple[str, tuple[int, ...]]] = [
            ("Custom", ()),
            ("Axial / translational slip spring", (1,)),
        ]
        if ndf >= 2:
            presets.append(("Shear spring Y", (2,)))
        if ndm == 2:
            if ndf >= 3:
                presets.extend([
                    ("Rotational hinge RZ", (3,)),
                    ("Planar joint UX-UY-RZ", (1, 2, 3)),
                    ("Full 3-DOF spring", (1, 2, 3)),
                ])
            else:
                presets.append(("Full 2-DOF spring", (1, 2)))
            return tuple(presets)

        if ndf >= 3:
            presets.append(("3D interface / bearing", (1, 2, 3)))
        if ndf >= 6:
            presets.extend([
                ("Rotational hinge RZ", (6,)),
                ("Full 6-DOF spring", (1, 2, 3, 4, 5, 6)),
            ])
        else:
            presets.append(
                (f"Full {ndf}-DOF spring", tuple(range(1, ndf + 1)))
            )
        return tuple(presets)

    def __init__(
        self,
        materials: dict[int, MaterialData],
        connection: ConnectionData | None = None,
        *,
        next_tag: int = 1,
        initial_node_i: int = 1,
        initial_node_j: int = 2,
        default_to_ground: bool = False,
        node_positions: dict[int, tuple[float, float, float]] | None = None,
        units=None,
        ndm: int = 3,
        ndf: int = 6,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("ZeroLength / Link Research Builder")
        self.setModal(True)
        self.resize(760, 720)
        self.materials = dict(materials)
        self.pending_materials: list[MaterialData] = []
        self.node_positions = dict(node_positions or {})
        self.units = dict(units or {})
        self.ndm = int(ndm)
        self.ndf = int(ndf)
        self.dof_labels = self.dof_labels_for_model(
            self.ndm,
            self.ndf,
        )
        self.presets = self.presets_for_model(
            self.ndm,
            self.ndf,
        )

        root = QVBoxLayout(self)

        intro = QLabel(
            "Research spring/interface builder. Assign one UniaxialMaterial "
            "per active local DOF; nonlinear materials such as Pinching4, "
            "Hysteretic, Fatigue, MinMax, Parallel and Series can be tested "
            "directly before assignment. Use Chain... on any DOF to build "
            "Steel02 → Fatigue → MinMax in one research workflow."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "padding: 7px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(intro)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Setup tab.
        setup_page = QWidget()
        setup_layout = QVBoxLayout(setup_page)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(connection.tag if connection else next_tag)

        self.name = QLineEdit()
        self.name.setText(
            connection.name
            if connection
            else f"Connection {self.tag.value()}"
        )

        self.connection_type = QComboBox()
        self.connection_type.addItems(["zeroLength", "twoNodeLink"])
        if connection:
            self.connection_type.setCurrentText(connection.connection_type)

        self.preset = QComboBox()
        for label, dofs in self.presets:
            self.preset.addItem(label, tuple(dofs))

        self.to_ground = QCheckBox("Create coincident fixed ground node")
        self.to_ground.setChecked(
            connection.generated_ground_node is not None
            if connection
            else default_to_ground
        )

        self.node_i = QSpinBox()
        self.node_i.setRange(1, 2_147_483_647)
        self.node_i.setValue(
            connection.node_i if connection else initial_node_i
        )

        self.node_j = QSpinBox()
        self.node_j.setRange(1, 2_147_483_647)
        self.node_j.setValue(
            connection.node_j if connection else initial_node_j
        )

        self.do_rayleigh = QCheckBox("Include this connection in Rayleigh damping")
        self.do_rayleigh.setChecked(
            connection.do_rayleigh if connection else False
        )

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Element type:", self.connection_type)
        form.addRow("Research preset:", self.preset)
        form.addRow("Node I:", self.node_i)
        form.addRow("Node J:", self.node_j)
        form.addRow("Spring to ground:", self.to_ground)
        form.addRow("Rayleigh:", self.do_rayleigh)
        setup_layout.addLayout(form)

        self.node_status = QLabel()
        self.node_status.setWordWrap(True)
        setup_layout.addWidget(self.node_status)

        type_hint = QLabel(
            "<b>zeroLength</b>: Node I and J must be coincident. "
            "<b>twoNodeLink</b>: use when the end nodes are physically separated."
        )
        type_hint.setWordWrap(True)
        type_hint.setStyleSheet("color: #637487;")
        setup_layout.addWidget(type_hint)
        setup_layout.addStretch(1)
        self.tabs.addTab(setup_page, "Setup")

        # DOF material assignment tab.
        dof_page = QWidget()
        dof_layout = QVBoxLayout(dof_page)
        hint = QLabel(
            "DOF directions are local to the connection orientation. "
            "Enable only the mechanisms intentionally represented by the spring."
        )
        hint.setWordWrap(True)
        dof_layout.addWidget(hint)

        dof_group = QGroupBox("Directional UniaxialMaterials")
        dof_form = QFormLayout(dof_group)
        self.dof_checks: list[QCheckBox] = []
        self.material_combos: list[QComboBox] = []
        self.material_type_labels: list[QLabel] = []
        self.test_buttons: list[QPushButton] = []
        self.chain_buttons: list[QPushButton] = []

        for dof, (label, meaning) in enumerate(self.dof_labels, start=1):
            row = QHBoxLayout()
            check = QCheckBox("Active")
            combo = QComboBox()
            for tag in sorted(self.materials):
                material = self.materials[tag]
                combo.addItem(
                    f"{tag} - {material.name}",
                    tag,
                )
            type_label = QLabel("—")
            type_label.setMinimumWidth(120)
            type_label.setStyleSheet("color: #526578;")
            test_button = QPushButton("Test...")
            test_button.setMaximumWidth(72)
            chain_button = QPushButton("Chain...")
            chain_button.setMaximumWidth(76)
            chain_button.setToolTip(
                "Build a Steel02 → Fatigue → MinMax research chain "
                "and assign its outer material to this DOF."
            )

            row.addWidget(check)
            row.addWidget(combo, 1)
            row.addWidget(type_label)
            row.addWidget(test_button)
            row.addWidget(chain_button)

            holder = QWidget()
            holder.setLayout(row)
            dof_form.addRow(
                f"{label} · dir {dof}<br><span style='color:#788897'>{meaning}</span>:",
                holder,
            )

            self.dof_checks.append(check)
            self.material_combos.append(combo)
            self.material_type_labels.append(type_label)
            self.test_buttons.append(test_button)
            self.chain_buttons.append(chain_button)

            check.toggled.connect(
                lambda checked, index=dof - 1: self._sync_dof_row(
                    index,
                    checked,
                )
            )
            combo.currentIndexChanged.connect(
                lambda _index, index=dof - 1: self._sync_material_type(index)
            )
            test_button.clicked.connect(
                lambda _checked=False, index=dof - 1: self._test_dof_material(index)
            )
            chain_button.clicked.connect(
                lambda _checked=False, index=dof - 1: self._build_dof_chain(index)
            )

        dof_layout.addWidget(dof_group)
        dof_layout.addStretch(1)
        self.tabs.addTab(dof_page, "DOF Materials")

        # Orientation tab.
        orient_page = QWidget()
        orient_layout = QVBoxLayout(orient_page)
        orient_group = QGroupBox("Local orientation")
        orient = QFormLayout(orient_group)
        ox = connection.orient_x if connection else (1.0, 0.0, 0.0)
        oy = connection.orient_y if connection else (0.0, 1.0, 0.0)

        self.ox = [_float_spin(v) for v in ox]
        self.oy = [_float_spin(v) for v in oy]

        ox_row = QHBoxLayout()
        oy_row = QHBoxLayout()
        for spin in self.ox:
            ox_row.addWidget(spin)
            spin.valueChanged.connect(self._update_orientation_preview)
        for spin in self.oy:
            oy_row.addWidget(spin)
            spin.valueChanged.connect(self._update_orientation_preview)

        ox_holder = QWidget()
        oy_holder = QWidget()
        ox_holder.setLayout(ox_row)
        oy_holder.setLayout(oy_row)
        orient.addRow("Local X vector:", ox_holder)
        orient.addRow("Local Y-plane vector:", oy_holder)
        orient_layout.addWidget(orient_group)

        orient_buttons = QHBoxLayout()
        global_button = QPushButton("Global XYZ")
        node_button = QPushButton("X = Node I → J")
        orthogonal_button = QPushButton("Normalize / Orthogonalize")
        global_button.clicked.connect(self._set_global_axes)
        node_button.clicked.connect(self._set_x_from_nodes)
        orthogonal_button.clicked.connect(self._orthogonalize_axes)
        orient_buttons.addWidget(global_button)
        orient_buttons.addWidget(node_button)
        orient_buttons.addWidget(orthogonal_button)
        orient_buttons.addStretch(1)
        orient_layout.addLayout(orient_buttons)

        self.axes_preview = LocalAxesPreview()
        orient_layout.addWidget(self.axes_preview, 1)

        self.orientation_status = QLabel()
        self.orientation_status.setWordWrap(True)
        orient_layout.addWidget(self.orientation_status)
        self.tabs.addTab(orient_page, "Orientation")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if connection:
            for dof, material_tag in connection.materials_by_dof.items():
                if 1 <= dof <= len(self.dof_checks):
                    self.dof_checks[dof - 1].setChecked(True)
                    index = self.material_combos[dof - 1].findData(
                        material_tag
                    )
                    if index >= 0:
                        self.material_combos[dof - 1].setCurrentIndex(index)
        elif self.materials:
            self.preset.setCurrentIndex(1)
            self._apply_preset_index(1)

        self.to_ground.toggled.connect(self._sync_ground_state)
        self.connection_type.currentTextChanged.connect(
            lambda _text: self._update_node_status()
        )
        self.node_i.valueChanged.connect(
            lambda _value: self._update_node_status()
        )
        self.node_j.valueChanged.connect(
            lambda _value: self._update_node_status()
        )
        self.preset.currentIndexChanged.connect(self._preset_changed)

        self._sync_ground_state(self.to_ground.isChecked())
        for index in range(len(self.dof_checks)):
            self._sync_dof_row(index, self.dof_checks[index].isChecked())
            self._sync_material_type(index)
        self._update_orientation_preview()
        self._update_node_status()

    def _preset_changed(self, index: int) -> None:
        if index <= 0:
            return
        self._apply_preset_index(index)

    def _apply_preset_index(self, index: int) -> None:
        dofs = set(self.preset.itemData(index) or ())
        for dof, check in enumerate(self.dof_checks, start=1):
            check.setChecked(dof in dofs)

        label = self.preset.itemText(index)
        if "translational slip" in label.lower():
            self._select_material_type(
                0,
                {"Pinching4", "Hysteretic", "ElasticPPGap", "Steel02", "Elastic"},
            )
        elif "rotational hinge" in label.lower():
            row = next(
                (
                    index
                    for index, (name, _meaning)
                    in enumerate(self.dof_labels)
                    if name == "RZ"
                ),
                None,
            )
            if row is not None:
                self._select_material_type(
                    row,
                    {"Pinching4", "Hysteretic", "Steel02"},
                )

    def _select_material_type(
        self,
        row: int,
        preferred_types: set[str],
    ) -> None:
        combo = self.material_combos[row]
        for index in range(combo.count()):
            tag = combo.itemData(index)
            material = self.materials.get(int(tag)) if tag is not None else None
            if material is not None and material.material_type in preferred_types:
                combo.setCurrentIndex(index)
                return

    def _refresh_material_combos(
        self,
        *,
        select_row: int | None = None,
        select_material_tag: int | None = None,
    ) -> None:
        pending_tags = {material.tag for material in self.pending_materials}
        for row, combo in enumerate(self.material_combos):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for tag in sorted(self.materials):
                material = self.materials[tag]
                suffix = " · pending" if tag in pending_tags else ""
                combo.addItem(
                    f"{tag} - {material.name}{suffix}",
                    tag,
                )
            wanted = (
                select_material_tag
                if select_row == row and select_material_tag is not None
                else previous
            )
            index = combo.findData(wanted)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)
            self._sync_material_type(row)

    def _build_dof_chain(self, index: int) -> None:
        label = self.dof_labels[index][0]
        dialog = MaterialChainDialog(
            self.materials,
            units=self.units,
            target_dof_label=label,
            parent=self,
        )
        if not dialog.exec():
            return

        result = dialog.chain_result()
        for material in result.materials:
            self.materials[material.tag] = material
            self.pending_materials.append(material)

        self._refresh_material_combos(
            select_row=index,
            select_material_tag=result.final_tag,
        )
        self.dof_checks[index].setChecked(True)
        self.connection_type.setCurrentText("zeroLength")
        self._sync_material_type(index)

    def _pending_materials_in_use(
        self,
        materials_by_dof: dict[int, int],
    ) -> list[MaterialData]:
        pending = {material.tag: material for material in self.pending_materials}
        needed: set[int] = set()

        def collect(tag: int) -> None:
            if tag in needed or tag not in pending:
                return
            needed.add(tag)
            material = pending[tag]
            if (
                material.material_type in {"MinMax", "Fatigue"}
                and material.base_material_tag is not None
            ):
                collect(material.base_material_tag)
            elif material.material_type in {"Parallel", "Series"}:
                for dependency in material.material_tags:
                    collect(dependency)

        for material_tag in materials_by_dof.values():
            collect(material_tag)

        return [
            material
            for material in self.pending_materials
            if material.tag in needed
        ]

    def _sync_dof_row(self, index: int, checked: bool) -> None:
        self.material_combos[index].setEnabled(bool(checked))
        self.test_buttons[index].setEnabled(
            bool(checked) and self.material_combos[index].currentData() is not None
        )
        self.material_type_labels[index].setEnabled(bool(checked))

    def _sync_material_type(self, index: int) -> None:
        combo = self.material_combos[index]
        tag = combo.currentData()
        material = self.materials.get(int(tag)) if tag is not None else None
        self.material_type_labels[index].setText(
            material.material_type if material is not None else "—"
        )
        self.test_buttons[index].setEnabled(
            self.dof_checks[index].isChecked() and material is not None
        )

    def _test_dof_material(self, index: int) -> None:
        combo = self.material_combos[index]
        tag = combo.currentData()
        if tag is None:
            return
        material = self.materials.get(int(tag))
        if material is None:
            return
        dialog = MaterialTestDialog(
            material,
            units=self.units,
            materials=self.materials,
            parent=self,
        )
        dialog.exec()

    def _sync_ground_state(self, checked: bool) -> None:
        self.node_j.setEnabled(not checked)
        self._update_node_status()

    def _node_position(
        self,
        tag: int,
    ) -> tuple[float, float, float] | None:
        value = self.node_positions.get(int(tag))
        if value is None:
            return None
        return tuple(float(item) for item in value)

    def _update_node_status(self) -> None:
        if self.to_ground.isChecked():
            self.node_status.setText(
                "Ground mode: Studio will create a coincident fully fixed node "
                "at Node I when the connection is created."
            )
            self.node_status.setStyleSheet(
                "padding: 6px; background: #eaf6ee; color: #276738;"
            )
            return

        a = self._node_position(self.node_i.value())
        b = self._node_position(self.node_j.value())
        if a is None or b is None:
            self.node_status.setText(
                "Node coordinates are unavailable for this preview. "
                "Project validation will check the connection on creation."
            )
            self.node_status.setStyleSheet(
                "padding: 6px; background: #f5f7f9; color: #526578;"
            )
            return

        distance = math.sqrt(
            sum((a[i] - b[i]) ** 2 for i in range(3))
        )
        zero_length = self.connection_type.currentText() == "zeroLength"
        if zero_length and distance > 1.0e-7:
            self.node_status.setText(
                f"Node separation = {distance:.6g}. zeroLength requires "
                "coincident nodes; use twoNodeLink or create a coincident node."
            )
            self.node_status.setStyleSheet(
                "padding: 6px; background: #fff0f0; color: #9b2c2c;"
            )
        else:
            mode = "coincident" if distance <= 1.0e-7 else "separated"
            self.node_status.setText(
                f"Node separation = {distance:.6g} · {mode} node pair."
            )
            self.node_status.setStyleSheet(
                "padding: 6px; background: #eaf6ee; color: #276738;"
            )

    def _axis_values(self) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float],
    ]:
        return (
            tuple(spin.value() for spin in self.ox),
            tuple(spin.value() for spin in self.oy),
        )

    def _update_orientation_preview(self) -> None:
        x, y = self._axis_values()
        self.axes_preview.set_axes(x, y)
        nx = _norm(x)
        ny = _norm(y)
        cross_norm = _norm(_cross(x, y))
        if nx <= 1.0e-14 or ny <= 1.0e-14:
            text = "Local X and Y-plane vectors must both be non-zero."
            style = "padding: 6px; background: #fff0f0; color: #9b2c2c;"
        elif cross_norm / (nx * ny) <= 1.0e-6:
            text = (
                "Local X and Y-plane vectors are parallel or nearly parallel. "
                "They cannot define a stable local coordinate system."
            )
            style = "padding: 6px; background: #fff0f0; color: #9b2c2c;"
        else:
            cosine = _dot(x, y) / (nx * ny)
            text = (
                f"Orientation valid · |X|={nx:.4g}, |Yp|={ny:.4g}, "
                f"cos(X,Yp)={cosine:.4g}. OpenSees derives local Y/Z "
                "from X and the Y-plane vector."
            )
            style = "padding: 6px; background: #eaf6ee; color: #276738;"
        self.orientation_status.setText(text)
        self.orientation_status.setStyleSheet(style)

    def _set_global_axes(self) -> None:
        values = (
            ((1.0, 0.0, 0.0), self.ox),
            ((0.0, 1.0, 0.0), self.oy),
        )
        for vector, spins in values:
            for value, spin in zip(vector, spins):
                spin.setValue(value)

    def _set_x_from_nodes(self) -> None:
        a = self._node_position(self.node_i.value())
        b = self._node_position(self.node_j.value())
        if a is None or b is None:
            QMessageBox.information(
                self,
                "Connection Orientation",
                "Node coordinates are not available.",
            )
            return
        delta = tuple(b[i] - a[i] for i in range(3))
        try:
            x = _unit(delta)
        except ValueError:
            QMessageBox.information(
                self,
                "Connection Orientation",
                "Node I and J are coincident, so their line cannot define "
                "local X. Use Global XYZ or enter the intended local axes.",
            )
            return

        reference = (
            (0.0, 0.0, 1.0)
            if abs(x[2]) < 0.90
            else (0.0, 1.0, 0.0)
        )
        projection = _dot(reference, x)
        y = tuple(reference[i] - projection * x[i] for i in range(3))
        y = _unit(y)
        for value, spin in zip(x, self.ox):
            spin.setValue(value)
        for value, spin in zip(y, self.oy):
            spin.setValue(value)

    def _orthogonalize_axes(self) -> None:
        x, y = self._axis_values()
        try:
            x = _unit(x)
            projection = _dot(y, x)
            y = tuple(y[i] - projection * x[i] for i in range(3))
            y = _unit(y)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Connection Orientation",
                str(exc),
            )
            return
        for value, spin in zip(x, self.ox):
            spin.setValue(value)
        for value, spin in zip(y, self.oy):
            spin.setValue(value)

    def spec(self) -> dict:
        materials_by_dof: dict[int, int] = {}
        for dof, (check, combo) in enumerate(
            zip(self.dof_checks, self.material_combos),
            start=1,
        ):
            if not check.isChecked():
                continue
            material_tag = combo.currentData()
            if material_tag is None:
                raise ValueError(
                    f"DOF {dof} is active but has no material."
                )
            materials_by_dof[dof] = int(material_tag)

        if not materials_by_dof:
            raise ValueError("Enable at least one connection DOF.")

        if self.connection_type.currentText() == "zeroLength":
            bond_tags = sorted(
                material_tag
                for material_tag in materials_by_dof.values()
                if (
                    material_tag in self.materials
                    and self.materials[material_tag].material_type == "Bond_SP01"
                )
            )
            if bond_tags:
                raise ValueError(
                    "Bond_SP01 represents rebar stress-slip for strain "
                    "penetration and should be used in a Fiber zeroLengthSection, "
                    "not directly as a force-deformation zeroLength DOF. "
                    "Use a calibrated Pinching4/Hysteretic macro spring here "
                    "or the dedicated strain-penetration workflow."
                )

        x, y = self._axis_values()
        nx = _norm(x)
        ny = _norm(y)
        if nx <= 1.0e-14 or ny <= 1.0e-14:
            raise ValueError("Connection orientation vectors cannot be zero.")
        if _norm(_cross(x, y)) / (nx * ny) <= 1.0e-6:
            raise ValueError(
                "Connection local X and Y-plane vectors cannot be parallel."
            )

        if (
            self.connection_type.currentText() == "zeroLength"
            and not self.to_ground.isChecked()
        ):
            a = self._node_position(self.node_i.value())
            b = self._node_position(self.node_j.value())
            if a is not None and b is not None:
                distance = math.sqrt(
                    sum((a[i] - b[i]) ** 2 for i in range(3))
                )
                if distance > 1.0e-7:
                    raise ValueError(
                        "zeroLength requires coincident nodes. "
                        f"Current separation is {distance:.6g}."
                    )

        return {
            "tag": self.tag.value(),
            "name": self.name.text().strip()
            or f"Connection {self.tag.value()}",
            "connection_type": self.connection_type.currentText(),
            "node_i": self.node_i.value(),
            "node_j": self.node_j.value(),
            "to_ground": self.to_ground.isChecked(),
            "materials_by_dof": materials_by_dof,
            "orient_x": x,
            "orient_y": y,
            "do_rayleigh": self.do_rayleigh.isChecked(),
            "pending_materials": self._pending_materials_in_use(
                materials_by_dof
            ),
        }

    def _validate_and_accept(self) -> None:
        if not self.materials:
            QMessageBox.warning(
                self,
                "ZeroLength / Link Builder",
                "Create at least one UniaxialMaterial first.",
            )
            return
        try:
            self.spec()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "ZeroLength / Link Builder",
                str(exc),
            )
            return
        self.accept()
