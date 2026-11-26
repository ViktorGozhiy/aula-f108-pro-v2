import pytest
from PyQt5.QtWidgets import QMessageBox

from aula_f108.blocks import led_effect, light_box
from aula_f108.blocks.light_box import LightBox
from aula_f108.ui import main_window
from aula_f108.ui.backlight_page import BacklightPage
from aula_f108.ui.device_page import DevicePage
from aula_f108.ui.light_box_page import LightBoxPage
from aula_f108.ui.settings_page import SettingsPage
from aula_f108.worker import ASLEEP, LINK_LOST_TEXT, READ_FAILED, RESTARTING, SEARCHING
from fixture_data import load_hex
from simkeyboard import SimulatedKeyboard
from window_rig import make_window, page_of


def dongle_keyboard(battery=80, charge_status=0):
    sim = SimulatedKeyboard(32)
    sim.blocks["device_info"][17] = battery
    sim.blocks["device_info"][18] = charge_status
    return sim


def test_shows_the_search_before_the_first_probe(qtbot, tmp_path):
    window, _rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    assert window.stack.currentWidget() is window.not_connected
    assert window.not_connected.reason.text() == SEARCHING
    assert not window.sidebar.isEnabled()
    assert window.connection_label.text() == SEARCHING


def test_builds_every_page(qtbot, tmp_path):
    window, _rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    titles = [window.sidebar.item(row).text() for row in range(window.sidebar.count())]
    assert titles == [
        "Backlight",
        "Key colours",
        "Key animation",
        "Side lighting",
        "7×7 display",
        "Keys",
        "Macros",
        "Settings",
        "Device",
    ]
    assert isinstance(window.pages[0], BacklightPage)
    assert isinstance(window.pages[-1], DevicePage)


def test_connected_on_the_cable(qtbot, tmp_path):
    window, rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    rig.step()
    assert window.stack.currentWidget() is window.pages[0]
    assert window.sidebar.isEnabled()
    assert window.connection_label.text() == "Cable"
    assert window.firmware_label.text() == "Firmware V1.33"
    assert window.battery_label.text() == "Charging"  # the captured read has charge status 1


def test_cable_without_charging_shows_no_battery_text(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.blocks["device_info"][18] = 0
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    assert window.battery_label.text() == ""


def test_dongle_shows_the_battery_level(qtbot, tmp_path):
    window, rig, _settings = make_window(qtbot, tmp_path, dongle=dongle_keyboard(80, 0))
    rig.step()
    assert window.connection_label.text() == "2.4G"
    assert window.battery_label.text() == "Battery 80 %"


def test_dongle_shows_charging(qtbot, tmp_path):
    window, rig, _settings = make_window(qtbot, tmp_path, dongle=dongle_keyboard(55, 1))
    rig.step()
    assert window.battery_label.text() == "Battery 55 %, charging"


@pytest.mark.parametrize(("notification", "reason"), [("55fc06", ASLEEP), ("55fc04", LINK_LOST_TEXT)])
def test_sleep_and_link_lost_show_the_not_connected_page_and_the_reason_in_the_status_bar(
    qtbot, tmp_path, notification, reason
):
    sim = dongle_keyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, dongle=sim)
    rig.step()
    sim.push(bytes.fromhex(notification))
    rig.step()
    assert window.stack.currentWidget() is window.not_connected
    assert window.not_connected.reason.text() == reason
    assert window.connection_label.text() == reason
    assert not window.sidebar.isEnabled()
    assert window.firmware_label.text() == ""
    assert window.battery_label.text() == ""


def test_reconnect_shows_the_page_selected_in_the_sidebar(qtbot, tmp_path):
    sim = dongle_keyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, dongle=sim)
    rig.step()
    window.sidebar.setCurrentRow(2)
    sim.push(bytes.fromhex("55fc06"))
    rig.step()
    rig.worker.request_probe()
    rig.step()
    assert window.stack.currentWidget() is window.pages[2]


def test_device_page_shows_the_device(qtbot, tmp_path):
    window, rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    rig.step()
    page = window.device_page
    assert page.model_value.text() == "AULA F108 Pro V2 (38a6:2739)"
    assert page.connection_value.text() == "Cable (USB)"
    assert page.firmware_value.text() == "V1.33"
    assert page.charge_value.text() == "charging"
    assert page.battery_value.isHidden()


def test_device_page_shows_the_battery_on_the_dongle(qtbot, tmp_path):
    window, rig, _settings = make_window(qtbot, tmp_path, dongle=dongle_keyboard(80, 0))
    rig.step()
    page = window.device_page
    assert page.connection_value.text() == "2.4G (dongle)"
    assert not page.battery_value.isHidden()
    assert page.battery_value.text() == "80 %"
    assert page.charge_value.text() == "not charging"


def test_device_page_without_connection(qtbot, tmp_path):
    window, _rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    assert window.device_page.connection_value.text() == "—"


