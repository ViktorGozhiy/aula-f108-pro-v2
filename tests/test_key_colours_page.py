import pytest
from PyQt5.QtWidgets import QMessageBox

from aula_f108.blocks import key_colours, led_effect
from aula_f108.blocks.key_colours import KeyColours
from aula_f108.ui.key_colours_page import EXPLANATION, KeyColoursPage, edited_text
from aula_f108.worker import ConnectionState
from mouse import move, press, release
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of

OFF = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
ESC, F1 = 0, 1


def table(**colours):
    entries = [OFF] * 128
    for name, colour in colours.items():
        entries[int(name.removeprefix("k"))] = colour
    return KeyColours(tuple(entries))


@pytest.fixture
def page(qtbot):
    page = KeyColoursPage()
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    return page


@pytest.fixture
def read_page(page):
    page.show_block("key_colours", table())
    page.colour.set_colour(RED)
    return page


def test_edited_text_counts_the_changed_keys():
    assert edited_text(0) == ""
    assert edited_text(2) == "Keys changed: 2. They are marked with a dot and not yet written to the keyboard."


def test_explanation_quotes_the_apply_button(page):
    assert f"“{page.apply.text()}”" in EXPLANATION


def test_body_is_disabled_until_the_first_read(page):
    assert not page.body.isEnabled()
    page.show_block("key_colours", table())
    assert page.body.isEnabled()


def test_body_fills_the_height_of_the_page(page):
    assert page.layout().stretch(1) == 1
    assert page.layout().stretch(2) == 0


def test_shows_the_read_colours_of_the_layout_keys(page):
    page.show_block("key_colours", table(k0=RED))
    assert page.keyboard.colour(ESC) == RED
    assert page.keyboard.colour(F1) == OFF
    assert page.requests == []


def test_touching_a_key_paints_and_marks_it(read_page):
    read_page.keyboard.touched.emit(ESC)
    assert read_page.keyboard.colour(ESC) == RED
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.edited_label.text() == edited_text(1)
    assert read_page.discard.isEnabled()
    assert read_page.requests == []


def test_painting_a_key_with_its_own_colour_is_an_edit(read_page):
    read_page.show_block("key_colours", table(k0=RED))
    read_page.keyboard.touched.emit(ESC)
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.edited_label.text() == edited_text(1)
    assert read_page.discard.isEnabled()


def test_pick_takes_the_colour_of_a_key_without_painting(read_page):
    read_page.show_block("key_colours", table(k1=BLUE))
    read_page.pick.setChecked(True)
    read_page.keyboard.touched.emit(F1)
    assert read_page.colour.colour() == BLUE
    assert not read_page.pick.isChecked()
    assert not read_page.keyboard.is_marked(F1)
    read_page.keyboard.touched.emit(ESC)
    assert read_page.keyboard.colour(ESC) == BLUE


def test_picking_a_colour_ends_the_drag_that_picked_it(read_page):
    read_page.show_block("key_colours", table(k1=BLUE))
    read_page.pick.setChecked(True)
    read_page.show()
    press(read_page.keyboard, read_page.keyboard.key_rect(ESC).center())
    move(read_page.keyboard, read_page.keyboard.key_rect(F1).center())
    release(read_page.keyboard, read_page.keyboard.key_rect(F1).center())
    assert not read_page.keyboard.is_marked(F1)
    assert read_page.keyboard.colour(F1) == BLUE


def test_fill_all_paints_every_layout_key(read_page):
    read_page.fill.click()
    assert all(read_page.keyboard.colour(key.index) == RED for key in read_page.keyboard.keys)
    assert read_page.edited_label.text() == edited_text(108)


