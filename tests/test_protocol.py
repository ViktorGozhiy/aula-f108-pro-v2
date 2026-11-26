import time

import pytest

from aula_f108.protocol import (
    ALLOWED_COMMANDS,
    CommandNotAllowed,
    Protocol,
    TransferError,
    bulk_header,
    check_allowed,
    reply_timeout,
    standard_header,
)
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard


def make_protocol(report_size=64):
    sim = SimulatedKeyboard(report_size)
    notifications = []
    return sim, Protocol(sim, notifications.append, time_scale=0.01), notifications


def headers(sim):
    return [packet[:8].hex(" ") for packet in sim.packets]


def test_standard_header():
    assert standard_header(0x10, 0x38, 0, True).hex(" ") == "aa 10 38 00 00 00 01 00"
    assert standard_header(0x22, 8, 0x1F8, True).hex(" ") == "aa 22 08 f8 01 00 01 00"
    assert standard_header(0x10, 0x18, 0x18, False).hex(" ") == "aa 10 18 18 00 00 00 00"


def test_bulk_header_vector_from_spec():
    # A 9-frame per-key animation on the cable: 4 + 972 * 3 = 2920 bytes in one 4096-byte chunk.
    assert bulk_header(0x42, 0, 2920, 4096).hex(" ") == "aa 42 00 00 00 01 00 00"


def test_bulk_header_high_bytes():
    assert bulk_header(0x41, 258, 7200, 24).hex(" ") == "aa 41 01 02 01 2d 00 00"


def test_bulk_header_n_plus_one_wraps_to_one_byte():
    assert bulk_header(0x41, 0, 255 * 24, 24).hex(" ") == "aa 41 00 00 00 00 00 00"


def test_bulk_header_refuses_other_commands():
    with pytest.raises(CommandNotAllowed):
        bulk_header(0x23, 0, 16, 4096)


@pytest.mark.parametrize("cmd", [0x11, 0x21, 0x25, 0x2A, 0x3D])
def test_long_timeout_commands(cmd):
    assert reply_timeout(cmd) == 2.0


@pytest.mark.parametrize("cmd", [0x10, 0x13, 0x23, 0x2B, 0x0F])
def test_short_timeout_commands(cmd):
    assert reply_timeout(cmd) == 0.5


def test_allow_list_is_the_spec_list():
    assert ALLOWED_COMMANDS == {
        0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x1B, 0x21, 0x22,
        0x23, 0x24, 0x25, 0x26, 0x2A, 0x2B, 0x3D, 0x41, 0x42,
    }
    for cmd in ALLOWED_COMMANDS:
        check_allowed(cmd)


@pytest.mark.parametrize("cmd", [0x0F, 0x1D, 0x2D, 0x34, 0x4F, 0x82, 0x85, 0x86, 0x90])
def test_transfers_refuse_commands_outside_the_allow_list(cmd):
    sim, protocol, _ = make_protocol()
    with pytest.raises(CommandNotAllowed):
        protocol.read_block(cmd, 24)
    with pytest.raises(CommandNotAllowed):
        protocol.write_block(cmd, bytes(24))
    assert sim.packets == []


def test_read_on_the_cable_is_one_packet():
    sim, protocol, _ = make_protocol(64)
    assert protocol.read_block(0x10, 56) == load_hex("wired-10.hex")
    assert headers(sim) == ["aa 10 38 00 00 00 01 00"]
    assert sim.packets[0][8:] == bytes(56)


def test_read_on_the_dongle_is_three_packets():
    sim, protocol, _ = make_protocol(32)
    assert protocol.read_block(0x10, 56) == load_hex("wired-10.hex")
    assert headers(sim) == [
        "aa 10 18 00 00 00 00 00",
        "aa 10 18 18 00 00 00 00",
        "aa 10 08 30 00 00 01 00",
    ]


def test_read_of_exact_multiple_flags_the_last_packet():
    sim, protocol, _ = make_protocol(32)
    protocol.read_block(0x11, 48)
    assert headers(sim) == ["aa 11 18 00 00 00 00 00", "aa 11 18 18 00 00 01 00"]


def test_write_on_the_cable_matches_vendor_example():
    sim, protocol, _ = make_protocol(64)
    data = bytes.fromhex("01ffffffff000000000503000000aa55")
    protocol.write_block(0x23, data)
    assert sim.packets == [bytes.fromhex("aa23100000000100") + data + bytes(40)]
    assert sim.blocks["led_effect"] == data


def test_write_on_the_dongle_is_chunked_by_address():
    sim, protocol, _ = make_protocol(32)
    data = bytes(range(56))
    protocol.write_block(0x21, data)
    assert headers(sim) == [
        "aa 21 18 00 00 00 00 00",
        "aa 21 18 18 00 00 00 00",
        "aa 21 08 30 00 00 01 00",
    ]
    assert sim.blocks["settings"] == data


def test_write_of_exact_multiple_flags_the_last_packet():
    sim, protocol, _ = make_protocol(32)
    protocol.write_block(0x21, bytes(48))
    assert headers(sim) == ["aa 21 18 00 00 00 00 00", "aa 21 18 18 00 00 01 00"]


def test_write_without_last_flag():
    sim, protocol, _ = make_protocol(32)
    protocol.write_block(0x21, bytes(56), last_flag=False)
    assert [packet[6] for packet in sim.packets] == [0, 0, 0]


