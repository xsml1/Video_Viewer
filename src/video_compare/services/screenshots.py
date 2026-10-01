from __future__ import annotations

import json
import os
import re
import tempfile
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Condition, Thread
from typing import Literal
from uuid import uuid4

from PySide6.QtGui import QImage, QTransform

from video_compare.domain.models import AssetInfo, FrameGroupSnapshot, TimelineSpec
from video_compare.domain.viewport import ViewRegion
from video_compare.media.color import display_notice
from video_compare.services.comparison_export import (
    CompositeLayout,
    CompositeTile,
    normalize_format,
)
from video_compare.services.comparison_export import (
    render as render_composite,
)
from video_compare.ui.annotations import Annotation


@dataclass(frozen=True, slots=True)
class ScreenshotRequest:
    kind: Literal["view", "frames", "compare"]
    output_dir: Path
    snapshot: FrameGroupSnapshot
    assets: Mapping[str, AssetInfo]
    spec: TimelineSpec
    regions: Mapping[str, ViewRegion]
    view_image: QImage | None = None
    device_pixel_ratio: float = 1.0
    display_asset_ids: tuple[str, ...] = ()
    time_offsets: Mapping[str, Fraction] = field(default_factory=dict)
    frame_offsets: Mapping[str, int] = field(default_factory=dict)
    target_path: Path | None = None
    composite: CompositeLayout | None = None
    tiles: tuple[CompositeTile, ...] = ()
    image_format: str = "PNG"
    quality: int = 95
    annotations: tuple[Annotation, ...] = ()
    overlay_color: str = "#00b050"
    overlay_backdrop: str = "#99000000"


@dataclass(frozen=True, slots=True)
class ScreenshotResult:
    group_id: tuple[int, int, int]
    paths: tuple[Path, ...] = ()
    error: str | None = None
    kind: str = "view"
    image_format: str = "PNG"
    target_path: Path | None = None
    media_kind: str = "video"


def _fraction(value) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return cleaned[:48] or "video"


def _frame_image(request: ScreenshotRequest, asset_id: str) -> QImage:
    frame = request.snapshot.frames[asset_id]
    rgb = frame.rgb
    image = QImage(
        rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888
    ).copy()
    transform = request.assets[asset_id].display_transform
    if transform.mirror_horizontal or transform.mirror_vertical:
        image = image.mirrored(transform.mirror_horizontal, transform.mirror_vertical)
    if transform.rotation_degrees:
        image = image.transformed(QTransform().rotate(-transform.rotation_degrees))
    return image


