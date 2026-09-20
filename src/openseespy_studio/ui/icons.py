from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def studio_icon(name: str) -> QIcon:
    """Return an OpenSeesPy Studio SVG icon by stem name."""
    path = _ICON_DIR / f"{name}.svg"
    return QIcon(str(path))


def _visual_icon_pixmap(size: int = 256) -> QPixmap:
    """Draw the OpenSeesPy Studio visual/seismic application mark."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Work in fixed 256 x 256 coordinates so the artwork stays proportional.
    scale = float(size) / 256.0
    p.scale(scale, scale)

    # --------------------------------------------------
    # COLORS
    # --------------------------------------------------
    NAVY = QColor("#083B70")
    NAVY_DARK = QColor("#052F5E")
    BLUE = QColor("#087FF5")
    BLUE_LIGHT = QColor("#40A7FF")
    RED = QColor("#F20D18")
    RED_DARK = QColor("#D90812")
    BASE = QColor("#A9BDCF")

    # --------------------------------------------------
    # BACKGROUND
    # --------------------------------------------------
    bg = QLinearGradient(0, 0, 0, 256)
    bg.setColorAt(0.0, QColor("#FFFFFF"))
    bg.setColorAt(1.0, QColor("#F4F8FC"))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(12, 12, 232, 232), 34, 34)

    # --------------------------------------------------
    # BASE BEAM
    # --------------------------------------------------
    base_pen = QPen(BASE, 5)
    base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

    p.setPen(base_pen)
    p.drawLine(QPointF(38, 174), QPointF(218, 174))

    # --------------------------------------------------
    # TWO COLUMNS
    # --------------------------------------------------
    column_pen = QPen(NAVY, 7)
    column_pen.setCapStyle(Qt.PenCapStyle.FlatCap)

    p.setPen(column_pen)
    p.drawLine(QPointF(40, 116), QPointF(40, 171))
    p.drawLine(QPointF(216, 116), QPointF(216, 171))

    # Column feet
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(NAVY_DARK)
    p.drawRoundedRect(QRectF(29, 168, 23, 10), 2.5, 2.5)
    p.drawRoundedRect(QRectF(204, 168, 24, 10), 2.5, 2.5)

    # --------------------------------------------------
    # EYE OUTER SHAPE
    # --------------------------------------------------
    eye_pen = QPen(NAVY, 11)
    eye_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    eye_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    p.setPen(eye_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Upper eyelid
    upper = QPainterPath()
    upper.moveTo(43, 110)
    upper.cubicTo(73, 63, 126, 57, 163, 69)
    upper.cubicTo(177, 74, 187, 81, 197, 89)
    p.drawPath(upper)

    # Lower eyelid
    lower = QPainterPath()
    lower.moveTo(43, 116)
    lower.cubicTo(70, 154, 116, 161, 156, 151)
    lower.cubicTo(171, 147, 181, 140, 190, 132)
    p.drawPath(lower)

    # --------------------------------------------------
    # IRIS
    # --------------------------------------------------
    iris_gradient = QRadialGradient(QPointF(110, 111), 29)
    iris_gradient.setColorAt(0.0, QColor("#4BB6FF"))
    iris_gradient.setColorAt(0.55, QColor("#168CFB"))
    iris_gradient.setColorAt(1.0, QColor("#0876EC"))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(iris_gradient))
    p.drawEllipse(QPointF(109, 113), 28, 28)

    # --------------------------------------------------
    # PUPIL
    # --------------------------------------------------
    pupil_gradient = QRadialGradient(QPointF(107, 109), 17)
    pupil_gradient.setColorAt(0.0, QColor("#174D7E"))
    pupil_gradient.setColorAt(1.0, QColor("#05315E"))

    p.setBrush(QBrush(pupil_gradient))
    p.drawEllipse(QPointF(109, 113), 15, 15)

    # Eye highlight
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QPointF(101, 104), 6, 6)

    # --------------------------------------------------
    # LEFT / RIGHT STRUCTURAL NODES
    # --------------------------------------------------
    def draw_node(x: float, y: float, radius: float = 8) -> None:
        gradient = QRadialGradient(
            QPointF(x - 2, y - 2),
            radius * 1.4,
        )
        gradient.setColorAt(0.0, BLUE_LIGHT)
        gradient.setColorAt(1.0, BLUE)

        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(x, y), radius, radius)

    draw_node(40, 113, 8)
    draw_node(216, 113, 8)

    # --------------------------------------------------
    # RED EARTHQUAKE / RESPONSE WAVE
    # --------------------------------------------------
    red_gradient = QLinearGradient(40, 113, 216, 113)
    red_gradient.setColorAt(0.0, RED)
    red_gradient.setColorAt(0.65, QColor("#FF141F"))
    red_gradient.setColorAt(1.0, RED_DARK)

    wave_pen = QPen(QBrush(red_gradient), 7)
    wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    wave_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    p.setPen(wave_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    wave = QPainterPath()

    # Start from left structural node.
    wave.moveTo(49, 113)

    # Smooth tail behind / below iris.
    wave.cubicTo(64, 112, 69, 132, 89, 137)

    # Resume from right side of iris.
    wave.moveTo(137, 117)
    wave.cubicTo(149, 117, 150, 116, 155, 102)

    # Small oscillation.
    wave.cubicTo(160, 85, 164, 143, 170, 130)

    # Main high peak.
    wave.cubicTo(175, 119, 178, 64, 182, 76)

    # Deep negative peak.
    wave.cubicTo(187, 93, 185, 156, 190, 144)

    # Second peak.
    wave.cubicTo(195, 130, 197, 92, 201, 100)

    # Decay.
    wave.cubicTo(205, 110, 205, 130, 210, 117)
    wave.cubicTo(212, 110, 214, 111, 216, 113)

    p.drawPath(wave)

    # Repaint the right structural node over the waveform.
    draw_node(216, 113, 8)

    p.end()
    return pixmap


def create_visual_icon(size: int = 256) -> QIcon:
    """Return the visual OpenSeesPy icon at the requested size."""
    return QIcon(_visual_icon_pixmap(size))


def app_icon() -> QIcon:
    """Return the application icon with native pixmaps for common UI sizes."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_visual_icon_pixmap(size))
    return icon
