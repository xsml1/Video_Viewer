"""Generate identifiable, non-user media for the format compatibility matrix."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import subprocess
from pathlib import Path

import imagecodecs
import numpy as np
import tifffile
from generate_fixtures import frame_pixels
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

# Each container is encoded for real, including presentation reordering where supported.
VIDEO_CASES = (
    ("h264_mp4", "mp4", "libx264", "yuv420p", ["-g", "12", "-bf", "3"]),
    ("h264_mov", "mov", "libx264", "yuv420p", ["-g", "12", "-bf", "3"]),
    ("h264_mkv", "mkv", "libx264", "yuv420p", ["-g", "12", "-bf", "3"]),
    ("h264_ts", "ts", "libx264", "yuv420p", ["-g", "12", "-bf", "3"]),
    ("h264_m2ts", "m2ts", "libx264", "yuv420p", ["-g", "12", "-bf", "3", "-f", "mpegts"]),
    ("h264_flv", "flv", "libx264", "yuv420p", ["-g", "12", "-bf", "3"]),
    (
        "hevc_mp4",
        "mp4",
        "libx265",
        "yuv420p",
        ["-x265-params", "log-level=error:keyint=12:bframes=3"],
    ),
    (
        "hevc_mov",
        "mov",
        "libx265",
        "yuv420p",
        ["-x265-params", "log-level=error:keyint=12:bframes=3"],
    ),
    (
        "hevc_mkv",
        "mkv",
        "libx265",
        "yuv420p",
        ["-x265-params", "log-level=error:keyint=12:bframes=3"],
    ),
    (
        "hevc10_mkv",
        "mkv",
        "libx265",
        "yuv420p10le",
        ["-x265-params", "log-level=error:keyint=12:bframes=3"],
    ),
    ("vp8_webm", "webm", "libvpx", "yuv420p", ["-deadline", "realtime", "-cpu-used", "8"]),
    ("vp9_webm", "webm", "libvpx-vp9", "yuv420p", ["-deadline", "realtime", "-cpu-used", "8"]),
    ("vp9_mkv", "mkv", "libvpx-vp9", "yuv420p", ["-deadline", "realtime", "-cpu-used", "8"]),
    ("av1_mkv", "mkv", "libaom-av1", "yuv420p", ["-cpu-used", "8", "-crf", "20", "-b:v", "0"]),
    ("av1_mp4", "mp4", "libaom-av1", "yuv420p", ["-cpu-used", "8", "-crf", "20", "-b:v", "0"]),
    ("mpeg4_avi", "avi", "mpeg4", "yuv420p", ["-q:v", "2", "-bf", "2"]),
    ("mpeg4_mp4", "mp4", "mpeg4", "yuv420p", ["-q:v", "2", "-bf", "2"]),
    ("mpeg2_mpg", "mpg", "mpeg2video", "yuv420p", ["-q:v", "2", "-bf", "2"]),
    ("mpeg2_ts", "ts", "mpeg2video", "yuv420p", ["-q:v", "2", "-bf", "2"]),
    ("mjpeg_avi", "avi", "mjpeg", "yuvj420p", ["-q:v", "2", "-color_range", "pc"]),
    ("mjpeg_mov", "mov", "mjpeg", "yuvj420p", ["-q:v", "2", "-color_range", "pc"]),
    ("wmv2_wmv", "wmv", "wmv2", "yuv420p", ["-b:v", "2M"]),
    ("prores_mov", "mov", "prores_ks", "yuv422p10le", ["-profile:v", "2"]),
    ("dnxhr_mov", "mov", "dnxhd", "yuv422p", ["-profile:v", "dnxhr_hq"]),
    ("dnxhr_mxf", "mxf", "dnxhd", "yuv422p", ["-profile:v", "dnxhr_hq"]),
    ("ffv1_mkv", "mkv", "ffv1", "yuv444p", ["-level", "3"]),
    ("ffv1_avi", "avi", "ffv1", "yuv444p", ["-level", "3"]),
    ("huffyuv_avi", "avi", "huffyuv", "yuv422p", []),
    ("qtrle_mov", "mov", "qtrle", "rgb24", []),
    ("theora_ogv", "ogv", "libtheora", "yuv420p", ["-q:v", "8"]),
)


def make_videos(output: Path, ffmpeg: Path) -> list[dict]:
    rows: list[dict] = []
    source = b"".join(frame_pixels(k) for k in range(36))
    for name, suffix, encoder, pixel_format, options in VIDEO_CASES:
        path = output / f"中文 空格 [{name}].{suffix}"
        if path.exists():
            raise FileExistsError(path)
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-n",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            "320x180",
            "-framerate",
            "30",
            "-i",
            "pipe:0",
            "-an",
            "-threads",
            "2",
            "-c:v",
            encoder,
            "-pix_fmt",
            pixel_format,
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            *options,
            str(path),
        ]
        result = subprocess.run(
            command, input=source, capture_output=True, timeout=120, check=False
        )
        if result.returncode:
            raise RuntimeError(f"{name} encode failed: {result.stderr.decode(errors='replace')}")
        rows.append({"name": name, "filename": path.name, "encoder": encoder, "frames": 36})
        print(f"encoded {name}", flush=True)
    return rows


def write_psd(path: Path, pixels: np.ndarray) -> None:
    height, width, _channels = pixels.shape
    header = b"8BPS" + struct.pack(">H6sHIIHH", 1, b"\0" * 6, 3, height, width, 8, 3)
    path.write_bytes(header + b"\0" * 12 + b"\0\0" + pixels.transpose(2, 0, 1).tobytes())


def make_images(output: Path) -> list[dict]:
    pixels = np.zeros((32, 48, 3), np.uint8)
    pixels[:] = (120, 40, 200)
    pixels[:8, :8] = (0, 255, 0)
    image = Image.fromarray(pixels)
    rows: list[dict] = []
    for suffix, fmt, options in (
        ("png", "PNG", {}),
        ("jpg", "JPEG", {"quality": 98, "subsampling": 0}),
        ("tif", "TIFF", {"compression": "tiff_lzw"}),
        ("webp", "WEBP", {"lossless": True}),
        ("avif", "AVIF", {"quality": 100}),
        ("heic", "HEIF", {"quality": 100}),
        ("bmp", "BMP", {}),
        ("gif", "GIF", {}),
        ("tga", "TGA", {}),
        ("jp2", "JPEG2000", {}),
        ("j2k", "JPEG2000", {"no_jp2": True}),
        ("qoi", "QOI", {}),
        ("pcx", "PCX", {}),
        ("ppm", "PPM", {}),
        ("dds", "DDS", {}),
        ("sgi", "SGI", {}),
    ):
        path = output / f"中文 [{fmt}].{suffix}"
        image.save(path, format=fmt, **options)
        rows.append(
            {
                "filename": path.name,
                "format": fmt,
                "rgb": [120, 40, 200],
                "tolerance": 3 if fmt in {"JPEG", "AVIF", "HEIF"} else 0,
            }
        )
    for name, encode in (
        ("jxl", lambda data: imagecodecs.jpegxl_encode(data, lossless=True, numthreads=1)),
        ("jxr", lambda data: imagecodecs.jpegxr_encode(data, level=1)),
        ("jls", imagecodecs.jpegls_encode),
    ):
        path = output / f"中文 [{name}].{name}"
        path.write_bytes(encode(pixels))
        rows.append(
            {"filename": path.name, "format": name.upper(), "rgb": [120, 40, 200], "tolerance": 0}
        )
    psd = output / "中文 [PSD].psd"
    write_psd(psd, pixels)
    rows.append({"filename": psd.name, "format": "PSD", "rgb": [120, 40, 200], "tolerance": 0})
    for suffix, fmt in (("ico", "ICO"), ("icns", "ICNS")):
        path = output / f"图标.{suffix}"
        Image.new("RGB", (256, 256), (120, 40, 200)).save(path, format=fmt)
        rows.append({"filename": path.name, "format": fmt, "rgb": [120, 40, 200], "tolerance": 0})
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32">'
        b'<rect width="48" height="32" fill="#7828c8"/></svg>'
    )
    for suffix, data in (("svg", svg), ("svgz", gzip.compress(svg))):
        path = output / f"矢量.{suffix}"
        path.write_bytes(data)
        rows.append(
            {"filename": path.name, "format": suffix.upper(), "rgb": [120, 40, 200], "tolerance": 0}
        )
    for compression in (None, "deflate", "lzw", "zstd"):
        path = output / f"RGB16-{compression}.tiff"
        tifffile.imwrite(
            path, pixels.astype(np.uint16) * 257, photometric="rgb", compression=compression
        )
        rows.append(
            {"filename": path.name, "format": "TIFF16", "rgb": [120, 40, 200], "tolerance": 0}
        )
    path = output / "RGB16.png"
    path.write_bytes(imagecodecs.png_encode(pixels.astype(np.uint16) * 257))
    rows.append({"filename": path.name, "format": "PNG16", "rgb": [120, 40, 200], "tolerance": 0})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("output must be a new or empty directory")
    manifest = {"videos": make_videos(args.output, args.ffmpeg), "images": make_images(args.output)}
    for row in manifest["videos"] + manifest["images"]:
        row["sha256"] = hashlib.sha256((args.output / row["filename"]).read_bytes()).hexdigest()
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"FORMAT_FIXTURES_OK: {len(manifest['videos'])} videos, {len(manifest['images'])} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
