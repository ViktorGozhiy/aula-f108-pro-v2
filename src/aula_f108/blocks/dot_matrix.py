"""GET_DOT_MATRIX_CONFIG / SET_DOT_MATRIX_MODE (0x3D / 0x2A): colours and sound-reactive mode of the 7×7 display.

[0..2] background RGB, [3..5] text RGB, [6] type, [7] mode, [8] dot-matrix mode. The writer builds the 9 bytes from
zeros, as the vendor does: character mode (mode 0) sets only the two colours, a sound mode (1 dance, 2 columns,
3 rows) sets only the mode. The read is unconfirmed: on firmware V1.33 it returned all zeros, so the application
does not use it to show what the display shows.
"""
from dataclasses import dataclass

from aula_f108.blocks import Block, check_colour, check_fields, check_range, check_size

SIZE = 9
CHARACTER_MODE = 0
DOT_MATRIX_MODES = frozenset({1, 2, 3})  # a read reports any other dot-matrix mode as 0, as the vendor reads it
FIELDS = frozenset({"background", "text", "mode"})
BLACK = (0, 0, 0)


@dataclass(frozen=True)
class DotMatrix:
    background: tuple[int, int, int]
    text: tuple[int, int, int]
    type: int
    mode: int
    dot_matrix_mode: int


def decode(raw: bytes) -> DotMatrix:
    check_size("dot matrix", raw, SIZE)
    return DotMatrix(
        background=(raw[0], raw[1], raw[2]),
        text=(raw[3], raw[4], raw[5]),
        type=raw[6],
        mode=raw[7],
        dot_matrix_mode=raw[8] if raw[8] in DOT_MATRIX_MODES else 0,
    )


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Build the block from zeros. `raw` is checked for its size only: the vendor writer does not use the read."""
    check_size("dot matrix", raw, SIZE)
    check_fields(changes, FIELDS)
    mode = changes.get("mode", CHARACTER_MODE)
    check_range("mode", mode, 0, 3)
    out = bytearray(SIZE)
    if mode == CHARACTER_MODE:
        background = changes.get("background", BLACK)
        text = changes.get("text", BLACK)
        check_colour("background", background)
        check_colour("text", text)
        out[0:3] = bytes(background)
        out[3:6] = bytes(text)
    else:
        out[7] = mode
    return bytes(out)


BLOCK = Block("dot_matrix", 0x3D, 0x2A, SIZE, decode, encode_into)
