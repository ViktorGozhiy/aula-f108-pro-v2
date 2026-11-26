from aula_f108.ui.not_connected_page import NotConnectedPage


def test_help_names_the_udev_rule_file(qtbot):
    page = NotConnectedPage()
    qtbot.addWidget(page)
    assert "packaging/70-aula-f108-pro-v2.rules" in page.help.text()


def test_shows_the_reason(qtbot):
    page = NotConnectedPage()
    qtbot.addWidget(page)
    page.show_reason("Keyboard not found")
    assert page.reason.text() == "Keyboard not found"
