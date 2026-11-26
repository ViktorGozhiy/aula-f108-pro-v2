Raw block reads from an AULA F108 Pro V2 (firmware V1.33), captured on 2026-11-14
with a read-only probe script over the cable (0xFF68 interface).
`wired-<cmd>.hex` holds the data bytes of read command `<cmd>` as one hex string.

`descriptor-<device>-<interface>.hex` holds a HID report descriptor as one hex string, read on
2026-11-14 from `/sys/class/hidraw/hidrawN/device/report_descriptor`: `wired-ff68` (cable command
interface), `wired-ff67` (cable bulk interface), `wired-consumer` (cable interface 1), `dongle-ff80`
(dongle command interface) and `dongle-mouse` (dongle interface 0).
`dongle-<cmd>.hex` holds the same reads through the 2.4G dongle (0xFF80 interface, 32-byte reports),
captured on 2026-11-15. The key tables 0x12 / 0x16 and the macro index 0x15 are byte-identical to the cable reads.
