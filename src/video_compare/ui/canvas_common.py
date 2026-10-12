from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
)

from video_compare.domain.models import (
    AssetInfo,
    DecodedFrame,
    DisplayTransform,
    FrameGroupSnapshot,
)
from video_compare.domain.viewport import PanelTransform, Rect, ViewRegion
from video_compare.media.color import preview_warning
from video_compare.ui.annotations import Annotation, draw_annotations
from video_compare.ui.i18n import language, translate
from video_compare.ui.layout import (
    PANE_GAP,
    LayoutMode,
    choose_rows,
    grid_shape,
    place_rows,
)
from video_compare.ui.overlay import draw_corner_labels
from video_compare.ui.theme import CanvasColors

# 名称与帧信息直接叠在画面上：名称在左上角，帧信息在右下角。
LABEL_HEIGHT = 0.0
LABEL_MARGIN = 8.0
OVERLAY_PADDING = 5.0

__all__ = [
    "LABEL_HEIGHT",
    "grid_shape",
    "hit_content",
    "paint_group",
    "pane_at",
    "pane_boxes",
    "pane_transform",
]


def _display_size(
    asset: AssetInfo, snapshot: FrameGroupSnapshot | None, *, pixel_mode: bool
) -> tuple[float, float]:
    frame = snapshot.frames.get(asset.asset_id) if snapshot is not None else None
    if frame is not None:
        height, width = frame.rgb.shape[:2]
    else:
        width, height = asset.coded_width, asset.coded_height
    if width <= 0 or height <= 0:
        width, height = 16.0, 9.0
    metadata = asset.display_transform
    if not pixel_mode:
        width *= float(metadata.sample_aspect_ratio)
    if metadata.rotation_degrees in {90, 270}:
        width, height = height, width
    return width, height


def _pane_aspects(
    order: Sequence[str],
    assets: Mapping[str, AssetInfo],
    snapshot: FrameGroupSnapshot | None,
    pixel_zoom: float | None,
) -> list[float]:
    """Displayed aspect ratio of every imported video (after rotation and SAR).

    The arrangement follows the source videos, not the current zoom window, so
    panes never jump to another row while the user zooms or drags.
    """
    aspects: list[float] = []
    for asset_id in order:
        display_width, display_height = _display_size(
            assets[asset_id], snapshot, pixel_mode=pixel_zoom is not None
        )
        aspects.append(max(display_width, 1e-6) / max(display_height, 1e-6))
    return aspects


def pane_boxes(
    width: int,
    height: int,
    order: Sequence[str],
    assets: Mapping[str, AssetInfo],
    snapshot: FrameGroupSnapshot | None,
    *,
    layout: LayoutMode = "auto",
    pixel_zoom: float | None = None,
    label_height: float = LABEL_HEIGHT,
    gap: float = PANE_GAP,
) -> dict[str, Rect]:
    """Content box of every pane, adapted to the imported video aspect ratios."""
    if not order:
        return {}
    aspects = _pane_aspects(order, assets, snapshot, pixel_zoom)
    rows = choose_rows(aspects, layout, width=width, height=height, gap=gap, row_extra=label_height)
    boxes = place_rows(rows, aspects, width=width, height=height, gap=gap, row_extra=label_height)
    return dict(zip(order, boxes, strict=True))


def pane_transform(
    width: int,
    height: int,
    order: tuple[str, ...],
    assets: Mapping[str, AssetInfo],
    snapshot: FrameGroupSnapshot | None,
    regions: Mapping[str, ViewRegion],
    asset_id: str,
    *,
    pixel_zoom: float | None = None,
    device_pixel_ratio: float = 1.0,
    layout: LayoutMode = "auto",
    gap: float = PANE_GAP,
) -> PanelTransform | None:
    if snapshot is None or asset_id not in snapshot.frames or asset_id not in order:
        return None
    boxes = pane_boxes(width, height, order, assets, snapshot, layout=layout, gap=gap)
    if asset_id not in boxes:
        return None
    panel = boxes[asset_id]
    if panel.width <= 0 or panel.height <= 0:
        return None
    display_width, display_height = _display_size(
        assets[asset_id], snapshot, pixel_mode=pixel_zoom is not None
    )
    region = regions.get(asset_id, ViewRegion())
    if pixel_zoom is not None:
        if pixel_zoom <= 0 or device_pixel_ratio <= 0:
            raise ValueError("像素倍率与 DPR 必须为正数")
        scale = pixel_zoom / device_pixel_ratio
        visible_width = min(int(display_width), max(1, int(panel.width / scale)))
        visible_height = min(int(display_height), max(1, int(panel.height / scale)))
        width_u = visible_width / display_width
        height_v = visible_height / display_height
        left = min(
            int(display_width) - visible_width,
            max(0, round(region.center_u * display_width - visible_width / 2)),
        )
        top = min(
            int(display_height) - visible_height,
            max(0, round(region.center_v * display_height - visible_height / 2)),
        )
        region = ViewRegion(
            (left + visible_width / 2) / display_width,
            (top + visible_height / 2) / display_height,
            width_u,
            height_v,
        )
        return PanelTransform(
            panel,
            display_width,
            display_height,
            region,
            fixed_scale=scale,
            pixel_ratio=device_pixel_ratio,
        )
    return PanelTransform(panel, display_width, display_height, region)


