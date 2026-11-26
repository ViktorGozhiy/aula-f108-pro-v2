"""Frame animations: the frame model shared by the dot matrix (49 pixels) and the per-key animation (108 keys),
the upload payload, GIF import and the two dot-matrix animations the application generates."""

import colorsys
import itertools
import math
from dataclasses import dataclass

from PIL import Image, ImageSequence

from aula_f108.blocks import check_colour, check_range
from aula_f108.layout import bounds

DOT_MATRIX_SIDE = 7
DOT_MATRIX_PIXELS = DOT_MATRIX_SIDE * DOT_MATRIX_SIDE
DEFAULT_SPEED = 90  # the speed of the vendor's built-in animations
DEFAULT_MAX_FRAMES = 512  # the vendor UI's frame limit
BLACK = (0, 0, 0)
RAINBOW_FRAMES = 14
PULSE_FRAMES = 16


@dataclass
class Animation:
    """Frames of RGB triplets (row-major 7×7 for the dot matrix, layout order for the keys) and a speed 1..100."""

    frames: list
    speed: int = DEFAULT_SPEED

    def payload(self, pixels: int) -> bytes:
        """[frames u16 LE, delay u16 LE] followed by the frames, as the vendor code builds it."""
        if not self.frames:
            raise ValueError("an animation needs at least one frame")
        check_range("speed", self.speed, 1, 100)
        out = bytearray(len(self.frames).to_bytes(2, "little") + delay(self.speed).to_bytes(2, "little"))
        for number, frame in enumerate(self.frames, start=1):
            if len(frame) != pixels:
                raise ValueError(f"frame {number} has {len(frame)} pixels, expected {pixels}")
            for colour in frame:
                check_colour("pixel", colour)
                out += bytes(colour)
        return bytes(out)


def delay(speed: int) -> int:
    """The frame delay the keyboard gets: ceil(101 - speed), as in the vendor code."""
    return math.ceil(101 - speed)


def preview_interval(speed: int) -> int:
    """Milliseconds per frame of a preview, as the vendor UI previews: (101 - speed) × 10."""
    return delay(speed) * 10


def frame_limit(reported: int) -> int:
    """The frame limit from device info, or the vendor UI's default when the keyboard reports 0."""
    return reported if reported > 0 else DEFAULT_MAX_FRAMES


def load_gif(path: str, max_frames: int) -> tuple[list, int]:
    """Return at most `max_frames` frames of the image file as RGB images, and the file's frame count.

    A file that cannot be read, or whose data is damaged, raises OSError.
    """
    try:
        with Image.open(path) as image:
            total = getattr(image, "n_frames", 1)
            frames = [frame.convert("RGB") for frame in itertools.islice(ImageSequence.Iterator(image), max_frames)]
    except OSError:
        raise
    except Exception as error:  # PIL raises IndexError, TypeError, struct.error and more on cut-off data
        raise OSError(f"the file is damaged ({type(error).__name__})") from error
    return frames, total


def dot_matrix_frames(images) -> list:
    """Each image scaled to 7×7, each pixel the average of its area, row-major."""
    return [list(image.resize((DOT_MATRIX_SIDE, DOT_MATRIX_SIDE), Image.Resampling.BOX).getdata()) for image in images]


def key_frames(images, keys) -> list:
    """Each image stretched over the keyboard and sampled at each key's centre, in the order of `keys`."""
    left, top, right, bottom = bounds(keys)
    frames = []
    for image in images:
        pixels = image.load()
        width, height = image.size
        frames.append(
            [
                pixels[
                    int((key.centre[0] - left) * width / (right - left)),
                    int((key.centre[1] - top) * height / (bottom - top)),
                ]
                for key in keys
            ]
        )
    return frames


def rainbow_sweep() -> Animation:
    """Hues across the columns, shifted by one step each frame."""
    frames = []
    for frame in range(RAINBOW_FRAMES):
        row = [_hue((column / DOT_MATRIX_SIDE + frame / RAINBOW_FRAMES) % 1.0) for column in range(DOT_MATRIX_SIDE)]
        frames.append(row * DOT_MATRIX_SIDE)
    return Animation(frames)


def pulse(colour) -> Animation:
    """The whole display in one colour, fading from black to the colour and back."""
    frames = []
    for frame in range(PULSE_FRAMES):
        level = (1 - math.cos(2 * math.pi * frame / PULSE_FRAMES)) / 2
        pixel = tuple(round(component * level) for component in colour)
        frames.append([pixel] * DOT_MATRIX_PIXELS)
    return Animation(frames)


def _hue(hue: float) -> tuple[int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return (round(red * 255), round(green * 255), round(blue * 255))
