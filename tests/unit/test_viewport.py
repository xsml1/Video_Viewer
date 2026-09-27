import pytest

from video_compare.domain.viewport import PanelTransform, Rect, ViewRegion


def test_forward_inverse_are_exact_for_different_resolutions() -> None:
    region = ViewRegion(0.42, 0.63, 0.4, 0.3)
    low = PanelTransform(Rect(0, 0, 800, 600), 640, 480, region)
    high = PanelTransform(Rect(0, 0, 800, 600), 1920, 1080, region)
    point = (0.37, 0.59)
    assert low.inverse(*low.forward(*point)) == pytest.approx(point)
    assert high.inverse(*high.forward(*point)) == pytest.approx(point)


def test_black_bar_is_not_content() -> None:
    transform = PanelTransform(Rect(0, 0, 1000, 1000), 1920, 1080, ViewRegion())
    assert transform.content_rect.y > 0
    with pytest.raises(ValueError, match="内容以外"):
        transform.inverse(500, 10)


def test_zoom_keeps_mouse_anchor_stationary() -> None:
    transform = PanelTransform(Rect(0, 0, 800, 600), 1920, 1080, ViewRegion())
    screen = transform.forward(0.25, 0.4)
    anchor = transform.inverse(*screen)
    zoomed = transform.region.zoom_at(*anchor, factor=2)
    after = PanelTransform(
        transform.panel, transform.display_width, transform.display_height, zoomed
    )
    assert after.forward(*anchor) == pytest.approx(screen)


def test_pan_clamps_shared_region() -> None:
    transform = PanelTransform(Rect(0, 0, 800, 600), 640, 480, ViewRegion(0.5, 0.5, 0.25, 0.25))
    moved = transform.pan(10000, 10000)
    # 水平方向：画面跟随指针（实施计划 7.2），向右拖到底看到最右侧区域。
    assert moved.center_u == moved.width_u / 2
    # 垂直方向：用户 2026-09-25 要求的“拖动视图”方向（DECISIONS D020），
    # 向下拖动视图下移，因此钳制在可见区域的下边界。
    assert moved.center_v == 1 - moved.height_v / 2


def test_pan_direction_per_axis_is_explicit() -> None:
    transform = PanelTransform(Rect(0, 0, 800, 600), 800, 600, ViewRegion(0.5, 0.5, 0.5, 0.5))
    step = transform.scale * 600
    moved = transform.pan(40, 40)
    assert moved.center_u == pytest.approx(0.5 - 40 / (transform.scale * 800))
    assert moved.center_v == pytest.approx(0.5 + 40 / step)
    after = PanelTransform(transform.panel, 800, 600, moved)
    before_point = transform.forward(0.5, 0.5)
    after_point = after.forward(0.5, 0.5)
    # Dragging right moves the picture right; dragging down moves the picture up.
    assert after_point[0] == pytest.approx(before_point[0] + 40)
    assert after_point[1] == pytest.approx(before_point[1] - 40)
