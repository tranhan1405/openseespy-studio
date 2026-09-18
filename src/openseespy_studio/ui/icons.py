from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def studio_icon(name: str) -> QIcon:
    """Return an OpenSeesPy Studio SVG icon by stem name."""
    path = _ICON_DIR / f"{name}.svg"
    return QIcon(str(path))
