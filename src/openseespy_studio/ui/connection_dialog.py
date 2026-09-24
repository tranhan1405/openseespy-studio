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

from ..project import ConnectionData, MaterialData, SectionData
from .material_chain_dialog import MaterialChainDialog
from .material_dialog import MaterialDialog
from .material_test_dialog import MaterialTestDialog
from .section_dialog import SectionDialog


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

    PRESETS = (
        ("Custom", ()),
        ("Axial / translational slip spring", (1,)),
        ("Shear spring Y", (2,)),
        ("Rotational hinge RZ", (6,)),
        ("Planar joint UX-UY-RZ", (1, 2, 6)),
        ("3D interface / bearing", (1, 2, 3)),
        ("Full 6-DOF spring", (1, 2, 3, 4, 5, 6)),
    )

    def __init__(
        self,
        materials: dict[int, MaterialData],
        connection: ConnectionData | None = None,
        *,
        sections: dict[int, SectionData] | None = None,
        next_tag: int = 1,
        initial_node_i: int = 1,
        initial_node_j: int = 2,
        initial_joint_nodes: list[int] | tuple[int, ...] | None = None,
        default_to_ground: bool = False,
        node_positions: dict[int, tuple[float, float, float]] | None = None,
        units=None,
        ndm: int = 3,
        ndf: int = 6,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Connection / Joint Builder")
        self.setModal(True)
        self.resize(760, 720)
        self.materials = dict(materials)
        self.pending_materials: list[MaterialData] = []
        self.sections = {
            int(tag): SectionData.from_dict(section.to_dict())
            for tag, section in (sections or {}).items()
        }
        self.pending_section_operations: list[
            tuple[str, int | None, SectionData]
        ] = []
        self.node_positions = dict(node_positions or {})
        self.units = dict(units or {})
        self.ndm = int(ndm)
        self.ndf = int(ndf)
        self._original_connection_type = (
            connection.connection_type if connection is not None else None
        )
        # These labels are element-direction labels, not raw nodal DOF
        # indices. zeroLength and twoNodeLink use different direction
        # numbering for 2D rotational response, so the rows are refreshed
        # whenever the connection model changes.
        self.display_dof_labels = list(self.DOF_LABELS)

        root = QVBoxLayout(self)

        intro = QLabel(
            "Create idealized frame connections and nonlinear joint models: "
            "Rigid, Pinned, Semi-Rigid, zeroLength/twoNodeLink, Joint2D, "
            "RC BeamColumnJoint, LehighJoint2D, or a Gupta-Krawinkler "
            "steel panel-zone macro. Use the dedicated tabs below for "
            "material, section, and joint data."
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
        self.connection_type.addItems([
            "rigid",
            "pinned",
            "semiRigid",
            "zeroLength",
            "zeroLengthSection",
            "twoNodeLink",
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        ])
        if connection:
            self.connection_type.setCurrentText(connection.connection_type)
        else:
            # Preserve the existing general-purpose connection workflow.
            # Users can switch explicitly to Rigid / Pinned / Joint models.
            self.connection_type.setCurrentText("zeroLength")

        self.preset = QComboBox()
        for label, directions in self.PRESETS:
            self.preset.addItem(label, tuple(directions))

        self.to_ground = QCheckBox("Create coincident fixed ground node")
        self.to_ground.setChecked(
            connection.generated_ground_node is not None
            if connection
            else default_to_ground
        )

        self.node_i = QSpinBox()
        self.node_i.setRange(0, 2_147_483_647)
        self.node_i.setValue(
            connection.node_i if connection else initial_node_i
        )

        self.node_j = QSpinBox()
        self.node_j.setRange(0, 2_147_483_647)
        self.node_j.setValue(
            connection.node_j if connection else initial_node_j
        )

        self.do_rayleigh = QCheckBox("Include this connection in Rayleigh damping")
        self.do_rayleigh.setChecked(
            connection.do_rayleigh if connection else False
        )

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Connection model:", self.connection_type)
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
            "<b>Rigid</b>: rigidLink beam. <b>Pinned</b>: translations tied, "
            "rotation released. <b>Semi-Rigid</b>: zeroLength spring with "
            "selected rotational/translational material DOFs. "
            "<b>TwoNodeLink</b>: geometry controls local X by default; enable "
            "orientation override only when needed. <b>Joint2D</b>, "
            "<b>BeamColumnJoint</b>, <b>LehighJoint2D</b>, and "
            "<b>KrawinklerPanelZone</b> use the Joint / Panel Zone tab. "
            "<b>BeamColumnJoint</b> supports 2D/3DOF and 3D/6DOF; the "
            "other dedicated joint wrappers remain 2D."
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
            "Direction IDs follow the selected OpenSees element convention. "
            "For a 2D zeroLength/semi-rigid spring, RZ is dir 6; for a "
            "2D twoNodeLink, RZ is dir 3. Enable only the mechanisms "
            "intentionally represented by the connection."
        )
        hint.setWordWrap(True)
        dof_layout.addWidget(hint)

        dof_group = QGroupBox("Directional UniaxialMaterials")
        dof_form = QFormLayout(dof_group)
        self.dof_checks: list[QCheckBox] = []
        self.material_combos: list[QComboBox] = []
        self.material_type_labels: list[QLabel] = []
        self.test_buttons: list[QPushButton] = []
        self.new_material_buttons: list[QPushButton] = []
        self.chain_buttons: list[QPushButton] = []
        self.dof_row_labels: list[QLabel] = []

        for dof, (label, meaning) in enumerate(self.display_dof_labels, start=1):
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
            new_material_button = QPushButton("New...")
            new_material_button.setMaximumWidth(72)
            new_material_button.setToolTip(
                "Create a UniaxialMaterial here and assign it to this DOF."
            )
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
            row.addWidget(new_material_button)
            row.addWidget(chain_button)

            holder = QWidget()
            holder.setLayout(row)
            row_label = QLabel(
                f"{label} · dir {dof}<br>"
                f"<span style='color:#788897'>{meaning}</span>"
            )
            row_label.setTextFormat(Qt.RichText)
            dof_form.addRow(row_label, holder)

            self.dof_row_labels.append(row_label)
            self.dof_checks.append(check)
            self.material_combos.append(combo)
            self.material_type_labels.append(type_label)
            self.test_buttons.append(test_button)
            self.new_material_buttons.append(new_material_button)
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
            new_material_button.clicked.connect(
                lambda _checked=False, index=dof - 1:
                self._create_dof_material(index)
            )
            chain_button.clicked.connect(
                lambda _checked=False, index=dof - 1: self._build_dof_chain(index)
            )

        dof_layout.addWidget(dof_group)

        link_group = QGroupBox("TwoNodeLink advanced")
        link_form = QFormLayout(link_group)
        link_params = (
            connection.parameters
            if connection is not None
            and connection.connection_type == "twoNodeLink"
            else {}
        )

        self.link_orientation_override = QCheckBox(
            "Override geometry-based local axes"
        )
        self.link_orientation_override.setChecked(
            bool(link_params.get("orientation_override", False))
        )
        self.link_orientation_override.setToolTip(
            "For a non-zero-length twoNodeLink, OpenSees normally takes local X "
            "from Node I → Node J. Enable this only when a manual local "
            "orientation is required."
        )
        link_form.addRow("Orientation:", self.link_orientation_override)

        saved_p_delta = list(link_params.get("p_delta", ()))
        self.link_pdelta_enable = QCheckBox("Use P-Delta moment distribution")
        self.link_pdelta_enable.setChecked(bool(saved_p_delta))
        pdelta_row = QHBoxLayout()
        self.link_pdelta_spins: list[QDoubleSpinBox] = []
        for index in range(4):
            value = saved_p_delta[index] if index < len(saved_p_delta) else 0.0
            spin = _float_spin(float(value))
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            self.link_pdelta_spins.append(spin)
            pdelta_row.addWidget(QLabel(("i", "j", "i-z", "j-z")[index]))
            pdelta_row.addWidget(spin)
        pdelta_holder = QWidget()
        pdelta_holder.setLayout(pdelta_row)
        link_form.addRow(self.link_pdelta_enable, pdelta_holder)

        saved_shear = list(link_params.get("shear_dist", ()))
        self.link_shear_enable = QCheckBox("Use shear-center distance")
        self.link_shear_enable.setChecked(bool(saved_shear))
        shear_row = QHBoxLayout()
        self.link_shear_spins: list[QDoubleSpinBox] = []
        for index in range(2):
            value = saved_shear[index] if index < len(saved_shear) else 0.5
            spin = _float_spin(float(value))
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            self.link_shear_spins.append(spin)
            shear_row.addWidget(QLabel(("dy", "dz")[index]))
            shear_row.addWidget(spin)
        shear_holder = QWidget()
        shear_holder.setLayout(shear_row)
        link_form.addRow(self.link_shear_enable, shear_holder)

        self.link_mass = _float_spin(float(link_params.get("mass", 0.0)))
        self.link_mass.setMinimum(0.0)
        link_form.addRow("Element mass:", self.link_mass)

        link_note = QLabel(
            "2D uses 2 P-Delta ratios and 1 shear-distance ratio; "
            "3D uses 4 and 2 respectively. End-moment ratio pairs must "
            "sum to ≤ 1.0."
        )
        link_note.setWordWrap(True)
        link_note.setStyleSheet("color: #637487;")
        link_form.addRow(link_note)
        dof_layout.addWidget(link_group)
        self.link_group = link_group

        dof_layout.addStretch(1)
        self.dof_page = dof_page
        self.dof_tab_index = self.tabs.addTab(dof_page, "DOF Materials")

        # Section assignment tab for zeroLengthSection.
        section_page = QWidget()
        section_layout = QVBoxLayout(section_page)
        section_group = QGroupBox("Section assignment")
        section_form = QFormLayout(section_group)

        self.section_combo = QComboBox()
        self._refresh_section_combo(
            select_tag=(
                connection.section_tag
                if connection is not None
                and connection.connection_type == "zeroLengthSection"
                else None
            )
        )
        section_form.addRow("Section:", self.section_combo)

        section_buttons = QHBoxLayout()
        self.new_section_button = QPushButton("New Section...")
        self.edit_section_button = QPushButton("Edit Selected...")
        self.new_section_button.clicked.connect(self._create_section)
        self.edit_section_button.clicked.connect(self._edit_selected_section)
        section_buttons.addWidget(self.new_section_button)
        section_buttons.addWidget(self.edit_section_button)
        section_buttons.addStretch(1)
        section_form.addRow("", section_buttons)

        self.section_status = QLabel(
            "zeroLengthSection uses the complete force-deformation response "
            "of the selected Section (for example Elastic or Fiber)."
        )
        self.section_status.setWordWrap(True)
        self.section_status.setStyleSheet("color: #637487;")
        section_form.addRow(self.section_status)

        section_layout.addWidget(section_group)
        section_layout.addStretch(1)
        self.section_page = section_page
        self.section_tab_index = self.tabs.addTab(section_page, "Section")

        # Joint / panel-zone assignment tab.
        joint_page = QWidget()
        joint_layout = QVBoxLayout(joint_page)

        joint_nodes_group = QGroupBox("External joint nodes")
        self.joint_nodes_group = joint_nodes_group
        joint_nodes_form = QFormLayout(joint_nodes_group)
        saved_external = (
            list(connection.parameters.get("external_nodes", ()))
            if connection is not None
            else [int(tag) for tag in (initial_joint_nodes or ())[:4]]
        )
        if (
            connection is None
            and len(saved_external) == 4
            and all(tag in self.node_positions for tag in saved_external)
        ):
            if self.ndm == 2:
                center_x = sum(
                    float(self.node_positions[tag][0])
                    for tag in saved_external
                ) / 4.0
                center_y = sum(
                    float(self.node_positions[tag][1])
                    for tag in saved_external
                ) / 4.0
                saved_external.sort(
                    key=lambda tag: math.atan2(
                        float(self.node_positions[tag][1]) - center_y,
                        float(self.node_positions[tag][0]) - center_x,
                    ),
                    reverse=True,
                )
                left_index = min(
                    range(4),
                    key=lambda index: float(
                        self.node_positions[saved_external[index]][0]
                    ),
                )
                saved_external = (
                    saved_external[left_index:]
                    + saved_external[:left_index]
                )
            else:
                try:
                    center = tuple(
                        sum(
                            float(self.node_positions[tag][axis])
                            for tag in saved_external
                        ) / 4.0
                        for axis in range(3)
                    )
                    vectors = {
                        tag: tuple(
                            float(self.node_positions[tag][axis])
                            - center[axis]
                            for axis in range(3)
                        )
                        for tag in saved_external
                    }
                    first = max(
                        saved_external,
                        key=lambda tag: _norm(vectors[tag]),
                    )
                    e1 = _unit(vectors[first])
                    candidates = [
                        (
                            _norm(_cross(e1, vectors[tag])),
                            tag,
                        )
                        for tag in saved_external
                        if tag != first
                    ]
                    _cross_norm, second = max(candidates)
                    normal = _unit(_cross(e1, vectors[second]))
                    e2 = _unit(_cross(normal, e1))
                    saved_external.sort(
                        key=lambda tag: math.atan2(
                            _dot(vectors[tag], e2),
                            _dot(vectors[tag], e1),
                        )
                    )
                    start = saved_external.index(min(saved_external))
                    saved_external = (
                        saved_external[start:]
                        + saved_external[:start]
                    )
                except (ValueError, ZeroDivisionError):
                    # Let project validation report the precise geometry
                    # problem when the user presses OK.
                    saved_external = sorted(saved_external)
        candidate_nodes = sorted(self.node_positions)
        while len(saved_external) < 4:
            index = len(saved_external)
            fallback = (
                candidate_nodes[index]
                if index < len(candidate_nodes)
                else (initial_node_i if index % 2 == 0 else initial_node_j)
            )
            saved_external.append(int(fallback))
        self.joint_node_spins: list[QSpinBox] = []
        self.joint_node_labels: list[QLabel] = []
        for label, value in zip(
            ("Left", "Top", "Right", "Bottom"),
            saved_external[:4],
        ):
            spin = QSpinBox()
            spin.setRange(0, 2_147_483_647)
            spin.setValue(int(value))
            row_label = QLabel(f"{label} node:")
            self.joint_node_labels.append(row_label)
            self.joint_node_spins.append(spin)
            joint_nodes_form.addRow(row_label, spin)
        joint_layout.addWidget(joint_nodes_group)

        self.joint_center_tag = QSpinBox()
        self.joint_center_tag.setRange(0, 2_147_483_647)
        self.joint_center_tag.setSpecialValueText("Auto")
        self.joint_center_tag.setValue(
            int(
                connection.parameters.get("imported_center_node_tag", 0)
            )
            if (
                connection is not None
                and connection.connection_type == "Joint2D"
            )
            else 0
        )
        joint_nodes_form.addRow(
            "Joint2D center node tag:",
            self.joint_center_tag,
        )

        joint_order_hint = QLabel(
            "When four nodes are preselected, SARE orders them cyclically. "
            "Krawinkler uses Left → Top → Right → Bottom. LehighJoint2D "
            "requires Node 1 → 4 counter-clockwise. Verify the preview/order "
            "before creating the joint."
        )
        joint_order_hint.setWordWrap(True)
        joint_order_hint.setStyleSheet("color: #637487;")
        joint_layout.addWidget(joint_order_hint)

        joint_dependency_row = QHBoxLayout()
        self.new_joint_material_button = QPushButton(
            "New Uniaxial Material..."
        )
        self.new_joint_material_button.setToolTip(
            "Create a material without leaving the Connection / Joint Builder"
        )
        self.new_joint_material_button.clicked.connect(
            self._create_joint_material
        )
        joint_dependency_row.addWidget(self.new_joint_material_button)
        joint_dependency_row.addStretch(1)
        joint_layout.addLayout(joint_dependency_row)

        joint_material_group = QGroupBox("Joint materials")
        joint_material_form = QFormLayout(joint_material_group)
        self.panel_material_combo = QComboBox()
        self.panel_material_combo.addItem("Select panel material...", None)
        for tag in sorted(self.materials):
            material = self.materials[tag]
            self.panel_material_combo.addItem(
                f"{tag} - {material.name}",
                int(tag),
            )
        saved_panel = (
            connection.parameters.get("panel_material")
            if connection is not None
            else None
        )
        panel_index = self.panel_material_combo.findData(saved_panel)
        if panel_index >= 0:
            self.panel_material_combo.setCurrentIndex(panel_index)
        joint_material_form.addRow(
            "Panel shear / rotational material:",
            self.panel_material_combo,
        )

        saved_interfaces = (
            list(connection.parameters.get(
                "interface_materials",
                (0, 0, 0, 0),
            ))
            if connection is not None
            else [0, 0, 0, 0]
        )
        self.interface_material_combos: list[QComboBox] = []
        for index in range(4):
            combo = QComboBox()
            combo.addItem("Rigid interface (0)", 0)
            for tag in sorted(self.materials):
                material = self.materials[tag]
                combo.addItem(
                    f"{tag} - {material.name}",
                    int(tag),
                )
            wanted = (
                saved_interfaces[index]
                if index < len(saved_interfaces)
                else 0
            )
            combo_index = combo.findData(int(wanted))
            if combo_index >= 0:
                combo.setCurrentIndex(combo_index)
            self.interface_material_combos.append(combo)
            joint_material_form.addRow(
                f"Joint2D interface Mat{index + 1}:",
                combo,
            )

        self.large_disp = QComboBox()
        self.large_disp.addItem("0 · small deformation", 0)
        self.large_disp.addItem("1 · large deformation", 1)
        self.large_disp.addItem("2 · large deformation + length correction", 2)
        saved_large_disp = (
            int(connection.parameters.get("large_disp", 0))
            if connection is not None
            else 0
        )
        large_index = self.large_disp.findData(saved_large_disp)
        if large_index >= 0:
            self.large_disp.setCurrentIndex(large_index)
        joint_material_form.addRow("Joint2D formulation:", self.large_disp)
        joint_layout.addWidget(joint_material_group)
        self.joint2d_material_group = joint_material_group

        # RC BeamColumnJoint · 13 physical component materials.
        bcj_group = QGroupBox(
            "BeamColumnJoint · RC component materials "
            "(N1 Bottom · N2 Right · N3 Top · N4 Left)"
        )
        bcj_layout = QHBoxLayout(bcj_group)
        bcj_left = QFormLayout()
        bcj_right = QFormLayout()
        bcj_layout.addLayout(bcj_left, 1)
        bcj_layout.addLayout(bcj_right, 1)
        bcj_labels = (
            "N1 bar-slip left",
            "N1 bar-slip right",
            "N1 interface shear",
            "N2 bar-slip bottom",
            "N2 bar-slip top",
            "N2 interface shear",
            "N3 bar-slip left",
            "N3 bar-slip right",
            "N3 interface shear",
            "N4 bar-slip bottom",
            "N4 bar-slip top",
            "N4 interface shear",
            "Shear panel",
        )
        saved_bcj = (
            list(connection.parameters.get("component_materials", ()))
            if (
                connection is not None
                and connection.connection_type == "BeamColumnJoint"
            )
            else []
        )
        self.bcj_material_combos: list[QComboBox] = []
        for index, label in enumerate(bcj_labels):
            combo = QComboBox()
            combo.addItem("Select material...", None)
            for material_tag in sorted(self.materials):
                material = self.materials[material_tag]
                combo.addItem(
                    f"{material_tag} - {material.name}",
                    int(material_tag),
                )
            if index < len(saved_bcj):
                wanted = int(saved_bcj[index])
                combo_index = combo.findData(wanted)
                if combo_index >= 0:
                    combo.setCurrentIndex(combo_index)
            self.bcj_material_combos.append(combo)
            target_form = bcj_left if index < 7 else bcj_right
            target_form.addRow(f"Mat{index + 1} · {label}:", combo)

        bcj_factor_group = QGroupBox("BeamColumnJoint geometry factors")
        bcj_factor_form = QFormLayout(bcj_factor_group)
        bcj_params = (
            connection.parameters
            if (
                connection is not None
                and connection.connection_type == "BeamColumnJoint"
            )
            else {}
        )
        self.bcj_height_factor = _float_spin(
            float(bcj_params.get("height_factor", 1.0))
        )
        self.bcj_width_factor = _float_spin(
            float(bcj_params.get("width_factor", 1.0))
        )
        self.bcj_height_factor.setMinimum(1.0e-12)
        self.bcj_width_factor.setMinimum(1.0e-12)
        bcj_factor_form.addRow("Height factor:", self.bcj_height_factor)
        bcj_factor_form.addRow("Width factor:", self.bcj_width_factor)
        self.bcj_factor_hint = QLabel(
            "Default = 1.0. In 2D the factors scale the effective joint "
            "height/width directly. In the current OpenSees 3D source the "
            "factors are retained in the internal spring formulation, while "
            "setDomain computes elemHeight/elemWidth with unit geometric "
            "scale. Non-default 3D values are preserved; review this upstream "
            "behavior when using them."
        )
        self.bcj_factor_hint.setWordWrap(True)
        self.bcj_factor_hint.setStyleSheet("color: #637487;")
        bcj_factor_form.addRow(self.bcj_factor_hint)
        joint_layout.addWidget(bcj_group)
        joint_layout.addWidget(bcj_factor_group)
        self.bcj_group = bcj_group
        self.bcj_factor_group = bcj_factor_group

        # LehighJoint2D · nine deformation-mode materials.
        lehigh_group = QGroupBox("LehighJoint2D · deformation-mode materials")
        lehigh_layout = QHBoxLayout(lehigh_group)
        lehigh_left = QFormLayout()
        lehigh_right = QFormLayout()
        lehigh_layout.addLayout(lehigh_left, 1)
        lehigh_layout.addLayout(lehigh_right, 1)
        lehigh_labels = (
            "Horizontal extension",
            "Vertical extension",
            "Shear distortion",
            "Beam flexure",
            "Column flexure",
            "Asymmetric beam flexure",
            "Asymmetric column flexure",
            "Beam varying shear distortion",
            "Column varying shear distortion",
        )
        saved_lehigh = (
            list(connection.parameters.get("mode_materials", ()))
            if (
                connection is not None
                and connection.connection_type == "LehighJoint2D"
            )
            else []
        )
        self.lehigh_material_combos: list[QComboBox] = []
        for index, label in enumerate(lehigh_labels):
            combo = QComboBox()
            combo.addItem("Select material...", None)
            for material_tag in sorted(self.materials):
                material = self.materials[material_tag]
                combo.addItem(
                    f"{material_tag} - {material.name}",
                    int(material_tag),
                )
            if index < len(saved_lehigh):
                wanted = int(saved_lehigh[index])
                combo_index = combo.findData(wanted)
                if combo_index >= 0:
                    combo.setCurrentIndex(combo_index)
            self.lehigh_material_combos.append(combo)
            target_form = lehigh_left if index < 5 else lehigh_right
            target_form.addRow(f"Mat{index + 1} · {label}:", combo)
        lehigh_hint = QLabel(
            "Node order must be counter-clockwise. Mat3 is the panel shear "
            "distortion mode; the remaining modes represent extension, "
            "flexure, asymmetry, and varying shear."
        )
        lehigh_hint.setWordWrap(True)
        lehigh_hint.setStyleSheet("color: #637487;")
        lehigh_layout.addWidget(lehigh_hint)
        joint_layout.addWidget(lehigh_group)
        self.lehigh_group = lehigh_group

        kraw_group = QGroupBox("Krawinkler stiff panel-boundary members")
        kraw_form = QFormLayout(kraw_group)
        params = connection.parameters if connection is not None else {}
        self.rigid_a = _float_spin(float(params.get("rigid_A", 0.0)))
        self.rigid_e = _float_spin(float(params.get("rigid_E", 0.0)))
        self.rigid_i = _float_spin(float(params.get("rigid_I", 0.0)))
        for spin in (self.rigid_a, self.rigid_e, self.rigid_i):
            spin.setMinimum(0.0)
        kraw_form.addRow("Rigid-link A:", self.rigid_a)
        kraw_form.addRow("Rigid-link E:", self.rigid_e)
        kraw_form.addRow("Rigid-link Iz:", self.rigid_i)
        kraw_hint = QLabel(
            "For KrawinklerPanelZone, enter deliberately stiff elastic-member "
            "properties in the active project unit system. The panel material "
            "defines the nonlinear shear-distortion spring."
        )
        kraw_hint.setWordWrap(True)
        kraw_hint.setStyleSheet("color: #637487;")
        kraw_form.addRow(kraw_hint)
        joint_layout.addWidget(kraw_group)
        self.kraw_group = kraw_group
        joint_layout.addStretch(1)

        self.joint_page = joint_page
        self.joint_tab_index = self.tabs.addTab(
            joint_page,
            "Joint / Panel Zone",
        )

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
        self.orientation_tab_index = self.tabs.addTab(
            orient_page,
            "Orientation",
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if connection:
            for dof, material_tag in connection.materials_by_dof.items():
                if 1 <= dof <= 6:
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
            self._connection_type_changed
        )
        self.node_i.valueChanged.connect(
            lambda _value: self._update_node_status()
        )
        self.node_j.valueChanged.connect(
            lambda _value: self._update_node_status()
        )
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.link_orientation_override.toggled.connect(
            lambda _checked: self._sync_two_node_link_options()
        )
        self.link_pdelta_enable.toggled.connect(
            lambda _checked: self._sync_two_node_link_options()
        )
        self.link_shear_enable.toggled.connect(
            lambda _checked: self._sync_two_node_link_options()
        )

        self._sync_ground_state(self.to_ground.isChecked())
        for index in range(6):
            self._sync_dof_row(index, self.dof_checks[index].isChecked())
            self._sync_material_type(index)
        self._connection_type_changed(self.connection_type.currentText())
        self._update_orientation_preview()
        self._update_node_status()

    def _refresh_section_combo(
        self,
        *,
        select_tag: int | None = None,
    ) -> None:
        if not hasattr(self, "section_combo"):
            return
        previous = self.section_combo.currentData()
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItem("Select section...", None)
        for tag in sorted(self.sections):
            section = self.sections[tag]
            self.section_combo.addItem(
                f"{tag} - {section.name} ({section.section_type})",
                int(tag),
            )
        wanted = select_tag if select_tag is not None else previous
        index = self.section_combo.findData(wanted)
        if index >= 0:
            self.section_combo.setCurrentIndex(index)
        self.section_combo.blockSignals(False)

    def _next_section_tag(self) -> int:
        return max(self.sections, default=0) + 1

    def _stage_section_materials(
        self,
        materials: list[MaterialData],
    ) -> None:
        known_pending = {material.tag for material in self.pending_materials}
        for material in materials:
            self.materials[int(material.tag)] = MaterialData.from_dict(
                material.to_dict()
            )
            if int(material.tag) not in known_pending:
                self.pending_materials.append(
                    MaterialData.from_dict(material.to_dict())
                )
                known_pending.add(int(material.tag))
        if materials:
            self._refresh_material_combos()

    def _create_section(self) -> None:
        dialog = SectionDialog(
            self.materials,
            next_tag=self._next_section_tag(),
            units=self.units,
            parent=self,
        )
        if not dialog.exec():
            return
        self._stage_section_materials(dialog.pending_materials())
        section = dialog.section_data()
        if section.tag in self.sections:
            QMessageBox.warning(
                self,
                "Section",
                f"Section tag {section.tag} already exists.",
            )
            return
        staged = SectionData.from_dict(section.to_dict())
        self.sections[staged.tag] = staged
        self.pending_section_operations.append(("add", None, staged))
        self._refresh_section_combo(select_tag=staged.tag)

    def _edit_selected_section(self) -> None:
        tag = self.section_combo.currentData()
        if tag is None:
            QMessageBox.information(
                self,
                "Section",
                "Select a section first.",
            )
            return
        original_tag = int(tag)
        section = self.sections.get(original_tag)
        if section is None:
            return
        dialog = SectionDialog(
            self.materials,
            section=SectionData.from_dict(section.to_dict()),
            units=self.units,
            parent=self,
        )
        if not dialog.exec():
            return
        self._stage_section_materials(dialog.pending_materials())
        updated = dialog.section_data()
        if updated.tag != original_tag and updated.tag in self.sections:
            QMessageBox.warning(
                self,
                "Section",
                f"Section tag {updated.tag} already exists.",
            )
            return
        self.sections.pop(original_tag, None)
        staged = SectionData.from_dict(updated.to_dict())
        self.sections[staged.tag] = staged
        self.pending_section_operations.append(
            ("update", original_tag, staged)
        )
        self._refresh_section_combo(select_tag=staged.tag)

    def _direction_profile(
        self,
        connection_type: str | None = None,
    ) -> tuple[list[tuple[str, str]], set[int]]:
        connection_type = (
            connection_type or self.connection_type.currentText()
        )
        labels = list(self.DOF_LABELS)

        if connection_type not in {
            "zeroLength",
            "twoNodeLink",
            "semiRigid",
        }:
            return labels, set()

        if self.ndm == 2 and self.ndf == 3:
            if connection_type in {"zeroLength", "semiRigid"}:
                # OpenSees zeroLength directions are local physical axes:
                # 1/2/3 = translations X/Y/Z; 4/5/6 = rotations X/Y/Z.
                # Therefore planar RZ is direction 6 even though the node's
                # third nodal DOF is RZ.
                labels = [
                    ("UX", "In-plane translation X"),
                    ("UY", "In-plane translation Y"),
                    ("—", "UZ is unavailable in a 2D frame"),
                    ("—", "RX is unavailable in a 2D frame"),
                    ("—", "RY is unavailable in a 2D frame"),
                    ("RZ", "Out-of-plane rotation about local Z"),
                ]
                return labels, {1, 2, 6}

            # twoNodeLink uses its 2D basic directions 1, 2, 3.
            labels = [
                ("UX", "In-plane translation X"),
                ("UY", "In-plane translation Y"),
                ("RZ", "Out-of-plane rotation in 2D twoNodeLink"),
                ("—", "Not available in a 2D twoNodeLink"),
                ("—", "Not available in a 2D twoNodeLink"),
                ("—", "Not available in a 2D twoNodeLink"),
            ]
            return labels, {1, 2, 3}

        if self.ndm == 3 and self.ndf >= 6:
            return labels, {1, 2, 3, 4, 5, 6}

        # Translation-only or uncommon model builders: expose only the
        # physical translational directions that the nodal model can carry.
        allowed = {
            direction
            for direction in (1, 2, 3)
            if direction <= self.ndf
        }
        return labels, allowed

    def _allowed_spring_directions(
        self,
        connection_type: str | None = None,
    ) -> set[int]:
        return self._direction_profile(connection_type)[1]

    def _refresh_direction_rows(self, connection_type: str) -> None:
        labels, allowed = self._direction_profile(connection_type)
        self.display_dof_labels = labels
        spring_mode = connection_type in {
            "zeroLength",
            "twoNodeLink",
            "semiRigid",
        }
        for direction, (label, meaning) in enumerate(labels, start=1):
            index = direction - 1
            available = spring_mode and direction in allowed
            self.dof_row_labels[index].setText(
                f"{label} · dir {direction}<br>"
                f"<span style='color:#788897'>{meaning}</span>"
            )
            self.dof_checks[index].setEnabled(available)
            if not available:
                self.dof_checks[index].setChecked(False)
            self._sync_dof_row(
                index,
                self.dof_checks[index].isChecked(),
            )

    def _sync_two_node_link_options(self) -> None:
        is_link = self.connection_type.currentText() == "twoNodeLink"
        self.link_group.setEnabled(is_link)
        p_count = 2 if self.ndm == 2 else 4
        s_count = 1 if self.ndm == 2 else 2
        for index, spin in enumerate(self.link_pdelta_spins):
            spin.setEnabled(
                is_link
                and self.link_pdelta_enable.isChecked()
                and index < p_count
            )
        for index, spin in enumerate(self.link_shear_spins):
            spin.setEnabled(
                is_link
                and self.link_shear_enable.isChecked()
                and index < s_count
            )
        self.link_mass.setEnabled(is_link)
        if hasattr(self, "orientation_tab_index"):
            self.tabs.setTabEnabled(
                self.orientation_tab_index,
                (
                    not is_link
                    or self.link_orientation_override.isChecked()
                ),
            )

    def _connection_type_changed(self, _text: str) -> None:
        connection_type = self.connection_type.currentText()
        section_mode = connection_type == "zeroLengthSection"
        spring_mode = connection_type in {
            "zeroLength",
            "twoNodeLink",
            "semiRigid",
        }
        joint_mode = connection_type in {
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }
        kinematic_mode = connection_type in {"rigid", "pinned"}

        self.preset.setEnabled(spring_mode)
        self._refresh_direction_rows(connection_type)
        self.tabs.setTabEnabled(self.dof_tab_index, spring_mode)
        self.tabs.setTabEnabled(self.section_tab_index, section_mode)
        self.tabs.setTabEnabled(self.joint_tab_index, joint_mode)
        self.new_section_button.setEnabled(section_mode)
        self.edit_section_button.setEnabled(section_mode)
        self.section_combo.setEnabled(section_mode)

        self.to_ground.setEnabled(
            connection_type in {
                "zeroLength",
                "zeroLengthSection",
                "semiRigid",
            }
        )
        if not self.to_ground.isEnabled():
            self.to_ground.setChecked(False)

        rayleigh_supported = connection_type in {
            "zeroLength",
            "zeroLengthSection",
            "semiRigid",
            "twoNodeLink",
            "KrawinklerPanelZone",
        }
        self.do_rayleigh.setEnabled(rayleigh_supported)
        if not rayleigh_supported:
            self.do_rayleigh.setChecked(False)

        self.node_i.setEnabled(not joint_mode)
        self.node_j.setEnabled(
            not joint_mode and not self.to_ground.isChecked()
        )

        joint2d_mode = connection_type == "Joint2D"
        bcj_mode = connection_type == "BeamColumnJoint"
        lehigh_mode = connection_type == "LehighJoint2D"
        kraw_mode = connection_type == "KrawinklerPanelZone"
        self.new_joint_material_button.setEnabled(joint_mode)
        self.joint2d_material_group.setEnabled(joint2d_mode)
        self.bcj_group.setEnabled(bcj_mode)
        self.bcj_factor_group.setEnabled(bcj_mode)
        self.lehigh_group.setEnabled(lehigh_mode)
        self.kraw_group.setEnabled(kraw_mode)
        for combo in self.interface_material_combos:
            combo.setEnabled(joint2d_mode)
        self.large_disp.setEnabled(joint2d_mode)
        self.joint_center_tag.setEnabled(joint2d_mode)
        for spin in (self.rigid_a, self.rigid_e, self.rigid_i):
            spin.setEnabled(kraw_mode)

        if kraw_mode:
            self.joint_nodes_group.setTitle(
                "External nodes · Left → Top → Right → Bottom"
            )
            labels = (
                "Left node:",
                "Top node:",
                "Right node:",
                "Bottom node:",
            )
        elif lehigh_mode:
            self.joint_nodes_group.setTitle(
                "External nodes · Node 1 → 4 counter-clockwise"
            )
            labels = ("Node 1:", "Node 2:", "Node 3:", "Node 4:")
        elif bcj_mode:
            self.joint_nodes_group.setTitle(
                (
                    "External nodes · N1 Bottom → N2 Right → "
                    "N3 Top → N4 Left"
                    if self.ndm == 2
                    else (
                        "External nodes · N1↔N3 height/column chord · "
                        "N2↔N4 width/beam chord"
                    )
                )
            )
            labels = ("Node 1:", "Node 2:", "Node 3:", "Node 4:")
        elif joint2d_mode:
            self.joint_nodes_group.setTitle(
                "External nodes · cyclic clockwise or counter-clockwise"
            )
            labels = ("Node 1:", "Node 2:", "Node 3:", "Node 4:")
        else:
            self.joint_nodes_group.setTitle("External joint nodes")
            labels = ("Node 1:", "Node 2:", "Node 3:", "Node 4:")
        for label_widget, text_value in zip(
            self.joint_node_labels,
            labels,
        ):
            label_widget.setText(text_value)

        if (
            bcj_mode
            and self._original_connection_type != "BeamColumnJoint"
        ):
            current_tags = [spin.value() for spin in self.joint_node_spins]
            if (
                len(set(current_tags)) == 4
                and all(tag in self.node_positions for tag in current_tags)
            ):
                if self.ndm == 2:
                    top = max(
                        current_tags,
                        key=lambda tag: float(
                            self.node_positions[tag][1]
                        ),
                    )
                    bottom = min(
                        current_tags,
                        key=lambda tag: float(
                            self.node_positions[tag][1]
                        ),
                    )
                    right = max(
                        current_tags,
                        key=lambda tag: float(
                            self.node_positions[tag][0]
                        ),
                    )
                    left = min(
                        current_tags,
                        key=lambda tag: float(
                            self.node_positions[tag][0]
                        ),
                    )
                    # Match the BeamColumnJoint convention used in
                    # the OpenSees reference figure/example:
                    # N1 = bottom, N2 = right, N3 = top, N4 = left.
                    ordered = [bottom, right, top, left]
                    if len(set(ordered)) == 4:
                        for spin, tag in zip(
                            self.joint_node_spins,
                            ordered,
                        ):
                            spin.setValue(int(tag))
                else:
                    # Start from the current cyclic order, then make the
                    # opposite chord with the strongest global-Z alignment
                    # Node 1↔3. Keep Node 1 on the lower end of that chord,
                    # matching the BeamColumnJoint reference convention,
                    # while preserving a cyclic node sequence.
                    cycle = list(current_tags)
                    pair_13 = (cycle[0], cycle[2])
                    pair_24 = (cycle[1], cycle[3])

                    def _verticality(pair: tuple[int, int]) -> float:
                        a = self.node_positions[pair[0]]
                        b = self.node_positions[pair[1]]
                        vector = tuple(
                            float(b[axis]) - float(a[axis])
                            for axis in range(3)
                        )
                        length = _norm(vector)
                        return (
                            abs(vector[2]) / length
                            if length > 1.0e-14
                            else -1.0
                        )

                    if _verticality(pair_24) > _verticality(pair_13):
                        cycle = [
                            cycle[1],
                            cycle[2],
                            cycle[3],
                            cycle[0],
                        ]
                    a = self.node_positions[cycle[0]]
                    c = self.node_positions[cycle[2]]
                    if float(a[2]) > float(c[2]):
                        cycle = [
                            cycle[2],
                            cycle[3],
                            cycle[0],
                            cycle[1],
                        ]
                    for spin, tag in zip(
                        self.joint_node_spins,
                        cycle,
                    ):
                        spin.setValue(int(tag))

        if lehigh_mode:
            current_tags = [spin.value() for spin in self.joint_node_spins]
            if (
                len(set(current_tags)) == 4
                and all(tag in self.node_positions for tag in current_tags)
            ):
                points = [self.node_positions[tag] for tag in current_tags]
                signed_area2 = sum(
                    float(points[index][0])
                    * float(points[(index + 1) % 4][1])
                    - float(points[(index + 1) % 4][0])
                    * float(points[index][1])
                    for index in range(4)
                )
                if signed_area2 < 0.0:
                    # Preserve Node 1 and reverse traversal to obtain CCW.
                    reordered = [
                        current_tags[0],
                        current_tags[3],
                        current_tags[2],
                        current_tags[1],
                    ]
                    for spin, tag in zip(
                        self.joint_node_spins,
                        reordered,
                    ):
                        spin.setValue(int(tag))

        if joint_mode:
            self.tabs.setCurrentIndex(self.joint_tab_index)
        elif section_mode:
            self.tabs.setCurrentIndex(self.section_tab_index)
        elif spring_mode and self.tabs.currentIndex() in {
            self.section_tab_index,
            self.joint_tab_index,
        }:
            self.tabs.setCurrentIndex(self.dof_tab_index)
        elif kinematic_mode and self.tabs.currentIndex() in {
            self.section_tab_index,
            self.joint_tab_index,
            self.dof_tab_index,
        }:
            self.tabs.setCurrentIndex(0)

        if connection_type == "semiRigid":
            target = (
                6
                if self.ndm == 2 and self.ndf == 3
                else min(6, self.ndf)
            )
            allowed = self._allowed_spring_directions(connection_type)
            if not any(item.isChecked() for item in self.dof_checks):
                for direction, check in enumerate(
                    self.dof_checks,
                    start=1,
                ):
                    if direction in allowed:
                        check.setChecked(direction == target)

        self._sync_two_node_link_options()
        self._update_node_status()

    def _preset_changed(self, index: int) -> None:
        if index <= 0:
            return
        self._apply_preset_index(index)

    def _apply_preset_index(self, index: int) -> None:
        connection_type = self.connection_type.currentText()
        directions = set(self.preset.itemData(index) or ())
        if (
            connection_type == "twoNodeLink"
            and self.ndm == 2
            and self.ndf == 3
        ):
            # The same physical RZ mechanism is direction 3 for a 2D
            # twoNodeLink, but direction 6 for zeroLength.
            directions = {
                3 if direction == 6 else direction
                for direction in directions
            }
        allowed = self._allowed_spring_directions(connection_type)
        directions.intersection_update(allowed)

        for direction, check in enumerate(self.dof_checks, start=1):
            check.setChecked(direction in directions)

        label = self.preset.itemText(index)
        if "translational slip" in label.lower():
            self._select_material_type(
                0,
                {"Pinching4", "Hysteretic", "ElasticPPGap", "Steel02", "Elastic"},
            )
        elif "rotational hinge" in label.lower():
            rotational_direction = (
                3
                if (
                    connection_type == "twoNodeLink"
                    and self.ndm == 2
                    and self.ndf == 3
                )
                else 6
            )
            if rotational_direction in allowed:
                self._select_material_type(
                    rotational_direction - 1,
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

        pending_tags = {
            material.tag for material in self.pending_materials
        }
        joint_combo_specs: list[tuple[QComboBox, str, object]] = []
        if hasattr(self, "panel_material_combo"):
            joint_combo_specs.append(
                (
                    self.panel_material_combo,
                    "Select panel material...",
                    None,
                )
            )
        for combo in getattr(self, "interface_material_combos", []):
            joint_combo_specs.append(
                (combo, "Rigid interface (0)", 0)
            )
        for combo in getattr(self, "bcj_material_combos", []):
            joint_combo_specs.append(
                (combo, "Select material...", None)
            )
        for combo in getattr(self, "lehigh_material_combos", []):
            joint_combo_specs.append(
                (combo, "Select material...", None)
            )

        for combo, first_label, first_data in joint_combo_specs:
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first_label, first_data)
            for tag in sorted(self.materials):
                material = self.materials[tag]
                suffix = " · pending" if tag in pending_tags else ""
                combo.addItem(
                    f"{tag} - {material.name}{suffix}",
                    int(tag),
                )
            index = combo.findData(previous)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _create_joint_material(self) -> None:
        next_tag = max(self.materials, default=0) + 1
        dialog = MaterialDialog(
            next_tag=next_tag,
            units=self.units,
            materials=self.materials,
            parent=self,
        )
        if not dialog.exec():
            return

        try:
            dependencies = dialog.pending_materials()
            material = dialog.material_data()
            candidates = list(dependencies) + [material]
            used = set(self.materials)
            for candidate in candidates:
                if candidate.tag in used:
                    raise ValueError(
                        f"Material tag {candidate.tag} already exists."
                    )
                used.add(candidate.tag)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Joint Material",
                str(exc),
            )
            return

        for candidate in candidates:
            copied = MaterialData.from_dict(candidate.to_dict())
            self.materials[copied.tag] = copied
            self.pending_materials.append(copied)

        new_tag = int(material.tag)
        self._refresh_material_combos()
        connection_type = self.connection_type.currentText()
        target_combos: list[QComboBox] = []
        if connection_type in {"Joint2D", "KrawinklerPanelZone"}:
            target_combos = [self.panel_material_combo]
        elif connection_type == "BeamColumnJoint":
            target_combos = list(self.bcj_material_combos)
        elif connection_type == "LehighJoint2D":
            target_combos = list(self.lehigh_material_combos)

        target = next(
            (
                combo
                for combo in target_combos
                if combo.currentData() in {None, 0}
            ),
            target_combos[0] if target_combos else None,
        )
        if target is not None:
            index = target.findData(new_tag)
            if index >= 0:
                target.setCurrentIndex(index)

    def _create_dof_material(self, index: int) -> None:
        next_tag = max(self.materials, default=0) + 1
        dialog = MaterialDialog(
            next_tag=next_tag,
            units=self.units,
            materials=self.materials,
            parent=self,
        )
        if not dialog.exec():
            return

        try:
            dependencies = dialog.pending_materials()
            material = dialog.material_data()
            candidates = list(dependencies) + [material]
            used = set(self.materials)
            for candidate in candidates:
                if candidate.tag in used:
                    raise ValueError(
                        f"Material tag {candidate.tag} already exists."
                    )
                used.add(candidate.tag)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Connection Material",
                str(exc),
            )
            return

        for candidate in candidates:
            copied = MaterialData.from_dict(candidate.to_dict())
            self.materials[copied.tag] = copied
            self.pending_materials.append(copied)

        self._refresh_material_combos(
            select_row=index,
            select_material_tag=material.tag,
        )
        self.dof_checks[index].setChecked(True)
        self._sync_material_type(index)

    def _build_dof_chain(self, index: int) -> None:
        label = self.display_dof_labels[index][0]
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
        direction = index + 1
        available = (
            direction
            in self._allowed_spring_directions(
                self.connection_type.currentText()
            )
        )
        self.material_combos[index].setEnabled(bool(checked) and available)
        self.new_material_buttons[index].setEnabled(available)
        self.chain_buttons[index].setEnabled(available)
        self.test_buttons[index].setEnabled(
            bool(checked)
            and available
            and self.material_combos[index].currentData() is not None
        )
        self.material_type_labels[index].setEnabled(
            bool(checked) and available
        )

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
        zero_length = self.connection_type.currentText() in {
            "zeroLength",
            "zeroLengthSection",
            "semiRigid",
            "pinned",
        }
        if zero_length and distance > 1.0e-7:
            self.node_status.setText(
                f"Node separation = {distance:.6g}. {self.connection_type.currentText()} requires "
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
        connection_type = self.connection_type.currentText()
        section_mode = connection_type == "zeroLengthSection"
        spring_mode = connection_type in {
            "zeroLength",
            "twoNodeLink",
            "semiRigid",
        }
        joint_mode = connection_type in {
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }

        materials_by_dof: dict[int, int] = {}
        if spring_mode:
            allowed_directions = self._allowed_spring_directions(
                connection_type
            )
            for direction, (check, combo) in enumerate(
                zip(self.dof_checks, self.material_combos),
                start=1,
            ):
                if (
                    direction not in allowed_directions
                    or not check.isChecked()
                ):
                    continue
                material_tag = combo.currentData()
                if material_tag is None:
                    raise ValueError(
                        f"Direction {direction} is active but has no material."
                    )
                materials_by_dof[direction] = int(material_tag)

            if not materials_by_dof:
                raise ValueError(
                    "Enable at least one valid connection direction."
                )

        section_tag: int | None = None
        if section_mode:
            selected_section = self.section_combo.currentData()
            if selected_section is None:
                raise ValueError(
                    "zeroLengthSection requires a Section assignment."
                )
            section_tag = int(selected_section)
            if section_tag not in self.sections:
                raise ValueError(
                    f"Section {section_tag} is not available."
                )

        if connection_type in {"zeroLength", "semiRigid"}:
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
                    "not directly as a force-deformation spring DOF."
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
            connection_type in {
                "zeroLength",
                "zeroLengthSection",
                "semiRigid",
                "pinned",
            }
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
                        f"{connection_type} requires coincident nodes. "
                        f"Current separation is {distance:.6g}."
                    )

        parameters: dict[str, object] = {}
        if connection_type == "twoNodeLink":
            parameters["orientation_override"] = (
                self.link_orientation_override.isChecked()
            )
            if self.link_pdelta_enable.isChecked():
                count = 2 if self.ndm == 2 else 4
                p_delta = [
                    float(spin.value())
                    for spin in self.link_pdelta_spins[:count]
                ]
                if self.ndm == 2:
                    if sum(p_delta) > 1.0 + 1.0e-12:
                        raise ValueError(
                            "TwoNodeLink P-Delta end-moment ratios must sum "
                            "to ≤ 1.0 in 2D."
                        )
                else:
                    if (
                        p_delta[0] + p_delta[1] > 1.0 + 1.0e-12
                        or p_delta[2] + p_delta[3] > 1.0 + 1.0e-12
                    ):
                        raise ValueError(
                            "TwoNodeLink 3D P-Delta ratio pairs must each "
                            "sum to ≤ 1.0."
                        )
                parameters["p_delta"] = p_delta
            else:
                parameters["p_delta"] = []

            if self.link_shear_enable.isChecked():
                count = 1 if self.ndm == 2 else 2
                parameters["shear_dist"] = [
                    float(spin.value())
                    for spin in self.link_shear_spins[:count]
                ]
            else:
                parameters["shear_dist"] = []
            parameters["mass"] = float(self.link_mass.value())

        node_i = self.node_i.value()
        node_j = self.node_j.value()
        referenced_materials: dict[int, int] = dict(materials_by_dof)

        if joint_mode:
            external_nodes = [
                spin.value() for spin in self.joint_node_spins
            ]
            if len(set(external_nodes)) != 4:
                raise ValueError(
                    "Joint external nodes must be four distinct tags."
                )
            parameters["external_nodes"] = external_nodes
            node_i, node_j = external_nodes[0], external_nodes[1]

            if connection_type == "Joint2D":
                panel_tag = self.panel_material_combo.currentData()
                if panel_tag is None:
                    raise ValueError(
                        "Joint2D requires a panel material."
                    )
                panel_tag = int(panel_tag)
                parameters["panel_material"] = panel_tag
                referenced_materials[100] = panel_tag
                interfaces = [
                    int(combo.currentData() or 0)
                    for combo in self.interface_material_combos
                ]
                parameters["interface_materials"] = interfaces
                parameters["large_disp"] = int(
                    self.large_disp.currentData()
                )
                if self.joint_center_tag.value() > 0:
                    parameters["imported_center_node_tag"] = int(
                        self.joint_center_tag.value()
                    )
                for index, material_tag in enumerate(
                    interfaces,
                    start=101,
                ):
                    if material_tag > 0:
                        referenced_materials[index] = material_tag

            elif connection_type == "BeamColumnJoint":
                component_materials: list[int] = []
                for index, combo in enumerate(
                    self.bcj_material_combos,
                    start=1,
                ):
                    material_tag = combo.currentData()
                    if material_tag is None:
                        raise ValueError(
                            "BeamColumnJoint requires all 13 component "
                            f"materials; Mat{index} is not assigned."
                        )
                    component_materials.append(int(material_tag))
                    referenced_materials[200 + index] = int(material_tag)
                parameters["component_materials"] = component_materials
                parameters["height_factor"] = float(
                    self.bcj_height_factor.value()
                )
                parameters["width_factor"] = float(
                    self.bcj_width_factor.value()
                )

            elif connection_type == "LehighJoint2D":
                mode_materials: list[int] = []
                for index, combo in enumerate(
                    self.lehigh_material_combos,
                    start=1,
                ):
                    material_tag = combo.currentData()
                    if material_tag is None:
                        raise ValueError(
                            "LehighJoint2D requires all 9 deformation-mode "
                            f"materials; Mat{index} is not assigned."
                        )
                    mode_materials.append(int(material_tag))
                    referenced_materials[300 + index] = int(material_tag)
                parameters["mode_materials"] = mode_materials

            else:
                panel_tag = self.panel_material_combo.currentData()
                if panel_tag is None:
                    raise ValueError(
                        "KrawinklerPanelZone requires a panel material."
                    )
                panel_tag = int(panel_tag)
                parameters["panel_material"] = panel_tag
                referenced_materials[100] = panel_tag
                rigid_a = float(self.rigid_a.value())
                rigid_e = float(self.rigid_e.value())
                rigid_i = float(self.rigid_i.value())
                if min(rigid_a, rigid_e, rigid_i) <= 0.0:
                    raise ValueError(
                        "KrawinklerPanelZone requires positive rigid-link "
                        "A, E, and Iz values."
                    )
                parameters.update({
                    "rigid_A": rigid_a,
                    "rigid_E": rigid_e,
                    "rigid_I": rigid_i,
                })

        pending_materials = (
            self._pending_materials_in_use(referenced_materials)
            if referenced_materials
            else []
        )

        return {
            "tag": self.tag.value(),
            "name": self.name.text().strip()
            or f"Connection {self.tag.value()}",
            "connection_type": connection_type,
            "node_i": node_i,
            "node_j": node_j,
            "to_ground": (
                self.to_ground.isChecked()
                if connection_type in {
                    "zeroLength",
                    "zeroLengthSection",
                    "semiRigid",
                }
                else False
            ),
            "materials_by_dof": materials_by_dof,
            "section_tag": section_tag,
            "orient_x": x,
            "orient_y": y,
            "do_rayleigh": (
                self.do_rayleigh.isChecked()
                if connection_type in {
                    "zeroLength",
                    "zeroLengthSection",
                    "semiRigid",
                    "twoNodeLink",
                    "KrawinklerPanelZone",
                }
                else False
            ),
            "parameters": parameters,
            "pending_materials": (
                pending_materials
                if not section_mode
                else [
                    MaterialData.from_dict(material.to_dict())
                    for material in self.pending_materials
                ]
            ),
            "pending_section_operations": [
                (
                    operation,
                    original_tag,
                    SectionData.from_dict(section.to_dict()),
                )
                for operation, original_tag, section
                in self.pending_section_operations
            ],
        }

    def _validate_and_accept(self) -> None:
        connection_type = self.connection_type.currentText()
        needs_uniaxial = connection_type in {
            "zeroLength",
            "twoNodeLink",
            "semiRigid",
            "Joint2D",
            "BeamColumnJoint",
            "LehighJoint2D",
            "KrawinklerPanelZone",
        }
        if needs_uniaxial and not self.materials:
            target_tab = (
                self.joint_tab_index
                if connection_type in {
                    "Joint2D",
                    "BeamColumnJoint",
                    "LehighJoint2D",
                    "KrawinklerPanelZone",
                }
                else self.dof_tab_index
            )
            self.tabs.setCurrentIndex(target_tab)
            QMessageBox.information(
                self,
                "Connection / Joint Builder",
                "This connection type needs at least one UniaxialMaterial. "
                "Create a material first or use New... in the DOF Materials tab.",
            )
            return
        try:
            self.spec()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Connection / Joint Builder",
                str(exc),
            )
            return
        self.accept()

