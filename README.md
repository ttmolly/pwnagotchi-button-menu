# pwnagotchi-button-menu

GPIO on-screen menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on i2coled 128x64.

Version **0.4.0**

## Controls

| Button | GPIO | Action |
|--------|------|--------|
| OK | 24 | Open menu / select |
| BACK | 25 | Back / close |
| UP | 17 | Move up |
| DOWN | 27 | Move down |
| RIGHT | 23 | Same as OK |
| LEFT | 22 | unused |

## Screens

- **Status** — temp, uptime, handshake count, last handshake, battery
- **Handshakes** — files in `bettercap.handshakes`
- **Mode** — AUTO / MANU / Stop
- **Plugins** — custom plugins only (not `button_menu`). Writes `/etc/pwnagotchi/conf.d/zz-button-menu.toml` then restarts pwnagotchi
- **Power** — restart pwnagotchi, restart bettercap, reboot, shutdown

Stop / Reboot / Shutdown ask for confirm.

## Install

```bash
sudo mkdir -p /usr/local/share/pwnagotchi/custom-plugins
sudo wget -O /usr/local/share/pwnagotchi/custom-plugins/button_menu.py \
  https://raw.githubusercontent.com/ttmolly/pwnagotchi-button-menu/main/button_menu.py
sudo systemctl restart pwnagotchi
```

Config:

```toml
main.custom_plugins = "/usr/local/share/pwnagotchi/custom-plugins"

[main.plugins.button_menu]
enabled = true
```

License: GPL-3.0
