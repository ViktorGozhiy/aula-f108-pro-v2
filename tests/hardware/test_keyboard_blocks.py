"""Checks on the real keyboard, collected only with AULA_HARDWARE=1.

Each writable block is written with the value read, then with a changed value, then with the original
values again, and each write is checked by reading back. The polling rate, the factory reset, the
Win/Mac mode and the dot matrix are never written, and no animation is uploaded.
"""

import pytest

from aula_f108.blocks.macros import INDEX_SIZE, MacroAction
from aula_f108.hidraw import HidrawDevice, find_command_interfaces
from aula_f108.key_actions import KeyboardKey
from aula_f108.keyboard import BLOCKS, Keyboard
from aula_f108.protocol import Protocol, TransferError


@pytest.fixture
def keyboard():
    for interface in find_command_interfaces():
        device = HidrawDevice(interface.path, interface.report_size)
        candidate = Keyboard(Protocol(device, lambda report: None))
        try:
            candidate.read(BLOCKS["device_info"])
        except TransferError:
            device.close()
            continue
        yield candidate
        device.close()
        return
    pytest.fail("no keyboard answers on a command interface")


def other(value: int, low: int, high: int) -> int:
    return low if value != low else low + 1


def without(raw: bytes, indexes: tuple) -> bytes:
    return bytes(value for index, value in enumerate(raw) if index not in indexes)


def check_write_and_restore(
    keyboard, name: str, changes: dict, compared_fields: tuple, unreported_bytes: tuple = ()
) -> tuple[bytes, bytes]:
    """Write the read value back unchanged, then the changes, compare each read-back, and restore.

    Bytes in `unreported_bytes` are left out of the comparisons of whole reads: the keyboard does not report
    them as written. Return the original read and the read after the changed write.
    """
    block = BLOCKS[name]
    original = keyboard.read(block)
    keyboard.write(block, block.encode_into(original, {}))
    assert without(keyboard.read(block), unreported_bytes) == without(original, unreported_bytes)
    try:
        written = keyboard.read_with_changes(block, changes)
        keyboard.write(block, written)
        after = keyboard.read(block)
        for field in compared_fields:
            assert getattr(block.decode(after), field) == getattr(block.decode(written), field), field
    finally:
        keyboard.write(block, block.encode_into(original, {}))
    assert without(keyboard.read(block), unreported_bytes) == without(original, unreported_bytes)
    return original, after


def test_reads_every_block(keyboard):
    for block in BLOCKS.values():
        raw = keyboard.read(block)
        if block.reader is None:
            assert len(raw) == block.size
        else:
            assert len(raw) >= INDEX_SIZE  # the macro index and the bodies after it
        block.decode(raw)


def test_settings_write_and_restore(keyboard):
    current = BLOCKS["settings"].decode(keyboard.read(BLOCKS["settings"]))
    changes = {
        "sleep_minutes": other(current.sleep_minutes, 1, 30),
        "debounce": other(current.debounce, 1, 5),
        "win_lock": not current.win_lock,
    }
    original, after = check_write_and_restore(keyboard, "settings", changes, ("sleep_minutes", "debounce", "win_lock"))
    # Only the bytes of the changed fields differ; every byte the application does not model kept its value.
    assert {index for index in range(len(original)) if after[index] != original[index]} <= {1, 3, 4}


def test_led_effect_write_and_restore(keyboard):
    # After a write the keyboard reports the colour as ff ff ff, so the colour is not compared.
    current = BLOCKS["led_effect"].decode(keyboard.read(BLOCKS["led_effect"]))
    changes = {
        "brightness": other(current.brightness, 1, 5),
        "speed": other(current.speed, 1, 5),
        "colour": (current.colour[0] ^ 0xFF, current.colour[1], current.colour[2]),
    }
    check_write_and_restore(keyboard, "led_effect", changes, ("mode", "brightness", "speed", "colourful"), (1, 2, 3))


def test_light_box_write_and_restore(keyboard):
    # The keyboard does not report the light box colour, so only mode, brightness and speed are compared.
    current = BLOCKS["light_box"].decode(keyboard.read(BLOCKS["light_box"]))
    changes = {"brightness": other(current.brightness, 1, 5), "speed": other(current.speed, 1, 5)}
    check_write_and_restore(keyboard, "light_box", changes, ("mode", "brightness", "speed"))


KEY_COLOUR_INDEX_BYTES = tuple(range(0, 512, 4))  # the writer numbers the entries; a read may report zeros there


def test_key_colours_write_and_restore(keyboard):
    current = BLOCKS["key_colours"].decode(keyboard.read(BLOCKS["key_colours"]))
    red, green, blue = current.colours[0]
    changes = {"colours": {0: (red ^ 0xFF, green, blue)}}
    original, after = check_write_and_restore(keyboard, "key_colours", changes, ("colours",), KEY_COLOUR_INDEX_BYTES)
    # Only the red byte of entry 0 differs; every other colour kept its value.
    changed = {index for index in range(len(original)) if after[index] != original[index]}
    assert changed - set(KEY_COLOUR_INDEX_BYTES) == {1}


SCROLL_LOCK = 100
F13, F14 = 0x68, 0x69


@pytest.mark.parametrize("name", ["base_keys", "fn_keys"])
def test_key_table_write_and_restore(keyboard, name):
    # Scroll Lock gets F13 for the time of the test, or F14 when it already holds F13.
    current = BLOCKS[name].decode(keyboard.read(BLOCKS[name]))
    usage = F14 if current.actions[SCROLL_LOCK] == KeyboardKey(F13) else F13
    changes = {"actions": {SCROLL_LOCK: KeyboardKey(usage)}}
    original, after = check_write_and_restore(keyboard, name, changes, ("actions",))
    # Only the entry of Scroll Lock differs; every other entry, inside the layout or not, kept its value.
    changed = {index for index in range(len(original)) if after[index] != original[index]}
    assert changed <= set(range(SCROLL_LOCK * 4, SCROLL_LOCK * 4 + 4))


A = 0x04


def test_macros_write_and_restore(keyboard):
    # One macro goes into the last empty slot. A macro is not played unless a key is assigned to it.
    current = BLOCKS["macros"].decode(keyboard.read(BLOCKS["macros"]))
    slot = max(slot for slot, actions in enumerate(current.macros) if not actions)
    actions = (MacroAction(10, A, True), MacroAction(10, A, False))
    check_write_and_restore(keyboard, "macros", {"macros": {slot: actions}}, ("macros",))
