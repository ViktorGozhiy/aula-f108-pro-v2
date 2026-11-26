"""A MainWindow on a worker rig, with settings in a temporary file."""

from PyQt5.QtCore import QSettings

from aula_f108.ui.main_window import MainWindow
from worker_rig import Rig


def make_window(qtbot, tmp_path, **devices):
    rig = Rig(**devices)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(rig.worker, settings)
    qtbot.addWidget(window)
    return window, rig, settings


def page_of(window, page_type):
    """The window's page of the given class."""
    return next(page for page in window.pages if isinstance(page, page_type))
