"""Shared test setup: never read or write the developer's real settings file."""

from __future__ import annotations

from pathlib import Path

import pytest

from video_compare.ui import main_window


@pytest.fixture(autouse=True)
def isolate_user_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        main_window, "user_config_path", lambda *_args, **_kwargs: tmp_path / "config"
    )
