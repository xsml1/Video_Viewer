"""Generate independently identifiable local media fixtures with FFmpeg CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np


def frame_pixels(ordinal: int, width: int = 320, height: int = 180) -> bytes:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, :] = (32, 55, 80)
    image[40 : height - 12, 20 : width - 20] = (90, 125, 155)
    image[55:95, 30 + ordinal % 120 : 70 + ordinal % 120] = (220, 80, 45)
    # A 16-bit marker in 4 x 4 large blocks survives H.264 chroma subsampling.
    for bit in range(16):
        row, col = divmod(bit, 8)
        value = 240 if ordinal & (1 << bit) else 10
        y = 8 + row * 14
        x = 8 + col * 14
        image[y : y + 11, x : x + 11] = value
    return image.tobytes()


def run_encoder(ffmpeg: Path, output: Path, count: int, fps: int, lossless: bool) -> None:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        "320x180",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
    ]
    if lossless:
        command += ["-c:v", "ffv1", "-level", "3", "-g", "1", str(output)]
    else:
        command += [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "12",
            "-g",
            "48",
            "-keyint_min",
            "48",
            "-bf",
            "3",
            "-sc_threshold",
            "0",
            str(output),
        ]
    source = b"".join(frame_pixels(k) for k in range(count))
    result = subprocess.run(command, input=source, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))


def re_time(ffmpeg: Path, source: Path, output: Path, expression: str) -> None:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"setpts={expression}",
        "-fps_mode",
        "vfr",
        "-c:v",
        "ffv1",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))


def ffmpeg_file(ffmpeg: Path, *arguments: str) -> None:
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("tests/assets/generated"))
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=72)
    args = parser.parse_args()
    if args.frames < 2 or args.frames > 65535:
        parser.error("--frames must be between 2 and 65535")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "f05_h264_bframes.mp4": {"fps": 30, "codec": "h264", "frame_count": args.frames},
        "f05_ffv1_oracle.mkv": {"fps": 30, "codec": "ffv1", "frame_count": args.frames},
        "f02_24fps.mkv": {"fps": 24, "codec": "ffv1", "frame_count": args.frames},
        "f03_60fps.mkv": {"fps": 60, "codec": "ffv1", "frame_count": args.frames},
    }
    for name, metadata in fixtures.items():
        run_encoder(
            args.ffmpeg, output / name, args.frames, metadata["fps"], metadata["codec"] == "ffv1"
        )
    source = output / "f05_ffv1_oracle.mkv"
    re_time(args.ffmpeg, source, output / "f04_vfr.mkv", "N/(30*TB)+mod(N\\,3)/(120*TB)")
    re_time(args.ffmpeg, source, output / "f10_nonzero_start.mkv", "PTS+2/TB")
    shutil.copyfile(output / "f05_h264_bframes.mp4", output / "f11_中文 空格 [样例].mp4")
    ffmpeg_file(
        args.ffmpeg,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=30",
        "-frames:v",
        "600",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-g",
        "60",
        "-bf",
        "3",
        "-threads",
        "2",
        str(output / "f18_index_frontier_600.mp4"),
    )
    fixtures["f18_index_frontier_600.mp4"] = {
        "fps": 30,
        "codec": "h264",
        "frame_count": 600,
        "size": "160x90",
        "note": "Multi-chunk index frontier and B-frame playback fixture",
    }
    for angle in (90, 180, 270):
        name = f"f07_rotate_{angle}.mp4"
        ffmpeg_file(
            args.ffmpeg,
            "-display_rotation:v:0",
            str(angle),
            "-i",
            str(output / "f05_h264_bframes.mp4"),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            str(output / name),
        )
        fixtures[name] = {"codec": "h264", "frame_count": args.frames, "rotation_ccw": angle}
    ffmpeg_file(
        args.ffmpeg,
        "-i",
        str(source),
        "-vf",
        "setsar=4/3",
        "-c:v",
        "ffv1",
        str(output / "f07_sar_4_3.mkv"),
    )
    fixtures["f07_sar_4_3.mkv"] = {
        "codec": "ffv1",
        "frame_count": args.frames,
        "sample_aspect_ratio": "4/3",
    }
    for name, color_primaries, transfer, matrix in (
        ("f09_sdr_10bit.mp4", "bt709", "bt709", "bt709"),
        ("f09_hdr_pq.mp4", "bt2020", "smpte2084", "bt2020nc"),
    ):
        ffmpeg_file(
            args.ffmpeg,
            "-i",
            str(source),
            "-vf",
            "format=yuv420p10le",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            f"pools=2:frame-threads=1:colorprim={color_primaries}:"
            f"transfer={transfer}:colormatrix={matrix}",
            "-tag:v",
            "hvc1",
            str(output / name),
        )
        fixtures[name] = {
            "codec": "hevc",
            "frame_count": args.frames,
            "pixel_format": "yuv420p10le",
            "color_primaries": color_primaries,
            "color_transfer": transfer,
            "color_matrix": matrix,
            "note": "Metadata recognition only; source RGB does not model PQ light",
        }
    for label, size, frame_count, preset, crf in (
        ("480p", "854x480", 120, "veryfast", "18"),
        ("1080p", "1920x1080", 120, "veryfast", "18"),
        ("4k", "3840x2160", 30, "ultrafast", "25"),
    ):
        name = f"f06_{label}_h264.mp4"
        ffmpeg_file(
            args.ffmpeg,
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate=30",
            "-frames:v",
            str(frame_count),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            crf,
            "-g",
            "60" if label != "4k" else "30",
            "-bf",
            "3" if label != "4k" else "2",
            "-threads",
            "4",
            "-pix_fmt",
            "yuv420p",
            str(output / name),
        )
        fixtures[name] = {
            "codec": "h264",
            "frame_count": frame_count,
            "size": size,
            "fps": 30,
            "note": "Resolution/performance fixture; not an encoded frame-ID oracle",
        }
        grid_name = f"f06_grid_{label}.mp4"
        ffmpeg_file(
            args.ffmpeg,
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:size={size}:rate=1,drawgrid=w=iw/10:h=ih/10:t=2:c=white,"
            "drawbox=x=iw/4:y=ih/4:w=iw/2:h=ih/2:c=red:t=fill",
            "-frames:v",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "0",
            "-pix_fmt",
            "yuv420p",
            str(output / grid_name),
        )
        fixtures[grid_name] = {
            "codec": "h264",
            "frame_count": 2,
            "size": size,
            "fps": 1,
            "note": "Identical normalized tenth-grid and red central ROI at each resolution",
        }
    fixtures["f04_vfr.mkv"] = {"fps": "variable", "codec": "ffv1", "frame_count": args.frames}
    fixtures["f10_nonzero_start.mkv"] = {
        "fps": 30,
        "codec": "ffv1",
        "frame_count": args.frames,
        "start_s": 2,
    }
    fixtures["f11_中文 空格 [样例].mp4"] = {
        "fps": 30,
        "codec": "h264",
        "frame_count": args.frames,
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {"format": 1, "generator": "large binary pixel marker", "fixtures": fixtures}, indent=2
        ),
        encoding="utf-8",
    )
    print(f"Generated {len(fixtures)} fixtures in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
