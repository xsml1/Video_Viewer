"""Turn a user logo into transparent app icon assets.

Two input kinds are supported:

* artwork that already carries transparency (for example ``logo2.png``) is kept
  exactly as delivered and only trimmed / resized;
* artwork with an opaque white background has only the border-connected white
  removed, so white details inside the picture stay intact; edge pixels are
  un-premultiplied against white to avoid a light halo.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND_MIN = 240


def load_rgba(path: Path) -> tuple[QImage, np.ndarray]:
    image = QImage(str(path)).convertToFormat(QImage.Format.Format_RGBA8888)
    if image.isNull():
        raise SystemExit(f"无法读取图片：{path}")
    raw = np.frombuffer(image.constBits(), dtype=np.uint8)
    pixels = (
        raw.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 4]
        .reshape(image.height(), image.width(), 4)
        .copy()
    )
    return image, pixels


def background_mask(pixels: np.ndarray, *, threshold: int = BACKGROUND_MIN) -> np.ndarray:
    """Background-ish pixels connected to the image border (scanline flood fill)."""
    height, width = pixels.shape[:2]
    candidate = pixels.min(axis=2) >= threshold
    filled = np.zeros((height, width), dtype=bool)
    stack: list[tuple[int, int]] = []
    for y in range(height):
        for x in (0, width - 1):
            if candidate[y, x]:
                stack.append((y, x))
    for x in range(width):
        for y in (0, height - 1):
            if candidate[y, x]:
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        if filled[y, x] or not candidate[y, x]:
            continue
        x0 = x
        while x0 > 0 and candidate[y, x0 - 1] and not filled[y, x0 - 1]:
            x0 -= 1
        x1 = x
        while x1 < width - 1 and candidate[y, x1 + 1] and not filled[y, x1 + 1]:
            x1 += 1
        filled[y, x0 : x1 + 1] = True
        for neighbor in (y - 1, y + 1):
            if not 0 <= neighbor < height:
                continue
            row = candidate[neighbor, x0 : x1 + 1] & ~filled[neighbor, x0 : x1 + 1]
            if not row.any():
                continue
            edges = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
            for start in edges[0::2]:
                stack.append((neighbor, x0 + int(start)))
    return filled


def key_out_background(pixels: np.ndarray, background: np.ndarray) -> np.ndarray:
    """RGBA result: background transparent, edge pixels un-premultiplied from white."""
    pixels = pixels[:, :, :3]
    height, width = pixels.shape[:2]
    alpha = np.where(background, 0, 255).astype(np.int16)
    # Widen the band by one pixel so anti-aliased edges lose their white fringe.
    band = np.zeros_like(background)
    for shift in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        rolled = np.roll(background, shift, axis=(0, 1))
        if shift[0] == 1:
            rolled[0, :] = False
        elif shift[0] == -1:
            rolled[-1, :] = False
        elif shift[1] == 1:
            rolled[:, 0] = False
        else:
            rolled[:, -1] = False
        band |= rolled
    band &= ~background
    minimum = pixels.min(axis=2).astype(np.int16)
    edge = band & (minimum < 250)
    edge_alpha = np.clip(255 - minimum, 0, 255)
    alpha = np.where(edge, edge_alpha, alpha)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = pixels
    rgba[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    if edge.any():
        scale = np.maximum(edge_alpha[edge], 1).astype(np.float32)
        flat = pixels[edge].astype(np.float32)
        unpremultiplied = np.clip(
            (flat - (255.0 - scale)[:, None]) * 255.0 / scale[:, None], 0.0, 255.0
        )
        rgba[edge, :3] = unpremultiplied.astype(np.uint8)
    rgba[background, 3] = 0
    return rgba


def has_transparency(pixels: np.ndarray) -> bool:
    return bool((pixels[:, :, 3] < 250).mean() > 0.02)


def normalize(pixels: np.ndarray) -> tuple[np.ndarray, str]:
    """Return RGBA pixels plus a note describing which path was used."""
    if has_transparency(pixels):
        return pixels, "输入已带透明通道：保留原始 alpha，只做裁剪与缩放"
    rgb = pixels[:, :, :3]
    return key_out_background(rgb, background_mask(rgb)), "白底抠图：仅移除与边缘连通的白色"


def trim_square(rgba: np.ndarray, *, margin_ratio: float = 0.04) -> np.ndarray:
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if not len(ys):
        raise SystemExit("裁剪失败：图像没有可见像素")
    top, bottom = int(ys.min()), int(ys.max())
    left, right = int(xs.min()), int(xs.max())
    cropped = rgba[top : bottom + 1, left : right + 1]
    height, width = cropped.shape[:2]
    side = int(max(height, width) * (1 + margin_ratio * 2))
    square = np.zeros((side, side, 4), dtype=np.uint8)
    y = (side - height) // 2
    x = (side - width) // 2
    square[y : y + height, x : x + width] = cropped
    return square


def to_qimage(rgba: np.ndarray) -> QImage:
    height, width = rgba.shape[:2]
    return QImage(rgba.data, width, height, rgba.strides[0], QImage.Format.Format_RGBA8888).copy()


def scaled(image: QImage, size: int) -> QImage:
    return image.scaled(
        QSize(size, size),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise SystemExit("PNG 编码失败")
    return bytes(buffer.data())


def write_ico(path: Path, image: QImage, sizes: tuple[int, ...] = ICO_SIZES) -> None:
    """Write a multi-size icon; each entry is stored as a PNG payload."""
    entries = [(size, png_bytes(scaled(image, size))) for size in sizes]
    header = bytearray()
    header += (0).to_bytes(2, "little")
    header += (1).to_bytes(2, "little")
    header += len(entries).to_bytes(2, "little")
    offset = 6 + 16 * len(entries)
    directory = bytearray()
    payload = bytearray()
    for size, data in entries:
        directory += bytes([0 if size >= 256 else size, 0 if size >= 256 else size])
        directory += bytes([0, 0])
        directory += (1).to_bytes(2, "little")
        directory += (32).to_bytes(2, "little")
        directory += len(data).to_bytes(4, "little")
        directory += offset.to_bytes(4, "little")
        offset += len(data)
        payload += data
    path.write_bytes(bytes(header + directory + payload))


def checkerboard(width: int, height: int, *, block: int = 16) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    painter = QPainter(image)
    try:
        for y in range(0, height, block):
            for x in range(0, width, block):
                light = ((x // block) + (y // block)) % 2 == 0
                painter.fillRect(x, y, block, block, QColor("#ffffff" if light else "#d9dee6"))
    finally:
        painter.end()
    return image


def preview(image: QImage, path: Path, *, size: int = 256) -> None:
    canvas = QImage(size * 3, size, QImage.Format.Format_RGB888)
    canvas.fill(QColor("#f4f6f9"))
    painter = QPainter(canvas)
    try:
        painter.drawImage(0, 0, checkerboard(size, size))
        painter.fillRect(size, 0, size, size, QColor("#ffffff"))
        painter.fillRect(size * 2, 0, size, size, QColor("#12161c"))
        for index in range(3):
            painter.drawImage(index * size, 0, scaled(image, size))
    finally:
        painter.end()
    canvas.save(str(path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("logo/logo2.png"))
    parser.add_argument("--output", type=Path, default=Path("src/video_compare/assets"))
    parser.add_argument("--preview", type=Path, default=Path("reports/artifacts/logo"))
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()
    app = QGuiApplication(sys.argv[:1])
    _image, pixels = load_rgba(args.source)
    rgba, note = normalize(pixels)
    square = trim_square(rgba)
    icon_image = scaled(to_qimage(square), args.size)
    args.output.mkdir(parents=True, exist_ok=True)
    png_path = args.output / "app.png"
    ico_path = args.output / "app.ico"
    if not icon_image.save(str(png_path), "PNG"):
        raise SystemExit(f"无法写入 {png_path}")
    write_ico(ico_path, icon_image)
    args.preview.mkdir(parents=True, exist_ok=True)
    preview(to_qimage(square), args.preview / "logo_preview.png")
    to_qimage(square).save(str(args.preview / "logo_transparent.png"))
    transparent = int((rgba[:, :, 3] == 0).sum())
    print(
        f"source {args.source} {pixels.shape[1]}x{pixels.shape[0]} -> icon "
        f"{icon_image.width()}x{icon_image.height()}, transparent pixels {transparent} "
        f"({transparent / (pixels.shape[0] * pixels.shape[1]):.1%})"
    )
    print(note)
    print(f"wrote {png_path} sha256={hashlib.sha256(png_path.read_bytes()).hexdigest()[:16]}")
    print(f"wrote {ico_path} sha256={hashlib.sha256(ico_path.read_bytes()).hexdigest()[:16]}")
    print(f"preview {args.preview / 'logo_preview.png'}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
