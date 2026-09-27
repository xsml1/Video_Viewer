from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction

from video_compare.domain.models import (
    FrameIndexEntry,
    GroupTargets,
    SyncMode,
    TargetFrame,
    TimelineRange,
    TimelineSpec,
)


class TimelineError(ValueError):
    """A requested position cannot be represented by the current timeline."""


@dataclass(frozen=True, slots=True)
class FrameTimeline:
    asset_id: str
    entries: tuple[FrameIndexEntry, ...]
    end_time: Fraction
    provisional: bool = False
    _local_times: tuple[Fraction, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("时间轴至少需要一帧")
        if tuple(entry.ordinal for entry in self.entries) != tuple(range(len(self.entries))):
            raise ValueError("FrameIndexEntry ordinal 必须从 0 连续递增")
        source_times = tuple(entry.source_time for entry in self.entries)
        if any(value is None for value in source_times):
            raise ValueError("精确时间轴不接受缺失 PTS")
        origin = source_times[0]
        assert origin is not None
        local_times = tuple(value - origin for value in source_times if value is not None)
        if any(right < left for left, right in zip(local_times, local_times[1:], strict=False)):
            raise ValueError("PTS 下降，无法建立精确时间轴")
        if self.end_time <= local_times[-1]:
            raise ValueError("end_time 必须晚于最后一帧开始时间")
        object.__setattr__(self, "_local_times", local_times)

    @property
    def local_times(self) -> tuple[Fraction, ...]:
        return self._local_times

    @property
    def frame_count(self) -> int:
        return len(self.entries)

    def local_time_at(self, ordinal: int) -> Fraction:
        if not 0 <= ordinal < self.frame_count:
            raise TimelineError(f"帧号超出范围：{ordinal + 1}")
        return self.local_times[ordinal]

    def ordinal_at(self, local_time: Fraction) -> int:
        if local_time < 0 or local_time >= self.end_time:
            raise TimelineError(f"时间超出范围：{float(local_time):.6f}s")
        # bisect_right makes repeated PTS select the last display-order frame.
        return bisect_right(self.local_times, local_time) - 1


class TimelineMapper:
    def __init__(self, timelines: Mapping[str, FrameTimeline]) -> None:
        self._timelines = dict(timelines)

    def valid_range(self, spec: TimelineSpec) -> TimelineRange:
        self._require_timelines(spec)
        if spec.mode is SyncMode.TIME:
            start = max(-spec.time_offsets[asset_id] for asset_id in spec.participants)
            end = min(
                self._timelines[asset_id].end_time - spec.time_offsets[asset_id]
                for asset_id in spec.participants
            )
            return TimelineRange(start=start, end=end, end_inclusive=False)
        start = max(-spec.frame_offsets[asset_id] for asset_id in spec.participants)
        end = min(
            self._timelines[asset_id].frame_count - 1 - spec.frame_offsets[asset_id]
            for asset_id in spec.participants
        )
        return TimelineRange(start=start, end=end, end_inclusive=True)

    def map_time(self, global_time: Fraction, spec: TimelineSpec) -> GroupTargets:
        if spec.mode is not SyncMode.TIME:
            raise TimelineError("当前不是时间同步模式")
        valid = self.valid_range(spec)
        if global_time < valid.start or global_time >= valid.end:
            raise TimelineError(f"全局时间不在公共范围 [{valid.start}, {valid.end})")
        targets: dict[str, TargetFrame] = {}
        for asset_id in spec.participants:
            local_time = global_time + spec.time_offsets[asset_id]
            ordinal = self._timelines[asset_id].ordinal_at(local_time)
            targets[asset_id] = TargetFrame(asset_id, ordinal, local_time)
        reference_ordinal = targets[spec.reference_id].ordinal
        return GroupTargets(global_time, reference_ordinal, targets)

    def map_frame(self, reference_ordinal: int, spec: TimelineSpec) -> GroupTargets:
        if spec.mode is not SyncMode.FRAME:
            raise TimelineError("当前不是帧号同步模式")
        valid = self.valid_range(spec)
        if reference_ordinal < valid.start or reference_ordinal > valid.end:
            raise TimelineError(f"基准帧不在公共范围 [{valid.start + 1}, {valid.end + 1}]")
        reference = self._timelines[spec.reference_id]
        global_time = reference.local_time_at(reference_ordinal)
        targets: dict[str, TargetFrame] = {}
        for asset_id in spec.participants:
            ordinal = reference_ordinal + spec.frame_offsets[asset_id]
            local_time = self._timelines[asset_id].local_time_at(ordinal)
            targets[asset_id] = TargetFrame(asset_id, ordinal, local_time)
        return GroupTargets(global_time, reference_ordinal, targets)

    def map_reference_frame(self, ui_frame_number: int, spec: TimelineSpec) -> GroupTargets:
        if ui_frame_number < 1:
            raise TimelineError("界面帧号从 1 开始")
        ordinal = ui_frame_number - 1
        if spec.mode is SyncMode.FRAME:
            return self.map_frame(ordinal, spec)
        reference_time = self._timelines[spec.reference_id].local_time_at(ordinal)
        return self.map_time(reference_time, spec)

    def next_event(self, committed: GroupTargets, spec: TimelineSpec) -> GroupTargets | None:
        valid = self.valid_range(spec)
        if spec.mode is SyncMode.FRAME:
            next_ordinal = committed.reference_ordinal + 1
            return self.map_frame(next_ordinal, spec) if next_ordinal <= valid.end else None
        current = committed.global_time
        candidates: list[Fraction] = []
        for asset_id in spec.participants:
            offset = spec.time_offsets[asset_id]
            times = self._timelines[asset_id].local_times
            next_index = bisect_right(times, current + offset)
            if next_index < len(times):
                event = times[next_index] - offset
                if event < valid.end:
                    candidates.append(event)
        return self.map_time(min(candidates), spec) if candidates else None

    def last_event(self, spec: TimelineSpec) -> GroupTargets:
        valid = self.valid_range(spec)
        if valid.empty:
            raise TimelineError("参与视频无公共有效范围")
        if spec.mode is SyncMode.FRAME:
            return self.map_frame(int(valid.end), spec)
        events = [valid.start]
        for asset_id in spec.participants:
            offset = spec.time_offsets[asset_id]
            times = self._timelines[asset_id].local_times
            index = bisect_left(times, valid.end + offset) - 1
            if index >= 0:
                event = times[index] - offset
                if event >= valid.start:
                    events.append(event)
        return self.map_time(max(events), spec)

    def rebase_reference(self, spec: TimelineSpec, new_reference_id: str) -> TimelineSpec:
        if new_reference_id not in spec.participants:
            raise TimelineError("新基准必须是参与视频")
        time_shift = spec.time_offsets[new_reference_id]
        frame_shift = spec.frame_offsets[new_reference_id]
        return TimelineSpec(
            mode=spec.mode,
            reference_id=new_reference_id,
            participants=spec.participants,
            time_offsets={key: value - time_shift for key, value in spec.time_offsets.items()},
            frame_offsets={key: value - frame_shift for key, value in spec.frame_offsets.items()},
        )

    def _require_timelines(self, spec: TimelineSpec) -> None:
        missing = set(spec.participants).difference(self._timelines)
        if missing:
            raise TimelineError(f"缺少时间轴：{', '.join(sorted(missing))}")


def parse_timecode(value: str) -> Fraction:
    text = value.strip()
    if not text:
        raise TimelineError("时间不能为空")
    parts = text.split(":")
    if len(parts) > 3:
        raise TimelineError("时间格式应为 SS、MM:SS 或 HH:MM:SS")
    try:
        seconds = Fraction(parts[-1])
        minutes = int(parts[-2]) if len(parts) >= 2 else 0
        hours = int(parts[-3]) if len(parts) == 3 else 0
    except (ValueError, ZeroDivisionError) as exc:
        raise TimelineError("时间格式无效") from exc
    if (
        seconds < 0
        or (seconds >= 60 and len(parts) > 1)
        or minutes < 0
        or (minutes >= 60 and len(parts) == 3)
        or hours < 0
    ):
        raise TimelineError("时间数值超出格式范围")
    return Fraction(hours * 3600 + minutes * 60) + seconds


def format_timecode(value: Fraction) -> str:
    if value < 0:
        sign = "-"
        value = -value
    else:
        sign = ""
    total_ms = round(value * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
