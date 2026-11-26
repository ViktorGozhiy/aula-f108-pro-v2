import pytest

from aula_f108.blocks import led_effect, light_box
from aula_f108.blocks.led_effect import LedEffect
from aula_f108.blocks.light_box import LightBox
from fixture_data import load_hex


def changed_bytes(before: bytes, after: bytes) -> dict:
    return {index: after[index] for index in range(len(before)) if before[index] != after[index]}


# Bytes 4 and 14-15 read as 0 and are always written as FF and AA 55.
FIXED_LED_BYTES = {4: 0xFF, 14: 0xAA, 15: 0x55}


def test_led_effect_decodes_the_cable_read():
    assert led_effect.decode(load_hex("wired-13.hex")) == LedEffect(
        mode=1, colour=(0, 255, 255), colourful=False, brightness=5, speed=3, direction=0,
    )


def test_led_effect_no_changes_sets_only_the_fixed_bytes():
    raw = load_hex("wired-13.hex")
    assert changed_bytes(raw, led_effect.encode_into(raw, {})) == FIXED_LED_BYTES


def test_led_effect_matches_vendor_example():
    written = led_effect.encode_into(bytes(16), {"mode": 1, "colour": (255, 255, 255), "brightness": 5, "speed": 3})
    assert written.hex(" ") == "01 ff ff ff ff 00 00 00 00 05 03 00 00 00 aa 55"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"mode": 7}, {0: 7}),
        ({"colour": (1, 2, 3)}, {1: 1, 2: 2, 3: 3}),
        ({"colourful": True}, {8: 1}),
        ({"brightness": 2}, {9: 2}),
        ({"speed": 1}, {10: 1}),
        ({"direction": 1}, {11: 1}),
    ],
)
def test_led_effect_writes_only_the_changed_field(changes, expected):
    raw = load_hex("wired-13.hex")
    assert changed_bytes(raw, led_effect.encode_into(raw, changes)) == expected | FIXED_LED_BYTES


def test_led_effect_keeps_unmodelled_bytes():
    raw = bytes(range(16))
    written = led_effect.encode_into(raw, {"brightness": 3})
    assert written[5:8] == raw[5:8]
    assert written[12:14] == raw[12:14]


def test_led_effect_colourful_off():
    raw = bytearray(load_hex("wired-13.hex"))
    raw[8] = 1
    assert led_effect.encode_into(bytes(raw), {"colourful": False})[8] == 0


@pytest.mark.parametrize("mode", [6, 8])
def test_led_effect_forced_colourful_modes(mode):
    raw = load_hex("wired-13.hex")
    assert led_effect.encode_into(raw, {"mode": mode, "colourful": False})[8] == 1


def test_led_effect_forced_colourful_follows_the_current_mode():
    raw = bytearray(load_hex("wired-13.hex"))
    raw[0] = 8
    raw[8] = 1
    assert led_effect.encode_into(bytes(raw), {"colourful": False})[8] == 1


def test_led_effect_other_mode_is_not_forced():
    raw = load_hex("wired-13.hex")
    assert led_effect.encode_into(raw, {"mode": 7, "colourful": False})[8] == 0


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("brightness", (1, 5), (0, 6)),
        ("speed", (0, 5), (-1, 6)),
        ("direction", (0, 1), (-1, 2)),
    ],
)
def test_led_effect_range_boundaries(field, good, bad):
    raw = load_hex("wired-13.hex")
    for value in good:
        led_effect.encode_into(raw, {field: value})
    for value in bad:
        with pytest.raises(ValueError, match=field):
            led_effect.encode_into(raw, {field: value})


@pytest.mark.parametrize("mode", [0, 19, 20, 0xFF])
def test_led_effect_writable_modes(mode):
    assert led_effect.encode_into(load_hex("wired-13.hex"), {"mode": mode})[0] == mode


@pytest.mark.parametrize("mode", [21, 0x55, 0xFE])
def test_led_effect_refuses_other_modes(mode):
    with pytest.raises(ValueError, match="cannot be written"):
        led_effect.encode_into(load_hex("wired-13.hex"), {"mode": mode})


def test_led_effect_refuses_bad_colour_and_unknown_field():
    raw = load_hex("wired-13.hex")
    with pytest.raises(ValueError, match="colour"):
        led_effect.encode_into(raw, {"colour": (256, 0, 0)})
    with pytest.raises(ValueError, match="unknown fields"):
        led_effect.encode_into(raw, {"secondary": (0, 0, 0)})


def test_light_box_decodes_the_cable_read():
    assert light_box.decode(load_hex("wired-1B.hex")) == LightBox(
        mode=1, colour=(255, 0, 0), colourful=True, brightness=2, speed=5,
    )


@pytest.mark.parametrize(("mode", "colourful"), [(1, 1), (2, 0), (3, 0), (4, 1), (7, 1)])
def test_light_box_colourful_flag_follows_the_mode(mode, colourful):
    written = light_box.encode_into(load_hex("wired-1B.hex"), {"mode": mode})
    assert written[0] == mode
    assert written[8] == colourful


def test_light_box_flag_follows_the_current_mode_when_mode_is_unchanged():
    raw = bytearray(load_hex("wired-1B.hex"))
    raw[0] = 2
    assert light_box.encode_into(bytes(raw), {"brightness": 4})[8] == 0


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"colour": (0, 255, 0)}, {1: 0, 2: 255}),
        ({"brightness": 4}, {9: 4}),
        ({"speed": 1}, {10: 1}),
    ],
)
def test_light_box_writes_only_the_changed_field(changes, expected):
    raw = load_hex("wired-1B.hex")
    assert changed_bytes(raw, light_box.encode_into(raw, changes)) == expected


def test_light_box_keeps_unmodelled_bytes():
    raw = bytes([1]) + bytes(range(1, 24))
    written = light_box.encode_into(raw, {"brightness": 3})
    assert written[4:8] == raw[4:8]
    assert written[11:] == raw[11:]


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("mode", (1, 7), (0, 8)),
        ("brightness", (1, 5), (0, 6)),
        ("speed", (1, 5), (0, 6)),
    ],
)
def test_light_box_range_boundaries(field, good, bad):
    raw = load_hex("wired-1B.hex")
    for value in good:
        light_box.encode_into(raw, {field: value})
    for value in bad:
        with pytest.raises(ValueError, match=field):
            light_box.encode_into(raw, {field: value})


def test_light_box_refuses_colourful_as_a_field_and_bad_colour():
    raw = load_hex("wired-1B.hex")
    with pytest.raises(ValueError, match="unknown fields: colourful"):
        light_box.encode_into(raw, {"colourful": False})
    with pytest.raises(ValueError, match="three components"):
        light_box.encode_into(raw, {"colour": (1, 2)})
