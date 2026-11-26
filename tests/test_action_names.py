import pytest

from aula_f108.action_names import KEY_NAMES, MODIFIER_NAMES, action_label, key_label, names, plain
from aula_f108.key_actions import (
    COMBO_MODIFIERS,
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


def test_every_name_holds_only_ascii():
    """Qt 5 can crash in fontconfig while looking up a fallback font for a glyph the UI font lacks."""
    all_names = names()
    for name in [*all_names.keys.values(), *all_names.media.values(), *all_names.mouse.values(),
                 *all_names.functions.values(), *MODIFIER_NAMES.values(), *KEY_NAMES.values()]:
        assert name.isascii(), name


def test_vendor_glyphs_are_replaced():
    assert plain("CTRL+↓") == "CTRL+Down"
    assert plain("Space") == "Space"
    keys = names().keys
    assert (keys[80], keys[81], keys[82], keys[79]) == ("Left", "Down", "Up", "Right")
    assert names().functions[50] == "CTRL+Down"
    assert names().functions[134] == "WIN+."


def test_keyboard_keys_in_the_vendor_order():
    keys = names().keys
    assert len(keys) == 115
    assert list(keys)[:3] == [0x29, 0x3A, 0x3B]
    assert keys[0x29] == "ESC"
    assert keys[0xAF] == "Fn"


def test_placeholder_key_names_are_replaced():
    keys = names().keys
    assert (keys[50], keys[100], keys[138], keys[145]) == ("Non-US #", "Non-US \\", "F18", "F25")


def test_entries_without_an_action_are_left_out():
    all_names = names()
    every = [*all_names.keys.values(), *all_names.media.values(), *all_names.mouse.values(),
             *all_names.functions.values()]
    assert "VOLINC" not in every
    assert "SWITCH" not in every


def test_media_mouse_and_function_names():
    all_names = names()
    assert len(all_names.media) == 17
    assert all_names.media[0xE9] == "Volume +"
    assert all_names.media[0x0192] == "Calculator"
    assert len(all_names.mouse) == 7
    assert all_names.mouse[(1, 1)] == "Mouse Left"
    assert all_names.mouse[(3, 0xFF)] == "Scroll Down"
    assert len(all_names.functions) == 153
    assert all_names.functions[1] == "Factory Reset"


def test_offered_functions_are_the_vendor_list():
    offered = names().offered_functions
    assert len(offered) == 43
    assert offered[:3] == (1, 2, 3)
    assert 30 not in offered  # listed by the vendor without a group: not offered


def test_every_combo_modifier_has_a_name():
    assert list(MODIFIER_NAMES) == list(COMBO_MODIFIERS)


def test_key_label_of_an_unknown_usage_is_its_number():
    assert key_label(0x04) == "A"
    assert key_label(0xB5) == "0xB5"


@pytest.mark.parametrize(("action", "label"), [
    (Default(), "Default"),
    (KeyboardKey(0x04), "A"),
    (KeyboardKey(0xB5), "0xB5"),
    (Consumer(0xE9), "Volume +"),
    (Consumer(0x1234), "0x1234"),
    (Mouse(1, 1), "Mouse Left"),
    (Mouse(3, 2), "Mouse 3:2"),
    (Macro(4), "M5"),
    (Combo((0xE0,), 0x06), "L-Ctrl+C"),
    (Combo((0xE0, 0xE1), 0x29), "L-Ctrl+L-Shift+ESC"),
    (TapHold(0xE1, 0x04, 200), "A / hold L-Shift"),
    (Toggle(0x04), "Toggle A"),
    (Function(1), "Factory Reset"),
    (Function(999), "Function 999"),
    (Raw(bytes.fromhex("0b030407")), "0B 03 04 07"),
])
def test_action_labels(action, label):
    assert action_label(action) == label
    assert label.isascii()
