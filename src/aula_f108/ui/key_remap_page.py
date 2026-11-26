"""Page "Keys": the actions of the keys on the base layer and the Fn layer, written with "Apply"."""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from aula_f108.action_names import action_label
from aula_f108.blocks.key_tables import BASE, ENTRIES, FN, LAYERS, factory_tables
from aula_f108.edited_table import EditedTable
from aula_f108.key_actions import Default
from aula_f108.layout import load_layout
from aula_f108.ui.action_editor import ActionEditor
from aula_f108.ui.keyboard_widget import KeyboardWidget
from aula_f108.ui.page import Page
from aula_f108.ui.widgets import make_combo

LAYER_NAMES = {BASE: "Base layer", FN: "Fn layer"}
EXPLANATION = (
    "Click a key and assign it an action. The Fn layer action runs when the key is pressed together with Fn. "
    "The keys show the actions that differ from their usual assignment. “Apply” writes "
    "the changes to the keyboard."
)
NO_KEY = "Choose a key on the picture."
RESET_TITLE = "Restore defaults"
MODE_CHANGED = (
    "The Windows/macOS mode changed, so the unapplied key changes were discarded: in the other mode the Fn layer "
    "can be different."
)


def edited_text(count: int) -> str:
    return f"Keys changed: {count}. They are marked with a dot and not yet written to the keyboard." if count else ""


def reset_question(layer: str) -> str:
    return f"Restore the factory actions of all keys on the “{LAYER_NAMES[layer]}” and write them to the keyboard?"


