from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPushButton

from video_compare.domain.models import TransportState
from video_compare.domain.viewport import ViewRegion
from video_compare.ui.canvas_common import pane_transform
from video_compare.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "tests/assets/generated/f05_h264_bframes.mp4"
FFPROBE = ROOT / ".codex-tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe"


def _source_id(rgb: np.ndarray) -> int:
    return sum(
        1 << bit
        for bit in range(16)
        if int(rgb[13 + (bit // 8) * 14, 13 + (bit % 8) * 14, 0]) >= 128
    )


def _margins(layout) -> tuple[int, int, int, int]:
    margins = layout.contentsMargins()
    return margins.left(), margins.top(), margins.right(), margins.bottom()


def _chrome(window: MainWindow):
    return (
        window._settings_button.parentWidget(),
        window._sidebar,
        window._play_button.parentWidget(),
        window._pixel_notice,
        window._annotation_bar,
    )


@pytest.fixture
def fullscreen_window(qtbot, tmp_path: Path, monkeypatch):
    image = tmp_path / "全屏 中文 图像.png"
    Image.new("RGB", (320, 180), (23, 83, 143)).save(image)
    input_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (image, VIDEO)}
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
    transport = window._transport
    transport.seek_reference_frame(8)
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal == 7, timeout=5000)
    assert _source_id(transport.displayed.frames[next(iter(window._assets))].rgb) == 7
    yield window
    if window.isVisible():
        window.close()
    for path, digest in input_hashes.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.gui
def test_fullscreen_fills_window_preserving_real_group_canvas_and_workers(
    qtbot, fullscreen_window, monkeypatch
) -> None:
    window = fullscreen_window
    canvas = window.canvas
    parent = canvas.parentWidget()
    first_id = canvas.display_order[0]
    canvas._set_region(first_id, ViewRegion(0.55, 0.55, 0.6, 0.6))
    regions = canvas.view_regions
    snapshot = window._current_display_snapshot()
    transport = window._transport
    spec = transport.spec
    workers = dict(transport._workers)
    order = canvas.display_order
    calls = []
    for worker in workers.values():
        monkeypatch.setattr(worker, "submit_latest", calls.append)
    visible = tuple(widget.isVisible() for widget in _chrome(window))
    qtbot.mouseClick(window._fullscreen_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(window.isFullScreen, timeout=2000)
    qtbot.waitUntil(lambda: canvas.size() == window.size(), timeout=2000)
    assert window._workspace_fullscreen
    assert all(not widget.isVisible() for widget in _chrome(window))
    assert _margins(window.centralWidget().layout()) == (0, 0, 0, 0)
    assert _margins(window._main_layout) == (0, 0, 0, 0)
    assert canvas.mapTo(window, QPoint(0, 0)) == QPoint(0, 0)
    assert canvas.parentWidget() is parent
    assert window.canvas is canvas
    assert window._transport is transport
    assert transport.spec is spec and transport._workers == workers
    assert canvas._snapshot is snapshot and canvas.view_regions == regions
    assert canvas.display_order == order and not calls
    exit_button = window._fullscreen_exit_button
    assert exit_button.parentWidget() is window.centralWidget() and exit_button.isVisible()
    exit_position = exit_button.mapTo(canvas, QPoint(0, 0))
    assert 0 <= canvas.width() - (exit_position.x() + exit_button.width()) <= 24
    assert 0 <= exit_position.y() <= 24
    qtbot.keyClick(canvas, Qt.Key.Key_F11)
    qtbot.waitUntil(lambda: not window.isFullScreen(), timeout=2000)
    assert not window._workspace_fullscreen
    assert not exit_button.isVisible()
    assert tuple(widget.isVisible() for widget in _chrome(window)) == visible
    assert window.canvas is canvas and canvas._snapshot is snapshot
    assert transport._workers == workers and not calls


@pytest.mark.gui
@pytest.mark.parametrize("maximized,sidebar_visible", [(False, True), (True, False)])
def test_fullscreen_restores_prior_window_state_and_exact_chrome(
    qtbot, fullscreen_window, tmp_path: Path, maximized: bool, sidebar_visible: bool
) -> None:
    window = fullscreen_window
    if maximized:
        window.showMaximized()
        qtbot.waitUntil(window.isMaximized, timeout=2000)
    window._sidebar_button.setChecked(sidebar_visible)
    qtbot.waitUntil(lambda: window._sidebar_animation is None, timeout=2000)
    window._pixel_mode_combo.setCurrentIndex(1)
    window.start_annotation_export(tmp_path / "pending-annotation.png")
    assert window._pixel_notice.isVisible() and window._annotation_bar.isVisible()
    root_layout = window.centralWidget().layout()
    root_layout.setContentsMargins(5, 7, 9, 11)
    root_layout.setSpacing(13)
    window._main_layout.setContentsMargins(2, 4, 6, 8)
    window._main_layout.setSpacing(15)
    root_margins, main_margins = _margins(root_layout), _margins(window._main_layout)
    visibility = tuple(widget.isVisible() for widget in _chrome(window))
    geometry = window.geometry()
    snapshot = window.canvas._snapshot
    window.set_workspace_fullscreen(True)
    qtbot.waitUntil(window.isFullScreen, timeout=2000)
    assert all(not widget.isVisible() for widget in _chrome(window))
    assert root_layout.spacing() == 0 and window._main_layout.spacing() == 0
    qtbot.mouseClick(window._fullscreen_exit_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._workspace_fullscreen, timeout=2000)
    assert window.isMaximized() is maximized
    assert tuple(widget.isVisible() for widget in _chrome(window)) == visibility
    assert window._sidebar_button.isChecked() is sidebar_visible
    assert _margins(root_layout) == root_margins
    assert _margins(window._main_layout) == main_margins
    assert root_layout.spacing() == 13 and window._main_layout.spacing() == 15
    if not maximized:
        assert window.geometry() == geometry
    assert window.canvas._snapshot is snapshot
    assert window.canvas.annotating


@pytest.mark.gui
def test_fullscreen_space_and_arrows_control_real_b_frames_with_exit_button_focus(
    qtbot, fullscreen_window
) -> None:
    window = fullscreen_window
    transport = window._transport
    video_id = next(iter(window._assets))
    image_id = next(iter(window._image_assets))
    still = window.canvas._snapshot.frames[image_id]
    window._step_amount.setText("2")
    window.set_workspace_fullscreen(True)
    exit_button = window._fullscreen_exit_button
    exit_button.setFocus()
    qtbot.keyClick(exit_button, Qt.Key.Key_Space)
    assert transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal >= 9, timeout=5000)
    qtbot.keyClick(exit_button, Qt.Key.Key_Space)
    assert transport.state is TransportState.PAUSED
    paused = transport.displayed.reference_ordinal
    qtbot.keyClick(exit_button, Qt.Key.Key_Right)
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal == paused + 2, timeout=5000)
    assert _source_id(transport.displayed.frames[video_id].rgb) == paused + 2
    qtbot.keyClick(exit_button, Qt.Key.Key_Left)
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal == paused, timeout=5000)
    assert _source_id(transport.displayed.frames[video_id].rgb) == paused
    assert window.canvas._snapshot.frames[image_id] is still
    assert window._workspace_fullscreen and exit_button.isVisible()
    assert all(not widget.isVisible() for widget in _chrome(window))
    qtbot.keyClick(exit_button, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not window._workspace_fullscreen, timeout=2000)


