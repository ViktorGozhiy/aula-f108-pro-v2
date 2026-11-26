"""GET / SET_CUSTOM_LED_DATA (0x14 / 0x24): the per-key colours, shown while the LED effect mode is 20.

The block holds 128 entries of [key index, R, G, B]; entry i belongs to key index i. The keyboard reads back zeros
as the index byte when no colours are stored, so the writer puts i into the first byte of every entry i, as the
vendor does.
"""
from dataclasses import dataclass

from aula_f108.blocks import Block, check_colour, check_fields, check_range, check_size

SIZE = 512
ENTRIES = 128
ENTRY_SIZE = 4
FIELDS = frozenset({"colours"})


@dataclass(frozen=True)
class KeyColours:
    colours: tuple[tuple[int, int, int], ...]  # indexed by key index


def decode(raw: bytes) -> KeyColours:
    check_size("key colours", raw, SIZE)
    return KeyColours(tuple(
        (raw[offset + 1], raw[offset + 2], raw[offset + 3]) for offset in range(0, SIZE, ENTRY_SIZE)
    ))


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Write the changed colours ({key index: (r, g, b)}) onto `raw` and number every entry."""
    check_size("key colours", raw, SIZE)
    check_fields(changes, FIELDS)
    out = bytearray(raw)
    for index, colour in changes.get("colours", {}).items():
        check_range("key index", index, 0, ENTRIES - 1)
        check_colour("colour", colour)
        offset = index * ENTRY_SIZE
        out[offset + 1:offset + 4] = bytes(colour)
    for index in range(ENTRIES):
        out[index * ENTRY_SIZE] = index
    return bytes(out)


BLOCK = Block("key_colours", 0x14, 0x24, SIZE, decode, encode_into)
