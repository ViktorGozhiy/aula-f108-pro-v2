"""The main window: sidebar of pages, the page stack and the status bar."""

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QWidget

from aula_f108.keyboard import BLOCKS
from aula_f108.ui.animation_controls import AnimationPage
from aula_f108.ui.backlight_page import BacklightPage
from aula_f108.ui.device_page import DevicePage
from aula_f108.ui.dot_matrix_page import DotMatrixPage
from aula_f108.ui.key_animation_page import KeyAnimationPage
from aula_f108.ui.key_colours_page import KeyColoursPage
from aula_f108.ui.key_remap_page import KeyRemapPage
from aula_f108.ui.light_box_page import LightBoxPage
from aula_f108.ui.macros_page import MacrosPage
from aula_f108.ui.not_connected_page import NotConnectedPage
from aula_f108.ui.profile_controller import ProfileController
from aula_f108.ui.settings_page import SettingsPage
from aula_f108.worker import SEARCHING, ConnectionState, DeviceWorker

CONNECTION_LABELS = {"cable": "Cable", "dongle": "2.4G"}
STATUS_MESSAGE_MS = 10000


class MainWindow(QMainWindow):
    def __init__(self, worker: DeviceWorker, settings: QSettings):
        super().__init__()
        self.setWindowTitle("AULA F108 Pro V2")
        self.resize(1100, 700)
        self._worker = worker
        self._settings = settings
        self._connection = None
        self.pages = self._create_pages()

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.stack = QStackedWidget()
        self.not_connected = NotConnectedPage()
        self.stack.addWidget(self.not_connected)
        for page in self.pages:
            self.sidebar.addItem(page.title)
            self.stack.addWidget(page)
            page.update_requested.connect(worker.request_update)
            page.page_requested.connect(self._open_page)
            if isinstance(page, AnimationPage):
                page.upload_requested.connect(worker.request_upload)
                page.cancel_upload_requested.connect(worker.request_cancel_upload)
        self.device_page.factory_reset_requested.connect(worker.request_factory_reset)
        worker.factory_reset_sent.connect(self._discard_edits)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.connection_label = QLabel()
        self.firmware_label = QLabel()
        self.battery_label = QLabel()
        for label in (self.battery_label, self.firmware_label, self.connection_label):
            self.statusBar().addPermanentWidget(label)

        worker.state_changed.connect(self._on_state)
        worker.block_read.connect(self._on_block_read)
        worker.block_written.connect(self._on_block_written)
        worker.block_failed.connect(self._on_block_failed)
        worker.write_failed.connect(self._on_write_failed)
        worker.upload_progress.connect(self._on_upload_progress)
        worker.upload_finished.connect(self._on_upload_finished)
        # Connected after the pages, so an export takes the colours the pages show for the blocks just read.
        self.profile = ProfileController(worker, self._shown_colours)
        self.device_page.export_requested.connect(self.profile.export_to)
        self.device_page.import_requested.connect(self.profile.import_from)
        self.profile.finished.connect(self.device_page.show_profile_result)
        self.profile.import_running.connect(self._show_import_running)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._on_page_selected)
        self._on_state(ConnectionState("not_connected", reason=SEARCHING))

    def _create_pages(self) -> list:
        self.device_page = DevicePage()
        return [
            BacklightPage(self._settings),
            KeyColoursPage(),
            KeyAnimationPage(),
            LightBoxPage(self._settings),
            DotMatrixPage(self._settings),
            KeyRemapPage(),
            MacrosPage(),
            SettingsPage(),
            self.device_page,
        ]

    def _page(self, page_type):
        return next(page for page in self.pages if isinstance(page, page_type))

    def _shown_colours(self) -> dict:
        return {
            "led_effect": self._page(BacklightPage).colour.colour(),
            "light_box": self._page(LightBoxPage).colour.colour(),
        }

    def _show_import_running(self, running: bool) -> None:
        for page in self.pages:
            page.show_import_running(running)

    def _discard_edits(self) -> None:
        for page in self.pages:
            page.discard_edits()

    def _open_page(self, title: str) -> None:
        self.sidebar.setCurrentRow([page.title for page in self.pages].index(title))

    def _on_state(self, state: ConnectionState) -> None:
        self._connection = state.connection
        connected = state.status == "connected"
        # Without a keyboard the status bar says why: searching, asleep, link lost, restarting, and so on.
        self.connection_label.setText(CONNECTION_LABELS[state.connection] if connected else state.reason)
        self.sidebar.setEnabled(connected)
        if connected:
            self.stack.setCurrentWidget(self.pages[self.sidebar.currentRow()])
        else:
            self.not_connected.show_reason(state.reason)
            self.stack.setCurrentWidget(self.not_connected)
            self.firmware_label.clear()
            self.battery_label.clear()
        for page in self.pages:
            page.show_connection(state)

    def _on_page_selected(self, row: int) -> None:
        if self._connection is None:
            return
        page = self.pages[row]
        self.stack.setCurrentWidget(page)
        for name in page.blocks:
            self._worker.request_read(name)

    def _on_block_read(self, name: str, value) -> None:
        for page in self.pages:
            if name in page.blocks:
                page.show_block(name, value)
        if name == "device_info":
            self._show_device_info(value)

    def _on_block_written(self, name: str, value) -> None:
        for page in self.pages:
            if name in page.blocks:
                page.show_written(name, value)

    def _on_block_failed(self, name: str, message: str) -> None:
        for page in self.pages:
            if name in page.blocks:
                page.show_failure(name, message)

    def _on_write_failed(self, name: str, message: str) -> None:
        self.statusBar().showMessage(message, STATUS_MESSAGE_MS)
        for page in self.pages:
            if name in page.blocks:
                page.show_write_failed(name, message)
        if name in BLOCKS:
            # Show what the keyboard has instead of the value that was not written.
            self._worker.request_read(name)

    def _animation_page(self, kind: str) -> AnimationPage:
        return next(page for page in self.pages if isinstance(page, AnimationPage) and page.upload_kind == kind)

    def _on_upload_progress(self, kind: str, sent: int, total: int) -> None:
        self._animation_page(kind).show_upload_progress(sent, total)

    def _on_upload_finished(self, kind: str, outcome: str) -> None:
        self._animation_page(kind).show_upload_finished(outcome)

    def _show_device_info(self, info) -> None:
        self.firmware_label.setText(f"Firmware V{info.firmware}")
        if self._connection == "dongle":
            text = f"Battery {info.battery} %" + (", charging" if info.charging else "")
        else:
            text = "Charging" if info.charging else ""
        self.battery_label.setText(text)
