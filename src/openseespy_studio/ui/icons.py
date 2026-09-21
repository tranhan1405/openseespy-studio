from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def studio_icon(name: str) -> QIcon:
    """Return a bundled SARE command SVG icon by stem name."""
    path = _ICON_DIR / f"{name}.svg"
    return QIcon(str(path))


def _visual_icon_pixmap(size: int = 256) -> QPixmap:
    """Draw the SARE application mark using only Qt vector primitives.

    The mark is intentionally simple:
    - navy structural-response S = SARE / structural analysis
    - red response curve = earthquake / nonlinear dynamic response
    - light field = readable at 16 px as well as large splash sizes
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    scale = float(size) / 256.0
    p.scale(scale, scale)

    navy = QColor("#0B315C")
    navy_dark = QColor("#082643")
    red = QColor("#E5252A")
    field = QColor("#F7FAFC")
    border = QColor("#DCE5EE")

    # Quiet engineering-style field. No gradients are used so the icon
    # remains crisp and reproducible across platforms and DPI settings.
    p.setPen(QPen(border, 2.0))
    p.setBrush(QBrush(field))
    p.drawRoundedRect(QRectF(12, 12, 232, 232), 42, 42)

    # Geometric S mark. A single heavy centreline is deliberately used
    # instead of a font glyph so branding is independent of installed fonts.
    s_path = QPainterPath()
    s_path.moveTo(190, 66)
    s_path.cubicTo(164, 48, 92, 48, 68, 70)
    s_path.cubicTo(45, 91, 55, 118, 82, 124)
    s_path.cubicTo(106, 129, 155, 123, 180, 138)
    s_path.cubicTo(207, 154, 202, 185, 178, 199)
    s_path.cubicTo(151, 216, 86, 212, 61, 193)

    s_pen = QPen(navy, 32.0)
    s_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    s_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(s_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(s_path)

    # Small darker terminal accents give a structural/member feel.
    accent_pen = QPen(navy_dark, 7.0)
    accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(accent_pen)
    p.drawLine(QPointF(167, 58), QPointF(192, 68))
    p.drawLine(QPointF(60, 192), QPointF(84, 203))

    # Response/deformation curve crossing the S. At large size it reads as
    # seismic response; at small size it remains a clean red deformation arc.
    response = QPainterPath()
    response.moveTo(38, 154)
    response.cubicTo(69, 154, 84, 151, 104, 136)
    response.cubicTo(119, 124, 129, 111, 143, 116)
    response.cubicTo(156, 120, 163, 143, 178, 150)
    response.cubicTo(190, 156, 204, 155, 218, 153)

    response_pen = QPen(red, 9.0)
    response_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    response_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(response_pen)
    p.drawPath(response)

    p.end()
    return pixmap

def create_visual_icon(size: int = 256) -> QIcon:
    """Return the SARE icon at the requested size."""
    return QIcon(_visual_icon_pixmap(size))


def app_icon() -> QIcon:
    """Return the application icon with native pixmaps for common UI sizes."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_visual_icon_pixmap(size))
    return icon
