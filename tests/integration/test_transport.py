from __future__ import annotations

import statistics
import time
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from video_compare.controllers.transport import TransportController
from video_compare.domain.models import SyncMode, TimelineSpec, TransportState
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video


@pytest.mark.integration
def test_two_real_decoders_commit_atomic_groups_and_latest_step(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    assert ffprobe.is_file()
    paths = [root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"]
    assets = [probe_video(path, ffprobe_path=ffprobe, asset_id=uuid4().hex) for path in paths]
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    spec = TimelineSpec(
        SyncMode.TIME, assets[0].asset_id, tuple(asset.asset_id for asset in assets)
    )
    controller = TransportController(
        {asset.asset_id: asset for asset in assets},
        timelines,
        spec,
        cache_bytes=8 * 1024 * 1024,
    )
    try:
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_time(Fraction(0))
        assert controller.displayed is not None
        assert {frame.ordinal for frame in controller.displayed.frames.values()} == {0}
        assert controller.state is TransportState.PAUSED

        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.step(1, Fraction(1), "frame")
            controller.step(1, Fraction(1), "frame")
            controller.step(1, Fraction(1), "frame")
        assert controller.displayed.reference_ordinal == 3
        assert {frame.ordinal for frame in controller.displayed.frames.values()} == {3}

        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_time(Fraction(1, 10))
        assert controller.displayed.requested_global_time == Fraction(1, 10)
        assert {frame.ordinal for frame in controller.displayed.frames.values()} == {3}

        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.play()
        controller.pause()
        assert controller.state is TransportState.PAUSED
        assert len(controller.displayed.frames) == 2
        assert controller.cache.used_bytes <= controller.cache.budget_bytes
    finally:
        assert controller.close()


@pytest.mark.integration
def test_prefetched_strict_playback_keeps_consecutive_complete_groups(
    qtbot, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    assets = [
        probe_video(root / name, ffprobe_path=ffprobe)
        for name in ("f05_h264_bframes.mp4", "f05_ffv1_oracle.mkv")
    ]
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    spec = TimelineSpec(
        SyncMode.TIME, assets[0].asset_id, tuple(asset.asset_id for asset in assets)
    )
    controller = TransportController(
        {asset.asset_id: asset for asset in assets}, timelines, spec, cache_bytes=8 * 1024 * 1024
    )
    try:
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_time(Fraction(0))
        events = []
        controller.group_ready.connect(events.append)
        controller.play()
        qtbot.waitUntil(lambda: len(events) >= 8, timeout=5000)
        controller.pause()
        end = min(item.end_time for item in timelines.values())
        expected_times = sorted(
            {time for item in timelines.values() for time in item.local_times if 0 < time < end}
        )
        assert [group.requested_global_time for group in events] == expected_times[: len(events)]
        assert all(set(group.frames) == set(timelines) for group in events)
        assert controller.state is TransportState.PAUSED
        assert controller.cache.item_count >= 4
        assert controller.cache.used_bytes <= controller.cache.budget_bytes
    finally:
        assert controller.close()


@pytest.mark.integration
def test_six_real_routes_play_pause_with_identical_source_frame_ids(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    paths = [root / "f05_h264_bframes.mp4"] * 6
    assets = [probe_video(path, ffprobe_path=ffprobe, asset_id=uuid4().hex) for path in paths]
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    spec = TimelineSpec(SyncMode.TIME, assets[0].asset_id, tuple(timelines))
    controller = TransportController(
        {asset.asset_id: asset for asset in assets}, timelines, spec, cache_bytes=64 * 1024 * 1024
    )
    groups = []
    controller.group_ready.connect(groups.append)
    try:
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_time(Fraction(0))
        controller.play()
        qtbot.waitUntil(lambda: len(groups) >= 16, timeout=10000)
        controller.pause()
        count_at_pause = len(groups)
        qtbot.wait(100)
        assert len(groups) == count_at_pause
        assert all(len(group.frames) == 6 for group in groups)
        assert all(
            {frame.ordinal for frame in group.frames.values()} == {group.reference_ordinal}
            for group in groups
        )
        assert [group.reference_ordinal for group in groups] == list(range(len(groups)))
        assert controller.cache.used_bytes <= controller.cache.budget_bytes
    finally:
        assert controller.close()


@pytest.mark.integration
def test_six_1080p_routes_fit_small_cache_without_overwriting_display(
    qtbot, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    video = root / "f06_1080p_h264.mp4"
    assets = [probe_video(video, ffprobe_path=ffprobe, asset_id=uuid4().hex) for _ in range(6)]
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    spec = TimelineSpec(SyncMode.TIME, assets[0].asset_id, tuple(timelines))
    controller = TransportController(
        {asset.asset_id: asset for asset in assets}, timelines, spec, cache_bytes=64 * 1024 * 1024
    )
    try:
        with qtbot.waitSignal(controller.group_ready, timeout=10000):
            controller.seek_reference_frame(1)
        first = controller.displayed
        assert first is not None
        first_pixels = first.frames[assets[0].asset_id].rgb.copy()
        with qtbot.waitSignal(controller.group_ready, timeout=10000):
            controller.seek_reference_frame(120)
        assert controller.state is TransportState.PAUSED
        assert len(controller.displayed.frames) == 6
        assert controller.cache.used_bytes <= controller.cache.budget_bytes
        assert np.array_equal(first.frames[assets[0].asset_id].rgb, first_pixels)
    finally:
        assert controller.close()


@pytest.mark.integration
def test_two_route_loop_repeats_last_included_frame_without_flashing_outside(
    qtbot, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    assets = [
        probe_video(root / name, ffprobe_path=ffprobe)
        for name in ("f05_h264_bframes.mp4", "f05_ffv1_oracle.mkv")
    ]
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    spec = TimelineSpec(
        SyncMode.TIME, assets[0].asset_id, tuple(asset.asset_id for asset in assets)
    )
    controller = TransportController(
        {asset.asset_id: asset for asset in assets}, timelines, spec, cache_bytes=8 * 1024 * 1024
    )
    try:
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_time(Fraction(0))
        assert controller.set_loop_start_from_displayed() == 0
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_reference_frame(2)
        loop = controller.set_loop_end_from_displayed()
        assert loop.end == Fraction(1, 15)
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_reference_frame(1)
        controller.set_speed(Fraction(4))
        controller.set_loop_enabled(True)
        events = []
        controller.group_ready.connect(
            lambda group: events.append(
                (
                    group.requested_global_time,
                    tuple(frame.ordinal for frame in group.frames.values()),
                )
            )
        )
        controller.play()
        qtbot.waitUntil(lambda: sum(time == 0 for time, _ in events) >= 100, timeout=20000)
        controller.pause()
        assert all(0 <= time < loop.end for time, _ in events)
        assert all(len(ordinals) == 2 for _, ordinals in events)
        assert all(ordinals[0] <= 1 for _, ordinals in events)
        assert controller.state is TransportState.PAUSED
        after_seek: list[int] = []
        controller.group_ready.connect(lambda group: after_seek.append(group.reference_ordinal))
        with qtbot.waitSignal(controller.group_ready, timeout=5000):
            controller.seek_reference_frame(50)
            controller.set_loop_enabled(True)
        qtbot.wait(50)
        assert after_seek == [0]
    finally:
        assert controller.close()


@pytest.mark.integration
@pytest.mark.parametrize("mode", [SyncMode.TIME, SyncMode.FRAME])
def test_real_two_route_playback_rates_follow_pts_intervals(
    qtbot, tmp_path: Path, mode: SyncMode
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    assets = [
        probe_video(root / "f05_h264_bframes.mp4", ffprobe_path=ffprobe, asset_id=uuid4().hex)
        for _ in range(2)
    ]
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    spec = TimelineSpec(mode, assets[0].asset_id, tuple(asset.asset_id for asset in assets))
    controller = TransportController(
        {asset.asset_id: asset for asset in assets}, timelines, spec, cache_bytes=8 * 1024 * 1024
    )
    try:
        medians: dict[Fraction, float] = {}
        for speed in (Fraction(1, 4), Fraction(2)):
            with qtbot.waitSignal(controller.group_ready, timeout=5000):
                controller.seek_reference_frame(1)
            controller.set_speed(speed)
            commits: list[tuple[float, int]] = []

            def record(group, sink=commits) -> None:
                sink.append((time.monotonic(), group.reference_ordinal))

            controller.group_ready.connect(record)
            controller.play()
            qtbot.waitUntil(lambda sink=commits: len(sink) >= 5, timeout=6000)
            controller.pause()
            controller.group_ready.disconnect(record)
            assert [ordinal for _, ordinal in commits[:5]] == [1, 2, 3, 4, 5]
            medians[speed] = statistics.median(
                commits[index + 1][0] - commits[index][0] for index in range(4)
            )
        # Source PTS spacing is 1/30 s: expected 133 ms at 0.25x and 17 ms at 2x.
        # The generous bounds allow decode and timer jitter but detect a dead speed control.
        assert 0.08 <= medians[Fraction(1, 4)] <= 0.35
        assert 0.008 <= medians[Fraction(2)] <= 0.12
        assert medians[Fraction(1, 4)] > medians[Fraction(2)] * 3
    finally:
        assert controller.close()
