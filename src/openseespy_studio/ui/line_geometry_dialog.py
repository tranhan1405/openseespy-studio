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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._line = line
        self._points = dict(points)
        self.setWindowTitle(
            "Edit Geometry Line" if line else "New Geometry Line"
        )
        self.resize(520, 620)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 10_000_000)
        self.tag.setValue(line.tag if line else int(next_tag))
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
        elif self.point_j.count() > 1:
            self.point_j.setCurrentIndex(1)
        form.addRow("Start Point:", self.point_i)
        form.addRow("End Point:", self.point_j)
        root.addLayout(form)

        mesh_group = QGroupBox("1D Mesh")
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

        self.reuse_nodes = QCheckBox("Reuse coincident existing FE nodes")
        self.reuse_nodes.setChecked(
            line.reuse_existing_nodes if line else True
        )
        mesh_form.addRow("", self.reuse_nodes)
        root.addWidget(mesh_group)

        recipe = QGroupBox("FE Recipe")
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
        self.section.addItem("Select Section...", None)
        for tag in sorted(sections):
            section = sections[tag]
            self.section.addItem(
                f"{tag} - {section.name} ({section.section_type})",
                int(tag),
            )
        if line and line.section_tag is not None:
            idx = self.section.findData(line.section_tag)
            if idx >= 0:
                self.section.setCurrentIndex(idx)
        elif len(sections) == 1:
            self.section.setCurrentIndex(1)
        recipe_form.addRow("Section:", self.section)

        self.transformation = QComboBox()
        self.transformation.addItem("Select Transformation...", None)
        for tag in sorted(transformations):
            transformation = transformations[tag]
            self.transformation.addItem(
                f"{tag} - {transformation.name} "
                f"({transformation.transformation_type})",
                int(tag),
            )
        if line and line.transformation_tag is not None:
            idx = self.transformation.findData(line.transformation_tag)
            if idx >= 0:
                self.transformation.setCurrentIndex(idx)
        elif len(transformations) == 1:
            self.transformation.setCurrentIndex(1)
        recipe_form.addRow("Transformation:", self.transformation)

        self.material = QComboBox()
        self.material.addItem("Select Material...", None)
        for tag in sorted(materials):
            material = materials[tag]
            self.material.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                int(tag),
            )
        if line and line.material_tag is not None:
            idx = self.material.findData(line.material_tag)
            if idx >= 0:
                self.material.setCurrentIndex(idx)
        elif len(materials) == 1:
            self.material.setCurrentIndex(1)
        recipe_form.addRow("Truss material:", self.material)

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
        self.integration_points.setRange(2, 20)
        self.integration_points.setValue(
            line.integration_points if line else 5
        )
        recipe_form.addRow("Integration points:", self.integration_points)

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
        buttons.button(QDialogButtonBox.Ok).setText(
            "Update Line" if line else "Create Line + Mesh"
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.family.currentTextChanged.connect(self._sync_family)
        self.mesh_mode.currentIndexChanged.connect(self._sync_mesh)
        self._sync_family()
        self._sync_mesh()

    def _sync_family(self, *_args) -> None:
        frame = self.family.currentText() == "Frame"
        for widget in (
            self.frame_type,
            self.section,
            self.transformation,
            self.integration,
            self.integration_points,
        ):
            widget.setEnabled(frame)
        for widget in (self.material, self.area, self.do_rayleigh):
            widget.setEnabled(not frame)

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

        family = self.family.currentText()
        section_tag = self.section.currentData()
        transformation_tag = self.transformation.currentData()
        material_tag = self.material.currentData()
        if family == "Frame":
            if section_tag is None:
                raise ValueError("Frame line requires a Section.")
            if transformation_tag is None:
                raise ValueError(
                    "Frame line requires a Geometric Transformation."
                )
        else:
            if material_tag is None:
                raise ValueError("Truss line requires a Material.")

        return LineGeometryData(
            tag=self.tag.value(),
            name=self.name.text().strip(),
            point_i=int(point_i),
            point_j=int(point_j),
            mesh_mode=str(self.mesh_mode.currentData()),
            divisions=self.divisions.value(),
            target_size=(
                self.target_size.value()
                if self.mesh_mode.currentData() == "target_size"
                else None
            ),
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
            do_rayleigh=self.do_rayleigh.isChecked(),
            generated_node_tags=(
                list(self._line.generated_node_tags)
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
