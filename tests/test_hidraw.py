import errno
import os

import pytest

from aula_f108 import hidraw
from aula_f108.hidraw import (
    CommandInterface,
    DescriptorInfo,
    DeviceBusy,
    DeviceGone,
    HidrawDevice,
    find_command_interfaces,
    parse_report_descriptor,
)
from fixture_data import load_hex


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("descriptor-wired-ff68.hex", DescriptorInfo(0xFF68, 0x61, 64, 64)),
        ("descriptor-wired-ff67.hex", DescriptorInfo(0xFF67, 0x61, 64, 4104)),
        ("descriptor-dongle-ff80.hex", DescriptorInfo(0xFF80, 0x01, 32, 32)),
        ("descriptor-dongle-mouse.hex", DescriptorInfo(0x01, 0x02, 5, 0)),
        ("descriptor-wired-consumer.hex", DescriptorInfo(0x0C, 0x01, 22, 0)),
    ],
)
def test_parses_real_descriptors(fixture, expected):
    assert parse_report_descriptor(load_hex(fixture)) == expected


def test_skips_long_items():
    descriptor = bytes.fromhex("fe0210aabb0668ff0961a101c0")
    assert parse_report_descriptor(descriptor) == DescriptorInfo(0xFF68, 0x61, 0, 0)


def test_reads_four_byte_item_data():
    descriptor = bytes.fromhex("0768ff00000961a101c0")
    assert parse_report_descriptor(descriptor).usage_page == 0xFF68


def test_rejects_descriptor_without_collection():
    with pytest.raises(ValueError, match="no collection"):
        parse_report_descriptor(bytes.fromhex("0668ff"))


def make_hidraw(root, name, uevent, descriptor_fixture=None):
    device = root / name / "device"
    device.mkdir(parents=True)
    (device / "uevent").write_text(uevent)
    if descriptor_fixture is not None:
        (device / "report_descriptor").write_bytes(load_hex(descriptor_fixture))


def test_finds_command_interfaces_cable_first(tmp_path):
    make_hidraw(tmp_path, "hidraw3", "HID_ID=0003:00000C45:0000FEFC\n", "descriptor-dongle-ff80.hex")
    make_hidraw(tmp_path, "hidraw1", "HID_ID=0003:00000C45:0000FEFC\n", "descriptor-dongle-mouse.hex")
    make_hidraw(tmp_path, "hidraw7", "HID_ID=0003:000038A6:00002739\n", "descriptor-wired-ff68.hex")
    make_hidraw(tmp_path, "hidraw8", "HID_ID=0003:000038A6:00002739\n", "descriptor-wired-ff67.hex")
    make_hidraw(tmp_path, "hidraw0", "HID_ID=0018:000004F3:0000327E\n", "descriptor-wired-ff68.hex")
    make_hidraw(tmp_path, "hidraw20", "HID_NAME=no id\n", "descriptor-wired-ff68.hex")
    make_hidraw(tmp_path, "hidraw21", "HID_ID=0003:000038A6:00002739\n")  # no report_descriptor file

    found = find_command_interfaces(str(tmp_path), "/dev")

    assert found == [
        CommandInterface("/dev/hidraw7", "cable", 64, "/dev/hidraw8", 4104),
        CommandInterface("/dev/hidraw3", "dongle", 32),
    ]


def test_cable_without_a_bulk_interface_node(tmp_path):
    make_hidraw(tmp_path, "hidraw7", "HID_ID=0003:000038A6:00002739\n", "descriptor-wired-ff68.hex")
    assert find_command_interfaces(str(tmp_path), "/dev") == [CommandInterface("/dev/hidraw7", "cable", 64)]


def test_dongle_has_no_bulk_interface(tmp_path):
    make_hidraw(tmp_path, "hidraw3", "HID_ID=0003:00000C45:0000FEFC\n", "descriptor-dongle-ff80.hex")
    make_hidraw(tmp_path, "hidraw4", "HID_ID=0003:00000C45:0000FEFC\n", "descriptor-wired-ff67.hex")
    assert find_command_interfaces(str(tmp_path), "/dev") == [CommandInterface("/dev/hidraw3", "dongle", 32)]


def test_finds_nothing_without_sysfs_directory(tmp_path):
    assert find_command_interfaces(str(tmp_path / "missing")) == []


@pytest.fixture
def fifo(tmp_path):
    path = tmp_path / "hidraw"
    os.mkfifo(path)
    return str(path)


def test_write_prepends_report_number(fifo):
    device = HidrawDevice(fifo, 4)
    other = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    device.write(bytes.fromhex("aa103800"))
    assert os.read(other, 100) == bytes.fromhex("00aa103800")
    os.close(other)
    device.close()


def test_write_rejects_wrong_report_size(fifo):
    device = HidrawDevice(fifo, 4)
    with pytest.raises(ValueError, match="4 bytes"):
        device.write(b"\xaa\x10\x38")
    device.close()


def test_read_returns_one_report(fifo):
    device = HidrawDevice(fifo, 4)
    other = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    os.write(other, bytes.fromhex("55103800"))
    assert device.read(1.0) == bytes.fromhex("55103800")
    os.close(other)
    device.close()


def test_read_returns_none_after_timeout(fifo):
    device = HidrawDevice(fifo, 4)
    assert device.read(0.01) is None
    device.close()


def test_read_returns_none_when_report_was_taken(fifo, monkeypatch):
    device = HidrawDevice(fifo, 4)
    other = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    os.write(other, b"\x55")

    def taken(fd, size):
        raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")

    monkeypatch.setattr(hidraw.os, "read", taken)
    assert device.read(1.0) is None
    monkeypatch.undo()
    os.close(other)
    device.close()


def test_read_error_means_device_gone(fifo, monkeypatch):
    device = HidrawDevice(fifo, 4)
    other = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    os.write(other, b"\x55")

    def unplugged(fd, size):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(hidraw.os, "read", unplugged)
    with pytest.raises(DeviceGone, match="Input/output error"):
        device.read(1.0)
    monkeypatch.undo()
    os.close(other)
    device.close()


def test_write_error_means_device_gone(fifo, monkeypatch):
    device = HidrawDevice(fifo, 4)

    def unplugged(fd, data):
        raise OSError(errno.ENODEV, "No such device")

    monkeypatch.setattr(hidraw.os, "write", unplugged)
    with pytest.raises(DeviceGone, match="No such device"):
        device.write(b"\xaa\x10\x38\x00")
    monkeypatch.undo()
    device.close()


def test_second_open_is_busy(fifo):
    first = HidrawDevice(fifo, 4)
    with pytest.raises(DeviceBusy):
        HidrawDevice(fifo, 4)
    first.close()
    HidrawDevice(fifo, 4).close()


def test_failed_lock_closes_the_descriptor(fifo):
    first = HidrawDevice(fifo, 4)
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(3):
        with pytest.raises(DeviceBusy):
            HidrawDevice(fifo, 4)
    assert len(os.listdir("/proc/self/fd")) == before
    first.close()


def test_node_is_opened_non_blocking(fifo):
    device = HidrawDevice(fifo, 4)
    assert not os.get_blocking(device._fd)
    device.close()


def test_close_twice_is_harmless(fifo):
    device = HidrawDevice(fifo, 4)
    device.close()
    device.close()
