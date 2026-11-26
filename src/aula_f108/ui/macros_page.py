"""Page "Macros": the 100 macro slots, edited here and written with "Apply"."""

import dataclasses

from PyQt5.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from aula_f108.action_names import key_label
from aula_f108.blocks.macros import KEYBOARD_ACTION, MACRO_SPACE, MOUSE_ACTION, SLOTS, MacroAction, body_size
from aula_f108.edited_table import EditedTable
from aula_f108.ui.action_editor import KeyPicker, select
from aula_f108.ui.page import Page
from aula_f108.ui.widgets import make_combo

KIND_NAMES = {KEYBOARD_ACTION: "Key", MOUSE_ACTION: "Mouse button"}
BUTTON_NAMES = {1: "left", 2: "right", 4: "middle", 8: "back", 16: "forward"}
PRESS_NAMES = {True: "Press", False: "Release"}
DEFAULT_DELAY_MS = 50
EXPLANATION = (
    "A macro is a sequence of key and mouse button presses and releases with delays. A macro is assigned to a key on "
    "the “Keys” page. Changed macros are marked with an asterisk; “Apply” writes all macros to the keyboard."
)


def code_name(action: MacroAction) -> str:
    if action.kind == KEYBOARD_ACTION:
        return key_label(action.code)
    if action.kind == MOUSE_ACTION:
        return f"mouse button {BUTTON_NAMES.get(action.code, f'0x{action.code:02X}')}"
    return f"code 0x{action.code:02X} of type {action.kind}"


def step_text(action: MacroAction) -> str:
    return f"{PRESS_NAMES[action.press]} {code_name(action)}, delay {action.delay} ms"


def slot_text(slot: int, actions: tuple, edited: bool) -> str:
    text = f"M{slot + 1}"
    if actions:
        text += f" ({len(actions)})"
    if edited:
        text += " *"
    return text


def used_text(used: int) -> str:
    text = f"{used} of {MACRO_SPACE} bytes of macro memory used."
    if used > MACRO_SPACE:
        text += " This is over the limit: delete actions to write the macros."
    return text


def edited_text(count: int) -> str:
    if not count:
        return ""
    return f"Macros changed: {count}. They are marked with an asterisk and not yet written to the keyboard."


