from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QMessageBox

from video_compare.ui.canvas_common import paint_group, pane_transform
from video_compare.ui.main_window import MainWindow


def _rgb(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    return (
        raw.reshape(converted.height(), converted.bytesPerLine())[:, : converted.width() * 3]
        .reshape(converted.height(), converted.width(), 3)
        .copy()
    )


def _canvas_pixels(canvas) -> np.ndarray:
    image = QImage(canvas.size(), QImage.Format.Format_RGB888)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    paint_group(
        painter,
        canvas.width(),
        canvas.height(),
        canvas._order,
        canvas._assets,
        canvas._snapshot,
        canvas._regions,
        canvas._roi_preview,
        canvas._colors,
        canvas.pixel_zoom,
        canvas.devicePixelRatioF(),
        None,
        canvas._layout_mode,
        canvas._overlay_visible,
        canvas.annotations,
        canvas._annotation_preview,
    )
    painter.end()
    return _rgb(image)


def _crop(data: np.ndarray, rect) -> np.ndarray:
    return data[round(rect.y) : round(rect.bottom), round(rect.x) : round(rect.right)]


def _content(window: MainWindow, asset_id: str):
    canvas = window.canvas
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._active_assets(),
        canvas._snapshot,
        canvas.view_regions,
        asset_id,
        layout=canvas.layout_mode,
    )
    assert transform is not None
    return transform.content_rect


def _point(rect, u: float, v: float) -> QPoint:
    return QPoint(round(rect.x + rect.width * u), round(rect.y + rect.height * v))


@pytest.mark.gui
@pytest.mark.parametrize("media_kind", ["video", "image"])
def test_local_rectangle_and_pen_stay_in_their_panes_and_export(
    qtbot,
    tmp_path: Path,
    monkeypatch,
    media_kind: str,
) -> None:
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe"
    )
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe,
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    if media_kind == "image":
        window._media_mode.setCurrentIndex(1)
        first, second = tmp_path / "first.png", tmp_path / "second.png"
        Image.new("RGB", (320, 180), (25, 40, 60)).save(first)
        Image.new("RGB", (320, 180), (60, 40, 25)).save(second)
        paths = [first, second]
    else:
        source = Path(__file__).resolve().parents[1] / "assets/generated/f05_h264_bframes.mp4"
        paths = [source, source]
    window.load_files(paths)
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and len(window._current_display_snapshot().frames) == 2
            and window.canvas._snapshot is not None
            and len(window.canvas._snapshot.frames) == 2
        ),
        timeout=10000,
    )
    canvas = window.canvas
    ordered = canvas.display_order
    marked = tmp_path / "marked.png"
    window.start_annotation_export(marked, layout="horizontal")
    bar = window._annotation_bar
    assert bar.link_checkbox.isChecked()
    bar.link_checkbox.setChecked(False)
    qtbot.wait(300)
    first_rect, second_rect = (_content(window, key) for key in ordered)

    baseline = tmp_path / "baseline.png"
    assert window.export_comparison_image(baseline, layout="horizontal") is not None
    qtbot.waitUntil(baseline.exists, timeout=10000)
    before_canvas = _canvas_pixels(canvas)
    second_before = _content(window, ordered[1])

    bar.set_shape("rect")
    bar.set_color("#ff3b30")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=_point(first_rect, 0.2, 0.2))
    qtbot.mouseMove(canvas, pos=_point(first_rect, 0.6, 0.6))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=_point(first_rect, 0.6, 0.6))
    assert len(canvas.annotations) == 1
    assert canvas.annotations[0].target_asset_id == ordered[0]
    qtbot.wait(50)
    after_rect_canvas = _canvas_pixels(canvas)
    second_after = _content(window, ordered[1])
    assert np.array_equal(
        _crop(before_canvas, second_before), _crop(after_rect_canvas, second_after)
    )
    first_after_rect = _content(window, ordered[0])

    first_only = tmp_path / "first-only.png"
    assert window.export_comparison_image(first_only, layout="horizontal") is not None
    qtbot.waitUntil(first_only.exists, timeout=10000)
    plan = window._composite_plan("horizontal")
    assert plan is not None
    tiles, composite, _skipped = plan
    split = tiles[0].pixel_width
    right = split + composite.gap_px
    bar.set_shape("pen")
    bar.set_color("#bf5af2")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=_point(second_rect, 0.2, 0.2))
    for fraction in (0.3, 0.4, 0.5, 0.6):
        qtbot.mouseMove(canvas, pos=_point(second_rect, fraction, fraction))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=_point(second_rect, 0.6, 0.6))
    assert len(canvas.annotations) == 2
    assert canvas.annotations[1].kind == "pen"
    assert canvas.annotations[1].target_asset_id == ordered[1]
    qtbot.wait(50)
    after_pen_canvas = _canvas_pixels(canvas)
    assert np.array_equal(
        _crop(after_rect_canvas, first_after_rect),
        _crop(after_pen_canvas, _content(window, ordered[0])),
    )

    bar.done_button.click()
    qtbot.waitUntil(marked.exists, timeout=10000)
    qtbot.waitUntil(lambda: canvas.annotations == (), timeout=10000)
    base_pixels = np.asarray(Image.open(baseline).convert("RGB"))
    first_pixels = np.asarray(Image.open(first_only).convert("RGB"))
    final_pixels = np.asarray(Image.open(marked).convert("RGB"))
    assert base_pixels.shape == first_pixels.shape == final_pixels.shape
    assert np.any(base_pixels[:, :split] != first_pixels[:, :split])
    assert np.array_equal(base_pixels[:, right:], first_pixels[:, right:])
    assert np.array_equal(first_pixels[:, :split], final_pixels[:, :split])
    assert np.any(first_pixels[:, right:] != final_pixels[:, right:])
    window.close()
