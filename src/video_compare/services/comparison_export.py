"""Compose the visible part of the compare view into one image without any UI.

The composite reproduces exactly the region each pane shows in the window at
the same scale, arranged per the requested layout. Titles, frame labels,
borders and every other interface element stay in the window only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from video_compare.domain.viewport import ViewRegion
from video_compare.ui.annotations import Annotation, draw_annotations
from video_compare.ui.overlay import draw_corner_labels

BACKGROUND = "#0b0e13"
GAP_PX = 6
_FORMATS = {"PNG": "PNG", "JPEG": "JPEG", "JPG": "JPEG"}


@dataclass(frozen=True, slots=True)
class CompositeTile:
    """One pane of the export: which source region and how big in device pixels."""

    asset_id: str
    region: ViewRegion
    pixel_width: int
    pixel_height: int
    name: str = ""
    info: str = ""

    def __post_init__(self) -> None:
        if self.pixel_width <= 0 or self.pixel_height <= 0:
            raise ValueError("导出画面尺寸必须为正数")
        if not 0 < self.region.width_u <= 1 or not 0 < self.region.height_v <= 1:
            raise ValueError("导出区域必须落在画面内")


@dataclass(frozen=True, slots=True)
class CompositeLayout:
    """Row arrangement of the tiles, indices pointing into the tile sequence."""

    rows: tuple[tuple[int, ...], ...]
    gap_px: int = GAP_PX

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("导出排列不能为空")
        if self.gap_px < 0:
            raise ValueError("导出间距不能为负")


def normalize_format(value: str) -> str:
    try:
        return _FORMATS[value.upper()]
    except KeyError as exc:
        raise ValueError(f"不支持的图片格式：{value}") from exc


def _validate(composite: CompositeLayout, count: int) -> None:
    seen: set[int] = set()
    for row in composite.rows:
        if not row:
            raise ValueError("导出排列含空行")
        for index in row:
            if not 0 <= index < count:
                raise ValueError("导出排列引用了不存在的画面")
            if index in seen:
                raise ValueError("导出排列重复引用了同一路画面")
            seen.add(index)
    if len(seen) != count:
        raise ValueError("导出排列没有覆盖全部画面")


def crop_rect(image_width: int, image_height: int, region: ViewRegion) -> QRect:
    """Integer source rectangle of the visible region inside a full frame image."""
    left = round(region.center_u * image_width - region.width_u * image_width / 2)
    top = round(region.center_v * image_height - region.height_v * image_height / 2)
    width = max(1, min(image_width, round(region.width_u * image_width)))
    height = max(1, min(image_height, round(region.height_v * image_height)))
    left = min(max(0, left), max(0, image_width - width))
    top = min(max(0, top), max(0, image_height - height))
    return QRect(left, top, width, height)


def plan_size(tiles: Sequence[CompositeTile], composite: CompositeLayout) -> tuple[int, int]:
    _validate(composite, len(tiles))
    width = 0
    height = 0
    for row in composite.rows:
        row_width = sum(tiles[index].pixel_width for index in row) + composite.gap_px * (
            len(row) - 1
        )
        width = max(width, row_width)
        height += max(tiles[index].pixel_height for index in row)
    height += composite.gap_px * (len(composite.rows) - 1)
    return max(1, width), max(1, height)


def render(
    items: Sequence[tuple[CompositeTile, QImage]],
    composite: CompositeLayout,
    *,
    annotations: Sequence[Annotation] = (),
    overlay_color: str = "#00b050",
    overlay_backdrop: str = "#99000000",
    draw_labels: bool = True,
) -> QImage:
    """Draw every visible pane region plus its corner labels and annotations."""
    if not items:
        raise ValueError("导出内容为空")
    tiles = [tile for tile, _ in items]
    width, height = plan_size(tiles, composite)
    canvas = QImage(width, height, QImage.Format.Format_RGB888)
    canvas.fill(QColor(BACKGROUND))
    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        y = 0
        for row in composite.rows:
            row_width = sum(tiles[index].pixel_width for index in row) + composite.gap_px * (
                len(row) - 1
            )
            row_height = max(tiles[index].pixel_height for index in row)
            x = (width - row_width) // 2
            for index in row:
                tile, image = items[index]
                source = crop_rect(image.width(), image.height(), tile.region)
                target = QRectF(x, y, tile.pixel_width, tile.pixel_height)
                downscaling = (
                    source.width() > tile.pixel_width or source.height() > tile.pixel_height
                )
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, downscaling)
                painter.drawImage(target, image, QRectF(source))
                if draw_labels:
                    draw_corner_labels(
                        painter,
                        target,
                        name=tile.name,
                        info=tile.info,
                        color=overlay_color,
                        backdrop=overlay_backdrop,
                    )
                pane_annotations = tuple(
                    item
                    for item in annotations
                    if item.target_asset_id is None or item.target_asset_id == tile.asset_id
                )
                if pane_annotations:
                    actual_region = ViewRegion(
                        (source.x() + source.width() / 2) / image.width(),
                        (source.y() + source.height() / 2) / image.height(),
                        source.width() / image.width(),
                        source.height() / image.height(),
                    )
                    draw_annotations(
                        painter,
                        target,
                        pane_annotations,
                        width=3.0,
                        region=actual_region,
                    )
                x += tile.pixel_width + composite.gap_px
            y += row_height + composite.gap_px
    finally:
        painter.end()
    return canvas


def rows_from_boxes(
    boxes: Sequence[tuple[float, float]], *, tolerance: float = 1.0
) -> tuple[tuple[int, ...], ...]:
    """Group (top, left) pane boxes into rows ordered top-to-bottom, left-to-right."""
    rows: list[list[int]] = []
    row_tops: list[float] = []
    lefts: list[dict[int, float]] = []
    for index, (top, left) in enumerate(boxes):
        for position, known in enumerate(row_tops):
            if abs(known - top) <= tolerance:
                rows[position].append(index)
                lefts[position][index] = left
                break
        else:
            row_tops.append(top)
            rows.append([index])
            lefts.append({index: left})
    order = sorted(range(len(rows)), key=lambda position: row_tops[position])
    return tuple(
        tuple(sorted(rows[position], key=lambda index: lefts[position][index]))
        for position in order
    )
