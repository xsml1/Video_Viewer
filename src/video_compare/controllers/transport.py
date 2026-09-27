from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from queue import Empty, Full, Queue
from time import monotonic_ns

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from video_compare.controllers.barrier import BarrierError, FrameBarrier
from video_compare.domain.models import (
    AssetInfo,
    FrameGroupSnapshot,
    FrameRequest,
    GroupTargets,
    LoopRange,
    SyncMode,
    TimelineSpec,
    TransportState,
)
from video_compare.domain.timeline import FrameTimeline, TimelineMapper
from video_compare.media.cache import CacheKey, FrameCache
from video_compare.media.workers import DecoderWorker, WorkerResult


class TransportController(QObject):
    """One main-thread transport clock and one atomic frame barrier per event."""

    group_ready = Signal(object)
    state_changed = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        assets: Mapping[str, AssetInfo],
        timelines: Mapping[str, FrameTimeline],
        spec: TimelineSpec,
        *,
        cache_bytes: int = 512 * 1024 * 1024,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.assets = dict(assets)
        self.timelines = dict(timelines)
        self.spec = spec
        self.mapper = TimelineMapper(timelines)
        self.cache = FrameCache(cache_bytes)
        self.state = TransportState.PAUSED
        self.session_epoch = 1
        self.generation = 0
        self.request_seq = 0
        self.speed = Fraction(1)
        self.loop_start: Fraction | int | None = None
        self.loop_range: LoopRange | None = None
        self.loop_enabled = False
        self.requested_time = Fraction(0)
        self.requested_frame = 0
        self._queued_frame: int | None = None
        self._queued_time: Fraction | None = None
        self._queued_step = False
        self._queued_resume = False
        self.displayed: FrameGroupSnapshot | None = None
        self._committed_targets: GroupTargets | None = None
        self._front_keys: list[CacheKey] = []
        self._pending: FrameBarrier | None = None
        self._pending_keys: list[CacheKey] = []
        self._resume_after_seek = False
        self._results: Queue[WorkerResult] = Queue(maxsize=max(12, 2 * len(spec.participants)))
        self._workers = {
            asset_id: DecoderWorker(
                self.assets[asset_id],
                self.timelines[asset_id],
                self.cache,
                self._enqueue_result,
            )
            for asset_id in spec.participants
        }
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(10)
        self._poll_timer.timeout.connect(self._drain_results)
        self._poll_timer.start()
        self._play_timer = QTimer(self)
        self._play_timer.setSingleShot(True)
        self._play_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._play_timer.timeout.connect(self._request_next_event)
        self._next_deadline_ns: int | None = None

    def _set_state(self, state: TransportState) -> None:
        if self.state != state:
            self.state = state
            self.state_changed.emit(state)

    def extend_timeline(self, asset_id: str, timeline: FrameTimeline) -> None:
        old = self.timelines.get(asset_id)
        if old is None or timeline.asset_id != asset_id or timeline.frame_count < old.frame_count:
            raise ValueError("索引更新与当前同步组不匹配")
        if timeline.entries[: old.frame_count] != old.entries:
            raise ValueError("索引更新改变了已显示帧的身份")
        self.timelines[asset_id] = timeline
        self.mapper = TimelineMapper(self.timelines)
        worker = self._workers.get(asset_id)
        if worker is not None:
            worker.extend_timeline(timeline)
        if self._queued_frame is not None:
            self._try_queued_frame()
            return
        if self._queued_time is not None:
            self._try_queued_time()
            return
        if (
            self.state is TransportState.BUFFERING
            and self._pending is None
            and self._resume_after_seek
        ):
            self._set_state(TransportState.PLAYING)
            self._schedule_next_event()

    def _queue_frame(self, ordinal: int, *, step: bool, resume: bool) -> None:
        self._invalidate()
        self.requested_frame = ordinal
        self._queued_frame = ordinal
        self._queued_time = None
        self._queued_step = step
        self._queued_resume = resume
        self._set_state(TransportState.SEEKING)

    def _queue_time(self, target: Fraction, *, step: bool, resume: bool) -> None:
        self._invalidate()
        self.requested_time = target
        self._queued_time = target
        self._queued_frame = None
        self._queued_step = step
        self._queued_resume = resume
        self._set_state(TransportState.SEEKING)

    def _try_queued_frame(self) -> None:
        ordinal = self._queued_frame
        if ordinal is None:
            return
        try:
            targets = self.mapper.map_reference_frame(ordinal + 1, self.spec)
        except ValueError as exc:
            if any(self.timelines[key].provisional for key in self.spec.participants):
                return
            if not self._queued_step:
                self._queued_frame = None
                self._set_state(TransportState.PAUSED)
                self.error_occurred.emit(str(exc))
                return
            valid = self.mapper.valid_range(self.spec)
            clamped = min(int(valid.end), max(int(valid.start), ordinal))
            targets = self.mapper.map_reference_frame(clamped + 1, self.spec)
        resume = self._queued_resume
        self._queued_frame = None
        self.requested_time = targets.global_time
        self.requested_frame = targets.reference_ordinal
        self._resume_after_seek = resume
        self._request_group(targets, new_generation=True)

    def _try_queued_time(self) -> None:
        target = self._queued_time
        if target is None:
            return
        try:
            if self.spec.mode is SyncMode.TIME:
                targets = self.mapper.map_time(target, self.spec)
            else:
                reference = self.timelines[self.spec.reference_id]
                targets = self.mapper.map_frame(reference.ordinal_at(target), self.spec)
        except ValueError as exc:
            if any(self.timelines[key].provisional for key in self.spec.participants):
                return
            if not self._queued_step:
                self._queued_time = None
                self._set_state(TransportState.PAUSED)
                self.error_occurred.emit(str(exc))
                return
            valid = self.mapper.valid_range(self.spec)
            if self.spec.mode is SyncMode.TIME:
                last = self.mapper.last_event(self.spec).global_time
                targets = self.mapper.map_time(
                    min(last, max(Fraction(valid.start), target)), self.spec
                )
            else:
                reference = self.timelines[self.spec.reference_id]
                local = min(reference.end_time - Fraction(1, 10**9), max(Fraction(0), target))
                ordinal = min(int(valid.end), max(int(valid.start), reference.ordinal_at(local)))
                targets = self.mapper.map_frame(ordinal, self.spec)
        resume = self._queued_resume
        self._queued_time = None
        self.requested_time = targets.global_time
        self.requested_frame = targets.reference_ordinal
        self._resume_after_seek = resume
        self._request_group(targets, new_generation=True)

    def _enqueue_result(self, result: WorkerResult) -> None:
        try:
            self._results.put_nowait(result)
        except Full:
            try:
                oldest = self._results.get_nowait()
            except Empty:
                oldest = None
            if oldest is not None and oldest.cache_key:
                self.cache.release(oldest.cache_key)
            try:
                self._results.put_nowait(result)
            except Full:
                if result.cache_key:
                    self.cache.release(result.cache_key)

    def _release_pending(self) -> None:
        for key in self._pending_keys:
            self.cache.release(key)
        self._pending_keys.clear()
        self._pending = None

    def _invalidate(self) -> None:
        self._play_timer.stop()
        self._next_deadline_ns = None
        self.generation += 1
        self._release_pending()
        for worker in self._workers.values():
            worker.cancel_before(self.generation)

    def _request_group(self, targets: GroupTargets, *, new_generation: bool) -> None:
        self._queued_frame = None
        self._queued_time = None
        if new_generation:
            self._invalidate()
        else:
            self._release_pending()
        # The immutable displayed snapshot and canvas own their RGB buffers.
        # Releasing cache pins here lets the next complete group fit a small
        # budget without changing or tearing the picture still on screen.
        for key in self._front_keys:
            self.cache.release(key)
        self._front_keys.clear()
        self.request_seq += 1
        group_id = (self.session_epoch, self.generation, self.request_seq)
        self._pending = FrameBarrier(group_id, targets)
        self._set_state(TransportState.SEEKING if new_generation else TransportState.BUFFERING)
        for asset_id, target in targets.targets.items():
            self._workers[asset_id].submit_latest(
                FrameRequest(
                    self.session_epoch,
                    self.generation,
                    self.request_seq,
                    asset_id,
                    target_ordinal=target.ordinal,
                )
            )

    def _drain_results(self) -> None:
        for _ in range(self._results.maxsize):
            try:
                result = self._results.get_nowait()
            except Empty:
                return
            if result.request.purpose == "prefetch":
                if result.cache_key:
                    self.cache.release(result.cache_key)
                continue
            pending = self._pending
            if pending is None or result.request.group_id != pending.group_id:
                if result.cache_key:
                    self.cache.release(result.cache_key)
                continue
            if result.cache_key:
                self._pending_keys.append(result.cache_key)
            try:
                snapshot = pending.add(result)
            except BarrierError as exc:
                self._release_pending()
                self._resume_after_seek = False
                self._set_state(TransportState.ERROR)
                self.error_occurred.emit(str(exc))
                continue
            if snapshot is None:
                continue
            self.displayed = snapshot
            self._committed_targets = pending.targets
            for key in self._front_keys:
                self.cache.release(key)
            self._front_keys = self._pending_keys
            self._pending_keys = []
            self._pending = None
            self.group_ready.emit(snapshot)
            if self._resume_after_seek:
                self._set_state(TransportState.PLAYING)
                self._schedule_next_event()
            else:
                self._set_state(TransportState.PAUSED)

    def seek_time(self, target: Fraction, resume: bool = False) -> None:
        try:
            if self.spec.mode is SyncMode.TIME:
                targets = self.mapper.map_time(target, self.spec)
            else:
                reference = self.timelines[self.spec.reference_id]
                targets = self.mapper.map_frame(reference.ordinal_at(target), self.spec)
        except ValueError:
            if target < 0 or not any(
                self.timelines[key].provisional for key in self.spec.participants
            ):
                raise
            self._queue_time(target, step=False, resume=resume)
            return
        self.requested_time = target
        self.requested_frame = targets.reference_ordinal
        self._resume_after_seek = resume
        self._request_group(targets, new_generation=True)

    def seek_reference_frame(self, ui_frame: int, resume: bool = False) -> None:
        if ui_frame < 1:
            raise ValueError("界面帧号从 1 开始")
        try:
            targets = self.mapper.map_reference_frame(ui_frame, self.spec)
        except ValueError:
            if not any(self.timelines[key].provisional for key in self.spec.participants):
                raise
            self._queue_frame(ui_frame - 1, step=False, resume=resume)
            return
        self._queued_frame = None
        self.requested_time = targets.global_time
        self.requested_frame = targets.reference_ordinal
        self._resume_after_seek = resume
        self._request_group(targets, new_generation=True)

    def step(self, direction: int, amount: Fraction, unit: str) -> None:
        if direction not in {-1, 1} or amount <= 0:
            raise ValueError("步进方向或数量无效")
        base_frame = self.requested_frame
        base_time = self.requested_time
        self.pause()
        valid = self.mapper.valid_range(self.spec)
        if unit == "frame":
            count = int(amount)
            if amount != count:
                raise ValueError("帧步进需要整数")
            target = base_frame + direction * count
            target = max(0, target)
            if any(self.timelines[key].provisional for key in self.spec.participants):
                try:
                    targets = self.mapper.map_reference_frame(target + 1, self.spec)
                except ValueError:
                    self._queue_frame(target, step=True, resume=False)
                    return
                self.requested_time = targets.global_time
                self.requested_frame = targets.reference_ordinal
                self._resume_after_seek = False
                self._request_group(targets, new_generation=True)
                return
            if self.spec.mode is SyncMode.FRAME:
                target = min(int(valid.end), max(int(valid.start), target))
                targets = self.mapper.map_frame(target, self.spec)
            else:
                reference = self.timelines[self.spec.reference_id]
                target = min(reference.frame_count - 1, max(0, target))
                targets = self.mapper.map_reference_frame(target + 1, self.spec)
        elif unit == "second":
            cursor = base_time + direction * amount
            if any(self.timelines[key].provisional for key in self.spec.participants):
                cursor = max(Fraction(0), cursor)
                try:
                    if self.spec.mode is SyncMode.TIME:
                        targets = self.mapper.map_time(cursor, self.spec)
                    else:
                        reference = self.timelines[self.spec.reference_id]
                        targets = self.mapper.map_frame(reference.ordinal_at(cursor), self.spec)
                except ValueError:
                    self._queue_time(cursor, step=True, resume=False)
                    return
                self.requested_time = cursor
                self.requested_frame = targets.reference_ordinal
                self._resume_after_seek = False
                self._request_group(targets, new_generation=True)
                return
            if self.spec.mode is SyncMode.TIME:
                last = self.mapper.last_event(self.spec).global_time
                cursor = min(last, max(Fraction(valid.start), cursor))
                targets = self.mapper.map_time(cursor, self.spec)
            else:
                reference = self.timelines[self.spec.reference_id]
                cursor = min(reference.end_time - Fraction(1, 10**9), max(Fraction(0), cursor))
                target = reference.ordinal_at(cursor)
                target = min(int(valid.end), max(int(valid.start), target))
                targets = self.mapper.map_frame(target, self.spec)
            self.requested_time = cursor
        else:
            raise ValueError("步进单位必须是 frame 或 second")
        if unit == "frame":
            self.requested_time = targets.global_time
        self.requested_frame = targets.reference_ordinal
        self._resume_after_seek = False
        self._request_group(targets, new_generation=True)

    def play(self) -> None:
        if self.state is TransportState.CLOSING:
            return
        if self._queued_frame is not None:
            self._queued_resume = True
            return
        if self.loop_enabled and self.loop_range and self._pending is not None:
            pending = self._pending.targets
            position = (
                pending.global_time
                if self.spec.mode is SyncMode.TIME
                else pending.reference_ordinal
            )
            if position < self.loop_range.start or position >= self.loop_range.end:
                self._seek_loop_start(resume=True)
                return
        if self._pending is not None:
            self._resume_after_seek = True
            return
        if self.loop_enabled and self.loop_range and self.state is TransportState.ENDED:
            self._seek_loop_start(resume=True)
            return
        if self.loop_enabled and self.loop_range and self.displayed is not None:
            current = (
                self.displayed.requested_global_time
                if self.spec.mode is SyncMode.TIME
                else self.displayed.reference_ordinal
            )
            if current < self.loop_range.start or current >= self.loop_range.end:
                self._seek_loop_start(resume=True)
                return
        if self.displayed is None or self.state is TransportState.ENDED:
            valid = self.mapper.valid_range(self.spec)
            if valid.empty:
                self.error_occurred.emit("参与视频没有公共有效范围")
                return
            if self.spec.mode is SyncMode.TIME:
                self.seek_time(Fraction(valid.start), resume=True)
            else:
                targets = self.mapper.map_frame(int(valid.start), self.spec)
                self.requested_frame = targets.reference_ordinal
                self.requested_time = targets.global_time
                self._resume_after_seek = True
                self._request_group(targets, new_generation=True)
            return
        self._resume_after_seek = True
        self._next_deadline_ns = None
        self._set_state(TransportState.PLAYING)
        self._schedule_next_event()

    def pause(self) -> None:
        self._play_timer.stop()
        self._next_deadline_ns = None
        self._resume_after_seek = False
        self._queued_resume = False
        if self.state in {TransportState.PLAYING, TransportState.BUFFERING}:
            self._invalidate()
            if self._committed_targets is not None:
                self.requested_time = self._committed_targets.global_time
                self.requested_frame = self._committed_targets.reference_ordinal
        self._set_state(TransportState.PAUSED)

    def set_speed(self, speed: Fraction) -> None:
        speed = Fraction(speed)
        if speed not in {Fraction(1, 4), Fraction(1, 2), Fraction(1), Fraction(2), Fraction(4)}:
            raise ValueError("仅支持 0.25、0.5、1、2、4 倍速")
        self.speed = speed
        self._reschedule_playback()

    def set_loop_start_from_displayed(self) -> Fraction | int:
        if self.displayed is None:
            raise ValueError("还没有已显示的同步帧组")
        self.loop_start = (
            self.displayed.requested_global_time
            if self.spec.mode is SyncMode.TIME
            else self.displayed.reference_ordinal
        )
        self.loop_range = None
        self.loop_enabled = False
        self._reschedule_playback()
        return self.loop_start

    def set_loop_end_from_displayed(self) -> LoopRange:
        if self.displayed is None or self.loop_start is None:
            raise ValueError("请先在已显示位置设置循环起点 I")
        reference = self.timelines[self.spec.reference_id]
        ordinal = self.displayed.reference_ordinal
        if self.spec.mode is SyncMode.TIME:
            boundary = (
                reference.local_time_at(ordinal + 1)
                if ordinal + 1 < reference.frame_count
                else reference.end_time
            )
            boundary -= self.spec.time_offsets[self.spec.reference_id]
        else:
            boundary = ordinal + 1
        loop_range = LoopRange(self.spec.mode, self.loop_start, boundary)
        valid = self.mapper.valid_range(self.spec)
        if loop_range.start < valid.start or loop_range.end > (
            valid.end if self.spec.mode is SyncMode.TIME else valid.end + 1
        ):
            raise ValueError("循环区间必须位于公共有效范围")
        self.loop_range = loop_range
        self.loop_enabled = False
        self._reschedule_playback()
        return loop_range

    def set_loop_enabled(self, enabled: bool) -> None:
        if enabled and self.loop_range is None:
            raise ValueError("请先设置有效的 I/O 循环区间")
        self.loop_enabled = enabled
        if enabled and self.loop_range is not None:
            if self._pending is not None:
                pending = self._pending.targets
                position = (
                    pending.global_time
                    if self.spec.mode is SyncMode.TIME
                    else pending.reference_ordinal
                )
            elif self.displayed is not None:
                position = (
                    self.displayed.requested_global_time
                    if self.spec.mode is SyncMode.TIME
                    else self.displayed.reference_ordinal
                )
            else:
                position = None
            if position is not None and (
                position < self.loop_range.start or position >= self.loop_range.end
            ):
                resume = self._resume_after_seek or self.state in {
                    TransportState.PLAYING,
                    TransportState.BUFFERING,
                }
                self._seek_loop_start(resume=resume)
                return
        self._reschedule_playback()

    def _reschedule_playback(self) -> None:
        if self.state is TransportState.PLAYING:
            self._play_timer.stop()
            self._next_deadline_ns = None
            self._schedule_next_event()

    def _seek_loop_start(self, *, resume: bool) -> None:
        assert self.loop_range is not None
        if self.spec.mode is SyncMode.TIME:
            self.seek_time(Fraction(self.loop_range.start), resume=resume)
        else:
            self.seek_reference_frame(int(self.loop_range.start) + 1, resume=resume)

    def _next_play_event(self) -> tuple[GroupTargets, Fraction] | None:
        if self._committed_targets is None:
            return None
        current = self._committed_targets
        next_targets = self.mapper.next_event(current, self.spec)
        if self.loop_enabled and self.loop_range is not None:
            current_position = (
                current.global_time
                if self.spec.mode is SyncMode.TIME
                else current.reference_ordinal
            )
            if current_position < self.loop_range.start or current_position >= self.loop_range.end:
                target = (
                    self.mapper.map_time(Fraction(self.loop_range.start), self.spec)
                    if self.spec.mode is SyncMode.TIME
                    else self.mapper.map_frame(int(self.loop_range.start), self.spec)
                )
                return target, Fraction(0)
            next_position = (
                next_targets.global_time
                if next_targets is not None and self.spec.mode is SyncMode.TIME
                else next_targets.reference_ordinal
                if next_targets is not None
                else None
            )
            if next_position is None or next_position >= self.loop_range.end:
                if self.spec.mode is SyncMode.TIME:
                    end_time = Fraction(self.loop_range.end)
                else:
                    reference = self.timelines[self.spec.reference_id]
                    end_ordinal = int(self.loop_range.end)
                    end_time = (
                        reference.local_time_at(end_ordinal)
                        if end_ordinal < reference.frame_count
                        else reference.end_time
                    )
                target = (
                    self.mapper.map_time(Fraction(self.loop_range.start), self.spec)
                    if self.spec.mode is SyncMode.TIME
                    else self.mapper.map_frame(int(self.loop_range.start), self.spec)
                )
                return target, max(Fraction(0), end_time - current.global_time)
        if next_targets is None:
            return None
        return next_targets, next_targets.global_time - current.global_time

    def _schedule_next_event(self) -> None:
        if self._committed_targets is None or self.state is not TransportState.PLAYING:
            return
        next_event = self._next_play_event()
        if next_event is None:
            if any(self.timelines[key].provisional for key in self.spec.participants):
                self._next_deadline_ns = None
                self._set_state(TransportState.BUFFERING)
            else:
                self._next_deadline_ns = None
                self._resume_after_seek = False
                self._set_state(TransportState.ENDED)
            return
        next_targets, interval = next_event
        self._prefetch(next_targets)
        # Keep one monotonic media clock. Decode time must not accumulate as
        # extra delay after each committed group; a late group catches up by
        # reducing only the next wait, without skipping frame identities.
        now = monotonic_ns()
        if self._next_deadline_ns is None:
            self._next_deadline_ns = now
        self._next_deadline_ns += round(float(interval / self.speed) * 1_000_000_000)
        wait_ms = max(1, round((self._next_deadline_ns - now) / 1_000_000))
        self._play_timer.start(wait_ms)

    def _prefetch(self, targets: GroupTargets) -> None:
        # One lookahead target per route. Workers keep only one replaceable queued
        # request, so interactive seeks can supersede this work immediately.
        for asset_id, target in targets.targets.items():
            self._workers[asset_id].submit_latest(
                FrameRequest(
                    self.session_epoch,
                    self.generation,
                    self.request_seq + 1,
                    asset_id,
                    target_ordinal=target.ordinal,
                    purpose="prefetch",
                )
            )

    def _request_next_event(self) -> None:
        if self.state is not TransportState.PLAYING or self._committed_targets is None:
            return
        next_event = self._next_play_event()
        if next_event is None:
            if any(self.timelines[key].provisional for key in self.spec.participants):
                self._set_state(TransportState.BUFFERING)
            else:
                self._set_state(TransportState.ENDED)
            return
        targets, _ = next_event
        self.requested_time = targets.global_time
        self.requested_frame = targets.reference_ordinal
        self._request_group(targets, new_generation=False)

    def close(self) -> bool:
        self._set_state(TransportState.CLOSING)
        self._play_timer.stop()
        self._next_deadline_ns = None
        self._poll_timer.stop()
        self._invalidate()
        for worker in self._workers.values():
            worker.request_close()
        joined = [worker.join(timeout=5) for worker in self._workers.values()]
        clean = all(joined)
        self._drain_results()
        for key in self._front_keys:
            self.cache.release(key)
        self._front_keys.clear()
        self.cache.clear_unpinned()
        return clean
