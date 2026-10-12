from __future__ import annotations

from collections.abc import Mapping

import shiboken6
from PySide6.QtCore import QRect, QRectF, QSize, Signal
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtOpenGL import QOpenGLTexture, QOpenGLTextureBlitter
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from video_compare.domain.models import (
    AssetInfo,
    DecodedFrame,
    DisplayTransform,
    FrameGroupSnapshot,
)
from video_compare.ui.canvas_common import paint_group
from video_compare.ui.canvas_interaction import CanvasInteractionMixin
from video_compare.ui.theme import CanvasColors


class CompareCanvas(CanvasInteractionMixin, QOpenGLWidget):
    """One GL canvas; unchanged source frames keep their front texture on view changes."""

    view_changed = Signal(object)
    annotations_changed = Signal(object)
    panel_double_clicked = Signal(str)
    panel_selected = Signal(str)
    panel_swap_requested = Signal(str, str)
    render_failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._order: tuple[str, ...] = ()
        self._assets: Mapping[str, AssetInfo] = {}
        self._snapshot: FrameGroupSnapshot | None = None
        self._pending_snapshot: FrameGroupSnapshot | None = None
        self._colors = CanvasColors()
        self._textures: dict[str, list[QOpenGLTexture | None]] = {}
        self._front_slots: dict[str, int] = {}
        self._front_frames: dict[str, DecodedFrame] = {}
        self._blitter: QOpenGLTextureBlitter | None = None
        self._render_error: str | None = None
        self._init_view()

    def initializeGL(self) -> None:
        self.context().aboutToBeDestroyed.connect(self._release_gl)
        self._blitter = QOpenGLTextureBlitter()
        if not self._blitter.create():
            self._render_error = "OpenGL 纹理绘制器初始化失败"
            self.render_failed.emit(self._render_error)

    def _release_gl(self) -> None:
        if self.context() is None:
            return
        self.makeCurrent()
        for pair in self._textures.values():
            for texture in pair:
                if texture is not None:
                    texture.destroy()
        self._textures.clear()
        self._front_slots.clear()
        self._front_frames.clear()
        if self._blitter is not None:
            self._blitter.destroy()
            self._blitter = None
        self._pending_snapshot = self._snapshot
        self._snapshot = None
        self.doneCurrent()

    def _discard_removed_textures(self) -> None:
        for asset_id in tuple(self._textures):
            if asset_id in self._assets:
                continue
            for texture in self._textures.pop(asset_id):
                if texture is not None:
                    texture.destroy()
            self._front_slots.pop(asset_id, None)
            self._front_frames.pop(asset_id, None)

    def set_theme_colors(self, colors: CanvasColors) -> None:
        self._colors = colors
        self.update()

    def set_layout(
        self, ordered_asset_ids: tuple[str, ...], assets: Mapping[str, AssetInfo]
    ) -> None:
        if ordered_asset_ids != self._order or set(assets) != set(self._assets):
            self.cancel_interaction()
        if set(assets) != set(self._assets):
            self._snapshot = None
            self._pending_snapshot = None
        self._order = ordered_asset_ids
        self._assets = dict(assets)
        self._reconcile_view()
        self.update()

    def clear_group(self) -> None:
        self.cancel_interaction()
        self._snapshot = None
        self._pending_snapshot = None
        self.update()

    def submit_group(self, snapshot: FrameGroupSnapshot) -> None:
        # A group becomes visible only after every changed route uploads successfully.
        self._pending_snapshot = snapshot
        self.update()

    @staticmethod
    def _image_for_upload(frame: DecodedFrame, transform: DisplayTransform) -> QImage:
        pixels = frame.rgb
        image = QImage(
            pixels.data,
            pixels.shape[1],
            pixels.shape[0],
            pixels.strides[0],
            QImage.Format.Format_RGB888,
        )
        if transform.mirror_horizontal or transform.mirror_vertical:
            image = image.mirrored(transform.mirror_horizontal, transform.mirror_vertical)
        if transform.rotation_degrees:
            image = image.transformed(QTransform().rotate(-transform.rotation_degrees))
        return image

    def _stage_group(self, snapshot: FrameGroupSnapshot) -> None:
        proposed_slots: dict[str, int] = {}
        for asset_id, frame in snapshot.frames.items():
            if self._assets[asset_id].color_info.hdr_unsupported:
                continue
            pair = self._textures.setdefault(asset_id, [None, None])
            current = self._front_slots.get(asset_id)
            if current is not None and self._front_frames.get(asset_id) is frame:
                proposed_slots[asset_id] = current
                continue
            slot = 0 if current is None else 1 - current
            image = self._image_for_upload(frame, self._assets[asset_id].display_transform)
            texture = pair[slot]
            if (
                texture is None
                or texture.width() != image.width()
                or texture.height() != image.height()
            ):
                if texture is not None:
                    texture.destroy()
                texture = QOpenGLTexture(image, QOpenGLTexture.MipMapGeneration.DontGenerateMipMaps)
                pair[slot] = texture
            else:
                rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
                pointer = shiboken6.VoidPtr(rgba.bits())
                texture.setData(
                    QOpenGLTexture.PixelFormat.RGBA, QOpenGLTexture.PixelType.UInt8, pointer
                )
            if not texture.isCreated() or not texture.isStorageAllocated():
                raise RuntimeError(f"视频 {asset_id} 的 OpenGL 纹理上传失败")
            proposed_slots[asset_id] = slot
        gl_error = self.context().functions().glGetError()
        if gl_error:
            raise RuntimeError(f"OpenGL 纹理上传错误：0x{gl_error:04x}")
        # Front slots change only after every route has completed and passed validation.
        self._front_slots = proposed_slots
        self._front_frames = dict(snapshot.frames)
        self._snapshot = snapshot
        self._pending_snapshot = None

    def _draw_texture(
        self,
        painter: QPainter,
        asset_id: str,
        _frame: DecodedFrame,
        _metadata: DisplayTransform,
        target: QRectF,
        source: QRectF,
        smooth: bool,
    ) -> None:
        texture = self._textures[asset_id][self._front_slots[asset_id]]
        if texture is None or self._blitter is None:
            return
        dpr = self.devicePixelRatioF()
        viewport = QRect(0, 0, round(self.width() * dpr), round(self.height() * dpr))
        physical_target = QRectF(
            target.x() * dpr,
            target.y() * dpr,
            target.width() * dpr,
            target.height() * dpr,
        )
        texture.setMinMagFilters(
            QOpenGLTexture.Filter.Linear if smooth else QOpenGLTexture.Filter.Nearest,
            QOpenGLTexture.Filter.Linear if smooth else QOpenGLTexture.Filter.Nearest,
        )
        painter.beginNativePainting()
        try:
            self._blitter.bind()
            target_matrix = QOpenGLTextureBlitter.targetTransform(physical_target, viewport)
            source_matrix = QOpenGLTextureBlitter.sourceTransform(
                source,
                QSize(texture.width(), texture.height()),
                QOpenGLTextureBlitter.Origin.OriginTopLeft,
            )
            self._blitter.blit(texture.textureId(), target_matrix, source_matrix)
            self._blitter.release()
        finally:
            painter.endNativePainting()

    def paintGL(self) -> None:
        self._discard_removed_textures()
        if self._pending_snapshot is not None and self._blitter is not None:
            try:
                self._stage_group(self._pending_snapshot)
                self._render_error = None
            except (RuntimeError, ValueError) as exc:
                self._pending_snapshot = None
                self._render_error = str(exc)
                self.render_failed.emit(self._render_error)
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
                self._draw_texture,
                self._layout_mode,
                self._overlay_visible,
                self.annotations,
                self._annotation_preview,
            )
            self._paint_swap_feedback(painter)
            if self._render_error:
                painter.setPen("#ef4444")
                painter.drawText(12, self.height() - 10, self._render_error)
        finally:
            painter.end()
