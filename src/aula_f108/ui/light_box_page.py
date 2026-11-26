"""Page "Side lighting": the light strip around the keyboard (light box block)."""
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFormLayout, QLabel

from aula_f108.blocks.light_box import COLOUR_MODES
from aula_f108.ui.page import Page
from aula_f108.ui.widgets import WHITE, ColourButton, colour_name, make_combo, make_slider, signals_blocked, stored_colour

MODE_NAMES = {
    1: "Light Flow",
    2: "Static",
    3: "Dynamic Breathing",
    4: "Spectrum Cycle",
    5: "Off",
    6: "Lively",
    7: "Chain Reaction",
}
NO_SPEED_MODES = frozenset({2})
COLOUR_KEY = "light_box/colour"
EXPLANATION = (
    "This page controls the light strip around the keyboard's perimeter. "
    "The program does not set the strip above the arrow keys: it changes only with key combinations "
    "on the keyboard (Fn+left Shift, Fn+left Alt, Fn+left Ctrl, Fn+X)."
)
COLOUR_NOT_REPORTED = (
    "The keyboard does not report the current strip colour. Until the program writes a colour, white is shown."
)


class LightBoxPage(Page):
    title = "Side lighting"
    blocks = ("light_box",)

    def __init__(self, settings: QSettings):
        super().__init__()
        self._settings = settings
        self.explanation = QLabel(EXPLANATION)
        self.explanation.setWordWrap(True)
        self.mode = make_combo(MODE_NAMES)
        self.colour = ColourButton()
        self.colour_note = QLabel(COLOUR_NOT_REPORTED)
        self.colour_note.setWordWrap(True)
        self.brightness = make_slider(1, 5)
        self.speed = make_slider(1, 5)

        stored = stored_colour(settings, COLOUR_KEY)
        self.colour.set_colour(stored or WHITE)
        self.colour_note.setHidden(stored is not None)

        form = QFormLayout(self.body)
        form.addRow(self.explanation)
        form.addRow("Effect", self.mode)
        form.addRow("Colour", self.colour)
        form.addRow(self.colour_note)
        form.addRow("Brightness", self.brightness)
        form.addRow("Speed", self.speed)

        self.mode.currentIndexChanged.connect(self._on_mode)
        self.colour.colour_chosen.connect(lambda colour: self._request())
        self.brightness.valueChanged.connect(lambda value: self._request(brightness=value))
        self.speed.valueChanged.connect(lambda value: self._request(speed=value))

    def display(self, name: str, box) -> None:
        """Show mode, brightness and speed. The colour of a read is not shown: the keyboard always reports red."""
        with signals_blocked(self.mode, self.brightness, self.speed):
            self.mode.setCurrentIndex(self.mode.findData(box.mode))
            self.brightness.setValue(box.brightness)
            self.speed.setValue(box.speed)
        self._update_controls(box.mode)

    def show_written(self, name: str, box) -> None:
        """The written colour is the colour of the strip now, also when an import wrote it. The page shows it, so
        the next write of the page carries it."""
        self._settings.setValue(COLOUR_KEY, colour_name(box.colour))
        self.colour.set_colour(box.colour)
        self.colour_note.hide()
        super().show_written(name, box)

    def _on_mode(self, index: int) -> None:
        mode = self.mode.itemData(index)
        self._update_controls(mode)
        self._request(mode=mode)

    def _update_controls(self, mode: int) -> None:
        self.colour.setEnabled(mode in COLOUR_MODES)
        self.speed.setEnabled(mode not in NO_SPEED_MODES)

    def _request(self, **changes) -> None:
        """Every write carries the page's colour, because the keyboard cannot report the colour it shows."""
        self.update_requested.emit("light_box", changes | {"colour": self.colour.colour()})
