from __future__ import annotations

import hashlib
import json
import random
import subprocess
from pathlib import Path

import numpy as np
import pytest

from video_compare.media.color import display_notice
from video_compare.media.decoder import PreciseDecoder
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "tests/assets/generated/hdr-20261001"
BIN = ROOT / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin"
NAMES = (
    "pq_hevc10",
    "pq_hevc10_full",
    "hlg_hevc10",
    "pq_ffv1_12",
    "pq_av1_10",
    "hlg_vp9_10",
    "bt2020_sdr10",
    "bt2020_sdr12",
    "p3_sdr10",
)


@pytest.fixture(scope="module")
def hdr_manifest() -> list[dict]:
    if not (MEDIA / "manifest.json").is_file():
        subprocess.run(
            [
                str(ROOT / ".venv/Scripts/python.exe"),
                str(ROOT / "tools/generate_hdr_fixtures.py"),
                "--ffmpeg",
                str(BIN / "ffmpeg.exe"),
                "--output",
                str(MEDIA),
            ],
            capture_output=True,
            check=True,
            timeout=240,
        )
    return json.loads((MEDIA / "manifest.json").read_text("utf-8"))


def independent_preview(path: Path, transfer: str, primaries: str, range_name: str) -> np.ndarray:
    # CLI swscale -> independent zimg inverse transfer/primaries -> FFmpeg Hable -> zimg OETF.
    # RGB16 intermediate matches the supported preview policy's quantization, not its formulas.
    matrix = "bt2020" if primaries == "bt2020" else "bt709"
    rgb16 = subprocess.check_output(
        [
            str(BIN / "ffmpeg.exe"),
            "-v",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            f"scale=in_color_matrix={matrix}:in_range={range_name}:out_range=pc:flags=bicubic,"
            "format=rgb48le",
            "-pix_fmt",
            "rgb48le",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        timeout=30,
    )
    # Reset RGB range/transfer metadata explicitly: copied YUV limited-range metadata
    # in a single optimized filter graph would expand RGB a second time in FFmpeg 9.
    filters = (
        "format=gbrp16le,"
        f"zscale=pin={primaries}:tin={transfer}:min=gbr:rin=full:"
        "p=bt709:t=linear:m=gbr:r=full:npl=100,format=gbrpf32le,"
    )
    if transfer in {"smpte2084", "arib-std-b67"}:
        filters += "tonemap=hable:desat=0:peak=10,"
    filters += (
        "zscale=pin=bt709:tin=linear:min=gbr:rin=full:p=bt709:"
        "t=bt709:m=gbr:r=full:npl=100,format=rgb24"
    )
    pixels = subprocess.run(
        [
            str(BIN / "ffmpeg.exe"),
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb48le",
            "-video_size",
            "320x180",
            "-i",
            "pipe:0",
            "-frames:v",
            "1",
            "-vf",
            filters,
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        input=rgb16,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    return np.frombuffer(pixels, np.uint8).reshape(180, 320, 3)


@pytest.mark.integration
@pytest.mark.parametrize("name", NAMES)
def test_hdr_wide_gamut_real_seek_metadata_and_independent_pixels(hdr_manifest, tmp_path, name):
    row = next(row for row in hdr_manifest if row["name"] == name)
    path = MEDIA / row["filename"]
    asset = probe_video(path, ffprobe_path=BIN / "ffprobe.exe")
    color = asset.color_info
    assert not color.hdr_unsupported
    assert color.transfer == row["transfer"]
    assert color.primaries == row["primaries"]
    assert color.range == row["range"]
    assert color.bit_depth == row["bit_depth"]
    if row["peak_metadata"]:
        assert color.peak_nits == 1000
        assert not color.peak_inferred
    assert "→" in display_notice(color)
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(asset)
    assert timeline.frame_count == row["frame_count"]
    oracle = json.loads(
        subprocess.check_output(
            [
                str(BIN / "ffprobe.exe"),
                "-v",
                "error",
                "-show_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=best_effort_timestamp",
                "-of",
                "json",
                str(path),
            ],
            timeout=20,
        )
    )
    assert [entry.pts for entry in timeline.entries] == [
        frame["best_effort_timestamp"] for frame in oracle["frames"]
    ]
    with PreciseDecoder(asset, timeline) as decoder:
        first = decoder.frame_at(0)
        reference = independent_preview(path, row["transfer"], row["primaries"], row["range"])
        difference = np.abs(first.rgb.astype(int) - reference.astype(int))
        # 8-bit integer rounding is the only allowed preview difference.
        assert difference.max() <= 1, (name, difference.max(), difference.mean())
        for target in [35, 0, 13, 12, 11, 1] + random.Random(2084).choices(range(36), k=40):
            frame = decoder.frame_at(target)
            identity = sum(
                (int(frame.rgb[13 + (bit // 8) * 14, 13 + (bit % 8) * 14, 0]) >= 128) << bit
                for bit in range(16)
            )
            assert identity == target, (name, target, identity)
            assert frame.pts == timeline.entries[target].pts
            assert not frame.rgb.flags.writeable
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
