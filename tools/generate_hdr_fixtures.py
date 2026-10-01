"""Encode real PQ/HLG/wide-gamut fixtures from independent linear source samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from generate_fixtures import frame_pixels

CASES = (
    ("pq_hevc10", "mp4", "libx265", "yuv420p10le", "smpte2084", "bt2020", "tv"),
    ("pq_hevc10_full", "mkv", "libx265", "yuv420p10le", "smpte2084", "bt2020", "pc"),
    ("hlg_hevc10", "ts", "libx265", "yuv420p10le", "arib-std-b67", "bt2020", "tv"),
    ("pq_ffv1_12", "mkv", "ffv1", "yuv444p12le", "smpte2084", "bt2020", "tv"),
    ("pq_av1_10", "mkv", "libaom-av1", "yuv420p10le", "smpte2084", "bt2020", "tv"),
    ("hlg_vp9_10", "webm", "libvpx-vp9", "yuv420p10le", "arib-std-b67", "bt2020", "tv"),
    ("bt2020_sdr10", "mkv", "ffv1", "yuv444p10le", "bt2020-10", "bt2020", "tv"),
    ("bt2020_sdr12", "mkv", "ffv1", "yuv444p12le", "bt2020-12", "bt2020", "pc"),
    ("p3_sdr10", "mkv", "ffv1", "yuv444p10le", "bt709", "smpte432", "tv"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("output must be empty; generated fixtures never overwrite existing files")
    frames = []
    for ordinal in range(36):
        rgb = np.frombuffer(frame_pixels(ordinal), np.uint8).reshape(180, 320, 3).copy()
        for index, gray in enumerate((0, 8, 16, 32, 64, 96, 128, 160, 192, 224, 255)):
            rgb[130:170, 4 + index * 28 : 28 + index * 28] = gray
        # Raw float GBR represents linear source light; no implementation HDR formulas used.
        planes = rgb.astype(np.float32).transpose(2, 0, 1)[[1, 2, 0]] / 255.0
        frames.append(planes.astype("<f4").tobytes())
    source = b"".join(frames)
    rows = []
    for name, suffix, encoder, fmt, transfer, primaries, range_name in CASES:
        path = output / f"中文 HDR [{name}].{suffix}"
        hdr = transfer in {"smpte2084", "arib-std-b67"}
        matrix = "bt2020nc" if primaries == "bt2020" else "bt709"
        vf = (
            f"zscale=pin={primaries}:tin=linear:min=gbr:rin=full:p={primaries}:"
            f"t={transfer}:m={matrix}:r={'full' if range_name == 'pc' else 'limited'}:"
            f"npl={1000 if hdr else 100},format={fmt}"
        )
        options = []
        if encoder == "libx265":
            parameters = "log-level=error:keyint=12:bframes=3"
            if transfer == "smpte2084":
                parameters += (
                    ":hdr10=1:repeat-headers=1:"
                    "master-display=G(13250,34500)B(7500,3000)R(34000,16000)"
                    "WP(15635,16450)L(10000000,1):max-cll=1000,400"
                )
            options = ["-x265-params", parameters, "-crf", "12"]
        elif encoder == "libaom-av1":
            options = ["-cpu-used", "8", "-crf", "12", "-b:v", "0"]
        elif encoder == "libvpx-vp9":
            options = ["-deadline", "realtime", "-cpu-used", "8", "-crf", "12", "-b:v", "0"]
        result = subprocess.run(
            [
                str(args.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-f",
                "rawvideo",
                "-pixel_format",
                "gbrpf32le",
                "-video_size",
                "320x180",
                "-framerate",
                "30",
                "-i",
                "pipe:0",
                "-vf",
                vf,
                "-c:v",
                encoder,
                *options,
                "-color_primaries",
                primaries,
                "-color_trc",
                transfer,
                "-colorspace",
                matrix,
                "-color_range",
                range_name,
                str(path),
            ],
            input=source,
            capture_output=True,
            timeout=90,
        )
        if result.returncode:
            raise RuntimeError(f"{name}: {result.stderr.decode('utf-8', errors='replace')}")
        rows.append(
            {
                "name": name,
                "filename": path.name,
                "transfer": transfer,
                "primaries": primaries,
                "range": range_name,
                "frame_count": 36,
                "bit_depth": 12 if "12le" in fmt else 10,
                "peak_metadata": encoder == "libx265" and transfer == "smpte2084",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (output / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    print(f"HDR_FIXTURES_OK: {len(rows)} real linear-light encoded clips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
