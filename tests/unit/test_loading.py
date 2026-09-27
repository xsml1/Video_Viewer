from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from video_compare.media.loading import AssetLoadWorker
from video_compare.media.probe import ProbeCancelled


def test_loader_cancels_inflight_probe_and_closes_cleanly(monkeypatch) -> None:
    entered = Event()

    def slow_probe(path, *, ffprobe_path, asset_id, cancelled):
        entered.set()
        deadline = time.monotonic() + 2
        while not cancelled() and time.monotonic() < deadline:
            time.sleep(0.005)
        if cancelled():
            raise ProbeCancelled("cancelled")
        raise AssertionError("测试中的探测任务未及时取消")

    monkeypatch.setattr("video_compare.media.loading.probe_video", slow_probe)
    loader = AssetLoadWorker(repository=None, ffprobe_path=None)
    loader.submit(Path("unread-test-file.mp4"))
    assert entered.wait(timeout=1)
    loader.cancel_all()
    loader.request_close()
    assert loader.join(timeout=1)
    assert loader.pop_result() is None
