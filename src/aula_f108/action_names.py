"""Names of key actions for the UI, from data/hfd-keycodes.json, the vendor's list of keys and functions.

Qt 5 can crash in fontconfig while looking up a fallback font for a glyph the UI font lacks, so every name holds only
ASCII: the vendor's arrows and its one CJK full stop are replaced.
"""
import json
from dataclasses import dataclass
from functools import cache

from aula_f108.key_actions import Combo, Consumer, Default, Function, KeyboardKey, Macro, Mouse, TapHold, Toggle
from aula_f108.layout import DATA

GLYPHS = {"←": "Left", "↓": "Down", "↑": "Up", "→": "Right", "。": "."}
# Keyboard usages whose vendor name is a placeholder: two keys of other layouts, and F13..F25, which the vendor names
# after the F108 keys whose default actions it never sends.
KEY_NAMES = {
    50: "Non-US #", 100: "Non-US \\", 133: "F13", 135: "F15", 136: "F16", 137: "F17", 138: "F18", 139: "F19",
    144: "F24", 145: "F25",
}
# The vendor's labels of the combo modifiers (it labels 0x65 R-Win).
MODIFIER_NAMES = {
    0xE0: "L-Ctrl", 0xE4: "R-Ctrl", 0xE1: "L-Shift", 0xE5: "R-Shift", 0xE2: "L-Alt", 0xE6: "R-Alt", 0xE3: "L-Win",
    0x65: "R-Win",
}
OFFERED_FUNCTION_GROUP = 2  # the uiGroup of the functions the vendor offers for this keyboard


@dataclass(frozen=True)
class Names:
    keys: dict               # HID keyboard usage -> name, in the vendor's order
    media: dict              # consumer usage -> name
    mouse: dict              # (Mouse.kind, Mouse.value) -> name
    functions: dict          # function id -> name
    offered_functions: tuple  # the function ids the vendor offers, in its order


def plain(name: str) -> str:
    """The name with the vendor's glyphs outside ASCII replaced."""
    for glyph, text in GLYPHS.items():
        name = name.replace(glyph, text)
    return name


@cache
def names() -> Names:
    entries = json.loads((DATA / "hfd-keycodes.json").read_text())["entries"]
    keys, media, mouse, functions, offered = {}, {}, {}, {}, []
    for entry in entries:
        name = plain(entry["name"])
        if entry["page"] == "KEYBOARD":
            keys[entry["value"]] = KEY_NAMES.get(entry["value"], name)
        elif entry["page"] == "CONSUMER_KEY":
            media[entry["value"]] = name
        elif entry["page"] == "MOUSE":
            mouse[(entry["bytes"][1], entry["bytes"][2])] = name
        elif entry["page"] == "FUNC":
            functions[entry["value"]] = name
            if entry["uiGroup"] == OFFERED_FUNCTION_GROUP:
                offered.append(entry["value"])
    return Names(keys, media, mouse, functions, tuple(offered))


def key_label(usage: int) -> str:
    return names().keys.get(usage, f"0x{usage:02X}")


def action_label(action) -> str:
    """A short text for a key action, for the keyboard picture and the editor."""
    if isinstance(action, Default):
        return "Default"
    if isinstance(action, KeyboardKey):
        return key_label(action.usage)
    if isinstance(action, Consumer):
        return names().media.get(action.usage, f"0x{action.usage:04X}")
    if isinstance(action, Mouse):
        return names().mouse.get((action.kind, action.value), f"Mouse {action.kind}:{action.value}")
    if isinstance(action, Macro):
        return f"M{action.slot + 1}"
    if isinstance(action, Combo):
        return "+".join([MODIFIER_NAMES[modifier] for modifier in action.modifiers] + [key_label(action.usage)])
    if isinstance(action, TapHold):
        return f"{key_label(action.tap)} / hold {key_label(action.hold)}"
    if isinstance(action, Toggle):
        return f"Toggle {key_label(action.usage)}"
    if isinstance(action, Function):
        return names().functions.get(action.id, f"Function {action.id}")
    return action.entry.hex(" ").upper()
