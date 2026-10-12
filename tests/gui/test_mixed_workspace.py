from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPushButton

from video_compare.domain.models import TransportState
from video_compare.domain.viewport import ViewRegion
from video_compare.ui import main_window
from video_compare.ui.canvas_software import SoftwareCompareCanvas
from video_compare.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "tests/assets/generated/f05_h264_bframes.mp4"
FFPROBE = ROOT / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe"


def _source_id(rgb: np.ndarray) -> int:
    # Independent truth encoded into the generated video before compression.
    return sum(
        (1 << bit)
        for bit in range(16)
        if int(rgb[13 + (bit // 8) * 14, 13 + (bit % 8) * 14, 0]) >= 128
    )


@pytest.fixture
def mixed_window(qtbot, tmp_path: Path, monkeypatch):
    image = tmp_path / "中文 图像 [1].png"
    Image.new("RGB", (320, 180), (17, 67, 117)).save(image)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=FFPROBE,
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    window.load_files([image, VIDEO])
    qtbot.waitUntil(
        lambda: (
            len(window._active_assets()) == 2
            and window._pending_add == 0
            and not window._image_pending
            and window._current_display_snapshot() is not None
            and len(window._current_display_snapshot().frames) == 2
        ),
        timeout=10000,
    )
    yield window, image
    window.close()


@pytest.mark.gui
def test_mixed_real_playback_step_keeps_still_and_video_range(qtbot, mixed_window) -> None:
    window, _image = mixed_window
    assert window.media_kind == "mixed"
    assert not hasattr(window, "_media_mode")
    image_id, video_id = window.canvas.display_order
    assert window._active_assets()[image_id].media_kind == "image"
    assert window._active_assets()[video_id].media_kind == "video"
    transport = window._transport
    assert transport is not None
    assert transport.spec.participants == (video_id,)
    assert transport.mapper.valid_range(transport.spec).end > 2
    first = window._current_display_snapshot()
    still = first.frames[image_id]
    digest = hashlib.sha256(still.rgb).hexdigest()
    transport.play()
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal >= 4, timeout=5000)
    transport.pause()
    paused = transport.displayed.reference_ordinal
    qtbot.wait(100)
    assert transport.displayed.reference_ordinal == paused
    assert window.canvas._snapshot.frames[image_id] is still
    assert hashlib.sha256(still.rgb).hexdigest() == digest
    for direction, expected in ((1, paused + 1), (-1, paused)):
        transport.step(direction, 1, "frame")
        qtbot.waitUntil(
            lambda ordinal=expected: transport.displayed.reference_ordinal == ordinal,
            timeout=5000,
        )
        display = window._current_display_snapshot()
        assert display.frames[image_id] is still
        assert display.frames[video_id].ordinal == expected
        assert _source_id(display.frames[video_id].rgb) == expected
        assert transport.state is TransportState.PAUSED


@pytest.mark.gui
def test_mixed_six_route_limit_and_swap_preserve_decoders(qtbot, mixed_window, monkeypatch) -> None:
    window, image = mixed_window
    window.load_files([VIDEO, image, VIDEO, image])
    qtbot.waitUntil(
        lambda: (
            len(window._active_assets()) == 6
            and window._pending_add == 0
            and not window._image_pending
            and window._current_display_snapshot() is not None
            and len(window._current_display_snapshot().frames) == 6
        ),
        timeout=10000,
    )
    order = window.canvas.display_order
    transport = window._transport
    workers = dict(transport._workers)
    spec = transport.spec
    snapshot = window.canvas._snapshot
    calls = []
    for worker in workers.values():
        monkeypatch.setattr(worker, "submit_latest", lambda request: calls.append(request))
    window.canvas.panel_swap_requested.emit(order[0], order[-1])
    expected = (order[-1], *order[1:-1], order[0])
    assert window.canvas.display_order == expected
    assert tuple(window._active_assets()) == expected
    assert window._transport is transport
    assert dict(transport._workers) == workers
    assert transport.spec is spec
    assert window.canvas._snapshot is snapshot
    assert not calls
    notices = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: notices.append(_args[2]))
    window.load_files([image, VIDEO])
    qtbot.wait(100)
    assert window.canvas.display_order == expected
    assert window.canvas._snapshot is snapshot
    assert len(window._active_assets()) == 6
    assert window._pending_add == 0 and not window._image_pending
    assert len(notices) == 1 and "6" in notices[0]


@pytest.mark.gui
def test_removing_last_video_keeps_still_and_rejects_old_transport_group(
    qtbot, mixed_window
) -> None:
    window, _image = mixed_window
    image_id = next(iter(window._image_assets))
    video_id = next(iter(window._assets))
    old_transport = window._transport
    old_snapshot = old_transport.displayed
    still = window.canvas._snapshot.frames[image_id]
    window._select_asset(video_id)
    window.remove_selected()
    qtbot.waitUntil(
        lambda: window._transport is None and window._current_display_snapshot() is not None,
        timeout=5000,
    )
    assert window.media_kind == "image"
    image_snapshot = window.canvas._snapshot
    assert tuple(image_snapshot.frames) == (image_id,)
    assert image_snapshot.frames[image_id] is still
    assert not window._play_button.isEnabled()
    window._on_group(old_snapshot)
    assert window.canvas._snapshot is image_snapshot
    window.load_files([VIDEO])
    qtbot.waitUntil(
        lambda: (
            window._transport is not None
            and window._current_display_snapshot() is not None
            and len(window._current_display_snapshot().frames) == 2
        ),
        timeout=10000,
    )
    current = window.canvas._snapshot
    # A queued signal from the closed controller may arrive after the new one.
    window._on_group(old_snapshot)
    assert window.canvas._snapshot is current
    assert old_transport is not window._transport
    assert set(current.frames) == set(window._active_assets())


@pytest.mark.gui
def test_mixed_snapshot_and_comparison_export_include_both_source_identities(
    qtbot, tmp_path: Path, mixed_window
) -> None:
    window, image = mixed_window
    transport = window._transport
    transport.seek_reference_frame(18)
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal == 17, timeout=5000)
    pinned = window._current_display_snapshot()
    group = window.save_frame_screenshots(tmp_path / "frames")
    assert group == pinned.group_id
    # Advance while the writer owns the captured immutable group.
    transport.play()
    qtbot.waitUntil(lambda: len(list((tmp_path / "frames").glob("*.json"))) == 2, timeout=5000)
    transport.pause()
    for sidecar_path in (tmp_path / "frames").glob("*.json"):
        metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert metadata["media_kind"] == "mixed"
        assert metadata["group_id"] == list(group)
        assert metadata["reference_ui_frame"] == 18
        assert len(metadata["assets"]) == 2
        entries = {entry["asset_id"]: entry for entry in metadata["assets"]}
        image_id = next(iter(window._image_assets))
        video_id = next(iter(window._assets))
        assert entries[image_id]["media_kind"] == "image"
        assert entries[image_id]["ui_frame"] is None
        assert entries[image_id]["source_pts"] is None
        assert entries[image_id]["time_sync_state"] == "static"
        assert entries[video_id]["media_kind"] == "video"
        assert entries[video_id]["ui_frame"] == 18
        assert entries[video_id]["source_pts"] == pinned.frames[video_id].pts
        exported = np.asarray(Image.open(sidecar_path.with_suffix(".png")).convert("RGB"))
        if metadata["export_asset_id"] == video_id:
            assert _source_id(exported) == 17
        else:
            assert np.array_equal(exported, np.asarray(Image.open(image).convert("RGB")))
    plan = window._composite_plan("horizontal")
    assert plan is not None
    tiles, _composite, skipped = plan
    assert len(tiles) == 2 and not skipped
    target = tmp_path / "mixed-comparison.png"
    assert window.export_comparison_image(target, layout="horizontal") is not None
    qtbot.waitUntil(target.exists, timeout=5000)
    assert Image.open(target).width > 320
    assert not target.with_suffix(".json").exists()