def test_apply_writes_the_edits(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    assert read_page.requests == [("key_colours", {"colours": {ESC: RED}})]


def test_written_colours_of_an_apply_switch_to_per_key_colours_once(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.show_written("key_colours", table(k0=RED))
    read_page.show_written("key_colours", table(k0=RED))
    assert read_page.requests == [("key_colours", {"colours": {ESC: RED}}), ("led_effect", {"mode": 20})]


def test_read_after_an_apply_does_not_switch_the_effect(read_page):
    read_page.apply.click()
    read_page.show_block("key_colours", table())
    assert read_page.requests == [("key_colours", {"colours": {}})]


@pytest.mark.parametrize(
    "end",
    [
        lambda page: page.show_write_failed("key_colours", "Change not written."),
        lambda page: page.show_connection(ConnectionState("not_connected", reason="Keyboard disconnected")),
    ],
)
def test_a_failed_apply_does_not_switch_the_effect_on_a_later_write(read_page, end):
    read_page.apply.click()
    end(read_page)
    read_page.show_written("key_colours", table())  # a write that is not of "Apply", such as an import
    assert read_page.requests == [("key_colours", {"colours": {}})]


def test_apply_without_edits_switches_to_per_key_colours(read_page):
    read_page.apply.click()
    read_page.show_written("key_colours", table())
    assert read_page.requests == [("key_colours", {"colours": {}}), ("led_effect", {"mode": 20})]


def test_discard_drops_the_edits(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.discard.click()
    assert read_page.keyboard.colour(ESC) == OFF
    assert not read_page.keyboard.is_marked(ESC)
    assert not read_page.discard.isEnabled()


def test_a_new_read_keeps_the_edits_on_top(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.show_block("key_colours", table(k1=BLUE))
    assert read_page.keyboard.colour(ESC) == RED
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.colour(F1) == BLUE


def test_written_table_clears_the_applied_edits(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.show_written("key_colours", table(k0=RED))
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.edited_label.text() == ""
    assert read_page.requests == [("key_colours", {"colours": {ESC: RED}}), ("led_effect", {"mode": 20})]


def test_written_table_without_an_apply_replaces_the_table_and_clears_no_edit(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.show_written("key_colours", table(k0=RED, k1=BLUE))
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.colour(F1) == BLUE
    assert read_page.requests == []  # a written table without an apply switches nothing


def test_apply_through_the_window_writes_the_colours_and_mode_20(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.colour.set_colour(RED)
    page.keyboard.touched.emit(ESC)
    page.apply.click()
    rig.step(2)
    assert bytes(sim.blocks["key_colours"][0:8]) == bytes([0, 255, 0, 0, 1, 0, 0, 0])
    assert led_effect.decode(bytes(sim.blocks["led_effect"])).mode == 20
    assert not page.keyboard.is_marked(ESC)
    assert settings.value("led_effect/colour") is None


def test_failed_colour_write_keeps_the_edits_and_the_effect(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.colour.set_colour(RED)
    page.keyboard.touched.emit(ESC)
    sim.drop[0x24] = 4
    page.apply.click()
    rig.step(3)
    assert window.statusBar().currentMessage() == "Change not written. The keyboard did not answer."
    assert page.keyboard.is_marked(ESC)
    assert page.keyboard.colour(ESC) == RED
    assert key_colours.decode(bytes(sim.blocks["key_colours"])).colours[ESC] == OFF
    assert 0x23 not in [cmd for cmd, _addr, _data in sim.writes]


def test_factory_reset_discards_the_edits_once_it_is_sent(qtbot, tmp_path, monkeypatch):
    window, rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.colour.set_colour(RED)
    page.keyboard.touched.emit(ESC)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.device_page.reset_button.click()
    assert page.keyboard.is_marked(ESC)  # confirmed, but not sent yet
    rig.step()
    assert not page.keyboard.is_marked(ESC)
    assert page.keyboard.colour(ESC) == OFF


def test_dropped_factory_reset_keeps_the_edits(qtbot, tmp_path, monkeypatch):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.colour.set_colour(RED)
    page.keyboard.touched.emit(ESC)
    sim.gone = True
    rig.worker.request_read("settings")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.device_page.reset_button.click()
    rig.step()
    assert window.statusBar().currentMessage() == "Change not written. Keyboard disconnected."
    assert page.keyboard.is_marked(ESC)
    assert page.keyboard.colour(ESC) == RED


def test_repainting_an_applied_key_with_the_old_colour_survives_the_write(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.colour.set_colour(OFF)
    read_page.keyboard.touched.emit(ESC)
    read_page.show_written("key_colours", table(k0=RED))
    assert read_page.keyboard.colour(ESC) == OFF
    assert read_page.keyboard.is_marked(ESC)
    read_page.apply.click()
    assert read_page.requests[-1] == ("key_colours", {"colours": {ESC: OFF}})


def test_repainting_with_the_old_colour_survives_a_read_queued_before_the_apply(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    rig.worker.request_read("key_colours")
    page.colour.set_colour(RED)
    page.keyboard.touched.emit(ESC)
    page.apply.click()
    page.colour.set_colour(OFF)
    page.keyboard.touched.emit(ESC)
    rig.step(4)
    assert page.keyboard.colour(ESC) == OFF
    assert page.keyboard.is_marked(ESC)
    assert key_colours.decode(bytes(sim.blocks["key_colours"])).colours[ESC] == RED


def test_a_read_never_clears_an_edit(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.show_block("key_colours", table(k0=RED))
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.colour(ESC) == RED


def test_apply_is_disabled_while_the_colour_write_is_pending(read_page):
    assert read_page.apply.isEnabled()
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    assert not read_page.apply.isEnabled()
    read_page.colour.set_colour(BLUE)
    read_page.keyboard.touched.emit(F1)
    read_page.apply.click()
    assert read_page.requests == [("key_colours", {"colours": {ESC: RED}})]


def test_painting_and_filling_stay_possible_while_the_colour_write_is_pending(read_page):
    read_page.apply.click()
    assert read_page.fill.isEnabled()
    read_page.keyboard.touched.emit(ESC)
    assert read_page.keyboard.is_marked(ESC)
    read_page.fill.click()
    assert read_page.keyboard.is_marked(F1)


def test_apply_is_enabled_again_when_the_colours_are_written(read_page):
    read_page.apply.click()
    read_page.show_written("key_colours", table())
    assert read_page.apply.isEnabled()


def test_apply_is_enabled_again_when_the_colour_write_fails(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.show_write_failed("key_colours", "Change not written.")
    assert read_page.apply.isEnabled()
    assert read_page.keyboard.is_marked(ESC)
    read_page.apply.click()
    assert read_page.requests[-1] == ("key_colours", {"colours": {ESC: RED}})


def test_apply_is_enabled_again_when_the_connection_is_lost(read_page):
    read_page.apply.click()
    read_page.show_connection(ConnectionState("not_connected", reason="Keyboard disconnected"))
    assert read_page.apply.isEnabled()


def test_apply_stays_disabled_while_the_keyboard_is_connected(read_page):
    read_page.apply.click()
    read_page.show_connection(ConnectionState("connected", connection="cable"))
    assert not read_page.apply.isEnabled()


def test_a_read_leaves_apply_disabled(read_page):
    read_page.apply.click()
    read_page.show_block("key_colours", table())
    assert not read_page.apply.isEnabled()


def test_discard_and_factory_reset_end_the_pending_apply(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.discard_edits()
    assert read_page.apply.isEnabled()


def test_repaint_after_an_apply_survives_the_written_table_that_holds_its_colour(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.keyboard.touched.emit(ESC)  # painted red again while the write of red runs
    read_page.show_written("key_colours", table(k0=RED))
    assert read_page.keyboard.is_marked(ESC)
    assert read_page.apply.isEnabled()
    read_page.apply.click()
    assert read_page.requests[-1] == ("key_colours", {"colours": {ESC: RED}})


def test_repaint_to_another_colour_after_an_apply_survives_the_written_table_and_is_applied_next(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.apply.click()
    read_page.colour.set_colour(BLUE)
    read_page.keyboard.touched.emit(ESC)
    read_page.show_written("key_colours", table(k0=RED))
    assert read_page.keyboard.colour(ESC) == BLUE
    assert read_page.keyboard.is_marked(ESC)
    read_page.apply.click()
    assert read_page.requests[-1] == ("key_colours", {"colours": {ESC: BLUE}})


def test_apply_pending_through_the_window_blocks_a_second_apply_until_it_is_written(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.colour.set_colour(RED)
    page.keyboard.touched.emit(ESC)
    page.apply.click()
    page.colour.set_colour(BLUE)
    page.keyboard.touched.emit(ESC)
    assert not page.apply.isEnabled()
    page.apply.click()  # ignored while the first write is pending
    rig.step(2)
    assert page.apply.isEnabled()
    assert page.keyboard.is_marked(ESC)
    assert key_colours.decode(bytes(sim.blocks["key_colours"])).colours[ESC] == RED


def test_apply_is_enabled_again_after_a_failed_write_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.keyboard.touched.emit(ESC)
    sim.drop[0x24] = 4
    page.apply.click()
    assert not page.apply.isEnabled()
    rig.step(3)
    assert page.apply.isEnabled()
    assert page.keyboard.is_marked(ESC)


def test_apply_is_enabled_again_when_the_keyboard_is_lost_before_the_write(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyColoursPage)
    page.keyboard.touched.emit(ESC)
    sim.gone = True
    rig.worker.request_read("settings")
    page.apply.click()
    assert not page.apply.isEnabled()
    rig.step()
    assert page.apply.isEnabled()
    assert page.keyboard.is_marked(ESC)


def test_written_colours_clear_only_the_edits_they_hold(read_page):
    read_page.keyboard.touched.emit(ESC)
    read_page.keyboard.touched.emit(F1)
    read_page.apply.click()
    read_page.show_written("key_colours", table(k0=RED))
    assert not read_page.keyboard.is_marked(ESC)
    assert read_page.keyboard.is_marked(F1)


def test_apply_is_disabled_while_an_import_runs_and_enabled_after_it(read_page):
    read_page.show_import_running(True)
    assert not read_page.apply.isEnabled()
    read_page.apply.click()
    assert read_page.requests == []
    read_page.show_import_running(False)
    assert read_page.apply.isEnabled()
    read_page.apply.click()
    assert len(read_page.requests) == 1


def test_apply_stays_disabled_after_a_write_ends_during_an_import(read_page):
    read_page.apply.click()
    read_page.show_import_running(True)
    read_page.show_written("key_colours", table())
    assert not read_page.apply.isEnabled()
    read_page.show_import_running(False)
    assert read_page.apply.isEnabled()


def test_apply_stays_disabled_after_the_import_while_its_own_write_is_pending(read_page):
    read_page.apply.click()
    read_page.show_import_running(True)
    read_page.show_import_running(False)
    assert not read_page.apply.isEnabled()
