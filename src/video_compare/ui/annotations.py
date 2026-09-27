"""Annotation shapes drawn over panes and reused by the comparison export.

Coordinates are normalised (0–1) in the source image. Rendering maps them
through each pane's current visible region, so zooming never moves a mark
away from the source pixels it was placed on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from video_compare.domain.viewport import ViewRegion

AnnotationKind = Literal["rect", "ellipse", "arrow", "line", "pen"]

SHAPES: tuple[tuple[str, str], ...] = (
    ("rect", "矩形"),
    ("ellipse", "圆形/椭圆"),
    ("arrow", "箭头"),
    ("line", "直线"),
    ("pen", "自由画笔"),
)

ANNOTATION_COLORS: tuple[tuple[str, str], ...] = (
    ("#ff3b30", "红"),
    ("#ff9500", "橙"),
    ("#ffd60a", "黄"),
    ("#34c759", "绿"),
    ("#00c7be", "青"),
    ("#0a84ff", "蓝"),
    ("#bf5af2", "紫"),
    ("#ffffff", "白"),
    ("#111111", "黑"),
)

ARROW_ANGLE = math.radians(28)
ARROW_LENGTH_FACTOR = 0.22
MIN_ARROW_LENGTH = 12.0
_FULL_REGION = ViewRegion()


@dataclass(frozen=True, slots=True)
class Annotation:
    """One source-anchored shape, optionally restricted to one asset."""

    kind: AnnotationKind
    start: tuple[float, float]
    end: tuple[float, float]
    color: str = "#ff3b30"
    points: tuple[tuple[float, float], ...] = ()
    target_asset_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {kind for kind, _ in SHAPES}:
            raise ValueError(f"未知标注形状：{self.kind}")
        for point in (self.start, self.end, *self.points):
            if not (0 <= point[0] <= 1 and 0 <= point[1] <= 1):
                raise ValueError("标注坐标必须落在画面内")
        if not QColor.isValidColorName(self.color):
            raise ValueError(f"无效标注颜色：{self.color}")

    def flipped(self) -> Annotation:
        """Same shape, visible region removed (used by 'Undo')."""
        return self


def _point(rect: QRectF, position: tuple[float, float], region: ViewRegion) -> QPointF:
    left = region.center_u - region.width_u / 2
    top = region.center_v - region.height_v / 2
    return QPointF(
        rect.x() + rect.width() * (position[0] - left) / region.width_u,
        rect.y() + rect.height() * (position[1] - top) / region.height_v,
    )


def draw_annotation(
    painter: QPainter,
    rect: QRectF,
    annotation: Annotation,
    *,
    width: float = 3.0,
    with_fill: bool = True,
    region: ViewRegion = _FULL_REGION,
) -> None:
    """Draw one annotation inside ``rect`` (logical or device pixels)."""
    if rect.width() <= 1 or rect.height() <= 1:
        return
    start = _point(rect, annotation.start, region)
    end = _point(rect, annotation.end, region)
    color = QColor(annotation.color)
    pen = QPen(color, width)
    pen.setCapStyle(pen.capStyle())
    pen.setJoinStyle(pen.joinStyle())
    painter.setPen(pen)
    box = QRectF(start, end).normalized()
    fill = QColor(color)
    fill.setAlpha(48)
    if annotation.kind == "rect":
        if with_fill:
            painter.fillRect(box, fill)
        painter.drawRect(box)
        return
    if annotation.kind == "ellipse":
        if with_fill:
            painter.setBrush(fill)
            painter.drawEllipse(box)
            painter.setBrush(QColor(0, 0, 0, 0))
        else:
            painter.drawEllipse(box)
        return
    if annotation.kind == "line":
        painter.drawLine(start, end)
        return
    if annotation.kind == "pen":
        points = annotation.points or (annotation.start, annotation.end)
        stroke = QPainterPath(_point(rect, points[0], region))
        for point in points[1:]:
            stroke.lineTo(_point(rect, point, region))
        painter.drawPath(stroke)
        return
    # arrow: shaft plus two head strokes
    painter.drawLine(start, end)
    length = math.hypot(end.x() - start.x(), end.y() - start.y())
    if length < 1e-6:
        return
    head = max(MIN_ARROW_LENGTH, length * ARROW_LENGTH_FACTOR)
    angle = math.atan2(end.y() - start.y(), end.x() - start.x())
    for offset in (ARROW_ANGLE, -ARROW_ANGLE):
        tip = QPointF(
            end.x() - head * math.cos(angle + offset),
            end.y() - head * math.sin(angle + offset),
        )
        painter.drawLine(end, tip)


def draw_annotations(
    painter: QPainter,
    rect: QRectF,
    annotations: tuple[Annotation, ...],
    *,
    width: float = 3.0,
    region: ViewRegion = _FULL_REGION,
) -> None:
    painter.save()
    try:
        painter.setClipRect(rect)
        for annotation in annotations:
            draw_annotation(painter, rect, annotation, width=width, region=region)
    finally:
        painter.restore()


def clamp_point(value: tuple[float, float]) -> tuple[float, float]:
    return (min(1.0, max(0.0, value[0])), min(1.0, max(0.0, value[1])))
