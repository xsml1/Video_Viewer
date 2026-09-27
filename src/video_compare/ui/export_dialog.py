"""Options for exporting the visible part of the compare view."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from video_compare.services.comparison_export import normalize_format
from video_compare.ui.i18n import translate
from video_compare.ui.localized_widgets import QCheckBox, QComboBox, QLabel

EXPORT_LAYOUTS: tuple[tuple[str, str], ...] = (
    ("window", "与窗口一致"),
    ("horizontal", "横向排列"),
    ("vertical", "竖向排列"),
    ("grid", "网格排列"),
)

EXPORT_FORMATS: tuple[tuple[str, str, str], ...] = (
    ("PNG", "PNG（无损，推荐）", ".png"),
    ("JPEG", "JPEG/JPG（可调质量）", ".jpg"),
)


@dataclass(frozen=True, slots=True)
class ExportOptions:
    layout: str
    image_format: str
    quality: int
    edit_first: bool = False


def format_suffix(image_format: str) -> str:
    for name, _label, suffix in EXPORT_FORMATS:
        if name == image_format.upper():
            return suffix
    return ".png"


def format_filter(image_format: str) -> str:
    name = normalize_format(image_format)
    if name == "JPEG":
        return "JPEG 图片 (*.jpg *.jpeg)"
    return "PNG 图片 (*.png)"


class ExportOptionsDialog(QDialog):
    """Ask how the comparison image should be arranged and encoded."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(translate("导出对比图"))
        self.setModal(True)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        hint = QLabel(
            "导出当前窗口里看到的画面区域（缩放的对比结果）：包含画面左上角的"
            "文件名、右下角的帧号信息与标注，不包含按钮、工具栏等界面元素；"
            "不再生成 JSON 文件。",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        layout.addWidget(hint)
        form = QFormLayout()
        form.setSpacing(10)
        self._layout_combo = QComboBox(self)
        for value, label in EXPORT_LAYOUTS:
            self._layout_combo.addItem(label, value)
        form.addRow(QLabel("排列方式", self), self._layout_combo)
        self._format_combo = QComboBox(self)
        for value, label, _suffix in EXPORT_FORMATS:
            self._format_combo.addItem(label, value)
        self._format_combo.currentIndexChanged.connect(self._refresh_quality_state)
        form.addRow(QLabel("图片格式", self), self._format_combo)
        self._quality = QSpinBox(self)
        self._quality.setRange(60, 100)
        self._quality.setValue(95)
        self._quality.setToolTip(translate("JPEG 质量，数值越高文件越大"))
        self._quality_label = QLabel("JPEG 质量", self)
        form.addRow(self._quality_label, self._quality)
        self._edit_check = QCheckBox("导出前先编辑标注（可选多画面联动）", self)
        self._edit_check.setToolTip("勾选后先在画面上框选或画箭头，点“完成并导出”才写文件")
        form.addRow(self._edit_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(translate("选择保存位置…"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(translate("取消"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_quality_state()

    def _refresh_quality_state(self) -> None:
        is_jpeg = normalize_format(self._format_combo.currentData()) == "JPEG"
        self._quality.setEnabled(is_jpeg)
        self._quality_label.setEnabled(is_jpeg)

    def options(self) -> ExportOptions:
        return ExportOptions(
            layout=self._layout_combo.currentData(),
            image_format=self._format_combo.currentData(),
            quality=int(self._quality.value()),
            edit_first=self._edit_check.isChecked(),
        )

    @property
    def edit_check(self) -> QCheckBox:
        return self._edit_check
