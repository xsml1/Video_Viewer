from __future__ import annotations

import json
import random
import subprocess
import time
from bisect import bisect_right
from fractions import Fraction
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from video_compare.domain.models import TransportState
from video_compare.domain.viewport import ViewRegion
from video_compare.media.decoder import DecodeError, PreciseDecoder
from video_compare.media.probe import ProbeCancelled
from video_compare.services.settings import AppSettings, load_settings
from video_compare.ui.canvas_common import grid_shape, pane_transform
from video_compare.ui.main_window import MainWindow


@pytest.mark.gui
def test_long_import_opens_real_first_frame_and_queues_steps(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    first_indexed = Event()
    continue_indexing = Event()
    original_build = window._repository.build

    def build_with_first_frame_gate(asset, **kwargs):
        preview = kwargs["preview"]

        def gated_preview(timeline):
            preview(timeline)
            if timeline.frame_count == 1 and not first_indexed.is_set():
                first_indexed.set()
                continue_indexing.wait(timeout=10)

        return original_build(asset, **{**kwargs, "preview": gated_preview})

    window._repository.build = build_with_first_frame_gate
    try:
        window.load_files([root / "f05_h264_bframes.mp4"])
        qtbot.waitUntil(
            lambda: (
                first_indexed.is_set()
                and window.canvas._snapshot is not None
                and len(window._assets) == 1
            ),
            timeout=5000,
        )
        transport = window._transport
        assert transport is not None
        assert transport.timelines[next(iter(window._assets))].provisional
        assert window.canvas._snapshot.reference_ordinal == 0
        transport.play()
        qtbot.waitUntil(lambda: transport.state is TransportState.BUFFERING, timeout=2000)
        transport.seek_time(Fraction(1, 10))
        assert transport.requested_time == Fraction(1, 10)
        assert transport.state is TransportState.SEEKING
        for _ in range(3):
            qtbot.mouseClick(window._forward_button, Qt.MouseButton.LeftButton)
        assert transport.requested_frame == 3
        assert window.canvas._snapshot.reference_ordinal == 0
    finally:
        continue_indexing.set()
    qtbot.waitUntil(
        lambda: (
            window._pending_add == 0
            and window.canvas._snapshot is not None
            and window.canvas._snapshot.reference_ordinal == 3
        ),
        timeout=8000,
    )
    asset_id = next(iter(window._assets))
    assert window._transport is transport
    assert not transport.timelines[asset_id].provisional
    assert (
        window.canvas._snapshot.frames[asset_id].pts == transport.timelines[asset_id].entries[3].pts
    )


@pytest.mark.gui
def test_removing_partially_indexed_route_cancels_its_loader(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    continue_indexing = Event()
    first_indexed = Event()
    original_build = window._repository.build

    def held_build(asset, **kwargs):
        preview = kwargs["preview"]

        def held_preview(timeline):
            preview(timeline)
            if timeline.frame_count == 1:
                first_indexed.set()
                continue_indexing.wait(timeout=10)

        return original_build(asset, **{**kwargs, "preview": held_preview})

    window._repository.build = held_build
    try:
        window.load_files([root / "f05_h264_bframes.mp4"])
        qtbot.waitUntil(
            lambda: (
                first_indexed.is_set()
                and window.canvas._snapshot is not None
                and len(window._assets) == 1
            ),
            timeout=5000,
        )
        asset = next(iter(window._assets.values()))
        window._file_list.setCurrentRow(0)
        window.remove_selected()
        assert not window._assets
        assert window._pending_add == 0
        assert window._transport is None
    finally:
        continue_indexing.set()
    qtbot.waitUntil(lambda: window._repository.state(asset).value == "partial", timeout=5000)
    qtbot.wait(50)
    assert not window._assets
    assert window.canvas._snapshot is None


@pytest.mark.gui
def test_offset_waits_for_common_index_coverage_then_recovers(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(
        lambda: window._pending_add == 0 and window.canvas._snapshot is not None,
        timeout=5000,
    )
    continue_indexing = Event()
    first_indexed = Event()
    original_build = window._repository.build

    def held_build(asset, **kwargs):
        preview = kwargs["preview"]

        def held_preview(timeline):
            preview(timeline)
            if timeline.frame_count == 1:
                first_indexed.set()
                continue_indexing.wait(timeout=10)

        return original_build(asset, **{**kwargs, "preview": held_preview})

    window._repository.build = held_build
    try:
        window.load_files([root / "f05_ffv1_oracle.mkv"])
        qtbot.waitUntil(
            lambda: first_indexed.is_set() and len(window._assets) == 2,
            timeout=5000,
        )
        window._file_list.setCurrentRow(1)
        window._time_offset_input.setText("+0.200")
        qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
        assert window._pending_transport_anchor is not None
        assert not window._play_button.isEnabled()
    finally:
        continue_indexing.set()
    qtbot.waitUntil(
        lambda: (
            window._pending_add == 0
            and window._pending_transport_anchor is None
            and window._transport is not None
            and window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 2
        ),
        timeout=8000,
    )
    first, second = tuple(window._assets)
    assert window._transport.displayed.frames[first].ordinal == 0
    assert window._transport.displayed.frames[second].ordinal == 6


@pytest.mark.gui
def test_playback_waits_at_real_index_frontier_and_resumes(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    video = root / "f18_index_frontier_600.mp4"
    assert video.is_file(), "先运行长片素材生成脚本"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    frontier_reached = Event()
    continue_indexing = Event()
    original_build = window._repository.build

    def held_build(asset, **kwargs):
        preview = kwargs["preview"]

        def held_preview(timeline):
            preview(timeline)
            if timeline.frame_count == 255:
                frontier_reached.set()
                continue_indexing.wait(timeout=10)

        return original_build(asset, **{**kwargs, "preview": held_preview})

    window._repository.build = held_build
    try:
        window.load_files([video])
        qtbot.waitUntil(
            lambda: (
                frontier_reached.is_set()
                and window._transport is not None
                and window._transport.timelines[next(iter(window._assets))].frame_count == 255
            ),
            timeout=8000,
        )
        transport = window._transport
        transport.seek_reference_frame(255)
        qtbot.waitUntil(
            lambda: (
                transport.displayed is not None and transport.displayed.reference_ordinal == 254
            ),
            timeout=5000,
        )
        transport.play()
        qtbot.waitUntil(lambda: transport.state is TransportState.BUFFERING, timeout=2000)
        assert transport.displayed.reference_ordinal == 254
    finally:
        continue_indexing.set()
    qtbot.waitUntil(
        lambda: transport.displayed is not None and transport.displayed.reference_ordinal >= 255,
        timeout=8000,
    )
    assert window._transport is transport
    window._file_list.setCurrentRow(0)
    window.remove_selected()
    assert not window._assets


@pytest.mark.gui
def test_two_imports_show_real_first_frames_while_first_full_index_waits(
    qtbot, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    first_video = root / "f18_index_frontier_600.mp4"
    assert first_video.is_file(), "先运行长片素材生成脚本"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    index_blocked = Event()
    continue_indexing = Event()
    original_build = window._repository.build

    def held_first_index(asset, **kwargs):
        preview = kwargs["preview"]

        def gated_preview(timeline):
            preview(timeline)
            if asset.path == first_video and timeline.frame_count == 1:
                index_blocked.set()
                continue_indexing.wait(timeout=10)

        return original_build(asset, **{**kwargs, "preview": gated_preview})

    window._repository.build = held_first_index
    try:
        window.load_files([first_video, root / "f05_h264_bframes.mp4"])
        qtbot.waitUntil(
            lambda: (
                index_blocked.is_set()
                and len(window._assets) == 2
                and window.canvas._snapshot is not None
                and len(window.canvas._snapshot.frames) == 2
            ),
            timeout=8000,
        )
        assert window._pending_add == 2
        assert all(timeline.provisional for timeline in window._timelines.values())
        assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {0}
    finally:
        continue_indexing.set()
    window.close()
    assert window._loader.join(timeout=0.1)


@pytest.mark.gui
def test_software_canvas_shows_real_two_and_six_frame_group(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    assert ffprobe.is_file(), "运行 GUI 真实媒体测试需要先安装项目 FFmpeg"
    assert (root / "f05_h264_bframes.mp4").is_file(), "先运行 fixture 生成器"
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    paths = [root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"]
    window.load_files(paths)
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    assert len(window._assets) == 2
    assert "RGB8 预览" in window._asset_info.text()
    assert "色彩元信息缺失，已推定" in window._asset_info.text()
    assert grid_shape(2) == (1, 2)
    assert len(window.canvas._snapshot.frames) == 2
    rendered = window.canvas.grab().toImage()
    assert not rendered.isNull()
    assert rendered.width() > 0 and rendered.height() > 0

    for _ in range(3):
        qtbot.mouseClick(window._forward_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 3, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {3}

    window._time_input.setFocus()
    qtbot.keyClick(window._time_input, Qt.Key.Key_Left)
    qtbot.wait(50)
    assert window.canvas._snapshot.reference_ordinal == 3
    window._mode.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window.canvas._snapshot.group_id == window._transport.displayed.group_id
        ),
        timeout=5000,
    )
    assert window._transport.displayed.reference_ordinal == 3

    window._slider.setValue(5000)
    window._finish_scrub()
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 36, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {36}

    window.load_files(paths * 2)
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 6,
        timeout=5000,
    )
    assert len(window._assets) == 6
    assert grid_shape(6) == (2, 3)
    assert len(window.canvas._snapshot.frames) == 6


@pytest.mark.gui
def test_grid_counts_one_through_six_and_seventh_is_rejected(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    source = root / "f05_h264_bframes.mp4"
    for count in range(1, 7):
        window.load_files([source])
        qtbot.waitUntil(
            lambda count=count: (
                len(window._assets) == count
                and window.canvas._snapshot is not None
                and len(window.canvas._snapshot.frames) == count
            ),
            timeout=5000,
        )
        assert grid_shape(count) == ((1, count) if count <= 3 else (2, 2 if count == 4 else 3))
        assert len(window.canvas._order) == count
    before_ids = tuple(window._assets)
    before_group = window.canvas._snapshot
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )
    window.load_files([source])
    assert warnings == [f"{source.name}：最多导入 6 路"]
    assert tuple(window._assets) == before_ids
    assert window.canvas._snapshot is before_group


@pytest.mark.gui
def test_one_hundred_real_single_video_window_open_close_cycles(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    index_path = tmp_path / "index.sqlite3"
    for _ in range(100):
        window = MainWindow(index_path, ffprobe_path=ffprobe, software=True)
        qtbot.addWidget(window)
        window.show()
        window.load_files([root / "f05_h264_bframes.mp4"])
        qtbot.waitUntil(lambda current=window: current.canvas._snapshot is not None, timeout=5000)
        workers = tuple(window._transport._workers.values())
        window.close()
        assert all(worker.join(timeout=0.1) for worker in workers)
        assert window._loader.join(timeout=0.1)
        assert window._screenshot_worker.join(timeout=0.1)


@pytest.mark.gui
def test_real_480p_1080p_4k_grid_shares_normalized_roi(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / f"f06_grid_{label}.mp4" for label in ("480p", "1080p", "4k")])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 3,
        timeout=10000,
    )
    assert [asset.coded_width for asset in window._assets.values()] == [854, 1920, 3840]
    for frame in window.canvas._snapshot.frames.values():
        rgb = frame.rgb
        mask = (rgb[:, :, 0] > 180) & (rgb[:, :, 1] < 90) & (rgb[:, :, 2] < 90)
        ys, xs = np.where(mask)
        # The generated YUV420 marker edges are rounded to even chroma samples.
        assert abs(int(xs.min()) - rgb.shape[1] / 4) <= 2
        assert abs(int(ys.min()) - rgb.shape[0] / 4) <= 2
        assert abs(int(xs.max()) + 1 - rgb.shape[1] * 3 / 4) <= 2
        assert abs(int(ys.max()) + 1 - rgb.shape[0] * 3 / 4) <= 2

    canvas = window.canvas
    source_id = canvas._order[0]
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas._order,
        window._assets,
        canvas._snapshot,
        canvas.view_regions,
        source_id,
        layout=canvas.layout_mode,
    )
    assert transform is not None
    start = transform.forward(0.3, 0.3)
    end = transform.forward(0.7, 0.7)
    window._roi_button.setChecked(True)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(*map(round, start)))
    qtbot.mouseMove(canvas, pos=QPoint(*map(round, end)))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(*map(round, end)))
    regions = canvas.view_regions
    assert len(set(regions.values())) == 1
    region = regions[source_id]
    x0, y0 = map(round, start)
    x1, y1 = map(round, end)
    content = transform.content_rect
    assert abs(region.center_u - ((x0 + x1) / 2 - content.x) / content.width) < 1e-12
    assert abs(region.center_v - ((y0 + y1) / 2 - content.y) / content.height) < 1e-12
    assert 0.38 <= region.width_u <= 0.42
    assert 0.38 <= region.height_v <= 0.42


@pytest.mark.gui
def test_hdr_import_joins_real_atomic_group_with_visible_sdr_policy(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None and len(window._assets) == 2)
    asset_ids = set(window._assets)
    window.load_files([root / "f09_hdr_pq.mp4"])
    qtbot.waitUntil(lambda: window._pending_add == 0, timeout=5000)
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 3,
        timeout=5000,
    )
    assert asset_ids < set(window._assets)
    assert len(window._assets) == 3
    hdr_id = next(key for key in window._assets if key not in asset_ids)
    assert "hable:1000" in window.canvas._snapshot.frames[hdr_id].color_policy_id
    window._file_list.setCurrentRow(2)
    assert "HDR PQ → SDR" in window._asset_info.text()

    window.load_files([root / "f09_sdr_10bit.mp4"])
    qtbot.waitUntil(lambda: window._pending_add == 0, timeout=5000)
    assert len(window._assets) == 4, window._status.text()
    qtbot.waitUntil(
        lambda: (
            len(window._assets) == 4
            and window.canvas._snapshot is not None
            and len(window.canvas._snapshot.frames) == 4
        )
    )
    window._file_list.setCurrentRow(3)
    assert "源 10-bit" in window._asset_info.text()
    assert "HDR/BT.2020" not in window._asset_info.text()


