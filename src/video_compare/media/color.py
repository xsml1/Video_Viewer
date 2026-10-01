from __future__ import annotations

import av
from av.video.reformatter import ColorRange, Colorspace, Interpolation, VideoReformatter

from video_compare.domain.models import ColorInfo
from video_compare.media.hdr import display_rgb16


class ColorError(RuntimeError):
    pass


def conversion_parameters(info: ColorInfo) -> tuple[Colorspace | int, ColorRange]:
    if info.hdr_unsupported:
        raise ColorError("该源色彩编码尚无可信显示路径（BT.2020 CL/非兼容 Dolby Vision）")
    matrices = {
        "bt709": Colorspace.ITU709,
        "smpte170m": Colorspace.ITU601,
        "bt470bg": Colorspace.ITU601,
        "smpte240m": Colorspace.SMPTE240M,
        "bt2020nc": 9,  # AVColorSpace.BT2020_NCL; PyAV 16 accepts the FFmpeg integer.
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
    if info.hdr_unsupported:
        raise ColorError("该源色彩编码尚无可信显示路径（BT.2020 CL/非兼容 Dolby Vision）")
    if info.transfer in {"smpte2084", "arib-std-b67"} or info.primaries in {"bt2020", "smpte432"}:
        if info.matrix == "gbr" or (info.pixel_format or "").startswith(("rgb", "bgr", "gbr")):
            encoded = frame.to_ndarray(format="rgb48le")
        else:
            matrix, source_range = conversion_parameters(info)
            encoded = reformatter.reformat(
                frame,
                format="rgb48le",
                src_colorspace=matrix,
                # PyAV 16 only configures swscale if src/dst values differ. RGB's
                # destination matrix is irrelevant, but 0 forces explicit range/matrix.
                dst_colorspace=0,
                src_color_range=source_range,
                dst_color_range=ColorRange.JPEG,
                # FFmpeg 8's bilinear YUV420p10 -> RGB48 path corrupts chroma;
                # bicubic uses the correct conversion path (verified against CLI).
                interpolation=Interpolation.BICUBIC,
            ).to_ndarray()
        return display_rgb16(encoded, info)
    if info.matrix == "gbr" or (info.pixel_format or "").startswith(("rgb", "bgr", "gbr")):
        return frame.to_ndarray(format="rgb24")
    matrix, source_range = conversion_parameters(info)
    converted = reformatter.reformat(
        frame,
        format="rgb24",
        src_colorspace=matrix,
        dst_colorspace=0,
        src_color_range=source_range,
        dst_color_range=ColorRange.JPEG,
    )
    return converted.to_ndarray()


def display_notice(info: ColorInfo) -> str:
    if info.hdr_unsupported:
        return "不支持的 HDR/BT.2020 编码"
    if info.transfer in {"smpte2084", "arib-std-b67"}:
        kind = "PQ" if info.transfer == "smpte2084" else "HLG"
        peak = "推定峰值" if info.peak_inferred else "源峰值"
        return f"HDR {kind} → SDR · Hable · {peak} {info.peak_nits:g} nit · RGB8 预览"
    if info.primaries == "bt2020":
        return "BT.2020 SDR → BT.709 · RGB8 预览"
    if info.primaries == "smpte432":
        return "Display P3 → BT.709 · RGB8 预览"
    return ""


def display_policy_id(info: ColorInfo) -> str:
    if display_notice(info):
        mapping = (
            f"hable:{info.peak_nits:g}"
            if info.transfer in {"smpte2084", "arib-std-b67"}
            else "gamut"
        )
        return f"rgb8-v2:{info.primaries}:{info.transfer}:{mapping}"
    return "rgb8-sdr-v1"


def preview_warning(info: ColorInfo) -> str:
    parts = [display_notice(info)]
    if info.inferred:
        parts.append("色彩推定")
    if info.bit_depth and info.bit_depth > 8:
        parts.append(f"{info.bit_depth}-bit 源 · RGB8 预览")
    if info.dolby_vision:
        parts.append("Dolby Vision 兼容基础层，未应用动态元数据")
    return " · ".join(part for part in parts if part)
