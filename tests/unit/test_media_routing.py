from pathlib import Path

import pytest
from PIL import Image

from video_compare.media.formats import infer_media_kind, media_file_filter


def test_real_image_contents_override_video_suffix(tmp_path: Path) -> None:
    path = tmp_path / "图像 重命名.mp4"
    Image.new("RGB", (12, 8), (12, 34, 56)).save(path, format="PNG")
    assert infer_media_kind(path) == "image"
    video = Path(__file__).resolve().parents[1] / "assets/generated/f05_h264_bframes.mp4"
    assert infer_media_kind(video) == "video"


@pytest.mark.parametrize("suffix, expected", [(".cr3", "image"), (".crm", "video")])
def test_canon_container_keeps_raw_and_movie_routes_separate(
    tmp_path: Path, suffix: str, expected: str
) -> None:
    # The ISO BMFF header alone tests routing; this is not a RAW decode fixture.
    path = tmp_path / f"canon{suffix}"
    path.write_bytes(b"\0\0\0\x18ftypcrx \0\0\0\0crx isom")
    assert infer_media_kind(path) == expected


def test_missing_file_routes_to_background_reader_and_filter_accepts_both(tmp_path: Path) -> None:
    assert infer_media_kind(tmp_path / "missing.png") == "image"
    assert infer_media_kind(tmp_path / "missing.mp4") == "video"
    file_filter = media_file_filter("mixed")
    assert "*.png" in file_filter and "*.mp4" in file_filter and "所有文件 (*)" in file_filter
