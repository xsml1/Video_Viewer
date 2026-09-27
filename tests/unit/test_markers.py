from __future__ import annotations

from fractions import Fraction

import numpy as np

from video_compare.domain.models import (
    DecodedFrame,
    FrameGroupSnapshot,
    FrameIndexEntry,
    SyncMode,
    TimelineSpec,
)
from video_compare.domain.timeline import FrameTimeline, TimelineMapper
from video_compare.services.markers import MarkerStore


def _timeline(asset_id: str) -> FrameTimeline:
    entries = tuple(FrameIndexEntry(i, i, 1, 30, 1, i == 0) for i in range(30))
    return FrameTimeline(asset_id, entries, Fraction(1))


def _frame(asset_id: str, ordinal: int) -> DecodedFrame:
    return DecodedFrame(
        asset_id,
        ordinal,
        ordinal,
        Fraction(1, 30),
        Fraction(ordinal, 30),
        np.zeros((2, 2, 3), dtype=np.uint8),
    )


def test_marker_rebases_requested_time_and_frame_content() -> None:
    mapper = TimelineMapper({"a": _timeline("a"), "b": _timeline("b")})
    snapshot = FrameGroupSnapshot(
        (1, 2, 3),
        Fraction(1, 5),
        6,
        {"a": _frame("a", 6), "b": _frame("b", 9)},
    )
    store = MarkerStore()
    time_spec = TimelineSpec(
        SyncMode.TIME, "a", ("a", "b"), time_offsets={"a": 0, "b": Fraction(1, 10)}
    )
    marker = store.add(snapshot, time_spec, title="对齐点", note="复核")
    assert marker.title == "对齐点" and marker.note == "复核"
    assert marker.requested_local_times["b"] == Fraction(3, 10)
    rebased = mapper.rebase_reference(time_spec, "b")
    target = store.resolve(marker.marker_id, rebased, mapper)
    assert target.global_time == Fraction(3, 10)
    assert {key: item.ordinal for key, item in target.targets.items()} == {"a": 6, "b": 9}

    frame_spec = TimelineSpec(SyncMode.FRAME, "a", ("a", "b"), frame_offsets={"a": 0, "b": 3})
    frame_marker = store.add(snapshot, frame_spec, title="")
    frame_rebased = mapper.rebase_reference(frame_spec, "b")
    frame_target = store.resolve(frame_marker.marker_id, frame_rebased, mapper)
    assert frame_marker.title == "帧 7"
    assert frame_target.reference_ordinal == 9
    assert {key: item.ordinal for key, item in frame_target.targets.items()} == {
        "a": 6,
        "b": 9,
    }
