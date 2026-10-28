#!/usr/bin/env python3
"""Medidor de uso de Claude siempre encima: ventana de 5 horas y semanal del plan.

Los datos los escribe la status line de Claude Code en ~/.cache/claude-meter.json
cada vez que Claude responde; este widget solo los lee.

- Arrastrar con clic izquierdo para moverlo (recuerda la posición).
- Clic derecho: cerrar.
"""
import json
import os
import time

# En Wayland solo las ventanas X11 pueden pedir "siempre encima"
os.environ.setdefault("GDK_BACKEND", "x11")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

DATA = os.path.expanduser("~/.cache/claude-meter.json")
CONF_DIR = os.path.expanduser("~/.config/claude-meter")
CONF = os.path.join(CONF_DIR, "config.json")
STALE_AFTER = 60 * 60  # pasado esto, el uso desde otros lados (web, móvil) puede no estar reflejado

DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

CSS = b"""
window { background-color: transparent; }
.card { background-color: rgba(22, 22, 22, 0.95); border-radius: 12px; }
.head { color: #d97757; font-weight: bold; }
.model { color: #a7a7a7; font-size: 9pt; }
.name { color: #ffffff; font-size: 9pt; }
.pct { color: #ffffff; font-weight: bold; font-size: 9pt; }
.reset, .foot { color: #8a8a8a; font-size: 8pt; }
.foot.stale { color: #e0a43a; }
progressbar trough { min-height: 6px; border-radius: 3px; background-color: rgba(255, 255, 255, 0.12); border: none; }
progressbar progress { min-height: 6px; border-radius: 3px; border: none; background-color: #4caf7a; }
progressbar.warn progress { background-color: #e0a43a; }
progressbar.crit progress { background-color: #e5534b; }
"""


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def until(epoch):
    secs = max(0, int(epoch - time.time()))
    h, m = divmod(secs // 60, 60)
    if h >= 24:
        t = time.localtime(epoch)
        return "{} {:02d}:{:02d}".format(DAYS[t.tm_wday], t.tm_hour, t.tm_min)
    return "{}h {:02d}m".format(h, m) if h else "{} min".format(m)


def ago(epoch):
    mins = int((time.time() - epoch) // 60)
    if mins < 1:
        return "ahora"
    if mins < 60:
        return "hace {} min".format(mins)
    return "hace {} h".format(mins // 60)


class Meter(Gtk.Window):
    def __init__(self):
        super().__init__(title="Claude meter")
        self.config = load_json(CONF, {})
        self.save_pos_id = 0
        self._setup_window()
        self._build_ui()
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)

    # ---------- ventana ----------
    def _setup_window(self):
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.stick()
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
            self.set_app_paintable(True)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        pos = self.config.get("pos")
        if pos:
            self.move(*pos)
        else:
            mon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
            area = mon.get_workarea()
            self.move(area.x + area.width - 260, area.y + area.height - 160)
        self.connect("configure-event", self._on_configure)
        self.connect("destroy", Gtk.main_quit)

    def _on_configure(self, *_):
        if self.save_pos_id:
            GLib.source_remove(self.save_pos_id)
        self.save_pos_id = GLib.timeout_add(600, self._save_pos)

    def _save_pos(self):
        self.save_pos_id = 0
        self.config["pos"] = list(self.get_position())
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(CONF, "w") as f:
            json.dump(self.config, f)
        return False

    # ---------- interfaz ----------
    def _label(self, css, xalign=0):
        lbl = Gtk.Label(xalign=xalign)
        lbl.get_style_context().add_class(css)
        return lbl

    def _limit_row(self, box, name):
        top = Gtk.Box(spacing=6)
        top.pack_start(self._label("name"), False, False, 0)
        top.get_children()[0].set_text(name)
        pct = self._label("pct", xalign=1)
        top.pack_end(pct, False, False, 0)
        bar = Gtk.ProgressBar()
        reset = self._label("reset")
        box.pack_start(top, False, False, 0)
        box.pack_start(bar, False, False, 0)
        box.pack_start(reset, False, False, 0)
        return pct, bar, reset

    def _build_ui(self):
        card = Gtk.EventBox()
        card.get_style_context().add_class("card")
        card.connect("button-press-event", self._on_press)
        self.add(card)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(210, -1)
        # el padding de CSS no aplica a un EventBox; el margen va en la caja
        box.set_margin_top(10)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        card.add(box)

        head = Gtk.Box(spacing=6)
        title = self._label("head")
        title.set_text("✳ Claude")
        self.model = self._label("model", xalign=1)
        head.pack_start(title, False, False, 0)
        head.pack_end(self.model, False, False, 0)
        box.pack_start(head, False, False, 2)

        self.five = self._limit_row(box, "Sesión (5 h)")
        box.pack_start(Gtk.Box(), False, False, 2)
        self.week = self._limit_row(box, "Semana")
        self.foot = self._label("foot")
        self.foot.set_tooltip_text("Los datos llegan cada vez que Claude Code responde. Sin usarlo no cambian, "
                                   "salvo el reinicio de cada ventana, que el widget calcula solo.")
        box.pack_start(self.foot, False, False, 2)
        self.show_all()

    def _on_press(self, widget, event):
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
        elif event.button == 3:
            menu = Gtk.Menu()
            item = Gtk.MenuItem(label="Cerrar medidor")
            item.connect("activate", lambda *_: self.destroy())
            menu.append(item)
            menu.show_all()
            menu.popup_at_pointer(event)
        return True

    # ---------- datos ----------
    def _set_limit(self, row, win):
        pct, bar, reset = row
        ctx = bar.get_style_context()
        ctx.remove_class("warn")
        ctx.remove_class("crit")
        # una ventana vencida o ausente significa que se reinició: arranca de cero
        if not win or win.get("resets_at", 0) <= time.time():
            pct.set_text("0%")
            bar.set_fraction(0)
            reset.set_text("sin uso en esta ventana")
            return
        used = float(win.get("used_percentage") or 0)
        pct.set_text("{:.0f}%".format(used))
        bar.set_fraction(min(used, 100) / 100)
        if used >= 85:
            ctx.add_class("crit")
        elif used >= 60:
            ctx.add_class("warn")
        reset.set_text("se reinicia en " + until(win["resets_at"]) if win["resets_at"] - time.time() < 86400
                       else "se reinicia el " + until(win["resets_at"]))

    def refresh(self):
        data = load_json(DATA, None)
        if not data:
            self.model.set_text("")
            for row in (self.five, self.week):
                row[0].set_text("—")
                row[1].set_fraction(0)
                row[2].set_text("")
            self.foot.set_text("Sin datos: usa Claude Code una vez")
            return True

        self.model.set_text(data.get("model") or "")
        self._set_limit(self.five, data.get("five_hour"))
        self._set_limit(self.week, data.get("seven_day"))
        updated = data.get("updated_at", 0)
        ctx = self.foot.get_style_context()
        if time.time() - updated > STALE_AFTER:
            ctx.add_class("stale")
        else:
            ctx.remove_class("stale")
        self.foot.set_text("Último uso de Claude " + ago(updated))
        return True


if __name__ == "__main__":
    Meter()
    Gtk.main()
