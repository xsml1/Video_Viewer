"""Qt text widgets that retain their source text for live language changes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox as _QCheckBox
from PySide6.QtWidgets import QComboBox as _QComboBox
from PySide6.QtWidgets import QLabel as _QLabel
from PySide6.QtWidgets import QLineEdit as _QLineEdit
from PySide6.QtWidgets import QPushButton as _QPushButton
from PySide6.QtWidgets import QSizePolicy

from video_compare.ui.i18n import translate

_SOURCE_ROLE = Qt.ItemDataRole.UserRole + 100
_SOURCE_TOOLTIP_ROLE = Qt.ItemDataRole.UserRole + 101


class _TextMixin:
    def _init_translation(self) -> None:
        self._source_text = super().text()
        self._source_tooltip = super().toolTip()
        super().setText(translate(self._source_text))

    def setText(self, text: str) -> None:
        self._source_text = text
        super().setText(translate(text))

    def setToolTip(self, text: str) -> None:
        self._source_tooltip = text
        super().setToolTip(translate(text))

    def retranslate(self) -> None:
        super().setText(translate(self._source_text))
        super().setToolTip(translate(self._source_tooltip))


class QLabel(_TextMixin, _QLabel):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_translation()


class StatusLabel(QLabel):
    """Keep asynchronous messages from resizing the canvas during a gesture."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(self._source_text)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text)


class QPushButton(_TextMixin, _QPushButton):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_translation()


class QCheckBox(_TextMixin, _QCheckBox):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_translation()


class QLineEdit(_QLineEdit):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._source_tooltip = super().toolTip()
        self._source_placeholder = super().placeholderText()
        super().setPlaceholderText(translate(self._source_placeholder))

    def setToolTip(self, text: str) -> None:
        self._source_tooltip = text
        super().setToolTip(translate(text))

    def setPlaceholderText(self, text: str) -> None:
        self._source_placeholder = text
        super().setPlaceholderText(translate(text))

    def retranslate(self) -> None:
        super().setToolTip(translate(self._source_tooltip))
        super().setPlaceholderText(translate(self._source_placeholder))


class QComboBox(_QComboBox):
    def addItem(self, text: str, userData=None) -> None:
        super().addItem(translate(text), userData)
        self.setItemData(self.count() - 1, text, _SOURCE_ROLE)

    def setItemText(self, index: int, text: str) -> None:
        self.setItemData(index, text, _SOURCE_ROLE)
        super().setItemText(index, translate(text))

    def setItemData(self, index: int, value, role=Qt.ItemDataRole.UserRole) -> None:
        if role == Qt.ItemDataRole.ToolTipRole and isinstance(value, str):
            super().setItemData(index, value, _SOURCE_TOOLTIP_ROLE)
            value = translate(value)
        super().setItemData(index, value, role)

    def setToolTip(self, text: str) -> None:
        self._source_tooltip = text
        super().setToolTip(translate(text))

    def retranslate(self) -> None:
        for index in range(self.count()):
            source = self.itemData(index, _SOURCE_ROLE)
            if source is not None:
                super().setItemText(index, translate(source))
            tooltip = self.itemData(index, _SOURCE_TOOLTIP_ROLE)
            if tooltip is not None:
                super().setItemData(index, translate(tooltip), Qt.ItemDataRole.ToolTipRole)
        super().setToolTip(translate(getattr(self, "_source_tooltip", "")))
