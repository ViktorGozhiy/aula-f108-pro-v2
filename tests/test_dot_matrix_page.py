import dataclasses

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog

from aula_f108.animation import BLACK, DOT_MATRIX_PIXELS, Animation
from aula_f108.blocks import device_info
from aula_f108.blocks.dot_matrix import DotMatrix
from aula_f108.ui.animation_controls import GIF_FILTER, OUTCOME_TEXTS
from aula_f108.ui.dot_matrix_page import BACKGROUND_KEY, STATE_NOT_REPORTED, TEXT_KEY, DotMatrixPage
from aula_f108.ui.key_animation_page import KeyAnimationPage
from aula_f108.worker import DOT_MATRIX_ANIMATION, UPLOAD_DONE
from fixture_data import load_hex
from gif_files import BLUE, RED, three_frame_gif
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of

WHITE = (255, 255, 255)
INFO = device_info.decode(load_hex("wired-10.hex"))  # led_max_frames 512


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def make_page(qtbot, settings):
    page = DotMatrixPage(settings)
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    page.uploads = []
    page.upload_requested.connect(lambda kind, payload: page.uploads.append((kind, payload)))
    return page


@pytest.fixture
def page(qtbot, settings):
    return make_page(qtbot, settings)


def test_starts_with_white_text_on_black_and_says_the_colours_are_not_reported(page):
    assert page.text_colour.colour() == WHITE
    assert page.background_colour.colour() == BLACK
    assert not page.colour_note.isHidden()


def test_state_note_names_the_buttons_that_wait_for_the_upload(page):
    assert page.state_note.text() == STATE_NOT_REPORTED
    for button in (page.rainbow_button, page.pulse_button, page.open_button, page.upload_panel.upload_button):
        assert f"“{button.text()}”" in STATE_NOT_REPORTED


def test_starts_with_the_last_written_colours(qtbot, settings):
    settings.setValue(TEXT_KEY, "#ff0000")
    settings.setValue(BACKGROUND_KEY, "#0000ff")
    page = make_page(qtbot, settings)
    assert page.text_colour.colour() == RED
    assert page.background_colour.colour() == BLUE
    assert page.colour_note.isHidden()


def test_one_stored_colour_keeps_the_note(qtbot, settings):
    settings.setValue(TEXT_KEY, "#ff0000")
    page = make_page(qtbot, settings)
    assert page.text_colour.colour() == RED
    assert page.background_colour.colour() == BLACK
    assert not page.colour_note.isHidden()


def test_text_colour_change_writes_both_colours_in_character_mode(page):
    page.text_colour.choose(RED)
    assert page.requests == [("dot_matrix", {"background": BLACK, "text": RED, "mode": 0})]


def test_background_colour_change_writes_both_colours_in_character_mode(page):
    page.background_colour.choose(BLUE)
    assert page.requests == [("dot_matrix", {"background": BLUE, "text": WHITE, "mode": 0})]


@pytest.mark.parametrize("mode", [1, 2, 3])
def test_sound_buttons_write_only_their_mode(page, mode):
    page.sound_buttons[mode].click()
    assert page.requests == [("dot_matrix", {"mode": mode})]


def test_sound_buttons_follow_the_vendor_order(page):
    assert [button.text() for button in page.sound_buttons.values()] == ["Dance to music", "Rows", "Columns"]
    assert list(page.sound_buttons) == [1, 3, 2]


def test_written_character_mode_remembers_the_colours(page, settings):
    page.show_written("dot_matrix", DotMatrix(BLUE, RED, 0, 0, 0))
    assert settings.value(TEXT_KEY) == "#ff0000"
    assert settings.value(BACKGROUND_KEY) == "#0000ff"
    assert page.colour_note.isHidden()


def test_written_sound_mode_remembers_nothing(page, settings):
    page.show_written("dot_matrix", DotMatrix(BLACK, BLACK, 0, 2, 0))
    assert settings.value(TEXT_KEY) is None
    assert not page.colour_note.isHidden()