@pytest.mark.gui
def test_screenshot_write_failure_preserves_displayed_group(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and len(window._assets) == 2
            and window._pending_add == 0
        ),
        timeout=5000,
    )
    original = window.canvas._snapshot
    not_a_directory = tmp_path / "existing-user-file.txt"
    not_a_directory.write_text("keep this content", encoding="utf-8")
    assert window.save_view_screenshot(not_a_directory) == original.group_id
    qtbot.waitUntil(lambda: "截图失败" in window._status.text(), timeout=5000)
    assert window.canvas._snapshot is original
    assert not_a_directory.read_text(encoding="utf-8") == "keep this content"


@pytest.mark.gui
def test_rapid_slider_requests_and_keyboard_steps_keep_latest_real_group(
    qtbot, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and len(window._assets) == 2
            and window._pending_add == 0
        ),
        timeout=5000,
    )
    window._mode.setCurrentIndex(1)
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    window._start_scrub()
    rng = random.Random(20260924)
    for index in range(99):
        window._slider.setValue(rng.randrange(10001))
        window._preview_scrub()
        if index % 10 == 0:
            qtbot.wait(1)
    window._slider.setValue(10000)
    window._finish_scrub()
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and window.canvas._snapshot.reference_ordinal == 71
        ),
        timeout=5000,
    )
    last_group = window.canvas._snapshot
    qtbot.wait(100)
    assert window.canvas._snapshot is last_group
    assert {frame.ordinal for frame in last_group.frames.values()} == {71}
    assert window._transport._results.qsize() <= window._transport._results.maxsize

    window._frame_input.setText("1")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 0, timeout=5000)
    window._play_button.setFocus()
    for _ in range(10):
        qtbot.keyClick(window, Qt.Key.Key_Right)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 10, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {10}
    for _ in range(10):
        qtbot.keyClick(window, Qt.Key.Key_Left)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 0, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {0}
    for _ in range(10):
        QApplication.sendEvent(
            window,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Right,
                Qt.KeyboardModifier.NoModifier,
                "",
                True,
            ),
        )
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 10, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {10}

    window._mode.setCurrentIndex(0)
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    window._time_input.setText("00:00:00.000")
    qtbot.keyClick(window._time_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 0, timeout=5000)
    window._step_unit.setCurrentIndex(1)
    window._step_amount.setText("1.000")
    qtbot.mouseClick(window._forward_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 30, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {30}
    transport = window._transport
    transport.seek_reference_frame(72)
    assert transport._pending is not None
    window.close()
    assert all(worker.join(timeout=0) for worker in transport._workers.values())
    assert window._loader.join(timeout=0)
    assert window._screenshot_worker.join(timeout=0)


@pytest.mark.gui
def test_slow_late_and_failed_route_never_mixes_gui_group(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: (
            window._current_display_snapshot() is not None
            and len(window._assets) == 2
            and window._pending_add == 0
        ),
        timeout=5000,
    )
    slow_id = tuple(window._assets)[1]
    transport = window._transport
    error_ordinal = (
        transport.mapper.map_reference_frame(18, transport.spec).targets[slow_id].ordinal
    )
    original = window.canvas._snapshot
    old_request_entered = Event()
    error_request_entered = Event()
    real_frame_at = PreciseDecoder.frame_at

    def injected_frame_at(self, ordinal):
        if self.asset.asset_id == slow_id:
            if ordinal == 1:
                time.sleep(0.2)
            if ordinal == 3:
                old_request_entered.set()
                time.sleep(0.2)
            if ordinal == error_ordinal:
                error_request_entered.set()
                raise DecodeError("注入的单路解码错误")
        return real_frame_at(self, ordinal)

    monkeypatch.setattr(PreciseDecoder, "frame_at", injected_frame_at)
    transport.seek_reference_frame(2)
    qtbot.waitUntil(
        lambda: transport._pending is not None and len(transport._pending._frames) == 1,
        timeout=5000,
    )
    assert window.canvas._snapshot is original
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 1, timeout=5000)
    assert {frame.ordinal for frame in window.canvas._snapshot.frames.values()} == {1}

    transport.seek_reference_frame(4)
    qtbot.waitUntil(old_request_entered.is_set, timeout=5000)
    transport.seek_reference_frame(5)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 4, timeout=5000)
    latest = window.canvas._snapshot
    qtbot.wait(100)
    assert window.canvas._snapshot is latest
    assert {frame.ordinal for frame in latest.frames.values()} == {4}

    transport.seek_reference_frame(18)
    assert transport._pending.targets.targets[slow_id].ordinal == error_ordinal
    qtbot.waitUntil(error_request_entered.is_set, timeout=5000)
    qtbot.waitUntil(lambda: transport.state is TransportState.ERROR, timeout=5000)
    assert window.canvas._snapshot is latest
    assert "注入的单路解码错误" in window._status.text()
    transport.seek_reference_frame(7)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 6, timeout=5000)
    assert {
        asset_id: frame.ordinal for asset_id, frame in window.canvas._snapshot.frames.items()
    } == {
        asset_id: target.ordinal
        for asset_id, target in transport.mapper.map_reference_frame(
            7, transport.spec
        ).targets.items()
    }


