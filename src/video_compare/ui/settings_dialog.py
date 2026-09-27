"""Theme and language settings."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import (
    QComboBox as NativeQComboBox,
)

from video_compare.services.settings import FOLLOW, AppSettings
from video_compare.ui.color_grid import ColorGrid
from video_compare.ui.i18n import LANGUAGE_OPTIONS, translate
from video_compare.ui.localized_widgets import QComboBox, QLabel, QPushButton
from video_compare.ui.theme import (
    FAMILY_LABELS,
    STANDARD_COLORS,
    resolve_family,
    theme_rows,
)

THEME_CHOICES = (("system", "跟随系统"), ("light", "浅色"), ("dark", "深色"))

# 顺序即界面上角色按钮的顺序；键名同时用于 AppSettings 字段映射。
ROLES: tuple[tuple[str, str], ...] = (
    ("workspace", "工作区"),
    ("function", "功能区"),
    ("accent", "强调色"),
    ("overlay", "视频信息"),
)

ROLE_HINTS = {
    "workspace": "视频窗口的背景、画面框与画布文字底色",
    "function": "工具栏、播放条、侧栏与控件的底色",
    "accent": "选中状态、进度条与画布高亮",
    "overlay": "画面上文件名称与帧信息的文字颜色（默认绿色）",
}


class SettingsDialog(QDialog):
    """Modal shell; every change applies immediately and is stored by the window."""

    appearance_changed = Signal()
    language_changed = Signal(str)

    def __init__(self, parent=None, *, settings: AppSettings) -> None:
        super().__init__(parent)
        self.setWindowTitle(translate("设置"))
        self.setModal(True)
        self.setMinimumWidth(600)
        self._colors = {
            "workspace": settings.workspace_color,
            "function": settings.function_color,
            "accent": settings.accent,
            "overlay": settings.overlay_color,
        }
        self._role = "workspace"
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        self._tabs = QTabWidget(self)
        theme_page = QWidget(self._tabs)
        layout = QVBoxLayout(theme_page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(12)
        self._tabs.addTab(theme_page, translate("主题"))
        language_page = QWidget(self._tabs)
        language_layout = QFormLayout(language_page)
        self._language_combo = NativeQComboBox(language_page)
        for value, self_name in LANGUAGE_OPTIONS:
            self._language_combo.addItem(self_name, value)
        self._language_combo.setCurrentIndex(self._language_combo.findData(settings.language))
        language_layout.addRow(QLabel("界面语言", language_page), self._language_combo)
        self._tabs.addTab(language_page, translate("语言"))
        root.addWidget(self._tabs)
        hint = QLabel(
            "整体色彩决定色系风格；工作区、功能区、强调色和视频信息四种颜色"
            "都用同一套色板选择：上方六行是所选色系的主题色及其由浅到深的深浅"
            "（右侧为原色），最下一行是标准色。",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._theme_combo = self._combo(
            [(value, label) for value, label in THEME_CHOICES], settings.theme
        )
        self._theme_combo.setMinimumWidth(250)
        form.addRow(QLabel("明暗模式", self), self._theme_combo)
        self._scheme_combo = self._combo(
            [(key, label) for key, label in FAMILY_LABELS.items()], settings.scheme
        )
        self._scheme_combo.setMinimumWidth(250)
        self._scheme_combo.setToolTip("整体色彩：色系风格，决定色板的主题颜色")
        form.addRow(QLabel("整体色彩", self), self._scheme_combo)
        layout.addLayout(form)

        role_row = QHBoxLayout()
        role_row.setSpacing(8)
        role_row.addWidget(self._section("颜色设置"))
        self._role_group = QButtonGroup(self)
        self._role_group.setExclusive(True)
        self._role_buttons: dict[str, QPushButton] = {}
        for key, label in ROLES:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setChecked(key == self._role)
            button.setToolTip(ROLE_HINTS[key])
            button.clicked.connect(lambda _checked, role=key: self.select_role(role))
            self._role_group.addButton(button)
            self._role_buttons[key] = button
            role_row.addWidget(button)
        role_row.addStretch(1)
        layout.addLayout(role_row)

        current_row = QHBoxLayout()
        current_row.setSpacing(8)
        self._follow_button = QPushButton("跟随色系", self)
        self._follow_button.setCheckable(True)
        self._follow_button.setToolTip("该颜色使用所选色系的主色")
        current_row.addWidget(self._follow_button)
        self._role_swatch = QLabel(self)
        self._role_swatch.setFixedSize(24, 24)
        current_row.addWidget(self._role_swatch)
        self._role_value = QLabel("", self)
        self._role_value.setObjectName("Hint")
        current_row.addWidget(self._role_value)
        current_row.addStretch(1)
        layout.addLayout(current_row)

        self._grid = ColorGrid(self)
        layout.addWidget(self._grid)
        standard_label = QLabel("标准颜色：点击任意色块即把该颜色用于当前角色", self)
        standard_label.setObjectName("Hint")
        layout.addWidget(standard_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(translate("完成"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self._close_button = buttons.button(QDialogButtonBox.StandardButton.Close)

        self._grid.color_picked.connect(self.pick_color)
        self._follow_button.clicked.connect(lambda: self.pick_color(FOLLOW))
        self._theme_combo.currentIndexChanged.connect(self._on_family_changed)
        self._scheme_combo.currentIndexChanged.connect(self._on_family_changed)
        self._language_combo.currentIndexChanged.connect(
            lambda: self.language_changed.emit(self._language_combo.currentData())
        )
        self._reload_grid()

    # -- helpers -------------------------------------------------------------

    def _section(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("SectionTitle")
        return label

    @staticmethod
    def _combo(choices, current) -> QComboBox:
        combo = QComboBox()
        for value, label in choices:
            combo.addItem(label, value)
        index = next((i for i in range(combo.count()) if combo.itemData(i) == current), 0)
        combo.setCurrentIndex(index)
        return combo

    def _on_family_changed(self) -> None:
        self._reload_grid()
        self.appearance_changed.emit()

    def _reload_grid(self) -> None:
        family = resolve_family(self._scheme_combo.currentData())
        rows = list(theme_rows(family))
        rows.append(())
        rows.append(STANDARD_COLORS)
        self._grid.set_colors(rows)
        self._refresh_role()

    def _refresh_role(self) -> None:
        color = self.resolved_color(self._role)
        self._grid.set_selected(self._colors[self._role])
        self._follow_button.setChecked(self._colors[self._role] == FOLLOW)
        self._role_swatch.setStyleSheet(
            f"background: {color}; border: 1px solid rgba(0,0,0,0.3); border-radius: 4px;"
        )
        label = dict(ROLES)[self._role]
        state = "跟随色系" if self._colors[self._role] == FOLLOW else "自定义"
        if self._language_combo.currentData() != "zh_CN":
            self._role_value.setText(f"{translate(label)}: {translate(state)} {color.upper()}")
        else:
            self._role_value.setText(f"{label}：{state} {color.upper()}")

    # -- state ---------------------------------------------------------------

    def select_role(self, role: str) -> None:
        self._role = role
        self._role_buttons[role].setChecked(True)
        self._refresh_role()

    def pick_color(self, color: str) -> None:
        self._colors[self._role] = color
        self._refresh_role()
        self.appearance_changed.emit()

    def resolved_color(self, role: str) -> str:
        value = self._colors[role]
        if value != FOLLOW:
            return value
        return resolve_family(self._scheme_combo.currentData()).base

    def appearance(self) -> dict[str, str]:
        return {
            "theme": self._theme_combo.currentData(),
            "scheme": self._scheme_combo.currentData(),
            "accent": self._colors["accent"],
            "workspace_color": self._colors["workspace"],
            "function_color": self._colors["function"],
            "overlay_color": self._colors["overlay"],
        }

    def set_color(self, role: str, color: str) -> None:
        """Set one role colour and notify (used by tests and shortcuts)."""
        self._colors[role] = color
        self._refresh_role()
        self.appearance_changed.emit()

    def sync_from(self, settings: AppSettings) -> None:
        self._colors = {
            "workspace": settings.workspace_color,
            "function": settings.function_color,
            "accent": settings.accent,
            "overlay": settings.overlay_color,
        }
        self._theme_combo.setCurrentIndex(self._theme_combo.findData(settings.theme))
        self._scheme_combo.setCurrentIndex(self._scheme_combo.findData(settings.scheme))
        self._language_combo.setCurrentIndex(self._language_combo.findData(settings.language))
        self._reload_grid()

    def retranslate(self) -> None:
        self.setWindowTitle(translate("设置"))
        self._tabs.setTabText(0, translate("主题"))
        self._tabs.setTabText(1, translate("语言"))
        for widget_type in (QLabel, QPushButton, QComboBox):
            for widget in self.findChildren(widget_type):
                widget.retranslate()
        self._close_button.setText(translate("完成"))
        self._refresh_role()

    @property
    def language_combo(self) -> NativeQComboBox:
        return self._language_combo

    @property
    def theme_combo(self) -> QComboBox:
        return self._theme_combo

    @property
    def scheme_combo(self) -> QComboBox:
        return self._scheme_combo

    @property
    def color_grid(self) -> ColorGrid:
        return self._grid

    @property
    def follow_button(self) -> QPushButton:
        return self._follow_button

    @property
    def role(self) -> str:
        return self._role

    def role_button(self, role: str) -> QPushButton:
        return self._role_buttons[role]

    def color_of(self, role: str) -> str:
        return self._colors[role]

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
