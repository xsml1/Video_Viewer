"""Exercise freehand annotation, zoom anchoring, and export on real OpenGL."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from video_compare.domain.viewport import ViewRegion
from video_compare.ui.canvas_common import pane_transform
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.main_window import MainWindow


def color_hits(image: QImage, x: int, y: int, radius: int = 6) -> int:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    rows = raw.reshape(converted.height(), converted.bytesPerLine())
    rgb = rows[:, : converted.width() * 3].reshape(converted.height(), converted.width(), 3)
    patch = rgb[max(0, y - radius) : y + radius + 1, max(0, x - radius) : x + radius + 1]
    purple = np.array([191, 90, 242], dtype=np.int16)
    return int((np.abs(patch.astype(np.int16) - purple).max(axis=2) <= 40).sum())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    videos = [
        Path("tests/assets/generated/f05_h264_bframes.mp4").resolve(strict=True),
        Path("tests/assets/generated/f05_ffv1_oracle.mkv").resolve(strict=True),
    ]
    app = QApplication(sys.argv)
    window = MainWindow(output / "index.sqlite3", ffprobe_path=args.ffprobe.resolve(strict=True))
    window.show()
    window.load_files(videos)
    notices: list[str] = []
    QMessageBox.information = lambda _parent, _title, message: notices.append(message)
    QMessageBox.critical = lambda _parent, _title, message: notices.append(f"ERROR: {message}")
    started = time.monotonic()
    state = {"phase": "loading", "error": None, "preview_hits": 0}
    target = output / "native-gl-pen.png"

    def fail(reason: str) -> None:
        state["error"] = reason
        app.quit()

    def check() -> None:
        if time.monotonic() - started > 15:
            fail("timed out waiting for real GL annotation export")
            return
        canvas = window.canvas
        if state["phase"] == "loading":
            if canvas._snapshot is None or len(canvas._snapshot.frames) != 2:
                return
            if not isinstance(canvas, CompareCanvas) or not canvas.isValid():
                fail("native OpenGL canvas unavailable")
                return
            first = canvas.display_order[0]
            window.start_annotation_export(target)
            window._annotation_bar.set_shape("pen")
            window._annotation_bar.set_color("#bf5af2")
            canvas._set_region(first, ViewRegion(0.5, 0.5, 0.5, 0.5))
            transform = pane_transform(
                canvas.width(),
                canvas.height(),
                canvas.display_order,
                window._assets,
                canvas._snapshot,
                canvas.view_regions,
                first,
                layout=canvas.layout_mode,
            )
            if transform is None:
                fail("missing native pane transform")
                return
            positions = [
                QPoint(*map(round, transform.forward(value, value)))
                for value in (0.4, 0.45, 0.5, 0.55, 0.6)
            ]
            QTest.mousePress(
                canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, positions[0]
            )
            for point in positions[1:]:
                QTest.mouseMove(canvas, point)
            QTest.mouseRelease(
                canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, positions[-1]
            )
            if len(canvas.annotations) != 1 or canvas.annotations[0].kind != "pen":
                fail("mouse freehand path was not committed")
                return
            mark = canvas.annotations[0]
            canvas._set_region(first, ViewRegion(0.6, 0.5, 0.5, 0.5))
            after = pane_transform(
                canvas.width(),
                canvas.height(),
                canvas.display_order,
                window._assets,
                canvas._snapshot,
                canvas.view_regions,
                first,
                layout=canvas.layout_mode,
            )
            if after is None:
                fail("missing transformed native pane")
                return
            x, y = map(round, after.forward(*mark.start))
            state["preview_hits"] = color_hits(canvas.grabFramebuffer(), x, y)
            if state["preview_hits"] <= 0:
                fail("freehand stroke moved away from its source pixel after zoom")
                return
            if canvas.mask().contains(QPoint(0, 0)):
                fail("playback canvas corner is not rounded")
                return
            window._annotation_bar.done_button.click()
            state["phase"] = "exporting"
            return
        if state["phase"] == "exporting":
            if not target.is_file() or window._saving_annotated_export:
                return
            if canvas.annotations or window._annotation_bar.isVisible():
                fail("annotations remain after successful export")
                return
            image = QImage(str(target))
            if image.isNull():
                fail("exported image cannot be loaded")
                return
            purple = np.array([191, 90, 242], dtype=np.int16)
            converted = image.convertToFormat(QImage.Format.Format_RGB888)
            raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
            rgb = raw.reshape(converted.height(), converted.bytesPerLine())[
                :, : converted.width() * 3
            ].reshape(converted.height(), converted.width(), 3)
            hits = int((np.abs(rgb.astype(np.int16) - purple).max(axis=2) <= 40).sum())
            if hits <= 30:
                fail("exported image lacks freehand stroke")
                return
            report = {
                "status": "passed",
                "renderer": "native QOpenGLWidget",
                "framebuffer": [canvas.width(), canvas.height()],
                "dpr": canvas.devicePixelRatioF(),
                "source_group_id": list(canvas._snapshot.group_id),
                "preview_purple_hits_near_source_point": state["preview_hits"],
                "export_purple_pixels": hits,
                "export_size": [image.width(), image.height()],
                "json_created": target.with_suffix(".json").exists(),
            }
            (output / "result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            state["phase"] = "finished"
            app.quit()

    timer = QTimer()
    timer.setInterval(25)
    timer.timeout.connect(check)
    timer.start()
    app.exec()
    timer.stop()
    window.close()
    if state["error"]:
        print(f"GL annotation verification failed: {state['error']}", file=sys.stderr)
        return 1
    print(f"GL annotation verification passed: {output / 'result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
