import logging
import time

import pytest

from aula_f108.blocks import led_effect
from aula_f108.hidraw import CommandInterface, DeviceBusy
from aula_f108.worker import (
    ASLEEP,
    DOT_MATRIX_ANIMATION,
    GONE,
    KEY_ANIMATION,
    NO_REPLY,
    NOT_WRITTEN,
    SLEEP,
    UPLOAD_CANCELLED,
    UPLOAD_DONE,
    UPLOAD_FAILED,
    ConnectionState,
    DeviceWorker,
    WorkerThread,
)
from simkeyboard import SimulatedKeyboard
from worker_rig import Rig

PAYLOAD = bytes(range(100))  # one chunk on the bulk interface, 2 on the cable command interface, 5 on the dongle


def connected(rig):
    rig.step()
    rig.events.clear()
    return rig


def cable_with_bulk():
    sim, bulk = SimulatedKeyboard(64), SimulatedKeyboard(4104)
    return connected(Rig(cable=sim, cable_bulk=bulk)), sim, bulk


def write_commands(sim):
    return [cmd for cmd, _addr, _data in sim.writes]


def test_connect_opens_the_bulk_interface_of_the_cable():
    rig, _sim, bulk = cable_with_bulk()
    assert rig.opened == ["/dev/sim-cable", "/dev/sim-cable_bulk"]
    assert not bulk.closed


def test_bulk_interface_is_opened_with_its_own_report_size():
    rig, _sim, _bulk = cable_with_bulk()
    assert rig.opened_report_sizes == [("/dev/sim-cable", 64), ("/dev/sim-cable_bulk", 4104)]


def test_notification_read_on_the_bulk_interface_reaches_the_worker():
    rig, _sim, bulk = cable_with_bulk()
    bulk.push(SLEEP)
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=ASLEEP)


def test_dot_matrix_animation_goes_to_the_bulk_interface():
    rig, sim, bulk = cable_with_bulk()
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert [packet[:2] for packet in bulk.packets] == [b"\xaa\x41"]
    assert bulk.uploaded(0x41) == PAYLOAD + bytes(4096 - len(PAYLOAD))
    assert 0x41 not in sim.sent_commands()
    assert sim.writes == []
    assert rig.of_kind("progress") == [(DOT_MATRIX_ANIMATION, 1, 1)]
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_DONE)]


def test_key_animation_sets_the_animation_effect_first():
    rig, sim, bulk = cable_with_bulk()
    rig.worker.request_upload(KEY_ANIMATION, PAYLOAD)
    rig.step()
    assert write_commands(sim) == [0x23]
    assert led_effect.decode(sim.writes[0][2]) == led_effect.LedEffect(0xFF, (255, 0, 0), False, 5, 0, 0)
    assert bulk.uploaded(0x42)[:len(PAYLOAD)] == PAYLOAD
    assert [event[0] for event in rig.events] == ["written", "progress", "upload_finished"]
    assert rig.of_kind("upload_finished") == [(KEY_ANIMATION, UPLOAD_DONE)]


def test_upload_on_the_dongle_uses_the_command_interface():
    sim = SimulatedKeyboard(32)
    rig = connected(Rig(dongle=sim))
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert sim.uploaded(0x41) == PAYLOAD + bytes(5 * 24 - len(PAYLOAD))
    assert rig.of_kind("progress")[-1] == (DOT_MATRIX_ANIMATION, 5, 5)


def test_cable_without_a_bulk_interface_uploads_on_the_command_interface():
    sim = SimulatedKeyboard(64)
    rig = connected(Rig(cable=sim))
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert sim.uploaded(0x41) == PAYLOAD + bytes(2 * 56 - len(PAYLOAD))
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_DONE)]


def test_bulk_interface_that_cannot_be_opened_is_logged_and_the_command_interface_used(caplog):
    sim = SimulatedKeyboard(64)
    rig = Rig(cable=sim, cable_bulk=PermissionError(13, "Permission denied"))
    with caplog.at_level(logging.WARNING, logger="aula_f108.worker"):
        rig.step()
    assert rig.state == ConnectionState("connected", "cable")
    assert "bulk interface /dev/sim-cable_bulk not opened" in caplog.text
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert sim.uploaded(0x41)[:len(PAYLOAD)] == PAYLOAD