@pytest.mark.gui
def test_fullscreen_ctrl_wheel_zoom_preserves_real_snapshot(qtbot, fullscreen_window) -> None:
    window = fullscreen_window
    window.set_workspace_fullscreen(True)
    canvas = window.canvas
    qtbot.waitUntil(lambda: canvas.size() == window.size(), timeout=2000)
    snapshot = canvas._snapshot
    first_id = canvas.display_order[0]
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas.display_order,
        window._active_assets(),
        snapshot,
        canvas.view_regions,
        first_id,
        layout=canvas.layout_mode,
    )
    assert transform is not None
    x, y = transform.forward(0.5, 0.5)
    point = QPoint(round(x), round(y))
    before = canvas.view_regions[first_id]
    wheel = QWheelEvent(
        QPointF(point),
        canvas.mapToGlobal(point),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas, wheel)
    assert canvas.view_regions[first_id].width_u == pytest.approx(before.width_u / 1.15)
    assert len(set(canvas.view_regions.values())) == 1
    assert canvas._snapshot is snapshot
    assert window._workspace_fullscreen


@pytest.mark.gui
def test_fullscreen_escape_exits_before_roi_or_pane_maximize(qtbot, fullscreen_window) -> None:
    window = fullscreen_window
    first_id = window.canvas.display_order[0]
    window._toggle_maximize_asset(first_id)
    window._roi_button.setChecked(True)
    window.set_workspace_fullscreen(True)
    canvas = window.canvas
    qtbot.waitUntil(lambda: canvas.size() == window.size(), timeout=2000)
    centre = canvas.rect().center()
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseMove(canvas, pos=centre + QPoint(40, 30))
    assert canvas._roi_preview is not None
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not window._workspace_fullscreen, timeout=2000)
    assert canvas._roi_preview is None and canvas._drag_asset is None
    assert window._maximized_id == first_id
    assert window._roi_button.isChecked()
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=centre + QPoint(40, 30))


