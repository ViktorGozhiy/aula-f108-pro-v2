import pytest
from PyQt5.QtCore import QSettings

from aula_f108.ui.widgets import is_light, stored_colour


def test_is_light_boundary():
    # Brightness is red * 299 + green * 587 + blue * 114; a colour is light only above 128000.
    assert not is_light((1, 189, 147))  # exactly 128000
    assert is_light((2, 205, 62))       # 128001


def test_white_is_light_and_black_is_not():
    assert is_light((255, 255, 255))
    assert not is_light((0, 0, 0))


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_stored_colour_without_a_value_is_none(settings):
    assert stored_colour(settings, "page/colour") is None


def test_stored_colour_reads_the_hex_value(settings):
    settings.setValue("page/colour", "#00ff80")
    assert stored_colour(settings, "page/colour") == (0, 255, 128)
