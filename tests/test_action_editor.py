import pytest

from aula_f108.action_names import names
from aula_f108.key_actions import (
    Combo,
    Consumer,
    Default,
    Function,
    KeyboardKey,
    Macro,
    Mouse,
    Raw,
    TapHold,
    Toggle,
)
from aula_f108.ui.action_editor import (
    COMBO_KEY_IS_MODIFIER,
    DEFAULT_HOLD_MS,
    GROUPS,
    ActionEditor,
    KeyPicker,
    raw_text,
)

A, ESC, L_SHIFT = 0x04, 0x29, 0xE1
RAW = Raw(bytes.fromhex("0b030407"))


@pytest.fixture
def editor(qtbot):
    editor = ActionEditor()
    qtbot.addWidget(editor)
    editor.chosen = []
    editor.action_chosen.connect(editor.chosen.append)
    return editor


def choose_group(editor, group):
    editor.group.setCurrentIndex(editor.group.findData(group))


@pytest.mark.parametrize(
    "action",
    [
        Default(),
        KeyboardKey(A),
        KeyboardKey(0xB5),
        Consumer(0xE9),
        Consumer(0x1234),
        Mouse(1, 2),
        Mouse(3, 0xFF),
        Mouse(1, 0x20),
        Macro(41),
        Macro(99, 1, 7),
        Macro(0, 2),
        Combo((0xE0,), A),
        Combo((0xE0, 0x65), ESC),
        TapHold(L_SHIFT, A, 250),
        Toggle(A),
        Function(9),
        Function(30),
    ],
)
def test_shows_an_action_and_builds_it_back(editor, action):
    editor.show_action(action)
    assert (
        editor.group.currentData()
        == {
            Default: "default",
            KeyboardKey: "keyboard",
            Consumer: "media",
            Mouse: "mouse",
            Macro: "macro",
            Combo: "combo",
            TapHold: "tap_hold",
            Toggle: "toggle",
            Function: "function",
        }[type(action)]
    )
    assert editor.stack.currentIndex() == editor.group.currentIndex()
    assert editor.action() == action
    assert editor.chosen == []


def test_groups_follow_the_choice_and_the_stack(editor):
    assert [editor.group.itemData(row) for row in range(editor.group.count())] == list(GROUPS)
    choose_group(editor, "mouse")
    assert editor.stack.currentIndex() == list(GROUPS).index("mouse")
    assert editor.action() == Mouse(*next(iter(names().mouse)))


def test_assign_emits_the_action_shown(editor):
    editor.show_action(KeyboardKey(ESC))
    editor.key.setCurrentIndex(editor.key.findData(A))
    editor.assign.click()
    assert editor.chosen == [KeyboardKey(A)]


def test_default_group_builds_the_default_action(editor):
    editor.show_action(KeyboardKey(A))
    choose_group(editor, "default")
    editor.assign.click()
    assert editor.chosen == [Default()]


def test_an_action_the_application_does_not_model_is_shown_read_only(editor):
    editor.show_action(RAW)
    assert editor.group.currentData() == "raw"
    assert not editor.group.model().item(editor.group.currentIndex()).isEnabled()
    assert editor.raw_text.text() == raw_text(RAW)
    assert "0B 03 04 07" in editor.raw_text.text()
    assert editor.action() is None
    assert not editor.assign.isEnabled()
    editor.assign.click()
    assert editor.chosen == []
    choose_group(editor, "keyboard")
    assert editor.assign.isEnabled()


def test_macro_count_takes_up_to_255_plays(editor):
    editor.show_action(Macro(3, 1, 5))
    editor.macro_count.setValue(200)
    assert editor.action() == Macro(3, 1, 200)


def test_macro_count_is_used_only_for_a_fixed_number_of_plays(editor):
    editor.show_action(Macro(3, 1, 5))
    assert editor.macro_count.isEnabled()
    editor.macro_mode.setCurrentIndex(editor.macro_mode.findData(0))
    assert not editor.macro_count.isEnabled()
    assert editor.action() == Macro(3, 0, 1)


def test_combo_with_one_modifier_leaves_the_second_empty(editor):
    editor.show_action(Combo((0xE0, 0xE1), A))
    editor.combo_second.setCurrentIndex(editor.combo_second.findData(0))
    assert editor.action() == Combo((0xE0,), A)


def test_combo_key_must_not_be_a_modifier(editor):
    editor.show_action(Combo((0xE0,), A))
    editor.combo_key.setCurrentIndex(editor.combo_key.findData(L_SHIFT))
    editor.assign.click()
    assert editor.chosen == []
    assert editor.error.text() == COMBO_KEY_IS_MODIFIER
    editor.combo_key.setCurrentIndex(editor.combo_key.findData(A))
    editor.assign.click()
    assert editor.chosen == [Combo((0xE0,), A)]
    assert editor.error.text() == ""


def test_changing_the_group_clears_the_error(editor):
    editor.show_action(Combo((0xE0,), L_SHIFT))
    editor.assign.click()
    choose_group(editor, "keyboard")
    assert editor.error.text() == ""


def test_hold_time_starts_at_the_vendor_value_in_steps_of_10_ms(editor):
    assert editor.hold_time.value() == DEFAULT_HOLD_MS
    assert (editor.hold_time.minimum(), editor.hold_time.maximum(), editor.hold_time.singleStep()) == (10, 1000, 10)


def test_function_choice_offers_the_vendor_list(editor):
    assert editor.function.count() == len(names().offered_functions)
    editor.show_action(Function(30))  # not offered: added to show the action read from the keyboard
    assert editor.function.count() == len(names().offered_functions) + 1


def test_key_picker_lists_the_keyboard_keys_and_adds_an_unknown_one(qtbot):
    picker = KeyPicker()
    qtbot.addWidget(picker)
    assert picker.count() == len(names().keys)
    picker.set_usage(A)
    assert (picker.usage(), picker.currentText()) == (A, "A")
    picker.set_usage(0xB5)
    assert (picker.usage(), picker.currentText()) == (0xB5, "0xB5")
    assert picker.count() == len(names().keys) + 1
    picker.set_usage(0xB5)
    assert picker.count() == len(names().keys) + 1
