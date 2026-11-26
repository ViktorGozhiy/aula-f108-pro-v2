from aula_f108.layout import Arrow, Key, bounds, load_layout


def test_layout_has_the_108_keys_once_each():
    keys = load_layout()
    assert len(keys) == 108
    assert len({key.index for key in keys}) == 108


def test_first_key_is_escape():
    assert load_layout()[0] == Key(0, "ESC", 20, 20, 50, 50)


def test_keys_without_a_usable_name_get_a_label():
    labels = {key.index: key.label for key in load_layout()}
    assert (labels[117], labels[116], labels[118], labels[119]) == ("Calc", "Mute", "Vol-", "Vol+")
    assert not any(label.startswith("<expr") for label in labels.values())


def test_key_labels_hold_only_ascii():
    """Qt 5 can crash in fontconfig while looking up a fallback font for a glyph the UI font lacks."""
    for key in load_layout():
        assert key.label.isascii(), key


def test_arrow_keys_have_a_direction_and_no_label():
    keys = {key.index: key for key in load_layout()}
    arrows = {index: keys[index].arrow for index in (88, 89, 90, 91)}
    assert arrows == {88: Arrow.LEFT, 89: Arrow.DOWN, 90: Arrow.UP, 91: Arrow.RIGHT}
    assert all(keys[index].label == "" for index in arrows)
    assert [key.index for key in keys.values() if key.arrow is not None] == [90, 88, 89, 91]


def test_centre_of_a_key():
    assert load_layout()[0].centre == (45.0, 45.0)


def test_bounds_of_the_layout():
    assert bounds(load_layout()) == (20, 20, 1217, 345)
