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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..moment_curvature import MomentCurvatureSpec
from ..project import ProjectDatabase
from ..units import UnitSystem


class MomentCurvatureDialog(QDialog):
    def __init__(
        self,
        project: ProjectDatabase,
        parent=None,
        *,
        new_section_callback=None,
    ):
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)
        self._new_section_callback = new_section_callback

        self.setWindowTitle("Moment-Curvature")
        self.resize(620, 520)
        self.setModal(True)

        root = QVBoxLayout(self)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(6, 6, 6, 6)
        content.setSpacing(8)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        intro = QLabel(
            "Run an isolated OpenSees zeroLengthSection test for one existing "
            "Section. SARE applies the axial preload first, holds it constant, "
            "then uses DisplacementControl on the bending rotation DOF to "
            "generate the section M–κ curve. The structural model is not "
            "modified."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "padding: 8px; background: #eef4fb; color: #40566c;"
        )
        content.addWidget(intro)

        setup_group = QGroupBox("Section test")
        form = QFormLayout(setup_group)

        self.section = QComboBox()
        self.section_new = QPushButton("New Section...")
        self.section_new.setEnabled(callable(self._new_section_callback))
        self.section_new.clicked.connect(self._create_section_dependency)
        self.section_holder = QWidget()
        section_row = QHBoxLayout(self.section_holder)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(4)
        section_row.addWidget(self.section, 1)
        section_row.addWidget(self.section_new)
        self._refresh_section_choices()
        form.addRow("Section:", self.section_holder)

        self.axis = QComboBox()
        if int(project.model.ndm) == 2:
            self.axis.addItem("Mz · 2D bending", "Mz")
        else:
            self.axis.addItem("Mz · about local/global z", "Mz")
            self.axis.addItem("My · about local/global y", "My")
        form.addRow("Bending axis:", self.axis)

        self.axial_load = QDoubleSpinBox()
        self.axial_load.setDecimals(8)
        self.axial_load.setRange(-1.0e15, 1.0e15)
        self.axial_load.setValue(0.0)
        self.axial_load.setSingleStep(10.0)
        self.axial_load.setSuffix(f" {self.units.force}")
        form.addRow(
            "Axial load P:",
            self.axial_load,
        )

        axial_note = QLabel(
            "OpenSees sign convention is used. For the usual RC column "
            "section test, compression is normally entered as a negative "
            "axial force."
        )
        axial_note.setWordWrap(True)
        axial_note.setStyleSheet("color: #617080;")
        form.addRow(axial_note)

        self.max_curvature = QDoubleSpinBox()
        self.max_curvature.setDecimals(12)
        self.max_curvature.setRange(1.0e-15, 1.0e12)
        # Research-friendly default: 0.02 1/m converted to active 1/L units.
        self.max_curvature.setValue(0.02 * self.units.length_to_m)
        self.max_curvature.setSingleStep(max(1.0e-8, 0.002 * self.units.length_to_m))
        self.max_curvature.setSuffix(f" 1/{self.units.length}")
        form.addRow("Maximum curvature κmax:", self.max_curvature)

        self.increments = QSpinBox()
        self.increments.setRange(2, 10000)
        self.increments.setValue(100)
        form.addRow("Increments:", self.increments)

        content.addWidget(setup_group)

        solver_group = QGroupBox("Automatic OpenSees procedure")
        solver_layout = QVBoxLayout(solver_group)
        solver_note = QLabel(
            "SARE creates two coincident temporary nodes, a zeroLengthSection "
            "using the selected Section, a Constant axial-load pattern, a "
            "Linear unit-moment reference pattern, and a Static "
            "DisplacementControl analysis. These objects exist only for the "
            "isolated Job and are not inserted into the project Model Tree."
        )
        solver_note.setWordWrap(True)
        solver_layout.addWidget(solver_note)
        content.addWidget(solver_group)
        content.addStretch(1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText(
            "Run Moment-Curvature"
        )
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(project.sections)
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _refresh_section_choices(self, select_tag=None) -> None:
        current = self.section.currentData() if self.section.count() else None
        wanted = select_tag if select_tag is not None else current
        self.section.clear()
        self.section.addItem("Select Section...", None)
        for tag in sorted(self.project.sections):
            item = self.project.sections[tag]
            self.section.addItem(
                f"{tag} - {item.name} ({item.section_type})",
                int(tag),
            )
        if wanted is not None:
            index = self.section.findData(int(wanted))
            if index >= 0:
                self.section.setCurrentIndex(index)
        elif self.section.count() == 2:
            self.section.setCurrentIndex(1)
        if hasattr(self, "buttons"):
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(
                self.section.count() > 1
            )

    def _create_section_dependency(self) -> None:
        if not callable(self._new_section_callback):
            return
        section = self._new_section_callback()
        if section is None:
            return
        self._refresh_section_choices(int(section.tag))

    def spec(self) -> MomentCurvatureSpec:
        section_tag = self.section.currentData()
        if section_tag is None:
            raise ValueError(
                "Create or select a Section before running Moment-Curvature."
            )
        return MomentCurvatureSpec(
            section_tag=int(section_tag),
            axis=str(self.axis.currentData()),
            axial_load=float(self.axial_load.value()),
            max_curvature=float(self.max_curvature.value()),
            increments=int(self.increments.value()),
        )

    def _validate_and_accept(self) -> None:
        try:
            self.spec()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Moment-Curvature",
                str(exc),
            )
            return
        self.accept()
