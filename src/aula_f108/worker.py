"""Device I/O in one thread: connection by probing, block reads, merged writes and notifications."""
import logging
import itertools
import threading
import time
from dataclasses import dataclass

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from aula_f108.blocks.key_tables import LAYERS
from aula_f108.blocks.led_effect import ANIMATION_SETUP
from aula_f108.hidraw import DeviceBusy, DeviceGone, HidrawDevice, find_command_interfaces
from aula_f108.keyboard import BLOCKS, Keyboard
from aula_f108.protocol import Protocol, TransferError

log = logging.getLogger(__name__)

PROBE_INTERVAL = 3.0
BATTERY_INTERVAL = 30.0
IDLE_WAIT = 0.05
ERROR_PAUSE = 1.0  # seconds the worker thread waits after an unexpected exception, so a repeated one does not flood the log

LINK_LOST = b"\x55\xfc\x04"
RESET = b"\x55\xfc\x05"
SLEEP = b"\x55\xfc\x06"
LINK_WOKE = b"\xa6\xff\x01"

SEARCHING = "Searching for the keyboard…"
NOT_FOUND = "Keyboard not found"
BUSY = "Another copy of the program is using the keyboard"
GONE = "Keyboard disconnected"
NO_REPLY = "Keyboard not responding"
ASLEEP = "Keyboard is asleep"
# The dongle reports a sleeping keyboard with 55 FC 04, the same as a switched-off one.
LINK_LOST_TEXT = "Keyboard out of reach: asleep or switched off. Press any key to wake it"
RESTARTING = "Keyboard is restarting"
READ_FAILED = "The keyboard did not answer the read. Open the page again to retry."
NOT_WRITTEN = "Change not written"
FACTORY_RESET_REQUEST = "factory_reset"
KEY_ANIMATION = "key_animation"
DOT_MATRIX_ANIMATION = "dot_matrix_animation"
UPLOAD_DONE = "done"
UPLOAD_CANCELLED = "cancelled"
UPLOAD_FAILED = "failed"
# The blocks read again after a Win/Mac change, as the vendor does: the Fn layer may differ between the modes.
MODE_BLOCKS = ("settings", *LAYERS)


@dataclass(frozen=True)
class ConnectionState:
    status: str                    # "connected", "not_connected" or "busy"
    connection: str | None = None  # "cable" or "dongle" while connected
    reason: str = ""               # why no keyboard is connected, shown to the user


@dataclass
class _Read:
    block: str


@dataclass
class _Update:
    block: str
    changes: dict
    ordered: bool = False  # written after the requests before it and before the ones after it: no merge across it
    batch: int | None = None  # the id of the batch of ordered writes it belongs to, reported when it finishes


@dataclass
class _FactoryReset:
    pass


@dataclass
class _Upload:
    kind: str
    payload: bytes


@dataclass(frozen=True)
class UploadKind:
    cmd: int
    led_effect: dict | None  # LED effect changes written before the frames


UPLOADS = {
    KEY_ANIMATION: UploadKind(0x42, ANIMATION_SETUP),
    DOT_MATRIX_ANIMATION: UploadKind(0x41, None),
}


