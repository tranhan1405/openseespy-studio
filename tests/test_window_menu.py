from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDockWidget

from openseespy_studio.ui.main_window import _dock_toggle_action


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
