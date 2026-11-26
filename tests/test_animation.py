import contextlib
from pathlib import Path

import pytest
from PIL import Image

from aula_f108.animation import (
    BLACK,
    DEFAULT_MAX_FRAMES,
    Animation,
    delay,
    dot_matrix_frames,
    frame_limit,
    key_frames,
    load_gif,
    preview_interval,
    pulse,
    rainbow_sweep,
)
from aula_f108.layout import load_layout
from gif_files import BLUE, GREEN, RED, three_frame_gif, write_gif


def test_payload_of_the_spec_vector():
    # A 9-frame per-key animation: 4 + 972 * 3 = 2920 bytes.
    payload = Animation([[BLACK] * 108] * 9).payload(108)
    assert len(payload) == 2920
    assert payload[:4] == bytes([9, 0, 11, 0])  # 9 frames, delay 101 - 90 = 11


def test_payload_holds_the_frames_in_order():
    animation = Animation([[RED, GREEN], [BLUE, BLACK]], speed=1)
    assert animation.payload(2) == bytes([2, 0, 100, 0]) + bytes(RED + GREEN + BLUE + BLACK)


def test_payload_needs_a_frame():
    with pytest.raises(ValueError, match="at least one frame"):
        Animation([]).payload(49)


def test_payload_checks_the_pixel_count():
    with pytest.raises(ValueError, match="frame 2 has 48 pixels, expected 49"):
        Animation([[BLACK] * 49, [BLACK] * 48]).payload(49)


@pytest.mark.parametrize("speed", [0, 101])
def test_payload_checks_the_speed(speed):
    with pytest.raises(ValueError, match="speed must be within 1..100"):
        Animation([[BLACK]], speed=speed).payload(1)


def test_payload_accepts_the_highest_speed():
    assert Animation([[BLACK]], speed=100).payload(1)[:4] == bytes([1, 0, 1, 0])


def test_payload_checks_the_colours():
    with pytest.raises(ValueError, match="pixel must be within 0..255"):
        Animation([[(0, 300, 0)]]).payload(1)


@pytest.mark.parametrize(("speed", "expected"), [(1, 100), (90, 11), (100, 1)])
def test_delay_follows_the_vendor_formula(speed, expected):
    assert delay(speed) == expected


def test_preview_shows_each_frame_for_ten_times_the_delay():
    assert preview_interval(90) == 110


@pytest.mark.parametrize(("reported", "limit"), [(0, DEFAULT_MAX_FRAMES), (1, 1), (300, 300)])
def test_frame_limit(reported, limit):
    assert frame_limit(reported) == limit


def test_load_gif_returns_rgb_frames_and_the_frame_count(tmp_path):
    images, total = load_gif(three_frame_gif(tmp_path / "a.gif"), 10)
    assert total == 3
    assert [image.getpixel((0, 0)) for image in images] == [RED, BLUE, GREEN]
    assert all(image.mode == "RGB" for image in images)


def test_load_gif_stops_at_the_frame_limit(tmp_path):
    path = three_frame_gif(tmp_path / "a.gif")
    images, total = load_gif(path, 2)
    assert (len(images), total) == (2, 3)
    assert len(load_gif(path, 3)[0]) == 3


def test_load_gif_takes_a_single_frame_image_without_a_frame_count(tmp_path):
    Image.new("RGB", (7, 7), RED).save(tmp_path / "a.jpg")
    images, total = load_gif(str(tmp_path / "a.jpg"), 10)
    assert (len(images), total) == (1, 1)


def test_load_gif_refuses_a_file_that_is_no_image(tmp_path):
    (tmp_path / "a.gif").write_text("not an image")
    with pytest.raises(OSError):
        load_gif(str(tmp_path / "a.gif"), 10)


def test_load_gif_refuses_a_truncated_file_with_an_os_error(tmp_path):
    data = Path(three_frame_gif(tmp_path / "a.gif")).read_bytes()
    for length in range(1, len(data)):
        (tmp_path / "cut.gif").write_bytes(data[:length])
        with contextlib.suppress(OSError):  # the only error a damaged file may raise
            load_gif(str(tmp_path / "cut.gif"), 10)


def test_load_gif_reports_a_file_cut_inside_a_frame_as_an_os_error(tmp_path):
    data = Path(three_frame_gif(tmp_path / "a.gif")).read_bytes()
    (tmp_path / "cut.gif").write_bytes(data[:111])
    with pytest.raises(OSError):
        load_gif(str(tmp_path / "cut.gif"), 10)


def test_dot_matrix_frames_average_an_area_of_two_colours():
    image = Image.new("RGB", (14, 14), BLACK)
    for y in range(2):
        image.putpixel((0, y), RED)
        image.putpixel((1, y), BLUE)
    red, green, blue = dot_matrix_frames([image])[0][0]
    assert (green, abs(red - 127.5) <= 1, abs(blue - 127.5) <= 1) == (0, True, True)


def test_dot_matrix_frames_average_each_area_into_7_by_7():
    image = Image.new("RGB", (14, 14), BLACK)
    for y in range(14):
        for x in range(2):
            image.putpixel((x, y), RED)
    frame = dot_matrix_frames([image])[0]
    assert len(frame) == 49
    assert frame[0] == RED
    assert frame[1] == BLACK
    assert frame[7] == RED


def test_key_frames_sample_each_key_centre_across_the_width():
    keys = load_layout()
    image = Image.new("RGB", (2, 1))
    image.putpixel((0, 0), RED)
    image.putpixel((1, 0), BLUE)
    frame = key_frames([image], keys)[0]
    by_index = dict(zip((key.index for key in keys), frame, strict=True))
    assert len(frame) == 108
    assert by_index[0] == RED  # Esc, left edge
    assert by_index[110] == BLUE  # keypad +, right edge


def test_key_frames_sample_each_key_centre_down_the_height():
    keys = load_layout()
    image = Image.new("RGB", (1, 2))
    image.putpixel((0, 0), RED)
    image.putpixel((0, 1), BLUE)
    by_index = dict(zip((key.index for key in keys), key_frames([image], keys)[0], strict=True))
    assert by_index[0] == RED  # Esc, top row
    assert by_index[83] == BLUE  # Space, bottom row


def test_rainbow_sweep_moves_the_hues_across_the_columns():
    animation = rainbow_sweep()
    assert len(animation.frames) == 14
    assert all(len(frame) == 49 for frame in animation.frames)
    first = animation.frames[0]
    assert first[0] == RED
    assert first[0:7] == first[42:49]  # every row is the same
    assert first[1] != first[0]
    assert animation.frames[1][0] != first[0]


def test_pulse_fades_the_colour_in_and_out():
    animation = pulse((200, 100, 0))
    assert len(animation.frames) == 16
    assert animation.frames[0] == [BLACK] * 49
    assert animation.frames[8] == [(200, 100, 0)] * 49
    assert animation.frames[4] == [(100, 50, 0)] * 49


def test_gif_frames_survive_a_round_trip(tmp_path):
    path = write_gif(tmp_path / "b.gif", [[[RED] * 7] * 7, [[BLUE] * 7] * 7])
    images, _total = load_gif(path, 10)
    assert dot_matrix_frames(images) == [[RED] * 49, [BLUE] * 49]
