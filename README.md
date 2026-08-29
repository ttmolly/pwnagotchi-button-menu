# pwnagotchi-button-menu

GPIO DS-style menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on a 128×64 i2coled (`0x3D`).

**v0.7.2** — `button_menu.py` in this repo is the full plugin. Do not use older stub commits.

## What it is

OK opens a 3×2 grid on the OLED. Face `A:` / `D:` count **this boot**. Lifetime totals live in STAT (`LA` / `LD`) and OPTS → Lifetime.

This plugin does **not** send assoc/deauth. It only counts what Pwnagotchi/Bettercap already did.

## Controls

| Button | BCM GPIO | Face | Menu | Place A/D |
|--------|----------|------|------|-----------|
| OK | 24 | Open | Select | Save this label, next |
| BACK | 25 | | Back / hold closes | Cancel |
| UP DOWN LEFT RIGHT | 17 / 27 / 22 / 23 | | Move | Nudge / hold to slide |
| Hold BACK + OK ~1s | | Lock / unlock | | |

Lock only arms after both pins have been **released** once. That plus pull-ups stops the boot loop (open → close → LOCKED) when GPIOs read low before they settle.

## Face vs lifetime

| Where | What |
|-------|------|
| Face `A:` `D:` | Session. Back to 0 after reboot or `systemctl restart pwnagotchi`. |
| Menu header `A:` `D:` | Same session numbers. |
| STAT `LA` `LD` | Lifetime assoc / deauth. |
| OPTS → Lifetime | Lifetime + current session. |
| OPTS → Reset A/D | Zeros session **and** lifetime. |

Lifetime is `/etc/pwnagotchi/button_menu.json`.

## Fixes in 0.7.2

**GPIO pull-ups on load.** Pins 17/27/22/23/24/25 get BCM pull-ups via `/dev/gpiomem` before the poll thread starts. Without that, idle buttons read as held.

**No false lock on boot.** Combo is ignored until BACK and OK have both gone idle once.

**Lifetime no longer jumps to 0 after a hard power-off.** Saves are: temp file in the same directory → `fsync` → atomic `os.replace`. A torn write used to make the next load fail silently and fall back to defaults (zeros). Leftover `.button_menu-*.tmp` files are cleaned on load.

**Counts flushed before you reboot from the menu.** PWR / MODE actions write the json first. Plugin unload also flushes. Checkpoints still happen every `SAVE_EVERY` (10) events so a yanked battery only loses a few packets.

**Cfg access is locked** so the UI thread and the assoc/deauth hooks do not race the json.

## STAT

2-column, no scroll: TEMP, CAP, UP, DSK, HS, BAT, AGE, LAST, LA, LD.

D-pad moves the cell. OK zooms. BACK leaves.

## Grid

```
47C     A:3  D:1      HS 5
STAT    HS     MODE
PLUG    PWR    OPTS
```

- **STAT** — dashboard above
- **HS** — handshake list / detail
- **MODE** — AUTO / MANU / STOP (confirm)
- **PLUG** — toggle custom plugins (restarts pwnagotchi)
- **PWR** — restart pwn / bettercap / reboot / poweroff (confirm)
- **OPTS** — counter on/off, place A/D, reset, lifetime

## Install

```bash
sudo wget -O /usr/local/share/pwnagotchi/custom-plugins/button_menu.py \
  https://raw.githubusercontent.com/ttmolly/pwnagotchi-button-menu/main/button_menu.py
```

```toml
[main.plugins.button_menu]
enabled = true
```

```bash
sudo python3 -m py_compile /usr/local/share/pwnagotchi/custom-plugins/button_menu.py && echo OK
sudo systemctl restart pwnagotchi
```

Log should show `v0.7.2 loaded` and `pullups {'UP': 1, ... 'OK': 1, 'BACK': 1}`.

OLED: `ui.display.type = "i2coled"`, `i2c_addr = 0x3d`, 128×64.

Turn off any other A/D counter plugin (e.g. EMP) so labels do not stack.

## Pins

Same KeyCrow / handheld map: pull-up, press = low.

## Changelog

- **0.7.2** — atomic json + fsync, cfg lock, flush on menu reboot, pull-ups, lock-ready, session face / lifetime STAT
- **0.7.1** — pull-ups, session vs lifetime split
- **0.6.x** — 3×2 grid, place A/D, hold-to-nudge

GPL-3.0
