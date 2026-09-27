from __future__ import annotations

from dataclasses import dataclass, field

from video_compare.domain.models import DecodedFrame, FrameGroupSnapshot, GroupTargets
from video_compare.media.workers import WorkerResult


class BarrierError(RuntimeError):
    pass


@dataclass(slots=True)
class FrameBarrier:
    group_id: tuple[int, int, int]
    targets: GroupTargets
    mapping_revision: int = 0
    _frames: dict[str, DecodedFrame] = field(default_factory=dict)

    def add(self, result: WorkerResult) -> FrameGroupSnapshot | None:
        request = result.request
        if request.group_id != self.group_id:
            raise BarrierError("旧请求不能进入当前帧组")
        target = self.targets.targets.get(request.asset_id)
        if target is None:
            raise BarrierError("非参与路结果不能进入当前帧组")
        if result.error:
            raise BarrierError(result.error)
        frame = result.frame
        if frame is None or frame.asset_id != request.asset_id:
            raise BarrierError("worker 未返回正确视频的帧")
        if request.target_ordinal != target.ordinal or frame.ordinal != target.ordinal:
            raise BarrierError("worker 返回的帧序号与固定目标不符")
        if request.asset_id in self._frames:
            raise BarrierError("重复结果不能覆盖本组已有帧")
        self._frames[request.asset_id] = frame
        if len(self._frames) != len(self.targets.targets):
            return None
        return FrameGroupSnapshot(
            group_id=self.group_id,
            requested_global_time=self.targets.global_time,
            reference_ordinal=self.targets.reference_ordinal,
            frames=self._frames,
            mapping_revision=self.mapping_revision,
        )
