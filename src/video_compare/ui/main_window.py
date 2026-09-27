from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from platformdirs import user_config_path
from PySide6.QtCore import QEasingCurve, QStandardPaths, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from video_compare.controllers.transport import TransportController
from video_compare.domain.models import (
    AssetInfo,
    DecodedFrame,
    FrameGroupSnapshot,
    SyncMode,
    TimelineSpec,
    TransportState,
)
from video_compare.domain.timeline import (
    FrameTimeline,
    TimelineError,
    format_timecode,
    parse_timecode,
)
from video_compare.media.images import ImageLoadResult, ImageLoadTask, ImageLoadWorker
from video_compare.media.index import FrameIndexRepository
from video_compare.media.loading import AssetLoadWorker, LoadResult, LoadTask
from video_compare.services.comparison_export import (
    CompositeLayout,
    CompositeTile,
    rows_from_boxes,
)
from video_compare.services.markers import MarkerStore
from video_compare.services.screenshots import ScreenshotRequest, ScreenshotWorker
from video_compare.services.settings import AppSettings, load_settings, save_settings
from video_compare.ui.annotation_bar import AnnotationBar
from video_compare.ui.branding import application_icon
from video_compare.ui.canvas_common import pane_boxes, pane_transform
from video_compare.ui.canvas_gl import CompareCanvas
from video_compare.ui.canvas_software import SoftwareCompareCanvas
from video_compare.ui.export_dialog import (
    ExportOptionsDialog,
    format_filter,
    format_suffix,
)
from video_compare.ui.i18n import language, set_language, translate
from video_compare.ui.layout import LAYOUT_LABELS, choose_rows
from video_compare.ui.localized_widgets import QComboBox, QLabel, QLineEdit, QPushButton
from video_compare.ui.settings_dialog import SettingsDialog
from video_compare.ui.theme import apply_theme


