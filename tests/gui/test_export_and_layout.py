from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QMessageBox

from video_compare.domain.viewport import ViewRegion
from video_compare.services.settings import load_settings
from video_compare.ui.canvas_common import pane_boxes, pane_transform
from video_compare.ui.main_window import MainWindow


def ffprobe_path() -> Path:
    path = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    assert path.is_file(), "运行 GUI 真实媒体测试需要先安装项目 FFmpeg"
    return path


def fixture_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    assert (root / "f05_h264_bframes.mp4").is_file(), "先运行 fixture 生成器"
    return root


def rgb(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    rows = raw.reshape(converted.height(), converted.bytesPerLine())
    return rows[:, : converted.width() * 3].reshape(converted.height(), converted.width(), 3).copy()


def crop(frame: np.ndarray, region: dict) -> np.ndarray:
    height, width = frame.shape[:2]
    left = round(region["center_u"] * width - region["width_u"] * width / 2)
    top = round(region["center_v"] * height - region["height_v"] * height / 2)
    box_width = max(1, min(width, round(region["width_u"] * width)))
    box_height = max(1, min(height, round(region["height_v"] * height)))
    left = min(max(0, left), max(0, width - box_width))
    top = min(max(0, top), max(0, height - box_height))
    return frame[top : top + box_height, left : left + box_width]


@pytest.mark.gui
def test_portrait_pair_is_packed_without_a_large_middle_gap(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe_path(),
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.resize(1200, 780)
    window.show()
    root = fixture_root()
    # Both fixtures carry rotation metadata and display as 180x320 portrait video.
    window.load_files([root / "f07_rotate_90.mp4", root / "f07_rotate_270.mp4"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=10000,
    )
    canvas = window.canvas
    order = canvas.display_order
    boxes = pane_boxes(
        canvas.width(),
        canvas.height(),
        order,
        window._assets,
        canvas._snapshot,
        layout=canvas.layout_mode,
    )
    first, second = boxes[order[0]], boxes[order[1]]
    assert first.height == pytest.approx(second.height)
    assert first.width < first.height, "竖屏视频必须按竖向比例显示"
    assert second.x - first.right <= 12, "两路竖屏视频之间不应留出大片空隙"
    assert first.x >= 12 or second.right <= canvas.width() - 12
    rendered = rgb(canvas.grab().toImage())
    background = np.array(QColor(canvas._colors.background).getRgb()[:3], dtype=np.uint8)
    gap_x = round((first.right + second.x) / 2)
    gap_y = round(first.y + first.height / 2)
    assert np.array_equal(rendered[gap_y, gap_x], background), "中间空隙应是画布背景"
    inside_x = round(first.x + first.width / 2)
    inside = rendered[round(first.y + first.height / 2), inside_x]
    assert not np.array_equal(inside, background), "画面框内应是真实视频像素"


@pytest.mark.gui
def test_layout_mode_combo_switches_and_is_remembered(qtbot, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.toml"
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe_path(),
        software=True,
        settings_path=settings_path,
    )
    qtbot.addWidget(window)
    window.show()
    index = next(
        i
        for i in range(window._layout_combo.count())
        if window._layout_combo.itemData(i) == "vertical"
    )
    window._layout_combo.setCurrentIndex(index)
    assert window.canvas.layout_mode == "vertical"
    assert load_settings(settings_path).layout == "vertical"
    window.load_files([fixture_root() / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=10000)
    canvas = window.canvas
    boxes = pane_boxes(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._assets,
        canvas._snapshot,
        layout="horizontal",
    )
    assert boxes[canvas.display_order[0]].y < boxes[canvas.display_order[0]].bottom


@pytest.mark.gui
def test_export_writes_visible_pixels_without_ui(qtbot, tmp_path: Path, monkeypatch) -> None:
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, text: notices.append((title, text)),
    )
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe_path(),
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    window.load_files([fixture_root() / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window._current_display_snapshot() is not None, timeout=10000)
    canvas = window.canvas
    asset_id = canvas.display_order[0]
    window._pixel_mode_combo.setCurrentIndex(1)
    canvas._set_region(asset_id, ViewRegion(0.5, 0.45, 0.5, 0.6))
    target = tmp_path / "对比图.png"
    group = window.export_comparison_image(target, layout="window", image_format="PNG")
    assert group == window._current_display_snapshot().group_id
    qtbot.waitUntil(lambda: target.is_file(), timeout=10000)
    qtbot.waitUntil(lambda: bool(notices), timeout=10000)
    assert notices[0][0] == "导出成功"
    assert str(target) in notices[0][1]
    assert not target.with_suffix(".json").exists(), "导出不应再生成 JSON"
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._assets,
        canvas._snapshot,
        canvas.view_regions,
        asset_id,
        pixel_zoom=canvas.pixel_zoom,
        device_pixel_ratio=canvas.devicePixelRatioF(),
        layout=canvas.layout_mode,
    )
    assert transform is not None
    content = transform.content_rect
    frame = window._current_display_snapshot().frames[asset_id].rgb
    expected = crop(
        frame,
        {
            "center_u": transform.region.center_u,
            "center_v": transform.region.center_v,
            "width_u": transform.region.width_u,
            "height_v": transform.region.height_v,
        },
    )
    exported = rgb(QImage(str(target)))
    assert exported.shape[:2] == (round(content.height), round(content.width))
    # 左上角文件名、右下角帧信息会覆盖角落像素，其余区域与窗口所见一致。
    assert np.array_equal(exported[40:-40, 40:-40], expected[40:-40, 40:-40]), (
        "导出画面中部应与窗口显示逐像素一致"
    )


@pytest.mark.gui
def test_export_supports_jpeg_and_reports_failure(qtbot, tmp_path: Path, monkeypatch) -> None:
    failures: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, text: failures.append(f"{title}::{text}"),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe_path(),
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    window.load_files(
        [fixture_root() / "f05_h264_bframes.mp4", fixture_root() / "f05_ffv1_oracle.mkv"]
    )
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and len(window._current_display_snapshot().frames) == 2
        ),
        timeout=10000,
    )
    jpeg = tmp_path / "对比图.jpg"
    group = window.export_comparison_image(jpeg, layout="vertical", image_format="JPEG", quality=90)
    assert group is not None
    qtbot.waitUntil(lambda: jpeg.is_file(), timeout=10000)
    assert not jpeg.with_suffix(".json").exists()
    image = QImage(str(jpeg))
    assert not image.isNull()
    tall = image.height() > image.width(), "竖向排列应为上下两行"
    assert tall

    blocker = tmp_path / "not-a-directory.txt"
    blocker.write_text("keep", encoding="utf-8")
    assert window.export_comparison_image(blocker / "out.png", layout="window") is not None
    qtbot.waitUntil(lambda: bool(failures), timeout=10000)
    assert failures[0].startswith("导出失败::")
    assert "没有保存成功" in failures[0]
    assert blocker.read_text(encoding="utf-8") == "keep"


@pytest.mark.gui
def test_annotated_export_syncs_shapes_and_colours(qtbot, tmp_path: Path, monkeypatch) -> None:
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, text: notices.append((title, text)),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: None)
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe_path(),
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    window.load_files(
        [fixture_root() / "f05_h264_bframes.mp4", fixture_root() / "f05_ffv1_oracle.mkv"]
    )
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and len(window._current_display_snapshot().frames) == 2
        ),
        timeout=10000,
    )
    canvas = window.canvas
    order = canvas.display_order
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        order,
        window._assets,
        canvas._snapshot,
        canvas.view_regions,
        order[0],
        layout=canvas.layout_mode,
    )
    assert transform is not None
    content = transform.content_rect
    assert not window._annotation_bar.isVisible()
    target = tmp_path / "标注导出.png"
    window.start_annotation_export(target, layout="window", image_format="PNG")
    assert window._annotation_bar.isVisible()
    assert canvas.annotating
    canvas.set_annotation_shape("rect")
    canvas.set_annotation_color("#0a84ff")
    start = QPoint(round(content.x + content.width * 0.2), round(content.y + content.height * 0.2))
    end = QPoint(round(content.x + content.width * 0.6), round(content.y + content.height * 0.5))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert len(canvas.annotations) == 1
    window._annotation_bar.done_button.click()
    qtbot.waitUntil(lambda: target.is_file(), timeout=10000)
    qtbot.waitUntil(lambda: bool(notices), timeout=10000)
    assert not window._annotation_bar.isVisible()
    assert not canvas.annotating
    assert canvas.annotations == ()
    assert not target.with_suffix(".json").exists()
    exported = rgb(QImage(str(target)))
    blue = np.array([10, 132, 255], dtype=np.int16)
    hits = (np.abs(exported.astype(np.int16) - blue).max(axis=2) <= 40).sum()
    assert hits > 200, f"导出图应包含蓝色标注，实际命中 {hits}"

    cancelled_target = tmp_path / "取消的标注.png"
    window.start_annotation_export(cancelled_target)
    assert canvas.annotations == ()
    window._annotation_bar.set_shape("pen")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    for fraction in (0.3, 0.4, 0.5, 0.6):
        point = QPoint(
            round(content.x + content.width * fraction),
            round(content.y + content.height * (fraction / 2)),
        )
        qtbot.mouseMove(canvas, pos=point)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=point)
    assert len(canvas.annotations) == 1
    assert canvas.annotations[0].kind == "pen"
    assert len(canvas.annotations[0].points) >= 3
    assert window._annotation_bar.annotation_select.count() == 1
    window._annotation_bar.delete_button.click()
    assert canvas.annotations == ()
    assert not window._annotation_bar.delete_button.isEnabled()

    window._annotation_bar.set_shape("rect")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    window._annotation_bar.set_shape("line")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert [item.kind for item in canvas.annotations] == ["rect", "line"]
    window._annotation_bar.annotation_select.setCurrentIndex(0)
    window._annotation_bar.delete_button.click()
    assert [item.kind for item in canvas.annotations] == ["line"]
    window._annotation_bar.cancel_button.click()
    assert not canvas.annotating
    assert canvas.annotations == ()
    assert not cancelled_target.exists()

    pen_target = tmp_path / "自由画笔.png"
    window.start_annotation_export(pen_target)
    window._annotation_bar.set_shape("pen")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    for fraction in (0.3, 0.4, 0.5, 0.6):
        point = QPoint(
            round(content.x + content.width * fraction),
            round(content.y + content.height * (fraction / 2)),
        )
        qtbot.mouseMove(canvas, pos=point)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=point)
    assert canvas.annotations[0].kind == "pen"
    window._annotation_bar.done_button.click()
    qtbot.waitUntil(lambda: pen_target.is_file(), timeout=10000)
    qtbot.waitUntil(lambda: canvas.annotations == (), timeout=10000)
    pen_pixels = rgb(QImage(str(pen_target)))
    assert (np.abs(pen_pixels.astype(np.int16) - blue).max(axis=2) <= 40).sum() > 30

    failed_target = tmp_path / "写入失败.png"
    window.start_annotation_export(failed_target)
    window._annotation_bar.set_shape("line")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert len(canvas.annotations) == 1

    def fail_write(_request):
        raise OSError("模拟磁盘写入失败")

    monkeypatch.setattr("video_compare.services.screenshots.export_screenshot", fail_write)
    window._annotation_bar.done_button.click()
    qtbot.waitUntil(lambda: not window._saving_annotated_export, timeout=10000)
    assert window._annotation_bar.isVisible()
    assert window._annotation_bar.isEnabled()
    assert canvas.annotating
    assert len(canvas.annotations) == 1
    window._annotation_bar.cancel_button.click()
    assert canvas.annotations == ()
    assert not failed_target.exists()


