"""The key layout of the keyboard: position, size and label of its 108 keys, from data/f108v2-layout.json."""
import json
from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
# The layout file holds untranslated label expressions for the four keys above the keypad.
LABELS = {116: "Mute", 117: "Calc", 118: "Vol-", 119: "Vol+"}


class Arrow(Enum):
    LEFT = "left"
    DOWN = "down"
    UP = "up"
    RIGHT = "right"


# The arrow keys are drawn as triangles and have no text label.
ARROWS = {88: Arrow.LEFT, 89: Arrow.DOWN, 90: Arrow.UP, 91: Arrow.RIGHT}


@dataclass(frozen=True)
class Key:
    index: int  # the firmware key index, as in the key tables and the per-key colours
    label: str
    x: int
    y: int
    w: int
    h: int
    arrow: Arrow | None = None  # the direction of an arrow key

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


@cache
def load_layout() -> tuple[Key, ...]:
    """The keys in the order of the layout file, which is the order of the per-key animation frames."""
    data = json.loads((DATA / "f108v2-layout.json").read_text())
    return tuple(
        Key(key["index"], LABELS.get(key["index"], "" if key["index"] in ARROWS else key["name"]),
            key["x"], key["y"], key["w"], key["h"], ARROWS.get(key["index"]))
        for key in data["keys"]
    )


def bounds(keys) -> tuple[int, int, int, int]:
    """Left, top, right and bottom edge of the keys, in layout units."""
    return (
        min(key.x for key in keys),
        min(key.y for key in keys),
        max(key.x + key.w for key in keys),
        max(key.y + key.h for key in keys),
    )
