"""A DeviceWorker connected to simulated keyboards, with a manual clock and a record of every signal."""
from aula_f108.hidraw import CommandInterface
from aula_f108.worker import DeviceWorker

BULK_SUFFIX = "_bulk"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Rig:
    """`devices` maps "cable" / "dongle" to a SimulatedKeyboard or to an exception that opening raises.

    "cable_bulk" is the cable's bulk upload interface: a SimulatedKeyboard(4104) or an exception that opening raises.
    """

    def __init__(self, **devices):
        self.devices = devices
        self.clock = Clock()
        self.opened = []
        self.opened_report_sizes = []  # (path, report size asked for) of every open
        self.events = []
        self.worker = DeviceWorker(
            find_interfaces=self._find, open_device=self._open, time_scale=0.01, clock=self.clock, idle_wait=0,
        )
        self.worker.state_changed.connect(lambda state: self.events.append(("state", state)))
        self.worker.block_read.connect(lambda name, value: self.events.append(("read", name, value)))
        self.worker.block_failed.connect(lambda name, message: self.events.append(("failed", name, message)))
        self.worker.block_written.connect(lambda name, value: self.events.append(("written", name, value)))
        self.worker.write_failed.connect(lambda name, message: self.events.append(("write_failed", name, message)))
        self.worker.batch_update_finished.connect(
            lambda batch, name, ok, message: self.events.append(("batch_update_finished", batch, name, ok, message)))
        self.worker.upload_progress.connect(
            lambda kind, sent, total: self.events.append(("progress", kind, sent, total)))
        self.worker.upload_finished.connect(
            lambda kind, outcome: self.events.append(("upload_finished", kind, outcome)))
        self.worker.factory_reset_sent.connect(lambda: self.events.append(("factory_reset_sent",)))

    def step(self, times: int = 1) -> None:
        for _ in range(times):
            self.worker.run_once()

    def of_kind(self, kind: str) -> list:
        return [event[1:] for event in self.events if event[0] == kind]

    @property
    def state(self):
        states = self.of_kind("state")
        return states[-1][0] if states else None

    def _find(self):
        interfaces = []
        for connection, device in self.devices.items():
            if connection.endswith(BULK_SUFFIX):
                continue
            bulk = self.devices.get(connection + BULK_SUFFIX)
            interfaces.append(CommandInterface(
                f"/dev/sim-{connection}", connection, getattr(device, "report_size", 64),
                None if bulk is None else f"/dev/sim-{connection}{BULK_SUFFIX}",
                getattr(bulk, "report_size", 0),
            ))
        return interfaces

    def _open(self, path, report_size):
        self.opened.append(path)
        self.opened_report_sizes.append((path, report_size))
        device = self.devices[path.removeprefix("/dev/sim-")]
        if isinstance(device, Exception):
            raise device
        device.closed = False
        return device
