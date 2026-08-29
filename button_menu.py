

# button_menu v0.7.2 — DS grid + A/D counters + place-on-face
# OK opens/selects. BACK backs out. Hold BACK closes.
# Place: move A, OK saves, move D, OK saves.

import glob
import json
import logging
import mmap
import os
import subprocess
import tempfile
import threading
import time

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.ui.view as view
from pwnagotchi.ui.components import FilledRect, LabeledValue, Widget

PINS = {"UP": 17, "DOWN": 27, "LEFT": 22, "RIGHT": 23, "OK": 24, "BACK": 25}
HIDE = (
    "face", "name", "status", "channel", "aps", "uptime",
    "shakes", "mode", "friend_face", "friend_name",
)
TILES = [
    ("STAT", "status"),
    ("HS", "handshakes"),
    ("MODE", "mode"),
    ("PLUG", "plugins"),
    ("PWR", "power"),
    ("OPTS", "options"),
]
NAV = {
    0: {"LEFT": 2, "RIGHT": 1, "UP": 3, "DOWN": 3},
    1: {"LEFT": 0, "RIGHT": 2, "UP": 4, "DOWN": 4},
    2: {"LEFT": 1, "RIGHT": 0, "UP": 5, "DOWN": 5},
    3: {"LEFT": 5, "RIGHT": 4, "UP": 0, "DOWN": 0},
    4: {"LEFT": 3, "RIGHT": 5, "UP": 1, "DOWN": 1},
    5: {"LEFT": 4, "RIGHT": 3, "UP": 2, "DOWN": 2},
}
STATUS_PAGES = (
    ("TEMP", "temp"), ("CAP", "cap"),
    ("UP", "uptime"), ("DSK", "disk"),
    ("HS", "hcount"), ("BAT", "battery"),
    ("AGE", "hsage"), ("LAST", "last"),
    ("LA", "assoc"), ("LD", "deauth"),
)

MODE = [("AUTO", "auto"), ("MANU", "manu"), ("STOP", "stop")]
POWER = [("PWN", "restart_pwn"), ("CAP", "restart_bc"), ("BOOT", "reboot"), ("OFF", "shutdown")]
OPTS = [("Counter", "toggle"), ("Place A/D", "place"), ("Reset A/D", "reset"), ("Lifetime", "life")]
CONFIRM = ("stop", "reboot", "shutdown", "auto", "manu", "restart_pwn", "restart_bc")
HS_EXT = (".pcap", ".pcapng", ".cap", ".hc22000", ".22000", ".hccapx")
CFG_PATH = "/etc/pwnagotchi/button_menu.json"
STEP = 2
SAVE_EVERY = 10  # lifetime counters are fsynced to disk every N events;
                 # lower this to trade SD-card wear for less possible
                 # loss on an unclean power pull
DEFAULTS = {
    "counter_on": True,
    "assoc_xy": [2, 20],
    "deauth_xy": [2, 32],
    "assoc": 0,
    "deauth": 0,
}

ICONS = {
    "STAT": [0x18, 0x18, 0x18, 0x18, 0x3C, 0x3C, 0x18, 0x00],
    "HS":   [0x3C, 0x42, 0x99, 0xBD, 0x99, 0x42, 0x3C, 0x00],
    "MODE": [0x10, 0x18, 0x1C, 0x1E, 0x1C, 0x18, 0x10, 0x00],
    "PLUG": [0x66, 0x66, 0x66, 0xFF, 0xFF, 0x7E, 0x3C, 0x18],
    "PWR":  [0x18, 0x3C, 0x66, 0xC3, 0xFF, 0xC3, 0xC3, 0x00],
    "OPTS": [0x18, 0x18, 0x7E, 0x7E, 0x18, 0x18, 0x00, 0x18],
}


def _run(cmd):
    logging.info("[button_menu] exec %s", cmd)
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def _icon(drawer, x, y, rows, color):
    for iy, row in enumerate(rows):
        for ix in range(8):
            if row & (0x80 >> ix):
                drawer.point((x + ix, y + iy), fill=color)


