"""The page shown while no keyboard answers."""

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

HELP = (
    "Check that:\n"
    "• the keyboard is connected with the cable, or is on in 2.4G mode with the dongle plugged into USB;\n"
    "• the udev rule packaging/70-aula-f108-pro-v2.rules is installed (see README.md);\n"
    "• no other program holds the keyboard: the vendor's website in a browser, OpenRGB "
    "or a second copy of this program."
)


class NotConnectedPage(QWidget):
    def __init__(self):
        super().__init__()
        self.reason = QLabel()
        font = QFont(self.reason.font())
        font.setPointSizeF(font.pointSizeF() * 1.3)
        font.setWeight(QFont.Weight.Bold)
        self.reason.setFont(font)
        self.help = QLabel(HELP)
        self.help.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.reason)
        layout.addWidget(self.help)
        layout.addStretch(1)

    def show_reason(self, reason: str) -> None:
        self.reason.setText(reason)
