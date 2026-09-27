from __future__ import annotations

import sqlite3
from bisect import bisect_right
from collections import Counter
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import av

from video_compare.domain.models import (
    AssetInfo,
    FrameIndexEntry,
    IndexLookup,
    IndexState,
    LookupStatus,
)
from video_compare.domain.timeline import FrameTimeline


class IndexError(RuntimeError):
    pass


class IndexCancelled(IndexError):
    pass


class FrameIndexRepository:
    """SQLite metadata index; each caller opens its own connection."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    end_num INTEGER,
                    end_den INTEGER,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS frames (
                    asset_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    pts INTEGER,
                    tb_num INTEGER NOT NULL,
                    tb_den INTEGER NOT NULL,
                    duration_ticks INTEGER,
                    is_keyframe INTEGER NOT NULL,
                    pts_occurrence INTEGER NOT NULL,
                    timing_quality TEXT NOT NULL,
                    PRIMARY KEY(asset_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS frames_asset_pts ON frames(asset_id, pts);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=20)

    def state(self, asset: AssetInfo) -> IndexState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fingerprint, schema_version, state FROM assets WHERE asset_id = ?",
                (asset.asset_id,),
            ).fetchone()
        if not row or row[0] != asset.fingerprint or row[1] != self.SCHEMA_VERSION:
            return IndexState.UNKNOWN
        return IndexState(row[2])

    def lookup_ordinal(self, asset: AssetInfo, ordinal: int) -> IndexLookup:
        if ordinal < 0:
            return IndexLookup(LookupStatus.OUT_OF_RANGE, reason="帧号必须大于等于 0")
        state = self.state(asset)
        if state is IndexState.UNKNOWN:
            return IndexLookup(LookupStatus.NEEDS_INDEX, reason="索引不存在或指纹已变化")
        if state is IndexState.FAILED:
            return IndexLookup(LookupStatus.INVALID_TIMING, reason="索引构建失败")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT ordinal,pts,tb_num,tb_den,duration_ticks,is_keyframe,"
                "pts_occurrence,timing_quality FROM frames WHERE asset_id=? AND ordinal=?",
                (asset.asset_id, ordinal),
            ).fetchone()
        if row:
            return IndexLookup(LookupStatus.HIT, FrameIndexEntry(*row))
        if state is IndexState.COMPLETE:
            return IndexLookup(LookupStatus.OUT_OF_RANGE, reason="已超出最后一帧")
        return IndexLookup(LookupStatus.NEEDS_INDEX, reason="目标帧尚未建立索引")

    def lookup_time(self, asset: AssetInfo, local_time: Fraction) -> IndexLookup:
        if local_time < 0:
            return IndexLookup(LookupStatus.OUT_OF_RANGE, reason="时间早于首帧")
        state = self.state(asset)
        if state is IndexState.UNKNOWN:
            return IndexLookup(LookupStatus.NEEDS_INDEX, reason="索引不存在或指纹已变化")
        if state is IndexState.FAILED:
            return IndexLookup(LookupStatus.INVALID_TIMING, reason="索引构建失败")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ordinal,pts,tb_num,tb_den,duration_ticks,is_keyframe,"
                "pts_occurrence,timing_quality FROM frames WHERE asset_id=? ORDER BY ordinal",
                (asset.asset_id,),
            ).fetchall()
            end = conn.execute(
                "SELECT end_num,end_den FROM assets WHERE asset_id=?", (asset.asset_id,)
            ).fetchone()
        if not rows:
            return IndexLookup(LookupStatus.NEEDS_INDEX, reason="还没有已索引帧")
        entries = tuple(FrameIndexEntry(*row) for row in rows)
        source_times = tuple(entry.source_time for entry in entries)
        if any(time is None for time in source_times):
            return IndexLookup(LookupStatus.INVALID_TIMING, reason="已索引帧缺少 PTS")
        origin = source_times[0]
        assert origin is not None
        times = tuple(time - origin for time in source_times if time is not None)
        if any(b < a for a, b in zip(times, times[1:], strict=False)):
            return IndexLookup(LookupStatus.INVALID_TIMING, reason="PTS 下降")
        if state is IndexState.COMPLETE:
            assert end is not None and end[0] is not None and end[1] is not None
            if local_time >= Fraction(*end):
                return IndexLookup(LookupStatus.OUT_OF_RANGE, reason="时间已到公共末端")
        elif local_time >= times[-1]:
            # The last indexed frame's end is not confirmed; more equal-PTS
            # frames may arrive, so do not mark it as an exact time hit yet.
            return IndexLookup(LookupStatus.NEEDS_INDEX, reason="目标时间尚未被下一帧界定")
        ordinal = bisect_right(times, local_time) - 1
        return IndexLookup(LookupStatus.HIT, entries[ordinal])

    @staticmethod
    def first_frame_timeline(
        asset: AssetInfo, *, cancelled: Callable[[], bool] | None = None
    ) -> FrameTimeline:
        """Decode one real display frame so a queued long import can open immediately."""
        if cancelled and cancelled():
            raise IndexCancelled(f"已取消 {asset.label} 的首帧预览")
        try:
            with av.open(str(asset.path), mode="r") as container:
                stream = container.streams[asset.stream_index]
                if stream.type != "video":
                    raise IndexError(f"stream {asset.stream_index} 不是视频流")
                frame = next(iter(container.decode(stream)), None)
        except (av.error.FFmpegError, OSError) as exc:
            raise IndexError(f"读取 {asset.label} 首帧失败：{exc}") from exc
        if cancelled and cancelled():
            raise IndexCancelled(f"已取消 {asset.label} 的首帧预览")
        if frame is None or frame.pts is None:
            raise IndexError(f"{asset.label} 的首帧缺失或没有 PTS")
        tb = Fraction(frame.time_base or stream.time_base)
        entry = FrameIndexEntry(
            ordinal=0,
            pts=frame.pts,
            time_base_num=tb.numerator,
            time_base_den=tb.denominator,
            duration_ticks=int(frame.duration) if frame.duration and frame.duration > 0 else None,
            is_keyframe=bool(frame.key_frame),
            pts_occurrence=0,
            timing_quality="actual",
        )
        return FrameTimeline(asset.asset_id, (entry,), tb, True)

    def build(
        self,
        asset: AssetInfo,
        *,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int], None] | None = None,
        preview: Callable[[FrameTimeline], None] | None = None,
        chunk_size: int = 256,
    ) -> FrameTimeline:
        if self.state(asset) is IndexState.COMPLETE:
            return self.load(asset)
        if cancelled and cancelled():
            raise IndexCancelled(f"已取消 {asset.label} 的索引")
        reused = self._reuse_matching_index(asset)
        if reused is not None:
            return reused
        with self._connect() as conn:
            conn.execute("DELETE FROM frames WHERE asset_id = ?", (asset.asset_id,))
            conn.execute(
                "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, NULL, NULL, NULL)",
                (asset.asset_id, asset.fingerprint, self.SCHEMA_VERSION, IndexState.BUILDING.value),
            )
        entries: list[FrameIndexEntry] = []
        occurrences: Counter[int] = Counter()
        try:
            with av.open(str(asset.path), mode="r") as container:
                stream = container.streams[asset.stream_index]
                if stream.type != "video":
                    raise IndexError(f"stream {asset.stream_index} 不是视频流")
                for frame in container.decode(stream):
                    if cancelled and cancelled():
                        raise IndexCancelled(f"已取消 {asset.label} 的索引")
                    tb = Fraction(frame.time_base or stream.time_base)
                    pts = frame.pts
                    occurrence = occurrences[pts] if pts is not None else 0
                    if pts is not None:
                        occurrences[pts] += 1
                    entry = FrameIndexEntry(
                        ordinal=len(entries),
                        pts=pts,
                        time_base_num=tb.numerator,
                        time_base_den=tb.denominator,
                        duration_ticks=int(frame.duration)
                        if frame.duration and frame.duration > 0
                        else None,
                        is_keyframe=bool(frame.key_frame),
                        pts_occurrence=occurrence,
                        timing_quality="actual" if pts is not None else "unavailable",
                    )
                    entries.append(entry)
                    if len(entries) == 1 and preview is not None and entry.pts is not None:
                        # A single real frame can be shown at its exact start.
                        # The one-tick frontier is only a temporary coverage bound.
                        preview(FrameTimeline(asset.asset_id, (entry,), entry.time_base, True))
                    if len(entries) % chunk_size == 0:
                        self._write_entries(asset.asset_id, entries[-chunk_size:])
                        if progress:
                            progress(len(entries))
                        if preview is not None:
                            partial = self._preview_timeline(asset.asset_id, entries)
                            if partial is not None:
                                preview(partial)
            if not entries:
                raise IndexError(f"{asset.label} 没有可解码画面")
            tail = len(entries) % chunk_size
            if tail:
                self._write_entries(asset.asset_id, entries[-tail:])
            if progress:
                progress(len(entries))
            last = entries[-1]
            if last.pts is None:
                raise IndexError("最后一帧缺少 PTS，精确时间同步不可用")
            origin = entries[0].source_time
            last_start = last.source_time
            assert origin is not None and last_start is not None
            duration = (
                last.duration_ticks * last.time_base
                if last.duration_ticks is not None
                else self._estimate_last_duration(entries)
            )
            end_time = last_start - origin + duration
            try:
                timeline = FrameTimeline(asset.asset_id, tuple(entries), end_time)
            except ValueError as exc:
                raise IndexError(str(exc)) from exc
            with self._connect() as conn:
                conn.execute(
                    "UPDATE assets SET state=?, end_num=?, end_den=?, error=NULL WHERE asset_id=?",
                    (
                        IndexState.COMPLETE.value,
                        end_time.numerator,
                        end_time.denominator,
                        asset.asset_id,
                    ),
                )
            return timeline
        except IndexCancelled:
            self._mark(asset.asset_id, IndexState.PARTIAL, "用户取消")
            raise
        except (av.error.FFmpegError, OSError, IndexError, ValueError) as exc:
            self._mark(asset.asset_id, IndexState.FAILED, str(exc))
            if isinstance(exc, IndexError):
                raise
            raise IndexError(f"建立 {asset.label} 索引失败：{exc}") from exc

    @staticmethod
    def _preview_timeline(asset_id: str, entries: list[FrameIndexEntry]) -> FrameTimeline | None:
        # Do not expose the newest PTS group until a later timestamp defines
        # its boundary. A later duplicate PTS can still change time selection.
        if len(entries) < 2:
            return None
        last_start = entries[-1].source_time
        first_start = entries[0].source_time
        if last_start is None or first_start is None or last_start <= first_start:
            return None
        cut = len(entries) - 1
        while cut and entries[cut - 1].source_time == last_start:
            cut -= 1
        try:
            return FrameTimeline(asset_id, tuple(entries[:cut]), last_start - first_start, True)
        except ValueError:
            return None

    def _reuse_matching_index(self, asset: AssetInfo) -> FrameTimeline | None:
        """Copy metadata rows for another route of the same unchanged source."""
        with self._connect() as conn:
            source = conn.execute(
                "SELECT asset_id,end_num,end_den FROM assets "
                "WHERE fingerprint=? AND schema_version=? AND state=? "
                "AND asset_id<>? AND end_num IS NOT NULL AND end_den IS NOT NULL LIMIT 1",
                (
                    asset.fingerprint,
                    self.SCHEMA_VERSION,
                    IndexState.COMPLETE.value,
                    asset.asset_id,
                ),
            ).fetchone()
            if source is None:
                return None
            conn.execute("DELETE FROM frames WHERE asset_id=?", (asset.asset_id,))
            conn.execute(
                "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (
                    asset.asset_id,
                    asset.fingerprint,
                    self.SCHEMA_VERSION,
                    IndexState.COMPLETE.value,
                    source[1],
                    source[2],
                ),
            )
            conn.execute(
                "INSERT INTO frames SELECT ?,ordinal,pts,tb_num,tb_den,duration_ticks,"
                "is_keyframe,pts_occurrence,timing_quality FROM frames WHERE asset_id=?",
                (asset.asset_id, source[0]),
            )
        return self.load(asset)

    @staticmethod
    def _estimate_last_duration(entries: list[FrameIndexEntry]) -> Fraction:
        if len(entries) > 1:
            previous = entries[-2].source_time
            last = entries[-1].source_time
            if previous is not None and last is not None and last > previous:
                return last - previous
        return Fraction(1, 30)

    def _write_entries(self, asset_id: str, entries: list[FrameIndexEntry]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO frames VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        asset_id,
                        entry.ordinal,
                        entry.pts,
                        entry.time_base_num,
                        entry.time_base_den,
                        entry.duration_ticks,
                        int(entry.is_keyframe),
                        entry.pts_occurrence,
                        entry.timing_quality,
                    )
                    for entry in entries
                ),
            )

    def _mark(self, asset_id: str, state: IndexState, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE assets SET state=?, error=? WHERE asset_id=?",
                (state.value, error[:2000], asset_id),
            )

    def load(self, asset: AssetInfo) -> FrameTimeline:
        if self.state(asset) is not IndexState.COMPLETE:
            raise IndexError(f"{asset.label} 的完整索引不可用")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ordinal,pts,tb_num,tb_den,duration_ticks,is_keyframe,"
                "pts_occurrence,timing_quality FROM frames WHERE asset_id=? ORDER BY ordinal",
                (asset.asset_id,),
            ).fetchall()
            end = conn.execute(
                "SELECT end_num,end_den FROM assets WHERE asset_id=?", (asset.asset_id,)
            ).fetchone()
        assert end is not None
        entries = tuple(FrameIndexEntry(*row) for row in rows)
        return FrameTimeline(asset.asset_id, entries, Fraction(*end))
