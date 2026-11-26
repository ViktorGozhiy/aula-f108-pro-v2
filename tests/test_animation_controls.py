import pytest
from PyQt5.QtWidgets import QFileDialog

from aula_f108.ui.animation_controls import GIF_FILTER, OUTCOME_TEXTS, UploadPanel, ask_gif_path, frames_note
from aula_f108.worker import UPLOAD_CANCELLED, UPLOAD_DONE, UPLOAD_FAILED


@pytest.fixture
def panel(qtbot):
    panel = UploadPanel()
    qtbot.addWidget(panel)
    return panel


def test_frames_note_counts_the_frames():
    assert frames_note(3, 3) == "Frames: 3."


def test_frames_note_says_when_frames_were_left_out():
    assert frames_note(4, 3) == "The file has 4 frames. The keyboard takes at most 3, the first 3 are loaded."


def test_upload_needs_an_animation(panel):
    assert not panel.upload_button.isEnabled()
    assert not panel.cancel_button.isEnabled()
    panel.set_ready(True)
    assert panel.upload_button.isEnabled()


def test_running_upload_offers_only_the_cancel(panel):
    panel.set_ready(True)
    panel.finish(UPLOAD_DONE)
    panel.start()
    assert not panel.upload_button.isEnabled()
    assert panel.cancel_button.isEnabled()
    assert panel.message.text() == ""
    assert panel.progress.maximum() == 0  # busy until the first chunk is sent


def test_progress_shows_the_chunks_sent(panel):
    panel.start()
    panel.show_progress(3, 10)
    assert (panel.progress.value(), panel.progress.maximum()) == (3, 10)


@pytest.mark.parametrize("outcome", [UPLOAD_DONE, UPLOAD_CANCELLED, UPLOAD_FAILED])
def test_finished_upload_shows_the_outcome_and_offers_the_upload_again(panel, outcome):
    panel.set_ready(True)
    panel.start()
    panel.finish(outcome)
    assert panel.message.text() == OUTCOME_TEXTS[outcome]
    assert panel.upload_button.isEnabled()
    assert not panel.cancel_button.isEnabled()


@pytest.mark.parametrize("outcome", [UPLOAD_CANCELLED, UPLOAD_FAILED])
def test_upload_that_ends_before_its_first_chunk_stops_the_busy_bar(panel, outcome):
    panel.set_ready(True)
    panel.start()
    panel.finish(outcome)
    assert panel.progress.maximum() != 0
    assert panel.progress.value() == 0


def test_finished_upload_keeps_the_progress_it_reached(panel):
    panel.start()
    panel.show_progress(4, 10)
    panel.finish(UPLOAD_CANCELLED)
    assert (panel.progress.value(), panel.progress.maximum()) == (4, 10)


def test_cancelled_upload_says_the_animation_may_be_partial():
    """A cancel can arrive before the first frame is sent, so the keyboard may be unchanged."""
    text = OUTCOME_TEXTS[UPLOAD_CANCELLED]
    assert "may hold an incomplete animation" in text
    assert "keyboard holds" not in text
    assert "again" in text


def test_buttons_emit_their_signals(panel, qtbot):
    panel.set_ready(True)
    with qtbot.waitSignal(panel.upload_clicked):
        panel.upload_button.click()
    panel.start()
    with qtbot.waitSignal(panel.cancel_clicked):
        panel.cancel_button.click()


def test_ask_gif_path_returns_the_chosen_file(monkeypatch):
    asked = []

    def dialog(*args):
        asked.append(args)
        return "/tmp/a.gif", GIF_FILTER

    monkeypatch.setattr(QFileDialog, "getOpenFileName", dialog)
    assert ask_gif_path(None) == "/tmp/a.gif"
    assert asked[0][3] == GIF_FILTER


def test_ask_gif_path_is_empty_when_cancelled(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    assert ask_gif_path(None) == ""
