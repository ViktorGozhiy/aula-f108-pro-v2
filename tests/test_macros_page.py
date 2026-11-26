import pytest

from aula_f108.blocks import macros
from aula_f108.blocks.macros import KEYBOARD_ACTION, MOUSE_ACTION, MacroAction, Macros
from aula_f108.ui.macros_page import (
    DEFAULT_DELAY_MS,
    EXPLANATION,
    MacrosPage,
    edited_text,
    slot_text,
    step_text,
    used_text,
)
from aula_f108.ui.key_remap_page import KeyRemapPage
from aula_f108.worker import ConnectionState
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of

A, B = 0x04, 0x05
PRESS_A = MacroAction(DEFAULT_DELAY_MS, A, True)
RELEASE_A = MacroAction(DEFAULT_DELAY_MS, A, False)
LEFT_CLICK = MacroAction(30, 1, True, MOUSE_ACTION)


def stored(**slots):
    entries = [()] * 100
    for name, actions in slots.items():
        entries[int(name.removeprefix("m"))] = tuple(actions)
    return Macros(tuple(entries))


@pytest.fixture
def page(qtbot):
    page = MacrosPage()
    qtbot.addWidget(page)
    page.requests = []
    page.update_requested.connect(lambda block, changes: page.requests.append((block, changes)))
    return page


@pytest.fixture
def read_page(page):
    page.show_block("macros", stored())
    page.key.set_usage(A)
    return page


def steps(page):
    return [page.steps.item(row).text() for row in range(page.steps.count())]


def test_texts():
    assert step_text(PRESS_A) == "Press A, delay 50 ms"
    assert step_text(MacroAction(0, 2, False, MOUSE_ACTION)) == "Release mouse button right, delay 0 ms"
    assert step_text(MacroAction(0, 0x20, True, MOUSE_ACTION)) == "Press mouse button 0x20, delay 0 ms"
    assert step_text(MacroAction(5, 0x10, True, 2)) == "Press code 0x10 of type 2, delay 5 ms"
    assert slot_text(0, (), False) == "M1"
    assert slot_text(99, (PRESS_A, RELEASE_A), True) == "M100 (2) *"
    assert used_text(512) == "512 of 512 bytes of macro memory used."
    assert used_text(516).endswith("This is over the limit: delete actions to write the macros.")
    assert edited_text(0) == ""
    assert edited_text(2) == (
        "Macros changed: 2. They are marked with an asterisk and not yet written to the keyboard."
    )


def test_explanation_quotes_the_keys_page_and_the_apply_button(page):
    assert f"“{KeyRemapPage.title}”" in EXPLANATION
    assert f"“{page.apply.text()}”" in EXPLANATION


def test_body_is_disabled_until_the_first_read(page):
    assert not page.body.isEnabled()
    page.show_block("macros", stored())
    assert page.body.isEnabled()


def test_shows_the_slots_and_the_steps_of_the_selected_one(page):
    page.show_block("macros", stored(m0=[PRESS_A, RELEASE_A], m2=[LEFT_CLICK]))
    assert page.slots.count() == 100
    assert [page.slots.item(row).text() for row in range(4)] == ["M1 (2)", "M2", "M3 (1)", "M4"]
    assert page.current_slot() == 0
    assert steps(page) == [step_text(PRESS_A), step_text(RELEASE_A)]
    page.slots.setCurrentRow(2)
    assert steps(page) == [step_text(LEFT_CLICK)]
    assert page.used_label.text() == used_text(12 + 8)
    assert page.requests == []


def test_add_appends_the_action_of_the_editor_and_marks_the_slot(read_page):
    read_page.add.click()
    assert steps(read_page) == [step_text(PRESS_A)]
    assert read_page.steps.currentRow() == 0
    assert read_page.slots.item(0).text() == "M1 (1) *"
    assert read_page.edited_label.text() == edited_text(1)
    assert read_page.used_label.text() == used_text(8)
    assert read_page.discard.isEnabled()
    assert read_page.apply.isEnabled()
    assert read_page.requests == []


def test_add_pair_appends_a_press_and_a_release(read_page):
    read_page.press.setCurrentIndex(read_page.press.findData(False))
    read_page.add_pair.click()
    assert steps(read_page) == [step_text(PRESS_A), step_text(RELEASE_A)]
    assert read_page.steps.currentRow() == 1