def test_busy_bulk_interface_is_logged_and_the_command_interface_used(caplog):
    sim = SimulatedKeyboard(64)
    rig = Rig(cable=sim, cable_bulk=DeviceBusy("/dev/sim-cable_bulk"))
    with caplog.at_level(logging.WARNING, logger="aula_f108.worker"):
        rig.step()
    assert rig.state == ConnectionState("connected", "cable")
    assert "bulk interface /dev/sim-cable_bulk not opened" in caplog.text
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert sim.uploaded(0x41)[:len(PAYLOAD)] == PAYLOAD


def test_reconnect_on_the_same_cable_keeps_the_open_bulk_interface():
    rig, sim, bulk = cable_with_bulk()
    sim.silent = True
    rig.worker.request_read("settings")
    rig.step()
    sim.silent = False
    rig.worker.request_probe()
    rig.step()
    assert rig.state == ConnectionState("connected", "cable")
    assert rig.opened == ["/dev/sim-cable", "/dev/sim-cable_bulk"]
    assert not bulk.closed


def test_switching_to_the_dongle_closes_the_bulk_interface():
    sim, bulk, dongle = SimulatedKeyboard(64), SimulatedKeyboard(4104), SimulatedKeyboard(32)
    rig = Rig(cable=sim, cable_bulk=bulk, dongle=dongle)
    rig.step()
    sim.silent = True
    rig.worker.request_read("settings")
    rig.step()
    rig.worker.request_probe()
    rig.step()
    assert rig.state == ConnectionState("connected", "dongle")
    assert bulk.closed


def test_shutdown_closes_the_bulk_interface():
    rig, _sim, bulk = cable_with_bulk()
    rig.worker.shutdown()
    assert bulk.closed


def test_io_error_on_the_bulk_interface_loses_the_keyboard():
    rig, sim, bulk = cable_with_bulk()
    bulk.gone = True
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=GONE)
    assert sim.closed
    assert bulk.closed
    assert rig.of_kind("write_failed") == [(DOT_MATRIX_ANIMATION, f"{NOT_WRITTEN}. {GONE}.")]
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_FAILED)]


def test_unanswered_upload_with_answering_probe_keeps_the_connection():
    rig, _sim, bulk = cable_with_bulk()
    bulk.drop[0x41] = 4
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert rig.of_kind("write_failed") == [(DOT_MATRIX_ANIMATION, f"{NOT_WRITTEN}. The keyboard did not answer.")]
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_FAILED)]
    assert rig.state is None


def test_failed_animation_effect_stops_the_key_animation():
    rig, sim, bulk = cable_with_bulk()
    sim.drop[0x23] = 4
    rig.worker.request_upload(KEY_ANIMATION, PAYLOAD)
    rig.step()
    assert bulk.packets == []
    assert [event[0] for event in rig.of_kind("write_failed")] == ["led_effect"]
    assert rig.of_kind("upload_finished") == [(KEY_ANIMATION, UPLOAD_FAILED)]


def test_cancel_before_the_upload_starts_sends_nothing():
    rig, sim, bulk = cable_with_bulk()
    rig.worker.request_upload(KEY_ANIMATION, PAYLOAD)
    rig.worker.request_cancel_upload(KEY_ANIMATION)
    rig.step()
    assert sim.writes == []
    assert bulk.packets == []
    assert rig.of_kind("upload_finished") == [(KEY_ANIMATION, UPLOAD_CANCELLED)]


def test_cancel_during_the_upload_stops_before_the_next_chunk():
    sim = SimulatedKeyboard(32)
    rig = connected(Rig(dongle=sim))
    rig.worker.upload_progress.connect(lambda kind, sent, total: rig.worker.request_cancel_upload(kind))
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert len(sim.uploads) == 1
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_CANCELLED)]


