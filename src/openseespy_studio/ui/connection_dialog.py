from __future__ import annotations

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
    QSpinBox,
    QVBoxLayout,
)

from ..project import ConnectionData, MaterialData


def _float_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(8)
    spin.setRange(-1.0e12, 1.0e12)
    spin.setValue(float(value))
    return spin


class ConnectionDialog(QDialog):
    DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

    def __init__(
        self,
        materials: dict[int, MaterialData],
        connection: ConnectionData | None = None,
        *,
        next_tag: int = 1,
        initial_node_i: int = 1,
        initial_node_j: int = 2,
        default_to_ground: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Connection / Spring Editor")
        self.setModal(True)
        self.resize(560, 520)
        self.materials = materials

        root = QVBoxLayout(self)
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

        self.do_rayleigh = QCheckBox("Include in Rayleigh damping")
        self.do_rayleigh.setChecked(
            connection.do_rayleigh if connection else False
        )

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.connection_type)
        form.addRow("Node I:", self.node_i)
        form.addRow("Node J:", self.node_j)
        form.addRow("Spring to ground:", self.to_ground)
        form.addRow("Rayleigh:", self.do_rayleigh)
        root.addLayout(form)

        hint = QLabel(
            "Enable 1–6 DOFs and assign one uniaxial material to each active DOF."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        dof_group = QGroupBox("Directional materials")
        dof_layout = QFormLayout(dof_group)
        self.dof_checks: list[QCheckBox] = []
        self.material_combos: list[QComboBox] = []

        for dof, label in enumerate(self.DOF_LABELS, start=1):
            row = QHBoxLayout()
            check = QCheckBox("Enabled")
            combo = QComboBox()
            for tag in sorted(self.materials):
                material = self.materials[tag]
                combo.addItem(
                    f"{tag} - {material.name} ({material.material_type})",
                    tag,
                )
            row.addWidget(check)
            row.addWidget(combo, 1)

            holder = QGroupBox()
            holder.setFlat(True)
            holder.setLayout(row)
            dof_layout.addRow(f"{label} (dir {dof}):", holder)

            self.dof_checks.append(check)
            self.material_combos.append(combo)

        root.addWidget(dof_group)

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
            self.dof_checks[0].setChecked(True)

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
        for spin in self.oy:
            oy_row.addWidget(spin)

        ox_holder = QGroupBox()
        oy_holder = QGroupBox()
        ox_holder.setFlat(True)
        oy_holder.setFlat(True)
        ox_holder.setLayout(ox_row)
        oy_holder.setLayout(oy_row)
        orient.addRow("Local X:", ox_holder)
        orient.addRow("Local Y:", oy_holder)
        root.addWidget(orient_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.to_ground.toggled.connect(self._sync_ground_state)
        self._sync_ground_state(self.to_ground.isChecked())

    def _sync_ground_state(self, checked: bool) -> None:
        self.node_j.setEnabled(not checked)

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
                    f"DOF {dof} is enabled but has no material."
                )
            materials_by_dof[dof] = int(material_tag)

        if not materials_by_dof:
            raise ValueError("Enable at least one connection DOF.")

        return {
            "tag": self.tag.value(),
            "name": self.name.text().strip()
            or f"Connection {self.tag.value()}",
            "connection_type": self.connection_type.currentText(),
            "node_i": self.node_i.value(),
            "node_j": self.node_j.value(),
            "to_ground": self.to_ground.isChecked(),
            "materials_by_dof": materials_by_dof,
            "orient_x": tuple(spin.value() for spin in self.ox),
            "orient_y": tuple(spin.value() for spin in self.oy),
            "do_rayleigh": self.do_rayleigh.isChecked(),
        }

    def _validate_and_accept(self) -> None:
        if not self.materials:
            QMessageBox.warning(
                self,
                "Connection Editor",
                "Create at least one uniaxial material first.",
            )
            return
        try:
            self.spec()
        except ValueError as exc:
            QMessageBox.warning(self, "Connection Editor", str(exc))
            return
        self.accept()