def test_mouse_actions_use_the_button(read_page):
    read_page.kind.setCurrentIndex(read_page.kind.findData(MOUSE_ACTION))
    assert read_page.key.isHidden()
    assert not read_page.button.isHidden()
    read_page.button.setCurrentIndex(read_page.button.findData(1))
    read_page.delay.setValue(30)
    read_page.add.click()
    read_page.apply.click()
    assert read_page.requests == [("macros", {"macros": {0: (LEFT_CLICK,)}})]


def test_delay_takes_up_to_65535_ms(read_page):
    read_page.delay.setValue(1000)
    read_page.add.click()
    assert read_page.steps.item(0).text() == step_text(MacroAction(1000, A, True))
    assert read_page.delay.maximum() == 0xFFFF


def test_selecting_a_step_shows_it_in_the_editor(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A, LEFT_CLICK]))
    read_page.steps.setCurrentRow(1)
    assert read_page.kind.currentData() == MOUSE_ACTION
    assert read_page.button.currentData() == 1
    assert read_page.press.currentData() is True
    assert read_page.delay.value() == 30
    read_page.steps.setCurrentRow(0)
    assert read_page.kind.currentData() == KEYBOARD_ACTION
    assert read_page.key.usage() == A
    assert not read_page.key.isHidden()


def test_a_step_of_an_unnamed_type_keeps_its_type_when_replaced(read_page):
    odd = MacroAction(5, 0x40, True, 2)
    read_page.show_block("macros", stored(m0=[odd]))
    read_page.steps.setCurrentRow(0)
    assert read_page.kind.currentText() == "Type 2"
    assert read_page.button.currentText() == "0x40"
    read_page.replace.click()
    read_page.apply.click()
    assert read_page.requests == [("macros", {"macros": {0: (odd,)}})]


def test_replace_changes_the_selected_step(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A, RELEASE_A]))
    read_page.steps.setCurrentRow(1)
    read_page.key.set_usage(B)
    read_page.replace.click()
    assert steps(read_page) == [step_text(PRESS_A), step_text(MacroAction(DEFAULT_DELAY_MS, B, False))]
    assert read_page.steps.currentRow() == 1


def test_remove_deletes_the_selected_step(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A, RELEASE_A]))
    read_page.steps.setCurrentRow(1)
    read_page.remove.click()
    assert steps(read_page) == [step_text(PRESS_A)]
    assert read_page.steps.currentRow() == 0
    read_page.remove.click()
    assert steps(read_page) == []
    assert read_page.steps.currentRow() == -1


def test_up_and_down_move_the_selected_step(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A, RELEASE_A, LEFT_CLICK]))
    read_page.steps.setCurrentRow(2)
    read_page.up.click()
    assert steps(read_page) == [step_text(PRESS_A), step_text(LEFT_CLICK), step_text(RELEASE_A)]
    assert read_page.steps.currentRow() == 1
    read_page.down.click()
    assert steps(read_page) == [step_text(PRESS_A), step_text(RELEASE_A), step_text(LEFT_CLICK)]
    assert read_page.steps.currentRow() == 2


def test_step_buttons_follow_the_selection(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A, RELEASE_A]))
    assert not read_page.replace.isEnabled()
    assert not read_page.remove.isEnabled()
    assert not read_page.up.isEnabled()
    assert not read_page.down.isEnabled()
    assert read_page.clear.isEnabled()
    read_page.steps.setCurrentRow(0)
    assert read_page.replace.isEnabled()
    assert read_page.remove.isEnabled()
    assert not read_page.up.isEnabled()
    assert read_page.down.isEnabled()
    read_page.steps.setCurrentRow(1)
    assert read_page.up.isEnabled()
    assert not read_page.down.isEnabled()


def test_clear_empties_the_macro(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A, RELEASE_A]))
    read_page.clear.click()
    assert steps(read_page) == []
    assert not read_page.clear.isEnabled()
    assert read_page.slots.item(0).text() == "M1 *"
    read_page.apply.click()
    assert read_page.requests == [("macros", {"macros": {0: ()}})]


def test_apply_writes_the_edited_slots(read_page):
    read_page.add.click()
    read_page.slots.setCurrentRow(5)
    read_page.add_pair.click()
    read_page.apply.click()
    assert read_page.requests == [("macros", {"macros": {0: (PRESS_A,), 5: (PRESS_A, RELEASE_A)}})]


