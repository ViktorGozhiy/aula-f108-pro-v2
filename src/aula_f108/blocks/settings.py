"""GET / SET_GAME_MODE (0x11 / 0x21): Win lock, sleep, debounce, cable polling rate, Win/Mac mode."""
from dataclasses import dataclass

from aula_f108.blocks import Block, check_fields, check_range, check_size

SIZE = 56
POLLING_RATES_HZ = (125, 250, 500, 1000, 2000, 4000, 8000)
WIN_LOCK_BIT = 0x01
FIELDS = frozenset({"win_lock", "sleep_minutes", "debounce", "polling_rate", "mac_mode"})


@dataclass(frozen=True)
class Settings:
    win_lock: bool
    sleep_minutes: int  # 0 = never
    debounce: int
    polling_rate: int  # index into POLLING_RATES_HZ
    mac_mode: bool


def decode(raw: bytes) -> Settings:
    check_size("settings", raw, SIZE)
    return Settings(
        win_lock=bool(raw[1] & WIN_LOCK_BIT),
        sleep_minutes=raw[3],
        debounce=raw[4],
        polling_rate=raw[5],
        mac_mode=raw[6] == 1,
    )


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Write the changed fields onto `raw`. Byte 1 keeps its Alt+Tab and Alt+F4 bits."""
    check_size("settings", raw, SIZE)
    check_fields(changes, FIELDS)
    out = bytearray(raw)
    if "win_lock" in changes:
        out[1] = (out[1] & ~WIN_LOCK_BIT & 0xFF) | (WIN_LOCK_BIT if changes["win_lock"] else 0)
    if "sleep_minutes" in changes:
        check_range("sleep_minutes", changes["sleep_minutes"], 0, 30)
        out[3] = changes["sleep_minutes"]
    if "debounce" in changes:
        check_range("debounce", changes["debounce"], 1, 5)
        out[4] = changes["debounce"]
    if "polling_rate" in changes:
        check_range("polling_rate", changes["polling_rate"], 0, len(POLLING_RATES_HZ) - 1)
        out[5] = changes["polling_rate"]
    if "mac_mode" in changes:
        out[6] = 1 if changes["mac_mode"] else 0
    return bytes(out)


BLOCK = Block("settings", 0x11, 0x21, SIZE, decode, encode_into)
