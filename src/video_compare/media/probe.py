from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

import av

from video_compare.domain.models import AssetInfo, ColorInfo, DisplayTransform


class ProbeError(RuntimeError):
    pass


class ProbeCancelled(ProbeError):
    pass


def find_binary(name: str, configured: Path | None = None) -> Path:
    if configured:
        candidate = configured.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise ProbeError(f"配置的 {name} 不存在：{candidate}")
    executable = f"{name}.exe" if os.name == "nt" else name
    bundled = Path(sys.executable).resolve().parent / "bin" / executable
    if bundled.is_file():
        return bundled
    found = shutil.which(name)
    if found:
        return Path(found).resolve()
    raise ProbeError(f"找不到 {name}；请在设置中指定路径或安装 FFmpeg")


def _fraction(value: str | None) -> Fraction | None:
    if not value or value in {"N/A", "0/0"}:
        return None
    try:
        return Fraction(value.replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        return None


def _bit_depth(stream: dict[str, Any]) -> int | None:
    explicit = stream.get("bits_per_raw_sample")
    if explicit and explicit != "0":
        return int(explicit)
    pixel_format = stream.get("pix_fmt") or ""
    try:
        return max(component.bits for component in av.VideoFormat(pixel_format).components)
    except (ValueError, KeyError):
        return None


def _fingerprint(path: Path, stream_index: int) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(path.resolve()).casefold().encode("utf-8"))
    decoder_signature = f"pyav-{av.__version__}|avcodec-{av.library_versions.get('libavcodec')}"
    digest.update(
        f"|{stat.st_size}|{stat.st_mtime_ns}|{stream_index}|index-v2|{decoder_signature}".encode()
    )
    with path.open("rb") as source:
        digest.update(source.read(64 * 1024))
        if stat.st_size > 64 * 1024:
            source.seek(max(0, stat.st_size - 64 * 1024))
            digest.update(source.read(64 * 1024))
    return digest.hexdigest()


def probe_video(
    path: Path,
    *,
    ffprobe_path: Path | None = None,
    stream_index: int | None = None,
    asset_id: str | None = None,
    timeout_s: float = 15,
    cancelled: Callable[[], bool] | None = None,
) -> AssetInfo:
    if cancelled and cancelled():
        raise ProbeCancelled(f"已取消探测 {path.name}")
    path = path.expanduser().resolve(strict=True)
    command = [
        str(find_binary("ffprobe", ffprobe_path)),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-show_frames",
        "-read_intervals",
        "%+#1",
        "-show_entries",
        "frame=stream_index,side_data_list",
        "-of",
        "json",
        str(path),
    ]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise ProbeError(f"无法探测 {path.name}：{exc}") from exc
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            if cancelled and cancelled():
                raise ProbeCancelled(f"已取消探测 {path.name}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError(f"探测 {path.name} 超时（{timeout_s:g} 秒）")
            try:
                stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    if process.returncode != 0:
        reason = stderr.decode("utf-8", errors="replace")[:2000]
        raise ProbeError(f"探测失败 {path.name}（退出码 {process.returncode}）：{reason}")
    try:
        metadata: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe 返回了无效 JSON：{path.name}") from exc
    streams = [
        stream
        for stream in metadata.get("streams", [])
        if stream.get("codec_type") == "video"
        and not stream.get("disposition", {}).get("attached_pic", 0)
    ]
    if stream_index is not None:
        streams = [stream for stream in streams if stream.get("index") == stream_index]
    if not streams:
        raise ProbeError(f"没有可用视频流：{path.name}")
    stream = streams[0]
    if stream.get("field_order") not in {None, "unknown", "progressive"}:
        raise ProbeError(f"暂不支持交错扫描视频：{path.name}（{stream['field_order']}）")
    side_data = stream.get("side_data_list") or []
    frame_side_data = [
        item
        for frame in metadata.get("frames", [])
        if frame.get("stream_index") == stream["index"]
        for item in frame.get("side_data_list", [])
    ]
    rotation = 0
    for item in side_data:
        if "rotation" in item:
            rotation = int(round(float(item["rotation"]))) % 360
            break
    if rotation not in {0, 90, 180, 270}:
        raise ProbeError(f"暂不支持旋转角度 {rotation}°：{path.name}")
    transfer = stream.get("color_transfer")
    primaries = stream.get("color_primaries")
    hdr = transfer in {"smpte2084", "arib-std-b67"}
    width, height = int(stream["width"]), int(stream["height"])
    matrix = stream.get("color_space")
    range_name = stream.get("color_range")
    peak = None
    dolby = False
    unsupported_dolby = False
    for item in [*side_data, *frame_side_data]:
        if "dv_profile" in item:
            dolby = True
            unsupported_dolby = item.get("dv_bl_signal_compatibility_id", 0) not in {1, 2, 4}
        if item.get("max_content") and float(item["max_content"]) > 0:
            peak = float(item["max_content"])
        elif peak is None and item.get("max_luminance"):
            peak = float(_fraction(str(item["max_luminance"])) or 0) or None
    if peak is not None and (not math.isfinite(peak) or not 0.1 <= peak <= 10000):
        peak = None  # Invalid peak metadata must be labeled as an inferred preview value.
    inferred = not matrix or not range_name
    if matrix in {"bt2020nc", "bt2020c"} and not primaries:
        primaries = "bt2020"
        inferred = True
    if primaries in {"bt2020", "smpte432"} and not transfer:
        inferred = True
    if hdr and not primaries:
        primaries = "bt2020"
        inferred = True
    if (hdr or primaries == "bt2020") and not matrix:
        matrix = "bt2020nc"
        inferred = True
    color = ColorInfo(
        matrix=matrix or ("bt709" if height >= 720 else "smpte170m"),
        range=range_name or "unspecified",
        primaries=primaries,
        transfer=transfer,
        pixel_format=stream.get("pix_fmt"),
        bit_depth=_bit_depth(stream),
        inferred=inferred,
        hdr_unsupported=matrix == "bt2020c" or unsupported_dolby,
        peak_nits=peak if peak is not None else 1000.0,
        peak_inferred=peak is None,
        dolby_vision=dolby,
    )
    sar = _fraction(stream.get("sample_aspect_ratio")) or Fraction(1)
    return AssetInfo(
        asset_id=asset_id or _fingerprint(path, int(stream["index"]))[:16],
        path=path,
        fingerprint=_fingerprint(path, int(stream["index"])),
        stream_index=int(stream["index"]),
        coded_width=width,
        coded_height=height,
        time_base=_fraction(stream.get("time_base")) or Fraction(1, 1),
        display_transform=DisplayTransform(rotation_degrees=rotation, sample_aspect_ratio=sar),
        color_info=color,
        codec_name=stream.get("codec_name"),
        average_rate=_fraction(stream.get("avg_frame_rate")),
        duration_hint=_fraction(stream.get("duration")),
    )
