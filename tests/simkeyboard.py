"""A keyboard simulated at the report level: it stores blocks, answers reads and applies writes."""
import threading

from aula_f108.hidraw import DeviceGone
from fixture_data import load_hex

READS = {
    0x10: "device_info", 0x11: "settings", 0x12: "base_keys", 0x13: "led_effect", 0x14: "key_colours",
    0x15: "macros", 0x16: "fn_keys", 0x1B: "light_box", 0x3D: "dot_matrix",
}
WRITES = {
    0x21: "settings", 0x22: "base_keys", 0x23: "led_effect", 0x24: "key_colours", 0x25: "macros", 0x26: "fn_keys",
    0x2A: "dot_matrix", 0x2B: "light_box",
}
BULK_UPLOADS = frozenset({0x41, 0x42})
FIXTURES = {
    "device_info": "wired-10.hex",
    "settings": "wired-11.hex",
    "led_effect": "wired-13.hex",
    "light_box": "wired-1B.hex",
    "key_colours": "wired-14.hex",
    "dot_matrix": "wired-3D.hex",
    "base_keys": "wired-12.hex",
    "fn_keys": "wired-16.hex",
    "macros": "wired-15.hex",
}
# The macro block is addressed like memory: the whole 16-bit address space, starting with the captured index.
MEMORY_SIZES = {"macros": 0x10000}
FACTORY_RESET = 0x0F
LIGHT_BOX_READ = 0x1B
LED_EFFECT_READ = 0x13
LED_EFFECT_WRITE = 0x23


class SimulatedKeyboard:
    """Implements the Device interface of aula_f108.protocol. Starts with the blocks captured from the cable."""

    def __init__(self, report_size: int = 64):
        self.report_size = report_size
        self.blocks = {
            name: bytearray(load_hex(fixture).ljust(MEMORY_SIZES.get(name, 0), b"\x00"))
            for name, fixture in FIXTURES.items()
        }
        self.factory = {name: bytes(block) for name, block in self.blocks.items()}
        self.packets = []   # every packet written to the keyboard
        self.writes = []    # (cmd, addr, data) of every write packet and of the factory reset
        self.uploads = []   # (cmd, chunk number, data) of every bulk upload packet
        self.drop = {}      # cmd -> number of packets of that command to leave unanswered
        self.led_effect_written = False  # a read of the LED effect reports its colour as ff ff ff after a host write
        self.silent = False
        self.gone = False   # every write and read raises DeviceGone
        self.closed = False
        self._interjected = []
        self._pending = []
        self._condition = threading.Condition()

    def write(self, report: bytes) -> None:
        assert len(report) == self.report_size
        if self.gone:
            raise DeviceGone("simulated unplug")
        with self._condition:
            self.packets.append(bytes(report))
            reply = self._answer(bytes(report))
            if reply is not None:
                self._pending.extend(self._interjected)
                self._interjected.clear()
                self._pending.append(reply.ljust(self.report_size, b"\x00"))
                self._condition.notify_all()

    def read(self, timeout: float) -> bytes | None:
        if self.gone:
            raise DeviceGone("simulated unplug")
        with self._condition:
            if not self._pending:
                self._condition.wait(max(timeout, 0))
            return self._pending.pop(0) if self._pending else None

    def push(self, report: bytes) -> None:
        """Send an unsolicited report, such as a notification."""
        with self._condition:
            self._pending.append(bytes(report).ljust(self.report_size, b"\x00"))
            self._condition.notify_all()

    def interject(self, report: bytes) -> None:
        """Send `report` just before the next reply."""
        self._interjected.append(bytes(report).ljust(self.report_size, b"\x00"))

    def choose_led_colour(self, colour: tuple[int, int, int]) -> None:
        """Choose the LED effect colour on the keyboard, as Fn+Tab does: reads report it until the next host write."""
        self.blocks["led_effect"][1:4] = bytes(colour)
        self.led_effect_written = False

    def close(self) -> None:
        self.closed = True

    def sent_commands(self) -> list[int]:
        return [packet[1] for packet in self.packets]

    def uploaded(self, cmd: int) -> bytes:
        """The data of every bulk upload packet of `cmd`, joined in order, padding included."""
        return b"".join(data for upload_cmd, _chunk, data in self.uploads if upload_cmd == cmd)

    def _answer(self, packet: bytes) -> bytes | None:
        cmd, length = packet[1], packet[2]
        addr = packet[3] | packet[4] << 8
        if self.silent:
            return None
        if self.drop.get(cmd, 0) > 0:
            self.drop[cmd] -= 1
            return None
        header = bytes([0x55, cmd, length, packet[3], packet[4], 0, packet[6], 0])
        if cmd in BULK_UPLOADS:
            self.uploads.append((cmd, packet[2] << 8 | packet[3], packet[8:]))
            return header
        if cmd in READS:
            data = bytearray(self.blocks[READS[cmd]][addr:addr + length])
            if cmd == LIGHT_BOX_READ and addr == 0:
                # The real keyboard always reports red and colourful 1, whatever was written.
                data[1:4] = b"\xff\x00\x00"
                data[8] = 1
            if cmd == LED_EFFECT_READ and addr == 0 and self.led_effect_written:
                # The real keyboard reports the colour as ff ff ff after any host write.
                data[1:4] = b"\xff\xff\xff"
            return header + bytes(data)
        if cmd in WRITES:
            data = packet[8:8 + length]
            self.blocks[WRITES[cmd]][addr:addr + length] = data
            self.writes.append((cmd, addr, data))
            if cmd == LED_EFFECT_WRITE:
                self.led_effect_written = True
            return header + data
        if cmd == FACTORY_RESET:
            self.blocks = {name: bytearray(block) for name, block in self.factory.items()}
            self.writes.append((cmd, 0, b""))
            return header
        return None
