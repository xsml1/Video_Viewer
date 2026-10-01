"""Additional still readers preserving sample depth before the RGB8 preview."""

from __future__ import annotations

from pathlib import Path

import imagecodecs
import numpy as np
import tifffile
from PIL import Image

MAX_IMAGE_BYTES = 512 * 1024 * 1024


def _jpeg_header(path: Path) -> tuple[int, int, int, int] | None:
    # CharLS's check() returns None in the locked build. Read JPEG marker segments
    # instead; skipping their lengths also avoids matching marker bytes inside ICC.
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            return None
        for _segment in range(4096):
            if stream.read(1) != b"\xff":
                return None
            value = stream.read(1)
            while value == b"\xff":
                value = stream.read(1)
            if not value:
                return None
            marker = value[0]
            if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
                continue
            if marker in {0xD9, 0xDA}:
                return None
            length = stream.read(2)
            if len(length) != 2 or (size := int.from_bytes(length, "big")) < 2:
                return None
            if marker == 0xF7:
                header = stream.read(6)
                if len(header) == 6:
                    return (
                        marker,
                        header[0],
                        int.from_bytes(header[3:5], "big"),
                        int.from_bytes(header[1:3], "big"),
                    )
                return None
            stream.seek(size - 2, 1)
    return None


def check_image_size(width: int, height: int, bytes_per_pixel: int = 3) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("图像尺寸无效")
    if width * height * max(3, bytes_per_pixel) > MAX_IMAGE_BYTES:
        raise ValueError("图像解码后超过单路 512 MiB 限额")


def integer_preview(data: np.ndarray, depth: int | None = None) -> tuple[Image.Image, list[str]]:
    if data.ndim not in {2, 3} or (data.ndim == 3 and data.shape[2] not in {1, 2, 3, 4}):
        raise ValueError(f"不支持的图像通道布局：{data.shape}")
    channels = data.shape[2] if data.ndim == 3 else 1
    check_image_size(data.shape[1], data.shape[0], channels * data.dtype.itemsize)
    if data.dtype.kind == "f":
        raise ValueError("浮点/HDR 图像尚无可信显示转换，不能当作普通 SDR 预览")
    notes: list[str] = []
    if data.dtype.kind == "b":
        samples = data.astype(np.uint8) * 255
    elif data.dtype.kind == "u" and data.dtype.itemsize in {1, 2}:
        bits = depth or data.dtype.itemsize * 8
        if not 1 <= bits <= 16:
            raise ValueError(f"不支持 {bits}-bit 图像采样")
        if bits > 8:
            samples = (data >> (bits - 8)).astype(np.uint8)
            notes.append(
                "16-bit 灰度按高 8 位预览"
                if channels == 1 and bits == 16
                else f"{bits}-bit 整数按高 8 位转 RGB8 预览"
            )
        elif bits < 8:
            samples = ((data.astype(np.uint16) * 255) // ((1 << bits) - 1)).astype(np.uint8)
        else:
            samples = data.astype(np.uint8, copy=False)
    else:
        raise ValueError(f"不支持的图像采样类型：{data.dtype}；原件未改变")
    if samples.ndim == 3 and channels == 1:
        samples = samples[:, :, 0]
    return Image.fromarray(samples), notes


def open_extended_image(
    path: Path, prefix: bytes
) -> tuple[Image.Image, str, int | None, list[str]] | None:
    # Content signatures take precedence over suffixes, including renamed files.
    if prefix.startswith((b"II*\0", b"MM\0*", b"II+\0", b"MM\0+")):
        with tifffile.TiffFile(path) as source:
            page = source.pages[0]
            if 50706 in page.tags or int(page.photometric) == 32803:
                return None  # DNG/CFA must be developed by LibRaw, not used as a thumbnail.
            if int(page.photometric) not in {0, 1, 2}:
                return None  # Palette/CMYK and other models use Pillow's metadata-aware reader.
            check_image_size(
                page.imagewidth, page.imagelength, page.samplesperpixel * page.dtype.itemsize
            )
            if page.extrasamples and any(int(value) != 2 for value in page.extrasamples):
                return None  # Associated alpha is handled by Pillow.
            data = page.asarray(maxworkers=1)
            if int(page.planarconfig) == 2 and data.ndim == 3:
                data = np.moveaxis(data, 0, -1)
            if int(page.photometric) == 0 and data.dtype.kind in {"u", "b"}:
                data = (
                    np.logical_not(data)
                    if data.dtype.kind == "b"
                    else (1 << page.bitspersample) - 1 - data
                )
            image, notes = integer_preview(data, page.bitspersample)
            if len(source.pages) > 1:
                notes.append("多页/动画只显示首页")
            profile = page.tags.get(34675)
            if profile is not None:
                image.info["icc_profile"] = profile.value
            orientation = page.tags.get(274)
            if orientation is not None:
                image.getexif()[274] = int(orientation.value)
            return image, "TIFF", int(page.bitspersample), notes
    if prefix.startswith(b"\x89PNG\r\n\x1a\n") and len(prefix) >= 26 and prefix[24] == 16:
        # Pillow truncates 16-bit RGB PNG internally. Decode samples explicitly.
        with Image.open(path) as source:
            check_image_size(*source.size, 8)
            metadata = dict(source.info)
            exif = source.getexif()
        data = imagecodecs.png_decode(path.read_bytes())
        image, notes = integer_preview(data, 16)
        image.info.update(metadata)
        image.info["exif"] = exif.tobytes()
        if metadata.get("acTL") or metadata.get("duration") is not None:
            notes.append("多页/动画只显示首页")
        return image, "PNG", 16, notes
    if prefix.startswith((b"\xff\x0a", b"\0\0\0\x0cJXL \r\n\x87\n")):
        data = imagecodecs.jpegxl_decode(
            path.read_bytes(), index=0, keeporientation=False, numthreads=1
        )
        image, notes = integer_preview(data)
        notes.append("JPEG XL 只显示首页；色彩配置未校验，按解码数值预览")
        return image, "JPEG XL", None, notes
    if prefix.startswith(b"II\xbc\x01"):
        data = imagecodecs.jpegxr_decode(path.read_bytes())
        image, notes = integer_preview(data)
        notes.append("JPEG XR 色彩配置未校验，按解码数值预览")
        return image, "JPEG XR", None, notes
    if prefix.startswith(b"\xff\xd8") and (header := _jpeg_header(path)) is not None:
        _marker, depth, width, height = header
        check_image_size(width, height, 8)
        data = imagecodecs.jpegls_decode(path.read_bytes())
        image, notes = integer_preview(data, depth)
        notes.append("JPEG-LS 色彩配置未校验，按解码数值预览")
        return image, "JPEG-LS", depth, notes
    return None
