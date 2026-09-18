from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OpenSeesPy Studio")
    app.setStyle("Fusion")
    try:
        window = MainWindow()
    except RuntimeError as exc:
        QMessageBox.critical(None, "Startup error", str(exc))
        return 1
    window.show()
    return app.exec()
