"""Application icon lookup for source runs and packaged builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon

ICON_NAME = "app.ico"


def icon_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    override = os.environ.get("VIDEO_COMPARE_ICON")
    if override:
        candidates.append(Path(override))
    package = Path(__file__).resolve().parent.parent / "assets" / ICON_NAME
    candidates.append(package)
    try:
        executable = Path(sys.executable).resolve().parent
    except (OSError, RuntimeError):
        executable = None
    if executable is not None:
        candidates.append(executable / "assets" / ICON_NAME)
    return tuple(candidates)


def application_icon() -> QIcon | None:
    for path in icon_candidates():
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return None