@pytest.mark.gui
def test_single_video_can_play_pause_and_locate(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    assert len(window.canvas._snapshot.frames) == 1
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal >= 1, timeout=5000)
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    assert window._transport.state.value == "paused"
    window._frame_input.setText("49")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 48, timeout=5000)
    assert next(iter(window.canvas._snapshot.frames.values())).ordinal == 48


@pytest.mark.gui
def test_ctrl_wheel_links_view_and_black_bar_does_not_zoom(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    canvas = window.canvas
    first = canvas._order[0]
    transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas._order,
        canvas._assets,
        canvas._snapshot,
        canvas.view_regions,
        first,
        layout=canvas.layout_mode,
    )
    assert transform is not None
    x, y = transform.forward(0.5, 0.5)

    def wheel(px: float, py: float, ctrl: bool) -> None:
        local = QPointF(px, py)
        event = QWheelEvent(
            local,
            canvas.mapToGlobal(QPoint(round(px), round(py))),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        canvas.wheelEvent(event)

    wheel(x, y, False)
    wheel(x, 10, True)
    assert canvas.view_regions[first].width_u == 1
    wheel(x, y, True)
    assert canvas.view_regions[first].width_u < 1
    assert len(set(canvas.view_regions.values())) == 1
    qtbot.mouseClick(window._fit_button, Qt.MouseButton.LeftButton)
    assert canvas.view_regions[first].width_u == 1
    qtbot.mouseClick(window._roi_button, Qt.MouseButton.LeftButton)
    start = QPoint(round(x - 70), round(y - 35))
    end = QPoint(round(x + 70), round(y + 35))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert canvas.view_regions[first].width_u < 1
    assert len(set(canvas.view_regions.values())) == 1
    before = canvas.view_regions[first]
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
    qtbot.mouseMove(canvas, pos=QPoint(round(x + 2), round(y + 2)))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x + 2), round(y + 2)))
    assert canvas.view_regions[first] == before
    qtbot.mouseClick(window._roi_button, Qt.MouseButton.LeftButton)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
    qtbot.mouseMove(canvas, pos=QPoint(round(x + 20), round(y)))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x + 20), round(y)))
    assert canvas.view_regions[first].center_u != before.center_u

    qtbot.mouseClick(window._fit_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._roi_button, Qt.MouseButton.LeftButton)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x), 10))
    qtbot.mouseMove(canvas, pos=QPoint(round(x + 20), 30))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x + 20), 30))
    assert canvas.view_regions[first] == ViewRegion()
    edge_transform = pane_transform(
        canvas.width(),
        canvas.height(),
        canvas._order,
        canvas._assets,
        canvas._snapshot,
        canvas.view_regions,
        first,
        layout=canvas.layout_mode,
    )
    assert edge_transform is not None
    content = edge_transform.content_rect
    start = QPoint(round(content.right) - 7, round(content.bottom) - 7)
    end = QPoint(round(content.right) - 2, round(content.bottom) - 2)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    edge_region = canvas.view_regions[first]
    assert 0 < edge_region.width_u < 1
    assert 0 < edge_region.height_v < 1
    assert edge_region.center_u + edge_region.width_u / 2 <= 1
    assert edge_region.center_v + edge_region.height_v / 2 <= 1
    assert len(set(canvas.view_regions.values())) == 1
    qtbot.mouseClick(window._fit_button, Qt.MouseButton.LeftButton)
    assert all(region.width_u == region.height_v == 1 for region in canvas.view_regions.values())


