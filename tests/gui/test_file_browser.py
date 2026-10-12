from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from video_compare.ui.file_browser import FileBrowser


def make_browser(qtbot) -> FileBrowser:
    browser = FileBrowser()
    qtbot.addWidget(browser)
    browser.resize(350, 550)
    browser.show()
    return browser


def visible_names(browser: FileBrowser) -> set[str]:
    root = browser.tree.rootIndex()
    return {
        browser.model.fileName(browser.model.index(row, 0, root))
        for row in range(browser.model.rowCount(root))
    }


def wait_for_names(qtbot, browser: FileBrowser, names: set[str]) -> None:
    qtbot.waitUntil(lambda: visible_names(browser) == names, timeout=5000)


def double_click(qtbot, browser: FileBrowser, path: Path) -> None:
    index = browser.model.index(str(path))
    assert index.isValid()
    browser.tree.scrollTo(index)
    position = browser.tree.visualRect(index).center()
    assert browser.tree.viewport().rect().contains(position)
    qtbot.mouseClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    qtbot.mouseDClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=position)


@pytest.mark.gui
def test_real_folder_lists_both_media_types_and_navigates_by_double_click(
    qtbot, tmp_path: Path
) -> None:
    folder = tmp_path / "中文 工作文件夹"
    folder.mkdir()
    child = folder / "下一级 文件夹"
    child.mkdir()
    Image.new("RGB", (12, 8), (12, 90, 140)).save(folder / "中文 图像.PNG")
    video_source = Path(__file__).parents[1] / "assets" / "generated" / "f05_h264_bframes.mp4"
    shutil.copyfile(video_source, folder / "中文 视频.mp4")
    (folder / "说明.txt").write_text("不显示的普通文件", encoding="utf-8")

    browser = make_browser(qtbot)
    assert browser.current_directory is None
    assert browser.set_directory(folder)
    wait_for_names(qtbot, browser, {child.name, "中文 图像.PNG", "中文 视频.mp4"})
    assert browser.model.isReadOnly()
    assert browser.path_edit.text() == str(folder)
    double_click(qtbot, browser, child)
    qtbot.waitUntil(lambda: browser.current_directory == child)
    wait_for_names(qtbot, browser, set())
    qtbot.mouseClick(browser.up_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: browser.current_directory == folder)
    wait_for_names(qtbot, browser, {child.name, "中文 图像.PNG", "中文 视频.mp4"})
    assert (folder / "说明.txt").read_text(encoding="utf-8") == "不显示的普通文件"


@pytest.mark.gui
def test_media_double_click_signals_full_paths_and_space_never_activates(
    qtbot, tmp_path: Path
) -> None:
    image = tmp_path / "带 空格.png"
    Image.new("RGB", (5, 3), (19, 31, 43)).save(image)
    video = tmp_path / "视频 空格.mp4"
    video_source = Path(__file__).parents[1] / "assets" / "generated" / "f05_h264_bframes.mp4"
    shutil.copyfile(video_source, video)
    before = hashlib.sha256(image.read_bytes()).hexdigest()
    before_video = hashlib.sha256(video.read_bytes()).hexdigest()
    browser = make_browser(qtbot)
    browser.set_directory(tmp_path)
    wait_for_names(qtbot, browser, {image.name, video.name})
    activated: list[str] = []
    browser.file_activated.connect(activated.append)
    double_click(qtbot, browser, image)
    assert activated == [str(image)]
    double_click(qtbot, browser, video)
    assert activated == [str(image), str(video)]
    qtbot.keyClick(browser.tree, Qt.Key.Key_Space)
    qtbot.keyClick(browser.tree, Qt.Key.Key_Space)
    assert activated == [str(image), str(video)]
    assert hashlib.sha256(image.read_bytes()).hexdigest() == before
    assert hashlib.sha256(video.read_bytes()).hexdigest() == before_video


@pytest.mark.gui
def test_back_forward_history_replaces_abandoned_branch(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    third = tmp_path / "third"
    for directory in (first, second, third):
        directory.mkdir()
    browser = make_browser(qtbot)
    assert browser.set_directory(first)
    assert browser.set_directory(second)
    assert browser.back_button.isEnabled()
    assert not browser.forward_button.isEnabled()
    browser.back_button.click()
    assert browser.current_directory == first
    assert not browser.back_button.isEnabled()
    assert browser.forward_button.isEnabled()
    browser.forward_button.click()
    assert browser.current_directory == second
    browser.back_button.click()
    assert browser.set_directory(third)
    assert not browser.forward_button.isEnabled()
    browser.back_button.click()
    assert browser.current_directory == first
    browser.forward_button.click()
    assert browser.current_directory == third


@pytest.mark.gui
def test_path_entry_and_invalid_directory_preserve_current_folder(qtbot, tmp_path: Path) -> None:
    child = tmp_path / "相对 路径"
    child.mkdir()
    image = tmp_path / "image.png"
    Image.new("RGB", (3, 2)).save(image)
    browser = make_browser(qtbot)
    browser.set_directory(tmp_path)
    browser.path_edit.setText(child.name)
    qtbot.keyClick(browser.path_edit, Qt.Key.Key_Return)
    assert browser.current_directory == child
    errors: list[str] = []
    browser.error_occurred.connect(errors.append)
    assert not browser.set_directory(image)
    assert browser.current_directory == child
    assert str(image) in errors[-1]
    assert "不是文件夹" in browser.status_label.text()
    browser.path_edit.setText(str(tmp_path / "不存在"))
    qtbot.keyClick(browser.path_edit, Qt.Key.Key_Return)
    assert browser.current_directory == child
    assert "不存在" in errors[-1]
    browser.back_button.click()
    assert browser.current_directory == tmp_path


@pytest.mark.gui
def test_refresh_reads_changes_and_keeps_navigation_history(qtbot, tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    browser = make_browser(qtbot)
    browser.set_directory(tmp_path)
    browser.set_directory(child)
    wait_for_names(qtbot, browser, set())
    image = child / "added.png"
    Image.new("RGB", (3, 2), (51, 62, 73)).save(image)
    browser.refresh_button.click()
    wait_for_names(qtbot, browser, {image.name})
    assert browser.current_directory == child
    browser.back_button.click()
    assert browser.current_directory == tmp_path
    assert not browser.back_button.isEnabled()


@pytest.mark.gui
def test_choose_folder_cancel_keeps_current_directory(qtbot, tmp_path: Path, monkeypatch) -> None:
    browser = make_browser(qtbot)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path))
    browser.choose_button.click()
    assert browser.current_directory == tmp_path
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: "")
    browser.choose_button.click()
    assert browser.current_directory == tmp_path
    assert not browser.back_button.isEnabled()
