from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ThemeName = Literal["system", "light", "dark"]
LanguageName = Literal["zh_CN", "zh_TW", "en_US", "ja_JP", "ko_KR", "fr_FR", "de_DE", "es_ES"]
LayoutName = Literal["auto", "grid", "horizontal", "vertical"]
ColorName = str  # "follow" or an explicit "#rrggbb" picked from the swatch grid

THEMES = ("system", "light", "dark")
LANGUAGES = ("zh_CN", "zh_TW", "en_US", "ja_JP", "ko_KR", "fr_FR", "de_DE", "es_ES")
LAYOUT_NAMES = ("auto", "grid", "horizontal", "vertical")
FOLLOW = "follow"


def family_names() -> tuple[str, ...]:
    from video_compare.ui.theme import FAMILIES

    return tuple(FAMILIES)


def valid_color(value: str) -> bool:
    if value == FOLLOW:
        return True
    from PySide6.QtGui import QColor

    return value.startswith("#") and QColor.isValidColorName(value)


def _clean(app: dict, key: str, allowed: tuple[str, ...], default: str) -> str:
    value = app.get(key, default)
    return value if isinstance(value, str) and value in allowed else default


@dataclass(frozen=True, slots=True)
class AppSettings:
    language: LanguageName = "zh_CN"
    theme: ThemeName = "system"
    accent: ColorName = FOLLOW
    layout: LayoutName = "auto"
    scheme: str = "codex"
    workspace_color: ColorName = FOLLOW
    function_color: ColorName = FOLLOW
    overlay_color: ColorName = "#00b050"

    def __post_init__(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError("无效语言设置")
        if self.theme not in THEMES:
            raise ValueError("无效外观设置")
        if not valid_color(self.accent):
            raise ValueError("无效强调色设置")
        if self.layout not in LAYOUT_NAMES:
            raise ValueError("无效排列设置")
        if self.scheme not in family_names():
            raise ValueError("无效色系设置")
        for name, value in (
            ("工作区颜色", self.workspace_color),
            ("功能区颜色", self.function_color),
            ("视频信息颜色", self.overlay_color),
        ):
            if not valid_color(value):
                raise ValueError(f"无效{name}设置")


def load_settings(path: Path) -> AppSettings:
    if not path.is_file():
        return AppSettings()
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
        app = data.get("app", {})
        if not isinstance(app, dict):
            raise ValueError("设置表格式错误")
        scheme = _clean(app, "scheme", family_names(), "codex")

        def colour(key: str, default: str) -> str:
            value = app.get(key, default)
            return value if isinstance(value, str) and valid_color(value) else default

        return AppSettings(
            language=_clean(app, "language", LANGUAGES, "zh_CN"),
            theme=_clean(app, "theme", THEMES, "system"),
            accent=colour("accent", FOLLOW),
            layout=_clean(app, "layout", LAYOUT_NAMES, "auto"),
            scheme=scheme,
            workspace_color=colour("workspace_color", FOLLOW),
            function_color=colour("function_color", FOLLOW),
            overlay_color=colour("overlay_color", "#00b050"),
        )
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError):
        return AppSettings()


def save_settings(path: Path, settings: AppSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f'[app]\nlanguage = "{settings.language}"\n'
        f'theme = "{settings.theme}"\naccent = "{settings.accent}"\n'
        f'layout = "{settings.layout}"\nscheme = "{settings.scheme}"\n'
        f'workspace_color = "{settings.workspace_color}"\n'
        f'function_color = "{settings.function_color}"\n'
        f'overlay_color = "{settings.overlay_color}"\n'
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
