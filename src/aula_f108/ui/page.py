"""Base class of the sidebar pages."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class Page(QWidget):
    """Shows the blocks named in `blocks` and asks for changes to them with update_requested."""

    title = ""
    blocks: tuple[str, ...] = ()
    update_requested = pyqtSignal(str, object)  # block name, dict of changed fields
    page_requested = pyqtSignal(str)  # the title of another page to show

    def __init__(self):
        super().__init__()
        self._failed: set[str] = set()
        self._import_running = False
        self.failure_label = QLabel()
        self.failure_label.setWordWrap(True)
        self.failure_label.hide()
        self.body = QWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.failure_label)
        layout.addWidget(self.body)
        layout.addStretch(1)

    def show_block(self, name: str, value) -> None:
        """Show a value read from the keyboard. A successful read makes the page usable again."""
        self._failed.discard(name)
        self._update_availability()
        self.display(name, value)

    def show_written(self, name: str, value) -> None:
        """Show the value as it was written to the keyboard."""
        self.display(name, value)

    def show_write_failed(self, name: str, message: str) -> None:
        """Called when a requested write of a block was not written. Pages that wait for a write override it."""

    def show_failure(self, name: str, message: str) -> None:
        self._failed.add(name)
        self.failure_label.setText(message)
        self._update_availability()

    def show_connection(self, state) -> None:
        """Called on every connection change. Pages that depend on the connection type override it."""

    def show_import_running(self, running: bool) -> None:
        """Called when an import of the configuration starts and when it ends. While it runs, the pages that write a
        table with "Apply" cannot apply, because the import's own writes of that table come first."""
        self._import_running = running
        self._update_apply()

    def _update_apply(self) -> None:
        """Pages with an "Apply" button set whether it is enabled."""

    def discard_edits(self) -> None:
        """Called after the worker sent a factory reset. Pages with unapplied edits override it."""

    def fill_height(self) -> None:
        """Give the body the free height of the page, for pages whose main widget scales with the window."""
        layout = self.layout()
        layout.setStretch(layout.count() - 1, 0)
        layout.setStretchFactor(self.body, 1)

    def display(self, name: str, value) -> None:
        raise NotImplementedError

    def _update_availability(self) -> None:
        self.failure_label.setHidden(not self._failed)
        self.body.setEnabled(not self._failed)
