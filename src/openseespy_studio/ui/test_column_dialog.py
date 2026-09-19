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
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..project import ProjectDatabase
from ..test_column import TestColumnSpec
from ..units import UnitSystem


def _double(
    value: float,
    low: float = 0.0,
    high: float = 1.0e20,
    decimals: int = 6,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(low, high)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


class TestColumnWizard(QDialog):
    PRESETS = (
        "Blank Column",
        "Cantilever Cyclic Test",
        "Cantilever Pushover",
        "Axial + Lateral Column",
        "Dynamic / Shake-table Column",
    )

    def __init__(
        self,
        project: ProjectDatabase,
        *,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)
        self.setWindowTitle("Quick 1D Column / Test Specimen")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.resize(650, 620)

        root = QVBoxLayout(self)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)

        intro = QLabel(
            "Create a single-line column specimen for experimental validation, "
            "cyclic/pushover studies, section tests, or simple dynamic models."
        )
        intro.setWordWrap(True)
        body_layout.addWidget(intro)

        preset_form = QFormLayout()
        self.preset = QComboBox()
        self.preset.addItems(self.PRESETS)
        preset_form.addRow("Preset:", self.preset)
        body_layout.addLayout(preset_form)

        geometry_group = QGroupBox("Geometry & formulation")
        geometry = QFormLayout(geometry_group)
        self.height = _double(3.0, 1.0e-6, 1.0e9)
        self.elements = QSpinBox()
        self.elements.setRange(1, 200)
        self.elements.setValue(1)

        self.axis = QComboBox()
        self.axis.addItem("Global Z · vertical", 3)
        self.axis.addItem("Global X", 1)
        self.axis.addItem("Global Y", 2)

        self.lateral = QComboBox()
        self.lateral.addItem("Global X", 1)
        self.lateral.addItem("Global Y", 2)
        self.lateral.addItem("Global Z", 3)

        self.planar = QCheckBox(
            "Planar test behavior · restrain out-of-plane DOFs automatically"
        )
        self.planar.setChecked(True)

        self.section = QComboBox()
        self.section.addItem("Unassigned · assign later", None)
        for tag in sorted(project.sections):
            item = project.sections[tag]
            self.section.addItem(
                f"{tag} - {item.name} ({item.section_type})",
                tag,
            )

        self.element_type = QComboBox()
        self.element_type.addItems(
            ["forceBeamColumn", "dispBeamColumn", "elasticBeamColumn"]
        )

        self.integration = QComboBox()
        self.integration.addItems(["Lobatto", "Legendre"])
        self.integration_points = QSpinBox()
        self.integration_points.setRange(2, 50)
        self.integration_points.setValue(5)

        self.transformation = QComboBox()
        self.transformation.addItem("Auto · PDelta", ("auto", "PDelta"))
        self.transformation.addItem("Auto · Linear", ("auto", "Linear"))
        self.transformation.addItem(
            "Auto · Corotational",
            ("auto", "Corotational"),
        )
        for tag in sorted(project.transformations):
            item = project.transformations[tag]
            self.transformation.addItem(
                f"{tag} - {item.name} ({item.transformation_type})",
                ("tag", tag),
            )

        geometry.addRow(
            f"Column height [{self.units.length}]:",
            self.height,
        )
        geometry.addRow("Number of elements:", self.elements)
        geometry.addRow("Column axis:", self.axis)
        geometry.addRow("Lateral/test direction:", self.lateral)
        geometry.addRow("", self.planar)
        geometry.addRow("Section:", self.section)
        geometry.addRow("Element formulation:", self.element_type)
        geometry.addRow("Beam integration:", self.integration)
        geometry.addRow("Integration points:", self.integration_points)
        geometry.addRow("Geometric transformation:", self.transformation)
        body_layout.addWidget(geometry_group)

        boundary_group = QGroupBox("Boundary")
        boundary = QFormLayout(boundary_group)
        self.base_support = QComboBox()
        self.base_support.addItems(["Fixed", "Pinned", "Free"])
        self.top_support = QComboBox()
        self.top_support.addItems(["Free", "Pinned", "Fixed"])
        boundary.addRow("Base:", self.base_support)
        boundary.addRow("Top:", self.top_support)
        body_layout.addWidget(boundary_group)

        loading_group = QGroupBox("Optional test setup")
        loading = QFormLayout(loading_group)

        self.use_axial = QCheckBox("Create constant axial-load pattern")
        self.axial = _double(100.0, 0.0, 1.0e20)
        loading.addRow(self.use_axial)
        loading.addRow(
            f"Compression load [{self.units.force}]:",
            self.axial,
        )

        self.use_lateral = QCheckBox("Create lateral reference-load pattern")
        self.lateral_load = _double(1.0, -1.0e20, 1.0e20)
        loading.addRow(self.use_lateral)
        loading.addRow(
            f"Reference load [{self.units.force}]:",
            self.lateral_load,
        )

        self.use_displacement = QCheckBox(
            "Create direct prescribed displacement (ops.sp)"
        )
        self.displacement = _double(
            0.01,
            -1.0e20,
            1.0e20,
        )
        loading.addRow(self.use_displacement)
        loading.addRow(
            f"Prescribed displacement [{self.units.length}]:",
            self.displacement,
        )

        self.use_mass = QCheckBox("Assign lumped mass at top node")
        self.top_mass = _double(1.0, 0.0, 1.0e20)
        loading.addRow(self.use_mass)
        loading.addRow(
            f"Top mass [{self.units.mass_label}]:",
            self.top_mass,
        )

        mass_dir_widget = QGroupBox("Top-mass directions")
        mass_dir_row = QHBoxLayout(mass_dir_widget)
        self.mass_directions: dict[int, QCheckBox] = {}
        for dof, label in ((1, "UX"), (2, "UY"), (3, "UZ")):
            check = QCheckBox(label)
            check.setChecked(True)
            self.mass_directions[dof] = check
            mass_dir_row.addWidget(check)
        mass_dir_row.addStretch(1)
        loading.addRow("", mass_dir_widget)

        body_layout.addWidget(loading_group)

        options_group = QGroupBox("Creation")
        options = QFormLayout(options_group)
        self.replace_geometry = QCheckBox(
            "Replace current model geometry with this standalone specimen"
        )
        self.replace_geometry.setChecked(True)
        options.addRow(self.replace_geometry)
        body_layout.addWidget(options_group)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setObjectName("Muted")
        body_layout.addWidget(self.preview)

        note = QLabel(
            "Axial, lateral-reference, and prescribed-displacement actions "
            "create separate Plain patterns. The reference load is a load "
            "shape for Pushover/Cyclic; it is not a fixed applied force once "
            "DisplacementControl is used. Direct prescribed displacement is "
            "a separate ops.sp workflow and is normally left off when using "
            "the Cyclic/Pushover templates."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        body_layout.addWidget(note)

        body_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Create Specimen")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.preset.currentTextChanged.connect(self._apply_preset)
        self.axis.currentIndexChanged.connect(self._axis_changed)
        self.lateral.currentIndexChanged.connect(self._update_preview)
        self.planar.toggled.connect(self._update_preview)
        self.height.valueChanged.connect(self._update_preview)
        self.elements.valueChanged.connect(self._update_preview)
        self.element_type.currentTextChanged.connect(self._sync_formulation)
        for toggle in (
            self.use_axial,
            self.use_lateral,
            self.use_displacement,
            self.use_mass,
        ):
            toggle.toggled.connect(self._sync_optional_controls)
        self._apply_preset(self.preset.currentText())
        self._sync_formulation()
        self._sync_optional_controls()
        self._update_preview()

    def _apply_preset(self, preset: str) -> None:
        self.use_axial.setChecked(False)
        self.use_lateral.setChecked(False)
        self.use_displacement.setChecked(False)
        self.use_mass.setChecked(False)
        self.base_support.setCurrentText("Fixed")
        self.top_support.setCurrentText("Free")
        self.planar.setChecked(True)

        if preset == "Cantilever Cyclic Test":
            self.use_lateral.setChecked(True)
            self.lateral_load.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")
        elif preset == "Cantilever Pushover":
            self.use_lateral.setChecked(True)
            self.lateral_load.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")
        elif preset == "Axial + Lateral Column":
            self.use_axial.setChecked(True)
            self.use_lateral.setChecked(True)
            self.axial.setValue(100.0)
            self.lateral_load.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")
        elif preset == "Dynamic / Shake-table Column":
            self.use_mass.setChecked(True)
            self.top_mass.setValue(1.0)
            self.element_type.setCurrentText("forceBeamColumn")

        self._sync_optional_controls()
        self._update_preview()

    def _axis_changed(self, *_args) -> None:
        axis = int(self.axis.currentData())
        if int(self.lateral.currentData()) == axis:
            for direction in (1, 2, 3):
                if direction != axis:
                    index = self.lateral.findData(direction)
                    if index >= 0:
                        self.lateral.setCurrentIndex(index)
                        break
        self._update_preview()

    def _sync_formulation(self, *_args) -> None:
        nonlinear = self.element_type.currentText() in {
            "forceBeamColumn",
            "dispBeamColumn",
        }
        self.integration.setEnabled(nonlinear)
        self.integration_points.setEnabled(nonlinear)
        self._update_preview()

    def _sync_optional_controls(self, *_args) -> None:
        self.axial.setEnabled(self.use_axial.isChecked())
        self.lateral_load.setEnabled(self.use_lateral.isChecked())
        self.displacement.setEnabled(self.use_displacement.isChecked())
        self.top_mass.setEnabled(self.use_mass.isChecked())
        for check in self.mass_directions.values():
            check.setEnabled(self.use_mass.isChecked())
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        axis = {1: "X", 2: "Y", 3: "Z"}[int(self.axis.currentData())]
        lateral = {1: "X", 2: "Y", 3: "Z"}[
            int(self.lateral.currentData())
        ]
        options = []
        if self.use_axial.isChecked():
            options.append("axial")
        if self.use_lateral.isChecked():
            options.append("lateral reference")
        if self.use_displacement.isChecked():
            options.append("prescribed displacement")
        if self.use_mass.isChecked():
            options.append("top mass")
        self.preview.setText(
            f"Preview: 1D {axis}-axis column · {self.height.value():g} "
            f"{self.units.length} · {self.elements.value()} element(s) · "
            f"lateral {lateral} · "
            f"{'planar' if self.planar.isChecked() else '3D'} · "
            + (", ".join(options) if options else "geometry only")
        )

    def data(self) -> TestColumnSpec:
        axis = int(self.axis.currentData())
        lateral = int(self.lateral.currentData())
        if lateral == axis and (
            self.planar.isChecked()
            or self.use_lateral.isChecked()
            or self.use_displacement.isChecked()
        ):
            raise ValueError(
                "Choose a lateral/test direction different from the column axis."
            )

        transform_data = self.transformation.currentData()
        transform_tag = None
        transform_type = "PDelta"
        if (
            isinstance(transform_data, tuple)
            and len(transform_data) == 2
        ):
            if transform_data[0] == "tag":
                transform_tag = int(transform_data[1])
                transform_type = self.project.transformations[
                    transform_tag
                ].transformation_type
            else:
                transform_type = str(transform_data[1])

        mass_dirs = tuple(
            dof
            for dof, check in self.mass_directions.items()
            if check.isChecked()
        )
        if self.use_mass.isChecked() and not mass_dirs:
            raise ValueError(
                "Select at least one direction for the top mass."
            )

        return TestColumnSpec(
            height=self.height.value(),
            num_elements=self.elements.value(),
            axis=axis,
            lateral_direction=lateral,
            planar=self.planar.isChecked(),
            replace_geometry=self.replace_geometry.isChecked(),
            section_tag=(
                int(self.section.currentData())
                if self.section.currentData() is not None
                else None
            ),
            transformation_tag=transform_tag,
            transformation_type=transform_type,
            element_type=self.element_type.currentText(),
            integration_type=self.integration.currentText(),
            integration_points=self.integration_points.value(),
            base_support=self.base_support.currentText(),
            top_support=self.top_support.currentText(),
            top_mass=(
                self.top_mass.value()
                if self.use_mass.isChecked()
                else 0.0
            ),
            top_mass_directions=mass_dirs or (1, 2, 3),
            axial_load=(
                self.axial.value()
                if self.use_axial.isChecked()
                else 0.0
            ),
            lateral_reference_load=(
                self.lateral_load.value()
                if self.use_lateral.isChecked()
                else 0.0
            ),
            prescribed_displacement=(
                self.displacement.value()
                if self.use_displacement.isChecked()
                else 0.0
            ),
            name_prefix=self.preset.currentText(),
        )

    def _accept(self) -> None:
        try:
            self.data()
        except (KeyError, TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Quick 1D Column", str(exc))
            return
        self.accept()
