import pytest

from aula_f108.blocks import macros
from aula_f108.blocks.macros import BLOCK, MACRO_SPACE, MOUSE_ACTION, MacroAction, Macros
from aula_f108.keyboard import BLOCKS, Keyboard
from aula_f108.protocol import Protocol, TransferError
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard

A = 0x04
PRESS_A = MacroAction(10, A, True)
RELEASE_A = MacroAction(20, A, False)
BODY_A = bytes([4, 0, 0, 0, 10, 0, A, 0xB0, 20, 0, A, 0x30])
EMPTY = load_hex("wired-15.hex")  # no macro stored: the index is all zeros


def make_keyboard(report_size=64):
    sim = SimulatedKeyboard(report_size)
    return sim, Keyboard(Protocol(sim, lambda report: None, time_scale=0.01))


def store(sim, slot, offset, body):
    """Put a macro body into the simulated macro memory and point the slot at it."""
    sim.blocks["macros"][slot * 4 : slot * 4 + 4] = offset.to_bytes(4, "little")
    sim.blocks["macros"][offset : offset + len(body)] = body


def block_with(slot, offset, body):
    raw = bytearray(EMPTY)
    raw[slot * 4 : slot * 4 + 4] = offset.to_bytes(4, "little")
    raw.extend(bytes(max(0, offset + len(body) - len(raw))))
    raw[offset : offset + len(body)] = body
    return bytes(raw)


def reads_after_the_index(sim, index_packets=8):
    """(length, address) of each read packet after the packets of the index."""
    return [(packet[2], packet[3] | packet[4] << 8) for packet in sim.packets[index_packets:]]


def test_block_is_in_the_keyboard_table():
    assert BLOCKS["macros"] is BLOCK
    assert (BLOCK.read_cmd, BLOCK.write_cmd, BLOCK.size) == (0x15, 0x25, 400)


def test_decodes_the_captured_index_as_empty():
    assert macros.decode(EMPTY) == Macros(((),) * 100)


def test_decodes_each_action():
    raw = block_with(3, 400, bytes([6, 0, 0, 0, 10, 0, A, 0xB0, 0, 1, 1, 0x90, 5, 0, 1, 0x10]))
    assert macros.decode(raw).macros[3] == (
        PRESS_A,
        MacroAction(256, 1, True, MOUSE_ACTION),
        MacroAction(5, 1, False, MOUSE_ACTION),
    )


def test_decodes_the_action_type_from_bits_4_to_6():
    raw = block_with(3, 400, bytes([2, 0, 0, 0, 10, 0, A, 0xE0]))  # press, type 6
    assert macros.decode(raw).macros[3] == (MacroAction(10, A, True, 6),)


def test_decode_needs_the_index():
    with pytest.raises(ValueError, match="400-byte index, got 399 bytes"):
        macros.decode(bytes(399))


def test_decode_refuses_a_body_inside_the_index():
    with pytest.raises(ValueError, match="address 100 lies outside"):
        macros.decode(block_with(0, 100, BODY_A))


def test_decode_refuses_a_header_past_the_block():
    raw = bytearray(EMPTY)
    raw[0:4] = (398).to_bytes(4, "little")  # below 400 is refused before the header is looked at
    with pytest.raises(ValueError, match="lies outside"):
        macros.decode(bytes(raw))
    raw[0:4] = (402).to_bytes(4, "little")
    raw.extend(bytes(4))  # 404 bytes: the header at 402 ends at 406
    with pytest.raises(ValueError, match="address 402 lies outside"):
        macros.decode(bytes(raw))


def test_decode_refuses_a_body_past_the_block():
    with pytest.raises(ValueError, match="ends past the block"):
        macros.decode(block_with(0, 400, BODY_A[:8]))


def test_reads_only_the_index_when_no_macro_is_stored():
    sim, keyboard = make_keyboard()
    assert keyboard.read(BLOCK) == EMPTY
    assert sim.sent_commands() == [0x15] * 8  # 400 bytes in packets of 56