class DeviceWorker(QObject):
    """Owns the open command interface. The UI calls the request methods; results come back as signals."""

    state_changed = pyqtSignal(object)       # ConnectionState
    block_read = pyqtSignal(str, object)     # block name, decoded value
    block_failed = pyqtSignal(str, str)      # block name, message: the block could not be read
    block_written = pyqtSignal(str, object)  # block name, decoded value as written
    write_failed = pyqtSignal(str, str)      # block name or "factory_reset", message
    batch_update_finished = pyqtSignal(int, str, bool, str)  # batch id, block, written, message of each batch request
    upload_progress = pyqtSignal(str, int, int)  # upload kind, chunks sent, chunk count
    upload_finished = pyqtSignal(str, str)       # upload kind, UPLOAD_DONE, UPLOAD_CANCELLED or UPLOAD_FAILED
    factory_reset_sent = pyqtSignal()        # the factory reset was sent: unapplied edits of the pages are void

    def __init__(self, find_interfaces=find_command_interfaces, open_device=HidrawDevice,
                 time_scale: float = 1.0, clock=time.monotonic, idle_wait: float = IDLE_WAIT):
        super().__init__()
        self._find_interfaces = find_interfaces
        self._open_device = open_device
        self._time_scale = time_scale
        self._clock = clock
        self._idle_wait = idle_wait
        self._condition = threading.Condition()
        self._requests = []
        self._batch_ids = itertools.count(1)
        self._probe_now = True
        self._notifications = []
        # The open command interface stays open while it gives no I/O error, also when the keyboard
        # behind it stops answering, so notifications such as "link woke" still arrive.
        self._device = None
        self._path = None
        self._protocol = None
        self._bulk_device = None   # the cable's separate bulk upload interface, while it is open
        self._bulk_path = None
        self._bulk = None          # Protocol over the bulk interface
        # One cancel flag per upload kind, so a cancel on one page never stops or is cleared by the other page.
        self._cancel_upload = {kind: threading.Event() for kind in UPLOADS}
        self._keyboard = None      # set only while the keyboard answers
        self._connection = None    # "cable" or "dongle", set only while the keyboard answers
        self._reason = NOT_FOUND
        self._state = None
        self._next_probe = 0.0
        self._next_battery = 0.0

    # Requests, called from the UI thread.

    def request_read(self, block: str) -> None:
        self._check_block(block)
        self._enqueue(_Read(block))

    def request_update(self, block: str, changes: dict) -> None:
        """Queue a write of the changed fields. A queued write of the same block takes the newer values."""
        self._check_block(block)
        with self._condition:
            for request in reversed(self._requests):
                if isinstance(request, (_FactoryReset, _Upload)) or (isinstance(request, _Update) and request.ordered):
                    break
                if isinstance(request, _Update) and request.block == block:
                    _merge(request.changes, changes)
                    return
            self._requests.append(_Update(block, dict(changes)))
            self._condition.notify_all()

    def request_updates(self, updates: list) -> int:
        """Queue writes [(block, changes)] to run in this order. No queued write merges into them or past them.
        Returns the id of the batch: `batch_update_finished` reports every one of these writes with it, also when
        the write is dropped because the keyboard is lost."""
        for block, _changes in updates:
            self._check_block(block)
        with self._condition:
            batch = next(self._batch_ids)
            self._requests.extend(
                _Update(block, dict(changes), ordered=True, batch=batch) for block, changes in updates)
            self._condition.notify_all()
        return batch

    def request_factory_reset(self) -> None:
        self._enqueue(_FactoryReset())

    def request_upload(self, kind: str, payload: bytes) -> None:
        """Queue a bulk upload of an animation. A new upload clears an earlier cancel of the same kind."""
        if kind not in UPLOADS:
            raise KeyError(f"unknown upload {kind!r}")
        self._cancel_upload[kind].clear()
        self._enqueue(_Upload(kind, bytes(payload)))

    def request_cancel_upload(self, kind: str) -> None:
        """Stop the running or queued upload of this kind before its next chunk."""
        self._cancel_upload[kind].set()

    def cancel_uploads(self) -> None:
        """Stop every running or queued upload before its next chunk, as when the application closes."""
        for cancel in self._cancel_upload.values():
            cancel.set()

    def request_probe(self) -> None:
        with self._condition:
            self._probe_now = True
            self._condition.notify_all()

    # The worker loop.

    def run_once(self) -> None:
        """One step: probe while no keyboard answers, otherwise handle one request or read notifications."""
        if self._connection is None:
            self._run_disconnected()
        else:
            self._run_connected()
        self._handle_notifications()

    def shutdown(self) -> None:
        self._close_device()

    def _run_disconnected(self) -> None:
        self._drop_requests(f"{NOT_WRITTEN}. Keyboard not connected.")
        if self._take_probe_due():
            self._connect()
        elif self._device is not None:
            self._poll()
        else:
            with self._condition:
                self._condition.wait(self._idle_wait)

    def _run_connected(self) -> None:
        if self._take_probe_request():
            self._alive()
            return
        request = self._take_request()
        if request is not None:
            self._handle(request)
        elif self._connection == "dongle" and self._clock() >= self._next_battery:
            self._next_battery = self._clock() + BATTERY_INTERVAL
            self._read("device_info")
        else:
            self._poll()

    def _connect(self) -> None:
        self._next_probe = self._clock() + PROBE_INTERVAL
        busy = False
        for interface in self._find_interfaces():
            reused = interface.path == self._path
            if reused:
                device = self._device
            else:
                try:
                    device = self._open_device(interface.path, interface.report_size)
                except DeviceBusy:
                    busy = True
                    continue
                except OSError:
                    continue  # no permission yet or the node went away; the next probe retries
            protocol = Protocol(device, self._note, self._time_scale)
            try:
                raw = protocol.read_block(BLOCKS["device_info"].read_cmd, BLOCKS["device_info"].size)
            except TransferError:
                if not reused:
                    device.close()
                continue
            except DeviceGone:
                if reused:
                    self._close_device()
                else:
                    device.close()
                continue
            self._use(device, interface, protocol)
            self.block_read.emit("device_info", BLOCKS["device_info"].decode(raw))
            self._read_all(skip="device_info")
            return
        if busy:
            self._set_state(ConnectionState("busy", reason=BUSY))
        else:
            self._set_state(ConnectionState("not_connected", reason=self._reason))

    def _use(self, device, interface, protocol) -> None:
        if self._device is not None and self._device is not device:
            self._device.close()
        self._device, self._path, self._protocol = device, interface.path, protocol
        if interface.bulk_path != self._bulk_path:
            self._close_bulk()
            self._open_bulk(interface)
        self._keyboard, self._connection = Keyboard(protocol), interface.connection
        self._next_battery = self._clock() + BATTERY_INTERVAL
        self._set_state(ConnectionState("connected", interface.connection))

    def _open_bulk(self, interface) -> None:
        """Open the separate bulk interface. Without it uploads go to the command interface, as the vendor does."""
        if interface.bulk_path is None:
            return
        try:
            device = self._open_device(interface.bulk_path, interface.bulk_report_size)
        except (DeviceBusy, OSError) as error:
            log.warning("bulk interface %s not opened, uploads use the command interface: %s",
                        interface.bulk_path, error)
            return
        self._bulk_device, self._bulk_path = device, interface.bulk_path
        self._bulk = Protocol(device, self._note, self._time_scale)

    def _handle(self, request) -> None:
        if isinstance(request, _Read):
            self._read(request.block)
        elif isinstance(request, _Update):
            self._update(request.block, request.changes, request.batch)
        elif isinstance(request, _Upload):
            self._upload(request.kind, request.payload)
        else:
            self._factory_reset()

    def _read_all(self, skip: str | None = None) -> None:
        for name in BLOCKS:
            if self._connection is None:
                return
            if name != skip:
                self._read(name)

    def _read(self, name: str) -> None:
        block = BLOCKS[name]
        try:
            raw = self._keyboard.read(block)
        except DeviceGone:
            self._lose(GONE, close=True)
            return
        except TransferError:
            if self._alive():
                self.block_failed.emit(name, READ_FAILED)
            return
        self.block_read.emit(name, block.decode(raw))

    def _update(self, name: str, changes: dict, batch: int | None = None) -> bool:
        """Write the changes onto a fresh read of the block. Returns True when the block was written.
        The request of a batch is also reported with `batch_update_finished`."""
        block = BLOCKS[name]
        try:
            written = self._keyboard.read_with_changes(block, changes)
        except ValueError as error:
            message = f"{NOT_WRITTEN}. {error}"
            self.write_failed.emit(name, message)
            self._finish_batch_update(batch, name, False, message)
            return False
        except (TransferError, DeviceGone) as error:
            self._finish_batch_update(batch, name, False, self._report_unwritten(name, error))
            return False
        try:
            self._keyboard.write(block, written)
        except (TransferError, DeviceGone) as error:
            if self._resets_keyboard(name, changes):
                self._lose(RESTARTING, close=True)
                self._finish_batch_update(batch, name, False, f"{NOT_WRITTEN}. {RESTARTING}.")
            else:
                self._finish_batch_update(batch, name, False, self._report_unwritten(name, error))
            return False
        self.block_written.emit(name, block.decode(written))
        self._finish_batch_update(batch, name, True, "")
        if name == "settings" and "mac_mode" in changes:
            for reread in MODE_BLOCKS:
                if self._connection is None:
                    break
                self._read(reread)
        return True

    def _upload(self, kind: str, payload: bytes) -> None:
        """Write the LED effect the upload needs, then send the frames on the bulk interface."""
        upload = UPLOADS[kind]
        cancel = self._cancel_upload[kind]
        if cancel.is_set():
            self.upload_finished.emit(kind, UPLOAD_CANCELLED)
            return
        if upload.led_effect is not None and not self._update("led_effect", dict(upload.led_effect)):
            self.upload_finished.emit(kind, UPLOAD_FAILED)
            return
        protocol = self._bulk if self._bulk is not None else self._protocol
        try:
            sent = protocol.upload(
                upload.cmd, payload,
                progress=lambda done, total: self.upload_progress.emit(kind, done, total),
                cancelled=cancel.is_set,
            )
        except (TransferError, DeviceGone) as error:
            self._report_unwritten(kind, error)
            self.upload_finished.emit(kind, UPLOAD_FAILED)
            return
        self.upload_finished.emit(kind, UPLOAD_DONE if sent else UPLOAD_CANCELLED)

    def _finish_batch_update(self, batch: int | None, name: str, written: bool, message: str) -> None:
        if batch is not None:
            self.batch_update_finished.emit(batch, name, written, message)

    def _report_unwritten(self, name: str, error: Exception) -> str:
        """An I/O error loses the keyboard; a missing reply probes it and keeps the connection when it answers.
        Returns the message reported."""
        if isinstance(error, DeviceGone):
            self._lose(GONE, close=True)
            message = f"{NOT_WRITTEN}. {GONE}."
        else:
            self._alive()
            message = f"{NOT_WRITTEN}. The keyboard did not answer."
        self.write_failed.emit(name, message)
        return message

    def _resets_keyboard(self, name: str, changes: dict) -> bool:
        """A polling-rate write on the cable restarts the keyboard, so a missing reply to the write is expected."""
        return name == "settings" and "polling_rate" in changes and self._connection == "cable"

    def _factory_reset(self) -> None:
        try:
            replied = self._keyboard.factory_reset()
        except DeviceGone:
            replied = False  # treated as the restart after the reset, so the reset counts as sent
        self.factory_reset_sent.emit()
        if replied:
            self._read_all()
        else:
            self._lose(RESTARTING, close=True)

    def _alive(self) -> bool:
        """Probe with GET_DEVICE_INFO on the same interface; when it fails, the keyboard counts as lost."""
        try:
            self._keyboard.read(BLOCKS["device_info"])
        except DeviceGone:
            self._lose(GONE, close=True)
            return False
        except TransferError:
            self._lose(NO_REPLY, close=False)
            return False
        return True

    def _lose(self, reason: str, close: bool) -> None:
        """The keyboard stopped answering: report it, drop queued requests and probe every 3 s."""
        if close:
            self._close_device()
        self._keyboard = self._connection = None
        self._reason = reason
        self._next_probe = self._clock() + PROBE_INTERVAL
        self._set_state(ConnectionState("not_connected", reason=reason))
        self._drop_requests(f"{NOT_WRITTEN}. {reason}.")

    def _poll(self) -> None:
        try:
            self._protocol.poll(self._idle_wait)
        except DeviceGone:
            if self._connection is not None:
                self._lose(GONE, close=True)
            else:
                self._close_device()

    def _close_device(self) -> None:
        if self._device is not None:
            self._device.close()
        self._device = self._path = self._protocol = None
        self._close_bulk()

    def _close_bulk(self) -> None:
        if self._bulk_device is not None:
            self._bulk_device.close()
        self._bulk_device = self._bulk_path = self._bulk = None

    def _note(self, report: bytes) -> None:
        self._notifications.append(report)

    def _handle_notifications(self) -> None:
        reports = list(self._notifications)
        self._notifications.clear()
        for report in reports:
            log.info("notification %s", report[:8].hex(" "))
            prefix = report[:3]
            if prefix in (SLEEP, LINK_LOST):
                if self._connection is not None:
                    self._lose(ASLEEP if prefix == SLEEP else LINK_LOST_TEXT, close=False)
            elif prefix == LINK_WOKE:
                self.request_probe()
            elif prefix == RESET and self._connection is not None:
                self._read_all()

    def _take_probe_due(self) -> bool:
        with self._condition:
            due = self._probe_now or self._clock() >= self._next_probe
            self._probe_now = False
        return due

    def _take_probe_request(self) -> bool:
        with self._condition:
            requested, self._probe_now = self._probe_now, False
        return requested

    def _check_block(self, block: str) -> None:
        if block not in BLOCKS:
            raise KeyError(f"unknown block {block!r}")

    def _enqueue(self, request) -> None:
        with self._condition:
            self._requests.append(request)
            self._condition.notify_all()

    def _take_request(self):
        with self._condition:
            return self._requests.pop(0) if self._requests else None

    def _drop_requests(self, message: str) -> None:
        """Queued requests cannot run without a keyboard. Reads need no answer: a connect reads every block."""
        with self._condition:
            dropped, self._requests = self._requests, []
        for request in dropped:
            if isinstance(request, _Update):
                self.write_failed.emit(request.block, message)
                self._finish_batch_update(request.batch, request.block, False, message)
            elif isinstance(request, _FactoryReset):
                self.write_failed.emit(FACTORY_RESET_REQUEST, message)
            elif isinstance(request, _Upload):
                self.write_failed.emit(request.kind, message)
                self.upload_finished.emit(request.kind, UPLOAD_FAILED)

    def _set_state(self, state: ConnectionState) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)


def _merge(queued: dict, newer: dict) -> None:
    """Merge newer changes into queued ones of the same block. A newer value wins; for a table field (a dict of
    entries, such as the colours of the keys) a newer entry wins and the other queued entries stay."""
    for field, value in newer.items():
        old = queued.get(field)
        queued[field] = {**old, **value} if isinstance(old, dict) and isinstance(value, dict) else value


class WorkerThread(QThread):
    """Runs the worker loop until stop() is called."""

    def __init__(self, worker: DeviceWorker, error_pause: float = ERROR_PAUSE):
        super().__init__()
        self.worker = worker
        self._error_pause = error_pause
        self._stopping = threading.Event()

    def run(self) -> None:
        while not self._stopping.is_set():
            try:
                self.worker.run_once()
            except Exception:
                # A bug must not end device I/O: probing and hot-plug keep working after it.
                log.exception("unexpected error in the worker")
                self._stopping.wait(self._error_pause)
        self.worker.shutdown()

    def stop(self) -> None:
        self._stopping.set()
        self.worker.cancel_uploads()
        self.wait()
