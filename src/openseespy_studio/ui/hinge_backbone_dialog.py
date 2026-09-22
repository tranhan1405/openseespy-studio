from __future__ import annotations

from PySide6.QtWidgets import (
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
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..hinge_backbone import (
    HingeBackbonePoint,
    build_symmetric_hysteretic_hinge,
)
from ..project import MaterialData
from ..units import UnitSystem


class HingeBackboneDialog(QDialog):
    """Build a transparent three-point moment-rotation hinge backbone."""

    POINT_LABELS = (
        "Point 1 · cracking / first breakpoint",
        "Point 2 · yield / main breakpoint",
        "Point 3 · ultimate / terminal breakpoint",
    )

    def __init__(
        self,
        *,
        next_tag: int,
        units=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Hinge Backbone Builder")
        self.resize(760, 650)
        self._units = UnitSystem.from_mapping(units)

        root = QVBoxLayout(self)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            self.scroll.horizontalScrollBarPolicy().ScrollBarAlwaysOff
        )

        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(4, 4, 4, 4)
        content.setSpacing(8)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        intro = QLabel(
            "Research workflow: 1) obtain a section/member response curve; "
            "2) identify three characteristic points; 3) convert the "
            "deformation basis explicitly; 4) create a Hysteretic "
            "moment-rotation material. Element assignment is intentionally "
            "kept separate: use Model > ZeroLength / Link afterwards."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        content.addWidget(intro)

        source_group = QGroupBox("1 · Response source")
        source_form = QFormLayout(source_group)

        self.source_kind = QComboBox()
        self.source_kind.addItem(
            "SARE / OpenSees moment-curvature result",
            "sare_moment_curvature",
        )
        self.source_kind.addItem(
            "Response-2000 / external section analysis",
            "response_2000",
        )
        self.source_kind.addItem(
            "Published / manually identified backbone",
            "manual",
        )
        source_form.addRow("Source:", self.source_kind)

        self.source_note = QLineEdit()
        self.source_note.setPlaceholderText(
            "Optional specimen, paper, file, section ID, or analysis note"
        )
        source_form.addRow("Traceability note:", self.source_note)

        self.basis = QComboBox()
        self.basis.addItem(
            "Moment–rotation M–θ · deformation already in rad",
            "moment_rotation",
        )
        self.basis.addItem(
            "Moment–curvature M–κ · convert with θ = κ × L_eq",
            "moment_curvature",
        )
        self.basis.currentIndexChanged.connect(self._sync_basis)
        source_form.addRow("Input basis:", self.basis)

        content.addWidget(source_group)

        points_group = QGroupBox("2 · Characteristic positive-branch points")
        points_layout = QVBoxLayout(points_group)

        self.points = QTableWidget(3, 3)
        self.points.setHorizontalHeaderLabels(
            [
                "Characteristic point",
                f"Moment [{self._units.moment_label}]",
                "Deformation [rad]",
            ]
        )
        self._moment_spins: list[QDoubleSpinBox] = []
        self._deformation_spins: list[QDoubleSpinBox] = []
        for row, label in enumerate(self.POINT_LABELS):
            label_item = QTableWidgetItem(label)
            self.points.setItem(row, 0, label_item)

            moment = QDoubleSpinBox()
            moment.setDecimals(8)
            moment.setRange(0.0, 1.0e15)
            moment.setSingleStep(1.0)
            self.points.setCellWidget(row, 1, moment)
            self._moment_spins.append(moment)

            deformation = QDoubleSpinBox()
            deformation.setDecimals(12)
            deformation.setRange(0.0, 1.0e9)
            deformation.setSingleStep(0.0001)
            self.points.setCellWidget(row, 2, deformation)
            self._deformation_spins.append(deformation)

        self.points.horizontalHeader().setStretchLastSection(True)
        points_layout.addWidget(self.points)

        point_note = QLabel(
            "SARE does not auto-label cracking, yield, or ultimate from a "
            "monotonic curve. The researcher confirms these points so the "
            "calibration remains traceable and reviewable."
        )
        point_note.setWordWrap(True)
        point_note.setStyleSheet("color: #617080;")
        points_layout.addWidget(point_note)

        content.addWidget(points_group)

        conversion_group = QGroupBox("3 · Deformation conversion")
        conversion_form = QFormLayout(conversion_group)

        self.hinge_length = QDoubleSpinBox()
        self.hinge_length.setDecimals(8)
        self.hinge_length.setRange(0.0, 1.0e12)
        self.hinge_length.setSingleStep(0.01)
        self.hinge_length.setSuffix(f" {self._units.length}")
        conversion_form.addRow(
            "Equivalent hinge length L_eq:",
            self.hinge_length,
        )

        self.conversion_note = QLabel()
        self.conversion_note.setWordWrap(True)
        conversion_form.addRow(self.conversion_note)
        content.addWidget(conversion_group)

        cyclic_group = QGroupBox("4 · Cyclic rule and output material")
        cyclic_form = QFormLayout(cyclic_group)

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(int(next_tag))
        cyclic_form.addRow("Material tag:", self.tag)

        self.name = QLineEdit(f"Hinge Backbone {int(next_tag)}")
        cyclic_form.addRow("Material name:", self.name)

        self.pinch_x = self._factor_spin(1.0, 0.0, 1.0)
        self.pinch_y = self._factor_spin(1.0, 0.0, 1.0)
        self.damage_1 = self._factor_spin(0.0, 0.0, 1.0e6)
        self.damage_2 = self._factor_spin(0.0, 0.0, 1.0e6)
        self.beta = self._factor_spin(0.0, -1.0e6, 1.0e6)

        cyclic_form.addRow("pinchX:", self.pinch_x)
        cyclic_form.addRow("pinchY:", self.pinch_y)
        cyclic_form.addRow("damage1:", self.damage_1)
        cyclic_form.addRow("damage2:", self.damage_2)
        cyclic_form.addRow("beta:", self.beta)

        cyclic_note = QLabel(
            "Important: M–κ or M–θ defines the backbone only. Pinching, "
            "unloading/reloading behavior and cyclic deterioration are not "
            "identified by the monotonic section curve. The initial values "
            "above are explicit user-editable assumptions and should be "
            "calibrated separately against cyclic evidence when available."
        )
        cyclic_note.setWordWrap(True)
        cyclic_note.setStyleSheet(
            "padding: 7px; background: #fff4df; color: #7a5600;"
        )
        cyclic_form.addRow(cyclic_note)

        content.addWidget(cyclic_group)

        next_step = QLabel(
            "Next: Model > ZeroLength / Link... > Rotational hinge RZ > "
            "select this Hysteretic material. Then create the Cyclic analysis "
            "protocol under Analysis > Analysis Wizard > Cyclic."
        )
        next_step.setWordWrap(True)
        next_step.setStyleSheet(
            "padding: 7px; background: #f7f7f7; color: #526578;"
        )
        content.addWidget(next_step)
        content.addStretch(1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText(
            "Create Hysteretic Material"
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._sync_basis()

    @staticmethod
    def _factor_spin(
        value: float,
        minimum: float,
        maximum: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(8)
        spin.setRange(float(minimum), float(maximum))
        spin.setValue(float(value))
        spin.setSingleStep(0.05)
        return spin

    def _sync_basis(self, *_args) -> None:
        basis = str(self.basis.currentData())
        curvature = basis == "moment_curvature"
        self.hinge_length.setEnabled(curvature)

        if curvature:
            self.points.setHorizontalHeaderItem(
                2,
                QTableWidgetItem(
                    f"Curvature [1/{self._units.length}]"
                ),
            )
            self.conversion_note.setText(
                "Explicit equivalent-hinge assumption: θ = κ × L_eq. "
                "SARE does not estimate L_eq automatically."
            )
        else:
            self.points.setHorizontalHeaderItem(
                2,
                QTableWidgetItem("Rotation θ [rad]"),
            )
            self.conversion_note.setText(
                "No kinematic conversion is applied: the entered "
                "deformations are used directly as hinge rotations."
            )

    def material_data(self) -> MaterialData:
        basis = str(self.basis.currentData())
        points: list[HingeBackbonePoint] = []

        for moment_spin, deformation_spin in zip(
            self._moment_spins,
            self._deformation_spins,
        ):
            moment_nm = self._units.moment_to_nm_value(
                moment_spin.value()
            )
            deformation = float(deformation_spin.value())
            if basis == "moment_curvature":
                deformation = deformation / self._units.length_to_m
            points.append(
                HingeBackbonePoint(
                    moment_nm=moment_nm,
                    deformation=deformation,
                )
            )

        hinge_length_m = None
        if basis == "moment_curvature":
            hinge_length_m = self._units.length_to_m_value(
                self.hinge_length.value()
            )

        return build_symmetric_hysteretic_hinge(
            tag=int(self.tag.value()),
            name=self.name.text(),
            points=points,
            basis=basis,
            equivalent_hinge_length_m=hinge_length_m,
            source_kind=str(self.source_kind.currentData()),
            source_note=self.source_note.text(),
            pinch_x=float(self.pinch_x.value()),
            pinch_y=float(self.pinch_y.value()),
            damage_1=float(self.damage_1.value()),
            damage_2=float(self.damage_2.value()),
            beta=float(self.beta.value()),
        )

    def _validate_and_accept(self) -> None:
        try:
            self.material_data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Hinge Backbone Builder",
                str(exc),
            )
            return
        self.accept()
