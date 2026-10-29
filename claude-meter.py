#!/usr/bin/env python3
"""Medidor de uso de Claude siempre encima: ventana de 5 horas y semanal del plan.

Los datos los escribe la status line de Claude Code en ~/.cache/claude-meter.json
cada vez que Claude responde; este widget solo los lee.

- La mascota cambia de ánimo según el uso: feliz con poco, cansada y triste al acercarse al límite.
- En reposo solo se ve el muñeco y un globito con su ánimo; al pasar el mouse aparecen los porcentajes.
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
MASCOT = 64
FRAME_MS = 80
LOOP = 6.6  # segundos; todo movimiento de la mascota se repite en este ciclo y así se dibuja una sola vez

# ánimo según el mayor de los dos porcentajes: (hasta %, ánimo)
MOODS = [(50, "happy"), (75, "ok"), (90, "tired"), (100, "sad")]
MOOD_TEXT = {
    "happy": "¡Estoy feliz!",
    "ok": "Estoy bien",
    "tired": "Estoy cansado…",
    "sad": "Estoy triste",
    "empty": "Estoy agotado",
    "sleep": "Zzz…",
}

CSS = b"""
window { background-color: transparent; }
.card { background-color: rgba(22, 22, 22, 0.95); border-radius: 12px; }
.head { color: #d97757; font-weight: bold; }
.bubble { color: #ffffff; font-size: 9pt; font-weight: bold; background-color: rgba(22, 22, 22, 0.85);
          border-radius: 9px; padding: 2px 8px; }
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


def mascot_svg(mood, t, px=MASCOT, crop=True):
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

    # recortado: sin el aire de arriba/abajo, para poder pegarlo a los bordes de la pantalla
    vb = (6, 44) if crop else (0, 56)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 {2} 56 {3}" '
            'shape-rendering="crispEdges">{4}</svg>').format(px, round(px * vb[1] / 56), vb[0], vb[1], "".join(parts))


