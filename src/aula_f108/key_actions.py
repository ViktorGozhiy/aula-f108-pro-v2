"""Key actions of the key tables: a tagged union over the 4-byte entries, encoded as the vendor's yN encoder does.

An entry is [page, p1, p2, p3]. An entry decodes to a typed action only when that action encodes back to the same four
bytes; every other entry, SOCD and the magnetic-switch pages included, decodes to Raw and is written back unchanged.
"""

from dataclasses import dataclass

from aula_f108.blocks import check_range

ENTRY_SIZE = 4
DEFAULT_PAGE = 0
MOUSE_PAGE = 1
KEYBOARD_PAGE = 2
CONSUMER_PAGE = 3
MACRO_PAGE = 6
COMBO_PAGE = 7
TAP_HOLD_PAGE = 9
TOGGLE_PAGE = 10
FUNCTION_PAGE = 13
FN_USAGE = 0xAF  # the keyboard usage of the Fn key
MOUSE_BUTTON = 1  # Mouse.kind of a button; the value is the button mask
MOUSE_WHEEL = 3  # Mouse.kind of the wheel; the value is 1 (up) or 0xFF (down)
MOUSE_KINDS = (MOUSE_BUTTON, MOUSE_WHEEL)
MACRO_SLOTS = 100
MACRO_ONCE = 0  # play the macro once
MACRO_TIMES = 1  # play it `count` times
MACRO_UNTIL_KEY = 2  # play it until the next key press
MACRO_MODES = (MACRO_ONCE, MACRO_TIMES, MACRO_UNTIL_KEY)
# The modifiers the vendor offers for a combo, in its order: L-Ctrl, R-Ctrl, L-Shift, R-Shift, L-Alt, R-Alt, L-Win
# and 0x65, which the vendor labels R-Win.
COMBO_MODIFIERS = (0xE0, 0xE4, 0xE1, 0xE5, 0xE2, 0xE6, 0xE3, 0x65)
TAP_HOLD_MIN_MS = 10
TAP_HOLD_MAX_MS = 1000
TAP_HOLD_STEP_MS = 10  # the entry holds the time in units of 10 ms


@dataclass(frozen=True)
class Default:
    """The firmware's own action of the key."""


@dataclass(frozen=True)
class KeyboardKey:
    usage: int  # HID keyboard usage; FN_USAGE is the Fn key


@dataclass(frozen=True)
class Consumer:
    usage: int  # 16-bit HID consumer usage (media keys)


@dataclass(frozen=True)
class Mouse:
    kind: int  # MOUSE_BUTTON or MOUSE_WHEEL
    value: int  # button mask, or 1 / 0xFF for the wheel


@dataclass(frozen=True)
class Macro:
    slot: int  # 0..99, shown as M1..M100
    mode: int = MACRO_ONCE
    count: int = 1  # the number of plays in MACRO_TIMES mode


@dataclass(frozen=True)
class Combo:
    modifiers: tuple[int, ...]  # one or two of COMBO_MODIFIERS
    usage: int  # the key pressed with them


@dataclass(frozen=True)
class TapHold:
    hold: int  # the key sent when the key is held
    tap: int  # the key sent when the key is tapped
    time_ms: int  # how long a press must last to count as a hold


@dataclass(frozen=True)
class Toggle:
    usage: int  # the key that a press switches between held and released


@dataclass(frozen=True)
class Function:
    id: int  # a keyboard function from hfd-keycodes.json


@dataclass(frozen=True)
class Raw:
    entry: bytes  # an entry the application does not model, written back unchanged


