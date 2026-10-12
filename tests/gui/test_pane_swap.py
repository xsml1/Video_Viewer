from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import QApplication

from video_compare.domain.models import FrameGroupSnapshot
from video_compare.domain.viewport import ViewRegion
from video_compare.media.decoder import PreciseDecoder
from video_compare.media.images import decode_image
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video
from video_compare.ui.canvas_common import pane_boxes
from video_compare.ui.canvas_software import SoftwareCompareCanvas


@pytest.fixture
def mixed_canvas(qtbot, tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    video_asset = probe_video(
        root / "tests/assets/generated/f05_h264_bframes.mp4",
        ffprobe_path=root / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe",
    )
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(video_asset)
    with PreciseDecoder(video_asset, timeline) as decoder:
        video_frame = decoder.frame_at(7)
    image_path = tmp_path / "中文 图像.png"
    Image.new("RGB", (320, 180), (70, 130, 210)).save(image_path)
    image_asset, image_frame, _note = decode_image(image_path)
    assets = {video_asset.asset_id: video_asset, image_asset.asset_id: image_asset}
    snapshot = FrameGroupSnapshot(
        (1, 2, 3),
        Fraction(7, 30),
        7,
        {video_asset.asset_id: video_frame, image_asset.asset_id: image_frame},
    )
    canvas = SoftwareCompareCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(800, 400)
    canvas.set_layout(tuple(assets), assets)
    canvas.set_layout_mode("horizontal")
    canvas.submit_group(snapshot)
    canvas.show()
    qtbot.waitUntil(lambda: canvas.isVisible())
    swaps: list[tuple[str, str]] = []
    selections: list[str] = []

    def swap(source: str, target: str) -> None:
        swaps.append((source, target))
        order = list(canvas.display_order)
        first, second = order.index(source), order.index(target)
        order[first], order[second] = order[second], order[first]
        canvas.set_layout(tuple(order), assets)

    canvas.panel_swap_requested.connect(swap)
    canvas.panel_selected.connect(selections.append)
    return canvas, snapshot, swaps, selections


def _centers(canvas) -> tuple[QPoint, QPoint]:
    boxes = pane_boxes(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        canvas._assets,
        canvas._snapshot,
        layout=canvas.layout_mode,
    )
    return tuple(
        QPoint(round(box.x + box.width / 2), round(box.y + box.height / 2))
        for box in boxes.values()
    )


@pytest.mark.gui
def test_mixed_panes_swap_by_mouse_without_changing_frames_or_view(qtbot, mixed_canvas):
    canvas, snapshot, swaps, selections = mixed_canvas
    video_id, image_id = canvas.display_order
    regions = {
        video_id: ViewRegion(0.45, 0.4, 0.5, 0.5),
        image_id: ViewRegion(0.65, 0.6, 0.4, 0.4),
    }
    canvas.set_view_state(regions, linked=False)
    before_pixels = {asset_id: frame.rgb.copy() for asset_id, frame in snapshot.frames.items()}
    start, target = _centers(canvas)
    before_feedback = canvas.grab().toImage()
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=start + QPoint(25, 0))
    assert canvas.view_regions[video_id] != regions[video_id]
    qtbot.mouseMove(canvas, pos=target)
    assert canvas._swap_target == image_id
    assert canvas.view_regions == regions
    assert canvas.grab().toImage() != before_feedback
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=target)
    assert swaps == [(video_id, image_id)]
    assert selections == [video_id]
    assert canvas.display_order == (image_id, video_id)
    assert canvas._snapshot is snapshot
    assert canvas.view_regions == regions
    assert not canvas._swap_started
    for asset_id, frame in snapshot.frames.items():
        assert canvas._snapshot.frames[asset_id] is frame
        assert np.array_equal(frame.rgb, before_pixels[asset_id])