@pytest.mark.gui
@pytest.mark.parametrize("count", [1, 3, 6])
def test_theme_and_accent_preserve_group_pixels_and_view(
    qtbot, tmp_path: Path, monkeypatch, count: int
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    settings_path = tmp_path / "settings.toml"
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe,
        software=True,
        settings_path=settings_path,
    )
    qtbot.addWidget(window)
    window.show()
    path = root / "f05_h264_bframes.mp4"
    window.load_files([path] * count)
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == count
        ),
        timeout=5000,
    )
    first = window.canvas._order[0]
    window.canvas._set_region(first, window.canvas.view_regions[first].zoom_at(0.5, 0.5, 2))
    snapshot = window.canvas._snapshot
    regions = window.canvas.view_regions
    pixels = {key: frame.rgb.tobytes() for key, frame in snapshot.frames.items()}

    themes = [window._theme_combo.itemData(index) for index in range(window._theme_combo.count())]
    accents = ["follow", "#000000", "#ff0000", "#0070c0", "#7030a0"]
    for theme in themes:
        window._theme_combo.setCurrentIndex(window._theme_combo.findData(theme))
        for accent in accents:
            window.set_accent(accent)
            assert window.canvas._snapshot is snapshot
            assert window.canvas.view_regions == regions
            assert {key: frame.rgb.tobytes() for key, frame in snapshot.frames.items()} == pixels
            assert window._transport.displayed is snapshot
            assert load_settings(settings_path) == AppSettings(
                theme=window._theme_combo.currentData(),
                accent=accent,
            )

    if count == 1:
        from video_compare.ui import theme as theme_module

        window._theme_combo.setCurrentIndex(window._theme_combo.findData("system"))
        stylesheet_before = QApplication.instance().styleSheet()
        actual_dark = theme_module.is_dark(window._settings, QApplication.instance())
        with monkeypatch.context() as patch:
            patch.setattr(theme_module, "is_dark", lambda _settings, _app: not actual_dark)
            QApplication.instance().styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
            assert QApplication.instance().styleSheet() != stylesheet_before
            assert window.canvas._snapshot is snapshot
            assert window.canvas.view_regions == regions
            assert {key: frame.rgb.tobytes() for key, frame in snapshot.frames.items()} == pixels
        window._theme_combo.setCurrentIndex(window._theme_combo.findData("dark"))
        stylesheet_before = QApplication.instance().styleSheet()
        QApplication.instance().styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
        assert QApplication.instance().styleSheet() == stylesheet_before

    if count == 3:
        qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal >= 2, timeout=5000)
        previous_ordinal = window.canvas._snapshot.reference_ordinal
        window._theme_combo.setCurrentIndex(window._theme_combo.findData("light"))
        window.set_accent("#00b0f0")
        assert window.canvas.view_regions == regions
        qtbot.waitUntil(
            lambda: window.canvas._snapshot.reference_ordinal > previous_ordinal,
            timeout=5000,
        )
        assert len(window.canvas._snapshot.frames) == 3
        qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
        window._theme_combo.setCurrentIndex(window._theme_combo.findData("dark"))
        window.set_accent("#7030a0")

    window.close()
    reopened = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe,
        software=True,
        settings_path=settings_path,
    )
    qtbot.addWidget(reopened)
    assert reopened._theme_combo.currentData() == "dark"
    assert reopened._settings.accent == "#7030a0"


