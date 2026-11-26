# AULA F108 Pro V2 for Linux

A PyQt5 configurator for the AULA F108 Pro V2 keyboard on Linux. It works over the USB cable and over the 2.4G dongle.

This project is not affiliated with or endorsed by AULA.

## Features

- Backlight: effect, colour, colourful mode, brightness, speed, direction.
- Key colours: paint the keys on a picture of the keyboard. Changed keys are marked with a dot until "Apply" writes them; "Apply" also switches the keyboard to the key colours mode.
- Key animation: a GIF shown on the keys, with a preview, a speed setting and the upload to the keyboard.
- Side lighting: the light strip around the keyboard's perimeter (effect, colour, brightness, speed). The strip above the arrow keys can be set only with key combinations on the keyboard: Fn+left Shift, Fn+left Alt, Fn+left Ctrl, Fn+X.
- 7×7 display: text and background colour, sound reaction, a frame editor, the "Rainbow" and "Pulse in the chosen colour" animations, GIF upload.
- Keys: the actions of the keys on the base layer and on the Fn layer, on a picture of the keyboard. A key can get another key, a media action, a mouse button, a macro, a combination with modifiers, different keys for tap and hold, a toggle or a keyboard function. "Restore defaults…" writes the factory actions of all keys on a layer. Changed keys are marked with a dot until "Apply" writes them.
- Macros: 100 macros M1–M100 made of key and mouse button presses and releases with delays. A macro is assigned to a key on the "Keys" page.
- Settings: polling rate over the cable, sleep time, debounce, Windows or macOS mode, Win key lock.
- Device: model, connection, firmware version, battery charge in 2.4G mode, saving the settings to a JSON file and loading them from it, factory reset.

## udev rule

Without a udev rule only root can access the keyboard. The rule gives access to the logged-in user:

    sudo cp packaging/70-aula-f108-pro-v2.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger

Then reconnect the keyboard and the dongle.

## Running

The program needs the system packages `python3`, `python3-pyqt5` and `python3-pil` (Ubuntu 24.04 with KDE has them installed). The script runs the system `/usr/bin/python3`.

    ./aula-f108

The script `packaging/install-desktop-entry.sh` adds a menu entry: it copies the desktop file to `$XDG_DATA_HOME/applications` (by default `~/.local/share/applications`).

Before starting, close other programs that talk to the keyboard: the vendor's website in a browser, OpenRGB. If the program is already running, a second copy reports that another copy of the program is using the keyboard.

## Known limitations

- The keyboard reports the backlight colour only when it was chosen on the keyboard itself (Fn+Tab). It does not report a colour written by the program; the program then shows the last colour it wrote.
- The keyboard does not report the side lighting colour. The program shows the last colour it wrote; before the first write it shows white.
- When the polling rate over the cable changes, the keyboard restarts. The program reconnects to it by itself.
- In 2.4G mode the keyboard goes to sleep after the set time. The dongle reports a sleeping keyboard the same way as a switched-off one, so the program shows "Keyboard out of reach: asleep or switched off. Press any key to wake it". After any key press the program reconnects by itself.
- Bluetooth is not supported: the vendor does not configure the keyboard over Bluetooth either.
- The keyboard does not report the colours of the 7×7 display or what it shows. The program shows the last colours it wrote; before the first write it shows white text on a black background.
- A cancelled or interrupted animation upload may leave an incomplete animation on the keyboard. Upload the animation again.
- Animations upload slowly over the 2.4G dongle: a key animation of 512 frames takes about 6900 packets.
- The size of the macro memory is unknown. The program does not write macros that take more than 512 bytes, the size the vendor's program states. The "Macros" page shows how many bytes are used.
- Switching between Windows and macOS mode discards unapplied changes on the "Keys" page. This is a precaution: a check on firmware V1.33 showed that the key tables are the same in both modes.
- Key actions the program does not know are shown as bytes and written back unchanged until they are replaced.
- The settings file does not hold animations or the 7×7 display settings. The backlight and side lighting colours in the file are the ones the program shows, because the keyboard does not report a colour written by the program.

## Development

Test environment:

    /usr/bin/python3 -m venv --system-site-packages .venv
    .venv/bin/pip install pytest pytest-qt

Tests:

    .venv/bin/python -m pytest

The tests on a real keyboard write to it and then restore the previous values. They run only when asked for explicitly:

    AULA_HARDWARE=1 .venv/bin/python -m pytest tests/hardware -v

## License

MIT, see `LICENSE`.
