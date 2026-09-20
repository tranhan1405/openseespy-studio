from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.project import SectionData, TransformationData
from openseespy_studio.ui.geometry_dialogs import ElementDialog


_APP = QApplication.instance() or QApplication([])


def _close(dialog: ElementDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    _APP.processEvents()


def test_frame_dialog_constructs_with_real_transformation_field_name():
    sections = {
        1: SectionData(1, "Elastic column", "Elastic"),
        2: SectionData(2, "Fiber column", "Fiber"),
    }
    transformations = {
        1: TransformationData(
            1,
            "PDelta column",
            "PDelta",
            (1.0, 0.0, 0.0),
        )
    }

    dialog = ElementDialog(
        10,
        node_i=1,
        node_j=2,
        sections=sections,
        transformations=transformations,
    )
    try:
        assert dialog.transformation.count() == 1
        assert "PDelta column" in dialog.transformation.currentText()
        assert "(PDelta)" in dialog.transformation.currentText()

        # Elastic formulation must only expose Elastic sections.
        assert dialog.element_type.currentText() == "elasticBeamColumn"
        assert dialog.section.count() == 1
        assert dialog.section.currentData() == 1

        values = dialog.values()
        assert values[0] == 10
        assert values[1:3] == (1, 2)
        assert values[3] == "elasticBeamColumn"
        assert values[4] == 1
        assert values[5] == 1
    finally:
        _close(dialog)


def test_frame_dialog_allows_fiber_section_for_force_beam_column():
    sections = {
        1: SectionData(1, "Elastic column", "Elastic"),
        2: SectionData(2, "Fiber column", "Fiber"),
    }
    transformations = {
        1: TransformationData(
            1,
            "Linear column",
            "Linear",
            (1.0, 0.0, 0.0),
        )
    }

    dialog = ElementDialog(
        11,
        node_i=1,
        node_j=2,
        sections=sections,
        transformations=transformations,
    )
    try:
        dialog.element_type.setCurrentText("forceBeamColumn")
        _APP.processEvents()

        assert dialog.section.count() == 2
        assert dialog.section.findData(2) >= 0
        assert dialog.integration_type.isEnabled()
        assert dialog.integration_points.isEnabled()
    finally:
        _close(dialog)
