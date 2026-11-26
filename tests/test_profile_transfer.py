import json

from aula_f108 import profile
from aula_f108.blocks import key_colours, macros
from aula_f108.blocks.key_tables import BASE
from aula_f108.blocks.macros import MacroAction
from aula_f108.key_actions import KeyboardKey
from aula_f108.keyboard import BLOCKS
from aula_f108.profile import EXPORTED_BLOCKS, IMPORT_ORDER, MODEL
from aula_f108.ui import device_page
from aula_f108.ui.device_page import PROFILE_NOTE, PROFILE_RUNNING, DevicePage
from aula_f108.ui.key_colours_page import KeyColoursPage
from aula_f108.ui.key_remap_page import KeyRemapPage
from aula_f108.ui.light_box_page import LightBoxPage
from aula_f108.ui.macros_page import MacrosPage
from aula_f108.ui.profile_controller import BLOCK_NAMES, NOTHING_TO_IMPORT, ProfileController
from aula_f108.worker import GONE, READ_FAILED, RESTARTING, ConnectionState
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of
from worker_rig import Rig

PRESS_A = MacroAction(10, 0x04, True)
RELEASE_A = MacroAction(20, 0x04, False)
ALL_WRITTEN = (
    "Written: backlight, side lighting, key colours, base layer, Fn layer, macros, settings."
)


def connected_window(qtbot, tmp_path, sim=None):
    sim = sim or SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    return window, rig, sim


def export_with(window, monkeypatch, path):
    monkeypatch.setattr(device_page, "ask_export_path", lambda parent: str(path))
    window.device_page.export_button.click()


def import_from(window, monkeypatch, path):
    monkeypatch.setattr(device_page, "ask_import_path", lambda parent: str(path))
    window.device_page.import_button.click()


def file_of(sim, tmp_path, name="source.json"):
    """A configuration file with the blocks of a simulated keyboard."""
    values = {block: BLOCKS[block].decode(bytes(sim.blocks[block])) for block in EXPORTED_BLOCKS}
    path = tmp_path / name
    profile.save(path, profile.export_profile(values, {"led_effect": (0, 0, 255), "light_box": (0, 255, 0)}))
    return path


def changed_keyboard():
    sim = SimulatedKeyboard()
    sim.blocks["settings"][3] = 10                       # sleep after 10 minutes
    sim.blocks["led_effect"][0] = 7                      # breathing
    sim.blocks["light_box"][9] = 4                       # brightness 4
    sim.blocks["key_colours"][1:4] = bytes([1, 2, 3])    # Esc
    sim.blocks["base_keys"][0:4] = bytes([2, 0, 0x04, 0])  # Esc types A
    sim.blocks["fn_keys"][4:8] = bytes([0x0D, 0, 0, 9])  # Fn+F1: Mac mode
    raw = macros.encode_into(bytes(sim.blocks["macros"][:400]), {"macros": {3: (PRESS_A, RELEASE_A)}})
    sim.blocks["macros"][:len(raw)] = raw
    return sim


def test_device_page_explains_the_file(qtbot):
    page = DevicePage()
    qtbot.addWidget(page)
    assert page.profile_note.text() == PROFILE_NOTE
    assert "Animations and the 7×7 display are not saved" in PROFILE_NOTE


def test_cancelled_file_choice_starts_nothing(qtbot, monkeypatch):
    page = DevicePage()
    qtbot.addWidget(page)
    requests = []
    page.export_requested.connect(requests.append)
    page.import_requested.connect(requests.append)
    monkeypatch.setattr(device_page, "ask_export_path", lambda parent: "")
    monkeypatch.setattr(device_page, "ask_import_path", lambda parent: "")
    page.export_button.click()
    page.import_button.click()
    assert requests == []
    assert page.export_button.isEnabled()