class MenuCanvas(Widget):
    def __init__(self, plugin):
        super().__init__((0, 0), view.BLACK)
        self.plugin = plugin

    def draw(self, canvas, drawer):
        p = self.plugin
        if not p.open:
            return
        w, h = canvas.size
        drawer.rectangle([0, 0, w - 1, h - 1], fill=view.WHITE)
        font = fonts.Small
        if p.confirm:
            self._confirm(drawer, font, p.confirm)
            return
        fn = {
            "menu": self._root, "status": self._status, "status_detail": self._status,
            "handshakes": self._hs,
            "hs_detail": self._hs_detail, "mode": self._mode, "plugins": self._plugins,
            "power": self._power, "options": self._options, "life": self._life,
        }.get(p.screen, self._root)
        fn(drawer, w, h, font, p)

    def _confirm(self, drawer, font, act):
        label = act.upper().replace("_", " ")
        drawer.text((8, 18), "Confirm %s?" % label, font=font, fill=view.BLACK)
        drawer.text((16, 36), "OK=yes  BACK=no", font=font, fill=view.BLACK)

    def _root(self, drawer, w, h, font, p):
        drawer.text((2, 1), p._temp(), font=font, fill=view.BLACK)
        mid = "A:%s  D:%s" % (int(p.sess_assoc), int(p.sess_deauth))
        drawer.text((max(28, (w - int(font.getlength(mid))) // 2), 1), mid, font=font, fill=view.BLACK)
        hs = "HS %d" % p._hs_count()
        drawer.text((w - 2 - int(font.getlength(hs)), 1), hs, font=font, fill=view.BLACK)
        boxes = [
            (1, 12, 41, 25), (43, 12, 41, 25), (85, 12, 42, 25),
            (1, 38, 41, 25), (43, 38, 41, 25), (85, 38, 42, 25),
        ]
        for i, (lab, _) in enumerate(TILES):
            x, y, tw, th = boxes[i]
            sel = i == p.index
            if sel:
                drawer.rectangle([x, y, x + tw - 1, y + th - 1], fill=view.BLACK)
                col = view.WHITE
            else:
                drawer.rectangle([x, y, x + tw - 1, y + th - 1], outline=view.BLACK)
                col = view.BLACK
            ic = ICONS.get(lab)
            if ic:
                _icon(drawer, x + (tw // 2) - 4, y + 2, ic, col)
            lw = int(font.getlength(lab))
            drawer.text((x + max(0, (tw - lw) // 2), y + th - 10), lab, font=font, fill=col)

    def _status(self, drawer, w, h, font, p):
        if p.screen == "status_detail":
            lab, key = STATUS_PAGES[p.index % len(STATUS_PAGES)]
            drawer.text((4, 2), lab, font=font, fill=view.BLACK)
            big = fonts.Bold if fonts.Bold else font
            drawer.text((4, 22), p._status_value(key), font=big, fill=view.BLACK)
            drawer.text((4, 52), "BACK", font=font, fill=view.BLACK)
            return
        drawer.text((2, 1), "STAT", font=font, fill=view.BLACK)
        cw, rh, top = 63, 10, 12
        for i, (lab, key) in enumerate(STATUS_PAGES):
            col, row = i % 2, i // 2
            x = 1 + col * 64
            y = top + row * rh
            val = p._status_value(key)
            if len(val) > 7:
                val = val[:7]
            line = "%s %s" % (lab, val)
            if i == p.index:
                drawer.rectangle([x, y, x + cw, y + rh - 1], fill=view.BLACK)
                drawer.text((x + 2, y), line, font=font, fill=view.WHITE)
            else:
                drawer.text((x + 2, y), line, font=font, fill=view.BLACK)

    def _hs(self, drawer, w, h, font, p):
        files = p._hs_files()
        drawer.text((2, 1), "HS %d" % len(files), font=font, fill=view.BLACK)
        if not files:
            drawer.text((4, 20), "empty", font=font, fill=view.BLACK)
            return
        vis = 5
        if p.index < p.offset:
            p.offset = p.index
        if p.index >= p.offset + vis:
            p.offset = p.index - vis + 1
        for i in range(vis):
            j = p.offset + i
            if j >= len(files):
                break
            name = files[j][2][:16]
            y = 12 + i * 10
            if j == p.index:
                drawer.rectangle([0, y, w - 1, y + 9], fill=view.BLACK)
                drawer.text((4, y), name, font=font, fill=view.WHITE)
            else:
                drawer.text((4, y), name, font=font, fill=view.BLACK)

    def _hs_detail(self, drawer, w, h, font, p):
        name = os.path.basename(p.detail or "")[:18]
        try:
            st = os.stat(p.detail)
            size = "%dK" % max(1, st.st_size // 1024)
            when = time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime))
        except Exception:
            size, when = "?", "?"
        drawer.text((4, 4), name, font=font, fill=view.BLACK)
        drawer.text((4, 18), when, font=font, fill=view.BLACK)
        drawer.text((4, 30), size, font=font, fill=view.BLACK)
        drawer.text((4, 52), "BACK", font=font, fill=view.BLACK)

    def _mode(self, drawer, w, h, font, p):
        drawer.text((4, 2), "MODE %s" % p._mode_now(), font=font, fill=view.BLACK)
        boxes = [(2, 16, 40, 30), (44, 16, 40, 30), (86, 16, 40, 30)]
        for i, (lab, _) in enumerate(MODE):
            x, y, tw, th = boxes[i]
            sel = i == p.index
            if sel:
                drawer.rectangle([x, y, x + tw - 1, y + th - 1], fill=view.BLACK)
                col = view.WHITE
            else:
                drawer.rectangle([x, y, x + tw - 1, y + th - 1], outline=view.BLACK)
                col = view.BLACK
            lw = int(font.getlength(lab))
            drawer.text((x + (tw - lw) // 2, y + 10), lab, font=font, fill=col)

    def _plugins(self, drawer, w, h, font, p):
        names = p._plugin_list()
        drawer.text((2, 1), "PLUGINS", font=font, fill=view.BLACK)
        if not names:
            drawer.text((4, 20), "none", font=font, fill=view.BLACK)
            return
        vis = 5
        if p.index < p.offset:
            p.offset = p.index
        if p.index >= p.offset + vis:
            p.offset = p.index - vis + 1
        for i in range(vis):
            j = p.offset + i
            if j >= len(names):
                break
            flag = "ON" if p._plugin_on(names[j]) else "OFF"
            line = "%s %s" % (names[j][:12].ljust(12), flag)
            y = 12 + i * 10
            if j == p.index:
                drawer.rectangle([0, y, w - 1, y + 9], fill=view.BLACK)
                drawer.text((4, y), line, font=font, fill=view.WHITE)
            else:
                drawer.text((4, y), line, font=font, fill=view.BLACK)

    def _power(self, drawer, w, h, font, p):
        drawer.text((4, 1), "POWER", font=font, fill=view.BLACK)
        boxes = [(2, 14, 61, 23), (65, 14, 61, 23), (2, 39, 61, 23), (65, 39, 61, 23)]
        for i, (lab, _) in enumerate(POWER):
            x, y, tw, th = boxes[i]
            sel = i == p.index
            if sel:
                drawer.rectangle([x, y, x + tw - 1, y + th - 1], fill=view.BLACK)
                col = view.WHITE
            else:
                drawer.rectangle([x, y, x + tw - 1, y + th - 1], outline=view.BLACK)
                col = view.BLACK
            lw = int(font.getlength(lab))
            drawer.text((x + (tw - lw) // 2, y + 7), lab, font=font, fill=col)

    def _life(self, drawer, w, h, font, p):
        drawer.text((2, 1), "LIFETIME", font=font, fill=view.BLACK)
        drawer.text((4, 16), "A %s" % int(p.cfg.get("assoc") or 0), font=font, fill=view.BLACK)
        drawer.text((4, 28), "D %s" % int(p.cfg.get("deauth") or 0), font=font, fill=view.BLACK)
        drawer.text((4, 42), "now A %s D %s" % (int(p.sess_assoc), int(p.sess_deauth)), font=font, fill=view.BLACK)
        drawer.text((4, 54), "BACK", font=font, fill=view.BLACK)

    def _options(self, drawer, w, h, font, p):

        drawer.text((2, 1), "OPTS", font=font, fill=view.BLACK)
        rows = [
            "Counter %s" % ("ON" if p.cfg["counter_on"] else "OFF"),
            "Place A/D",
            "Reset A/D",
            "Lifetime",
        ]
        for i, row in enumerate(rows):
            y = 12 + i * 12
            if i == p.index:
                drawer.rectangle([0, y, w - 1, y + 13], fill=view.BLACK)
                drawer.text((4, y + 2), row, font=font, fill=view.WHITE)
            else:
                drawer.text((4, y + 2), row, font=font, fill=view.BLACK)


class ButtonMenu(plugins.Plugin):
    __author__ = "evilcrow"
    __version__ = "0.7.2"
    __license__ = "GPL3"
    __description__ = "DS grid menu + A/D counters with place-on-face"

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
        self._saved_ui = {}
        self._cursor = {}
        self._back_down = 0.0
        self._lock_ok = 0.0
        self.placing = None
        self._place_old = None
        self._hold_t = {n: 0.0 for n in PINS}
        self.locked = False
        self._lock_ready = False
        self._lock_combo = 0.0
        self.screen_off = False
        self._sleep_down = 0.0
        self._wake_down = 0.0
        self._wait_release = False
        self.sess_assoc = 0
        self.sess_deauth = 0
        self._cfg_lock = threading.RLock()
        self.cfg = dict(DEFAULTS)
        self.cfg["assoc_xy"] = list(DEFAULTS["assoc_xy"])
        self.cfg["deauth_xy"] = list(DEFAULTS["deauth_xy"])

    def on_loaded(self):
        self._load_cfg()
        fd = os.open("/dev/gpiomem", os.O_RDWR | os.O_SYNC)
        self._mem = mmap.mmap(fd, 4096)
        os.close(fd)
        self._pullups()
        threading.Thread(target=self._loop, daemon=True).start()
        logging.info("[button_menu] v0.7.2 loaded")

    def on_ready(self, agent):
        self.agent = agent

    def on_ui_setup(self, ui):
        self.ui = ui
        ui.add_element("bm_bg", FilledRect([0, 0, 0, 0], view.WHITE))
        ui.add_element("bm_ds", MenuCanvas(self))
        ax, ay = self.cfg["assoc_xy"]
        dx, dy = self.cfg["deauth_xy"]
        ui.add_element("bm_assoc", LabeledValue(
            color=view.BLACK, label="A:", value="0",
            position=(ax, ay), label_font=fonts.Bold, text_font=fonts.Medium,
        ))
        ui.add_element("bm_deauth", LabeledValue(
            color=view.BLACK, label="D:", value="0",
            position=(dx, dy), label_font=fonts.Bold, text_font=fonts.Medium,
        ))
        self._apply_counters(ui)

    def on_ui_update(self, ui):
        self.ui = ui
        self._apply_counters(ui)

    def on_association(self, agent, access_point):
        self.sess_assoc += 1
        with self._cfg_lock:
            self.cfg["assoc"] = int(self.cfg.get("assoc") or 0) + 1
            due = self.cfg["assoc"] % SAVE_EVERY == 0
        if due:
            self._save_cfg()

    def on_deauthentication(self, agent, access_point, client_station):
        self.sess_deauth += 1
        with self._cfg_lock:
            self.cfg["deauth"] = int(self.cfg.get("deauth") or 0) + 1
            due = self.cfg["deauth"] % SAVE_EVERY == 0
        if due:
            self._save_cfg()

    def on_unload(self, ui):
        # Fires when the plugin is disabled at runtime (web UI/config
        # toggle) - flush whatever hasn't hit a SAVE_EVERY checkpoint.
        # Note this does NOT fire for `systemctl restart/stop pwnagotchi`
        # or a reboot/poweroff - pwnagotchi's plugin manager only calls
        # on_unload() on an explicit toggle-off. The flush in _do() below
        # is what covers the menu's own PWN/BOOT/OFF/AUTO/MANU actions,
        # which is the path that was actually rolling counts back.
        self._save_cfg()
        logging.info("[button_menu] unloaded, cfg flushed")

    def _load_cfg(self):
        with self._cfg_lock:
            try:
                with open(CFG_PATH) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.cfg.update(data)
            except Exception:
                pass
            self.cfg["assoc_xy"] = list(self.cfg.get("assoc_xy") or DEFAULTS["assoc_xy"])
            self.cfg["deauth_xy"] = list(self.cfg.get("deauth_xy") or DEFAULTS["deauth_xy"])
            # a SIGKILL mid-save can't run _save_cfg()'s own cleanup, so
            # sweep any leftover temp files on the next clean boot
            try:
                for stray in glob.glob(os.path.join(os.path.dirname(CFG_PATH), ".button_menu-*.tmp")):
                    os.unlink(stray)
            except Exception:
                pass

    def _save_cfg(self):
        # Write to a temp file in the same dir, fsync it, then rename
        # over the real path. os.replace() is atomic on POSIX, so a
        # power cut mid-write can only ever leave the OLD complete file
        # or the NEW complete file in place - never a half-written/
        # corrupt one. Previously a torn write here made the next
        # _load_cfg() throw, get silently swallowed, and fall back to
        # DEFAULTS - i.e. the lifetime counters looked like they'd been
        # reset to 0 after a hard power-off.
        with self._cfg_lock:
            d = os.path.dirname(CFG_PATH)
            tmp_path = None
            try:
                os.makedirs(d, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(prefix=".button_menu-", suffix=".tmp", dir=d)
                os.chmod(tmp_path, 0o644)
                with os.fdopen(fd, "w") as f:
                    json.dump(self.cfg, f)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, CFG_PATH)
                tmp_path = None
            except Exception as e:
                logging.error("[button_menu] save cfg %s", e)
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

    def _apply_counters(self, ui):
        show = (bool(self.cfg.get("counter_on")) or self.placing) and not self.open
        ax, ay = self.cfg["assoc_xy"]
        dx, dy = self.cfg["deauth_xy"]
        if not show:
            ax, ay, dx, dy = -80, -80, -80, -80
        try:
            a = dict(ui._state.items()).get("bm_assoc")
            d = dict(ui._state.items()).get("bm_deauth")
            if a is not None:
                a.xy = (ax, ay)
                a.label = ">A:" if self.placing == "assocs" else "A:"
                a.value = str(int(self.sess_assoc))
            if d is not None:
                d.xy = (dx, dy)
                d.label = ">D:" if self.placing == "deauth" else "D:"
                d.value = str(int(self.sess_deauth))
        except Exception:
            pass
        if self.placing:
            try:
                ui.set("status", "place %s  OK=save" % ("A" if self.placing == "assocs" else "D"), force=True)
            except Exception:
                pass

    def _cfg_agent(self):
        if self.agent is not None:
            return getattr(self.agent, "config", None)
        return None

    def _hs_dir(self):
        cfg = self._cfg_agent()
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
            if name.lower().endswith(HS_EXT):
                path = os.path.join(folder, name)
                try:
                    st = os.stat(path)
                except Exception:
                    continue
                out.append((st.st_mtime, path, name))
        out.sort(reverse=True)
        return out

    def _hs_count(self):
        return len(self._hs_files())

    def _plugin_dir(self):
        cfg = self._cfg_agent()
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
        cfg = self._cfg_agent()
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
            return "-- C"
        try:
            return "%.0fC" % (int(raw) / 1000.0)
        except Exception:
            return "-- C"

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

    def _status_value(self, key):
        if key == "temp":
            return self._temp()
        if key == "uptime":
            return self._uptime()
        if key == "hcount":
            return str(self._hs_count())
        if key == "last":
            files = self._hs_files()
            if not files:
                return "none"
            name = files[0][2]
            return name[:16] + ">" if len(name) > 16 else name
        if key == "battery":
            return self._battery()
        if key == "hsage":
            return self._hs_age()
        if key == "cap":
            return self._cap_status()
        if key == "disk":
            return self._disk_free()
        if key == "assoc":
            return str(int(self.cfg.get("assoc") or 0))
        if key == "deauth":
            return str(int(self.cfg.get("deauth") or 0))
        if key == "mode":
            return self._mode_now()
        return "n/a"

    def _hs_age(self):
        files = self._hs_files()
        if not files:
            return "none"
        sec = max(0, int(time.time() - files[0][0]))
        if sec < 60:
            return "%ds ago" % sec
        if sec < 3600:
            return "%dm ago" % (sec // 60)
        if sec < 86400:
            return "%dh ago" % (sec // 3600)
        return "%dd ago" % (sec // 86400)

    def _cap_status(self):
        try:
            r = subprocess.run(
                ["systemctl", "is-active", "bettercap"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                return "UP"
        except Exception:
            pass
        try:
            r = subprocess.run(["pidof", "bettercap"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0:
                return "UP"
        except Exception:
            pass
        return "DOWN"

    def _disk_free(self):
        path = self._hs_dir()
        if not os.path.isdir(path):
            path = "/"
        try:
            st = os.statvfs(path)
            free = st.f_bavail * st.f_frsize
        except Exception:
            return "n/a"
        if free >= 1024 ** 3:
            return "%.1fG free" % (free / (1024.0 ** 3))
        return "%dM free" % (free // (1024 * 1024))

    def _nitems(self):
        return {
            "menu": 6, "status": len(STATUS_PAGES), "status_detail": 1,
            "handshakes": max(1, len(self._hs_files())),
            "mode": 3, "plugins": max(1, len(self._plugin_list())),
            "power": 4, "options": 4,
        }.get(self.screen, 1)

    def _lev(self):
        return int.from_bytes(self._mem[13 * 4:13 * 4 + 4], "little")

    def _edge(self, name):
        bit = (self._lev() >> PINS[name]) & 1
        prev = self._last[name]
        self._last[name] = bit
        if name == "BACK" and bit == 0 and prev == 1:
            self._back_down = time.time()
        if prev == 1 and bit == 0:
            now = time.time()
            if now - self._last_t[name] > 0.16:
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

    def _pullups(self):
        def wr(reg, val):
            self._mem[reg*4:reg*4+4] = int(val).to_bytes(4, "little")
        wr(37, 2)
        time.sleep(0.002)
        mask = 0
        for n in PINS:
            mask |= 1 << PINS[n]
        wr(38, mask)
        time.sleep(0.002)
        wr(37, 0)
        wr(38, 0)
        lev = self._lev()
        for n in PINS:
            self._last[n] = (lev >> PINS[n]) & 1
        logging.info("[button_menu] pullups %s", {n: self._last[n] for n in PINS})

    def _pressed(self, name):

        return ((self._lev() >> PINS[name]) & 1) == 0

    def _poll_lock(self):
        if not getattr(self, "_lock_ready", False):
            if not (self._pressed("BACK") and self._pressed("OK")):
                self._lock_ready = True
            return
        if self._pressed("BACK") and self._pressed("OK"):
            if self._lock_combo == 0.0:
                self._lock_combo = time.time()
            elif 0 < self._lock_combo < time.time() - 0.8:
                self._lock_combo = -1.0
                self.locked = not self.locked
                logging.info("[button_menu] lock %s", self.locked)
                if self.locked:
                    if self.placing:
                        self._place_cancel()
                    if self.open:
                        self._close()
                    ui = self.ui or view.ROOT
                    if ui:
                        try:
                            ui.set("status", "LOCKED", force=True)
                            ui.update(force=True)
                        except Exception:
                            pass
                else:
                    ui = self.ui or view.ROOT
                    if ui:
                        try:
                            ui.set("status", "unlocked", force=True)
                            ui.update(force=True)
                        except Exception:
                            pass
        else:
            self._lock_combo = 0.0

    def _poll(self):
        if self._wait_release:
            if not self._pressed("BACK") and not self._pressed("OK"):
                self._wait_release = False
            for n in PINS:
                self._last[n] = (self._lev() >> PINS[n]) & 1
            return
        self._poll_lock()
        if self.locked:
            for n in PINS:
                self._last[n] = (self._lev() >> PINS[n]) & 1
            return
        if self.placing:
            self._poll_place()
            return
        if not self.open:
            if self._edge("OK"):
                self.open = True
                self.screen = "menu"
                self.index = self._cursor.get("menu", 0)
                self.offset = 0
                self.confirm = None
                logging.info("[button_menu] open")
                self._show()
            return
        if self._last.get("BACK") == 0 and self._back_down and time.time() - self._back_down > 0.7:
            self._back_down = 0.0
            self._wait_release = True
            self._close()
            return
        if self._edge("BACK"):
            self._back()
            return
        if self.screen == "menu":
            for b in ("UP", "DOWN", "LEFT", "RIGHT"):
                if self._edge(b):
                    self.index = NAV[self.index][b]
                    self._cursor["menu"] = self.index
                    self._show()
                    return
            if self._edge("OK"):
                self._ok()
            return
        if self.screen == "status_detail":
            if self._edge("OK") or self._edge("BACK") or self._edge("LEFT"):
                self.screen = "status"
                self._show()
            return
        if self.screen == "status":
            n = len(STATUS_PAGES)
            row, col = divmod(self.index, 2)
            if self._edge("LEFT") or self._edge("RIGHT"):
                col ^= 1
                self.index = row * 2 + col
                if self.index >= n:
                    self.index = n - 1
                self._show()
            elif self._edge("UP"):
                row = (row - 1) % 5
                self.index = row * 2 + col
                if self.index >= n:
                    self.index = n - 1
                self._show()
            elif self._edge("DOWN"):
                row = (row + 1) % 5
                self.index = row * 2 + col
                if self.index >= n:
                    self.index = n - 1
                self._show()
            elif self._edge("OK"):
                self.screen = "status_detail"
                self._show()
            return
        if self.screen == "mode":
            if self._edge("LEFT"):
                self.index = (self.index - 1) % 3
                self._show()
            elif self._edge("RIGHT"):
                self.index = (self.index + 1) % 3
                self._show()
            elif self._edge("OK"):
                self._ok()
            return
        if self.screen == "power":
            grid = {
                0: {"LEFT": 1, "RIGHT": 1, "UP": 2, "DOWN": 2},
                1: {"LEFT": 0, "RIGHT": 0, "UP": 3, "DOWN": 3},
                2: {"LEFT": 3, "RIGHT": 3, "UP": 0, "DOWN": 0},
                3: {"LEFT": 2, "RIGHT": 2, "UP": 1, "DOWN": 1},
            }
            for b in ("UP", "DOWN", "LEFT", "RIGHT"):
                if self._edge(b):
                    self.index = grid[self.index][b]
                    self._show()
                    return
            if self._edge("OK"):
                self._ok()
            return
        if self._edge("UP"):
            self.index = (self.index - 1) % self._nitems()
            self._show()
        elif self._edge("DOWN"):
            self.index = (self.index + 1) % self._nitems()
            self._show()
        elif self._edge("OK"):
            self._ok()
        elif self._edge("LEFT"):
            self._back()

    def _held(self, name):
        bit = (self._lev() >> PINS[name]) & 1
        now = time.time()
        if bit != 0:
            self._hold_t[name] = 0.0
            return False
        if self._hold_t[name] == 0.0:
            self._hold_t[name] = now
            return True
        held = now - self._hold_t[name]
        if held < 0.28:
            return False
        step = 0.05 if held > 0.9 else 0.08
        last = self._last_t.get("_rep_"+name, 0.0)
        if now - last >= step:
            self._last_t["_rep_"+name] = now
            return True
        return False

    def _poll_place(self):
        ui = self.ui or view.ROOT
        key = "assoc_xy" if self.placing == "assocs" else "deauth_xy"
        x, y = list(self.cfg[key])
        moved = False
        if self._held("LEFT"):
            x -= STEP; moved = True
        elif self._held("RIGHT"):
            x += STEP; moved = True
        elif self._held("UP"):
            y -= STEP; moved = True
        elif self._held("DOWN"):
            y += STEP; moved = True
        elif self._edge("OK"):
            self._place_ok()
            return
        elif self._edge("BACK"):
            self._place_cancel()
            return
        if moved and ui:
            w = ui.width()
            h = ui.height()
            x = max(0, min(w - 28, x))
            y = max(0, min(h - 12, y))
            self.cfg[key] = [x, y]
            self._apply_counters(ui)
            try:
                ui.update(force=True)
            except Exception:
                pass

    def _start_place(self):
        self._place_old = {
            "assoc_xy": list(self.cfg["assoc_xy"]),
            "deauth_xy": list(self.cfg["deauth_xy"]),
        }
        self.cfg["counter_on"] = True
        self.placing = "assocs"
        self._close()
        logging.info("[button_menu] place A")

    def _place_ok(self):
        if self.placing == "assocs":
            self.placing = "deauth"
            logging.info("[button_menu] A saved, place D")
            ui = self.ui or view.ROOT
            if ui:
                self._apply_counters(ui)
                try:
                    ui.update(force=True)
                except Exception:
                    pass
            return
        self.placing = None
        self._place_old = None
        self._save_cfg()
        logging.info("[button_menu] D saved")
        ui = self.ui or view.ROOT
        if ui:
            try:
                ui.set("status", "A/D saved", force=True)
                ui.update(force=True)
            except Exception:
                pass

    def _place_cancel(self):
        if self._place_old:
            self.cfg["assoc_xy"] = list(self._place_old["assoc_xy"])
            self.cfg["deauth_xy"] = list(self._place_old["deauth_xy"])
        self.placing = None
        self._place_old = None
        logging.info("[button_menu] place cancel")
        ui = self.ui or view.ROOT
        if ui:
            self._apply_counters(ui)
            try:
                ui.update(force=True)
            except Exception:
                pass

    def _back(self):
        if self.confirm:
            self.confirm = None
            self._show()
            return
        self._cursor[self.screen] = self.index
        if self.screen == "status_detail":
            self.screen = "status"
            self._show()
            return
        if self.screen == "hs_detail":
            self.screen = "handshakes"
            self.index = self._cursor.get("handshakes", 0)
        elif self.screen == "menu":
            self._close()
            return
        else:
            self.screen = "menu"
            self.index = self._cursor.get("menu", 0)
        self.offset = 0
        self._show()

    def _ok(self):
        if getattr(self, "_lock_ok", 0) > time.time():
            return
        if self.confirm:
            act = self.confirm
            self.confirm = None
            self._do(act)
            return
        if self.screen == "menu":
            _, dest = TILES[self.index]
            self._cursor["menu"] = self.index
            self.screen = dest
            self.index = self._cursor.get(dest, 0)
            self.offset = 0
            self._lock_ok = time.time() + 0.35
            self._show()
            return
        if self.screen == "handshakes":
            files = self._hs_files()
            if files and self.index < len(files):
                self.detail = files[self.index][1]
                self._cursor["handshakes"] = self.index
                self.screen = "hs_detail"
                self._show()
            return
        if self.screen == "plugins":
            names = self._plugin_list()
            if names and self.index < len(names):
                self._toggle_plugin(names[self.index])
            return
        if self.screen == "mode":
            _, act = MODE[self.index]
            if act in CONFIRM:
                self.confirm = act
                self._show()
            else:
                self._do(act)
            return
        if self.screen == "power":
            _, act = POWER[self.index]
            if act in CONFIRM:
                self.confirm = act
                self._show()
            else:
                self._do(act)
            return
        if self.screen == "options":
            _, act = OPTS[self.index]
            if act == "toggle":
                self.cfg["counter_on"] = not bool(self.cfg.get("counter_on"))
                self._save_cfg()
                self._show()
            elif act == "place":
                self._start_place()
            elif act == "reset":
                with self._cfg_lock:
                    self.cfg["assoc"] = 0
                    self.cfg["deauth"] = 0
                self.sess_assoc = 0
                self.sess_deauth = 0
                self._save_cfg()
                self._show()
            elif act == "life":
                self.screen = "life"
                self._show()

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
        if not self._saved_ui:
            for k in HIDE:
                try:
                    self._saved_ui[k] = ui.get(k)
                except Exception:
                    self._saved_ui[k] = None
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
        try:
            ui.update(force=True)
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
        self._bg(ui, False)
        for k, val in list(self._saved_ui.items()):
            try:
                ui.set(k, val if val is not None else "", force=True)
            except Exception:
                pass
        self._saved_ui = {}
        try:
            ui.unpin()
        except Exception:
            pass
        self._apply_counters(ui)
        try:
            ui.update(force=True)
        except Exception:
            pass

    def _do(self, act):
        logging.info("[button_menu] action %s", act)
        # Flush the lifetime counters before we tear the process down.
        # This is the actual fix for counts looking wrong after a
        # restart/reboot: PWN/BOOT/OFF/AUTO/MANU all kill or restart the
        # pwnagotchi process, on_unload() does NOT fire for any of them
        # (see the comment on that method), and the periodic every-
        # SAVE_EVERY save may not have hit a checkpoint yet.
        self._save_cfg()
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

