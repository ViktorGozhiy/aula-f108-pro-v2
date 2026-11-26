"""Page "Settings": polling rate, sleep, debounce, Win/Mac mode and Win-key lock (settings block)."""

from PyQt5.QtWidgets import QCheckBox, QFormLayout, QLabel, QSpinBox

from aula_f108.blocks.settings import POLLING_RATES_HZ
from aula_f108.ui.page import Page
from aula_f108.ui.widgets import make_combo, signals_blocked

SYSTEM_NAMES = {False: "Windows", True: "macOS"}
RATE_NOTE = "Polling rate over the cable. When it changes, the keyboard on the cable restarts and reconnects."
SYSTEM_NOTE = (
    "When the system changes, unapplied changes on the “Keys” page are discarded: the Fn layer can depend on the "
    "system."
)


def rate_label(hz: int) -> str:
    return f"{hz} Hz" if hz < 1000 else f"{hz // 1000} kHz"


class SettingsPage(Page):
    title = "Settings"
    blocks = ("settings",)

    def __init__(self):
        super().__init__()
        self.polling_rate = make_combo({index: rate_label(hz) for index, hz in enumerate(POLLING_RATES_HZ)})
        self.rate_note = QLabel(RATE_NOTE)
        self.rate_note.setWordWrap(True)
        self.sleep = QSpinBox()
        self.sleep.setRange(0, 30)
        self.sleep.setSpecialValueText("Never")
        self.sleep.setSuffix(" min")
        self.sleep.setKeyboardTracking(False)
        self.debounce = QSpinBox()
        self.debounce.setRange(1, 5)
        self.debounce.setKeyboardTracking(False)
        self.system = make_combo(SYSTEM_NAMES)
        self.system_note = QLabel(SYSTEM_NOTE)
        self.system_note.setWordWrap(True)
        self.win_lock = QCheckBox("Win key lock")

        form = QFormLayout(self.body)
        form.addRow("Polling rate (cable)", self.polling_rate)
        form.addRow(self.rate_note)
        form.addRow("Sleep after", self.sleep)
        form.addRow("Debounce", self.debounce)
        form.addRow("System", self.system)
        form.addRow(self.system_note)
        form.addRow("", self.win_lock)

        self.polling_rate.currentIndexChanged.connect(
            lambda index: self._request(polling_rate=self.polling_rate.itemData(index))
        )
        self.sleep.valueChanged.connect(lambda value: self._request(sleep_minutes=value))
        self.debounce.valueChanged.connect(lambda value: self._request(debounce=value))
        self.system.currentIndexChanged.connect(lambda index: self._request(mac_mode=self.system.itemData(index)))
        self.win_lock.toggled.connect(lambda checked: self._request(win_lock=checked))

    def display(self, name: str, settings) -> None:
        with signals_blocked(self.polling_rate, self.sleep, self.debounce, self.system, self.win_lock):
            self.polling_rate.setCurrentIndex(self.polling_rate.findData(settings.polling_rate))
            self.sleep.setValue(settings.sleep_minutes)
            self.debounce.setValue(settings.debounce)
            self.system.setCurrentIndex(self.system.findData(settings.mac_mode))
            self.win_lock.setChecked(settings.win_lock)

    def _request(self, **changes) -> None:
        self.update_requested.emit("settings", changes)
