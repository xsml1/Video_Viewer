from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMessageBox

from video_compare.domain.viewport import ViewRegion
from video_compare.media.images import decode_image
from video_compare.ui.canvas_common import pane_boxes
from video_compare.ui.main_window import MainWindow


@pytest.mark.gui
def test_real_still_formats_orientation_and_alpha(qtbot, tmp_path: Path) -> None:
    base = Image.new("RGB", (12, 8), (210, 20, 50))
    for suffix, fmt in (
        ("png", "PNG"),
        ("jpg", "JPEG"),
        ("tif", "TIFF"),
        ("webp", "WEBP"),
        ("avif", "AVIF"),
        ("heic", "HEIF"),
        ("bmp", "BMP"),
        ("gif", "GIF"),
    ):
        path = tmp_path / f"中文 图像.{suffix}"
        base.save(path, format=fmt)
        asset, frame, _note = decode_image(path)
        assert asset.media_kind == "image"
        assert frame.rgb.shape == (8, 12, 3)
        assert abs(int(frame.rgb[3, 4, 0]) - 210) <= (20 if fmt in {"JPEG", "HEIF", "AVIF"} else 1)
    svg = tmp_path / "vector.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8">'
        '<rect width="12" height="8" fill="#00ff00"/></svg>',
        encoding="utf-8",
    )
    _asset, frame, _note = decode_image(svg)
    assert tuple(frame.rgb[3, 4]) == (0, 255, 0)
    alpha = tmp_path / "alpha.png"
    Image.new("RGBA", (2, 2), (250, 0, 0, 0)).save(alpha)
    _asset, frame, note = decode_image(alpha)
    assert tuple(frame.rgb[0, 0]) == (255, 255, 255)
    assert "白底" in note
    cmyk = tmp_path / "cmyk.tif"
    Image.new("CMYK", (2, 2), (0, 255, 255, 0)).save(cmyk)
    _asset, frame, note = decode_image(cmyk)
    assert tuple(frame.rgb[0, 0]) == (255, 0, 0)
    assert "CMYK" in note
    sixteen = tmp_path / "gray16.tif"
    Image.fromarray(np.array([[0, 65535]], dtype=np.uint16)).save(sixteen)
    _asset, frame, note = decode_image(sixteen)
    assert tuple(frame.rgb[0, 0]) == (0, 0, 0)
    assert tuple(frame.rgb[0, 1]) == (255, 255, 255)
    assert "高 8 位" in note
    oriented = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    base.save(oriented, exif=exif)
    _asset, frame, _note = decode_image(oriented)
    assert frame.rgb.shape == (12, 8, 3)


@pytest.mark.gui
def test_image_mode_real_import_replace_export_and_video_return(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    first = tmp_path / "red.png"
    second = tmp_path / "blue.tif"
    replacement = tmp_path / "green.webp"
    Image.new("RGB", (32, 24), (255, 0, 0)).save(first)
    Image.new("RGB", (48, 24), (0, 0, 255)).save(second)
    Image.new("RGB", (32, 24), (0, 255, 0)).save(replacement)
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second, replacement)
    }
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    window._media_mode.setCurrentIndex(1)
    assert not window._play_button.isVisible()
    window.load_files([first, second])
    qtbot.waitUntil(
        lambda: len(window._image_assets) == 2 and window.canvas._snapshot is not None, timeout=5000
    )
    snapshot = window.canvas._snapshot
    assert [tuple(snapshot.frames[key].rgb[0, 0]) for key in window._image_assets] == [
        (255, 0, 0),
        (0, 0, 255),
    ]
    window._file_list.setCurrentRow(0)
    assert window.replace_selected(replacement)
    qtbot.waitUntil(
        lambda: any(asset.path == replacement for asset in window._image_assets.values()),
        timeout=5000,
    )
    assert [
        tuple(window.canvas._snapshot.frames[key].rgb[0, 0]) for key in window._image_assets
    ] == [(0, 255, 0), (0, 0, 255)]
    window._pixel_mode_combo.setCurrentIndex(1)
    first_id = next(iter(window._image_assets))
    window.canvas._set_region(first_id, ViewRegion(0.5, 0.5, 0.5, 0.5))
    assert {region.width_u for region in window.canvas.view_regions.values()} == {0.5}
    assert window.save_frame_screenshots(tmp_path / "saved") is not None
    qtbot.waitUntil(lambda: len(list((tmp_path / "saved").glob("*.png"))) == 2, timeout=5000)
    sidecar = json.loads(next((tmp_path / "saved").glob("*.json")).read_text(encoding="utf-8"))
    assert sidecar["media_kind"] == "image"
    target = tmp_path / "compare.png"
    assert window.export_comparison_image(target) is not None
    qtbot.waitUntil(target.exists, timeout=5000)
    assert np.asarray(Image.open(target)).size > 0
    window._pixel_mode_combo.setCurrentIndex(0)
    window.canvas.reset_fit()
    annotated = tmp_path / "annotated.png"
    window.start_annotation_export(annotated)
    canvas = window.canvas
    boxes = pane_boxes(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._image_assets,
        canvas._snapshot,
        layout=canvas.layout_mode,
    )
    box = boxes[canvas.display_order[0]]
    start = QPoint(round(box.x + box.width * 0.3), round(box.y + box.height * 0.3))
    end = QPoint(round(box.x + box.width * 0.6), round(box.y + box.height * 0.6))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert len(canvas.annotations) == 1
    window._finish_annotation_export()
    qtbot.waitUntil(annotated.exists, timeout=5000)
    qtbot.waitUntil(lambda: not canvas.annotations, timeout=5000)
    pixels = np.asarray(Image.open(annotated).convert("RGB"))
    assert (
        np.count_nonzero(
            (pixels[:, :, 0] > 180) & (pixels[:, :, 1] < 100) & (pixels[:, :, 2] < 100)
        )
        > 20
    )
    window._media_mode.setCurrentIndex(0)
    assert window.canvas._snapshot is None
    video = Path(__file__).resolve().parents[1] / "assets/generated/f05_h264_bframes.mp4"
    window.load_files([video])
    qtbot.waitUntil(
        lambda: window._transport is not None and window._transport.displayed is not None,
        timeout=5000,
    )
    video_snapshot = window._transport.displayed
    window._media_mode.setCurrentIndex(1)
    assert len(window._image_assets) == 2
    assert window.canvas._snapshot is window._image_snapshot
    window._on_group(video_snapshot)
    assert window.canvas._snapshot is window._image_snapshot
    for path, digest in before.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    window.close()
