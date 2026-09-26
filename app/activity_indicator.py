"""Small, theme-independent activity marker for the chat footer."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


class ActivityFace(QWidget):
    BUSY = {"preparing", "waiting", "reasoning", "writing", "tool", "auto", "speaking"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = "idle"
        self.frame = 0
        self.setFixedSize(29, 29)
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._advance)

    def _advance(self):
        self.frame = (self.frame + 1) % 12
        self.update()

    def set_phase(self, phase: str):
        if self.phase == phase:
            return
        self.phase = phase
        self.frame = 0
        if phase in self.BUSY:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#7db3ff" if self.phase in self.BUSY else "#f0bc67" if self.phase in {"paused", "stalled"} else "#8796ac")
        painter.setPen(QPen(color, 1.8))
        painter.setBrush(QColor("#182332"))
        painter.drawEllipse(QRectF(3.5, 3.5, 21, 21))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        blink = self.phase in self.BUSY and self.frame == 9
        for x in (10.5, 17.5):
            painter.drawRoundedRect(QRectF(x, 11.5 if blink else 10.5, 2, 1 if blink else 3), 1, 1)
        painter.setPen(QPen(color, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(10, 14, 8, 6), 195 * 16, 150 * 16)
        if self.phase in self.BUSY:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            # An orbiting light makes activity visible without flashing the panel.
            angles = ((13, 0), (19, 2), (25, 8), (25, 15), (20, 22), (12, 25),
                      (5, 22), (0, 16), (0, 9), (4, 3), (9, 0), (13, 0))
            x, y = angles[self.frame]
            painter.drawEllipse(QRectF(x, y, 3, 3))


class ActivityIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # The footer must never impose a large minimum width on the chat pane:
        # Windows can otherwise pin the splitter to its 230 px sidebar minimum.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(40)
        self.setMaximumWidth(250)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        self.face = ActivityFace(self)
        self.label = QLabel(self)
        self.label.setObjectName("SubtleLabel")
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        row.addWidget(self.face)
        row.addWidget(self.label, 1)
        self.description = ""
        self.set_phase("idle", "Bereit")

    def set_phase(self, phase: str, description: str):
        self.face.set_phase(phase)
        self.description = description
        self._update_text()
        self.setToolTip(description)
        self.setAccessibleName(description)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self):
        width = self.label.width()
        if width > 0:
            self.label.setText(QFontMetrics(self.label.font()).elidedText(
                self.description, Qt.TextElideMode.ElideRight, max(0, width - 3)))
