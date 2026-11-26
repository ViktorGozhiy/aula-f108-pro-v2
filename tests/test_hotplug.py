import socket
import struct

import pytest

from aula_f108.hotplug import HotplugWatcher, is_hidraw_change, open_uevent_socket


def udev_message(action, subsystem, bloom=bytes(8), padding=b""):
    """A message as systemd-udevd sends it: a 40-byte header, optional padding, then the properties.

    In the header the magic, the hashes and the tag bloom filter are big-endian; header_size,
    properties_off and properties_len are in the sender's byte order.
    """
    properties = b"\x00".join(
        [
            f"ACTION={action}".encode(),
            b"DEVPATH=/devices/pci0000:00/usb1/1-2/1-2:1.2/0003:38A6:2739.0001/hidraw/hidraw11",
            f"SUBSYSTEM={subsystem}".encode(),
            b"DEVNAME=/dev/hidraw11",
            b"",
        ]
    )
    header = (
        b"libudev\x00"
        + bytes.fromhex("feedcafe")
        + struct.pack("=III", 40, 40 + len(padding), len(properties))
        + bytes.fromhex("1a2b3c4d00000000")
        + bloom
    )
    return header + padding + properties


@pytest.mark.parametrize("action", ["add", "remove"])
def test_hidraw_add_and_remove_are_changes(action):
    assert is_hidraw_change(udev_message(action, "hidraw"))


def test_properties_after_a_header_that_ends_with_a_non_zero_byte_are_found():
    assert is_hidraw_change(udev_message("add", "hidraw", bloom=bytes.fromhex("0000040000201008")))


def test_libudev_properties_start_at_the_offset_in_the_header():
    assert is_hidraw_change(udev_message("add", "hidraw", padding=b"\x01\x02\x03\x04"))


def test_kernel_format_message_is_understood():
    message = b"add@/devices/x/hidraw/hidraw3\x00ACTION=add\x00SUBSYSTEM=hidraw\x00"
    assert is_hidraw_change(message)


def test_other_actions_and_subsystems_are_not_changes():
    assert not is_hidraw_change(udev_message("change", "hidraw"))
    assert not is_hidraw_change(udev_message("add", "usb"))


def test_uevent_socket_is_a_non_blocking_netlink_socket():
    sock = open_uevent_socket()
    assert sock.family == socket.AF_NETLINK
    assert not sock.getblocking()
    sock.close()


def test_uevent_socket_joins_the_udev_group():
    # Group 2 carries the events after udev has applied the access rules; group 1 carries the kernel's.
    sock = open_uevent_socket()
    assert sock.getsockname()[1] == 2
    sock.close()


@pytest.fixture
def socket_pair():
    reader, writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    reader.setblocking(False)
    yield reader, writer
    writer.close()


def test_watcher_signals_a_hidraw_change_once_per_batch(qtbot, socket_pair):
    reader, writer = socket_pair
    watcher = HotplugWatcher(reader)
    emitted = []
    watcher.hidraw_changed.connect(lambda: emitted.append(True))
    writer.send(udev_message("remove", "hidraw"))
    writer.send(udev_message("add", "hidraw"))
    qtbot.waitUntil(lambda: len(emitted) > 0, timeout=1000)
    qtbot.wait(50)
    assert emitted == [True]
    watcher.close()


def test_close_disables_the_notifier_and_closes_the_socket(socket_pair):
    reader, _writer = socket_pair
    watcher = HotplugWatcher(reader)
    assert watcher._notifier.isEnabled()
    watcher.close()
    assert not watcher._notifier.isEnabled()
    assert reader.fileno() == -1


def test_watcher_ignores_other_events(qtbot, socket_pair):
    reader, writer = socket_pair
    watcher = HotplugWatcher(reader)
    with qtbot.assertNotEmitted(watcher.hidraw_changed, wait=100):
        writer.send(udev_message("add", "usb"))
    watcher.close()
