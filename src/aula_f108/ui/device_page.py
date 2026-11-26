"""Page "Device": model, connection, firmware, battery, the configuration file and the factory reset."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton

from aula_f108.ui.page import Page

MODEL = "AULA F108 Pro V2"
CONNECTION_NAMES = {"cable": "Cable (USB)", "dongle": "2.4G (dongle)"}
RESET_TITLE = "Factory reset"
RESET_QUESTION = (
    "All keyboard settings return to the factory defaults: backlight, key assignments, macros and settings. Continue?"
)
PROFILE_NOTE = (
    "The file holds the settings, the backlight, the side lighting, the key colours, the key assignments of both "
    "layers and the macros. Animations and the 7×7 display are not saved. Loading writes the settings from the file "
    "to the keyboard."
)
PROFILE_FILTER = "Keyboard settings (*.json)"
PROFILE_RUNNING = "Running…"


def ask_export_path(parent) -> str:
    """Ask where to save the configuration. Returns an empty string when the user cancels."""
    path, _selected_filter = QFileDialog.getSaveFileName(parent, "Save settings", "aula-f108.json", PROFILE_FILTER)
    return path


def ask_import_path(parent) -> str:
    """Ask for a configuration file. Returns an empty string when the user cancels."""
    path, _selected_filter = QFileDialog.getOpenFileName(parent, "Load settings", "", PROFILE_FILTER)
    return path


class DevicePage(Page):
    title = "Device"
    blocks = ("device_info",)
    factory_reset_requested = pyqtSignal()
    export_requested = pyqtSignal(str)  # the file to save the configuration to
    import_requested = pyqtSignal(str)  # the file to load the configuration from

    def __init__(self):
        super().__init__()
        self.model_value = QLabel(MODEL)
        self.connection_value = QLabel("—")
        self.firmware_value = QLabel("—")
        self.battery_label = QLabel("Battery")
        self.battery_value = QLabel("—")
        self.charge_value = QLabel("—")
        self.profile_note = QLabel(PROFILE_NOTE)
        self.profile_note.setWordWrap(True)
        self.export_button = QPushButton("Save settings to file…")
        self.import_button = QPushButton("Load settings from file…")
        self.profile_result = QLabel()
        self.profile_result.setWordWrap(True)
        self.reset_button = QPushButton("Factory reset…")

        form = QFormLayout(self.body)
        form.addRow("Model", self.model_value)
        form.addRow("Connection", self.connection_value)
        form.addRow("Firmware", self.firmware_value)
        form.addRow(self.battery_label, self.battery_value)
        form.addRow("Charging", self.charge_value)
        form.addRow(self.profile_note)
        profile_buttons = QHBoxLayout()
        profile_buttons.addWidget(self.export_button)
        profile_buttons.addWidget(self.import_button)
        profile_buttons.addStretch(1)
        form.addRow(profile_buttons)
        form.addRow(self.profile_result)
        form.addRow(self.reset_button)

        self.export_button.clicked.connect(self._export)
        self.import_button.clicked.connect(self._import)
        self.reset_button.clicked.connect(self._confirm_reset)

    def show_connection(self, state) -> None:
        self.connection_value.setText(CONNECTION_NAMES.get(state.connection, "—"))
        on_dongle = state.connection == "dongle"
        self.battery_label.setVisible(on_dongle)
        self.battery_value.setVisible(on_dongle)

    def display(self, name: str, info) -> None:
        self.model_value.setText(f"{MODEL} ({info.vid:04x}:{info.pid:04x})")
        self.firmware_value.setText(f"V{info.firmware}")
        self.battery_value.setText(f"{info.battery} %")
        self.charge_value.setText("charging" if info.charging else "not charging")

    def show_profile_result(self, text: str) -> None:
        """Show how the export or the import ended and allow the next one."""
        self.profile_result.setText(text)
        self.export_button.setEnabled(True)
        self.import_button.setEnabled(True)

    def _export(self) -> None:
        path = ask_export_path(self)
        if path:
            self._start_profile()
            self.export_requested.emit(path)

    def _import(self) -> None:
        path = ask_import_path(self)
        if path:
            self._start_profile()
            self.import_requested.emit(path)

    def _start_profile(self) -> None:
        self.profile_result.setText(PROFILE_RUNNING)
        self.export_button.setEnabled(False)
        self.import_button.setEnabled(False)

    def _confirm_reset(self) -> None:
        answer = QMessageBox.question(
            self,
            RESET_TITLE,
            RESET_QUESTION,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.factory_reset_requested.emit()
