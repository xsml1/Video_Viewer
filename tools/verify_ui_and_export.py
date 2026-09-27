"""Verify the adaptive layout, modern shell and comparison export on real video.

Run on a machine with a display; every check uses real decoded frames.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from video_compare.ui.canvas_common import pane_boxes, pane_transform
from video_compare.ui.main_window import MainWindow


def _as_rgb(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(converted.constBits(), dtype=np.uint8)
    rows = raw.reshape(converted.height(), converted.bytesPerLine())
    return rows[:, : converted.width() * 3].reshape(converted.height(), converted.width(), 3).copy()


def _count_colour(part: np.ndarray, color: str, tolerance: int = 48) -> int:
    target = np.array(QColor(color).getRgb()[:3], dtype=np.int16)
    return int((np.abs(part.astype(np.int16) - target).max(axis=2) <= tolerance).sum())


def _expected_export_size(window: MainWindow) -> tuple[int, int]:
    """Visible tile sizes in device pixels arranged into the current rows."""
    canvas = window.canvas
    dpr = max(1.0, canvas.devicePixelRatioF())
    order = canvas.display_order
    boxes = pane_boxes(canvas.width(), canvas.height(), order, window._assets, canvas._snapshot)
    rows: dict[float, list[tuple[int, int]]] = {}
    for asset_id in order:
        transform = pane_transform(
            canvas.width(),
            canvas.height(),
            order,
            window._assets,
            canvas._snapshot,
            canvas.view_regions,
            asset_id,
            pixel_zoom=canvas.pixel_zoom,
            device_pixel_ratio=dpr,
            layout=canvas.layout_mode,
        )
        if transform is None:
            continue
        content = transform.content_rect
        rows.setdefault(round(boxes[asset_id].y, 1), []).append(
            (max(1, round(content.width * dpr)), max(1, round(content.height * dpr)))
        )
    width = max(sum(t[0] for t in row) + 6 * (len(row) - 1) for row in rows.values())
    height = sum(max(t[1] for t in row) for row in rows.values()) + 6 * (len(rows) - 1)
    return width, height


def wait_for(app: QApplication, window: MainWindow, count: int, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = window.canvas._snapshot
        if snapshot is not None and len(snapshot.frames) == count:
            return
        app.processEvents()
        time.sleep(0.02)
    raise SystemExit(f"超时：等待 {count} 路完整帧组失败（{window._status.text()}）")


def wait_for_file(app: QApplication, path: Path, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return
        app.processEvents()
        time.sleep(0.02)
    raise SystemExit(f"超时：导出文件未生成 {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/artifacts/ui"))
    parser.add_argument("--portrait", type=Path, nargs=2, default=None)
    parser.add_argument("--software", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path("tests/assets/generated").resolve()
    videos = (
        [path.resolve() for path in args.portrait]
        if args.portrait
        else [root / "f07_rotate_90.mp4", root / "f07_rotate_270.mp4"]
    )
    for video in videos:
        if not video.is_file():
            raise SystemExit(f"缺少视频：{video}")

    app = QApplication(sys.argv[:1])
    # 自检期间不要弹出模态提示，否则脚本会停在消息框上等待点击。
    notices: list[tuple[str, str]] = []
    for name in ("information", "warning", "critical"):
        setattr(
            QMessageBox,
            name,
            staticmethod(
                lambda _parent, title, text, _name=name, **_kwargs: notices.append(
                    (_name, f"{title}::{text}")
                )
            ),
        )
    window = MainWindow(
        output / "verify-index.sqlite3",
        ffprobe_path=args.ffprobe.resolve(),
        software=args.software,
        settings_path=output / "verify-settings.toml",
    )
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    window.load_files(videos)
    wait_for(app, window, 2)
    canvas = window.canvas
    renderer = type(canvas).__name__
    icon_missing = window.windowIcon().isNull()
    window.setWindowTitle(f"视频对比工具 · 验证（{renderer}）")
    from video_compare.ui.theme import FAMILIES

    for key in FAMILIES:
        mode = "dark" if key == "cyberpunk" else "light"
        window._theme_combo.setCurrentIndex(window._theme_combo.findData(mode))
        window._scheme_combo.setCurrentIndex(window._scheme_combo.findData(key))
        for role in ("workspace", "function", "accent"):
            window.set_role_color(role, "follow")
        app.processEvents()
        time.sleep(0.3)
        app.processEvents()
        window.grab().save(str(output / f"scheme_{key}.png"))
        if key == "codex":
            canvas_image = (
                canvas.grabFramebuffer()
                if hasattr(canvas, "grabFramebuffer")
                else canvas.grab().toImage()
            )
            canvas_image.save(str(output / "canvas_light.png"))
    window._theme_combo.setCurrentIndex(window._theme_combo.findData("dark"))
    window._scheme_combo.setCurrentIndex(window._scheme_combo.findData("codex"))
    window.set_role_color("overlay", "#00b050")
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()
    window.grab().save(str(output / "window_dark.png"))
    window._theme_combo.setCurrentIndex(window._theme_combo.findData("light"))
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    window.grab().save(str(output / "window_light.png"))

    settings_dialog = window._settings_dialog
    settings_dialog.select_role("overlay")
    settings_dialog.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()
    settings_dialog.grab().save(str(output / "settings_dialog.png"))
    settings_dialog.close()

    # 名称在画面左上角、帧信息在右下角，颜色即设置里的“视频信息”颜色。
    order = canvas.display_order
    boxes = pane_boxes(canvas.width(), canvas.height(), order, window._assets, canvas._snapshot)
    first_box = boxes[order[0]]
    canvas.grabFramebuffer().save(str(output / "canvas_overlays.png")) if hasattr(
        canvas, "grabFramebuffer"
    ) else canvas.grab().toImage().save(str(output / "canvas_overlays.png"))
    frame_pixels = _as_rgb(
        canvas.grabFramebuffer() if hasattr(canvas, "grabFramebuffer") else canvas.grab().toImage()
    )
    corner = frame_pixels[
        round(first_box.y) : round(first_box.y + first_box.height / 3),
        round(first_box.x) : round(first_box.x + first_box.width / 3),
    ]
    bottom = frame_pixels[
        round(first_box.bottom - first_box.height / 3) : round(first_box.bottom),
        round(first_box.right - first_box.width / 3) : round(first_box.right),
    ]
    overlay_color = window._settings.overlay_color
    top_count = _count_colour(corner, overlay_color)
    bottom_count = _count_colour(bottom, overlay_color)
    print(f"视频信息颜色 {overlay_color}：左上角像素 {top_count}，右下角像素 {bottom_count}")
    if top_count < 20 or bottom_count < 20:
        raise SystemExit("画面角落没有按设置绘制名称/帧信息")

    sidebar_width = window._sidebar.width()
    window._splitter.setSizes([1200, 260])
    app.processEvents()
    narrowed = window._sidebar.width()
    if narrowed >= sidebar_width:
        raise SystemExit("拖动分隔条没有改变信息栏宽度")
    window._sidebar_button.setChecked(False)
    hide_widths = []
    deadline = time.monotonic() + 2
    while window._sidebar.isVisible() and time.monotonic() < deadline:
        app.processEvents()
        hide_widths.append(window._splitter.sizes()[1])
        time.sleep(0.01)
    if window._sidebar.isVisible() or not any(0 < width < narrowed for width in hide_widths):
        raise SystemExit("侧栏隐藏动画未完整执行")
    window.grab().save(str(output / "window_sidebar_hidden.png"))
    window._sidebar_button.setChecked(True)
    show_widths = []
    deadline = time.monotonic() + 2
    while window._sidebar_animation is not None and time.monotonic() < deadline:
        app.processEvents()
        show_widths.append(window._splitter.sizes()[1])
        time.sleep(0.01)
    if not window._sidebar.isVisible() or not any(0 < width < narrowed for width in show_widths):
        raise SystemExit("侧栏呼出动画未完整执行")
    print(f"侧栏宽度 {sidebar_width}px → {narrowed}px，隐藏/恢复有连续动画")
    app.processEvents()

    order = canvas.display_order
    boxes = pane_boxes(canvas.width(), canvas.height(), order, window._assets, canvas._snapshot)
    first, second = boxes[order[0]], boxes[order[1]]
    middle_gap = second.x - first.right
    outer_margin = min(first.x, canvas.width() - second.right)
    portrait = first.width < first.height and second.width < second.height
    print(f"渲染器 {renderer}；画布 {canvas.width()}x{canvas.height()}")
    print(
        f"画面框：{first.width:.1f}x{first.height:.1f} 与 {second.width:.1f}x{second.height:.1f}；"
        f"中间空隙 {middle_gap:.1f}px；外侧留白 {outer_margin:.1f}px"
    )
    if first.height != second.height or abs(second.y - first.y) > 0.001:
        raise SystemExit("两路竖屏画面没有对齐到同一行/同一高度")
    if portrait and middle_gap > 12:
        raise SystemExit(f"竖屏视频之间仍有 {middle_gap:.1f}px 空隙")
    if portrait and outer_margin < middle_gap:
        raise SystemExit("外侧留白应大于中间空隙，避免画面被拆开")

    # Zoom + pan through the same code path as the mouse, then re-capture.
    zoom_target = (round(first.x + first.width / 2), round(first.y + first.height / 2))
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent

    for _ in range(3):
        canvas.wheelEvent(
            QWheelEvent(
                QPointF(*zoom_target),
                canvas.mapToGlobal(QPoint(*zoom_target)),
                QPoint(),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
        )
    app.processEvents()
    zoomed = canvas.view_regions[order[0]]
    if zoomed.width_u >= 1:
        raise SystemExit("Ctrl+滚轮没有缩小视图区域，无法验证平移")
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(*zoom_target))
    QTest.mouseMove(canvas, pos=QPoint(zoom_target[0] + 30, zoom_target[1] + 40))
    QTest.mouseRelease(
        canvas, Qt.MouseButton.LeftButton, pos=QPoint(zoom_target[0] + 30, zoom_target[1] + 40)
    )
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    region = canvas.view_regions[order[0]]
    print(f"缩放后 {zoomed} -> 拖拽(+30,+40)后 {region}")
    if region.center_u >= zoomed.center_u and region.center_v >= zoomed.center_v:
        raise SystemExit("拖拽平移没有改变视图区域")
    horizontal_moved = region.center_u < zoomed.center_u
    vertical_moved_down = region.center_v > zoomed.center_v
    print(
        f"水平方向：{'跟随指针（向左拖动视图）' if horizontal_moved else '未按预期'}；"
        f"垂直方向：{'视图跟随指针向下' if vertical_moved_down else '未按预期'}"
    )
    if not horizontal_moved or not vertical_moved_down:
        raise SystemExit("平移方向与当前约定不一致")
    if hasattr(canvas, "grabFramebuffer"):
        canvas.grabFramebuffer().save(str(output / "canvas_panned.png"))
    else:
        canvas.grab().toImage().save(str(output / "canvas_panned.png"))

    window._canvas.reset_fit()

    png_path = output / "对比图_与窗口一致.png"
    jpeg_path = output / "对比图_竖向排列.jpg"
    png_path.unlink(missing_ok=True)
    jpeg_path.unlink(missing_ok=True)
    png_path.with_suffix(".json").unlink(missing_ok=True)
    jpeg_path.with_suffix(".json").unlink(missing_ok=True)
    assert window.export_comparison_image(png_path, layout="window", image_format="PNG")
    wait_for_file(app, png_path)
    assert window.export_comparison_image(
        jpeg_path, layout="vertical", image_format="JPEG", quality=90
    )
    wait_for_file(app, jpeg_path)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    png = QImage(str(png_path))
    jpeg = QImage(str(jpeg_path))
    print(
        f"PNG {png.width()}x{png.height()} {png_path.stat().st_size} bytes；"
        f"JPEG {jpeg.width()}x{jpeg.height()} {jpeg_path.stat().st_size} bytes"
    )
    if png.isNull() or jpeg.isNull():
        raise SystemExit("导出的图片无法读取")
    if png_path.with_suffix(".json").exists() or jpeg_path.with_suffix(".json").exists():
        raise SystemExit("导出不应再生成 JSON 文件")
    expected_width, expected_height = _expected_export_size(window)
    print(
        f"窗口布局导出的理论尺寸 {expected_width}x{expected_height}；"
        f"实际 {png.width()}x{png.height()}"
    )
    if (png.width(), png.height()) != (expected_width, expected_height):
        raise SystemExit("导出尺寸与可见画面尺寸不一致")
    if jpeg.width() >= jpeg.height():
        raise SystemExit("竖向排列的导出图应为上下两行")
    if _count_colour(_as_rgb(png), overlay_color) < 40:
        raise SystemExit("导出图缺少画面左上角/右下角的视频信息文字")
    window.grab().save(str(output / "window_exported.png"))
    print(f"窗口图标已设置：{not icon_missing}")
    if not any(name == "information" for name, _ in notices):
        raise SystemExit("导出成功提示没有出现")
    print(f"导出提示：{notices[-1][1].splitlines()[0]}")

    from video_compare.ui.export_dialog import ExportOptionsDialog

    dialog = ExportOptionsDialog(window)
    dialog.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()
    dialog.grab().save(str(output / "export_dialog_png.png"))
    png_options = dialog.options()
    if png_options.image_format != "PNG" or dialog._quality.isEnabled():
        raise SystemExit("导出对话框 PNG 状态不正确")
    dialog._format_combo.setCurrentIndex(1)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    dialog.grab().save(str(output / "export_dialog_jpeg.png"))
    jpeg_options = dialog.options()
    if jpeg_options.image_format != "JPEG" or not dialog._quality.isEnabled():
        raise SystemExit("导出对话框 JPEG 状态不正确")
    print(
        f"导出对话框：默认 {png_options.layout}/{png_options.image_format}，"
        f"切换后 {jpeg_options.layout}/{jpeg_options.image_format}/{jpeg_options.quality}"
    )
    dialog.close()

    # 编辑导出：在画面上拖出一个矩形，导出图必须包含该标注（所有画面同步）。
    annotated = output / "对比图_带标注.png"
    annotated.unlink(missing_ok=True)
    window.start_annotation_export(annotated, layout="window", image_format="PNG")
    if not window._annotation_bar.isVisible() or not canvas.annotating:
        raise SystemExit("编辑导出模式没有启动")
    canvas.set_annotation_shape("rect")
    canvas.set_annotation_color("#0a84ff")
    start = QPoint(
        round(first_box.x + first_box.width * 0.25),
        round(first_box.y + first_box.height * 0.25),
    )
    end = QPoint(
        round(first_box.x + first_box.width * 0.7), round(first_box.y + first_box.height * 0.6)
    )
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, pos=end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    if len(canvas.annotations) != 1:
        raise SystemExit("拖拽没有生成标注")
    canvas.grabFramebuffer().save(str(output / "canvas_annotated.png")) if hasattr(
        canvas, "grabFramebuffer"
    ) else canvas.grab().toImage().save(str(output / "canvas_annotated.png"))
    window._annotation_bar.done_button.click()
    wait_for_file(app, annotated)
    deadline = time.monotonic() + 5
    while canvas.annotations and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    if canvas.annotations or window._annotation_bar.isVisible():
        raise SystemExit("导出成功后标注没有从画布清除")
    app.processEvents()
    blue = _count_colour(_as_rgb(QImage(str(annotated))), "#0a84ff")
    if blue < 200:
        raise SystemExit(f"导出图里没有标注图形（命中 {blue} 像素）")
    if annotated.with_suffix(".json").exists():
        raise SystemExit("标注导出不应生成 JSON")
    print(f"标注导出：蓝色矩形像素 {blue}，无 JSON")
    print(f"证据目录：{output}")
    print(f"PNG sha256={hashlib.sha256(png_path.read_bytes()).hexdigest()[:16]}")
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
