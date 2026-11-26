import dataclasses

import pytest
from PyQt5.QtCore import Qt

from aula_f108.blocks import settings as settings_block
from aula_f108.ui.key_remap_page import KeyRemapPage
from aula_f108.ui.settings_page import SYSTEM_NOTE, SettingsPage, rate_label
from fixture_data import load_hex

READ = settings_block.decode(load_hex("wired-11.hex"))


@pytest.fixture
def page(qtbot):
    page = SettingsPage()
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    page.show_block("settings", READ)
    return page


@pytest.mark.parametrize(("hz", "label"), [(125, "125 Hz"), (500, "500 Hz"), (1000, "1 kHz"), (8000, "8 kHz")])
def test_rate_labels(hz, label):
    assert rate_label(hz) == label


def test_system_note_quotes_the_keys_page():
    assert f"“{KeyRemapPage.title}”" in SYSTEM_NOTE


def test_shows_the_read_settings_without_requesting_writes(page):
    assert page.polling_rate.currentText() == "8 kHz"
    assert page.sleep.value() == 1
    assert page.debounce.value() == 3
    assert page.system.currentText() == "Windows"
    assert not page.win_lock.isChecked()
    assert page.requests == []


def test_read_shows_mac_mode_and_win_lock_without_requesting_writes(page):
    page.show_block("settings", dataclasses.replace(READ, mac_mode=True, win_lock=True))
    assert page.system.currentText() == "macOS"
    assert page.win_lock.isChecked()
    assert page.requests == []


def test_sleep_zero_reads_never(page):
    page.sleep.setValue(0)
    assert page.sleep.text() == "Never"


def test_polling_rate_is_labelled_as_the_cable_rate(page):
    assert "over the cable" in page.rate_note.text()


def test_controls_request_their_field(page):
    page.polling_rate.setCurrentIndex(3)
    page.sleep.setValue(10)
    page.debounce.setValue(5)
    page.system.setCurrentIndex(1)
    page.win_lock.setChecked(True)
    assert page.requests == [
        ("settings", {"polling_rate": 3}),
        ("settings", {"sleep_minutes": 10}),
        ("settings", {"debounce": 5}),
        ("settings", {"mac_mode": True}),
        ("settings", {"win_lock": True}),
    ]


@pytest.mark.parametrize(("spin_box", "typed", "change"), [
    ("sleep", "25", {"sleep_minutes": 25}),
    ("debounce", "5", {"debounce": 5}),
])
def test_typed_value_is_requested_once_when_editing_finishes(qtbot, page, spin_box, typed, change):
    field = getattr(page, spin_box).lineEdit()
    field.selectAll()
    qtbot.keyClicks(field, typed)
    assert page.requests == []
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert page.requests == [("settings", change)]
