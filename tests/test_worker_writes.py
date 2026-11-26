import logging

import pytest

from aula_f108.blocks import key_colours, led_effect, settings
from aula_f108.hidraw import CommandInterface
from aula_f108.keyboard import BLOCKS
from aula_f108.worker import (
    GONE,
    NO_REPLY,
    NOT_WRITTEN,
    RESTARTING,
    ConnectionState,
    DeviceWorker,
    WorkerThread,
)
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard
from worker_rig import Rig


def connected_rig(connection="cable"):
    sim = SimulatedKeyboard(64 if connection == "cable" else 32)
    rig = Rig(**{connection: sim})
    rig.step()
    rig.events.clear()
    return rig, sim


def write_commands(sim):
    return [cmd for cmd, _addr, _data in sim.writes]


def transfers(sim):
    """The commands sent, one entry for each run of packets of the same command."""
    commands = sim.sent_commands()
    return [cmd for index, cmd in enumerate(commands) if index == 0 or commands[index - 1] != cmd]


class UnpluggedByTheWrite(SimulatedKeyboard):
    """Gives an I/O error from the first packet of the write command `cmd` on, as a restart or an unplug does."""

    def __init__(self, cmd, report_size=64):
        super().__init__(report_size)
        self.unplug_cmd = cmd

    def write(self, report):
        if report[1] == self.unplug_cmd:
            self.gone = True
        super().write(report)


def connected_rig_on(sim):
    rig = Rig(cable=sim)
    rig.step()
    rig.events.clear()
    return rig


def test_update_writes_changes_onto_a_fresh_read():
    rig, sim = connected_rig()
    sim.blocks["settings"][4] = 5
    rig.worker.request_update("settings", {"sleep_minutes": 10})
    rig.step()
    assert sim.blocks["settings"][3] == 10
    assert sim.blocks["settings"][4] == 5
    assert rig.of_kind("written") == [("settings", settings.decode(bytes(sim.blocks["settings"])))]
    assert rig.of_kind("read") == []


def test_queued_writes_of_one_block_are_merged():
    rig, sim = connected_rig()
    rig.worker.request_update("led_effect", {"brightness": 2})
    rig.worker.request_update("led_effect", {"brightness": 4, "speed": 1})
    rig.step(2)
    assert write_commands(sim) == [0x23]
    assert led_effect.decode(bytes(sim.blocks["led_effect"])).brightness == 4
    assert led_effect.decode(bytes(sim.blocks["led_effect"])).speed == 1


def test_queued_write_merges_past_a_write_of_another_block():
    rig, sim = connected_rig()
    rig.worker.request_update("led_effect", {"brightness": 2})
    rig.worker.request_update("settings", {"debounce": 2})
    rig.worker.request_update("led_effect", {"speed": 1})
    rig.step(2)
    assert write_commands(sim) == [0x23, 0x21]
    assert led_effect.decode(bytes(sim.blocks["led_effect"])).brightness == 2
    assert led_effect.decode(bytes(sim.blocks["led_effect"])).speed == 1
    assert sim.blocks["settings"][4] == 2


def test_queued_table_writes_keep_the_entries_of_both():
    rig, sim = connected_rig()
    rig.worker.request_update("key_colours", {"colours": {0: (1, 2, 3), 1: (4, 5, 6)}})
    rig.worker.request_update("key_colours", {"colours": {1: (7, 8, 9)}})
    rig.step(2)
    assert write_commands(sim) == [0x24] * 10  # one write of 512 bytes in 10 packets
    colours = key_colours.decode(bytes(sim.blocks["key_colours"])).colours
    assert (colours[0], colours[1]) == ((1, 2, 3), (7, 8, 9))


def test_writes_are_not_merged_across_a_factory_reset():
    rig, sim = connected_rig()
    rig.worker.request_update("led_effect", {"brightness": 2})
    rig.worker.request_factory_reset()
    rig.worker.request_update("led_effect", {"brightness": 4})
    rig.step(3)
    assert write_commands(sim) == [0x23, 0x0F, 0x23]
    assert sim.blocks["led_effect"][9] == 4


def test_ordered_writes_are_not_merged_into_earlier_writes():
    rig, sim = connected_rig()
    rig.worker.request_update("settings", {"debounce": 2})
    rig.worker.request_updates([("led_effect", {"speed": 2}), ("settings", {"debounce": 3})])
    rig.step(3)
    assert write_commands(sim) == [0x21, 0x23, 0x21]
    assert sim.blocks["settings"][4] == 3


def test_later_writes_are_not_merged_into_ordered_writes():
    rig, sim = connected_rig()
    rig.worker.request_updates([("settings", {"debounce": 3}), ("led_effect", {"speed": 2})])
    rig.worker.request_update("settings", {"debounce": 2})
    rig.step(3)
    assert write_commands(sim) == [0x21, 0x23, 0x21]
    assert sim.blocks["settings"][4] == 2