def test_a_new_upload_clears_an_earlier_cancel():
    rig, _sim, _bulk = cable_with_bulk()
    rig.worker.request_cancel_upload(DOT_MATRIX_ANIMATION)
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_DONE)]


def test_cancel_of_one_kind_leaves_the_queued_upload_of_the_other_kind():
    rig, _sim, bulk = cable_with_bulk()
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.worker.request_upload(KEY_ANIMATION, PAYLOAD)
    rig.worker.request_cancel_upload(DOT_MATRIX_ANIMATION)
    rig.step(2)
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_CANCELLED), (KEY_ANIMATION, UPLOAD_DONE)]
    assert bulk.uploaded(0x41) == b""
    assert bulk.uploaded(0x42)[:len(PAYLOAD)] == PAYLOAD


def test_upload_of_the_other_kind_keeps_a_cancel():
    rig, _sim, bulk = cable_with_bulk()
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.worker.request_cancel_upload(DOT_MATRIX_ANIMATION)
    rig.worker.request_upload(KEY_ANIMATION, PAYLOAD)
    rig.step(2)
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_CANCELLED), (KEY_ANIMATION, UPLOAD_DONE)]
    assert bulk.uploaded(0x41) == b""


def test_unknown_upload_is_refused():
    rig, _sim, _bulk = cable_with_bulk()
    with pytest.raises(KeyError):
        rig.worker.request_upload("boot_animation", PAYLOAD)
    with pytest.raises(KeyError):
        rig.worker.request_cancel_upload("boot_animation")


def test_writes_are_not_merged_across_an_upload():
    rig, sim, _bulk = cable_with_bulk()
    rig.worker.request_update("led_effect", {"brightness": 2})
    rig.worker.request_upload(KEY_ANIMATION, PAYLOAD)
    rig.worker.request_update("led_effect", {"brightness": 4})
    rig.step(3)
    assert write_commands(sim) == [0x23, 0x23, 0x23]
    assert sim.blocks["led_effect"][9] == 4


def test_queued_upload_is_dropped_when_the_keyboard_is_lost():
    rig, sim, _bulk = cable_with_bulk()
    sim.gone = True
    rig.worker.request_read("settings")
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert rig.of_kind("write_failed") == [(DOT_MATRIX_ANIMATION, f"{NOT_WRITTEN}. {GONE}.")]
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_FAILED)]


def test_unanswered_upload_with_a_silent_keyboard_loses_the_connection():
    rig, sim, bulk = cable_with_bulk()
    bulk.drop[0x41] = 4
    sim.silent = True
    rig.worker.request_upload(DOT_MATRIX_ANIMATION, PAYLOAD)
    rig.step()
    assert rig.state == ConnectionState("not_connected", reason=NO_REPLY)
    assert rig.of_kind("upload_finished") == [(DOT_MATRIX_ANIMATION, UPLOAD_FAILED)]


def test_stopping_the_worker_thread_cancels_the_running_upload(qtbot):
    class SlowKeyboard(SimulatedKeyboard):
        def write(self, report):
            super().write(report)
            if report[1] == 0x41:
                time.sleep(0.005)

    sim = SlowKeyboard(32)
    chunks = 400  # 2 s when nothing stops it
    worker = DeviceWorker(
        find_interfaces=lambda: [CommandInterface("/dev/sim-dongle", "dongle", 32)],
        open_device=lambda path, report_size: sim,
        time_scale=0.01,
        idle_wait=0.01,
    )
    finished = []
    worker.upload_finished.connect(lambda kind, outcome: finished.append((kind, outcome)))
    thread = WorkerThread(worker)
    with qtbot.waitSignal(worker.state_changed, timeout=2000):
        thread.start()
    worker.request_upload(DOT_MATRIX_ANIMATION, bytes(24 * chunks))
    qtbot.waitUntil(lambda: len(sim.uploads) > 0, timeout=2000)
    thread.stop()
    assert thread.isFinished()
    assert len(sim.uploads) < chunks // 2
    qtbot.waitUntil(lambda: bool(finished), timeout=2000)
    assert finished == [(DOT_MATRIX_ANIMATION, UPLOAD_CANCELLED)]
