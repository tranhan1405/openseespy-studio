from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTabBar,
    QVBoxLayout,
    QWidget,
)


class ResultsPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(145)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        w, h = self.width(), self.height()
        left = max(58, int(w * 0.16))
        right = w - 22
        top = 36
        bottom = h - 22

        # Color legend
        legend = QRectF(16, top, 13, bottom - top)
        grad = QLinearGradient(0, legend.bottom(), 0, legend.top())
        grad.setColorAt(0.00, QColor("#1c4cff"))
        grad.setColorAt(0.25, QColor("#00a7ff"))
        grad.setColorAt(0.50, QColor("#24d34f"))
        grad.setColorAt(0.75, QColor("#ffe400"))
        grad.setColorAt(1.00, QColor("#e53935"))
        painter.fillRect(legend, grad)
        painter.setPen(QColor("#405268"))
        painter.drawText(35, top + 7, "0.12")
        painter.drawText(35, bottom, "0.00")

        # Schematic frame preview
        cols = 5
        stories = 4
        dx = (right - left) / (cols - 1)
        dy = (bottom - top) / stories

        level_colors = [
            QColor("#2457e6"),
            QColor("#00a5df"),
            QColor("#20bd64"),
            QColor("#f1c40f"),
            QColor("#e84a32"),
        ]

        for j in range(cols):
            x = left + j * dx
            for k in range(stories):
                y1 = bottom - k * dy
                y2 = bottom - (k + 1) * dy
                pen = QPen(level_colors[min(k + 1, len(level_colors) - 1)], 2)
                painter.setPen(pen)
                painter.drawLine(QPointF(x, y1), QPointF(x + 4, y2))

        for k in range(stories + 1):
            y = bottom - k * dy
            painter.setPen(QPen(level_colors[min(k, len(level_colors) - 1)], 2))
            for j in range(cols - 1):
                x1 = left + j * dx + (k * 1.0)
                x2 = left + (j + 1) * dx + (k * 1.0)
                painter.drawLine(QPointF(x1, y), QPointF(x2, y))

        painter.setPen(QColor("#6f8091"))
        painter.drawText(12, 18, "Disp. Z (m)")


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)

        tabs = QTabBar()
        tabs.addTab("Deformation")
        tabs.addTab("Mode Shape")
        tabs.addTab("Node Results")
        tabs.addTab("Element Results")
        tabs.setExpanding(False)
        layout.addWidget(tabs)

        controls = QHBoxLayout()
        quantity = QComboBox()
        quantity.addItems(["Displacement", "Reaction", "Acceleration"])
        direction = QComboBox()
        direction.addItems(["Z-direction", "X-direction", "Y-direction"])
        controls.addWidget(quantity)
        controls.addWidget(direction)
        controls.addStretch(1)
        layout.addLayout(controls)

        preview = ResultsPreview()
        layout.addWidget(preview, 1)
