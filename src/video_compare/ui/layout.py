"""Pane arrangement shared by the compare canvas and the composite export.

The arrangement is computed from the real content aspect ratios so that panes
that show portrait video stay packed instead of leaving a large empty gap in
the middle of a landscape window. Every pane in one arrangement uses the same
scale, which keeps "same region" comparison fair when resolutions differ.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from video_compare.domain.viewport import Rect

LayoutMode = Literal["auto", "grid", "horizontal", "vertical"]

LAYOUT_MODES: tuple[LayoutMode, ...] = ("auto", "grid", "horizontal", "vertical")
LAYOUT_LABELS: dict[str, str] = {
    "auto": "自动（按画面比例）",
    "grid": "网格排列",
    "horizontal": "横向排列",
    "vertical": "竖向排列",
}

# 相邻画面之间的间距（逻辑像素）。导出时按设备像素放大。
PANE_GAP = 8.0
# 自动排列容忍的最大画质损失：多一行至少要让画面放大 15% 才采用，
# 这样两路同比例视频在常规窗口里保持并排，而不是被拆成上下两行。
AUTO_ROW_GAIN = 1.15


def grid_shape(count: int) -> tuple[int, int]:
    """Classic equal-cell shape, also used as the row partition of grid mode."""
    if not 1 <= count <= 6:
        raise ValueError("单画布支持 1–6 路")
    return {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2), 5: (2, 3), 6: (2, 3)}[count]


def _row_partitions(count: int, mode: LayoutMode) -> tuple[tuple[tuple[int, ...], ...], ...]:
    if mode not in LAYOUT_MODES:
        raise ValueError(f"未知排列方式：{mode}")
    if mode == "horizontal":
        return ((tuple(range(count)),),)
    if mode == "vertical":
        return (tuple((index,) for index in range(count)),)
    if mode == "grid":
        _, columns = grid_shape(count)
        return (
            tuple(
                tuple(range(start, min(count, start + columns)))
                for start in range(0, count, columns)
            ),
        )
    partitions: list[tuple[tuple[int, ...], ...]] = []
    for mask in range(1 << (count - 1)):
        rows: list[tuple[int, ...]] = []
        current = [0]
        for index in range(1, count):
            if mask & (1 << (index - 1)):
                rows.append(tuple(current))
                current = [index]
            else:
                current.append(index)
        rows.append(tuple(current))
        partitions.append(tuple(rows))
    return tuple(partitions)


def _uniform_scale(
    rows: tuple[tuple[int, ...], ...],
    aspects: Sequence[float],
    width: float,
    height: float,
    gap: float,
    row_extra: float,
) -> float:
    """Largest height that keeps every row inside the frame at one common scale."""
    scale = (height - row_extra * len(rows) - gap * (len(rows) - 1)) / len(rows)
    if scale <= 0:
        return 0.0
    for row in rows:
        total = sum(aspects[index] for index in row)
        if total <= 0:
            return 0.0
        scale = min(scale, (width - gap * (len(row) - 1)) / total)
    return max(0.0, scale)


def choose_rows(
    aspects: Sequence[float],
    mode: LayoutMode = "auto",
    *,
    width: float,
    height: float,
    gap: float = PANE_GAP,
    row_extra: float = 0.0,
) -> tuple[tuple[int, ...], ...]:
    """Group pane indices into rows; indices stay in display order."""
    count = len(aspects)
    if count == 0:
        return ()
    if width <= 0 or height <= 0:
        raise ValueError("画布尺寸必须为正数")
    if any(aspect <= 0 for aspect in aspects):
        raise ValueError("画面比例必须为正数")
    if gap < 0 or row_extra < 0:
        raise ValueError("间距不能为负")
    candidates = _row_partitions(count, mode)
    if mode != "auto":
        return candidates[0]
    scored = [
        (_uniform_scale(rows, aspects, width, height, gap, row_extra), rows) for rows in candidates
    ]
    best = max(score for score, _ in scored)
    if best <= 0:
        return min(candidates, key=len)
    # 目标：在画质损失很小的情况下尽量少分行（沿用 AUTO_ROW_GAIN 的语义）。
    limit = best / AUTO_ROW_GAIN
    return min((rows for score, rows in scored if score >= limit), key=len)


def place_rows(
    rows: tuple[tuple[int, ...], ...],
    aspects: Sequence[float],
    *,
    width: float,
    height: float,
    gap: float = PANE_GAP,
    row_extra: float = 0.0,
) -> tuple[Rect, ...]:
    """Place panes as packed content boxes of exactly the pane content ratio."""
    count = len(aspects)
    if count == 0:
        return ()
    if width <= 0 or height <= 0:
        raise ValueError("画布尺寸必须为正数")
    if any(aspect <= 0 for aspect in aspects):
        raise ValueError("画面比例必须为正数")
    if gap < 0 or row_extra < 0:
        raise ValueError("间距不能为负")
    gap = min(gap, min(width, height) / (2 * count))
    scale = _uniform_scale(rows, aspects, width, height, gap, row_extra)
    if scale <= 0:
        raise ValueError("可用空间无法容纳画面")
    total_height = (scale + row_extra) * len(rows) + gap * (len(rows) - 1)
    y = (height - total_height) / 2
    boxes: list[Rect | None] = [None] * count
    for row in rows:
        row_width = scale * sum(aspects[index] for index in row) + gap * (len(row) - 1)
        x = (width - row_width) / 2
        for index in row:
            pane_width = scale * aspects[index]
            boxes[index] = Rect(x, y + row_extra, pane_width, scale)
            x += pane_width + gap
        y += scale + row_extra + gap
    return tuple(box for box in boxes if box is not None)


def arrange(
    aspects: Sequence[float],
    mode: LayoutMode = "auto",
    *,
    width: float,
    height: float,
    gap: float = PANE_GAP,
    row_extra: float = 0.0,
) -> tuple[Rect, ...]:
    """Convenience wrapper: choose rows and place them inside the frame."""
    rows = choose_rows(aspects, mode, width=width, height=height, gap=gap, row_extra=row_extra)
    return place_rows(rows, aspects, width=width, height=height, gap=gap, row_extra=row_extra)
