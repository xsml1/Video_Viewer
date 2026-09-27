"""Native GL checks against real rotated/SAR compressed fixtures."""

from __future__ import annotations

import argparse
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from video_compare.domain.models import FrameGroupSnapshot
from video_compare.media.decoder import PreciseDecoder
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video
from video_compare.ui.canvas_common import pane_transform
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.canvas_software import SoftwareCompareCanvas


def _rgb(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = np.frombuffer(image.constBits(), dtype=np.uint8)
    return (
        pixels.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
        .reshape(image.height(), image.width(), 3)
        .copy()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/artifacts"))
    args = parser.parse_args()
    root = Path("tests/assets/generated")
    app = QApplication(sys.argv)
    canvas = CompareCanvas()
    canvas.resize(650, 550)
    canvas.show()
    # Overlay labels live in the picture corners; hide them for pixel-exact crops.
    canvas.set_overlay_visible(False)
    software = SoftwareCompareCanvas()
    software.resize(650, 550)
    software.show()
    software.set_overlay_visible(False)
    app.processEvents()
    if not canvas.isValid():
        raise RuntimeError("Native QOpenGLWidget is not valid")
    args.output.mkdir(parents=True, exist_ok=True)
    repository = FrameIndexRepository(args.output / "display-index.sqlite3")

    for angle, quarter_turns in ((90, 1), (180, 2), (270, 3)):
        asset = probe_video(root / f"f07_rotate_{angle}.mp4", ffprobe_path=args.ffprobe)
        timeline = repository.build(asset)
        with PreciseDecoder(asset, timeline) as decoder:
            frame = decoder.frame_at(0)
        snapshot = FrameGroupSnapshot((1, angle, 1), Fraction(0), 0, {asset.asset_id: frame})
        canvas.set_layout((asset.asset_id,), {asset.asset_id: asset})
        canvas.submit_group(snapshot)
        canvas.set_pixel_mode(True)
        app.processEvents()
        image = canvas.grabFramebuffer()
        if canvas._snapshot is not snapshot:
            raise AssertionError(f"Rotated group {angle} was not committed")
        transform = pane_transform(
            canvas.width(),
            canvas.height(),
            canvas._order,
            canvas._assets,
            snapshot,
            canvas.view_regions,
            asset.asset_id,
            pixel_zoom=1.0,
            device_pixel_ratio=canvas.devicePixelRatioF(),
        )
        assert transform is not None
        dpr = canvas.devicePixelRatioF()
        content = transform.content_rect
        x, y = round(content.x * dpr), round(content.y * dpr)
        expected = np.rot90(frame.rgb, k=quarter_turns)
        actual = _rgb(image)[y : y + expected.shape[0], x : x + expected.shape[1]]
        if not np.array_equal(actual, expected):
            raise AssertionError(f"Native GL {angle} degree crop differs from decoded source")
        software.set_layout((asset.asset_id,), {asset.asset_id: asset})
        software.submit_group(snapshot)
        software.set_pixel_mode(True)
        app.processEvents()
        software_image = software.grab().toImage()
        software_transform = pane_transform(
            software.width(),
            software.height(),
            software._order,
            software._assets,
            snapshot,
            software.view_regions,
            asset.asset_id,
            pixel_zoom=1.0,
            device_pixel_ratio=software.devicePixelRatioF(),
        )
        assert software_transform is not None
        software_content = software_transform.content_rect
        sx = round(software_content.x * software.devicePixelRatioF())
        sy = round(software_content.y * software.devicePixelRatioF())
        software_crop = _rgb(software_image)[
            sy : sy + expected.shape[0], sx : sx + expected.shape[1]
        ]
        if not np.array_equal(software_crop, expected):
            raise AssertionError(f"Software {angle} degree crop differs from decoded source")
        image.save(str(args.output / f"f07_gl_rotate_{angle}.png"))
        print(f"GL rotation {angle}: exact {expected.shape[1]}x{expected.shape[0]} at DPR {dpr}")

    sar = probe_video(root / "f07_sar_4_3.mkv", ffprobe_path=args.ffprobe)
    timeline = repository.build(sar)
    with PreciseDecoder(sar, timeline) as decoder:
        frame = decoder.frame_at(0)
    snapshot = FrameGroupSnapshot((1, 4, 3), Fraction(0), 0, {sar.asset_id: frame})
    canvas.set_layout((sar.asset_id,), {sar.asset_id: sar})
    canvas.set_pixel_mode(False)
    canvas.submit_group(snapshot)
    app.processEvents()
    image = canvas.grabFramebuffer()
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas._order,
        canvas._assets,
        snapshot,
        canvas.view_regions,
        sar.asset_id,
        device_pixel_ratio=canvas.devicePixelRatioF(),
    )
    assert transform is not None
    ratio = transform.content_rect.width / transform.content_rect.height
    if abs(ratio - (320 * 4 / 3) / 180) > 0.001:
        raise AssertionError(f"SAR aspect ratio is incorrect: {ratio}")
    image.save(str(args.output / "f07_gl_sar_4_3.png"))
    print(f"GL SAR 4:3: displayed aspect {ratio:.6f}")
    canvas.close()
    software.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
