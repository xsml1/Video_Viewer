"""Shared drawing of the corner info chips (window canvas and export)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen

MARGIN = 8.0
PADDING = 5.0


def _elide(text: str, metrics: QFontMetricsF, width: float) -> str:
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1.0, width))


def draw_chip(
    painter: QPainter,
    *,
    text: str,
    color: str,
    backdrop: str,
    anchor: tuple[float, float],
    max_width: float,
    align_right: bool,
    align_bottom: bool,
    margin: float = MARGIN,
    padding: float = PADDING,
) -> None:
    """Translucent backdrop plus text, drawn inside a picture corner."""
    if not text or max_width < 24:
        return
    metrics = QFontMetricsF(painter.font())
    width = min(metrics.horizontalAdvance(text), max_width)
    height = metrics.height() + padding
    anchor_x, anchor_y = anchor
    x = anchor_x - width - padding * 2 if align_right else anchor_x
    y = anchor_y - height if align_bottom else anchor_y
    box = QRectF(x, y, width + padding * 2, height)
    path = QPainterPath()
    path.addRoundedRect(box, 5.0, 5.0)
    painter.fillPath(path, QColor(backdrop))
    painter.setPen(QPen(QColor(color)))
    painter.drawText(
        box.adjusted(padding, 0, -padding, 0),
        (Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft)
        | Qt.AlignmentFlag.AlignVCenter,
        _elide(text, metrics, width),
    )


def draw_corner_labels(
    painter: QPainter,
    rect: QRectF,
    *,
    name: str,
    info: str,
    color: str,
    backdrop: str,
    margin: float = MARGIN,
) -> None:
    """File name in the top-left corner, frame details in the bottom-right."""
    available = max(0.0, rect.width() - margin * 2 - 90)
    draw_chip(
        painter,
        text=name,
        color=color,
        backdrop=backdrop,
        anchor=(rect.x() + margin, rect.y() + margin),
        max_width=available,
        align_right=False,
        align_bottom=False,
        margin=margin,
    )
    draw_chip(
        painter,
        text=info,
        color=color,
        backdrop=backdrop,
        anchor=(rect.right() - margin, rect.bottom() - margin),
        max_width=available,
        align_right=True,
        align_bottom=True,
        margin=margin,
    )