def test_ordered_writes_report_each_request_of_their_batch():
    rig, sim = connected_rig()
    batch = rig.worker.request_updates([("led_effect", {"speed": 2}), ("settings", {"debounce": 3})])
    other = rig.worker.request_updates([("settings", {"debounce": 2})])
    rig.step(3)
    assert other != batch
    assert rig.of_kind("batch_update_finished") == [
        (batch, "led_effect", True, ""),
        (batch, "settings", True, ""),
        (other, "settings", True, ""),
    ]
    assert [event[0] for event in rig.events].count("written") == 3


def test_unordered_writes_report_no_batch():
    rig, _sim = connected_rig()
    rig.worker.request_update("settings", {"debounce": 2})
    rig.step()
    assert rig.of_kind("written") != []
    assert rig.of_kind("batch_update_finished") == []


def test_ordered_write_of_an_invalid_change_reports_its_batch():
    rig, _sim = connected_rig()
    batch = rig.worker.request_updates([("settings", {"debounce": 9}), ("led_effect", {"speed": 2})])
    rig.step(2)
    message = f"{NOT_WRITTEN}. debounce must be within 1..5, got 9"
    assert rig.of_kind("write_failed") == [("settings", message)]
    assert rig.of_kind("batch_update_finished") == [
        (batch, "settings", False, message),
        (batch, "led_effect", True, ""),
    ]


def test_ordered_write_without_a_reply_reports_its_batch():
    rig, sim = connected_rig()
    sim.drop[0x21] = 4
    batch = rig.worker.request_updates([("settings", {"debounce": 2})])
    rig.step()
    message = f"{NOT_WRITTEN}. The keyboard did not answer."
    assert rig.of_kind("write_failed") == [("settings", message)]
    assert rig.of_kind("batch_update_finished") == [(batch, "settings", False, message)]


def test_ordered_write_that_restarts_the_keyboard_reports_its_batch():
    rig, sim = connected_rig()
    sim.drop[0x21] = 4
    batch = rig.worker.request_updates([("settings", {"polling_rate": 3})])
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=RESTARTING)
    assert rig.of_kind("batch_update_finished") == [(batch, "settings", False, f"{NOT_WRITTEN}. {RESTARTING}.")]


def test_ordered_writes_dropped_by_a_lost_keyboard_report_their_batch():
    rig, sim = connected_rig()
    sim.gone = True
    batch = rig.worker.request_updates([("led_effect", {"speed": 2}), ("settings", {"debounce": 3})])
    rig.step()
    message = f"{NOT_WRITTEN}. {GONE}."
    assert rig.of_kind("batch_update_finished") == [
        (batch, "settings", False, message),
        (batch, "led_effect", False, message),
    ]


def test_ordered_writes_without_a_keyboard_report_their_batch():
    sim = SimulatedKeyboard()
    sim.silent = True
    rig = Rig(cable=sim)
    rig.step()
    batch = rig.worker.request_updates([("led_effect", {"speed": 2}), ("settings", {"debounce": 3})])
    rig.step()
    message = f"{NOT_WRITTEN}. Keyboard not connected."
    assert rig.of_kind("batch_update_finished") == [
        (batch, "led_effect", False, message),
        (batch, "settings", False, message),
    ]


def test_writes_of_different_blocks_keep_their_order():
    rig, sim = connected_rig()
    rig.worker.request_update("settings", {"debounce": 2})
    rig.worker.request_update("led_effect", {"speed": 2})
    rig.step(2)
    assert write_commands(sim) == [0x21, 0x23]


def test_update_of_an_unknown_block_is_refused():
    rig, _sim = connected_rig()
    with pytest.raises(KeyError):
        rig.worker.request_update("side_light", {})


def test_invalid_change_is_reported_and_not_written():
    rig, sim = connected_rig()
    rig.worker.request_update("settings", {"debounce": 9})
    rig.step()
    assert rig.of_kind("write_failed") == [("settings", f"{NOT_WRITTEN}. debounce must be within 1..5, got 9")]
    assert sim.writes == []
    assert rig.state is None


def test_failed_write_with_answering_probe_keeps_the_connection():
    rig, sim = connected_rig()
    sim.drop[0x21] = 4
    rig.worker.request_update("settings", {"debounce": 2})
    rig.step()
    assert rig.of_kind("write_failed") == [("settings", f"{NOT_WRITTEN}. The keyboard did not answer.")]
    assert rig.state is None


