from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from video_compare.domain.models import DecodedFrame


class CacheBudgetError(RuntimeError):
    pass


CacheKey = tuple[str, int]


class FrameCache:
    """Thread-safe byte LRU; front and pending frames hold explicit pins."""

    def __init__(self, budget_bytes: int = 512 * 1024 * 1024) -> None:
        if budget_bytes <= 0:
            raise ValueError("缓存预算必须为正数")
        self.budget_bytes = budget_bytes
        self._lock = RLock()
        self._items: OrderedDict[CacheKey, DecodedFrame] = OrderedDict()
        self._pins: dict[CacheKey, int] = {}
        self._used_bytes = 0

    @property
    def used_bytes(self) -> int:
        with self._lock:
            return self._used_bytes

    @property
    def item_count(self) -> int:
        with self._lock:
            return len(self._items)

    def acquire(self, key: CacheKey) -> DecodedFrame | None:
        with self._lock:
            frame = self._items.get(key)
            if frame is not None:
                self._items.move_to_end(key)
                self._pins[key] = self._pins.get(key, 0) + 1
            return frame

    def insert_acquired(self, key: CacheKey, frame: DecodedFrame) -> DecodedFrame:
        with self._lock:
            existing = self._items.get(key)
            if existing is not None:
                self._items.move_to_end(key)
                self._pins[key] = self._pins.get(key, 0) + 1
                return existing
            required = frame.rgb.nbytes
            if required > self.budget_bytes:
                raise CacheBudgetError(f"单帧 {required} 字节超过缓存预算 {self.budget_bytes} 字节")
            while self._used_bytes + required > self.budget_bytes:
                victim = next((item for item in self._items if self._pins.get(item, 0) == 0), None)
                if victim is None:
                    raise CacheBudgetError("当前显示/待提交帧已占满缓存预算")
                old = self._items.pop(victim)
                self._used_bytes -= old.rgb.nbytes
            self._items[key] = frame
            self._pins[key] = 1
            self._used_bytes += required
            return frame

    def release(self, key: CacheKey) -> None:
        with self._lock:
            count = self._pins.get(key, 0)
            if count == 0:
                raise RuntimeError(f"释放未 pin 的缓存帧：{key}")
            if count == 1:
                del self._pins[key]
            else:
                self._pins[key] = count - 1

    def clear_unpinned(self) -> None:
        with self._lock:
            for key in list(self._items):
                if self._pins.get(key, 0) == 0:
                    self._used_bytes -= self._items.pop(key).rgb.nbytes
