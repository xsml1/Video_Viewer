from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QImage

from video_compare.domain.models import FrameGroupSnapshot, SyncMode, TimelineSpec
from video_compare.domain.viewport import ViewRegion
from video_compare.media.decoder import PreciseDecoder
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video
from video_compare.services.screenshots import ScreenshotRequest, export_screenshot

ROOT = Path(__file__).resolve().parents[1] / "assets" / "generated"
BIN = (
    Path(__file__).resolve().parents[2]
    / ".codex-tools"
    / "ffmpeg"
    / "ffmpeg-9.0.1-essentials_build"
    / "bin"
)


def _rgb(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = np.frombuffer(image.constBits(), dtype=np.uint8)
    return (
        pixels.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
        .reshape(image.height(), image.width(), 3)
        .copy()
    )


def _orange_box(pixels: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where((pixels[:, :, 0] > 140) & (pixels[:, :, 1] < 120) & (pixels[:, :, 2] < 100))
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


@pytest.mark.integration
def test_rotation_and_sar_metadata_match_independent_ffprobe() -> None:
    for angle in (90, 180, 270):
        path = ROOT / f"f07_rotate_{angle}.mp4"
        asset = probe_video(path, ffprobe_path=BIN / "ffprobe.exe")
        result = subprocess.run(
            [str(BIN / "ffprobe.exe"), "-v", "error", "-show_streams", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        stream = json.loads(result.stdout)["streams"][0]
        assert stream["side_data_list"][0]["rotation"] % 360 == angle
        assert asset.display_transform.rotation_degrees == angle
    sar = probe_video(ROOT / "f07_sar_4_3.mkv", ffprobe_path=BIN / "ffprobe.exe")
    assert sar.display_transform.sample_aspect_ratio == Fraction(4, 3)


@pytest.mark.integration
def test_rotated_frame_screenshot_matches_ffmpeg_autorotate(tmp_path: Path) -> None:
    path = ROOT / "f07_rotate_90.mp4"
    asset = probe_video(path, ffprobe_path=BIN / "ffprobe.exe")
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(asset)
    decoder = PreciseDecoder(asset, timeline)
    try:
        frame = decoder.frame_at(0)
    finally:
        decoder.close()
    snapshot = FrameGroupSnapshot((1, 1, 1), Fraction(0), 0, {asset.asset_id: frame})
    request = ScreenshotRequest(
        kind="frames",
        output_dir=tmp_path / "screenshots",
        snapshot=snapshot,
        assets={asset.asset_id: asset},
        spec=TimelineSpec(SyncMode.TIME, asset.asset_id, (asset.asset_id,)),
        regions={asset.asset_id: ViewRegion()},
    )
    paths = export_screenshot(request)
    image = QImage(str(next(path for path in paths if path.suffix == ".png")))
    actual = _rgb(image)
    assert np.array_equal(actual, np.rot90(frame.rgb, k=1))
    reference = subprocess.check_output(
        [
            str(BIN / "ffmpeg.exe"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
    )
    ffmpeg_rgb = np.frombuffer(reference, dtype=np.uint8).reshape(320, 180, 3)
    assert _orange_box(actual) == _orange_box(ffmpeg_rgb)


@pytest.mark.integration
def test_hevc_10bit_sdr_and_hdr_policy(tmp_path: Path) -> None:
    sdr = probe_video(ROOT / "f09_sdr_10bit.mp4", ffprobe_path=BIN / "ffprobe.exe")
    hdr = probe_video(ROOT / "f09_hdr_pq.mp4", ffprobe_path=BIN / "ffprobe.exe")
    assert sdr.color_info.bit_depth == 10
    assert sdr.color_info.transfer == "bt709"
    assert not sdr.color_info.hdr_unsupported
    assert hdr.color_info.bit_depth == 10
    assert hdr.color_info.transfer == "smpte2084"
    assert not hdr.color_info.hdr_unsupported

    # The requested HDR feature produces a labeled SDR preview from actual source pixels.
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(hdr)
    with PreciseDecoder(hdr, timeline) as decoder:
        frame = decoder.frame_at(0)
    assert frame.rgb.dtype == np.uint8
    assert frame.color_policy_id == "rgb8-v2:bt2020:smpte2084:hable:1000"
    sdr_timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(sdr)
    decoder = PreciseDecoder(sdr, sdr_timeline)
    try:
        sdr_frame = decoder.frame_at(0)
    finally:
        decoder.close()
    assert sdr_frame.color_policy_id == "rgb8-sdr-v1"
    snapshot = FrameGroupSnapshot((1, 1, 1), Fraction(0), 0, {hdr.asset_id: frame})
    output = tmp_path / "hdr-frames"
    request = ScreenshotRequest(
        kind="frames",
        output_dir=output,
        snapshot=snapshot,
        assets={hdr.asset_id: hdr},
        spec=TimelineSpec(SyncMode.TIME, hdr.asset_id, (hdr.asset_id,)),
        regions={hdr.asset_id: ViewRegion()},
    )
    paths = export_screenshot(request)
    image = QImage(str(next(path for path in paths if path.suffix == ".png")))
    assert np.array_equal(_rgb(image), frame.rgb)
    metadata = json.loads(next(path for path in paths if path.suffix == ".json").read_text("utf-8"))
    color = metadata["assets"][0]["color"]
    assert color["transfer"] == "smpte2084"
    assert color["primaries"] == "bt2020"
    assert "HDR PQ → SDR" in color["preview"]
    assert color["policy_id"] == frame.color_policy_id