class MacrosPage(Page):
    title = "Macros"
    blocks = ("macros",)

    def __init__(self):
        super().__init__()
        self._table = EditedTable([()] * SLOTS)
        # Set by "Apply" to the newest edit it sends while its write is pending, None otherwise.
        self._applied_edit = None
        self.explanation = QLabel(EXPLANATION)
        self.explanation.setWordWrap(True)
        self.slots = QListWidget()
        self.steps = QListWidget()
        self.kind = make_combo(KIND_NAMES)
        self.key = KeyPicker()
        self.button = make_combo(BUTTON_NAMES)
        self.press = make_combo(PRESS_NAMES)
        self.delay = QSpinBox()
        self.delay.setRange(0, 0xFFFF)
        self.delay.setSuffix(" ms")
        self.delay.setValue(DEFAULT_DELAY_MS)
        self.add = QPushButton("Add")
        self.add_pair = QPushButton("Add press and release")
        self.replace = QPushButton("Replace")
        self.remove = QPushButton("Delete")
        self.up = QPushButton("Up")
        self.down = QPushButton("Down")
        self.clear = QPushButton("Clear macro")
        self.used_label = QLabel()
        self.used_label.setWordWrap(True)
        self.edited_label = QLabel()
        self.edited_label.setWordWrap(True)
        self.discard = QPushButton("Discard changes")
        self.apply = QPushButton("Apply")
        for slot in range(SLOTS):
            self.slots.addItem(slot_text(slot, (), False))
        self.slots.setCurrentRow(0)

        editor = QFormLayout()
        editor.addRow("Type", self.kind)
        self.key_label = QLabel("Key")
        self.button_label = QLabel("Button")
        editor.addRow(self.key_label, self.key)
        editor.addRow(self.button_label, self.button)
        editor.addRow("Action", self.press)
        editor.addRow("Delay", self.delay)
        step_buttons = QGridLayout()
        for position, button in enumerate(
            (self.add, self.add_pair, self.replace, self.remove, self.up, self.down, self.clear)
        ):
            step_buttons.addWidget(button, position // 2, position % 2)
        right = QVBoxLayout()
        right.addWidget(self.steps, 1)
        right.addLayout(editor)
        right.addLayout(step_buttons)
        lists = QHBoxLayout()
        lists.addWidget(self.slots)
        lists.addLayout(right, 2)
        bottom = QHBoxLayout()
        bottom.addWidget(self.used_label, 1)
        bottom.addWidget(self.discard)
        bottom.addWidget(self.apply)
        layout = QVBoxLayout(self.body)
        layout.addWidget(self.explanation)
        layout.addLayout(lists, 1)
        layout.addWidget(self.edited_label)
        layout.addLayout(bottom)
        self.fill_height()
        self.body.setEnabled(False)  # the slots show the keyboard's macros only after the first read

        self.slots.currentRowChanged.connect(lambda row: self._show())
        self.steps.currentRowChanged.connect(self._on_step)
        self.kind.currentIndexChanged.connect(lambda index: self._show_kind())
        self.add.clicked.connect(self._add)
        self.add_pair.clicked.connect(self._add_pair)
        self.replace.clicked.connect(self._replace)
        self.remove.clicked.connect(self._remove)
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        self.clear.clicked.connect(lambda: self._store([], -1))
        self.discard.clicked.connect(self.discard_edits)
        self.apply.clicked.connect(self._apply)
        self._show_kind()
        self._show()

    def display(self, name: str, value) -> None:
        """A read or a write replaces the macros under the edits."""
        self._table.set_base(value.macros)
        self._show()

    def show_written(self, name: str, value) -> None:
        """The written block clears the edits that "Apply" sent and it holds."""
        if self._applied_edit is None:
            self._table.set_base(value.macros)
        else:
            self._table.set_written(value.macros, self._applied_edit)
        self._applied_edit = None
        self._show()

    def show_write_failed(self, name: str, message: str) -> None:
        self._applied_edit = None
        self._show()

    def show_connection(self, state) -> None:
        """Without a keyboard the queued write of "Apply" is dropped."""
        if state.status == "not_connected":
            self._applied_edit = None
            self._show()

    def discard_edits(self) -> None:
        self._table.discard()
        self._applied_edit = None
        self._show()

    def current_slot(self) -> int:
        return self.slots.currentRow()

    def _actions(self) -> list:
        return list(self._table.value(self.current_slot()))

    def _editor_action(self, press: bool | None = None) -> MacroAction:
        kind = self.kind.currentData()
        code = self.key.usage() if kind == KEYBOARD_ACTION else self.button.currentData()
        return MacroAction(self.delay.value(), code, self.press.currentData() if press is None else press, kind)

    def _add(self) -> None:
        actions = self._actions() + [self._editor_action()]
        self._store(actions, len(actions) - 1)

    def _add_pair(self) -> None:
        press = self._editor_action(press=True)
        actions = self._actions() + [press, dataclasses.replace(press, press=False)]
        self._store(actions, len(actions) - 1)

    def _replace(self) -> None:
        row = self.steps.currentRow()
        actions = self._actions()
        actions[row] = self._editor_action()
        self._store(actions, row)

    def _remove(self) -> None:
        row = self.steps.currentRow()
        actions = self._actions()
        del actions[row]
        self._store(actions, min(row, len(actions) - 1))

    def _move(self, step: int) -> None:
        row = self.steps.currentRow()
        actions = self._actions()
        actions[row], actions[row + step] = actions[row + step], actions[row]
        self._store(actions, row + step)

    def _store(self, actions: list, row: int) -> None:
        """Keep the actions as the edit of the current slot and select the step at `row` (-1 for none)."""
        self._table.edit(self.current_slot(), tuple(actions))
        self._show()
        self.steps.setCurrentRow(row)

    def _on_step(self, row: int) -> None:
        """Show the selected step in the editor. A type or a button the page does not name gets its number."""
        if row >= 0:
            action = self._actions()[row]
            select(self.kind, action.kind, f"Type {action.kind}")
            if action.kind == KEYBOARD_ACTION:
                self.key.set_usage(action.code)
            else:
                select(self.button, action.code, f"0x{action.code:02X}")
            self.press.setCurrentIndex(self.press.findData(action.press))
            self.delay.setValue(action.delay)
        self._update_step_buttons()

    def _show_kind(self) -> None:
        keyboard = self.kind.currentData() == KEYBOARD_ACTION
        self.key.setHidden(not keyboard)
        self.key_label.setHidden(not keyboard)
        self.button.setHidden(keyboard)
        self.button_label.setHidden(keyboard)

    def _apply(self) -> None:
        self._applied_edit = self._table.last_edit()
        self.update_requested.emit("macros", {"macros": self._table.changes()})
        self._show()

    def _show(self) -> None:
        edited = self._table.edited()
        for slot in range(SLOTS):
            self.slots.item(slot).setText(slot_text(slot, self._table.value(slot), slot in edited))
        self.steps.clear()
        for action in self._table.value(self.current_slot()):
            self.steps.addItem(step_text(action))
        used = body_size(self._table.value(slot) for slot in range(SLOTS))
        self.used_label.setText(used_text(used))
        self.edited_label.setText(edited_text(len(edited)))
        self.discard.setEnabled(bool(edited))
        self._update_apply()
        self._update_step_buttons()

    def _update_apply(self) -> None:
        edited = self._table.edited()
        used = body_size(self._table.value(slot) for slot in range(SLOTS))
        self.apply.setEnabled(
            bool(edited) and self._applied_edit is None and not self._import_running and used <= MACRO_SPACE
        )

    def _update_step_buttons(self) -> None:
        row, count = self.steps.currentRow(), self.steps.count()
        self.replace.setEnabled(row >= 0)
        self.remove.setEnabled(row >= 0)
        self.up.setEnabled(row > 0)
        self.down.setEnabled(0 <= row < count - 1)
        self.clear.setEnabled(count > 0)
