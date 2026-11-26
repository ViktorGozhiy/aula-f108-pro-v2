import pytest

from aula_f108.blocks import key_tables
from aula_f108.blocks.key_tables import BASE, BASE_BLOCK, FN, FN_BLOCK, LAYERS, KeyTable, factory_tables
from aula_f108.key_actions import Consumer, Default, Function, KeyboardKey, Macro
from aula_f108.keyboard import BLOCKS, Keyboard
from aula_f108.protocol import Protocol
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard

BASE_READ = load_hex("wired-12.hex")
FN_READ = load_hex("wired-16.hex")
ESC, F1, A_KEY, SCROLL_LOCK = 0, 1, 49, 100


def test_decodes_the_captured_base_table():
    actions = key_tables.decode(BASE_READ).actions
    assert len(actions) == 128
    assert actions[ESC] == KeyboardKey(0x29)
    assert actions[F1] == Default()
    assert actions[15] == Consumer(0xE2)  # outside the layout
    assert actions[116] == KeyboardKey(0xB5)  # Mute: a firmware-internal code


def test_decodes_the_captured_fn_table():
    actions = key_tables.decode(FN_READ).actions
    assert actions[ESC] == Function(1)
    assert actions[A_KEY] == KeyboardKey(0x04)


def test_encode_into_changes_only_the_named_entries():
    out = key_tables.encode_into(BASE_READ, {"actions": {ESC: KeyboardKey(0x04), 127: Function(9)}})
    assert out[0:4] == bytes([2, 0, 4, 0])
    assert out[508:512] == bytes([13, 0, 0, 9])
    assert out[4:508] == BASE_READ[4:508]


def test_encode_into_without_changes_keeps_the_table():
    assert key_tables.encode_into(BASE_READ, {}) == BASE_READ


@pytest.mark.parametrize("index", [-1, 128])
def test_encode_into_refuses_an_index_outside_the_table(index):
    with pytest.raises(ValueError, match="key index"):
        key_tables.encode_into(BASE_READ, {"actions": {index: Default()}})


def test_encode_into_refuses_an_action_the_entry_cannot_hold():
    with pytest.raises(ValueError, match="macro slot"):
        key_tables.encode_into(BASE_READ, {"actions": {ESC: Macro(100)}})


def test_encode_into_refuses_unknown_fields():
    with pytest.raises(ValueError, match="unknown fields: colours"):
        key_tables.encode_into(BASE_READ, {"colours": {}})


def test_tables_must_be_512_bytes():
    with pytest.raises(ValueError, match="512 bytes, got 511"):
        key_tables.decode(bytes(511))
    with pytest.raises(ValueError, match="512 bytes, got 511"):
        key_tables.encode_into(bytes(511), {})


def test_factory_tables_are_the_captured_reads():
    assert factory_tables() == {BASE: key_tables.decode(BASE_READ), FN: key_tables.decode(FN_READ)}
    assert isinstance(factory_tables()[BASE], KeyTable)


def test_blocks_of_the_two_layers():
    assert LAYERS == ("base_keys", "fn_keys")
    assert BLOCKS[BASE] is BASE_BLOCK
    assert BLOCKS[FN] is FN_BLOCK
    assert (BASE_BLOCK.read_cmd, BASE_BLOCK.write_cmd) == (0x12, 0x22)
    assert (FN_BLOCK.read_cmd, FN_BLOCK.write_cmd) == (0x16, 0x26)


def test_keyboard_writes_a_changed_table_on_the_dongle():
    sim = SimulatedKeyboard(32)
    keyboard = Keyboard(Protocol(sim, lambda report: None, time_scale=0.01))
    written = keyboard.read_with_changes(FN_BLOCK, {"actions": {SCROLL_LOCK: KeyboardKey(0x68)}})
    keyboard.write(FN_BLOCK, written)
    assert bytes(sim.blocks[FN]) == written
    assert written[SCROLL_LOCK * 4:SCROLL_LOCK * 4 + 4] == bytes([2, 0, 0x68, 0])
    assert sim.sent_commands() == [0x16] * 22 + [0x26] * 22  # 21 packets of 24 bytes and one of 8
