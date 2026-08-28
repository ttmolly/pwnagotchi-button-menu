import logging, os, mmap, time, threading, subprocess
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.ui.view as view
from pwnagotchi.ui.components import Text, FilledRect

PINS = {"UP":17,"DOWN":27,"LEFT":22,"RIGHT":23,"OK":24,"BACK":25}
ITEMS = [("Close","close"),("Stop Pwnagotchi","stop"),("Restart AUTO","auto"),
         ("Restart MANU","manu"),("Reboot","reboot"),("Shutdown","shutdown")]
HIDE = ("face","name","status","channel","aps","uptime","shakes","mode","friend_face","friend_name")

def _run(cmd):
    logging.info("[button_menu] exec %s", cmd)
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class ButtonMenu(plugins.Plugin):
    __author__="evilcrow"
    __version__="0.3.3"
    __license__="GPL3"
    __description__="GPIO power menu"
    def __init__(self):
        self.open=False; self.confirm=None; self.index=0; self.ui=None; self._mem=None
        self._last={n:1 for n in PINS}; self._last_t={n:0.0 for n in PINS}
    def on_loaded(self):
        fd=os.open("/dev/gpiomem", os.O_RDWR|os.O_SYNC)
        self._mem=mmap.mmap(fd,4096); os.close(fd)
        threading.Thread(target=self._loop, daemon=True).start()
        logging.info("[button_menu] v3.3 loaded")
    def on_ui_setup(self, ui):
        self.ui=ui
        ui.add_element("bm_bg", FilledRect([0,0,0,0], view.WHITE))
        for i in range(8):
            ui.add_element("bm%d"%i, Text(value="", position=(2,i*8), font=fonts.Small, color=view.BLACK))
    def on_ui_update(self, ui):
        self.ui=ui
        if self.open:
            self._paint(ui)
    def _lev(self):
        return int.from_bytes(self._mem[13*4:13*4+4], "little")
    def _edge(self, name):
        bit=(self._lev()>>PINS[name])&1
        prev=self._last[name]; self._last[name]=bit
        if prev==1 and bit==0:
            now=time.time()
            if now-self._last_t[name]>0.18:
                self._last_t[name]=now
                return True
        return False
    def _loop(self):
        while True:
            try: self._poll()
            except Exception as e: logging.error("[button_menu] poll %s", e)
            time.sleep(0.04)
    def _poll(self):
        if not self.open:
            for n in PINS:
                if self._edge(n):
                    self.open=True; self.confirm=None; self.index=0
                    logging.info("[button_menu] open via %s", n)
                    self._show(); return
            return
        if self._edge("BACK"):
            if self.confirm: self.confirm=None; self._show()
            else: self._close()
            return
        if self._edge("UP"):
            self.index=(self.index-1)%len(ITEMS); self._show()
        elif self._edge("DOWN"):
            self.index=(self.index+1)%len(ITEMS); self._show()
        elif self._edge("OK") or self._edge("RIGHT"):
            if self.confirm:
                act=self.confirm; self.confirm=None; self._do(act)
            else:
                _,act=ITEMS[self.index]
                if act in ("stop","reboot","shutdown"):
                    self.confirm=act; self._show()
                else:
                    self._do(act)
    def _bg(self, ui, on):
        try:
            bg=dict(ui._state.items()).get("bm_bg")
            if bg is not None:
                bg.xy=[0,0,ui.width(),ui.height()] if on else [0,0,0,0]
        except Exception:
            pass
    def _show(self):
        ui=self.ui or view.ROOT
        if not ui: return
        try: ui.pin(HIDE)
        except Exception: pass
        for k in HIDE:
            try: ui.set(k, "", force=True)
            except Exception: pass
        self._bg(ui, True)
        self._paint(ui)
        try: ui.update(force=True)
        except Exception: pass
    def _paint(self, ui):
        lines=["MENU","","","","","","",""]
        if self.confirm:
            lines[2]="Confirm %s?"%self.confirm.upper()
            lines[3]="OK=yes BACK=no"
        else:
            for i,(lab,_) in enumerate(ITEMS):
                lines[i+1]=("%s %s"%(">" if i==self.index else " ", lab))
        for i,t in enumerate(lines):
            try: ui.set("bm%d"%i, t)
            except Exception: pass
    def _close(self):
        logging.info("[button_menu] close")
        self.open=False; self.confirm=None
        ui=self.ui or view.ROOT
        if not ui: return
        for i in range(8):
            try: ui.set("bm%d"%i, "")
            except Exception: pass
        self._bg(ui, False)
        try: ui.unpin()
        except Exception: pass
        try: ui.update(force=True)
        except Exception: pass
    def _do(self, act):
        logging.info("[button_menu] action %s", act)
        if act=="close": self._close(); return
        if act=="stop": _run("systemctl stop pwnagotchi")
        elif act=="auto": _run("touch /root/.pwnagotchi-auto; rm -f /root/.pwnagotchi-manual; systemctl restart pwnagotchi")
        elif act=="manu": _run("touch /root/.pwnagotchi-manual; rm -f /root/.pwnagotchi-auto; systemctl restart pwnagotchi")
        elif act=="reboot": _run("sync; sleep 1; reboot")
        elif act=="shutdown": _run("sync; sleep 1; poweroff")