def test_read_of_the_dot_matrix_changes_nothing(page):
    page.show_block("dot_matrix", DotMatrix(BLUE, RED, 0, 1, 0))
    assert page.text_colour.colour() == WHITE
    assert page.background_colour.colour() == BLACK
    assert page.requests == []


def test_frame_limit_comes_from_device_info(page):
    page.show_block("device_info", dataclasses.replace(INFO, led_max_frames=1))
    assert not page.editor.add_button.isEnabled()


def test_rainbow_button_loads_the_rainbow_sweep(page):
    page.rainbow_button.click()
    assert len(page.editor.animation().frames) == 14


def test_pulse_button_pulses_the_paint_colour(page):
    page.editor.paint_colour.set_colour(RED)
    page.pulse_button.click()
    frames = page.editor.animation().frames
    assert len(frames) == 16
    assert frames[8] == [RED] * DOT_MATRIX_PIXELS


def test_gif_is_scaled_into_the_editor(page, tmp_path):
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    frames = page.editor.animation().frames
    assert len(frames) == 3
    assert (frames[0][0], frames[0][6]) == (RED, BLUE)
    assert page.gif_label.text() == "Frames: 3."


def test_gif_is_cut_at_the_frame_limit(page, tmp_path):
    page.show_block("device_info", dataclasses.replace(INFO, led_max_frames=2))
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    assert len(page.editor.animation().frames) == 2
    assert page.gif_label.text().startswith("The file has 3 frames.")


def test_file_that_is_no_image_is_reported(page, tmp_path):
    (tmp_path / "a.gif").write_text("not an image")
    page.load_file(str(tmp_path / "a.gif"))
    assert page.gif_label.text().startswith("Could not open the file")
    assert len(page.editor.animation().frames) == 1


def test_damaged_file_is_reported(page, tmp_path):
    data = open(three_frame_gif(tmp_path / "a.gif"), "rb").read()
    (tmp_path / "cut.gif").write_bytes(data[:111])
    page.load_file(str(tmp_path / "cut.gif"))
    assert page.gif_label.text().startswith("Could not open the file")
    assert len(page.editor.animation().frames) == 1


def test_gif_keeps_the_speed_of_the_editor(page, tmp_path):
    page.editor.speed.setValue(40)
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    assert page.editor.speed.value() == 40


def test_open_button_loads_the_chosen_file(page, tmp_path, monkeypatch):
    path = three_frame_gif(tmp_path / "a.gif")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (path, GIF_FILTER))
    page.open_button.click()
    assert len(page.editor.animation().frames) == 3


def test_cancelled_file_dialog_changes_nothing(page, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    page.open_button.click()
    assert len(page.editor.animation().frames) == 1
    assert page.gif_label.text() == ""


def test_upload_sends_the_editor_animation(page):
    assert page.upload_panel.upload_button.isEnabled()
    page.upload_panel.upload_button.click()
    assert page.uploads == [(DOT_MATRIX_ANIMATION, Animation([[BLACK] * 49], 90).payload(49))]


def test_colour_change_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, DotMatrixPage)
    page.text_colour.choose((1, 2, 3))
    rig.step()
    assert bytes(sim.blocks["dot_matrix"]) == bytes([0, 0, 0, 1, 2, 3, 0, 0, 0])
    assert settings.value(TEXT_KEY) == "#010203"
    assert page.colour_note.isHidden()


def test_upload_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, DotMatrixPage)
    page.upload_panel.upload_button.click()
    rig.step()
    payload = Animation([[BLACK] * 49], 90).payload(49)
    assert sim.uploaded(0x41)[:len(payload)] == payload
    assert page.upload_panel.message.text() == OUTCOME_TEXTS[UPLOAD_DONE]
    chunks = -(-len(payload) // 56)
    assert (page.upload_panel.progress.value(), page.upload_panel.progress.maximum()) == (chunks, chunks)
    assert page_of(window, KeyAnimationPage).upload_panel.message.text() == ""


def test_frame_limit_reaches_the_page_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.blocks["device_info"][26:28] = (1).to_bytes(2, "little")
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, DotMatrixPage)
    assert not page.editor.add_button.isEnabled()
