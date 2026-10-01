from __future__ import annotations

from pathlib import Path

import imagecodecs
import numpy as np
import pytest
import tifffile
from PIL import Image

from video_compare.media import image_formats
from video_compare.media.images import ImageLoadWorker, decode_image


def test_renamed_jxl_and_png_use_contents_even_with_raw_suffix(tmp_path: Path):
    pixels = np.full((8, 12, 3), (15, 90, 240), np.uint8)
    jxl = tmp_path / "renamed.bin"
    jxl.write_bytes(imagecodecs.jpegxl_encode(pixels, lossless=True, numthreads=1))
    png = tmp_path / "misleading.cr2"
    Image.fromarray(pixels).save(png, format="PNG")
    for path in (jxl, png):
        _asset, frame, _note = decode_image(path)
        assert np.array_equal(frame.rgb, pixels)


@pytest.mark.parametrize("orientation", [2, 3, 4, 5, 6, 7, 8])
def test_rgb16_tiff_orientation_and_planar_samples(tmp_path: Path, orientation: int):
    values = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)
    path = tmp_path / "planar.tiff"
    tifffile.imwrite(
        path,
        (values.astype(np.uint16) * 257).transpose(2, 0, 1),
        photometric="rgb",
        planarconfig="separate",
        extratags=[(274, "H", 1, orientation, False)],
    )
    methods = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_270,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_90,
    }
    expected = np.asarray(Image.fromarray(values).transpose(methods[orientation]))
    asset, frame, _note = decode_image(path)
    assert asset.color_info.bit_depth == 16
    assert np.array_equal(frame.rgb, expected)


def test_png16_preserves_depth_and_composites_alpha_on_white(tmp_path: Path):
    data = np.array([[[65535, 0, 0, 0], [0, 65535, 0, 65535], [65535, 0, 0, 32768]]], np.uint16)
    path = tmp_path / "alpha16.png"
    path.write_bytes(imagecodecs.png_encode(data))
    asset, frame, note = decode_image(path)
    assert asset.color_info.bit_depth == 16
    assert frame.rgb.tolist() == [[[255, 255, 255], [0, 255, 0], [255, 127, 127]]]
    assert "白底" in note


def test_multi_page_tiff_uses_only_first_real_page(tmp_path: Path):
    path = tmp_path / "pages.tiff"
    with tifffile.TiffWriter(path) as writer:
        writer.write(np.full((8, 12, 3), (10, 20, 30), np.uint8), photometric="rgb")
        writer.write(np.full((8, 12, 3), (40, 50, 60), np.uint8), photometric="rgb")
    _asset, frame, note = decode_image(path)
    assert tuple(frame.rgb[0, 0]) == (10, 20, 30)
    assert "只显示首页" in note


def test_real_libraw_bayer_dng_and_renamed_dng_use_sensor_not_thumbnail(tmp_path: Path):
    pixels = np.full((256, 384), 2048, np.uint16)
    # DNG 1.4 RGGB sensor, D65 identity camera matrix, half-level neutral light.
    tags = [
        (50706, "B", 4, (1, 4, 0, 0), False),
        (50707, "B", 4, (1, 1, 0, 0), False),
        (50708, "s", 0, "Synthetic verification sensor", False),
        (33421, "H", 2, (2, 2), False),
        (33422, "B", 4, (0, 1, 1, 2), False),
        (50710, "B", 3, (0, 1, 2), False),
        (50711, "H", 1, 1, False),
        (50713, "H", 2, (1, 1), False),
        (50714, "2I", 1, (0, 1), False),
        (50717, "I", 1, 4095, False),
        (50721, "2i", 9, (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1), False),
        (50728, "2I", 3, (1, 1, 1, 1, 1, 1), False),
        (50778, "H", 1, 21, False),
    ]
    path = tmp_path / "synthetic.dng"
    tifffile.imwrite(path, pixels, photometric=32803, metadata=None, extratags=tags)
    original = path.read_bytes()
    renamed = tmp_path / "renamed.bin"
    renamed.write_bytes(original)
    for source in (path, renamed):
        asset, frame, note = decode_image(source)
        assert asset.codec_name == "RAW/LibRaw"
        assert frame.rgb.shape == (256, 384, 3)
        assert tuple(frame.rgb[100, 100]) == (180, 180, 180)
        assert "未自动提亮" in note
        assert not frame.rgb.flags.writeable
        assert source.read_bytes() == original


def test_size_budget_is_checked_before_native_tiff_decode(tmp_path: Path, monkeypatch):
    path = tmp_path / "too-large.tiff"
    tifffile.imwrite(path, np.zeros((8, 12, 3), np.uint16), photometric="rgb")
    monkeypatch.setattr(image_formats, "MAX_IMAGE_BYTES", 100)
    monkeypatch.setattr(
        tifffile.TiffPage,
        "asarray",
        lambda *_args, **_kwargs: pytest.fail("decoded before size check"),
    )
    with pytest.raises(ValueError, match="512 MiB"):
        decode_image(path)


def test_float_hdr_failure_does_not_kill_reader_and_next_file_loads(qtbot, tmp_path: Path):
    hdr = tmp_path / "floating.tif"
    tifffile.imwrite(hdr, np.full((8, 12, 3), 2.0, np.float32), photometric="rgb")
    valid = tmp_path / "valid.png"
    Image.new("RGB", (12, 8), (50, 60, 70)).save(valid)
    worker = ImageLoadWorker()
    results = []
    try:
        worker.submit(hdr)
        worker.submit(valid)

        def loaded():
            while (result := worker.pop_result()) is not None:
                results.append(result)
            return len(results) == 2

        qtbot.waitUntil(loaded, timeout=5000)
        assert "HDR" in results[0].error
        assert results[1].error is None
        assert tuple(results[1].frame.rgb[0, 0]) == (50, 60, 70)
    finally:
        worker.request_close()
        assert worker.join(timeout=5)
