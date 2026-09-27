from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, Thread

from video_compare.domain.models import AssetInfo, DecodedFrame, FrameRequest
from video_compare.domain.timeline import FrameTimeline
from video_compare.media.cache import CacheKey, FrameCache
from video_compare.media.decoder import PreciseDecoder


@dataclass(frozen=True, slots=True)
class WorkerResult:
    request: FrameRequest
    frame: DecodedFrame | None
    error: str | None = None
    cache_key: CacheKey | None = None


class DecoderWorker:
    """A single daemon owns one PyAV container and one replaceable request slot."""

    def __init__(
        self,
        asset: AssetInfo,
        timeline: FrameTimeline,
        cache: FrameCache,
        on_result: Callable[[WorkerResult], None],
    ) -> None:
        self.asset = asset
        self.timeline = timeline
        self.cache = cache
        self.on_result = on_result
        self._condition = Condition()
        self._latest: FrameRequest | None = None
        self._generation_floor = 0
        self._timeline_revision: FrameTimeline | None = None
        self._closed = False
        self._thread = Thread(target=self._run, name=f"decoder-{asset.asset_id[:8]}", daemon=True)
        self._thread.start()

    def submit_latest(self, request: FrameRequest) -> None:
        if request.asset_id != self.asset.asset_id:
            raise ValueError("请求视频身份与 worker 不符")
        with self._condition:
            if self._closed:
                raise RuntimeError("worker 已关闭")
            if request.generation < self._generation_floor:
                return
            self._latest = request
            self._condition.notify()

    def cancel_before(self, generation: int) -> None:
        with self._condition:
            self._generation_floor = max(self._generation_floor, generation)
            if self._latest and self._latest.generation < self._generation_floor:
                self._latest = None
            self._condition.notify()

    def extend_timeline(self, timeline: FrameTimeline) -> None:
        if (
            timeline.asset_id != self.asset.asset_id
            or timeline.frame_count < self.timeline.frame_count
        ):
            raise ValueError("索引更新与当前视频不匹配")
        with self._condition:
            self._timeline_revision = timeline
            self._condition.notify()

    def request_close(self) -> None:
        with self._condition:
            self._closed = True
            self._latest = None
            self._condition.notify()

    def join(self, timeout: float | None = None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def pending_count(self) -> int:
        with self._condition:
            return int(self._latest is not None)

    def _run(self) -> None:
        decoder: PreciseDecoder | None = None
        init_error: str | None = None
        try:
            decoder = PreciseDecoder(self.asset, self.timeline)
        except (RuntimeError, OSError, ValueError) as exc:
            init_error = f"{self.asset.label}: 初始化解码器失败：{exc}"
        try:
            while True:
                with self._condition:
                    while self._latest is None and not self._closed:
                        self._condition.wait()
                    if self._closed:
                        return
                    request = self._latest
                    self._latest = None
                    assert request is not None
                    if request.generation < self._generation_floor:
                        continue
                    revision = self._timeline_revision
                    self._timeline_revision = None
                if revision is not None:
                    # Only the owner thread touches the decoder and its container.
                    if decoder is not None:
                        decoder.close()
                    self.timeline = revision
                    decoder = None
                    init_error = None
                    try:
                        decoder = PreciseDecoder(self.asset, revision)
                    except (RuntimeError, OSError, ValueError) as exc:
                        init_error = f"{self.asset.label}: 更新解码索引失败：{exc}"
                if init_error:
                    self.on_result(WorkerResult(request, None, error=init_error))
                    continue
                key = (request.asset_id, request.target_ordinal)
                try:
                    if request.target_ordinal is None:
                        raise ValueError("worker 需要已经映射的目标 ordinal")
                    assert decoder is not None
                    frame = self.cache.acquire(key)
                    if frame is None:
                        frame = decoder.frame_at(request.target_ordinal)
                        frame = self.cache.insert_acquired(key, frame)
                    result = WorkerResult(request, frame, cache_key=key)
                except (RuntimeError, ValueError, OSError) as exc:
                    result = WorkerResult(request, None, error=f"{self.asset.label}: {exc}")
                self.on_result(result)
        finally:
            if decoder is not None:
                decoder.close()
