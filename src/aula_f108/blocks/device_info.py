"""GET_DEVICE_INFO (0x10): identity, firmware version, battery and frame limits. Read only."""
from dataclasses import dataclass

from aula_f108.blocks import Block, check_size

SIZE = 56
CHARGING_STATUSES = frozenset({1, 2})


@dataclass(frozen=True)
class DeviceInfo:
    vid: int
    pid: int
    firmware: str
    work_mode: int
    battery: int
    charge_status: int
    gif_max_frames: int
    led_max_frames: int

    @property
    def charging(self) -> bool:
        return self.charge_status in CHARGING_STATUSES


def decode(raw: bytes) -> DeviceInfo:
    check_size("device info", raw, SIZE)
    version = (raw[8] & 0x0F) + (raw[8] >> 4) * 10 + raw[9] * 100
    return DeviceInfo(
        vid=int.from_bytes(raw[4:6], "little"),
        pid=int.from_bytes(raw[6:8], "little"),
        firmware=f"{version // 100}.{version % 100:02d}",
        work_mode=raw[16],
        battery=raw[17],
        charge_status=raw[18],
        gif_max_frames=int.from_bytes(raw[24:26], "little"),
        led_max_frames=int.from_bytes(raw[26:28], "little"),
    )


BLOCK = Block("device_info", 0x10, None, SIZE, decode, None)
