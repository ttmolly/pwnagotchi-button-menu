# button_menu v0.4.0 — pwnagotchi64 OLED menu
# OK opens. BACK goes up / closes. UP/DOWN move.
# GPIO via /dev/gpiomem. No extra packages.

import glob
import logging
import mmap
import os
import subprocess
import threading
import time

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.ui.view as view
from pwnagotchi.ui.components import FilledRect, Text

PINS = {"UP": 17, "DOWN": 27, "LEFT": 22, "RIGHT": 23, "OK": 24, "BACK": 25}
HIDE = (
    "face", "name", "status", "channel", "aps", "uptime",
    "shakes", "mode", "friend_face", "friend_name",
)
ROOT = [
    ("Status", "status"),
    ("Handshakes", "handshakes"),
    ("Mode", "mode"),
    ("Plugins", "plugins"),
    ("Power", "power"),
]
STATUS = [
    ("Temp", "temp"),
    ("Uptime", "uptime"),
    ("Handshakes #", "hcount"),
    ("Last handshake", "last"),
    ("Battery", "battery"),
]
MODE = [
    ("Restart AUTO", "auto"),
    ("Restart MANU", "manu"),
    ("Stop Pwnagotchi", "stop"),
]
POWER = [
    ("Restart Pwnagotchi", "restart_pwn"),
    ("Restart Bettercap", "restart_bc"),
    ("Reboot", "reboot"),
    ("Shutdown", "shutdown"),
]
CONFIRM = ("stop", "reboot", "shutdown")
HS_EXT = (".pcap", ".pcapng", ".cap", ".hc22000", ".22000", ".hccapx")


def _run(cmd):
    logging.info("[button_menu] exec %s", cmd)
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


