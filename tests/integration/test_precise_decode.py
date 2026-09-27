from __future__ import annotations

import os
import random
import shutil
import subprocess
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from queue import Empty, Queue

import av
import numpy as np
import pytest

from video_compare.domain.models import FrameRequest, IndexState, LookupStatus
from video_compare.media.cache import FrameCache
from video_compare.media.decoder import PreciseDecoder
from video_compare.media.index import FrameIndexRepository, IndexCancelled
from video_compare.media.probe import probe_video
from video_compare.media.workers import DecoderWorker, WorkerResult


def _binary(name: str) -> Path:
    configured = os.environ.get(f"VIDEO_COMPARE_{name.upper()}")
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
    local = Path(__file__).resolve().parents[2] / ".codex-tools" / "ffmpeg"
    for candidate in local.glob(f"*/bin/{name}.exe"):
        return candidate
    found = shutil.which(name)
    if found:
        return Path(found)
    pytest.fail(f"缺少 {name}，无法执行真实媒体集成测试")


@pytest.fixture(scope="session")
def media_dir() -> Path:
    output = Path(__file__).resolve().parents[1] / "assets" / "generated"
    command = [
        str(Path(os.environ.get("VIRTUAL_ENV", ".venv")) / "Scripts" / "python.exe"),
        str(Path(__file__).resolve().parents[2] / "tools" / "generate_fixtures.py"),
        "--output",
        str(output),
        "--ffmpeg",
        str(_binary("ffmpeg")),
    ]
    if not (output / "f11_中文 空格 [样例].mp4").is_file():
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            pytest.fail(f"生成真实测试素材失败：{result.stderr}")
    return output


def marker_id(rgb: np.ndarray) -> int:
    result = 0
    for bit in range(16):
        row, col = divmod(bit, 8)
        if int(rgb[13 + row * 14, 13 + col * 14, 0]) >= 128:
            result |= 1 << bit
    return result


@pytest.mark.integration
@pytest.mark.parametrize(
    "filename",
    [
        "f05_h264_bframes.mp4",
        "f05_ffv1_oracle.mkv",
        "f04_vfr.mkv",
        "f10_nonzero_start.mkv",
        "f11_中文 空格 [样例].mp4",
    ],
)
def test_random_seek_and_reverse_are_exact(media_dir: Path, tmp_path: Path, filename: str) -> None:
    asset = probe_video(media_dir / filename, ffprobe_path=_binary("ffprobe"))
    repository = FrameIndexRepository(tmp_path / "frame-index.sqlite3")
    timeline = repository.build(asset, chunk_size=11)
    assert timeline.frame_count == 72
    assert repository.load(asset).entries == timeline.entries
    rng = random.Random(20260923)
    targets = [0, 1, 47, 48, 71, 70, 49, 0] + [rng.randrange(72) for _ in range(100)]
    with PreciseDecoder(asset, timeline) as decoder:
        for target in targets:
            frame = decoder.frame_at(target)
            assert frame.ordinal == target
            assert frame.pts == timeline.entries[target].pts
            assert marker_id(frame.rgb) == target
            assert not frame.rgb.flags.writeable