class KeyRemapPage(Page):
    title = "Keys"
    blocks = (BASE, FN, "settings")

    def __init__(self):
        super().__init__()
        self._tables = {layer: EditedTable([Default()] * ENTRIES) for layer in LAYERS}
        # The newest edit that the pending write of a layer carries, None while no write of that layer is pending.
        # "Apply" and "Restore defaults" stay disabled while a write is pending.
        self._applied = dict.fromkeys(LAYERS)
        self._loaded = set()   # the layers read from the keyboard so far
        self._mac_mode = None  # the Win/Mac mode of the last settings value, None before the first one
        self._selected = None  # the key index chosen on the picture
        self.explanation = QLabel(EXPLANATION)
        self.explanation.setWordWrap(True)
        self.layer = make_combo(LAYER_NAMES)
        self.reset = QPushButton("Restore defaults…")
        self.discard = QPushButton("Discard changes")
        self.apply = QPushButton("Apply")
        self.keyboard = KeyboardWidget(load_layout())
        self.key_label = QLabel(NO_KEY)
        self.editor = ActionEditor()
        self.edited_label = QLabel()
        self.edited_label.setWordWrap(True)
        self.mode_note = QLabel(MODE_CHANGED)
        self.mode_note.setWordWrap(True)
        self.mode_note.hide()

        tools = QHBoxLayout()
        tools.addWidget(self.layer)
        tools.addWidget(self.reset)
        tools.addStretch(1)
        tools.addWidget(self.discard)
        tools.addWidget(self.apply)
        editing = QVBoxLayout()
        editing.addWidget(self.key_label)
        editing.addWidget(self.editor)
        bottom = QHBoxLayout()
        bottom.addLayout(editing, 1)
        notes = QVBoxLayout()
        notes.addWidget(self.edited_label)
        notes.addWidget(self.mode_note)
        notes.addStretch(1)
        bottom.addLayout(notes, 1)
        layout = QVBoxLayout(self.body)
        layout.addWidget(self.explanation)
        layout.addLayout(tools)
        layout.addWidget(self.keyboard, 1)
        layout.addLayout(bottom)
        self.fill_height()
        self.body.setEnabled(False)  # the keys show the keyboard's actions only after both tables are read

        self.layer.currentIndexChanged.connect(lambda index: self._show())
        self.keyboard.touched.connect(self._select)
        self.editor.action_chosen.connect(self._assign)
        self.discard.clicked.connect(self.discard_edits)
        self.apply.clicked.connect(self._apply)
        self.reset.clicked.connect(self._confirm_reset)
        self._show()

    def current_layer(self) -> str:
        return self.layer.currentData()

    def show_block(self, name: str, value) -> None:
        if name in LAYERS:
            self._loaded.add(name)
        super().show_block(name, value)

    def display(self, name: str, value) -> None:
        """A read replaces a table under its edits; a settings value may change the Win/Mac mode."""
        if name == "settings":
            self._show_mode(value.mac_mode)
        else:
            self._tables[name].set_base(value.actions)
        self._show()

    def show_written(self, name: str, value) -> None:
        """A written table clears the edits that its "Apply" sent and it holds."""
        if name not in LAYERS:
            super().show_written(name, value)
            return
        applied = self._applied[name]
        if applied is None:
            self._tables[name].set_base(value.actions)
        else:
            self._tables[name].set_written(value.actions, applied)
        self._applied[name] = None
        self._show()

    def show_write_failed(self, name: str, message: str) -> None:
        if name in LAYERS:
            self._applied[name] = None
            self._show()

    def show_connection(self, state) -> None:
        """Without a keyboard the queued writes of "Apply" are dropped."""
        if state.status == "not_connected":
            self._applied = dict.fromkeys(LAYERS)
            self._show()

    def discard_edits(self) -> None:
        for table in self._tables.values():
            table.discard()
        self._applied = dict.fromkeys(LAYERS)
        self.mode_note.hide()
        self._show()

    def _update_availability(self) -> None:
        super()._update_availability()
        self.body.setEnabled(not self._failed and self._loaded == set(LAYERS))

    def _show_mode(self, mac_mode: bool) -> None:
        """After a Win/Mac change the edits are discarded: they were made on the Fn layer of the other mode."""
        changed = self._mac_mode is not None and mac_mode != self._mac_mode
        self._mac_mode = mac_mode
        if changed and any(table.edited() for table in self._tables.values()):
            self.discard_edits()
            self.mode_note.show()

    def _select(self, index: int) -> None:
        self.keyboard.end_drag()
        self._selected = index
        self._show()

    def _assign(self, action) -> None:
        self._tables[self.current_layer()].edit(self._selected, action)
        self.mode_note.hide()
        self._show()

    def _apply(self) -> None:
        self._send([layer for layer in LAYERS if self._tables[layer].edited()])

    def _confirm_reset(self) -> None:
        layer = self.current_layer()
        answer = QMessageBox.question(
            self, RESET_TITLE, reset_question(layer),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        factory = factory_tables()[layer].actions
        for key in self.keyboard.keys:
            self._tables[layer].edit(key.index, factory[key.index])
        self._send([layer])

    def _send(self, layers) -> None:
        for layer in layers:
            table = self._tables[layer]
            self._applied[layer] = table.last_edit()
            self.update_requested.emit(layer, {"actions": table.changes()})
        self._show()

    def _key_name(self, index: int) -> str:
        key = next(key for key in self.keyboard.keys if key.index == index)
        return key.label or action_label(factory_tables()[BASE].actions[index])

    def _update_apply(self) -> None:
        edited = any(table.edited() for table in self._tables.values())
        pending = any(applied is not None for applied in self._applied.values())
        self.apply.setEnabled(edited and not pending and not self._import_running)
        self.reset.setEnabled(not pending and not self._import_running)

    def _show(self) -> None:
        layer = self.current_layer()
        table = self._tables[layer]
        own = factory_tables()[BASE].actions  # what each key does without remapping
        labels = {}
        for key in self.keyboard.keys:
            action = table.value(key.index)
            if action != own[key.index] and not isinstance(action, Default):
                labels[key.index] = action_label(action)
        self.keyboard.set_labels(labels)
        self.keyboard.set_marked(table.edited())
        self.keyboard.set_selected(self._selected)
        edited = sum(len(each.edited()) for each in self._tables.values())
        self.edited_label.setText(edited_text(edited))
        self.discard.setEnabled(edited > 0)
        self._update_apply()
        self.editor.setEnabled(self._selected is not None)
        if self._selected is None:
            self.key_label.setText(NO_KEY)
        else:
            self.key_label.setText(f"Key {self._key_name(self._selected)}, {LAYER_NAMES[layer]}")
            self.editor.show_action(table.value(self._selected))