def test_selecting_a_page_reads_its_blocks(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    reads = sim.sent_commands().count(0x10)
    window.sidebar.setCurrentRow(window.pages.index(window.device_page))
    rig.step()
    assert window.stack.currentWidget() is window.device_page
    assert sim.sent_commands().count(0x10) == reads + 1


def test_selecting_a_page_without_keyboard_does_nothing(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.silent = True
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    window.sidebar.setCurrentRow(1)
    assert window.stack.currentWidget() is window.not_connected


def test_backlight_change_writes_the_led_effect(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = window.pages[0]
    page.mode.setCurrentIndex(page.mode.findData(7))
    rig.step()
    # The fixture reports cyan, a colour chosen on the keyboard, so the page sends it.
    assert sim.writes == [
        (0x23, 0, led_effect.encode_into(load_hex("wired-13.hex"), {"mode": 7, "colour": (0, 255, 255)}))
    ]
    assert page.mode.currentData() == 7


def test_backlight_keeps_the_colour_chosen_on_the_keyboard(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.choose_led_colour((255, 0, 0))
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = window.pages[0]
    assert page.colour.colour() == (255, 0, 0)
    page.brightness.setValue(2)
    rig.step()
    assert led_effect.decode(sim.writes[-1][2]).colour == (255, 0, 0)
    assert led_effect.decode(sim.writes[-1][2]).brightness == 2


def test_backlight_keeps_the_chosen_colour_when_another_field_changes(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = window.pages[0]
    page.colour.choose((0, 128, 0))
    rig.step()
    page.brightness.setValue(2)
    rig.step()
    assert led_effect.decode(sim.writes[-1][2]).colour == (0, 128, 0)
    assert led_effect.decode(sim.writes[-1][2]).brightness == 2


def test_failed_read_disables_the_page_until_a_read_succeeds(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    sim.drop[0x13] = 4
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page = window.pages[0]
    assert not page.body.isEnabled()
    assert page.failure_label.text() == READ_FAILED
    window.sidebar.setCurrentRow(window.pages.index(window.device_page))
    window.sidebar.setCurrentRow(0)
    rig.step(2)
    assert page.body.isEnabled()


def test_failed_write_is_reported_and_the_keyboard_value_shown(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    sim.drop[0x23] = 4
    page = window.pages[0]
    page.brightness.setValue(2)
    rig.step()
    assert window.statusBar().currentMessage() == "Change not written. The keyboard did not answer."
    rig.step()
    assert page.brightness.value() == 5


def test_failed_factory_reset_is_reported_without_a_read(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    sent = len(sim.packets)
    rig.worker.write_failed.emit("factory_reset", "Change not written. Keyboard not connected.")
    rig.step()
    assert window.statusBar().currentMessage() == "Change not written. Keyboard not connected."
    assert len(sim.packets) == sent


def test_write_failure_message_stays_for_the_status_message_time(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window, "STATUS_MESSAGE_MS", 50)
    window, rig, _settings = make_window(qtbot, tmp_path, cable=SimulatedKeyboard())
    rig.step()
    rig.worker.write_failed.emit("factory_reset", "Change not written.")
    assert window.statusBar().currentMessage() == "Change not written."
    qtbot.waitUntil(lambda: window.statusBar().currentMessage() == "", timeout=1000)


def test_confirmed_factory_reset_resets_the_keyboard(qtbot, tmp_path, monkeypatch):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    sim.blocks["led_effect"][9] = 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.device_page.reset_button.click()
    rig.step()
    assert (0x0F, 0, b"") in sim.writes
    assert window.pages[0].brightness.value() == 5


def test_factory_reset_question_defaults_to_no(qtbot, monkeypatch):
    page = DevicePage()
    qtbot.addWidget(page)
    asked = []

    def question(*args):
        asked.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", question)
    page.reset_button.click()
    parent, _title, text, buttons, default = asked[0]
    assert parent is page
    assert "return to the factory defaults" in text
    assert buttons == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert default == QMessageBox.StandardButton.No


def test_declined_factory_reset_sends_nothing(qtbot, tmp_path, monkeypatch):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window.device_page.reset_button.click()
    rig.step()
    assert sim.writes == []


def test_light_box_change_writes_the_page_colour_and_remembers_it(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page_of(window, LightBoxPage).brightness.setValue(4)
    rig.step()
    assert light_box.decode(bytes(sim.blocks["light_box"])) == LightBox(1, (255, 255, 255), True, 4, 5)
    assert settings.value("light_box/colour") == "#ffffff"
    assert page_of(window, LightBoxPage).colour_note.isHidden()


def test_settings_change_writes_the_settings(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    page_of(window, SettingsPage).sleep.setValue(10)
    rig.step()
    assert sim.blocks["settings"][3] == 10


def test_polling_rate_change_on_the_cable_waits_for_the_restart(qtbot, tmp_path):
    sim = SimulatedKeyboard()
    window, rig, _settings = make_window(qtbot, tmp_path, cable=sim)
    rig.step()
    sim.drop[0x21] = 4
    page_of(window, SettingsPage).polling_rate.setCurrentIndex(3)
    rig.step()
    assert window.stack.currentWidget() is window.not_connected
    assert window.not_connected.reason.text() == RESTARTING
    assert window.connection_label.text() == RESTARTING
    assert window.statusBar().currentMessage() == ""
