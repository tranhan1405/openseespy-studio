from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


def _spin(
    value: float,
    *,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 8,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setValue(float(value))
    return spin


class WallFiberPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(145)
        self._widths: tuple[float, ...] = ()
        self._rhos: tuple[float, ...] = ()
        self._sfi = False

    def set_fibers(self, widths, rhos=(), *, sfi: bool = False) -> None:
        self._widths = tuple(float(value) for value in widths)
        self._rhos = tuple(float(value) for value in rhos)
        self._sfi = bool(sfi)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfcfe"))
        painter.setPen(QPen(QColor("#c8d2dc"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if not self._widths or sum(self._widths) <= 0.0:
            painter.setPen(QColor("#738394"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Macro-fiber preview")
            return
        box = QRectF(
            24.0,
            30.0,
            max(40.0, self.width() - 48.0),
            max(48.0, self.height() - 58.0),
        )
        total = sum(self._widths)
        x = box.left()
        palette = (QColor("#dceaf6"), QColor("#edf3f8"))
        for index, width in enumerate(self._widths):
            cell_width = box.width() * width / total
            rect = QRectF(x, box.top(), cell_width, box.height())
            painter.fillRect(rect, palette[index % 2])
            painter.setPen(QPen(QColor("#31516c"), 1))
            painter.drawRect(rect)
            painter.setPen(QColor("#17356d"))
            label = f"F{index + 1}"
            if not self._sfi and index < len(self._rhos):
                label += f"\nρ={self._rhos[index]:.3g}"
            painter.drawText(rect, Qt.AlignCenter, label)
            x += cell_width
        painter.setPen(QColor("#526578"))
        painter.drawText(
            QRectF(20.0, 4.0, self.width() - 40.0, 22.0),
            Qt.AlignCenter,
            f"Total wall width = {total:g}",
        )


class RCWallMacroElementDialog(QDialog):
    """Editor for MVLEM, SFI_MVLEM, and MVLEM_3D."""

    def __init__(
        self,
        *,
        tag: int,
        nodes,
        materials,
        nd_materials,
        ndm: int,
        ndf: int,
        initial_nodes=(),
        element=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Edit RC Wall Macro Element"
            if element is not None
            else "Create RC Wall Macro Element"
        )
        self.setModal(True)
        self.resize(860, 690)
        self._nodes = dict(nodes or {})
        self._materials = dict(materials or {})
        self._nd_materials = dict(nd_materials or {})
        self._dims = (int(ndm), int(ndf))
        if self._dims == (2, 3):
            formulations = (
                ("MVLEM · uniaxial macro-fibers", "MVLEM"),
                ("SFI_MVLEM · FSAM macro-fibers", "SFI_MVLEM"),
            )
            node_count = 2
        elif self._dims == (3, 6):
            formulations = (("MVLEM_3D · four-node wall panel", "MVLEM_3D"),)
            node_count = 4
        else:
            raise ValueError(
                "RC wall macro-elements require ndm=2/ndf=3 "
                "or ndm=3/ndf=6."
            )
        self._node_count = node_count

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(int(element.tag) if element is not None else int(tag))
        form.addRow("Element tag:", self.tag)

        selected = (
            list(element.node_tags())
            if element is not None
            else list(initial_nodes or ())
        )
        fallback = sorted(self._nodes)
        while len(selected) < node_count:
            candidate = next(
                (value for value in fallback if value not in selected),
                None,
            )
            if candidate is None:
                break
            selected.append(candidate)

        self.node_combos = []
        for index in range(node_count):
            combo = QComboBox()
            for node_tag in sorted(self._nodes):
                x, y, z = self._nodes[node_tag].xyz
                combo.addItem(
                    f"{node_tag}  ({x:g}, {y:g}, {z:g})",
                    int(node_tag),
                )
            if index < len(selected):
                wanted = combo.findData(int(selected[index]))
                if wanted >= 0:
                    combo.setCurrentIndex(wanted)
            self.node_combos.append(combo)
            form.addRow(f"Node {index + 1}:", combo)

        self.formulation = QComboBox()
        for label, value in formulations:
            self.formulation.addItem(label, value)
        if element is not None:
            index = self.formulation.findData(element.element_type)
            if index >= 0:
                self.formulation.setCurrentIndex(index)
        form.addRow("Formulation:", self.formulation)

        self.fiber_count = QSpinBox()
        self.fiber_count.setRange(2, 50)
        initial_count = (
            len(element.wall_widths)
            if element is not None and element.wall_widths
            else 4
        )
        self.fiber_count.setValue(initial_count)
        form.addRow("Macro-fibers m:", self.fiber_count)

        self.center_ratio = _spin(
            element.wall_center_ratio if element is not None else 0.4,
            low=0.0, high=1.0, decimals=6,
        )
        form.addRow("Center-of-rotation ratio c:", self.center_ratio)

        self.density = _spin(
            element.wall_density if element is not None else 0.0,
            low=0.0,
        )
        form.addRow("Element density:", self.density)

        self.shear_material = QComboBox()
        self._fill_material_combo(
            self.shear_material,
            sorted(self._materials),
            element.wall_shear_tag if element is not None else None,
            empty_label="No uniaxial material available",
        )
        form.addRow("Shear material:", self.shear_material)

        self.thick_mod = _spin(
            element.wall_thick_mod if element is not None else 0.63,
            low=1.0e-9, decimals=6,
        )
        form.addRow("MVLEM_3D thickness modifier:", self.thick_mod)

        self.poisson = _spin(
            element.wall_poisson if element is not None else 0.25,
            low=-0.999999, high=0.499999, decimals=6,
        )
        form.addRow("MVLEM_3D Poisson ratio:", self.poisson)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Thickness", "Width", "ρ", "Concrete", "Steel", "FSAM nDMaterial"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        self.preview = WallFiberPreview()
        root.addWidget(self.preview)
        note = QLabel(
            "MVLEM uses uniaxial concrete/steel macro-fibers plus one shear "
            "material. SFI_MVLEM uses one FSAM nDMaterial per macro-fiber. "
            "MVLEM_3D uses four wall-panel nodes in OpenSees order."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding: 7px; background: #eef4fb; color: #40566c;"
        )
        root.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.formulation.currentIndexChanged.connect(self._sync_formulation)
        self.fiber_count.valueChanged.connect(self._resize_rows)
        self._resize_rows(initial_count)
        if element is not None:
            self._load_element_rows(element)
        self._sync_formulation()

    def _fill_material_combo(
        self, combo, tags, selected, *, empty_label: str
    ) -> None:
        combo.clear()
        for tag in tags:
            material = self._materials[int(tag)]
            combo.addItem(
                f"{tag} - {material.name} ({material.material_type})",
                int(tag),
            )
        if combo.count() == 0:
            combo.addItem(empty_label, None)
            combo.setEnabled(False)
            return
        if selected is not None:
            index = combo.findData(int(selected))
            if index >= 0:
                combo.setCurrentIndex(index)

    def _material_tags_for_role(self, role: str) -> list[int]:
        if role == "concrete":
            preferred = [
                tag for tag, item in self._materials.items()
                if "Concrete" in item.material_type
            ]
        elif role == "steel":
            preferred = [
                tag for tag, item in self._materials.items()
                if "Steel" in item.material_type
                or item.material_type == "ReinforcingSteel"
            ]
        else:
            preferred = list(self._materials)
        return sorted(preferred or self._materials)

    def _combo(self, role: str, selected=None) -> QComboBox:
        combo = QComboBox()
        if role == "fsam":
            tags = [
                tag for tag, item in self._nd_materials.items()
                if item.material_type == "FSAM"
            ]
            for tag in sorted(tags):
                item = self._nd_materials[tag]
                combo.addItem(f"{tag} - {item.name} (FSAM)", int(tag))
            if combo.count() == 0:
                combo.addItem("No FSAM nDMaterial", None)
                combo.setEnabled(False)
        else:
            for tag in self._material_tags_for_role(role):
                item = self._materials[tag]
                combo.addItem(f"{tag} - {item.name}", int(tag))
            if combo.count() == 0:
                combo.addItem(f"No {role} material", None)
                combo.setEnabled(False)
        if selected is not None:
            index = combo.findData(int(selected))
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(self._refresh_preview)
        return combo

    def _row_values(self, row: int) -> dict[str, object]:
        result = {}
        for key, column in (("thickness", 0), ("width", 1), ("rho", 2)):
            widget = self.table.cellWidget(row, column)
            result[key] = (
                float(widget.value())
                if isinstance(widget, QDoubleSpinBox)
                else 0.0
            )
        for key, column in (("concrete", 3), ("steel", 4), ("fsam", 5)):
            widget = self.table.cellWidget(row, column)
            result[key] = (
                widget.currentData()
                if isinstance(widget, QComboBox)
                else None
            )
        return result

    def _resize_rows(self, count: int) -> None:
        old = [self._row_values(row) for row in range(self.table.rowCount())]
        self.table.setRowCount(int(count))
        for row in range(int(count)):
            values = old[row] if row < len(old) else {
                "thickness": 0.20, "width": 0.25, "rho": 0.01,
                "concrete": None, "steel": None, "fsam": None,
            }
            thickness = _spin(float(values["thickness"]), low=1.0e-9)
            width = _spin(float(values["width"]), low=1.0e-9)
            rho = _spin(float(values["rho"]), low=0.0, high=1.0, decimals=6)
            for spin in (thickness, width, rho):
                spin.valueChanged.connect(self._refresh_preview)
            self.table.setCellWidget(row, 0, thickness)
            self.table.setCellWidget(row, 1, width)
            self.table.setCellWidget(row, 2, rho)
            self.table.setCellWidget(row, 3, self._combo("concrete", values["concrete"]))
            self.table.setCellWidget(row, 4, self._combo("steel", values["steel"]))
            self.table.setCellWidget(row, 5, self._combo("fsam", values["fsam"]))
        self._refresh_preview()

    def _load_element_rows(self, element) -> None:
        for row in range(self.table.rowCount()):
            if row < len(element.wall_thicknesses):
                self.table.cellWidget(row, 0).setValue(element.wall_thicknesses[row])
            if row < len(element.wall_widths):
                self.table.cellWidget(row, 1).setValue(element.wall_widths[row])
            if row < len(element.wall_rhos):
                self.table.cellWidget(row, 2).setValue(element.wall_rhos[row])
            for column, values in (
                (3, element.wall_concrete_tags),
                (4, element.wall_steel_tags),
                (5, element.wall_nd_material_tags),
            ):
                if row < len(values):
                    combo = self.table.cellWidget(row, column)
                    index = combo.findData(int(values[row]))
                    if index >= 0:
                        combo.setCurrentIndex(index)

    def _sync_formulation(self, *_args) -> None:
        formulation = str(self.formulation.currentData())
        is_sfi = formulation == "SFI_MVLEM"
        is_3d = formulation == "MVLEM_3D"
        for column in (2, 3, 4):
            self.table.setColumnHidden(column, is_sfi)
        self.table.setColumnHidden(5, not is_sfi)
        self.shear_material.setEnabled(not is_sfi and self._materials)
        self.density.setEnabled(not is_sfi)
        self.thick_mod.setEnabled(is_3d)
        self.poisson.setEnabled(is_3d)
        self._refresh_preview()

    def _refresh_preview(self, *_args) -> None:
        rows = [
            self._row_values(row)
            for row in range(self.table.rowCount())
        ]
        self.preview.set_fibers(
            [row["width"] for row in rows],
            [row["rho"] for row in rows],
            sfi=str(self.formulation.currentData()) == "SFI_MVLEM",
        )

    def values(self) -> dict[str, object]:
        formulation = str(self.formulation.currentData())
        nodes = tuple(int(combo.currentData()) for combo in self.node_combos)
        if len(set(nodes)) != self._node_count:
            raise ValueError(
                f"{formulation} requires {self._node_count} distinct nodes."
            )
        rows = [self._row_values(row) for row in range(self.table.rowCount())]
        thicknesses = tuple(float(row["thickness"]) for row in rows)
        widths = tuple(float(row["width"]) for row in rows)
        rhos = tuple(float(row["rho"]) for row in rows)
        if formulation == "SFI_MVLEM":
            nd_tags = tuple(row["fsam"] for row in rows)
            if any(tag is None for tag in nd_tags):
                raise ValueError(
                    "SFI_MVLEM requires one FSAM nDMaterial per macro-fiber."
                )
            concrete_tags = ()
            steel_tags = ()
            shear_tag = None
            rhos = ()
            density = 0.0
        else:
            concrete_tags = tuple(row["concrete"] for row in rows)
            steel_tags = tuple(row["steel"] for row in rows)
            if any(tag is None for tag in concrete_tags):
                raise ValueError(
                    f"{formulation} requires a concrete material per fiber."
                )
            if any(tag is None for tag in steel_tags):
                raise ValueError(
                    f"{formulation} requires a steel material per fiber."
                )
            shear_tag = self.shear_material.currentData()
            if shear_tag is None:
                raise ValueError(
                    f"{formulation} requires a shear uniaxial material."
                )
            nd_tags = ()
            density = float(self.density.value())
        return {
            "tag": int(self.tag.value()),
            "nodes": nodes,
            "formulation": formulation,
            "center_ratio": float(self.center_ratio.value()),
            "density": density,
            "thicknesses": thicknesses,
            "widths": widths,
            "rhos": tuple(float(value) for value in rhos),
            "concrete_tags": tuple(int(value) for value in concrete_tags),
            "steel_tags": tuple(int(value) for value in steel_tags),
            "shear_tag": None if shear_tag is None else int(shear_tag),
            "nd_material_tags": tuple(int(value) for value in nd_tags),
            "thick_mod": float(self.thick_mod.value()),
            "poisson": float(self.poisson.value()),
        }

    def _accept(self) -> None:
        try:
            self.values()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "RC Wall Macro Element", str(exc))
            return
        self.accept()