def test_apply_is_disabled_while_the_write_is_pending(read_page):
    read_page.add.click()
    read_page.apply.click()
    assert not read_page.apply.isEnabled()
    read_page.add.click()
    read_page.apply.click()
    assert len(read_page.requests) == 1


def test_written_block_clears_the_applied_edits_and_keeps_later_ones(read_page):
    read_page.add.click()
    read_page.apply.click()
    read_page.slots.setCurrentRow(1)
    read_page.add.click()
    read_page.show_written("macros", stored(m0=[PRESS_A]))
    assert read_page.slots.item(0).text() == "M1 (1)"
    assert read_page.slots.item(1).text() == "M2 (1) *"
    assert read_page.apply.isEnabled()


def test_written_block_without_an_apply_keeps_the_edits(read_page):
    read_page.add.click()
    read_page.show_written("macros", stored(m0=[PRESS_A], m1=[RELEASE_A]))
    assert read_page.slots.item(0).text() == "M1 (1) *"
    assert read_page.slots.item(1).text() == "M2 (1)"


def test_a_read_keeps_the_edits_on_top(read_page):
    read_page.add.click()
    read_page.show_block("macros", stored(m0=[RELEASE_A, RELEASE_A]))
    assert steps(read_page) == [step_text(PRESS_A)]
    assert read_page.slots.item(0).text() == "M1 (1) *"


def test_failed_write_and_lost_connection_enable_apply(read_page):
    read_page.add.click()
    read_page.apply.click()
    read_page.show_write_failed("macros", "Change not written.")
    assert read_page.apply.isEnabled()
    read_page.apply.click()
    read_page.show_connection(ConnectionState("connected", "cable"))
    assert not read_page.apply.isEnabled()
    read_page.show_connection(ConnectionState("not_connected", reason="Keyboard disconnected"))
    assert read_page.apply.isEnabled()


def test_discard_and_factory_reset_drop_the_edits(read_page):
    read_page.add.click()
    read_page.discard.click()
    assert steps(read_page) == []
    assert read_page.slots.item(0).text() == "M1"
    assert not read_page.discard.isEnabled()
    read_page.add.click()
    read_page.apply.click()
    read_page.discard_edits()
    assert read_page.edited_label.text() == ""
    assert not read_page.apply.isEnabled()
    read_page.add.click()
    assert read_page.apply.isEnabled()  # the edit after the reset can be applied


def test_apply_is_refused_above_the_macro_space(read_page):
    read_page.show_block("macros", stored(m0=[PRESS_A] * 125))  # 504 bytes
    read_page.slots.setCurrentRow(1)
    read_page.add.click()  # 504 + 8 = 512 bytes: they fit
    assert read_page.used_label.text() == used_text(512)
    assert read_page.apply.isEnabled()
    read_page.add.click()  # 516 bytes
    assert read_page.used_label.text() == used_text(516)
    assert not read_page.apply.isEnabled()


def test_apply_through_the_window_writes_the_macros(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, MacrosPage)
    assert page.body.isEnabled()
    page.key.set_usage(A)
    page.add_pair.click()
    page.apply.click()
    rig.step()
    assert macros.decode(bytes(sim.blocks["macros"])).macros[0] == (PRESS_A, RELEASE_A)
    assert page.slots.item(0).text() == "M1 (2)"


def test_apply_is_disabled_while_an_import_runs_and_enabled_after_it(read_page):
    read_page.add.click()
    read_page.show_import_running(True)
    assert not read_page.apply.isEnabled()
    read_page.apply.click()
    assert read_page.requests == []
    assert read_page.edited_label.text() == edited_text(1)
    read_page.show_import_running(False)
    assert read_page.apply.isEnabled()
    read_page.apply.click()
    assert len(read_page.requests) == 1


def test_apply_stays_disabled_without_edits_after_an_import(read_page):
    read_page.show_import_running(True)
    read_page.show_import_running(False)
    assert not read_page.apply.isEnabled()


def test_the_row_label_follows_the_shown_field(read_page):
    read_page.kind.setCurrentIndex(read_page.kind.findData(KEYBOARD_ACTION))
    assert not read_page.key_label.isHidden()
    assert read_page.button_label.isHidden()
    read_page.kind.setCurrentIndex(read_page.kind.findData(MOUSE_ACTION))
    assert read_page.key_label.isHidden()
    assert not read_page.button_label.isHidden()
