"""Packaged-process smoke check using the same window and real media pipeline.

The check runs inside the launched application: import two real videos, locate a
source frame, save the annotated view, verify the adaptive layout, then export
the visible comparison image and confirm the success notice was raised.
"""

from __future__ import annotations

import json
import time
from bisect import bisect_right
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from video_compare.domain.models import SyncMode
from video_compare.ui.canvas_common import pane_boxes, pane_transform
from video_compare.ui.main_window import MainWindow


class _FullscreenCheck:
    """A timer-driven smoke check using the shipped buttons and real frame group."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.canvas = window.canvas
        self.transport = window._transport
        self.snapshot = window._current_display_snapshot()
        self.workers = dict(self.transport._workers) if self.transport is not None else {}
        self.window_size = window.size()
        self.canvas_size = self.canvas.size()
        self.order = self.canvas.display_order
        self.regions = self.canvas.view_regions
        self.visibility = [
            (widget, widget.isVisible())
            for widget in (window._top_bar, window._sidebar, window._transport_panel)
        ]

    def start(self) -> None:
        self.window._fullscreen_button.click()

    def _check_identity(self) -> None:
        window = self.window
        if (
            window.canvas is not self.canvas
            or window._transport is not self.transport
            or window._current_display_snapshot() is not self.snapshot
            or self.canvas.display_order != self.order
            or self.canvas.view_regions != self.regions
        ):
            raise RuntimeError("full-screen changed the canvas, complete frame group or view")
        if self.transport is not None and self.transport._workers != self.workers:
            raise RuntimeError("full-screen rebuilt decoder workers")

    def entered(self) -> bool:
        window = self.window
        if (
            not window.isFullScreen()
            or self.canvas.size() != window.size()
            or window._current_display_snapshot() is None
        ):
            return False
        self._check_identity()
        if (
            not window._workspace_fullscreen
            or not window._fullscreen_exit_button.isVisible()
            or any(widget.isVisible() for widget, _visible in self.visibility)
        ):
            raise RuntimeError("full-screen did not hide controls or show its exit button")
        return True

    def exit(self) -> None:
        self.window._fullscreen_exit_button.click()

    def restored(self) -> bool:
        window = self.window
        if (
            window.isFullScreen()
            or window.size() != self.window_size
            or self.canvas.size() != self.canvas_size
            or window._current_display_snapshot() is None
        ):
            return False
        self._check_identity()
        if (
            window._workspace_fullscreen
            or window._fullscreen_exit_button.isVisible()
            or any(widget.isVisible() != visible for widget, visible in self.visibility)
        ):
            raise RuntimeError("full-screen exit did not restore the normal controls")
        return True


def run_self_test(app: QApplication, window: MainWindow, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    known = set(output_dir.glob("compare_*_view.json"))
    export_path = output_dir / "selftest_compare.png"
    export_path.unlink(missing_ok=True)
    export_path.with_suffix(".json").unlink(missing_ok=True)
    deadline = time.monotonic() + 60
    state: dict[str, object] = {"phase": "load", "group": None, "view": None, "gap": 0.0}
    exit_code = 1
    dialogs: list[tuple[str, str]] = []
    for name in ("information", "warning", "critical"):
        setattr(
            QMessageBox,
            name,
            staticmethod(
                lambda _parent, title, text, _name=name, **_kwargs: dialogs.append(
                    (_name, f"{title}::{text}")
                )
            ),
        )
    timer = QTimer(window)
    timer.setInterval(50)

    def fail(reason: str) -> None:
        nonlocal exit_code
        print(f"SELF_TEST_FAILED: {reason}", flush=True)
        exit_code = 1
        timer.stop()
        window.close()
        app.quit()

    def start_export() -> None:
        order = window.canvas.display_order
        boxes = pane_boxes(
            window.canvas.width(),
            window.canvas.height(),
            order,
            window._active_assets(),
            window.canvas._snapshot,
        )
        first, second = boxes[order[0]], boxes[order[1]]
        if abs(first.y - second.y) < 0.01:
            gap = second.x - first.right
        else:
            upper, lower = sorted((first, second), key=lambda box: box.y)
            gap = lower.y - upper.bottom
        if not 0 <= gap <= 12:
            fail(f"pane gap is not packed: {gap}")
            return
        state["gap"] = gap
        if window.windowIcon().isNull():
            fail("application icon was not applied")
            return
        if window.export_comparison_image(export_path, layout="window", image_format="PNG") is None:
            fail(f"comparison export request failed: {window._status.text()}")
            return
        state["phase"] = "compare"

    def verify_export() -> None:
        nonlocal exit_code
        # The success notice is raised by the window's own drain timer, which may
        # run one tick after this check, so wait for it instead of racing the file.
        if not any(name == "information" and str(export_path) in text for name, text in dialogs):
            return
        image = QImage(str(export_path))
        if export_path.with_suffix(".json").exists():
            fail("comparison export must not write a JSON sidecar")
            return
        expected = expected_export_size()
        if image.isNull() or (image.width(), image.height()) != expected:
            fail(f"comparison export size mismatch: {image.width()}x{image.height()} vs {expected}")
            return
        print(
            f"SELF_TEST_OK: {state['view']} group={state['group']} "
            f"layout_gap={state['gap']:.1f} export={image.width()}x{image.height()} "
            f"icon=True fullscreen=True normal_restore=True notices={len(dialogs)}",
            flush=True,
        )
        exit_code = 0
        timer.stop()
        window.close()
        app.quit()

    def expected_export_size() -> tuple[int, int]:
        """Visible tile sizes in device pixels, arranged into rows."""
        canvas = window.canvas
        dpr = max(1.0, canvas.devicePixelRatioF())
        order = canvas.display_order
        assets = window._active_assets()
        boxes = pane_boxes(
            canvas.width(),
            canvas.height(),
            order,
            assets,
            canvas._snapshot,
            layout=canvas.layout_mode,
        )
        rows: dict[float, list[tuple[int, int]]] = {}
        for asset_id in order:
            transform = pane_transform(
                canvas.width(),
                canvas.height(),
                order,
                assets,
                canvas._snapshot,
                canvas.view_regions,
                asset_id,
                pixel_zoom=canvas.pixel_zoom,
                device_pixel_ratio=dpr,
                layout=canvas.layout_mode,
            )
            if transform is None:
                continue
            content = transform.content_rect
            box = boxes[asset_id]
            rows.setdefault(round(box.y, 1), []).append(
                (max(1, round(content.width * dpr)), max(1, round(content.height * dpr)))
            )
        width = max(sum(tile[0] for tile in row) + 6 * (len(row) - 1) for row in rows.values())
        height = sum(max(tile[1] for tile in row) for row in rows.values()) + 6 * (len(rows) - 1)
        return width, height

    def check() -> None:
        phase = state["phase"]
        if time.monotonic() >= deadline:
            fail(f"timeout at {phase}: {window._status.text()}")
            return
        if phase == "load":
            if len(window._active_assets()) != 2:
                if window._pending_add == 0 and not window._image_pending:
                    fail(f"import failed: {window._status.text()}")
                return
            snapshot = window._current_display_snapshot()
            if snapshot is None or len(snapshot.frames) != 2:
                return
            if window._pending_add or window._image_pending:
                return
            if window._transport is None:
                fail("video self-test needs at least one real video")
                return
            state["fullscreen"] = _FullscreenCheck(window)
            state["fullscreen"].start()
            state["phase"] = "fullscreen"
        elif phase in {"fullscreen", "normal"}:
            fullscreen = state["fullscreen"]
            try:
                if phase == "fullscreen":
                    if fullscreen.entered():
                        fullscreen.exit()
                        state["phase"] = "normal"
                elif fullscreen.restored():
                    window._transport.seek_reference_frame(2)
                    state["phase"] = "seek"
            except RuntimeError as exc:
                fail(str(exc))
        elif phase == "seek":
            snapshot = window._current_display_snapshot()
            if snapshot is None or snapshot.reference_ordinal != 1:
                return
            spec = window._transport.spec
            for asset_id, frame in snapshot.frames.items():
                if window._active_assets()[asset_id].media_kind == "image":
                    if frame is not window._image_frames[asset_id]:
                        fail("static image changed during video seek")
                        return
                    continue
                entries = window._timelines[asset_id].entries
                if spec.mode is SyncMode.TIME:
                    # Containers quantize PTS differently (e.g. MKV 33 ms vs TS
                    # 1/30 s). Time synchronization need not select equal ordinals.
                    source_time = entries[0].source_time + snapshot.requested_global_time
                    source_time += spec.time_offsets.get(asset_id, 0)
                    expected = (
                        bisect_right([entry.source_time for entry in entries], source_time) - 1
                    )
                else:
                    expected = 1 + spec.frame_offsets.get(asset_id, 0)
                if frame.ordinal != expected or frame.pts != entries[expected].pts:
                    fail("seek returned an incorrect source frame or PTS")
                    return
            group = window.save_view_screenshot(output_dir)
            if group is None:
                fail(f"screenshot request failed: {window._status.text()}")
                return
            state["group"] = group
            state["phase"] = "screenshot"
        elif phase == "screenshot":
            created = set(output_dir.glob("compare_*_view.json")) - known
            if not created:
                return
            sidecar = next(iter(created))
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            png = sidecar.with_suffix(".png")
            if (
                metadata["group_id"] != list(state["group"])
                or metadata["reference_ui_frame"] != 2
                or len(metadata["assets"]) != 2
                or not png.is_file()
                or png.stat().st_size == 0
            ):
                fail("saved PNG/JSON does not match the sought complete group")
                return
            state["view"] = str(png)
            start_export()
        elif phase == "compare":
            if not export_path.is_file():
                return
            verify_export()
        else:  # pragma: no cover - defensive
            fail(f"unknown phase {phase}")

    timer.timeout.connect(check)
    timer.start()
    app.exec()
    return exit_code


def run_image_self_test(app: QApplication, window: MainWindow, output_dir: Path) -> int:
    """Exercise still import, the active canvas, and export in a launched process."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "image_compare.png"
    if target.exists():
        print(f"IMAGE_SELF_TEST_FAILED: output already exists: {target}", flush=True)
        return 1
    deadline = time.monotonic() + 60
    phase = "load"
    fullscreen: _FullscreenCheck | None = None
    result_code = 1
    timer = QTimer(window)
    timer.setInterval(50)
    notices: list[str] = []
    QMessageBox.information = staticmethod(lambda _parent, _title, message: notices.append(message))

    def fail(reason: str) -> None:
        nonlocal result_code
        print(f"IMAGE_SELF_TEST_FAILED: {reason}", flush=True)
        result_code = 1
        timer.stop()
        window.close()
        app.quit()

    def check() -> None:
        nonlocal phase, result_code, fullscreen
        if time.monotonic() > deadline:
            fail(f"timeout at {phase}: {window._status.text()}")
            return
        if phase == "load":
            if len(window._image_assets) != 2:
                if not window._image_pending:
                    fail(f"import failed: {window._status.text()}")
                return
            snapshot = window._current_display_snapshot()
            if snapshot is None or len(snapshot.frames) != 2:
                return
            if any(asset.media_kind != "image" for asset in window._image_assets.values()):
                fail("video asset entered the image canvas")
                return
            fullscreen = _FullscreenCheck(window)
            fullscreen.start()
            phase = "fullscreen"
        elif phase in {"fullscreen", "normal"}:
            try:
                if phase == "fullscreen":
                    if fullscreen.entered():
                        fullscreen.exit()
                        phase = "normal"
                elif fullscreen.restored():
                    if window.export_comparison_image(target) is None:
                        fail(f"export request failed: {window._status.text()}")
                        return
                    phase = "export"
            except RuntimeError as exc:
                fail(str(exc))
        elif phase == "export":
            if not target.is_file() or not notices:
                return
            image = QImage(str(target))
            if image.isNull() or image.width() < 2 or image.height() < 2:
                fail("exported PNG is empty")
                return
            print(
                f"IMAGE_SELF_TEST_OK: {target} {image.width()}x{image.height()} "
                "fullscreen=True normal_restore=True",
                flush=True,
            )
            result_code = 0
            timer.stop()
            window.close()
            app.quit()

    timer.timeout.connect(check)
    timer.start()
    app.exec()
    return result_code
