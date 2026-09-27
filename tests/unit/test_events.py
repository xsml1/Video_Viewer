from fractions import Fraction

from video_compare.domain.models import FrameIndexEntry, SyncMode, TimelineSpec
from video_compare.domain.timeline import FrameTimeline, TimelineMapper


def make(asset_id: str, fps: int, count: int) -> FrameTimeline:
    entries = tuple(FrameIndexEntry(k, k, 1, fps, 1, k == 0) for k in range(count))
    return FrameTimeline(asset_id, entries, Fraction(count, fps))


def test_time_mode_uses_union_of_all_participant_pts() -> None:
    mapper = TimelineMapper({"24": make("24", 24, 24), "60": make("60", 60, 60)})
    spec = TimelineSpec(SyncMode.TIME, "24", ("24", "60"))
    event = mapper.map_time(Fraction(0), spec)
    event = mapper.next_event(event, spec)
    assert event is not None
    assert event.global_time == Fraction(1, 60)
    assert event.targets["24"].ordinal == 0
    assert event.targets["60"].ordinal == 1
    event = mapper.next_event(event, spec)
    assert event is not None and event.global_time == Fraction(1, 30)


def test_frame_mode_advances_one_reference_ordinal() -> None:
    mapper = TimelineMapper({"24": make("24", 24, 3), "60": make("60", 60, 3)})
    spec = TimelineSpec(SyncMode.FRAME, "24", ("24", "60"))
    event = mapper.map_frame(0, spec)
    assert mapper.next_event(event, spec).reference_ordinal == 1
    assert mapper.next_event(mapper.last_event(spec), spec) is None