def ago(epoch):
    mins = int((time.time() - epoch) // 60)
    if mins < 1:
        return "ahora"
    if mins < 60:
        return "hace {} min".format(mins)
    return "hace {} h".format(mins // 60)


class Meter(Gtk.Window):
    """Ventana del muñeco. Solo se mueve cuando el usuario la arrastra; el detalle va en otra ventana."""

    def __init__(self):
        super().__init__(title="Claude meter")
        self.config = load_json(CONF, {})
        self.save_pos_id = 0
        self.mood = "sleep"
        self.dragging = False
        self.drag_end_id = 0
        self.hide_id = 0
        self.t0 = time.time()
        self.frames = {}  # ánimo -> lista de pixbufs del ciclo
        self._setup_css()
        self._setup_window()
        self._build_buddy()
        self._build_details()
        anchor = self.config.get("anchor")
        if anchor:
            self.move(*anchor)
        else:
            self._to_corner()
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)
        GLib.timeout_add(FRAME_MS, self._animate)

    # ---------- ventana del muñeco ----------
    def _setup_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    @staticmethod
    def _transparent(win):
        visual = win.get_screen().get_rgba_visual()
        if visual:
            win.set_visual(visual)
            win.set_app_paintable(True)

    def _setup_window(self):
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_icon_name("claude-meter")
        self.stick()
        self._transparent(self)
        # al cambiar de tamaño (texto del globito) se conserva la esquina inferior derecha: el muñeco no se corre
        self.set_gravity(Gdk.Gravity.SOUTH_EAST)
        self.connect("configure-event", self._on_configure)
        self.connect("destroy", Gtk.main_quit)

    def _end_drag_later(self):
        # el gestor de ventanas no avisa al soltar: se da por terminado tras un rato sin movimiento
        if self.drag_end_id:
            GLib.source_remove(self.drag_end_id)
        self.drag_end_id = GLib.timeout_add(700, self._drag_done)

    def _drag_done(self):
        self.drag_end_id = 0
        self.dragging = False
        return False

    def _on_configure(self, *_):
        if self.dragging:
            self._end_drag_later()
        if self.save_pos_id:
            GLib.source_remove(self.save_pos_id)
        self.save_pos_id = GLib.timeout_add(600, self._save_pos)

    def _save_pos(self):
        self.save_pos_id = 0
        self.config.pop("pos", None)  # formato viejo (esquina superior izquierda)
        self.config["anchor"] = list(self.get_position())
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(CONF, "w") as f:
            json.dump(self.config, f)
        return False

    def _to_corner(self):
        """Pega el muñeco a la esquina inferior derecha del área útil (sin tapar barras del sistema)."""
        mon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
        area = mon.get_workarea()
        size = self.get_preferred_size()[1]
        self.move(area.x + area.width - size.width - 8, area.y + area.height - size.height - 8)

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

    def _hover_box(self, win):
        root = Gtk.EventBox()
        root.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        root.connect("enter-notify-event", self._on_enter)
        root.connect("leave-notify-event", self._on_leave)
        win.add(root)
        return root

    def _build_buddy(self):
        root = self._hover_box(self)
        root.connect("button-press-event", self._on_press)
        buddy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        root.add(buddy)
        # globito con el ánimo y el muñeco, sin fondo
        self.mood_lbl = self._label("bubble")
        self.mood_lbl.set_halign(Gtk.Align.END)
        self.mascot = Gtk.Image()
        self.mascot.set_size_request(MASCOT, round(MASCOT * 44 / 56))
        self.mascot.set_halign(Gtk.Align.END)
        buddy.pack_start(self.mood_lbl, False, False, 0)
        buddy.pack_start(self.mascot, False, False, 0)
        self.show_all()

    def _build_details(self):
        """Tarjeta con los porcentajes: ventana emergente aparte que se abre a la izquierda del muñeco."""
        self.popup = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._transparent(self.popup)
        root = self._hover_box(self.popup)
        card = Gtk.EventBox()
        card.get_style_context().add_class("card")
        root.add(card)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(210, -1)
        # el padding de CSS no aplica a un EventBox; el margen va en la caja
        box.set_margin_top(10)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        card.add(box)

        top = Gtk.Box(spacing=6)
        title = self._label("head")
        title.set_text("Claude")
        self.model = self._label("model", xalign=1)
        top.pack_start(title, False, False, 0)
        top.pack_end(self.model, False, False, 0)
        box.pack_start(top, False, False, 0)
        self.five = self._limit_row(box, "Sesión (5 h)")
        box.pack_start(Gtk.Box(), False, False, 2)
        self.week = self._limit_row(box, "Semana")
        self.foot = self._label("foot")
        box.pack_start(self.foot, False, False, 2)
        root.show_all()

    # ---------- detalle al pasar el mouse ----------
    def _on_enter(self, widget, event):
        if self.dragging:
            return False
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = 0
        if not self.popup.get_visible():
            self._show_details()
        return False

    def _on_leave(self, widget, event):
        # al entrar a un hijo también llega un "leave": ese no cuenta
        if event.detail != Gdk.NotifyType.INFERIOR and not self.hide_id:
            self.hide_id = GLib.timeout_add(300, self._hide_details)
        return False

    def _show_details(self):
        """A la izquierda del muñeco y alineada abajo con él; a la derecha si no cabe."""
        ox, oy = self.get_window().get_origin()[1:]
        w, h = self.get_size()
        pw, ph = (lambda n: (n.width, n.height))(self.popup.get_preferred_size()[1])
        area = Gdk.Display.get_default().get_monitor_at_window(self.get_window()).get_workarea()
        x = ox - pw - 6
        if x < area.x:
            x = ox + w + 6
        y = max(area.y, min(oy + h - ph, area.y + area.height - ph))
        self.popup.move(x, y)
        self.popup.show()

    def _hide_details(self):
        self.hide_id = 0
        self.popup.hide()
        return False

    def _on_press(self, widget, event):
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            # mientras se arrastra no se abre el detalle
            self.dragging = True
            if self.hide_id:
                GLib.source_remove(self.hide_id)
                self.hide_id = 0
            self.popup.hide()
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            self._end_drag_later()
        elif event.button == 3:
            self.popup.hide()
            menu = Gtk.Menu()
            item = Gtk.MenuItem(label="Llevar a la esquina")
            item.connect("activate", lambda *_: self._to_corner())
            menu.append(item)
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
            text += (" · vuelvo en " if full - now < 86400 else " · vuelvo el ") + until(full)
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
