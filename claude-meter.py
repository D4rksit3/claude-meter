#!/usr/bin/env python3
"""Medidor de uso de Claude siempre encima: ventana de 5 horas y semanal del plan.

Los datos los escribe la status line de Claude Code en ~/.cache/claude-meter.json
cada vez que Claude responde; este widget solo los lee.

- La mascota cambia de ánimo según el uso: feliz con poco, cansada y triste al acercarse al límite.
- Arrastrar con clic izquierdo para moverlo (recuerda la posición).
- Clic derecho: cerrar.
"""
import json
import math
import os
import time

# En Wayland solo las ventanas X11 pueden pedir "siempre encima"
os.environ.setdefault("GDK_BACKEND", "x11")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

DATA = os.path.expanduser("~/.cache/claude-meter.json")
CONF_DIR = os.path.expanduser("~/.config/claude-meter")
CONF = os.path.join(CONF_DIR, "config.json")
STALE_AFTER = 60 * 60  # pasado esto, el uso desde otros lados (web, móvil) puede no estar reflejado

DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MASCOT = 56
FRAME_MS = 80
LOOP = 6.6  # segundos; todo movimiento de la mascota se repite en este ciclo y así se dibuja una sola vez

# ánimo según el mayor de los dos porcentajes: (hasta %, ánimo)
MOODS = [(50, "happy"), (75, "ok"), (90, "tired"), (100, "sad")]
MOOD_TEXT = {
    "happy": "¡Con toda la energía!",
    "ok": "Vamos bien",
    "tired": "Ya se va cansando…",
    "sad": "Casi sin energía",
    "empty": "Agotado",
    "sleep": "Zzz… aún sin datos",
}