def _metadata(
    request: ScreenshotRequest,
    *,
    kind: str,
    size: tuple[int, int],
    asset_id: str | None = None,
    composite: dict | None = None,
) -> dict:
    snapshot = request.snapshot
    display_ids = request.display_asset_ids or request.spec.participants
    metadata = {
        "schema_version": 1,
        "media_kind": request.assets[request.spec.reference_id].media_kind,
        "kind": kind,
        "export_asset_id": asset_id,
        "group_id": list(snapshot.group_id),
        "global_time_seconds": _fraction(snapshot.requested_global_time),
        "reference_ui_frame": (
            snapshot.reference_ordinal + 1
            if request.assets[request.spec.reference_id].media_kind == "video"
            else None
        ),
        "reference_asset_id": request.spec.reference_id,
        "sync_mode": (
            request.spec.mode.value
            if request.assets[request.spec.reference_id].media_kind == "video"
            else None
        ),
        "png_size_px": list(size),
        "device_pixel_ratio": request.device_pixel_ratio,
        "preview_format": "RGB8/PNG",
        "assets": [
            {
                "asset_id": asset_id,
                "label": request.assets[asset_id].label,
                "fingerprint": request.assets[asset_id].fingerprint,
                "source_pts": snapshot.frames[asset_id].pts,
                "time_base": _fraction(snapshot.frames[asset_id].time_base),
                "local_time_seconds": _fraction(snapshot.frames[asset_id].local_time),
                "ui_frame": (
                    snapshot.frames[asset_id].ordinal + 1
                    if request.assets[asset_id].media_kind == "video"
                    else None
                ),
                "media_kind": request.assets[asset_id].media_kind,
                "time_offset_seconds": _fraction(
                    request.time_offsets.get(
                        asset_id, request.spec.time_offsets.get(asset_id, Fraction(0))
                    )
                ),
                "frame_offset": request.frame_offsets.get(
                    asset_id, request.spec.frame_offsets.get(asset_id, 0)
                ),
                "time_sync_state": (
                    "participating" if asset_id in request.spec.participants else "detached"
                ),
                "view_region": {
                    "center_u": request.regions[asset_id].center_u,
                    "center_v": request.regions[asset_id].center_v,
                    "width_u": request.regions[asset_id].width_u,
                    "height_v": request.regions[asset_id].height_v,
                },
                "sample_aspect_ratio": _fraction(
                    request.assets[asset_id].display_transform.sample_aspect_ratio
                ),
                "rotation_degrees": request.assets[asset_id].display_transform.rotation_degrees,
                "color": {
                    "matrix": request.assets[asset_id].color_info.matrix,
                    "range": request.assets[asset_id].color_info.range,
                    "primaries": request.assets[asset_id].color_info.primaries,
                    "transfer": request.assets[asset_id].color_info.transfer,
                    "bit_depth": request.assets[asset_id].color_info.bit_depth,
                    "peak_nits": request.assets[asset_id].color_info.peak_nits,
                    "peak_inferred": request.assets[asset_id].color_info.peak_inferred,
                    "dolby_vision": request.assets[asset_id].color_info.dolby_vision,
                    "preview": display_notice(request.assets[asset_id].color_info),
                    "inferred": request.assets[asset_id].color_info.inferred,
                    "hdr_unsupported": request.assets[asset_id].color_info.hdr_unsupported,
                    "policy_id": snapshot.frames[asset_id].color_policy_id,
                },
            }
            for asset_id in display_ids
        ],
    }
    if composite is not None:
        metadata["composite"] = composite
    return metadata


def _publish_pair(image: QImage, sidecar: dict, png_path: Path) -> tuple[Path, Path]:
    json_path = png_path.with_suffix(".json")
    image_fd, image_name = tempfile.mkstemp(
        dir=png_path.parent, prefix=f".{png_path.stem}.", suffix=".png.tmp"
    )
    try:
        json_fd, json_name = tempfile.mkstemp(
            dir=png_path.parent, prefix=f".{png_path.stem}.", suffix=".json.tmp"
        )
    except OSError:
        os.close(image_fd)
        Path(image_name).unlink(missing_ok=True)
        raise
    image_temp, json_temp = Path(image_name), Path(json_name)
    published: list[Path] = []
    try:
        os.close(image_fd)
        os.close(json_fd)
        if not image.save(str(image_temp), "PNG"):
            raise OSError("PNG 编码失败")
        with json_temp.open("w", encoding="utf-8") as output:
            json.dump(sidecar, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        for temporary, target in ((image_temp, png_path), (json_temp, json_path)):
            os.link(temporary, target)
            published.append(target)
        return png_path, json_path
    except (OSError, ValueError, RuntimeError):
        for target in published:
            target.unlink(missing_ok=True)
        raise
    finally:
        image_temp.unlink(missing_ok=True)
        json_temp.unlink(missing_ok=True)


def _publish_composite(
    image: QImage,
    target: Path,
    image_format: str,
    quality: int,
) -> tuple[Path, ...]:
    """Write the user-chosen export path atomically (overwriting that file only)."""
    image_fd, image_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.stem}.", suffix=".tmp"
    )
    image_temp = Path(image_name)
    try:
        os.close(image_fd)
        if not image.save(str(image_temp), image_format, quality):
            raise OSError(f"{image_format} 编码失败")
        os.replace(image_temp, target)
        return (target,)
    finally:
        image_temp.unlink(missing_ok=True)


