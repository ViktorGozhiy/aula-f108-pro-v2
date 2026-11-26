"""The keyboard's configuration blocks over one command interface."""

from aula_f108.blocks import (
    Block,
    device_info,
    dot_matrix,
    key_colours,
    key_tables,
    led_effect,
    light_box,
    macros,
    settings,
)
from aula_f108.protocol import Protocol

# The order is the order in which a connect reads the blocks.
BLOCKS = {
    block.name: block
    for block in (
        device_info.BLOCK,
        settings.BLOCK,
        led_effect.BLOCK,
        light_box.BLOCK,
        key_colours.BLOCK,
        dot_matrix.BLOCK,
        key_tables.BASE_BLOCK,
        key_tables.FN_BLOCK,
        macros.BLOCK,
    )
}


class Keyboard:
    def __init__(self, protocol: Protocol):
        self.protocol = protocol

    def read(self, block: Block) -> bytes:
        if block.reader is not None:
            return block.reader(self.protocol)
        return self.protocol.read_block(block.read_cmd, block.size)

    def write(self, block: Block, raw: bytes) -> None:
        _require_writable(block)
        if block.writer is not None:
            block.writer(self.protocol, raw)
        else:
            self.protocol.write_block(block.write_cmd, raw)

    def read_with_changes(self, block: Block, changes: dict) -> bytes:
        """Read the block and return it with the changed fields written onto it. Nothing is written."""
        _require_writable(block)
        return block.encode_into(self.read(block), changes)

    def factory_reset(self) -> bool:
        return self.protocol.factory_reset()


def _require_writable(block: Block) -> None:
    if block.write_cmd is None:
        raise ValueError(f"{block.name} cannot be written")
