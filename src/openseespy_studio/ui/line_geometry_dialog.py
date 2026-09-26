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
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..model import FRAME_ELEMENT_TYPES
from ..project import (
    LineGeometryData,
    MaterialData,
    PointGeometryData,
    SectionData,
    TransformationData,
)


def _float_spin(
    value: float = 0.0,
    *,
    low: float = -1.0e12,
    high: float = 1.0e12,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(8)
    spin.setRange(low, high)
    spin.setValue(float(value))
    spin.setKeyboardTracking(False)
    return spin


class PointGeometryDialog(QDialog):
    def __init__(
        self,
        *,
        next_tag: int,
        point: PointGeometryData | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._point = point
        self.setWindowTitle(
            "Edit Geometry Point" if point else "New Geometry Point"
        )

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 10_000_000)
        self.tag.setValue(point.tag if point else int(next_tag))
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            point.name if point else f"Point {next_tag}"
        )
        form.addRow("Name:", self.name)

        xyz = point.xyz if point else (0.0, 0.0, 0.0)
        self.xyz = [_float_spin(value) for value in xyz]
        row = QHBoxLayout()
        for label, spin in zip(("X", "Y", "Z"), self.xyz):
            row.addWidget(QLabel(label))
            row.addWidget(spin)
        form.addRow("Coordinates:", row)
        root.addLayout(form)

        note = QLabel(
            "Geometry Points are preprocessing vertices. They are not "
            "OpenSees Nodes until a Line or Surface mesh generates FE entities."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def data(self) -> PointGeometryData:
        return PointGeometryData(
            tag=self.tag.value(),
            name=self.name.text().strip(),
            xyz=tuple(spin.value() for spin in self.xyz),
        )

    def _accept(self) -> None:
        try:
            self.data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Geometry Point", str(exc))
            return
        self.accept()


class LineGeometryDialog(QDialog):
    def __init__(
        self,
        *,
        next_tag: int,
        points: dict[int, PointGeometryData],
        sections: dict[int, SectionData],
        transformations: dict[int, TransformationData],
        materials: dict[int, MaterialData],
        line: LineGeometryData | None = None,
        initial_point_i: int | None = None,
        initial_point_j: int | None = None,
        mode: str = "full",
        new_section_callback=None,
        new_transformation_callback=None,
        new_material_callback=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._line = line
        self._points = dict(points)
        self._sections = dict(sections)
        self._transformations = dict(transformations)
        self._materials = dict(materials)
        self._new_section_callback = new_section_callback
        self._new_transformation_callback = new_transformation_callback
        self._new_material_callback = new_material_callback
        self._mode = str(mode).strip().lower()
        if self._mode not in {"geometry", "mesh", "full"}:
            raise ValueError("Line dialog mode must be geometry, mesh, or full.")
        if self._mode == "mesh":
            self.setWindowTitle("Configure Line Mesh / FE Recipe")
        else:
            self.setWindowTitle(
                "Edit Geometry Line" if line else "New Geometry Line"
            )
        self.resize(520, 620)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 10_000_000)
        self.tag.setValue(line.tag if line else int(next_tag))
        self.tag.setEnabled(line is None)
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            line.name if line else f"Line {next_tag}"
        )
        form.addRow("Name:", self.name)

        self.point_i = QComboBox()
        self.point_j = QComboBox()
        for tag in sorted(points):
            point = points[tag]
            label = (
                f"{tag} - {point.name} "
                f"({point.xyz[0]:g}, {point.xyz[1]:g}, {point.xyz[2]:g})"
            )
            self.point_i.addItem(label, int(tag))
            self.point_j.addItem(label, int(tag))
        if line:
            i = self.point_i.findData(line.point_i)
            j = self.point_j.findData(line.point_j)
            if i >= 0:
                self.point_i.setCurrentIndex(i)
            if j >= 0:
                self.point_j.setCurrentIndex(j)
        else:
            if initial_point_i is not None:
                i = self.point_i.findData(int(initial_point_i))
                if i >= 0:
                    self.point_i.setCurrentIndex(i)
            if initial_point_j is not None:
                j = self.point_j.findData(int(initial_point_j))
                if j >= 0:
                    self.point_j.setCurrentIndex(j)
            elif self.point_j.count() > 1:
                self.point_j.setCurrentIndex(1)
        form.addRow("Start Point:", self.point_i)
        form.addRow("End Point:", self.point_j)
        root.addLayout(form)

        mesh_group = QGroupBox("1D Mesh")
        self.mesh_group = mesh_group
        mesh_form = QFormLayout(mesh_group)
        self.mesh_mode = QComboBox()
        self.mesh_mode.addItem("By divisions", "divisions")
        self.mesh_mode.addItem("By target element size", "target_size")
        mode = line.mesh_mode if line else "divisions"
        self.mesh_mode.setCurrentIndex(
            max(0, self.mesh_mode.findData(mode))
        )
        mesh_form.addRow("Sizing:", self.mesh_mode)

        self.divisions = QSpinBox()
        self.divisions.setRange(1, 10_000)
        self.divisions.setValue(line.divisions if line else 1)
        mesh_form.addRow("Divisions:", self.divisions)

        self.target_size = _float_spin(
            line.target_size
            if line and line.target_size is not None else 1.0,
            low=1.0e-12,
        )
        mesh_form.addRow("Target size:", self.target_size)

        self.bias = _float_spin(
            line.bias if line else 1.0,
            low=1.0e-6,
        )
        self.bias.setToolTip(
            "Last element length / first element length. "
            "1.0 gives a uniform Line mesh."
        )
        mesh_form.addRow("Bias (last / first):", self.bias)

        self.reuse_nodes = QCheckBox("Reuse coincident existing FE nodes")
        self.reuse_nodes.setChecked(
            line.reuse_existing_nodes if line else True
        )
        mesh_form.addRow("", self.reuse_nodes)
        root.addWidget(mesh_group)

        recipe = QGroupBox("FE Recipe")
        self.recipe_group = recipe
        recipe_form = QFormLayout(recipe)

        self.family = QComboBox()
        self.family.addItems(["Frame", "Truss"])
        self.family.setCurrentText(
            line.element_family if line else "Frame"
        )
        recipe_form.addRow("Element family:", self.family)

        self.frame_type = QComboBox()
        self.frame_type.addItems(sorted(FRAME_ELEMENT_TYPES))
        self.frame_type.setCurrentText(
            line.element_type if line else "elasticBeamColumn"
        )
        recipe_form.addRow("Frame formulation:", self.frame_type)

        self.section = QComboBox()
        self.section_new = QPushButton("New Section...")
        self.section_new.setToolTip(
            "Define a Section now without closing this Line dialog."
        )
        self.section_new.setEnabled(callable(self._new_section_callback))
        self.section_new.clicked.connect(self._create_section_dependency)
        section_holder = QWidget()
        section_row = QHBoxLayout(section_holder)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(4)
        section_row.addWidget(self.section, 1)
        section_row.addWidget(self.section_new)
        self._refresh_section_choices(
            line.section_tag if line and line.section_tag is not None else None
        )
        recipe_form.addRow("Section:", section_holder)

        self.transformation = QComboBox()
        self.transformation_new = QPushButton("New Transformation...")
        self.transformation_new.setToolTip(
            "Define a Geometric Transformation now without closing this dialog."
        )
        self.transformation_new.setEnabled(
            callable(self._new_transformation_callback)
        )
        self.transformation_new.clicked.connect(
            self._create_transformation_dependency
        )
        transformation_holder = QWidget()
        transformation_row = QHBoxLayout(transformation_holder)
        transformation_row.setContentsMargins(0, 0, 0, 0)
        transformation_row.setSpacing(4)
        transformation_row.addWidget(self.transformation, 1)
        transformation_row.addWidget(self.transformation_new)
        self._refresh_transformation_choices(
            line.transformation_tag
            if line and line.transformation_tag is not None
            else None
        )
        recipe_form.addRow("Transformation:", transformation_holder)

        self.material = QComboBox()
        self.material_new = QPushButton("New Material...")
        self.material_new.setToolTip(
            "Define a Uniaxial Material now without closing this Line dialog."
        )
        self.material_new.setEnabled(callable(self._new_material_callback))
        self.material_new.clicked.connect(self._create_material_dependency)
        material_holder = QWidget()
        material_row = QHBoxLayout(material_holder)
        material_row.setContentsMargins(0, 0, 0, 0)
        material_row.setSpacing(4)
        material_row.addWidget(self.material, 1)
        material_row.addWidget(self.material_new)
        self._refresh_material_choices(
            line.material_tag if line and line.material_tag is not None else None
        )
        recipe_form.addRow("Truss material:", material_holder)

        self.area = _float_spin(
            line.area if line else 1.0,
            low=1.0e-12,
        )
        recipe_form.addRow("Truss area:", self.area)

        self.integration = QComboBox()
        self.integration.addItems(
            ["Lobatto", "Legendre", "Radau", "NewtonCotes", "Trapezoidal"]
        )
        self.integration.setCurrentText(
            line.integration_type if line else "Lobatto"
        )
        recipe_form.addRow("Beam integration:", self.integration)

        self.integration_points = QSpinBox()
        self.integration_points.setRange(1, 20)
        self.integration_points.setValue(
            line.integration_points if line else 5
        )
        recipe_form.addRow("Integration points:", self.integration_points)

        self.center_rotation = _float_spin(
            line.center_rotation if line else 0.4,
            low=0.0,
            high=1.0,
        )
        self.center_rotation.setToolTip(
            "dispBeamColumnInt center-of-rotation ratio cRot (0..1)."
        )
        recipe_form.addRow("cRot (dispBeamColumnInt):", self.center_rotation)

        self.formulation_note = QLabel()
        self.formulation_note.setWordWrap(True)
        self.formulation_note.setStyleSheet(
            "padding: 6px; background: #f3f6f9; color: #526476;"
        )
        recipe_form.addRow("", self.formulation_note)

        self.mass_per_length = _float_spin(
            line.mass_per_length if line else 0.0,
            low=0.0,
        )
        recipe_form.addRow("Mass / length:", self.mass_per_length)

        self.consistent_mass = QCheckBox("Use consistent mass")
        self.consistent_mass.setChecked(
            line.consistent_mass if line else False
        )
        recipe_form.addRow("", self.consistent_mass)

        self.do_rayleigh = QCheckBox("Include Truss in Rayleigh damping")
        self.do_rayleigh.setChecked(line.do_rayleigh if line else False)
        recipe_form.addRow("", self.do_rayleigh)
        root.addWidget(recipe)

        note = QLabel(
            "The Line remains a geometry object. Generate Mesh creates "
            "OpenSees Nodes and Frame/Truss Elements under FE Model."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        if self._mode == "geometry":
            buttons.button(QDialogButtonBox.Ok).setText(
                "Update Geometry" if line else "Create Geometry"
            )
            self.mesh_group.setVisible(False)
            self.recipe_group.setVisible(False)
            self.resize(520, 300)
        elif self._mode == "mesh":
            buttons.button(QDialogButtonBox.Ok).setText("Save Mesh Recipe")
            self.tag.setEnabled(False)
            self.name.setEnabled(False)
            self.point_i.setEnabled(False)
            self.point_j.setEnabled(False)
        else:
            buttons.button(QDialogButtonBox.Ok).setText(
                "Update Line" if line else "Create Line + Mesh"
            )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.family.currentTextChanged.connect(self._sync_family)
        self.frame_type.currentTextChanged.connect(self._sync_frame_type)
        self.mesh_mode.currentIndexChanged.connect(self._sync_mesh)
        self._sync_family()
        self._sync_frame_type()
        self._sync_mesh()

    @staticmethod
    def _select_combo_tag(combo: QComboBox, tag: int | None) -> None:
        if tag is None:
            if combo.count() == 2:
                combo.setCurrentIndex(1)
            return
        index = combo.findData(int(tag))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _refresh_section_choices(self, select_tag: int | None = None) -> None:
        current = self.section.currentData() if self.section.count() else None
        wanted = select_tag if select_tag is not None else current
        self.section.clear()
        self.section.addItem("Select Section...", None)
        formulation = (
            self.frame_type.currentText()
            if hasattr(self, "frame_type")
            else "elasticBeamColumn"
        )
        for tag in sorted(self._sections):
            section = self._sections[tag]
            if (
                formulation
                in {"elasticBeamColumn", "ElasticTimoshenkoBeam"}
                and section.section_type != "Elastic"
            ):
                continue
            if (
                formulation == "dispBeamColumnInt"
                and section.section_type != "FiberInt"
            ):
                continue
            self.section.addItem(
                f"{tag} - {section.name} ({section.section_type})",
                int(tag),
            )
        self._select_combo_tag(self.section, wanted)

    def _refresh_transformation_choices(
        self,
        select_tag: int | None = None,
    ) -> None:
        current = (
            self.transformation.currentData()
            if self.transformation.count()
            else None
        )
        wanted = select_tag if select_tag is not None else current
        self.transformation.clear()
        self.transformation.addItem("Select Transformation...", None)
        formulation = (
            self.frame_type.currentText()
            if hasattr(self, "frame_type")
            else "elasticBeamColumn"
        )
        for tag in sorted(self._transformations):
            transformation = self._transformations[tag]
            if (
                formulation == "dispBeamColumnInt"
                and transformation.transformation_type != "LinearInt"
            ):
                continue
            if (
                formulation != "dispBeamColumnInt"
                and transformation.transformation_type == "LinearInt"
            ):
                continue
            self.transformation.addItem(
                f"{tag} - {transformation.name} "
                f"({transformation.transformation_type})",
                int(tag),
            )
        self._select_combo_tag(self.transformation, wanted)

    def _refresh_material_choices(self, select_tag: int | None = None) -> None:
        current = self.material.currentData() if self.material.count() else None
        wanted = select_tag if select_tag is not None else current
        self.material.clear()
        self.material.addItem("Select Material...", None)
        for tag in sorted(self._materials):
            material = self._materials[tag]
            self.material.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                int(tag),
            )
        self._select_combo_tag(self.material, wanted)

    def _create_section_dependency(self) -> None:
        if not callable(self._new_section_callback):
            return
        section = self._new_section_callback()
        if section is None:
            return
        self._sections[int(section.tag)] = section
        self._refresh_section_choices(int(section.tag))

    def _create_transformation_dependency(self) -> None:
        if not callable(self._new_transformation_callback):
            return
        transformation = self._new_transformation_callback()
        if transformation is None:
            return
        self._transformations[int(transformation.tag)] = transformation
        self._refresh_transformation_choices(int(transformation.tag))

    def _create_material_dependency(self) -> None:
        if not callable(self._new_material_callback):
            return
        material = self._new_material_callback()
        if material is None:
            return
        self._materials[int(material.tag)] = material
        self._refresh_material_choices(int(material.tag))

    def _sync_family(self, *_args) -> None:
        frame = self.family.currentText() == "Frame"
        for widget in (
            self.frame_type,
            self.section,
            self.section_new,
            self.transformation,
            self.transformation_new,
            self.integration,
            self.integration_points,
            self.center_rotation,
        ):
            widget.setEnabled(frame)
        for widget in (
            self.material,
            self.material_new,
            self.area,
            self.do_rayleigh,
        ):
            widget.setEnabled(not frame)
        if frame:
            self._sync_frame_type()

    def _sync_frame_type(self, *_args) -> None:
        if not hasattr(self, "frame_type"):
            return
        formulation = self.frame_type.currentText()
        frame = self.family.currentText() == "Frame"
        nonlinear = formulation in {"forceBeamColumn", "dispBeamColumn"}
        interaction = formulation == "dispBeamColumnInt"
        self.integration.setEnabled(frame and nonlinear)
        self.integration_points.setEnabled(frame and (nonlinear or interaction))
        self.integration_points.setMinimum(1 if interaction else 2)
        self.center_rotation.setEnabled(frame and interaction)
        self.consistent_mass.setEnabled(frame and not interaction)
        if interaction:
            self.consistent_mass.setChecked(False)

        if not frame:
            self.formulation_note.setText(
                "Truss recipe: assign a uniaxial material and cross-sectional "
                "area. Frame-only formulation controls are disabled."
            )
        elif interaction:
            self.formulation_note.setText(
                "dispBeamColumnInt line recipe requires a FiberInt section "
                "and LinearInt transformation. cRot is stored on every "
                "generated element; no separate beamIntegration tag is used."
            )
        elif formulation == "ElasticTimoshenkoBeam":
            self.formulation_note.setText(
                "Elastic Timoshenko line recipe includes shear deformation. "
                "Use an Elastic section with the required shear properties."
            )
        elif formulation == "elasticBeamColumn":
            self.formulation_note.setText(
                "Elastic Euler-Bernoulli line recipe. Shear deformation is "
                "neglected."
            )
        else:
            self.formulation_note.setText(
                "Distributed-plasticity frame recipe. The selected section, "
                "transformation and beam integration are copied to generated "
                "elements."
            )

        self._refresh_section_choices()
        self._refresh_transformation_choices()

    def _sync_mesh(self, *_args) -> None:
        target = self.mesh_mode.currentData() == "target_size"
        self.divisions.setEnabled(not target)
        self.target_size.setEnabled(target)

    def data(self) -> LineGeometryData:
        point_i = self.point_i.currentData()
        point_j = self.point_j.currentData()
        if point_i is None or point_j is None:
            raise ValueError("A Line requires two Geometry Points.")
        if int(point_i) == int(point_j):
            raise ValueError("Start and end Geometry Points must differ.")

        if self._mode == "geometry":
            if self._line is None:
                return LineGeometryData(
                    tag=self.tag.value(),
                    name=self.name.text().strip(),
                    point_i=int(point_i),
                    point_j=int(point_j),
                    mesh_recipe_configured=False,
                )
            data = self._line.to_dict()
            data.update({
                "tag": self.tag.value(),
                "name": self.name.text().strip(),
                "point_i": int(point_i),
                "point_j": int(point_j),
            })
            return LineGeometryData.from_dict(data)

        family = self.family.currentText()
        section_tag = self.section.currentData()
        transformation_tag = self.transformation.currentData()
        material_tag = self.material.currentData()
        if family == "Frame":
            if section_tag is None:
                raise ValueError("Frame mesh recipe requires a Section.")
            if transformation_tag is None:
                raise ValueError(
                    "Frame mesh recipe requires a Geometric Transformation."
                )
        else:
            if material_tag is None:
                raise ValueError("Truss mesh recipe requires a Material.")

        return LineGeometryData(
            tag=self.tag.value(),
            name=self.name.text().strip(),
            point_i=int(point_i),
            point_j=int(point_j),
            mesh_recipe_configured=True,
            mesh_mode=str(self.mesh_mode.currentData()),
            divisions=self.divisions.value(),
            target_size=(
                self.target_size.value()
                if self.mesh_mode.currentData() == "target_size"
                else None
            ),
            bias=self.bias.value(),
            reuse_existing_nodes=self.reuse_nodes.isChecked(),
            element_family=family,
            element_type=(
                self.frame_type.currentText()
                if family == "Frame" else "truss"
            ),
            section_tag=(
                int(section_tag)
                if family == "Frame" and section_tag is not None
                else None
            ),
            transformation_tag=(
                int(transformation_tag)
                if family == "Frame" and transformation_tag is not None
                else None
            ),
            material_tag=(
                int(material_tag)
                if family == "Truss" and material_tag is not None
                else None
            ),
            area=self.area.value(),
            integration_type=self.integration.currentText(),
            integration_points=self.integration_points.value(),
            mass_per_length=self.mass_per_length.value(),
            consistent_mass=self.consistent_mass.isChecked(),
            center_rotation=self.center_rotation.value(),
            do_rayleigh=self.do_rayleigh.isChecked(),
            generated_node_tags=(
                list(self._line.generated_node_tags)
                if self._line else []
            ),
            owned_node_tags=(
                list(self._line.owned_node_tags)
                if self._line else []
            ),
            generated_element_tags=(
                list(self._line.generated_element_tags)
                if self._line else []
            ),
        )

    def _accept(self) -> None:
        try:
            self.data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Geometry Line", str(exc))
            return
        self.accept()
