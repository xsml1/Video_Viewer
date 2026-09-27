from fractions import Fraction

import pytest

from video_compare.domain.models import FrameIndexEntry, SyncMode, TimelineSpec
from video_compare.domain.timeline import (
    FrameTimeline,
    TimelineError,
    TimelineMapper,
    parse_timecode,
)


def timeline(asset_id: str, fps: int, count: int) -> FrameTimeline:
    entries = tuple(FrameIndexEntry(k, k, 1, fps, 1, k == 0) for k in range(count))
    return FrameTimeline(asset_id, entries, Fraction(count, fps))


def test_time_mode_uses_pts_floor_for_different_fps() -> None:
    mapper = TimelineMapper({"30": timeline("30", 30, 30), "24": timeline("24", 24, 24)})
    spec = TimelineSpec(SyncMode.TIME, "30", ("30", "24"))
    result = mapper.map_time(Fraction(1, 10), spec)
    assert result.targets["30"].ordinal == 3
    assert result.targets["24"].ordinal == 2


def test_frame_mode_uses_ordinal_and_offset() -> None:
    mapper = TimelineMapper({"a": timeline("a", 24, 10), "b": timeline("b", 60, 12)})
    spec = TimelineSpec(
        SyncMode.FRAME,
        "a",
        ("a", "b"),
        frame_offsets={"a": 0, "b": 2},
    )
    result = mapper.map_frame(4, spec)
    assert result.targets["a"].ordinal == 4
    assert result.targets["b"].ordinal == 6
    assert result.global_time == Fraction(1, 6)


def test_repeated_pts_selects_last_display_frame() -> None:
    entries = (
        FrameIndexEntry(0, 100, 1, 1000, 1, True, 0),
        FrameIndexEntry(1, 100, 1, 1000, 1, False, 1),
        FrameIndexEntry(2, 140, 1, 1000, 1, False, 0),
    )
    item = FrameTimeline("vfr", entries, Fraction(80, 1000))
    assert item.ordinal_at(Fraction(0)) == 1


def test_offsets_define_public_half_open_time_range() -> None:
    mapper = TimelineMapper({"a": timeline("a", 10, 10), "b": timeline("b", 10, 8)})
    spec = TimelineSpec(
        SyncMode.TIME,
        "a",
        ("a", "b"),
        time_offsets={"a": 0, "b": Fraction(1, 5)},
    )
    valid = mapper.valid_range(spec)
    assert valid.start == 0
    assert valid.end == Fraction(3, 5)
    with pytest.raises(TimelineError):
        mapper.map_time(valid.end, spec)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1.250", Fraction(5, 4)), ("01:02.5", Fraction(125, 2)), ("1:02:03.125", Fraction(29785, 8))],
)
def test_parse_timecode(text: str, expected: Fraction) -> None:
    assert parse_timecode(text) == expected


@pytest.mark.parametrize("text", ["", "-1", "NaN", "1:60", "1:2:60", "1:2:3:4"])
def test_parse_timecode_rejects_invalid_values(text: str) -> None:
    with pytest.raises((TimelineError, ValueError)):
        parse_timecode(text)
