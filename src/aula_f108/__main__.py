"""Start the configurator: python -m aula_f108."""
import logging
import sys

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from aula_f108.hotplug import HotplugWatcher, open_uevent_socket
from aula_f108.ui.main_window import MainWindow
from aula_f108.worker import DeviceWorker, WorkerThread

log = logging.getLogger("aula_f108")


def start_hotplug(worker: DeviceWorker) -> HotplugWatcher | None:
    """Probe at once on hidraw add and remove events. Without them, a lost keyboard is still probed every 3 s."""
    try:
        sock = open_uevent_socket()
    except OSError as error:
        log.warning("hot-plug events are not available: %s", error)
        return None
    watcher = HotplugWatcher(sock)
    watcher.hidraw_changed.connect(worker.request_probe)
    return watcher


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("aula-f108")
    app.setDesktopFileName("aula-f108")
    settings = QSettings("aula-f108", "aula-f108")
    worker = DeviceWorker()
    window = MainWindow(worker, settings)
    watcher = start_hotplug(worker)
    thread = WorkerThread(worker)
    thread.start()
    window.show()
    try:
        return app.exec()
    finally:
        thread.stop()
        if watcher is not None:
            watcher.close()


if __name__ == "__main__":
    sys.exit(main())