def test_failed_write_with_failed_probe_loses_the_keyboard():
    rig, sim = connected_rig()
    sim.drop[0x21] = 4
    sim.drop[0x10] = 4
    rig.worker.request_update("settings", {"debounce": 2})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=NO_REPLY)
    assert [event[0] for event in rig.of_kind("write_failed")] == ["settings"]


def test_io_error_during_a_write_loses_the_keyboard():
    rig, sim = connected_rig()
    sim.gone = True
    rig.worker.request_update("led_effect", {"speed": 2})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert rig.of_kind("write_failed") == [("led_effect", f"{NOT_WRITTEN}. {GONE}.")]
    assert sim.closed


def test_io_error_while_sending_a_write_loses_the_keyboard():
    sim = UnpluggedByTheWrite(0x23)
    rig = connected_rig_on(sim)
    rig.worker.request_update("led_effect", {"speed": 2})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert rig.of_kind("write_failed") == [("led_effect", f"{NOT_WRITTEN}. {GONE}.")]
    assert sim.closed


def test_polling_rate_on_the_cable_without_reply_waits_for_the_restart():
    rig, sim = connected_rig("cable")
    sim.drop[0x21] = 4
    rig.worker.request_update("settings", {"polling_rate": 3})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=RESTARTING)
    assert rig.of_kind("write_failed") == []
    assert sim.closed
    rig.clock.now = 3.0
    rig.step()
    assert rig.state == ConnectionState("connected", "cable")
    assert [event[0] for event in rig.of_kind("read")] == list(BLOCKS)


def test_polling_rate_on_the_cable_with_io_error_waits_for_the_restart():
    sim = UnpluggedByTheWrite(0x21)
    rig = connected_rig_on(sim)
    rig.worker.request_update("settings", {"polling_rate": 3})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=RESTARTING)
    assert rig.of_kind("write_failed") == []
    assert sim.closed


def test_polling_rate_on_the_cable_with_a_failed_read_is_an_error():
    rig, sim = connected_rig("cable")
    sim.drop[0x11] = 4
    rig.worker.request_update("settings", {"polling_rate": 3})
    rig.step()
    assert rig.of_kind("write_failed") == [("settings", f"{NOT_WRITTEN}. The keyboard did not answer.")]
    assert rig.state is None
    assert 0x21 not in sim.sent_commands()


def test_polling_rate_on_the_cable_with_io_error_in_the_read_loses_the_keyboard():
    rig, sim = connected_rig("cable")
    sim.gone = True
    rig.worker.request_update("settings", {"polling_rate": 3})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert rig.of_kind("write_failed") == [("settings", f"{NOT_WRITTEN}. {GONE}.")]


def test_polling_rate_on_the_dongle_without_reply_is_an_error():
    rig, sim = connected_rig("dongle")
    sim.drop[0x21] = 4
    rig.worker.request_update("settings", {"polling_rate": 3})
    rig.step()
    assert [event[0] for event in rig.of_kind("write_failed")] == ["settings"]
    assert rig.state is None


def test_other_settings_on_the_cable_without_reply_are_an_error():
    rig, sim = connected_rig("cable")
    sim.drop[0x21] = 4
    rig.worker.request_update("settings", {"sleep_minutes": 3})
    rig.step()
    assert [event[0] for event in rig.of_kind("write_failed")] == ["settings"]


def test_win_mac_change_reads_the_settings_and_both_key_tables_again():
    rig, sim = connected_rig()
    rig.worker.request_update("settings", {"mac_mode": True})
    rig.step()
    assert transfers(sim)[-5:] == [0x11, 0x21, 0x11, 0x12, 0x16]
    assert [event[:2] for event in rig.events] == [
        ("written", "settings"),
        ("read", "settings"),
        ("read", "base_keys"),
        ("read", "fn_keys"),
    ]


class UnpluggedAfterTheWrite(SimulatedKeyboard):
    """Gives an I/O error on every read after the reply to the write command `cmd`."""

    def __init__(self, cmd, report_size=64):
        super().__init__(report_size)
        self.unplug_cmd = cmd

    def read(self, timeout):
        report = super().read(timeout)
        if report is not None and report[1] == self.unplug_cmd:
            self.gone = True
        return report


def test_win_mac_change_stops_the_reads_when_the_keyboard_is_lost():
    sim = UnpluggedAfterTheWrite(0x21)
    rig = connected_rig_on(sim)
    rig.worker.request_update("settings", {"mac_mode": True})
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert rig.of_kind("read") == []
    assert [event[0] for event in rig.of_kind("written")] == ["settings"]


def test_factory_reset_with_reply_reads_every_block():
    rig, sim = connected_rig()
    sim.blocks["led_effect"][9] = 1
    rig.worker.request_factory_reset()
    rig.step()
    assert sim.blocks["led_effect"] == load_hex("wired-13.hex")
    assert [event[0] for event in rig.of_kind("read")] == list(BLOCKS)