@pytest.mark.integration
def test_h264_fixture_has_b_frames_and_ffprobe_pts(media_dir: Path, tmp_path: Path) -> None:
    source = media_dir / "f05_h264_bframes.mp4"
    with av.open(str(source)) as container:
        frames = list(container.decode(container.streams.video[0]))
    assert any(str(frame.pict_type) == "3" for frame in frames)
    result = subprocess.run(
        [
            str(_binary("ffprobe")),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=pts",
            "-of",
            "csv=p=0",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    independent_pts = [
        int(line.split(",", 1)[0]) for line in result.stdout.splitlines() if line.strip()
    ]
    asset = probe_video(source, ffprobe_path=_binary("ffprobe"))
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(asset)
    assert [entry.pts for entry in timeline.entries] == independent_pts


@pytest.mark.integration
def test_vfr_and_nonzero_origin_use_actual_pts(media_dir: Path, tmp_path: Path) -> None:
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    vfr = probe_video(media_dir / "f04_vfr.mkv", ffprobe_path=_binary("ffprobe"))
    shifted = probe_video(media_dir / "f10_nonzero_start.mkv", ffprobe_path=_binary("ffprobe"))
    vfr_timeline = repository.build(vfr)
    shifted_timeline = repository.build(shifted)
    intervals = [
        b - a for a, b in zip(vfr_timeline.local_times, vfr_timeline.local_times[1:], strict=False)
    ]
    assert len(set(intervals)) > 1
    assert shifted_timeline.entries[0].pts == 2000
    assert shifted_timeline.local_times[0] == 0
    assert shifted_timeline.ordinal_at(shifted_timeline.local_times[27]) == 27


@pytest.mark.integration
def test_partial_index_is_not_mistaken_for_end_of_file(media_dir: Path, tmp_path: Path) -> None:
    asset = probe_video(media_dir / "f05_h264_bframes.mp4", ffprobe_path=_binary("ffprobe"))
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    seen = 0

    def progress(value: int) -> None:
        nonlocal seen
        seen = value

    with pytest.raises(IndexCancelled):
        repository.build(asset, cancelled=lambda: seen >= 5, progress=progress, chunk_size=5)
    assert repository.state(asset) is IndexState.PARTIAL
    assert repository.lookup_ordinal(asset, 4).status is LookupStatus.HIT
    assert repository.lookup_ordinal(asset, 5).status is LookupStatus.NEEDS_INDEX
    assert repository.lookup_time(asset, Fraction(3, 30)).entry.ordinal == 3
    assert repository.lookup_time(asset, Fraction(4, 30)).status is LookupStatus.NEEDS_INDEX
    assert repository.state(replace(asset, fingerprint="changed")) is IndexState.UNKNOWN
    timeline = repository.build(asset)
    assert timeline.frame_count == 72
    assert repository.lookup_ordinal(asset, 72).status is LookupStatus.OUT_OF_RANGE


@pytest.mark.integration
def test_incremental_timelines_expose_only_real_covered_frames(
    media_dir: Path, tmp_path: Path
) -> None:
    asset = probe_video(media_dir / "f05_h264_bframes.mp4", ffprobe_path=_binary("ffprobe"))
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    previews = []
    complete = repository.build(asset, chunk_size=5, preview=previews.append)
    assert previews[0].frame_count == 1
    assert previews[0].provisional
    assert len(previews) > 2
    assert all(preview.provisional for preview in previews)
    for preview in previews[1:]:
        assert preview.entries == complete.entries[: preview.frame_count]
        assert preview.end_time == complete.local_time_at(preview.frame_count)
        with PreciseDecoder(asset, preview) as decoder:
            last = decoder.frame_at(preview.frame_count - 1)
        assert marker_id(last.rgb) == preview.frame_count - 1
    assert not complete.provisional


@pytest.mark.integration
def test_duplicate_route_reuses_complete_metadata_index(
    media_dir: Path, tmp_path: Path, monkeypatch
) -> None:
    source = media_dir / "f05_h264_bframes.mp4"
    repository = FrameIndexRepository(tmp_path / "index.sqlite3")
    first = probe_video(source, ffprobe_path=_binary("ffprobe"), asset_id="first")
    second = probe_video(source, ffprobe_path=_binary("ffprobe"), asset_id="second")
    original = repository.build(first)

    def forbid_decode(*args, **kwargs):
        raise AssertionError("重复路不应再解码整段视频建立索引")

    monkeypatch.setattr("video_compare.media.index.av.open", forbid_decode)
    copied = repository.build(second)
    assert copied.asset_id == "second"
    assert copied.entries == original.entries
    assert copied.end_time == original.end_time
    assert repository.state(second) is IndexState.COMPLETE


@pytest.mark.integration
def test_worker_latest_mailbox_and_clean_close(media_dir: Path, tmp_path: Path) -> None:
    asset = probe_video(media_dir / "f05_h264_bframes.mp4", ffprobe_path=_binary("ffprobe"))
    timeline = FrameIndexRepository(tmp_path / "index.sqlite3").build(asset)
    cache = FrameCache(8 * 1024 * 1024)
    results: Queue[WorkerResult] = Queue()
    worker = DecoderWorker(asset, timeline, cache, results.put)
    try:
        for seq in range(100):
            worker.submit_latest(FrameRequest(1, 2, seq, asset.asset_id, target_ordinal=seq % 72))
        worker.cancel_before(3)
        worker.submit_latest(FrameRequest(1, 3, 100, asset.asset_id, target_ordinal=71))
        assert worker.pending_count <= 1
        final: WorkerResult | None = None
        for _ in range(102):
            try:
                item = results.get(timeout=2)
            except Empty:
                break
            if item.request.generation == 3:
                final = item
            if item.cache_key:
                cache.release(item.cache_key)
            if final is not None:
                break
        assert final is not None
        assert final.error is None
        assert final.frame is not None
        assert marker_id(final.frame.rgb) == 71
    finally:
        worker.request_close()
        assert worker.join(timeout=5)
