# pwnagotchi-button-menu

GPIO menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on 128x64 i2coled.

**v0.5.0** — DS-style icon grid (not a list).

## Controls

| Button | GPIO | Face | Grid | Inside |
|--------|------|------|------|--------|
| OK | 24 | Open | Enter tile | Select |
| BACK | 25 | | Close | Back |
| Hold BACK | 25 | | Close all | Close all |
| UP/DOWN/LEFT/RIGHT | 17/27/22/23 | | Move on grid | Move / cycle |

## Root

Top strip: temp + handshake count.
Tiles: STAT HS MODE / PLUG PWR. Selected tile is inverted.

STAT pages cycle with LEFT/RIGHT.

## Install

See repo `button_menu.py`. TTL: use base64+gzip, not nano.

GPL-3.0
