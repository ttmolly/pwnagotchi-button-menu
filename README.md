# pwnagotchi-button-menu

On-screen GPIO menu for [pwnagotchi64](https://github.com/ex18a/pwnagotchi64) on a **128x64 i2coled**.

Version **0.4.1**

No extra apt/pip packages. Buttons are read from `/dev/gpiomem`.

## Controls

| Button | BCM GPIO | On the face | Inside the menu |
|--------|----------|-------------|-----------------|
| OK | 24 | Open menu | Select |
| BACK | 25 | — | Back one screen / close |
| UP | 17 | — | Move up |
| DOWN | 27 | — | Move down |
| RIGHT | 23 | — | Same as OK |
| LEFT | 22 | — | unused |

Buttons go to GND. Internal pull-up is used.

## Screens

```
MENU
> Status        Temp, uptime, handshake count, last file, battery
  Handshakes    Newest files in bettercap.handshakes
  Mode          Restart AUTO / MANU / Stop
  Plugins       Custom plugins only (not this one)
  Power         Restart pwnagotchi, restart bettercap, reboot, shutdown
```

Stop / Reboot / Shutdown ask `OK=yes  BACK=no`.

Closing the menu restores the face, **name**, and status (v0.4.1).

## Install

```bash
sudo mkdir -p /usr/local/share/pwnagotchi/custom-plugins
sudo wget -O /usr/local/share/pwnagotchi/custom-plugins/button_menu.py \
  https://raw.githubusercontent.com/ttmolly/pwnagotchi-button-menu/main/button_menu.py
sudo systemctl restart pwnagotchi
sudo grep -a button_menu /var/log/pwnagotchi.log | tail
```

You want `v0.4.1 loaded`.

`/etc/pwnagotchi/config.toml`:

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

No Wi-Fi / TTL only: do not paste the plugin into `nano` (indent breaks). Use `tee` or `base64 | gzip -d`.

## Plugins screen

Lists `*.py` in `main.custom_plugins` except `button_menu`.

OK writes `/etc/pwnagotchi/conf.d/zz-button-menu.toml` and restarts pwnagotchi. Main `config.toml` is not rewritten.

## Pins

`UP=17 DOWN=27 LEFT=22 RIGHT=23 OK=24 BACK=25`

## Changelog

- **0.4.1** — save/restore face, name, status when leaving the menu
- **0.4.0** — Status / Handshakes / Mode / Plugins / Power; OK opens
- **0.3.3** — first working full-screen menu + reboot/shutdown

## License

GPL-3.0