def test_reads_each_stored_macro_at_its_offset():
    sim, keyboard = make_keyboard()
    store(sim, 2, 1000, BODY_A)
    raw = keyboard.read(BLOCK)
    assert len(raw) == 1012
    assert raw[1000:1012] == BODY_A
    assert macros.decode(raw).macros[2] == (PRESS_A, RELEASE_A)
    assert reads_after_the_index(sim) == [(4, 1000), (8, 1004)]


def test_reads_macros_stored_in_any_order():
    sim, keyboard = make_keyboard()
    store(sim, 0, 1000, BODY_A)
    store(sim, 1, 400, BODY_A)  # below the end of the memory read for M1
    assert macros.decode(keyboard.read(BLOCK)).macros[:2] == ((PRESS_A, RELEASE_A), (PRESS_A, RELEASE_A))


def test_reads_a_macro_without_actions_as_an_empty_slot():
    sim, keyboard = make_keyboard()
    store(sim, 0, 400, bytes(4))
    raw = keyboard.read(BLOCK)
    assert macros.decode(raw).macros[0] == ()
    assert reads_after_the_index(sim) == [(4, 400)]


def test_reads_a_macro_that_ends_at_the_address_limit():
    sim, keyboard = make_keyboard()
    store(sim, 0, 0xFFF8, macros.encode_body((PRESS_A,)))  # 8 bytes: the last one is at 0xFFFF
    assert macros.decode(keyboard.read(BLOCK)).macros[0] == (PRESS_A,)


def test_reads_an_empty_macro_whose_header_ends_at_the_address_limit():
    sim, keyboard = make_keyboard()
    store(sim, 0, 0xFFFC, bytes(4))  # the header takes the last four addresses
    assert macros.decode(keyboard.read(BLOCK)).macros[0] == ()


@pytest.mark.parametrize(
    ("offset", "body", "message"),
    [
        (399, bytes(4), "M1 points to address 399"),
        (0xFFFD, bytes(3), "M1 points to address 65533"),
        (0xFFF8, bytes([4, 0, 0, 0]), "M1 ends at address 65540"),
    ],
)
def test_read_refuses_a_macro_outside_the_memory(offset, body, message):
    sim, keyboard = make_keyboard()
    store(sim, 0, offset, body)
    with pytest.raises(TransferError, match=message):
        keyboard.read(BLOCK)


def test_encode_into_writes_a_macro_into_an_empty_block():
    out = macros.encode_into(EMPTY, {"macros": {2: (PRESS_A, RELEASE_A)}})
    assert out == block_with(2, 400, BODY_A)


def test_encode_body_counts_each_action_twice():
    assert macros.encode_body((PRESS_A,))[:4] == bytes([2, 0, 0, 0])
    with pytest.raises(ValueError, match="macro length"):
        macros.encode_body(())


def test_encode_body_takes_at_most_32767_actions():
    assert macros.encode_body((PRESS_A,) * 32767)[:4] == bytes([0xFE, 0xFF, 0, 0])  # the count 65534
    with pytest.raises(ValueError, match="macro length must be within 2..65535, got 65536"):
        macros.encode_body((PRESS_A,) * 32768)


def test_unchanged_macro_keeps_its_bytes_and_bodies_are_packed_in_slot_order():
    kept = bytes([2, 0, 0, 0, 7, 0, A, 0xB5])  # low flag bits the application does not model
    raw = block_with(5, 1000, kept)
    out = macros.encode_into(raw, {"macros": {1: (PRESS_A, RELEASE_A)}})
    assert out[4:8] == (400).to_bytes(4, "little")
    assert out[20:24] == (412).to_bytes(4, "little")
    assert out[400:] == BODY_A + kept


def test_empty_change_removes_the_macro():
    raw = block_with(2, 400, BODY_A)
    assert macros.encode_into(raw, {"macros": {2: ()}}) == EMPTY


def test_unchanged_macro_without_actions_is_left_empty():
    raw = block_with(4, 400, bytes(4))
    assert macros.encode_into(raw, {}) == EMPTY


