"""Page "Key animation": a GIF shown on the keys, previewed on the keyboard picture and uploaded with 0x42."""
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from aula_f108.animation import (
    DEFAULT_MAX_FRAMES,
    DEFAULT_SPEED,
    Animation,
    frame_limit,
    key_frames,
    load_gif,
    preview_interval,
)
from aula_f108.layout import load_layout
from aula_f108.ui.animation_controls import AnimationPage, ask_gif_path, frames_note
from aula_f108.ui.keyboard_widget import KeyboardWidget
from aula_f108.ui.widgets import make_slider
from aula_f108.worker import KEY_ANIMATION

EXPLANATION = (
    "Open a GIF: the program stretches each frame over the whole keyboard and takes the colour at the centre of "
    "each key. Before the upload the backlight switches to the animation mode. Over the cable the upload takes "
    "seconds, over the 2.4G dongle it can take several minutes."
)


class KeyAnimationPage(AnimationPage):
    title = "Key animation"
    blocks = ("device_info",)
    upload_kind = KEY_ANIMATION

    def __init__(self):
        super().__init__()
        self._keys = load_layout()
        self._frames = []
        self._frame = 0
        self._max_frames = DEFAULT_MAX_FRAMES
        self.explanation = QLabel(EXPLANATION)
        self.explanation.setWordWrap(True)
        self.open_button = QPushButton("Open GIF…")
        self.file_label = QLabel("No file chosen")
        self.frames_label = QLabel()
        self.frames_label.setWordWrap(True)
        self.keyboard = KeyboardWidget(self._keys)
        self.speed = make_slider(1, 100)
        self.speed.setTickInterval(10)
        self.speed.setValue(DEFAULT_SPEED)
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(preview_interval(DEFAULT_SPEED))

        file_row = QHBoxLayout()
        file_row.addWidget(self.open_button)
        file_row.addWidget(self.file_label, 1)
        speed_row = QFormLayout()
        speed_row.addRow("Speed", self.speed)
        layout = QVBoxLayout(self.body)
        layout.addWidget(self.explanation)
        layout.addLayout(file_row)
        layout.addWidget(self.frames_label)
        layout.addWidget(self.keyboard, 1)
        layout.addLayout(speed_row)
        layout.addWidget(self.upload_panel)
        self.fill_height()

        self.open_button.clicked.connect(self._choose_file)
        self.speed.valueChanged.connect(lambda value: self.preview_timer.setInterval(preview_interval(value)))
        self.preview_timer.timeout.connect(self._next_frame)

    def display(self, name: str, info) -> None:
        self._max_frames = frame_limit(info.gif_max_frames)

    def payload(self) -> bytes:
        return Animation(self._frames, self.speed.value()).payload(len(self._keys))

    def load_file(self, path: str) -> None:
        try:
            images, total = load_gif(path, self._max_frames)
        except OSError as error:
            self.frames_label.setText(f"Could not open the file: {error}")
            return
        self._frames = key_frames(images, self._keys)
        self._frame = 0
        self.file_label.setText(Path(path).name)
        self.frames_label.setText(frames_note(total, len(images)))
        self._show_frame()
        self.preview_timer.start()
        self.upload_panel.set_ready(True)

    def _choose_file(self) -> None:
        path = ask_gif_path(self)
        if path:
            self.load_file(path)

    def _next_frame(self) -> None:
        self._frame = (self._frame + 1) % len(self._frames)
        self._show_frame()

    def _show_frame(self) -> None:
        self.keyboard.set_colours({key.index: colour for key, colour in zip(self._keys, self._frames[self._frame])})