@pytest.mark.gui
def test_fullscreen_modal_dialog_keeps_transport_and_fullscreen_unchanged(
    qtbot, fullscreen_window
) -> None:
    window = fullscreen_window
    transport = window._transport
    window.set_workspace_fullscreen(True)
    ordinal = transport.displayed.reference_ordinal
    modal = QDialog(window)
    modal.setModal(True)
    modal.resize(300, 120)
    field = QLineEdit("abc", modal)
    field.setGeometry(10, 10, 200, 30)
    field.setCursorPosition(1)
    button = QPushButton("Test", modal)
    button.setGeometry(10, 60, 80, 30)
    modal.show()
    qtbot.waitUntil(lambda: QApplication.activeModalWidget() is modal, timeout=2000)
    try:
        qtbot.keyClick(button, Qt.Key.Key_Space)
        qtbot.keyClick(field, Qt.Key.Key_Right)
        qtbot.keyClick(field, Qt.Key.Key_F11)
        assert field.cursorPosition() == 2
        assert transport.state is TransportState.PAUSED
        assert transport.displayed.reference_ordinal == ordinal
        assert window._workspace_fullscreen
        qtbot.keyClick(field, Qt.Key.Key_Escape)
        assert window._workspace_fullscreen
    finally:
        modal.close()


@pytest.mark.gui
def test_closing_fullscreen_releases_real_decoder_and_loader_workers(
    qtbot, fullscreen_window
) -> None:
    window = fullscreen_window
    transport = window._transport
    workers = tuple(transport._workers.values())
    window.set_workspace_fullscreen(True)
    qtbot.keyClick(window.canvas, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: transport.displayed.reference_ordinal >= 9, timeout=5000)
    window.close()
    assert window._transport is None
    assert not window.isVisible()
    assert all(worker.join(timeout=0) for worker in workers)
    assert window._loader.join(timeout=0)
    assert window._image_loader.join(timeout=0)
    assert window._screenshot_worker.join(timeout=0)


@pytest.mark.gui
def test_async_annotation_export_finished_in_fullscreen_stays_hidden(
    qtbot, fullscreen_window, tmp_path: Path
) -> None:
    window = fullscreen_window
    target = tmp_path / "fullscreen-completed.png"
    window.start_annotation_export(target)
    assert window._annotation_bar.isVisible()
    window._finish_annotation_export()
    window.set_workspace_fullscreen(True)
    qtbot.waitUntil(
        lambda: target.exists() and window._pending_annotated_export is None, timeout=5000
    )
    assert not window._annotation_bar.isVisible()
    assert not window.canvas.annotating
    window.set_workspace_fullscreen(False)
    assert not window._annotation_bar.isVisible()
    assert not window.canvas.annotating
    with Image.open(target) as exported:
        assert exported.size[0] > 0


@pytest.mark.gui
def test_fullscreen_auxiliary_ui_updates_remain_hidden_until_exit(
    qtbot, fullscreen_window, tmp_path: Path
) -> None:
    window = fullscreen_window
    window.set_workspace_fullscreen(True)
    window._pixel_mode_combo.setCurrentIndex(1)
    window.start_annotation_export(tmp_path / "pending-annotation.png")
    assert not window._pixel_notice.isVisible()
    assert not window._annotation_bar.isVisible()
    window.set_workspace_fullscreen(False)
    assert window._pixel_notice.isVisible()
    assert window._annotation_bar.isVisible()
    assert window.canvas.annotating
    window._cancel_annotation_export()
