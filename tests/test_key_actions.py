import pytest

from aula_f108.key_actions import (
    COMBO_MODIFIERS,
    FN_USAGE,
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
    decode,
    encode,
)
from fixture_data import load_hex

CTRL, SHIFT, R_WIN = 0xE0, 0xE1, 0x65
A = 0x04


@pytest.mark.parametrize(("action", "entry"), [
    (Default(), "00000000"),
    (KeyboardKey(A), "02000400"),
    (KeyboardKey(0), "02000000"),
    (KeyboardKey(0xFF), "0200ff00"),
    (KeyboardKey(FN_USAGE), "0200af00"),
    (Consumer(0x00E9), "03e90000"),
    (Consumer(0x0192), "03920100"),
    (Consumer(0xFFFF), "03ffff00"),
    (Mouse(1, 1), "01010100"),
    (Mouse(1, 0), "01010000"),
    (Mouse(3, 0xFF), "0103ff00"),
    (Macro(0), "06000001"),
    (Macro(99, 2, 255), "066302ff"),
    (Combo((CTRL,), 1), "07e00001"),
    (Combo((CTRL, R_WIN), 0xFF), "07e065ff"),
    (TapHold(1, 1, 10), "09010101"),
    (TapHold(0xFF, 0xFF, 1000), "09ffff64"),
    (TapHold(0xE1, A, 200), "09e10414"),
    (Toggle(1), "0a010000"),
    (Toggle(0xFF), "0aff0000"),
    (Function(1), "0d000001"),
    (Function(0x123456), "0d123456"),
    (Function(0xFFFFFF), "0dffffff"),
    (Raw(bytes.fromhex("0b030407")), "0b030407"),
])
def test_encodes_and_decodes_each_action(action, entry):
    assert encode(action) == bytes.fromhex(entry)
    assert decode(bytes.fromhex(entry)) == action


@pytest.mark.parametrize("entry", [
    "00010000",  # default with a non-zero byte
    "02010400",  # keyboard key with a non-zero second byte
    "02000401",  # keyboard key with a non-zero fourth byte
    "03e90001",  # consumer key with a non-zero fourth byte
    "01020100",  # mouse action of kind 2
    "01010101",  # mouse action with a non-zero fourth byte
    "06640001",  # macro slot 100
    "06000301",  # macro mode 3
    "06000000",  # macro played 0 times
    "0700e004",  # combo with an empty first modifier
    "07000004",  # combo without modifiers
    "07550004",  # combo with a modifier the vendor does not offer
    "07e0e100",  # combo without a key
    "07e000e1",  # combo whose key is a modifier
    "09040400",  # tap/hold of 0 ms
    "09040465",  # tap/hold of 1010 ms
    "09000401",  # tap/hold without a hold key
    "0a040001",  # toggle with a non-zero fourth byte
    "0a000000",  # toggle without a key
    "0d000000",  # function 0
    "0b030407",  # SOCD
    "0e010200",  # END
    "80010002",  # FUNC_V2
    "04000000",  # system key
])
def test_entries_the_codec_cannot_rebuild_decode_as_raw(entry):
    assert decode(bytes.fromhex(entry)) == Raw(bytes.fromhex(entry))


@pytest.mark.parametrize(("action", "message"), [
    (KeyboardKey(-1), "key usage"),
    (KeyboardKey(0x100), "key usage"),
    (Consumer(-1), "consumer usage"),
    (Consumer(0x10000), "consumer usage"),
    (Mouse(2, 1), "kind must be 1 or 3"),
    (Mouse(1, -1), "mouse value"),
    (Mouse(1, 0x100), "mouse value"),
    (Macro(-1), "macro slot"),
    (Macro(100), "macro slot"),
    (Macro(0, -1), "macro mode"),
    (Macro(0, 3), "macro mode"),
    (Macro(0, 0, 0), "macro count"),
    (Macro(0, 0, 0x100), "macro count"),
    (Combo((), A), "combo modifier count"),
    (Combo((CTRL, SHIFT, R_WIN), A), "combo modifier count"),
    (Combo((0x55,), A), "0x55 is not a combo modifier"),
    (Combo((CTRL,), 0), "combo key"),
    (Combo((CTRL,), 0x100), "combo key"),
    (Combo((CTRL,), SHIFT), "must not be a modifier"),
    (TapHold(0, A, 100), "hold key"),
    (TapHold(0x100, A, 100), "hold key"),
    (TapHold(A, 0, 100), "tap key"),
    (TapHold(A, 0x100, 100), "tap key"),
    (TapHold(A, A, 0), "hold time"),
    (TapHold(A, A, 1010), "hold time"),
    (TapHold(A, A, 15), "multiple of 10 ms"),
    (Toggle(0), "toggle key"),
    (Toggle(0x100), "toggle key"),
    (Function(0), "function"),
    (Function(0x1000000), "function"),
    (Raw(bytes(3)), "4 bytes, got 3"),
    ("A", "not a key action"),
])
def test_encode_refuses_values_the_entry_cannot_hold(action, message):
    with pytest.raises(ValueError, match=message):
        encode(action)


def test_every_combo_modifier_encodes():
    for modifier in COMBO_MODIFIERS:
        assert encode(Combo((modifier,), A)) == bytes([7, modifier, 0, A])


def test_decode_needs_four_bytes():
    with pytest.raises(ValueError, match="4 bytes, got 5"):
        decode(bytes(5))


@pytest.mark.parametrize("fixture", ["wired-12.hex", "wired-16.hex"])
def test_every_captured_entry_decodes_and_encodes_back_unchanged(fixture):
    table = load_hex(fixture)
    for offset in range(0, len(table), 4):
        entry = table[offset:offset + 4]
        assert encode(decode(entry)) == entry
