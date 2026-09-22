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
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..model import SHELL_ELEMENT_TYPES
from ..project import SectionData, SurfaceGeometryData
from ..surface_mesher import rectangle_surface_points


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


class SurfaceGeometryDialog(QDialog):
    """Numeric Rectangle/Quad surface geometry editor for shell preprocessing."""

    def __init__(
        self,
        *,
        next_tag: int,
        sections: dict[int, SectionData],
        surface: SurfaceGeometryData | None = None,
        initial_points: tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ] | None = None,
        initial_point_tags: tuple[int, int, int, int] | None = None,
        preview_callback=None,
        mode: str = "full",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._mode = str(mode).strip().lower()
        if self._mode not in {"geometry", "mesh", "full"}:
            raise ValueError("Surface dialog mode must be geometry, mesh, or full.")
        if self._mode == "mesh":
            self.setWindowTitle("Configure Surface Mesh / Shell Recipe")
        else:
            self.setWindowTitle(
                "Edit Surface Geometry" if surface is not None
                else "New Surface Geometry"
            )
        self.resize(520, 650)
        self._surface = surface
        self._sections = dict(sections)
        self._preview_callback = preview_callback
        self._corner_point_tags = (
            surface.corner_point_tags
            if surface is not None
            else initial_point_tags
        )

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 10_000_000)
        self.tag.setValue(surface.tag if surface else int(next_tag))
        form.addRow("Tag:", self.tag)

        self.name = QLineEdit(
            surface.name if surface else f"Surface {next_tag}"
        )
        form.addRow("Name:", self.name)

        self.surface_type = QComboBox()
        self.surface_type.addItems(["Rectangle", "Quad"])
        self.surface_type.setCurrentText(
            surface.surface_type
            if surface
            else "Quad"
            if initial_points is not None
            else "Rectangle"
        )
        form.addRow("Shape:", self.surface_type)
        root.addLayout(form)

        self.rectangle_group = QGroupBox("Rectangle")
        rectangle_form = QFormLayout(self.rectangle_group)
        self.plane = QComboBox()
        self.plane.addItems(["XY", "XZ", "YZ"])
        rectangle_form.addRow("Working plane:", self.plane)

        initial_points = (
            surface.points
            if surface is not None
            else initial_points
            if initial_points is not None
            else (
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
            )
        )
        origin = initial_points[0]
        self.origin_spins = [_float_spin(value) for value in origin]
        origin_row = QHBoxLayout()
        for label, spin in zip(("X", "Y", "Z"), self.origin_spins):
            origin_row.addWidget(QLabel(label))
            origin_row.addWidget(spin)
        rectangle_form.addRow("Origin:", origin_row)

        width = max(
            (
                sum(
                    (
                        initial_points[1][axis]
                        - initial_points[0][axis]
                    ) ** 2
                    for axis in range(3)
                )
            ) ** 0.5,
            1.0,
        )
        height = max(
            (
                sum(
                    (
                        initial_points[3][axis]
                        - initial_points[0][axis]
                    ) ** 2
                    for axis in range(3)
                )
            ) ** 0.5,
            1.0,
        )
        self.width = _float_spin(width, low=1.0e-12)
        self.height = _float_spin(height, low=1.0e-12)
        rectangle_form.addRow("Width / U length:", self.width)
        rectangle_form.addRow("Height / V length:", self.height)
        root.addWidget(self.rectangle_group)

        self.quad_group = QGroupBox("Quadrilateral corners")
        quad_form = QFormLayout(self.quad_group)
        self.quad_spins: list[list[QDoubleSpinBox]] = []
        for index, point in enumerate(initial_points, start=1):
            row = QHBoxLayout()
            spins = [_float_spin(value) for value in point]
            self.quad_spins.append(spins)
            for label, spin in zip(("X", "Y", "Z"), spins):
                row.addWidget(QLabel(label))
                row.addWidget(spin)
            quad_form.addRow(f"P{index}:", row)
        root.addWidget(self.quad_group)

        mesh_group = QGroupBox("Mapped Quad Mesh")
        self.mesh_group = mesh_group
        mesh_form = QFormLayout(mesh_group)

        self.section = QComboBox()
        self.section.addItem("Select Shell Section...", None)
        for tag in sorted(self._sections):
            section = self._sections[tag]
            self.section.addItem(
                f"{tag} - {section.name} ({section.section_type})",
                tag,
            )
        if surface and surface.section_tag is not None:
            index = self.section.findData(surface.section_tag)
            if index >= 0:
                self.section.setCurrentIndex(index)
        elif len(self._sections) == 1:
            self.section.setCurrentIndex(1)
        mesh_form.addRow("Shell section:", self.section)

        self.formulation = QComboBox()
        self.formulation.addItems(sorted(SHELL_ELEMENT_TYPES))
        self.formulation.setCurrentText(
            surface.formulation if surface else "ASDShellQ4"
        )
        mesh_form.addRow("Formulation:", self.formulation)

        self.corotational = QCheckBox(
            "Corotational kinematics (ASDShellQ4)"
        )
        self.corotational.setChecked(
            surface.corotational if surface else False
        )
        mesh_form.addRow("", self.corotational)

        self.use_local_x = QCheckBox("Specify shell local X vector")
        self.use_local_x.setChecked(
            bool(surface and surface.local_x is not None)
        )
        mesh_form.addRow("", self.use_local_x)
        local_x = (
            surface.local_x
            if surface and surface.local_x is not None
            else (1.0, 0.0, 0.0)
        )
        self.local_x_spins = [_float_spin(value) for value in local_x]
        local_x_row = QHBoxLayout()
        for label, spin in zip(("X", "Y", "Z"), self.local_x_spins):
            local_x_row.addWidget(QLabel(label))
            local_x_row.addWidget(spin)
        mesh_form.addRow("Local X:", local_x_row)

        self.no_eas = QCheckBox("Disable EAS (ASDShellQ4)")
        self.no_eas.setChecked(surface.no_eas if surface else False)
        mesh_form.addRow("", self.no_eas)

        self.use_drilling_stab = QCheckBox(
            "Specify drilling stabilization"
        )
        self.use_drilling_stab.setChecked(
            bool(surface and surface.drilling_stab is not None)
        )
        mesh_form.addRow("", self.use_drilling_stab)
        self.drilling_stab = _float_spin(
            surface.drilling_stab
            if surface and surface.drilling_stab is not None
            else 0.0,
            low=0.0,
        )
        mesh_form.addRow(
            "Drilling stabilization:",
            self.drilling_stab,
        )

        self.drilling_nl = QCheckBox(
            "Nonlinear drilling stabilization"
        )
        self.drilling_nl.setChecked(
            surface.drilling_nl if surface else False
        )
        mesh_form.addRow("", self.drilling_nl)

        self.mesh_mode = QComboBox()
        self.mesh_mode.addItem("By divisions (Nu × Nv)", "divisions")
        self.mesh_mode.addItem("By target element size", "target_size")
        mode = surface.mesh_mode if surface else "divisions"
        mode_index = self.mesh_mode.findData(mode)
        self.mesh_mode.setCurrentIndex(max(0, mode_index))
        mesh_form.addRow("Sizing:", self.mesh_mode)

        self.divisions_u = QSpinBox()
        self.divisions_u.setRange(1, 500)
        self.divisions_u.setValue(surface.divisions_u if surface else 4)
        mesh_form.addRow("Divisions U:", self.divisions_u)

        self.divisions_v = QSpinBox()
        self.divisions_v.setRange(1, 500)
        self.divisions_v.setValue(surface.divisions_v if surface else 4)
        mesh_form.addRow("Divisions V:", self.divisions_v)

        self.target_size = _float_spin(
            surface.target_size
            if surface and surface.target_size is not None
            else 1.0,
            low=1.0e-12,
        )
        mesh_form.addRow("Target size:", self.target_size)

        self.bias_u = _float_spin(
            surface.bias_u if surface else 1.0,
            low=0.01,
            high=100.0,
        )
        self.bias_u.setToolTip(
            "Last U cell size / first U cell size. 1.0 = uniform."
        )
        mesh_form.addRow("Bias U (end/start):", self.bias_u)

        self.bias_v = _float_spin(
            surface.bias_v if surface else 1.0,
            low=0.01,
            high=100.0,
        )
        self.bias_v.setToolTip(
            "Last V cell size / first V cell size. 1.0 = uniform."
        )
        mesh_form.addRow("Bias V (end/start):", self.bias_v)

        edge_seed_row = QHBoxLayout()
        self.edge_seed_spins: list[QSpinBox] = []
        existing_seeds = (
            surface.edge_divisions
            if surface and surface.edge_divisions is not None
            else (None, None, None, None)
        )
        for index, seed in enumerate(existing_seeds, start=1):
            spin = QSpinBox()
            spin.setRange(0, 500)
            spin.setSpecialValueText("Auto")
            spin.setValue(0 if seed is None else int(seed))
            spin.setToolTip(
                f"Edge {index} divisions; 0 uses global sizing. "
                "Opposite edges 1/3 and 2/4 must match."
            )
            self.edge_seed_spins.append(spin)
            edge_seed_row.addWidget(QLabel(f"E{index}"))
            edge_seed_row.addWidget(spin)
        mesh_form.addRow("Edge seeds:", edge_seed_row)

        self.reuse_nodes = QCheckBox("Reuse coincident existing nodes")
        self.reuse_nodes.setChecked(
            surface.reuse_existing_nodes if surface else True
        )
        mesh_form.addRow("", self.reuse_nodes)

        self.conform_edges = QCheckBox(
            "Conform to existing shared-edge shell mesh"
        )
        self.conform_edges.setChecked(
            surface.conform_existing_edges if surface else True
        )
        mesh_form.addRow("", self.conform_edges)
        root.addWidget(mesh_group)

        note = QLabel(
            "Geometry and Mesh are separate. Create/edit the Surface shape "
            "first; configure the Shell mesh recipe separately before "
            "generating FE nodes and elements."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        buttons_row = QHBoxLayout()
        self.preview_button = QPushButton("Preview Mesh")
        self.preview_button.setEnabled(preview_callback is not None)
        self.preview_button.setToolTip(
            "Preview the current mesh sizing without changing the FE model"
        )
        self.preview_button.clicked.connect(self._preview_mesh)
        buttons_row.addWidget(self.preview_button)
        buttons_row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        if self._mode == "geometry":
            buttons.button(QDialogButtonBox.Ok).setText(
                "Update Geometry" if surface else "Create Geometry"
            )
            self.mesh_group.setVisible(False)
            self.preview_button.setVisible(False)
            self.resize(520, 430)
        elif self._mode == "mesh":
            buttons.button(QDialogButtonBox.Ok).setText("Save Mesh Recipe")
            self.tag.setEnabled(False)
            self.name.setEnabled(False)
            self.surface_type.setEnabled(False)
            self.rectangle_group.setEnabled(False)
            self.quad_group.setEnabled(False)
        else:
            buttons.button(QDialogButtonBox.Ok).setText(
                "Update Surface" if surface else "Create Surface + Mesh"
            )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons_row.addWidget(buttons)
        root.addLayout(buttons_row)

        self.surface_type.currentTextChanged.connect(self._sync_shape)
        self.formulation.currentTextChanged.connect(
            self._sync_formulation
        )
        self.mesh_mode.currentIndexChanged.connect(self._sync_mesh_mode)
        self.reuse_nodes.toggled.connect(self._sync_conformity)
        self.conform_edges.toggled.connect(self._sync_conformity)
        self.use_local_x.toggled.connect(self._sync_formulation)
        self.use_drilling_stab.toggled.connect(
            self._sync_formulation
        )
        self._sync_shape()
        self._sync_formulation()
        self._sync_mesh_mode()
        self._sync_conformity()

    def _sync_shape(self, *_args) -> None:
        rectangle = self.surface_type.currentText() == "Rectangle"
        self.rectangle_group.setVisible(rectangle)
        self.quad_group.setVisible(not rectangle)

    def _sync_formulation(self, *_args) -> None:
        advanced = self.formulation.currentText() == "ASDShellQ4"
        self.corotational.setEnabled(advanced)
        self.use_local_x.setEnabled(advanced)
        self.no_eas.setEnabled(advanced)
        self.use_drilling_stab.setEnabled(advanced)
        self.drilling_nl.setEnabled(advanced)
        for spin in self.local_x_spins:
            spin.setEnabled(
                advanced and self.use_local_x.isChecked()
            )
        self.drilling_stab.setEnabled(
            advanced and self.use_drilling_stab.isChecked()
        )

    def _sync_mesh_mode(self, *_args) -> None:
        target = self.mesh_mode.currentData() == "target_size"
        self.divisions_u.setEnabled(not target)
        self.divisions_v.setEnabled(not target)
        self.target_size.setEnabled(target)

    def _sync_conformity(self, *_args) -> None:
        if self.conform_edges.isChecked():
            self.reuse_nodes.setChecked(True)
        if not self.reuse_nodes.isChecked():
            self.conform_edges.setChecked(False)
        self.conform_edges.setEnabled(self.reuse_nodes.isChecked())

    def _points(self):
        if self.surface_type.currentText() == "Rectangle":
            origin = tuple(spin.value() for spin in self.origin_spins)
            return rectangle_surface_points(
                origin,
                self.width.value(),
                self.height.value(),
                plane=self.plane.currentText(),
            )
        return tuple(
            tuple(spin.value() for spin in spins)
            for spins in self.quad_spins
        )

    def data(self) -> SurfaceGeometryData:
        if self._mode == "geometry":
            if self._surface is None:
                return SurfaceGeometryData(
                    tag=self.tag.value(),
                    name=self.name.text().strip(),
                    surface_type=self.surface_type.currentText(),
                    points=self._points(),
                    mesh_recipe_configured=False,
                    section_tag=None,
                    corner_point_tags=self._corner_point_tags,
                )
            data = self._surface.to_dict()
            data.update({
                "tag": self.tag.value(),
                "name": self.name.text().strip(),
                "surface_type": self.surface_type.currentText(),
                "points": [list(point) for point in self._points()],
                "corner_point_tags": (
                    None
                    if self._corner_point_tags is None
                    else list(self._corner_point_tags)
                ),
            })
            return SurfaceGeometryData.from_dict(data)

        section_tag = self.section.currentData()
        if section_tag is None:
            raise ValueError(
                "Surface mesh recipe requires a Shell Section."
            )
        return SurfaceGeometryData(
            tag=self.tag.value(),
            name=self.name.text().strip(),
            surface_type=self.surface_type.currentText(),
            points=self._points(),
            mesh_recipe_configured=True,
            section_tag=int(section_tag),
            formulation=self.formulation.currentText(),
            corner_point_tags=self._corner_point_tags,
            corotational=(
                self.corotational.isChecked()
                if self.formulation.currentText() == "ASDShellQ4"
                else False
            ),
            local_x=(
                tuple(spin.value() for spin in self.local_x_spins)
                if (
                    self.formulation.currentText() == "ASDShellQ4"
                    and self.use_local_x.isChecked()
                )
                else None
            ),
            no_eas=(
                self.no_eas.isChecked()
                if self.formulation.currentText() == "ASDShellQ4"
                else False
            ),
            drilling_stab=(
                self.drilling_stab.value()
                if (
                    self.formulation.currentText() == "ASDShellQ4"
                    and self.use_drilling_stab.isChecked()
                )
                else None
            ),
            drilling_nl=(
                self.drilling_nl.isChecked()
                if self.formulation.currentText() == "ASDShellQ4"
                else False
            ),
            mesh_mode=str(self.mesh_mode.currentData()),
            divisions_u=self.divisions_u.value(),
            divisions_v=self.divisions_v.value(),
            target_size=(
                self.target_size.value()
                if self.mesh_mode.currentData() == "target_size"
                else None
            ),
            bias_u=self.bias_u.value(),
            bias_v=self.bias_v.value(),
            edge_divisions=(
                tuple(
                    None if spin.value() == 0 else spin.value()
                    for spin in self.edge_seed_spins
                )
                if any(spin.value() > 0 for spin in self.edge_seed_spins)
                else None
            ),
            reuse_existing_nodes=self.reuse_nodes.isChecked(),
            conform_existing_edges=self.conform_edges.isChecked(),
            generated_node_tags=(
                list(self._surface.generated_node_tags)
                if self._surface else []
            ),
            generated_element_tags=(
                list(self._surface.generated_element_tags)
                if self._surface else []
            ),
        )

    def _preview_mesh(self) -> None:
        if self._preview_callback is None:
            return
        try:
            surface = self.data()
            self._preview_callback(surface)
        except (TypeError, ValueError) as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Surface Mesh Preview", str(exc))

    def _accept(self) -> None:
        try:
            self.data()
        except (TypeError, ValueError) as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Surface", str(exc))
            return
        self.accept()
