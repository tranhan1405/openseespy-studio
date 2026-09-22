from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDockWidget

from openseespy_studio.ui.main_window import MainWindow, _dock_toggle_action


_APP = QApplication.instance() or QApplication([])


def test_blank_dock_toggle_action_gets_fallback_name():
    dock = QDockWidget("")
    try:
        action = _dock_toggle_action(
            dock,
            fallback_text="Python / Command",
        )
        assert action.text() == "Python / Command"
    finally:
        dock.close()
        dock.deleteLater()
        _APP.processEvents()


def test_named_dock_toggle_action_keeps_existing_title():
    dock = QDockWidget("Console")
    try:
        action = _dock_toggle_action(
            dock,
            fallback_text="Fallback",
        )
        assert action.text() == "Console"
    finally:
        dock.close()
        dock.deleteLater()
        _APP.processEvents()



def test_moment_curvature_action_callback_accepts_qaction_checked_argument():
    signature = inspect.signature(
        MainWindow._run_moment_curvature_workflow
    )
    parameters = list(signature.parameters.values())

    assert [parameter.name for parameter in parameters[:2]] == [
        "self",
        "checked",
    ]
    assert parameters[1].default is False
