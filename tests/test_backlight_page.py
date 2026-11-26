import dataclasses

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog

from aula_f108.blocks import led_effect
from aula_f108.ui.backlight_page import ANIMATION_NOTE, COLOUR_KEY, COLOUR_NOT_REPORTED, PER_KEY_NOTE, BacklightPage
from aula_f108.ui.widgets import ColourButton, signals_blocked
from fixture_data import load_hex

WHITE = (255, 255, 255)
CYAN = (0, 255, 255)
RED = (255, 0, 0)
# The fixture reports cyan, a colour chosen on the keyboard. After a host write a read reports white.
READ = led_effect.decode(load_hex("wired-13.hex"))
READ_AFTER_HOST_WRITE = dataclasses.replace(READ, colour=WHITE)


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def make_page(qtbot, settings):
    page = BacklightPage(settings)
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    return page


@pytest.fixture
def page(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("led_effect", READ_AFTER_HOST_WRITE)
    return page


def select_mode(page, mode):
    page.mode.setCurrentIndex(page.mode.findData(mode))


def test_shows_the_read_effect_without_requesting_writes(page):
    assert page.mode.currentData() == 1
    assert page.colour.colour() == WHITE
    assert not page.colourful.isChecked()
    assert page.brightness.value() == 5
    assert page.speed.value() == 3
    assert page.direction.currentData() == 0
    assert page.current_note.isHidden()
    assert page.requests == []


def test_read_shows_colourful_and_direction_without_requesting_writes(page):
    page.show_block("led_effect", led_effect.LedEffect(10, (255, 0, 0), True, 5, 3, 1))
    assert page.colourful.isChecked()
    assert page.direction.currentData() == 1
    assert page.requests == []


def test_mode_change_requests_the_mode(page):
    select_mode(page, 10)
    assert page.requests == [("led_effect", {"mode": 10, "colour": WHITE})]


@pytest.mark.parametrize("mode", [1, 20, 0x55])
def test_speed_is_off_for_static_and_per_key_modes(page, mode):
    page.show_block("led_effect", led_effect.LedEffect(mode, (0, 0, 0), False, 5, 3, 0))
    assert not page.speed.isEnabled()


def test_speed_is_on_for_other_modes(page):
    select_mode(page, 2)
    assert page.speed.isEnabled()


@pytest.mark.parametrize("mode", [10, 11, 12, 16, 18])
def test_direction_is_on_for_direction_modes(page, mode):
    select_mode(page, mode)
    assert page.direction.isEnabled()


@pytest.mark.parametrize("mode", [1, 9, 13, 17])
def test_direction_is_off_for_other_modes(page, mode):
    select_mode(page, 10)
    select_mode(page, mode)
    assert not page.direction.isEnabled()


@pytest.mark.parametrize("mode", [6, 8])
def test_colourful_is_forced_for_modes_6_and_8(page, mode):
    select_mode(page, mode)
    assert page.colourful.isChecked()
    assert not page.colourful.isEnabled()
    assert page.requests == [("led_effect", {"mode": mode, "colour": WHITE})]


def test_colourful_is_free_for_other_modes(page):
    select_mode(page, 6)
    select_mode(page, 7)
    assert page.colourful.isEnabled()


@pytest.mark.parametrize(("mode", "note"), [(20, PER_KEY_NOTE), (0x55, PER_KEY_NOTE), (0xFF, ANIMATION_NOTE)])
def test_per_key_and_animation_modes_are_explained(page, mode, note):
    page.show_block("led_effect", led_effect.LedEffect(mode, (255, 0, 0), False, 5, 0, 0))
    assert page.mode.currentIndex() == -1
    assert not page.current_note.isHidden()
    assert page.current_note.text() == note


def test_choosing_a_mode_hides_the_note(page):
    page.show_block("led_effect", led_effect.LedEffect(20, (255, 0, 0), False, 5, 0, 0))
    select_mode(page, 1)
    assert page.current_note.isHidden()


def test_controls_request_their_field_and_the_page_colour(page):
    page.brightness.setValue(2)
    page.speed.setValue(4)
    page.colourful.setChecked(True)
    page.direction.setCurrentIndex(page.direction.findData(1))
    page.colour.choose((1, 2, 3))
    assert page.requests == [
        ("led_effect", {"brightness": 2, "colour": WHITE}),
        ("led_effect", {"speed": 4, "colour": WHITE}),
        ("led_effect", {"colourful": True, "colour": WHITE}),
        ("led_effect", {"direction": 1, "colour": WHITE}),
        ("led_effect", {"colour": (1, 2, 3)}),
    ]


def test_brightness_change_after_a_read_sends_the_page_colour_not_the_read_colour(page):
    page.colour.choose((0, 128, 0))
    page.show_written("led_effect", dataclasses.replace(READ, colour=(0, 128, 0)))
    page.requests.clear()
    page.show_block("led_effect", READ_AFTER_HOST_WRITE)
    page.brightness.setValue(2)
    assert page.requests == [("led_effect", {"brightness": 2, "colour": (0, 128, 0)})]


def test_read_colour_chosen_on_the_keyboard_is_shown_and_sent(qtbot, settings):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    page.show_block("led_effect", dataclasses.replace(READ, colour=RED))
    assert page.colour.colour() == RED
    assert page.requests == []
    page.brightness.setValue(2)
    assert page.requests == [("led_effect", {"brightness": 2, "colour": RED})]


def test_white_read_keeps_the_stored_colour_and_sends_it(qtbot, settings):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    page.show_block("led_effect", READ_AFTER_HOST_WRITE)
    assert page.colour.colour() == (0, 255, 0)
    assert page.colour_note.isHidden()
    page.brightness.setValue(2)
    assert page.requests == [("led_effect", {"brightness": 2, "colour": (0, 255, 0)})]


def test_white_read_without_a_stored_colour_shows_white_and_the_note(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("led_effect", READ_AFTER_HOST_WRITE)
    assert page.colour.colour() == WHITE
    assert not page.colour_note.isHidden()


def test_white_read_after_a_real_colour_restores_the_stored_colour(qtbot, settings):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    page.show_block("led_effect", dataclasses.replace(READ, colour=RED))
    page.show_block("led_effect", READ_AFTER_HOST_WRITE)
    assert page.colour.colour() == (0, 255, 0)
    assert page.colour_note.isHidden()
    page.brightness.setValue(2)
    assert page.requests == [("led_effect", {"brightness": 2, "colour": (0, 255, 0)})]


def test_white_read_after_a_real_colour_without_a_stored_colour_shows_white_and_the_note(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("led_effect", dataclasses.replace(READ, colour=RED))
    assert page.colour_note.isHidden()
    page.show_block("led_effect", READ_AFTER_HOST_WRITE)
    assert page.colour.colour() == WHITE
    assert not page.colour_note.isHidden()
    page.brightness.setValue(2)
    assert page.requests == [("led_effect", {"brightness": 2, "colour": WHITE})]


def test_colour_note_hides_when_a_real_colour_is_read(qtbot, settings):
    page = make_page(qtbot, settings)
    assert not page.colour_note.isHidden()
    page.show_block("led_effect", READ)
    assert page.colour.colour() == CYAN
    assert page.colour_note.isHidden()


def test_starts_with_white_and_says_the_colour_is_not_reported(qtbot, settings):
    page = make_page(qtbot, settings)
    assert page.colour.colour() == WHITE
    assert not page.colour_note.isHidden()
    assert page.colour_note.text() == COLOUR_NOT_REPORTED


def test_starts_with_the_last_written_colour(qtbot, settings):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    assert page.colour.colour() == (0, 255, 0)
    assert page.colour_note.isHidden()


def test_written_colour_is_remembered(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_written("led_effect", led_effect.LedEffect(7, (0, 128, 255), True, 2, 2, 0))
    assert settings.value(COLOUR_KEY) == "#0080ff"
    assert page.colour_note.isHidden()
    assert make_page(qtbot, settings).colour.colour() == (0, 128, 255)


def test_failed_read_disables_the_page_until_the_next_read(page):
    page.show_failure("led_effect", "The keyboard did not answer")
    assert not page.body.isEnabled()
    assert not page.failure_label.isHidden()
    assert page.failure_label.text() == "The keyboard did not answer"
    page.show_block("led_effect", READ)
    assert page.body.isEnabled()
    assert page.failure_label.isHidden()


def test_written_value_is_shown(page):
    page.show_written("led_effect", led_effect.LedEffect(7, (9, 9, 9), True, 2, 2, 0))
    assert page.mode.currentData() == 7
    assert page.brightness.value() == 2
    assert page.requests == []


def test_colour_button_emits_the_dialog_choice(qtbot, monkeypatch):
    button = ColourButton()
    qtbot.addWidget(button)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *args: QColor(10, 20, 30))
    with qtbot.waitSignal(button.colour_chosen) as blocker:
        button.click()
    assert blocker.args == [(10, 20, 30)]
    assert button.text() == "#0a141e"


def test_colour_button_ignores_a_cancelled_dialog(qtbot, monkeypatch):
    button = ColourButton()
    qtbot.addWidget(button)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *args: QColor())
    with qtbot.assertNotEmitted(button.colour_chosen):
        button.click()
    assert button.colour() == (255, 255, 255)


def test_colour_button_text_colour_follows_brightness(qtbot):
    button = ColourButton()
    qtbot.addWidget(button)
    button.set_colour((255, 255, 255))
    assert "color: black" in button.styleSheet()
    button.set_colour((0, 0, 128))
    assert "color: white" in button.styleSheet()


def test_colour_button_text_colour_boundary(qtbot):
    # Brightness is red * 299 + green * 587 + blue * 114; text turns black only above 128000.
    button = ColourButton()
    qtbot.addWidget(button)
    button.set_colour((1, 189, 147))  # exactly 128000
    assert "color: white" in button.styleSheet()
    button.set_colour((2, 205, 62))  # 128001
    assert "color: black" in button.styleSheet()


def test_signals_blocked_restores_signals_after_an_error(qtbot):
    button = ColourButton()
    qtbot.addWidget(button)
    with pytest.raises(RuntimeError):
        with signals_blocked(button):
            raise RuntimeError
    assert not button.signalsBlocked()


def test_per_key_colour_write_keeps_the_stored_colour(qtbot, settings):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    page.show_written("led_effect", led_effect.LedEffect(20, WHITE, False, 5, 3, 0))
    assert settings.value(COLOUR_KEY) == "#00ff00"
    assert page.colour.colour() == (0, 255, 0)


def test_animation_setup_write_keeps_the_stored_colour_and_the_note(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_written("led_effect", led_effect.LedEffect(0xFF, RED, False, 5, 0, 0))
    assert settings.value(COLOUR_KEY) is None
    assert page.colour.colour() == WHITE
    assert not page.colour_note.isHidden()


@pytest.mark.parametrize("mode", [20, 0x55, 0xFF])
def test_colour_read_in_a_per_key_mode_is_not_taken(qtbot, settings, mode):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    page.show_block("led_effect", led_effect.LedEffect(mode, RED, False, 5, 0, 0))
    assert page.colour.colour() == (0, 255, 0)
