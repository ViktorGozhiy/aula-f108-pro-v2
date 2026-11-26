"""Controls shared by the two animation pages: the upload panel, the GIF file choice and the AnimationPage base."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from aula_f108.ui.page import Page
from aula_f108.worker import UPLOAD_CANCELLED, UPLOAD_DONE, UPLOAD_FAILED

GIF_FILTER = "GIF (*.gif)"
OUTCOME_TEXTS = {
    UPLOAD_DONE: "The animation is uploaded to the keyboard.",
    UPLOAD_CANCELLED: "Upload cancelled. The keyboard may hold an incomplete animation: upload it again.",
    UPLOAD_FAILED: "The animation was not uploaded. The keyboard may hold an incomplete animation: upload it again.",
}


def ask_gif_path(parent) -> str:
    """Ask for a GIF file. Returns an empty string when the user cancels."""
    path, _selected_filter = QFileDialog.getOpenFileName(parent, "Open GIF", "", GIF_FILTER)
    return path


def frames_note(total: int, loaded: int) -> str:
    if total > loaded:
        return f"The file has {total} frames. The keyboard takes at most {loaded}, the first {loaded} are loaded."
    return f"Frames: {loaded}."


class UploadPanel(QWidget):
    """The upload button, the progress of a running upload, its cancel button and the outcome."""

    upload_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._ready = False
        self._uploading = False
        self.upload_button = QPushButton("Upload to keyboard")
        self.cancel_button = QPushButton("Cancel upload")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.message = QLabel()
        self.message.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.upload_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.progress, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        layout.addWidget(self.message)

        self.upload_button.clicked.connect(self.upload_clicked)
        self.cancel_button.clicked.connect(self.cancel_clicked)
        self._update_buttons()

    def set_ready(self, ready: bool) -> None:
        """Whether there is an animation to upload."""
        self._ready = ready
        self._update_buttons()

    def start(self) -> None:
        self._uploading = True
        self.progress.setRange(0, 0)
        self.message.clear()
        self._update_buttons()

    def show_progress(self, sent: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(sent)

    def finish(self, outcome: str) -> None:
        self._uploading = False
        if self.progress.maximum() == 0:  # no chunk was sent: the bar must not look busy any longer
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
        self.message.setText(OUTCOME_TEXTS[outcome])
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.upload_button.setEnabled(self._ready and not self._uploading)
        self.cancel_button.setEnabled(self._uploading)


class AnimationPage(Page):
    """A page that uploads a frame animation. Its upload panel shows the progress and the outcome."""

    upload_kind = ""
    upload_requested = pyqtSignal(str, object)  # upload kind, payload bytes
    cancel_upload_requested = pyqtSignal(str)  # upload kind

    def __init__(self):
        super().__init__()
        self.upload_panel = UploadPanel()
        self.upload_panel.upload_clicked.connect(self._upload)
        self.upload_panel.cancel_clicked.connect(lambda: self.cancel_upload_requested.emit(self.upload_kind))

    def payload(self) -> bytes:
        raise NotImplementedError

    def show_upload_progress(self, sent: int, total: int) -> None:
        self.upload_panel.show_progress(sent, total)

    def show_upload_finished(self, outcome: str) -> None:
        self.upload_panel.finish(outcome)

    def _upload(self) -> None:
        self.upload_panel.start()
        self.upload_requested.emit(self.upload_kind, self.payload())
