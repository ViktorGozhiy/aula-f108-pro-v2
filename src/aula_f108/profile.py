"""Export and import of the configuration the application models, as a JSON file.

The file holds decoded fields, not raw bytes: the settings, the LED effect, the light box, the per-key colours of the
108 layout keys, the 108 layout entries of both key tables and the used macro slots. Animations and the dot matrix are
not part of it. An import checks the whole file first and then gives one write request per block, so the worker writes
the fields onto a fresh read and every byte the application does not model keeps the keyboard's value.
"""

import dataclasses
import json
from pathlib import Path

from aula_f108 import key_actions
from aula_f108.blocks.led_effect import PER_KEY_MODE, PER_KEY_MODES
from aula_f108.blocks.macros import SLOTS, MacroAction
from aula_f108.key_actions import Combo, Consumer, Default, Function, KeyboardKey, Macro, Mouse, Raw, TapHold, Toggle
from aula_f108.keyboard import BLOCKS
from aula_f108.layout import load_layout

MODEL = "AULA F108 Pro V2"
FORMAT = 1
EXPORTED_BLOCKS = ("settings", "led_effect", "light_box", "key_colours", "base_keys", "fn_keys", "macros")
# The settings come last: a polling-rate write restarts the keyboard on the cable.
IMPORT_ORDER = ("led_effect", "light_box", "key_colours", "base_keys", "fn_keys", "macros", "settings")
SETTINGS_FIELDS = {"win_lock": bool, "sleep_minutes": int, "debounce": int, "polling_rate": int, "mac_mode": bool}
LED_EFFECT_FIELDS = {"mode": int, "colour": tuple, "colourful": bool, "brightness": int, "speed": int, "direction": int}
LIGHT_BOX_FIELDS = {"mode": int, "colour": tuple, "brightness": int, "speed": int}
ACTION_TYPES = {
    "default": Default,
    "keyboard": KeyboardKey,
    "consumer": Consumer,
    "mouse": Mouse,
    "macro": Macro,
    "combo": Combo,
    "tap_hold": TapHold,
    "toggle": Toggle,
    "function": Function,
    "raw": Raw,
}
TYPE_NAMES = {action_type: name for name, action_type in ACTION_TYPES.items()}
LIST_FIELDS = frozenset({("combo", "modifiers"), ("raw", "entry")})
MACRO_ACTION_FIELDS = frozenset(field.name for field in dataclasses.fields(MacroAction))


class ProfileError(ValueError):
    """The file is not a configuration this application can import. The message is shown to the user."""


def layout_indexes() -> list:
    return sorted(key.index for key in load_layout())


# Export


def export_profile(values: dict, colours: dict) -> dict:
    """The file content for the decoded blocks in `values` (by block name).

    `colours` holds the colours of "led_effect" and "light_box" that the pages show, because the keyboard does not
    report a colour the application wrote.
    """
    settings, effect, box = values["settings"], values["led_effect"], values["light_box"]
    keys = layout_indexes()
    return {
        "model": MODEL,
        "format": FORMAT,
        "settings": {field: getattr(settings, field) for field in SETTINGS_FIELDS},
        "led_effect": {
            # A read reports per-key colours as 20 or 0x55; only 20 can be written.
            "mode": PER_KEY_MODE if effect.mode in PER_KEY_MODES else effect.mode,
            "colour": list(colours["led_effect"]),
            "colourful": effect.colourful,
            "brightness": effect.brightness,
            "speed": effect.speed,
            "direction": effect.direction,
        },
        "light_box": {
            "mode": box.mode,
            "colour": list(colours["light_box"]),
            "brightness": box.brightness,
            "speed": box.speed,
        },
        "key_colours": {str(index): list(values["key_colours"].colours[index]) for index in keys},
        "base_keys": {str(index): action_to_json(values["base_keys"].actions[index]) for index in keys},
        "fn_keys": {str(index): action_to_json(values["fn_keys"].actions[index]) for index in keys},
        "macros": {
            str(slot): [dataclasses.asdict(action) for action in actions]
            for slot, actions in enumerate(values["macros"].macros)
            if actions
        },
    }


def action_to_json(action) -> dict:
    data = {"type": TYPE_NAMES[type(action)]}
    for field in dataclasses.fields(action):
        value = getattr(action, field.name)
        data[field.name] = list(value) if isinstance(value, (tuple, bytes)) else value
    return data


def save(path, profile: dict) -> None:
    Path(path).write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")


# Import