def hit_content(
    width: int,
    height: int,
    order: tuple[str, ...],
    assets: Mapping[str, AssetInfo],
    snapshot: FrameGroupSnapshot | None,
    regions: Mapping[str, ViewRegion],
    x: float,
    y: float,
    *,
    pixel_zoom: float | None = None,
    device_pixel_ratio: float = 1.0,
    layout: LayoutMode = "auto",
) -> tuple[str, PanelTransform] | None:
    for asset_id in order:
        transform = pane_transform(
            width,
            height,
            order,
            assets,
            snapshot,
            regions,
            asset_id,
            pixel_zoom=pixel_zoom,
            device_pixel_ratio=device_pixel_ratio,
            layout=layout,
        )
        if transform is not None and transform.content_rect.contains(x, y):
            return asset_id, transform
    return None


def pane_at(
    width: int,
    height: int,
    order: Sequence[str],
    assets: Mapping[str, AssetInfo],
    snapshot: FrameGroupSnapshot | None,
    regions: Mapping[str, ViewRegion],
    x: float,
    y: float,
    *,
    layout: LayoutMode = "auto",
) -> str | None:
    """Pane under the pointer, including its label strip and letterbox area."""
    boxes = pane_boxes(width, height, order, assets, snapshot, layout=layout)
    for asset_id in order:
        box = boxes.get(asset_id)
        if box is None:
            continue
        if box.x <= x <= box.right and box.y - LABEL_HEIGHT <= y <= box.bottom:
            return asset_id
    return None


def _elide(text: str, font: QFontMetricsF, width: float) -> str:
    return font.elidedText(text, Qt.TextElideMode.ElideRight, max(1.0, width))


def _draw_overlays(
    painter: QPainter,
    colors: CanvasColors,
    content: Rect,
    *,
    name: str,
    info: str,
    warning: str,
) -> None:
    """File name in the picture's top-left, frame details in its bottom-right."""
    detail = f"{info} · {warning}" if warning else info
    draw_corner_labels(
        painter,
        QRectF(content.x, content.y, content.width, content.height),
        name=name,
        info=detail,
        color=colors.overlay,
        backdrop=colors.overlay_backdrop,
        margin=LABEL_MARGIN,
    )


