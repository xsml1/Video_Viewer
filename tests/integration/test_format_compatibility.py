from __future__ import annotations

import hashlib
import json
import random
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from video_compare.media.decoder import PreciseDecoder
from video_compare.media.images import decode_image
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video

ROOT = Path(__file__).resolve().parents[2]
FORMATS = ROOT / "tests/assets/generated/formats-20261001"
BIN = ROOT / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin"
VIDEO_NAMES = [
    "h264_mp4",
    "h264_mov",
    "h264_mkv",
    "h264_ts",
    "h264_m2ts",
    "h264_flv",
    "hevc_mp4",
    "hevc_mov",
    "hevc_mkv",
    "hevc10_mkv",
    "vp8_webm",
    "vp9_webm",
    "vp9_mkv",
    "av1_mkv",
    "av1_mp4",
    "mpeg4_avi",
    "mpeg4_mp4",
    "mpeg2_mpg",
    "mpeg2_ts",
    "mjpeg_avi",
    "mjpeg_mov",
    "wmv2_wmv",
    "prores_mov",
    "dnxhr_mov",
    "dnxhr_mxf",
    "ffv1_mkv",
    "ffv1_avi",
    "huffyuv_avi",
    "qtrle_mov",
    "theora_ogv",
]


@pytest.fixture(scope="module")
def format_manifest() -> dict:
    manifest = FORMATS / "manifest.json"
    if not manifest.is_file():
        subprocess.run(
            [
                str(ROOT / ".venv/Scripts/python.exe"),
                str(ROOT / "tools/generate_format_fixtures.py"),
                "--output",
                str(FORMATS),
                "--ffmpeg",
                str(BIN / "ffmpeg.exe"),
            ],
            check=True,
            timeout=240,
            capture_output=True,
        )
    return json.loads(manifest.read_text(encoding="utf-8"))


@pytest.mark.integration
@pytest.mark.parametrize("name", VIDEO_NAMES)
def test_real_codecs_random_seek_pts_and_source_identity(
    format_manifest, tmp_path: Path, name: str
):
    row = next(row for row in format_manifest["videos"] if row["name"] == name)
    path = FORMATS / row["filename"]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    asset = probe_video(path, ffprobe_path=BIN / "ffprobe.exe")
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(asset)
    oracle = json.loads(
        subprocess.check_output(
            [
                str(BIN / "ffprobe.exe"),
                "-v",
                "error",
                "-fflags",
                "+genpts",
                "-select_streams",
                "v:0",
                "-show_frames",
                "-show_entries",
                "frame=pts,best_effort_timestamp",
                "-of",
                "json",
                str(path),
            ],
            timeout=20,
        )
    )["frames"]
    assert timeline.frame_count == len(oracle) == 36
    # FFmpeg reconstructs omitted presentation timestamps in AVI/MPEG-PS.
    # Its independent CLI exposes these as best_effort_timestamp, as does PyAV.
    expected_pts = [frame["best_effort_timestamp"] for frame in oracle]
    assert [entry.pts for entry in timeline.entries] == expected_pts
    for entry, metadata in zip(timeline.entries, oracle, strict=True):
        if "pts" in metadata:
            assert entry.pts == metadata["pts"]
    targets = [0, 35, 11, 12, 13, 24, 23] + random.Random(123).choices(range(36), k=100)
    with PreciseDecoder(asset, timeline) as decoder:
        for target in targets:
            frame = decoder.frame_at(target)
            # Independent truth: the encoded source has black/white bits of k at fixed coordinates.
            actual = sum(
                (int(frame.rgb[13 + (bit // 8) * 14, 13 + (bit % 8) * 14, 0]) >= 128) << bit
                for bit in range(16)
            )
            assert actual == target, (name, target, actual, decoder.last_method)
            assert frame.pts == expected_pts[target]
            assert frame.local_time == Fraction(frame.pts - expected_pts[0]) * asset.time_base
            assert frame.rgb.shape == (180, 320, 3)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before == row["sha256"]


@pytest.mark.integration
def test_real_image_format_matrix_pixels_depth_and_read_only(format_manifest, qapp):
    for row in format_manifest["images"]:
        path = FORMATS / row["filename"]
        asset, frame, note = decode_image(path)
        actual = frame.rgb[frame.rgb.shape[0] // 2, frame.rgb.shape[1] // 2].astype(int)
        assert np.all(np.abs(actual - row["rgb"]) <= row["tolerance"]), (row, actual, note)
        assert not frame.rgb.flags.writeable
        if row["format"] in {"TIFF16", "PNG16"}:
            assert asset.color_info.bit_depth == 16
            assert "8 位" in note
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
