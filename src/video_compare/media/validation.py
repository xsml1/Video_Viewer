from __future__ import annotations

import av

from video_compare.domain.models import AssetInfo


def validate_video_frame(frame: av.VideoFrame, asset: AssetInfo) -> None:
    if (frame.width, frame.height) != (asset.coded_width, asset.coded_height):
        raise ValueError(
            f"{asset.label} 运行中变分辨率或探测尺寸不符："
            f"{asset.coded_width}×{asset.coded_height} → {frame.width}×{frame.height}；已停止该路"
        )
    if frame.interlaced_frame:
        raise ValueError(f"{asset.label} 含交错场，尚无经过验证的显示路径")
