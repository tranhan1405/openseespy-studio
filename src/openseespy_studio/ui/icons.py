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

        # Navy app tile.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#17356d"))
        painter.drawRoundedRect(rect, radius, radius)

        # Minimal eye: the visual/studio identity.
        eye_pen = QPen(QColor("#eef4ff"))
        eye_pen.setWidthF(max(1.1, size * 0.045))
        eye_pen.setCapStyle(Qt.RoundCap)
        eye_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(eye_pen)
        painter.setBrush(Qt.NoBrush)

        eye = QPainterPath()
        eye.moveTo(size * 0.17, size * 0.52)
        eye.cubicTo(
            size * 0.29,
            size * 0.30,
            size * 0.71,
            size * 0.30,
            size * 0.83,
            size * 0.52,
        )
        eye.cubicTo(
            size * 0.71,
            size * 0.74,
            size * 0.29,
            size * 0.74,
            size * 0.17,
            size * 0.52,
        )
        painter.drawPath(eye)

        # Iris/pupil kept simple so the mark remains readable at 16 px.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#dce8ff"))
        painter.drawEllipse(
            QRectF(
                size * 0.405,
                size * 0.405,
                size * 0.19,
                size * 0.19,
            )
        )
        painter.setBrush(QColor("#17356d"))
        painter.drawEllipse(
            QRectF(
                size * 0.455,
                size * 0.455,
                size * 0.09,
                size * 0.09,
            )
        )

        # Red seismic trace over the eye.
        points = (
            (0.08, 0.54),
            (0.22, 0.54),
            (0.28, 0.43),
            (0.34, 0.66),
            (0.42, 0.23),
            (0.50, 0.62),
            (0.57, 0.41),
            (0.65, 0.57),
            (0.73, 0.47),
            (0.82, 0.54),
            (0.92, 0.54),
        )
        wave = QPainterPath()
        wave.moveTo(size * points[0][0], size * points[0][1])
        for x, y in points[1:]:
            wave.lineTo(size * x, size * y)

        wave_pen = QPen(QColor("#d32f2f"))
        wave_pen.setWidthF(max(1.4, size * 0.06))
        wave_pen.setCapStyle(Qt.RoundCap)
        wave_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(wave_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(wave)

        painter.end()
        icon.addPixmap(pixmap)

    return icon