def encode(action) -> bytes:
    """The 4-byte entry of a key action. Raises ValueError for a value the entry cannot hold."""
    if isinstance(action, Default):
        return bytes(ENTRY_SIZE)
    if isinstance(action, KeyboardKey):
        check_range("key usage", action.usage, 0, 0xFF)
        return bytes([KEYBOARD_PAGE, 0, action.usage, 0])
    if isinstance(action, Consumer):
        check_range("consumer usage", action.usage, 0, 0xFFFF)
        return bytes([CONSUMER_PAGE, action.usage & 0xFF, action.usage >> 8, 0])
    if isinstance(action, Mouse):
        if action.kind not in MOUSE_KINDS:
            raise ValueError(f"mouse action kind must be 1 or 3, got {action.kind}")
        check_range("mouse value", action.value, 0, 0xFF)
        return bytes([MOUSE_PAGE, action.kind, action.value, 0])
    if isinstance(action, Macro):
        check_range("macro slot", action.slot, 0, MACRO_SLOTS - 1)
        check_range("macro mode", action.mode, MACRO_ONCE, MACRO_UNTIL_KEY)
        check_range("macro count", action.count, 1, 0xFF)
        return bytes([MACRO_PAGE, action.slot, action.mode, action.count])
    if isinstance(action, Combo):
        check_range("combo modifier count", len(action.modifiers), 1, 2)
        for modifier in action.modifiers:
            if modifier not in COMBO_MODIFIERS:
                raise ValueError(f"0x{modifier:02X} is not a combo modifier")
        check_range("combo key", action.usage, 1, 0xFF)
        if action.usage in COMBO_MODIFIERS:
            raise ValueError("the combo key must not be a modifier")
        first, second = (tuple(action.modifiers) + (0,))[:2]
        return bytes([COMBO_PAGE, first, second, action.usage])
    if isinstance(action, TapHold):
        check_range("hold key", action.hold, 1, 0xFF)
        check_range("tap key", action.tap, 1, 0xFF)
        check_range("hold time", action.time_ms, TAP_HOLD_MIN_MS, TAP_HOLD_MAX_MS)
        if action.time_ms % TAP_HOLD_STEP_MS:
            raise ValueError(f"hold time must be a multiple of {TAP_HOLD_STEP_MS} ms, got {action.time_ms}")
        return bytes([TAP_HOLD_PAGE, action.hold, action.tap, action.time_ms // TAP_HOLD_STEP_MS])
    if isinstance(action, Toggle):
        check_range("toggle key", action.usage, 1, 0xFF)
        return bytes([TOGGLE_PAGE, action.usage, 0, 0])
    if isinstance(action, Function):
        check_range("function", action.id, 1, 0xFFFFFF)
        return bytes([FUNCTION_PAGE]) + action.id.to_bytes(3, "big")
    if isinstance(action, Raw):
        if len(action.entry) != ENTRY_SIZE:
            raise ValueError(f"a key action entry is {ENTRY_SIZE} bytes, got {len(action.entry)}")
        return bytes(action.entry)
    raise ValueError(f"not a key action: {action!r}")


def decode(entry: bytes):
    """The key action of a 4-byte entry; Raw for every entry that the typed action would not rebuild unchanged."""
    entry = bytes(entry)
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"a key action entry is {ENTRY_SIZE} bytes, got {len(entry)}")
    action = _typed(entry)
    try:
        rebuilt = action is not None and encode(action) == entry
    except ValueError:
        rebuilt = False
    return action if rebuilt else Raw(entry)


def _typed(entry: bytes):
    page, p1, p2, p3 = entry
    if page == DEFAULT_PAGE:
        return Default()
    if page == MOUSE_PAGE:
        return Mouse(p1, p2)
    if page == KEYBOARD_PAGE:
        return KeyboardKey(p2)
    if page == CONSUMER_PAGE:
        return Consumer(p1 | p2 << 8)
    if page == MACRO_PAGE:
        return Macro(p1, p2, p3)
    if page == COMBO_PAGE:
        return Combo(tuple(modifier for modifier in (p1, p2) if modifier), p3)
    if page == TAP_HOLD_PAGE:
        return TapHold(p1, p2, p3 * TAP_HOLD_STEP_MS)
    if page == TOGGLE_PAGE:
        return Toggle(p1)
    if page == FUNCTION_PAGE:
        return Function(int.from_bytes(entry[1:], "big"))
    return None