def paint_group(
    painter: QPainter,
    width: int,
    height: int,
    order: tuple[str, ...],
    assets: Mapping[str, AssetInfo],
    snapshot: FrameGroupSnapshot | None,
    regions: Mapping[str, ViewRegion] | None = None,
    roi_preview: Rect | None = None,
    colors: CanvasColors | None = None,
    pixel_zoom: float | None = None,
    device_pixel_ratio: float = 1.0,
    draw_frame: Callable[
        [QPainter, str, DecodedFrame, DisplayTransform, QRectF, QRectF, bool], None
    ]
    | None = None,
    layout: LayoutMode = "auto",
    overlay_visible: bool = True,
    annotations: tuple[Annotation, ...] = (),
    annotation_preview: Annotation | None = None,
) -> None:
    regions = regions or {}
    colors = colors or CanvasColors()
    painter.fillRect(QRectF(0, 0, width, height), QColor(colors.background))
    painter.setFont(QFont("Microsoft YaHei UI", 9))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if not order:
        painter.setPen(QColor(colors.muted))
        painter.drawText(
            QRectF(0, 0, width, height),
            Qt.AlignmentFlag.AlignCenter,
            translate("选择工作文件夹，双击图像或视频开始对比，也可以将文件拖入窗口"),
        )
        return
    boxes = pane_boxes(width, height, order, assets, snapshot, layout=layout)
    for asset_id in order:
        box = boxes.get(asset_id)
        if box is None:
            continue
        color = assets[asset_id].color_info
        warning = translate(preview_warning(color))
        frame = snapshot.frames.get(asset_id) if snapshot is not None else None
        if frame is None:
            info = translate("等待画面")
        elif assets[asset_id].media_kind == "image":
            info = (
                f"{assets[asset_id].coded_width}×{assets[asset_id].coded_height} · "
                f"{assets[asset_id].codec_name or translate('图像')}"
            )
        else:
            detached = (
                " · 已脱离同步"
                if snapshot is not None and snapshot.boundary_states.get(asset_id) == "detached"
                else ""
            )
            if language() != "zh_CN":
                suffix = f" · {translate('已脱离同步')}" if detached else ""
                info = f"{translate('帧')} {frame.ordinal + 1} · PTS {frame.pts}{suffix}"
            else:
                info = f"帧 {frame.ordinal + 1} · PTS {frame.pts}{detached}"
        path = QPainterPath()
        path.addRoundedRect(QRectF(box.x, box.y, box.width, box.height), 6.0, 6.0)
        painter.fillPath(path, QColor(colors.surface))
        if color.hdr_unsupported:
            painter.setPen(QColor(colors.warning))
            painter.drawText(
                QRectF(box.x + 12, box.y, box.width - 24, box.height),
                Qt.AlignmentFlag.AlignCenter,
                translate("HDR/BT.2020 暂不显示画面\n仅可查看元信息"),
            )
            _stroke_pane(painter, box, colors)
            if overlay_visible:
                _draw_overlays(
                    painter,
                    colors,
                    box,
                    name=assets[asset_id].label,
                    info=info,
                    warning=warning,
                )
            continue
        if frame is None:
            _stroke_pane(painter, box, colors)
            if overlay_visible:
                _draw_overlays(
                    painter,
                    colors,
                    box,
                    name=assets[asset_id].label,
                    info=info,
                    warning=warning,
                )
            continue
        pixels = frame.rgb
        qimage = QImage(
            pixels.data,
            pixels.shape[1],
            pixels.shape[0],
            pixels.strides[0],
            QImage.Format.Format_RGB888,
        )
        metadata = assets[asset_id].display_transform
        if metadata.mirror_horizontal or metadata.mirror_vertical:
            qimage = qimage.mirrored(metadata.mirror_horizontal, metadata.mirror_vertical)
        if metadata.rotation_degrees:
            # ffprobe reports positive display rotation counter-clockwise; Qt image Y points down.
            qimage = qimage.transformed(QTransform().rotate(-metadata.rotation_degrees))
        panel = pane_transform(
            width,
            height,
            order,
            assets,
            snapshot,
            regions,
            asset_id,
            pixel_zoom=pixel_zoom,
            device_pixel_ratio=device_pixel_ratio,
            layout=layout,
        )
        if panel is None:
            continue
        content = panel.content_rect
        region = panel.region
        source = QRectF(
            (region.center_u - region.width_u / 2) * qimage.width(),
            (region.center_v - region.height_v / 2) * qimage.height(),
            region.width_u * qimage.width(),
            region.height_v * qimage.height(),
        )
        target = QRectF(content.x, content.y, content.width, content.height)
        smooth = pixel_zoom is None and panel.scale < 1
        painter.save()
        painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
        if draw_frame is None:
            # The RGB array belongs to the immutable snapshot and remains live until paint ends.
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
            painter.drawImage(target, qimage, source)
        else:
            draw_frame(painter, asset_id, frame, metadata, target, source, smooth)
        painter.restore()
        if annotations or annotation_preview is not None:
            pen_width = 3.0 if draw_frame is None else 3.0 * max(1.0, device_pixel_ratio)
            pane_annotations = tuple(
                item
                for item in annotations
                if item.target_asset_id is None or item.target_asset_id == asset_id
            )
            draw_annotations(
                painter,
                QRectF(content.x, content.y, content.width, content.height),
                pane_annotations,
                width=pen_width,
                region=region,
            )
            if annotation_preview is not None and annotation_preview.target_asset_id in {
                None,
                asset_id,
            }:
                draw_annotations(
                    painter,
                    QRectF(content.x, content.y, content.width, content.height),
                    (annotation_preview,),
                    width=pen_width,
                    region=region,
                )
        _stroke_pane(painter, box, colors)
        if overlay_visible:
            _draw_overlays(
                painter,
                colors,
                content,
                name=assets[asset_id].label,
                info=info,
                warning=warning,
            )
    if roi_preview is not None:
        painter.setPen(QPen(QColor(colors.accent), 2, Qt.PenStyle.DashLine))
        painter.fillRect(
            QRectF(roi_preview.x, roi_preview.y, roi_preview.width, roi_preview.height),
            QColor(colors.accent_fill),
        )
        painter.drawRect(
            QRectF(roi_preview.x, roi_preview.y, roi_preview.width, roi_preview.height)
        )


def _stroke_pane(painter: QPainter, box: Rect, colors: CanvasColors) -> None:
    path = QPainterPath()
    path.addRoundedRect(QRectF(box.x + 0.5, box.y + 0.5, box.width - 1, box.height - 1), 6.0, 6.0)
    painter.setPen(QPen(QColor(colors.border), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
