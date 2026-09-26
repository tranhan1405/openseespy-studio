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
    QPolygonF,
)

_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def studio_icon(name: str) -> QIcon:
    """Return a bundled FEWIZ command SVG icon by stem name."""
    path = _ICON_DIR / f"{name}.svg"
    return QIcon(str(path))


def _node(
    painter: QPainter,
    point: QPointF,
    radius: float,
    *,
    fill: QColor,
    outline: QColor,
    width: float = 2.5,
) -> None:
    painter.setPen(QPen(outline, width))
    painter.setBrush(QBrush(fill))
    painter.drawEllipse(point, radius, radius)


def _spark(painter: QPainter, x: float, y: float, color: QColor) -> None:
    """Draw the small four-point generation spark used by the FEWIZ brand."""
    path = QPolygonF(
        [
            QPointF(x, y - 13),
            QPointF(x + 4, y - 4),
            QPointF(x + 13, y),
            QPointF(x + 4, y + 4),
            QPointF(x, y + 13),
            QPointF(x - 4, y + 4),
            QPointF(x - 13, y),
            QPointF(x - 4, y - 4),
        ]
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPolygon(path)


def _visual_icon_pixmap(size: int = 256) -> QPixmap:
    """Draw the FEWIZ mesh-W mark using only Qt vector primitives.

    The full mark is a finite-element ribbon: two node rows, member edges and
    alternating triangular mesh faces form a W. Blue is the existing/model
    side, orange is the Wizard-generated side, and a single small spark marks
    automated generation. At 16-32 px the mesh is intentionally simplified.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    scale = float(size) / 256.0
    p.scale(scale, scale)

    navy = QColor("#0A2E55")
    blue = QColor("#0B5DAA")
    cyan = QColor("#2D86D1")
    orange = QColor("#F28C00")
    orange_dark = QColor("#C96E00")
    white = QColor("#FFFFFF")
    face_blue = QColor(65, 139, 202, 72)
    face_orange = QColor(242, 140, 0, 70)

    # Dark engineering field, matching the selected app-icon family.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(navy))
    p.drawRoundedRect(QRectF(10, 10, 236, 236), 44, 44)

    top = [
        QPointF(42, 64),
        QPointF(77, 150),
        QPointF(124, 92),
        QPointF(164, 150),
        QPointF(205, 62),
    ]
    bottom = [
        QPointF(59, 84),
        QPointF(92, 176),
        QPointF(130, 120),
        QPointF(180, 176),
        QPointF(220, 82),
    ]

    if size <= 32:
        # Small-size glyph: preserve the same silhouette without tiny mesh.
        center = [
            QPointF(50, 70),
            QPointF(85, 169),
            QPointF(127, 106),
            QPointF(172, 169),
            QPointF(213, 70),
        ]
        left_pen = QPen(white, 14.0)
        left_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        left_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(left_pen)
        for a, b in zip(center[:3], center[1:4]):
            p.drawLine(a, b)
        right_pen = QPen(orange, 14.0)
        right_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        right_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(right_pen)
        p.drawLine(center[3], center[4])
        for point in center[:4]:
            _node(p, point, 7.0, fill=white, outline=white, width=1.0)
        _node(p, center[4], 7.0, fill=orange, outline=orange, width=1.0)
        p.end()
        return pixmap

    # Alternating triangular faces make the W read as an FE mesh, not a logo
    # made from generic connected dots.
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        fill = face_blue if i < 2 else face_orange
        p.setBrush(QBrush(fill))
        if i % 2 == 0:
            p.drawPolygon(QPolygonF([top[i], bottom[i], top[i + 1]]))
            p.drawPolygon(
                QPolygonF([bottom[i], bottom[i + 1], top[i + 1]])
            )
        else:
            p.drawPolygon(QPolygonF([top[i], bottom[i], bottom[i + 1]]))
            p.drawPolygon(
                QPolygonF([top[i], bottom[i + 1], top[i + 1]])
            )

    # Edge rows: white/blue on the existing-model half and orange on the
    # Wizard-generated half.
    for row in (top, bottom):
        for i in range(4):
            color = white if i < 2 else orange
            pen = QPen(color, 5.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawLine(row[i], row[i + 1])

    # Cross-members and panel diagonals.
    for i in range(5):
        color = cyan if i < 3 else orange_dark
        p.setPen(QPen(color, 3.3))
        p.drawLine(top[i], bottom[i])
    for i in range(4):
        color = cyan if i < 2 else orange_dark
        p.setPen(QPen(color, 3.0))
        if i % 2 == 0:
            p.drawLine(bottom[i], top[i + 1])
        else:
            p.drawLine(top[i], bottom[i + 1])

    # Nodes: model side uses white/blue, generated side orange.
    for i, point in enumerate(top + bottom):
        original_index = i if i < 5 else i - 5
        if original_index < 3:
            _node(p, point, 5.2, fill=white, outline=blue, width=2.2)
        else:
            _node(
                p,
                point,
                5.2,
                fill=orange,
                outline=orange_dark,
                width=2.0,
            )

    _spark(p, 218, 43, orange)
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
