from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..masonry_wall import MasonryWallSpec, validate_masonry_wall_spec
from ..project import ProjectDatabase
from ..units import UnitSystem


def _double(
    value: float,
    low: float = -1.0e20,
    high: float = 1.0e20,
    decimals: int = 6,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(float(low), float(high))
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


class MasonryWallPreview(QWidget):
    """Compact engineering schematic for masonry-wall formulations."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.formulation = "EquivalentStrut"
        self.width_value = 3.0
        self.height_value = 2.8
        self.crossed = True
        self.setMinimumHeight(260)

    def set_wall(
        self,
        *,
        formulation: str,
        width: float,
        height: float,
        crossed: bool,
    ) -> None:
        self.formulation = str(formulation)
        self.width_value = max(float(width), 1.0e-9)
        self.height_value = max(float(height), 1.0e-9)
        self.crossed = bool(crossed)
        self.update()

    def _panel_points(
        self,
        left: float,
        top: float,
        wall_w: float,
        wall_h: float,
    ) -> list[tuple[float, float]]:
        return [
            (left, top + wall_h),
            (left + wall_w / 3.0, top + wall_h),
            (left + 2.0 * wall_w / 3.0, top + wall_h),
            (left + wall_w, top + wall_h),
            (left + wall_w, top + 2.0 * wall_h / 3.0),
            (left + wall_w, top + wall_h / 3.0),
            (left + wall_w, top),
            (left + 2.0 * wall_w / 3.0, top),
            (left + wall_w / 3.0, top),
            (left, top),
            (left, top + wall_h / 3.0),
            (left, top + 2.0 * wall_h / 3.0),
        ]

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))

        margin = 46.0
        available_w = max(float(self.width()) - 2.0 * margin, 20.0)
        available_h = max(float(self.height()) - 2.0 * margin, 20.0)
        scale = min(
            available_w / self.width_value,
            available_h / self.height_value,
        )
        wall_w = self.width_value * scale
        wall_h = self.height_value * scale
        left = (float(self.width()) - wall_w) / 2.0
        top = (float(self.height()) - wall_h) / 2.0

        painter.fillRect(
            int(left), int(top), int(wall_w), int(wall_h), QColor("#fffdf8")
        )
        painter.setPen(QPen(QColor("#50677d"), 1.5))
        painter.drawRect(int(left), int(top), int(wall_w), int(wall_h))

        orange = QColor("#f28c00")
        if self.formulation == "EquivalentStrut":
            painter.setPen(QPen(orange, 4.0))
            painter.drawLine(
                int(left),
                int(top + wall_h),
                int(left + wall_w),
                int(top),
            )
            if self.crossed:
                painter.drawLine(
                    int(left + wall_w),
                    int(top + wall_h),
                    int(left),
                    int(top),
                )
            painter.setPen(QPen(QColor("#40566c"), 1.0))
            painter.drawText(
                int(left + 8),
                int(top + 18),
                "Equivalent diagonal strut model",
            )
        else:
            points = self._panel_points(left, top, wall_w, wall_h)
            painter.setPen(QPen(QColor("#a56b22"), 2.0))
            # Schematic six-strut family: central + two lateral each direction.
            for a, b in ((0, 6), (1, 5), (11, 7), (3, 9), (2, 10), (4, 8)):
                painter.drawLine(
                    int(points[a][0]),
                    int(points[a][1]),
                    int(points[b][0]),
                    int(points[b][1]),
                )
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(orange, 1.8))
            for index, (x, y) in enumerate(points, start=1):
                painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)
                painter.drawText(int(x + 4), int(y - 4), str(index))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#40566c"), 1.0))
            painter.drawText(
                int(left + 8),
                int(top + 18),
                "MasonPan12 · 12 perimeter nodes / 6 internal struts",
            )

        painter.setPen(QPen(QColor("#52677b"), 1.0))
        painter.drawText(
            int(left),
            int(top + wall_h + 24),
            f"W = {self.width_value:g} · H = {self.height_value:g}",
        )
        painter.end()


class MasonryWallWizard(QWizard):
    """Create a 2D masonry wall/infill using native OpenSees formulations."""

    def __init__(self, project: ProjectDatabase, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.units = UnitSystem.from_mapping(project.units)
        self.setWindowTitle("Masonry Wall Wizard")
        self.setMinimumSize(780, 720)
        self.setOption(QWizard.WizardOption.HaveHelpButton, False)

        self._build_geometry_page()
        self._build_material_page()
        self._build_formulation_page()
        self._build_review_page()
        self.currentIdChanged.connect(self._page_changed)
        self._sync_formulation()
        self._sync_material_strategy()
        self._update_review()

    def _page_changed(self, page_id: int) -> None:
        self._update_review()
        page_to_scroll = {
            0: getattr(self, "geometry_scroll", None),
            1: getattr(self, "material_scroll", None),
            2: getattr(self, "formulation_scroll", None),
            3: getattr(self, "preview_scroll", None),
        }
        scroll = page_to_scroll.get(int(page_id))
        if scroll is not None:
            scroll.verticalScrollBar().setValue(0)

    def _scrollable_page_body(
        self,
        page: QWizardPage,
        name: str,
    ) -> QWidget:
        """Keep wizard navigation fixed while page content scrolls vertically."""
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(page)
        scroll.setObjectName(f"masonry-wall-{name}-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        body = QWidget()
        body.setObjectName(f"masonry-wall-{name}-scroll-body")
        scroll.setWidget(body)
        outer.addWidget(scroll)

        setattr(self, f"{name}_scroll", scroll)
        return body

    def _build_geometry_page(self) -> None:
        page = QWizardPage()
        page.setTitle("1 · Geometry & Formulation")
        page.setSubTitle(
            "Create a standalone masonry/infill panel in a 2D / 3DOF "
            "OpenSees domain."
        )
        body = self._scrollable_page_body(page, "geometry")
        layout = QVBoxLayout(body)
        form = QFormLayout()

        self.wall_name = QLineEdit("Masonry Wall")
        self.formulation = QComboBox()
        self.formulation.addItem(
            "Equivalent Struts · crossed corotTruss", "EquivalentStrut"
        )
        self.formulation.addItem(
            "MasonPan12 · native 12-node masonry panel", "MasonPan12"
        )
        self.width = _double(self.units.length_from_m(3.0), 1.0e-9)
        self.height = _double(self.units.length_from_m(2.8), 1.0e-9)
        self.thickness = _double(self.units.length_from_m(0.15), 1.0e-9)
        self.origin_x = _double(0.0)
        self.origin_y = _double(0.0)
        self.replace_geometry = QCheckBox("Replace current FE model")
        self.replace_geometry.setChecked(True)

        form.addRow("Name:", self.wall_name)
        form.addRow("Formulation:", self.formulation)
        form.addRow(f"Width [{self.units.length}]:", self.width)
        form.addRow(f"Height [{self.units.length}]:", self.height)
        form.addRow(f"Thickness [{self.units.length}]:", self.thickness)
        form.addRow(f"Origin X [{self.units.length}]:", self.origin_x)
        form.addRow(f"Origin Y [{self.units.length}]:", self.origin_y)
        form.addRow("", self.replace_geometry)
        layout.addLayout(form)

        self.geometry_preview = MasonryWallPreview()
        self.geometry_preview.setObjectName("masonry-wall-geometry-preview")
        self.geometry_preview.setMinimumHeight(230)
        layout.addWidget(self.geometry_preview)

        note = QLabel(
            "Equivalent Struts is a simplified infill representation. "
            "MasonPan12 is the native OpenSees 12-node / six-strut panel. "
            "Append mode intentionally refuses coincident geometry until a "
            "dedicated frame-node attachment workflow is added."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding:8px;background:#eef5fb;color:#35536f;"
        )
        layout.addWidget(note)
        layout.addStretch(1)

        for widget in (
            self.wall_name,
            self.formulation,
            self.width,
            self.height,
            self.thickness,
            self.origin_x,
            self.origin_y,
            self.replace_geometry,
        ):
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._update_review)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._formulation_changed)
            elif isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(self._update_review)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._update_review)

        self.addPage(page)

    def _build_material_page(self) -> None:
        page = QWizardPage()
        page.setTitle("2 · Masonry Material")
        page.setSubTitle(
            "OpenSees uniaxialMaterial('Masonry') · Crisafulli/Torrisi model."
        )
        body = self._scrollable_page_body(page, "material")
        form = QFormLayout(body)

        self.material_strategy = QComboBox()
        self.material_strategy.addItem(
            "Create custom Masonry material from values below",
            "CreateCustom",
        )
        self.material_strategy.addItem(
            "Reuse existing Masonry material(s) from project",
            "UseExisting",
        )
        self.existing_material = QComboBox()
        self.existing_lateral_material = QComboBox()
        for combo, role in (
            (self.existing_material, "central / strut"),
            (self.existing_lateral_material, "lateral"),
        ):
            combo.addItem(f"Select {role} Masonry material…", None)
            for tag in sorted(self.project.materials):
                material = self.project.materials[tag]
                if material.material_type != "Masonry":
                    continue
                combo.addItem(
                    f"{tag} - {material.name} (Masonry)",
                    int(tag),
                )

        form.addRow("Material source:", self.material_strategy)
        form.addRow("Existing central / strut:", self.existing_material)
        form.addRow(
            "Existing lateral (MasonPan12):",
            self.existing_lateral_material,
        )

        stress_label = self.units.engineering_stress_label
        self.Fm = _double(5.0, 1.0e-9, 1.0e9)
        self.Ft = _double(0.20, 1.0e-9, 1.0e9)
        self.Emo = _double(2500.0, 1.0e-9, 1.0e12, 3)
        self.Um = _double(-0.002, -1.0, -1.0e-12, 7)
        self.Uult = _double(-0.010, -1.0, -1.0e-12, 7)
        self.Ucl = _double(0.0005, 1.0e-12, 1.0, 7)
        self.L = _double(1.0, 1.0, 1.0)
        self.a1 = _double(1.0, 1.0, 1.0)
        self.a2 = _double(0.20, 0.0, 1.0)
        self.L.setToolTip(
            "Normalized to 1 for FEWIZ truss/MasonPan12 wall workflows."
        )
        self.a1.setToolTip(
            "Normalized Area1=1; Area2 is the relative degraded area."
        )
        self.D1 = _double(-0.002, -1.0, -1.0e-12, 7)
        self.D2 = _double(-0.006, -1.0, -1.0e-12, 7)
        self.Ach = _double(0.40, 0.0, 10.0)
        self.Are = _double(0.30, 0.0, 10.0)
        self.Ba = _double(1.75, 0.0, 10.0)
        self.Bch = _double(0.20, 0.0, 10.0)
        self.Gun = _double(2.0, 0.0, 10.0)
        self.Gplu = _double(0.60, 0.0, 10.0)
        self.Gplr = _double(1.30, 0.0, 10.0)
        self.Exp1 = _double(1.75, 0.0, 10.0)
        self.Exp2 = _double(1.25, 0.0, 10.0)
        self.IENV = QComboBox()
        self.IENV.addItem("0 · Sargin descending envelope", 0)
        self.IENV.addItem("1 · Parabolic descending envelope", 1)

        form.addRow(f"|Fm| compression [{stress_label}]:", self.Fm)
        form.addRow(f"Ft tension [{stress_label}]:", self.Ft)
        form.addRow(f"Emo [{stress_label}]:", self.Emo)
        form.addRow("Um:", self.Um)
        form.addRow("Uult:", self.Uult)
        form.addRow("Ucl:", self.Ucl)
        form.addRow("Normalized L:", self.L)
        form.addRow("Normalized Area1 A1:", self.a1)
        form.addRow("Relative Area2 A2:", self.a2)
        form.addRow("D1:", self.D1)
        form.addRow("D2:", self.D2)
        form.addRow("Ach:", self.Ach)
        form.addRow("Are:", self.Are)
        form.addRow("Ba:", self.Ba)
        form.addRow("Bch:", self.Bch)
        form.addRow("Gun:", self.Gun)
        form.addRow("Gplu:", self.Gplu)
        form.addRow("Gplr:", self.Gplr)
        form.addRow("Exp1:", self.Exp1)
        form.addRow("Exp2:", self.Exp2)
        form.addRow("Envelope IENV:", self.IENV)

        warning = QLabel(
            "⚠ These are generic starting values, not a verified material "
            "preset. L=1 and Area1=1 are normalized values used by this wall "
            "workflow; calibrate the constitutive parameters against actual "
            "masonry/infill tests."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "padding:9px;background:#fff4df;color:#805400;font-weight:600;"
        )
        form.addRow(warning)

        self._custom_material_widgets = (
            self.Fm, self.Ft, self.Emo, self.Um, self.Uult, self.Ucl,
            self.L, self.a1, self.a2, self.D1, self.D2, self.Ach,
            self.Are, self.Ba, self.Bch, self.Gun, self.Gplu,
            self.Gplr, self.Exp1, self.Exp2, self.IENV,
        )
        for widget in self._custom_material_widgets:
            if isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(self._update_review)
            else:
                widget.currentIndexChanged.connect(self._update_review)
        self.material_strategy.currentIndexChanged.connect(
            self._material_strategy_changed
        )
        self.existing_material.currentIndexChanged.connect(
            self._update_review
        )
        self.existing_lateral_material.currentIndexChanged.connect(
            self._update_review
        )

        self.addPage(page)

    def _build_formulation_page(self) -> None:
        page = QWizardPage()
        page.setTitle("3 · Formulation Parameters")
        page.setSubTitle(
            "Only parameters relevant to the selected formulation are editable."
        )
        body = self._scrollable_page_body(page, "formulation")
        form = QFormLayout(body)

        self.strut_width_ratio = _double(0.10, 1.0e-6, 1.0, 6)
        self.crossed_struts = QCheckBox("Use crossed diagonals")
        self.crossed_struts.setChecked(True)
        self.masonpan_w_tot = _double(0.25, 1.0e-6, 10.0, 6)
        self.masonpan_w1 = _double(0.50, 1.0e-6, 1.0, 6)
        self.boundary_E = _double(
            self.units.engineering_stress_from_pa(30.0e9),
            1.0e-9,
        )
        self.boundary_width = _double(
            self.units.length_from_m(0.30),
            1.0e-9,
        )
        self.boundary_depth = _double(
            self.units.length_from_m(0.30),
            1.0e-9,
        )

        form.addRow("Equivalent strut width / diagonal:", self.strut_width_ratio)
        form.addRow("", self.crossed_struts)
        form.addRow("MasonPan12 w_tot:", self.masonpan_w_tot)
        form.addRow("MasonPan12 w1:", self.masonpan_w1)

        boundary_title = QLabel("<b>Surrounding boundary frame</b>")
        form.addRow(boundary_title)
        form.addRow(
            f"Frame E [{self.units.engineering_stress_label}]:",
            self.boundary_E,
        )
        form.addRow(
            f"Frame width [{self.units.length}]:",
            self.boundary_width,
        )
        form.addRow(
            f"Frame depth [{self.units.length}]:",
            self.boundary_depth,
        )
        boundary_note = QLabel(
            "Required for a stable standalone infill model. MasonPan12 is a "
            "six-strut panel intended to interact with surrounding beam/column "
            "members; FEWIZ creates an elastic perimeter frame automatically."
        )
        boundary_note.setWordWrap(True)
        boundary_note.setStyleSheet(
            "padding:8px;background:#fff7e8;color:#7a5418;"
        )
        form.addRow(boundary_note)

        self.formulation_note = QLabel()
        self.formulation_note.setWordWrap(True)
        self.formulation_note.setStyleSheet(
            "padding:9px;background:#eef5fb;color:#35536f;"
        )
        form.addRow(self.formulation_note)

        self.strut_width_ratio.valueChanged.connect(self._update_review)
        self.crossed_struts.toggled.connect(self._update_review)
        self.masonpan_w_tot.valueChanged.connect(self._update_review)
        self.masonpan_w1.valueChanged.connect(self._update_review)
        self.boundary_E.valueChanged.connect(self._update_review)
        self.boundary_width.valueChanged.connect(self._update_review)
        self.boundary_depth.valueChanged.connect(self._update_review)
        self.addPage(page)

    def _build_review_page(self) -> None:
        page = QWizardPage()
        page.setTitle("4 · Preview & Create")
        page.setSubTitle(
            "Review topology, material model and FE objects before creation."
        )
        body = self._scrollable_page_body(page, "preview")
        layout = QVBoxLayout(body)
        self.preview = MasonryWallPreview()
        self.preview.setObjectName("masonry-wall-review-preview")
        layout.addWidget(self.preview)

        self.geometry_summary = QLabel()
        self.geometry_summary.setWordWrap(True)
        self.geometry_summary.setStyleSheet(
            "padding:9px;background:#ffffff;color:#26394c;"
        )
        layout.addWidget(self.geometry_summary)

        self.material_summary = QLabel()
        self.material_summary.setWordWrap(True)
        self.material_summary.setStyleSheet(
            "padding:9px;background:#ffffff;color:#26394c;"
        )
        layout.addWidget(self.material_summary)

        self.validation_status = QLabel()
        self.validation_status.setWordWrap(True)
        layout.addWidget(self.validation_status)
        layout.addStretch(1)
        self.addPage(page)

    def _formulation_changed(self, *_args) -> None:
        self._sync_formulation()
        self._sync_material_strategy()
        self._update_review()

    def _material_strategy_changed(self, *_args) -> None:
        self._sync_material_strategy()
        self._update_review()

    def _sync_formulation(self) -> None:
        formulation = str(self.formulation.currentData())
        is_strut = formulation == "EquivalentStrut"
        self.strut_width_ratio.setEnabled(is_strut)
        self.crossed_struts.setEnabled(is_strut)
        self.masonpan_w_tot.setEnabled(not is_strut)
        self.masonpan_w1.setEnabled(not is_strut)
        if is_strut:
            self.formulation_note.setText(
                "Equivalent Struts creates one or two corotTruss diagonals. "
                "Each strut area = thickness × (width ratio × panel diagonal)."
            )
        else:
            self.formulation_note.setText(
                "MasonPan12 creates one native 12-node masonry panel. "
                "Nodes are ordered counter-clockwise from the lower-left "
                "corner; mat_1 is the central-strut material and mat_2 the "
                "lateral-strut material."
            )

    def _sync_material_strategy(self) -> None:
        if not hasattr(self, "material_strategy"):
            return
        use_existing = (
            str(self.material_strategy.currentData()) == "UseExisting"
        )
        formulation = (
            str(self.formulation.currentData())
            if hasattr(self, "formulation")
            else "EquivalentStrut"
        )
        for widget in getattr(self, "_custom_material_widgets", ()):
            widget.setEnabled(not use_existing)
        self.existing_material.setEnabled(use_existing)
        self.existing_lateral_material.setEnabled(
            use_existing and formulation == "MasonPan12"
        )

    def data(self) -> MasonryWallSpec:
        stress_to_pa = self.units.engineering_stress_to_pa
        return MasonryWallSpec(
            name=self.wall_name.text().strip() or "Masonry Wall",
            formulation=str(self.formulation.currentData()),
            width=float(self.width.value()),
            height=float(self.height.value()),
            thickness=float(self.thickness.value()),
            origin_x=float(self.origin_x.value()),
            origin_y=float(self.origin_y.value()),
            replace_geometry=bool(self.replace_geometry.isChecked()),
            strut_width_ratio=float(self.strut_width_ratio.value()),
            crossed_struts=bool(self.crossed_struts.isChecked()),
            masonpan_w_tot=float(self.masonpan_w_tot.value()),
            masonpan_w1=float(self.masonpan_w1.value()),
            boundary_E=stress_to_pa(float(self.boundary_E.value())),
            boundary_width=float(self.boundary_width.value()),
            boundary_depth=float(self.boundary_depth.value()),
            material_strategy=str(self.material_strategy.currentData()),
            existing_material_tag=(
                None
                if self.existing_material.currentData() is None
                else int(self.existing_material.currentData())
            ),
            existing_lateral_material_tag=(
                None
                if self.existing_lateral_material.currentData() is None
                else int(self.existing_lateral_material.currentData())
            ),
            Fm=-abs(stress_to_pa(self.Fm.value())),
            Ft=abs(stress_to_pa(self.Ft.value())),
            Um=float(self.Um.value()),
            Uult=float(self.Uult.value()),
            Ucl=float(self.Ucl.value()),
            Emo=abs(stress_to_pa(self.Emo.value())),
            L=float(self.L.value()),
            a1=float(self.a1.value()),
            a2=float(self.a2.value()),
            D1=float(self.D1.value()),
            D2=float(self.D2.value()),
            Ach=float(self.Ach.value()),
            Are=float(self.Are.value()),
            Ba=float(self.Ba.value()),
            Bch=float(self.Bch.value()),
            Gun=float(self.Gun.value()),
            Gplu=float(self.Gplu.value()),
            Gplr=float(self.Gplr.value()),
            Exp1=float(self.Exp1.value()),
            Exp2=float(self.Exp2.value()),
            IENV=int(self.IENV.currentData()),
        )

    def _validation_messages(self) -> list[str]:
        messages: list[str] = []
        try:
            validate_masonry_wall_spec(self.data())
        except ValueError as exc:
            messages.append(str(exc))
        spec = self.data()
        if spec.material_strategy == "UseExisting":
            if spec.existing_material_tag is None:
                messages.append(
                    "Select an existing Masonry material for the strut / "
                    "central-strut role."
                )
            if (
                spec.formulation == "MasonPan12"
                and spec.existing_lateral_material_tag is None
            ):
                messages.append(
                    "Select an existing Masonry material for MasonPan12 "
                    "lateral struts."
                )
        if (
            not self.replace_geometry.isChecked()
            and (int(self.project.model.ndm), int(self.project.model.ndf))
            != (2, 3)
        ):
            messages.append(
                "Append mode requires the current project to be ndm=2 / ndf=3."
            )
        return messages

    def _update_review(self, *_args) -> None:
        if not hasattr(self, "formulation"):
            return
        formulation = str(self.formulation.currentData())
        preview_kwargs = {
            "formulation": formulation,
            "width": float(self.width.value()),
            "height": float(self.height.value()),
            "crossed": bool(self.crossed_struts.isChecked()),
        }
        if hasattr(self, "geometry_preview"):
            self.geometry_preview.set_wall(**preview_kwargs)
        if hasattr(self, "preview"):
            self.preview.set_wall(**preview_kwargs)
        else:
            return
        diagonal = math.hypot(
            float(self.width.value()),
            float(self.height.value()),
        )
        if formulation == "EquivalentStrut":
            count = 2 if self.crossed_struts.isChecked() else 1
            width = diagonal * float(self.strut_width_ratio.value())
            area = width * float(self.thickness.value())
            topology = (
                f"{count} corotTruss element(s) · equivalent width "
                f"{width:g} {self.units.length} · area {area:g} "
                f"{self.units.length}²"
            )
            material_objects = (
                "reuse 1 Masonry material"
                if self.material_strategy.currentData() == "UseExisting"
                else "create 1 Masonry material"
            )
            objects = (
                f"4 nodes · {count} strut element(s) · {material_objects}"
            )
        else:
            topology = (
                "12 perimeter nodes · six internal struts in native MasonPan12 · "
                f"w_tot={self.masonpan_w_tot.value():g} · "
                f"w1={self.masonpan_w1.value():g}"
            )
            material_objects = (
                "reuse 2 Masonry material references"
                if self.material_strategy.currentData() == "UseExisting"
                else "create 2 Masonry materials"
            )
            objects = (
                "12 nodes · 1 MasonPan12 element · " + material_objects
            )

        mode = (
            "Replace current FE model"
            if self.replace_geometry.isChecked()
            else "Append to current 2D model"
        )
        self.geometry_summary.setText(
            "<b>Wall to create</b><br>"
            f"{self.wall_name.text().strip() or 'Masonry Wall'} · "
            f"{formulation}<br>"
            f"W × H × t = {self.width.value():g} × "
            f"{self.height.value():g} × {self.thickness.value():g} "
            f"{self.units.length}<br>"
            f"{topology}<br>{objects}<br>"
            f"Boundary frame: E={self.boundary_E.value():g} "
            f"{self.units.engineering_stress_label}, "
            f"{self.boundary_width.value():g} × "
            f"{self.boundary_depth.value():g} {self.units.length}<br>"
            f"Mode: {mode}"
        )
        if self.material_strategy.currentData() == "UseExisting":
            primary = self.existing_material.currentText()
            lateral = self.existing_lateral_material.currentText()
            material_text = (
                "<b>Masonry constitutive model</b><br>"
                f"Reused central / strut: {primary}"
            )
            if formulation == "MasonPan12":
                material_text += f"<br>Reused lateral: {lateral}"
            material_text += (
                "<br><span style='color:#35536f'>Existing project material "
                "parameters and provenance are preserved.</span>"
            )
        else:
            material_text = (
                "<b>Masonry constitutive model</b><br>"
                f"Fm = -{self.Fm.value():g} "
                f"{self.units.engineering_stress_label} · "
                f"Ft = {self.Ft.value():g} "
                f"{self.units.engineering_stress_label} · "
                f"Emo = {self.Emo.value():g} "
                f"{self.units.engineering_stress_label}<br>"
                f"Um={self.Um.value():g} · Uult={self.Uult.value():g} · "
                f"Ucl={self.Ucl.value():g}<br>"
                "L=1 · Area1=1 normalized for the FEWIZ masonry workflow<br>"
                "<span style='color:#a15c00'>Custom / unverified starting "
                "parameters — calibration required.</span>"
            )
        self.material_summary.setText(material_text)
        messages = self._validation_messages()
        if messages:
            self.validation_status.setStyleSheet(
                "padding:9px;background:#fff0ee;color:#b42318;font-weight:600;"
            )
            self.validation_status.setText(
                "<b>Preview check · needs attention</b><br>"
                + "<br>".join(f"• {message}" for message in messages)
            )
        else:
            self.validation_status.setStyleSheet(
                "padding:9px;background:#eaf7ee;color:#226b3a;font-weight:600;"
            )
            self.validation_status.setText(
                "✓ Preview check · Ready to create masonry wall"
            )

        finish = self.button(QWizard.WizardButton.FinishButton)
        if finish is not None:
            finish.setEnabled(not messages)

    def validateCurrentPage(self) -> bool:
        try:
            if self.currentId() == self.pageIds()[-1]:
                validate_masonry_wall_spec(self.data())
                messages = self._validation_messages()
                if messages:
                    raise ValueError(messages[0])
            elif self.currentId() == self.pageIds()[0]:
                if (
                    not self.replace_geometry.isChecked()
                    and (
                        int(self.project.model.ndm),
                        int(self.project.model.ndf),
                    ) != (2, 3)
                ):
                    raise ValueError(
                        "Append mode requires an ndm=2 / ndf=3 project."
                    )
            elif self.currentId() == self.pageIds()[1]:
                validate_masonry_wall_spec(self.data())
                messages = self._validation_messages()
                if messages:
                    raise ValueError(messages[0])
        except ValueError as exc:
            QMessageBox.warning(self, "Masonry Wall Wizard", str(exc))
            return False
        return super().validateCurrentPage()
