"""GIF files for the tests, written with PIL."""

from PIL import Image

RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


def write_gif(path, frames: list) -> str:
    """Write frames given as rows of RGB pixels and return the path as a string."""
    images = []
    for rows in frames:
        image = Image.new("RGB", (len(rows[0]), len(rows)))
        for y, row in enumerate(rows):
            for x, colour in enumerate(row):
                image.putpixel((x, y), colour)
        images.append(image)
    images[0].save(path, save_all=True, append_images=images[1:], duration=100, loop=0)
    return str(path)


def three_frame_gif(path) -> str:
    """2×1 pixels: red|blue, then blue|red, then green|green."""
    return write_gif(path, [[[RED, BLUE]], [[BLUE, RED]], [[GREEN, GREEN]]])
