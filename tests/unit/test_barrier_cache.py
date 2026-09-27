from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from video_compare.controllers.barrier import BarrierError, FrameBarrier
from video_compare.domain.models import (
    DecodedFrame,
    FrameRequest,
    GroupTargets,
    TargetFrame,
)
from video_compare.media.cache import CacheBudgetError, FrameCache
from video_compare.media.workers import WorkerResult


def decoded(asset_id: str, ordinal: int) -> DecodedFrame:
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[:, :, 0] = ordinal
    return DecodedFrame(asset_id, ordinal, ordinal, Fraction(1, 30), Fraction(ordinal, 30), rgb)


def request(asset_id: str, ordinal: int, generation: int = 2) -> FrameRequest:
    return FrameRequest(1, generation, 3, asset_id, target_ordinal=ordinal)


def test_barrier_commits_only_complete_correct_group() -> None:
    targets = GroupTargets(
        Fraction(1, 30),
        1,
        {"a": TargetFrame("a", 1, Fraction(1, 30)), "b": TargetFrame("b", 2, Fraction(2, 30))},
    )
    barrier = FrameBarrier((1, 2, 3), targets)
    assert barrier.add(WorkerResult(request("b", 2), decoded("b", 2))) is None
    with pytest.raises(BarrierError, match="旧请求"):
        barrier.add(WorkerResult(request("a", 1, generation=1), decoded("a", 1)))
    with pytest.raises(BarrierError, match="序号"):
        barrier.add(WorkerResult(request("a", 1), decoded("a", 0)))
    snapshot = barrier.add(WorkerResult(request("a", 1), decoded("a", 1)))
    assert snapshot is not None
    assert set(snapshot.frames) == {"a", "b"}
    with pytest.raises(TypeError):
        snapshot.frames["a"] = decoded("a", 3)


def test_cache_counts_bytes_and_respects_pins() -> None:
    cache = FrameCache(budget_bytes=24)
    first = decoded("a", 1)
    second = decoded("a", 2)
    third = decoded("a", 3)
    cache.insert_acquired(("a", 1), first)
    cache.insert_acquired(("a", 2), second)
    assert cache.used_bytes == 24
    with pytest.raises(CacheBudgetError):
        cache.insert_acquired(("a", 3), third)
    cache.release(("a", 1))
    cache.insert_acquired(("a", 3), third)
    assert cache.used_bytes == 24
    assert cache.acquire(("a", 1)) is None
    assert cache.acquire(("a", 2)) is second
    cache.release(("a", 2))
    cache.release(("a", 2))
    cache.release(("a", 3))
    cache.clear_unpinned()
    assert cache.used_bytes == 0
