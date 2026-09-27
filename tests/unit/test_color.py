import av
from av.video.reformatter import ColorRange, Colorspace, VideoReformatter

from video_compare.domain.models import ColorInfo
from video_compare.media.color import conversion_parameters, to_rgb8


def test_limited_and_full_gray_conversion_are_explicit() -> None:
    frame = av.VideoFrame(2, 2, "yuv420p")
    for index, plane in enumerate(frame.planes):
        plane.update(bytes([16 if index == 0 else 128]) * plane.buffer_size)
    limited = ColorInfo(matrix="smpte170m", range="tv", pixel_format="yuv420p")
    full = ColorInfo(matrix="smpte170m", range="pc", pixel_format="yuv420p")
    assert conversion_parameters(limited) == (Colorspace.ITU601, ColorRange.MPEG)
    assert conversion_parameters(full) == (Colorspace.ITU601, ColorRange.JPEG)
    assert tuple(to_rgb8(frame, limited, VideoReformatter())[0, 0]) == (0, 0, 0)
    assert tuple(to_rgb8(frame, full, VideoReformatter())[0, 0]) == (16, 16, 16)


def test_601_and_709_matrices_produce_distinct_reference_patches() -> None:
    frame = av.VideoFrame(2, 2, "yuv420p")
    for plane, value in zip(frame.planes, (81, 90, 240), strict=True):
        plane.update(bytes([value]) * plane.buffer_size)
    info_601 = ColorInfo(matrix="smpte170m", range="tv", pixel_format="yuv420p")
    info_709 = ColorInfo(matrix="bt709", range="tv", pixel_format="yuv420p")
    assert tuple(to_rgb8(frame, info_601, VideoReformatter())[0, 0]) == (253, 0, 0)
    assert tuple(to_rgb8(frame, info_709, VideoReformatter())[0, 0]) == (255, 23, 0)