@pytest.mark.gui
def test_mixed_first_upload_fallback_preserves_complete_real_group_and_view(
    qtbot, tmp_path: Path, mixed_window, monkeypatch
) -> None:
    window, _image = mixed_window
    old_canvas = window.canvas
    first_id = old_canvas.display_order[0]
    old_canvas._set_region(first_id, ViewRegion(0.5, 0.5, 0.5, 0.5))
    regions = old_canvas.view_regions
    snapshot = window._current_display_snapshot()
    transport = window._transport
    workers = dict(transport._workers)
    order = old_canvas.display_order
    calls = []
    for worker in workers.values():
        monkeypatch.setattr(worker, "submit_latest", lambda request: calls.append(request))
    # Real source frames have reached the window, but a failed first GL upload
    # has no front snapshot. Use the same branch without a fake decoder/GL API.
    old_canvas._snapshot = None
    assert window._current_display_snapshot() is None
    original_gl_type = main_window.CompareCanvas
    monkeypatch.setattr(main_window, "CompareCanvas", type(old_canvas))
    try:
        window._fallback_canvas("test: first texture upload failed")
    finally:
        monkeypatch.setattr(main_window, "CompareCanvas", original_gl_type)
    assert isinstance(window.canvas, SoftwareCompareCanvas)
    assert window.canvas is not old_canvas
    assert window.canvas._snapshot is snapshot
    assert window._current_display_snapshot() is snapshot
    assert set(snapshot.frames) == set(window._active_assets())
    assert window.canvas.display_order == order
    assert window.canvas.view_regions == regions
    assert window._transport is transport and transport._workers == workers
    assert not calls
    assert window.save_frame_screenshots(tmp_path / "fallback-frames") == snapshot.group_id
    assert window.save_view_screenshot(tmp_path / "fallback-view") == snapshot.group_id
    qtbot.waitUntil(
        lambda: (
            len(list((tmp_path / "fallback-frames").glob("*.png"))) == 2
            and len(list((tmp_path / "fallback-view").glob("*.png"))) == 1
        ),
        timeout=5000,
    )
    video_id = next(iter(window._assets))
    assert _source_id(snapshot.frames[video_id].rgb) == snapshot.reference_ordinal
    assert "软件渲染" in window._status.text() or "保存" in window._status.text()


