"""Export and import of the configuration through the device worker, started from the device page."""
from PyQt5.QtCore import QObject, pyqtSignal

from aula_f108 import profile
from aula_f108.keyboard import BLOCKS
from aula_f108.profile import EXPORTED_BLOCKS, ProfileError

BLOCK_NAMES = {
    "settings": "settings", "led_effect": "backlight", "light_box": "side lighting",
    "key_colours": "key colours", "base_keys": "base layer", "fn_keys": "Fn layer", "macros": "macros",
}
NOTHING_TO_IMPORT = "The file holds no settings to write."


class ProfileController(QObject):
    """Export reads the blocks fresh and writes the file; import writes the file's blocks and reads every block again.

    `colours()` returns the colours of "led_effect" and "light_box" that the pages show, because the keyboard does
    not report a colour the application wrote. `finished` carries the outcome for the user. `import_running` is True
    from the moment the import's writes are queued and False once the import is reported as finished or failed.
    """

    finished = pyqtSignal(str)
    import_running = pyqtSignal(bool)

    def __init__(self, worker, colours):
        super().__init__()
        self._worker = worker
        self._colours = colours
        self._export_path = None    # the file of the running export
        self._export_values = {}    # the blocks read for it so far
        self._import_results = None  # block name -> None while its write runs, "" when written, else the message
        self._import_batch = None    # the id the worker gave the import's writes
        worker.block_read.connect(self._on_read)
        worker.block_failed.connect(self._on_read_failed)
        worker.batch_update_finished.connect(self._on_import_result)
        worker.state_changed.connect(self._on_state)

    def export_to(self, path: str) -> None:
        self._export_path = path
        self._export_values = {}
        for name in EXPORTED_BLOCKS:
            self._worker.request_read(name)

    def import_from(self, path: str) -> None:
        try:
            changes = profile.import_changes(profile.load(path))
        except ProfileError as error:
            self.finished.emit(f"Settings not loaded: {error}.")
            return
        if not changes:
            self.finished.emit(NOTHING_TO_IMPORT)
            return
        self._import_results = {name: None for name, _block_changes in changes}
        self.import_running.emit(True)
        self._import_batch = self._worker.request_updates(changes)

    def _on_read(self, name: str, value) -> None:
        if self._export_path is None or name not in EXPORTED_BLOCKS:
            return
        self._export_values[name] = value
        if len(self._export_values) < len(EXPORTED_BLOCKS):
            return
        path, self._export_path = self._export_path, None
        try:
            profile.save(path, profile.export_profile(self._export_values, self._colours()))
        except OSError as error:
            self.finished.emit(f"Settings not saved: {error}.")
            return
        self.finished.emit(f"Settings saved to {path}.")

    def _on_read_failed(self, name: str, message: str) -> None:
        if self._export_path is not None and name in EXPORTED_BLOCKS:
            self._export_path = None
            self.finished.emit(f"Settings not saved: could not read “{BLOCK_NAMES[name]}”. {message}")

    def _on_import_result(self, batch: int, name: str, written: bool, message: str) -> None:
        """Record the outcome of one write of the running import. The worker reports every write of the import's
        batch, also one it drops, so only the import's own writes count: a page's write queued before, during or
        after the import is not taken for the import's."""
        if self._import_results is None or batch != self._import_batch:
            return
        self._import_results[name] = "" if written else message
        if all(result is not None for result in self._import_results.values()):
            self._finish_import()
            for block in BLOCKS:
                self._worker.request_read(block)

    def _on_state(self, state) -> None:
        """Without a keyboard nothing more arrives. The reconnect reads every block again."""
        if state.status == "connected":
            return
        if self._export_path is not None:
            self._export_path = None
            self.finished.emit(f"Settings not saved: {state.reason}.")
        if self._import_results is not None:
            for name, result in self._import_results.items():
                if result is None:
                    self._import_results[name] = state.reason
            self._finish_import()

    def _finish_import(self) -> None:
        results, self._import_results, self._import_batch = self._import_results, None, None
        self.import_running.emit(False)
        written = [BLOCK_NAMES[name] for name, result in results.items() if result == ""]
        failed = [f"{BLOCK_NAMES[name]} ({result})" for name, result in results.items() if result != ""]
        texts = []
        if written:
            texts.append(f"Written: {', '.join(written)}.")
        if failed:
            texts.append(f"Not written: {'; '.join(failed)}.")
        self.finished.emit(" ".join(texts))
