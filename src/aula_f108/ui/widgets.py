"""Small widgets shared by the pages."""
from contextlib import contextmanager

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog, QComboBox, QPushButton, QSlider, QWidget

WHITE = (255, 255, 255)


def colour_name(colour) -> str:
    red, green, blue = colour
    return f"#{red:02x}{green:02x}{blue:02x}"


def is_light(colour) -> bool:
    """True when black text reads better than white text on this colour."""
    red, green, blue = colour
    return red * 299 + green * 587 + blue * 114 > 128000


def stored_colour(settings, key: str) -> tuple[int, int, int] | None:
    """The colour stored under `key` as "#rrggbb", or None when none is stored."""
    stored = settings.value(key, "", type=str)
    if not stored:
        return None
    colour = QColor(stored)
    return (colour.red(), colour.green(), colour.blue())


class ColourButton(QPushButton):
    """Shows a colour. A click opens the colour dialog; a chosen colour is emitted as (r, g, b)."""

    colour_chosen = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(100)
        self._colour = WHITE
        self.clicked.connect(self._open_dialog)
        self._show_colour()

    def colour(self) -> tuple[int, int, int]:
        return self._colour

    def set_colour(self, colour) -> None:
        """Show a colour without emitting colour_chosen."""
        self._colour = tuple(colour)
        self._show_colour()

    def choose(self, colour) -> None:
        """Take a colour as the user's choice."""
        self.set_colour(colour)
        self.colour_chosen.emit(self._colour)

    def _open_dialog(self) -> None:
        chosen = QColorDialog.getColor(QColor(*self._colour), self, "Choose colour")
        if chosen.isValid():
            self.choose((chosen.red(), chosen.green(), chosen.blue()))

    def _show_colour(self) -> None:
        red, green, blue = self._colour
        self.setText(colour_name(self._colour))
        text = "black" if is_light(self._colour) else "white"
        self.setStyleSheet(f"background-color: rgb({red}, {green}, {blue}); color: {text};")


def make_slider(low: int, high: int) -> QSlider:
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(low, high)
    slider.setPageStep(1)
    slider.setTickInterval(1)
    slider.setTickPosition(QSlider.TickPosition.TicksBelow)
    return slider


def make_combo(names: dict) -> QComboBox:
    """A combo box with one item for each value of `names`, showing its name and holding the value as item data."""
    combo = QComboBox()
    for value, name in names.items():
        combo.addItem(name, value)
    return combo


@contextmanager
def signals_blocked(*widgets):
    """Set widget values from the keyboard without emitting change requests."""
    for widget in widgets:
        widget.blockSignals(True)
    try:
        yield
    finally:
        for widget in widgets:
            widget.blockSignals(False)


class TouchArea(QWidget):
    """A widget of items the user paints by pressing the left button over them or dragging across them."""

    touched = pyqtSignal(int)  # the item under the pressed left button: on the press and on each new item of a drag

    def __init__(self):
        super().__init__()
        self._dragging = False
        self._last = None

    def item_at(self, point) -> int | None:
        raise NotImplementedError

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last = None
            self._touch(event.pos())

    def end_drag(self) -> None:
        """Stop painting until the next press, for a press that was used for something other than painting."""
        self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._touch(event.pos())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def _touch(self, point) -> None:
        item = self.item_at(point)
        if item is not None and item != self._last:
            self._last = item
            self.touched.emit(item)
