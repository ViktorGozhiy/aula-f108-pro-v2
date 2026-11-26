import logging
import time

import pytest

from aula_f108.blocks import device_info
from aula_f108.hidraw import CommandInterface, DeviceBusy, DeviceGone
from aula_f108.keyboard import BLOCKS
from aula_f108.worker import (
    ASLEEP,
    BUSY,
    GONE,
    LINK_LOST_TEXT,
    NO_REPLY,
    NOT_FOUND,
    READ_FAILED,
    ConnectionState,
    DeviceWorker,
)
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard
from worker_rig import Rig

SLEEP = bytes.fromhex("55fc06")
LINK_LOST = bytes.fromhex("55fc04")
RESET = bytes.fromhex("55fc05")
LINK_WOKE = bytes.fromhex("a6ff01")


def silent_keyboard(report_size=64):
    sim = SimulatedKeyboard(report_size)
    sim.silent = True
    return sim


def connected_rig(connection="cable"):
    sim = SimulatedKeyboard(64 if connection == "cable" else 32)
    rig = Rig(**{connection: sim})
    rig.step()
    rig.events.clear()
    return rig, sim


def test_connects_to_the_cable_first_and_reads_every_block():
    cable, dongle = SimulatedKeyboard(64), SimulatedKeyboard(32)
    rig = Rig(cable=cable, dongle=dongle)
    rig.step()
    assert rig.events[0] == ("state", ConnectionState("connected", "cable"))
    assert [event[0] for event in rig.of_kind("read")] == list(BLOCKS)
    assert rig.of_kind("read")[0][1] == device_info.decode(load_hex("wired-10.hex"))
    assert dongle.packets == []


def test_uses_the_dongle_when_the_cable_does_not_answer():
    cable = silent_keyboard()
    rig = Rig(cable=cable, dongle=SimulatedKeyboard(32))
    rig.step()
    assert rig.state == ConnectionState("connected", "dongle")
    assert cable.closed


def test_skips_an_interface_without_permission():
    rig = Rig(cable=PermissionError(13, "Permission denied"), dongle=SimulatedKeyboard(32))
    rig.step()
    assert rig.state == ConnectionState("connected", "dongle")


def test_reports_another_copy_holding_the_keyboard():
    rig = Rig(cable=DeviceBusy("/dev/sim-cable"))
    rig.step()
    assert rig.state == ConnectionState("busy", reason=BUSY)


def test_reports_no_keyboard_once():
    rig = Rig(cable=silent_keyboard())
    rig.step()
    rig.clock.now = 3.0
    rig.step()
    assert rig.of_kind("state") == [(ConnectionState("not_connected", reason=NOT_FOUND),)]


def test_probes_every_three_seconds():
    rig = Rig(cable=silent_keyboard())
    rig.step()
    rig.clock.now = 2.99
    rig.step()
    assert len(rig.opened) == 1
    rig.clock.now = 3.0
    rig.step()
    assert len(rig.opened) == 2


def test_probe_request_probes_at_once():
    rig = Rig(cable=silent_keyboard())
    rig.step()
    rig.worker.request_probe()
    rig.step()
    assert len(rig.opened) == 2


def test_failed_block_read_disables_only_that_block():
    sim = SimulatedKeyboard()
    sim.drop[0x13] = 4
    rig = Rig(cable=sim)
    rig.step()
    assert rig.of_kind("failed") == [("led_effect", READ_FAILED)]
    assert [event[0] for event in rig.of_kind("read")] == [name for name in BLOCKS if name != "led_effect"]
    assert rig.state.status == "connected"


def test_read_request_reads_the_block():
    rig, _sim = connected_rig()
    rig.worker.request_read("settings")
    rig.step()
    assert [event[0] for event in rig.of_kind("read")] == ["settings"]


def test_read_request_for_an_unknown_block_is_refused():
    rig, _sim = connected_rig()
    with pytest.raises(KeyError):
        rig.worker.request_read("side_light")


