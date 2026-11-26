"""The editor of one key action, with a group for each kind of action, and the key picker it shares with the macros."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aula_f108.action_names import MODIFIER_NAMES, action_label, names
from aula_f108.key_actions import (
    COMBO_MODIFIERS,
    MACRO_SLOTS,
    MACRO_TIMES,
    TAP_HOLD_MAX_MS,
    TAP_HOLD_MIN_MS,
    TAP_HOLD_STEP_MS,
    Combo,
    Consumer,
    Default,
    Function,
    KeyboardKey,
    Macro,
    Mouse,
    Raw,
    TapHold,
    Toggle,
)
from aula_f108.ui.widgets import make_combo, signals_blocked

GROUPS = {
    "default": "Default",
    "keyboard": "Key",
    "media": "Media",
    "mouse": "Mouse",
    "macro": "Macro",
    "combo": "Combination",
    "tap_hold": "Tap and hold",
    "toggle": "Toggle",
    "function": "Keyboard function",
    "raw": "Other",
}
GROUP_OF = {
    Default: "default",
    KeyboardKey: "keyboard",
    Consumer: "media",
    Mouse: "mouse",
    Macro: "macro",
    Combo: "combo",
    TapHold: "tap_hold",
    Toggle: "toggle",
    Function: "function",
    Raw: "raw",
}
MACRO_MODE_NAMES = {0: "Once", 1: "A set number of times", 2: "Until the next press"}
NO_MODIFIER = 0
DEFAULT_HOLD_MS = 400  # the vendor's starting value
DEFAULT_TEXT = "The key performs the action set in the firmware."
COMBO_KEY_IS_MODIFIER = "The combination key cannot be a modifier: choose another key."


def raw_text(action: Raw) -> str:
    return (
        f"The program does not support the action {action_label(action)}. It can be replaced with another action; "
        "until it is replaced, it is written back unchanged."
    )


def mouse_code(kind: int, value: int) -> int:
    """The item data of a mouse action in the mouse choice."""
    return kind << 8 | value


def select(combo: QComboBox, value, name: str) -> None:
    """Select the item that holds `value`, adding one with `name` when the combo box has none."""
    index = combo.findData(value)
    if index < 0:
        combo.addItem(name, value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


class KeyPicker(QComboBox):
    """A choice of keyboard keys by name. The item data is the HID usage."""

    def __init__(self):
        super().__init__()
        for usage, name in names().keys.items():
            self.addItem(name, usage)

    def usage(self) -> int:
        return self.currentData()

    def set_usage(self, usage: int) -> None:
        select(self, usage, action_label(KeyboardKey(usage)))


class ActionEditor(QWidget):
    """Shows one key action and builds a new one. "Assign" emits action_chosen with the action shown."""

    action_chosen = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        all_names = names()
        self.group = make_combo(GROUPS)
        # An action the application does not model can be shown, but not chosen.
        self.group.model().item(self.group.findData("raw")).setEnabled(False)
        self.stack = QStackedWidget()
        self.default_text = QLabel(DEFAULT_TEXT)
        self.default_text.setWordWrap(True)
        self.key = KeyPicker()
        self.media = make_combo(all_names.media)
        self.mouse = make_combo({mouse_code(*action): name for action, name in all_names.mouse.items()})
        self.macro_slot = make_combo({slot: f"M{slot + 1}" for slot in range(MACRO_SLOTS)})
        self.macro_mode = make_combo(MACRO_MODE_NAMES)
        self.macro_count = QSpinBox()
        self.macro_count.setRange(1, 255)
        self.combo_first = make_combo(MODIFIER_NAMES)
        self.combo_second = make_combo({NO_MODIFIER: "None"} | MODIFIER_NAMES)
        self.combo_key = KeyPicker()
        self.tap_key = KeyPicker()
        self.hold_key = KeyPicker()
        self.hold_time = QSpinBox()
        self.hold_time.setRange(TAP_HOLD_MIN_MS, TAP_HOLD_MAX_MS)
        self.hold_time.setSingleStep(TAP_HOLD_STEP_MS)
        self.hold_time.setSuffix(" ms")
        self.hold_time.setValue(DEFAULT_HOLD_MS)
        self.toggle_key = KeyPicker()
        self.function = make_combo({id: all_names.functions[id] for id in all_names.offered_functions})
        self.raw_text = QLabel()
        self.raw_text.setWordWrap(True)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.assign = QPushButton("Assign")

        panels = {
            "default": [(None, self.default_text)],
            "keyboard": [("Key", self.key)],
            "media": [("Action", self.media)],
            "mouse": [("Action", self.mouse)],
            "macro": [("Macro", self.macro_slot), ("Run", self.macro_mode), ("Repeat count", self.macro_count)],
            "combo": [("Modifier", self.combo_first), ("Second modifier", self.combo_second), ("Key", self.combo_key)],
            "tap_hold": [("On tap", self.tap_key), ("On hold", self.hold_key), ("Hold longer than", self.hold_time)],
            "toggle": [("Key", self.toggle_key)],
            "function": [("Function", self.function)],
            "raw": [(None, self.raw_text)],
        }
        for group in GROUPS:  # the pages of the stack are in the order of the group choice
            panel = QWidget()
            form = QFormLayout(panel)
            for label, widget in panels[group]:
                if label is None:
                    form.addRow(widget)
                else:
                    form.addRow(label, widget)
            self.stack.addWidget(panel)
        top = QFormLayout()
        top.addRow("Action", self.group)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.assign)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.stack)
        layout.addWidget(self.error)
        layout.addLayout(buttons)

        self.group.currentIndexChanged.connect(lambda index: self._show_group())
        self.macro_mode.currentIndexChanged.connect(lambda index: self._show_macro_mode())
        self.assign.clicked.connect(self._assign)
        self._show_group()
        self._show_macro_mode()

    def show_action(self, action) -> None:
        """Show an action in its group, without emitting action_chosen."""
        with signals_blocked(self.group):
            self.group.setCurrentIndex(self.group.findData(GROUP_OF[type(action)]))
        self._show_group()
        if isinstance(action, KeyboardKey):
            self.key.set_usage(action.usage)
        elif isinstance(action, Consumer):
            select(self.media, action.usage, action_label(action))
        elif isinstance(action, Mouse):
            select(self.mouse, mouse_code(action.kind, action.value), action_label(action))
        elif isinstance(action, Macro):
            self.macro_slot.setCurrentIndex(self.macro_slot.findData(action.slot))
            self.macro_mode.setCurrentIndex(self.macro_mode.findData(action.mode))
            self.macro_count.setValue(action.count)
        elif isinstance(action, Combo):
            second = action.modifiers[1] if len(action.modifiers) > 1 else NO_MODIFIER
            self.combo_first.setCurrentIndex(self.combo_first.findData(action.modifiers[0]))
            self.combo_second.setCurrentIndex(self.combo_second.findData(second))
            self.combo_key.set_usage(action.usage)
        elif isinstance(action, TapHold):
            self.tap_key.set_usage(action.tap)
            self.hold_key.set_usage(action.hold)
            self.hold_time.setValue(action.time_ms)
        elif isinstance(action, Toggle):
            self.toggle_key.set_usage(action.usage)
        elif isinstance(action, Function):
            select(self.function, action.id, action_label(action))
        elif isinstance(action, Raw):
            self.raw_text.setText(raw_text(action))

    def action(self):
        """The action the controls describe; None in the group of actions the application does not model."""
        group = self.group.currentData()
        if group == "default":
            return Default()
        if group == "keyboard":
            return KeyboardKey(self.key.usage())
        if group == "media":
            return Consumer(self.media.currentData())
        if group == "mouse":
            code = self.mouse.currentData()
            return Mouse(code >> 8, code & 0xFF)
        if group == "macro":
            mode = self.macro_mode.currentData()
            return Macro(self.macro_slot.currentData(), mode, self.macro_count.value() if mode == MACRO_TIMES else 1)
        if group == "combo":
            modifiers = (self.combo_first.currentData(), self.combo_second.currentData())
            return Combo(tuple(modifier for modifier in modifiers if modifier != NO_MODIFIER), self.combo_key.usage())
        if group == "tap_hold":
            return TapHold(self.hold_key.usage(), self.tap_key.usage(), self.hold_time.value())
        if group == "toggle":
            return Toggle(self.toggle_key.usage())
        if group == "function":
            return Function(self.function.currentData())
        return None

    def _show_group(self) -> None:
        self.stack.setCurrentIndex(self.group.currentIndex())
        self.assign.setEnabled(self.group.currentData() != "raw")
        self.error.clear()

    def _show_macro_mode(self) -> None:
        self.macro_count.setEnabled(self.macro_mode.currentData() == MACRO_TIMES)

    def _assign(self) -> None:
        action = self.action()
        if isinstance(action, Combo) and action.usage in COMBO_MODIFIERS:
            self.error.setText(COMBO_KEY_IS_MODIFIER)
            return
        self.error.clear()
        self.action_chosen.emit(action)
