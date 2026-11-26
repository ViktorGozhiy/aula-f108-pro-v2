import copy
import dataclasses
import json

import pytest

from aula_f108 import profile
from aula_f108.blocks import key_colours, key_tables, led_effect, light_box, macros, settings
from aula_f108.blocks.macros import MacroAction
from aula_f108.key_actions import Combo, Consumer, Default, Function, KeyboardKey, Macro, Mouse, Raw, TapHold, Toggle
from aula_f108.layout import load_layout
from aula_f108.profile import IMPORT_ORDER, MODEL, ProfileError, action_from_json, action_to_json, import_changes
from fixture_data import load_hex

LAYOUT = sorted(key.index for key in load_layout())
ESC = 0
PRESS_A = MacroAction(10, 0x04, True)
RELEASE_A = MacroAction(20, 0x04, False)
COLOURS = {"led_effect": (0, 255, 255), "light_box": (0, 0, 255)}


def captured_values():
    raw_macros = macros.encode_into(load_hex("wired-15.hex"), {"macros": {3: (PRESS_A, RELEASE_A)}})
    raw_colours = key_colours.encode_into(load_hex("wired-14.hex"), {"colours": {ESC: (1, 2, 3)}})
    return {
        "settings": settings.decode(load_hex("wired-11.hex")),
        "led_effect": led_effect.decode(load_hex("wired-13.hex")),
        "light_box": light_box.decode(load_hex("wired-1B.hex")),
        "key_colours": key_colours.decode(raw_colours),
        "base_keys": key_tables.decode(load_hex("wired-12.hex")),
        "fn_keys": key_tables.decode(load_hex("wired-16.hex")),
        "macros": macros.decode(raw_macros),
    }


@pytest.fixture
def exported():
    return profile.export_profile(captured_values(), COLOURS)


def test_export_holds_the_modelled_fields(exported):
    assert exported["model"] == MODEL
    assert exported["format"] == 1
    assert exported["settings"] == {
        "win_lock": False, "sleep_minutes": 1, "debounce": 3, "polling_rate": 6, "mac_mode": False,
    }
    assert exported["led_effect"] == {
        "mode": 1, "colour": [0, 255, 255], "colourful": False, "brightness": 5, "speed": 3, "direction": 0,
    }
    assert exported["light_box"] == {"mode": 1, "colour": [0, 0, 255], "brightness": 2, "speed": 5}
    assert list(exported["key_colours"]) == [str(index) for index in LAYOUT]
    assert exported["key_colours"]["0"] == [1, 2, 3]
    assert exported["base_keys"]["0"] == {"type": "keyboard", "usage": 0x29}
    assert exported["base_keys"]["1"] == {"type": "default"}
    assert exported["fn_keys"]["0"] == {"type": "function", "id": 1}
    assert "15" not in exported["base_keys"]  # outside the layout
    assert exported["macros"] == {"3": [
        {"delay": 10, "code": 4, "press": True, "kind": 3}, {"delay": 20, "code": 4, "press": False, "kind": 3},
    ]}


def test_export_writes_per_key_mode_0x55_as_20():
    values = captured_values()
    values["led_effect"] = dataclasses.replace(values["led_effect"], mode=0x55)
    assert profile.export_profile(values, COLOURS)["led_effect"]["mode"] == 20


def test_saved_file_loads_back(exported, tmp_path):
    path = tmp_path / "profile.json"
    profile.save(path, exported)
    assert profile.load(path) == exported
    assert path.read_text().endswith("}\n")


def test_import_gives_one_write_per_block_with_the_settings_last(exported):
    result = import_changes(exported)
    assert [name for name, _changes in result] == list(IMPORT_ORDER)
    changes = dict(result)
    assert changes["settings"] == exported["settings"]
    assert changes["led_effect"]["colour"] == (0, 255, 255)
    assert changes["light_box"] == {"mode": 1, "colour": (0, 0, 255), "brightness": 2, "speed": 5}
    assert changes["key_colours"]["colours"][ESC] == (1, 2, 3)
    assert len(changes["key_colours"]["colours"]) == 108
    assert changes["base_keys"]["actions"][ESC] == KeyboardKey(0x29)
    assert changes["fn_keys"]["actions"][ESC] == Function(1)
    assert changes["macros"]["macros"][3] == (PRESS_A, RELEASE_A)
    assert changes["macros"]["macros"][0] == ()  # every slot the file does not hold is written empty
    assert len(changes["macros"]["macros"]) == 100


def test_import_skips_the_sections_the_file_does_not_hold():
    assert import_changes({"model": MODEL, "format": 1, "settings": {"debounce": 2}}) == [
        ("settings", {"debounce": 2}),
    ]
    assert import_changes({"model": MODEL, "format": 1}) == []


@pytest.mark.parametrize("action", [
    Default(), KeyboardKey(4), Consumer(0xE9), Mouse(3, 0xFF), Macro(5, 1, 3), Combo((0xE0, 0x65), 4),
    TapHold(0xE1, 4, 200), Toggle(4), Function(9), Raw(bytes.fromhex("0b030407")),
])
def test_every_action_type_goes_through_the_file(action):
    assert action_from_json(json.loads(json.dumps(action_to_json(action)))) == action