def test_read_without_answer_and_failed_probe_loses_the_keyboard_but_keeps_the_interface():
    rig, sim = connected_rig()
    sim.silent = True
    rig.worker.request_read("settings")
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=NO_REPLY)
    assert rig.of_kind("failed") == []
    assert not sim.closed
    sim.silent = False
    rig.clock.now = 3.0
    rig.step()
    assert rig.state == ConnectionState("connected", "cable")
    assert len(rig.opened) == 1


def test_io_error_during_a_read_closes_the_interface():
    rig, sim = connected_rig()
    sim.gone = True
    rig.worker.request_read("settings")
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert sim.closed


def test_io_error_while_idle_closes_the_interface():
    rig, sim = connected_rig()
    sim.gone = True
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert sim.closed


def test_probe_request_while_connected_checks_the_keyboard():
    rig, sim = connected_rig()
    rig.worker.request_probe()
    rig.step()
    assert rig.state is None  # no state change
    assert sim.sent_commands()[-1] == 0x10
    sim.silent = True
    rig.worker.request_probe()
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=NO_REPLY)


def test_requests_without_a_keyboard_are_dropped():
    sim = silent_keyboard()
    rig = Rig(cable=sim)
    rig.step()
    rig.worker.request_read("settings")
    rig.step()
    sim.silent = False
    rig.worker.request_probe()
    rig.step()
    assert [event[0] for event in rig.of_kind("read")] == list(BLOCKS)


@pytest.mark.parametrize(("report", "reason"), [(SLEEP, ASLEEP), (LINK_LOST, LINK_LOST_TEXT)])
def test_sleep_and_link_lost_notifications_lose_the_keyboard(report, reason):
    rig, sim = connected_rig("dongle")
    sim.push(report)
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=reason)
    assert not sim.closed


def test_link_woke_probes_at_once_on_the_open_interface():
    rig, sim = connected_rig("dongle")
    sim.push(SLEEP)
    rig.step()
    sim.push(LINK_WOKE)
    rig.step()
    rig.step()
    assert rig.state == ConnectionState("connected", "dongle")
    assert len(rig.opened) == 1


def test_sleep_while_not_connected_changes_nothing():
    rig, sim = connected_rig("dongle")
    sim.push(SLEEP)
    rig.step()
    sim.push(LINK_LOST)
    rig.step()
    assert len(rig.of_kind("state")) == 1


def test_io_error_while_not_connected_closes_the_interface():
    rig, sim = connected_rig("dongle")
    sim.push(SLEEP)
    rig.step()
    sim.gone = True
    rig.step()
    assert sim.closed
    assert len(rig.of_kind("state")) == 1


def test_reset_notification_reads_every_block_again():
    rig, sim = connected_rig()
    sim.push(RESET)
    rig.step()
    assert [event[0] for event in rig.of_kind("read")] == list(BLOCKS)


def test_reset_notification_while_not_connected_reads_nothing():
    rig, sim = connected_rig("dongle")
    sim.push(SLEEP)
    rig.step()
    sim.push(RESET)
    rig.step()
    assert rig.of_kind("read") == []


def test_other_notifications_are_logged(caplog):
    caplog.set_level(logging.INFO, logger="aula_f108.worker")
    rig, sim = connected_rig()
    sim.push(bytes.fromhex("55fa0102"))
    rig.step()
    assert "notification 55 fa 01 02" in caplog.text
    assert rig.events == []


def test_battery_is_read_every_30_seconds_on_the_dongle():
    rig, sim = connected_rig("dongle")
    rig.clock.now = 29.9
    rig.step()
    assert rig.of_kind("read") == []
    rig.clock.now = 30.0
    rig.step()
    assert [event[0] for event in rig.of_kind("read")] == ["device_info"]


