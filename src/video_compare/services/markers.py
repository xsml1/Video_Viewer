from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from uuid import uuid4

from video_compare.domain.models import FrameGroupSnapshot, GroupTargets, SyncMode, TimelineSpec
from video_compare.domain.timeline import TimelineMapper


@dataclass(frozen=True, slots=True)
class Marker:
    marker_id: str
    title: str
    note: str
    mode: SyncMode
    global_time: Fraction
    reference_ordinal: int
    reference_id: str
    ordinals: Mapping[str, int]
    requested_local_times: Mapping[str, Fraction]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ordinals", MappingProxyType(dict(self.ordinals)))
        object.__setattr__(
            self, "requested_local_times", MappingProxyType(dict(self.requested_local_times))
        )


class MarkerStore:
    """Session-only markers anchored to the actually committed frame group."""

    def __init__(self) -> None:
        self._markers: dict[str, Marker] = {}

    @property
    def markers(self) -> tuple[Marker, ...]:
        return tuple(self._markers.values())

    def get(self, marker_id: str) -> Marker:
        return self._markers[marker_id]

    def add(
        self, snapshot: FrameGroupSnapshot, spec: TimelineSpec, *, title: str, note: str = ""
    ) -> Marker:
        if set(snapshot.frames) != set(spec.participants):
            raise ValueError("Marker 必须来自当前完整参与帧组")
        local_times = {
            asset_id: (
                snapshot.requested_global_time + spec.time_offsets[asset_id]
                if spec.mode is SyncMode.TIME
                else frame.local_time
            )
            for asset_id, frame in snapshot.frames.items()
        }
        marker = Marker(
            marker_id=uuid4().hex,
            title=title.strip() or f"帧 {snapshot.reference_ordinal + 1}",
            note=note.strip(),
            mode=spec.mode,
            global_time=snapshot.requested_global_time,
            reference_ordinal=snapshot.reference_ordinal,
            reference_id=spec.reference_id,
            ordinals={asset_id: frame.ordinal for asset_id, frame in snapshot.frames.items()},
            requested_local_times=local_times,
        )
        self._markers[marker.marker_id] = marker
        return marker

    def resolve(self, marker_id: str, spec: TimelineSpec, mapper: TimelineMapper) -> GroupTargets:
        marker = self.get(marker_id)
        reference_id = spec.reference_id
        if reference_id not in marker.ordinals:
            raise ValueError("Marker 不包含当前基准视频；可能已替换该路")
        if spec.mode is SyncMode.TIME:
            local_time = marker.requested_local_times[reference_id]
            return mapper.map_time(local_time - spec.time_offsets[reference_id], spec)
        ordinal = marker.ordinals[reference_id] - spec.frame_offsets[reference_id]
        return mapper.map_frame(ordinal, spec)
