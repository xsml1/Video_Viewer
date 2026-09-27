"""Cancel a real long H.264 index through the GUI loader and verify cleanup."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QApplication

from video_compare.ui.main_window import MainWindow


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/artifacts"))
    args = parser.parse_args()
    root = Path("tests/assets/generated").resolve()
    root.mkdir(parents=True, exist_ok=True)
    video = root / "f18_long_index_5min.mp4"
    if not video.exists():
        result = subprocess.run(
            [
                str(args.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=640x360:rate=30",
                "-frames:v",
                "9000",
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-g",
                "60",
                "-bf",
                "3",
                str(video),
            ],
            capture_output=True,
            check=False,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    original_hash = _sha256(video)
    args.output.mkdir(parents=True, exist_ok=True)
    index_path = args.output / "long-cancel-index.sqlite3"
    if index_path.exists():
        parser.error(f"index already exists; use a fresh output directory: {index_path}")

    app = QApplication(sys.argv)
    window = MainWindow(index_path, ffprobe_path=args.ffprobe, software=True)
    entered = Event()
    written_frames = 0
    original_write = window._repository._write_entries

    def record_write(asset_id, entries) -> None:
        nonlocal written_frames
        original_write(asset_id, entries)
        written_frames += len(entries)
        entered.set()

    window._repository._write_entries = record_write
    window.show()
    started = time.perf_counter()
    window.load_files([video])
    deadline = started + 20
    while not entered.is_set() and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)
    if not entered.is_set():
        raise AssertionError(f"Real index did not reach first chunk: {window._status.text()}")
    if window._pending_add == 0:
        raise AssertionError(
            "Index completed before cancellation; test did not exercise inflight work"
        )
    cancel_started = time.perf_counter()
    window.close()
    app.processEvents()
    cancel_seconds = time.perf_counter() - cancel_started
    if window._loader._thread.is_alive():
        raise AssertionError("Asset loader survived window close")
    if _sha256(video) != original_hash:
        raise AssertionError("Input video was modified by indexing/cancellation")
    with sqlite3.connect(index_path) as database:
        states = [row[0] for row in database.execute("SELECT state FROM assets")]
    if states != ["partial"]:
        raise AssertionError(f"Cancelled real index was not marked partial: {states}")
    print(
        f"Long index cancelled after {written_frames} real frames; "
        f"close={cancel_seconds:.3f}s; input_sha256={original_hash}; state=partial"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
