"""Packet framing of the hfd protocol: headers, chunked transfers, reply matching and resends."""

import math
import time
from collections.abc import Callable
from typing import Protocol as DeviceProtocol

HEADER_SIZE = 8
RESENDS = 3
SHORT_TIMEOUT = 0.5
LONG_TIMEOUT = 2.0
LONG_TIMEOUT_COMMANDS = frozenset({0x11, 0x21, 0x25, 0x2A, 0x3D})
# Every command the application sends through the general path. Factory reset has its own method.
ALLOWED_COMMANDS = frozenset(
    {
        0x10,
        0x11,
        0x12,
        0x13,
        0x14,
        0x15,
        0x16,
        0x1B,
        0x21,
        0x22,
        0x23,
        0x24,
        0x25,
        0x26,
        0x2A,
        0x2B,
        0x3D,
        0x41,
        0x42,
    }
)
BULK_COMMANDS = frozenset({0x41, 0x42})
FACTORY_RESET = 0x0F
FACTORY_RESET_ALL = 0xFF
NOTIFICATION_PREFIXES = (b"\x55\xfc", b"\x55\xfa", b"\xa6\xff")
MAX_CHUNKS = 0x10000  # the chunk number of a bulk header is 16 bits


class Device(DeviceProtocol):
    report_size: int

    def write(self, report: bytes) -> None: ...

    def read(self, timeout: float) -> bytes | None: ...


class CommandNotAllowed(ValueError):
    """The command ID is not one the application sends."""


class TransferError(Exception):
    """The keyboard did not answer a packet after all resends, or answered with a short reply."""


def check_allowed(cmd: int) -> None:
    if cmd not in ALLOWED_COMMANDS:
        raise CommandNotAllowed(f"command 0x{cmd:02X} is not allowed")


def standard_header(cmd: int, length: int, addr: int, last: bool) -> bytes:
    return bytes([0xAA, cmd, length, addr & 0xFF, (addr >> 8) & 0xFF, 0, 1 if last else 0, 0])


def bulk_header(cmd: int, chunk: int, payload_length: int, chunk_size: int) -> bytes:
    """Header of a bulk upload packet (0x41, 0x42), as the vendor code builds it.

    Bytes 4-5 hold n = floor(payload_length / chunk_size) and (n + 1) & 0xFF; n is not the chunk count.
    """
    if cmd not in BULK_COMMANDS:
        raise CommandNotAllowed(f"command 0x{cmd:02X} is not a bulk upload")
    n = payload_length // chunk_size
    return bytes([0xAA, cmd, (chunk >> 8) & 0xFF, chunk & 0xFF, (n >> 8) & 0xFF, (n + 1) & 0xFF, 0, 0])


def chunk_count(payload_length: int, chunk_size: int) -> int:
    """Number of chunks of a bulk upload. Every chunk, the last included, is padded to `chunk_size` bytes."""
    if payload_length == 0:
        raise ValueError("a bulk upload needs data")
    chunks = math.ceil(payload_length / chunk_size)
    if chunks > MAX_CHUNKS:
        raise ValueError(f"a bulk upload takes at most {MAX_CHUNKS} chunks, got {chunks}")
    return chunks


def reply_timeout(cmd: int) -> float:
    return LONG_TIMEOUT if cmd in LONG_TIMEOUT_COMMANDS else SHORT_TIMEOUT


def is_notification(report: bytes) -> bool:
    return bytes(report[:2]) in NOTIFICATION_PREFIXES


class Protocol:
    """Transfers over one command interface. Notifications read on the way go to `on_notification`."""

    def __init__(self, device: Device, on_notification: Callable[[bytes], None], time_scale: float = 1.0):
        self.device = device
        self._on_notification = on_notification
        self._time_scale = time_scale

    @property
    def data_size(self) -> int:
        return self.device.report_size - HEADER_SIZE

    def poll(self, timeout: float) -> None:
        """Read at most one report outside a transfer and pass a notification on."""
        report = self.device.read(timeout)
        if report is not None:
            self._pass_on(report)

    def read_block(self, cmd: int, size: int, addr: int = 0) -> bytes:
        check_allowed(cmd)
        data = bytearray()
        for offset in range(0, size, self.data_size):
            length = min(self.data_size, size - offset)
            last = offset + length == size
            reply = self._exchange(self._packet(standard_header(cmd, length, addr + offset, last)), cmd)
            if len(reply) < HEADER_SIZE + length:
                raise TransferError(f"short reply to command 0x{cmd:02X}: {len(reply)} bytes")
            data += reply[HEADER_SIZE : HEADER_SIZE + length]
        return bytes(data)

    def write_block(self, cmd: int, data: bytes, addr: int = 0, last_flag: bool = True) -> None:
        check_allowed(cmd)
        for offset in range(0, len(data), self.data_size):
            piece = data[offset : offset + self.data_size]
            last = last_flag and offset + len(piece) == len(data)
            self._exchange(self._packet(standard_header(cmd, len(piece), addr + offset, last), piece), cmd)

    def upload(
        self,
        cmd: int,
        payload: bytes,
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        """Send a bulk upload (0x41, 0x42) in chunks of `data_size` bytes, each zero-padded, waiting for each reply.

        `progress(sent, total)` is called after each chunk. `cancelled()` is asked before each chunk; when it returns
        True the upload stops. Returns True when every chunk was sent and False when the upload was cancelled.
        """
        if cmd not in BULK_COMMANDS:
            raise CommandNotAllowed(f"command 0x{cmd:02X} is not a bulk upload")
        size = self.data_size
        total = chunk_count(len(payload), size)
        for chunk in range(total):
            if cancelled is not None and cancelled():
                return False
            piece = bytes(payload[chunk * size : (chunk + 1) * size]).ljust(size, b"\x00")
            self._exchange(self._packet(bulk_header(cmd, chunk, len(payload), size), piece), cmd)
            if progress is not None:
                progress(chunk + 1, total)
        return True

    def factory_reset(self) -> bool:
        """Send the full factory reset once, without resends, and report whether the keyboard replied."""
        self._drain()
        self.device.write(self._packet(standard_header(FACTORY_RESET, FACTORY_RESET_ALL, 0, False)))
        return self._wait_reply(FACTORY_RESET, reply_timeout(FACTORY_RESET)) is not None

    def _packet(self, header: bytes, data: bytes = b"") -> bytes:
        return (header + bytes(data)).ljust(self.device.report_size, b"\x00")

    def _exchange(self, packet: bytes, cmd: int) -> bytes:
        timeout = reply_timeout(cmd)
        for _attempt in range(1 + RESENDS):
            self._drain()
            self.device.write(packet)
            reply = self._wait_reply(cmd, timeout)
            if reply is not None:
                return reply
        raise TransferError(f"no reply to command 0x{cmd:02X} after {RESENDS} resends")

    def _wait_reply(self, cmd: int, timeout: float) -> bytes | None:
        deadline = time.monotonic() + timeout * self._time_scale
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            report = self.device.read(remaining)
            if report is None:
                return None
            if report[0] == 0x55 and report[1] == cmd:
                return report
            self._pass_on(report)

    def _drain(self) -> None:
        """Take the stale reports waiting before a request."""
        while (report := self.device.read(0)) is not None:
            self._pass_on(report)

    def _pass_on(self, report: bytes) -> None:
        if is_notification(report):
            self._on_notification(bytes(report))
