import pytest

from aula_f108.protocol import MAX_CHUNKS, CommandNotAllowed, Protocol, TransferError, chunk_count
from simkeyboard import SimulatedKeyboard

SPEC_VECTOR = bytes(range(256)) * 11 + bytes(104)  # 2920 bytes: a 9-frame per-key animation (4 + 972 * 3)


def make_protocol(report_size):
    sim = SimulatedKeyboard(report_size)
    return sim, Protocol(sim, lambda report: None, time_scale=0.01)


def test_nine_frame_key_animation_is_one_chunk_on_the_cable_bulk_interface():
    sim, protocol = make_protocol(4104)
    assert protocol.upload(0x42, SPEC_VECTOR) is True
    assert len(sim.packets) == 1
    packet = sim.packets[0]
    assert len(packet) == 4104
    assert packet[:8].hex(" ") == "aa 42 00 00 00 01 00 00"
    assert packet[8:8 + 2920] == SPEC_VECTOR
    assert packet[8 + 2920:] == bytes(4096 - 2920)


def test_dongle_sends_24_byte_chunks_with_the_vendor_header():
    sim, protocol = make_protocol(32)
    assert protocol.upload(0x42, SPEC_VECTOR) is True
    assert len(sim.packets) == 122  # ceil(2920 / 24)
    assert sim.packets[0][:8].hex(" ") == "aa 42 00 00 00 7a 00 00"  # n = 2920 // 24 = 121, n + 1 = 0x7a
    assert sim.packets[-1][:8].hex(" ") == "aa 42 00 79 00 7a 00 00"
    assert sim.uploaded(0x42) == SPEC_VECTOR + bytes(122 * 24 - 2920)


def test_payload_of_exactly_two_chunks_takes_two_packets():
    sim, protocol = make_protocol(32)
    protocol.upload(0x41, bytes(range(48)))
    assert [packet[:8].hex(" ") for packet in sim.packets] == ["aa 41 00 00 00 03 00 00", "aa 41 00 01 00 03 00 00"]
    assert sim.uploaded(0x41) == bytes(range(48))


def test_progress_is_reported_after_every_chunk():
    _sim, protocol = make_protocol(32)
    calls = []
    assert protocol.upload(0x41, bytes(49), progress=lambda sent, total: calls.append((sent, total)),
                           cancelled=lambda: False) is True
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_cancel_stops_before_the_next_chunk():
    sim, protocol = make_protocol(32)
    assert protocol.upload(0x41, bytes(49), cancelled=lambda: len(sim.packets) >= 1) is False
    assert len(sim.packets) == 1


def test_unanswered_chunk_fails_after_the_resends():
    sim, protocol = make_protocol(32)
    sim.drop[0x41] = 4
    with pytest.raises(TransferError):
        protocol.upload(0x41, bytes(10))
    assert len(sim.packets) == 4


def test_upload_refuses_a_command_that_is_not_a_bulk_upload():
    sim, protocol = make_protocol(32)
    with pytest.raises(CommandNotAllowed):
        protocol.upload(0x24, bytes(10))
    assert sim.packets == []


def test_chunk_count_needs_data():
    with pytest.raises(ValueError, match="needs data"):
        chunk_count(0, 24)


@pytest.mark.parametrize(("length", "chunks"), [(1, 1), (24, 1), (25, 2), (48, 2), (49, 3)])
def test_chunk_count_rounds_up(length, chunks):
    assert chunk_count(length, 24) == chunks


def test_chunk_count_limit_is_the_16_bit_chunk_number():
    assert chunk_count(24 * MAX_CHUNKS, 24) == MAX_CHUNKS
    with pytest.raises(ValueError, match="at most 65536 chunks"):
        chunk_count(24 * MAX_CHUNKS + 1, 24)
