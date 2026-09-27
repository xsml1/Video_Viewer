from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom


@dataclass(frozen=True, slots=True)
class ViewRegion:
    center_u: float = 0.5
    center_v: float = 0.5
    width_u: float = 1.0
    height_v: float = 1.0

    def constrained(self, *, min_size: float = 1 / 64) -> ViewRegion:
        width = min(1.0, max(min_size, self.width_u))
        height = min(1.0, max(min_size, self.height_v))
        half_w = width / 2
        half_h = height / 2
        center_u = min(1 - half_w, max(half_w, self.center_u))
        center_v = min(1 - half_h, max(half_h, self.center_v))
        return ViewRegion(center_u, center_v, width, height)

    def zoom_at(self, anchor_u: float, anchor_v: float, factor: float) -> ViewRegion:
        if factor <= 0:
            raise ValueError("缩放因子必须为正数")
        anchor_u = min(1.0, max(0.0, anchor_u))
        anchor_v = min(1.0, max(0.0, anchor_v))
        return ViewRegion(
            anchor_u - (anchor_u - self.center_u) / factor,
            anchor_v - (anchor_v - self.center_v) / factor,
            self.width_u / factor,
            self.height_v / factor,
        ).constrained()


@dataclass(frozen=True, slots=True)
class PanelTransform:
    panel: Rect
    display_width: float
    display_height: float
    region: ViewRegion
    fixed_scale: float | None = None
    pixel_ratio: float = 1.0

    def __post_init__(self) -> None:
        if self.panel.width <= 0 or self.panel.height <= 0:
            raise ValueError("面板尺寸必须为正数")
        if self.display_width <= 0 or self.display_height <= 0:
            raise ValueError("视频显示尺寸必须为正数")

    @property
    def scale(self) -> float:
        if self.fixed_scale is not None:
            return self.fixed_scale
        return min(
            self.panel.width / (self.region.width_u * self.display_width),
            self.panel.height / (self.region.height_v * self.display_height),
        )

    @property
    def content_rect(self) -> Rect:
        width = self.scale * self.region.width_u * self.display_width
        height = self.scale * self.region.height_v * self.display_height
        if self.fixed_scale is not None:
            return Rect(
                round((self.panel.x + (self.panel.width - width) / 2) * self.pixel_ratio)
                / self.pixel_ratio,
                round((self.panel.y + (self.panel.height - height) / 2) * self.pixel_ratio)
                / self.pixel_ratio,
                width,
                height,
            )
        return Rect(
            self.panel.x + (self.panel.width - width) / 2,
            self.panel.y + (self.panel.height - height) / 2,
            width,
            height,
        )

    def forward(self, u: float, v: float) -> tuple[float, float]:
        content = self.content_rect
        x = content.x + self.scale * self.display_width * (
            u - self.region.center_u + self.region.width_u / 2
        )
        y = content.y + self.scale * self.display_height * (
            v - self.region.center_v + self.region.height_v / 2
        )
        return x, y

    def inverse(self, x: float, y: float, *, require_content: bool = True) -> tuple[float, float]:
        if require_content and not self.content_rect.contains(x, y):
            raise ValueError("坐标位于视频内容以外")
        u = (
            self.region.center_u
            - self.region.width_u / 2
            + (x - self.content_rect.x) / (self.scale * self.display_width)
        )
        v = (
            self.region.center_v
            - self.region.height_v / 2
            + (y - self.content_rect.y) / (self.scale * self.display_height)
        )
        return u, v

    def pan(self, delta_x: float, delta_y: float) -> ViewRegion:
        """Pointer drag in logical pixels (x→right, y→down).

        水平方向沿用实施计划 7.2：`center_u -= Δx/(s*Dw)`，画面跟随指针。
        垂直方向按用户 2026-09-25 的明确要求改为“拖动视图”语义：
        向下拖动时视图下移（画面向上移动）。见 docs/DECISIONS.md D020。
        """
        return ViewRegion(
            self.region.center_u - delta_x / (self.scale * self.display_width),
            self.region.center_v + delta_y / (self.scale * self.display_height),
            self.region.width_u,
            self.region.height_v,
        ).constrained()

    def roi_from_screen(self, rect: Rect, *, min_logical_size: float = 4.0) -> ViewRegion:
        if rect.width < min_logical_size or rect.height < min_logical_size:
            raise ValueError("ROI 框选区域过小")
        content = self.content_rect
        left = min(content.right, max(content.x, rect.x))
        top = min(content.bottom, max(content.y, rect.y))
        right = min(content.right, max(content.x, rect.right))
        bottom = min(content.bottom, max(content.y, rect.bottom))
        if right <= left or bottom <= top:
            raise ValueError("ROI 未覆盖视频内容")
        u0, v0 = self.inverse(left, top)
        u1, v1 = self.inverse(right, bottom)
        return ViewRegion((u0 + u1) / 2, (v0 + v1) / 2, u1 - u0, v1 - v0).constrained()
