"""GET / SET_KEY (0x12 / 0x22) and GET / SET_FN_KEY (0x16 / 0x26): the key actions of the base layer and the Fn layer.

Each table holds 128 four-byte key actions; entry i belongs to key index i. A write sends the whole table, built from
the fresh read with only the changed entries replaced, so entries outside the layout keep the keyboard's values.
"""

import json
from dataclasses import dataclass
from functools import cache

from aula_f108 import key_actions
from aula_f108.blocks import Block, check_fields, check_range, check_size
from aula_f108.layout import DATA

SIZE = 512
ENTRIES = 128
BASE = "base_keys"
FN = "fn_keys"
LAYERS = (BASE, FN)
FIELDS = frozenset({"actions"})


@dataclass(frozen=True)
class KeyTable:
    actions: tuple  # 128 key actions (aula_f108.key_actions), indexed by key index


def decode(raw: bytes) -> KeyTable:
    check_size("key table", raw, SIZE)
    return KeyTable(
        tuple(
            key_actions.decode(raw[offset : offset + key_actions.ENTRY_SIZE])
            for offset in range(0, SIZE, key_actions.ENTRY_SIZE)
        )
    )


def encode_into(raw: bytes, changes: dict) -> bytes:
    """Write the changed actions ({key index: action}) onto `raw`."""
    check_size("key table", raw, SIZE)
    check_fields(changes, FIELDS)
    out = bytearray(raw)
    for index, action in changes.get("actions", {}).items():
        check_range("key index", index, 0, ENTRIES - 1)
        offset = index * key_actions.ENTRY_SIZE
        out[offset : offset + key_actions.ENTRY_SIZE] = key_actions.encode(action)
    return bytes(out)


@cache
def factory_tables() -> dict:
    """The key tables of an unmodified keyboard, by layer name, from data/f108v2-default-keytables.json."""
    data = json.loads((DATA / "f108v2-default-keytables.json").read_text())
    return {BASE: decode(bytes.fromhex(data["base"])), FN: decode(bytes.fromhex(data["fn"]))}


BASE_BLOCK = Block(BASE, 0x12, 0x22, SIZE, decode, encode_into)
FN_BLOCK = Block(FN, 0x16, 0x26, SIZE, decode, encode_into)
