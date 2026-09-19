from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def studio_icon(name: str) -> QIcon:
    """Return an OpenSeesPy Studio SVG icon by stem name."""
    path = _ICON_DIR / f"{name}.svg"
    return QIcon(str(path))


def app_icon() -> QIcon:
    """Return the OpenSeesPy Studio application icon drawn with Qt."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        margin = max(1.0, size * 0.06)
        rect = QRectF(
            margin,
            margin,
            size - 2.0 * margin,
            size - 2.0 * margin,
        )
        radius = size * 0.18
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#17356d"))
        painter.drawRoundedRect(rect, radius, radius)

        points = (
            (0.10, 0.53),
            (0.22, 0.53),
            (0.28, 0.39),
            (0.35, 0.68),
            (0.43, 0.22),
            (0.51, 0.64),
            (0.58, 0.41),
            (0.66, 0.58),
            (0.73, 0.46),
            (0.81, 0.55),
            (0.90, 0.53),
        )
        path = QPainterPath()
        path.moveTo(size * points[0][0], size * points[0][1])
        for x, y in points[1:]:
            path.lineTo(size * x, size * y)

        pen = QPen(QColor("#d32f2f"))
        pen.setWidthF(max(1.5, size * 0.065))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()

        icon.addPixmap(pixmap)

    return icon
