"""GET / SET_LIGHT_BOX (0x1B / 0x2B): the light strip around the keyboard.

A read always reports red and colourful 1, so the colour the keyboard shows cannot be read back.
"""
from dataclasses import dataclass

from aula_f108.blocks import Block, check_colour, check_fields, check_range, check_size

SIZE = 24
COLOUR_MODES = frozenset({2, 3})  # the colour applies and the colourful flag is 0
FIELDS = frozenset({"mode", "colour", "brightness", "speed"})


@dataclass(frozen=True)
class LightBox:
    mode: int
    colour: tuple[int, int, int]
    colourful: bool
    brightness: int
    speed: int


def decode(raw: bytes) -> LightBox:
    check_size("light box", raw, SIZE)
    return LightBox(
        mode=raw[0],
        colour=(raw[1], raw[2], raw[3]),
        colourful=raw[8] == 1,
        brightness=raw[9],
        speed=raw[10],
    )


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Write the changed fields onto `raw` and set the colourful flag from the mode, as the vendor does."""
    check_size("light box", raw, SIZE)
    check_fields(changes, FIELDS)
    out = bytearray(raw)
    if "mode" in changes:
        check_range("mode", changes["mode"], 1, 7)
        out[0] = changes["mode"]
    if "colour" in changes:
        check_colour("colour", changes["colour"])
        out[1:4] = bytes(changes["colour"])
    if "brightness" in changes:
        check_range("brightness", changes["brightness"], 1, 5)
        out[9] = changes["brightness"]
    if "speed" in changes:
        check_range("speed", changes["speed"], 1, 5)
        out[10] = changes["speed"]
    out[8] = 0 if out[0] in COLOUR_MODES else 1
    return bytes(out)


BLOCK = Block("light_box", 0x1B, 0x2B, SIZE, decode, encode_into)