@pytest.mark.gui
def test_space_only_toggles_transport_for_buttons_inputs_and_folder_tree(
    qtbot, mixed_window
) -> None:
    window, image = mixed_window
    assert window._file_browser.set_directory(image.parent)
    tree = window._file_browser.tree
    qtbot.waitUntil(lambda: window._file_browser.model.rowCount(tree.rootIndex()) > 0)
    path = window._file_browser.path_edit
    path_before = path.text()
    check = window._linked_button
    checked_before = check.isChecked()
    button = window._forward_button
    button_clicks = []
    button.clicked.connect(lambda: button_clicks.append(True))
    targets = (button, check, window._time_input, path, tree)
    transport = window._transport
    for target in targets:
        transport.pause()
        target.setFocus()
        text_before = target.text() if isinstance(target, QLineEdit) else None
        qtbot.keyClick(target, Qt.Key.Key_Space)
        assert transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
        repeated = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Space,
            Qt.KeyboardModifier.NoModifier,
            " ",
            True,
            5,
        )
        QApplication.sendEvent(target, repeated)
        assert transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
        qtbot.keyClick(target, Qt.Key.Key_Space)
        assert transport.state is TransportState.PAUSED
        if text_before is not None:
            assert target.text() == text_before
        assert check.isChecked() == checked_before
        assert not button_clicks
    assert path.text() == path_before
    # A modal dialog owns its keyboard; Space must never start background video.
    modal = QDialog(window)
    modal.setModal(True)
    modal_button = QPushButton("Close", modal)
    modal_button.move(QPoint(20, 20))
    modal.show()
    qtbot.waitUntil(lambda: QApplication.activeModalWidget() is modal)
    qtbot.keyClick(modal_button, Qt.Key.Key_Space)
    assert transport.state is TransportState.PAUSED
    modal.close()
