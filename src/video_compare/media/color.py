from __future__ import annotations

import av
from av.video.reformatter import ColorRange, Colorspace, VideoReformatter

from video_compare.domain.models import ColorInfo


class ColorError(RuntimeError):
    pass


def conversion_parameters(info: ColorInfo) -> tuple[Colorspace, ColorRange]:
    if info.hdr_unsupported:
        raise ColorError("HDR 源尚无可信 tone mapping，不提供 SDR 画面")
    matrices = {
        "bt709": Colorspace.ITU709,
        "smpte170m": Colorspace.ITU601,
        "bt470bg": Colorspace.ITU601,
        "smpte240m": Colorspace.SMPTE240M,
    }
    matrix = matrices.get(info.matrix or "")
    if matrix is None:
        raise ColorError(f"暂不支持颜色矩阵：{info.matrix}")
    if info.range in {"pc", "jpeg"} or (info.pixel_format or "").startswith("yuvj"):
        source_range = ColorRange.JPEG
    elif info.range in {"tv", "mpeg", "unspecified", None}:
        source_range = ColorRange.MPEG
    else:
        raise ColorError(f"暂不支持颜色范围：{info.range}")
    return matrix, source_range


def to_rgb8(frame: av.VideoFrame, info: ColorInfo, reformatter: VideoReformatter):
    if info.matrix == "gbr" or (info.pixel_format or "").startswith(("rgb", "bgr", "gbr")):
        return frame.to_ndarray(format="rgb24")
    matrix, source_range = conversion_parameters(info)
    converted = reformatter.reformat(
        frame,
        format="rgb24",
        src_colorspace=matrix,
        src_color_range=source_range,
        dst_color_range=ColorRange.JPEG,
    )
    return converted.to_ndarray()