def test_read_from_a_start_address_is_chunked_from_that_address():
    sim, protocol, _ = make_protocol(32)
    assert protocol.read_block(0x10, 40, addr=8) == load_hex("wired-10.hex")[8:48]
    assert headers(sim) == ["aa 10 18 08 00 00 00 00", "aa 10 10 20 00 00 01 00"]


def test_write_from_a_start_address_is_chunked_from_that_address():
    sim, protocol, _ = make_protocol(32)
    data = bytes(range(1, 41))
    protocol.write_block(0x21, data, addr=8)
    assert headers(sim) == ["aa 21 18 08 00 00 00 00", "aa 21 10 20 00 00 01 00"]
    assert sim.blocks["settings"][8:48] == data
    assert sim.blocks["settings"][:8] == load_hex("wired-11.hex")[:8]


def test_stale_reply_is_drained_before_the_request():
    sim, protocol, notifications = make_protocol()
    sim.push(bytes.fromhex("5513100000000100") + bytes(16))
    assert protocol.read_block(0x13, 16) == load_hex("wired-13.hex")
    assert notifications == []


def test_drained_notification_is_passed_on():
    sim, protocol, notifications = make_protocol()
    sim.push(bytes.fromhex("55fc06"))
    protocol.read_block(0x13, 16)
    assert [report[:3] for report in notifications] == [bytes.fromhex("55fc06")]


def test_notification_before_the_reply_is_passed_on():
    sim, protocol, notifications = make_protocol()
    sim.interject(bytes.fromhex("a6ff01"))
    assert protocol.read_block(0x13, 16) == load_hex("wired-13.hex")
    assert [report[:3] for report in notifications] == [bytes.fromhex("a6ff01")]


def test_other_reply_before_the_reply_is_skipped():
    sim, protocol, notifications = make_protocol()
    sim.interject(bytes.fromhex("5511380000000100"))
    assert protocol.read_block(0x13, 16) == load_hex("wired-13.hex")
    assert notifications == []


def test_report_with_another_first_byte_is_not_a_reply():
    sim, protocol, _ = make_protocol()
    sim.interject(bytes.fromhex("aa13000000000100"))
    assert protocol.read_block(0x13, 16) == load_hex("wired-13.hex")


def test_three_lost_replies_are_resent():
    sim, protocol, _ = make_protocol()
    sim.drop[0x13] = 3
    assert protocol.read_block(0x13, 16) == load_hex("wired-13.hex")
    assert len(sim.packets) == 4
    assert len(set(sim.packets)) == 1


def test_four_lost_replies_fail():
    sim, protocol, _ = make_protocol()
    sim.drop[0x13] = 4
    with pytest.raises(TransferError, match="0x13"):
        protocol.read_block(0x13, 16)
    assert len(sim.packets) == 4


class ChattyDevice:
    """Answers every wait with a notification and never with the reply."""

    report_size = 64

    def __init__(self):
        self.writes = 0

    def write(self, report):
        self.writes += 1

    def read(self, timeout):
        if timeout == 0:
            return None
        time.sleep(0.001)
        return bytes.fromhex("55fa01").ljust(64, b"\x00")


def test_wait_ends_at_the_deadline_while_other_reports_keep_coming():
    device = ChattyDevice()
    notifications = []
    protocol = Protocol(device, notifications.append, time_scale=0.01)
    with pytest.raises(TransferError):
        protocol.read_block(0x13, 16)
    assert device.writes == 4
    assert notifications


class ShortReplyDevice:
    report_size = 64

    def __init__(self):
        self.replies = []

    def write(self, report):
        self.replies.append(bytes.fromhex("5510380000000100") + bytes(2))

    def read(self, timeout):
        return self.replies.pop(0) if self.replies else None


def test_short_reply_fails():
    protocol = Protocol(ShortReplyDevice(), lambda report: None, time_scale=0.01)
    with pytest.raises(TransferError, match="short reply"):
        protocol.read_block(0x10, 56)


def test_poll_passes_a_notification_on():
    sim, protocol, notifications = make_protocol()
    sim.push(bytes.fromhex("55fc05"))
    protocol.poll(0)
    assert [report[:3] for report in notifications] == [bytes.fromhex("55fc05")]


def test_poll_ignores_other_reports_and_silence():
    sim, protocol, notifications = make_protocol()
    sim.push(bytes.fromhex("5513100000000100"))
    protocol.poll(0)
    protocol.poll(0)
    assert notifications == []


def test_factory_reset_sends_once_and_reports_the_reply():
    sim, protocol, _ = make_protocol()
    sim.blocks["settings"][3] = 9
    assert protocol.factory_reset() is True
    assert sim.packets == [bytes.fromhex("aa0fff0000000000") + bytes(56)]
    assert sim.blocks["settings"] == load_hex("wired-11.hex")


def test_factory_reset_waits_the_short_reply_timeout():
    class SilentDevice:
        report_size = 64

        def __init__(self):
            self.read_timeouts = []

        def write(self, report):
            pass

        def read(self, timeout):
            self.read_timeouts.append(timeout)
            return None

    device = SilentDevice()
    assert Protocol(device, lambda report: None, time_scale=1000).factory_reset() is False
    waited = max(device.read_timeouts)
    assert 400 < waited <= 500  # 0.5 s scaled by 1000, not the 2 s of the long timeout


def test_factory_reset_without_reply_is_not_resent():
    sim, protocol, _ = make_protocol()
    sim.drop[0x0F] = 1
    assert protocol.factory_reset() is False
    assert len(sim.packets) == 1
