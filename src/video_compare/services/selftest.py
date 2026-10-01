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
            window._assets,
            window.canvas._snapshot,
        )
        first, second = boxes[order[0]], boxes[order[1]]
        if abs(first.height - second.height) > 0.01 or abs(first.y - second.y) > 0.01:
            fail(f"adaptive layout rows differ: {first} vs {second}")
            return
        gap = second.x - first.right
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
            f"icon=True notices={len(dialogs)}",
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
        boxes = pane_boxes(canvas.width(), canvas.height(), order, window._assets, canvas._snapshot)
        rows: dict[float, list[tuple[int, int]]] = {}
        for asset_id in order:
            transform = pane_transform(
                canvas.width(),
                canvas.height(),
                order,
                window._assets,
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
            if len(window._assets) != 2:
                if window._pending_add == 0:
                    fail(f"import failed: {window._status.text()}")
                return
            snapshot = window._current_display_snapshot()
            if snapshot is None or len(snapshot.frames) != 2:
                return
            assert window._transport is not None
            window._transport.seek_reference_frame(2)
            state["phase"] = "seek"
        elif phase == "seek":
            snapshot = window._current_display_snapshot()
            if snapshot is None or snapshot.reference_ordinal != 1:
                return
            spec = window._transport.spec
            for asset_id, frame in snapshot.frames.items():
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
        nonlocal phase, result_code
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
            if window.export_comparison_image(target) is None:
                fail(f"export request failed: {window._status.text()}")
                return
            phase = "export"
        elif phase == "export":
            if not target.is_file() or not notices:
                return
            image = QImage(str(target))
            if image.isNull() or image.width() < 2 or image.height() < 2:
                fail("exported PNG is empty")
                return
            print(f"IMAGE_SELF_TEST_OK: {target} {image.width()}x{image.height()}", flush=True)
            result_code = 0
            timer.stop()
            window.close()
            app.quit()

    timer.timeout.connect(check)
    timer.start()
    app.exec()
    return result_code
