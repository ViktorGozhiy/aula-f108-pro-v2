"""Page "Key colours": per-key colours painted on the keyboard picture and written with "Apply"."""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from aula_f108.blocks.key_colours import ENTRIES
from aula_f108.blocks.led_effect import PER_KEY_MODE
from aula_f108.edited_table import EditedTable
from aula_f108.layout import load_layout
from aula_f108.ui.keyboard_widget import KeyboardWidget
from aula_f108.ui.page import Page
from aula_f108.ui.widgets import ColourButton

OFF = (0, 0, 0)
EXPLANATION = (
    "Click a key or drag across keys to paint them with the chosen colour. Black turns a key "
    "off. “Apply” writes the colours to the keyboard and switches it to the key colours mode."
)


def edited_text(count: int) -> str:
    return f"Keys changed: {count}. They are marked with a dot and not yet written to the keyboard." if count else ""


class KeyColoursPage(Page):
    title = "Key colours"
    blocks = ("key_colours",)

    def __init__(self):
        super().__init__()
        self._table = EditedTable([OFF] * ENTRIES)
        self.explanation = QLabel(EXPLANATION)
        self.explanation.setWordWrap(True)
        self.keyboard = KeyboardWidget(load_layout())
        self.colour = ColourButton()
        self.pick = QPushButton("Pick colour from key")
        self.pick.setCheckable(True)
        self.fill = QPushButton("Fill all")
        self.discard = QPushButton("Discard changes")
        self.apply = QPushButton("Apply")
        self.edited_label = QLabel()
        self.edited_label.setWordWrap(True)
        # Set by "Apply": the effect switches to mode 20 once the worker reports the colours as written. A failed
        # or dropped write clears it, so a later write of this block, such as an import, does not switch the effect.
        self._switch_after_write = False
        # Set by "Apply" to the newest edit it sends while its write is pending, None otherwise. "Apply" stays
        # disabled meanwhile, so the written table is only compared with the edits of that one write.
        self._applied_edit = None

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Colour"))
        tools.addWidget(self.colour)
        tools.addWidget(self.pick)
        tools.addWidget(self.fill)
        tools.addStretch(1)
        tools.addWidget(self.discard)
        tools.addWidget(self.apply)
        layout = QVBoxLayout(self.body)
        layout.addWidget(self.explanation)
        layout.addLayout(tools)
        layout.addWidget(self.keyboard, 1)
        layout.addWidget(self.edited_label)
        self.fill_height()
        self.body.setEnabled(False)  # the keys show the keyboard's colours only after the first read

        self.keyboard.touched.connect(self._on_key)
        self.fill.clicked.connect(self._fill_all)
        self.discard.clicked.connect(self.discard_edits)
        self.apply.clicked.connect(self._apply)
        self._show_table()

    def display(self, name: str, value) -> None:
        """A read or a write replaces the table under the edits."""
        self._table.set_base(value.colours)
        self._show_table()

    def show_written(self, name: str, value) -> None:
        """A written table clears the edits that "Apply" sent and it holds. After the colours of "Apply" are
        written, switch the effect to them."""
        if self._applied_edit is None:
            self._table.set_base(value.colours)
        else:
            self._table.set_written(value.colours, self._applied_edit)
        self._end_pending_apply()
        super().show_written(name, value)
        if self._switch_after_write:
            self._switch_after_write = False
            self.update_requested.emit("led_effect", {"mode": PER_KEY_MODE})

    def show_write_failed(self, name: str, message: str) -> None:
        self._switch_after_write = False
        self._end_pending_apply()

    def show_connection(self, state) -> None:
        """Without a keyboard the queued write of "Apply" is dropped."""
        if state.status == "not_connected":
            self._switch_after_write = False
            self._end_pending_apply()

    def show_import_running(self, running: bool) -> None:
        """An import writes the LED effect of its file, so a switch to mode 20 that waits for the colours of "Apply"
        would overwrite it. The import drops that switch. A file without a led_effect section leaves the mode as it is;
        the colours are written and the mode can be set on the backlight page."""
        if running:
            self._switch_after_write = False
        super().show_import_running(running)

    def discard_edits(self) -> None:
        self._table.discard()
        self._end_pending_apply()
        self._show_table()

    def _on_key(self, index: int) -> None:
        if self.pick.isChecked():
            self.colour.set_colour(self._table.value(index))
            self.pick.setChecked(False)
            self.keyboard.end_drag()
        else:
            self._table.edit(index, self.colour.colour())
            self._show_table()

    def _fill_all(self) -> None:
        for key in self.keyboard.keys:
            self._table.edit(key.index, self.colour.colour())
        self._show_table()

    def _apply(self) -> None:
        self._switch_after_write = True
        self._applied_edit = self._table.last_edit()
        self._update_apply()
        self.update_requested.emit("key_colours", {"colours": self._table.changes()})

    def _end_pending_apply(self) -> None:
        self._applied_edit = None
        self._update_apply()

    def _update_apply(self) -> None:
        self.apply.setEnabled(self._applied_edit is None and not self._import_running)

    def _show_table(self) -> None:
        self.keyboard.set_colours({key.index: self._table.value(key.index) for key in self.keyboard.keys})
        edited = self._table.edited()
        self.keyboard.set_marked(edited)
        self.discard.setEnabled(bool(edited))
        self.edited_label.setText(edited_text(len(edited)))
