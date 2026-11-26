import pytest

from aula_f108.blocks import dot_matrix
from aula_f108.blocks.dot_matrix import DotMatrix
from fixture_data import load_hex

READ = load_hex("wired-3D.hex")  # firmware V1.33 answers all zeros
FILLED = bytes([9] * 9)


def test_decodes_the_captured_read():
    assert dot_matrix.decode(READ) == DotMatrix((0, 0, 0), (0, 0, 0), 0, 0, 0)


def test_decodes_every_field():
    assert dot_matrix.decode(bytes([1, 2, 3, 4, 5, 6, 7, 1, 3])) == DotMatrix((1, 2, 3), (4, 5, 6), 7, 1, 3)


@pytest.mark.parametrize(("raw_mode", "decoded"), [(0, 0), (1, 1), (3, 3), (4, 0), (0xFF, 0)])
def test_dot_matrix_mode_outside_1_to_3_reads_as_0(raw_mode, decoded):
    assert dot_matrix.decode(bytes(8) + bytes([raw_mode])).dot_matrix_mode == decoded


def test_decode_rejects_a_wrong_size():
    with pytest.raises(ValueError, match="9 bytes"):
        dot_matrix.decode(bytes(8))


def test_character_mode_sets_only_the_two_colours():
    out = dot_matrix.encode_into(FILLED, {"background": (1, 2, 3), "text": (4, 5, 6), "mode": 0})
    assert out == bytes([1, 2, 3, 4, 5, 6, 0, 0, 0])


def test_character_mode_is_the_default_mode():
    assert dot_matrix.encode_into(READ, {"background": (1, 2, 3), "text": (4, 5, 6)}) == bytes([1, 2, 3, 4, 5, 6, 0, 0, 0])


def test_missing_colours_are_written_as_black():
    assert dot_matrix.encode_into(FILLED, {"text": (4, 5, 6)}) == bytes([0, 0, 0, 4, 5, 6, 0, 0, 0])
    assert dot_matrix.encode_into(FILLED, {"background": (1, 2, 3)}) == bytes([1, 2, 3, 0, 0, 0, 0, 0, 0])


@pytest.mark.parametrize("mode", [1, 2, 3])
def test_sound_mode_sets_only_the_mode(mode):
    assert dot_matrix.encode_into(FILLED, {"mode": mode}) == bytes(7) + bytes([mode, 0])


def test_sound_mode_drops_colours_merged_into_the_same_write():
    out = dot_matrix.encode_into(READ, {"background": (1, 2, 3), "text": (4, 5, 6), "mode": 2})
    assert out == bytes(7) + bytes([2, 0])


@pytest.mark.parametrize("mode", [-1, 4])
def test_rejects_a_mode_outside_0_to_3(mode):
    with pytest.raises(ValueError, match="mode must be within 0..3"):
        dot_matrix.encode_into(READ, {"mode": mode})


@pytest.mark.parametrize("field", ["background", "text"])
def test_rejects_a_bad_colour(field):
    with pytest.raises(ValueError, match=f"{field} must be within 0..255"):
        dot_matrix.encode_into(READ, {field: (0, 0, 300)})


def test_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unknown fields: type"):
        dot_matrix.encode_into(READ, {"type": 1})


def test_encode_rejects_a_wrong_size():
    with pytest.raises(ValueError, match="9 bytes"):
        dot_matrix.encode_into(bytes(10), {})
