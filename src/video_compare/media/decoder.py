from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from fractions import Fraction

import av
from av.video.reformatter import VideoReformatter

from video_compare.domain.models import AssetInfo, DecodedFrame
from video_compare.domain.timeline import FrameTimeline
from video_compare.media.color import display_policy_id, to_rgb8
from video_compare.media.validation import validate_video_frame


class DecodeError(RuntimeError):
    pass


class PreciseDecoder:
    """Owned by one worker/thread. Returns only an index-identified display frame."""

    def __init__(self, asset: AssetInfo, timeline: FrameTimeline) -> None:
        if timeline.asset_id != asset.asset_id:
            raise ValueError("索引与视频身份不一致")
        if asset.color_info.hdr_unsupported:
            raise DecodeError("该 HDR/BT.2020 编码尚无可信显示路径")
        self.asset = asset
        self.timeline = timeline
        self._container: av.InputContainer | None = None
        self._stream: av.VideoStream | None = None
        self._iterator: Iterator[av.VideoFrame] | None = None
        self._cursor_ordinal = -1
        self.last_method = "none"
        self._reformatter = VideoReformatter()
        pts_counts = Counter(entry.pts for entry in timeline.entries if entry.pts is not None)
        self._unique_pts = {
            entry.pts: entry.ordinal
            for entry in timeline.entries
            if entry.pts is not None and pts_counts[entry.pts] == 1
        }
        self._open()

    def _open(self) -> None:
        self._container = av.open(str(self.asset.path), mode="r")
        self._stream = self._container.streams[self.asset.stream_index]
        if self._stream.type != "video":
            self._container.close()
            raise DecodeError("探测的 stream index 不再指向视频流")
        self._iterator = iter(self._container.decode(self._stream))
        self._cursor_ordinal = -1

    def close(self) -> None:
        if self._container is not None:
            self._container.close()
        self._container = None
        self._stream = None
        self._iterator = None

    def __enter__(self) -> PreciseDecoder:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def frame_at(self, ordinal: int) -> DecodedFrame:
        if self._container is None or self._iterator is None:
            raise DecodeError("解码器已关闭")
        if not 0 <= ordinal < self.timeline.frame_count:
            raise DecodeError(f"目标帧越界：{ordinal + 1}")
        if ordinal > self._cursor_ordinal and ordinal - self._cursor_ordinal <= 12:
            frame = self._decode_forward(ordinal)
            if frame is not None:
                self.last_method = "forward"
                return frame
        # Seeking to an earlier keyframe is only a starting point. Decode until
        # the raw PTS matches the indexed target. This also handles B-frame reorder.
        anchors = [
            entry
            for entry in self.timeline.entries[: ordinal + 1]
            if entry.is_keyframe and entry.pts is not None
        ]
        for anchor in reversed(anchors):
            result = self._seek_and_decode(anchor.pts, ordinal)
            if result is not None:
                self.last_method = f"seek:{anchor.ordinal}"
                return result
        # Open GOP, repeated/missing PTS or a demuxer seek overshoot may make
        # local frame identity ambiguous. Reopening and counting from start is safe.
        self.close()
        self._open()
        result = self._decode_from_start(ordinal)
        if result is None:
            raise DecodeError(f"从文件开头解码仍找不到第 {ordinal + 1} 帧")
        self.last_method = "start-fallback"
        return result

    def _decode_forward(self, target: int) -> DecodedFrame | None:
        assert self._iterator is not None
        for frame in self._iterator:
            candidate = self._unique_pts.get(frame.pts)
            if candidate is None or candidate <= self._cursor_ordinal:
                return None
            self._cursor_ordinal = candidate
            if candidate == target:
                return self._convert(frame, target)
            if candidate > target:
                return None
        return None

    def _seek_and_decode(self, anchor_pts: int, target: int) -> DecodedFrame | None:
        assert self._container is not None and self._stream is not None
        try:
            self._container.seek(anchor_pts, backward=True, any_frame=False, stream=self._stream)
            self._iterator = iter(self._container.decode(self._stream))
            self._cursor_ordinal = -1
            for frame in self._iterator:
                candidate = self._unique_pts.get(frame.pts)
                if candidate is None:
                    return None
                self._cursor_ordinal = candidate
                if candidate == target:
                    return self._convert(frame, target)
                if candidate > target:
                    return None
        except av.error.FFmpegError as exc:
            raise DecodeError(f"seek/decode 失败：{exc}") from exc
        return None

    def _decode_from_start(self, target: int) -> DecodedFrame | None:
        assert self._iterator is not None
        for ordinal, frame in enumerate(self._iterator):
            self._cursor_ordinal = ordinal
            if ordinal == target:
                return self._convert(frame, target)
        return None

    def _convert(self, frame: av.VideoFrame, ordinal: int) -> DecodedFrame:
        try:
            validate_video_frame(frame, self.asset)
        except ValueError as exc:
            raise DecodeError(str(exc)) from exc
        expected = self.timeline.entries[ordinal]
        if frame.pts != expected.pts or Fraction(frame.time_base) != expected.time_base:
            raise DecodeError(
                f"帧身份不符：目标 {ordinal + 1} PTS={expected.pts}，实际 PTS={frame.pts}"
            )
        rgb = to_rgb8(frame, self.asset.color_info, self._reformatter)
        local_time = self.timeline.local_time_at(ordinal)
        return DecodedFrame(
            asset_id=self.asset.asset_id,
            ordinal=ordinal,
            pts=frame.pts,
            time_base=expected.time_base,
            local_time=local_time,
            rgb=rgb,
            timing_quality=expected.timing_quality,
            color_policy_id=display_policy_id(self.asset.color_info),
        )