CSS = b"""
window { background-color: transparent; }
.card { background-color: rgba(22, 22, 22, 0.95); border-radius: 12px; }
.head { color: #d97757; font-weight: bold; }
.mood { color: #e8e8e8; font-size: 9pt; }
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


def mascot_svg(mood, t, px=MASCOT):
    """Un cuadro del muñequito pixelado de Claude Code, en una caja de 56x56.

    Rejilla de 18x5 celdas: cuerpo, dos ojitos, bracitos a los lados y cuatro patitas.
    """
    ux, uy = 3, 6               # cada pixel es el doble de alto que de ancho, como las celdas de la terminal
    w = 2 * math.pi / LOOP      # frecuencias enteras de w: el ciclo cierra sin saltos
    hop = -abs(math.sin(w * 3 * t)) * 5 if mood == "happy" else 0
    sway = round(math.sin(w * 2 * t)) * 0.5 if mood == "ok" else 0
    sink = {"tired": 2, "sad": 3, "empty": 5, "sleep": 3}.get(mood, 0)
    breathe = math.sin(w * t * (1 if mood in ("sad", "empty", "sleep") else 2)) * 0.4
    x0 = 1 + sway * ux
    y0 = 14 + hop + sink
    # se apaga el color a medida que se cansa
    color = {"happy": "#e8774f", "ok": "#d97757", "tired": "#c98463", "sad": "#b58c79",
             "empty": "#978a84", "sleep": "#b58c79"}[mood]
    hole = "#161616"

    def px_rect(cx, cy, cw=1, ch=1, fill=None, extra=""):
        return '<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="{}"{}/>'.format(
            x0 + cx * ux, y0 + cy * uy, cw * ux, ch * uy, fill or color, extra)

    parts = [
        px_rect(3, 0 - breathe / uy, 12, 2 + breathe / uy),  # cabeza (respira estirándose un poco)
        px_rect(3, 2, 12, 2),                               # cuerpo
    ]
    # bracitos: arriba saludando si está feliz, abajo si está decaído
    if mood == "happy":
        up = math.sin(w * 6 * t) > 0
        parts += [px_rect(1, 1 if up else 2, 2), px_rect(15, 2 if up else 1, 2)]
    elif mood in ("sad", "empty", "tired"):
        parts += [px_rect(1.5, 3, 1.5), px_rect(15, 3, 1.5)]
    else:
        parts += [px_rect(1, 2, 2), px_rect(15, 2, 2)]
    # patitas: caminan cuando está feliz, quietas si no
    step = mood == "happy" and math.sin(w * 6 * t) > 0
    for i, cx in enumerate((4, 6, 11, 13)):
        lift = 0.3 if step and i % 2 == 0 else 0
        parts.append(px_rect(cx, 4 - lift, 1, 1))

    # ojos: huecos en la cabeza
    blink = (t % (LOOP / 2)) < 0.15
    for ex in (5, 12):
        if mood == "sleep" or (blink and mood in ("happy", "ok", "tired")):
            parts.append(px_rect(ex, 1.65, 1, 0.2, hole))
        elif mood == "tired":
            parts.append(px_rect(ex, 1.4, 1, 0.6, hole))
        elif mood == "empty":
            cx, cy = x0 + (ex + 0.5) * ux, y0 + 1.5 * uy
            parts.append('<path d="M{0:.2f} {1:.2f} l{2} {2} M{3:.2f} {1:.2f} l-{2} {2}" stroke="{4}" '
                         'stroke-width="1" stroke-linecap="round"/>'.format(cx - 1.6, cy - 1.6, 3.2, cx + 1.6, hole))
        else:
            parts.append(px_rect(ex, 1, 1, 1, hole))
    if mood == "happy":  # cachetes
        parts += [px_rect(3.5, 1.65, 1, 0.3, "#f6b3a6"), px_rect(13.5, 1.65, 1, 0.3, "#f6b3a6")]
    if mood == "sad":    # lagrimita que cae
        drop = t / LOOP * 4 % 1
        parts.append(px_rect(5.2, 2 + drop * 2.5, 0.6, 0.3, "#6db3e8",
                             ' opacity="{:.2f}"'.format(1 - drop)))
    if mood in ("sleep", "empty"):
        for k in range(2):
            ph = (t / LOOP * 4 + k * 0.5) % 1
            parts.append('<text x="{:.1f}" y="{:.1f}" font-family="monospace" font-weight="bold" '
                         'font-size="{:.1f}" fill="#a7a7a7" opacity="{:.2f}">z</text>'.format(
                             42 + ph * 6, max(8, y0 - 1 - ph * 8), 6 + ph * 4, 1 - ph))

    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{0}" viewBox="0 0 56 56" '
            'shape-rendering="crispEdges">{1}</svg>').format(px, "".join(parts))


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
        self.mood = "sleep"
        self.t0 = time.time()
        self.frames = {}  # ánimo -> lista de pixbufs del ciclo
        self._setup_window()
        self._build_ui()
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)
        GLib.timeout_add(FRAME_MS, self._animate)

    # ---------- ventana ----------
    def _setup_window(self):
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_icon_name("claude-meter")
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

        head = Gtk.Box(spacing=8)
        self.mascot = Gtk.Image()
        self.mascot.set_size_request(MASCOT, MASCOT)
        head.pack_start(self.mascot, False, False, 0)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_valign(Gtk.Align.CENTER)
        top = Gtk.Box(spacing=6)
        title = self._label("head")
        title.set_text("Claude")
        self.model = self._label("model", xalign=1)
        top.pack_start(title, False, False, 0)
        top.pack_end(self.model, False, False, 0)
        self.mood_lbl = self._label("mood")
        self.mood_lbl.set_line_wrap(True)
        self.mood_lbl.set_max_width_chars(22)
        info.pack_start(top, False, False, 0)
        info.pack_start(self.mood_lbl, False, False, 0)
        head.pack_start(info, True, True, 0)
        box.pack_start(head, False, False, 0)

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

    # ---------- mascota ----------
    def _frame(self, mood, i):
        frames = self.frames.setdefault(mood, [None] * int(LOOP * 1000 / FRAME_MS))
        if frames[i] is None:  # se dibuja la primera vez que se necesita y queda en caché
            loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
            loader.write(mascot_svg(mood, i * FRAME_MS / 1000).encode())
            loader.close()
            frames[i] = loader.get_pixbuf()
        return frames[i]

    def _animate(self):
        if self.get_mapped():
            n = int(LOOP * 1000 / FRAME_MS)
            i = int((time.time() - self.t0) * 1000 / FRAME_MS) % n
            self.mascot.set_from_pixbuf(self._frame(self.mood, i))
        return True

    def _set_mood(self, data):
        if not data:
            self.mood = "sleep"
            self.mood_lbl.set_text(MOOD_TEXT["sleep"])
            return
        now = time.time()
        live = [w for w in (data.get("five_hour"), data.get("seven_day"))
                if w and w.get("resets_at", 0) > now]
        used = max([float(w.get("used_percentage") or 0) for w in live] or [0])
        self.mood = next((m for limit, m in MOODS if used < limit), "empty")
        text = MOOD_TEXT[self.mood]
        if self.mood == "empty":
            full = min(w["resets_at"] for w in live if float(w.get("used_percentage") or 0) >= 100)
            text += (" · vuelve en " if full - now < 86400 else " · vuelve el ") + until(full)
        self.mood_lbl.set_text(text)

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
            self._set_mood(None)
            return True

        self.model.set_text(data.get("model") or "")
        self._set_limit(self.five, data.get("five_hour"))
        self._set_limit(self.week, data.get("seven_day"))
        self._set_mood(data)
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
