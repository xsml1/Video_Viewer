"""Show real decoded fixture frames on the native Windows OpenGL canvas."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from video_compare.ui.canvas_common import pane_transform
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", required=True, type=Path)
    parser.add_argument("--output", default=Path("reports/artifacts"), type=Path)
    parser.add_argument("videos", nargs="*", type=Path)
    args = parser.parse_args()
    if args.videos and len(args.videos) != 2:
        parser.error("pass exactly two videos or use the generated default pair")
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path("tests/assets/generated").resolve()
    paths = args.videos or [root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"]
    app = QApplication(sys.argv)
    window = MainWindow(
        args.output / "gl-index.sqlite3",
        ffprobe_path=args.ffprobe,
        settings_path=args.output / "settings.toml",
    )
    if isinstance(window.canvas, CompareCanvas):
        window.canvas.render_failed.connect(lambda reason: print(f"GL render failed: {reason}"))
    window.show()
    # 画面角落的名称/帧信息会覆盖像素，逐像素验证前关闭（导出与截图不受影响）。
    window.canvas.set_overlay_visible(False)
    window.load_files(paths)
    state = {"exit": 0}
    deadline = time.monotonic() + 15
    old_exports = set(args.output.glob("compare_*_view.json")) if args.output.exists() else set()
    exported_group = None
    six_size = None
    held_frame = None
    detached_id = None

    def capture_two() -> None:
        canvas = window.canvas
        if canvas._snapshot is None or len(canvas._snapshot.frames) != 2:
            if time.monotonic() >= deadline:
                print("2-pane complete frame group timed out")
                state["exit"] = 1
                app.quit()
            else:
                QTimer.singleShot(50, capture_two)
            return
        if not isinstance(canvas, CompareCanvas) or not canvas.isValid():
            print("OpenGL canvas unavailable; software fallback active")
            state["exit"] = 1
            app.quit()
            return
        image = canvas.grabFramebuffer()
        if image.isNull():
            print("2-pane framebuffer is null")
            state["exit"] = 1
            app.quit()
            return
        args.output.mkdir(parents=True, exist_ok=True)
        image.save(str(args.output / "m0_gl_two.png"))
        print(
            f"2-pane framebuffer: {image.width()}x{image.height()} DPR={canvas.devicePixelRatioF()}"
        )
        window._pixel_mode_combo.setCurrentIndex(1)
        pixel_image = canvas.grabFramebuffer().convertToFormat(QImage.Format.Format_RGB888)
        asset_id = canvas._order[0]
        transform = pane_transform(
            canvas.width(),
            canvas.height(),
            canvas._order,
            window._assets,
            canvas._snapshot,
            canvas.view_regions,
            asset_id,
            pixel_zoom=1.0,
            device_pixel_ratio=canvas.devicePixelRatioF(),
        )
        assert transform is not None
        content = transform.content_rect
        dpr = canvas.devicePixelRatioF()
        x, y = round(content.x * dpr), round(content.y * dpr)
        frame = canvas._snapshot.frames[asset_id].rgb
        width, height = frame.shape[1], frame.shape[0]
        pixels = np.frombuffer(pixel_image.constBits(), dtype=np.uint8)
        pixels = pixels.reshape(pixel_image.height(), pixel_image.bytesPerLine())
        pixels = pixels[:, : pixel_image.width() * 3].reshape(
            pixel_image.height(), pixel_image.width(), 3
        )
        if not np.array_equal(pixels[y : y + height, x : x + width], frame):
            print("Native OpenGL 100% pixel crop differs from decoded RGB frame")
            state["exit"] = 1
            app.quit()
            return
        pixel_image.save(str(args.output / "m5_gl_pixel_100.png"))
        window._pixel_mode_combo.setCurrentIndex(0)
        window.load_files(paths * 2)
        QTimer.singleShot(50, capture_six)

    def capture_six() -> None:
        nonlocal exported_group, six_size
        canvas = window.canvas
        if canvas._snapshot is None or len(canvas._snapshot.frames) != 6:
            if time.monotonic() >= deadline:
                print("6-pane complete frame group timed out")
                state["exit"] = 1
                app.quit()
            else:
                QTimer.singleShot(50, capture_six)
            return
        assert isinstance(canvas, CompareCanvas)
        image = canvas.grabFramebuffer()
        if image.isNull() or len(canvas._snapshot.frames) != 6:
            print("6-pane framebuffer or frame group invalid")
            state["exit"] = 1
        else:
            image.save(str(args.output / "m0_gl_six.png"))
            window.grab().save(str(args.output / "window_six.png"))
            six_size = [image.width(), image.height()]
            size = f"{image.width()}x{image.height()}"
            print(f"6-pane framebuffer: {size} DPR={canvas.devicePixelRatioF()}")
            group = canvas._snapshot
            transport = window._transport
            first_id = tuple(window._assets)[0]
            window._file_list.setCurrentRow(0)
            window._move_selected(1)
            window._toggle_maximize_asset(first_id)
            if (
                window._transport is not transport
                or canvas._snapshot is not group
                or canvas._order != (first_id,)
                or len(canvas._snapshot.frames) != 6
            ):
                print("Native maximize/reorder changed the transport or complete frame group")
                state["exit"] = 1
                app.quit()
                return
            canvas.grabFramebuffer().save(str(args.output / "m5_gl_maximized.png"))
            window._toggle_maximize_asset(first_id)
            if len(canvas._order) != 6 or canvas._snapshot is not group:
                print("Native grid restore lost the complete frame group")
                state["exit"] = 1
                app.quit()
                return
            exported_group = window.save_view_screenshot(args.output)
            if exported_group is None:
                print("GL composite screenshot request failed")
                state["exit"] = 1
                app.quit()
                return
            QTimer.singleShot(50, verify_export)
            return
        app.quit()

    def start_detached() -> None:
        nonlocal held_frame, detached_id
        detached_id = next(
            key for key in window._assets if key != window._transport.spec.reference_id
        )
        held_frame = window._transport.displayed.frames[detached_id]
        window._file_list.setCurrentRow(tuple(window._assets).index(detached_id))
        window._toggle_time_participation()
        QTimer.singleShot(50, verify_detached)

    def verify_detached() -> None:
        core = window._transport.displayed
        display = window._current_display_snapshot()
        if core is None or len(core.frames) != 5 or display is None:
            if time.monotonic() >= deadline:
                print("Native detached frame group timed out")
                state["exit"] = 1
                app.quit()
            else:
                QTimer.singleShot(50, verify_detached)
            return
        if (
            display.frames[detached_id] is not held_frame
            or display.boundary_states[detached_id] != "detached"
        ):
            print("Native detached pane did not hold its real frame")
            state["exit"] = 1
            app.quit()
            return
        window.canvas.grabFramebuffer().save(str(args.output / "m5_gl_detached.png"))
        window._toggle_time_participation()
        QTimer.singleShot(50, verify_rejoined)

    def verify_rejoined() -> None:
        core = window._transport.displayed
        if core is None or len(core.frames) != 6:
            if time.monotonic() >= deadline:
                print("Native detached route rejoin timed out")
                state["exit"] = 1
                app.quit()
            else:
                QTimer.singleShot(50, verify_rejoined)
            return
        if window.canvas._snapshot is not core:
            print("Native rejoin did not restore one complete frame group")
            state["exit"] = 1
        app.quit()

    def verify_export() -> None:
        new_exports = set(args.output.glob("compare_*_view.json")) - old_exports
        if not new_exports:
            if time.monotonic() >= deadline:
                print("GL composite screenshot timed out")
                state["exit"] = 1
                app.quit()
            else:
                QTimer.singleShot(50, verify_export)
            return
        sidecar = next(iter(new_exports))
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        png = sidecar.with_suffix(".png")
        if (
            data["group_id"] != list(exported_group)
            or data["png_size_px"] != six_size
            or not png.is_file()
        ):
            print("GL screenshot sidecar and complete frame group do not match")
            state["exit"] = 1
        else:
            print(f"GL composite screenshot: {png.name}, group={exported_group}")
        if state["exit"]:
            app.quit()
        else:
            start_detached()

    QTimer.singleShot(50, capture_two)
    app.exec()
    return state["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
