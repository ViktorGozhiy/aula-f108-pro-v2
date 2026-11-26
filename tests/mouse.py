"""Mouse events sent straight to a widget, so a drag works without a window system."""
from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication


def _send(widget, kind, point, button, buttons):
    QApplication.sendEvent(widget, QMouseEvent(kind, QPointF(point), button, buttons, Qt.KeyboardModifier.NoModifier))


def press(widget, point, button=Qt.MouseButton.LeftButton):
    _send(widget, QEvent.Type.MouseButtonPress, point, button, button)


def move(widget, point):
    _send(widget, QEvent.Type.MouseMove, point, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)


def release(widget, point, button=Qt.MouseButton.LeftButton):
    _send(widget, QEvent.Type.MouseButtonRelease, point, button, Qt.MouseButton.NoButton)