@pytest.mark.gui
def test_file_drop_remove_replace_and_seventh_limit(qtbot, tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    first_path = root / "f05_h264_bframes.mp4"
    second_path = root / "f05_ffv1_oracle.mkv"
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(first_path)), QUrl.fromLocalFile(str(second_path))])
    enter = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(drop)
    assert drop.isAccepted()
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    ids = tuple(window._assets)
    assert [asset.path for asset in window._assets.values()] == [first_path, second_path]
    assert str(first_path) in window._file_list.item(0).toolTip()

    window._file_list.setCurrentRow(1)
    assert window.replace_selected(root / "missing.mp4") is False
    assert tuple(window._assets) == ids
    assert window.replace_selected(first_path) is True
    qtbot.waitUntil(lambda: tuple(window._assets)[1] != ids[1], timeout=5000)
    assert tuple(window._assets)[0] == ids[0]
    assert tuple(window._assets)[1] != ids[1]
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None
            and set(window.canvas._snapshot.frames) == set(window._assets)
        ),
        timeout=5000,
    )
    replaced_id = tuple(window._assets)[1]
    window._file_list.setCurrentRow(0)
    window.remove_selected()
    assert tuple(window._assets) == (replaced_id,)
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None
            and set(window.canvas._snapshot.frames) == {replaced_id}
        ),
        timeout=5000,
    )

    warnings = []
    monkeypatch.setattr(
        "video_compare.ui.main_window.QMessageBox.warning", lambda *args: warnings.append(args[2])
    )
    window.load_files([first_path] * 6)
    qtbot.waitUntil(lambda: len(window._assets) == 6, timeout=5000)
    assert len(window._assets) == 6
    assert len(warnings) == 1 and "最多导入 6 路" in warnings[0]
    assert window._file_list.count() == 6
    assert len(set(window._assets)) == 6
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 6,
        timeout=5000,
    )
    controller = window._transport
    window.close()
    assert all(worker.join(timeout=0) for worker in controller._workers.values())


@pytest.mark.gui
def test_configured_frame_and_second_steps_and_edges(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    window._step_amount.setText("5")
    qtbot.mouseClick(window._forward_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 5, timeout=5000)
    assert window._transport.requested_frame == 5
    start_time = window._transport.requested_time
    window._step_unit.setCurrentIndex(1)
    window._step_amount.setText("0.01")
    for _ in range(5):
        qtbot.mouseClick(window._forward_button, Qt.MouseButton.LeftButton)
    assert window._transport.requested_time == start_time + Fraction(5, 100)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 6, timeout=5000)
    window._time_input.setFocus()
    before = window._transport.requested_time
    qtbot.keyClick(window._time_input, Qt.Key.Key_Left)
    assert window._transport.requested_time == before
    window.setFocus()
    qtbot.keyClick(window, Qt.Key.Key_End)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 71, timeout=5000)
    qtbot.keyClick(window, Qt.Key.Key_Home)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 0, timeout=5000)


@pytest.mark.gui
def test_indexing_does_not_block_ui_and_close_cancels(qtbot, tmp_path: Path, monkeypatch) -> None:
    entered = Event()

    def slow_probe(path, *, ffprobe_path, asset_id, cancelled):
        entered.set()
        while not cancelled():
            time.sleep(0.005)
        raise ProbeCancelled("close cancelled probe")

    monkeypatch.setattr("video_compare.media.loading.probe_video", slow_probe)
    window = MainWindow(tmp_path / "index.sqlite3", software=True)
    qtbot.addWidget(window)
    window.show()
    start = time.monotonic()
    window.load_files([Path("fake-slow.mp4")])
    assert time.monotonic() - start < 0.1
    assert entered.wait(timeout=1)
    fired = []
    QTimer.singleShot(20, lambda: fired.append(True))
    qtbot.waitUntil(lambda: bool(fired), timeout=500)
    window.close()
    assert window._loader.join(timeout=1)


@pytest.mark.gui
def test_reference_switch_preserves_displayed_content(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f04_vfr.mkv"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    window._time_input.setText("00:00:00.500")
    qtbot.keyClick(window._time_input, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: window.canvas._snapshot.requested_global_time == Fraction(1, 2),
        timeout=5000,
    )
    before = window.canvas._snapshot
    old_frames = {key: frame.ordinal for key, frame in before.frames.items()}
    new_reference = tuple(window._assets)[1]
    window._reference_combo.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window._transport.spec.reference_id == new_reference
            and window.canvas._snapshot.group_id != before.group_id
        ),
        timeout=5000,
    )
    assert {
        key: frame.ordinal for key, frame in window.canvas._snapshot.frames.items()
    } == old_frames
    assert window._transport.displayed.requested_global_time == Fraction(1, 2)


@pytest.mark.gui
def test_24_60_vfr_modes_offsets_and_reference_match_ffprobe(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    paths = [root / name for name in ("f02_24fps.mkv", "f03_60fps.mkv", "f04_vfr.mkv")]
    assert all(path.is_file() for path in paths), "先运行 fixture 生成器"

    def expected_ordinal(path: Path, local_time: Fraction) -> int:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        source_times = [
            Fraction(line.strip()) for line in result.stdout.splitlines() if line.strip()
        ]
        local_times = [value - source_times[0] for value in source_times]
        return bisect_right(local_times, local_time) - 1

    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files(paths)
    qtbot.waitUntil(
        lambda: (
            window._pending_add == 0
            and window.canvas._snapshot is not None
            and len(window.canvas._snapshot.frames) == 3
        ),
        timeout=8000,
    )
    first, second, third = tuple(window._assets)
    for row, time_offset, frame_offset in ((1, "+0.200", "+5"), (2, "-0.100", "-3")):
        window._file_list.setCurrentRow(row)
        window._time_offset_input.setText(time_offset)
        window._frame_offset_input.setText(frame_offset)
        qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    window._time_input.setText("00:00:00.500")
    qtbot.keyClick(window._time_input, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None
            and window.canvas._snapshot.requested_global_time == Fraction(1, 2)
        ),
        timeout=5000,
    )
    assert {
        asset_id: frame.ordinal for asset_id, frame in window.canvas._snapshot.frames.items()
    } == {
        first: expected_ordinal(paths[0], Fraction(1, 2)),
        second: expected_ordinal(paths[1], Fraction(7, 10)),
        third: expected_ordinal(paths[2], Fraction(2, 5)),
    }

    window._mode.setCurrentIndex(1)
    window._frame_input.setText("30")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None and window.canvas._snapshot.reference_ordinal == 29
        ),
        timeout=5000,
    )
    assert {key: frame.ordinal for key, frame in window.canvas._snapshot.frames.items()} == {
        first: 29,
        second: 34,
        third: 26,
    }
    window._reference_combo.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window._transport.spec.reference_id == second
            and window.canvas._snapshot is not None
            and window.canvas._snapshot.reference_ordinal == 34
        ),
        timeout=5000,
    )
    assert {key: frame.ordinal for key, frame in window.canvas._snapshot.frames.items()} == {
        first: 29,
        second: 34,
        third: 26,
    }


