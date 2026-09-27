from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage

from video_compare.domain.viewport import ViewRegion
from video_compare.services.comparison_export import (
    CompositeLayout,
    CompositeTile,
    crop_rect,
    normalize_format,
    plan_size,
    render,
    rows_from_boxes,
)
from video_compare.ui.annotations import Annotation


def pattern(width: int, height: int, *, base: int = 0) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    for y in range(height):
        for x in range(width):
            image.setPixelColor(
                x,
                y,
                QColor((base + x * 3) % 256, (base + y * 5) % 256, (base + x + y) % 256),
            )
    return image


def as_array(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    rows = raw.reshape(converted.height(), converted.bytesPerLine())
    return rows[:, : converted.width() * 3].reshape(converted.height(), converted.width(), 3).copy()


def test_crop_rect_maps_region_to_source_pixels() -> None:
    region = ViewRegion(0.5, 0.5, 0.5, 0.5)
    rect = crop_rect(400, 200, region)
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (100, 50, 200, 100)
    corner = crop_rect(400, 200, ViewRegion(0.05, 0.05, 0.5, 0.5))
    assert (corner.x(), corner.y()) == (0, 0)
    whole = crop_rect(400, 200, ViewRegion())
    assert (whole.x(), whole.y(), whole.width(), whole.height()) == (0, 0, 400, 200)


def test_horizontal_export_keeps_exact_visible_pixels() -> None:
    source = pattern(200, 100)
    region = ViewRegion(0.5, 0.5, 0.4, 0.6)
    tile = CompositeTile("a", region, 80, 60)
    composite = CompositeLayout(((0,),))
    image = render([(tile, source)], composite)
    rect = crop_rect(200, 100, region)
    assert image.width() == 80 and image.height() == 60
    assert np.array_equal(
        as_array(image), as_array(source)[rect.y() : rect.y() + 60, rect.x() : rect.x() + 80]
    )


def test_two_tiles_are_packed_with_one_gap_and_centered_rows() -> None:
    first = pattern(120, 60, base=10)
    second = pattern(80, 90, base=40)
    tiles = (
        CompositeTile("a", ViewRegion(0.5, 0.5, 1.0, 1.0), 120, 60),
        CompositeTile("b", ViewRegion(0.5, 0.5, 1.0, 1.0), 80, 90),
    )
    horizontal = render(list(zip(tiles, (first, second), strict=True)), CompositeLayout(((0, 1),)))
    assert (horizontal.width(), horizontal.height()) == (120 + 6 + 80, 90)
    vertical = render(list(zip(tiles, (first, second), strict=True)), CompositeLayout(((0,), (1,))))
    assert (vertical.width(), vertical.height()) == (120, 60 + 6 + 90)
    assert plan_size(tiles, CompositeLayout(((0,), (1,)))) == (120, 156)
    pixels = as_array(vertical)
    # The narrower pane is centered inside the wider row.
    assert np.array_equal(pixels[0:60, 0:120], as_array(first))
    assert np.array_equal(pixels[66:156, 20:100], as_array(second))


def test_export_rejects_inconsistent_layouts() -> None:
    tile = CompositeTile("a", ViewRegion(), 10, 10)
    with pytest.raises(ValueError, match="不存在的画面"):
        plan_size([tile], CompositeLayout(((0, 1),)))
    with pytest.raises(ValueError, match="重复引用"):
        plan_size([tile, tile], CompositeLayout(((0, 0),)))
    with pytest.raises(ValueError, match="没有覆盖"):
        plan_size([tile, tile], CompositeLayout(((0,),)))
    with pytest.raises(ValueError, match="空行"):
        plan_size([tile], CompositeLayout(((),)))
    with pytest.raises(ValueError, match="导出内容为空"):
        render([], CompositeLayout(((0,),)))
    with pytest.raises(ValueError, match="尺寸必须为正数"):
        CompositeTile("a", ViewRegion(), 0, 10)
    with pytest.raises(ValueError, match="不支持的图片格式"):
        normalize_format("tiff")


def test_format_aliases_and_row_grouping() -> None:
    assert normalize_format("png") == "PNG"
    assert normalize_format("JPEG") == "JPEG"
    assert normalize_format("jpg") == "JPEG"
    boxes = [(100.0, 10.0), (100.4, 200.0), (400.0, 10.0), (10.0, 10.0)]
    assert rows_from_boxes(boxes) == ((3,), (0, 1), (2,))
    assert rows_from_boxes([(0.0, 5.0), (0.0, 1.0)]) == ((1, 0),)


def test_export_does_not_prepend_a_label_strip() -> None:
    """A label strip or border would shift or repaint the first video pixels."""
    source = pattern(40, 40, base=7)
    region = ViewRegion(0.5, 0.5, 0.5, 0.5)
    tile = CompositeTile("a", region, 20, 20)
    image = render([(tile, source)], CompositeLayout(((0,),)), draw_labels=False)
    expected = as_array(source)[10:30, 10:30]
    assert (image.width(), image.height()) == (20, 20)
    assert np.array_equal(as_array(image), expected)
    assert image.format() == QImage.Format.Format_RGB888


def test_export_draws_corner_labels_and_annotations(qapp) -> None:
    # 文本绘制需要 QGuiApplication；pytest-qt 的 qapp 夹具提供它。
    source = QImage(200, 120, QImage.Format.Format_RGB888)
    source.fill(QColor("#101010"))
    tile = CompositeTile("a", ViewRegion(), 200, 120, name="clip.mp4", info="帧 7 · PTS 200")
    annotation = Annotation("rect", (0.2, 0.2), (0.8, 0.8), "#ff3b30")
    plain = render([(tile, source)], CompositeLayout(((0,),)), draw_labels=False)
    labelled = render(
        [(tile, source)],
        CompositeLayout(((0,),)),
        annotations=(annotation,),
        overlay_color="#00b050",
    )
    assert plain.pixelColor(5, 5) == QColor("#101010")
    # 左上角出现绿色文件名、右下角出现绿色帧信息，中间出现红色标注。
    assert _count(labelled, "#00b050", (0, 0, 100, 24)) > 10
    assert _count(labelled, "#00b050", (100, 96, 200, 120)) > 10
    assert _count(labelled, "#ff3b30", (40, 40, 160, 96)) > 20
    assert _count(plain, "#ff3b30") == 0


def test_export_limits_local_annotations_to_their_asset(qapp) -> None:
    source = QImage(100, 100, QImage.Format.Format_RGB888)
    source.fill(QColor("#101010"))
    tiles = [
        CompositeTile("a", ViewRegion(), 100, 100),
        CompositeTile("b", ViewRegion(), 100, 100),
    ]
    items = list(zip(tiles, (source, source), strict=True))
    layout = CompositeLayout(((0, 1),))
    linked = Annotation("rect", (0.2, 0.2), (0.8, 0.8), "#ff3b30")
    local = Annotation("pen", (0.1, 0.1), (0.9, 0.9), "#bf5af2", ((0.1, 0.1), (0.9, 0.9)), "a")
    both = render(items, layout, annotations=(linked,), draw_labels=False)
    scoped = render(items, layout, annotations=(linked, local), draw_labels=False)
    before = as_array(both)
    after = as_array(scoped)
    assert _count(both, "#ff3b30", (0, 0, 100, 100)) > 20
    assert _count(both, "#ff3b30", (106, 0, 206, 100)) > 20
    assert np.any(before[:, :100] != after[:, :100])
    assert np.array_equal(before[:, 106:], after[:, 106:])


def _count(image: QImage, color: str, box: tuple[int, int, int, int] | None = None) -> int:
    """Pixels close to ``color`` inside an optional (x0, y0, x1, y1) window."""
    data = as_array(image).astype(np.int16)
    if box is not None:
        x0, y0, x1, y1 = box
        data = data[y0:y1, x0:x1]
    target = np.array(QColor(color).getRgb()[:3], dtype=np.int16)
    return int((np.abs(data - target).max(axis=2) <= 40).sum())
