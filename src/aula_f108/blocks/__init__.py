"""Configuration blocks of the keyboard: decode the raw bytes and write changed fields onto a fresh read."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Block:
    name: str
    read_cmd: int
    write_cmd: int | None
    size: int  # the bytes of a read; for a block with its own reader, the size of its fixed first part
    decode: Callable[[bytes], object]
    encode_into: Callable[[bytes, dict], bytes] | None
    reader: Callable[[object], bytes] | None = None  # reads a block of variable size over a Protocol
    writer: Callable[[object, bytes], None] | None = None  # writes a block that takes more than one transfer


def check_size(name: str, raw: bytes, size: int) -> None:
    if len(raw) != size:
        raise ValueError(f"{name} block must be {size} bytes, got {len(raw)}")


def check_fields(changes: dict, allowed: frozenset) -> None:
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")


def check_range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} must be within {low}..{high}, got {value}")


def check_colour(name: str, colour: tuple) -> None:
    if len(colour) != 3:
        raise ValueError(f"{name} must have three components, got {len(colour)}")
    for component in colour:
        check_range(name, component, 0, 255)
