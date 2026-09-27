from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from video_compare.domain.models import (
    AssetInfo,
    DecodedFrame,
    DisplayTransform,
    FrameGroupSnapshot,
)
from video_compare.domain.viewport import ViewRegion
from video_compare.ui.canvas_common import pane_transform


@pytest.mark.parametrize("dpr", [1.0, 1.5, 2.0])
def test_native_pixel_transform_uses_framebuffer_pixels_and_ignores_sar(dpr: float) -> None:
    asset = AssetInfo(
        "a",
        Path("sample.mp4"),
        "fingerprint",
        0,
        640,
        480,
        Fraction(1, 1000),
        display_transform=DisplayTransform(sample_aspect_ratio=Fraction(2)),
    )
    frame = DecodedFrame(
        "a", 0, 0, Fraction(1, 1000), Fraction(0), np.zeros((480, 640, 3), np.uint8)
    )
    snapshot = FrameGroupSnapshot((1, 1, 1), Fraction(0), 0, {"a": frame})
    arguments = (360, 260, ("a",), {"a": asset}, snapshot, {"a": ViewRegion()}, "a")
    area = pane_transform(*arguments)
    pixel = pane_transform(*arguments, pixel_zoom=1.0, device_pixel_ratio=dpr)
    assert area is not None and pixel is not None
    assert area.display_width == 1280
    assert pixel.display_width == 640
    assert pixel.scale * dpr == pytest.approx(1.0)
    assert pixel.region.width_u * 640 == round(pixel.region.width_u * 640)
    assert pixel.region.height_v * 480 == round(pixel.region.height_v * 480)
    assert pixel.content_rect.x * dpr == round(pixel.content_rect.x * dpr)
    assert pixel.content_rect.y * dpr == round(pixel.content_rect.y * dpr)
    assert pixel.inverse(*pixel.forward(0.5, 0.5)) == pytest.approx((0.5, 0.5))


def test_rotated_pixel_transform_uses_rotated_sample_dimensions() -> None:
    asset = AssetInfo(
        "a",
        Path("sample.mp4"),
        "fingerprint",
        0,
        640,
        480,
        Fraction(1, 1000),
        display_transform=DisplayTransform(rotation_degrees=90, sample_aspect_ratio=Fraction(2)),
    )
    frame = DecodedFrame(
        "a", 0, 0, Fraction(1, 1000), Fraction(0), np.zeros((480, 640, 3), np.uint8)
    )
    snapshot = FrameGroupSnapshot((1, 1, 1), Fraction(0), 0, {"a": frame})
    transform = pane_transform(
        360,
        260,
        ("a",),
        {"a": asset},
        snapshot,
        {"a": ViewRegion()},
        "a",
        pixel_zoom=1.0,
        device_pixel_ratio=2.0,
    )
    assert transform is not None
    assert (transform.display_width, transform.display_height) == (480, 640)