@pytest.mark.gui
def test_time_and_frame_offsets_rebase_and_empty_range(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    first, second = tuple(window._assets)
    window._file_list.setCurrentRow(1)
    window._time_offset_input.setText("+0.200")
    window._frame_offset_input.setText("+5")
    qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None
            and window.canvas._snapshot.frames[second].ordinal == 6
        ),
        timeout=5000,
    )
    assert window._transport.spec.time_offsets[second] == Fraction(1, 5)
    assert window.canvas._snapshot.frames[first].ordinal == 0

    window._mode.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window.canvas._snapshot is not None
            and window.canvas._snapshot.frames[second].ordinal == 5
        ),
        timeout=5000,
    )
    assert window._transport.spec.frame_offsets[second] == 5
    window._reference_combo.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window._transport.spec.reference_id == second
            and window.canvas._snapshot is not None
            and window.canvas._snapshot.reference_ordinal == 5
        ),
        timeout=5000,
    )
    assert window._transport.spec.frame_offsets[first] == -5
    assert window._transport.spec.time_offsets[first] == Fraction(-1, 5)
    assert window.canvas._snapshot.frames[first].ordinal == 0
    assert window.canvas._snapshot.frames[second].ordinal == 5

    window._time_offset_input.setText("1.000")
    qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    assert "基准视频 Offset 必须为 0" in window._status.text()
    assert window._transport.spec.time_offsets[second] == 0
    window._file_list.setCurrentRow(0)
    window._time_offset_input.setText("0.000")
    window._frame_offset_input.setText("-1000")
    qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    assert not window._play_button.isEnabled()
    assert window.canvas._snapshot is None
    window._frame_offset_input.setText("-5")
    qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    assert window._play_button.isEnabled()


@pytest.mark.gui
def test_speed_and_loop_controls_use_displayed_group(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    window._speed_combo.setCurrentIndex(4)
    assert window._transport.speed == 4
    qtbot.mouseClick(window._loop_in_button, Qt.MouseButton.LeftButton)
    assert window._transport.loop_start == 0
    window._frame_input.setText("2")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 1, timeout=5000)
    qtbot.mouseClick(window._loop_out_button, Qt.MouseButton.LeftButton)
    assert window._transport.loop_range.end == Fraction(1, 15)
    window._frame_input.setText("1")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 0, timeout=5000)
    qtbot.mouseClick(window._loop_button, Qt.MouseButton.LeftButton)
    assert window._transport.loop_enabled
    seen = []
    window._transport.group_ready.connect(lambda group: seen.append(group.reference_ordinal))
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: seen.count(0) >= 1, timeout=5000)
    window._speed_combo.setCurrentIndex(0)
    assert window._transport.speed == Fraction(1, 4)
    window._speed_combo.setCurrentIndex(3)
    assert window._transport.speed == 2
    qtbot.waitUntil(lambda: seen.count(0) >= 3, timeout=5000)
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    assert set(seen) == {0, 1}
    assert "已开启" in window._loop_status.text()


@pytest.mark.gui
def test_screenshots_use_one_frozen_real_frame_group(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    output = tmp_path / "frames"
    frozen = window.canvas._snapshot
    group_id = window.save_frame_screenshots(output)
    assert group_id == frozen.group_id
    qtbot.waitUntil(
        lambda: len(list(output.glob("*.png"))) == 2 and len(list(output.glob("*.json"))) == 2,
        timeout=5000,
    )
    for sidecar_path in output.glob("*.json"):
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["group_id"] == list(group_id)
        asset_id = sidecar["export_asset_id"]
        assert (
            sidecar["assets"][tuple(window._assets).index(asset_id)]["source_pts"]
            == frozen.frames[asset_id].pts
        )
        image = QImage(str(sidecar_path.with_suffix(".png"))).convertToFormat(
            QImage.Format.Format_RGB888
        )
        raw = np.frombuffer(image.constBits(), dtype=np.uint8)
        rgb = raw.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
        rgb = rgb.reshape(image.height(), image.width(), 3)
        assert np.array_equal(rgb, frozen.frames[asset_id].rgb)

    view_dir = tmp_path / "view"
    assert window.save_view_screenshot(view_dir) == group_id
    qtbot.waitUntil(
        lambda: len(list(view_dir.glob("*.png"))) == 1 and len(list(view_dir.glob("*.json"))) == 1,
        timeout=5000,
    )
    view_png = next(view_dir.glob("*.png"))
    view_json = json.loads(view_png.with_suffix(".json").read_text(encoding="utf-8"))
    view_image = QImage(str(view_png))
    assert view_json["group_id"] == list(group_id)
    assert view_json["kind"] == "view"
    assert view_json["png_size_px"] == [view_image.width(), view_image.height()]

    first = tuple(window._assets)[0]
    window.canvas._set_region(first, ViewRegion(0.5, 0.5, 0.5, 0.5))
    roi_dir = tmp_path / "roi_view"
    expected_roi_view = (
        window.canvas.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    )
    assert window.save_view_screenshot(roi_dir) == group_id
    qtbot.waitUntil(lambda: len(list(roi_dir.glob("*.json"))) == 1, timeout=5000)
    roi_png = next(roi_dir.glob("*.png"))
    roi_json = json.loads(roi_png.with_suffix(".json").read_text(encoding="utf-8"))
    actual_roi_view = QImage(str(roi_png)).convertToFormat(QImage.Format.Format_RGBA8888)
    assert actual_roi_view == expected_roi_view
    assert roi_json["group_id"] == list(group_id)
    assert all(item["view_region"]["width_u"] == 0.5 for item in roi_json["assets"])

    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal >= 2, timeout=5000)
    playing_snapshot = window.canvas._snapshot
    playing_dir = tmp_path / "playing"
    playing_group = window.save_frame_screenshots(playing_dir)
    assert playing_group == playing_snapshot.group_id
    qtbot.waitUntil(lambda: len(list(playing_dir.glob("*.json"))) == 2, timeout=5000)
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    for sidecar_path in playing_dir.glob("*.json"):
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["group_id"] == list(playing_group)
        asset_id = sidecar["export_asset_id"]
        assert (
            sidecar["assets"][tuple(window._assets).index(asset_id)]["ui_frame"]
            == playing_snapshot.frames[asset_id].ordinal + 1
        )


