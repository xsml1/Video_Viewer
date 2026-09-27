"""Stress real Windows OpenGL playback, random seeks, and bounded resources."""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import tempfile
import threading
import time
from pathlib import Path

from benchmark_playback import _rss_bytes
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from video_compare.domain.models import TransportState
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration-s", type=float, default=1800)
    parser.add_argument("--seek-every-s", type=float, default=2)
    parser.add_argument("--cache-mib", type=int, default=64)
    parser.add_argument("--routes", type=int, choices=(2, 4, 6), default=2)
    args = parser.parse_args()
    if args.duration_s <= 0 or args.seek_every_s <= 0 or args.cache_mib <= 0:
        parser.error("duration, seek interval, and cache size must be positive")
    video = args.video.resolve(strict=True)
    ffprobe = args.ffprobe.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        parser.error("output report already exists; choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    index = output.with_suffix(".sqlite3")
    if index.exists():
        parser.error("index path already exists; choose a new report path")
    window = MainWindow(index, ffprobe_path=ffprobe)
    window.show()
    window.load_files([video] * args.routes)
    rng = random.Random(20260925)
    samples: list[dict[str, int | float | None]] = []
    errors: list[str] = []
    groups = 0
    seeks = 0
    started = 0.0
    cpu_started = 0.0
    controller = None
    phase = "loading"
    first_timeout = max(20, args.routes * 10)
    first_deadline = time.monotonic() + first_timeout

    def fail(reason: str) -> None:
        errors.append(reason)
        finish()

    def on_group(group) -> None:
        nonlocal groups
        groups += 1
        if len(group.frames) != args.routes:
            fail("incomplete displayed frame group")
            return
        for asset_id, frame in group.frames.items():
            if frame.pts != window._timelines[asset_id].entries[frame.ordinal].pts:
                fail("displayed PTS differs from indexed source frame")
                return

    def sample() -> None:
        if phase != "running" or controller is None:
            return
        canvas = window.canvas
        if not isinstance(canvas, CompareCanvas) or not canvas.isValid():
            fail("native OpenGL canvas became unavailable")
            return
        image = canvas.grabFramebuffer()
        if image.isNull():
            fail("native OpenGL framebuffer is null")
            return
        row = {
            "elapsed_s": round(time.monotonic() - started, 3),
            "rss_bytes": _rss_bytes(),
            "cache_bytes": controller.cache.used_bytes,
            "cache_items": controller.cache.item_count,
            "result_queue": controller._results.qsize(),
            "worker_pending": sum(worker.pending_count for worker in controller._workers.values()),
            "threads": threading.active_count(),
            "groups": groups,
            "seeks": seeks,
            "framebuffer_width": image.width(),
            "framebuffer_height": image.height(),
            "dpr": canvas.devicePixelRatioF(),
        }
        samples.append(row)
        if row["cache_bytes"] > controller.cache.budget_bytes:
            fail("cache exceeded its byte budget")
        elif row["result_queue"] > controller._results.maxsize:
            fail("result queue exceeded its capacity")

    def seek() -> None:
        nonlocal seeks
        if phase != "running" or controller is None:
            return
        frame_count = window._timelines[controller.spec.reference_id].frame_count
        try:
            controller.seek_reference_frame(rng.randint(1, frame_count), resume=True)
        except (RuntimeError, ValueError) as exc:
            fail(f"random seek failed: {exc}")
            return
        seeks += 1

    def finish() -> None:
        nonlocal phase
        if phase == "finished":
            return
        elapsed = time.monotonic() - started if started else 0.0
        cpu_seconds = time.process_time() - cpu_started if cpu_started else 0.0
        phase = "finished"
        seek_timer.stop()
        sample_timer.stop()
        if controller is not None and controller.state is not TransportState.CLOSING:
            controller.pause()
        window.close()
        if controller is not None and not all(
            worker.join(timeout=0) for worker in controller._workers.values()
        ):
            errors.append("decoder worker survived window close")
        if not window._loader.join(timeout=0) or not window._screenshot_worker.join(timeout=0):
            errors.append("loader or screenshot worker survived window close")
        if not errors and (groups < 2 or seeks < 1):
            errors.append("not enough playback groups or random seeks were completed")
        payload = {
            "status": "failed" if errors else "measured",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "video": str(video),
            "renderer": "native visible QOpenGLWidget, framebuffer sampled every 5 seconds",
            "gpu_bytes": None,
            "routes": args.routes,
            "cache_budget_bytes": args.cache_mib * 1024 * 1024,
            "requested_duration_seconds": args.duration_s,
            "elapsed_seconds": round(elapsed, 3),
            "cpu_seconds": round(cpu_seconds, 3),
            "committed_groups": groups,
            "random_seeks": seeks,
            "samples": samples,
            "errors": errors,
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=output.parent, suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(
            f"{payload['status']}: {groups} groups, {seeks} seeks, {elapsed:.1f}s, report={output}"
        )
        app.exit(int(bool(errors)))

    def check_ready() -> None:
        nonlocal controller, phase, started, cpu_started
        if phase != "loading":
            return
        canvas = window.canvas
        if (
            canvas._snapshot is None
            or len(canvas._snapshot.frames) != args.routes
            or window._pending_add != 0
            or window._transport is None
        ):
            if time.monotonic() >= first_deadline:
                fail(
                    f"{args.routes} complete video frames did not load within "
                    f"{first_timeout} seconds"
                )
            return
        if not isinstance(canvas, CompareCanvas) or not canvas.isValid():
            fail("native OpenGL canvas did not initialize")
            return
        controller = window._transport
        controller.cache.budget_bytes = args.cache_mib * 1024 * 1024
        controller.group_ready.connect(on_group)
        controller.error_occurred.connect(fail)
        phase = "running"
        started = time.monotonic()
        cpu_started = time.process_time()
        controller.play()
        seek_timer.start(round(args.seek_every_s * 1000))
        sample_timer.start(5000)
        QTimer.singleShot(round(args.duration_s * 1000), finish)

    load_timer = QTimer()
    load_timer.setInterval(25)
    load_timer.timeout.connect(check_ready)
    load_timer.start()
    seek_timer = QTimer()
    seek_timer.timeout.connect(seek)
    sample_timer = QTimer()
    sample_timer.timeout.connect(sample)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
