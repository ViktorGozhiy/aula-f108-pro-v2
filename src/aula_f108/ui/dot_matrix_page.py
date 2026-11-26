"""Page "7×7 display": text and background colours, sound-reactive modes and frame animations of the dot matrix."""

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from aula_f108.animation import (
    BLACK,
    DEFAULT_MAX_FRAMES,
    DOT_MATRIX_PIXELS,
    Animation,
    dot_matrix_frames,
    frame_limit,
    load_gif,
    pulse,
    rainbow_sweep,
)
from aula_f108.blocks.dot_matrix import CHARACTER_MODE
from aula_f108.ui.animation_controls import AnimationPage, ask_gif_path, frames_note
from aula_f108.ui.frame_editor import FrameEditor
from aula_f108.ui.widgets import WHITE, ColourButton, colour_name, stored_colour
from aula_f108.worker import DOT_MATRIX_ANIMATION

TEXT_KEY = "dot_matrix/text"
BACKGROUND_KEY = "dot_matrix/background"
SOUND_MODE_NAMES = {1: "Dance to music", 3: "Rows", 2: "Columns"}  # in the vendor's order
STATE_NOT_REPORTED = (
    "The keyboard does not report what the display shows now. The sound reaction buttons and the text and background "
    "colours change the display at once. “Rainbow”, “Pulse in the chosen colour” and “Open GIF…” only fill the frame "
    "editor: the display changes after “Upload to keyboard”."
)
COLOURS_NOT_REPORTED = (
    "The keyboard does not report the display colours. Until the program writes colours, white text on a black "
    "background is shown."
)


class DotMatrixPage(AnimationPage):
    title = "7×7 display"
    blocks = ("dot_matrix", "device_info")
    upload_kind = DOT_MATRIX_ANIMATION

    def __init__(self, settings: QSettings):
        super().__init__()
        self._settings = settings
        self._max_frames = DEFAULT_MAX_FRAMES
        self.state_note = QLabel(STATE_NOT_REPORTED)
        self.state_note.setWordWrap(True)
        self.text_colour = ColourButton()
        self.background_colour = ColourButton()
        self.colour_note = QLabel(COLOURS_NOT_REPORTED)
        self.colour_note.setWordWrap(True)
        text = stored_colour(settings, TEXT_KEY)
        background = stored_colour(settings, BACKGROUND_KEY)
        self.text_colour.set_colour(text or WHITE)
        self.background_colour.set_colour(background or BLACK)
        self.colour_note.setHidden(text is not None and background is not None)
        self.sound_buttons = {mode: QPushButton(name) for mode, name in SOUND_MODE_NAMES.items()}
        self.editor = FrameEditor()
        self.rainbow_button = QPushButton("Rainbow")
        self.pulse_button = QPushButton("Pulse in the chosen colour")
        self.open_button = QPushButton("Open GIF…")
        self.gif_label = QLabel()
        self.gif_label.setWordWrap(True)
        self.upload_panel.set_ready(True)

        colours = QGroupBox("Text")
        colours_form = QFormLayout(colours)
        colours_form.addRow("Text colour", self.text_colour)
        colours_form.addRow("Background colour", self.background_colour)
        colours_form.addRow(self.colour_note)
        sound = QGroupBox("Sound reaction")
        sound_row = QHBoxLayout(sound)
        for button in self.sound_buttons.values():
            sound_row.addWidget(button)
        sound_row.addStretch(1)
        animation = QGroupBox("Animation")
        animation_layout = QVBoxLayout(animation)
        animation_layout.addWidget(self.editor, 1)
        sources = QHBoxLayout()
        sources.addWidget(self.rainbow_button)
        sources.addWidget(self.pulse_button)
        sources.addWidget(self.open_button)
        sources.addStretch(1)
        animation_layout.addLayout(sources)
        animation_layout.addWidget(self.gif_label)
        animation_layout.addWidget(self.upload_panel)
        layout = QVBoxLayout(self.body)
        layout.addWidget(self.state_note)
        layout.addWidget(colours)
        layout.addWidget(sound)
        layout.addWidget(animation, 1)
        self.fill_height()

        self.text_colour.colour_chosen.connect(lambda colour: self._request_colours())
        self.background_colour.colour_chosen.connect(lambda colour: self._request_colours())
        for mode, button in self.sound_buttons.items():
            button.clicked.connect(lambda checked, mode=mode: self.update_requested.emit("dot_matrix", {"mode": mode}))
        self.rainbow_button.clicked.connect(lambda: self.editor.set_animation(rainbow_sweep()))
        self.pulse_button.clicked.connect(lambda: self.editor.set_animation(pulse(self.editor.paint_colour.colour())))
        self.open_button.clicked.connect(self._choose_file)

    def display(self, name: str, value) -> None:
        """Device info gives the frame limit. A dot-matrix read changes nothing on the page: it is unconfirmed."""
        if name == "device_info":
            self._max_frames = frame_limit(value.led_max_frames)
            self.editor.set_max_frames(self._max_frames)

    def show_written(self, name: str, matrix) -> None:
        """Remember the colours of a written character-mode write; a sound-mode write carries no colours."""
        if matrix.mode == CHARACTER_MODE:
            self._settings.setValue(TEXT_KEY, colour_name(matrix.text))
            self._settings.setValue(BACKGROUND_KEY, colour_name(matrix.background))
            self.colour_note.hide()
        super().show_written(name, matrix)

    def payload(self) -> bytes:
        return self.editor.animation().payload(DOT_MATRIX_PIXELS)

    def load_file(self, path: str) -> None:
        try:
            images, total = load_gif(path, self._max_frames)
        except OSError as error:
            self.gif_label.setText(f"Could not open the file: {error}")
            return
        self.editor.set_animation(Animation(dot_matrix_frames(images), self.editor.speed.value()))
        self.gif_label.setText(frames_note(total, len(images)))

    def _choose_file(self) -> None:
        path = ask_gif_path(self)
        if path:
            self.load_file(path)

    def _request_colours(self) -> None:
        self.update_requested.emit(
            "dot_matrix",
            {
                "background": self.background_colour.colour(),
                "text": self.text_colour.colour(),
                "mode": CHARACTER_MODE,
            },
        )
