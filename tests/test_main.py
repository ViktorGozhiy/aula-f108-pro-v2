import logging
import os
import socket
import subprocess
import time
from pathlib import Path

from PyQt5.QtCore import QSettings

from aula_f108 import __main__ as entry
from simkeyboard import SimulatedKeyboard
from worker_rig import Rig

REPO = Path(__file__).resolve().parent.parent


def test_hotplug_event_makes_the_worker_probe(qtbot):
    sim = SimulatedKeyboard()
    sim.silent = True
    rig = Rig(cable=sim)
    rig.step()
    watcher = entry.start_hotplug(rig.worker)
    watcher.hidraw_changed.emit()
    rig.step()
    assert len(rig.opened) == 2
    watcher.close()


def test_missing_hotplug_events_are_logged(monkeypatch, caplog):
    def refused():
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(entry, "open_uevent_socket", refused)
    rig = Rig(cable=SimulatedKeyboard())
    with caplog.at_level(logging.WARNING, logger="aula_f108"):
        assert entry.start_hotplug(rig.worker) is None
    assert "hot-plug events are not available" in caplog.text


def test_main_runs_the_worker_and_cleans_up_after_the_event_loop(qtbot, tmp_path, monkeypatch):
    sim = SimulatedKeyboard()
    rig = Rig(cable=sim)
    reader, writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    reader.setblocking(False)
    logging_options = {}

    class FakeApplication:
        def __init__(self, argv):
            pass

        def setApplicationName(self, name):
            pass

        def setDesktopFileName(self, name):
            pass

        def exec(self):
            deadline = time.monotonic() + 2
            while not rig.opened and time.monotonic() < deadline:
                time.sleep(0.01)
            assert rig.opened
            return 7

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(entry, "QApplication", FakeApplication)
    monkeypatch.setattr(entry, "QSettings", lambda *args: settings)
    monkeypatch.setattr(entry, "DeviceWorker", lambda: rig.worker)
    monkeypatch.setattr(entry, "open_uevent_socket", lambda: reader)
    monkeypatch.setattr(entry.logging, "basicConfig", lambda **options: logging_options.update(options))
    assert entry.main() == 7
    assert logging_options["level"] == logging.INFO
    assert sim.closed
    assert reader.fileno() == -1
    writer.close()


def run_installer(env):
    subprocess.run(
        ["sh", str(REPO / "packaging" / "install-desktop-entry.sh")], env=env, check=True, capture_output=True
    )


def test_desktop_entry_is_installed_into_the_home_directory(tmp_path):
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}
    run_installer(env)
    entry_text = (tmp_path / ".local/share/applications/aula-f108.desktop").read_text()
    assert f"Exec={REPO}/aula-f108\n" in entry_text
    assert "@REPO@" not in entry_text


def test_desktop_entry_follows_xdg_data_home(tmp_path):
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"), "XDG_DATA_HOME": str(tmp_path / "data")}
    run_installer(env)
    assert (tmp_path / "data/applications/aula-f108.desktop").is_file()


def test_start_script_runs_the_package_with_the_system_python():
    script = (REPO / "aula-f108").read_text()
    assert "/usr/bin/python3 -m aula_f108" in script
    assert os.access(REPO / "aula-f108", os.X_OK)
