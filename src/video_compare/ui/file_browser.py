"""Read-only local folder navigation for adding images and videos to a workspace."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from video_compare.media.formats import IMAGE_SUFFIXES, VIDEO_SUFFIXES
from video_compare.ui.i18n import translate
from video_compare.ui.localized_widgets import QLabel, QLineEdit, QPushButton


class FileBrowser(QWidget):
    """Navigate folders without renaming, moving, or removing source media."""

    file_activated = Signal(str)
    directory_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FileBrowser")
        self._current_directory: Path | None = None
        self._history: list[Path] = []
        self._history_index = -1
        self._suffixes = frozenset(IMAGE_SUFFIXES + VIDEO_SUFFIXES)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.choose_button = QPushButton("选择工作文件夹", self)
        self.choose_button.setToolTip("选择文件夹后，双击图像或视频添加到当前工作区")
        self.choose_button.clicked.connect(self.choose_directory)
        layout.addWidget(self.choose_button)

        navigation = QHBoxLayout()
        navigation.setSpacing(4)
        self.back_button = QPushButton("←", self)
        self.back_button.setToolTip("后退到上次浏览的文件夹")
        self.back_button.clicked.connect(self.go_back)
        self.forward_button = QPushButton("→", self)
        self.forward_button.setToolTip("前进到下次浏览的文件夹")
        self.forward_button.clicked.connect(self.go_forward)
        self.up_button = QPushButton("↑", self)
        self.up_button.setToolTip("上一级文件夹")
        self.up_button.clicked.connect(self.go_up)
        self.refresh_button = QPushButton("刷新", self)
        self.refresh_button.setToolTip("重新读取当前文件夹")
        self.refresh_button.clicked.connect(self.refresh)
        for button in (
            self.back_button,
            self.forward_button,
            self.up_button,
            self.refresh_button,
        ):
            navigation.addWidget(button)
        layout.addLayout(navigation)

        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("文件夹路径，回车进入")
        self.path_edit.setToolTip("当前文件夹路径；可输入其他路径后按回车")
        self.path_edit.returnPressed.connect(self._enter_path)
        layout.addWidget(self.path_edit)

        self.tree = QTreeView(self)
        self.view = self.tree
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setDragEnabled(False)
        self.tree.setAcceptDrops(False)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tree.doubleClicked.connect(self._activate_index)
        self.model = self._new_model()
        layout.addWidget(self.tree, 1)

        self.status_label = QLabel("选择工作文件夹，浏览图像和视频", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._update_navigation()

    @property
    def current_directory(self) -> Path | None:
        return self._current_directory

    def _new_model(self) -> QFileSystemModel:
        model = QFileSystemModel(self)
        model.setReadOnly(True)
        model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        model.setNameFilters([f"*.{suffix}" for suffix in sorted(self._suffixes)])
        model.setNameFilterDisables(False)
        self.tree.setModel(model)
        for column in range(1, model.columnCount()):
            self.tree.hideColumn(column)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        return model

    def choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            translate("选择工作文件夹"),
            str(self._current_directory or Path.home()),
        )
        if directory:
            self.set_directory(Path(directory))

    def set_directory(self, path: Path) -> bool:
        return self._navigate_to(path, record_history=True)

    def _navigate_to(self, path: Path, *, record_history: bool) -> bool:
        directory = Path(path).expanduser()
        if not directory.is_absolute() and self._current_directory is not None:
            directory = self._current_directory / directory
        try:
            directory = directory.resolve(strict=True)
            if not stat.S_ISDIR(directory.stat().st_mode):
                raise NotADirectoryError(f"不是文件夹：{directory}")
            # Validate read access before changing the root or navigation history.
            with os.scandir(directory) as entries:
                next(entries, None)
        except (OSError, ValueError, RuntimeError) as exc:
            self._show_error(f"无法打开文件夹 {directory}：{exc}")
            return False

        if record_history and directory != self._current_directory:
            del self._history[self._history_index + 1 :]
            self._history.append(directory)
            self._history_index = len(self._history) - 1
        self._current_directory = directory
        self.tree.setRootIndex(self.model.setRootPath(str(directory)))
        self.path_edit.setText(str(directory))
        self.path_edit.setToolTip(str(directory))
        self.status_label.setText("双击图像/视频添加到工作区；双击文件夹进入")
        self.status_label.setToolTip("")
        self._update_navigation()
        self.directory_changed.emit(str(directory))
        return True

    def go_back(self) -> None:
        if self._history_index > 0:
            target = self._history_index - 1
            if self._navigate_to(self._history[target], record_history=False):
                self._history_index = target
                self._update_navigation()

    def go_forward(self) -> None:
        if self._history_index + 1 < len(self._history):
            target = self._history_index + 1
            if self._navigate_to(self._history[target], record_history=False):
                self._history_index = target
                self._update_navigation()

    def go_up(self) -> None:
        directory = self._current_directory
        if directory is not None and directory.parent != directory:
            self.set_directory(directory.parent)

    def refresh(self) -> None:
        directory = self._current_directory
        if directory is None:
            return
        if not self.set_directory(directory):
            return
        # A fresh model also refreshes shares whose filesystem notifications were lost.
        old_model = self.model
        self.model = self._new_model()
        self.tree.setRootIndex(self.model.setRootPath(str(directory)))
        old_model.deleteLater()

    def _enter_path(self) -> None:
        text = self.path_edit.text().strip()
        if text:
            self.set_directory(Path(text))
        else:
            self._show_error("请输入文件夹路径")

    def _activate_index(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        path = Path(self.model.filePath(index))
        if self.model.isDir(index):
            self.set_directory(path)
        elif path.suffix.lower().lstrip(".") in self._suffixes:
            if path.is_file():
                self.file_activated.emit(str(path))
            else:
                self._show_error(f"文件已不存在：{path}")

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(message)
        self.error_occurred.emit(message)

    def _update_navigation(self) -> None:
        directory = self._current_directory
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(self._history_index + 1 < len(self._history))
        self.up_button.setEnabled(directory is not None and directory.parent != directory)
        self.refresh_button.setEnabled(directory is not None)

    def retranslate(self) -> None:
        for widget_type in (QLabel, QPushButton, QLineEdit):
            for widget in self.findChildren(widget_type):
                widget.retranslate()
