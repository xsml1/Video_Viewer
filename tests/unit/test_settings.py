from __future__ import annotations

from pathlib import Path

from video_compare.services.settings import AppSettings, load_settings, save_settings


def test_settings_round_trip_and_atomic_replacement(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.toml"
    assert load_settings(path) == AppSettings()
    first = AppSettings(theme="dark", accent="#10b981")
    save_settings(path, first)
    assert load_settings(path) == first
    second = AppSettings(
        theme="light",
        accent="#7030a0",
        scheme="morandi",
        workspace_color="#7fd1c1",
        function_color="#00e5ff",
        overlay_color="#ff0000",
    )
    save_settings(path, second)
    assert load_settings(path) == second
    assert list(path.parent.iterdir()) == [path]


def test_invalid_settings_fall_back_without_overwriting_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    for content in ('[app]\ntheme = "neon"\n', 'app = "wrong type"\n', "[app\n"):
        path.write_text(content, encoding="utf-8")
        assert load_settings(path) == AppSettings()
        assert path.read_text(encoding="utf-8") == content


def test_unknown_colour_entries_fall_back_per_field(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text(
        '[app]\nscheme = "morandi"\naccent = "blue"\n'
        'workspace_color = "unknown"\noverlay_color = "#00ff00"\n',
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded.scheme == "morandi"
    assert loaded.accent == "follow"
    assert loaded.workspace_color == "follow"
    assert loaded.overlay_color == "#00ff00"
    assert loaded.function_color == "follow"
    assert path.read_text(encoding="utf-8").startswith("[app]")


def test_default_overlay_colour_is_green(tmp_path: Path) -> None:
    assert AppSettings().overlay_color == "#00b050"
    assert load_settings(tmp_path / "missing.toml").overlay_color == "#00b050"
