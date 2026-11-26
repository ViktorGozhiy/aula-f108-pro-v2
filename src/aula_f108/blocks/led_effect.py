"""GET / SET_LED_EFFECT (0x13 / 0x23): the main backlight effect.

A read reports the colour chosen on the keyboard with Fn+Tab. After a host write it reports the colour as
ff ff ff, whatever was written. So a colour other than ff ff ff is the colour the keys show, and ff ff ff means
the host set the colour (or it is white). Mode, colourful flag, brightness, speed and direction are reported as
written.
"""

from dataclasses import dataclass

from aula_f108.blocks import Block, check_colour, check_fields, check_range, check_size

SIZE = 16
PER_KEY_MODE = 20  # the mode the per-key colours page writes
PER_KEY_MODES = frozenset({PER_KEY_MODE, 0x55})  # a read reports per-key colours as 20 or 0x55
ANIMATION_MODE = 0xFF
WRITABLE_MODES = frozenset(range(21)) | {ANIMATION_MODE}
FORCED_COLOURFUL_MODES = frozenset({6, 8})
FIELDS = frozenset({"mode", "colour", "colourful", "brightness", "speed", "direction"})
# The LED effect the vendor writes before a per-key animation upload.
ANIMATION_SETUP = {
    "mode": ANIMATION_MODE,
    "colour": (255, 0, 0),
    "colourful": False,
    "brightness": 5,
    "speed": 0,
    "direction": 0,
}


@dataclass(frozen=True)
class LedEffect:
    mode: int
    colour: tuple[int, int, int]
    colourful: bool
    brightness: int
    speed: int
    direction: int


def decode(raw: bytes) -> LedEffect:
    check_size("LED effect", raw, SIZE)
    return LedEffect(
        mode=raw[0],
        colour=(raw[1], raw[2], raw[3]),
        colourful=raw[8] == 1,
        brightness=raw[9],
        speed=raw[10],
        direction=raw[11],
    )


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Write the changed fields onto `raw`. Bytes 4 and 14-15 get the values the vendor writer puts there."""
    check_size("LED effect", raw, SIZE)
    check_fields(changes, FIELDS)
    out = bytearray(raw)
    if "colour" in changes:
        check_colour("colour", changes["colour"])
        out[1:4] = bytes(changes["colour"])
    if "colourful" in changes:
        out[8] = 1 if changes["colourful"] else 0
    if "brightness" in changes:
        check_range("brightness", changes["brightness"], 1, 5)
        out[9] = changes["brightness"]
    if "speed" in changes:
        check_range("speed", changes["speed"], 0, 5)
        out[10] = changes["speed"]
    if "direction" in changes:
        check_range("direction", changes["direction"], 0, 1)
        out[11] = changes["direction"]
    if "mode" in changes:
        if changes["mode"] not in WRITABLE_MODES:
            raise ValueError(f"mode {changes['mode']} cannot be written")
        out[0] = changes["mode"]
    if out[0] in FORCED_COLOURFUL_MODES:
        out[8] = 1
    out[4] = 0xFF
    out[14:16] = b"\xaa\x55"
    return bytes(out)


BLOCK = Block("led_effect", 0x13, 0x23, SIZE, decode, encode_into)
