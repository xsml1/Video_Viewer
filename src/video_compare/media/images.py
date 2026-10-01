"""Read still images without changing the source file or using video timelines."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from uuid import uuid4

import numpy as np
import rawpy
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from PySide6.QtGui import QColor, QColorSpace, QImage, QImageReader, QPainter

from video_compare.domain.models import AssetInfo, ColorInfo, DecodedFrame
from video_compare.media.image_formats import (
    MAX_IMAGE_BYTES,
    check_image_size,
    open_extended_image,
)

register_heif_opener()


@dataclass(frozen=True, slots=True)
class ImageLoadTask:
    path: Path
    replace_id: str | None = None
    token: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class ImageLoadResult:
    task: ImageLoadTask
    asset: AssetInfo | None = None
    frame: DecodedFrame | None = None
    note: str = ""
    error: str | None = None


def _rgb_from_qimage(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    height, width = converted.height(), converted.width()
    data = np.frombuffer(converted.constBits(), dtype=np.uint8)
    return (
        data.reshape(height, converted.bytesPerLine())[:, : width * 3]
        .reshape(height, width, 3)
        .copy()
    )


def _decode_with_qt(path: Path) -> tuple[np.ndarray, str, int, str]:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        check_image_size(size.width(), size.height())
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString())
    if image.width() * image.height() * 3 > MAX_IMAGE_BYTES:
        raise ValueError("图像解码后超过单路 512 MiB 限额")
    profile = image.colorSpace()
    if profile.isValid():
        if profile.transferFunction() in {
            QColorSpace.TransferFunction.St2084,
            QColorSpace.TransferFunction.Hlg,
        }:
            raise ValueError("HDR 图像尚无可信显示路径")
        image.convertToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        note = ""
    else:
        note = "未嵌入色彩配置，按 sRGB 预览"
    alpha = image.hasAlphaChannel()
    if alpha:
        white = QImage(image.size(), QImage.Format.Format_RGB888)
        white.fill(QColor("white"))
        painter = QPainter(white)
        painter.drawImage(0, 0, image)
        painter.end()
        image = white
    if alpha:
        note = f"{note}；透明区域按白底预览" if note else "透明区域按白底预览"
    if reader.imageCount() > 1:
        note += "；多页/动画只显示首页"
    if bytes(reader.format()) in {b"svg", b"svgz", b"pdf"}:
        note += "；矢量/文档按默认尺寸栅格化预览"
    return _rgb_from_qimage(image), bytes(reader.format()).decode(errors="replace"), 8, note


def _decode_with_pillow(path: Path) -> tuple[np.ndarray, str, int | None, str]:
    with path.open("rb") as stream:
        prefix = stream.read(64)
    extended = open_extended_image(path, prefix)
    source = extended[0] if extended else Image.open(path)
    with source:
        check_image_size(*source.size)
        nclx = source.info.get("nclx_profile") or {}
        if nclx.get("transfer_characteristics") in {16, 18} or nclx.get("color_primaries") == 9:
            raise ValueError("HDR/PQ/HLG/BT.2020 图像尚无可信显示路径")
        image = ImageOps.exif_transpose(source)
        if image.width * image.height * 3 > MAX_IMAGE_BYTES:
            raise ValueError("图像解码后超过单路 512 MiB 限额")
        source_format = (
            extended[1] if extended else source.format or path.suffix.lstrip(".").upper()
        )
        depth = extended[2] if extended else source.info.get("bit_depth", 8)
        note_parts: list[str] = list(extended[3]) if extended else []
        if getattr(source, "n_frames", 1) > 1:
            note_parts.append("多页/动画只显示首页")
        if image.mode in {"I;16", "I;16L", "I;16B"}:
            gray = (np.asarray(image, dtype=np.uint16) >> 8).astype(np.uint8)
            rgb = np.repeat(gray[:, :, None], 3, axis=2)
            note_parts.append("16-bit 灰度按高 8 位预览")
            note_parts.append("未嵌入 ICC，按 sRGB 预览")
            return rgb, source_format, 16, "；".join(note_parts)
        if image.mode in {"I", "F"}:
            raise ValueError("32-bit 整数/浮点图像尚无可信 SDR 显示转换")
        icc = image.info.get("icc_profile")
        if icc:
            try:
                alpha = image.getchannel("A") if "A" in image.getbands() else None
                cms_input = image if image.mode in {"RGB", "CMYK", "L"} else image.convert("RGB")
                image = ImageCms.profileToProfile(
                    cms_input,
                    ImageCms.ImageCmsProfile(BytesIO(icc)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
                if alpha is not None:
                    image.putalpha(alpha)
            except (OSError, ValueError, ImageCms.PyCMSError):
                note_parts.append("ICC 配置无效，未校色")
        else:
            note_parts.append(
                "未嵌入 ICC，CMYK 按默认转换预览"
                if image.mode == "CMYK"
                else "未嵌入 ICC，按 sRGB 预览"
            )
        if "A" in image.getbands() or "transparency" in image.info:
            image = image.convert("RGBA")
            white = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(white, image).convert("RGB")
            note_parts.append("透明区域按白底预览")
        else:
            image = image.convert("RGB")
        if depth is not None and depth > 8 and not extended:
            note_parts.append("高位深源转 RGB8 预览")
        return (
            np.array(image, dtype=np.uint8, copy=True),
            source_format,
            depth,
            "；".join(note_parts),
        )


def decode_image(path: Path) -> tuple[AssetInfo, DecodedFrame, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as stream:
        prefix = stream.read(16)
    is_dng = False
    if prefix.startswith((b"II*\0", b"MM\0*", b"II+\0", b"MM\0+")):
        import tifffile

        with tifffile.TiffFile(path) as source:
            is_dng = 50706 in source.pages[0].tags or int(source.pages[0].photometric) == 32803
    if is_dng:
        rgb, source_format, depth, note = _decode_raw(path)
    else:
        try:
            rgb, source_format, depth, note = _decode_with_pillow(path)
        except (UnidentifiedImageError, OSError) as pillow_error:
            try:
                rgb, source_format, depth, note = _decode_with_qt(path)
            except (ValueError, OSError) as qt_error:
                try:
                    rgb, source_format, depth, note = _decode_raw(path)
                except (OSError, ValueError, rawpy.LibRawError) as raw_error:
                    raise ValueError(
                        f"无法读取图像（Pillow: {pillow_error}；Qt: {qt_error}；RAW: {raw_error}）"
                    ) from raw_error
    if rgb.nbytes > MAX_IMAGE_BYTES:
        raise ValueError("图像解码后超过单路 512 MiB 限额")
    rgb.setflags(write=False)
    stat = path.stat()
    fingerprint = hashlib.sha256(
        f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    ).hexdigest()
    asset_id = uuid4().hex
    asset = AssetInfo(
        asset_id,
        path,
        fingerprint,
        0,
        rgb.shape[1],
        rgb.shape[0],
        Fraction(1),
        color_info=ColorInfo(
            matrix="RGB/sRGB",
            range="full",
            pixel_format=source_format,
            bit_depth=depth,
            inferred=any(text in note for text in ("未嵌入", "ICC 配置无效", "色彩配置未校验")),
        ),
        codec_name=source_format,
        media_kind="image",
    )
    frame = DecodedFrame(asset_id, 0, None, Fraction(1), Fraction(0), rgb, "image-rgb8")
    return asset, frame, note


def _decode_raw(path: Path) -> tuple[np.ndarray, str, None, str]:
    with rawpy.imread(str(path)) as source:
        check_image_size(source.sizes.width, source.sizes.height, 6)
        rgb = source.postprocess(
            output_bps=8,
            use_camera_wb=True,
            no_auto_bright=True,
            output_color=rawpy.ColorSpace.sRGB,
        )
    return rgb, "RAW/LibRaw", None, "RAW 相机白平衡显影为 RGB8；未自动提亮"


class ImageLoadWorker:
    """One bounded reader; results are applied on the GUI thread only."""

    def __init__(self) -> None:
        self._tasks: Queue[ImageLoadTask | None] = Queue(maxsize=6)
        self._results: Queue[ImageLoadResult] = Queue(maxsize=6)
        self._closed = Event()
        self._thread = Thread(target=self._run, name="image-reader", daemon=True)
        self._thread.start()

    def submit(self, path: Path, replace_id: str | None = None) -> ImageLoadTask:
        if self._closed.is_set():
            raise RuntimeError("图像读取器已关闭")
        task = ImageLoadTask(path, replace_id)
        try:
            self._tasks.put_nowait(task)
        except Full as exc:
            raise RuntimeError("图像加载队列已满") from exc
        return task

    def pop_result(self) -> ImageLoadResult | None:
        try:
            return self._results.get_nowait()
        except Empty:
            return None

    def request_close(self) -> None:
        self._closed.set()
        while True:
            try:
                self._results.get_nowait()
            except Empty:
                break
        while True:
            try:
                self._tasks.get_nowait()
            except Empty:
                break
        self._tasks.put(None)

    def join(self, timeout: float = 30) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        while (task := self._tasks.get()) is not None:
            if self._closed.is_set():
                break
            try:
                asset, frame, note = decode_image(task.path)
                result = ImageLoadResult(task, asset, frame, note)
            except (
                OSError,
                ValueError,
                RuntimeError,
                SyntaxError,
                MemoryError,
                rawpy.LibRawError,
                Image.DecompressionBombError,
            ) as exc:
                result = ImageLoadResult(task, error=str(exc))
            if not self._closed.is_set():
                self._results.put(result)
