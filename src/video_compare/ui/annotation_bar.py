"""Toolbar for editing annotations before exporting the comparison image."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
)

from video_compare.ui.annotations import ANNOTATION_COLORS, SHAPES, Annotation
from video_compare.ui.localized_widgets import QCheckBox, QComboBox, QLabel, QPushButton


class AnnotationBar(QFrame):
    """Shape/colour pickers plus undo, clear, finish and cancel actions."""

    undo_requested = Signal()
    clear_requested = Signal()
    delete_requested = Signal(int)
    finished = Signal()
    cancelled = Signal()
    shape_changed = Signal(str)
    color_changed = Signal(str)
    link_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        choices = QHBoxLayout()
        choices.setSpacing(8)
        layout.addLayout(choices)
        hint = QLabel("标注缩放后仍跟随源位置", self)
        hint.setObjectName("Hint")
        choices.addWidget(hint)
        self._shape_combo = QComboBox(self)
        for value, label in SHAPES:
            self._shape_combo.addItem(label, value)
        self._shape_combo.currentIndexChanged.connect(
            lambda: self.shape_changed.emit(self._shape_combo.currentData())
        )
        choices.addWidget(self._shape_combo)
        self._color_combo = QComboBox(self)
        for value, label in ANNOTATION_COLORS:
            self._color_combo.addItem(f"● {label}", value)
            self._color_combo.setItemData(
                self._color_combo.count() - 1,
                f"线条颜色 {label} {value.upper()}",
                3,
            )
        self._color_combo.currentIndexChanged.connect(
            lambda: self.color_changed.emit(self._color_combo.currentData())
        )
        choices.addWidget(self._color_combo)
        self._annotation_select = QComboBox(self)
        self._annotation_select.setToolTip("选择要删除的标注")
        self._annotation_select.setMinimumWidth(115)
        choices.addWidget(self._annotation_select)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._link_checkbox = QCheckBox("标注联动到全部画面", self)
        self._link_checkbox.setChecked(True)
        self._link_checkbox.setToolTip(
            "关闭后，新画的矩形和自由画笔等标注只作用于起笔所在画面；已画标注保持原范围"
        )
        self._link_checkbox.toggled.connect(self.link_changed)
        actions.addWidget(self._link_checkbox)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._undo_button = QPushButton("撤销上一笔", self)
        self._undo_button.clicked.connect(self.undo_requested)
        actions.addWidget(self._undo_button)
        self._delete_button = QPushButton("删除选中", self)
        self._delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self._annotation_select.currentIndex())
        )
        actions.addWidget(self._delete_button)
        self._clear_button = QPushButton("删除全部", self)
        self._clear_button.clicked.connect(self.clear_requested)
        actions.addWidget(self._clear_button)
        self._cancel_button = QPushButton("取消", self)
        self._cancel_button.clicked.connect(self.cancelled)
        actions.addWidget(self._cancel_button)
        self._done_button = QPushButton("完成并导出", self)
        self._done_button.setObjectName("Primary")
        self._done_button.clicked.connect(self.finished)
        actions.addWidget(self._done_button)
        self.set_annotations(())

    def set_annotations(self, annotations: tuple[Annotation, ...]) -> None:
        labels = dict(SHAPES)
        self._annotation_select.clear()
        for index, annotation in enumerate(annotations, start=1):
            scope = "全部画面" if annotation.target_asset_id is None else "仅起笔画面"
            self._annotation_select.addItem(f"第 {index} 笔 · {labels[annotation.kind]} · {scope}")
        self._annotation_select.setEnabled(bool(annotations))
        self._delete_button.setEnabled(bool(annotations))
        self._undo_button.setEnabled(bool(annotations))
        self._clear_button.setEnabled(bool(annotations))
        if annotations:
            self._annotation_select.setCurrentIndex(len(annotations) - 1)

    def shape(self) -> str:
        return self._shape_combo.currentData()

    def color(self) -> str:
        return self._color_combo.currentData()

    def set_shape(self, kind: str) -> None:
        index = self._shape_combo.findData(kind)
        if index >= 0:
            self._shape_combo.setCurrentIndex(index)

    def set_color(self, color: str) -> None:
        index = self._color_combo.findData(color)
        if index >= 0:
            self._color_combo.setCurrentIndex(index)

    @property
    def done_button(self) -> QPushButton:
        return self._done_button

    @property
    def undo_button(self) -> QPushButton:
        return self._undo_button

    @property
    def clear_button(self) -> QPushButton:
        return self._clear_button

    @property
    def delete_button(self) -> QPushButton:
        return self._delete_button

    @property
    def annotation_select(self) -> QComboBox:
        return self._annotation_select

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel_button

    @property
    def link_checkbox(self) -> QCheckBox:
        return self._link_checkbox

    def retranslate(self, annotations: tuple[Annotation, ...]) -> None:
        for widget_type in (QLabel, QPushButton, QCheckBox, QComboBox):
            for widget in self.findChildren(widget_type):
                widget.retranslate()
        self.set_annotations(annotations)