@pytest.mark.parametrize(("data", "message"), [
    ([], "the file holds no keyboard settings"),
    ({"model": "AULA F87", "format": 1}, "the file was not saved for AULA F108 Pro V2"),
    ({"model": MODEL, "format": 2}, "unknown file version: 2"),
    ({"model": MODEL, "format": 1, "dot_matrix": {}}, "unknown sections: dot_matrix"),
])
def test_import_refuses_a_file_of_another_kind(data, message):
    with pytest.raises(ProfileError, match=message):
        import_changes(data)


def broken(exported, section, value):
    data = copy.deepcopy(exported)
    data[section] = value
    return data


@pytest.mark.parametrize(("section", "value", "message"), [
    ("settings", [], "section settings: section: invalid entry"),
    ("settings", {"rate": 1}, "section settings: unknown field rate"),
    ("settings", {"debounce": "3"}, "debounce: invalid value '3'"),
    ("settings", {"debounce": True}, "debounce: invalid value True"),
    ("settings", {"mac_mode": 1}, "mac_mode: invalid value 1"),
    ("settings", {"debounce": 9}, "section settings: debounce must be within 1..5, got 9"),
    ("led_effect", {"colour": [1, 2]}, "colour: expected three numbers"),
    ("led_effect", {"colour": "red"}, "colour: expected three numbers"),
    ("led_effect", {"colour": [1, 2, "3"]}, "colour: invalid value '3'"),
    ("led_effect", {"colour": [1, 2, 256]}, "colour must be within 0..255"),
    ("led_effect", {"mode": 0x55}, "mode 85 cannot be written"),
    ("light_box", {"brightness": 0}, "section light_box: brightness must be within 1..5"),
    ("key_colours", [], "section key_colours: section: invalid entry"),
    ("key_colours", {"15": [0, 0, 0]}, "key '15' is not valid"),
    ("key_colours", {"x": [0, 0, 0]}, "key 'x' is not valid"),
    ("base_keys", [], "section base_keys: section: invalid entry"),
    ("base_keys", {"0": "A"}, "action: invalid entry 'A'"),
    ("base_keys", {"0": {"type": "socd"}}, "unknown action type 'socd'"),
    ("base_keys", {"0": {"type": []}}, "unknown action type"),
    ("base_keys", {"0": {"type": {}}}, "unknown action type"),
    ("base_keys", {"15": {"type": "default"}}, "key '15' is not valid"),
    ("base_keys", {"0": {"type": "keyboard"}}, "action keyboard must have the fields: type, usage"),
    ("base_keys", {"0": {"type": "keyboard", "usage": 4, "page": 2}}, "must have the fields"),
    ("base_keys", {"0": {"type": "keyboard", "usage": 4.0}}, "usage: invalid value 4.0"),
    ("base_keys", {"0": {"type": "keyboard", "usage": 256}}, "key usage must be within 0..255"),
    ("fn_keys", {"0": {"type": "combo", "modifiers": 224, "usage": 4}}, "modifiers: invalid entry 224"),
    ("fn_keys", {"0": {"type": "combo", "modifiers": [224, "x"], "usage": 4}}, "modifiers: invalid value"),
    ("fn_keys", {"0": {"type": "raw", "entry": [1, 2, 3]}}, "4 bytes, got 3"),
    ("fn_keys", {"0": {"type": "raw", "entry": [1, 2, 3, 256]}}, "section fn_keys"),
    ("fn_keys", {"200": {"type": "default"}}, "key '200' is not valid"),
    ("fn_keys", {"15": {"type": "default"}}, "key '15' is not valid"),
    ("macros", [], "section macros: section: invalid entry"),
    ("macros", {"100": []}, "macro slot '100' is not valid"),
    ("macros", {"0": {}}, "macro: invalid entry"),
    ("macros", {"0": ["x"]}, "macro action: invalid entry 'x'"),
    ("macros", {"0": [{"delay": 1, "code": 4, "press": True}]}, "must have the fields: code, delay, kind, press"),
    ("macros", {"0": [{"delay": 1, "code": 4, "press": 1, "kind": 3}]}, "press: invalid value 1"),
    ("macros", {"0": [{"delay": -1, "code": 4, "press": True, "kind": 3}]}, "delay must be within"),
    ("macros", {"0": [{"delay": 0, "code": 4, "press": True, "kind": 3}] * 128}, "the macros take 516 bytes"),
])
def test_import_refuses_a_section_it_cannot_write(exported, section, value, message):
    with pytest.raises(ProfileError, match=message):
        import_changes(broken(exported, section, value))


def test_import_takes_the_last_macro_slot(exported):
    data = broken(exported, "macros", {"99": [{"delay": 10, "code": 4, "press": True, "kind": 3}]})
    assert dict(import_changes(data))["macros"]["macros"][99] == (PRESS_A,)


def test_load_reports_a_missing_or_broken_file(tmp_path):
    with pytest.raises(ProfileError, match="the file could not be read"):
        profile.load(tmp_path / "missing.json")
    path = tmp_path / "broken.json"
    path.write_text("{")
    with pytest.raises(ProfileError, match="the file could not be read"):
        profile.load(path)
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ProfileError, match="the file could not be read"):
        profile.load(path)
