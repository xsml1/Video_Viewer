from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from platformdirs import user_cache_path
from PySide6.QtWidgets import QApplication

from video_compare.ui.branding import application_icon
from video_compare.ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地视频与图像对比工具")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--mode", choices=("video", "image"), default="video")
    parser.add_argument("--ffprobe", type=Path, default=None)
    parser.add_argument("--software", action="store_true", help="使用 QPainter 软件画布")
    parser.add_argument("--self-test-output", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--self-test-image-output", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.self_test_output is not None and (args.mode != "video" or len(args.files) != 2):
        parser.error("--self-test-output requires exactly two local videos")
    if args.self_test_image_output is not None and (args.mode != "image" or len(args.files) != 2):
        parser.error("--self-test-image-output requires exactly two local images")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Video Viewer")
    app.setApplicationDisplayName("Video Viewer")
    app.setOrganizationName("Video Viewer")
    icon = application_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    ffprobe = args.ffprobe or (
        Path(os.environ["VIDEO_COMPARE_FFPROBE"])
        if os.environ.get("VIDEO_COMPARE_FFPROBE")
        else None
    )
    diagnostic_output = args.self_test_output or args.self_test_image_output
    cache = (
        diagnostic_output / "frame-index.sqlite3"
        if diagnostic_output is not None
        else user_cache_path("video-compare", "OpenAI") / "frame-index.sqlite3"
    )
    window = MainWindow(
        cache,
        ffprobe_path=ffprobe,
        software=args.software,
        settings_path=diagnostic_output / "settings.toml"
        if diagnostic_output is not None
        else None,
    )
    window.show()
    # --mode remains accepted for older launch scripts; files now share one workspace.
    if args.files:
        window.load_files(args.files)
    if args.self_test_output is not None:
        from video_compare.services.selftest import run_self_test

        return run_self_test(app, window, args.self_test_output)
    if args.self_test_image_output is not None:
        from video_compare.services.selftest import run_image_self_test

        return run_image_self_test(app, window, args.self_test_image_output)
    return app.exec()
