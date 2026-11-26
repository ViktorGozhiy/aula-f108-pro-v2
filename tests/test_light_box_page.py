import pytest
from PyQt5.QtCore import QSettings

from aula_f108.blocks import light_box
from aula_f108.blocks.light_box import LightBox
from aula_f108.ui.light_box_page import COLOUR_KEY, LightBoxPage
from fixture_data import load_hex

READ = light_box.decode(load_hex("wired-1B.hex"))  # the keyboard reports red and colourful 1


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def make_page(qtbot, settings):
    page = LightBoxPage(settings)
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    return page


def select_mode(page, mode):
    page.mode.setCurrentIndex(page.mode.findData(mode))


def test_starts_with_white_and_says_the_colour_is_not_reported(qtbot, settings):
    page = make_page(qtbot, settings)
    assert page.colour.colour() == (255, 255, 255)
    assert not page.colour_note.isHidden()


def test_starts_with_the_last_written_colour(qtbot, settings):
    settings.setValue(COLOUR_KEY, "#00ff00")
    page = make_page(qtbot, settings)
    assert page.colour.colour() == (0, 255, 0)
    assert page.colour_note.isHidden()


def test_explains_which_strip_it_controls(qtbot, settings):
    page = make_page(qtbot, settings)
    assert "perimeter" in page.explanation.text()
    assert "Fn+X" in page.explanation.text()


def test_read_shows_mode_brightness_speed_but_not_the_reported_colour(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("light_box", READ)
    assert page.mode.currentData() == 1
    assert page.brightness.value() == 2
    assert page.speed.value() == 5
    assert page.colour.colour() == (255, 255, 255)
    assert page.requests == []


def test_read_of_a_later_mode_does_not_request_a_write(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("light_box", LightBox(2, (255, 0, 0), True, 2, 5))
    assert page.mode.currentData() == 2
    assert page.requests == []


@pytest.mark.parametrize(
    ("mode", "colour_on", "speed_on"), [(1, False, True), (2, True, False), (3, True, True), (5, False, True)]
)
def test_controls_follow_the_mode(qtbot, settings, mode, colour_on, speed_on):
    page = make_page(qtbot, settings)
    page.show_block("light_box", READ)
    select_mode(page, mode)
    assert page.colour.isEnabled() is colour_on
    assert page.speed.isEnabled() is speed_on


def test_every_request_carries_the_page_colour(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("light_box", READ)
    select_mode(page, 2)
    page.brightness.setValue(4)
    page.speed.setValue(3)
    page.colour.choose((0, 0, 255))
    white = (255, 255, 255)
    assert page.requests == [
        ("light_box", {"mode": 2, "colour": white}),
        ("light_box", {"brightness": 4, "colour": white}),
        ("light_box", {"speed": 3, "colour": white}),
        ("light_box", {"colour": (0, 0, 255)}),
    ]


def test_written_colour_is_remembered(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_written("light_box", LightBox(2, (0, 128, 255), False, 4, 3))
    assert settings.value(COLOUR_KEY) == "#0080ff"
    assert page.colour_note.isHidden()
    assert page.mode.currentData() == 2
    assert make_page(qtbot, settings).colour.colour() == (0, 128, 255)


def test_written_colour_is_shown_and_sent_with_the_next_change(qtbot, settings):
    page = make_page(qtbot, settings)
    page.show_block("light_box", READ)
    page.show_written("light_box", LightBox(1, (0, 255, 0), False, 2, 5))  # written by an import, for example
    assert page.colour.colour() == (0, 255, 0)
    page.brightness.setValue(4)
    assert page.requests == [("light_box", {"brightness": 4, "colour": (0, 255, 0)})]