class ButtonMenu(plugins.Plugin):
    __author__ = "evilcrow"
    __version__ = "0.4.0"
    __license__ = "GPL3"
    __description__ = "OLED menu: status, handshakes, mode, plugins, power"

    def __init__(self):
        self.open = False
        self.screen = "menu"
        self.index = 0
        self.offset = 0
        self.confirm = None
        self.detail = None
        self.ui = None
        self.agent = None
        self._mem = None
        self._last = {n: 1 for n in PINS}
        self._last_t = {n: 0.0 for n in PINS}
        self._items = list(ROOT)

    def on_loaded(self):
        fd = os.open("/dev/gpiomem", os.O_RDWR | os.O_SYNC)
        self._mem = mmap.mmap(fd, 4096)
        os.close(fd)
        threading.Thread(target=self._loop, daemon=True).start()
        logging.info("[button_menu] v0.4.0 loaded")

    def on_ready(self, agent):
        self.agent = agent

    def on_ui_setup(self, ui):
        self.ui = ui
        ui.add_element("bm_bg", FilledRect([0, 0, 0, 0], view.WHITE))
        for i in range(8):
            ui.add_element(
                "bm%d" % i,
                Text(value="", position=(2, i * 8), font=fonts.Small, color=view.BLACK),
            )

    def on_ui_update(self, ui):
        self.ui = ui
        if self.open:
            self._paint(ui)

    def _cfg(self):
        if self.agent is not None:
            return getattr(self.agent, "config", None)
        return None

    def _hs_dir(self):
        cfg = self._cfg()
        try:
            return cfg["bettercap"]["handshakes"]
        except Exception:
            return "/home/pwn/handshakes"

    def _hs_files(self):
        folder = self._hs_dir()
        out = []
        try:
            names = os.listdir(folder)
        except Exception:
            return out
        for name in names:
            low = name.lower()
            if low.endswith(HS_EXT):
                path = os.path.join(folder, name)
                try:
                    st = os.stat(path)
                except Exception:
                    continue
                out.append((st.st_mtime, path, name))
        out.sort(reverse=True)
        return out

    def _plugin_dir(self):
        cfg = self._cfg()
        try:
            return cfg["main"]["custom_plugins"] or ""
        except Exception:
            return "/usr/local/share/pwnagotchi/custom-plugins"

    def _plugin_list(self):
        folder = self._plugin_dir()
        names = []
        try:
            for fn in sorted(os.listdir(folder)):
                if fn.endswith(".py") and not fn.startswith("_"):
                    name = fn[:-3]
                    if name != "button_menu":
                        names.append(name)
        except Exception:
            pass
        return names

    def _plugin_on(self, name):
        cfg = self._cfg()
        try:
            return bool(cfg["main"]["plugins"].get(name, {}).get("enabled"))
        except Exception:
            return False

    def _toggle_plugin(self, name):
        folder = "/etc/pwnagotchi/conf.d"
        path = folder + "/zz-button-menu.toml"
        try:
            os.makedirs(folder, exist_ok=True)
            import toml
            cfg = {}
            if os.path.exists(path):
                with open(path) as f:
                    cfg = toml.load(f) or {}
            plugs = cfg.setdefault("main", {}).setdefault("plugins", {})
            entry = plugs.setdefault(name, {})
            now = not self._plugin_on(name)
            entry["enabled"] = now
            with open(path, "w") as f:
                toml.dump(cfg, f)
            logging.info("[button_menu] plugin %s -> %s", name, now)
            _run("systemctl restart pwnagotchi")
        except Exception as e:
            logging.error("[button_menu] toggle %s: %s", name, e)

    def _temp(self):
        raw = _read("/sys/class/thermal/thermal_zone0/temp")
        if not raw:
            return "n/a"
        try:
            return "%.1f C" % (int(raw) / 1000.0)
        except Exception:
            return "n/a"

    def _uptime(self):
        raw = _read("/proc/uptime")
        if not raw:
            return "n/a"
        try:
            sec = int(float(raw.split()[0]))
        except Exception:
            return "n/a"
        d, sec = divmod(sec, 86400)
        h, sec = divmod(sec, 3600)
        m, _ = divmod(sec, 60)
        if d:
            return "%dd %dh %dm" % (d, h, m)
        return "%dh %dm" % (h, m)

    def _battery(self):
        for pat in (
            "/sys/class/power_supply/*/capacity",
            "/sys/class/power_supply/*/capacity_level",
        ):
            hits = glob.glob(pat)
            if hits:
                val = _read(hits[0])
                if val:
                    return val if (val.endswith("%") or not val.isdigit()) else val + "%"
        return "n/a"

    def _mode_now(self):
        if os.path.exists("/root/.pwnagotchi-manual"):
            return "MANU"
        return "AUTO"

    def _lines_for(self):
        title = self.screen.upper()
        rows = []
        if self.confirm:
            return [
                "MENU",
                "",
                "Confirm %s?" % self.confirm.upper().replace("_", " "),
                "OK=yes  BACK=no",
                "", "", "", "",
            ]
        if self.screen == "menu":
            self._items = list(ROOT)
            rows = [lab for lab, _ in ROOT]
        elif self.screen == "status":
            self._items = list(STATUS)
            rows = [lab for lab, _ in STATUS]
        elif self.screen == "status_detail":
            key = self.detail
            if key == "temp":
                return ["TEMP", "", self._temp(), "", "SoC", "", "BACK=back", ""]
            if key == "uptime":
                return ["UPTIME", "", self._uptime(), "", "", "", "BACK=back", ""]
            if key == "hcount":
                return ["HANDSHAKES", "", str(len(self._hs_files())), "", "", "", "BACK=back", ""]
            if key == "last":
                files = self._hs_files()
                name = files[0][2] if files else "none"
                if len(name) > 18:
                    name = name[:17] + ">"
                return ["LAST", "", name, "", "", "", "BACK=back", ""]
            if key == "battery":
                return ["BATTERY", "", self._battery(), "", "", "", "BACK=back", ""]
            return ["STATUS", "", "n/a", "", "", "", "BACK=back", ""]
        elif self.screen == "handshakes":
            files = self._hs_files()
            self._items = [(n, p) for _, p, n in files] or [("empty", None)]
            title = "HS %d" % len(files)
            rows = [n[:16] for _, _, n in files] or ["empty"]
        elif self.screen == "hs_detail":
            name = os.path.basename(self.detail or "")
            try:
                st = os.stat(self.detail)
                size = "%dK" % max(1, st.st_size // 1024)
                when = time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime))
            except Exception:
                size, when = "?", "?"
            if len(name) > 18:
                name = name[:17] + ">"
            return [name, when, size, "", "", "", "BACK=back", ""]
        elif self.screen == "mode":
            self._items = list(MODE)
            rows = [lab for lab, _ in MODE]
            title = "MODE %s" % self._mode_now()
        elif self.screen == "plugins":
            names = self._plugin_list()
            self._items = [(n, n) for n in names] or [("none", None)]
            rows = []
            for n in names:
                flag = "ON" if self._plugin_on(n) else "OFF"
                short = n[:12]
                rows.append("%s %s" % (short.ljust(12), flag))
            if not rows:
                rows = ["none"]
        elif self.screen == "power":
            self._items = list(POWER)
            rows = [lab for lab, _ in POWER]
        else:
            self._items = list(ROOT)
            rows = [lab for lab, _ in ROOT]

        if self.index >= len(self._items):
            self.index = 0
        visible = 6
        if self.index < self.offset:
            self.offset = self.index
        if self.index >= self.offset + visible:
            self.offset = self.index - visible + 1
        lines = [title] + [""] * 7
        for i in range(visible):
            j = self.offset + i
            if j >= len(rows):
                break
            mark = ">" if j == self.index else " "
            lines[i + 1] = ("%s %s" % (mark, rows[j]))[:21]
        return lines

    def _lev(self):
        return int.from_bytes(self._mem[13 * 4:13 * 4 + 4], "little")

    def _edge(self, name):
        bit = (self._lev() >> PINS[name]) & 1
        prev = self._last[name]
        self._last[name] = bit
        if prev == 1 and bit == 0:
            now = time.time()
            if now - self._last_t[name] > 0.18:
                self._last_t[name] = now
                return True
        return False

    def _loop(self):
        while True:
            try:
                self._poll()
            except Exception as e:
                logging.error("[button_menu] poll %s", e)
            time.sleep(0.04)

    def _poll(self):
        if not self.open:
            if self._edge("OK"):
                self.open = True
                self.screen = "menu"
                self.index = 0
                self.offset = 0
                self.confirm = None
                logging.info("[button_menu] open")
                self._show()
            return
        if self._edge("BACK"):
            self._back()
            return
        if self._edge("UP"):
            n = max(1, len(self._items))
            self.index = (self.index - 1) % n
            self._show()
        elif self._edge("DOWN"):
            n = max(1, len(self._items))
            self.index = (self.index + 1) % n
            self._show()
        elif self._edge("OK") or self._edge("RIGHT"):
            self._ok()

    def _back(self):
        if self.confirm:
            self.confirm = None
            self._show()
            return
        if self.screen == "status_detail":
            self.screen = "status"
            self.index = 0
        elif self.screen == "hs_detail":
            self.screen = "handshakes"
            self.index = 0
        elif self.screen == "menu":
            self._close()
            return
        else:
            self.screen = "menu"
            self.index = 0
        self.offset = 0
        self._show()

    def _ok(self):
        if self.confirm:
            act = self.confirm
            self.confirm = None
            self._do(act)
            return
        if not self._items:
            return
        lab, act = self._items[self.index]
        if self.screen == "menu":
            self.screen = act
            self.index = 0
            self.offset = 0
            self._show()
            return
        if self.screen == "status":
            self.screen = "status_detail"
            self.detail = act
            self._show()
            return
        if self.screen == "handshakes":
            if act:
                self.screen = "hs_detail"
                self.detail = act
                self._show()
            return
        if self.screen == "plugins":
            if act:
                self._toggle_plugin(act)
            return
        if self.screen == "mode":
            if act in CONFIRM:
                self.confirm = act
                self._show()
            else:
                self._do(act)
            return
        if self.screen == "power":
            if act in CONFIRM:
                self.confirm = act
                self._show()
            else:
                self._do(act)

    def _bg(self, ui, on):
        try:
            bg = dict(ui._state.items()).get("bm_bg")
            if bg is not None:
                bg.xy = [0, 0, ui.width(), ui.height()] if on else [0, 0, 0, 0]
        except Exception:
            pass

    def _show(self):
        ui = self.ui or view.ROOT
        if not ui:
            return
        try:
            ui.pin(HIDE)
        except Exception:
            pass
        for k in HIDE:
            try:
                ui.set(k, "", force=True)
            except Exception:
                pass
        self._bg(ui, True)
        self._paint(ui)
        try:
            ui.update(force=True)
        except Exception:
            pass

    def _paint(self, ui):
        lines = self._lines_for()
        while len(lines) < 8:
            lines.append("")
        for i in range(8):
            try:
                ui.set("bm%d" % i, lines[i][:21])
            except Exception:
                pass

    def _close(self):
        logging.info("[button_menu] close")
        self.open = False
        self.screen = "menu"
        self.confirm = None
        ui = self.ui or view.ROOT
        if not ui:
            return
        for i in range(8):
            try:
                ui.set("bm%d" % i, "")
            except Exception:
                pass
        self._bg(ui, False)
        try:
            ui.unpin()
        except Exception:
            pass
        try:
            ui.update(force=True)
        except Exception:
            pass

    def _do(self, act):
        logging.info("[button_menu] action %s", act)
        if act == "stop":
            _run("systemctl stop pwnagotchi")
        elif act == "auto":
            _run("touch /root/.pwnagotchi-auto; rm -f /root/.pwnagotchi-manual; systemctl restart pwnagotchi")
        elif act == "manu":
            _run("touch /root/.pwnagotchi-manual; rm -f /root/.pwnagotchi-auto; systemctl restart pwnagotchi")
        elif act == "restart_pwn":
            _run("systemctl restart pwnagotchi")
        elif act == "restart_bc":
            _run("systemctl restart bettercap")
        elif act == "reboot":
            _run("sync; sleep 1; reboot")
        elif act == "shutdown":
            _run("sync; sleep 1; poweroff")
