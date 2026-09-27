"""Verify pane-local annotations on the native OpenGL canvas and export."""

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

from video_compare.ui.canvas_common import pane_transform
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.main_window import MainWindow


def pixels(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    return (
        raw.reshape(converted.height(), converted.bytesPerLine())[:, : converted.width() * 3]
        .reshape(converted.height(), converted.width(), 3)
        .copy()
    )


def content(canvas, window, asset_id):
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._active_assets(),
        canvas._snapshot,
        canvas.view_regions,
        asset_id,
        layout=canvas.layout_mode,
    )
    if transform is None:
        raise RuntimeError(f"missing pane transform: {asset_id}")
    rect = transform.content_rect
    return rect, lambda u, v: QPoint(
        round(rect.x + rect.width * u), round(rect.y + rect.height * v)
    )


def crop(data: np.ndarray, rect) -> np.ndarray:
    return data[round(rect.y) : round(rect.bottom), round(rect.x) : round(rect.right)]


def draw(canvas, start: QPoint, end: QPoint, *, pen: bool) -> None:
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    if pen:
        for fraction in (0.25, 0.35, 0.45):
            point = QPoint(
                round(start.x() + (end.x() - start.x()) * fraction / 0.5),
                round(start.y() + (end.y() - start.y()) * fraction / 0.5),
            )
            QTest.mouseMove(canvas, point)
    else:
        QTest.mouseMove(canvas, end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
    QMessageBox.information = lambda *_args: None
    QMessageBox.critical = lambda *_args: None
    state = {"done": False, "error": None}
    started = time.monotonic()
    target = output / "local-annotations.png"

    def check() -> None:
        if time.monotonic() - started > 20:
            state["error"] = "timed out"
            app.quit()
            return
        canvas = window.canvas
        if state["done"]:
            if not target.is_file() or window._saving_annotated_export:
                return
            image = QImage(str(target))
            if image.isNull():
                state["error"] = "export image is invalid"
            else:
                data = pixels(image)
                purple = np.array([191, 90, 242], dtype=np.int16)
                red = np.array([255, 59, 48], dtype=np.int16)
                split = image.width() // 2
                red_left = int(
                    (np.abs(data[:, :split].astype(np.int16) - red).max(axis=2) < 40).sum()
                )
                purple_right = int(
                    (np.abs(data[:, split:].astype(np.int16) - purple).max(axis=2) < 40).sum()
                )
                if red_left < 20 or purple_right < 20:
                    state["error"] = (
                        f"export lacks local strokes: red={red_left}, purple={purple_right}"
                    )
                else:
                    report = {
                        "status": "passed",
                        "renderer": "native QOpenGLWidget",
                        "source_group_id": list(canvas._snapshot.group_id),
                        "local_annotation_count": 2,
                        "export_red_first_pane_pixels": red_left,
                        "export_purple_second_pane_pixels": purple_right,
                        "export_size": [image.width(), image.height()],
                    }
                    (output / "result.json").write_text(
                        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
            app.quit()
            return
        if canvas._snapshot is None or len(canvas._snapshot.frames) != 2:
            return
        if not isinstance(canvas, CompareCanvas) or not canvas.isValid():
            state["error"] = "native OpenGL canvas unavailable"
            app.quit()
            return
        try:
            window.start_annotation_export(target, layout="horizontal")
            bar = window._annotation_bar
            bar.link_checkbox.setChecked(False)
            first, second = canvas.display_order
            first_rect, first_point = content(canvas, window, first)
            second_rect, second_point = content(canvas, window, second)
            canvas.repaint()
            before = pixels(canvas.grabFramebuffer())
            bar.set_shape("rect")
            bar.set_color("#ff3b30")
            draw(canvas, first_point(0.2, 0.2), first_point(0.6, 0.6), pen=False)
            if len(canvas.annotations) != 1 or canvas.annotations[0].target_asset_id != first:
                raise RuntimeError("rectangle was not restricted to the first pane")
            canvas.repaint()
            after_rect = pixels(canvas.grabFramebuffer())
            if not np.array_equal(crop(before, second_rect), crop(after_rect, second_rect)):
                raise RuntimeError("first-pane rectangle changed the second GL pane")
            bar.set_shape("pen")
            bar.set_color("#bf5af2")
            draw(canvas, second_point(0.2, 0.2), second_point(0.6, 0.6), pen=True)
            if len(canvas.annotations) != 2 or canvas.annotations[1].target_asset_id != second:
                raise RuntimeError("pen was not restricted to the second pane")
            canvas.repaint()
            after_pen = pixels(canvas.grabFramebuffer())
            if not np.array_equal(crop(after_rect, first_rect), crop(after_pen, first_rect)):
                raise RuntimeError("second-pane pen changed the first GL pane")
            bar.done_button.click()
            state["done"] = True
        except RuntimeError as exc:
            state["error"] = str(exc)
            app.quit()

    timer = QTimer()
    timer.setInterval(25)
    timer.timeout.connect(check)
    timer.start()
    app.exec()
    timer.stop()
    window.close()
    if state["error"]:
        print(f"GL annotation scope verification failed: {state['error']}", file=sys.stderr)
        return 1
    print(f"GL annotation scope verification passed: {output / 'result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