def load(path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:  # ValueError covers bad JSON and bad UTF-8
        raise ProfileError(f"the file could not be read ({error})") from error


def import_changes(profile) -> list:
    """Check the whole file and return [(block name, changes)] in the order of the writes.

    A section the file does not hold is not written. Raises ProfileError for anything the file must not hold.
    """
    if not isinstance(profile, dict):
        raise ProfileError("the file holds no keyboard settings")
    if profile.get("model") != MODEL:
        raise ProfileError(f"the file was not saved for {MODEL}")
    if profile.get("format") != FORMAT:
        raise ProfileError(f"unknown file version: {profile.get('format')!r}")
    unknown = set(profile) - {"model", "format"} - set(IMPORT_ORDER)
    if unknown:
        raise ProfileError(f"unknown sections: {', '.join(sorted(unknown))}")
    result = []
    for name in IMPORT_ORDER:
        if name not in profile:
            continue
        try:
            changes = SECTIONS[name](profile[name])
            block = BLOCKS[name]
            block.encode_into(bytes(block.size), changes)  # the ranges and sizes the block checks
        except ValueError as error:
            raise ProfileError(f"section {name}: {error}") from error
        result.append((name, changes))
    return result


def action_from_json(data):
    _require(data, dict, "action")
    type_name = data.get("type")
    action_type = ACTION_TYPES.get(type_name) if isinstance(type_name, str) else None
    if action_type is None:
        raise ProfileError(f"unknown action type {type_name!r}")
    fields = [field.name for field in dataclasses.fields(action_type)]
    if set(data) != {"type", *fields}:
        raise ProfileError(f"action {type_name} must have the fields: {', '.join(['type', *fields])}")
    values = {}
    for name in fields:
        if (type_name, name) in LIST_FIELDS:
            _require(data[name], list, name)
            values[name] = tuple(_number(item, int, name) for item in data[name])
        else:
            values[name] = _number(data[name], int, name)
    if action_type is Raw:
        values["entry"] = bytes(values["entry"])
    action = action_type(**values)
    key_actions.encode(action)  # the values the entry can hold
    return action


def _fields(data, kinds: dict) -> dict:
    _require(data, dict, "section")
    changes = {}
    for field, value in data.items():
        if field not in kinds:
            raise ProfileError(f"unknown field {field}")
        changes[field] = _colour(value) if kinds[field] is tuple else _number(value, kinds[field], field)
    return changes


def _key_colours(data) -> dict:
    _require(data, dict, "section")
    keys = layout_indexes()
    return {"colours": {_index(index, keys, "key"): _colour(colour) for index, colour in data.items()}}


def _key_table(data) -> dict:
    _require(data, dict, "section")
    keys = layout_indexes()
    return {"actions": {_index(index, keys, "key"): action_from_json(action) for index, action in data.items()}}


def _macros(data) -> dict:
    """Every slot the file does not hold is written empty."""
    _require(data, dict, "section")
    slots = {slot: () for slot in range(SLOTS)}
    for slot, actions in data.items():
        _require(actions, list, "macro")
        slots[_index(slot, range(SLOTS), "macro slot")] = tuple(_macro_action(action) for action in actions)
    return {"macros": slots}


def _macro_action(data) -> MacroAction:
    _require(data, dict, "macro action")
    if set(data) != MACRO_ACTION_FIELDS:
        raise ProfileError(f"a macro action must have the fields: {', '.join(sorted(MACRO_ACTION_FIELDS))}")
    return MacroAction(
        delay=_number(data["delay"], int, "delay"),
        code=_number(data["code"], int, "code"),
        press=_number(data["press"], bool, "press"),
        kind=_number(data["kind"], int, "kind"),
    )


SECTIONS = {
    "settings": lambda data: _fields(data, SETTINGS_FIELDS),
    "led_effect": lambda data: _fields(data, LED_EFFECT_FIELDS),
    "light_box": lambda data: _fields(data, LIGHT_BOX_FIELDS),
    "key_colours": _key_colours,
    "base_keys": _key_table,
    "fn_keys": _key_table,
    "macros": _macros,
}


def _require(value, kind: type, what: str) -> None:
    if not isinstance(value, kind):
        raise ProfileError(f"{what}: invalid entry {value!r}")


def _number(value, kind: type, what: str):
    """`value` when it has the type `kind`; a bool does not count as an int."""
    if (kind is int and isinstance(value, bool)) or not isinstance(value, kind):
        raise ProfileError(f"{what}: invalid value {value!r}")
    return value


def _colour(value) -> tuple:
    if not isinstance(value, list) or len(value) != 3:
        raise ProfileError(f"colour: expected three numbers, got {value!r}")
    return tuple(_number(component, int, "colour") for component in value)


def _index(text: str, allowed, what: str) -> int:
    if not text.isdigit() or int(text) not in allowed:
        raise ProfileError(f"{what} {text!r} is not valid")
    return int(text)
