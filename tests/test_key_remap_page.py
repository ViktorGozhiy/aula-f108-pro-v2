import dataclasses

import pytest
from PyQt5.QtWidgets import QMessageBox

from aula_f108.blocks import key_tables
from aula_f108.blocks import settings as settings_block
from aula_f108.blocks.key_tables import BASE, FN, factory_tables
from aula_f108.key_actions import Default, Function, KeyboardKey
from aula_f108.layout import load_layout
from aula_f108.ui.key_remap_page import (
    EXPLANATION,
    LAYER_NAMES,
    MODE_CHANGED,
    NO_KEY,
    RESET_TITLE,
    KeyRemapPage,
    edited_text,
    reset_question,
)
from aula_f108.ui.settings_page import SYSTEM_NOTE, SettingsPage
from aula_f108.worker import ConnectionState
from fixture_data import load_hex
from mouse import move, press, release
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of

ESC, F1, A_KEY, LEFT, MUTE = 0, 1, 49, 88, 116
A, B = 0x04, 0x05
SETTINGS = settings_block.decode(load_hex("wired-11.hex"))  # Windows mode
MAC = dataclasses.replace(SETTINGS, mac_mode=True)
LAYOUT = [key.index for key in load_layout()]


def table(layer=BASE, **actions):
    entries = list(factory_tables()[layer].actions)
    for name, action in actions.items():
        entries[int(name.removeprefix("k"))] = action
    return key_tables.KeyTable(tuple(entries))


def assign(page, index, action):
    page.keyboard.touched.emit(index)
    page.editor.show_action(action)
    page.editor.assign.click()


@pytest.fixture
def page(qtbot):
    page = KeyRemapPage()
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    return page


@pytest.fixture
def read_page(page):
    page.show_block("settings", SETTINGS)
    page.show_block(BASE, table(BASE))
    page.show_block(FN, table(FN))
    return page


def test_edited_text_counts_the_changed_keys():
    assert edited_text(0) == ""
    assert edited_text(2) == "Keys changed: 2. They are marked with a dot and not yet written to the keyboard."


def test_explanation_quotes_the_apply_button(page):
    assert f"“{page.apply.text()}”" in EXPLANATION


def test_body_is_enabled_once_both_tables_are_read(page):
    page.show_block("settings", SETTINGS)
    assert not page.body.isEnabled()
    page.show_block(BASE, table(BASE))
    assert not page.body.isEnabled()
    page.show_block(FN, table(FN))
    assert page.body.isEnabled()


def test_failed_read_disables_the_body(read_page):
    read_page.show_failure("settings", "The keyboard did not answer the read.")
    assert not read_page.body.isEnabled()
    read_page.show_block("settings", SETTINGS)
    assert read_page.body.isEnabled()


def test_body_fills_the_height_of_the_page(page):
    assert page.layout().stretch(1) == 1
    assert page.layout().stretch(2) == 0


def test_keys_with_their_own_action_show_their_own_labels(read_page):
    assert read_page.current_layer() == BASE
    assert all(read_page.keyboard.label(index) is None for index in LAYOUT)  # F1..F12 default, 116..119 own codes


def test_fn_layer_shows_the_actions_that_differ_from_the_key(read_page):
    read_page.layer.setCurrentIndex(read_page.layer.findData(FN))
    assert read_page.keyboard.label(ESC) == "Factory Reset"
    assert read_page.keyboard.label(A_KEY) is None
    assert read_page.keyboard.label(F1) is None


def test_no_key_is_selected_at_first(read_page):
    assert read_page.key_label.text() == NO_KEY
    assert not read_page.editor.isEnabled()
    assert read_page.keyboard.selected() is None


def test_selecting_a_key_shows_its_action(read_page):
    read_page.keyboard.touched.emit(ESC)
    assert read_page.keyboard.selected() == ESC
    assert read_page.editor.isEnabled()
    assert read_page.editor.action() == KeyboardKey(0x29)
    assert read_page.key_label.text() == f"Key ESC, {LAYER_NAMES[BASE]}"
    assert read_page.requests == []


def test_dragging_across_keys_selects_only_the_pressed_key(read_page):
    read_page.show()
    press(read_page.keyboard, read_page.keyboard.key_rect(ESC).center())
    move(read_page.keyboard, read_page.keyboard.key_rect(F1).center())
    release(read_page.keyboard, read_page.keyboard.key_rect(F1).center())
    assert read_page.keyboard.selected() == ESC
    assert read_page.editor.action() == KeyboardKey(0x29)


