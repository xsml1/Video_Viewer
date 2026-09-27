from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainterPath, QRegion

from video_compare.domain.viewport import Rect, ViewRegion
from video_compare.ui.annotations import SHAPES, Annotation, clamp_point
from video_compare.ui.canvas_common import hit_content, pane_at, pane_transform


class CanvasInteractionMixin:
    """Shared pointer handling for GL and software canvas implementations."""

    def _init_view(self) -> None:
        self._regions: dict[str, ViewRegion] = {}
        self._area_regions: dict[str, ViewRegion] = {}
        self._pixel_regions: dict[str, ViewRegion] = {}
        self._pixel_mode = False
        self._pixel_zoom = 1.0
        self._layout_mode: str = "auto"
        self._overlay_visible = True
        self._annotations: list[Annotation] = []
        self._annotating = False
        self._annotation_shape = SHAPES[0][0]
        self._annotation_color = "#ff3b30"
        self._annotation_linked = True
        self._annotation_start: tuple[float, float] | None = None
        self._annotation_asset_id: str | None = None
        self._annotation_points: list[tuple[float, float]] = []
        self._annotation_preview: Annotation | None = None
        self._linked = True
        self._roi_mode = False
        self._drag_asset: str | None = None
        self._last_pos: tuple[float, float] | None = None
        self._roi_start: tuple[float, float] | None = None
        self._roi_preview: Rect | None = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
        self.setMask(QRegion(outline.toFillPolygon().toPolygon()))

    def _reconcile_view(self) -> None:
        current = next(iter(self._regions.values()), ViewRegion())
        self._regions = {
            asset_id: self._regions.get(asset_id, current if self._linked else ViewRegion())
            for asset_id in self._assets
        }

    @property
    def view_regions(self) -> dict[str, ViewRegion]:
        return dict(self._regions)

    @property
    def display_order(self) -> tuple[str, ...]:
        return self._order

    @property
    def layout_mode(self) -> str:
        return self._layout_mode

    @property
    def overlay_visible(self) -> bool:
        return self._overlay_visible

    def set_overlay_visible(self, visible: bool) -> None:
        """Toggle the name/frame overlays (used by pixel-exact verification)."""
        if visible == self._overlay_visible:
            return
        self._overlay_visible = visible
        self.update()

    # -- annotation mode -----------------------------------------------------

    @property
    def annotations(self) -> tuple[Annotation, ...]:
        return tuple(self._annotations)

    @property
    def annotating(self) -> bool:
        return self._annotating

    def set_annotating(self, enabled: bool) -> None:
        self._annotating = enabled
        self._annotation_start = None
        self._annotation_asset_id = None
        self._annotation_points.clear()
        self._annotation_preview = None
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_annotation_shape(self, kind: str) -> None:
        self._annotation_shape = kind

    def set_annotation_color(self, color: str) -> None:
        self._annotation_color = color

    def set_annotation_linked(self, linked: bool) -> None:
        """Choose the scope of new strokes; existing strokes keep their scope."""
        self._annotation_linked = linked

    def undo_annotation(self) -> bool:
        if not self._annotations:
            return False
        self._annotations.pop()
        self.annotations_changed.emit(self.annotations)
        self.update()
        return True

    def delete_annotation(self, index: int) -> bool:
        if not 0 <= index < len(self._annotations):
            return False
        del self._annotations[index]
        self.annotations_changed.emit(self.annotations)
        self.update()
        return True

    def clear_annotations(self) -> None:
        if not self._annotations:
            return
        self._annotations.clear()
        self.annotations_changed.emit(self.annotations)
        self.update()

    def set_layout_mode(self, mode: str) -> None:
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        self.view_changed.emit(self.view_regions)
        self.update()

    def set_view_state(self, regions: dict[str, ViewRegion], linked: bool) -> None:
        self._regions = dict(regions)
        self._linked = linked
        self._reconcile_view()
        self.update()

    @property
    def pixel_zoom(self) -> float | None:
        return self._pixel_zoom if self._pixel_mode else None

    def set_pixel_mode(self, enabled: bool) -> None:
        if enabled == self._pixel_mode:
            return
        previous = self._regions
        if enabled:
            self._area_regions = dict(previous)
            saved = self._pixel_regions
        else:
            self._pixel_regions = dict(previous)
            saved = self._area_regions
        self._regions = {
            asset_id: ViewRegion(
                previous.get(asset_id, ViewRegion()).center_u,
                previous.get(asset_id, ViewRegion()).center_v,
                saved.get(asset_id, ViewRegion()).width_u,
                saved.get(asset_id, ViewRegion()).height_v,
            )
            for asset_id in self._assets
        }
        self._pixel_mode = enabled
        self.view_changed.emit(self.view_regions)
        self.update()

    def set_linked(self, linked: bool, source_asset_id: str | None = None) -> None:
        if linked and self._assets:
            source = source_asset_id if source_asset_id in self._assets else self._order[0]
            region = self._regions.get(source, ViewRegion())
            self._regions = dict.fromkeys(self._assets, region)
        self._linked = linked
        self.update()

    def set_roi_mode(self, enabled: bool) -> None:
        self._roi_mode = enabled
        self._roi_start = None
        self._roi_preview = None
        self.update()

    def reset_fit(self) -> None:
        if self._pixel_mode:
            self._pixel_zoom = 1.0
        self._regions = dict.fromkeys(self._assets, ViewRegion())
        self.view_changed.emit(self.view_regions)
        self.update()

    def _set_region(self, asset_id: str, region: ViewRegion) -> None:
        if self._linked:
            self._regions = dict.fromkeys(self._assets, region)
        else:
            self._regions[asset_id] = region
        self.view_changed.emit(self.view_regions)
        self.update()

    def _hit(self, x: float, y: float):
        return hit_content(
            self.width(),
            self.height(),
            self._order,
            self._assets,
            self._snapshot,
            self._regions,
            x,
            y,
            pixel_zoom=self.pixel_zoom,
            device_pixel_ratio=self.devicePixelRatioF(),
            layout=self._layout_mode,
        )

    def _begin_annotation(self, x: float, y: float) -> bool:
        hit = self._hit(x, y)
        if hit is None:
            return False
        self._annotation_asset_id = hit[0]
        position = clamp_point(hit[1].inverse(x, y))
        self._annotation_start = position
        self._annotation_points = [position]
        self._annotation_preview = Annotation(
            self._annotation_shape,
            position,
            position,
            self._annotation_color,
            (position,) if self._annotation_shape == "pen" else (),
            None if self._annotation_linked else hit[0],
        )
        self.update()
        return True

    def _update_annotation(self, x: float, y: float) -> None:
        assert self._annotation_start is not None
        assert self._annotation_asset_id is not None
        transform = pane_transform(
            self.width(),
            self.height(),
            self._order,
            self._assets,
            self._snapshot,
            self._regions,
            self._annotation_asset_id,
            pixel_zoom=self.pixel_zoom,
            device_pixel_ratio=self.devicePixelRatioF(),
            layout=self._layout_mode,
        )
        if transform is None:
            return
        content = transform.content_rect
        point_x = min(content.right, max(content.x, x))
        point_y = min(content.bottom, max(content.y, y))
        position = clamp_point(transform.inverse(point_x, point_y, require_content=False))
        if self._annotation_shape == "pen" and position != self._annotation_points[-1]:
            self._annotation_points.append(position)
        self._annotation_preview = Annotation(
            self._annotation_shape,
            self._annotation_start,
            position,
            self._annotation_color,
            tuple(self._annotation_points) if self._annotation_shape == "pen" else (),
            self._annotation_preview.target_asset_id,
        )
        self.update()

    def _finish_annotation(self, x: float, y: float) -> None:
        assert self._annotation_start is not None
        self._update_annotation(x, y)
        preview = self._annotation_preview
        self._annotation_start = None
        self._annotation_asset_id = None
        self._annotation_points.clear()
        self._annotation_preview = None
        if preview is None:
            return
        start, end = preview.start, preview.end
        if preview.kind == "pen":
            if len(preview.points) < 2:
                self.update()
                return
        elif abs(start[0] - end[0]) < 0.004 and abs(start[1] - end[1]) < 0.004:
            self.update()
            return
        self._annotations.append(preview)
        self.annotations_changed.emit(self.annotations)
        self.update()

    def wheelEvent(self, event) -> None:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            event.ignore()
            return
        point = event.position()
        hit = self._hit(point.x(), point.y())
        if hit is None:
            event.ignore()
            return
        asset_id, transform = hit
        anchor = transform.inverse(point.x(), point.y())
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if self._pixel_mode:
            self._pixel_zoom = min(16.0, max(0.25, self._pixel_zoom * factor))
            scale = self._pixel_zoom / self.devicePixelRatioF()
            center_u = anchor[0] - (point.x() - transform.panel.x - transform.panel.width / 2) / (
                scale * transform.display_width
            )
            center_v = anchor[1] - (point.y() - transform.panel.y - transform.panel.height / 2) / (
                scale * transform.display_height
            )
            current = self._regions.get(asset_id, ViewRegion())
            self._set_region(
                asset_id,
                ViewRegion(center_u, center_v, current.width_u, current.height_v),
            )
        else:
            self._set_region(asset_id, transform.region.zoom_at(*anchor, factor))
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        point = event.position()
        if self._annotating:
            if self._begin_annotation(point.x(), point.y()):
                event.accept()
            else:
                event.ignore()
            return
        hit = self._hit(point.x(), point.y())
        if hit is None:
            event.ignore()
            return
        self._drag_asset = hit[0]
        self._last_pos = (point.x(), point.y())
        if self._roi_mode:
            self._roi_start = self._last_pos
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._order:
            event.ignore()
            return
        asset_id = pane_at(
            self.width(),
            self.height(),
            self._order,
            self._assets,
            self._snapshot,
            self._regions,
            event.position().x(),
            event.position().y(),
            layout=self._layout_mode,
        )
        if asset_id is not None:
            self.panel_double_clicked.emit(asset_id)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event) -> None:
        if self._annotating and self._annotation_start is not None:
            self._update_annotation(event.position().x(), event.position().y())
            event.accept()
            return
        if self._drag_asset is None or self._last_pos is None:
            event.ignore()
            return
        point = event.position()
        x, y = point.x(), point.y()
        if self._roi_start is not None:
            start_x, start_y = self._roi_start
            self._roi_preview = Rect(
                min(start_x, x), min(start_y, y), abs(x - start_x), abs(y - start_y)
            )
            self.update()
        else:
            transform = pane_transform(
                self.width(),
                self.height(),
                self._order,
                self._assets,
                self._snapshot,
                self._regions,
                self._drag_asset,
                pixel_zoom=self.pixel_zoom,
                device_pixel_ratio=self.devicePixelRatioF(),
                layout=self._layout_mode,
            )
            if transform is not None:
                dx, dy = x - self._last_pos[0], y - self._last_pos[1]
                self._set_region(self._drag_asset, transform.pan(dx, dy))
        self._last_pos = (x, y)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._annotating and self._annotation_start is not None:
            self._finish_annotation(event.position().x(), event.position().y())
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._drag_asset is None:
            event.ignore()
            return
        if self._roi_start is not None:
            point = event.position()
            start_x, start_y = self._roi_start
            rect = Rect(
                min(start_x, point.x()),
                min(start_y, point.y()),
                abs(point.x() - start_x),
                abs(point.y() - start_y),
            )
            transform = pane_transform(
                self.width(),
                self.height(),
                self._order,
                self._assets,
                self._snapshot,
                self._regions,
                self._drag_asset,
                pixel_zoom=self.pixel_zoom,
                device_pixel_ratio=self.devicePixelRatioF(),
                layout=self._layout_mode,
            )
            if transform is not None:
                try:
                    selected = transform.roi_from_screen(rect)
                    if self._pixel_mode:
                        self._pixel_zoom = min(
                            16.0,
                            max(
                                0.25,
                                self.devicePixelRatioF()
                                * min(
                                    transform.panel.width
                                    / (selected.width_u * transform.display_width),
                                    transform.panel.height
                                    / (selected.height_v * transform.display_height),
                                ),
                            ),
                        )
                    self._set_region(self._drag_asset, selected)
                except ValueError:
                    self._roi_preview = None
        self._drag_asset = None
        self._last_pos = None
        self._roi_start = None
        self._roi_preview = None
        self.update()
        event.accept()
