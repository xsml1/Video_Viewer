from __future__ import annotations

import pytest

from video_compare.ui.layout import (
    PANE_GAP,
    arrange,
    choose_rows,
    grid_shape,
    place_rows,
)

PORTRAIT = 1080 / 1920
LANDSCAPE = 16 / 9


def test_portrait_pair_packs_into_one_row_without_middle_gap() -> None:
    boxes = arrange([PORTRAIT, PORTRAIT], width=1200, height=740)
    assert len(boxes) == 2
    left, right = boxes
    assert left.height == right.height
    assert left.y == right.y
    assert right.x - left.right == pytest.approx(PANE_GAP)
    # The empty space ends up outside the pair instead of between the videos.
    assert left.x == pytest.approx(1200 - right.right)
    assert left.x > PANE_GAP * 2
    assert left.width / left.height == pytest.approx(PORTRAIT)


def test_portrait_pair_stacks_when_the_canvas_is_narrow() -> None:
    boxes = arrange([PORTRAIT, PORTRAIT], width=420, height=1000)
    assert len(boxes) == 2
    assert boxes[1].y - boxes[0].bottom == pytest.approx(PANE_GAP)
    assert boxes[0].x == pytest.approx(boxes[1].x)
    assert boxes[0].width == pytest.approx(boxes[1].width)


def test_landscape_pair_keeps_the_familiar_side_by_side_grid() -> None:
    boxes = arrange([LANDSCAPE, LANDSCAPE], width=1200, height=740)
    assert boxes[0].y == boxes[1].y
    assert boxes[1].x - boxes[0].right == pytest.approx(PANE_GAP)
    assert boxes[0].width > 560


def test_six_landscape_tiles_keep_two_rows_of_three() -> None:
    boxes = arrange([LANDSCAPE] * 6, width=1200, height=740)
    per_row = {round(box.y) for box in boxes}
    assert len(per_row) == 2
    assert [round(box.y) for box in boxes] == sorted(round(box.y) for box in boxes)
    assert boxes[0].width == pytest.approx(boxes[1].width)
    assert boxes[3].y > boxes[0].y


def test_forced_modes_override_the_automatic_choice() -> None:
    aspects = [PORTRAIT] * 4
    horizontal = arrange(aspects, "horizontal", width=1000, height=800)
    vertical = arrange(aspects, "vertical", width=1000, height=800)
    grid = arrange(aspects, "grid", width=1000, height=800)
    assert len({round(box.y) for box in horizontal}) == 1
    assert len({round(box.x) for box in vertical}) == 1
    assert len(grid) == 4
    assert grid[0].y == grid[1].y
    assert grid[2].y == grid[3].y > grid[0].y
    assert len({round(box.y) for box in vertical}) == 4
    assert len({round(box.x) for box in vertical}) == 1
    assert len({round(box.y) for box in grid}) == 2


def test_every_pane_shares_one_scale_and_stays_inside_the_canvas() -> None:
    aspects = [LANDSCAPE, PORTRAIT, 4 / 3, LANDSCAPE]
    boxes = arrange(aspects, "auto", width=1000, height=700)
    heights = {round(box.height, 6) for box in boxes}
    assert len(heights) == 1
    for box, aspect in zip(boxes, aspects, strict=True):
        assert box.width / box.height == pytest.approx(aspect)
        assert box.x >= 0 and box.y >= 0
        assert box.right <= 1000.0001 and box.bottom <= 700.0001
    for first, second in ((0, 1), (2, 3)):
        assert boxes[second].x >= boxes[first].right


def test_label_strip_reserves_height_above_each_row() -> None:
    plain = place_rows(((0,),), [PORTRAIT], width=400, height=600)
    striped = place_rows(((0,),), [PORTRAIT], width=400, height=600, row_extra=22)
    assert plain[0].height == pytest.approx(600)
    assert striped[0].height == pytest.approx(578)
    assert striped[0].y == pytest.approx(22)


def test_grid_shape_is_unchanged_for_one_to_six_panes() -> None:
    assert [grid_shape(count) for count in range(1, 7)] == [
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 2),
        (2, 3),
        (2, 3),
    ]


def test_rejects_invalid_input() -> None:
    assert arrange([], "auto", width=800, height=600) == ()
    with pytest.raises(ValueError):
        arrange([1.0], "auto", width=0, height=600)
    with pytest.raises(ValueError):
        arrange([0.0], "auto", width=800, height=600)
    with pytest.raises(ValueError):
        choose_rows([1.0], "diagonal", width=800, height=600)
    with pytest.raises(ValueError):
        place_rows(((0,),), [1.0], width=800, height=600, gap=-1)