def test_battery_is_read_again_after_30_more_seconds():
    rig, sim = connected_rig("dongle")
    rig.clock.now = 30.0
    rig.step()
    rig.events.clear()
    rig.clock.now = 59.9
    rig.step()
    assert rig.of_kind("read") == []
    rig.clock.now = 60.0
    rig.step()
    assert [event[0] for event in rig.of_kind("read")] == ["device_info"]


def test_battery_is_not_polled_on_the_cable():
    rig, sim = connected_rig("cable")
    rig.clock.now = 30.0
    rig.step()
    assert rig.of_kind("read") == []


def timed_step(worker):
    start = time.monotonic()
    worker.run_once()
    return time.monotonic() - start


def test_loop_waits_between_probes_while_no_interface_is_found():
    worker = DeviceWorker(find_interfaces=lambda: [], open_device=None, idle_wait=0.05)
    worker.run_once()
    assert timed_step(worker) >= 0.04


def test_loop_waits_for_reports_while_connected_and_idle():
    sim = SimulatedKeyboard()
    worker = DeviceWorker(
        find_interfaces=lambda: [CommandInterface("/dev/sim-cable", "cable", 64)],
        open_device=lambda path, report_size: sim,
        time_scale=0.01,
        idle_wait=0.05,
    )
    worker.run_once()
    assert timed_step(worker) >= 0.04


def test_shutdown_closes_the_interface():
    rig, sim = connected_rig()
    rig.worker.shutdown()
    assert sim.closed


def test_failed_probe_keeps_the_open_interface():
    rig, sim = connected_rig()
    sim.silent = True
    rig.worker.request_read("settings")
    rig.step()
    rig.clock.now = 3.0
    rig.step()
    assert not sim.closed
    assert len(rig.opened) == 1
    assert len(rig.of_kind("state")) == 1


def test_io_error_while_probing_closes_the_interface():
    rig, sim = connected_rig("dongle")
    sim.push(SLEEP)
    rig.step()
    sim.gone = True
    rig.clock.now = 3.0
    rig.step()
    assert sim.closed
    assert len(rig.opened) == 1
    rig.clock.now = 6.0
    rig.step()
    assert len(rig.opened) == 2
    assert sim.closed


def test_connecting_to_the_cable_closes_the_open_dongle():
    cable, dongle = silent_keyboard(64), SimulatedKeyboard(32)
    rig = Rig(cable=cable, dongle=dongle)
    rig.step()
    dongle.push(SLEEP)
    rig.step()
    cable.silent = False
    rig.clock.now = 3.0
    rig.step()
    assert rig.state == ConnectionState("connected", "cable")
    assert dongle.closed


class AnswersOnlyTheFirstPacket(SimulatedKeyboard):
    def _answer(self, packet):
        if len(self.packets) > 1:
            return None
        return super()._answer(packet)


def test_keyboard_lost_while_reading_the_blocks_stops_the_reads():
    rig = Rig(cable=AnswersOnlyTheFirstPacket())
    rig.step()
    assert [event[0] for event in rig.of_kind("read")] == ["device_info"]
    assert rig.state == ConnectionState("not_connected", reason=NO_REPLY)


class UnpluggedDuringTheProbe(SimulatedKeyboard):
    """Leaves the settings reads unanswered, then fails the probe that follows with an I/O error."""

    def write(self, report):
        if report[1] == 0x10 and self.drop.get(0x11) == 0:
            raise DeviceGone("unplugged")
        super().write(report)


def test_io_error_in_the_probe_after_a_failed_read_closes_the_interface():
    sim = UnpluggedDuringTheProbe()
    rig = Rig(cable=sim)
    rig.step()
    sim.drop[0x11] = 4
    rig.worker.request_read("settings")
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert sim.closed


def test_link_lost_text_says_the_keyboard_may_sleep():
    """Over the dongle a sleeping keyboard is reported as 55 FC 04, the same as a switched-off one."""
    assert "asleep" in LINK_LOST_TEXT
    assert "Press any key" in LINK_LOST_TEXT
