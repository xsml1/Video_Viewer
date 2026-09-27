from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import numpy as np
from numpy.typing import NDArray


class SyncMode(StrEnum):
    TIME = "time"
    FRAME = "frame"


class IndexState(StrEnum):
    UNKNOWN = "unknown"
    BUILDING = "building"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


class LookupStatus(StrEnum):
    HIT = "hit"
    NEEDS_INDEX = "needs_index"
    OUT_OF_RANGE = "out_of_range"
    INVALID_TIMING = "invalid_timing"


class TransportState(StrEnum):
    EMPTY = "empty"
    LOADING = "loading"
    PAUSED = "paused"
    PLAYING = "playing"
    SEEKING = "seeking"
    SCRUBBING = "scrubbing"
    BUFFERING = "buffering"
    ENDED = "ended"
    CLOSING = "closing"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DisplayTransform:
    rotation_degrees: Literal[0, 90, 180, 270] = 0
    mirror_horizontal: bool = False
    mirror_vertical: bool = False
    sample_aspect_ratio: Fraction = Fraction(1, 1)


@dataclass(frozen=True, slots=True)
class ColorInfo:
    matrix: str | None = None
    range: str | None = None
    primaries: str | None = None
    transfer: str | None = None
    pixel_format: str | None = None
    bit_depth: int | None = None
    inferred: bool = False
    hdr_unsupported: bool = False


@dataclass(frozen=True, slots=True)
class AssetInfo:
    asset_id: str
    path: Path
    fingerprint: str
    stream_index: int
    coded_width: int
    coded_height: int
    time_base: Fraction
    display_transform: DisplayTransform = DisplayTransform()
    color_info: ColorInfo = ColorInfo()
    codec_name: str | None = None
    average_rate: Fraction | None = None
    duration_hint: Fraction | None = None
    alias: str | None = None
    media_kind: Literal["video", "image"] = "video"

    @property
    def label(self) -> str:
        return self.alias or self.path.name


@dataclass(frozen=True, slots=True)
class FrameIndexEntry:
    ordinal: int
    pts: int | None
    time_base_num: int
    time_base_den: int
    duration_ticks: int | None
    is_keyframe: bool
    pts_occurrence: int = 0
    timing_quality: str = "actual"

    @property
    def time_base(self) -> Fraction:
        return Fraction(self.time_base_num, self.time_base_den)

    @property
    def source_time(self) -> Fraction | None:
        return None if self.pts is None else self.pts * self.time_base


@dataclass(frozen=True, slots=True)
class TimelineSpec:
    mode: SyncMode
    reference_id: str
    participants: tuple[str, ...]
    time_offsets: Mapping[str, Fraction] = field(default_factory=dict)
    frame_offsets: Mapping[str, int] = field(default_factory=dict)
    end_policy: Literal["intersection"] = "intersection"

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", SyncMode(self.mode))
        if self.reference_id not in self.participants:
            raise ValueError("基准视频必须参与时间轴")
        if len(set(self.participants)) != len(self.participants):
            raise ValueError("参与视频不能重复")
        time_offsets = {
            asset_id: Fraction(self.time_offsets.get(asset_id, 0)) for asset_id in self.participants
        }
        frame_offsets = {
            asset_id: int(self.frame_offsets.get(asset_id, 0)) for asset_id in self.participants
        }
        if time_offsets[self.reference_id] != 0 or frame_offsets[self.reference_id] != 0:
            raise ValueError("基准视频 Offset 必须为 0")
        object.__setattr__(self, "time_offsets", MappingProxyType(time_offsets))
        object.__setattr__(self, "frame_offsets", MappingProxyType(frame_offsets))


@dataclass(frozen=True, slots=True)
class FrameRequest:
    session_epoch: int
    generation: int
    request_seq: int
    asset_id: str
    target_ordinal: int | None = None
    target_local_time: Fraction | None = None
    purpose: Literal["present", "scrub", "prefetch", "snapshot"] = "present"

    def __post_init__(self) -> None:
        if (self.target_ordinal is None) == (self.target_local_time is None):
            raise ValueError("帧请求必须且只能指定 ordinal 或 local_time")

    @property
    def group_id(self) -> tuple[int, int, int]:
        return self.session_epoch, self.generation, self.request_seq


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    asset_id: str
    ordinal: int
    pts: int | None
    time_base: Fraction
    local_time: Fraction
    rgb: NDArray[np.uint8]
    color_policy_id: str = "sdr-rgb8"
    timing_quality: str = "actual"

    def __post_init__(self) -> None:
        if self.rgb.dtype != np.uint8 or self.rgb.ndim != 3 or self.rgb.shape[2] != 3:
            raise ValueError("rgb 必须是 H×W×3 uint8 数组")
        self.rgb.setflags(write=False)


@dataclass(frozen=True, slots=True)
class FrameGroupSnapshot:
    group_id: tuple[int, int, int]
    requested_global_time: Fraction
    reference_ordinal: int | None
    frames: Mapping[str, DecodedFrame]
    boundary_states: Mapping[str, str] = field(default_factory=dict)
    mapping_revision: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", MappingProxyType(dict(self.frames)))
        object.__setattr__(self, "boundary_states", MappingProxyType(dict(self.boundary_states)))


@dataclass(frozen=True, slots=True)
class TimelineRange:
    start: Fraction | int
    end: Fraction | int
    end_inclusive: bool

    @property
    def empty(self) -> bool:
        return self.end < self.start if self.end_inclusive else self.end <= self.start


@dataclass(frozen=True, slots=True)
class LoopRange:
    mode: SyncMode
    start: Fraction | int
    end: Fraction | int

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("循环区间必须至少包含一个位置")


@dataclass(frozen=True, slots=True)
class TargetFrame:
    asset_id: str
    ordinal: int
    local_time: Fraction


@dataclass(frozen=True, slots=True)
class GroupTargets:
    global_time: Fraction
    reference_ordinal: int
    targets: Mapping[str, TargetFrame]

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", MappingProxyType(dict(self.targets)))


@dataclass(frozen=True, slots=True)
class IndexLookup:
    status: LookupStatus
    entry: FrameIndexEntry | None = None
    reason: str | None = None
