"""Measure a real decoded, strictly synchronized loop without a GUI renderer."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import subprocess
import tempfile
import threading
import time
import tracemalloc
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QTimer

from video_compare.controllers.transport import TransportController
from video_compare.domain.models import SyncMode, TimelineSpec
from video_compare.media.index import FrameIndexRepository
from video_compare.media.probe import probe_video


def _rss_bytes() -> int | None:
    if os.name != "nt":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def _ffprobe_version(path: Path) -> str:
    result = subprocess.run(
        [str(path), "-version"], capture_output=True, text=True, check=True, timeout=10
    )
    return result.stdout.splitlines()[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["standard"], default="standard")
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=1800)
    parser.add_argument("--output", type=Path, default=Path("reports/benchmark.json"))
    parser.add_argument("--video", type=Path, help="Use one real video for every independent route")
    parser.add_argument("--routes", type=int, choices=(2, 4, 6), default=2)
    parser.add_argument("--cache-mib", type=int, default=64)
    parser.add_argument("--trace-alloc", action="store_true")
    args = parser.parse_args()
    if args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if args.cache_mib <= 0:
        parser.error("--cache-mib must be positive")
    if args.trace_alloc:
        tracemalloc.start(10)

    root = Path("tests/assets/generated").resolve()
    if args.video is None:
        if args.routes != 2:
            parser.error("--routes other than 2 requires --video")
        paths = [root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"]
    else:
        paths = [args.video.resolve()] * args.routes
    for path in paths:
        if not path.is_file():
            parser.error(f"missing generated fixture: {path}")
    app = QCoreApplication([])
    probe_start = time.perf_counter()
    assets = [probe_video(path, ffprobe_path=args.ffprobe, asset_id=uuid4().hex) for path in paths]
    probe_seconds = time.perf_counter() - probe_start
    index_start = time.perf_counter()
    repository = FrameIndexRepository(Path("reports/artifacts/benchmark-index.sqlite3"))
    timelines = {asset.asset_id: repository.build(asset) for asset in assets}
    index_seconds = time.perf_counter() - index_start
    spec = TimelineSpec(
        SyncMode.TIME, assets[0].asset_id, tuple(asset.asset_id for asset in assets)
    )
    controller = TransportController(
        {asset.asset_id: asset for asset in assets},
        timelines,
        spec,
        cache_bytes=args.cache_mib * 1024 * 1024,
    )

    phase = "initial"
    started = 0.0
    cpu_started = 0.0
    event_count = 0
    wrap_count = 0
    previous_time = Fraction(-1)
    sample_rows: list[dict[str, int | float | None]] = []
    errors: list[str] = []
    result_code = 0
    baseline_snapshot = None

    def sample() -> None:
        if phase != "running":
            return
        row = {
            "elapsed_s": round(time.perf_counter() - started, 3),
            "rss_bytes": _rss_bytes(),
            "cache_bytes": controller.cache.used_bytes,
            "cache_items": controller.cache.item_count,
            "result_queue": controller._results.qsize(),
            "worker_pending": sum(worker.pending_count for worker in controller._workers.values()),
            "threads": threading.active_count(),
        }
        if args.trace_alloc:
            row["python_traced_current_bytes"], row["python_traced_peak_bytes"] = (
                tracemalloc.get_traced_memory()
            )
        sample_rows.append(row)

    def finish() -> None:
        nonlocal phase, result_code
        if phase == "finished":
            return
        elapsed = time.perf_counter() - started if started else 0.0
        cpu_seconds = time.process_time() - cpu_started if cpu_started else 0.0
        sample()
        phase = "finished"
        controller.pause()
        if not controller.close():
            errors.append("decoder workers did not stop within close timeout")
        if event_count < 2 or (args.duration_s >= 60 and wrap_count < 1):
            errors.append("loop did not commit enough real frame groups")
        result_code = int(bool(errors))
        payload = {
            "status": "failed" if errors else "measured",
            "platform": platform.platform(),
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
            "logical_cpus": os.cpu_count(),
            "python": platform.python_version(),
            "pyside6": version("PySide6"),
            "pyav": version("av"),
            "ffprobe": _ffprobe_version(args.ffprobe),
            "scenario": (
                f"{len(assets)} routes, {assets[0].coded_width}x{assets[0].coded_height}, "
                f"{assets[0].average_rate} fps hint, "
                f"{', '.join(sorted({asset.codec_name or 'unknown' for asset in assets}))}, "
                f"{timelines[assets[0].asset_id].frame_count}-frame local loop"
            ),
            "renderer": "none (QCoreApplication transport/decoder benchmark)",
            "gpu_bytes": None,
            "cache_budget_bytes": controller.cache.budget_bytes,
            "source_files": [str(path) for path in paths],
            "probe_seconds": round(probe_seconds, 3),
            "index_seconds": round(index_seconds, 3),
            "requested_duration_seconds": args.duration_s,
            "elapsed_seconds": round(elapsed, 3),
            "cpu_seconds": round(cpu_seconds, 3),
            "committed_groups": event_count,
            "loop_wraps": wrap_count,
            "groups_per_second": round(event_count / elapsed, 3) if elapsed else 0,
            "samples": sample_rows,
            "errors": errors,
        }
        if args.trace_alloc and baseline_snapshot is not None:
            comparison = tracemalloc.take_snapshot().compare_to(baseline_snapshot, "lineno")
            payload["python_allocation_deltas"] = [
                {
                    "location": str(item.traceback[0]),
                    "bytes": item.size_diff,
                    "count": item.count_diff,
                }
                for item in comparison[:20]
            ]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=args.output.parent, suffix=".tmp", delete=False
            ) as output:
                temporary = Path(output.name)
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, args.output)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        print(
            f"{payload['status']}: {event_count} groups, {wrap_count} wraps, "
            f"{elapsed:.1f}s, report={args.output}"
        )
        app.quit()

    def on_error(reason: str) -> None:
        errors.append(reason)
        finish()

    def on_group(group) -> None:
        nonlocal phase, started, cpu_started, event_count, wrap_count, previous_time
        nonlocal baseline_snapshot
        for asset_id, frame in group.frames.items():
            expected = timelines[asset_id].entries[frame.ordinal]
            if frame.pts != expected.pts:
                on_error(f"frame identity mismatch for {asset_id}, ordinal={frame.ordinal}")
                return
        if phase == "initial":
            phase = "seek_end"
            controller.set_loop_start_from_displayed()
            QTimer.singleShot(
                0, lambda: controller.seek_reference_frame(timelines[spec.reference_id].frame_count)
            )
        elif phase == "seek_end":
            controller.set_loop_end_from_displayed()
            phase = "seek_start"
            QTimer.singleShot(0, lambda: controller.seek_reference_frame(1))
        elif phase == "seek_start":
            phase = "running"
            if args.trace_alloc:
                baseline_snapshot = tracemalloc.take_snapshot()
                tracemalloc.reset_peak()
            started = time.perf_counter()
            cpu_started = time.process_time()
            previous_time = group.requested_global_time
            controller.set_loop_enabled(True)
            controller.play()
            QTimer.singleShot(round(args.duration_s * 1000), finish)
        elif phase == "running":
            event_count += 1
            if group.requested_global_time < previous_time:
                wrap_count += 1
            previous_time = group.requested_global_time

    controller.group_ready.connect(on_group)
    controller.error_occurred.connect(on_error)
    sampler = QTimer()
    sampler.setInterval(5000)
    sampler.timeout.connect(sample)
    sampler.start()
    QTimer.singleShot(0, lambda: controller.seek_time(Fraction(0)))
    app.exec()
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