@pytest.mark.parametrize("slot", [0, 99])
def test_encode_into_takes_the_first_and_the_last_slot(slot):
    out = macros.encode_into(EMPTY, {"macros": {slot: (PRESS_A,)}})
    assert macros.decode(out).macros[slot] == (PRESS_A,)


@pytest.mark.parametrize("slot", [-1, 100])
def test_encode_into_refuses_a_slot_outside_the_100(slot):
    with pytest.raises(ValueError, match="macro slot"):
        macros.encode_into(EMPTY, {"macros": {slot: (PRESS_A,)}})


def test_encode_into_refuses_unknown_fields():
    with pytest.raises(ValueError, match="unknown fields: actions"):
        macros.encode_into(EMPTY, {"actions": {}})


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (MacroAction(-1, A, True), "delay"),
        (MacroAction(0x10000, A, True), "delay"),
        (MacroAction(0, -1, True), "key code"),
        (MacroAction(0, 0x100, True), "key code"),
        (MacroAction(0, A, True, -1), "action type"),
        (MacroAction(0, A, True, 8), "action type"),
    ],
)
def test_encode_into_refuses_values_an_action_cannot_hold(action, message):
    with pytest.raises(ValueError, match=message):
        macros.encode_into(EMPTY, {"macros": {0: (action,)}})


def test_action_boundaries_encode():
    assert macros.encode_action(MacroAction(0xFFFF, 0xFF, False, 7)) == bytes([0xFF, 0xFF, 0xFF, 0x70])
    assert macros.encode_action(MacroAction(0, 0, True, 0)) == bytes([0, 0, 0, 0x80])


def test_bodies_of_512_bytes_fit_and_516_bytes_are_refused():
    assert MACRO_SPACE == 512
    fits = (PRESS_A,) * 127  # 4 + 127 * 4 = 512 bytes
    assert len(macros.encode_into(EMPTY, {"macros": {0: fits}})) == 400 + 512
    with pytest.raises(ValueError, match="the macros take 516 bytes, at most 512 fit"):
        macros.encode_into(EMPTY, {"macros": {0: fits + (PRESS_A,)}})


def test_body_size_counts_the_used_slots():
    assert macros.body_size([(), (PRESS_A,), (PRESS_A, RELEASE_A)]) == 8 + 12


def test_write_sends_the_index_without_the_flag_then_the_bodies_with_it():
    sim, keyboard = make_keyboard()
    keyboard.write(BLOCK, keyboard.read_with_changes(BLOCK, {"macros": {2: (PRESS_A, RELEASE_A)}}))
    writes = [(packet[3] | packet[4] << 8, packet[6]) for packet in sim.packets if packet[1] == 0x25]
    assert writes == [(address, 0) for address in range(0, 400, 56)] + [(400, 1)]
    assert macros.decode(keyboard.read(BLOCK)).macros[2] == (PRESS_A, RELEASE_A)


def test_write_without_macros_sends_only_the_index():
    sim, keyboard = make_keyboard()
    store(sim, 2, 400, BODY_A)
    keyboard.write(BLOCK, keyboard.read_with_changes(BLOCK, {"macros": {2: ()}}))
    flags = [packet[6] for packet in sim.packets if packet[1] == 0x25]
    assert flags == [0] * 8
    assert bytes(sim.blocks["macros"][:400]) == EMPTY


def test_write_on_the_dongle():
    sim, keyboard = make_keyboard(32)
    keyboard.write(BLOCK, macros.encode_into(EMPTY, {"macros": {0: (PRESS_A, RELEASE_A)}}))
    writes = [(packet[3] | packet[4] << 8, packet[6]) for packet in sim.packets if packet[1] == 0x25]
    assert writes == [(address, 0) for address in range(0, 400, 24)] + [(400, 1)]
    assert macros.decode(keyboard.read(BLOCK)).macros[0] == (PRESS_A, RELEASE_A)
