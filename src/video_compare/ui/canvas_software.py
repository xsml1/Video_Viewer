from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from video_compare.domain.models import AssetInfo, FrameGroupSnapshot
from video_compare.ui.canvas_common import paint_group
from video_compare.ui.canvas_interaction import CanvasInteractionMixin
from video_compare.ui.theme import CanvasColors


class SoftwareCompareCanvas(CanvasInteractionMixin, QWidget):
    """QPainter fallback with the same atomic snapshot interface."""

    view_changed = Signal(object)
    annotations_changed = Signal(object)
    panel_double_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._order: tuple[str, ...] = ()
        self._assets: Mapping[str, AssetInfo] = {}
        self._snapshot: FrameGroupSnapshot | None = None
        self._colors = CanvasColors()
        self._init_view()

    def set_theme_colors(self, colors: CanvasColors) -> None:
        self._colors = colors
        self.update()

    def set_layout(
        self, ordered_asset_ids: tuple[str, ...], assets: Mapping[str, AssetInfo]
    ) -> None:
        if set(assets) != set(self._assets):
            self._snapshot = None
        self._order = ordered_asset_ids
        self._assets = dict(assets)
        self._reconcile_view()
        self.update()

    def clear_group(self) -> None:
        self._snapshot = None
        self.update()

    def submit_group(self, snapshot: FrameGroupSnapshot) -> None:
        self._snapshot = snapshot
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        try:
            paint_group(
                painter,
                self.width(),
                self.height(),
                self._order,
                self._assets,
                self._snapshot,
                self._regions,
                self._roi_preview,
                self._colors,
                self.pixel_zoom,
                self.devicePixelRatioF(),
                None,
                self._layout_mode,
                self._overlay_visible,
                self.annotations,
                self._annotation_preview,
            )
        finally:
            painter.end()