@pytest.mark.gui
def test_marker_returns_to_real_content_after_reference_switch(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    window._frame_input.setText("10")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 9, timeout=5000)
    original = {key: frame.ordinal for key, frame in window.canvas._snapshot.frames.items()}
    window._marker_title.setText("检查点")
    window._marker_note.setText("真实帧")
    qtbot.mouseClick(window._marker_add_button, Qt.MouseButton.LeftButton)
    assert window._marker_list.count() == 1
    marker = window._marker_store.markers[0]
    assert marker.title == "检查点" and marker.note == "真实帧"
    window._frame_input.setText("50")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.canvas._snapshot.reference_ordinal == 49, timeout=5000)
    window._reference_combo.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: window._transport.spec.reference_id == tuple(window._assets)[1], timeout=5000
    )
    qtbot.mouseClick(window._marker_jump_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            {key: frame.ordinal for key, frame in window.canvas._snapshot.frames.items()}
            == original
        ),
        timeout=5000,
    )
    monkeypatch.setattr(
        "video_compare.ui.main_window.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    window.close()
    assert window._closing_confirmed


@pytest.mark.gui
def test_reorder_and_maximize_keep_full_real_group_and_view(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    first, second = tuple(window._assets)
    transport = window._transport
    snapshot = window.canvas._snapshot
    window._linked_button.setChecked(False)
    region = ViewRegion(0.4, 0.5, 0.5, 0.5)
    window.canvas._set_region(first, region)
    assert window.canvas.view_regions[first] == region
    window._file_list.setCurrentRow(0)
    qtbot.mouseClick(window._move_down_button, Qt.MouseButton.LeftButton)
    assert window.canvas._order == (second, first)
    assert window._transport is transport
    assert window.canvas._snapshot is snapshot
    assert window._transport.spec.reference_id == first
    assert window._selected_asset_id() == first
    qtbot.mouseDClick(
        window.canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(window.canvas.width() * 3 // 4, window.canvas.height() // 2),
    )
    assert window.canvas._order == (first,)
    assert set(window.canvas._snapshot.frames) == {first, second}
    assert window.canvas.view_regions[first] == region
    assert window._transport is transport
    qtbot.keyClick(window.canvas, Qt.Key.Key_Escape)
    assert window.canvas._order == (second, first)
    assert window.canvas.view_regions[first] == region
    assert window.canvas._snapshot is snapshot
    second_region = ViewRegion(0.6, 0.5, 0.7, 0.7)
    window.canvas._set_region(second, second_region)
    window._file_list.setCurrentRow(0)
    assert window._selected_asset_id() == second
    window._linked_button.setChecked(True)
    assert window.canvas.view_regions == {first: second_region, second: second_region}
    assert window.canvas._snapshot is snapshot


@pytest.mark.gui
def test_native_pixel_mode_shows_real_frame_one_to_one(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=5000)
    asset_id = next(iter(window._assets))
    snapshot = window.canvas._snapshot
    window._pixel_mode_combo.setCurrentIndex(1)
    assert window.canvas.pixel_zoom == 1.0
    assert window._pixel_notice.isVisible()
    # 名称/帧信息叠在画面角落，逐像素比对时先隐藏，验证 1:1 映射本身。
    window.canvas.set_overlay_visible(False)
    transform = pane_transform(
        window.canvas.width(),
        window.canvas.height(),
        (asset_id,),
        window._assets,
        snapshot,
        window.canvas.view_regions,
        asset_id,
        pixel_zoom=1.0,
        device_pixel_ratio=window.canvas.devicePixelRatioF(),
        layout=window.canvas.layout_mode,
    )
    assert transform is not None
    rendered = window.canvas.grab().toImage().convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(rendered.constBits(), dtype=np.uint8)
    rgb = raw.reshape(rendered.height(), rendered.bytesPerLine())[:, : rendered.width() * 3]
    rgb = rgb.reshape(rendered.height(), rendered.width(), 3)
    content = transform.content_rect
    x, y = round(content.x), round(content.y)
    frame_rgb = snapshot.frames[asset_id].rgb
    assert content.width == frame_rgb.shape[1]
    assert content.height == frame_rgb.shape[0]
    assert np.array_equal(rgb[y : y + frame_rgb.shape[0], x : x + frame_rgb.shape[1]], frame_rgb)
    center = QPoint(round(content.x + content.width / 2), round(content.y + content.height / 2))
    wheel = QWheelEvent(
        QPointF(center),
        window.canvas.mapToGlobal(center),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    window.canvas.wheelEvent(wheel)
    assert window.canvas.pixel_zoom == pytest.approx(1.15)
    assert "1.15×" in window._pixel_notice.text()
    assert window.canvas._snapshot is snapshot
    window._pixel_mode_combo.setCurrentIndex(0)
    assert window.canvas.pixel_zoom is None


@pytest.mark.gui
def test_hundred_real_replace_remove_reload_cycles_release_old_workers(
    qtbot, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    first_path = root / "f05_h264_bframes.mp4"
    second_path = root / "f05_ffv1_oracle.mkv"
    window.load_files([first_path, second_path])
    qtbot.waitUntil(
        lambda: window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 2,
        timeout=5000,
    )
    first_id = tuple(window._assets)[0]
    for cycle in range(100):
        window._file_list.setCurrentRow(1)
        old_id = window._selected_asset_id()
        old_transport = window._transport
        replacement = first_path if cycle % 2 else second_path
        assert window.replace_selected(replacement)
        qtbot.waitUntil(
            lambda old_id=old_id: (
                old_id not in window._assets
                and window.canvas._snapshot is not None
                and len(window.canvas._snapshot.frames) == 2
                and set(window.canvas._snapshot.frames) == set(window._assets)
            ),
            timeout=5000,
        )
        assert tuple(window._assets)[0] == first_id
        assert all(worker.join(timeout=0) for worker in old_transport._workers.values())
        window._file_list.setCurrentRow(1)
        old_transport = window._transport
        window.remove_selected()
        qtbot.waitUntil(
            lambda: (
                window.canvas._snapshot is not None and len(window.canvas._snapshot.frames) == 1
            ),
            timeout=5000,
        )
        assert all(worker.join(timeout=0) for worker in old_transport._workers.values())
        window.load_files([second_path])
        qtbot.waitUntil(
            lambda: (
                window.canvas._snapshot is not None
                and len(window.canvas._snapshot.frames) == 2
                and window._pending_add == 0
            ),
            timeout=5000,
        )
    assert not window._pending_replacements
    assert window._pending_add == 0
    transport = window._transport
    window.close()
    assert all(worker.join(timeout=0) for worker in transport._workers.values())
    assert window._loader.join(timeout=0)


@pytest.mark.gui
def test_detached_route_holds_real_frame_and_rejoins_current_group(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: (
            window._transport is not None
            and window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    first, second = tuple(window._assets)
    window._file_list.setCurrentRow(0)
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    assert not window._excluded_ids
    assert "基准视频必须参与同步" in window._status.text()
    window._file_list.setCurrentRow(1)
    frozen = window._transport.displayed.frames[second]
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 1
            and window._current_display_snapshot() is not None
        ),
        timeout=5000,
    )
    assert window._transport.spec.participants == (first,)
    assert not window._reference_combo.model().item(1).isEnabled()
    assert window.canvas._snapshot.frames[second] is frozen
    assert window.canvas._snapshot.boundary_states[second] == "detached"
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._transport.displayed.reference_ordinal >= 2, timeout=5000)
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    assert window.canvas._snapshot.frames[second] is frozen
    window._frame_input.setText("20")
    qtbot.keyClick(window._frame_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window._transport.displayed.reference_ordinal == 19, timeout=5000)
    assert window.canvas._snapshot.frames[first].ordinal == 19
    assert window.canvas._snapshot.frames[second] is frozen
    output = tmp_path / "detached"
    assert window.save_frame_screenshots(output) == window.canvas._snapshot.group_id
    qtbot.waitUntil(lambda: len(list(output.glob("*.json"))) == 2, timeout=5000)
    sidecars = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*.json")]
    held = next(data for data in sidecars if data["export_asset_id"] == second)
    held_metadata = next(data for data in held["assets"] if data["asset_id"] == second)
    assert held_metadata["time_sync_state"] == "detached"
    assert held_metadata["ui_frame"] == frozen.ordinal + 1
    window._mode.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window._transport.spec.mode.value == "frame"
            and window._current_display_snapshot() is not None
        ),
        timeout=5000,
    )
    window._frame_offset_input.setText("+5")
    qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window._current_display_snapshot() is not None
        ),
        timeout=5000,
    )
    assert window._frame_offsets[second] == 5
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 2
            and window._transport.displayed.reference_ordinal == 19
        ),
        timeout=5000,
    )
    assert window.canvas._snapshot is window._transport.displayed
    assert window.canvas._snapshot.frames[second].ordinal == 24
    assert not window._held_frames
    assert window._reference_combo.model().item(1).isEnabled()
    window._file_list.setCurrentRow(1)
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None and len(window._transport.displayed.frames) == 1
        ),
        timeout=5000,
    )
    window._file_list.setCurrentRow(0)
    window.remove_selected()
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window._transport.spec.reference_id == second
            and window._transport.displayed.reference_ordinal == 24
        ),
        timeout=5000,
    )
    assert not window._excluded_ids
    assert window.canvas._snapshot.frames[second].ordinal == 24


