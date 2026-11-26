"""Page "Backlight": the main backlight effect (LED effect block)."""
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QCheckBox, QFormLayout, QLabel

from aula_f108.blocks.led_effect import ANIMATION_MODE, FORCED_COLOURFUL_MODES, PER_KEY_MODES
from aula_f108.ui.key_animation_page import KeyAnimationPage
from aula_f108.ui.key_colours_page import KeyColoursPage
from aula_f108.ui.page import Page
from aula_f108.ui.widgets import WHITE, ColourButton, colour_name, make_combo, make_slider, signals_blocked, stored_colour

MODE_NAMES = {
    0: "Off",
    1: "Static",
    2: "Single Point On",
    3: "Single Point Off",
    4: "Starry Sky",
    5: "Snowfall",
    6: "Blooming",
    7: "Dynamic Breathing",
    8: "Spectrum Cycle",
    9: "Colourful Spring",
    10: "Colourful Cross",
    11: "Drifting",
    12: "Peak Return",
    13: "Instant Trigger",
    14: "Dual Action",
    15: "Ripple Spread",
    16: "Flowing Stream",
    17: "Mountain Layers",
    18: "Gentle Rain",
    19: "Shuttle",
}
NO_SPEED_MODES = frozenset({1}) | PER_KEY_MODES
DIRECTION_MODES = frozenset({10, 11, 12, 16, 18})
DIRECTION_NAMES = {0: "Forward", 1: "Reverse"}
# Modes the per-key pages write. They send no colour (20) or the vendor's red (0xFF), so the page keeps its own.
OTHER_PAGE_MODES = PER_KEY_MODES | {ANIMATION_MODE}
PER_KEY_NOTE = (
    f'The keyboard now shows the key colours (page <a href="{KeyColoursPage.title}">'
    f"“{KeyColoursPage.title}”</a>). Choose an effect to replace them."
)
ANIMATION_NOTE = (
    f'The keyboard now plays the key animation (page <a href="{KeyAnimationPage.title}">'
    f"“{KeyAnimationPage.title}”</a>). Choose an effect to replace it."
)
COLOUR_KEY = "led_effect/colour"
HOST_SET_COLOUR = (255, 255, 255)  # what a read reports for a colour written by the host
COLOUR_NOT_REPORTED = (
    "The keyboard does not report the colour set by the program. Until the program writes a colour, white is shown."
)


class BacklightPage(Page):
    title = "Backlight"
    blocks = ("led_effect",)

    def __init__(self, settings: QSettings):
        super().__init__()
        self._settings = settings
        self.mode = make_combo(MODE_NAMES)
        self.current_note = QLabel()
        self.current_note.setWordWrap(True)
        self.current_note.hide()
        self.current_note.setTextFormat(Qt.TextFormat.RichText)
        self.current_note.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.current_note.linkActivated.connect(self.page_requested)
        self.colour = ColourButton()
        self.colour_note = QLabel(COLOUR_NOT_REPORTED)
        self.colour_note.setWordWrap(True)
        self.colourful = QCheckBox("Colourful mode")
        self.brightness = make_slider(1, 5)
        self.speed = make_slider(1, 5)
        self.direction = make_combo(DIRECTION_NAMES)

        self._show_stored_colour()

        form = QFormLayout(self.body)
        form.addRow("Effect", self.mode)
        form.addRow(self.current_note)
        form.addRow("Colour", self.colour)
        form.addRow(self.colour_note)
        form.addRow("", self.colourful)
        form.addRow("Brightness", self.brightness)
        form.addRow("Speed", self.speed)
        form.addRow("Direction", self.direction)

        self.mode.currentIndexChanged.connect(self._on_mode)
        self.colour.colour_chosen.connect(lambda colour: self._request())
        self.colourful.toggled.connect(lambda checked: self._request(colourful=checked))
        self.brightness.valueChanged.connect(lambda value: self._request(brightness=value))
        self.speed.valueChanged.connect(lambda value: self._request(speed=value))
        self.direction.currentIndexChanged.connect(
            lambda index: self._request(direction=self.direction.itemData(index)))

    def display(self, name: str, effect) -> None:
        """Show the effect. A colour other than ff ff ff is the one chosen on the keyboard and becomes the page
        colour. ff ff ff means the program set the colour, so the page shows the colour it stored, or white."""
        with signals_blocked(self.mode, self.colourful, self.brightness, self.speed, self.direction):
            self.mode.setCurrentIndex(self.mode.findData(effect.mode))
            self.colourful.setChecked(effect.colourful)
            self.brightness.setValue(effect.brightness)
            self.speed.setValue(effect.speed)
            self.direction.setCurrentIndex(self.direction.findData(effect.direction))
        if effect.colour != HOST_SET_COLOUR and effect.mode not in OTHER_PAGE_MODES:
            self.colour.set_colour(effect.colour)
            self.colour_note.hide()
        else:
            self._show_stored_colour()
        if effect.mode in PER_KEY_MODES:
            note = PER_KEY_NOTE
        elif effect.mode == ANIMATION_MODE:
            note = ANIMATION_NOTE
        else:
            note = ""
        self.current_note.setText(note)
        self.current_note.setHidden(not note)
        self._update_controls(effect.mode)

    def _show_stored_colour(self) -> None:
        """Show the colour the program last wrote, or white with the note when it has written none."""
        stored = stored_colour(self._settings, COLOUR_KEY)
        self.colour.set_colour(stored or WHITE)
        self.colour_note.setHidden(stored is not None)

    def show_written(self, name: str, effect) -> None:
        """Remember the written colour, except for the modes the per-key pages write."""
        if effect.mode not in OTHER_PAGE_MODES:
            self._settings.setValue(COLOUR_KEY, colour_name(effect.colour))
            self.colour_note.hide()
        super().show_written(name, effect)

    def _on_mode(self, index: int) -> None:
        mode = self.mode.itemData(index)
        self.current_note.hide()
        self._update_controls(mode)
        self._request(mode=mode)

    def _update_controls(self, mode: int) -> None:
        self.speed.setEnabled(mode not in NO_SPEED_MODES)
        self.direction.setEnabled(mode in DIRECTION_MODES)
        forced = mode in FORCED_COLOURFUL_MODES
        self.colourful.setEnabled(not forced)
        if forced:
            with signals_blocked(self.colourful):
                self.colourful.setChecked(True)

    def _request(self, **changes) -> None:
        """Every write carries the page's colour, because the keyboard cannot report a colour written by the host."""
        self.update_requested.emit("led_effect", changes | {"colour": self.colour.colour()})
