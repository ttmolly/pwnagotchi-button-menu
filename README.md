# pwnagotchi-button-menu

GPIO DS-style menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on 128x64 i2coled.

**v0.7.0** — no screen-sleep (parked).

## Controls

| Button | GPIO | Face | Menu | Place A/D |
|--------|------|------|------|-----------|
| OK | 24 | Open | Select | Save this label, next |
| BACK | 25 | | Back / hold closes | Cancel place |
| D-pad | 17/27/22/23 | | Move | Nudge / hold to slide |
| Hold BACK+OK | 25+24 | Lock / unlock buttons | | |

MODE: LEFT/RIGHT then OK. POWER: D-pad then OK. Restarts ask confirm.

## Root grid

```
47C      A:12  D:7      HS 5
STAT   HS    MODE
PLUG   PWR   OPTS
```

Face A:/D: hide while the menu is open. Counts stay in the header.

## STAT

2-column dashboard: TEMP, CAP, UP, DSK, HS, BAT, AGE, LAST, A, D.
D-pad moves the cell. OK zooms. BACK leaves.

## OPTS

Counter ON/OFF, Place A/D, Reset A/D.

Place: live face, move A, OK, move D, OK. Hold D-pad to slide.
Saved in `/etc/pwnagotchi/button_menu.json`.

## Lock

Hold BACK and OK together ~1s. Status shows `LOCKED`. Same combo unlocks.
Does not blank the OLED.

Turn off any old EMP/counter plugin.

## Install

```bash
sudo wget -O /usr/local/share/pwnagotchi/custom-plugins/button_menu.py \
  https://raw.githubusercontent.com/ttmolly/pwnagotchi-button-menu/main/button_menu.py
sudo systemctl restart pwnagotchi
```

TTL: do not nano-paste. Use base64+gzip chunks.

## Changelog

- **0.7.0** — button lock, 2-col STAT (CAP/disk/HS age/A/D), hide face counters in menu
- **0.6.1** — A/D header, hold-to-nudge place
- **0.6.0** — 3x2 grid + OPTS, A/D on face
- **0.5.1** — restore face/name; confirm restarts
- **0.4.1** — restore name after close

GPL-3.0
