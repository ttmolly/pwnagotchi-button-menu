# pwnagotchi-button-menu

GPIO on-screen power menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on an i2coled 128x64.

Any button opens the menu. UP/DOWN move. OK selects. BACK closes.

## Buttons (BCM)

| Button | GPIO |
|--------|------|
| UP | 17 |
| DOWN | 27 |
| LEFT | 22 |
| RIGHT | 23 |
| OK | 24 |
| BACK | 25 |

Wired to GND. Internal pull-up via `/dev/gpiomem`. No extra packages.

## Install

```bash
sudo mkdir -p /usr/local/share/pwnagotchi/custom-plugins
sudo cp button_menu.py /usr/local/share/pwnagotchi/custom-plugins/
```

In `/etc/pwnagotchi/config.toml`:

```toml
main.custom_plugins = "/usr/local/share/pwnagotchi/custom-plugins"

[main.plugins.button_menu]
enabled = true

[ui.display]
enabled = true
type = "i2coled"
i2c_addr = 0x3d
width = 128
height = 64
```

```bash
sudo systemctl restart pwnagotchi
```

## Menu

- Close
- Stop Pwnagotchi
- Restart AUTO
- Restart MANU
- Reboot (confirm)
- Shutdown (confirm)

License: GPL-3.0