class MainWindow(QMainWindow):
    """Core window: all participating videos share one transport and canvas."""

    def __init__(
        self,
        index_path: Path,
        ffprobe_path: Path | None = None,
        software: bool = False,
        settings_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Video Viewer")
        self.resize(1440, 860)
        self.setMinimumSize(1000, 600)
        icon = application_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        self._repository = FrameIndexRepository(index_path)
        self._ffprobe_path = ffprobe_path
        self._loader = AssetLoadWorker(self._repository, ffprobe_path)
        self._image_loader = ImageLoadWorker()
        self._image_assets: dict[str, AssetInfo] = {}
        self._image_frames: dict[str, DecodedFrame] = {}
        self._image_notes: dict[str, str] = {}
        self._image_pending: set[ImageLoadTask] = set()
        self._image_replacements: dict[str, ImageLoadTask] = {}
        self._image_snapshot: FrameGroupSnapshot | None = None
        self._image_revision = 0
        self._screenshot_worker = ScreenshotWorker()
        self._marker_store = MarkerStore()
        self._closing_confirmed = False
        self._pending_add = 0
        self._partial_tasks: dict[LoadTask, str] = {}
        self._cancelled_loads: set[LoadTask] = set()
        self._pending_transport_anchor: tuple[int | None, Fraction | None, bool] | None = None
        self._load_error_notice: str | None = None
        self._pending_replacements: dict[str, LoadTask] = {}
        self._range_notice: str | None = None
        self._message_open = False
        self._pending_export_note = ""
        self._export_dir: Path | None = None
        self._canvas_annotation_shape = "rect"
        self._canvas_annotation_color = "#ff3b30"
        self._pending_annotated_export: tuple[Path, str, str, int] | None = None
        self._saving_annotated_export = False
        self._settings_path = settings_path or (
            user_config_path("video-compare", "OpenAI") / "settings.toml"
        )
        self._settings = load_settings(self._settings_path)
        set_language(self._settings.language)
        self._assets: dict[str, AssetInfo] = {}
        self._excluded_ids: set[str] = set()
        self._held_frames: dict[str, DecodedFrame] = {}
        self._time_offsets: dict[str, Fraction] = {}
        self._frame_offsets: dict[str, int] = {}
        self._maximized_id: str | None = None
        self._timelines: dict[str, FrameTimeline] = {}
        self._transport: TransportController | None = None
        self._canvas = SoftwareCompareCanvas(self) if software else CompareCanvas(self)
        self._software = software
        if isinstance(self._canvas, CompareCanvas):
            self._canvas.render_failed.connect(
                lambda reason: QTimer.singleShot(0, lambda: self._fallback_canvas(reason))
            )
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 10)
        root_layout.setSpacing(8)

        # 顶部单行工具栏：全局操作 + 设置入口。
        top_bar = QFrame(central)
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(8)
        title = QLabel("Video Viewer", self)
        title.setObjectName("AppTitle")
        top_layout.addWidget(title)
        self._media_mode = QComboBox(self)
        self._media_mode.addItem("视频对比", "video")
        self._media_mode.addItem("图像对比", "image")
        self._media_mode.currentIndexChanged.connect(self._switch_media_mode)
        top_layout.addWidget(self._media_mode)
        add_button = QPushButton("添加视频", self)
        self._add_button = add_button
        add_button.setObjectName("Primary")
        add_button.setToolTip("添加本地视频（最多 6 路，Ctrl+O）")
        add_button.clicked.connect(self._choose_files)
        top_layout.addWidget(add_button)
        self._mode = QComboBox(self)
        self._mode.addItem("按时间同步", SyncMode.TIME)
        self._mode.addItem("按帧号同步", SyncMode.FRAME)
        self._mode.setToolTip("同步方式：按真实 PTS 或显示帧号")
        self._mode.currentIndexChanged.connect(self._switch_mode)
        top_layout.addWidget(self._mode)
        self._reference_combo = QComboBox(self)
        self._reference_combo.setToolTip("基准视频（与列表选中项独立）")
        self._reference_combo.setMinimumWidth(110)
        self._reference_combo.currentIndexChanged.connect(self._switch_reference)
        top_layout.addWidget(self._reference_combo)
        self._pixel_mode_combo = QComboBox(self)
        self._pixel_mode_combo.addItem("同区域查看", False)
        self._pixel_mode_combo.addItem("原生像素 100%", True)
        self._pixel_mode_combo.setToolTip("原生像素以 framebuffer 物理像素为准，忽略视频 SAR")
        self._pixel_mode_combo.currentIndexChanged.connect(self._change_pixel_mode)
        top_layout.addWidget(self._pixel_mode_combo)
        self._layout_combo = QComboBox(self)
        for value in ("auto", "grid", "horizontal", "vertical"):
            self._layout_combo.addItem(LAYOUT_LABELS[value], value)
        self._layout_combo.setToolTip("画面排列方式；自动会按导入视频的比例选择")
        self._layout_combo.setCurrentIndex(
            next(
                index
                for index in range(self._layout_combo.count())
                if self._layout_combo.itemData(index) == self._settings.layout
            )
        )
        self._layout_combo.currentIndexChanged.connect(self._change_layout)
        top_layout.addWidget(self._layout_combo)
        self._fit_button = QPushButton("适应", self)
        self._fit_button.setToolTip("适应画面：恢复完整画面（F）")
        self._fit_button.clicked.connect(self._canvas.reset_fit)
        top_layout.addWidget(self._fit_button)
        self._roi_button = QPushButton("框选 ROI", self)
        self._roi_button.setCheckable(True)
        self._roi_button.setToolTip("在画面内拖出区域，其他路定位到相同相对区域")
        self._roi_button.toggled.connect(self._canvas.set_roi_mode)
        top_layout.addWidget(self._roi_button)
        self._linked_button = QPushButton("视图联动", self)
        self._linked_button.setCheckable(True)
        self._linked_button.setChecked(True)
        self._linked_button.setToolTip("缩放、平移、ROI 是否联动所有画面")
        self._linked_button.toggled.connect(self._set_view_linked)
        top_layout.addWidget(self._linked_button)
        top_layout.addStretch(1)
        self._save_view_button = QPushButton("保存视图", self)
        self._save_view_button.setToolTip("保存整个画布 PNG，含文件名与帧号标注")
        self._save_view_button.clicked.connect(lambda: self._choose_screenshot_dir("view"))
        top_layout.addWidget(self._save_view_button)
        self._save_frames_button = QPushButton("保存原帧", self)
        self._save_frames_button.setToolTip("保存各路源采样帧 PNG 与帧身份 JSON")
        self._save_frames_button.clicked.connect(lambda: self._choose_screenshot_dir("frames"))
        top_layout.addWidget(self._save_frames_button)
        self._export_button = QPushButton("导出对比图…", self)
        self._export_button.setObjectName("Primary")
        self._export_button.setToolTip("导出当前窗口看到的画面（不含界面元素）")
        self._export_button.clicked.connect(self.choose_export_options)
        top_layout.addWidget(self._export_button)
        self._settings_button = QPushButton("设置", self)
        self._settings_button.setToolTip("色系、明暗模式与强调色")
        self._settings_button.clicked.connect(self._open_settings)
        top_layout.addWidget(self._settings_button)
        self._sidebar_button = QPushButton("侧栏", self)
        self._sidebar_button.setCheckable(True)
        self._sidebar_button.setChecked(True)
        self._sidebar_button.setToolTip("显示或隐藏右侧信息栏")
        self._sidebar_button.toggled.connect(self._toggle_sidebar)
        top_layout.addWidget(self._sidebar_button)
        root_layout.addWidget(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self._splitter = splitter
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        main_area = QWidget(splitter)
        layout = QVBoxLayout(main_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._main_layout = layout
        sidebar = QFrame(splitter)
        sidebar.setObjectName("Card")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(620)
        self._sidebar = sidebar
        self._sidebar_last_width = 330
        self._sidebar_animation: QVariantAnimation | None = None
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(14, 12, 14, 12)
        side_layout.setSpacing(8)
        splitter.addWidget(main_area)
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(1, True)
        splitter.setSizes([940, 330])
        root_layout.addWidget(splitter, 1)

        side_header = QHBoxLayout()
        side_header.setSpacing(6)
        self._side_title = self._section_title("视频文件")
        side_header.addWidget(self._side_title)
        side_header.addStretch(1)
        self._sidebar_hide_button = QPushButton("»", self)
        self._sidebar_hide_button.setObjectName("Ghost")
        self._sidebar_hide_button.setToolTip("隐藏侧栏")
        self._sidebar_hide_button.setFixedWidth(28)
        self._sidebar_hide_button.clicked.connect(lambda: self._sidebar_button.setChecked(False))
        side_header.addWidget(self._sidebar_hide_button)
        side_layout.addLayout(side_header)
        file_controls = QHBoxLayout()
        file_controls.setSpacing(8)
        self._remove_button = QPushButton("移除选中", self)
        self._remove_button.clicked.connect(self.remove_selected)
        file_controls.addWidget(self._remove_button)
        self._replace_button = QPushButton("替换选中", self)
        self._replace_button.clicked.connect(self._choose_replacement)
        file_controls.addWidget(self._replace_button)
        side_layout.addLayout(file_controls)
        order_controls = QHBoxLayout()
        order_controls.setSpacing(8)
        self._move_up_button = QPushButton("上移", self)
        self._move_up_button.clicked.connect(lambda: self._move_selected(-1))
        order_controls.addWidget(self._move_up_button)
        self._move_down_button = QPushButton("下移", self)
        self._move_down_button.clicked.connect(lambda: self._move_selected(1))
        order_controls.addWidget(self._move_down_button)
        side_layout.addLayout(order_controls)
        self._participant_button = QPushButton("暂停选中路同步", self)
        self._participant_button.clicked.connect(self._toggle_time_participation)
        side_layout.addWidget(self._participant_button)
        self._file_list = QListWidget(self)
        self._file_list.setAcceptDrops(False)
        self._file_list.currentRowChanged.connect(self._show_selected_offsets)
        self._file_list.currentRowChanged.connect(self._show_selected_asset_info)
        self._file_list.currentRowChanged.connect(self._refresh_participant_button)
        side_layout.addWidget(self._file_list, 2)
        hint = QLabel("双击画面单路查看 · Esc 返回网格", self)
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        side_layout.addWidget(hint)
        self._asset_info = QLabel("选中一路查看源信息与预览限制", self)
        self._asset_info.setWordWrap(True)
        self._asset_info.setObjectName("Hint")
        side_layout.addWidget(self._asset_info)
        self._offset_title = self._section_title("选中路 Offset")
        side_layout.addWidget(self._offset_title)
        offset_controls = QGridLayout()
        offset_controls.setSpacing(8)
        offset_controls.addWidget(QLabel("时间（秒）", self), 0, 0)
        self._time_offset_input = QLineEdit("0.000", self)
        offset_controls.addWidget(self._time_offset_input, 0, 1)
        offset_controls.addWidget(QLabel("帧", self), 1, 0)
        self._frame_offset_input = QLineEdit("0", self)
        offset_controls.addWidget(self._frame_offset_input, 1, 1)
        self._offset_button = QPushButton("应用 Offset", self)
        self._offset_button.clicked.connect(self._apply_offsets)
        offset_controls.addWidget(self._offset_button, 2, 0, 1, 2)
        side_layout.addLayout(offset_controls)
        self._marker_title_label = self._section_title("Marker（仅本次会话）")
        side_layout.addWidget(self._marker_title_label)
        self._marker_title = QLineEdit(self)
        self._marker_title.setPlaceholderText("标题（可选）")
        side_layout.addWidget(self._marker_title)
        self._marker_note = QLineEdit(self)
        self._marker_note.setPlaceholderText("备注（可选）")
        side_layout.addWidget(self._marker_note)
        marker_controls = QHBoxLayout()
        marker_controls.setSpacing(8)
        self._marker_add_button = QPushButton("添加 Marker (M)", self)
        self._marker_add_button.clicked.connect(self._add_marker)
        marker_controls.addWidget(self._marker_add_button)
        self._marker_jump_button = QPushButton("跳转选中 Marker", self)
        self._marker_jump_button.clicked.connect(self._jump_marker)
        marker_controls.addWidget(self._marker_jump_button)
        side_layout.addLayout(marker_controls)
        self._marker_list = QListWidget(self)
        self._marker_list.itemDoubleClicked.connect(lambda _item: self._jump_marker())
        side_layout.addWidget(self._marker_list, 1)

        self._pixel_notice = QLabel("原生像素检查：忽略 SAR；Ctrl+滚轮调整像素倍率", self)
        self._pixel_notice.setVisible(False)
        self._pixel_notice.setObjectName("Hint")
        layout.addWidget(self._pixel_notice)
        self._annotation_bar = AnnotationBar(main_area)
        self._annotation_bar.setVisible(False)
        self._annotation_bar.shape_changed.connect(self._canvas.set_annotation_shape)
        self._annotation_bar.color_changed.connect(self._canvas.set_annotation_color)
        self._annotation_bar.link_changed.connect(self._canvas.set_annotation_linked)
        self._annotation_bar.undo_requested.connect(self._canvas.undo_annotation)
        self._annotation_bar.clear_requested.connect(self._canvas.clear_annotations)
        self._annotation_bar.delete_requested.connect(self._canvas.delete_annotation)
        self._annotation_bar.finished.connect(self._finish_annotation_export)
        self._annotation_bar.cancelled.connect(self._cancel_annotation_export)
        self._canvas.annotations_changed.connect(self._annotation_bar.set_annotations)
        self._annotation_bar.set_shape(self._canvas_annotation_shape)
        self._annotation_bar.set_color(self._canvas_annotation_color)
        self._canvas.set_annotation_linked(self._annotation_bar.link_checkbox.isChecked())
        layout.addWidget(self._annotation_bar)
        self._canvas.view_changed.connect(self._refresh_pixel_notice)
        layout.addWidget(self._canvas, 1)

        # 画面下方：进度与播放控制（播放相关操作集中在视频窗口底部）。
        transport = QFrame(main_area)
        transport.setObjectName("Transport")
        transport_layout = QVBoxLayout(transport)
        transport_layout.setContentsMargins(12, 10, 12, 10)
        transport_layout.setSpacing(8)
        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, 10000)
        self._slider.sliderPressed.connect(self._start_scrub)
        self._slider.valueChanged.connect(self._queue_scrub_preview)
        self._slider.sliderReleased.connect(self._finish_scrub)
        transport_layout.addWidget(self._slider)
        transport_row = QHBoxLayout()
        transport_row.setSpacing(8)
        self._play_button = QPushButton("播放", self)
        self._play_button.setObjectName("Primary")
        self._play_button.setToolTip("播放或暂停（空格）")
        self._play_button.clicked.connect(self._toggle_play)
        transport_row.addWidget(self._play_button)
        self._back_button = QPushButton("←", self)
        self._back_button.setToolTip("后退一步（左方向键）")
        self._back_button.clicked.connect(lambda: self._step(-1))
        transport_row.addWidget(self._back_button)
        self._forward_button = QPushButton("→", self)
        self._forward_button.setToolTip("前进一步（右方向键）")
        self._forward_button.clicked.connect(lambda: self._step(1))
        transport_row.addWidget(self._forward_button)
        self._step_unit = QComboBox(self)
        self._step_unit.setMinimumWidth(72)
        self._step_unit.addItem("帧", "frame")
        self._step_unit.addItem("秒", "second")
        transport_row.addWidget(self._step_unit)
        self._step_amount = QLineEdit("1", self)
        self._step_amount.setToolTip("步进量：帧为正整数；秒最多精确到毫秒")
        self._step_amount.setMaximumWidth(64)
        transport_row.addWidget(self._step_amount)
        transport_row.addWidget(QLabel("速度", self))
        self._speed_combo = QComboBox(self)
        for label, value in (
            ("0.25×", "1/4"),
            ("0.5×", "1/2"),
            ("1×", "1"),
            ("2×", "2"),
            ("4×", "4"),
        ):
            self._speed_combo.addItem(label, value)
        self._speed_combo.setCurrentIndex(2)
        self._speed_combo.currentIndexChanged.connect(self._change_speed)
        transport_row.addWidget(self._speed_combo)
        self._loop_in_button = QPushButton("I", self)
        self._loop_in_button.setToolTip("把当前完整组设为循环起点")
        self._loop_in_button.clicked.connect(self._set_loop_start)
        transport_row.addWidget(self._loop_in_button)
        self._loop_out_button = QPushButton("O", self)
        self._loop_out_button.setToolTip("把当前完整组设为循环终点")
        self._loop_out_button.clicked.connect(self._set_loop_end)
        transport_row.addWidget(self._loop_out_button)
        self._loop_button = QPushButton("区间循环", self)
        self._loop_button.setCheckable(True)
        self._loop_button.toggled.connect(self._toggle_loop)
        transport_row.addWidget(self._loop_button)
        transport_row.addStretch(1)
        self._time_input = QLineEdit(self)
        self._time_input.setPlaceholderText("时间 HH:MM:SS.mmm")
        self._time_input.setToolTip("输入全局时间并回车定位")
        self._time_input.returnPressed.connect(self._seek_time_input)
        transport_row.addWidget(self._time_input)
        self._frame_input = QLineEdit(self)
        self._frame_input.setPlaceholderText("帧号（从 1 开始）")
        self._frame_input.setToolTip("输入基准视频帧号并回车定位")
        self._frame_input.setValidator(QIntValidator(1, 2_147_483_647, self))
        self._frame_input.returnPressed.connect(self._seek_frame_input)
        transport_row.addWidget(self._frame_input)
        transport_layout.addLayout(transport_row)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self._status = QLabel("添加本地视频；当前按完整帧组同步显示", self)
        self._status.setObjectName("Status")
        self._status.setWordWrap(True)
        status_row.addWidget(self._status, 1)
        self._loop_status = QLabel("循环：未设置", self)
        self._loop_status.setObjectName("Hint")
        status_row.addWidget(self._loop_status)
        transport_layout.addLayout(status_row)
        layout.addWidget(transport)
        self._transport_panel = transport
        self._video_transport_widgets = [
            self._slider,
            self._loop_status,
            *(
                transport_row.itemAt(i).widget()
                for i in range(transport_row.count())
                if transport_row.itemAt(i).widget() is not None
            ),
        ]
        self._video_side_widgets = (
            self._participant_button,
            self._offset_title,
            self._time_offset_input,
            self._frame_offset_input,
            self._offset_button,
            self._marker_title_label,
            self._marker_title,
            self._marker_note,
            self._marker_add_button,
            self._marker_jump_button,
            self._marker_list,
        )
        self._offset_labels = [offset_controls.itemAtPosition(row, 0).widget() for row in (0, 1)]
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.setInterval(50)
        self._scrub_timer.timeout.connect(self._preview_scrub)
        self._scrub_was_playing = False

        self._settings_dialog = SettingsDialog(self, settings=self._settings)
        self._theme_combo = self._settings_dialog.theme_combo
        self._scheme_combo = self._settings_dialog.scheme_combo
        self._color_grid = self._settings_dialog.color_grid
        self._settings_dialog.appearance_changed.connect(self._change_appearance)
        self._settings_dialog.language_changed.connect(self._change_language)

        self._canvas.panel_double_clicked.connect(self._toggle_maximize_asset)
        self.setCentralWidget(central)
        self.setAcceptDrops(True)
        self._apply_theme()
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._on_system_color_scheme_changed
        )
        self._canvas.set_layout_mode(self._settings.layout)
        self._loader_timer = QTimer(self)
        self._loader_timer.setInterval(25)
        self._loader_timer.timeout.connect(self._drain_load_results)
        self._loader_timer.start()
        self._screenshot_timer = QTimer(self)
        self._screenshot_timer.setInterval(50)
        self._screenshot_timer.timeout.connect(self._drain_screenshot_results)
        self._screenshot_timer.start()
        if not software:
            QTimer.singleShot(100, self._ensure_canvas)

    @property
    def canvas(self):
        return self._canvas

    @property
    def media_kind(self) -> str:
        return str(self._media_mode.currentData())

    def _active_assets(self) -> dict[str, AssetInfo]:
        return self._image_assets if self.media_kind == "image" else self._assets

    def _switch_media_mode(self) -> None:
        image_mode = self.media_kind == "image"
        if image_mode and self._transport is not None:
            self._transport.pause()
        if self._pending_annotated_export is not None and not self._saving_annotated_export:
            self._cancel_annotation_export()
        self._canvas.clear_annotations()
        self._canvas.clear_group()
        self._maximized_id = None
        self._add_button.setText("添加图像" if image_mode else "添加视频")
        self._save_frames_button.setText("保存各图" if image_mode else "保存原帧")
        self._save_frames_button.setToolTip(
            "保存各路 RGB8 预览 PNG 与图像来源 JSON"
            if image_mode
            else "保存各路源采样帧 PNG 与帧身份 JSON"
        )
        self._add_button.setToolTip(
            "添加本地图像（最多 6 路，Ctrl+O）"
            if image_mode
            else "添加本地视频（最多 6 路，Ctrl+O）"
        )
        self._side_title.setText("图像文件" if image_mode else "视频文件")
        self._mode.setVisible(not image_mode)
        self._reference_combo.setVisible(not image_mode)
        for widget in (
            *self._video_side_widgets,
            *self._offset_labels,
            *self._video_transport_widgets,
        ):
            widget.setVisible(not image_mode)
        self._refresh_file_list()
        self._refresh_layout()
        if image_mode:
            self._present_images()
        elif self._transport is not None and self._transport.displayed is not None:
            self._on_state(self._transport.state)
            self._on_group(self._transport.displayed)
        else:
            self._status.setText("添加本地视频；当前按完整帧组同步显示")

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("SectionTitle")
        return label

    def _change_layout(self) -> None:
        mode = self._layout_combo.currentData()
        self._canvas.set_layout_mode(mode)
        self._settings = replace(self._settings, layout=mode)
        try:
            save_settings(self._settings_path, self._settings)
        except OSError as exc:
            self._on_error(f"无法保存排列设置：{exc}")
        self._refresh_pixel_notice()

    def _open_settings(self) -> None:
        self._settings_dialog.exec()

    def _toggle_sidebar(self, visible: bool) -> None:
        self._sidebar_hide_button.setEnabled(visible)
        if self._sidebar_animation is not None:
            self._sidebar_animation.stop()
            self._sidebar_animation.deleteLater()
        total = sum(self._splitter.sizes())
        if total <= 0:
            self._sidebar.setVisible(visible)
            return
        sidebar = self._sidebar
        was_visible = sidebar.isVisible()
        if visible:
            sidebar.setMinimumWidth(1)
            sidebar.show()
            if not was_visible:
                self._splitter.setSizes([total, 0])
                start = 0
            else:
                start = sidebar.width()
            target = min(620, max(220, self._sidebar_last_width))
        else:
            start = sidebar.width()
            if start >= 220:
                self._sidebar_last_width = start
            sidebar.setMinimumWidth(1)
            target = 0
        animation = QVariantAnimation(self)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(start)
        animation.setEndValue(target)
        self._sidebar_animation = animation

        def resize_sidebar(value: int) -> None:
            if self._sidebar_animation is animation:
                width = max(0, min(total, int(value)))
                self._splitter.setSizes([total - width, width])

        def finish_sidebar() -> None:
            if self._sidebar_animation is not animation:
                return
            self._sidebar_animation = None
            animation.deleteLater()
            if visible:
                sidebar.setMinimumWidth(220)
                self._splitter.setSizes([max(0, total - target), target])
            else:
                sidebar.hide()
                sidebar.setMinimumWidth(220)

        animation.valueChanged.connect(resize_sidebar)
        animation.finished.connect(finish_sidebar)
        animation.start()

    def _change_appearance(self) -> None:
        values = self._settings_dialog.appearance()
        self._settings = AppSettings(
            layout=self._settings.layout, language=self._settings.language, **values
        )
        self._apply_theme()
        try:
            save_settings(self._settings_path, self._settings)
        except OSError as exc:
            self._on_error(f"无法保存外观设置：{exc}")

    def _change_language(self, language: str) -> None:
        if language == self._settings.language:
            return
        self._settings = replace(self._settings, language=language)
        set_language(language)
        for widget_type in (QLabel, QPushButton, QLineEdit, QComboBox):
            for widget in self.findChildren(widget_type):
                widget.retranslate()
        self._settings_dialog.retranslate()
        self._annotation_bar.retranslate(self._canvas.annotations)
        self._canvas.update()
        try:
            save_settings(self._settings_path, self._settings)
        except OSError as exc:
            self._on_error(f"无法保存语言设置：{exc}")

    def set_accent(self, accent: str) -> None:
        """Set the accent colour (``follow`` or ``#rrggbb``) and persist it."""
        self._settings_dialog.set_color("accent", accent)

    def set_role_color(self, role: str, color: str) -> None:
        """Set one colour role: workspace/function/accent/overlay."""
        self._settings_dialog.set_color(role, color)

    def _ensure_canvas(self) -> None:
        if isinstance(self._canvas, CompareCanvas) and self._canvas.context() is None:
            self._fallback_canvas("OpenGL 上下文不可用")

    def _fallback_canvas(self, reason: str) -> None:
        if not isinstance(self._canvas, CompareCanvas):
            return
        old = self._canvas
        snapshot = self._current_display_snapshot()
        if (
            snapshot is None
            and self.media_kind == "video"
            and self._transport is not None
            and self._transport.displayed is not None
        ):
            core = self._transport.displayed
            snapshot = (
                FrameGroupSnapshot(
                    core.group_id,
                    core.requested_global_time,
                    core.reference_ordinal,
                    {**core.frames, **self._held_frames},
                    {**core.boundary_states, **dict.fromkeys(self._held_frames, "detached")},
                    core.mapping_revision,
                )
                if self._held_frames
                else core
            )
        if snapshot is None and self.media_kind == "image":
            snapshot = self._image_snapshot
        regions = old.view_regions
        linked = old._linked
        roi_mode = old._roi_mode
        annotations = old.annotations
        annotating = old.annotating
        annotation_shape = old._annotation_shape
        annotation_color = old._annotation_color
        annotation_linked = old._annotation_linked
        replacement = SoftwareCompareCanvas(self)
        self._main_layout.replaceWidget(old, replacement)
        old.deleteLater()
        self._canvas = replacement
        replacement.panel_double_clicked.connect(self._toggle_maximize_asset)
        replacement.view_changed.connect(self._refresh_pixel_notice)
        self._software = True
        self._refresh_layout()
        replacement.set_pixel_mode(old._pixel_mode)
        replacement._pixel_zoom = old._pixel_zoom
        replacement.set_layout_mode(old.layout_mode)
        replacement.set_view_state(regions, linked)
        replacement.set_roi_mode(roi_mode)
        replacement.set_theme_colors(old._colors)
        replacement._annotations = list(annotations)
        replacement.set_annotation_shape(annotation_shape)
        replacement.set_annotation_color(annotation_color)
        replacement.set_annotation_linked(annotation_linked)
        replacement.set_annotating(annotating)
        for signal, method in (
            (self._annotation_bar.shape_changed, old.set_annotation_shape),
            (self._annotation_bar.color_changed, old.set_annotation_color),
            (self._annotation_bar.link_changed, old.set_annotation_linked),
            (self._annotation_bar.undo_requested, old.undo_annotation),
            (self._annotation_bar.clear_requested, old.clear_annotations),
            (self._annotation_bar.delete_requested, old.delete_annotation),
        ):
            signal.disconnect(method)
        self._annotation_bar.shape_changed.connect(replacement.set_annotation_shape)
        self._annotation_bar.color_changed.connect(replacement.set_annotation_color)
        self._annotation_bar.link_changed.connect(replacement.set_annotation_linked)
        self._annotation_bar.undo_requested.connect(replacement.undo_annotation)
        self._annotation_bar.clear_requested.connect(replacement.clear_annotations)
        self._annotation_bar.delete_requested.connect(replacement.delete_annotation)
        replacement.annotations_changed.connect(self._annotation_bar.set_annotations)
        self._fit_button.clicked.disconnect()
        self._fit_button.clicked.connect(replacement.reset_fit)
        self._roi_button.toggled.disconnect()
        self._roi_button.toggled.connect(replacement.set_roi_mode)
        if snapshot is not None:
            replacement.submit_group(snapshot)
        self._status.setText(f"{reason}；已切换软件渲染")

    def _choose_files(self) -> None:
        if self.media_kind == "image":
            title = "添加本地图像"
            files = (
                "图像 (*.png *.jpg *.jpeg *.jfif *.bmp *.gif *.tif *.tiff *.webp "
                "*.avif *.heic *.heif *.svg *.svgz *.pdf *.psd *.tga *.ico *.icns "
                "*.pbm *.pgm *.ppm *.xbm *.xpm *.dng *.cr2 *.cr3 *.nef *.arw "
                "*.raf *.rw2 *.orf *.pef);;所有文件 (*)"
            )
        else:
            title = "添加本地视频"
            files = "视频 (*.mp4 *.mov *.mkv *.avi *.webm);;所有文件 (*)"
        names, _ = QFileDialog.getOpenFileNames(self, translate(title), "", translate(files))
        if names:
            self.load_files([Path(name) for name in names])

    def _choose_replacement(self) -> None:
        if self._file_list.currentItem() is None:
            self._on_error("请先选中需要替换的一路")
            return
        name, _ = QFileDialog.getOpenFileName(
            self,
            translate("替换图像" if self.media_kind == "image" else "替换视频"),
            "",
            translate("图像 (*.*);;所有文件 (*)")
            if self.media_kind == "image"
            else translate("视频 (*.mp4 *.mov *.mkv *.avi *.webm);;所有文件 (*)"),
        )
        if name:
            self.replace_selected(Path(name))

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.load_files(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _refresh_file_list(self, selected_id: str | None = None) -> None:
        self._file_list.clear()
        for asset in self._active_assets().values():
            prefix = (
                "[已脱离同步] "
                if self.media_kind == "video" and asset.asset_id in self._excluded_ids
                else ""
            )
            self._file_list.addItem(prefix + asset.label)
            item = self._file_list.item(self._file_list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, asset.asset_id)
            if self.media_kind == "image":
                item.setToolTip(
                    f"{asset.path}\n{asset.coded_width}×{asset.coded_height} · {asset.codec_name}"
                )
            else:
                timeline = self._timelines[asset.asset_id]
                item.setToolTip(
                    f"{asset.path}\n{asset.coded_width}×{asset.coded_height} · "
                    f"{timeline.frame_count} 帧 · {asset.codec_name or '未知编码'}"
                )
            if asset.asset_id == selected_id:
                self._file_list.setCurrentItem(item)
        if self._file_list.currentItem() is None and self._file_list.count():
            self._file_list.setCurrentRow(0)

    def _show_selected_asset_info(self) -> None:
        asset_id = self._selected_asset_id()
        assets = self._active_assets()
        if asset_id is None or asset_id not in assets:
            self._asset_info.setText("选中一路查看源信息与预览限制")
            return
        asset = assets[asset_id]
        if self.media_kind == "image":
            note = self._image_notes.get(asset_id, "")
            self._asset_info.setText(
                f"{asset.coded_width}×{asset.coded_height} · {asset.codec_name or '图像'}\n"
                f"RGB8 预览 · {note or '源文件只读'}"
            )
            return
        color = asset.color_info
        transform = asset.display_transform
        notices = ["RGB8 预览"]
        if color.bit_depth and color.bit_depth > 8:
            notices.append(f"源 {color.bit_depth}-bit")
        if color.inferred:
            notices.append("色彩元信息缺失，已推定")
        if color.hdr_unsupported:
            notices.append("HDR/BT.2020 暂不显示画面，仅可查看元信息")
        if transform.rotation_degrees:
            notices.append(f"逆时针旋转 {transform.rotation_degrees}°")
        if transform.sample_aspect_ratio != 1:
            notices.append(f"SAR {transform.sample_aspect_ratio}")
        matrix = color.matrix or "未知"
        range_name = color.range or "未知"
        self._asset_info.setText(
            f"{asset.coded_width}×{asset.coded_height} · {asset.codec_name or '未知编码'}\n"
            f"色彩 {matrix}/{range_name} · {' · '.join(notices)}"
            + ("\n已脱离时间同步，画面保留在退出时" if asset_id in self._excluded_ids else "")
        )

    def _refresh_participant_button(self) -> None:
        if self.media_kind == "image":
            return
        asset_id = self._selected_asset_id()
        self._participant_button.setEnabled(asset_id is not None)
        self._participant_button.setText(
            "重新加入时间同步" if asset_id in self._excluded_ids else "暂停选中路同步"
        )

    def _refresh_reference_combo(self, replaced: tuple[str, str] | None = None) -> None:
        previous = self._reference_combo.currentData()
        if replaced is not None and previous == replaced[0]:
            previous = replaced[1]
        if previous not in self._assets or previous in self._excluded_ids:
            previous = next((key for key in self._assets if key not in self._excluded_ids), None)
        self._reference_combo.blockSignals(True)
        self._reference_combo.clear()
        for index, asset in enumerate(self._assets.values()):
            self._reference_combo.addItem(asset.label, asset.asset_id)
            if asset.asset_id in self._excluded_ids:
                self._reference_combo.model().item(index).setEnabled(False)
                self._reference_combo.setItemData(
                    index, "先重新加入时间同步，才能设为基准", Qt.ItemDataRole.ToolTipRole
                )
        if previous is not None:
            self._reference_combo.setCurrentIndex(tuple(self._assets).index(previous))
        self._reference_combo.blockSignals(False)

    def _selected_asset_id(self) -> str | None:
        item = self._file_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _set_view_linked(self, linked: bool) -> None:
        self._canvas.set_linked(linked, self._selected_asset_id())

    def _change_pixel_mode(self) -> None:
        enabled = bool(self._pixel_mode_combo.currentData())
        self._canvas.set_pixel_mode(enabled)
        self._pixel_notice.setVisible(enabled)
        self._refresh_pixel_notice()

    def _refresh_pixel_notice(self) -> None:
        if self._canvas.pixel_zoom is not None:
            self._pixel_notice.setText(
                f"原生像素检查：{self._canvas.pixel_zoom:g}×；忽略 SAR；Ctrl+滚轮调整倍率"
            )

    def _show_selected_offsets(self) -> None:
        asset_id = self._selected_asset_id()
        time_offset = self._time_offsets.get(asset_id, Fraction(0))
        frame_offset = self._frame_offsets.get(asset_id, 0)
        self._time_offset_input.setText(f"{float(time_offset):+.3f}")
        self._frame_offset_input.setText(f"{frame_offset:+d}")

    def _apply_offsets(self) -> None:
        asset_id = self._selected_asset_id()
        if asset_id is None or self._transport is None:
            self._on_error("请先选中一路视频")
            return
        raw_time = self._time_offset_input.text().strip()
        raw_frame = self._frame_offset_input.text().strip()
        if not re.fullmatch(r"[+-]?\d+(?:\.\d{1,3})?", raw_time):
            self._on_error("时间 Offset 请输入最多三位小数的秒数")
            return
        if not re.fullmatch(r"[+-]?\d+", raw_frame):
            self._on_error("帧 Offset 请输入整数")
            return
        time_offset = Fraction(raw_time)
        frame_offset = int(raw_frame)
        spec = self._transport.spec
        if asset_id == spec.reference_id and (time_offset or frame_offset):
            self._on_error("基准视频 Offset 必须为 0")
            return
        time_offsets = dict(self._time_offsets)
        frame_offsets = dict(self._frame_offsets)
        time_offsets[asset_id] = time_offset
        frame_offsets[asset_id] = frame_offset
        self._canvas.clear_group()
        if spec.mode is SyncMode.TIME:
            self._rebuild_transport(
                anchor_time=self._displayed_time(),
                offsets=(time_offsets, frame_offsets),
            )
        else:
            anchor = (
                self._transport.displayed.reference_ordinal + 1
                if self._transport.displayed
                else None
            )
            self._rebuild_transport(
                anchor_ui_frame=anchor,
                offsets=(time_offsets, frame_offsets),
            )
        self._show_selected_offsets()

    def _toggle_time_participation(self) -> None:
        asset_id = self._selected_asset_id()
        transport = self._transport
        if asset_id is None or transport is None or transport.displayed is None:
            self._on_error("请先等待完整帧组，再调整时间参与状态")
            return
        if asset_id == transport.spec.reference_id and asset_id not in self._excluded_ids:
            self._on_error("基准视频必须参与同步；请先切换基准")
            return
        playing = transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
        anchor_time = transport.displayed.requested_global_time
        anchor_frame = transport.displayed.reference_ordinal + 1
        if asset_id in self._excluded_ids:
            self._excluded_ids.remove(asset_id)
            self._held_frames.pop(asset_id, None)
        else:
            frame = transport.displayed.frames.get(asset_id)
            if frame is None:
                self._on_error("选中路尚无已显示的同步帧")
                return
            self._held_frames[asset_id] = frame
            self._excluded_ids.add(asset_id)
        self._refresh_file_list(selected_id=asset_id)
        self._refresh_reference_combo()
        self._canvas.clear_group()
        self._rebuild_transport(
            anchor_time=anchor_time if transport.spec.mode is SyncMode.TIME else None,
            anchor_ui_frame=anchor_frame if transport.spec.mode is SyncMode.FRAME else None,
            resume=playing,
        )

    def load_files(self, paths: list[Path]) -> None:
        if self.media_kind == "image":
            self._load_images(paths)
            return
        self._load_error_notice = None
        errors: list[str] = []
        for path in paths:
            if len(self._assets) + self._pending_add - len(self._partial_tasks) >= 6:
                errors.append(f"{path.name}：最多导入 6 路")
                continue
            try:
                self._loader.submit(path)
            except RuntimeError as exc:
                errors.append(f"{path.name}：{exc}")
                continue
            self._pending_add += 1
        if self._pending_add:
            self._status.setText(f"正在后台探测/索引 {self._pending_add} 路；窗口仍可操作")
        if errors:
            QMessageBox.warning(self, translate("部分视频未导入"), translate("\n".join(errors)))

    def _drain_load_results(self) -> None:
        while (result := self._loader.pop_result()) is not None:
            self._apply_load_result(result)
        while (image_result := self._image_loader.pop_result()) is not None:
            self._apply_image_result(image_result)
        if self._load_error_notice is not None:
            self._on_error(self._load_error_notice)

    def _load_images(self, paths: list[Path]) -> None:
        errors: list[str] = []
        for path in paths:
            additions = sum(task.replace_id is None for task in self._image_pending)
            if len(self._image_assets) + additions >= 6:
                errors.append(f"{path.name}：最多导入 6 路")
                continue
            if not path.is_file():
                errors.append(f"{path.name}：文件不存在")
                continue
            try:
                task = self._image_loader.submit(path)
            except RuntimeError as exc:
                errors.append(f"{path.name}：{exc}")
                continue
            self._image_pending.add(task)
        if self._image_pending:
            self._status.setText(f"正在读取 {len(self._image_pending)} 张图像")
        if errors:
            QMessageBox.warning(self, translate("部分图像未导入"), translate("\n".join(errors)))

    def _apply_image_result(self, result: ImageLoadResult) -> None:
        task = result.task
        if task not in self._image_pending:
            return
        self._image_pending.remove(task)
        replace_id = task.replace_id
        if replace_id is not None and self._image_replacements.get(replace_id) is not task:
            return
        if replace_id is not None:
            del self._image_replacements[replace_id]
        if result.error:
            if self.media_kind == "image":
                self._on_error(f"{task.path.name}：{result.error}；原画面未改变")
            return
        assert result.asset is not None and result.frame is not None
        old_bytes = (
            self._image_frames[replace_id].rgb.nbytes if replace_id in self._image_frames else 0
        )
        used = sum(frame.rgb.nbytes for frame in self._image_frames.values())
        if used - old_bytes + result.frame.rgb.nbytes > 1024 * 1024 * 1024:
            if self.media_kind == "image":
                self._on_error("图像组 RGB 缓冲超过 1 GiB，原画面未改变")
            return
        selected = self._selected_asset_id() if self.media_kind == "image" else None
        asset = result.asset
        if replace_id is None:
            self._image_assets[asset.asset_id] = asset
        elif replace_id in self._image_assets:
            self._image_assets = {
                (asset.asset_id if key == replace_id else key): (
                    asset if key == replace_id else old
                )
                for key, old in self._image_assets.items()
            }
            self._image_frames.pop(replace_id, None)
            self._image_notes.pop(replace_id, None)
            if self._maximized_id == replace_id and self.media_kind == "image":
                self._maximized_id = asset.asset_id
            if selected == replace_id:
                selected = asset.asset_id
        else:
            return
        self._image_frames[asset.asset_id] = result.frame
        self._image_notes[asset.asset_id] = result.note
        self._image_revision += 1
        self._image_snapshot = None
        if self.media_kind == "image":
            self._refresh_file_list(selected_id=selected)
            self._refresh_layout()
            self._present_images()

    def _present_images(self) -> None:
        if self.media_kind != "image":
            return
        if not self._image_assets:
            self._canvas.clear_group()
            self._status.setText("添加本地图像；可比较 1–6 张")
            return
        if self._image_snapshot is None:
            self._image_snapshot = FrameGroupSnapshot(
                (1, self._image_revision, 0),
                Fraction(0),
                0,
                {key: self._image_frames[key] for key in self._image_assets},
            )
        self._canvas.submit_group(self._image_snapshot)
        self._status.setText(f"正在对比 {len(self._image_assets)} 张图像 · RGB8 预览 · 源文件只读")

    def _apply_load_result(self, result: LoadResult) -> None:
        if result.task in self._cancelled_loads:
            return
        replace_id = result.task.replace_id
        if replace_id is None:
            if not result.partial:
                self._pending_add -= 1
        elif self._pending_replacements.get(replace_id) is not result.task:
            return
        elif not result.partial:
            del self._pending_replacements[replace_id]
        partial_id = self._partial_tasks.get(result.task)
        if result.error:
            if partial_id is not None:
                self._partial_tasks.pop(result.task, None)
                self._assets.pop(partial_id, None)
                self._timelines.pop(partial_id, None)
                self._time_offsets.pop(partial_id, None)
                self._frame_offsets.pop(partial_id, None)
                self._excluded_ids.discard(partial_id)
                self._held_frames.pop(partial_id, None)
                self._refresh_file_list()
                self._refresh_reference_combo()
                self._rebuild_transport()
            self._load_error_notice = f"{result.task.path.name}：{result.error}"
            self._on_error(self._load_error_notice)
            return
        assert result.asset is not None and result.timeline is not None
        if partial_id is not None:
            if not result.partial:
                self._partial_tasks.pop(result.task, None)
            self._timelines[partial_id] = result.timeline
            if self._transport is not None:
                self._transport.extend_timeline(partial_id, result.timeline)
                if self._pending_transport_anchor is not None:
                    valid = self._transport.mapper.valid_range(self._transport.spec)
                    if not valid.empty:
                        anchor_frame, anchor_time, resume = self._pending_transport_anchor
                        self._rebuild_transport(
                            anchor_ui_frame=anchor_frame, anchor_time=anchor_time, resume=resume
                        )
                    elif not any(
                        self._timelines[key].provisional
                        for key in self._transport.spec.participants
                    ):
                        self._pending_transport_anchor = None
                        self._on_error("参与视频没有公共有效范围")
            if result.partial:
                self._status.setText(
                    f"{result.asset.label}：已索引 {result.timeline.frame_count} 帧，"
                    "可播放已覆盖区域；后台继续索引"
                )
            else:
                self._status.setText(f"{result.asset.label}：索引完成")
            return
        selected = self._selected_asset_id()
        anchor_time = self._displayed_time()
        asset = result.asset
        if replace_id is None:
            self._assets[asset.asset_id] = asset
            self._time_offsets[asset.asset_id] = Fraction(0)
            self._frame_offsets[asset.asset_id] = 0
            if result.partial:
                self._partial_tasks[result.task] = asset.asset_id
        elif replace_id in self._assets:
            self._assets = {
                (asset.asset_id if key == replace_id else key): (
                    asset if key == replace_id else old
                )
                for key, old in self._assets.items()
            }
            del self._timelines[replace_id]
            self._excluded_ids.discard(replace_id)
            self._held_frames.pop(replace_id, None)
            self._time_offsets[asset.asset_id] = self._time_offsets.pop(replace_id, Fraction(0))
            self._frame_offsets[asset.asset_id] = self._frame_offsets.pop(replace_id, 0)
            if self._maximized_id == replace_id:
                self._maximized_id = asset.asset_id
            if selected == replace_id:
                selected = asset.asset_id
        else:
            return
        self._timelines[asset.asset_id] = result.timeline
        self._refresh_file_list(selected_id=selected)
        self._refresh_reference_combo(
            replaced=(replace_id, asset.asset_id) if replace_id is not None else None
        )
        self._rebuild_transport(anchor_time=anchor_time)
        if self._pending_add:
            self._status.setText(
                f"已导入 {len(self._assets)} 路，仍在索引 {self._pending_add} 路；已覆盖区域可播放"
            )

    def _remove_selected_image(self) -> None:
        asset_id = self._selected_asset_id()
        if asset_id is None:
            self._on_error("请先选中需要移除的图像")
            return
        self._image_assets.pop(asset_id, None)
        self._image_frames.pop(asset_id, None)
        self._image_notes.pop(asset_id, None)
        self._image_replacements.pop(asset_id, None)
        if self._maximized_id == asset_id:
            self._maximized_id = None
        self._image_revision += 1
        self._image_snapshot = None
        self._canvas.clear_group()
        self._refresh_file_list()
        self._refresh_layout()
        self._present_images()

    def remove_selected(self) -> None:
        if self.media_kind == "image":
            self._remove_selected_image()
            return
        asset_id = self._selected_asset_id()
        if asset_id is None:
            self._on_error("请先在视频列表中选中需要移除的一路")
            return
        for task, partial_id in tuple(self._partial_tasks.items()):
            if partial_id == asset_id:
                self._loader.cancel(task)
                self._cancelled_loads.add(task)
                del self._partial_tasks[task]
                self._pending_add -= 1
                break
        previous_spec = self._transport.spec if self._transport else None
        displayed = self._transport.displayed if self._transport else None
        del self._assets[asset_id]
        del self._timelines[asset_id]
        self._excluded_ids.discard(asset_id)
        self._held_frames.pop(asset_id, None)
        self._time_offsets.pop(asset_id, None)
        self._frame_offsets.pop(asset_id, None)
        if self._assets and len(self._excluded_ids) == len(self._assets):
            promoted_id = next(iter(self._assets))
            self._excluded_ids.remove(promoted_id)
            self._held_frames.pop(promoted_id, None)
        if self._maximized_id == asset_id:
            self._maximized_id = None
        self._pending_replacements.pop(asset_id, None)
        self._refresh_file_list()
        self._refresh_reference_combo()
        new_reference_id = self._reference_combo.currentData()
        anchor_time = None
        anchor_ui_frame = None
        if displayed is not None and previous_spec is not None and new_reference_id is not None:
            if previous_spec.mode is SyncMode.TIME:
                anchor_time = displayed.requested_global_time + self._time_offsets.get(
                    new_reference_id, Fraction(0)
                )
            else:
                anchor_ui_frame = (
                    displayed.reference_ordinal + self._frame_offsets.get(new_reference_id, 0) + 1
                )
        self._rebuild_transport(anchor_time=anchor_time, anchor_ui_frame=anchor_ui_frame)
        if not self._assets:
            self._status.setText("已移除全部视频；可添加本地视频")

    def replace_selected(self, path: Path) -> bool:
        if self.media_kind == "image":
            asset_id = self._selected_asset_id()
            if asset_id is None:
                self._on_error("请先选中需要替换的图像")
                return False
            if not path.is_file():
                self._on_error(f"替换失败，原图像未改变：文件不存在 {path}")
                return False
            try:
                task = self._image_loader.submit(path, replace_id=asset_id)
            except RuntimeError as exc:
                self._on_error(str(exc))
                return False
            self._image_pending.add(task)
            self._image_replacements[asset_id] = task
            self._status.setText(f"正在读取替换图像 {path.name}，原画面保持显示")
            return True
        asset_id = self._selected_asset_id()
        if asset_id is None:
            self._on_error("请先在视频列表中选中需要替换的一路")
            return False
        if not path.is_file():
            self._on_error(f"替换失败，原视频未改变：文件不存在 {path}")
            return False
        try:
            task = self._loader.submit(path, replace_id=asset_id)
        except RuntimeError as exc:
            self._on_error(f"替换失败，原视频未改变：{exc}")
            return False
        self._pending_replacements[asset_id] = task
        self._status.setText(f"正在后台索引替换文件 {path.name}，原画面保持显示")
        return True

    def _displayed_time(self) -> Fraction | None:
        if self._transport and self._transport.displayed:
            return self._transport.displayed.requested_global_time
        return None

    def _refresh_layout(self) -> None:
        assets = self._active_assets()
        if self._maximized_id not in assets:
            self._maximized_id = None
        order = (self._maximized_id,) if self._maximized_id else tuple(assets)
        self._canvas.set_layout(order, assets)

    def _toggle_maximize_asset(self, asset_id: str) -> None:
        if asset_id not in self._active_assets():
            return
        self._maximized_id = None if self._maximized_id == asset_id else asset_id
        self._refresh_layout()

    def _move_selected(self, direction: int) -> None:
        asset_id = self._selected_asset_id()
        assets = self._active_assets()
        order = list(assets)
        if asset_id is None:
            return
        index = order.index(asset_id)
        target = index + direction
        if not 0 <= target < len(order):
            return
        order[index], order[target] = order[target], order[index]
        if self.media_kind == "image":
            self._image_assets = {key: assets[key] for key in order}
            self._image_revision += 1
            self._image_snapshot = None
        else:
            self._assets = {key: assets[key] for key in order}
        self._refresh_file_list(selected_id=asset_id)
        if self.media_kind == "video":
            self._refresh_reference_combo()
        self._refresh_layout()
        if self.media_kind == "image":
            self._present_images()

    def _rebuild_transport(
        self,
        anchor_ui_frame: int | None = None,
        anchor_time: Fraction | None = None,
        offsets: tuple[dict[str, Fraction], dict[str, int]] | None = None,
        resume: bool = False,
    ) -> None:
        self._pending_transport_anchor = None
        previous_spec = self._transport.spec if self._transport is not None else None
        if offsets is not None:
            self._time_offsets.update(offsets[0])
            self._frame_offsets.update(offsets[1])
        if self._transport is not None:
            self._transport.close()
            self._transport.deleteLater()
            self._transport = None
        self._refresh_layout()
        order = tuple(self._assets)
        if not order:
            return
        reference_id = self._reference_combo.currentData() or order[0]
        if previous_spec and reference_id != previous_spec.reference_id:
            time_shift = self._time_offsets.get(reference_id, Fraction(0))
            frame_shift = self._frame_offsets.get(reference_id, 0)
            self._time_offsets = {
                key: value - time_shift for key, value in self._time_offsets.items()
            }
            self._frame_offsets = {
                key: value - frame_shift for key, value in self._frame_offsets.items()
            }
        participants = tuple(key for key in order if key not in self._excluded_ids)
        spec = TimelineSpec(
            SyncMode(self._mode.currentData()),
            reference_id,
            participants,
            time_offsets=self._time_offsets,
            frame_offsets=self._frame_offsets,
        )
        transport = TransportController(self._assets, self._timelines, spec, parent=self)
        self._transport = transport
        transport.set_speed(Fraction(self._speed_combo.currentData()))
        self._loop_button.blockSignals(True)
        self._loop_button.setChecked(False)
        self._loop_button.blockSignals(False)
        self._loop_status.setText("循环：未设置（时间轴变更后重置）")
        transport.group_ready.connect(self._on_group)
        transport.state_changed.connect(self._on_state)
        transport.error_occurred.connect(self._on_error)
        self._show_selected_offsets()
        valid = transport.mapper.valid_range(spec)
        if valid.empty:
            self._play_button.setEnabled(False)
            self._canvas.clear_group()
            if any(self._timelines[key].provisional for key in participants):
                self._pending_transport_anchor = (anchor_ui_frame, anchor_time, resume)
                self._status.setText("等待索引覆盖公共时间区间")
            else:
                self._on_error("参与视频没有公共有效范围")
            return
        self._play_button.setEnabled(True)
        self._range_notice = None
        if anchor_ui_frame is not None:
            clamped = max(int(valid.start) + 1, min(int(valid.end) + 1, anchor_ui_frame))
            if clamped != anchor_ui_frame:
                self._range_notice = "原位置超出新公共区间，已定位到最近边界"
            transport.seek_reference_frame(clamped, resume=resume)
        elif anchor_time is not None:
            if spec.mode is SyncMode.TIME:
                last = transport.mapper.last_event(spec).global_time
                clamped_time = max(Fraction(valid.start), min(last, anchor_time))
                if clamped_time != anchor_time:
                    self._range_notice = "原位置超出新公共区间，已定位到最近边界"
                transport.seek_time(clamped_time, resume=resume)
            else:
                ordinal = self._timelines[reference_id].ordinal_at(anchor_time)
                clamped = max(int(valid.start), min(int(valid.end), ordinal))
                if clamped != ordinal:
                    self._range_notice = "原位置超出新公共区间，已定位到最近边界"
                transport.seek_reference_frame(clamped + 1, resume=resume)
        if anchor_ui_frame is None and anchor_time is None:
            if spec.mode is SyncMode.TIME:
                transport.seek_time(Fraction(valid.start), resume=resume)
            else:
                transport.seek_reference_frame(int(valid.start) + 1, resume=resume)
        self._status.setText(f"{len(participants)} 路参与同步，等待完整帧组")

    def _on_group(self, snapshot) -> None:
        if self.media_kind == "image":
            return
        if self._held_frames:
            snapshot_for_canvas = FrameGroupSnapshot(
                snapshot.group_id,
                snapshot.requested_global_time,
                snapshot.reference_ordinal,
                {**snapshot.frames, **self._held_frames},
                {**snapshot.boundary_states, **dict.fromkeys(self._held_frames, "detached")},
                snapshot.mapping_revision,
            )
        else:
            snapshot_for_canvas = snapshot
        self._canvas.submit_group(snapshot_for_canvas)
        self._time_input.setText(format_timecode(snapshot.requested_global_time))
        self._frame_input.setText(str(snapshot.reference_ordinal + 1))
        if not self._slider.isSliderDown() and self._transport:
            valid = self._transport.mapper.valid_range(self._transport.spec)
            if self._transport.spec.mode is SyncMode.TIME:
                end = self._transport.mapper.last_event(self._transport.spec).global_time
                span = end - valid.start
                value = (
                    round((snapshot.requested_global_time - valid.start) * 10000 / span)
                    if span
                    else 0
                )
            else:
                span = valid.end - valid.start
                value = (
                    round((snapshot.reference_ordinal - valid.start) * 10000 / span) if span else 0
                )
            self._slider.blockSignals(True)
            self._slider.setValue(max(0, min(10000, value)))
            self._slider.blockSignals(False)
        self._status.setText(
            f"已同步显示 {len(snapshot.frames)} 路"
            + (f"，{len(self._held_frames)} 路脱离同步" if self._held_frames else "")
            + " · "
            f"组 {snapshot.group_id} · 缓存 {self._transport.cache.used_bytes // (1024 * 1024)} MiB"
            + (f" · {self._range_notice}" if self._range_notice else "")
            + (f" · 错误：{self._load_error_notice}" if self._load_error_notice else "")
        )
        self._range_notice = None

    def _on_state(self, state: TransportState) -> None:
        if self.media_kind == "image":
            return
        playing = state in {TransportState.PLAYING, TransportState.BUFFERING}
        self._play_button.setText("暂停" if playing else "播放")

    def _on_error(self, message: str) -> None:
        self._status.setText(f"错误：{message}")

    def _toggle_play(self) -> None:
        if self._transport is None:
            return
        if self._transport.state in {TransportState.PLAYING, TransportState.BUFFERING}:
            self._transport.pause()
        else:
            self._transport.play()

    def _step(self, direction: int) -> None:
        if self._transport is None:
            return
        try:
            raw = self._step_amount.text().strip()
            amount = Fraction(raw)
            unit = self._step_unit.currentData()
            if amount <= 0 or (unit == "frame" and amount.denominator != 1):
                raise ValueError("帧步进需正整数；秒步进需正数")
            if unit == "second" and len(raw.partition(".")[2]) > 3:
                raise ValueError("秒步进最多精确到毫秒")
            self._transport.step(direction, amount, unit)
        except (ValueError, TimelineError) as exc:
            self._on_error(str(exc))

    def _seek_time_input(self) -> None:
        if self._transport is None:
            return
        try:
            self._transport.seek_time(parse_timecode(self._time_input.text()))
        except (ValueError, TimelineError) as exc:
            self._on_error(str(exc))

    def _seek_frame_input(self) -> None:
        if self._transport is None:
            return
        try:
            self._transport.seek_reference_frame(int(self._frame_input.text()))
        except (ValueError, TimelineError) as exc:
            self._on_error(str(exc))

    def _switch_mode(self) -> None:
        if self._assets:
            anchor = (
                self._transport.displayed.reference_ordinal + 1
                if self._transport and self._transport.displayed
                else None
            )
            self._rebuild_transport(anchor_ui_frame=anchor)

    def _switch_reference(self) -> None:
        if self._transport is None:
            return
        new_reference_id = self._reference_combo.currentData()
        old_spec = self._transport.spec
        if new_reference_id in self._excluded_ids:
            self._reference_combo.blockSignals(True)
            self._reference_combo.setCurrentIndex(tuple(self._assets).index(old_spec.reference_id))
            self._reference_combo.blockSignals(False)
            self._on_error("脱离同步的视频不能设为基准；请先重新加入")
            return
        if new_reference_id == old_spec.reference_id:
            return
        displayed = self._transport.displayed
        if displayed is None:
            self._rebuild_transport()
            self._show_selected_offsets()
            return
        if old_spec.mode is SyncMode.TIME:
            anchor_time = displayed.requested_global_time + old_spec.time_offsets[new_reference_id]
            self._rebuild_transport(anchor_time=anchor_time)
        else:
            anchor_ui_frame = (
                displayed.reference_ordinal + old_spec.frame_offsets[new_reference_id] + 1
            )
            self._rebuild_transport(anchor_ui_frame=anchor_ui_frame)
        self._show_selected_offsets()

    def _change_speed(self) -> None:
        if self._transport is not None:
            self._transport.set_speed(Fraction(self._speed_combo.currentData()))

    def _choose_screenshot_dir(self, kind: str) -> None:
        directory = QFileDialog.getExistingDirectory(self, translate("选择截图保存目录"))
        if directory:
            if kind == "view":
                self.save_view_screenshot(Path(directory))
            else:
                self.save_frame_screenshots(Path(directory))

    def choose_export_options(self) -> None:
        """Ask layout and format, then export the visible compare area."""
        if self._current_display_snapshot() is None:
            QMessageBox.warning(
                self,
                translate("暂时无法导出"),
                translate("还没有可导出的画面。请先导入文件，等画面显示后再导出。"),
            )
            return
        dialog = ExportOptionsDialog(self)
        if dialog.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        suffix = format_suffix(options.image_format)
        directory = self._export_dir
        if directory is None or not Path(directory).is_dir():
            pictures = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.PicturesLocation
            )
            directory = Path(pictures) if pictures else Path.home()
        default = directory / f"对比图_{datetime.now():%Y%m%d_%H%M%S}{suffix}"
        name, _ = QFileDialog.getSaveFileName(
            self,
            translate("保存对比图"),
            str(default),
            translate(format_filter(options.image_format)),
        )
        if not name:
            return
        target = Path(name)
        if (
            target.suffix.lower() not in {".png", ".jpg", ".jpeg"}
            or target.suffix.lower() != suffix
        ):
            target = target.with_suffix(suffix)
        self._export_dir = target.parent
        if options.edit_first:
            self.start_annotation_export(
                target,
                layout=options.layout,
                image_format=options.image_format,
                quality=options.quality,
            )
        else:
            self.export_comparison_image(
                target,
                layout=options.layout,
                image_format=options.image_format,
                quality=options.quality,
            )

    def start_annotation_export(
        self,
        target: Path,
        *,
        layout: str = "window",
        image_format: str = "PNG",
        quality: int = 95,
    ) -> None:
        """Enter annotation mode; the pending export runs on “完成并导出”."""
        if self._current_display_snapshot() is None:
            self._on_error("还没有可导出的完整同步帧组")
            return
        if self._saving_annotated_export:
            return
        self._canvas.clear_annotations()
        self._pending_annotated_export = (target, layout, image_format, quality)
        self._annotation_bar.setVisible(True)
        self._canvas.set_annotating(True)
        self._status.setText(
            "标注模式：在画面上拖拽绘画；取消“标注联动”可只画起笔区域；完成后点“完成并导出”"
        )

    def _finish_annotation_export(self) -> None:
        pending = self._pending_annotated_export
        if pending is None or self._saving_annotated_export:
            return
        target, layout, image_format, quality = pending
        submitted = self.export_comparison_image(
            target, layout=layout, image_format=image_format, quality=quality
        )
        if submitted is None:
            return
        self._saving_annotated_export = True
        self._annotation_bar.setEnabled(False)
        self._canvas.set_annotating(False)

    def _cancel_annotation_export(self) -> None:
        if self._saving_annotated_export:
            return
        self._annotation_bar.setVisible(False)
        self._canvas.set_annotating(False)
        self._canvas.clear_annotations()
        self._pending_annotated_export = None
        self._status.setText("已取消标注导出；本次标注已清除")

    def _composite_plan(
        self, layout: str
    ) -> tuple[tuple[CompositeTile, ...], CompositeLayout, list[str]] | None:
        snapshot = self._current_display_snapshot()
        if snapshot is None:
            self._on_error("还没有可导出的完整同步帧组")
            return None
        canvas = self._canvas
        assets = self._active_assets()
        order = canvas.display_order
        dpr = max(1.0, canvas.devicePixelRatioF())
        boxes = pane_boxes(
            canvas.width(),
            canvas.height(),
            order,
            assets,
            snapshot,
            layout=canvas.layout_mode,
            pixel_zoom=canvas.pixel_zoom,
        )
        tiles: list[CompositeTile] = []
        positions: list[tuple[float, float]] = []
        skipped: list[str] = []
        for asset_id in order:
            asset = assets[asset_id]
            if asset_id not in snapshot.frames:
                skipped.append(f"{asset.label}（没有已显示的画面）")
                continue
            if asset.color_info.hdr_unsupported:
                # HDR panes cannot produce trustworthy RGB8 pixels, so they stay out.
                skipped.append(f"{asset.label}（HDR/BT.2020 无可信 RGB8 画面）")
                continue
            transform = pane_transform(
                canvas.width(),
                canvas.height(),
                order,
                assets,
                snapshot,
                canvas.view_regions,
                asset_id,
                pixel_zoom=canvas.pixel_zoom,
                device_pixel_ratio=dpr,
                layout=canvas.layout_mode,
            )
            if transform is None:
                skipped.append(f"{asset.label}（无法计算显示区域）")
                continue
            content = transform.content_rect
            tiles.append(
                CompositeTile(
                    asset_id,
                    transform.region,
                    max(1, round(content.width * dpr)),
                    max(1, round(content.height * dpr)),
                    name=asset.label,
                    info=(
                        f"{asset.coded_width}×{asset.coded_height} · {asset.codec_name}"
                        if self.media_kind == "image"
                        else (
                            f"{translate('帧')} {{frame}} · PTS {{pts}}{{detached}}"
                            if language() != "zh_CN"
                            else "帧 {frame} · PTS {pts}{detached}"
                        ).format(
                            frame=snapshot.frames[asset_id].ordinal + 1,
                            pts=snapshot.frames[asset_id].pts,
                            detached=(
                                (
                                    f" · {translate('已脱离同步')}"
                                    if language() != "zh_CN"
                                    else " · 已脱离同步"
                                )
                                if snapshot.boundary_states.get(asset_id) == "detached"
                                else ""
                            ),
                        )
                    ),
                )
            )
            box = boxes.get(asset_id)
            positions.append((box.y, box.x) if box is not None else (content.y, content.x))
        if not tiles:
            self._on_error("没有可导出的画面：所有路都缺少可信预览")
            return None
        if layout == "window":
            rows = rows_from_boxes(positions)
        else:
            aspects = [tile.pixel_width / tile.pixel_height for tile in tiles]
            rows = choose_rows(
                aspects,
                layout,
                width=sum(tile.pixel_width for tile in tiles),
                height=sum(tile.pixel_height for tile in tiles),
            )
        return tuple(tiles), CompositeLayout(rows), skipped

    def export_comparison_image(
        self,
        target: Path,
        *,
        layout: str = "window",
        image_format: str = "PNG",
        quality: int = 95,
    ) -> tuple[int, int, int] | None:
        """Compose the visible compare area into ``target`` and write a sidecar."""
        plan = self._composite_plan(layout)
        if plan is None:
            return None
        tiles, composite, skipped = plan
        snapshot = self._current_display_snapshot()
        if snapshot is None:
            self._on_error("还没有可导出的完整同步帧组")
            return None
        assets = self._active_assets()
        request = ScreenshotRequest(
            kind="compare",
            output_dir=target.parent,
            snapshot=snapshot,
            assets=dict(assets),
            spec=self._active_spec(),
            regions=self._canvas.view_regions,
            device_pixel_ratio=self._canvas.devicePixelRatioF(),
            display_asset_ids=tuple(tile.asset_id for tile in tiles),
            time_offsets=dict(self._time_offsets) if self.media_kind == "video" else {},
            frame_offsets=dict(self._frame_offsets) if self.media_kind == "video" else {},
            target_path=target,
            composite=composite,
            tiles=tiles,
            image_format=image_format,
            quality=quality,
            annotations=self._canvas.annotations,
            overlay_color=self._canvas._colors.overlay,
            overlay_backdrop=self._canvas._colors.overlay_backdrop,
        )
        try:
            self._screenshot_worker.submit(request)
        except RuntimeError as exc:
            self._on_error(str(exc))
            self._notify("critical", "导出失败", f"对比图未能保存。\n\n原因：{exc}")
            return None
        self._pending_export_note = (
            f"，已跳过 {len(skipped)} 路：{'、'.join(skipped)}" if skipped else ""
        )
        self._status.setText(
            f"正在导出对比图 · {len(composite.rows)} 行 · {len(tiles)} 路 · 组 {snapshot.group_id}"
        )
        return snapshot.group_id

    def _notify(self, level: str, title: str, text: str) -> None:
        """Show one modal notice at a time so worker callbacks cannot stack dialogs."""
        if self._message_open:
            return
        self._message_open = True
        try:
            if level == "critical":
                QMessageBox.critical(self, translate(title), translate(text))
            elif level == "warning":
                QMessageBox.warning(self, translate(title), translate(text))
            else:
                QMessageBox.information(self, translate(title), translate(text))
        finally:
            self._message_open = False

    def _current_display_snapshot(self) -> FrameGroupSnapshot | None:
        if self.media_kind == "image":
            display = self._canvas._snapshot
            return display if display is self._image_snapshot else None
        core = self._transport.displayed if self._transport else None
        display = self._canvas._snapshot
        if core is None or display is None:
            return None
        if not self._held_frames:
            return display if display is core else None
        if display.group_id != core.group_id or set(display.frames) != set(self._assets):
            return None
        if any(display.frames[key] is not frame for key, frame in core.frames.items()):
            return None
        if any(display.frames[key] is not frame for key, frame in self._held_frames.items()):
            return None
        return display

    def _active_spec(self) -> TimelineSpec:
        if self.media_kind == "video":
            assert self._transport is not None
            return self._transport.spec
        keys = tuple(self._image_assets)
        return TimelineSpec(SyncMode.FRAME, keys[0], keys)

    def _screenshot_request(
        self, kind: str, output_dir: Path, view_image=None
    ) -> tuple[int, int, int] | None:
        snapshot = self._current_display_snapshot()
        if snapshot is None:
            self._on_error("还没有可保存的完整同步帧组")
            return None
        request = ScreenshotRequest(
            kind=kind,
            output_dir=output_dir,
            snapshot=snapshot,
            assets=dict(self._active_assets()),
            spec=self._active_spec(),
            regions=self._canvas.view_regions,
            view_image=view_image,
            device_pixel_ratio=self._canvas.devicePixelRatioF(),
            display_asset_ids=tuple(self._active_assets()),
            time_offsets=dict(self._time_offsets) if self.media_kind == "video" else {},
            frame_offsets=dict(self._frame_offsets) if self.media_kind == "video" else {},
        )
        try:
            self._screenshot_worker.submit(request)
        except RuntimeError as exc:
            self._on_error(str(exc))
            return None
        self._status.setText(f"正在保存截图 · 完整组 {snapshot.group_id}")
        return snapshot.group_id

    def save_view_screenshot(self, output_dir: Path) -> tuple[int, int, int] | None:
        if self._current_display_snapshot() is None:
            self._on_error("还没有可保存的完整同步帧组")
            return None
        image = (
            self._canvas.grabFramebuffer()
            if isinstance(self._canvas, CompareCanvas)
            else self._canvas.grab().toImage()
        )
        if image.isNull():
            self._on_error("无法读取当前对比画布")
            return None
        return self._screenshot_request("view", output_dir, image.copy())

    def save_frame_screenshots(self, output_dir: Path) -> tuple[int, int, int] | None:
        return self._screenshot_request("frames", output_dir)

    def _drain_screenshot_results(self) -> None:
        while (result := self._screenshot_worker.pop_result()) is not None:
            if result.kind == "compare":
                self._finish_export(result)
                continue
            if result.error:
                self._on_error(f"截图失败（组 {result.group_id}）：{result.error}")
            else:
                self._status.setText(
                    f"已保存 {len(result.paths) // 2} 张 PNG · 组 {result.group_id} · "
                    f"{result.paths[0].parent}"
                )

    def _finish_export(self, result) -> None:
        note = self._pending_export_note
        self._pending_export_note = ""
        if (
            self._saving_annotated_export
            and self._pending_annotated_export is not None
            and result.target_path == self._pending_annotated_export[0]
        ):
            self._saving_annotated_export = False
            self._annotation_bar.setEnabled(True)
            if result.error:
                self._canvas.set_annotating(True)
            else:
                self._pending_annotated_export = None
                self._annotation_bar.setVisible(False)
                self._canvas.clear_annotations()
        if result.error:
            self._on_error(f"导出失败（组 {result.group_id}）：{result.error}")
            self._notify(
                "critical",
                "导出失败",
                f"对比图没有保存成功。\n\n原因：{result.error}",
            )
            return
        image_path = result.paths[0]
        self._status.setText(
            f"已导出 {result.image_format} 对比图 · 组 {result.group_id} · {image_path}{note}"
        )
        self._notify(
            "information",
            "导出成功",
            f"对比图已保存：\n{image_path}\n\n（画面左上角文件名、右下角帧号与标注"
            f"已一起导出；组 {result.group_id}）{note}"
            if result.media_kind == "video"
            else f"对比图已保存：\n{image_path}\n\n（文件名、图像尺寸与标注已一起导出）{note}",
        )

    def _add_marker(self) -> None:
        snapshot = self._transport.displayed if self._transport else None
        if snapshot is None or self._current_display_snapshot() is None:
            self._on_error("请先等待完整同步帧组，再添加 Marker")
            return
        marker = self._marker_store.add(
            snapshot,
            self._transport.spec,
            title=self._marker_title.text(),
            note=self._marker_note.text(),
        )
        label = f"{marker.title} · {format_timecode(marker.global_time)}"
        self._marker_list.addItem(f"{label} · 帧 {marker.reference_ordinal + 1}")
        item = self._marker_list.item(self._marker_list.count() - 1)
        item.setData(Qt.ItemDataRole.UserRole, marker.marker_id)
        item.setToolTip(marker.note or "仅本次会话，退出后不会保存")
        self._marker_list.setCurrentItem(item)
        self._marker_title.clear()
        self._marker_note.clear()
        self._status.setText(f"已在完整组 {snapshot.group_id} 添加 Marker（仅本次会话）")

    def _jump_marker(self) -> None:
        item = self._marker_list.currentItem()
        if item is None or self._transport is None:
            self._on_error("请先选中一个 Marker")
            return
        try:
            target = self._marker_store.resolve(
                item.data(Qt.ItemDataRole.UserRole),
                self._transport.spec,
                self._transport.mapper,
            )
            if self._transport.spec.mode is SyncMode.TIME:
                self._transport.seek_time(target.global_time)
            else:
                self._transport.seek_reference_frame(target.reference_ordinal + 1)
        except (KeyError, ValueError, TimelineError) as exc:
            self._on_error(f"无法跳转 Marker：{exc}")

    def _set_loop_start(self) -> None:
        if self._transport is None:
            return
        try:
            start = self._transport.set_loop_start_from_displayed()
        except ValueError as exc:
            self._on_error(str(exc))
            return
        self._loop_button.blockSignals(True)
        self._loop_button.setChecked(False)
        self._loop_button.blockSignals(False)
        self._loop_status.setText(f"循环起点 {start}；请定位终点后按 O")

    def _set_loop_end(self) -> None:
        if self._transport is None:
            return
        try:
            loop = self._transport.set_loop_end_from_displayed()
        except ValueError as exc:
            self._on_error(str(exc))
            return
        self._loop_status.setText(f"循环 [{loop.start}, {loop.end})；点击开启")

    def _toggle_loop(self, enabled: bool) -> None:
        if self._transport is None:
            return
        try:
            self._transport.set_loop_enabled(enabled)
        except ValueError as exc:
            self._loop_button.blockSignals(True)
            self._loop_button.setChecked(False)
            self._loop_button.blockSignals(False)
            self._on_error(str(exc))
            return
        if self._transport.loop_range is not None:
            loop = self._transport.loop_range
            self._loop_status.setText(
                f"循环 [{loop.start}, {loop.end}) {'已开启' if enabled else '已关闭'}"
            )

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        colors = apply_theme(app, self._settings)
        self._canvas.set_theme_colors(colors)

    def _on_system_color_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._settings.theme == "system":
            self._apply_theme()

    def _change_theme(self) -> None:
        """Kept as an alias: appearance is now one combined setting."""
        self._change_appearance()

    def _start_scrub(self) -> None:
        self._scrub_was_playing = bool(
            self._transport
            and self._transport.state in {TransportState.PLAYING, TransportState.BUFFERING}
        )
        if self._transport:
            self._transport.pause()

    def _queue_scrub_preview(self) -> None:
        if self._slider.isSliderDown():
            self._scrub_timer.start()

    def _slider_target(self) -> Fraction | int:
        assert self._transport is not None
        valid = self._transport.mapper.valid_range(self._transport.spec)
        position = Fraction(self._slider.value(), 10000)
        if self._transport.spec.mode is SyncMode.TIME:
            end = self._transport.mapper.last_event(self._transport.spec).global_time
            return Fraction(valid.start) + position * (end - valid.start)
        return int(valid.start) + round(position * (valid.end - valid.start))

    def _preview_scrub(self) -> None:
        if self._transport is None:
            return
        target = self._slider_target()
        try:
            if self._transport.spec.mode is SyncMode.TIME:
                self._transport.seek_time(Fraction(target))
            else:
                self._transport.seek_reference_frame(int(target) + 1)
        except TimelineError as exc:
            self._on_error(str(exc))

    def _finish_scrub(self) -> None:
        self._scrub_timer.stop()
        if self._transport is None:
            return
        target = self._slider_target()
        try:
            if self._transport.spec.mode is SyncMode.TIME:
                self._transport.seek_time(Fraction(target), resume=self._scrub_was_playing)
            else:
                self._transport.seek_reference_frame(
                    int(target) + 1, resume=self._scrub_was_playing
                )
        except TimelineError as exc:
            self._on_error(str(exc))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_O and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._choose_files()
            return
        if isinstance(self.focusWidget(), QLineEdit):
            super().keyPressEvent(event)
            return
        if self.media_kind == "image" and event.key() not in {
            Qt.Key.Key_F,
            Qt.Key.Key_Escape,
        }:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Space:
            self._toggle_play()
        elif event.key() == Qt.Key.Key_Left:
            self._step(-1)
        elif event.key() == Qt.Key.Key_Right:
            self._step(1)
        elif event.key() == Qt.Key.Key_F:
            self._canvas.reset_fit()
        elif event.key() == Qt.Key.Key_I:
            self._set_loop_start()
        elif event.key() == Qt.Key.Key_O:
            self._set_loop_end()
        elif event.key() == Qt.Key.Key_M:
            self._add_marker()
        elif event.key() in {Qt.Key.Key_Home, Qt.Key.Key_End}:
            self._seek_edge(event.key() == Qt.Key.Key_End)
        elif event.key() == Qt.Key.Key_Escape:
            if self._roi_button.isChecked():
                self._roi_button.setChecked(False)
            elif self._maximized_id is not None:
                self._maximized_id = None
                self._refresh_layout()
        else:
            super().keyPressEvent(event)

    def _seek_edge(self, end: bool) -> None:
        if self._transport is None:
            return
        spec = self._transport.spec
        valid = self._transport.mapper.valid_range(spec)
        if valid.empty:
            return
        try:
            if spec.mode is SyncMode.TIME:
                target = (
                    self._transport.mapper.last_event(spec).global_time
                    if end
                    else Fraction(valid.start)
                )
                self._transport.seek_time(target)
            else:
                ordinal = int(valid.end if end else valid.start)
                self._transport.seek_reference_frame(ordinal + 1)
        except TimelineError as exc:
            self._on_error(str(exc))

    def closeEvent(self, event) -> None:
        if self._marker_store.markers and not self._closing_confirmed:
            decision = QMessageBox.question(
                self,
                translate("Marker 未保存"),
                translate("Marker 仅在本次会话有效，退出后不会保留。仍要退出吗？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if decision != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing_confirmed = True
        self._loader_timer.stop()
        self._screenshot_timer.stop()
        QApplication.instance().styleHints().colorSchemeChanged.disconnect(
            self._on_system_color_scheme_changed
        )
        self._loader.request_close()
        self._image_loader.request_close()
        self._screenshot_worker.request_close()
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._loader.join(timeout=5)
        self._image_loader.join(timeout=30)
        self._screenshot_worker.join(timeout=30)
        super().closeEvent(event)