@pytest.mark.gui
def test_detach_during_real_playback_keeps_single_clock_running(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: (
            window._transport is not None
            and window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    first, second = tuple(window._assets)
    window._file_list.setCurrentRow(1)
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._transport.displayed.reference_ordinal >= 2, timeout=5000)
    frozen = window._transport.displayed.frames[second]
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.state is TransportState.PLAYING
            and len(window._transport.displayed.frames) == 1
        ),
        timeout=5000,
    )
    after_detach = window._transport.displayed.reference_ordinal
    qtbot.waitUntil(
        lambda: window._transport.displayed.reference_ordinal > after_detach,
        timeout=5000,
    )
    assert window.canvas._snapshot.frames[second] is frozen
    assert first in window._transport.displayed.frames
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.state is TransportState.PLAYING
            and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    assert window.canvas._snapshot is window._transport.displayed
    qtbot.mouseClick(window._play_button, Qt.MouseButton.LeftButton)


@pytest.mark.gui
def test_detached_offset_rebases_when_switching_active_reference(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files(
        [root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv", root / "f05_h264_bframes.mp4"]
    )
    qtbot.waitUntil(
        lambda: (
            window._transport is not None
            and window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 3
        ),
        timeout=5000,
    )
    first, second, third = tuple(window._assets)
    for row, amount in ((1, "+0.200"), (2, "+0.100")):
        window._file_list.setCurrentRow(row)
        window._time_offset_input.setText(amount)
        qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: (
                window._transport.displayed is not None
                and len(window._transport.displayed.frames) == 3
            ),
            timeout=5000,
        )
    window._file_list.setCurrentRow(2)
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    held = window.canvas._snapshot.frames[third]
    window._time_input.setText("1.000")
    qtbot.keyClick(window._time_input, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window._transport.displayed.requested_global_time == Fraction(1)
        ),
        timeout=5000,
    )
    window._reference_combo.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window._transport.spec.reference_id == second
            and window._transport.displayed.requested_global_time == Fraction(6, 5)
        ),
        timeout=5000,
    )
    assert window.canvas._snapshot.frames[third] is held
    assert window._time_offsets == {
        first: Fraction(-1, 5),
        second: Fraction(0),
        third: Fraction(-1, 10),
    }
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None and len(window._transport.displayed.frames) == 3
        ),
        timeout=5000,
    )
    frames = window._transport.displayed.frames
    assert frames[first].ordinal == 30
    assert frames[second].ordinal == 36
    assert frames[third].ordinal == 33


@pytest.mark.gui
def test_rejoin_beyond_common_end_clamps_to_last_valid_group(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(tmp_path / "index.sqlite3", ffprobe_path=ffprobe, software=True)
    qtbot.addWidget(window)
    window.show()
    window.load_files([root / "f05_h264_bframes.mp4", root / "f05_ffv1_oracle.mkv"])
    qtbot.waitUntil(
        lambda: (
            window._transport is not None
            and window._transport.displayed is not None
            and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    first, second = tuple(window._assets)
    window._file_list.setCurrentRow(1)
    window._time_offset_input.setText("+2.000")
    qtbot.mouseClick(window._offset_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None and len(window._transport.displayed.frames) == 1
        ),
        timeout=5000,
    )
    window._time_input.setText("2.200")
    qtbot.keyClick(window._time_input, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None
            and window._transport.displayed.requested_global_time == Fraction(11, 5)
        ),
        timeout=5000,
    )
    qtbot.mouseClick(window._participant_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window._transport.displayed is not None and len(window._transport.displayed.frames) == 2
        ),
        timeout=5000,
    )
    snapshot = window._transport.displayed
    assert Fraction(0) < snapshot.requested_global_time < Fraction(1, 2)
    assert snapshot.frames[first].ordinal == 11
    assert snapshot.frames[second].ordinal == 71
    assert "已定位到最近边界" in window._status.text()
