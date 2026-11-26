"""Hot-plug events: a netlink socket on the udev multicast group reports hidraw add and remove events.

The events only trigger an immediate probe. The connection state belongs to the worker.
"""
import socket
import sys

from PyQt5.QtCore import QObject, QSocketNotifier, pyqtSignal

NETLINK_KOBJECT_UEVENT = 15  # Python's socket module does not define it
UDEV_GROUP = 2  # udev sends its events after applying its rules, so the uaccess ACL is already in place
LIBUDEV_PREFIX = b"libudev\x00"
PROPERTIES_OFFSET = slice(16, 20)  # properties_off of the libudev header, in the sender's byte order
HIDRAW_SUBSYSTEM = b"SUBSYSTEM=hidraw"
HIDRAW_ACTIONS = (b"ACTION=add", b"ACTION=remove")
MESSAGE_SIZE = 65536


def open_uevent_socket() -> socket.socket:
    sock = socket.socket(
        socket.AF_NETLINK, socket.SOCK_DGRAM | socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC, NETLINK_KOBJECT_UEVENT,
    )
    sock.bind((0, UDEV_GROUP))
    return sock


def is_hidraw_change(message: bytes) -> bool:
    """True for an add or remove event of a hidraw node. Properties are NUL-separated KEY=VALUE fields.

    A udev message starts with a binary header that ends with a tag bloom filter, so its properties are
    read from the offset the header gives. A kernel message has no header.
    """
    if message.startswith(LIBUDEV_PREFIX):
        message = message[int.from_bytes(message[PROPERTIES_OFFSET], sys.byteorder):]
    fields = message.split(b"\x00")
    return HIDRAW_SUBSYSTEM in fields and any(action in fields for action in HIDRAW_ACTIONS)


class HotplugWatcher(QObject):
    """Emits hidraw_changed once for every batch of messages that holds a hidraw add or remove event."""

    hidraw_changed = pyqtSignal()

    def __init__(self, sock: socket.socket):
        super().__init__()
        self._socket = sock
        self._notifier = QSocketNotifier(sock.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_readable)

    def close(self) -> None:
        self._notifier.setEnabled(False)
        self._socket.close()

    def _on_readable(self) -> None:
        changed = False
        while True:
            try:
                message = self._socket.recv(MESSAGE_SIZE)
            except BlockingIOError:
                break
            changed = changed or is_hidraw_change(message)
        if changed:
            self.hidraw_changed.emit()
