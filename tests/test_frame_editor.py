import pytest
from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QColor

from aula_f108.animation import BLACK, Animation
from aula_f108.ui.frame_editor import FrameEditor, PixelGrid
from mouse import move, press

RED = (255, 0, 0)
BLUE = (0, 0, 255)


@pytest.fixture
def grid(qtbot):
    grid = PixelGrid()
    qtbot.addWidget(grid)
    grid.resize(210, 210)
    grid.touches = []
    grid.touched.connect(grid.touches.append)
    return grid


@pytest.fixture
def editor(qtbot):
    editor = FrameEditor()
    qtbot.addWidget(editor)
    return editor


def frame_names(editor):
    return [editor.frame_list.item(row).text() for row in range(editor.frame_list.count())]


def test_cells_are_row_major(grid):
    assert grid.cell_rect(8) == QRectF(30, 30, 30, 30)


def test_cells_are_centred_in_a_wider_grid(grid):
    grid.resize(300, 210)
    assert grid.cell_rect(0) == QRectF(45, 0, 30, 30)
    assert grid.item_at(QPointF(10, 10)) is None


def test_cells_are_centred_in_a_taller_grid(grid):
    grid.resize(210, 300)
    assert grid.cell_rect(0) == QRectF(0, 45, 30, 30)


def test_item_at_finds_the_pixel(grid):
    assert grid.item_at(QPointF(45, 45)) == 8


def test_drag_touches_each_pixel(grid):
    press(grid, QPointF(15, 15))
    move(grid, QPointF(45, 15))
    assert grid.touches == [0, 1]


def test_pixels_are_drawn_in_their_colour(grid):
    grid.set_pixels([RED] + [BLACK] * 48)
    image = grid.grab().toImage()
    assert QColor(image.pixel(15, 15)).getRgb()[:3] == RED
    assert QColor(image.pixel(45, 15)).getRgb()[:3] == BLACK
    assert grid.pixels()[0] == RED


def test_starts_with_one_black_frame(editor):
    assert editor.animation() == Animation([[BLACK] * 49], 90)
    assert frame_names(editor) == ["Frame 1"]
    assert not editor.delete_button.isEnabled()


def test_painting_changes_the_current_frame(editor):
    editor.paint_colour.set_colour(RED)
    editor.grid.touched.emit(3)
    assert editor.animation().frames[0][3] == RED
    assert editor.grid.pixels()[3] == RED


def test_add_inserts_a_black_frame_after_the_current_one(editor):
    editor.paint_colour.set_colour(RED)
    editor.grid.touched.emit(0)
    editor.add_button.click()
    assert frame_names(editor) == ["Frame 1", "Frame 2"]
    assert editor.frame_list.currentRow() == 1
    assert editor.animation().frames[1] == [BLACK] * 49
    assert editor.delete_button.isEnabled()


def test_copy_duplicates_the_current_frame(editor):
    editor.paint_colour.set_colour(RED)
    editor.grid.touched.emit(0)
    editor.copy_button.click()
    assert editor.animation().frames[1][0] == RED
    editor.grid.touched.emit(1)
    assert editor.animation().frames[0][1] == BLACK


def test_delete_of_the_last_frame_selects_the_one_before(editor):
    editor.add_button.click()
    editor.add_button.click()
    editor.delete_button.click()
    assert len(editor.animation().frames) == 2
    assert editor.frame_list.currentRow() == 1


def test_delete_of_the_first_frame_keeps_the_first_row(editor):
    editor.paint_colour.set_colour(RED)
    editor.add_button.click()
    editor.grid.touched.emit(0)  # frame 2 gets a red pixel
    editor.frame_list.setCurrentRow(0)
    editor.delete_button.click()
    assert editor.frame_list.currentRow() == 0
    assert editor.grid.pixels()[0] == RED


def test_selecting_a_frame_shows_it(editor):
    editor.paint_colour.set_colour(RED)
    editor.grid.touched.emit(0)
    editor.add_button.click()
    editor.frame_list.setCurrentRow(0)
    assert editor.grid.pixels()[0] == RED


def test_frame_limit_disables_add_and_copy(editor):
    editor.set_max_frames(2)
    assert editor.add_button.isEnabled()
    editor.add_button.click()
    assert not editor.add_button.isEnabled()
    assert not editor.copy_button.isEnabled()
    editor.delete_button.click()
    assert editor.add_button.isEnabled()


def test_speed_sets_the_preview_interval_and_the_animation_speed(editor):
    assert editor.preview_timer.interval() == 110
    editor.speed.setValue(51)
    assert editor.preview_timer.interval() == 500
    assert editor.animation().speed == 51


def test_preview_runs_through_the_frames_and_wraps(editor):
    editor.add_button.click()
    editor.preview.setChecked(True)
    assert editor.preview_timer.isActive()
    editor.preview_timer.timeout.emit()
    assert editor.frame_list.currentRow() == 0
    editor.preview_timer.timeout.emit()
    assert editor.frame_list.currentRow() == 1
    editor.preview.setChecked(False)
    assert not editor.preview_timer.isActive()


def test_set_animation_replaces_frames_and_speed(editor):
    editor.add_button.click()
    editor.set_animation(Animation([[RED] * 49, [BLUE] * 49, [BLACK] * 49], 70))
    assert frame_names(editor) == ["Frame 1", "Frame 2", "Frame 3"]
    assert editor.frame_list.currentRow() == 0
    assert editor.grid.pixels() == [RED] * 49
    assert editor.speed.value() == 70


def test_animation_is_a_copy(editor):
    animation = editor.animation()
    animation.frames[0][0] = RED
    assert editor.animation().frames[0][0] == BLACK