def test_an_arrow_key_is_named_by_its_action(read_page):
    read_page.keyboard.touched.emit(LEFT)
    assert read_page.key_label.text() == f"Key Left, {LAYER_NAMES[BASE]}"


def test_assigning_an_action_marks_and_labels_the_key(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    assert read_page.keyboard.label(ESC) == "A"
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.edited_label.text() == edited_text(1)
    assert read_page.discard.isEnabled()
    assert read_page.apply.isEnabled()
    assert read_page.requests == []


def test_assigning_the_default_action_shows_the_key_label(read_page):
    assign(read_page, ESC, Default())
    assert read_page.keyboard.label(ESC) is None
    assert read_page.keyboard.is_marked(ESC)


def test_apply_without_edits_is_disabled(read_page):
    assert not read_page.apply.isEnabled()
    assert not read_page.discard.isEnabled()


def test_edits_are_kept_per_layer(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.layer.setCurrentIndex(read_page.layer.findData(FN))
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.editor.action() == Function(1)
    assign(read_page, ESC, KeyboardKey(B))
    assert read_page.edited_label.text() == edited_text(2)
    read_page.layer.setCurrentIndex(read_page.layer.findData(BASE))
    assert read_page.keyboard.label(ESC) == "A"


def test_apply_writes_each_layer_with_edits(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    assert read_page.requests == [(BASE, {"actions": {ESC: KeyboardKey(A)}})]
    read_page.show_written(BASE, table(BASE, k0=KeyboardKey(A)))
    read_page.layer.setCurrentIndex(read_page.layer.findData(FN))
    assign(read_page, F1, KeyboardKey(B))
    read_page.layer.setCurrentIndex(read_page.layer.findData(BASE))
    assign(read_page, F1, KeyboardKey(A))
    read_page.apply.click()
    assert read_page.requests[1:] == [
        (BASE, {"actions": {F1: KeyboardKey(A)}}), (FN, {"actions": {F1: KeyboardKey(B)}}),
    ]


def test_apply_and_reset_are_disabled_while_a_write_is_pending(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    assert not read_page.apply.isEnabled()
    assert not read_page.reset.isEnabled()
    assign(read_page, F1, KeyboardKey(B))
    read_page.apply.click()
    assert len(read_page.requests) == 1
    read_page.show_written(BASE, table(BASE, k0=KeyboardKey(A)))
    assert read_page.apply.isEnabled()
    assert read_page.reset.isEnabled()


def test_written_table_clears_the_applied_edits_and_keeps_later_ones(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    assign(read_page, F1, KeyboardKey(B))
    read_page.show_written(BASE, table(BASE, k0=KeyboardKey(A)))
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.label(ESC) == "A"
    assert read_page.keyboard.is_marked(F1)
    assert read_page.edited_label.text() == edited_text(1)


def test_reassigning_an_applied_key_survives_the_write(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    assign(read_page, ESC, KeyboardKey(0x29))
    read_page.show_written(BASE, table(BASE, k0=KeyboardKey(A)))
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.label(ESC) is None


def test_written_table_without_an_apply_replaces_the_table_and_keeps_the_edits(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_written(BASE, table(BASE, k1=KeyboardKey(B)))
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.label(F1) == "B"


def test_a_read_keeps_the_edits_on_top(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_block(BASE, table(BASE, k0=KeyboardKey(A), k1=KeyboardKey(B)))
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.label(F1) == "B"


def test_failed_write_enables_apply_and_keeps_the_edits(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    read_page.show_write_failed("settings", "Change not written.")
    assert not read_page.apply.isEnabled()
    read_page.show_write_failed(BASE, "Change not written.")
    assert read_page.apply.isEnabled()
    assert read_page.keyboard.is_marked(ESC)


def test_lost_connection_enables_apply(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    read_page.show_connection(ConnectionState("connected", "cable"))
    assert not read_page.apply.isEnabled()
    read_page.show_connection(ConnectionState("not_connected", reason="Keyboard disconnected"))
    assert read_page.apply.isEnabled()


def test_discard_drops_the_edits_of_both_layers(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.layer.setCurrentIndex(read_page.layer.findData(FN))
    assign(read_page, ESC, KeyboardKey(B))
    read_page.discard.click()
    assert read_page.keyboard.label(ESC) == "Factory Reset"
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.edited_label.text() == ""
    assert not read_page.discard.isEnabled()


def test_reset_writes_the_factory_actions_of_the_layout_keys_of_the_layer(read_page, monkeypatch):
    asked = []

    def question(*args):
        asked.append(args)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    read_page.show_block(FN, table(FN, k0=KeyboardKey(A), k15=KeyboardKey(B)))
    read_page.layer.setCurrentIndex(read_page.layer.findData(FN))
    read_page.reset.click()
    factory = factory_tables()[FN].actions
    assert read_page.requests == [(FN, {"actions": {index: factory[index] for index in LAYOUT}})]
    assert 15 not in read_page.requests[0][1]["actions"]  # outside the layout: never touched
    assert asked[0][1] == RESET_TITLE == read_page.reset.text().removesuffix("…")
    assert asked[0][2] == reset_question(FN)
    assert asked[0][4] == QMessageBox.StandardButton.No
    assert read_page.keyboard.is_marked(ESC)
    assert not read_page.apply.isEnabled()


def test_declined_reset_changes_nothing(read_page, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    read_page.reset.click()
    assert read_page.requests == []
    assert read_page.edited_label.text() == ""


def test_win_mac_change_discards_the_edits_with_a_note(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_block("settings", MAC)
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.edited_label.text() == ""
    assert not read_page.mode_note.isHidden()
    assert read_page.mode_note.text() == MODE_CHANGED


def test_written_win_mac_change_discards_the_edits(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_written("settings", MAC)
    assert not read_page.keyboard.is_marked(ESC)


def test_win_mac_change_without_edits_shows_no_note(read_page):
    read_page.show_block("settings", MAC)
    assert read_page.mode_note.isHidden()


def test_settings_without_a_mode_change_keep_the_edits(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_block("settings", dataclasses.replace(SETTINGS, debounce=5))
    assert read_page.keyboard.is_marked(ESC)


def test_first_settings_value_keeps_the_edits(page):
    page.show_block(BASE, table(BASE))
    page.show_block(FN, table(FN))
    assign(page, ESC, KeyboardKey(A))
    page.show_block("settings", MAC)
    assert page.keyboard.is_marked(ESC)


def test_next_edit_hides_the_mode_note(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_block("settings", MAC)
    assign(read_page, F1, KeyboardKey(B))
    assert read_page.mode_note.isHidden()


def test_discard_hides_the_mode_note(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_block("settings", MAC)
    read_page.discard_edits()
    assert read_page.mode_note.isHidden()


def test_factory_reset_discards_the_edits(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.apply.click()
    read_page.discard_edits()
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.reset.isEnabled()


def test_settings_page_says_that_a_system_change_discards_key_edits(qtbot):
    settings_page = SettingsPage()
    qtbot.addWidget(settings_page)
    assert settings_page.system_note.text() == SYSTEM_NOTE


def test_apply_through_the_window_writes_the_table(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyRemapPage)
    assert page.body.isEnabled()
    assign(page, ESC, KeyboardKey(A))
    page.apply.click()
    rig.step()
    assert bytes(sim.blocks[BASE][0:4]) == bytes([2, 0, A, 0])
    assert bytes(sim.blocks[BASE][4:]) == load_hex("wired-12.hex")[4:]
    assert not page.keyboard.is_marked(ESC)
    assert page.keyboard.label(ESC) == "A"


def test_win_mac_change_in_the_window_discards_the_edits_and_shows_the_new_fn_layer(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyRemapPage)
    assign(page, ESC, KeyboardKey(A))
    sim.blocks[FN][0:4] = bytes([0x0D, 0, 0, 2])  # the Fn layer of the other mode
    page_of(window, SettingsPage).system.setCurrentIndex(1)
    rig.step()
    assert sim.blocks["settings"][6] == 1
    assert not page.keyboard.is_marked(ESC)
    assert not page.mode_note.isHidden()
    page.layer.setCurrentIndex(page.layer.findData(FN))
    assert page.keyboard.label(ESC) == "Bluetooth Channel 1"


def test_apply_and_reset_are_disabled_while_an_import_runs_and_enabled_after_it(read_page):
    assign(read_page, ESC, KeyboardKey(A))
    read_page.show_import_running(True)
    assert not read_page.apply.isEnabled()
    assert not read_page.reset.isEnabled()
    read_page.apply.click()
    assert read_page.requests == []
    assert read_page.keyboard.is_marked(ESC)
    read_page.show_import_running(False)
    assert read_page.apply.isEnabled()
    assert read_page.reset.isEnabled()
    read_page.apply.click()
    assert len(read_page.requests) == 1


def test_apply_stays_disabled_without_edits_after_an_import(read_page):
    read_page.show_import_running(True)
    read_page.show_import_running(False)
    assert not read_page.apply.isEnabled()