def test_factory_reset_without_reply_waits_for_the_restart():
    rig, sim = connected_rig()
    sim.drop[0x0F] = 1
    rig.worker.request_factory_reset()
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=RESTARTING)
    assert sim.closed


def test_factory_reset_with_io_error_waits_for_the_restart():
    rig, sim = connected_rig()
    sim.gone = True
    rig.worker.request_factory_reset()
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=RESTARTING)


def test_queued_writes_are_dropped_when_the_keyboard_is_lost():
    rig, sim = connected_rig()
    sim.gone = True
    rig.worker.request_read("settings")
    rig.worker.request_update("led_effect", {"speed": 2})
    rig.worker.request_factory_reset()
    rig.step()
    message = f"{NOT_WRITTEN}. {GONE}."
    assert rig.of_kind("write_failed") == [("led_effect", message), ("factory_reset", message)]


def test_writes_without_a_keyboard_are_dropped_with_a_message():
    sim = SimulatedKeyboard()
    sim.silent = True
    rig = Rig(cable=sim)
    rig.step()
    rig.worker.request_update("settings", {"debounce": 2})
    rig.step()
    assert rig.of_kind("write_failed") == [("settings", f"{NOT_WRITTEN}. Keyboard not connected.")]


def test_worker_thread_connects_and_stops(qtbot):
    sim = SimulatedKeyboard()
    worker = DeviceWorker(
        find_interfaces=lambda: [CommandInterface("/dev/sim-cable", "cable", 64)],
        open_device=lambda path, report_size: sim,
        time_scale=0.01,
        idle_wait=0.01,
    )
    thread = WorkerThread(worker)
    with qtbot.waitSignal(worker.state_changed, timeout=2000) as blocker:
        thread.start()
    assert blocker.args[0] == ConnectionState("connected", "cable")
    thread.stop()
    assert thread.isFinished()
    assert sim.closed


def test_worker_thread_logs_an_unexpected_error_and_keeps_running(qtbot, caplog):
    sim = SimulatedKeyboard()
    calls = []

    def find_interfaces():
        calls.append(True)
        if len(calls) == 1:
            raise ValueError("report descriptor has no collection")
        return [CommandInterface("/dev/sim-cable", "cable", 64)]

    worker = DeviceWorker(
        find_interfaces=find_interfaces,
        open_device=lambda path, report_size: sim,
        time_scale=0.01,
        idle_wait=0.01,
    )
    thread = WorkerThread(worker, error_pause=0.01)
    with caplog.at_level(logging.ERROR, logger="aula_f108.worker"):
        thread.start()
        qtbot.waitUntil(lambda: "unexpected error in the worker" in caplog.text, timeout=2000)
        with qtbot.waitSignal(worker.state_changed, timeout=2000) as blocker:
            worker.request_probe()
    assert blocker.args[0] == ConnectionState("connected", "cable")
    assert "ValueError: report descriptor has no collection" in caplog.text
    thread.stop()
    assert thread.isFinished()


def test_worker_thread_pauses_after_an_unexpected_error(qtbot, caplog):
    class FailingWorker:
        calls = 0

        def run_once(self):
            self.calls += 1
            raise ValueError("bug")

        def cancel_uploads(self):
            pass

        def shutdown(self):
            pass

    worker = FailingWorker()
    thread = WorkerThread(worker, error_pause=0.3)
    with caplog.at_level(logging.ERROR, logger="aula_f108.worker"):
        thread.start()
        qtbot.wait(150)
        thread.stop()
    assert worker.calls == 1


def test_factory_reset_with_reply_is_reported_as_sent():
    rig, _sim = connected_rig()
    rig.worker.request_factory_reset()
    rig.step()
    assert rig.of_kind("factory_reset_sent") == [()]


def test_factory_reset_without_reply_is_reported_as_sent():
    rig, sim = connected_rig()
    sim.drop[0x0F] = 1
    rig.worker.request_factory_reset()
    rig.step()
    assert rig.of_kind("factory_reset_sent") == [()]


def test_factory_reset_with_io_error_is_reported_as_sent():
    rig, sim = connected_rig()
    sim.gone = True
    rig.worker.request_factory_reset()
    rig.step()
    assert rig.of_kind("factory_reset_sent") == [()]


def test_dropped_factory_reset_is_not_reported_as_sent():
    rig, sim = connected_rig()
    sim.gone = True
    rig.worker.request_read("settings")
    rig.worker.request_factory_reset()
    rig.step()
    assert rig.of_kind("write_failed") == [("factory_reset", f"{NOT_WRITTEN}. {GONE}.")]
    assert rig.of_kind("factory_reset_sent") == []