def test_buttons_are_disabled_until_the_result(qtbot, monkeypatch, tmp_path):
    page = DevicePage()
    qtbot.addWidget(page)
    requests = []
    page.export_requested.connect(requests.append)
    monkeypatch.setattr(device_page, "ask_export_path", lambda parent: str(tmp_path / "a.json"))
    page.export_button.click()
    assert requests == [str(tmp_path / "a.json")]
    assert page.profile_result.text() == PROFILE_RUNNING
    assert not page.export_button.isEnabled()
    assert not page.import_button.isEnabled()
    page.show_profile_result("Done.")
    assert page.profile_result.text() == "Done."
    assert page.export_button.isEnabled()
    assert page.import_button.isEnabled()


def test_export_reads_the_blocks_and_saves_the_file(qtbot, tmp_path, monkeypatch):
    window, rig, sim = connected_window(qtbot, tmp_path, changed_keyboard())
    path = tmp_path / "profile.json"
    export_with(window, monkeypatch, path)
    assert not path.exists()  # the blocks are read first
    rig.step(len(EXPORTED_BLOCKS))
    data = json.loads(path.read_text())
    assert data["model"] == MODEL
    assert data["settings"]["sleep_minutes"] == 10
    assert data["led_effect"]["colour"] == [0, 255, 255]  # the colour the backlight page shows
    assert data["light_box"]["colour"] == [255, 255, 255]  # not reported: the page's white
    assert data["base_keys"]["0"] == {"type": "keyboard", "usage": 4}
    assert data["macros"]["3"][0] == {"delay": 10, "code": 4, "press": True, "kind": 3}
    assert window.device_page.profile_result.text() == f"Settings saved to {path}."
    assert window.device_page.export_button.isEnabled()


def test_export_ignores_reads_of_other_blocks(qtbot, tmp_path, monkeypatch):
    window, rig, _sim = connected_window(qtbot, tmp_path)
    rig.worker.request_read("device_info")
    path = tmp_path / "profile.json"
    export_with(window, monkeypatch, path)
    rig.step(1 + len(EXPORTED_BLOCKS))
    assert path.exists()


def test_export_ignores_failed_reads_of_other_blocks(qtbot, tmp_path, monkeypatch):
    window, rig, sim = connected_window(qtbot, tmp_path)
    sim.drop[0x3D] = 4
    rig.worker.request_read("dot_matrix")
    path = tmp_path / "profile.json"
    export_with(window, monkeypatch, path)
    rig.step(1 + len(EXPORTED_BLOCKS))
    assert path.exists()
    assert window.device_page.profile_result.text() == f"Settings saved to {path}."


def test_export_that_cannot_write_the_file_says_so(qtbot, tmp_path, monkeypatch):
    window, rig, _sim = connected_window(qtbot, tmp_path)
    export_with(window, monkeypatch, tmp_path / "missing" / "profile.json")
    rig.step(len(EXPORTED_BLOCKS))
    assert window.device_page.profile_result.text().startswith("Settings not saved: [Errno 2]")


def test_export_with_a_failed_read_saves_nothing(qtbot, tmp_path, monkeypatch):
    window, rig, sim = connected_window(qtbot, tmp_path)
    sim.drop[0x15] = 4
    path = tmp_path / "profile.json"
    export_with(window, monkeypatch, path)
    rig.step(len(EXPORTED_BLOCKS))
    assert not path.exists()
    assert window.device_page.profile_result.text() == (
        f"Settings not saved: could not read “macros”. {READ_FAILED}"
    )


def test_export_stops_when_the_keyboard_is_lost(qtbot, tmp_path, monkeypatch):
    window, rig, sim = connected_window(qtbot, tmp_path)
    path = tmp_path / "profile.json"
    export_with(window, monkeypatch, path)
    sim.gone = True
    rig.step()
    assert not path.exists()
    assert window.device_page.profile_result.text() == f"Settings not saved: {GONE}."