def export_screenshot(request: ScreenshotRequest) -> tuple[Path, ...]:
    if request.kind == "frames" and any(
        request.assets[asset_id].color_info.hdr_unsupported
        for asset_id in request.display_asset_ids or request.spec.participants
    ):
        raise ValueError("HDR/BT.2020 暂不支持可信 RGB8 原帧截图；请移除该路后重试")
    if request.kind == "compare":
        return _export_composite(request)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = request.snapshot
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid4().hex[:12]
    base = f"compare_{stamp}_f{snapshot.reference_ordinal + 1:06d}_{unique}"
    saved: list[Path] = []
    try:
        if request.kind == "view":
            if request.view_image is None or request.view_image.isNull():
                raise ValueError("合成视图像素为空")
            image = request.view_image
            png = request.output_dir / f"{base}_view.png"
            saved.extend(
                _publish_pair(
                    image,
                    _metadata(request, kind="view", size=(image.width(), image.height())),
                    png,
                )
            )
        else:
            for index, asset_id in enumerate(
                request.display_asset_ids or request.spec.participants, start=1
            ):
                image = _frame_image(request, asset_id)
                name = _safe_name(request.assets[asset_id].label)
                png = request.output_dir / f"{base}_{index}_{name}.png"
                saved.extend(
                    _publish_pair(
                        image,
                        _metadata(
                            request,
                            kind="frame",
                            size=(image.width(), image.height()),
                            asset_id=asset_id,
                        ),
                        png,
                    )
                )
        return tuple(saved)
    except (OSError, ValueError, RuntimeError, KeyError):
        for path in saved:
            path.unlink(missing_ok=True)
        raise


def _export_composite(request: ScreenshotRequest) -> tuple[Path, ...]:
    if request.composite is None or not request.tiles:
        raise ValueError("没有可导出的画面；请先导入视频并等待完整帧组")
    if request.target_path is None:
        raise ValueError("缺少导出文件路径")
    for tile in request.tiles:
        if request.assets[tile.asset_id].color_info.hdr_unsupported:
            raise ValueError("HDR/BT.2020 暂不支持可信 RGB8 导出；请移除该路后重试")
    image_format = normalize_format(request.image_format)
    quality = max(1, min(100, int(request.quality)))
    items = [(tile, _frame_image(request, tile.asset_id)) for tile in request.tiles]
    image = render_composite(
        items,
        request.composite,
        annotations=request.annotations,
        overlay_color=request.overlay_color,
        overlay_backdrop=request.overlay_backdrop,
    )
    if image.isNull():
        raise ValueError("合成图像为空")
    target = request.target_path
    if target.exists() and target.is_dir():
        raise OSError(f"导出路径是文件夹：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return _publish_composite(image, target, image_format, quality)


class ScreenshotWorker:
    """Encode frozen snapshots off the UI thread with a bounded request queue."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._requests: deque[ScreenshotRequest] = deque()
        self._results: Queue[ScreenshotResult] = Queue(maxsize=4)
        self._closed = False
        self._thread = Thread(target=self._run, name="screenshot-writer", daemon=True)
        self._thread.start()

    def submit(self, request: ScreenshotRequest) -> None:
        with self._condition:
            if self._closed or len(self._requests) >= 2:
                raise RuntimeError("截图队列已关闭或已满")
            self._requests.append(request)
            self._condition.notify()

    def pop_result(self) -> ScreenshotResult | None:
        try:
            return self._results.get_nowait()
        except Empty:
            return None

    def request_close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def join(self, timeout: float = 30) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._requests and not self._closed:
                    self._condition.wait()
                if not self._requests and self._closed:
                    return
                request = self._requests.popleft()
            try:
                paths = export_screenshot(request)
                result = ScreenshotResult(
                    request.snapshot.group_id,
                    paths,
                    kind=request.kind,
                    image_format=(
                        normalize_format(request.image_format)
                        if request.kind == "compare"
                        else "PNG"
                    ),
                    target_path=request.target_path,
                    media_kind=request.assets[request.spec.reference_id].media_kind,
                )
            except (OSError, ValueError, RuntimeError, KeyError) as exc:
                result = ScreenshotResult(
                    request.snapshot.group_id,
                    error=str(exc),
                    kind=request.kind,
                    target_path=request.target_path,
                    media_kind=request.assets[request.spec.reference_id].media_kind,
                )
            while True:
                try:
                    self._results.put(result, timeout=0.1)
                    break
                except Full:
                    with self._condition:
                        if self._closed:
                            return
