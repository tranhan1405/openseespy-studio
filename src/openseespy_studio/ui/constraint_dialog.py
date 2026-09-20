from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from ..project import ConstraintData
from .selection import parse_tag_expression


class ConstraintDialog(QDialog):
    DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

    @staticmethod
    def dof_labels_for_model(ndm: int, ndf: int) -> tuple[str, ...]:
        ndm = int(ndm)
        ndf = int(ndf)
        if ndm == 2:
            labels = ["UX", "UY"]
            if ndf >= 3:
                labels.append("RZ")
            return tuple(labels[:ndf])
        return ConstraintDialog.DOF_LABELS[:ndf]

    @staticmethod
    def diaphragm_directions_for_model(
        ndm: int,
    ) -> tuple[tuple[str, int], ...]:
        if int(ndm) == 2:
            return (
                ("X perpendicular direction (1)", 1),
                ("Y perpendicular direction (2)", 2),
            )
        return (
            ("X normal (DOF 1)", 1),
            ("Y normal (DOF 2)", 2),
            ("Z normal (DOF 3)", 3),
        )

    def __init__(
        self,
        constraint: ConstraintData | None = None,
        *,
        next_tag: int = 1,
        initial_retained: int = 1,
        initial_constrained: list[int] | None = None,
        ndm: int = 3,
        ndf: int = 6,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("MPC Constraint Editor")
        self.setModal(True)
        self.resize(430, 430)
        self.ndm = int(ndm)
        self.ndf = int(ndf)
        self.dof_labels = self.dof_labels_for_model(
            self.ndm,
            self.ndf,
        )

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(constraint.tag if constraint else next_tag)

        self.name = QLineEdit()
        self.name.setText(
            constraint.name
            if constraint
            else f"Constraint {self.tag.value()}"
        )

        self.constraint_type = QComboBox()
        self.constraint_type.addItems([
            "equalDOF",
            "rigidLink",
            "rigidDiaphragm",
        ])
        if constraint:
            self.constraint_type.setCurrentText(constraint.constraint_type)

        self.retained_node = QSpinBox()
        self.retained_node.setRange(1, 2_147_483_647)
        self.retained_node.setValue(
            constraint.retained_node if constraint else initial_retained
        )

        self.constrained_nodes = QLineEdit()
        constrained = (
            constraint.constrained_nodes
            if constraint
            else list(initial_constrained or [])
        )
        self.constrained_nodes.setText(
            ", ".join(map(str, constrained))
        )
        self.constrained_nodes.setPlaceholderText("e.g. 12, 13, 20-25")

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.constraint_type)
        form.addRow("Retained / master node:", self.retained_node)
        form.addRow("Constrained / slave nodes:", self.constrained_nodes)
        root.addLayout(form)

        hint = QLabel(
            "The retained/master node must be different from all constrained/slave nodes."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.dof_group = QGroupBox("equalDOF directions")
        dof_form = QFormLayout(self.dof_group)
        self.dof_checks: list[QCheckBox] = []
        for index, label in enumerate(self.dof_labels, start=1):
            check = QCheckBox(f"DOF {index}")
            self.dof_checks.append(check)
            dof_form.addRow(f"{label}:", check)
        root.addWidget(self.dof_group)

        if constraint and constraint.constraint_type == "equalDOF":
            for dof in constraint.dofs:
                if 1 <= dof <= len(self.dof_checks):
                    self.dof_checks[dof - 1].setChecked(True)
        elif constraint is None:
            for check in self.dof_checks[: min(self.ndm, self.ndf)]:
                check.setChecked(True)

        self.link_group = QGroupBox("rigidLink options")
        link_form = QFormLayout(self.link_group)
        self.link_type = QComboBox()
        self.link_type.addItems(["beam", "bar"])
        if constraint:
            self.link_type.setCurrentText(constraint.link_type)
        link_form.addRow("Link type:", self.link_type)
        root.addWidget(self.link_group)

        self.diaphragm_group = QGroupBox("rigidDiaphragm options")
        diaphragm_form = QFormLayout(self.diaphragm_group)
        self.perp_dirn = QComboBox()
        for label, direction in self.diaphragm_directions_for_model(
            self.ndm
        ):
            self.perp_dirn.addItem(label, direction)
        if constraint:
            index = self.perp_dirn.findData(constraint.perp_dirn)
            if index >= 0:
                self.perp_dirn.setCurrentIndex(index)
        elif self.ndm >= 3:
            index = self.perp_dirn.findData(3)
            if index >= 0:
                self.perp_dirn.setCurrentIndex(index)
        diaphragm_form.addRow("Perpendicular direction:", self.perp_dirn)
        root.addWidget(self.diaphragm_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.constraint_type.currentTextChanged.connect(self._sync_type)
        self._sync_type(self.constraint_type.currentText())

    def _sync_type(self, constraint_type: str) -> None:
        self.dof_group.setVisible(constraint_type == "equalDOF")
        self.link_group.setVisible(constraint_type == "rigidLink")
        self.diaphragm_group.setVisible(
            constraint_type == "rigidDiaphragm"
        )

    def _constrained_tags(self) -> list[int]:
        tags = sorted(parse_tag_expression(self.constrained_nodes.text()))
        if not tags:
            raise ValueError("Enter at least one constrained/slave node.")
        return tags

    def constraint_data(self) -> ConstraintData:
        constraint_type = self.constraint_type.currentText()
        dofs = tuple(
            index
            for index, check in enumerate(self.dof_checks, start=1)
            if check.isChecked()
        )

        return ConstraintData(
            tag=self.tag.value(),
            name=self.name.text().strip()
            or f"Constraint {self.tag.value()}",
            constraint_type=constraint_type,
            retained_node=self.retained_node.value(),
            constrained_nodes=self._constrained_tags(),
            dofs=dofs if constraint_type == "equalDOF" else (),
            link_type=self.link_type.currentText(),
            perp_dirn=int(self.perp_dirn.currentData()),
        )

    def _validate_and_accept(self) -> None:
        try:
            self.constraint_data()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Constraint Editor", str(exc))
            return
        self.accept()