@pytest.mark.gui
@pytest.mark.parametrize("cancellation", ["escape", "return", "outside", "leave", "layout"])
def test_pane_swap_cancelled_without_side_effects(qtbot, mixed_canvas, cancellation):
    canvas, snapshot, swaps, _selections = mixed_canvas
    order = canvas.display_order
    regions = canvas.view_regions
    start, target = _centers(canvas)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=target)
    assert canvas._swap_started
    assert canvas._swap_target == order[1]
    release = target
    if cancellation == "escape":
        qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    elif cancellation == "return":
        release = start
        qtbot.mouseMove(canvas, pos=release)
    elif cancellation == "outside":
        release = QPoint(-10, target.y())
        qtbot.mouseMove(canvas, pos=release)
    elif cancellation == "leave":
        QApplication.sendEvent(canvas, QEvent(QEvent.Type.Leave))
    else:
        canvas.set_layout_mode("vertical")
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=release)
    assert swaps == []
    assert canvas.display_order == order
    assert canvas._snapshot is snapshot
    assert canvas.view_regions == regions
    assert not canvas._swap_started


@pytest.mark.gui
def test_swap_respects_drag_threshold_and_click_selects(qtbot, mixed_canvas):
    canvas, snapshot, swaps, selections = mixed_canvas
    first, second = canvas.display_order
    boxes = pane_boxes(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        canvas._assets,
        snapshot,
        layout=canvas.layout_mode,
    )
    start = QPoint(round(boxes[first].right) - 1, round(boxes[first].y + 50))
    target = QPoint(round(boxes[second].x) + 1, start.y())
    previous = QApplication.startDragDistance()
    QApplication.setStartDragDistance(100)
    try:
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(canvas, pos=target)
        assert not canvas._swap_started
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=target)
    finally:
        QApplication.setStartDragDistance(previous)
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=_centers(canvas)[1])
    assert swaps == []
    assert selections == [first, second]


@pytest.mark.gui
@pytest.mark.parametrize("mode", ["roi", "annotation"])
def test_roi_and_annotation_take_priority_over_pane_swap(qtbot, mixed_canvas, mode):
    canvas, snapshot, swaps, selections = mixed_canvas
    order = canvas.display_order
    start, target = _centers(canvas)
    target += QPoint(0, 40)
    if mode == "roi":
        canvas.set_roi_mode(True)
    else:
        canvas.set_annotation_linked(False)
        canvas.set_annotating(True)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=target)
    assert not canvas._swap_started
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=target)
    assert swaps == []
    assert selections == [order[0]]
    assert canvas.display_order == order
    assert canvas._snapshot is snapshot
    if mode == "roi":
        assert canvas.view_regions[order[0]].width_u < 1
    else:
        assert len(canvas.annotations) == 1
        assert canvas.annotations[0].target_asset_id == order[0]


@pytest.mark.gui
def test_same_pane_left_drag_and_middle_drag_pan_without_swapping(qtbot, mixed_canvas):
    canvas, snapshot, swaps, _selections = mixed_canvas
    first, _second = canvas.display_order
    initial = dict.fromkeys(canvas.display_order, ViewRegion(0.5, 0.5, 0.4, 0.4))
    canvas.set_view_state(initial, linked=True)
    start, target = _centers(canvas)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=start + QPoint(30, 20))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=start + QPoint(30, 20))
    moved = canvas.view_regions[first]
    assert moved.center_u < 0.5
    assert moved.center_v > 0.5
    assert len(set(canvas.view_regions.values())) == 1
    canvas.set_view_state(initial, linked=True)
    qtbot.mousePress(canvas, Qt.MouseButton.MiddleButton, pos=start)
    qtbot.mouseMove(canvas, pos=target)
    qtbot.mouseRelease(canvas, Qt.MouseButton.MiddleButton, pos=target)
    assert canvas.view_regions[first] != initial[first]
    assert swaps == []
    assert canvas._snapshot is snapshot


@pytest.mark.gui
def test_double_click_continues_to_request_maximize(qtbot, mixed_canvas):
    canvas, snapshot, swaps, _selections = mixed_canvas
    double_clicks: list[str] = []
    canvas.panel_double_clicked.connect(double_clicks.append)
    qtbot.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=_centers(canvas)[1])
    assert double_clicks == [canvas.display_order[1]]
    assert swaps == []
    assert canvas._snapshot is snapshot
