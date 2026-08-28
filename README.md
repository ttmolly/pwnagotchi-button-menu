# pwnagotchi-button-menu

GPIO DS-style menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on 128x64 i2coled.

**v0.6.1**

## Controls

| Button | GPIO | Face | Menu | Place A/D |
|--------|------|------|------|-----------|
| OK | 24 | Open | Select | Save this label, next |
| BACK | 25 | | Back / close | Cancel place |
| Hold BACK | 25 | | Close all | |
| D-pad | 17/27/22/23 | | Move | Nudge / hold to slide |

MODE: LEFT/RIGHT then OK. POWER: D-pad then OK. Restarts ask confirm.

## Root grid

```
47C      A:12  D:7      HS 5
STAT   HS    MODE
PLUG   PWR   OPTS
```

Face A:/D: widgets hide while the menu is open. Counts stay in the header.

OPTS: Counter ON/OFF, Place A/D, Reset A/D.

Place: live face, move A, OK, move D, OK. Hold D-pad to keep sliding.
Saved in `/etc/pwnagotchi/button_menu.json`.

Turn off any old EMP/counter plugin.

## Install

```bash
sudo wget -O /usr/local/share/pwnagotchi/custom-plugins/button_menu.py \
  https://raw.githubusercontent.com/ttmolly/pwnagotchi-button-menu/main/button_menu.py
sudo systemctl restart pwnagotchi
```

TTL: do not nano-paste. Use base64+gzip chunks.

## Changelog

- **0.6.1** — A/D in menu header, hide face counters in menu, hold-to-nudge
- **0.6.0** — 3x2 grid + OPTS, A/D on face, place-on-face
- **0.5.1** — restore face/name; confirm restarts
- **0.4.1** — restore name after close

GPL-3.0
