import dataclasses

import pytest
from PyQt5.QtWidgets import QFileDialog

from aula_f108.animation import Animation
from aula_f108.blocks import device_info, led_effect
from aula_f108.ui.animation_controls import GIF_FILTER, OUTCOME_TEXTS
from aula_f108.ui.backlight_page import ANIMATION_NOTE, PER_KEY_NOTE
from aula_f108.ui.key_animation_page import KeyAnimationPage
from aula_f108.ui.key_colours_page import KeyColoursPage
from aula_f108.worker import KEY_ANIMATION, UPLOAD_CANCELLED, UPLOAD_DONE
from fixture_data import load_hex
from gif_files import BLUE, GREEN, RED, three_frame_gif, write_gif
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of

INFO = device_info.decode(load_hex("wired-10.hex"))  # gif_max_frames 512
ESC = 0


@pytest.fixture
def page(qtbot):
    page = KeyAnimationPage()
    qtbot.addWidget(page)
    page.uploads = []
    page.upload_requested.connect(lambda kind, payload: page.uploads.append((kind, payload)))
    return page


def test_starts_without_an_animation(page):
    assert page.file_label.text() == "No file chosen"
    assert not page.upload_panel.upload_button.isEnabled()
    assert not page.preview_timer.isActive()


def test_loaded_gif_is_shown_on_the_keys(page, tmp_path):
    page.load_file(three_frame_gif(tmp_path / "heart.gif"))
    assert page.file_label.text() == "heart.gif"
    assert page.frames_label.text() == "Frames: 3."
    assert page.keyboard.colour(ESC) == RED
    assert page.preview_timer.isActive()
    assert page.upload_panel.upload_button.isEnabled()


def test_preview_steps_through_the_frames_and_wraps(page, tmp_path):
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    seen = []
    for _ in range(3):
        page.preview_timer.timeout.emit()
        seen.append(page.keyboard.colour(ESC))
    assert seen == [BLUE, GREEN, RED]


def test_preview_speed_follows_the_slider(page):
    assert page.preview_timer.interval() == 110
    page.speed.setValue(50)
    assert page.preview_timer.interval() == 510


def test_frame_limit_comes_from_device_info(page, tmp_path):
    page.show_block("device_info", dataclasses.replace(INFO, gif_max_frames=2))
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    assert page.frames_label.text().startswith("The file has 3 frames.")
    page.preview_timer.timeout.emit()
    page.preview_timer.timeout.emit()
    assert page.keyboard.colour(ESC) == RED


def test_file_that_is_no_image_is_reported(page, tmp_path):
    (tmp_path / "a.gif").write_text("not an image")
    page.load_file(str(tmp_path / "a.gif"))
    assert page.frames_label.text().startswith("Could not open the file")
    assert not page.upload_panel.upload_button.isEnabled()


def test_damaged_file_is_reported(page, tmp_path):
    data = open(three_frame_gif(tmp_path / "a.gif"), "rb").read()
    (tmp_path / "cut.gif").write_bytes(data[:111])
    page.load_file(str(tmp_path / "cut.gif"))
    assert page.frames_label.text().startswith("Could not open the file")
    assert not page.upload_panel.upload_button.isEnabled()


def test_second_file_starts_the_preview_from_its_first_frame(page, tmp_path):
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    page.preview_timer.timeout.emit()
    page.preview_timer.timeout.emit()
    write_gif(tmp_path / "b.gif", [[[BLUE, BLUE]]])
    page.load_file(str(tmp_path / "b.gif"))
    assert page.keyboard.colour(ESC) == BLUE
    page.preview_timer.timeout.emit()
    assert page.keyboard.colour(ESC) == BLUE


def test_open_button_loads_the_chosen_file(page, tmp_path, monkeypatch):
    path = three_frame_gif(tmp_path / "a.gif")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (path, GIF_FILTER))
    page.open_button.click()
    assert page.file_label.text() == "a.gif"


def test_cancelled_file_dialog_changes_nothing(page, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    page.open_button.click()
    assert page.file_label.text() == "No file chosen"


def test_upload_sends_the_frames_in_layout_order(page, tmp_path):
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    page.speed.setValue(80)
    page.upload_panel.upload_button.click()
    assert page.uploads == [(KEY_ANIMATION, Animation(page._frames, 80).payload(108))]
    assert page.upload_panel.cancel_button.isEnabled()


def test_cancel_button_asks_for_the_cancel_of_the_key_animation(page, tmp_path, qtbot):
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    page.upload_panel.upload_button.click()
    with qtbot.waitSignal(page.cancel_upload_requested) as blocker:
        page.upload_panel.cancel_button.click()
    assert blocker.args == [KEY_ANIMATION]


def test_upload_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyAnimationPage)
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    page.upload_panel.upload_button.click()
    rig.step()
    payload = Animation(page._frames, 90).payload(108)
    assert sim.uploaded(0x42)[:len(payload)] == payload
    assert led_effect.decode(bytes(sim.blocks["led_effect"])).mode == 0xFF
    assert page.upload_panel.message.text() == OUTCOME_TEXTS[UPLOAD_DONE]
    chunks = -(-len(payload) // 56)
    assert (page.upload_panel.progress.value(), page.upload_panel.progress.maximum()) == (chunks, chunks)
    assert settings.value("led_effect/colour") is None


def test_frame_limit_reaches_the_page_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.blocks["device_info"][24:26] = (2).to_bytes(2, "little")
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyAnimationPage)
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    assert page.frames_label.text().startswith("The file has 3 frames.")


def test_cancel_through_the_window(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = page_of(window, KeyAnimationPage)
    page.load_file(three_frame_gif(tmp_path / "a.gif"))
    page.upload_panel.upload_button.click()
    page.upload_panel.cancel_button.click()
    rig.step()
    assert sim.uploads == []
    assert page.upload_panel.message.text() == OUTCOME_TEXTS[UPLOAD_CANCELLED]


def test_backlight_notes_link_to_the_per_key_pages():
    assert f'href="{KeyColoursPage.title}"' in PER_KEY_NOTE
    assert f'href="{KeyAnimationPage.title}"' in ANIMATION_NOTE


def test_backlight_links_open_the_per_key_pages(qtbot, tmp_path):
    window, rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    rig.step()
    window.pages[0].current_note.linkActivated.emit(KeyColoursPage.title)
    assert window.stack.currentWidget() is page_of(window, KeyColoursPage)
    window.pages[0].current_note.linkActivated.emit(KeyAnimationPage.title)
    assert window.stack.currentWidget() is page_of(window, KeyAnimationPage)
    assert window.sidebar.currentRow() == window.pages.index(page_of(window, KeyAnimationPage))
