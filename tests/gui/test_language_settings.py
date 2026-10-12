from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QTabWidget

from video_compare.services.settings import load_settings
from video_compare.ui.export_dialog import ExportOptionsDialog
from video_compare.ui.i18n import LANGUAGE_OPTIONS, translate
from video_compare.ui.main_window import MainWindow


def test_language_tabs_self_names_live_switch_and_persistence(qtbot, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.toml"
    window = MainWindow(tmp_path / "index.sqlite3", software=True, settings_path=settings_path)
    qtbot.addWidget(window)
    window.show()
    combo = window._settings_dialog.language_combo
    tabs = window._settings_dialog.findChild(QTabWidget)
    assert tabs is not None
    names = [label for _code, label in LANGUAGE_OPTIONS]
    setting_labels = {
        "zh_CN": "设置",
        "zh_TW": "設定",
        "en_US": "Settings",
        "ja_JP": "設定",
        "ko_KR": "설정",
        "fr_FR": "Paramètres",
        "de_DE": "Optionen",
        "es_ES": "Ajustes",
    }
    assert [combo.itemText(i) for i in range(combo.count())] == names
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["主题", "语言"]

    for code, _self_name in LANGUAGE_OPTIONS:
        combo.setCurrentIndex(combo.findData(code))
        assert load_settings(settings_path).language == code or code == "zh_CN"
        assert [combo.itemText(i) for i in range(combo.count())] == names
        assert [tabs.tabText(i) for i in range(tabs.count())] == [
            translate("主题"),
            translate("语言"),
        ]
        assert window._settings_button.text() == translate("设置")
        assert window._settings_button.text() == setting_labels[code]
        assert window._annotation_bar.link_checkbox.text() == translate("标注联动到全部画面")
        assert window._file_browser.choose_button.text() == translate("选择工作文件夹")
        assert not hasattr(window, "_media_mode")
        dialog = ExportOptionsDialog(window)
        assert dialog.windowTitle() == translate("导出对比图")
        dialog.close()

    assert window._add_button.text() == translate("选择工作文件夹")
    window._theme_combo.setCurrentIndex(window._theme_combo.findData("dark"))
    assert load_settings(settings_path).theme == "dark"
    assert load_settings(settings_path).language == "es_ES"
    window.close()

    reopened = MainWindow(tmp_path / "reopened.sqlite3", software=True, settings_path=settings_path)
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened._settings_dialog.language_combo.currentData() == "es_ES"
    assert reopened._settings_button.text() == translate("设置")
    assert reopened._theme_combo.currentData() == "dark"
    assert [reopened._settings_dialog.language_combo.itemText(i) for i in range(8)] == names
    reopened.close()


def test_switch_language_keeps_loaded_image_group(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (80, 48), (20, 40, 60)).save(first)
    Image.new("RGB", (80, 48), (70, 50, 30)).save(second)
    window = MainWindow(
        tmp_path / "index.sqlite3",
        software=True,
        settings_path=tmp_path / "settings.toml",
    )
    qtbot.addWidget(window)
    window.show()
    window.load_files([first, second])
    qtbot.waitUntil(
        lambda: window._image_snapshot is not None and len(window._image_snapshot.frames) == 2,
        timeout=10000,
    )
    snapshot = window._image_snapshot
    assert snapshot is not None
    frame_bytes = {key: bytes(frame.rgb.data) for key, frame in snapshot.frames.items()}
    combo = window._settings_dialog.language_combo
    for code, _self_name in LANGUAGE_OPTIONS:
        combo.setCurrentIndex(combo.findData(code))
        assert window._image_snapshot is snapshot
        assert {key: bytes(frame.rgb.data) for key, frame in snapshot.frames.items()} == frame_bytes
        assert len(window.canvas._snapshot.frames) == 2
    window.close()