def test_import_writes_every_block_of_the_file_and_reads_every_block(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step(len(IMPORT_ORDER))
    assert window.device_page.profile_result.text() == ALL_WRITTEN
    assert sim.blocks["settings"][3] == 10
    assert sim.blocks["led_effect"][0:4] == bytes([7, 0, 0, 255])
    assert sim.blocks["light_box"][1:4] == bytes([0, 255, 0])
    assert sim.blocks["light_box"][9] == 4
    assert sim.blocks["key_colours"][1:4] == bytes([1, 2, 3])
    assert sim.blocks["base_keys"][0:4] == bytes([2, 0, 4, 0])
    assert sim.blocks["fn_keys"][4:8] == bytes([0x0D, 0, 0, 9])
    assert macros.decode(bytes(sim.blocks["macros"])).macros[3] == (PRESS_A, RELEASE_A)
    assert bytes(sim.blocks["base_keys"][60:64]) == load_hex("wired-12.hex")[60:64]  # outside the layout: kept
    rig.events.clear()
    rig.step(len(BLOCKS))
    assert [event[0] for event in rig.of_kind("read")] == list(BLOCKS)


def test_import_shows_the_written_light_box_colour_and_keeps_it(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)  # the light box colour (0, 255, 0)
    window, rig, sim = connected_window(qtbot, tmp_path)
    page = page_of(window, LightBoxPage)
    assert page.colour.colour() == (255, 255, 255)
    import_from(window, monkeypatch, path)
    rig.step(len(IMPORT_ORDER) + len(BLOCKS))  # the writes and the reads after them
    assert page.colour.colour() == (0, 255, 0)
    page.brightness.setValue(2)
    rig.step()
    assert sim.blocks["light_box"][1:4] == bytes([0, 255, 0])
    assert sim.blocks["light_box"][9] == 2
    export_path = tmp_path / "profile.json"
    export_with(window, monkeypatch, export_path)
    rig.step(len(EXPORTED_BLOCKS))
    assert json.loads(export_path.read_text())["light_box"]["colour"] == [0, 255, 0]


def test_import_of_a_bad_file_writes_nothing(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"model": "AULA F87", "format": 1}))
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step()
    assert (window.device_page.profile_result.text()
            == "Settings not loaded: the file was not saved for AULA F108 Pro V2.")
    assert sim.writes == []
    assert window.device_page.import_button.isEnabled()


def test_import_of_a_malformed_action_type_writes_nothing(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"model": MODEL, "format": 1, "base_keys": {"0": {"type": []}}}))
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step()
    assert window.device_page.profile_result.text().startswith("Settings not loaded: section base_keys:")
    assert sim.writes == []
    assert window.device_page.import_button.isEnabled()


def test_import_of_a_file_without_sections_writes_nothing(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"model": MODEL, "format": 1}))
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    assert window.device_page.profile_result.text() == NOTHING_TO_IMPORT
    assert sim.writes == []


