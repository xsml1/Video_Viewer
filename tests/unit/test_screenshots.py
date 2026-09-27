from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from video_compare.services.screenshots import _publish_composite, _publish_pair, _safe_name


def test_screenshot_names_are_windows_safe() -> None:
    assert _safe_name('a<>:"/\\|?*b. ') == "a_________b"
    assert _safe_name(" . ") == "video"


def test_png_publication_never_overwrites_existing_file(tmp_path: Path) -> None:
    image = QImage(2, 2, QImage.Format.Format_RGB888)
    image.fill(QColor("red"))
    target = tmp_path / "already.png"
    target.write_bytes(b"user file")
    with pytest.raises(FileExistsError):
        _publish_pair(image, {"group_id": [1, 2, 3]}, target)
    assert target.read_bytes() == b"user file"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["already.png"]


def test_composite_export_writes_one_image_without_json(tmp_path: Path) -> None:
    image = QImage(4, 2, QImage.Format.Format_RGB888)
    image.fill(QColor("red"))
    target = tmp_path / "对比图.png"
    other = tmp_path / "keep.png"
    other.write_bytes(b"user file")
    assert _publish_composite(image, target, "PNG", 95) == (target,)
    replacement = QImage(4, 2, QImage.Format.Format_RGB888)
    replacement.fill(QColor("blue"))
    _publish_composite(replacement, target, "PNG", 95)
    assert QImage(str(target)).pixelColor(0, 0) == QColor("blue")
    assert other.read_bytes() == b"user file"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["keep.png", "对比图.png"]


def test_composite_export_reports_encoding_failure(tmp_path: Path) -> None:
    image = QImage(4, 2, QImage.Format.Format_RGB888)
    image.fill(QColor("green"))
    target = tmp_path / "wrong.txt"
    with pytest.raises(OSError, match="编码失败"):
        _publish_composite(image, target, "PNGX", 95)
    assert not target.exists()
    assert not (tmp_path / "wrong.json").exists()
