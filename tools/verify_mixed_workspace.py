"""Verify real folder browsing, mixed media and mouse swaps on Windows OpenGL."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

import av
import numpy as np
import PySide6
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QKeyEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox
from source_digest import digest

from video_compare.domain.models import TransportState
from video_compare.ui.canvas_common import pane_boxes, pane_transform
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.main_window import MainWindow


def wait_until(predicate, description: str, timeout_s: float = 10) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(20)
    raise RuntimeError(f"timed out: {description}")


def source_id(rgb: np.ndarray) -> int:
    return sum(
        1 << bit
        for bit in range(16)
        if int(rgb[13 + (bit // 8) * 14, 13 + (bit % 8) * 14, 0]) >= 128
    )


def qimage_rgb(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(image.constBits(), dtype=np.uint8)
    return (
        raw.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
        .reshape(image.height(), image.width(), 3)
        .copy()
    )


def double_click(browser, path: Path) -> None:
    def visible_index() -> bool:
        index = browser.model.index(str(path))
        return index.isValid() and browser.tree.visualRect(index).height() > 0

    wait_until(visible_index, f"folder row visible: {path.name}")
    index = browser.model.index(str(path))
    browser.tree.scrollTo(index)
    point = browser.tree.visualRect(index).center()
    QTest.mouseClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseDClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QApplication.processEvents()


def verify_fullscreen(window, image_id: str, video_id: str, output: Path, report: dict) -> None:
    canvas = window.canvas
    transport = window._transport
    transport.pause()
    wait_until(
        lambda: window._current_display_snapshot() is not None,
        "complete group before full-screen entry",
    )
    snapshot = window._current_display_snapshot()
    canvas_size = canvas.size()
    order = canvas.display_order
    regions = canvas.view_regions
    workers = {key: id(worker) for key, worker in transport._workers.items()}
    sidebar_visible = window._sidebar.isVisible()
    QTest.mouseClick(window._fullscreen_button, Qt.MouseButton.LeftButton)

    def filled_screen() -> bool:
        screen = window.screen().geometry()
        return (
            window.isFullScreen()
            and window._workspace_fullscreen
            and canvas.size() == screen.size()
            and canvas.mapToGlobal(QPoint()) == screen.topLeft()
            and window._current_display_snapshot() is snapshot
        )

    wait_until(filled_screen, "same native canvas fills the full display")
    assert window.canvas is canvas and canvas.isValid()
    assert window._transport is transport
    assert {key: id(worker) for key, worker in transport._workers.items()} == workers
    assert canvas.display_order == order and canvas.view_regions == regions
    assert window._fullscreen_exit_button.isVisible()
    assert not window._fullscreen_button.isVisible()
    assert not window._sidebar.isVisible() and not window._transport_panel.isVisible()
    screen = window.screen().geometry()
    origin = canvas.mapToGlobal(QPoint())
    report["fullscreen"] = {
        "screen_geometry": [screen.x(), screen.y(), screen.width(), screen.height()],
        "canvas_geometry": [origin.x(), origin.y(), canvas.width(), canvas.height()],
        "device_pixel_ratio": canvas.devicePixelRatioF(),
        "entry_group_id": list(snapshot.group_id),
        "same_canvas_and_decoders": True,
    }
    canvas.setFocus()
    before_play = transport.displayed.reference_ordinal
    QTest.keyClick(canvas, Qt.Key.Key_Space)
    wait_until(
        lambda: transport.displayed.reference_ordinal > before_play,
        "Space starts real playback in full-screen",
    )
    QTest.keyClick(canvas, Qt.Key.Key_Space)
    assert transport.state is TransportState.PAUSED
    wait_until(
        lambda: window._current_display_snapshot() is not None,
        "complete paused native group in full-screen",
    )
    paused = transport.displayed.reference_ordinal
    QTest.qWait(100)
    assert transport.displayed.reference_ordinal == paused
    assert canvas._snapshot.frames[image_id] is snapshot.frames[image_id]
    for key, expected in ((Qt.Key.Key_Right, paused + 1), (Qt.Key.Key_Left, paused)):
        QTest.keyClick(canvas, key)
        wait_until(
            lambda ordinal=expected: (
                window._current_display_snapshot() is not None
                and window._current_display_snapshot().reference_ordinal == ordinal
            ),
            f"full-screen keyboard step to source frame {expected}",
        )
        assert source_id(canvas._snapshot.frames[video_id].rgb) == expected
        assert canvas._snapshot.frames[image_id] is snapshot.frames[image_id]
        assert transport.state is TransportState.PAUSED
    stable = window._current_display_snapshot()
    view_before = canvas.view_regions
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._active_assets(),
        stable,
        view_before,
        video_id,
        layout=canvas.layout_mode,
    )
    assert transform is not None
    content = transform.content_rect
    center = QPoint(round(content.x + content.width / 2), round(content.y + content.height / 2))
    wheel = QWheelEvent(
        QPointF(center),
        canvas.mapToGlobal(center),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas, wheel)
    assert canvas.view_regions[video_id].width_u < view_before[video_id].width_u
    assert len(set(canvas.view_regions.values())) == 1
    assert canvas._snapshot is stable
    report["fullscreen"]["viewport_after_ctrl_wheel"] = {
        key: {
            "center_u": value.center_u,
            "center_v": value.center_v,
            "width_u": value.width_u,
            "height_v": value.height_v,
        }
        for key, value in canvas.view_regions.items()
    }
    canvas.repaint()
    QTest.qWait(40)
    full_framebuffer = canvas.grabFramebuffer()
    assert full_framebuffer.save(str(output / "native-gl-fullscreen.png"))
    assert window.grab().save(str(output / "fullscreen-window-qt-widget-grab.png"))
    report["fullscreen"]["framebuffer_size"] = [
        full_framebuffer.width(),
        full_framebuffer.height(),
    ]
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    wait_until(
        lambda: (
            not window._workspace_fullscreen
            and not window.isFullScreen()
            and canvas.size() == canvas_size
        ),
        "Escape restores the normal canvas and toolbars",
    )
    assert window._fullscreen_button.isVisible()
    assert window._transport_panel.isVisible()
    assert window._sidebar.isVisible() == sidebar_visible
    assert window.canvas is canvas and canvas._snapshot is stable
    assert window._transport is transport
    assert {key: id(worker) for key, worker in transport._workers.items()} == workers
    zoomed_regions = canvas.view_regions
    QTest.keyClick(canvas, Qt.Key.Key_F11)
    wait_until(
        lambda: window._workspace_fullscreen and canvas.size() == screen.size(),
        "F11 enters full-screen again",
    )
    assert canvas._snapshot is stable and canvas.view_regions == zoomed_regions
    QTest.mouseClick(window._fullscreen_exit_button, Qt.MouseButton.LeftButton)
    wait_until(
        lambda: not window._workspace_fullscreen and canvas.size() == canvas_size,
        "top-right X restores normal workspace",
    )
    assert window.canvas is canvas and canvas._snapshot is stable
    assert canvas.display_order == order and canvas.view_regions == zoomed_regions
    assert window._sidebar.isVisible() == sidebar_visible
    assert window._transport_panel.isVisible()
    assert not window._fullscreen_exit_button.isVisible()
    canvas.reset_fit()
    report["checks"].append(
        "native full-screen fills display with same canvas/decoders/group; Space and "
        "exact arrow-key frame IDs, Ctrl-wheel zoom, Escape and top-right X restoration"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--video", type=Path, default=Path("tests/assets/generated/f05_h264_bframes.mp4")
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    workdir = output / "工作文件夹"
    child = workdir / "下一级"
    child.mkdir(parents=True)
    image_path = workdir / "静态 图像 [1].png"
    Image.new("RGB", (320, 180), (17, 67, 117)).save(image_path)
    video_path = child / "真实 B帧 [2].mp4"
    shutil.copy2(args.video.resolve(strict=True), video_path)
    source_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (image_path, video_path)
    }
    app = QApplication(sys.argv)
    window = MainWindow(
        output / "index.sqlite3",
        ffprobe_path=args.ffprobe.resolve(strict=True),
        settings_path=output / "settings.toml",
    )
    window.show()
    notices = []
    for kind in ("information", "warning", "critical"):
        setattr(QMessageBox, kind, lambda *args, _kind=kind: notices.append((_kind, args[1:])))
    report = {
        "status": "failed",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pyside6": PySide6.__version__,
        "pyav": av.__version__,
        "ffprobe": str(args.ffprobe.resolve()),
        "inputs": [str(image_path), str(video_path)],
        "source_hashes": source_hashes,
        "checks": [],
    }
    try:
        browser = window._file_browser
        assert browser.set_directory(workdir)
        double_click(browser, child)
        wait_until(lambda: browser.current_directory == child, "double-click folder enters child")
        QTest.mouseClick(browser.up_button, Qt.MouseButton.LeftButton)
        wait_until(lambda: browser.current_directory == workdir, "up button returns to parent")
        double_click(browser, image_path)
        wait_until(
            lambda: len(window._image_assets) == 1 and window.canvas._snapshot is not None,
            "double-click image adds real still",
        )
        double_click(browser, child)
        wait_until(lambda: browser.current_directory == child, "enter child again")
        double_click(browser, video_path)
        wait_until(
            lambda: (
                window._current_display_snapshot() is not None
                and len(window._current_display_snapshot().frames) == 2
                and window._pending_add == 0
            ),
            "double-click video adds real decoded route",
        )
        report["checks"].append("folder down/up and actual image/video double-click import")
        canvas = window.canvas
        assert isinstance(canvas, CompareCanvas) and canvas.isValid(), "native OpenGL unavailable"
        report["renderer"] = "native QOpenGLWidget"
        report["device_pixel_ratio"] = canvas.devicePixelRatioF()
        report["framebuffer_size"] = [canvas.width(), canvas.height()]
        first_order = canvas.display_order
        image_id, video_id = first_order
        still = canvas._snapshot.frames[image_id]
        transport = window._transport
        assert transport.spec.participants == (video_id,)
        assert transport.mapper.valid_range(transport.spec).end > 2
        transport.play()
        wait_until(lambda: transport.displayed.reference_ordinal >= 5, "real video playback")
        transport.pause()
        paused_frame = transport.displayed.reference_ordinal
        QTest.qWait(120)
        assert transport.displayed.reference_ordinal == paused_frame
        assert canvas._snapshot.frames[image_id] is still
        transport.step(1, 1, "frame")
        wait_until(
            lambda: (
                window._current_display_snapshot() is not None
                and window._current_display_snapshot().reference_ordinal == paused_frame + 1
            ),
            "complete native display at precise next frame",
        )
        assert source_id(canvas._snapshot.frames[video_id].rgb) == paused_frame + 1, (
            "decoded marker does not match the complete displayed step"
        )
        assert canvas._snapshot.frames[image_id] is still
        report["checks"].append("real B-frame playback/pause/step and immutable static image")

        snapshot = canvas._snapshot
        worker_ids = {key: id(worker) for key, worker in transport._workers.items()}
        regions = canvas.view_regions
        boxes = pane_boxes(
            canvas.width(),
            canvas.height(),
            first_order,
            window._active_assets(),
            snapshot,
            layout=canvas.layout_mode,
        )
        points = [
            QPoint(
                round(boxes[key].x + boxes[key].width / 2),
                round(boxes[key].y + boxes[key].height / 2),
            )
            for key in first_order
        ]
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=points[0])
        QTest.mouseMove(canvas, pos=(points[0] + points[1]) / 2, delay=20)
        QTest.mouseMove(canvas, pos=points[1], delay=20)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=points[1])
        assert canvas.display_order == tuple(reversed(first_order)), "mouse swap failed"
        assert window._transport is transport and canvas._snapshot is snapshot
        assert {key: id(worker) for key, worker in transport._workers.items()} == worker_ids
        assert canvas.view_regions == regions
        report["checks"].append(
            "actual mouse drag swaps panes without changing frames/decoders/view"
        )
        canvas.set_overlay_visible(True)
        canvas.repaint()
        QTest.qWait(60)
        framebuffer = canvas.grabFramebuffer()
        assert framebuffer.save(str(output / "native-gl-mixed-swapped.png"))
        overlay_pixels = qimage_rgb(framebuffer)
        overlay_count = int(
            np.count_nonzero(
                (overlay_pixels[:, :, 1] > 120)
                & (overlay_pixels[:, :, 0] < 60)
                & (overlay_pixels[:, :, 2] < 120)
            )
        )
        assert overlay_count > 20, "native framebuffer lacks source labels"
        report["native_overlay_pixels"] = overlay_count
        # QWidget.grab can omit QPainter overlays from a QOpenGLWidget child.
        # Keep the widget shell and actual framebuffer as separate evidence.
        assert window.grab().save(str(output / "window-qt-widget-grab.png"))
        report["window_capture"] = (
            "QWidget.grab captures the folder browser and controls; OpenGL labels "
            "are verified in the separate native-gl-mixed-swapped framebuffer"
        )

        button_clicks = []
        window._forward_button.clicked.connect(lambda: button_clicks.append(True))
        initial_link = window._linked_button.isChecked()
        for target in (
            window._forward_button,
            window._linked_button,
            window._time_input,
            browser.path_edit,
            browser.tree,
        ):
            transport.pause()
            target.setFocus()
            text_before = target.text() if isinstance(target, QLineEdit) else None
            QTest.keyClick(target, Qt.Key.Key_Space)
            assert transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
            repeat = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.NoModifier,
                " ",
                True,
                10,
            )
            QApplication.sendEvent(target, repeat)
            assert transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
            QTest.keyClick(target, Qt.Key.Key_Space)
            assert transport.state is TransportState.PAUSED
            assert window._linked_button.isChecked() == initial_link and not button_clicks
            if text_before is not None:
                assert target.text() == text_before
        report["checks"].append(
            "Space only toggles playback under button/input/tree focus; repeat ignored"
        )

        verify_fullscreen(window, image_id, video_id, output, report)

        transport.seek_reference_frame(18)
        wait_until(
            lambda: (
                window._current_display_snapshot() is not None
                and window._current_display_snapshot().reference_ordinal == 17
            ),
            "complete native display at UI frame 18",
        )
        pinned = window._current_display_snapshot()
        group_id = window.save_frame_screenshots(output / "frames")
        assert group_id == pinned.group_id, "frame screenshot did not pin the displayed group"
        view_id = window.save_view_screenshot(output / "view")
        assert view_id == group_id, "view screenshot did not pin the displayed group"
        transport.play()
        wait_until(
            lambda: (
                len(list((output / "frames").glob("*.json"))) == 2
                and len(list((output / "view").glob("*.json"))) == 1
            ),
            "mixed frame/view screenshot writes",
        )
        transport.pause()
        wait_until(
            lambda: window._current_display_snapshot() is not None,
            "complete native display after pausing screenshot playback",
        )
        for path in (output / "frames").glob("*.json"):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            assert metadata["media_kind"] == "mixed"
            assert metadata["group_id"] == list(group_id)
            assert metadata["reference_ui_frame"] == 18
            assert len(metadata["assets"]) == 2
            exported = np.asarray(Image.open(path.with_suffix(".png")).convert("RGB"))
            if metadata["export_asset_id"] == video_id:
                assert source_id(exported) == 17
            else:
                assert np.array_equal(exported, still.rgb)
        target = output / "mixed-comparison.png"
        assert window.export_comparison_image(target, layout="horizontal") is not None
        wait_until(target.is_file, "mixed comparison export")
        assert not target.with_suffix(".json").exists()
        exported = QImage(str(target))
        assert not exported.isNull() and exported.width() > 320
        report["checks"].append("pinned mixed PNG/JSON group IDs/pixels and comparison export")
        report["screenshot_group_id"] = list(group_id)
        report["export_size"] = [exported.width(), exported.height()]
        assert source_hashes == {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (image_path, video_path)
        }
        report["checks"].append("input media hashes unchanged")
        report["status"] = "passed"
    except (AssertionError, RuntimeError, OSError, ValueError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    finally:
        report["source_files"], report["source_digest"] = digest(Path("src").resolve())
        window.close()
        app.processEvents()
        (output / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
