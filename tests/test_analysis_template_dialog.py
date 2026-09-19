from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from openseespy_studio.ui.analysis_template_dialog import AnalysisTemplateDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize(
    ("template_name", "page_index"),
    [
        ("Modal", 3),
        ("Pushover", 0),
        ("Cyclic", 1),
        ("Nonlinear Time History", 2),
    ],
)
def test_analysis_template_dialog_opens_for_every_template(
    qapp,
    template_name: str,
    page_index: int,
):
    dialog = AnalysisTemplateDialog(
        default_node=1,
        units={"length": "m", "force": "kN", "time": "s"},
        initial_template=template_name,
    )
    try:
        assert dialog.windowTitle() == "Analysis Template"
        assert dialog.template.currentText() == template_name
        assert dialog.pages.currentIndex() == page_index
        assert dialog.summary.text().strip()
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
