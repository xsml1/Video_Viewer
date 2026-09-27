"""Capture the bundled languages on a real Windows Qt window."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from video_compare.ui.i18n import LANGUAGE_OPTIONS
from video_compare.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    window = MainWindow(output / "index.sqlite3", settings_path=output / "settings.toml")
    window.show()
    app.processEvents()
    choices = window._settings_dialog.language_combo
    report = {}
    for code, self_name in LANGUAGE_OPTIONS:
        choices.setCurrentIndex(choices.findData(code))
        app.processEvents()
        names = [choices.itemText(index) for index in range(choices.count())]
        expected_names = [label for _value, label in LANGUAGE_OPTIONS]
        if names != expected_names:
            raise RuntimeError(f"language self names changed in {code}: {names}")
        window._settings_dialog.show()
        app.processEvents()
        if not window.grab().save(str(output / f"main-{code}.png"), "PNG"):
            raise RuntimeError(f"main screenshot failed: {code}")
        window._settings_dialog._tabs.setCurrentIndex(0)
        app.processEvents()
        if not window._settings_dialog.grab().save(
            str(output / f"settings-theme-{code}.png"), "PNG"
        ):
            raise RuntimeError(f"theme screenshot failed: {code}")
        window._settings_dialog._tabs.setCurrentIndex(1)
        app.processEvents()
        if not window._settings_dialog.grab().save(
            str(output / f"settings-language-{code}.png"), "PNG"
        ):
            raise RuntimeError(f"language screenshot failed: {code}")
        report[code] = {
            "self_name": self_name,
            "setting_button": window._settings_button.text(),
            "theme_tab": window._settings_dialog._tabs.tabText(0),
            "language_tab": window._settings_dialog._tabs.tabText(1),
            "window_size": [window.width(), window.height()],
        }
        window._settings_dialog.hide()
    window.close()
    (output / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Language UI verification passed: {output / 'result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
