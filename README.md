# pwnagotchi-button-menu

GPIO DS-style menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on 128x64 i2coled (`0x3D`).

**v0.7.1**

## Controls

| Button | GPIO | Face | Menu |
|--------|------|------|------|
| OK | 24 | Open | Select |
| BACK | 25 | | Back / hold closes |
| D-pad | 17/27/22/23 | | Move |
| Hold BACK+OK | | Lock / unlock after pins idle | |

Pins get BCM pull-ups on load. Without that every button reads held and the menu lock-loops on boot.

## Face

`A:` / `D:` are this boot only. They go back to 0 after reboot or `systemctl restart pwnagotchi`.

## STAT

2-column: TEMP, CAP, UP, DSK, HS, BAT, AGE, LAST, **LA**, **LD**.

`LA` / `LD` are lifetime assoc / deauth in `/etc/pwnagotchi/button_menu.json`.

## OPTS

Counter on/off, Place A/D, Reset A/D (session + lifetime), Lifetime page.

## Install

Put `button_menu.py` in `/usr/local/share/pwnagotchi/custom-plugins/` and enable:

```toml
[main.plugins.button_menu]
enabled = true
```

```bash
sudo systemctl restart pwnagotchi
```

Header must say v0.7.1. Do not use an old stub file.

GPL-3.0
