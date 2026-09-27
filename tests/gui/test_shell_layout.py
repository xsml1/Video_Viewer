from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QSplitter

from video_compare.services.settings import AppSettings, load_settings
from video_compare.ui.canvas_common import pane_boxes
from video_compare.ui.main_window import MainWindow
from video_compare.ui.theme import FAMILIES, canvas_colors_for, palette_for


def make_window(qtbot, tmp_path: Path) -> MainWindow:
    ffprobe = (
        Path(__file__).resolve().parents[2]
        / ".codex-tools"
        / "ffmpeg"
        / "ffmpeg-9.0.1-essentials_build"
        / "bin"
        / "ffprobe.exe"
    )
    window = MainWindow(
        tmp_path / "index.sqlite3",
        ffprobe_path=ffprobe,
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    return window


def centre_y(window: MainWindow, widget) -> int:
    return widget.mapTo(window, widget.rect().center()).y()


def rgb(image) -> np.ndarray:
    converted = image.convertToFormat(image.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    rows = raw.reshape(converted.height(), converted.bytesPerLine())
    return rows[:, : converted.width() * 3].reshape(converted.height(), converted.width(), 3).copy()


def _colour_pixels(part: np.ndarray, color: str, tolerance: int = 48) -> int:
    target = np.array(QColor(color).getRgb()[:3], dtype=np.int16)
    diff = np.abs(part.astype(np.int16) - target).max(axis=2)
    return int((diff <= tolerance).sum())


@pytest.mark.gui
def test_top_bar_is_one_row_and_transport_sits_under_the_video(qtbot, tmp_path: Path) -> None:
    window = make_window(qtbot, tmp_path)
    top_bar = window._settings_button.parentWidget()
    assert top_bar.objectName() == "TopBar"
    window.setWindowTitle("Video Viewer")
    assert window.windowTitle() == "Video Viewer"
    same_row = [
        window._mode,
        window._reference_combo,
        window._pixel_mode_combo,
        window._layout_combo,
        window._fit_button,
        window._roi_button,
        window._linked_button,
        window._save_view_button,
        window._save_frames_button,
        window._export_button,
        window._settings_button,
        window._sidebar_button,
    ]
    centres = [centre_y(window, widget) for widget in same_row]
    assert max(centres) - min(centres) <= 2, "顶部工具栏必须只有一行"
    top_bottom = top_bar.mapTo(window, top_bar.rect().bottomLeft()).y()
    canvas_top = window.canvas.mapTo(window, window.canvas.rect().topLeft()).y()
    canvas_bottom = window.canvas.mapTo(window, window.canvas.rect().bottomLeft()).y()
    assert top_bottom <= canvas_top
    for control in (window._play_button, window._slider, window._speed_combo):
        assert control.mapTo(window, control.rect().topLeft()).y() >= canvas_bottom, (
            "播放相关控件应在视频窗口下方"
        )
    assert window._slider.mapTo(window, window._slider.rect().center()).y() < centre_y(
        window, window._play_button
    )
    mask = window.canvas.mask()
    assert not mask.isEmpty()
    assert not mask.contains(QPoint(0, 0))
    assert mask.contains(QPoint(15, 15))


@pytest.mark.gui
def test_sidebar_is_right_hand_resizable_and_hideable(qtbot, tmp_path: Path) -> None:
    window = make_window(qtbot, tmp_path)
    splitter = window._splitter
    assert isinstance(splitter, QSplitter)
    sidebar = window._sidebar
    assert sidebar.parentWidget() is splitter
    assert splitter.indexOf(sidebar) == 1, "信息栏应位于右侧"
    assert splitter.indexOf(window.canvas.parentWidget()) == 0
    splitter.setSizes([760, 420])
    wide = sidebar.width()
    splitter.setSizes([960, 260])
    narrow = sidebar.width()
    assert wide > narrow, "拖动分隔条应能改变信息栏宽度"
    assert 220 <= narrow <= 620
    window._sidebar_hide_button.click()
    assert sidebar.isVisible()
    qtbot.wait(70)
    assert 0 < sidebar.width() < narrow
    qtbot.waitUntil(lambda: not sidebar.isVisible(), timeout=1000)
    assert not window._sidebar_button.isChecked()
    window._sidebar_button.setChecked(True)
    assert sidebar.isVisible()
    qtbot.wait(70)
    assert 0 < sidebar.width() < narrow
    qtbot.waitUntil(lambda: window._sidebar_animation is None, timeout=1000)
    assert sidebar.width() == pytest.approx(narrow, abs=8)
    window._sidebar_button.setChecked(False)
    qtbot.wait(60)
    window._sidebar_button.setChecked(True)
    qtbot.waitUntil(lambda: window._sidebar_animation is None, timeout=1000)
    assert sidebar.isVisible()
    assert sidebar.width() >= 220


@pytest.mark.gui
def test_colour_schemes_apply_to_workspace_and_function_areas(qtbot, tmp_path: Path) -> None:
    required = {"morandi", "cream", "retro", "cyberpunk", "macaron"}
    assert required <= set(FAMILIES)
    assert FAMILIES["codex"].label == "清爽极简"
    app = QApplication.instance()
    combinations = {
        key: (
            palette_for(AppSettings(theme="light", scheme=key), app),
            canvas_colors_for(AppSettings(theme="light", scheme=key), app),
        )
        for key in FAMILIES
    }
    fingerprints = {
        key: (
            shell.window,
            shell.surface,
            shell.accent,
            workspace.background,
            workspace.surface,
        )
        for key, (shell, workspace) in combinations.items()
    }
    assert len(set(fingerprints.values())) == len(FAMILIES), "每个色系应有各自的颜色组合"
    for key in FAMILIES:
        dark_shell = palette_for(AppSettings(theme="dark", scheme=key), app)
        assert dark_shell.window != combinations[key][0].window
    picks = {
        color: palette_for(
            AppSettings(theme="light", scheme="codex", function_color=color), app
        ).surface
        for color in ("#ff0000", "#00b050", "#0070c0", "#7030a0")
    }
    assert len(set(picks.values())) == len(picks), "功能区选定颜色应决定界面底色"

    window = make_window(qtbot, tmp_path)
    listed = {window._scheme_combo.itemData(index) for index in range(window._scheme_combo.count())}
    assert required <= listed
    window._scheme_combo.setCurrentIndex(window._scheme_combo.findData("codex"))
    window.set_role_color("function", "#00e5ff")
    window.set_role_color("workspace", "#f3d5b5")
    window.set_role_color("overlay", "#00ff00")
    saved = load_settings(tmp_path / "settings.toml")
    assert (
        saved.scheme,
        saved.function_color,
        saved.workspace_color,
        saved.overlay_color,
    ) == ("codex", "#00e5ff", "#f3d5b5", "#00ff00")
    shell = palette_for(saved, app)
    workspace = canvas_colors_for(saved, app)
    assert shell.surface != workspace.surface
    assert window.canvas._colors.background == workspace.background
    assert window.canvas._colors.accent == workspace.accent
    assert window.canvas._colors.overlay == "#00ff00"


@pytest.mark.gui
def test_colour_grid_offers_theme_shades_and_standard_colours(qtbot, tmp_path: Path) -> None:
    window = make_window(qtbot, tmp_path)
    grid = window._color_grid
    family = FAMILIES["macaron"]
    window._scheme_combo.setCurrentIndex(window._scheme_combo.findData("macaron"))
    # 8 theme colours × (base + 5 shades) plus 15 standard colours.
    assert grid.swatch_count() == len(family.colors) * 6 + 15
    for role, colour in (
        ("workspace", "#7030a0"),
        ("function", "#0070c0"),
        ("accent", "#ffc000"),
        ("overlay", "#ff0000"),
    ):
        window._settings_dialog.role_button(role).click()
        assert window._settings_dialog.role == role
        window._color_grid.color_picked.emit(colour)
        saved = load_settings(tmp_path / "settings.toml")
        assert getattr(saved, f"{role}_color" if role != "accent" else "accent") == colour
    assert window.canvas._colors.overlay == "#ff0000"
    window._settings_dialog.role_button("accent").click()
    window._settings_dialog.follow_button.click()
    assert window._settings.accent == "follow"
    assert window.canvas._colors.accent == family.base


@pytest.mark.gui
def test_overlay_labels_sit_in_the_picture_corners(qtbot, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "generated"
    window = make_window(qtbot, tmp_path)
    window.load_files([root / "f05_h264_bframes.mp4"])
    qtbot.waitUntil(lambda: window.canvas._snapshot is not None, timeout=10000)
    canvas = window.canvas
    assert window._settings.overlay_color == "#00b050"
    order = canvas.display_order
    box = pane_boxes(canvas.width(), canvas.height(), order, window._assets, canvas._snapshot)[
        order[0]
    ]
    assert canvas.overlay_visible is True
    rendered = rgb(canvas.grab().toImage())
    quadrant = {
        "top_left": rendered[
            round(box.y) : round(box.y + box.height / 3),
            round(box.x) : round(box.x + box.width / 3),
        ],
        "top_right": rendered[
            round(box.y) : round(box.y + box.height / 3),
            round(box.right - box.width / 3) : round(box.right),
        ],
        "bottom_right": rendered[
            round(box.bottom - box.height / 3) : round(box.bottom),
            round(box.right - box.width / 3) : round(box.right),
        ],
        "bottom_left": rendered[
            round(box.bottom - box.height / 3) : round(box.bottom),
            round(box.x) : round(box.x + box.width / 3),
        ],
    }
    counts = {
        name: _colour_pixels(part, window._settings.overlay_color)
        for name, part in quadrant.items()
    }
    assert counts["top_left"] > 20, counts
    assert counts["bottom_right"] > 20, counts
    assert counts["top_right"] < 5 and counts["bottom_left"] < 5, counts
    window.set_role_color("overlay", "#ff00ff")
    canvas.update()
    rendered = rgb(canvas.grab().toImage())
    top_left = rendered[
        round(box.y) : round(box.y + box.height / 3),
        round(box.x) : round(box.x + box.width / 3),
    ]
    assert _colour_pixels(top_left, "#ff00ff") > 20
    assert _colour_pixels(top_left, "#00b050") < 5
