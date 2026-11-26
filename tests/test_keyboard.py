import pytest

from aula_f108.blocks import device_info, light_box, settings
from aula_f108.keyboard import BLOCKS, Keyboard
from aula_f108.protocol import Protocol
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard


def make_keyboard(report_size=64):
    sim = SimulatedKeyboard(report_size)
    return sim, Keyboard(Protocol(sim, lambda report: None, time_scale=0.01))


def test_blocks_in_read_order():
    assert list(BLOCKS) == [
        "device_info",
        "settings",
        "led_effect",
        "light_box",
        "key_colours",
        "dot_matrix",
        "base_keys",
        "fn_keys",
        "macros",
    ]


@pytest.mark.parametrize(
    ("name", "fixture"),
    [
        ("device_info", "wired-10.hex"),
        ("settings", "wired-11.hex"),
        ("led_effect", "wired-13.hex"),
        ("key_colours", "wired-14.hex"),
        ("dot_matrix", "wired-3D.hex"),
        ("base_keys", "wired-12.hex"),
        ("fn_keys", "wired-16.hex"),
        ("macros", "wired-15.hex"),
    ],
)
def test_reads_every_block(name, fixture):
    _sim, keyboard = make_keyboard()
    assert keyboard.read(BLOCKS[name]) == load_hex(fixture)


def test_light_box_read_reports_red_and_colourful():
    sim, keyboard = make_keyboard()
    sim.blocks["light_box"][1:4] = b"\x00\x00\xff"
    sim.blocks["light_box"][8] = 0
    assert light_box.decode(keyboard.read(BLOCKS["light_box"])).colour == (255, 0, 0)


def test_changes_are_written_onto_a_fresh_read():
    sim, keyboard = make_keyboard()
    sim.blocks["settings"][4] = 5  # changed on the keyboard, for example by an Fn combination
    written = keyboard.read_with_changes(BLOCKS["settings"], {"sleep_minutes": 10})
    keyboard.write(BLOCKS["settings"], written)
    assert settings.decode(written).debounce == 5
    assert settings.decode(written).sleep_minutes == 10
    assert bytes(sim.blocks["settings"]) == written
    assert sim.sent_commands() == [0x11, 0x21]


def test_read_with_changes_writes_nothing():
    sim, keyboard = make_keyboard()
    changed = keyboard.read_with_changes(BLOCKS["settings"], {"debounce": 2})
    assert changed == settings.encode_into(load_hex("wired-11.hex"), {"debounce": 2})
    assert bytes(sim.blocks["settings"]) == load_hex("wired-11.hex")
    assert sim.sent_commands() == [0x11]


def test_changes_are_written_on_the_dongle():
    sim, keyboard = make_keyboard(32)
    keyboard.write(BLOCKS["led_effect"], keyboard.read_with_changes(BLOCKS["led_effect"], {"brightness": 2}))
    assert sim.blocks["led_effect"][9] == 2
    assert sim.sent_commands() == [0x13, 0x23]


def test_device_info_cannot_be_written():
    sim, keyboard = make_keyboard()
    with pytest.raises(ValueError, match="device_info cannot be written"):
        keyboard.read_with_changes(device_info.BLOCK, {})
    with pytest.raises(ValueError, match="device_info cannot be written"):
        keyboard.write(device_info.BLOCK, bytes(56))
    assert sim.packets == []


def test_factory_reset():
    sim, keyboard = make_keyboard()
    assert keyboard.factory_reset() is True
    assert sim.writes == [(0x0F, 0, b"")]
