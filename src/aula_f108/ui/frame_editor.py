"""The dot-matrix animation editor: a 7×7 grid of the current frame, the frame list with add, copy and delete,
the paint colour, the speed and a preview."""
from PyQt5.QtCore import QPointF, QRectF, QTimer
from PyQt5.QtGui import QColor, QPainter, QPalette
from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QWidget

from aula_f108.animation import (
    BLACK,
    DEFAULT_MAX_FRAMES,
    DEFAULT_SPEED,
    DOT_MATRIX_PIXELS,
    DOT_MATRIX_SIDE,
    Animation,
    preview_interval,
)
from aula_f108.ui.widgets import ColourButton, TouchArea, make_slider, signals_blocked


class PixelGrid(TouchArea):
    """The 7×7 pixels of one frame, row-major. `touched` carries the pixel index under the pressed left button."""

    def __init__(self):
        super().__init__()
        self._pixels = [BLACK] * DOT_MATRIX_PIXELS
        self.setMinimumSize(210, 210)

    def set_pixels(self, pixels) -> None:
        self._pixels = list(pixels)
        self.update()

    def pixels(self) -> list:
        return list(self._pixels)

    def cell_rect(self, index: int) -> QRectF:
        side = min(self.width(), self.height()) / DOT_MATRIX_SIDE
        left = (self.width() - side * DOT_MATRIX_SIDE) / 2
        top = (self.height() - side * DOT_MATRIX_SIDE) / 2
        row, column = divmod(index, DOT_MATRIX_SIDE)
        return QRectF(left + column * side, top + row * side, side, side)

    def item_at(self, point) -> int | None:
        for index in range(DOT_MATRIX_PIXELS):
            if self.cell_rect(index).contains(QPointF(point)):
                return index
        return None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
        for index, colour in enumerate(self._pixels):
            painter.setBrush(QColor(*colour))
            painter.drawRect(self.cell_rect(index).adjusted(1, 1, -1, -1))
        painter.end()


class FrameEditor(QWidget):
    def __init__(self):
        super().__init__()
        self._frames = [[BLACK] * DOT_MATRIX_PIXELS]
        self._current = 0
        self._max_frames = DEFAULT_MAX_FRAMES
        self.grid = PixelGrid()
        self.paint_colour = ColourButton()
        self.speed = make_slider(1, 100)
        self.speed.setTickInterval(10)
        self.speed.setValue(DEFAULT_SPEED)
        self.preview = QPushButton("Preview")
        self.preview.setCheckable(True)
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(preview_interval(DEFAULT_SPEED))
        self.frame_list = QListWidget()
        self.add_button = QPushButton("Add frame")
        self.copy_button = QPushButton("Copy frame")
        self.delete_button = QPushButton("Delete frame")

        form = QFormLayout()
        form.addRow("Colour", self.paint_colour)
        form.addRow("Speed", self.speed)
        left = QVBoxLayout()
        left.addWidget(self.grid, 1)
        left.addLayout(form)
        left.addWidget(self.preview)
        right = QVBoxLayout()
        right.addWidget(self.frame_list, 1)
        right.addWidget(self.add_button)
        right.addWidget(self.copy_button)
        right.addWidget(self.delete_button)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(left, 1)
        layout.addLayout(right)

        self.grid.touched.connect(self._paint)
        self.frame_list.currentRowChanged.connect(self._select)
        self.add_button.clicked.connect(self._add)
        self.copy_button.clicked.connect(self._copy)
        self.delete_button.clicked.connect(self._delete)
        self.speed.valueChanged.connect(lambda value: self.preview_timer.setInterval(preview_interval(value)))
        self.preview.toggled.connect(self._on_preview)
        self.preview_timer.timeout.connect(self._next_frame)
        self._show_frames()

    def animation(self) -> Animation:
        return Animation([list(frame) for frame in self._frames], self.speed.value())

    def set_animation(self, animation: Animation) -> None:
        self._frames = [list(frame) for frame in animation.frames]
        self._current = 0
        self.speed.setValue(animation.speed)
        self._show_frames()

    def set_max_frames(self, max_frames: int) -> None:
        self._max_frames = max_frames
        self._update_buttons()

    def _paint(self, index: int) -> None:
        self._frames[self._current][index] = self.paint_colour.colour()
        self.grid.set_pixels(self._frames[self._current])

    def _add(self) -> None:
        self._frames.insert(self._current + 1, [BLACK] * DOT_MATRIX_PIXELS)
        self._current += 1
        self._show_frames()

    def _copy(self) -> None:
        self._frames.insert(self._current + 1, list(self._frames[self._current]))
        self._current += 1
        self._show_frames()

    def _delete(self) -> None:
        del self._frames[self._current]
        self._current = min(self._current, len(self._frames) - 1)
        self._show_frames()

    def _select(self, row: int) -> None:
        self._current = row
        self.grid.set_pixels(self._frames[row])

    def _on_preview(self, checked: bool) -> None:
        if checked:
            self.preview_timer.start()
        else:
            self.preview_timer.stop()

    def _next_frame(self) -> None:
        self.frame_list.setCurrentRow((self._current + 1) % len(self._frames))

    def _show_frames(self) -> None:
        with signals_blocked(self.frame_list):
            self.frame_list.clear()
            self.frame_list.addItems([f"Frame {number}" for number in range(1, len(self._frames) + 1)])
            self.frame_list.setCurrentRow(self._current)
        self.grid.set_pixels(self._frames[self._current])
        self._update_buttons()

    def _update_buttons(self) -> None:
        room = len(self._frames) < self._max_frames
        self.add_button.setEnabled(room)
        self.copy_button.setEnabled(room)
        self.delete_button.setEnabled(len(self._frames) > 1)
