"""Office-like colour picker: theme colours with shade rows plus standard colours."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QToolButton, QWidget

SWATCH_SIZE = 22


class ColorGrid(QWidget):
    """Grid of colour swatches; clicking one emits the chosen ``#rrggbb`` value."""

    color_picked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        self._group.buttonClicked.connect(self._on_clicked)

    def set_colors(self, rows: Sequence[Sequence[str]]) -> None:
        """Rebuild the grid; an empty row inserts a small vertical gap."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._buttons.clear()
        for button in self._group.buttons():
            self._group.removeButton(button)
        grid_row = 0
        for row in rows:
            if not row:
                spacer = QWidget(self)
                spacer.setFixedHeight(6)
                self._layout.addWidget(spacer, grid_row, 0)
                grid_row += 1
                continue
            for column, color in enumerate(row):
                button = QToolButton(self)
                button.setObjectName("Swatch")
                button.setCheckable(True)
                button.setFixedSize(QSize(SWATCH_SIZE, SWATCH_SIZE))
                button.setToolTip(color.upper())
                button.setStyleSheet(f"background: {color};")
                self._group.addButton(button)
                self._layout.addWidget(button, grid_row, column)
                self._buttons.setdefault(color.lower(), button)
            grid_row += 1

    def set_selected(self, color: str) -> None:
        button = self._buttons.get(color.lower())
        if button is not None:
            button.setChecked(True)
        else:
            for item in self._group.buttons():
                item.setChecked(False)

    def _on_clicked(self, button: QToolButton) -> None:
        self.color_picked.emit(button.toolTip().lower())

    def swatch_count(self) -> int:
        return len(self._group.buttons())
