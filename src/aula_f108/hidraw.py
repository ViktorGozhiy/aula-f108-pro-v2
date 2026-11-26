"""Access to the keyboard's hidraw interfaces: discovery through sysfs and raw report I/O."""

import fcntl
import os
import select
from dataclasses import dataclass
from pathlib import Path

INPUT_ITEM = 0x80
OUTPUT_ITEM = 0x90
READ_BUFFER = 8192


@dataclass(frozen=True)
class DescriptorInfo:
    usage_page: int
    usage: int
    input_size: int
    output_size: int


@dataclass(frozen=True)
class KnownDevice:
    vid: int
    pid: int
    connection: str
    command_usage_page: int
    bulk_usage_page: int | None  # None: bulk uploads go to the command interface


# The order is the probing order: when the keyboard answers on both, the cable is used.
KNOWN_DEVICES = (
    KnownDevice(0x38A6, 0x2739, "cable", 0xFF68, 0xFF67),
    KnownDevice(0x0C45, 0xFEFC, "dongle", 0xFF80, None),
)


@dataclass(frozen=True)
class CommandInterface:
    path: str
    connection: str
    report_size: int
    bulk_path: str | None = None  # the separate bulk upload interface; None: uploads use the command interface
    bulk_report_size: int = 0


class DeviceGone(Exception):
    """The hidraw node gave an I/O error: the device was unplugged or is resetting."""


class DeviceBusy(Exception):
    """Another process holds the exclusive lock on the hidraw node."""


def parse_report_descriptor(descriptor: bytes) -> DescriptorInfo:
    """Return the usage of the first top-level collection and the summed input and output report sizes in bytes."""
    usage_page = 0
    usage = 0
    report_size = 0
    report_count = 0
    top = None
    bits = {INPUT_ITEM: 0, OUTPUT_ITEM: 0}
    position = 0
    while position < len(descriptor):
        prefix = descriptor[position]
        if prefix == 0xFE:
            # Long item: a data size byte and a tag byte follow, then the data.
            position += 3 + descriptor[position + 1]
            continue
        size = (0, 1, 2, 4)[prefix & 0x03]
        value = int.from_bytes(descriptor[position + 1 : position + 1 + size], "little")
        position += 1 + size
        item = prefix & 0xFC
        if item == 0x04:
            usage_page = value
        elif item == 0x08:
            usage = value
        elif item == 0x74:
            report_size = value
        elif item == 0x94:
            report_count = value
        elif item == 0xA0 and top is None:
            top = (usage_page, usage)
        elif item in bits:
            bits[item] += report_size * report_count
    if top is None:
        raise ValueError("report descriptor has no collection")
    return DescriptorInfo(top[0], top[1], bits[INPUT_ITEM] // 8, bits[OUTPUT_ITEM] // 8)


def _hid_id(uevent: str) -> tuple[int, int] | None:
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            _bus, vid, pid = line.removeprefix("HID_ID=").split(":")
            return int(vid, 16), int(pid, 16)
    return None


def find_command_interfaces(sysfs_root: str = "/sys/class/hidraw", dev_root: str = "/dev") -> list[CommandInterface]:
    """List the command interfaces of the known devices, cable first, each with its bulk upload interface if any.

    The bulk interface is matched by VID and PID, so one keyboard of each kind is supported.
    """
    root = Path(sysfs_root)
    if not root.is_dir():
        return []
    commands = []
    bulk = {}
    for entry in root.iterdir():
        try:
            ids = _hid_id((entry / "device" / "uevent").read_text())
            descriptor = (entry / "device" / "report_descriptor").read_bytes()
        except OSError:
            continue  # the device went away during the walk
        for rank, known in enumerate(KNOWN_DEVICES):
            if ids != (known.vid, known.pid):
                continue
            info = parse_report_descriptor(descriptor)
            path = os.path.join(dev_root, entry.name)
            if info.usage_page == known.command_usage_page:
                commands.append((rank, entry.name, path, known.connection, info.output_size))
            elif info.usage_page == known.bulk_usage_page:
                bulk[rank] = (path, info.output_size)
    commands.sort(key=lambda item: (item[0], item[1]))
    return [
        CommandInterface(path, connection, size, *bulk.get(rank, (None, 0)))
        for rank, _name, path, connection, size in commands
    ]


class HidrawDevice:
    """One open hidraw node. Reports carry no report number, so every write starts with the byte 0x00."""

    def __init__(self, path: str, report_size: int):
        self.path = path
        self.report_size = report_size
        self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._fd)
            raise DeviceBusy(path) from None

    def write(self, report: bytes) -> None:
        if len(report) != self.report_size:
            raise ValueError(f"report must be {self.report_size} bytes, got {len(report)}")
        try:
            os.write(self._fd, b"\x00" + bytes(report))
        except OSError as error:
            raise DeviceGone(f"{self.path}: {error.strerror}") from error

    def read(self, timeout: float) -> bytes | None:
        """Return one input report, or None when none arrives within `timeout` seconds."""
        ready, _, _ = select.select([self._fd], [], [], max(timeout, 0))
        if not ready:
            return None
        try:
            return os.read(self._fd, READ_BUFFER)
        except BlockingIOError:
            return None
        except OSError as error:
            raise DeviceGone(f"{self.path}: {error.strerror}") from error

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
