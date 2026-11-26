import pytest

from aula_f108.blocks import check_colour, check_fields, check_range, check_size
from aula_f108.blocks import device_info, settings
from aula_f108.blocks.device_info import DeviceInfo
from aula_f108.blocks.settings import Settings
from fixture_data import load_hex


def changed_bytes(before: bytes, after: bytes) -> dict:
    return {index: after[index] for index in range(len(before)) if before[index] != after[index]}


def test_check_size():
    check_size("x", bytes(4), 4)
    with pytest.raises(ValueError, match="4 bytes, got 3"):
        check_size("x", bytes(3), 4)


def test_check_fields():
    check_fields({"a": 1}, frozenset({"a", "b"}))
    with pytest.raises(ValueError, match="unknown fields: c"):
        check_fields({"a": 1, "c": 2}, frozenset({"a", "b"}))


def test_check_range_boundaries():
    check_range("x", 1, 1, 5)
    check_range("x", 5, 1, 5)
    with pytest.raises(ValueError, match="1..5, got 0"):
        check_range("x", 0, 1, 5)
    with pytest.raises(ValueError, match="got 6"):
        check_range("x", 6, 1, 5)


def test_check_colour():
    check_colour("colour", (0, 128, 255))
    with pytest.raises(ValueError, match="three components"):
        check_colour("colour", (0, 128))
    with pytest.raises(ValueError, match="got 256"):
        check_colour("colour", (0, 256, 0))
    with pytest.raises(ValueError, match="got -1"):
        check_colour("colour", (-1, 0, 0))


def test_device_info_decodes_the_cable_read():
    assert device_info.decode(load_hex("wired-10.hex")) == DeviceInfo(
        vid=0x38A6, pid=0x2739, firmware="1.33", work_mode=0x19, battery=0,
        charge_status=1, gif_max_frames=512, led_max_frames=512,
    )


def test_device_info_frame_limits_come_from_their_own_bytes():
    raw = bytearray(load_hex("wired-10.hex"))
    raw[24:28] = (300).to_bytes(2, "little") + (700).to_bytes(2, "little")
    info = device_info.decode(bytes(raw))
    assert (info.gif_max_frames, info.led_max_frames) == (300, 700)


def test_device_info_firmware_keeps_two_digits():
    raw = bytearray(load_hex("wired-10.hex"))
    raw[8:10] = b"\x05\x02"
    assert device_info.decode(bytes(raw)).firmware == "2.05"


@pytest.mark.parametrize(("status", "charging"), [(0, False), (1, True), (2, True), (3, False)])
def test_device_info_charging(status, charging):
    raw = bytearray(load_hex("wired-10.hex"))
    raw[18] = status
    assert device_info.decode(bytes(raw)).charging is charging


def test_device_info_rejects_wrong_size():
    with pytest.raises(ValueError):
        device_info.decode(bytes(24))


def test_device_info_is_read_only():
    assert device_info.BLOCK.write_cmd is None
    assert device_info.BLOCK.read_cmd == 0x10


def test_settings_decodes_the_cable_read():
    assert settings.decode(load_hex("wired-11.hex")) == Settings(
        win_lock=False, sleep_minutes=1, debounce=3, polling_rate=6, mac_mode=False,
    )


def test_settings_polling_rates():
    assert settings.POLLING_RATES_HZ[0] == 125
    assert settings.POLLING_RATES_HZ[6] == 8000


def test_settings_no_changes_keeps_every_byte():
    raw = bytes(range(56))
    assert settings.encode_into(raw, {}) == raw


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"sleep_minutes": 10}, {3: 10}),
        ({"debounce": 5}, {4: 5}),
        ({"polling_rate": 3}, {5: 3}),
        ({"mac_mode": True}, {6: 1}),
        ({"win_lock": True}, {1: 1}),
    ],
)
def test_settings_writes_only_the_changed_field(changes, expected):
    raw = load_hex("wired-11.hex")
    assert changed_bytes(raw, settings.encode_into(raw, changes)) == expected


def test_settings_mac_mode_off():
    raw = bytearray(load_hex("wired-11.hex"))
    raw[6] = 1
    assert settings.encode_into(bytes(raw), {"mac_mode": False})[6] == 0


def test_settings_win_lock_keeps_alt_bits():
    raw = bytearray(56)
    raw[1] = 0b110
    assert settings.encode_into(bytes(raw), {"win_lock": True})[1] == 0b111
    raw[1] = 0b111
    assert settings.encode_into(bytes(raw), {"win_lock": False})[1] == 0b110


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("sleep_minutes", (0, 30), (-1, 31)),
        ("debounce", (1, 5), (0, 6)),
        ("polling_rate", (0, 6), (-1, 7)),
    ],
)
def test_settings_range_boundaries(field, good, bad):
    raw = load_hex("wired-11.hex")
    for value in good:
        settings.encode_into(raw, {field: value})
    for value in bad:
        with pytest.raises(ValueError, match=field):
            settings.encode_into(raw, {field: value})


def test_settings_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown fields: wireless_rate"):
        settings.encode_into(load_hex("wired-11.hex"), {"wireless_rate": 1})


def test_settings_rejects_wrong_size():
    with pytest.raises(ValueError):
        settings.encode_into(bytes(24), {})
    with pytest.raises(ValueError):
        settings.decode(bytes(24))
