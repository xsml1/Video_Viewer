from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Condition, Thread
from uuid import uuid4

from video_compare.domain.models import AssetInfo
from video_compare.domain.timeline import FrameTimeline
from video_compare.media.index import FrameIndexRepository, IndexCancelled
from video_compare.media.index import IndexError as MediaIndexError
from video_compare.media.probe import ProbeCancelled, ProbeError, probe_video


@dataclass(frozen=True, slots=True)
class LoadTask:
    path: Path
    generation: int
    replace_id: str | None = None
    task_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class LoadResult:
    task: LoadTask
    asset: AssetInfo | None = None
    timeline: FrameTimeline | None = None
    error: str | None = None
    partial: bool = False


class AssetLoadWorker:
    """One fast first-frame probe and one bounded full-index worker."""

    def __init__(self, repository: FrameIndexRepository, ffprobe_path: Path | None) -> None:
        self._repository = repository
        self._ffprobe_path = ffprobe_path
        self._condition = Condition()
        self._tasks: deque[LoadTask] = deque()
        self._index_tasks: deque[tuple[LoadTask, AssetInfo, FrameTimeline | None]] = deque()
        self._results: Queue[LoadResult] = Queue(maxsize=6)
        self._generation = 0
        self._cancelled: set[str] = set()
        self._active_probe: str | None = None
        self._active_index: str | None = None
        self._closed = False
        self._probe_thread = Thread(target=self._probe_run, name="asset-probe", daemon=True)
        self._thread = Thread(target=self._run, name="asset-index", daemon=True)
        self._probe_thread.start()
        self._thread.start()

    def submit(self, path: Path, replace_id: str | None = None) -> LoadTask:
        with self._condition:
            if self._closed or len(self._tasks) + len(self._index_tasks) >= 6:
                raise RuntimeError("导入队列已关闭或已满")
            task = LoadTask(path, self._generation, replace_id)
            self._tasks.append(task)
            self._condition.notify_all()
            return task

    def cancel_all(self) -> None:
        with self._condition:
            self._generation += 1
            self._tasks.clear()
            self._index_tasks.clear()
            self._cancelled.clear()
            self._condition.notify_all()

    def cancel(self, task: LoadTask) -> None:
        with self._condition:
            self._tasks = deque(item for item in self._tasks if item.task_id != task.task_id)
            self._index_tasks = deque(
                item for item in self._index_tasks if item[0].task_id != task.task_id
            )
            if task.task_id in {self._active_probe, self._active_index}:
                self._cancelled.add(task.task_id)
            self._condition.notify_all()

    def request_close(self) -> None:
        with self._condition:
            self._closed = True
            self._generation += 1
            self._tasks.clear()
            self._index_tasks.clear()
            self._condition.notify_all()

    def join(self, timeout: float = 5) -> bool:
        self._thread.join(timeout)
        self._probe_thread.join(timeout)
        return not self._thread.is_alive() and not self._probe_thread.is_alive()

    def pop_result(self) -> LoadResult | None:
        try:
            return self._results.get_nowait()
        except Empty:
            return None

    def _task_obsolete(self, task: LoadTask) -> bool:
        with self._condition:
            return (
                self._closed
                or task.generation != self._generation
                or task.task_id in self._cancelled
            )

    def _publish(self, result: LoadResult) -> None:
        while not self._task_obsolete(result.task):
            try:
                self._results.put(result, timeout=0.1)
                return
            except Full:
                continue

    def _probe_run(self) -> None:
        while True:
            with self._condition:
                while not self._tasks and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                task = self._tasks.popleft()
                self._active_probe = task.task_id
            if self._task_obsolete(task):
                with self._condition:
                    self._active_probe = None
                continue
            try:
                asset = probe_video(
                    task.path,
                    ffprobe_path=self._ffprobe_path,
                    asset_id=uuid4().hex,
                    cancelled=lambda task=task: self._task_obsolete(task),
                )
                if asset.color_info.hdr_unsupported:
                    color = asset.color_info
                    raise ProbeError(
                        "BT.2020 CL 或非兼容 Dolby Vision 尚未支持，已拒绝导入该路；"
                        f"源元信息：{color.primaries or '未知原色'}/"
                        f"{color.transfer or '未知传递函数'}/{color.matrix or '未知矩阵'}"
                    )
                first: FrameTimeline | None = None
                if task.replace_id is None:
                    first = self._repository.first_frame_timeline(
                        asset, cancelled=lambda task=task: self._task_obsolete(task)
                    )
                    self._publish(LoadResult(task, asset, first, partial=True))
                with self._condition:
                    if not self._closed and not self._task_obsolete_unlocked(task):
                        self._index_tasks.append((task, asset, first))
                        self._condition.notify_all()
            except (ProbeCancelled, IndexCancelled):
                pass
            except (OSError, ValueError, ProbeError, RuntimeError) as exc:
                self._publish(LoadResult(task, error=str(exc)))
            finally:
                with self._condition:
                    self._active_probe = None
                    if self._active_index != task.task_id:
                        self._cancelled.discard(task.task_id)

    def _task_obsolete_unlocked(self, task: LoadTask) -> bool:
        return (
            self._closed or task.generation != self._generation or task.task_id in self._cancelled
        )

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._index_tasks and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                task, asset, first = self._index_tasks.popleft()
                self._active_index = task.task_id
            if self._task_obsolete(task):
                with self._condition:
                    self._active_index = None
                    self._cancelled.discard(task.task_id)
                continue
            try:

                def publish_preview(
                    timeline: FrameTimeline,
                    first: FrameTimeline | None = first,
                    task: LoadTask = task,
                    asset: AssetInfo = asset,
                ) -> None:
                    if first is not None and timeline.entries[0] != first.entries[0]:
                        raise MediaIndexError("源文件在首帧预览与完整索引之间发生变化")
                    if timeline.frame_count > 1:
                        self._publish(LoadResult(task, asset, timeline, partial=True))

                timeline = self._repository.build(
                    asset,
                    cancelled=lambda task=task: self._task_obsolete(task),
                    preview=publish_preview if task.replace_id is None else None,
                )
                if first is not None and timeline.entries[0] != first.entries[0]:
                    raise MediaIndexError("源文件在首帧预览与完整索引之间发生变化")
                result = LoadResult(task, asset, timeline)
            except (ProbeCancelled, IndexCancelled):
                continue
            except (OSError, ValueError, ProbeError, RuntimeError) as exc:
                result = LoadResult(task, error=str(exc))
            finally:
                with self._condition:
                    self._active_index = None
                    self._cancelled.discard(task.task_id)
            self._publish(result)