def test_import_reports_the_blocks_that_were_not_written(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    sim.drop[0x25] = 4
    import_from(window, monkeypatch, path)
    rig.step(len(IMPORT_ORDER))
    assert window.device_page.profile_result.text() == (
        "Written: backlight, side lighting, key colours, base layer, Fn layer, settings. "
        "Not written: macros (Change not written. The keyboard did not answer.)."
    )


def test_import_without_any_written_block_lists_only_the_failures(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": MODEL, "format": 1, "settings": {"debounce": 2}}))
    window, rig, sim = connected_window(qtbot, tmp_path)
    sim.drop[0x21] = 4
    import_from(window, monkeypatch, path)
    rig.step()
    assert window.device_page.profile_result.text() == (
        "Not written: settings (Change not written. The keyboard did not answer.)."
    )


def test_import_ignores_results_that_are_not_of_its_own_writes(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, _sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.worker.write_failed.emit("factory_reset", "Change not written.")
    rig.worker.write_failed.emit("led_effect", "Change not written.")
    rig.worker.batch_update_finished.emit(1000, "led_effect", False, "Change not written.")  # another batch
    assert window.device_page.profile_result.text() == PROFILE_RUNNING
    rig.step(len(IMPORT_ORDER))
    assert window.device_page.profile_result.text() == ALL_WRITTEN


def test_write_queued_before_the_import_is_not_taken_for_its_first_block(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    rig.worker.request_update("led_effect", {"speed": 99})  # refused; queued before the import's first block
    import_from(window, monkeypatch, path)
    rig.step(1)
    assert window.device_page.profile_result.text() == PROFILE_RUNNING
    assert not any(button.isEnabled() for button in apply_pages(window))
    rig.step(len(IMPORT_ORDER))
    assert window.device_page.profile_result.text() == ALL_WRITTEN
    assert sim.blocks["led_effect"][0] == 7


def test_import_ends_with_the_led_mode_of_the_file_after_a_queued_apply_of_the_colours(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)  # LED mode 7
    window, rig, sim = connected_window(qtbot, tmp_path)
    page = page_of(window, KeyColoursPage)
    page.keyboard.touched.emit(0)
    page.apply.click()  # the colours write is queued; the switch to mode 20 would follow it
    import_from(window, monkeypatch, path)
    rig.step(20)
    assert window.device_page.profile_result.text() == ALL_WRITTEN
    assert sim.blocks["led_effect"][0] == 7


def test_import_that_restarts_the_keyboard_reports_the_rest(qtbot, tmp_path, monkeypatch):
    source = changed_keyboard()
    source.blocks["settings"][5] = 3  # 1 kHz: the cable restarts after the write
    path = file_of(source, tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    sim.drop[0x21] = 4
    import_from(window, monkeypatch, path)
    rig.step(len(IMPORT_ORDER))
    assert window.device_page.profile_result.text() == (
        "Written: backlight, side lighting, key colours, base layer, Fn layer, macros. "
        f"Not written: settings ({RESTARTING})."
    )


class RestartingKeyboard(SimulatedKeyboard):
    """Leaves a write of the settings with a polling rate of 1 kHz unanswered, as the cable restarts."""

    def _answer(self, packet):
        if packet[1] == 0x21 and packet[3] | packet[4] << 8 == 0 and packet[8 + 5] == 3:
            return None
        return super()._answer(packet)


def test_import_behind_a_queued_settings_write_keeps_the_settings_last(qtbot, tmp_path, monkeypatch):
    source = changed_keyboard()
    source.blocks["settings"][5] = 3  # 1 kHz: the cable restarts after the write
    path = file_of(source, tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path, RestartingKeyboard())
    rig.worker.request_update("settings", {"debounce": 2})  # queued before the import
    import_from(window, monkeypatch, path)
    rig.step(1 + len(IMPORT_ORDER))
    assert sim.blocks["base_keys"][0:4] == bytes([2, 0, 4, 0])
    assert window.device_page.profile_result.text() == (
        "Written: backlight, side lighting, key colours, base layer, Fn layer, macros. "
        f"Not written: settings ({RESTARTING})."
    )


def test_connected_state_keeps_the_export_and_the_import_running(qtbot, tmp_path, monkeypatch):
    window, rig, _sim = connected_window(qtbot, tmp_path)
    path = tmp_path / "profile.json"
    export_with(window, monkeypatch, path)
    rig.worker.state_changed.emit(ConnectionState("connected", "cable"))
    rig.step(len(EXPORTED_BLOCKS))
    assert window.device_page.profile_result.text() == f"Settings saved to {path}."
    import_from(window, monkeypatch, path)
    rig.worker.state_changed.emit(ConnectionState("connected", "cable"))
    rig.step(len(IMPORT_ORDER))
    assert window.device_page.profile_result.text() == ALL_WRITTEN


def test_writes_without_an_import_report_nothing(qtbot, tmp_path):
    window, rig, _sim = connected_window(qtbot, tmp_path)
    rig.worker.request_update("settings", {"debounce": 2})
    rig.step()
    assert window.device_page.profile_result.text() == ""


A_KEY = 49
SETTLED_STEPS = 40  # more than the queue of an import, the reads after it and the writes of one "Apply"


def apply_pages(window):
    return [page_of(window, page_type).apply for page_type in (KeyColoursPage, KeyRemapPage, MacrosPage)]


def edit_pages(window):
    """Edit the key colours, the key table and the macros, so that every "Apply" has something to write."""
    colours = page_of(window, KeyColoursPage)
    colours.colour.set_colour((9, 9, 9))
    colours.keyboard.touched.emit(A_KEY)
    remap = page_of(window, KeyRemapPage)
    remap.keyboard.touched.emit(A_KEY)
    remap.editor.show_action(KeyboardKey(0x05))
    remap.editor.assign.click()
    macros_page = page_of(window, MacrosPage)
    macros_page.key.set_usage(0x05)
    macros_page.add.click()


def test_apply_of_the_key_page_during_an_import_is_disabled_and_works_after_it(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step(1)  # only the LED effect is written
    page = page_of(window, KeyRemapPage)
    page.keyboard.touched.emit(A_KEY)
    page.editor.show_action(KeyboardKey(0x05))
    page.editor.assign.click()
    assert not page.apply.isEnabled()
    page.apply.click()  # ignored
    rig.step(SETTLED_STEPS)
    assert bytes(sim.blocks[BASE][A_KEY * 4:A_KEY * 4 + 4]) != bytes([2, 0, 5, 0])
    assert page.keyboard.is_marked(A_KEY)
    assert page.apply.isEnabled()
    page.apply.click()
    rig.step(SETTLED_STEPS)
    assert bytes(sim.blocks[BASE][A_KEY * 4:A_KEY * 4 + 4]) == bytes([2, 0, 5, 0])
    assert not page.keyboard.is_marked(A_KEY)
    assert page.edited_label.text() == ""


def test_apply_of_the_colours_page_during_an_import_is_disabled_and_works_after_it(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step(1)
    page = page_of(window, KeyColoursPage)
    page.colour.set_colour((9, 9, 9))
    page.keyboard.touched.emit(A_KEY)
    assert not page.apply.isEnabled()
    page.apply.click()  # ignored
    rig.step(SETTLED_STEPS)
    assert key_colours.decode(bytes(sim.blocks["key_colours"])).colours[A_KEY] != (9, 9, 9)
    assert page.keyboard.is_marked(A_KEY)
    assert page.apply.isEnabled()
    page.apply.click()
    rig.step(SETTLED_STEPS)
    assert key_colours.decode(bytes(sim.blocks["key_colours"])).colours[A_KEY] == (9, 9, 9)
    assert not page.keyboard.is_marked(A_KEY)
    assert page.edited_label.text() == ""


def test_apply_of_the_macros_page_during_an_import_is_disabled_and_works_after_it(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step(1)
    page = page_of(window, MacrosPage)
    page.slots.setCurrentRow(0)
    page.key.set_usage(0x05)
    page.add.click()
    assert not page.apply.isEnabled()
    rig.step(SETTLED_STEPS)
    assert page.apply.isEnabled()
    page.apply.click()
    rig.step(SETTLED_STEPS)
    assert macros.decode(bytes(sim.blocks["macros"])).macros[0] == (MacroAction(50, 0x05, True),)
    assert page.edited_label.text() == ""


def test_apply_buttons_follow_the_import_from_its_start_to_its_result(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, _sim = connected_window(qtbot, tmp_path)
    edit_pages(window)
    assert all(button.isEnabled() for button in apply_pages(window))
    import_from(window, monkeypatch, path)
    assert not any(button.isEnabled() for button in apply_pages(window))
    rig.step(len(IMPORT_ORDER) - 1)
    assert not any(button.isEnabled() for button in apply_pages(window))
    rig.step(1)
    assert all(button.isEnabled() for button in apply_pages(window))


def test_apply_buttons_are_enabled_again_when_the_import_loses_the_keyboard(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    edit_pages(window)
    import_from(window, monkeypatch, path)
    rig.step(1)
    assert not any(button.isEnabled() for button in apply_pages(window))
    sim.gone = True
    rig.step()
    assert "Not written" in window.device_page.profile_result.text()
    assert all(button.isEnabled() for button in apply_pages(window))


def test_import_of_one_section_does_not_finish_before_its_own_write(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "base_keys.json"
    path.write_text(json.dumps({"model": MODEL, "format": 1, "base_keys": {"0": {"type": "keyboard", "usage": 4}}}))
    window, rig, sim = connected_window(qtbot, tmp_path)
    page = page_of(window, KeyRemapPage)
    page.keyboard.touched.emit(A_KEY)
    page.editor.show_action(KeyboardKey(0x05))
    page.editor.assign.click()
    page.apply.click()  # its write of the key table is queued before the import's
    import_from(window, monkeypatch, path)
    rig.step(1)  # the write of the page
    page.keyboard.touched.emit(A_KEY + 1)
    page.editor.show_action(KeyboardKey(0x06))
    page.editor.assign.click()
    assert window.device_page.profile_result.text() == PROFILE_RUNNING
    assert not page.apply.isEnabled()
    rig.step(1)  # the write of the import
    assert window.device_page.profile_result.text() == "Written: base layer."
    assert page.apply.isEnabled()
    page.apply.click()
    rig.step(SETTLED_STEPS)
    assert bytes(sim.blocks[BASE][0:4]) == bytes([2, 0, 4, 0])
    assert bytes(sim.blocks[BASE][(A_KEY + 1) * 4:(A_KEY + 1) * 4 + 4]) == bytes([2, 0, 6, 0])
    assert not page.keyboard.is_marked(A_KEY + 1)
    assert not page.apply.isEnabled()


def test_import_that_loses_the_keyboard_reports_the_blocks_not_written(qtbot, tmp_path, monkeypatch):
    path = file_of(changed_keyboard(), tmp_path)
    window, rig, sim = connected_window(qtbot, tmp_path)
    import_from(window, monkeypatch, path)
    rig.step(1)
    sim.gone = True
    rig.step()
    assert window.device_page.profile_result.text() == (
        "Written: backlight. Not written: " + "; ".join(
            f"{BLOCK_NAMES[block]} ({GONE})" for block in IMPORT_ORDER[1:]) + "."
    )


def test_import_ends_when_the_worker_drops_its_writes_without_a_state_change(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.silent = True
    rig = Rig(cable=sim)
    rig.step()  # no keyboard answers: the state is already "not connected" and stays so
    controller = ProfileController(rig.worker, lambda: {})
    results = []
    controller.finished.connect(results.append)
    running = []
    controller.import_running.connect(running.append)
    path = tmp_path / "led.json"
    path.write_text(json.dumps({"model": MODEL, "format": 1, "led_effect": {"speed": 2}}))
    controller.import_from(str(path))
    rig.step()
    assert running == [True, False]
    assert results == ["Not written: backlight (Change not written. Keyboard not connected.)."]


def test_apply_buttons_are_enabled_again_when_every_block_of_the_import_fails(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": MODEL, "format": 1, "settings": {"debounce": 2}}))
    window, rig, sim = connected_window(qtbot, tmp_path)
    edit_pages(window)
    sim.drop[0x21] = 4
    import_from(window, monkeypatch, path)
    assert not any(button.isEnabled() for button in apply_pages(window))
    rig.step()
    assert all(button.isEnabled() for button in apply_pages(window))


def test_import_of_a_file_that_is_refused_keeps_the_apply_buttons_enabled(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"model": "AULA F87", "format": 1}))
    window, rig, _sim = connected_window(qtbot, tmp_path)
    edit_pages(window)
    import_from(window, monkeypatch, path)
    assert all(button.isEnabled() for button in apply_pages(window))