@pytest.mark.gui
def test_annotation_tracks_source_through_zoom_and_export(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: None)
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe_path(),
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    window.load_files(
        [fixture_root() / "f05_h264_bframes.mp4", fixture_root() / "f05_ffv1_oracle.mkv"]
    )
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=10000,
    )
    canvas = window.canvas
    first = canvas.display_order[0]
    target = tmp_path / "缩放后的标注.png"
    window.start_annotation_export(target)
    window._annotation_bar.set_shape("line")
    window._annotation_bar.set_color("#bf5af2")
    canvas._set_region(first, ViewRegion(0.5, 0.5, 0.5, 0.5))

    def transform():
        return pane_transform(
            canvas.width(),
            canvas.height(),
            canvas.display_order,
            window._assets,
            canvas._snapshot,
            canvas.view_regions,
            first,
            layout=canvas.layout_mode,
        )

    before = transform()
    assert before is not None
    start = QPoint(*map(round, before.forward(0.4, 0.4)))
    end = QPoint(*map(round, before.forward(0.6, 0.6)))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert len(canvas.annotations) == 1
    mark = canvas.annotations[0]
    assert mark.start == pytest.approx((0.4, 0.4), abs=0.003)
    assert mark.end == pytest.approx((0.6, 0.6), abs=0.003)

    canvas._set_region(first, ViewRegion(0.55, 0.5, 0.4, 0.4))
    after = transform()
    assert after is not None
    point = QPoint(*map(round, after.forward(*mark.start)))
    preview = rgb(canvas.grab().toImage())
    purple = np.array([191, 90, 242], dtype=np.int16)

    def hits_near(image: np.ndarray, x: int, y: int) -> int:
        patch = image[max(0, y - 5) : y + 6, max(0, x - 5) : x + 6]
        return int((np.abs(patch.astype(np.int16) - purple).max(axis=2) <= 40).sum())

    assert hits_near(preview, point.x(), point.y()) > 0
    plan = window._composite_plan("window")
    assert plan is not None
    tile = plan[0][0]
    source_left = tile.region.center_u - tile.region.width_u / 2
    source_top = tile.region.center_v - tile.region.height_v / 2
    expected_x = round((mark.start[0] - source_left) * tile.pixel_width / tile.region.width_u)
    expected_y = round((mark.start[1] - source_top) * tile.pixel_height / tile.region.height_v)
    window._annotation_bar.done_button.click()
    qtbot.waitUntil(lambda: target.is_file(), timeout=10000)
    qtbot.waitUntil(lambda: canvas.annotations == (), timeout=10000)
    exported = rgb(QImage(str(target)))
    assert hits_near(exported, expected_x, expected_y) > 0
