import pytest

from aula_f108.blocks import key_colours
from aula_f108.blocks.key_colours import KeyColours
from aula_f108.keyboard import BLOCKS, Keyboard
from aula_f108.protocol import Protocol
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard

READ = load_hex("wired-14.hex")  # no colours stored: all zeros, index bytes included


def test_decodes_the_captured_read():
    assert key_colours.decode(READ) == KeyColours(((0, 0, 0),) * 128)


def test_decodes_each_entry_by_key_index():
    raw = bytearray(READ)
    raw[20:24] = bytes([5, 10, 20, 30])
    assert key_colours.decode(bytes(raw)).colours[5] == (10, 20, 30)


def test_decode_rejects_a_wrong_size():
    with pytest.raises(ValueError, match="512 bytes"):
        key_colours.decode(bytes(511))


def test_encode_without_changes_numbers_every_entry():
    out = key_colours.encode_into(READ, {})
    assert [out[index * 4] for index in range(128)] == list(range(128))
    assert all(out[index * 4 + 1:index * 4 + 4] == b"\x00\x00\x00" for index in range(128))


def test_encode_writes_only_the_changed_colours():
    raw = bytearray(READ)
    raw[29:32] = bytes([1, 2, 3])  # entry 7, set on the keyboard and not changed by the user
    out = key_colours.encode_into(bytes(raw), {"colours": {0: (255, 0, 0), 127: (0, 0, 255)}})
    assert out[0:4] == bytes([0, 255, 0, 0])
    assert out[508:512] == bytes([127, 0, 0, 255])
    assert out[28:32] == bytes([7, 1, 2, 3])


@pytest.mark.parametrize("index", [-1, 128])
def test_encode_rejects_an_index_outside_the_table(index):
    with pytest.raises(ValueError, match="key index must be within 0..127"):
        key_colours.encode_into(READ, {"colours": {index: (0, 0, 0)}})


def test_encode_accepts_the_last_index():
    assert key_colours.encode_into(READ, {"colours": {127: (1, 1, 1)}})[508:512] == bytes([127, 1, 1, 1])


def test_encode_rejects_a_bad_colour():
    with pytest.raises(ValueError, match="colour must be within 0..255"):
        key_colours.encode_into(READ, {"colours": {3: (0, 256, 0)}})


def test_encode_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unknown fields: mode"):
        key_colours.encode_into(READ, {"mode": 20})


def test_encode_rejects_a_wrong_size():
    with pytest.raises(ValueError, match="512 bytes"):
        key_colours.encode_into(bytes(4), {})


def test_written_on_the_dongle_in_22_packets():
    sim = SimulatedKeyboard(32)
    keyboard = Keyboard(Protocol(sim, lambda report: None, time_scale=0.01))
    block = BLOCKS["key_colours"]
    keyboard.write(block, keyboard.read_with_changes(block, {"colours": {1: (9, 8, 7)}}))
    assert sim.blocks["key_colours"][4:8] == bytes([1, 9, 8, 7])
    assert sim.sent_commands() == [0x14] * 22 + [0x24] * 22
