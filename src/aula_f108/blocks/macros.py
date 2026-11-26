"""GET / SET_MACRO (0x15 / 0x25): the 100 macro slots.

The macro memory, as the vendor code reads and writes it: a 400-byte index of 100 u32 LE offsets (0 for an empty
slot), then the macro bodies. A body is a u16 LE count (the number of actions times 2), two zero bytes, and four bytes
per action: delay u16 LE in ms, key code, flags (bit 7 press, bits 4-6 the action type: 3 keyboard, 1 mouse).

The raw form of the block is the index followed by the memory up to the end of the last body, each body at its
offset. A read takes the index, then the count and the actions of each used slot. A write rebuilds the bodies one
after another from address 400 and sends two transfers: the index without the last-packet flag, then the bodies with
it. Without bodies only the index is sent.

The size of the macro memory is not known: the vendor writer checks no limit, and the vendor's device info reports
macroSpaceSize 512. So a write whose bodies take more than MACRO_SPACE = 512 bytes is refused; the index is a fixed
area in front of them and is not counted.
"""
from dataclasses import dataclass

from aula_f108.blocks import Block, check_fields, check_range
from aula_f108.protocol import TransferError

READ_CMD = 0x15
WRITE_CMD = 0x25
SLOTS = 100
OFFSET_SIZE = 4
INDEX_SIZE = SLOTS * OFFSET_SIZE
BODY_HEADER_SIZE = 4
ACTION_SIZE = 4
ADDRESS_LIMIT = 0x10000  # a packet header holds a 16-bit address
MACRO_SPACE = 512
KEYBOARD_ACTION = 3
MOUSE_ACTION = 1
PRESS = 0x80
FIELDS = frozenset({"macros"})


@dataclass(frozen=True)
class MacroAction:
    delay: int   # milliseconds
    code: int    # HID usage of a keyboard action, button mask of a mouse action
    press: bool  # False for a release
    kind: int = KEYBOARD_ACTION


@dataclass(frozen=True)
class Macros:
    macros: tuple  # by slot: a tuple of MacroAction; an empty tuple is an empty slot


def decode(raw: bytes) -> Macros:
    _check_index(raw)
    return Macros(tuple(_decode_body(raw, offset) if offset else () for offset in _offsets(raw)))


def encode_action(action: MacroAction) -> bytes:
    check_range("delay", action.delay, 0, 0xFFFF)
    check_range("key code", action.code, 0, 0xFF)
    check_range("action type", action.kind, 0, 7)
    flags = (PRESS if action.press else 0) | action.kind << 4
    return bytes([action.delay & 0xFF, action.delay >> 8, action.code, flags])


def encode_body(actions) -> bytes:
    """The body of a macro with at least one action."""
    count = len(actions) * 2
    check_range("macro length", count, 2, 0xFFFF)
    return bytes([count & 0xFF, count >> 8, 0, 0]) + b"".join(encode_action(action) for action in actions)


def body_size(slots) -> int:
    """The bytes the bodies of these macros take in the macro memory."""
    return sum(BODY_HEADER_SIZE + ACTION_SIZE * len(actions) for actions in slots if actions)


def assemble(bodies) -> bytes:
    """The index and the bodies one after another from address 400. `bodies` holds a body or None for each slot."""
    index = bytearray(INDEX_SIZE)
    memory = bytearray()
    for slot, body in enumerate(bodies):
        if body:
            start = slot * OFFSET_SIZE
            index[start:start + OFFSET_SIZE] = (INDEX_SIZE + len(memory)).to_bytes(OFFSET_SIZE, "little")
            memory += body
    return bytes(index + memory)


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Rebuild the block with the changed slots ({slot: actions}); an empty tuple empties a slot.

    A used slot that is not changed keeps its body bytes. A slot without actions is left empty, as the vendor writer
    does. Raises ValueError when the bodies take more than MACRO_SPACE bytes.
    """
    check_fields(changes, FIELDS)
    current = decode(raw)
    changed = changes.get("macros", {})
    for slot in changed:
        check_range("macro slot", slot, 0, SLOTS - 1)
    offsets = _offsets(raw)
    bodies = []
    for slot in range(SLOTS):
        if slot in changed:
            actions = tuple(changed[slot])
            bodies.append(encode_body(actions) if actions else None)
        elif current.macros[slot]:
            offset = offsets[slot]
            bodies.append(bytes(raw[offset:offset + _body_span(raw, offset)]))
        else:
            bodies.append(None)
    out = assemble(bodies)
    used = len(out) - INDEX_SIZE
    if used > MACRO_SPACE:
        raise ValueError(f"the macros take {used} bytes, at most {MACRO_SPACE} fit")
    return out


def read(protocol) -> bytes:
    """Read the index, then the count and the actions of each used slot, as the vendor code does."""
    index = protocol.read_block(READ_CMD, INDEX_SIZE)
    memory = bytearray(index)
    for slot, offset in enumerate(_offsets(index)):
        if offset == 0:
            continue
        if offset < INDEX_SIZE or offset + BODY_HEADER_SIZE > ADDRESS_LIMIT:
            raise TransferError(f"macro M{slot + 1} points to address {offset}, outside the macro memory")
        header = protocol.read_block(READ_CMD, BODY_HEADER_SIZE, offset)
        end = offset + _body_span(header, 0)
        if end > ADDRESS_LIMIT:
            raise TransferError(f"macro M{slot + 1} ends at address {end}, outside the macro memory")
        actions = protocol.read_block(READ_CMD, end - offset - BODY_HEADER_SIZE, offset + BODY_HEADER_SIZE)
        memory.extend(bytes(max(0, end - len(memory))))
        memory[offset:end] = header + actions
    return bytes(memory)


def write(protocol, raw: bytes) -> None:
    """Send the index without the last-packet flag, then the bodies at address 400 with it."""
    protocol.write_block(WRITE_CMD, raw[:INDEX_SIZE], 0, last_flag=False)
    if len(raw) > INDEX_SIZE:
        protocol.write_block(WRITE_CMD, raw[INDEX_SIZE:], INDEX_SIZE)


def _check_index(raw: bytes) -> None:
    if len(raw) < INDEX_SIZE:
        raise ValueError(f"macro block must hold the {INDEX_SIZE}-byte index, got {len(raw)} bytes")


def _offsets(raw: bytes) -> list:
    return [int.from_bytes(raw[slot * OFFSET_SIZE:(slot + 1) * OFFSET_SIZE], "little") for slot in range(SLOTS)]


def _body_span(raw: bytes, offset: int) -> int:
    """The bytes of the body at `offset`: its header and its actions."""
    return BODY_HEADER_SIZE + (raw[offset] | raw[offset + 1] << 8) // 2 * ACTION_SIZE


def _decode_body(raw: bytes, offset: int) -> tuple:
    if offset < INDEX_SIZE or offset + BODY_HEADER_SIZE > len(raw):
        raise ValueError(f"the macro body at address {offset} lies outside the block")
    end = offset + _body_span(raw, offset)
    if end > len(raw):
        raise ValueError(f"the macro body at address {offset} ends past the block")
    return tuple(_decode_action(raw[position:position + ACTION_SIZE])
                 for position in range(offset + BODY_HEADER_SIZE, end, ACTION_SIZE))


def _decode_action(entry: bytes) -> MacroAction:
    return MacroAction(entry[0] | entry[1] << 8, entry[2], bool(entry[3] & PRESS), (entry[3] >> 4) & 7)


BLOCK = Block("macros", READ_CMD, WRITE_CMD, INDEX_SIZE, decode, encode_into, read, write)
