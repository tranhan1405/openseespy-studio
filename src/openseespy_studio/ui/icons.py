from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)

_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def studio_icon(name: str) -> QIcon:
    """Return a bundled FEWIZ command SVG icon by stem name."""
    path = _ICON_DIR / f"{name}.svg"
    return QIcon(str(path))


def _draw_node(
    painter: QPainter,
    x: float,
    y: float,
    radius: float,
    *,
    fill: QColor,
    outline: QColor,
) -> None:
    painter.setPen(QPen(outline, 4.0))
    painter.setBrush(QBrush(fill))
    painter.drawEllipse(QPointF(x, y), radius, radius)


def _visual_icon_pixmap(size: int = 256) -> QPixmap:
    """Draw the FEWIZ application mark with Qt vector primitives.

    The mark is intentionally CAD-like rather than illustrative:
    - a five-node structural W identifies the Wizard workflow
    - members and nodes read directly as finite-element geometry
    - one red terminal member indicates generated/active model content

    No gradients, magic-wand motifs or decorative sparkles are used so the
    mark stays technical and legible at toolbar and taskbar sizes.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    scale = float(size) / 256.0
    p.scale(scale, scale)

    navy = QColor("#0B315C")
    blue = QColor("#2871B9")
    red = QColor("#E5252A")
    field = QColor("#F7FAFC")
    border = QColor("#DCE5EE")

    p.setPen(QPen(border, 2.0))
    p.setBrush(QBrush(field))
    p.drawRoundedRect(QRectF(12, 12, 232, 232), 42, 42)

    nodes = (
        QPointF(52, 66),
        QPointF(88, 188),
        QPointF(128, 116),
        QPointF(168, 188),
        QPointF(204, 66),
    )

    member_pen = QPen(navy, 13.0)
    member_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    member_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(member_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for start, end in zip(nodes[:3], nodes[1:4]):
        p.drawLine(start, end)

    active_pen = QPen(red, 13.0)
    active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    active_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(active_pen)
    p.drawLine(nodes[3], nodes[4])

    for point in nodes[:4]:
        _draw_node(
            p,
            point.x(),
            point.y(),
            9.0,
            fill=field,
            outline=navy,
        )
    _draw_node(
        p,
        nodes[4].x(),
        nodes[4].y(),
        9.0,
        fill=field,
        outline=red,
    )

    # The central node is filled to provide a stable visual anchor at 16 px.
    _draw_node(
        p,
        nodes[2].x(),
        nodes[2].y(),
        7.0,
        fill=blue,
        outline=blue,
    )

    p.end()
    return pixmap


def create_visual_icon(size: int = 256) -> QIcon:
    """Return the FEWIZ icon at the requested size."""
    return QIcon(_visual_icon_pixmap(size))


def app_icon() -> QIcon:
    """Return the application icon with native pixmaps for common UI sizes."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_visual_icon_pixmap(size))
    return icon
